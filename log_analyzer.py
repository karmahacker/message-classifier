"""
Log Analyzer Agent — powered by Qwen3.5-2B via llama.cpp
Collects k8s pod logs, classifies severity, alerts on critical issues.
"""
from flask import Flask, request, jsonify
import requests
import json
import os
import subprocess
from datetime import datetime, timezone

app = Flask(__name__)

LLAMA_URL = os.getenv("LLAMA_URL", "http://llama-cpp-api-2.llama-cpp-2.svc.cluster.local:8080")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # Optional: Telegram/Slack webhook for alerts

ANALYZER_PROMPT = os.getenv("ANALYZER_PROMPT", """You are a log analyzer. Analyze the following Kubernetes pod logs and respond with ONLY a JSON object:

{
  "severity": "normal|warning|error|critical",
  "summary": "one-line summary of what's happening",
  "issues": ["list of specific issues found, empty if none"],
  "action": "recommended action or 'none'"
}

Severity guide:
- normal: healthy operation, no issues
- warning: non-critical issues (high restarts, slow responses, deprecation warnings)
- error: service degradation (crash loops, connection failures, OOM)
- critical: service down, data loss risk, security breach

Be concise. Return ONLY valid JSON.
/no_think""").replace("\\n", "\n")

# Namespaces to skip (noisy infra logs)
SKIP_NAMESPACES = set(os.getenv("SKIP_NAMESPACES", "kube-system,kube-flannel,kube-proxy").split(","))

# Only alert on these severities
ALERT_SEVERITIES = set(os.getenv("ALERT_SEVERITIES", "error,critical").split(","))


def get_pod_logs(namespace, pod, lines=50):
    """Fetch recent logs from a pod via kubectl."""
    try:
        result = subprocess.run(
            ["kubectl", "logs", "-n", namespace, pod, "--tail", str(lines), "--timestamps"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def get_pod_events(namespace, pod):
    """Get recent events for a pod."""
    try:
        result = subprocess.run(
            ["kubectl", "get", "events", "-n", namespace,
             "--field-selector", f"involvedObject.name={pod}",
             "--sort-by=.lastTimestamp", "-o", "custom-columns=TIME:.lastTimestamp,TYPE:.type,REASON:.reason,MESSAGE:.message",
             "--no-headers"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def get_all_pods():
    """Get all running pods across namespaces."""
    try:
        result = subprocess.run(
            ["kubectl", "get", "pods", "--all-namespaces", "-o", "json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
        pods = []
        for item in data.get("items", []):
            ns = item["metadata"]["namespace"]
            name = item["metadata"]["name"]
            phase = item.get("status", {}).get("phase", "Unknown")
            restarts = 0
            for cs in item.get("status", {}).get("containerStatuses", []):
                restarts += cs.get("restartCount", 0)
            if ns not in SKIP_NAMESPACES:
                pods.append({
                    "namespace": ns,
                    "pod": name,
                    "phase": phase,
                    "restarts": restarts,
                })
        return pods
    except Exception as e:
        return []


def analyze_logs(namespace, pod, logs, events=""):
    """Send logs to llama2 for analysis."""
    context = f"Namespace: {namespace}\nPod: {pod}\n\n"
    if events:
        context += f"Events:\n{events}\n\n"
    context += f"Logs (last 50 lines):\n{logs}"

    # Truncate to avoid overwhelming the 2B model
    if len(context) > 4000:
        context = context[:4000] + "\n... (truncated)"

    try:
        resp = requests.post(
            f"{LLAMA_URL}/v1/chat/completions",
            json={
                "messages": [
                    {"role": "system", "content": ANALYZER_PROMPT},
                    {"role": "user", "content": context},
                ],
                "max_tokens": 800,
                "temperature": 0,
            },
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()
        message = result["choices"][0]["message"]
        content = message.get("content", "").strip()
        reasoning = message.get("reasoning_content", "")

        # Try to extract JSON from various formats
        json_str = content

        # Strip markdown code fences
        if "```" in json_str:
            parts = json_str.split("```")
            for part in parts[1:]:
                cleaned = part.strip()
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:].strip()
                if cleaned.startswith("{"):
                    json_str = cleaned
                    break

        # Find JSON object boundaries
        start = json_str.find("{")
        end = json_str.rfind("}")
        if start >= 0 and end > start:
            json_str = json_str[start:end + 1]

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            # Fallback: extract from reasoning if content failed
            severity = "warning"
            if "critical" in (reasoning + content).lower():
                severity = "critical"
            elif "error" in (reasoning + content).lower():
                severity = "error"
            elif "normal" in (reasoning + content).lower():
                severity = "normal"

            summary = reasoning.split("\n")[-1][:200] if reasoning else content[:200]
            parsed = {
                "severity": severity,
                "summary": summary or "Could not parse structured output",
                "issues": [],
                "action": "check manually",
            }

        return parsed
    except Exception as e:
        return {"severity": "unknown", "summary": f"Analysis failed: {e}", "issues": [], "action": "check manually"}


def send_alert(pod_info, analysis):
    """Send alert via webhook if configured."""
    if not WEBHOOK_URL:
        return
    severity = analysis.get("severity", "unknown").upper()
    summary = analysis.get("summary", "No summary")
    ns = pod_info["namespace"]
    pod = pod_info["pod"]
    issues = "\n".join(f"  • {i}" for i in analysis.get("issues", []))
    action = analysis.get("action", "none")

    text = f"🚨 [{severity}] {ns}/{pod}\n{summary}"
    if issues:
        text += f"\n\nIssues:\n{issues}"
    if action and action != "none":
        text += f"\n\nAction: {action}"

    try:
        requests.post(WEBHOOK_URL, json={"text": text}, timeout=10)
    except Exception:
        pass


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/scan", methods=["POST", "GET"])
def scan():
    """Quick scan: list all pods with status, flag problems. No LLM calls."""
    pods = get_all_pods()
    problems = []
    healthy = []

    for p in pods:
        entry = {
            "namespace": p["namespace"],
            "pod": p["pod"],
            "phase": p["phase"],
            "restarts": p["restarts"],
        }
        if p["restarts"] > 3 or p["phase"] not in ("Running", "Succeeded", "Completed"):
            entry["flag"] = "problem"
            problems.append(entry)
        else:
            healthy.append(entry)

    return jsonify({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_pods": len(pods),
        "problems": problems,
        "problem_count": len(problems),
        "healthy_count": len(healthy),
        "tip": "Use POST /analyze with {\"namespace\":\"x\",\"pod\":\"y\"} to AI-analyze specific pods",
    })


@app.route("/scan/deep", methods=["POST", "GET"])
def deep_scan():
    """Deep scan: analyze ONLY problematic pods with LLM. May take 1-2 min per pod."""
    pods = get_all_pods()
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pods_analyzed": 0,
        "results": [],
        "alerts": [],
    }

    # Only analyze pods with actual problems (restarts > 3, not running)
    target_pods = [p for p in pods if p["restarts"] > 3 or p["phase"] not in ("Running", "Succeeded", "Completed")]

    # Cap at 3 pods per scan to stay within timeout
    for p in target_pods[:3]:
        logs = get_pod_logs(p["namespace"], p["pod"])
        if not logs:
            continue

        events = get_pod_events(p["namespace"], p["pod"])
        analysis = analyze_logs(p["namespace"], p["pod"], logs, events)

        result = {
            "namespace": p["namespace"],
            "pod": p["pod"],
            "restarts": p["restarts"],
            "phase": p["phase"],
            "analysis": analysis,
        }
        report["results"].append(result)
        report["pods_analyzed"] += 1

        severity = analysis.get("severity", "normal")
        if severity in ALERT_SEVERITIES:
            report["alerts"].append(result)
            send_alert(p, analysis)

    return jsonify(report)


@app.route("/analyze", methods=["POST"])
def analyze_single():
    """Analyze logs for a specific pod."""
    data = request.get_json(force=True)
    namespace = data.get("namespace", "default")
    pod = data.get("pod", "")
    raw_logs = data.get("logs", "")

    if not pod and not raw_logs:
        return jsonify({"error": "provide 'pod' name or 'logs' text"}), 400

    if not raw_logs and pod:
        raw_logs = get_pod_logs(namespace, pod)
        if not raw_logs:
            return jsonify({"error": f"could not fetch logs for {namespace}/{pod}"}), 404

    events = get_pod_events(namespace, pod) if pod else ""
    analysis = analyze_logs(namespace, pod or "custom", raw_logs, events)

    return jsonify({
        "namespace": namespace,
        "pod": pod or "custom",
        "analysis": analysis,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8002)

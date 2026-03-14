"""
TM (Task Manager) Agent — powered by Qwen3.5-2B via llama.cpp
Receives a feature request, returns structured task breakdown as JSON.
"""
from flask import Flask, request, jsonify
import requests
import json
import os

app = Flask(__name__)

LLAMA_URL = os.getenv("LLAMA_URL", "http://llama-cpp-api-2.llama-cpp-2.svc.cluster.local:8080")

TM_SYSTEM_PROMPT = os.getenv("TM_SYSTEM_PROMPT", """You are TM (Task Manager). Break feature requests into 3-6 tasks. Return ONLY a JSON array. No explanation, no markdown, no wrapping.

Format:
[{"role": "analyst|dev|frontend|devsecops|tester", "priority": "P1|P2|P3|P4", "title": "short title", "spec": "what to do", "depends_on": []}]

Rules:
- First task: analyst (research/design) or dev (if straightforward)
- Last task: always tester (verification)
- Each task = different piece of work
- Specs: concise, actionable — what exactly to build/do
- depends_on: list of task indices (0-based) this task needs completed first. Empty [] if none.
- P1 = critical/blocking, P2 = important, P3 = normal, P4 = nice-to-have
- Roles: analyst (research/design), dev (backend), frontend (UI), devsecops (infra/security), tester (QA)

Return ONLY the JSON array. Nothing else.
/no_think""").replace("\\n", "\n")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/plan", methods=["POST"])
def plan():
    """Receive a feature request, return task breakdown."""
    data = request.get_json(force=True)
    feature_request = data.get("request", "").strip()
    project = data.get("project", "").strip()
    context = data.get("context", "").strip()

    if not feature_request:
        return jsonify({"error": "missing 'request' field"}), 400

    user_msg = ""
    if project:
        user_msg += f"Project: {project}\n"
    if context:
        user_msg += f"Context: {context}\n"
    user_msg += f"\n{feature_request}"

    try:
        resp = requests.post(
            f"{LLAMA_URL}/v1/chat/completions",
            json={
                "messages": [
                    {"role": "system", "content": TM_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "max_tokens": 3000,
                "temperature": 0.1,
            },
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()

        content = result["choices"][0]["message"]["content"].strip()
        reasoning = result["choices"][0]["message"].get("reasoning_content", "")

        # Parse JSON from response — handle markdown wrapping
        json_str = content
        if "```" in json_str:
            json_str = json_str.split("```")[1]
            if json_str.startswith("json"):
                json_str = json_str[4:]
            json_str = json_str.strip()

        tasks = json.loads(json_str)

        # Generate task-cli.sh commands
        project_id = project or "unnamed"
        prefix = "".join(c for c in project_id if c.isalpha()).upper()[:4]
        story_id = f"S-{prefix}-01"

        cli_commands = []
        for t in tasks:
            cmd = (
                f'scripts/team/task-cli.sh create "{project_id}" "{story_id}" '
                f'"{t["role"]}" "{t["priority"]}" "{t["title"]}" "{t.get("spec", "")}"'
            )
            cli_commands.append(cmd)

        return jsonify({
            "tasks": tasks,
            "cli_commands": cli_commands,
            "task_count": len(tasks),
            "project": project_id,
            "story": story_id,
            "reasoning": reasoning[:500] if reasoning else None,
            "tokens": result.get("usage", {}),
        })

    except json.JSONDecodeError as e:
        return jsonify({
            "error": f"Failed to parse model output as JSON: {e}",
            "raw_output": content,
        }), 422
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001)

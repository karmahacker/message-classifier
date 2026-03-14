from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

LLAMA_URL = os.getenv("LLAMA_URL", "http://llama-cpp-api.llama-cpp.svc.cluster.local:8080")

DEFAULT_PROMPT = """You classify messages into exactly one category. Reply with ONLY the category code, nothing else.

Categories:
- UI = Urgent AND Important: Needs immediate action, serious consequences if delayed. Examples: server outage, security breach, payment failure, system crash.
- UN = Urgent AND Not Important: Time-sensitive but low impact. Examples: meeting starting now, someone waiting for reply on trivial matter, expiring coupon.
- NI = Not Urgent AND Important: Matters but can wait hours/days. Examples: tax deadline next week, quarterly review, strategy planning, important email not time-critical.
- NN = Not Urgent AND Not Important: Low priority, no time pressure. Examples: social media notification, funny video, casual chat, newsletter, blog post.

Reply with ONLY: UI, UN, NI, or NN
/no_think"""

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", DEFAULT_PROMPT).replace("\\n", "\n")

LABELS = {
    "UI": "Urgent + Important",
    "UN": "Urgent + Not Important",
    "NI": "Not Urgent + Important",
    "NN": "Not Urgent + Not Important",
}


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/classify", methods=["POST"])
def classify():
    data = request.get_json(force=True)
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "missing 'text' field"}), 400

    try:
        resp = requests.post(
            f"{LLAMA_URL}/v1/chat/completions",
            json={
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "max_tokens": 5,
                "temperature": 0,
            },
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        code = result["choices"][0]["message"]["content"].strip().upper()
        # Normalize: take first valid code found
        for valid in ("UI", "UN", "NI", "NN"):
            if valid in code:
                code = valid
                break
        else:
            code = "UNKNOWN"

        return jsonify({
            "classification": code,
            "label": LABELS.get(code, "Unknown"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

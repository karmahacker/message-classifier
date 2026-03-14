from flask import Flask, request, jsonify
import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

LLAMA_URL = os.getenv("LLAMA_URL", "http://llama-cpp-api.llama-cpp.svc.cluster.local:8080")

DEFAULT_PROMPT = """Ты классифицируешь входящие сообщения от клиентов и подрядчиков digital-агентства.

Верни ТОЛЬКО валидный JSON без пояснений, без markdown, без ```json.

Формат ответа:
{"importance":"...","urgency":"...","category":"...","requires_human":true,"recommended_owner":"..."}

=== importance ===
high   — клиент сообщает о проблеме, потере трафика, остановке рекламы, отсутствии лидов, критической ошибке, потере доступов, жалобе, риске срыва работы
medium — есть запрос на действие, согласование, подготовку, изменение бюджета, прислать отчёт, обновить медиаплан, проверить настройки
low    — обычный статус, подтверждение, информирование без блокера и без срочного риска

=== urgency ===
urgent      — есть явная срочность: "срочно", "сейчас", "не работает", "упало", "лидов нет", "реклама не крутится"
today       — есть указание "сегодня", "до конца дня"
this_week   — требует работы в ближайшие дни, но без аварии
no_deadline — обычный статус без срока и без срочности

=== category ===
seo               — SEO-задачи, органика, позиции, индексация, тексты, семантика, трафик из поиска
ppc               — реклама, кампании, объявления, ставки, открутка, лиды из рекламы
analytics         — отчёты, метрики, аналитика, события, цели, дашборды
billing           — счета, оплата, документы, акты, закрывающие, реквизиты
access            — доступы, логины, права, восстановление доступа
reporting         — запрос отчёта, отправка отчёта руководителю
contractor_update — плановый статус от подрядчика без блокера
approval          — согласование бюджета, подтверждение, запрос обновлённого медиаплана

=== requires_human ===
true  — есть запрос на действие, проблема, согласование, жалоба, блокер, нужен ответ или решение
false — обычный статус от исполнителя без блокера, без вопроса и без просьбы что-то сделать

=== recommended_owner ===
seo     — SEO-вопрос
ppc     — PPC-вопрос
account — клиентская коммуникация, согласование, координация, approval
finance — billing
tech    — доступы, технические проблемы, аналитические настройки
owner   — только если вопрос реально требует эскалации руководителю

Правила:
- не ставь category=seo или category=ppc, если это в первую очередь согласование или обычный статус
- если сообщение короткое, но явно содержит проблему — классифицируй по смыслу
/no_think"""

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", DEFAULT_PROMPT).replace("\\n", "\n")

VALID_IMPORTANCE = {"high", "medium", "low"}
VALID_URGENCY = {"urgent", "today", "this_week", "no_deadline"}
VALID_CATEGORY = {"seo", "ppc", "analytics", "billing", "access", "reporting", "contractor_update", "approval"}
VALID_OWNER = {"seo", "ppc", "account", "finance", "tech", "owner"}


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
                "max_tokens": 60,
                "temperature": 0,
            },
            timeout=30,
            verify=False,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()

        # Strip markdown code fences if model wraps output
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        result = json.loads(raw)

        # Validate and sanitize fields
        importance = result.get("importance", "")
        urgency = result.get("urgency", "")
        category = result.get("category", "")
        requires_human = result.get("requires_human", None)
        recommended_owner = result.get("recommended_owner", "")

        if importance not in VALID_IMPORTANCE:
            importance = "unknown"
        if urgency not in VALID_URGENCY:
            urgency = "unknown"
        if category not in VALID_CATEGORY:
            category = "unknown"
        if not isinstance(requires_human, bool):
            requires_human = None
        if recommended_owner not in VALID_OWNER:
            recommended_owner = "unknown"

        return jsonify({
            "importance": importance,
            "urgency": urgency,
            "category": category,
            "requires_human": requires_human,
            "recommended_owner": recommended_owner,
        })
    except (json.JSONDecodeError, KeyError) as e:
        return jsonify({"error": f"parse error: {e}", "raw": raw}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

# Message Classifier

Lightweight message classifier for digital agency workflows, powered by Qwen3-1.7B via llama.cpp.

Classifies incoming messages from clients and contractors across 5 dimensions:

| Field | Values |
|-------|--------|
| `importance` | `high` / `medium` / `low` |
| `urgency` | `urgent` / `today` / `this_week` / `no_deadline` |
| `category` | `seo` / `ppc` / `analytics` / `billing` / `access` / `reporting` / `contractor_update` / `approval` |
| `requires_human` | `true` / `false` |
| `recommended_owner` | `seo` / `ppc` / `account` / `finance` / `tech` / `owner` |

## Usage

```bash
curl https://classifier.k8s.vrgo.dev/classify \
  -H "Content-Type: application/json" \
  -d '{"text":"Реклама не крутится с утра, лидов нет вообще"}'
```

Response:
```json
{
  "importance": "high",
  "urgency": "urgent",
  "category": "ppc",
  "requires_human": true,
  "recommended_owner": "ppc"
}
```

## Configuration

Copy `.env.example` to `.env` and adjust:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLAMA_URL` | `http://llama-cpp-api.llama-cpp.svc.cluster.local:8080` | llama.cpp server URL |
| `SYSTEM_PROMPT` | *(built-in classifier prompt)* | Override system prompt. Use `\n` for newlines. |

## Run locally

```bash
pip install flask requests python-dotenv
cp .env.example .env
# Edit .env — set LLAMA_URL to your llama.cpp instance
python app.py
```

## Testing

Put one message per line in a file and run:

```bash
./test.sh                                        # test_messages.txt vs localhost:8000
./test.sh my_messages.txt                        # custom file
./test.sh my_messages.txt https://classifier.k8s.vrgo.dev  # custom file + API
```

## Docker

```bash
docker build -t message-classifier .
docker run -p 8000:8000 -e LLAMA_URL=http://host:8080 message-classifier
```

## Deploy (k8s)

Manifests are in [karmahacker/k8s-cluster](https://github.com/karmahacker/k8s-cluster) → `apps/llama-cpp/classifier.yaml`

ArgoCD syncs automatically.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/classify` | Classify a message (`{"text": "..."}`) |

## Stack

- **Runtime:** Python 3.11+ + Flask
- **Model:** Qwen3-1.7B Q4_K_M (1GB, CPU inference)
- **Infra:** Kubernetes, llama.cpp server, nginx ingress + TLS

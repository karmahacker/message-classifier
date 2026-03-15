# Message Classifier

## CI/CD

- **Tests:** Run on every PR to `main`
- **Deploy:** On PR merge → build `PR-<N>` image → push to DO registry → GitOps PR on k8s-cluster → ArgoCD sync
- **Notifications:** Test results and deploy status sent to Telegram


Lightweight message urgency/importance classifier powered by Qwen3-1.7B via llama.cpp.

Classifies messages into 4 categories using the [Eisenhower Matrix](https://en.wikipedia.org/wiki/Time_management#The_Eisenhower_Method):

| Code | Label | When |
|------|-------|------|
| **UI** | Urgent + Important | Needs immediate action, serious consequences if delayed |
| **UN** | Urgent + Not Important | Time-sensitive but low impact |
| **NI** | Not Urgent + Important | Matters but can wait hours/days |
| **NN** | Not Urgent + Not Important | Low priority, no time pressure |

## Usage

```bash
curl https://classifier.k8s.vrgo.dev/classify \
  -H "Content-Type: application/json" \
  -d '{"text":"Server is down, all customers affected"}'
```

Response:
```json
{
  "classification": "UI",
  "label": "Urgent + Important"
}
```

## Configuration

Copy `.env.example` to `.env` and adjust:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLAMA_URL` | `http://llama-cpp-api.llama-cpp.svc.cluster.local:8080` | llama.cpp server URL |
| `SYSTEM_PROMPT` | *(built-in classifier prompt)* | System prompt for classification. Use `\n` for newlines. |

## Run locally

```bash
pip install flask requests gunicorn
cp .env.example .env
# Edit .env — set LLAMA_URL to your llama.cpp instance
python app.py
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

- **Runtime:** Python 3.12 + Flask + Gunicorn
- **Model:** Qwen3-1.7B Q4_K_M (1GB, CPU inference)
- **Infra:** Kubernetes, llama.cpp server, nginx ingress + TLS

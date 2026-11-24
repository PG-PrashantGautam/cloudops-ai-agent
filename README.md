# PG-AI (v1.0) — Local Multi-Agent CloudOps CLI

**PG-AI** (Prashant Gautam AI) is a local, zero-cost, privacy-first **Multi-Agent CloudOps CLI** built in Python. It uses a **Manager-Specialist (Division of Labor)** architecture powered by local LLMs via **Ollama** (`llama3.2` + `qwen2.5-coder:3b`), with optional **AWS Bedrock** fallback.

---

## 1. Architecture Overview (How to Explain It in a Video)

Instead of forcing one giant model to do everything, PG-AI splits the work between a **fast Router** and **focused Specialists**:

```text
User Terminal: pg-ai "check promtail pod in observability"
                         │
                         ▼
         ┌───────────────────────────────┐
         │   MANAGER / ROUTER (pg_ai.py) │  Model: llama3.2 (3B)
         │   Classifies intent -> JSON   │  Temp: 0.0 (Deterministic)
         └───────────────┬───────────────┘
                         │
      ┌──────────────────┼──────────────────┬──────────────────┐
      ▼                  ▼                  ▼                  ▼
┌───────────┐      ┌───────────┐      ┌───────────┐      ┌───────────┐
│ 01 IAM    │      │ 02 Logs   │      │ 03 Cost   │      │ 04 EKS    │
│ Generator │      │ Analyzer  │      │ Analyzer  │      │ Troublesh.│
└───────────┘      └───────────┘      └───────────┘      └───────────┘
                   Model: qwen2.5-coder:3b (Specialist)
```

### Why This Design Matters
* **Zero API Cost & 100% Privacy:** Sensitive logs, IAM ARNs, and Kubernetes configs never leave your laptop when running on Ollama.
* **Fast Routing:** `llama3.2` (3B) only outputs a tiny JSON routing decision.
* **Accurate Technical Output:** `qwen2.5-coder:3b` specializes in YAML, JSON, `kubectl`, and AWS CLI fixes.
* **Offline Demo Ready:** Every specialist supports `--mock` mode so you can demo or teach the full pipeline without live AWS billing or a live cluster.

---

## 2. Project Structure

| Path | Role |
| :--- | :--- |
| `pg_ai.py` | Master CLI entry point & LLM intent router |
| `core/llm_client.py` | Unified LLM wrapper supporting Ollama (local) and AWS Bedrock |
| `projects/01_iam_generator/` | Least-privilege AWS IAM JSON generator + wildcard security linter |
| `projects/02_log_analyzer/` | AWS CloudWatch Logs fetcher + AI root-cause analyzer |
| `projects/03_cost_analyzer/` | AWS Cost Explorer FinOps anomaly detector |
| `projects/04_eks_troubleshooter/` | Fuzzy pod matcher + status-based conditional `kubectl` troubleshooter |

---

## 3. Complete Setup Guide (WSL2 / Ubuntu / Linux)

### Step 1: Prerequisites
* Python 3.10+
* [Ollama](https://ollama.com/) installed and running
* Pull the two lightweight local models:
  ```bash
  ollama pull llama3.2
  ollama pull qwen2.5-coder:3b
  ```
* *(Optional for live AWS/EKS mode)*: `aws configure` and `kubectl` configured for your cluster.

### Step 2: Install Dependencies
```bash
git clone <your-repo-url>
cd pg-ai-v1.0

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Step 3: Make `pg-ai` a Global Linux Command
Create a launcher in `/usr/local/bin/pg-ai` pointing to your project's `venv` Python (update the path if your folder is elsewhere):

```bash
sudo tee /usr/local/bin/pg-ai > /dev/null << 'EOF'
#!/usr/bin/env bash
exec /mnt/d/cloudops-ai-agent/venv/bin/python3 /mnt/d/cloudops-ai-agent/pg_ai.py "$@"
EOF

sudo chmod +x /usr/local/bin/pg-ai
```

Now you can run `pg-ai` from **any directory** without activating `venv`.

---

## 4. Quick Demo Commands (Great for Video Recording)

Run all 4 routes offline using `--mock`:

```bash
# 1. EKS Troubleshooting (CrashLoopBackOff + YAML duplicate key)
pg-ai "check promtail pod in observability" --mock

# 2. IAM Policy Generation + Wildcard Security Linter
pg-ai "create an IAM policy to read and write objects in s3 bucket pg-ai-backups"

# 3. CloudWatch Log Analysis (Cross-account AssumeRole AccessDenied)
pg-ai "check cloudwatch error logs for payment lambda" --mock

# 4. FinOps Cost Anomaly Detection (NAT Gateway & Glue spike)
pg-ai "check aws cost anomalies for the last 7 days" --mock
```

Switch to AWS Bedrock on any command:
```bash
pg-ai "check promtail pod in observability" --mock --provider bedrock
```

---

## 5. How to Push Version-Wise to GitHub (`v1.0`)

```bash
git init
git add .
git commit -m "Release PG-AI v1.0: Deterministic Multi-Agent CloudOps CLI"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main

# Tag v1.0 so viewers can always check out this exact version
git tag -a v1.0 -m "PG-AI v1.0 — Local Multi-Agent CloudOps CLI"
git push origin v1.0
```

---

## 6. Roadmap
* **v1.0 (Current):** Global CLI, strict JSON router, 4 specialists, fuzzy pod matching, status-based conditional branching.
* **v2.0 (Next):** Local RAG with ChromaDB + `nomic-embed-text` for internal runbooks and past RCA memory.
* **v3.0:** Autonomous ReAct tool-calling loop with LangGraph + Human-in-the-Loop (HITL) guardrails.
* **v4.0:** Model Context Protocol (MCP) server/client integration.
* **v5.0:** Proactive AIOps with FastAPI + Prometheus Alertmanager webhooks.

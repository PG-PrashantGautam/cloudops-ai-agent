# PG-AI: Autonomous Dual-Mode CloudOps & AIOps Platform

**PG-AI** is a multi-agent CloudOps assistant and event-driven AIOps platform designed for AWS and Amazon EKS operations. It runs **100% locally at $0 cost** (Ollama + ChromaDB) or scales seamlessly to **AWS Cloud** (Amazon Bedrock Nova + Bedrock Managed Knowledge Base in `ap-south-1`).

---

## Architecture & Release Evolution

| Release | Milestone | Core Capabilities |
| :--- | :--- | :--- |
| **`v1.0`** | **Multi-Agent CLI** | Natural-language intent router (`pg_ai.py`) dispatching to 4 specialists: IAM Policy Generator + InfoSec Linter, CloudWatch Log Analyzer, FinOps Cost Anomaly Detector, and EKS Troubleshooter. |
| **`v2.0`** | **Local RAG Engine** | Semantic runbook retrieval using **ChromaDB** and Ollama (`nomic-embed-text`) so diagnoses prioritize internal SOPs. |
| **`v3.0`** | **Autonomous Agent (HITL)** | **LangGraph** ReAct loop (`langgraph_agent.py`) that inspects pods, consults runbooks, and pauses at `interrupt()` for **Human-in-the-Loop** approval before executing mutating `kubectl` actions. |
| **`v4.0`** | **MCP Server** | Exposes CloudOps tools (`search_cloudops_runbooks`, `inspect_eks_pod`, `lint_iam_policy`) via **Model Context Protocol (MCP SDK v2.x)** over `stdio` for Kiro CLI, VS Code, and Claude Desktop. |
| **`v5.0`** | **Event-Driven AIOps** | **FastAPI** webhook server (`webhook_server.py`) receiving **Prometheus Alertmanager** alerts, returning `202 Accepted` immediately, and running background RAG + LLM incident triage. |
| **`v6.0`** | **AWS Bedrock Cloud Edition** | Dual-mode RAG & LLM backend in `ap-south-1` using **Amazon Nova** (`apac.amazon.nova-micro-v1:0` / `lite-v1:0`) and **AWS Bedrock Managed Knowledge Base**. |

---

## Project Structure

```text
cloudops-ai-agent/
├── pg_ai.py                              # Main CLI & Intent Router
├── core/
│   ├── llm_client.py                     # Dual-mode LLM client (Ollama / AWS Bedrock)
│   └── rag_engine.py                     # Dual-mode RAG engine (ChromaDB / Bedrock Managed KB)
├── knowledge_base/runbooks/              # Internal Markdown SOPs (EKS, AWS, InfoSec)
├── projects/
│   ├── 01_iam_generator/                 # Least-privilege IAM generator & security linter
│   ├── 02_log_analyzer/                  # CloudWatch Logs error triage
│   ├── 03_cost_analyzer/                 # AWS Cost Explorer FinOps analyzer
│   ├── 04_eks_troubleshooter/            # Kubernetes / EKS pod & event diagnostics
│   ├── 05_autonomous_agent/              # v3.0 LangGraph ReAct + HITL agent
│   ├── 06_mcp_server/                    # v4.0 MCP Server + stdio client test
│   └── 07_alertmanager_webhook/          # v5.0 FastAPI Prometheus Alertmanager webhook
└── requirements.txt
Quick Start
1. Setup Environment
Bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
2. Configure .env
Code snippet
# LLM Provider: "ollama" (local) or "bedrock" (AWS)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_ROUTER_MODEL=llama3.2
OLLAMA_SPECIALIST_MODEL=qwen2.5-coder:3b
OLLAMA_EMBED_MODEL=nomic-embed-text

# AWS Bedrock (ap-south-1)
AWS_REGION=ap-south-1
BEDROCK_ROUTER_MODEL_ID=apac.amazon.nova-micro-v1:0
BEDROCK_SPECIALIST_MODEL_ID=apac.amazon.nova-lite-v1:0

# RAG Provider: "local" (ChromaDB) or "bedrock" (Managed KB)
RAG_PROVIDER=local
BEDROCK_KB_ID=<your-kb-id>
BEDROCK_DATA_SOURCE_ID=<your-data-source-id>
BEDROCK_RUNBOOK_BUCKET=<your-s3-bucket>
Usage Examples
1. Ingest Internal Runbooks (Local ChromaDB or Bedrock KB):

Bash
python3 pg_ai.py --ingest
2. Multi-Agent CLI (Local Ollama vs. AWS Bedrock):

Bash
# Local ($0)
python3 pg_ai.py "check promtail pod in observability" --mock

# AWS Bedrock (Amazon Nova + Managed KB)
python3 pg_ai.py "check promtail pod in observability" --mock --provider bedrock
3. Autonomous LangGraph Agent with Human-in-the-Loop (v3.0):

Bash
python3 pg_ai.py --agent "check promtail pod in observability, search runbooks, and restart daemonset if needed" --mock
4. Model Context Protocol Server (v4.0):

Bash
python3 projects/06_mcp_server/test_mcp_client.py
5. Prometheus Alertmanager Webhook Server (v5.0):

Bash
uvicorn projects.07_alertmanager_webhook.webhook_server:app --host 0.0.0.0 --port 8000

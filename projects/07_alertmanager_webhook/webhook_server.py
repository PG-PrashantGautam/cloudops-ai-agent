import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel

# Ensure root 'core' package is importable
ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from core.llm_client import LLMClient
from core.rag_engine import RAGEngine

app = FastAPI(title="PG-AI v5.0 — AIOps Alertmanager Webhook", version="5.0.0")

# In-memory store of recent AI triage reports (for quick inspection via GET /incidents)
INCIDENT_HISTORY: list[dict[str, Any]] = []

TRIAGE_SYSTEM_PROMPT = """You are PG-AI v5.0, an automated SRE Incident Triage Engine.
You have received a firing Prometheus Alertmanager webhook.
If INTERNAL RUNBOOKS / SOPs are provided and match the alert, prioritize the company-approved fix.

Respond concisely with:
1. **Alert Summary:** What failed and where (namespace/pod/service).
2. **Likely Root Cause:** Based on the alert labels, annotations, and runbooks.
3. **Recommended Action:** Exact kubectl or AWS CLI command for the on-call engineer.
"""


class AlertItem(BaseModel):
    status: str = "firing"
    labels: dict[str, str] = {}
    annotations: dict[str, str] = {}


class AlertmanagerPayload(BaseModel):
    receiver: str = "pg-ai-webhook"
    status: str = "firing"
    alerts: list[AlertItem]


def process_alert_triage(alert: AlertItem):
    """Background worker: RAG lookup + LLM diagnosis for a firing alert."""
    alert_name = alert.labels.get("alertname", "UnknownAlert")
    namespace = alert.labels.get("namespace", "default")
    pod = alert.labels.get("pod", "unknown")
    summary = alert.annotations.get("summary", "")
    description = alert.annotations.get("description", "")

    print(f"\n[🚨] Triaging firing alert: {alert_name} | ns={namespace} | pod={pod}")

    search_query = f"{alert_name} {namespace} {pod} {summary} {description}"
    try:
        runbooks = RAGEngine().search(search_query, top_k=2)
        if runbooks:
            print("[📚] Matched internal runbook from ChromaDB.")
    except Exception as e:
        print(f"[⚠️] RAG lookup skipped ({e})")
        runbooks = ""

    prompt_parts = []
    if runbooks:
        prompt_parts.append(f"=== INTERNAL RUNBOOKS / SOPs ===\n{runbooks}\n")
    prompt_parts.append(
        f"=== PROMETHEUS ALERT ===\n"
        f"AlertName: {alert_name}\n"
        f"Status: {alert.status}\n"
        f"Labels: {alert.labels}\n"
        f"Annotations: {alert.annotations}\n"
    )

    client = LLMClient(role="specialist")
    print(f"[🧠] Generating triage report | Provider: {client.provider} | Model: {client.model}")

    report = client.generate(
        prompt="\n".join(prompt_parts),
        system_prompt=TRIAGE_SYSTEM_PROMPT,
        temperature=0.1,
    )

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alertname": alert_name,
        "namespace": namespace,
        "pod": pod,
        "rag_matched": bool(runbooks),
        "triage_report": report,
    }
    INCIDENT_HISTORY.insert(0, record)

    print(f"\n--- 🤖 AI Triage Report ({alert_name}) ---")
    print(report)
    print("------------------------------------------\n")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "pg-ai-v5-webhook"}


@app.get("/incidents")
def list_incidents():
    return {"count": len(INCIDENT_HISTORY), "incidents": INCIDENT_HISTORY}


@app.post("/webhook/alertmanager", status_code=202)
def alertmanager_webhook(payload: AlertmanagerPayload, background_tasks: BackgroundTasks):
    """Receive Prometheus Alertmanager webhooks and queue AI triage in the background."""
    firing_alerts = [a for a in payload.alerts if a.status == "firing"]

    for alert in firing_alerts:
        background_tasks.add_task(process_alert_triage, alert)

    return {
        "status": "accepted",
        "queued_firing_alerts": len(firing_alerts),
        "message": "AI triage queued in background. Check GET /incidents for results.",
    }
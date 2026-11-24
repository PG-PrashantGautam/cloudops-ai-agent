import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from core.llm_client import LLMClient

ROUTER_SYSTEM_PROMPT = """You are the PG-AI CloudOps Intent Router.
Classify the user's request into ONE of these four intents and extract the required parameters as raw JSON.

INTENTS & PARAMETERS:
1. "iam"  -> Creating or generating AWS IAM policies.
   Parameters: {"request": "<plain-English permission request>"}
2. "logs" -> Checking or analyzing AWS CloudWatch logs / Lambda errors.
   Parameters: {"log_group": "<log group name or empty string>", "hours": 24, "filter": "ERROR"}
3. "cost" -> Analyzing AWS billing, spend, FinOps anomalies, or service costs.
   Parameters: {"days": 7}
4. "eks"  -> Troubleshooting Kubernetes / Amazon EKS pods, services, deployments, or namespaces.
   Parameters: {"namespace": "default", "res_type": "pod", "res_name": "<resource name>"}
5. "unknown" -> Anything outside the 4 domains above.
   Parameters: {}

Output ONLY raw, valid JSON in this exact format (no markdown backticks, no explanations):
{"intent": "<iam|logs|cost|eks|unknown>", "parameters": {...}}
"""


def clean_json_response(raw_text: str) -> str:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw_text[start : end + 1].strip()
    return raw_text.strip()


def route_query(user_query: str, provider: str = None) -> dict:
    client = LLMClient(provider=provider, role="router")
    print(f"[🧭] Routing query | Provider: {client.provider} | Router Model: {client.model}")

    raw = client.generate(
        prompt=user_query,
        system_prompt=ROUTER_SYSTEM_PROMPT,
        temperature=0.0,
    )

    try:
        decision = json.loads(clean_json_response(raw))
    except json.JSONDecodeError:
        decision = {"intent": "unknown", "parameters": {}}

    print(f"[🔀] Route Decision: {json.dumps(decision)}")
    return decision


def dispatch_to_specialist(
    decision: dict, provider: str = None, mock: bool = False, no_rag: bool = False
):
    """Execute the matching specialist script using the active Python interpreter."""
    intent = decision.get("intent", "unknown").lower()
    params = decision.get("parameters", {})

    cmd = [sys.executable]

    if intent == "iam":
        script = ROOT_DIR / "projects/01_iam_generator/iam_generator.py"
        req = params.get("request", "").strip()
        if not req:
            print("[❌] Router did not extract an IAM permission request.")
            sys.exit(1)
        cmd += [str(script), req]
        if no_rag:
            cmd += ["--no-rag"]

    elif intent == "logs":
        script = ROOT_DIR / "projects/02_log_analyzer/log_analyzer.py"
        cmd += [str(script)]
        if mock or not params.get("log_group"):
            if not mock:
                print("[ℹ️] No CloudWatch Log Group specified — defaulting to --mock mode.")
            cmd += ["--mock"]
        else:
            cmd += ["--log-group", str(params["log_group"])]
            if params.get("hours"):
                cmd += ["--hours", str(params["hours"])]
            if params.get("filter"):
                cmd += ["--filter", str(params["filter"])]
        if no_rag:
            cmd += ["--no-rag"]

    elif intent == "cost":
        script = ROOT_DIR / "projects/03_cost_analyzer/cost_analyzer.py"
        cmd += [str(script)]
        if mock:
            cmd += ["--mock"]
        else:
            cmd += ["--days", str(params.get("days", 7))]

    elif intent == "eks":
        script = ROOT_DIR / "projects/04_eks_troubleshooter/eks_troubleshooter.py"
        cmd += [str(script)]
        if mock:
            cmd += ["--mock"]
        else:
            cmd += [
                "--namespace", str(params.get("namespace", "default")),
                "--type", str(params.get("res_type", "pod")),
                "--name", str(params.get("res_name", "")),
            ]
        if no_rag:
            cmd += ["--no-rag"]

    else:
        print("[❓] Intent not recognized. Try asking about IAM policies, CloudWatch logs, AWS costs, or EKS pods.")
        sys.exit(0)

    if provider:
        cmd += ["--provider", provider]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(cmd, env=env, check=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PG-AI: Dual-Mode Multi-Agent CloudOps CLI")
    parser.add_argument("query", nargs="?", help="Natural-language CloudOps request")
    parser.add_argument("--provider", choices=["ollama", "bedrock"], default=None, help="Override LLM provider")
    parser.add_argument("--mock", action="store_true", help="Run backend specialist in offline mock mode")
    parser.add_argument("--no-rag", action="store_true", help="Disable local ChromaDB runbook lookup")
    parser.add_argument("--ingest", action="store_true", help="Ingest all runbooks in knowledge_base/runbooks/ into ChromaDB")
    parser.add_argument("--agent", action="store_true", help="Run v3.0 Autonomous LangGraph ReAct Agent (with HITL)")
    args = parser.parse_args()

    if args.ingest:
        from core.rag_engine import RAGEngine
        count = RAGEngine().ingest_runbooks()
        print(f"[✅] Knowledge base updated. Total chunks in ChromaDB: {count}")
        sys.exit(0)

    if args.agent:
        script = ROOT_DIR / "projects/05_autonomous_agent/langgraph_agent.py"
        cmd = [sys.executable, str(script)]
        if args.query:
            cmd.append(args.query)
        if not args.mock:
            cmd.append("--live")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR) + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run(cmd, env=env, check=False)
        sys.exit(0)

    user_query = args.query or input("Ask PG-AI:\n> ").strip()
    if not user_query:
        print("Error: Query cannot be empty.")
        sys.exit(1)

    route_decision = route_query(user_query, provider=args.provider)
    dispatch_to_specialist(
        route_decision, provider=args.provider, mock=args.mock, no_rag=args.no_rag
    )
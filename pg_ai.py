#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.llm_client import LLMClient

ROUTER_SYSTEM_PROMPT = """You are the Master CloudOps Router Agent.
Your job is to classify the user's natural-language infrastructure request into one of four specialist tools and extract parameters as STRICT JSON.

AVAILABLE INTENTS & SCHEMAS:
1. "iam" - Creating or modifying AWS IAM policies or permissions.
   Parameters: {"request": "<exact permission request>"}
2. "logs" - Analyzing AWS CloudWatch Logs or Lambda/application errors.
   Parameters: {"log_group": "<log group name or empty string>", "filter": "<error keyword or ERROR>", "hours": 24}
3. "cost" - Checking AWS billing, spend anomalies, or FinOps cost optimization.
   Parameters: {"days": 7}
4. "eks" - Troubleshooting Kubernetes/EKS pods, services, deployments, or CrashLoopBackOff issues.
   Parameters: {"namespace": "<namespace or default>", "res_type": "<pod|svc|deployment>", "res_name": "<resource name>"}
5. "unknown" - Anything outside these four CloudOps domains.
   Parameters: {}

STRICT RULES:
- Output ONLY raw, valid JSON. No markdown backticks, no explanations.
- Example output: {"intent": "eks", "parameters": {"namespace": "observability", "res_type": "pod", "res_name": "promtail"}}
"""


def extract_json(raw_text: str) -> dict:
    """Extract and parse the JSON object even if the router model adds extra text."""
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(raw_text[start : end + 1].strip())
    return json.loads(raw_text.strip())


def route_query(query: str, provider: str = None) -> dict:
    """Use the fast router model to classify intent and extract parameters."""
    router = LLMClient(provider=provider, role="router")
    print(f"[🧭] Routing query | Provider: {router.provider} | Router Model: {router.model}")

    raw_output = router.generate(
        prompt=f"Classify this request:\n{query}",
        system_prompt=ROUTER_SYSTEM_PROMPT,
        temperature=0.0,
    )

    try:
        decision = extract_json(raw_output)
        print(f"[🔀] Route Decision: {json.dumps(decision)}")
        return decision
    except json.JSONDecodeError as e:
        print(f"[❌] Router returned invalid JSON: {e}\nRaw output:\n{raw_output}")
        sys.exit(1)


def dispatch_to_specialist(decision: dict, provider: str = None, mock: bool = False):
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
    args = parser.parse_args()

    user_query = args.query or input("Ask PG-AI:\n> ").strip()
    if not user_query:
        print("Error: Query cannot be empty.")
        sys.exit(1)

    route_decision = route_query(user_query, provider=args.provider)
    dispatch_to_specialist(route_decision, provider=args.provider, mock=args.mock)

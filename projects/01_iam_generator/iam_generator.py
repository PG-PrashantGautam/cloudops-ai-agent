import argparse
import json
import sys
from pathlib import Path

# Allow importing from the root 'core' package regardless of where the script is run
ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from core.llm_client import LLMClient
from core.rag_engine import RAGEngine

SYSTEM_PROMPT = """You are a Senior AWS Security Architect specializing in IAM least-privilege policies.
Your task is to convert a user's plain-English permission request into a valid AWS IAM Policy JSON.

STRICT RULES:
1. Follow the Principle of Least Privilege. Never use "*" for Action unless explicitly requested.
2. Scope Resource ARNs tightly using realistic placeholders (e.g., arn:aws:s3:::my-bucket/*) instead of "*" wherever AWS supports resource-level permissions.
3. Include a descriptive "Sid" for every statement and always use "Version": "2012-10-17".
4. If INTERNAL INFOSEC GUARDRAILS are provided and apply to the requested AWS service, you MUST enforce their mandatory rules (such as Condition blocks or action scoping) in the generated JSON.
5. Output ONLY raw, valid JSON. Do NOT include markdown backticks (```json), explanations, or extra text.
"""


def clean_json_response(raw_text: str) -> str:
    """Extract the JSON object even if the model adds markdown or trailing notes."""
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw_text[start : end + 1].strip()
    return raw_text.strip()


def security_lint(policy: dict) -> list[str]:
    """Basic least-privilege check for wildcard actions or resources."""
    warnings = []

    if policy.get("Version") != "2012-10-17":
        warnings.append("Missing or invalid 'Version' (expected '2012-10-17').")
    if "Statement" not in policy:
        warnings.append("Missing required 'Statement' block.")

    statements = policy.get("Statement", [])
    if isinstance(statements, dict):
        statements = [statements]

    for idx, stmt in enumerate(statements, start=1):
        sid = stmt.get("Sid", f"Statement-{idx}")
        actions = stmt.get("Action", [])
        resources = stmt.get("Resource", [])

        if isinstance(actions, str):
            actions = [actions]
        if isinstance(resources, str):
            resources = [resources]

        if any(a == "*" or a.endswith(":*") for a in actions):
            warnings.append(f"[{sid}] Broad wildcard detected in Action: {actions}")
        if "*" in resources:
            warnings.append(f"[{sid}] Wildcard '*' detected in Resource. Verify if resource-level scoping is possible.")

    return warnings


def fetch_rag_context(request: str) -> str:
    """Query local ChromaDB for matching internal InfoSec IAM guardrails."""
    try:
        rag = RAGEngine()
        hits = rag.search(f"AWS IAM InfoSec guardrail policy for: {request}", top_k=2)
        if hits:
            print("[📚] Retrieved matching InfoSec guardrails from ChromaDB.")
        return hits
    except Exception as e:
        print(f"[⚠️] RAG lookup skipped ({e})")
        return ""


def generate_iam_policy(
    request: str, provider: str = None, output_file: str = None, use_rag: bool = True
):
    guardrails = fetch_rag_context(request) if use_rag else ""

    prompt_parts = []
    if guardrails:
        prompt_parts.append(f"=== INTERNAL INFOSEC GUARDRAILS ===\n{guardrails}\n")
    prompt_parts.append(
        f"Create a least-privilege AWS IAM policy JSON for: {request}\n"
        "Remember: output ONLY raw, valid JSON."
    )

    client = LLMClient(provider=provider, role="specialist")
    print(f"\n[🔐] Generating IAM Policy | Provider: {client.provider} | Model: {client.model}")

    raw_output = client.generate(
        prompt="\n".join(prompt_parts),
        system_prompt=SYSTEM_PROMPT,
        temperature=0.0,
    )

    cleaned = clean_json_response(raw_output)

    try:
        policy_dict = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"\n[❌] Model returned invalid JSON: {e}\nRaw output:\n{raw_output}")
        sys.exit(1)

    formatted_json = json.dumps(policy_dict, indent=2)
    print("\n--- Generated AWS IAM Policy ---")
    print(formatted_json)
    print("--------------------------------")

    warnings = security_lint(policy_dict)
    if warnings:
        print("\n[⚠️] Security Linter Warnings:")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("\n[✅] Security Linter: Passed (no broad wildcards detected).")

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(formatted_json + "\n")
        print(f"[💾] Policy saved to: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Least-Privilege AWS IAM Policy Generator")
    parser.add_argument("request", nargs="?", help="Plain-English IAM permission request")
    parser.add_argument("--provider", choices=["ollama", "bedrock"], default=None, help="Override LLM provider")
    parser.add_argument("--output", "-o", default=None, help="Save generated JSON policy to a file")
    parser.add_argument("--no-rag", action="store_true", help="Disable local ChromaDB InfoSec guardrail lookup")
    args = parser.parse_args()

    user_request = args.request or input("Describe the AWS permissions you need:\n> ").strip()
    if not user_request:
        print("Error: Permission request cannot be empty.")
        sys.exit(1)

    generate_iam_policy(
        user_request,
        provider=args.provider,
        output_file=args.output,
        use_rag=not args.no_rag,
    )
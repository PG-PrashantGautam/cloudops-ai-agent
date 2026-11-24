import json
import subprocess
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

# Ensure root packages and numbered project folders are importable
ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "projects" / "01_iam_generator"))

from core.rag_engine import RAGEngine
from iam_generator import security_lint

# Initialize MCP Server (SDK v2.x)
mcp = MCPServer("PG-AI CloudOps")


@mcp.tool()
def search_cloudops_runbooks(query: str, top_k: int = 2) -> str:
    """Search the local ChromaDB vector database for internal EKS, AWS, and InfoSec runbooks."""
    try:
        hits = RAGEngine().search(query, top_k=top_k)
        return hits or "No matching internal runbooks found."
    except Exception as e:
        return f"RAG search error: {e}"


@mcp.tool()
def inspect_eks_pod(namespace: str, pod_name: str, mock: bool = True) -> str:
    """Read-only: Inspect a Kubernetes/EKS pod's status and recent error logs."""
    if mock:
        return (
            f"Resource: pod/{pod_name} (Namespace: {namespace})\n"
            "Status: CrashLoopBackOff (Exit Code 1, Restarts: 6)\n"
            "Logs: level=error msg='Unable to parse /etc/promtail/promtail.yaml: "
            "yaml: unmarshal errors: line 42: key \"action\" already set in map'"
        )

    res = subprocess.run(
        ["kubectl", "describe", "pod", pod_name, "-n", namespace],
        capture_output=True,
        text=True,
    )
    output = res.stdout.strip() or res.stderr.strip()
    return output[:3500]


@mcp.tool()
def lint_iam_policy(policy_json: str) -> str:
    """Validate an AWS IAM Policy JSON string against least-privilege InfoSec rules."""
    try:
        policy_dict = json.loads(policy_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    warnings = security_lint(policy_dict)
    if not warnings:
        return "PASSED: No broad wildcards or structural IAM issues detected."
    return "WARNINGS FOUND:\n" + "\n".join(f"- {w}" for w in warnings)


if __name__ == "__main__":
    # Runs over stdio for Kiro CLI, VS Code, Claude Desktop, and MCP clients
    mcp.run(transport="stdio")
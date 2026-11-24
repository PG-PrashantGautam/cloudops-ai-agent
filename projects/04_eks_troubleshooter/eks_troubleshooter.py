import argparse
import json
import subprocess
import sys
from pathlib import Path

# Allow importing from the root 'core' package regardless of where the script is run
ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from core.llm_client import LLMClient
from core.rag_engine import RAGEngine

SYSTEM_PROMPT = """You are a Senior Kubernetes & Amazon EKS Site Reliability Engineer.
Analyze the provided live `kubectl` diagnostics (Status, Describe output, Namespace Warnings, Logs, or Endpoints) and deliver a sharp, actionable troubleshooting report.

If INTERNAL RUNBOOKS / SOPs are provided and match the issue, prioritize the company-approved fix and exact commands from the runbook.

STRUCTURE YOUR RESPONSE AS:
1. **Root Cause:** Exact technical reason for the failure (cite specific exit codes, events, or log lines).
2. **Fix Command:** Exact `kubectl` command(s) or YAML snippet required to resolve the issue.
3. **Verification:** Command to confirm the resource is healthy after applying the fix.

Keep the output strictly technical and concise. Do not explain basic Kubernetes concepts.
"""

MOCK_K8S_DATA = """
Resource: pod/promtail-klx8l (Namespace: observability)
Detected Status: CrashLoopBackOff

--- Describe Output ---
Name:         promtail-klx8l
Namespace:    observability
Status:       Running
Containers:
  promtail:
    Image:          grafana/promtail:2.9.3
    State:          Waiting
      Reason:       CrashLoopBackOff
    Last State:     Terminated
      Reason:       Error
      Exit Code:    1
    Restart Count:  6
Events:
  Type     Reason     Age                From     Message
  ----     ------     ----               ----     -------
  Warning  BackOff    2m (x24 over 7m)   kubelet  Back-off restarting failed container promtail in pod promtail-klx8l_observability

--- Recent Logs ---
level=error ts=2026-11-20T10:15:22.419Z caller=main.go:75 msg="error creating promtail" error="Unable to parse config: /etc/promtail/promtail.yaml: yaml: unmarshal errors:\n  line 42: key \"action\" already set in map"
""".strip()


def run_kubectl(args: list[str]) -> tuple[int, str, str]:
    """Run a read-only kubectl command and return (returncode, stdout, stderr)."""
    res = subprocess.run(["kubectl"] + args, capture_output=True, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def resolve_pod_name(namespace: str, partial_name: str) -> str:
    """Resolve a partial pod name (e.g., 'promtail') to an exact pod name in the namespace."""
    rc, out, _ = run_kubectl([
        "get", "pods", "-n", namespace,
        "--no-headers", "-o", "custom-columns=:metadata.name",
    ])
    if rc == 0 and out:
        all_pods = out.splitlines()
        if partial_name in all_pods:
            return partial_name
        matched = [p for p in all_pods if partial_name in p]
        if matched:
            print(f"[💡] Fuzzy matched '{partial_name}' -> '{matched[0]}'")
            return matched[0]
    return partial_name


def get_pod_status(namespace: str, pod_name: str) -> str:
    """Detect the specific pod/container state (e.g., Pending, CrashLoopBackOff, OOMKilled, Running)."""
    rc, out, _ = run_kubectl(["get", "pod", pod_name, "-n", namespace, "-o", "json"])
    if rc != 0 or not out:
        return "Unknown"

    try:
        pod = json.loads(out)
        phase = pod.get("status", {}).get("phase", "Unknown")
        for cs in pod.get("status", {}).get("containerStatuses", []):
            waiting_reason = cs.get("state", {}).get("waiting", {}).get("reason")
            terminated_reason = cs.get("lastState", {}).get("terminated", {}).get("reason")
            if waiting_reason:
                return waiting_reason
            if terminated_reason == "OOMKilled":
                return "OOMKilled"
        return phase
    except json.JSONDecodeError:
        return "Unknown"


def get_namespace_warnings(namespace: str) -> str:
    """Fetch the last 10 Warning events in the namespace."""
    rc, out, _ = run_kubectl([
        "get", "events", "-n", namespace,
        "--field-selector=type=Warning",
        "--sort-by=.lastTimestamp",
    ])
    if rc == 0 and out:
        lines = out.splitlines()
        return "\n".join(lines[-10:]) if len(lines) > 1 else "No recent warnings."
    return "No recent warnings."


def gather_cluster_data(namespace: str, res_type: str, res_name: str) -> str:
    """Conditionally gather kubectl diagnostics based on resource type and pod status."""
    is_pod = res_type in ("pod", "pods", "po")
    if is_pod:
        res_name = resolve_pod_name(namespace, res_name)

    print(f"[🔍] Scanning {res_type}/{res_name} in namespace '{namespace}'...")
    context = f"Resource: {res_type}/{res_name} (Namespace: {namespace})\n"

    # 1. Always fetch Describe (trimmed to protect 3B model context window)
    print("[📋] Fetching resource configuration and events...")
    rc, desc_out, desc_err = run_kubectl(["describe", res_type, res_name, "-n", namespace])
    if rc != 0:
        print(f"[❌] kubectl describe failed:\n{desc_err}")
        sys.exit(1)
    if len(desc_out) > 4000:
        desc_out = desc_out[:1800] + "\n...[truncated]...\n" + desc_out[-2000:]
    context += f"\n--- Describe Output ---\n{desc_out}\n"

    # 2. Always fetch recent namespace warnings
    warnings = get_namespace_warnings(namespace)
    context += f"\n--- Namespace Warnings ---\n{warnings}\n"

    # 3. Conditional Branching for Pods
    if is_pod:
        status = get_pod_status(namespace, res_name)
        print(f"[🚦] Detected Pod Status: {status}")
        context += f"\nDetected Status: {status}\n"

        if status == "Pending":
            print("[🖥️] Pod is Pending — skipping logs, checking node capacity...")
            _, nodes_out, _ = run_kubectl(["get", "nodes", "-o", "wide"])
            context += f"\n--- Cluster Nodes ---\n{nodes_out or 'Unable to fetch nodes.'}\n"

        elif status in ("CrashLoopBackOff", "Error", "OOMKilled", "CreateContainerConfigError"):
            print("[📜] Crash detected — fetching previous and current container logs...")
            rc_prev, prev_logs, _ = run_kubectl(["logs", res_name, "-n", namespace, "--all-containers", "--previous", "--tail=40"])
            if rc_prev == 0 and prev_logs:
                context += f"\n--- Previous Container Logs ---\n{prev_logs}\n"
            rc_curr, curr_logs, _ = run_kubectl(["logs", res_name, "-n", namespace, "--all-containers", "--tail=30"])
            if rc_curr == 0 and curr_logs:
                context += f"\n--- Current Container Logs ---\n{curr_logs}\n"

        else:
            print("[📜] Pod is Running — fetching recent logs and namespace services/endpoints...")
            _, curr_logs, _ = run_kubectl(["logs", res_name, "-n", namespace, "--all-containers", "--tail=40"])
            context += f"\n--- Recent Logs ---\n{curr_logs or '(No logs available)'}\n"
            _, svc_out, _ = run_kubectl(["get", "svc,endpoints", "-n", namespace])
            context += f"\n--- Namespace Services & Endpoints ---\n{svc_out or '(None found)'}\n"

    # 4. Service-specific check
    elif res_type in ("svc", "service", "services"):
        print("[🌐] Fetching Service endpoints...")
        _, ep_out, _ = run_kubectl(["get", "endpoints", res_name, "-n", namespace])
        context += f"\n--- Endpoints ---\n{ep_out or '(No endpoints found)'}\n"

    return context


def fetch_rag_context(cluster_data: str) -> str:
    """Query local ChromaDB for matching internal runbooks using the latest error context."""
    try:
        rag = RAGEngine()
        # Focus the embedding query on the resource header + recent logs/events
        rag_query = cluster_data[:300] + "\n" + cluster_data[-1000:]
        hits = rag.search(rag_query, top_k=2)
        if hits:
            print("[📚] Retrieved matching internal runbooks from ChromaDB.")
        return hits
    except Exception as e:
        print(f"[⚠️] RAG lookup skipped ({e})")
        return ""


def diagnose_cluster(cluster_data: str, provider: str = None, use_rag: bool = True):
    """Send collected Kubernetes diagnostics (+ optional RAG runbooks) to the LLM."""
    runbook_context = fetch_rag_context(cluster_data) if use_rag else ""

    prompt_parts = []
    if runbook_context:
        prompt_parts.append(f"=== INTERNAL RUNBOOKS / SOPs ===\n{runbook_context}\n")
    prompt_parts.append(f"=== LIVE KUBERNETES / EKS DIAGNOSTICS ===\n{cluster_data}")

    full_prompt = "\n".join(prompt_parts)

    client = LLMClient(provider=provider, role="specialist")
    print(f"[🧠] Diagnosing cluster data | Provider: {client.provider} | Model: {client.model}")

    report = client.generate(
        prompt=f"Diagnose this Kubernetes/EKS resource:\n\n{full_prompt}",
        system_prompt=SYSTEM_PROMPT,
        temperature=0.1,
    )

    print("\n--- ☸️ EKS AI Diagnostics ---")
    print(report)
    print("-----------------------------\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI-Powered Kubernetes / Amazon EKS Troubleshooter")
    parser.add_argument("--namespace", "-n", default="default", help="Kubernetes namespace (default: default)")
    parser.add_argument("--type", "-t", dest="res_type", default="pod", help="Resource type: pod, svc, deployment (default: pod)")
    parser.add_argument("--name", help="Resource name (supports partial fuzzy matching for pods)")
    parser.add_argument("--mock", action="store_true", help="Use built-in mock CrashLoopBackOff diagnostics")
    parser.add_argument("--no-rag", action="store_true", help="Disable local ChromaDB runbook lookup")
    parser.add_argument("--provider", choices=["ollama", "bedrock"], default=None, help="Override LLM provider")
    args = parser.parse_args()

    if args.mock:
        print("[ℹ️] Running in MOCK mode with sample CrashLoopBackOff pod diagnostics...")
        raw_data = MOCK_K8S_DATA
    else:
        res_name = args.name or input(f"Enter {args.res_type} name in '{args.namespace}': ").strip()
        if not res_name:
            print("Error: Provide --name or use --mock.")
            sys.exit(1)
        raw_data = gather_cluster_data(args.namespace, args.res_type.lower(), res_name)

    diagnose_cluster(raw_data, provider=args.provider, use_rag=not args.no_rag)
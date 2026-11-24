import argparse
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command, interrupt

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(dotenv_path=ROOT_DIR / ".env")

from core.rag_engine import RAGEngine

MOCK_MODE = True


# --- 1. Define Tools (Read-Only vs. Mutating with HITL) ---

@tool
def inspect_pod(namespace: str, pod_name: str) -> str:
    """Read-only: Fetch pod status and recent error logs for a Kubernetes pod."""
    print(f"[🔧 Tool] inspect_pod(namespace='{namespace}', pod_name='{pod_name}')")
    if MOCK_MODE:
        return (
            f"Pod: {pod_name} (Namespace: {namespace})\n"
            "Status: CrashLoopBackOff (Exit Code 1, Restarts: 6)\n"
            "Logs: level=error msg='Unable to parse /etc/promtail/promtail.yaml: "
            "yaml: unmarshal errors: line 42: key \"action\" already set in map'"
        )
    res = subprocess.run(
        ["kubectl", "describe", "pod", pod_name, "-n", namespace],
        capture_output=True,
        text=True,
    )
    return (res.stdout or res.stderr)[:3000]


@tool
def search_runbooks(query: str) -> str:
    """Read-only: Search local ChromaDB internal CloudOps runbooks for approved SOPs."""
    print(f"[🔧 Tool] search_runbooks(query='{query[:60]}...')")
    try:
        hits = RAGEngine().search(query, top_k=2)
        return hits or "No matching internal runbook found."
    except Exception as e:
        return f"RAG lookup failed: {e}"


@tool
def restart_workload(namespace: str, workload_type: str, workload_name: str) -> str:
    """MUTATING ACTION: Restart a Kubernetes Deployment or DaemonSet. Requires human approval."""
    cmd_str = f"kubectl rollout restart {workload_type}/{workload_name} -n {namespace}"
    print(f"[🔧 Tool] restart_workload -> requesting approval for: {cmd_str}")

    # Pause graph execution and surface the exact command to the human operator
    decision = interrupt({
        "action": "restart_workload",
        "command": cmd_str,
        "message": f"Approve executing: `{cmd_str}`? (yes/no)",
    })

    if str(decision).strip().lower() not in ("y", "yes", "approve"):
        return f"[REJECTED BY HUMAN] Cancelled command: {cmd_str}"

    if MOCK_MODE:
        return f"[MOCK EXECUTED] {cmd_str} -> {workload_type}.apps/{workload_name} restarted"

    res = subprocess.run(cmd_str.split(), capture_output=True, text=True)
    return res.stdout.strip() or res.stderr.strip()


TOOLS = [inspect_pod, search_runbooks, restart_workload]


# --- 2. Define Graph State & Nodes ---

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def build_agent(model_override: str = None):
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model_name = model_override or os.getenv("OLLAMA_ROUTER_MODEL", "llama3.2")

    llm = ChatOllama(
        model=model_name,
        base_url=ollama_url,
        temperature=0.0,
    ).bind_tools(TOOLS)

    system_msg = SystemMessage(
        content=(
            "You are PG-AI v3.0, an autonomous CloudOps SRE agent.\n"
            "1. Always inspect the resource and search internal runbooks before proposing a fix.\n"
            "2. If a workload restart is needed per the runbook, call `restart_workload`.\n"
            "3. Keep final answers concise and technical.\n"
            "4. If a human rejects a mutating tool call, explicitly state that the action was "
            "cancelled and do not claim you will execute it."
        )
    )

    def agent_node(state: AgentState):
        response = llm.invoke([system_msg] + state["messages"])
        return {"messages": [response]}

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(TOOLS))

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    # Checkpointer is mandatory for interrupt() / Command(resume=...)
    return builder.compile(checkpointer=InMemorySaver()), model_name


# --- 3. Interactive CLI Runner with HITL Resume Loop ---

def run_agent(prompt: str, model_override: str = None):
    graph, active_model = build_agent(model_override=model_override)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    print(f"\n[🤖] PG-AI v3.0 (LangGraph ReAct | Model: {active_model} | Mock={MOCK_MODE})")
    result = graph.invoke({"messages": [HumanMessage(content=prompt)]}, config=config)

    # Loop while the graph is paused on a Human-in-the-Loop interrupt()
    while "__interrupt__" in result and result["__interrupt__"]:
        payload = result["__interrupt__"][0].value
        print("\n[🛑 HUMAN APPROVAL REQUIRED]")
        print(f"    Command: {payload.get('command')}")
        user_input = input("    Approve execution? (yes/no): ").strip()

        # Resume the exact paused thread with the human's decision
        result = graph.invoke(Command(resume=user_input), config=config)

    print("\n--- ✅ Final Agent Response ---")
    print(result["messages"][-1].content)
    print("-------------------------------\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PG-AI v3.0: Autonomous LangGraph Agent with HITL")
    parser.add_argument("query", nargs="?", help="CloudOps task for the autonomous agent")
    parser.add_argument("--live", action="store_true", help="Run real kubectl commands instead of mock mode")
    parser.add_argument("--model", default=None, help="Override Ollama model (e.g., llama3.2, qwen3.5:4b)")
    args = parser.parse_args()

    MOCK_MODE = not args.live
    user_query = args.query or (
        "Check promtail pod in observability namespace, consult our runbooks, "
        "and restart the promtail daemonset if appropriate."
    )
    run_agent(user_query, model_override=args.model)
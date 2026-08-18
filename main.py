"""CLI runner for the skeleton. Set AUTO_APPROVE=1 to skip the HITL interrupt."""
import os, json
os.environ.setdefault("AUTO_APPROVE", "1")

from graph.workflow import build_graph
from graph.state import new_state
from agents.base_agent import add_usage, estimate_cost  # noqa: F401


def run(query: str, files=None):
    graph = build_graph()
    state = new_state(query, uploaded_files=files or [])
    cfg = {"configurable": {"thread_id": state["run_id"]}}
    final = graph.invoke(state, cfg)
    return final


if __name__ == "__main__":
    files = [{"path": "data/churn.csv", "type": "csv", "name": "churn.csv"}]
    final = run("What factors are associated with customer churn?", files=files)
    print("=" * 60)
    print("STATUS:", final["status"], "| run:", final["run_id"])
    print("COMPLETED:", final["completed_agents"])
    print("-" * 60, "\nCOMMS LOG:")
    for m in final["messages"]:
        print(f"  {m['from_agent']:>10} -> {m['to_agent']:<10} [{m['type']}] {m['content']}")
    print("-" * 60, "\nREPORT:\n")
    print(final["final_report"])

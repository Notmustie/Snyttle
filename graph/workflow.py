"""Assemble the LangGraph workflow — the walking skeleton.

Topology: Supervisor is the hub. Planner -> human approval -> back to Supervisor,
which dynamically dispatches specialists, then Critic (bounded revision loop),
then Writer -> END. Runs end-to-end with all nodes stubbed and no API keys.
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from graph.state import ResearchState, comms, log, Status
from agents.supervisor import supervisor_node, route_next
from agents.planner import planner_node
from agents.researcher import researcher_node
from agents.knowledge import knowledge_node
from agents.data_analyst import data_analyst_node
from agents.critic import critic_node
from agents.writer import writer_node
import config

try:
    from langgraph.types import interrupt  # LangGraph >= 0.2.x
except Exception:  # noqa: BLE001
    interrupt = None


def human_approval_node(state):
    """The single HITL checkpoint: approve/modify/reject the plan.

    In AUTO_APPROVE mode (CLI/tests) it records an automatic approval. In the
    Streamlit app, `interrupt()` pauses the graph; the UI resumes with a decision.
    """
    rid = state["run_id"]
    if config.AUTO_APPROVE or interrupt is None:
        decision = {"checkpoint": "plan_approval", "decision": "approve", "auto": True}
    else:
        payload = interrupt({"checkpoint": "plan_approval",
                             "plan": state.get("research_plan")})
        decision = {"checkpoint": "plan_approval",
                    "decision": payload.get("decision", "approve"),
                    "edited_plan": payload.get("edited_plan")}
        if decision.get("edited_plan"):
            state["research_plan"] = decision["edited_plan"]
    return {
        "human_decisions": [decision],
        "status": Status.RESEARCHING,
        "messages": [comms("human", "supervisor", "system",
                           f"Plan {decision['decision']}", rid)],
        "execution_logs": [log(rid, "human", "plan approval",
                              status=decision["decision"])],
    }


def revise_node(state):
    """Increment the revision counter so specialists re-run for a new cycle."""
    rid = state["run_id"]
    rev = state.get("revision_count", 0) + 1
    return {
        "revision_count": rev,
        "status": Status.REVISING,
        "messages": [comms("supervisor", "research", "feedback",
                           f"Revision {rev}: addressing critic errors", rid)],
        "execution_logs": [log(rid, "supervisor", f"revision {rev}")],
    }


def build_graph(checkpointer=None):
    g = StateGraph(ResearchState)

    g.add_node("supervisor", supervisor_node)
    g.add_node("planner", planner_node)
    g.add_node("human_approval", human_approval_node)
    g.add_node("research", researcher_node)
    g.add_node("knowledge", knowledge_node)
    g.add_node("data_analyst", data_analyst_node)
    g.add_node("critic", critic_node)
    g.add_node("revise", revise_node)
    g.add_node("writer", writer_node)

    g.add_edge(START, "supervisor")

    # Supervisor dispatches based on route_next().
    g.add_conditional_edges("supervisor", route_next, {
        "planner": "planner",
        "research": "research",
        "knowledge": "knowledge",
        "data_analyst": "data_analyst",
        "critic": "critic",
        "revise": "revise",
        "writer": "writer",
    })

    # Planner passes through the human checkpoint, then back to the hub.
    g.add_edge("planner", "human_approval")
    g.add_edge("human_approval", "supervisor")

    # Every specialist returns to the hub.
    for n in ("research", "knowledge", "data_analyst", "critic", "revise"):
        g.add_edge(n, "supervisor")

    g.add_edge("writer", END)

    return g.compile(checkpointer=checkpointer or MemorySaver())


# Module-level compiled graph for the UI / viz.
graph = build_graph()

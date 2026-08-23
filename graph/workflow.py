"""Assemble the LangGraph workflow.

Topology: Supervisor is the hub. Planner -> human approval -> back to Supervisor,
which dynamically dispatches specialists, then Critic (bounded revision loop),
then Writer -> END.
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

from graph.state import ResearchState, comms, log, Status
from memory.database import persist_run

import config

try:
    from langgraph.types import interrupt  # LangGraph >= 0.2.x
except Exception:  # noqa: BLE001
    interrupt = None


def human_approval_node(state):
    """The single HITL checkpoint: approve/modify/reject the plan.

    In AUTO_APPROVE mode (CLI/tests) it records an automatic approval. In the
    Streamlit app, `interrupt()` pauses the graph; the UI resumes with a decision
    payload: {"decision": "approve"|"edit"|"reject", "edited_plan": {...}?}.
    """
    rid = state["run_id"]
    updates = {"status": Status.RESEARCHING}

    if config.AUTO_APPROVE or interrupt is None:
        decision = {"checkpoint": "plan_approval", "decision": "approve", "auto": True}
    else:
        payload = interrupt({"checkpoint": "plan_approval",
                             "plan": state.get("research_plan")}) or {}
        decision = {"checkpoint": "plan_approval",
                    "decision": payload.get("decision", "approve"),
                    "edited_plan": payload.get("edited_plan")}
        if decision.get("edited_plan"):
            updates["research_plan"] = decision["edited_plan"]  # persist the edit
        if decision["decision"] == "reject":
            updates["status"] = Status.ERROR

    updates.update({
        "human_decisions": [decision],
        "messages": [comms("human", "supervisor", "system",
                           f"Plan {decision['decision']}", rid)],
        "execution_logs": [log(rid, "human", "plan approval",
                              status=decision["decision"])],
    })
    return updates


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

def persist_node(state):
    """Terminal node: write the completed run to SQLite. Best-effort."""
    rid = state["run_id"]
    from agents.base_agent import estimate_cost
    cost = estimate_cost(state.get("token_usage", {}))
    ok = persist_run({**state, "estimated_cost": cost})
    return {
        "estimated_cost": cost,
        "execution_logs": [log(rid, "system", "run persisted to sqlite",
                               status="ok" if ok else "degraded", tool="sqlite")],
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
    g.add_node("persist", persist_node)

    g.add_edge(START, "supervisor")

    g.add_conditional_edges("supervisor", route_next, {
        "planner": "planner",
        "research": "research",
        "knowledge": "knowledge",
        "data_analyst": "data_analyst",
        "critic": "critic",
        "revise": "revise",
        "writer": "writer",
        "stop": END,
    })

    g.add_edge("planner", "human_approval")
    g.add_edge("human_approval", "supervisor")

    for n in ("research", "knowledge", "data_analyst", "critic", "revise"):
        g.add_edge(n, "supervisor")

    g.add_edge("writer", "persist")
    g.add_edge("persist", END)

    return g.compile(checkpointer=checkpointer or MemorySaver())


graph = build_graph()
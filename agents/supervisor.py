"""Supervisor: the central router. All routing decisions live here.

It is both a node (initializes/updates control state) and a router function
(decides the next hop). Specialists always return to the Supervisor.
"""
from graph.state import comms, log, Status
import config


def supervisor_node(state):
    """Set route_flags after planning; advance status. Pure control, no LLM."""
    rid = state["run_id"]
    updates = {"current_agent": "supervisor",
               "execution_logs": [log(rid, "supervisor", "route")]}

    # First entry: nothing planned yet -> go plan.
    if not state.get("research_plan"):
        updates["status"] = Status.PLANNING
        return updates

    # Compute routing flags once, from the plan + uploaded files.
    if not state.get("route_flags"):
        files = state.get("uploaded_files", [])
        has_pdf = any(f.get("type") == "pdf" for f in files)
        has_csv = any(f.get("type") == "csv" for f in files)
        # Skeleton default: a research question needs web + academic evidence.
        flags = {"need_web": True, "need_academic": True,
                 "need_rag": has_pdf, "need_data": has_csv}
        updates["route_flags"] = flags
        updates["messages"] = [
            comms("supervisor", "planner", "delegation",
                  f"Plan approved; routing flags {flags}", rid)]
    return updates


def route_next(state) -> str:
    """Router: return the name of the next node to run.

    Completions are stamped `agent@<revision_count>`, so a revision bump makes
    every check see the specialist as not-yet-done for the new cycle and re-runs it.
    """
    if not state.get("research_plan"):
        return "planner"

    flags = state.get("route_flags", {})
    rev = state.get("revision_count", 0)
    done = set(state.get("completed_agents", []))

    def is_done(agent: str) -> bool:
        return f"{agent}@{rev}" in done

    if (flags.get("need_web") or flags.get("need_academic")) and not is_done("research"):
        return "research"
    if flags.get("need_rag") and not is_done("knowledge"):
        return "knowledge"
    if flags.get("need_data") and not is_done("data_analyst"):
        return "data_analyst"

    # All flagged specialists done this cycle -> critique.
    if not is_done("critic"):
        return "critic"

    # Critic ran this cycle: honor a bounded revision request.
    wants_revision = any(f.get("severity") == "ERROR"
                         for f in state.get("critic_feedback", []))
    if wants_revision and rev < config.MAX_REVISIONS:
        return "revise"

    return "writer"

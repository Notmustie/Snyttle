import json
from graph.state import comms, log, Status
from agents.base_agent import call_claude, add_usage, resolve_effort
import config

PLANNER_SYSTEM = (
    "You are the Research Planner in a multi-agent research system. Decompose the "
    "user's request into an executable plan. Return ONLY a JSON object with keys: "
    "objectives (list of strings), subtasks (list of strings), evidence_needs "
    "(list of strings), success_criteria (list of strings). "
    "No prose, no markdown fences."
)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def _fallback_plan(query: str) -> dict:
    return {
        "objectives": [f"Answer: {query}"],
        "subtasks": ["gather web + academic evidence", "analyze any dataset", "critique", "report"],
        "evidence_needs": ["recent web sources", "academic literature"],
        "success_criteria": ["claims supported by cited sources", "methodology sound"],
    }


def planner_node(state):
    rid = state["run_id"]
    eff = resolve_effort(state, "planner")
    files = [f.get("name") for f in state.get("uploaded_files", [])]
    user = (f"Research question: {state['user_query']}\n"
            f"Uploaded files: {files}\n"
            f"Preferences: {state.get('preferences', {})}\n"
            "Produce the plan as JSON.")
    try:
        text, itok, otok = call_claude(PLANNER_SYSTEM, user,
                                       model=config.PLANNER_MODEL, effort=eff)
        plan = json.loads(_strip_fences(text))
        token_usage = add_usage(state.get("token_usage", {}), "planner", itok, otok)
        logs = [log(rid, "planner", "plan drafted (llm)", tool="claude")]
    except Exception as e:  # noqa: BLE001 — any failure => safe fallback
        plan = _fallback_plan(state["user_query"])
        token_usage = state.get("token_usage", {})
        logs = [log(rid, "planner", "plan fallback (stub)", status="degraded", error=str(e))]

    return {
        "current_agent": "planner",
        "research_plan": plan,
        "completed_agents": ["planner"],
        "status": Status.AWAITING_PLAN_APPROVAL,
        "token_usage": token_usage,
        "messages": [comms("planner", "supervisor", "result",
                           f"Draft plan: {len(plan.get('subtasks', []))} subtasks", rid)],
        "execution_logs": logs,
    }
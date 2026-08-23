"""Critic: quality gates on evidence, methodology, and internal consistency.

DAY 7: reviews all gathered evidence (web, academic, RAG, analysis) against the
research plan. Can emit ERROR-level feedback to trigger a revision loop (capped
at 2 retries). Otherwise passes with INFO-level observations.
"""
from __future__ import annotations
import json
from graph.state import comms, log, feedback
from agents.base_agent import call_claude, add_usage, resolve_effort, resolve_model
import config

CRITIC_SYSTEM = (
    "You critically review research evidence. Given a research question, plan, "
    "and all gathered evidence, identify gaps, conflicts, methodological issues, "
    "or unsupported claims. Return ONLY a JSON array of feedback objects: "
    "{\"severity\": \"INFO\"|\"WARNING\"|\"ERROR\", \"target_agent\": str, "
    "\"issue\": str, \"suggestion\": str}. Severity: ERROR if something must be "
    "fixed before reporting, WARNING if noteworthy but acceptable, INFO if minor. "
    "Return an empty array if quality is good. No prose, no markdown fences."
)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def critic_node(state):
    rid = state["run_id"]
    rev = state.get("revision_count", 0)
    eff = resolve_effort(state, "critic")
    model = resolve_model(state, "critic")
    logs = []
    token_usage = state.get("token_usage", {})

    # Assemble what's been gathered so far
    plan = state.get("research_plan") or {}
    web = state.get("research_results", [])
    lit = state.get("literature_results", [])
    rag = state.get("retrieved_context", [])
    ana = state.get("analysis_results") or {}

    payload = {
        "question": state["user_query"],
        "plan": {"objectives": plan.get("objectives", []),
                 "evidence_needs": plan.get("evidence_needs", [])},
        "evidence": {
            "web_claims": len(web),
            "academic_works": len(lit),
            "rag_passages": len(rag),
            "analysis_findings": len(ana.get("findings", [])),
        },
        "sample_claims": [w.get("claim", "")[:100] for w in web[:3]],
        "missing_columns": state.get("dataset_info", {}).get("missing", {}) if state.get("dataset_info") else {},
    }

    user = (f"Research question: {state['user_query']}\n\n"
            f"Evidence summary:\n{json.dumps(payload, indent=2)}\n\n"
            "Review for quality, conflicts, gaps, and methodology issues.")

    try:
        text, itok, otok = call_claude(CRITIC_SYSTEM, user, model=model, effort=eff)
        fb_list = json.loads(_strip_fences(text))
        if not isinstance(fb_list, list):
            fb_list = []
        token_usage = add_usage(token_usage, "critic", itok, otok)
        logs.append(log(rid, "critic", f"reviewed: {len(fb_list)} feedback items", tool="claude"))
    except Exception as e:  # noqa: BLE001 — fallback: INFO pass if review fails
        fb_list = [feedback("INFO", "critic", "Quality review unavailable", "Proceed with caution")]
        logs.append(log(rid, "critic", "review fallback", status="degraded", error=str(e)))

    errors = any(f.get("severity") == "ERROR" for f in fb_list)
    msg = f"Reviewed evidence: {len(fb_list)} feedback item(s)"
    if errors:
        msg += f" (includes {sum(1 for f in fb_list if f.get('severity')=='ERROR')} ERROR(s))"

    return {
        "current_agent": "critic",
        "completed_agents": [f"critic@{rev}"],
        "critic_feedback": fb_list,
        "token_usage": token_usage,
        "messages": [comms("critic", "supervisor", "result", msg, rid)],
        "execution_logs": logs,
    }
"""The shared ResearchState — the single object every agent reads and writes.

Append-only lists use operator.add reducers so concurrent/sequential writes
ACCUMULATE instead of overwriting. This is the detail that silently breaks
LangGraph builds if omitted.
"""
from __future__ import annotations
import operator
import uuid
from datetime import datetime, timezone
from typing import TypedDict, Annotated, Optional


# ---- Status values (locked enum) ----
class Status:
    INITIALIZING = "INITIALIZING"
    PLANNING = "PLANNING"
    AWAITING_PLAN_APPROVAL = "AWAITING_PLAN_APPROVAL"
    RESEARCHING = "RESEARCHING"
    ANALYZING = "ANALYZING"
    CRITIQUING = "CRITIQUING"
    REVISING = "REVISING"
    WRITING = "WRITING"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


class ResearchState(TypedDict, total=False):
    # ---- Input ----
    run_id: str
    user_query: str
    preferences: dict
    uploaded_files: list[dict]              # [{path, type: 'pdf'|'csv', name}]

    # ---- Planning ----
    research_plan: Optional[dict]           # {objectives, subtasks, evidence_needs, success_criteria}

    # ---- Routing / control ----
    route_flags: dict                       # {need_web, need_academic, need_rag, need_data}
    completed_agents: Annotated[list[str], operator.add]
    current_agent: str
    status: str

    # ---- Agent outputs ----
    research_results: Annotated[list[dict], operator.add]
    literature_results: Annotated[list[dict], operator.add]
    retrieved_context: Annotated[list[dict], operator.add]
    dataset_info: Optional[dict]
    analysis_results: Optional[dict]

    # ---- Critic ----
    critic_feedback: Annotated[list[dict], operator.add]
    revision_count: int

    # ---- HITL ----
    human_decisions: Annotated[list[dict], operator.add]

    # ---- Output ----
    final_report: Optional[str]

    # ---- Observability (UI panels read these) ----
    messages: Annotated[list[dict], operator.add]        # comms log
    execution_logs: Annotated[list[dict], operator.add]
    errors: Annotated[list[dict], operator.add]
    token_usage: dict
    estimated_cost: float


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_state(user_query: str, uploaded_files: list[dict] | None = None,
              preferences: dict | None = None) -> ResearchState:
    """Factory for a fresh run. current_agent/status set to initializing."""
    return ResearchState(
        run_id=str(uuid.uuid4())[:8],
        user_query=user_query,
        preferences=preferences or {},
        uploaded_files=uploaded_files or [],
        research_plan=None,
        route_flags={},
        completed_agents=[],
        current_agent="supervisor",
        status=Status.INITIALIZING,
        research_results=[],
        literature_results=[],
        retrieved_context=[],
        dataset_info=None,
        analysis_results=None,
        critic_feedback=[],
        revision_count=0,
        human_decisions=[],
        final_report=None,
        messages=[],
        execution_logs=[],
        errors=[],
        token_usage={},
        estimated_cost=0.0,
    )


# ---- Structured record builders (keep formats consistent everywhere) ----
def comms(from_agent: str, to_agent: str, msg_type: str, content: str, run_id: str) -> dict:
    """Communication panel reads this format verbatim."""
    return {"ts": _now(), "from_agent": from_agent, "to_agent": to_agent,
            "type": msg_type, "content": content, "run_id": run_id}


def log(run_id: str, agent: str, event: str, status: str = "ok",
        tool: str | None = None, duration: float | None = None,
        error: str | None = None) -> dict:
    return {"ts": _now(), "run_id": run_id, "agent": agent, "event": event,
            "status": status, "tool": tool, "duration": duration, "error": error}


def feedback(severity: str, target_agent: str, issue: str, suggestion: str) -> dict:
    return {"severity": severity, "target_agent": target_agent,
            "issue": issue, "suggestion": suggestion}

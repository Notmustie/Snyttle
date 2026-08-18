"""Planner: turns the query into objectives/subtasks/success criteria.

Skeleton = dummy plan. Real version: base_agent.call_claude with a planning prompt.
"""
from graph.state import comms, log, Status


def planner_node(state):
    rid = state["run_id"]
    plan = {
        "objectives": ["Understand the question", "Gather evidence", "Analyze", "Report"],
        "subtasks": ["research", "rag?", "data analysis?"],
        "evidence_needs": ["recent web sources", "academic literature"],
        "success_criteria": ["claims supported", "sources cited"],
    }
    return {
        "current_agent": "planner",
        "research_plan": plan,
        "completed_agents": ["planner"],
        "status": Status.AWAITING_PLAN_APPROVAL,
        "messages": [comms("planner", "supervisor", "result", "Draft plan ready", rid)],
        "execution_logs": [log(rid, "planner", "plan drafted")],
    }

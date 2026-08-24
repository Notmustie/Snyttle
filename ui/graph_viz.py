"""Builds a per-run-accurate Mermaid diagram of the workflow graph.

The stock `graph.get_graph().draw_mermaid_png()` renders the STATIC compiled
topology — same shape every run, no reflection of what actually happened.
This module hand-authors the same topology (kept in sync with
graph/workflow.py's build_graph()) and colors each node by what this
particular run did: done, currently paused, skipped, or not-yet-reached.
"""
from __future__ import annotations

# id -> (display label, mermaid shape template using {label})
NODE_SHAPES = {
    "start":           ("Start", "(({label}))"),
    "supervisor":      ("Supervisor", "[{label}]"),
    "planner":         ("Planner", "[{label}]"),
    "human_approval":  ("Plan Approval", "{{{{{label}}}}}"),
    "research":        ("Research", "[{label}]"),
    "knowledge":       ("Knowledge / RAG", "[{label}]"),
    "data_analyst":    ("Data Analyst", "[{label}]"),
    "critic":          ("Critic", "[{label}]"),
    "revise":          ("Revise", "[{label}]"),
    "writer":          ("Writer", "[{label}]"),
    "persist":         ("Persist", "[({label})]"),
    "finish":             ("End", "(({label}))"),
}

# Mirrors build_graph() in graph/workflow.py exactly.
EDGES = [
    ("start", "supervisor"),
    ("supervisor", "planner"), ("supervisor", "research"),
    ("supervisor", "knowledge"), ("supervisor", "data_analyst"),
    ("supervisor", "critic"), ("supervisor", "revise"),
    ("supervisor", "writer"), ("supervisor", "finish"),
    ("planner", "human_approval"), ("human_approval", "supervisor"),
    ("research", "supervisor"), ("knowledge", "supervisor"),
    ("data_analyst", "supervisor"), ("critic", "supervisor"),
    ("revise", "supervisor"),
    ("writer", "persist"), ("persist", "finish"),
]

_STYLE = {
    "done":    "fill:#DCEFD3,stroke:#4C7A3E,color:#2B2118,stroke-width:1.5px",
    "current": "fill:#F5E8CE,stroke:#8B6F47,color:#2B2118,stroke-width:2.5px",
    "skipped": "fill:#F4F1EA,stroke:#C9B79C,color:#A89A87,stroke-dasharray:4 3",
    "hub":     "fill:#EFE6D8,stroke:#8B6F47,color:#2B2118,stroke-width:2px",
    "pending": "fill:#FDFBF7,stroke:#C9B79C,color:#6B5D4F",
}


def _base_names(completed: list[str]) -> set[str]:
    """completed_agents entries are 'agent' or 'agent@rev' — strip the stamp."""
    return {a.split("@")[0] for a in completed}


def node_statuses(final: dict | None, pending: dict | None) -> dict[str, str]:
    """One status per node: done | current | skipped | hub | pending."""
    if not final and not pending:
        return {n: "pending" for n in NODE_SHAPES}

    state = final or {}
    done = _base_names(state.get("completed_agents", []))
    run_finished = bool(final)
    status: dict[str, str] = {}

    status["start"] = "done"
    status["supervisor"] = "hub"  # the router runs every cycle; not tracked individually

    status["planner"] = "done" if "planner" in done else (
        "pending" if not run_finished else "skipped")

    if pending:
        status["human_approval"] = "current"
    else:
        status["human_approval"] = "done" if state.get("human_decisions") else (
            "skipped" if run_finished else "pending")

    for node in ("research", "knowledge", "data_analyst", "critic"):
        if node in done:
            status[node] = "done"
        else:
            status[node] = "skipped" if run_finished else "pending"

    status["revise"] = "done" if state.get("revision_count", 0) > 0 else (
        "skipped" if run_finished else "pending")

    status["writer"] = "done" if "writer" in done else (
        "skipped" if run_finished else "pending")

    # persist has no completed_agents entry — infer from terminal status.
    status["persist"] = "done" if state.get("status") == "COMPLETE" else (
        "skipped" if run_finished else "pending")

    status["finish"] = "done" if run_finished else "pending"

    return status


def build_run_mermaid(final: dict | None, pending: dict | None) -> str:
    """Hand-authored Mermaid text (kept 1:1 with build_graph()'s real topology),
    colored per-node for THIS run. Fed to draw_mermaid_png() for rasterizing —
    same renderer LangGraph's own diagram uses, no new dependency."""
    statuses = node_statuses(final, pending)
    lines = ["graph TD"]

    for node_id, (label, shape_tpl) in NODE_SHAPES.items():
        shape = shape_tpl.format(label=label)
        lines.append(f"    {node_id}{shape}")

    for src, dst in EDGES:
        lines.append(f"    {src} --> {dst}")

    for status_name, style in _STYLE.items():
        lines.append(f"    classDef {status_name} {style};")

    for node_id, status_name in statuses.items():
        lines.append(f"    class {node_id} {status_name};")

    return "\n".join(lines)
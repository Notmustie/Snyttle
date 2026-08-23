"""Writer: synthesize evidence into a structured, cited report.

DAY 7: the final node. Takes all validated evidence and produces a markdown
report organized by the plan's structure, with inline citations to sources.
"""
from __future__ import annotations
import json
from graph.state import comms, log, Status
from agents.base_agent import call_claude, add_usage,resolve_effort, resolve_model
import config

WRITER_SYSTEM = (
    "You write research reports. Given a research question, evidence (web claims, "
    "academic papers, document passages, data findings), and a success plan, "
    "synthesize into markdown. Structure: # Research Report, ## Summary, "
    "## Findings (one per major claim, each citing its source), ## References. "
    "Citations: use [source](#source-label) inline; list full sources at the end. "
    "Be concise, factual, and cite everything. Output ONLY markdown, no preamble."
)


def _citekey(source: dict | None, i: int) -> str:
    """Generate a citation key from a source dict."""
    if not source:
        return f"src{i}"
    if isinstance(source, dict):
        url = source.get("source_url") or source.get("url") or ""
        title = source.get("title", "")[:30]
        return f"src-{title.replace(' ', '-')[:20]}".lower()
    return f"src{i}"


def writer_node(state):
    rid = state["run_id"]
    logs = []
    token_usage = state.get("token_usage", {})
    eff = resolve_effort(state, "writer")
    model = resolve_model(state, "writer")

    # Assemble all evidence for the Writer
    plan = state.get("research_plan") or {}
    web = state.get("research_results", [])
    lit = state.get("literature_results", [])
    rag = state.get("retrieved_context", [])
    ana = state.get("analysis_results") or {}

    # Build a formatted evidence summary
    sources = []
    for i, w in enumerate(web):
        sources.append({
            "type": "web",
            "claim": w.get("claim", ""),
            "url": w.get("source_url", ""),
            "title": w.get("title", ""),
        })
    for i, p in enumerate(lit):
        sources.append({
            "type": "academic",
            "title": p.get("title", ""),
            "authors": ", ".join(p.get("authors", [])[:3]),
            "year": p.get("year"),
            "doi": p.get("doi", ""),
        })
    for i, p in enumerate(rag):
        sources.append({
            "type": "rag",
            "text": p.get("text", "")[:150],
            "source_id": p.get("source_id", ""),
            "doc_name": p.get("doc_name", ""),
        })
    findings_text = "\n".join(ana.get("findings", [])[:10]) if ana.get("findings") else ""

    payload = {
        "question": state["user_query"],
        "objectives": plan.get("objectives", [])[:5],
        "success_criteria": plan.get("success_criteria", [])[:3],
        "evidence_summary": {
            "web_sources": len(web),
            "academic_works": len(lit),
            "documents_retrieved": len(rag),
            "data_findings": len(ana.get("findings", [])) if ana else 0,
        },
        "sources_json": json.dumps(sources[:15], indent=2)[:2000],
        "analysis_output": findings_text[:500],
    }

    user = (f"Research question: {state['user_query']}\n\n"
            f"Evidence and sources:\n{json.dumps(payload, indent=2)}\n\n"
            "Write the report incorporating all evidence with citations.")

    try:
        report, itok, otok = call_claude(WRITER_SYSTEM, user, model=model, effort=eff)
        token_usage = add_usage(token_usage, "writer", itok, otok)
        logs.append(log(rid, "writer", "report generated", tool="claude"))
    except Exception as e:  # noqa: BLE001 — fallback to a stub report
        report = (f"# Research Report\n\n**Question:** {state['user_query']}\n\n"
                  "## Summary\nReport generation encountered an issue; see evidence logs.\n\n"
                  "## Evidence\n" +
                  "\n".join([f"- {w.get('claim', 'N/A')[:100]}" for w in web[:5]]) +
                  f"\n\n## Notes\n{len(sources)} sources gathered.")
        logs.append(log(rid, "writer", "report fallback", status="degraded", error=str(e)))

    return {
        "current_agent": "writer",
        "completed_agents": ["writer"],
        "final_report": report,
        "status": Status.COMPLETE,
        "token_usage": token_usage,
        "messages": [comms("writer", "supervisor", "result",
                           f"Report: {len(report)} chars, {report.count('##')} sections", rid)],
        "execution_logs": logs,
    }
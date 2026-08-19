"""Research agent: web (Tavily) + academic (OpenAlex) evidence gathering.

DAY 4: real tool calls. Each tool is wrapped independently so one outage
degrades that source only — the graph never crashes on a tool failure.
Claude then extracts structured claims, each tied to a source URL.
"""
from __future__ import annotations
import json
from graph.state import comms, log
from agents.base_agent import call_claude, add_usage, resolve_effort
from tools.web_search import search_web
from tools.academic_search import search_academic
import config

EXTRACT_SYSTEM = (
    "You extract evidence for a research question. Given search results, return "
    "ONLY a JSON array. Each element: {\"claim\": str, \"source_url\": str, "
    "\"title\": str, \"snippet\": str}. The claim must be a specific factual "
    "statement supported by that source — not a summary of the source. Copy "
    "source_url and title verbatim from the input. Omit results that don't "
    "support a concrete claim. No prose, no markdown fences."
)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def _queries(state) -> list[str]:
    """Build search queries from the plan's evidence needs, falling back to the query."""
    plan = state.get("research_plan") or {}
    needs = [n for n in (plan.get("evidence_needs") or []) if isinstance(n, str)]
    base = state["user_query"]
    qs = [base] + [f"{base} {n}" for n in needs[:2]]
    return qs[:3]


def researcher_node(state):
    rid = state["run_id"]
    rev = state.get("revision_count", 0)
    eff = resolve_effort(state, "research")
    logs, errors = [], []
    web_hits: list[dict] = []
    lit: list[dict] = []

    # --- Web search (Tavily) — degrade independently ---
    for q in _queries(state):
        try:
            hits = search_web(q)
            web_hits.extend(hits)
            logs.append(log(rid, "research", f"tavily: {len(hits)} hits for '{q[:40]}'",
                            tool="tavily"))
        except Exception as e:  # noqa: BLE001
            logs.append(log(rid, "research", "tavily failed", status="degraded",
                            tool="tavily", error=str(e)))
            errors.append({"agent": "research", "tool": "tavily", "error": str(e)})

    # --- Academic search (OpenAlex) — degrade independently ---
    try:
        lit = search_academic(state["user_query"])
        logs.append(log(rid, "research", f"openalex: {len(lit)} works", tool="openalex"))
    except Exception as e:  # noqa: BLE001
        logs.append(log(rid, "research", "openalex failed", status="degraded",
                        tool="openalex", error=str(e)))
        errors.append({"agent": "research", "tool": "openalex", "error": str(e)})

    # --- Extract structured claims from web hits via Claude ---
    results: list[dict] = []
    token_usage = state.get("token_usage", {})
    if web_hits:
        payload = json.dumps(web_hits[:10], indent=2)[:12000]
        user = (f"Research question: {state['user_query']}\n\n"
                f"Search results:\n{payload}\n\nExtract the evidence as JSON.")
        try:
            text, itok, otok = call_claude(EXTRACT_SYSTEM, user,
                                           model=config.AGENT_MODEL, effort=eff)
            parsed = json.loads(_strip_fences(text))
            if isinstance(parsed, list):
                results = [r for r in parsed if isinstance(r, dict) and r.get("source_url")]
            token_usage = add_usage(token_usage, "research", itok, otok)
            logs.append(log(rid, "research", f"extracted {len(results)} claims", tool="claude"))
        except Exception as e:  # noqa: BLE001
            # Fall back to raw hits so downstream agents still get evidence.
            results = [{"claim": h["snippet"][:200], "source_url": h["url"],
                        "title": h["title"], "snippet": h["snippet"]} for h in web_hits[:5]]
            logs.append(log(rid, "research", "extraction fallback (raw hits)",
                            status="degraded", error=str(e)))

    msg = f"Retrieved {len(results)} web claims + {len(lit)} academic works"
    if errors:
        msg += f" ({len(errors)} tool failure(s))"

    return {
        "current_agent": "research",
        "completed_agents": [f"research@{rev}"],
        "research_results": results,
        "literature_results": lit,
        "token_usage": token_usage,
        "errors": errors,
        "messages": [comms("research", "supervisor", "result", msg, rid)],
        "execution_logs": logs,
    }
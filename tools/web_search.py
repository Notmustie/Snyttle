"""Tavily web search.

Returns structured hits. Raises on failure so the calling agent can log the
error and degrade gracefully (the graph must never crash on a tool outage).
"""
from __future__ import annotations
import os
import config


def search_web(query: str, k: int = config.TAVILY_MAX_RESULTS) -> list[dict]:
    """Search the web via Tavily. Returns [{title, url, snippet}]."""
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY not set")

    from tavily import TavilyClient  # imported lazily so the skeleton runs without it
    client = TavilyClient(api_key=key)
    resp = client.search(query=query, max_results=k, search_depth="basic")

    out = []
    for r in resp.get("results", []):
        out.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": (r.get("content") or "")[:500],
        })
    return out
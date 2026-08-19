"""OpenAlex academic search (no API key required).

Set OPENALEX_MAILTO in .env to join the polite pool (faster, more reliable).
"""
from __future__ import annotations
import os
import requests
import config

BASE = "https://api.openalex.org/works"


def _abstract_from_index(inv: dict | None) -> str:
    """OpenAlex returns abstracts as an inverted index; rebuild the text."""
    if not inv:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)[:800]


def search_academic(query: str, k: int = config.OPENALEX_MAX_RESULTS) -> list[dict]:
    """Search OpenAlex. Returns [{title, authors, year, doi, url, abstract}]."""
    params = {"search": query, "per_page": k}
    mailto = os.getenv("OPENALEX_MAILTO")
    if mailto:
        params["mailto"] = mailto

    resp = requests.get(BASE, params=params, timeout=20)
    resp.raise_for_status()

    out = []
    for w in resp.json().get("results", []):
        authors = [a.get("author", {}).get("display_name", "")
                   for a in (w.get("authorships") or [])][:5]
        out.append({
            "title": w.get("display_name", ""),
            "authors": [a for a in authors if a],
            "year": w.get("publication_year"),
            "doi": w.get("doi", ""),
            "url": w.get("id", ""),
            "abstract": _abstract_from_index(w.get("abstract_inverted_index")),
        })
    return out
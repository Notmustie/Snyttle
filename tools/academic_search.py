"""OpenAlex academic search (no API key required).

Set OPENALEX_MAILTO in .env to join the polite pool (faster, more reliable).
"""
from __future__ import annotations
import os
import re
import time
import requests
import config

BASE = "https://api.openalex.org/works"

_UNSAFE = re.compile(r"[^\w\s-]")


def _sanitize_query(q: str) -> str:
    cleaned = _UNSAFE.sub(" ", q)
    return " ".join(cleaned.split())[:300]


def _abstract_from_index(inv: dict | None) -> str:
    if not inv:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)[:800]


def search_academic(query: str, k: int = config.OPENALEX_MAX_RESULTS,
                    max_retries: int = 2) -> list[dict]:
    """Search OpenAlex. Retries with backoff on 429 (rate limit)."""
    params = {"search": _sanitize_query(query), "per_page": k}
    mailto = os.getenv("OPENALEX_MAILTO")
    if mailto:
        params["mailto"] = mailto

    resp = None
    for attempt in range(max_retries + 1):
        resp = requests.get(BASE, params=params, timeout=20)
        if resp.status_code == 429 and attempt < max_retries:
            time.sleep(1.5 * (attempt + 1))
            continue
        break
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
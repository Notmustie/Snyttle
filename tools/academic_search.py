"""OpenAlex/Crossref academic search (stub)."""
import config
def search_academic(query: str, k: int = config.OPENALEX_MAX_RESULTS) -> list[dict]:
    return [{"title": f"Paper on {query}", "authors": [], "year": 2025,
             "doi": "10.0000/stub", "abstract": "stub"}][:k]

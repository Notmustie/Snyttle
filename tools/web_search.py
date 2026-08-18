"""Tavily web search (stub). Real: call Tavily API, return structured results."""
import config
def search_web(query: str, k: int = config.TAVILY_MAX_RESULTS) -> list[dict]:
    return [{"claim": "", "source_url": "https://example.com", "title": f"Result for {query}",
             "snippet": "stub"}][:k]

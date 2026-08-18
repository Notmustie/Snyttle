"""Research agent: web (Tavily) + academic (OpenAlex). Skeleton = dummy evidence."""
from agents.base_agent import stub_node

researcher_node = stub_node(
    "research", "supervisor", "Retrieved 3 web + 2 academic sources (stub)",
    produces={
        "research_results": [{"claim": "stub finding", "source_url": "https://example.com",
                              "title": "Stub source", "snippet": "..."}],
        "literature_results": [{"title": "Stub paper", "authors": ["A. Author"],
                                "year": 2025, "doi": "10.0000/stub", "abstract": "..."}],
    },
)

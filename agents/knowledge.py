"""Knowledge/RAG agent: Chroma retrieval with provenance. Skeleton = dummy passage."""
from agents.base_agent import stub_node

knowledge_node = stub_node(
    "knowledge", "supervisor", "Retrieved 2 passages from uploaded docs (stub)",
    produces={"retrieved_context": [
        {"text": "stub passage", "source_id": "doc1#p3", "page": 3, "doc_name": "upload.pdf"}]},
)

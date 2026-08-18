"""RAG pipeline (stub): PDF -> chunk -> Chroma -> retrieve with provenance."""
import config
def ingest_pdf(path: str) -> int:
    """Extract, chunk, embed (Chroma default), store. Returns chunk count."""
    return 0
def retrieve(query: str, k: int = config.RETRIEVE_K) -> list[dict]:
    return [{"text": "stub passage", "source_id": "doc#p1", "page": 1, "doc_name": "stub.pdf"}][:k]

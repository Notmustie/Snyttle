"""Chroma vector store wrapper (stub). Uses Chroma default embeddings (local)."""
import config
class VectorStore:
    def __init__(self, path: str = config.CHROMA_DIR):
        self.path = path
    def add(self, chunks: list[dict]): ...
    def query(self, text: str, k: int = config.RETRIEVE_K) -> list[dict]:
        return []

"""Chroma vector store wrapper.

Uses Chroma's DEFAULT embedding function (all-MiniLM-L6-v2, runs locally via
ONNX) — no extra API key, no per-token cost, works offline. Persists to disk so
the knowledge base survives restarts.
"""
from __future__ import annotations
import config


class VectorStore:
    """Thin wrapper over a persistent Chroma collection."""

    def __init__(self, path: str = config.CHROMA_DIR, collection: str = "documents"):
        import chromadb
        self.client = chromadb.PersistentClient(path=path)
        self.collection = self.client.get_or_create_collection(name=collection)

    def add(self, chunks: list[dict]) -> int:
        """Add chunks. Each: {id, text, metadata:{source_id, doc_name, page}}."""
        if not chunks:
            return 0
        self.collection.add(
            ids=[c["id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[c["metadata"] for c in chunks],
        )
        return len(chunks)

    def query(self, text: str, k: int = config.RETRIEVE_K) -> list[dict]:
        """Retrieve top-k passages WITH provenance metadata."""
        if self.count() == 0:
            return []
        res = self.collection.query(query_texts=[text], n_results=min(k, self.count()))
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        out = []
        for i, doc in enumerate(docs):
            m = metas[i] if i < len(metas) else {}
            out.append({
                "text": doc,
                "source_id": m.get("source_id", ""),
                "doc_name": m.get("doc_name", ""),
                "page": m.get("page"),
                "distance": dists[i] if i < len(dists) else None,
            })
        return out

    def count(self) -> int:
        return self.collection.count()

    def reset(self) -> None:
        """Drop and recreate the collection (used by tests)."""
        name = self.collection.name
        self.client.delete_collection(name)
        self.collection = self.client.get_or_create_collection(name=name)
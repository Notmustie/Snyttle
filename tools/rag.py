"""RAG pipeline: PDF/text -> extract -> chunk -> embed -> Chroma -> retrieve.

Every chunk carries provenance (doc_name, page, source_id) so retrieved context
can be cited in the final report.
"""
from __future__ import annotations
import hashlib
import os
from memory.vector_store import VectorStore
import config


def _chunk_text(text: str, size: int = config.CHUNK_SIZE,
                overlap: int = config.CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping character windows, breaking on whitespace."""
    text = " ".join(text.split())
    if not text:
        return []
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            sp = text.rfind(" ", start + int(size * 0.5), end)
            if sp != -1:
                end = sp
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def extract_pages(path: str) -> list[tuple[int, str]]:
    """Return [(page_number, text)]. Supports .pdf and plain text files."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        return [(i + 1, (p.extract_text() or "")) for i, p in enumerate(reader.pages)]
    with open(path, "r", errors="ignore") as f:
        return [(1, f.read())]


def ingest_document(path: str, store: VectorStore | None = None) -> dict:
    """Extract, chunk, and store a document. Returns {doc_name, pages, chunks}."""
    store = store or VectorStore()
    doc_name = os.path.basename(path)
    pages = extract_pages(path)

    chunks = []
    for page_no, page_text in pages:
        for j, ch in enumerate(_chunk_text(page_text)):
            source_id = f"{doc_name}#p{page_no}c{j}"
            uid = hashlib.sha1(f"{source_id}:{ch[:80]}".encode()).hexdigest()[:16]
            chunks.append({
                "id": uid,
                "text": ch,
                "metadata": {"source_id": source_id, "doc_name": doc_name, "page": page_no},
            })

    added = store.add(chunks)
    return {"doc_name": doc_name, "pages": len(pages), "chunks": added}


def retrieve(query: str, k: int = config.RETRIEVE_K,
             store: VectorStore | None = None) -> list[dict]:
    """Retrieve top-k passages with provenance."""
    store = store or VectorStore()
    return store.query(query, k=k)
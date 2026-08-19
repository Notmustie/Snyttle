"""Knowledge/RAG agent: index uploaded documents and retrieve with provenance.

DAY 5: real Chroma-backed retrieval. Ingestion is idempotent per run (chunk ids
are content-hashed, so re-ingesting the same doc won't duplicate). Every
retrieved passage carries doc_name + page + source_id for citation.
"""
from __future__ import annotations
from graph.state import comms, log
from tools.rag import ingest_document, retrieve
from memory.vector_store import VectorStore
import config

INGESTABLE = {"pdf", "txt", "md", "other"}


def _queries(state) -> list[str]:
    """Retrieve against the question plus the plan's evidence needs."""
    plan = state.get("research_plan") or {}
    needs = [n for n in (plan.get("evidence_needs") or []) if isinstance(n, str)]
    return [state["user_query"]] + needs[:2]


def knowledge_node(state):
    rid = state["run_id"]
    rev = state.get("revision_count", 0)
    logs, errors = [], []
    retrieved: list[dict] = []

    docs = [f for f in state.get("uploaded_files", [])
            if f.get("type") in INGESTABLE]
    if not docs:
        return {
            "current_agent": "knowledge",
            "completed_agents": [f"knowledge@{rev}"],
            "messages": [comms("knowledge", "supervisor", "result",
                               "No documents to index", rid)],
            "execution_logs": [log(rid, "knowledge", "no documents; skipped")],
        }

    try:
        store = VectorStore()
    except Exception as e:  # noqa: BLE001 — Chroma unavailable
        return {
            "current_agent": "knowledge",
            "completed_agents": [f"knowledge@{rev}"],
            "errors": [{"agent": "knowledge", "tool": "chroma", "error": str(e)}],
            "messages": [comms("knowledge", "supervisor", "result",
                               "RAG unavailable (vector store error)", rid)],
            "execution_logs": [log(rid, "knowledge", "chroma init failed",
                                   status="degraded", tool="chroma", error=str(e))],
        }

    # --- Ingest each document independently ---
    for d in docs:
        try:
            info = ingest_document(d["path"], store=store)
            logs.append(log(rid, "knowledge",
                            f"ingested {info['doc_name']}: {info['pages']}p "
                            f"-> {info['chunks']} chunks", tool="chroma"))
        except Exception as e:  # noqa: BLE001
            logs.append(log(rid, "knowledge", f"ingest failed: {d.get('name')}",
                            status="degraded", tool="chroma", error=str(e)))
            errors.append({"agent": "knowledge", "tool": "chroma",
                           "error": f"{d.get('name')}: {e}"})

    # --- Retrieve with provenance, de-duplicated by source_id ---
    seen = set()
    for q in _queries(state):
        try:
            for p in retrieve(q, k=config.RETRIEVE_K, store=store):
                sid = p.get("source_id")
                if sid and sid not in seen:
                    seen.add(sid)
                    retrieved.append(p)
            logs.append(log(rid, "knowledge", f"retrieved for '{q[:40]}'", tool="chroma"))
        except Exception as e:  # noqa: BLE001
            logs.append(log(rid, "knowledge", "retrieval failed", status="degraded",
                            tool="chroma", error=str(e)))
            errors.append({"agent": "knowledge", "tool": "chroma", "error": str(e)})

    msg = f"Indexed {len(docs)} doc(s); retrieved {len(retrieved)} passages"
    if errors:
        msg += f" ({len(errors)} failure(s))"

    return {
        "current_agent": "knowledge",
        "completed_agents": [f"knowledge@{rev}"],
        "retrieved_context": retrieved,
        "errors": errors,
        "messages": [comms("knowledge", "supervisor", "result", msg, rid)],
        "execution_logs": logs,
    }
# -*- coding: utf-8 -*-
"""
P4.4 — Custom firm playbook: ingest, search, delete.
Stores firm-specific style/clause examples in Pinecone namespace playbook_{user_id}.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_CHUNK_SIZE    = 500
_CHUNK_OVERLAP = 50
_EMBEDDING_MODEL = "text-embedding-3-large"
_EMBEDDING_DIMS  = 3072
_NS_PREFIX = "playbook_"


def _get_pinecone_index():
    from pinecone import Pinecone
    api_key = os.environ["PINECONE_API_KEY"]
    host    = os.environ.get("PINECONE_HOST", "")
    pc = Pinecone(api_key=api_key)
    if host:
        return pc.Index(host=host)
    indexes = pc.list_indexes()
    return pc.Index(indexes[0].name)


def _get_embeddings_client():
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(
        model=_EMBEDDING_MODEL,
        dimensions=_EMBEDDING_DIMS,
        openai_api_key=os.environ["OPENAI_API_KEY"],
    )


def _chunk_text(tekst: str) -> list[str]:
    """Split text into overlapping chunks of _CHUNK_SIZE chars."""
    chunks: list[str] = []
    start = 0
    while start < len(tekst):
        end = start + _CHUNK_SIZE
        chunks.append(tekst[start:end].strip())
        start += _CHUNK_SIZE - _CHUNK_OVERLAP
    return [c for c in chunks if c]


def ingest_playbook(user_id: str, filename: str, tekst: str) -> int:
    """Embed and upsert document into playbook_{user_id} namespace.

    Returns the number of vectors upserted.
    """
    if not tekst or not tekst.strip():
        return 0

    chunks = _chunk_text(tekst)
    if not chunks:
        return 0

    namespace = f"{_NS_PREFIX}{user_id}"
    emb_client = _get_embeddings_client()
    index = _get_pinecone_index()

    vectors_raw = emb_client.embed_documents(chunks)

    import uuid
    records = []
    for i, (chunk, vec) in enumerate(zip(chunks, vectors_raw)):
        records.append({
            "id": f"pb_{user_id}_{i}_{uuid.uuid4().hex[:8]}",
            "values": vec,
            "metadata": {
                "user_id":     user_id,
                "filename":    filename,
                "chunk_index": i,
                "text":        chunk,
            },
        })

    batch = 50
    for start in range(0, len(records), batch):
        index.upsert(vectors=records[start:start + batch], namespace=namespace)

    logger.info("[PLAYBOOK] ingest user=%.8s ns=%s chunks=%d", user_id, namespace, len(records))
    return len(records)


def search_playbook(user_id: str, query: str, top_k: int = 3) -> list[str]:
    """Search playbook_{user_id} namespace and return matching text chunks."""
    if not query or not query.strip():
        return []
    try:
        namespace = f"{_NS_PREFIX}{user_id}"
        emb_client = _get_embeddings_client()
        vec = emb_client.embed_query(query)
        index = _get_pinecone_index()
        result = index.query(
            vector=vec,
            top_k=top_k,
            namespace=namespace,
            include_metadata=True,
        )
        matches = result.matches if hasattr(result, "matches") else result.get("matches", [])
        texts = [(m.metadata or {}).get("text", "") for m in matches]
        return [t for t in texts if t.strip()]
    except Exception:
        logger.warning("[PLAYBOOK] search failed for user=%.8s", user_id)
        return []


def delete_playbook(user_id: str) -> int:
    """Delete entire playbook_{user_id} namespace. Returns vector count deleted."""
    try:
        namespace = f"{_NS_PREFIX}{user_id}"
        index = _get_pinecone_index()
        stats = index.describe_index_stats()
        ns_data = stats.namespaces.get(namespace) if hasattr(stats, "namespaces") else {}
        count = (ns_data.vector_count if hasattr(ns_data, "vector_count") else 0) if ns_data else 0
        index.delete(delete_all=True, namespace=namespace)
        logger.info("[PLAYBOOK] deleted ns=%s vectors=%d", namespace, count)
        return count
    except Exception:
        logger.warning("[PLAYBOOK] delete failed for user=%.8s", user_id)
        return 0

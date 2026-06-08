# -*- coding: utf-8 -*-
"""
F7 — Interni pravni stavovi firme.
Stores firm-specific internal legal positions in Pinecone namespace interni_stavovi_{user_id}.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_CHUNK_SIZE    = 500
_CHUNK_OVERLAP = 50
_EMBEDDING_MODEL = "text-embedding-3-large"
_EMBEDDING_DIMS  = 3072
_NS_PREFIX = "interni_stavovi_"


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
    chunks: list[str] = []
    start = 0
    while start < len(tekst):
        end = start + _CHUNK_SIZE
        chunks.append(tekst[start:end].strip())
        start += _CHUNK_SIZE - _CHUNK_OVERLAP
    return [c for c in chunks if c]


def ingest_stav(user_id: str, naslov: str, tekst: str) -> int:
    """Embed and upsert internal legal position into interni_stavovi_{user_id} namespace."""
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
            "id": f"is_{user_id[:8]}_{i}_{uuid.uuid4().hex[:8]}",
            "values": vec,
            "metadata": {
                "user_id":     user_id,
                "naslov":      naslov,
                "chunk_index": i,
                "text":        chunk,
                "tip":         "interni_stav",
            },
        })

    batch = 50
    for start in range(0, len(records), batch):
        index.upsert(vectors=records[start:start + batch], namespace=namespace)

    logger.info("[INTERNI] ingest user=%.8s ns=%s chunks=%d naslov=%r", user_id, namespace, len(records), naslov)
    return len(records)


def search_stavovi(user_id: str, upit: str, top_k: int = 5) -> list[dict]:
    """Search interni_stavovi_{user_id} namespace and return matching chunks with score."""
    if not upit or not upit.strip():
        return []
    try:
        namespace = f"{_NS_PREFIX}{user_id}"
        emb_client = _get_embeddings_client()
        vec = emb_client.embed_query(upit)
        index = _get_pinecone_index()
        result = index.query(
            vector=vec,
            top_k=top_k,
            namespace=namespace,
            include_metadata=True,
        )
        matches = result.matches if hasattr(result, "matches") else result.get("matches", [])
        return [
            {
                "tekst":  (m.metadata or {}).get("text", ""),
                "naslov": (m.metadata or {}).get("naslov", ""),
                "score":  round(float(m.score), 3),
            }
            for m in matches
            if float(m.score) > 0.5 and (m.metadata or {}).get("text", "").strip()
        ]
    except Exception:
        logger.warning("[INTERNI] search failed for user=%.8s", user_id)
        return []


def obrisi_stavove(user_id: str) -> int:
    """Delete entire interni_stavovi_{user_id} namespace. Returns vector count deleted."""
    try:
        namespace = f"{_NS_PREFIX}{user_id}"
        index = _get_pinecone_index()
        stats = index.describe_index_stats()
        ns_data = stats.namespaces.get(namespace) if hasattr(stats, "namespaces") else {}
        count = (ns_data.vector_count if hasattr(ns_data, "vector_count") else 0) if ns_data else 0
        index.delete(delete_all=True, namespace=namespace)
        logger.info("[INTERNI] deleted ns=%s vectors=%d", namespace, count)
        return count
    except Exception:
        logger.warning("[INTERNI] delete failed for user=%.8s", user_id)
        return 0


def status_stavova(user_id: str) -> dict:
    """Returns namespace stats for user's internal positions."""
    try:
        namespace = f"{_NS_PREFIX}{user_id}"
        index = _get_pinecone_index()
        stats = index.describe_index_stats()
        ns_data = stats.namespaces.get(namespace) if hasattr(stats, "namespaces") else {}
        count = (ns_data.vector_count if hasattr(ns_data, "vector_count") else 0) if ns_data else 0
        return {"ima_stavova": count > 0, "broj_vektora": count}
    except Exception:
        return {"ima_stavova": False, "broj_vektora": 0}

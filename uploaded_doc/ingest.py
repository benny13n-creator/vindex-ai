from __future__ import annotations

import logging
import os
from typing import Optional

from .schema import ChunkingManifest
from .session import expires_at_iso

logger = logging.getLogger(__name__)

_TEXT_TRUNCATE = 40_000
_TMP_NS_PREFIX = "tmp_"


def _get_pinecone_index():
    from pinecone import Pinecone
    api_key = os.environ["PINECONE_API_KEY"]
    host = os.environ.get("PINECONE_HOST", "")
    pc = Pinecone(api_key=api_key)
    if host:
        return pc.Index(host=host)
    # Fall back to first available index
    indexes = pc.list_indexes()
    index_name = indexes[0].name
    return pc.Index(index_name)


def _get_embeddings_client():
    from langchain_openai import OpenAIEmbeddings
    from app.services.retrieve import EMBEDDING_MODEL
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        dimensions=3072,
        openai_api_key=os.environ["OPENAI_API_KEY"],
    )


def ingest_session(
    manifest: ChunkingManifest,
    session_id: str,
    ttl_hours: int = 24,
    namespace_prefix: str = _TMP_NS_PREFIX,
    namespace_override: Optional[str] = None,
    extra_metadata: Optional[dict] = None,
) -> int:
    """Embed chunks and upsert to a Pinecone namespace.

    Default behavior (namespace_override=None) is UNCHANGED: namespace is
    <namespace_prefix><session_id>. Use namespace_prefix='pred_' for permanent
    predmet documents (cleanup_expired only deletes tmp_* namespaces).
    Default prefix 'tmp_' is for temporary sessions.

    namespace_override / extra_metadata (Institutional Learning & RAG Audit,
    2026-07-26, stavka #1): kad je namespace_override prosleđen, koristi se
    UMESTO <prefix><session_id> -- ovo je kanal za novu "vlasnik znanja"
    šemu (kancelarija_{id} / user_{id}, v. shared/kancelarija_utils.py)
    koja zamenjuje raniju per-upload nasumičnu pred_{session_id} šemu.
    extra_metadata (npr. {"predmet_id":..., "kancelarija_id":..., "type":
    "case_doc"}) se dodaje u metadata SVAKOG vektora, da omogući metadata
    filter pri pretrazi unutar deljenog namespace-a.

    Returns the number of vectors upserted. Raises on API errors.
    """
    if manifest.total_chunks == 0:
        return 0

    namespace = namespace_override if namespace_override else f"{namespace_prefix}{session_id}"
    exp_iso = expires_at_iso(ttl_hours) if (not namespace_override and namespace_prefix == _TMP_NS_PREFIX) else ""

    embeddings_client = _get_embeddings_client()
    index = _get_pinecone_index()

    texts = [c.text for c in manifest.chunks]
    vectors_raw = embeddings_client.embed_documents(texts)

    records = []
    for chunk, vec in zip(manifest.chunks, vectors_raw):
        text_stored = chunk.text[:_TEXT_TRUNCATE]
        metadata = {
            "session_id": session_id,
            "source_filename": manifest.source_filename,
            "source_format": manifest.source_format,
            "chunk_index": chunk.chunk_index,
            "chunk_mode": chunk.chunk_mode,
            "article_label": chunk.article_label or "",
            "text": text_stored,
            "token_count": chunk.token_count,
            "expires_at": exp_iso,
        }
        if extra_metadata:
            metadata.update(extra_metadata)
        records.append({
            "id": chunk.chunk_id,
            "values": vec,
            "metadata": metadata,
        })

    BATCH_SIZE = 50
    for i in range(0, len(records), BATCH_SIZE):
        index.upsert(vectors=records[i:i+BATCH_SIZE], namespace=namespace)
    logger.info(
        "[INGEST] session=%s ns=%s chunks=%d",
        session_id, namespace, len(records),
    )
    return len(records)

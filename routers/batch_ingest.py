# -*- coding: utf-8 -*-
"""
Vindex AI — routers/batch_ingest.py

Phase 5.2: Batch ingest novih presuda.
Admin-only endpoints for ingesting new court decisions into Pinecone.
All endpoints require founder-level admin access.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from shared.deps import FOUNDER_EMAILS, _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.batch_ingest")
router = APIRouter(tags=["batch_ingest"])

ALLOWED_NAMESPACES = {"sudska_praksa", "misljenja"}

# Transliteration map for ASCII Pinecone vector IDs
_SRLATMAP = str.maketrans("žšćčđŽŠĆČĐ", "zsccdZSCCD")

_CHUNK_SIZE    = 800
_CHUNK_OVERLAP = 150
_EMBED_BATCH   = 50
_UPSERT_BATCH  = 100


# ─── Admin guard ──────────────────────────────────────────────────────────────

async def _require_admin(user: dict = Depends(get_current_user)) -> dict:
    if (user.get("email") or "").lower() not in FOUNDER_EMAILS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pristup zabranjen — samo za administratore.",
        )
    return user


# ─── Patchable wrappers (critical for asyncio.to_thread testability) ──────────

def _embed(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI
    client = OpenAI()
    resp = client.embeddings.create(model="text-embedding-3-large", input=texts)
    return [e.embedding for e in resp.data]


def _upsert_to_pinecone(vectors: list[dict], namespace: str) -> None:
    from pinecone import Pinecone
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    idx = pc.Index(os.environ.get("PINECONE_INDEX", "vindex-ai"))
    idx.upsert(vectors=vectors, namespace=namespace)


def _update_job(supa, job_id: str, **fields) -> None:
    supa.table("ingest_jobs").update(fields).eq("id", job_id).execute()


# ─── Chunking helpers ─────────────────────────────────────────────────────────

def chunk_text(text: str) -> list[str]:
    text = text.strip()
    if len(text) <= _CHUNK_SIZE:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + _CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - _CHUNK_OVERLAP
    return chunks


def build_chunks(decision_id: str, text: str, metadata: dict) -> list[dict]:
    ascii_id = decision_id.translate(_SRLATMAP)
    parts = chunk_text(text)
    result = []
    for i, part in enumerate(parts):
        result.append({
            "id":       f"{ascii_id}_c{i}",
            "values":   [],
            "metadata": {
                "text":        part,
                "chunk_index": i,
                "decision_id": decision_id,
                **{k: v for k, v in metadata.items() if v is not None},
            },
        })
    return result


# ─── Core ingest logic ────────────────────────────────────────────────────────

def _run_ingest_sync(
    job_id: str,
    decisions: list[dict],
    namespace: str,
    supa,
) -> None:
    """Synchronous ingest runner — call via asyncio.to_thread."""
    processed = 0
    failed    = 0

    _update_job(supa, job_id,
                status="running",
                started_at=datetime.now(timezone.utc).isoformat())

    # Build chunks from all decisions
    all_chunks: list[dict] = []
    for dec in decisions:
        try:
            chunks = build_chunks(dec["id"], dec["text"], dec.get("metadata", {}))
            all_chunks.extend(chunks)
        except Exception as exc:
            logger.warning("Chunking failed for %s: %s", dec.get("id"), exc)
            failed += 1

    # Embed in batches, collect vectors
    texts = [c["metadata"]["text"] for c in all_chunks]
    vectors_ready: list[dict] = []
    for i in range(0, len(texts), _EMBED_BATCH):
        batch_texts = texts[i : i + _EMBED_BATCH]
        try:
            embeddings = _embed(batch_texts)
            for j, emb in enumerate(embeddings):
                chunk = all_chunks[i + j]
                vectors_ready.append({
                    "id":       chunk["id"],
                    "values":   emb,
                    "metadata": chunk["metadata"],
                })
        except Exception as exc:
            logger.error("Embedding batch %d failed: %s", i // _EMBED_BATCH, exc)
            failed += len(batch_texts)

    # Upsert to Pinecone in batches
    for i in range(0, len(vectors_ready), _UPSERT_BATCH):
        batch = vectors_ready[i : i + _UPSERT_BATCH]
        try:
            _upsert_to_pinecone(batch, namespace)
            processed += len(batch)
        except Exception as exc:
            logger.error("Upsert batch %d failed: %s", i // _UPSERT_BATCH, exc)
            failed += len(batch)
        _update_job(supa, job_id, processed=processed, failed_docs=failed)

    final_status = "done" if processed > 0 else "failed"
    _update_job(
        supa, job_id,
        status=final_status,
        processed=processed,
        failed_docs=failed,
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    logger.info("Ingest job %s finished: processed=%d failed=%d status=%s",
                job_id, processed, failed, final_status)


# ─── Request / response models ────────────────────────────────────────────────

class IngestDecision(BaseModel):
    id:       str  = Field(..., min_length=1, max_length=200)
    text:     str  = Field(..., min_length=10, max_length=100_000)
    metadata: dict = Field(default_factory=dict)


class IngestJobReq(BaseModel):
    namespace: str                  = Field(default="sudska_praksa")
    source:    Optional[str]        = Field(default=None, max_length=500)
    decisions: list[IngestDecision] = Field(..., min_length=1, max_length=500)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/api/admin/ingest/job", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
async def create_ingest_job(
    request: Request,
    req: IngestJobReq,
    bt: BackgroundTasks,
    user: dict = Depends(_require_admin),
):
    if req.namespace not in ALLOWED_NAMESPACES:
        raise HTTPException(
            status_code=422,
            detail=f"Namespace '{req.namespace}' nije dozvoljen. Dozvoljeni: {sorted(ALLOWED_NAMESPACES)}",
        )

    supa   = _get_supa()
    job_id = str(uuid.uuid4())
    decisions_raw = [d.model_dump() for d in req.decisions]

    supa.table("ingest_jobs").insert({
        "id":          job_id,
        "created_by":  (user.get("email") or ""),
        "status":      "pending",
        "namespace":   req.namespace,
        "source":      req.source,
        "total_docs":  len(req.decisions),
        "processed":   0,
        "failed_docs": 0,
        "created_at":  datetime.now(timezone.utc).isoformat(),
    }).execute()

    bt.add_task(
        asyncio.to_thread,
        _run_ingest_sync,
        job_id,
        decisions_raw,
        req.namespace,
        supa,
    )

    return {
        "job_id":     job_id,
        "status":     "pending",
        "total_docs": len(req.decisions),
        "namespace":  req.namespace,
    }


@router.get("/api/admin/ingest/jobs")
@limiter.limit("30/minute")
async def list_ingest_jobs(
    request: Request,
    user: dict = Depends(_require_admin),
):
    supa = _get_supa()
    result = await asyncio.to_thread(
        lambda: supa.table("ingest_jobs")
                     .select("*")
                     .order("created_at", desc=True)
                     .limit(20)
                     .execute()
    )
    return {"jobs": result.data or []}


@router.get("/api/admin/ingest/job/{job_id}")
@limiter.limit("30/minute")
async def get_ingest_job(
    request: Request,
    job_id: str,
    user: dict = Depends(_require_admin),
):
    supa = _get_supa()
    result = await asyncio.to_thread(
        lambda: supa.table("ingest_jobs")
                     .select("*")
                     .eq("id", job_id)
                     .single()
                     .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Posao nije pronađen.")
    return result.data

"""
B1 write-only audit log — PII-free, fire-and-forget.

Storage: Supabase (Postgres). Chosen because it is already in the stack,
persists across Render redeploys (ephemeral disk would lose JSONL/SQLite on
every deploy), and the free tier handles 50-200 req/day trivially.

Run this SQL ONCE in Supabase Dashboard → SQL Editor before deploying:

    CREATE TABLE IF NOT EXISTS response_audit (
        id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        ts            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        pipeline_id   VARCHAR(32) NOT NULL,
        endpoint      VARCHAR(60) NOT NULL,
        tip           VARCHAR(20),
        query_hash    VARCHAR(16) NOT NULL,
        confidence    VARCHAR(10),
        top_score     FLOAT,
        top_article   TEXT,
        top_law       TEXT,
        response_len  INTEGER     NOT NULL DEFAULT 0,
        response_hash VARCHAR(32) NOT NULL,
        latency_ms    INTEGER     NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS ra_ts_idx    ON response_audit(ts DESC);
    CREATE INDEX IF NOT EXISTS ra_qhash_idx ON response_audit(query_hash);
"""

import asyncio
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("vindex.audit")

_supa = None


def _get_supa():
    global _supa
    if _supa is None:
        try:
            from supabase import create_client
            url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
            key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
            if url and key:
                _supa = create_client(url, key)
        except Exception:
            logger.warning("audit_log: Supabase client init failed")
    return _supa


def _sha(text: str, n: int = 16) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()[:n]


def log_response(
    *,
    endpoint: str,
    query_hash: str,
    tip: Optional[str] = None,
    confidence: Optional[str] = None,
    top_score: Optional[float] = None,
    top_article: Optional[str] = None,
    top_law: Optional[str] = None,
    response_text: str = "",
    latency_ms: int = 0,
) -> None:
    """
    Fire-and-forget B1 audit entry. Call from async context only.
    Schedules a background write; never blocks the response.
    Failure is caught and logged to stderr — never propagated.
    """
    asyncio.create_task(
        _write(
            endpoint=endpoint,
            query_hash=query_hash,
            tip=tip,
            confidence=confidence,
            top_score=top_score,
            top_article=top_article,
            top_law=top_law,
            response_text=response_text,
            latency_ms=latency_ms,
        )
    )


async def _write(
    *,
    endpoint: str,
    query_hash: str,
    tip: Optional[str],
    confidence: Optional[str],
    top_score: Optional[float],
    top_article: Optional[str],
    top_law: Optional[str],
    response_text: str,
    latency_ms: int,
) -> None:
    try:
        supa = _get_supa()
        if supa is None:
            return
        ts = datetime.now(timezone.utc).isoformat()
        pipeline_id = _sha(f"{ts}:{query_hash}", 32)
        await asyncio.to_thread(
            lambda: supa.table("response_audit").insert({
                "ts":           ts,
                "pipeline_id":  pipeline_id,
                "endpoint":     endpoint,
                "tip":          tip,
                "query_hash":   query_hash,
                "confidence":   confidence,
                "top_score":    top_score,
                "top_article":  top_article,
                "top_law":      top_law,
                "response_len": len(response_text),
                "response_hash": _sha(response_text, 32),
                "latency_ms":   latency_ms,
            }).execute()
        )
        logger.debug(
            "[AUDIT] %s q=%s conf=%s lat=%dms",
            endpoint, query_hash, confidence, latency_ms,
        )
    except Exception:
        logger.warning("B1 audit write failed — non-blocking", exc_info=True)

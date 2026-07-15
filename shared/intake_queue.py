# -*- coding: utf-8 -*-
"""
Vindex AI — shared/intake_queue.py

Smart Intake Engine, Faza 0 (docs/adr/, ADR-0002) — Postgres-backed job
queue. intake_jobs.status JE queue-a; workeri claim-uju redove preko
claim_intake_job() RPC (SELECT ... FOR UPDATE SKIP LOCKED), nikad direktnim
UPDATE-om (race condition između konkurentnih workera bez row-level lock-a).

Faza 0 namerno NE menja nijedno AI ponašanje — ovaj modul zna samo da
upiše/claim-uje/završi/retry-uje redove. Klasifikacija/ekstrakcija/case-
matching dolaze u Fazi 1 kao stage-workeri koji koriste ove funkcije.

Retry/backoff: eksponencijalni, capped na 1h, dead-letter (status='failed')
posle max_attempts — dizajn review §20 Failure Recovery Strategy.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from shared.deps import _get_supa

logger = logging.getLogger("vindex.intake_queue")

_BACKOFF_BASE_S = 30
_BACKOFF_CAP_S = 3600
_VALID_SOURCES = ("dropzone", "mobile", "watcher", "email", "scanner", "portal", "api")
_VALID_STATUSES = (
    "received", "preprocessing", "classifying", "extracting",
    "matching", "dedup_check", "awaiting_review", "completed", "failed",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def enqueue_job(
    source: str,
    content_sha256: str,
    storage_path: str,
    uploaded_by: str,
    kancelarija_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> str:
    """Atomska Upload Transaction (job + audit_log + outbox event u jednoj
    Postgres transakciji, preko enqueue_intake_job RPC). Idempotentna — isti
    idempotency_key vraća POSTOJEĆI job_id, nikad duplikat."""
    if source not in _VALID_SOURCES:
        raise ValueError(f"intake_queue: '{source}' nije validan izvor {_VALID_SOURCES}.")

    result = await asyncio.to_thread(
        lambda: _get_supa().rpc("enqueue_intake_job", {
            "p_source": source,
            "p_content_sha256": content_sha256,
            "p_storage_path": storage_path,
            "p_uploaded_by": uploaded_by,
            "p_kancelarija_id": kancelarija_id,
            "p_idempotency_key": idempotency_key,
        }).execute()
    )
    job_id = result.data
    if not job_id:
        raise RuntimeError("intake_queue.enqueue_job: RPC nije vratio job_id.")
    logger.info("[INTAKE_QUEUE] enqueue: job=%s izvor=%s", str(job_id)[:8], source)
    return job_id


async def claim_next_job(from_status: str, to_status: str) -> Optional[dict]:
    """Claim najstarijeg claimable reda preko claim_intake_job RPC
    (SELECT ... FOR UPDATE SKIP LOCKED) — bezbedno sa više konkurentnih
    workera. Vraća None ako nema posla."""
    if from_status not in _VALID_STATUSES or to_status not in _VALID_STATUSES:
        raise ValueError(f"intake_queue: nevalidan status prelaz {from_status}->{to_status}.")

    result = await asyncio.to_thread(
        lambda: _get_supa().rpc("claim_intake_job", {
            "p_from_status": from_status,
            "p_to_status": to_status,
        }).execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


async def mark_job_completed(job_id: str) -> None:
    """Atomsko okončanje preko complete_intake_job RPC — status + audit +
    outbox event u jednoj transakciji (ne tri odvojena poziva kao u prvoj
    verziji ovog fajla — taj oblik NIJE bio atoman, popravljeno pre nego što
    je iko počeo da se oslanja na garanciju koju nije zaista davao)."""
    await asyncio.to_thread(
        lambda: _get_supa().rpc("complete_intake_job", {"p_job_id": job_id}).execute()
    )
    logger.info("[INTAKE_QUEUE] completed: job=%s", job_id[:8])


async def mark_job_failed(job_id: str, error: str, attempts: int, max_attempts: int) -> None:
    """Retry sa eksponencijalnim backoff-om (30s * 2^attempts, cap 1h) dok se
    ne dostigne max_attempts — posle toga status='failed' (dead-letter,
    dizajn review §20). Atomsko preko fail_intake_job RPC (status + audit +
    outbox event na dead-letter, status + audit na retry) — backoff formula
    ostaje ovde (jedno mesto), RPC samo upisuje već izračunatu next_retry_at."""
    new_attempts = attempts + 1
    is_dead_letter = new_attempts >= max_attempts
    next_retry = None
    if not is_dead_letter:
        backoff_s = min(_BACKOFF_BASE_S * (2 ** attempts), _BACKOFF_CAP_S)
        next_retry = (datetime.now(timezone.utc) + timedelta(seconds=backoff_s)).isoformat()

    await asyncio.to_thread(
        lambda: _get_supa().rpc("fail_intake_job", {
            "p_job_id": job_id,
            "p_error": error,
            "p_new_attempts": new_attempts,
            "p_max_attempts": max_attempts,
            "p_next_retry_at": next_retry,
        }).execute()
    )

    if is_dead_letter:
        logger.warning("[INTAKE_QUEUE] dead-letter: job=%s posle %d pokušaja: %s", job_id[:8], new_attempts, error)
    else:
        logger.info("[INTAKE_QUEUE] retry scheduled: job=%s pokušaj=%d/%d: %s", job_id[:8], new_attempts, max_attempts, next_retry)


async def reap_stale_jobs(stale_after_seconds: int = 300) -> int:
    """Nalazi poslove zaglavljene u ne-terminalnom, ne-awaiting_review statusu
    čiji je claimed_at stariji od praga (worker je pao usred obrade — restart-
    safety garancija) i vraća ih kroz mark_job_failed (isti retry/dead-letter
    put kao svaki drugi neuspeh). Vraća broj reap-ovanih poslova."""
    threshold = (datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)).isoformat()
    in_progress_statuses = ("preprocessing", "classifying", "extracting", "matching", "dedup_check")

    res = await asyncio.to_thread(
        lambda: _get_supa().table("intake_jobs")
            .select("id, attempts, max_attempts")
            .in_("status", list(in_progress_statuses))
            .lt("claimed_at", threshold)
            .execute()
    )
    stale_jobs = res.data or []
    for job in stale_jobs:
        await mark_job_failed(
            job["id"], "reaped: worker nije javio zavrsetak u okviru praga (verovatno pao usred obrade)",
            job.get("attempts", 0), job.get("max_attempts", 5),
        )
    if stale_jobs:
        logger.warning("[INTAKE_QUEUE] reaped %d zaglavljenih poslova (prag=%ds)", len(stale_jobs), stale_after_seconds)
    return len(stale_jobs)


async def get_queue_metrics() -> dict:
    """Čita intake_queue_metrics view — operativna vidljivost, Faza 0
    Definition of Done. Izvedeno u letu, nikad zaseban stored red."""
    res = await asyncio.to_thread(
        lambda: _get_supa().table("intake_queue_metrics").select("*").execute()
    )
    rows = res.data or []
    return rows[0] if rows else {}


async def get_outbox_metrics() -> dict:
    """Čita events_outbox_metrics view."""
    res = await asyncio.to_thread(
        lambda: _get_supa().table("events_outbox_metrics").select("*").execute()
    )
    rows = res.data or []
    return rows[0] if rows else {}


async def record_heartbeat(worker_id: str, jobs_processed: int, jobs_failed: int) -> None:
    """Upsert worker heartbeat reda — poziva se na svaki worker tick. Best-
    effort: greška ovde ne sme da obori worker petlju."""
    try:
        await asyncio.to_thread(
            lambda: _get_supa().table("intake_worker_heartbeat").upsert({
                "worker_id": worker_id,
                "last_heartbeat_at": _now_iso(),
                "jobs_processed": jobs_processed,
                "jobs_failed": jobs_failed,
            }, on_conflict="worker_id").execute()
        )
    except Exception as exc:
        logger.warning("[INTAKE_QUEUE] heartbeat upis neuspešan (non-fatal) za worker=%s: %s", worker_id, exc)


async def get_worker_heartbeats() -> list[dict]:
    res = await asyncio.to_thread(
        lambda: _get_supa().table("intake_worker_heartbeat").select("*").order("last_heartbeat_at", desc=True).execute()
    )
    return res.data or []


async def write_audit(
    job_id: str,
    event_type: str,
    actor: str,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
) -> None:
    """Append-only zapis — nikad UPDATE/DELETE. Best-effort: greška ovde ne
    sme da obori obradu posla, samo se loguje."""
    try:
        await asyncio.to_thread(
            lambda: _get_supa().table("intake_audit_log").insert({
                "intake_job_id": job_id,
                "event_type": event_type,
                "actor": actor,
                "before": before,
                "after": after,
            }).execute()
        )
    except Exception as exc:
        logger.warning("[INTAKE_QUEUE] audit upis neuspešan (non-fatal) za job=%s: %s", job_id[:8], exc)

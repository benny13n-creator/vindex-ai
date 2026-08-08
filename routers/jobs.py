# -*- coding: utf-8 -*-
"""
Vindex AI — Async Job Queue

In-memory job store za dugotrajne AI operacije (kompletna_analiza, outcome_intel, batch).
Klijent dobija job_id odmah, pa poluje GET /api/jobs/{job_id} dok status != done/error.

Job lifecycle: pending → running → done | error
TTL: 60 minuta (čišćenje po svakom upisu)
"""
import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException
from shared.deps import get_current_user

logger = logging.getLogger("vindex.jobs")
router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# ─── In-memory store ──────────────────────────────────────────────────────────
_JOB_TTL_S = 3600  # 60 minuta

_jobs: dict[str, dict] = {}


def _cleanup():
    now = time.time()
    stale = [jid for jid, j in _jobs.items() if now - j["created_at"] > _JOB_TTL_S]
    for jid in stale:
        del _jobs[jid]


def create_job(user_id: str, tip: str, dedupe_key: Optional[str] = None) -> str:
    """Kreira novi posao i vraća job_id.

    P1-A (2026-08-08): with `dedupe_key`, an identical request that is already
    pending or running returns THAT job instead of starting a second one.

    Why this endpoint shape needs it: /kompletna-analiza answers 202 instantly
    and charges 6 credits from inside the background task, once the work
    finishes. A double-click, an impatient re-submit, or any client retry of the
    202 therefore started a second full analysis and billed a second 6 credits
    for one lawyer action -- 12 credits, two identical answers, no way to tell
    afterwards that it happened.

    SCOPE, stated honestly: _jobs is per-process. This dedupes within one worker
    only. That is not a weaker guarantee than the feature it protects -- the job
    store itself is per-process, so GET /api/jobs/{id} can only ever be answered
    by the worker that created the job. Whatever makes polling work makes this
    work. A cross-worker guarantee needs the DB-backed dedupe_key pattern used
    in migrations 099/101, which is a schema change and deliberately not bundled
    in here.
    """
    return create_job_deduped(user_id, tip, dedupe_key)[0]


def create_job_deduped(user_id: str, tip: str, dedupe_key: Optional[str] = None) -> tuple[str, bool]:
    """As create_job, but also reports whether an existing job was reused.

    The caller MUST know: on a reuse it must not schedule the background task a
    second time, or the dedupe accomplishes nothing.
    """
    _cleanup()

    if dedupe_key:
        for j in _jobs.values():
            if (
                j["user_id"] == user_id
                and j["tip"] == tip
                and j.get("dedupe_key") == dedupe_key
                and j["status"] in ("pending", "running")
            ):
                logger.info(
                    "[JOB] dedupe pogodak %s tip=%s user=%s — vraćam postojeći posao umesto novog",
                    j["id"][:8], tip, user_id[:8],
                )
                return j["id"], True

    jid = str(uuid.uuid4())
    _jobs[jid] = {
        "dedupe_key": dedupe_key,
        "id":         jid,
        "user_id":    user_id,
        "tip":        tip,
        "status":     "pending",
        "result":     None,
        "error":      None,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    logger.info("[JOB] kreiran %s tip=%s user=%s", jid[:8], tip, user_id[:8])
    return jid, False


def update_job(jid: str, status: str, result: Any = None, error: str = None):
    if jid not in _jobs:
        return
    _jobs[jid].update({"status": status, "result": result, "error": error, "updated_at": time.time()})
    logger.info("[JOB] %s → %s", jid[:8], status)


def get_job(jid: str, user_id: str) -> Optional[dict]:
    j = _jobs.get(jid)
    if j and j["user_id"] == user_id:
        return j
    return None


# ─── Runner ───────────────────────────────────────────────────────────────────

async def run_in_background(jid: str, coro_factory: Callable, *args, **kwargs):
    """Pokreće korutinu i upisuje rezultat/grešku u job store."""
    update_job(jid, "running")
    try:
        result = await coro_factory(*args, **kwargs)
        update_job(jid, "done", result=result)
    except Exception as exc:
        logger.exception("[JOB] %s greška: %s", jid[:8], exc)
        update_job(jid, "error", error=str(exc))


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{job_id}")
async def poll_job(job_id: str, user=Depends(get_current_user)):
    """
    Poluje status posla.
    Response:
      { id, tip, status: pending|running|done|error, result?, error?, elapsed_s }
    """
    j = get_job(job_id, user["user_id"])
    if not j:
        raise HTTPException(status_code=404, detail="Posao nije pronađen.")
    elapsed = round(time.time() - j["created_at"], 1)
    return {
        "id":       j["id"],
        "tip":      j["tip"],
        "status":   j["status"],
        "result":   j["result"] if j["status"] == "done"  else None,
        "error":    j["error"]  if j["status"] == "error" else None,
        "elapsed_s": elapsed,
    }

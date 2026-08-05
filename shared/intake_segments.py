# -*- coding: utf-8 -*-
"""
Vindex AI — shared/intake_segments.py

Program Intake Sprint 005 (2026-08-05) — Segment Identity + lifecycle
persistence (Phase 4 + Phase 6). This module owns the ONLY table for
segment rows (intake_job_segments, migration 093) — mirrors
shared/intake_queue.py's own job-lifecycle pattern, but scoped one level
down: segments within a job, not jobs within the queue.

Deliberately NOT merged into shared/intake_documents.py: that module owns
document/entity/review persistence (Phase 5, the EXISTING classification
pipeline, unchanged by this sprint); this module owns segment IDENTITY and
STATUS BEFORE a segment is ever classified — a genuinely different question
(a segment can be 'pending' or 'failed' with no intake_documents row at all
yet), not a subset of what intake_documents.py already does.

Only ever populated for a job that segment_document() split into 2+
documents — a job that stayed one whole document writes zero rows here,
by design (see shared/intake_segment.py and migration 093 comments): this
is what keeps the single-document case byte-for-byte identical to
pre-Sprint-005 behavior.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from shared.deps import _get_supa
from shared.intake_segment import Segment

logger = logging.getLogger("vindex.intake_segments")

# Bounded in-process retry count — NOT a cross-run backoff schedule. A full
# claim/backoff RPC (mirroring claim_intake_job's SELECT...FOR UPDATE SKIP
# LOCKED) is genuinely new architecture beyond this sprint's bounded scope
# (see Mission Report, Deferred) — this gives each segment one immediate
# in-process retry within the SAME worker tick before dead-lettering it,
# which is enough to absorb a transient error (a flaky OpenAI call, a
# momentary DB blip) without building the full cross-run machinery.
DEFAULT_MAX_ATTEMPTS = 2


async def create_segments(intake_job_id: str, segments: list[Segment]) -> list[dict]:
    """Bulk-inserts one row per Segment, status='pending'. Only called when
    len(segments) >= 2 (see module docstring) — the caller (shared/
    intake_worker.py) is responsible for that gate; this function itself
    has no opinion on when it's appropriate to call it, only how to persist
    what it's given. Returns the inserted rows (with assigned ids), ordered
    by segment_index, so the caller can zip them back against the original
    Segment list positionally."""
    if not segments:
        return []
    supa = _get_supa()
    rows = [{
        "intake_job_id": intake_job_id,
        "segment_index": idx,
        "start_page": seg.start_page,
        "end_page": seg.end_page,
        "segmentation_reason": seg.reason,
        "segmentation_confidence": seg.confidence,
        "boundary_signals": [
            {"kind": s.kind, "strength": s.strength, "page_number": s.page_number, "detail": s.detail}
            for s in seg.signals
        ],
        "max_attempts": DEFAULT_MAX_ATTEMPTS,
    } for idx, seg in enumerate(segments)]
    res = await asyncio.to_thread(lambda: supa.table("intake_job_segments").insert(rows).execute())
    inserted = res.data or []
    logger.info("[INTAKE_SEGMENTS] job=%s segmented into %d documents", intake_job_id[:8], len(inserted))
    return sorted(inserted, key=lambda r: r["segment_index"])


async def mark_segment_processing(segment_id: str) -> None:
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("intake_job_segments").update({"status": "processing"}).eq("id", segment_id).execute()
    )


async def mark_segment_completed(segment_id: str, document_id: str) -> None:
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("intake_job_segments")
            .update({"status": "completed", "document_id": document_id})
            .eq("id", segment_id)
            .execute()
    )


async def mark_segment_awaiting_review(segment_id: str, document_id: str) -> None:
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("intake_job_segments")
            .update({"status": "awaiting_review", "document_id": document_id})
            .eq("id", segment_id)
            .execute()
    )


async def mark_segment_failed(segment_id: str, error: str, attempts: int, max_attempts: int) -> bool:
    """Records one failed attempt. Returns True if this was the FINAL
    attempt (segment is now dead-lettered, status='failed') so the caller
    knows whether to retry immediately in-process or move on to the next
    segment. Unlike shared/intake_queue.py::mark_job_failed, there is no
    next_retry_at / backoff here — retries happen immediately, within the
    same worker tick, because the whole point of per-segment isolation
    (Phase 6) is that a slow cross-run retry for ONE segment must never
    delay or block its siblings, which have already been processed by the
    time this is called."""
    new_attempts = attempts + 1
    is_dead_letter = new_attempts >= max_attempts
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("intake_job_segments")
            .update({
                "status": "failed" if is_dead_letter else "pending",
                "attempts": new_attempts,
                "last_error": str(error)[:500],
            })
            .eq("id", segment_id)
            .execute()
    )
    if is_dead_letter:
        logger.error("[INTAKE_SEGMENTS] segment=%s dead-lettered posle %d pokušaja: %s", segment_id[:8], new_attempts, error)
    else:
        logger.warning("[INTAKE_SEGMENTS] segment=%s pokušaj %d/%d neuspešan, odmah ponovni pokušaj: %s", segment_id[:8], new_attempts, max_attempts, error)
    return is_dead_letter


async def get_segments_for_job(intake_job_id: str) -> list[dict]:
    supa = _get_supa()
    res = await asyncio.to_thread(
        lambda: supa.table("intake_job_segments")
            .select("*")
            .eq("intake_job_id", intake_job_id)
            .order("segment_index")
            .execute()
    )
    return res.data or []


def any_segment_needs_attention(segment_rows: list[dict]) -> bool:
    """Pure function over already-fetched rows — a job with 2+ segments
    needs human review if ANY segment ended up 'awaiting_review' or
    'failed' (dead-lettered). This collapses what Fork C's design proposed
    as a distinct 'partially_failed' job status into the EXISTING
    'awaiting_review' status (shared/intake_queue.py's _tick() already
    knows how to route there) — a deliberate, bounded simplification for
    this sprint, not an oversight. See Mission Report, Deferred, for why a
    true partially_failed status (and whether finalize_intake_job may ever
    create a case from one) is left as an open founder decision."""
    return any(r["status"] in ("awaiting_review", "failed") for r in segment_rows)


# ─── Program Intake Sprint 006 (2026-08-05) — Ownership Resolution lifecycle ──
#
# assimilation_status (migration 094) is orthogonal to this file's own
# classification-lifecycle `status` column above — a segment reaches
# 'completed' (classification) before Ownership Resolution ever runs; these
# 4 functions own ONLY the second, later question: does this classified
# document belong to a specific case/client. Two-column, two-owner design,
# same reasoning Sprint 005 itself used to keep identity fields off
# intake_documents.

async def get_segment_for_document(document_id: str) -> Optional[dict]:
    """Program Intake Sprint 006 — the lineage lookup finalize_intake_job
    needs to find a document's own page range (for per-segment text
    slicing) and its intake_job_segments.id (for the new
    predmet_dokumenti.source_intake_job_segment_id FK, migration 094).
    Returns None for a single-document job (Sprint 005's own invariant: no
    intake_job_segments rows exist at all when a job never segmented) —
    callers must treat None as "this document has no segment lineage to
    record," not as an error."""
    supa = _get_supa()
    res = await asyncio.to_thread(
        lambda: supa.table("intake_job_segments").select("*").eq("document_id", document_id).maybe_single().execute()
    )
    return res.data if res else None


async def mark_assimilation_resolved(segment_id: str) -> None:
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("intake_job_segments").update({"assimilation_status": "resolved"}).eq("id", segment_id).execute()
    )


async def mark_assimilation_review_required(segment_id: str, reason: str) -> None:
    """reason is logged, not persisted onto this row (this table has no
    free-text reason column of its own for this lifecycle) — the actual
    human-facing review reason lives on the intake_review_queue /
    predmet_dokumenti / HTTP-response layer that raised this outcome; this
    status flip only marks that this segment's OWNERSHIP (not classification)
    needs a human decision."""
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("intake_job_segments").update({"assimilation_status": "review_required"}).eq("id", segment_id).execute()
    )
    logger.info("[INTAKE_SEGMENTS] segment=%s assimilation review_required: %s", segment_id[:8], reason)


async def mark_assimilation_failed(segment_id: str, error: str) -> None:
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("intake_job_segments").update({"assimilation_status": "failed", "last_error": str(error)[:500]}).eq("id", segment_id).execute()
    )
    logger.warning("[INTAKE_SEGMENTS] segment=%s assimilation failed: %s", segment_id[:8], error)

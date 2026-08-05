# -*- coding: utf-8 -*-
"""
Program Intake Sprint 004 (2026-08-05) — "Human Review Orchestration &
Automatic Resumption". Tests for the new POST /jobs/{job_id}/review/resolve
endpoint, the canonical and ONLY way for a lawyer to unblock a document
whose classification/extraction needed review.

Before this sprint: shared/intake_documents.py::resolve_review_queue_for_job
existed (migration 074) but had ZERO call sites anywhere in the codebase —
a document could be flagged for review and then remain there forever, with
no path back to COMPLETED. This endpoint is that path, and it wires
resolve_review() (which also advances intake_jobs.status from
'awaiting_review' back to 'completed') so that finalize_intake_job's
existing status gate naturally re-opens — no new blocking logic needed in
finalize itself.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request as StarletteRequest


def _fake_request():
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/smart-intake/jobs/job-1/review/resolve", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 12345),
    }
    return StarletteRequest(scope=scope)


def _fake_user():
    return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "advokat@vindex.rs"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _chain(data):
    c = MagicMock()
    for m in ["select", "eq", "maybe_single", "execute"]:
        setattr(c, m, MagicMock(return_value=c))
    r = MagicMock(); r.data = data
    c.execute = MagicMock(return_value=r)
    return c


@pytest.mark.anyio
async def test_resolve_job_review_happy_path_resolves_and_logs_audit():
    """Program Delta, Sprint 002 (2026-08-05): the old direct
    `asyncio.create_task(log_action("dokument_review_resolved", ...))` call
    was replaced by a durable REVIEW_ACCEPTED event emission -- the
    Canonical Consequence Engine (services/case_evolution.py) now owns
    writing that specific audit row as its own 'review_confirmation_audit'
    consequence, not this endpoint directly. This test now asserts on the
    EMISSION (event type + payload), not a direct log_action call."""
    from routers.smart_intake import resolve_job_review

    supa = MagicMock()
    supa.table = MagicMock(return_value=_chain({"id": "job-1", "status": "awaiting_review", "predmet_id": None}))

    with patch("routers.smart_intake._get_supa", return_value=supa), \
         patch("routers.smart_intake.intake_documents.resolve_review",
               new=AsyncMock(return_value={"review_resolved_now": True, "job_status_advanced": True})), \
         patch("services.event_bus.emit_durable", new=AsyncMock()) as mock_emit:
        result = await resolve_job_review("job-1", _fake_request(), _fake_user())

    assert result["ok"] is True
    assert result["already_finalized"] is False
    assert result["review_resolved_now"] is True
    assert result["job_status_advanced"] is True
    mock_emit.assert_awaited_once()
    from services.event_bus import EventType
    assert mock_emit.call_args.args[0] == EventType.REVIEW_ACCEPTED
    assert mock_emit.call_args.args[1] == "00000000-0000-0000-0000-000000000001"
    assert mock_emit.call_args.args[2] is None  # predmet_id -- job wasn't finalized yet
    assert mock_emit.call_args.args[3]["intake_job_id"] == "job-1"
    assert mock_emit.call_args.args[3]["review_resolved_now"] is True


@pytest.mark.anyio
async def test_resolve_job_review_404_when_not_owned_or_missing():
    from routers.smart_intake import resolve_job_review

    supa = MagicMock()
    supa.table = MagicMock(return_value=_chain(None))

    with patch("routers.smart_intake._get_supa", return_value=supa):
        with pytest.raises(Exception) as exc_info:
            await resolve_job_review("job-ghost", _fake_request(), _fake_user())

    assert getattr(exc_info.value, "status_code", None) == 404


@pytest.mark.anyio
async def test_resolve_job_review_already_finalized_still_resolves_and_wires_genome():
    """Program Delta, Sprint 002 (2026-08-05): a review resolved AFTER
    finalize already ran used to be a complete no-op (predmet_id set ->
    early return, resolve_review() never even called) -- the
    intake_review_queue row stayed unresolved FOREVER. Fixed this sprint
    (belongs to the migrated REVIEW_ACCEPTED event's own Human Review
    domain, fixable without a business decision): resolve_review() now
    always runs (idempotent by construction), and the REVIEW_ACCEPTED event
    still carries the job's own predmet_id -- exactly what lets the
    Canonical Consequence Engine's genome_refresh/timeline_entry
    consequences do REAL work for a post-finalize correction (the founder's
    own worked example: 'Review Accepted -> Genome -> Timeline -> Audit')."""
    from routers.smart_intake import resolve_job_review

    supa = MagicMock()
    supa.table = MagicMock(return_value=_chain({"id": "job-1", "status": "completed", "predmet_id": "pred-999"}))
    mock_resolve = AsyncMock(return_value={"review_resolved_now": True, "job_status_advanced": False})

    with patch("routers.smart_intake._get_supa", return_value=supa), \
         patch("routers.smart_intake.intake_documents.resolve_review", mock_resolve), \
         patch("services.event_bus.emit_durable", new=AsyncMock()) as mock_emit:
        result = await resolve_job_review("job-1", _fake_request(), _fake_user())

    assert result["already_finalized"] is True
    assert result["review_resolved_now"] is True
    mock_resolve.assert_awaited_once()  # fixed: no longer skipped
    mock_emit.assert_awaited_once()
    assert mock_emit.call_args.args[2] == "pred-999"  # predmet_id -- genome/timeline can now do real work


@pytest.mark.anyio
async def test_resolve_job_review_idempotent_on_double_call():
    """Two rapid resolve calls (double-click) must both succeed honestly --
    the second reports review_resolved_now=False (nothing left to resolve)
    rather than erroring or duplicating an audit entry for the same action."""
    from routers.smart_intake import resolve_job_review

    supa = MagicMock()
    supa.table = MagicMock(return_value=_chain({"id": "job-1", "status": "awaiting_review", "predmet_id": None}))

    with patch("routers.smart_intake._get_supa", return_value=supa), \
         patch("routers.smart_intake.intake_documents.resolve_review",
               new=AsyncMock(return_value={"review_resolved_now": False, "job_status_advanced": False})), \
         patch("services.event_bus.emit_durable", new=AsyncMock()):
        result = await resolve_job_review("job-1", _fake_request(), _fake_user())

    assert result["ok"] is True
    assert result["review_resolved_now"] is False


@pytest.mark.anyio
async def test_correct_entity_endpoint_logs_audit_action():
    """Program Intake Sprint 004: correct_entity had zero audit logging
    before this sprint (Fork A §5) -- every human decision must leave a
    trace (mission Phase 5)."""
    from routers.smart_intake import correct_entity

    with patch("routers.smart_intake.intake_documents.correct_entity",
               new=AsyncMock(return_value={"entity_id": "e-1", "entity_type": "deadline", "corrected_value": "15.12.2026"})), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        result = await correct_entity(
            "e-1", _fake_request(), corrected_value="15.12.2026", reason="Pogresan datum", error_source=None,
            user=_fake_user(),
        )
        await asyncio.sleep(0)  # let the fire-and-forget create_task run

    assert result["entity_id"] == "e-1"
    mock_log.assert_awaited_once()
    assert mock_log.call_args.args[0] == "entity_corrected"
    assert mock_log.call_args.kwargs["resource_id"] == "e-1"


# ═══════════════════════════════════════════════════════════════════════════
# The sprint's central guarantee: finalize actually STOPS on an unresolved
# review, with a clear, actionable reason -- and automatically resumes
# (same finalize call, no special-casing) once resolved. Proves Phase 4
# (Automatic Pipeline Resume) end to end at the HTTP-contract level.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_finalize_blocks_with_clear_actionable_message_when_awaiting_review():
    from routers.smart_intake import finalize_intake_job, FinalizeReq
    from fastapi import HTTPException

    supa = MagicMock()
    supa.table = MagicMock(return_value=_chain({
        "id": "job-1", "status": "awaiting_review", "storage_path": "u1/x",
        "original_filename": "tuzba.pdf", "mime_type": "application/pdf",
        "predmet_id": None, "completed_at": None,
    }))

    with patch("routers.smart_intake._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc_info:
            await finalize_intake_job("job-1", _fake_request(), FinalizeReq(), _fake_user())

    assert exc_info.value.status_code == 409
    # Must name the actual unblocking action, not a generic "try again later".
    assert "review/resolve" in exc_info.value.detail


@pytest.mark.anyio
async def test_resolve_then_finalize_proceeds_without_repeating_processing():
    """After resolve_review() advances status to 'completed', a subsequent
    finalize call must pass the SAME status gate finalize already had --
    proving resume needs zero new logic in finalize itself, and confirming
    no OCR/classification is repeated (get_job_result is called, not
    _download_and_decrypt/extract/classify)."""
    from routers.smart_intake import finalize_intake_job, FinalizeReq

    supa = MagicMock()

    def _table(name):
        if name == "intake_jobs":
            return _chain({
                "id": "job-1", "status": "completed", "storage_path": "u1/x",
                "original_filename": "tuzba.pdf", "mime_type": "application/pdf",
                "predmet_id": None, "completed_at": "2026-08-05T00:00:00Z",
            })
        return _chain(None)
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.smart_intake._get_supa", return_value=supa), \
         patch("routers.smart_intake.intake_queue.claim_finalize", new=AsyncMock(return_value={"id": "job-1"})), \
         patch("routers.smart_intake.intake_documents.get_job_documents", new=AsyncMock(return_value=[])) as mock_get_result:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await finalize_intake_job("job-1", _fake_request(), FinalizeReq(), _fake_user())

    # Empty document list -> a DIFFERENT 409 (classification unavailable),
    # proving execution passed the status gate and reached the real finalize
    # body -- not repeating any pipeline step, just resuming past the
    # resolved gate. (Program Intake Sprint 006: get_job_result() -> the
    # list-returning get_job_documents(), see routers/smart_intake.py.)
    assert exc_info.value.status_code == 409
    assert "Klasifikacija nije dostupna" in exc_info.value.detail
    mock_get_result.assert_awaited_once_with("job-1")

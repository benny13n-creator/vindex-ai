# -*- coding: utf-8 -*-
"""
Program Intake Sprint 002 (2026-08-05) — regression tests for Pipeline C
(routers/smart_intake.py::finalize_intake_job)'s atomic claim fix.

This is the sprint's single most severe finding, independently confirmed by
all 3 investigation forks the same day (Fork A §C-bonus, Fork B §3.4, Fork C
Phase 5 #4): the endpoint's own idempotency guard read `intake_jobs.
predmet_id`, but that column was only written as the LAST, unwrapped
statement in the function, after 6-8 other independently-committed writes
(predmet, client, deadline, document, Pinecone vectors) had already run. Two
finalize calls for the same job_id close enough together (double-click, or a
frontend timeout retry while the first call is still running) both read
predmet_id=NULL, both pass the guard, and both run the entire body
independently -- silently duplicating a full legal case.

Fix: `claim_intake_finalize` RPC (migration 092) atomically claims the
finalize slot BEFORE any side effects run, mirroring `claim_intake_job`'s own
SELECT...FOR UPDATE SKIP LOCKED pattern. `shared/intake_queue.py::claim_finalize`
wraps it; `finalize_intake_job` now calls it right after the status check and
before any predmet/client/document/Pinecone work begins.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request as StarletteRequest


def _fake_user():
    return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "advokat@vindex.rs"}


def _fake_request():
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/smart-intake/jobs/job-1/finalize", "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _completed_job(job_id="job-1", predmet_id=None):
    return {
        "id": job_id, "status": "completed", "storage_path": "u1/abc",
        "original_filename": "tuzba.pdf", "mime_type": "application/pdf",
        "predmet_id": predmet_id, "completed_at": "2026-08-05T10:00:00Z",
    }


@pytest.mark.anyio
async def test_claim_fails_and_predmet_already_set_returns_already_finalized():
    """Sequential retry AFTER the first call already fully succeeded: the
    claim correctly fails (predmet_id is no longer NULL), and the endpoint
    must return the existing predmet_id, not attempt to re-run anything."""
    from routers.smart_intake import finalize_intake_job, FinalizeReq

    job = _completed_job(predmet_id=None)  # initial fetch is pre-claim-check
    job_select_chain = MagicMock()
    job_select_chain.data = job

    refetch_chain = MagicMock()
    refetch_chain.data = {"predmet_id": "predmet-already-created-1", "assimilation_complete": True}

    mock_supa = MagicMock()

    def _table(name):
        c = MagicMock()
        if name == "intake_jobs":
            # First call in the function body fetches the job; the SECOND
            # call (only reached if the claim fails) re-fetches predmet_id.
            c.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = job_select_chain
            c.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = refetch_chain
        return c

    mock_supa.table = MagicMock(side_effect=_table)

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("routers.smart_intake.intake_queue.claim_finalize", new=AsyncMock(return_value=None)):
        result = await finalize_intake_job(
            "job-1", _fake_request(), FinalizeReq(), user=_fake_user(),
        )

    assert result["ok"] is True
    assert result["predmet_id"] == "predmet-already-created-1"
    assert result["already_finalized"] is True


@pytest.mark.anyio
async def test_claim_fails_and_predmet_not_yet_set_returns_409_in_progress():
    """Concurrent double-click / timeout-retry WHILE the first call is still
    running: the claim correctly fails (another finalize's claim is fresh),
    but predmet_id is still NULL -- this must be reported as 'in progress',
    a distinct, honest outcome from 'already finalized', not silently
    treated the same way and not allowed to fall through and duplicate."""
    from routers.smart_intake import finalize_intake_job, FinalizeReq
    from fastapi import HTTPException

    job = _completed_job(predmet_id=None)
    job_select_chain = MagicMock(data=job)
    refetch_chain = MagicMock(data={"predmet_id": None})

    mock_supa = MagicMock()

    def _table(name):
        c = MagicMock()
        if name == "intake_jobs":
            c.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = job_select_chain
            c.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = refetch_chain
        return c

    mock_supa.table = MagicMock(side_effect=_table)

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("routers.smart_intake.intake_queue.claim_finalize", new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc_info:
            await finalize_intake_job("job-1", _fake_request(), FinalizeReq(), user=_fake_user())

    assert exc_info.value.status_code == 409
    assert "toku" in exc_info.value.detail.lower()  # "already in progress", not a silent no-op or duplicate


@pytest.mark.anyio
async def test_claim_succeeds_proceeds_to_run_the_finalize_body():
    """The winning call: claim succeeds, so the function must proceed past
    the guard into the real work (verified here by confirming it goes on to
    read intake_documents.get_job_result, the very next real step)."""
    from routers.smart_intake import finalize_intake_job, FinalizeReq
    from fastapi import HTTPException

    job = _completed_job(predmet_id=None)
    job_select_chain = MagicMock(data=job)

    mock_supa = MagicMock()

    def _table(name):
        c = MagicMock()
        if name == "intake_jobs":
            c.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = job_select_chain
        return c
    mock_supa.table = MagicMock(side_effect=_table)

    # Program Intake Sprint 006 (2026-08-05): get_job_result() was replaced by
    # the list-returning get_job_documents() (Sprint 005 segmented jobs can
    # have 2+ documents, which get_job_result's own .maybe_single() could not
    # handle). An empty list is the equivalent "no classification available"
    # signal this test exercises.
    mock_get_job_documents = AsyncMock(return_value=[])

    with patch("routers.smart_intake._get_supa", return_value=mock_supa), \
         patch("routers.smart_intake.intake_queue.claim_finalize", new=AsyncMock(return_value={"id": "job-1", "finalizing_at": "now"})), \
         patch("routers.smart_intake.intake_documents.get_job_documents", new=mock_get_job_documents):
        # An empty document list triggers a 409 further down the real function
        # body -- proves execution reached past the claim guard into real
        # logic, not that the whole flow succeeds end-to-end (out of scope).
        with pytest.raises(HTTPException) as exc_info:
            await finalize_intake_job("job-1", _fake_request(), FinalizeReq(), user=_fake_user())

    mock_get_job_documents.assert_awaited_once_with("job-1")
    assert exc_info.value.status_code == 409
    assert "klasifikacija" in exc_info.value.detail.lower()

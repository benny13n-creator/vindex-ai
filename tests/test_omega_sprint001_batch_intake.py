# -*- coding: utf-8 -*-
"""
Program Omega, Master Sprint 001 (2026-08-06) — "From Document Upload to
Complete Case Intelligence". Priority 1's own named scenario: a lawyer
uploads a large folder (up to 500 documents) and expects the system to
organize it automatically, not require 500 manual clicks.

Tests here cover the 2 concrete fixes this sprint made to close the gap
between "one document, one manual flow" and "a folder, one outcome":

1. `upload_intake_documents`'s own time-budget break — large batches must
   return a clean, resumable partial response instead of risking a
   gunicorn worker-timeout mid-batch (OCR_AND_INTAKE_CAPACITY_REPORT.md's
   own headline finding).
2. `POST /jobs/finalize-batch` — a new endpoint that finalizes N jobs as
   ONE operation and returns ONE aggregate summary, reusing
   `_finalize_intake_job_core` per job unchanged (no new AI/Genome/Evidence
   capability, pure orchestration).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.datastructures import Headers
from starlette.requests import Request as StarletteRequest
from fastapi import UploadFile, HTTPException


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_user():
    return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "advokat@vindex.rs"}


def _fake_request(path="/api/smart-intake/documents"):
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": path, "app": MagicMock(), "state": MagicMock(), "client": ("127.0.0.1", 1),
    }
    return StarletteRequest(scope=scope)


def _upload_file(name: str, content: bytes = b"%PDF-1.4 fake pdf bytes") -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(content), headers=Headers({"content-type": "application/pdf"}))


def _make_upload_supa():
    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "intake_jobs":
            # No existing job for any idempotency_key -- every file is new.
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        return t
    supa.table.side_effect = _table
    supa.storage.from_.return_value.upload.return_value = None
    return supa


# ═══════════════════════════════════════════════════════════════════════════
# Time-budget break — large batch upload
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_upload_batch_stops_early_when_time_budget_exceeded_and_reports_remaining():
    """Simulates a large batch where the time budget runs out partway
    through -- must stop cleanly, report what succeeded, and honestly list
    the remaining filenames so the frontend can resubmit them, instead of
    risking a gunicorn timeout kill with no response at all. Uses a REAL
    tiny time budget + a real tiny per-file delay (not a mocked clock --
    time.monotonic() is a genuinely global, shared function other code
    calls too, so patching it directly is fragile/coupled to internals)."""
    import asyncio as _asyncio
    from routers import smart_intake as si

    supa = _make_upload_supa()
    files = [_upload_file(f"dok_{i}.pdf") for i in range(5)]

    async def _slow_enqueue(**kw):
        await _asyncio.sleep(0.03)
        return "job-" + kw["idempotency_key"][-4:]

    with patch("routers.smart_intake._get_supa", return_value=supa), \
         patch("routers.smart_intake.intake_queue.enqueue_job", new=AsyncMock(side_effect=_slow_enqueue)), \
         patch.object(si, "_UPLOAD_TIME_BUDGET_S", 0.05), \
         patch("routers.smart_intake._encrypt", return_value=b"ENCRYPTED"):
        result = await si.upload_intake_documents(_fake_request(), files, _fake_user())

    assert result["ukupno"] == 5
    assert result["nastavlja"] is True
    # At least 1 file processed before the budget tripped, and NOT all 5 --
    # the exact count depends on real elapsed wall-clock time, deliberately
    # not pinned to a fragile exact number.
    assert 1 <= len(result["rezultati"]) < 5
    assert result["preostali_fajlovi"] == [f.filename for f in files][len(result["rezultati"]):]
    assert all(r["ok"] for r in result["rezultati"])


@pytest.mark.anyio
async def test_upload_batch_within_time_budget_processes_everything_normally():
    """The common case (small/medium batch) must be completely unaffected
    -- nastavlja=False, all files processed, no behavior change."""
    from routers.smart_intake import upload_intake_documents

    supa = _make_upload_supa()
    files = [_upload_file(f"dok_{i}.pdf") for i in range(3)]

    with patch("routers.smart_intake._get_supa", return_value=supa), \
         patch("routers.smart_intake.intake_queue.enqueue_job", new=AsyncMock(side_effect=lambda **kw: "job-" + kw["idempotency_key"][-4:])), \
         patch("routers.smart_intake._encrypt", return_value=b"ENCRYPTED"):
        result = await upload_intake_documents(_fake_request(), files, _fake_user())

    assert result["ukupno"] == 3
    assert result["nastavlja"] is False
    assert result["preostali_fajlovi"] == []
    assert len(result["rezultati"]) == 3
    assert all(r["ok"] for r in result["rezultati"])


# ═══════════════════════════════════════════════════════════════════════════
# Batch finalize — aggregate summary
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_finalize_batch_aggregates_multiple_jobs_into_one_case_summary():
    """3 jobs, 2 of which land in the SAME predmet_id (e.g. all part of one
    client's folder), 1 flagged for review -- the aggregate summary must
    show ONE row for the shared case with the right document count, not 2
    separate 'successes' with no case-level context."""
    from routers.smart_intake import finalize_intake_jobs_batch, BatchFinalizeReq

    async def _fake_core(job_id, request, body, user, emit_document_accepted=True):
        if job_id == "job-1":
            return {"ok": True, "predmet_id": "pred-A", "naziv": "Markovic", "dokumenata_povezano": 1,
                     "klasifikacija_nesigurna": False, "rok_dodat": True, "already_finalized": False}
        if job_id == "job-2":
            return {"ok": True, "predmet_id": "pred-A", "naziv": "Markovic", "dokumenata_povezano": 1,
                     "klasifikacija_nesigurna": True, "rok_dodat": False, "already_finalized": False}
        if job_id == "job-3":
            return {"ok": True, "predmet_id": "pred-B", "naziv": "Petrovic", "dokumenata_povezano": 2,
                     "klasifikacija_nesigurna": False, "rok_dodat": False, "already_finalized": False}
        raise AssertionError(f"unexpected job_id {job_id}")

    pre_supa = MagicMock()
    pre_supa.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"case_dna": {}}

    with patch("routers.smart_intake._finalize_intake_job_core", new=AsyncMock(side_effect=_fake_core)), \
         patch("routers.smart_intake._get_supa", return_value=pre_supa), \
         patch("services.event_bus.emit_durable", new=AsyncMock()) as mock_emit:
        result = await finalize_intake_jobs_batch(
            BatchFinalizeReq(job_ids=["job-1", "job-2", "job-3"]), _fake_request(), _fake_user(),
        )

    assert result["ukupno_poslato"] == 3
    assert result["uspesno_finalizovano"] == 3
    assert result["neuspesno"] == 0
    assert result["dokumenata_povezano_ukupno"] == 4
    assert result["dokumenti_za_proveru"] == 1
    assert result["rokovi_dodati"] == 1
    predmeti_by_id = {p["predmet_id"]: p for p in result["predmeti_pogodjeni"]}
    assert predmeti_by_id["pred-A"]["dokumenata"] == 2  # job-1 + job-2 merged into ONE row
    assert predmeti_by_id["pred-B"]["dokumenata"] == 2
    assert len(result["predmeti_pogodjeni"]) == 2  # not 3 -- pred-A deduplicated
    assert "napomena_genome" in result
    # Program Omega, Sprint 002 -- one DOCUMENT_BATCH_COMPLETED emission per
    # unique predmet_id, never per job (2 cases touched, not 3 jobs).
    assert mock_emit.await_count == 2
    from services.event_bus import EventType
    emitted_predmeti = {c.args[2] for c in mock_emit.call_args_list}
    assert emitted_predmeti == {"pred-A", "pred-B"}
    assert all(c.args[0] == EventType.DOCUMENT_BATCH_COMPLETED for c in mock_emit.call_args_list)
    pred_a_call = next(c for c in mock_emit.call_args_list if c.args[2] == "pred-A")
    assert pred_a_call.args[3]["dokumenata_dodato"] == 2
    assert pred_a_call.args[3]["dokumenti_za_proveru"] == 1
    assert pred_a_call.args[3]["rokovi_dodati"] == 1
    assert set(pred_a_call.args[3]["job_ids"]) == {"job-1", "job-2"}
    assert result["batch_status"] == "completed"
    assert result["affected_cases"] == 2
    assert result["refresh_required"] is True
    assert all(p["refresh_zakazan"] for p in result["predmeti_pogodjeni"])


@pytest.mark.anyio
async def test_finalize_batch_one_failure_does_not_abort_the_rest():
    """A single bad job_id (404, or any other finalize-time error) must not
    prevent the OTHER jobs in the batch from being finalized -- same
    failure-isolation principle finalize_intake_job already uses per
    document, now proven at the batch level too."""
    from routers.smart_intake import finalize_intake_jobs_batch, BatchFinalizeReq

    async def _fake_core(job_id, request, body, user, emit_document_accepted=True):
        if job_id == "job-bad":
            raise HTTPException(status_code=404, detail="Posao nije pronađen.")
        return {"ok": True, "predmet_id": "pred-A", "naziv": "Markovic", "dokumenata_povezano": 1,
                "klasifikacija_nesigurna": False, "rok_dodat": False, "already_finalized": False}

    pre_supa = MagicMock()
    pre_supa.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"case_dna": {}}

    with patch("routers.smart_intake._finalize_intake_job_core", new=AsyncMock(side_effect=_fake_core)), \
         patch("routers.smart_intake._get_supa", return_value=pre_supa), \
         patch("services.event_bus.emit_durable", new=AsyncMock()):
        result = await finalize_intake_jobs_batch(
            BatchFinalizeReq(job_ids=["job-1", "job-bad", "job-2"]), _fake_request(), _fake_user(),
        )

    assert result["uspesno_finalizovano"] == 2
    assert result["neuspesno"] == 1
    bad_detail = next(d for d in result["detalji"] if d["job_id"] == "job-bad")
    assert bad_detail["ok"] is False
    assert "nije pronađen" in bad_detail["greska"]


@pytest.mark.anyio
async def test_finalize_batch_does_not_hit_per_job_rate_limit():
    """The whole reason _finalize_intake_job_core exists as an undecorated
    function: calling the RATE-LIMITED finalize_intake_job directly in a
    loop would trip its own 20/minute limit partway through any batch
    bigger than 20. This test proves the batch endpoint calls the
    UNDECORATED core, not the decorated wrapper, for a batch of 30 (bigger
    than the single-job endpoint's own 20/minute limit)."""
    from routers.smart_intake import finalize_intake_jobs_batch, BatchFinalizeReq

    call_count = {"n": 0}
    async def _fake_core(job_id, request, body, user, emit_document_accepted=True):
        call_count["n"] += 1
        return {"ok": True, "predmet_id": f"pred-{job_id}", "naziv": "X", "dokumenata_povezano": 1,
                "klasifikacija_nesigurna": False, "rok_dodat": False, "already_finalized": False}

    pre_supa = MagicMock()
    pre_supa.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"case_dna": {}}

    job_ids = [f"job-{i}" for i in range(30)]
    with patch("routers.smart_intake._finalize_intake_job_core", new=AsyncMock(side_effect=_fake_core)), \
         patch("routers.smart_intake._get_supa", return_value=pre_supa), \
         patch("services.event_bus.emit_durable", new=AsyncMock()):
        result = await finalize_intake_jobs_batch(BatchFinalizeReq(job_ids=job_ids), _fake_request(), _fake_user())

    assert call_count["n"] == 30
    assert result["uspesno_finalizovano"] == 30


@pytest.mark.anyio
async def test_finalize_wrapper_still_delegates_to_core_unchanged():
    """The single-job HTTP endpoint (finalize_intake_job) must still behave
    identically after the extraction -- it's a pure pass-through to
    _finalize_intake_job_core, zero logic difference."""
    from routers.smart_intake import finalize_intake_job, FinalizeReq

    sentinel = {"ok": True, "predmet_id": "pred-X"}
    user = _fake_user()
    body = FinalizeReq()
    with patch("routers.smart_intake._finalize_intake_job_core", new=AsyncMock(return_value=sentinel)) as mock_core:
        result = await finalize_intake_job("job-1", _fake_request(), body, user)

    assert result is sentinel
    mock_core.assert_awaited_once()
    assert mock_core.call_args.args[0] == "job-1"
    assert mock_core.call_args.args[2] is body
    assert mock_core.call_args.args[3] == user

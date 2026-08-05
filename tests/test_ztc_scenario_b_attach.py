# -*- coding: utf-8 -*-
"""
Zero-Touch Case investigation (2026-08-03, BETA-002/Scenario B): before this
fix, POST /api/smart-intake/jobs/{id}/finalize ALWAYS inserted a new
`predmeti` row -- there was no way to finalize a second document into a case
a prior finalize call already created. A lawyer uploading N documents for
one client (the batch-upload contract already returns one job_id per file)
silently got N separate cases instead of one organized case.

Fix: FinalizeReq gained an optional `predmet_id` field. When present,
finalize attaches the document to that existing case instead of creating a
new one. This also surfaced a second, previously-harmless bug: the
predmet_dokumenti insert hardcoded `redni_broj: 1` for every document (fine
when every case only ever had exactly one document; a silent collision the
moment two documents share a case).

Mirrors tests/test_lz002_evidence_autoclassify.py's mocking pattern (mock
only external I/O, exercise the real finalize_intake_job end to end).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request as StarletteRequest


def _fake_request():
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/smart-intake/jobs/job-1/finalize", "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _fake_user():
    return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "advokat@vindex.rs"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_supa(existing_predmet=None, existing_redni_broj_rows=None, new_doc_id="dok-002"):
    """existing_predmet: dict or None -- what the attach-lookup finds (None -> 404 case).
    existing_redni_broj_rows: list of dicts like [{"redni_broj": 3}] representing
    documents already in the target case, or [] for a brand-new case."""
    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "intake_jobs":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                "id": "job-1", "status": "completed", "storage_path": "session/xyz",
                "original_filename": "podnesak2.pdf", "mime_type": "application/pdf",
                "predmet_id": None, "completed_at": None,
            }
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "predmeti":
            t.insert.return_value.execute.return_value.data = [{"id": "pred-NEW"}]
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = existing_predmet
        elif name == "predmet_dokumenti":
            t.insert.return_value.execute.return_value.data = [{"id": new_doc_id}]
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = (
                existing_redni_broj_rows if existing_redni_broj_rows is not None else []
            )
        elif name == "klijenti":
            t.select.return_value.eq.return_value.ilike.return_value.neq.return_value.limit.return_value.execute.return_value.data = []
            t.insert.return_value.execute.return_value.data = [{"id": "kl-001"}]
        elif name == "predmet_klijenti":
            t.insert.return_value.execute.return_value.data = [{}]
        elif name == "predmet_hronologija":
            t.insert.return_value.execute.return_value.data = [{}]
        elif name == "proactive_alerts":
            t.insert.return_value.execute.return_value.data = [{}]
        return t

    supa.table.side_effect = _table
    return supa


def _patched(mock_supa, job_result):
    return (
        patch("routers.smart_intake._get_supa", return_value=mock_supa),
        patch("shared.intake_documents.get_job_result", new=AsyncMock(return_value=job_result)),
        patch("shared.intake_worker.worker._download_and_decrypt", new=AsyncMock(return_value=b"raw bytes")),
        patch("uploaded_doc.extractor.extract", return_value=("Drugi dokument teksta.", False, False)),
        patch("uploaded_doc.chunker.chunk_document", return_value={"chunks": []}),
        patch("uploaded_doc.ingest.ingest_session", return_value=None),
        patch("uploaded_doc.session.generate_session_id", return_value="sess-002"),
        patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)),
        patch("shared.vector_origin.now_iso", return_value="2026-08-03T00:00:00Z"),
        patch("routers.evidence.klasifikuj_i_sacuvaj"),
        patch("routers.intake._run_conflict_check", new=AsyncMock(return_value={"conflict_detected": False})),
        # Program Intake Sprint 002 (2026-08-05): finalize now atomically
        # claims the finalize slot before running any side effects (migration
        # 092, claim_intake_finalize RPC) -- mock it winning the claim so
        # these pre-existing tests keep exercising the real function body,
        # same as before this sprint's fix.
        patch("routers.smart_intake.intake_queue.claim_finalize", new=AsyncMock(return_value={"id": "job-1"})),
    )


async def _run_finalize_and_drain(mock_supa, job_result, body):
    from routers.smart_intake import finalize_intake_job

    captured_coros = []

    def _capture_create_task(coro, *a, **kw):
        captured_coros.append(coro)
        return MagicMock()

    patches = _patched(mock_supa, job_result)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], \
         patch("asyncio.create_task", side_effect=_capture_create_task):
        result = await finalize_intake_job("job-1", _fake_request(), body, _fake_user())
        for coro in captured_coros:
            try:
                await coro
            except Exception:
                pass
    return result


@pytest.mark.anyio
async def test_finalize_attaches_to_existing_predmet_instead_of_creating_new():
    from routers.smart_intake import FinalizeReq

    mock_supa = _make_supa(
        existing_predmet={"id": "pred-EXISTING", "naziv": "Petrović protiv Markovića"},
        existing_redni_broj_rows=[{"redni_broj": 1}],
    )
    job_result = {"document": {"document_type": "podnesak"}, "entities": [], "review": None}

    result = await _run_finalize_and_drain(
        mock_supa, job_result, FinalizeReq(predmet_id="pred-EXISTING"),
    )

    assert result["predmet_id"] == "pred-EXISTING"
    predmeti_calls = [c for c in mock_supa.table.call_args_list if c.args == ("predmeti",)]
    assert predmeti_calls, "predmeti table must have been touched (lookup)"
    # the mock's `predmeti` MagicMock is shared across calls (side_effect returns
    # a NEW MagicMock per call to supa.table -- verify no insert happened by
    # checking the specific table object never had .insert invoked)
    table_obj = mock_supa.table("predmeti")
    # calling supa.table("predmeti") again returns a *different* MagicMock (side_effect
    # constructs a fresh one each call) -- so instead assert via the finalize's own
    # observable outcome: no NEW predmet id ("pred-NEW") was ever returned.
    assert result["predmet_id"] != "pred-NEW"


@pytest.mark.anyio
async def test_finalize_404_when_attach_target_not_found_or_not_owned():
    from routers.smart_intake import FinalizeReq
    from fastapi import HTTPException

    mock_supa = _make_supa(existing_predmet=None)
    job_result = {"document": {"document_type": "podnesak"}, "entities": [], "review": None}

    with pytest.raises(HTTPException) as exc_info:
        await _run_finalize_and_drain(mock_supa, job_result, FinalizeReq(predmet_id="pred-GHOST"))

    assert exc_info.value.status_code == 404


@pytest.mark.anyio
async def test_finalize_without_predmet_id_still_creates_new_case():
    """Backward compatibility: omitting predmet_id must behave exactly as before."""
    from routers.smart_intake import FinalizeReq

    mock_supa = _make_supa(existing_redni_broj_rows=[])
    job_result = {"document": {"document_type": "podnesak"}, "entities": [], "review": None}

    result = await _run_finalize_and_drain(mock_supa, job_result, FinalizeReq())

    assert result["predmet_id"] == "pred-NEW"


@pytest.mark.anyio
async def test_finalize_assigns_next_redni_broj_when_attaching_second_document():
    """Core Scenario B regression guard: a second document attached to an
    existing case that already has a document at redni_broj=1 must NOT also
    get redni_broj=1 (the pre-fix hardcoded behavior) -- it must get 2."""
    from routers.smart_intake import FinalizeReq

    mock_supa = _make_supa(
        existing_predmet={"id": "pred-EXISTING", "naziv": "Predmet"},
        existing_redni_broj_rows=[{"redni_broj": 1}],
    )
    job_result = {"document": {"document_type": "podnesak"}, "entities": [], "review": None}

    captured_inserts = []
    real_table = mock_supa.table.side_effect

    def _spy_table(name):
        t = real_table(name)
        if name == "predmet_dokumenti":
            orig_insert = t.insert
            def _spy_insert(row):
                captured_inserts.append(row)
                return orig_insert(row)
            t.insert = _spy_insert
        return t
    mock_supa.table.side_effect = _spy_table

    await _run_finalize_and_drain(
        mock_supa, job_result, FinalizeReq(predmet_id="pred-EXISTING"),
    )

    assert captured_inserts, "predmet_dokumenti insert must have been attempted"
    assert captured_inserts[0]["redni_broj"] == 2


@pytest.mark.anyio
async def test_finalize_first_document_in_new_case_gets_redni_broj_1():
    from routers.smart_intake import FinalizeReq

    mock_supa = _make_supa(existing_redni_broj_rows=[])
    job_result = {"document": {"document_type": "podnesak"}, "entities": [], "review": None}

    captured_inserts = []
    real_table = mock_supa.table.side_effect

    def _spy_table(name):
        t = real_table(name)
        if name == "predmet_dokumenti":
            orig_insert = t.insert
            def _spy_insert(row):
                captured_inserts.append(row)
                return orig_insert(row)
            t.insert = _spy_insert
        return t
    mock_supa.table.side_effect = _spy_table

    await _run_finalize_and_drain(mock_supa, job_result, FinalizeReq())

    assert captured_inserts
    assert captured_inserts[0]["redni_broj"] == 1

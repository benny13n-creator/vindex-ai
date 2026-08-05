# -*- coding: utf-8 -*-
"""
Program Intake Sprint 006 (2026-08-05) — "Canonical Case Assimilation".
Integration tests for routers/smart_intake.py::finalize_intake_job's new
per-document assimilation loop: content-based case auto-match, conflicting
case numbers across a bundled upload, per-document failure isolation
(Phase 5), and lineage FK continuity (Phase 4).

Mirrors tests/test_ztc_scenario_b_attach.py's mocking pattern (mock only
external I/O, exercise the real finalize_intake_job end to end).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import contextlib
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


def _doc_entry(doc_id, case_number=None, segment_id=None):
    entities = []
    if case_number:
        entities.append({"entity_type": "case_number", "value": case_number, "confidence": 0.95})
    return {
        "document": {"id": doc_id, "document_type": "lawsuit", "classification_confidence": 0.95, "ocr_used": False},
        "entities": entities,
        "review": None,
    }, segment_id


def _make_supa(predmeti_matches=None, segment_map=None, fail_redni_broj=None):
    """predmeti_matches: rows returned by the broj_predmeta lookup (Ownership
    Resolution) when no explicit predmet_id is given.
    segment_map: {document_id: segment_row_dict} for intake_job_segments
    lookups (None entries -> single-document job, no segment).
    fail_redni_broj: set of redni_broj values whose predmet_dokumenti insert
    must fail for EVERY fallback variant -- redni_broj is fixed per-document
    before the variant-fallback loop runs, unlike source_intake_job_segment_id
    (which some fallback variants deliberately omit), so it's a stable key
    that fails a document's insert regardless of which variant is tried."""
    segment_map = segment_map or {}
    fail_redni_broj = fail_redni_broj or set()
    supa = MagicMock()
    state = {"predmet_dokumenti_calls": 0}

    def _table(name):
        t = MagicMock()
        if name == "intake_jobs":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                "id": "job-1", "status": "completed", "storage_path": "session/xyz",
                "original_filename": "bundle.pdf", "mime_type": "application/pdf",
                "predmet_id": None, "completed_at": None,
            }
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "predmeti":
            t.insert.return_value.execute.return_value.data = [{"id": "pred-NEW"}]
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = predmeti_matches or []
        elif name == "predmet_dokumenti":
            def _insert(row):
                state["predmet_dokumenti_calls"] += 1
                res = MagicMock()
                if row.get("redni_broj") in fail_redni_broj:
                    raise RuntimeError("insert boom")
                res.data = [{"id": f"pdok-{state['predmet_dokumenti_calls']}"}]
                return res
            t.insert.side_effect = _insert
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
            # Program Intake Sprint 007 -- default both new lookups to "no
            # match found" (no crash-recovery needed, no content-hash
            # duplicate found): the dedup check does .eq().eq().execute()
            # (no .limit()); the crash-recovery check does
            # .eq().eq().limit().execute() -- distinct attribute paths off
            # the same shared .select.return_value.eq.return_value node.
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        elif name == "klijenti":
            t.select.return_value.eq.return_value.ilike.return_value.neq.return_value.execute.return_value.data = []
            t.insert.return_value.execute.return_value.data = [{"id": "kl-001"}]
        elif name == "predmet_klijenti":
            t.insert.return_value.execute.return_value.data = [{}]
        elif name == "predmet_hronologija":
            t.insert.return_value.execute.return_value.data = [{}]
        elif name == "intake_job_segments":
            def _seg_maybe_single(doc_id_holder=[None]):
                pass
            m = MagicMock()

            def _eq(col, val):
                inner = MagicMock()
                inner.maybe_single.return_value.execute.return_value.data = segment_map.get(val)
                return inner
            t.select.return_value.eq.side_effect = _eq
        return t

    supa.table.side_effect = _table
    return supa


def _patches(mock_supa, documents, extract_pages=None):
    return (
        patch("routers.smart_intake._get_supa", return_value=mock_supa),
        patch("shared.intake_segments._get_supa", return_value=mock_supa),
        patch("shared.case_assimilation._get_supa", return_value=mock_supa),
        patch("shared.intake_documents.get_job_documents", new=AsyncMock(return_value=documents)),
        patch("shared.intake_worker.worker._download_and_decrypt", new=AsyncMock(return_value=b"raw bytes")),
        patch("uploaded_doc.extractor.extract", return_value=("Tuzba teksta ovde.", False, False, extract_pages)),
        patch("uploaded_doc.chunker.chunk_document", return_value={"chunks": []}),
        patch("uploaded_doc.ingest.ingest_session", return_value=None),
        patch("uploaded_doc.session.generate_session_id", return_value="sess-001"),
        patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)),
        patch("shared.vector_origin.now_iso", return_value="2026-08-05T00:00:00Z"),
        patch("routers.evidence.klasifikuj_i_sacuvaj"),
        patch("routers.intake._run_conflict_check", new=AsyncMock(return_value={"conflict_detected": False})),
        patch("routers.smart_intake.intake_queue.claim_finalize", new=AsyncMock(return_value={"id": "job-1"})),
        patch("shared.audit_immutable.log_action", new=AsyncMock()),
    )


async def _run_finalize_and_drain(mock_supa, documents, body, extract_pages=None):
    from routers.smart_intake import finalize_intake_job

    captured_coros = []

    def _capture_create_task(coro, *a, **kw):
        captured_coros.append(coro)
        return MagicMock()

    with contextlib.ExitStack() as stack:
        for p in _patches(mock_supa, documents, extract_pages):
            stack.enter_context(p)
        stack.enter_context(patch("asyncio.create_task", side_effect=_capture_create_task))
        result = await finalize_intake_job("job-1", _fake_request(), body, _fake_user())
        for coro in captured_coros:
            try:
                await coro
            except Exception:
                pass
    return result


@pytest.mark.anyio
async def test_content_based_case_number_match_auto_attaches_to_existing_case():
    """Phase 2 (Ownership Resolution) -- no explicit predmet_id, but the
    extracted case number exactly matches ONE existing predmet: auto-attach
    instead of creating a duplicate case (the capability this sprint added
    -- previously finalize ALWAYS created a new predmet without predmet_id)."""
    from routers.smart_intake import FinalizeReq

    doc, _ = _doc_entry("dok-001", case_number="П. 100/24")
    mock_supa = _make_supa(predmeti_matches=[{"id": "pred-EXISTING", "naziv": "Postojeci predmet"}])

    result = await _run_finalize_and_drain(mock_supa, [doc], FinalizeReq())

    assert result["predmet_id"] == "pred-EXISTING"


@pytest.mark.anyio
async def test_content_based_case_number_ambiguous_match_returns_409_not_a_guess():
    """2+ existing cases share the extracted case number -- never guesses
    (mission's own absolute rule), requires an explicit predmet_id instead."""
    from routers.smart_intake import FinalizeReq
    from fastapi import HTTPException

    doc, _ = _doc_entry("dok-001", case_number="П. 100/24")
    mock_supa = _make_supa(predmeti_matches=[{"id": "pred-A", "naziv": "A"}, {"id": "pred-B", "naziv": "B"}])

    with pytest.raises(HTTPException) as exc_info:
        await _run_finalize_and_drain(mock_supa, [doc], FinalizeReq())

    assert exc_info.value.status_code == 409
    # Program Intake Sprint 007 -- case numbers are now canonicalized
    # (normalize_case_number) before comparison/storage/display: "П. 100/24"
    # becomes "П100/24" (no separator before the number, slash before the
    # year). See shared/case_assimilation.py + tests/test_case_number_normalization.py.
    assert "П100/24" in exc_info.value.detail


@pytest.mark.anyio
async def test_conflicting_case_numbers_across_bundle_blocks_before_creating_a_case():
    """A genuinely multi-case bundle (2+ documents with DIFFERENT case
    numbers in one upload) must never be silently assimilated as one case --
    and no predmet should be created at all before this check fires."""
    from routers.smart_intake import FinalizeReq
    from fastapi import HTTPException

    doc_a, _ = _doc_entry("dok-001", case_number="П. 100/24")
    doc_b, _ = _doc_entry("dok-002", case_number="П. 200/24")
    mock_supa = _make_supa()

    with pytest.raises(HTTPException) as exc_info:
        await _run_finalize_and_drain(mock_supa, [doc_a, doc_b], FinalizeReq())

    assert exc_info.value.status_code == 409
    # Program Intake Sprint 007 -- canonicalized form, see comment above.
    assert "П100/24" in exc_info.value.detail and "П200/24" in exc_info.value.detail
    # No predmet must have been created -- the conflict check runs BEFORE
    # any predmeti.insert call.
    predmeti_insert_calls = [
        c for c in mock_supa.table("predmeti").insert.mock_calls
    ]
    assert not predmeti_insert_calls


@pytest.mark.anyio
async def test_one_document_insert_failure_does_not_lose_or_block_sibling():
    """Phase 5 (Deterministic Failure Recovery) -- one document's
    predmet_dokumenti insert throwing must not abort the loop; the sibling
    document still gets linked. Segments are keyed by document_id via the
    intake_job_segments mock (segment ids seg-A / seg-B)."""
    from routers.smart_intake import FinalizeReq

    doc_a, _ = _doc_entry("dok-001")
    doc_b, _ = _doc_entry("dok-002")
    segment_map = {
        "dok-001": {"id": "seg-A", "start_page": 1, "end_page": 1},
        "dok-002": {"id": "seg-B", "start_page": 2, "end_page": 2},
    }
    mock_supa = _make_supa(segment_map=segment_map, fail_redni_broj={1})

    result = await _run_finalize_and_drain(
        mock_supa, [doc_a, doc_b], FinalizeReq(), extract_pages=["Strana 1.", "Strana 2."],
    )

    assert result["dokumenata_ukupno"] == 2
    assert result["dokumenata_povezano"] == 1
    outcomes = {d["document_id"]: d["povezan"] for d in result["dokumenti"]}
    assert outcomes["dok-001"] is False
    assert outcomes["dok-002"] is True


@pytest.mark.anyio
async def test_lineage_fk_set_from_matching_segment_per_document():
    """Phase 4 (Lineage Verification) -- each document's predmet_dokumenti
    insert must carry ITS OWN intake_job_segments.id, not the other
    document's, and not a shared/blank value."""
    from routers.smart_intake import FinalizeReq

    doc_a, _ = _doc_entry("dok-001")
    doc_b, _ = _doc_entry("dok-002")
    segment_map = {
        "dok-001": {"id": "seg-A", "start_page": 1, "end_page": 1},
        "dok-002": {"id": "seg-B", "start_page": 2, "end_page": 2},
    }
    mock_supa = _make_supa(segment_map=segment_map)

    captured_rows = []
    real_table = mock_supa.table.side_effect

    def _spy_table(name):
        t = real_table(name)
        if name == "predmet_dokumenti":
            orig_insert = t.insert
            def _spy_insert(row):
                captured_rows.append(dict(row))
                return orig_insert(row)
            t.insert = _spy_insert
        return t
    mock_supa.table.side_effect = _spy_table

    await _run_finalize_and_drain(
        mock_supa, [doc_a, doc_b], FinalizeReq(), extract_pages=["Strana 1.", "Strana 2."],
    )

    lineage_by_doc = {}
    # naziv_fajla is identical across rows (same job filename) -- rely on
    # insertion order instead (doc_a processed before doc_b, matching the
    # loop's own sequential order).
    assert len(captured_rows) == 2
    assert captured_rows[0]["source_intake_job_segment_id"] == "seg-A"
    assert captured_rows[1]["source_intake_job_segment_id"] == "seg-B"


@pytest.mark.anyio
async def test_single_document_job_has_no_lineage_fk_by_design():
    """A single-document job (no intake_job_segments rows exist at all,
    Sprint 005's own invariant) must get source_intake_job_segment_id=None,
    not an error and not a fabricated value."""
    from routers.smart_intake import FinalizeReq

    doc, _ = _doc_entry("dok-001")
    mock_supa = _make_supa(segment_map={})  # no segment row for dok-001

    captured_rows = []
    real_table = mock_supa.table.side_effect

    def _spy_table(name):
        t = real_table(name)
        if name == "predmet_dokumenti":
            orig_insert = t.insert
            def _spy_insert(row):
                captured_rows.append(dict(row))
                return orig_insert(row)
            t.insert = _spy_insert
        return t
    mock_supa.table.side_effect = _spy_table

    await _run_finalize_and_drain(mock_supa, [doc], FinalizeReq())

    assert captured_rows[0]["source_intake_job_segment_id"] is None


@pytest.mark.anyio
async def test_document_assimilation_writes_an_audit_entry():
    """Phase 1 audit finding: finalize_intake_job had ZERO audit calls for
    document-into-case registration (unlike Pipeline A's per-case upload).
    Every successfully-linked document must now leave an audit trace."""
    from routers.smart_intake import FinalizeReq

    doc, _ = _doc_entry("dok-001")
    mock_supa = _make_supa()

    with contextlib.ExitStack() as stack:
        for p in _patches(mock_supa, [doc]):
            stack.enter_context(p)
        # log_action is imported locally inside finalize_intake_job (fresh
        # lookup on every call), so patching the source module (not a
        # routers.smart_intake.log_action module-level attribute, which
        # doesn't exist) is what actually intercepts it.
        mock_log = stack.enter_context(patch("shared.audit_immutable.log_action", new=AsyncMock()))
        stack.enter_context(patch("asyncio.create_task", side_effect=lambda coro, *a, **kw: MagicMock()))
        from routers.smart_intake import finalize_intake_job
        await finalize_intake_job("job-1", _fake_request(), FinalizeReq(), _fake_user())

    mock_log.assert_awaited_once()
    assert mock_log.call_args.args[0] == "document_assimilated"
    assert mock_log.call_args.args[2] == "predmet_dokumenti"

# -*- coding: utf-8 -*-
"""Tests for shared/intake_documents.py (Smart Intake Phase 1A persistence)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_chain(data):
    chain = MagicMock()
    for attr in ["select", "eq", "update", "insert", "order", "limit", "is_", "maybe_single"]:
        setattr(chain, attr, MagicMock(return_value=chain))
    chain.execute = MagicMock(return_value=MagicMock(data=data))
    return chain


@pytest.mark.anyio
async def test_create_document_returns_id():
    from shared import intake_documents as idoc
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain([{"id": "doc-1"}]))
    with patch("shared.intake_documents._get_supa", return_value=supa):
        doc_id = await idoc.create_document("job-1", "judgment", 0.85, "heuristic")
    assert doc_id == "doc-1"


@pytest.mark.anyio
async def test_insert_entities_bulk():
    from shared import intake_documents as idoc
    rows = [{"id": "e1", "entity_type": "case_number"}, {"id": "e2", "entity_type": "deadline"}]
    supa = MagicMock()
    chain = _make_chain(rows)
    supa.table = MagicMock(return_value=chain)
    entities = [
        {"entity_type": "case_number", "value": "П 341/26", "confidence": 0.95, "extraction_method": "regex"},
        {"entity_type": "deadline", "value": None, "confidence": 0.0, "extraction_method": "regex"},
    ]
    with patch("shared.intake_documents._get_supa", return_value=supa):
        result = await idoc.insert_entities("doc-1", entities)
    assert len(result) == 2
    chain.insert.assert_called_once()


@pytest.mark.anyio
async def test_insert_entities_empty_list_is_noop():
    from shared import intake_documents as idoc
    supa = MagicMock()
    with patch("shared.intake_documents._get_supa", return_value=supa):
        result = await idoc.insert_entities("doc-1", [])
    assert result == []
    supa.table.assert_not_called()


@pytest.mark.anyio
async def test_get_job_result_no_document_returns_empty_shape():
    from shared import intake_documents as idoc
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain(None))
    with patch("shared.intake_documents._get_supa", return_value=supa):
        result = await idoc.get_job_result("job-1")
    assert result == {"document": None, "entities": [], "review": None}


@pytest.mark.anyio
async def test_get_job_result_assembles_document_entities_review():
    from shared import intake_documents as idoc

    document = {"id": "doc-1", "document_type": "judgment"}
    entities = [{"id": "e1", "entity_type": "deadline", "confidence": 0.72}]
    review = {"id": "r1", "reason": "low_confidence_extraction", "low_confidence_fields": ["deadline"]}

    def _table(name):
        if name == "intake_documents":
            return _make_chain(document)
        if name == "extracted_entities":
            return _make_chain(entities)
        if name == "intake_review_queue":
            return _make_chain(review)
        return _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("shared.intake_documents._get_supa", return_value=supa):
        result = await idoc.get_job_result("job-1")

    assert result["document"]["document_type"] == "judgment"
    assert result["entities"][0]["entity_type"] == "deadline"
    assert result["review"]["low_confidence_fields"] == ["deadline"]


@pytest.mark.anyio
async def test_correct_entity_preserves_original_writes_corrected():
    from shared import intake_documents as idoc

    entity = {"id": "e1", "document_id": "doc-1", "entity_type": "deadline", "value": None, "confidence": 0.0}
    doc = {"intake_job_id": "job-1", "document_type": "judgment"}

    calls = []
    def _table(name):
        calls.append(name)
        if name == "extracted_entities":
            return _make_chain(entity)
        if name == "intake_documents":
            return _make_chain(doc)
        return _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("shared.intake_documents._get_supa", return_value=supa):
        result = await idoc.correct_entity("e1", "15.12.2026", "advokat@primer.rs")

    assert result["corrected_value"] == "15.12.2026"
    assert result["entity_type"] == "deadline"
    assert "intake_processing_outcomes" in calls  # write_processing_outcome pozvan sa user_corrected=True


@pytest.mark.anyio
async def test_correct_entity_passes_optional_reason_to_outcome():
    from shared import intake_documents as idoc

    entity = {"id": "e1", "document_id": "doc-1", "entity_type": "deadline", "value": None, "confidence": 0.0}
    doc = {"intake_job_id": "job-1", "document_type": "judgment"}

    outcome_inserts = []
    def _table(name):
        if name == "extracted_entities":
            return _make_chain(entity)
        if name == "intake_documents":
            return _make_chain(doc)
        if name == "intake_processing_outcomes":
            chain = _make_chain(None)
            def _capture_insert(payload):
                outcome_inserts.append(payload)
                return chain
            chain.insert = MagicMock(side_effect=_capture_insert)
            return chain
        return _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("shared.intake_documents._get_supa", return_value=supa):
        await idoc.correct_entity("e1", "15.12.2026", "advokat@primer.rs", reason="Datum presude nije rok za žalbu.")

    assert len(outcome_inserts) == 1
    assert outcome_inserts[0]["correction_reason"] == "Datum presude nije rok za žalbu."


@pytest.mark.anyio
async def test_correct_entity_reason_defaults_to_none():
    from shared import intake_documents as idoc

    entity = {"id": "e1", "document_id": "doc-1", "entity_type": "deadline", "value": None, "confidence": 0.0}
    doc = {"intake_job_id": "job-1", "document_type": "judgment"}

    outcome_inserts = []
    def _table(name):
        if name == "extracted_entities":
            return _make_chain(entity)
        if name == "intake_documents":
            return _make_chain(doc)
        if name == "intake_processing_outcomes":
            chain = _make_chain(None)
            def _capture_insert(payload):
                outcome_inserts.append(payload)
                return chain
            chain.insert = MagicMock(side_effect=_capture_insert)
            return chain
        return _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("shared.intake_documents._get_supa", return_value=supa):
        await idoc.correct_entity("e1", "15.12.2026", "advokat@primer.rs")  # no reason passed

    assert outcome_inserts[0]["correction_reason"] is None


@pytest.mark.anyio
async def test_correct_entity_passes_optional_error_source_to_outcome():
    from shared import intake_documents as idoc

    entity = {"id": "e1", "document_id": "doc-1", "entity_type": "deadline", "value": None, "confidence": 0.0}
    doc = {"intake_job_id": "job-1", "document_type": "judgment"}

    outcome_inserts = []
    def _table(name):
        if name == "extracted_entities":
            return _make_chain(entity)
        if name == "intake_documents":
            return _make_chain(doc)
        if name == "intake_processing_outcomes":
            chain = _make_chain(None)
            def _capture_insert(payload):
                outcome_inserts.append(payload)
                return chain
            chain.insert = MagicMock(side_effect=_capture_insert)
            return chain
        return _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("shared.intake_documents._get_supa", return_value=supa):
        await idoc.correct_entity("e1", "15.12.2026", "advokat@primer.rs", error_source="parser")

    assert outcome_inserts[0]["error_source"] == "parser"


@pytest.mark.anyio
async def test_write_processing_outcome_rejects_unknown_error_source():
    from shared import intake_documents as idoc

    outcome_inserts = []
    supa = MagicMock()
    chain = _make_chain(None)
    def _capture_insert(payload):
        outcome_inserts.append(payload)
        return chain
    chain.insert = MagicMock(side_effect=_capture_insert)
    supa.table = MagicMock(return_value=chain)

    with patch("shared.intake_documents._get_supa", return_value=supa):
        await idoc.write_processing_outcome("job-1", "judgment", 0.9, {}, 1200, error_source="not_a_real_source")

    assert outcome_inserts[0]["error_source"] is None  # fail-soft: nevalidna vrednost se tiho odbacuje, upis se ne obara


@pytest.mark.anyio
async def test_correct_entity_raises_when_entity_missing():
    from shared import intake_documents as idoc
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain(None))
    with patch("shared.intake_documents._get_supa", return_value=supa):
        with pytest.raises(ValueError):
            await idoc.correct_entity("missing-id", "x", "user")


@pytest.mark.anyio
async def test_write_processing_outcome_swallows_errors():
    from shared import intake_documents as idoc
    supa = MagicMock()
    supa.table = MagicMock(side_effect=Exception("db down"))
    with patch("shared.intake_documents._get_supa", return_value=supa):
        await idoc.write_processing_outcome("job-1", "judgment", 0.9, {}, 1200)  # must not raise


@pytest.mark.anyio
async def test_write_processing_outcome_raises_when_raise_on_error_true():
    """Program Intake Sprint 002 (2026-08-05) -- shared/intake_worker.py::
    _process() passes raise_on_error=True because this write is the ONLY
    reliable completion signal has_processing_outcome() checks. Swallowing
    a transient failure here (the default, correct_entity()'s own use case)
    would silently let a job be marked completed with no outcome row --
    exactly the bug shape Sprint 001 fixed, reopened through this door
    (Sprint 002 Fork A §B1 / Fork B §3.3). Must propagate so _tick()'s
    existing retry machinery handles it, same as every other failure."""
    from shared import intake_documents as idoc
    supa = MagicMock()
    supa.table = MagicMock(side_effect=Exception("db down"))
    with patch("shared.intake_documents._get_supa", return_value=supa):
        with pytest.raises(Exception, match="db down"):
            await idoc.write_processing_outcome("job-1", "judgment", 0.9, {}, 1200, raise_on_error=True)


@pytest.mark.anyio
async def test_has_processing_outcome_true_when_row_exists():
    from shared import intake_documents as idoc
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain({"intake_job_id": "job-1"}))
    with patch("shared.intake_documents._get_supa", return_value=supa):
        assert await idoc.has_processing_outcome("job-1") is True


@pytest.mark.anyio
async def test_has_processing_outcome_false_when_no_row():
    from shared import intake_documents as idoc
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain(None))
    with patch("shared.intake_documents._get_supa", return_value=supa):
        assert await idoc.has_processing_outcome("job-1") is False


@pytest.mark.anyio
async def test_delete_partial_document_deletes_children_before_parent():
    """Program Intake Sprint 001 -- redosled mora biti deca pre roditelja
    (extracted_entities/intake_review_queue nemaju ON DELETE CASCADE na
    intake_documents, migracija 074), inace bi FK constraint oborio
    brisanje roditelja dok deca jos postoje."""
    from shared import intake_documents as idoc
    delete_order = []

    def _table(name):
        chain = _make_chain(None)
        original_delete = chain.delete
        def _tracked_delete(*a, **kw):
            delete_order.append(name)
            return original_delete(*a, **kw)
        chain.delete = MagicMock(side_effect=_tracked_delete)
        return chain
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("shared.intake_documents._get_supa", return_value=supa):
        await idoc.delete_partial_document("doc-stale", "job-1")

    assert delete_order.index("extracted_entities") < delete_order.index("intake_documents")
    assert delete_order.index("intake_review_queue") < delete_order.index("intake_documents")


# ═══════════════════════════════════════════════════════════════════════════
# Program Intake Sprint 004 (2026-08-05) — resolve_review_queue_for_job /
# resolve_review(). Before this sprint, resolve_review_queue_for_job existed
# (migration 074) but had ZERO call sites anywhere in the codebase — a
# review could be created but never resolved through any live path.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_resolve_review_queue_for_job_returns_true_when_row_resolved():
    from shared import intake_documents as idoc
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain([{"id": "rq-1", "resolved_at": "2026-08-05T00:00:00Z"}]))
    with patch("shared.intake_documents._get_supa", return_value=supa):
        resolved = await idoc.resolve_review_queue_for_job("job-1", "advokat@vindex.rs")
    assert resolved is True


@pytest.mark.anyio
async def test_resolve_review_queue_for_job_returns_false_when_already_resolved():
    """Idempotent: a second call against an already-resolved row finds
    zero matching rows (the WHERE resolved_at IS NULL clause excludes it)
    and must report that honestly, not claim it resolved something."""
    from shared import intake_documents as idoc
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain([]))
    with patch("shared.intake_documents._get_supa", return_value=supa):
        resolved = await idoc.resolve_review_queue_for_job("job-1", "advokat@vindex.rs")
    assert resolved is False


@pytest.mark.anyio
async def test_resolve_review_advances_job_status_and_resolves_review():
    from shared import intake_documents as idoc

    def _table(name):
        if name == "intake_review_queue":
            return _make_chain([{"id": "rq-1"}])
        if name == "intake_jobs":
            return _make_chain([{"id": "job-1", "status": "completed"}])
        return _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("shared.intake_documents._get_supa", return_value=supa):
        result = await idoc.resolve_review("job-1", "advokat@vindex.rs")

    assert result["review_resolved_now"] is True
    assert result["job_status_advanced"] is True


@pytest.mark.anyio
async def test_resolve_review_simultaneous_approval_only_one_wins():
    """Program Intake Sprint 004 Phase 6 (Concurrency Verification): two
    users (or one user double-clicking) resolve the SAME review at
    effectively the same time. Postgres single-row UPDATE with a
    WHERE resolved_at IS NULL clause means only the first to actually
    commit affects a row -- the second's UPDATE matches zero rows. This
    test simulates that outcome (not real DB concurrency, which is out of
    a unit test's reach) and proves resolve_review()'s CALLER-facing
    contract handles it correctly: no duplication, no lost decision, no
    contradictory status -- exactly one 'true' resolution, one honest
    'already done' no-op."""
    from shared import intake_documents as idoc

    # First caller: review row still unresolved, job still awaiting_review.
    call_count = {"review": 0, "job": 0}

    def _table(name):
        if name == "intake_review_queue":
            call_count["review"] += 1
            # First call resolves it (1 row affected); any subsequent call
            # finds it already resolved (0 rows -- Postgres WHERE excludes it).
            return _make_chain([{"id": "rq-1"}] if call_count["review"] == 1 else [])
        if name == "intake_jobs":
            call_count["job"] += 1
            return _make_chain([{"id": "job-1"}] if call_count["job"] == 1 else [])
        return _make_chain(None)

    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("shared.intake_documents._get_supa", return_value=supa):
        first = await idoc.resolve_review("job-1", "advokat1@vindex.rs")
        second = await idoc.resolve_review("job-1", "advokat2@vindex.rs")

    assert first["review_resolved_now"] is True
    assert first["job_status_advanced"] is True
    # The second caller's action is NOT an error and NOT a duplicate --
    # it's an honest, safe no-op reporting nothing was left to resolve.
    assert second["review_resolved_now"] is False
    assert second["job_status_advanced"] is False


@pytest.mark.anyio
async def test_resolve_review_on_job_with_no_review_entry_is_a_safe_noop():
    """Duplicate/misdirected call: resolving a job that was never flagged
    for review at all (no intake_review_queue row ever created) must not
    error -- it's a safe no-op, not a defect to guard against with an
    exception."""
    from shared import intake_documents as idoc
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain([]))
    with patch("shared.intake_documents._get_supa", return_value=supa):
        result = await idoc.resolve_review("job-never-flagged", "advokat@vindex.rs")
    assert result["review_resolved_now"] is False
    assert result["job_status_advanced"] is False


@pytest.mark.anyio
async def test_resolve_review_idempotent_when_already_resolved_and_completed():
    """Second call (already resolved, job already completed): both steps
    are no-ops (empty result sets), reported honestly as such -- not an
    error, and safe to call repeatedly (e.g. a lawyer double-clicking the
    confirm button, or a retried request)."""
    from shared import intake_documents as idoc

    def _table(name):
        return _make_chain([])
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("shared.intake_documents._get_supa", return_value=supa):
        result = await idoc.resolve_review("job-1", "advokat@vindex.rs")

    assert result["review_resolved_now"] is False
    assert result["job_status_advanced"] is False

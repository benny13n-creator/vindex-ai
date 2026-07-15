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

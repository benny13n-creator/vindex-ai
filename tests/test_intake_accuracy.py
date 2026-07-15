# -*- coding: utf-8 -*-
"""Tests for shared/intake_accuracy.py (Office Accuracy Dashboard, Validation Sprint)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_chain(data):
    chain = MagicMock()
    for attr in ["select", "eq", "neq", "in_", "order", "limit", "is_"]:
        setattr(chain, attr, MagicMock(return_value=chain))
    chain.execute = MagicMock(return_value=MagicMock(data=data))
    return chain


@pytest.mark.anyio
async def test_below_min_sample_returns_honest_empty_state():
    from shared import intake_accuracy as ia
    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain([{"id": "d1"}, {"id": "d2"}]))  # only 2, below _MIN_SAMPLE_SIZE
    with patch("shared.intake_accuracy._get_supa", return_value=supa):
        result = await ia.get_office_accuracy_kpis()
    assert result["nedovoljno_podataka"] is True
    assert result["obradjeno_dokumenata"] == 2
    assert "ocr_uspesnost" not in result


@pytest.mark.anyio
async def test_computes_kpis_above_min_sample():
    from shared import intake_accuracy as ia

    documents = [{"id": f"d{i}", "ocr_used": False, "classification_method": "heuristic"} for i in range(6)]
    documents[0]["classification_method"] = "llm"  # 1/6 LLM fallback for classification

    review_rows = [
        {"intake_job_id": "j0", "document_id": "d0", "reason": "low_confidence_extraction", "low_confidence_fields": ["deadline", "judge"]},
        {"intake_job_id": "j1", "document_id": "d1", "reason": "ocr_failed", "low_confidence_fields": []},
    ]

    entities = [
        {"entity_type": "case_number", "extraction_method": "regex", "reviewed": False, "document_id": "d0"},
        {"entity_type": "deadline", "extraction_method": "regex", "reviewed": True, "document_id": "d0"},
        {"entity_type": "judge", "extraction_method": "llm", "reviewed": True, "document_id": "d0"},
        {"entity_type": "court", "extraction_method": "llm", "reviewed": False, "document_id": "d2"},
    ]

    outcomes = [
        {"intake_job_id": "j0", "user_corrected": False, "processing_time_ms": 2000, "created_at": "2026-07-15T10:00:00+00:00"},
        {"intake_job_id": "j0", "user_corrected": True, "processing_time_ms": 0, "created_at": "2026-07-15T10:00:08+00:00", "fields_corrected": ["deadline"]},
    ]

    def _table(name):
        if name == "intake_documents":
            return _make_chain(documents)
        if name == "intake_review_queue":
            return _make_chain(review_rows)
        if name == "extracted_entities":
            return _make_chain(entities)
        if name == "intake_processing_outcomes":
            return _make_chain(outcomes)
        return _make_chain([])
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("shared.intake_accuracy._get_supa", return_value=supa):
        result = await ia.get_office_accuracy_kpis()

    assert result["nedovoljno_podataka"] is False
    assert result["obradjeno_dokumenata"] == 6
    # 1 od 6 dokumenata (d1) je ocr_failed -> 5/6 uspesnost
    assert result["ocr_uspesnost"] == pytest.approx(5 / 6, rel=1e-3)
    # samo d0 ima low_confidence_fields (2), ostalih 5 dokumenata imaju 0
    assert result["prosecan_broj_review_polja"] == pytest.approx(2 / 6, rel=1e-3)
    # 2 od 4 entiteta su reviewed=True, sva na d0 -> 1/6 dokumenata sa ispravkom
    assert result["stopa_ispravki"] == pytest.approx(1 / 6, rel=1e-3)
    assert result["najcesce_ispravljano_polje"] in ("deadline", "judge")  # tied 1-1, either is a valid mode
    assert result["llm_fallback_klasifikacija"] == pytest.approx(1 / 6, rel=1e-3)
    assert result["llm_fallback_ekstrakcija"] == pytest.approx(2 / 4, rel=1e-3)
    assert result["prosecno_vreme_obrade_ms"] == 2000
    assert result["prosecno_vreme_do_ispravke_s"] == pytest.approx(8.0, rel=1e-2)
    assert result["napomena_vreme_ispravke"] is not None


@pytest.mark.anyio
async def test_no_entities_llm_fallback_is_none_not_zero():
    from shared import intake_accuracy as ia
    documents = [{"id": f"d{i}", "ocr_used": False, "classification_method": "heuristic"} for i in range(6)]

    def _table(name):
        if name == "intake_documents":
            return _make_chain(documents)
        return _make_chain([])
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("shared.intake_accuracy._get_supa", return_value=supa):
        result = await ia.get_office_accuracy_kpis()

    assert result["llm_fallback_ekstrakcija"] is None  # nema entiteta -> "nema podataka", ne 0%

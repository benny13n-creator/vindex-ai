# -*- coding: utf-8 -*-
"""Tests for Phase 2.3.1 — doc confidence gate bias in ask_agent.

This file sorts alphabetically before test_doc_pitanje_api.py so that
the real main module is imported before any mock replaces it in sys.modules.
After capturing references, main is removed from sys.modules so
test_doc_pitanje_api.py's setdefault can install its own mock.
All patching uses patch.object(_real_main, ...) to target the real module.
"""

import sys
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import real main, capture what we need, then clear sys.modules so
# test_doc_pitanje_api.py's setdefault can install its api-level mock.
import main as _real_main
ask_agent = _real_main.ask_agent
del sys.modules["main"]

# ─── Shared helpers ──────────────────────────────────────────────────────────

_FAKE_DOC = "Zaposleni ima pravo na godišnji odmor od najmanje 20 radnih dana. " * 3


def _make_meta(confidence: str, doc_scores: list) -> tuple:
    docs = [_FAKE_DOC]
    meta = {
        "confidence": confidence,
        "top_score": 0.50,
        "top_article": "Član 1",
        "top_law": "zakon o radu",
        "doc_passages": [{"score": s, "text_snippet": "Probni rad traje 6 meseci."} for s in doc_scores],
        "praksa_matches": [],
    }
    return docs, meta


def _fake_llm_response(*args, **kwargs) -> str:
    return "Prema vašem dokumentu, probni rad traje šest meseci."


# ─── Test 1: LOW → MEDIUM when doc score >= 0.5 ──────────────────────────────

def test_gate_bias_low_to_medium():
    """LOW law-confidence + doc score 0.7 → bias upgrades to MEDIUM, LLM called."""
    docs, meta = _make_meta("LOW", [0.7])

    with patch.object(_real_main, "retrieve_documents", return_value=(docs, meta)), \
         patch.object(_real_main, "_pozovi_openai", side_effect=_fake_llm_response) as mock_llm, \
         patch.object(_real_main, "_proveri_halucinaciju", return_value=(True, "")), \
         patch.object(_real_main, "_verifikuj_pravne_greske", return_value=(True, "")):
        result = ask_agent("Koliko traje probni rad?", extra_namespaces=["tmp_xyz"])

    assert result["status"] == "success"
    assert result["confidence"] != "LOW", "Confidence should have been upgraded from LOW"
    mock_llm.assert_called()


# ─── Test 2: MEDIUM → HIGH when doc score >= 0.5 ─────────────────────────────

def test_gate_bias_medium_to_high():
    """MEDIUM law-confidence + doc score 0.8 → bias upgrades to HIGH, LLM called."""
    docs, meta = _make_meta("MEDIUM", [0.8])

    with patch.object(_real_main, "retrieve_documents", return_value=(docs, meta)), \
         patch.object(_real_main, "_pozovi_openai", side_effect=_fake_llm_response) as mock_llm, \
         patch.object(_real_main, "_proveri_halucinaciju", return_value=(True, "")), \
         patch.object(_real_main, "_verifikuj_pravne_greske", return_value=(True, "")):
        result = ask_agent("Koliko traje probni rad?", extra_namespaces=["tmp_xyz"])

    assert result["status"] == "success"
    assert result["confidence"] == "HIGH"
    mock_llm.assert_called()


# ─── Test 3: no bias when doc score below threshold ───────────────────────────

def test_no_bias_when_doc_score_below_threshold():
    """Doc score 0.4 < 0.5 threshold → LOW band unchanged → refusal, no LLM."""
    docs, meta = _make_meta("LOW", [0.4])

    with patch.object(_real_main, "retrieve_documents", return_value=(docs, meta)), \
         patch.object(_real_main, "_pozovi_openai", side_effect=_fake_llm_response) as mock_llm:
        result = ask_agent("Koliko traje probni rad?", extra_namespaces=["tmp_xyz"])

    assert result["confidence"] == "LOW"
    mock_llm.assert_not_called()


# ─── Test 4: no bias when extra_namespaces is None ───────────────────────────

def test_no_bias_when_no_extra_namespaces():
    """extra_namespaces=None → gate bias block skipped → LOW stays LOW."""
    docs, meta = _make_meta("LOW", [0.9])

    with patch.object(_real_main, "retrieve_documents", return_value=(docs, meta)), \
         patch.object(_real_main, "_pozovi_openai", side_effect=_fake_llm_response) as mock_llm:
        result = ask_agent("Koliko traje probni rad?", extra_namespaces=None)

    assert result["confidence"] == "LOW"
    mock_llm.assert_not_called()


# ─── Test 5: no bias when doc_passages list is empty ─────────────────────────

def test_no_bias_when_doc_passages_empty():
    """extra_namespaces provided but doc_passages=[] → band unchanged."""
    docs, meta = _make_meta("LOW", [])

    with patch.object(_real_main, "retrieve_documents", return_value=(docs, meta)), \
         patch.object(_real_main, "_pozovi_openai", side_effect=_fake_llm_response) as mock_llm:
        result = ask_agent("Koliko traje probni rad?", extra_namespaces=["tmp_xyz"])

    assert result["confidence"] == "LOW"
    mock_llm.assert_not_called()

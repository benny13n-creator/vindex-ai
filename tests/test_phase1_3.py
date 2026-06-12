# -*- coding: utf-8 -*-
"""
Unit tests for Phase 1.3 — parallel retrieval + praksa formatter.

These tests use mocks so they run without a live Pinecone connection.
"""

import sys
import os
import types
from unittest.mock import MagicMock, patch, call
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.retrieve import (
    _formatiraj_praksa_match,
    _PRAKSA_NS,
    PRAKSA_CONFIDENCE_HIGH_THRESHOLD,
    PRAKSA_CONFIDENCE_MEDIUM_THRESHOLD,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_match(id: str, score: float, metadata: dict):
    """Build a minimal Pinecone-style ScoredVector mock."""
    m = MagicMock()
    m.id = id
    m.score = score
    m.metadata = metadata
    return m


def _make_praksa_match(decision_number="Kzz 754/2025", court="Vrhovni sud",
                       matter="Krivična", section="OBRAZLOŽENJE",
                       text="Sud je utvrdio da je žalba neosnovana prema članu 203 KZ.",
                       cited=None, decision_id_fallback=None):
    meta = {
        "doc_type": "sudska_praksa",
        "court": court,
        "decision_number": decision_number,
        "decision_id_fallback": decision_id_fallback,
        "decision_date": "2026-01-15",
        "matter": matter,
        "registrant": decision_number.split()[0] if decision_number else "",
        "source_url": "https://www.vrh.sud.rs/sr-lat/kzz-754-2025",
        "section": section,
        "chunk_index": 0,
        "chunk_total": 5,
        "cited_articles_raw": cited or ["203", "210"],
        "cited_articles_normalized": [],
        "text": text,
    }
    return _make_match(f"{decision_number.replace(' ', '_')}__chunk_0", 0.72, meta)


# ─── Test 1: praksa formatter includes key fields ─────────────────────────────

def test_praksa_formatter_includes_decision_number():
    """Formatter output must contain decision_number, court, matter, and cited articles."""
    m = _make_praksa_match()
    out = _formatiraj_praksa_match(m)

    assert "SUDSKA PRAKSA [" in out, f"Missing SUDSKA PRAKSA header: {out[:200]}"
    assert "Kzz 754/2025" in out, f"Missing decision number: {out[:200]}"
    assert "Vrhovni sud" in out, f"Missing court: {out[:200]}"
    assert "Krivična" in out, f"Missing matter: {out[:200]}"
    assert "203" in out, f"Missing cited article: {out[:200]}"
    # Must include section label for non-HEADER sections
    assert "OBRAZLOŽENJE" in out or "Sekcija" in out, f"Missing section label: {out[:200]}"
    # Must include the chunk text
    assert "žalba neosnovana" in out, f"Missing chunk text: {out[:200]}"


def test_praksa_formatter_includes_date():
    """Formatter must include decision_date in header."""
    m = _make_praksa_match()
    out = _formatiraj_praksa_match(m)
    assert "2026-01-15" in out, f"Missing date in header: {out[:200]}"


# ─── Test 2: fallback when decision_number is empty ──────────────────────────

def test_praksa_formatter_handles_decision_id_fallback():
    """When decision_number is empty (3 partial zastitaprava decisions),
    formatter uses decision_id_fallback and does not crash."""
    m = _make_praksa_match(
        decision_number="",
        decision_id_fallback="id_b4d6052a4905",
        court="Vrhovni sud",
        matter="Zaštita prava",
    )
    out = _formatiraj_praksa_match(m)

    assert "SUDSKA PRAKSA [" in out, f"Missing header: {out[:200]}"
    assert "id_b4d6052a4905" in out, f"Missing fallback id: {out[:200]}"
    assert out.strip(), "Output must be non-empty"


# ─── Test 3: formatter output is long enough to pass _filtriraj_kontekst ─────

def test_praksa_formatter_passes_context_filter():
    """_filtriraj_kontekst filters docs with len <= 50. Formatter output must be > 50 chars."""
    m = _make_praksa_match()
    out = _formatiraj_praksa_match(m)
    assert len(out.strip()) > 50, f"Formatter output too short ({len(out)} chars): {out[:200]}"


# ─── Test 4: gate thresholds — zakon band unchanged ──────────────────────────

def test_gate_zakon_thresholds_unchanged():
    """Phase 1.3 must not change the existing zakon gate thresholds."""
    assert CONFIDENCE_HIGH_THRESHOLD == 0.65, (
        f"Zakon HIGH threshold changed: {CONFIDENCE_HIGH_THRESHOLD}"
    )
    assert CONFIDENCE_MEDIUM_THRESHOLD == 0.52, (
        f"Zakon MEDIUM threshold changed: {CONFIDENCE_MEDIUM_THRESHOLD}"
    )


def test_gate_praksa_thresholds_match_zakon():
    """Phase 1.3: praksa HIGH must equal zakon HIGH; MEDIUM may be >= after calibration."""
    assert PRAKSA_CONFIDENCE_HIGH_THRESHOLD == CONFIDENCE_HIGH_THRESHOLD, (
        "Praksa HIGH threshold should match zakon HIGH threshold for Phase 1.3"
    )
    assert PRAKSA_CONFIDENCE_MEDIUM_THRESHOLD >= CONFIDENCE_MEDIUM_THRESHOLD, (
        "Praksa MEDIUM threshold must not be lower than zakon MEDIUM threshold"
    )


# ─── Test 5: _PRAKSA_NS constant is correct ──────────────────────────────────

def test_praksa_namespace_constant():
    """Namespace string must be exactly 'sudska_praksa'."""
    assert _PRAKSA_NS == "sudska_praksa", f"Wrong namespace: {_PRAKSA_NS!r}"


# ─── Test 6: parallel retrieval calls Pinecone with namespace ────────────────

def test_parallel_retrieval_calls_sudska_praksa_namespace():
    """
    _pretraga_praksa must call index.query with namespace='sudska_praksa'.
    Verified via mock without live Pinecone connection.
    """
    from app.services.retrieve import _pretraga_praksa

    mock_index = MagicMock()
    mock_matches = [_make_praksa_match()]
    mock_index.query.return_value = MagicMock(matches=mock_matches)

    with patch("app.services.retrieve._get_index", return_value=mock_index):
        result = _pretraga_praksa([0.0] * 3072, k=5)

    mock_index.query.assert_called_once()
    call_kwargs = mock_index.query.call_args
    # Verify namespace argument
    ns = call_kwargs.kwargs.get("namespace") or (
        call_kwargs.args[2] if len(call_kwargs.args) > 2 else None
    )
    assert call_kwargs.kwargs.get("namespace") == "sudska_praksa", (
        f"Expected namespace='sudska_praksa', got: {call_kwargs}"
    )
    assert result == mock_matches


def test_parallel_retrieval_returns_empty_on_error():
    """_pretraga_praksa must return [] (not raise) when Pinecone fails."""
    from app.services.retrieve import _pretraga_praksa

    mock_index = MagicMock()
    mock_index.query.side_effect = Exception("Pinecone connection error")

    with patch("app.services.retrieve._get_index", return_value=mock_index):
        result = _pretraga_praksa([0.0] * 3072, k=5)

    assert result == [], f"Expected empty list on error, got: {result}"

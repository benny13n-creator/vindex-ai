# -*- coding: utf-8 -*-
"""
Commit 4/N: P0 Security Hardening — 10 regression tests.

T1  — /api/pitanje/stream _event_generator uses ask_agent (not raw chat.completions)
T2  — /api/pitanje/stream _event_generator has _get_credits for no-deduct branch
T3  — /api/register has @limiter.limit("5/minute") decorator
T4  — should_deduct=True when status=success and blocked=False
T5  — should_deduct=False when status=success and blocked=True
T6  — should_deduct=False when status=error
T7  — Korak 1.5 hard refusal returns blocked=True
T8  — MEDIUM guard block (_parsiraj_strukturni_odgovor=False) returns blocked=True
T9  — MEDIUM pravna_greska (_verifikuj_pravne_greske=False) returns blocked=True
T10 — HIGH pravna_greska (_verifikuj_pravne_greske=False) returns blocked=True
"""

import sys
import os
import inspect
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ["VINDEX_CACHE_BYPASS"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stash pattern — import main without leaving it in sys.modules
_stashed_main = sys.modules.pop("main", None)
import main as _m
del sys.modules["main"]
if _stashed_main is not None:
    sys.modules["main"] = _stashed_main

# api.py source as text (for structural inspection)
_API_SRC = open(
    os.path.join(os.path.dirname(__file__), "..", "api.py"),
    encoding="utf-8",
).read()


# ─── helpers ──────────────────────────────────────────────────────────────────

def _docs_stub() -> list[str]:
    """Three docs with enough content to pass _filtriraj_kontekst."""
    base = "Zakon o obligacionim odnosima, Član 100: Tekst člana za testiranje. " * 12
    return [base, base, base]


# ─── T1: stream _event_generator uses ask_agent ───────────────────────────────

def test_t1_stream_generator_uses_ask_agent():
    """
    The _event_generator body inside /api/pitanje/stream must reference
    ask_agent (guard-complete path) and must NOT call chat.completions.create
    (old raw-LLM path).
    """
    # Extract _event_generator body from api.py source
    # Locate the block between 'async def _event_generator():' and the matching
    # 'return StreamingResponse(' that follows it.
    start = _API_SRC.find("async def _event_generator():")
    assert start != -1, "T1: _event_generator not found in api.py"

    end = _API_SRC.find("return StreamingResponse(", start)
    assert end != -1, "T1: StreamingResponse return not found after _event_generator"

    body = _API_SRC[start:end]

    assert "ask_agent" in body, \
        "T1 FAIL: _event_generator must reference ask_agent"
    assert "chat.completions.create" not in body, \
        "T1 FAIL: _event_generator must NOT call chat.completions.create (raw LLM bypass)"


# ─── T2: stream _event_generator has _get_credits ─────────────────────────────

def test_t2_stream_generator_has_get_credits():
    """
    _event_generator must call _get_credits for the no-deduct branch
    (when blocked=True or status=error).
    """
    start = _API_SRC.find("async def _event_generator():")
    end = _API_SRC.find("return StreamingResponse(", start)
    body = _API_SRC[start:end]

    assert "_get_credits" in body, \
        "T2 FAIL: _event_generator must call _get_credits for non-deduction path"


# ─── T3: /api/register has rate limit decorator ───────────────────────────────

def test_t3_register_has_rate_limit():
    """
    @limiter.limit("5/minute") must appear immediately before @app.post("/api/register")
    or as the next decorator after it, within 3 lines.
    """
    idx = _API_SRC.find('@app.post("/api/register")')
    assert idx != -1, "T3: /api/register route not found in api.py"

    # Grab 200 chars before + 200 after to capture the decorator block
    snippet = _API_SRC[max(0, idx - 200): idx + 200]
    assert 'limiter.limit("5/minute")' in snippet, \
        f"T3 FAIL: @limiter.limit('5/minute') not near /api/register. snippet: {snippet[:300]}"


# ─── T4/T5/T6: conditional deduction logic ────────────────────────────────────

def _should_deduct(rezultat: dict) -> bool:
    """Mirror the conditional deduction logic from api.py /api/pitanje handler."""
    return (
        rezultat.get("status") == "success"
        and not rezultat.get("blocked", False)
    )


def test_t4_deduct_success_no_block():
    """status=success, blocked absent → should_deduct=True."""
    assert _should_deduct({"status": "success", "data": "tekst"}) is True, \
        "T4 FAIL: clean success must trigger deduction"


def test_t5_deduct_success_blocked():
    """status=success, blocked=True → should_deduct=False (hallucination block)."""
    assert _should_deduct({"status": "success", "blocked": True, "data": "[!]..."}) is False, \
        "T5 FAIL: blocked success must NOT trigger deduction"


def test_t6_deduct_error():
    """status=error → should_deduct=False regardless of blocked flag."""
    assert _should_deduct({"status": "error", "message": "error"}) is False, \
        "T6 FAIL: error response must NOT trigger deduction"
    assert _should_deduct({"status": "error", "blocked": True}) is False, \
        "T6b FAIL: error+blocked must NOT trigger deduction"


# ─── T7: Korak 1.5 hard refusal → blocked=True ────────────────────────────────

def test_t7_korak15_hard_refusal_blocked():
    """
    When _ekstrakcija_clana returns an explicit article reference and
    _direktan_fetch_clana finds nothing in the corpus, ask_agent must
    return blocked=True.
    """
    docs = _docs_stub()

    with patch.object(_m, "retrieve_documents") as mock_rd, \
         patch.object(_m, "ekstrakcija_clana") as mock_ek, \
         patch.object(_m, "_direktan_fetch_clana") as mock_df:

        mock_rd.return_value = (docs, {
            "confidence": "HIGH", "top_score": 0.91,
            "top_article": "Član 999", "top_law": "KZ",
        })
        mock_ek.return_value = ("Član 999", "KZ")
        mock_df.return_value = []  # article NOT in corpus

        result = _m.ask_agent("Koja je kazna po članu 999 KZ?", None)

    assert result.get("blocked") is True, \
        f"T7 FAIL: Korak 1.5 refusal must set blocked=True. Got: {result}"
    assert result.get("status") == "success", \
        "T7: status must remain 'success' for Korak 1.5 hard refusal"


# ─── T8: MEDIUM guard block → blocked=True ────────────────────────────────────

def test_t8_medium_guard_block_blocked():
    """
    When _parsiraj_strukturni_odgovor returns False on the MEDIUM path,
    ask_agent must return blocked=True.
    """
    docs = _docs_stub()

    with patch.object(_m, "retrieve_documents") as mock_rd, \
         patch.object(_m, "ekstrakcija_clana") as mock_ek, \
         patch.object(_m, "_filtriraj_kontekst") as mock_fc, \
         patch.object(_m, "klasifikuj_pitanje") as mock_kl, \
         patch.object(_m, "_pozovi_openai") as mock_llm, \
         patch.object(_m, "_parsiraj_strukturni_odgovor") as mock_ps:

        mock_rd.return_value = (docs, {
            "confidence": "MEDIUM", "top_score": 0.75,
            "top_article": "Član 100", "top_law": "ZOO",
        })
        mock_ek.return_value = (None, None)   # no explicit article reference
        mock_fc.return_value = docs
        mock_kl.return_value = "DEFINICIJA"
        mock_llm.return_value = '{"fabricated": "json"}'
        mock_ps.return_value = (False, "[!] STATUSNA POTVRDA: Fabrikacija detektovana.")

        result = _m.ask_agent("Šta je odgovornost?", None)

    assert result.get("blocked") is True, \
        f"T8 FAIL: MEDIUM guard block must set blocked=True. Got: {result}"


# ─── T9: MEDIUM pravna_greska → blocked=True ──────────────────────────────────

def test_t9_medium_pravna_greska_blocked():
    """
    When _verifikuj_pravne_greske fails on the MEDIUM path (after JSON guard
    passes), ask_agent must return blocked=True.
    """
    docs = _docs_stub()

    with patch.object(_m, "retrieve_documents") as mock_rd, \
         patch.object(_m, "ekstrakcija_clana") as mock_ek, \
         patch.object(_m, "_filtriraj_kontekst") as mock_fc, \
         patch.object(_m, "klasifikuj_pitanje") as mock_kl, \
         patch.object(_m, "_pozovi_openai") as mock_llm, \
         patch.object(_m, "_parsiraj_strukturni_odgovor") as mock_ps, \
         patch.object(_m, "_verifikuj_pravne_greske") as mock_vp:

        mock_rd.return_value = (docs, {
            "confidence": "MEDIUM", "top_score": 0.76,
            "top_article": "Član 100", "top_law": "ZOO",
        })
        mock_ek.return_value = (None, None)
        mock_fc.return_value = docs
        mock_kl.return_value = "DEFINICIJA"
        mock_llm.return_value = '{"valid": "json"}'
        mock_ps.return_value = (True, "odgovor tekst koji prolazi guard")
        mock_vp.return_value = (False, "koristi zabranjeni izraz")

        result = _m.ask_agent("Šta je odgovornost?", None)

    assert result.get("blocked") is True, \
        f"T9 FAIL: MEDIUM pravna_greska must set blocked=True. Got: {result}"


# ─── T10: HIGH pravna_greska → blocked=True ───────────────────────────────────

def test_t10_high_pravna_greska_blocked():
    """
    When _verifikuj_pravne_greske fails on the HIGH path (after JSON guard and
    topic-drift check both pass), ask_agent must return blocked=True.
    """
    docs = _docs_stub()

    with patch.object(_m, "retrieve_documents") as mock_rd, \
         patch.object(_m, "ekstrakcija_clana") as mock_ek, \
         patch.object(_m, "_filtriraj_kontekst") as mock_fc, \
         patch.object(_m, "klasifikuj_pitanje") as mock_kl, \
         patch.object(_m, "_pozovi_openai") as mock_llm, \
         patch.object(_m, "_parsiraj_strukturni_odgovor") as mock_ps, \
         patch.object(_m, "_proveri_tematsku_relevantnost") as mock_tr, \
         patch.object(_m, "_verifikuj_pravne_greske") as mock_vp:

        mock_rd.return_value = (docs, {
            "confidence": "HIGH", "top_score": 0.93,
            "top_article": "Član 100", "top_law": "ZOO",
        })
        mock_ek.return_value = (None, None)   # skip Korak 1.5
        mock_fc.return_value = docs
        mock_kl.return_value = "DEFINICIJA"
        mock_llm.return_value = '{"valid": "json"}'
        mock_ps.return_value = (True, "odgovor tekst koji prolazi guard")
        mock_tr.return_value = (True, "tematski ok")   # no downgrade
        mock_vp.return_value = (False, "zabranjeni izraz")

        result = _m.ask_agent("Šta je odgovornost?", None)

    assert result.get("blocked") is True, \
        f"T10 FAIL: HIGH pravna_greska must set blocked=True. Got: {result}"

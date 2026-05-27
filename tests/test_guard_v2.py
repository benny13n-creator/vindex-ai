# -*- coding: utf-8 -*-
"""
Hallucination guard v2.0 unit tests — strict per-article logic.

Tests _proveri_halucinaciju directly (8 cases):
  T1 — article cited AND present in context → valid
  T2 — article cited ("Član"), NOT in context → invalid
  T3 — only exempt articles cited (ZOO structural) → valid
  T4 — exempt + non-exempt; non-exempt absent → invalid
  T5 — early-return marker ("nije pronađen u bazi") → valid always
  T6 — thin context (< 3 docs) → skip, valid
  T7 — no article citations, no quote → valid
  T8 — no article citations, but CITAT IZ ZAKONA absent from context → invalid
"""

import sys
import os
import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import real main module (handle mock installed by parallel test file)
_stashed_mock = sys.modules.pop("main", None)
import main as _real_main
_fn = _real_main._proveri_halucinaciju
del sys.modules["main"]
if _stashed_mock is not None:
    sys.modules["main"] = _stashed_mock


# ─── helpers ───────────────────────────────────────────────────────────────

def _make_docs(texts: list[str]) -> list[str]:
    """
    Wrap raw texts so combined length ≥ 500 chars and count ≥ 3.
    Padding text is generic legal boilerplate that contains no article numbers.
    """
    pad = (
        "Zakon o radu reguliše prava i obaveze zaposlenih i poslodavaca. "
        "Odredbe zakona primenjuju se na sve zaposlene. "
    )
    result = list(texts)
    while len(result) < 3:
        result.append(pad)
    while sum(len(d) for d in result) < 500:
        result.append(pad)
    return result


# ─── T1: article present in context → valid ─────────────────────────────────

def test_t1_article_present_in_context():
    """Član 162 cited AND in context → guard should pass (True, 'ok')."""
    docs = _make_docs([
        "Zakon o radu, Član 162: Poslodavac i zaposleni mogu ugovoriti zabranu konkurencije.",
    ])
    odgovor = (
        "Prema Član 162 Zakona o radu, poslodavac i zaposleni mogu ugovoriti "
        "zabranu konkurencije. Klauzula mora biti pisana i precizirana."
    )
    validan, razlog = _fn(odgovor, docs)
    assert validan is True, f"T1 FAIL: expected True, got False. razlog={razlog}"


# ─── T2: article cited but ABSENT from context → invalid ────────────────────

def test_t2_article_absent_from_context():
    """Član 999 cited but NOT in context → guard should block (False, ...)."""
    docs = _make_docs([
        "Zakon o radu, Član 162: Poslodavac i zaposleni mogu ugovoriti zabranu konkurencije.",
    ])
    # Odgovor cites Član 999 which is nowhere in docs
    odgovor = (
        "Prema Član 999 Zakona o radu, zabrana konkurencije može trajati "
        "najviše dve godine od prestanka radnog odnosa."
    )
    validan, razlog = _fn(odgovor, docs)
    assert validan is False, "T2 FAIL: expected False (fabricated Član 999), got True"
    assert "999" in razlog, f"T2: razlog should mention 999, got: {razlog}"


# ─── T3: only exempt (ZOO structural) articles → valid ───────────────────────

def test_t3_only_exempt_articles():
    """Člana 154 and 200 are in _FRAMEWORK_CLANOVI_EXEMPT → guard skips them, returns True."""
    docs = _make_docs([
        "Zakon o obligacionim odnosima reguliše naknadu štete.",
    ])
    # Docs do NOT contain Clan 154 or 200 — but they're exempt
    odgovor = (
        "Prema Član 154 ZOO, svako ko drugome prouzrokuje štetu dužan je da je naknadi. "
        "Član 200 ZOO reguliše nematerijalnu štetu."
    )
    validan, razlog = _fn(odgovor, docs)
    assert validan is True, f"T3 FAIL: expected True (all exempt), got False. razlog={razlog}"


# ─── T4: exempt + non-exempt; non-exempt absent → invalid ───────────────────

def test_t4_exempt_plus_fabricated():
    """Član 154 (exempt) + Član 87 (not exempt, not in context) → block."""
    docs = _make_docs([
        "Zakon o obligacionim odnosima reguliše naknadu štete.",
    ])
    odgovor = (
        "Prema Član 154 ZOO osnov je odgovornosti za štetu. "
        "Član 87 ZOO propisuje posebne uslove koje treba ispuniti."
    )
    validan, razlog = _fn(odgovor, docs)
    assert validan is False, "T4 FAIL: expected False (Član 87 fabricated), got True"
    assert "87" in razlog, f"T4: razlog should mention 87, got: {razlog}"


# ─── T5: early-return marker → always valid ──────────────────────────────────

def test_t5_early_return_marker():
    """'nije pronađen u bazi' marker → skip guard, return True."""
    docs = _make_docs([
        "Zakon o radu, Član 162: Zabrana konkurencije.",
    ])
    odgovor = (
        "Tražena odredba nije pronađen u bazi zakona RS. "
        "Nema informacija o članu koji je naveden."
    )
    validan, razlog = _fn(odgovor, docs)
    assert validan is True, f"T5 FAIL: expected True (marker), got False. razlog={razlog}"


# ─── T6: thin context (< 3 docs) → skip, valid ───────────────────────────────

def test_t6_thin_context_skip():
    """Less than 3 docs → guard skips, returns True (avoids false positives on bad retrieval)."""
    thin_docs = [
        "Zakon o radu, Član 162: kratko.",
        "Još jedan kratki odeljak.",
    ]
    # len(thin_docs) == 2 < 3 → guard must skip
    odgovor = "Prema Član 500 ZR, neka fabricirana odredba."
    validan, razlog = _fn(odgovor, thin_docs)
    assert validan is True, f"T6 FAIL: expected True (thin context skip), got False. razlog={razlog}"


# ─── T7: no article citations, no quote → valid ──────────────────────────────

def test_t7_no_citations_no_quote():
    """No article numbers cited, no CITAT IZ ZAKONA block → guard returns True."""
    docs = _make_docs([
        "Zakon o radu reguliše radne odnose.",
    ])
    odgovor = (
        "Zabrana konkurencije je ugovorna obaveza između poslodavca i zaposlenog. "
        "Ova obaveza mora biti precizirana u ugovoru o radu."
    )
    validan, razlog = _fn(odgovor, docs)
    assert validan is True, f"T7 FAIL: expected True (no citations), got False. razlog={razlog}"


# ─── T8: quote present but absent from context → invalid ─────────────────────

def test_t8_fabricated_quote():
    """No article nums, but CITAT IZ ZAKONA block with text NOT in context → block."""
    docs = _make_docs([
        "Zakon o radu reguliše radne odnose.",
    ])
    # odgovor has no Član citations, but has a CITAT IZ ZAKONA block not in docs
    odgovor = (
        "Zakon o radu propisuje sledeće:\n\n"
        'CITAT IZ ZAKONA: "Zaposleni koji prekrši zabranu konkurencije dužan je da plati penale u visini godišnje zarade."\n\n'
        "Ova odredba je jasno definisana u zakonu."
    )
    validan, razlog = _fn(odgovor, docs)
    assert validan is False, "T8 FAIL: expected False (quote not in context), got True"
    assert "citat" in razlog.lower() or "pronađen" in razlog.lower(), \
        f"T8: razlog should mention citat/nije pronađen, got: {razlog}"

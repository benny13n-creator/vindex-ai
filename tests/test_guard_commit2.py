# -*- coding: utf-8 -*-
"""
Hallucination guard — Commit 2/3: NACRT + ANALIZA unit tests (7 cases).

NACRT:
  T1 — _dohvati_nacrt_kontekst("ugovor_neodredjeno") → returns non-empty list
  T2 — ask_nacrt: output cites article FROM retrieved context → PASS (not blocked)
  T3 — ask_nacrt: output cites article NOT in retrieved context → hard block

ANALIZA:
  T4 — doc cites ZR čl. 162, analiza cites ZR čl. 162 → PASS
  T5 — doc cites ZR čl. 162, analiza cites ZR čl. 175 (not in doc) → HARD block ← EXPLICIT
  T6 — doc without any article citations, analiza attempts to cite → HARD block
  T7 — _proveri_analiza_citate with empty allowed_pairs → blocks any citation
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_stashed_mock = sys.modules.pop("main", None)
import main as _m
del sys.modules["main"]
if _stashed_mock is not None:
    sys.modules["main"] = _stashed_mock

_dohvati_nacrt_kontekst = _m._dohvati_nacrt_kontekst
_ekstrahuj_clanove_iz_dokumenta = _m._ekstrahuj_clanove_iz_dokumenta
_proveri_analiza_citate = _m._proveri_analiza_citate
ask_nacrt = _m.ask_nacrt
ask_analiza = _m.ask_analiza


# ─── helpers ─────────────────────────────────────────────────────────────────

def _fake_match(clan_label: str, zakon: str, tekst: str) -> MagicMock:
    """Build a minimal Pinecone match mock with metadata."""
    m = MagicMock()
    m.metadata = {
        "law": zakon,
        "article": clan_label,
        "text": tekst,
        "parent_text": tekst,
    }
    m.id = f"fake-{clan_label}"
    m.score = 0.85
    return m


# ─── NACRT T1: _dohvati_nacrt_kontekst ───────────────────────────────────────

def test_t1_nacrt_kontekst_returns_nonempty():
    """
    _dohvati_nacrt_kontekst('ugovor_neodredjeno') must return ≥1 doc when
    _direktan_fetch_clana is mocked to return a valid match.
    """
    fake = _fake_match("Član 30", "zakon o radu",
                       "Zakon o radu, Član 30: Ugovor o radu zaključuje se u pisanoj formi.")

    with patch.object(_m, "_direktan_fetch_clana", return_value=[fake]):
        docs = _dohvati_nacrt_kontekst("ugovor_neodredjeno")

    assert len(docs) >= 1, f"T1 FAIL: expected ≥1 doc, got {len(docs)}"
    assert "Član 30" in docs[0] or "zakon o radu" in docs[0].lower(), \
        f"T1 FAIL: doc content unexpected: {docs[0][:100]}"


# ─── NACRT T2: ask_nacrt passes when cited article is in context ───────────────

def test_t2_nacrt_legit_article_not_blocked():
    """
    ask_nacrt: LLM output cites article that IS in fetched context → not blocked.
    """
    fake = _fake_match(
        "Član 30", "zakon o radu",
        "Zakon o radu, Član 30: Ugovor o radu zaključuje se u pisanoj formi. " * 5
    )
    ctx_text = (
        "ZAKON: zakon o radu\nČLAN: Član 30\n\n"
        "CITABILNI TEKST: Ugovor o radu zaključuje se u pisanoj formi. " * 3
    )

    with patch.object(_m, "_direktan_fetch_clana", return_value=[fake, fake, fake]), \
         patch.object(_m, "_pozovi_openai",
                      return_value=(
                          "PRAVNI OSNOV: Zakon o radu Član 30.\n\n"
                          "NACRT:\nUgovor o radu zaključen je u skladu sa Zakonom o radu Član 30."
                      )), \
         patch.object(_m, "_verifikuj_pravne_greske", return_value=(True, "")), \
         patch.object(_m, "_dodaj_disclaimer", side_effect=lambda x: x):

        rezultat = ask_nacrt("ugovor_neodredjeno", "Zapošljavam Jana Jankovića na neodređeno.")

    assert "[!] UPOZORENJE" not in (rezultat.get("data") or ""), \
        "T2 FAIL: legitimate Član 30 should NOT trigger block"
    assert rezultat.get("status") == "success", f"T2 FAIL: {rezultat}"


# ─── NACRT T3: ask_nacrt blocks when cited article is NOT in context ────────────

def test_t3_nacrt_fabricated_article_blocked():
    """
    ask_nacrt: LLM output cites Član 999 which is NOT in fetched context → hard block.
    """
    fake = _fake_match(
        "Član 30", "zakon o radu",
        "Zakon o radu, Član 30: Ugovor o radu zaključuje se u pisanoj formi. " * 5
    )

    with patch.object(_m, "_direktan_fetch_clana", return_value=[fake, fake, fake]), \
         patch.object(_m, "_pozovi_openai",
                      return_value=(
                          "PRAVNI OSNOV: Zakon o radu Član 999.\n\n"
                          "NACRT:\nSkladu sa Član 999 ZR, ugovor se zaključuje."
                      )):

        rezultat = ask_nacrt("ugovor_neodredjeno", "Zapošljavam Jana Jankovića na neodređeno.")

    assert "[!] UPOZORENJE" in (rezultat.get("data") or ""), \
        "T3 FAIL: fabricated Član 999 must trigger block"
    assert rezultat.get("status") == "success"


# ─── ANALIZA T4: doc has Član 162, analiza cites Član 162 → PASS ───────────────

def test_t4_analiza_legit_citation_passes():
    """
    ask_analiza: document contains 'Član 162', analysis cites 'Član 162' → allowed.
    """
    doc = (
        "UGOVOR O RADU\n"
        "Član 1: Zabrana konkurencije u skladu sa Član 162 Zakona o radu.\n"
        "Zaposleni se obavezuje da po prestanku radnog odnosa neće raditi konkurentski posao."
    )

    with patch.object(_m, "_pozovi_openai",
                      return_value=(
                          "PRAVNI OSNOV: Zakon o radu Član 162.\n\n"
                          "ANALIZA: Ugovor sadrži klauzulu zabrane konkurencije prema Član 162 ZR."
                      )), \
         patch.object(_m, "_verifikuj_pravne_greske", return_value=(True, "")), \
         patch.object(_m, "_ogranici_pouzdanost", side_effect=lambda x: x), \
         patch.object(_m, "_dodaj_disclaimer", side_effect=lambda x: x):

        rezultat = ask_analiza(doc, "")

    assert "[!] ANALIZA BLOKIRANA" not in (rezultat.get("data") or ""), \
        "T4 FAIL: Član 162 is in document, should NOT be blocked"
    assert rezultat.get("status") == "success"


# ─── ANALIZA T5: doc has Član 162, analiza cites Član 175 (not in doc) → BLOCK ──

def test_t5_analiza_new_article_blocked():
    """
    EXPLICIT REQUIRED PASS.
    ask_analiza: document has Član 162. Analysis cites Član 175 (not in doc) → HARD BLOCK.
    """
    doc = (
        "UGOVOR O RADU\n"
        "Član 1: Zabrana konkurencije u skladu sa Član 162 Zakona o radu.\n"
        "Zaposleni ne sme da radi kod konkurencije dve godine po prestanku."
    )

    with patch.object(_m, "_pozovi_openai",
                      return_value=(
                          "PRAVNI OSNOV: Zakon o radu Član 162 i Član 175.\n\n"
                          "ANALIZA: Klauzula je u skladu sa Član 162 ZR. "
                          "Prema Član 175 ZR, zaposleni ima pravo na otkazni rok."
                      )):

        rezultat = ask_analiza(doc, "")

    assert "[!] ANALIZA BLOKIRANA" in (rezultat.get("data") or ""), \
        "T5 FAIL (EXPLICIT): Član 175 not in document → HARD BLOCK required"
    assert "175" in (rezultat.get("data") or ""), \
        "T5 FAIL: block message should mention Član 175"
    assert rezultat.get("status") == "success"


# ─── ANALIZA T6: doc without article citations → LLM citations ALLOWED ──────────
# Behavior changed: empty allowed_articles now means "document has no inline article
# refs" (standard contract) → guard passes through to avoid over-blocking real use.

def test_t6_analiza_no_doc_articles_blocks_any_citation():
    """
    ask_analiza: document has NO article citations. LLM adds Član 30.
    New behavior: guard passes through — standard contracts without inline 'Član N'
    refs are not blocked (Suzana fix).
    """
    doc = (
        "UGOVOR O RADU\n"
        "Zaposleni i poslodavac zaključuju ugovor o radu na neodređeno vreme. "
        "Zarada iznosi 80.000 dinara mesečno. Radno vreme je 40 sati nedeljno."
    )

    with patch.object(_m, "_pozovi_openai",
                      return_value=(
                          "PRAVNI OSNOV: Zakon o radu Član 30.\n\n"
                          "ANALIZA: Ugovor treba da sadrži elemente iz Član 30 ZR."
                      )):

        rezultat = ask_analiza(doc, "")

    assert "[!] ANALIZA BLOKIRANA" not in (rezultat.get("data") or ""), \
        "T6 FAIL: empty allowed_articles must no longer block — standard contracts pass through"
    assert rezultat.get("status") == "success", "T6 FAIL: status mora biti success"


# ─── ANALIZA T7: _proveri_analiza_citate with empty allowed_articles → PASS ─────

def test_t7_proveri_analiza_citate_empty_allowed_blocks():
    """
    _proveri_analiza_citate(output, frozenset()) → passes through.
    New behavior: empty allowed_articles means document has no inline article refs,
    not that all citations are forbidden.
    """
    output_with_citation = (
        "ANALIZA: U skladu sa Član 30 Zakona o radu, ugovor mora biti u pisanoj formi."
    )
    validan, razlog = _proveri_analiza_citate(output_with_citation, frozenset())
    assert validan is True, \
        "T7 FAIL: empty allowed_articles + any citation → must return True (pass through)"
    assert razlog == "ok", f"T7 FAIL: razlog should be 'ok', got: {razlog}"

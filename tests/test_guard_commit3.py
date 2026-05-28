# -*- coding: utf-8 -*-
"""
Hallucination guard — Commit 3/3: Structured JSON output enforcement (7 cases).

T1 — JSON parse success → serialized to --- text, guard passes
T2 — JSON parse failure → graceful hallucination block, no crash
T3 — JSON with fabricated citat_zakona (not in docs) → guard blocks
T4 — JSON with valid citat_zakona from context → passes, marker text present
T5 — _json_ka_tekst PARNICA → contains --- ANALIZA ŠTETE, --- PROCESNI KORACI
T6 — _json_ka_tekst COMPLIANCE → contains --- COMPLIANCE KORACI
T7 — _json_ka_tekst empty citat → serializes as [—]
"""

import sys
import os
import json
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

_parsiraj = _m._parsiraj_strukturni_odgovor
_json_ka_tekst = _m._json_ka_tekst
_JSON_SCHEMA_MAP = _m._JSON_SCHEMA_MAP


# ─── helper ──────────────────────────────────────────────────────────────────

def _build_json_parnica(
    citat_zakona: str = "Zakon o obligacionim odnosima, Član 155: Šteta se nadoknađuje.",
    pravni_osnov: str = "ZOO čl. 155",
    pravni_zakljucak: str = "Tužilac ima pravo na naknadu štete.",
    statusna_potvrda_status: str = "ok",
    statusna_potvrda_tekst: str = "Verifikovano",
) -> str:
    return json.dumps({
        "statusna_potvrda_status": statusna_potvrda_status,
        "statusna_potvrda_tekst": statusna_potvrda_tekst,
        "hijerarhija_izvora": "ZOO (primarni)",
        "pravni_zakljucak": pravni_zakljucak,
        "analiza_stete": "Materijalna i nematerijalna šteta.",
        "procena_vrednosti": "Oko 500.000 RSD.",
        "citat_zakona": citat_zakona,
        "pravni_osnov": pravni_osnov,
        "rizici_i_izuzeci": "Zastarelost 3 godine.",
        "kada_ne_vazi": "Nema dokaza o šteti.",
        "procesni_koraci": "1. Tužba 2. Veštačenje",
        "kljucno_pitanje": "Da li postoji uzročna veza?",
        "potrebne_informacije": "Medicinska dokumentacija.",
        "izvor": "Zakon o obligacionim odnosima (Sl. glasnik RS, br. 29/1978)",
    }, ensure_ascii=False)


def _docs_with_zoo_155() -> list[str]:
    """Return 3+ docs containing Član 155 but not Član 999 — satisfies guard's
    len(docs) >= 3 threshold so fabrication detection actually fires."""
    base = (
        "Zakon o obligacionim odnosima, Član 155: Šteta se nadoknađuje. "
        "Ko drugome prouzrokuje štetu dužan je naknaditi je. " * 5
    )
    return [
        base,
        "Zakon o obligacionim odnosima, Član 155: Svako je dužan da se uzdrži od "
        "postupka kojim se može drugome prouzrokovati šteta. " * 4,
        "Zakon o obligacionim odnosima, Član 155: Naknada štete obuhvata stvarnu "
        "štetu i izmaklu korist. " * 4,
    ]


# ─── T1: JSON parse success → serialized to --- text, guard passes ────────────

def test_t1_json_parse_success_serialized():
    """
    Valid JSON with citat_zakona from docs → parse succeeds, output contains
    --- marker sections expected by frontend.
    """
    raw = _build_json_parnica()
    docs = _docs_with_zoo_155()

    uspeh, tekst = _parsiraj(raw, "PARNICA", docs)

    assert uspeh is True, f"T1 FAIL: expected success, got block: {tekst[:200]}"
    assert "--- HIJERARHIJA IZVORA" in tekst, "T1 FAIL: missing --- HIJERARHIJA IZVORA"
    assert "--- PRAVNI ZAKLJUČAK" in tekst, "T1 FAIL: missing --- PRAVNI ZAKLJUČAK"
    assert "--- CITAT ZAKONA [RAG]" in tekst, "T1 FAIL: missing --- CITAT ZAKONA [RAG]"
    assert "--- PRAVNI OSNOV" in tekst, "T1 FAIL: missing --- PRAVNI OSNOV"
    assert "STATUSNA POTVRDA" in tekst, "T1 FAIL: missing STATUSNA POTVRDA"


# ─── T2: JSON parse failure → graceful block, no crash ────────────────────────

def test_t2_json_parse_failure_graceful():
    """
    Invalid JSON input → _parsiraj_strukturni_odgovor returns (False, block_text)
    without crashing. Block text contains expected block marker.
    """
    bad_json = "Ovo nije JSON. Slobodan tekst sa Član 155."
    docs = _docs_with_zoo_155()

    uspeh, tekst = _parsiraj(bad_json, "PARNICA", docs)

    assert uspeh is False, "T2 FAIL: expected failure on bad JSON"
    assert "[!] STATUSNA POTVRDA" in tekst or "UPOZORENJE" in tekst or "BLOKIRAN" in tekst, \
        f"T2 FAIL: expected block marker in output, got: {tekst[:200]}"
    # Must not crash — reaching here means no exception raised


# ─── T3: JSON with fabricated citat_zakona → guard blocks ─────────────────────

def test_t3_fabricated_citat_zakona_blocked():
    """
    JSON with citat_zakona citing Član 999 (not in docs) → structural guard fires,
    returns (False, block_text).
    """
    raw = _build_json_parnica(
        citat_zakona="Zakon o obligacionim odnosima, Član 999: Fiktivni član.",
        pravni_osnov="ZOO čl. 999",
        pravni_zakljucak="Prema Član 999 ZOO, tužilac ima pravo.",
    )
    docs = _docs_with_zoo_155()

    uspeh, tekst = _parsiraj(raw, "PARNICA", docs)

    assert uspeh is False, \
        "T3 FAIL: fabricated Član 999 must trigger structural guard block"
    assert "[!]" in tekst or "blokiran" in tekst.lower(), \
        f"T3 FAIL: block marker expected in output: {tekst[:200]}"


# ─── T4: JSON with valid citat_zakona → passes, marker text present ────────────

def test_t4_valid_citat_zakona_passes():
    """
    JSON with citat_zakona verbatim from docs → guard passes,
    serialized text contains expected marker sections.
    """
    raw = _build_json_parnica(
        citat_zakona="Zakon o obligacionim odnosima, Član 155: Šteta se nadoknađuje.",
        pravni_osnov="ZOO čl. 155",
    )
    docs = _docs_with_zoo_155()

    uspeh, tekst = _parsiraj(raw, "PARNICA", docs)

    assert uspeh is True, f"T4 FAIL: valid citat must pass guard: {tekst[:200]}"
    assert "--- CITAT ZAKONA [RAG]" in tekst, "T4 FAIL: missing citat sekcija"
    assert "--- PRAVNI OSNOV" in tekst, "T4 FAIL: missing pravni osnov sekcija"
    assert "Šteta se nadoknađuje" in tekst, "T4 FAIL: citat content not in serialized output"


# ─── T5: _json_ka_tekst PARNICA → type-specific sections present ───────────────

def test_t5_json_ka_tekst_parnica_sections():
    """
    _json_ka_tekst with PARNICA data → output contains PARNICA-specific markers:
    --- ANALIZA ŠTETE and --- PROCESNI KORACI.
    """
    data = {
        "statusna_potvrda_status": "ok",
        "statusna_potvrda_tekst": "Verifikovano",
        "hijerarhija_izvora": "ZOO",
        "pravni_zakljucak": "Postoji osnov za tužbu.",
        "analiza_stete": "Materijalna šteta 200k.",
        "procena_vrednosti": "200.000 RSD",
        "citat_zakona": "ZOO čl. 155: tekst.",
        "pravni_osnov": "ZOO čl. 155",
        "rizici_i_izuzeci": "Zastarelost.",
        "kada_ne_vazi": "Bez dokaza.",
        "procesni_koraci": "1. Tužba",
        "kljucno_pitanje": "Pitanje?",
        "potrebne_informacije": "Dokumenta.",
        "izvor": "ZOO",
    }

    tekst = _json_ka_tekst(data, "PARNICA")

    assert "--- ANALIZA ŠTETE" in tekst, "T5 FAIL: missing --- ANALIZA ŠTETE"
    assert "--- PROCESNI KORACI" in tekst, "T5 FAIL: missing --- PROCESNI KORACI"
    assert "--- PROCENA VREDNOSTI ZAHTEVA" in tekst, "T5 FAIL: missing --- PROCENA VREDNOSTI ZAHTEVA"
    assert "--- RIZICI I IZUZECI" in tekst, "T5 FAIL: missing --- RIZICI I IZUZECI"
    assert "--- KADA OVO NE VAŽI" in tekst, "T5 FAIL: missing --- KADA OVO NE VAŽI"


# ─── T6: _json_ka_tekst COMPLIANCE → type-specific sections present ───────────

def test_t6_json_ka_tekst_compliance_sections():
    """
    _json_ka_tekst with COMPLIANCE data → output contains COMPLIANCE-specific markers:
    --- ANALIZA USKLAĐENOSTI and --- COMPLIANCE KORACI.
    """
    data = {
        "statusna_potvrda_status": "warn",
        "statusna_potvrda_tekst": "Potrebna provera",
        "hijerarhija_izvora": "ZSPNFT",
        "pravni_zakljucak": "Subjekt mora prijaviti sumnjive transakcije.",
        "analiza_uskladjenosti": "KYC procedura nije kompletna.",
        "citat_zakona": "ZSPNFT čl. 30: KYC obaveza.",
        "pravni_osnov": "ZSPNFT čl. 30",
        "rizici_i_rokovi": "Kazna do 5M RSD.",
        "compliance_koraci": "1. Identifikuj klijenta 2. Podnesi STR",
        "kljucno_pitanje": "Da li postoji PEP?",
        "potrebne_informacije": "Izjava o vlasništvu.",
        "izvor": "ZSPNFT (Sl. glasnik RS, br. 113/2017)",
    }

    tekst = _json_ka_tekst(data, "COMPLIANCE")

    assert "--- ANALIZA USKLAĐENOSTI" in tekst, "T6 FAIL: missing --- ANALIZA USKLAĐENOSTI"
    assert "--- COMPLIANCE KORACI" in tekst, "T6 FAIL: missing --- COMPLIANCE KORACI"
    assert "--- RIZICI I ROKOVI" in tekst, "T6 FAIL: missing --- RIZICI I ROKOVI"
    assert "[~] STATUSNA POTVRDA" in tekst, "T6 FAIL: warn status symbol expected [~]"


# ─── T7: _json_ka_tekst empty citat → serializes as [—] ─────────────────────

def test_t7_empty_citat_zakona_serializes_as_dash():
    """
    When citat_zakona is empty or None, _json_ka_tekst must output '[—]'
    in the --- CITAT ZAKONA [RAG] section.
    """
    data_empty = {
        "statusna_potvrda_status": "err",
        "statusna_potvrda_tekst": "Nije verifikovano",
        "hijerarhija_izvora": "",
        "pravni_zakljucak": "",
        "citat_zakona": "",
        "pravni_osnov": "",
        "izvor": "",
    }
    tekst_empty = _json_ka_tekst(data_empty, "DEFINICIJA")
    assert "[—]" in tekst_empty, \
        f"T7 FAIL: empty citat should produce [—], got: {tekst_empty[:200]}"

    data_none = dict(data_empty)
    data_none["citat_zakona"] = None
    tekst_none = _json_ka_tekst(data_none, "DEFINICIJA")
    assert "[—]" in tekst_none, \
        f"T7 FAIL: None citat should produce [—], got: {tekst_none[:200]}"

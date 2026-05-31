# -*- coding: utf-8 -*-
"""
Commit 7a — Sudska praksa integration tests (8 cases).

T1 — retrieve_sudska_praksa() returns chunks with correct metadata fields
T2 — process_praksa_chunks gate: all top-3 scores < 0.56 → returns []
T3 — process_praksa_chunks dedup: 3 chunks same decision_number → 1 returned
T4 — JSON schemas (all 4 types) have sudska_praksa array field
T5 — _extract_praksa_citations parses (sud, broj_odluke) from output dict
T6 — _parsiraj_strukturni_odgovor blocks fabricated praksa citation
T7 — _json_ka_tekst renders SUDSKA PRAKSA section when decisions present
T8 — _json_ka_tekst does NOT render SUDSKA PRAKSA section when [] or absent
"""

import sys
import os
import json
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Import retrieve helpers (T1, T2, T3) ─────────────────────────────────────

from app.services.retrieve import (
    retrieve_sudska_praksa as _retrieve_sp,
    process_praksa_chunks  as _process_pc,
    PRAKSA_CONFIDENCE_MEDIUM_THRESHOLD as _GATE,
)

# ── Import main helpers (T4-T8) ───────────────────────────────────────────────

# Stash/restore so module-level side-effects don't conflict with other test files
_stashed = sys.modules.pop("main", None)
import main as _m
del sys.modules["main"]
if _stashed is not None:
    sys.modules["main"] = _stashed

_json_ka_tekst        = _m._json_ka_tekst
_extract_citations    = _m._extract_praksa_citations
_parsiraj             = _m._parsiraj_strukturni_odgovor
_JSON_SCHEMA_MAP      = _m._JSON_SCHEMA_MAP
_format_praksa_ctx    = _m._format_praksa_context


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_match(decision_number: str, court: str, score: float, text: str = "tekst odluke") -> MagicMock:
    """Build a mock Pinecone match object."""
    m = MagicMock()
    m.score = score
    m.metadata = {
        "decision_number": decision_number,
        "court": court,
        "decision_date": "2024-01-01",
        "matter": "radni_sporovi",
        "text": text,
    }
    return m


def _build_parnica_json(sudska_praksa=None, citat="Zakon o radu, Član 162: zabrana konkurencije"):
    """Build minimal valid PARNICA JSON string."""
    data = {
        "statusna_potvrda_status": "ok",
        "statusna_potvrda_tekst": "Verifikovano",
        "hijerarhija_izvora": "ZR (primarni)",
        "pravni_zakljucak": "Zabrana važi.",
        "analiza_stete": "—",
        "procena_vrednosti": "—",
        "citat_zakona": citat,
        "pravni_osnov": "ZR čl. 162",
        "rizici_i_izuzeci": "—",
        "kada_ne_vazi": "—",
        "procesni_koraci": "1. Tužba",
        "kljucno_pitanje": "Da li važi klauzula?",
        "potrebne_informacije": "—",
        "izvor": "Zakon o radu (Sl. glasnik RS)",
    }
    if sudska_praksa is not None:
        data["sudska_praksa"] = sudska_praksa
    return json.dumps(data, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# T1 — retrieve_sudska_praksa() returns chunks with correct metadata structure
# ─────────────────────────────────────────────────────────────────────────────

def test_t1_retrieve_sudska_praksa_returns_metadata():
    """retrieve_sudska_praksa() calls _pretraga_praksa and returns raw matches."""
    m1 = _make_match("Гж 123/2022", "Apelacioni sud u Beogradu", 0.61)
    m2 = _make_match("Кж 456/2023", "Vrhovni sud", 0.55)

    with patch("app.services.retrieve._pretraga_praksa", return_value=[m1, m2]) as mock_p:
        with patch("app.services.retrieve._ugradi_query", return_value=[0.1] * 3072):
            results = _retrieve_sp("zabrana konkurencije", top_k=10)

    assert len(results) == 2
    assert results[0].score == 0.61
    assert results[0].metadata["decision_number"] == "Гж 123/2022"
    assert results[1].metadata["court"] == "Vrhovni sud"
    # Verify namespace param was passed
    mock_p.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# T2 — process_praksa_chunks gate: all top-3 < 0.56 → []
# ─────────────────────────────────────────────────────────────────────────────

def test_t2_gate_blocks_when_all_below_threshold():
    """Gate fires when all top-3 scores are below PRAKSA_CONFIDENCE_MEDIUM_THRESHOLD."""
    chunks = [
        _make_match("DN1", "Sud A", 0.48),
        _make_match("DN2", "Sud B", 0.47),
        _make_match("DN3", "Sud C", 0.46),
        _make_match("DN4", "Sud D", 0.45),
    ]
    result = _process_pc(chunks, k=3)
    assert result == [], f"Expected empty list, got {result}"


def test_t2_gate_passes_when_at_least_one_above_threshold():
    """Gate does NOT fire when at least one top-3 score ≥ threshold."""
    chunks = [
        _make_match("DN1", "Sud A", 0.57),   # ≥ 0.56
        _make_match("DN2", "Sud B", 0.49),
        _make_match("DN3", "Sud C", 0.48),
    ]
    result = _process_pc(chunks, k=3)
    assert len(result) == 3


# ─────────────────────────────────────────────────────────────────────────────
# T3 — process_praksa_chunks dedup: same decision_number → keep 1
# ─────────────────────────────────────────────────────────────────────────────

def test_t3_dedup_same_decision_number():
    """Three chunks with same decision_number → only highest-score chunk kept."""
    chunks = [
        _make_match("DN_SAME", "Sud A", 0.72, "tekst 1"),
        _make_match("DN_SAME", "Sud A", 0.68, "tekst 2"),
        _make_match("DN_SAME", "Sud A", 0.61, "tekst 3"),
    ]
    result = _process_pc(chunks, k=3)
    assert len(result) == 1, f"Expected 1 unique decision, got {len(result)}"
    assert result[0]["score"] == 0.72


def test_t3_dedup_keeps_multiple_distinct_decisions():
    """Three chunks with different decision_numbers → all 3 kept."""
    chunks = [
        _make_match("DN_A", "Sud A", 0.72),
        _make_match("DN_B", "Sud B", 0.68),
        _make_match("DN_C", "Sud C", 0.61),
    ]
    result = _process_pc(chunks, k=3)
    assert len(result) == 3


# ─────────────────────────────────────────────────────────────────────────────
# T4 — All 4 JSON schemas have sudska_praksa array field
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tip", ["PARNICA", "COMPLIANCE", "PORESKI", "DEFINICIJA"])
def test_t4_json_schema_has_sudska_praksa(tip):
    """All 4 schema types contain sudska_praksa as an array field."""
    schema = _JSON_SCHEMA_MAP[tip]
    props = schema["json_schema"]["schema"]["properties"]
    assert "sudska_praksa" in props, f"Schema {tip} missing sudska_praksa field"
    sp = props["sudska_praksa"]
    assert sp["type"] == "array", f"Schema {tip}: sudska_praksa must be array, got {sp['type']}"
    # items must define the required sub-fields
    item_props = sp["items"]["properties"]
    assert "sud" in item_props
    assert "broj_odluke" in item_props
    assert "sazetak_relevantnosti" in item_props


# ─────────────────────────────────────────────────────────────────────────────
# T5 — _extract_praksa_citations parses (sud, broj_odluke) pairs
# ─────────────────────────────────────────────────────────────────────────────

def test_t5_extract_citations_normal():
    """Extract (sud, broj_odluke) pairs from a populated sudska_praksa array."""
    data = {
        "sudska_praksa": [
            {"sud": "Apelacioni sud u Beogradu", "broj_odluke": "Gž 123/2022", "sazetak_relevantnosti": "Relevantno."},
            {"sud": "Vrhovni sud", "broj_odluke": "Kzz 456/2023", "sazetak_relevantnosti": "Relevantno."},
        ]
    }
    pairs = _extract_citations(data)
    assert len(pairs) == 2
    assert ("Apelacioni sud u Beogradu", "Gž 123/2022") in pairs
    assert ("Vrhovni sud", "Kzz 456/2023") in pairs


def test_t5_extract_citations_empty_array():
    """Empty sudska_praksa array → empty citation list."""
    data = {"sudska_praksa": []}
    assert _extract_citations(data) == []


def test_t5_extract_citations_missing_key():
    """Missing sudska_praksa key → empty citation list."""
    data = {"pravni_zakljucak": "nema praksa polje"}
    assert _extract_citations(data) == []


def test_t5_extract_citations_ignores_short_dn():
    """Decision numbers shorter than 3 chars are ignored."""
    data = {
        "sudska_praksa": [
            {"sud": "Sud X", "broj_odluke": "AB", "sazetak_relevantnosti": "x"}  # too short
        ]
    }
    assert _extract_citations(data) == []


# ─────────────────────────────────────────────────────────────────────────────
# T6 — _parsiraj_strukturni_odgovor blocks fabricated praksa citation
# ─────────────────────────────────────────────────────────────────────────────

def test_t6_guard_blocks_fabricated_praksa():
    """
    When sudska_praksa cites a decision NOT in provided praksa_context → guard blocks.
    """
    # Context only mentions DN_REAL, not DN_FAKE
    praksa_ctx = "SUDSKA PRAKSA:\n1. Apelacioni sud u Beogradu, DN_REAL, 2023-01-01\n   Sažetak: tekst"
    docs_law = ["ZAKON: zakon o radu\nČLAN: Član 162\n\nCITABILNI TEKST: Zabrana konkurencije."]

    raw_json = _build_parnica_json(
        sudska_praksa=[
            {"sud": "Nepostojeci sud", "broj_odluke": "DN_FAKE_XYZ_999",
             "sazetak_relevantnosti": "fabrikovano"},
        ],
        citat="zakon o radu, Član 162: zabrana"
    )

    ok, msg = _parsiraj(raw_json, "PARNICA", docs_law, praksa_context=praksa_ctx)
    assert not ok, "Expected guard to BLOCK fabricated praksa citation"
    assert "DN_FAKE_XYZ_999" in msg or "Sudska praksa" in msg


def test_t6_guard_allows_verified_praksa():
    """
    When sudska_praksa cites a decision that IS in praksa_context → guard passes.
    """
    dn = "Gž 1234/2022"
    praksa_ctx = f"SUDSKA PRAKSA:\n1. Apelacioni sud u Beogradu, {dn}, 2022-06-15\n   Sažetak: tekst"
    docs_law = [
        "ZAKON: zakon o radu\nČLAN: Član 162\n\nCITABILNI TEKST: Zabrana konkurencije Član 162."
    ]

    raw_json = _build_parnica_json(
        sudska_praksa=[
            {"sud": "Apelacioni sud u Beogradu", "broj_odluke": dn,
             "sazetak_relevantnosti": "Odluka potvrđuje zabranu konkurencije."},
        ],
        citat="zakon o radu, Član 162: zabrana"
    )

    ok, _ = _parsiraj(raw_json, "PARNICA", docs_law, praksa_context=praksa_ctx)
    assert ok, "Expected guard to PASS for verified praksa citation"


def test_t6_guard_passes_when_no_praksa_context():
    """Without praksa_context, existing guard is unchanged (backward compat)."""
    docs_law = [
        "ZAKON: zakon o radu\nČLAN: Član 162\n\nCITABILNI TEKST: Zabrana konkurencije Član 162."
    ]
    raw_json = _build_parnica_json(
        sudska_praksa=[],
        citat="zakon o radu, Član 162: zabrana"
    )
    ok, _ = _parsiraj(raw_json, "PARNICA", docs_law)  # no praksa_context
    assert ok


# ─────────────────────────────────────────────────────────────────────────────
# T7 — _json_ka_tekst renders SUDSKA PRAKSA section when decisions present
# ─────────────────────────────────────────────────────────────────────────────

def test_t7_json_ka_tekst_renders_sudska_praksa():
    """When sudska_praksa array is non-empty → --- SUDSKA PRAKSA section rendered."""
    data = {
        "statusna_potvrda_status": "ok",
        "statusna_potvrda_tekst": "Verifikovano",
        "hijerarhija_izvora": "ZR",
        "pravni_zakljucak": "Zabrana važi.",
        "analiza_stete": "—",
        "procena_vrednosti": "—",
        "citat_zakona": "ZR čl. 162",
        "pravni_osnov": "ZR čl. 162",
        "rizici_i_izuzeci": "—",
        "kada_ne_vazi": "—",
        "procesni_koraci": "1. Tužba",
        "kljucno_pitanje": "?",
        "potrebne_informacije": "—",
        "izvor": "Sl. glasnik RS",
        "sudska_praksa": [
            {
                "sud": "Apelacioni sud u Nišu",
                "broj_odluke": "Gž1 123/2022",
                "datum": "2022-05-12",
                "sazetak_relevantnosti": "Zabrana bez naknade je ništava.",
            }
        ],
    }
    output = _json_ka_tekst(data, "PARNICA")
    assert "--- SUDSKA PRAKSA" in output
    assert "Apelacioni sud u Nišu" in output
    assert "Gž1 123/2022" in output
    assert "Zabrana bez naknade je ništava." in output


def test_t7_json_ka_tekst_renders_multiple_decisions():
    """Three decisions → all three rendered in order."""
    data = {
        "statusna_potvrda_status": "ok",
        "statusna_potvrda_tekst": "Verifikovano",
        "hijerarhija_izvora": "ZR",
        "pravni_zakljucak": "Zabrana važi.",
        "analiza_stete": "—",
        "procena_vrednosti": "—",
        "citat_zakona": "ZR čl. 162",
        "pravni_osnov": "ZR čl. 162",
        "rizici_i_izuzeci": "—",
        "kada_ne_vazi": "—",
        "procesni_koraci": "—",
        "kljucno_pitanje": "—",
        "potrebne_informacije": "—",
        "izvor": "ZR",
        "sudska_praksa": [
            {"sud": "Sud A", "broj_odluke": "A/1", "datum": "", "sazetak_relevantnosti": "sa1"},
            {"sud": "Sud B", "broj_odluke": "B/2", "datum": "", "sazetak_relevantnosti": "sb2"},
            {"sud": "Sud C", "broj_odluke": "C/3", "datum": "", "sazetak_relevantnosti": "sc3"},
        ],
    }
    output = _json_ka_tekst(data, "PARNICA")
    assert "1. Sud A, A/1" in output
    assert "2. Sud B, B/2" in output
    assert "3. Sud C, C/3" in output


# ─────────────────────────────────────────────────────────────────────────────
# T8 — _json_ka_tekst does NOT render SUDSKA PRAKSA when empty or absent
# ─────────────────────────────────────────────────────────────────────────────

def _base_parnica_data(**kwargs):
    base = {
        "statusna_potvrda_status": "ok",
        "statusna_potvrda_tekst": "Verifikovano",
        "hijerarhija_izvora": "ZR",
        "pravni_zakljucak": "—",
        "analiza_stete": "—",
        "procena_vrednosti": "—",
        "citat_zakona": "ZR čl. 162",
        "pravni_osnov": "ZR čl. 162",
        "rizici_i_izuzeci": "—",
        "kada_ne_vazi": "—",
        "procesni_koraci": "—",
        "kljucno_pitanje": "—",
        "potrebne_informacije": "—",
        "izvor": "ZR",
    }
    base.update(kwargs)
    return base


def test_t8_no_sudska_praksa_section_when_empty_array():
    """Empty sudska_praksa array → no --- SUDSKA PRAKSA section in output."""
    data = _base_parnica_data(sudska_praksa=[])
    output = _json_ka_tekst(data, "PARNICA")
    assert "--- SUDSKA PRAKSA" not in output


def test_t8_no_sudska_praksa_section_when_key_absent():
    """Missing sudska_praksa key → no --- SUDSKA PRAKSA section in output."""
    data = _base_parnica_data()
    output = _json_ka_tekst(data, "PARNICA")
    assert "--- SUDSKA PRAKSA" not in output

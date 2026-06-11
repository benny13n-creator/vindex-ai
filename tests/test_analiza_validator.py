# -*- coding: utf-8 -*-
"""
Testovi za analiza/validator.py (Slojevi 3, 9, 10).
Svi testovi su offline — bez LLM poziva.
"""

import json
import pytest
from analiza.segmenter import segment_document
from analiza.validator import (
    parse_llm_response,
    validate_clause_excerpts,
    validate_clause_refs,
    compute_executive_summary,
    validate_law_refs,
    run_validation_pipeline,
)

# ─── Fixture dokumenti ───────────────────────────────────────────────────────

UGOVOR_TEKST = """UGOVOR O RADU

Ugovorne strane:
Poslodavac: DOO Test

zaključuju sledeći ugovor:

Član 1
Predmet ugovora. Poslodavac zasniva radni odnos sa zaposlenim.

Član 2
Zarada zaposlenog iznosi 100.000 dinara mesečno.

Član 3
Raskid ugovora bez otkaznog roka dozvoljen je samo u slučaju krivice zaposlenog.

Član 4
Ugovorna kazna iznosi 10% godišnje zarade u slučaju otkaza od strane zaposlenog.
"""

VALID_JSON_RESPONSE = json.dumps({
    "document_type": "ugovor",
    "findings": [
        {
            "id": "f1",
            "category": "pravni_rizik",
            "severity": "visok",
            "clause_ref": "clause_3",
            "clause_excerpt": "Raskid ugovora bez otkaznog roka dozvoljen je samo u slučaju krivice zaposlenog.",
            "law_ref": "član 178 Zakona o radu",
            "finding": "Raskid bez otkaznog roka je ograničen na slučajeve krivice (ZR čl. 179).",
            "suggested_fix": "Dodati otkazni rok od minimum 8 dana.",
            "confidence": 90,
        },
        {
            "id": "f2",
            "category": "finansijski",
            "severity": "srednji",
            "clause_ref": "clause_4",
            "clause_excerpt": "Ugovorna kazna iznosi 10% godišnje zarade",
            "law_ref": None,
            "finding": "Ugovorna kazna od 10% godišnje zarade može biti visoka.",
            "suggested_fix": None,
            "confidence": 75,
        }
    ],
    "missing_clauses": [
        {
            "clause_name": "Viša sila",
            "why_it_matters": "Bez ove klauzule, strane su potpuno izložene riziku.",
            "suggested_text": None
        }
    ],
    "financial_exposure": {
        "max_total_exposure_rsd": 120000,
        "items": [
            {"type": "ugovorna_kazna", "clause_ref": "clause_4", "amount_or_formula": "10% od 1.200.000 = 120.000 RSD", "notes": "procena"}
        ]
    },
    "litigation_readiness": {
        "applicable": False,
        "evidence_gaps": [],
        "procedural_defects": [],
        "deadline_risks": []
    },
    "attack_surface": [
        {"vulnerability": "Odredba o raskidu je jednosmerna — favorizuje poslodavca.", "clause_ref": "clause_3", "severity": "srednji"}
    ],
    "low_confidence_findings": [],
    "legacy_text": "PRAVNI OSNOV: ZR\nANALIZA: Ugovor ima rizike.\nIDENTIFIKOVANI RIZICI: Raskid\nPREPORUKE: Dodati VŠ\nPOUZDANOST: 85%"
}, ensure_ascii=False)


# ─── parse_llm_response ───────────────────────────────────────────────────────

def test_parse_validan_json():
    parsed, is_fallback = parse_llm_response(VALID_JSON_RESPONSE)
    assert not is_fallback
    assert parsed["document_type"] == "ugovor"
    assert len(parsed["findings"]) == 2

def test_parse_strip_markdown_fences():
    with_fences = "```json\n" + VALID_JSON_RESPONSE + "\n```"
    parsed, is_fallback = parse_llm_response(with_fences)
    assert not is_fallback
    assert "document_type" in parsed

def test_parse_strip_preambula():
    with_preamble = "Evo JSON odgovor:\n\n" + VALID_JSON_RESPONSE
    parsed, is_fallback = parse_llm_response(with_preamble)
    assert not is_fallback
    assert "document_type" in parsed

def test_parse_nevalidan_json_fallback():
    parsed, is_fallback = parse_llm_response("Ovo nije JSON.")
    assert is_fallback
    assert parsed["_parse_error"] is True
    assert parsed["executive_summary"] is None
    assert "legacy_text" in parsed

def test_parse_retry_uspeva():
    good_json = json.dumps({"document_type": "ugovor", "findings": [], "missing_clauses": [],
                            "financial_exposure": {"max_total_exposure_rsd": None, "items": []},
                            "litigation_readiness": {"applicable": False, "evidence_gaps": [], "procedural_defects": [], "deadline_risks": []},
                            "attack_surface": [], "low_confidence_findings": [], "legacy_text": "test"})
    call_count = [0]
    def retry_fn():
        call_count[0] += 1
        return good_json
    parsed, is_fallback = parse_llm_response("invalidan json", retry_fn=retry_fn)
    assert not is_fallback
    assert call_count[0] == 1
    assert parsed["document_type"] == "ugovor"


# ─── validate_clause_excerpts ─────────────────────────────────────────────────

def test_validate_excerpts_validan():
    doc = segment_document(UGOVOR_TEKST)
    parsed, _ = parse_llm_response(VALID_JSON_RESPONSE)
    result = validate_clause_excerpts(parsed, doc)
    # "Raskid ugovora bez otkaznog roka" JE u tekstu
    assert any(f["id"] == "f1" for f in result["findings"])

def test_validate_excerpts_izmisljeni_excerpt():
    doc = segment_document(UGOVOR_TEKST)
    bad_json = json.dumps({
        "document_type": "ugovor",
        "findings": [{
            "id": "f_bad",
            "category": "pravni_rizik",
            "severity": "visok",
            "clause_ref": "clause_1",
            "clause_excerpt": "Ova rečenica ne postoji u dokumentu uopšte NIKAKO.",
            "law_ref": None,
            "finding": "Izmišljeni nalaz.",
            "suggested_fix": None,
            "confidence": 80,
        }],
        "missing_clauses": [], "financial_exposure": {"max_total_exposure_rsd": None, "items": []},
        "litigation_readiness": {"applicable": False, "evidence_gaps": [], "procedural_defects": [], "deadline_risks": []},
        "attack_surface": [], "low_confidence_findings": [], "legacy_text": ""
    }, ensure_ascii=False)
    parsed, _ = parse_llm_response(bad_json)
    result = validate_clause_excerpts(parsed, doc)
    # Neispravan excerpt mora otići u low_confidence
    assert len(result["findings"]) == 0
    assert len(result["low_confidence_findings"]) == 1
    assert result["low_confidence_findings"][0]["reason_excluded"] == "excerpt_not_found_in_source"

def test_validate_excerpts_null_excerpt_prolazi():
    doc = segment_document(UGOVOR_TEKST)
    null_excerpt_json = json.dumps({
        "document_type": "ugovor",
        "findings": [{"id": "f1", "category": "pravni_rizik", "severity": "nizak", "clause_ref": None,
                      "clause_excerpt": None, "law_ref": None, "finding": "Test.", "suggested_fix": None, "confidence": 80}],
        "missing_clauses": [], "financial_exposure": {"max_total_exposure_rsd": None, "items": []},
        "litigation_readiness": {"applicable": False, "evidence_gaps": [], "procedural_defects": [], "deadline_risks": []},
        "attack_surface": [], "low_confidence_findings": [], "legacy_text": ""
    })
    parsed, _ = parse_llm_response(null_excerpt_json)
    result = validate_clause_excerpts(parsed, doc)
    assert len(result["findings"]) == 1  # Null excerpt = OK


# ─── validate_clause_refs ─────────────────────────────────────────────────────

def test_validate_refs_validan():
    doc = segment_document(UGOVOR_TEKST)
    parsed, _ = parse_llm_response(VALID_JSON_RESPONSE)
    # Preskoči excerpt validation da testiramo samo refs
    parsed = validate_clause_refs(parsed, doc)
    # clause_3 i clause_4 postoje u ugovoru
    assert len(parsed["findings"]) == 2

def test_validate_refs_nepostojeci_ref():
    doc = segment_document(UGOVOR_TEKST)
    bad_ref_json = json.dumps({
        "document_type": "ugovor",
        "findings": [{"id": "f1", "category": "pravni_rizik", "severity": "nizak", "clause_ref": "clause_99",
                      "clause_excerpt": None, "law_ref": None, "finding": "Test.", "suggested_fix": None, "confidence": 80}],
        "missing_clauses": [], "financial_exposure": {"max_total_exposure_rsd": None, "items": []},
        "litigation_readiness": {"applicable": False, "evidence_gaps": [], "procedural_defects": [], "deadline_risks": []},
        "attack_surface": [], "low_confidence_findings": [], "legacy_text": ""
    })
    parsed, _ = parse_llm_response(bad_ref_json)
    result = validate_clause_refs(parsed, doc)
    assert len(result["findings"]) == 0
    assert result["low_confidence_findings"][0]["reason_excluded"].startswith("invalid_clause_ref")

def test_validate_refs_null_prolazi():
    doc = segment_document(UGOVOR_TEKST)
    null_ref_json = json.dumps({
        "document_type": "ugovor",
        "findings": [{"id": "f1", "category": "pravni_rizik", "severity": "nizak", "clause_ref": None,
                      "clause_excerpt": None, "law_ref": None, "finding": "Test.", "suggested_fix": None, "confidence": 80}],
        "missing_clauses": [], "financial_exposure": {"max_total_exposure_rsd": None, "items": []},
        "litigation_readiness": {"applicable": False, "evidence_gaps": [], "procedural_defects": [], "deadline_risks": []},
        "attack_surface": [], "low_confidence_findings": [], "legacy_text": ""
    })
    parsed, _ = parse_llm_response(null_ref_json)
    result = validate_clause_refs(parsed, doc)
    assert len(result["findings"]) == 1


# ─── compute_executive_summary ────────────────────────────────────────────────

def test_compute_summary_formula():
    parsed, _ = parse_llm_response(VALID_JSON_RESPONSE)
    result = compute_executive_summary(parsed)
    es = result["executive_summary"]
    assert 0 <= es["overall_risk_score"] <= 100
    assert es["risk_label"] in ("nizak", "srednji", "visok", "kritican")
    assert es["missing_clauses_count"] == 1
    assert es["recommendations_count"] >= 1

def test_compute_summary_prazno():
    empty = {"findings": [], "missing_clauses": [], "financial_exposure": {}, "litigation_readiness": {}}
    result = compute_executive_summary(empty)
    es = result["executive_summary"]
    assert es["overall_risk_score"] == 0
    assert es["risk_label"] == "nizak"
    assert es["critical_count"] == 0

def test_compute_summary_severity_scores_mapiran():
    parsed, _ = parse_llm_response(VALID_JSON_RESPONSE)
    result = compute_executive_summary(parsed)
    for f in result["findings"]:
        assert "severity_score" in f
        assert f["severity_score"] in (20, 50, 80, 100)

def test_compute_summary_kritican_score_visok():
    kritican_json = json.dumps({
        "findings": [
            {"id": "f1", "severity": "kritican", "confidence": 90, "category": "pravni_rizik",
             "clause_ref": None, "clause_excerpt": None, "law_ref": None, "finding": "Test.", "suggested_fix": None}
        ],
        "missing_clauses": [], "financial_exposure": {"max_total_exposure_rsd": None, "items": []},
        "litigation_readiness": {"applicable": False, "evidence_gaps": [], "procedural_defects": [], "deadline_risks": []},
        "attack_surface": [], "low_confidence_findings": [], "legacy_text": ""
    })
    parsed, _ = parse_llm_response(kritican_json)
    result = compute_executive_summary(parsed)
    es = result["executive_summary"]
    assert es["overall_risk_score"] == 100
    assert es["critical_count"] == 1


# ─── validate_law_refs ────────────────────────────────────────────────────────

def test_validate_law_refs_poznat():
    parsed, _ = parse_llm_response(VALID_JSON_RESPONSE)
    # f1 ima "član 178 Zakona o radu" — treba da prođe
    result = validate_law_refs(parsed)
    f1 = next(f for f in result["findings"] if f["id"] == "f1")
    assert f1["unverified_law_ref"] is False

def test_validate_law_refs_nepoznat():
    nepoznat_json = json.dumps({
        "findings": [{"id": "f1", "severity": "nizak", "category": "pravni_rizik",
                      "clause_ref": None, "clause_excerpt": None,
                      "law_ref": "Zakon o bezimenom strpljenju RS", "finding": "Test.",
                      "suggested_fix": None, "confidence": 80}],
        "missing_clauses": [], "financial_exposure": {"max_total_exposure_rsd": None, "items": []},
        "litigation_readiness": {"applicable": False, "evidence_gaps": [], "procedural_defects": [], "deadline_risks": []},
        "attack_surface": [], "low_confidence_findings": [], "legacy_text": ""
    })
    parsed, _ = parse_llm_response(nepoznat_json)
    result = validate_law_refs(parsed)
    f1 = next(f for f in result["findings"] if f["id"] == "f1")
    assert f1["unverified_law_ref"] is True

def test_validate_law_refs_null_prolazi():
    null_law_json = json.dumps({
        "findings": [{"id": "f1", "severity": "nizak", "category": "pravni_rizik",
                      "clause_ref": None, "clause_excerpt": None,
                      "law_ref": None, "finding": "Test.", "suggested_fix": None, "confidence": 80}],
        "missing_clauses": [], "financial_exposure": {"max_total_exposure_rsd": None, "items": []},
        "litigation_readiness": {"applicable": False, "evidence_gaps": [], "procedural_defects": [], "deadline_risks": []},
        "attack_surface": [], "low_confidence_findings": [], "legacy_text": ""
    })
    parsed, _ = parse_llm_response(null_law_json)
    result = validate_law_refs(parsed)
    f1 = next(f for f in result["findings"] if f["id"] == "f1")
    assert "unverified_law_ref" not in f1  # null law_ref se ne flaguje


# ─── run_validation_pipeline — E2E ───────────────────────────────────────────

def test_pipeline_e2e_validan():
    doc = segment_document(UGOVOR_TEKST)
    result = run_validation_pipeline(VALID_JSON_RESPONSE, doc)
    assert "executive_summary" in result
    assert result["executive_summary"] is not None
    assert "low_confidence_findings" in result
    assert result["executive_summary"]["overall_risk_score"] > 0

def test_pipeline_e2e_parse_greska_fallback():
    doc = segment_document(UGOVOR_TEKST)
    result = run_validation_pipeline("Ovo nije JSON!", doc)
    assert result["_parse_error"] is True
    assert result["executive_summary"] is None
    assert "legacy_text" in result

def test_pipeline_nikad_ne_baca():
    doc = segment_document(UGOVOR_TEKST)
    # Edge case: prazan JSON
    result = run_validation_pipeline("{}", doc)
    assert isinstance(result, dict)
    assert "low_confidence_findings" in result

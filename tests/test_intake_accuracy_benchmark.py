# -*- coding: utf-8 -*-
"""
Tests for scripts/intake_accuracy_benchmark.py's comparison/aggregation
logic. These use ONLY synthetic values to prove the harness computes
correctly — never presented as real accuracy data (see golden_dataset/
README.md: the real dataset ships empty on purpose).
"""
import sys, os, importlib.util
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _load_module():
    path = os.path.join(os.path.dirname(__file__), "..", "scripts", "intake_accuracy_benchmark.py")
    spec = importlib.util.spec_from_file_location("intake_accuracy_benchmark", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_normalize_collapses_whitespace_and_case():
    mod = _load_module()
    assert mod._normalize("  Osnovni   Sud U Beogradu.  ") == "osnovni sud u beogradu"


def test_values_match_none_expected_is_not_applicable_always_true():
    mod = _load_module()
    assert mod._values_match("deadline", None, None) is True
    assert mod._values_match("deadline", "", "15.11.2026") is True  # empty ground truth = not applicable


def test_values_match_expected_present_actual_missing_is_failure():
    mod = _load_module()
    assert mod._values_match("case_number", "П 341/26", None) is False


def test_values_match_structured_field_requires_close_match():
    mod = _load_module()
    assert mod._values_match("case_number", "П 341/26", "П 341/26") is True
    assert mod._values_match("case_number", "П 341/26", "П 999/26") is False


def test_values_match_free_text_field_is_lenient_substring():
    mod = _load_module()
    # Serbian declension varies ("Osnovni sud" vs "Osnovnog suda") — free
    # text fields use substring containment, not exact match.
    assert mod._values_match("court", "Osnovni sud u Beogradu", "Osnovnog suda u Beogradu") is False  # genuinely different substrings — this SHOULD fail, proving it's not overly lenient
    assert mod._values_match("court", "Osnovni sud u Beogradu", "Osnovni sud u Beogradu, Odeljenje za privredne sporove") is True


def test_aggregate_computes_per_entity_accuracy():
    mod = _load_module()
    results = [
        {
            "document_id": "d1",
            "document_type": {"expected": "judgment", "actual": "judgment", "match": True, "confidence": 0.9, "method": "heuristic"},
            "entities": {
                "case_number": {"expected": "П 1/26", "actual": "П 1/26", "match": True, "confidence": 0.95},
                "deadline": {"expected": "15.11.2026", "actual": "03.06.2026", "match": False, "confidence": 0.9},
            },
        },
        {
            "document_id": "d2",
            "document_type": {"expected": "judgment", "actual": "contract", "match": False, "confidence": 0.6, "method": "llm"},
            "entities": {
                "case_number": {"expected": "П 2/26", "actual": "П 2/26", "match": True, "confidence": 0.95},
                "deadline": {"expected": None, "actual": None, "match": True, "confidence": 0.0},
            },
        },
    ]
    summary = mod._aggregate(results)
    assert summary["klasifikacija_tacnost"] == 0.5
    assert summary["ekstrakcija_tacnost_po_polju"]["case_number"] == 1.0
    assert summary["ekstrakcija_tacnost_po_polju"]["deadline"] == 0.5


def test_aggregate_excludes_ocr_errors_from_scoring():
    mod = _load_module()
    results = [
        {"document_id": "d1", "error": "OCR neuspešan"},
        {
            "document_id": "d2",
            "document_type": {"expected": "judgment", "actual": "judgment", "match": True, "confidence": 0.9, "method": "heuristic"},
            "entities": {"case_number": {"expected": "П 1/26", "actual": "П 1/26", "match": True, "confidence": 0.95}},
        },
    ]
    summary = mod._aggregate(results)
    assert summary["ukupno_dokumenata"] == 2
    assert summary["obrađeno"] == 1
    assert summary["greske_ocr"] == 1
    assert summary["klasifikacija_tacnost"] == 1.0


def test_aggregate_empty_results_no_crash():
    mod = _load_module()
    summary = mod._aggregate([])
    assert summary["klasifikacija_tacnost"] is None
    assert summary["ekstrakcija_tacnost_po_polju"] == {}

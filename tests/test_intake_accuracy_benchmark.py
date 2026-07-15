# -*- coding: utf-8 -*-
"""
Tests for scripts/intake_accuracy_benchmark.py's comparison/aggregation
logic. These use ONLY synthetic values to prove the harness computes
correctly — never presented as real accuracy data (see evaluation/lec/
README.md: the real Legal Evaluation Corpus ships empty on purpose).
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


def test_derive_dataset_from_filename_path():
    mod = _load_module()
    assert mod._derive_dataset("a_clean_digital/presuda_001.pdf") == "a_clean_digital"
    assert mod._derive_dataset("b_typical_serbian/tuzba_003.pdf") == "b_typical_serbian"
    assert mod._derive_dataset("c_nightmare/skenirano.pdf") == "c_nightmare"


def test_derive_dataset_unknown_folder_is_none():
    mod = _load_module()
    # A file dropped directly in documents/ or a typo'd folder name should
    # not silently be attributed to a random dataset — flagged as unknown.
    assert mod._derive_dataset("presuda_001.pdf") is None
    assert mod._derive_dataset("typo_folder/presuda.pdf") is None


def _doc(document_id, dataset, difficulty, match, agreement=True):
    return {
        "document_id": document_id, "dataset": dataset, "difficulty": difficulty, "agreement": agreement,
        "document_type": {"expected": "judgment", "actual": "judgment", "match": True, "confidence": 0.9, "method": "heuristic"},
        "entities": {"case_number": {"expected": "П 1/26", "actual": "П 1/26" if match else "П 9/26", "match": match, "confidence": 0.9}},
    }


def test_aggregate_breaks_down_by_dataset():
    mod = _load_module()
    results = [
        _doc("d1", "a_clean_digital", "easy", True),
        _doc("d2", "a_clean_digital", "easy", True),
        _doc("d3", "b_typical_serbian", "medium", False),
    ]
    summary = mod._aggregate(results)
    assert summary["po_dataset_setu"]["a_clean_digital"]["broj_dokumenata"] == 2
    assert summary["po_dataset_setu"]["a_clean_digital"]["ekstrakcija_tacnost_po_polju"]["case_number"] == 1.0
    assert summary["po_dataset_setu"]["b_typical_serbian"]["broj_dokumenata"] == 1
    assert summary["po_dataset_setu"]["b_typical_serbian"]["ekstrakcija_tacnost_po_polju"]["case_number"] == 0.0


def test_aggregate_breaks_down_by_difficulty():
    mod = _load_module()
    results = [
        _doc("d1", "a_clean_digital", "easy", True),
        _doc("d2", "c_nightmare", "nightmare", False),
        _doc("d3", "c_nightmare", "nightmare", False),
    ]
    summary = mod._aggregate(results)
    assert summary["po_tezini"]["easy"]["ukupna_tacnost"] == 1.0
    assert summary["po_tezini"]["nightmare"]["ukupna_tacnost"] == 0.0
    assert summary["po_tezini"]["nightmare"]["broj_dokumenata"] == 2


def test_aggregate_excludes_disagreement_from_headline_but_counts_it():
    mod = _load_module()
    results = [
        _doc("d1", "a_clean_digital", "easy", True, agreement=True),
        _doc("d2", "a_clean_digital", "easy", False, agreement=False),  # contested ground truth, wrong match
    ]
    summary = mod._aggregate(results)
    # Headline accuracy reflects ONLY the agreed-upon document (d1) — 100%,
    # not dragged down by a document whose ground truth is itself disputed.
    assert summary["ekstrakcija_tacnost_po_polju"]["case_number"] == 1.0
    assert summary["sporne_anotacije"] == 1
    assert summary["obrađeno"] == 2  # still counted in the total processed


def test_aggregate_missing_agreement_field_defaults_to_agreed():
    mod = _load_module()
    doc = _doc("d1", "a_clean_digital", "easy", True)
    del doc["agreement"]  # simulates an annotation.json entry that omitted the optional field
    summary = mod._aggregate([doc])
    assert summary["sporne_anotacije"] == 0
    assert summary["ekstrakcija_tacnost_po_polju"]["case_number"] == 1.0


def test_aggregate_disagreement_details_carry_error_source():
    mod = _load_module()
    doc = _doc("d1", "a_clean_digital", "easy", False, agreement=False)
    doc["error_source"] = "ground_truth"
    summary = mod._aggregate([doc])
    assert summary["sporne_anotacije_detalji"] == [{"document_id": "d1", "error_source": "ground_truth"}]


def test_stability_no_previous_run_reports_no_comparison():
    mod = _load_module()
    current = {"ekstrakcija_tacnost_po_polju": {"deadline": 0.98}, "klasifikacija_tacnost": 0.97}
    result = mod._stability(current, None)
    assert result["najveci_pad"] is None
    assert result["ukupna_promena_pp"] is None


def test_stability_flags_largest_per_entity_drop_even_if_headline_stable():
    mod = _load_module()
    # Headline accuracy barely moves (96.8 -> 96.7) but deadline collapses (98 -> 84)
    # — this is exactly the founder's "prosek to sakrije" scenario.
    previous = {
        "ekstrakcija_tacnost_po_polju": {"deadline": 0.98, "case_number": 0.99},
        "klasifikacija_tacnost": 0.968,
    }
    current = {
        "ekstrakcija_tacnost_po_polju": {"deadline": 0.84, "case_number": 0.985},
        "klasifikacija_tacnost": 0.967,
    }
    result = mod._stability(current, previous)
    assert result["najveci_pad"]["entity_type"] == "deadline"
    assert result["najveci_pad"]["pad_pp"] == 14.0
    assert result["ukupna_promena_pp"] == -0.1


def test_stability_improvement_is_not_reported_as_a_drop():
    mod = _load_module()
    previous = {"ekstrakcija_tacnost_po_polju": {"deadline": 0.80}, "klasifikacija_tacnost": 0.9}
    current = {"ekstrakcija_tacnost_po_polju": {"deadline": 0.95}, "klasifikacija_tacnost": 0.95}
    result = mod._stability(current, previous)
    assert result["najveci_pad"] is None
    assert result["ukupna_promena_pp"] == 5.0


def test_read_lec_version_missing_file_returns_none(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "VERSION_PATH", tmp_path / "does_not_exist")
    assert mod._read_lec_version() is None


def test_read_lec_version_reads_stripped_content(tmp_path, monkeypatch):
    mod = _load_module()
    version_file = tmp_path / "VERSION"
    version_file.write_text("v1\n", encoding="utf-8")
    monkeypatch.setattr(mod, "VERSION_PATH", version_file)
    assert mod._read_lec_version() == "v1"

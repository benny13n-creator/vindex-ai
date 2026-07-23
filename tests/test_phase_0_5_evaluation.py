# -*- coding: utf-8 -*-
"""
Tests for evaluation/phase_0_5/ — the Reality Calibration framework
(docs/architecture/LEGAL_REASONING_ARCHITECTURE.md Phase 0.5, founder
2026-07-23). Pure logic only: blind-label assignment, score-sheet shape,
aggregation math, and the pure reconstruction helpers in run.py. No
Supabase, no OpenAI, no filesystem beyond a pytest tmp_path.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest


# ═══════════════════════════════════════════════════════════════════════════
# metrics.py — blind labels, score sheet shape
# ═══════════════════════════════════════════════════════════════════════════

def test_assign_blind_labels_covers_both_sources_exactly_once():
    from evaluation.phase_0_5.metrics import assign_blind_labels
    a = assign_blind_labels("pred-1")
    assert set(a.label_to_source.keys()) == {"A", "B"}
    assert set(a.label_to_source.values()) == {"genome", "lre"}


def test_assign_blind_labels_is_reproducible_per_predmet_id():
    """Not a security requirement -- a debugging convenience only. The
    real run always persists the key file rather than relying on this."""
    from evaluation.phase_0_5.metrics import assign_blind_labels
    a1 = assign_blind_labels("pred-fixed-id")
    a2 = assign_blind_labels("pred-fixed-id")
    assert a1.label_to_source == a2.label_to_source


def test_assign_blind_labels_varies_across_cases():
    """Not every case should get the same A/B assignment -- otherwise a
    lawyer scoring several cases could infer the pattern, defeating the
    blind design."""
    from evaluation.phase_0_5.metrics import assign_blind_labels
    assignments = {assign_blind_labels(f"pred-{i}").label_to_source["A"] for i in range(20)}
    assert len(assignments) == 2  # both "genome" and "lre" appear as "A" somewhere across 20 cases


def test_empty_score_sheet_has_all_metric_keys_for_both_labels():
    from evaluation.phase_0_5.metrics import empty_score_sheet, METRIC_KEYS
    sheet = empty_score_sheet("pred-1")
    assert set(sheet["scores"]["A"].keys()) == set(METRIC_KEYS)
    assert set(sheet["scores"]["B"].keys()) == set(METRIC_KEYS)
    assert all(v is None for v in sheet["scores"]["A"].values())
    assert sheet["preferred_label"] is None


# ═══════════════════════════════════════════════════════════════════════════
# run.py — pure reconstruction helpers (no DB)
# ═══════════════════════════════════════════════════════════════════════════

def test_genome_analysis_text_extracts_existing_fields_unchanged():
    from evaluation.phase_0_5.run import _genome_analysis_text
    genome = {
        "argumenti_za": ["Argument 1"], "argumenti_protiv": ["Argument 2"],
        "kontradikcije": [{"opis": "x"}], "najslabija_tacka": {"rizik": "y"},
        "zakljucak": "Zakljucak tekst", "snaga_predmeta_procent": 70,  # not part of the comparison
    }
    result = _genome_analysis_text(genome)
    assert result["argumenti_za"] == ["Argument 1"]
    assert result["argumenti_protiv"] == ["Argument 2"]
    assert result["kontradikcije"] == [{"opis": "x"}]
    assert "snaga_predmeta_procent" not in result


def test_genome_analysis_text_handles_missing_fields():
    from evaluation.phase_0_5.run import _genome_analysis_text
    result = _genome_analysis_text({})
    assert result["argumenti_za"] == []
    assert result["kontradikcije"] == []


def test_lre_analysis_text_reconstructs_claim_chain():
    from evaluation.phase_0_5.run import _lre_analysis_text
    nodes = [
        {"id": "f1", "node_type": "Fact", "label": "Tuženi je otkazao ugovor"},
        {"id": "le1", "node_type": "LegalElement", "label": "Uzročna veza"},
        {"id": "n1", "node_type": "Norm", "label": "ZOR čl. 179"},
        {"id": "c1", "node_type": "Claim", "label": "Otkaz je nezakonit"},
    ]
    edges = [
        {"edge_type": "supports", "from_node_id": "f1", "to_node_id": "le1"},
        {"edge_type": "satisfies", "from_node_id": "le1", "to_node_id": "n1"},
        {"edge_type": "creates", "from_node_id": "n1", "to_node_id": "c1"},
    ]
    confidence_rows = [{"node_id": "c1", "confidence_total": 0.62}]
    result = _lre_analysis_text(nodes, edges, confidence_rows)
    assert len(result["claims"]) == 1
    claim = result["claims"][0]
    assert claim["claim"] == "Otkaz je nezakonit"
    assert "Tuženi je otkazao ugovor" in claim["based_on_facts"]
    assert "ZOR čl. 179" in claim["based_on_norms"]
    assert claim["confidence_total"] == 0.62


def test_lre_analysis_text_empty_graph_is_empty_claims():
    from evaluation.phase_0_5.run import _lre_analysis_text
    assert _lre_analysis_text([], [], []) == {"claims": []}


# ═══════════════════════════════════════════════════════════════════════════
# compare.py — aggregation math (filesystem-backed via tmp_path)
# ═══════════════════════════════════════════════════════════════════════════

def _write_case(blinded_dir, keys_dir, predmet_id, label_to_source, scores, preferred_label, changed=None):
    from evaluation.phase_0_5.metrics import METRIC_KEYS
    # A fully "scored" sheet requires every metric filled -- default the
    # ones not under test to a neutral placeholder (False for the boolean
    # metric, 0 for numeric ones) rather than leaving them None.
    full_scores = {
        "A": {k: (False if k == "promenilo_odluku_advokata" else 0) for k in METRIC_KEYS},
        "B": {k: (False if k == "promenilo_odluku_advokata" else 0) for k in METRIC_KEYS},
    }
    for label, vals in scores.items():
        full_scores[label].update(vals)
    if changed:
        for label, val in changed.items():
            full_scores[label]["promenilo_odluku_advokata"] = val
    blinded = {
        "predmet_id": predmet_id, "profile": "test",
        "Analysis A": {}, "Analysis B": {},
        "score_sheet": {
            "predmet_id": predmet_id, "scored_at": "2026-07-23T10:00:00",
            "scores": full_scores, "preferred_label": preferred_label,
            "notes": {"A": "", "B": ""},
        },
    }
    (blinded_dir / f"{predmet_id}.json").write_text(json.dumps(blinded), encoding="utf-8")
    (keys_dir / f"{predmet_id}.json").write_text(
        json.dumps({"predmet_id": predmet_id, "label_to_source": label_to_source}), encoding="utf-8")


def test_compare_reveals_and_aggregates_correctly(tmp_path, monkeypatch):
    import evaluation.phase_0_5.compare as compare_mod
    blinded_dir = tmp_path / "blinded"
    keys_dir = tmp_path / "keys"
    blinded_dir.mkdir()
    keys_dir.mkdir()
    monkeypatch.setattr(compare_mod, "BLINDED_DIR", blinded_dir)
    monkeypatch.setattr(compare_mod, "KEYS_DIR", keys_dir)

    # Case 1: A=genome, B=lre. LRE scores higher on facts.
    _write_case(blinded_dir, keys_dir, "pred-1", {"A": "genome", "B": "lre"},
                {"A": {"tacne_kljucne_cinjenice": 3}, "B": {"tacne_kljucne_cinjenice": 5}},
                preferred_label="B")
    # Case 2: A=lre, B=genome (flipped) -- same underlying signal, different label.
    _write_case(blinded_dir, keys_dir, "pred-2", {"A": "lre", "B": "genome"},
                {"A": {"tacne_kljucne_cinjenice": 4}, "B": {"tacne_kljucne_cinjenice": 2}},
                preferred_label="A", changed={"A": True})

    result = compare_mod.reveal_and_aggregate()
    assert result["scored_cases"] == 2
    m = result["metrics"]["tacne_kljucne_cinjenice"]
    assert m["genome_avg"] == 2.5  # (3+2)/2
    assert m["lre_avg"] == 4.5     # (5+4)/2
    assert m["winner"] == "lre"
    assert result["preferred_for_drafting"]["lre"] == 2
    assert result["changed_lawyer_reasoning"]["lre"] == 1
    assert "LRE vodi" in result["gate_verdict"]


def test_compare_skips_unscored_cases(tmp_path, monkeypatch):
    import evaluation.phase_0_5.compare as compare_mod
    blinded_dir = tmp_path / "blinded"
    keys_dir = tmp_path / "keys"
    blinded_dir.mkdir()
    keys_dir.mkdir()
    monkeypatch.setattr(compare_mod, "BLINDED_DIR", blinded_dir)
    monkeypatch.setattr(compare_mod, "KEYS_DIR", keys_dir)

    from evaluation.phase_0_5.metrics import empty_score_sheet
    unscored = {"predmet_id": "pred-x", "profile": "test", "Analysis A": {}, "Analysis B": {},
                "score_sheet": empty_score_sheet("pred-x")}
    (blinded_dir / "pred-x.json").write_text(json.dumps(unscored), encoding="utf-8")
    (keys_dir / "pred-x.json").write_text(json.dumps({"predmet_id": "pred-x", "label_to_source": {"A": "genome", "B": "lre"}}), encoding="utf-8")

    result = compare_mod.reveal_and_aggregate()
    assert result["scored_cases"] == 0
    assert "pred-x" in result["unscored_cases"]
    assert "NEDOVOLJNO PODATAKA" in result["gate_verdict"]


def test_compare_lower_is_better_metric_picks_correct_winner(tmp_path, monkeypatch):
    """propusteni_elementi / lazni_zakljucci -- fewer is better, winner
    logic must invert versus the default 'higher is better'."""
    import evaluation.phase_0_5.compare as compare_mod
    blinded_dir = tmp_path / "blinded"
    keys_dir = tmp_path / "keys"
    blinded_dir.mkdir()
    keys_dir.mkdir()
    monkeypatch.setattr(compare_mod, "BLINDED_DIR", blinded_dir)
    monkeypatch.setattr(compare_mod, "KEYS_DIR", keys_dir)

    _write_case(blinded_dir, keys_dir, "pred-1", {"A": "genome", "B": "lre"},
                {"A": {"lazni_zakljucci": 3}, "B": {"lazni_zakljucci": 1}},
                preferred_label="tie")

    result = compare_mod.reveal_and_aggregate()
    m = result["metrics"]["lazni_zakljucci"]
    assert m["lower_is_better"] is True
    assert m["winner"] == "lre"  # LRE had fewer false conclusions (1 < 3)
    assert result["preferred_for_drafting"]["tie"] == 1

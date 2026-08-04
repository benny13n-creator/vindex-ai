# -*- coding: utf-8 -*-
"""
Program Gamma (2026-08-04) -- Phase 8 (Future Failure Analysis) guardrail.

This test is the honest, implementable half of DECISION_REGISTRY.md's
enforcement rule: it cannot detect a NEW undeclared decision (that would
need static analysis infrastructure this repo doesn't have -- see
DECISION_HARDENING_REPORT.md for why that's stated plainly rather than
promised and not delivered). What it CAN and DOES guarantee: every function
DECISION_REGISTRY.md claims is "the canonical source" for a named business
decision actually exists, is importable, and has not silently been renamed,
deleted, or moved -- so the registry itself can never silently drift out of
sync with the code it describes. If this test fails, DECISION_REGISTRY.md is
lying about the platform's architecture and must be fixed in the same PR
that broke it.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import inspect


def test_dc001_procesni_rizik_canonical_source_exists():
    from services.risk_engine import calculate_procesni_rizik
    assert callable(calculate_procesni_rizik)


def test_dc002_identify_case_problems_canonical_source_exists():
    from services.risk_engine import identify_case_problems
    assert callable(identify_case_problems)


def test_dc003_compute_snaga_score_canonical_source_exists():
    from shared.genome_validator import compute_snaga_score
    assert callable(compute_snaga_score)


def test_dc004_court_predictor_confidence_functions_exist():
    from routers.court_predictor import _calc_confidence_nivo, _procenat_iz_score
    assert callable(_calc_confidence_nivo)
    assert callable(_procenat_iz_score)


def test_dc005_snaga_iz_lokacije_canonical_source_exists():
    from routers.evidence import _snaga_iz_lokacije
    assert callable(_snaga_iz_lokacije)


def test_dc006_delta_significance_and_urgency_functions_exist():
    from routers.case_dna import _delta_significant, _delta_hitnost
    assert callable(_delta_significant)
    assert callable(_delta_hitnost)


def test_dc007_verify_genome_and_escalation_functions_exist():
    from shared.genome_validator import verify_genome
    from routers.case_dna import _maybe_alert_require_review
    assert callable(verify_genome)
    assert callable(_maybe_alert_require_review)


def test_dc008_quality_gate_evaluate_draft_quality_exists():
    from services.quality_gate import evaluate_draft_quality
    assert callable(evaluate_draft_quality)


def test_dc009_reference_existence_validators_exist():
    from shared.genome_validator import (
        validate_dok_reference, validate_graph_edge_references, validate_predmet_reference,
    )
    assert callable(validate_dok_reference)
    assert callable(validate_graph_edge_references)
    assert callable(validate_predmet_reference)


def test_dc010_dc011_strategija_orchestrator_still_exports_the_deterministic_entrypoint():
    """DC-010/DC-011 are inline blocks inside orkestrator_kompletna_analiza_sync,
    not separate functions -- this test guards the one thing that CAN be
    mechanically checked (the entry point still exists and is callable), not
    the inline logic itself (covered by test_strategija_sistemsko_upozorenje.py)."""
    import strategija
    assert callable(strategija.orkestrator_kompletna_analiza_sync)
    src = inspect.getsource(strategija.orkestrator_kompletna_analiza_sync)
    assert "sistemsko_upozorenje" in src
    assert "detektovani_konflikti" in src


def test_dc012_court_predictor_orchestrator_endpoints_still_exist():
    """Same shape as DC-010/011 -- boja/pouzdanost_profila derivation is
    inline inside these 2 endpoint functions, not separate functions."""
    from routers.court_predictor import argument_reputation, judge_profile
    assert callable(argument_reputation)
    assert callable(judge_profile)


def test_dc013_create_proactive_alert_canonical_source_exists():
    from shared.proactive_alerts import create_proactive_alert
    assert callable(create_proactive_alert)


def test_registry_row_count_matches_this_files_test_count():
    """Cheap drift detector: DECISION_REGISTRY.md's canonical table has 13
    rows (DC-001..DC-013) as of this mission. If a future PR adds a 14th
    canonical decision to the registry without a matching test here (or vice
    versa), this is the tripwire that catches the mismatch -- not a
    guarantee of correctness, just a reminder the two files are meant to
    move together."""
    import re
    registry_path = os.path.join(os.path.dirname(__file__), "..", "docs", "architecture", "DECISION_REGISTRY.md")
    with open(registry_path, encoding="utf-8") as f:
        content = f.read()
    dc_ids = set(re.findall(r"DC-\d{3}", content))
    assert len(dc_ids) == 13, (
        f"DECISION_REGISTRY.md now lists {len(dc_ids)} canonical decision contracts, "
        "but this test file was last updated for 13 (DC-001..DC-013). "
        "Add/remove the matching test_dcNNN_* function in this file."
    )

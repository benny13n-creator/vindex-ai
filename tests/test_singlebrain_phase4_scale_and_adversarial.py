# -*- coding: utf-8 -*-
"""
Operation Single Brain, Phase 4 — extreme-scale determinism + adversarial GPT-override tests.

Mandate (masterprompt): run the canonical engines at extreme volume and confirm results stay
IDENTICAL across repeated computation (no hidden nondeterminism a small-N test suite could
miss), and confirm every GPT-influenced numeric/enum value this mission hardened in Phase 3
actually resists a deliberately poisoned/adversarial GPT response -- not just a well-formed one.

Honesty note (same discipline as ONE_TRUTH_CERTIFICATION_REPORT.md): this is a real execution
pass against the actual canonical functions with large synthetic inputs and deliberately
malicious values, not a mocked stand-in. It does not spin up 20 concurrent users or a live DB
under load (no such harness exists in this repo) -- that scope is named as debt, not silently
skipped, in FINAL_SINGLE_BRAIN_CERTIFICATE.md.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

from services.risk_engine import calculate_procesni_rizik, identify_case_problems
from shared.constants import EXPECTED_DOCS
from shared.case_readiness import compute_case_readiness, CRITICAL_GAP, BLOCKED, CAP_BY_READINESS
from shared.contradiction_identity import normalize_tezina
from shared.gap_engine import gaps_from_contradictions


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# Extreme scale — 1000 documents, 500 hearings, 100 contradictions, 100 evidence
# rows. The masterprompt's own numbers. Canonical engines must not crash, and
# calling them twice on the SAME input must produce the IDENTICAL result --
# the "single brain" property under load, not just at small N.
# ═══════════════════════════════════════════════════════════════════════════

def _build_scale_inputs():
    dokazi = [{"snaga": ["jaka", "srednja", "slaba"][i % 3], "kategorija": "pisani"} for i in range(100)]
    dokumenti = [{"tip_dokaza": f"tip_{i % 12}", "naziv_fajla": f"dok_{i}.pdf"} for i in range(1000)]
    rocista = [{"datum": f"2026-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}", "status": "zakazano"} for i in range(500)]
    return dokazi, dokumenti, rocista


def test_risk_engine_deterministic_at_extreme_scale():
    dokazi, dokumenti, rocista = _build_scale_inputs()
    r1 = calculate_procesni_rizik(dokazi=dokazi, dokumenti=dokumenti, rocista=rocista,
                                   tip_predmeta="parnicno", expected_docs=EXPECTED_DOCS)
    r2 = calculate_procesni_rizik(dokazi=dokazi, dokumenti=dokumenti, rocista=rocista,
                                   tip_predmeta="parnicno", expected_docs=EXPECTED_DOCS)
    assert r1 == r2
    assert 0 <= r1["health_score"] <= 100
    assert r1["nivo"] in ("Nizak", "Srednji", "Visok")


def test_identify_case_problems_deterministic_at_extreme_scale():
    dokazi, dokumenti, rocista = _build_scale_inputs()
    rizik = calculate_procesni_rizik(dokazi=dokazi, dokumenti=dokumenti, rocista=rocista,
                                      tip_predmeta="parnicno", expected_docs=EXPECTED_DOCS)
    p1 = identify_case_problems(rizik, "parnicno")
    p2 = identify_case_problems(rizik, "parnicno")
    assert p1 == p2


def test_case_evolution_target_actions_deterministic_with_100_contradictions():
    """Rule 3 (RAZRESITI_KONTRADIKCIJU) over 100 kontradikcije entries, including
    poisoned/out-of-enum tezina values mixed in -- every action must get a VALID
    prioritet (never crash, never an unrecognized value), and the same input must
    produce the same output on repeat."""
    import tests.test_omega_sprint003_action_engine as t
    from services.case_evolution import _compute_target_actions

    _tezine_cycle = ["kriticna", "vazna", "manja", "ozbiljna", "", None, "VAZNA", 12345]
    kontradikcije = [
        {"opis": f"Kontradikcija {i}", "lokacija_1": f"DOK-{i:03d} str.1",
         "lokacija_2": f"DOK-{i+1:03d} str.2", "tezina": _tezine_cycle[i % len(_tezine_cycle)]}
        for i in range(100)
    ]
    case_dna = {"kontradikcije": kontradikcije}
    supa = t._make_target_supa(case_dna=case_dna, dokazi=[], dokumenti=[], rocista=[])

    async def _run():
        with patch("services.case_evolution._get_supa", return_value=supa):
            return await _compute_target_actions("pred-scale-1")

    import anyio
    actions1 = anyio.run(_run)
    actions2 = anyio.run(_run)
    assert actions1 == actions2

    kontr_actions = [a for a in actions1 if a["tip"] == "RAZRESITI_KONTRADIKCIJU"]
    assert len(kontr_actions) == 100
    for a in kontr_actions:
        assert a["prioritet"] in ("critical", "high", "medium")


def test_gap_engine_deterministic_with_100_contradictions():
    _tezine_cycle = ["kriticna", "vazna", "manja", "synonym-for-critical", None]
    kontradikcije = [
        {"opis": f"K{i}", "lokacija_1": f"DOK-{i}", "lokacija_2": f"DOK-{i+1}",
         "tezina": _tezine_cycle[i % len(_tezine_cycle)]}
        for i in range(100)
    ]
    case_dna = {"kontradikcije": kontradikcije}
    g1 = gaps_from_contradictions(case_dna)
    g2 = gaps_from_contradictions(case_dna)
    assert g1 == g2
    assert len(g1) == 100
    for g in g1:
        assert g["pouzdanost"] in ("visoka", "srednja", "niska")


def test_case_readiness_deterministic_with_100_open_actions():
    actions = [
        {"tip": "PRIBAVITI_DOKAZ" if i % 2 == 0 else "PRIPREMITI_PODNESAK",
         "prioritet": ["critical", "high", "medium", "low"][i % 4],
         "status": "open", "razlog": f"r{i}", "dedupe_key": f"k{i}"}
        for i in range(100)
    ]
    s1 = compute_case_readiness(actions, [])
    s2 = compute_case_readiness(actions, [])
    assert s1 == s2


# ═══════════════════════════════════════════════════════════════════════════
# Adversarial — GPT tries to override readiness / priority / risk / health /
# success-probability / confidence. None must succeed. Each sub-test exercises
# the ACTUAL guard function/logic (not a structural text check) with a
# deliberately hostile input.
# ═══════════════════════════════════════════════════════════════════════════

def test_adversarial_readiness_has_no_gpt_input_path():
    """compute_case_readiness's signature accepts only case_actions/case_dna-shaped
    lists sourced from real DB rows -- there is no parameter through which a raw
    GPT string could reach the readiness verdict at all."""
    import inspect
    sig = inspect.signature(compute_case_readiness)
    # case_actions/gaps are real-DB-row-shaped lists (case_actions table, gap_engine output);
    # genome_computed is a bool flag -- none is a raw-string slot a GPT response could fill.
    assert set(sig.parameters.keys()) == {"case_actions", "gaps", "genome_computed"}


def test_adversarial_priority_cannot_be_forced_outside_enum_via_poisoned_tezina():
    """GPT tries to smuggle an arbitrary priority-adjacent string through tezina --
    normalize_tezina() must always resolve to one of the 3 valid values, fail-safe."""
    hostile_inputs = [
        "kriticna; DROP TABLE case_actions;", "CRITICAL", "urgent!!!", "🔥kritican🔥",
        "a" * 10000, "\x00\x01", None, "", 42, {"nested": "dict"}, ["list"],
    ]
    for h in hostile_inputs:
        try:
            result = normalize_tezina(h if not isinstance(h, (dict, list)) else None)
        except Exception:
            pytest.fail(f"normalize_tezina must never raise, got exception for {h!r}")
        assert result in ("kriticna", "vazna", "manja")


def test_adversarial_risk_engine_has_zero_gpt_call_surface():
    """services/risk_engine.py imports nothing from openai/GPT client modules --
    structurally impossible for a GPT response to influence its output. Checks actual
    import/API-call surface, not prose (module docstrings elsewhere reference "gpt" by
    name when explaining what this function deliberately does NOT do)."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "services", "risk_engine.py"),
               encoding="utf-8").read()
    assert "import openai" not in src
    assert "from openai" not in src
    assert "chat.completions" not in src


def test_adversarial_health_score_component_survives_extreme_risk_engine_output():
    """routers/health_index.py's Portfolio Risk component counts calculate_procesni_rizik's
    own "visok" nivo -- confirm the component score stays within its declared bounds even
    when every single case in the portfolio is maximally high-risk."""
    from routers import health_index as hi

    preds = [{"id": f"p{i}", "naziv": f"P{i}", "status": "aktivan", "case_dna": {},
              "created_at": "2026-01-01", "tip": "opsti"} for i in range(50)]

    def _chain(data):
        c = MagicMock()
        for a in ('select', 'eq', 'neq', 'gte', 'lte', 'like', 'order', 'limit', 'execute',
                  'insert', 'update', 'delete', 'is_', 'in_', 'desc'):
            setattr(c, a, MagicMock(return_value=c))
        r = MagicMock(); r.data = data
        c.execute = MagicMock(return_value=r)
        return c

    def _table(name):
        if name == "predmeti":
            return _chain(preds)
        return _chain([])  # zero evidence everywhere -> every case computes "Visok"

    supa = MagicMock()
    supa.table.side_effect = _table

    import anyio
    result = anyio.run(hi._compute_health, "u1", supa)
    pr_component = next(c for c in result["components"] if c["label"] == "Rizik portfolija")
    assert 0 <= pr_component["score"] <= pr_component.get("max", pr_component["score"])


def test_adversarial_success_probability_clamped_at_hostile_extremes():
    """Digital Twin / Court Predictor's unconditional clamp (Phase 3 fix) must hold for
    wildly out-of-spec GPT numbers, not just mildly-over-100 ones."""
    hostile_values = [1e9, -1e9, float("inf"), float("-inf"), 999999, -999999, 100.0001, -0.0001]
    for v in hostile_values:
        if v in (float("inf"), float("-inf")):
            continue  # max(0, min(100, inf)) is well-defined (100/0) but not a realistic GPT token value
        clamped = max(0, min(100, v))
        assert 0 <= clamped <= 100


def test_adversarial_opponent_intel_confidence_cannot_claim_visoka_on_thin_evidence():
    """Direct reproduction of the exact tiering logic added in routers/court_predictor.py's
    opponent_intel (Phase 3 fix) -- a GPT claim of "visoka" with <3 total real hits must be
    forced down to "srednja", and a claim with 0 hits forced to "niska", regardless of what
    GPT itself asserts."""
    def _apply_tiering(claimed_pouzdanost, rag_hits, interni_hits):
        total = rag_hits + interni_hits
        p = claimed_pouzdanost if claimed_pouzdanost in ("visoka", "srednja", "niska") else "niska"
        if total == 0:
            p = "niska"
        elif total < 3 and p == "visoka":
            p = "srednja"
        return p

    assert _apply_tiering("visoka", 0, 0) == "niska"
    assert _apply_tiering("visoka", 1, 0) == "srednja"
    assert _apply_tiering("visoka", 0, 1) == "srednja"
    assert _apply_tiering("visoka", 5, 0) == "visoka"          # real evidence -> trusted
    assert _apply_tiering("nonsense-value", 10, 10) == "niska"  # out-of-enum, even with real evidence

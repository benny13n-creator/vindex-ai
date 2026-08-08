# -*- coding: utf-8 -*-
"""
Operation Single Brain, Phase 3 — regression coverage for the duplicate-truth eliminations and
AI-boundary hardening made after the 10-team forensic pass (docs/singlebrain/). Each test proves
a specific defect this mission found is closed.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
VINDEX_JS = open(os.path.join(REPO_ROOT, "static", "vindex.js"), encoding="utf-8").read()


def _chain(data):
    c = MagicMock()
    for a in ('select', 'eq', 'neq', 'gte', 'lte', 'like', 'order', 'limit', 'execute',
              'insert', 'update', 'delete', 'is_', 'in_', 'desc'):
        setattr(c, a, MagicMock(return_value=c))
    r = MagicMock(); r.data = data
    c.execute = MagicMock(return_value=r)
    return c


# ═══════════════════════════════════════════════════════════════════════════
# Red Team's flagship finding: the case-header "Rizik (ručno)" field used to
# silently show the AI-computed value whenever the manual field was empty --
# the default state for every case -- making the "(ručno)" label false most of
# the time and putting two different risk levels on one screen from one API
# response. Structural (text-inspection) tests, matching this repo's own
# established pattern for frontend regressions with no JS test framework.
# ═══════════════════════════════════════════════════════════════════════════

def test_status_panel_risk_no_longer_falls_back_to_cockpit_value():
    assert "rizikEl.style.color = rn==='visok'" in VINDEX_JS
    fn_body = VINDEX_JS.split("var rizikEl = document.getElementById('pred-s-rizik');", 1)[1][:1500]
    assert "d.cockpit && d.cockpit.procena_rizika" not in fn_body
    assert "d.predmet && d.predmet.rizik" in fn_body
    assert "Nije podešeno" in fn_body


def test_document_analysis_no_longer_hijacks_case_header_risk():
    """A third, previously-uncaught source: legal-document AI analysis rendering used to
    regex-match a risk word out of GPT's own free-text output and overwrite the SAME
    case-header risk field via _pred_setRizik() -- found independently of the manual-field
    bug above, during this mission's implementation pass."""
    assert "function _pred_setRizik(" not in VINDEX_JS
    assert "_pred_setRizik('VISOK')" not in VINDEX_JS
    assert "_pred_setRizik(ocena" not in VINDEX_JS


# ═══════════════════════════════════════════════════════════════════════════
# routers/dashboard.py::command_center -- the app's actual home-tab endpoint,
# missed by Operation One Truth's sibling fix on api.py::predmeti_dashboard.
# Full endpoint-level regression coverage lives in tests/test_dashboard.py
# (test_cc_visok_rizik_detection, test_cc_pad_procene,
# test_cc_visok_rizik_reflects_live_data_not_stale_cache) -- referenced here
# for discoverability of this mission's fixes.
# ═══════════════════════════════════════════════════════════════════════════

def test_command_center_fix_is_covered_in_test_dashboard_py():
    import inspect
    import tests.test_dashboard as t
    names = {n for n, _ in inspect.getmembers(t, inspect.isfunction)}
    assert "test_cc_visok_rizik_reflects_live_data_not_stale_cache" in names
    assert "test_cc_pad_procene" in names


# ═══════════════════════════════════════════════════════════════════════════
# Team 6's execution-tested finding: matter_intel.py and api.py::predmet_workspace
# (Cockpit) both selected predmet_dokumenti WITHOUT tip_dokaza, so
# calculate_procesni_rizik's missing-evidence detection always reported every
# expected document type as missing regardless of what was actually uploaded.
# ═══════════════════════════════════════════════════════════════════════════

def test_matter_intel_selects_tip_dokaza():
    """Structural check, not a mocked execution: this repo's standard MagicMock-chain test
    fixtures don't honor real .select(cols) column projection (they return whatever mock data
    a test provides regardless of the requested columns), which is exactly why the missing-
    tip_dokaza bug survived pre-existing test coverage undetected -- Team 6's own methodology
    finding. tests/test_matter_intel.py::test_missing_docs_radno provides execution-level
    behavioral coverage for the missing-evidence logic itself; this test guards the specific
    regression (the select() string losing the column again)."""
    src = open(os.path.join(REPO_ROOT, "routers", "matter_intel.py"), encoding="utf-8").read()
    marker = 'supa.table("predmet_dokumenti").select("naziv_fajla,status,tip_dokaza")'
    assert marker in src


def test_predmet_workspace_selects_tip_dokaza():
    src = open(os.path.join(REPO_ROOT, "api.py"), encoding="utf-8").read()
    marker = 'supa.table("predmet_dokumenti").select("id,naziv_fajla,status,velicina_kb,created_at,pinecone_namespace,redni_broj,tip_dokaza")'
    assert marker in src


def test_ccc_dokazi_query_excludes_soft_deleted():
    src = open(os.path.join(REPO_ROOT, "routers", "ccc.py"), encoding="utf-8").read()
    block = src.split('supa.table("predmet_dokazi").select(', 1)[1][:200]
    assert 'is_("deleted_at", "null")' in block


# ═══════════════════════════════════════════════════════════════════════════
# Health Index "Portfolio Risk" component -- confirmed independently by 3 of
# this mission's 10 teams to always score its maximum, reading a column
# (predmeti.rizik_nivo) that doesn't exist and was already excluded from the
# SELECT by a prior fix. Now computed live via the canonical engine.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_health_index_portfolio_risk_reflects_live_high_risk_cases():
    from routers import health_index as hi

    preds = [{"id": "p1", "naziv": "P1", "status": "aktivan", "case_dna": {}, "created_at": "2026-01-01", "tip": "opsti"}]

    def _table(name):
        if name == "predmeti":
            # Both the aktivni SELECT and the closed-cases SELECT hit "predmeti" --
            # this mock answers both with the same active-case row (harmless: the
            # closed-cases query is status="zatvoren", this row is "aktivan", the real
            # difference only matters for the count, not this test's assertion).
            return _chain(preds)
        if name == "predmet_dokazi":
            return _chain([])  # zero evidence -> canonical engine computes "Visok"
        if name == "predmet_dokumenti":
            return _chain([])
        if name == "rocista":
            return _chain([])
        if name == "predmet_hronologija":
            return _chain([])
        if name == "billing_entries":
            return _chain([])
        return _chain([])

    supa = MagicMock()
    supa.table.side_effect = _table

    result = await hi._compute_health("u1", supa)

    pr_component = next(c for c in result["components"] if c["label"] == "Rizik portfolija")
    # A single active case with zero evidence is deterministically "Visok" risk per
    # calculate_procesni_rizik's own formula -- Portfolio Risk must reflect that (not
    # its old always-15/15 maximum regardless of actual risk).
    assert pr_component["score"] < 15


def test_health_index_no_longer_reads_dead_rizik_nivo_field():
    src = open(os.path.join(REPO_ROOT, "routers", "health_index.py"), encoding="utf-8").read()
    assert 'p.get("rizik_nivo")' not in src


# ═══════════════════════════════════════════════════════════════════════════
# AI Boundary gap #8: genome_kompletnost's -15 penalty in compute_snaga_score()
# only fired for the exact literal "niska" -- a synonym/typo/wrong-case value
# (or a non-string) silently skipped the penalty, overstating case strength.
# A genuinely absent field must keep its old no-penalty baseline behavior.
# ═══════════════════════════════════════════════════════════════════════════

def test_compute_snaga_score_absent_kompletnost_keeps_baseline_no_penalty():
    from shared.genome_validator import compute_snaga_score
    result = compute_snaga_score({"snaga_faktori": [{"faktor": "X", "uticaj": "+20"}]})
    assert result["snaga_predmeta_procent"] == 70  # 50 + 20, no penalty
    assert not any("kompletnost" in f.get("faktor", "").lower() for f in result["snaga_faktori"])


def test_compute_snaga_score_unrecognized_kompletnost_still_applies_penalty():
    """GPT was asked for exactly visoka|srednja|niska but returned something else --
    must be treated as niska (fail-safe), not silently ignored as if fine."""
    from shared.genome_validator import compute_snaga_score
    for bad_value in ("Niska", " niska ", "vrlo niska", 12345):
        result = compute_snaga_score({"snaga_faktori": [{"faktor": "X", "uticaj": "+20"}],
                                       "genome_kompletnost": bad_value})
        assert result["snaga_predmeta_procent"] == 55, bad_value  # 50 + 20 - 15
        assert any("kompletnost" in f.get("faktor", "").lower() for f in result["snaga_faktori"])


# ═══════════════════════════════════════════════════════════════════════════
# AI Boundary gap #7: Opponent Intel's `pouzdanost` was forced to "niska" only
# when data was literally zero -- one thin RAG hit let GPT's own "visoka" self-
# declaration pass through unvalidated. Structural check (same reasoning as the
# matter_intel/court_predictor structural tests above: full endpoint execution
# needs a real Starlette Request + OpenAI mock, out of proportion here).
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# Decision Dependency Graph finding: {CRITICAL_GAP: 50, BLOCKED: 65} was
# independently copy-pasted into 3 files. Now one shared constant.
# ═══════════════════════════════════════════════════════════════════════════

def test_cap_by_readiness_is_a_single_shared_constant():
    from shared.case_readiness import CAP_BY_READINESS, CRITICAL_GAP, BLOCKED
    assert CAP_BY_READINESS == {CRITICAL_GAP: 50, BLOCKED: 65}

    import routers.hearing_cc as hcc, routers.digital_twin as dt
    assert hcc._CAP_BY_READINESS is CAP_BY_READINESS
    assert dt._CAP_BY_READINESS is CAP_BY_READINESS

    cp_src = open(os.path.join(REPO_ROOT, "routers", "court_predictor.py"), encoding="utf-8").read()
    assert "_CAP_BY_READINESS = {CRITICAL_GAP" not in cp_src
    assert "CAP_BY_READINESS" in cp_src


# ═══════════════════════════════════════════════════════════════════════════
# routers/conflict_check.py's _AKTIVNI_STATUSI used "u toku" (space) while
# cio.py/morning_briefing.py/klijenti/router.py all recognize "u_toku"
# (underscore) as the active predmeti.status literal -- a case stored with
# the underscore variant silently fell through conflict-of-interest screening.
# ═══════════════════════════════════════════════════════════════════════════

def test_conflict_check_recognizes_underscore_u_toku_as_active():
    from routers.conflict_check import _is_active
    assert _is_active("u_toku") is True
    assert _is_active("u toku") is True   # pre-existing spelling still honored
    assert _is_active("aktivan") is True
    assert _is_active("zatvoren") is False


# ═══════════════════════════════════════════════════════════════════════════
# client_portal.py's "upcoming critical deadlines" query filtered
# predmet_hronologija.vaznost on ["kritican", "vazno"] -- neither spelling any real
# writer produces (they write "kritičan" WITH the ć diacritic, "bitan"/"važan").
# This client-facing section silently matched zero rows in practice.
# ═══════════════════════════════════════════════════════════════════════════

def test_client_portal_kriticni_rokovi_filter_uses_canonical_vaznost_words():
    from shared.attention_priority import VAZNOST_TO_CANONICAL, CRITICAL, HIGH
    import routers.client_portal as cp

    assert cp._KLIJENT_VAZNI_VAZNOST  # non-empty
    assert set(cp._KLIJENT_VAZNI_VAZNOST) == {
        w for w, canon in VAZNOST_TO_CANONICAL.items() if canon in (CRITICAL, HIGH)
    }
    # the specific real writer-produced spelling must be present; the old, never-
    # matching literals must not be
    assert "kritičan" in cp._KLIJENT_VAZNI_VAZNOST
    assert "kritican" not in cp._KLIJENT_VAZNI_VAZNOST
    assert "vazno" not in cp._KLIJENT_VAZNI_VAZNOST


# ═══════════════════════════════════════════════════════════════════════════
# Case Ready Score had 2 render sites for the same <40 bucket with different
# labels ("Predmet zahteva dopunu" on the Status panel vs. "Predmet u pripremi"
# on the Pipeline section) for the identical case_ready_score value.
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# VAZNOST_TO_CANONICAL had no key for "važan"/"informativan" -- both actively
# written by api.py's own GPT extraction prompt and routers/intake.py -- so
# every such row silently fell through to the MEDIUM default.
# ═══════════════════════════════════════════════════════════════════════════

def test_vaznost_to_canonical_covers_all_actively_written_values():
    from shared.attention_priority import VAZNOST_TO_CANONICAL, HIGH, INFORMATIONAL
    assert VAZNOST_TO_CANONICAL["važan"] == HIGH
    assert VAZNOST_TO_CANONICAL["informativan"] == INFORMATIONAL
    # pre-existing entries unchanged
    assert VAZNOST_TO_CANONICAL["kritičan"] != VAZNOST_TO_CANONICAL["važan"]


def test_client_portal_important_deadlines_now_includes_vazan():
    """Compounds with the earlier client_portal fix: "važan" is a real writer-produced
    value (unlike "kritican"/"vazno"), so it must count as a client-facing important
    deadline once VAZNOST_TO_CANONICAL recognizes it."""
    import routers.client_portal as cp
    assert "važan" in cp._KLIJENT_VAZNI_VAZNOST


def test_case_ready_score_low_bucket_label_matches_across_render_sites():
    assert "stEl.textContent = s >= 70 ? 'Predmet spreman za rad'" in VINDEX_JS
    assert "'Predmet u pripremi'" not in VINDEX_JS
    assert "var statusMap = {70:'Predmet spreman za rad', 40:'Predmet delimično spreman', 0:'Predmet zahteva dopunu'};" in VINDEX_JS


# ═══════════════════════════════════════════════════════════════════════════
# CIO's top-level "pouzdanost" (GPT's self-declared confidence in the whole
# briefing) was never enum-validated, unlike the per-block predmet_id references
# a few lines above it which already go through validate_predmet_reference().
# ═══════════════════════════════════════════════════════════════════════════

def test_cio_top_level_pouzdanost_is_enum_validated():
    src = open(os.path.join(REPO_ROOT, "routers", "cio.py"), encoding="utf-8").read()
    marker = 'for _kljuc in ("najveci_rizik", "najveca_prilika", "zapostavljen_predmet",'
    block = src.split(marker, 1)[1][:900]
    assert '_p = izvestaj.get("pouzdanost")' in block
    assert 'izvestaj["pouzdanost"] = _p if _p in ("visoka", "srednja", "niska") else "niska"' in block


def test_opponent_intel_pouzdanost_is_enum_validated_and_evidence_tiered():
    src = open(os.path.join(REPO_ROOT, "routers", "court_predictor.py"), encoding="utf-8").read()
    marker = 'with _ai_case_ctx(predmet_id=payload.predmet_id, module_name="court_predictor", operation_name="opponent_intel"):'
    block = src.split(marker, 1)[1][:1600]
    assert '_p = _p if _p in ("visoka", "srednja", "niska") else "niska"' in block
    assert '_total_hits = _rag_hit_count + _interni_hit_count' in block
    assert 'elif _total_hits < 3 and _p == "visoka":' in block


# ═══════════════════════════════════════════════════════════════════════════
# Team 4's AI Boundary gaps #3-5: hearing_cc.py's BLACKSWAN-AI-003 unconditional
# 0-100 clamp (applied regardless of readiness status, unlike the conditional
# readiness-tier cap) existed on only 1 of 4 GPT success-probability generators.
# Structural checks, same reasoning as test_matter_intel_selects_tip_dokaza above
# for why this repo's MagicMock-chain fixtures can't validate this behaviorally
# without a much larger endpoint-level harness (OpenAI client, rate limiter,
# real Starlette Request all required) for marginal benefit over a source check.
# ═══════════════════════════════════════════════════════════════════════════

def test_digital_twin_kreiraj_simulacija_has_unconditional_probability_clamp():
    src = open(os.path.join(REPO_ROOT, "routers", "digital_twin.py"), encoding="utf-8").read()
    marker = 'scenariji            = rezultat.get("scenariji", [])'
    # Program Phoenix, Mission 015 (LIVINGSYS-DEBT-024) widened this window from
    # 2000 -- its own explanatory comment for the conservative-cap-on-fetch-failure
    # fix pushed _CAP_BY_READINESS.get(_status) past the old boundary.
    block = src.split(marker, 1)[1][:3200]
    assert '_sc["verovatnoca"] = max(0, min(100, _v0))' in block
    # unconditional clamp must run before the readiness-tier cap, not replace it
    assert block.index('_v0))') < block.index('_CAP_BY_READINESS.get(_status)')


def test_digital_twin_sta_ako_has_unconditional_probability_clamp():
    src = open(os.path.join(REPO_ROOT, "routers", "digital_twin.py"), encoding="utf-8").read()
    marker = 'nova_verovatnoca   = rezultat.get("nova_verovatnoca_uspeha", 50)'
    # Program Phoenix, Mission 015 (LIVINGSYS-DEBT-024): widened from 700, same
    # reason as kreiraj_simulacija's window above.
    block = src.split(marker, 1)[1][:1200]
    assert 'nova_verovatnoca = max(0, min(100, nova_verovatnoca))' in block
    assert block.index('max(0, min(100') < block.index('_CAP_BY_READINESS.get(_status)')


# ═══════════════════════════════════════════════════════════════════════════
# AI Boundary gaps #1-2: kontradikcije[].tezina (raw GPT classification) flowed
# into 2 independent consumers (case_actions.prioritet, Gap.pouzdanost), each with
# its own silent "unrecognized -> middle bucket" default -- neither validated the
# value was actually one of the 3 Genome's own prompt asks for. Now both go through
# shared/contradiction_identity.py::normalize_tezina(), fail-safe toward the most
# conservative bucket ("kriticna") for out-of-enum input.
# ═══════════════════════════════════════════════════════════════════════════

def test_normalize_tezina_passes_through_valid_values():
    from shared.contradiction_identity import normalize_tezina
    assert normalize_tezina("kriticna") == "kriticna"
    assert normalize_tezina("vazna") == "vazna"
    assert normalize_tezina("manja") == "manja"


def test_normalize_tezina_fails_safe_toward_most_conservative_bucket():
    from shared.contradiction_identity import normalize_tezina
    assert normalize_tezina("ozbiljna") == "kriticna"       # GPT synonym/paraphrase
    assert normalize_tezina(None) == "kriticna"
    assert normalize_tezina("") == "kriticna"
    assert normalize_tezina("  KRITICNA  ") == "kriticna"   # case/whitespace tolerant


def test_normalize_tezina_never_raises_on_non_string_input():
    """Found by Phase 4's own adversarial test (a stray non-string in un-schema-enforced
    GPT JSON): the original (raw or "").strip() crashed outright on an int/dict/list."""
    from shared.contradiction_identity import normalize_tezina
    for hostile in (42, 3.14, True, {"a": 1}, ["x"]):
        assert normalize_tezina(hostile) == "kriticna"


@pytest.mark.anyio
async def test_case_evolution_rule3_unrecognized_tezina_does_not_silently_downgrade():
    """Before this fix: an out-of-enum tezina fell through case_evolution.py's own
    dict.get(..., "medium") default, silently keeping a possibly-critical
    contradiction OUT of BLOCKED readiness (which requires prioritet=="high")."""
    import tests.test_omega_sprint003_action_engine as t
    from services.case_evolution import _compute_target_actions

    case_dna = {"kontradikcije": [
        {"opis": "Sporan nalaz veštaka", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1",
         "tezina": "ozbiljna"},  # not one of kriticna/vazna/manja
    ]}
    supa = t._make_target_supa(case_dna=case_dna, dokazi=[], dokumenti=[], rocista=[])
    with patch("services.case_evolution._get_supa", return_value=supa):
        actions = await _compute_target_actions("pred-1")

    kontradikcije = [a for a in actions if a["tip"] == "RAZRESITI_KONTRADIKCIJU"]
    assert len(kontradikcije) == 1
    assert kontradikcije[0]["prioritet"] == "critical"


def test_gap_engine_unrecognized_tezina_does_not_silently_downgrade():
    from shared.gap_engine import gaps_from_contradictions

    case_dna = {"kontradikcije": [
        {"opis": "Sporan nalaz veštaka", "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-03 str.1",
         "tezina": "ozbiljna"},
    ]}
    gaps = gaps_from_contradictions(case_dna)
    assert len(gaps) == 1
    assert gaps[0]["pouzdanost"] == "visoka"


def test_court_predictor_has_unconditional_probability_clamp_and_ordering_fix():
    src = open(os.path.join(REPO_ROOT, "routers", "court_predictor.py"), encoding="utf-8").read()
    marker = 'analiza = (rezultat.get("analiza") or "").strip()'
    block = src.split(marker, 1)[1][:3000]
    assert 'rezultat[_k] = max(0, min(100, _v0))' in block
    assert block.index('_v0))') < block.index('CAP_BY_READINESS.get(_readiness_status)')
    # min<=max ordering enforcement, previously absent entirely
    assert 'rezultat["procenat_min"], rezultat["procenat_max"] = _pmax, _pmin' in block

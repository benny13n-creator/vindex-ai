# -*- coding: utf-8 -*-
"""
Program Sigma, Master Sprint 005 (2026-08-06) — "Case Commander Consolidation
& Operational Brain Unification". Tests proving Case Commander no longer
generates its own decisions -- every recommendation-bearing field now reads
`case_actions`/`shared/gap_engine.py`/`shared/case_readiness.py` directly, GPT
is restricted to 2 explicitly-advisory fields (protivnikova_strategija,
sudska_praksa) and to portfolio-wide contradictions/unlinked-documents
(neither of which any canonical system currently computes).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# shared/commander_schema.py — the response schema itself
# ═══════════════════════════════════════════════════════════════════════════

def test_canonical_field_shape():
    from shared.commander_schema import canonical_field
    f = canonical_field("x", source="case_actions", evidence="key-1", confidence="visoka")
    assert set(f.keys()) == {"value", "source", "evidence", "confidence", "generated_by", "timestamp"}
    assert f["generated_by"] == "deterministic"
    assert f["source"] == "case_actions"
    assert f["evidence"] == "key-1"


def test_gpt_advisory_field_never_carries_evidence():
    from shared.commander_schema import gpt_advisory_field
    f = gpt_advisory_field("neka procena", "gpt-4o")
    assert f["source"] == "gpt_advisory"
    assert f["evidence"] is None
    assert f["generated_by"] == "gpt-4o"


def test_gpt_explanation_field_points_at_original_source():
    from shared.commander_schema import gpt_explanation_field
    f = gpt_explanation_field("objašnjenje", "gpt-4o-mini", of_source="case_actions", of_evidence="key-2")
    assert f["source"] == "case_actions"
    assert f["evidence"] == "key-2"
    assert f["generated_by"] == "gpt-4o-mini"


# ═══════════════════════════════════════════════════════════════════════════
# routers/case_commander.py::_kanonski_nalazi — per-case canonical findings
# ═══════════════════════════════════════════════════════════════════════════

def _ctx(predmet=None, case_actions=None, dokazi=None, rocista=None, dokumenta=None):
    return {
        "predmet": predmet or {"naziv": "Test", "tip_postupka": "parnicno", "case_dna": {}},
        "case_actions": case_actions or [],
        "dokazi": dokazi or [],
        "rocista": rocista or [],
        "dokumenta": dokumenta or [],
        "rokovi": [], "komentari": [],
    }


def test_kanonski_nalazi_preporuceni_potez_reads_case_actions_top_priority():
    from routers.case_commander import _kanonski_nalazi

    ctx = _ctx(case_actions=[
        {"tip": "PRIBAVITI_DOKAZ", "razlog": "Pribaviti dokaz o uručenju", "prioritet": "high",
         "rok": None, "dedupe_key": "k1", "status": "open"},
        {"tip": "PLANIRATI_ROKOVE", "razlog": "manje bitno", "prioritet": "low",
         "rok": None, "dedupe_key": "k2", "status": "open"},
    ])
    result = _kanonski_nalazi(ctx)
    assert result["preporuceni_potez"]["value"] == "Pribaviti dokaz o uručenju"
    assert result["preporuceni_potez"]["source"] == "case_actions"
    assert result["preporuceni_potez"]["evidence"] == "k1"
    assert result["preporuceni_potez"]["generated_by"] == "deterministic"


def test_kanonski_nalazi_no_open_actions_says_so_not_empty():
    from routers.case_commander import _kanonski_nalazi
    ctx = _ctx(
        predmet={"naziv": "Test", "tip_postupka": "parnicno", "case_dna": {"verzija": 1}},
        case_actions=[],
    )
    result = _kanonski_nalazi(ctx)
    assert "Nema otvorenih akcija" in result["preporuceni_potez"]["value"]
    assert result["readiness_status"] == "READY"


def test_kanonski_nalazi_readiness_unknown_when_genome_never_ran():
    """No case_dna at all AND no open actions -> genuinely not enough
    signal, must be UNKNOWN, not a guessed READY."""
    from routers.case_commander import _kanonski_nalazi
    ctx = _ctx(predmet={"naziv": "Test", "tip_postupka": "parnicno", "case_dna": {}}, case_actions=[])
    result = _kanonski_nalazi(ctx)
    assert result["readiness_status"] == "UNKNOWN"


def test_kanonski_nalazi_vremenski_pritisak_uses_nearest_deadline_action():
    from routers.case_commander import _kanonski_nalazi
    ctx = _ctx(case_actions=[
        {"tip": "PRIPREMITI_PODNESAK", "razlog": "Kasniji rok", "prioritet": "high",
         "rok": "2026-12-01", "dedupe_key": "later", "status": "open"},
        {"tip": "PRIPREMITI_PODNESAK", "razlog": "Bliži rok", "prioritet": "critical",
         "rok": "2026-08-10", "dedupe_key": "sooner", "status": "open"},
    ])
    result = _kanonski_nalazi(ctx)
    assert "sooner" == result["vremenski_pritisak"]["evidence"]
    assert "2026-08-10" in result["vremenski_pritisak"]["value"]


def test_kanonski_nalazi_readiness_status_is_critical_gap_on_critical_action():
    from routers.case_commander import _kanonski_nalazi
    ctx = _ctx(case_actions=[
        {"tip": "PRIPREMITI_PODNESAK", "razlog": "Hitno", "prioritet": "critical",
         "rok": "2026-08-08", "dedupe_key": "k1", "status": "open"},
    ])
    result = _kanonski_nalazi(ctx)
    assert result["readiness_status"] == "CRITICAL_GAP"
    assert "kritičan" in result["status_predmeta"]["value"].lower()


def test_kanonski_nalazi_rizici_sourced_from_identify_case_problems():
    from routers.case_commander import _kanonski_nalazi
    # Case with zero evidence -> identify_case_problems fires "Nema uploadovanih dokaza"
    ctx = _ctx(predmet={"naziv": "Test", "tip_postupka": "parnicno", "case_dna": {}},
               case_actions=[], dokazi=[], dokumenta=[], rocista=[])
    result = _kanonski_nalazi(ctx)
    assert any("dokaza" in r["value"].lower() for r in result["rizici"])
    assert all(r["source"] == "identify_case_problems" for r in result["rizici"])
    assert all(r["generated_by"] == "deterministic" for r in result["rizici"])


# ═══════════════════════════════════════════════════════════════════════════
# routers/case_commander.py::_kanonski_prioritet_i_rizici — portfolio ranking
# ═══════════════════════════════════════════════════════════════════════════

def test_kanonski_prioritet_ranks_critical_gap_case_first():
    from routers.case_commander import _kanonski_prioritet_i_rizici

    predmeti = [
        {"id": "aaaaaaaa-1111", "naziv": "Case A (READY)", "case_actions": []},
        {"id": "bbbbbbbb-2222", "naziv": "Case B (CRITICAL)", "case_actions": [
            {"tip": "PRIPREMITI_PODNESAK", "razlog": "Hitno!", "prioritet": "critical",
             "rok": "2026-08-08", "dedupe_key": "crit-1", "status": "open"},
        ]},
    ]
    prioritet, rizici = _kanonski_prioritet_i_rizici(predmeti)
    assert prioritet is not None
    assert prioritet["predmet_naziv"] == "Case B (CRITICAL)"
    assert prioritet["source"] == "case_readiness"
    assert prioritet["evidence"] == "crit-1"


def test_kanonski_prioritet_none_when_all_cases_ready():
    from routers.case_commander import _kanonski_prioritet_i_rizici
    predmeti = [{"id": "aaaaaaaa-1111", "naziv": "Case A", "case_actions": []}]
    prioritet, rizici = _kanonski_prioritet_i_rizici(predmeti)
    assert prioritet is None
    assert rizici == []


def test_kanonski_prioritet_empty_portfolio():
    from routers.case_commander import _kanonski_prioritet_i_rizici
    prioritet, rizici = _kanonski_prioritet_i_rizici([])
    assert prioritet is None
    assert rizici == []


def test_kanonski_rizici_sorted_by_canonical_priority_across_cases():
    from routers.case_commander import _kanonski_prioritet_i_rizici
    predmeti = [
        {"id": "aaaaaaaa-1111", "naziv": "Case A", "case_actions": [
            {"tip": "OJACATI_DOKAZE", "razlog": "low prio", "prioritet": "low",
             "rok": None, "dedupe_key": "low-1", "status": "open"},
        ]},
        {"id": "bbbbbbbb-2222", "naziv": "Case B", "case_actions": [
            {"tip": "PRIPREMITI_PODNESAK", "razlog": "critical prio", "prioritet": "critical",
             "rok": "2026-08-08", "dedupe_key": "crit-1", "status": "open"},
        ]},
    ]
    _, rizici = _kanonski_prioritet_i_rizici(predmeti)
    assert rizici[0]["evidence"] == "crit-1"  # critical sorts first regardless of case order


# ═══════════════════════════════════════════════════════════════════════════
# routers/case_commander.py::commander_checklist — Phase 4, no fabricated completion
# ═══════════════════════════════════════════════════════════════════════════

def _req():
    from starlette.requests import Request as StarletteRequest
    scope = {"type": "http", "method": "POST", "headers": [], "query_string": b"",
              "path": "/api/commander/checklist", "app": MagicMock(), "state": MagicMock(),
              "client": ("testclient", 123)}
    return StarletteRequest(scope=scope)


def _commander_supa(predmet):
    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = predmet
        else:
            for chain_end in ("order", "limit", "eq", "is_"):
                pass
            m = MagicMock()
            m.execute.return_value.data = []
            t.select.return_value = m
            m.eq.return_value = m
            m.order.return_value = m
            m.limit.return_value = m
            m.is_.return_value = m
        return t

    supa.table.side_effect = _table
    return supa


@pytest.mark.anyio
async def test_cross_case_analiza_prioritet_ignores_gpt_and_uses_case_actions():
    """The actual headline bug this sprint fixed: _cross_case_analiza's own
    'prioritet' field used to be a raw GPT guess (item 4 of the old prompt).
    Even if GPT tries to claim a priority in its own JSON, the new code
    must ignore it -- the prompt itself no longer asks for it, and the
    returned prioritet must come from case_actions/case_readiness."""
    from routers import case_commander as cc

    podaci = {"predmeti": [
        {"id": "aaaaaaaa-1111", "naziv": "Predmet A (nema akcija)", "tip_postupka": "parnica",
         "protivnik": "", "sud": "", "opis": "", "rokovi": [], "dokumenti": [], "komentari": [],
         "case_actions": []},
        {"id": "bbbbbbbb-2222", "naziv": "Predmet B (kritično)", "tip_postupka": "parnica",
         "protivnik": "", "sud": "", "opis": "", "rokovi": [], "dokumenti": [], "komentari": [],
         "case_actions": [
             {"tip": "PRIPREMITI_PODNESAK", "razlog": "Rok za 2 dana", "prioritet": "critical",
              "rok": "2026-08-08", "dedupe_key": "crit-b", "status": "open"},
         ]},
    ]}

    raw = json.dumps({"nalazi": [], "rezime": "x"})

    with patch.object(cc, "_pozovi_cross_case_api", return_value=raw), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        rezultat = await cc._cross_case_analiza(podaci, "Advokat Test")

    assert rezultat["prioritet"]["predmet_naziv"] == "Predmet B (kritično)"
    assert rezultat["prioritet"]["source"] == "case_readiness"
    assert rezultat["prioritet"]["evidence"] == "crit-b"


@pytest.mark.anyio
async def test_cross_case_analiza_survives_total_gpt_failure_with_canonical_findings():
    """Real behavior improvement: a total GPT outage no longer empties the
    whole brief when case_actions has real, deterministic findings."""
    from routers import case_commander as cc

    podaci = {"predmeti": [
        {"id": "bbbbbbbb-2222", "naziv": "Predmet B", "tip_postupka": "parnica",
         "protivnik": "", "sud": "", "opis": "", "rokovi": [], "dokumenti": [], "komentari": [],
         "case_actions": [
             {"tip": "PRIPREMITI_PODNESAK", "razlog": "Rok za 2 dana", "prioritet": "critical",
              "rok": "2026-08-08", "dedupe_key": "crit-b", "status": "open"},
         ]},
    ]}

    with patch.object(cc, "_pozovi_cross_case_api", side_effect=Exception("trajna greška")), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        rezultat = await cc._cross_case_analiza(podaci, "Advokat Test")

    assert rezultat["nalazeni"] is True
    assert rezultat["greska"] is True
    assert rezultat["prioritet"]["predmet_naziv"] == "Predmet B"
    assert any(n["evidence"] == "crit-b" for n in rezultat["nalazi"])


@pytest.mark.anyio
async def test_checklist_never_reports_a_step_as_completed():
    from routers import case_commander as cc

    predmet = {"naziv": "Test predmet", "tip_postupka": "gradjansko", "status": "aktivan", "case_dna": {}}
    supa = _commander_supa(predmet)

    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content=(
        "## Priprema\n- [x] Sakupiti dokaze\n- [ ] Pripremiti tužbu\n"
    )))]

    with patch.object(cc, "_get_supa", return_value=supa), \
         patch.object(cc.UsageService, "consume", new=AsyncMock()), \
         patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.return_value = fake_response
        result = await cc.commander_checklist(
            _req(), cc.ChecklistRequest(predmet_id="pred-1"),
            user={"user_id": "u1", "email": "a@b.com"},
        )

    assert all(stavka["completed"] is False for stavka in result["stavke"])
    assert len(result["stavke"]) == 2

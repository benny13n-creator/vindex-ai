# -*- coding: utf-8 -*-
"""
Program Sigma, Master Sprint 004 (2026-08-06) — "Legal Case Readiness & Action
Planning Engine". Tests for shared/case_readiness.py (top_open_action,
compute_case_readiness) and its 2 integration points -- proves the real,
previously-unknown bug this sprint found: routers/case_intelligence.py's own
AI Briefing and routers/copilot.py::_handle_analiza_predmeta each
independently GPT-generated their own "single most urgent next action" +
urgency tier, fully disconnected from case_actions (the platform's own
canonical, deterministic action-tracking table) -- exactly the "Copilot
verzija / Strategy verzija" duplication this sprint's own Phase 2 forbids.
Fixed: both now read case_actions' own highest-priority open row instead.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# shared/case_readiness.py::top_open_action
# ═══════════════════════════════════════════════════════════════════════════

def test_top_open_action_none_when_empty():
    from shared.case_readiness import top_open_action
    assert top_open_action([]) is None
    assert top_open_action(None) is None


def test_top_open_action_picks_highest_canonical_priority():
    from shared.case_readiness import top_open_action
    rows = [
        {"razlog": "B", "prioritet": "medium", "status": "open"},
        {"razlog": "A", "prioritet": "critical", "status": "open"},
        {"razlog": "C", "prioritet": "low", "status": "open"},
    ]
    top = top_open_action(rows)
    assert top["razlog"] == "A"


def test_top_open_action_ignores_closed_rows():
    from shared.case_readiness import top_open_action
    rows = [
        {"razlog": "closed-critical", "prioritet": "critical", "status": "closed"},
        {"razlog": "open-medium", "prioritet": "medium", "status": "open"},
    ]
    top = top_open_action(rows)
    assert top["razlog"] == "open-medium"


def test_top_open_action_tiebreaks_by_earlier_deadline():
    from shared.case_readiness import top_open_action
    rows = [
        {"razlog": "later", "prioritet": "high", "rok": "2026-12-01", "status": "open"},
        {"razlog": "sooner", "prioritet": "high", "rok": "2026-09-01", "status": "open"},
    ]
    top = top_open_action(rows)
    assert top["razlog"] == "sooner"


# ═══════════════════════════════════════════════════════════════════════════
# shared/case_readiness.py::compute_case_readiness — the 5-state model
# ═══════════════════════════════════════════════════════════════════════════

def test_readiness_unknown_when_nothing_computed_yet():
    from shared.case_readiness import compute_case_readiness, UNKNOWN
    result = compute_case_readiness([], [], genome_computed=False)
    assert result["status"] == UNKNOWN


def test_readiness_critical_gap_beats_everything_else():
    from shared.case_readiness import compute_case_readiness, CRITICAL_GAP
    actions = [
        {"tip": "PRIBAVITI_DOKAZ", "prioritet": "high", "status": "open", "razlog": "high"},
        {"tip": "PRIPREMITI_PODNESAK", "prioritet": "critical", "status": "open", "razlog": "URGENT", "dedupe_key": "k1"},
    ]
    result = compute_case_readiness(actions, [])
    assert result["status"] == CRITICAL_GAP
    assert result["razlog"] == "URGENT"
    assert result["izvor"] == ["k1"]


def test_readiness_blocked_on_high_priority_evidence_or_contradiction_gap():
    from shared.case_readiness import compute_case_readiness, BLOCKED
    actions = [{"tip": "RAZRESITI_KONTRADIKCIJU", "prioritet": "high", "status": "open", "razlog": "x", "dedupe_key": "k2"}]
    result = compute_case_readiness(actions, [])
    assert result["status"] == BLOCKED


def test_readiness_blocked_not_triggered_by_high_priority_non_blocking_type():
    """A high-priority PLANIRATI_ROKOVE action isn't a hard blocker (not
    PRIBAVITI_DOKAZ/RAZRESITI_KONTRADIKCIJU) -- must fall through to
    PARTIALLY_READY, not BLOCKED."""
    from shared.case_readiness import compute_case_readiness, PARTIALLY_READY
    actions = [{"tip": "PLANIRATI_ROKOVE", "prioritet": "high", "status": "open", "razlog": "x"}]
    result = compute_case_readiness(actions, [])
    assert result["status"] == PARTIALLY_READY


def test_readiness_partially_ready_on_low_priority_open_action():
    from shared.case_readiness import compute_case_readiness, PARTIALLY_READY
    actions = [{"tip": "OJACATI_DOKAZE", "prioritet": "informational", "status": "open", "razlog": "x"}]
    result = compute_case_readiness(actions, [])
    assert result["status"] == PARTIALLY_READY


def test_readiness_partially_ready_on_hypothesis_only_gap_with_no_actions():
    from shared.case_readiness import compute_case_readiness, PARTIALLY_READY
    gaps = [{"tip": "GENOME_NEDOSTAJE", "hipoteza": True, "razlog": "Možda nedostaje aneks", "dedupe_key": "g1"}]
    result = compute_case_readiness([], gaps)
    assert result["status"] == PARTIALLY_READY
    assert result["izvor"] == ["g1"]


def test_readiness_ready_when_nothing_open_and_no_gaps():
    from shared.case_readiness import compute_case_readiness, READY
    result = compute_case_readiness([], [])
    assert result["status"] == READY


def test_readiness_deterministic_gap_hipoteza_false_does_not_alone_trigger_partial():
    """A deterministic (hipoteza=False) gap with no corresponding open
    case_actions row is a data inconsistency the model shouldn't crash on --
    but per this model's own explicit rule set, only hipoteza=True gaps are
    checked directly (deterministic findings are expected to already be
    represented via case_actions)."""
    from shared.case_readiness import compute_case_readiness, READY
    gaps = [{"tip": "NEMA_DOKAZA", "hipoteza": False, "razlog": "x"}]
    result = compute_case_readiness([], gaps)
    assert result["status"] == READY


# ═══════════════════════════════════════════════════════════════════════════
# routers/case_intelligence.py — AI Briefing override
# ═══════════════════════════════════════════════════════════════════════════

def _req():
    scope = {"type": "http", "method": "POST", "headers": [], "query_string": b"",
             "path": "/api/intelligence/predmeti/predmet-1/briefing", "app": MagicMock(), "state": MagicMock(),
             "client": ("testclient", 123)}
    return StarletteRequest(scope=scope)


def _resp(content: str):
    m = MagicMock()
    m.choices = [MagicMock(message=MagicMock(content=content))]
    return m


def _chain(data=None):
    c = MagicMock()
    for attr in ["select", "eq", "in_", "order", "limit", "maybe_single", "insert"]:
        setattr(c, attr, MagicMock(return_value=c))
    c.execute = MagicMock(return_value=MagicMock(data=data))
    return c


def _make_ci_supa(case_actions_data=None):
    predmeti_chain = _chain(data={"naziv": "Test predmet", "tip": "parnica", "status": "aktivan",
                                    "oblast_prava": "", "opis": "", "klijent_id": None, "case_dna": {}})
    empty_list_chain = _chain(data=[])
    tables = {
        "predmeti": predmeti_chain,
        "lessons_learned": empty_list_chain,
        "firm_dna": empty_list_chain,
        "case_patterns": empty_list_chain,
        "proactive_alerts": empty_list_chain,
        "decision_log": empty_list_chain,
        "case_actions": _chain(data=case_actions_data or []),
    }
    supa = MagicMock()
    supa.table = MagicMock(side_effect=lambda name: tables.get(name, empty_list_chain))
    return supa


@pytest.mark.anyio
async def test_briefing_overrides_gpt_next_action_with_case_actions_top_priority():
    """The actual bug: when case_actions has an open row, the briefing's own
    sledeci_korak/razlog/hitnost must come from IT, not from GPT's own guess."""
    from routers import case_intelligence as ci

    supa = _make_ci_supa(case_actions_data=[
        {"razlog": "Pripremiti odgovor na tužbu -- rok za 2 dana", "prioritet": "critical",
         "rok": "2026-08-08", "dedupe_key": "rociste_x", "status": "open"},
    ])

    with patch.object(ci, "_get_supa", return_value=supa), \
         patch.object(ci, "_pozovi_briefing_api", new=AsyncMock(return_value=_resp(json.dumps({
             "sledeci_korak": "GPT-ova sopstvena, netačna procena",
             "hitnost": "ovaj_mesec", "razlog": "GPT-ov sopstveni razlog",
             "pouzdanost_briefinga": "SREDNJA",
         })))), \
         patch.object(ci.UsageService, "consume", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await ci.case_intelligence_briefing(
            _req(), "predmet-1", user={"user_id": "u1", "email": "a@b.com"},
        )

    assert result["briefing"]["sledeci_korak"] == "Pripremiti odgovor na tužbu -- rok za 2 dana"
    assert result["briefing"]["hitnost"] == "odmah"  # critical -> odmah
    assert "rociste_x" in result["briefing"]["razlog"]


@pytest.mark.anyio
async def test_briefing_states_no_open_action_instead_of_falling_back_to_gpt_program_tau_003():
    """Supersedes this file's own prior test (same fixture, opposite
    assertion): Program Tau, Master Sprint 003 (2026-08-06) found the
    Sigma-004 override above was only CONDITIONAL -- GPT's own raw guess
    survived whenever case_actions had nothing open, exactly the "GPT may
    never redefine" gap Tau 003 exists to close. sledeci_korak/razlog/hitnost
    are no longer even asked of GPT (see case_intelligence.py's own
    _BRIEFING_SYSTEM) -- an honest "nothing open" statement now replaces the
    old GPT fallback unconditionally."""
    from routers import case_intelligence as ci

    supa = _make_ci_supa(case_actions_data=[])

    with patch.object(ci, "_get_supa", return_value=supa), \
         patch.object(ci, "_pozovi_briefing_api", new=AsyncMock(return_value=_resp(json.dumps({
             "relevantne_lekcije": [], "komunikacioni_savet": "", "potvrdjeni_obrasci": [],
         })))), \
         patch.object(ci.UsageService, "consume", new=AsyncMock()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await ci.case_intelligence_briefing(
            _req(), "predmet-1", user={"user_id": "u1", "email": "a@b.com"},
        )

    assert result["briefing"]["sledeci_korak"] == "Nema otvorenih akcija u Case Actions za ovaj predmet."
    assert result["briefing"]["hitnost"] == "ovaj_mesec"


# ═══════════════════════════════════════════════════════════════════════════
# routers/copilot.py::_handle_analiza_predmeta — sledeci_korak override
# ═══════════════════════════════════════════════════════════════════════════

def _make_copilot_supa(predmet: dict, case_actions_data=None):
    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = predmet
        elif name == "case_actions":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = case_actions_data or []
        else:
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
            t.select.return_value.eq.return_value.execute.return_value.data = []
        return t

    supa.table.side_effect = _table
    return supa


def _fake_gpt_response(payload: dict):
    msg = MagicMock()
    msg.message.content = json.dumps(payload)
    resp = MagicMock()
    resp.choices = [msg]
    return resp


@pytest.mark.anyio
async def test_analiza_predmeta_overrides_sledeci_korak_with_case_actions_top_priority():
    from routers.copilot import _handle_analiza_predmeta

    predmet = {"naziv": "Test predmet", "opis": "Opis", "tip": "radno", "status": "aktivan", "case_dna": None}
    supa = _make_copilot_supa(predmet, case_actions_data=[
        {"razlog": "Pribaviti dokaz o uručenju", "prioritet": "high", "rok": None, "status": "open"},
    ])
    gpt_payload = {
        "procena": "x", "prednosti": [], "slabosti": [], "nedostaju": [],
        "sledeci_korak": {"opis": "GPT-ova sopstvena procena", "rok": "", "prioritet": "normalan"},
        "verovatnoca_uspeha": 50,
    }

    async def _fake_call(oai, **kwargs):
        return _fake_gpt_response(gpt_payload)

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._pozovi_gpt4o_mini", new=_fake_call):
        result = await _handle_analiza_predmeta("Šanse?", "pred-1", "user-1")

    assert result["sledeci_korak"]["opis"] == "Pribaviti dokaz o uručenju"
    assert result["sledeci_korak"]["prioritet"] == "hitan"  # high -> hitan


@pytest.mark.anyio
async def test_analiza_predmeta_states_no_open_action_instead_of_falling_back_to_gpt_program_tau_003():
    """Supersedes this file's own prior test (same fixture, opposite
    assertion): Program Tau, Master Sprint 003 (2026-08-06) found the Sigma-004
    override below was only CONDITIONAL -- GPT's own raw sledeci_korak guess
    survived whenever case_actions had nothing open. Now unconditional; an
    honest "nothing open" statement replaces the GPT fallback."""
    from routers.copilot import _handle_analiza_predmeta

    predmet = {"naziv": "Test predmet", "opis": "Opis", "tip": "radno", "status": "aktivan", "case_dna": None}
    supa = _make_copilot_supa(predmet, case_actions_data=[])
    gpt_payload = {"procena": "x", "prednosti": []}

    async def _fake_call(oai, **kwargs):
        return _fake_gpt_response(gpt_payload)

    with patch("routers.copilot._get_supa", return_value=supa), \
         patch("routers.copilot._pozovi_gpt4o_mini", new=_fake_call):
        result = await _handle_analiza_predmeta("Šanse?", "pred-1", "user-1")

    assert result["sledeci_korak"]["opis"] == "Nema otvorenih akcija u Case Actions za ovaj predmet."

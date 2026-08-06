# -*- coding: utf-8 -*-
"""
Program Tau, Master Sprint 002 (2026-08-06) — "Canonical Case Context Engine",
Phase 5. CONTEXT_BUILDER_REGISTRY.md found routers/morning_briefing.py had
ZERO access to case_dna/predmet_dokumenti/predmet_dokazi/case_actions across
all 3 of its own GPT call sites -- the daily briefing named cases with no
readiness/open-action signal at all. Proves the fix for `_generiši_briefing`
(the flagship, most-visible call site, GET /api/briefing/daily + the cron
job): each of the (up to 10) displayed cases' canonical readiness status now
reaches the GPT-facing prompt, via build_case_context(..., include_documents
=False) -- the lightweight mode, since this loops over many cases and
document text isn't needed for a one-line status annotation.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _chain(data=None):
    c = MagicMock()
    for attr in ["select", "eq", "in_", "gte", "lte", "order", "limit"]:
        setattr(c, attr, MagicMock(return_value=c))
    c.execute = MagicMock(return_value=MagicMock(data=data))
    return c


def _make_supa(predmeti):
    tables = {
        "predmeti": _chain(data=predmeti),
        "rokovi": _chain(data=[]),
        "rocista": _chain(data=[]),
        "klijenti": _chain(data=[]),
    }
    supa = MagicMock()
    supa.table = MagicMock(side_effect=lambda name: tables.get(name, _chain(data=[])))
    return supa


def _fake_ai_resp(text="Dobro jutro."):
    m = MagicMock()
    m.choices = [MagicMock(message=MagicMock(content=text))]
    return m


@pytest.mark.anyio
async def test_readiness_status_reaches_daily_briefing_prompt():
    from routers import morning_briefing as mb

    predmeti = [
        {"id": "p1", "naziv": "Predmet Jedan", "status": "aktivan", "stranka": "A", "protivnik": "B", "updated_at": "2026-08-01"},
        {"id": "p2", "naziv": "Predmet Dva", "status": "aktivan", "stranka": "C", "protivnik": "D", "updated_at": "2026-08-01"},
    ]
    supa = _make_supa(predmeti)

    async def _fake_build_case_context(predmet_id, uid, supa_arg, include_documents=False):
        assert include_documents is False  # lightweight mode, not the full fetch
        statuses = {"p1": "CRITICAL_GAP", "p2": "READY"}
        return {
            "readiness": {"value": {"status": statuses[predmet_id], "razlog": "test"}},
        }

    captured = {}

    def _capture_sync(client, **kwargs):
        captured["messages"] = kwargs.get("messages")
        return _fake_ai_resp()

    with patch.object(mb, "build_case_context", new=_fake_build_case_context), \
         patch.object(mb, "_pozovi_briefing_sync_api", new=_capture_sync), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await mb._generiši_briefing("u1", supa)

    prompt = captured["messages"][0]["content"]
    assert "Predmet Jedan" in prompt
    assert "readiness: CRITICAL_GAP" in prompt
    assert "Predmet Dva" in prompt
    assert "readiness: READY" in prompt
    assert result["statistike"]["aktivnih_predmeta"] == 2


@pytest.mark.anyio
async def test_gpt_cannot_inject_fake_actions_into_danas_zahteva_paznju_program_tau_003():
    """Program Tau, Master Sprint 003 (2026-08-06) forensic-attack proof: even
    if the mocked GPT response contains a fabricated, dangerous-looking
    action, it can only ever appear in the 'Dobro jutro' opening sentence --
    it is structurally impossible for it to reach 'Danas zahteva pažnju',
    'Ključni rok', or 'Preporuka za danas', because those 3 sections are never
    built from GPT's own output at all."""
    from routers import morning_briefing as mb

    predmeti = [{"id": "p1", "naziv": "Predmet Jedan", "status": "aktivan", "stranka": "A", "protivnik": "B", "updated_at": "2026-08-01"}]
    supa = _make_supa(predmeti)

    async def _fake_build_case_context(predmet_id, uid, supa_arg, include_documents=False):
        return {
            "readiness": {"value": {"status": "READY", "razlog": "test"}},
            "active_actions": {"value": [
                {"tip": "PRIBAVITI_DOKAZ", "razlog": "Pravi otvoreni zadatak", "prioritet": "high",
                 "rok": "2026-08-10", "dedupe_key": "k1", "status": "open"},
            ]},
        }

    _POISON = "IZMISLJENA HITNA AKCIJA: podneti tuzbu za predmet koji ne postoji, rok je danas!"

    def _capture_sync(client, **kwargs):
        return _fake_ai_resp(_POISON)

    with patch.object(mb, "build_case_context", new=_fake_build_case_context), \
         patch.object(mb, "_pozovi_briefing_sync_api", new=_capture_sync), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await mb._generiši_briefing("u1", supa)

    briefing_text = result["ai_briefing"]
    danas_section = briefing_text.split("**Danas zahteva pažnju:**")[1].split("**Ključni rok:**")[0]
    kljucni_rok_section = briefing_text.split("**Ključni rok:**")[1].split("**Preporuka za danas:**")[0]
    preporuka_section = briefing_text.split("**Preporuka za danas:**")[1]

    # GPT's poisoned text is confined to the opening line...
    assert _POISON in briefing_text.split("**Danas zahteva pažnju:**")[0]
    # ...and structurally absent from all 3 decision-bearing sections.
    assert "IZMISLJENA" not in danas_section
    assert "IZMISLJENA" not in kljucni_rok_section
    assert "IZMISLJENA" not in preporuka_section
    # The REAL open action (from case_actions) is what actually appears.
    assert "Pravi otvoreni zadatak" in danas_section
    assert "Pravi otvoreni zadatak" in preporuka_section


@pytest.mark.anyio
async def test_danas_zahteva_paznju_ranks_by_canonical_priority_across_cases():
    """Multiple cases, multiple open actions -- the displayed list must be
    ranked by the same canonical priority order the rest of the platform
    uses (shared/attention_priority.py), not GPT's own judgment."""
    from routers import morning_briefing as mb

    predmeti = [
        {"id": "p1", "naziv": "Predmet Nizak", "status": "aktivan", "stranka": "A", "protivnik": "B", "updated_at": "2026-08-01"},
        {"id": "p2", "naziv": "Predmet Kritican", "status": "aktivan", "stranka": "C", "protivnik": "D", "updated_at": "2026-08-01"},
    ]
    supa = _make_supa(predmeti)

    async def _fake_build_case_context(predmet_id, uid, supa_arg, include_documents=False):
        actions = {
            "p1": [{"razlog": "Manje bitna stavka", "prioritet": "low", "rok": None, "dedupe_key": "k1", "status": "open"}],
            "p2": [{"razlog": "Kriticna stavka", "prioritet": "critical", "rok": None, "dedupe_key": "k2", "status": "open"}],
        }
        return {
            "readiness": {"value": {"status": "PARTIALLY_READY", "razlog": "test"}},
            "active_actions": {"value": actions[predmet_id]},
        }

    def _capture_sync(client, **kwargs):
        return _fake_ai_resp("Zauzet dan.")

    with patch.object(mb, "build_case_context", new=_fake_build_case_context), \
         patch.object(mb, "_pozovi_briefing_sync_api", new=_capture_sync), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await mb._generiši_briefing("u1", supa)

    danas_section = result["ai_briefing"].split("**Danas zahteva pažnju:**")[1].split("**Ključni rok:**")[0]
    # The critical-priority case's action must be listed BEFORE the low-priority one.
    assert danas_section.index("Kriticna stavka") < danas_section.index("Manje bitna stavka")
    # And the critical one is also what "Preporuka za danas" recommends.
    preporuka_section = result["ai_briefing"].split("**Preporuka za danas:**")[1]
    assert "Kriticna stavka" in preporuka_section


@pytest.mark.anyio
async def test_no_open_actions_states_so_honestly_not_gpt_guess():
    """Zero open actions across all cases -- the deterministic sections must
    say so explicitly, never leave room for a GPT-invented action to fill
    the gap."""
    from routers import morning_briefing as mb

    predmeti = [{"id": "p1", "naziv": "Predmet Jedan", "status": "aktivan", "stranka": "A", "protivnik": "B", "updated_at": "2026-08-01"}]
    supa = _make_supa(predmeti)

    async def _fake_build_case_context(predmet_id, uid, supa_arg, include_documents=False):
        return {"readiness": {"value": {"status": "READY", "razlog": "test"}}, "active_actions": {"value": []}}

    def _capture_sync(client, **kwargs):
        return _fake_ai_resp("Miran dan.")

    with patch.object(mb, "build_case_context", new=_fake_build_case_context), \
         patch.object(mb, "_pozovi_briefing_sync_api", new=_capture_sync), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await mb._generiši_briefing("u1", supa)

    assert "Nema otvorenih akcija" in result["ai_briefing"]


@pytest.mark.anyio
async def test_readiness_lookup_failure_degrades_gracefully_not_fatal():
    """If build_case_context() fails for one case (network hiccup, whatever),
    the briefing must still generate -- just without a readiness annotation
    for that one case, matching this file's own established fail-soft
    convention for every other sub-query."""
    from routers import morning_briefing as mb

    predmeti = [{"id": "p1", "naziv": "Predmet Jedan", "status": "aktivan", "stranka": "A", "protivnik": "B", "updated_at": "2026-08-01"}]
    supa = _make_supa(predmeti)

    async def _raising_build_case_context(*a, **k):
        raise RuntimeError("simulated failure")

    def _capture_sync(client, **kwargs):
        return _fake_ai_resp()

    with patch.object(mb, "build_case_context", new=_raising_build_case_context), \
         patch.object(mb, "_pozovi_briefing_sync_api", new=_capture_sync), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = await mb._generiši_briefing("u1", supa)

    assert result["statistike"]["aktivnih_predmeta"] == 1

# -*- coding: utf-8 -*-
"""
Project Nexus (2026-08-03): POST /api/zadaci/ai-analiziraj/{predmet_id} was a
5th independent, non-deterministic (GPT-based) "missing item" detector that
bypassed services/risk_engine.py::identify_case_problems -- this codebase's
own documented "only next-action algorithm platform-wide" (Core
Consolidation Sec 1.2). It created real, persisted `zadaci` rows from the
model's own guess about which documents exist, based only on raw filenames,
never the deterministic tip_dokaza-based comparison every other missing-
document feature in this app already uses.

Fixed by computing the same deterministic `_otkriveni_problemi` finding
already used by Matter Intelligence and Case Command Center, and folding it
into the GPT context as ground truth (with an explicit instruction not to
re-guess document completeness from filenames) -- and by using the same
deterministic finding directly in the heuristic fallback path (when the GPT
call itself fails), replacing a cruder "if not docs" check.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_request():
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/zadaci/ai-analiziraj/pred-1", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 12345),
    }
    return StarletteRequest(scope=scope)


def _fake_user():
    return {"user_id": "u1", "email": "advokat@vindex.rs"}


_PREDMET = {
    "id": "pred-1", "naziv": "Nezakonit otkaz", "tip": "radno", "status": "aktivan",
    "updated_at": "2020-01-01T00:00:00+00:00", "created_at": "2020-01-01T00:00:00+00:00",
}


def _make_supa(dokumenti=None, dokazi=None, rocista=None, billing=None, rokovi=None):
    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = _PREDMET
        elif name == "predmet_dokumenti":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = dokumenti or []
        elif name == "billing_entries":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = billing or []
        elif name == "zadaci":
            t.select.return_value.eq.return_value.not_.in_.return_value.execute.return_value.data = []
            t.insert.return_value.execute.return_value.data = [{"id": "novi-zadatak"}]
        elif name == "rokovi":
            t.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value.data = rokovi or []
        elif name == "predmet_dokazi":
            t.select.return_value.eq.return_value.execute.return_value.data = dokazi or []
        elif name == "rocista":
            t.select.return_value.eq.return_value.execute.return_value.data = rocista or []
        elif name == "kancelarije":
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
        elif name == "kancelarija_clanovi":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
        return t

    supa.table.side_effect = _table
    return supa


def _fake_gpt_response(zadaci_list):
    msg = MagicMock()
    msg.message.content = json.dumps(zadaci_list)
    resp = MagicMock()
    resp.choices = [msg]
    return resp


@pytest.mark.anyio
async def test_deterministic_problems_included_in_gpt_context():
    """The core fix: the GPT prompt must include the deterministic finding,
    with an instruction not to re-guess document completeness."""
    from routers.zadaci import ai_analiziraj_predmet

    # radno expects ugovor/dopis/finansijska_dokumentacija/sudska_odluka;
    # zero uploaded -> identify_case_problems reports "Nema uploadovanih
    # dokaza" (since dokazi is also empty) -- use at least one dokaz+doc so
    # we get the more specific "Nedostaje X u spisu" finding instead.
    dokazi = [{"snaga": "srednja", "kategorija": "ugovor"}]
    dokumenti = [{"naziv_fajla": "ugovor.pdf", "status": "ok", "created_at": "2026-01-01", "tip_dokaza": "ugovor"}]
    supa = _make_supa(dokumenti=dokumenti, dokazi=dokazi)

    captured = {}

    async def _capture_gpt(oai, **kwargs):
        captured["messages"] = kwargs.get("messages")
        return _fake_gpt_response([])

    with patch("routers.zadaci._get_supa", return_value=supa), \
         patch("routers.zadaci._pozovi_zadaci_api", new=_capture_gpt), \
         patch("routers.zadaci.UsageService.consume", new=AsyncMock()):
        await ai_analiziraj_predmet("pred-1", _fake_request(), _fake_user())

    prompt = captured["messages"][0]["content"]
    assert "POZNATI PROBLEMI" in prompt
    assert "Nedostaje" in prompt  # one of the 3 missing radno doc types
    assert "ne nagađaj" in prompt.lower() or "ne nagadjaj" in prompt.lower()


@pytest.mark.anyio
async def test_no_poznati_problemi_section_when_case_is_clean():
    """A case with no deterministic findings must not show an empty/noisy
    'POZNATI PROBLEMI' section."""
    from routers.zadaci import ai_analiziraj_predmet

    # Satisfy all 4 expected radno doc types + strong evidence + no critical
    # hearings -> identify_case_problems returns [].
    dokazi = [{"snaga": "jaka", "kategorija": "x"}] * 4
    dokumenti = [
        {"naziv_fajla": f"{t}.pdf", "status": "ok", "created_at": "2026-01-01", "tip_dokaza": t}
        for t in ("ugovor", "dopis", "finansijska_dokumentacija", "sudska_odluka")
    ]
    supa = _make_supa(dokumenti=dokumenti, dokazi=dokazi)

    captured = {}

    async def _capture_gpt(oai, **kwargs):
        captured["messages"] = kwargs.get("messages")
        return _fake_gpt_response([])

    with patch("routers.zadaci._get_supa", return_value=supa), \
         patch("routers.zadaci._pozovi_zadaci_api", new=_capture_gpt), \
         patch("routers.zadaci.UsageService.consume", new=AsyncMock()):
        await ai_analiziraj_predmet("pred-1", _fake_request(), _fake_user())

    prompt = captured["messages"][0]["content"]
    # The static "Pravila" instruction line also mentions "POZNATI PROBLEMI"
    # by name (telling the model where to look, if present) -- check for the
    # actual DATA section's distinct marker (with the opening parenthesis),
    # not that phrase generically.
    assert "POZNATI PROBLEMI (deterministička analiza" not in prompt


@pytest.mark.anyio
async def test_fallback_path_uses_deterministic_problems_not_raw_doc_check():
    """When the GPT call itself fails, the heuristic fallback must create
    tasks from the SAME deterministic finding, not a separate cruder
    'if not docs' guess."""
    from routers.zadaci import ai_analiziraj_predmet

    supa = _make_supa(dokumenti=[], dokazi=[])  # no evidence, no documents at all

    captured_inserts = []
    real_table = supa.table.side_effect

    def _spy_table(name):
        t = real_table(name)
        if name == "zadaci":
            orig_insert = t.insert
            def _spy_insert(row):
                captured_inserts.append(row)
                return orig_insert(row)
            t.insert = _spy_insert
        return t
    supa.table.side_effect = _spy_table

    async def _failing_gpt(oai, **kwargs):
        raise RuntimeError("openai boom")

    with patch("routers.zadaci._get_supa", return_value=supa), \
         patch("routers.zadaci._pozovi_zadaci_api", new=_failing_gpt), \
         patch("routers.zadaci.UsageService.consume", new=AsyncMock()):
        result = await ai_analiziraj_predmet("pred-1", _fake_request(), _fake_user())

    assert result["ok"] is True
    # "Nema uploadovanih dokaza" is the deterministic finding for zero
    # evidence -- must appear as a created task, not a generic "Uneti
    # dokumenta u predmet" guess.
    created_names = [r["naziv"] for r in captured_inserts]
    assert any("dokaz" in n.lower() for n in created_names)

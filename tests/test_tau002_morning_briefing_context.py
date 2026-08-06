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

# -*- coding: utf-8 -*-
"""
Program Tau, Master Sprint 004 (2026-08-06) -- "Canonical Legal Reasoning &
GPT-5.5 Intelligence Layer", Phase 5 (extreme scale) -- Performance Engineer.

Proves or disproves that shared/case_context.py::build_case_context() and
shared/gap_engine.py correctly handle: 300 deadlines, 50 contradictions, and
a 20-year-old case, without silent truncation or date-arithmetic bugs.
(500/1000-document scale is already covered by tests/test_tau002_case_context.py
-- not duplicated here.)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, data):
        self._data = data
        self._single = False

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def maybe_single(self):
        self._single = True
        return self

    def execute(self):
        if self._single:
            d = self._data
            return _FakeResult(d if isinstance(d, dict) else (d[0] if d else None))
        return _FakeResult(self._data)


class _FakeSupa:
    def __init__(self, tables: dict):
        self._tables = tables

    def table(self, name):
        return _FakeQuery(self._tables.get(name, []))


@pytest.mark.anyio
async def test_300_deadlines_not_silently_dropped():
    """rocista is fetched with no .limit() in shared/case_context.py::_fetch_raw
    -- confirmed by reading the code before writing this test. Proves it
    empirically too: 300 rows in, 300 rows out."""
    from shared.case_context import build_case_context
    rocista = [{"id": f"r{i}", "sud": f"Sud {i%5}", "datum": f"2026-{(i%12)+1:02d}-01", "status": "zakazano"} for i in range(300)]
    tables = {
        "predmeti": {"id": "p1", "naziv": "Test", "tip_postupka": "parnicno", "case_dna": {}},
        "rocista": rocista,
    }
    supa = _FakeSupa(tables)
    result = await build_case_context("p1", "u1", supa)
    assert len(result["deadlines"]["value"]) == 300


@pytest.mark.anyio
async def test_50_contradictions_not_silently_capped():
    """shared/gap_engine.py::gaps_from_contradictions has no [:N] slice --
    confirmed by reading the source before writing this test (unlike the
    Tau 003 DISPLAY-layer caps in case_intelligence.py/copilot.py, which
    only truncate what's shown to a lawyer, not the raw case_context data)."""
    from shared.case_context import build_case_context
    kontradikcije = [
        {"opis": f"Kontradikcija broj {i}", "lokacija_1": f"DOK-{i}", "lokacija_2": f"DOK-{i+1}", "tezina": "vazna"}
        for i in range(50)
    ]
    tables = {
        "predmeti": {"id": "p1", "naziv": "Test", "tip_postupka": "parnicno",
                     "case_dna": {"verzija": 1, "kontradikcije": kontradikcije}},
    }
    supa = _FakeSupa(tables)
    result = await build_case_context("p1", "u1", supa)
    assert len(result["contradictions"]["value"]) == 50


@pytest.mark.anyio
async def test_20_year_old_case_date_arithmetic_does_not_break():
    """predmeti/rocista/predmet_hronologija rows from 2006 (20 years before
    'today', 2026-08-06 per this session's own established date) must not
    crash or silently vanish from build_case_context()'s own output."""
    from shared.case_context import build_case_context
    tables = {
        "predmeti": {
            "id": "p1", "naziv": "Star predmet", "tip_postupka": "parnicno",
            "status": "aktivan", "case_dna": {},
        },
        "rocista": [{"id": "r-old", "sud": "Osnovni sud", "datum": "2006-01-15", "status": "zavrseno"}],
        "predmet_hronologija": [{"dogadjaj": "Podneta tuzba", "datum_iso": "2006-01-10", "vaznost": "kritičan"}],
    }
    supa = _FakeSupa(tables)
    result = await build_case_context("p1", "u1", supa)
    assert result["deadlines"]["value"][0]["datum"] == "2006-01-15"
    assert result["timeline"]["value"][0]["datum_iso"] == "2006-01-10"


def test_morning_briefing_dani_do_handles_20_year_old_and_future_dates():
    """routers/morning_briefing.py::_dani_do (inline closure) -- re-implemented
    identically here since it's a closure, not importable -- proves
    date.fromisoformat subtraction doesn't overflow/misbehave for very old
    or far-future dates."""
    from datetime import date
    danas = date(2026, 8, 6)

    def _dani_do(datum_str: str) -> int:
        try:
            return (date.fromisoformat(str(datum_str)[:10]) - danas).days
        except Exception:
            return 999

    assert _dani_do("2006-01-15") < 0  # 20 years in the past -- large negative, no crash
    assert _dani_do("2046-01-15") > 0  # 20 years in the future -- large positive, no crash
    assert _dani_do("not-a-date") == 999  # malformed input -- fail-soft, not a crash

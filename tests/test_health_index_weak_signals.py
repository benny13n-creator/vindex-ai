# -*- coding: utf-8 -*-
"""
G-031 (D26, VINDEX_OPERATIONAL_GAP_REGISTER.md) — routers/health_index.py::
_compute_weak_signals previously read genome.get("ishod")/genome.get(
"preporucena_akcija"), neither of which exists in the Case Genome schema
(routers/case_dna.py:39-115), so the "lose" signal could never fire.

This test proves the fix: outcome now comes from predmet_hronologija's real
"Predmet zatvoren — Ishod: <label>" entries (same data routers/predmeti_close.py
writes and routers/predmeti_close.py::get_predmet_ishod reads), and any
leftover genome ishod/preporucena_akcija fields are ignored entirely.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_chain(data):
    chain = MagicMock()
    for attr in ["select", "eq", "update", "insert", "upsert", "order", "limit",
                 "is_", "in_", "lt", "single", "maybe_single", "ilike", "gte", "lte"]:
        setattr(chain, attr, MagicMock(return_value=chain))
    chain.execute = MagicMock(return_value=MagicMock(data=data))
    return chain


@pytest.mark.anyio
async def test_weak_signals_uses_hronologija_ishod_not_genome_fields():
    from routers import health_index as hi

    # 8 closed "radni_spor" predmeti. Each carries a stale/bogus genome
    # "ishod"/"preporucena_akcija" field on purpose -- the fix must ignore
    # these completely, not just fail to crash on them.
    closed = [
        {"id": f"p{i}", "tip": "radni_spor", "oblast": "radno",
         "status": "zatvoren", "created_at": "2026-01-01",
         "case_dna": {"ishod": "totally-fake-value", "preporucena_akcija": "also-fake"}}
        for i in range(8)
    ]

    # Real outcomes, as routers/predmeti_close.py actually writes them:
    # 5 losses (poraz/odbacena), 3 wins -- >=60% loss rate should trigger the signal.
    hron_rows = []
    for i in range(5):
        hron_rows.append({"predmet_id": f"p{i}", "dogadjaj": "Predmet zatvoren — Ishod: Poraz", "datum": "2026-06-01"})
    for i in range(5, 7):
        hron_rows.append({"predmet_id": f"p{i}", "dogadjaj": "Predmet zatvoren — Ishod: Tužba odbačena", "datum": "2026-06-01"})
    hron_rows.append({"predmet_id": "p7", "dogadjaj": "Predmet zatvoren — Ishod: Pobeda", "datum": "2026-06-01"})

    predmeti_chain = _make_chain(closed)
    hron_chain = _make_chain(hron_rows)

    supa = MagicMock()
    def _table(name):
        if name == "predmeti":
            return predmeti_chain
        if name == "predmet_hronologija":
            return hron_chain
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    signals = await hi._compute_weak_signals("user-1", supa)

    # The real hronologija data shows 7/8 unfavorable (poraz + odbacena) --
    # well above the 60% threshold -- so the "loš ishod" signal must fire.
    assert any("nepovoljan" in s["tekst"] for s in signals), signals
    tekst = next(s["tekst"] for s in signals if "nepovoljan" in s["tekst"])
    assert "7 od 8" in tekst
    # The bogus genome fields must never leak into the signal text.
    assert "totally-fake-value" not in tekst
    assert "also-fake" not in tekst


@pytest.mark.anyio
async def test_weak_signals_ignores_neutral_outcomes():
    """Nagodba/odustajanje are NOT counted as 'lose' -- they can be a good
    strategic outcome, not a failure. Only poraz/odbacena count."""
    from routers import health_index as hi

    closed = [
        {"id": f"p{i}", "tip": "ugovorni_spor", "oblast": "privredno",
         "status": "zatvoren", "created_at": "2026-01-01", "case_dna": None}
        for i in range(8)
    ]
    hron_rows = [
        {"predmet_id": f"p{i}", "dogadjaj": "Predmet zatvoren — Ishod: Nagodba / Poravnanje", "datum": "2026-06-01"}
        for i in range(8)
    ]

    predmeti_chain = _make_chain(closed)
    hron_chain = _make_chain(hron_rows)
    supa = MagicMock()
    def _table(name):
        if name == "predmeti":
            return predmeti_chain
        if name == "predmet_hronologija":
            return hron_chain
        return _make_chain([])
    supa.table = MagicMock(side_effect=_table)

    signals = await hi._compute_weak_signals("user-1", supa)

    assert not any("nepovoljan" in s["tekst"] for s in signals), signals

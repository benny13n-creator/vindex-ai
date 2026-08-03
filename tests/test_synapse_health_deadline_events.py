# -*- coding: utf-8 -*-
"""
Project Synapse (2026-08-03): a full emit/consume audit of services/event_bus.py
found two fully-wired, working proactive-alert handlers (HEALTH_SCORE_PROMENJEN,
ROK_KRITICAN) that were never triggered by anything in the repository --
routers/matter_intel.py::get_matter_intel already computes exactly the signal
each one needs, on every case-open, but never emitted these events.

Two changes tested here:
1. services/risk_engine.py::calculate_procesni_rizik now also returns
   "kriticni_rocista" (the actual critical-hearing rows, not just a count) --
   purely additive, so the emit site doesn't have to re-derive the same
   0<=days<=7 date math a second time.
2. routers/matter_intel.py::_maybe_emit_health_and_deadline_events emits both
   events when warranted, with MANDATORY dedup against an existing unread
   alert of the same type -- this function runs on every case-open
   (matter_intel_load() auto-fires on every pred_select()), so emitting
   unconditionally would spam a new duplicate alert on every page view.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.risk_engine import calculate_procesni_rizik


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# calculate_procesni_rizik — kriticni_rocista addition
# ═══════════════════════════════════════════════════════════════════════════

def _iso_in(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


def test_kriticni_rocista_contains_the_actual_rows_within_7_days():
    rocista = [
        {"sud": "Osnovni sud u Beogradu", "datum": _iso_in(3), "status": "zakazano"},
        {"sud": "Apelacioni sud", "datum": _iso_in(20), "status": "zakazano"},
    ]
    r = calculate_procesni_rizik(dokazi=[], dokumenti=[], rocista=rocista, tip_predmeta="ostalo", expected_docs={"ostalo": []})
    assert r["kriticni_rokovi"] == 1
    assert len(r["kriticni_rocista"]) == 1
    assert r["kriticni_rocista"][0]["sud"] == "Osnovni sud u Beogradu"


def test_kriticni_rocista_empty_when_no_hearing_within_7_days():
    rocista = [{"sud": "Apelacioni sud", "datum": _iso_in(20), "status": "zakazano"}]
    r = calculate_procesni_rizik(dokazi=[], dokumenti=[], rocista=rocista, tip_predmeta="ostalo", expected_docs={"ostalo": []})
    assert r["kriticni_rokovi"] == 0
    assert r["kriticni_rocista"] == []


def test_kriticni_rocista_count_matches_list_length_multiple_critical():
    rocista = [
        {"sud": "Sud A", "datum": _iso_in(1), "status": "zakazano"},
        {"sud": "Sud B", "datum": _iso_in(5), "status": "zakazano"},
    ]
    r = calculate_procesni_rizik(dokazi=[], dokumenti=[], rocista=rocista, tip_predmeta="ostalo", expected_docs={"ostalo": []})
    assert r["kriticni_rokovi"] == 2
    assert len(r["kriticni_rocista"]) == 2


# ═══════════════════════════════════════════════════════════════════════════
# _maybe_emit_health_and_deadline_events
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_emits_health_score_event_when_low_and_no_existing_alert():
    from routers.matter_intel import _maybe_emit_health_and_deadline_events

    supa = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute.return_value = MagicMock(data=[])  # no existing unread alert
    supa.table.return_value = chain

    with patch("services.event_bus.emit") as mock_emit:
        await _maybe_emit_health_and_deadline_events(supa, "uid-1", "pred-1", 20, [])

    mock_emit.assert_called_once()
    args = mock_emit.call_args[0]
    from services.event_bus import EventType
    assert args[0] == EventType.HEALTH_SCORE_PROMENJEN
    assert args[1] == "uid-1"
    assert args[2] == "pred-1"
    assert args[3] == {"health_score": 20}


@pytest.mark.anyio
async def test_does_not_emit_health_score_event_when_score_is_healthy():
    from routers.matter_intel import _maybe_emit_health_and_deadline_events

    supa = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute.return_value = MagicMock(data=[])
    supa.table.return_value = chain

    with patch("services.event_bus.emit") as mock_emit:
        await _maybe_emit_health_and_deadline_events(supa, "uid-1", "pred-1", 75, [])

    mock_emit.assert_not_called()


@pytest.mark.anyio
async def test_does_not_emit_health_score_event_when_unread_alert_already_exists():
    """The core regression guard: this function runs on EVERY case-open --
    without this dedup check, a lawyer would get a duplicate alert every
    single page view for as long as the health score stays low."""
    from routers.matter_intel import _maybe_emit_health_and_deadline_events

    supa = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute.return_value = MagicMock(data=[{"id": "existing-alert-1"}])  # already exists
    supa.table.return_value = chain

    with patch("services.event_bus.emit") as mock_emit:
        await _maybe_emit_health_and_deadline_events(supa, "uid-1", "pred-1", 10, [])

    mock_emit.assert_not_called()


@pytest.mark.anyio
async def test_emits_rok_kritican_event_with_correct_payload():
    from routers.matter_intel import _maybe_emit_health_and_deadline_events

    supa = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute.return_value = MagicMock(data=[])
    supa.table.return_value = chain

    kriticni_rocista = [{"sud": "Privredni sud u Novom Sadu", "datum": "2026-08-10", "status": "zakazano"}]

    with patch("services.event_bus.emit") as mock_emit:
        await _maybe_emit_health_and_deadline_events(supa, "uid-1", "pred-1", 80, kriticni_rocista)

    mock_emit.assert_called_once()
    from services.event_bus import EventType
    args = mock_emit.call_args[0]
    assert args[0] == EventType.ROK_KRITICAN
    assert args[3]["datum"] == "2026-08-10"
    assert "Privredni sud u Novom Sadu" in args[3]["naziv"]


@pytest.mark.anyio
async def test_does_not_emit_rok_kritican_when_no_critical_hearings():
    from routers.matter_intel import _maybe_emit_health_and_deadline_events

    supa = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute.return_value = MagicMock(data=[])
    supa.table.return_value = chain

    with patch("services.event_bus.emit") as mock_emit:
        await _maybe_emit_health_and_deadline_events(supa, "uid-1", "pred-1", 80, [])

    mock_emit.assert_not_called()


@pytest.mark.anyio
async def test_emit_failure_does_not_raise():
    """Fire-and-forget discipline matching every other background task this
    engagement has built -- a failure here must never propagate."""
    from routers.matter_intel import _maybe_emit_health_and_deadline_events

    supa = MagicMock()
    supa.table.side_effect = RuntimeError("db unreachable")

    # Must not raise.
    await _maybe_emit_health_and_deadline_events(supa, "uid-1", "pred-1", 10, [{"sud": "X", "datum": "2026-08-05"}])

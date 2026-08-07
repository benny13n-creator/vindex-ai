# -*- coding: utf-8 -*-
"""
Program Phoenix, Mission 007 -- Case Evolution Consequence Chain Integrity.
Closes LIVINGSYS-DEBT-011 (timeline_entry idempotency, partial), LIVINGSYS-DEBT-016 (fully).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-011 (partial) — timeline_entry lacked an inner idempotency
# guard; a crash-then-reclaim within the stale-pending window produced a
# duplicate, user-visible Timeline row.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_timeline_entry_skips_duplicate_insert_on_reclaim():
    from services.event_bus import Event, EventType
    from services.case_evolution import _consequence_timeline_entry

    existing_row = {"id": "hron-1"}
    insert_calls = []

    def _table(name):
        t = MagicMock()
        if name == "predmet_hronologija":
            t.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = [existing_row]
            def _insert(row):
                insert_calls.append(row)
                m = MagicMock(); m.execute.return_value = MagicMock(data=[{"id": "hron-NEW"}])
                return m
            t.insert.side_effect = _insert
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    event = Event(type=EventType.DOCUMENT_ACCEPTED, user_id="u1", predmet_id="pred-1",
                  payload={"dokumenti": ["dok.pdf"]}, event_id="evt-1")

    with patch("services.case_evolution._get_supa", return_value=supa):
        result = await _consequence_timeline_entry(event)

    assert insert_calls == []  # no duplicate row created
    assert result == "hron-1"  # returns the existing row's id


@pytest.mark.anyio
async def test_timeline_entry_creates_row_when_no_recent_duplicate():
    from services.event_bus import Event, EventType
    from services.case_evolution import _consequence_timeline_entry

    def _table(name):
        t = MagicMock()
        if name == "predmet_hronologija":
            t.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = []
            t.insert.return_value.execute.return_value.data = [{"id": "hron-new"}]
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    event = Event(type=EventType.DOCUMENT_ACCEPTED, user_id="u1", predmet_id="pred-1",
                  payload={"dokumenti": ["dok.pdf"]}, event_id="evt-1")

    with patch("services.case_evolution._get_supa", return_value=supa):
        result = await _consequence_timeline_entry(event)

    assert result == "hron-new"


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-016 — NEW_EVIDENCE_REGISTERED never triggered
# refresh_case_actions, so case_actions/readiness could lag live risk.
# ═══════════════════════════════════════════════════════════════════════════

def test_new_evidence_registered_now_includes_refresh_case_actions():
    from services.case_evolution import CONSEQUENCE_REGISTRY
    from services.event_bus import EventType

    names = [c.name for c in CONSEQUENCE_REGISTRY[EventType.NEW_EVIDENCE_REGISTERED]]
    assert "evidence_classification" in names
    assert "refresh_case_actions" in names

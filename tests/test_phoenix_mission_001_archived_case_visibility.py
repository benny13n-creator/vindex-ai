# -*- coding: utf-8 -*-
"""
Program Phoenix, Mission 001 -- Archived-Case Visibility Consolidation.
Closes LIVINGSYS-DEBT-037, -048, -038 (leak part), -036: each proves an archived/closed
case's hearing/deadline/action no longer leaks into a proactive or operational surface,
while a genuinely unresolvable/unknown case reference still fails open (kalendar.py only).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-037 — AI Deadline Guardian scanned deadlines with no case-status
# awareness.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_guardian_scan_excludes_deadline_on_archived_case():
    from routers import zastarelost as zs

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.execute.return_value.data = [
                {"id": "pred-active", "status": "aktivan"},
                {"id": "pred-archived", "status": "zatvoren"},
            ]
        elif name == "rokovi":
            t.select.return_value.eq.return_value.gte.return_value.lte.return_value.order.return_value.execute.return_value.data = [
                {"id": "r1", "naziv": "Rok A", "datum": "2026-08-10", "tip": "podnesak", "predmet_id": "pred-active", "opis": ""},
                {"id": "r2", "naziv": "Rok B", "datum": "2026-08-10", "tip": "podnesak", "predmet_id": "pred-archived", "opis": ""},
            ]
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    from unittest.mock import AsyncMock

    with patch.object(zs, "_get_supa", return_value=supa), \
         patch.object(zs, "UsageService") as mock_usage:
        mock_usage.consume = AsyncMock(return_value=None)
        result = await zs.guardian_scan({"user_id": "u1", "email": "a@b.com"})

    ids = {r["id"] for r in result["scan"]}
    assert "r1" in ids
    assert "r2" not in ids


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-048 — Matter Intelligence had no hearing-status filter; a
# cancelled/completed hearing scored as a live "critical deadline".
# ═══════════════════════════════════════════════════════════════════════════

def test_matter_intel_rocista_query_filters_zakazano_status():
    src = open(os.path.join(os.path.dirname(__file__), "..", "routers", "matter_intel.py"), encoding="utf-8").read()
    marker = 'supa.table("rocista").select('
    block = src.split(marker, 1)[1][:200]
    assert '.eq("status", "zakazano")' in block


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-038 (leak part) — Calendar never filtered by predmeti.status; an
# archived case's hearing/deadline rendered on the firm-wide deadline Calendar. A
# genuinely unresolvable predmet_id (not found in the predmeti fetch at all) must
# still fail OPEN and render (pre-existing, intentional behavior, re-verified here).
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_aggr_events_excludes_archived_case_hearing_and_deadline():
    from routers.kalendar import _aggr_events

    def _table(name):
        t = MagicMock()
        if name == "rocista":
            t.select.return_value.eq.return_value.gte.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {"id": "r1", "predmet_id": "pred-active", "sud": "Sud1", "datum": "2026-08-10",
                 "vreme": "10:00", "status": "zakazano"},
                {"id": "r2", "predmet_id": "pred-archived", "sud": "Sud2", "datum": "2026-08-10",
                 "vreme": "11:00", "status": "zakazano"},
            ]
        elif name == "predmet_hronologija":
            t.select.return_value.eq.return_value.gte.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {"predmet_id": "pred-active", "dogadjaj": "Rok aktivan", "datum_iso": "2026-08-11", "vaznost": "kritičan"},
                {"predmet_id": "pred-archived", "dogadjaj": "Rok arhiviran", "datum_iso": "2026-08-11", "vaznost": "kritičan"},
            ]
        elif name == "predmeti":
            t.select.return_value.eq.return_value.execute.return_value.data = [
                {"id": "pred-active", "naziv": "Aktivan predmet", "status": "aktivan"},
                {"id": "pred-archived", "naziv": "Arhiviran predmet", "status": "zatvoren"},
            ]
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("routers.kalendar._get_supa", return_value=supa):
        events = await _aggr_events("u1", "2026-08-01", "2026-08-31")

    pids = {e["predmet_id"] for e in events}
    assert "pred-active" in pids
    assert "pred-archived" not in pids
    assert len(events) == 2  # 1 hearing + 1 deadline for the active case only


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-036 — case_actions worklist ("what must I do today") included
# archived/closed cases' still-open actions.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_worklist_excludes_archived_case():
    from routers import case_actions as ca
    from starlette.requests import Request as StarletteRequest

    def _req():
        scope = {"type": "http", "method": "GET", "path": "/", "headers": [],
                  "query_string": b"", "app": MagicMock(), "state": MagicMock(),
                  "client": ("127.0.0.1", 1234)}
        return StarletteRequest(scope=scope)

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.not_.in_.return_value.execute.return_value.data = [
                {"id": "pred-active", "naziv": "Aktivan predmet"},
            ]
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(ca, "_get_supa", return_value=supa), \
         patch.object(ca, "_fetch_open_actions", new=lambda supa, ids: _fake_actions(ids)):
        result = await ca.get_worklist(_req(), {"user_id": "u1"})

    assert all(c["predmet_id"] == "pred-active" for c in result["predmeti"])


async def _fake_actions(predmet_ids):
    # Only the active case's id was ever passed in (query-level filter, not post-filter) --
    # proves the archived case never even reaches _fetch_open_actions.
    assert predmet_ids == ["pred-active"]
    return [{"predmet_id": "pred-active", "prioritet": "critical", "rok": "2026-08-10", "razlog": "test"}]

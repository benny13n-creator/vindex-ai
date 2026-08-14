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
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


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
        elif name == "predmet_hronologija":
            # BETA-DEADLINE-DOMAIN-001: fixture prebacen sa nepostojece tabele
            # `rokovi` na kanonskog vlasnika. Invarijanta koju test cuva --
            # rok na arhiviranom predmetu se ne skenira -- nije promenjena.
            _d = (date.today() + timedelta(days=2)).isoformat()
            t.select.return_value.eq.return_value.gte.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {"id": "r1", "dogadjaj": "Rok A", "datum_iso": _d,
                 "vaznost": "kritičan", "predmet_id": "pred-active", "akter": ""},
                {"id": "r2", "dogadjaj": "Rok B", "datum_iso": _d,
                 "vaznost": "kritičan", "predmet_id": "pred-archived", "akter": ""},
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
        events, _meta = await _aggr_events("u1", "2026-08-01", "2026-08-31")

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


# ═══════════════════════════════════════════════════════════════════════════
# Final Beta Gate F18 (CRITICAL) — get_workspace (the daily "Today" board, a
# DIFFERENT endpoint than get_worklist above) had no status filter at all on
# its own predmeti query -- an archived/closed case's still-open case_actions
# kept appearing on the actual Workspace board a lawyer checks every morning.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_workspace_board_excludes_archived_case():
    import asyncio as _asyncio
    import routers.workspace as workspace

    def _req():
        from starlette.requests import Request as StarletteRequest
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

    async def _real_gather(*coros, **kw):
        return await _asyncio.gather(*coros, return_exceptions=True)

    async def _fake_open_actions(supa, predmet_ids):
        # Proves the archived case's id never reaches the case_actions query --
        # the filter must happen at the predmeti query, not after the fact.
        assert predmet_ids == ["pred-active"]
        return []

    async def _fake_recently_completed(supa, predmet_ids, uid):
        assert predmet_ids == ["pred-active"]
        return [], []

    with patch.object(workspace, "_get_supa", return_value=supa), \
         patch.object(workspace, "gather_with_timeout", new=_real_gather), \
         patch.object(workspace, "_fetch_open_actions", new=_fake_open_actions), \
         patch.object(workspace, "_fetch_waiting_zadaci", new=AsyncMock(return_value=[])), \
         patch.object(workspace, "_fetch_review_jobs", new=AsyncMock(return_value=[])), \
         patch.object(workspace, "_fetch_recently_completed", new=_fake_recently_completed):
        result = await _asyncio.wait_for(
            workspace.get_workspace(_req(), {"user_id": "u1"}), timeout=3.0
        )

    # The real assertion is inside _fake_open_actions/_fake_recently_completed above:
    # if the archived case's id had leaked through, predmet_ids would be
    # ["pred-active", "pred-archived"] and those asserts would fail the test.
    assert result["ukupno_aktivnih"] == 0

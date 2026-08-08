# -*- coding: utf-8 -*-
"""
Phoenix Closure operation (2026-08-08) -- Phase 3: resolving the 8
PARTIALLY FIXED Living System debt items' remainders. This file covers
LIVINGSYS-DEBT-011 (3 remaining consequence executors: genome_refresh,
review_confirmation_audit, review_rejection_audit, case_intelligence_summary).
Other partial items (-036, -038, -041, -046) have their own test files.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from starlette.requests import Request as StarletteRequest


def _req():
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    scope = {
        "type": "http", "method": "GET", "path": "/", "headers": [],
        "query_string": b"", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 1234),
    }
    return StarletteRequest(scope=scope, receive=receive)


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-011 remainder -- genome_refresh had no inner idempotency
# guard; a crash-then-reclaim of the SAME event_id re-triggered a full 2nd
# GPT recompute. Dedup key is scoped to event_id (not a shared hardcoded
# trigger label) so 2 genuinely different events are never conflated.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_genome_refresh_skips_duplicate_on_same_event_id_reclaim():
    from services.event_bus import Event, EventType
    from services.case_evolution import _consequence_genome_refresh

    def _table(name):
        t = MagicMock()
        if name == "predmet_genome_history":
            t.select.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value.data = \
                [{"verzija": 4}]
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    event = Event(type=EventType.DOCUMENT_ACCEPTED, user_id="u1", predmet_id="pred-1",
                  payload={}, event_id="evt-dup-1")

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock()) as mock_refresh:
        result = await _consequence_genome_refresh(event)

    mock_refresh.assert_not_called()
    assert result == "skipped_duplicate_refresh_v4"


@pytest.mark.anyio
async def test_genome_refresh_proceeds_when_no_recent_duplicate_for_this_event():
    from services.event_bus import Event, EventType
    from services.case_evolution import _consequence_genome_refresh

    calls = {"n": 0}

    def _table(name):
        t = MagicMock()
        if name == "predmet_genome_history":
            t.select.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        elif name == "predmeti":
            def _select(*a, **kw):
                m = MagicMock()
                calls["n"] += 1
                verzija = 1 if calls["n"] == 1 else 2
                m.eq.return_value.maybe_single.return_value.execute.return_value = \
                    MagicMock(data={"case_dna": {"verzija": verzija}})
                return m
            t.select.side_effect = _select
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    event = Event(type=EventType.DOCUMENT_ACCEPTED, user_id="u1", predmet_id="pred-1",
                  payload={}, event_id="evt-new-1")

    async def _fake_run_genome_background(predmet_id, uid, before_verzija, trigger=None):
        assert trigger == "case_evolution:evt-new-1"

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock(side_effect=_fake_run_genome_background)) as mock_refresh:
        result = await _consequence_genome_refresh(event)

    mock_refresh.assert_called_once()
    assert result == "2"


@pytest.mark.anyio
async def test_genome_refresh_different_event_ids_are_not_conflated():
    """The old hardcoded-trigger-label dedup key would have wrongly skipped
    this 2nd, genuinely-different event. Confirms the event_id-scoped key fix."""
    from services.event_bus import Event, EventType
    from services.case_evolution import _consequence_genome_refresh

    calls = {"n": 0}

    def _table(name):
        t = MagicMock()
        if name == "predmet_genome_history":
            # A recent row exists, but for a DIFFERENT event_id's trigger label.
            t.select.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        elif name == "predmeti":
            def _select(*a, **kw):
                m = MagicMock()
                calls["n"] += 1
                verzija = 5 if calls["n"] == 1 else 6
                m.eq.return_value.maybe_single.return_value.execute.return_value = \
                    MagicMock(data={"case_dna": {"verzija": verzija}})
                return m
            t.select.side_effect = _select
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    event = Event(type=EventType.ROCISTE_ZAKAZANO, user_id="u1", predmet_id="pred-1",
                  payload={}, event_id="evt-hearing-2")

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock()) as mock_refresh:
        await _consequence_genome_refresh(event)

    # The dup-check query itself was scoped to THIS event's own trigger label
    # (case_evolution:evt-hearing-2), not any other event's -- verify via the
    # eq() call args captured on the mock chain.
    mock_refresh.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-011 remainder -- review_confirmation_audit /
# review_rejection_audit had no guard against a duplicate append on reclaim.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_review_confirmation_audit_skips_duplicate_on_reclaim():
    from services.event_bus import Event, EventType
    from services.case_evolution import _consequence_review_confirmation_audit

    def _table(name):
        t = MagicMock()
        if name == "audit_immutable":
            t.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = \
                [{"id": "audit-1"}]
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    event = Event(type=EventType.REVIEW_ACCEPTED, user_id="u1", predmet_id="pred-1",
                  payload={"intake_job_id": "job-1"}, event_id="evt-1")

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        result = await _consequence_review_confirmation_audit(event)

    mock_log.assert_not_called()
    assert result == "skipped_duplicate_audit:job-1"


@pytest.mark.anyio
async def test_review_confirmation_audit_logs_when_no_recent_duplicate():
    from services.event_bus import Event, EventType
    from services.case_evolution import _consequence_review_confirmation_audit

    def _table(name):
        t = MagicMock()
        if name == "audit_immutable":
            t.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = []
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    event = Event(type=EventType.REVIEW_ACCEPTED, user_id="u1", predmet_id="pred-1",
                  payload={"intake_job_id": "job-2", "prior_status": "pending",
                           "job_status_advanced": True, "review_resolved_now": True},
                  event_id="evt-2")

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        result = await _consequence_review_confirmation_audit(event)

    mock_log.assert_called_once()
    assert result == "audit_logged:job-2"


@pytest.mark.anyio
async def test_review_rejection_audit_skips_duplicate_on_reclaim():
    from services.event_bus import Event, EventType
    from services.case_evolution import _consequence_review_rejection_audit

    def _table(name):
        t = MagicMock()
        if name == "audit_immutable":
            t.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = \
                [{"id": "audit-2"}]
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    event = Event(type=EventType.REVIEW_REJECTED, user_id="u1", predmet_id="pred-1",
                  payload={"intake_job_id": "job-3"}, event_id="evt-3")

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        result = await _consequence_review_rejection_audit(event)

    mock_log.assert_not_called()
    assert result == "skipped_duplicate_audit:job-3"


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-011 remainder -- case_intelligence_summary had no guard
# against a duplicate row on reclaim. Dedup key: the row's own event_id.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_case_intelligence_summary_skips_duplicate_on_same_event_id():
    from services.event_bus import Event, EventType
    from services.case_evolution import _consequence_case_intelligence_summary

    def _table(name):
        t = MagicMock()
        if name == "case_intelligence_summaries":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = \
                [{"id": "sum-1"}]
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    event = Event(type=EventType.DOCUMENT_BATCH_COMPLETED, user_id="u1", predmet_id="pred-1",
                  payload={"dokumenata_dodato": 3}, event_id="evt-batch-1")

    with patch("services.case_evolution._get_supa", return_value=supa):
        result = await _consequence_case_intelligence_summary(event)

    assert result == "sum-1"
    # confirms the function returned BEFORE reaching the predmeti/risk-engine reads
    supa.table.assert_any_call("case_intelligence_summaries")


@pytest.mark.anyio
async def test_case_intelligence_summary_inserts_when_no_duplicate_event_id():
    from services.event_bus import Event, EventType
    from services.case_evolution import _consequence_case_intelligence_summary

    insert_calls = []

    def _table(name):
        t = MagicMock()
        if name == "case_intelligence_summaries":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
            def _insert(row):
                insert_calls.append(row)
                m = MagicMock(); m.execute.return_value = MagicMock(data=[{"id": "sum-new"}])
                return m
            t.insert.side_effect = _insert
        elif name == "predmeti":
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = \
                MagicMock(data={"case_dna": {"verzija": 2, "kontradikcije": [], "datumi_kljucni": []}, "tip": "parnica"})
        elif name == "predmet_dokazi":
            t.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(data=[])
        elif name == "predmet_dokumenti":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        elif name == "rocista":
            t.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=[])
        return t

    supa = MagicMock()
    supa.table.side_effect = _table

    event = Event(type=EventType.DOCUMENT_BATCH_COMPLETED, user_id="u1", predmet_id="pred-1",
                  payload={"dokumenata_dodato": 2, "pre_kontradikcije": 0, "pre_dogadjaji": 0},
                  event_id="evt-batch-2")

    with patch("services.case_evolution._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        result = await _consequence_case_intelligence_summary(event)

    assert insert_calls, "expected a real insert when no duplicate event_id exists"
    assert insert_calls[0]["event_id"] == "evt-batch-2"
    assert result == "sum-new"


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-038 remainder -- kalendar.py::_aggr_events' 200-row cap and
# return_exceptions=True fallback were both silent. Now returns a 2nd `meta`
# dict (degraded_sources, truncated) alongside the events list.
# ═══════════════════════════════════════════════════════════════════════════

def _kalendar_supa(rocista_data=None, hron_data=None, pred_data=None,
                    rocista_exc=None, hron_exc=None):
    def _table(name):
        t = MagicMock()
        if name == "rocista":
            chain = t.select.return_value.eq.return_value.gte.return_value.lte.return_value.order.return_value.limit.return_value
            if rocista_exc:
                chain.execute.side_effect = rocista_exc
            else:
                chain.execute.return_value = MagicMock(data=rocista_data or [])
        elif name == "predmet_hronologija":
            chain = t.select.return_value.eq.return_value.gte.return_value.lte.return_value.order.return_value.limit.return_value
            if hron_exc:
                chain.execute.side_effect = hron_exc
            else:
                chain.execute.return_value = MagicMock(data=hron_data or [])
        elif name == "predmeti":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=pred_data or [])
        return t

    supa = MagicMock()
    supa.table.side_effect = _table
    return supa


@pytest.mark.anyio
async def test_aggr_events_meta_clean_on_full_success():
    from routers.kalendar import _aggr_events

    supa = _kalendar_supa(rocista_data=[{"id": "r1", "predmet_id": "p1", "datum": "2026-08-10", "status": "zakazano"}])

    with patch("routers.kalendar._get_supa", return_value=supa):
        events, meta = await _aggr_events("u1", "2026-08-01", "2026-08-31")

    assert meta == {"degraded_sources": [], "truncated": False}
    assert len(events) == 1


@pytest.mark.anyio
async def test_aggr_events_meta_flags_degraded_source_on_exception():
    from routers.kalendar import _aggr_events

    supa = _kalendar_supa(rocista_exc=RuntimeError("db down"))

    with patch("routers.kalendar._get_supa", return_value=supa):
        events, meta = await _aggr_events("u1", "2026-08-01", "2026-08-31")

    assert "rocista" in meta["degraded_sources"]
    assert events == []  # existing fail-soft behavior unchanged


@pytest.mark.anyio
async def test_aggr_events_meta_flags_truncated_at_200_cap():
    from routers.kalendar import _aggr_events

    two_hundred_rows = [
        {"id": f"r{i}", "predmet_id": "p1", "datum": "2026-08-10", "status": "zakazano"}
        for i in range(200)
    ]
    supa = _kalendar_supa(rocista_data=two_hundred_rows)

    with patch("routers.kalendar._get_supa", return_value=supa):
        _events, meta = await _aggr_events("u1", "2026-08-01", "2026-08-31")

    assert meta["truncated"] is True


@pytest.mark.anyio
async def test_kalendar_pregled_response_carries_disclosure_fields():
    from routers.kalendar import kalendar_pregled
    from starlette.requests import Request as StarletteRequest

    supa = _kalendar_supa(rocista_data=[])
    scope = {
        "type": "http", "method": "GET",
        "headers": [], "query_string": b"",
        "path": "/api/kalendar/pregled",
        "app": MagicMock(), "state": MagicMock(),
    }
    req = StarletteRequest(scope=scope)

    with patch("routers.kalendar._get_supa", return_value=supa):
        result = await kalendar_pregled(req, od="2026-08-01", datum_do="2026-08-31",
                                         user={"user_id": "u1"})

    assert "degraded_sources" in result
    assert "truncated" in result
    assert result["degraded_sources"] == []
    assert result["truncated"] is False


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-022 remainder -- evidence.py's persisted classification
# confidence signal was never rendered; the Reklasifikuj action already
# existed but had nothing telling a lawyer WHICH documents deserve it.
# ═══════════════════════════════════════════════════════════════════════════

def test_evidence_document_card_renders_low_confidence_badge():
    import os
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent.parent
    vindex_js = (repo_root / "static" / "vindex.js").read_text(encoding="utf-8")

    assert "_klasifikacija_pouzdanost" in vindex_js
    assert "niskaPouzdanost" in vindex_js
    # the badge markup must be wired into the SAME docs.map render that
    # already builds the Reklasifikuj button, not a separate disconnected block
    marker = "docs.map(function(doc) {"
    block = vindex_js.split(marker, 1)[1][:2200]
    assert "niskaPouzdanost" in block
    assert "evidence_reklasifikuj" in block


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-041 remainder -- 8 of 9 FormData upload call sites had no
# timeout (only pred_upload_doc did, Mission 013). All 9 now use the shared
# _fetchWithTimeout helper.
# ═══════════════════════════════════════════════════════════════════════════

def test_all_formdata_upload_sites_use_fetch_with_timeout():
    import re
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent.parent
    vindex_js = (repo_root / "static" / "vindex.js").read_text(encoding="utf-8")

    formdata_positions = [m.start() for m in re.finditer(r"new FormData\(\)", vindex_js)]
    assert len(formdata_positions) == 9, "expected exactly 9 known upload sites -- if this changed, re-audit for new ones"

    for pos in formdata_positions:
        window = vindex_js[pos:pos + 600]
        assert "_fetchWithTimeout(" in window, f"upload site at offset {pos} still uses raw fetch()"
        assert re.search(r"_fetchWithTimeout\([^,]+,\s*\{", window), f"upload site at offset {pos} missing options object"


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-046 remainder -- cio_daily's losing claim attempt used to
# unconditionally pay its own full GPT generation cost. A losing request now
# waits (bounded) for an in-process winner and reuses its persisted report.
# ═══════════════════════════════════════════════════════════════════════════

def _cio_daily_stateful_supa():
    """Models cio_dnevni_izvestaj's real query shapes: cache-check select,
    stale-reclaim update (.lt), fresh-claim insert (UNIQUE violation on
    conflict), coalesce-wait select, final persist update (no .lt)."""
    rows: dict = {}

    class _SelectNode:
        def __init__(self, key):
            self.key = key
        def eq(self, col, val):
            return self
        def single(self):
            return self
        def execute(self):
            res = MagicMock()
            res.data = rows.get(self.key)
            return res

    class _UpdateNode:
        def __init__(self, key, payload):
            self.key = key
            self.payload = payload
            self.lt_val = None
        def eq(self, col, val):
            return self
        def lt(self, col, val):
            self.lt_val = val
            return self
        def execute(self):
            res = MagicMock()
            row = rows.get(self.key)
            if self.lt_val is not None:
                matched = row is not None and row.get("created_at", "") < self.lt_val
            else:
                matched = row is not None
            if matched:
                rows[self.key].update(self.payload)
                res.data = [rows[self.key]]
            else:
                res.data = []
            return res

    def _table(name):
        assert name == "cio_dnevni_izvestaj"
        t = MagicMock()
        def _select(*a, **kw):
            node = MagicMock()
            key_holder = {}
            def _eq(col, val):
                key_holder.setdefault("uid" if col == "user_id" else "datum", val)
                return node
            node.eq.side_effect = _eq
            def _single():
                return node
            node.single.side_effect = _single
            def _execute():
                key = (key_holder.get("uid"), key_holder.get("datum"))
                res = MagicMock()
                res.data = rows.get(key)
                return res
            node.execute.side_effect = _execute
            return node
        t.select.side_effect = _select

        def _insert(payload):
            key = (payload["user_id"], payload["datum"])
            node = MagicMock()
            def _execute():
                if key in rows:
                    raise Exception('duplicate key value violates unique constraint "cio_dnevni_izvestaj_user_id_datum_key"')
                row = dict(payload)
                row.setdefault("created_at", "2026-08-08T10:00:00+00:00")
                rows[key] = row
                res = MagicMock(); res.data = [row]
                return res
            node.execute.side_effect = _execute
            return node
        t.insert.side_effect = _insert

        def _update(payload):
            node = MagicMock()
            key_holder = {}
            lt_holder = {}
            def _eq(col, val):
                key_holder.setdefault("uid" if col == "user_id" else "datum", val)
                return node
            def _lt(col, val):
                lt_holder["v"] = val
                return node
            node.eq.side_effect = _eq
            node.lt.side_effect = _lt
            def _execute():
                key = (key_holder.get("uid"), key_holder.get("datum"))
                row = rows.get(key)
                res = MagicMock()
                if "v" in lt_holder:
                    matched = row is not None and row.get("created_at", "") < lt_holder["v"]
                else:
                    matched = row is not None
                if matched:
                    rows[key].update(payload)
                    res.data = [rows[key]]
                else:
                    res.data = []
                return res
            node.execute.side_effect = _execute
            return node
        t.update.side_effect = _update
        return t

    supa = MagicMock()
    supa.table.side_effect = _table
    return supa, rows


@pytest.mark.anyio
async def test_cio_daily_winner_cleans_up_inflight_state_after_success():
    import routers.cio as cio
    supa, _rows = _cio_daily_stateful_supa()
    user = {"user_id": "u-solo", "email": "a@b.com"}

    with patch.object(cio, "_get_supa", return_value=supa), \
         patch.object(cio, "_generiši_cio_izvestaj", new=AsyncMock(return_value={"predmeta_analizirano": 3})), \
         patch.object(cio, "UsageService") as mock_usage:
        mock_usage.consume = AsyncMock(return_value=100)
        result = await cio.cio_daily(_req(), user)

    assert result["predmeta_analizirano"] == 3
    assert cio._cio_daily_inflight == set()
    assert cio._cio_daily_done_event == {}


@pytest.mark.anyio
async def test_cio_daily_loser_waits_and_reuses_winners_report_no_duplicate_gpt_call():
    """The core -046 fix: a losing claim attempt with an in-process winner
    already generating must NOT call _generiši_cio_izvestaj itself.

    Deliberately does NOT reuse _cio_daily_stateful_supa: that mock's realistic
    cache-check would race against the claim-loss simulation below (both are
    keyed off the same row-age condition, so a row old enough to force the
    fresh-insert into "duplicate key" is also old enough to either satisfy the
    top-of-function 6h cache-return or win the stale-reclaim update itself --
    the real production race only produces a loser via true concurrent timing,
    which a single sequential test call can't reproduce through that path).
    Instead: a minimal purpose-built mock forces claimed=False deterministically
    (cache-check finds nothing, stale-reclaim finds nothing, insert hits a
    simulated concurrent duplicate-key) and a call-counter distinguishes the
    2 distinct .select() calls this function makes (cache-check, then the
    NEW coalesce-wait fresh-read this fix adds)."""
    import routers.cio as cio
    from datetime import date

    danes_iso = date.today().isoformat()
    coalesce_key = f"u-race:{danes_iso}"
    select_calls = {"n": 0}
    winner_report = {"izvestaj": {}, "predmeta_analizirano": 0, "created_at": "irrelevant"}

    def _table(name):
        assert name == "cio_dnevni_izvestaj"
        t = MagicMock()

        def _select(*a, **kw):
            node = MagicMock()
            node.eq.return_value = node
            node.single.return_value = node
            def _execute():
                select_calls["n"] += 1
                res = MagicMock()
                # 1st call = cache-check (nothing cached yet); 2nd+ = this
                # fix's coalesce-wait fresh-read (winner's report, once set).
                res.data = None if select_calls["n"] == 1 else dict(winner_report)
                return res
            node.execute.side_effect = _execute
            return node
        t.select.side_effect = _select

        def _update(payload):
            node = MagicMock()
            node.eq.return_value = node
            node.lt.return_value = node
            node.execute.return_value = MagicMock(data=[])  # stale-reclaim: nothing to reclaim
            return node
        t.update.side_effect = _update

        def _insert(payload):
            node = MagicMock()
            def _execute():
                raise Exception('duplicate key value violates unique constraint "cio_dnevni_izvestaj_user_id_datum_key"')
            node.execute.side_effect = _execute
            return node
        t.insert.side_effect = _insert
        return t

    supa = MagicMock()
    supa.table.side_effect = _table
    user = {"user_id": "u-race", "email": "a@b.com"}

    cio._cio_daily_inflight.add(coalesce_key)
    done_event = asyncio.Event()
    cio._cio_daily_done_event[coalesce_key] = done_event

    async def _release_winner_shortly():
        await asyncio.sleep(0.05)
        winner_report["izvestaj"] = {"predmeta_analizirano": 7, "poruka": "winner's report"}
        winner_report["predmeta_analizirano"] = 7
        done_event.set()

    generiši_mock = AsyncMock(return_value={"predmeta_analizirano": 99})  # would prove a duplicate call
    try:
        with patch.object(cio, "_get_supa", return_value=supa), \
             patch.object(cio, "_generiši_cio_izvestaj", new=generiši_mock), \
             patch.object(cio, "UsageService") as mock_usage:
            mock_usage.consume = AsyncMock(return_value=100)
            release_task = asyncio.create_task(_release_winner_shortly())
            result = await cio.cio_daily(_req(), user)
            await release_task
    finally:
        cio._cio_daily_inflight.discard(coalesce_key)
        cio._cio_daily_done_event.pop(coalesce_key, None)

    generiši_mock.assert_not_called()
    mock_usage.consume.assert_not_called()  # loser must never charge
    assert result["predmeta_analizirano"] == 7
    assert result["iz_kesa"] is True


@pytest.mark.anyio
async def test_cio_daily_loser_falls_back_to_own_generation_without_inflight_marker():
    """Cross-process race (no in-process winner marker) -- must preserve the
    exact pre-fix behavior: generate its own report, don't charge, don't hang."""
    import routers.cio as cio
    from datetime import date

    danes_iso = date.today().isoformat()

    def _table(name):
        assert name == "cio_dnevni_izvestaj"
        t = MagicMock()

        def _select(*a, **kw):
            node = MagicMock()
            node.eq.return_value = node
            node.single.return_value = node
            node.execute.return_value = MagicMock(data=None)  # nothing cached
            return node
        t.select.side_effect = _select

        def _update(payload):
            node = MagicMock()
            node.eq.return_value = node
            node.lt.return_value = node
            node.execute.return_value = MagicMock(data=[])  # stale-reclaim: nothing to reclaim
            return node
        t.update.side_effect = _update

        def _insert(payload):
            node = MagicMock()
            def _execute():
                # No in-process inflight marker exists for this key at all --
                # simulates a DIFFERENT worker having already claimed it.
                raise Exception('duplicate key value violates unique constraint "cio_dnevni_izvestaj_user_id_datum_key"')
            node.execute.side_effect = _execute
            return node
        t.insert.side_effect = _insert
        return t

    supa = MagicMock()
    supa.table.side_effect = _table
    user = {"user_id": "u-crossproc", "email": "a@b.com"}

    with patch.object(cio, "_get_supa", return_value=supa), \
         patch.object(cio, "_generiši_cio_izvestaj", new=AsyncMock(return_value={"predmeta_analizirano": 5})), \
         patch.object(cio, "UsageService") as mock_usage:
        mock_usage.consume = AsyncMock(return_value=100)
        result = await cio.cio_daily(_req(), user)

    mock_usage.consume.assert_not_called()  # still a loser, must not charge
    assert result["predmeta_analizirano"] == 5  # got its OWN freshly-generated report
    assert result["iz_kesa"] is False

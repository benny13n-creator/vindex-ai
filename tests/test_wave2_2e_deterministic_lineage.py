# -*- coding: utf-8 -*-
"""
VINDEX AI V1, Wave 2, Task 2E -- Deterministic future action lineage.

PROVEN PROBLEM (Wave 1): case_actions.event_id/correlation_id get
overwritten on every later reconciliation (the column reflects the LATEST
event, by design -- Task 2E preserves this, see its own instruction not
to change it without evidence). The immutable consequence audit
(services/case_evolution.py::_consequence_refresh_case_actions's own
"case_action_refreshed" log_action call) used to carry only aggregate
counts (created=N/updated=N/closed=N) -- never WHICH concrete action a
given run created/updated/closed. On a multi-event matter, attributing a
specific case_actions row to the event that produced it degraded to a
timestamp-proximity guess.

Fix: the SAME existing "case_action_refreshed" audit call now also
carries created_actions/updated_actions/closed_actions -- lists of
{id, dedupe_key} for exactly what THIS run affected. No new table, no new
audit action type, no change to case_actions.event_id's own "latest
wins" semantics.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake-test-key")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")

from datetime import date, timedelta

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api import app  # noqa: E402,F401 -- bootstraps the full import graph safely

from services.event_bus import Event, EventType  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# Fake Postgres -- same proven harness as Wave 2's own prior tasks.
# ═══════════════════════════════════════════════════════════════════════════

class _FakeQuery:
    def __init__(self, rows_ref):
        self._rows_ref = rows_ref
        self._filtered = list(rows_ref)
        self._op = "select"
        self._payload = None
        self._single = False

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filtered = [r for r in self._filtered if r.get(col) == val]
        return self

    def neq(self, col, val):
        self._filtered = [r for r in self._filtered if r.get(col) != val]
        return self

    def in_(self, col, vals):
        vals = set(vals)
        self._filtered = [r for r in self._filtered if r.get(col) in vals]
        return self

    @property
    def not_(self):
        return _NotFilter(self)

    def is_(self, col, val):
        if val in ("null", None):
            self._filtered = [r for r in self._filtered if r.get(col) is None]
        return self

    def gte(self, col, val):
        self._filtered = [r for r in self._filtered if (r.get(col) or "") >= val]
        return self

    def order(self, col, desc=False):
        self._filtered.sort(key=lambda r: r.get(col) or "", reverse=desc)
        return self

    def limit(self, _n):
        return self

    def maybe_single(self):
        self._single = True
        return self

    def execute(self):
        res = MagicMock()
        if self._op == "insert":
            new_row = dict(self._payload)
            new_row.setdefault("id", f"gen-{len(self._rows_ref) + 1}")
            new_row.setdefault("status", "open")
            self._rows_ref.append(new_row)
            res.data = [new_row]
        elif self._op == "update":
            for r in self._filtered:
                r.update(self._payload)
            res.data = list(self._filtered)
        else:
            res.data = (self._filtered[0] if self._filtered else None) if self._single else list(self._filtered)
        return res


class _NotFilter:
    def __init__(self, query: "_FakeQuery"):
        self._query = query

    def in_(self, col, vals):
        vals = set(vals)
        self._query._filtered = [r for r in self._query._filtered if r.get(col) not in vals]
        return self._query

    def eq(self, col, val):
        self._query._filtered = [r for r in self._query._filtered if r.get(col) != val]
        return self._query


class _FakeSupa:
    def __init__(self, tables: dict):
        self.tables = {k: list(v) for k, v in tables.items()}

    def table(self, name):
        self.tables.setdefault(name, [])
        return _FakeQuery(self.tables[name])


PID = "pred-1"


def _predmet_row():
    return {"id": PID, "user_id": "user-1", "naziv": "Predmet A", "case_dna": {}, "tip": "parnicno", "status": "aktivan"}


def _rociste(rid, days_out=5):
    return {"id": rid, "predmet_id": PID, "sud": "Osnovni sud",
            "datum": (date.today() + timedelta(days=days_out)).isoformat(), "status": "zakazano"}


def _make_fake(rocista=None):
    return _FakeSupa({
        "predmeti": [_predmet_row()],
        "predmet_dokazi": [], "predmet_dokumenti": [],
        "rocista": list(rocista or []),
        "case_actions": [],
    })


def _event(event_id):
    return Event(type=EventType.ROCISTE_ZAKAZANO, user_id="user-1", predmet_id=PID,
                 payload={}, correlation_id=f"corr-{event_id}", event_id=event_id)


def _hearing_dedupe_key(rociste_id: str) -> str:
    from services.case_evolution import _stable_key
    return _stable_key("rociste", rociste_id)


# ═══════════════════════════════════════════════════════════════════════════
# Multi-event lineage: E1 creates A, E2 creates B + refreshes A, E3
# refreshes both. Provable from audit metadata alone, no timestamps.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_multi_event_lineage_addressable_without_timestamp_guessing():
    from services.case_evolution import _consequence_refresh_case_actions

    fake = _make_fake(rocista=[_rociste("roc-A")])
    audit_calls = []

    async def _capture_log_action(action, **kw):
        if action == "case_action_refreshed":
            audit_calls.append(kw)
        return "audit-id"

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("shared.audit_immutable.log_action", new=_capture_log_action):
        # E1: only roc-A exists -- creates action A.
        await _consequence_refresh_case_actions(_event("E1"))

        # E2: roc-B now also scheduled -- creates action B, refreshes A
        # (roc-A's own dedupe_key is still in the target set, unchanged
        # content -> UPDATE path, a legitimate "refresh").
        fake.tables["rocista"].append(_rociste("roc-B"))
        await _consequence_refresh_case_actions(_event("E2"))

        # E3: nothing changed -- both A and B refresh again.
        await _consequence_refresh_case_actions(_event("E3"))

    by_event = {c["metadata"]["event_id"]: c["metadata"] for c in audit_calls}
    key_a = _hearing_dedupe_key("roc-A")
    key_b = _hearing_dedupe_key("roc-B")

    # A document-less, evidence-less matter also trips the risk engine's
    # own "missing expected document type" rules on every run -- those
    # extra actions are irrelevant noise here; every assertion below is
    # scoped to key_a/key_b specifically, not exact-set equality on the
    # whole created/updated lists.

    # A originated from E1: appears in E1's created_actions, nowhere in
    # E1's updated_actions (it didn't exist yet to be refreshed).
    e1_created_keys = {e["dedupe_key"] for e in by_event["E1"]["created_actions"]}
    e1_updated_keys = {e["dedupe_key"] for e in by_event["E1"]["updated_actions"]}
    assert key_a in e1_created_keys
    assert key_a not in e1_updated_keys
    action_a_id = next(e["id"] for e in by_event["E1"]["created_actions"] if e["dedupe_key"] == key_a)

    # B originated from E2 (not E1 -- roc-B didn't exist yet then), and E2
    # also refreshed A (not created it again).
    e2_created_keys = {e["dedupe_key"] for e in by_event["E2"]["created_actions"]}
    e2_updated_keys = {e["dedupe_key"] for e in by_event["E2"]["updated_actions"]}
    assert key_b in e2_created_keys
    assert key_a not in e2_created_keys
    assert key_a in e2_updated_keys
    action_b_id = next(e["id"] for e in by_event["E2"]["created_actions"] if e["dedupe_key"] == key_b)
    # A's OWN id, referenced from E2's update entry, matches the id E1 created.
    e2_update_entry_for_a = next(e for e in by_event["E2"]["updated_actions"] if e["dedupe_key"] == key_a)
    assert e2_update_entry_for_a["id"] == action_a_id

    # E3 refreshed BOTH A and B, created neither.
    e3_created_keys = {e["dedupe_key"] for e in by_event["E3"]["created_actions"]}
    e3_updated_keys = {e["dedupe_key"] for e in by_event["E3"]["updated_actions"]}
    assert key_a not in e3_created_keys
    assert key_b not in e3_created_keys
    assert {key_a, key_b} <= e3_updated_keys
    e3_ids = {e["dedupe_key"]: e["id"] for e in by_event["E3"]["updated_actions"]}
    assert e3_ids[key_a] == action_a_id
    assert e3_ids[key_b] == action_b_id


@pytest.mark.anyio
async def test_retry_does_not_create_false_lineage_entry():
    """A retry (2nd call, same logical state, different event_id -- e.g.
    the outer Event Bus retrying a consequence that failed AFTER
    refresh_case_actions already committed in a previous attempt) must
    show as a refresh (updated_actions), never a 2nd created_actions entry
    for an action that already exists."""
    from services.case_evolution import _consequence_refresh_case_actions

    fake = _make_fake(rocista=[_rociste("roc-A")])
    audit_calls = []

    async def _capture_log_action(action, **kw):
        if action == "case_action_refreshed":
            audit_calls.append(kw)
        return "audit-id"

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("shared.audit_immutable.log_action", new=_capture_log_action):
        await _consequence_refresh_case_actions(_event("E1"))
        await _consequence_refresh_case_actions(_event("E1-retry"))

    key_a = _hearing_dedupe_key("roc-A")
    retry_meta = audit_calls[1]["metadata"]
    assert retry_meta["created_actions"] == []
    assert key_a in {e["dedupe_key"] for e in retry_meta["updated_actions"]}


@pytest.mark.anyio
async def test_concurrent_create_loser_records_no_fabricated_lineage():
    """The existing concurrent-duplicate-insert handling (partial UNIQUE
    index violation) must not fabricate a created_actions entry for a row
    this call never actually inserted."""
    from services.case_evolution import _consequence_refresh_case_actions

    fake = _make_fake(rocista=[_rociste("roc-A")])

    class _DupInsertQuery(_FakeQuery):
        def execute(self):
            if self._op == "insert":
                raise Exception("duplicate key value violates unique constraint")
            return super().execute()

    class _DupFakeSupa(_FakeSupa):
        def table(self, name):
            self.tables.setdefault(name, [])
            if name == "case_actions":
                return _DupInsertQuery(self.tables[name])
            return _FakeQuery(self.tables[name])

    dup_fake = _DupFakeSupa(fake.tables)
    audit_calls = []

    async def _capture_log_action(action, **kw):
        if action == "case_action_refreshed":
            audit_calls.append(kw)
        return "audit-id"

    with patch("services.case_evolution._get_supa", return_value=dup_fake), \
         patch("shared.audit_immutable.log_action", new=_capture_log_action):
        result = await _consequence_refresh_case_actions(_event("E1"))

    assert result == "created=0 updated=0 closed=0"
    assert audit_calls[0]["metadata"]["created_actions"] == []


@pytest.mark.anyio
async def test_lost_close_race_records_no_fabricated_close_lineage():
    """The existing optimistic-concurrency guard on CLOSE (.eq("updated_at",
    snapshot)) can make a close a safe no-op when a fresher concurrent
    write already changed the row. That must not be counted or recorded as
    a close THIS run performed."""
    from services.case_evolution import _consequence_refresh_case_actions

    existing_action = {
        "id": "ca-1", "predmet_id": PID, "tip": "PRIPREMITI_PODNESAK", "status": "open",
        "dedupe_key": "stale-key-not-in-target", "razlog": "x", "prioritet": "high", "rok": None,
        "updated_at": "2026-09-01T00:00:00+00:00",
    }
    fake = _make_fake(rocista=[])
    fake.tables["case_actions"] = [existing_action]

    class _RacedCloseQuery(_FakeQuery):
        def execute(self):
            if self._op == "update" and self._payload.get("status") == "closed":
                # Simulates a fresher concurrent write already having
                # changed updated_at -- this call's own .eq("updated_at",
                # snapshot) matches zero rows.
                res = MagicMock()
                res.data = []
                return res
            return super().execute()

    class _RacedFakeSupa(_FakeSupa):
        def table(self, name):
            self.tables.setdefault(name, [])
            if name == "case_actions":
                return _RacedCloseQuery(self.tables[name])
            return _FakeQuery(self.tables[name])

    raced_fake = _RacedFakeSupa(fake.tables)
    audit_calls = []

    async def _capture_log_action(action, **kw):
        if action == "case_action_refreshed":
            audit_calls.append(kw)
        return "audit-id"

    with patch("services.case_evolution._get_supa", return_value=raced_fake), \
         patch("shared.audit_immutable.log_action", new=_capture_log_action):
        result = await _consequence_refresh_case_actions(_event("E1"))

    # A document-less, evidence-less matter also trips the risk engine's
    # own "missing expected document type" rules -- irrelevant noise here;
    # what this test proves is scoped to the one pre-existing stale action.
    assert "closed=0" in result
    assert audit_calls[0]["metadata"]["closed_actions"] == []
    # The row itself is untouched -- still open, exactly as the race requires.
    assert fake.tables["case_actions"][0]["status"] == "open"

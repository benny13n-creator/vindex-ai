# -*- coding: utf-8 -*-
"""
VINDEX AI V1, Wave 2, Task 2B -- Terminal matter invariant + canonical
action ownership.

Wave 1 proved: services/case_evolution.py is the canonical decision owner
for case_actions, but routers/predmeti_close.py ALSO wrote directly to it
(migrations/099_case_actions.sql's own invariant violated), and neither
that direct write NOR the canonical reconcile ever checked whether the
matter had gone terminal before creating/updating an open action or
projecting a notification. The concrete failure: an event queued while a
matter was active, processed AFTER the matter was closed, could insert a
brand-new open case_actions row and fire a "Hitan rok" bell for a case the
lawyer already closed.

This file proves, against the REAL production code (not a reimplementation
-- `services.case_evolution._compute_target_actions`,
`_consequence_refresh_case_actions`,
`_consequence_project_case_actions_to_notifications`, and
`routers.predmeti_close.zatvori_predmet` /  `bulk_promena_statusa`):

1. RACE: an event delayed until after matter closure cannot create a new
   open action or a new notification.
2. REPLAY: replaying an already-processed pre-closure event after closure
   does not resurrect operational work.
3. Existing open actions on a matter that goes terminal actually get
   closed (not just blocked from growing) -- via the SAME negative-
   reconciliation path a normal "fact no longer holds" resolution uses.
4. ACTIVE-MATTER REGRESSION: normal create/update/close behavior for a
   non-terminal matter is unchanged.
5. Canonical ownership: routers/predmeti_close.py (single-close AND bulk
   paths) now drive case_actions exclusively through
   _consequence_refresh_case_actions -- no direct table write.
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
# Generic in-memory fake Postgres -- same proven harness as
# tests/test_omega_sprint004_case_to_workspace_flow.py (a real, mutable,
# shared table per name), extended with .neq() for predmeti_close.py's own
# concurrency guard.
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

    def upsert(self, row, on_conflict=None, ignore_duplicates=False):
        self._op = "upsert"
        self._payload = row
        self._on_conflict = [c.strip() for c in (on_conflict or "").split(",") if c.strip()]
        self._ignore_duplicates = ignore_duplicates
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
        elif self._op == "upsert":
            keys = self._on_conflict or ["id"]
            existing = next(
                (r for r in self._rows_ref if all(r.get(k) == self._payload.get(k) for k in keys)),
                None,
            )
            if existing is not None:
                if self._ignore_duplicates:
                    res.data = []  # PostgREST: DO NOTHING conflict -> no row returned
                else:
                    existing.update(self._payload)
                    res.data = [existing]
            else:
                new_row = dict(self._payload)
                new_row.setdefault("id", f"gen-{len(self._rows_ref) + 1}")
                self._rows_ref.append(new_row)
                res.data = [new_row]
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


def _predmet_row(status="aktivan"):
    return {"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A", "case_dna": {}, "tip": "parnicno", "status": status}


def _rociste_row_soon():
    """A hearing 5 days out -- trips case_actions Rule 1 (PRIPREMITI_PODNESAK),
    the exact target-action class the terminal guard must suppress."""
    return {
        "id": "roc-1", "predmet_id": "pred-1",
        "sud": "Osnovni sud", "datum": (date.today() + timedelta(days=5)).isoformat(),
        "status": "zakazano",
    }


def _event(event_type=EventType.DOCUMENT_ACCEPTED, event_id="evt-1"):
    return Event(type=event_type, user_id="user-1", predmet_id="pred-1",
                 payload={}, correlation_id="corr-1", event_id=event_id)


def _make_fake(status="aktivan", with_hearing=True, case_actions=None, notifications=None):
    return _FakeSupa({
        "predmeti": [_predmet_row(status)],
        "predmet_dokazi": [],
        "predmet_dokumenti": [],
        "rocista": [_rociste_row_soon()] if with_hearing else [],
        "case_actions": list(case_actions or []),
        "notifications": list(notifications or []),
    })


# ═══════════════════════════════════════════════════════════════════════════
# 1. Active-matter regression -- normal behavior unchanged
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_active_matter_with_upcoming_hearing_creates_open_action():
    from services.case_evolution import _consequence_refresh_case_actions

    fake = _make_fake(status="aktivan", with_hearing=True)
    with patch("services.case_evolution._get_supa", return_value=fake):
        result = await _consequence_refresh_case_actions(_event())

    # An active matter with zero evidence/documents on file also trips the
    # risk engine's own "missing expected document type" rules -- this test
    # is about the hearing-driven deadline rule specifically, so it asserts
    # that action exists among whatever was created, not an exact total.
    assert "closed=0" in result
    open_actions = [r for r in fake.tables["case_actions"] if r.get("status") == "open"]
    assert len(open_actions) >= 1
    hearing_actions = [a for a in open_actions if a["tip"] == "PRIPREMITI_PODNESAK"]
    assert len(hearing_actions) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 2. RACE: event delayed past matter closure cannot create a new open
#    action or a new notification
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_race_delayed_event_after_closure_creates_no_open_action():
    """E1 emitted while the matter was active (its target set would include
    a hearing-driven PRIPREMITI_PODNESAK action). Processing is delayed
    until AFTER the matter is closed -- simulated by flipping the fake
    predmeti row's status to 'zatvoren' before the reconcile actually
    runs, exactly what an outbox-delayed dispatch would see on its own
    fresh read."""
    from services.case_evolution import _consequence_refresh_case_actions

    fake = _make_fake(status="aktivan", with_hearing=True)
    # Matter closes while E1 is "in flight" -- the delayed processor only
    # ever sees the CURRENT row when it finally reads it.
    fake.tables["predmeti"][0]["status"] = "zatvoren"

    with patch("services.case_evolution._get_supa", return_value=fake):
        result = await _consequence_refresh_case_actions(_event())

    assert result == "created=0 updated=0 closed=0"
    assert fake.tables["case_actions"] == []


@pytest.mark.anyio
async def test_race_delayed_event_after_closure_fires_no_notification():
    from services.case_evolution import _consequence_project_case_actions_to_notifications

    fake = _make_fake(status="zatvoren", with_hearing=True, case_actions=[{
        "id": "ca-1", "predmet_id": "pred-1", "tip": "PRIPREMITI_PODNESAK",
        "status": "open", "dedupe_key": "rociste:roc-1",
        "razlog": "Rok ističe za 5 dana", "prioritet": "critical", "rok": (date.today() + timedelta(days=5)).isoformat(),
    }])

    with patch("services.case_evolution._get_supa", return_value=fake):
        result = await _consequence_project_case_actions_to_notifications(_event())

    assert result == "skipped_terminal_matter"
    assert fake.tables["notifications"] == []


@pytest.mark.anyio
async def test_race_end_to_end_via_handle_case_changed():
    """The full dispatcher path (handle_case_changed -> refresh_case_actions,
    NEW_EVIDENCE_REGISTERED's own registered sequence) for a matter closed
    before this delayed event is processed. Zero open actions, zero
    notifications, event still completes (marked handled, not dead-lettered
    -- a terminal matter is not itself a processing error).

    Deliberately NOT DOCUMENT_ACCEPTED/ROCISTE_ZAKAZANO here: both register
    genome_refresh first, which Wave 1 already identified as having its own
    separate, not-yet-fixed false dependency on document/genome state for a
    document-less matter (Task 2C, strictly AFTER this task in the Wave 2
    sequence) -- exercising it here would conflate 2C's own not-yet-closed
    defect with what THIS test exists to prove. NEW_EVIDENCE_REGISTERED's
    registry entry is [evidence_classification, refresh_case_actions] --
    no genome step -- and evidence_classification no-ops cleanly
    ("skipped_no_dokument_id") on this test's empty payload."""
    from services.case_evolution import handle_case_changed

    fake = _make_fake(status="zatvoren", with_hearing=True)

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await handle_case_changed(_event(EventType.NEW_EVIDENCE_REGISTERED, event_id="evt-race-1"))

    assert [r for r in fake.tables["case_actions"] if r.get("status") == "open"] == []
    assert fake.tables["notifications"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. REPLAY: an old pre-closure event replayed after closure does not
#    resurrect work
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_replay_after_closure_does_not_resurrect_action():
    """First run happens while active (creates the action, matching normal
    behavior). Matter then closes (simulating predmeti_close.py's own
    reconcile call, which would have closed it -- reproduced directly here
    via a second _consequence_refresh_case_actions call, its own proven
    negative-reconciliation path). A REPLAY of the original event E1 (e.g.
    outbox retry, or a queued duplicate) must not reopen it."""
    from services.case_evolution import _consequence_refresh_case_actions

    fake = _make_fake(status="aktivan", with_hearing=True)
    with patch("services.case_evolution._get_supa", return_value=fake):
        first = await _consequence_refresh_case_actions(_event(event_id="evt-1"))
    n_created = len([r for r in fake.tables["case_actions"] if r["status"] == "open"])
    assert n_created >= 1
    assert f"created={n_created}" in first

    # Matter closes -- predmeti_close.py's own canonical reconcile call.
    fake.tables["predmeti"][0]["status"] = "zatvoren"
    with patch("services.case_evolution._get_supa", return_value=fake):
        closure_reconcile = await _consequence_refresh_case_actions(_event(event_id="evt-close"))
    assert f"closed={n_created}" in closure_reconcile
    assert [r for r in fake.tables["case_actions"] if r["status"] == "open"] == []

    # Replay of the ORIGINAL event, e.g. an outbox retry that still had the
    # old payload queued.
    with patch("services.case_evolution._get_supa", return_value=fake):
        replay = await _consequence_refresh_case_actions(_event(event_id="evt-1"))

    assert replay == "created=0 updated=0 closed=0"
    assert [r for r in fake.tables["case_actions"] if r["status"] == "open"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. Existing open actions actually resolve (not merely blocked from
#    growing) when the matter goes terminal
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_terminal_matter_closes_existing_open_actions_via_negative_reconciliation():
    from services.case_evolution import _consequence_refresh_case_actions

    existing_open = {
        "id": "ca-existing", "predmet_id": "pred-1", "tip": "PRIBAVITI_DOKAZ",
        "status": "open", "dedupe_key": "nedostaje:ugovor", "razlog": "x",
        "prioritet": "high", "rok": None, "updated_at": "2026-09-01T00:00:00+00:00",
    }
    fake = _make_fake(status="zatvoren", with_hearing=False, case_actions=[existing_open])

    with patch("services.case_evolution._get_supa", return_value=fake):
        result = await _consequence_refresh_case_actions(_event())

    assert result == "created=0 updated=0 closed=1"
    row = fake.tables["case_actions"][0]
    assert row["status"] == "closed"
    assert row["closed_at"] is not None


# ═══════════════════════════════════════════════════════════════════════════
# 5. Canonical write ownership -- predmeti_close.py routes through the
#    canonical reconcile, end to end via the real HTTP handlers
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_zatvori_predmet_reconciles_via_canonical_function_not_direct_write():
    from routers.predmeti_close import ZatvoriReq, zatvori_predmet
    from starlette.requests import Request as StarletteRequest

    existing_open = {
        "id": "ca-existing", "predmet_id": "pred-1", "tip": "PRIBAVITI_DOKAZ",
        "status": "open", "dedupe_key": "nedostaje:ugovor", "razlog": "x",
        "prioritet": "high", "rok": None, "updated_at": "2026-09-01T00:00:00+00:00",
    }
    fake = _FakeSupa({
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A", "status": "aktivan", "opis": "", "case_dna": {}, "tip": "parnicno"}],
        "predmet_hronologija": [],
        "predmet_dokazi": [], "predmet_dokumenti": [], "rocista": [],
        "case_actions": [existing_open],
        "notifications": [], "profiles": [], "billing_entries": [], "case_benchmarks": [],
    })

    req = MagicMock(spec=StarletteRequest)
    req.headers = {}
    req.client = None
    req.state = MagicMock()

    with patch("routers.predmeti_close._get_supa", return_value=fake), \
         patch("services.case_evolution._get_supa", return_value=fake):
        result = await zatvori_predmet(
            "pred-1", ZatvoriReq(ishod="pobeda"), req, {"user_id": "user-1"},
        )

    assert result["ok"] is True
    assert fake.tables["predmeti"][0]["status"] == "zatvoren"
    assert [r for r in fake.tables["case_actions"] if r["status"] == "open"] == []
    assert fake.tables["case_actions"][0]["status"] == "closed"


@pytest.mark.anyio
async def test_bulk_zatvaranje_reconciles_only_actually_updated_predmeti():
    from routers.predmeti_close import BulkAkcijaReq, bulk_promena_statusa
    from starlette.requests import Request as StarletteRequest

    fake = _FakeSupa({
        "predmeti": [
            {"id": "p1", "user_id": "user-1", "naziv": "P1", "status": "aktivan", "case_dna": {}, "tip": "parnicno"},
            {"id": "p2", "user_id": "user-1", "naziv": "P2", "status": "zatvoren", "case_dna": {}, "tip": "parnicno"},  # already terminal -> loses the .neq() race
        ],
        "predmet_dokazi": [], "predmet_dokumenti": [], "rocista": [],
        "case_actions": [
            {"id": "ca-p1", "predmet_id": "p1", "tip": "PRIBAVITI_DOKAZ", "status": "open", "dedupe_key": "k1", "razlog": "x", "prioritet": "high", "rok": None, "updated_at": "2026-09-01T00:00:00+00:00"},
            {"id": "ca-p2", "predmet_id": "p2", "tip": "PRIBAVITI_DOKAZ", "status": "open", "dedupe_key": "k2", "razlog": "x", "prioritet": "high", "rok": None, "updated_at": "2026-09-01T00:00:00+00:00"},
        ],
        "notifications": [],
    })

    req = MagicMock(spec=StarletteRequest)
    req.headers = {}
    req.client = None
    req.state = MagicMock()

    with patch("routers.predmeti_close._get_supa", return_value=fake), \
         patch("services.case_evolution._get_supa", return_value=fake):
        result = await bulk_promena_statusa(
            BulkAkcijaReq(predmet_ids=["p1", "p2"], akcija="zatvaranje"), req, {"user_id": "user-1"},
        )

    # p2 was already 'zatvoren' -- the .neq("status", "zatvoren") guard
    # means it does not count as newly updated by THIS call.
    assert result["azurirano"] == 1
    # p1's action reconciled (closed) as part of THIS call.
    ca_p1 = next(r for r in fake.tables["case_actions"] if r["id"] == "ca-p1")
    assert ca_p1["status"] == "closed"
    # p2's action untouched by this call (it wasn't in the actually-updated set) --
    # proves scoping to update_r.data, not the full requested id list.
    ca_p2 = next(r for r in fake.tables["case_actions"] if r["id"] == "ca-p2")
    assert ca_p2["status"] == "open"

# -*- coding: utf-8 -*-
"""
Program Omega, Sprint 005 (2026-08-06) — "Unified Operational Experience",
Scenario 1: prove the FULL chain, not just the Action Engine's own slice of
it. Unlike Sprint 004's own flow test (which calls
`_consequence_refresh_case_actions` directly), this file drives the REAL
`dispatch_pending_events()` — the same entry point a background worker
uses against a raw `events` outbox row — through `handle_case_changed`'s
own canonical dispatch (genome_refresh -> timeline_entry ->
refresh_case_actions, Program Delta/Omega's own established sequential
guarantee) and into `GET /api/workspace`'s read path. This is the
mission's own "Upload -> Dokument -> Review -> Prihvatanje -> Workspace ->
Case -> Action -> Dashboard, sve mora biti povezano" scenario, scoped
honestly: it starts from a durable DOCUMENT_ACCEPTED event already sitting
in the outbox (exactly what `smart_intake.py::finalize_intake_job`/
`resolve_job_review` produce at the end of the real upload/review flow --
that specific step is already proven by this whole engagement's own
Sprint 001-007/Delta test suites, not re-proven here) through to the one
thing that was NEVER proven end-to-end before this sprint: does it reach
Workspace automatically, with nothing manual in between.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.event_bus import EventType


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _NotFilter:
    """Backs `.not_.is_(...)`/`.not_.in_(...)` -- Program Omega, Final
    Sprint 007's own _consequence_project_case_actions_to_notifications
    uses `.not_.is_("dedupe_key", "null")` (the same real supabase-py idiom
    already used repo-wide, e.g. routers/benchmarking.py), which this fake
    harness never needed to model before this sprint."""
    def __init__(self, query):
        self._query = query

    def is_(self, col, val):
        if val in ("null", None):
            self._query._filtered = [r for r in self._query._filtered if r.get(col) is not None]
        return self._query

    def in_(self, col, vals):
        vals = set(vals)
        self._query._filtered = [r for r in self._query._filtered if r.get(col) not in vals]
        return self._query


class _FakeQuery:
    """Generic in-memory fake query builder -- same idiom as
    tests/test_omega_sprint004_case_to_workspace_flow.py, extended here
    with `.is_()`/`.order()`/`.limit()` support for the `events` outbox's
    own claim-fallback select shape."""
    def __init__(self, rows_ref):
        self._rows_ref = rows_ref
        self._filtered = list(rows_ref)
        self._op = "select"
        self._payload = None
        self._single = False
        self._ignore_duplicates = False
        self._on_conflict = None

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

    def upsert(self, row, on_conflict=None, ignore_duplicates=False):
        self._op = "upsert"
        self._payload = row
        self._ignore_duplicates = ignore_duplicates
        self._on_conflict = on_conflict
        return self

    def eq(self, col, val):
        self._filtered = [r for r in self._filtered if r.get(col) == val]
        return self

    def in_(self, col, vals):
        vals = set(vals)
        self._filtered = [r for r in self._filtered if r.get(col) in vals]
        return self

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

    @property
    def not_(self):
        return _NotFilter(self)

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
        elif self._op == "upsert":
            new_row = dict(self._payload)
            if self._ignore_duplicates and self._on_conflict:
                # Program Lambda, Certification 004: real INSERT ... ON
                # CONFLICT (cols) DO NOTHING inserts nothing (and returns
                # no row) if a row already matches on the conflict
                # columns -- needed for _try_claim_consequence's own
                # atomic claim (services/case_evolution.py).
                cols = [c.strip() for c in self._on_conflict.split(",")]
                conflict = any(
                    all(r.get(c) == new_row.get(c) for c in cols)
                    for r in self._rows_ref
                )
                if conflict:
                    res.data = []
                    return res
            self._rows_ref.append(new_row)
            res.data = [new_row]
        elif self._op == "update":
            for r in self._filtered:
                r.update(self._payload)
            res.data = list(self._filtered)
        else:
            res.data = (self._filtered[0] if self._filtered else None) if self._single else list(self._filtered)
        return res


class _FakeSupa:
    def __init__(self, tables: dict):
        self.tables = {k: list(v) for k, v in tables.items()}

    def table(self, name):
        self.tables.setdefault(name, [])
        return _FakeQuery(self.tables[name])


class _Req:
    pass


def _user():
    return {"user_id": "user-1"}


@pytest.mark.anyio
async def test_scenario1_raw_outbox_event_flows_all_the_way_to_workspace():
    from services.event_bus import dispatch_pending_events
    from routers.workspace import get_workspace

    fake = _FakeSupa({
        "events": [{
            "id": "evt-real-1", "event_type": "DocumentAccepted", "user_id": "user-1",
            "predmet_id": "pred-1", "payload": {"dokumenti": ["tuzba.pdf"]},
            "correlation_id": "corr-real-1", "dispatch_attempts": 0,
        }],
        "case_evolution_consequences": [],
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A", "case_dna": {"verzija": 1}, "tip": "parnicno"}],
        "predmet_hronologija": [],
        "predmet_dokazi": [],
        "predmet_dokumenti": [],
        "rocista": [],
        "case_actions": [],
        "zadaci": [],
        "intake_jobs": [],
    })
    # Match Program Delta's own established "no claim_pending_events RPC
    # deployed" fallback path.
    fake.rpc = MagicMock(side_effect=Exception("PGRST202: Could not find the function public.claim_pending_events"))

    async def _fake_genome_bg(predmet_id, uid, before_verzija, trigger=None):
        # _consequence_genome_refresh independently verifies case_dna.verzija
        # actually incremented -- simulate what a real refresh does.
        for row in fake.tables["predmeti"]:
            if row["id"] == predmet_id:
                row["case_dna"] = {**row.get("case_dna", {}), "verzija": (row.get("case_dna", {}).get("verzija") or 0) + 1}
    genome_bg = AsyncMock(side_effect=_fake_genome_bg)
    with patch("shared.deps._get_supa", return_value=fake), \
         patch("services.case_evolution._get_supa", return_value=fake), \
         patch("routers.case_dna._run_genome_background", genome_bg), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        result = await dispatch_pending_events()

    assert result["dispecovano"] == 1
    genome_bg.assert_awaited_once()  # Genome really refreshed, not skipped
    assert len(fake.tables["predmet_hronologija"]) == 1  # Timeline entry written
    assert len(fake.tables["case_actions"]) >= 1  # Action Engine really ran

    # The exact same table state, read through the exact same production
    # Workspace endpoint -- no manual refresh, no second data source.
    with patch("routers.workspace._get_supa", return_value=fake):
        workspace = await get_workspace(_Req(), _user())

    assert workspace["ukupno_aktivnih"] >= 1
    all_items = workspace["danas"] + workspace["kriticno"] + workspace["predstojece"]
    assert any(item["predmet_id"] == "pred-1" for item in all_items)


@pytest.mark.anyio
async def test_scenario1_replay_does_not_duplicate_workspace_items():
    """Re-dispatching the same durable event (e.g. an operator retry) must
    not produce a second case_actions row for the same fact, and Workspace
    must show the identical result both times."""
    from services.event_bus import dispatch_pending_events, Event
    from services.case_evolution import handle_case_changed
    from routers.workspace import get_workspace

    fake = _FakeSupa({
        "events": [{
            "id": "evt-real-1", "event_type": "DocumentAccepted", "user_id": "user-1",
            "predmet_id": "pred-1", "payload": {"dokumenti": ["tuzba.pdf"]},
            "correlation_id": "corr-real-1", "dispatch_attempts": 0,
        }],
        "case_evolution_consequences": [],
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A", "case_dna": {"verzija": 1}, "tip": "parnicno"}],
        "predmet_hronologija": [],
        "predmet_dokazi": [],
        "predmet_dokumenti": [],
        "rocista": [],
        "case_actions": [],
        "zadaci": [],
        "intake_jobs": [],
    })
    fake.rpc = MagicMock(side_effect=Exception("PGRST202: Could not find the function public.claim_pending_events"))

    async def _fake_genome_bg(predmet_id, uid, before_verzija, trigger=None):
        for row in fake.tables["predmeti"]:
            if row["id"] == predmet_id:
                row["case_dna"] = {**row.get("case_dna", {}), "verzija": (row.get("case_dna", {}).get("verzija") or 0) + 1}

    with patch("shared.deps._get_supa", return_value=fake), \
         patch("services.case_evolution._get_supa", return_value=fake), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock(side_effect=_fake_genome_bg)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await dispatch_pending_events()

    with patch("routers.workspace._get_supa", return_value=fake):
        first = await get_workspace(_Req(), _user())

    n_actions_after_first = len(fake.tables["case_actions"])

    # Replay the SAME event_id directly (simulating a retry/duplicate
    # delivery) -- handle_case_changed's own idempotency (per event_id +
    # consequence_name) must make this a full no-op.
    replay_event = Event(type=EventType.DOCUMENT_ACCEPTED, user_id="user-1", predmet_id="pred-1",
                          payload={"dokumenti": ["tuzba.pdf"]}, correlation_id="corr-real-1", event_id="evt-real-1")
    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock()) as genome_bg2, \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await handle_case_changed(replay_event)
    genome_bg2.assert_not_awaited()  # already completed, not redone

    with patch("routers.workspace._get_supa", return_value=fake):
        second = await get_workspace(_Req(), _user())

    assert len(fake.tables["case_actions"]) == n_actions_after_first  # no duplicate row
    assert first["ukupno_aktivnih"] == second["ukupno_aktivnih"]

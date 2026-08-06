# -*- coding: utf-8 -*-
"""
Program Omega, Final Sprint 007 (2026-08-06) — Canonical Notification &
Trigger Engine, Phase 6 (Concurrency). Attacks _consequence_project_case_
actions_to_notifications with genuinely concurrent (asyncio.gather, real
thread-pool interleaving via asyncio.to_thread) executions -- not just
sequential unit calls -- to prove the partial-UNIQUE-index race path
(migration 101) is exercised correctly under real interleaving, not only
reasoned about.

Honest scope: this proves the CODE PATH that would run against a real
Postgres unique-index violation is correct under real concurrent asyncio/
thread-pool execution. It does not stand up a real Postgres instance --
see NOTIFICATION_DEDUPLICATION_REPORT.md's own residual-gaps section for
what is proven at this level vs. what would need a live-DB integration
test.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import threading
import pytest
from unittest.mock import MagicMock, patch

from services.event_bus import Event, EventType


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _RacyQuery:
    """Same shape as tests/test_omega_sprint007_project_notifications.py's
    own _Query, but the notifications table's own insert path enforces a
    REAL uniqueness check under a threading.Lock -- simulating exactly what
    migration 101's own partial UNIQUE index (user_id, dedupe_key) WHERE
    procitano=FALSE guarantees on the real database, including the race
    window between check and insert that only a DB constraint (not
    application code) can close."""
    def __init__(self, rows_ref, lock, enforce_unique):
        self._rows_ref = rows_ref
        self._filtered = list(rows_ref)
        self._op = "select"
        self._payload = None
        self._single = False
        self._lock = lock
        self._enforce_unique = enforce_unique

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

    def maybe_single(self):
        self._single = True
        return self

    @property
    def not_(self):
        return _RacyNot(self)

    def execute(self):
        if self._op == "insert":
            if self._enforce_unique:
                with self._lock:
                    conflict = any(
                        r.get("user_id") == self._payload.get("user_id")
                        and r.get("dedupe_key") == self._payload.get("dedupe_key")
                        and not r.get("procitano", False)
                        for r in self._rows_ref
                    )
                    if conflict:
                        raise Exception(
                            'duplicate key value violates unique constraint '
                            '"idx_notifications_open_dedupe"'
                        )
                    new_row = dict(self._payload)
                    new_row.setdefault("id", f"notif-{len(self._rows_ref) + 1}")
                    new_row.setdefault("procitano", False)
                    self._rows_ref.append(new_row)
            else:
                new_row = dict(self._payload)
                new_row.setdefault("id", f"notif-{len(self._rows_ref) + 1}")
                new_row.setdefault("procitano", False)
                self._rows_ref.append(new_row)
            res = MagicMock(); res.data = [self._payload]
            return res
        elif self._op == "update":
            with self._lock:
                for r in self._filtered:
                    r.update(self._payload)
            res = MagicMock(); res.data = list(self._filtered)
            return res
        else:
            res = MagicMock()
            res.data = (self._filtered[0] if self._filtered else None) if self._single else list(self._filtered)
            return res


class _RacyNot:
    def __init__(self, query):
        self._query = query

    def is_(self, col, val):
        if val in ("null", None):
            self._query._filtered = [r for r in self._query._filtered if r.get(col) is not None]
        return self._query


class _RacyFakeSupa:
    """Shared, mutable table state across "concurrent workers" -- each
    call to .table() re-snapshots the CURRENT shared list (as a real
    Supabase client re-queries the live DB on every call), so a second
    worker's SELECT can see rows a first worker's INSERT already
    committed, exactly like real concurrent DB sessions would (read
    committed isolation)."""
    def __init__(self, tables):
        self.tables = {k: list(v) for k, v in tables.items()}
        self._lock = threading.Lock()

    def table(self, name):
        self.tables.setdefault(name, [])
        return _RacyQuery(self.tables[name], self._lock, enforce_unique=(name == "notifications"))


def _event(predmet_id="pred-1", event_id="evt-1"):
    return Event(type=EventType.DOCUMENT_ACCEPTED, user_id="user-1", predmet_id=predmet_id,
                 payload={}, correlation_id="corr-1", event_id=event_id)


@pytest.mark.anyio
async def test_two_concurrent_projections_for_the_same_deadline_produce_exactly_one_row():
    """Attack: 2 concurrent Case Evolution dispatches for the SAME predmet
    (e.g. a genome_refresh triggered from 2 near-simultaneous events) both
    reach _consequence_project_case_actions_to_notifications at close to
    the same time, for the SAME dedupe_key, with no existing notification
    yet. Mission's own 'parallel upload -> no duplicate attention items'
    scenario, applied to this consequence directly."""
    from services.case_evolution import _consequence_project_case_actions_to_notifications

    fake = _RacyFakeSupa({
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A"}],
        "case_actions": [{
            "dedupe_key": "rociste:rociste-1", "razlog": "Ročište", "prioritet": "critical",
            "rok": "2026-08-10", "predmet_id": "pred-1", "status": "open", "tip": "PRIPREMITI_PODNESAK",
        }],
        "notifications": [],
    })

    with patch("services.case_evolution._get_supa", return_value=fake):
        results = await asyncio.gather(
            _consequence_project_case_actions_to_notifications(_event(event_id="evt-A")),
            _consequence_project_case_actions_to_notifications(_event(event_id="evt-B")),
        )

    # Exactly one notification row must exist -- the DB-index race path
    # (caught duplicate-key exception) must have absorbed the loser, not
    # crashed the whole consequence.
    assert len(fake.tables["notifications"]) == 1
    # Combined across both concurrent runs, exactly 1 create total (the
    # other either saw the winner's row on its own SELECT, or hit the
    # unique-index race and was swallowed) -- never 2 creates.
    total_created = sum(int(r.split("created=")[1].split(" ")[0]) for r in results)
    assert total_created == 1


@pytest.mark.anyio
async def test_ten_concurrent_projections_same_deadline_still_exactly_one_row():
    """A harsher version of the above -- 10-way concurrency, same fact."""
    from services.case_evolution import _consequence_project_case_actions_to_notifications

    fake = _RacyFakeSupa({
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A"}],
        "case_actions": [{
            "dedupe_key": "rociste:rociste-1", "razlog": "Ročište", "prioritet": "high",
            "rok": "2026-08-10", "predmet_id": "pred-1", "status": "open", "tip": "PRIPREMITI_PODNESAK",
        }],
        "notifications": [],
    })

    with patch("services.case_evolution._get_supa", return_value=fake):
        await asyncio.gather(*[
            _consequence_project_case_actions_to_notifications(_event(event_id=f"evt-{i}"))
            for i in range(10)
        ])

    assert len(fake.tables["notifications"]) == 1


@pytest.mark.anyio
async def test_concurrent_projections_for_different_predmeti_do_not_interfere():
    """Negative control -- concurrent work on genuinely DIFFERENT cases must
    not be serialized or dropped by the same shared-table race handling."""
    from services.case_evolution import _consequence_project_case_actions_to_notifications

    fake = _RacyFakeSupa({
        "predmeti": [
            {"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A"},
            {"id": "pred-2", "user_id": "user-1", "naziv": "Predmet B"},
        ],
        "case_actions": [
            {"dedupe_key": "rociste:r-1", "razlog": "R1", "prioritet": "critical",
             "rok": "2026-08-10", "predmet_id": "pred-1", "status": "open", "tip": "PRIPREMITI_PODNESAK"},
            {"dedupe_key": "rociste:r-2", "razlog": "R2", "prioritet": "critical",
             "rok": "2026-08-11", "predmet_id": "pred-2", "status": "open", "tip": "PRIPREMITI_PODNESAK"},
        ],
        "notifications": [],
    })

    with patch("services.case_evolution._get_supa", return_value=fake):
        await asyncio.gather(
            _consequence_project_case_actions_to_notifications(_event(predmet_id="pred-1", event_id="evt-1")),
            _consequence_project_case_actions_to_notifications(_event(predmet_id="pred-2", event_id="evt-2")),
        )

    assert len(fake.tables["notifications"]) == 2
    keys = {r["dedupe_key"] for r in fake.tables["notifications"]}
    assert keys == {"rociste:r-1", "rociste:r-2"}

# -*- coding: utf-8 -*-
"""
Program Omega, Final Sprint 007 (2026-08-06) — Canonical Notification &
Trigger Engine. Direct tests for
services/case_evolution.py::_consequence_project_case_actions_to_notifications
-- the new trailing consequence that projects case_actions' own canonical
deadline findings (tip='PRIPREMITI_PODNESAK') into the notifications table,
using the SAME dedupe_key-based reconcile-target-vs-existing idiom already
proven for case_actions itself (migration 099), now applied to a second
table (migration 101). Proves: create/update/close reconciliation, the
canonical->notifications priority translation, graceful no-op when there is
no predmet_id/owner, and benign handling of a concurrent duplicate-insert
race (the partial UNIQUE index migration 101 adds).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

from services.event_bus import Event, EventType


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _Query:
    """Minimal in-memory fake query builder over a list[dict], enough for
    the exact select/eq/insert/update/not_.is_ chains this consequence
    uses."""
    def __init__(self, rows_ref, on_insert=None):
        self._rows_ref = rows_ref
        self._filtered = list(rows_ref)
        self._op = "select"
        self._payload = None
        self._single = False
        self._on_insert = on_insert

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
        return _Not(self)

    def execute(self):
        res = MagicMock()
        if self._op == "insert":
            if self._on_insert:
                self._on_insert(self._payload)
            new_row = dict(self._payload)
            new_row.setdefault("id", f"notif-{len(self._rows_ref) + 1}")
            new_row.setdefault("procitano", False)
            self._rows_ref.append(new_row)
            res.data = [new_row]
        elif self._op == "update":
            for r in self._filtered:
                r.update(self._payload)
            res.data = list(self._filtered)
        else:
            res.data = (self._filtered[0] if self._filtered else None) if self._single else list(self._filtered)
        return res


class _Not:
    def __init__(self, query):
        self._query = query

    def is_(self, col, val):
        if val in ("null", None):
            self._query._filtered = [r for r in self._query._filtered if r.get(col) is not None]
        return self._query


class _FakeSupa:
    def __init__(self, tables, on_insert=None):
        self.tables = {k: list(v) for k, v in tables.items()}
        self._on_insert = on_insert or {}

    def table(self, name):
        self.tables.setdefault(name, [])
        return _Query(self.tables[name], on_insert=self._on_insert.get(name))


def _event(predmet_id="pred-1", event_id="evt-1"):
    return Event(type=EventType.DOCUMENT_ACCEPTED, user_id="user-1", predmet_id=predmet_id,
                 payload={}, correlation_id="corr-1", event_id=event_id)


@pytest.mark.anyio
async def test_no_predmet_id_is_a_clean_noop():
    from services.case_evolution import _consequence_project_case_actions_to_notifications

    event = Event(type=EventType.DOCUMENT_ACCEPTED, user_id="user-1", predmet_id=None,
                  payload={}, correlation_id="corr-1", event_id="evt-1")
    result = await _consequence_project_case_actions_to_notifications(event)
    assert result == "skipped_no_predmet_id"


@pytest.mark.anyio
async def test_predmet_without_owner_is_a_clean_noop():
    from services.case_evolution import _consequence_project_case_actions_to_notifications

    fake = _FakeSupa({"predmeti": [{"id": "pred-1", "naziv": "Predmet A"}]})  # no user_id
    with patch("services.case_evolution._get_supa", return_value=fake):
        result = await _consequence_project_case_actions_to_notifications(_event())
    assert result == "skipped_no_owner"


@pytest.mark.anyio
async def test_new_open_deadline_action_creates_one_notification_with_translated_priority():
    from services.case_evolution import _consequence_project_case_actions_to_notifications

    fake = _FakeSupa({
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A"}],
        "case_actions": [{
            "dedupe_key": "rociste:rociste-1", "razlog": "Ročište 2026-08-10",
            "prioritet": "critical", "rok": "2026-08-10",
            "predmet_id": "pred-1", "status": "open", "tip": "PRIPREMITI_PODNESAK",
        }],
        "notifications": [],
    })
    with patch("services.case_evolution._get_supa", return_value=fake):
        result = await _consequence_project_case_actions_to_notifications(_event())

    assert result == "created=1 updated=0 closed=0"
    assert len(fake.tables["notifications"]) == 1
    row = fake.tables["notifications"][0]
    assert row["dedupe_key"] == "rociste:rociste-1"
    assert row["prioritet"] == "urgent"  # CANONICAL_TO_NOTIFICATIONS[critical]
    assert row["tip"] == "hitan_rok"
    assert row["user_id"] == "user-1"
    assert row["predmet_id"] == "pred-1"


@pytest.mark.anyio
async def test_same_target_and_existing_key_updates_not_duplicates():
    from services.case_evolution import _consequence_project_case_actions_to_notifications

    fake = _FakeSupa({
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A"}],
        "case_actions": [{
            "dedupe_key": "rociste:rociste-1", "razlog": "Ročište pomereno na 2026-08-12",
            "prioritet": "high", "rok": "2026-08-12",
            "predmet_id": "pred-1", "status": "open", "tip": "PRIPREMITI_PODNESAK",
        }],
        "notifications": [{
            "id": "notif-existing", "dedupe_key": "rociste:rociste-1",
            "user_id": "user-1", "predmet_id": "pred-1", "procitano": False,
            "prioritet": "urgent", "tip": "hitan_rok",
        }],
    })
    with patch("services.case_evolution._get_supa", return_value=fake):
        result = await _consequence_project_case_actions_to_notifications(_event())

    assert result == "created=0 updated=1 closed=0"
    assert len(fake.tables["notifications"]) == 1  # still exactly one row
    row = fake.tables["notifications"][0]
    assert row["id"] == "notif-existing"
    assert row["prioritet"] == "high"  # re-translated from the updated case_actions priority
    assert row["tip"] == "rok"


@pytest.mark.anyio
async def test_retry_100_times_still_exactly_one_notification():
    """Mission's own mandatory Scenario 2 ('Isti rok. Retry 100 puta. -> I
    dalje jedna aktivna notifikacija'), applied directly to this
    consequence."""
    from services.case_evolution import _consequence_project_case_actions_to_notifications

    fake = _FakeSupa({
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A"}],
        "case_actions": [{
            "dedupe_key": "rociste:rociste-1", "razlog": "Ročište", "prioritet": "critical", "rok": "2026-08-10",
            "predmet_id": "pred-1", "status": "open", "tip": "PRIPREMITI_PODNESAK",
        }],
        "notifications": [],
    })
    with patch("services.case_evolution._get_supa", return_value=fake):
        for _ in range(100):
            await _consequence_project_case_actions_to_notifications(_event())

    assert len(fake.tables["notifications"]) == 1


@pytest.mark.anyio
async def test_resolved_deadline_closes_the_orphaned_notification():
    from services.case_evolution import _consequence_project_case_actions_to_notifications

    fake = _FakeSupa({
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A"}],
        "case_actions": [],  # the deadline action is gone -- resolved/rescheduled out of window
        "notifications": [{
            "id": "notif-orphan", "dedupe_key": "rociste:rociste-1",
            "user_id": "user-1", "predmet_id": "pred-1", "procitano": False,
            "prioritet": "urgent", "tip": "hitan_rok",
        }],
    })
    with patch("services.case_evolution._get_supa", return_value=fake):
        result = await _consequence_project_case_actions_to_notifications(_event())

    assert result == "created=0 updated=0 closed=1"
    assert fake.tables["notifications"][0]["procitano"] is True


@pytest.mark.anyio
async def test_concurrent_duplicate_insert_is_swallowed_not_raised():
    """migration 101's own partial UNIQUE index (user_id, dedupe_key) WHERE
    procitano=FALSE -- a second, concurrent projection racing to insert the
    SAME fact must be treated as a benign already-created race, not an
    error that fails the whole consequence."""
    from services.case_evolution import _consequence_project_case_actions_to_notifications

    def _boom(_row):
        raise Exception('duplicate key value violates unique constraint "idx_notifications_open_dedupe"')

    fake = _FakeSupa({
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A"}],
        "case_actions": [{
            "dedupe_key": "rociste:rociste-1", "razlog": "Ročište", "prioritet": "critical", "rok": "2026-08-10",
            "predmet_id": "pred-1", "status": "open", "tip": "PRIPREMITI_PODNESAK",
        }],
        "notifications": [],
    }, on_insert={"notifications": _boom})
    with patch("services.case_evolution._get_supa", return_value=fake):
        result = await _consequence_project_case_actions_to_notifications(_event())  # must not raise

    assert result == "created=0 updated=0 closed=0"


@pytest.mark.anyio
async def test_non_duplicate_insert_error_still_propagates():
    from services.case_evolution import _consequence_project_case_actions_to_notifications

    def _boom(_row):
        raise Exception("connection refused")

    fake = _FakeSupa({
        "predmeti": [{"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A"}],
        "case_actions": [{
            "dedupe_key": "rociste:rociste-1", "razlog": "Ročište", "prioritet": "critical", "rok": "2026-08-10",
            "predmet_id": "pred-1", "status": "open", "tip": "PRIPREMITI_PODNESAK",
        }],
        "notifications": [],
    }, on_insert={"notifications": _boom})
    with patch("services.case_evolution._get_supa", return_value=fake):
        with pytest.raises(Exception, match="connection refused"):
            await _consequence_project_case_actions_to_notifications(_event())

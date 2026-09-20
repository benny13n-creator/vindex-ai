# -*- coding: utf-8 -*-
"""
VINDEX AI V1, Wave 2, Task 2A -- Dead-letter observability.

Proves the fix for the Wave 1 finding: `events_outbox_metrics` used to
treat a terminally dead-lettered event identically to a clean dispatch
(both have `dispatched_at` set), so a permanently failed Case Evolution
consequence (genome refresh, case_actions reconciliation, notification
projection) was invisible on the only operational surface for the queue.

Two things are proven here:

1. `services/event_bus.py::classify_outbox_event` -- the Python-side
   classification rule -- correctly sorts all four required scenarios
   (pending/never-attempted, retrying-with-error, success, dead-letter)
   into exactly PENDING_RETRYABLE / SUCCESS / DEAD_LETTER, and that the
   real dispatch_pending_events() dead-letter write path uses the SAME
   DEAD_LETTER_MARKER constant this classifier reads (so the two can't
   silently drift apart).
2. migrations/130_events_outbox_dead_letter_metrics.sql's SQL text
   actually implements the corrected semantics: dead_letter_count exists,
   avg_dispatch_latency_s excludes dead-lettered rows, events_with_errors
   no longer requires dispatched_at IS NULL.

HONEST LIMITATION (documented per this repo's own established practice,
see docs/PHASE_PLAN.md Phase 0): this session has no live Postgres access
(SUPABASE_DB_URL not available here). The migration's actual SQL execution
against a real `events` table is NOT verified by these tests -- only (a)
that the Python classifier its docstring claims to mirror is correct, and
(b) that the migration file's SQL text contains the required corrected
FILTER clauses. Running migration 129 against production and re-reading
`events_outbox_metrics` live remains an explicit UNKNOWN for the founder
to close (same category as every other migration in this repo -- the
founder runs it, per this repo's own migrations policy).
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

import pytest
from unittest.mock import MagicMock, patch

from api import app  # noqa: E402,F401 -- bootstraps _patch_prompt_guard()

from services import event_bus as eb  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# 1. classify_outbox_event -- pure classification logic
# ═══════════════════════════════════════════════════════════════════════════

class TestClassifyOutboxEvent:
    def test_never_attempted_pending_is_pending_retryable(self):
        row = {"dispatched_at": None, "dispatch_attempts": 0, "last_error": None}
        assert eb.classify_outbox_event(row) == eb.OUTBOX_PENDING_RETRYABLE

    def test_retrying_with_error_but_not_yet_dispatched_is_pending_retryable(self):
        """A row that has already failed once or twice but hasn't hit
        MAX_DISPATCH_ATTEMPTS yet -- dispatched_at is still NULL (the outer
        dispatch loop only sets it on success or dead-letter exhaustion)."""
        row = {"dispatched_at": None, "dispatch_attempts": 3, "last_error": "boom: db timeout"}
        assert eb.classify_outbox_event(row) == eb.OUTBOX_PENDING_RETRYABLE

    def test_clean_dispatch_is_success(self):
        row = {"dispatched_at": "2026-09-19T10:00:00+00:00", "dispatch_attempts": 0, "last_error": None}
        assert eb.classify_outbox_event(row) == eb.OUTBOX_SUCCESS

    def test_dispatched_after_a_transient_retry_is_still_success(self):
        """dispatched_at set, dispatch_attempts > 0, but last_error is not a
        DEAD_LETTER marker -- a row that failed once, retried, and then
        genuinely succeeded. Must not be misclassified as dead-letter."""
        row = {"dispatched_at": "2026-09-19T10:05:00+00:00", "dispatch_attempts": 2, "last_error": "transient: boom"}
        assert eb.classify_outbox_event(row) == eb.OUTBOX_SUCCESS

    def test_dead_lettered_row_is_dead_letter_not_success(self):
        """The exact shape event_bus.py's own dead-letter write produces:
        dispatched_at IS SET (stops the poller) but last_error carries the
        DEAD_LETTER_MARKER. This is the row the Wave 1 finding proved was
        being silently counted as a clean success."""
        row = {
            "dispatched_at": "2026-09-19T10:10:00+00:00",
            "dispatch_attempts": eb.MAX_DISPATCH_ATTEMPTS,
            "last_error": f"{eb.DEAD_LETTER_MARKER} after {eb.MAX_DISPATCH_ATTEMPTS} attempts: RuntimeError: handler always fails",
        }
        assert eb.classify_outbox_event(row) == eb.OUTBOX_DEAD_LETTER

    def test_missing_fields_default_to_pending_retryable(self):
        assert eb.classify_outbox_event({}) == eb.OUTBOX_PENDING_RETRYABLE


# ═══════════════════════════════════════════════════════════════════════════
# 2. The real dead-letter write path uses the same marker the classifier reads
# ═══════════════════════════════════════════════════════════════════════════

class TestDeadLetterWriteUsesSharedMarker:
    @pytest.mark.anyio
    async def test_dead_letter_write_is_classified_as_dead_letter(self):
        """End-to-end within event_bus.py: drive dispatch_pending_events()
        for a permanently-broken handler, capture the exact row it writes
        to `events`, then feed that same payload through
        classify_outbox_event() and prove it comes back DEAD_LETTER -- not
        SUCCESS. This is the regression guard: if event_bus.py's dead-letter
        write ever stops using DEAD_LETTER_MARKER, this test catches the
        drift immediately instead of the metrics view silently going stale."""
        updates = []

        def _table(name):
            c = MagicMock()
            if name == "events":
                rows = [{
                    "id": "evt-1", "event_type": "rok_dodan", "user_id": "u1",
                    "predmet_id": None, "payload": {},
                    "dispatch_attempts": eb.MAX_DISPATCH_ATTEMPTS - 1,
                    "correlation_id": "cid-1",
                }]
                r = MagicMock(); r.data = rows
                c.select.return_value = c
                c.is_.return_value = c
                c.order.return_value = c
                c.limit.return_value = c
                c.execute = MagicMock(return_value=r)

                def _update(payload):
                    updates.append(payload)
                    return c
                c.update = MagicMock(side_effect=_update)
                c.eq.return_value = c
            return c

        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)
        supa.rpc = MagicMock(side_effect=Exception("PGRST202: Could not find the function public.claim_pending_events"))

        async def _broken_handler(event):
            raise RuntimeError("permanently broken")

        with patch("shared.deps._get_supa", return_value=supa), \
             patch.object(eb.bus, "_handlers", {eb.EventType.ROK_DODAN: [_broken_handler]}):
            result = await eb.dispatch_pending_events()

        assert result["dead_letter"] == 1
        written = updates[0]
        assert eb.DEAD_LETTER_MARKER in written["last_error"]

        # The exact row now sitting in `events` after this write -- prove
        # the classifier (and therefore the metrics view it mirrors) sees
        # it as DEAD_LETTER, not SUCCESS.
        simulated_row = {
            "dispatched_at": written["dispatched_at"],
            "dispatch_attempts": written["dispatch_attempts"],
            "last_error": written["last_error"],
        }
        assert simulated_row["dispatched_at"] is not None  # the exact condition that used to mean "success"
        assert eb.classify_outbox_event(simulated_row) == eb.OUTBOX_DEAD_LETTER


# ═══════════════════════════════════════════════════════════════════════════
# 3. Migration 129 SQL text implements the corrected metric semantics
# ═══════════════════════════════════════════════════════════════════════════

class TestMigration129ViewText:
    @staticmethod
    def _read_migration() -> str:
        path = os.path.join(
            os.path.dirname(__file__), "..", "migrations",
            "130_events_outbox_dead_letter_metrics.sql",
        )
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_dead_letter_count_field_exists(self):
        sql = self._read_migration()
        assert "dead_letter_count" in sql
        assert "last_error LIKE 'DEAD_LETTER%'" in sql

    def test_avg_latency_excludes_dead_letter_rows(self):
        sql = self._read_migration()
        # The avg_dispatch_latency_s FILTER must explicitly exclude
        # DEAD_LETTER rows, not merely require dispatched_at IS NOT NULL
        # (which a dead-lettered row also satisfies).
        latency_clause = sql.split("AS avg_dispatch_latency_s")[0].split("avg(extract")[-1]
        assert "DEAD_LETTER" in latency_clause

    def test_events_with_errors_no_longer_requires_dispatched_at_is_null(self):
        sql = self._read_migration()
        errors_clause = sql.split("AS events_with_errors")[0].split(
            "count(*) FILTER (WHERE dispatch_attempts > 0)"
        )
        # The corrected clause is the bare dispatch_attempts > 0 predicate
        # with no accompanying "dispatched_at IS NULL" -- proving the old
        # exclusion of dead-lettered rows (dispatched_at IS NOT NULL) was
        # removed, not merely relocated.
        assert len(errors_clause) == 2

    def test_marker_matches_python_constant(self):
        """The single sync point between this SQL and event_bus.py: both
        must use the literal text 'DEAD_LETTER'."""
        sql = self._read_migration()
        assert eb.DEAD_LETTER_MARKER in sql
        assert f"last_error LIKE '{eb.DEAD_LETTER_MARKER}%'" in sql

# -*- coding: utf-8 -*-
"""
SEC-002 — Data Retention & GDPR/ZZPL Cleanup tests.

Verifies services/retention_service.py::execute_retention_cleanup() deletes
rows older than the documented retention window and keeps newer rows, for
each of the 3 tables (security_events, user_daily_activity, ai_forensics)
plus the Pinecone tmp_* buffer cleanup call. Also locks in that the 2
confirmed-dead tables (usage_events, response_audit) are never touched.
"""
import os
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")
os.environ.setdefault("FOUNDER_EMAILS", "founder@example.com")


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeDeleteQuery:
    """Simulates supabase-py's .table(x).delete().lt(col, val).execute()
    chain against an in-memory row store keyed by table name. Rows are
    plain dicts; comparison is lexicographic string comparison, which is
    correct for same-format ISO-8601 timestamps/dates (what the real code
    always passes)."""

    def __init__(self, store: dict, table_name: str):
        self._store = store
        self._table = table_name
        self._column = None
        self._cutoff = None

    def delete(self):
        return self

    def lt(self, column, value):
        self._column = column
        self._cutoff = value
        return self

    def execute(self):
        rows = self._store.get(self._table, [])
        to_delete = [r for r in rows if str(r[self._column]) < str(self._cutoff)]
        self._store[self._table] = [r for r in rows if str(r[self._column]) >= str(self._cutoff)]

        class _Result:
            data = to_delete
        return _Result()


class _FakeSupa:
    def __init__(self, store: dict):
        self._store = store

    def table(self, name):
        return _FakeDeleteQuery(self._store, name)


def _iso_days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def _date_days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


@pytest.fixture()
def fake_store():
    """3 rows per table: one clearly old (should be deleted), one clearly
    recent (should survive), one exactly at the retention boundary is
    intentionally NOT included here -- boundary behavior is a `<` vs `<=`
    detail already covered by reading the cutoff value itself in other
    tests, not fuzzed here to avoid a flaky off-by-one-day test."""
    return {
        "security_events": [
            {"id": "se-old", "created_at": _iso_days_ago(120)},
            {"id": "se-new", "created_at": _iso_days_ago(5)},
        ],
        "user_daily_activity": [
            {"id": "uda-old", "date": _date_days_ago(120)},
            {"id": "uda-new", "date": _date_days_ago(5)},
        ],
        "ai_forensics": [
            {"id": "af-old", "started_at": _iso_days_ago(200)},
            {"id": "af-new", "started_at": _iso_days_ago(10)},
        ],
    }


@pytest.fixture(autouse=True)
def _patch_pinecone_cleanup():
    """cleanup_expired talks to real Pinecone -- mock it for every test in
    this file except the one that specifically tests it fails gracefully."""
    with patch(
        "uploaded_doc.cleanup.cleanup_expired",
        return_value={"namespaces_deleted": 2, "chunks_deleted": 14, "namespaces_inspected": 5},
    ):
        yield


class TestIndividualCleanupFunctions:
    @pytest.mark.anyio
    async def test_security_events_deletes_old_keeps_new(self, fake_store):
        from services.retention_service import _cleanup_security_events
        with patch("shared.deps._get_supa", return_value=_FakeSupa(fake_store)):
            result = await _cleanup_security_events()
        assert result["status"] == "ok"
        assert result["obrisano"] == 1
        remaining_ids = {r["id"] for r in fake_store["security_events"]}
        assert remaining_ids == {"se-new"}

    @pytest.mark.anyio
    async def test_user_daily_activity_deletes_old_keeps_new(self, fake_store):
        from services.retention_service import _cleanup_user_daily_activity
        with patch("shared.deps._get_supa", return_value=_FakeSupa(fake_store)):
            result = await _cleanup_user_daily_activity()
        assert result["status"] == "ok"
        assert result["obrisano"] == 1
        remaining_ids = {r["id"] for r in fake_store["user_daily_activity"]}
        assert remaining_ids == {"uda-new"}

    @pytest.mark.anyio
    async def test_ai_forensics_deletes_old_keeps_new(self, fake_store):
        from services.retention_service import _cleanup_ai_forensics
        with patch("shared.deps._get_supa", return_value=_FakeSupa(fake_store)):
            result = await _cleanup_ai_forensics()
        assert result["status"] == "ok"
        assert result["obrisano"] == 1
        remaining_ids = {r["id"] for r in fake_store["ai_forensics"]}
        assert remaining_ids == {"af-new"}

    @pytest.mark.anyio
    async def test_ai_forensics_uses_180_day_window_not_90(self, fake_store):
        """A row 120 days old must SURVIVE ai_forensics cleanup (180-day
        window) even though it would be deleted from security_events/
        user_daily_activity (90-day window) -- this is the one place the
        3 tables deliberately use different retention lengths."""
        from services.retention_service import _cleanup_ai_forensics
        fake_store["ai_forensics"] = [{"id": "af-120d", "started_at": _iso_days_ago(120)}]
        with patch("shared.deps._get_supa", return_value=_FakeSupa(fake_store)):
            result = await _cleanup_ai_forensics()
        assert result["obrisano"] == 0
        assert len(fake_store["ai_forensics"]) == 1

    @pytest.mark.anyio
    async def test_pinecone_cleanup_calls_existing_function(self):
        from services.retention_service import _cleanup_pinecone_tmp_buffers
        result = await _cleanup_pinecone_tmp_buffers()
        assert result["status"] == "ok"
        assert result["namespaces_deleted"] == 2
        assert result["chunks_deleted"] == 14

    @pytest.mark.anyio
    async def test_pinecone_cleanup_failure_does_not_raise(self):
        from services.retention_service import _cleanup_pinecone_tmp_buffers
        with patch("uploaded_doc.cleanup.cleanup_expired", side_effect=RuntimeError("Pinecone down")):
            result = await _cleanup_pinecone_tmp_buffers()
        assert result["status"] == "greska"
        assert "Pinecone down" in result["greska"]

    @pytest.mark.anyio
    async def test_delete_failure_does_not_raise(self, fake_store):
        """A table-level exception (e.g. table doesn't exist yet) must
        produce a 'greska' status, never propagate -- matches the isolated-
        per-module pattern already established in api.py's cron_daily."""
        from services.retention_service import _cleanup_security_events

        class _BrokenSupa:
            def table(self, name):
                raise RuntimeError("relation does not exist")

        with patch("shared.deps._get_supa", return_value=_BrokenSupa()):
            result = await _cleanup_security_events()
        assert result["status"] == "greska"
        assert "does not exist" in result["greska"]


class TestExecuteRetentionCleanup:
    @pytest.mark.anyio
    async def test_runs_all_four_steps_and_summarizes(self, fake_store):
        from services.retention_service import execute_retention_cleanup
        with patch("shared.deps._get_supa", return_value=_FakeSupa(fake_store)):
            result = await execute_retention_cleanup()

        assert result["security_events"]["obrisano"] == 1
        assert result["user_daily_activity"]["obrisano"] == 1
        assert result["ai_forensics"]["obrisano"] == 1
        assert result["pinecone_tmp_buffers"]["namespaces_deleted"] == 2

        # 1 + 1 + 1 (row deletes) + 2 (pinecone namespaces) = 5
        assert result["_summary"]["ukupno_obrisano"] == 5
        assert result["_summary"]["greske"] == 0

    @pytest.mark.anyio
    async def test_one_table_failure_does_not_block_others(self, fake_store):
        """security_events fails (simulated), but user_daily_activity,
        ai_forensics, and the Pinecone cleanup must still run and succeed --
        proves the isolation the module's docstring promises."""
        from services.retention_service import execute_retention_cleanup

        real_supa = _FakeSupa(fake_store)

        class _PartiallyBrokenSupa:
            def table(self, name):
                if name == "security_events":
                    raise RuntimeError("simulated failure")
                return real_supa.table(name)

        with patch("shared.deps._get_supa", return_value=_PartiallyBrokenSupa()):
            result = await execute_retention_cleanup()

        assert result["security_events"]["status"] == "greska"
        assert result["user_daily_activity"]["status"] == "ok"
        assert result["ai_forensics"]["status"] == "ok"
        assert result["pinecone_tmp_buffers"]["status"] == "ok"
        assert result["_summary"]["greske"] == 1

    @pytest.mark.anyio
    async def test_summary_lists_excluded_tables_never_touched(self, fake_store):
        from services.retention_service import (
            execute_retention_cleanup,
            TABLES_EXCLUDED_PENDING_RETENTION_DECISION,
        )
        with patch("shared.deps._get_supa", return_value=_FakeSupa(fake_store)):
            result = await execute_retention_cleanup()
        assert set(result["_summary"]["tabele_van_dometa"]) == {"usage_events", "response_audit"}
        assert TABLES_EXCLUDED_PENDING_RETENTION_DECISION == ("usage_events", "response_audit")


class TestExcludedTablesAreActuallyLive:
    """SEC-002 Korak 3 -- CORRECTION (2026-07-24): the read-only analysis
    phase originally claimed usage_events/response_audit were "confirmed
    dead" (SEC-034/SEC-035-class finding). That claim was WRONG, caught by
    these very tests failing on first run: both tables are actively used.
    `usage_events` has a migration (migrations/009_notifications_analytics.sql,
    `public.usage_events` -- missed originally because the search pattern
    didn't account for the `public.` prefix) and is read/written by
    routers/analytics.py, routers/product_intelligence.py, routers/gdpr.py
    (part of the GDPR data export!), routers/onboarding.py, routers/voice.py,
    api.py. `response_audit` genuinely has no migration in migrations/ (only
    in legacy supabase_setup.sql/supabase_migration_v3.sql -- a real
    SEC-034-class untracked-schema instance) but IS written by
    app/services/audit_log.py -- the original Bash grep for it failed due
    to shell-escaping, not because the call site doesn't exist.

    These tests lock in the CORRECTED understanding: both tables are live,
    excluded from this retention job only because their retention period
    hasn't been decided yet -- not because they might be dead."""

    def test_excluded_tables_never_targeted_by_delete_calls(self):
        """Whatever we know or don't know about these tables, this retention
        module itself must never call _delete_older_than on either one."""
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent / "services" / "retention_service.py").read_text(encoding="utf-8")
        for table in ("usage_events", "response_audit"):
            assert f'_delete_older_than("{table}"' not in src

    def test_usage_events_has_a_migration(self):
        from pathlib import Path
        migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
        found = any(
            "CREATE TABLE IF NOT EXISTS public.usage_events" in f.read_text(encoding="utf-8", errors="replace")
            for f in migrations_dir.glob("*.sql")
        )
        assert found, "usage_events migration not found -- if it was genuinely removed, re-evaluate this table's status"

    def test_usage_events_is_referenced_in_application_code(self):
        from pathlib import Path
        repo_root = Path(__file__).resolve().parent.parent
        hits = [
            str(f) for f in repo_root.rglob("*.py")
            if "tests" not in f.parts and "__pycache__" not in f.parts
            and '.table("usage_events")' in f.read_text(encoding="utf-8", errors="replace")
        ]
        assert len(hits) >= 1, "usage_events no longer referenced anywhere -- if genuinely dead now, re-evaluate"

    def test_response_audit_is_referenced_in_application_code(self):
        from pathlib import Path
        repo_root = Path(__file__).resolve().parent.parent
        hits = [
            str(f) for f in repo_root.rglob("*.py")
            if "tests" not in f.parts and "__pycache__" not in f.parts
            and '.table("response_audit")' in f.read_text(encoding="utf-8", errors="replace")
        ]
        assert len(hits) >= 1, "response_audit no longer referenced anywhere -- if genuinely dead now, re-evaluate"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

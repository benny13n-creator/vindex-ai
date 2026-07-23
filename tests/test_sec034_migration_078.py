# -*- coding: utf-8 -*-
"""
SEC-034 — migration 078 structural verification (klijenti + predmet_komentari
RLS policies).

HONEST SCOPE, same as tests/test_sec031_migrations.py and tests/
test_sec034_migration_completeness.py: this does NOT execute the migration
against a real Postgres instance (no Docker/local Postgres/psycopg2 in this
environment). It verifies the migration FILE matches what scripts/
sec034_live_completeness_check.sql (2026-07-23) found missing in production
and what supabase_setup.sql already defines as the source of truth for these
two tables' policies. Live confirmation happens via the read-only query in
this migration's own "VERIFIKACIJA POSLE POKRETANJA" section, run by the
founder after execution.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = REPO_ROOT / "migrations" / "078_sec034_klijenti_komentari_policies.sql"
SETUP_PATH = REPO_ROOT / "supabase_setup.sql"

EXPECTED_POLICIES = {
    ("klijenti", "klijenti_select", "SELECT"),
    ("klijenti", "klijenti_insert", "INSERT"),
    ("klijenti", "klijenti_update", "UPDATE"),
    ("klijenti", "klijenti_delete", "DELETE"),
    ("predmet_komentari", "komentari_select", "SELECT"),
    ("predmet_komentari", "komentari_insert", "INSERT"),
    ("predmet_komentari", "komentari_update", "UPDATE"),
    ("predmet_komentari", "komentari_delete", "DELETE"),
}

POLICY_RE = re.compile(
    r'CREATE POLICY\s+"([^"]+)"\s+ON\s+(?:public\.)?(\w+)\s+FOR\s+(SELECT|INSERT|UPDATE|DELETE)',
    re.IGNORECASE,
)


def _text() -> str:
    assert MIGRATION_PATH.is_file(), f"{MIGRATION_PATH} missing"
    return MIGRATION_PATH.read_text(encoding="utf-8")


class TestMigrationFileExists:
    def test_file_present(self):
        assert MIGRATION_PATH.is_file()


class TestAllEightPoliciesDefined:
    def test_exact_policy_set(self):
        text = _text()
        found = {
            (table.lower(), name, cmd.upper())
            for name, table, cmd in POLICY_RE.findall(text)
        }
        assert found == EXPECTED_POLICIES, (
            f"Mismatch.\nMissing: {EXPECTED_POLICIES - found}\n"
            f"Unexpected: {found - EXPECTED_POLICIES}"
        )

    def test_all_use_owner_scoped_condition(self):
        # Every policy must scope on auth.uid()::text = user_id -- the exact
        # condition supabase_setup.sql uses, not a looser one.
        text = _text()
        blocks = re.findall(
            r'CREATE POLICY\s+"[^"]+"\s+ON\s+(?:public\.)?\w+\s+FOR\s+\w+\s+'
            r'(?:USING|WITH CHECK).*?;',
            text,
            re.IGNORECASE | re.DOTALL,
        )
        assert len(blocks) == 8
        for cond in blocks:
            assert "auth.uid()::text = user_id" in cond.replace("\n", " ")


class TestIdempotentGuards:
    def test_every_policy_wrapped_in_not_exists_guard(self):
        text = _text()
        # Each of the 8 policies must be preceded by a pg_policies existence
        # check within its own DO $$ block -- makes the migration safe to
        # re-run, matching supabase_setup.sql's own idempotent pattern.
        for _table, name, _cmd in EXPECTED_POLICIES:
            pattern = re.compile(
                r"IF NOT EXISTS\s*\(SELECT 1 FROM pg_policies WHERE tablename='(\w+)' "
                rf"AND policyname='{re.escape(name)}'\)",
            )
            assert pattern.search(text), f"Missing idempotent guard for policy {name!r}"


class TestRlsEnableStatementsPresent:
    def test_both_tables_enable_rls(self):
        text = _text()
        assert re.search(r"ALTER TABLE public\.klijenti ENABLE ROW LEVEL SECURITY", text)
        assert re.search(r"ALTER TABLE public\.predmet_komentari ENABLE ROW LEVEL SECURITY", text)


class TestMatchesSupabaseSetupSource:
    """The migration must be a faithful copy of supabase_setup.sql's own
    definitions for these two tables -- not a reinterpretation."""

    def test_source_file_still_defines_same_policies(self):
        assert SETUP_PATH.is_file()
        setup_text = SETUP_PATH.read_text(encoding="utf-8", errors="replace")
        found = {
            (table.lower(), name, cmd.upper())
            for name, table, cmd in POLICY_RE.findall(setup_text)
            if table.lower() in ("klijenti", "predmet_komentari")
        }
        assert found == EXPECTED_POLICIES, (
            "supabase_setup.sql's own klijenti/predmet_komentari policies "
            f"changed since migration 078 was written. Found: {found}"
        )


class TestNoAuthUsersOrFkTouched:
    """This migration is policy-only -- it must not touch any FK or CASCADE/
    RESTRICT rule, staying out of SEC-031's territory entirely."""

    def test_no_foreign_key_ddl(self):
        text = _text().upper()
        assert "REFERENCES" not in text
        assert "DROP CONSTRAINT" not in text
        assert "ADD CONSTRAINT" not in text


class TestSingleTransaction:
    def test_wrapped_in_begin_commit(self):
        text = _text()
        assert re.search(r"^\s*BEGIN;", text, re.MULTILINE)
        assert re.search(r"^\s*COMMIT;", text, re.MULTILINE)


class TestRollbackDocumented:
    def test_rollback_section_present_and_commented_out(self):
        text = _text()
        assert "ROLLBACK" in text.upper()
        for policy in ("klijenti_select", "klijenti_insert", "klijenti_update", "klijenti_delete",
                       "komentari_select", "komentari_insert", "komentari_update", "komentari_delete"):
            assert f'DROP POLICY IF EXISTS "{policy}"' in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

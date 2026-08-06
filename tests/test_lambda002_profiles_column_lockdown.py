# -*- coding: utf-8 -*-
"""
Program Lambda, Certification 002 (2026-08-06) -- addendum. The Database & RLS
Auditor fork found that public.profiles' own UPDATE RLS policy
(supabase_setup.sql:38-41, `USING (auth.uid() = id)`, no WITH CHECK) restricts
which ROW a user may update but not which COLUMNS -- so any authenticated user
can set is_pro/plan/trial_kraj on their own row directly from the browser
(static/vindex.js holds a public anon key and talks to Supabase directly),
a free permanent PRO escalation with zero backend involvement. This finding
was reported by that fork but never closed by the sprint's own final triage
pass (migration 102 fixed 5 unrelated RPC-privilege bugs; this one was missed
until manual re-review caught the gap between what was found and what shipped).

The fix is a SQL column-level GRANT (migrations/103_lambda002_profiles_column_lockdown.sql),
not Python code -- same as migration 102, this codebase's standing rule is that
migrations are never auto-run, the founder always runs them himself. This test
is a static regression guard: it proves the migration file exists and actually
locks UPDATE down to full_name only, so a future edit can't silently drop the
fix before the founder has a chance to apply it.
"""
import os

_MIGRATION_PATH = os.path.join(
    os.path.dirname(__file__), "..", "migrations", "103_lambda002_profiles_column_lockdown.sql"
)


def _read_migration() -> str:
    with open(_MIGRATION_PATH, encoding="utf-8") as f:
        return f.read()


def test_migration_file_exists():
    assert os.path.isfile(_MIGRATION_PATH), (
        "migrations/103_lambda002_profiles_column_lockdown.sql must exist -- "
        "the fix for the confirmed profiles UPDATE column-privilege bypass."
    )


def test_authenticated_and_anon_update_grant_is_revoked():
    sql = _read_migration()
    assert "REVOKE UPDATE ON public.profiles FROM authenticated;" in sql
    assert "REVOKE UPDATE ON public.profiles FROM anon;" in sql


def test_authenticated_regains_only_full_name_column():
    sql = _read_migration()
    assert "GRANT UPDATE (full_name) ON public.profiles TO authenticated;" in sql
    # The privileged columns must never appear inside any GRANT UPDATE(...) column list.
    for col in ("is_pro", "plan", "trial_kraj", "onboarding_done"):
        assert f"GRANT UPDATE ({col})" not in sql, f"{col} must never be directly writable by authenticated"
        assert f"full_name, {col}" not in sql and f"{col}, full_name" not in sql, (
            f"{col} must not be smuggled into the same GRANT UPDATE(...) list as full_name"
        )


def test_service_role_keeps_full_access():
    sql = _read_migration()
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON public.profiles TO service_role;" in sql

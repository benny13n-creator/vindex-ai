# -*- coding: utf-8 -*-
"""
Program Lambda, Certification 002 (2026-08-06) -- Database & RLS Auditor fork
found deduct_credit() and set_user_pro() as SECURITY DEFINER RPC functions
callable directly via PostgREST by any authenticated user, with no ownership
check inside the function body -- a cross-account credit-drain DoS and a free
PRO monetary escalation, both entirely independent of the FastAPI backend.

The fix is a SQL privilege change (migrations/102_lambda002_rpc_ownership_lockdown.sql),
not Python code -- this codebase's own standing rule is that migrations are
never auto-run, the founder always runs them himself. This test is therefore a
static regression guard: it proves the migration file exists and actually
contains a REVOKE-from-PUBLIC/anon/authenticated + GRANT-to-service_role-only
statement for every function the audit named, so a future edit can't silently
drop the fix before the founder has a chance to apply it.
"""
import os

_MIGRATION_PATH = os.path.join(
    os.path.dirname(__file__), "..", "migrations", "102_lambda002_rpc_ownership_lockdown.sql"
)

_FUNCTIONS = [
    ("public.deduct_credit(UUID)", "user_credits"),
    ("public.set_user_pro(TEXT, BOOLEAN)", "profiles"),
    ("public.deduct_n_credits(UUID, INTEGER)", "user_credits"),
    ("public.get_activity_averages(UUID)", "user_daily_activity"),
    ("public.get_next_broj_fakture(UUID)", "fakture"),
]


def _read_migration() -> str:
    with open(_MIGRATION_PATH, encoding="utf-8") as f:
        return f.read()


def test_migration_file_exists():
    assert os.path.isfile(_MIGRATION_PATH), (
        "migrations/102_lambda002_rpc_ownership_lockdown.sql must exist -- "
        "the fix for the confirmed deduct_credit/set_user_pro RPC ownership bypass."
    )


def test_every_flagged_function_is_revoked_from_public_anon_authenticated():
    sql = _read_migration()
    for fn_sig, _table in _FUNCTIONS:
        assert f"REVOKE ALL ON FUNCTION {fn_sig} FROM PUBLIC;" in sql, f"{fn_sig} missing REVOKE FROM PUBLIC"
        assert f"REVOKE ALL ON FUNCTION {fn_sig} FROM anon;" in sql, f"{fn_sig} missing REVOKE FROM anon"
        assert f"REVOKE ALL ON FUNCTION {fn_sig} FROM authenticated;" in sql, f"{fn_sig} missing REVOKE FROM authenticated"


def test_every_flagged_function_still_grants_service_role():
    """The backend itself must keep working -- every one of these RPCs is
    called by shared/deps.py's service-role client, which must still be
    able to execute them after the lockdown."""
    sql = _read_migration()
    for fn_sig, _table in _FUNCTIONS:
        assert f"GRANT EXECUTE ON FUNCTION {fn_sig} TO service_role;" in sql, f"{fn_sig} missing GRANT TO service_role"


def test_deduct_credit_previous_authenticated_grant_is_being_revoked_not_just_ignored():
    """deduct_credit was the one function with an EXPLICIT, confirmed-live
    GRANT ... TO authenticated (supabase_setup.sql:148) -- the migration must
    revoke authenticated specifically, not just rely on a PUBLIC revoke that
    an explicit prior GRANT could otherwise still override in some Postgres
    versions/orderings. Belt-and-suspenders, matching the migration's own
    explicit per-role REVOKE statements."""
    sql = _read_migration()
    assert "REVOKE ALL ON FUNCTION public.deduct_credit(UUID) FROM authenticated;" in sql

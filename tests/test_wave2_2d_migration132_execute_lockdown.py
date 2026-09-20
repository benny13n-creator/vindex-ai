# -*- coding: utf-8 -*-
"""
VINDEX AI V1, Wave 2, Task 2D -- P0 authorization hotfix regression
(migration 132).

PROVEN PRODUCTION DEFECT (2026-09-20): after migration 130 applied,
`information_schema.routine_privileges` showed EXECUTE granted to `anon`
and `authenticated` -- not just `service_role` -- on all 3 new SECURITY
DEFINER source-invalidation RPCs. Migration 130's own
`REVOKE ALL ... FROM PUBLIC` never touched those grants: `PUBLIC` and a
named role like `anon`/`authenticated` are different grantees in
Postgres: revoking from `PUBLIC` does not revoke a grant made directly to
a named role.

This test does not connect to any database -- it proves, from migration
131's own SQL text, that the fix actually covers all 3 functions and all
4 required statements (REVOKE FROM PUBLIC, REVOKE FROM anon, REVOKE FROM
authenticated, GRANT TO service_role) per function, so this exact class
of gap cannot silently reappear in a future migration without this test
catching it. Live production privilege confirmation is a separate,
already-completed step (this session's own emergency mitigation +
production catalog queries), not something a local test can prove.
"""
import os

MIGRATION_PATH = os.path.join(
    os.path.dirname(__file__), "..", "migrations",
    "132_lock_down_source_invalidation_rpc_execute.sql",
)

FUNCTIONS = (
    ("invalidate_dokaz_and_emit_event", "(TEXT, TEXT, UUID, TEXT)"),
    ("invalidate_rociste_and_emit_event", "(TEXT, TEXT, UUID, TEXT)"),
    ("invalidate_dokument_relational_and_emit_event", "(TEXT, TEXT, TEXT, UUID, TEXT)"),
)


def _read_migration_131() -> str:
    with open(MIGRATION_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _code_only(sql: str) -> str:
    """Strip `-- ...` comment lines so prose (which may quote SQL
    fragments while explaining the incident) can't produce a false
    positive for any of the checks below."""
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


def test_migration_131_file_exists():
    assert os.path.exists(MIGRATION_PATH), "migrations/132_lock_down_source_invalidation_rpc_execute.sql is missing"


def test_every_function_has_all_four_required_privilege_statements():
    sql = _code_only(_read_migration_131())

    for fn_name, fn_sig in FUNCTIONS:
        fq = f"public.{fn_name}{fn_sig}"

        revoke_stmt = f"REVOKE EXECUTE ON FUNCTION {fq}"
        assert revoke_stmt in sql, f"{fn_name}: missing REVOKE EXECUTE statement with exact signature {fn_sig}"

        # Find the REVOKE statement's own FROM clause (up to the
        # terminating semicolon) and require it name all 3 grantees --
        # a single combined "FROM PUBLIC, anon, authenticated" satisfies
        # this, matching how migration 132 is actually written.
        revoke_start = sql.index(revoke_stmt)
        revoke_end = sql.index(";", revoke_start)
        revoke_clause = sql[revoke_start:revoke_end]
        assert "PUBLIC" in revoke_clause, f"{fn_name}: REVOKE does not cover PUBLIC"
        assert "anon" in revoke_clause, f"{fn_name}: REVOKE does not cover anon -- the exact class of gap this hotfix exists to close"
        assert "authenticated" in revoke_clause, f"{fn_name}: REVOKE does not cover authenticated -- the exact class of gap this hotfix exists to close"

        grant_stmt = f"GRANT EXECUTE ON FUNCTION {fq}"
        assert grant_stmt in sql, f"{fn_name}: missing GRANT EXECUTE statement with exact signature {fn_sig}"
        grant_start = sql.index(grant_stmt)
        grant_end = sql.index(";", grant_start)
        grant_clause = sql[grant_start:grant_end]
        assert "service_role" in grant_clause, f"{fn_name}: GRANT does not target service_role"


def test_migration_does_not_touch_function_bodies_or_security_properties():
    """Scope guard: this hotfix must be privilege-only. If a future edit
    to this file accidentally reintroduces CREATE FUNCTION, SECURITY
    DEFINER, or search_path changes, that's scope creep this test
    catches immediately."""
    sql = _code_only(_read_migration_131())
    assert "CREATE FUNCTION" not in sql
    assert "CREATE OR REPLACE FUNCTION" not in sql
    assert "SECURITY DEFINER" not in sql
    assert "search_path" not in sql
    assert "ALTER DEFAULT PRIVILEGES" not in sql
    assert "DELETE FROM" not in sql
    assert "UPDATE " not in sql
    assert "INSERT INTO" not in sql
    assert "DROP " not in sql


def test_migration_contains_no_dynamic_sql():
    sql = _code_only(_read_migration_131())
    assert "EXECUTE format(" not in sql
    assert "EXECUTE '" not in sql
    assert "format(" not in sql
    assert "||" not in sql


def test_migration_targets_exactly_the_three_proven_functions_no_more_no_less():
    sql = _code_only(_read_migration_131())
    n_revoke = sql.count("REVOKE EXECUTE ON FUNCTION")
    n_grant = sql.count("GRANT EXECUTE ON FUNCTION")
    assert n_revoke == 3, f"expected exactly 3 REVOKE EXECUTE statements, found {n_revoke}"
    assert n_grant == 3, f"expected exactly 3 GRANT EXECUTE statements, found {n_grant}"

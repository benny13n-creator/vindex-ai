# -*- coding: utf-8 -*-
"""
VINDEX AI V1, Wave 2, P0/P1 production defect fix regression (migration 133).

PROVEN PRODUCTION DEFECT (2026-09-20, live canary against release
f7945040): DELETE /api/evidence/predmeti/{id}/dokaz/{id} returned HTTP 500
three times, deterministically. Direct probing of
invalidate_dokaz_and_emit_event(text,text,uuid,text) confirmed:

    ERROR 42883: operator does not exist: uuid = text
    WHERE pd.id = p_dokaz_id AND pd.user_id = p_user_id

predmet_dokazi.id/user_id/predmet_id are `uuid` columns; migration 131
declared the corresponding RPC parameters TEXT. Postgres has no
`uuid = text` equality operator, so every call failed at query-plan time
-- the same structural defect existed in all 3 atomic invalidation RPCs
migration 131 introduced (rocista, predmet_dokumenti are also uuid-keyed).

This test file does not connect to any database -- it proves, from
migration 133's own SQL text, that: the new signatures are UUID-typed on
every identity parameter; the exact old TEXT signatures are dropped (not
just superseded); the fully-hardened authorization lockdown applies to the
new signatures directly (no repeat of migration 131 -> 132's two-step
exposure window); and the atomic mutation+event-insert contract is
unchanged. Live production re-verification (the RPC actually succeeding
end to end) is a separate, already-planned step this local test cannot
prove.
"""
import os

MIGRATION_PATH = os.path.join(
    os.path.dirname(__file__), "..", "migrations",
    "133_fix_source_invalidation_rpc_uuid_contract.sql",
)

OLD_SIGNATURES = (
    ("invalidate_dokaz_and_emit_event", "(TEXT, TEXT, UUID, TEXT)"),
    ("invalidate_rociste_and_emit_event", "(TEXT, TEXT, UUID, TEXT)"),
    ("invalidate_dokument_relational_and_emit_event", "(TEXT, TEXT, TEXT, UUID, TEXT)"),
)

NEW_SIGNATURES = (
    ("invalidate_dokaz_and_emit_event", "(UUID, UUID, UUID, TEXT)"),
    ("invalidate_rociste_and_emit_event", "(UUID, UUID, UUID, TEXT)"),
    ("invalidate_dokument_relational_and_emit_event", "(UUID, UUID, UUID, UUID, TEXT)"),
)


def _read_migration_133() -> str:
    with open(MIGRATION_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _code_only(sql: str) -> str:
    """Strip `-- ...` comment lines so prose explaining the incident (which
    necessarily quotes old/new signatures and SQL fragments) can't produce
    a false positive for any of the checks below."""
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


def test_migration_133_file_exists():
    assert os.path.exists(MIGRATION_PATH), "migrations/133_fix_source_invalidation_rpc_uuid_contract.sql is missing"


def test_every_function_declares_uuid_for_every_identity_parameter():
    """Requirement 1: UUID parameters for all UUID identifiers. Checks the
    CREATE OR REPLACE FUNCTION signature itself (not prose), for each of
    the 3 functions, that every identity parameter (dokaz/rociste/
    dokument/predmet/user id, whichever apply) is declared UUID and
    p_event_id remains UUID -- only p_correlation_id stays TEXT."""
    sql = _code_only(_read_migration_133())

    create_dokaz = "CREATE OR REPLACE FUNCTION public.invalidate_dokaz_and_emit_event(\n    p_dokaz_id       UUID,\n    p_user_id        UUID,\n    p_event_id       UUID,\n    p_correlation_id TEXT DEFAULT NULL\n)"
    assert create_dokaz in sql, "invalidate_dokaz_and_emit_event: identity parameters are not declared UUID"

    create_rociste = "CREATE OR REPLACE FUNCTION public.invalidate_rociste_and_emit_event(\n    p_rociste_id     UUID,\n    p_user_id        UUID,\n    p_event_id       UUID,\n    p_correlation_id TEXT DEFAULT NULL\n)"
    assert create_rociste in sql, "invalidate_rociste_and_emit_event: identity parameters are not declared UUID"

    create_dokument = "CREATE OR REPLACE FUNCTION public.invalidate_dokument_relational_and_emit_event(\n    p_dokument_id    UUID,\n    p_predmet_id     UUID,\n    p_user_id        UUID,\n    p_event_id       UUID,\n    p_correlation_id TEXT DEFAULT NULL\n)"
    assert create_dokument in sql, "invalidate_dokument_relational_and_emit_event: identity parameters are not declared UUID"


def test_where_clause_columns_are_compared_against_uuid_typed_parameters():
    """Directly targets the proven failure: the WHERE/DELETE predicate
    columns (all uuid in production) must be compared against a parameter
    that is now declared UUID, not TEXT. Re-derives each parameter's
    declared type from the function signature and checks it against the
    exact predicate this defect broke."""
    sql = _code_only(_read_migration_133())

    assert "WHERE pd.id = p_dokaz_id\n          AND pd.user_id = p_user_id" in sql
    assert "WHERE r.id = p_rociste_id\n          AND r.user_id = p_user_id" in sql
    assert "WHERE pdoc.id = p_dokument_id\n          AND pdoc.predmet_id = p_predmet_id\n          AND pdoc.user_id = p_user_id" in sql
    # Combined with test_every_function_declares_uuid_for_every_identity_parameter
    # above (which proves p_dokaz_id/p_user_id/p_rociste_id/p_dokument_id/
    # p_predmet_id are all declared UUID in these exact functions), this
    # proves the WHERE-clause comparison that produced "operator does not
    # exist: uuid = text" now compares uuid = uuid.


def test_obsolete_text_signatures_are_explicitly_dropped():
    """Requirement 2: obsolete TEXT signatures explicitly removed, not
    merely superseded. CREATE OR REPLACE cannot change argument types in
    place -- a UUID-typed CREATE creates a new, separate overload and
    leaves the old TEXT-typed one live unless a DROP explicitly targets
    its exact old signature."""
    sql = _code_only(_read_migration_133())
    for fn_name, old_sig in OLD_SIGNATURES:
        drop_stmt = f"DROP FUNCTION IF EXISTS public.{fn_name}{old_sig}"
        assert drop_stmt in sql, f"{fn_name}: old TEXT signature {old_sig} is not explicitly dropped -- leaves a dead SECURITY DEFINER overload live and risks PostgREST overload-resolution ambiguity"


def test_authorization_lockdown_applies_to_new_uuid_signatures_only():
    """Requirement 3: anon=false, authenticated=false, service_role=true
    for the NEW UUID signatures specifically (not the old, now-dropped
    ones) -- applied directly, not left for a follow-up hotfix migration
    the way 131 -> 132 was."""
    sql = _code_only(_read_migration_133())

    for fn_name, new_sig in NEW_SIGNATURES:
        fq = f"public.{fn_name}{new_sig}"

        revoke_stmt = f"REVOKE EXECUTE ON FUNCTION {fq}"
        assert revoke_stmt in sql, f"{fn_name}: missing REVOKE EXECUTE on the new UUID signature {new_sig}"
        revoke_start = sql.index(revoke_stmt)
        revoke_end = sql.index(";", revoke_start)
        revoke_clause = sql[revoke_start:revoke_end]
        assert "PUBLIC" in revoke_clause, f"{fn_name}: REVOKE does not cover PUBLIC"
        assert "anon" in revoke_clause, f"{fn_name}: REVOKE does not cover anon"
        assert "authenticated" in revoke_clause, f"{fn_name}: REVOKE does not cover authenticated"

        grant_stmt = f"GRANT EXECUTE ON FUNCTION {fq}"
        assert grant_stmt in sql, f"{fn_name}: missing GRANT EXECUTE on the new UUID signature {new_sig}"
        grant_start = sql.index(grant_stmt)
        grant_end = sql.index(";", grant_start)
        grant_clause = sql[grant_start:grant_end]
        assert "service_role" in grant_clause, f"{fn_name}: GRANT does not target service_role"


def test_no_grant_or_revoke_targets_the_old_text_signatures():
    """A grant/revoke accidentally left pointed at the old (now-dropped)
    TEXT signature would be dead SQL at best and a sign the migration
    author didn't actually update every reference at worst."""
    sql = _code_only(_read_migration_133())
    for fn_name, old_sig in OLD_SIGNATURES:
        old_fq = f"public.{fn_name}{old_sig}"
        for stmt_prefix in ("REVOKE EXECUTE ON FUNCTION ", "GRANT EXECUTE ON FUNCTION "):
            assert f"{stmt_prefix}{old_fq}" not in sql, f"{fn_name}: a GRANT/REVOKE still targets the dropped old signature {old_sig}"


def test_atomic_mutation_and_event_insert_still_share_one_function_body():
    """Requirement 4: the SQL contract (mutation + SourceInvalidated
    insert in one function, one implicit transaction) migration 131
    established is unchanged by this type fix."""
    sql = _code_only(_read_migration_133())

    assert sql.count("INSERT INTO public.events") == 3
    assert sql.count("'SourceInvalidated'") == 3
    assert sql.count("ON CONFLICT (id) DO NOTHING") == 3
    assert "UPDATE public.predmet_dokazi" in sql
    assert "DELETE FROM public.rocista" in sql
    assert "DELETE FROM public.predmet_dokumenti" in sql
    # Each function's UPDATE/DELETE and its own INSERT INTO events must be
    # inside the SAME CREATE OR REPLACE FUNCTION ... AS $$ ... $$ body --
    # approximated here by requiring exactly 3 function bodies (3 opening
    # $$ ... 3 closing $$ pairs) and exactly 3 mutation statements, ruling
    # out the insert having been hoisted out to a separate statement.
    assert sql.count("$$;") == 3
    assert sql.count("SECURITY DEFINER") == 3
    assert sql.count("SET search_path = ''") == 3


def test_correlation_id_parameter_is_unchanged_text():
    """p_correlation_id is never compared against a uuid column (only
    stored/returned as free text into events.correlation_id, itself a
    text column) -- must stay TEXT, not be swept into the UUID fix."""
    sql = _code_only(_read_migration_133())
    assert sql.count("p_correlation_id TEXT DEFAULT NULL") == 3


def test_return_contract_unchanged_from_migration_131():
    """Preserving existing return contract semantics: RETURNS TABLE shape
    for each function is byte-identical to migration 131 -- callers
    (services/event_bus.py) read `predmet_id`/`invalidated` fields whose
    Python-visible shape must not change."""
    sql = _code_only(_read_migration_133())
    assert "RETURNS TABLE(predmet_id TEXT, invalidated BOOLEAN)" in sql
    assert sql.count("RETURNS TABLE(predmet_id TEXT, invalidated BOOLEAN)") == 2
    assert "RETURNS TABLE(invalidated BOOLEAN)" in sql


def test_migration_contains_no_dynamic_sql():
    sql = _code_only(_read_migration_133())
    assert "EXECUTE format(" not in sql
    assert "EXECUTE '" not in sql
    assert "format(" not in sql
    assert "||" not in sql

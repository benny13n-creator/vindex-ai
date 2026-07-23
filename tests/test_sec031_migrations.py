# -*- coding: utf-8 -*-
"""
SEC-031 — migration file structural verification (v2, name-agnostic).

HONEST SCOPE, stated up front: this test suite does NOT execute the
migration against a real Postgres instance. This development environment
has no Docker, no local Postgres, and no psycopg2 (verified directly, not
assumed) — there is no way to genuinely "spin up the schema and confirm it
migrates without errors or data loss" from here.

REVISION NOTE (v1 -> v4):
  v1: hardcoded constraint names (`<table>_<column>_fkey`). Failed on the
      first real production run — `predmet_delegiranja_od_user_id_fkey`
      did not exist. Failed safely: GRUPA 1's transaction rolled back
      cleanly, zero data touched.
  v2: replaced hardcoded names with `_sec031_fix_fk(table, column, rule)`,
      a plpgsql function that looks up the actual constraint name via
      `pg_constraint` instead of assuming a naming convention.
  v3: a production diagnostic (read-only, run by the founder) revealed the
      real cause was deeper than naming — 3 of the original 19 approved
      pairs (4 constraints) didn't exist in production at all:
      `predmet_delegiranja` (table itself never migrated, per migration
      054's own header comment), `conversations` (legacy file, apparently
      never run), and `tos_acceptances` (unexplained at the time). Removed
      from the active migration (down to 15 pairs), documented in an
      "ODLOZENO" section rather than silently dropped.
  v4 (current): migrations 054 and 056 were run in production, so
      `predmet_delegiranja` and `tos_acceptances` now exist — their pairs
      are back in the active migration (18 pairs total). `conversations`
      remains PERMANENTLY excluded — confirmed zero call sites in current
      code (superseded by `predmet_istorija` long ago) — this is a
      deliberate, documented exclusion now, not a pending investigation.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = REPO_ROOT / "migrations" / "077_sec031_restrict_auth_users_cascade.sql"

# The 18 (table, column) pairs CONFIRMED LIVE in production and included in
# this migration's active run, as of v4 (2026-07-23) — after migrations 054
# (predmet_delegiranja) and 056 (tos_acceptances) were run in production.
EXPECTED_TIER_A_PAIRS: set[tuple[str, str]] = {
    ("predmeti", "user_id"),
    ("predmet_dokumenti", "user_id"),
    ("predmet_hronologija", "user_id"),
    ("predmet_beleske", "user_id"),
    ("predmet_istorija", "user_id"),
    ("predmet_delegiranja", "od_user_id"),
    ("predmet_delegiranja", "na_user_id"),
    ("fakture", "user_id"),
    ("billing_entries", "user_id"),
    ("timer_sessions", "user_id"),
    ("tarife", "user_id"),
    ("tarifne_stavke_custom", "user_id"),
    ("sef_log", "user_id"),
    ("praceni_predmeti", "user_id"),
    ("rocista", "user_id"),
    ("smart_contract_analyses", "user_id"),
    ("tos_acceptances", "user_id"),
    ("user_knowledge", "user_id"),
}

# PERMANENTLY excluded — not a pending investigation. `conversations` is
# defined only in a legacy root-level file (supabase_migration.sql) that was
# never run against production, and has zero call sites in current
# application code (chat/Q&A persistence moved to `predmet_istorija` long
# ago, confirmed in SEC031_FK_GRAPH.md). There is nothing to protect and no
# reason to resurrect a dead table just to bring it under this migration.
DEFERRED_PAIRS: set[tuple[str, str]] = {
    ("conversations", "user_id"),
}

_CALL_PATTERN = re.compile(
    r"_sec031_fix_fk\(\s*'(\w+)'\s*,\s*'(\w+)'\s*,\s*'(RESTRICT|CASCADE)'\s*\)"
)


def _strip_sql_comments(sql: str) -> str:
    return "\n".join(
        line for line in sql.split("\n")
        if not line.strip().startswith("--")
    )


def _full_sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _active_sql() -> str:
    """Everything up to (not including) the commented-out ROLLBACK block."""
    full = _full_sql()
    return _strip_sql_comments(full.split("-- BEGIN;\n-- SELECT _sec031_fix_fk")[0])


def _rollback_sql() -> str:
    """The commented-out rollback section, uncommented for parsing."""
    full = _full_sql()
    marker = "-- BEGIN;\n-- SELECT _sec031_fix_fk"
    if marker not in full:
        return ""
    rollback_raw = marker[3:] + full.split(marker)[1]  # keep the leading 'BEGIN;...'
    lines = []
    for line in rollback_raw.split("\n"):
        stripped = line.strip()
        if stripped.startswith("-- "):
            lines.append(stripped[3:])
        elif stripped.startswith("--"):
            lines.append(stripped[2:])
        else:
            lines.append(line)
    return "\n".join(lines)


def _extract_calls(sql: str, rule: str) -> set[tuple[str, str]]:
    return {(t, c) for t, c, r in _CALL_PATTERN.findall(sql) if r == rule}


class TestMigrationFileExists:
    def test_migration_file_exists(self):
        assert MIGRATION_PATH.exists(), f"Expected {MIGRATION_PATH} not found."


class TestHelperFunctionIsNameAgnostic:
    """Verifies _sec031_fix_fk itself — the one place the find-drop-add-
    validate logic lives — does NOT hardcode a constraint name anywhere,
    and does look up the real one via pg_constraint before acting."""

    def test_function_looks_up_constraint_via_pg_constraint(self):
        full = _full_sql()
        assert "pg_constraint" in full
        assert "confrelid = 'auth.users'::regclass" in full

    def test_function_raises_on_missing_constraint_rather_than_silently_skipping(self):
        full = _full_sql()
        assert "RAISE EXCEPTION" in full

    def test_function_uses_not_valid_then_validate_pattern(self):
        full = _full_sql()
        assert "NOT VALID" in full
        assert "VALIDATE CONSTRAINT" in full

    def test_no_hardcoded_fkey_suffix_naming_assumption(self):
        """v1's bug: assuming every constraint is named '<table>_<column>_fkey'.
        v2 must not reintroduce that assumption anywhere in the active SQL."""
        active = _active_sql()
        assert not re.search(r"DROP CONSTRAINT \w+_fkey", active), (
            "Found a hardcoded '<name>_fkey' DROP CONSTRAINT — this is exactly "
            "the assumption that failed against real production data."
        )


class TestMigrationMatchesApprovedPlan:
    def test_active_calls_match_approved_tier_a_exactly(self):
        active = _active_sql()
        found = _extract_calls(active, "RESTRICT")
        missing = EXPECTED_TIER_A_PAIRS - found
        extra = found - EXPECTED_TIER_A_PAIRS
        assert not missing, f"Migration is missing confirmed-live pairs: {missing}"
        assert not extra, f"Migration calls _sec031_fix_fk for pairs NOT in the confirmed-live set: {extra}"
        assert len(found) == 18, f"Expected exactly 18 RESTRICT calls, found {len(found)}"

    def test_no_cascade_calls_in_active_migration(self):
        active = _active_sql()
        assert not _extract_calls(active, "CASCADE"), (
            "Active (forward) migration section calls _sec031_fix_fk with CASCADE — "
            "should only appear in the rollback section"
        )

    def test_deferred_pairs_are_not_in_active_migration(self):
        """`conversations` (the one permanently-excluded pair, a dead legacy
        table) must NOT appear as an active _sec031_fix_fk() call. If it
        starts appearing here, it means someone tried to resurrect it
        without re-confirming it's actually needed and actually exists."""
        active = _active_sql()
        active_pairs = _extract_calls(active, "RESTRICT") | _extract_calls(active, "CASCADE")
        overlap = active_pairs & DEFERRED_PAIRS
        assert not overlap, (
            f"Permanently-excluded pair(s) {overlap} found in the ACTIVE migration — "
            f"these were removed because the table doesn't exist and isn't used; "
            f"re-confirm before reintroducing them."
        )

    def test_deferred_pairs_are_documented_in_the_file(self):
        """`conversations` must still be mentioned in the file's ODLOZENO
        section so the exclusion reasoning isn't silently lost. The other
        two tables from earlier revisions (predmet_delegiranja,
        tos_acceptances) are now ACTIVE, not deferred, but still expected
        to appear in the file (in the active SS section) — this assertion
        just confirms they weren't accidentally deleted from the file
        entirely during the v3->v4 edit."""
        full = _full_sql()
        assert "ODLOZENO" in full or "ODLOŽENO" in full
        assert "predmet_delegiranja" in full
        assert "conversations" in full
        assert "tos_acceptances" in full


class TestNoDataMutation:
    @pytest.mark.parametrize("forbidden", ["INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE", "DROP TABLE"])
    def test_no_row_mutating_statements(self, forbidden):
        active = _active_sql().upper()
        assert forbidden.upper() not in active, (
            f"Found a data-mutating statement ({forbidden!r}) in the active migration"
        )


class TestRollbackIsComplete:
    def test_rollback_section_exists(self):
        assert "ROLLBACK" in _full_sql().upper()

    def test_rollback_restores_cascade_for_all_18_active_pairs(self):
        rollback = _rollback_sql()
        cascade_pairs = _extract_calls(rollback, "CASCADE")
        missing = EXPECTED_TIER_A_PAIRS - cascade_pairs
        assert not missing, f"Rollback section missing CASCADE restoration for: {missing}"
        assert len(cascade_pairs) == 18

    def test_rollback_drops_the_helper_function(self):
        """Cleanup — the helper function shouldn't linger in the schema
        forever once rollback is complete."""
        full = _full_sql()
        rollback_area = full.split("ROLLBACK")[-1]
        assert "DROP FUNCTION" in rollback_area


class TestTransactionSplitting:
    def test_forward_migration_uses_multiple_transactions(self):
        active = _active_sql()
        begin_count = len(re.findall(r"^BEGIN;", active, re.MULTILINE))
        commit_count = len(re.findall(r"^COMMIT;", active, re.MULTILINE))
        assert begin_count == commit_count, "Unbalanced BEGIN/COMMIT pairs"
        assert begin_count >= 2, f"Expected 2+ transactions, found {begin_count}"

    def test_no_transaction_contains_all_18_pairs(self):
        active = _active_sql()
        blocks = re.findall(r"BEGIN;(.*?)COMMIT;", active, re.DOTALL)
        assert blocks, "No BEGIN...COMMIT blocks found"
        for block in blocks:
            pairs_in_block = _extract_calls(block, "RESTRICT")
            assert len(pairs_in_block) < 18, "Found a transaction containing all 18 pairs — split is not real"


class TestDiagnosticQueryPresent:
    """§0's read-only diagnostic query must exist in the file (commented, for
    manual copy-paste) — this is what should be run before/after each group,
    and is exactly what surfaced the v1 naming failure in the first place."""

    def test_readonly_diagnostic_query_present(self):
        full = _full_sql()
        assert "pg_get_constraintdef" in full
        assert "SELECT" in full

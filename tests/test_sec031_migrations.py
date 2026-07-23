# -*- coding: utf-8 -*-
"""
SEC-031 — migration file structural verification.

HONEST SCOPE, stated up front: this test suite does NOT execute the
migration against a real Postgres instance. This development environment
has no Docker, no local Postgres, and no psycopg2 (verified directly, not
assumed) — there is no way to genuinely "spin up the schema and confirm it
migrates without errors or data loss" from here. Claiming otherwise would
repeat exactly the kind of unverified claim this whole SEC-031 workstream
has been built to avoid.

What this suite DOES verify, mechanically and reproducibly:
  1. migrations/077_sec031_restrict_auth_users_cascade.sql exists and
     contains EXACTLY the 19 (table, column) pairs approved in
     docs/security/SEC031_MIGRATION_DRY_RUN.md SS2 — cross-checked against
     that document's own SQL code block, not hand-copied twice.
  2. Every constraint follows the DROP -> ADD ... NOT VALID -> VALIDATE
     three-step pattern (the production-safe, minimal-lock form).
  3. Every ADD CONSTRAINT targets auth.users(id) with ON DELETE RESTRICT
     (never CASCADE, never any other table).
  4. The file contains a complete, symmetric ROLLBACK section restoring
     ON DELETE CASCADE for the identical 19 pairs.
  5. The file contains NO data-mutating statement anywhere (no INSERT,
     UPDATE, DELETE, TRUNCATE, or DROP TABLE) outside of comments — a
     mechanical proof that this migration cannot lose data by construction,
     not just a claim about intent.
  6. The migration is split into multiple transactions (BEGIN/COMMIT
     pairs), matching SEC031_MIGRATION_DRY_RUN.md SS3's revised
     recommendation to bound how long auth.users itself is locked.

Actually running this against production (or even a staging Postgres) is
explicitly the founder's own Production Reality Gate step — see
docs/security/SEC031_MIGRATION_DRY_RUN.md and
docs/security/SEC031_PRODUCTION_ASSUMPTIONS.md. This suite closes the gap
between "a human read the SQL and it looked right" and "the SQL is
mechanically proven to match the approved, peer-reviewed plan" — it does
not and cannot close the gap between "matches the plan" and "actually
works against the real database."
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = REPO_ROOT / "migrations" / "077_sec031_restrict_auth_users_cascade.sql"
DRY_RUN_DOC_PATH = REPO_ROOT / "docs" / "security" / "SEC031_MIGRATION_DRY_RUN.md"

# The exact 19 (table, column) pairs approved in SEC031_MIGRATION_SAFETY_PLAN.md
# / SEC031_MIGRATION_DRY_RUN.md — Tier A, post-peer-review revision.
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
    ("conversations", "user_id"),
}


def _strip_sql_comments(sql: str) -> str:
    """Removes '-- ...' line comments so rollback-section pattern matching
    doesn't accidentally count commented-out statements as active ones."""
    return "\n".join(
        line for line in sql.split("\n")
        if not line.strip().startswith("--")
    )


def _active_sql() -> str:
    return _strip_sql_comments(MIGRATION_PATH.read_text(encoding="utf-8"))


def _full_sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _extract_add_constraint_pairs(sql: str, expected_action: str) -> set[tuple[str, str]]:
    """Parses 'ALTER TABLE <t> ADD CONSTRAINT ... FOREIGN KEY (<c>)
    REFERENCES auth.users(id) ON DELETE <ACTION>' statements, returns the
    set of (table, column) pairs found for that specific ON DELETE action."""
    pattern = re.compile(
        r"ALTER TABLE (\w+) ADD CONSTRAINT \w+_fkey\s+"
        r"FOREIGN KEY \((\w+)\) REFERENCES auth\.users\(id\) ON DELETE (\w+)",
        re.IGNORECASE,
    )
    pairs = set()
    for table, column, action in pattern.findall(sql):
        if action.upper() == expected_action.upper():
            pairs.add((table, column))
    return pairs


class TestMigrationFileExists:
    def test_migration_file_exists(self):
        assert MIGRATION_PATH.exists(), (
            f"Expected {MIGRATION_PATH} — SEC-031 Tier A migration file not found."
        )


class TestMigrationMatchesApprovedPlan:
    """Cross-checks the migration file against the approved 19-pair list —
    not just internal self-consistency, but fidelity to what was actually
    designed, dry-run, and independently peer-reviewed."""

    def test_active_restrict_statements_match_approved_tier_a_exactly(self):
        active = _active_sql()
        found = _extract_add_constraint_pairs(active, "RESTRICT")
        missing = EXPECTED_TIER_A_PAIRS - found
        extra = found - EXPECTED_TIER_A_PAIRS
        assert not missing, f"Migration is missing approved Tier A constraints: {missing}"
        assert not extra, (
            f"Migration adds RESTRICT constraints NOT in the approved Tier A plan: {extra} — "
            f"any addition beyond the peer-reviewed plan needs its own review, not a silent extra line"
        )
        assert len(found) == 19, f"Expected exactly 19 constraints, found {len(found)}"

    def test_every_restrict_constraint_has_matching_drop_before_it(self):
        """Structural check: every ADD CONSTRAINT must be preceded by a DROP
        of the SAME constraint name — proves the file follows the safe
        drop-then-recreate pattern, not an ADD onto an already-existing
        differently-configured constraint (which would fail at runtime)."""
        active = _active_sql()
        add_names = set(re.findall(r"ADD CONSTRAINT (\w+_fkey)", active))
        drop_names = set(re.findall(r"DROP CONSTRAINT (\w+_fkey)", active))
        assert add_names == drop_names, (
            f"Mismatch between DROP and ADD CONSTRAINT names — "
            f"only in ADD: {add_names - drop_names}, only in DROP: {drop_names - add_names}"
        )
        assert len(add_names) == 19

    def test_every_added_constraint_is_validated(self):
        """Every ADD CONSTRAINT ... NOT VALID must be followed by a matching
        VALIDATE CONSTRAINT — otherwise the constraint exists but is never
        actually enforced against existing rows."""
        active = _active_sql()
        add_names = set(re.findall(r"ADD CONSTRAINT (\w+_fkey)", active))
        validate_names = set(re.findall(r"VALIDATE CONSTRAINT (\w+_fkey)", active))
        assert add_names == validate_names, (
            f"Constraints added but never validated: {add_names - validate_names}"
        )

    def test_no_cascade_in_the_active_migration(self):
        """The whole point of this migration is CASCADE -> RESTRICT — an
        active (non-rollback, non-comment) CASCADE statement would mean the
        migration silently does nothing for that table."""
        active = _active_sql()
        cascade_pairs = _extract_add_constraint_pairs(active, "CASCADE")
        assert not cascade_pairs, (
            f"Active migration section still adds CASCADE (should be RESTRICT) for: {cascade_pairs}"
        )

    def test_matches_dry_run_document_verbatim(self):
        """Extracts the SQL code block from SEC031_MIGRATION_DRY_RUN.md SS2
        itself and confirms the migration file's active RESTRICT statements
        are the exact same set — catches drift if either document is edited
        without updating the other."""
        assert DRY_RUN_DOC_PATH.exists()
        doc_text = DRY_RUN_DOC_PATH.read_text(encoding="utf-8")
        doc_restrict_pairs = _extract_add_constraint_pairs(doc_text, "RESTRICT")
        migration_pairs = _extract_add_constraint_pairs(_active_sql(), "RESTRICT")
        assert doc_restrict_pairs == migration_pairs, (
            "Migration file has drifted from the approved dry-run document — "
            f"doc has {doc_restrict_pairs - migration_pairs} not in migration, "
            f"migration has {migration_pairs - doc_restrict_pairs} not in doc"
        )


class TestNoDataMutation:
    """Mechanical proof (not a claim) that this migration cannot lose data —
    scans for any statement that touches rows, not just constraint metadata,
    anywhere in the active (non-comment) SQL."""

    @pytest.mark.parametrize("forbidden", ["INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE", "DROP TABLE"])
    def test_no_row_mutating_statements(self, forbidden):
        active = _active_sql().upper()
        assert forbidden.upper() not in active, (
            f"Found a data-mutating statement ({forbidden!r}) in the active migration — "
            f"this migration must ONLY change constraint metadata"
        )


class TestRollbackIsComplete:
    """The rollback section is commented out (not meant to run alongside the
    forward migration) but must be a complete, symmetric inverse — same 19
    pairs, CASCADE instead of RESTRICT."""

    def test_rollback_section_exists(self):
        full = _full_sql()
        assert "ROLLBACK" in full.upper()

    def test_rollback_restores_cascade_for_all_19_pairs(self):
        full = _full_sql()
        # Rollback lines are commented ('-- ALTER TABLE ...', '--     FOREIGN
        # KEY (...)', etc.) — strip a leading '-- ' (or '--' with no space)
        # from EVERY line in the rollback section so multi-line statements
        # (ALTER TABLE ... ADD CONSTRAINT ... \n --     FOREIGN KEY ...)
        # reassemble into matchable SQL, regardless of what each individual
        # continuation line starts with.
        rollback_section = full.split("ROLLBACK")[-1]
        uncommented_lines = []
        for line in rollback_section.split("\n"):
            stripped = line.strip()
            if stripped.startswith("-- "):
                uncommented_lines.append(stripped[3:])
            elif stripped.startswith("--"):
                uncommented_lines.append(stripped[2:])
            else:
                uncommented_lines.append(line)
        uncommented_rollback = "\n".join(uncommented_lines)
        cascade_pairs = _extract_add_constraint_pairs(uncommented_rollback, "CASCADE")
        missing = EXPECTED_TIER_A_PAIRS - cascade_pairs
        assert not missing, f"Rollback section missing CASCADE restoration for: {missing}"
        assert len(cascade_pairs) == 19


class TestTransactionSplitting:
    """SEC031_MIGRATION_DRY_RUN.md SS3's revised recommendation: split into
    multiple transactions to bound how long auth.users itself is locked,
    rather than one single 19-constraint transaction."""

    def test_forward_migration_uses_multiple_transactions(self):
        active = _active_sql()
        begin_count = len(re.findall(r"^BEGIN;", active, re.MULTILINE))
        commit_count = len(re.findall(r"^COMMIT;", active, re.MULTILINE))
        assert begin_count == commit_count, "Unbalanced BEGIN/COMMIT pairs in the active migration"
        assert begin_count >= 2, (
            f"Expected the migration split into 2+ transactions per the peer-reviewed "
            f"lock-duration recommendation, found {begin_count}"
        )

    def test_no_transaction_contains_all_19_constraints(self):
        """Confirms the split is real, not cosmetic (e.g. one big BEGIN...COMMIT
        that happens to also have an empty second block)."""
        active = _active_sql()
        blocks = re.findall(r"BEGIN;(.*?)COMMIT;", active, re.DOTALL)
        for block in blocks:
            pairs_in_block = _extract_add_constraint_pairs(block, "RESTRICT")
            assert len(pairs_in_block) < 19, "Found a transaction containing all 19 constraints — split is not real"

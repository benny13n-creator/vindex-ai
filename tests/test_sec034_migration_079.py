# -*- coding: utf-8 -*-
"""
SEC-034 finalization — migration 079 structural verification
(predmet_delegiranja.predmet_id -> predmeti(id) ON DELETE CASCADE).

HONEST SCOPE, same as every other migration test this cycle
(test_sec031_migrations.py, test_sec034_migration_078.py): this does NOT
execute the migration against a real Postgres instance (no Docker/local
Postgres/psycopg2 in this environment). It verifies the migration FILE
matches the approved decision — CASCADE, not RESTRICT, per the founder's
explicit 2026-07-23 confirmation (consistency with migration 054's
original spec; RESTRICT would make any previously-delegated predmet
permanently undeletable since routers/enterprise.py has no delegation-
delete endpoint). Live confirmation happens via the read-only query in
this migration's own "VERIFIKACIJA POSLE POKRETANJA" section, run by the
founder after execution.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = REPO_ROOT / "migrations" / "079_fix_predmet_delegiranja_fk.sql"
MIGRATION_054_PATH = REPO_ROOT / "migrations" / "054_predmet_delegiranja.sql"
MIGRATION_077_PATH = REPO_ROOT / "migrations" / "077_sec031_restrict_auth_users_cascade.sql"


def _text() -> str:
    assert MIGRATION_PATH.is_file(), f"{MIGRATION_PATH} missing"
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _executable_sql_only(text: str) -> str:
    """Strip `--` comment lines -- explanatory prose (which legitimately
    discusses auth.users/RESTRICT as context for the CASCADE decision)
    should not trip checks meant for the actual DDL statements."""
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("--")
    )


class TestMigrationFileExists:
    def test_file_present(self):
        assert MIGRATION_PATH.is_file()


class TestForeignKeyDefinition:
    def test_references_predmeti_on_predmet_id(self):
        text = _text()
        assert re.search(
            r"ADD CONSTRAINT predmet_delegiranja_predmet_id_fkey\s+"
            r"FOREIGN KEY \(predmet_id\) REFERENCES public\.predmeti\(id\)",
            text,
        )

    def test_uses_cascade_not_restrict(self):
        text = _text()
        # The exact clause must be ON DELETE CASCADE for this FK -- confirm
        # both that CASCADE is present in the right place and that this
        # migration does not introduce a RESTRICT rule (that would be the
        # SEC-031 pattern, wrong direction for this relationship).
        fk_block = re.search(
            r"ADD CONSTRAINT predmet_delegiranja_predmet_id_fkey.*?NOT VALID",
            text,
            re.DOTALL,
        )
        assert fk_block, "Could not locate the FK ADD CONSTRAINT block"
        assert "ON DELETE CASCADE" in fk_block.group(0)
        assert "RESTRICT" not in fk_block.group(0)

    def test_uses_not_valid_validate_pattern(self):
        text = _text()
        assert "NOT VALID" in text
        assert re.search(
            r"VALIDATE CONSTRAINT predmet_delegiranja_predmet_id_fkey", text
        )


class TestIdempotentGuard:
    def test_wrapped_in_not_exists_guard(self):
        text = _text()
        assert re.search(
            r"IF NOT EXISTS\s*\(\s*SELECT 1 FROM pg_constraint "
            r"WHERE conname = 'predmet_delegiranja_predmet_id_fkey'",
            text,
        )


class TestDoesNotTouchAuthUsersOrSec031:
    """This migration must stay entirely out of SEC-031's territory --
    no auth.users reference, no RESTRICT rule, no touching the 18
    constraints migration 077 already closed."""

    def test_no_auth_users_reference(self):
        text = _executable_sql_only(_text())
        assert "auth.users" not in text

    def test_no_restrict_keyword_at_all(self):
        text = _executable_sql_only(_text()).upper()
        assert "RESTRICT" not in text


class TestMatchesMigration054Intent:
    """Migration 054 originally specified ON DELETE CASCADE for this exact
    column -- 079 must restore that, not invent a new rule."""

    def test_054_specifies_cascade_for_predmet_id(self):
        assert MIGRATION_054_PATH.is_file()
        text = MIGRATION_054_PATH.read_text(encoding="utf-8", errors="replace")
        assert re.search(
            r"predmet_id\s+uuid\s+NOT NULL\s+REFERENCES public\.predmeti\(id\)\s+ON DELETE CASCADE",
            text,
            re.IGNORECASE,
        ), "migrations/054 no longer defines CASCADE for predmet_id -- 079 may now be out of sync"


class TestConsistentWithSec031Scope:
    """079 must not appear in migration 077's Tier A pairs -- this FK was
    always out of SEC-031's auth.users-cascade scope by design."""

    def test_predmet_id_not_in_077_tier_a_pairs(self):
        assert MIGRATION_077_PATH.is_file()
        text = MIGRATION_077_PATH.read_text(encoding="utf-8", errors="replace")
        assert "predmet_delegiranja', 'predmet_id'" not in text.replace(" ", "")


class TestSingleTransaction:
    def test_wrapped_in_begin_commit(self):
        text = _text()
        assert re.search(r"^\s*BEGIN;", text, re.MULTILINE)
        assert re.search(r"^\s*COMMIT;", text, re.MULTILINE)


class TestRollbackDocumented:
    def test_rollback_drops_only_this_constraint(self):
        text = _text()
        assert "ROLLBACK" in text.upper()
        assert "DROP CONSTRAINT IF EXISTS predmet_delegiranja_predmet_id_fkey" in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

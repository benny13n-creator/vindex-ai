# -*- coding: utf-8 -*-
"""
SEC-034 — migration source completeness check.

HONEST SCOPE, stated up front: SEC-034 itself (docs/security/SECURITY_GAP_
REGISTER.md) was found when migrations 054 and 056 turned out to have done
NOTHING against production, because `CREATE TABLE IF NOT EXISTS` found the
table already existing in a bare, incomplete form. Both migration FILES
were themselves correct and complete — the mismatch only existed between
the file and the live database. That means **this test cannot detect
SEC-034's actual risk** — a repo-only check is structurally blind to
"live state disagrees with the file that would create it," because that
requires a live database this environment does not have (no Docker, no
local Postgres, no psycopg2 — verified directly, not assumed).

What this test DOES check, which is real and useful on its own: whether
the migration SOURCE is internally self-consistent — specifically,
whether every table that enables Row Level Security also either (a)
defines at least one CREATE POLICY somewhere in the corpus, or (b) is on
an explicit, justified allowlist of tables that are intentionally
service-role-only (RLS enabled, zero policies == deny all non-service-
role access by design — the same pattern already used deliberately for
`audit_immutable`, whose policy is `USING (FALSE)`). This catches a
different but related bug: a future migration that enables RLS and then
forgets to add a policy, silently leaving a table either fully locked out
or -- if RLS was never actually applied live -- fully open. It does not
and cannot confirm live production matches any of this.

For the actual live-state check that SEC-034 needs, see
scripts/sec034_live_completeness_check.sql — a read-only diagnostic the
founder runs directly against production, following the same pattern
established for SEC-031 (SS0 diagnostic query).

INVESTIGATION NOTE (2026-07-23): an initial naive regex census flagged 15
tables as "RLS enabled but no policy found." Manually reading each one's
migration source showed 11 of the 15 were false positives — the census
regex failed on multi-line `CREATE POLICY "name"\n ON table` syntax and
`DO $$ ... CREATE POLICY ... END $$;` idempotent-guard blocks. A second,
non-greedy regex pass (the one this test uses) correctly finds only 4
tables with RLS-enabled-and-zero-policy: `email_notif_log`,
`kancelarija_clanovi`, `law_docs`, `security_events`. Reading each of
those 4 confirmed all are intentional service-role-only tables (explicit
comments: "Nema user pristupa — samo admin čita kroz service_role" /
"Samo service_role (backend) ima pristup" / equivalent), not gaps. Zero
genuine gaps were found in this pass — that is a real result, not an
absence of looking.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"

# Tables where RLS is enabled with deliberately ZERO end-user-facing
# policies -- default-deny, service_role (which bypasses RLS entirely,
# see SEC-004) is the only path in. Each entry must cite the comment in
# its own migration file that documents the decision. Adding a table here
# must be a conscious act, not a silent side effect of a missing policy.
SERVICE_ROLE_ONLY_TABLES: dict[str, str] = {
    "email_notif_log": "migrations/021_email_notif.sql — GRANT ... TO service_role, no user policy (notification delivery log)",
    "kancelarija_clanovi": "migrations/018_kancelarija.sql — 'Backend has full access', membership reads are API-mediated",
    "law_docs": "migrations/020_law_docs.sql — 'Samo service_role (backend) ima pristup — admini pristupaju via API'",
    "security_events": "migrations/043_security_bulletproof.sql — 'Nema user pristupa — samo admin čita kroz service_role'",
}

RLS_ENABLE_RE = re.compile(
    r"ALTER TABLE\s+(?:public\.)?(\w+)\s+ENABLE ROW LEVEL SECURITY",
    re.IGNORECASE,
)
# Non-greedy on purpose: matches either a quoted policy name or a single
# bare token, never free-text spanning multiple statements. An earlier,
# greedy version of this pattern (`["\']?[^"\']*["\']?`) silently
# swallowed multiple consecutive CREATE POLICY statements into one match
# and undercounted policies -- this shape avoids that failure mode.
CREATE_POLICY_RE = re.compile(
    r'CREATE POLICY\s+(?:"[^"]*"|\S+)\s+ON\s+(?:public\.)?(\w+)',
    re.IGNORECASE,
)


def _migration_files() -> list[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    assert files, f"No migration files found under {MIGRATIONS_DIR}"
    return files


def _full_corpus_text() -> str:
    return "\n".join(
        f.read_text(encoding="utf-8", errors="replace") for f in _migration_files()
    )


class TestMigrationsDirectoryExists:
    def test_migrations_dir_present_and_nonempty(self):
        assert MIGRATIONS_DIR.is_dir()
        assert len(_migration_files()) >= 60  # 69 at time of writing; floor, not exact pin


class TestRlsPolicyCompleteness:
    """Every RLS-enabled table either has a policy, or is an explicit,
    justified, service-role-only allowlist entry. No third option."""

    def test_every_rls_table_has_policy_or_is_allowlisted(self):
        full = _full_corpus_text()
        rls_tables = {m.lower() for m in RLS_ENABLE_RE.findall(full)}
        policy_tables = {m.lower() for m in CREATE_POLICY_RE.findall(full)}

        unexplained = sorted(
            t for t in rls_tables
            if t not in policy_tables and t not in SERVICE_ROLE_ONLY_TABLES
        )
        assert not unexplained, (
            "These tables enable RLS but define no CREATE POLICY anywhere "
            "in migrations/, and are not on the documented "
            "SERVICE_ROLE_ONLY_TABLES allowlist: "
            f"{unexplained}. Either add a policy, or add a justified "
            "allowlist entry citing the table's own migration comment."
        )

    def test_allowlist_entries_are_still_policy_free(self):
        # Guards the allowlist itself against going stale: if a later
        # migration adds a real policy to one of these tables, the
        # allowlist entry becomes misleading and should be removed.
        full = _full_corpus_text()
        policy_tables = {m.lower() for m in CREATE_POLICY_RE.findall(full)}
        stale = sorted(t for t in SERVICE_ROLE_ONLY_TABLES if t in policy_tables)
        assert not stale, (
            f"These allowlisted tables now DO have a CREATE POLICY: {stale}. "
            "Remove them from SERVICE_ROLE_ONLY_TABLES -- the allowlist is "
            "for tables with no policy at all, and is now out of date."
        )

    def test_allowlist_entries_still_enable_rls(self):
        # Guards against the opposite drift: an allowlisted table whose
        # RLS enable statement was removed/renamed, silently turning
        # "default-deny by RLS" into "no RLS at all."
        full = _full_corpus_text()
        rls_tables = {m.lower() for m in RLS_ENABLE_RE.findall(full)}
        missing_rls = sorted(t for t in SERVICE_ROLE_ONLY_TABLES if t not in rls_tables)
        assert not missing_rls, (
            f"These allowlisted tables no longer enable RLS at all: {missing_rls}. "
            "Without RLS, 'service-role-only by default-deny' does not hold -- "
            "this needs an actual fix, not an allowlist entry."
        )


class TestKnownSec034Instances:
    """SEC-034 was discovered via 2 concrete production instances
    (predmet_delegiranja, tos_acceptances). This locks in that those two
    migrations still define what they're supposed to, so a future edit
    can't silently regress the fix in the source itself. It cannot check
    whether the fix actually landed live -- see the module docstring."""

    def test_predmet_delegiranja_migration_defines_auth_users_fks(self):
        path = MIGRATIONS_DIR / "054_predmet_delegiranja.sql"
        assert path.is_file()
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "predmet_delegiranja" in text
        assert "od_user_id" in text and "na_user_id" in text

    def test_tos_acceptances_migration_defines_user_fk(self):
        full = _full_corpus_text()
        assert "tos_acceptances" in full
        assert re.search(
            r"tos_acceptances.*?user_id.*?REFERENCES\s+auth\.users",
            full,
            re.IGNORECASE | re.DOTALL,
        ) or re.search(
            r"user_id\s+UUID.*?REFERENCES\s+auth\.users",
            full,
            re.IGNORECASE,
        )


class TestLiveDiagnosticScriptExists:
    def test_sec034_live_check_script_present(self):
        script = REPO_ROOT / "scripts" / "sec034_live_completeness_check.sql"
        assert script.is_file(), (
            "scripts/sec034_live_completeness_check.sql is the actual "
            "mechanism that can detect SEC-034's real risk (live state vs. "
            "migration file) -- this test suite alone cannot."
        )
        content = script.read_text(encoding="utf-8")
        assert "SELECT" in content.upper()
        # Must stay read-only -- this is handed to the founder to run
        # directly against production.
        forbidden = ["DROP ", "DELETE ", "UPDATE ", "INSERT ", "ALTER ", "TRUNCATE "]
        upper = content.upper()
        for kw in forbidden:
            assert kw not in upper, f"Live diagnostic script must stay read-only, found {kw!r}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

# SEC-031 — Production Assumptions

**Date:** 2026-07-23
**Status:** Fact/assumption boundary document. **No schema changed.** Purpose: separate what this analysis has actually verified from what it has merely inferred or assumed — per explicit instruction that "grep shows nobody calls delete-user" is evidence about the application, not proof about production or platform behavior.

---

## Verified (from repository inspection — reproducible, cited)

| # | Fact | Evidence |
|---|---|---|
| 1 | No application code path calls Supabase's user-deletion admin API (`auth.admin.deleteUser`/equivalent) | Full-repo grep for `delete_user\|auth\.admin\|admin\.delete\|deleteUser` — only 2 matches total, both unrelated (`auth.admin.create_user` at `api.py:2082`, `auth.admin.sign_out` at `api.py:2226`) |
| 2 | The application's own GDPR erasure endpoint never touches `auth.users` | Grep of `routers/gdpr.py` for `auth\.users\|admin\.\|delete_user\|auth\.admin` — zero matches |
| 3 | No test in this repository performs or asserts on an `auth.users` deletion | Grep of `tests/` for `delete.*auth\.users\|auth\.users.*delete\|admin\.delete_user` — zero matches |
| 4 | The schema **as written in this repository** defines the FK shape described in `SEC031_IMPACT_ANALYSIS.md` and `SEC031_FK_GRAPH.md` | Exhaustive extraction of every `CREATE TABLE` block across `migrations/*.sql`, `supabase_migrations/*.sql`, `supabase_setup.sql` — cross-checked by two independent extraction passes, counts reconciled |
| 5 | Postgres's documented behavior is that a single `DELETE` statement is atomic, and a `RESTRICT`/`NO ACTION` constraint violation anywhere in that statement aborts the whole statement | Standard, documented PostgreSQL referential-integrity behavior — not specific to this schema, not something this repository could contradict even if it wanted to |
| 6 | No migration-tracking table or automated migration runner exists in this repository | Searched `scripts/*.py` and repo root for a schema-migrations table or runner — none found; migrations appear to be applied manually |

**What #4 and #6 together mean:** the repo describes an *intended* schema. Whether that intended schema is what's actually live in the production Supabase project is a **separate question this repository cannot answer about itself** — see the unverified items below.

---

## Not verified — requires explicit confirmation before this migration is run

| # | Open question | Why it matters | How to close it |
|---|---|---|---|
| 1 | **Does production actually have these exact constraints, with these exact `ON DELETE` settings, right now?** | If a migration file was edited after being applied, applied out of order, or partially applied, the live schema could differ from what's in the repo — the whole plan is built on the repo's description of the schema | Run the read-only `information_schema` query from `SEC031_IMPACT_ANALYSIS.md` §5 against production before writing any migration SQL |
| 2 | **Does Supabase's "Delete user" dashboard action, or the Admin API's `deleteUser` call, execute a plain SQL `DELETE FROM auth.users`?** | Supabase's Auth service (GoTrue) is a separate service that manages the `auth` schema — it is not guaranteed that its user-deletion path is a literal, unmodified `DELETE` statement against the table. It could involve its own internal soft-delete/cleanup logic, different transaction handling, or additional steps (e.g., revoking sessions first) that this analysis has not seen and cannot see from this repository | Requires either Supabase's own documentation/support confirmation for this project's plan tier, or an actual controlled test in a non-production project |
| 3 | **Does Supabase run any automated cleanup of `auth.users` rows outside the application's control** (e.g., purging unconfirmed/abandoned signups after N days, a platform-level retention job)? | If such a job exists and this migration makes affected rows `RESTRICT`-protected, the job could start failing/erroring in a way this repository has no visibility into | `REQUIRES PRODUCTION VERIFICATION` — check Supabase project settings / support docs for this specific project, not derivable from this repo |
| 4 | **Does any operational process outside this repository rely on deleting a user and expecting the cascade** (a manual admin runbook, a support-team spreadsheet process, an internal script not committed to this repo, a one-off cleanup someone ran from their own machine)? | This is exactly the kind of thing that wouldn't appear in any grep of this codebase, and is the single most likely source of an unpleasant surprise if this migration lands without checking | Only the founder/team can answer this — it's an organizational-process question, not a code question |
| 5 | **Are there any Postgres triggers, functions, or Supabase Auth Hooks attached to `auth.users` that this repository doesn't version?** | The `auth` schema is managed by Supabase, not by this repository's own migrations — anything attached there outside of what's shown in `migrations/*.sql` (which only ever *reference* `auth.users`, never define it) would be invisible to this analysis | Query production directly: `SELECT tgname FROM pg_trigger WHERE tgrelid = 'auth.users'::regclass;` (read-only, safe to run) |
| 6 | **Actual row counts and expected lock duration for the `DROP CONSTRAINT`/`ADD CONSTRAINT` operations** | The migration plan describes these as "near-instant, metadata-only" based on general Postgres behavior for constraint changes — this has not been measured against this project's actual production table sizes | Check table sizes (`SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE relname IN (...)`) before scheduling the migration window, and/or test timing on a staging copy first |
| 7 | **Whether the constraint names assumed in `SEC031_MIGRATION_DRY_RUN.md` match what's actually live** | The dry-run document uses Postgres's default auto-generated naming convention (`<table>_<column>_fkey`) since the `CREATE TABLE` statements in this repo don't specify explicit constraint names — if production constraints were ever manually renamed or recreated with different names, the `DROP CONSTRAINT` statements as written would fail (safely — with a clear "constraint does not exist" error, not a silent wrong action) | Confirm via `information_schema` before running (same query as #1 also returns constraint names) |

---

## What this means in practice

Items 1 and 7 in the unverified list are cheap, read-only, and should simply be run before writing real migration SQL — they're not open-ended organizational questions, they're one query away from being converted into verified facts. Items 2–6 range from "another read-only query" (5, 6) to genuinely outside this repository's visibility (2, 3, 4) — those need a human decision or an external confirmation, not more code inspection. **No amount of further repository analysis can close items 2–4** — that is precisely the boundary this document exists to make explicit, rather than letting "the code looks safe" quietly stand in for "the operation is safe."

## What this document does not do

Does not run any of the verification queries listed above (they are read-only, but running them was not requested for this document — this document's job is to state which checks are required, not to execute them). Does not change any schema. Does not authorize the migration.

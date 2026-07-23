# SEC-031 — Migration Dry Run (Phase 1, Tier A)

**Date:** 2026-07-23 (revised same day after independent peer review — see `SEC031_PEER_REVIEW_CONSENSUS.md`)
**Status:** Dry run only. **No executable migration file exists. Nothing in this document has been run.** This is the last plan-stage deliverable before an actual `migrations/0NN_sec031_restrict.sql` file could be written — that file is not authorized by this document.
**Revision note:** two corrections from independent peer review: (1) §3's original lock analysis incorrectly claimed no lock is taken on `auth.users` — corrected below, it does take one. (2) Two more constraints (`user_knowledge`, `conversations`) added to match the revised Tier A list in `SEC031_MIGRATION_SAFETY_PLAN.md`. Tier A is now 19 constraints across 18 tables (was 17/16).

**Prerequisite, not yet satisfied:** `SEC031_PRODUCTION_ASSUMPTIONS.md` item 1 and item 7 (confirm live constraint state and exact constraint names via the `information_schema` query) should be run and their results compared against what's assumed below **before** any real migration file is written from this dry run.

---

## 1. Constraint naming assumption

None of the `CREATE TABLE` statements in this schema specify an explicit `CONSTRAINT <name>` for these foreign keys — they use inline `REFERENCES` clauses. Postgres's default naming convention for an unnamed FK is `<table>_<column>_fkey`. **This document assumes that convention holds in production.** This is exactly `SEC031_PRODUCTION_ASSUMPTIONS.md` item 7 — unverified. If a constraint name below doesn't match production, the corresponding `DROP CONSTRAINT` fails safely (a clear "constraint does not exist" error, no silent wrong action) rather than doing anything unintended — but it does mean the actual migration file should either confirm names first or use a name-resolving `DO` block rather than hardcoded names, noted in §4.

---

## 2. Exact ALTER TABLE statements — Tier A (19 constraints, 18 tables)

Pattern used per constraint (the production-safe two-step form, avoiding a long-held `ACCESS EXCLUSIVE` lock during validation):

```sql
ALTER TABLE <table> DROP CONSTRAINT <table>_<column>_fkey;
ALTER TABLE <table> ADD CONSTRAINT <table>_<column>_fkey
    FOREIGN KEY (<column>) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE <table> VALIDATE CONSTRAINT <table>_<column>_fkey;
```

`NOT VALID` makes the `ADD CONSTRAINT` step itself near-instant (no existing-row scan) and only takes a brief `ACCESS EXCLUSIVE` lock; the subsequent `VALIDATE CONSTRAINT` scans existing rows to confirm they satisfy the constraint but only needs `SHARE UPDATE EXCLUSIVE` (does not block concurrent reads/writes) — standard Postgres practice for adding FK constraints on live tables without a long write-blocking window.

### Full statement list

```sql
-- predmeti
ALTER TABLE predmeti DROP CONSTRAINT predmeti_user_id_fkey;
ALTER TABLE predmeti ADD CONSTRAINT predmeti_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE predmeti VALIDATE CONSTRAINT predmeti_user_id_fkey;

-- predmet_dokumenti
ALTER TABLE predmet_dokumenti DROP CONSTRAINT predmet_dokumenti_user_id_fkey;
ALTER TABLE predmet_dokumenti ADD CONSTRAINT predmet_dokumenti_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE predmet_dokumenti VALIDATE CONSTRAINT predmet_dokumenti_user_id_fkey;

-- predmet_hronologija
ALTER TABLE predmet_hronologija DROP CONSTRAINT predmet_hronologija_user_id_fkey;
ALTER TABLE predmet_hronologija ADD CONSTRAINT predmet_hronologija_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE predmet_hronologija VALIDATE CONSTRAINT predmet_hronologija_user_id_fkey;

-- predmet_beleske
ALTER TABLE predmet_beleske DROP CONSTRAINT predmet_beleske_user_id_fkey;
ALTER TABLE predmet_beleske ADD CONSTRAINT predmet_beleske_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE predmet_beleske VALIDATE CONSTRAINT predmet_beleske_user_id_fkey;

-- predmet_istorija
ALTER TABLE predmet_istorija DROP CONSTRAINT predmet_istorija_user_id_fkey;
ALTER TABLE predmet_istorija ADD CONSTRAINT predmet_istorija_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE predmet_istorija VALIDATE CONSTRAINT predmet_istorija_user_id_fkey;

-- predmet_delegiranja (2 columns)
ALTER TABLE predmet_delegiranja DROP CONSTRAINT predmet_delegiranja_od_user_id_fkey;
ALTER TABLE predmet_delegiranja ADD CONSTRAINT predmet_delegiranja_od_user_id_fkey
    FOREIGN KEY (od_user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE predmet_delegiranja VALIDATE CONSTRAINT predmet_delegiranja_od_user_id_fkey;

ALTER TABLE predmet_delegiranja DROP CONSTRAINT predmet_delegiranja_na_user_id_fkey;
ALTER TABLE predmet_delegiranja ADD CONSTRAINT predmet_delegiranja_na_user_id_fkey
    FOREIGN KEY (na_user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE predmet_delegiranja VALIDATE CONSTRAINT predmet_delegiranja_na_user_id_fkey;

-- fakture
ALTER TABLE fakture DROP CONSTRAINT fakture_user_id_fkey;
ALTER TABLE fakture ADD CONSTRAINT fakture_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE fakture VALIDATE CONSTRAINT fakture_user_id_fkey;

-- billing_entries
ALTER TABLE billing_entries DROP CONSTRAINT billing_entries_user_id_fkey;
ALTER TABLE billing_entries ADD CONSTRAINT billing_entries_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE billing_entries VALIDATE CONSTRAINT billing_entries_user_id_fkey;

-- timer_sessions
ALTER TABLE timer_sessions DROP CONSTRAINT timer_sessions_user_id_fkey;
ALTER TABLE timer_sessions ADD CONSTRAINT timer_sessions_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE timer_sessions VALIDATE CONSTRAINT timer_sessions_user_id_fkey;

-- tarife
ALTER TABLE tarife DROP CONSTRAINT tarife_user_id_fkey;
ALTER TABLE tarife ADD CONSTRAINT tarife_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE tarife VALIDATE CONSTRAINT tarife_user_id_fkey;

-- tarifne_stavke_custom
ALTER TABLE tarifne_stavke_custom DROP CONSTRAINT tarifne_stavke_custom_user_id_fkey;
ALTER TABLE tarifne_stavke_custom ADD CONSTRAINT tarifne_stavke_custom_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE tarifne_stavke_custom VALIDATE CONSTRAINT tarifne_stavke_custom_user_id_fkey;

-- sef_log
ALTER TABLE sef_log DROP CONSTRAINT sef_log_user_id_fkey;
ALTER TABLE sef_log ADD CONSTRAINT sef_log_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE sef_log VALIDATE CONSTRAINT sef_log_user_id_fkey;

-- praceni_predmeti
ALTER TABLE praceni_predmeti DROP CONSTRAINT praceni_predmeti_user_id_fkey;
ALTER TABLE praceni_predmeti ADD CONSTRAINT praceni_predmeti_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE praceni_predmeti VALIDATE CONSTRAINT praceni_predmeti_user_id_fkey;

-- rocista
ALTER TABLE rocista DROP CONSTRAINT rocista_user_id_fkey;
ALTER TABLE rocista ADD CONSTRAINT rocista_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE rocista VALIDATE CONSTRAINT rocista_user_id_fkey;

-- smart_contract_analyses
ALTER TABLE smart_contract_analyses DROP CONSTRAINT smart_contract_analyses_user_id_fkey;
ALTER TABLE smart_contract_analyses ADD CONSTRAINT smart_contract_analyses_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE smart_contract_analyses VALIDATE CONSTRAINT smart_contract_analyses_user_id_fkey;

-- tos_acceptances
ALTER TABLE tos_acceptances DROP CONSTRAINT tos_acceptances_user_id_fkey;
ALTER TABLE tos_acceptances ADD CONSTRAINT tos_acceptances_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE tos_acceptances VALIDATE CONSTRAINT tos_acceptances_user_id_fkey;

-- user_knowledge (added post-peer-review — see revision note above)
ALTER TABLE user_knowledge DROP CONSTRAINT user_knowledge_user_id_fkey;
ALTER TABLE user_knowledge ADD CONSTRAINT user_knowledge_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE user_knowledge VALIDATE CONSTRAINT user_knowledge_user_id_fkey;

-- conversations (added post-peer-review — defined in the legacy supabase_migration.sql,
-- not the primary migrations/ series; confirm the table actually exists in production
-- before including this statement in the real migration file, per
-- SEC031_PRODUCTION_ASSUMPTIONS.md's new item on this table)
ALTER TABLE conversations DROP CONSTRAINT conversations_user_id_fkey;
ALTER TABLE conversations ADD CONSTRAINT conversations_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE conversations VALIDATE CONSTRAINT conversations_user_id_fkey;
```

---

## 3. Expected locks

| Step | Lock on child table | Lock on `auth.users` | Duration |
|---|---|---|---|
| `DROP CONSTRAINT` | `ACCESS EXCLUSIVE` | `ShareRowExclusiveLock` (removes the RI trigger on the referenced table) | Near-instant — metadata only, no row scan |
| `ADD CONSTRAINT ... NOT VALID` | `ACCESS EXCLUSIVE` | `ShareRowExclusiveLock` (installs the RI trigger on the referenced table) | Near-instant — `NOT VALID` skips the existing-row check at add time |
| `VALIDATE CONSTRAINT` | `SHARE UPDATE EXCLUSIVE` | None | Proportional to table row count — does **not** block concurrent reads or writes, only blocks other DDL on the same table |

**Correction (post-peer-review): the original version of this document claimed no lock is taken on `auth.users`. That was wrong.** `DROP`/`ADD CONSTRAINT` for a FK referencing `auth.users(id)` installs or removes a referential-integrity trigger on the **referenced** table — `auth.users` — which takes a `ShareRowExclusiveLock` on it, not just on the child table declaring the FK. `ShareRowExclusiveLock` conflicts with ordinary `ROW EXCLUSIVE` locks, meaning **`auth.users` INSERT/UPDATE/DELETE (i.e., new signups, logins that touch `auth.users`, Supabase Auth's own internal writes) can briefly queue** behind this migration. `VALIDATE CONSTRAINT` itself does not re-lock `auth.users` — only the `DROP`/`ADD` steps do, and each is near-instant, but if all 19 constraints run in a single transaction (as originally proposed), the cumulative lock on `auth.users` is held from the first `ADD CONSTRAINT` until `COMMIT` — not indefinitely, but for the full duration of the transaction, not just each individual statement.

**Revised recommendation**: split Tier A into 2-3 smaller transactions (e.g., by table group) rather than one, specifically to bound how long `auth.users` is write-locked at any single point, and schedule the whole operation during a genuinely low-traffic window — now for the correct, verified reason, not the original (incorrect) "no lock on auth.users at all" reasoning. **`NOT VERIFIED` against this project's actual production row counts** (`SEC031_PRODUCTION_ASSUMPTIONS.md` item 6) — expected to be sub-second per constraint given typical early-stage SaaS table sizes, but not measured; the `auth.users` lock duration in particular is worth measuring on staging before a production run, since it's the one part of this migration that touches a table outside this project's own schema control.

---

## 4. Rollback SQL

Exact inverse of §2, restoring the original `CASCADE` definition, same `NOT VALID`/`VALIDATE` safety pattern:

```sql
ALTER TABLE predmeti DROP CONSTRAINT predmeti_user_id_fkey;
ALTER TABLE predmeti ADD CONSTRAINT predmeti_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE NOT VALID;
ALTER TABLE predmeti VALIDATE CONSTRAINT predmeti_user_id_fkey;

-- ... identical pattern repeated for all 19 constraints listed in §2,
-- substituting ON DELETE CASCADE for ON DELETE RESTRICT.
```

**Rollback is unconditionally safe**: this migration never deletes, moves, or rewrites a single row in either direction — it only changes constraint metadata. There is no data-loss risk from rolling back, and no data-loss risk from applying it in the first place (the whole point of the change is to make destructive deletion *harder*, not to perform one).

**Naming risk noted for the real migration file** (not resolved here): if `SEC031_PRODUCTION_ASSUMPTIONS.md` item 7's verification finds different live constraint names, the actual migration should either use the confirmed names directly, or use a `DO $$ ... $$` block that looks up the constraint name from `information_schema` at run time rather than hardcoding it — a decision for whoever writes the real migration file, flagged here rather than silently assumed away.

---

## 5. Expected before/after behavior

| Scenario | Before this migration | After this migration |
|---|---|---|
| Direct `DELETE FROM auth.users WHERE id = X`, where `X` owns at least one row in any Tier A table | Succeeds — cascades through the full graph traced in `SEC031_FK_GRAPH.md`, destroying all legal/financial data transitively | **Fails** with a foreign-key-violation error naming the specific Tier A constraint; `auth.users` row and all dependent data remain fully intact, unchanged |
| Direct `DELETE FROM auth.users WHERE id = X`, where `X` has zero rows in every Tier A table (a genuinely empty/unused account) | Succeeds, cascades trivially (nothing of consequence to destroy) | **Still succeeds** — this migration does not lock down accounts with no legal/financial footprint |
| `routers/gdpr.py`'s existing erasure endpoint | Anonymizes `profiles` only; never touches `auth.users` | **Unchanged** — this migration has zero interaction with that code path, confirmed in `SEC031_IMPACT_ANALYSIS.md` §4 |
| Ordinary application reads/writes to any Tier A table (creating a `predmet`, adding a `fakture`, etc.) | Normal | **Unchanged** — the constraint only activates on an attempted `auth.users` deletion, never on ordinary CRUD |
| `supa.auth.admin.create_user` / `supa.auth.admin.sign_out` (the only two `auth.admin.*` call sites in the codebase) | Normal | **Unchanged** — neither performs a delete |

---

## 6. Test matrix

Same six tests specified in `SEC031_MIGRATION_SAFETY_PLAN.md` §4, now with concrete pre-conditions and pass/fail criteria tied to the exact statements above — not yet written as executable test code (that's the implementation step, still gated on founder approval of this whole document chain):

| # | Test | Precondition | Exact action | Pass criterion |
|---|---|---|---|---|
| 1 | Protected-account deletion blocked | Test user owns 1 row in `predmeti` | `DELETE FROM auth.users WHERE id = <test_user>` | Statement raises `foreign key violation`; `predmeti` row, `auth.users` row, and all transitively-dependent rows (per §5's graph) still exist afterward |
| 2 | Clean-account deletion still works | Test user owns 0 rows in every Tier A table | Same delete | Statement succeeds; `auth.users` row and its trivially-cascaded operational data (sessions, logs) are gone |
| 3 | GDPR flow unaffected | Existing `tests/test_gdpr_delete.py` | Run unmodified | Passes exactly as before migration |
| 4 | Full regression suite unaffected | N/A | Run full suite (1725 tests as of SEC-001's closure) | Passes unchanged — confirms zero effect on any non-`auth.users`-deletion path |
| 5 | Admin operations unaffected | N/A | Exercise `create_user` and `sign_out` | Both succeed, unchanged |
| 6 | Rollback restores original behavior | Migration applied, test 1 confirmed blocking | Run §4's rollback SQL, then repeat test 1's exact delete | Delete now **succeeds** (cascade restored) — proves rollback is complete and functional, not just "the SQL ran without error" |

**Staging demonstration recommended, not yet performed**: per the explicit standard set for this plan, test 6 in particular should be run end-to-end on a staging/non-production copy of the schema before this is considered verified — a rollback that hasn't been exercised is a rollback that's only theoretically proven.

---

## 7. What this document does not do

- Does not create `migrations/0NN_sec031_restrict.sql` or any other executable file.
- Does not run any statement listed above, in either this or any other environment.
- Does not resolve the constraint-naming assumption (§1) — that requires the production verification query from `SEC031_PRODUCTION_ASSUMPTIONS.md` item 1/7 first.
- Does not include Tier B (the `predmeti`/`klijenti`-children hardening from the migration safety plan) — scoped to Tier A only, matching that plan's own phasing recommendation.

## Recommendation summary

1. Run `SEC031_PRODUCTION_ASSUMPTIONS.md`'s read-only verification queries (items 1, 5, 7) against production first — cheap, safe, and would immediately confirm or correct every assumption this dry run makes about live constraint names and current state.
2. Once confirmed, the statements in §2 can become an actual migration file with minimal changes (mainly: swap in real constraint names if they differ).
3. Demonstrate the full test matrix (§6), including the rollback test, on staging before considering this production-ready.
4. **This document does not authorize writing the executable migration file.** That remains a separate, explicit next decision.

# SEC-031 — Migration Safety Plan (Phase 1: Safety Lock)

**Date:** 2026-07-23
**Status:** Plan only. **No schema modified by this document — no migration file has been written or run.** This is deliverable #4 in the SEC-031 chain (`SEC031_IMPACT_ANALYSIS.md` → `SEC031_REMEDIATION_DESIGN.md` → this plan →, only after founder sign-off, an actual migration).
**Scope boundary set by founder:** Phase 1 (this plan) is a **safety lock against catastrophic accidental deletion** — it is explicitly *not* the lifecycle architecture (`SEC031_REMEDIATION_DESIGN.md`), which stays deferred until SEC-002's retention-duration questions are legally confirmed. The two phases do not block each other: Phase 1 can and should proceed now; Phase 2 (lifecycle) waits.

---

## 0. The one fact that shapes this whole plan

Postgres evaluates a `DELETE FROM auth.users WHERE id = X` as **one atomic statement**. If *any* foreign key referencing that row has `ON DELETE RESTRICT`/`NO ACTION` and a matching dependent row exists, **the entire statement fails and rolls back — including any `CASCADE` deletes on other tables that would otherwise have fired.** This means Phase 1 does not require flipping all 46 first-level and 15 second-level foreign keys found in the impact analysis. It requires flipping the ones on tables that must never silently disappear (legal + financial records). Once those are `RESTRICT`, **any account that has ever created a single predmet or invoice becomes structurally undeletable via a direct `auth.users` delete, full stop** — the disposable tables (sessions, notification logs, usage events) never get a chance to matter, because the transaction never gets that far. Accounts with genuinely zero legal/financial footprint (e.g., a signup that never created anything) remain hard-deletable, which is a reasonable, low-risk behavior to preserve rather than lock down for no protective benefit.

This changes the migration from "flip ~60 constraints" to a much smaller, more precisely scoped, more reviewable change — smaller surface area is itself a safety property for the migration itself.

---

## 1. Foreign keys that must change from CASCADE to RESTRICT

### Tier A — Required to close SEC-031 (first-level, directly from `auth.users`)

These are sufficient on their own, per §0's transaction semantics, to make any account with legal/financial data undeletable via a direct Auth-layer delete.

| Table | Column | Category | Current | Change to |
|---|---|---|---|---|
| `predmeti` | `user_id` | Legal | CASCADE | **RESTRICT** |
| `predmet_dokumenti` | `user_id` | Legal | CASCADE | **RESTRICT** |
| `predmet_hronologija` | `user_id` | Legal | CASCADE | **RESTRICT** |
| `predmet_beleske` | `user_id` | Legal | CASCADE | **RESTRICT** |
| `predmet_istorija` | `user_id` | Legal | CASCADE | **RESTRICT** |
| `predmet_delegiranja` | `od_user_id`, `na_user_id` | Legal | CASCADE | **RESTRICT** |
| `fakture` | `user_id` | Financial | CASCADE | **RESTRICT** |
| `billing_entries` | `user_id` | Financial | CASCADE | **RESTRICT** |
| `timer_sessions` | `user_id` | Financial | CASCADE | **RESTRICT** |
| `tarife` | `user_id` | Financial | CASCADE | **RESTRICT** |
| `tarifne_stavke_custom` | `user_id` | Financial | CASCADE | **RESTRICT** |
| `sef_log` | `user_id` | Financial/tax-audit | CASCADE | **RESTRICT** |
| `praceni_predmeti` | `user_id` | Legal (monitored cases) | CASCADE | **RESTRICT** |
| `rocista` | `user_id` | Legal (court hearings) | CASCADE | **RESTRICT** |
| `smart_contract_analyses` | `user_id` | Legal/compliance | CASCADE | **RESTRICT** |
| `tos_acceptances` | `user_id` | Consent/audit — see note below | CASCADE | **RESTRICT** |

**16 tables, 17 constraints.** `tos_acceptances` is included even though it's not "legal case" or "financial" in the usual sense: it is evidence that a user actually accepted the Terms of Service at a given time — the same reasoning that keeps `audit_immutable` permanent applies here at a smaller scale (a consent record that can vanish is a consent record that can't later be proven). Flagging this reasoning explicitly since it's a judgment call, not a mechanical categorization.

### Tier B — Recommended, but a related and distinct finding from SEC-031's original scope

`predmeti`/`klijenti` children still cascade if `predmeti`/`klijenti` rows are deleted **directly** (not via `auth.users`) — e.g., a bug in a "delete this case" admin feature, or a future script. Tier A does not protect against this because it's a different trigger (§0's protection is specifically about the `auth.users`-initiated chain). Same failure shape, same irreversibility, worth closing at the same time since the migration mechanism is identical, but this is technically adjacent to SEC-031 as scoped (auth.users cascade) rather than the same finding — noting the distinction so it isn't silently folded in without being named.

| Table | Column | Parent | Current | Change to |
|---|---|---|---|---|
| `predmet_dokumenti` | `predmet_id` | `predmeti` | CASCADE | RESTRICT (recommended) |
| `predmet_hronologija` | `predmet_id` | `predmeti` | CASCADE | RESTRICT (recommended) |
| `predmet_beleske` | `predmet_id` | `predmeti` | CASCADE | RESTRICT (recommended) |
| `predmet_istorija` | `predmet_id` | `predmeti` | CASCADE | RESTRICT (recommended) |
| `predmet_komentari` | `predmet_id` | `predmeti` | CASCADE | RESTRICT (recommended) |
| `predmet_klijenti` | `predmet_id`, `klijent_id` | `predmeti`, `klijenti` | CASCADE | RESTRICT (recommended) |
| `predmet_dokazi` | `predmet_id` | `predmeti` | CASCADE | RESTRICT (recommended) |
| `rocista` | `predmet_id` | `predmeti` | CASCADE | RESTRICT (recommended) |
| `timer_sessions` | `predmet_id` | `predmeti` | CASCADE | RESTRICT (recommended) |
| `tarife` | `klijent_id` | `klijenti` | CASCADE | RESTRICT (recommended) |
| `predmet_delegiranja` | `predmet_id` | `predmeti` | CASCADE | RESTRICT (recommended) |

**Deliberately excluded even from Tier B** (recommend leaving as CASCADE): `predmet_health_log.predmet_id`, `notifications.predmet_id`, `twin_simulacije.predmet_id`, `simulator_partije.predmet_id` — these are derived/computed/notification data, reproducible or disposable, not source-of-truth legal/financial content. Locking these too would add friction (blocking legitimate case-closure flows, if any exist) without protecting anything irreplaceable.

### Explicitly left as CASCADE — no change recommended

Operational, session, log, notification, and template tables: `user_roles`, `sef_podesavanja`, `recurring_templates`, `email_log`, `usage_events`, `notifications`, `korisnik_sms_profil`, `korisnik_plan`, `korisnik_usage`, `onboarding_email_log`, `apr_lookup_log`, `korisnik_viber_profil`, `notification_log`, `support_tickets`, `cio_dnevni_izvestaj`, `twin_simulacije`, `onboarding_state`, `user_knowledge`, `simulator_partije`, `whatsapp_pretplate`, `whatsapp_send_log`, `aktivne_sesije`, `portal_status_log`, `user_credits`, `predmet_health_log`. None of these hold irreplaceable legal or financial source data; per §0, locking them provides no additional protection once the Tier A tables are RESTRICT (the transaction fails before reaching them anyway, for any account that matters) while narrowing them further would only add operational friction for the rare account that has nothing but disposable data.

### A separate, adjacent finding surfaced while building this plan — `klijenti` has no FK to `auth.users` at all

`klijenti.user_id` is declared `TEXT NOT NULL` (`supabase_setup.sql:570`) with **no foreign key constraint whatsoever** — not `CASCADE`, not `RESTRICT`, nothing. This means client records are *already* immune to SEC-031's specific cascade mechanism (a small positive, discovered by accident rather than by design), but it also means there is **zero database-level referential integrity** binding a client record to a real user — an orphaned or typo'd `user_id` would currently go undetected at the schema level, and adding real protection here isn't a CASCADE→RESTRICT flip like the rest of this plan; it would require first adding a proper FK constraint (and reconciling `TEXT` vs. the `UUID` type used everywhere else, e.g. `predmet_klijenti.klijent_id UUID REFERENCES klijenti(id)`). **Out of scope for this Phase 1 plan** (it's an "add integrity" migration, not a "restrict an existing cascade" migration) — recorded here so it isn't lost; recommend a separate, small follow-up finding (call it `SEC-033`) for the Gap Register rather than scope-creeping this plan.

---

## 2. Tables grouped by category (as requested)

| Category | Tables | Phase 1 treatment |
|---|---|---|
| **Legal records** | `predmeti`, `predmet_dokumenti`, `predmet_hronologija`, `predmet_beleske`, `predmet_istorija`, `predmet_komentari`, `predmet_klijenti`, `predmet_dokazi`, `predmet_delegiranja`, `praceni_predmeti`, `rocista`, `smart_contract_analyses` | Tier A/B — RESTRICT |
| **Financial records** | `fakture`, `billing_entries`, `timer_sessions`, `tarife`, `tarifne_stavke_custom`, `sef_log` | Tier A/B — RESTRICT |
| **User profile data** | `profiles`, `user_roles`, `korisnik_sms_profil`, `korisnik_viber_profil`, `whatsapp_pretplate`, `tos_acceptances` | `profiles` stays CASCADE (deleting the identity record on account closure is the *intended* effect, not a risk — nothing else references `profiles` directly, everything else references `auth.users`); `tos_acceptances` moves to RESTRICT as consent evidence (Tier A); the rest stay CASCADE |
| **Operational data** | `usage_events`, `korisnik_plan`, `korisnik_usage`, `cio_dnevni_izvestaj`, `apr_lookup_log`, `aktivne_sesije`, `support_tickets`, `onboarding_state`, `user_knowledge`, `twin_simulacije`, `simulator_partije`, `sef_podesavanja`, `recurring_templates`, `predmet_health_log`, `user_credits` | Stay CASCADE |
| **Temporary/log data** | `email_log`, `onboarding_email_log`, `notification_log`, `notifications`, `whatsapp_send_log`, `portal_status_log` | Stay CASCADE |

---

## 3. Migration order, dependency risks, rollback strategy

### Migration mechanics
Postgres has no `ALTER CONSTRAINT ... ON DELETE` form — changing a delete action requires `DROP CONSTRAINT` followed by `ADD CONSTRAINT ... REFERENCES ... ON DELETE RESTRICT` for each FK. This is a metadata-only operation (no table rewrite, no data scan) but each `DROP`/`ADD CONSTRAINT` pair briefly takes an `ACCESS EXCLUSIVE` lock on the child table — real but sub-second on tables this size, `NOT VERIFIED` against actual production row counts.

### Order
1. **No cross-table ordering dependency exists** — each constraint change is independent (they don't reference each other), so there is no correctness-driven sequence requirement. Recommend, for operational clarity rather than correctness: Tier A first (auth.users-level, the actual SEC-031 fix), Tier B second (predmeti/klijenti-level, the adjacent hardening), as two separate migration files/commits — so Tier A can be deployed and verified independently even if Tier B needs more review time.
2. Within Tier A, no sub-ordering is required — all 17 constraints can be changed in a single transaction.
3. Run during a low-traffic window out of caution for lock acquisition, even though the expected lock duration is short — standard practice for any `ACCESS EXCLUSIVE`-taking DDL, `NOT VERIFIED` as strictly necessary at this table size but costs nothing to schedule conservatively.

### Dependency risk assessment (checked directly, not assumed)
- **Application code**: grepped the entire codebase for any call to Supabase's user-deletion admin API (`auth.admin.deleteUser`/`delete_user`) — **zero call sites found**. The only `auth.admin.*` calls in the codebase are `create_user` (`api.py:2082`) and `sign_out` (`api.py:2226`). No application code path performs or depends on a hard `auth.users` delete today.
- **GDPR endpoint**: already confirmed in `SEC031_IMPACT_ANALYSIS.md` §4 — `routers/gdpr.py` never touches `auth.users`, so this migration has zero interaction with the existing (separately-flagged, SEC-002) erasure flow. Applying this migration does not change SEC-002's behavior at all, for better or worse.
- **Test suite**: grepped `tests/` for any test performing or asserting on an `auth.users` deletion — none found.
- **Net assessment**: this migration has no known live dependency to break. The only thing it changes is that an action nobody's code currently performs (and that only an operator manually using the Supabase dashboard or Admin API could trigger) will now fail loudly instead of succeeding silently and catastrophically.

### Rollback strategy
Each `ADD CONSTRAINT` can be reverted by its own `DROP CONSTRAINT` + `ADD CONSTRAINT ... ON DELETE CASCADE` (restoring the original definition) — fully reversible, no data was ever touched or lost by this migration in either direction, since it only ever changes constraint metadata. Recommend keeping the exact original constraint names and definitions recorded in the migration file's own down/rollback section (or a paired "down" script) so rollback doesn't require re-deriving the original CASCADE definitions from this document.

---

## 4. Required regression tests

| Test | Setup | Action | Expected result |
|---|---|---|---|
| **User deletion attempt (protected account)** | Create a test user with at least one `predmet` (or a row in any Tier A table) | Attempt `DELETE FROM auth.users WHERE id = <test_user>` directly (simulating the Supabase Admin API / dashboard path) | **Fails** with a foreign-key-violation error; the `auth.users` row and all dependent rows remain fully intact, unchanged, queryable |
| **User deletion attempt (clean account)** | Create a test user with zero rows in any Tier A table (fresh signup, nothing created) | Same direct deletion attempt | **Succeeds** — confirms the migration doesn't over-lock accounts that have no legal/financial footprint to protect |
| **GDPR flow unaffected** | Existing `tests/test_gdpr_delete.py` suite | Run unchanged | **Passes exactly as before** — confirms this migration doesn't interact with or break the existing (separately-tracked, SEC-002) GDPR erasure endpoint, since it never touched `auth.users` in the first place |
| **Legitimate data access unaffected** | Normal authenticated user with `predmeti`/`fakture`/etc. | Run the full existing test suite (currently 1725 tests per SEC-001's closure) | **Passes unchanged** — confirms this is a pure constraint-metadata change with zero effect on any read/write path that isn't a direct `auth.users` deletion |
| **Admin operations unaffected** | `supa.auth.admin.create_user` and `supa.auth.admin.sign_out` (the only two `auth.admin.*` call sites in the codebase) | Exercise both | **Both succeed unchanged** — neither performs a delete, so neither is affected by this migration |
| **Tier B — direct `predmeti` deletion (if Tier B is included)** | A `predmeti` row with children in each Tier-B table | Attempt `DELETE FROM predmeti WHERE id = <test_predmet>` directly | **Fails** with a foreign-key-violation error, same reasoning as the primary test, extended to the adjacent finding |

All six should be written as explicit, isolated regression tests (matching the discipline already used for `tests/test_sec001_predmet_ownership.py`) once this plan is approved and an actual migration is written — not written yet, since this document is the plan, not the implementation.

---

## 5. What this document does not do

- Does not write or run any migration file.
- Does not change any schema, constraint, or data.
- Does not implement the lifecycle model from `SEC031_REMEDIATION_DESIGN.md` (Phase 2, explicitly deferred pending SEC-002's legal-confirmation items).
- Does not fix `klijenti`'s missing FK constraint (flagged as a new, separate candidate finding, `SEC-033`, not folded into this plan's scope).
- Does not decide the low-traffic deployment window's exact timing — an operational scheduling detail for whoever runs the eventual migration.

## Recommendation summary

1. Phase 1 (this plan, Tier A minimum, Tier B recommended) is independent of and does not need to wait for SEC-002's retention-duration legal questions — it answers "can an accidental delete destroy legal data" (no legal judgment required), not "how long must we keep it" (which does).
2. 16 tables / 17 constraints (Tier A) are sufficient to close SEC-031 as scoped, due to Postgres's atomic-transaction FK-check behavior (§0) — not a large migration.
3. Zero known application dependency on the current CASCADE behavior — checked directly (codebase grep, test suite grep), not assumed.
4. Fully reversible — constraint-metadata-only change, no data touched in either direction.
5. `klijenti`'s missing FK is a related but separate, smaller finding (`SEC-033`) worth its own Gap Register row, not in this plan's scope.
6. **This document does not authorize writing or running the migration.** That remains the next explicit decision point, separate from this plan being reviewed and approved.

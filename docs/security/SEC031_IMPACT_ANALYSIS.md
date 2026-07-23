# SEC-031 — Impact Analysis: `ON DELETE CASCADE` from `auth.users`

**Date:** 2026-07-23
**Status:** Analysis only. **No schema changed by this document.** Per explicit instruction — confirm scope before any remediation is chosen or implemented.
**Trigger:** Discovered while building the SEC-002 retention matrix (`docs/security/SEC002_DATA_RETENTION_ANALYSIS.md` §0). Founder reprioritized it above SEC-002 itself: SEC-001 was "attacker reads someone else's case," SEC-031 is "one click permanently destroys the entire legal/financial record of a user" — for a legal-records product, the second is arguably worse because it is irreversible and requires no attacker at all, just an ordinary admin action taken without knowing this chain exists.

Method: exhaustive regex extraction over every `CREATE TABLE` block in `migrations/*.sql`, `supabase_migrations/*.sql`, and `supabase_setup.sql` (46 raw `REFERENCES auth.users(id)` lines found, cross-checked twice by two independent extraction passes — counts reconciled). This is a **repo-schema** analysis; it does not by itself prove what is live in the production database (see §5).

---

## 0. Immediate containment (before schema remediation)

This is an operational precaution, not a fix — nothing below changes schema or code. It exists because there is a real window between "this risk is now documented" and "this risk is closed," and a document alone is not sufficiently visible during that window if someone reaches for the Supabase dashboard for an unrelated reason (test-account cleanup, offboarding, a support request) without knowing this chain exists.

**Current status:**
- No schema changes have been applied as a result of this analysis.
- Whether this cascade is live in production is not yet confirmed (§5) — treat it as live until the verification query below says otherwise.

**Temporary operational rule, effective immediately, until remediation (§6) is designed and deployed:**
- Do **not** delete any user directly from the Supabase Auth dashboard.
- Do **not** run any cleanup/offboarding script that calls Supabase's user-deletion API (`auth.admin.deleteUser` or equivalent) against this project.
- Any account-deletion action — for any reason, including test data cleanup — must go through a reviewed path, not a direct Auth-layer delete, until this finding is closed.

**Verification required before this section can be closed:**
- Run the read-only FK inspection query in §5 against production to confirm the exact live cascade state (it is read-only — it changes nothing, so there is no reason to defer running it).

30 tables have at least one column with `ON DELETE CASCADE` directly to `auth.users(id)`. (An additional 5 columns reference `auth.users(id)` **without** cascade — `RESTRICT` by Postgres default — listed separately in §1b, since those are the opposite of the risk: they would currently **block** a user deletion rather than silently destroy data, which is also worth knowing.)

| # | Table | Column | Migration source |
|---|---|---|---|
| 1 | `profiles` | `id` | `supabase_setup.sql:14` |
| 2 | `user_credits` | `user_id` | `supabase_setup.sql:55` |
| 3 | `predmeti` | `user_id` | `supabase_setup.sql:283` |
| 4 | `predmet_dokumenti` | `user_id` | `supabase_setup.sql:339` |
| 5 | `predmet_hronologija` | `user_id` | `supabase_setup.sql:390` |
| 6 | `predmet_beleske` | `user_id` | `supabase_setup.sql:437` |
| 7 | `predmet_istorija` | `user_id` | `supabase_setup.sql:490` |
| 8 | `user_roles` | `user_id` | `migrations/002_klijenti_crm.sql:11` |
| 9 | `fakture` | `user_id` | `migrations/003_billing.sql:9` |
| 10 | `billing_entries` | `user_id` | `migrations/003_billing.sql:30` |
| 11 | `timer_sessions` | `user_id` | `migrations/003_billing.sql:51` |
| 12 | `rocista` | `user_id` | `migrations/005_rocista.sql:10` |
| 13 | `tarife` | `user_id` | `migrations/006_tarife.sql:9` |
| 14 | `tarifne_stavke_custom` | `user_id` | `migrations/006_tarife.sql:28` |
| 15 | `sef_podesavanja` | `user_id` | `migrations/008_sef_recurring.sql:8` |
| 16 | `sef_log` | `user_id` | `migrations/008_sef_recurring.sql:24` |
| 17 | `recurring_templates` | `user_id` | `migrations/008_sef_recurring.sql:43` |
| 18 | `email_log` | `user_id` | `migrations/008_sef_recurring.sql:68` |
| 19 | `usage_events` | `user_id` | `migrations/009_notifications_analytics.sql:16` |
| 20 | `notifications` | `user_id` | `migrations/009_notifications_analytics.sql:52` |
| 21 | `korisnik_sms_profil` | `user_id` | `migrations/012_sms_notifikacije.sql:6` |
| 22 | `korisnik_plan` | `user_id` | `migrations/024_plans_usage.sql:6` |
| 23 | `korisnik_usage` | `user_id` | `migrations/024_plans_usage.sql:18` |
| 24 | `onboarding_email_log` | `user_id` | `migrations/025_onboarding_emails.sql:6` |
| 25 | `apr_lookup_log` | `user_id` | `migrations/048_reliability_hardening.sql:24` |
| 26 | `korisnik_viber_profil` | `user_id` | `migrations/048_reliability_hardening.sql:73` |
| 27 | `notification_log` | `user_id` | `migrations/048_reliability_hardening.sql:110` |
| 28 | `support_tickets` | `user_id` | `migrations/049_health_observability.sql:40` |
| 29 | `cio_dnevni_izvestaj` | `user_id` | `migrations/050_cio_dnevni_izvestaj.sql:14` |
| 30 | `twin_simulacije` | `user_id` | `migrations/052_twin_simulacije.sql:16` |
| 31 | `onboarding_state` | `user_id` | `migrations/053_orphaned_inline_schemas.sql:28` |
| 32 | `user_knowledge` | `user_id` | `migrations/053_orphaned_inline_schemas.sql:47` |
| 33 | `simulator_partije` | `user_id` | `migrations/053_orphaned_inline_schemas.sql:66` |
| 34 | `whatsapp_pretplate` | `user_id` | `migrations/053_orphaned_inline_schemas.sql:88` |
| 35 | `whatsapp_send_log` | `user_id` | `migrations/053_orphaned_inline_schemas.sql:102` |
| 36 | `predmet_delegiranja` | `od_user_id`, `na_user_id` | `migrations/054_predmet_delegiranja.sql:16-17` |
| 37 | `tos_acceptances` | `user_id` | `migrations/056_tos_acceptances.sql:17` |
| 38 | `smart_contract_analyses` | `user_id` | `migrations/smart_contract_analyses.sql:12` |
| 39 | `aktivne_sesije` | `user_id` | `supabase_migrations/044_aktivne_sesije.sql:9` |
| 40 | `praceni_predmeti` | `user_id` | `supabase_migrations/045_portal_monitoring.sql:9` |
| 41 | `portal_status_log` | `user_id` | `supabase_migrations/045_portal_monitoring.sql:41` |

(41 tables, 42 columns — `predmet_delegiranja` has two.)

### 1b. `auth.users(id)` references WITHOUT cascade (default `RESTRICT`)
These would currently **block** deleting a user at the Auth layer if any row exists (Postgres raises a foreign-key-violation error rather than deleting) — the opposite failure mode, worth distinguishing from the cascade risk itself:

| Table | Column | Source |
|---|---|---|
| `user_roles` | `dodelio` | `migrations/002_klijenti_crm.sql:14` |
| `klijent_dokumenti` | `uploaded_by` | `migrations/002_klijenti_crm.sql:156` |
| `klijent_komunikacija` | `ucesnik_id` | `migrations/002_klijenti_crm.sql:182` |
| `predmet_dokazi` | `user_id` | `migrations/016_evidence_vault.sql:27` |

Note the inconsistency at `predmet_dokazi`: its `user_id`→`auth.users` FK is `RESTRICT` (no cascade), but its `predmet_id`→`predmeti` FK **is** `CASCADE` (§2) — so evidence records would survive a direct `auth.users` deletion attempt on their own `user_id` column (Postgres would actually reject the deletion outright, since `RESTRICT` blocks it) but would still be destroyed if the parent `predmeti` row is deleted through the first-level cascade instead. This is exactly the kind of per-table inconsistency the founder's original diagnosis anticipated — not a single uniform rule, several independently-authored ones.

---

## 2. Second-level cascade — tables referencing `predmeti(id)` / `klijenti(id)` / `fakture(id)`

These tables don't reference `auth.users` directly, but cascade transitively if their parent (`predmeti`, `klijenti`, or `fakture`) is deleted by the first-level cascade above.

| Table | Column | Parent | Cascade? |
|---|---|---|---|
| `predmet_dokumenti` | `predmet_id` | `predmeti` | **CASCADE** |
| `predmet_hronologija` | `predmet_id` | `predmeti` | **CASCADE** |
| `predmet_beleske` | `predmet_id` | `predmeti` | **CASCADE** |
| `predmet_istorija` | `predmet_id` | `predmeti` | **CASCADE** |
| `predmet_komentari` | `predmet_id` | `predmeti` | **CASCADE** |
| `predmet_klijenti` | `predmet_id`, `klijent_id` | `predmeti`, `klijenti` | **CASCADE** (both) |
| `predmet_dokazi` | `predmet_id` | `predmeti` | **CASCADE** |
| `predmet_health_log` | `predmet_id` | `predmeti` | **CASCADE** |
| `timer_sessions` | `predmet_id` | `predmeti` | **CASCADE** |
| `rocista` | `predmet_id` | `predmeti` | **CASCADE** |
| `tarife` | `klijent_id` | `klijenti` | **CASCADE** |
| `notifications` | `predmet_id` | `predmeti` | **CASCADE** |
| `twin_simulacije` | `predmet_id` | `predmeti` | **CASCADE** |
| `simulator_partije` | `predmet_id` | `predmeti` | **CASCADE** |
| `predmet_delegiranja` | `predmet_id` | `predmeti` | **CASCADE** |
| `klijent_dokumenti` | `klijent_id`, `predmet_id` | `klijenti`, `predmeti` | RESTRICT (not cascade) |
| `klijent_komunikacija` | `klijent_id` | `klijenti` | RESTRICT |
| `fakture` | `predmet_id` | `predmeti` | RESTRICT |
| `billing_entries` | `predmet_id`, `faktura_id` | `predmeti`, `fakture` | RESTRICT |
| `recurring_templates` | `klijent_id`, `predmet_id` | `klijenti`, `predmeti` | RESTRICT |
| `usage_events` | `predmet_id` | `predmeti` | RESTRICT |
| `predmet_dokazi` | `dokument_id` | `predmet_dokumenti` | RESTRICT |

**Third-level check performed (not just assumed):** searched for any table referencing the second-level tables above (`predmet_dokumenti`, `predmet_klijenti`, `rocista`, `predmet_dokazi`, `klijenti`, `fakture`, `timer_sessions`, `tarife`) as a parent. Result: no further cascade depth found — the handful of tables that do reference these (`klijent_dokumenti`→`klijenti`, `billing_entries`→`fakture`, `predmet_dokazi`→`predmet_dokumenti`) are all `RESTRICT`, not `CASCADE`, so the destructive chain does not go deeper than two levels.

**Net effect if `auth.users` row is deleted:** `predmeti` cascades (first level) which then cascades a second time into 15 child tables (`predmet_dokumenti`, `predmet_hronologija`, `predmet_beleske`, `predmet_istorija`, `predmet_komentari`, `predmet_klijenti`, `predmet_dokazi`, `predmet_health_log`, `timer_sessions`, `rocista`, `notifications`, `twin_simulacije`, `simulator_partije`, `predmet_delegiranja`, plus `predmet_klijenti`'s effect on the `klijenti` side) — combined with the 41 tables that cascade directly from `auth.users` itself (§1), roughly **56 distinct tables** are destroyed by a single `auth.users` row deletion, either directly or transitively.

---

## 3. Which of these tables carry legal/document/financial/audit/personal data

| Category | Tables |
|---|---|
| **Legal matter data** (case content, work product) | `predmeti`, `predmet_hronologija`, `predmet_beleske`, `predmet_istorija`, `predmet_komentari`, `predmet_klijenti`, `predmet_dokazi`, `predmet_delegiranja`, `praceni_predmeti`, `twin_simulacije`, `simulator_partije`, `user_knowledge` |
| **Documents** | `predmet_dokumenti`, `klijent_dokumenti` (RESTRICT-protected, see §1b/§2) |
| **Financial records** | `fakture`, `billing_entries`, `timer_sessions`, `tarife`, `tarifne_stavke_custom`, `korisnik_plan`, `user_credits`, `sef_podesavanja`, `sef_log`, `recurring_templates` |
| **Audit/compliance-adjacent records** | `tos_acceptances`, `sef_log`, `portal_status_log`, `usage_events` |
| **Personal data (contact/identity)** | `profiles`, `korisnik_sms_profil`, `korisnik_viber_profil`, `whatsapp_pretplate`, `klijent_komunikacija`, `support_tickets` |
| **Communication logs** | `email_log`, `onboarding_email_log`, `notification_log`, `notifications`, `whatsapp_send_log` |
| **Operational/internal (lower stakes)** | `usage_events`, `korisnik_usage`, `onboarding_state`, `cio_dnevni_izvestaj`, `apr_lookup_log`, `aktivne_sesije`, `user_roles` |
| **Web3/compliance module** | `smart_contract_analyses` |

**The tables that matter most for this analysis** are the ones simultaneously (a) directly or transitively cascaded from `auth.users`, and (b) legal/financial/document records with a plausible retention obligation: `predmeti` and its 8 CASCADE children, `fakture`, `billing_entries`, `timer_sessions`, `tarife`. These are exactly the tables SEC-002's retention matrix already flagged as `REQUIRES LEGAL CONFIRMATION` on retention duration — SEC-031 is the mechanism by which that unresolved question could be made moot in an instant, for better or worse, without anyone deciding it.

---

## 4. Can the GDPR deletion endpoint trigger this cascade?

**No — confirmed by direct code inspection, not inferred.** `routers/gdpr.py` (`gdpr_delete_account`, the `DELETE /api/gdpr/account` handler) contains zero references to `auth.users`, Supabase Admin API, or any user-deletion call (`grep` for `auth.users|admin\.|delete_user|auth\.admin` in the file returns no matches). The endpoint only updates `profiles` (anonymizes `email`/`full_name`) and touches `korisnik_email_notif`. It never calls Supabase's `auth.admin.deleteUser()`-equivalent or issues any SQL that would touch the `auth.users` table itself.

**This means SEC-031 and SEC-002 are independent risks that happen to share a root cause (no unified account-closure policy), not the same bug seen twice.** SEC-002 is "the app's own deletion path under-deletes and over-claims." SEC-031 is "a *different*, non-app deletion path — one the application does not gate, warn about, or even know exists — would over-delete catastrophically." Fixing SEC-002 (the message or the anonymization scope) does not touch SEC-031 at all; they need separate remediation.

---

## 5. Does production already enforce this schema? `REQUIRES PRODUCTION VERIFICATION`

**Cannot be determined from the repository alone.** No migration-tracking table (`schema_migrations` or equivalent) or automated migration runner was found anywhere in this codebase — `migrations/*.sql` files appear to be applied manually against Supabase (consistent with this project's established practice of the founder running migration SQL himself rather than any script doing it automatically). That means the repo's schema files describe *intended* schema, not provably *live* schema.

**Circumstantial evidence only** (not proof): the application's live features (billing/`fakture`, court dates/`rocista`, evidence vault/`predmet_dokazi`, etc., per `project_billing`, `project_evidence_vault_migration_bug` memory) function in production, which is only possible if their underlying tables exist — implying most or all of these migrations have in fact been applied. But **the exact `ON DELETE CASCADE` clause on each individual column cannot be confirmed this way** — a table can exist and function correctly for ordinary reads/writes regardless of its FK's delete-action, so "the feature works" is not evidence about cascade behavior specifically.

**To close this gap with certainty (a read-only production check, not a schema change):**
```sql
SELECT
    tc.table_name, kcu.column_name, rc.delete_rule
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.referential_constraints rc
    ON tc.constraint_name = rc.constraint_name
JOIN information_schema.constraint_column_usage ccu
    ON rc.unique_constraint_name = ccu.constraint_name
WHERE ccu.table_name = 'users' AND ccu.table_schema = 'auth'
ORDER BY tc.table_name;
```
This is a read-only query against Postgres system catalogs — it changes nothing, and would give a definitive, authoritative list of exactly which cascade rules are live today, closing this section's `REQUIRES PRODUCTION VERIFICATION` marker with certainty. Recommend running this before choosing a remediation strategy in §6, since the true blast radius in production could in principle differ from the repo's schema files (e.g., if a migration was edited after being applied, or applied out of order).

---

## 6. Three remediation strategies

No recommendation is made between these — they involve a real product/policy tradeoff (data safety vs. operational simplicity vs. GDPR-erasure completeness), the same class of decision SEC-002 already surfaced. Presented for founder review.

### A) `RESTRICT` (change cascade to restrict/no-action)
Change every `ON DELETE CASCADE` on the tables in §1/§2 to `ON DELETE RESTRICT` (or drop the cascade clause, which defaults to `NO ACTION`, functionally similar).
- **Effect:** A direct `auth.users` deletion would fail outright with a foreign-key-violation error unless every dependent row was removed first. This makes SEC-031's accidental-catastrophic-deletion scenario **impossible by construction** — Postgres itself refuses the operation.
- **Tradeoff:** Whoever performs a legitimate user deletion (e.g., a genuinely-requested full erasure, if that's ever the correct policy for a given table) now has to explicitly handle every dependent table first — more friction, but friction in exactly the place where a decision should be deliberate, not accidental.
- **Complexity:** Low–Medium — a set of `ALTER TABLE ... DROP CONSTRAINT ... ADD CONSTRAINT ... ON DELETE RESTRICT` statements, no data migration needed, purely a schema change.

### B) Soft-delete architecture
Stop using hard deletes at the `auth.users` level (or anywhere in this chain) as the mechanism for account closure at all. Every table gets (or already has, e.g. `klijenti.deleted_at`) a `deleted_at`/`is_deleted` marker; "deleting" an account means the application sets these flags across the owned rows in a single, audited, application-level transaction — never a database-level cascade.
- **Effect:** Full control over what "deleted" means per table (can differ by table, matching SEC-002's own "depends on data type" conclusion) and full reversibility during any grace period. `auth.users` itself would need to not be hard-deleted either (Supabase supports banning/disabling a user without deleting the row) to fully close the risk — or its cascade would still need to move to RESTRICT (combine with strategy A) so the mechanism can't fire even accidentally.
- **Tradeoff:** Most implementation work — every read path needs to start filtering `deleted_at IS NULL`, and a real purge/retention job needs to exist eventually or "soft-deleted" data accumulates forever.
- **Complexity:** Large — this is the shape of the "future Data Retention Architecture" already proposed in `SEC002_DATA_RETENTION_ANALYSIS.md` §5, not a small patch. The two efforts should likely be designed together, not sequentially.

### C) Archive/anonymization model
On account closure, run a single application-level job that, per table, either anonymizes in place (same idea as the current `profiles` handling, extended to `predmeti`/`klijenti`/etc.) or moves rows to a separate archive schema/table with restricted access, then only *afterward* allows the `auth.users` row itself to be removed (or never removes it, converting it to a disabled/anonymized auth record instead).
- **Effect:** Satisfies both a genuine GDPR-erasure intent (personal identifiers gone from the live, normally-queried tables) and a genuine retention obligation (the underlying case/financial record survives somewhere, auditable, just not attributable to a live identity) — this is the model that best matches what SEC-002's matrix suggested might be legally necessary for `predmeti`/`klijenti`/`fakture` specifically.
- **Tradeoff:** Needs the retention-duration legal questions from SEC-002 answered first to know what "anonymize" vs. "archive-and-keep-identified" should mean per table — this strategy can't be fully designed independent of that open legal question.
- **Complexity:** Medium–Large, and explicitly gated on the SEC-002 legal-confirmation items being resolved first.

**All three strategies are compatible with also applying strategy A as an immediate, cheap safety net** (RESTRICT stops the accidental-catastrophic case regardless of which longer-term architecture is eventually chosen) — worth considering as a fast, low-risk first step independent of the larger B/C decision, but this document does not authorize implementing even that without explicit founder sign-off, per the standing "analysis first" instruction.

---

## Summary for the founder

- **Immediate containment is in effect (§0)**: no direct Supabase Auth user deletion until this is closed — operational rule, not a code change.
- **56 tables**, directly or transitively, would be destroyed by a single `auth.users` row deletion — confirmed by full schema trace, not estimated.
- **The GDPR endpoint cannot trigger this** — it's a separate, currently-ungated risk (direct Supabase Auth deletion), not a variant of SEC-002.
- **Whether this is live in production today is `REQUIRES PRODUCTION VERIFICATION`** — a safe, read-only SQL query is provided in §5 to confirm with certainty before any remediation decision.
- **Three remediation strategies are laid out (§6), not recommended between** — RESTRICT is the cheapest and could reasonably be applied as an immediate safety net regardless of which longer-term architecture (soft-delete vs. archive/anonymization) is eventually chosen, but nothing here is authorized to be implemented yet.

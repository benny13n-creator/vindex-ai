# SEC-031 — Production Execution Log

**Date:** 2026-07-23
**Status:** `migrations/077_sec031_restrict_auth_users_cascade.sql` (v4) **successfully applied against production**. This is the closing document for the entire SEC-031 chain — Impact Analysis → Remediation Design → Migration Safety Plan → FK Graph → Production Assumptions → Migration Dry Run → Peer Review → v1/v2/v3/v4 migration file → **this execution log**. SEC-031 moves to **Stage 9 — Closed** on `docs/security/FINDING_LIFECYCLE.md`'s 9-stage model: not just "Verified Fix" (tests pass) but "Production Verified" (confirmed correct in the real environment) and now formally closed.

---

## What actually happened, step by step

Executed directly by the founder in the Supabase SQL Editor, verified after each step via read-only queries — not assumed at any point.

1. **First attempt (v1, hardcoded constraint names) failed on the very first statement**: `predmet_delegiranja_od_user_id_fkey` did not exist under that name. GRUPA 1's transaction rolled back cleanly — **zero rows touched**, exactly the safety property the plan was designed to guarantee.
2. Rewrote the migration (v2) to look up real constraint names via `pg_constraint` instead of assuming a naming convention.
3. Founder ran the read-only diagnostic query (`SELECT ... FROM pg_constraint WHERE confrelid = 'auth.users'::regclass AND contype='f'`) — revealed the real cause was deeper than naming: **3 of the 19 originally-approved pairs did not exist in production at all** (`predmet_delegiranja`, `conversations`, `tos_acceptances`). Migration revised to v3, removing these 3 pending investigation.
4. Investigated each:
   - `predmet_delegiranja`: its own migration (`054_predmet_delegiranja.sql`) had a header comment stating it was never run. **Founder ran migration 054.**
   - `tos_acceptances`: unexplained at the time — its migration (`056_tos_acceptances.sql`) was a normal numbered migration, not a legacy file. **Founder ran migration 056.** (This migration's own header comment revealed a separate, more urgent finding — see §"Other findings" below.)
   - `conversations`: confirmed legacy/dead, permanently excluded — not investigated further, no code depends on it.
5. Founder confirmed via a targeted existence check (`to_regclass`) that both `predmet_delegiranja` and `tos_acceptances` now existed. Migration revised to v4, restoring both to the active run (18 pairs total).
6. **GRUPA 1 (8 pairs) failed again**: `predmet_delegiranja.od_user_id` had no FK to `auth.users` — the table had existed in production *before* migration 054 was run today, in a bare form (only `id`, `predmet_id`, `od_user_id`, `na_user_id`, `napomena`, `status`, `created_at` columns and a bare `PRIMARY KEY`, confirmed via `information_schema.columns` and `pg_constraint`). Because migration 054 uses `CREATE TABLE IF NOT EXISTS`, its entire body — the FK constraints, RLS, policies, indexes — was silently skipped, even though the migration "ran successfully" with no error. Founder manually added the two missing FKs (`od_user_id`, `na_user_id` → `auth.users(id) ON DELETE CASCADE`, matching migration 054's original specification exactly) directly in production. GRUPA 1 re-run, verified: all 8 pairs `RESTRICT`.
7. **GRUPA 2 (6 pairs, financial) succeeded on the first try** — verified: all 6 `RESTRICT`.
8. **GRUPA 3 (4 pairs) failed on `tos_acceptances`**: identical pattern — the table already existed with only `PRIMARY KEY` and `UNIQUE(user_id, version)`, no FK to `auth.users`, so migration 056's FK/RLS/policies were silently skipped the same way. Founder manually added the missing FK (`user_id` → `auth.users(id) ON DELETE CASCADE`, matching migration 056's spec). GRUPA 3 re-run, verified: all 4 pairs `RESTRICT`.
9. **Final comprehensive verification**: a single query for every `auth.users`-referencing FK with `RESTRICT` in its definition returned all 18 expected pairs, nothing missing, nothing extra.

**Total real-world outcome: 18/18 confirmed `ON DELETE RESTRICT` in production, zero data touched at any point, two genuine rollbacks (both clean, both recovered), two real gaps found and fixed along the way that were outside SEC-031's own original scope.**

---

## Other findings surfaced during this execution (not SEC-031 itself)

### SEC-034 (new) — "IF NOT EXISTS" migrations can silently no-op against a pre-existing partial table

Both `predmet_delegiranja` and `tos_acceptances` existed in production, in bare/incomplete form (columns and a primary key only, missing every FK, every RLS policy, every index their real migration defines) **before** their respective numbered migrations were ever run today. Because both migrations use `CREATE TABLE IF NOT EXISTS`, running them produced no error and no indication anything was wrong — but the entire body of each migration (everything after the `CREATE TABLE` line, since the whole statement is skipped when the table already exists) never executed.

**This is a distinct, general risk from SEC-033** (which is about columns that were *never designed* with a FK at all). SEC-034 is about a migration that *is* correctly written, but silently fails to take effect because the target table already exists in some other, incomplete shape — with zero error signal. Added to `SECURITY_GAP_REGISTER.md`.

**Immediate consequence for both tables, still open, tracked separately from SEC-031:**
- `predmet_delegiranja` is still missing: `predmet_id → predmeti(id)` FK, `ENABLE ROW LEVEL SECURITY`, both RLS policies, both indexes (`idx_delegiranja_od`, `idx_delegiranja_na`).
- `tos_acceptances` is still missing: `ENABLE ROW LEVEL SECURITY`, both RLS policies.

Neither is a SEC-031 concern (RLS doesn't matter for backend-mediated access given SEC-004's service-role architecture) — but both should be closed for defense-in-depth and correctness, and are exactly the kind of gap SEC-034's broader question ("are there other tables in this state?") should check for systematically.

### The `tos_acceptances` discovery's real significance

Migration `056_tos_acceptances.sql`'s own header comment states: *"routers/tos.py... je aktivno pozivan... ali tabela nikad nije migrirana. GET /status namerno 'fail-open'-uje na DB gresku (vraca accepted=true)... sto znaci da je efekat trajno nepostojece tabele da se ToS/AI-consent modal NIKAD nije prikazao nijednom korisniku, i nijedno prihvatanje nije ikad zabelezeno."* This means: until migration 056 was run today (as a direct consequence of investigating SEC-031), **no user had ever had a valid, recorded ToS/AI-consent acceptance in production** — the check silently assumed consent on every database error, which is what a missing table produces on every single call. This is now closed by migration 056 having been run, independent of SEC-031's own scope — but it's a materially important compliance fact worth the founder's own separate follow-up (e.g., whether existing users need to be prompted to accept going forward, now that the table actually exists).

---

## What this closes and what remains open

**Closed:** SEC-031 itself — the `auth.users` cascade risk. 18/18 Tier A constraints confirmed `RESTRICT` in production, verified by direct query, not assumed.

**Still open, newly surfaced, tracked separately:**
- SEC-034 (new) — audit the rest of `migrations/*.sql` for the same "IF NOT EXISTS silently skipped" risk pattern.
- `predmet_delegiranja` and `tos_acceptances` RLS/policies/remaining-FK completion (small, low-risk, not yet done).
- The ToS/AI-consent historical gap — whether any retroactive user communication is needed (a product/legal decision, not an engineering one).

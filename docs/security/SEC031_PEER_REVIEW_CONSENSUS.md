# SEC-031 — Peer Review Consensus / Conflict Table

**Date:** 2026-07-23
**Method:** original analysis (Claude, this session) vs. independent review (fresh Opus instance, no shared context, explicitly tasked to falsify the claims, not confirm them). Per founder's methodology: only conflicts get re-investigated, not the whole package.

---

## Consensus / Conflict table

| Claim | Claude (original) | Opus (independent) | Status | Follow-up |
|---|---|---|---|---|
| Atomic `DELETE` + `RESTRICT` mechanism (core theorem) | ✅ Asserted | ✅ Independently confirmed, with own reasoning (checked `DEFERRABLE` status, statement-level rollback semantics) | **Consensus** | None needed |
| `klijenti` has no FK to `auth.users` | ✅ Claimed | ✅ Confirmed verbatim from source | **Consensus** | None needed |
| Migration SQL pattern (`NOT VALID`/`VALIDATE`) | ✅ Claimed safe | ✅ Confirmed standard and safe (noted as slightly over-engineered for a same-column CASCADE→RESTRICT change, not wrong) | **Consensus** | None — over-engineering noted, not a defect |
| Constraint naming assumption (`<table>_<column>_fkey`) | ✅ Claimed correct default | ✅ Confirmed correct for every Tier A FK checked | **Consensus** | None needed |
| Rollback SQL correctness | ✅ Claimed safe/complete | No defect raised | **Consensus** | None needed |
| Verified/unverified split methodology | ✅ Claimed accurate | ✅ Called "unusually disciplined" | **Consensus** | None needed |
| **Tier A list completeness ("no counter-example exists")** | ✅ Claimed complete | ❌ Found `user_knowledge` — tagged "Legal matter data," direct `CASCADE` to `auth.users`, `predmet_id` has no FK at all (no transitive cover either) | **Conflict** | **Resolved below — see §1** |
| **"Exhaustive" FK extraction** | ✅ Claimed exhaustive over the schema | ❌ Two root-level files (`supabase_migration.sql`, `supabase_migration_v3.sql`) excluded; one defines `conversations` (missed entirely), the other appeared to redefine `usage_events`/`notifications` differently | **Conflict** | **Resolved below — see §2** |
| **Lock analysis ("no lock on `auth.users`")** | ✅ Claimed no lock on `auth.users` | ❌ `ADD`/`DROP CONSTRAINT` referencing `auth.users` takes `ShareRowExclusiveLock` on `auth.users` itself, not just the child table | **Conflict** | **Resolved below — see §3** |
| Several "RESTRICT" labels in the docs | Labeled as RESTRICT | Some are actually `SET NULL` (immaterial to the proof's load-bearing property, but factually mislabeled) | **Conflict (minor)** | **Resolved below — see §2** |

**5 of 9 checked claims: consensus on first pass. 4 conflicts, all now investigated and resolved (not just noted) below — per the "only conflicts get re-investigated" principle, no other part of the package was re-opened.**

---

## §1 — `user_knowledge` resolution

Confirmed by direct source read (`migrations/053_orphaned_inline_schemas.sql:45-54`) and by checking actual usage (`routers/knowledge_base.py` — actively read/written, a live "lawyer's personal notes/positions/references" feature, not dead code). Opus's classification stands: this is real legal work-product, not disposable data.

**Action taken:** `user_knowledge.user_id` added to Tier A in `SEC031_MIGRATION_SAFETY_PLAN.md` and the corresponding `ALTER TABLE` statements added to `SEC031_MIGRATION_DRY_RUN.md`. Combined with `conversations` (§2 below), Tier A is now **18 tables / 19 constraints** (was 16/17).

## §2 — Root-file exclusion resolution

Investigated both previously-excluded files directly:

- **`supabase_migration_v3.sql` is a byte-for-byte duplicate of `migrations/009_notifications_analytics.sql`** (confirmed by direct comparison) — not a conflicting redefinition, just the same content present in two places (a root-level copy predating the numbered `migrations/` convention). **No actual schema ambiguity here.** The "RESTRICT vs. SET NULL" discrepancy Opus found was real, but it was **my own mislabeling**, not a file conflict: `fakture.predmet_id`, `billing_entries.faktura_id`, `klijent_dokumenti.predmet_id`, `recurring_templates.klijent_id`/`.predmet_id`, and `usage_events.predmet_id` are all `ON DELETE SET NULL`, not `RESTRICT` — verified against source directly. (`billing_entries.predmet_id` genuinely is `RESTRICT` — that one was labeled correctly.) Both `RESTRICT` and `SET NULL` are "non-cascade" for this proof's purposes, so the load-bearing property was never wrong — only the rule name.

- **`supabase_migration.sql` is a genuine legacy file, superseded but not fully redundant.** Its `profiles` definition is confirmed superseded — `supabase_setup.sql`'s own `profiles` table carries a comment explicitly acknowledging the older design (*"credits_remaining intentionally NOT here — lives in user_credits"*), proving the current schema's authors knew about and deliberately replaced the older shape. `api.py`/`shared/deps.py`/`README.md` all point to `supabase_setup.sql`, never to this file, as the schema to run. **But this file also defines `conversations`** (`supabase_migration.sql:79-87`, `user_id → auth.users ON DELETE CASCADE`, no downstream references — a leaf), which is **not redefined anywhere else** and **not written to by any current application code** (confirmed: zero `.table("conversations")` call sites anywhere in `api.py`/`routers/`/`shared/`) — chat/Q&A history persistence was superseded by `predmet_istorija` (confirmed actively used, already Tier A-protected). `feedback`, `reported_errors`, `api_costs`, `ratio_decidendi` (the file's other tables) were spot-checked: `api_costs` is live (used in `shared/cost.py`, operational telemetry, correctly low-stakes), `ratio_decidendi` is legal-corpus reference data (already correctly excluded elsewhere as non-personal), `feedback`/`reported_errors` are minor, low-stakes tables not warranting Tier A.

**Action taken:** `conversations.user_id` added to Tier A **provisionally** — it's dead code today, so this migration's practical effect on it may be moot, but if `supabase_migration.sql` was ever actually run against production (plausible — it's the oldest schema file, dated April 2026, before `supabase_setup.sql` existed), the table and any historical rows could still exist and are, per this project's own reasoning throughout SEC-031, worth protecting rather than assuming irrelevant. Explicitly flagged in `SEC031_PRODUCTION_ASSUMPTIONS.md` as a new item: whether `conversations` actually has any rows in production is unverified and matters for whether this is real protection or a no-op.

`SEC031_FK_GRAPH.md`'s "exhaustive" claim corrected to name the three schema files explicitly checked and note the two root files as now-included.

## §3 — Lock analysis resolution

Opus is correct: adding or dropping a foreign key that references `auth.users(id)` installs/removes a referential-integrity trigger on the **referenced** table (`auth.users`), which takes a `ShareRowExclusiveLock` on it — not just on the child table declaring the FK. `ShareRowExclusiveLock` conflicts with `ROW EXCLUSIVE` (i.e., ordinary `INSERT`/`UPDATE`/`DELETE`), meaning **new signups and logins could briefly queue** behind this migration's transaction, for as long as it's held.

**Action taken:** `SEC031_MIGRATION_DRY_RUN.md` §3 corrected to state this accurately, and a new recommendation added: since the lock is held for the whole transaction if all constraints are applied together, and now spans 18 (not 17) constraints, consider splitting Tier A into a few smaller transactions rather than one, purely to minimize how long `auth.users` is write-locked at once — a refinement to the deployment approach, not a change to which constraints are needed.

---

## Net effect on the plan

The core thesis (A: atomicity, the majority of B: transitive protection) survives independent review intact. Two real completeness gaps (`user_knowledge`, `conversations`) are now closed by extending Tier A to 18 constraints. One factual error (lock claim) is corrected. One labeling error (RESTRICT vs. SET NULL, 5 instances) is corrected. None of this reopens the plan's fundamental approach — it strengthens the proof rather than replacing it, which is exactly what a peer review is for.

**Lifecycle status:** still **Stage 4 — Remediation Candidate**, now with the Peer Review gate's findings addressed. **Production Reality Gate remains unopened** — including a new item specific to this round: whether `conversations` has any live rows in production, which only production access can answer, not further repo analysis.

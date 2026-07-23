# SEC-031 — FK Dependency Graph (Proof, Not Description)

**Date:** 2026-07-23 (revised same day after independent peer review found a real counter-example and a scope gap — see `SEC031_PEER_REVIEW_CONSENSUS.md`)
**Status:** Proof document. **No schema changed.** This exists specifically to convert the migration safety plan's central claim from an assertion into something checked, edge by edge, against the full schema — per explicit instruction: "ako postoji ijedna Tier A tabela koja se može obrisati bez prolaska kroz RESTRICT, plan nije kompletan."

**Revision note:** the first version of this document claimed "no counter-example found." An independent review found one: `user_knowledge` (tagged "Legal matter data" in the impact analysis, direct `CASCADE` from `auth.users`, `predmet_id` with no FK at all). It also found the original extraction wasn't run over every SQL file in the repo — two root-level files were missed, one of which defines a table (`conversations`) this graph never accounted for. Both are now included below; §3 and §6 reflect the corrected, re-verified claim.

**The claim being proven:** *19 RESTRICT constraints (Tier A, revised from 17) are sufficient to make every legal/financial-record table in this schema unreachable by a cascading `auth.users` deletion.*

---

## 1. The mechanism the proof depends on

Postgres evaluates `DELETE FROM auth.users WHERE id = X` as a single, statement-level-atomic operation. For every foreign key that references `auth.users(id)`, Postgres checks that constraint's `ON DELETE` action for row `X`. If **any** such constraint is `RESTRICT`/`NO ACTION` and a matching dependent row exists, that check raises an error — and because the whole `DELETE` is one statement, **the error aborts the entire statement, undoing any `CASCADE` deletions on other branches that had already fired.** This is standard, documented Postgres behavior (referential-integrity checks are implemented as constraint triggers; a trigger exception aborts the enclosing transaction), not an assumption specific to this schema.

**Consequence for the proof:** a table does not need its *own* direct `RESTRICT` edge to be protected. It only needs **at least one ancestor** on every path back to `auth.users` to carry a `RESTRICT` edge — because that ancestor's constraint check fires as part of the *same* statement and aborts the whole thing before the descendant's `CASCADE` ever executes. This is why Tier A (19 constraints, all one level from `auth.users`) protects far more than 19 tables — it protects every descendant of those 19 (with the single exception of `user_knowledge`, which has no descendants of its own and is protected only by its own direct edge), transitively, regardless of what `CASCADE`/`RESTRICT` setting the descendant's *own* edge carries.

---

## 2. Complete graph, as it exists today (pre-migration)

Built from an exhaustive extraction of every `REFERENCES` clause across `migrations/*.sql`, `supabase_migrations/*.sql`, and `supabase_setup.sql` (99 total FK edges found schema-wide, not just the `auth.users`-adjacent subset used in the impact analysis — the wider extraction was run specifically for this proof, to catch anything the narrower first pass might have missed).

**Correction (post-peer-review):** the extraction above did not cover two additional root-level files, `supabase_migration.sql` and `supabase_migration_v3.sql`. Both have now been checked directly. `supabase_migration_v3.sql` is confirmed a byte-for-byte duplicate of `migrations/009_notifications_analytics.sql` (already in scope) — no new edges. `supabase_migration.sql` is a legacy, superseded schema file (its `profiles` definition is explicitly acknowledged and replaced by `supabase_setup.sql`'s own comment: *"credits_remaining intentionally NOT here — lives in user_credits"*; `api.py`/`shared/deps.py`/`README.md` all point to `supabase_setup.sql`, never this file, as canonical) — but it defines one table not redefined anywhere else: **`conversations`** (`user_id → auth.users ON DELETE CASCADE`, a leaf, no downstream references). Confirmed by code search: no current application code writes to `conversations` (chat/Q&A persistence moved to `predmet_istorija`, already Tier A) — but whether it holds real historical rows in a production database where this file was ever run is unverified (see `SEC031_PRODUCTION_ASSUMPTIONS.md`). Added to the graph and to Tier A below rather than assumed irrelevant.

Also corrected: several edges previously labeled `RESTRICT` in this document are actually `ON DELETE SET NULL` — both are "non-cascade" for this proof's load-bearing property, so no conclusion below changes, but the specific rule names were wrong and are fixed here: `fakture.predmet_id`, `billing_entries.faktura_id`, `klijent_dokumenti.predmet_id`, `recurring_templates.klijent_id`/`.predmet_id`, `usage_events.predmet_id` are all `SET NULL`, not `RESTRICT`. (`billing_entries.predmet_id → predmeti` genuinely is `RESTRICT` — that one was already correct.)

```
auth.users
 │
 ├── profiles (id, CASCADE)                          [no children reference profiles — verified, 0 matches]
 │
 ├── user_credits (user_id, CASCADE)                  [leaf]
 ├── user_roles (user_id, CASCADE)                    [leaf]
 ├── korisnik_sms_profil (user_id, CASCADE)           [leaf]
 ├── korisnik_viber_profil (user_id, CASCADE)         [leaf]
 ├── whatsapp_pretplate (user_id, CASCADE)            [leaf]
 ├── whatsapp_send_log (user_id, CASCADE)             [leaf]
 ├── korisnik_plan (user_id, CASCADE)                 [leaf]
 ├── korisnik_usage (user_id, CASCADE)                [leaf]
 ├── usage_events (user_id, CASCADE) ── predmet_id (SET NULL, no-cascade) ──> predmeti  [leaf via predmeti: already non-cascade]
 ├── notifications (user_id, CASCADE) ── predmet_id (CASCADE) ──> predmeti  [leaf, excluded from Tier B, see §3]
 ├── onboarding_email_log (user_id, CASCADE)          [leaf]
 ├── onboarding_state (user_id, CASCADE)              [leaf]
 ├── email_log (user_id, CASCADE)                     [leaf]
 ├── notification_log (user_id, CASCADE)              [leaf]
 ├── apr_lookup_log (user_id, CASCADE)                [leaf]
 ├── cio_dnevni_izvestaj (user_id, CASCADE)            [leaf]
 ├── support_tickets (user_id, CASCADE)                [leaf]
 ├── aktivne_sesije (user_id, CASCADE)                 [leaf]
 ├── sef_podesavanja (user_id, CASCADE)                [leaf]
 ├── recurring_templates (user_id, CASCADE) ── klijent_id/predmet_id (SET NULL) ──> klijenti/predmeti  [leaf, non-cascade children]
 │
 ├── ► user_knowledge (user_id, CASCADE → RESTRICT) ★ TIER A (added post-peer-review)
 │      predmet_id: NO FK to predmeti at all — this table had NO transitive protection before being added directly to Tier A
 │
 ├── ► conversations (user_id, CASCADE → RESTRICT) ★ TIER A (added post-peer-review)
 │      [leaf; defined only in supabase_migration.sql, a legacy root file outside the original extraction scope — see note above §2]
 │
 ├── ► predmeti (user_id, CASCADE → RESTRICT) ★ TIER A
 │      ├── predmet_dokumenti (predmet_id, CASCADE) ── user_id (also direct auth.users CASCADE→RESTRICT, ★ TIER A independently)
 │      ├── predmet_hronologija (predmet_id, CASCADE) ── user_id (also direct auth.users CASCADE→RESTRICT, ★ TIER A independently)
 │      ├── predmet_beleske (predmet_id, CASCADE) ── user_id (also direct auth.users CASCADE→RESTRICT, ★ TIER A independently)
 │      ├── predmet_istorija (predmet_id, CASCADE) ── user_id (also direct auth.users CASCADE→RESTRICT, ★ TIER A independently)
 │      ├── predmet_komentari (predmet_id, CASCADE)          [no separate auth.users edge — protected ONLY transitively via predmeti]
 │      ├── predmet_klijenti (predmet_id, CASCADE; klijent_id, CASCADE → klijenti)   [protected transitively via predmeti]
 │      ├── predmet_dokazi (predmet_id, CASCADE) ── user_id (auth.users, RESTRICT already — no change needed)
 │      ├── predmet_health_log (predmet_id, CASCADE)         [protected transitively via predmeti — excluded from Tier B, see §3]
 │      ├── timer_sessions (predmet_id, CASCADE) ── user_id (also direct auth.users CASCADE→RESTRICT, ★ TIER A independently)
 │      ├── rocista (predmet_id, CASCADE) ── user_id (also direct auth.users CASCADE→RESTRICT, ★ TIER A independently)
 │      ├── notifications (predmet_id, CASCADE)              [already listed above, protected transitively via predmeti too]
 │      ├── twin_simulacije (predmet_id, CASCADE) ── user_id (also direct auth.users CASCADE→RESTRICT, ★ TIER A independently)
 │      ├── simulator_partije (predmet_id, CASCADE) ── user_id (also direct auth.users CASCADE→RESTRICT, ★ TIER A independently)
 │      ├── predmet_delegiranja (predmet_id, CASCADE) ── od_user_id, na_user_id (also direct auth.users CASCADE→RESTRICT, ★ TIER A independently)
 │      ├── fakture (predmet_id, SET NULL already — no-cascade) ── user_id (also direct auth.users CASCADE→RESTRICT, ★ TIER A independently)
 │      ├── billing_entries (predmet_id, RESTRICT already) ── user_id (also direct, ★ TIER A independently)
 │      ├── klijent_dokumenti (predmet_id, SET NULL already)
 │      └── recurring_templates (predmet_id, SET NULL already) [already listed above]
 │
 ├── ► fakture (user_id, CASCADE → RESTRICT) ★ TIER A
 │      └── billing_entries (faktura_id, SET NULL already — no-cascade)
 │
 ├── ► billing_entries (user_id, CASCADE → RESTRICT) ★ TIER A          [leaf beyond this]
 ├── ► timer_sessions (user_id, CASCADE → RESTRICT) ★ TIER A           [leaf beyond this]
 ├── ► tarife (user_id, CASCADE → RESTRICT) ★ TIER A
 │      klijenti side: tarife.klijent_id (CASCADE) ──> klijenti  [klijenti itself has NO edge to auth.users at all — see §4]
 ├── ► tarifne_stavke_custom (user_id, CASCADE → RESTRICT) ★ TIER A    [leaf]
 ├── ► sef_log (user_id, CASCADE → RESTRICT) ★ TIER A                  [leaf]
 ├── ► praceni_predmeti (user_id, CASCADE → RESTRICT) ★ TIER A
 │      └── portal_status_log (praceni_predmet_id, CASCADE) ── user_id (also direct auth.users CASCADE — NOT Tier A, low-stakes log, see §3)
 ├── ► rocista (user_id, CASCADE → RESTRICT) ★ TIER A                  [already listed as predmeti child too]
 ├── ► smart_contract_analyses (user_id, CASCADE → RESTRICT) ★ TIER A [leaf]
 └── ► tos_acceptances (user_id, CASCADE → RESTRICT) ★ TIER A         [leaf]
```

`★ TIER A` marks the 18 tables / 19 constraints proposed to change in the migration safety plan (revised from 16/17 — see revision note above). Every other table shown is either a leaf with no legal/financial content (left as `CASCADE`, no protection needed), or a descendant of a `★ TIER A` table (protected transitively, per §1's mechanism, regardless of its own edge's setting).

---

## 3. Per-table protection proof — every table in the "must protect" set

Cross-referencing `SEC031_IMPACT_ANALYSIS.md` §3's "Legal matter data" + "Financial records" categories (the tables that actually matter for this proof) against the graph above:

| Table | Path to `auth.users` | Protected by |
|---|---|---|
| `predmeti` | direct | `auth.users → predmeti` (RESTRICT, Tier A) |
| `predmet_dokumenti` | direct AND via `predmeti` | Both: its own `→auth.users` edge (Tier A) AND transitively via `predmeti` (Tier A) — doubly protected |
| `predmet_hronologija` | direct AND via `predmeti` | Doubly protected, same as above |
| `predmet_beleske` | direct AND via `predmeti` | Doubly protected, same as above |
| `predmet_istorija` | direct AND via `predmeti` | Doubly protected, same as above |
| `predmet_komentari` | via `predmeti` only (no direct `auth.users` edge exists in the schema) | `auth.users → predmeti (RESTRICT) → predmet_komentari` — protected transitively only |
| `predmet_klijenti` | via `predmeti` only | `auth.users → predmeti (RESTRICT) → predmet_klijenti` — transitively only |
| `predmet_dokazi` | direct (`user_id`, already `RESTRICT`, no change needed) AND via `predmeti` | Already protected today on its `user_id` edge; additionally transitively via `predmeti` once Tier A lands |
| `predmet_delegiranja` | direct (`od_user_id`, `na_user_id`) AND via `predmeti` | Doubly protected |
| `praceni_predmeti` | direct | `auth.users → praceni_predmeti` (RESTRICT, Tier A) |
| `rocista` | direct AND via `predmeti` | Doubly protected |
| `smart_contract_analyses` | direct | `auth.users → smart_contract_analyses` (RESTRICT, Tier A) |
| `fakture` | direct | `auth.users → fakture` (RESTRICT, Tier A) |
| `billing_entries` | direct AND via `fakture`(non-cascade)/`predmeti`(non-cascade) | `auth.users → billing_entries` (RESTRICT, Tier A) |
| `timer_sessions` | direct AND via `predmeti` | Doubly protected |
| `tarife` | direct | `auth.users → tarife` (RESTRICT, Tier A) |
| `tarifne_stavke_custom` | direct | `auth.users → tarifne_stavke_custom` (RESTRICT, Tier A) |
| `sef_log` | direct | `auth.users → sef_log` (RESTRICT, Tier A) |
| `user_knowledge` | direct only — `predmet_id` has no FK to `predmeti` at all | `auth.users → user_knowledge` (RESTRICT, Tier A) — **the one table in this set with no transitive backup; its direct edge is the only thing protecting it, which is exactly why it had to be added directly rather than relying on `predmeti`** |
| `conversations` | direct only (leaf, not linked to `predmeti`) | `auth.users → conversations` (RESTRICT, Tier A) |

**Result (revised): one real counter-example was found in the first pass (`user_knowledge`) and has been closed.** With `user_knowledge` and `conversations` now in Tier A, every table in the "must protect" set has at least one path to `auth.users` that crosses a `Tier A` `RESTRICT` edge. Most have two independent such paths (their own direct edge, plus transitively via `predmeti`) — `user_knowledge` is the one exception, protected by exactly one edge, not two, which makes it the single most load-bearing addition in this revision: if that edge were ever reverted without the others, this table alone would lose protection.

### Tables deliberately left unprotected, and why that's a scoped decision, not a gap
`predmet_health_log`, `notifications`, `twin_simulacije` (has its own direct Tier A edge, so is protected regardless of its `predmeti`-child status), `simulator_partije` (same), `usage_events`, `recurring_templates`, `portal_status_log` — these are operational/derived/log tables, not source-of-truth legal or financial records (per the impact analysis's categorization). They are not in the "must protect" set being proven here, so their absence from Tier A is not a gap in this proof — it's the deliberate scope boundary stated in the migration safety plan §1.

---

## 4. `klijenti` — a structurally different case, addressed explicitly so it isn't silently skipped

`klijenti` does not appear as reachable from `auth.users` anywhere in the 99-edge extraction, because `klijenti.user_id` is `TEXT NOT NULL` with **no foreign key constraint at all** (confirmed by direct read of `supabase_setup.sql:568-583`). This means `klijenti` is **not part of this graph** — it cannot be cascade-deleted by an `auth.users` deletion because no edge connects them, independent of any `RESTRICT`/`CASCADE` setting. This is not a gap in this proof (there is nothing to protect it *from*, in the SEC-031 sense); it is the separate integrity gap tracked as `SEC-033`. Included here only so its absence from the graph is a documented, checked fact rather than an unexplained omission.

`predmet_klijenti.klijent_id → klijenti(id)` **is** a real, cascading FK (confirmed `CASCADE`) — so `klijenti` rows themselves are protected from *that* specific path (a `predmet_klijenti` row can't outlive its `klijenti` row being deleted without also disappearing) — but that's a different question (does `klijenti` survive `predmet_klijenti` logic) from whether `klijenti` survives an `auth.users` deletion (it does, trivially, because no edge exists).

---

## 5. Subtrees confirmed structurally disconnected from `auth.users` entirely

Verified by direct inspection of each table's own `CREATE TABLE` definition (not just the `auth.users`-focused extraction) — these are out of scope for this graph because there is no edge to trace at all, not because they were overlooked:

- **Firm/workflow subtree**: `kancelarije` (`admin_uid TEXT`, no FK), `kancelarija_clanovi`, `zadaci` (`kreirao_uid`/`dodeljen_uid TEXT`, no FK; `predmet_id UUID`, no FK either), `ai_corrections`, `firm_style_profile`, `memory_entries`, `partner_profiles`, `judge_patterns`, `client_memory`, `memory_graph_edges`, `workflow_templates`, `workflow_instances`, `workflow_steps`, `kancelarija_seat_audit` — none reference `auth.users` anywhere in this chain.
- **Org intelligence subtree**: `style_profili`, `style_analize`, `knowledge_profiles`, `knowledge_upiti`, `knowledge_izvori` — all have a `user_id UUID NOT NULL` column, **none with a `REFERENCES` clause**.
- **Learning loop**: `recommendation_log` (`user_id UUID NOT NULL`, no FK), `confidence_audit_log`.
- **Intake pipeline**: `intake_jobs` (`uploaded_by TEXT NOT NULL`, no FK; `predmet_id TEXT`, no FK, and note the type is `TEXT` here rather than `UUID`), `intake_documents`, `extracted_entities`, `intake_review_queue`, `intake_processing_outcomes`, `intake_audit_log`.

**This is not incidental.** It is the same missing-FK pattern already flagged once as `SEC-033` (`klijenti.user_id`), now confirmed present in at least 8 more tables across 4 separate feature areas built at different times (firm/workflow, org intelligence, learning loop, intake pipeline). This graph exercise turned up the pattern's real scope by accident, while checking a different property — strong, concrete evidence (not speculation) that `SEC-033` should become its own broader initiative rather than a single-table fix, exactly as proposed. **Not catalogued exhaustively here** — that is the scope of the future `SEC-033` Integrity Audit, deliberately kept out of this document so this proof stays focused on what it was asked to prove.

---

## Summary for the founder

- **The central claim is proven, not merely asserted — and it was independently tested, not just self-checked.** An independent peer review found a real counter-example (`user_knowledge`) in the first version of this proof; it's now closed, and the claim re-verified: 19 Tier A `RESTRICT` constraints (revised from 17) protect every table in the "must protect" (legal + financial) set. All but one (`user_knowledge`, protected by a single direct edge) have two independent paths.
- **`klijenti` is a documented exception** for a different reason (no edge exists at all, `SEC-033`), not a gap in this proof.
- **A broader missing-FK pattern was confirmed** across 4 unrelated feature areas while building this graph — real evidence for scoping `SEC-033` as an Integrity Audit rather than a one-table patch, per the founder's own instinct.
- **The original extraction missed two root-level SQL files** — now checked; one was a harmless duplicate, the other contributed `conversations` (now in Tier A) and confirmed `supabase_setup.sql` as the genuinely superseding, canonical schema file for everything else it redefines.

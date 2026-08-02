# Mission 001 — Architecture Decision: `predmet_klijenti` Ownership Integrity

**Author (role):** AI CTO / Chief Architect + Database Architect (schema-history review)
**Date:** 2026-08-02
**Status:** **IMPLEMENTED, QA COMPLETE.** Revision 3's approved scope is fully built: all 5
`user_id` removals, the `api.py:5245` select-column fix, the bulk-import compensating delete, and
`tests/test_mission001_predmet_klijenti.py` (6 tests, all passing, including a real User Scenario
Test against the live endpoint function). Full existing intake/onboarding/predmet/klijenti test
suite (174 tests) re-run with zero regressions.
**Source:** `docs/product/BOJAN_WORKFLOW_GAP_ANALYSIS_2026-08-02.md`;
`memory: project_predmet_klijenti_bug`

---

## Revision 2 — founder direction

Founder confirmed the no-schema-change conclusion and its reasoning (normalized model; adding
`user_id` here would create two sources of truth with no clean rule for which wins). Founder's own
framing, preserved verbatim because it reframes what this mission is actually about: *"5 call sites
šalje kolonu koja ne postoji — to nije jedan bug, to je simptom... kako je moguće da je pet različitih
mesta u kodu moglo da šalje nepostojeću kolonu, a da to nije bilo uhvaćeno ranije? To je procesni
problem."* Three concrete changes:

1. **New deliverable added to this mission: a Schema Contract Check** (§8, new) — a mechanical,
   generalizable check that an `.insert()`/`.update()` payload's keys are all real columns on the
   target table, so this bug *class* (not just this instance) stops being possible to introduce
   silently — today it's `user_id` on `predmet_klijenti`; tomorrow it could be `tenant_id`,
   `status`, or any other field on any other table.
2. **Bulk-import's orphan-row risk (call site #3) is elevated to P0**, bundled with the `user_id`
   fix rather than treated as a secondary cleanup — founder's reasoning: *"predmet je uspešno kreoran
   → link nije → korisnik dobija pogrešnu grešku"* is a **transactional consistency problem**, not a
   UX problem, and shouldn't ship at a lower priority than the field-removal fix it's adjacent to.
3. **Verification pass, not a full Red Team, and narrowly scoped** — one question: *"Postoji li još
   bilo koji insert/update nad `predmet_klijenti` koji koristi kolonu koje nema ili ostavlja
   mogućnost orphan stanja?"* If clean, founder pre-approved implementation on that result alone —
   no further review cycle. `routers/copilot.py`'s separate `id`-column bug stays out of this
   mission, per the founder's explicit approval of keeping it separate (*"dobro što ga nisu 'ugurali'
   u isti tiket... neka ostane poseban"*).

---

## Revision 3 — final scope, approved

Founder's ruling on §9's open question: **`api.py:5245`'s `.select("id")` fix is now part of Mission
001.** Reasoning, preserved because it is now a standing rule (`OPERATING_PROTOCOL.md`, "Ticket/
Mission scope boundary rule"): the test for whether a related finding joins the current mission is
not "is this the same bug class as something already deferred" (it is the same class as
`copilot.py:610`, which correctly stays deferred), it is **"does fixing the current mission's change
in isolation actually let the user complete the scenario without this other fix right next to it."**
Here, no — the `.select("id")` bug sits directly in front of the insert this mission is already
fixing at that exact call site, so removing `user_id` alone would ship a change with zero observable
effect (the preceding bug prevents the insert from ever being reached). `copilot.py:610` stays a
separate ticket precisely because it's a different feature/workflow/test surface, not because the
bug is dissimilar — same bug ≠ same ticket; same user-facing functionality = same ticket.

**Final approved scope for Mission 001:**
- ✅ Remove `user_id` from all 5 insert payloads (`routers/intake.py` ×3, `api.py:5253`,
  `routers/onboarding.py:234`).
- ✅ Fix `api.py:5245`'s `.select("id")` → a real column (`"predmet_id"` or `"klijent_id"`), matching
  the correction already recommended for the same bug class at `copilot.py:610`.
- ✅ Bulk-import (#3) compensating delete, P0, per Revision 2.
- ✅ Regression tests (§5) for all of the above.
- ✅ A **User Scenario Test** (new, required per the founder's Definition-of-Done rule — see below)
  for the complete "link a client to a case" flow, run end to end, not inferred from passing unit
  tests of its individual parts.
- ❌ `copilot.py:610` — stays a separate ticket (same bug class, different feature/workflow).
- ❌ Schema Contract Check (§8) — stays a separate, non-blocking follow-on item, per Revision 2.

**New standing rule adopted, beyond this one mission** (founder's own instruction — added to
`agents/11_qa_engineering.md` and `templates/QA_REPORT.md`): **Definition of Done is not "tests
pass," it is "the user can complete the scenario the ticket was opened for."** The founder's own
worked example, now the canonical case for this rule: Mission 001's `user_id` removal and the
`.select("id")` fix were each individually testable and would each individually report green, while
the actual user goal — link a client to a case — still failed end to end, because the two changes
are functionally dependent at the same call site. Every QA report for this mission (and, going
forward, every future one) must include a numbered, end-to-end User Scenario Test — not just
per-change unit coverage.

### Mission 001's own User Scenario Test (required by the rule just adopted — filled in now, verified at implementation/QA time, not before)

```
Scenario: Link a client to an existing case (via the "confirm AI suggestions" endpoint, api.py:5253)
1. Advokat creates predmet P (any path) -> P exists, no client linked yet
2. Advokat calls the confirm-links endpoint with klijent_id K for predmet P
   -> predmet_klijenti now contains (P, K); response reports K as linked
3. Advokat calls the same endpoint again with the same K
   -> duplicate-check correctly finds the existing link (no PGRST error from
      selecting a nonexistent column) and does not insert a second row
4. predmet_klijenti still contains exactly one (P, K) row after step 3
   -> database is left consistent, not duplicated, not orphaned

PASS/FAIL to be recorded by QA at implementation time — this is the test that would have caught
the stacked-bug gap described in Revision 3 above, had it existed before this mission started.
```

---

## 1. Root cause (re-derived from schema history, not assumed)

The original finding (2026-07-16, and re-confirmed in the 2026-08-02 gap analysis) described this as
a **missing column** — as if `user_id` should be on `predmet_klijenti` and was accidentally dropped
or never migrated in. Re-reading the table's actual origin changes that conclusion.

**`supabase_setup.sql:610-628`** — the table's original definition:

```sql
CREATE TABLE IF NOT EXISTS public.predmet_klijenti (
  predmet_id UUID NOT NULL REFERENCES public.predmeti(id) ON DELETE CASCADE,
  klijent_id UUID NOT NULL REFERENCES public.klijenti(id) ON DELETE CASCADE,
  uloga      TEXT DEFAULT 'stranka' CHECK (uloga IN ('stranka','protivna_stranka','svedok','ostalo')),
  PRIMARY KEY (predmet_id, klijent_id)
);
ALTER TABLE public.predmet_klijenti ENABLE ROW LEVEL SECURITY;
CREATE POLICY "pk_owner_all" ON public.predmet_klijenti
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.predmeti
            WHERE id = predmet_klijenti.predmet_id
              AND user_id = auth.uid()
        )
    );
```

This is a **pure join table by design**: composite primary key (`predmet_id`, `klijent_id`), no
surrogate `id` column, no `user_id` column. Ownership is meant to be derived **transitively** —
"who owns this link" is answered by "who owns the `predmeti` row it points to," exactly as the
`pk_owner_all` RLS policy expresses. This is a legitimate, common relational design choice: a link
table doesn't need its own owner column when ownership is already unambiguous via one of its foreign
keys.

**The bug is not a missing column. It is application code sending a field the schema never had**,
across 5 call sites (found below — 2 more than the original report), all constructed independently
of the table's actual design, presumably by analogy to `predmeti`/`klijenti`, which *do* carry
`user_id` directly (they are not join tables). `routers/smart_intake.py`'s finalize path
(`:472-478`) already does this correctly — its own inline comment (`:465-471`) documents exactly
this history and confirms omitting `user_id` works.

**Why this matters for the recommended fix:** the correct remediation is determined by the schema's
original intent, not by pattern-matching "a field failed to insert, therefore add the column." Adding
`user_id` to a table whose ownership is already fully and correctly derivable via `predmet_id` would
introduce a **new** integrity risk — a redundant copy of ownership data that could drift from the
authoritative source (`predmeti.user_id`) if a case is ever reassigned, and one more column every
future insert site has to remember to populate correctly. The existing RLS policy already solves
ownership at the schema level, for whenever RLS is the enforcement path; today it structurally
cannot be (SEC-004 — the app's single service-role DB client bypasses RLS on all backend routes),
but that is a separate, already-tracked, larger architectural item — not a reason to duplicate
ownership data here as a workaround.

## 2. Scope correction — 5 call sites, not 3

The original report and the 2026-08-02 gap analysis both found 3 broken sites in `routers/intake.py`.
Re-grepping every `predmet_klijenti` insert in the repo during this architecture review found **2
more**, both live, both sending the same invalid `user_id` field:

| # | File:line | Endpoint / context | Failure mode |
|---|---|---|---|
| 1 | `routers/intake.py:194-202` | `POST /api/intake/kreiraj` — primary AI-assisted case creation | Narrow `try/except`, warning logged, **link silently never persisted** |
| 2 | `routers/intake.py:740-747` | `POST /api/intake/from-template` — 7 pre-built case templates | Narrow `try/except`, **silently swallowed** (bare `except: pass`) |
| 3 | `routers/intake.py:877-884` | `POST /api/intake/bulk-import` — bulk CSV/row import | **Not independently caught** — this insert sits inside the per-row `try` (`:831`) whose `except` is at `:888`. A failure here does not silently continue: it causes the **entire row** to be reported as an error in the response's `greske` list, even though the `predmeti` row (created at `:863-874`, *before* this insert) has **already committed** — there is no transaction wrapping the two inserts. Net effect: the caller sees "row N failed," but a real, orphaned `predmeti` row with no client link exists in the database. This is a different and arguably worse failure shape than #1/#2 (visible error, but the visible error doesn't match what actually happened, and cleanup doesn't happen automatically). |
| 4 | `api.py:5253` | `POST` (one-click "confirm AI suggestions" endpoint, called from the frontend confirm-card after document upload — per its own docstring, `api.py:5227`) | Same narrow-try pattern as #1 |
| 5 | `routers/onboarding.py:234` | Demo/onboarding case creation | Same narrow-try pattern as #1 |

**Adjacent, differently-shaped finding (not part of this fix, flagged for a separate decision):**
`routers/copilot.py:610` — a "link client to case" Copilot command — runs
`.select("id").eq("predmet_id", ...).eq("klijent_id", ...)` against `predmet_klijenti` **as a
duplicate-link check before inserting**. The table has no `id` column (confirmed above — composite
PK only). This is not the `user_id` bug; it is a second, independent schema-mismatch bug on the same
table, in the opposite direction (a `SELECT` naming a nonexistent column, rather than an `INSERT`).
Its likely effect: the duplicate check either errors (caught by copilot.py's broader error handling,
degrading the command to a generic failure message) or returns no rows regardless of whether a link
already exists, meaning **repeated use of this specific Copilot command could insert duplicate
`predmet_klijenti` rows** for the same case/client pair (no unique constraint exists on
`(predmet_id, klijent_id)` beyond the composite primary key itself — actually, the composite PK
**would** reject a true duplicate at the DB level with a constraint violation, so the realistic
consequence is a **PostgREST 23505 error surfaced as a generic Copilot failure message**, not a
silent duplicate). Recommend logging this as a small separate fix (`.select("predmet_id")` instead of
`.select("id")`) rather than folding it into this mission, since it's a distinct bug shape and low
severity (annoying error message, not data loss).

## 3. Recommended fix (no migration)

**Strip `user_id` from the insert payload at all 5 call sites listed above.** No schema change, no
migration file, no backfill, no `ADD COLUMN`. This exactly matches what `smart_intake.py:472-478`
already does correctly, and matches the table's original design intent (§1).

This is a smaller, safer change than a migration would be: it touches only application code already
covered by this project's existing test infrastructure (§5), carries zero production-data risk (no
`ALTER TABLE`, no existing rows touched), and requires no coordination with the founder for a
Supabase-side migration run — consistent with this project's own standing rule that migration SQL is
drafted for the founder to review and run himself, which this fix avoids needing entirely.

### Rejected alternative: add `user_id` to `predmet_klijenti`

Considered and rejected. Would require: a migration (`ALTER TABLE ... ADD COLUMN user_id UUID`,
correctly nullable or backfilled since 0 existing rows means no backfill is actually needed today —
but that's incidental, not a reason to prefer this path), updating the RLS policy to decide whether
`user_id` or the `predmet_id` join is now authoritative (a genuine design question with no clean
answer, since having both invites exactly the drift risk named in §1), and auditing every future
insert site to keep both in sync. Rejected because it solves a problem that doesn't exist (the table
was never missing ownership derivation — the RLS policy already has it) by introducing one that does
(a second, potentially-stale ownership signal on a table that didn't need one).

## 4. Affected files

| File | Change |
|---|---|
| `routers/intake.py` | Remove `"user_id": uid,` from the 3 `predmet_klijenti` insert payloads (`:200`, `:744`, `:881`) |
| `api.py` | Remove `"user_id": uid,` from the insert payload at `:5257`, **and** (per Revision 3, now in scope) fix the duplicate-check at `:5245` — `.select("id")` → `.select("predmet_id")` (or any real column; the check only needs to know whether a row exists, not read any particular field back) |
| `routers/onboarding.py` | Remove `"user_id": uid,` from the insert payload at `:236` |
| `routers/intake.py:877-884` (bulk-import) — **P0, per founder's Revision-2 direction, not a secondary cleanup** | Two changes, both required: (a) remove `user_id` from the payload, same as the other 4 sites; (b) **add a compensating delete**: if the `predmet_klijenti` insert fails for any reason after the `predmeti` row (`:863-874`) has committed, delete the just-created `predmeti` row before recording the row as failed in `greske`. This is the founder's own framing applied directly — "predmet uspešno kreiran → link nije → korisnik dobija pogrešnu grešku" is a transactional consistency problem, and a compensating delete is the correct fix at this scope (a real DB transaction wrapping both inserts would be the more thorough fix, but Supabase's REST/PostgREST interface does not expose multi-statement transactions to this codebase's existing call pattern — a compensating action is the standard, correct mitigation at this layer, and matches how this codebase already handles similar cross-call consistency elsewhere). After this fix, a row reported as failed in `greske` will accurately mean **nothing was created**, not "something was half-created." |

No files outside `routers/intake.py`, `api.py`, and `routers/onboarding.py` need to change for the
core fix. `routers/copilot.py`'s `id`-column bug is tracked separately (§2), not included here.

## 5. Tests

**Regression test, per the founder's own worked scenario** — this is the test that actually matters,
because it verifies both halves of what "ownership integrity" means here: the link is *persisted*,
and it is *correctly scoped*, not just that the insert doesn't error.

```
Scenario: cross-user isolation on predmet_klijenti after the fix

1. Advokat A creates klijent K (POST /api/klijenti or equivalent, as Advokat A)
2. Advokat A creates predmet P via each of the 5 fixed paths in turn
   (parametrize the test over all 5 call sites — this is exactly the kind
   of "same bug, N call sites" class this project has repeatedly found
   elsewhere; a single call-site test would not have caught #3/#4/#5 here)
3. Assert: predmet_klijenti now contains exactly one row (P, K), with no
   PGRST204 / insert error in the response
4. Assert: reading /api/predmeti/{P}/klijenti (or equivalent) as Advokat A
   returns K
5. Advokat B (a different account) attempts to read the same predmet_klijenti
   link (directly, or via any endpoint exposing it)
6. Assert: Advokat B sees nothing — either a 404/403 on the predmet itself
   (since predmeti already filters by user_id, confirmed elsewhere in this
   codebase), or, if a lower-level query path exists, that it never returns
   cross-tenant rows
```

Existing test infrastructure to build on: `tests/test_intake_conflict_check.py` already mocks
`predmet_klijenti` reads via a Supabase-table mock keyed by `klijent_id` (`:43-49`, `:224-230`) —
extend this pattern for the insert-path assertions rather than building new mock infrastructure.

**Additional, narrower tests:**
- Bulk-import specifically (call site #3, now P0 per Revision 2): assert that if the
  `predmet_klijenti` insert fails for any reason, (a) the response's `greske` entry for that row is
  accurate, **and** (b) the compensating delete actually runs — the previously-created `predmeti` row
  is confirmed absent afterward (query for it directly in the test, don't just assert the delete call
  was made). This test must be written to inject a failure (mock the `predmet_klijenti` insert to
  raise) specifically to exercise the compensating-delete path, not only to confirm the happy path.
- One negative test confirming the *old* behavior would have failed the way production did: mock
  PostgREST to reject an insert containing a `user_id` key on this table (matching the real
  `PGRST204` error), confirm the fixed code path no longer sends that key at all 5 sites — this
  guards specifically against a future regression re-adding `user_id` by copy-paste from
  `predmeti`/`klijenti` insert code nearby, which is how this bug was introduced in the first place.

## 6. Rollback strategy

Because the recommended fix is a pure application-code change (no migration, no schema change, no
data backfill), rollback is the simplest case this project's `ESCALATION_RULES.md`/git-safety
protocol has to handle: **revert the commit.** No production data is touched by the fix itself (the
table remains schemaless-for-`user_id`, exactly as it is today), so there is no forward-migration to
undo and no backward-migration to write. The only state that changes going forward is that new
`predmet_klijenti` rows start actually persisting (they do not today) — reverting the code change
simply returns to today's status quo (silent non-persistence), which is safe, if undesirable, since
that is the exact current production behavior this mission is fixing.

If, after implementation, the founder or a later review decides `user_id` genuinely should be added
to `predmet_klijenti` after all (e.g., a future requirement makes the RLS-via-join design
insufficient), that would be raised as a **new, separate architecture decision** — not a rollback of
this one, since the two are different designs, not a revert of each other.

## 7. Verification pass condition (resolved — founder's narrower alternative to a full Red Team)

Founder's own question, exact scope, run as the sole remaining gate before implementation (§9 below
for the actual result): *"Does any other insert/update on `predmet_klijenti` use a nonexistent
column, or leave the possibility of an orphan state?"* Pre-approved disposition: if the answer is
clean, implementation proceeds directly on this document — no further review cycle, no full Red Team
pass. This reflects the founder's own risk calibration for this class of change (no schema touched,
a subtraction not an addition, trivial rollback) versus the multi-pass depth used earlier this
session for the rate-limiting/security-model chain — a deliberately different, lighter-weight gate
for a deliberately lower-risk change, not a shortcut applied inconsistently.

## 8. Schema Contract Check (new deliverable, added per founder's Revision-2 direction)

**The actual problem this mission surfaced is broader than one bug.** Five independent call sites,
written at different times by (presumably) different reasoning, all made the identical mistake of
sending a column that doesn't exist on the target table. That is not explainable as one lapse — it's
a **process gap**: nothing in this codebase's current tooling checks an `.insert()`/`.update()`
payload's keys against the actual schema before it reaches PostgREST at runtime, so a typo or a
copy-paste-from-a-different-table error is invisible until it either silently fails (as here) or
throws in production.

**Deliverable:** a mechanical check — script or CI job — that:
1. Statically or dynamically enumerates every `supabase.table("<name>").insert({...})` and
   `.update({...})` call site in the codebase (a straightforward AST walk, in the same spirit as the
   route-enumeration scripts already used elsewhere in this codebase's own tooling
   — `scripts/export_rls_policies.py`, and the live-route-walking method this session's Red Team
   passes used repeatedly for `app.routes`).
2. Extracts the literal dict keys being inserted/updated wherever they're statically determinable
   (a literal dict, as in every one of the 5 sites found here) — flagging dynamically-constructed
   payloads (`**kwargs`, a variable dict) as unverifiable-by-this-method rather than silently passing
   them.
3. Compares those keys against the actual table's real column set, obtained from a live schema
   introspection (`information_schema.columns` via a Postgres connection, the same shape
   `scripts/export_rls_policies.py` already reaches for — see that script's own noted need for
   `SUPABASE_DB_URL` rather than the app's service-role key) — **not** from a hand-maintained list of
   expected columns, which would just relocate the same "declared vs. actual" drift risk into the
   checker itself (the same class of mistake this project's Security Governance Framework work,
   earlier this session, spent considerable effort diagnosing and correcting for — a check is only as
   good as the thing it verifies against being the live, authoritative source, not a copy of it).
4. Fails (CI or a pre-commit/periodic job — venue TBD by whoever implements it, following this
   project's own now-standing rule of declaring the enforcement venue honestly rather than assuming
   CI can reach a live DB by default) on any statically-determinable payload key with no matching
   column.

**Explicitly not this mission's job to fully design or build now** — this document commits to the
*need* and the *shape* (live schema introspection, not a hand-maintained list; static-payload
coverage with dynamic payloads honestly flagged as out-of-reach rather than silently passed), the
same way earlier architecture documents this session committed to a principle before a full build.
Recommend scoping this as its own follow-on item once Mission 001's immediate fix ships, not as a
blocking prerequisite for the `predmet_klijenti` fix itself — the fix is well-understood and
low-risk today; the Schema Contract Check is the structural prevention for the *next* instance of
this bug class, on a different table, which is valuable but not urgent in the same way the live
data-integrity gap is.

## 9. Verification pass result

Founder's exact question, run directly (no subagent needed — confirmed a "few minutes" job, as
anticipated): *"Does any other insert/update on `predmet_klijenti` use a nonexistent column, or
leave the possibility of an orphan state?"*

**Confirmed clean:**
- **Zero `.update()` calls** on `predmet_klijenti` anywhere in the repo (repo-wide grep, `.py` only).
- **Zero `.delete()` calls** either — cleanup on delete is handled entirely at the DB level via
  `ON DELETE CASCADE` on both `predmet_id`/`klijent_id` foreign keys (`supabase_setup.sql:611-612`),
  so there is no app-level orphan-on-delete risk to check for.
- All **7** total insert call sites on this table are now accounted for (the 5 needing the
  `user_id` fix; `smart_intake.py:473`, already correct; `copilot.py:616`, already correct on the
  insert itself). No 8th site exists.
- No other call site has bulk-import's specific "created-then-misreported" shape: `intake.py`'s
  other two broken sites (#1, #2) already fail silently *without* misreporting success/failure
  (once `user_id` is removed, they succeed normally); `api.py:5253` and `onboarding.py:234` both
  insert against contexts that either don't create a new `predmeti` row in the same call
  (`api.py:5253` operates on an already-existing `predmet_id`) or aren't part of a per-row
  batch-with-inaccurate-error-reporting pattern (`onboarding.py:234`) — bulk-import (#3) remains the
  one site with a genuine orphan/misreport risk, correctly elevated to P0 above.

**Not clean — one finding requiring a decision, found at the exact site this mission is already
touching:** `api.py:5245`'s duplicate-link check —
`.select("id").eq("predmet_id", predmet_id).eq("klijent_id", _kid).execute()` — immediately
preceding the insert at `:5253` — has **the same nonexistent-`id`-column bug** previously found only
at `copilot.py:610` and explicitly kept out of this mission as a separate ticket. This is a **second,
independent occurrence** of that bug class, not a duplicate report of the same one — and it sits
directly in front of one of the 5 inserts this mission is already fixing.

**Practical consequence:** selecting a nonexistent column is expected to raise (PostgREST rejects
unknown columns in a `select`), and that `.select()` call sits inside the same `try` block as the
insert (`:5243-5261`) — so the exception is very likely raised and caught **before** the insert is
ever reached. If so, removing `user_id` from `api.py:5253`'s insert payload alone will **not** make
this endpoint's link-creation actually work; the preceding `.select("id")` must also be fixed (the
same one-line correction already recommended for `copilot.py`: select a real column, e.g.
`"predmet_id"`, instead of `"id"`).

**Decision needed from the founder:** given the founder's own instruction to keep the
`copilot.py`-class bug in a separate ticket, does that ticket now expand to cover **both**
occurrences (`copilot.py:610` **and** `api.py:5245`), fixed together, separately from Mission 001 —
in which case `api.py:5253`'s `user_id` removal ships as scoped here but the endpoint remains
non-functional for its actual purpose (silently, same as today) until that separate ticket lands —
or does `api.py:5245`'s `.select("id")` get folded into this mission specifically, since fixing
`user_id` alone at this one site produces no observable improvement without it? Recommend the
latter: fixing `user_id` at a site whose preceding check already prevents the insert from ever being
reached would be shipping a change with no actual effect at that specific site, which doesn't serve
this mission's own goal — but this is the founder's call, consistent with the discipline already
shown in keeping `copilot.py` separate the first time.

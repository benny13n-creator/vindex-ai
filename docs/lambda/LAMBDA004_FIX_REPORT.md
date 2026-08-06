# Fix Report — Program Lambda, Certification 004

Every implemented correction, per this mission's own required format: root cause, why existing protection
failed, why the fix is correct, regression proof.

## Fix A — `routers/case_dna.py::_do_genome_refresh` destroyed live Genome data on any GPT failure

**Root cause**: `_extract_genome` correctly signals failure via `{"greska": str(exc)}`, never raising. The
caller had a correct guard (`if not genome.get("greska")`) around the verification/hronologija-sync steps,
but NOT around the actual write to `predmeti.case_dna` a few lines below — a full-value JSON column replace.

**Why existing protection failed**: the guard existed but its scope was too narrow — it protected the
*advisory* steps (verification, sync) but not the *destructive* one (the live write).

**Why the fix is correct**: all steps after extraction (write, history save, event emit, delta/alert,
require-review) now share ONE early-return on failure, using the exact same signal the narrower guard already
checked. Nothing about the live case is touched on failure; only a log line records it.

**Regression proof**: `tests/test_ztc_genome_scale_and_race.py` (2 new tests), `tests/test_case_dna_events.py`
(1 corrected test). Phase 6 adversarial re-attack found and closed one edge case (truthiness → key-presence).

## Fix B — `main.py` Map-Reduce silently presented a failed batch as "found nothing"

**Root cause**: `_map_analiziraj_batch` (by design, "never raises") caught its own GPT-call exception and
returned an empty-but-valid-shaped dict, indistinguishable from a genuinely clean batch.

**Why existing protection failed**: the failure was correctly caught (preventing a full analysis crash) but
the SIGNAL of that failure was discarded at the same point — the caller's own `except Exception` around
`fut.result()` could never fire, since the inner function never raises.

**Why the fix is correct**: `_map_analiziraj_batch` now returns an internal `_batch_failed` marker (popped
before aggregation, never reaches the report); the caller collects failed indices into `partial_failure`/
`failed_batches` fields in the response.

**Regression proof**: `tests/test_akcija2_faza4_2026_07_24.py` (2 tests extended). The coordinator's own
first fix attempt targeted the wrong location (the never-fired outer exception handler) — caught by the
coordinator's own new test failing immediately, corrected before being reported done.

## Fix D — `services/case_evolution.py`'s consequence dedup was a TOCTOU race (closes `LAMBDA003-EVT-001`)

**Root cause**: `_get_consequence_status` (read) then `_mark_pending` (a plain upsert, which overwrites
rather than blocking) — two concurrent calls could both pass the read-check before either wrote 'pending'.

**Why existing protection failed**: no protection existed; this was Certification 003's own already-named,
deliberately-deferred debt (needed a fix shape decision this sprint resolved).

**Why the fix is correct**: `_try_claim_consequence` replaces read-then-write with a genuinely atomic claim —
a fresh `INSERT...ON CONFLICT DO NOTHING` wins outright; on conflict, 'completed' is never reclaimed, 'failed'
is reclaimed unconditionally (a non-self-referential, safe transition), and 'pending' is reclaimed only if
`updated_at` is older than a 300-second staleness threshold reused from `shared/intake_queue.py::
reap_stale_jobs`'s own precedent (not a newly-guessed number).

**Self-correction during implementation**: the FIRST version reclaimed 'pending' unconditionally, reasoning
that re-entry into `handle_case_changed` already implied the outer dispatch layer wanted a retry. A regression
test written immediately after (`test_try_claim_consequence_second_attempt_on_still_pending_row_loses`) proved
this wrong — a self-referential `status='pending'`→`'pending'` transition that any number of concurrent
callers could all satisfy. Corrected to the staleness-gated version before being reported done.

**Regression proof**: `tests/test_case_evolution.py` (10 tests, including the one that caught the flaw), plus
6 test files' own fake-Supabase harnesses updated to model the new atomic semantics correctly (45 more tests
across those files, all passing). Phase 6 adversarial re-attack gave this fix the most scrutiny of the whole
sprint and found it holds, with one documented assumption (default Postgres READ COMMITTED isolation).

## Fix E — `routers/intake.py::intake_kreiraj` and `api.py::kreiraj_predmet` had zero double-submit protection

**Root cause**: a bare, unconditional `predmeti` INSERT in both endpoints, unlike `smart_intake.py`'s own
atomic-claim-protected case-creation path.

**Why existing protection failed**: no protection existed; these 2 entry points never received the same
hardening `smart_intake.py`'s finalize path got in an earlier sprint.

**Why the fix is correct**: a recent-duplicate check (same user + naziv within 5s → 409) before the insert.
Explicitly a check-then-insert mitigation, not full atomicity — documented as such, since true atomicity
needs a client-generated idempotency key (a frontend change out of scope for this backend-only sprint).

**Regression proof**: `tests/test_intake.py` (2 new), `tests/test_sentinel_reliability_fixes.py` (1 new),
5 pre-existing test files' mocks updated. Phase 6 confirmed the `.eq("user_id", ...)` scoping is present in
both (no cross-tenant false-positive) and that 409 is the correct client-facing signal.

## Fix F — `intake_kreiraj`'s client-link step had no status field in its response

**Root cause**: every other optional step (`rok_dodat`/`docs_linked`/`billing_kreiran`) reports its own
outcome; the client-link step did not, bundled into the same code region as Fix E.

**Fix**: `klijent_povezan` added to the response, mirroring the sibling fields' own pattern.

**Regression proof**: covered by the same `tests/test_intake.py` changes as Fix E.

## Fix G — `api.py::update_predmet` had no optimistic-concurrency guard

**Root cause**: a blind `.update(allowed).eq("id",...).eq("user_id",...)` — no version/timestamp precondition.

**Why existing protection failed**: no protection existed; `predmeti.updated_at` (genuinely trigger-refreshed
on every UPDATE) was available but never used as a concurrency token.

**Why the fix is correct**: an opt-in `if_updated_at` client-supplied value, used as a WHERE precondition when
present; 0 rows matched → conflict. Opt-in and backward-compatible — a caller not sending it gets the exact
prior behavior.

**Self-correction (Phase 6)**: the first version's 409 conflated a genuine stale-write with "predmet_id
doesn't exist at all" — a real, minor, disclosed flaw (not a security gap, ownership scoping was always
correct either way). Fixed with a cheap follow-up existence check distinguishing 404 from 409.

**Regression proof**: `tests/test_sentinel_reliability_fixes.py` (4 tests, including the 404-vs-409 case the
Phase 6 fork's finding produced).

## Fix H — `routers/workspace.py::get_workspace`'s primary gather had no `return_exceptions=True`

**Root cause**: unlike this same file's own `_fetch_recently_completed` sibling gather (which correctly uses
`return_exceptions=True`), the primary 3-way gather did not — a transient failure in any ONE sub-fetch raised
unhandled, discarding the other two's results and taking down the whole daily operational board.

**Why the fix is correct**: matches the sibling gather's own already-correct, already-proven pattern exactly
— each sub-fetch degrades to an empty list independently on its own failure, logged with the specific bucket
name for operator visibility.

**Regression proof**: `tests/test_omega_sprint004_workspace.py` (2 new tests: one sub-fetch failing still
returns a coherent response; no-failure case behaves exactly as before). Phase 6 confirmed the all-3-fail case
also degrades safely (every downstream loop/sort/count is a no-op over empty lists).

## Total regression proof

Full repository suite: **3,008 passed, 1 skipped, 0 failed** (independently re-run by the coordinator, not
cited from any fork). Zero production files touched beyond the 5 named above (`case_dna.py`, `main.py`,
`case_evolution.py`, `intake.py`, `api.py`, `workspace.py`) plus their own direct test files.

# Database Survival Report — Program Lambda, Certification 004

**Agent**: Database Reliability Engineer, with fixes implemented by the coordinator and adversarially
re-attacked in Phase 6.

## Case creation — UNSAFE for double-submission in 2 of 3 entry points — now FIXED

`smart_intake.py::_finalize_intake_job_core` (SAFE, proven, multi-sprint-hardened: atomic `claim_intake_finalize`
RPC, crash-recovery via `source_intake_job_id`, honest partial-failure reporting) vs. `routers/intake.py::
intake_kreiraj` and `api.py::kreiraj_predmet` (both a bare, unconditional INSERT — no idempotency key, no
pre-check; a double-click created 2 real `predmeti` rows, each triggering its own Case Pipeline).

**Also found**: `intake_kreiraj`'s own client-link step had no status field in its response, unlike every
other optional step (`rok_dodat`/`docs_linked`/`billing_kreiran`) — a failed/rejected client link was
invisible to the caller.

**Fix**: a recent-duplicate check (same user + same `naziv` within a 5-second window → 409) before the
insert, applied to both endpoints — explicitly a check-then-insert mitigation, not a full atomic guarantee
(documented as such; true atomicity needs a client-generated idempotency key, a frontend change out of this
backend-only sprint's scope). `klijent_povezan` added to `intake_kreiraj`'s own response shape. **Phase 6
adversarial re-attack** confirmed both dup-checks correctly scope by `user_id` (no cross-tenant leak) and that
a 409 is the correct signal for a well-behaved client (not blindly retried, unlike 5xx/429).

**Status: FIXED.** Proof: `tests/test_intake.py` (2 new tests), `tests/test_sentinel_reliability_fixes.py`
(1 new test for `kreiraj_predmet`), plus 5 pre-existing test files' own mocks updated for the new dup-check
query shape (23 tests total across affected files, all passing).

## Constraint-violation handling — SAFE, established reused pattern

`shared/audit_immutable.py::_is_unique_violation` reused across 6+ independent call sites (`billing.py::
timer_start`'s own original proven 409-not-500 fix, `copilot.py`, `services/case_evolution.py`, 2 background
watchers). No unhandled-500-on-constraint-violation path found in areas checked.

## `content_sha256` document dedup — NEEDS-DEEPER-LOOK, named as debt

Backed by a plain, non-unique index — dedup enforced at the application level (a SELECT check before INSERT),
not the database level. Two finalize calls for identical document content, same user, within a narrow
concurrent window, could theoretically both pass the check before either insert lands — structurally the
same shape as `LAMBDA003-EVT-001`, narrower in practice (requires identical content + concurrent timing), not
verified exploitable. Named in `LAMBDA004_HANDOVER.md`, not fixed this sprint (narrow, unconfirmed,
lower-priority than the confirmed findings that were fixed).

## Migration safety — SAFE, spot-checked

5 recent migrations (091, 095, 096, 102, 103) spot-checked for idempotency (`IF NOT EXISTS`/`CREATE OR REPLACE`
discipline, correct `DROP POLICY`+`CREATE POLICY` supersede patterns) — all genuinely match their own
"safe to re-run" header claims, verified not just trusted.

## Orphan records — no new instance found beyond already-tracked

The `predmet_klijenti` 0-rows issue is pre-existing and already tracked (out of this sprint's scope). No new
orphan-record class found beyond the `content_sha256` race noted above.

## Optimistic concurrency — was entirely absent, now FIXED

`api.py::update_predmet` did a blind last-write-wins update with no version/`updated_at` precondition — a
stale write from one browser tab silently clobbered newer data with no conflict ever surfaced. `predmeti` has
a real, trigger-refreshed `updated_at` column (genuinely bumped on every UPDATE via
`update_predmeti_updated_at`, not just a DEFAULT that only applies on INSERT) — no new migration needed.

**Fix**: an opt-in `if_updated_at` client-supplied token; a caller not sending it gets the exact prior
behavior (zero regression risk for existing frontends); a caller sending it and getting 0 rows back means the
row changed since they read it → 409. **Phase 6 adversarial re-attack found a real, minor flaw**: the
original version conflated "stale write" with "predmet_id doesn't exist / isn't owned by this caller" into
the same misleading 409 message. Fixed with a cheap follow-up existence check distinguishing genuine 404 from
genuine 409 — ownership enforcement itself was never affected either way, only the error message's accuracy.

**Status: FIXED.** Proof: `tests/test_sentinel_reliability_fixes.py` (4 tests: no-`if_updated_at` no-regression,
matching-token succeeds, stale-token-but-row-exists → 409, stale-token-and-row-missing → 404).

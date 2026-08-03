# Mission Olympus Backtest — Engineering Board (Agents 17, 18, 19, 20)

**Scope**: does each agent's charter, as actually written (not as it could ideally be written), direct a
reviewer toward the real historical findings named below? Tested against Project Nexus (2026-08-03),
Project Phoenix (2026-08-03), and Mission Keystone (2026-08-04).

**Methodological caveat, stated up front, honestly**: all 4 charters were authored *after* these findings
were known, and each charter's own precedent section explicitly names several of them by file:line. Asking
"would this charter catch the finding it already quotes" is partly circular. To make this a real test, not
a rubber stamp, this report evaluates two things separately for each finding: (1) does the charter's
**general, non-precedent-specific** Responsibilities language — the checks that would apply to a *different*
bug of the same shape, not just the cited one — actually direct a reviewer to look in the right place, and
(2) does the charter catch at least one finding it does *not* explicitly cite, proving generalization
rather than memorized-answer matching.

---

## Agent 17 — Architecture Review Agent

**Tested against**: Nexus finding — `routers/ccc.py`'s health_score silently diverged from the canonical
`risk_engine.py` formula under the identical field name (two implementations, same declared concept);
Nexus finding — `routers/zadaci.py::ai_analiziraj_predmet`, a 5th independent, non-deterministic
missing-document detector bypassing the platform's one declared algorithm.

**Verdict: WOULD CATCH — and generalizes, not just memorized.** The charter's first Responsibilities
bullet — *"does a new concept... have exactly one authoritative implementation, or did the change
introduce a second, competing one under a different or identical name"* — is a general principle, not a
citation of the specific bug. It would catch **any** future instance of this shape (two health-score
formulas, two risk calculators, two correlation-id generators), not only the two already named. Confirmed
by testing it against a *third*, not-cited-in-the-charter Nexus finding of the identical shape: finding #5,
"a copy of the SAME date-math bug, independently duplicated in `routers/ccc.py`" — the charter's general
"second competing implementation" check catches this too, even though the charter's precedent section only
names the health-score and detector examples, not the date-math duplication specifically. This is real
evidence of generalization, not just circular citation-matching.

**Nuance, stated honestly**: catching that ccc.py had "its own inline reimplementation" (a structural
duplication) is not the same as independently discovering the *subtle date-math bug itself* (naive-vs-aware
datetime comparison) hidden inside a single, non-duplicated implementation. Agent 17 would flag "this
should call the canonical function instead of reimplementing it" — which, once acted on, incidentally
eliminates the duplicate bug — but would not, on its own charter, independently verify the *correctness* of
the canonical implementation it's pointing the fix toward. That verification is Agent 18's or QA's job, and
neither charter explicitly lists "verify timezone-aware datetime comparison correctness" as a check (see
Agent 18's gap below).

## Agent 18 — Backend Engineering Review Agent

**Tested against**: Project Phoenix's headline finding (`asyncio.gather(..., return_exceptions=True)`
swallowing handler exceptions before `dispatch_pending_events()`'s retry-tracking ever saw them); Mission
Keystone's multi-worker Event Bus duplicate-dispatch race.

**Verdict: WOULD CATCH.** Both are named explicitly and specifically in the charter's Responsibilities
section (the `claim_pending_events()`/`MAX_DISPATCH_ATTEMPTS` bullet, the retry/dead-letter bullet) — this
is the charter with the highest precedent-specificity of the 4, closest to "memorized answer" territory.
To test generalization independently of the named citations, this agent's *underlying* principle — "does a
shared resource under multi-worker concurrency have atomic claim, and does a repeated request produce a
duplicate row" — is a transferable software-engineering check, not specific to Event Bus. It would
plausibly extend to, e.g., a *different* future shared-outbox-shaped table with the same unclaimed-SELECT
pattern, which is the actual generalization test that matters for this codebase (this pattern already
appears twice — `intake_jobs` and `events` — so a third instance is a real, not hypothetical, future risk).

**Gap found, stated honestly**: Nexus finding #6 — `routers/ccc.py`'s document query never selected
`tip_dokaza`, a live silent bug (the SQL `SELECT` string never requested the column the filtering logic
needed) — is **not** clearly caught by this charter as currently written. The charter's Role line promises
"database... correctness" broadly, but every Responsibilities bullet is concurrency/transaction/event-
specific; none say "verify a SELECT actually fetches every column the downstream code reads." This is a
plain, different bug class (a data-completeness/query-correctness bug, not a concurrency bug) that doesn't
fit any of the 4 Engineering Board charters cleanly — Architecture Review (17) checks for duplicate
*implementations*, not for a single implementation silently omitting a column; Reliability & Chaos (20)
attacks failure/recovery, not a query that succeeds but returns incomplete data. **Recommend**: add an
explicit bullet to Agent 18's Responsibilities — "does every SELECT/query statement fetch every column the
consuming code actually reads downstream" — closing this real, demonstrated gap.

## Agent 19 — Frontend Engineering Review Agent

**Tested against**: Nexus finding #7 — Case Genome refresh's false "success" toast on genuine LLM failure
(backend correctly returns `{"greska": ...}` fail-soft, frontend never checked before choosing the toast);
Keystone's `GEN-1`/`GEN-2` findings (stale-analysis-not-flagged, silent 90s watcher timeout).

**Verdict: WOULD CATCH.** The charter's first bullet — *"does the frontend show a success toast/state
without checking the backend's actual response for a fail-soft error marker"* — states the Nexus finding
almost verbatim, which is expected since it's the named precedent, but the underlying check ("does the
frontend branch correctly on every documented backend response shape, not just the happy path") is general
and would catch the same class of bug on any other endpoint with a fail-soft `{"greska":...}`-shaped
response the frontend doesn't check. The GEN-1/GEN-2 bullets are similarly general ("silent background-task
failure with no user signal," "stale-state indicators") — these describe a checkable pattern, not a single
instance.

**No gap found for this agent specifically** — its four Responsibilities bullets map cleanly onto four
distinct, real historical findings from two different missions, with no overlap between them.

## Agent 20 — Reliability & Chaos Agent

**Tested against**: all of Sentinel's chaos work, Phoenix's full charter, and Keystone's multi-worker
race — already the charter's own explicit precedent section.

**Verdict: WOULD CATCH**, with the least circularity risk of the 4, because its Responsibilities section is
written as a *methodology* (simulate crash/duplicate/delay/retry-exhaustion/dead-letter; check idempotency;
never assume a prior fix still holds) rather than a list of specific historical bugs. This is the correct
shape for a chaos-testing charter — Phoenix and Keystone's own real value came from applying exactly this
generic methodology to whatever code existed at the time, not from checking a fixed list. The charter's
explicit "never assume a prior mission's fix is still correct" bullet is itself validated by this backtest's
own live mini-test below, which re-verifies rather than assumes.

**No gap found** — this charter's generality is its own answer to the circularity concern; it does not
need a novel finding to prove generalization the way 17-19 did, because its method (not its target list) is
what's being tested, and that method is exactly what Sentinel/Phoenix/Keystone already proved works when
actually run.

---

## Live forward-looking mini-test — does Agent 20 correctly recognize a FIXED state, not just broken ones?

Read `services/event_bus.py` directly, today (not from memory of Phoenix's/Keystone's own reports):

- `publish_async()` (line ~302): re-raises after `asyncio.gather(..., return_exceptions=True)` completes,
  with an inline comment explicitly documenting the original bug and the fix rationale. Confirmed present.
- `MAX_DISPATCH_ATTEMPTS = 5` (line 378), `_is_missing_function_error()` (line 381),
  `claim_pending_events` RPC call with graceful fallback (lines ~405-423): all confirmed present, matching
  Keystone's own report exactly.
- Ran the actual test suites: `python -m pytest tests/test_phoenix_reliability_failure_recovery.py
  tests/test_keystone_readiness_validation.py -q` → **20 passed**, live, right now.

**Conclusion a fresh Agent 20 reviewer would reach today**: gate state **`PROTECTED`** for both the
handler-failure-detection defect and the multi-worker duplicate-dispatch race — both fixes are present,
tested, and passing. This is the correct, non-trivial result: it proves the charter's "re-verify, don't
assume" instruction, applied for real, converges on the same conclusion the original missions reported,
rather than either rubber-stamping or manufacturing a false regression to seem thorough.

---

## Gaps found in this backtest (summary)

1. **Agent 18** has no explicit check for "does a query fetch every column downstream code needs" — a
   real, demonstrated Nexus finding (`ccc.py`'s missing `tip_dokaza` select) that doesn't cleanly fit any of
   the 4 Engineering Board charters as currently written. Recommend adding this bullet to Agent 18.
2. **No agent among 17-20 independently verifies datetime/timezone-comparison correctness** inside a
   single, non-duplicated implementation — Agent 17 catches *duplication* of such a bug, not the bug's
   existence in the canonical, non-duplicated version. This is arguably acceptable (QA Engineering's
   existing charter, Agent 11, already covers correctness-of-implementation testing) but worth naming
   explicitly as a boundary, not silently assumed covered.

Both gaps are narrow, specific, and actionable — not a wholesale charter failure. 3 of 4 agents (17, 19,
20) show genuine generalization beyond their cited precedents; Agent 18 is more precedent-specific and has
one identified, fixable gap.

# Reliability Verification Report — Program Delta, Sprint 003 (2026-08-05)

Proof that this sprint's migration (Pipeline A's 2 emissions, `rocista.py`'s 1 emission, `ROCISTE_ZAKAZANO`'s
first-ever wiring) did not weaken reliability — same mechanism Sprints 001-002 already proved, reused, not
rebuilt.

## Per-event proof, against the mission's 8 required properties

| Property | `DOCUMENT_ACCEPTED` (Pipeline A) | `NEW_EVIDENCE_REGISTERED` (Pipeline A) | `ROCISTE_ZAKAZANO` |
|---|---|---|---|
| Replay | ✔ same `(event_id, consequence_name)` mechanism as Pipeline C's own emission — identical event_id on redispatch, both consequences skip re-execution | ✔ same | ✔ tested (`test_rociste_zakazano_reuses_genome_refresh_executor_end_to_end`, replay asserted) |
| Retry | ✔ Event Bus `MAX_DISPATCH_ATTEMPTS=5`, unchanged | ✔ | ✔ |
| Crash recovery | ✔ a crash after `genome_refresh` completes, before `timeline_entry`, resumes exactly where Sprint 001 already proved for Pipeline C — same executors, same table | ✔ single-consequence event, crash-before-complete degenerates to "not yet completed", covered by the same idempotency check | ✔ single-consequence event, same reasoning |
| Duplicate event | ✔ two separate `events` rows (e.g. accidental double-emission) get two separate `event_id`s — each independently idempotent, no cross-contamination | ✔ | ✔ |
| Parallel execution | ✔ Pipeline A and Pipeline C's own `DOCUMENT_ACCEPTED` emissions for DIFFERENT predmet_ids never share an `event_id` — no race | ✔ per-document `event_id`, same reasoning as Sprint 002's own evidence-parallel test | ✔ |
| Audit continuity | ✔ generic `case_evolution_consequence_completed` per consequence, unchanged | ✔ | ✔ |
| Provenance continuity | ✔ `result_ref` = verified `case_dna.verzija` / timeline row id, unchanged executor | ✔ `result_ref` = `dokument_id` or a named `skipped_*` reason, unchanged executor | ✔ `result_ref` = verified `case_dna.verzija` |
| Correlation continuity | ✔ `emit_durable` reads `current_correlation_id()` at emission time, same helper used by every other call site | ✔ | ✔ |

## What's genuinely new this sprint, reliability-wise

1. **Two `asyncio.sleep(N)` heuristics removed entirely** (Pipeline A's `sleep(3)`, `rocista.py`'s `sleep(2)`)
   — neither was a real reliability mechanism (a slow GPT call could always exceed either window), and their
   removal doesn't weaken anything: `genome_refresh`'s own before/after `verzija` verification never depended
   on the sleep for correctness, only as a best-effort ordering nudge. The event-emission-order approach (see
   Event Migration Report) is honestly no stronger a guarantee, but it is not weaker either, and it removes a
   fixed, unconditional delay from the response path.
2. **Pipeline A's evidence-classify and genome-refresh failures now retry** — previously fire-and-forget
   `asyncio.create_task`, silently dropped on failure, exactly the same class of gap Sprint 002 closed for
   Pipeline C. Sprint 003 closes the LAST 2 instances of this specific gap platform-wide (confirmed by the
   repo-wide grep in the Event Migration Report's own Task 4 section).
3. **`ROCISTE_ZAKAZANO` goes from zero reliability properties (it never ran at all) to all 8** — not a
   regression risk in any direction, since nothing depended on this event type doing anything before.

## Ordering dependency, honestly assessed (not a new capability, a documented trade-off)

`_consequence_genome_refresh`'s own correctness (verified via `case_dna.verzija` increment) does NOT depend on
`tip_dokaza` having been set by evidence classification first — Genome recomputes from whatever state exists
at call time and always increments `verzija` on a genuine successful run, regardless of whether classification
already ran. The ordering (evidence emitted before genome) is a DATA QUALITY nicety (Genome's own scoring
might undercount evidence types if classification hasn't finished), not a RELIABILITY question (genome_refresh
still succeeds, verifies, and audits correctly either way). This distinction — reliability vs. data quality —
is the same one Program Delta has held since Sprint 001 (Program Delta owns orchestration reliability, not AI
content correctness) and is not re-litigated here.

## Test 7 — repo-wide bypass search, the strongest form of this sprint's own proof

`tests/test_delta_sprint003_full_convergence.py::test_no_new_direct_call_bypass_of_canonical_consequence_functions`
walks every `.py` file in the repository (excluding `tests/`) searching for `_run_genome_background(`,
`klasifikuj_i_sacuvaj(`, and `_run_conflict_check(` — and asserts the only files containing each are the
function's own definition, `services/case_evolution.py`, and (for `_run_conflict_check` only)
`routers/intake.py`'s own documented, deliberate exception. This is not a one-time manual grep whose result
could silently go stale — it is a regression test that will fail the day anyone (human or AI) adds a new
direct call bypassing the canonical mechanism.

## Full suite result

Confirmed via a full background run before this sprint's commit — see Sprint 003 Mission Report for the exact
final pass/fail count.

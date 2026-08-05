# OCR & Intake Capacity Report — Program Omega, Master Sprint 001 (2026-08-06)

Agent 2's own central question: *"Da li advokat može poslati haotičnu fasciklu i dobiti organizovan predmet?"*
Answer: mostly yes, with 2 real capacity gaps found and fixed this sprint, and 1 named, deliberately deferred.

## Capacity finding 1 — batch upload could exceed the gunicorn worker timeout (FIXED)

**Evidence**: `gunicorn.conf.py` sets `timeout = 120`. `POST /api/smart-intake/documents`
(`routers/smart_intake.py::upload_intake_documents`) processed every file in a batch SEQUENTIALLY inside one
request — read → AES-GCM encrypt → Supabase Storage upload → `enqueue_job` RPC — with the response only
returned after every file finished. For the mission's own named Priority 1 scenario (500 documents), even a
conservative 200-300ms per file adds up to 100-150s, comfortably over the 120s limit for anything but small
files on a fast connection.

**What this meant in practice, before the fix**: gunicorn kills the worker mid-request. Every file already
enqueued IS safe (durable `intake_jobs` row, `idempotency_key` prevents a duplicate on resubmission) — no data
loss in the strict sense — but the LAWYER never receives any response telling them which of the 500 files got
through before the connection died. The client sees a generic connection failure with no actionable next
step.

**Fix**: `_UPLOAD_TIME_BUDGET_S = 90.0` — a deliberate margin under the real 120s limit. The upload loop now
checks elapsed time BEFORE starting each new file (never mid-file — a file already in progress always
finishes and is durably enqueued). If the budget is exceeded, the endpoint returns immediately with
`{"nastavlja": true, "preostali_fajlovi": [...]}"` — an honest, structured, resumable response the frontend
can act on by resubmitting exactly the remaining files in a follow-up call, safely (already-processed files'
`idempotency_key` makes any accidental resubmission a no-op, not a duplicate).

**Tested**: `tests/test_omega_sprint001_batch_intake.py::test_upload_batch_stops_early_when_time_budget_exceeded_and_reports_remaining`
(real elapsed-time-based, not a mocked clock — see the test's own docstring for why) and
`test_upload_batch_within_time_budget_processes_everything_normally` (proves zero behavior change for the
common small/medium batch case).

## Capacity finding 2 — no batch-finalize mechanism existed at all (FIXED)

**Evidence**: repo-wide grep for `finalize.*batch`/`batch.*finalize` in `routers/smart_intake.py` returned zero
matches before this sprint. Each uploaded file becomes its own `intake_jobs` row; finalizing it into a real
case requires a SEPARATE `POST /jobs/{job_id}/finalize` call. For 500 uploaded files, that is 500 separate
manual (or frontend-scripted) finalize calls, with NO single response summarizing what happened across the
whole batch — the mission's own explicit example output ("Obrađeno 500 dokumenata. Pronađeno: 1 postojeći
predmet...") had no code path that could produce it.

**Fix**: `POST /jobs/finalize-batch` (`BatchFinalizeReq.job_ids`, up to 1000). Loops calling
`_finalize_intake_job_core` (the SAME logic the single-job endpoint uses, extracted — see "a necessary
refactor" below) per job, aggregates: total processed, success/failure counts, unique cases touched with a
document count per case (so 40 documents landing in the same existing case show as ONE row, not 40 disjoint
successes), documents flagged for review, deadlines added. Reuses everything — zero new AI capability, zero
new Genome/Timeline/Evidence logic, per the mission's own "Omega Principle."

**A necessary refactor, done as safely as possible**: calling the RATE-LIMITED `finalize_intake_job` directly
in a loop would have hit its own `20/minute` slowapi limit partway through any batch bigger than 20 — slowapi's
`@limiter.limit()` decorator genuinely checks/increments its counter on every call to the decorated function,
not only requests routed through Starlette (confirmed by reading `shared/rate.py` and slowapi's own
`Limiter._check_request_limit` before choosing a design). `finalize_intake_job` was split into a thin decorated
wrapper + an undecorated `_finalize_intake_job_core` containing the ENTIRE original function body, unchanged —
a pure extraction, verified by running all 10 existing finalize-related test files afterward with zero
regressions (they all still call `finalize_intake_job` directly and get identical behavior, since it's now a
1-line delegator).

**Tested**: `tests/test_omega_sprint001_batch_intake.py` — 4 tests covering aggregation-with-dedup, per-job
failure isolation, proof the rate limit is genuinely bypassed for the core (30-job batch, bigger than the
single-job endpoint's own 20/minute), and proof the extraction didn't change the single-job endpoint's own
behavior.

## Capacity finding 3 — Genome recomputes once per finalize call, not once per case (NOT fixed, named honestly)

If 500 documents all belong to ONE case and are finalized via 500 separate `_finalize_intake_job_core` calls
(even via the new batch endpoint, which still loops per-job), each call that successfully links a document
still emits its OWN `DOCUMENT_ACCEPTED` event, and Case Evolution Engine still triggers a FULL Genome recompute
per event — up to 500 full recomputes for what is conceptually "one case receiving 500 documents."

**Why not fixed this sprint**: closing this properly means changing how `_finalize_intake_job_core` decides
WHEN to emit `DOCUMENT_ACCEPTED` (batching multiple jobs' worth of accepted documents into ONE emission per
touched `predmet_id`, deferred until the whole batch's document-linking work is done) — a real, non-trivial
change to Program Intake/Delta's own already-hardened emission logic, carrying real regression risk to
extensively-tested, production-critical machinery. Attempting it inside this same sprint, on top of the
upload-timeout and batch-finalize fixes already made, would have meant less careful testing of everything at
once — not the right tradeoff.

**Recommended direction for a future sprint**: `_finalize_intake_job_core` could accept an internal
`suppress_document_accepted: bool` parameter; `finalize_intake_jobs_batch` would then collect, per unique
`predmet_id` touched, the full list of accepted document names across every job in the batch, and emit
`DOCUMENT_ACCEPTED` exactly ONCE per touched case after the loop completes — mirroring the coalescing Sprint
001 already proved works for a single multi-document finalize call, now generalized to a multi-JOB batch.

## Scenario coverage, honestly assessed against the mission's own testing standard

| Scenario | Status |
|---|---|
| A. 10 documents | Fully covered by existing Program Intake test suite (unchanged) + this sprint's own batch tests |
| B. 100 documents | Same code path as A and C — no different logic kicks in at 100; covered by the same tests, not separately load-tested with 100 REAL documents in this sprint (no live environment available to this session) |
| C. 500 documents | The upload-endpoint time-budget fix and batch-finalize endpoint directly target this scenario; NOT live-tested against 500 real files end-to-end (same reason as B) — tested at the unit/mock level against the exact mechanisms that would be exercised |
| D. 500 with duplicates/bad OCR/wrong order/unclear names | Duplicate detection: unchanged, already content-hash based (Program Intake Sprint 007), scale-independent. Bad OCR: routes to Review Required, unchanged. Wrong order/unclear names: Ownership Resolution never relies on filename or upload order (Program Intake Sprint 006's own explicit design), so this scenario is structurally already handled — not separately tested this sprint since no NEW code touches this path |
| E. Interruption during processing | The upload endpoint's new time-budget break directly addresses this for the UPLOAD phase specifically; the FINALIZE phase's own crash-recovery (assimilation_complete-gated claim, Program Intake Sprint 007) was already proven and is unchanged by this sprint's batch-finalize wrapper (each per-job call still goes through the same claim/idempotency machinery) |

**Honest gap**: this sprint's own testing is unit/mock-level, proving the MECHANISMS work correctly in
isolation and in combination — it does not constitute a live load test against 500 real scanned documents.
That remains a real verification step before declaring the 500-document scenario production-ready under real
network/storage/GPT-latency conditions.

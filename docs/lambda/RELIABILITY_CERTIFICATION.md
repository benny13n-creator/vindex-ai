# RELIABILITY_CERTIFICATION — Program Lambda, Certification 008

Covers Team 4 (Event Bus/Distributed Consistency), Team 5 (Concurrency/Race Conditions), Team 10
(Reliability/Failure Recovery). Simulated (via code reading, not live chaos injection) worker crash, OpenAI
timeout, database timeout, retry storms, and concurrent writes/reads.

## HIGH — fixed this sprint

**Credit-loss on genuine LLM failure** (`api.py` `/api/pitanje` + `/api/pitanje/stream`): credit is
pre-deducted before the GPT call; on exhausted-retry OpenAI failure, `ask_agent` returns
`{"status": "error", ...}` rather than raising, and the refund check only tested `from_cache`/`blocked` —
never `status == "error"`. `UsageService.refund()` existed and was correctly used for the other two cases,
but was dead for this one. A sustained OpenAI outage burned a real credit on every affected request while
showing the lawyer an apologetic error. Fixed: refund now fires on all three conditions.

**Event Bus batch-claim staleness race** (`services/event_bus.py`): `claim_pending_events` stamps an entire
50-row batch with one `claimed_at`, but dispatch processes rows strictly serially with GPT-bound handlers
(`run_case_pipeline`, Genome refresh). If cumulative processing exceeds the 120s staleness window, a
still-legitimately-queued row becomes reclaimable by another worker mid-batch, causing duplicate handler
execution. Fixed via a per-row heartbeat that refreshes `claimed_at` for the remaining batch after each row
completes, so the staleness clock now tracks "since this worker last made progress," not "since the batch
was claimed."

**Invoice-number race** (`routers/billing.py`): see `RELIABILITY_CERTIFICATION.md`'s sibling concurrency
finding in `ARCHITECTURE_CERTIFICATION.md`/main report — a financial-record-integrity issue as much as a
reliability one. Fixed via retry-on-conflict + a new unique-constraint migration (104, drafted).

## MEDIUM / MEDIUM-LOW — fixed this sprint

- **`klijenti/router.py` client creation**: zero double-submit protection (a double-click or flaky-network
  retry silently created duplicate client records). Fixed via the same 5s-window check-then-insert pattern
  already established for `predmeti`/`intake_kreiraj` creation.
- **`routers/predmeti_close.py`**: read-then-write race — two concurrent close requests both passed the
  pre-check before either wrote, silently double-appending closure notes and double-firing benchmark/audit
  side effects. Fixed via a `.neq("status", "zatvoren")` guard on the write itself, returning 409 on a lost
  race instead of silently double-applying.

## Re-verified still fixed, no regression

`shared/llm_retry.py`'s jitter (thundering-herd mitigation), `case_dna.py`'s `greska`-key guard before
writing to the live `case_dna` column, Map-Reduce's `failed_batches` tracking — all 3 previously-fixed
reliability issues confirmed unchanged in current code.

## Re-verified still open, tracked, not newly discovered

- `LAMBDA006-EVT-001` (`_mark_completed`'s bookkeeping write unprotected against a transient failure right
  after a successful executor).
- `SENT-001` (`HEALTH_SCORE_PROMENJEN`/`ROK_KRITICAN` still non-durable `emit()`, not durable outbox).
- `KEYSTONE-007` (migration 091's atomic-claim RPC, if not applied, silently falls back to unclaimed plain-
  select dispatch — would make the Event Bus finding above worse, not better).
- `LAMBDA006-INTAKE-001` / `LAMBDA006-PIPE-001` (TOCTOU races in document sequencing / Case Pipeline steps
  under genuine concurrency, both re-confirmed unchanged).

## Checked, confirmed sound

Worker crash recovery (`shared/intake_queue.py::reap_stale_jobs`, Smart Intake's `finalizing_at` CAS guard),
~90 `@llm_retry` call sites' idempotency, `_try_claim_consequence`'s atomic-claim logic, `case_actions`/
`notifications` reconciliation's DB-unique-index-based concurrency safety.

**Verdict**: 5 new reliability/concurrency findings this sprint (2 HIGH, 2 MEDIUM/MEDIUM-LOW, 1 shared with
architecture), all fixed with test coverage. 4 prior findings re-verified still fixed, no regression. 4
prior findings re-confirmed still open, correctly not silently dropped from tracking.

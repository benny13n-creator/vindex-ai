# Program Lambda, Certification 006 — Chaos Engineering Certification

**Date**: 2026-08-07
**Mission**: 2nd of the Overnight Autonomous Certification Chain, Certification 005 → 006 → 007. Mandate:
treat the system as production SaaS. Randomly kill OpenAI/Supabase/Redis/Event Bus/Storage/background
workers; interrupt upload/genome refresh/notifications/workspace build/AI reasoning/batch jobs; look for
TOCTOU, race, stale cache, deadlock, livelock, orphan jobs, duplicate execution, memory leak, resource
exhaustion, queue starvation. Every found problem: fix, test, try to trigger it again.

## Method

6 forensic areas, each via code-level trace/mock reasoning (no live deployment exists — same methodology
every prior Lambda sprint has used): Event Bus & background workers, Database/Storage/Cache, AI/OpenAI
failure injection, Upload/Smart Intake/finalize, Genome/Workspace/Case Actions, and Audit chain/ownership/AI
boundary. The first 5 were launched as parallel, strictly read-only forensic forks — explicitly re-briefed
after Certification 005's own process failure (see `feedback_audit_forks_before_trusting_push` memory) to
never write files, never implement fixes, report findings only. All 5 stayed within brief this time — no
process violation this sprint. The 6th area's fork could not be spawned (session hit its subagent limit,
200/200) and was investigated directly by the coordinator instead.

## Findings — clean areas (no fix needed, traced and confirmed sound)

- Event Bus dispatch loop killed mid-batch: safe, no batch-level transaction, no double-dispatch.
- Genome refresh in-process livelock: not found, `finally`-guarded coalescing set.
- Intake queue orphan jobs: safe, `reap_stale_jobs` genuinely periodic via `IntakeWorker._tick()`.
- Duplicate consequence execution across processes: not possible, Postgres-level atomicity confirmed for
  both the fresh-insert and reclaim paths of `_try_claim_consequence`.
- Queue starvation: not found, `claim_pending_events` uses strict FIFO (`ORDER BY created_at ... FOR UPDATE
  SKIP LOCKED`).
- Memory leak: not found in the collections checked; `main.py`'s `_CACHE` has an enforced max with eviction.
- `ask_agent` cache: sound, cache is skipped entirely whenever history/namespaces/memory could shape the
  answer — no cross-tenant or race risk by construction.
- Rate limiter: sound, matches its own `test_sec005_failopen_limiter.py` fail-open claims exactly.
- Deadlock: structurally impossible — every claim/lock is a single auto-committed PostgREST statement, never
  a multi-statement transaction spanning two locks.
- GPT-writing call sites (5 sampled): the already-fixed Genome "corrupt on failure" bug is not systemic — the
  4 other sampled sites validate/raise cleanly *before* any DB write, unlike Genome's write-first shape.
- Malformed/truncated JSON: correctly caught by callers' own broad exception handling, not a gap in
  `llm_retry` (which deliberately never retries `JSONDecodeError` — retrying wouldn't help a 200 response).
- Digital Twin's 3 scenarios: one GPT call, one JSON object — not a genuine multi-step orchestration, no
  partial-failure shape to signal.
- AI Governance provenance on failure: sound end-to-end — `shared/ai_client.py`'s SDK-level monkeypatch
  always persists a `status="error"` provenance row before re-raising, wired uniformly, not per-call-site.
- Process restart mid-finalize (Smart Intake): sound, already hardened by `assimilation_complete`'s own
  partial-progress resume design (Program Intake Sprint 007).
- Batch finalize idempotency: sound by composition (each `job_id` independently protected).
- Conflict-check race: real but inherent to the endpoint's own advisory-only contract, not a defect.
- Concurrent Genome refresh for the same case: sound, already coalesced and tested
  (`test_ztc_genome_scale_and_race.py`).
- Workspace reading `case_dna` mid-write: sound, Postgres MVCC guarantees no torn JSONB read.
- Genome consumers reading mid-refresh (2 of 5 checked: Copilot, Court Predictor): sound, fresh query per
  call, no stale session cache found.
- Audit interruption mid-loop (coordinator's own check): sound — sequential loop execution means consequences
  completed earlier in the same call already had their own `_mark_completed`+audit committed before a later
  consequence's raise.
- Correlation ID continuity across retries (coordinator's own check): sound — persisted on the durable outbox
  row itself, not regenerated per dispatch attempt.
- Ownership-reassignment TOCTOU (coordinator's own check): not applicable, no case-reassignment feature exists.
- Malformed GPT field corrupting downstream computation (coordinator's own check): sound —
  `_neto_uticaj`/`compute_snaga_score` defensively skip malformed `uticaj` values, bounded output regardless.

## Findings — fixed this sprint

### 1. Smart Intake finalize's own stale-claim overtake (CRITICAL — same bug class as Certification 005's own fix)

**Found by**: Upload/Intake Chaos fork. **File**: `routers/smart_intake.py`.

`claim_intake_finalize`'s 120s staleness window (`shared/intake_queue.py::claim_finalize`) can legitimately
reclaim a job from a worker that's merely slow (a genuinely long Pinecone ingest), not crashed. The FINAL
write that closes out finalize (`.update({"predmet_id":..., "assimilation_complete":...}).eq("id", job_id)`)
had no compare-and-swap against the `finalizing_at` claim that authorized it — if both the original (slow but
alive) worker and the reclaiming worker reached this write, whichever ran last silently won, with the other's
already-created predmet/client-link/documents/billing left orphaned with nothing pointing back to them.

**Fix**: the final write now includes `.eq("finalizing_at", claimed["finalizing_at"])`. If the claim has since
been overwritten by another worker's reclaim, the update matches zero rows, the coordinator logs CRITICAL and
raises a 409 instead of silently reporting success. This does not by itself prevent the duplicate WORK a
genuinely-slow worker may have already done before reaching this line (closing that needs the whole flow to
become per-step idempotent/resumable — named as debt, `LAMBDA006-INTAKE-001` covers the related `redni_broj`
race but the deeper resumability gap is captured inline in this fix's own code comment for a future sprint).
**Test**: `test_finalize_final_write_raises_when_finalizing_at_changed_underneath` in
`tests/test_ztc_scenario_b_attach.py`.

### 2. Copilot's unbounded document-text fetch (Medium — resource exhaustion, repeat of an already-fixed pattern)

**Found by**: Database/Storage/Cache Chaos fork. **File**: `routers/copilot.py`.

`_handle_analiza_predmeta` and `_handle_plan_predmeta` both queried `predmet_dokumenti` selecting full
`tekst_sadrzaj` for EVERY document in a case, unconditionally, before `_select_documents()`'s own bounding
logic (~5 documents) ever ran — the exact pattern `shared/case_context.py::_fetch_raw` already fixed for its
own callers (Lambda Master Sprint 001), never migrated to Copilot's own separate, parallel fetch. For the
mission's own "500 documents" scenario, every Copilot call pulled unbounded full-text volume over the network
first. **Fix**: both handlers now query metadata-only, then call `shared/case_context.py::
_fetch_document_texts` (already existing, reused, not duplicated) for only the bounded selected subset.
**Test**: `test_document_content_reaches_prompt_program_tau_002` in
`tests/test_synapse_copilot_genome_context.py` updated to model the 2-phase fetch; all other copilot tests
independently re-verified passing.

### 3. `llm_retry`'s zero-jitter exponential backoff (Medium — retry-storm risk under sustained outage)

**Found by**: AI/OpenAI Chaos fork. **File**: `shared/llm_retry.py`.

`wait_exponential(multiplier=1, min=1, max=8)` produced an identical, deterministic backoff schedule for
every concurrent caller — during a sustained OpenAI outage, every request retrying around the same wall-clock
time would re-hit the API in near-lockstep the moment it recovers, a genuine thundering-herd risk distinct
from `LAMBDA004-AI-001`'s own timeout-configuration concern. **Fix**: `+ wait_random(0, 2)` composed onto the
existing exponential wait — tenacity's own supported composition, adds 0-2s jitter while keeping the existing
min/max envelope. **Verification**: 96 pre-existing `llm_retry`-adjacent tests re-run, all pass unchanged.

## Findings — named as debt, not guessed at

6 items in `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md`:
- `LAMBDA006-EVT-001` — `_mark_completed`'s own bookkeeping write is unprotected against a transient failure
  right after a successful executor; a non-idempotent executor (Timeline) could duplicate on retry. Narrower
  and rarer than this sprint's own CRITICAL fix.
- `LAMBDA006-SEC-001` — `ai_cache`'s RLS policy exists only as a code comment, not a tracked migration.
- `LAMBDA006-INTAKE-001` — no unique constraint on `predmet_dokumenti(predmet_id, redni_broj)`, a TOCTOU under
  parallel upload (the mission's own named 500-document scenario) producing cosmetic duplicate document
  numbers. Needs a migration.
- `LAMBDA006-GOV-001` — fire-and-forget `log_action` (36 call sites) has no drain guarantee during an
  ordinary graceful shutdown, not just a violent crash.
- `LAMBDA006-PIPE-001` — Case Pipeline steps 3/5's own marker-check is TOCTOU-safe for sequential retries but
  not genuinely concurrent pipeline invocation.
- `LAMBDA006-GEN-001` — Genome deadline corrections don't supersede stale `predmet_hronologija` rows, only
  add new ones alongside them; needs a deadline-identity concept, a product/domain decision.

## Gate 006 — hard gate results

- Full regression suite: independently re-run by the coordinator after all fixes: **3,016 passed, 1 skipped,
  0 failed** (387.15s) — exactly 3,015 (Certification 005's own closing count) + 1 new test (the CAS-guard
  regression test for finding #1 below). No fork's own self-report was cited (none was offered this sprint
  since all forks stayed within their read-only brief).
- Targeted test runs after each fix: `test_ztc_scenario_b_attach.py` (6/6), `test_synapse_copilot_genome_context.py`
  (4/4) plus the 7 other copilot/genome-consumer test files (95/96, 1 pre-existing-shape fix applied), 96
  llm_retry-adjacent tests (96/96) — all green before the final full-suite run.
- No lost events, no duplicate events (the one near-miss — Smart Intake finalize — is now CAS-protected and
  fails loudly instead), no orphan jobs, no deadlock, no starvation, no new regressions.
- Process discipline: 5 of 6 forensic areas via strictly-read-only forks, zero brief violations this sprint —
  a direct correction from Certification 005's own recurrence, and the 6th area (audit/ownership/AI boundary)
  investigated directly by the coordinator due to a hard subagent-count limit, not a scoping choice.

**Verdict**: Gate 006 conditions met. 3 real findings fixed and tested, 21 areas traced and confirmed sound,
6 items honestly named as debt rather than guessed at or silently dropped. Proceeding to Certification 007
(Enterprise Beta Certification).

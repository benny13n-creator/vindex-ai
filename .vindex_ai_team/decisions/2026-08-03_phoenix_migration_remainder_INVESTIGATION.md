# Project Phoenix — Phase 8: Migration Remainder Investigation

**Scope**: read-only. Investigates the 3 items Mission Migration deferred (`MIGRATION-001/002/003`):
`main.py::ask_agent`, Drafting's deep generation call + `ask_analiza`, Smart Intake extraction. Answers
two questions for each: (1) is it reliable (retry/recovery/detection) regardless of audit status, and
(2) how hard would canonical audit/provenance/correlation migration actually be. No code changed.

---

## 1. `main.py::ask_agent` (core RAG Q&A pipeline, ~400 lines, `main.py:3129-3527`)

### Reliability posture: **Excellent, already**

- Every sub-step is individually try/excepted with a clean fallback: Pinecone retrieval failure →
  `{"status": "error", "message": "Sistem je trenutno zauzet..."}`; praksa/mišljenja retrieval failures
  → logged, continues without that context (never fatal); each of up to 3 possible GPT calls
  (MEDIUM path, HIGH path, HIGH→MEDIUM downgrade path) is individually try/excepted with the same clean
  degraded response.
- The whole function body is ALSO wrapped in one outer `try/except Exception` (`main.py:3523-3526`) —
  belt and suspenders.
- The low-level GPT caller `_pozovi_openai` (`main.py:2240`) is `@llm_retry`-decorated — automatic
  retry with exponential backoff for rate-limit/5xx/timeout/connection errors, no retry for 4xx.
- **No database writes happen inside `ask_agent` at all** — it's a pure retrieve→compute→return
  function (the only persistence is an in-process response cache, `_cache_get`/`_cache_set`). This
  means there is structurally **no partial-write/orphan-record risk** from this function failing
  partway — every exit path is a complete, self-consistent dict.
- Already has its own hallucination-guard layer (`KORAK 1.5`'s hard-refusal-on-uncited-article check,
  `_verifikuj_pravne_greske`, topic-drift detection with automatic HIGH→MEDIUM downgrade, structural
  JSON-schema guard on the LLM's own output) — this is, if anything, the single most defended AI call
  path in the entire codebase against silent hallucination, not a weak point.
- **Verdict**: no reliability gap found. If Project Phoenix simulates "GPT times out here," the function
  already returns a clean, correctly-classified error response, never a crash, never an inconsistent
  state.

### Migration difficulty: **Low-Medium, not "large" as previously assumed**

- Confirmed via grep: zero references to `case_context`/`log_action`/`ai_provenance` anywhere in
  `main.py` — only the automatic wrapper-level capture applies (model/prompt-hash/output-hash/
  request-level correlation_id, per Mission Atlas/Ledger's universal defaults).
- `ask_agent` takes no `predmet_id` parameter at all — it's a pure free-text Q&A entry point, not
  case-scoped by design (matches Strategy Engine's own precedent, which already calls `case_context()`
  with `predmet_id=None` for exactly this reason).
- Because the ENTIRE function is a single synchronous call with no nested `asyncio.create_task`/
  `asyncio.to_thread` boundary crossed internally, wrapping the whole function body (or its single
  call site in `routers/copilot.py::_handle_pravno_pitanje`, which already does
  `await asyncio.to_thread(_ask, q, history or None)`) in ONE `case_context(module_name="ask_agent",
  operation_name="pravno_pitanje")` would correctly tag all up-to-3 GPT calls with the same
  correlation_id, exactly like Court Predictor's endpoints already do. A dedicated `log_action` audit
  call could be added once, at the successful-response return points (or immediately after the
  `to_thread` call returns in the Copilot caller, checking `rezultat.get("status") == "success"`).
- **This is NOT a "large, deep call chain" migration** — it's one function, one wrapping point,
  no deeper package boundary to cross. The Mission Migration report's characterization of this as too
  complex to migrate safely was **more cautious than the evidence supports** — the actual GPT-calling
  logic is flat (no recursive delegation), just long (many sequential guard/format steps). Correcting
  that assessment here per this mission's own instruction to fix prior missions' inaccuracies.

---

## 2. Drafting — `generate_draft` (`drafting/router.py:404-474`) + `ask_analiza` (`main.py:3586-3645`)

### Reliability posture: **Excellent, already**

- `generate_draft`: one GPT call (`_call_openai`, `@llm_retry`-decorated, `drafting/router.py:47-48`)
  for field extraction; the rest (template fill, date normalization, compliance check) is deterministic,
  non-AI code. Whole function wrapped in one try/except (`drafting/router.py:422,469-474`) with a clean
  `{"status": "error", ...}` fallback. **No DB writes inside this function** — pure text generation,
  returned to the caller.
- `ask_analiza`: one GPT call (`_pozovi_openai`, same `@llm_retry`), full try/except
  (`main.py:3591,3642-3644`), plus its own hallucination guard (`_proveri_analiza_citate` — blocks any
  article citation not present in the source document, a citation-existence check in the same family as
  `ask_agent`'s KORAK 1.5). No DB writes here either.
- The ROUTER-level staging step (`routers/drafting.py::_stage_draft_for_review`), which runs AFTER
  `generate_draft` returns successfully, already has `quality_gate`-based confidence scoring AND (per
  Mission Migration, already done) a dedicated `log_action` audit entry.
- **Verdict**: no reliability gap. Same "flat, well-guarded, no partial-write risk" pattern as
  `ask_agent`.

### Migration difficulty: **Low**

- `routers/drafting.py::nacrt` already has `req.predmet_id` in scope at its call site
  (`rezultat = await _pokreni(_drafting_generate, req.vrsta, _skini_pii(req.opis), user["user_id"])`,
  `routers/drafting.py:550`) — wrapping this ONE call in
  `case_context(predmet_id=req.predmet_id, module_name="drafting", operation_name="nacrt")` is a
  single-line change, exactly the same pattern Court Predictor's 7 endpoints already use. `_pokreni` is
  just `asyncio.to_thread(fn, *args)` (`routers/drafting.py:164-165`) — context propagates into the
  thread correctly, same guarantee already proven for Evidence classification.
- `routers/drafting.py::analiza` doesn't have a `predmet_id` field on `AnalizaReq` — same "no case
  scope by design" situation as `ask_agent`; `case_context(predmet_id=None, module_name="drafting",
  operation_name="analiza")` would still be a valid, low-effort addition for correlation/audit
  continuity even without case-linkage.
- **Not "genuinely large"** — this is 1-2 call sites, not a deep package. Mission Migration's caution
  here was reasonable given its own time-boxed scope, but the actual migration effort is comparable to
  the Court Predictor batch already completed, not categorically harder.

---

## 3. Smart Intake extraction (`routers/smart_intake.py`, `shared/intake_worker.py`,
`shared/intake_queue.py`)

### Reliability posture: **Best of the 3 — genuine, verified, already-tested durable infrastructure**

- `shared/intake_queue.py::mark_job_failed` implements real exponential backoff (`30s * 2^attempts`,
  capped at 1h, `_BACKOFF_BASE_S`/`_BACKOFF_CAP_S`) up to `max_attempts` (default 5), then dead-letters
  the job (`status='failed'`) via the atomic `fail_intake_job` RPC (status + audit + durable
  `DocumentJobFailed` outbox event in one transaction, confirmed in migration 073 and re-confirmed
  working end-to-end by Project Sentinel's own fix — `on_document_job_failed` now creates a
  `proactive_alerts` row for this exact event).
- **The reaper genuinely exists AND is genuinely called**: `reap_stale_jobs`
  (`shared/intake_queue.py:129-152`) finds jobs stuck in a non-terminal status
  (`preprocessing`/`classifying`/`extracting`/`matching`/`dedup_check`) whose `claimed_at` is older than
  a threshold (worker crashed mid-claim) and routes them back through the SAME `mark_job_failed`
  retry/dead-letter path. Confirmed called from `shared/intake_worker.py:105` (the worker's own loop),
  not just a defined-but-unused function — and covered by 3 separate test files
  (`test_intake_phase0.py`, `test_intake_worker.py`, `test_intake_e2e_restart.py`).
- `claim_intake_job` uses `SELECT ... FOR UPDATE SKIP LOCKED` (migration 073) — confirmed safe against
  two workers claiming the same job.
- OCR failure within a job is explicitly fail-soft by design (confirmed by Project Sentinel earlier):
  saved with `confidence=0.0`, routed to a review queue, job still completes rather than retrying an
  identical un-fixable image.
- **Verdict**: this is the single MOST reliable AI-adjacent subsystem in the codebase, by a wide margin
  — genuine durable job queue, genuine crash recovery, genuine tested retry/backoff/dead-letter, unlike
  the in-memory-only gaps Project Sentinel found elsewhere (`ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN`,
  still open as `SENT-001`).

### Migration difficulty: **Medium — genuinely different shape than the other two**

- Confirmed via grep: zero `case_context`/`log_action` references in any of the 3 files — matches the
  presumption.
- Unlike `ask_agent`/Drafting, this system's AI call (document classification/extraction) happens
  **inside a background worker loop**, not inside an HTTP request — there is no natural
  `ai_provenance.set_request_context()`-established correlation_id to inherit (no HTTP request exists at
  the time a worker claims and processes a job). A meaningful migration here would need the job's OWN
  `id` (already a stable, durable identifier) to serve as (or generate) the correlation_id at enqueue
  time, then have `IntakeWorker._process()` explicitly call
  `case_context(correlation_id=job_id_or_derived, predmet_id=..., document_id=..., module_name=
  "smart_intake", ...)` around its classification/extraction GPT calls, and add a `log_action` (or
  `log_action_sync`, since worker code may not always run inside a task with a live loop — same
  precaution as this mission's own `evidence.py` fix) call on job completion.
- This is more work than the other two (touches the worker's processing loop, needs a deliberate
  decision about whether `job_id` becomes the correlation_id or a new one is minted and stored on the
  job row), but still uses 100% existing mechanisms — no new infrastructure required, just a different
  wiring point than the HTTP-request-scoped pattern used everywhere else so far.

---

## Summary for the coordinator

| Item | Reliability (independent of audit status) | Migration difficulty |
|---|---|---|
| `main.py::ask_agent` | Excellent — full retry, full guard coverage, zero partial-write risk | Low-Medium (single flat function, one wrap point) — **easier than Mission Migration assumed** |
| Drafting (`generate_draft` + `ask_analiza`) | Excellent — same pattern, zero partial-write risk | Low (1-2 call sites, `predmet_id` already available for `nacrt`) — **easier than assumed** |
| Smart Intake | Best of the 3 — genuine durable queue, tested reaper, atomic RPC transactions | Medium — background-worker context, needs a job-id-based correlation scheme, not the HTTP-request pattern used elsewhere |

None of the 3 items have a reliability gap Project Phoenix needs to fix. All 3 are safe to migrate onto
the canonical audit stack using patterns already proven this engagement (Court Predictor's
`case_context()`+`log_action` for the first two; a job-id-based correlation variant, still using the
same `case_context()`/`log_action_sync` primitives, for Smart Intake).

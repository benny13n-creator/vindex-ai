# Lambda 004 Failure Map — Program Lambda, Certification 004

**Agent**: Reliability Architect. Complete INPUT→PROCESS→DATABASE WRITE→EVENT EMISSION→AI CALL→CONSEQUENCE→USER
OUTPUT map across every named system, with critical/important/non-critical classification, built BEFORE any
code change and used by Agents 2-6 to scope their own failure-injection work.

## Smart Intake / Document Processing — CRITICAL PATH

`routers/smart_intake.py::upload_intake_documents` → encrypt (AES) → Storage upload (**CRITICAL**, external
dep: Supabase Storage) → `intake_queue.enqueue_job` (atomic RPC, one transaction: job + audit + outbox) →
compensating storage delete on enqueue failure (orphan-blob prevention, already proven). Idempotency:
`content_sha256`+`idempotency_key` UNIQUE index, pre-checked before storage write.

Worker: `shared/intake_worker.py::IntakeWorker._tick` → `claim_next_job` (atomic RPC) → `_process`
(**CRITICAL**, external dep: OpenAI for OCR/classify/extract) → `mark_job_completed`/`_awaiting_review`/
`_failed` (exponential backoff, dead-letter at max_attempts). Crash recovery: `reap_stale_jobs` (>300s stuck)
+ `_process`'s own partial-document cleanup-and-reprocess.

## Case Creation — CRITICAL PATH

`smart_intake.py::_finalize_intake_job_core` (hardened: atomic `claim_intake_finalize` RPC, crash-recovery via
`source_intake_job_id`, honest partial-failure reporting) vs. `routers/intake.py::intake_kreiraj` and
`api.py::kreiraj_predmet` (both found UNSAFE for double-submission — see `LAMBDA004_FIX_REPORT.md`, now
FIXED). `PREDMET_KREIRAN` durable event → 9-step Case Pipeline (`services/case_pipeline.py`).

## Case Evolution — CRITICAL PATH

`services/case_evolution.py::handle_case_changed` (**CRITICAL**) — refuses to run without a durable
`event_id`. Per-(event, consequence) dedup via `case_evolution_consequences`. Found: a genuine TOCTOU race
(`LAMBDA003-EVT-001`, re-confirmed with broader real-world blast radius — 5 of 9 executors would produce a
visible duplicate — now FIXED, see `LAMBDA004_EVENT_SURVIVAL_REPORT.md`).

## Case Actions — CRITICAL PATH

Reconciliation-based (`_compute_target_actions`/`_consequence_refresh_case_actions`), DB-constraint-backed
dedup (partial UNIQUE index, migration 099) — the more mature pattern the event-consequence fix now extends
platform-wide via the atomic claim.

## Workspace — CRITICAL PATH

`routers/workspace.py::get_workspace` (**CRITICAL** — the daily operational board). Found: primary
`asyncio.gather` had no `return_exceptions=True`, unlike this same file's own sibling gather — one hiccup
crashed the whole board. Now FIXED.

## Notifications — IMPORTANT PATH, MIXED reliability

Two independent, overlapping systems with DIFFERENT guarantees (found during Chaos Engineer/Certification
Auditor cross-check): `shared/proactive_alerts.py::create_proactive_alert` (event-bus-driven, hardened —
retries, durable failure-audit on exhaustion) vs. `routers/notifications.py::_generate_notifications`
(polling-driven, unprotected — bare try/except, failure indistinguishable from "nothing to notify"). Named as
an architectural observation, not a confirmed bug requiring a fix this sprint (see `LAMBDA004_HANDOVER.md`).

## AI Governance Layer / GPT Integrations — CRITICAL PATH for Genome, IMPORTANT elsewhere

The deterministic-cap pattern (Court Predictor, Hearing CC, Digital Twin, CIO) verified fresh, holds:
GPT call → JSON parse → deterministic cap against canonical readiness → credit consumption only after success
→ any exception caught by an outer handler, honest error, never a fake success. `shared/llm_retry.py` retries
only transient errors, `reraise=True`, never silently swallows.

Found: `routers/case_dna.py::_do_genome_refresh` (**CRITICAL**) — a GPT failure destroyed live Genome data
instead of leaving it untouched (the sprint's single worst finding, now FIXED). `main.py` Map-Reduce contract
analysis silently presented a failed batch as "found nothing" (now FIXED — `partial_failure`/`failed_batches`
surfaced). Zero explicit timeout across ~63 OpenAI client sites (named as debt, not guessed at — see
`LAMBDA004_HANDOVER.md`).

## Background Workers — CRITICAL PATH

Dominant pattern: RPC-based atomic claims (`SELECT...FOR UPDATE SKIP LOCKED`) for every genuinely
concurrent-sensitive operation (`claim_intake_job`, `claim_intake_finalize`, `claim_pending_events`, and now
`_try_claim_consequence`'s own equivalent for case_evolution_consequences). Each has a documented, narrow
fallback if the RPC isn't deployed live (`KEYSTONE-007`, already tracked, still open — unverifiable from
source whether migrations are applied in production).

## Audit System — CRITICAL PATH (compliance-adjacent)

`shared/audit_immutable.py::log_action` — append-only, hash-chained, tamper-evident by construction. Not
independently re-audited this sprint beyond confirming its reuse pattern (`_is_unique_violation` helper) is
correctly shared across 6+ call sites for constraint-violation handling.

## Memory Systems (Case Genome, Memory Graph) — CRITICAL PATH

Case Genome: see AI Governance above. Self-documented, real, PRE-EXISTING limitation (not new, not this
sprint's own finding): `_run_genome_background`'s in-process coalescing (`_genome_refresh_inflight` sets)
prevents a same-process race but explicitly does NOT coalesce across separate gunicorn worker processes — the
code's own docstring names this, not fixed this sprint (out of scope — a genuinely different, larger
cross-process coordination problem, not confirmed to have caused any real incident).

## External dependency map

OpenAI (Smart Intake, all AI Governance modules, Memory Graph) · Pinecone (RAG retrieval, institutional
memory) · Supabase Postgres (universal) · Supabase Storage (Smart Intake, client_portal) · Redis
(rate-limiting only, per Certification 003's own exhaustive check) · no confirmed 3rd-party push/SMS/email
provider at the in-app notification layer specifically (email digests are a separate, decoupled system,
`routers/email_notif.py`).

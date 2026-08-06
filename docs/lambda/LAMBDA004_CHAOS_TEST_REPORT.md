# Chaos Test Report — Program Lambda, Certification 004

**Agent**: Chaos Engineer. No live deployment exists in this environment, so "failure injection" means:
identify the exact point a failure would occur, then trace precisely what the surrounding code does next by
reading it directly — citing the actual exception-handling/retry/idempotency logic, matching this whole
engagement's own established methodology for race/concurrency claims.

## Scenario 1 — 500 document upload, worker crash during processing

**Verdict: SURVIVES.** `claim_intake_job` RPC is a genuine atomic claim (`SELECT...FOR UPDATE SKIP LOCKED`,
`SECURITY DEFINER`). `reap_stale_jobs` is wired into the worker's own tick loop, not dead code — finds jobs
stuck past a claimed-at threshold and routes them through the same retry/dead-letter path. `_process` has
explicit, multi-layered idempotency: detects a document-created-but-outcome-not-written partial state (a
worker crashed exactly there) and deletes+reprocesses cleanly rather than skipping or duplicating. Case
creation happens at a separate, independently-atomic-claimed step (`claim_intake_finalize`), decoupling
OCR-crash-recovery from case-creation-duplication risk entirely.

## Scenario 5 — Notification delivery, provider unavailable

**Verdict: MIXED** (resolved precisely via cross-check with the Reliability Architect + Certification
Auditor — see `LAMBDA004_HANDOVER.md`). The `proactive_alerts` system (event-bus-driven) genuinely survives:
`create_proactive_alert` retries up to 3 attempts and writes a durable `proactive_alert_insert_failed` audit
entry on exhaustion — a lost alert is never silent. The separate `notifications` system
(`_generate_notifications`, polling-driven) does not have the same protection — a bare try/except with no
retry, no durable failure record, indistinguishable from "nothing to notify." Named as an architectural
observation for follow-up, not fixed this sprint (narrower blast radius, a different system than originally
misidentified — see the handover doc for full reasoning on why this wasn't rushed into this sprint).

## User Behavior Failures

1. **Double-click / duplicate case creation — FAILS, confirmed, now FIXED.** `intake_kreiraj`/`kreiraj_predmet`
   had zero idempotency protection — unlike the file-upload path's own `content_sha256`+`idempotency_key`
   pattern. Fixed via a recent-duplicate check (see `LAMBDA004_FIX_REPORT.md`, Fix E).
2. **Refresh mid-operation — SURVIVES.** Upload/processing is entirely server-side (queue + worker), not
   dependent on a persistent client connection.
3. **Duplicate document upload — SURVIVES, confirmed wired end-to-end.** `content_sha256` dedup operates at
   both enqueue time (idempotency key) and finalize time (independent re-check against same-case and
   other-case content).
4. **Stale data / concurrent edits — FAILS, confirmed, now FIXED.** `api.py::update_predmet` had no
   version/`updated_at` precondition — a stale write from one tab silently clobbered a newer one. Fixed via
   an opt-in `if_updated_at` optimistic-concurrency token (Fix G).

## Phase 4 — Audit and security intersection under failure

- **(a) cross-tenant exposure**: not found — ownership filters remain present in every write path checked.
- **(b) duplicate billing**: not directly confirmed in this sprint's own scope; flagged as a related,
  unconfirmed risk if case creation's own double-click gap (now fixed) ever cascaded into a billing setup
  step — closing the case-creation gap also closes this theoretical extension of it.
- **(c) approval-skip**: not found — the `awaiting_review` status-gating mechanism was already built
  specifically to close a review-skip bug in a prior sprint, re-confirmed still correct.
- **(d) false appearance of completion**: not found in this sprint's own traced areas — the opposite pattern
  is explicitly, deliberately engineered against (Intake Sprint 001's own "false success" bug class, already
  fixed in a prior sprint, re-confirmed not regressed).
- **(e) silent failure**: the double-click case-duplication gap WAS a form of this (a user action succeeding
  twice, silently, with no error at either request) — now closed by Fix E.

## Summary verdict table

| Scenario | Verdict | Status |
|---|---|---|
| 500-doc upload, worker crash | SURVIVES | CERTIFIED |
| Notification delivery, provider unavailable | MIXED | `proactive_alerts` CERTIFIED; `notifications` polling path named as follow-up (see handover) |
| Double-click case creation | FAILED → FIXED | FIXED |
| Browser refresh mid-operation | SURVIVES | CERTIFIED |
| Duplicate document upload | SURVIVES | CERTIFIED |
| Stale concurrent edit | FAILED → FIXED | FIXED |
| Cross-tenant exposure via failure | Not found | CERTIFIED |
| Approval-skip via failure | Not found | CERTIFIED |
| False completion via failure | Not found | CERTIFIED |
| Silent failure via failure | Found (double-click) | FIXED |

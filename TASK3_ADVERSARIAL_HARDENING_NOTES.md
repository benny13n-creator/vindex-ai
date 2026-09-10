# TASK 3 — Adversarial hardening notes (partial pass)

Continues directly from Task 0/Task 2. Two concrete adversarial tests run live against the isolated test account/local server; the remainder of Task 3's full scope (full 12-scenario matrix belongs to Task 7) was **not** attempted in this pass — scoped honestly below.

## Test 1 — Retry/redelivery idempotency: PROVEN SAFE

Forced a redelivery of an already-dispatched `NewEvidenceRegistered` event (predmet `b61b4da3-...`, event `e0bf8eea-aae5-44a2-b73d-eb823d378b13`) by resetting `events.dispatched_at` to `NULL` directly in the DB — simulating exactly the "redelivered/retried event for the same X" scenario the code comments in `case_evolution.py` (`_consequence_evidence_classify` L604-612, `_consequence_refresh_case_actions` L1076-1096) explicitly name as a known risk class.

- Before: 2 open `case_actions` rows (ids `b7002f8c-...`, `80b2b234-...`), 1 `predmet_dokazi` row.
- Dispatch loop correctly picked up the reset row within ~10s and re-set `dispatched_at`.
- After: **exactly the same 2 `case_actions` rows by id** (not new rows — genuine idempotency, not accidental stability) and still exactly 1 `predmet_dokazi` row.

This is live confirmation that the dedupe mechanisms described in code (partial UNIQUE index on `(predmet_id, dedupe_key) WHERE status='open'` for `case_actions`, `klasifikovan_at` marker for evidence classification) actually hold under a real redelivery, not just in comments.

## Test 2 — Cross-tenant isolation: PROVEN FAIL-CLOSED

Created a second isolated test account (tenant B, `61a59d44-7c5c-4687-92b2-b7961d452d71`) and, authenticated as tenant B, attempted to touch tenant A's predmet (`b61b4da3-...`):

- `GET /api/case-actions/predmeti/{tenant_A_predmet_id}` → `404 {"detail":"Predmet nije pronađen"}`
- `POST /api/evidence/predmeti/{tenant_A_predmet_id}/dokaz` → `404 {"detail":"Not Found"}`

Both fail closed (404, not a data leak, not a silent 200). Consistent with the ownership-predicate pattern already documented in `routers/evidence.py::add_dokaz` (L354-358) and the case-actions route.

## Explicitly NOT tested in this pass (honest scope disclosure)

- Concurrency (two simultaneous writers racing on the same predmet) — the code comments (`_consequence_refresh_case_actions` L1076-1096) already document this as narrowed-but-not-fully-eliminated debt for the UPDATE/CLOSE paths specifically; not independently re-verified here.
- Rollback / partial-failure mid-chain (e.g. `evidence_classification` succeeds but `refresh_case_actions` throws) — not induced in this pass.
- `dispatch_attempts` exhaustion (`MAX_DISPATCH_ATTEMPTS=5`) — not exercised; would require forcing the handler to fail repeatedly.
- The full 12-scenario adversarial matrix belongs to Task 7 and was not attempted here.

## Local state

Committed locally on `case-evolution-spine`. **No push, no deploy.** Test data (tenant A predmet/user from Task 0/2, tenant B user `61a59d44-...`) left in Supabase for inspection.

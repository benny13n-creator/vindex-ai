# TASK 2 — Wire manual evidence (`add_dokaz`) into the case event contract

Branch: `case-evolution-spine`. Builds directly on `TASK0_CASE_EVOLUTION_SPINE_FORENSIC_CONTRACT.md`'s confirmed gap (section C): manual evidence entry wrote to `predmet_dokazi` but never told the Canonical Consequence Engine, live-proven as a **missing producer** (zero rows in the `events` outbox for the call), not a broken dispatcher.

## Change

`routers/evidence.py::add_dokaz` — after the existing `upisi_dokaz()` call succeeds, added one `emit_durable(EventType.NEW_EVIDENCE_REGISTERED, ...)` call, wrapped in the same non-fatal try/except pattern already proven live at `api.py:6010-6020` for the auto-analyze upload path. No new event type, no new consequence, no new infrastructure — reuses the existing, already-registered `NEW_EVIDENCE_REGISTERED` consequence chain (`evidence_classification` + `refresh_case_actions`, `services/case_evolution.py:1397-1406`).

Payload carries `dokument_id` (pass-through, `None` when the manual entry isn't linked to a document — `_consequence_evidence_classify`'s own `dokument_id` gate already treats that as a harmless no-op, since there's nothing to classify), `dokaz_id` (the row `upisi_dokaz` just wrote, for traceability), and `trigger: "manual_add_dokaz"` (distinguishes this producer from `pipeline_a_upload` in event payloads/logs).

A bus failure here cannot turn a successful evidence write into a failed HTTP response — same fail-soft discipline as every other `emit_durable` call site (log a warning, still return `200 {"ok": true, ...}` to the caller).

## Live verification (before/after, same mechanism as Task 0)

Local server restarted with the fix (`[EVENT_BUS] dispatch loop pokrenut`, `[INTAKE_WORKER] ... pokrenut` confirmed in startup log). Fresh predmet `b61b4da3-cd08-470a-a646-10e82776c1f6`, same isolated Professional-tier test account used throughout Task 0.

1. Baseline `case_actions`: `broj_akcija: 0`.
2. `POST /api/evidence/predmeti/{id}/dokaz` (`tvrdnja`: "Tuženi AD Vodovod nije odgovorio na tužbu u zakonskom roku od 15 dana.", `snaga: "jaka"`) → `200 {"ok":true,"id":"6818d984-...",...}`.
3. **5 seconds later**, `case_actions`: `broj_akcija: 2` (previously required 30s+ with zero result). One action: `tip: "PRIBAVITI_DOKAZ"`, `status: "open"`, `confidence: 1.0`, `correlation_id: "9b55c617-c541-4505-9d6a-2227f297c69f"`.
4. Direct `events` outbox query for the same predmet confirms the causal chain:

   | event_type | created_at | dispatched_at | correlation_id |
   |---|---|---|---|
   | `predmet_kreiran` | 22:29:26.87 | 22:29:33.06 | `ebadd69a...` |
   | `NewEvidenceRegistered` | 22:29:28.24 | 22:29:31.89 | `9b55c617-c541-4505-9d6a-2227f297c69f` |

   The `NewEvidenceRegistered` event's `correlation_id` is the **exact same value** as the resulting `case_actions` row's `correlation_id`. This is not coincidental timing — it is the same correlation chain proven for the document-upload path in Task 0, now proven for the manual path too.

## What was NOT re-tested in this pass (honest scope disclosure)

- Adversarial cases the mandate's own Task 2 asks for (retry/redelivery, concurrency, rollback, cross-tenant) were **not** run in this pass — the underlying `emit_durable`/`dispatch_pending_events` idempotency and concurrency guarantees are the same ones already proven for the upload path (atomic `claim_pending_events` RPC with `SKIP LOCKED`, `MAX_DISPATCH_ATTEMPTS=5`, optional `event_id`+`ignore_duplicates` for producer-side idempotency), and this change is a pure reuse of that existing contract with no new logic — but "the contract is proven elsewhere" is not the same as "this specific call site was adversarially tested." Recommend a dedicated pass before treating Task 2 as fully closed per the mandate's own bar.
- The `dokument_id`-present case (manual `add_dokaz` call that DOES reference an uploaded document) was not live-tested in this pass — only the more common no-document case was. Worth one more live run before full closure.

## Local state

Committed locally on `case-evolution-spine`. **No push, no deploy.** Test predmet `b61b4da3-...` and the Task 0 test predmeti/user left in Supabase for inspection (same isolated test account, `731be489-e41b-49f3-93fd-42d547c5f982`, Professional tier).

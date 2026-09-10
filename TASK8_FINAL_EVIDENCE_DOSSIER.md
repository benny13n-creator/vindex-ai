# TASK 8 — CASE EVOLUTION SPINE: FINAL EVIDENCE DOSSIER

Branch: `case-evolution-spine`. Base: `3cd603eb` (= `origin/main` at sprint start). HEAD: `7960813f`. **8 local commits, 0 pushed, 0 deployed.** Two production code files touched (`api.py`, `routers/evidence.py`), 44 lines added, 0 removed. Every claim below is either PROVEN (live runtime/DB evidence cited) or explicitly marked otherwise.

Full per-task detail lives in the sibling reports in this same directory: `TASK0_CASE_EVOLUTION_SPINE_FORENSIC_CONTRACT.md`, `TASK2_EVIDENCE_EVENT_WIRING_REPORT.md`, `TASK3_ADVERSARIAL_HARDENING_NOTES.md`, `TASK4_RESULT_CONTRACT_ASSESSMENT.md`, `TASK5_AI_CONTEXT_FRESHNESS_REPORT.md`, `TASK6_DEADLINES_STOP_REPORT.md`, `TASK7_ADVERSARIAL_VERIFICATION_REPORT.md`. This document is the roll-up, not a replacement.

---

## Executive summary

The Bojan+Miroslav canon's core claim — Vindex should provide continuous case understanding (event → state-change → consequence → next-action) — was previously audited as substantially broken (document ingestion allegedly never triggered the Consequence Engine). **That specific claim was wrong**, and this sprint's first job was proving it wrong with runtime evidence, not just re-asserting the opposite. Once corrected, the real gap turned out to be narrower but still load-bearing: a lawyer's own manually-entered facts, and the AI's ability to actually use any newly-added fact, were the two places the spine was genuinely broken. Both are now fixed and live-proven. Deadlines are honestly reported as not safely closeable tonight, with the specific reason why.

## What was PROVEN (runtime/DB evidence, not code-reading alone)

1. **The event bus is real, running infrastructure**, not dead code — confirmed via live startup logs (`[EVENT_BUS] dispatch loop pokrenut`) and successful live dispatches throughout the night.
2. **Document upload → event → evolution → case action already worked end-to-end before this sprint touched any code.** Live proof: a real PDF upload produced a `case_actions` row within ~13s, with a `correlation_id` that exactly matches the emitting event row in the outbox (`api.py:6012`/`6024`, `NewEvidenceRegistered`/`DocumentAccepted` → `GenomeUpdated` → `case_actions` insert). **This corrects the prior audit's "0 hits" finding** — its grep window missed code ~340 lines into a large function.
3. **Manual evidence entry (`add_dokaz`) did NOT reach the Consequence Engine before this sprint.** Live proof: a successful evidence write produced zero events and zero `case_actions` after 30s of observation, and a direct query of the `events` outbox table showed **zero rows** for the call — proving it was a missing producer, not a slow/broken dispatcher.
4. **Fix (Task 2)**: one `emit_durable(EventType.NEW_EVIDENCE_REGISTERED, ...)` call added to `routers/evidence.py::add_dokaz`, mirroring the already-proven upload-path shape exactly. Live proof after the fix: `case_actions` went 0 → 2 within 5 seconds of a manual fact entry, correlation-ID-matched to the resulting event.
5. **The AI (`/api/pitanje`) could not see manually-entered facts, at any freshness — a structural absence, not a timing gap.** Root cause: the endpoint never queried `predmet_dokazi` at all (only notes + chat history); the separate, richer context builder used elsewhere also never selects the fact-text column. Live proof: a distinctive fact (contractual penalty `73492.17` RSD) remained invisible to the AI even 90+ seconds after being added.
6. **Fix (Task 5)**: `predmet_dokazi.tvrdnja` wired into `/api/pitanje`'s existing beleske/istorija context pipeline, reusing the same quarantine (`_ctx_bezbedan`) and non-instructional packaging (`zapakuj_nepoverljivo`) already used and adversarially proven for those channels. Live proof: same predmet, same question, only the code changed — the AI went from "not defined in the provided sources" to the exact correct figure.
7. **Retry/redelivery is genuinely idempotent.** Forced a real event redelivery (reset `dispatched_at` to `NULL`); the result was byte-identical `case_actions` rows (same ids), not duplicates.
8. **Cross-tenant access fails closed.** A second isolated tenant reading/writing another tenant's predmet via case-actions and evidence endpoints got `404` both times, not a leak.
9. **The new Task 5 code path is itself injection-resistant.** A classic instruction-override attack planted inside a manually-entered fact was written successfully (correct — storage is content-neutral) but never reached the model: server logs show `[CTX_KARANTIN] ... izolovano: ['dokaz#0']`, the existing quarantine catching it in the specific new channel.
10. **5-way concurrent evidence writes lost no data and produced no event collisions** (5/5 rows written, 5 distinct correlation_ids, 0 dispatch errors) — though this specific input shape happened to produce 0 case_actions, so it does not independently confirm dedupe-under-concurrency (item 7 already did, for a shape that does produce actions).
11. **`case_actions` has exactly one writer in the entire codebase** (`case_evolution.py:1175`) — reconfirmed, unchanged from prior audits.
12. **No `rokovi`/`deadlines` table exists** in the live schema (checked live, `PGRST205` for all three candidate names). **`EMAIL_SMTP_HOST` is not configured** in this session's `.env` (checked live) — directly reconfirms the standing BLK-3 finding that no reminder-delivery channel exists today.

## What was FIXED (2 code changes, both live-verified before/after)

| File | Change | Proof |
|---|---|---|
| `routers/evidence.py::add_dokaz` | +1 `emit_durable(NEW_EVIDENCE_REGISTERED, ...)` call, non-fatal try/except | `case_actions` 0→2 in 5s, correlation-ID-matched |
| `api.py::pitanje()` | +1 query (`predmet_dokazi.tvrdnja`) piped through the existing quarantine/packaging pipeline | AI answer changed from "not defined" to the exact fact, same predmet/question, code-only diff |

Both changes reuse existing, already-hardened mechanisms (the proven event contract; the proven T2/T3 trust-boundary packaging) rather than inventing new infrastructure — consistent with the mandate's own instruction to prefer reuse over new construction where the existing contract is adequate.

## What was investigated and NOT changed, with reasons

- **Task 4 (result contract)**: already adequate at the event/action/deadline/dedupe/confidence/correlation_id level. One disclosed gap — fact-level provenance (`izvor_dokumenti`) populated for only 1 of 5 action types — documented, not blindly redesigned, because it may be inherent to those rules' own case-level (not per-fact) risk math and deserves its own dedicated read of `risk_engine.py` before touching.
- **Task 6 (deadlines)**: **legitimate STOP**, per the mandate's own explicit allowance. Extraction logic exists and is already hardened (BLK-1 fixed a real fabricated-deadline incident). The gap is a founder-level product/risk decision (should an unconfirmed high-confidence extraction auto-create a reminder-worthy obligation?) plus missing infrastructure (SMTP not configured) — not a coding gap closeable by more code alone. Building it blind risks the exact "looks done, silently never alerts anyone" failure class this project's own history has repeatedly flagged as the worst bug shape.

## What was NOT attempted (honest scope, not silently dropped)

- Full 12-scenario Task 7 adversarial matrix — 4 scenarios run (redelivery idempotency, cross-tenant isolation, injection resistance on new code, 5-way concurrent write safety); mid-chain rollback, `dispatch_attempts` exhaustion, true two-writer race on an action-producing shape, and `dokument_id`-linked manual entry are explicit follow-up.
- Live A/B test of `/api/pitanje` freshness for the *document-upload* path specifically (only the manual-entry path was A/B tested; the upload path's event-to-case_actions latency was proven, but not a full freshness A/B on AI answers post-upload).
- `services/case_pipeline.py`/`routers/case_pipeline.py` were not read for a possible duplicate/competing mechanism (Task 0 §H, flagged, not resolved).
- Any change to deadline architecture, per Task 6's own legitimate stop.

## Local repository state

```
7960813f docs(task7): consolidated adversarial verification -- injection + concurrency
4024b7a0 docs(task6): deadlines/rokovi -- legitimate STOP, evidenced
a3c582ec fix(pitanje): wire predmet_dokazi facts into AI context (Task 5)
75a9c90f docs(task3): live adversarial checks -- redelivery idempotency + cross-tenant isolation
fc502055 fix(evidence): wire manual add_dokaz into the case event contract
572eaed6 docs(task0): add full correlation-ID-linked event chain proof
14a75c42 docs(task0): Case Evolution Spine forensic contract, live-verified
3cd603eb ui(v1): swap typography to Source Serif 4 / Source Sans 3   <- origin/main, sprint start
```

**0 pushes. 0 deploys.** All testing done against a local server (port 8994) and an isolated, service-role-created test account (`731be489-e41b-49f3-93fd-42d547c5f982`, tenant B `61a59d44-...`) — the founder's real account and data were never touched. Test artifacts (several predmeti, 2 test users) left in Supabase for inspection; `auth.admin.delete_user` cleanup was rate-limited (informational, not a defect) so they were not deleted.

## Recommendation

**GO for review and push, with Task 6 explicitly deferred.** The two code changes are small (44 lines total), each reuses an already-proven mechanism rather than inventing one, and each is proven with a real before/after live test — not asserted, demonstrated. Recommend: founder reviews the diff (`git diff 3cd603eb..HEAD -- api.py routers/evidence.py`) and this dossier, then decides on push/deploy personally, per this sprint's standing rule that only the founder controls that step.

Suggested immediate next real-world action once deployed: re-run the Task 2/Task 5 live A/B tests (or equivalent) against production once, the same way tonight's local tests were run, before relying on the fix in front of a real user — this dossier's proof is real but is local-server proof, and production configuration (connection pooling, multiple gunicorn workers per the `dispatch_pending_events` docstring's own note) was not independently re-verified.

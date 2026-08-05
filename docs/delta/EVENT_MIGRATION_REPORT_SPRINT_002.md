# Event Migration Report — Program Delta, Sprint 002 (2026-08-05)

"Canonical Event Migration I — Human Decisions Become System Decisions". Migrates 4 existing scattered
"decide what happens next" call sites onto the ONE canonical mechanism Sprint 001 built
(`services/case_evolution.py::handle_case_changed`), without building any new system, AI capability, or
Genome/Timeline/Alert functionality.

## What "migrate, don't extend" meant concretely, per event

### REVIEW_ACCEPTED

**Before**: `routers/smart_intake.py::resolve_job_review` did two things directly — (1) called
`intake_documents.resolve_review()` (advances `intake_jobs.status`), (2) fired an in-process,
fire-and-forget `asyncio.create_task(log_action("dokument_review_resolved", ...))`. No Genome/Timeline
involvement at all, ever — the founder's own worked example ("Review Accepted → Genome → Timeline → Audit")
described an INTENDED shape, not the codebase's literal prior behavior.

**After**: (1) unchanged (still the direct, synchronous call — this IS the state-changing work that must
happen durably before the event is emitted, same discipline as `DOCUMENT_ACCEPTED`'s own emission). (2)
replaced with a durable `REVIEW_ACCEPTED` emission. The Canonical Consequence Engine now decides: for a
pre-finalize acceptance (common case, no `predmet_id` yet), `genome_refresh`/`timeline_entry` gracefully
no-op (REUSING `DOCUMENT_ACCEPTED`'s own executors, unchanged); for a post-finalize correction, both do REAL
work — this is where the founder's own worked example becomes literally true, for the one case where it
actually matters.

**A real bug fixed as part of this migration** (belongs to REVIEW_ACCEPTED's own Human Review domain, fixable
without a business decision, per this sprint's own mandate): the endpoint used to return early — without even
calling `resolve_review()` — whenever a job was already finalized ("nema više nijedan status da otključa").
This meant the `intake_review_queue` row for a POST-finalize correction never got marked resolved, staying
"unresolved" forever, a silent UI-facing gap (a review dashboard would show it as pending indefinitely).
Fixed: `resolve_review()` now always runs (already idempotent by construction — `.is_("resolved_at","null")`
+ `.eq("status","awaiting_review")` — a second call is a safe no-op), and the response still reports
`already_finalized` for backward compatibility.

### REVIEW_REJECTED

**Before**: did not exist. Program Intake Sprint 004's own `INTAKE-012` explicitly named this as a founder
decision, left open.

**After**: this sprint's own mandate ("Ako nešto nije definisano, napraviti jednu definiciju") required
defining it, not leaving it open indefinitely. Definition kept deliberately narrow and low-risk (see
`CASE_EVOLUTION_REGISTRY.md`'s own "šta se poništava/ostaje/replanira" fields for the full reasoning): a new
`POST /jobs/{job_id}/review/reject` endpoint, a new `shared/intake_documents.py::reject_review()` function
(reusing the SAME `resolve_review_queue_for_job` helper `resolve_review()` already uses — Rule Zero, not a
parallel implementation), and one new terminal `intake_jobs.status` value (`'rejected'`, migration 097 —
additive CHECK-constraint widening, the SQL migration the founder runs himself, per standing project
convention). No new AI/OCR/re-classification capability was built — a rejection intentionally leaves the
document requiring an explicit human follow-up (`correct_entity` or re-upload), never an automatic retry.

### NEW_CLIENT_LINKED

**Before**: `routers/smart_intake.py::finalize_intake_job` fired a direct, in-process
`asyncio.create_task(_conflict_check_bg())` after attempting to link a client — a failure inside that
background task was logged and permanently silently dropped, no retry, ever.

**After**: a durable `NEW_CLIENT_LINKED` emission, exact same trigger condition as the code it replaces.
`services/case_evolution.py::_consequence_conflict_check` reuses `routers/intake.py::_run_conflict_check` and
`shared/proactive_alerts.py::create_proactive_alert` UNCHANGED — same conflict-detection logic, same alert
shape. The one behavioral difference is a genuine RELIABILITY IMPROVEMENT, not new capability: a failure now
propagates to the Event Bus's own proven retry/dead-letter mechanism (`MAX_DISPATCH_ATTEMPTS=5`) instead of
vanishing silently after the first attempt.

### NEW_EVIDENCE_REGISTERED

**Before**: `routers/smart_intake.py::finalize_intake_job` fired a direct, in-process
`asyncio.create_task(asyncio.to_thread(klasifikuj_i_sacuvaj, ...))` per accepted document (when
classification wasn't already flagged uncertain) — same silent-failure-drop risk as the conflict-check.

**After**: a durable `NEW_EVIDENCE_REGISTERED` emission, per document (matching the granularity of the call
it replaces — NOT once-per-finalize-call like `DOCUMENT_ACCEPTED`, since evidence classification is
inherently per-document). `services/case_evolution.py::_consequence_evidence_classify` reuses
`routers/evidence.py::klasifikuj_i_sacuvaj` UNCHANGED. Deliberately does not carry the extracted text in the
event payload (avoids duplicating a potentially ~100KB blob into the durable outbox per document) — instead
re-reads `tekst_sadrzaj` from the SAME `predmet_dokumenti` row the event's own `dokument_id` already points
to. Verifies via `klasifikovan_at` (before/after), never trusting "no exception" alone — the same discipline
`genome_refresh` already established in Sprint 001, since `klasifikuj_i_sacuvaj`'s own outer try/except does
not always re-raise internal failures.

## The canonical durable-emission helper (new this sprint, factored refactor)

Sprint 001 introduced ONE emission idiom (`INSERT INTO events`, tolerant of the `correlation_id` column not
yet existing) at exactly one call site. This sprint needed the SAME idiom at 4 more call sites — rather than
copying the same try/except/fallback boilerplate 4 more times, it was factored into
`services/event_bus.py::emit_durable()`, and `DOCUMENT_ACCEPTED`'s own Sprint-001 emission site was refactored
to use it too. Now exactly ONE function in the whole codebase knows how to durably emit an event — the "no
hidden orchestrators" principle applied to the emission mechanism itself, not just to the consequences.

## What did NOT change

Genome (`_run_genome_background`), the Timeline table shape, Evidence Vault's own classification logic
(`_klasifikuj_dokument`), the conflict-check's own matching logic (`_run_conflict_check`), and the Event Bus's
durable outbox/atomic-claim/retry/dead-letter machinery are all reused UNCHANGED. Zero new AI functions, zero
new Genome/Timeline/Alert capabilities — every migrated consequence executor is a thin wrapper around a
function that already existed before this sprint.

## Regression discipline

3 existing test files needed updates because they asserted on the OLD direct-call behavior being replaced
(`tests/test_sprint004_review_resolve.py`, `tests/test_ztc_conflict_check_autowiring.py`) — updated to assert
on the new durable emission instead, following the exact pattern Sprint 001 itself established. One new test
file (`tests/test_delta_sprint002_event_migration.py`, 15 tests) covers all 6 required scenarios plus each new
executor's own edge cases (missing predmet_id, missing klijent_ime, missing tekst_sadrzaj, verification-not-
self-report). Full suite confirmed zero regressions (see Reliability Verification Report / Mission Report for
the exact count).

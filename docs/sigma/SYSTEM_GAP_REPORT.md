# System Gap Report — Program Sigma, Master Sprint 001 (2026-08-06)

Phase 9 deliverable: assume the system is not ready; hunt for chain breaks, manual steps, hidden AI
decisions, duplicate algorithms/DBs/events, lost documents/deadlines/tasks/clients/links. Every finding
below is either FIXED this sprint (with tests) or NAMED as a debt item with reasoning for why it wasn't
safe to fix blind.

## Fixed this sprint

1. **`PREDMET_KREIRAN` never emitted from Smart Intake** — the mission's own primary scenario (500 chaotic
   documents → auto-created case) never received mini-strategy, HCC briefing, risk snapshot, Copilot's
   opening recommendation, or a "case created" history entry. Fixed: `routers/smart_intake.py` now emits
   it exactly once per genuinely-new case, via the same durable-outbox pattern already proven for
   `DOCUMENT_ACCEPTED`. See `END_TO_END_PIPELINE.md`.
2. **Step 1 of the Case Pipeline (`analiza_dokumenata`) false-FAILED for every Smart-Intake case** — it only
   recognized a legacy istorija marker Smart Intake's own Genome-based analysis never writes. Fixed to also
   accept a populated `case_dna` as evidence of analysis.
3. **A real near-duplicate-deadline risk avoided, not introduced**: the new `PREDMET_KREIRAN` wiring
   deliberately SKIPS `_step_ekstrakcija_rokova` for Smart-Intake cases (the one Case Pipeline step that
   would have written a second, independently-derived deadline into the un-deduplicated
   `predmet_hronologija` table) — found and designed around BEFORE implementing, not discovered as a bug
   afterward.

12 new tests (`tests/test_case_pipeline.py`), full regression suite re-run clean (see METRICS.md for the
final count).

## Named this sprint, not fixed — with reasoning

| ID | Finding | Why not fixed this sprint |
|---|---|---|
| `SIGMA-001` | Client-linking failure (`resolve_client_ownership`) is silently swallowed — a case can be fully complete by every other measure with ZERO linked client and nothing flags it | Surfacing this needs a product decision on WHERE/HOW to flag it (dashboard warning? Case Ready Score deduction? retry mechanism?) — a UX choice, not a mechanical fix |
| `SIGMA-002` | Genome's contradiction diff (`_compute_delta`) matches by `opis[:60]` string-prefix, not stable identity — a rephrased-but-identical contradiction between 2 refresh calls can register as a false eliminate+create churn | A live GPT-facing extraction-contract change, out of a certification sprint's own safe scope |
| `SIGMA-003` | A document that fails decrypt/extract during finalize produces a silent per-document flag in the finalize HTTP response only — never surfaced in `GET /api/matter-intel`'s own "what's missing" view a lawyer actually opens later | Needs a new persisted "processing failures" field/query — a real feature addition, not a wiring fix |
| `OMEGA-023` (Sprint 007, re-confirmed unchanged) | `proactive_alerts`' own check-before-emit is a TOCTOU race, no DB constraint | Unchanged this sprint — same reasoning as Sprint 007's own deferral |
| `OMEGA-026` (Sprint 007, re-confirmed unchanged) | `notification_log`/`email_notif_log` have no DB unique constraint | Unchanged |
| **New this sprint** — client/case-number/document-content dedup TOCTOU races | `shared/case_assimilation.py::resolve_client_ownership`/`resolve_case_ownership` and the document `content_sha256` check are all SELECT-then-INSERT application logic, no DB-enforced uniqueness (`migrations/095_intake_bulletproofing.sql:26-28` creates a NON-unique index) — see below | Recorded as `SIGMA-004` |

### `SIGMA-004` — no DB-enforced uniqueness for client/case-number/document-content matching

Confirmed via `grep` across `migrations/`: zero unique indexes on `klijenti(user_id, ime, prezime)`,
`predmeti(user_id, broj_predmeta)`, or `predmet_dokumenti(user_id, content_sha256)`. Two truly concurrent
finalize calls racing on the SAME new client name, case number, or document content could each pass their
own SELECT check and both insert — the same TOCTOU class this engagement has now found repeatedly
(`proactive_alerts`, `notification_log`/`email_notif_log`, and now this). **Why not fixed this sprint**: a
correct fix for each of these 3 tables needs its own schema review — e.g. a unique index on
`predmet_dokumenti(predmet_id, content_sha256)` would need to confirm `deleted_at`-scoping and interaction
with the existing cross-case "route to review" path first, and `klijenti`/`predmeti` uniqueness needs
scoping decisions (case-insensitive? per-user only, or per-user+per-firm?) that are product decisions, not
mechanical fixes. Bundling 3 non-trivial migrations into the tail of an already-large sprint risked exactly
the kind of rushed, unreliable change the mission's own "pouzdano rešenje" (a RELIABLE solution) standard
explicitly warns against. Real-world exposure is bounded by how the batch-finalize endpoint actually calls
`_finalize_intake_job_core` — sequentially per job within one request, not via genuinely parallel OS
processes — so a 500-document SINGLE batch request is not exposed to this race; TWO SEPARATE, truly
concurrent finalize requests (e.g. 2 browser tabs) are.

## What this sprint could NOT certify (stated honestly)

- **No live, 500-1000-document load test was run against a real Postgres/Supabase instance.** Every
  duplication/idempotency/concurrency claim in this sprint's own deliverables is proven at the code-path
  and mocked-concurrency (`asyncio.gather` against an in-memory fake enforcing the real partial-unique-index
  semantics — the same technique Sprint 007 used and proved sufficient to catch a real race-handling bug)
  level, matching this whole engagement's established testing discipline (no live infrastructure exists in
  this dev environment). `docs/omega/OCR_AND_INTAKE_CAPACITY_REPORT.md` (prior sprint) covers what capacity
  testing WAS feasible.
- **`SIGMA-002`'s own precision gap was not independently reproduced against a real GPT call** — it is a
  reasoned risk from reading the extraction/diff code, not an observed failure with a captured before/after
  transcript.
- **Crash-mid-finalize recovery for the NEW `PREDMET_KREIRAN` emission specifically** was not given its own
  dedicated crash-recovery test — it reuses the exact same durable-outbox/idempotent-consequence machinery
  Sprint 007's own `test_delta_sprint004_certification.py` already proves crash-safe for `DOCUMENT_ACCEPTED`,
  and `on_predmet_kreiran`'s own steps are each independently idempotent-by-marker (`case_pipeline.py`'s own
  design, pre-existing) — but a dedicated end-to-end "crash between predmeti insert and PREDMET_KREIRAN
  emission, replay" test was not written this sprint, a real, named scope boundary.

## Definition of Done — honest self-assessment

The mission's own Definition of Done requires proving the FULL chain works end-to-end with zero data loss,
zero duplication, one source of truth, and automatic downstream propagation. This sprint:

- **Closed** the one genuinely new, previously-undiscovered chain break found (`PREDMET_KREIRAN` never
  firing for the platform's own primary intake path) — code-proven, tested, zero regressions.
- **Re-verified**, not re-built, everything Program Omega's own Sprints 002-007 already proved (Genome/
  Timeline/Tasks/Notifications auto-refresh, dedupe_key + partial-UNIQUE-index idempotency, crash/replay
  safety) — still accurate against current code.
- **Named, honestly, 4 new debt items** (`SIGMA-001` through `004`) found by treating the mission's own
  Phase 9 instruction literally ("pretpostaviti da sistem nije spreman") rather than confirming existing
  architecture — none judged safe to fix blind within this sprint's own time budget without risking a
  rushed, unreliable change.

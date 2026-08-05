# Program Intake — Sprint 001: Bulletproof Document Intake Foundation

**Date**: 2026-08-04
**Charter**: UPLOAD → OCR → VALIDACIJA → STORAGE must become canonical, deterministic, verifiable, and
production-reliable. No new AI capabilities, screens, panels, or agents. Explicitly forbidden to touch:
Decision Engine, Copilot, Strategy Engine, Firm Brain, Briefing, Dashboard, Search, Alerts, Timeline,
Deadlines, Task Engine, Memory Graph — findings there are documented, not fixed.

**Active team**: Chief Systems Architect, Reliability & Failure Recovery Engineer, Evidence & Consistency
Auditor, Security & Trust Auditor, Code Quality/Refactoring Reviewer. All other `.vindex_ai_team` roles on
STANDBY per this mission's own charter — no Mission Olympus governance review phase for this sprint.

## 0. Method

Three parallel read-only forensic forks investigated (1) Upload/OCR/Classification, (2) Async/Retry/Failure
Recovery, (3) Storage/Status/Audit/Provenance, each building on Program Gamma's Fork E (intake classifier
race), Project Phoenix's Event Bus fixes, and Mission Ledger's correlation-ID primitives rather than
re-deriving from scratch. Full fork outputs: `.vindex_ai_team/decisions/2026-08-04_intake_fork_*.md`.

**One factual contradiction between forks was resolved by direct code verification before any implementation
began.** Fork 3 claimed Smart Intake (Pipeline B/C) "has no frontend entry point," citing an `api.py:4049`
in-code comment. That comment is stale — written during "Operation Lawyer Day" (2026-08-03) before "Operation
Beta Closure," the same night, added real frontend wiring. Direct grep of `static/vindex.js` confirmed 8
`smart-intake`/`smart_intake` references including live `fetch()` calls to 5 distinct endpoints, plus an
explicit comment block dated "Operation Beta Closure (2026-08-03)" stating this is "the first UI wired to
it." **Conclusion carried through this entire report: all three upload pipelines (A, B, C) are live,
reachable, real-user-facing today.** Nothing found below is theoretical or dormant.

## 1. The three pipelines (Phase 3 — Duplicate Pipeline Analysis)

| | Pipeline A | Pipeline B (async) | Pipeline C (finalize) |
|---|---|---|---|
| Entry point | `POST /api/predmeti/{id}/upload` (`api.py:4061`) | `POST /api/smart-intake/documents` (`routers/smart_intake.py:92`) | `POST /api/smart-intake/jobs/{id}/finalize` (`smart_intake.py:373`) |
| Model | Synchronous, inline, in-request | Durable job queue (`intake_jobs`, migration 073) + background `IntakeWorker` | Synchronous, second full pass over the same file B's worker already processed once |
| OCR/Pinecone/DB | All inline, one request | `IntakeWorker._process()` — atomic `SELECT...FOR UPDATE SKIP LOCKED` claim, exponential backoff, stale-job reaper, dead-letter | Inline again — decrypt→OCR→chunk→Pinecone→DB, same fragility shape as A |
| Original file storage | **Missing before this sprint** — tempfile deleted, `storage_path` was a non-dereferenceable label | AES-GCM encrypted upload to private `intake-dokumenti` bucket (real, correct) | Reads from the same bucket B wrote to |
| Job durability | None — a crash mid-request loses everything in-flight | Full — survives worker restart, process restart | Depends entirely on B's job having already succeeded; this pass itself has none |

A 4th independent async mechanism sits underneath all three: the Event Bus durable outbox (`events` table).
Migration 091 (atomic dispatch claim) is drafted but **not run** — `KEYSTONE-007`, a founder action item, not
something this sprint implements around. Until it runs, all 4 default gunicorn workers each start an
independent dispatch loop against a plain-SELECT race — a live multi-worker duplicate-dispatch exposure for
any non-idempotent Event Bus handler. Documented, not fixed (infrastructure the sprint doesn't own).

**Why three pipelines exist, not by design flaw but by product-evolution accident**: Pipeline A predates
Smart Intake and still serves the per-case "add a document to an existing case" flow. Pipeline B/C is the
newer, document-first intake flow (case doesn't exist yet at upload time) with materially better engineering
(durable queue, encryption, idempotency-by-design). Full canonicalization (retiring A in favor of B/C) is a
product/UX decision outside this sprint's bounded scope — see §5.

## 2. Six independent writers of `predmet_dokumenti` (not two, as `ALPHA-003` originally framed)

| # | Writer | OCR? | Classifies? | Sets `status` explicitly? (before this sprint) |
|---|---|---|---|---|
| 1 | `api.py:4226` — Pipeline A | Yes | Best-effort bg | Yes |
| 2 | `smart_intake.py:682` — Pipeline C finalize | Yes | Yes (2-stage) | Yes |
| 3 | `routers/intake.py:236` — CRM Wizard reference-link | No (already done upstream) | No | **No → fixed this sprint** |
| 4 | `routers/onboarding.py:274` — demo predmet stub | No (no real file) | No | **No → fixed this sprint** |
| 5 | `routers/drafting.py:310` — approved-draft promotion | N/A (text already known) | No `tip_dokaza` set | `status` yes; **`tip_dokaza` fixed this sprint** |
| 6 | `routers/evidence.py:210` — shared classifier UPDATE | — | The canonical Serbian-vocabulary classifier all others route through (or don't) | — |

Four independent AI document-type classifiers exist in total; only two (`intake_classify.py` English 13-type,
`evidence.py::_klasifikuj_dokument` Serbian 9-type) ever persist to the DB and participate in the classifier
race already documented by Program Gamma's Fork E and re-confirmed unchanged this sprint. The other two
(`api.py::_detect_doc_type`, `routers/dokument.py::_klasifikuj_dokaz`) are ephemeral prompt-routing/Q&A-only
and never write to `predmet_dokumenti` — cost/maintenance duplication, not a correctness bug. Not fixed this
sprint (`ALPHA-003`/`GAMMA-009` shape — a vocabulary/ownership decision, not a bounded bug fix).

## 3. What this sprint fixed (Phase 7 — bounded implementation)

All five below are tested (`tests/test_intake_*.py`, `tests/test_intake_original_file_storage.py`,
`tests/test_intake_dokument_view_audit.py`, `tests/test_intake_status_writers.py`) and the full suite
(2492 tests) passes with zero regressions after each.

1. **Pipeline A now preserves the original uploaded file** (`api.py:4113-4141`). Reuses
   `routers/smart_intake.py::_encrypt`/`_STORAGE_BUCKET` (same AES-GCM pattern as the Klijenti Trezor) rather
   than inventing new encryption. Best-effort/non-blocking by design — a storage failure doesn't abort a
   request that didn't have this protection before, but `storage_path` never lies: it's the real key on
   success, the old non-dereferenceable label on failure. Directly closes "dokument može nestati."

2. **`IntakeWorker._process()`'s silent partial-completion bug fixed** (`shared/intake_worker.py:137-160`,
   `shared/intake_documents.py::has_processing_outcome`/`delete_partial_document`). This was the single most
   severe finding across all 3 forks: a crash between `create_document()` and `write_processing_outcome()`
   caused the old idempotency guard to treat "document row exists" as "job is done," and `_tick()` would mark
   the job `completed` with zero entities, zero review-queue escalation, no exception, no log, no dead-letter
   trace — indistinguishable from a genuine success. Fix: the guard now also checks whether
   `intake_processing_outcomes` has a row (the true last-step completion signal); if not, the partial
   document/entities/review-queue rows are deleted and the job is reprocessed cleanly from scratch. Directly
   closes "upload može prijaviti uspeh iako obrada nije bezbedno završena" — the mission's own named worst
   case, inside the exact subsystem Project Phoenix once called "the single most reliable AI-adjacent
   subsystem" in the whole engagement.

3. **`dokument_view` audit logging wired** (`api.py:4843-4859`). `AUDITABLE_ACTIONS` and the UI label already
   existed; only the `log_action()` call site at `predmet_dokument_preview` was missing. Same fire-and-forget,
   best-effort pattern as the existing `dokument_upload` call.

4. **Explicit `status` set at the two writers that previously fell through to the misleading `na_cekanju`
   DB default forever**: `routers/intake.py`'s wizard reference-link now writes `status="sacuvano"` (reuses
   existing vocabulary — this step only links an already-processed document, it doesn't reprocess it, so
   "sacuvano" is the honest conservative claim); `routers/onboarding.py`'s demo stub now writes
   `status="demo"` (deliberately distinct — no real file exists behind that row, claiming "sacuvano" would be
   a lie).

5. **`tip_dokaza` set deterministically at the drafting-promotion writer** (`routers/drafting.py:310-320`).
   An approved AI draft promoted into the case record previously left `tip_dokaza` permanently NULL — no
   background task touches it at all. Rather than triggering a new classification call (would risk reading as
   "new AI capability," also wasteful — the type is already known with certainty), the insert now sets
   `tip_dokaza="podnesak"` directly, reusing the exact value `routers/evidence.py`'s own classifier vocabulary
   already defines for "tužba, žalba, prigovor, zahtev stranke."

## 4. What this sprint deliberately deferred (with reasoning)

- **Pipeline C's DB-insert-failure exposure** (`smart_intake.py:588-689`): the entire decrypt→OCR→chunk→
  Pinecone→DB block is one broad `try/except`; if all 3 fallback insert variants fail after Pinecone ingest
  already succeeded, `doc_linked=False` is honestly computed and returned, but the finalize response still
  says `"ok": true` because the `predmet` (case) row itself was already created successfully earlier in the
  same call. Unlike Pipeline A (Project Sentinel's hard-fail precedent, `api.py:4243-4247`), hard-failing here
  is not a safe direct port: Pipeline A's endpoint does one thing (attach a document to an existing case), so
  a 500 there is an honest total failure. Pipeline C's endpoint does several things in one call (create case +
  client links + hronologija + document); a 500 here would misreport a case that WAS genuinely created as a
  total failure, risking a confused retry that duplicates the case. The correct fix requires a real design
  decision (partial-success response contract, or splitting case-creation from document-attachment into
  separate calls) that this sprint's bounded-implementation discipline does not license inventing on the spot.
  Tracked as `INTAKE-001`.
- **Orphaned Storage blobs on enqueue failure** (Pipeline B, `smart_intake.py:129-156`): if the encrypted
  upload succeeds but the subsequent `enqueue_intake_job` RPC throws, the blob remains in `intake-dokumenti`
  forever with zero reference anywhere; no cleanup job or bucket lifecycle policy exists. A cleanup job is new
  infrastructure, out of this sprint's "no new capability" bound. Tracked as `INTAKE-002`.
- **`intake_jobs.status`'s richer 9-value enum is discarded at finalize** — Confidence Graph data, OCR
  confidence, classification method, and human corrections captured during Phase 1A become permanently
  unlinked from the case-file document once finalized (zero occurrences of `intake_job_id` in the
  `predmet_dokumenti` insert dict). A genuine product/architecture question (should `predmet_dokumenti` gain a
  lineage FK?), not a bounded bug. Tracked as `INTAKE-003`.
- **4-way classifier taxonomy duplication** (§2) and **document-status 3-way fragmentation** (§ below) —
  same shape as already-tracked `ALPHA-003`/`GAMMA-009`/`GAMMA-010`; sharpened with this sprint's evidence,
  not re-attempted as a fix (a vocabulary/ownership decision, not this sprint's to make unilaterally).
- **`routers/copilot.py:804`'s dead-branch status read** (`status in ("na_cekanju", "greska")` treated as
  "pending"; `"greska"` is never written anywhere, and `"na_cekanju"` isn't a real in-progress signal on
  Pipeline A's synchronous flow, so Copilot misreports finished wizard-linked/demo documents as eternally
  pending) — Copilot is explicitly a forbidden-to-fix module this sprint. Documented only. Tracked as
  `INTAKE-004`.
- **Migration 091 not run** — already tracked as `KEYSTONE-007`, a founder action item.

## 5. Canonicalization verdict (Phase 5)

Full canonicalization (one entry point, one processing path) was **not** performed this sprint. Reasoning:
Pipeline A and Pipeline B/C serve genuinely different, both-live product flows (attach-to-existing-case vs.
document-first-case-creation) — collapsing them is a product decision, not a bounded reliability fix, and
this sprint's charter explicitly bars introducing new screens/flows to accommodate a merge. What *was*
canonicalized within each pipeline's existing shape: original-file storage now uses the same bucket/encryption
scheme on both A and B/C (§3.1), and `status`/`tip_dokaza` now follow the same existing vocabulary everywhere
they're set (§3.4-5) — reducing representational drift without merging the pipelines themselves. Full
topology diagram: `INTAKE_FLOW_DIAGRAM.md`. Source-of-truth analysis: `INTAKE_SOURCE_OF_TRUTH_MATRIX.md`.
Failure-mode analysis: `INTAKE_FAILURE_RECOVERY_MATRIX.md`. Duplicate inventory:
`INTAKE_DUPLICATE_LOGIC_REGISTER.md`. Prioritized risk list: `INTAKE_RISK_REGISTER.md`. Test inventory:
`INTAKE_TEST_COVERAGE_REPORT.md`.

## 6. Mission closure self-check (against the charter's own explicit forbidden conditions)

- A document can disappear → **No** on Pipeline A (fixed §3.1) and Pipeline B/C (already correct). Orphaned
  Storage blobs on enqueue failure (`INTAKE-002`, deferred) are wasted space, not a lost *linked* document —
  no `intake_jobs` row ever referenced them, so nothing that was ever "in the system" from a user's
  perspective is lost.
- A document can be duplicated → No new duplication path found or introduced; `IntakeWorker`'s idempotency
  fix actively prevents an existing under-specified duplication risk (double entity-insertion on crash-retry).
- A document can remain without a status → Fixed for the 2 writers that previously had no explicit value
  (§3.4). Pipeline C's `dokument_povezan: false` on total insert failure is an honest signal, not a missing
  one (`INTAKE-001`, deferred with reasoning, not silently left broken).
- Upload can report success without safe completion → Fixed, the sprint's most severe single finding (§3.2).
- Two sources of truth for the same status → Not eliminated (document-status is genuinely 3-way fragmented
  across `predmet_dokumenti.status`, `tip_dokaza`/`klasifikovan_at`, and `intake_jobs.status`) — but this is
  pre-existing, load-bearing product shape (different tables answer different questions), not a bug this
  sprint introduced or silently ignored; documented in full in `INTAKE_SOURCE_OF_TRUTH_MATRIX.md` and tracked
  as `INTAKE-003`/`INTAKE-004`, not closed.
- More than one canonical pipeline exists → True, and **not** resolved this sprint (§5) — by the charter's
  own literal wording this blocks a "mission complete, fully canonical" declaration. This sprint closes as
  **bounded reliability hardening within the existing 3-pipeline topology**, not as full pipeline
  canonicalization. That distinction is the accurate, non-inflated characterization of what was achieved.

---

## 7. Update — Program Intake Sprint 007 (2026-08-05), "Intake Finalization – Bulletproof Intake"

Sprints 002-006 built segmentation (one upload → N logical documents), classification confidence-gating, and
Ownership Resolution (which case/client a document belongs to). Sprint 007 closes the 3 debts Sprint 006
itself deferred (`INTAKE-018` cross-upload dedup, `INTAKE-019` partial-failure retry, `INTAKE-020` case-number
normalization) — the last remaining gaps standing between "reliable" and the mission's own explicit
definition of **bulletproof**: *the same document can be uploaded any number of times, processing can be
interrupted at any point, the caller can retry any number of times, and the system always ends with exactly
one correct document, one correct case, one lineage chain, one audit/provenance record.*

**Scope discipline this sprint**: only Pipeline C (`finalize_intake_job`) was touched — Pipeline A/A-ephemeral/
B were explicitly out of scope (mirrors Sprint 006's own `INTAKE-015` deferral: segmentation/assimilation
correctness is proven end-to-end for Pipeline C first; extending the same content-identity mechanism to the
other 3 pipelines is a separate, future, bounded piece of work, not attempted here).

**What changed** (full detail: `DUPLICATE_DETECTION_REPORT.md`, `RETRY_RELIABILITY_REPORT.md`,
`CASE_NUMBER_NORMALIZATION_SPECIFICATION.md`, `SPRINT_007_MISSION_REPORT.md`):

1. **One deterministic content identity** (`predmet_dokumenti.content_sha256`, migration 095) answers BOTH
   "was this exact content already assimilated anywhere" (Debt 1) and "did this segment's own insert already
   happen" (Debt 2) — the same lookup, scoped differently by outcome (same-case match = idempotent no-op;
   different-case match = review, never silently linked or silently dropped).
2. **Crash recovery** (`predmet_dokumenti.source_intake_job_id`, migration 095, generalizing Sprint 006's own
   segment-only lineage FK to every document) — a retried finalize call recovers an already-resolved
   `predmet_id` from an already-inserted document instead of running Ownership Resolution fresh and creating a
   second case.
3. **The atomic finalize claim** (`claim_intake_finalize`, migration 092) now gates on a new
   `intake_jobs.assimilation_complete` flag instead of `predmet_id IS NULL` — closing the gap where a job that
   completed with SOME documents unlinked (a soft partial failure, not a hard crash) was previously stuck
   "finalized" forever with no retry path.
4. **Case number canonicalization** (`shared/case_assimilation.py::normalize_case_number`) — a real 3-part
   parser (prefix/number/year) replacing the prior whitespace-collapse-only placeholder, so every
   punctuation/spacing variant of the same case number resolves to one identity before comparison or storage.

**Mission closure claim, checked against this sprint's own tests** (`tests/test_sprint007_bulletproof_intake.py`,
`tests/test_case_assimilation.py`): the same document uploaded twice, a crash before the completion marker is
written, a soft partial failure after it is written, and a retry of either — all converge on one document, one
case, one lineage chain, one audit/provenance record. See `SPRINT_007_MISSION_REPORT.md` for the full
Otkriveno/Popravljeno/Dokazano/Odloženo breakdown.

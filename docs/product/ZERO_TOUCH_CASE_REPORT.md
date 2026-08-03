# Zero-Touch Case Report

**Mission:** Operation Autonomous Law Office (BETA-002), founder's Master Prompt, 2026-08-03.
**Mission success condition (verbatim):** *"A lawyer uploads documents and the platform
automatically transforms them into an organized legal case requiring minimal additional
administrative work."*

**Verdict: not yet true, and the reason is not what three nights of backend wiring fixed.** The
single largest finding of this mission is that Smart Intake — the pipeline this mission and the two
before it (Night Shift, Operation Lawyer Zero) spent three sessions improving — has **no frontend
entry point**. A lawyer cannot reach it from the app today. Everything below should be read against
that fact: real fixes, real value the moment a lawyer can reach this pipeline, none of it yet
experienced by an actual user.

---

## Repository architecture used

Smart Intake's job/finalize model (`routers/smart_intake.py`) is the component this mission's "upload
→ automatic organized case" journey structurally matches:

```
POST /api/smart-intake/documents (202 + job_id per file, immediately)
        │
        ▼
shared/intake_queue.py (Postgres-backed queue) ── shared/intake_worker.py (background)
        │                                                  │
        │                                     OCR (uploaded_doc/extractor.py)
        │                                     → classify (shared/intake_classify.py)
        │                                     → extract entities (shared/intake_extract.py)
        ▼
POST /api/smart-intake/jobs/{id}/finalize
        │
        ├─→ predmeti (create new, OR attach to existing via ZTC-001's new predmet_id param)
        ├─→ klijenti + predmet_klijenti (client link, best-effort)
        ├─→ predmet_hronologija (extracted deadline, if confidence allows)
        ├─→ conflict check (ZTC-003, new — non-blocking, surfaces via proactive_alerts)
        ├─→ Pinecone ingest + predmet_dokumenti (chunked text, embeddings, tip_dokaza)
        ├─→ Case Genome refresh, background (routers/case_dna.py — ZTC-002 fixed its scale/race bugs)
        └─→ Evidence Vault classification, background (routers/evidence.py, wired by LZ-002)
```

**The gap**: nothing in the actual frontend (`static/vindex.js`, all root `*.html`) calls any
`/api/smart-intake/*` endpoint. The UI instead calls `/api/dokument/upload` (a different, deliberately
synchronous Q&A tool) and `/api/predmeti/{id}/upload` (an older per-case upload path). See
`docs/product/ZERO_TOUCH_CASE_REPORT.md#connected-components` below and the dedicated Blocker Report
(`.vindex_ai_team/decisions/2026-08-03_ZTC-FRONTEND_smart_intake_wiring_BLOCKER_REPORT.md`) for full
evidence.

## Workflow diagram — the 10-step journey against what's real today

| Step (founder's description) | Status |
|---|---|
| 1-3: client arrives, lawyer selects client, uploads files | **Blocked at the first click** — no UI path to Smart Intake exists. The older upload paths work but don't produce the automatic-organization journey described. |
| 4: every subsystem fires on upload (OCR, classify, extract, deadlines, evidence, embeddings, etc.) | **True on the backend**, once a job reaches finalize — confirmed working: OCR, classification, entity extraction, deadline detection (confidence-gated), Evidence Vault classification (LZ-002), Genome refresh (ZTC-002-hardened), Pinecone embeddings/ingest, conflict check (ZTC-003, new). **Not true from the product**, since finalize is never called by any UI action. |
| 5: Vindex automatically knows the case's story (parties, dates, evidence, risks, next actions) | **Real, via Case Genome** (`routers/case_dna.py`) and the deterministic missing-document detector (`services/risk_engine.py`) — both reachable once a case has documents, regardless of which upload path put them there. |
| 6: Lawyer Dashboard reflects all of this automatically | Not independently re-verified this run — LZ-001/002/003 (prior session) already confirmed the dashboard-adjacent pieces (reminders, missing-doc detector, search) read real data once populated. |
| 7: Workflow friction audit | Partially covered by the scenario replay below — the dominant friction point found is structural (no entry point), not a series of small clicks to trim. |
| 8: Scenario replay (A-G) | See table below. |
| 9: Repository-wide reuse audit | See "Duplicate-logic sweep" below — clean, no new duplication found. |
| 10: Beta Readiness Review | See final section. |

## Connected components (Rule Zero — what was wired, not built)

| Existing, working component | Was disconnected from / broken for | Now connected to / fixed |
|---|---|---|
| `finalize_intake_job`'s case-creation logic | Any way to attach a second document to a case a prior finalize call created | `FinalizeReq.predmet_id` — optional, additive, attaches instead of creating new (ZTC-001) |
| `predmet_dokumenti`'s `redni_broj` sequencing | Correct numbering once a case has more than one document (was hardcoded to 1) | Computed from the target case's current max, per document (ZTC-001) |
| Case Genome's document fetch (`_do_genome_refresh`, `refresh_case_dna`) | The true total document count for a case (was silently truncated before the "documents skipped" counter ever saw it) | A separate `count="exact"` query threaded into `_extract_genome` (ZTC-002) |
| Case Genome's document selection | Recency — was pure upload order, silently dropping the newest documents past #25 | `order(desc=True)` — most recent documents considered first when truncation is unavoidable (ZTC-002) |
| `_run_genome_background` (every automatic Genome trigger) | Any protection against concurrent same-case refreshes racing | In-process coalescing wrapper around the renamed `_do_genome_refresh` (ZTC-002) |
| `routers/intake.py`'s conflict-check matching logic | Smart Intake's document-first finalize flow (only ever reachable from the older name-first CRM wizard) | Extracted into `_run_conflict_check`, called as a non-blocking background task from finalize, surfaced via the existing `proactive_alerts` mechanism (ZTC-003) |

## Components reused (no new logic written)

- `proactive_alerts` table/pattern (already used by Case Genome's own delta alerts) — reused as-is for
  surfacing conflict-check findings (ZTC-003), not a new notification system.
- The existing conflict-check matching algorithm (name normalization, substring matching, three
  scenario checks) — extracted, not rewritten, for the auto-trigger (ZTC-003).
- Case Genome's existing per-document header format (`[DOK-NN: ...]`) — unchanged; only fetch
  ordering and the reported skip-count changed (ZTC-002).

## Components intentionally skipped

- **ZIP-archive upload support** (`ZTC-004`) — confirmed not to exist anywhere in the repo. Deferred:
  the founder's own prompt named it as conditional ("if already supported"), and it's practically
  gated on ZTC-000 anyway (no lawyer-reachable upload surface exists yet to extend with ZIP handling).
- **Content-based language detection** (`ZTC-005`) — confirmed not to exist (OCR only selects which
  installed Tesseract packs to feed, never inspects actual document content). No measured failure
  case exists in this investigation (e.g., a real foreign-language document producing bad OCR) — per
  the North Star discipline already established for `M-011` (Performance), not promoted without
  evidence.
- **A document-selection heuristic smarter than pure recency for Case Genome** — flipping to
  descending order is a safe default improvement over pure upload-order, but choosing the *ideal*
  subset (e.g., "always keep the original filing plus the N most recent") is a product/domain
  judgment call, treated as a smaller follow-on rather than guessed at alongside three other fixes.
- **A case-merge/consolidation endpoint** — real gap (confirmed no `spoji_predmet`/`merge_predmet`
  exists anywhere), but it's a recovery tool for a bug ZTC-001 now prevents going forward, not part of
  preventing the bug itself. Not attempted tonight.

## Manual work removed (once ZTC-000 ships)

- A lawyer uploading multiple documents for one client no longer has to notice and manually
  consolidate N accidentally-separate cases into one (ZTC-001).
- A lawyer working a large, long-running case no longer has Case Genome silently and invisibly
  stop considering new documents past the 25th upload (ZTC-002).
- A lawyer no longer has to remember to run a conflict check themselves before an AI-created case
  goes live — it happens automatically, and any finding is visible immediately in the new case
  (ZTC-003).

## Remaining manual work

- **Reaching Smart Intake at all** — today, 100% manual, because there is no button. This is the
  dominant remaining friction point, ahead of everything else in this report combined.
- Reviewing/confirming extracted entities before finalize (already-known, already-scoped elsewhere —
  Smart Intake's own job/entity-correction UI, unaffected by this mission).
- Deciding what to do about a flagged conflict of interest (deliberately left to the lawyer's
  judgment — see ZTC-003's design rationale).
- Manually merging any pre-existing duplicate cases created by the batch-upload bug before ZTC-001
  shipped (no tooling exists for this — named as a real, smaller gap, not attempted tonight).

## Scenario replay (Step 8) — traced against actual code, not live-executed

| Scenario | Finding |
|---|---|
| A — one PDF | Works end to end on the backend (unreachable from the product — see ZTC-000). |
| B — ten PDFs, one client | **Was broken, now fixed (ZTC-001)**: previously created 10 separate cases; now the UI (once it exists) can finalize the first normally and attach the remaining 9. |
| C — mixed images | OCR path for images confirmed working (Night Shift M-001); no new issue found this mission. |
| D — scanned court decision | Same OCR path as C; no distinct issue found. |
| E — several procedural submissions | Exercises the same multi-document-to-one-case path as B — covered by the ZTC-001 fix. |
| F — documents uploaded days apart | Timing itself is not a staleness risk (each upload triggers a correct full recompute) — the real risk was the **concurrency** race (fixed, ZTC-002), which matters for near-simultaneous uploads (e.g., Scenario B/E), not days-apart ones. |
| G — existing case with hundreds of documents | **Was broken, now fixed (ZTC-002)**: Genome silently capped at the first 25 uploaded documents, with a "0 skipped" counter that could never detect the problem. Now considers the most recent 25 and reports the true skip count. |

## Repository-wide reuse audit (Step 9)

No new duplicate logic found. 13 total writers to `predmet_hronologija` confirmed — 11 beyond the
two already known are single-purpose lifecycle writers (case closure, hearing scheduling, contract
representation, onboarding, copilot), not competing chronology-extraction systems. No second OCR
invocation path, no second embeddings/Pinecone-ingest implementation, no second Evidence Vault
classifier. The 4-LLM-analysis-per-document landscape (Smart Intake classifier, Evidence Vault
classifier, Case Genome, the older upload path's free-text "procena") remains intentional layering —
each serves a genuinely different consumer — not accidental duplication, reconfirmed from LZ-002's
prior investigation.

## Current Beta Readiness

**Full test suite: 2306 passed, 1 skipped, 0 failed** (was 2289/1/0 before this session) — zero
regressions from three fixes touching Smart Intake finalize and Case Genome's core refresh path.
No schema/migration changes. No new third-party dependencies. 18 new tests this run.

Substantively: the backend automation this mission set out to verify and harden is now materially
more correct (batch uploads produce one case, Genome doesn't silently truncate large cases, conflict
checking runs automatically) — but the mission's own success condition remains **not met**, because
the product has no way for a lawyer to trigger any of it. This is the honest state, not an inflated
one: three sessions of real backend work are currently inert for an actual beta user.

## Recommended next mission

**ZTC-000 — bring the frontend-wiring decision to the founder directly.** This is the first mission
in three nights of autonomous work that is fundamentally a product/design decision, not an
investigation-then-fix one. Everything else on the Mission Board is downstream of it: no further
backend hardening of Smart Intake pays off for a real lawyer until this ships. Full options laid out
in `.vindex_ai_team/decisions/2026-08-03_ZTC-FRONTEND_smart_intake_wiring_BLOCKER_REPORT.md`.

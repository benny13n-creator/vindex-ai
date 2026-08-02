# Mission Board — Autonomous Night Shift

**Purpose:** the founder's explicit correction to the Night Shift protocol — don't let the agent
"decide what's next" from a loose list each time; work a real, pre-committed backlog instead.
**Rule (founder's own words, binding for this and every future autonomous run):** *"Always execute
the highest-priority mission marked TODO whose dependencies are satisfied. After successful
completion, mark it DONE and automatically proceed to the next eligible mission."*

**Status legend:** `TODO` / `IN_PROGRESS` / `BLOCKED` / `NEEDS_SCOPING` (evidence insufficient to
start safely — must become TODO with real completion criteria before it's eligible) / `DONE`.

**Do not push during autonomous execution.** Commit locally after each mission per the founder's
explicit instruction for this operation — this overrides the standing auto-push convention
(`feedback_auto_push.md`) for Night Shift runs specifically, not permanently.

---

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| M-001 | Image Upload Support | 1 | none | Medium | **DONE** | `.jpg`/`.jpeg`/`.png` accepted on Smart Intake's upload path; OCR runs on them; a regression test uploads an image and confirms text extraction + classification succeed; existing PDF/DOCX path unaffected (full existing suite green). **Completed 2026-08-02** — see `decisions/2026-08-02_M-001_image_upload_MISSION_REVIEW.md`. 3 coordinated fixes required (extractor + worker suffix-guessing + upload validation); 18 new tests, 170 total green. |
| M-002 | Case Genome Wiring Verification | 2 | none | Medium (investigation, not a rewrite) | **DONE** | Direct evidence (not inference) on whether the 2026-07-21 finding ("7/9 event types dead, Case Pipeline never auto-fires") still holds against current code. Produces either: (a) confirmation it's fixed, with the fix's evidence cited, or (b) a precise, current list of what's actually wired vs. not, so Sprint 4 (AI Case Intelligence) work isn't built on an assumption. **Completed 2026-08-02** — see `decisions/2026-08-02_M-002_case_genome_wiring_VERIFICATION.md`. Better than assumed: Case Pipeline auto-fires on `POST /api/predmeti` (fixed 2026-07-22, one day after the finding) and on `/api/intake/from-template`; Genome refresh confirmed live on both major upload paths; promised output fields confirmed genuinely reachable via 2 real consumers. Still true: `intake_kreiraj` (the primary AI-assisted creation endpoint) has no pipeline trigger — proposed as new mission **M-013** (small, copy an existing working pattern). 7/9 event types still dead (re-confirmed independently), 3 of those have real handlers with no emitter (cheap future win, not urgent). `health_index` dead-field claim could not be located — likely already fixed by removal. |
| M-003 | Search Table Mismatch | 3 | none | Small–Medium | **DONE** | `routers/search.py`'s document search reaches `predmet_dokumenti.tekst_sadrzaj` (Smart Intake's table), not only `uploaded_documents.extracted_text`. Regression test: a document ingested via Smart Intake's finalize path is findable by its content via `GET /api/search`. **Completed 2026-08-02** — see `decisions/2026-08-02_M-003_search_table_mismatch_MISSION_REVIEW.md`. Worse than assumed: `uploaded_documents` confirmed fully dead (zero writers, per its own creation migration's comment) — replaced the query target rather than adding a second, permanently-empty one. 3 new tests, 27/27 green. |
| M-004 | Automatic Chronology Extraction (multi-event) | 4 | none (M-006 depends on this) | Large | NEEDS_SCOPING | Requires a new extraction prompt/pipeline (per Bojan Gap Analysis: no code path today extracts >1 dated event per document). Too large for a single Night Shift mission as stated — first sub-task, if attempted: a narrow proof-of-concept (2-3 event types from one document class) with its own completion criteria, not the full feature. |
| M-005 | Deadline Chain Integration | 5 | none | **Small (WRONG — actually needs a design decision)** | **NEEDS_SCOPING** | Wire `routers/rokovi_lanac.py`'s existing deadline-chain calculator to fire automatically when `shared/intake_extract.py` extracts a deadline entity, instead of requiring manual lawyer trigger. Regression test: an extracted deadline produces a full downstream chain (not just the one raw date) without a manual call. **BLOCKED 2026-08-02** — see `decisions/2026-08-02_M-005_deadline_chain_BLOCKER_REPORT.md`. Investigated before implementing: the extraction pipeline's deadline category is too coarse to safely pick the correct one of 14 procedure-specific chains (civil/criminal/labor/administrative/enforcement) — auto-firing blind risks citing the wrong law. Needs a founder-level product/risk decision (silent auto-apply with a new `tip`×`document_type` mapping, vs. propose-then-confirm matching this codebase's established pattern for uncertain AI output) before this is safely re-scoped as a TODO. |
| M-006 | Timeline Intelligence (richer content) | 6 | M-004 | — | BLOCKED | No independent work exists until M-004 produces real multi-event data — the aggregator (`intelligence_timeline.py`) already works; it has nothing richer to show yet. |
| M-007 | OCR Accuracy Improvements | 7 | M-001 (image OCR path must exist first) | Unknown | NEEDS_SCOPING | No current evidence of a specific accuracy problem (no error-rate data, no user complaint on record). Before this is TODO-eligible: gather evidence (a small sample of real OCR outputs vs. source, or confirm none exists to sample) — do not guess at an accuracy fix with no measured baseline. |
| M-008 | AI Extraction Improvements | 8 | none | Unknown | NEEDS_SCOPING | Same issue as M-007 — "improve extraction" has no measurable target without a known failure case. Convert to TODO only once a specific extraction gap is found with evidence (e.g., during M-002's or M-004's investigation). |
| M-009 | Workflow Regression Tests | 9 | none | Medium | TODO | Add end-to-end regression coverage for the 9 Beta Critical Path scenarios (`docs/product/BETA_CRITICAL_PATH_2026-08-02.md`) that don't yet have one — cross-reference against the existing suite first; don't duplicate what `tests/test_mission001_predmet_klijenti.py` and others already cover. |
| M-010 | Security Findings (forensic audit) | 10 | none | Small (scoped narrowly, see note) | TODO | **Scoped deliberately narrow for Night Shift**: only SEC-058 (duplicate `_verify_token`-adjacent PII log line, `shared/deps.py:229` + `api.py:216` — a 2-line diff, already fully specified in the forensic remediation plan's Epic A). **Everything else from the forensic audit's Epic B/Security Governance Framework chain stays explicitly OUT of scope for autonomous execution** — that whole area is mid-founder-review (parked at Revision 2, ACTIVE BLOCKER) and touching it autonomously would violate the "Founder decision required → stop" rule. |
| M-011 | Performance Improvements | 11 | none | Unknown | NEEDS_SCOPING | No profiling data exists in this repo from this session. Do not invent a performance fix without a measured baseline — Phase 2's own admission criteria ("clear repository evidence") isn't met. If attempted: the mission is to *produce* a baseline (identify the 2-3 heaviest real endpoints and measure them), not to "optimize" blind. |
| M-012 | Technical Debt | 12 | none | Small (scoped narrowly) | TODO | **Scoped to one concrete, already-found item**: `routers/copilot.py:610`'s `.select("id")` duplicate-check bug (same nonexistent-column class fixed at `api.py:5245` in Mission 001, deliberately kept separate then — see `decisions/2026-08-02_mission001_predmet_klijenti_ARCHITECTURE_DECISION.md` §2/Revision 3) — now its own small, well-understood, one-line-plus-test fix. |
| M-013 | Wire `intake_kreiraj` into the Case Pipeline / Event Bus | 3.5 (added by M-002, ordered after M-003, before M-004) | none | Small | **DONE** | Proposed by M-002's investigation: `POST /api/intake/kreiraj` (the primary AI-assisted case-creation endpoint) does not trigger the 9-step Case Pipeline, unlike `post_from_template` (`routers/intake.py:775-783`) and the plain `/api/predmeti` route (`api.py:3242-3268`), both of which already do. Completion: `intake_kreiraj` triggers the pipeline the same way (via `emit(EventType.PREDMET_KREIRAN, ...)` or a direct `run_case_pipeline` call, matching an existing convention, not inventing one); a regression test confirms the pipeline runs after a case is created through this specific endpoint. **Completed 2026-08-02** — see `decisions/2026-08-02_M-013_intake_kreiraj_pipeline_MISSION_REVIEW.md`. Verbatim copy of `post_from_template`'s existing pattern. 2 new tests, 180 total green. |

## Dependency graph (for the "eligible" check)

```
M-001 ──> M-007 (needs image OCR path to exist before accuracy work is even meaningful)
M-004 ──> M-006 (timeline has nothing new to show without multi-event data)
M-002, M-003, M-005, M-009, M-010, M-012 ── no dependencies, immediately eligible
M-008, M-011 ── NEEDS_SCOPING, not eligible until converted to a real TODO with evidence
```

## Explicit exclusions from autonomous scope (per the Master Prompt's own Stop Conditions)

- Any change requiring a production schema migration (per this project's standing rule, migrations
  are drafted for the founder to review and run himself — never auto-applied, and per the Master
  Prompt, a schema migration requirement is itself a stop condition, not just an execution note).
- The Security Governance Framework / Epic B rate-limiting chain — explicitly mid-founder-review,
  parked at Revision 2, ACTIVE BLOCKER. Not touched tonight under any mission.
- Intake system convergence at the backend/API level — explicitly rejected by decision record
  (`decisions/2026-08-02_intake_convergence_DECISION_RECORD.md`); not reopened without a new
  founder-supplied reason to revisit.

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

## North Star (added 2026-08-02, binding for all future mission selection)

The founder's own instruction after the first Night Shift run, verbatim: *"Ne bih povećavao broj
agenata. Ne bih dodavao nove uloge. Ne bih komplikovao organizaciju. Umesto toga, zadao bih joj jedan
cilj: 'Smanjite broj beta blokera.' Sve misije neka se biraju isključivo prema tome."* No new roles,
no new process — the existing 15-role organization and this board's existing mechanics are judged
sufficient. What changes is the filter every future mission (proposed or pre-listed) must pass:

**Does this mission remove, or provide direct evidence toward removing, a blocker on one of
`docs/product/BETA_CRITICAL_PATH_2026-08-02.md`'s 9 named scenarios?**

- If yes — eligible, prioritize by the existing priority number.
- If it's general engineering quality with **no** identified connection to a beta-blocking
  scenario (performance work with no measured problem, technical debt with no user-facing
  symptom, "improve X" with no evidence of X currently blocking anything) — it stays
  `NEEDS_SCOPING` or gets removed from active consideration entirely, regardless of how cheap or
  well-understood the fix would be. Being easy to do is not the same as being worth doing next.
- Track actual impact in `METRICS.md`'s "Beta blockers removed" row — that number, over time, is
  the organization's real scorecard, not "missions completed."

Re-evaluated below against this filter (2026-08-02): M-004/M-006 (chronology/timeline) and M-005
(deadline chains) directly gate Beta Critical Path scenarios #6/#7 — stay prioritized. M-007 (OCR
accuracy) is scenario-#4-adjacent but has no measured baseline yet — stays `NEEDS_SCOPING` until
one exists, not promoted on assumption. **M-011 (Performance) has no identified connection to any
Beta Critical Path scenario and no evidence a performance problem exists at all** — per the North
Star, this does not compete for mission slots going forward unless real evidence surfaces that
something is actually blocking beta because of it; kept on the board only as a record, not as
active backlog. M-009 (Workflow Regression Tests) supports confidence in already-closed blockers
rather than closing a new one — useful, but ranked below anything that would close a scenario still
open.

## Operation Lawyer Zero (2026-08-03) — LZ missions

Added per `docs/product/LAWYER_AUTOMATION_MAP.md`, itself filtered through the North Star above.
LZ missions are numbered separately from the M-series (different mission, same board, same rules).

---

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| LZ-001 | Fix `vaznost` vocabulary mismatch so AI-extracted deadlines trigger the automatic email reminder | 1 | none | Small | **DONE** | The daily-cron email reminder (`email_notif.py::posalji_podsetnike`) fires for deadlines written by Smart Intake (`"važan"`) and `intake_kreiraj` (`"bitan"`), not only the hardcoded templates' `"kritičan"`. Regression test: a deadline created via each AI-extraction path is confirmed to match the cron's query. **Completed 2026-08-03** — see `decisions/2026-08-03_LZ-001_reminder_vocabulary_MISSION_REVIEW.md`. Found the vocabulary problem is bigger than scoped (6 spellings across 3 writers, not 2-3) — deliberately fixed only the safe, read-side subset (broadened the cron's filter, touched zero writers) rather than risk breaking `api.py`'s existing `_VAZNOST_ORDER`/`:5449` logic, which already depends on `"bitan"` existing. Full vocabulary unification proposed as **LZ-005** below. 5 new tests, 23/23 green. |
| LZ-002 | Auto-trigger Evidence Vault classification on document ingestion | 2 | none | Medium | **DONE** | `routers/evidence.py`'s richer classifier (`tip_dokaza`, `pravni_elementi`, `kljucne_cinjenice`) fires automatically when a document is ingested (Smart Intake finalize and/or Case Pipeline step 1), not only via the manual `/reklasifikuj` action. Regression test: a newly-finalized document has `tip_dokaza` set without a manual trigger; `services/risk_engine.py`'s missing-document detector can see it. **Completed 2026-08-03** — see `decisions/2026-08-03_LZ-002_evidence_autoclassify_MISSION_REVIEW.md`. Root cause was different than framed: Smart Intake already wrote `tip_dokaza`, using its own coarse classifier's vocabulary, which can never match `EXPECTED_DOCS` — same defect shape as LZ-001, one field over. Case Pipeline step 1 turned out to check an unrelated marker (a 3rd system entirely) — not wired there. Fix: call the existing `klasifikuj_i_sacuvaj` as a background task on Smart Intake finalize. Deliberately does not consume a billing credit (system-initiated, not lawyer-initiated). 2 new tests, 28/28 green. |
| LZ-003 | Extend global search to cover tasks + evidence fields | 3 | none | Small | **DONE** | `routers/search.py` gains `_search_zadaci` and evidence-field coverage, following the existing 6-type pattern exactly. Regression test: a task is findable by name; a document is findable by its `tip_dokaza`/`pravni_elementi`. **Completed 2026-08-03** — see `decisions/2026-08-03_LZ-003_search_extension_MISSION_REVIEW.md`. Found `zadaci` has NO `user_id` column (only `kreirao_uid`/`dodeljen_uid`/`kancelarija_id`) — copying the other 6 branches' pattern exactly would have been a schema/tenant-isolation error. Scoped to the safe subset (creator-or-assignee, a strict subset of the RLS policy's full firm-wide grant). 4 new tests incl. a dedicated isolation check, 37/37 green. |
| LZ-005 | Unify `predmet_hronologija.vaznost` vocabulary across all writers and readers | 5 (proposed by LZ-001) | none | Medium–Large (needs a full reader audit first) | NEEDS_SCOPING | LZ-001 found ≥6 distinct spellings/values across `intake.py` (`"bitan"`), `smart_intake.py` (`"važan"`), `rokovi_lanac.py`'s `_VAZNOST_HRON` (`"kljucan"`/`"normalan"`/`"info"`), the DB's own `CHECK` constraint (`'kritičan'`/`'važan'`/`'informativan'`), and at least 2 existing readers (`api.py`'s `_VAZNOST_ORDER` at `:5114`, a filter at `:5449`) that already depend on `"bitan"` specifically. Before this is a safe TODO: enumerate every reader of `vaznost` (not just the ones found so far) and confirm a single canonical vocabulary can be adopted without silently changing any existing view's sort/filter behavior. |
| LZ-004 | Convert Genome/risk-engine "missing" findings into `zadaci` tasks | 4 | LZ-002 (risk engine needs a real signal first) | Medium (design decision needed — see map) | NEEDS_SCOPING | Auto-create-silently vs. propose-then-confirm needs a founder-level call (same class of question as `M-005`'s blocker report) before this is a safe TODO. |

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
| M-010 | Security Findings (forensic audit) | 10 | none | Small (scoped narrowly, see note) | **DONE** | **Scoped deliberately narrow for Night Shift**: only SEC-058 (duplicate `_verify_token`-adjacent PII log line, `shared/deps.py:229` + `api.py:216` — a 2-line diff, already fully specified in the forensic remediation plan's Epic A). **Everything else from the forensic audit's Epic B/Security Governance Framework chain stays explicitly OUT of scope for autonomous execution** — that whole area is mid-founder-review (parked at Revision 2, ACTIVE BLOCKER) and touching it autonomously would violate the "Founder decision required → stop" rule. **Completed 2026-08-02** — see `decisions/2026-08-02_M-010_sec058_MISSION_REVIEW.md`. Found and disclosed an adjacent, out-of-scope `.warning` line with the same pattern (lower risk, failure-path only) rather than silently touching or ignoring it. 5 new tests (one verified against a negative control), 31/31 green. |
| M-011 | Performance Improvements | 11 | none | Unknown | **NEEDS_SCOPING — parked under the North Star** | No profiling data exists in this repo from this session, and no connection to any Beta Critical Path scenario has been identified. Per the 2026-08-02 North Star addition: this does not compete for mission slots until real evidence surfaces that a performance problem is actually blocking beta — kept on the board as a record, not as active backlog. If that evidence ever appears, re-scope with a measured baseline first (identify the 2-3 heaviest real endpoints and measure them), not a blind "optimize." |
| M-012 | Technical Debt | 12 | none | Small (scoped narrowly) | **DONE** | **Scoped to one concrete, already-found item**: `routers/copilot.py:610`'s `.select("id")` duplicate-check bug (same nonexistent-column class fixed at `api.py:5245` in Mission 001, deliberately kept separate then — see `decisions/2026-08-02_mission001_predmet_klijenti_ARCHITECTURE_DECISION.md` §2/Revision 3) — now its own small, well-understood, one-line-plus-test fix. **Completed 2026-08-02** — see `decisions/2026-08-02_M-012_copilot_predmet_klijenti_MISSION_REVIEW.md`. Scope grew from 1 to 2 bugs: found, while fixing the known one, that the same function's INSERT also had Mission 001's `user_id` bug — a 6th call site that mission's sweep missed. Fixed both together (same user-facing action). 2 new tests, 30/30 green. |
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

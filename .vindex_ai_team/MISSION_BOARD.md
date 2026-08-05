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

## Operation Autonomous Law Office (2026-08-03) — ZTC missions

Founder's Master Prompt (BETA-002): design/implement the first complete "Zero-Touch Case" workflow.
Mission success condition (verbatim): *"A lawyer uploads documents and the platform automatically
transforms them into an organized legal case requiring minimal additional administrative work."*
Full investigation: `decisions/2026-08-03_zero_touch_case_SCENARIO_INVESTIGATION.md`. Deliverable:
`docs/product/ZERO_TOUCH_CASE_REPORT.md`. ZTC missions numbered separately from M-/LZ-series.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| ZTC-000 | Give Smart Intake a real frontend entry point | 1 (top of board — everything below is inert without it) | none | Large (product/design decision, not wiring) | **NEEDS_SCOPING — founder decision required** | See `decisions/2026-08-03_ZTC-FRONTEND_smart_intake_wiring_BLOCKER_REPORT.md`. Confirmed: zero references to `smart-intake` anywhere in the frontend; the UI only calls the two older upload paths. Every automation fix this session and last (LZ-001/002, ZTC-001/002/003) only pays off once a lawyer can actually reach this pipeline. Not a wiring fix — building new UI screens blind conflicts with this project's own UI-style discipline and is a real product-direction call (which upload path becomes primary). Three options laid out in the report; none chosen. |
| ZTC-001 | Allow finalize to attach a document to an existing case (Scenario B) | 2 | none | Medium | **DONE** | `FinalizeReq` gains optional `predmet_id`; providing it attaches instead of creating a new case; `redni_broj` sequenced correctly across multiple documents in one case. **Completed 2026-08-03** — see `decisions/2026-08-03_ZTC-001_scenario_b_attach_MISSION_REVIEW.md`. Confirmed the most consequential single finding against the mission's success criterion: a 10-file batch upload previously created 10 separate cases with no merge feature to recover. 5 new tests, 2306 total green. |
| ZTC-002 | Fix Case Genome's silent 25-document cap + concurrent-refresh race (Scenario G + F) | 3 | none | Medium | **DONE** | Genome document fetch orders by recency instead of upload order when truncating; the reported skipped-document count reflects the true total, not an already-limited approximation; concurrent same-case refreshes coalesce instead of racing. **Completed 2026-08-03** — see `decisions/2026-08-03_ZTC-002_genome_scale_and_race_MISSION_REVIEW.md`. The "documents skipped" counter was found to always read ~0 for exactly the cases where truncation mattered (>25 real documents) — same "wrong value, not no value" defect shape as LZ-001/LZ-002. 8 new tests, 2306 total green. |
| ZTC-003 | Auto-run conflict-of-interest check on document-first case creation (Scenario 5) | 4 | none | Medium | **DONE** | Smart Intake's finalize calls the existing conflict-check logic (extracted from `routers/intake.py` into a reusable function, not duplicated) as a non-blocking background task, surfacing any finding via the existing `proactive_alerts` mechanism. **Completed 2026-08-03** — see `decisions/2026-08-03_ZTC-003_conflict_check_autowiring_MISSION_REVIEW.md`. Deliberately non-blocking: a false-positive name match must never silently block a real case's creation. 5 new tests, 2306 total green. |
| ZTC-004 | ZIP-archive upload support | 5 | ZTC-000 (no reachable upload UI to extend until then) | Medium | NEEDS_SCOPING | Confirmed: does not exist anywhere (only `routers/data_export.py`'s unrelated export-zip feature uses `zipfile`). Would need per-entry zip-bomb guards mirroring `uploaded_doc/extractor.py`'s existing DOCX protections (`MAX_ZIP_ENTRIES`, `MAX_DECOMPRESSED_BYTES`), then loop each entry through the existing per-file upload/OCR pipeline. Named as optional ("if already supported") in the founder's own prompt — deferred rather than rushed alongside three higher-severity fixes tonight, and blocked in practice on ZTC-000 (no lawyer-reachable upload surface to extend yet anyway). |
| ZTC-005 | Content-based document language detection | — | none | Unknown | **NEEDS_SCOPING — parked, no evidence of a problem** | Confirmed: does not exist. OCR's own `_detect_ocr_lang` only checks which Tesseract language packs are *installed*, always feeding the same fixed Serbian+English combination regardless of actual document content — no per-document detection, no stored language field anywhere. Same North-Star treatment as M-011 (Performance): no measured failure case (e.g., a real foreign-language document producing bad OCR) exists yet in this investigation, and building content-based detection is new capability, not "connect existing." Not promoted to TODO without evidence a document has actually been mishandled because of this. |

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

## Operation Invisible Features (2026-08-03) — IF missions

Founder's Master Prompt (BETA-003): find every production-ready-but-unreachable capability and
connect what already exists — forbidden from building new backend capability. Full census:
`decisions/2026-08-03_invisible_features_CENSUS.md`. Deliverable: `docs/product/FEATURE_DISCOVERY_REPORT.md`.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| IF-001 | Wire GDPR self-service account deletion into Settings | 1 | none | Small | **DONE** | `DELETE /api/gdpr/account` (already working) gets a real Settings button with an irreversible-action confirmation. **Completed 2026-08-03** — see `decisions/2026-08-03_IF-001_gdpr_account_deletion_MISSION_REVIEW.md`. Motivated by a public commitment already made in `static/bezbednosni-list.html` ("self-service button in preparation"). Checked GDPR *export* first and found it's a live-but-inferior duplicate of the already-wired `/api/export/complete` — correctly left unconnected. Pure frontend change, `sw.js` cache bumped, 2306/2307 suite unchanged. |
| IF-002 | Wire per-case AI Briefing button into case-detail view | 2 | none | Small | **DONE** | `POST /api/intelligence/predmeti/{id}/briefing` (already working) gets a button in the existing Case Intelligence section. **Completed 2026-08-03** — see `decisions/2026-08-03_IF-002_case_intelligence_briefing_MISSION_REVIEW.md`. Confirmed distinct from the already-wired portfolio-wide CIO briefing (per-case vs. cross-case) before wiring, to avoid shipping a duplicate. All LLM-sourced text passed through the codebase's canonical `escHtml()` before DOM insertion. Pure frontend change, 2306/2307 suite unchanged. |
| IF-003 | Client CSV import — resolve which of two implementations should be live | 3 | none | — (product decision) | **NEEDS_SCOPING — founder decision required** | See `decisions/2026-08-03_IF-DECISIONS_duplicates_and_memory_graph_BLOCKER_REPORT.md` §1. The dead implementation (`import_klijenti.py`) is the SAFER one (preview + confirm); the live one is a simpler one-shot import. Not a wiring task — replacing, augmenting, or leaving as-is are all real product choices. |
| IF-004 | WhatsApp notifications — reconnect dedicated subscription system, or retire it | 4 | none | — (product decision) | **NEEDS_SCOPING — founder decision required** | See blocker report §2. `sms.py`'s simpler flag-based approach is already live and covers the core need; the dead `whatsapp_notif.py` adds granularity with no evidence of demand. Reads as a deletion candidate, not a reconnection one — flagged rather than deleted unilaterally. |
| IF-005 | Memory Graph — decide how relationships get populated before any UI is safe to ship | 5 | none | — (product/architecture decision) | **NEEDS_SCOPING — founder decision required** | See blocker report §3. The single most interesting dead feature found (`GET /api/memory-graph/upit` — cross-case argument/outcome queries), but `memory_graph_edges` has exactly one writer (an also-dead manual-entry endpoint) — shipping a query box alone would show every real user a permanently empty graph. Needs a decision: manual population UX (needs its own UI too), or automatic extraction from case data (new AI logic, explicitly out of this mission's scope). |
| IF-006 | Remaining confirmed-dead routers, unranked | 6 | none | Unknown per-item | TODO (needs individual assessment) | `agent_notifications`, `knowledge_hygiene`, `knowledge_transfer`, `region`, `strategy_simulator`, `style_checker` — all real, all genuinely unreachable, none individually assessed for relative lawyer value this run. `auto_discovery` is admin-only by design (lower lawyer-facing priority regardless). `status_page` needs one direct follow-up read of `static/status.html`'s own script before its true status is confirmed. |

## Operation Lawyer Day (2026-08-03) — LD missions

Founder's Master Prompt (BETA-004): simulate a complete real law-office workday inside Vindex AI,
minute by minute, to answer one question — can a lawyer work an entire day without leaving the
platform? Full simulation: `docs/product/LAWYER_DAY_REPORT.md`. Root-cause analyses of every
interruption found: `docs/product/WORKFLOW_INTERRUPTION_REPORT.md`. Hidden-feature findings:
`docs/product/HIDDEN_FEATURES_REPORT.md`. Engagement-wide trajectory: `docs/product/BETA_PROGRESS.md`.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| LD-001 | Fix photo upload on the actually-reachable upload path (`api.py`, not Smart Intake) | 1 | none | Small | **DONE** | `POST /api/predmeti/{id}/upload`'s `_ALLOWED_MIMES`/`_ALLOWED_SUFFIXES` widened to accept `.jpg/.jpeg/.png`, mirroring Smart Intake's already-proven allowlist. **Completed 2026-08-03** — see `decisions/2026-08-03_LD-001_photo_upload_reachable_path_MISSION_REVIEW.md`. Corrects Night Shift M-001's "photo upload now works end to end" claim, which was only true for the unreachable Smart Intake path — a real lawyer could not upload a phone photo anywhere in the app until this fix. 5 new tests, 2311 total green. |
| LD-002 | Hearing-prep export bundle | 2 | none | Medium | NEEDS_SCOPING (P2, not implemented per mission's own "only P0/P1" rule) | No single feature bundles judge/opponent research + Case Genome/Briefing + deadlines + drafted documents into one export. Every underlying piece already works — pure aggregation UI. See `WORKFLOW_INTERRUPTION_REPORT.md` Finding #5. |
| LD-003 | Lawyer-facing audit/activity log viewer | 3 | none | Small-Medium | TODO (P2/P3, not implemented) | `shared/audit_immutable.py`'s log is written but never rendered anywhere in the UI. See Finding #6. |
| LD-004 | Case archiving button inside case-detail view | 4 | none | Small | TODO (P2/P3, not implemented) | Currently only reachable via bulk-select from the case list. See Finding #7. |
| LD-005 | Duplicate-file detection on the reachable upload path | 5 | none | Small | TODO (P2, not implemented) | Smart Intake has exact-hash dedup; `api.py`'s reachable per-case upload does not. See Finding #4. |
| LD-006 | Team comments (`predmet_komentari`) missing from global search | 6 | none | Small | TODO (P3, not implemented) | Confirmed NOT a duplicate of `predmet_beleske` (private notes) — both serve distinct, intentional purposes per the UI's own copy. Only the search-coverage gap is real. See Finding #8. |

## Operation Beta Lockdown (2026-08-03) — BL missions

Founder's Master Prompt (BETA-005): a comprehensive Beta-readiness audit — Feature Completion Matrix,
full workflow tracing, tenant-isolation/audit/search sweep, workflow-fragmentation documentation, and a
19-scenario Beta Acceptance Test. Full reports: `docs/product/BETA_LOCKDOWN_REPORT.md` (executive
summary), `FEATURE_COMPLETION_MATRIX.md`, `BLOCKER_REPORT.md`, `WORKFLOW_GAPS.md`, `CURRENT_STATE.md`,
`RELEASE_READINESS.md`. Investigation: `decisions/2026-08-03_beta_lockdown_isolation_audit_search_INVESTIGATION.md`.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| BL-001 | Fix cross-tenant task-data leak (`GET /api/zadaci/predmet/{id}`, zero ownership check) | 1 | none | Small | **DONE** | Ownership check added mirroring an established in-file pattern. **Completed 2026-08-03** — see `decisions/2026-08-03_BL-001_zadaci_idor_MISSION_REVIEW.md`. Found via this mission's own tenant-isolation sweep, not externally reported — a live, exploitable IDOR, not theoretical. 4 new tests, one confirmed via negative control against the pre-fix code. 2315 total green. **This mission's own success-critical finding** — see `BETA_LOCKDOWN_REPORT.md`. |
| BL-002 | Draft staging/approval pipeline has no frontend entry point | 2 | none | Medium | NEEDS_SCOPING — founder decision, same shape as ZTC-000/BLOCKER-2 | `routers/drafting.py`'s confidence-gated draft review/approval flow (which would make drafts permanently searchable) has zero frontend references. Newly found this mission. See `BLOCKER_REPORT.md`/`BLOCKER-3`. |
| BL-003 | Audit-log coverage: ~80% of the defined action taxonomy never fires | 3 | none | Medium (spans many call sites) | TODO, not urgent | `shared/audit_immutable.py::AUDITABLE_ACTIONS` defines 24 action types; only ~5-8 actually trigger in production code, including a gap where `predmet_create` isn't logged for the real-world case-creation path (`intake_kreiraj`). See `WORKFLOW_GAPS.md` #7/#8. |
| BL-004 | Genome background-refresh defense-in-depth hardening | 4 | none | Small | TODO, low priority | `_do_genome_refresh` doesn't hard-return on an ownership-check miss — not currently exploitable via any real call site, but worth an early `return` for defense-in-depth. See `WORKFLOW_GAPS.md` #11. |

## Operation Beta Closure (2026-08-03) — BC missions

Founder's Master Prompt (BETA-006): expose, complete, and polish existing technology rather than build
new — explicitly authorizing Priority 1 (Smart Intake UI) after five prior missions correctly declined
to guess at it. Full reports: `docs/product/BETA_CLOSURE_REPORT.md` (executive summary),
`UPDATED_BLOCKER_REPORT.md`, `UPDATED_FEATURE_MATRIX.md`, `WORKFLOW_COMPLETION_REPORT.md`,
`UI_WIRING_REPORT.md`.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| BC-001 | Build Smart Intake's first-ever frontend (upload → review → finalize) | 1 (ABSOLUTE) | none | Large (frontend only, zero backend changes) | **DONE** | New `#si-overlay` panel (3 steps), 2 new entry-point buttons, wired to all 4 existing `routers/smart_intake.py` endpoints. **Completed 2026-08-03** — see `docs/product/UI_WIRING_REPORT.md`. Resolves `BLOCKER-2`/`ZTC-000` — the dominant open item across 5 prior missions tonight. Zero backend changes; full suite unchanged at 2315 passed. |
| BC-002 | Expose the draft staging/approval pipeline | 2 | none | Small | **DONE** | New "Nacrti na čekanju" section in case detail, wired to `routers/drafting.py`'s existing `staging`/`approve`/`reject` endpoints. **Completed 2026-08-03** — resolves `BLOCKER-3`. Zero backend changes. |

## Operation Wow Factor (2026-08-03) — WOW missions

Founder's Master Prompt (BETA-007): dramatically increase perceived value via composition, not new
features — "Not five buttons. One." Full report: `docs/product/WOW_REPORT.md`. Investigation:
`decisions/2026-08-03_wow_factor_composition_audit_INVESTIGATION.md`.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| WOW-001 | Winning Strategy Brief — compose AI Briefing + Similar Cases + Outcome Trends into one panel | 1 | none | Small (pure orchestration) | **DONE** | New button in Case Intelligence section, parallel-fetches 3 existing endpoints, graceful per-section degradation. **Completed 2026-08-03** — see `docs/product/WOW_REPORT.md`. Deliberately a separate button from plain AI Briefing (no silent cost change to an existing feature); deliberately excludes Matter Intelligence (already visible elsewhere) and Judge/Opponent Intelligence (real data gap found, not composable for free — see WOW-003). Zero backend changes, full suite unchanged at 2315 passed. |
| WOW-002 | Post-upload magic-moment recap for Smart Intake | 2 | none | Small | **DONE** | After finalize, shows document-type counts + review-correction count using data already in memory — zero new API calls. Does not poll for Genome/Evidence completion (states plainly they're running in background) to avoid introducing new waiting/polling. |
| WOW-003 | Auto-populate `predmeti.tuzilac`/`tuzeni` from Smart Intake's already-extracted judge/opponent entities | 3 | none | Small (backend write, uses existing extraction) | NEEDS_SCOPING | Found this mission: Smart Intake extracts judge/court/plaintiff/defendant entities but never writes them onto the case row, so Judge & Court Profiler / Opponent Intelligence still require manual name entry even when the AI already knows it. A real, small, low-risk backend change — outside this mission's compose-only charter, flagged for a future mission rather than built speculatively. |

## Project Synapse (2026-08-03) — SYN missions

Founder's Master Prompt (BETA-008): "Architecture Evolution" — transform independent AI modules into
one continuously reasoning system. "DO NOT BUILD NEW AI FEATURES. BUILD ONE INTELLIGENCE." Full
reports: `docs/architecture/EXECUTIVE_SUMMARY.md`, `COGNITIVE_GRAPH.md`,
`INTELLIGENCE_PROPAGATION_MAP.md`, `ORCHESTRATION_REPORT.md`, `COGNITIVE_ISLANDS_REPORT.md`,
`FOUNDER_WOW_REPORT.md`. Investigation: `decisions/2026-08-03_synapse_cognitive_audit_INVESTIGATION.md`.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| SYN-001 | Fix `calculate_procesni_rizik`'s naive/aware datetime bug + return critical-hearing rows | 1 | none | Small | **DONE** | Pre-existing bug: silently excluded any hearing stored as a plain date from `predstojeći_rokovi`/`kriticni_rokovi`. Found while wiring SYN-002 below, fixed as a prerequisite. 3 new tests, 12 pre-existing `test_matter_intel.py` tests re-confirmed passing. |
| SYN-002 | Emit `HEALTH_SCORE_PROMENJEN` and `ROK_KRITICAN` — both had real, fully-wired proactive-alert handlers, never triggered by anything | 2 | SYN-001 | Small | **DONE** | Wired from `routers/matter_intel.py::get_matter_intel`, mandatory dedup against an existing unread alert (this endpoint fires on every case-open). 6 new tests including an explicit dedup-guard test. |
| SYN-003 | Copilot's case analysis reads Case Genome instead of re-deriving from scratch | 3 | none | Small | **DONE** | Confirmed 4th independent case-strength-synthesis path via a full cognitive audit; now folds a compact Genome summary into its existing single GPT call. 3 new tests. |
| SYN-004 | Firm Brain (precedenti.py) reads Case Genome instead of re-deriving from scratch | 4 | none | Small | **DONE** | Same pattern as SYN-003. 2 new tests. |
| SYN-005 | New `DOCUMENT_JOB_FAILED` handler (event already emitted, zero handler exists) | 5 | none | Small-Medium | NEEDS_SCOPING | Requires genuinely new handler logic (what to notify, whom) — outside this mission's orchestration-only charter. See `COGNITIVE_ISLANDS_REPORT.md` #4. |
| SYN-006 | Outcome Intelligence + Judge/Court Profiler read Case Genome (same pattern as SYN-003/004) | 6 | none | Small-Medium | TODO | Confirmed same gap as SYN-003/004; not fixed this mission due to more involved per-file prompt logic in each — well-precedented, low-risk future mission. |
| SYN-007 | `knowledge_profiles` phantom data source (Briefing's 8th source, structurally always empty) | 7 | none | — (founder decision) | NEEDS_SCOPING | Only writer is confirmed-dead `knowledge_transfer.py`. Two paths (build real extraction = new AI, out of charter; wire the existing dead router's UI = smaller). Founder call. |
| SYN-008 | Write Smart Intake's extracted judge/opponent entities onto `predmeti.tuzilac`/`tuzeni` | 8 | none | Small | NEEDS_SCOPING (reconfirmed from `WOW-003`) | Highest-value remaining opportunity per `FOUNDER_WOW_REPORT.md` — would let Judge/Opponent Intelligence auto-populate with zero lawyer typing. Not attempted this mission (compose-only scope). |

## Project Nexus (2026-08-03) — NEX missions

Founder's Master Prompt (BETA-009): "Pre-Beta Intelligence Integration Mission" — transform Vindex from
a collection of modules into one intelligence flow. Full reports: `docs/architecture/NEXUS_INTELLIGENCE_GRAPH.md`,
`NEXUS_MODULE_DEPENDENCY_MAP.md`, `NEXUS_ICS_SCORE.md`, `NEXUS_TOP_20_BREAKPOINTS.md`,
`NEXUS_PRE_BETA_CRITICAL_PATH.md`, `NEXUS_ORCHESTRATION_REPORT.md`, `NEXUS_BETA_READINESS_REPORT.md`.
Investigations: `decisions/2026-08-03_nexus_module_inventory_source_of_truth_INVESTIGATION.md`,
`decisions/2026-08-03_nexus_provenance_reliability_audit_INVESTIGATION.md`.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| NEX-001 | Eliminate `routers/ccc.py`'s duplicate, silently-diverging health-score formula + fix its missing-`tip_dokaza` bug | 1 | none | Small | **DONE** | Delegates to the canonical `services/risk_engine.py::calculate_procesni_rizik` instead of a local reimplementation. **Completed 2026-08-03** — see `docs/architecture/NEXUS_ORCHESTRATION_REPORT.md`. Confirmed real Phase-5 violation: two live endpoints could report two different `health_score` values for the same case under the identical field name. 2 new tests + 2 rewritten (imported a now-deleted function), 11 total in `test_ccc.py`. |
| NEX-002 | Ground `routers/zadaci.py::ai_analiziraj_predmet`'s AI task creation in the canonical `identify_case_problems` | 2 | none | Medium | **DONE** | Was a 5th independent, side-effect-producing GPT-based missing-document detector bypassing the platform's declared sole deterministic algorithm. Now folds the deterministic finding into its GPT prompt (and its GPT-failure fallback path) instead of independently guessing from raw filenames. 3 new tests. |
| NEX-003 | Fix Case Genome refresh's false-success-toast on genuine LLM failure | 3 | none | Small | **DONE** | Frontend never checked `dna.greska` before choosing a toast — a lawyer saw a green "success" notification on a real failure. Pure frontend fix, no backend change. |
| NEX-004 | Resolve `PREDMET_KREIRAN`'s Event Bus durability gap | 4 | Verify `run_case_pipeline` idempotency first | Medium | **DONE (2026-08-03, Project Sentinel)** | Idempotency verified (`_step_ekstrakcija_rokova`'s marker-based dedup); `api.py::kreiraj_predmet` now writes directly to the durable `events` outbox instead of calling `emit()`, mirroring `_emit_genome_event`'s already-proven pattern. See `SENTINEL_ORCHESTRATION_REPORT.md` Fix 3. `ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN` share the same class of gap but were NOT converted — see SENT-001 below. |
| NEX-005 | New `DOCUMENT_JOB_FAILED` handler | 5 | none | Small-Medium | **DONE (2026-08-03, Project Sentinel)** | `on_document_job_failed` added to `services/event_bus.py`, subscribed in `_register_defaults()` — resolves the job owner via `intake_jobs.uploaded_by` (the outbox event row itself carries no `user_id`) and writes a `proactive_alerts` row. See `SENTINEL_ORCHESTRATION_REPORT.md` Fix 4. |
| NEX-006 | AI action provenance strategy (`model`/`prompt version`/`output hash`, captured nowhere in the repo) | 6 | none | Large (schema decision) | NEEDS_SCOPING — founder decision | Uniform gap across all 6 audited AI call sites. Needs a founder-level decision on how much provenance infrastructure to build. |
| NEX-007 | Fold Case Genome/AI Briefing into an existing hallucination guardrail (Quality Gate's citation check, or Legal Reasoning Engine's SOURCE-n constraint) | 7 | none | Medium | TODO | Both of the highest-visibility AI outputs trust GPT-4o's own output on prompt instruction alone; two structurally-stronger guardrails exist elsewhere, unused here. |
| NEX-008 | Outcome Intelligence + Judge/Court Predictor read Case Genome (same pattern as Copilot/Firm Brain, Project Synapse) | 8 | none | Small-Medium | TODO | Reconfirmed same gap; well-precedented, low-risk future mission. |

## Dependency graph (for the "eligible" check)

```
M-001 ──> M-007 (needs image OCR path to exist before accuracy work is even meaningful)
M-004 ──> M-006 (timeline has nothing new to show without multi-event data)
M-002, M-003, M-005, M-009, M-010, M-012 ── no dependencies, immediately eligible
M-008, M-011 ── NEEDS_SCOPING, not eligible until converted to a real TODO with evidence
```

## Project Sentinel (2026-08-03) — SENT missions

Founder's Master Prompt: "Pre-Beta Reliability, Trust & Operational Integrity Mission" — deliberate
follow-on to Project Nexus (which answered "do the modules cooperate?"); this mission answers "can the
system survive real law-office operation without losing data, silent errors, or false AI conclusions?"
Full report: `docs/architecture/SENTINEL_RELIABILITY_TRUST_REPORT.md` (Phase 7 E2E verification, Phase 8
metrics — ICS/CIC/Reliability Score/Provenance Coverage/Failure Recovery Coverage, Phase 9 Beta Gate,
full findings list, final recommendation). Implementation record: `SENTINEL_ORCHESTRATION_REPORT.md`.
Investigations: `decisions/2026-08-03_sentinel_critical_flows_INVESTIGATION.md`,
`decisions/2026-08-03_sentinel_event_bus_hardening_INVESTIGATION.md`,
`decisions/2026-08-03_sentinel_failure_recovery_INVESTIGATION.md`,
`decisions/2026-08-03_sentinel_source_of_truth_recheck_INVESTIGATION.md`,
`decisions/2026-08-03_sentinel_provenance_hallucination_INVESTIGATION.md`.

Also closed **NEX-004** and **NEX-005** (see above) — both scoped by Project Nexus, unblocked and
implemented this mission.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| SENT-001 | Convert `ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN` to durable outbox | 1 | Verify `matter_intel.py`'s alert-dedup is safe under durable retry (a naive conversion could double-insert an alert) | Medium | **NEEDS_SCOPING — re-verified still accurate, still open (2026-08-03, Project Phoenix)** | Same non-durable-emit exposure `PREDMET_KREIRAN` had — NOT converted this mission per the investigation's own explicit recommendation to verify dedup safety first. Project Phoenix directly re-confirmed both event types are still `emit()`'d purely in-process, no durable outbox row for either (`2026-08-03_phoenix_reverify_sentinel_INVESTIGATION.md` §7) — unchanged, not a regression, still gated on the same dedup-safety check. |
| SENT-002 | Ground Morning Briefing in `calculate_procesni_rizik`/`identify_case_problems` | 2 | none | Medium-Large | NEEDS_SCOPING | Proven fix pattern exists (Task Engine, Project Nexus) but Briefing fans out across up to 20 active cases per request — not a single-case surgical fix, needs its own scoped pass. |
| SENT-003 | Strategy Engine persistence (link legal conclusions to `predmet_id`) | 3 | Founder decision: should every Strategy Engine call require a case context? | Large (architecture) | NEEDS_SCOPING — founder decision | 8 endpoints currently discard every output on response; not linked to Timeline/Genome/Firm Brain. |
| SENT-004 | Widen `AUDITABLE_ACTIONS` + wire Strategy Engine/Copilot/Briefing/Case Pipeline/Task Engine into durable audit | 4 | Founder decision on which actions warrant durable hash-chained provenance | Medium-Large | **MOSTLY DONE (2026-08-03, Mission Ledger + Mission Migration)** | Strategy Engine (9 endpoints), Briefing, Task Engine, and 6 of Copilot's ~8 handlers now wired. Case Pipeline's own 9 internal steps remain unwired — see `MIGRATION-001`. |
| SENT-005 | Unify the 3 independent hallucination-guard patterns (`quality_gate.py`, Task Engine's prompt-grounding, ~50 ad hoc JSON-parse-only sites) into one shared layer | 5 | Design decision: which pattern becomes canonical | Large (new shared infrastructure) | NEEDS_SCOPING — founder decision | Highest-exposure gap: `routers/copilot.py`'s free-text chat has no grounding/citation check at all. |
| SENT-006 | AI Provenance shared schema (`model`/`prompt version`/`duration`/`sources used`) | 6 | Founder decision on schema investment | Large | **DONE (2026-08-03, Mission Atlas)** | Discovered migration 043's `ai_forensics` table + `security/ai_forensics.py` already implemented ~half this schema but were never called from any AI call site (confirmed dead). Connected via `shared/ai_client.py`'s existing SEC-003 patch point (same interception layer, extended, not duplicated) — now captures model/prompt-hashes/tokens/latency/output-hash/correlation_id for 100% of AI calls structurally. See `docs/architecture/ATLAS_AI_PROVENANCE_REPORT.md`. Migration 089 (drafted, NOT applied) adds the remaining schema columns + immutability trigger. |
| SENT-007 | Document-level contradiction detection within a case | 7 | none | Large (new capability) | TODO — out of "connect, don't build" mandate | No existing mechanism to extend; would be new capability, correctly not attempted this mission. |
| SENT-008 | Upload idempotency via `source_sha256` | 8 | Product decision: silently skip duplicate? show existing doc? merge? | Medium | NEEDS_SCOPING — product decision | Hash is already computed and discarded; retry-after-timeout currently duplicates the entire upload pipeline. |
| SENT-009 | Genome background-refresh durability (the *trigger*, not the `GENOME_UPDATED` event itself) | 9 | none | Medium-Large | TODO | 4 separate fire-and-forget entry points; a crash between upload and refresh completion silently drops the Genome update. |
| SENT-010 | Confirm Firm Brain auto-population intent | 10 | Founder confirmation | Small (once scoped) | NEEDS_SCOPING — founder decision | Manual-save-only entry points confirmed at medium confidence; may be deliberate (lawyer-curated knowledge), needs explicit confirmation either way. |

## Mission Atlas (2026-08-03) — ATLAS missions

Founder's Master Prompt: "AI Provenance & Decision Traceability" — closes SENT-006 (above). Full report:
`docs/architecture/ATLAS_AI_PROVENANCE_REPORT.md`. Migration draft (NOT applied):
`migrations/089_ai_provenance_extension.sql`.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| ATLAS-001 | Run migration 089 in production | 1 | Founder runs migrations himself, per standing rule | Small | NEEDS_SCOPING — founder action | Until run, provenance capture falls back to legacy-only columns (proven safe, but Provenance Coverage stays at the pre-migration floor). |
| ATLAS-002 | Populate `confidence_score`/`hallucination_check_result` | 2 | none (mechanical, but touches each parsing call site) | Medium | TODO | Wrapper only sees the raw API response before the caller parses JSON; needs a second reporting call (e.g. `ai_provenance.report_confidence(correlation_id, score)`) per call site that already derives a confidence value (Drafting's `quality_gate`, Genome's `snaga_procent`). |
| ATLAS-003 | Wire `retrieved_context_ids`/`retrieval_query` from RAG functions | 3 | none | Medium-Large | TODO | `app/services/retrieve.py`'s retrieval functions return formatted text, not chunk/document IDs — a return-contract change to a widely-shared module. |
| ATLAS-004 | Unify or explicitly separate Genome's `_emit_genome_event` correlation_id from this mission's per-AI-call correlation_id | 4 | Architecture decision | Small (once decided) | **DONE (2026-08-03, Mission Ledger)** | Unified: `_emit_genome_event` now inherits `shared/ai_provenance.py`'s request-scoped correlation_id instead of minting its own, falling back to a fresh one only when no context exists (e.g. a background call). |
| ATLAS-005 | Extend explicit `case_context()` wiring to the ~45 AI call sites not covered this mission | 5 | none (mechanical) | Large (many small edits) | **MOSTLY DONE (2026-08-03, Mission Migration)** | Extended to Copilot's 5 remaining handlers, Court Predictor's 7 endpoints, Evidence classification, upload's 3 parallel calls. Remaining: `main.py::ask_agent`, `drafting/`'s deep generate call — see `MIGRATION-001`/`002`. |
| ATLAS-006 | Populate `audit_reference`, cross-link to `audit_immutable` | 6 | SENT-004 (`AUDITABLE_ACTIONS` widening) | Medium | **MOSTLY DONE (2026-08-03, Mission Ledger + Mission Migration)** | `audit_reference` defaults to `correlation_id`. `AUDITABLE_ACTIONS` widened + `log_action` wired for 28 of 36 inventoried AI operations (78%, up from Ledger's ~25%) — see `docs/architecture/MIGRATION_CANONICAL_AI_ADOPTION_REPORT.md`. |

## Mission Ledger (2026-08-03) — LEDGER missions

Founder's Master Prompt: "End-to-End Traceability & Operational Evidence Chain" — closes `ATLAS-004`
and partially closes `SENT-004`/`ATLAS-006` (above). Full report:
`docs/architecture/LEDGER_TRACEABILITY_REPORT.md`. Migration draft (NOT applied):
`migrations/090_ledger_correlation_id.sql`.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| LEDGER-001 | Run migration 090 in production (alongside 089 if not already run) | 1 | Founder runs migrations himself | Small | NEEDS_SCOPING — founder action | Until run, `correlation_id` on `events`/`audit_immutable` falls back to payload/metadata JSON only (proven safe, not indexed/joinable at the column level). |
| LEDGER-002 | Propagate `PREDMET_KREIRAN`'s correlation_id into Case Pipeline's 9 internal steps | 2 | Decision: is per-step granularity worth it, or is "pipeline ran" sufficient? | Medium | NEEDS_SCOPING — not re-investigated this pass | Chain currently provably continuous through the event trigger, not into each step's own writes. Not directly re-traced by Project Phoenix (out of its 4 forks' specific scope) — status carried forward unchanged, not re-confirmed. |
| LEDGER-003 | Wire correlation_id into `DOCUMENT_JOB_*` events (SQL-sourced, not Python) | 3 | Founder decision — worth changing `fail_intake_job` and sibling RPC signatures? | Medium-Large | NEEDS_SCOPING — founder decision | Needs `intake_worker.py` to generate and pass a correlation_id at enqueue time, threaded through the whole job lifecycle. Related, same-shaped design question surfaced independently by Project Phoenix's `MIGRATION-003` re-scoping (Smart Intake's background-worker context has no HTTP-request-scoped correlation_id to inherit either) — worth resolving both together, same root cause. |
| LEDGER-004 | Extend `AUDITABLE_ACTIONS`/`log_action` wiring to the remaining ~15 AI features (Court Predictor, Drafting, document classification, Copilot's other ~9 handlers, etc.) | 4 | none (mechanical, many files) | Large | **MOSTLY DONE (2026-08-03, Mission Migration)** | Court Predictor (7 endpoints), Copilot (5 more handlers), Evidence classification, Drafting staging, upload AI analysis all migrated. Audit Link Coverage now ~78% (36-row granular count) — see `docs/architecture/MIGRATION_CANONICAL_AI_ADOPTION_REPORT.md`. Remainder: `MIGRATION-001`/`002`. |

## Mission Migration (2026-08-03) — MIGRATION missions

Founder's Master Prompt: "Canonical AI Infrastructure Adoption" — closes most of `LEDGER-004`/
`ATLAS-005`/`ATLAS-006`/`SENT-004`. Full report:
`docs/architecture/MIGRATION_CANONICAL_AI_ADOPTION_REPORT.md`.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| MIGRATION-001 | Migrate `main.py::ask_agent` (core RAG Q&A, Copilot's `pravno_pitanje` delegates here) onto explicit `case_context()` + a dedicated audit action | 1 | none (mechanical, but architecturally deep/complex) | Large | **DONE (2026-08-03, Project Phoenix)** | Mission Migration's own "too large/complex" characterization corrected — Phoenix's re-investigation found it a flat, single-wrap-point function. `routers/copilot.py::_handle_pravno_pitanje` now wraps the `ask_agent` delegation in `case_context(module_name="ask_agent", operation_name="pravno_pitanje")` + `log_action(action="copilot_pravno_pitanje", ...)` on success. See `PHOENIX_RELIABILITY_FAILURE_RECOVERY_REPORT.md` Phase 8. |
| MIGRATION-002 | Migrate `drafting/`'s `_drafting_generate` (deep GPT call) and `routers/drafting.py::analiza` (`ask_analiza`) | 2 | none (mechanical, multi-layer) | Medium-Large | **DONE (2026-08-03, Project Phoenix)** | Same correction as MIGRATION-001 — both turned out to be 1-2 call sites, not a deep package. `routers/drafting.py::nacrt` and `::analiza` now wrapped in `case_context()` + `log_action("drafting_nacrt"/"drafting_analiza", ...)`. `nacrt`'s new audit entry fires independently of the pre-existing `_stage_draft_for_review` entry (two distinct points, not a duplicate). See Phase 8. |
| MIGRATION-003 | Re-verify Smart Intake extraction's audit/case-context status | 3 | none | Small (verification) | **NEEDS_SCOPING — deferred a 2nd time, different reason this time** | Re-investigated by Project Phoenix (`2026-08-03_phoenix_migration_remainder_INVESTIGATION.md` §3): confirmed reliability is excellent (best of the 3 deferred items — genuine durable job queue, tested reaper) but migration difficulty is genuinely Medium, not mechanical like the other two — its AI calls run inside a background worker loop with no HTTP-request-scoped correlation_id to inherit; needs a deliberate design decision (job `id` as correlation_id, or mint+store a new one) before wiring. Not deferred out of caution this time — deferred because it needs a real design call. |

## Project Phoenix (2026-08-03) — PHOENIX missions

Founder's Master Prompt: "Enterprise Reliability & Failure Recovery Validation" — closes
`MIGRATION-001`/`002` (above), re-verifies Project Sentinel's original 12-scenario investigation
against current code, and finds/fixes the single most severe reliability defect discovered across this
entire engagement: the durable-outbox Event Bus could not actually detect or retry a handler failure —
`asyncio.gather(..., return_exceptions=True)` in `publish_async()` swallowed every handler exception
before `dispatch_pending_events()`'s own retry-tracking `except` block ever saw it, meaning migration
073's `dispatch_attempts`/`last_error` columns were dead code for this failure class and a
permanently-broken `on_genome_updated`/`on_predmet_kreiran` handler was marked `dispatched_at` (false
success) after exactly one silent failure. Full report:
`docs/architecture/PHOENIX_RELIABILITY_FAILURE_RECOVERY_REPORT.md`. Investigations:
`decisions/2026-08-03_phoenix_reverify_sentinel_INVESTIGATION.md`,
`decisions/2026-08-03_phoenix_event_search_memory_chaos_INVESTIGATION.md`,
`decisions/2026-08-03_phoenix_db_transaction_chaos_INVESTIGATION.md`,
`decisions/2026-08-03_phoenix_migration_remainder_INVESTIGATION.md`.

Also closed **MIGRATION-001** and **MIGRATION-002** (see above) — both correctly identified by Mission
Migration, both migrated this mission after Phoenix's own re-investigation corrected Migration's "too
risky this session" caution.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| PHOENIX-001 | Event Bus dead-letter rows have no operator-facing surface | 1 | none | Small-Medium | TODO | `MAX_DISPATCH_ATTEMPTS=5` dead-lettering (this mission's own new mechanism) durably records a permanently-failing handler's row with a `"DEAD_LETTER after N attempts: ..."` marker and a `logger.critical` line, but nothing alerts a human — an engineer must know to query the `events` table. A cron digest or a `proactive_alerts` row (mirroring `on_document_job_failed`'s own precedent) would close this cheaply, using an existing pattern rather than new infrastructure. |
| PHOENIX-002 | `nightly_alert_insert_failed` audit entries have no operator-facing surface | 2 | none | Small | TODO | Same shape as PHOENIX-001 — this mission's fix makes a lost critical alert durably recorded (`shared/audit_immutable.py`), but no human is notified. Same fix pattern applies (cron digest, or a `proactive_alerts` row for the on-call engineer/founder, not the affected lawyer). |
| PHOENIX-003 | Re-verify Timeline, Deadlines, Firm Brain, Anthropic, and File Storage failure-recovery posture | 3 | none | Medium (investigation) | **PARTIALLY RESOLVED (2026-08-04, Mission Keystone)** | Anthropic resolved: confirmed zero usage anywhere in the codebase (no SDK import, no key var, no model string) — reclassified N/A, not a gap. File Storage, OCR timeout, Timeline/Deadlines/Firm Brain failure posture still not independently re-verified by any mission — see `KEYSTONE_FINAL_READINESS_REPORT.md`'s Risk Register item K-14. |
| PHOENIX-004 | Pinecone ghost-vector cleanup on the aborted-upload path | 4 | none | Small-Medium | TODO | Known, named since Project Sentinel (`api.py:4249-4251`'s own comment) — a vector ingested before a `predmet_dokumenti` insert failure is never cleaned up. Not attempted this mission (different scope: request-path reliability, not post-hoc cleanup) but now explicitly tracked as its own item rather than living only as an inline comment. |

## Mission Keystone (2026-08-04) — Final Pre-Beta Readiness Validation

Founder's Master Prompt: "Final Pre-Beta Readiness Validation" — the 6th and final mission of this
session's engagement. Explicit mandate to challenge, not confirm, prior work. Fresh, full-system
re-measurement (Phase 2) found every prior mission's coverage metric was computed against a narrower
scope than reality: an unfiltered grep found 76 AI call sites across 55 files (vs. the ~36-row
hand-curated inventories Atlas/Ledger/Migration/Phoenix all used), revising Audit Link Coverage down to
~39% system-wide. Found and fixed the multi-worker Event Bus duplicate-dispatch race (production runs 4
gunicorn workers, each with an independent unclaimed-poll `DispatchLoop`) via a new `claim_pending_events`
RPC mirroring migration 073's proven `claim_intake_job` pattern. Found one High-severity, unresolved
finding: `routers/gdpr.py::gdpr_delete_account` doesn't cascade to Pinecone vectors/Storage files —
**narrowed from an initial Critical framing by Mission Olympus's 2026-08-04 backtest**, which found the
case/client/document retention is already disclosed with a stated legal basis (Zakon o advokaturi), not a
silent gap; the real open gap is specifically vectors/storage. Corrects a prior mission's inaccurate
characterization of `services/retention_service.py` as "the GDPR deletion mechanism" (it only does
operational-log TTL cleanup). Final Beta Gate decision: 🟡 **READY WITH ACCEPTED RISKS**, conditional on
the founder explicitly accepting the GDPR gap and Strategy Engine's ungrounded confidence-percentage risk
for a closed beta. Full report:
`docs/architecture/KEYSTONE_FINAL_READINESS_REPORT.md`. Investigations:
`decisions/2026-08-04_keystone_phase1_architecture_freeze_INVESTIGATION.md`,
`decisions/2026-08-04_keystone_phase2_metrics_INVESTIGATION.md`,
`decisions/2026-08-04_keystone_phase3_golden_path_INVESTIGATION.md`,
`decisions/2026-08-04_keystone_phase4_chaos_INVESTIGATION.md`,
`decisions/2026-08-04_keystone_phase5_ai_quality_INVESTIGATION.md`,
`decisions/2026-08-04_keystone_phase6_security_INVESTIGATION.md`,
`decisions/2026-08-04_keystone_phase7_beta_user_simulation_INVESTIGATION.md`.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| KEYSTONE-CRITICAL | GDPR account deletion doesn't cascade to Pinecone vectors or Storage files (narrowed from the whole case/client/document set — see K-1's Mission Olympus correction) | 0 | Founder decision on whether/how to purge vectors/storage, or extend the existing disclosure to cover them | Medium | **FOUNDER DECISION REQUIRED** | See Risk Register item K-1 (now High, not Critical). Not a "clearly localized" fix — touches real data irreversibly, needs explicit scope sign-off before implementation. |
| KEYSTONE-001 | Voice Orchestrator (`services/voice_orchestrator.py`) bypasses the canonical AI wrapper entirely | 1 | none | Medium-Large | TODO | Raw WebSocket to OpenAI's Realtime API — no correlation_id/case_context/provenance capture for voice sessions. Breaks the "100% wrapper coverage" claim for this one feature. |
| KEYSTONE-002 | Genome → Strategy/Risk/Tasks connectivity gap; Memory Graph is fully isolated (Firm Brain has one narrow real consumer, corrected by Mission Olympus — see below) | 2 | Founder decision — is deeper auto-connection desired, or is lawyer-initiated by design? | Large (architecture) | NEEDS_SCOPING — founder decision | The 9-step Case Pipeline auto-fires once at case creation (before documents exist) and never re-runs; Strategy Engine output isn't persisted for Timeline/Dashboard. Not a bug — a product-design question. |
| KEYSTONE-003 | Document classification and Genome refresh background-task failures are log-only, no durable audit/alert | 3 | none (proven pattern exists) | Small-Medium | TODO | Apply Phoenix's own nightly-alert retry+durable-audit pattern (`nightly_alert_insert_failed`) to these two background paths — same shape, not new infrastructure. |
| KEYSTONE-004 | Strategy Engine's litigation win-probability % is raw, ungrounded LLM output with zero validation | 1 | Founder decision — apply Deterministic Intelligence Framework pattern? | Medium-Large | TODO — highest-priority non-Critical item | The single riskiest AI-quality finding in the app: no backend confidence computation, no citation-grounding check, on the number a lawyer cares about most. |
| KEYSTONE-005 | Genome analysis not flagged stale after a case-defining field edit | 4 | none | Small (UX) | TODO — explicitly UX, deferred past this mission | Editing `tip`/`rizik` gives instant save confirmation but the AI analysis below silently stays unmarked as potentially outdated. |
| KEYSTONE-006 | Genome background-regen watcher silently times out after 90s with no error state | 5 | none | Small (UX) | TODO — explicitly UX, deferred past this mission | Reverts to default hint text with no failure signal; manual refresh still works. |
| KEYSTONE-007 | Run `migrations/091_event_bus_atomic_claim.sql` in production | 1 | Founder runs migrations himself | Small | NEEDS_SCOPING — founder action | Until run, the multi-worker Event Bus duplicate-dispatch race (this mission's code fix is inert without it) remains exactly as exposed as before this mission. |
| KEYSTONE-008 | Predmet-creation endpoint has no idempotency key; Client creation uses the older `audit_log` mechanism with no dedup | 4 | Founder decision on idempotency-key design | Medium | NEEDS_SCOPING | Client-side retry could double-create a case; rapid double-submit on client creation isn't deduped. |

## Mission Olympus (2026-08-04) — Enterprise AI Governance Layer

Founder's Master Prompt: "Enterprise AI Governance Layer" — builds a permanent, standing 6-layer,
19-new-agent Enterprise Review Board (`AI_GOVERNANCE_ARCHITECTURE.md`) that reviews *completed changes*
before merge, complementing (not duplicating) the pre-existing 15-role feature-development organization
(`ORG_CHART.md`). 21 roles actively participate (19 new + Agents 05/14 reused by reference); 34 roles
total across both organizations. 8 required governance documents written:
`AI_GOVERNANCE_ARCHITECTURE.md`, `AGENT_CATALOG.md`, `AGENT_RESPONSIBILITY_MATRIX.md`,
`REVIEW_PIPELINE.md`, `QUALITY_GATES.md`, `AGENT_COMMUNICATION_PROTOCOL.md`,
`DECISION_ESCALATION_POLICY.md`, `GOVERNANCE_METRICS.md`.

Per the founder's own explicit closing instruction, **not wired into mandatory nightly use yet** — first
backtested against 6 historical missions (Nexus, Sentinel, Atlas, Ledger, Phoenix, Keystone). Result: 14
of 19 new agents confirmed WOULD CATCH a real historical finding; 3 honestly have no historical precedent
(LEC v1 benchmark corpus empty; no mission ever measured performance/cost; Legal Domain Expert never
existed before); 1 partially validated. The backtest itself produced **3 genuine corrections to
already-published reports** — Keystone's "Firm Brain fully isolated" claim was wrong (a real consumer
exists, `api.py::_fetch_firm_memory_context`), Keystone's K-1 GDPR finding was more nuanced than reported
(the retention is disclosed with a stated legal basis; the real gap is narrower — Pinecone/Storage
specifically), and Agent 18's own charter had a real gap (no query-completeness check), fixed during
validation. Full report: `docs/architecture/OLYMPUS_BACKTEST_VALIDATION_REPORT.md`. Investigations:
`decisions/2026-08-04_olympus_backtest_engineering_board.md`,
`decisions/2026-08-04_olympus_backtest_ai_legal_board.md`,
`decisions/2026-08-04_olympus_backtest_product_platform_board.md`.

**Recommendation, phased, not blanket**: 12 agents (17, 18, 19, 20, 23, 26, 27, 28, 29, 30, 31, 33) ready
for mandatory use now; Agent 21 partially ready (1 of 3 sub-domains validated); Agents 24, 32 enabled
informational-only until they have real baseline data; Agent 25 in a calibration period.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| OLYMPUS-001 | Wire the 12 backtest-validated agents (17,18,19,20,23,26,27,28,29,30,31,33) into the actual nightly mission workflow | 1 | Founder decision on rollout timing | Medium | TODO — founder decision | Currently documented, charter-complete, and backtest-validated, but not yet actually invoked as a standing gate on any real change since this mission ended. |
| OLYMPUS-002 | Populate `evaluation/lec/` with real, sourced documents so Agent 24 (AI Evaluation & Benchmark) has something to measure | 2 | Founder — explicitly the founder's own stated task, not fabricable by an agent | Medium | NEEDS_SCOPING — founder action | `evaluation/lec/annotations.json` ships empty by design ("Nemam ground truth, dakle nemam benchmark. To je naučno ispravno.") — until populated, Agent 24 can only validate its own harness, not measure real precision/regression. |
| OLYMPUS-003 | Establish a first performance/cost baseline so Agent 32 has something to compare future changes against | 3 | none (Atlas's `ai_forensics.latency_ms` already has raw data to start from) | Medium | TODO | Zero historical mission ever measured latency/throughput/cost — Agent 32's first invocations should establish a baseline, not gate a merge against nothing. |
| OLYMPUS-004 | Resolve Agent 16's cross-board sequencing gap (Consulted-relationship ordering in Phase G1) before operationalizing the pipeline for real | 4 | none | Small | TODO | Noted in the Director's own charter and `REVIEW_PIPELINE.md` — not blocking, but a real scoping gap for whoever wires this pipeline into an actual workflow. |
| OLYMPUS-005 | Exercise Agent 21's untested sub-domains (cross-version stability, cross-module contradiction) on a real future case | 5 | none | Medium | TODO | Internal-consistency sub-domain is validated; the other two have zero historical exercise — first real invocation should treat findings as provisional. |

## Program Alpha (2026-08-04) — Eliminate Entire Classes of Defects

Founder's Master Prompt 001: "Eliminate Entire Classes of Defects" — not a bug-hunt, a search for the
architectural patterns that let a given class of bug recur. 6 parallel domain investigations mapped 38
business decisions platform-wide; 11 were confirmed duplicates. **6 duplicate classes eliminated this
mission** (proactive alert creation, embedding-model identifier, Court Predictor confidence, AI-call audit
trail, correlation ID, correlation-ID minting) — 30 combined duplicate/competing implementations reduced
to 6 canonical ones. Net codebase change: 29 files, +331/-603 lines (net -272), 2 files deleted entirely.
**First real, live exercise of the Mission Olympus governance layer** (Phase 9): 3 fresh agents
(Architecture Review, Reliability & Chaos, Backend Engineering Review) reviewed the actual diff and found
4 real, valid issues — all fixed in the same pass before this mission closed (an incomplete
embedding-model migration missing 4 more live call sites; a misleading code comment overstating what 2 of
3 Event Bus handlers' new `raise` actually does; a real reliability defect where the canonical alert
function's internal retry could compound with the durable-outbox batch loop and cause duplicate
processing under a sustained outage). Full report: `docs/architecture/CANONICAL_ARCHITECTURE_REPORT.md`.
Also: `BUSINESS_LOGIC_INVENTORY.md`, `SOURCE_OF_TRUTH_REGISTRY.md`, `DUPLICATE_DECISION_REPORT.md`,
`CANONICAL_MIGRATION_PLAN.md`, `SYSTEM_HARDENING_REPORT.md`, `ARCHITECTURAL_DEBT_REGISTER.md`.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| ALPHA-001 | `api.py::_require_auth`'s request-context stamp is inert for 11 endpoints due to `asyncio.to_thread` context-isolation (empirically confirmed) | 1 | Benchmark `_verify_token`'s actual CPU cost first | Medium | TODO | Correlation-id still works for these endpoints (middleware sets it before the thread hop); `user_id`-in-context does not. Found during this mission's own item-8 implementation, not the original diagnostic. |
| ALPHA-002 | SMTP connection/auth boilerplate (5 independent copies) — narrower, correctly-scoped version of the abandoned "consolidate all SMTP" item | 2 | none | Small-Medium | TODO | Message *construction* correctly differs per caller (attachments, Reply-To, multipart shape) and must stay caller-owned; only the `ehlo()`/`starttls()`/`login()` boilerplate is a genuine duplicate. |
| ALPHA-003 | Two independent document-classification taxonomies (`shared/intake_classify.py` 13-type vs. `routers/evidence.py` 9-type), held together today only by write-order sequencing | 1 | Founder decision — which taxonomy wins, or a mapping layer | Large | NEEDS_SCOPING — founder decision | Critical-tier finding, correctly deferred: fragile under this mission's own stress-test framing (concurrent workers), but needs a real design decision, not a mechanical migration. |
| ALPHA-004 | Two overlapping entity-extraction pipelines (`shared/intake_extract.py` vs. Evidence's `ai_tags`) | 3 | none | Medium | TODO | Lower priority than ALPHA-003 — no active correctness bug today, only duplicated AI cost and drift risk. |
| ALPHA-005 | Two "firm memory for AI" implementations, one live-but-cruder, one dead-but-more-capable (`api.py::_fetch_firm_memory_context` vs. `routers/firm_memory.py::kontekst_za_ai`) | 1 | Founder decision — is expanding Copilot's context (judge/client memory) wanted now | Medium | NEEDS_SCOPING — founder decision | Critical-tier finding; correctly gated on a product decision since the fix is a real behavioral change (more AI context), not a pure refactor. |
| ALPHA-006 | No canonical Pinecone namespace registry — a document can be ingested into a namespace nothing ever queries | 2 | Founder/design decision — constants module vs. DB-backed registry | Medium | NEEDS_SCOPING | Real "write success, permanently orphaned data" defect class, trivially reachable via `auto_discovery.py`'s free-text namespace field. |
| ALPHA-007 | "Critical deadline" threshold duplicated with 2 different values across ≥6 files | 4 | Resolve `ccc.py`'s 30-day-window discrepancy first | Small-Medium | NEEDS_SCOPING | Needs a judgment call (deliberately different concept vs. real inconsistency) before mechanical extraction. |

## Program Beta (2026-08-04) — Deterministic AI & Evidence-First Architecture

Founder's Master Prompt 002: "Eliminate Entire Classes of AI Reasoning Defects" — not a mission to improve
AI, a mission to redefine its role. Core principle: "Model nije izvor istine. Model je samo izvršilac.
Izvor istine je platforma." 5 parallel domain investigations inventoried every AI operation in the
platform (Upload/OCR/Extraction, Genome/Memory/Firm Brain, Legal Reasoning/Strategy/Court Predictor,
Copilot/Briefing/Drafting, Search/Tasks/Alerts/Dashboard). Single most severe finding: Strategy Engine's
litigation-percentage has **4 independent, unreconciled raw-LLM percentage generators** for one
conceptual value — worse than Court Predictor's own pre-fix state, and a materially more precise
diagnosis of the pre-existing `KEYSTONE-004` entry (now superseded by `PROGBETA-001` below).

**3 bounded canonicalizations implemented and shipped** (deterministic-derivation pattern, now proven
4× independently in this repo): Evidence Vault `snaga` derived from `_lociraj_tvrdnju`'s already-computed
grounding result instead of a hardcoded constant; Compare docs (the only AI call in the platform with
zero provenance/evidence-validation/UI-trust-signal) wrapped in `case_context()` + a new
`validate_dok_reference()` DOK-XX existence check + symmetric UI signal; Strategy Engine's cross-step
`sistemsko_upozorenje` moved from LLM-decided to code-computed, overriding the LLM's output in both
directions.

**Second live exercise of the Mission Olympus governance layer** (Phase 10, the founder's own 9 mandatory
named agents + Reliability & Chaos = 10 fresh, independent reviewers): 1 clean APPROVED (Security Review),
8 APPROVED WITH CONDITIONS, 1 DEGRADED (AI Quality Auditor — independently corroborated by AI Grounding).
Real, convergent findings across reviewers, all fixed in the same pass: Evidence Vault's `_snaga_iz_
lokacije` could over-claim confidence for too-short (spurious match) or too-long (only-prefix-verified)
claims — bounded to [20,100] chars; Strategy Engine's determinism fix had no guard against off-spec
`confidence` values and conflated JSON-parse failures with genuine low-confidence signal — both fixed;
Compare's evidence-check widened to cover `kontradikcije`/`razlike_kljucne`, not just `koji_je_jaci_dokaz`;
`_evidence_check`'s shape normalized to match `verify_genome()`'s contract; the whole block moved inside
its own fail-soft try/except after a real TypeError risk was found; Evidence Vault's UI gained a grounding
tooltip and Compare's UI gained a positive `approve` confirmation, closing 2 real backend-correct-but-
not-user-visible gaps. **One self-correction found by the review itself**: this mission's own deferred-item
IDs (`BETA-001`..`005`) collided with unrelated missions' existing IDs in this file — renamed to
`PROGBETA-00X` throughout. Full reports: `docs/architecture/AI_CANONICAL_ARCHITECTURE.md`,
`AI_DECISION_GRAPH.md`, `EVIDENCE_CHAIN_REGISTRY.md`, `CONFIDENCE_MODEL_SPECIFICATION.md`,
`AI_REASONING_PIPELINE.md`, `HALLUCINATION_ELIMINATION_REPORT.md`, `MODEL_INDEPENDENCE_REPORT.md`,
`AI_SYSTEM_HARDENING_REPORT.md`. Deferred-item detail: `ARCHITECTURAL_DEBT_REGISTER.md`.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| PROGBETA-001 | Strategy Engine's 4 independent litigation-percentage generators (supersedes `KEYSTONE-004`) | 1 | New signal wiring — VKS-specific search + `case_patterns` firm-history query, neither exists in `strategija.py` today | Large | TODO — highest-priority open item | A shared `compute_litigation_score()` (Court Predictor's proven pattern) consumed by all 4 call sites; blocked on adding the 2 missing deterministic input signals first. |
| PROGBETA-002 | RAG provenance (`retrieval_meta`) never threaded into `case_context()`'s already-connected `retrieval_query`/`retrieved_context_ids` params, ~15+ call sites | 2 | none — mechanism exists end-to-end | Medium (wide, not deep) | TODO | Confirmed independently 3× same day (Program Alpha + 2 Program Beta forks). Highest-leverage single fix in the platform; deserves its own fully-tested pass given the number of heterogeneous call sites. |
| PROGBETA-003 | `services/quality_gate.py`'s citation-verification mechanism not reused by Strategy Engine or Genome | 2 | Confirm portability against real integration code at both new call sites | Medium | NEEDS_SCOPING | Mechanism is generic by construction (operates on arbitrary text), but reuse-feasibility wasn't confirmed by reading actual integration code — don't assume, verify first. |
| PROGBETA-004 | Genome `heatmap`/`najslabija_tacka.kriticnost` — no deterministic post-processing (same defect class `compute_snaga_score` was built to fix, unaddressed here) | 3 | Genome extraction schema redesign — no already-extracted per-dimension factor list exists to aggregate from | Medium-Large | NEEDS_SCOPING | Larger than the initial fork finding suggested: needs new extracted factors, not just a new post-processor function. |
| PROGBETA-005 | Copilot akcija handlers (`_handle_akcija_rok` etc.) extract fact (`datum_iso`) and inference (`vaznost`) via one undifferentiated call, no source marker | 3 | JSON schema change across 4 handler functions | Medium | TODO | Writes directly to `predmet_hronologija` (system-of-record) — higher stakes than Strategy Engine's un-persisted prose, shouldn't be rushed. |
| PROGBETA-006 | Evidence Vault `snaga` fix makes a previously-dead `risk_engine.py` risk-scoring branch reachable, no backfill for pre-fix `predmet_dokazi` rows | 2 | Founder decision — run a backfill job, or accept documented vintage-skew as self-healing | Small (as a migration) | NEEDS_SCOPING — found by Olympus Faza 10 governance review (Evidence Integrity) | Bounded, self-healing over time as documents are re-uploaded/re-classified — not a correctness bug, a consistency transition worth an explicit decision. |
| PROGBETA-007 | `compare_docs`'s `dok_res` query has no explicit `.order()`; response labels assume alignment with `n1`/`n2` | 4 | none | Small | TODO — found by Olympus Faza 10 governance review (AI Grounding); pre-existing, not introduced by Program Beta | Doesn't affect `validate_dok_reference()`'s own correctness (set-based), but undermines the "known documents" trust story — one sort call away from closed. |
| PROGBETA-008 | `DokazReq.snaga` has no enum/`Literal` constraint on manual entry | 5 | none | Small | TODO — found by Olympus Faza 10 governance review (Evidence Integrity); pre-existing, now more consequential | Simple fix (`Literal["jaka","srednja","slaba"]`) when picked up; only affects the low-volume manual-entry path. |

## Program Gamma (2026-08-04) — Canonical Decision Engine

Founder's Master Prompt 003: "Eliminate Entire Classes of Decision Fragmentation" — the third and most
architecturally ambitious lens of the night. Not code duplication (Alpha), not AI-reasoning defects
(Beta), but whether a BUSINESS OR LEGAL DECISION is independently produced by more than one module. 5
parallel domain forks, explicitly built to walk the actual consumer layers Alpha's and Beta's own domain
scoping never reached, found the single largest finding of this entire multi-mission session: "next
recommended action" has **18 independent, unreconciled producers** platform-wide (full enumeration:
`ARCHITECTURAL_DEBT_REGISTER.md`'s `GAMMA-001`), extending the founder's own already-open
`G030_NEXT_ACTION_DECISION_MODEL.md` (2026-07-22, 3 known authorities) with 16 more, while also confirming
one of G-030's original 3 (Matter Intel) was resolved by an intervening mission and no longer belongs on
the list.

**5 bounded fixes implemented** (one live production bug + 4 canonicalizations): `case_intelligence.py`'s
"next step" endpoint was almost certainly 500ing on every call (wrong `proactive_alerts` column names,
same mistake class already fixed once elsewhere) — fixed. The proven "referenced entity must exist in
scope" Evidence Chain pattern (Program Beta's `validate_dok_reference`) was generalized to 2 new ID
schemes and wired into 2 more AI-decision endpoints (`evidence_graph.py`, `case_commander.py`'s daily
briefing) that had zero of the 3 Evidence Chain links. 2 "should have been impossible" gaps were closed:
Strategy Engine's `detektovani_konflikti` field (left LLM-decided in the same function where its sibling
field was fixed by Program Beta hours earlier the same day) and Court Predictor's `boja`/`pouzdanost_profila`
(raw LLM output despite each prompt stating a checkable rule). A byte-identical inline formula duplicated
twice in `case_dna.py` was deduplicated.

**Second live exercise of Mission Olympus's full 10-agent governance board this mission** (10 fresh
reviewers: Chief Systems Architect, Decision Consistency Auditor, Architecture Review, AI Governance,
Evidence Integrity, Security, Reliability, Workflow Integrity, Legal Domain Expert, Metrics Guardian). No
BLOCKED verdicts — 1 clean PASS, 1 clean APPROVED, 8 APPROVED WITH CONDITIONS. **Strongest convergence
signal (3 independent reviewers converging on the same defect, automatically Critical per the mission's
own rule)**: the Synthesis prompt still named the exact 2 conflict examples the new deterministic code
hard-coded, risking duplicate-worded findings, and one of the 2 checks risked false positives on legally
coherent scenarios — fixed (prompt updated mirroring Program Beta's own precedent, wording softened,
litigation-vs-transactional category-error guard added). **Second convergence (2 reviewers)**:
`_evidence_check` was computed for both new endpoints but never surfaced in the frontend — fixed (toast +
inline marker + a persisted-reload bug where the flag was recoverable only for the instant right after
generation, then permanently lost). Every other individual finding (an attribution-check gap, a
numeric-string coercion gap, missing Sentry visibility, an internally-inconsistent "12+" producer count
across 3 documents, a missing debt-register entry, an overclaimed "fully specified" design sketch) was
fixed in the same pass. 38 new tests across 6 files, full suite green.

**Headline deliverable**: `docs/architecture/DECISION_REGISTRY.md` — 13 canonical decisions formally
catalogued with contracts for the first time (a pattern this codebase has organically re-invented 4 times
since 2026-07-18), every known fragmented decision catalogued alongside them (not hidden), plus a
registration-rule process convention + `tests/test_decision_registry_completeness.py` as the practical,
honestly-scoped guardrail — explicitly NOT claiming a CI/static-analysis gate that doesn't exist in this
repo (verified, not assumed). Full reports: `docs/architecture/CANONICAL_DECISION_ENGINE.md`,
`DECISION_GRAPH.md`, `DECISION_CONTRACTS.md`, `DECISION_CONSUMER_MAP.md`, `DECISION_CONSISTENCY_REPORT.md`,
`DECISION_MIGRATION_REPORT.md`, `DECISION_HARDENING_REPORT.md`.

| ID | Mission | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| GAMMA-001 | "Next recommended action" has no single owner — 18 independent producers (full enumeration in `ARCHITECTURAL_DEBT_REGISTER.md`) | 1 | Founder product decision — which of 18 surfaces survive as distinct UI presentations of one shared answer | Large (product + implementation) | NEEDS_SCOPING — founder decision | Design fully specified (`CANONICAL_DECISION_ENGINE.md`'s `compute_next_action()` sketch, itself flagged by governance review as a starting shape not a complete per-producer spec) — implementation blocked on the founder call, not on design work. |
| GAMMA-002 | `routers/cio.py:148` reads Genome's raw `nedostaje.hitnost` instead of canonical `identify_case_problems` | 3 | none | Small | TODO | Concrete instance of the registry's own registration-rule gap, found (not created) during Phase 6 consumer mapping. |
| GAMMA-003 | `matter_intel.py`'s Uncertainty Dashboard + Pre-Flight Check don't use canonical risk engine, zero Evidence Chain | 2 | none | Medium | TODO | 2 of the 4 independent "case strength/readiness" producers found this mission, in the same file as the canonical source, not calling it. |
| GAMMA-004 | Case Commander's other 3 endpoints (`/analiza`, `/quick-check`, `/checklist`) have zero Evidence Chain | 2 | none | Medium | TODO | Same DC-009 pattern proven cheap to close for `_cross_case_analiza`, just not yet done for these 3. |
| GAMMA-005 | `case_intelligence.py::case_intelligence_briefing` has no provenance wrapping | 3 | none | Small | TODO | The live bug was fixed this mission; provenance wrapping was deliberately not added in the same pass to keep the fix bounded. |
| GAMMA-006 | `ask_agent`'s recommendation is case-specific in fact, case-agnostic in the audit trail (`predmet_id=None`) | 3 | none | Small | TODO | Distinct from `PROGBETA-002` — about `predmet_id` itself, not RAG provenance. |
| GAMMA-007 | No CI/static-analysis guardrail against a new undeclared decision | 3 | Confirm what CI (if any) exists on this repo first | Medium | NEEDS_SCOPING | Honestly scoped in `DECISION_HARDENING_REPORT.md` — a `scripts/audit_decision_registry.py` heuristic (same style as `audit_routers.py`) recommended, not a hard gate. |
| GAMMA-008 | Case Pipeline step 6 is a free, automatic, unlabeled shadow of the paid `hearing_cc.py` Hearing Command Center | 2 | Product decision — label/reconcile/retire the lite version | Medium | NEEDS_SCOPING | Both paths reachable and both run today — worse than dead code, an unlabeled duplicate a lawyer could genuinely rely on. |
| GAMMA-009 | Document/case readiness has 2 structurally incompatible representations (`quality_gate` vs. Pravni Revizor), no shared vocabulary | 2 | Design decision — which representation wins, or a mapping layer | Medium-Large | NEEDS_SCOPING | Reachable by an ordinary user workflow, not hypothetical. |
| GAMMA-010 | "How urgent is this" has 6+ independently-defined vocabularies, incl. a literal field-name collision (Genome vs. Copilot PLAN `nedostaje`) | 3 | Vocabulary decision (which enum wins, or a mapping layer) | Medium | NEEDS_SCOPING | Same discipline as `ALPHA-003`'s taxonomy question — not a blind rename. |
| GAMMA-011 | `shared/genome_validator.py`'s module docstring/name no longer matches its contents (3 of 6 functions are Genome-agnostic) | 5 | none | Small | TODO — found by Olympus Faza 10 governance review (Chief Systems Architect) | Recommended trigger: whenever a 4th caller of the reference-validation family appears, extract to `shared/reference_validation.py`. |

## Explicit exclusions from autonomous scope (per the Master Prompt's own Stop Conditions)

- Any change requiring a production schema migration (per this project's standing rule, migrations
  are drafted for the founder to review and run himself — never auto-applied, and per the Master
  Prompt, a schema migration requirement is itself a stop condition, not just an execution note).
- The Security Governance Framework / Epic B rate-limiting chain — explicitly mid-founder-review,
  parked at Revision 2, ACTIVE BLOCKER. Not touched tonight under any mission.
- Intake system convergence at the backend/API level — explicitly rejected by decision record
  (`decisions/2026-08-02_intake_convergence_DECISION_RECORD.md`); not reopened without a new
  founder-supplied reason to revisit.

## Program Intake, Sprint 001 (2026-08-04) — Bulletproof Document Intake Foundation

Founder's fourth Master Prompt of the night, narrower scope than Alpha/Beta/Gamma by design: only 5 named
agents active (Chief Systems Architect, Reliability & Failure Recovery Engineer, Evidence & Consistency
Auditor, Security & Trust Auditor, Code Quality/Refactoring Reviewer), everyone else STANDBY, no Mission
Olympus governance review phase for this sprint. Goal: UPLOAD → OCR → VALIDACIJA → STORAGE becomes canonical,
deterministic, verifiable, production-reliable — no new AI capability, screens, panels, or agents.

**3 parallel forensic forks** confirmed, before any implementation, that **all three upload pipelines are
live and reachable in production today** — a factual contradiction between two forks (whether Smart Intake's
frontend wiring exists) was personally resolved by direct grep of `static/vindex.js`, not left ambiguous.
This raised the real-world severity of every finding: nothing in this sprint's scope was theoretical.

**2 critical fixes implemented and regression-tested** (2492 tests, zero regressions): Pipeline A now
preserves the original uploaded file in encrypted Supabase Storage (was never stored anywhere before —
tempfile deleted after OCR, `storage_path` a non-dereferenceable label); `IntakeWorker._process()`'s silent
false-success bug fixed — a crash between `create_document()` and `write_processing_outcome()` used to cause
a job to be marked `completed` with zero entities and zero review-queue escalation, indistinguishable from a
genuine success, inside the exact subsystem Project Phoenix once called "the single most reliable
AI-adjacent subsystem" in the engagement. **3 supporting fixes**: `dokument_view` audit logging wired
(plumbing already existed on both ends, only the call site was missing); 2 `predmet_dokumenti` writers that
silently fell to a misleading `na_cekanju` DB default forever now write explicit, honest `status` values;
an approved-AI-draft promotion writer that left `tip_dokaza` permanently NULL now sets it deterministically
(`"podnesak"`, reusing existing vocabulary — no new AI call).

**Full canonicalization of the 3-pipeline topology was explicitly not attempted** — consistent with, and now
doubly confirmed by, the standing exclusion above (`2026-08-02_intake_convergence_DECISION_RECORD.md`):
Pipeline A and Pipeline B/C serve genuinely different live product flows; collapsing them is a product
decision this sprint's charter does not license making unilaterally. What this sprint delivers is bounded
reliability hardening within the existing topology, honestly characterized as such — not an inflated "fully
canonical" claim.

**8 required deliverables**: `docs/architecture/INTAKE_ARCHITECTURE_REPORT.md`, `INTAKE_FLOW_DIAGRAM.md`,
`INTAKE_SOURCE_OF_TRUTH_MATRIX.md`, `INTAKE_FAILURE_RECOVERY_MATRIX.md`, `INTAKE_DUPLICATE_LOGIC_REGISTER.md`,
`INTAKE_RISK_REGISTER.md`, `INTAKE_TEST_COVERAGE_REPORT.md`, and 4 new entries in
`ARCHITECTURAL_DEBT_REGISTER.md` (`INTAKE-001` through `INTAKE-004`).

| ID | Finding | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| INTAKE-001 | Pipeline C reports `"ok": true` even when the document insert fails after Pinecone ingest already succeeded (ghost vector) | 1 | Product/API-contract decision — partial-success response shape, or split case-creation from document-attach | Medium | NEEDS_SCOPING | Not a safe direct port of Sentinel's hard-fail pattern (case row already created earlier in the same call — a 500 would misreport genuine partial success and risk a duplicate-creating retry). |
| INTAKE-002 | Orphaned encrypted Storage blobs on Pipeline B enqueue failure, no cleanup mechanism | 2 | none | Small-Medium | **DONE (Sprint 002, 2026-08-05)** | Fixed via pre-upload idempotency_key check (skips the Storage write entirely on a known duplicate) + compensating delete on enqueue exception — Sprint 002 Fork C found the trigger was broader than originally scoped (every ordinary duplicate resubmit, not only RPC failure); both are now closed. |
| INTAKE-003 | `intake_jobs.status`'s richer processing lineage discarded entirely at Pipeline C finalize | 3 | Schema/product decision — should case-file views ever surface OCR/classification lineage | Medium | NEEDS_SCOPING | No functional defect today, a foreclosed-future-capability cost. |
| INTAKE-004 | `routers/copilot.py:804` misreports finished wizard-linked/demo documents as eternally pending | 4 | none — Copilot is explicitly forbidden to touch this sprint | Small | TODO | Documented only per this sprint's own forbidden-module list; not fixed. |

## Program Intake, Sprint 002 (2026-08-05) — Atomic Document Lifecycle

Founder's fifth Master Prompt of this multi-session Program Intake arc: "one document, one identity, one
lifecycle, one truth." Same 5-agent-only, no-Olympus-phase pattern as Sprint 001 (Chief Systems Architect,
Reliability & Failure Recovery Engineer, Evidence & Consistency Auditor, Security & Trust Auditor, Database &
Transaction Integrity Reviewer). Same forbidden-module list (OCR quality, Genome, Decision Engine, Strategy,
Copilot, Briefing, Timeline, Search, Alerts, Tasks, Dashboard, Firm Brain).

**3 parallel forensic forks converged independently on the identical root defect** — Pipeline C's finalize
endpoint had an exploitable check-then-act race that could silently duplicate a full legal case (case +
client + deadline + document + Pinecone vectors) under concurrent retry. All 3 forks (atomicity/orphan audit,
transaction-boundary/state-machine, idempotency/replay) found this independently the same day — the strongest
possible internal-consistency signal this session's methodology produces.

**4 fixes implemented and regression-tested** (2512 tests, zero regressions, was 2502 going in): (1) Pipeline
C's duplicate-case race — fixed via `claim_intake_finalize` atomic RPC (migration 092, drafted not applied),
mirroring `claim_intake_job`'s own proven `SELECT...FOR UPDATE SKIP LOCKED` pattern; (2)
`write_processing_outcome()`'s silent exception swallow, which had quietly reopened Sprint 001's own
false-success bug shape through a different door — fixed via a `raise_on_error` parameter used only by
`IntakeWorker._process()`'s two call sites; (3) Pipeline A's orphan-blob exposure, proven wider than known (5
distinct downstream raise sites, zero tracking infrastructure) — fixed via compensating cleanup; (4) Pipeline
B's orphan-blob trigger, proven broader than `INTAKE-002`'s original scope (every ordinary duplicate resubmit,
not only RPC failure) — fixed via a pre-upload existence check plus compensating cleanup on the narrower
true-race case.

**3 new findings deliberately deferred with reasoning** (`INTAKE-005` through `INTAKE-007`,
`ARCHITECTURAL_DEBT_REGISTER.md`): Pipeline A's own Pinecone-ghost-vector risk (same root cause as
`INTAKE-001`, a cross-system compensating action neither pipeline has); `intake_jobs`' dormant intermediate
processing sub-states (real, zero-migration, but observability not consistency); a cluster of
production-replay forensic gaps (no document loss, but real reconstruction blind spots). Also corrected a
stale claim in Sprint 001's own `INTAKE_FAILURE_RECOVERY_MATRIX.md` (`dedup_check` was never real
infrastructure — the actual dedup mechanism is the `idempotency_key` UNIQUE index).

**7 required deliverables**: `docs/architecture/DOCUMENT_LIFECYCLE_ARCHITECTURE_REPORT.md`,
`ATOMICITY_VERIFICATION_REPORT.md`, `STATE_MACHINE_SPECIFICATION.md`, `TRANSACTION_BOUNDARY_ANALYSIS.md`,
`FAILURE_INJECTION_REPORT.md`, `REPLAY_VALIDATION_REPORT.md`, and 3 new `ARCHITECTURAL_DEBT_REGISTER.md`
entries (`INTAKE-005` through `INTAKE-007`, checked against existing prefixes first — no collision).

| ID | Finding | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| INTAKE-005 | Pipeline A's own Pinecone-ghost-vector risk on DB-insert failure after Pinecone success (same root cause as INTAKE-001) | 1 | none — but a genuine new capability (cross-system compensating delete), not a bounded patch | Medium | TODO | Recommended direction: background reconciliation job diffing Pinecone vs. predmet_dokumenti; new scheduled infrastructure, out of this sprint's bound. |
| INTAKE-006 | `intake_jobs.status`'s intermediate processing sub-states (classifying/extracting/matching/dedup_check) declared but never written | 3 | none — zero migration needed | Small | TODO | Real, bounded, optional — observability, not consistency; deferred so as not to dilute this sprint's 4 consistency fixes. |
| INTAKE-007 | Production-replay forensic blind spots (no ocr_used column, no Pinecone→document FK, 2 disconnected fire-and-forget provenance systems, no truncation marker) | 3 | Durable-with-retry infrastructure or new schema columns | Medium | NEEDS_SCOPING | No document loss — a forensic-completeness gap, distinct from and lower-severity than a consistency defect. |

## Program Intake, Sprint 003 (2026-08-05) — Canonical Document Understanding

Founder's sixth Master Prompt of this multi-session Program Intake arc: pivots from "can the system read a
document" (Sprints 001-002) to "does the system understand what it read." Same deliberately narrow charter
shape, tighter still: only 5 named agents active (Chief Systems Architect, Legal Domain Expert, Evidence &
Consistency Auditor, Reliability & Failure Recovery Engineer, Code Quality/Refactoring Reviewer), no Mission
Olympus phase, an even longer STANDBY list than Sprint 001/002 (adds Metrics/Strategy/Voice/Analytics/
Documentation Review to the usual forbidden set). Forbidden to implement: Timeline, Deadlines, Tasks, Alerts,
Genome extensions, Briefing, Copilot, Decision Engine, Search, Firm Brain. Mission's own closing instruction:
optimize for accuracy and trust, not for the count of auto-classified documents.

**3 parallel forensic forks** (classification inventory + duplicate audit; canonical taxonomy + confidence
model design; review-queue audit + edge-case validation) found the platform has **5 independent AI document
classifiers, not 4** as every prior session's tracking assumed — a previously-uncounted 5th classifier
(`api.py::_call_metapodaci`) escaped every earlier `tip_dokaza`-scoped grep because it persists into
`predmet_istorija`, not the field prior forks searched for. **Headline finding**: only 1 of the 5 classifiers
has a genuine confidence-gated escape hatch, and even that one classifier's correctly-flagged "I'm not sure"
signal was being silently erased — Pipeline C's finalize let a SECOND, confidence-blind classifier
unconditionally overwrite an already-flagged-uncertain classification, meaning the platform's one working
instance of "admit uncertainty" never had a chance to reach the permanent case record.

**2 fixes implemented and regression-tested** (2517 tests, zero regressions, was 2512 going in): (1) Pipeline
C finalize no longer schedules the confidence-blind overwrite when Pipeline B's classification was flagged
low-confidence — the honest, uncertain value survives instead of being replaced by an equally unfounded but
more-confident-looking guess; finalize's own response now always surfaces `klasifikacija_nesigurna`/
`nesigurna_polja` explicitly. (2) `GET /jobs/{job_id}` no longer silently presents a stale, pre-finalize
classification as current — a confirmed, permanent, two-different-Serbian-labels contradiction the frontend's
own hardcoded translation map was showing lawyers during Smart Intake review — now flags staleness honestly
instead.

**2 large designs produced, deliberately not adopted in code this sprint**: `CANONICAL_DOCUMENT_TAXONOMY.md`
(10 parent categories reconciling all 4 existing classifier vocabularies + the founder's own example, full
mapping table, every edge case explicitly justified — including a genuine correction to a pre-existing defect
in `intake_classify.py`'s own `enforcement` keyword list) and `CONFIDENCE_SPECIFICATION.md` (a grounding-
verified confidence model, the platform's 4th confirmed instance of the already-proven `compute_*()` pattern,
closing `EVIDENCE_CHAIN_REGISTRY.md` row #5's previously-Broken status with a concrete design). Full adoption
(schema migration + rewiring 5 classifiers to one canonical engine) is correctly out of this sprint's bounded
scope — a large future undertaking, not attempted piecemeal.

**8 required deliverables**: `docs/architecture/CANONICAL_DOCUMENT_TAXONOMY.md`,
`CLASSIFICATION_ARCHITECTURE_REPORT.md`, `CLASSIFICATION_INVENTORY.md`, `CONFIDENCE_SPECIFICATION.md`,
`REVIEW_QUEUE_SPECIFICATION.md`, `DUPLICATE_CLASSIFICATION_REPORT.md`, and 4 new
`ARCHITECTURAL_DEBT_REGISTER.md` entries (`INTAKE-008` through `INTAKE-011`, checked against existing
prefixes first — no collision).

| ID | Finding | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| INTAKE-008 | No confidence-gated review queue on Pipeline A or the 2 ephemeral classifiers (3 of 5 classifiers still silently default to "ostalo" on uncertainty) | 1 | `CONFIDENCE_SPECIFICATION.md` actually implemented | Large | TODO | Majority of live classification volume still has zero uncertainty handling — highest-priority follow-up. |
| INTAKE-009 | `/reklasifikuj` has a code-level concurrency defect — no lock, a double-click races itself | 3 | none — mirrors migration 092's already-proven pattern | Small-Medium | TODO | Low-frequency admin action, doesn't corrupt data, just produces a nondeterministic winner. |
| INTAKE-010 | No cross-row classification-consistency check for same-hash duplicate uploads | 3 | New reconciliation capability | Medium | NEEDS_SCOPING | source_sha256 computed at 3 sites, queried back at 0; no evidence of actual production impact. |
| INTAKE-011 | Phase 7 edge-case findings: OCR-confidence decoupling, no rotation detection, no multi-document/"spis" boundary detection | 3 | OCR/extraction-layer work, explicitly out of this sprint's charter | Medium | NEEDS_SCOPING | "Ne rešavati OCR" — diagnosis only, per the mission's own instruction. |

## Program Intake, Sprint 004 (2026-08-05) — Human Review Orchestration & Automatic Resumption

Founder's seventh Master Prompt of this multi-session Program Intake arc. **Explicit charter departure from
Sprints 001-003: not a research/documentation sprint** — every technical problem found that could be fixed
without a new founder business decision had to be fixed in the same sprint, no backlog for fixable things.
Smallest team yet: 4 agents (Chief Systems Architect, Legal Domain Expert, Reliability & Failure Recovery
Engineer, Evidence & Consistency Auditor), longest STANDBY list yet. Forbidden to implement: OCR, Genome,
Copilot, Strategy Engine, Timeline, Tasks, Search, Dashboard, Firm Brain, Alerts, Voice, Memory Graph.

**Headline finding**: `shared/intake_documents.py::resolve_review_queue_for_job` — a fully-correct function
that marks a review resolved, existing since Sprint 001-era migration 074 — had **zero call sites anywhere in
the codebase**. A document flagged for human review could never leave that state through any live path.
Compounding this: `intake_jobs.status='awaiting_review'` was declared in the schema from day one but never
actually written — every job reached `status='completed'` unconditionally while a separate table
simultaneously claimed the same job still needed review. Two disagreeing truths about the same fact, and
`finalize_intake_job` never checked either signal — it created the case regardless.

**12 findings fixed this sprint** (full list, `HUMAN_REVIEW_ARCHITECTURE_REPORT.md` §2), most consequentially:
wired up the dead `resolve_review_queue_for_job` via a new canonical endpoint; corrected `IntakeWorker`'s
`_tick()` to actually set `awaiting_review` (making finalize's PRE-EXISTING status gate block correctly, zero
new blocking logic needed); added audit logging to both human-decision endpoints (`correct_entity`, the new
resolve endpoint) which previously had none; and — found only as a direct consequence of shipping the backend
fix responsibly — **3 frontend bugs that would have made low-confidence documents poll forever, never appear
on the review screen, and have no button to act on even if they did.** All fixed in the same pass, per this
sprint's own binding rule.

**3 findings deliberately deferred as genuine business decisions** (`INTAKE-012` through `INTAKE-014`): what a
"reject" action should concretely do (vs. the built "confirm as-is" path); direct document-type correction
(blocked on Sprint 003's still-unadopted taxonomy decision); `staging_memory`'s own missing audit trail (a
different subsystem, out of this sprint's object of study).

**7 required deliverables**: `docs/architecture/HUMAN_REVIEW_ARCHITECTURE_REPORT.md`, updated
`REVIEW_QUEUE_SPECIFICATION.md`, `RESUME_WORKFLOW_SPECIFICATION.md`, `AUDIT_PROVENANCE_VERIFICATION_REPORT.md`,
`CONCURRENCY_VERIFICATION_REPORT.md`, `END_TO_END_FLOW_VERIFICATION.md`, `SPRINT_004_MISSION_REPORT.md` (the
sprint's own required 3-section report), and 3 new `ARCHITECTURAL_DEBT_REGISTER.md` entries (`INTAKE-012`
through `INTAKE-014`, checked against existing prefixes first — no collision).

| ID | Finding | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| INTAKE-012 | No "reject" action exists for a low-confidence classification, only "confirm as-is" | 1 | Founder decision — what should rejection concretely trigger | Medium | NEEDS_SCOPING | Real gap in the mission's own named test list; correctly deferred rather than guessed at. |
| INTAKE-013 | No way to directly correct the AI-detected document TYPE itself (only 8 entity fields are correctable) | 2 | Which vocabulary a correction writes to — blocked on Sprint 003's taxonomy adoption decision | Medium | NEEDS_SCOPING | Confirm-as-is already unblocks processing; this only blocks changing an uncertain type. |
| INTAKE-014 | `staging_memory`'s (AI-draft approval) approve/reject endpoints have zero audit logging | 3 | none — same pattern this sprint proved twice | Small | TODO | Different subsystem (drafting, not intake), out of this sprint's chartered scope. |

## Program Intake, Sprint 005 (2026-08-05) — Canonical Document Segmentation

Founder's eighth Master Prompt of this multi-session Program Intake arc. One uploaded file is not always one
legal document — a bundled PDF can contain a podnesak, presuda, prilozi, dokazi, and a punomoćje. This sprint
builds the ONE system that decides how many separate legal documents a single upload actually contains,
before classification runs. Smallest team of this sprint style: 5 agents (Chief Systems Architect, Legal
Domain Expert, Evidence & Consistency Auditor, Reliability & Failure Recovery Engineer, Code Quality/
Refactoring Reviewer). Same binding rule as Sprint 004: every technical problem found within scope that could
be fixed without a new founder business decision was fixed in the same sprint. Governing rule with absolute
priority throughout: never split a PDF incorrectly when there isn't enough evidence — a wrongly-split filing
is worse than one correctly-unsplit bundle.

**Headline finding + build**: `uploaded_doc/extractor.py::extract_pdf()` already built a per-page text list
internally (both born-digital and OCR paths) and discarded it at the final join — the single prerequisite
fact that made a canonical segmentation engine possible without touching how the extractor reads a PDF at
all. Built `shared/intake_segment.py` (pure, zero-I/O, deterministic signal detection + a conservative
combination rule: 2+ strong signals or 1 strong+corroborating auto-splits, thin evidence routes to human
review, nothing silently guessed) and wired it into Pipeline B (`shared/intake_worker.py`, the durable Smart
Intake queue worker) with full per-segment identity (new table `intake_job_segments`, migration `093`) and
per-segment failure isolation (each segment gets its own try/except + bounded in-process retry, one segment's
permanent failure never loses or blocks its siblings).

**3 real bugs found and fixed during this sprint's own testing, not filed for later**: (1) `_find_heading_keyword`
used substring containment, so Serbian inflection ("zahtevu") could falsely match a heading keyword
("ZAHTEV") mid-word — fixed to word-boundary matching. (2) The new per-segment retry loop could have
reintroduced Sprint 001's already-fixed orphan-document defect on a mid-attempt failure — fixed by reusing the
existing `delete_partial_document()` cleanup. (3) The idempotency check's `.maybe_single()` call would have
raised on a resumed segmented job with 2+ documents sharing one job id — fixed by checking segment existence
first, via a plain list query.

**42 pre-existing tests, rippled by the extractor's contract change** (3-tuple → 4-tuple, adding the
preserved page list), found and fixed across 12 files — full regression suite green, zero unresolved
failures.

**7 required deliverables**: `docs/architecture/CANONICAL_SEGMENTATION_ARCHITECTURE_REPORT.md`,
`CANONICAL_SEGMENTATION_SIGNAL_SPECIFICATION.md`, `SEGMENT_IDENTITY_SPECIFICATION.md`,
`SEGMENTATION_FAILURE_RECOVERY_REPORT.md`, `SEGMENTATION_EDGE_CASE_VALIDATION_REPORT.md`,
`USER_AUTOMATION_GAIN_REPORT_SPRINT005.md`, `SPRINT_005_MISSION_REPORT.md`, plus 3 new
`ARCHITECTURAL_DEBT_REGISTER.md` entries (`INTAKE-015` through `INTAKE-017`, checked against existing
prefixes first — no collision).

| ID | Finding | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| INTAKE-015 | Segmentation only wired into Pipeline B, not Pipelines A/A-ephemeral/C | 2 | Founder decision — desired interactive UX for a synchronous upload path | Medium | NEEDS_SCOPING | The engine itself is already pipeline-agnostic; only the reaction to a multi-document result differs by pipeline. |
| INTAKE-016 | No cross-run backoff/retry-claim system for segments, only bounded in-process retry | 3 | New architecture — a claim RPC mirroring `claim_intake_job`'s own pattern | Medium | NEEDS_SCOPING | A dead-lettered segment is visible/audited, just not auto-retried on a later tick. |
| INTAKE-017 | No distinct `partially_failed` job status — collapsed into existing `awaiting_review` | 3 | Founder decision — may finalize ever proceed on an M-1-of-M segmented job | Small-Medium | NEEDS_SCOPING | Safe by default (fail-closed via the existing status gate); only a UX-precision gap today. |

## Program Intake, Sprint 006 (2026-08-05) — Canonical Case Assimilation

Ninth masterprompt of this multi-session Program Intake arc. Sprint 005 proved one PDF can contain multiple
logical documents; this sprint proves each of those documents becomes part of a specific, correctly-
identified case and client — deterministically, never a guess. Smallest team of this sprint style: 3 agents
(Chief Systems Architect, Legal Domain Expert, Reliability & Failure Recovery Engineer). Same binding rule as
Sprints 004/005: every technical problem found within scope that could be fixed without a new founder
business decision was fixed in the same sprint. Governing rule with absolute priority throughout: a document
assigned to the wrong case is a more serious problem than ten documents waiting for human confirmation.

**Headline finding**: `predmeti` had NO structured case-number column at all, and no mechanism anywhere in the
repo could recognize that an incoming document's case number matches an already-open case — every non-
interactive intake either required an explicit `predmet_id` or unconditionally created a duplicate case. Also
found: a live client-name-matching bug (`finalize_intake_job` compared a full "First Last" string against
`klijenti.ime`, a first-name-only column, `.limit(1)` with no disambiguation — the mission's own named "two
clients, same surname" failure mode, unmitigated), zero audit calls for document-into-case registration, a
false-success bug (case marked finalized with 0 documents linked), and a structural incompatibility with
Sprint 005's own multi-segment output (`finalize_intake_job` and `GET /jobs/{job_id}` both still called the
single-document `get_job_result()`, which would raise on any segmented job).

**Built**: `shared/case_assimilation.py` (Ownership Resolution — exact case-number match auto-attaches to an
existing case, exact full-name match auto-links a client, anything ambiguous routes to Review Required, never
a guess) + `predmeti.broj_predmeta` (migration 094) + `predmet_dokumenti.source_intake_job_segment_id`
lineage FK with a DB-enforced UNIQUE constraint (Evidence Integrity) + `intake_job_segments.assimilation_
status` (a second, orthogonal lifecycle from Sprint 005's own classification `status`). `finalize_intake_job`
rewritten from a single-document function into a per-document loop, each with its own try/except (Phase 5
isolation, extending Sprint 005's own per-segment pattern one stage further into assimilation) — every
document Sprint 005 produces is now correctly assimilated, audited, and provenance-tracked, not just the
first.

**A real bug found and fixed during this sprint's own test-writing**: `looks_like_company()`'s first
implementation replaced dots with spaces before tokenizing a party name, shattering "d.o.o." into meaningless
single-letter tokens that never matched anything — fixed to strip dots per-token instead of using them as a
word separator.

**7 required deliverables**: `docs/architecture/CANONICAL_CASE_ASSIMILATION_ARCHITECTURE_REPORT.md`,
`OWNERSHIP_RESOLUTION_SPECIFICATION.md`, `LINEAGE_VERIFICATION_REPORT.md`, `EVIDENCE_INTEGRITY_REPORT.md`,
`CASE_ASSIMILATION_FAILURE_RECOVERY_REPORT.md`, `CASR_METRICS_REPORT.md`, `SPRINT_006_MISSION_REPORT.md`,
plus 3 new `ARCHITECTURAL_DEBT_REGISTER.md` entries (`INTAKE-018` through `INTAKE-020`, checked against
existing prefixes first — no collision).

| ID | Finding | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| INTAKE-018 | No segment-content-hash dedup across two different overall uploads | 3 | New architecture — a content-hash column + cross-job lookup | Medium | NEEDS_SCOPING | Not a wrong-case risk today, only a missed-duplicate-detection gap. |
| INTAKE-019 | A partially-failed finalize has no automatic retry path once `predmet_id` is set | 2 | Founder/scoping decision — does "finalized" mean fully done or partially done | Medium | NEEDS_SCOPING | Failure is visible (per-document + segment status), just not self-healing yet. |
| INTAKE-020 | Case number matching is exact-only, no format normalization beyond whitespace | 3 | none — deliberate conservatism choice | Small | TODO (low priority) | Safe direction by design (create-new, never mis-attach); a missed-attach-opportunity risk only. |

## Program Intake, Sprint 007 (2026-08-05) — Intake Finalization – Bulletproof Intake

Tenth masterprompt of this multi-session Program Intake arc, and the last one this arc scopes as
"reliability hardening" — after this sprint, Intake is a closed subsystem future missions (Timeline, Genome,
Case Evolution, Tasks, Alerts, Briefing, Copilot) build ON, not one that needs further architectural
reconstruction. **Hard token budget**: max 3 agents, only 2 active at start (Reliability & Failure Recovery
Engineer, Chief Systems Architect), 3rd (Code Quality/Refactoring Reviewer) STANDBY unless a written
justification for scope-escape arose — none did; both roles executed directly, no subagents spawned, per the
mission's own explicit minimal-footprint instruction. Scope: closes exactly the 3 debts Sprint 006 itself
deferred (`INTAKE-018` through `INTAKE-020`) — nothing more.

**Headline finding**: Sprint 006's own `INTAKE-019` was more severe than its description implied — the
idempotency gate didn't just block retry of a soft partial failure, it also meant a HARD CRASH before the
durable `predmet_id` write would let a retry run Ownership Resolution completely fresh and create a genuinely
SECOND duplicate case. Also found: `normalize_case_number`'s own prefix character set (new this sprint) had a
real gap for mixed-case two-letter Cyrillic prefixes ("Пж"/"Гж" — the actual shape Serbian court
abbreviations use), caught via this sprint's own test-writing.

**Built**: one deterministic content identity (`predmet_dokumenti.content_sha256`, migration 095, SHA-256 of
extracted text, never filename/size/date) answering BOTH cross-upload duplicate detection AND retry
idempotency with the same lookup; crash recovery via a generalized lineage FK
(`predmet_dokumenti.source_intake_job_id`, extending Sprint 006's segment-only FK to every document); the
atomic finalize claim itself widened (`claim_intake_finalize`'s WHERE clause: `predmet_id IS NULL` →
`intake_jobs.assimilation_complete = false`) so both a hard crash and a soft partial failure remain correctly
retryable; a real 3-part case-number canonical parser (prefix/number/year) replacing the whitespace-only
placeholder.

**Mission's own bulletproof definition, proven by test, not merely claimed**: same document uploaded twice,
processing interrupted at any point (hard crash before OR soft failure after the completion marker), retried
any number of times — always converges on one document, one case, one lineage chain, one audit/provenance
record. 14 new tests, full suite 2,595 passed/1 skipped/0 failed (was 2,581).

**7 required deliverables**: `docs/architecture/DUPLICATE_DETECTION_REPORT.md`, `RETRY_RELIABILITY_REPORT.md`,
`CASE_NUMBER_NORMALIZATION_SPECIFICATION.md`, updated `INTAKE_ARCHITECTURE_REPORT.md`, updated
`ARCHITECTURAL_DEBT_REGISTER.md`, `SPRINT_007_MISSION_REPORT.md`, plus 2 new debt entries (`INTAKE-021`,
`INTAKE-022`, checked against existing prefixes first — no collision). `INTAKE-018` through `INTAKE-020`
formally CLOSED.

| ID | Finding | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| INTAKE-021 | Dedup/retry mechanism only wired into Pipeline C, not A/A-ephemeral | 2 | none — mechanical extension of an already-pipeline-agnostic mechanism | Medium | NEEDS_SCOPING | Deliberate scope boundary (hard token budget), not an oversight — the mechanism itself needs no redesign to extend. |
| INTAKE-022 | No automatic backoff/dead-letter ceiling for a document failing across repeated manual finalize retries | 3 | none — finalize is lawyer-initiated, not automatic | Small | TODO (low priority) | Each retry is cheap/safe via content-hash idempotency; only a missing ceiling on indefinite manual retry. |

## Program Delta, Sprint 001 (2026-08-05) — Canonical Case Evolution Engine

First masterprompt of a new program: Program Intake (Sprints 001-007) is finished; a document is no longer
the goal, only an event. **Hard token budget**: max 2 active agents, no exceptions, no subagents, no parallel
analysis (Enterprise Systems Architect, Reliability Engineer) — both roles executed directly, honored for
the whole sprint. **Standing founder recommendation for all future Delta sprints**: read only
`docs/delta/*` (this sprint's own deliverables), not the full Nexus→Intake history, to keep context focused.

**Headline finding**: the pre-existing Event Bus (durable outbox, atomic claim, bounded retry/dead-letter,
correlation_id — all mature before this sprint) had no idempotency AT THE PER-CONSEQUENCE level within one
event handler — a multi-step handler's retry would re-run already-succeeded steps. Closed with exactly one
new tracking table keyed off the outbox's OWN row id, not a new event system.

**Built**: `services/case_evolution.py` — the one canonical `handle_case_changed` dispatcher (Case Changed →
Determine Consequences → Execute → Verify → Audit → Complete), `CONSEQUENCE_REGISTRY` contract, wired for
exactly one event this sprint (`DOCUMENT_ACCEPTED`, 2 consequences: `genome_refresh` — independently
verified via `case_dna.verzija` before/after, never trusting `_run_genome_background`'s own silent-swallow
self-report; `timeline_entry` — one row per finalize call, matching Genome's own coalescing);
`case_evolution_consequences` table (migration 096, `UNIQUE(event_id, consequence_name)`); 8 new `EventType`
values mapping every event Task 1 named; `finalize_intake_job`'s direct Genome-trigger call replaced with a
durable event emission (Pipeline C only — the one pipeline already hardened by Sprint 007).

**Mission's own success definition, proven by test not merely claimed**: all 6 required scenarios (new
document — every consequence exactly once; crash after Genome, retry — no duplicate; crash after Timeline,
retry — resumes as full no-op; two parallel events — no cross-contamination; replay — no new consequences;
audit — every consequence shares one correlation_id) proven in `tests/test_case_evolution.py` (10 new tests,
all passing). Full suite: **2,605 passed, 1 skipped, 0 failed** (was 2,595) — zero regressions.

**6 required deliverables**: `docs/delta/CASE_EVOLUTION_REGISTRY.md`, `EVENT_FLOW_DIAGRAM.md`,
`CANONICAL_CONSEQUENCE_ENGINE_SPECIFICATION.md`, `ARCHITECTURE_DIAGRAM.md`, `SPRINT_001_MISSION_REPORT.md`,
plus 3 new debt entries in `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md` (`DELTA-001`/`DELTA-002`/
`DELTA-003` — checked against existing prefixes first, no collision).

| ID | Finding | Priority | Depends on | Complexity | Status | Completion criteria |
|---|---|---|---|---|---|---|
| DELTA-001 | ~~Only `DOCUMENT_ACCEPTED` has wired consequences~~ — UPDATED Sprint 002: 5 of 8 wired, 3 remain (`DOCUMENT_MODIFIED`/`CONFIDENCE_DROPPED`/`MANUAL_CORRECTION_APPLIED`) | 3 | none | Low | NEEDS_SCOPING (downgraded) | Each remaining event has an explicit "no proven need yet" reasoning |
| DELTA-002 | ~~3 scattered call sites~~ — UPDATED Sprint 002: 2 of the original 4 migrated (Evidence Vault, conflict-check) + 1 undiscovered-until-Sprint-002 site also migrated (`resolve_job_review`'s own audit call); Pipeline A + `rocista.py` Genome triggers remain | 2 | none — mechanical, different feature surface | Medium | NEEDS_SCOPING | A future Delta sprint scoped to "Pipeline A + rocista.py Genome migration" closes this |
| DELTA-003 | No rollback mechanism for cross-consequence dependencies | 4 | an event whose consequences are NOT independently safe (none exists yet) | — | WONTFIX (no current need) | Speculative architecture for a case that doesn't exist in the platform today |
| DELTA-004 | `REVIEW_REJECTED`'s own "rollback" is trivial-by-construction (no consequence was ever registered to undo), not a general mechanism | 4 | same as DELTA-003 | — | WONTFIX (no current need) | Only relevant if a future event's rejection needs to undo an ALREADY-APPLIED consequence |

## Program Delta, Sprint 002 (2026-08-05) — Canonical Event Migration I: Human Decisions Become System Decisions

Second Delta sprint, per the founder's own standing instruction: read only `docs/delta/*` at sprint start
(followed). **Hard token budget**: max 2 active agents, no exceptions, no subagents, no parallel analysis —
honored for the whole sprint. Migrates 4 more events onto Sprint 001's canonical mechanism:
`REVIEW_ACCEPTED`, `REVIEW_REJECTED`, `NEW_CLIENT_LINKED`, `NEW_EVIDENCE_REGISTERED`.

**Headline finding**: `NEW_CLIENT_LINKED` and `NEW_EVIDENCE_REGISTERED` both replaced code using
`asyncio.create_task(...)` fire-and-forget — a failure inside either was logged once and PERMANENTLY lost
(no retry, no dead-letter, no durable trace). Migrating both is a genuine reliability improvement, not just
an architectural one: failures now propagate to the Event Bus's own proven retry/dead-letter mechanism
(`MAX_DISPATCH_ATTEMPTS=5`) instead of silently vanishing after one attempt.

**Built**: `services/event_bus.py::emit_durable()` — Sprint 001's own single emission idiom factored into one
shared function (used at all 5 emission call sites now, including `DOCUMENT_ACCEPTED`'s own retrofitted
Sprint-001 site); 4 new consequence executors in `services/case_evolution.py`, all reusing existing functions
UNCHANGED (`_run_conflict_check`, `klasifikuj_i_sacuvaj`, `log_action`) — REVIEW_ACCEPTED even reuses
`DOCUMENT_ACCEPTED`'s own `genome_refresh`/`timeline_entry` executors directly (no duplication); `shared/
intake_documents.py::reject_review()` + `POST /jobs/{job_id}/review/reject` — REVIEW_REJECTED's first-ever
canonical definition, closing Program Intake Sprint 004's long-open `INTAKE-012`; migration 097 (additive
`intake_jobs.status` CHECK widening for the new `'rejected'` terminal value).

**1 real bug found and fixed as part of the migration, not a separate bug hunt** (belongs to the migrated
`REVIEW_ACCEPTED` event's own Human Review domain, no business decision needed): `resolve_job_review` used to
return early WITHOUT resolving the review at all whenever a job was already finalized — the
`intake_review_queue` row for a post-finalize correction stayed "unresolved" forever. Fixed: `resolve_review()`
now always runs (already idempotent), and the founder's own worked example ("Review Accepted → Genome →
Timeline → Audit") now literally applies for exactly the case where it matters.

**Mission's own success definition, proven by test not merely claimed**: all 6 required scenarios (Review
Accepted → Genome → Timeline → Audit exactly once; Review Rejected → trivial-by-construction rollback, no
duplicates; Client Linked replayed → same result; Evidence Added parallel → no race condition; crash after
first consequence, retry → resumes; replay → same correlation_id/audit/result) proven in `tests/
test_delta_sprint002_event_migration.py` (15 new tests, all passing). 4 existing test files updated (asserted
the OLD direct-call behavior this sprint replaced, not discovered bugs). Full suite: **2,619 passed, 1 skipped,
0 failed** (was 2,605) — zero regressions.

**6 required deliverables**: updated `docs/delta/CASE_EVOLUTION_REGISTRY.md`, `EVENT_MIGRATION_REPORT_SPRINT_002.md`,
updated `EVENT_FLOW_DIAGRAM.md`, `RELIABILITY_VERIFICATION_REPORT_SPRINT_002.md`, updated
`docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md` (`DELTA-001`/`DELTA-002` updated, `DELTA-004` added),
`SPRINT_002_MISSION_REPORT.md`.

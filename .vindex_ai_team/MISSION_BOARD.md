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
| NEX-004 | Resolve `PREDMET_KREIRAN`'s Event Bus durability gap | 4 | Verify `run_case_pipeline` idempotency first | Medium | NEEDS_SCOPING | The one true in-process-only `emit()` call site in the repo — no durable outbox row, unlike every other event type. Highest-priority open item per `NEXUS_BETA_READINESS_REPORT.md`. Not fixed blind: making it durable risks double-firing the Case Pipeline unless idempotency is verified first. |
| NEX-005 | New `DOCUMENT_JOB_FAILED` handler | 5 | none | Small-Medium | NEEDS_SCOPING | Emitted on every failed OCR/classification job, zero handler exists. Needs new handler logic, one step past pure orchestration. |
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

## Explicit exclusions from autonomous scope (per the Master Prompt's own Stop Conditions)

- Any change requiring a production schema migration (per this project's standing rule, migrations
  are drafted for the founder to review and run himself — never auto-applied, and per the Master
  Prompt, a schema migration requirement is itself a stop condition, not just an execution note).
- The Security Governance Framework / Epic B rate-limiting chain — explicitly mid-founder-review,
  parked at Revision 2, ACTIVE BLOCKER. Not touched tonight under any mission.
- Intake system convergence at the backend/API level — explicitly rejected by decision record
  (`decisions/2026-08-02_intake_convergence_DECISION_RECORD.md`); not reopened without a new
  founder-supplied reason to revisit.

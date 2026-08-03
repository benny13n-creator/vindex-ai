# Lawyer Day Report

**Mission:** Operation Lawyer Day, founder's Master Prompt, 2026-08-03.
**Method:** every step below is traced against actual repository code (file:line), not assumed. No
step is marked reachable without a confirmed frontend caller; no step is marked blocked without
confirming no path exists. This is a simulation of what a real lawyer's mouse clicks and keystrokes
would trigger — API existence alone is never treated as sufficient.

**Headline result:** a lawyer CAN reach the end of a full workday inside Vindex AI today — but only by
using an older, cruder set of paths for document intake, while the newer, better-designed Smart Intake
pipeline (structured per-document review, confidence-corrected entity extraction, multi-document
batching into one case) sits completely unreachable. The day does not hard-stop; it silently downgrades.
Full evidence for every claim below: `.vindex_ai_team/decisions/2026-08-03_lawyer_day_workflow_gaps_INVESTIGATION.md`,
plus this multi-night engagement's prior investigations (Smart Intake frontend gap, Scenario B/G/F/5
fixes, Feature Discovery census).

---

## Workflow 1 — New client calls, needs legal assistance

| Step | Status | Evidence |
|---|---|---|
| Lawyer creates client | ✅ CONTINUE | CRM Intake Wizard (`routers/intake.py`), reachable from the Klijenti tab. |
| Creates case | ✅ CONTINUE | Same wizard, or `POST /api/predmeti` directly — both trigger the Case Pipeline (confirmed prior session). |
| Uploads phone photos + PDFs | ⚠️ DEGRADED, not blocked | The lawyer cannot reach `POST /api/smart-intake/documents` (zero frontend callers, confirmed — see Blocker Report `2026-08-03_ZTC-FRONTEND_smart_intake_wiring_BLOCKER_REPORT.md`). They CAN reach `POST /api/predmeti/{id}/upload` (`api.py:4133`), a real, working, per-case upload — but it accepts only PDF/DOCX (`api.py:4179`, `_ALLOWED_MIMES`/`_ALLOWED_SUFFIXES`) — **phone photos (JPG/PNG) are rejected on the one upload path a lawyer can actually reach**, even though image OCR was built and works (Night Shift M-001) — just not wired into this endpoint. |
| Runs OCR | ✅ CONTINUE (for PDF/DOCX only) | `api.py:4192` calls the same `uploaded_doc/extractor.py::extract` Smart Intake uses. |
| Checks extraction | ⚠️ DEGRADED | No per-entity confidence-review UI exists on this path (that UI only exists for Smart Intake's job model, unreachable). The lawyer gets a free-text AI "procena" (assessment), not a structured, correctable entity list. |
| Generates AI analysis | ✅ CONTINUE | Same endpoint auto-runs RAG-enriched legal analysis + chronology + metadata extraction in parallel (`api.py:4477-4521`) — genuinely rich, real output. |
| Creates chronology | ✅ CONTINUE | Extracted events written to `predmet_hronologija` with the correct, DB-constraint-valid vocabulary (`api.py:3952`, `:4596-4598`) — confirmed NOT subject to the `vaznost` fragmentation bug found earlier this engagement (that affected other writers, not this one). |
| Adds notes | ✅ CONTINUE | "Beleške" panel in case detail (`index.html:922-923`) — private, per-lawyer notes, explicitly labeled "vidljive samo vama" (visible only to you). |
| Schedules reminder | ✅ CONTINUE | Any deadline written with `vaznost` in `["kritičan","važan","bitan","kljucan","normalan"]` is picked up by the daily email cron (LZ-001 fix, this engagement). |
| Generates first draft | ✅ CONTINUE | AI Workspace → "nacrti" mode, real, dual-backend (`/api/nacrt` for simple documents, `/api/podnesak` for 8 litigation-document types) — confirmed fully wired this mission's investigation. |
| Exports | ✅ CONTINUE | `nacrtExportDocx()` → `POST /api/nacrti/export/docx` → real `.docx` download. |

**Workflow 1 verdict: completes, degraded.** The single real interruption is photo upload rejection on
the only reachable path — a lawyer with phone photos of a document (a common real scenario: photos of
a contract, an ID, a handwritten note) cannot get them into a case at all today, despite OCR-for-images
having existed since Night Shift M-001. See `WORKFLOW_INTERRUPTION_REPORT.md` Finding #1.

## Workflow 2 — Existing client returns

| Step | Status | Evidence |
|---|---|---|
| Find old case | ✅ CONTINUE | Search covers cases, clients, documents, tasks, hearings, chronology, notes (7 types, `routers/search.py`, extended this engagement). |
| Search documents | ✅ CONTINUE | `_search_dokumenti` matches `tekst_sadrzaj` + `tip_dokaza` (M-003, LZ-002). |
| Search evidence | ✅ CONTINUE | Same document search branch; Evidence Vault's richer classification (`predmet_dokazi`) is not itself a separate search branch, but its output (`tip_dokaza`) is searchable. |
| Review chronology | ✅ CONTINUE | Case-detail chronology panel, reads `predmet_hronologija` directly. |
| Review AI Briefing | ✅ CONTINUE | `case_intelligence`'s per-case briefing button, wired **tonight's prior mission** (IF-002) — this specific step would have been a hard gap as recently as a few hours before this simulation. |
| Generate new strategy | ✅ CONTINUE | AI Workspace → "strategija" mode, dedicated buttons (`stratPokreni()`, `stratOrkestratorPokreni()`), confirmed fully wired. |
| Update deadlines | ✅ CONTINUE | `routers/rokovi_lanac.py`'s deadline-chain calculator is a real, reachable, MANUAL feature — a lawyer can trigger it themselves (only *automatic* firing was correctly left unbuilt, per `M-005`'s Blocker Report, since the extraction pipeline can't reliably pick the right one of 14 procedure-specific chains). |
| Generate response | ✅ CONTINUE | Same "nacrti"/"podnesak" pipeline as Workflow 1. |
| Export | ✅ CONTINUE | Same DOCX export. |

**Workflow 2 verdict: completes, no interruption found.** This is the strongest workflow in the app —
every step traced to a real, reachable, working feature.

## Workflow 3 — 20 new scanned documents arrive

| Step | Status | Evidence |
|---|---|---|
| Batch upload | ⚠️ DEGRADED | Smart Intake's batch endpoint (`POST /api/smart-intake/documents`, accepts a `List[UploadFile]`, returns one job per file) is unreachable. The reachable path (`api.py:4133`) accepts exactly ONE file per call — a lawyer (or their UI) would need 20 separate upload actions, not a true batch. |
| Duplicates | ✅ Exists, narrower scope | Smart Intake has real SHA-256 exact-content dedup (`smart_intake.py:126`, idempotency key) — but it's on the unreachable path. The reachable per-case upload path (`api.py:4133`) has no dedup check at all — uploading the same file twice creates two `predmet_dokumenti` rows. |
| OCR | ✅ CONTINUE (per file, PDF/DOCX only) | Same as Workflow 1. |
| Classification | ✅ CONTINUE | Evidence Vault auto-classify already wired into this reachable path (`api.py:4321-4330`) — confirmed NOT a gap, contrary to this mission's initial working hypothesis. |
| Routing (to one case) | ✅ CONTINUE, if the case already exists | Since this path uploads TO a specific existing `predmet_id`, 20 documents uploaded this way correctly land in ONE case — the "N separate cases" bug (Scenario B, fixed `ZTC-001`) was specific to Smart Intake's finalize-creates-new-case behavior, which doesn't apply here. |
| Searchability | ✅ CONTINUE | Same search coverage as Workflow 2. |
| Case Genome | ✅ CONTINUE, with a caveat | Auto-refreshes after each upload (`api.py:4332-4345`). For a case that already has ≥25 documents, only the 25 most recent are ever analyzed (Scenario G, fixed `ZTC-002` — now recency-biased and accurately reported, not silently wrong). 20 new documents added to an already-large case would push older-but-still-recent documents out of analysis — expected behavior given the fix, not a new bug. |
| Timeline | ✅ CONTINUE | Aggregates from `predmet_hronologija`, populated per-document. |

**Workflow 3 verdict: completes, meaningfully degraded.** 20 documents CAN all be processed — but as 20
separate manual upload actions instead of one batch, with no duplicate-file protection, through a path
that (per Workflow 1) also can't accept phone photos. The backend already has a proper batch+dedup
system built (Smart Intake) sitting completely idle.

## Workflow 4 — Preparing tomorrow's hearing

| Step | Status | Evidence |
|---|---|---|
| Prior arguments | ✅ CONTINUE | Case Genome's `pravna_teorija`/`strategija` fields, plus AI Briefing. |
| Evidence | ✅ CONTINUE | Evidence Vault panel, case-scoped. |
| Judge history | ✅ CONTINUE — **better than assumed** | Dedicated "Litigation Intelligence" AIWS mode (`index.html:3065-3131`, PRO-gated): Judge & Court Profiler (`stratJudgeProfile()`), Opponent Intelligence (`stratOpponentIntel()`), Similar Cases, Outcome Trends — all real, all wired. Not previously catalogued this engagement; found fresh this mission. |
| Client history | ✅ CONTINUE | Client Communication Profile, folded into the AI Briefing (IF-002). |
| Generated briefs | ✅ CONTINUE | "nacrti"/"podnesak" drafting, same as Workflow 1/2. |
| Knowledge base | ✅ CONTINUE | Personal notes/knowledge tool, confirmed reachable in prior sessions. |
| Deadlines | ✅ CONTINUE | Calendar tab, aggregates `predmet_hronologija`. |
| Export package | ❌ DOES NOT EXIST as a single feature | No endpoint or UI bundles judge history + opponent intelligence + evidence + briefs + deadlines into one download. A lawyer must visit 4+ separate views and export pieces individually. Every underlying capability already works — this is a missing aggregation UI, not a blocked backend. |

**Workflow 4 verdict: completes, with real friction.** Nothing is blocked; everything needed for
hearing prep is reachable — but scattered across enough separate screens that "prepare for tomorrow's
hearing" is a 15-minute multi-tab exercise instead of a single action.

## Workflow 5 — End of day

| Step | Status | Evidence |
|---|---|---|
| GDPR | ✅ CONTINUE | Self-service export (`/api/export/complete`, richer) and account deletion (wired **tonight's prior mission**, IF-001) both reachable from Settings. |
| Audit | ⚠️ PARTIAL | An immutable backend audit log exists (`shared/audit_immutable.py`) and is written to (document uploads, GDPR actions) — but no UI lets a lawyer VIEW their own activity history. Confirmed absent, not found under any name in `vindex.js`. |
| Billing | ✅ CONTINUE | `routers/billing_reports.py`, "Finansije" tab, fully wired. |
| Archive | ⚠️ DEGRADED | Case archiving works (`routers/predmeti_close.py`) but only via bulk-select from the case LIST view, not a button while viewing a single case's own detail panel — a lawyer finishing work on one specific case must navigate back to the list to archive it. |
| Notifications | ✅ CONTINUE | Notification bell, confirmed working in prior sessions. |
| Backup | N/A, correctly | No lawyer-facing backup-status UI exists — this is legitimately an infrastructure concern with no natural surface for a lawyer, not a gap. |
| Case status | ✅ CONTINUE | Status changes reachable from the case list's bulk-action bar (same mechanism as archiving). |

**Workflow 5 verdict: completes, with two real but minor gaps** (no activity-log viewer; archiving
requires a trip back to the list view).

---

## Overall verdict

**A lawyer can complete a full workday inside Vindex AI today without leaving the platform for any
hard-blocking reason.** No workflow step among the 5 simulated produces a true dead end. The mission's
success condition ("the simulated lawyer reaches the end of the workday, or the exact blockers are
identified with executable proof") is met by the first branch, with one important qualifier the
founder should weigh heavily: **the day that completes is not the day this multi-night engagement has
spent three sessions building.** Every recent improvement to intake quality — structured per-document
review, exact-duplicate detection, image/photo OCR, true multi-document-to-one-case batching — lives
in Smart Intake, which remains completely unreachable. The lawyer's actual day runs on an older,
functionally complete but cruder pipeline that happens to also work, largely by coincidence of having
been built first and never deprecated.

See `WORKFLOW_INTERRUPTION_REPORT.md` for root-cause analysis of every degradation found, classified
P0-P3, and `BETA_PROGRESS.md` for how this fits the engagement's overall trajectory.

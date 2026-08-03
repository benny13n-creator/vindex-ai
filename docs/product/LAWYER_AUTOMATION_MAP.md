# Lawyer Automation Map

**Mission:** Operation Lawyer Zero (BETA-001), 2026-08-03.
**Method:** every row grounded in file:line evidence — from this mission's own Phase 1 inspection
(`.vindex_ai_team/decisions/2026-08-03_lawyer_zero_phase1_INSPECTION.md`) plus verified findings
from the same session's earlier Night Shift (`.vindex_ai_team/NIGHT_SHIFT_SUMMARY_2026-08-02.md`,
`docs/product/BETA_CRITICAL_PATH_2026-08-02.md`, `docs/product/BOJAN_WORKFLOW_GAP_ANALYSIS_2026-08-02.md`).
No claim below is invented — where evidence is incomplete, that is stated explicitly rather than
filled in with an assumption.

**Headline finding:** this codebase does not need a new automation feature tonight. It needs **one
vocabulary bug fixed** and **one classification step connected** — both real, working, already-built
systems that are currently silent for exactly the cases the AI pipeline creates. That is Rule Zero's
entire point: connect before you build.

---

## Workflow-step map

| Step (human workflow today) | Current implementation | Missing wiring | Missing data | Blocking dependency | Effort | Risk | Business value | Reuse % |
|---|---|---|---|---|---|---|---|---|
| **Client arrives → case created** | ✅ Real. Two entry points confirmed working and *not* duplicates (`.vindex_ai_team/decisions/2026-08-02_intake_convergence_DECISION_RECORD.md`): description-first (`routers/intake.py::intake_kreiraj`) and document-first (`routers/smart_intake.py` finalize). Both now trigger the 9-step Case Pipeline (fixed 2026-08-02, M-013). | None | None | None | — | — | Done | 100% |
| **Upload scanned documents** | ✅ Real, async, encrypted. PDF/DOCX/TXT/JPG/PNG all accepted (image support added 2026-08-02, M-001). OCR (Tesseract, Serbian-aware) runs automatically in the background worker. | None | None | None | — | — | Done | 100% |
| **Manually rename files** | 🟡 Partially automatic. `shared/intake_classify.py` assigns a coarse `document_type` automatically (lawsuit/response/appeal/judgment/etc.), surfaced in the job-status view — a lawyer sees a suggested type, doesn't have to guess from a filename. The *filename itself* is not auto-generated from content (e.g. `"presuda_zalba_15dana.pdf"` from a scanned `"IMG_2847.jpg"`) — this specific sub-step (auto-renaming to a meaningful filename) was not found anywhere in the inspection. | A rename-from-classification step doesn't exist. | Document type + a key date/party, both already extracted, would be sufficient to compose a filename. | None | Small | Low | Medium — cosmetic but reduces one manual step lawyers do reflexively | ~70% (classification data already exists; only the compose-and-rename step is missing) |
| **Manually connect files (to a case, to each other)** | ✅ Mostly real. Smart Intake's finalize path auto-links an uploaded document to a case (`predmet_dokumenti`), decides an owning client via extracted parties. | None found for the primary path. | — | — | — | — | Done for the primary path | ~90% |
| **Manually enter chronology** | 🟡 Real but thin. `routers/intelligence_timeline.py` auto-aggregates a working timeline view from 6 real sources — the *view* requires no manual entry. But only **one** deadline is extracted per document (Bojan Gap Analysis, 2026-08-02) — no multi-event extraction (filing/response/hearing dates from one document) exists. This is `docs/product/BETA_CRITICAL_PATH_2026-08-02.md` scenario #6/#7, tracked as `M-004`/`NEEDS_SCOPING` on the Mission Board — correctly not attempted blind (needs its own scoping pass; "Large" complexity, new extraction design). | Multi-event extraction pipeline. | A prompt/heuristic design that reliably finds >1 dated legal event per document — does not exist yet, not a wiring problem. | None new tonight. | Large | Medium (new NLP surface, needs real validation before trusting output) | High — this is the single biggest "chronology as a story, not a folder" gap | Low — this is new work, not existing-component wiring, so Rule Zero doesn't apply the same way |
| **Manually create reminders** | 🔴→🟢 **Found broken, fixable tonight.** `routers/email_notif.py::posalji_podsetnike` is a real, working, already-scheduled (`api.py`'s daily cron, 07:00 UTC, confirmed live) email reminder system — 7/3/1-day-out warnings, deduplicated, real HTML email. **It filters on `vaznost == "kritičan"` exactly, and every AI-extraction deadline-writing path uses a different string** (`"važan"` from Smart Intake, `"bitan"` from the primary `intake_kreiraj` flow, and yet a third, non-diacritic vocabulary — `"kritican"`/`"vazno"`/`"info"` — from the deadline-chain calculator). **The reminder system has never fired for an AI-extracted deadline, ever, and nothing in the code was broken in the usual sense — two independently-written, independently-correct pieces just used different words for the same concept.** See `LZ-001` below. | The cron's filter, or the writers' vocabulary — one needs to change to match the other. | None. | None. | **Small** | **Low** (a filter/constant change, not new logic; the sending mechanism itself is untouched and already proven) | **Very high — this is the single highest-leverage fix in this entire inspection** | **Very high — 100% reuse, zero new systems** |
| **Manually create tasks** | 🟡 Real task system exists (`routers/zadaci.py`), zero automatic creation from anything. Case Genome's `nedostaje` (missing evidence) field and `services/risk_engine.py`'s deterministic `nedostajuci_dokazi` output both identify things a lawyer should act on — neither creates a `zadaci` row. A lawyer has to read the AI's output and manually decide to act on it. | A "convert AI finding → task" step. | None — both source fields already exist and are populated. | `LZ-002` below (risk engine's signal is currently starved for freshly-uploaded documents, see next row) — fixing that first makes this wiring more valuable. | Medium (needs a design decision: auto-create silently, or propose-then-confirm — same class of question `M-005`'s blocker report raised for deadlines; a wrongly-created task is lower-stakes than a wrongly-cited legal deadline, but the same discipline applies) | Low-Medium | High | Medium — the `zadaci` table/API is 100% reusable; the "when to create one" logic is new |
| **Manually search through documents** | 🟢 Fixed 2026-08-02 (M-003) for full-text document content. **New blind spots found this pass**: global search has no coverage of `zadaci` (tasks) or evidence-specific fields (`tip_dokaza`, `pravni_elementi`, `kljucne_cinjenice`). A lawyer can't find a task by name, or a document by its legal classification, only by whatever text also happens to be in the raw document body. | Two more `_search_*` helper functions, following the exact pattern already used for 6 other types in `routers/search.py`. | None. | None. | Small | Low | Medium | Very high — copy-paste of an existing, working pattern |
| **Manually open multiple screens** | Not independently measured this pass (Phase 5, Lawyer Experience Review, below, addresses this directly rather than as a table row) | — | — | — | — | — | — | — |
| **Manually decide what is missing** | 🔴→🟡 **Found broken, structurally.** Two independent missing-document detectors exist: Case Genome's LLM-derived `nedostaje` field (confirmed reachable, 2026-08-02), and `services/risk_engine.py::identify_case_problems` — explicitly documented as *"the only next-action algorithm platform-wide"* (Core Consolidation decision, `routers/matter_intel.py:5-8`). The deterministic one **depends entirely on `tip_dokaza`** (evidence type), which is only ever set by `routers/evidence.py`'s richer classification (Evidence Vault) — **confirmed not auto-triggered on upload**. Case Pipeline's own step 1 explicitly defers this ("biće analizirani pri otvaranju" — will be analyzed when opened) rather than running it. **Net effect: the platform's own designated single source of truth for "what's missing" has no real signal for any freshly-uploaded document until a lawyer happens to open it and something else lazily triggers classification.** See `LZ-002` below. | Fire Evidence Vault classification automatically on ingestion (Smart Intake finalize, and/or Case Pipeline step 1), instead of relying on a lazy on-view trigger. | None — the classifier itself is built and working, just not called at the right time. | None. | None. | Medium (touches two call sites; needs to confirm it doesn't duplicate work already done by `shared/intake_classify.py`'s coarser pass — see Rule Zero note below) | Low-Medium | **Very high — this is the platform's only deterministic missing-document algorithm, currently blind for new documents** | High — 100% reuse of the classifier; new work is only the trigger wiring |

---

## Rule Zero check — before implementing anything

Both LZ-001 and LZ-002 are exactly the shape Rule Zero asks for: real, correct, already-built
systems, silently disconnected by a small, well-understood gap. Neither requires new design.

**One open question flagged, not resolved, per Rule Zero's own spirit** (don't rebuild, but also
don't blindly connect two systems that were deliberately kept separate): `shared/intake_classify.py`
(coarse, Smart Intake) and `routers/evidence.py`'s classifier (rich, Evidence Vault) both classify
the same documents for overlapping purposes. This map does not resolve whether Evidence Vault's
classification should *replace* the coarse one for AI-consuming paths, or whether both are meant to
coexist (different consumers, different depth). **LZ-002 is scoped to *add* the missing auto-trigger,
not to remove or replace the existing coarse classifier** — the narrower, lower-risk interpretation,
consistent with tonight's own discipline of connecting rather than redesigning. If the founder wants
the two systems consolidated (Core Consolidation's "1 concept = 1 owner" principle would suggest
eventually asking this), that is a separate, future decision.

---

## Selected for tonight's implementation (North Star: `MISSION_BOARD.md`)

| ID | Mission | Priority | Why |
|---|---|---|---|
| **LZ-001** | Fix `vaznost` vocabulary mismatch so AI-extracted deadlines trigger the existing automatic email reminder | **1** | Highest value-to-risk ratio found in this entire mission. Zero new systems; a already-scheduled, already-correct cron simply can't see the deadlines that matter most today. |
| **LZ-002** | Auto-trigger Evidence Vault classification on document ingestion | **2** | Feeds the platform's *only* deterministic missing-document algorithm, currently starved for every new document. Second-highest value-to-risk ratio. |
| **LZ-003** | Extend global search to cover tasks + evidence fields | 3 | Real gap, low risk, but lower business value than the two above — deferred if time runs out, not skipped silently. |
| **LZ-004** | Convert Genome/risk-engine "missing" findings into `zadaci` tasks | 4 | Genuinely valuable but needs a design decision (auto-create vs. propose-confirm) before implementation — more design risk than LZ-001-003; only attempted if time and confidence allow after the top 2 are solid. |

**Not selected tonight, explicitly, with reasons** (per the master prompt's own instruction —
postponed missions must be explained, not silently dropped):
- **Multi-event chronology extraction** (the chronology row above) — real, high-value, but not a
  "connect existing components" task; it's new NLP design work, already correctly parked as
  `M-004`/`NEEDS_SCOPING` on the Mission Board pending its own scoping pass.
- **Auto-rename files from classification** — real but lower value than LZ-001/002; a cosmetic
  convenience, not a blocker to any Beta Critical Path scenario.
- **Evidence Vault vs. Smart Intake classifier consolidation** — a legitimate architecture question,
  explicitly a founder-level product decision (which system should own document classification long
  term), not an engineering wiring task — flagged, not decided, consistent with this session's
  established discipline of not guessing at founder-level calls.

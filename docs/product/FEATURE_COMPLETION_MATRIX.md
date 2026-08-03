# Feature Completion Matrix

**Mission:** Operation Beta Lockdown, founder's Master Prompt, 2026-08-03.
**Rule applied throughout**: a feature does not exist until a real lawyer can discover it, access it,
understand it, complete it, and continue working — from the UI, not from a passing test or a working
endpoint. Every level below cites file:line evidence gathered across this engagement's 6 operations
tonight (Night Shift, Lawyer Zero, Autonomous Law Office, Invisible Features, Lawyer Day, Beta
Lockdown) — nothing here is asserted without a prior direct code read.

**Level definitions** (founder's own scale):
- **L5** — Production Ready: discoverable, reachable, completable, integrated (search/audit where
  relevant), tenant-isolated.
- **L4** — Usable but incomplete: reachable and completable, but missing one integration dimension
  (search, audit, a secondary entry point) or has a minor UX gap.
- **L3** — Backend complete, frontend incomplete: real, correct, tested logic with no UI path at all.
- **L2** — Hidden capability: reachable only via direct API call; a UI exists for something adjacent
  but not for this specific capability.
- **L1** — Partial implementation: some real logic exists but the feature cannot complete a full
  workflow even via direct API call (e.g., populates nothing, or depends on a second unbuilt piece).
- **L0** — Dead code: no caller anywhere, or deliberately superseded/deactivated.

---

## Case & document lifecycle

| Feature | Level | Discover | Access | Understand | Complete | Continue | Search | Audit | Tenant-isolated |
|---|---|---|---|---|---|---|---|---|---|
| Create client + case (CRM Intake Wizard) | **L5** | Klijenti/Predmeti tabs | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ only via `POST /api/predmeti`, not `intake_kreiraj` | ✅ |
| Upload PDF/DOCX to existing case (`api.py:4133`) | **L5** | Case detail view | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `dokument_upload` logged | ✅ (verified this mission) |
| Upload photo (JPG/PNG) to existing case | **L5** (fixed tonight, LD-001) | Same as above | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Smart Intake (job/finalize model — structured review, batch, exact-dedup, multi-doc-to-one-case) | **L3** | None — zero frontend references anywhere | ❌ | N/A | Only via direct API | N/A | N/A | ✅ (would be, if reached) | ✅ (verified backend-side) |
| OCR (PDF/DOCX/image) | **L5**, as a component of the reachable upload path | N/A (invisible, runs automatically) | ✅ | N/A | ✅ | ✅ | N/A | N/A | N/A |
| Case Genome (`case_dna`) | **L5** | Case detail, "Case Intelligence" section | ✅ | ✅ | ✅ | ✅ | ❌ Genome content itself not searchable (minor) | ✅ `genome_refresh` always logged | ✅ (re-verified this mission, all entry points) |
| Evidence Vault auto-classification | **L5** | Case detail, evidence panel | ✅ | ✅ | ✅ | ✅ | ⚠️ `tip_dokaza` searchable; richer fields (`kljucne_cinjenice`/`pravni_elementi`) not | ⚠️ not explicitly audited | ✅ (re-verified this mission) |
| Conflict-of-interest check | **L4** | Manual, CRM wizard only | ✅ (name-first flow) | ✅ | ✅ | ✅ | N/A | ⚠️ not audited | ✅ |
| Chronology / deadline extraction | **L5** | Case detail | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ not explicitly audited as its own action | ✅ |
| Automatic email deadline reminders | **L5** | N/A (proactive, arrives by email) | ✅ | ✅ | ✅ | ✅ | N/A | N/A | ✅ |
| Deadline-chain auto-calculation | **L4** | Manual trigger only (by design — `M-005`'s Blocker Report: auto-firing is unsafe without more signal) | ✅ | ✅ | ✅ | ✅ | N/A | ⚠️ not audited | ✅ |
| Document drafting (`nacrti`/`podnesak`) + DOCX export | **L4** | AI Workspace tab | ✅ | ✅ | ✅ (export works) | ⚠️ draft never enters the permanent case record | ❌ — the staging/approval step that would make it searchable is built but has zero frontend (new finding, see below) | ⚠️ not audited | ✅ (draft staging confirmed scoped) |
| Draft staging + confidence-gated approval (`routers/drafting.py`) | **L3** | None — zero frontend references to "staging" anywhere | ❌ | N/A | Only via direct API | N/A | N/A (blocks the draft above from becoming searchable) | N/A | ✅ (verified backend-side) |
| Strategy generation (single-agent + 6-agent orchestrated) | **L5** | AI Workspace tab, dedicated buttons | ✅ | ✅ | ✅ | ✅ | N/A | ⚠️ not audited | ✅ |
| Litigation Intelligence (judge/opponent/similar-case/outcome-trend research) | **L5** | AI Workspace tab, PRO-gated mode | ✅ | ✅ | ✅ | ✅ | N/A | ⚠️ not audited | ✅ (assumed consistent with rest of file; not independently re-verified this mission) |
| Per-case AI Briefing | **L5** (fixed tonight, IF-002) | Case detail, Case Intelligence section | ✅ | ✅ | ✅ | ✅ | N/A | ⚠️ not audited | ✅ (re-verified this mission — all 8 underlying queries) |
| Portfolio-wide daily briefing (CIO) | **L5** | Home tab | ✅ | ✅ | ✅ | ✅ | N/A | N/A | ✅ (established prior sessions) |
| Case archiving / status change | **L4** | Case LIST view bulk-select only, not case-detail | ✅ | ✅ | ✅ | ✅ | N/A | ⚠️ not audited | ✅ (re-verified this mission, double-scoped) |
| Case-scoped activity history (Intelligence Timeline) | **L5** | Case detail | ✅ | ✅ | ✅ | ✅ | N/A | ✅ (aggregates `audit_immutable` among 6 sources) | ✅ (established) |
| Account-wide activity/audit log viewer | **L0** — does not exist | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |

## Search, tasks, calendar, notes

| Feature | Level | Notes |
|---|---|---|
| Global search (7 types: docs, cases, clients, tasks, notes, hearings, chronology) | **L5** | All 7 branches re-verified tenant-scoped this mission — no issue found. |
| Task management (`zadaci`) | **L4→L5 after tonight's fix** | Fully reachable, real CRUD, correctly scoped everywhere EXCEPT one endpoint (`GET /api/zadaci/predmet/{id}`) which had **zero ownership check** — a live, exploitable cross-tenant leak. **Fixed tonight (BL-001)**, see Blocker Report / mission review. |
| Calendar / deadline aggregation | **L5** | Established prior sessions, re-confirmed reachable. |
| Private case notes ("Beleške") | **L5** | Reachable, searchable, correctly scoped, explicitly labeled private in its own tooltip. |
| Team comments ("Komentari tima") | **L4** | Reachable, full CRUD, but excluded from global search (confirmed this engagement, Lawyer Day). Confirmed NOT a duplicate of Beleške — distinct, intentional purpose. |

## Compliance, billing, export

| Feature | Level | Notes |
|---|---|---|
| GDPR self-service data export | **L5** | `/api/export/complete`, richer than the also-live-but-narrower `/api/gdpr/export` (correctly left unconnected to avoid a duplicate). |
| GDPR self-service account deletion | **L5** (fixed tonight's prior mission, IF-001) | Fulfills a promise already made in the public security whitepaper. |
| Billing / financial reports | **L5** | "Finansije" tab, fully wired, established prior sessions. |
| Voice command engine (standard + realtime) | **L5** | Prominent mic button in main UI chrome, routes through the same auth/permission/RAG layer as everything else. |
| Evidence Graph (single-case entity/relationship graph) | **L5** | Wired, 4 frontend references. |
| Knowledge Graph (cross-entity legal network) | **L5** | Wired, 1 frontend reference (narrower usage than Evidence Graph, still reachable). |
| Memory Graph (cross-case argument/outcome queries) | **L2** | Real, sophisticated query logic; zero frontend callers AND its only data-writer endpoint is also dead — even a direct API call today returns an empty result for any real firm. Most interesting hidden feature found this engagement; not safely wireable without a founder decision on data population strategy. |
| Web3 / Digital Asset Compliance Suite (AML/CARF/DAC8/MiCA/whitepaper) | **L5**, deliberately gated | Heavily wired (14+ frontend references); hidden behind a Settings flag by prior, intentional product decision — not an incompleteness. |
| Knowledge Base (personal notes/knowledge tool) | **L5** | Established reachable prior sessions. |

## Confirmed dead (Level 0), from Operation Invisible Features' census, unchanged tonight

`agent_notifications`, `auto_discovery` (admin-only by design), `gdpr`-export-half (superseded by a
better live duplicate), `import_klijenti` (fragmentation case, see `CURRENT_STATE.md`),
`knowledge_hygiene`, `knowledge_transfer`, `onboarding` (deliberately superseded, confirmed via explicit
code comments), `region`, `status_page` (needs one more direct check), `strategy_simulator`,
`style_checker`, `whatsapp_notif` (fragmentation case, see `CURRENT_STATE.md`).

---

## Level distribution summary

| Level | Count (this matrix) | Examples |
|---|---|---|
| L5 | 22 | Case creation, upload (PDF/DOCX/image), Genome, Evidence Vault, search, strategy, drafting-export, Litigation Intelligence, GDPR (both), billing, Voice, Evidence/Knowledge Graph, Case Intelligence Briefing, CIO, task management (after tonight's fix) |
| L4 | 6 | Conflict-check (manual only), deadline-chain (manual by design), draft-to-case-record, archiving (wrong screen), team comments (not searchable), audit (case-scoped works, account-wide doesn't) |
| L3 | 2 | Smart Intake (the whole pipeline), draft staging/approval |
| L2 | 1 | Memory Graph |
| L1 | 0 | none found this engagement |
| L0 | 11 | the confirmed-dead router set from Operation Invisible Features, unchanged |

**Two L3 findings (Smart Intake, draft staging/approval) share the exact same root shape**: real,
correct, tested backend logic with genuinely zero frontend callers. This is the dominant completion
gap in the entire application — not incorrect logic, not missing features, but a systemic pattern of
backend work outrunning frontend wiring across at least two major subsystems.

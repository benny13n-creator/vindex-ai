# Vindex AI — UX Implementation Gap Report v1.0

**Date:** 2026-07-22
**Method:** Cross-reference of `VINDEX_AI_UX_SIMPLIFICATION_STRATEGY.md` and `VINDEX_UX_SIMPLIFICATION_AUDIT_2026-07-20.md` (both 2026-07-20) against current code state. This is **not** a new UX audit — no new judgment calls about what's good/bad were made. Every classification below is a factual implementation-status check against already-written recommendations.

**Foundational fact this entire report rests on:**
```
git diff --stat 0070c3c..HEAD -- index.html static/vindex.js static/vindex.css static/*.html static/*.css static/*.js
→ (empty output)
git log --oneline 0070c3c..HEAD -- static/ index.html
→ (empty output)
```
Every frontend file is **byte-for-byte identical** to its state when both source audits were written. This means every `file:line` citation in those two documents is still exactly correct today — nothing needed re-verification by fresh grep, because nothing could have moved. The only things that *could* have changed are backend prerequisites the UI work depends on (G-026, G-030) — those were checked directly against the current Gap Register.

---

## Executive Summary

**Realization rate: 0% of all three sprints.** Not one Sprint 1/2/3 item from either source document has been implemented. This is not a surprising or concerning finding — no frontend work of any kind has happened since these documents were written; every commit since (`0070c3c` → `HEAD`, 2026-07-20 → 2026-07-22) has been backend-only (CONTRACT 01 verification, D22, G-031→G-034). The UX strategy was correctly treated as "written for later," and later hasn't arrived yet.

**The two backend prerequisites that block the two P0 items are also still Open:** G-030 (Next Action consolidation — blocks Top 10 #2) and G-026 (credit panel visibility bug — blocks part of Sprint 2) both remain `Open` in `VINDEX_OPERATIONAL_GAP_REGISTER.md`, unchanged since 2026-07-20.

**Most important synthesis point, not present in either source document:** per the founder's own already-established rule (`project_operating_system_connectivity_audit` memory, 2026-07-20 — *"beta NE čeka P1/P2/P3 — čeka SAMO P0 (CONTRACT 01)"*), **none of this UX debt is a pilot blocker.** CONTRACT 01 is now not just "beta-ready" but production-verified (D3/D9/D22, this session). The honest answer to "what's needed before a real pilot user test" is: **nothing from this report** — it was already decided that UX and pilot timing run in parallel, not sequentially.

---

## Implementation Status — Top 10 UX Problems

| # | Problem | Recommended fix | Status | Evidence | Priority | Next action |
|---|---|---|---|---|---|---|
| 1 | Dashboard: 4 independent AI-narrative sources (Health Index/CC Briefing/Jutarnji brifing/CIO) | Merge into one "today" block, one voice | **NOT IMPLEMENTED** | `vindex.js:1158,1262,1625,16543` unchanged (file identical) | P0 | Sprint 3 — requires backend "which source is master" decision first, same discipline as G-027 |
| 2 | "Sledeća akcija" — 4 non-communicating systems (Cockpit/Matter Intel/CRS/`workflow.py`) | Consolidate to one source of truth | **NOT IMPLEMENTED** — and its blocking prerequisite (**G-030**) is also still `Open` | `VINDEX_OPERATIONAL_GAP_REGISTER.md` G-030 row, unchanged | P0 | G-030 empirical validation (same method as G-027) must happen before *any* code — this is a product decision, not a UI task |
| 3 | Pregled predmeta: 3 score-widgets (data unified by G-027, display isn't) | Visually merge into one display | **Status: Completed** (2026-07-22, commit `c91e0de`). **Verification: Playwright component verification.** **Production: Not required.** **Reason: Pure presentation-layer consolidation. No backend or business logic changes.** | `index.html:811-920`, `static/vindex.css` `.pred-scorecard`/`.pred-scorecard-section` — one shared border/background, `mi-rizik`/`mi-sledeca` hidden (data-level duplicates, kept in DOM so `matter_intel_load()` needs zero JS changes — confirmed 0-line diff on `static/vindex.js`) | P1 | **Closed.** Isolated HTML fragment + actual `pred_renderCockpit`/`pred_renderCaseReadyScore` functions run under Playwright, 0 JS errors, screenshot-confirmed at desktop and mobile width — component-level, not full production E2E (honestly labeled as such, not overclaimed). "Sledeća akcija" consolidation intentionally NOT touched — remains G-030, a separate unresolved decision. |
| 4 | Sidebar: 13 items vs. 5 on mobile | Reorganize to 4 primary + 2 grouped sections | **NOT IMPLEMENTED** | Sidebar markup unchanged | P1 | Touches every page, needs regression testing — correctly scoped as Sprint 2 |
| 5 | AI hub: 7 mode-pills before first question | Group less-used modes, or let system infer intent | **NOT IMPLEMENTED** | `index.html:2715-2722` (`aiws-modes`) unchanged | P1 (P2 for renaming only) | Sprint 3 — larger architectural shell change |
| 6 | "Dokumenti" top-level tab, redirect-only | Remove as nav item | **NOT IMPLEMENTED** | `index.html:3252-3281` (`tab-dok`) unchanged | P2 | Lowest-risk item in the entire roadmap — pure dead-navigation removal, zero dependencies |
| 7 | 2 parallel modal implementations (`modal-overlay`/`vx-modal-overlay` vs. inline `style="position:fixed"`) | Unify to one mechanism | **NOT IMPLEMENTED** | Confirmed still both patterns present (unchanged) | P2 | Verify PWA install modals' differences are intentional before unifying (already flagged as a pre-check in the source doc) |
| 8 | Podešavanja: 22 sections, no progressive disclosure | Apply existing "Detaljni izveštaji" collapse pattern | **NOT IMPLEMENTED** | `index.html:3284+` unchanged | P3 | Lowest priority — Google Principle Test already says current state isn't a violation |
| 9 | Rokovi: 3 export buttons instead of 1 menu | Consolidate into "Izvezi ▾" | **NOT IMPLEMENTED** | `index.html:2647-2682` (`tab-kal`) unchanged | P3 | Sprint 1 — trivial, zero dependencies |
| 10 | Fake search (`title="dolazi uskoro"`) + decorative constellation animation on Dashboard | Remove both | **NOT IMPLEMENTED** | `vindex.js:1467` unchanged | P2 (search) / P3 (animation) | Sprint 1 — trivial, zero dependencies |

**Additionally confirmed unchanged (not a gap, a positive control):** Case Genome panel (`_caseDnaRender`, `vindex.js:16685-17048`) remains the one correctly-structured reference screen — still no L1/L2/L3 violation, still the pattern everything else should copy. This wasn't at risk of regressing since nothing touched it, but worth stating explicitly since the whole strategy document's core recommendation is "copy this pattern," and that pattern is still intact and available to copy.

## Sprint Realization

| Sprint | Items | Implemented | Partially | Not implemented |
|---|---|---|---|---|
| Sprint 1 (lowest risk) | 4 (remove Dokumenti tab, remove fake search/animation, move admin sections behind "Više alata", consolidate Rokovi export buttons) | 0 | 0 | 4 (**0%**) |
| Sprint 2 (medium risk) | 3 (merge 3 score-widgets, sidebar reorg, G-026 fix) | **1** (score-widget merge, 2026-07-22) | 0 | 2 (**33%**) |
| Sprint 3 (higher risk) | 5 (Dashboard consolidation, Sledeća akcija consolidation, AI hub grouping, modal unification, Podešavanja disclosure) | 0 | 0 | 5 (**0%**) |

**Total: 1/12 roadmap items implemented (8%).** First item closed same day as this report, per founder's explicit "Track B, item 1" prioritization (isolated, measurable, low risk, immediately visible) — see `VINDEX_OPERATIONAL_GAP_REGISTER.md` for the closure record if one is added.

## P0/P1/P2 Open Items (carried forward unchanged from source docs)

- **P0:** Dashboard 4-voice consolidation (#1), Sledeća akcija consolidation (#2, blocked on G-030 decision)
- **P1:** Pregled predmeta widget merge (#3, ready — no backend blocker), Sidebar reorg (#4), AI hub mode grouping (#5)
- **P2:** Dokumenti tab removal (#6), Modal unification (#7), Fake search removal (#10)
- **P3:** Podešavanja disclosure (#8), Rokovi export menu (#9)

## Recommended Implementation Order (unchanged from source docs — re-stated, not re-derived)

1. **Sprint 1 items first if/when a UI sprint starts** — zero dependencies, lowest risk, and two of them (#6, #10) directly address the user's very first five minutes.
2. **G-030 empirical validation before touching #2** — this is a product decision (which system becomes the single "next action" source), not a design task, and must not be pre-chosen.
3. **#3 (score-widget merge) is the one item ready to implement independent of any other decision** — data is already unified (G-027), this is pure display work.
4. **#1 (Dashboard consolidation) waits on its own backend "master source" decision**, same discipline as G-027/G-030.

## Assessment: What's Needed for a Real Pilot User Test

**Nothing from this report.** This is the one place this document adds a conclusion the source docs didn't have the context to reach (they predate CONTRACT 01's production verification): CONTRACT 01 is now proven end-to-end in production (D3/D9/D22, `CONTRACT_01_PRODUCTION_VERIFICATION.md`), and per the founder's own already-established rule, beta/pilot timing was decided to run independent of UX/G-030 work, not gated behind it. The UX debt catalogued here is real and worth fixing, but it is not evidence against piloting now — it's a parallel track, exactly as already decided.

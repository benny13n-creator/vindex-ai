# User Journey Certification — Program Omega, Final Sprint 005 (2026-08-06)

Phase 5's own required deliverable: simulate a real lawyer, 08:00, opening the platform. Do they get —
without searching — what's urgent, what's waiting for review, what's overdue, what's done, which case
needs attention, and which document just arrived?

## The scenario, walked through against the actual, now-shipped code

**08:00, lawyer opens Vindex AI.** `dash_load()` fires (`static/vindex.js:1206`), which now — as of this
sprint — loads, in order: Command Center (case list overview) → **Workspace** (`wsLoad()`, new) →
Health Index (restored) → CIO Daily → the "Ostalo za pregled" strip (billing/inactivity/new-doc
ambient notices). Workspace is the FIRST substantive section after the header and quick-actions bar —
not buried, not a 7th tab to find.

| Mission's own question | Where it's answered | Sourced from |
|---|---|---|
| **Šta je hitno** (what's urgent) | Workspace's own "Kritično" bucket, red dot | `case_actions` where `prioritet='critical'`, `status='open'` — Sprint 003's own deterministic Action Engine, not a GPT guess |
| **Šta čeka pregled** (what's waiting for review) | Workspace's own "Za pregled" bucket | `intake_jobs` where `status='awaiting_review'` — Smart Intake's own real, pre-existing review-queue signal, now surfaced as a list for the first time (`OMEGA-004`-adjacent gap, closed for THIS specific data by this sprint's own Workspace read) |
| **Šta kasni** (what's overdue) | Workspace's own "Danas"/"Kritično" buckets (a `rok` in the past would already have surfaced as critical by the deadline-priority rule, `_priority_by_days`) | `case_actions`, `rocista`-sourced |
| **Šta je završeno** (what's done) | Workspace's own "Završeno nedavno" bucket | `case_actions` closed in the last 3 days ∪ `zadaci` marked done in the last 3 days — proven to use a REAL timestamp this sprint (the `"now()"` bug fix), not a broken/empty filter |
| **Koji predmet zahteva pažnju** (which case needs attention) | Every Workspace item carries `predmet_naziv`, clickable via `_dashGoToPredmet` — the SAME navigation helper every other panel on the platform already uses | `case_actions.predmet_id` → `predmeti.naziv` |
| **Koji dokument upravo stigao** (which document just arrived) | The "Ostalo za pregled" strip (formerly "Inbox," this sprint's own fix restored its visibility) shows `dokument` items from the last 24h | `predmet_dokumenti` |

**All of the above without a single search** — no `⌘K` needed, no tab-hunting, no "where do I find X."

## What was NOT true before this sprint, and is now

Before this sprint, the architecturally-correct answer to every question above (`case_actions`,
built and tested in Sprint 003) existed but was reachable ONLY by calling the API directly — a real
lawyer would have seen 3 GPT narrative widgets (2 of which were SILENTLY BROKEN, rendering nothing) and
an Inbox section that only ever showed hearing/deadline items duplicating what Workspace also computed,
with the genuinely unique billing/inactivity signals computed but never once displayed. **The honest
gap this sprint closes**: a lawyer opening the platform before today would NOT have reliably gotten
these 6 answers without hunting; now they do, on the first screen, automatically.

## What is still honestly imperfect (Phase 7 discipline: don't overclaim)

1. **Pre-Sprint-003 cases may under-report** until `scripts/backfill_case_actions.py` (`OMEGA-014`) is
   actually run — `_kcPanelRokovi` (the older deadline panel) is deliberately kept alongside Workspace as
   a safety net for exactly this reason, so "šta kasni" for an old case is not silently lost, just shown
   twice (once via each panel) until the backfill runs.
2. **"Koji predmet zahteva pažnju" only covers deterministic action-tracking** — the 4 demoted GPT
   narrative widgets (`OMEGA-017`) still separately compute their own opinions on the same page; a
   thorough lawyer could still see 2 different "important case" signals if they read both Workspace and,
   say, CIO Daily. Named, not hidden.
3. **Visual vocabulary is not 100% unified yet** (`OMEGA-018`) — Workspace's own critical/high/medium/low
   color scheme is now also used by the new case-detail "Otvorene akcije" panel, but Cockpit's own risk
   badge and the Zadaci panel's own badge still use their own, different-looking conventions.

## Certification verdict

**Certified for the deterministic operational core**: the 6 questions the mission's own 08:00 scenario
asks are all answered, automatically, on first load, from a single primary section, without search —
proven both by code (this document) and by test (`tests/test_omega_sprint005_full_chain_to_workspace.py`,
`tests/test_omega_sprint004_case_to_workspace_flow.py`, `tests/test_omega_sprint004_workspace.py`).

**Not certified as the platform's ONLY voice** — 4 secondary GPT surfaces remain, by deliberate,
risk-conscious choice (not touching live GPT behavior without live-browser verification), not by
oversight. This is the same honest, bounded certification posture every Program Omega sprint has used —
Sprint 003 certified the deterministic action domain, not the whole platform's every AI feature; this
sprint certifies the primary journey, not universal uniformity.

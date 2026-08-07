# Operation Iron Lawyer, Master Sprint 001 — Findings & Triage

21 independent teams (Alpha–Uniform), each investigating a distinct human-experience surface via direct
code tracing of `static/vindex.js`/`index.html` (no live browser tool available — disclosed methodology
constraint, consistent with every prior certification in this program). Read-only investigation phase
complete. This document is the coordinator's triage: which findings are CONFIRMED and get fixed this
sprint (UI-only, safe, deterministic), and which are named as debt (require a product decision, touch
business logic/backend, or are too broad for a safe single-pass fix).

## Triage rule

Per the mission's own FORBIDDEN list: no business logic, legal rules, AI reasoning, Genome, Event Bus, AI
Governance, Security/RLS/Ownership, or Audit changes. A finding is FIXED NOW only if it is a pure
frontend/UI change with no behavioral change to backend logic. Findings that require a product decision
(e.g. which of 5 "case success" scores is canonical) or touch billing/credit logic are named as **DEBT**,
not fixed, and flagged for founder decision.

## Findings requiring a founder/product decision (not fixable as a safe UI patch)

- **IRONLAWYER-DEBT-001** (Gamma): Case Commander is a fully-built, billed (`professional` tier),
  permission-gated backend feature with **zero frontend entry point** — a paying customer cannot ever
  trigger it. Decision needed: wire it up, or delist it from the feature registry/pricing.
- **IRONLAWYER-DEBT-002** (Romeo): 9 more backend routers follow the identical dead-feature pattern with
  zero frontend callers (`region`, `style_checker`, `knowledge_hygiene`, `knowledge_transfer`,
  `strategy_simulator`, `auto_discovery`, `agent_notifications`, `onboarding.py`'s own separate flow,
  `whatsapp_notif`), plus a fully-built duplicate CSV import (`routers/import_klijenti.py`) competing with
  a live cruder one. Backend/product decision, not a frontend fix.
- **IRONLAWYER-DEBT-003** (Bravo/Charlie/Mike/Oscar, converged): the platform shows a case's "how strong/
  risky is this" via **5-7 independently-computed, unreconciled scores** on the same case (CCC health,
  Matter Intel health, Cockpit risk, manual risk field, Genome strength, Case Ready Score, Twin
  probabilities, Copilot success %). This is the single most consequential UX finding of the mission —
  fixing it safely requires picking ONE canonical surface, which is a product decision, not a copy-edit.
  Flagged CRITICAL/HIGH by 4 independent teams.
- **IRONLAWYER-DEBT-004** (Oscar): AI prediction confidence-checking is gated behind an extra paid credit
  ("Proveri pouzdanost predikcije — 1 kredit") rather than shown by default — a billing/credit-consumption
  decision, out of UI-only scope.
- **IRONLAWYER-DEBT-005** (Quebec): systemic lack of ARIA/tabindex across the entire dynamically-rendered
  app (0 ARIA attributes in 22,800 lines; 63 keyboard-unreachable click controls) and styling drift (12%
  shared-button-class adoption, ~26 parallel one-off badge class families). Too broad for a single safe
  pass — the highest-value instance (dashboard primary navigation) is fixed this sprint; full remediation
  needs a dedicated accessibility/design-system sprint.
- **IRONLAWYER-DEBT-006** (Uniform): no request timeout/retry exists on any of the ~300 `fetch()` call
  sites in the app — a stalled connection hangs the UI indefinitely. A shared timeout wrapper is applied
  this sprint to the highest-traffic paths (dashboard, case list, Copilot chat); full rollout across all
  call sites is future work.
- **IRONLAWYER-DEBT-007** (Uniform): case list silently truncates at 200 of N with no "showing X of Y"
  indicator — needs a backend total-count contract change to fix correctly; named as debt rather than
  papered over with a guess.
- **IRONLAWYER-DEBT-008** (Uniform): no draft/progress persistence across a reload/crash mid-flow (Smart
  Intake, CRM forms) — real data-loss risk, but a correct sessionStorage-based implementation needs careful
  design/testing beyond a same-sprint safe patch; named as urgent debt, not swept under the rug.
- **IRONLAWYER-DEBT-009** (Bravo/Echo/Hotel): case-detail "Pregled" tab is a 313-line kitchen-sink screen
  mixing read (status/risk) with admin actions (contract generation, client portal, case closing) with no
  chronological/urgency grouping; deadlines alone appear in 5 separate widgets. Structural redesign, not a
  same-sprint patch.
- **IRONLAWYER-DEBT-010** (November): `identify_case_problems`' wording ("kritičan rok u narednih 7 dana")
  includes already-overdue items but the string doesn't say so, and neither `/workspace` nor `/matter-intel`
  exposes a separate `zakasneli_rokovi` count to the frontend — needs a backend field/string change.
- **IRONLAWYER-DEBT-011** (Lima): no manual chronology entry exists — chronology is AI/system-generated
  only. Adding manual entry is a new capability, a product decision, not a UI polish item.
- **IRONLAWYER-DEBT-012** (Delta): 3 of 5 case-creation code paths are dead/hidden
  (`pred_kreiraj`/`pred-new-modal`, `qiOtvori` quick-create, `bulkOtvori` CSV import) — fully built but
  unreachable. Whether to promote them to visible entry points or delete them is a product decision;
  flagged, not unilaterally resolved either way this sprint.
- **IRONLAWYER-DEBT-013** (Papa/Kilo): most AI response types (Copilot: 14 of ~20 backend intents;
  citations not clickable) render as undifferentiated text — broader structured-rendering work beyond this
  sprint's safe-patch budget beyond the fallback improvement made below.

## Findings fixed this sprint (UI-only, see commit for exact diffs)

Grouped by team; each is a pure frontend change, no business-logic/backend/security change.

1. Smart Intake finalize silently drops `awaiting_review` documents / dead "Kreiraj predmet" button
   (Foxtrot F1, CRITICAL — real bug)
2. Notification priority color-coding dead due to stale key vocabulary (Juliet F1, CRITICAL — real bug)
3. Notification read-state never reaches the server and gets silently reverted (Juliet F2, CRITICAL — real
   bug)
4. Copilot chat shows stale prior case's conversation after switching cases (Papa F2, HIGH — real bug)
5. Evidence "needs review" color dead due to CSS class-name typo (Kilo F4, real bug)
6. Case list (`Predmeti`) renders a silently-blank screen on fetch failure, indistinguishable from broken
   (Sierra S1, HIGH)
7. Case chronology panel blanks silently on fetch failure (Sierra S2)
8. Global search conflates "search failed" with "no results" (Sierra S3)
9. Client billing-rate save shows a bare "Greška"/"Greška mreže" bypassing the app's own centralized error
   helper (Sierra S4)
10. Visible Intelligence Timeline goes stale after a document upload; dead, invisible duplicate
    hronologija widget removed (wastes 2 API calls per case load + 2 more per upload) (Lima F1 / Bravo B2,
    corrected)
11. Cockpit "Otkriveni problemi" and "Hitni rokovi" cards can show contradictory deadline info on the same
    screen with no explanation (November N4)
12. Cockpit problem list has no severity color-coding, silently truncates to 3 with no way to see the rest,
    and has no click-through to the relevant tab (November N1/N2/N3)
13. Breadcrumb shows raw internal tab id `zadaci-g` instead of a label (Alpha finding)
14. "Portfolio kancelarije" (internal Vindex SaaS metrics) nav item shown to every user, dead-ends with
    "access denied" for non-admins (Alpha finding)
15. Closed case has no way to reopen from the case detail screen itself, only via list bulk-select (Delta
    D3)
16. Close-case tooltip claims "Zatvori i arhiviraj" (close = archive) when they are two different actions
    (Delta D2)
17. Workspace items with no linked case render as clickable but silently no-op (Echo E1)
18. Duplicate "Današnji rokovi" panel removed from dashboard now that Workspace's "Danas" bucket is the
    canonical surface (Echo E4 / Hotel H2)
19. Global search (Cmd+K): tasks (`zadaci`) were invisible despite a working backend searcher (India I1)
20. Global search placeholders promised categories that don't exist ("zakone", "rokove") (India I2)
21. Dead, permanently-blank duplicate search button next to the real search bar removed (India I3)
22. Evidence reclassify control disappeared once *any* classification was assigned, making a wrong
    AI-assigned type permanently uncorrectable from the UI (Kilo K3 / Tango T-C)
23. Evidence/classification status was invisible on the primary Dokumenti tab document list (Kilo K2 /
    Tango T-B)
24. The in-case "Analiza dokumenta" shortcut uploads to a different, TTL-bound ephemeral session never
    attached to the case, with no warning it isn't saved permanently (Kilo K5)
25. Copilot chat's default response bubble left literal `**markdown**` asterisks unrendered despite an
    existing formatter (Papa P4)
26. Copilot backend "next action" hints (`akcija`) were computed but discarded; no deep-link button
    (Papa P5)
27. Copilot's `ANALIZA_PREDMETA` success-probability output had no AI-generated disclaimer, unlike the
    rest of the app (Papa P8)
28. Case Genome panel showed no staleness/freshness indicator (Mike M1)
29. Calendar entries (list + month-grid day detail) didn't link to their case, unlike notification-bell
    clicks which do (Tango T-A)
30. Closing a case gave no warning about unbilled time/open invoices (Tango T-E)
31. Case AI summary had no copy-to-clipboard button, unlike every other AI output in the app (Tango T-D)
32. Banned decorative emoji present in the highest-traffic screen (AI response section headers) and
    onboarding copy, violating the project's standing icon-ban convention (Quebec)
33. Animated glow/box-shadow effects violating the project's standing "no glow" Bloomberg-style convention
    (Quebec)
34. Dead onboarding modal wired to a hardcoded no-op function, fully superseded by a second, live
    onboarding flow (Romeo R1)
35. Dashboard's primary case-navigation rows (`kc-panel-row`, `kc-sphere-quad`) were mouse-only, unreachable
    by keyboard (Quebec, partial fix of DEBT-005)
36. Icon-only "remove file" button had no accessible label (Quebec)
37. Vanity firm health-score widget was rendered above the actionable urgent-items panels on the morning
    dashboard (Hotel H3)
38. Dead, unused `/billing/pregled` fetch on every dashboard load removed (Hotel H5)
39. Two same-page fields both labeled "Rizik" (one manual, one AI-computed) with no distinction (Charlie
    C2)
40. Kanban terminal phase label ("Završen") clarified against case status ("Zatvoren") to reduce confusion
    between the two independent lifecycle fields (Delta D4)
41. Shared fetch-timeout helper added and applied to dashboard/case-list/Copilot chat fetches (Uniform
    U1, partial — see DEBT-006 for full-rollout scope)

See git log for the exact commit(s) implementing these with regression coverage where applicable.

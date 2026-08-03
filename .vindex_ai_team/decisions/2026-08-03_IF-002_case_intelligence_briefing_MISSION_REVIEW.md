# Mission Review — IF-002: Per-case AI Briefing button

**Mission Board entry:** `MISSION_BOARD.md`, IF-002.
**Executed by:** Operation Invisible Features (BETA-003), 2026-08-03.
**Status:** DONE.

---

## Architecture Decision

### The finding
`POST /api/intelligence/predmeti/{id}/briefing` (`routers/case_intelligence.py`) is a real, working
integration layer: it chains Lessons Learned, Firm DNA, Knowledge Profile, Client Communication
Profile, Case Patterns, active Alerts, and the Decision Log into one GPT-4o-synthesized recommendation
(next step, reason, key risks, urgency, confidence) — exactly the "bez otvaranja deset ekrana" ("without
opening ten screens") framing in its own docstring. It had zero frontend callers.

### Distinguishing this from a similar-looking existing feature
Before wiring it, checked whether this duplicates the existing "Chief Intelligence Officer" (CIO)
section already live in the app (`vindex.js:17086` `_cioLoad`, calling `/api/cio/daily`/`/api/cio/run`).
It doesn't: CIO is a **cross-case, portfolio-wide** daily briefing (aggregates health across ALL active
cases); `case_intelligence` is scoped to **one open case**. Different question, different consumer —
not a duplicate, both worth having reachable.

### Placement
Added directly beneath the existing "Case DNA" (Case Genome) button/panel in the case-detail view's
"Case Intelligence" section (`index.html:1594-1600`) — same visual pattern (a button, a hint line, a
result mount that stays hidden until populated), so it reads as a natural second capability in an
already-established section rather than a new, disconnected UI concept.

---

## Implementation
`index.html` — new "AI Briefing — sledeći korak" button + hint + result mount, inside the existing
Case Intelligence section.
`static/vindex.js` — new `_intelBriefingLoad(predmetId)` (calls the endpoint, in-flight guard against
double-clicks, matching the existing Case DNA refresh button's pattern) and `_intelBriefingRender(b,
izvori)` (renders next-step/reason/urgency/key-risks/communication-advice, all values passed through
the codebase's canonical `escHtml()` before insertion into `innerHTML` — no raw LLM output written to
the DOM unescaped).
`static/sw.js` — cache bump covered by the same version bump as IF-001 (single frontend deploy).

---

## QA Report

### User Scenario Test
```
Scenario: a lawyer opens a case and wants one clear next action instead of
reading through Genome, Lessons Learned, Firm DNA, and the Decision Log
separately.
Before: the backend could already produce exactly this, but nothing in the
UI could reach it.
After: "AI Briefing" button in the case's own Case Intelligence section ->
one call -> next step + reason + urgency + key risks + communication
advice, rendered inline.

Manually verified: node --check static/vindex.js (syntax valid); escHtml
used for every LLM-sourced string rendered into innerHTML (XSS discipline
consistent with this file's 2026-07-24 XSS sweep, referenced at
vindex.js:14196).
```

### Regression suite
No backend code changed. Full suite: 2306 passed, 1 skipped, 0 failed (unchanged). No frontend test
harness exists in this repo; verified via `node --check` only, not live-browser-tested this session.

### Rollback strategy
Pure frontend addition. No backend/schema change. Revert removes the button/functions; the endpoint is
untouched.

---

## Lessons Learned
Two features that both "aggregate everything into one recommendation" (CIO and this) are not
automatically duplicates — the right question is what's being aggregated FOR (a portfolio vs. a single
case), not whether the pitch sounds similar. Worth the reminder for future invisible-feature sweeps:
don't merge two capabilities just because their one-line descriptions rhyme.

## Founder Summary
A lawyer opening any case can now get a single synthesized "what to do next" recommendation drawing on
lessons learned, firm patterns, risks, and prior decisions on that case — the backend has done this for
a while; it just had no button. Confirmed distinct from the existing portfolio-wide CIO briefing, not a
duplicate of it.

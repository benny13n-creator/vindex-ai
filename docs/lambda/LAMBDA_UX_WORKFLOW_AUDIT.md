# Legal Workflow + UX + Product Audit — Program Lambda, Master Sprint 001

Full E2E path trace (Upload → Intake → Case → Genome → Event → Workspace → Notifications → Dashboard → AI)
and a full lawyer-workday walkthrough, grounded in direct code/frontend reads, not documentation claims.

## Part 1 — E2E path: PASS for the primary path

The main "add document to existing case" path (`POST /api/predmeti/{id}/upload`) is confirmed solid,
concretely, not assumed:
- Frontend calls the endpoint directly (`static/vindex.js:19295`).
- On success, emits `NEW_EVIDENCE_REGISTERED`/`DOCUMENT_ACCEPTED` via the durable Event Engine.
- The registered consequence chain (genome_refresh → timeline_entry → refresh_case_actions →
  project_notifications) means one upload produces real, automatic Genome/`case_actions`/notification
  updates — not a manual multi-step process.
- A real orphan-prevention safeguard already exists for this specific path (Project Sentinel, prior sprint):
  if the DB insert fails after Pinecone ingestion succeeded, the endpoint raises rather than returning a
  false success.

## Part 2 — New findings

| # | Finding | Status | Severity |
|---|---|---|---|
| 1 | Two adjacent top-bar "new case" buttons (`+ Novi predmet` / `+ Iz dokumenta`) with near-identical tooltip promises — both claimed automatic extraction from a document, nothing explained which to prefer. Real confusion risk on the single most important first action a new beta lawyer takes. | **FIXED this sprint** — minimal copy-only clarification (guided/manual-first vs. fastest/document-first framing), no redesign, no button removed/added. Service worker cache bumped so the change actually reaches users. | Moderate-High → Closed |
| 2 | `routers/onboarding.py` — a richer, `/demo-predmet`-capable onboarding system sits fully dead (zero frontend callers, confirmed by direct grep) behind a much thinner live welcome-overlay mechanism | Named as `LAMBDA-003`, not fixed — a product decision (wire it in before beta, or not), not a bug | Medium |
| 3 | `import_klijenti.py`'s CSV import router | Reconfirmed still dead — matches the pre-existing, already-escalated `IF-003` finding, not new | — |

## Part 3 — Dead-route spot check

Cross-checked `scripts/audit_routers.py`'s own claims for `onboarding`, `import_klijenti` against direct
`grep` on both `vindex.js` AND `index.html` (the script's own known blind spot doesn't check the HTML file
directly) — both confirmed genuinely dead by the independent check, not just the script's own bucketing.

## Verdict

The core, highest-traffic path (document upload on an existing case) is solid, verified end to end, not
assumed. One real, live, first-impression UX confusion risk was found and fixed with a minimal, safe copy
change. One genuine product-investment-vs-usage gap is named for a founder decision rather than guessed at.

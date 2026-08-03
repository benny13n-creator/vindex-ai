# Hidden Features Report

**Mission:** Operation Lawyer Day, 2026-08-03 (secondary objective, alongside the day-simulation in
`LAWYER_DAY_REPORT.md`). Consolidates every hidden/disconnected/underused capability found across this
mission and cross-references the more exhaustive prior sweep (`docs/product/FEATURE_DISCOVERY_REPORT.md`,
Operation Invisible Features, same day) rather than repeating it.

---

## New this mission (found during the day-simulation, not previously catalogued)

| Feature | What it does | Status |
|---|---|---|
| **Litigation Intelligence** (`index.html:3065-3131`) | PRO-gated AIWS mode: Judge & Court Profiler, Opponent Intelligence, Similar Cases ("Law Firm Brain"), Outcome Trends | **Fully wired, not hidden** — genuinely reachable, just not previously catalogued in this engagement's running inventory of what exists. Recorded here so it isn't "rediscovered" as a gap by a future mission. |
| **Document drafting** (`nacrti`/`podnesak`, AIWS mode) | Dual-backend draft generation (12 simple document types, 8 structured litigation types) + DOCX export | **Fully wired, not hidden** — same note as above. |
| **Strategy generation** (`strategija`, AIWS mode) | Single-agent and 6-agent-orchestrated case strategy analysis | **Fully wired, not hidden** — same note as above. |

These three are not new capabilities — they were built and wired before this engagement began — but
none had been explicitly confirmed reachable in this engagement's own investigation record until
tonight. Worth the correction: not everything this engagement has been finding is broken; several
substantial features work exactly as intended and simply hadn't been checked yet.

## Confirmed genuinely dead or gapped (evidence-level detail in `WORKFLOW_INTERRUPTION_REPORT.md`)

- **Duplicate-file detection** exists (Smart Intake, exact SHA-256) but only on the unreachable path.
- **True batch upload** exists (Smart Intake) but only on the unreachable path.
- **Hearing-prep export bundle**: does not exist anywhere — a real gap, not a wiring problem (every
  piece it would draw from already works).
- **Lawyer-facing audit log viewer**: does not exist anywhere.
- **Case archiving**: exists and works, but only reachable from the case list's bulk-action bar, not
  from within a case's own detail view.
- **Team comments in global search**: `predmet_komentari` has full CRUD but zero search coverage.

## Resolved: NOT a hidden duplicate

`predmet_beleske` ("Beleške" — private, per-lawyer notes) and `predmet_komentari` ("Komentari tima" —
team-visible comments) were flagged by Operation Invisible Features' census as a possible duplicate
pair needing a "current winner / current loser" unification call. This mission checked the actual UI
copy directly: `index.html:922` explicitly labels Beleške "vidljive samo vama" (visible only to you);
`index.html:1489` explicitly labels the other "Komentari tima" (team comments). **These are two
intentionally distinct features, not a duplicate** — no unification recommendation is warranted. The
only real, narrower gap is search coverage (Finding #8 in the interruption report), not architecture.

## Standing findings from earlier tonight, cross-referenced not repeated

See `docs/product/FEATURE_DISCOVERY_REPORT.md` (Operation Invisible Features) for the full, separately
-investigated census: 12 confirmed-dead routers, 2 real duplicate-feature pairs needing founder
decisions (client CSV import, WhatsApp notifications), and Memory Graph (the most interesting dead
feature found this whole engagement — a cross-case argument/outcome query engine with no automatic way
to populate its own data).

## Tooling note, reconfirmed

`scripts/audit_routers.py`'s known blind spots (documented in the Invisible Features census) were not
re-triggered this mission — this mission's investigation worked from direct code/frontend reads, not
the script's output, throughout.

---

## Net effect on "hidden features" count

Combining tonight's two missions (Invisible Features + Lawyer Day): 2 real invisible features connected
and shipped (GDPR self-service deletion, per-case AI Briefing), 1 real bug fixed that was masquerading
as a already-closed beta blocker (photo upload on the reachable path), 3 features confirmed as
already-working-and-simply-uncatalogued (Litigation Intelligence, drafting, strategy generation), 1
suspected duplicate resolved as intentionally-distinct (notes vs. comments), and a clear, evidence-
backed list of what remains genuinely hidden or gapped for future prioritization.

---

## Update — Operation Beta Lockdown, 2026-08-03 (same day, third pass)

A deeper tenant-isolation/audit/search sweep (`.vindex_ai_team/decisions/2026-08-03_beta_lockdown_isolation_audit_search_INVESTIGATION.md`)
found one major new hidden feature and corrected one prior claim from this same report.

### New hidden feature: the draft staging/approval pipeline
`routers/drafting.py` already stages every AI-generated draft into `staging_memory` with a computed
confidence score (`_stage_draft_for_review`, `:199-228`), and `POST /api/staging/{id}/approve`
(`:300-309`) already promotes an approved draft into `predmet_dokumenti` — at which point it becomes
searchable via the existing document-search branch with zero further work. **Zero frontend references
to "staging" exist anywhere in `vindex.js`.** Same root shape as Smart Intake: a real, working,
tested backend pipeline with no way for a lawyer to reach it. See `BLOCKER_REPORT.md`/`BLOCKER-3`.

### Correction to this report's own earlier claim
This report previously stated "no lawyer-facing audit log viewer exists" without qualification. More
precise: **case-scoped** audit visibility DOES exist — `routers/intelligence_timeline.py`'s "life of
the case" view (confirmed called from `vindex.js:18008`) aggregates `audit_immutable` among 6 sources.
What's actually missing is an **account-wide, cross-case** activity view, and — a separate, larger
finding — roughly 80% of the audit system's own defined action taxonomy (`AUDITABLE_ACTIONS`, 24 types)
never fires in production code at all. Full detail in `BETA_LOCKDOWN_REPORT.md`.

### Critical finding from the same sweep, not a "hidden feature" but load-bearing here
`GET /api/zadaci/predmet/{predmet_id}` had zero ownership verification — a live, exploitable
cross-tenant task-data leak, found by the same investigation pass that produced the corrections above.
Fixed same night (`BL-001`). See `BLOCKER_REPORT.md` and `docs/product/BETA_LOCKDOWN_REPORT.md` for
full detail — recorded here only because it was found via the same sweep, not filed as a "hidden
feature" (it's a missing security check, not an undiscoverable capability).

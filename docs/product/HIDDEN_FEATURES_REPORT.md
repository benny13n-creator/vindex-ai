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

# Governance Metrics — Methodology

**What this file is**: the methodology for measuring the Mission Olympus governance board *itself* — is
it complete, is it non-overlapping, is it actually being used, is it catching things. This is distinct
from `METRICS.md`, which tracks Vindex AI *product* metrics (ICS, CIC, Reliability Score, etc.) — one of
which (Metrics Guardian, Agent 31) is itself a *subject* this file measures, not a metric this file
reports. Read `docs/architecture/OLYMPUS_BACKTEST_VALIDATION_REPORT.md` for the actual numbers from this
mission's own first measurement; this file defines how to measure them again next time, matching every
other metrics file in this project's own established discipline (`NEXUS_ICS_SCORE.md`'s "Recomputation
note", `METRICS.md`'s own cross-run methodology notes).

## The 7 metrics, and how each is computed

1. **Number of implemented agents** — a plain count of charter files under `.vindex_ai_team/agents/`
   that actually exist and match `AGENT_CATALOG.md`'s roster (not a target, not an intention — a file that
   exists and was read to confirm its content matches its catalog entry).
2. **Responsibility coverage** — for every layer/role the founder's mission charter named, is there a
   Responsible party in `AGENT_RESPONSIBILITY_MATRIX.md`? Denominator = every named Olympus role from the
   founder's own mission prompt (Layers 1–6, all named agents including the 4 "dodatni agent" additions).
   Numerator = how many have an actual, filed charter with a distinct, non-overlapping scope statement.
3. **Responsibility overlaps** — count of activities in `AGENT_RESPONSIBILITY_MATRIX.md` with more than
   one Responsible party. Target 0, verified mechanically (one Responsible-column value per row, checked
   for duplicates).
4. **Uncovered areas** — count of founder-named layers/roles with no corresponding charter file or RACI
   row. Target 0, verified against the founder's original mission prompt text directly, not against this
   mission's own after-the-fact summary of it (to avoid the same "re-derive from memory instead of the
   source" risk this project's own history has been burned by before).
5. **Number of defined review gates** — count of distinct rows in `QUALITY_GATES.md`'s table (the Mission
   Olympus extension) plus `REVIEW_GATES.md`'s original table (the two are additive, not overlapping sets
   of gates).
6. **Number of automated quality checks** — count of gate states with a fixed enum (i.e., mechanically
   verifiable, not free-form prose) across both `REVIEW_GATES.md` and `QUALITY_GATES.md`. A role with "no
   fixed enum" (advisory-only roles) does not count toward this number — it measures mechanically-checkable
   gates specifically, per the mission's own request ("broj automatskih kvalitetnih provera").
7. **Estimated development-quality impact** — **not a number to invent**. The only honest way to estimate
   this is the backtest itself: for each historical mission this governance layer is tested against
   (Nexus, Sentinel, Atlas, Ledger, Phoenix, Keystone), did the relevant new agent's charter, applied
   faithfully, actually catch the same finding that mission's own ad hoc investigation found — or something
   it missed? A backtest that catches real, previously-known findings is evidence of impact; a backtest
   that finds nothing new and nothing old is evidence the charter needs revision before being trusted with
   real quality-gating authority. **This file does not report a percentage-improvement claim** — this
   project's own evidence-based-claims discipline (`docs/security/PUBLIC_SECURITY_CLAIMS.md`'s existing
   norm, applied here by analogy) requires a claim like "this layer improves quality by X%" to be backed by
   a controlled before/after comparison this mission does not have the data to run. What this file *can*
   report, honestly: how many of N historical findings the new roster would have caught, stated as a
   fraction with the actual findings named, not a synthesized percentage.

## How to recompute these metrics for a future mission

Same discipline as `NEXUS_ICS_SCORE.md`'s own "Recomputation note" and `METRICS.md`'s cross-run
methodology sections: use the same denominators (the founder's original Mission Olympus prompt's named
roles, not a paraphrase of it), append new rows for any newly-added agent rather than redefining what
"coverage" means, and state explicitly whether a figure is comparable to a prior run or represents a
methodology change (exactly the correction this same mission had to make to Keystone's own ICS/CIC
figures — see the top of `docs/architecture/KEYSTONE_FINAL_READINESS_REPORT.md`).

## Where the actual current numbers live

`docs/architecture/OLYMPUS_BACKTEST_VALIDATION_REPORT.md` (this mission's own first measurement) and the
Mission Olympus section of `.vindex_ai_team/METRICS.md` (the dated, cross-run-comparable record).

# Phase 0.5 — Decision Review

**Status: TEMPLATE — no data collected yet.** This document defines the
decision criteria *before* any Phase 0.5 numbers exist, per founder
instruction (2026-07-23): *"To sprečava da odluka bude doneta na osnovu
entuzijazma."* Same discipline as `G030_NEXT_ACTION_DECISION_MODEL.md` —
the framework is written first, the decision is filled in after, and the
framework itself is not allowed to change once real data starts arriving
(same "don't change the measuring instrument mid-experiment" rule that
already applied to `retrieval_agreement`).

Fill in the sections below only after `evaluation/phase_0_5/report.py`
has real output across the full curated dataset (not a partial run).

---

## Inputs required before this document can be completed

- [ ] `compare.py` output across ALL cases in the dataset manifest (not a subset)
- [ ] The per-profile matrix (`report.py`'s "MATRICA PO TIPU PREDMETA" section)
- [ ] `FAILURE_LOG.md` populated for every clear loss on either side
- [ ] `changed_lawyer_reasoning` counts
- [ ] `preferred_for_drafting` counts

## The three possible outcomes — criteria fixed in advance

### GO
LRE wins or ties on a majority of metrics **overall**, does not lose
badly on any single metric (no metric where Genome beats LRE by a wide,
consistent margin), and the `changed_lawyer_reasoning` count for LRE is
greater than zero across the dataset (if LRE never changed a lawyer's
mind on anything, "GO" is not defensible regardless of averaged scores).
→ Proceed to Phase 1 (Genome field migration) as scoped in
`LEGAL_REASONING_ARCHITECTURE.md` §1/§12.

### GO WITH FIXES
LRE wins on most metrics but the profile matrix shows it is
**meaningfully worse in one or more specific case-type categories** (not
noise — a consistent pattern across multiple cases of the same profile),
or `FAILURE_LOG.md` shows a recurring, fixable root cause (e.g.
"Evidence mapping" appearing in 3+ entries). → Do not migrate Genome's
fields yet. Fix the identified, specific weakness first, re-run Phase 0.5
on the affected profile category only (not the whole dataset again), then
re-evaluate.

### NO GO
LRE loses on a majority of metrics, or wins only on metrics that don't
matter for practical use (e.g. wins on "tačno identifikovane činjenice"
but loses badly on "korisnost za izradu podneska" and
"promenilo_odluku_advokata" stays at zero) — a technically-more-structured
answer that a lawyer would not actually trust or use is not a win. →
Phase 1 does not happen. LRE Phase 0 infrastructure stays in place
(read-only, wired to nothing) for a future re-attempt after a
architecture change, but is not migrated into anywhere user-facing.

---

## Filled-in decision (complete only when data exists)

**Date:**
**Dataset size / composition:**
**Outcome: GO / GO WITH FIXES / NO GO**
**Evidence (numbers, not impressions):**
**If GO WITH FIXES — specific fix(es) required before re-evaluation:**
**Founder sign-off:**

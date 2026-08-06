# Tau 005 Handover — What This Sprint Found But Didn't Fix

Program Tau, Master Sprint 004 mapped the whole platform's GPT reasoning pipeline for the first time (prior
sprints scoped to 4 files). It found the fragmentation problem Tau 002/003 fixed for those 4 files is much
larger platform-wide. This document is the priority-ordered handover for whichever sprint picks this up
next — not a demand that it be Tau 005 specifically.

## If the next sprint has the appetite for ONE more Sigma-005-scale migration

**`court_predictor.py` (`TAU-011` + `TAU-014`)**. This is the single highest-value target found this
sprint: a live, paid, 7-endpoint feature family that accepts a real case ID and never uses it. Fixing this
means a lawyer's court-outcome prediction actually reflects that case's current Genome/evidence/documents,
not just whatever text got typed into a form that call. Bundle `TAU-014` (citation grounding for the
win-probability number) into the same sprint since both live in the same file and a context-aware rewrite
is the natural place to also add source citations. Use Sigma 005's Case Commander migration as the
template: forensic-verify live-caller status per endpoint first (this sprint found `court_predictor.py` is
definitely live, but didn't verify EACH of the 7 endpoints individually), then migrate onto
`build_case_context()` (full or lightweight mode per endpoint's own needs), preserving exact existing
response shapes since these are confirmed-live consumers.

## If the next sprint wants breadth over depth

**`TAU-012`** — the 17+-file migration backlog. Don't attempt all of them in one sprint; pick the 3-4
highest-traffic ones (this sprint didn't measure traffic — that's its own first task) and migrate those,
naming the rest forward again. `hearing_cc.py` is the single most duplicative one (a full 7-table bespoke
"gather everything" builder, functionally overlapping `build_case_context()` almost entirely) — good
first target since the migration is more mechanical (swap an existing rich builder for the canonical one)
than `court_predictor.py`'s (build case-awareness from near-zero).

## If the next sprint wants to expand the Case Context contract itself

**`TAU-013`** — add `client_history`, `previous_strategies` (both already have real data,
`client_twin_profili`/`case_patterns`/`lessons_learned`), and resolve `rokovi` vs `rocista`. This is a
schema-expansion task, not a migration task — lower risk, but touches the contract every future consumer
will inherit, so it deserves its own careful design pass (should `OCR metadata` become a 15th field, or
live inside `document_summaries`? that wasn't decided this sprint).

## If the next sprint is security-focused

**`TAU-015`** — the SEC-003 prompt guard threshold gap. Needs a real false-positive test matrix against
Serbian legal text before touching `BLOCK_THRESHOLD` or adding new patterns — don't rush this one either,
it's exactly the kind of security-relevant tuning that needs its own dedicated rigor.

## What NOT to do

- Don't build a 2nd context builder alongside `build_case_context()` for any of the migration targets —
  every one of Tau 002/003/004's own findings assumes reuse, not a parallel system.
- Don't fix `TAU-011` and `TAU-012` in the same sprint unless traffic data justifies it — `TAU-011` is a
  correctness/trust issue (predictions ignoring real case state); `TAU-012` is a consistency/duplication
  issue. Different urgency, don't conflate.
- Don't expand the Case Context contract (`TAU-013`) at the same time as a big migration (`TAU-011`/`012`)
  — changing the target while migrating onto it compounds risk for no benefit; sequence them.

## What's already solid, don't re-litigate

`shared/case_context.py`'s own 13-field contract, the Document Visibility Engine (500/1000-doc scale
proven twice now), the decision-boundary work in `case_intelligence.py`/`copilot.py`/`morning_briefing.py`,
and `legal_reasoning_engine.py`'s SOURCE-n grounding pattern are all confirmed sound this sprint — build ON
them, don't re-verify them from scratch every sprint the way this whole program has (correctly) done for
NEW claims, not settled ones.

# DECISION_ARCHITECTURE.md — Operation Singular Intelligence, Mission 001, Team C

Architecture only, per this mission's own Phase 1 rule ("Do NOT implement yet. Only produce
architecture"). No code in this document was implemented this mission.

## What Case Commander already is (re-verified)

`routers/case_commander.py`'s decision core (`_kanonski_nalazi()`) makes exactly one call —
`build_case_context()` — and reads `readiness`/`missing_evidence`/`active_actions` straight off it.
Zero independent recomputation, zero unguarded GPT decision field (its 2 narrative fields —
`protivnikova_strategija`, `sudska_praksa` — are `gpt_advisory`-tagged and structurally barred from
ever influencing status/priority/risk). This confirms both prior Single Brain missions' conclusion:
**the decision core requires no new intelligence to become an Executive Interpretation Layer.**

## The premise correction

Both prior missions assumed "wire up Case Commander" means adding a new UI surface. **It doesn't need
to** — `routers/case_intelligence.py`'s "AI Briefing" / "Winning Strategy Brief" panel already
independently arrived at nearly Case Commander's exact design (canonical core from `build_case_context()`
+ 2 quarantined GPT-advisory fields) via an earlier, separate sprint, and it already has a live frontend
caller (`_intelBriefingRender`/`_winningBriefRender`, `static/vindex.js` ~16918-17042). Two populated,
independently-evolved implementations of the same design exist; Case Commander is not filling an empty
slot, it's a redundant twin of one that's already live.

## What genuinely still needs consolidation before EITHER can be called "the" executive layer

1. **`services/case_pipeline.py::_step_copilot_preporuka`** renders "Copilot preporuka" directly beside
   the Case Ready Score checklist, sourced from `identify_case_problems()` — NOT from `case_actions`/
   `top_open_action()`. Different algorithm, same category, can disagree with the AI Briefing panel's
   `sledeci_korak` on the same case.
2. **`routers/copilot.py::_handle_predlozi`** — independent generator, granular items not rendered
   (summary count only), lower collision risk but still a live independent voice.
3. **`routers/zastarelost.py`** — a self-contained date-calculator UI, lowest collision priority.
4. `build_case_context()` does NOT aggregate `calculate_case_ready_score` (setup-completeness — a
   deliberately separate question per `READINESS_AUTHORITY_SPEC.md`, not a gap) nor
   `case_intelligence.py`'s institutional-memory domain (`lessons_learned`/`firm_dna`/`case_patterns`,
   never in `build_case_context`'s scope by Tau Sprint 002's own design).

## Sequencing risk if activated naively

Wiring EITHER Case Commander OR a "fixed" AI Briefing panel into a NEW UI slot, without touching (1)-(3)
above, does not consolidate anything — it adds a 3rd voice next to 2 that already exist, reproducing the
exact "duplicate readiness, one layer down" pattern Single Brain Mission 002 already had to fix once for
the numeric Case Ready Score.

## Two viable paths (neither implemented this mission)

**Option A — consolidate first, activate second.** Close `SINGLEBRAIN2-DEBT-001`: retire/redirect
`_step_copilot_preporuka` and `_handle_predlozi` onto `top_open_action()` (or a documented
CANONICAL_OWNER pattern mirroring `READINESS_AUTHORITY_SPEC.md`). Only then does either Case Commander
or the AI Briefing panel enter a genuinely de-duplicated field.

**Option B — activation absorbs consolidation.** Scope the activation work itself as: Case Commander's
canonical core REPLACES (not joins) the AI Briefing panel's existing UI slot, AND the Case Ready Score
panel's `copilot_preporuka` sub-widget is retired/redirected onto the same source in the same change.
This closes `SINGLEBRAIN2-DEBT-001` as a side effect of activation, with no separate mission required.

**What is explicitly unsafe**: adding a new Case Commander panel alongside the AI Briefing panel and
`copilot_preporuka` widget, unchanged. This is additive, not consolidating.

## What Case Commander needs to reach full parity with what's already live (2 real gaps, not new intelligence)

1. **Setup-completeness**: if meant to fully replace the Case Ready Score panel (not just sit beside
   it), it needs to also surface `calculate_case_ready_score`'s output — trivial to wire (the function
   already exists and is already readiness-capped), currently simply not called from this file.
2. **Institutional memory / Firm DNA**: if meant to replace the Winning Strategy Brief panel outright, the
   `lessons_learned`/`firm_dna`/`case_patterns` domain needs composing in — either as a new optional
   section of `build_case_context()`, or by the frontend calling both endpoints and merging. This is
   composition of already-existing canonical/quarantined sources, not new scoring — but it is real,
   non-trivial work.

## Recommendation for this mission's own implementation phase

**Full Case Commander activation is deferred, consistent with both prior missions' own caution.** The
risk of creating a new, immediately-visible collision (per the sequencing analysis above) outweighs the
value of activating it partially within this mission's remaining scope. This mission instead implements
the lighter-touch, safe mitigation available today: explicit disclosure labels on `health_index.py`'s
"Chief Partner — Direktiva za danas" and `cio.py`'s "Preporuka za danas" (the Command Center's 2
un-reconciled GPT recommendation surfaces, per `SEMANTIC_MAP.md` §11), so a lawyer can at least SEE that
these are independent AI suggestions rather than the platform's single canonical answer — a Truth
Contract compliance fix, not a consolidation. Full Case Commander/AI-Briefing/Copilot-preporuka
consolidation (Option A or B above) is named as `SINGULAR-DEBT-001`, the explicit recommendation for
the next mission.

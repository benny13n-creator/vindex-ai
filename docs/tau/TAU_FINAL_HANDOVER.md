# Tau Final Handover — Where Consolidation Stands, and What "One System" Still Requires

Program Tau, Master Sprint 008 migrated `routers/cio.py` — the founder's own stated expectation was that
this would be the last big dedicated AI-consolidation sprint. This handover is written accordingly: not
"what's the next single-file migration" (every prior Tau handover's own shape), but an honest accounting of
what IS now consolidated, what genuinely ISN'T yet, and what the founder's own closing question — "does
Vindex AI work as one operational system, or a set of excellent individual functions, across an 8-hour real
workday" — actually requires answering.

## What is now consolidated (verified, not asserted)

`shared/case_context.py::build_case_context()` is read directly by 7 executive/reasoning surfaces now:
`case_intelligence.py`, `court_predictor.py`, `morning_briefing.py`, `hearing_cc.py`, `case_commander.py`
(both its single-case and portfolio-wide paths), and `cio.py` (this sprint). All 7 structurally cannot
disagree about a case's own readiness/gaps/actions, because there is exactly one computation to disagree
with — proven directly this sprint by feeding one mocked canonical result through 4 different surfaces'
own interpretation logic and confirming identical agreement, not just architecturally inferred. The
deterministic-cap GPT-boundary mechanism (readiness constrains a GPT-claimed number) has now been proven 4
times, in 2 different directions (capping a success score down for a bad case — Court Predictor, Hearing
CC; capping a risk score down for a good case — `cio.py`, this sprint) — strong evidence the PATTERN
generalizes, not just the specific instances.

## What is genuinely NOT yet consolidated — named precisely, not glossed over

**`routers/health_index.py`** — found this sprint's own Phase 1 census, NOT migrated. A complete,
independent 6-component "Firm Health Score" with its own GPT-decided "Chief Partner" recommendation system,
fed by a wholly separate scoring model, never touching `case_actions`/`build_case_context()`/Workspace at
all. This is architecturally the SAME class of problem `cio.py` had — arguably a LARGER one, since it has
its own GPT-decided recommendation layer on top of its own independent scoring, not just independent
scoring feeding an otherwise-similar narrative synthesis. **This is the single highest-priority target for
any future consolidation work**, if the founder decides more is warranted before beta.

**`TAU-017`** — `cio.py`'s own former sibling finding — is now closed by this sprint's own migration (the
adversarial predmet_id/kriticnost/kriticni_rok checks close the specific GPT-boundary gap that debt item
named). `health_index.py`'s own `_compute_chief_partner` is a NEW, analogous, still-open violation —
formalize as its own debt item, don't fold it into `TAU-017`'s own closed text.

**The risk_engine duplicate-computation family (`TAU-012`, Tau 007's own finding)** — `zadaci.py`,
`api.py::predmet_workspace`, `matter_intel.py` (which also carries its own pre-existing `GAMMA-003`),
`ccc.py`, `dashboard.py` (both `command_center`'s own stale-risk-blob parsing AND `matter_health_score`'s
own direct risk_engine call) remain unmigrated. None is GPT-decided (confirmed clean on that specific axis
by Tau 007's own audit), but each is a live drift risk in the same shape `case_commander.py` had before
Tau 007.

**`dashboard.py::command_center`'s own `ai_preporuke`** — a rule-based (not GPT-decided, so not a Phase 5
violation) but still independent prioritization heuristic running alongside `case_actions`/Workspace's own
canonical next-action list. Found this sprint's own Phase 1, not previously named anywhere.

## The founder's own closing question, and what would actually answer it

"Does Vindex AI work as one operational system across an 8-hour real workday, or a set of excellent
individual functions?" is NOT answered by counting how many files call `build_case_context()`. It requires a
different kind of evidence than any Tau sprint's own methodology (forensic file-by-file migration,
adversarial unit tests, structural AST proofs) can produce alone: a full-day, cross-feature SIMULATION —
the same method `project_night_shift_2026_08_02.md`'s own "Lawyer Day" and "Zero-Touch Case" runs used
earlier in this whole engagement, which found real, consequential gaps (a "fixed" upload path that was
fixed for one endpoint but not the one a real lawyer's own frontend actually called) that no amount of
subsystem-level correctness could have surfaced on its own. Recommend this — not another single-file
migration — as literally the first candidate task if a next session picks this up, matching the founder's
own explicit framing that the "final gate before serious beta testing" is a workflow question, not an
architecture-purity question.

## What NOT to do

- Don't treat `health_index.py` as a small follow-on to squeeze into a "cleanup" sprint — it has its own
  independent scoring model AND its own GPT recommendation layer, likely comparable in migration effort to
  `cio.py` itself, not a quick pass.
- Don't build a shared executive-context helper across `cio.py`/`health_index.py`/the remaining
  `risk_engine` family — reconfirmed a 5th time this program that request shapes differ enough (`cio.py`'s
  own portfolio-of-compact-objects shape vs. `case_commander.py`'s own single-case shape vs. whatever
  `health_index.py`'s own 6-component structure turns out to need) that a forced shared abstraction would
  misfit at least one of them.
- Don't assume "consolidated onto canonical sources" is the same claim as "works as one system for a real
  workday" — this sprint proves the former for `cio.py`; it does not, and was never designed to, prove the
  latter for the platform as a whole.

## What's already solid, don't re-litigate

`shared/case_context.py::build_case_context()` as the single reasoning-and-context source, proven now
across 7 consumer modules of at least 3 genuinely different shapes (single-case injection, portfolio-loop
injection, duplicate-computation-elimination). The deterministic-cap GPT-boundary pattern, proven 4 times
in 2 directions. `shared/genome_validator.py::validate_predmet_reference`'s own reuse for a 2nd
cross-cutting concern (Case Commander's cross-case findings, now CIO's own portfolio findings) — confirms
it's a genuinely general-purpose "does this reference a real entity in scope" checker, not a one-off.

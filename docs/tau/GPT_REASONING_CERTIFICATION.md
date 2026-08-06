# GPT Reasoning Certification — Program Tau, Master Sprint 004

Certifies the state of GPT legal-reasoning quality across the platform against this sprint's own mission:
"platforma mora početi da koristi GPT kao vrhunskog pravnog analitičara, a ne kao generatora teksta."

## Certification scope

This certifies the state found and the fixes made — it does NOT certify that every GPT call on the
platform now reasons over complete, grounded context. That claim would be false; see the debt items below.

## 1. Context completeness

**Certified**: `case_intelligence.py`, `copilot.py`, `morning_briefing.py` (the 3 modules Tau 002/003
already migrated) see documents + Genome (narrow slice) + evidence + deadlines + actions + readiness
together, via the canonical `build_case_context()` contract or its own sub-helpers.

**NOT certified**: 17+ other case-linked files (`TAU-012`) reason over their own bespoke, independently
maintained context — no guarantee of completeness or consistency with the canonical picture.
`court_predictor.py` (`TAU-011`) is the sharpest failure: 7 live, paid endpoints accept a real case ID and
never use it to see that case's actual tracked state at all.

## 2. Decision boundary (carried forward from Tau 003, re-verified not regressed)

**Certified, re-confirmed this sprint**: `case_intelligence.py`, `copilot.py`, `morning_briefing.py`'s
flagship call site still compute priority/next-action/deadline/risk deterministically — no regression
found across Phase 1-6's own re-reading of this code.

**NOT certified**: `strategija.py`'s advisory labeling (Tau 003) and `court_predictor.py`'s decision logic
were not re-audited for NEW decision-boundary violations this sprint (out of this sprint's own Phase 3
scope, which focused on verifying Tau 003 held rather than re-sweeping the whole platform).

## 3. Evidence grounding (this sprint's own Phase 4 finding)

**Certified**: `services/legal_reasoning_engine.py` (SOURCE-n, unwired but structurally sound),
`case_dna.py`'s `kontradikcije` field, `evidence_graph.py`'s `OSPORAVA` edges, and — **new this sprint** —
`case_dna.py`'s `najslabija_tacka` field (previously ungrounded, now carries the same DOK-XX grounding
requirement as `kontradikcije`, validated by a new `shared/genome_validator.py` check).

**NOT certified**: `snaga_predmeta_procent` (internal consistency checked, not externally grounded — a
real but different kind of check than `najslabija_tacka` now has) and `court_predictor.py`'s win-probability
(`TAU-014`, no citation grounding at all).

## 4. Scale (Phase 5)

**Certified**: 300 deadlines, 50 contradictions, and 20-year-old cases all pass through
`build_case_context()`'s own pipeline correctly — proven by `tests/test_tau004_extreme_scale.py`, not
asserted. 500/1000-document scale was already certified in Tau Sprint 002.

## 5. Adversarial robustness (Phase 6)

**Certified**: prompt injection embedded in document content (the "malicious OCR" attack, using the
established dense-payload pattern) is still correctly blocked by SEC-003's guard, no regression.

**NOT certified**: a subtler, single-phrase injection variant scored below the guard's own block threshold
during exploratory testing (`TAU-015`, not fixed — see the debt item for why). Duplicate evidence rows are
silently double-counted (`TAU-016`). Chronological implausibility in `timeline` is not validated
(`TAU-016`). Statute/article citations outside `legal_reasoning_engine.py` are not grounded against a real
legal corpus anywhere (`TAU-016`, and `_validate_clan_brojevi` is confirmed a plausibility check, not an
existence check).

## Overall verdict

The 3 modules Tau 002/003 already migrated are meaningfully more trustworthy after this sprint's own
`najslabija_tacka` grounding fix and past/upcoming hearing labeling. The platform AS A WHOLE is not yet
"GPT as legal analyst, not text generator" — the majority of case-linked GPT call sites (17+ files) still
reason over independently-maintained, unverified context, and `court_predictor.py` specifically produces
predictions that don't consult the case they claim to be about. This sprint's own honest contribution is
mapping that gap precisely (`GPT_CONTEXT_MAP.md`), not closing it — closing it is `TAU-011`/`TAU-012`'s own
future scope, sized correctly as multi-sprint work, not something a single sprint could safely rush.

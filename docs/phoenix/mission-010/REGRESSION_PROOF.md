# Mission 010 — Regression Proof

## Claim 1 — RAG retrieval doesn't break generation when unavailable/failing

- `test_generate_draft_skips_retrieval_when_rag_unavailable` proves `_RAG_AVAILABLE=False`
  produces a normal successful draft with no RAG block in the extraction prompt.
- `test_generate_draft_survives_rag_retrieval_failure` proves a `retrieve_documents` exception
  (network/auth failure) still produces a successful draft — fail-open, matching `/api/podnesak`'s
  own established resilience pattern exactly.

## Claim 2 — the critique pass only changes output when it finds a real problem

- `test_generate_draft_critique_leaves_clean_draft_unchanged` proves a critique response with no
  reported problems leaves the draft byte-identical.
- `test_generate_draft_critique_neutralizes_hallucinated_article_number` proves a critique
  response that DOES report a problem replaces the flagged content — this is the mission's
  flagship reproduction of the original CRITICAL scenario.
- `test_generate_draft_critique_failure_still_returns_draft_with_applied_false` proves a
  critique-pass exception still returns the (unreviewed) draft rather than blocking the response
  — same never-raise guarantee `_critique_and_refine_draft`'s own docstring commits to.

## Claim 3 — the compliance report (deterministic, not AI-generated) is unaffected

The critique pass runs on `nacrt_tekst` BEFORE `compliance_tekst` is appended (fix log, step 6
vs. step 7) — `test_generate_draft_critique_neutralizes_hallucinated_article_number` confirms no
`VINDEX COMPLIANCE` block leaks in for a type with `compliance_tip=None`, and the pre-existing
`test_generate_draft_includes_compliance` (unchanged assertion, RAG disabled) confirms a type
WITH `compliance_tip` still gets its deterministic report appended exactly as before this
mission.

## Claim 4 — both drafting surfaces stay in sync by construction, not convention

`test_both_drafting_surfaces_import_the_same_critique_prompt` and
`..._izvori_kontekst` use `is`-identity checks (not just value equality) to prove
`routers.drafting` and `drafting.router` reference the literal same object from
`shared/drafting_grounding.py` — a future edit to one can't silently diverge from the other.

## Claim 5 — no pre-existing test lost coverage

All 5 modified tests in `tests/unit/test_drafting.py` kept every original assertion; the only
addition was the `_RAG_AVAILABLE=False` patch (required to avoid a newly-introduced real network
call) and, for the first test, a new `critique_applied is True` assertion (additive).

## Subsystem regression

240 tests across `drafting/`, `routers/drafting.py`, `shared/drafting_grounding.py`,
`court_predictor.py`, `voice_realtime`, and the frontend structural suite: **240 passed,
0 failed.**

## Full-suite regression

See `TEST_RESULTS.md` for the exact before/after counts.

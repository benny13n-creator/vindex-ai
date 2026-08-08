# Mission 014 — Root Cause Analysis

## Root cause

`_generiši_cio_izvestaj` was written with a cost-conscious cap (40 cases) as a reasonable
engineering default long before the portfolio-scale question ("what happens past 40") was a live
concern. As the debt register's own framing notes, fixing the cap or its ordering requires a
genuine tradeoff decision (query/GPT cost at scale vs. completeness; which cases best represent
a necessarily-partial sample) that only the founder can make. But nobody had separately asked
"does the RESPONSE at least say when it's incomplete" — a materially smaller, purely additive
question that doesn't require resolving the harder one first.

## Why disclosure-only is the correct scope for this mission

This mirrors the exact reasoning already established for `-047` (Mission 009, Court Predictor
grounding disclosure) and `-015`/`-013` (Missions 009/010, drafting critique disclosure): when a
real limitation can't be cheaply removed, honestly surfacing it is a legitimate, bounded fix in
its own right — not a consolation prize. A lawyer who knows their CIO report only covers 40 of
57 active cases can act on that (check the rest manually, ask for the cap to be raised); a lawyer
who doesn't know cannot.

## Why the count query is fail-soft while the main fetch stays fail-hard

This is the same "core data vs. disclosure metadata" distinction already applied throughout this
whole engagement (e.g. Mission 013's `matter_health_score` distinguishing a timeout on its
ownership check from every other query). The `predmeti` fetch IS the report — its failure must
surface as a real error, not a false "0 cases" result. The count query only ADDS an honesty
signal on top of an otherwise-complete report; its own failure degrading to "truncation status
unknown" (silently omitting the disclosure, not fabricating a wrong one) is the correct fail-soft
behavior, matching this program's repeated "never fabricate, default to the safer/more honest
state" pattern.

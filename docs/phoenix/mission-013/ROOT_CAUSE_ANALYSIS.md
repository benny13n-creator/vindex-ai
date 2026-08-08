# Mission 013 — Root Cause Analysis

## `-040` — no per-call/per-endpoint timeout

`asyncio.gather(..., return_exceptions=True)` was correctly adopted across these endpoints to
prevent one query's FAILURE from taking down the whole aggregate response — a real, already-
solved problem. But `return_exceptions=True` only catches exceptions that are actually raised;
it does nothing for a query that simply never returns (a slow index, a connection pool
exhaustion, a network partition). Nobody had layered an overall time bound on top of the
already-correct per-query failure isolation — the 2 concerns (partial failure vs. total latency)
look similar but need different mechanisms, and only the first had been addressed.

## `-041` — no explicit app-level upload timeout

`fetch()` has no built-in timeout — by design, matching the browser's own default HTTP client
behavior. Every other network call in this frontend shares the same gap; `pred_upload_doc` was
singled out as the highest-traffic, most case-critical instance (the primary path for a lawyer
getting a document INTO the system) rather than a uniquely broken one.

## Why bounding the OUTER gather/fetch (not every individual query) is the correct scope

The debt register's own suggested implementation ("`asyncio.wait_for` wrapping across the
highest-traffic endpoints' 10+ parallel queries EACH") could be read as "wrap all 10+ queries
individually." This mission instead wraps the single outer `gather()` call (or the single
standalone fetch) per endpoint — functionally equivalent for the user-facing goal ("does this
page load in bounded time"), but a dramatically smaller diff (1 wrapping call per endpoint
instead of 10+), and actually MORE useful: a lawyer cares whether their dashboard loaded in
reasonable time, not which of 13 individual queries specifically was slow.

## Why `-041`'s scope is 1 endpoint, not all upload paths

This frontend has 6+ distinct upload call sites (case documents, playbook, portal, admin law
corpus, freeform doc analysis, Smart Intake). Hardening all of them in one mechanical pass would
multiply this mission's diff size without a correspondingly higher payoff — `pred_upload_doc`
(case-document upload, the primary path a lawyer uses to get evidence into an active matter) was
chosen as the highest-value, most bounded target, establishing `_fetchWithTimeout()` as a reusable
pattern for whichever future mission (or the founder directly) extends it to the remaining paths.

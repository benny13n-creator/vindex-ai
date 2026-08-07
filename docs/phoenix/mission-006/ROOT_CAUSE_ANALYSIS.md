# Mission 006 — Root Cause Analysis

## Common root cause

`_klasifikuj_dokument` was designed around a single, reasonable-sounding principle — "never let
an AI hiccup block the evidence pipeline, always fall back to something usable" — but the
fallback and the genuine article share the exact same shape, so nothing downstream (a human
reviewing the evidence matrix, or code deciding whether to bill for the result) could tell them
apart. `-022` is the same gap in a different guise: the classification was never asked to
self-report its own uncertainty at all, so even a genuinely low-confidence-but-not-outright-
failed classification looked identical to a highly confident one.

## Why `reklasifikuj`'s fire-and-forget pattern existed

The original design (`asyncio.create_task`, charge immediately, return "started in background")
optimized for a fast HTTP response on an action a lawyer might not wait around for. That's a
reasonable UX goal in isolation, but it directly conflicts with correct billing — you cannot
charge for an outcome you haven't observed yet. The debt register's own framing already
identifies the tension and resolves it in favor of correctness: this is a manual, occasional
action (not a hot path), so the fast-response optimization was the wrong tradeoff for a
credit-charging endpoint specifically.

## Why the confidence signal was folded into `ai_tags` rather than a new column

`predmet_dokumenti.ai_tags` is an existing JSONB column already used for exactly this kind of
extensible, evolving-schema metadata (`stranke`, `datumi`, `iznosi`, etc.) — adding new keys to
it is the established, zero-migration extension point this table already provides, not a new
pattern invented for this mission.

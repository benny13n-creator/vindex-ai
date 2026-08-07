# Mission 009 — Root Cause Analysis

## Common root cause

Both items are the same failure mode one level removed from the "silent failure / false
success family" this whole program keeps finding: not a lie about the OUTCOME (the score, the
draft text), but a lie of omission about the PROCESS that produced it. The lawyer sees a
confident number or an unflagged draft and has no way to tell "this went through the full
verification pipeline" from "this didn't, and the platform quietly fell back."

## `-047` — argument grounding disclosure gap

`argument_reputation` was built to accept up to 10 arguments (a real, deliberate product
limit), but its RAG retrieval loop was written against `payload.argumenti[:5]` — very likely a
cost/latency guard added when the endpoint was extended from a smaller cap, without a
corresponding change to either (a) extend retrieval to the new limit or (b) mark the
un-retrieved arguments as such. The LLM prompt itself doesn't distinguish "I have real cases in
front of me for this argument" from "I'm reasoning from general legal knowledge" — it produces
the same confident `relevantne_odluke`/`uspesnost_procena` shape either way, so the gap was
invisible without an explicit disclosure field.

## `-015` — critique-pass disclosure gap

`_critique_and_refine_draft`'s own docstring already states its design intent: "Nikad ne baca:
svaka greška pada nazad na originalni nacrt umesto da blokira odgovor" (never raises; every
error falls back to the original draft rather than blocking the response). That's the correct
availability tradeoff — a lawyer should always get a draft, never a 500. But the function was
built to prioritize "always return something usable" and never separately addressed "and let
the caller know whether what it verified." The 2 degradation paths (total failure; partial
failure with no fix text) were both treated as equivalent to "the pass succeeded and found
nothing wrong" from the caller's point of view — they produce byte-identical output.

## Why these are safe, bounded fixes (not new algorithms)

- `-047` reuses the exact retrieval call already made — no 2nd RAG pass, no new query. The
  disclosure is a pure post-hoc tag on data already computed.
- `-015`'s tuple return is a type-signature change on a private (`_`-prefixed), single-call-site
  function — no new control flow, only an additional field threaded through the one path that
  already existed.
- Neither fix changes what the platform DOES (retrieval scope, critique retry behavior) — both
  are honest disclosure of an existing, real limitation, exactly the "make the gap visible"
  precedent this debt item explicitly named.

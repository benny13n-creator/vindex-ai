# Canonical Context Factory — Program Tau, Master Sprint 006, Phases 2-3

## Phase 2 — Pattern Verification

Compares the platform's 3 proven `build_case_context()` consumers — `case_intelligence.py` (Tau 002),
`court_predictor.py` (Tau 005), and `morning_briefing.py` (Tau 002, portfolio-wide variant) — to confirm
whether a universal migration pattern actually exists, or whether the mission's own "canonical context" was
just repeated coincidentally.

### The 6 dimensions found present, independently, in all 3

| Dimension | `case_intelligence.py` | `court_predictor.py` | `morning_briefing.py` |
|---|---|---|---|
| **Fail-soft fetch** | `asyncio.gather(..., build_case_context(...), return_exceptions=True)` — a failed fetch degrades, never raises | `_dohvati_case_context_ako_postoji()` — `try/except`, returns `None` on any exception or missing `predmet_id` | `asyncio.gather(*[build_case_context(...) for p in cases], return_exceptions=True)` — same shape, looped |
| **Local formatting function** | `_build_context_text(data)` — dict → prompt text | `_case_context_blok(cc)` — dict → prompt text | `_linija_predmeta(p)` — per-case one-line render (no block-level formatter needed, since output is a status digest, not a reasoning brief) |
| **Explicit mode selection** | Full (`include_documents` default `True`) — briefing needs document content | Full for 2 endpoints, lightweight for 5 — decided per-endpoint by reasoning-task shape | Lightweight (`include_documents=False`) always — portfolio loop over up to 10 cases, document text not needed for a status line |
| **GPT boundary mechanism** | `_ai_provenance` ownership map — every output field tagged `deterministic` or `gpt_advisory`, sourced explicitly | Deterministic readiness-based cap on `procenat_min`/`procenat_max`; `_calc_confidence_nivo`'s readiness-replaces-evidence-count rule | Canonical action ranking (Tau 003) — `top_open_action()` picks the displayed action, GPT never re-ranks |
| **Evidentiary chain** | `_ai_provenance.source` names the exact canonical field per output value | `koriscena_praksa` reports actually-retrieved precedent; case-context-derived cap is traceable to `readiness.value.status` | `readiness` badge appended per case line, sourced directly from `build_case_context()`'s own `readiness` field, no GPT paraphrase |
| **Tests proving the boundary holds under adversarial input** | (pre-existing from Tau 003, not re-verified this sprint — out of scope) | 21 tests incl. adversarial cap-override, concurrency, replay (Tau 005) | (pre-existing from Tau 002/003, not re-verified this sprint) |

### Conclusion: yes, a universal pattern exists — with one confirmed variant, not an exception

All 3 independently converged on the same 5-part shape (fetch → format → mode-select → bound GPT →
trace evidence) without being designed as a shared template in advance — 3 data points is enough to call
this a genuine pattern, not coincidence. The one real variation is **single-case vs. portfolio-wide**:
`morning_briefing.py` loops `build_case_context()` over many cases and needs a per-item line, not a
per-case text block — its "formatter" is naturally shaped differently (one line vs. a multi-section block).
This is a legitimate variant of the pattern (Dimension 2 still present, just shaped for its own consumer),
not a case where the pattern failed to apply.

## Phase 3 — Factory Definition: the Canonical Context Migration Pattern

Formalizes the 6 dimensions above into a definition any future migration should instantiate. This is a
**pattern to instantiate, not code to import** — per this program's own repeated "no shared context builder
beyond the one canonical fetch function itself" prohibition (confirmed again this sprint: forcing a shared
formatter/wrapper module across files with genuinely different request shapes — `judge_profile`'s missing
case-description field, `hearing_cc.py`'s notes/AI-history fields with no canonical equivalent — would either
be too generic to be useful or would silently misfit at least one endpoint, as already observed twice in
this program).

### 1. Input

The module's own `predmet_id` (or equivalent identifying field) — confirm via Phase 1-style forensic
re-verification (not assumed) that it is genuinely present on the request model and would genuinely resolve
to a real case for this module's own live callers. If it is Optional or the module has non-case-linked
callers too, that's not disqualifying — it changes step 2's behavior, not whether the pattern applies.

### 2. Fail-soft behavior

A file-local wrapper (or, if the module already does a fail-soft parallel gather like
`case_intelligence.py`/`morning_briefing.py`, an item within it) that calls `build_case_context()` exactly
once and never lets a context-fetch failure break the endpoint's own pre-existing behavior:
- Missing/falsy `predmet_id` → skip the fetch, return `None`/degrade silently, do not raise.
- `build_case_context()` returning `{"error": ...}` (e.g. `predmet_not_found`) → same degrade path.
- Any exception during the fetch → caught, logged, degrade path, never propagates to the caller.

This is a genuinely necessary, provably-justified helper (not a "new context builder") because every one of
the 3 proven consumers independently needed it — but it stays file-local, not shared, since its exact
integration shape (standalone wrapper vs. one item in an existing `asyncio.gather`) depends on how the
module already structures its own data fetching.

### 3. Formatter

A file-local function turning the canonical dict into whatever shape the module's own prompt needs — a
multi-section text block (`_case_context_blok`, `_build_context_text`) for a single-case reasoning task, or
a one-line render (`_linija_predmeta`) for a portfolio digest. Never a 2nd data source — every value it
prints must trace back to a `build_case_context()` field, nothing invented or independently queried.

### 4. Endpoint mode

An explicit, stated decision (not a default): full context (`include_documents=True`, real document
excerpts via the pre-existing Document Visibility Engine) vs. lightweight (`include_documents=False`,
readiness/Genome/gaps/deadlines/actions text only) vs. consistency-check-only (no injection, just a
cross-check field, for a request shape with no case-description field at all — `judge_profile`'s own
precedent) vs. not applicable (the module's own `predmet_id`, if present, doesn't map to a case-reasoning
task at all — e.g. a pure audit/write-path use).

**Decision rule**: full mode only if the module's own core reasoning task is directly about case strength/
evidence (mirrors Tau 005's own reasoning: `prediktuj_ishod`/`battle_report` needed real documents,
`judge_profile`/`confidence_check` didn't). Default to lightweight for everything else that has a genuine
case-description field. Consistency-check-only for anything shaped like `judge_profile`.

### 5. GPT boundary (grounding hook)

Prefer a deterministic mechanism over a pure prompt instruction wherever the canonical context contains a
value that should constrain, not just inform, GPT's output — proven twice now (Tau 003's provenance-
ownership map, Tau 005's readiness-based percentage cap). The exact mechanism is module-specific (a hard
cap, a consistency-check field, a replace-not-add scoring rule, a canonical ranking GPT may not override) —
there is no single reusable boundary function, because what "the canonical truth" constrains differs per
module's own output shape. This is itself a Factory finding, not a gap: **the boundary mechanism cannot be
templated as code, only as a design question to ask** ("does this module's output make a claim the
canonical context can already verify or bound? If yes, enforce it in code after the GPT call, don't just
ask nicely in the prompt.").

### 6. Evidentiary chain

Every canonical-context-derived claim in the module's own response should be traceable to which field
produced it — either via an explicit provenance map (`case_intelligence.py`'s `_ai_provenance`), an honest
"what was actually retrieved" field (`court_predictor.py`'s `koriscena_praksa`), or a direct pass-through
value with a named source (`morning_briefing.py`'s `readiness` badge). Never ask GPT to self-cite which
canonical fact it used — this program has twice now (Tau 004, Tau 005) deliberately avoided that design
since it introduces a new hallucination-validation problem instead of closing one.

### 7. Tests

At minimum, per migrated module: (a) a test proving the fetch degrades gracefully when `predmet_id` is
absent or the fetch fails (unchanged pre-migration behavior preserved); (b) a test proving the formatter
only surfaces canonical-context values, nothing invented; (c) if a deterministic boundary mechanism was
added, an adversarial test proving GPT cannot override it via prompt-level persuasion; (d) a concurrency
test if the module can plausibly be called for 2 different cases at once (proves no cross-contamination).

## What Phase 2/3 explicitly did NOT produce, and why

No shared Python helper module implementing steps 2/3 generically. Attempting one was considered and
rejected — the 3 proven consumers' own fail-soft wrappers and formatters are structurally similar but not
identical (single-item `try/except` vs. gather-participant, multi-section block vs. one-line render), and
forcing a shared abstraction across them would either need enough parameters to become as complex as just
writing the file-local version, or would quietly misfit the next module with its own genuinely different
shape (exactly what this program's own prior sprints have found happens whenever a "helper" tries to serve
requesters with different needs). The Factory's output is a **template to instantiate per file**, proven now
against a 4th case in Phase 4 (`hearing_cc.py`).

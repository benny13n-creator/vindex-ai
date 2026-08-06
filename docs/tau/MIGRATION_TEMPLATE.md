# Canonical Context Migration Template — Program Tau, Master Sprint 006

Operational checklist for migrating one GPT-calling module onto `shared/case_context.py::build_case_context()`.
Companion to `docs/tau/CANONICAL_CONTEXT_FACTORY.md` (the analysis behind this checklist — read that first
if a step here doesn't make sense). Proven against `hearing_cc.py` in this sprint's own Phase 4
(`docs/tau/HEARING_CC_MIGRATION_REPORT.md`).

## Step 0 — Forensic re-verification (don't skip, don't assume)

Before touching any code:
- [ ] Read the module's own request model(s). Does a case-identifying field (`predmet_id` or equivalent)
      actually exist? Is it required or Optional?
- [ ] Read the module's own live frontend caller(s) (`static/vindex.js` or equivalent) directly. Does the
      real payload actually send the case-identifying field? (Tau 005 found the live Court Predictor UI
      often doesn't — don't assume the request model's own shape reflects real traffic.)
- [ ] Read the module's own current context-fetching code. List every table it queries, keyed by what.
- [ ] For each field the module currently fetches, check: does `build_case_context()`'s own 13-field
      contract already carry an equivalent? List what's covered, and — just as importantly — **list what
      the module currently uses that has NO canonical equivalent** (this sprint's own `hearing_cc.py` pilot
      found `predmet_beleske`/`predmet_istorija` have no canonical field at all — a real finding, not a
      blocker, see Step 5).
- [ ] **Check for duplicate COMPUTATION, not just duplicate fetch.** Added after Phase 7's own simulation
      pass found `case_commander.py` and `zadaci.py::ai_analiziraj_predmet` don't just independently query
      the same tables `build_case_context()` queries — they independently call the exact SAME deterministic
      functions (`services/risk_engine.py::calculate_procesni_rizik`/`identify_case_problems`,
      `shared/gap_engine.py::collect_case_gaps`, `shared/case_readiness.py::compute_case_readiness`) that
      `build_case_context()` already calls internally, to re-derive `readiness`/`missing_evidence`/
      `contradictions` from scratch via a 2nd independently-fetched data set. This is a stronger migration
      opportunity than a plain "add missing fields" swap: it can ELIMINATE a real duplicate-computation risk
      (2 independent fetches of the same underlying rows could theoretically drift if one's own query
      changes and the other doesn't — a live footgun, not just redundant work) by re-mapping the module's
      own output shape onto `build_case_context()`'s already-computed `readiness`/`missing_evidence`/
      `contradictions` fields directly, rather than recomputing them. If Step 0 finds this shape, the
      migration should replace the computation, not just supplement it.
- [ ] Check whether the module's own reasoning task is genuinely single-case, or has a mixed/portfolio-wide
      shape that needs different treatment (`opponent_intel`'s cross-portfolio search, `confidence_check`'s
      firm-wide aggregation — both Tau 005 precedents for "keep this bespoke query, add canonical context
      alongside it, don't force a replacement").

## Step 1 — Fail-soft fetch

Add a file-local wrapper (or an item in an existing fail-soft `asyncio.gather`) calling `build_case_context()`
exactly once:
```python
async def _dohvati_case_context_ako_postoji(predmet_id, uid, supa, include_documents=False):
    if not predmet_id:
        return None
    try:
        return await build_case_context(predmet_id, uid, supa, include_documents=include_documents)
    except Exception as exc:
        logger.warning("[<MODULE>] build_case_context greška (nastavlja bez kanonskog konteksta): %s", exc)
        return None
```
- [ ] Never raises. Never blocks the endpoint's own pre-existing behavior when context is unavailable.

## Step 2 — Formatter

Write a file-local function turning the canonical dict into the module's own prompt shape (multi-section
block for a single-case reasoning task, one-line render for a portfolio digest, or nothing at all if the
canonical context only feeds a cross-check field rather than prompt text).
- [ ] Every line traces to a real `build_case_context()` field — nothing invented, nothing independently
      queried inside this function.
- [ ] Returns an empty/falsy value cleanly when context is `None` or carries an `"error"` key.

## Step 3 — Mode decision (write this down, don't default)

- [ ] State explicitly: full (`include_documents=True`) / lightweight (`False`) / consistency-check-only /
      not applicable. Justify against the module's own actual reasoning task, not by copying the last
      migration's choice.

## Step 4 — GPT boundary

- [ ] Ask: does this module's output make a claim the canonical context can already verify or bound
      (a percentage, a status, a court name, a date)? If yes: enforce it in code AFTER the GPT call
      (a cap, a consistency-check field, a replace-not-add scoring rule), not just via a prompt instruction.
      If no genuine bound exists, say so — not every module needs one.

## Step 5 — Name what doesn't fit (this is a finding, not a failure)

- [ ] If the module's own bespoke fetch surfaces something with no canonical equivalent (Step 0's own list),
      decide explicitly: (a) drop it if genuinely low-value, stated why; (b) keep the bespoke fetch for that
      ONE piece alongside the new canonical call (same precedent as `opponent_intel`); (c) flag it as a
      candidate for expanding `build_case_context()`'s own contract (`TAU-013`-style, a separate future
      task, not this migration's problem to solve). Do NOT silently drop functionality without stating which
      of these three you chose.

## Step 6 — Tests

- [ ] Fetch degrades gracefully (no `predmet_id`, or `build_case_context()` raises/returns an error).
- [ ] Formatter only surfaces canonical values.
- [ ] If a Step 4 boundary was added: adversarial test proving GPT can't override it.
- [ ] Concurrency test if 2 different cases can plausibly be in flight at once.
- [ ] Every pre-existing test for the module still passes, or was updated for a stated, intentional
      behavior change (not silently loosened).

## Step 7 — Migration completeness proof

- [ ] Full `supa.table()` (or equivalent) call-site inventory for the migrated module, classifying every
      remaining non-canonical query as either write-only/audit, a deliberately-kept different-shaped signal
      (state why), or a genuine leftover bypass (fix it).

## Step 8 — Full regression + commit

- [ ] Run the full test suite, not just the migrated module's own tests.
- [ ] Commit with the specific finding/fix, not a generic "migrate X" message.

## Forbidden, every step

No new shared context builder. No new GPT wrapper. No new predictor/decision logic. No hardcoding. No
duplicated logic between the new canonical path and a leftover bespoke one for the same data. No half-done
migration (a module either fully follows this template or is explicitly named as a Step-5 partial with a
stated reason — never silently abandoned mid-way).

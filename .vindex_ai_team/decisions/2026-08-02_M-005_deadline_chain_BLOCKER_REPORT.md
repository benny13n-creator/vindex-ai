# Blocker Report — M-005: Deadline Chain Integration

**Mission Board entry:** `MISSION_BOARD.md`, M-005, priority 5.
**Executed by:** Autonomous Night Shift (founder's Master Prompt v1.0), 2026-08-02.
**Status:** BLOCKED. Reverted to `NEEDS_SCOPING` — not implemented, per the Master Prompt's own Stop
Condition: *"architecture conflict exists → never guess."*

---

## Problem
M-005 as scoped: *"Wire `routers/rokovi_lanac.py`'s existing deadline-chain calculator to fire
automatically when `shared/intake_extract.py` extracts a deadline entity."* Investigating this
before implementing (Phase 1-2 of the mission loop) found a real ambiguity that makes automatic
firing unsafe without a design decision this mission cannot make on its own.

## Evidence
- `routers/rokovi_lanac.py`'s chain catalog (`_TIPOVI`, `:30-271`) is keyed by **14** specific
  triggering-event types, each tied to a **specific procedural law**: no prefix = ZPP (civil
  procedure) — e.g. `dostava_presude_prvostepene`; `zkp_` = criminal procedure; `zr_` = labor
  termination; `zup_` = administrative procedure; `zio_` = enforcement procedure.
- `shared/intake_extract.py`'s deadline extraction only produces a coarse **category**
  (`uploaded_doc/deadline_parser.py::_kategorija`, `:55-61`): `zastarelost`, `otkaz`, `zalba`,
  `podnesak`, `isplata`, `ostalo` — six values, with no signal for *which procedural law* applies.
- `shared/intake_classify.py`'s document-type classifier (`DOCUMENT_TYPES`, `:32-36`) is similarly
  coarse on this specific axis: `judgment`, `court_decision`, `appeal`, `enforcement`, etc. — it
  distinguishes document *shape* (a judgment vs. a decision vs. an appeal), not which *procedure*
  (civil/criminal/labor/administrative/enforcement) produced it.
- **Consequence, concretely**: a document classified `judgment` with an extracted `zalba` (appeal)
  category could correctly map to `dostava_presude_prvostepene` (civil, 15-day ZPP appeal window),
  `zkp_dostava_presude` (criminal, a different ZKP window), or one of the `zup_` administrative
  variants — and today's extraction pipeline has no reliable signal to choose between them.

## Why this blocks automatic firing specifically
A silently wrong chain — the wrong law cited, the wrong day-count computed — is a **worse** outcome
than no automation at all. This project's own established pattern everywhere else uncertain AI
output touches a legal consequence (entity extraction's confidence-gated review queue, intake
description-to-case-type proposals, document classification's low-confidence review routing) is
**propose, never silently apply**, specifically because a wrong deadline computation is the single
highest-consequence failure mode this whole product exists to prevent. Auto-firing a chain from a
category this coarse would violate that established pattern, not extend it.

## Options
1. **Do nothing tonight; leave as `NEEDS_SCOPING`.** (Recommended for tonight — see below.)
2. **Add a `predmet.tip` × `document_type` mapping table.** The case's own `tip` field (set at
   creation — `radni`, `krivicno`, `upravno`, `izvrsenje`, `opsti`/`gradjansko`, per
   `routers/intake.py`'s template catalog) is a real, already-available signal for *which procedure
   applies*, that `intake_extract.py`'s deadline category alone doesn't carry. Combined with
   `document_type`, this could plausibly disambiguate most of the 14 `_TIPOVI` keys safely. **Not
   attempted tonight** — this is new design (a mapping table that doesn't exist yet, with its own
   correctness risk if built carelessly), larger than this mission's "Small" complexity estimate,
   and exactly the kind of design decision this project's own discipline says should go through an
   Architecture Review with adversarial checking before being built, not be improvised solo at night.
3. **Propose-not-apply**: compute the candidate chain and attach it to the document's review queue
   entry (matching the existing entity-correction UX) for lawyer confirmation, rather than writing
   `predmet_hronologija` rows directly. This sidesteps the wrong-citation risk entirely (nothing is
   committed without a human), but is a UI-facing contract change (the job-status response shape,
   a new confirm action) — real, valuable, and out of a Small-complexity night-shift mission's safe
   scope without founder sign-off on the UX shape.

## Recommendation
Re-scope M-005 to `NEEDS_SCOPING` (matching M-004/M-007/M-008/M-011's existing treatment on the
board) with this report as its grounding evidence. A future scoping pass should decide between
option 2 (silent auto-apply, only if the `tip`×`document_type` mapping can be shown to disambiguate
reliably — needs real validation, not assumption) and option 3 (propose-then-confirm, the pattern
this codebase already uses everywhere else for exactly this risk class) **before** any code is
written — this is a founder-level product/risk decision (how much automation risk is acceptable for
a wrong-law failure mode), not an engineering-only one.

## Risk of proceeding without this decision
Shipping either option blind risks producing a subtly wrong legal deadline that looks
AI-confirmed and correct to a lawyer who has learned to trust the system's other outputs — the
single most damaging kind of error this specific product can make. This report exists specifically
so that risk is never taken silently.

---

## Mission Board disposition
`M-005` status changed from `TODO` to `NEEDS_SCOPING`. No code changed by this mission.

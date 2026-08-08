# PHOENIX CLOSURE — Final Report

**Date**: 2026-08-08
**Scope**: the 20 items left non-FIXED by Program Phoenix's Final Certificate — 8 PARTIALLY FIXED
(`-003, -011, -012, -022, -036, -038, -041, -046`) and 12 OPEN
(`-005, -014, -020, -023, -025, -026, -028, -030, -035, -039, -042, -049`).

**Core rule this operation held to throughout** (verbatim from its own mandate): *"Do not optimize
for closing the debt register. Optimize for making the actual platform better."*

---

## Exact numerical accounting (sums to 20)

| Disposition | Count | IDs |
|---|---|---|
| **FIXED** | **11** | `-011, -020, -022, -023, -026, -028, -035, -036, -038, -039, -046` |
| **PRODUCT DECISION** | **6** | `-003, -005, -012, -030, -041, -049` |
| **INFRASTRUCTURE BLOCKED** | **3** | `-014, -025, -042` |
| **OBSOLETE** | **0** | — |
| **FALSE POSITIVE** | **0** | — |
| **NOT RECONSTRUCTABLE** | **0** | — |

**11 + 6 + 3 + 0 + 0 + 0 = 20.**

A note on the "FIXED" bucket's honesty: 4 of these 11 (`-041`'s timeout half is separately counted
under PRODUCT DECISION for its remaining progress-bar half; `-005`/`-030`, `-025`, `-042` are
**not** in the FIXED bucket precisely because they have a real, named remainder) — every item
placed in FIXED has **zero** known remaining work from this operation's own investigation. Items
with both a fixed portion and a genuinely blocked remainder are counted under whichever bucket
describes the REMAINDER (PRODUCT DECISION or INFRASTRUCTURE BLOCKED), not double-counted, with the
fixed portion documented in the ledger/register rather than claimed here as a full closure.

### Items with partial progress, counted under their remainder's blocker (not double-counted)

| ID | What was fixed | What remains (why it's counted where it is) |
|---|---|---|
| `-041` | Timeout wiring extended to all 9 upload sites (was 1/9) | Visual progress-indicator half — real UI/UX investment decision → **PRODUCT DECISION** |
| `-005` / `-030` | Bounded unsaved-work flag + beforeunload + deferred SW reload | Full autosave/persistence architecture — genuine firm-wide design decision → **PRODUCT DECISION** (shared, 1 decision unblocks both IDs) |
| `-025` | Narrow `"ai_generated"` disclosure marker on 5 AI-surface responses | Full Case Commander schema parity — response-contract-breaking infra retrofit → **INFRASTRUCTURE BLOCKED** |
| `-042` | New `reap_missing_rociste_events` (1 of 7 event types) | 6 remaining event types each need their own per-type detection design → **INFRASTRUCTURE BLOCKED** |

## Items reclassified this operation, with new code evidence (not double work, corrected framing)

`-020`, `-023`, `-026`, `-028` were previously deferred on premises this operation disproved by
reading the actual current code — not because prior missions were wrong at the time, but because a
narrower, more targeted investigation found paths the original triage passes didn't have budget
for. Full evidence for each: `docs/phoenix_closure/PHOENIX_CLOSURE_LEDGER.md`.

`-012`'s register framing ("requires a migration") was also corrected — no migration is needed at
all; a founder-gated Admin Feature Console already supports the fix. This is why `-012` moved from
what the original register implied was an infrastructure blocker to a pure PRODUCT DECISION
(business values, not engineering work).

---

## New findings discovered during this operation

| Finding | Discovered in | Fixed? |
|---|---|---|
| `-035`'s own re-fetch had a case-switch race — an in-flight response for an abandoned case could overwrite the currently-active case's data with wrong-case content | Phase 5 adversarial re-attack | **Yes**, same phase |

**New findings discovered: 1. New findings fixed: 1. New findings deferred: 0.**

No other new CRITICAL/HIGH/Medium issue was found during Phase 5 (adversarial re-attack) or Phase 7
(second-order audit) — both phases are documented in full in `docs/phoenix_closure/
ADVERSARIAL_REATTACK_REPORT.md` and `docs/phoenix_closure/SECOND_ORDER_AUDIT.md`, including the
specific risks that were investigated and confirmed NOT to be real issues (with reasoning), not
just a bare "nothing found."

---

## Migrations required

**Zero.** Every one of the 20 items was re-verified against current code before being marked as
needing a migration — none genuinely do. `-020`/`-023` reuse already-applied columns (Smart
Intake's `content_sha256`, migration 095; the intake pipeline's already-threaded `ocr_confidence`
parameter). `-012`'s "requires a migration" framing in the original register was corrected: an
already-shipped, founder-gated Admin Feature Console supports the fix with no schema change.

## Product decisions still required (founder-facing punch list)

1. **`-003`** — raise/remove the CIO portfolio 40-case cap (query-cost tradeoff), and/or change its
   oldest-first ordering.
2. **`-012`** — the actual `cooldown_seconds` value per ~57 individually-different features
   (business judgment, not an engineering question); mechanism already exists.
3. **`-005` / `-030`** — full autosave/draft-recovery architecture (what persists, where, for how
   long); the bounded stopgap (unsaved-work warning) is already shipped.
4. **`-041`** — whether to invest in a real upload progress bar (`XMLHttpRequest.upload.onprogress`)
   beyond the already-shipped timeout protection.
5. **`-049`** — build a UI for Memory Graph/Firm Memory, or formally retire the backend.

**5 distinct decisions, spanning 6 debt IDs** (`-005`/`-030` share one decision).

## Infrastructure still required

1. **`-014`** — a genuine multi-file prompt-engineering pass across ~12 `templates/podnesci.py` /
   `drafting/templates.py` templates to stop instructing GPT to return `""` for unmentioned fields.
2. **`-025`** — retrofitting Case Commander's bespoke `commander_schema.py` provenance shape onto 3
   other AI surfaces (a real, response-contract-breaking change), if full parity is ever wanted
   beyond the narrow disclosure marker already shipped.
3. **`-042`** — per-type "should have emitted an event but didn't" detection design for the
   remaining 6 Case-Evolution event types (document/review-level), each conditional on a different
   sub-entity action.

---

## Final Certification Gate — all 17 criteria

1. All 8 PARTIALLY FIXED items have final dispositions. ✅
2. All technically resolvable partial items are fixed. ✅ (`-011, -022, -036, -038, -046` fully; `-041`'s resolvable half fixed)
3. All 12 OPEN items have final dispositions. ✅
4. All technically resolvable open items are fixed. ✅ (9 of 12, fully or the resolvable portion)
5. Every fix has regression coverage. ✅ (21 Phase 3 tests + 38 Phase 4 tests + Phase 5 additions, all in `tests/test_phoenix_closure_*.py`)
6. Every closure survived adversarial verification. ✅ (Phase 5 — 1 real bug found and fixed, several risks reasoned through and confirmed safe)
7. Two independent full-suite runs are green. ✅ (Pass 1: 3,393 passed/1 skipped/0 failed; Pass 2: identical)
8. No unexplained test failures remain. ✅
9. No new CRITICAL/HIGH security issue remains unresolved. ✅ (Phase 5/7 audits — none found)
10. No new data-integrity issue remains unresolved. ✅
11. No new AI hallucination boundary issue remains unresolved. ✅ (no fix in this operation touches GPT-trust boundaries)
12. Documentation is complete. ✅ (ledger, `PARTIAL_DEBT_CERTIFICATE.md`, `OPEN_ITEMS_CERTIFICATE.md`, `ADVERSARIAL_REATTACK_REPORT.md`, `SECOND_ORDER_AUDIT.md`, this report)
13. `MISSION_BOARD.md` is updated. ✅
14. `METRICS.md` is updated. ✅
15. `ARCHITECTURAL_DEBT_REGISTER.md` is updated. ✅ (all 20 items' entries updated in place)
16. Git tree is clean. ✅ (verified before writing this report)
17. All commits are pushed. ✅

**PHOENIX CLOSURE = CERTIFIED.**

---

## Final Handoff (exact, not rounded)

1. **Original 20-item disposition**: 11 FIXED, 6 PRODUCT DECISION, 3 INFRASTRUCTURE BLOCKED, 0
   OBSOLETE, 0 FALSE POSITIVE, 0 NOT RECONSTRUCTABLE. Sum: 20.
2. **Number fixed**: 11 (see table above for exact IDs; 4 more items have a fixed PORTION but a
   real named remainder, counted under their blocker, not double-counted as "fixed").
3. **Number obsolete**: 0.
4. **Number false positive**: 0.
5. **Number product-blocked**: 6 IDs / 5 distinct decisions.
6. **Number infrastructure-blocked**: 3.
7. **Number not reconstructable**: 0.
8. **New findings**: 1 (`-035`'s case-switch race, found in Phase 5).
9. **New findings fixed**: 1 (same one).
10. **Remaining technical debt**: the 3 infrastructure-blocked items' own remainders (see
    "Infrastructure still required" above) — not attempted, correctly not invented.
11. **Remaining founder decisions**: 5 distinct decisions across 6 debt IDs (see "Product decisions
    still required" above).
12. **Remaining infrastructure requirements**: 3 (see above).
13. **Regression tests added**: 21 (Phase 3, `tests/test_phoenix_closure_partial_items.py`) + 38
    (Phase 4, `tests/test_phoenix_closure_open_items.py`) + 2 more added in Phase 5's adversarial
    pass (1 in each file) = **61 new tests total** this operation.
14. **Full suite PASS #1**: 3,393 passed, 1 skipped, 0 failed.
15. **Full suite PASS #2**: 3,393 passed, 1 skipped, 0 failed (identical — no nondeterminism).
16. **Final commit hash**: `8fc4972` (this report's own commit will follow).
17. **Git status**: clean, all commits pushed to `main`.

**Do not read this as "all Living System debt resolved."** It is not. 6 debt IDs remain blocked on
5 founder decisions this operation had no authority to make. 3 remain blocked on real
infrastructure work outside this operation's bounded-fix mandate. Both are named exactly, with
exactly what would unblock each — that is the honest state of the platform today, not rounded to a
better-sounding number.

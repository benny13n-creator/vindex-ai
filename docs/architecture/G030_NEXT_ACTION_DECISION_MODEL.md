# G-030 — Next Action Decision Model (ADR)

**Date:** 2026-07-22
**Type:** Decision framework only. **No code changed.** This document exists to make the founder's decision easier, not to make it. Every option below is stated with its tradeoff, not with a recommendation ranked above the others — same discipline as G-027/G-034: the empirical step comes before the architectural one, not after.

**Status: Discovery complete. Finding: three competing next-action authorities exist (Cockpit, Matter Intel, Case Ready Score — see `G030_NEXT_ACTION_OWNERSHIP_ANALYSIS.md` for the full mapping). Risk: high UX confusion + trust issue. Implementation: Blocked pending product decision. Next: this document.**

---

## What this decision actually is

Not a bug fix. Not a UI cleanup. This is the decision that determines whether Vindex is *"a dashboard with several AI opinions on it"* or *"an operating system with one command center."* Worth stating plainly because it's easy to let this quietly resolve itself as a UI sprint item (as the original Sprint 3 classification nearly did) when it's actually a product-identity decision.

## The principle already proven once in this codebase

`services/risk_engine.py` (G-027) already answered a smaller version of this exact question for "risk level" specifically: **a deterministic layer decides the fact, GPT explains the fact — GPT never decides the fact.** Formalized as **AR-01**: *"LLM nikada ne određuje poslovno stanje sistema (rizik/status/rok/kompletiranost/prioritet). LLM sme da objasni/sumira/predloži/upozori, ali određuje deterministički sloj."*

"Next action" is a business-state decision by AR-01's own definition (it implies a priority, a due-date framing, an urgency). Today, only one of the three competing systems (Matter Intel) follows this rule. Cockpit's `prioritet` field is fully GPT-decided (already logged separately as **G-029**, not yet actioned) — this is the same violation AR-01 was written to prevent, just not yet corrected for this specific field.

## Candidate canonical sources — stated, not ranked

### A) Matter Intel becomes canonical
- **For:** Already deterministic, already reuses `risk_engine.py`'s signals, zero AR-01 exposure, already exists and is tested.
- **Against:** Its phrasing is templated/generic ("Pribaviti X koji nedostaje u spisu") — six fixed if/elif branches, not tailored to the specific case narrative the way Cockpit's GPT output is. Currently invisible in the UI (would need to be surfaced, not just "picked").

### B) Cockpit becomes canonical
- **For:** Already the most prominent, most-seen, most case-specific in phrasing (reads dokumenti/beleske/hronologija, not just counts).
- **Against:** Fully GPT-decided today, including `prioritet` — adopting it as canonical without first fixing G-029 would be formalizing the exact thing AR-01 exists to prevent, not resolving it.

### C) Case Ready Score's copilot_preporuka becomes canonical
- **For:** Ties the recommendation to the fullest picture of "is this case ready" (checklist across docs/clients/deadlines/history/hearings).
- **Against:** Manually-triggered, not always present, and uses its own separate GPT risk assessment disconnected from `risk_engine.py` (the G-034-shaped gap, different pairing). Weakest exposure of the three today.

### D) A new orchestration layer ("Next Action Engine") reusing existing signals
- **For:** Matches the AR-01/G-027 shape exactly — deterministic decision, GPT explanation — using signals that **already exist and are already computed** (`risk_engine.py`'s output, deadline data, missing-document data). Would not require a new AI agent or new data source, only a new deterministic decision function plus a thin GPT phrasing pass, same shape as `_compute_next_action` already is.
- **Against:** Is, by definition, new code — the one option that isn't just "pick an existing winner." Requires explicitly defining the decision rules (which signal wins when risk is high AND a deadline is close AND documents are missing, simultaneously) — a real design task, not a trivial one.

**Not offering a ranked recommendation here on purpose.** Option D looks structurally closest to the proven pattern, but "looks closest to a good pattern" is exactly the kind of judgment G-027's own history warns against trusting without measurement — Cockpit's `prioritet` field probably also looked fine until the pattern was named.

## Illustrative shape, if D is chosen (not a proposal to build it now)

```
risk_engine.py::calculate_procesni_rizik   ──┐
Deadline data (rokovi_kriticni / rocista)  ──┤──▶  Next Action Engine   ──▶  GPT phrasing
Missing-document data (nedostajuci_dokazi) ──┘        (deterministic          ("zašto")
                                                        decision: WHAT
                                                        + priority)
```

What the lawyer would see on "Pregled predmeta" — **one block, not three**:

```
SLEDEĆI POTEZ

Pribaviti odgovor veštaka

Zašto:
 - kritičan dokaz nedostaje
 - rok 14 dana
 - predmet trenutno visokog rizika

Izvor: Risk + Dokumenti + Rokovi
```

The "Izvor" (source) line is deliberate, not decorative — it's the same trust-building instinct as the Genome Verification Layer's "AI je proverio sopstvenu procenu" narrative: showing which deterministic facts produced the recommendation is itself the thing that makes a skeptical lawyer trust it, independent of which candidate ends up canonical.

## What would need to happen before this is buildable (regardless of which candidate is chosen)

1. **G-029 first, if B is ever in the running** — Cockpit's `prioritet` can't become canonical while it's still GPT-only; that's a prerequisite, not a parallel task.
2. **Empirical comparison, same method as G-027/G-034** — before picking, measure whether Matter Intel's and Cockpit's recommendations actually *disagree* on a real sample of cases, or usually converge. If they mostly agree, the "confusion" risk is more about *visual* redundancy (closer to the Top10 #3 fix already shipped) than about *conflicting advice* — a materially smaller problem than currently assumed, worth knowing before committing to a bigger rebuild.
3. **A decision on tone/specificity** — if Matter Intel's determinism is kept as the decision layer, its output phrasing needs the same case-specific texture Cockpit currently has, or lawyers will perceive the "upgrade" as a downgrade in usefulness even though it's more trustworthy.

## Explicitly not proposed

Per the founder's standing exclusions for this item: no new AI agent, no "merge everything into one GPT call," no deleting Cockpit outright. All four candidates above reuse infrastructure that already exists.

---

**This document does not close G-030.** It exists so the founder's next message can be a decision ("go with D, run the empirical comparison first" / "not now" / something else) rather than a re-derivation of the same options.

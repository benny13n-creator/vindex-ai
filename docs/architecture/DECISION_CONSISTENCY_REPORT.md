# Decision Consistency Report — Program Gamma (Masterprompt 003), Phase 7

**The mission's own test**: for the same predmet, do all modules see the
same decision, the same explanation, the same Evidence Chain, the same
correlation ID, the same audit trail? **"Ako odgovor nije DA, misija nije
završena."**

**Honest answer: NO, not yet, for most of the decisions this mission
found fragmented.** Per this session's own established discipline (Program
Alpha's SMTP abandonment, Program Beta's PROGBETA-001 deferral), the
response to "not yet" is not to force an unsafe rushed fix — it is to (a)
close every instance that IS safely closable this session, (b) design the
rest fully, and (c) state plainly what remains open and why. This report
does that for all findings across the 5 Program Gamma domain investigations.

## Consistency checks performed, findings

### 1. Same decision?

| Decision | Same across all producers? | Evidence |
|---|---|---|
| Procesni rizik / health score | **YES** | `DECISION_CONSUMER_MAP.md` — 6+ consumers, 0 divergence, verified as a live regression check this mission (all 3 previously-fixed instances still delegate correctly) |
| "What's missing" (documents) | **NO** | DC-002 (canonical) vs. Genome's `nedostaje` vs. Strategy V2's `nedostajuci_dokazi` vs. Copilot PLAN's `nedostaje` — 4 independent answers, field-name collision between 2 of them |
| Contradiction between evidence | **PARTIALLY, improving** | 4 producers (Genome, Compare, Evidence Graph, Case Commander); 2 already evidence-checked (Genome, Compare, pre-existing); 2 more evidence-checked THIS mission (Evidence Graph, Case Commander) — but the 4 still don't cross-reference EACH OTHER's findings, only validate their own references don't point at invented entities |
| Strategic recommendation / next action | **NO — worst case in the platform** | 18 independent producers, 0 cross-checks, confirmed by every one of the 5 domain forks independently |
| Litigation win-probability | **NO** | 5 generators (`PROGBETA-001`'s 4 + Case Pipeline step 5), unchanged this mission — correctly deferred, not attempted |
| Document readiness | **NO** | `quality_gate` (numeric, calibrated) vs. Pravni Revizor (categorical, ungrounded) — structurally incompatible representations of the same question |
| Court Predictor confidence | **YES** | DC-004, canonical, Program Alpha fix, unchanged and re-verified this mission |
| Court Predictor argument color / profile confidence | **YES, as of this mission** | DC-012 — was raw/inconsistent, now derived from the same number the caller already has |

### 2. Same explanation?

Where the decision itself is fragmented, the explanation is necessarily
also fragmented — there is no single narrative to compare. Where the
decision IS canonical (DC-001/002/004/013), the explanation is consistent
by construction (one formula, one set of named factors, read by every
consumer).

### 3. Same Evidence Chain?

| Producer | Evidence Chain status |
|---|---|
| `compare_docs`, `evidence_graph.py`, `case_commander.py`'s `_cross_case_analiza` | **YES, as of this mission** — all 3 now run through the same `validate_dok_reference`/`validate_graph_edge_references`/`validate_predmet_reference` family (DC-009), same `{odluka, hard_flags, soft_flags}` shape |
| `case_commander.py`'s other 3 endpoints, `matter_intel.py`'s 2 endpoints | **NO** — zero Evidence Chain, not migrated this session (`DECISION_CONSUMER_MAP.md`, `GAMMA-003`/`GAMMA-004`) |
| Strategy Engine's 9 endpoints (citations) | **NO** — `PROGBETA-003`, unchanged |

### 4. Same correlation ID / audit trail?

| Producer | Provenance status |
|---|---|
| `evidence_graph.py::generisi_graf`, `case_commander.py::_cross_case_analiza` | **Fixed this mission** — `case_context()` wrapping added |
| `case_intelligence.py::case_intelligence_briefing` | Not wrapped this mission (the fix here was the live-bug repair, not provenance) — `GAMMA-005` |
| `ask_agent` recommendations via Copilot | Case-specific in fact, but `case_context()` passes `predmet_id=None` — a real, previously-undocumented gap (Program Gamma's Copilot fork, Finding 3) — `GAMMA-006` |

## What this mission actually closed (the "DA" cases, newly true)

1. Evidence Graph's contradiction/relationship edges are now evidence-checked and audit-wrapped, same mechanism as Compare Docs.
2. Case Commander's cross-case findings are now evidence-checked (predmet-reference existence) and audit-wrapped for its single most-used endpoint (`_cross_case_analiza`, feeding the daily morning briefing).
3. Court Predictor's `boja`/`pouzdanost_profila` are now guaranteed consistent with their own underlying numbers — previously could silently contradict.
4. Strategy Engine Synthesis's categorical conflict detection now has a code-guaranteed floor (2 structurally-checkable conflict types), closing the exact "sibling field left unfixed" gap Program Beta's own Faza 10 governance review would have flagged had it read this file.
5. `case_intelligence.py`'s "next step" endpoint went from **almost certainly 500ing on every call** to actually functioning — the most severe single fix this mission made, because a broken decision endpoint is worse for decision integrity than a duplicated one (a duplicate at least returns AN answer).

## What remains open (the "NE" cases, honestly reported, tracked)

See `ARCHITECTURAL_DEBT_REGISTER.md`'s Program Gamma section for full detail
on each `GAMMA-00X` item. Summary, by severity:

- **Critical, unresolved, needs a founder product decision**: "next
  recommended action" ownership (18 producers, full enumeration in ARCHITECTURAL_DEBT_REGISTER.md GAMMA-001) — this is not a Program
  Gamma decision to make; it widens G-030's already-open, founder-blocked
  question. `GAMMA-001`.
- **Critical, unresolved, needs new signal-wiring before a fix is even
  designable**: litigation win-probability (5 generators, `PROGBETA-001`
  + Case Pipeline step 5).
- **High, unresolved, needs a design decision (which representation wins,
  or a mapping layer)**: document readiness (`quality_gate` vs. Pravni
  Revizor), "what's missing" vocabulary collision (Genome vs. Copilot PLAN).
- **High, unresolved, needs its own bounded implementation pass**: Case
  Commander's remaining 3 endpoints, Matter Intel's 2 endpoints (both
  Evidence-Chain gaps of the exact kind DC-009 already proves is cheap to
  close — just not yet done for these 5 endpoints).
- **Medium, unresolved, needs a reliability fix not a decision-ownership
  fix**: document classification race (`ALPHA-003`), unchanged.
- **Medium, unresolved, needs a product decision on capability expansion**:
  Firm memory judge-favorability orphaning (`ALPHA-005`), unchanged.

## Conclusion, stated in the mission's own terms

Per Phase 10's own success criteria, this mission is honest about not being
"finished" in the sense of eliminating all decision fragmentation — that
was never achievable in one session given the scale found (18 producers
for the single largest decision type). What this mission delivers instead,
matching the discipline every prior mission this session has used
successfully: every fragmentation instance is now **detected and
documented in a registry that didn't exist before**, the reusable fix
pattern (DC-009's reference-existence family) is now proven a 3rd and 4th
time and cheaply portable, 2 live consumers were actually migrated onto it,
1 live production bug was fixed, 2 small "should have been impossible"
gaps were closed (DC-011, DC-012), and every remaining gap has a named
severity, a named blocker (design decision vs. implementation effort vs.
reliability fix), and a `GAMMA-00X` tracking entry — not a silent debt.

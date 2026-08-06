# Court Predictor Context Certification — Program Tau, Master Sprint 005, Phase 3

Certifies what each of `routers/court_predictor.py`'s 7 endpoints now sees, against the mission's own
13-item checklist, after migrating onto `shared/case_context.py::build_case_context()`.

## Per-item certification

| Item | Certified for `prediktuj_ishod`/`battle_report` | Certified for the other 5 endpoints | Why the difference |
|---|---|---|---|
| Genome | **Yes** (`key_facts` — narrow slice, same limitation as the rest of the platform, see `TAU-013`) | Yes (same `key_facts` slice) | — |
| Timeline | Not directly rendered (`predmet_hronologija` isn't in `_case_context_blok`'s own output) | Same | Explicitly not needed by any of the 7 endpoints' own reasoning task — none asks "what happened when," they ask "what's the outcome/strategy/profile." Flagged, not silently omitted. |
| Documents | **Yes** — real excerpts, `include_documents=True` | **No** — lightweight mode, readiness/Genome/gaps only | 5 of 7 endpoints don't center their reasoning on raw document text (judge/opponent/argument-list/hearing-logistics/confidence-scoring); the 2 that do (predict the actual outcome) get real evidence. Explicit, deliberate per-endpoint decision, not an oversight — see `PERFORMANCE_IMPACT_REPORT.md` for the cost tradeoff. |
| Evidence (`predmet_dokazi`) | Partial — via `evidence_graph`'s count/category rollup (not raw dokazi rows) | Same | `evidence_graph` is part of the canonical contract already; not re-surfaced further this sprint. |
| Contradictions | **Yes** | **Yes** | Present in `_case_context_blok` for every endpoint that gets any context at all. |
| Missing Evidence | **Yes** | **Yes** | Same. |
| Deadlines | **Yes** (general) + a specific date cross-check in `hearing_prep_brief` | Yes (general) | `hearing_prep_brief` additionally validates the caller-supplied hearing date against real `rocista` rows. |
| Case Actions | **Yes** | **Yes** | Present in `_case_context_blok`. |
| Readiness | **Yes**, and structurally enforced (deterministic cap on `procenat_min`/`procenat_max`) | **Yes** for `confidence_check` (feeds `_calc_confidence_nivo`'s own score); present but advisory-only for the remaining 4 | `confidence_check`'s own architecture (DC-004, deterministic scoring) was the natural place to wire readiness into an already-existing score, not just prompt text. |
| OCR metadata | **No** | **No** | Not part of the canonical contract at all yet (`TAU-013`, pre-existing gap from Tau 004) — not something this sprint's own scope (Court Predictor specifically) could add without first expanding the contract itself. |
| Parties | **Yes** | **Yes** | Present in `_case_context_blok`. |
| Hearings | **Yes** (as part of Deadlines — `rocista` includes both past and future, `proslo` flag from Tau 004) | **Yes** | Same field as Deadlines above — this platform doesn't track hearings as a conceptually separate item from deadlines. |
| Court metadata | **Partial** — `case_identity.sud` (the court's name), cross-checked against caller input in `battle_report`'s own consistency logic and `judge_profile`'s own dedicated check | Same (`judge_profile` specifically) | No STRUCTURED court-level data (jurisdiction rules, per-court filing deadlines) exists anywhere in this platform (`TAU-013`'s own finding, Tau 004) — only the court's own name string is available at all, and that's what's certified here. |

## What's explicitly NOT certified, and why (per the mission's own "ako nešto nedostaje: objasni zašto" rule)

- **OCR metadata and structured court-level data don't reach any endpoint** — neither exists in the
  canonical `build_case_context()` contract yet (`TAU-013`). This is a contract-expansion task, out of THIS
  sprint's own scope (Court Predictor migration specifically, not contract expansion).
- **5 of 7 endpoints don't see raw document text** — a deliberate cost/latency tradeoff for endpoints
  whose own reasoning task doesn't center on document content (see the table above and
  `PERFORMANCE_IMPACT_REPORT.md`).
- **`judge_profile` gets the lightest treatment of all 7** — its own request model has no
  case-description field at all (confirmed twice, independently, by `COURT_PREDICTOR_FORENSIC_REPORT.md`).
  It is architecturally about a court/judge, not a specific case. The one thing case context legitimately
  adds — a consistency check between the caller-typed court and the tracked case's own court — is what it
  gets, deliberately, not a forced full injection that wouldn't fit the endpoint's own purpose.

## Certification verdict

`prediktuj_ishod` and `battle_report` — the platform's own "predict this case's outcome" endpoints — now
see Genome, Documents, Evidence (via evidence_graph), Contradictions, Missing Evidence, Deadlines/Hearings,
Case Actions, Readiness (structurally enforced), Parties, and partial Court metadata: **10 of 13** checklist
items, certified with evidence (tests in `tests/test_tau005_court_predictor_migration.py`), not asserted.
The remaining 5 endpoints see a lighter but still real subset appropriate to their own narrower reasoning
task. OCR metadata and structured court data are named as genuine, pre-existing platform gaps (`TAU-013`),
not something this sprint could close without expanding the canonical contract itself.

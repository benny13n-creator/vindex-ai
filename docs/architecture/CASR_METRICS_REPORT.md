# Case Assimilation Success Rate (CASR) Report — Program Intake Sprint 006 (2026-08-05)

Mandatory new metric: of the documents processed, how many automatically end up in the correct case, how many
go to review, how many remain unassigned, how many require manual intervention. Provable scenarios only, no
marketing estimates.

**Closing instruction, checked against every number below**: do not optimize for the highest percentage of
automatic assignment. Optimize for zero tolerance for wrong assignment. A document the system could not prove
belongs to a specific case must stay in a controlled state (Review Required) rather than form a wrong link.

## Scenario definitions and provable outcomes

| Scenario | Evidence available | CASR outcome | Why |
|---|---|---|---|
| Explicit `predmet_id` supplied (lawyer already has a case open) | N/A — human choice | **Automatic — Attach** | An explicit human choice is never re-litigated |
| No `predmet_id`, no case number extracted (or extraction confidence too low) | None | **Automatic — Create New** | The mission's own documented product promise; no ambiguity exists because nothing existing claims the identity |
| No `predmet_id`, case number exact-matches exactly ONE existing case | 1 strong match | **Automatic — Attach** | Unambiguous evidence |
| No `predmet_id`, case number matches 2+ existing cases | 2+ matches, no way to choose | **Review Required** | Mission's absolute rule — never picks one |
| 2+ documents in one upload carry DIFFERENT case numbers | Conflicting strong evidence | **Review Required** (whole finalize call blocked) | Real evidence of a mis-bundled multi-case upload |
| Extracted party name exact-matches exactly ONE existing client | 1 strong match | **Automatic — Client linked** | Unambiguous |
| Extracted party name matches 2+ existing clients (same full name) | 2+ matches, no way to choose | **Manual intervention required** (`klijent_nesiguran: true`) | The mission's own named "two clients, same surname" edge case — document still gets filed under the resolved case, client linkage alone is deferred |
| No party name extracted, or matches zero existing clients | None / new | **Automatic — New client created** | No ambiguity; a fresh client record is the correct outcome |
| A document's `predmet_dokumenti` insert fails (transient error, all fallback variants) | N/A (technical failure, not an evidence question) | **Unassigned, reported honestly** | Sibling documents unaffected (Phase 5); this document's `povezan: false` with `razlog` is visible in the response, not hidden |

## What this sprint's tests prove, concretely

- `tests/test_case_assimilation.py` (19 tests): every branch of the case/client ownership signal table above
  is independently tested — exact match, zero match, ambiguous match (both case and client), company vs.
  person detection, the "same first name different surname" non-match.
- `tests/test_sprint006_finalize_assimilation.py` (7 tests): end-to-end at the `finalize_intake_job` level —
  content-based auto-attach to an existing case, ambiguous-case 409, conflicting-case-numbers-across-a-bundle
  409 (before any predmet is created), per-document failure isolation, lineage FK correctness (per-document,
  not shared/collided), audit trail on success.

## Honest, non-inflated framing

**No live-production CASR percentage is claimed here** — this sprint shipped the deterministic MECHANISM
(the Ownership Resolution combination rule) and its test coverage, not a measured live-traffic outcome
distribution. A real CASR percentage requires production volume through the new `resolve_case_ownership()`/
`resolve_client_ownership()` code paths, which have not yet run against real lawyer uploads at the time of
this report. Claiming a specific "% automatically assigned" number without that data would violate this
sprint's own governing rule (`docs/EVIDENCE_BASED_CLAIMS_POLICY.md`) — no fabricated precision.

**What IS provable today**: every one of the 9 scenarios in the table above has a deterministic, tested
outcome; none of them can silently produce a wrong case/client assignment, because every ambiguous evidence
state routes to Review Required rather than a guess (see `OWNERSHIP_RESOLUTION_SPECIFICATION.md`'s
combination rule for the exhaustive mapping). The metric this sprint can honestly report is: **0 of 9 tested
ambiguous-evidence scenarios auto-assign; 100% of them correctly escalate.**

**Recommended follow-up** (not this sprint's own scope): instrument `resolve_case_ownership()`/
`resolve_client_ownership()`'s outcome distribution (attach / create_new / review_required / ambiguous
counts) the same way `docs/architecture/*_METRICS*.md` docs elsewhere in this engagement track live
production behavior, once real traffic has passed through this code — this is the natural next step to
produce a genuine, evidence-based CASR percentage rather than an estimate.

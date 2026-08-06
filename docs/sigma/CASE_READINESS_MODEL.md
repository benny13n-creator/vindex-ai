# Case Readiness Model — Program Sigma, Master Sprint 004 (2026-08-06)

Phase 4 deliverable: a deterministic 5-state model (READY/PARTIALLY_READY/BLOCKED/CRITICAL_GAP/UNKNOWN)
built from evidence/documents/deadlines/procedural status/contradictions/gaps — never a GPT number.

## A real risk this sprint had to design around: 4 overlapping "readiness" concepts already existed

Before writing any new code, this sprint's own forensic fork found the codebase already has **4
independent, partially-overlapping "how ready/at-risk is this case" concepts** — meaning a naive 5th
addition would have been exactly the kind of "new parallel system" this sprint's own founding principle
forbids:

| Existing concept | File:line | Shape | Deterministic? |
|---|---|---|---|
| Case Ready Score | `services/case_pipeline.py::calculate_case_ready_score` (88-138) | 0-100 numeric score + checklist | Yes — but measures SETUP completeness (docs/clients/deadlines/strategy/risk/hearing present), a different question than procedural readiness |
| `procesni_rizik.nivo` | `services/risk_engine.py::calculate_procesni_rizik` | `nizak\|srednji\|visok` | Yes — case-level RISK, already documented (Sprint 006) as a deliberately separate concept from action priority |
| Uncertainty Score | `routers/matter_intel.py::get_uncertainty_dashboard` (line 269) | Numeric `uncertainty_score`, 5 hand-weighted "nesigurnost" dimensions | Partly — hand-weighted heuristic, not a clean deterministic derivation |
| **Pre-Flight status** | `routers/matter_intel.py::preflight_check` (line 473), `_PREFLIGHT_SYSTEM` prompt (line 445) | `"spreman" \| "potrebna_paznja" \| "nije_spreman"` | **No — GPT-generated.** The closest existing thing to Phase 4's own request, and it's exactly the kind of "GPT status string" this sprint's own Phase 5 explicitly forbids applied to priority |

**Decision: build the new model as its own function, do not touch the 4 existing ones.** Each of the 4 has
its own live consumers and its own product purpose (setup checklist, case risk, workload uncertainty,
pre-submission sanity check) — retrofitting or replacing any of them without live-browser verification of
every downstream consumer is a real, separate piece of work this sprint's own time budget did not include.
This document names the overlap explicitly (per Phase 1's own "no exceptions" discipline) rather than
silently ignoring it.

## The new model: `shared/case_readiness.py::compute_case_readiness`

A pure function over ALREADY-canonical signals — `case_actions.prioritet` (itself already
`shared/attention_priority.py`'s own canonical, deterministic vocabulary) and `shared/gap_engine.py`'s own
Gap records (Program Sigma Sprint 003) — no GPT call, no new detection.

| State | Trigger (first match wins) |
|---|---|
| `UNKNOWN` | Genome has never run for this case AND no `case_actions` exist yet — not enough signal |
| `CRITICAL_GAP` | Any open `case_actions` row has `prioritet == "critical"` |
| `BLOCKED` | No critical row, but an open `PRIBAVITI_DOKAZ`/`RAZRESITI_KONTRADIKCIJU` action has `prioritet == "high"` — a hard prerequisite not yet critical |
| `PARTIALLY_READY` | Any other open `case_actions` row exists (medium/low/informational), OR a GPT-only (`hipoteza: True`) Gap Engine finding exists with no deterministic backing |
| `READY` | Zero open `case_actions`, zero unresolved gaps |

Every result carries `razlog` (the specific triggering action/gap's own reason text) and `izvor` (its
`dedupe_key`(s)) — never a bare label, satisfying Phase 6's own "svaki element mora imati trag porekla"
requirement at the model's own output, not just at the `case_actions` row level.

## Why `BLOCKED` vs `CRITICAL_GAP` is drawn where it is

The mission's own 5-state vocabulary does not define the exact boundary between these two states — this is
a genuine design decision, made and documented here rather than left implicit. The distinction chosen:
`CRITICAL_GAP` means the deterministic engine has already flagged the SHARPEST possible signal (a
`case_actions.prioritet == "critical"` row — a deadline ≤3 days, zero evidence at all, or a critical
contradiction); `BLOCKED` means a real, still-unresolved prerequisite exists (missing evidence or an
unresolved contradiction) that has not yet escalated to critical. This mirrors how a lawyer would actually
describe the two states in conversation ("this case is blocked on X" vs. "this case has a critical
problem") — not an arbitrary numeric threshold.

## 8 new tests, all passing

`tests/test_sigma_sprint004_case_readiness.py` proves each of the 5 states individually (including 2
negative controls: a high-priority NON-blocking-type action must NOT trigger `BLOCKED`; a deterministic
[`hipoteza: False`] gap with no corresponding action must NOT alone trigger `PARTIALLY_READY`, since
deterministic findings are expected to already be represented via `case_actions`).

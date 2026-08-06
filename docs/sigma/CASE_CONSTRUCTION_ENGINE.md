# Case Construction Engine — Program Sigma, Master Sprint 001 (2026-08-06)

Phase 3 deliverable: for a single `predmet`, verify each required field is populated by an AUTOMATIC,
already-wired mechanism (not a manual/GPT step nobody connected), with the exact writer cited. Where a
field is *supposed* to auto-populate but the write path had a real bug, that bug is named and, where safe,
fixed this sprint.

## Completeness matrix

| Field | Auto-populated? | Writer | Notes |
|---|---|---|---|
| identitet (`predmeti` row) | Yes | `routers/smart_intake.py:656` (`_create_new_predmet_from_value_map`) | 5 other creation sites exist (`api.py:3133`, `routers/intake.py`, `routers/onboarding.py`, `routers/integracije.py`) — not a duplication of THIS row (each creates a distinct case), a legitimate multi-entry-point product surface |
| stranke (parties, `klijenti`/`predmet_klijenti`) | Yes, best-effort | `routers/smart_intake.py:1002-1058` via `shared/case_assimilation.py::resolve_client_ownership` | Wrapped in a non-fatal try/except (line 1059) — a failure here silently produces a case with NO linked client and nothing flags it; see `SYSTEM_GAP_REPORT.md` |
| dokumenti (`predmet_dokumenti`) | Yes | `routers/smart_intake.py:1295-` | Content-hash-checked per document |
| dokazi (`predmet_dokazi`) | Yes | `_consequence_evidence_classify` (`services/case_evolution.py:323`) via `NEW_EVIDENCE_REGISTERED`, `routers/evidence.py:256` | Per-document, GPT-driven, up to 5 facts/doc |
| rokovi (`predmet_hronologija`/`rocista`) | Yes, best-effort | `routers/smart_intake.py:1109-1127` (one deadline, from the anchor document's own extracted field, non-fatal) + `case_actions`' own Rule 1 | Only the ANCHOR document's own deadline is captured at finalize time — not every document's own deadline; the more thorough coverage comes from `case_actions`' own ongoing Rule 1 recompute reading `rocista`, not from this one-shot capture |
| sud, broj predmeta, status | Yes | Same `predmeti` insert (`routers/smart_intake.py:663`) | `broj_predmeta` only set if extraction actually found a case number |
| istorija (`predmet_istorija`) | **Was NO for Smart Intake before this sprint's fix** | 6 pre-existing writer sites (`api.py`, `rocista.py`, `matter_intel.py`, `case_pipeline.py` ×5) | Smart Intake's own case-creation path never triggered `case_pipeline.py`'s own `_step_istorija` — the very FIRST "case created" entry never got written for the dominant creation path. **Fixed this sprint** — see `END_TO_END_PIPELINE.md`'s own headline finding |
| vremenska linija (Timeline) | Yes | `_consequence_timeline_entry` via `DOCUMENT_ACCEPTED` | Confirmed |
| AI analiza / genome (`case_dna`) | Yes | `_consequence_genome_refresh` via `DOCUMENT_ACCEPTED` | Confirmed |
| strategija | **Was NO for Smart Intake before this sprint's fix** | Only `case_pipeline.py::_step_strategija` | Never auto-ran for Smart-Intake-created cases — a lawyer had to manually trigger Strategy via `routers/strategija.py`. **Fixed this sprint** |
| akcije (`case_actions`) | Yes | `_consequence_refresh_case_actions` via `DOCUMENT_ACCEPTED` | Confirmed |

## The fix, and why it's scoped the way it is

Full mechanics in `END_TO_END_PIPELINE.md`'s own "Headline finding" section. Summary: `routers/
smart_intake.py` now emits `PREDMET_KREIRAN` exactly once per genuinely-new case, wiring in the 5
previously-missing Case Pipeline steps (`auto_linking` read-only, `kalendar` read-only, `strategija`
additive, `hcc` additive, `risk_snapshot` additive, `copilot_preporuka` no DB write, `istorija` additive) —
while deliberately EXCLUDING `ekstrakcija_rokova` (the one step that would have written to the same
un-deduplicated `predmet_hronologija` table Smart Intake's own initial-deadline capture already writes to,
a real near-duplicate risk this sprint's own "no duplication" mandate required avoiding).

## Remaining known gap: client-linking silent failure

`resolve_client_ownership`'s own call site wraps client linking in a bare try/except that does not surface
a failure anywhere the lawyer would see — a case could be fully "complete" by every other measure (documents,
Genome, deadlines) but have ZERO linked client, with no flag distinguishing "genuinely no client mentioned
in the documents" from "client-linking silently failed." Not fixed this sprint (surfacing this correctly
needs a product decision on where/how to flag it — a new dashboard warning, a Case Ready Score deduction,
or a retry mechanism — each a different UX choice, not a mechanical fix). Recorded as `SIGMA-001` in the
Architectural Debt Register.

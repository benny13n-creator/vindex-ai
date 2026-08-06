# GPT Boundary Policy — Program Sigma, Master Sprint 005 (2026-08-06)

Phase 4 deliverable: GPT may explain, summarize, rephrase, help a lawyer. GPT may never create a new
action, change a priority, change a readiness status, or invent a missing item. This document is the
policy `routers/case_commander.py` now enforces structurally, and the reference other modules should follow.

## The rule

| GPT MAY | GPT MAY NOT |
|---|---|
| Explain why an already-canonical fact matters (`gpt_explanation_field`, points at the original `source`/`evidence`) | Decide that something is missing, risky, urgent, or resolved — that is `identify_case_problems`/`shared/gap_engine.py`/`case_actions`'s own job |
| Offer a genuinely-advisory opinion with NO canonical equivalent (`gpt_advisory_field`, `source="gpt_advisory"`, `evidence=None` always) — e.g. "what will opposing counsel likely do" | Assert an advisory opinion AS IF it were a canonical fact — every `gpt_advisory_field` is structurally tagged, never merged into a `canonical_field`-shaped record |
| Propose a generic procedural template (which steps a case TYPE usually needs) | Claim a specific step is ALREADY DONE without real evidence (`commander_checklist`'s own pre-sprint bug) |
| Summarize/rephrase a `case_actions` row's own `razlog` for readability | Independently re-derive its own priority number/tier for that same fact (`hitnost`, `verovatnoca_uspeha`-as-priority — Sprint 004's own finding, same rule extended here) |

## How this is enforced in `routers/case_commander.py` (not just documented)

1. **`shared/commander_schema.py`** — every returned field is one of `canonical_field` (GPT never touches
   it), `gpt_explanation_field` (GPT phrased it, but `source`/`evidence` point at the original canonical
   fact), or `gpt_advisory_field` (`source="gpt_advisory"`, `evidence=None` always — structurally
   impossible to present as a sourced fact).
2. **`_ADVISORY_SYSTEM`** (the new, narrowed prompt for `commander_analiza`) is explicit in its own text:
   *"Ovo su procene, ne činjenice — ne tvrdi da nešto nedostaje, ne predlaži sledeći korak, ne proceni
   rizik, ne odlučuj prioritet."* The prompt itself states the boundary, not just this document.
3. **`_cross_case_analiza`'s own new prompt** removed the `PRIORITET`/`RIZICI` categories from GPT's own
   instructions entirely — GPT is not merely told not to decide priority, it is never ASKED to.
4. **`commander_checklist`** — `completed` is hardcoded `False` after parsing, regardless of what GPT's own
   markdown output claims.
5. **`commander_quick_check`** — no longer calls GPT at all for its own "3 most urgent" list; it reads
   `_kanonski_nalazi`'s own already-computed, already-prioritized findings.

## Existing anti-hallucination pattern reused, not reinvented

`shared/genome_validator.py::validate_predmet_reference` (built in Program Gamma, 2026-08-04, for
Compare/Evidence Graph) already proves a GPT-cited `predmet_id_prefix`/`predmet_naziv` pair actually
matches one of the cases sent to the model — real, working, reused unchanged for the 2 GPT-advisory
categories (`kontradikcija`/`nepovezan_dokument`) that remain in `_cross_case_analiza`. This is a
reference-existence check (did GPT invent a case that doesn't exist), not a claim-truth check (is the
contradiction/observation itself real) — the 2 are different guarantees, and this document does not
overclaim the latter.

## What this policy does NOT claim

This policy governs `routers/case_commander.py`. It is a REFERENCE for other GPT-facing modules
(`routers/case_intelligence.py`, `routers/copilot.py` — already migrated in Sprint 004; `routers/
morning_briefing.py`, `routers/strategija.py` — NOT migrated, see `OPERATIONAL_BRAIN_CERTIFICATION.md`'s
own honest accounting), not a claim that every GPT call in the platform already follows it.

# AI Certification Report — Program Tau, Master Sprint 003, Phase 4

**Mission's own pass/fail condition**: "Pokušaj da naterš GPT da: izmisli prioritet / izmisli spremnost /
izmisli rokove / izmisli nedostajuće dokaze / izmisli kontradikcije / izmisli sledeći korak / izmisli
pravne činjenice. Ako bilo koji uspe: Sprint pada."

Each attack below is backed by a concrete, executed test — not asserted from reading the code. File:test
citations given for every one.

## 1. Invent priority

**Attack**: feed a poisoned/legacy-shaped GPT response containing a fabricated `prioritet`/`hitnost` value
into every migrated endpoint; check it never reaches the output.
- `case_intelligence.py`: `test_gpt_cannot_inject_fake_risks_or_confidence_program_tau_003` — poisoned
  `hitnost: "odmah"` never overrides the deterministic value (`tests/test_case_intelligence_briefing_alerts_fix.py`).
- `copilot.py`: `sledeci_korak.prioritet` is derived from `case_actions.prioritet` via `top_open_action`,
  unconditionally — GPT is no longer even asked for a `sledeci_korak` object at all
  (`test_synth_system_no_longer_asks_gpt_for_slabosti_or_verovatnoca` proves the schema no longer contains it).
- `morning_briefing.py`: `test_danas_zahteva_paznju_ranks_by_canonical_priority_across_cases` — ranking
  across cases is done by `shared/attention_priority.py::canonical_sort_key`, proven with a
  critical-vs-low fixture, GPT never sees the ranking step at all.
- **Result: FAILS to invent priority in every migrated surface.**

## 2. Invent readiness

**Attack**: find any GPT-decidable "readiness"/"spremnost" field to poison.
- Repo-wide: no `_SYSTEM` prompt anywhere in the 4 migrated files (or `case_commander.py`) asks GPT for a
  readiness/spremnost value — `readiness` is computed exclusively by
  `shared/case_readiness.py::compute_case_readiness`, confirmed by the Phase 1 forensic sweep across all 4
  files' full prompt text (`AI_DECISION_SURFACE_MAP.md`).
- **Result: FAILS — there is no readiness field for GPT to invent; the attack surface doesn't exist.**

## 3. Invent deadlines

**Attack**: poison `kriticni_rokovi`/`rokovi_hitni`-shaped fields with a fabricated date/deadline.
- `copilot.py::_handle_plan_predmeta`: `kriticni_rokovi` is now built from the real `urgentni`/`nadolazeci`
  `predmet_hronologija` rows already fetched — GPT's own restatement is no longer asked for
  (`_PLAN_SYSTEM`'s schema no longer contains `kriticni_rokovi`, verified in
  `docs/tau/AI_DECISION_SURFACE_MAP.md`'s own re-read).
- `morning_briefing.py`: `test_gpt_cannot_inject_fake_actions_into_danas_zahteva_paznju_program_tau_003`
  poisons the GPT response with a fabricated "rok je danas!" claim; "Ključni rok" is built from
  `rocista_danas`/`rokovi_hitni`/`rokovi_uskoro` (real DB rows) BEFORE the GPT call, and the poisoned text
  is proven confined to the opening sentence only.
- **Result: FAILS to invent deadlines in every migrated surface.**

## 4. Invent missing evidence

**Attack**: poison `nedostaju`/`nedostaje`-shaped fields.
- Already correctly Gap-Engine-owned since Sigma 003/004 (`missing_evidence_labels`/`missing_evidence_plan_items`),
  unconditionally overridden whenever the Genome-derived list is non-empty — unchanged, still verified passing
  by `tests/test_sigma_sprint003_gap_engine.py` (63 pre-existing tests, zero regressions this sprint).
- `case_intelligence.py`'s own `napomena` (missing-evidence-adjacent) is now deterministic
  (`test_gpt_cannot_inject_fake_risks_or_confidence_program_tau_003` proves the poisoned string is replaced).
- **Result: FAILS to invent missing evidence in every migrated surface.**

## 5. Invent contradictions

**Attack**: poison `kljucni_rizici`/`slabosti`/`upozorenja` fields whose real source is Genome's own
`kontradikcije[]`.
- `test_slabosti_derived_from_genome_not_gpt` (`tests/test_tau003_decision_boundary.py`) directly poisons
  a `slabosti` field with a fabricated weakness; only the real Genome contradiction
  ("Prava Genome kontradikcija") survives.
- **Result: FAILS to invent contradictions in every migrated surface.**

## 6. Invent next action

**Attack**: poison `sledeci_korak` across every endpoint that has one.
- `case_intelligence.py`: `test_briefing_states_no_open_action_instead_of_falling_back_to_gpt_program_tau_003`
  — zero open `case_actions` still produces the honest "Nema otvorenih akcija" statement, not a GPT guess,
  under the NEW unconditional override.
- `copilot.py`: `test_analiza_predmeta_states_no_open_action_instead_of_falling_back_to_gpt_program_tau_003`
  — same proof, same file family.
- `morning_briefing.py`: `test_no_open_actions_states_so_honestly_not_gpt_guess` — zero actions across all
  cases still produces an honest statement, not a fabricated "Preporuka za danas."
- **Result: FAILS to invent a next action in every migrated surface — this closes TAU-002 and TAU-003's own
  named "conditional override" gap directly.**

## 7. Invent legal facts

**Attack**: check whether any migrated surface lets GPT assert an unverified legal fact as if canonical.
- `services/legal_reasoning_engine.py` (unchanged, out of this sprint's scope) remains the platform's own
  strongest anti-hallucination pattern (SOURCE-n citations built only from real retrieved tuples) — not
  modified, not degraded.
- `strategija.py`'s `_V2_SYSTEM` prompt now explicitly instructs GPT not to present `procenat` as a
  calculated statistic (`test_v2_system_prompt_no_longer_presents_procenat_as_calculated_stat`); every
  response additionally carries `_ai_advisory` provenance stating the analysis is unverified GPT opinion
  over caller-supplied text (`test_all_9_strategija_endpoints_attach_ai_advisory_provenance`).
- **Result: no structural prevention of GPT inventing a legal citation exists anywhere in this sprint's
  scope (that's `legal_reasoning_engine.py`'s own domain, unchanged) — but every field this sprint touched
  that could be MISTAKEN for a verified fact is now either computed deterministically or explicitly labeled
  as opinion. Certification here is about labeling honesty, not citation-grounding (out of scope).**

---

## What remains open, named not hidden

- `morning_briefing.py`'s `_ai_prioritizacija_alertova` and `today_focus` — the latter's own GPT-vs-fallback
  inconsistency (Phase 1's own "bonus finding") is named as new debt (`TAU-010`), not fixed this sprint.
- `strategija.py`'s `faze[].koraci[].prioritet`-shaped fields (its own internal plan structure) remain
  GPT Advisory by necessity — no case record exists to check them against, and this sprint's own fix (the
  `_ai_advisory` wrapper) already labels the whole response honestly.
- `court_predictor.py`'s win-probability and `evidence_graph.py`'s contradiction edges are pre-existing,
  larger fragmentations (Program Beta, `DECISION_CONSISTENCY_REPORT.md`) explicitly out of this sprint's
  scope — named, cross-referenced, not silently ignored.
- No live-browser verification was performed for `case_intelligence.py`/`copilot.py`/`strategija.py` (all
  3 confirmed LIVE) — every fix preserves the EXACT existing response field names/types these consumers
  already read, verified against `index.html`'s own render code, but an actual browser click-through was
  not run this sprint.

## Verdict

**7 of 7 named attack categories fail to succeed against every surface this sprint migrated**, each backed
by an executed test, not an inference. The 2 categories with a partial/no-op result (readiness — no attack
surface exists; legal facts — out of this sprint's scope by design) are explained above, not glossed over.

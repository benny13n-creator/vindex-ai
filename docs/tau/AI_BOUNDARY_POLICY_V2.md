# AI Boundary Policy v2 — Program Tau, Master Sprint 003

Supersedes `docs/sigma/GPT_BOUNDARY_POLICY.md` (Case Commander only) and `docs/tau/LEGAL_AI_BOUNDARY_POLICY.md`
(Tau 001, survey without migration) as the platform-wide statement of what changed. The rule itself is
unchanged — this document exists to state, precisely, which modules now enforce it and how.

## The rule (unchanged since Sigma 005, restated as binding platform-wide policy)

| GPT MAY | GPT MAY NOT |
|---|---|
| Explain why an already-canonical fact matters | Decide that something is missing, risky, urgent, or resolved |
| Offer an advisory opinion with no canonical equivalent, structurally tagged as such | Assert an advisory opinion as if it were a canonical fact |
| Propose a generic procedural template or draft | Claim a specific step is already done without real evidence |
| Summarize/rephrase a canonical fact for readability | Independently re-derive a priority/urgency/readiness number for that same fact |

This is architectural, not model-capability-dependent — a smarter model does not relax any MAY-NOT above.

## What changed this sprint, module by module

### `routers/case_commander.py` — unchanged, still the reference implementation (Sigma 005)

### `routers/case_intelligence.py` — CLOSED (was TAU-002's own subject for this file)
`sledeci_korak`/`razlog`/`hitnost` are no longer even asked of GPT — computed unconditionally from
`case_actions` via `top_open_action`. `kljucni_rizici` now reads `case_context`'s own
`missing_evidence`/`contradictions`. `napomena` and `pouzdanost_briefinga` are deterministic (data-
completeness derived), never GPT self-report. `relevantne_lekcije`/`komunikacioni_savet`/`potvrdjeni_obrasci`
remain GPT, now provenance-tagged (`_ai_provenance` sidecar, additive, live-frontend-safe).

### `routers/copilot.py` — CLOSED (was TAU-002's own subject for this file)
Both handlers' `sledeci_korak` overrides are now unconditional. `slabosti`/`upozorenja` read Genome via
`shared/gap_engine.py`. `verovatnoca_uspeha` reads Genome's own `snaga_predmeta_procent` directly (no
independent GPT number). `kriticni_rokovi` returns the real `predmet_hronologija` rows, not a GPT
restatement of them. `nedostaju`/`nedostaje` were already correctly Gap-Engine-owned (Sigma 003/004),
unchanged.

### `routers/morning_briefing.py` — CLOSED for the flagship call site (was TAU-003)
`_generiši_briefing`'s "Danas zahteva pažnju"/"Ključni rok"/"Preporuka za danas" are now built entirely in
code from `case_actions` (ranked via `shared/attention_priority.py::canonical_sort_key`, the same order
Sigma 005 uses platform-wide) and `rocista`/`rokovi`. GPT is asked for exactly one sentence (the "Dobro
jutro" opening tone) — structurally incapable of reaching the 3 decision-bearing sections, proven by test
(`test_gpt_cannot_inject_fake_actions_into_danas_zahteva_paznju_program_tau_003`). `_ai_prioritizacija_alertova`
and `today_focus` remain unmigrated this sprint — the former was already correctly scoped (GPT rephrases a
deterministic list, proven by its own fallback identity), the latter is named as new debt (`TAU-010`, see
`ARCHITECTURAL_DEBT_REGISTER.md`).

### `routers/strategija.py` — labeled, not redirected (no canonical source exists to redirect to)
No `predmet_id` exists anywhere in this file — confirmed twice, independently, by Tau 002 and Tau 003.
`sistemsko_upozorenje` and `detektovani_konflikti`'s categorical half remain correctly code-owned
(`DC-010`/`DC-011`, unchanged). Every one of the 9 endpoints now attaches `_ai_advisory` provenance
(additive, live-frontend-safe) stating plainly that the response is a GPT opinion over unverified,
caller-supplied text, not a checked platform fact. `procena_uspeha.procenat`'s own prompt text now
explicitly disclaims it as a subjective estimate, not a calculated statistic.

## Mandatory human confirmation before downstream action (unchanged from Tau 001)

Anything that would create, close, or reprioritize a `case_actions` row; anything filed or sent externally;
anything affecting a court deadline; any GPT-drafted document before it leaves the platform in the lawyer's
name. None of the above may be triggered by a GPT output directly, in this or any future architecture —
this sprint's own migrations reinforce that boundary, they do not relax it anywhere.

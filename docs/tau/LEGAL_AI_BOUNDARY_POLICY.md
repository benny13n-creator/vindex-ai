# Legal AI Boundary Policy — Program Tau, Master Sprint 001 (Agent 5, Phase 1 analysis)

Extends `docs/sigma/GPT_BOUNDARY_POLICY.md` (governs `routers/case_commander.py` only, already
implemented and enforced) to the rest of the platform, in the context of GPT-5.1 being introduced as a
deeper reasoning layer. This document is analysis + policy, not a claim that the rest of the platform
already complies — see the survey below, which found modules that do not.

## The rule (unchanged from Sigma 005, restated as the platform-wide standard)

| GPT MAY | GPT MAY NOT |
|---|---|
| Explain why an already-canonical fact matters | Decide that something is missing, risky, urgent, or resolved — that's `identify_case_problems`/`shared/gap_engine.py`/`case_actions`'s job |
| Offer an advisory opinion with no canonical equivalent, structurally tagged as such | Assert an advisory opinion as if it were a canonical fact |
| Propose a generic procedural template | Claim a specific step is already done without real evidence |
| Summarize/rephrase a canonical fact for readability | Independently re-derive a priority/urgency number for that same fact |

This is an **architectural** restriction, not a model-capability one. GPT-5.1 being a better reasoner does
not relax any MAY-NOT above — a smarter model that invents a missing-evidence list is still inventing it.

## Survey: does each module already respect this boundary? (verified against current code, 2026-08-06)

| Module | GPT surface | Reads `case_actions`/canonical sources? | Verdict |
|---|---|---|---|
| `routers/case_commander.py` | all 8 surfaces | Yes — migrated fully in Sigma 005 | **Compliant** (reference implementation) |
| `routers/case_intelligence.py` | briefing top-action (~L371-397) | Yes, but only as an **override with GPT fallback**: `top_open_action(case_actions)` overrides GPT's own guess only when an open action exists; falls back to "GPT's own guess" (per the code's own comment) when `case_actions` is empty | **Partially compliant** — GPT can still invent a next action when the canonical table has nothing open |
| `routers/copilot.py` | analiza next-action (~L434-454) | Same override-with-fallback pattern as above | **Partially compliant**, same gap |
| `routers/morning_briefing.py` | "Danas zahteva pažnju" (2-4 prioritized actions), "Preporuka za danas" | **No** — zero references to `case_actions` anywhere in the file; the prompt (L185-204) builds the action list purely from raw context text (rokovi/predmeti/ročišta strings) with no canonical override at all | **Non-compliant** — same shape of violation `case_commander.py` had pre-Sigma-005 |
| `routers/strategija.py` (`_V2_SYSTEM`, L349-371) | `kljucni_rizici`, `nedostajuci_dokazi`, `sledeci_koraci` (each with its own `prioritet`) | **No** — no `case_actions`/`gap_engine`/`identify_case_problems` read found; all 3 categories are GPT-invented directly from case text in one JSON call | **Non-compliant** — a 3-way independent duplicate of exactly the categories Sigma 005 consolidated in Case Commander |

**Both already-documented gaps** (`morning_briefing.py`, `strategija.py`) were flagged, not newly
discovered, in `docs/sigma/GPT_BOUNDARY_POLICY.md`'s own closing section and
`OPERATIONAL_BRAIN_CERTIFICATION.md` — this survey independently re-verifies both against current code
rather than re-citing the prior claim, and additionally identifies that `case_intelligence.py`/
`copilot.py`'s own "migration" is a fallback override, not a full removal of the GPT-invention path, which
neither prior document stated explicitly.

The other ~38 files with OpenAI calls (drafting, evidence, precedents, court_predictor, etc.) were **not**
individually surveyed here — full inventory is Agent 1's (`AI_ARCHITECTURE_MAP.md`) job; this document only
classifies the subset named in this sprint's own scope plus what a full-file `case_actions` grep found.

## Where GPT-5.1 as a reasoning layer adds legitimate value

| Legitimate use | Why capability matters here |
|---|---|
| Multi-step legal argument construction FROM already-canonical facts (e.g., draft an argument citing the specific `dokazi`/`case_actions` rows already on file) | Reasoning quality genuinely improves the output; the facts themselves are not invented |
| Explaining WHY a `readiness_status` or `identify_case_problems` finding is what it is, in plain language for the lawyer | Explanation is explicitly MAY; better reasoning = better explanation, not a new decision |
| Drafting assistance (letters, submissions) grounded in supplied facts | Generation is not decision-making as long as facts are supplied, not invented |
| Spotting a pattern across evidence a lawyer already has (e.g., "these 3 already-logged `dokazi` rows are mutually inconsistent") | A genuinely advisory synthesis task with no canonical equivalent — must stay `gpt_advisory_field`-tagged, never merged into canonical output |

## Where GPT-5.1 must stay hard-restricted regardless of model capability

Creating a `case_action`; changing `prioritet`/`hitnost`/readiness status; asserting something is missing
or resolved; bypassing `case_actions`/`gap_engine`/`case_readiness`/`identify_case_problems` with an
independently-derived equivalent. These are architectural boundaries (Core Consolidation, 2026-07-22: "1
koncept = 1 vlasnik = 1 algoritam = 1 istina") — GPT-5.1 is not a new owner candidate for any of them.

## Mandatory human confirmation before downstream action

- Anything that would create, close, or reprioritize a `case_actions` row.
- Anything that would be filed or sent externally (court submissions, client communications).
- Anything affecting a court deadline (`rocista`, procedural rok calculations).
- Any GPT-drafted document before it leaves the platform in the lawyer's name.

None of the above may be triggered by a GPT output directly in the current or any GPT-5.1 architecture;
all require an explicit lawyer action on a canonical row.

# Gap Engine Registry — Program Sigma, Master Sprint 003 (2026-08-06)

Phase 1 deliverable: repo-wide inventory of every mechanism that already reports missing evidence, missing
documents, incomplete cases, unresolved contradictions, or legal risk, classified CANONICAL/PROJECTION/
LEGACY/DEAD. Every claim below cites a file:line actually read this sprint (2 forensic forks).

## CANONICAL mechanisms (each owns a distinct, non-overlapping domain)

| Mechanism | File:line | Type | Domain |
|---|---|---|---|
| `identify_case_problems` | `services/risk_engine.py:157-` | Deterministic, code-computed | "What's wrong with THIS case" — reused by Cockpit/Matter Intel/Case Ready Score/`case_actions` Rule 2/4/5. Output phrased as fact ("Nedostaje X u spisu") and IS fact — a literal comparison against `EXPECTED_DOCS`, not an inference |
| Genome `case_dna.nedostaje[]` | `routers/case_dna.py:120-122` (extraction prompt) | GPT-extracted | Case-level, holistic missing-evidence inference. **The prompt has no explicit hedge instruction** ("only if reasonably certain," "mark as hypothesis") — an output-shape spec only, not currently enforcing Phase 2's own "hipoteza, ne činjenica" requirement at the source |
| `nacrti/checklist_engine.py::analiziraj_checklist` | `nacrti/checklist_engine.py:78-`, wired at `routers/drafting.py:846-870` | GPT + keyword fallback | **Previously-uncatalogued, live, CANONICAL for its own domain**: checks whether a lawyer's free-text facts (typed BEFORE drafting a document) cover all legally-required elements for that document type. Confirmed live (`static/vindex.js:7305`). Different domain than case-FILE completeness — checks draft-INPUT completeness, not what's in the case's own document set — not a duplicate, a useful design-shape precedent (see `GAP_ENGINE_REGISTRY.md`'s own Phase 2 record shape below) |
| `services/legal_reasoning_engine.py::generate_reasoning_graph` | Lines 328-332 | Deterministic gate + GPT | **A relevant near-miss, not currently a gap-reporter.** Builds `Fact→LegalElement→Norm→Claim` chains but only accepts a chain with `>=1 fact AND >=1 norm` (line 331) — any legal element GPT considers unsupported is silently `continue`-skipped, never recorded anywhere. This is the ONE place in the codebase structurally positioned to detect "this legal element has zero supporting evidence," and it currently discards that signal. See "Deliberately not wired" below for why |

## NOT-CANONICAL: 2 independent GPT "missing items" generators found and fixed this sprint

`routers/copilot.py` had **2 separate GPT calls, in 2 different handlers, each independently producing its
own free-form "what's missing" list**, neither backed by `EXPECTED_DOCS` nor reliably reading Genome:

- `_handle_analiza_predmeta` (line ~335-421): its own prompt DID softly reference Genome context for
  OTHER fields (procena/prednosti/slabosti), but its own `"nedostaju"` field was still independently
  GPT-generated, not read from Genome.
- `_handle_plan_predmeta` (line ~468-529): had **zero Genome context of any kind** — a fully independent
  3rd "missing items" GPT inference, blind to Genome's own already-computed list.

Combined with Genome's own `nedostaje[]`, this was **3 independent GPT-generated "what's missing"
surfaces** — the clearest, most concrete, live violation of this program's own "jedan mehanizam postaje
vlasnik" founding principle found this sprint, not a hypothetical risk. **Fixed this sprint** — see
`CANONICAL_FACT_ENGINE.md`... [continued in `SIGMA_MASTER_SPRINT_003_REPORT.md`'s own "Popravljeno" section].

## PROJECTION (correctly reuses, does not re-derive)

`routers/case_intelligence.py:266-268` (AI Briefing) — reads `genome.get("nedostaje")` directly, generates
nothing of its own. Confirmed as the pre-existing correct model; `routers/copilot.py`'s own 2 handlers now
follow it too (this sprint's own fix, via `shared/gap_engine.py`).

## LEGACY / DEAD

None found for this specific concern. `routers/zastarelost.py`, `routers/court_predictor.py`,
`routers/health_index.py` have zero matches for missing-evidence/incomplete-case concepts — confirmed
genuinely out of this domain, not silently duplicating it.

## Deliberately not wired this sprint: the Legal Reasoning Engine's own discarded signal

`services/legal_reasoning_engine.py`'s own module docstring records an explicit, founder-stated Phase 0
constraint (2026-07-23): *"Wired to nothing: no automatic trigger, no downstream consumer reads this yet.
Manual generation only."* This is a deliberate architectural staging decision, not an oversight — the
docstring itself distinguishes Phase 0 (current) from a future Phase 1 that would extend consumption.
Surfacing its own silently-discarded unsupported `LegalElement` nodes as Gap records would mean adding the
Gap Engine as this module's first-ever downstream consumer, directly overriding that explicit founder
boundary. **Not done this sprint** — named precisely, with the exact fix already scoped (don't discard,
record), for whichever future sprint the founder authorizes to open Phase 1 of the Legal Reasoning Engine
itself. Recorded as `SIGMA-012` in the Debt Register.

## Status/lifecycle concepts found (Phase 5's own starting precedent)

No OPEN/CONFIRMED/REJECTED/RESOLVED/SUPERSEDED-style status exists anywhere for a "finding" or "flag"
beyond `case_actions.status` (open/closed, binary) and Program Sigma Sprint 002's own contradiction-identity
work (which itself has no richer state machine yet — `SIGMA-010`, still open). **A strong, already-proven
precedent was found**: `lessons_learned.status_lekcije` (`migrations/039_epistemic_confidence.sql:12-13`) —
`'predlog_ai' → 'usvojena_praksa' (partner confirms) | 'odbijena' | 'zastarela'`, with `potvrdio`/
`potvrdjeno_at` (who/when confirmed) and a SEPARATE `pouzdanost` confidence column. Two weaker cousins also
found: `migrations/082_agent_recommendations.sql:21` (`pending/accepted/rejected`) and
`migrations/088_staging_memory.sql:40` (`pending/approved/rejected`) — same shape, narrower vocabulary. See
`LEGAL_HYPOTHESIS_ENGINE.md` for the full design built on this precedent.

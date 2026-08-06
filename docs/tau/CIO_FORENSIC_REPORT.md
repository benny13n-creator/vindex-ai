# CIO Forensic Report — Program Tau, Master Sprint 008, Phase 2

Full-file forensic read of `routers/cio.py` (468 lines, 3 endpoints, all delegating to
`_generiši_cio_izvestaj`/`_kompaktan_predmet`). For each of the 3 endpoints: what it reads, what it ignores,
what it computes, what GPT concludes, what should be deterministic.

## What CIO reads today — confirmed independent of every canonical source

`_generiši_cio_izvestaj` fetches 4 tables directly: `predmeti` (id/naziv/oblast_prava/updated_at/`case_dna`,
up to 40 active cases), `firm_dna`, `lessons_learned`, `case_patterns`. **Zero calls** to
`build_case_context()`, `case_actions`, `shared/case_readiness.py`, or `shared/gap_engine.py` anywhere in
this file — confirmed by direct grep, not assumed from Sprint 007's own prior finding (`TAU-017`).

## What CIO computes — `_kompaktan_predmet`, entirely Genome-sourced, bypassing every normalizer

| Signal | Current source | Canonical equivalent | Bypasses |
|---|---|---|---|
| `snaga` | `case_dna.snaga_predmeta_procent` | Same field, via `build_case_context()`'s own `key_facts` | Nothing — same source either way |
| `najslabija_tacka` | `case_dna.najslabija_tacka` | Same field, via `key_facts` | Nothing — same source either way |
| `dana_bez_aktivnosti` | `predmeti.updated_at` date diff | No canonical staleness metric exists platform-wide | Nothing — legitimately bespoke, not a duplicate of anything |
| `rokovi_aktivni` | **`case_dna.rokovi_kriticni`** — Genome's OWN GPT-extracted deadline list | Canonical `deadlines` (from `rocista` table, real structured data, via `build_case_context()`) | **A 3rd, previously unknown deadline source** — see finding below |
| `kontradikcije_kriticne` | `case_dna.kontradikcije` filtered directly (`tezina=="kriticna"`) | Canonical `contradictions` (`shared/gap_engine.py::gaps_from_contradictions`, identity-tracked via `shared/contradiction_identity.py`) | The canonical normalizer's own empty-`opis` filter and stable dedupe-key assignment |
| `nedostaje_kriticno` | `case_dna.nedostaje` filtered directly (`hitnost=="kriticno"`) | Canonical `missing_evidence` (`shared/gap_engine.py::gaps_from_genome_nedostaje`) | The canonical normalizer |
| `portfolio_zdravlje.kriticnih_rizika` | Count of `najslabija_tacka.kriticnost >= 85` — Genome's own ad hoc 0-100 heuristic | No canonical equivalent scale — closest is `readiness.status in (CRITICAL_GAP, BLOCKED)` | Nothing directly, but disagrees in spirit with the platform's own canonical definition of "critical" |

## New finding: a 3rd independent deadline source, beyond the already-known `rocista`/`rokovi` split

`TAU-013` (Master Sprint 004) and its Master Sprint 006/007 corroborations named the `rocista` table
(canonical `deadlines`) vs. the `rokovi` table (used by `case_commander.py`, `decision_replay.py`,
`zadaci.py`, `digital_twin.py`) as 2 competing deadline sources. `cio.py` reveals a genuinely different,
**3rd** source: `case_dna.rokovi_kriticni[]` — a list GPT extracts and embeds INTO the Genome object itself
during Genome extraction (`routers/case_dna.py`), never cross-checked against either DB table. This means a
deadline could exist in `rocista` (real, structured) but be silently absent from Genome's own
`rokovi_kriticni` (if the extraction pass missed it or ran before the deadline was added), or vice versa
(Genome could "see" a deadline mentioned in document text that was never entered into `rocista` at all) — CIO's
own portfolio report is the ONLY consumer of this 3rd source found in this sprint's own census.

## What GPT concludes — and which of it should be deterministic

The system prompt (`_CIO_SYSTEM`) asks GPT to independently SELECT, from the compact portfolio JSON, which
ONE case is `najveci_rizik` (assigning it an invented `kriticnost: 0-100` score), which is `najveca_prilika`,
which is `zapostavljen_predmet`, which has the `neprimecena_kontradikcija`, which has the `kriticni_rok`,
which has a `suboptimalna_strategija`, which is a `slicni_predmet`, and to author ONE `cio_preporuka` naming
a specific case. **This is GPT deciding priority and risk, not explaining an already-decided priority** —
even though several of the underlying signals (deadline proximity, contradiction count) are already computed
deterministically in `_kompaktan_predmet` BEFORE the prompt, GPT is still the one that picks WHICH case
matters most and invents a severity number for it, per this sprint's own explicit Phase 5 rule ("GPT ne sme
menjati priority/risk").

**What should be deterministic, reusing existing mechanisms only (no new algorithm)**:
- `predmet_id` validity for every one of the 8 JSON blocks — `shared/genome_validator.py::validate_predmet_reference`,
  the SAME function `case_commander.py::_cross_case_analiza` already uses for exactly this check.
- `najveci_rizik.kriticnost` — should be capped against the SAME `predmet_id`'s own canonical readiness
  status, reusing the exact `_CAP_BY_READINESS`-shaped mechanism already proven 3 times (Court Predictor,
  Hearing CC) rather than trusting GPT's own invented number unconditionally.
- `kriticni_rok` — should be cross-checked against that predmet_id's own real canonical `deadlines`, not
  trusted as asserted; if no matching real deadline exists, the claim is a hallucination.

**What's confirmed already correct / out of scope for a deterministic check**: `najveca_prilika`,
`suboptimalna_strategija`, `slicni_predmet`, `cio_preporuka`'s own wording, and `cio_zakljucak` have no
canonical equivalent anywhere in the platform to check them against — these remain genuinely GPT-synthesized
narrative, same category as `case_commander.py`'s own `protivnikova_strategija`/`sudska_praksa` (Sigma 005's
own GPT Boundary Policy: advisory synthesis over already-grounded facts is in-bounds; inventing the facts
themselves is not).

## Verdict

`cio.py` is confirmed a genuinely parallel reasoning surface — its own portfolio_zdravlje statistics, its
own contradiction/gap counts, and its own deadline source are all independently derived from raw Genome
fields rather than the canonical `build_case_context()`/`gap_engine.py`/`case_readiness.py` chain every
other executive surface in this program has already migrated onto. This is not a hypothetical drift risk
(Tau 007's own framing for the risk_engine family) — it's an ACTIVE divergence today: a case's own CIO
report and its own canonical readiness can already disagree, since neither reads the other.

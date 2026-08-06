# Executive Consolidation — Program Tau, Master Sprint 008, Phase 3

Migrates `routers/cio.py` onto existing canonical sources. No new helper, builder, wrapper, or algorithm —
reuses `build_case_context()` (already proven for portfolio loops by `morning_briefing.py` and
`case_commander.py`'s own jutarnji digest) and `shared/genome_validator.py::validate_predmet_reference`
(already used by `case_commander.py::_cross_case_analiza` for the identical "did GPT reference a real
predmet_id" check).

## Forensic pre-check: CIO is live, unlike Sprint 007's own target

`grep -n "/api/cio/" static/vindex.js` confirms `_cioLoad()` calls `GET /api/cio/daily` / `POST /api/cio/run`
directly, wired into the dashboard's own `_cioLoad(hdr)` call in `dash_load()` — genuinely live, unlike
`case_commander.py` (Tau 007) which was confirmed fully dead. The exact response shape (`izvestaj.cio_preporuka`,
`izvestaj.najveci_rizik.{predmet_naziv,predmet_id,rizik,kriticnost}`,
`izvestaj.zapostavljen_predmet.{predmet_naziv,predmet_id,dana_bez_aktivnosti,rizik_zapustanja}`,
`izvestaj.kriticni_rok`, `izvestaj.portfolio_zdravlje.{ukupno_aktivnih,jakih,srednje,slabih,prosecna_snaga,
kriticnih_rizika}`) is directly rendered by `_cioRender()` — confirmed by reading that function, not
assumed. **Every field name and type is preserved exactly**; only WHERE each value's own data originates
changed.

## What changed

### `_kompaktan_predmet` — now built from canonical context, not raw `case_dna`

| Signal | Before | After |
|---|---|---|
| `snaga` | `case_dna.snaga_predmeta_procent` | `build_case_context()`'s own `key_facts.snaga_predmeta_procent` (same field, canonical wrapper) |
| `najslabija_tacka` | `case_dna.najslabija_tacka` | `key_facts.najslabija_tacka` (same field, canonical wrapper) |
| `rokovi_aktivni` | **`case_dna.rokovi_kriticni[]`** — Genome's own GPT-extracted deadline list, a 3rd deadline source never cross-checked against `rocista`/`rokovi` | Canonical `deadlines` (the real `rocista` table, filtered to `not proslo`, ≤60 days out) |
| `kontradikcije_kriticne` | `case_dna.kontradikcije` filtered directly (`tezina=="kriticna"`) | Canonical `contradictions` (`gap_engine.py`-normalized, `pouzdanost=="visoka"`) |
| `nedostaje_kriticno` | `case_dna.nedostaje` filtered directly (`hitnost=="kriticno"`) | Canonical `missing_evidence` (`gap_engine.py`-normalized, `pouzdanost=="visoka"`) — a deliberate widening, now also counting `identify_case_problems`-sourced high-confidence gaps, not only Genome-sourced ones, same "read the canonical field wholesale" precedent Tau 007 established for `case_commander.py`'s own `nedostaje` |
| `strategija_cilj`, `zakljucak` | `case_dna.strategija`/`case_dna.zakljucak` | **Unchanged** — canonical `key_facts` carries no `strategija`/`zakljucak` field; kept as a named Step-5 exception (`docs/tau/MIGRATION_TEMPLATE.md`), not a migration gap worked around silently |
| `genome_verzija` | `case_dna.verzija` | **Dropped** — never part of GPT's own required output schema, purely extra context; canonical `key_facts` carries no version number since that's an internal Genome implementation detail, not a case fact |

`_generiši_cio_izvestaj` now loops `build_case_context(p["id"], uid, supa, include_documents=False)` across
all fetched active cases (`asyncio.gather`, the same established portfolio-loop pattern `morning_briefing.py`
and `case_commander.py`'s own jutarnji digest already use) — fail-soft per case, a `build_case_context()`
failure for one case excludes only that case from the portfolio, same behavior as a case with no Genome model
had before.

### `portfolio_zdravlje.kriticnih_rizika` — redefined to the platform's own canonical definition of "critical"

Before: counted `najslabija_tacka.kriticnost >= 85` — Genome's own ad hoc 0-100 heuristic, unrelated to how
any other executive surface defines "critical." After: counts cases whose canonical `readiness.status` is
`CRITICAL_GAP`/`BLOCKED` — the SAME definition Workspace, Case Commander, Court Predictor, and Hearing CC
already use. Proven by an adversarial test with 2 cases whose Genome heuristic score and canonical readiness
DISAGREE (one canonically CRITICAL_GAP with a low Genome score, one canonically READY with a high Genome
score) — confirms only the canonically-critical case is counted.

### GPT Boundary enforcement — reusing existing validators only, applied after the GPT call

1. **`predmet_id` validity**: every one of the 7 predmet-referencing JSON blocks
   (`najveci_rizik`/`najveca_prilika`/`zapostavljen_predmet`/`neprimecena_kontradikcija`/`kriticni_rok`/
   `suboptimalna_strategija`/`slicni_predmet`) is checked via `shared/genome_validator.py::validate_predmet_reference`
   — the exact function `case_commander.py::_cross_case_analiza` already uses for this exact check, passed
   the full UUID (the function is generic over any string key against a known-set, despite its own
   docstring/error text being historically written for the 8-character-prefix convention). A block
   referencing a nonexistent `predmet_id` is nulled, not shown.
2. **`najveci_rizik.kriticnost` deterministic cap**: if the referenced case's own canonical readiness is
   `READY`, `kriticnost` is capped at 40 — reusing the exact `_CAP_BY_READINESS`-shaped mechanism already
   proven 3 times (Court Predictor, Hearing CC), applied in the opposite direction (capping a risk score DOWN
   for a good case, vs. capping a success score down for a bad one — same PATTERN, different score
   semantics).
3. **`kriticni_rok` cross-check**: the claimed date is checked against that predmet_id's own real,
   canonical `deadlines` list; if no match exists, the block is nulled — same "honest reporting, don't
   invent" discipline `court_predictor.py`'s own `koriscena_praksa` field already established.

### What stays genuinely GPT-synthesized, correctly not touched

`najveca_prilika`, `suboptimalna_strategija`, `slicni_predmet`, `cio_preporuka`'s own wording, and
`cio_zakljucak` have no canonical equivalent anywhere in the platform — these remain GPT's own narrative
synthesis over now-grounded facts, the same category as `case_commander.py`'s own
`protivnikova_strategija`/`sudska_praksa` (Sigma 005's own GPT Boundary Policy: synthesis over grounded
facts is in-bounds, inventing the facts themselves is not).

## Tests

18 new tests (`tests/test_tau008_cio_consolidation.py`): canonical field sourcing (including the deadline-
source switch, proven by constructing a case where the OLD Genome-embedded deadline and the NEW canonical
deadline disagree, and asserting only the canonical one survives), the `kriticnih_rizika` redefinition
(proven with 2 cases whose Genome heuristic and canonical readiness intentionally disagree), 3 adversarial
GPT-boundary proofs (hallucinated `predmet_id` nulled, `kriticnost` capped for a canonically-READY case,
fabricated `kriticni_rok` nulled), a positive control (a REAL `kriticni_rok` survives the cross-check),
fail-soft degradation, concurrency (2 different users' reports don't cross-contaminate), replay stability,
and a structural test confirming `_kompaktan_predmet`'s own source no longer references `case_dna`'s
`rokovi_kriticni`/`kontradikcije`/`nedostaje`/`snaga_predmeta_procent` fields directly.

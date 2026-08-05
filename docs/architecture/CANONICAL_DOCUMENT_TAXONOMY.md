# Canonical Document Taxonomy — Program Intake Sprint 003 (2026-08-05)

**Status: DESIGNED, NOT YET ADOPTED IN CODE.** This document is the taxonomy itself — the schema/classifier
rewiring needed to make it the platform's actual single source of truth is future work (§6). Full design
rationale: `.vindex_ai_team/decisions/2026-08-05_intake_sprint003_fork_taxonomy_confidence.md` (Fork B).

## 1. The taxonomy — 10 parent categories

| # | Canonical parent (`tip_dokaza` value) | Serbian label | Subtypes |
|---|---|---|---|
| 1 | `sudska_odluka` | Sudska odluka | `presuda`, `resenje`, `zakljucak`, `zapisnik_sa_rocista` |
| 2 | `podnesak` | Podnesak | `tuzba`, `odgovor_na_tuzbu`, `zalba`, `prigovor`, `zahtev`, `predlog`, `izvrsni_predlog` |
| 3 | `ugovor` | Ugovor | *(flat — no existing vocabulary or product need demanded a split)* |
| 4 | `punomocje` | Punomoćje | *(flat, promoted to top-level — §3)* |
| 5 | `dopis` | Dopis | `email`, `obavestenje`, `upozorenje`, `pravno_misljenje` |
| 6 | `medicinska_dokumentacija` | Medicinska dokumentacija | `nalaz`, `izvestaj_medicinski`, `otpusna_lista` |
| 7 | `finansijska_dokumentacija` | Finansijska dokumentacija | `faktura`, `izvod`, `priznanica`, `potvrda_o_placanju` |
| 8 | `javna_isprava` | Javna isprava | *(flat)* |
| 9 | `vestacki_nalaz` | Veštački nalaz | *(flat)* |
| 10 | `ostalo` | Ostalo | *(escape hatch, always available, never forced)* |

Design principles (mission charter, all four checked against every entry above): legal not technical; mutually
exclusive with an `Ostalo` escape hatch; usable as an actual classifier target (every category has a concrete
detectable signal, §4 of the Confidence Specification); reconciles all 4 existing vocabularies + the founder's
example (full mapping table below), not invented from scratch.

## 2. Full mapping from every existing vocabulary

### `routers/evidence.py` (the anchor — `EXPECTED_DOCS` is keyed to this vocabulary exactly)
Identical 1:1 for all 9 values (`sudska_odluka`, `podnesak`, `ugovor`, `dopis`, `medicinska_dokumentacija`,
`finansijska_dokumentacija`, `javna_isprava`, `vestacki_nalaz`, `ostalo`) — this vocabulary IS the anchor.

### `shared/intake_classify.py` (12+`other`, English)
`lawsuit→podnesak.tuzba` · `response→podnesak.odgovor_na_tuzbu` · `appeal→podnesak.zalba` ·
`judgment→sudska_odluka.presuda` · `contract→ugovor` · `invoice→finansijska_dokumentacija.faktura` ·
`power_of_attorney→punomocje` · `evidence→`**excluded** (§3.2) · `email→dopis.email` ·
`court_decision→sudska_odluka.resenje` · `enforcement→`**split**, see §3.6 ·
`legal_opinion→dopis.pravno_misljenje` (weakest mapping, §3.5) · `other→ostalo`.

### `routers/dokument.py::_klasifikuj_dokaz` (9-value, ephemeral)
`ugovor→ugovor` · `presuda→sudska_odluka.presuda` · `resenje→sudska_odluka.resenje` ·
`zapisnik→sudska_odluka.zapisnik_sa_rocista` (§3.7) · `izvestaj→`**context-dependent, no static mapping** (§3.8) ·
`priznanica→finansijska_dokumentacija.priznanica` · `dopis→dopis` · `punomocje→punomocje` · `ostalo→ostalo`.

### `api.py::_detect_doc_type` (3-value, ephemeral, prompt-routing only)
`presuda→sudska_odluka.presuda` · `ugovor→ugovor` · `opsti→ostalo`.

### Founder's example taxonomy
All 13 named items map cleanly except: Dokaz (**excluded**, §3.2), Fotografija/Audio/Video (**excluded**,
§3.3). `javna_isprava` — absent from the founder's list but kept (structurally required by `EXPECTED_DOCS`
across 4 of 9 case types; dropping it would silently break `services/risk_engine.py`'s missing-document
detector).

## 3. Edge-case decisions (explicit judgment calls, not hand-waved)

- **§3.1 `punomocje` promoted to top-level.** Absent from the anchor vocabulary entirely (a real gap — a
  punomoćje uploaded today silently falls into `ostalo`), but present as first-class in `intake_classify.py`
  AND the founder's own example. It's also structurally the easiest category to detect (fixed legal form:
  grantor, grantee, scope, notarization markers).
- **§3.2 "Dokaz"/`evidence` excluded entirely.** Collides with an already-existing, differently-scoped concept:
  `predmet_dokazi.kategorija` (migration 016) is a per-*claim* evidentiary-ROLE classification, not a
  document-TYPE. Almost any document can function as evidence — that's not a type, it's a role already
  captured correctly elsewhere. Recreating "Dokaz" here would reintroduce the exact "same word, two
  incompatible vocabularies" collision this taxonomy exists to eliminate.
- **§3.3 Fotografija/Audio/Video excluded**, recommended as a separate deterministic `file_kind` field (MIME/
  extension-derived, zero LLM guessing needed) — a technical fact, not a legal one, analogous to how
  `ocr_used` is already handled as metadata rather than a taxonomy value. Not implemented this sprint.
- **§3.5 `legal_opinion→dopis.pravno_misljenje`** — the weakest mapping in the table, explicitly flagged as
  such. Revisit trigger: promote to its own category once `intake_processing_outcomes` volume shows this
  shape arriving often enough to matter (measurable, not guessed).
- **§3.6 `enforcement` — a genuine pre-existing defect in the source vocabulary, not an artifact of
  reconciling it.** `intake_classify.py`'s own keyword list conflates a party-submitted enforcement petition
  with a court-issued enforcement order under one label. Canonical taxonomy splits by which keyword matched:
  court-issued → `sudska_odluka.resenje`; party-submitted → `podnesak.izvrsni_predlog`. A genuine improvement,
  not a compromise.
- **§3.7 `zapisnik`** (hearing record) → `sudska_odluka.zapisnik_sa_rocista` — produced by the court, filed
  alongside decisions, shares the same detectable structural signal (court letterhead, case-number header).
- **§3.8 `izvestaj`** ("report") has **no static mapping** — genuinely ambiguous across `medicinska_
  dokumentacija`/`finansijska_dokumentacija`/`vestacki_nalaz` depending on content. Design constraint on the
  classifier itself: a bare "izveštaj" keyword hit alone must never be sufficient for auto-accept.
- **Worked example (§1.3 of Fork B): sudsko poravnanje** (court-approved settlement). A naive keyword
  classifier routes toward `ugovor` (settlements are agreements). Under Serbian civil procedure a
  court-recorded settlement has the same enforceable force as a judgment — canonical routing is
  `sudska_odluka`, driven by structural court-issuance markers taking priority over the generic `ugovor`
  keyword when both fire.

## 4. `EXPECTED_DOCS` stays a separate cross-cutting dimension

**Recommendation, not implemented**: keep `shared/constants.py::EXPECTED_DOCS` (case_type → list of expected
canonical parent categories) fully separate from the document taxonomy itself. Different axis (per-document
type vs. per-case-type expected set), different cardinality (folding case-type-awareness into the taxonomy
would multiply its size by 9 case types for zero classification benefit — a `ugovor` looks the same textually
regardless of which case it ends up filed under). `EXPECTED_DOCS` only ever needs parent-level granularity
(confirmed: `services/risk_engine.py`'s consumption is exact-string-match at the parent level only).
`punomocje` deliberately excluded from every `EXPECTED_DOCS` case-type list — whether a punomoćje is expected
depends on whether the client used a legal representative, orthogonal to case type; folding it in would
produce a false "missing document" flag for every self-represented client.

## 5. What this taxonomy is NOT (scope boundary)

- Not a database migration — the required CHECK constraint widening (migration 074's 13 English values →
  this Serbian set) is a design note with a ready mapping table (§2), not written SQL, per this repo's
  standing rule that migrations are drafted by whoever actually implements the change, not speculatively.
- Not a rewrite of any classifier — no classifier's code was touched by this taxonomy design.
- Not a decision about Genome/Decision Engine/Copilot's own document-facing surfaces — explicitly forbidden
  modules this sprint, not designed for.

## 6. Adoption path (future work, not this sprint)

1. Widen migration 074's CHECK constraint on `intake_documents.document_type` to the canonical Serbian set
   (mapping table in §2 ready to hand off).
2. Rewire `shared/intake_classify.py`'s heuristic keyword lists to the canonical vocabulary (word lists are
   directly derivable from `evidence.py`'s own prompt docstring — no new legal research needed).
3. Retire `routers/evidence.py::_klasifikuj_dokument` as a SEPARATE classifier once `intake_classify.py`
   itself produces the canonical vocabulary — this is the actual fix for `ALPHA-003`'s classifier race (one
   classifier, not two racing).
4. Decide the fate of the 2 ephemeral classifiers (`api.py::_detect_doc_type`, `routers/dokument.py::
   _klasifikuj_dokaz`) — cost/maintenance duplication, not a correctness bug, lower priority.

# Timeline Registry — Program Sigma, Master Sprint 002 (2026-08-06)

Phase 1 deliverable: repo-wide inventory of every timeline/chronology/history writer and reader, classified
CANONICAL/PROJECTION/LEGACY/DEAD, with a direct answer to whether a timeline event can be modified/closed/
voided today. Every claim below cites a file:line actually read this sprint (forensic fork investigation).

## Writers of `predmet_hronologija` — 15 confirmed insert sites

`api.py:4661`, `api.py:5353`, `routers/case_dna.py:623`, `routers/copilot.py:565`, `routers/intake.py:210,343,808`,
`routers/onboarding.py:246`, `routers/predmeti_close.py:181`, `routers/rocista.py:314`,
`routers/rokovi_lanac.py:436`, `routers/smart_intake.py:1148`, `routers/ugovor_zastupanja.py:336`,
`services/case_evolution.py:205`, `services/case_pipeline.py:332`.

**Not a duplication.** All 15 write the identical schema
(`predmet_id, user_id, dogadjaj, datum, datum_iso, vaznost, akter`), but each is **CANONICAL for its own
distinct business event** (a hearing follow-up, a Genome-synced deadline, a Copilot-extracted deadline, a
contract-signing event, a case-closure event, etc.) — this is 15 different facts sharing one table and
schema, not 15 competing implementations of the same concept. No duplicate/competing chronology-assembly
algorithm was found among them.

**Zero UPDATE, zero DELETE call sites against this table anywhere in the repo** (confirmed by targeted
regex, not absence-of-grep-hit). `predmet_hronologija` is strictly append-only by construction — no
revision, supersede, or void concept exists in the schema or in any code path.

**Direct answer to the mission's own Phase 3 question ("can a later document modify/close/void a prior
timeline event?"): No.** A later document can only ADD a new row; it cannot reference, modify, or retract
an earlier one. See `CANONICAL_FACT_ENGINE.md` for why this is a real, named gap rather than a defect this
sprint tried to rush a fix for.

## A previously-uncatalogued architectural finding: one table, two semantics

`services/case_evolution.py::_consequence_timeline_entry` (the ONE Case-Evolution-owned writer, triggered
via `handle_case_changed`) never sets `datum`/`datum_iso` — it writes a pure narrative "what happened" log
entry. Every OTHER writer sets `datum_iso` — they write deadline/dated-event entries. Same table, same
schema, two different semantics, distinguished only by whether `datum_iso` happens to be null. Not fixed
this sprint (a schema split is a real migration, out of a certification-plus-targeted-fix sprint's own
scope) — named as `SIGMA-005` in the Debt Register.

## No source-document linkage

None of the 15 writers include a `dokument_id`/`source_document_id` field — no timeline entry can be traced
back to the specific document that produced it. `akter` is a free-text provenance label
(e.g. `"Genome (AI)"`, `"Advokat"`), not a foreign key. Relevant to Phase 4 — see
`EVIDENCE_GRAPH_SPECIFICATION.md`'s own finding (c): no FK from evidence to timeline point either.

## Projections (read-only, confirmed via zero `.insert`/`.update`/`.delete` in each file)

- **`routers/intelligence_timeline.py`** — the actual canonical "life of the case" aggregator, explicitly
  documented in its own module docstring (Core Consolidation Sec 1.6, 2026-07-22) as a deliberate pure
  query-layer merge, not a new table. Aggregates 6 sources: `predmeti`, `predmet_dokumenti`, `rocista`,
  `predmet_hronologija`, `predmet_genome_history`, `audit_immutable` — explicitly chosen NOT to merge
  `predmet_hronologija` and `audit_immutable` into one table since one is tamper-evident and the other
  isn't. This is the mission's own "jedinstvena vremenska linija predmeta" (unified case timeline)
  requirement, already built.
- **`routers/dashboard.py`** — presentational summary card over `predmet_hronologija`.
- **`routers/knowledge_graph.py`** — a DIFFERENT concept than Phase 4's evidence graph: a case-relationship
  graph (Predmet↔Klijenti↔Zakoni↔Presude↔Dokumenti↔Rokovi), not an evidence-to-claim-to-timeline graph.
- ~25 other confirmed read-only sites (billing_reports, copilot, matter_intel, notifications, export,
  search, etc.).

## A previously-unappreciated asset: `predmet_genome_history` already IS an audit trail

`predmet_genome_history` (`routers/case_dna.py:461-476` writer, `:976` and
`routers/intelligence_timeline.py:154` readers) already persists the FULL prior Genome object — including
its own `kontradikcije` list — with a `verzija` number and `trigger_event`, immediately before every
overwrite. Confirmed append-only (no UPDATE/DELETE against this table anywhere). **The raw historical
record of every Genome state this case has ever had is never lost.** This materially narrows Phase 5's own
scope: the actual gap was never "Genome forgets history" — the history is already fully preserved — it was
specifically that the identity-matching logic couldn't reliably recognize "this is the SAME contradiction as
last time" across versions. See `CONTRADICTION_ENGINE_SPECIFICATION.md` for the fix.

## Dead / legacy

None found. `routers/case_pipeline.py` (the HTTP wrapper, registered at `api.py:594,691`) is the live
entrypoint to the already-known canonical `services/case_pipeline.py::run_case_pipeline` — not a duplicate.

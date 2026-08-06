# Evidence Graph Specification — Program Sigma, Master Sprint 002 (2026-08-06)

Phase 4 deliverable: for a `predmet_dokazi` (evidence) row, verify each required linkage exists, is
derivable, or is missing, with file:line citations.

## Schema

`predmet_dokazi` (`migrations/016_evidence_vault.sql:23-35`, extended by
`migrations/080_predmet_dokazi_grounding.sql`): `id, predmet_id, dokument_id (FK), user_id, tvrdnja (claim
text), kategorija (cinjenica|dokaz|svedok|vestacenje|pravni_osnov|ostalo), snaga, pravni_element, napomena,
deleted_at, stranica, paragraf, start_offset, end_offset`.

## The 4 required linkages

| # | Linkage | Status | Detail |
|---|---|---|---|
| (a) | Which document it came from | **EXISTS** | `dokument_id` column, populated at insert (`routers/evidence.py:246`) |
| (b) | Which claim/argument it supports | **EXISTS, conditionally** | A full, already-built graph schema (`migrations/076_legal_reasoning_engine.sql`: `reasoning_nodes` Fact/LegalElement/Norm/Claim, `reasoning_edges` supports/satisfies/creates, `reasoning_evidence` linking a Fact node to its `dokaz_id`/`dokument_id`) is populated by `services/legal_reasoning_engine.py::generate_reasoning_graph` (line 258+), reading facts from `predmet_dokazi` (`_fetch_facts`, lines 90-106) and writing a `reasoning_evidence` row per Fact node (lines 344-347). **This is a real, working Evidence Graph — but it is on-demand only** (`POST /{predmet_id}/reasoning-graph/generate`, `routers/legal_reasoning.py:31`), never auto-triggered by Case Evolution. Outside a generated reasoning graph, "supports" is only derivable via `predmet_dokazi.tvrdnja`/`pravni_element` free text |
| (c) | Which fact/timeline point it belongs to | **MISSING** | No FK from `predmet_dokazi` (or `reasoning_nodes`) to `predmet_hronologija`. No table anywhere links an evidence item to a specific timeline event |
| (d) | Which document disputes/contradicts it | **MISSING at the per-evidence level** | Contradictions live only at the whole-case Genome level (`case_dna.kontradikcije`, free text with `lokacija_1`/`lokacija_2` string citations, not FKs) — no column on `predmet_dokazi` or `reasoning_nodes` records "this specific evidence item is contested by document Y" |

## Why (b) is conditional, not fully "EXISTS"

The Legal Reasoning Engine (migration 076) is a complete, tested, working evidence-to-claim graph — but it
requires an explicit, separate API call to populate, and is never wired into the automatic
Upload→Assimilation→Genome/Timeline/Tasks chain (`DOCUMENT_ACCEPTED`/`DOCUMENT_BATCH_COMPLETED`) this whole
engagement has otherwise made fully autonomous. Confirmed via grep: only `routers/legal_reasoning.py` and
`evaluation/phase_0_5/run.py` reference `reasoning_*` tables — Case Evolution never touches them. A case
built entirely through Smart Intake, exactly as thoroughly as the mission's own primary scenario describes,
would have ZERO reasoning-graph rows unless a lawyer separately, manually requests one.

**Why not auto-wired this sprint**: `generate_reasoning_graph` is a substantial GPT-driven operation (its
own dedicated on-demand endpoint, presumably with real latency/cost), and auto-firing it on every document
acceptance would be a genuine new automatic AI-cost/latency commitment per document — a product decision
about cost/value tradeoff, not a mechanical wiring fix like `PREDMET_KREIRAN` was in Master Sprint 001.
Recorded as `SIGMA-006`.

## (c) and (d): the real gaps, and why they're not fixed by connecting existing code

Unlike (b), no existing mechanism already computes (c) or (d) even on-demand — these require NEW linkage
concepts (evidence↔timeline FK; per-evidence contradiction flag) that don't exist anywhere in the current
schema. Building them properly means:
- (c): either a new nullable FK column on `predmet_dokazi` pointing at `predmet_hronologija` (requires
  `predmet_hronologija` to have a stable, referenceable identity per row — it does, via its own `id`
  primary key, so this is schema-feasible), populated at evidence-classification time by matching the
  evidence's own extracted date/context against nearby timeline entries — a real extraction/matching
  algorithm, not a trivial column add.
- (d): a `contested_by_dokument_id`/similar column, populated by wiring per-evidence contradiction detection
  into `klasifikuj_i_sacuvaj` (`routers/evidence.py:256`) — currently this function performs whole-document
  classification, not cross-document contradiction comparison at the evidence-item level (that comparison
  currently only happens at the whole-Genome level).

**Why not fixed this sprint**: both require new extraction/matching logic (not GPT prompt changes, but real
new deterministic-or-AI-assisted linking algorithms), squarely the kind of "new functionality" the mission's
own founding principle requires to reuse canonical mechanisms for — and no existing canonical mechanism
currently performs evidence-to-timeline or evidence-to-evidence contradiction linking to reuse. Building
one blind, at the tail of an already-large sprint, risks exactly the "parallel algorithm" outcome the
mission explicitly forbids. Recorded as `SIGMA-007` (evidence↔timeline linkage) and `SIGMA-008`
(per-evidence contradiction linkage) — both scoped as real, valuable future work with a clear design
starting point (this document), not vague TODOs.

## Fact ownership (Phase 2) — merge/dedup logic per fact type

| Fact type | Merge/dedup logic | Citation |
|---|---|---|
| Client/party | Never auto-merges — 2+ name matches → `ambiguous`, surfaced not resolved | `shared/case_assimilation.py::resolve_client_ownership` (Sprint 001, re-confirmed unchanged) |
| Case | Never auto-merges — 2+ case-number matches → `review_required` | `resolve_case_ownership`, same file |
| Evidence (`predmet_dokazi`) | **No merge logic at all — blind `insert(rows)`, no SELECT-before-insert** | `routers/evidence.py:256` |
| "Witness" (`svedok`) | **Not a distinct entity** — `svedok` is only a `kategorija` value on `predmet_dokazi`, no separate identity/table; the same witness named in 2 documents produces 2 unrelated rows with no linkage attempt at all | `migrations/016_evidence_vault.sql:29` |
| Timeline events | No dedup of any kind (established, `TIMELINE_REGISTRY.md`) | — |

The evidence blind-insert pattern is NOT directly exposed to "same document processed twice," because it's
gated upstream by Smart Intake's own `content_sha256` document-level idempotency check (same content in the
same case → no-op, `klasifikuj_i_sacuvaj` never runs a second time) — an indirect/derived protection, not a
guarantee `predmet_dokazi` itself enforces. Recorded alongside `SIGMA-004` (Sprint 001) as the same TOCTOU
class, extended to this table — see `TIMELINE_FORENSIC_REPORT.md`.

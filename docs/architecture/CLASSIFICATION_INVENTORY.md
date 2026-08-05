# Classification Inventory — Program Intake Sprint 003 (2026-08-05)

Phase 1 requirement: map every place the platform classifies a document, guesses its type, or uses GPT/
heuristics/regex/metadata/filename to do so. Full evidence: `.vindex_ai_team/decisions/
2026-08-05_intake_sprint003_fork_classification_inventory_duplicates.md` (Fork A).

## Complete inventory — 5 independent AI classifiers, not 4 as previously tracked

| # | Site | Taxonomy | Persists to | Reachable live | Decided by |
|---|---|---|---|---|---|
| 1 | `shared/intake_classify.py::classify()` | English, 13-type | `intake_documents.document_type` | Yes (Pipeline B/C) | AI (heuristic-first, LLM fallback) |
| 2 | `routers/evidence.py::_klasifikuj_dokument` | Serbian, 9-type | `predmet_dokumenti.tip_dokaza` | Yes (Pipeline A + B/C, fire-and-forget) | AI |
| 3 | `api.py::_detect_doc_type` | 3-way keyword heuristic | Nothing (ephemeral, prompt-routing only) | Yes (Pipeline A, every upload) | Heuristic, not LLM |
| 4 | `routers/dokument.py::_klasifikuj_dokaz` | 9-type, 4th vocabulary | Nothing (ephemeral, session Q&A) | Yes (`/api/dokument/klasifikuj-sesija`) | AI |
| 5 | **`api.py::_call_metapodaci`** (new finding this sprint) | 8-type, 5th vocabulary | `predmet_istorija.odgovor` (JSON blob) + API response `"metadata"` key | Yes (Pipeline A, same request as #2/#3) | AI |

**Finding #5 is genuinely new** — not previously counted by any prior fork because it never touches
`predmet_dokumenti.tip_dokaza`, the field every earlier classifier census was scoped around. `gpt-4o-mini`,
`temperature=0`, runs inside Pipeline A's own upload request in the same `asyncio.gather` as the procena/
hronologija calls. **A single upload through Pipeline A now triggers 3 independent "what type is this"
decisions in one request-response cycle** (classifiers #2, #3, #5), not 2.

## A 6th vocabulary — genuinely a different object, not a competing classifier

`klijenti/router.py::upload_klijent_dokument` has its own 9-value, **100% human-decided** `tip_dokumenta`
field (a required Pydantic parameter, no AI call). Persists to `klijent_dokumenti.tip_dokumenta` — a client
vault document (ID card, contract copy), not a case-file document. Correctly not counted as a competing
classifier for `predmet_dokumenti.tip_dokaza`. Noteworthy overlap: the same physical file could be uploaded
once into Klijenti Trezor (human-typed type) and separately into a case (AI-classified type) with zero
reconciliation code anywhere.

## Intersects a forbidden module — noted, not deep-dived

`strategija.py`'s F10 orchestrator asks GPT-4o for a free-text `"tip_dokumenta"` description as part of a
larger document-review analysis — not a controlled taxonomy, never persisted structurally. Strategy Engine is
forbidden to deep-dive this sprint; noted for completeness only.

## Confirmed clean — no document-type decision logic

`shared/genome_validator.py` and `routers/case_commander.py` — grepped for every search term this sprint's
inventory used, zero matches in either file.

## Downstream consumers — read only, do not independently decide a type

| Site | What it does |
|---|---|
| `services/risk_engine.py` | Set-membership check against `EXPECTED_DOCS` for missing-document detection |
| `routers/matter_intel.py` | Same `EXPECTED_DOCS` matching |
| `routers/ccc.py` | Same pattern, "nedostajući dokazi" panel |
| `routers/case_dna.py` (Genome — forbidden module, noted only) | Formats `tip` into a Genome prompt-context string |
| `routers/evidence_graph.py` | Reads `tip_dokaza` for graph node labeling |
| `services/case_pipeline.py` | Feeds `tip_dokaza` into `risk_engine.calculate_procesni_rizik` |
| `routers/drafting.py:327` | **Writes**, but deterministically (`"podnesak"`, no AI call — the Sprint 001 fix) — not a competing classifier |

`shared/constants.py::EXPECTED_DOCS` exclusively uses `evidence.py`'s 9-type vocabulary — confirming it, not
`intake_classify.py`'s, is the de facto canonical one every real consumer depends on, even though nothing in
the code enforces it wins the classifier race.

## Human-override paths — audited precisely; one is not what it appears

- **Smart Intake's `/entities/{id}/correct`** — genuinely human-typed, but `document_type` is structurally
  **not** a correctable entity (`ENTITY_TYPES` is 8 fields: case_number, judge, plaintiff, defendant, court,
  deadline, amount, law_cited — confirmed against the frontend's own identical label map).
- **Evidence Vault's `/reklasifikuj`** — **not a human override.** Despite its name, it takes no lawyer-
  supplied type value; it re-fetches the document text and fires the same AI classifier again via another
  unawaited `asyncio.create_task`, returning immediately with "reclassification started in background."
  Human-*triggered* AI re-classification, not human classification.

**Net finding: there is no path anywhere in the codebase for a lawyer to directly set/type
`predmet_dokumenti.tip_dokaza` to a value of their choosing.** The only genuinely human-decided document-type
field anywhere in the platform is Klijenti Trezor's `tip_dokumenta` — a different table, a different object.

## Summary

5 independent AI classifiers (not 4), 1 genuinely-separate human-decided vocabulary for a different object,
1 forbidden-module intersection noted only, 7 confirmed read-only consumers, 1 deterministic non-AI writer,
zero human-override path for the case-document field itself. Full detail, all file:line citations:
`.vindex_ai_team/decisions/2026-08-05_intake_sprint003_fork_classification_inventory_duplicates.md`.

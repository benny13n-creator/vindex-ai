# Fork A — Program Intake Sprint 003: Classification Inventory (Phase 1) + Duplicate Detection Audit (Phase 6)

**Lens**: Chief Systems Architect + Code Quality/Refactoring Reviewer. **Mode**: read-only, no code changes.
**Prior art read in full before investigating** (not re-derived): `docs/architecture/INTAKE_ARCHITECTURE_REPORT.md`,
`INTAKE_DUPLICATE_LOGIC_REGISTER.md`, `ARCHITECTURAL_DEBT_REGISTER.md` (`ALPHA-003`/`ALPHA-004`),
`.vindex_ai_team/decisions/2026-08-04_intake_fork_upload_ocr_classification_FORENSICS.md`. That prior fork's
Finding 4 (four classifiers) and Finding 3 (the classifier race) are the baseline this report extends, not
repeats. Forbidden/standby modules this sprint (Genome, Decision Engine, Copilot, Search, Firm Brain, Timeline,
Deadlines, Tasks, Alerts, Briefing) are noted only where a traced path touches them — not investigated.

---

## Phase 1 — Complete classification inventory

### 1.1 The 4 already-known classifiers — re-confirmed unchanged, not re-derived

| Classifier | File:line | Vocabulary | Persists to | Live/reachable |
|---|---|---|---|---|
| `shared/intake_classify.py::classify()` | `intake_classify.py:125-133` | English, 13-type (`DOCUMENT_TYPES`, line 32-36), CHECK-constrained (migration 074:44) | `intake_documents.document_type` | Yes — Pipeline B worker |
| `routers/evidence.py::_klasifikuj_dokument` | `evidence.py:73-93` | Serbian, 9-type (line 42-51) | `predmet_dokumenti.tip_dokaza` (no CHECK constraint — migration 016:6 is plain `TEXT`) | Yes — fired from both Pipeline A and B/C |
| `api.py::_detect_doc_type` | `api.py:3539-3541`, called `api.py:4191` | 3-way keyword heuristic (`presuda`/`ugovor`/`opsti`) | Nothing — ephemeral prompt-routing var only | Yes — Pipeline A, every upload |
| `routers/dokument.py::_klasifikuj_dokaz` | `dokument.py:84-118` | 4th taxonomy, 9-type (`ugovor\|presuda\|resenje\|zapisnik\|izvestaj\|priznanica\|dopis\|punomocje\|ostalo`, line 95) | Nothing — ephemeral session Q&A only | Yes — `/api/dokument/klasifikuj-sesija` |

### 1.2 NEW classifier found this sprint — a 5th independent AI document-type decision, not previously counted

**`api.py::_call_metapodaci`** (`api.py:4514-4535`, invoked inside `predmet_upload_auto_analyze`, Pipeline A's
own endpoint) runs a **fifth, independent GPT call** that decides `tip_dokumenta` with an **8-value taxonomy
distinct from all 4 known ones**: `tuzba|ugovor|zalba|presuda|resenje|izjava|punomoćje|ostalo`
(`_META_SYSTEM`, `api.py:4514-4524`). Model `gpt-4o-mini`, `temperature=0` (`api.py:4529`), runs in the same
`asyncio.gather` as `_call_procena` and `_call_hronologija` (`api.py:4549-4554`), inside the **same request**
that also runs `_detect_doc_type` (heuristic, §1.1) and fires the async `evidence.py::klasifikuj_i_sacuvaj`
(§1.1) for the identical uploaded file. **This means a single upload through Pipeline A triggers three
independent "what type of document is this" decisions in one request-response cycle**, not two.

- **Persists**: yes, but not to `predmet_dokumenti.tip_dokaza`. The parsed `metapodaci` dict (including
  `tip_dokumenta`) is inserted into `predmet_istorija` as a JSON blob tagged `"[Metapodaci] {filename}"`
  (`api.py:4649-4655`, `confidence: "HIGH"`) and returned to the caller in the JSON response under the
  `"metadata"` key (`api.py:4726`).
- **Reachable live**: confirmed — `predmet_upload_auto_analyze` is `POST /api/predmeti/{id}/upload`, the
  already-confirmed-live Pipeline A entry point from Sprint 001's report §1.
- **Why this wasn't caught before**: prior forks' classifier counts were scoped to writers of
  `predmet_dokumenti.tip_dokaza` specifically (the race-relevant field). This one never touches that column,
  so it's invisible to a `tip_dokaza`-scoped grep — but it is a real 5th AI-answered "what type is this"
  decision, visible to the lawyer in `predmet_istorija` (case timeline/history) and in the upload response,
  under yet a different vocabulary. **Net correction to prior art**: 5 independent AI document-classification
  call sites exist, not 4; 3 of the 5 (`_klasifikuj_dokument`, `intake_classify.classify`, `_call_metapodaci`)
  ever persist a value anywhere queryable later, not 2.

### 1.3 A distinct, correctly-out-of-scope object with its own taxonomy — Klijenti Trezor

**`klijenti/router.py::upload_klijent_dokument`** (`klijenti/router.py:706-803`) has its own `tip_dokumenta`
field, Pydantic-validated against a **9th, still-different fixed set**:
`{"lk","pasos","ugovor","presuda","resenje","punomocje","ostalo","medicina","finansije"}`
(`klijenti/router.py:697-703`). This is **100% human-decided** — a required request parameter
(`Field(..., max_length=30)`), no AI call anywhere in this function. It persists to a **different table**,
`klijent_dokumenti.tip_dokumenta` (`klijenti/router.py:781`), which is a client-record vault document (ID
card, client-side contract copy), not a case-file document — genuinely a different object than
`predmet_dokumenti`, so this is **not a competing classifier for the same field**. Confirmed live and
frontend-wired: `GET /klijenti/{id}/dokumenti` is called from `static/vindex.js:4784` and rendered at
`vindex.js:4791`. **Noteworthy overlap, not a bug**: `DokumentUploadReq.predmet_id` (`klijenti/router.py:695`)
optionally links a Trezor document to a case — meaning the same physical file could plausibly be uploaded
once into Klijenti Trezor (human-typed type) and separately into a case via Pipeline A/B (AI-classified type),
with `predmet_id` the only thread connecting them and zero reconciliation code anywhere (see Phase 6b).

### 1.4 Intersects a forbidden module, not deep-dived — Strategy Engine's free-text "tip_dokumenta"

`strategija.py`'s F10 orchestrator (`_ORK_REVIZOR_SYSTEM`/`_ORK_DUE_DILIGENCE_SYSTEM`, `strategija.py:457-504`)
asks GPT-4o to return a **free-text** `"tip_dokumenta": "opis tipa i svrhe dokumenta"` field as part of a
larger document-review analysis — not a controlled taxonomy/enum, never persisted to `predmet_dokumenti` or
any structured column (read-verified: only appears inside the JSON schema description strings, `strategija.py:
469, 495`). This is Strategy Engine, adjacent to the sprint's forbidden Decision Engine boundary — noted for
completeness because it independently answers the same underlying question, not investigated further.

### 1.5 False positive, ruled out — corrections.py classifies corrections, not documents

`routers/corrections.py::_klasifikuj_korekciju_async` (`corrections.py:190-215`) classifies the **type of edit
a lawyer made to AI-generated text** (`tip_korekcije`) — semantically unrelated to document-type
classification despite matching the `klasifik` grep. Excluded from the inventory.

### 1.6 Confirmed clean — no document-type decision logic found

`shared/genome_validator.py` and `routers/case_commander.py` — grepped for every search term in this sprint's
list (`tip_dokaza`, `document_type`, `doc_type`, `klasifik`, `vrsta_dokumenta`, `tip_dokumenta`,
`dokument_tip`), **zero matches in either file**. Neither participates in document classification in any way.

### 1.7 Downstream consumers — read a classification someone else made, do NOT independently decide one

Confirmed by direct read, not merely by grep hit, that each of these only **reads** `tip_dokaza`/
`EXPECTED_DOCS` and never writes/decides a type:

| Site | File:line | What it does with the value |
|---|---|---|
| `services/risk_engine.py` | `risk_engine.py:64` | `postojeci_tipovi = {d.get("tip_dokaza") ...}` — set-membership check against `EXPECTED_DOCS` for missing-document detection |
| `routers/matter_intel.py` | `matter_intel.py:297,321-322` | Same `EXPECTED_DOCS` matching, re-exposed via Matter Intel's own missing-docs view |
| `routers/ccc.py` | `ccc.py:75,123,137` | Same pattern, Case Command Center's "nedostajući dokazi" panel |
| `routers/case_dna.py` (Genome) | `case_dna.py:253,1054` | Formats `tip` into a Genome prompt-context string; **Genome itself is forbidden this sprint, noted only** |
| `routers/evidence_graph.py` | `evidence_graph.py:80,210` | Reads `tip_dokaza` for evidence-graph node labeling |
| `services/case_pipeline.py` | `case_pipeline.py:534,598` | Selects `tip_dokaza`, feeds it into `risk_engine.calculate_procesni_rizik` (Case Pipeline touches Decision-Engine-adjacent territory — not deep-dived) |
| `routers/drafting.py` (writer, not reader) | `drafting.py:327` | **This one writes**, but deterministically (`"tip_dokaza": "podnesak"`, no AI call) — the Sprint 001 fix, re-confirmed present; not a competing classifier, a fixed constant |

`shared/constants.py::EXPECTED_DOCS` (`constants.py:10-20`) exclusively uses `evidence.py`'s 9-type Serbian
vocabulary in all 9 case-type lists — confirming `evidence.py`'s taxonomy, not `intake_classify.py`'s, is the
de facto canonical one every consumer actually depends on, even though nothing enforces it wins the race
(§Phase 6a).

### 1.8 Human-override paths — audited precisely, one is not what it appears

The task brief named two candidate "human decides" paths. Direct code reading shows **only one of the two
actually lets a human type a value; the other only re-triggers AI**:

- **Smart Intake's `/entities/{entity_id}/correct`** (`smart_intake.py:267-297`) — genuinely a human-typed
  override, but **does not cover document type at all**. `ENTITY_TYPES` (`shared/intake_extract.py:36-37`) is
  `case_number, judge, plaintiff, defendant, court, deadline, amount, law_cited` — 8 fields, confirmed via the
  frontend's own label map `_SI_ENTITY_LABELS` (`static/vindex.js:20939-20942`), which mirrors this exact
  list. **`document_type` is structurally not a correctable entity** anywhere in this mechanism.
- **Evidence Vault's `/reklasifikuj`** (`evidence.py:375-408`) — **not a human override either.** Reading the
  full function: it takes no lawyer-supplied type value at all; it re-fetches the document text and fires
  `klasifikuj_i_sacuvaj` — the exact same AI classifier — again, via another unawaited
  `asyncio.create_task` (`evidence.py:401-406`), returning `{"ok": true, "poruka": "Reklasifikacija pokrenuta
  u pozadini."}` before the new classification has even run. **It is "human-triggered AI re-classification,"
  not "human classification."**

**Net finding: there is no path anywhere in the codebase for a lawyer to directly set/type
`predmet_dokumenti.tip_dokaza` to a value of their choosing.** The only document-type field with a genuine
human-decided value anywhere in the platform is Klijenti Trezor's `tip_dokumenta` (§1.3) — a different table,
a different object, not the case-document classification this sprint (and `ALPHA-003`) is about.

### 1.9 Complete Phase 1 table

| # | Classifier/decision-site | Taxonomy | Persists to | Reachable live today | Decided by |
|---|---|---|---|---|---|
| 1 | `shared/intake_classify.py::classify()` | English, 13-type | `intake_documents.document_type` | Yes (Pipeline B/C, confirmed Sprint 001) | AI (heuristic-first, LLM fallback) |
| 2 | `routers/evidence.py::_klasifikuj_dokument` | Serbian, 9-type | `predmet_dokumenti.tip_dokaza` | Yes (Pipeline A + B/C, fire-and-forget) | AI |
| 3 | `api.py::_detect_doc_type` | 3-way keyword heuristic | Nothing (ephemeral) | Yes (Pipeline A, every upload) | AI-adjacent heuristic, not LLM |
| 4 | `routers/dokument.py::_klasifikuj_dokaz` | 9-type, 4th vocabulary | Nothing (ephemeral, session Q&A) | Yes (`/api/dokument/klasifikuj-sesija`) | AI |
| 5 | **`api.py::_call_metapodaci`** (NEW) | 8-type, 5th vocabulary | `predmet_istorija.odgovor` (JSON blob) + API response `"metadata"` key | Yes (Pipeline A, same request as #2/#3) | AI |
| 6 | `klijenti/router.py::upload_klijent_dokument` | 9-value fixed set, 6th vocabulary | `klijent_dokumenti.tip_dokumenta` (different table/object) | Yes | **Human** (required param, no AI) |
| 7 | `strategija.py` F10 orchestrator | Free-text description, not an enum | Nowhere structured (Strategy Engine output only) | Yes, but Strategy Engine is forbidden-to-deep-dive this sprint | AI |
| — | `routers/drafting.py:327` | N/A — hardcoded constant `"podnesak"` | `predmet_dokumenti.tip_dokaza` | Yes | Deterministic code, not a classifier |
| — | Smart Intake `/entities/{id}/correct` | N/A | `intake_entities.corrected_value` | Yes | Human, but document_type is out of its field scope entirely |
| — | Evidence Vault `/reklasifikuj` | Re-runs #2 | Re-runs #2's write | Yes | **Not human** — human-*triggered*, AI-*decided* |

---

## Phase 6 — Duplicate/contradiction detection audit

### 6(a) — The classifier race: precisely distinguished from a worse bug it is NOT

`predmet_dokumenti.tip_dokaza` is a plain `TEXT` column with **no CHECK constraint**
(`migrations/016_evidence_vault.sql:6`) — confirmed via direct migration read, extending prior art's citation
of this fact to the schema level myself. Postgres single-row `UPDATE`s are atomic, so at any instant there is
exactly **one** value in that column for a given row — the already-known race
(`shared/intake_worker.py:173` → `smart_intake.py:676` → `smart_intake.py:725-735` →
`evidence.py:210-215`, all re-confirmed present and unchanged at these lines) makes that **final** value
**non-deterministic** (English- or Serbian-vocabulary, depending on which write lands last), but it does
**NOT** produce two contradictory values *stored simultaneously in the same field*. **This is a confirmed
distinction, not an assumption**: a reader querying `tip_dokaza` mid-race sees either the pre- or post-value,
never a mix or both. Sharper statement than prior forks gave: the defect is "unpredictable single value,"
not "corrupted/duplicated value."

**However — a genuinely new, sharper, and worse finding**: the race's *losing* write is not actually
discarded. `intake_documents.document_type` (the English-vocab staging value, migration 074's CHECK-
constrained column) is **never deleted at finalize** — the only deletion path is
`delete_partial_document()` (`shared/intake_documents.py:176-187`), called exclusively from the crash-recovery
guard in `shared/intake_worker.py:161` (Sprint 001's own fix), not from the normal finalize flow. This means:

- `GET /api/smart-intake/jobs/{job_id}` (`routers/smart_intake.py:217-264`, `intake_job_status`, confirmed
  live: `@router.get`, rate-limited 60/min, `Depends(get_current_user)`) remains callable **indefinitely
  after finalize** and returns `document["document_type"]` (line 255) — the original English-vocab
  classification, frozen at whatever it was before `evidence.py`'s async task ever ran or possibly landed a
  *different* value later.
- **This endpoint is not merely theoretically reachable — it is the exact endpoint the Smart Intake review
  screen (step 3, before finalize) already polls** (`static/vindex.js:21131`, `:21162`), and the frontend
  keeps its own hardcoded Serbian translation map for this English vocabulary,
  `_SI_DOC_TYPE_LABELS` (`static/vindex.js:20933-20938`, all 13 `intake_classify.py` types mapped to Serbian
  labels — e.g. `appeal → 'žalba'`, `court_decision → 'sudska odluka'`, `evidence → 'dokaz'`), rendered at
  `vindex.js:21215` and `:21348` **during the lawyer's finalize-review step**.
- **Concrete contradiction, confirmed, not merely possible**: `evidence.py`'s 9-type taxonomy does not contain
  `'žalba'`, `'dokaz'`, or `'sudska odluka'` as literal `tip_dokaza` values (its own set is `sudska_odluka`,
  `podnesak`, `ugovor`, `dopis`, `medicinska_dokumentacija`, `finansijska_dokumentacija`, `javna_isprava`,
  `vestacki_nalaz`, `ostalo` — `evidence.py:42-51`). A document the lawyer saw and implicitly confirmed as
  `'žalba'` during Smart Intake review can, after finalize, show as `'podnesak'` in Evidence Vault — **two
  different, human-visible, Serbian-language classification labels for the same physical document, held
  simultaneously and indefinitely in two different tables (`intake_documents.document_type` vs.
  `predmet_dokumenti.tip_dokaza`), reachable via two different live endpoints, with zero reconciliation code
  anywhere in the codebase (grepped: no cross-reference between the two tables by document identity exists).**
  This is a **confirmed defect**, distinct in shape from the already-known race — the race is about which
  value *lands* in one field; this is about a stale, un-cleaned-up value in a *second* field that nothing
  ever reconciles against the first, and that a real screen already surfaces to the lawyer before the "real"
  classification even exists.

### 6(b) — Same document, uploaded twice: no consistency check exists anywhere, confirmed by exhaustive grep

Extending Sprint 002's finding (content hash computed, essentially never queried) into the classification
domain specifically: `source_sha256` is computed at 3 sites — `api.py:4198`, `smart_intake.py:688`,
`dokument.py:221` (this last one never persists, ephemeral session path) — and grepping every occurrence of
`source_sha256` in the repo (`api.py`, `drafting.py`, `dokument.py`, `smart_intake.py`, `uploaded_doc/*`,
tests) finds **zero** `.eq("source_sha256", ...)`/`.filter(...)`/any query site that reads it back for
comparison. **Confirmed: no code anywhere compares two `predmet_dokumenti` rows' `tip_dokaza` values for
agreement, even when their `source_sha256` values are identical.** If the same physical file is uploaded
twice — Pipeline A twice, or Pipeline A once and Smart Intake once, or (per §1.3) once into a case via
Pipeline A/B and once into Klijenti Trezor with a manually-typed different type — the system has **no concept
that these are "the same document,"** and each row's `tip_dokaza` (or Trezor's `tip_dokumenta`) is decided,
displayed, and consumed by downstream `EXPECTED_DOCS` matching completely independently. Confirmed defect
(absence of a feature that would need to exist to prevent silent contradiction), not observed as an active
data-corruption incident — no evidence either way of it having actually happened in production data (out of
this fork's scope to query live DB rows).

### 6(c) — Re-running `/reklasifikuj` twice: two separable questions, answered separately

**(i) Concurrency defect — confirmed, code-level, not model-dependent.** `reklasifikuj`
(`evidence.py:375-408`) itself launches its classification via an **unawaited** `asyncio.create_task`
(line 401-406) and returns immediately (`"poruka": "Reklasifikacija pokrenuta u pozadini."`) — it is
rate-limited (`@limiter.limit("10/minute")`, line 376) but has **no per-document lock or idempotency guard**.
Two rapid calls against the same `dok_id` (double-click, two browser tabs, or a retried request after a slow
initial response) launch two concurrent background tasks, each independently calling `_klasifikuj_dokument`
and then unconditionally `UPDATE`-ing `tip_dokaza` (`evidence.py:210-215`, no `WHERE` clause checking a
version/timestamp, no compare-and-swap). Whichever GPT-4o-mini call's `UPDATE` executes last silently wins,
irrespective of which call was launched first. **This is the exact same race shape as the already-known
intake finalize race, self-inflicted by the very action meant to fix a bad classification** — confirmed
defect, exists regardless of whether the model returns identical output both times.

**(ii) Model-nondeterminism — genuinely unverified, not a code bug, with concrete evidence for how likely it
is.** Determinism controls (`temperature`) were checked at every LLM-based classifier's actual call site:

| Classifier | `temperature` | File:line |
|---|---|---|
| `evidence.py::_pozovi_evidence_api` (the canonical one) | `0` | `evidence.py:64` |
| `api.py::_call_metapodaci` (new, §1.2) | `0` | `api.py:4529` |
| `intake_classify.py::classify_llm` (LLM-fallback path only — `classify_heuristic` short-circuits first and is 100% deterministic) | `0.1` | `intake_classify.py:103` |
| `dokument.py::_klasifikuj_dokaz` | `0.2` | `dokument.py:79` |
| `api.py::_detect_doc_type` | N/A — pure keyword heuristic, no LLM call at all | `api.py:3539-3541` |

`evidence.py`'s own classifier — the one `reklasifikuj` actually re-runs — uses `temperature=0`, the
code-level intent is deterministic. **This fork did not execute live repeat calls against the OpenAI API to
verify bit-for-bit repeatability** (out of a read-only investigation's means, and `temperature=0` on GPT
models is well-documented industry-wide as reducing but not mathematically guaranteeing identical output
across calls, due to upstream batching/routing nondeterminism outside this codebase's control). **Correctly
classified as genuinely unverified/model-dependent, not a code bug** — distinct from finding (i), which is a
100%-reproducible code defect independent of what the model returns.

---

## Summary for parent

**Phase 1**: 5 independent AI document-type classifiers exist (not 4) — `api.py::_call_metapodaci` is a new
finding, an 8-vocabulary 5th classifier hiding in plain sight because it persists to `predmet_istorija`, not
`predmet_dokumenti.tip_dokaza`, so it was invisible to every prior `tip_dokaza`-scoped grep. A 6th, genuinely
separate and correctly-scoped human-decided taxonomy exists for a different object (Klijenti Trezor's
`klijent_dokumenti.tip_dokumenta`). Zero human-override path exists for the actual case-document field
(`tip_dokaza`) anywhere in the platform — Evidence Vault's `/reklasifikuj`, despite its name and the task
brief's assumption, only re-triggers the same AI, it does not accept a lawyer-typed value. `genome_validator.py`
and `case_commander.py` confirmed clean (zero matches). All consumer sites (`risk_engine.py`, `matter_intel.py`,
`ccc.py`, `case_dna.py`, `evidence_graph.py`, `case_pipeline.py`) confirmed read-only, not competing
classifiers.

**Phase 6**: Three distinct, precisely-separated findings, not one blurred claim. (a) The already-known
classifier race produces an unpredictable *single* value, not a stored contradiction in one field — but a
**new, sharper defect** was found: the losing/superseded English-vocab value never gets cleaned up out of
`intake_documents.document_type`, remains live-queryable via `GET /api/smart-intake/jobs/{job_id}`
indefinitely after finalize, and is the exact value + a hardcoded frontend translation map
(`_SI_DOC_TYPE_LABELS`) the lawyer already sees during Smart Intake's own review step — producing a confirmed,
concrete, user-visible, permanent two-different-Serbian-labels contradiction across two tables/endpoints for
the same document, with no reconciliation code anywhere. (b) Confirmed by exhaustive grep: no code anywhere
compares `tip_dokaza` across rows sharing the same `source_sha256`, or across a case-document row and a
Klijenti Trezor row for what might be the same physical file — the system has no concept of "these are the
same document" for classification purposes, extending Sprint 002's upload-dedup finding into the
classification domain. (c) `/reklasifikuj` has a confirmed, code-level, model-independent concurrency defect
(unawaited fire-and-forget task, no lock, no compare-and-swap — a double-click races itself); separately,
whether the underlying GPT-4o-mini call is bit-for-bit repeatable at `temperature=0` is genuinely unverified
and correctly left unverified rather than assumed either way — `evidence.py`'s canonical classifier and the
new `api.py::_call_metapodaci` both use `temperature=0` (deterministic intent), while
`intake_classify.py`'s LLM-fallback path (`0.1`) and `dokument.py`'s classifier (`0.2`) are non-deterministic
by explicit design choice, not oversight.

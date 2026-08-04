# Forensics — Program Intake, Sprint 001: Upload / OCR / Classification / Storage

**Scope:** document intake pipeline ONLY (upload → OCR → validation → storage). Decision Engine, Copilot,
Strategy Engine, Firm Brain, Briefing, Dashboard, Search, Alerts, Timeline, Deadlines, Task Engine, Memory
Graph explicitly out of scope — noted in one sentence where touched, not investigated. Read-only, no
code/git changes. All claims verified against current code today (2026-08-04), not cited from prior
missions on faith — prior art is cited only where independently re-confirmed, and every place this fork's
own reading diverges from or extends prior art is marked explicitly.

**Prior art read in full before investigating:** `2026-08-04_gamma_domain_search_memory_firmbrain_pipeline_
INVENTORY.md` §2, `2026-08-04_alpha_domain_document_pipeline_INVENTORY.md`, `2026-08-04_beta_domain_upload_
ocr_extraction_INVENTORY.md`, `ARCHITECTURAL_DEBT_REGISTER.md` (ALPHA-003/004, PROGBETA-006/008),
`2026-08-03_LZ-002_evidence_autoclassify_MISSION_REVIEW.md`, `2026-08-02_intake_convergence_DECISION_
RECORD.md`, `2026-08-03_BC-001-002_smart_intake_and_staging_ui_ARCHITECTURE_DECISION.md`,
`2026-08-03_LD-001_photo_upload_reachable_path_MISSION_REVIEW.md`, `2026-08-03_ZTC-FRONTEND_smart_intake_
wiring_BLOCKER_REPORT.md`, `2026-08-02_M-001_image_upload_MISSION_REVIEW.md`.

---

## Finding 1 — Six independent writers of `predmet_dokumenti`, not two; three genuinely reachable upload
entry points, not counting an admin-only fourth and an ephemeral fifth pipeline

Grepped every `predmet_dokumenti` insert in the repo. Six call sites write a real row into the canonical
document table:

| # | File:line | Path | Runs OCR? | Sets `tip_dokaza` at insert? | Triggers async classification? |
|---|---|---|---|---|---|
| 1 | `api.py:4226/4228` (`predmet_upload_auto_analyze`, route `POST /api/predmeti/{id}/upload`) | Older per-case upload | Yes, `extract()` called directly at `api.py:4120` | No | Yes — `api.py:4265-4274`, fires `evidence.py::klasifikuj_i_sacuvaj` |
| 2 | `routers/smart_intake.py:682` (`finalize_intake_job`) | Smart Intake Engine | No — reuses text already OCR'd by the async worker (`shared/intake_worker.py`) | **Yes**, synchronously, English vocabulary (`tip_dokaza: doc_type`, line 676) | Yes — `smart_intake.py:725-735`, fires the same `evidence.py::klasifikuj_i_sacuvaj` |
| 3 | `routers/intake.py:236/242` (`kreiraj`, CRM Wizard) | CRM Intake Wizard — attaches *references* to already-uploaded docs | No — never calls `extract()` at all | No | **No** — no classification of any kind is ever triggered for a document linked this way |
| 4 | `routers/onboarding.py:274` | Demo-predmet stub (welcome/onboarding flow) | No — no real file, metadata only (`naziv_fajla`/`velicina_kb`) | No | **No** |
| 5 | `routers/drafting.py:310` (`_promote_staged_draft_to_pinecone`) | AI-drafted document, lawyer-approved, promoted into the case record | N/A — generated text, not OCR'd | No | **No** |
| 6 | `routers/evidence.py:210-215` | Not an insert — the `UPDATE` that all of the above eventually route through | N/A | Overwrites unconditionally | N/A (this IS the classifier) |

**Three genuinely reachable, independent upload entry points that let a user get a NEW document into the
system** (i.e., rows #1 and #2's insert paths, plus the ephemeral non-`predmet_dokumenti` path below):

1. **`POST /api/predmeti/{predmet_id}/upload`** (`api.py:4061-4063`, `predmet_upload_auto_analyze`) — the
   older, synchronous, per-case upload. Confirmed still the primary reachable path (LD-001's 2026-08-03
   fix — `_ALLOWED_MIMES`/`_ALLOWED_SUFFIXES` at `api.py:4040-4058` — is live: `.jpg`/`.jpeg`/`.png` present,
   with LD-001's own in-code comment explaining why).
2. **`POST /api/smart-intake/documents` + `POST /api/smart-intake/jobs/{id}/finalize`**
   (`routers/smart_intake.py:94`, `:375`) — async, job-queue-based, batch, document-first case creation.
   **Correction to prior art, verified today**: `2026-08-03_ZTC-FRONTEND_smart_intake_wiring_BLOCKER_
   REPORT.md` stated Smart Intake had **zero** frontend callers ("Exhaustive search... zero matches").
   That gap is closed — `2026-08-03_BC-001-002...ARCHITECTURE_DECISION.md` documents two new buttons
   ("+ Iz dokumenta", "Otpremi dokumenta") added the same day, and a direct grep of `static/vindex.js`
   today finds **8** occurrences of `smart-intake`/`smart_intake`, confirming real, current frontend wiring.
   Both upload paths (#1 and #2) are live, reachable, and independent today — this is not a stale/dead
   second path, it is two real, parallel, user-reachable ways to get a document into a case.
3. **`POST /api/dokument/upload`** (`routers/dokument.py:159-161`) — the deliberately separate, ephemeral,
   session-based Q&A upload (`docs/adr/0001-async-ingest-job-queue.md`'s own stated rationale, re-confirmed
   by direct code read: 24h-TTL Pinecone `tmp_` namespace, **never inserts into `predmet_dokumenti` at
   all**). Correctly identified by `2026-08-02_intake_convergence_DECISION_RECORD.md` as a third, distinct
   system that should not be merged with the other two — re-confirmed here at the code level: this file has
   no `predmet_dokumenti` reference anywhere (grepped).

**Not case-document upload entry points, noted for completeness only, not investigated further** (out of
this sprint's document-into-a-case scope): `routers/law_upload.py` (`POST /api/admin/law/upload`) is
admin-only ingestion of Serbian statute PDFs into Pinecone's `zakoni_rs` namespace — a different corpus
entirely, not a case document. `klijenti/router.py`'s `UploadFile` is a CSV client-list bulk import, not a
document upload.

**Convergence answer:** Upload paths #1 and #2 do **not** converge on the same downstream processing —
they are two independently-coded pipelines that both eventually call the same two leaf functions
(`uploaded_doc/extractor.py::extract()` for OCR, `routers/evidence.py::klasifikuj_i_sacuvaj()` for
classification) but via **entirely separate call sequences with different synchronous side effects**
(see Finding 3). Path #3 (`routers/intake.py`) converges with neither — it is a pure reference-linking
mechanism with no OCR and no classification trigger of any kind (see Finding 4).

---

## Finding 2 — OCR: still `pytesseract.image_to_string()`, still no real confidence; THREE real call
sites into `extract()`, not one (correction to Program Alpha's inventory)

`uploaded_doc/extractor.py` (312 lines, read in full) confirmed unchanged from Program Beta's own
description: `_ocr_image()` (lines 103-120) calls `pytesseract.image_to_string(img, lang=ocr_lang,
timeout=45)` with an `eng`-only fallback on failure — no `image_to_data()`, no per-word confidence anywhere.
Every one of `extract_pdf`/`extract_image`/`extract_docx`/`extract_txt`/`extract()` returns a 3-tuple
`(text, is_scanned, ocr_used)` — **there is no confidence field returned by the extractor at all**, matching
Program Beta's finding exactly.

**Correction to Program Alpha's own domain inventory** (`2026-08-04_alpha_domain_document_pipeline_
INVENTORY.md`, line 13): it states `extract()`'s "Consumers" column as `shared/intake_worker.py (only call
site found)`, rated "1 — genuinely canonical." **This is inaccurate as of today's code.** A direct grep for
every caller of `extract(` found **three** independent call sites, not one:

- `shared/intake_worker.py:246-247` (`IntakeWorker._extract_text`, the async Smart Intake worker)
- `api.py:4078,4120` (`predmet_upload_auto_analyze`, called **directly and synchronously** inside the
  request path, via `asyncio.to_thread(extract, tmp_path)`)
- `routers/dokument.py:175,199` (`dokument_upload`, also direct/synchronous, same pattern)

The function itself is genuinely canonical (one implementation, no duplicate OCR logic anywhere) — Alpha's
underlying conclusion ("OCR is not duplicated") still holds. But the specific claim "only call site found"
undercounts by 2, which matters for this sprint's mandate to map every path with file:line precision: a
future change to `extract()`'s signature or behavior has three call sites to update, not one, and two of
them (`api.py`, `dokument.py`) run it synchronously inside a live HTTP request with a 10-45s pytesseract
timeout in the call chain, not safely isolated in a background worker the way Alpha's "canonical, single
call site" framing implies.

`routers/drafting.py:469` imports `extract_docx`/`extract_txt` directly (bypassing the `extract()`
dispatcher) for a different purpose (loading a reference document into a drafting prompt, not intake) —
noted for completeness, not a duplicate of the OCR decision since it never touches the image/PDF-OCR path.

---

## Finding 3 — The classification race (Gamma's finding): confirmed still live today, exactly as described,
PLUS a second, structurally different failure mode on the OTHER upload path Gamma did not examine

### 3a. Smart Intake path — confirmed unchanged at the cited lines

Re-read `shared/intake_worker.py:128-204` (`_process`) and `routers/smart_intake.py:586-757` (the finalize
document-linking block) in full. Every specific claim in Gamma's §2 is independently reconfirmed at today's
line numbers:

- `intake_worker.py:173` calls `self._classify(text)` → `shared/intake_classify.py::classify()`
  (English 13-type vocabulary: `lawsuit`, `judgment`, etc., defined `intake_classify.py:32-36`).
- `intake_worker.py:176-183` writes this into the **staging** table via `intake_documents.create_document()`
  — this is `intake_documents.document_type`, not yet `predmet_dokumenti.tip_dokaza`.
- `smart_intake.py:426` (`finalize_intake_job`) reads it back: `doc_type = document.get("document_type") or
  "other"`.
- `smart_intake.py:676` writes it **synchronously**, inside the finalize request, as the first attempt of a
  three-variant fallback insert loop (lines 675-687): `{**_dok_row_base, "tip_dokaza": doc_type,
  "klasifikovan_at": "now()", ...}` — this is the wrong-vocabulary write landing in `predmet_dokumenti`.
- `smart_intake.py:725-735` (`_evidence_classify_bg`) fires `routers/evidence.py::klasifikuj_i_sacuvaj` via
  **`asyncio.create_task`, unawaited, no retry on the caller side, failure caught by a bare
  `except Exception as ce: logger.warning(...)`** (line 733-734) — exactly as Gamma described.
- `routers/evidence.py:210-215` (`klasifikuj_i_sacuvaj`'s own `UPDATE`) overwrites `tip_dokaza`
  **unconditionally**, with no confidence field and no conditional check against the existing value.

**New precision this fork adds, not previously stated**: the synchronous write at `smart_intake.py:675-687`
is itself a 3-variant try/fallback loop — if the `tip_dokaza`/`klasifikovan_at` column variant fails (e.g. a
schema-mismatch edge case), it falls back to a variant with **no `tip_dokaza` field at all**. In the
overwhelming common case (migration 016/074 applied) the first variant succeeds and Gamma's description
holds exactly; this fallback path is a secondary, lower-probability way the field could start out fully
NULL rather than wrong-vocabulary — same ultimate consequence (invisible to `EXPECTED_DOCS` matching),
different starting state.

**Verdict: the race is live, unchanged, and exactly as Gamma described.** No code has touched this path
since Gamma's fork ran.

### 3b. `api.py`'s older upload path — a DIFFERENT bug shape Gamma's narrower scope did not examine

Gamma's fork was scoped to the Smart Intake finalize flow specifically. Reading `api.py`'s older,
independently-reachable upload endpoint (`predmet_upload_auto_analyze`, Finding 1's path #1) end to end
shows a **structurally different defect in the same field**:

- The insert at `api.py:4211-4228` (`_row` dict) **never includes `tip_dokaza` at all** — no synchronous
  classifier runs on this path (no `intake_classify.py` call anywhere in `api.py`).
- `api.py:4265-4274` fires the identical `asyncio.create_task(asyncio.to_thread(klasifikuj_i_sacuvaj, ...))`
  pattern as Smart Intake, unawaited, same silent-log-only failure handling
  (`except Exception as _ce: logger.warning(...)`, line 4273-4274).
- **Consequence, precisely stated**: on this path there is no wrong-vocabulary intermediate value to race
  against — `tip_dokaza` is simply **NULL from the moment of insert** until (if ever) the single background
  classifier lands. If `klasifikuj_i_sacuvaj` throws (its own internal `_klasifikuj_dokument` call is
  wrapped in its own try/except that returns a safe `"ostalo"` default, so it practically never raises; but
  the surrounding `UPDATE` at `evidence.py:210-215` can still fail on a transient DB error, silently logged
  only) — `tip_dokaza` stays **permanently NULL**, not permanently wrong-vocabulary.
- A permanently-NULL `tip_dokaza` is exactly as invisible to `services/risk_engine.py`'s `EXPECTED_DOCS`
  matcher as a wrong-vocabulary one — same downstream consequence, different mechanism, previously
  undocumented because no prior fork traced this specific endpoint's classification wiring end to end.

**Why this matters for the sprint's mandate**: both of the platform's two live, reachable, independent
upload entry points have a live gap in `tip_dokaza` reliability, but the two failure modes are NOT the same
bug and would need different fixes — Smart Intake's is "two writers, wrong one can win or persist";
`api.py`'s is "one writer, async, no synchronous fallback at all, single point of failure with no safety
net." A fix designed only around Gamma's (Smart Intake) description would leave `api.py`'s upload path's
gap completely unaddressed, since it doesn't have a second, wrong-vocabulary write to reconcile — it has no
write at all until the background task lands.

### 3c. Two more writers where NO classifier ever runs (new, not previously documented anywhere)

Finding 1's rows #3 (`routers/intake.py`), #4 (`routers/onboarding.py`), and #5 (`routers/drafting.py`)
insert real `predmet_dokumenti` rows and **never trigger any classification background task at all** — no
`asyncio.create_task(klasifikuj_i_sacuvaj, ...)` anywhere in any of these three files (confirmed by reading
each insert's surrounding code). Consequence: a document attached via the CRM Wizard's reference-linking
step, a demo predmet's stub document, or a lawyer's own AI-drafted-and-approved document all carry
`tip_dokaza = NULL` **permanently, by design**, not as a race-condition side effect — these three paths
never even attempt the correct-vocabulary classification. For `routers/drafting.py`'s case specifically,
this means a real, lawyer-approved, substantive document in the case file is structurally invisible to
`EXPECTED_DOCS`-based missing-document detection forever, unless a lawyer separately, manually triggers
`/api/evidence/predmeti/{id}/reklasifikuj/{dok_id}` (confirmed still present, `routers/evidence.py:375-377`)
for that specific document.

**No confidence arbitration exists anywhere in this system** — re-confirmed: `evidence.py::_klasifikuj_
dokument` (lines 73-93) returns no confidence field, and its caller's `UPDATE` (lines 210-215) has no
conditional logic of any kind; "whoever writes last wins, if anything writes at all" is the complete
description of `tip_dokaza` ownership across all six writers.

---

## Finding 4 — Four independent AI document-type classifiers exist, not two; only two of them ever reach
the canonical field (correction/extension of ALPHA-003)

ALPHA-003 and Gamma's §2 both frame this as "two independent taxonomies" (`intake_classify.py`'s English
13-type vs. `evidence.py`'s Serbian 9-type). Both are correct about the two that matter for the race
(Finding 3), but a full read of every upload-adjacent file in scope finds **two additional, previously
uncounted classifiers**, neither of which writes to `predmet_dokumenti` and so neither participates in the
race — but both are real, independent AI calls answering the identical question ("what type of document is
this") that no prior audit's classification-duplication count included:

1. `api.py:3539-3541` (`_detect_doc_type`) — a third, coarse, 3-way keyword heuristic
   (`presuda`/`ugovor`/`opsti`), called at `api.py:4147` immediately after OCR on the older upload path.
   **Never persisted to any table** — used only to pick which AI system-prompt variant runs for that
   endpoint's own "auto-analiza" writeup (`api.py:4293-4294`) and returned to the caller in the JSON
   response (`api.py:4654`, key `"doc_type"`). Ephemeral, ephemeral-only, does not collide with anything in
   the database — but it is a third GPT-prompt-routing decision over "what kind of document is this,"
   unrelated to and uncoordinated with either of the two DB-writing classifiers.
2. `routers/dokument.py:71-118` (`_klasifikuj_dokaz`) — a **fourth**, entirely separate taxonomy
   (`ugovor|presuda|resenje|zapisnik|izvestaj|priznanica|dopis|punomocje|ostalo`, line 95), its own GPT-4o-
   mini call, its own prompt, running inside `routers/dokument.py`'s ephemeral session-based Q&A upload
   (Finding 1, path #3). Never written to `predmet_dokumenti` (that pipeline never inserts a row there at
   all) — the result is only retrievable via a separate on-demand endpoint
   (`POST /api/dokument/klasifikuj-sesija`, referenced at `dokument.py:271-272` but not read in full, out of
   this sprint's storage-focused scope beyond noting its existence).

**Net correction**: four independent AI document-classification implementations exist in the
intake-adjacent codebase today (`intake_classify.py`, `evidence.py`, `api.py::_detect_doc_type`,
`dokument.py::_klasifikuj_dokaz`), a duplicated-AI-cost and maintenance-burden count ALPHA-003 did not
capture in full — but the *correctness* risk (the race, Finding 3) is still specifically and only about the
two that write to the canonical `predmet_dokumenti.tip_dokaza` column. The other two are real but
lower-severity findings: wasted API calls maintaining prompts for the same question, not a data-integrity
bug.

---

## Finding 5 — Entity extraction (ALPHA-004): confirmed current, no change

`shared/intake_extract.py` (269 lines, read in full) and `routers/evidence.py`'s `ai_tags` extraction
(embedded in `_klasifikuj_dokument`'s single prompt, lines 26-55) remain exactly as ALPHA-004 and Program
Beta described: intake's version is regex-first (case_number 0.95, amount 0.92, court 0.9, deadline
0.72-0.97 formula-derived — confirmed genuinely deterministic, `intake_extract.py:85-150`) with an LLM
fallback for judge/plaintiff/defendant/court/law_cited (`extract_free_text_entities`, lines 192-236,
`gpt-4o-mini`, temp 0.1, each field individually null-safe). Evidence's `ai_tags` is a single unstructured
LLM field with no regex pre-check and no per-field confidence. **Confirmed: these write to different
targets** — intake's entities go to the `extracted_entities` staging table (via
`intake_documents.insert_entities`, called from `intake_worker.py:184`, never promoted into
`predmet_dokazi` or any permanent case table by any code this fork found) while Evidence's `ai_tags` writes
directly onto `predmet_dokumenti.ai_tags` (`evidence.py:213`) and `kljucne_cinjenice` becomes
`predmet_dokazi` rows (`evidence.py:238-276`). **No active overwrite conflict** — ALPHA-004's own
"lower-priority than ALPHA-003" framing holds, unchanged. One consequence not previously stated: Smart
Intake's regex-extracted, genuinely-deterministic entities (case number, amount, deadline, court) are
computed, stored in the staging table, shown to the lawyer during the finalize review step — **and then
never written anywhere permanent** once the case is created; only Evidence's less-rigorous, unstructured
LLM `ai_tags` survives into the case's permanent record. The more trustworthy extraction is the one that
gets thrown away after finalize.

---

## Finding 6 — Evidence `snaga`: PROGBETA-006's fix is confirmed live (correction to Beta's own now-stale
finding)

Program Beta's inventory (`2026-08-04_beta_domain_upload_ocr_extraction_INVENTORY.md`, its own "worst
offender") describes `predmet_dokazi.snaga` as hardcoded `"srednja"` for every row. **This has since been
fixed within the same day's work** (`routers/evidence.py:163-186`, `_snaga_iz_lokacije`, explicitly
docstring-dated "Program Beta (2026-08-04)"): `snaga` is now derived from `_lociraj_tvrdnju`'s own
found/not-found grounding result — `"jaka"` only when the claim is both located AND within a
length-validated range (`_SNAGA_MIN_TVRDNJA_LEN` to `_PROBE_MAX_LEN`, lines 160, 183), `"srednja"`
otherwise. Confirmed wired into `klasifikuj_i_sacuvaj`'s row-building loop at `evidence.py:250`. Beta's own
Architectural Debt Register entry (`PROGBETA-006`) already flags the one remaining consequence of this fix
(pre-fix rows stay frozen at the old default, no backfill) — re-confirmed accurate, not re-derived here.

---

## Summary for parent

**Upload entry points: 3 genuinely independent, reachable ones** for getting a document into the system —
`POST /api/predmeti/{id}/upload` (older, synchronous, per-case), `POST /api/smart-intake/documents` +
`/finalize` (async, batch, document-first case creation — confirmed reachable from the frontend today, via
2026-08-03's BC-001/002 buttons, correcting the earlier ZTC-FRONTEND blocker report's "zero frontend
callers" finding, which was accurate when written but is no longer accurate), and `POST /api/dokument/
upload` (ephemeral, session-based, never touches `predmet_dokumenti` at all). They do **not** converge on
shared processing — each has its own independent sequence of OCR/classification/insert calls, sharing only
two leaf functions (`extract()`, `klasifikuj_i_sacuvaj()`).

**The classification race Program Gamma found is still live today, unchanged, at the exact cited lines**
(`shared/intake_worker.py:173`, `routers/smart_intake.py:676` and `:725-735`, `routers/evidence.py:210-215`).
**This fork's main extension**: that race is only ONE of at least three distinct `tip_dokaza`-reliability
gaps across the platform's upload paths — the *other* live upload endpoint (`api.py`'s older per-case
upload) has no synchronous write at all, so its failure mode is "permanently NULL if the lone async
classifier fails" rather than "permanently wrong-vocabulary"; and three more writers of `predmet_dokumenti`
(`routers/intake.py`'s reference-linking, `routers/onboarding.py`'s demo stub, `routers/drafting.py`'s
approved-draft promotion) never trigger classification at all, by design, leaving `tip_dokaza` permanently
NULL for every document that arrives through them — including, notably, a lawyer's own finished, approved
work product.

**Single most severe finding**: `routers/drafting.py:309-318` — a lawyer-approved AI draft, promoted into
the permanent case record as a real `predmet_dokumenti` row, **never gets `tip_dokaza` set by any mechanism
in the codebase** unless a lawyer manually visits Evidence Vault and clicks reklasifikuj for that specific
document. This is worse than the already-known race condition: the race at least usually resolves to a
correct value once the background task lands; this path has no background task at all. A case's own
generated legal work product is structurally invisible to `services/risk_engine.py`'s missing-document
detector forever, by design, silently — the exact "next action" algorithm the platform relies on as its
sole deterministic source of truth (per Core Consolidation) cannot see one of the most legally significant
documents in the case.

**OCR**: unchanged from Program Beta's description (`pytesseract.image_to_string()`, no real confidence,
`0.6` hardcoded placeholder at the one point it's needed downstream) — but reached by **three** independent
call sites, not the one Program Alpha's inventory counted (`shared/intake_worker.py`, `api.py`,
`routers/dokument.py`), two of which run it synchronously inside a live HTTP request.

**Classification duplication**: four independent AI classifiers exist (not two) — `intake_classify.py`,
`evidence.py`, `api.py::_detect_doc_type`, `dokument.py::_klasifikuj_dokaz` — but only the first two ever
write to the canonical column, so the correctness risk remains exactly as sized by ALPHA-003/Gamma; the
other two are pure cost/maintenance duplication, not a data-integrity bug.

**Entity extraction (ALPHA-004)**: unchanged, confirmed still two independent, non-colliding pipelines — new
observation: the more rigorous, deterministic regex-based extraction (Smart Intake) is discarded after
finalize; only the less rigorous LLM-based extraction (Evidence) survives into the permanent record.

**`snaga` (Beta's "worst offender")**: already fixed, same day, confirmed live — Beta's own finding is now
stale and should not be re-flagged by a future fork without checking `evidence.py:163-186` first.

# Program Intake Sprint 005 — "Canonical Document Segmentation" — Phase 1 Segmentation Audit

**Date**: 2026-08-05
**Scope**: READ-ONLY audit. Confirm and extend Sprint 003's `INTAKE-011` side-finding ("every classifier reads
only the HEAD of a whole-file concatenated text string... no document-boundary concept anywhere in the data
model") with a dedicated, deeper pass: extractor internals, chunker internals, a repo-wide inventory of ANY
existing document-splitting code (for any purpose), schema/UI multi-document awareness, and the exact
data-shape at every OCR/extraction call site. Genome, Timeline, Deadlines, Tasks, Copilot, Strategy Engine,
Firm Brain, Search — not touched, noted only where directly relevant.

---

## 1. `uploaded_doc/extractor.py` — page-level text: does it exist internally, and where is it discarded?

**File**: `uploaded_doc/extractor.py` (312 lines, full file read).

### `extract_pdf()` (lines 142–201) — born-digital path

- Line 150: `reader = pypdf.PdfReader(str(path))`
- Lines 154–159:
  ```python
  pages: list[str] = []
  total_chars = 0
  for page in reader.pages:
      text = (page.extract_text() or "").strip()
      pages.append(text)
      total_chars += len(text)
  ```
  **Per-page text absolutely exists as a Python list (`pages: list[str]`) at this point** — one string per
  physical PDF page, in order.
- Line 166: `return "\n\n".join(pages), False, False` — **this is the exact discard point.** The list is
  flattened into a single string and the page boundaries are never returned. The function signature itself
  (`tuple[str, bool, bool]`) has no slot for a list.

### `extract_pdf()` — OCR/scanned path (lines 168–201)

- Lines 177–185:
  ```python
  doc = fitz.open(str(path))
  ocr_pages: list[str] = []
  for page_num, page in enumerate(doc):
      pixmap = page.get_pixmap(dpi=300)
      img = Image.open(io.BytesIO(pixmap.tobytes("png")))
      page_text = _ocr_image(img, ocr_lang)
      ...
      ocr_pages.append(page_text)
  ```
  Same shape: `ocr_pages` is a per-page list, `page_num` is even explicitly available as a loop variable.
- Line 187: `ocr_text = "\n\n".join(p for p in ocr_pages if p)` — same discard pattern, and here it's actually
  slightly lossier: pages with empty OCR output are filtered out entirely (`if p`), so even a page-*count*
  signal is lost, not just page-*boundary* position.
- Line 190: `return ocr_text, False, True` — again, flat string only.

**Verdict**: **CONFIRMED — a hook point exists that could be reused.** Both code paths inside `extract_pdf`
already build a `list[str]` indexed by physical page before throwing it away at the join. Making segmentation
possible for PDFs does NOT require touching `pypdf`/`fitz` page iteration at all — it requires changing what
`extract_pdf` (and the shared `extract()` contract) *returns*, not how it *reads*. The minimal viable change is
literally: don't join, or join AND also return the pre-join list/offsets alongside it.

### `extract_docx()` (lines 204–232) — no page concept exists at all

- Lines 217–230: iterates `doc.element.body` block-by-block (`w:p` paragraphs, `w:tbl` tables), appending each
  block's text to a flat `parts: list[str]`.
- Line 232: `return "\n".join(parts), False, False`.

**Verdict**: **CONFIRMED — no competing implementation, and no reusable page hook either.** DOCX (OOXML) has no
first-class "page" concept in the document model at all — pagination is a rendering-time computation (font
metrics, page size, margins), not stored in the XML the way PDF stores discrete page objects. `python-docx`
does not expose page boundaries. Any segmentation signal for DOCX would have to come from structural markers
(headings, page-break elements `<w:br w:type="page"/>`, section breaks) rather than a true page list — a
materially different (and harder) problem than the PDF case. This is worth flagging explicitly for the design
phase: **"page-level" segmentation cannot be format-uniform** — PDF has real pages to key off, DOCX does not.

### `extract_txt()` (lines 235–237) and `extract_image()` (lines 247–298)

- `.txt` has no page concept (plain string, single read).
- `extract_image()` is inherently single-page — one image file = one OCR pass (line 281–282: `with
  Image.open(path) as img: text = _ocr_image(img, ocr_lang)`). No multi-page ambiguity possible here by
  construction — a segmentation feature would never apply to this path (a photographed single page can't
  contain "N documents" in the same way a combined PDF can, though it could in principle contain a montage —
  out of scope, not something the current code even partially handles).

### `extract()` dispatcher (lines 301–311)

Uniform contract confirmed: every format returns exactly `tuple[str, bool, bool]` — `(text, is_scanned,
ocr_used)`. This is the single interface all 4 call sites (see §5 below) rely on identically. **This is the
one contract that would need to change (or be supplemented by a new sibling function) for segmentation to
enter the pipeline at all.**

---

## 2. `uploaded_doc/chunker.py` — confirmed characterization, and is it a reusable signal?

**File**: `uploaded_doc/chunker.py` (187 lines, full file read).

Sprint 003's characterization is **CONFIRMED, precisely**:

- `chunk_document(text: str, source_meta: dict)` (line 123) takes an already-flattened string — no page or
  document-boundary information in `source_meta` (line 127–131 only reads `source_filename`, `source_format`,
  `source_sha256`, `is_scanned`, `session_id`).
- Two modes, chosen by density of a single global regex, not by any topic/identity signal:
  - `ARTICLE_REGEX` (lines 16–19): matches `Član|Člana|Članu|Članom|Tačka` + number. If
    `len(matches) >= ARTICLE_DENSITY_THRESHOLD` (3, line 20), the WHOLE text is treated as one article-numbered
    instrument (`_chunk_article_aware`, lines 44–62) — segments split purely at each "Član N" occurrence,
    with no concept that two different "Član 1"s from two different attached contracts are not the same
    logical unit.
  - Otherwise: pure token-count recursive splitting (`_split_recursive`, lines 65–92) — fixed
    `TARGET_TOKENS=600`/`OVERLAP_TOKENS=100`, paragraph/newline/sentence-boundary snapping only as a
    tie-breaker inside a token window, not a document-identity signal.
- `_enforce_max_tokens` (lines 101–120) only re-splits oversized segments; still no identity concept.
- `UploadedDocChunk` (schema.py lines 9–21) and `ChunkingManifest` (schema.py lines 24–35) confirm no
  `page_start`/`page_end`/`document_index`/`parent_document_id` field exists anywhere in the chunk record —
  fields are `chunk_index`, `chunk_mode`, `article_label`, `text`, `token_count`, `char_count`. `article_label`
  is the only quasi-structural field, and it is a *label* ("Član 7"), not a document-identity marker.

**Is it a reusable INPUT signal for segmentation?** **CONFIRMED — a hook point exists that could be reused,
but only a weak/partial one, and it is a fundamentally different concern.**

- Chunking's job is "make RAG-sized pieces of ONE known document" — it presupposes document identity, it does
  not discover it. Feeding chunker output into a segmentation step would be backwards (segmentation must run
  *before* chunking, since chunking already assumes one coherent document to chunk).
- The one thing genuinely reusable is the **regex machinery itself as a pattern-detection primitive**:
  `ARTICLE_REGEX`'s "Član/Tačka" density detection and the paragraph/newline boundary-snapping logic in
  `_split_recursive` (lines 78–85) are exactly the kind of structural-marker detection a segmentation engine
  would also need (just pointed at different markers — document-type headers like "TUŽBA", "PRESUDA",
  "PRILOG 1", court letterhead patterns — rather than "Član N"). This is a code-pattern reuse opportunity
  (same regex-density-threshold technique), not a data-pipeline reuse opportunity.
- Chunking is confirmed a **separate concern**: chunking = embedding/RAG granularity for a document already
  known to be one thing; segmentation = discovering how many "things" a single upload actually contains. They
  operate on opposite sides of the pipeline relative to document-identity.

---

## 3. Repo-wide inventory of ANY existing document-splitting code, for ANY purpose

This is the most important section for avoiding a competing implementation. Three genuinely distinct
mechanisms were found; none of them is a case-intake multi-document splitter, but one of them (`analiza/
segmenter.py`) was **not previously documented** in any intake sprint and must be accounted for by name in
Sprint 005's design so it isn't rediscovered mid-build or accidentally duplicated.

### 3a. `analiza/segmenter.py` — **NEW FINDING: an existing "Document Segmentation Engine," but for a different axis of the problem**

Not mentioned in any prior Program Intake sprint doc (`INTAKE_ARCHITECTURE_REPORT.md`,
`DOCUMENT_LIFECYCLE_ARCHITECTURE_REPORT.md`, `HUMAN_REVIEW_ARCHITECTURE_REPORT.md`,
`CLASSIFICATION_ARCHITECTURE_REPORT.md`, or the Sprint 003 fork's own review-queue edge-case doc) — confirmed
by grep, zero hits for "segmenter" in any of those four files.

- Module docstring literally names itself "Sloj 1 — Document Segmentation Engine" (lines 1–13).
- `detect_document_type(tekst)` (lines 93–124) — keyword-scores the **first 3000 characters only** (line 98:
  `probe = tekst[:3000].lower()`) into exactly one of `"ugovor"|"presuda"|"resenje"|"ostalo"` for the ENTIRE
  input string. **This is the identical head-only, single-document-assumption defect Sprint 003 found in the
  classifiers** — if fed a multi-document combined PDF, it will detect one type from whichever document is
  first, then segment the entire remaining blob as if it were sections/clauses of that one type.
  - `Segment` dataclass (lines 27–33): `id`, `type`, `naslov`, `tekst`, `start_offset`, `end_offset` — this
    IS a real, working start/end-offset structural model, but its segments are **sub-document units** (a
    contract clause "Član 7", a judgment section "obrazloženje") — never a claim about "this is a different
    physical document than the one before it."
  - `_segmentuj_ugovor`/`_segmentuj_presudu`/`_fallback_segments` (lines 162–324): regex/keyword-driven
    section splitting within the single detected doc_type. `_fallback_segments` (block-of-1500-chars) is the
    closest thing to a "no structure found" degrade path, structurally similar to chunker's recursive split
    but independently implemented (confirmed separate: no shared code between `chunker.py` and
    `segmenter.py`, both reimplement their own paragraph-boundary-snapping logic).
- **Consumers** (confirmed via grep, all single-document, all LLM-context-shaping, none intake-related):
  `routers/dokument.py:394,412` (Forenzički Legal Audit — `segment_document(tekst)` called once per
  analysis request, feeds `ask_analiza_v2`), `routers/evidence.py:143–144` (Evidence Vault grounding —
  populates `predmet_dokazi.paragraf` per migration `080_predmet_dokazi_grounding.sql`), `routers/
  cross_doc.py:118–120`, `main.py:4023` (imports the dataclasses), plus `analiza/validator.py:23`.
- Migration `080_predmet_dokazi_grounding.sql` (full file read) confirms the actual production use: it adds
  `stranica` (estimated page number, **"Procenjena stranica" = "estimated page," line 22-23 comment — not a
  true tracked page**), `paragraf` (segment ID like `"clause_7"`), `start_offset`, `end_offset` to
  `predmet_dokazi` — i.e., "where inside THIS ONE document did this evidence citation come from," not
  "how many documents are in this upload."

**Verdict**: **NEW FINDING.** A real, running, previously-undocumented segmentation engine exists in the repo,
but it segments *within* an already-identified single document (clauses/sections), assumes single document
identity via the same head-only pattern the classifiers use, and is owned by a different subsystem (Forenzički
Legal Audit / Evidence Vault grounding — outside this sprint's charter to modify). It is **not a competing
implementation of case-intake multi-document splitting** — it solves a different problem (structure-within-
one-document, not identity-of-how-many-documents) — but Sprint 005's design doc must name it explicitly to
avoid two "segment" concepts colliding in vocabulary or getting confused by a future reader/reviewer. Naming
recommendation: reserve "segment" for `analiza/segmenter.py`'s existing meaning (sub-document structural units)
and use a different term (e.g. "split," "sub-document," "logical document boundary") for whatever Sprint 005
designs, to avoid a name collision with an existing, shipped concept.

### 3b. `scripts/ingest_bilten.py` / `ingest_bilten_v2.py` / `ingest_bilten_to_pinecone.py` — **NEW FINDING: a real, working, multi-document PDF splitter — for bulk RAG-corpus ingestion, entirely unconnected to case intake**

Not mentioned in any prior Program Intake sprint doc (same grep check as above, zero hits).

- Purpose: ingesting scanned court-bulletin PDFs (Apelacioni sud Beograd/Niš, Vrhovni sud "bilteni") — each
  PDF contains **dozens of separate court decisions concatenated in one file** — into individual per-decision
  records for the Pinecone case-law knowledge base (`data/apelacioni_bilteni/`, confirmed present in the repo's
  untracked working tree per `git status`).
- `ingest_bilten_v2.py:117–124` (`_extract_text_from_pdf`):
  ```python
  def _extract_text_from_pdf(pdf_path: Path) -> list[str]:
      from pypdf import PdfReader
      reader = PdfReader(str(pdf_path))
      pages = []
      for page in reader.pages:
          pages.append(page.extract_text() or "")
      ...
      return pages
  ```
  **This function returns the per-page list directly** — proof that preserving page-level granularity from
  `pypdf` (the same library `uploaded_doc/extractor.py` uses) is not technically hard; `uploaded_doc/
  extractor.py` simply chooses not to, for its own (case-intake) purpose.
- `parse_bilten_bg()` (lines 172–onward): joins pages back into `full_text` (line 184, same "\n\n".join
  pattern as `extractor.py`!) but then **actually splits it into multiple logical documents** using a
  bulletin-format-specific boundary regex, `_AUTEUR_SPLIT` (lines 138–141): splits on the Serbian editorial
  marker `"аутор сентенце:"` ("sentence/headnote author:") which appears once per decision in this specific
  publication format. Each resulting segment becomes one `decision` dict with its own `decision_id`,
  `decision_number` (case number), `court`, date, etc. (confirmed by reading lines 260–270 building the `d =
  {...}` record).
  - `ingest_bilten.py` (line 68 `_extract_text_from_pdf`, line 128, lines ~181 "split by finding all
    attribution matches") does the same pattern for the AS Niš format.
  - This is a genuinely working "1 PDF → N logical documents" splitter, in production use for RAG corpus
    building — **but its splitting signal (`"аутор сентенце:"` boundary text) is entirely specific to this one
    court-bulletin publication format** and has zero applicability to a lawyer's uploaded lawsuit-plus-exhibits
    PDF, which has no such fixed editorial marker.

**Verdict**: **CONFIRMED — no competing implementation for case-intake purposes, but flagged per the mission's
explicit instruction to surface ALL existing splitting logic regardless of subsystem.** This is real,
shipped, multi-document-PDF-splitting code — just for a disconnected subsystem (scraped legal-corpus ingestion
for Pinecone, not `predmet_dokumenti`/`intake_jobs`/`intake_documents` at all — these scripts never touch
those tables). Two points of genuine design value for Sprint 005:
  1. **Precedent that page-list preservation from `pypdf` is cheap** (see `_extract_text_from_pdf` above) —
     directly answers part of Question 1's implication: nothing about `pypdf` itself forces the flattening
     `uploaded_doc/extractor.py` does.
  2. **A cautionary example of the alternative approach's fragility**: this splitter only works because the
     input format is externally fixed and known in advance (a specific court's bulletin layout). A general
     "any lawyer's combined PDF" segmenter cannot rely on a fixed editorial marker the way this script does —
     it would need a more general signal (document-type-header detection, page-layout discontinuity,
     court-letterhead repetition, etc.), which is a harder, more LLM/heuristic-dependent problem than what
     this script solves.

### 3c. `klijenti/router.py` (Trezor / client-document upload) — confirmed no multi-doc handling, and confirmed why

- `upload_klijent_dokument()` (lines 707–803, full function read): reads raw multipart bytes (line 734),
  encrypts with AES-GCM (lines 744–756), uploads the encrypted blob directly to Supabase Storage bucket
  `klijent-dokumenti` (lines 759–770), inserts one `klijent_dokumenti` metadata row (lines 776–787). **No
  `extract()` call anywhere in this file** (confirmed by grep: zero matches for `extractor` in
  `klijenti/router.py`).
- **Verdict**: **CONFIRMED — no competing implementation, and structurally cannot have one.** Trezor has no
  text-extraction or document-identity concept at all (it stores an opaque encrypted blob, never reads its
  content) — this reconfirms Sprint 003's characterization of Trezor as "a genuinely different object." A
  multi-document concept is not merely absent here, it is inapplicable to this pipeline's design as it exists
  today (there is nothing to segment because nothing is ever read).

### 3d. Nothing else found

Full `uploaded_doc/*.py` directory read/grepped (`cleanup.py`, `deadline_parser.py`, `ingest.py`,
`session.py`, `__init__.py`, `__main__.py`, `api_models.py`) — no other splitting logic. Repo-wide grep for
`page_start|page_end|parent_document|document_group|multi_doc|segment|split_from|source_page` across
`scripts/*.py` beyond the bilten scripts found nothing additional (other scrape/ingest scripts — `scrape_acas.
py`, `scrape_kjn.py`, `scrape_parlament.py`, `scrape_mfin.py`, `scrape_kzk.py`, `scrape_ustavni.py`,
`scrape_pa_sud.py`, `scrape_apelacioni_bilteni.py`, `scrape_echr.py`, etc. — are pure web-scraping/download
scripts, not PDF-content splitters; the actual splitting logic lives only in the separate `ingest_bilten*.py`
scripts covered above).

---

## 4. Schema and UI multi-document awareness

### Schema (migrations)

- `predmet_dokumenti`: no migration creates or alters this table with any parent/child, page range, or
  segment column (grepped `page_start|page_end|parent_document|document_group|multi_doc|segment|deo|is_multi|
  document_index|doc_index|split_from|source_page` case-insensitively across the entire `migrations/`
  directory — zero matches on this table).
- `intake_jobs` / `intake_documents`: same grep, only matches were in `074_intake_phase1a.sql` and
  `080_predmet_dokazi_grounding.sql` (Evidence Vault, covered in §3a — not intake).
- **Direct, load-bearing citation — migration `074_intake_phase1a.sql` line 58** (the `intake_documents` table
  comment, written 2026-07-xx, i.e. the schema's own author already flagged this at design time):
  > `'Rezultat klasifikacije jednog intake_jobs posla. 1:1 sa intake_jobs u Fazi 1A (nema batch-multi-document
  > logike još).'` — *("...1:1 with intake_jobs in Phase 1A (no batch-multi-document logic yet).")*
  This is the schema's own author-acknowledged confirmation, predating Sprint 003's independent discovery of
  the same gap from the classifier-behavior side. Two independent lines of evidence (schema comment + runtime
  behavior) converge on the same conclusion.
- `predmet_dokazi.stranica`/`.paragraf`/`.start_offset`/`.end_offset` (migration 080) are the only
  location-type columns anywhere near this area, and as shown in §3a they describe a position **within** one
  already-identified document, not a document-count or document-boundary concept.

**Verdict**: **CONFIRMED — no competing implementation, no existing schema hook at all.** Any parent/child or
segment-count concept needs new columns/tables from scratch; there is nothing partially built to extend.

### UI (`static/vindex.js`)

- Smart Intake wizard (Pipeline C) DOES support multi-file selection: `siFilesSelected()` (line 21019),
  `_siAddFiles(fileList)` (lines 21026–21047) loops over a browser `FileList` and stages each into a
  `_siFiles` array (per-file validation: extension allowlist, 25MB size cap), rendered via
  `_siRenderFilesList()` (lines 21049–21059) with individual remove buttons (`siRemoveFile`, line 21061).
- **This is "upload N separate files in one wizard session," not "one file contains N documents."** Each
  staged file is a fully independent physical upload (its own `File` object, its own future `intake_jobs`
  row) — confirmed by the loop structure treating `fileList[i]` as one whole file to be pushed as one
  `{file, filename, status}` entry, with no per-file content inspection at staging time. There is no code path
  anywhere in the reachable JS around this feature that treats "one selected file" as anything other than "one
  document" downstream.

**Verdict**: **CONFIRMED — no existing UI concept of one-file-containing-many-documents.** The multi-file
capability that does exist is orthogonal to this sprint's problem and does not need to change for a
segmentation feature to be added — a segmentation step would sit *after* a single staged file is uploaded,
splitting its extracted text into N logical documents server-side, with the current multi-file UI unaffected
(it would, at most, need to later render "1 file → N detected documents" as an expanded list, a UI change not
yet designed anywhere).

---

## 5. Exact call-site data shape today — all 4 OCR/extraction call sites

All 4 confirmed via `grep -n "extract("` across the relevant files. Every one destructures the identical
3-tuple immediately, with no intermediate structure:

| Pipeline | File:Line | Exact code |
|---|---|---|
| A (sync per-case upload) | `api.py:4164` | `text, is_scanned, ocr_used = await asyncio.to_thread(extract, tmp_path)` |
| A-ephemeral (`/api/dokument/*`) | `routers/dokument.py:199` | `text, is_scanned, ocr_used = await asyncio.to_thread(extract, tmp_path)` |
| B (durable queue worker) | `shared/intake_worker.py:202` | `text, is_scanned, ocr_used = await asyncio.to_thread(self._extract_text, tmp_path)` — where `_extract_text` (line 320–322) is a one-line wrapper: `return extract(path)` |
| C (Smart Intake finalize) | `routers/smart_intake.py:813` | `text, is_scanned, ocr_used = await asyncio.to_thread(extract, tmp_path)` |

**Immediately after, at every site, `text` is treated as one atomic string for the rest of that function's
lifetime** — confirmed by reading each site's following ~20–30 lines:

- **api.py:4164–4199** (Pipeline A): `if not text or not text.strip()` empty check (line 4184) →
  `_detect_doc_type(text)` (line 4191, single call) → `source_meta` dict built with the raw file's
  `source_sha256` (whole-file hash, line 4198) → fed to `chunk_document` as one manifest.
- **routers/dokument.py:199–224**: same `is_scanned` HTTPException branch → `source_meta` built identically
  (whole-file `sha256`, line 221) → (continues to `chunk_document`/`segment_document`, both single-document
  APIs as shown above).
- **shared/intake_worker.py:202–245**: `is_scanned` branch writes a `document_type='other'` row and returns
  early (lines 209–232, exactly ONE `intake_documents` row created either way) → otherwise
  `classification = await self._classify(text)` (line 234, **one classify() call for the whole string**) →
  `entities = await self._extract_entities(text)` (line 235, same) → **exactly one `create_document()` call**
  (line 237) creates **exactly one `intake_documents` row per `intake_jobs` row**, structurally 1:1 by
  construction (matches migration 074's own comment in §4).
- **routers/smart_intake.py:813–828**: `if text and text.strip()` → `source_meta` (whole-file sha256, line
  824) → `manifest = await asyncio.to_thread(chunk_document, text, source_meta)` (line 828) — one manifest,
  one `predmet_dokumenti` link downstream (per Sprint 001's already-documented `INTAKE-003`, the
  `predmet_dokumenti`↔`intake_jobs` FK gap — unrelated but adjacent).

**Verdict for all 4 sites**: **CONFIRMED — no competing implementation, uniform insertion point identified.**
Because all 4 call sites share the exact same destructuring pattern and the exact same library call
(`uploaded_doc.extractor.extract`), a segmentation step has exactly ONE natural insertion point in the shared
library (`uploaded_doc/extractor.py` and/or a new sibling module it calls), not 4 separate call-site patches.
The minimal-surface-area design would be: extend or wrap `extract()`'s return contract (today
`tuple[str, bool, bool]`) so that ALL 4 callers receive whatever new segmentation-relevant data exists, then
have each of the 4 call sites decide independently whether/how to act on it (e.g. Pipeline B might auto-fan-out
into N `intake_documents` rows immediately; Pipeline A's synchronous per-case upload might instead surface a
"we detected 3 documents in this file — confirm?" step, given it's an interactive request/response call, not a
background job).

---

## Summary table

| # | Question | Verdict |
|---|---|---|
| 1 | Extractor page-level access | **CONFIRMED — hook point exists.** `extract_pdf`'s born-digital (line 154–159) and OCR (177–185) paths both build a `list[str]` per page internally; both discard it at the `"\n\n".join(...)` return (lines 166, 187). DOCX/TXT/image have no page concept at all (structural, not a discard — nothing to reuse there). |
| 2 | Chunker as segmentation signal | **CONFIRMED — chunking and segmentation are separate concerns; only the regex-density-threshold *technique* (not chunker's data/output) is reusable.** No page/document-boundary field exists on `UploadedDocChunk`/`ChunkingManifest` (schema.py). |
| 3 | Repo-wide splitting inventory | **Two NEW FINDINGS**: `analiza/segmenter.py` (real, shipped, sub-document structural segmentation — different axis, same head-only single-doc-type assumption as classifiers) and `scripts/ingest_bilten*.py` (real, shipped, true multi-document PDF splitter — for RAG-corpus bulletin ingestion, entirely disconnected from case intake, format-specific splitting signal). Trezor (`klijenti/router.py`) **CONFIRMED — no competing implementation** (no text extraction at all, structurally inapplicable). |
| 4 | Schema/UI multi-doc awareness | **CONFIRMED — none exists.** Migration `074_intake_phase1a.sql:58`'s own comment states "nema batch-multi-document logike još." `static/vindex.js`'s multi-file UI (`_siAddFiles`, line 21026) is "N files," not "1 file, N documents" — orthogonal, unaffected by a future segmentation feature. |
| 5 | Call-site data shape | **CONFIRMED — uniform single insertion point.** All 4 sites (`api.py:4164`, `routers/dokument.py:199`, `shared/intake_worker.py:202`, `routers/smart_intake.py:813`) call the same `extract()` function and destructure the identical `(text, is_scanned, ocr_used)` 3-tuple, immediately treating `text` as one atomic string. A segmentation step belongs in the shared library, not patched 4 times. |

## Design-phase implications (observations, not proposals — no implementation performed)

- Any segmentation mechanism will need to be **format-aware**: PDF has a true per-page signal to build on;
  DOCX/TXT/image do not, and would need a different (structural-marker-based) approach or could be explicitly
  out-of-scope for a first version.
- The term **"segment"** is already a taken, shipped concept (`analiza/segmenter.py`, sub-document
  clauses/sections) — Sprint 005 should pick different vocabulary for "how many physical documents does this
  upload contain" to avoid confusion with the existing Forensic Legal Audit / Evidence Vault feature.
- `scripts/ingest_bilten_v2.py` is proof that a hand-rolled, format-specific splitter is tractable when the
  input format is known and fixed — but is also a cautionary example that this approach doesn't generalize; a
  lawyer's arbitrary "lawsuit + exhibits" combined PDF has no equivalent fixed editorial marker to split on.
- The natural code insertion point is the shared `uploaded_doc/extractor.py`/`extract()` contract, consumed
  identically by all 4 current call sites — meaning a single well-designed change point, not four independent
  patches, though each of the 4 call sites (one interactive/synchronous, three background/async) may
  legitimately want to react to a "multiple documents detected" result differently.

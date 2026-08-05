# Canonical Document Segmentation — Signals + Segment Identity — Program Intake Sprint 005, Fork (2026-08-05)

**Status: DESIGN ONLY, READ-ONLY INVESTIGATION.** No files edited, no migration SQL written (standing convention:
migrations are drafted by whoever implements the change). Scope: Phase 2 (Canonical Segmentation Signals) and
Phase 4 (Segment Identity) of Sprint 005's charter. Genome, Timeline, Deadlines, Tasks, Copilot, Strategy Engine,
Firm Brain, Search are out of scope and were not touched or read.

Builds directly on, and does not re-derive: `docs/architecture/CANONICAL_DOCUMENT_TAXONOMY.md` (Sprint 003, the
10-category Serbian taxonomy), `CONFIDENCE_SPECIFICATION.md` (Sprint 003, the baseline+factors confidence shape and
the never-trust-raw-LLM-self-report governing rule), `REVIEW_QUEUE_SPECIFICATION.md` + `RESUME_WORKFLOW_SPECIFICATION.md`
(Sprint 004, the now-proven end-to-end review/resolve/resume mechanism), `routers/evidence.py::_klasifikuj_dokument`'s
real prompt, `shared/intake_classify.py`'s real `_HEURISTICS`, and `analiza/segmenter.py`'s real code (a naming
collision addressed head-on in §0 below).

## §0. Terminology collision, flagged before anything else

`analiza/segmenter.py` already exists and is already called "Document Segmentation Engine" — but it answers a
**completely different question**. It splits the text of ONE already-identified document into internal
clauses/sections (`Segment`/`SegmentedDocument` dataclasses, `segment_map()`, `to_llm_context()`) purely to give an
LLM addressable chunks for analysis (e.g. `routers/evidence.py::_lociraj_tvrdnju` uses it to resolve which
paragraph a claim falls in). It never decides "is this actually two physically separate documents that got
scanned into one PDF."

Sprint 005's segmentation is the opposite axis: **splitting one uploaded PDF/file into N separate logical
documents at page boundaries**, upstream of classification, before `analiza/segmenter.py` would ever run on any
of the resulting pieces. This is exactly the "same word, two incompatible vocabularies" collision this session's
own memory has repeatedly flagged (Sprint 003 §3.2's `Dokaz`/`predmet_dokazi.kategorija` boundary; Program
Gamma's `GAMMA-010` field-collision finding) — except here it's a naming collision between two pieces of code,
not two data concepts. **Recommendation for whoever implements Phase 3/5**: do not name any new
module/table/function `segment*` without a disambiguating prefix (e.g. `intake_document_boundary_*` or
`intake_split_*`), and do not import or extend `analiza/segmenter.py` for this — it solves a different problem
and its `Segment` dataclass would be a false-cognate trap for the next engineer who greps "segment" in this
codebase. This document itself uses "segment" throughout only because the mission charter uses that word; the
concrete design below is careful to always say "intake_documents row" / "logical document" for the actual object,
not `analiza/segmenter.py`'s `Segment`.

## §1. Phase 2 — Canonical Segmentation Signals

Per-signal format: **pattern** (concrete, checkable) → **strength** (STRONG = can justify a split alone if
found cleanly; CORROBORATING = never sufficient alone) → **false positive** (a worked example of this signal
firing on a document that is NOT actually a boundary) → **mitigation** (how the signal design avoids that FP).

A cross-cutting design rule threaded through every signal below, learned once and applied to all seven:
**position matters more than presence.** `shared/intake_classify.py`'s own `_HEAD_CHARS = 400` window already
encodes this principle for whole-document classification (a keyword in the head of the text is signal; the same
keyword anywhere else in a 50-page document is not run through the heuristic at all). Every positional signal
below (letterhead, case number, appendix numbering) inherits the same discipline, applied per-page instead of
per-document: **a candidate marker counts only when it appears isolated near the top of a page**, not merely
present anywhere on that page. This single rule is what keeps every one of Serbian legal documents' own
self-quoting habits (a rešenje reciting an earlier P.br., an appellate decision quoting the first-instance
letterhead in its "obrazloženje") from generating false splits — quoted material inside prose is, definitionally,
embedded mid-paragraph, not isolated at page-top.

### 1. Promena tipa akta (act-type change)

- **Pattern**: run the exact same heuristic keyword scan `intake_classify.py::classify_heuristic()` already
  performs on a whole document's first 400 characters — but per page, on each page's own first ~400 characters
  — and compare the winning `document_type`/`tip_dokaza` (per Sprint 003's canonical taxonomy, not the old
  12-value vocabulary) between page N and page N+1. A flip (e.g. page 1 hits `sudska_odluka.resenje` via
  "РЕШЕЊЕ", page 6 hits `podnesak.zalba` via "ЖАЛБА"/"ПРИГОВОР") is the signal.
- **Strength**: CORROBORATING only. Per-page text windows are noisier than whole-document ones (less context,
  more `ostalo`/no-hit results), and — see false positive below — the taxonomy's own boilerplate makes bare
  keyword co-occurrence unreliable on its own, exactly why Sprint 003 §1.3 (sudsko poravnanje) and §3.6
  (enforcement split) already established that structural markers must outrank a bare keyword hit for
  *classification*; the same discipline applies here for *segmentation*.
- **False positive**: nearly every rešenje in Serbian civil procedure ends with a "Pouka o pravnom leku" footer:
  *"Protiv ovog rešenja dozvoljena je žalba u roku od 8 dana od dana prijema..."* — this single sentence contains
  "žalba," which a naive per-page scan would read as "a new žalba document started here." It is boilerplate
  INSIDE the one rešenje, not a new document.
- **Mitigation**: only count an act-type flip when the new type's keyword appears isolated at page-top (per the
  cross-cutting rule above) — a "Pouka o pravnom leku" footer is, by definition, at the BOTTOM of the page it
  appears on, in a full sentence, not a standalone heading line. This one positional check eliminates the
  majority of same-document false positives for this signal without needing any new legal knowledge beyond what
  `evidence.py`'s prompt and `intake_classify.py`'s heuristics already encode.

### 2. Novo zaglavlje (new letterhead)

- **Pattern**: a real Serbian court letterhead is a **three-part block**, all co-located at the top of a page:
  (1) "РЕПУБЛИКА СРБИЈА" / "REPUBLIKA SRBIJA"; (2) a court-name-and-level line — "ОСНОВНИ СУД У [grad]" /
  "VIŠI SUD U [grad]" / "APELACIONI SUD U [grad]" / "PRIVREDNI SUD U [grad]" / "VRHOVNI KASACIONI SUD" (the same
  court-level vocabulary already implicit in `evidence.py`'s `ai_tags.sud_organ` field and `analiza/segmenter.py`'s
  own `_PRESUDA_KW`/`_RESENJE_KW` lists — "vrhovni kasacioni sud," "apelacioni sud," "prvostepeni sud"); (3) a
  case-number line near the top — reference-prefix formats like "П. бр. 1234/24," "Гж 567/23," "Рев 89/2024"
  (matching `analiza/segmenter.py`'s own reference-abbreviation vocabulary: "rev.," "gž.," "p.," "iv.," "r.,"
  "kž."). "New letterhead" = this three-part shape recurring at a page OTHER than page 1 — a shape that, in a
  genuine single continuous document, only ever appears once.
- **Strength**: STRONG — arguably the single strongest signal of the seven. A single document's internal
  continuation pages use running headers/page numbers at most; they never repeat the full letterhead block,
  because there is no reason to re-identify the issuing court partway through a document it already issued.
  Finding this shape again, cleanly, at page-top, partway through a scanned PDF is a very reliable indicator of
  a second physically distinct served document.
- **False positive**: an appellate rešenje's "obrazloženje" (reasoning) section routinely reproduces the
  first-instance court's identity while narrating procedural history: *"Prvostepenom presudom Osnovnog suda u
  Novom Sadu, П. 245/22, утврђено је да..."* — this names a court and a case number, but embedded mid-paragraph,
  not as a standalone three-part header block.
- **Mitigation**: require ALL THREE sub-elements ("REPUBLIKA SRBIJA" line, court+level line, case-number line)
  co-located within the first ~2-3 lines immediately after the page-break boundary — not merely present
  somewhere on the page. A quoted reference inside prose will have at most one of the three elements in that
  exact position (the court name, embedded in a sentence, not preceded by "REPUBLIKA SRBIJA" on its own line
  immediately above it). This directly reuses this signal's own defining shape as its own false-positive filter.

### 3. Novi broj predmeta (new case number)

- **Pattern**: same Serbian case-number formats as above (prefix abbreviation + number/year), detected as a
  STANDALONE line, differing from the case number already captured for page 1 (or from `predmet.tip`'s known
  case reference, when available via the case-type-prior mechanism CONFIDENCE_SPECIFICATION §2 already
  describes — degrading gracefully to "absent" the same way, since Pipeline B is document-first and a case may
  not exist yet).
- **Strength**: STRONG **only when co-occurring with a new letterhead at the same boundary** (§decision rule
  below). ALONE, it is CORROBORATING ONLY — a single ongoing dispute legitimately accumulates MULTIPLE distinct
  reference numbers across its own lifecycle (a first-instance case P.123/23 is assigned a NEW appellate number
  Gž.45/24 on appeal, describing the exact same underlying dispute). A bare case-number change, without a new
  letterhead, is at least as consistent with "same matter, next procedural stage, still one legitimately-bundled
  scan" as it is with "new document."
- **False positive**: the exact procedural-history recitation from signal #2's false positive also serves here —
  *"Rešenjem Osnovnog suda u Novom Sadu P.1234/22 od 14.3.2023 ... po žalbi tuženog zavedenoj pod Gž.567/23..."*
  cites TWO case numbers in one paragraph of ONE document.
- **Mitigation**: identical positional requirement — a case number counts only when isolated on its own line at
  page-top (the structural convention Serbian court documents actually use: the case number as a standalone
  header line, typically near the letterhead), never when recited inline within a sentence of running prose.

### 4. Novi potpisni blok (new signature block)

- **Pattern**: Serbian legal-document closing formulas — a judge's name + signature line ("судија" / "sudija"),
  a "ПОУКА О ПРАВНОМ ЛЕКУ" section, a "Dostaviti:" distribution list, a notary stamp reference for punomoćje
  ("Overeno kod javnog beležnika," "OPU/UPP broj"), or an advokat's signature block ("Advokat, [Ime Prezime],"
  "adv. legitimacija broj"). A signature block appearing mid-document (not at the tail end of the whole
  extracted text) followed immediately by a NEW heading/letterhead on the next page is a boundary marker —
  documents close with signature blocks once, at their true end.
- **Strength**: STRONG CORROBORATING, not sufficient alone. Standalone, a signature block just marks "an ending"
  — which could equally be the natural end of the ONE document followed by legitimately-attached exhibits/proof
  of service that are part of the SAME filing, not a new document. Its real value is CONFIRMING a boundary a
  structural signal on the following page already suggests (signature-block-end-of-page-N + [letterhead OR
  case-number]-start-of-page-N+1 is a strong combined signal).
- **False positive**: a punomoćje is routinely attached as its own short annex to a tužba/podnesak — it carries
  its own complete signature+notarization block, but is legitimately part of the SAME upload a lawyer
  intentionally scanned as one bundle (cover letter + tužba + punomoćje, one PDF, by design). Whether this
  should split into 2 logical documents or stay one filing bundle is a genuine judgment call, not a
  false-positive to eliminate — flagged explicitly in §2 as a case that should ROUTE TO REVIEW rather than
  silently auto-split, since punomoćje is Sprint 003's own top-level taxonomy category and both outcomes
  (split / keep-together) are defensible.

### 5. Novi sud (new court)

- **Pattern**: the court-name/level token specifically changing between pages (page 1: "ОСНОВНИ СУД У
  БЕОГРАДУ"; a later page: "ВИШИ СУД У БЕОГРАДУ," or a different city's court entirely) — a subset of signal #2.
- **Strength/recommendation**: **fold into signal #2 (novo zaglavlje) as a sub-check, not a fully independent
  8th signal.** The mission names it separately, but scoring it independently would double-count the exact same
  underlying textual evidence the letterhead check already consumes — precisely the failure mode
  CONFIDENCE_SPECIFICATION §3 warns against ("never blend... without preserving which ones fired," which cuts
  both ways: also never double-count one fact as two signals). Concretely: `signals_used.new_letterhead` should
  carry which specific court+level token was captured (`{"found": true, "page": 4, "court": "Viši sud u
  Beogradu"}`), so a lawyer/auditor can see WHICH court changed without a second signal entry duplicating the
  same page-4 evidence.
- **False positive / mitigation**: identical to signal #2 (a lower court named inline in an appellate
  "obrazloženje" without the full structural block).

### 6. Novi učesnici (new parties)

- **Pattern**: Serbian party-role labels are structurally fixed — "тужилац"/"tužilac" (plaintiff),
  "тужени"/"tuženi" (defendant), "предлагач"/"predlagač" (petitioner), "противник предлагача"/"protivnik
  predlagača" (respondent), "извршни поверилац"/"izvršni poverilac," "извршни дужник"/"izvršni dužnik" (matching
  `analiza/segmenter.py`'s own `_RESENJE_KW` vocabulary). A caption naming entirely different people/entities
  under these same role-labels, at a later page, versus the parties already captured in `evidence.py`'s own
  `ai_tags.stranke` for page 1.
- **Strength**: CORROBORATING ONLY, genuinely weak alone. Multi-defendant litigation legitimately discusses each
  co-defendant's specific liability in sequence within ONE judgment, naming different people per subsection
  without being separate documents. Documents also routinely name OTHER proceedings' parties when citing
  precedent or a related case. Requires a structural signal (letterhead/case-number) at the same boundary before
  contributing meaningfully to a split decision.
- **False positive**: any discussion of a "povezan predmet" (related case) or witness testimony naming
  third parties who are not part of the document's own caption.

### 7. Nova numeracija priloga (new appendix/attachment numbering)

- **Pattern**: Serbian filings enumerate attachments explicitly — "Прилог 1:," "Prilog br. 1," "У прилогу
  достављамо:," numbered exhibit lists ("Dokaz br. 1 - ..."). A RESTART of this running numbering (Prilog 1
  reappearing after Prilog 5 was already seen earlier in the same file) signals a boundary — or marks the start
  of the referenced attachment itself (pages under "Prilog 3" ARE a contract copy attached as evidence) — which
  is exactly the multi-document-bundle case this sprint exists to detect.
- **Strength**: CORROBORATING, moderate. The restart-to-1 pattern is fairly specific and rarely accidental, but
  alone it doesn't supply the resulting piece's own document type — the classifier still has to run on whatever
  starts there regardless.
- **False positive**: a cover podnesak that merely LISTS its attachments inline in prose (*"uz ovaj podnesak
  dostavljamo: 1) punomoćje, 2) izvod iz registra, 3) dokaz o uplati takse"*) without any actual restart of a
  running header/footer numbering scheme — a list, not a structural numbering restart.
- **Mitigation**: same positional discipline as every signal above — count "Prilog N" only when found as an
  isolated page-level header/footer marker, not inline within a paragraph.

### Additional signals found grounded in real Serbian legal-document structure, beyond the mission's 7

- **8. Page-count-footer discontinuity ("Strana X od Y").** Serbian court documents commonly footer-stamp
  "Strana X od Y." If page N reads "Strana 5 od 5" (the declared last page of a 5-page document) and page N+1
  reads "Strana 1 od 3" (declared first page of a NEW, different-length document), this is a purely mechanical,
  language-and-content-independent signal. **STRONG on its own when cleanly found** — a genuine single
  document's own X-of-Y sequence is monotonic by construction, so a reset is essentially unambiguous. Caveat:
  treat with more caution when `ocr_used=True` (a misread digit, e.g. "8" read as "3," is a data-quality risk,
  not a false-positive-by-design risk) and with full confidence when the source has a native text layer
  (`ocr_used=False`).
- **9. Near-blank page as physical separator.** A mostly-blank page (fax cover sheet, a blank divider between
  physically stapled originals) between two content pages. CORROBORATING only — some legitimate documents have
  genuinely blank pages by design ("ova strana je namerno ostavljena prazna"). Useful only alongside a
  structural signal on the immediately following page.

## §2. The combination rule — when to actually split

Per CONFIDENCE_SPECIFICATION's own established discipline: **never blend signals into one undifferentiated
score.** Every signal that fires at a given page-to-page boundary is recorded with its own strength tier
(STRONG or CORROBORATING) and identity (which one, on which page) — never collapsed into a single number before
a decision is made.

For a specific boundary candidate (a page transition where at least one signal fired):

| Condition at that boundary | Outcome |
|---|---|
| 2+ STRONG signals agree (e.g. new letterhead AND new case number both fire) | **AUTO-SPLIT** |
| 1 STRONG signal + at least 1 CORROBORATING signal agreeing | **AUTO-SPLIT** |
| Exactly 1 STRONG signal, zero corroboration | **ROUTE TO REVIEW** |
| 2+ CORROBORATING signals agree, no STRONG signal | **ROUTE TO REVIEW** |
| 1 lone CORROBORATING signal, nothing else | **KEEP AS ONE** (too thin to even escalate) |
| Nothing fires | **KEEP AS ONE** (the default, unmarked case) |

**Why review, not silent keep-as-one, for the ambiguous middle band**: the mission's conservatism mandate
("nikada ne podeli PDF pogrešno kada nema dovoljno dokaza") cuts in both directions. A wrongful SPLIT produces
two broken/incomplete case files out of one real document — genuine data damage, hard to notice, hard to undo
cleanly. A wrongful "keep as one" when a split was warranted is comparatively cheap: a lawyer notices the bundle
still looks mixed and re-uploads/splits manually later — recoverable, low-cost, no silent damage. Given this
asymmetry, the design leans toward **never auto-splitting on thin evidence**, but it must not silently swallow
real-but-insufficient evidence either — when there IS a real signal that isn't yet strong enough to trust
blindly (the two "ROUTE TO REVIEW" rows), the honest answer is to surface it to a human, not to pick silently
in either direction.

**Reuse, don't reinvent, Sprint 004's now-proven review/resume mechanism.** Concretely: create the review-queue
entry at the WHOLE-job level exactly as today (`intake_review_queue.intake_job_id`, `document_id` pointing at
the not-yet-split job's single `intake_documents` row), with a NEW 4th deterministic reason value —
`segmentation_uncertain` — added to the existing exactly-3-value CHECK-constraint vocabulary
(`ocr_failed | classification_uncertain | low_confidence_extraction | segmentation_uncertain`, a design note for
whoever drafts the migration, not SQL here). This surfaces on the exact same Step 3 review screen that Sprint 004
already made reachable end-to-end (`RESUME_WORKFLOW_SPECIFICATION.md` §1's "reuse the existing gate, don't build
a new one" principle, applied one level up: reuse the existing QUEUE, don't build a new one).

**One honest gap to flag, not solve here**: Sprint 004's `resolve_review_queue_for_job()` resolves **every**
unresolved review-queue row for a job in one call (`UPDATE ... WHERE intake_job_id = ? AND resolved_at IS NULL`,
confirmed in `shared/intake_documents.py`/`RESUME_WORKFLOW_SPECIFICATION.md` §3). Once a job can carry several
segments each with their own independent low-confidence classification, a lawyer resolving ONE ambiguous
boundary with a single job-level "resolve" call would also silently mark any OTHER unrelated low-confidence
segment issue on the same job as resolved, without the lawyer having looked at it. This is a real, scoped
question for whoever implements Phase 3/5 — either add row-scoped (`document_id`-level) resolution, or
explicitly accept job-level granularity for v1 and document the limitation. Not resolved here; flagging it is
this fork's job, not fixing it (out of scope — Phase 3/5, not Phase 2/4).

**Also flagged, not solved**: reusing the review-queue *row* mechanism does not mean the existing correction UI
is ready for this. Sprint 004's UI corrects field VALUES (an entity, a document type). A segmentation-uncertain
escalation asks a fundamentally different question — "where, if anywhere, should this be split?" — which likely
needs a page-image boundary picker, not a text-field correction control. Reusing the escalation plumbing is
correct; assuming the existing correction screen already handles this interaction is not — real new frontend
surface for whoever implements this.

## §3. Phase 4 — Segment Identity

### The unifying frame: "no split" is segment count N=1, not a special case

The cleanest design treats the *common, unsplit* case as simply the N=1 instance of the general N-segment case,
not a separately-branching code path. A job that never triggers any signal still gets exactly one
`intake_documents` row, with `segment_order=1`, `start_page=1`, `end_page=<total pages>`,
`segmentation_reason='single_document'`. Every existing row (created before this sprint ships) backfills to this
same value. This means no downstream consumer needs an "if segmented / else" branch for the ordinary case — it
already IS a segment, of which there happens to be exactly one.

### Fields every segment carries

| Field | Shape | Notes |
|---|---|---|
| `id` | existing `intake_documents.id` UUID PK | unchanged |
| parent job | existing `intake_documents.intake_job_id` FK | unchanged — already the right relationship (see §4) |
| `segment_order` | NEW, INTEGER NOT NULL, 1-indexed | position among siblings sharing the same `intake_job_id`; 1-indexed to match how it will be *displayed* to a lawyer ("Segment 2 od 3") and how Serbian court documents themselves 1-index their own "Strana X od Y" footers |
| `start_page` / `end_page` | NEW, INTEGER NOT NULL, 1-indexed, inclusive | matches natural lawyer page references and PDF-viewer 1-indexing |
| `segmentation_reason` | NEW, TEXT, fixed vocabulary, CHECK-constrained (design note) | proposed values: `single_document` (default/common case), `new_letterhead`, `new_case_number`, `new_signature_block_and_heading`, `page_reset`, `combined_signals` (2+ signals fired, no single dominant reason), `manual_split` (human-drawn during review resolution) — mirrors `intake_review_queue.reason`'s exactly-3-value discipline, extended to a comparably small fixed set, not free text |
| `segmentation_confidence` | NEW, NUMERIC | independently scored, reusing Sprint 003's `baseline + Σ(factor adjustments)` shape, **never blended with `classification_confidence`** — a segment boundary can be very confidently drawn while the resulting piece's TYPE is still uncertain, or vice versa; these are two different questions (WHERE vs WHAT), exactly extending Sprint 003's own "parent and subtype get independent confidence, never blended" principle one level further up |
| `segmentation_method` | NEW, TEXT tag | mirrors `classification_method`'s existing `heuristic \| llm` shape: `deterministic` (signals matched via regex/structural checks, no LLM call — the default and, per this design, the ONLY method proposed for v1), `manual` (human-drawn during review). **No `llm_assisted` value is being proposed for v1** — running an LLM judgment per page-boundary candidate across a whole document would be expensive, and per CONFIDENCE_SPECIFICATION's own governing constraint, less trustworthy than the structural/keyword signals already available; the space is reserved in the vocabulary for future work, not built now |
| `segmentation_signals_used` | NEW, JSONB | mirrors the exact `signals_used` structured shape CONFIDENCE_SPECIFICATION §5 already established for classification — keeps WHICH signals fired, at which page, at what strength, visible downstream, never collapsed into one opaque score. E.g. `{"new_letterhead": {"found": true, "page": 4, "court": "Viši sud u Beogradu"}, "new_case_number": {"found": true, "page": 4, "value": "Гж 118/24"}, "act_type_change": null, "page_reset": null}` |
| correlation ID | **not a new column — see §5** | reasoned through separately below, deliberately not folded into the table shape |

### §4. Table shape — extend `intake_documents`, do not create a new table

**Recommendation: no new table.** `intake_documents` already IS "one row = one logical document's classification
result" — exactly the granularity a segment needs.

**The schema already permits this, today, with zero migration for the relationship itself.**
`intake_documents.intake_job_id` (migration 074) carries **no UNIQUE constraint** — the "1:1 with intake_jobs"
rule is a comment/convention (`COMMENT ON TABLE ... 'Rezultat klasifikacije jednog intake_jobs posla. 1:1 sa
intake_jobs u Fazi 1A (nema batch-multi-document logike još)'`), not a database-enforced invariant. The ONE
concrete place that operationally enforces 1:1 today is `shared/intake_documents.py::get_job_result()`, which
calls `supa.table("intake_documents").select("*").eq("intake_job_id", intake_job_id).maybe_single().execute()` —
Supabase/PostgREST's `.maybe_single()` requires 0 or 1 matching rows and errors on more. This is the single,
identified call site that would need to change (to a plain list-returning `.execute()`, ordered by
`segment_order`) — a bounded code change, not a schema migration, and not something this read-only investigation
implements.

**Why the one-to-many analogy the mission points to is exactly right, and already proven in this schema.**
`extracted_entities.document_id` → `intake_documents.id` is already a genuine, unconstrained one-to-many FK — N
entity rows per document, no uniqueness assumption anywhere. Once a segment gets its own `intake_documents.id`,
entity extraction requires **zero schema change** — it already scopes correctly to whichever document
(segment) row is passed as `document_id`. Same for `intake_review_queue`, which already carries both
`intake_job_id` (required) AND `document_id` (nullable) — per-segment review escalation already has a place to
live without any schema change: a low-confidence classification on segment 2 of 3 creates a row with
`document_id = segment_2's intake_documents.id`, exactly mirroring today's single-document flow.

**Why `intake_jobs` should NOT change shape — no "1 parent job + N child segment-jobs."** Every column on
`intake_jobs` (`content_sha256`, `storage_path`, `idempotency_key`, `attempts`/`max_attempts`/`next_retry_at`/
`claimed_at`, the whole `claim_intake_job`/`complete_intake_job`/`fail_intake_job` atomic-RPC and reaper
machinery from migration 073) governs the lifecycle of **one physically uploaded blob** — decrypting it, OCR'ing
it, retrying if that fails. Segmentation is a purely logical subdivision that only becomes meaningful AFTER OCR
has already succeeded on the whole blob — there is no such thing as "OCR failed for segment 2," because segments
do not exist as addressable objects until after the one shared OCR/extraction pass over the whole file completes.
Forking `intake_jobs` into N child jobs per upload would duplicate the entire retry/claim/reap machinery for
segments that never independently retry anything — no benefit, real cost (every consumer of `intake_jobs.status`
as "the" job state, e.g. `intake_queue_metrics`, `_tick()`, `finalize_intake_job`'s status gate, would need to be
taught about a parent/child distinction it has no actual use for).

**Why not a brand-new `intake_segments` table, kept distinct from `intake_documents`?** Considered and rejected.
It would force every existing downstream consumer of `intake_documents`+`extracted_entities` (classification
confidence read paths, entity extraction, review-queue creation, `finalize_intake_job`'s case-creation logic) to
learn a NEW join (segment → document) that carries zero information beyond what `segment_order`/`start_page`/
`end_page`/`segmentation_reason` express directly as columns on `intake_documents` itself. That would recreate
precisely the "two tables quietly answering almost the same question" pattern this session's own memory has
already flagged as a mistake to avoid (`REVIEW_QUEUE_SPECIFICATION.md` §3's `staging_memory` boundary decision;
Sprint 003 §3.2's `Dokaz`/`predmet_dokazi.kategorija` collision) — **except that in those cases there genuinely
was a different question being asked** (input-confidence vs. draft-approval; document-type vs. evidentiary-role).
Here there is not: "which document is this" and "which segment is this" are the *same* question once a segment
IS a document. A separate table would only be justified if a segment needed to exist as an object BEFORE
classification — e.g. a purely geometric page-range with no type yet — but every one of the seven-plus signals
above is already entangled with classification-adjacent evidence (act-type change, letterhead, case number), so
segmentation and classification are decided together, at the same processing step, about the same object. One
row per logical document remains correct.

**Concrete downstream consequence, flagged and NOT solved here** (future implementation work for Phase 3/5, not
a schema question): `get_job_result()`'s single-document return shape, the Step 3 review screen's implicit "the
document" framing, and `finalize_intake_job`'s case-creation logic all currently assume exactly one
`intake_documents` row per job. Making the relationship genuinely 1:N requires touching these three identified
call sites. This is real, bounded work — but it is work, not a design gap; naming it here so it isn't
rediscovered from scratch when Phase 3/5 starts.

### §5. Correlation ID — inherit by default is the platform's own rule, but a segment's own AI calls should branch, exactly as the platform's own precedent already allows

**How correlation IDs actually work in this codebase today** (`shared/ai_provenance.py`, Mission Ledger,
2026-08-03): a correlation_id is set ONCE per HTTP request (`set_request_context`, at the two auth choke
points), and every AI call/audit/event write inherits it by default via `case_context()` — *unless* a
sub-operation explicitly asks for its own (`case_context(correlation_id=...)`), which the module's own docstring
names as an intentional, already-used escape hatch: `api.py`'s parallel procena/hronologija/metapodaci calls
each keep their own id today. The join key is persisted on `events` and `audit_immutable` (migration 090,
"Ledger Correlation ID") — **not** on `intake_jobs`/`intake_documents`/`extracted_entities`, none of which carry
a `correlation_id` column today. Confirmed by grep: no `case_context()`/`correlation_id` reference exists
anywhere in `shared/intake_classify.py`, `shared/intake_extract.py`, or `shared/intake_worker.py` today — Pipeline
B's classification/extraction calls currently run with no explicit case-level correlation context at all (a
pre-existing gap, out of scope to fix here, but relevant context for reasoning about what "inherit" would even
mean for this pipeline right now).

**Recommendation: each segment should mint its own correlation_id when its own downstream processing begins,
via `case_context(correlation_id=new_correlation_id(), document_id=<segment's intake_documents.id>, ...)` —
exactly the codebase's own already-established pattern for "multiple independent AI operations sharing one
request/job."** Reasoning: once a job produces N segments, each segment becomes its own independent downstream
processing unit — its own classification LLM call (if the heuristic doesn't hit), its own entity-extraction
calls, its own potential review-queue escalation, and eventually its own `predmet` (case) at finalize time. This
is structurally identical to the `api.py` parallel-calls case the module's own docstring already names as the
correct use of the override — the only difference is these "parallel calls" happen sequentially across segments
of one job rather than concurrently within one request, which does not change the reasoning: each is an
independently-meaningful operation deserving its own traceable id, not artificially yoked to the others just
because they share a physical upload.

**Why this does not break Sprint 004's continuity, and why no `correlation_id` column is needed on
`intake_documents` at all.** Sprint 004 proved continuity for the case where ONE request/job maps to ONE
traceable operation end-to-end — segmentation does not touch that guarantee, because the join key that actually
threads "which segment does this event/audit row belong to" is not correlation_id in the first place, it is
`document_id` (already a first-class column on `events`' payload usage pattern and directly on `intake_documents`
itself) combined with the always-present `intake_job_id` FK back to the parent upload. Correlation_id's job is
narrower and different: "which single AI/audit operation is this," not "which document/upload does this belong
to." `intake_documents` doesn't carry a correlation_id column TODAY either (classification_confidence has never
needed one) — the durable link back to the parent upload is, and remains, the `intake_job_id` FK, which every
segment already carries unchanged. Recovering "what was the parent upload's own correlation_id" (if one exists at
all, given the pipeline gap noted above) remains a query over `events`/`audit_immutable` keyed by
`intake_job_id`, exactly as it works today for the single-document case — segmentation adds rows to that same
query, it does not change how the query works.

## §6. Self-skepticism check (required by the mission charter)

- **If a new table were the right call, extending `intake_documents` would need to be rejected — it isn't.** A
  new table is the correct answer exactly when two genuinely different questions are being asked about
  co-existing objects (as `staging_memory` vs. `intake_review_queue` correctly remain separate, per Sprint 004's
  own analysis). Here, "which document" and "which segment" collapse into one question the moment a segment
  is classified — which happens at the very same processing step every one of this design's own signals
  operates at. The one scenario that WOULD justify a separate table — a segment existing as a bare page-range
  object before any classification attempt — does not arise, because every signal above is itself
  classification-adjacent (act-type, letterhead, case number all directly overlap what the classifier already
  looks at).
- **If correlation IDs should stay purely inherited (never branch per segment), this design would be wrong —
  it isn't, because the codebase's own docstring already names the branching case as legitimate and in active
  use** (`api.py`'s parallel analysis calls). Segmentation is the same shape of problem (multiple independently-
  meaningful AI operations under one enclosing request/job), not a new shape requiring new justification.
  What WOULD be wrong is adding a `correlation_id` column to `intake_documents` itself to "store" this — that
  conflates a per-operation tracing concept with a per-object identity concept; the design above deliberately
  keeps them separate, using the FK chain (`intake_job_id`) for object identity and the ambient contextvar
  (persisted only on `events`/`audit_immutable`, as today) for operation tracing.
- **Where this design is most likely to be wrong in practice, flagged honestly**: (a) the per-page heuristic
  scan in signal #1 assumes page-boundary-aware text is available at segmentation time — today `extract_pdf()`
  (`uploaded_doc/extractor.py`) builds a `pages: list[str]` internally but **returns only the flattened, joined
  string** (`"\n\n".join(pages)`) to its caller; supporting any of these page-anchored signals requires changing
  `extract_pdf`'s/`extract_image`'s return contract to also expose page boundaries (offsets into the joined text,
  or the raw per-page list) — a real, identified, non-trivial prerequisite for Phase 3, not solved here. (b) The
  job-level-only granularity of `resolve_review_queue_for_job()` (§2 above) is a genuine rough edge this design
  surfaces but does not resolve. Both are named so Phase 3/5 does not have to rediscover them.

## §7. Explicit scope confirmation

Genome, Timeline, Deadlines, Tasks, Copilot, Strategy Engine, Firm Brain, and Search were not read, referenced,
or designed against in this document. No file was edited. No migration SQL was written — every schema change
described above (`segment_order`, `start_page`, `end_page`, `segmentation_reason`, `segmentation_confidence`,
`segmentation_method`, `segmentation_signals_used` columns on `intake_documents`; the 4th `intake_review_queue`
CHECK value `segmentation_uncertain`) is a design note for whoever drafts that migration, per this repo's
standing convention.

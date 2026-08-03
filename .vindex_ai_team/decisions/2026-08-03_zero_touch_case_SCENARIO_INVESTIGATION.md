# Zero-Touch Case — Scenario & Gap Investigation

**Mission:** Operation Autonomous Law Office (BETA-002), Steps 4/8/9. Read-only investigation, no
code changes. Scope: 6 areas not already covered by Night Shift or Lawyer Zero, plus a dedicated
Scenario B check. All findings below are file:line grounded.

---

## HEADLINE FINDING (not one of the original 6 items — found while investigating Scenario B)

**Smart Intake has no frontend entry point. A lawyer cannot reach it today.**

Exhaustive search of every frontend file in the repo (`static/*.js`, all root `*.html`, no other
frontend framework present) for `smart-intake` / `smart_intake` / `SmartIntake`: **zero matches**,
case-insensitive, across `.js/.html/.jsx/.ts/.tsx/.vue`.

What the UI actually calls for uploads (`static/vindex.js`):
- `/api/dokument/upload` (lines 8874, 20378) — the older *session-based Q&A upload*, explicitly
  documented in `smart_intake.py`'s own header comment as a different, synchronous feature.
- `/api/predmeti/{id}/upload` (line 19402) — the older *per-case* upload path (writes the
  `"[Auto-analiza]"` `predmet_istorija` marker `services/case_pipeline.py` step 1 checks, per LZ-002).

Neither calls `POST /api/smart-intake/documents` or `POST /api/smart-intake/jobs/{id}/finalize`.

**Why this matters for BETA-002 specifically:** the founder's "Zero-Touch Case" journey (Steps 3-6:
upload → OCR/classify/extract in one call → auto-organized case) structurally matches Smart Intake's
job/finalize model, not either upload path the UI actually calls. Every fix this session
(`LZ-001`, `LZ-002`, parts of the Night Shift wave) wired *downstream* signal quality onto a pipeline
whose *front door* a lawyer cannot open from the product today. This is the single largest gap found
in this investigation — bigger than any individual scenario issue below, because it means Scenario
A-G below are currently only reachable via direct API call (e.g. Postman, or a test), not by an
actual lawyer using the app.

**Not a "connect existing wiring" fix** — this is a founder-relevant product decision (which upload
path is meant to be primary going forward, and whether the existing two paths get deprecated or kept
alongside Smart Intake) more than a single engineering task, flagged here rather than guessed at.

---

## 1. ZIP file support

**Verdict: does not exist, on any upload path.**

Searched for `zipfile`/`.zip`/`ZIP_DEFLATED`/`is_zipfile` (case-insensitive) across the whole repo.
The only hits are `routers/data_export.py` (an *export* feature — bundles a lawyer's own data into a
zip for download, unrelated to intake) plus doc/config files. No upload endpoint
(`/api/smart-intake/documents`, `/api/dokument/upload`, `/api/predmeti/{id}/upload`) has any zip
handling. A lawyer uploading a `.zip` of scanned documents today would have it treated as a single
opaque binary file and almost certainly fail whatever MIME/extension check gates each endpoint (not
verified per-endpoint, but no code path exists to unpack it regardless).

## 2. Language detection

**Verdict: does not exist beyond OCR's own fixed language-pack fallback — no per-document content
detection, no stored language field anywhere.**

`uploaded_doc/extractor.py::_detect_ocr_lang()` (lines 123-139) is the only "language" logic in the
document pipeline. It does not inspect document content at all — it calls
`pytesseract.get_languages(config="")` to see which Tesseract language packs are *installed on the
server*, then always returns a fixed combined string (`"srp+srp_latn+eng"` if both Serbian packs are
present, degrading gracefully to `"eng"` otherwise). This same combined string is used for every OCR
call regardless of the actual document's language — it works by feeding Tesseract all candidate
alphabets at once, not by detecting which one applies. Confirmed no `jezik` (language) field exists
anywhere in `shared/` (searched `shared/intake_extract.py` and the broader `shared/` tree
specifically) — no document or entity ever has a detected/stored language value. A non-Serbian,
non-English document (e.g. a foreign judgment attached as evidence) would be OCR'd with the wrong
language model and silently produce degraded text, with no signal anywhere that this happened.

## 3. Scale behavior — Scenario B (10-file batch) and Scenario G (hundreds of documents)

### Scenario B — CONFIRMED SERIOUS, directly undermines BETA-002's core promise
`routers/smart_intake.py::finalize_intake_job` (line 364) operates on exactly one `job_id` and
**always inserts a new `predmeti` row** (line 444-455) unless that specific job was already
finalized before (the only idempotency check is `job.predmet_id` already being set, line 391-392).
`FinalizeReq` (line 333-336) has exactly three fields — `naziv`, `klijent_strana`,
`klijent_ime_override` — **no `predmet_id` or any other "attach to an existing case" parameter
exists**. There is structurally no way, via this API, to finalize a second document into the same
case a first document just created.

Consequence: a lawyer uploading 10 pages of one client's case (Scenario B) — which, given the
job-per-file batch upload contract (line 99: "202 + job_id po fajlu"), the frontend would call
finalize on one job at a time — gets **10 separate `predmeti` rows**, not 1 organized case. Each of
those 10 finalize calls also independently fires its own Genome background refresh, deadline sync,
Evidence Vault classification, and Pinecone ingest (see Scenario F below) — meaning the platform does
roughly 10x the per-case automation work, fragmented across 10 case records the lawyer must now
manually notice and consolidate.

**No case-merge/consolidation feature exists** to recover from this after the fact — searched for
`spoji_predmet`/`merge_predmet`/`consolidat*` across the repo; no dedicated endpoint or service found.

This is very likely the most consequential single finding for BETA-002's stated mission success
criterion ("uploads documents, gets one organized case").

### Scenario G — CONFIRMED, different shape than hypothesized
Hypothesis going in was "expensive O(n) reprocessing on large cases." Actual finding is more
specific and arguably worse: **`_GENOME_MAX_DOCS = 25`** (`routers/case_dna.py:198`). Both
`_run_genome_background` (line 618) and
`refresh_case_dna` (line 748) query `predmet_dokumenti` `.order("redni_broj").limit(_GENOME_MAX_DOCS)`
— ordered by **upload order**, not importance/recency. For a case with hundreds of documents, only
the **first 25 ever uploaded** are ever considered by Case Genome — document #30, #100, #300 (which
could be the final judgment, a critical piece of evidence, anything) is silently invisible to Genome
forever, with no warning to the lawyer that this truncation is happening. This is a silent-cap
problem, not a performance problem — cheaper to fix (surface the cap, or bias selection toward
recency/type) but currently entirely undocumented in the product.

## 4. Scenario F — documents uploaded days apart (staleness / concurrency)

**Verdict: no debounce anywhere; a real (if narrow) race condition exists on concurrent triggers,
though days-apart timing itself is not a staleness risk — same-window concurrent uploads are.**

Confirmed via grep of every `_run_genome_background`/`_genome_bg` call site (`api.py:4342`,
`routers/rocista.py:177`, `routers/smart_intake.py:619`) and `services/ambient_analyzer.py`'s comment
(the only debounce concept in the codebase, unrelated to Genome) — there is no debounce, queueing, or
coalescing on Genome refresh anywhere. Each trigger independently does a full read-modify-write:
load `case_dna`, recompute from scratch via an LLM call, `verzija = stari_verzija + 1`, write back.

For Scenario F specifically (days apart), this is actually *fine* — each new upload correctly
triggers a fresh, complete recompute, so there's no staleness in the sense of "Genome not
reflecting a days-old document." The real risk is **concurrent** triggers (which Scenario B's batch
upload — or any two uploads happening within the same processing window — would produce): two
`_run_genome_background` calls can both read the same `stari_verzija`, both compute
`stari_verzija + 1`, and whichever write lands last wins — the other's Genome history entry
(`_save_genome_history`, called before the update) is preserved, but the `case_dna` update itself can
be silently overwritten, and one of the two triggering documents' contribution to Genome could be
lost from the *current* state until the next trigger fires (self-healing on the next upload, but a
real window of incorrect data in between).

## 5. Conflict-check timing gap

**Verdict: confirmed real — no automatic conflict check exists anywhere in the document-first
(Smart Intake) flow.**

`POST /api/intake/conflict-check` (`routers/intake.py:397`) is the only conflict-check endpoint in
the repo (confirmed via `tests/test_conflict_check.py`, `tests/test_intake_conflict_check.py`,
`routers/conflict_check.py` also exists as a supporting module). It requires manually-supplied
`novi_klijent_ime` / `novi_klijent_faktura` / `protivna_strana` (lines 390-394) — i.e. it belongs to
the **older, name-first CRM Intake Wizard** (`routers/intake.py`, per that router's own header
comment distinguishing it from Smart Intake), where a lawyer types a client/opposing-party name
*before* any case exists.

`routers/smart_intake.py` (the document-first flow) has **zero references** to conflict-check,
anywhere. Structurally there is no natural moment for it to run automatically: party names aren't
known until after AI extraction completes (`entities`/`value_map` in `finalize_intake_job`), and
`finalize_intake_job` itself never calls the conflict-check logic even though it already has
extracted `plaintiff`/`defendant` values in `value_map` (lines 411-414) at exactly the point it would
be needed — a case gets created with no conflict check ever having run, silently, every time.

## 6. Duplicate-logic sweep

**Verdict: no unexpected third AI-chronology-extraction mechanism found. 13 total writers to
`predmet_hronologija` confirmed, but 11 of the 13 (beyond the two already known) are single-event
lifecycle writers, not competing extraction systems — expected, not duplicate logic.**

Full writer list found (`grep "predmet_hronologija\").insert"`, whole repo):
`api.py` (x2 — one is the older upload path's own entry, one is a different single-event write),
`services/case_pipeline.py`, `routers/case_dna.py` (Genome's own `_sync_rokovi_to_hronologija`),
`routers/copilot.py`, `routers/intake.py` (x3 — the AI-extraction path, already known),
`routers/onboarding.py`, `routers/predmeti_close.py`, `routers/rokovi_lanac.py` (the deadline-chain
calculator, already known), `routers/rocista.py` (hearing scheduling), `routers/smart_intake.py`,
`routers/ugovor_zastupanja.py` (contract representation). Each of the "new" ones (onboarding, case
closure, hearing scheduling, contract representation, copilot) writes a single specific lifecycle
event of its own domain (e.g. "case closed on X date"), not a competing document-chronology-extraction
pipeline — this is expected fan-out into a shared timeline table, not the kind of duplicate logic
Step 9 is looking for. No third OCR invocation path, no second embeddings/Pinecone-ingest
implementation, and no second Evidence Vault classifier were found either (the three-mechanism
document-analysis landscape from `LZ-002`'s investigation remains complete and accurate).

The 4-LLM-analysis-per-document landscape from `LZ-002` (Smart Intake classifier, Evidence Vault
classifier, Genome, older upload path's "procena") is unchanged by this investigation and remains
best characterized as intentional layering (each serves a genuinely different consumer), not
accidental duplication — reconfirmed, not re-investigated in depth here since `LZ-002` already
covered it.

---

## Summary table

| # | Area | Verdict | Severity |
|---|---|---|---|
| — | Smart Intake has no frontend entry point | Confirmed, not previously known | **Critical — reframes the whole mission** |
| 1 | ZIP support | Does not exist | Medium (Scenario C/D adjacent, not currently blocking) |
| 2 | Language detection | Does not exist (fixed OCR fallback only, no content detection, no stored field) | Medium |
| 3a | Scenario B (batch → 1 case) | Confirmed serious — creates N predmeti, not 1, no merge feature exists | **Critical — breaks core promise** |
| 3b | Scenario G (hundreds of docs) | Confirmed — silent 25-doc cap, ordered by upload order not importance | High |
| 4 | Scenario F / concurrency | No staleness risk from days-apart timing; real but narrow race condition on concurrent triggers | Medium |
| 5 | Conflict-check timing gap | Confirmed — never runs automatically in the document-first flow, despite extracted party names being available at finalize time | High |
| 6 | Duplicate-logic sweep | No new duplication found; 13 chronology writers confirmed all legitimate single-purpose | None — clean |

All items above are findings only, no implementation attempted, per this investigation's scope.

# Bojan Workflow Gap Analysis — 2026-08-02

**Target:** the one vertical workflow — Novi klijent → Kreiranje predmeta → Upload dokumenata → OCR
+ ekstrakcija → Automatsko popunjavanje predmeta → Generisanje hronologije → Identifikacija rokova →
Kreiranje obaveza → AI pregled predmeta.
**Method:** every status below is verified against actual current code (file:line), not against
prior memory/session summaries, several of which have previously turned out stale in this project.
Where a claim can only be confirmed live (production data, not code), that is stated explicitly.

---

## Phase 1 — Intelligent Intake

| Capability | Status | Evidence | Priority | Complexity |
|---|---|---|---|---|
| Client creation (basic fields) | ✅ | `klijenti/router.py` — full CRUD, encrypted PII fields (JMBG/pasoš/PIB), works today. | Sprint 1 | — (done) |
| Client creation (pravno lice / zastupnici / povezani subjekti) | 🟡 | `klijenti/router.py` has `tip` field distinguishing `fizicko_lice` (seen at `routers/smart_intake.py:459`); no evidence found of a `zastupnik`/representative or linked-entity structure in the CRM schema. | Sprint 1 | Medium |
| Case creation with AI assistance (free-text → structured proposal) | ✅ | `routers/intake.py:136-157` (`POST /api/intake/ekstrakcija`) — GPT-4o-mini takes free-text problem description, returns `predlog_naziva_predmeta`, `protivna_strana`, `vrsta_spora`, `vrednost_spora`, `prvi_rok`, `rok_opis`, `potrebni_dokumenti`. This is close to exactly the founder's worked example. Confirmed the model is explicitly instructed never to invent a deadline (`prvi_rok = null osim ako... EKSPLICITNO naveden`, `:49`). | Sprint 1 | — (done) |
| Case creation from natural free text + auto-created client + docs + deadline + billing, one call | ✅ | `routers/intake.py:160-350` (`POST /api/intake/kreiraj`) — creates `predmeti` row, links client via `predmet_klijenti`, adds a `predmet_hronologija` deadline row if `prvi_rok` present, links pre-uploaded docs, optionally creates a billing entry. This is a materially complete implementation of Phase 0's target flow's first 3-4 steps in one endpoint. | Sprint 1 | — (done) |
| Case creation via pre-built templates (7 case types with pre-populated deadline chronology) | ✅ | `routers/intake.py:574-797` — 7 templates (naknada štete, radni spor, razvod, krivično, privredno, upravno, izvršenje), each with a pre-defined `hronologija_predlozi` list inserted as relative-dated `predmet_hronologija` rows on creation. | Sprint 1 | — (done) |
| Document upload — PDF | ✅ | `uploaded_doc/extractor.py:220`; `api.py:4131` (`_ALLOWED_SUFFIXES = {".pdf", ".docx", ".doc"}` for the main upload path). | Sprint 1/2 | — (done) |
| Document upload — Word (.docx) | ✅ | `uploaded_doc/extractor.py:222`. | Sprint 1/2 | — (done) |
| Document upload — Word (.doc, legacy) | ❌ (known bug, not newly found) | `api.py:4131` lists `.doc` as accepted, but `uploaded_doc/extractor.py` has no `.doc` handler (confirmed by grep — only `.pdf`/`.docx` branches at lines 220/222) — this matches the already-tracked SEC-028 finding: accepted suffix, unhandled extractor, produces an unhandled 500 rather than a clean error. | Sprint 2 | Trivial (fix the mismatch) |
| Document upload — images/scanned photos (.jpg/.png) | ❌ | `api.py:4131`'s `_ALLOWED_SUFFIXES` set has no image extensions. `routers/smart_intake.py`'s own upload endpoint (`:80-158`) performs **no suffix/content-type validation at all** — it accepts any file, up to 25MB, and hands it to the same PDF/DOCX-only extractor downstream. A photographed document (a very common lawyer intake case — a client photographing a served decision) is not a supported input today on either upload path. | Sprint 1/2 | Medium (needs an image→PDF/OCR preprocessing step, e.g. Tesseract/Vision on raw images, not just PDF-embedded-scan OCR) |
| Upload pipeline: async, non-blocking (202 + job_id, background processing) | ✅ | `routers/smart_intake.py:80-158` — returns 202 immediately per file, actual OCR/classification/extraction happens in `shared/intake_worker.py` via a Postgres-backed queue (`shared/intake_queue.py`). This is a genuinely production-grade async pipeline design, not a stub. | Sprint 1/2 | — (done) |
| OCR (scanned PDF) | ✅ | `uploaded_doc/extractor.py` returns `(text, is_scanned, ocr_used)` — confirmed consumed at `routers/smart_intake.py:517` and surfaced back to the caller (`routers/smart_intake.py:201`, `dokument.ocr_koriscen`). | Sprint 1/2 | — (done) |
| Automatic document classification (type, confidence) | ✅ | `shared/intake_classify.py:57-133` — hybrid: regex/keyword heuristic first (auditable), LLM fallback, returns `{document_type, confidence, method}`. Confirmed wired end-to-end into the job-status endpoint (`routers/smart_intake.py:199-200`). This is real, not aspirational. | Sprint 1/2 | — (done) |
| Automatic entity extraction (case_number, judge, parties, court, deadline, amount, law) | ✅ | `shared/intake_extract.py:36-39` — 8 entity types, hybrid regex-first (for structured fields like case_number/amount) + LLM (for free-text fields like judge/parties), each with its own per-field confidence (Confidence Graph), explicitly fail-soft (an unfound field is a low-confidence entity in a review queue, never silently dropped — `:13-15`). | Sprint 1/2 | — (done) |
| **Automatic case-field population from extracted entities → real predmet, one confirm click** | ✅ | `routers/smart_intake.py:344-636` (`POST /api/smart-intake/jobs/{id}/finalize`) — this is the exact "Automatsko popunjavanje predmeta" step in Phase 0's target flow. Confirmed it: names the case from extracted plaintiff/defendant or case number (`:400-410`), creates or reuses a client (`:437-478`), inserts a single deadline chronology row if a deadline was extracted (`:482-500`), decrypts/chunks/embeds the source document into Pinecone and links it via `predmet_dokumenti` (`:502-591`), and fires a Case Genome background refresh (`:593-602`). This single endpoint is materially the entire Phase 0 target flow, already wired end-to-end. | Sprint 1/2 | — (done, see caveats below) |

**Caveats found on the "already have this" claim for Phase 1** (per the explicit instruction to flag
where the founder's own assumption may not hold):

1. **`predmet_klijenti` has no `user_id` column — confirmed still true in the current schema**, not
   just a past-session memory. `migrations/002_klijenti_crm.sql:130-138` is the only migration
   touching this table's columns and adds `uloga_klijenta`/`napomena`/`kreirano` — never `user_id`.
   `routers/smart_intake.py:464-471`'s own comment confirms this is a live, known issue: the *old*
   wizard (`routers/intake.py:194-202`, `:740-747`, `:877-884` — three separate call sites) still
   sends `user_id` on every `predmet_klijenti` insert, which fails silently (`PGRST204`, caught by a
   bare `except Exception: logger.warning(...)`) — meaning **every client-to-case link created via
   the old `/api/intake/kreiraj`, `/api/intake/from-template`, and `/api/intake/bulk-import` paths
   has been silently failing to persist**, for as long as those endpoints have been live. The new
   Smart Intake finalize path (`routers/smart_intake.py:472-478`) was written *specifically to omit*
   `user_id` and therefore does work. **This is not a hypothetical risk — it is a live, currently
   uncorrected bug in 3 of the app's intake code paths, confirmed by reading the current code, not by
   trusting the memory note that first found it.** Recommend either adding the column (compatible
   fix) or removing `user_id` from the three old call sites — both are small, but this should not be
   assumed already fixed.
2. Document upload accepts no image formats on either upload path — this will surface immediately in
   real lawyer use, since photographing a served document with a phone is an extremely common way
   evidence actually arrives.

---

## Phase 2 — Automatic Case Organization

| Capability | Status | Evidence | Priority | Complexity |
|---|---|---|---|---|
| AI document classification with metadata (type/date/court/related case) | ✅ (for Smart Intake path only) | Same evidence as Phase 1's classification/extraction rows — this is real for documents that go through `/api/smart-intake/documents`. | Sprint 2 | — (done for that path) |
| Document classification tied to the *older* upload paths (`/api/dokument/upload`, the main predmet-attached upload in `api.py`) | 🟡/❌ | No evidence found of the same classify/extract pipeline being invoked from `api.py`'s older document-upload code path — Smart Intake is described in its own file header (`routers/smart_intake.py:19-25`) as a **deliberately separate, parallel path**, not a replacement. A document uploaded the "old" way does not get automatic type/date/court extraction. | Sprint 2 | Medium (route old uploads through the same classify/extract pipeline, or make Smart Intake the single upload path) |
| Automatic chronology *generation from document content* (e.g., extracting multiple dated events from a document's text and inserting them as chronology rows) | ❌ | Found only **one** chronology row auto-inserted per finalize — the extracted `deadline` entity, as a single generic "Rok — {tip}" event (`routers/smart_intake.py:482-500`). No code path was found that extracts multiple dated events (filing date, response date, hearing date, etc.) from a document's full text and inserts them as separate chronology entries. The founder's own example ("12.01.2026 Podneta tužba / 15.02.2026 Primljen odgovor / 03.03.2026 Zakazano ročište") is not produced automatically anywhere found. | Sprint 3 | Large — needs a new multi-event extraction prompt/pipeline, not a small addition to the existing single-deadline extraction |
| Timeline as a real, working aggregated case view | ✅ | `routers/intelligence_timeline.py:56-80+` (`GET /api/predmeti/{id}/intelligence-timeline`) — a genuinely working, already-shipped feature (Core Consolidation §1.6, 2026-07-22) that aggregates 6 sources (predmet creation, `predmet_hronologija`, document uploads, AI analyses, Genome refreshes, and the immutable audit log) into one sorted chronological feed with icons/colors/formatted dates. This is real and running. | Sprint 3 | — (done) |
| Timeline populated with rich, multi-event, document-derived history (not just "predmet opened" + manually/template-added events) | 🟡 | The aggregator (above) is sound, but its *inputs* are thin per the row above — without automatic multi-event extraction, most of what appears in the timeline for a document-heavy case is upload events and template-seeded deadlines, not a narrative built from document content. The founder's "predmet kao priča, ne folder sa 200 fajlova" goal is **structurally supported** by `intelligence_timeline.py` but **not yet delivered**, because the richest possible input (multi-event chronology extraction) doesn't exist yet. | Sprint 3 | Same as the row above — this is the same gap, viewed from the UI side |

---

## Phase 3 — Deadlines and Obligations

| Capability | Status | Evidence | Priority | Complexity |
|---|---|---|---|---|
| Deadline extraction from a single document's text | ✅ (narrow) | `shared/intake_extract.py` reuses the existing `uploaded_doc/deadline_parser.py` for the `deadline` entity type (per its own header comment, `:8-9`); confirmed wired into finalize (`routers/smart_intake.py:296-310, 482-500`), including a real, test-driven bugfix (Serbian `DD.MM.YYYY` vs. ISO date format mismatch, documented at `:296-301`, found by an actual end-to-end test — a good sign of engineering rigor on this specific piece). | Sprint 1/3 | — (done, narrow) |
| **AI Deadline Engine**, per the founder's fuller description — propose a structured obligation (naziv/datum/prioritet) from deadline language found anywhere in a document, for lawyer confirmation | 🟡 | What exists is narrower than described: exactly **one** deadline per document is extracted and inserted directly as a chronology row with a fixed label ("Rok — {tip_labela}") and a fixed importance ("važan") — there is no lawyer-facing proposal/confirm step (it's inserted automatically on finalize, not proposed-then-confirmed), no `prioritet`-style field distinct from `vaznost`, and no handling for a document containing multiple distinct deadlines (e.g. "8 dana za žalbu, 30 dana za izvršenje"). | Sprint 3 | Medium — extends existing, working infrastructure rather than building new |
| Deadline **chain** computation (e.g., filing date → statutory response/appeal windows, with business-day/holiday adjustment) | ✅ (separate, manual-trigger feature) | `routers/rokovi_lanac.py:290-391` — a real, working feature: given an event type and a start date, computes a full chain of downstream legal deadlines with weekend/holiday adjustment (`_je_neradan`, `_adjust_for_weekend_holiday`, `:322-336`). This is **more sophisticated** than the founder's simple example, but it is **manually triggered** (lawyer picks event type + date) — it is not yet connected to the automatic deadline-extraction-from-document piperiline above. | Sprint 3 | Small — the two already-working pieces (extraction, chain computation) need to be connected, not built from scratch |
| Reminder system — dashboard | 🟡/✅ (likely, not directly re-verified in this pass) | `predmet_hronologija` rows (which deadlines populate) feed `intelligence_timeline.py` and are referenced across many routers (`routers/dashboard.py`, `routers/kalendar.py` found in the earlier grep sweep) — a dashboard-level deadline view very likely exists given this many consumers, but this specific pass did not open `routers/dashboard.py`/`routers/kalendar.py` to confirm the exact UI surfacing; flagged as not independently re-verified rather than assumed. | Sprint 3 | Unknown — needs direct verification before assuming done |
| Reminder system — email | Not verified in this pass | `routers/email_notif.py` exists (seen in the earlier grep sweep, referenced elsewhere in this project's security docs re: a routing collision, SEC-002) — presence confirmed, but whether it actually fires *for approaching deadlines specifically* (vs. other notification types) was not opened/verified in this pass. | Sprint 3 | Unknown — needs direct verification |

---

## Phase 4 — AI Case Assistant

| Capability | Status | Evidence | Priority | Complexity |
|---|---|---|---|---|
| "Razumi moj predmet" — sažetak | ✅ | Case Genome's `zakljucak` field (`routers/case_dna.py:125`) — "2-3 rečenice, šta advokat mora znati pre svega ostalog." | Sprint 4 | — (done) |
| — činjenice | ✅ | `pravna_teorija` block (`:52-59`) + `datumi_kljucni` (`:77-79`). | Sprint 4 | — (done) |
| — dokazi | ✅ | `dokazi_rang` (`:101-104`) — ranked evidence with a strength score, star rating, and reasoning per document. | Sprint 4 | — (done) |
| — sporne tačke | ✅ | `kontradikcije` (`:83-85`) — explicit contradiction detection with severity and source locations. | Sprint 4 | — (done) |
| — rizici | ✅ | `najslabija_tacka` (`:105-109`) + `upozorenja` (`:123`) — a single named weakest point with a criticality score and recommendation, plus a general warnings list. | Sprint 4 | — (done) |
| — sledeći koraci | ✅ | `strategija` block (`:110-118`) — primary goal, fallback plan, and scenario-based counter-responses. | Sprint 4 | — (done) |
| — nedostajuća dokumenta | ✅ | `nedostaje` (`:119-121`) — named missing document/evidence, urgency, and why it matters. | Sprint 4 | — (done) |
| Genome actually reflects the case's real documents, not stale/disconnected state | 🟡 (caveat, not re-verified live) | The Genome prompt itself is comprehensive and well-designed — **the concern is not the prompt, it's the pipeline feeding it**, per an already-recorded 2026-07-21 forensic finding (memory: "7/9 event types dead, Case Pipeline never auto-fires, zero connection to Firm DNA/Learning/Confidence/matter_intel risk"). This pass did **not** re-verify whether that finding still holds — `routers/case_dna.py`'s own header comment (`:6-14`) is itself mid-correction of a previously false docstring claim ("all AI functions read Genome" was found untrue the same day by a forensic audit; corrected to note only Evidence Vault now flows in as of that fix), which is a live signal that this subsystem has a documented history of documentation overclaiming actual wiring. **This should be directly re-verified before Sprint 4 is scoped**, not assumed either fixed or still broken. | Sprint 4 | Unknown until re-verified — could be Small (already fixed) or Large (still disconnected) |
| Refresh trigger — automatic after new document ingestion | ✅ | Confirmed at least for the Smart Intake finalize path: `routers/smart_intake.py:593-602` fires `_run_genome_background` 3 seconds after a document is linked. | Sprint 4 | — (done, for this one path) |

---

## Phase 5 — Court Workflow (explicitly lowest priority)

Not investigated in depth in this pass, per the founder's own framing (not urgent). Grep sweep found
no dedicated "ročišta/zapisnici/priprema pitanja" feature files beyond `routers/hearing_cc.py` and
`routers/rocista.py` (both present, neither opened) — gap size is therefore **unknown but likely
non-trivial**, consistent with the founder's own expectation that this phase comes later.

---

## Recommendation — what Sprint 1 should concretely consist of

**The founder's instinct that "we may not be starting from zero" is correct, and in fact stronger
than the founder's own framing assumed.** Phase 1's core flow (client → AI-assisted case creation →
document upload → OCR → classification → extraction → automatic case population, one-click finalize)
is **already built and wired end-to-end** via `routers/intake.py` + `routers/smart_intake.py`. This
is not a 20%-done stub; `finalize_intake_job` alone implements most of what a "Sprint 1: Intake Core"
would otherwise need to build from scratch.

**Given that, Sprint 1 should not be "build intake" — it should be:**

1. **Fix the confirmed-live `predmet_klijenti.user_id` bug** in the 3 old-wizard call sites
   (`routers/intake.py:194-202, 740-747, 877-884`) — trivial, but currently silently breaking every
   client-case link created through those 3 endpoints specifically (not the newer Smart Intake path).
2. **Unify or explicitly bridge the two parallel intake systems** (`routers/intake.py`'s
   AI-extraction-then-manual-confirm flow vs. `routers/smart_intake.py`'s upload-first-then-finalize
   flow) — both are real and working, but a lawyer's actual "new case" experience today likely
   depends on which UI entry point they use, and the founder's single target vertical flow implies
   these should converge into one, not remain two independently-maintained paths.
3. **Add image upload support** (`.jpg`/`.png` at minimum) to at least the Smart Intake path — this
   is a near-certain real-world blocker (photographed documents), not a nice-to-have, and is
   currently missing entirely rather than partially done.
4. **Fix the `.doc` accept/extractor mismatch** (`api.py:4131` vs. `uploaded_doc/extractor.py`) —
   trivial, already tracked as SEC-028.

**Sprint 2 (Document Intelligence)** is mostly about **connecting what already exists** rather than
building new: route the older upload path through the same classify/extract pipeline Smart Intake
already has, rather than maintaining two document-handling code paths with different capabilities.

**Sprint 3 (Timeline + Deadlines)** is where genuinely new work is needed: the timeline
*aggregator* (`intelligence_timeline.py`) is done and good; what's missing is **multi-event
chronology extraction** from document text (currently only a single deadline is extracted per
document) and **connecting** the existing deadline-chain calculator (`rokovi_lanac.py`, sophisticated
and already built) to the existing single-deadline extraction (`intake_extract.py`) — two solid
pieces that aren't wired together yet.

**Sprint 4 (AI Case Intelligence)** should start with **re-verifying Case Genome's actual current
wiring** before assuming it's ready to be the answer to "Razumi moj predmet" — the prompt design
already produces every field the founder asked for, but this subsystem has a specific, documented
history (same day, 2026-07-21/22) of its own documentation overclaiming what was actually connected,
and that history was not re-checked in this pass.

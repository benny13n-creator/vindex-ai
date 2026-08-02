# Beta Critical Path — 2026-08-02

**What this is:** not a feature list. The founder's own framing: *"Koje korisničke scenarije advokat
mora da može da završi bez greške na dan beta lansiranja?"* Nine scenarios, each verified against
actual current code (building on the Bojan Workflow Gap Analysis and Mission 001, plus 2 new checks
this document adds — search and export, not previously covered). If all nine work end to end, beta
has a real shot regardless of how many other features exist or don't.

**Method, unchanged from prior documents this mission:** every status below is grounded in file:line
evidence, not memory or docstring claims. Where something needs live/production verification beyond
what code alone can confirm, that is stated explicitly.

---

## The 9 scenarios

| # | Scenario | Status | Evidence | Blocks beta? |
|---|---|---|---|---|
| 1 | Kreirati klijenta | ✅ | `klijenti/router.py` — full CRUD, encrypted PII, in production today. | No — done. |
| 2 | Kreirati predmet | ✅ | Two working entry points, confirmed **not duplicates** — see `decisions/2026-08-02_intake_convergence_DECISION_RECORD.md`: description-first (`routers/intake.py`) and document-first (`routers/smart_intake.py`'s finalize). Mission 001 (2026-08-02) fixed the client-link persistence bug on both paths. | No — done, and just hardened. |
| 3 | Uploadovati PDF ili fotografiju | 🟡 | PDF: ✅ (`uploaded_doc/extractor.py`). Photo (`.jpg`/`.png`): ❌ — no image extensions accepted on either upload path (`api.py:4131`'s `_ALLOWED_SUFFIXES`; `smart_intake.py`'s upload endpoint does no suffix validation at all, so an image is silently accepted then fails downstream at the PDF/DOCX-only extractor). | **Yes.** Already flagged as the #1 real-world blocker (a client photographing a served document is an ordinary intake case, not an edge case). |
| 4 | Dobiti OCR | ✅ | `uploaded_doc/extractor.py` returns `(text, is_scanned, ocr_used)`, wired end to end into Smart Intake's job status. Works for scanned PDFs. | No, for the PDF case. Directly gated by #3 for the photo case — OCR itself works, but nothing reaches it for an image file today. |
| 5 | Dobiti AI analizu | 🟡 | Case Genome (`routers/case_dna.py`) produces every field the founder asked for (summary/facts/evidence/contested points/risks/next steps/missing documents) — the prompt is not the gap. **Not re-verified this pass**: a 2026-07-21 forensic finding recorded "7/9 event types dead, Case Pipeline never auto-fires" for this same subsystem, and `case_dna.py`'s own header comment (`:6-14`) is itself mid-correction of a prior docstring overclaim found the same day. Confirmed still true as of this document: **this has not been re-checked since**, so treat as unknown, not as fixed or broken. | **Possibly — needs re-verification before it can be marked safe.** This is the single highest-leverage unknown on this list: if Genome's live wiring is still degraded, scenario 5 silently fails for real users regardless of how good the prompt is. |
| 6 | Videti hronologiju | 🟡 | The aggregator (`routers/intelligence_timeline.py`, Core Consolidation §1.6) is real, working, and pulls from 6 real sources. What feeds it is thin: only **one** deadline gets extracted per document today; no code path extracts multiple dated events (filing/response/hearing) from a document's full text. A document-heavy case shows upload events and template-seeded deadlines, not the narrative the founder described. | **Partially.** The *view* won't break; the *content* won't yet feel like "an assistant wrote my case's story," which is specifically the value this scenario is meant to deliver. |
| 7 | Dobiti rokove | 🟡 | One deadline is extracted per document and inserted directly (no propose/confirm step, no handling for multiple deadlines in one document). A separately-built, more sophisticated deadline-**chain** calculator (`routers/rokovi_lanac.py`) exists and works but is **not connected** to the extraction pipeline — a small wiring job, not new development. | **Partially** — a single, correct deadline reaches the case; the fuller "AI Deadline Engine" experience the founder described does not exist yet. |
| 8 | Pronaći predmet | 🟡 (**new finding, not previously checked**) | `routers/search.py` — a real, working global search across `predmeti`, `klijenti`, `uploaded_documents`, billing, and `hronologija` (`.ilike` search, `_search_predmeti`/`_search_klijenti`/`_search_dokumenti` etc., `:38-95`+). **But it searches the wrong document table for this mission's own flow**: `_search_dokumenti` (`:78-95`) queries `uploaded_documents.extracted_text` — confirmed, independently, in an earlier pass this same session (Route Security Model work). Smart Intake's finalize endpoint links documents into **`predmet_dokumenti`** instead (`smart_intake.py:502-591`), a different table. **Consequence: full-text search does not reach documents ingested through the exact intake flow this whole mission just confirmed is the primary, working case-creation path.** A lawyer searching for a case by something only mentioned in an uploaded document's text — the single most natural way to "find a case" months later — will not find it if that document came in via Smart Intake. | **Yes, and this was invisible until this document.** Worth flagging precisely because it's the kind of gap that doesn't show up in a workflow walkthrough (search still returns *something* for case name/client name matches) but fails exactly the scenario the founder listed. |
| 9 | Izvesti dokument | ✅ | `services/predmet_pdf.py` (implied by test coverage) — 18 passing tests in `tests/test_predmet_pdf.py` covering non-empty output, all section combinations, special characters, auth requirement, 404 handling, filename generation. This is a genuinely well-tested, solid feature. | No — done. |

---

## What this means for sequencing, stated directly

**Confirmed blockers, in order of how directly they're felt:**
1. **#3 (image upload)** — already correctly identified as first priority. Unchanged.
2. **#8 (document search table mismatch)** — new finding from this document. Small-to-Medium fix
   (extend `_search_dokumenti` to also query `predmet_dokumenti.tekst_sadrzaj`, or — better,
   consistent with this project's Core Consolidation principle of "1 concept = 1 owner" — resolve
   *why* two document tables exist for what the user experiences as one concept, the same kind of
   question this mission just asked about the two intake systems, before patching search to cover
   both). Recommend a short, scoped investigation before the fix, not a blind extension of the
   search query.
3. **#5 (Case Genome live wiring)** — unknown severity until re-verified. This should happen
   **before** any further AI Case Intelligence work, not after, since it's the foundation scenario 5
   depends on entirely.
4. **#6/#7 (chronology and deadlines)** — both real but thin; already correctly sequenced as
   Sprint 3-scope, genuinely new work (multi-event extraction) plus one small wiring job (the
   deadline-chain connection).

**Not blockers — confirmed solid:** #1, #2 (just hardened by Mission 001), #4 (for the PDF case),
#9.

**Recommended immediate next steps, in order:**
1. Ship image upload (#3) — already agreed.
2. Re-verify Case Genome's actual live wiring (#5) — cheap to check, high-leverage to know before
   committing further AI Case Intelligence work on top of an uncertain foundation.
3. Investigate and fix the document-search table mismatch (#8) — newly found, real, and invisible
   without this document.
4. Then Sprint 3 (#6/#7) as already planned.

This ordering keeps the mission's own stated discipline — close gaps between what exists, don't
build parallel new systems — applied to the two things this document found that weren't visible from
the original gap analysis alone.

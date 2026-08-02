# Mission Review — M-003: Search Table Mismatch

**Mission Board entry:** `MISSION_BOARD.md`, M-003, priority 3.
**Executed by:** Autonomous Night Shift (founder's Master Prompt v1.0), 2026-08-02.
**Status:** DONE.

---

## Architecture Decision

### Root cause — worse than originally described, and the codebase already knew it
`docs/product/BETA_CRITICAL_PATH_2026-08-02.md` found that `routers/search.py`'s document search
queried `uploaded_documents.extracted_text` while Smart Intake links documents into a different
table, `predmet_dokumenti`. This mission verified that directly, and found it goes further:
**`uploaded_documents` is a confirmed-dead table.** Its own migration
(`migrations/057_active_orphaned_tables.sql:22-25`) states this in writing:

> *"uploaded_documents — samo se čita (routers/search.py), nigde se ne upisuje u kodu — verovatno
> mrtva grana pretrage (dokumenti idu u predmet_dokumenti), ali dodata za konzistentnost i da ne
> baca 500."*

Translated: created only to stop a 500 error on an already-dead search branch — the table was known,
in writing, to never receive a row from any code path, at the time it was added. Verified independently
(repo-wide grep for `.insert(`/`.upsert(` against `uploaded_documents`): **zero writers.** This
document search branch has never returned a real result for any document, through any upload path,
at any point since — not a regression introduced by Smart Intake, a pre-existing dead branch Smart
Intake's arrival made newly consequential (per the Beta Critical Path scenario it blocks).

`predmet_dokumenti.tekst_sadrzaj` is, by contrast, confirmed as the real, canonical, heavily-used
document-text column: read by `case_dna.py` (×3 sites), `evidence.py`, `case_commander.py`,
`drafting.py`, `evidence_graph.py`, `multi_agent.py`, `zakon_monitoring.py`, `api.py` — the actual
storage every AI/analysis feature already depends on.

### Alternatives considered
- **Query both tables (union).** Rejected — `uploaded_documents` cannot return a real result under
  any current code path; querying it adds a network round-trip for zero value. Consistent with this
  project's Core Consolidation principle (1 concept = 1 owner) — `predmet_dokumenti` is already the
  single real owner of case-document content.
- **Fix at the schema level (drop `uploaded_documents`).** Rejected for this mission — dropping a
  table is a migration decision requiring founder review per this project's standing rule, and is out
  of scope for a search-query fix; flagged below as a separate, optional tech-debt item.

### Security review
No change to RLS/ownership pattern — `predmet_dokumenti` already has its own `user_id` column and
the query still filters `.eq("user_id", uid)` exactly as the original code did against
`uploaded_documents`. No new exposure.

---

## Implementation
`routers/search.py::_search_dokumenti` — query target changed from `uploaded_documents` to
`predmet_dokumenti`; `.or_()` filter changed from `naziv_fajla,extracted_text` to
`naziv_fajla,tekst_sadrzaj`; preview text now shows a snippet of the actual document content
(falling back to `status` if no text is available yet, e.g. mid-OCR).

---

## QA Report

### User Scenario Test
```
Scenario: a lawyer searches for a case using a phrase that only appears inside
a document's content, where that document was ingested through Smart Intake.
1. Document uploaded via POST /api/smart-intake/documents, OCR'd/extracted,
   linked into predmet_dokumenti.tekst_sadrzaj by finalize (Mission 001 area
   of code, unchanged by this mission).
2. Lawyer later searches GET /api/search?q=<phrase from the document text>.
3. Before this fix: 0 results from the "dokumenti" branch, always, for any
   document (uploaded_documents has never had a row).
4. After this fix: the document is found, previewed with a snippet of its
   actual content.

PASS -- tests/test_search.py::test_search_finds_document_by_content_from_smart_intake_path
```

### Regression suite
27/27 `test_search.py` tests pass (24 pre-existing + 3 new); 32/32 across the broader
search/predmet_dokumenti sweep. Zero regressions.

### Rollback strategy
Pure application code, one query target changed, no schema/migration. Revert the diff to return to
today's (broken) status quo.

---

## Lessons Learned
The codebase's own migration history had already diagnosed this exact defect, in writing, at the
table's creation — and it was never acted on, because "the search branch doesn't 500" reads as
success when the actual failure (zero real results) produces no visible error. This is the same
"declared vs. verified" pattern from earlier this session's security work, recurring in product code:
a comment correctly identifying a dead code path is not the same as the dead code path being fixed.
**Recommendation, non-blocking, for a future tech-debt mission:** consider dropping `uploaded_documents`
entirely (founder migration decision required) — every current reader is now redirected, and no
writer has ever existed.

## Founder Summary
Global document search now actually reaches real document content (Beta Critical Path scenario #8,
"Pronaći predmet"). The root cause was worse than the triggering document suspected: the old query
target has never once returned a document result for anyone, confirmed by the codebase's own
migration comment written at the table's creation. Fixed by pointing at the real table
(`predmet_dokumenti`), not by adding a second, permanently-empty query. 27 tests green, 3 new,
zero regressions. Local commit only, not pushed.

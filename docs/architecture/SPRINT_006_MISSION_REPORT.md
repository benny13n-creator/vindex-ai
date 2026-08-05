# Mission Report — Program Intake Sprint 006 (2026-08-05)
## "Canonical Case Assimilation"

Per this sprint's own required deliverable shape: Pronađeno / Popravljeno / Kanonizovano / Odloženo. Full
technical detail in the companion documents
(`CANONICAL_CASE_ASSIMILATION_ARCHITECTURE_REPORT.md` and siblings); this report is the founder-facing
summary.

---

## Pronađeno (Found)

1. **`predmeti` had no structured case-number column at all**, and no mechanism anywhere in the repo could
   recognize that an incoming document's case number matches an already-open case. Every non-interactive
   intake either required an explicit `predmet_id` or unconditionally created a new case.
2. **A live client-name-matching bug**: `finalize_intake_job` compared a full "First Last" extracted name
   against `klijenti.ime` (first-name-only), with `.limit(1)` and no disambiguation — a query that could
   essentially never match a real two-word name correctly, and which would have silently picked an arbitrary
   client the one time it over-matched.
3. **Zero audit/provenance calls for document-into-case registration** in Pipeline C, unlike Pipeline A's
   per-case upload.
4. **No lineage FK from `predmet_dokumenti` back to `intake_jobs`/`intake_documents`/`intake_job_segments`**
   — Sprint 001's `INTAKE-003` gap, still open.
5. **A confirmed false-success bug**: the case-creation response returned `ok: True` unconditionally, never
   checking whether the document actually linked — a case could be created/attached and marked finalized
   while containing zero of its source documents.
6. **A structural incompatibility with Sprint 005's own multi-segment output**: `finalize_intake_job` and
   `GET /jobs/{job_id}` both still called the single-document `get_job_result()`, whose `.maybe_single()`
   would raise on any job Sprint 005 segmented into 2+ documents — and even without the crash, only one of N
   segments would ever have been assimilated.

## Popravljeno (Fixed)

1. **Content-based case auto-attach**, added `predmeti.broj_predmeta` (migration 094) — an extracted case
   number exact-matching exactly one existing case now auto-attaches instead of always creating a duplicate;
   2+ matches never guess, routing to an explicit, actionable 409 instead.
2. **Client ownership resolution rebuilt correctly** (`shared/case_assimilation.py::resolve_client_ownership`)
   — full-name comparison (not first-name-only), never auto-links between 2+ same-name candidates (surfaced
   as `klijent_nesiguran`/`klijent_kandidati` in the response instead), correctly splits person names and
   detects company names for the right target column.
3. **`finalize_intake_job` rewritten from a single-document function into a per-document loop** —
   `intake_documents.get_job_documents()` (new, list-returning, never `.maybe_single()`) replaces the crash-
   prone single-document fetch; every document Sprint 005 produced is now correctly assimilated, each with
   its own try/except (Phase 5 isolation — one document's failure never blocks or loses its siblings).
4. **Audit + provenance closed for document registration**: every successfully-linked document now runs
   inside `case_context()` and writes a `document_assimilated` audit entry — reusing the existing, proven
   primitives from Missions Atlas/Ledger, not a new mechanism.
5. **Lineage FK added** (`predmet_dokumenti.source_intake_job_segment_id`, migration 094) with a DB-enforced
   UNIQUE constraint (Evidence Integrity: a segment can produce at most one case-document row, ever).
6. **The false-success bug fixed honestly**: the response now reports `dokumenata_povezano`/`dokumenata_
   ukupno` as real per-document counts, and a total failure (0 of N) is logged at ERROR level.
7. **A genuinely multi-case bundle is detected and blocked**: 2+ documents in one upload carrying different
   extracted case numbers never gets silently assimilated under whichever document was read first — the
   whole finalize call is blocked with an explicit error naming the conflicting numbers.
8. **`GET /jobs/{job_id}` fixed for segmented jobs**: now uses the same list-safe `get_job_documents()`,
   additively exposing a full `dokumenti` list alongside the backward-compatible single-document fields.
9. **A real bug found and fixed during this sprint's own test-writing**: `looks_like_company()`'s first
   implementation replaced dots with spaces before tokenizing a party name, which shattered "d.o.o." into
   meaningless single-letter tokens that never matched — fixed to strip dots per-token instead.

## Kanonizovano (Canonicalized)

- **One single Ownership Resolution authority** (`shared/case_assimilation.py`) for both case and client
  matching — not a second parallel matcher, and not scattered inline logic re-derived per pipeline.
- **One single assimilation pipeline** — every document (1 for the common case, N for a segmented job) now
  passes through the identical per-document loop; no alternative code path for the multi-document case.
- **One lineage mechanism**, reusing Sprint 005's own `intake_job_segments` identity model rather than
  building a parallel lineage table — the same "one owner per concern" discipline Sprint 005 itself used.

## Odloženo (Deferred, with reasoning)

Full detail: `ARCHITECTURAL_DEBT_REGISTER.md`, `INTAKE-018` through `INTAKE-020`.

1. **No segment-content-hash dedup across two different overall uploads** — needs a new `content_sha256`
   column and cross-job lookup, genuinely new architecture beyond this sprint's bounded scope.
2. **A partially-failed finalize has no automatic retry path once `predmet_id` is set** — closing this
   requires a scoping decision (does "finalized" mean "fully done" or "at least partially done, may need
   reconciliation"), mirroring Sprint 005's own `partially_failed`-status deferral.
3. **Case number matching is exact-only, no format normalization beyond whitespace** — a deliberate
   conservatism choice; broadening it risks conflating two genuinely different case numbers, a judgment call
   this sprint's own mandate argues against making unilaterally.

None of these three block the mission's own success criteria — every document still ends in exactly one of
linked / explicitly-unlinked-with-a-reason / review-required; no wrong case/client link can occur through any
of these deferred gaps, only missed opportunities for additional automation.

## Section: Merljivo poboljšanje platforme (Measurable improvement)

| Metric | Before this sprint | After this sprint |
|---|---|---|
| Mechanisms that can recognize an incoming document belongs to an already-open case (by content) | 0 | 1 (`resolve_case_ownership`, exact case-number match) |
| Client-name matching correctness | Structurally broken (first-name-only column vs. full extracted name) | Correct (full-name comparison, company detection, never auto-picks between ambiguous matches) |
| Audit trail for document-into-case registration (Pipeline C) | None | Every successful registration audited (`document_assimilated`) |
| Lineage FK from case-file documents back to their originating upload/segment | 0 (Sprint 001's `INTAKE-003`, open since 2026-08-04) | 1 new FK + DB-enforced uniqueness, closing the gap for every Sprint-005-segmented job |
| Jobs Sprint 005 segments into 2+ documents that finalize could correctly process | 0 (would crash or silently assimilate only 1 of N) | All of them |
| False-success risk (case created/attached with 0 documents linked, reported as unconditional success) | Present, unfixed | Fixed — honest per-document + aggregate reporting, ERROR-level logging on total failure |
| New dedicated tests | 0 | 26 (19 `tests/test_case_assimilation.py` + 7 `tests/test_sprint006_finalize_assimilation.py`) |
| Full regression suite | 2,555 passed, 1 skipped, 0 failed (Sprint 005 close) | **2,581 passed, 1 skipped, 0 failed** — zero regressions from this sprint's changes |

**Platform state at the end of this sprint, honestly assessed**: a real capability gap (no way to recognize
an incoming document belongs to an existing case) is closed with a conservative, tested mechanism that never
guesses. A live correctness bug (client name matching) is fixed, not patched around. A structural
incompatibility between two consecutive sprints (Sprint 005's segmentation output vs. Sprint 006's own
finalize/status endpoints) is closed. Three genuine scope/architecture decisions remain open and are named,
not hidden.

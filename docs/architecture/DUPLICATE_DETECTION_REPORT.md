# Duplicate Detection Report — Program Intake Sprint 007 (2026-08-05)

Mission requirement (Debt 1): never use filename, size, or upload date. Implement a deterministic document
identity. If the system can prove the same document was already processed, do not create a duplicate. If the
evidence is insufficient, route to review — never guess.

## The identity

`predmet_dokumenti.content_sha256` (migration 095) — the SHA-256 hex digest of the document's own extracted
text (the same text that becomes `tekst_sadrzaj`/gets chunked for Pinecone), computed fresh at assimilation
time from the segment's own page-range slice (or the whole document's text for a single-document job).
**Never** derived from `naziv_fajla`, `velicina_kb`, `created_at`, or any other upload metadata — two files
with completely different names, sizes on disk (different compression/encoding), and upload timestamps, but
identical extracted content, hash identically.

## The check, and its three outcomes

Before every `predmet_dokumenti` insert, `finalize_intake_job` looks up existing rows sharing this
`content_sha256` (scoped by `user_id` — a tenant-isolation guard, never a cross-tenant lookup):

| Lookup result | Outcome | Reasoning |
|---|---|---|
| A match exists under the SAME `predmet_id` this call resolved | **Idempotent no-op** — reuse the existing row; mark the segment resolved (if applicable); no new document, no new lineage, no new audit, no new provenance | Either this segment's own prior attempt already succeeded (Debt 2's retry scenario), or a genuine re-upload of identical content into the same case — both cases mean "already correctly filed here," not "create another" |
| A match exists under a DIFFERENT `predmet_id` | **Review required** — the segment is NOT linked; `intake_job_segments.assimilation_status` (if applicable) is set to `review_required` with reason `duplicate_content_in_other_case`; the finalize response reports `povezan: false, razlog: "duplikat_u_drugom_predmetu"` | Never guess which case identical content really belongs to (mission's own absolute rule) — a lawyer must resolve this explicitly |
| No match | **Proceed normally** — first-time assimilation | Nothing to reconcile |

## Test scenarios required by the mission, and how each is proven

| Mission scenario (Serbian) | Test | What it proves |
|---|---|---|
| Isti PDF | `test_identical_content_same_case_is_not_duplicated_isti_pdf` | The exact same content, same target case → 0 new inserts, idempotent |
| Isti sadržaj pod drugim imenom | `test_same_content_different_filename_still_detected_isto_ime_drugo` | The dedup lookup never selects or filters on `naziv_fajla` — filename is structurally irrelevant, not coincidentally ignored |
| Isti sadržaj, drugi upload | `test_same_content_different_upload_isti_sadrzaj_drugi_upload` | An existing row from a completely different intake job is still found via content alone |
| Isti sadržaj posle retry | `test_same_content_after_retry_isti_sadrzaj_posle_retry` | A resumed job (recovered `predmet_id`) whose segment already has a row from the crashed prior attempt is a no-op, not a second document |
| (Named edge case, not in the mission's list but a direct consequence of "never guess") | `test_same_content_different_case_routes_to_review_not_guessed` | A cross-case content match never silently links or silently drops — always routes to review |

## Why this mechanism, not a simpler one

A naive alternative (comparing `naziv_fajla` + `velicina_kb` + upload date) was explicitly forbidden by the
mission, and would have been wrong anyway: the SAME physical document can be uploaded under a renamed file
(a lawyer re-scanning and re-saving with a different name), at a different compression level (different file
size for identical content), and at any later date — none of these are the document's actual identity.
Content hashing is the only mechanism that is invariant to all three while still being fully deterministic (no
fuzzy matching, no scoring, no false-positive risk from "close enough" names).

## Scope boundary, named honestly

This mechanism operates on **extracted text**, not raw file bytes. Two visually-identical scanned documents
that OCR to slightly different text (a different OCR engine, or a genuinely marginal scan-quality difference)
would NOT be detected as duplicates — this is a deliberate, bounded limitation: building fuzzy/near-duplicate
text matching is a different, much larger problem (with its own false-positive risk that would itself violate
the mission's "never guess" mandate) and is explicitly out of this sprint's scope. Today's mechanism correctly
catches the overwhelmingly common case (the same file, or a re-saved/renamed copy of it, run through the SAME
deterministic extraction path) without introducing any fuzzy-matching risk.

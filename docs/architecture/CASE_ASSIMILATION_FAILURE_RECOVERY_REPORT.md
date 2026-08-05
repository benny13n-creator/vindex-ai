# Case Assimilation Failure Recovery Report — Program Intake Sprint 006 (2026-08-05)

Mission requirement (Phase 5): if one segment fails, one predmet doesn't exist, classification is uncertain,
or audit fails to write — the other segments must continue normally. No global rollback. No false success
status.

## Per-document isolation, extending Sprint 005's own proven pattern

`finalize_intake_job`'s per-document loop wraps EACH document's chunk/ingest/insert/audit/Evidence-Vault
sequence in its own `try`/`except` — the exact same per-segment isolation discipline Sprint 005 built for
classification (`shared/intake_worker.py::_process_segments()`), now extended one stage further into
assimilation. One document's exception:
- Is caught locally, logged with the specific document/segment identifier.
- Marks that document's `intake_job_segments.assimilation_status = 'failed'` (if it has a segment — a
  single-document job has no segment row to mark, and simply reports itself unlinked in the response).
- Does NOT abort the loop — the next document is still attempted.
- Does NOT roll back the `predmet` that was already created/attached (a genuinely useful side effect,
  independent of any one document's fate).

Proven directly by `tests/test_sprint006_finalize_assimilation.py::test_one_document_insert_failure_does_not_lose_or_block_sibling`.

## Case ownership failure

If the target `predmet_id` a lawyer explicitly supplied doesn't exist (or isn't theirs), the ENTIRE finalize
call fails fast with a 404 — this is unchanged from before this sprint, and correctly so: an explicit,
named target that doesn't resolve is a caller error, not a partial-failure scenario.

If content-based Ownership Resolution finds the extracted case number matches 2+ existing cases, the entire
finalize call is blocked with a 409 before any predmet is created or any document is touched — never a
partial assimilation under a guessed case. The atomic finalize claim (`claim_intake_finalize`, migration 092)
is explicitly released (`finalizing_at` reset to NULL) on this exit path so a lawyer can retry immediately
with an explicit `predmet_id`, rather than waiting out the claim's ~120s staleness window.

## Classification uncertain

Unchanged from Sprint 004/005: a job only reaches `finalize_intake_job` at all once its status is
`'completed'`, which by construction means every one of its documents/segments was classified with
sufficient confidence (an uncertain segment routes the whole job to `'awaiting_review'` instead, per Sprint
005's own worker logic) — so "classification uncertain" cannot occur mid-finalize for a properly-gated job.
The `classification_uncertain`/`nesigurna_polja` response fields (Sprint 003/006) remain a defensive, honest
signal derived per-document from the review data get_job_documents() returns, in case this invariant is ever
violated by a future change — never silently assumed.

## Audit failure

`shared/audit_immutable.py::log_action()` is fail-soft by its own existing design (`"Greška u audit-u NIKAD ne
blokira glavni zahtev"`) — a failed audit write is caught internally, logged as a warning, and returns `None`
without raising. This sprint's new `document_assimilated` call site inherits this guarantee unchanged: an
audit-write failure never prevents a document from being correctly registered into its case.

## Deterministic outcome, never a false success

Every document ends the finalize call in exactly one of: linked (with lineage, audit, provenance all
recorded), or explicitly reported unlinked (`povezan: false`, with a `razlog`: `prazan_tekst` / `insert_
neuspesan` / `greska`). There is no third, silently-guessed state. The job-level response is likewise honest:
`dokumenata_povezano` / `dokumenata_ukupno` are reported as real counts, and a total failure (0 of N) is
logged at ERROR level rather than hidden behind an unconditional `ok: True`.

## Deliberately not built this sprint (see Architectural Debt Register for full reasoning)

- No cross-run retry/backoff for a FAILED document's re-assimilation — a failed document stays `failed` until
  the lawyer re-runs finalize (which, per the idempotency check, will attempt only the not-yet-linked
  documents on a subsequent call, since a job whose `predmet_id` is already set short-circuits to
  `already_finalized` — a genuinely failed document inside an already-finalized job has no automatic retry
  path today). This mirrors Sprint 005's own `INTAKE-016` deferral (bounded in-process retry only, no
  cross-run claim system) at the assimilation layer.

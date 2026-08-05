# Review Queue Specification — Program Intake Sprint 004 (2026-08-05)

**Note**: this filename previously held Sprint 003's review-queue analysis. This revision supersedes it —
Sprint 003 diagnosed that the queue's signal was being destroyed downstream; Sprint 004 makes the queue
itself a complete, resolvable, canonical system. Sprint 003's finding (Pipeline C silently overwriting an
uncertain classification) remains fixed and unchanged; this document describes the queue as it now stands
after this sprint's additional work.

## 1. The canonical queue

**Table**: `intake_review_queue` (migration 074). **One row per escalation.** Created by
`shared/intake_documents.py::create_review_queue_entry()`, called from exactly one place:
`shared/intake_worker.py::_process()` (Pipeline B's worker). No other code path creates a review-queue row.

**Fields**: `intake_job_id`, `document_id`, `reason` (CHECK-constrained, §2), `low_confidence_fields` (JSONB
array), `resolved_at`/`resolved_by` (nullable — unresolved when NULL). No free-text reason field exists;
`low_confidence_fields` carries the specific entity types involved (or `document_type` itself), not prose.

## 2. Unified review reasons (Phase 3)

Exactly 3 deterministic values, CHECK-constrained at the database level — no free text possible:

| Reason | Meaning | Set by |
|---|---|---|
| `ocr_failed` | The document was unreadable even after OCR | `_process()`'s OCR-failed branch |
| `classification_uncertain` | The document's TYPE itself is below `AUTO_ACCEPT_THRESHOLD` (0.90) — the more severe case, since a wrong type can misdirect downstream automation | `_process()`'s normal branch, when `document_type` is among the low-confidence fields (**new this sprint** — was previously lumped under the generic reason below) |
| `low_confidence_extraction` | One or more EXTRACTED FIELDS (deadline, amount, etc.) are uncertain, but the document's type itself is confidently known | `_process()`'s normal branch, all other cases |

Every escalation additionally carries: **confidence** (the actual numeric score that triggered it, on
`intake_documents.classification_confidence` / `extracted_entities.confidence`), **evidence** (the specific
field names in `low_confidence_fields` — a lawyer knows exactly what to check, not "something is uncertain"),
and now, in the frontend, a **human-readable reason label** (`_SI_REVIEW_REASON_LABELS`) shown alongside the
field list — closing the gap where only field names were ever shown, never the *why*.

## 3. Exactly one canonical queue — the `staging_memory` boundary decision

**Finding**: `staging_memory` (`routers/drafting.py`, migration 088) is a second, fully-working "human
confirms AI output" system — its own `is_lawyer_approved` boolean, its own `status IN ('pending','approved',
'rejected')` enum, its own confidence threshold (0.85), its own working approve/reject endpoints, its own
frontend.

**Decision: kept deliberately separate, not unified.** These answer genuinely different questions for
genuinely different objects:
- `intake_review_queue` — "is this INPUT document's classification/extraction confident enough to trust
  without a human looking at it?" One row per uploaded document, created automatically by a classifier.
- `staging_memory` — "does the lawyer approve of this AI-DRAFTED output before it enters the firm's permanent
  knowledge base?" One row per generated draft, approval is a deliberate authorial act, not a confidence
  threshold on an input.

Forcing these into one table would conflate an uncertainty-about-perception question with an approval-of-
generated-content question — the same category of mistake this session has repeatedly guarded against
elsewhere (Sprint 003 §3.2's Dokaz/`predmet_dokazi.kategorija` boundary, Program Gamma's `GAMMA-010` field-
collision finding). "Exactly one canonical review queue" is scoped, correctly, to the object this sprint's
charter names — documents that "cannot be reliably processed" — not to every human-confirms-AI-output
pattern in the platform.

## 4. Escalation → resolution → resume, end to end

```
_process() classifies/extracts
        ↓
confidence < 0.90 (or OCR failed)?
        ↓ yes
create_review_queue_entry(reason, fields)   ← Phase 3: unified, deterministic
        ↓
_tick() sets intake_jobs.status='awaiting_review'   ← Phase 1 fix: previously always 'completed'
        ↓
finalize_intake_job called → its EXISTING status gate rejects (409, clear message)   ← Phase 1 fix: previously never blocked at all
        ↓
Lawyer reviews on Step 3 screen (already existed; now actually reachable — Phase 1 fix #9/#10)
        ↓
POST /jobs/{id}/review/resolve   ← Phase 4: the ONE canonical resume action (new this sprint)
        ↓
resolve_review_queue_for_job() marks resolved_at   +   intake_jobs.status → 'completed'
        ↓
finalize_intake_job retried (same call, no special-casing) → status gate now passes → case created
```

No step in this chain repeats OCR, classification, or extraction. No step creates a duplicate document,
case, or vector. The resume IS the pre-existing finalize call, unmodified in its own logic — only its
precondition (the job's status) changed. Full detail: `RESUME_WORKFLOW_SPECIFICATION.md`.

## 5. What is NOT yet built (deferred, business decisions — §3 of `HUMAN_REVIEW_ARCHITECTURE_REPORT.md`)

- A genuine "reject" action (distinct from "confirm as-is").
- Direct correction of the document-TYPE value itself (only entity fields are correctable today).

Neither is a queue-architecture gap — the queue itself is complete, singular, and resolvable. Both are
questions about what OTHER actions a lawyer should be able to take against an already-well-formed queue entry.

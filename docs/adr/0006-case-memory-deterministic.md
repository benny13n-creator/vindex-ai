# ADR-0006: Case Memory is a deterministic lookup, not model fine-tuning

- Status: Accepted
- Date: 2026-07-15

## Context

Corrections a lawyer makes (an OCR-mangled judge's name, a misread party)
should not have to be made again. The obvious-sounding fix — feed
corrections back into model training — is the wrong one for a system whose
outputs feed legal deadlines: fine-tuning is non-deterministic, expensive to
run per-office, and effectively impossible to audit ("why did the model
produce this value" has no clean answer once it's baked into weights).

## Decision

Corrections are stored in `entity_corrections`, scoped by `kancelarija_id`
(one firm's correction never affects another firm's extraction). Future
extractions of a matching entity get a confidence boost toward the
corrected value. This is a lookup-and-boost, not a learning system — the
office learns Vindex learns the office, not the underlying model.

## Alternatives Considered

- **Fine-tune a shared model on correction data across all offices.**
  Rejected — cross-office data leakage risk, non-deterministic, unauditable,
  and expensive to retrain on every correction.
- **Per-office fine-tuned model.** Rejected — same non-determinism and
  audit problem, at even higher operational cost (one model per office).
- **No memory at all — every document extracted fresh.** Rejected — this is
  the status quo the brief specifically named as a failure: the same
  mistake recurring indefinitely.

## Consequences

- Fully explainable: "this value was auto-corrected because your office
  corrected it on [date]" is a real, literal answer, not an approximation.
- Introduces a new failure mode this ADR alone doesn't solve — a wrong
  correction becomes a systematic wrong answer going forward. Mitigated by
  `POST /api/admin/intake/corrections` (review/revoke), not by this
  decision itself. See the design review, §26.13.

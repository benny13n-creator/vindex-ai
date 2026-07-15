# ADR-0007: Versioned Facts deferred, out of Smart Intake's scope

- Status: Deferred — revisit when a Case/Client Facts data model is planned
- Date: 2026-07-15

## Context

Client and case facts (address, phone, employment status) can silently
change over a case's multi-year lifespan. Overwriting them in place means a
filing made three years into a case can no longer verify what the address
was when the case began. This is a real and correctly-identified problem.

## Decision

Smart Intake will **not** build fact versioning as part of this subsystem.
The reasoning: client and case facts are edited manually throughout the
rest of the product today — Settings, case detail pages — entirely outside
any intake flow. Versioning only the facts that happen to arrive via a
document would produce two different truth models for the same underlying
data, depending on how a fact happened to change. That's a worse outcome
than not versioning at all.

## Alternatives Considered

- **Version only intake-sourced fact changes.** Rejected for the reason
  above — a manually-edited phone number and a document-revealed address
  change are the same *kind* of event and need the same treatment.
- **Force full versioning into this subsystem's scope now.** Rejected —
  this is precisely the "can do everything" instinct a disciplined
  architecture pushes back on. It would also delay every other Smart
  Intake deliverable behind a much larger, separately-scoped data model
  change.

## Consequences

- Smart Intake documents remain the *trigger* for a fact change (via
  `source_document_id` on whatever eventually implements this) but not the
  *owner* of the versioning mechanism.
- This is a known gap, not a resolved one. Revisit when a broader Case/Client
  Facts initiative is scoped — Smart Intake becomes one writer into it, not
  the thing that builds it.

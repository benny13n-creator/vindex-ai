# ADR-0017: Automation Safety Levels

- Status: Accepted
- Date: 2026-07-15

## Context

The design accumulated a consistent instinct across every earlier ADR
without ever writing it down as a checkable rule: the required level of
human confirmation scales with the cost of being wrong, not with how
technically confident the AI is. ADR-0005 gates entity extraction at
90%/60%. ADR-0006 keeps Case Memory deterministic and auditable rather than
silently learned. ADR-0014 keeps lineage edges reviewable. ADR-0016 defers
Intent Engine specifically because its blast radius is categorically worse
than anything else in the design. None of that is stated as one rule a
future feature-builder can look up before deciding whether their new AI
action should run automatically.

## Decision

Every AI-driven action in Vindex is classified into one of the following
levels. The level determines the permission model — not the model's
self-reported confidence, and not how impressive the automation would look.

| Level | Action | Example | Permission |
|---|---|---|---|
| L0 | Preprocessing | OCR, deskew, denoise, contrast | Automatic |
| L1 | Metadata write | Recording extracted entities against a document | Automatic |
| L2 | High-confidence relational judgment | Case match ≥ 95%; lineage edge via explicit reference | Automatic |
| L3 | Lower-confidence relational judgment | Case match 60–94%; lineage edge via LLM inference; **any** possible-duplicate flag | Review queue — never silent |
| L4 | Knowledge State change | Health/Risk/Strategy/Completeness recalculation (ADR-0009) | Automatic, always audited via `case_dimension_history` |
| L5 | Operational status change | CRM/task status, seat or office assignment | User confirmation |
| L6 | Financial | Billing, invoicing, cost-sheet changes | User confirmation |
| L7 | Destructive or firm-wide | Deletion, case closing, an `entity_corrections` change affecting future extraction for the whole office | Explicit confirmation, reason logged |
| — | *(deferred)* Intent-driven business actions | Auto-close a task, auto-generate a workspace, auto-notify (ADR-0016) | Would span L5–L7 — this is precisely why ADR-0016 defers it rather than building it |

**Reconciling L2/L3 with ADR-0005's 90%/60% split.** These are
deliberately different numbers for a deliberately different reason, not an
inconsistency: ADR-0005's 90% threshold governs auto-accepting a single
extracted *field* (a judge's name, an amount). L2's 95% threshold governs
auto-accepting *where an entire document gets filed* — a materially higher
stakes decision than one field, and it gets a stricter bar. A future ADR
introducing a new automated judgment should set its own threshold based on
its own blast radius, not copy either number by default.

**L3 includes possible-duplicate flags unconditionally, not by confidence
tier.** ADR-0008 already established that semantic dedup is never silently
merged, at any similarity score — it isn't waiting for a future confidence
threshold to be tuned, it's categorically a review action.

## Alternatives Considered

- **A single global confidence threshold for all automated actions.**
  Rejected — this is the anti-pattern this ADR exists to prevent. It would
  let a low-stakes action (metadata write) and a high-stakes one (billing
  change) share a permission model just because they happen to use similar
  confidence math internally.
- **No formal levels — decide permission ad hoc per feature.** Rejected —
  this is what already produced the inconsistent PRO-gating pattern
  documented earlier this session (three different gating layers before
  PermissionService/UsageService unified it). A safety-level table is the
  same fix applied to automation permission that Feature Registry already
  applied to access control.

## Consequences

- Any future AI feature gets classified against this table before it ships,
  not after. "This is L5" is a complete, sufficient answer to "should this
  run automatically" — no separate debate needed each time.
- This table is a living document. A new level, or a reclassification of an
  existing action, should be a new ADR referencing this one — not a silent
  edit here.

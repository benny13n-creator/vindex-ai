# ADR-0016: Intent-driven orchestration layer deferred

- Status: Deferred — revisit once Phases 0–6 are live and their false-positive
  rates on case-matching/lineage are known
- Date: 2026-07-15

## Context

A proposal was made to extend the pipeline from reactive to intent-driven:
instead of `Document → Event → Projection`, `Document → Semantic Event →
Case Intent → Business Action → Projection`. Example: uploading a judgment
shouldn't just move Health +12 — the system should infer that a procedural
phase just concluded, and *act*: close stale tasks, surface an appeal
template, warn about the filing fee, recalculate the cost sheet, update
billing, update CRM status — without being asked.

This is a genuinely compelling direction and worth naming precisely why it
isn't being built now, rather than either silently absorbing it or silently
dropping it.

## Decision

**Deferred, not rejected.** Two specific reasons:

1. **It's a harder classification problem than anything else in this
   design.** Every other classification decision in Phases 0–6
   (document type, case match, lineage edge) classifies a document more or
   less on its own content. Inferring "procedural intent" requires
   classifying a document *in the context of that specific case's history*
   — the same document type (a judgment) means a different intent depending
   on whether it's a first-instance ruling, a post-remand judgment, or one
   closing an appeal. That's a materially harder problem than anything else
   in the pipeline, and Phases 0–6 haven't yet produced the case-history
   data (Document Lineage, Case Evolution) that intent-inference would need
   to lean on to do this reliably.

2. **The blast radius of a wrong inference is categorically worse than
   anything else in this design.** A wrong case-match misfiles a document.
   A wrong intent inference, taken to its logical conclusion in the
   proposal, auto-closes tasks, generates workspaces, and touches billing
   and CRM status — actions with real business and client-facing
   consequences, triggered without a document classification step this
   design already treats as needing human confirmation below 90%
   confidence (ADR-0005).

## Alternatives Considered

- **Build it now, fully automatic.** Rejected outright — see Consequence
  of a wrong inference above. This would be the single highest-blast-radius
  automated action anywhere in the product, built on the least-proven
  classification signal in the whole design.
- **Build it now, but every suggested action requires confirmation before
  executing.** Genuinely closer to right, and the shape any future version
  of this should take — but note that most of the individual actions in the
  example (surface an appeal template, warn about a fee, recalculate a cost
  sheet) are not new capabilities. They're orchestration of modules that
  already exist (`document_templates`, `profitabilnost_ai`, `zastarelost_
  guardian`, the CRM foundation layer). What's actually missing isn't those
  modules — it's the intent-classification step deciding *when* to invoke
  which of them, which is exactly the harder problem in point 1. Building
  the orchestration shell before the classification underneath it is solid
  is building on an unproven foundation.
- **Do nothing, never revisit.** Rejected — this is a real, differentiated
  direction and the deferral should be an active tracked decision, not an
  idea that quietly disappears.

## Consequences

- No Intent Engine, semantic-event layer, or auto-triggered business
  actions ship in Phases 0–6.
- If revisited: any future version must produce **suggested** actions
  gated by the same confidence-and-review discipline as case-matching and
  document lineage (ADR-0005, ADR-0014) — never auto-executed business
  actions — consistent with the "near-zero friction, mandatory fast
  exception path" principle already governing every other automated
  decision in this design.
- Revisit trigger: once Document Lineage (ADR-0014) and Case Evolution
  (ADR-0013) are live and have real-world confidence/false-positive data,
  that data is the actual prerequisite for scoping intent-classification
  reliably — not a separate research effort started from zero.

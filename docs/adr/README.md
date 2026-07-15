# Architecture Decision Records — Vindex Smart Intake Engine

ADRs for the Smart Intake Engine design (not yet implemented — Phase 0 per
the roadmap in the design review). Written at design time, before code,
specifically so a future team doesn't have to reverse-engineer *why* from
the schema alone. Each record is one decision: context, what was decided,
what else was considered, and what it costs.

Status values used below: `Accepted` (locked in, ready to build against),
`Deferred` (considered, deliberately not built now, with a revisit
trigger), `Superseded` (replaced by a later ADR — none yet).

| # | Decision | Status |
|---|---|---|
| [0001](0001-async-ingest-job-queue.md) | Ingest is async (202 + job_id), never a blocking request | Accepted |
| [0002](0002-postgres-job-queue.md) | Postgres-backed queue, not Celery/Redis | Accepted |
| [0003](0003-hybrid-extraction.md) | Regex-first, LLM-fallback for structured entities | Accepted |
| [0004](0004-folders-as-views.md) | Folders are computed views over tags, not storage | Accepted |
| [0005](0005-confidence-graph.md) | Per-entity confidence, not one score per document | Accepted |
| [0006](0006-case-memory-deterministic.md) | Case Memory is a deterministic lookup, not fine-tuning | Accepted |
| [0007](0007-versioned-facts-deferred.md) | Versioned Facts deferred, out of intake's scope | Deferred |
| [0008](0008-semantic-dedup-entity-overlap.md) | Semantic dedup requires entity overlap, not embedding alone | Accepted |
| [0009](0009-configuration-vs-knowledge-state.md) | Event sourcing applies to Knowledge State, not Configuration State | Accepted |
| [0010](0010-case-dimension-changed-envelope.md) | One generic `CaseDimensionChanged` event, not one type per dimension | Accepted |
| [0011](0011-case-dimension-type-as-entity.md) | Dimensions are a lookup table, not a CHECK-constrained string | Accepted |
| [0012](0012-state-diff-debounce.md) | State Diff Engine composes on a debounce window | Accepted |
| [0013](0013-case-evolution-no-analytics-table.md) | Case Evolution reads `case_dimension_history` directly | Accepted |
| [0014](0014-document-lineage-confidence-gated.md) | Lineage edges are confidence-scored and reviewable, never auto-asserted | Accepted |
| [0015](0015-target-state-scoped.md) | Target-state tracking, scoped to dimensions where "target" has meaning | Accepted |
| [0016](0016-intent-engine-deferred.md) | Intent-driven orchestration layer deferred | Deferred |

Source design review: internal architecture document, revisions 1–3,
2026-07-15.

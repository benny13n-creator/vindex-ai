# ADR-0002: Postgres-backed job queue, not Celery/Redis

- Status: Accepted
- Date: 2026-07-15

## Context

ADR-0001 requires a background job queue. No message broker (Celery, Redis,
RQ, arq) exists anywhere in the current stack — confirmed by reading the
codebase, not assumed. Introducing one is a real infrastructure decision:
another service to provision, monitor, and keep alive in production, on top
of Supabase/Postgres which is already there.

## Decision

`intake_jobs.status` is the queue. Workers claim rows with
`SELECT ... FOR UPDATE SKIP LOCKED`, process their stage, and update status —
formalizing the fire-and-forget `asyncio.create_task` background-task
pattern already used elsewhere in the codebase (e.g. `law_upload.py`) into a
proper polling worker loop that survives the originating request finishing.

## Alternatives Considered

- **Celery + Redis.** Rejected for now — real operational capability
  (retries, priority queues, distributed workers) that Vindex doesn't need
  at current volume (tens of thousands of documents, not millions/day), and
  a second infrastructure dependency to keep healthy.
- **A managed queue service (SQS, Cloud Tasks).** Rejected — ties the
  architecture to a specific cloud provider Vindex hasn't otherwise
  committed to, for a problem Postgres already solves at this scale.

## Consequences

- Enough for realistic law-firm volume; not designed to survive a
  10,000-documents-per-minute spike. If queue-depth monitoring
  (design review §22) shows sustained backlog, that's the trigger to
  revisit — not a projected future scale to build for today.
- One less moving part to operate than the alternative. Revisit this ADR
  if Vindex's ingest volume grows by an order of magnitude, not before.

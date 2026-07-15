# ADR-0001: Ingest is asynchronous (202 + job_id), never a blocking request

- Status: Accepted
- Date: 2026-07-15

## Context

The existing `/api/dokument/upload` endpoint runs OCR, classification, and
ingest synchronously inside the HTTP request. That's tolerable for a single
ephemeral-session document. Smart Intake targets batch drops (a lawyer's
whole morning inbox at once) — holding a connection open for the minutes a
14-file batch would take is not viable, and any transient failure mid-batch
would take the entire request down with it.

## Decision

`POST /api/intake/documents` accepts a multipart batch and returns
`202 Accepted` with a `job_id` per file immediately. All processing
(preprocess → classify → extract → match → enrich) happens in background
workers against a durable job record. Clients poll `GET /api/intake/jobs/{id}`
or subscribe via SSE.

## Alternatives Considered

- **Keep it synchronous, just raise the timeout.** Rejected — doesn't fix
  the single-slow-file-blocks-the-batch problem, and ties up a request
  worker for the duration of an OCR pass, which is exactly the kind of load
  that should be shed to a background worker pool.
- **Client-side chunked/sequential upload (one file at a time, in a loop).**
  Rejected — pushes orchestration complexity onto every client (web, mobile,
  future watcher/email adapters) instead of once, in the API.

## Consequences

- The UI needs a real progress-state model (§3 of the design review) instead
  of a single spinner — not free, but it's the same investment every serious
  batch-upload product makes.
- Requires the job queue (ADR-0002) and durable event bus to exist first —
  this ADR is a hard prerequisite for everything downstream in the roadmap.

# ADR-0004: Folders are computed views over tags, not physical storage

- Status: Accepted
- Date: 2026-07-15

## Context

The brief's own diagnosis: lawyers' files are badly named, duplicated, and
scattered across folders precisely because folder placement is a decision
made once, at upload time, and rarely revisited even when it's wrong. A
physical folder hierarchy on top of Smart Intake would just make that
mistake faster.

## Decision

Documents are stored flat, content-addressed under `predmet_id/`.
"Court Decisions / Evidence / Contracts / Correspondence" is a query over
`document_tags` (many-to-many — one document can be tagged `evidence`,
`medicinska_dokumentacija`, and `appeal_attachment` simultaneously),
computed at request time via `GET /api/intake/folders/{predmet_id}`.

## Alternatives Considered

- **Physical folder tree per case, one document per folder.** Rejected — a
  corrected classification would require physically moving the file, and a
  document that genuinely belongs in two categories (a medical report that
  is also case evidence) would have to be duplicated or arbitrarily
  assigned to one.
- **Single `document_type` enum column, no separate tags table.** Rejected
  as the sole mechanism — kept as the *primary* classification for
  auto-naming and default handling, but folder/view membership needed to be
  many-to-many, which a single enum column can't express.

## Consequences

- A corrected tag instantly changes which virtual folders a document
  appears in, with nothing to migrate — same principle already applied to
  the Pricing Matrix (derive, never duplicate-store).
- The `document_tags` vocabulary needs the same governance as any other
  taxonomy in the product (see ADR-0011's reasoning) — an uncontrolled
  free-text tag field would recreate the "badly named, inconsistent" problem
  one layer up.

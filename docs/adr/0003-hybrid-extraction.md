# ADR-0003: Regex-first, LLM-fallback for structured entity extraction

- Status: Accepted
- Date: 2026-07-15

## Context

Case numbers, dates, and monetary amounts follow fixed, learnable formats in
Serbian legal documents (e.g. case numbers matching `П\s?\d+/\d{2}`). Party
names, courts, and judges don't — they're free text. A single extraction
strategy for both is a mismatch for at least one of them.

## Decision

Extraction is hybrid and per-field: structured fields (case number, date,
amount) go through deterministic regex first, with LLM extraction only
filling what regex misses. Free-text fields (parties, court, judge) go
straight to LLM extraction. Every field carries its own confidence score
and an `extraction_method` (`regex` / `heuristic` / `llm`) — see ADR-0005.

## Alternatives Considered

- **Pure LLM extraction for every field.** Rejected. It looks more
  impressive in a demo and produces answers that are far harder to audit —
  the wrong tradeoff for a system whose outputs feed legal deadlines. It's
  also more expensive and slower per document than a regex match.
- **Pure regex/heuristic extraction, no LLM at all.** Rejected — free-text
  fields (party names, in particular) don't have a fixed format regex can
  reliably capture.

## Consequences

- Regex-extracted fields are close to 100% explainable and auditable by
  construction — the "why" shown to a lawyer for these fields is the
  literal pattern match, not a model's self-report.
- Requires maintaining a small library of Serbian legal-document regex
  patterns as a first-class artifact, not a throwaway detail — case number
  formats, in particular, may vary by court or case type and need upkeep.

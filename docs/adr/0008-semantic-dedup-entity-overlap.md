# ADR-0008: Semantic deduplication requires entity overlap, not embedding similarity alone

- Status: Accepted
- Date: 2026-07-15

## Context

Content-hashing catches exact duplicate files only. A rescanned or
rephotographed version of the same document produces a completely different
hash. Embedding similarity is the obvious fix — except legal documents are
unusually boilerplate-heavy: two different clients' powers of attorney, or
two standard-form contracts, will embed as near-identical purely from
shared template language, despite being genuinely different documents.

## Decision

A document is flagged as a possible duplicate only when **both** embedding
similarity **and** extracted-entity overlap (matching case number, parties,
or date from `extracted_entities`) clear their thresholds. Flagged into the
review queue as a suggestion — never silently merged or auto-deleted.

## Alternatives Considered

- **Embedding similarity alone.** Rejected — the boilerplate problem above
  makes this unreliable specifically in the legal domain, which is close to
  a worst case for pure semantic similarity.
- **Entity overlap alone, no embedding.** Rejected — misses genuine
  near-duplicates where entity extraction itself is uncertain (e.g. a
  low-confidence case number on both copies), which is exactly when
  embedding similarity is most useful as a second signal.

## Consequences

- Requires an embedding call per ingested document (reusing the existing
  embedding pipeline pattern from `law_upload.py`) — a real, if small,
  marginal cost per document (see the design review's cost discussion,
  §26.12).
- Should be monitored post-launch rather than assumed solved — this is a
  mitigation of a known hard problem, not a closed one.

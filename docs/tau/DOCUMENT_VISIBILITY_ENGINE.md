# Document Visibility Engine — Program Tau, Master Sprint 002, Phase 3

**Implementation**: `shared/case_context.py::_select_documents` (Layer 4 selection),
`shared/case_context.py::_excerpt` (within-document sampling, delegates to
`routers/cross_doc.py::_uzorkuj_dokument`), `shared/case_context.py::get_document_full_text` (Layer 5).
**Tests**: `tests/test_tau002_case_context.py` (11 tests directly targeting this engine).

## The problem this solves

`CONTEXT_BUILDER_REGISTRY.md` found `case_commander.py`'s own pre-Tau-002 builder fetched documents with
no `.order()` clause and then took `[:10]` of that unordered result — meaning the same static head-slice
of a case's documents was shown every single call, regardless of how many documents existed or which ones
were actually relevant. At the mission's own named "500 documents" scale, documents 11-500 were not
merely truncated — they never had any chance of being selected, ever, by construction.

## The 5 layers

**Layer 1 — Case metadata.** `case_identity`/`participants`/`procedural_status` in the Case Context
Contract. Always included, always small (a handful of scalar fields).

**Layer 2 — Genome facts.** `key_facts`/`contradictions`/the Genome-derived half of `missing_evidence`.
Always included when Genome has been computed for the case (`genome_computed`); `key_facts.value` is
explicitly `None`, not a fabricated placeholder, when it hasn't.

**Layer 3 — Evidence graph.** `evidence_graph` — a count-and-category rollup of `predmet_dokazi`, not raw
evidence text. Always included, always small (bounded by the number of distinct categories × strength
levels, not by evidence count).

**Layer 4 — Relevant document excerpts.** `relevant_documents.value.included`. This is where the "500
documents" problem is actually solved:

1. `_select_documents` first sorts the full document set by `redni_broj` (falling back to `id` if that's
   ever missing) — **it does not trust the order documents arrive in**, so a shuffled fetch result or a
   future query without an explicit `.order()` clause cannot change which documents get selected
   (`test_select_documents_out_of_input_order_still_deterministic`, `test_select_documents_deterministic_across_repeated_calls`).
2. The `MAX_RECENT_ALWAYS_INCLUDED` (5) most recently created documents are always included — a freshly
   uploaded document is never waiting behind 495 older ones to become visible.
3. The remaining slots (up to `MAX_DOCS_INCLUDED`, 15 total) are filled by a fixed-stride sample across
   the FULL remainder, by `redni_broj` — the same principle `cross_doc.py`'s own within-document sampler
   already uses, applied here at the document-selection level instead. `test_select_documents_covers_late_documents_not_just_head`
   proves this reaches into the back half of a 500-document case, not just the front.
4. Each included document's own text then goes through `_excerpt`, which calls
   `routers/cross_doc.py::_uzorkuj_dokument` directly — the existing, already-proven stride-based sampler
   (Program Celina, 2026-07-24) — rather than a new truncation implementation.

**Layer 5 — On-demand deep retrieval.** `relevant_documents.value.not_included_but_retrievable` lists
every document that didn't make the Layer 4 cut, each with its own `dokument_id` and a pointer to
`shared/case_context.py::get_document_full_text(predmet_id, uid, dokument_id, supa)` — a single,
RLS-scoped (`predmet_id` + `user_id` match), deterministic lookup that returns that document's full text
on request. `test_not_included_documents_are_retrievable_via_layer_5` proves this round-trips correctly:
a document excluded from a 300-document case's excerpt set is still fetchable, in full, by id.

## The actual proof of "no document permanently invisible"

Not "everything fits in one prompt" — it doesn't, and forcing it to would violate the mission's own
explicit ban on sending all 500 documents directly to the model. The proof is set-theoretic and directly
tested:

```
included_ids ∪ not_included_ids == all_document_ids   (nothing silently dropped)
included_ids ∩ not_included_ids == ∅                    (no double-accounting)
```

`test_select_documents_500_scale_every_document_accounted_for` and
`test_select_documents_1000_scale_every_document_accounted_for` assert exactly this at both of the
mission's own named extreme-test scales. Every document that exists is either directly visible in the
current call, or explicitly named with a working retrieval path — never simply absent with no trace.

## What Layer 5 does NOT yet do

`get_document_full_text` is implemented and tested as a standalone, callable function. It is **not yet
wired into any consumer's own GPT tool-calling loop** — Tau Sprint 001 found tool calling essentially
unused in legal-reasoning call sites across the whole codebase, and wiring live tool-calling into 3
migrated modules (Phase 5) is a materially larger, riskier change than proving the retrieval path itself
works. This sprint delivers the retrieval mechanism and its guarantee; a future sprint can wire a specific
consumer to call it live when a lawyer's own query names a document outside the Layer 4 sample. Flagged
explicitly here rather than silently left implicit, per this sprint's own "brutalna preciznost" standard.

## Determinism and statelessness (Phase 7's requirements, verified here structurally)

No `random` import anywhere in `shared/case_context.py`. `_select_documents` and `_excerpt` are pure
functions of their inputs. `build_case_context` performs a fresh Supabase read on every call — there is no
module-level cache, so a Genome refresh or new document upload between two calls is reflected on the very
next call, and two calls (from two different processes, i.e. after a restart) against unchanged underlying
data return byte-identical results apart from timestamp fields
(`test_build_case_context_deterministic_across_simulated_restarts`). Two concurrent calls for different
cases share no mutable state and cannot cross-contaminate each other's results
(`test_parallel_calls_for_different_cases_do_not_interfere`).

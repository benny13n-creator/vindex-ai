# Document Expectation Engine — Program Sigma, Master Sprint 003 (2026-08-06)

Phase 3 deliverable: does the platform already reason "this document implies that document should exist"?
Confirmed this sprint, via direct code reading: **no, not today.** This document records exactly what exists
adjacent to this capability, and a precise design for closing the gap without inventing a parallel algorithm.

## What exists today, and why none of it is document-to-document expectation

- **`shared/constants.py::EXPECTED_DOCS`** — a static, per-case-**type** list of expected document
  **categories** (e.g. `"parnicno": ["sudska_odluka", "podnesak", "ugovor", "dopis"]`), consumed by
  `calculate_procesni_rizik` to check "does at least one document of category X exist." This is
  case-TYPE-level, never document-to-document.
- **Genome's own `nedostaje[]`** (`routers/case_dna.py:120-122`) — case-level, holistic GPT judgment
  ("what would help prove this case"), constrained only by "samo ono sto ZAISTA nedostaje" (line 142). No
  instruction anywhere asks the model to reason about a SPECIFIC document implying a SPECIFIC companion
  document — no referential/pairwise reasoning instruction exists in the prompt at all.
- **`services/legal_reasoning_engine.py`'s own `LegalElement` node** — checked directly, does NOT model
  unsatisfied requirements. `_REASONING_SYSTEM`'s own prompt (lines 51-75) requires "svaki claim MORA imati
  bar jednu cinjenicu i bar jedan pravni izvor" (line 60) — a `LegalElement` node is only ever created when
  facts+norms already support it. There is no "this legal element is required but nothing satisfies it"
  concept in the graph as currently queried (though see `GAP_ENGINE_REGISTRY.md`'s own note — the raw
  discarded signal exists, just isn't wired to anything).
- **`nacrti/checklist_engine.py`** — the closest EXISTING mechanism in shape (a `naziv`/`pokriven`(bool)/
  `kriticnost`/`razlog`-if-missing checklist record, including a `punomocje` config entry at line 769) — but
  it checks whether a lawyer's **typed draft input** covers required elements before generating a document,
  never the case's own **already-uploaded document set**. Wrong mechanism to extend directly, right shape to
  borrow.

## The mission's own worked examples, checked one by one

| Example | Exists today? |
|---|---|
| Contract exists → expect referenced annexes | No — nothing reads a contract's own text for annex references |
| Appeal exists → expect proof of filing | No — nothing pairs an appeal document with a filing-receipt document |
| Court decision relies on delivery → expect a delivery receipt (dostavnica) | No — `routers/rocista.py` has no delivery-tracking field |
| Expert opinion cited → expect the actual expert report document | No — nothing cross-references a document's own citations against the document set |

**None of the mission's own 4 worked examples are currently detectable by any existing mechanism.** This is
Phase 3's own genuine, confirmed gap — not a wiring problem, a real missing capability.

## Why this was not implemented blind this sprint

Building document-to-document expectation reasoning correctly requires either (a) a new, carefully-scoped
GPT prompt asking the model to reason about referenced-but-absent companion documents (a genuine new
capability, not a duplicate of anything existing — but a live prompt-design decision with real legal-domain
correctness stakes: over-triggering produces noise a lawyer learns to ignore, under-triggering misses the
exact value this mission cares about), or (b) deterministic pattern-matching against document text for
specific reference phrases ("videti Aneks", "prilog br."), which is real NLP/extraction work, not a
mechanical fix. Both are the kind of "new algorithmic surface area" this sprint's own founding principle
requires to be centralized in ONE place, not scattered — meaning the RIGHT next step is a single, carefully
designed addition to `shared/gap_engine.py` (this sprint's own new canonical aggregation point), not an
ad-hoc addition to any one consumer.

## Recommended design (not implemented this sprint)

A new gap type, `GAP_TIP_OCEKIVANI_PRILOG`, populated by a NEW, single extraction step — most naturally as
an ADDITIONAL field on Genome's own extraction (`routers/case_dna.py`'s own prompt already reasons over the
full document corpus in one pass; asking it to ALSO report "document X references Y, which isn't present"
is an extension of an existing GPT call, not a new one) — output shape:
`{"referenced_by": "DOK-XX", "expected": "Aneks B", "reference_text": "..."}`, normalized into the same
canonical Gap record `shared/gap_engine.py` already defines (`ocekivano`/`pronadjeno`/`zasto`, `hipoteza:
True` always — GPT-advisory, per Phase 2's own explicit rule). This reuses the EXISTING Genome extraction
call (no new AI infrastructure), reuses the EXISTING Gap record shape (no new schema), and is scoped as ONE
well-defined prompt-extension decision, not implemented without a live-browser verification pass this
sprint's own time budget didn't include. Recorded as `SIGMA-013` in the Debt Register.

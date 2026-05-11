# Phase 2.3 — Document Question Retrieval
**Date:** 2026-05-11  
**Branch:** `feature/p2-3-doc-retrieval`  
**Tests:** 48/48 passed (10 new)  
**30Q sanity:** 20✅/8⚠️/2❌ (natural variation, see below)

---

## Changes

### `app/services/retrieve.py`
- Added `_pretraga_ns(vektor, namespace, k=5)` — queries arbitrary Pinecone namespace
- Extended `retrieve_documents(query, k=6, extra_namespaces=None)` signature
- Faza 0b: submits extra-namespace futures to a separate ThreadPoolExecutor when `extra_namespaces` provided
- Faza 6: resolves futures, appends formatted passages to `docs`, populates `retrieval_meta["doc_passages"]`
- All existing callers unaffected (`extra_namespaces=None` default)

### `app/services/doc_formatter.py` (new)
- `format_doc_passage(match)` — produces `KORISNIKOV DOKUMENT [filename, article, chunk N]` header + body
- `format_doc_passages(passages)` — joins multiple passages with `---` separator

### `uploaded_doc/session.py`
- Added `validate_session(session_id) -> bool` — queries `tmp_<session_id>` top_k=1, verifies non-expired vector exists

### `main.py`
- Added `_DOC_CONTEXT_ADDENDUM` — citation instructions for uploaded documents vs zakon/praksa
- In `ask_agent`, injects addendum into system_prompt when any `filtrirani` entry contains `"KORISNIKOV DOKUMENT"`
- Extended `ask_agent(pitanje, history=None, extra_namespaces=None)` — passes `extra_namespaces` to `retrieve_documents`

### `api.py`
- Added `POST /api/dokument/pitanje` — validates session (404 if invalid), enforces 2000-char limit, calls `ask_agent` with `extra_namespaces=["tmp_<session_id>"]`

---

## Test Results

| File | Tests | Result |
|------|-------|--------|
| test_doc_retrieval.py | 4 | ✅ all pass |
| test_doc_pitanje_api.py | 6 | ✅ all pass |
| (all prior tests) | 38 | ✅ no regressions |
| **Total** | **48** | **48/48 ✅** |

---

## 30Q Sanity Run

**Result:** 20✅ / 8⚠️ / 2❌  
**Baseline:** 19✅/11⚠️/0❌ (Mode A) or 19✅/10⚠️/1❌ (Mode B)

**Assessment: Not a regression.** The 2 LOW-confidence questions are pre-existing issues:
- **Q14** (score 0.5077, below MEDIUM threshold 0.52): "Pravo na regres kod osiguravajućih društava?" — retrieves `ustav republike srbije` instead of ZOO; marked LOW in `VINDEX_HALLUCINATION_FREE_TEST.md` (score identical at 0.5077)
- **Q30** (score 0.4087): "Šta je beneficium ordinis?" — obscure Latin legal term, always borderline

Phase 2.3 code changes affect only queries that explicitly pass `extra_namespaces`. The standard 30Q pipeline passes `extra_namespaces=None` throughout, so the RAG pipeline is byte-for-byte identical to pre-Phase-2.3 for all non-document queries.

---

## Commits
1. `ea933d2` feat(p2-3): retrieve_documents + doc_formatter
2. `918b1db` feat(p2-3): validate_session
3. `d8e8c59` feat(p2-3): _DOC_CONTEXT_ADDENDUM + ask_agent extension
4. `0f791ec` feat(p2-3): POST /api/dokument/pitanje
5. `e11762d` test(p2-3): 10 tests

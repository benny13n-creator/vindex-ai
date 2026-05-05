# Vindex AI — Architectural Audit
**Date:** 2026-05-04  
**Scope:** Full codebase read — api.py, main.py, retrieve.py, multi_query_rag.py, semantic_chunker.py, ingest_laws.py, ingest_kz.py, reindex_agentic.py, requirements.txt, Dockerfile  
**Methodology:** Read every file, cross-referenced against live Pinecone audit data (23,699 vectors, audit_chunks.py output). No bias toward preserving existing work.

---

## SECTION A — UNACCEPTABLE
*These issues either create security exposure, data correctness failures, or silent production failures right now. Each must be fixed before the next public release.*

---

### A1. Hardcoded secrets in source code (3 files)

**`ingest_kz.py:33`**
```python
INDEX_HOST = "vindex-ai-t8z679r.svc.aped-4627-b74a.pinecone.io"
```

**`ingest_laws.py`** — same pattern, hardcoded INDEX_HOST  
**`reindex_agentic.py:38`**
```python
INDEX_NAME = "vindex-ai"
```

These are infrastructure addresses committed to git history. Anyone with repo access can target the live index. Fix: `os.getenv("PINECONE_HOST")` / `os.getenv("PINECONE_INDEX_NAME")`, same as the pattern already used in retrieve.py.

---

### A2. Hardcoded founder email addresses in api.py

```python
FOUNDER_EMAILS = os.getenv("FOUNDER_EMAILS", "benny13.n@gmail.com,kristina.stojanovic@dsa.rs,kristinap93@hotmail.com")
```

These names appear in source code and therefore in git history forever. Founders get unlimited credits — anyone who can read this file and register with those emails bypasses the credit system. Fix: move to environment variable with no fallback default.

---

### A3. CORS wildcard combined with JWT auth

`api.py` defaults `ALLOWED_ORIGINS = ["*"]`. Every protected endpoint (`/api/ask`, `/api/me`, etc.) requires a Bearer token, but with wildcard CORS any malicious page can initiate cross-origin requests using a logged-in user's token. This is the classic CSRF-via-CORS pattern. Fix: explicitly list allowed origins (`https://vindex.ai`, `https://app.vindex.ai`). No wildcard.

---

### A4. Dead pipeline — multi_query_rag.py is never called

`multi_query_rag.py` is 818 lines of a fully implemented pipeline (intent classification, priority hierarchy, no-truncation context builder, conflict detection, structured JSON output). `main.py`'s `ask_agent` calls `retrieve_documents()` from `retrieve.py` — it does NOT call `run_multi_query_rag()`. The module is unreachable in production.

This means:
- FIX-1 through FIX-9 (labeled improvements) are all bypassed
- Every LLM call to `analyze_documents()` and `generate_structured_answer()` in multi_query_rag.py never happens
- The `classify_query_intent()` intent classification is dead
- The constitutional/treaty source hierarchy weighting (`_PRIORITY_WEIGHTS`) is dead

**Decision required:** either wire multi_query_rag.py into the main pipeline and delete the duplicate logic in retrieve.py + main.py, or delete multi_query_rag.py entirely. Having two competing pipelines where one is dead is worse than having one.

---

### A5. klasifikuj_pitanje() and 4 system prompts in main.py are dead code

`main.py` has `klasifikuj_pitanje()` which returns one of COMPLIANCE / PORESKI / PARNICA / DEFINICIJA, and 4 separate system prompts (one per type). `ask_agent` v3 never calls `klasifikuj_pitanje()` — it goes straight to the confidence gate. These ~200 lines of dead code mislead any developer reading the file.

---

### A6. Zero-vector used for semantic retrieval (_direktan_fetch_clana)

`retrieve.py` uses `[0.0] * 3072` as the query vector when doing direct article fetches:
```python
DUMMY_VEC = [0.0] * 3072
```

A zero vector has undefined cosine similarity (division by zero). Different Pinecone implementations handle this differently — some return random results, some return by insertion order, some crash. This is used in:
- The ZOO fallback (articles always injected when confidence is low)
- Any `_direktan_fetch_clana` call

The ZOO fallback means that for every low-confidence query, a set of fixed ZOO articles (`_ZOO_FALLBACK_CLANOVI`) is unconditionally injected regardless of relevance. For a question about criminal law, the pipeline injects contract law articles. That is the definition of context pollution.

---

### A7. 7,858 unaccounted vectors in Pinecone (33% of index)

From audit_chunks.py: total vectors = 23,699. Sum of all known law names = ~15,841. Gap = 7,858 vectors (33%) whose `law` field doesn't match any known law name. These are either:
- Old v1 vectors with different law name formatting (e.g. "krivični zakonik" vs "KZ")
- Vectors from laws ingested before the current naming convention
- Corruption from repeated reindex operations

These vectors pollute every unfiltered query. When `zakon` detection returns `None`, retrieve.py searches all 23,699 vectors — 33% of which are noise. This directly degrades answer quality for any multi-law question.

---

### A8. No version pinning in requirements.txt

```
fastapi
uvicorn[standard]
openai
pinecone
...
```

Every package is unpinned. The next `pip install` in any deployment could pull a breaking version. The OpenAI Python SDK has had multiple breaking API changes (v0→v1 migration). Pinecone SDK also changed its interface. This is one deploy away from silent breakage.

**Also missing from requirements.txt:** `cohere` — used in retrieve.py for reranking (`_get_cohere()`), but not listed. The app silently falls back to score-sort when Cohere is unavailable, meaning reranking quality degrades with no error.

---

### A9. Chunking boundary defects — ~330 articles with absorbed section headers

This is the issue being fixed in parallel (semantic_chunker.py `_skini_zaglavlja`). Documented here for completeness: ~330 articles in the live index have trailing section headers embedded in their `parent_text`. When these articles are retrieved, the LLM receives misleading text that suggests the article discusses topics it does not. The fix is in progress but not yet applied to the live index.

---

## SECTION B — MUST ADD WITHOUT COMPROMISE
*Absent functionality that creates either legal/compliance risk or operational blindness in a legal information service.*

---

### B1. Audit log for every LLM-generated answer

The app gives legal information to users. There is currently no persistent record of:
- What question was asked
- What context was retrieved (which articles, which law)
- What answer was generated
- What the confidence level was

If a user receives incorrect legal advice and acts on it, there is no way to reconstruct what happened. A Supabase `query_log` table (user_id, question, top_article, top_law, confidence, answer_summary, timestamp) is not optional for a legal product.

---

### B2. Answer disclaimer enforcement

There is a `napomena` field in the response schema and a `_verifikuj_pravne_greske()` check in main.py. But there is no guaranteed, unconditional disclaimer appended to every response that says "ovo nije pravni savet." The current disclaimer logic is:
- Only fires if `_verifikuj_pravne_greske()` detects one of 10 hardcoded patterns
- The napomena field can be "—" (empty)
- The LLM can return a confident-sounding answer with no caveat

For a legal information service in Serbia, this creates liability. The disclaimer must be structural (appended by the API layer regardless of LLM output), not LLM-dependent.

---

### B3. Dependency version lockfile

`requirements.txt` needs pinned versions. Create `requirements.txt` with `pip freeze` output from a working environment. Add `cohere` to it.

---

### B4. CORS lockdown (see A3)

Already called unacceptable above. Repeated here as a concrete action item: set `ALLOWED_ORIGINS` to the explicit list of frontend domains, remove any wildcard default.

---

### B5. Structured error responses for retrieval failure

When Pinecone returns zero results, the app currently returns a generic "nisu pronađeni relevantni pravni izvori" message. There is no:
- Differentiation between "index offline" vs "genuine no-match"
- Suggestion to rephrase
- Fallback to ask a human

Users querying about a topic not covered by the 19 indexed laws get the same message as users whose query hit a Pinecone API error. These are different situations requiring different responses.

---

### B6. Monitoring / alerting for confidence distribution

There is no aggregated tracking of confidence levels across queries. The confidence gate (HIGH/MEDIUM/LOW) determines whether users get real answers or refusals — but there is no way to know what fraction of production queries are being refused vs. answered. Without this telemetry, the thresholds (0.65 HIGH, 0.52 MEDIUM) cannot be tuned. Add at minimum a counter per confidence tier to whatever logging infrastructure exists.

---

## SECTION C — SALVAGEABLE
*Components that are architecturally sound but need specific fixes to reach production quality.*

---

### C1. retrieve.py — pipeline architecture is strong

The 5-stage pipeline (embed → multi-query decomposition + HyDE → parallel Pinecone search → Cohere rerank → CRAG) is genuinely good design. The orig_score_map sub-query pollution fix (2026-05-04) is the right approach. The cross-law tie-breaker logic (trust max-cosine for cross-law conflicts, trust Cohere for same-law) is thoughtful.

**Specific fixes needed:**
- Remove zero-vector ZOO fallback (A6 above) — replace with a proper semantic check or remove entirely
- The `_CRAG_PETLJA` calls `_prosiri_pretragu_crag()` which generates synonym queries but these go through unfiltered Pinecone search — apply law filter when zakon is known
- `_direktan_fetch_clana` should use a real semantic embedding, not a zero vector

---

### C2. main.py confidence-gated pipeline — sound structure

The three-tier gate (LOW → instant refusal, MEDIUM → raw article text, HIGH → LLM practical interpretation) correctly solves the hallucination problem for uncertain queries. The thresholds are plausible but unvalidated.

**Specific fixes needed:**
- Remove dead `klasifikuj_pitanje()` and 4 system prompts (A5)
- The MEDIUM-confidence path returns raw article text without a disclaimer — add the structural disclaimer (B2)
- `_skini_pii()` runs before OpenAI calls but query is logged in plaintext before that — move PII stripping to before logging

---

### C3. semantic_chunker.py — solid foundation

The article-boundary detection, parent-text metadata design (small embedding chunk + full parent_text for LLM), and stub detection are well-designed. The `_podeli_na_stavove()` fallback chain (numbered → blank-line → word-count) handles the variety of Serbian legal text formats.

**Specific fixes needed:**
- Add numbered header branch to `_SECTION_HEADER_RE`: `|\d{1,2}\.\s+[A-ZŠĐČĆŽ][a-zšđčćž\S ]{2,79}(?<![.,;:!?)\d])`  
  (catches "6. Posebna zaštita od otkaza", "2. Dnevni odmor", "3. Treći nasledni red")
- Run re-ingestion after regex is fully validated (see test_chunker_fix_v2.py)

---

### C4. api.py credit system — design is correct

The 15-credit free tier, `deduct_credit` Supabase RPC, founder unlimited access, and `_ensure_profile` upsert pattern are all sound. The `/api/credits-debug` diagnostic endpoint is a nice operational tool.

**Specific fixes needed:**
- Remove hardcoded founder emails (A2)
- The `/test-pinecone` endpoint uses hardcoded `"vindex-ai"` index name — use `PINECONE_INDEX_NAME` env var
- Rate limiter (60/hour per IP) should also apply to founder accounts — unlimited credits ≠ unlimited API calls

---

### C5. multi_query_rag.py — architecture worth using

The intent classification + angle-driven decomposition (FIX-1), per-query Pinecone cap instead of global truncation (FIX-2), constitutional hierarchy weighting (FIX-6), no-mid-article-truncation context builder (FIX-4), and conflict detection (FIX-7) are all genuine improvements over the current retrieve.py approach.

**The question is not "is this good?" but "why isn't it running?"** The path forward: wire `run_multi_query_rag()` into `ask_agent`, remove the duplicate retrieval+generation logic from main.py+retrieve.py, and consolidate into one pipeline. This is the most impactful architectural improvement available without new features.

---

### C6. ingest_laws.py / ingest_kz.py — ingest pattern is sound

Delete-then-ingest with 5s propagation sleep and post-ingest verification queries is the right approach. The `--dry-run` and `--verify` flags in ingest_kz.py are good operational design.

**Specific fixes needed:**
- Replace hardcoded `INDEX_HOST` with `os.getenv("PINECONE_HOST")` in both files
- `ingest_laws.py` does not cover ZUS, ZVP, ZZPL, ZZP — 4 laws with PDFs but no ingest coverage. These are in the 7,858 unaccounted vectors
- `reindex_agentic.py` connects via `pc.Index(INDEX_NAME)` — should use `pc.Index(host=INDEX_HOST)` for consistency with the rest of the codebase

---

## Summary Table

| ID  | Severity    | Component            | Issue                                                    |
|-----|-------------|----------------------|----------------------------------------------------------|
| A1  | CRITICAL    | ingest_kz, ingest_laws | Hardcoded Pinecone INDEX_HOST in source code           |
| A2  | HIGH        | api.py               | Hardcoded founder emails in source code                  |
| A3  | HIGH        | api.py               | CORS wildcard with JWT auth                              |
| A4  | HIGH        | multi_query_rag.py   | Entire pipeline is dead code — never called              |
| A5  | MEDIUM      | main.py              | klasifikuj_pitanje() + 4 prompts are dead code           |
| A6  | HIGH        | retrieve.py          | Zero-vector ZOO fallback injects irrelevant articles     |
| A7  | HIGH        | Pinecone index       | 7,858 unaccounted vectors (33%) pollute unfiltered search |
| A8  | MEDIUM      | requirements.txt     | No version pinning; cohere missing entirely              |
| A9  | HIGH        | semantic_chunker.py  | ~330 articles with absorbed section headers (in-progress fix) |
| B1  | MUST ADD    | Missing              | No audit log for generated answers                       |
| B2  | MUST ADD    | main.py / api.py     | No unconditional legal disclaimer per response           |
| B3  | MUST ADD    | requirements.txt     | Pin all deps, add cohere                                 |
| B4  | MUST ADD    | api.py               | CORS lockdown (same as A3)                               |
| B5  | MUST ADD    | retrieve.py / api.py | Structured retrieval failure differentiation             |
| B6  | MUST ADD    | Missing              | Confidence tier telemetry for threshold tuning           |
| C1  | FIX NEEDED  | retrieve.py          | Remove zero-vector fallback; fix CRAG unfiltered search  |
| C2  | FIX NEEDED  | main.py              | Remove dead code; add structural disclaimer              |
| C3  | FIX NEEDED  | semantic_chunker.py  | Add numbered header branch; re-ingest                    |
| C4  | FIX NEEDED  | api.py               | Hardcoded index name; founder rate limiting              |
| C5  | FIX NEEDED  | multi_query_rag.py   | Wire into main pipeline or delete                        |
| C6  | FIX NEEDED  | ingest scripts       | Env vars; add 4 missing laws; fix index connection       |

---

## Recommended Fix Order

1. **A1 + A2 + A3** — secrets and CORS. Zero-cost fixes, high risk if left.
2. **A8 (requirements.txt)** — pin versions, add cohere. One command: `pip freeze`.
3. **A9 + C3** — finish semantic_chunker.py regex fix and re-ingest (already in progress).
4. **A7** — identify and resolve the 7,858 unaccounted vectors. Run audit to find their actual `law` field values, decide whether to migrate or delete.
5. **A4 + C5** — wire multi_query_rag.py into the main pipeline, delete duplicate code in main.py/retrieve.py.
6. **A6** — replace zero-vector ZOO fallback with a real semantic check.
7. **B1 + B2** — audit log and unconditional disclaimer. Non-negotiable before any broader user acquisition.
8. **A5 + C2** — remove dead code.
9. **C6** — ingest missing 4 laws; fix hardcoded index connection.
10. **B5 + B6** — retrieval failure responses and confidence telemetry.

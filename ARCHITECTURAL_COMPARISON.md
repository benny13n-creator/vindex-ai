# Vindex AI — Architectural Comparison: Two Retrieval Pipelines
**Date:** 2026-05-04  
**Files compared:** `app/services/multi_query_rag.py` vs `app/services/retrieve.py` + `main.py`  
**Purpose:** Decide which pipeline to keep, which to delete, and what (if anything) to port.

---

## Context: What Each Pipeline Is

**Pipeline A — `multi_query_rag.py`**  
818-line fully self-contained pipeline. Entry point: `run_multi_query_rag(user_query)`.  
Returns `{zakljucak, korisceni_clanovi, coverage, konflikti, napomena}` structured JSON.  
**Status: dead code. Never called in production.**

**Pipeline B — `retrieve.py` + `main.py`**  
`retrieve_documents()` in retrieve.py feeds `ask_agent()` in main.py. This is the live pipeline.  
`ask_agent()` applies a confidence gate: LOW → refusal, MEDIUM → raw article text, HIGH → gpt-4o interpretation.  
**Status: the only pipeline users interact with.**

---

## FIX-1 through FIX-9 — Overlap Analysis

Before scoring, establish which improvements are unique to each side.

| Fix | Description | In multi_query_rag.py | In retrieve.py + main.py |
|-----|-------------|----------------------|--------------------------|
| FIX-1 | Intent classification + angle-driven decomposition | ✓ `classify_query_intent()` line 145; `_INTENT_ANGLES` lines 208-251 | ✗ Generic 3-sub-question prompt only (`_dekomponuj_query()` line 356) |
| FIX-2 | Per-query cap (k=4) instead of global hard cap | ✓ `TOP_K_PER_QUERY=4` line 40 | ✗ retrieve.py uses k=30 per law-filtered query (line 668) |
| FIX-3 | Combined query for Cohere (original &#124; sub-queries) | ✓ lines 419-421 | ✗ Cohere uses original query only (line 832) |
| FIX-4 | No mid-article truncation; budget-based context | ✓ `_CONTEXT_TOTAL_BUDGET=12_000` line 465 | ✗ No explicit context budget; parent_text capped in chunker at 3000 chars |
| FIX-5 | No minimum sources rule | ✓ (removed from prior version) | N/A (never existed in retrieve.py) |
| FIX-6 | Source hierarchy weighting (Constitution > statute > by-law) | ✓ `_PRIORITY_WEIGHTS` lines 51-65 | ✗ No source hierarchy; all laws scored equally |
| FIX-7 | Semantic legal reasoning layer (rules/exceptions/conditions/conflicts) | ✓ `analyze_documents()` line 514 | ✗ Only 10 hardcoded pattern checks (`_verifikuj_pravne_greske()` in main.py) |
| FIX-8 | Structured JSON output | ✓ `_ANSWER_SYSTEM_PROMPT` line 584 | ✗ Free-form markdown; 12-section narrative format |
| FIX-9 | Stability safeguards | ✓ Empty retrieval check, <2 docs warning, single-law warning | ✓ LOW confidence gate, CRAG fallback, ZOO fallback, empty context logging |

**Summary:**  
FIX-1, FIX-2, FIX-3, FIX-4, FIX-6, FIX-7, FIX-8 are **unique to multi_query_rag.py**.  
FIX-9 is present in both, with different mechanisms.

**What retrieve.py + main.py has that multi_query_rag.py lacks entirely:**

| Feature | Location | Why It Matters |
|---------|----------|----------------|
| HyDE (hypothetical doc embedding) | retrieve.py line 392 | Different signal path — embeds a synthetic legal paragraph, not the query |
| GPT expansion (4 alt queries) | retrieve.py line 928 | Background call; adds recall for edge vocabulary |
| CRAG self-correction loop | retrieve.py line 958 | Corrective: DELIMIČNO → synonym expansion; NIJE RELEVANTNO → HyDE retry |
| **Confidence gate (HIGH/MEDIUM/LOW)** | retrieve.py lines 302-312, main.py `ask_agent()` | **The single most important feature for a legal product** |
| Citation verification | main.py `_proveri_halucinaciju()` | Checks cited article numbers against retrieved context |
| 10 legal error patterns | main.py `_verifikuj_pravne_greske()` | Domain-specific: zastarelost periods, krivični vs. parnični confusion, etc. |
| PII stripping | main.py `_skini_pii()` | Removes JMBG, email, phone before OpenAI |
| Query TTL cache | main.py lines 163-194 | 1-hour cache, max 500 entries; significant cost reduction for repeat queries |
| Sub-query pollution fix | retrieve.py lines 554-558 | `orig_score_map` penalizes sub-query-only candidates (0.85×) |
| Cross-law Cohere tie-breaker | retrieve.py lines 842-861 | Within-law → trust Cohere; cross-law → trust max cosine |
| LAW_HINTS routing | retrieve.py lines 42-179 | 180+ keyword entries across 20 laws; filters Pinecone before embedding |
| Domain-specific triggers | retrieve.py lines 628-641 | ZDI, KZ, ZPDG, Smart contract expansion — topic-aware retrieval |
| SL_GLASNIK_MAP | main.py lines 36-159 | Sl. glasnik citations for every indexed law |
| MEDIUM path (raw text, no LLM) | main.py `ask_agent()` | Zero hallucination risk for medium-confidence queries |

---

## DIMENSION 1 — Retrieval Quality

### 1.1 Query Understanding

**multi_query_rag.py: 8/10**

`classify_query_intent()` (line 145) routes into 6 categories: rights, procedure, deadlines, jurisdiction, evidence, mixed. Rule-based keyword scoring with LLM fallback when top two scores are within 1. `_INTENT_ANGLES` (lines 208-251) maps each category to 5 specific search angles — "jurisdiction" gets "koji sud je stvarno nadležan", "mesna nadležnost", "sukob nadležnosti", "žalbeni organ", "izuzeci". `decompose_query()` (line 254) uses the angle template to guide GPT-4o-mini, producing 3-5 semantically orthogonal sub-queries rather than paraphrases.

This is substantially better query decomposition. A jurisdiction question produces jurisdiction-specific sub-queries. A deadline question produces deadline-specific sub-queries.

**retrieve.py + main.py: 6/10**

`_dekomponuj_query()` (line 356) is generic: "give me 3 concrete legal sub-questions." No intent awareness. For any question — jurisdiction, deadline, evidence — the prompt is identical. However, retrieve.py compensates with two additional signals absent from multi_query_rag.py: HyDE (`_generiši_hyde()`, line 392) generates a synthetic legal paragraph that matches the embedding space of actual statute text, and `_prosiri_query_gpt_wrapper()` (line 928) adds 4 more alternative queries in the background. These are different signal types, not better-targeted versions of the same signal.

### 1.2 Multi-Source / Source Hierarchy

**multi_query_rag.py: 9/10**

`_PRIORITY_WEIGHTS` (lines 51-65) explicitly encodes the Serbian legal hierarchy. Constitution gets +0.30, international treaties +0.25, major codified laws +0.10, bylaws +0.05. This weight is added to Cohere's relevance score (line 447), so a constitutional article with slightly lower semantic similarity still ranks above a municipal bylaw with higher similarity. Context is assembled law-by-law in priority order (line 478-482).

This is architecturally correct for a legal AI. A question about discrimination that hits both Ustav Član 21 and a pravilnik should always cite the constitution first. multi_query_rag.py guarantees this. retrieve.py does not.

**retrieve.py + main.py: 4/10**

`_izracunaj_skor()` (lines 546-595) has no source hierarchy. A municipal bylaw and the Constitution are treated identically by scoring. The only law-preference logic is matching the detected law (±30 points for law match) and exact article match (±50 points). Domain-specific boosts exist for specific laws (`skor += 80` for ZOO Član 200 when "nematerijalna šteta" detected, line 581) but these are hardcoded for specific known queries, not a systematic hierarchy.

### 1.3 Context Assembly

**multi_query_rag.py: 8/10**

`build_structured_context()` (line 468) enforces a 12,000-character total budget. Articles are checked against budget before inclusion; if adding an article would exceed the budget, it is skipped entirely — never truncated mid-text. Laws are ordered by priority score so constitutional articles always appear first. Output is grouped by law with `[LAW: ...]` headers.

**retrieve.py + main.py: 6/10**

`_formatiraj_match()` (line 600) returns parent_text from metadata (already capped at 3000 chars by the chunker). The list of formatted strings is passed directly to gpt-4o. There is no explicit total budget guard — if 6 articles each contain 3000 chars, the context is 18,000 chars. In practice this is rare because most articles are shorter, but there is no architectural protection against it.

### 1.4 Cohere Reranking Integration

**multi_query_rag.py: 8/10**

`rerank_documents()` (line 400) builds `combined_query = query + " | " + sub_queries[:4]` (lines 419-421) and passes this to `co.rerank()`. This is semantically correct: the reranker should see all angles of the question, not just the original phrasing. Priority boost applied additively to Cohere score (line 447).

**retrieve.py + main.py: 7/10**

`_cohere_rerank(query, top_kandid, k=k)` (line 832) passes only the original query. The sub-query signals that elevated certain documents into the top-10 candidate set are invisible to Cohere. However, retrieve.py has the cross-law tie-breaker (lines 842-861) which correctly distinguishes within-law disagreements (trust Cohere's semantic judgment) from cross-law disagreements (trust max cosine). This is a sophisticated and correct mechanism that multi_query_rag.py lacks.

### 1.5 Cross-Law Conflict Handling

**multi_query_rag.py: 7/10**

`analyze_documents()` (line 514) runs post-retrieval and semantically detects conflicts between retrieved provisions. Result injected into generation prompt. However, this is a separate GPT call, adds latency, and may not detect structural legal conflicts (lex specialis vs lex generalis) that require domain knowledge.

**retrieve.py + main.py: 5/10**

The cross-law tie-breaker in retrieve.py (lines 842-861) prevents wrong-law ranking. main.py's fallback system prompt (SYSTEM_PROMPT_FALLBACK, line 206) has explicit lex specialis / lex generalis instructions — "ZOO je uvek LEX GENERALIS — nikada ga ne navodi kao lex specialis" (line 215). But this logic lives in the prompt text, not in code that runs before or during retrieval.

---

## DIMENSION 2 — Answer Generation

### 2.1 Hallucination Guards

**multi_query_rag.py: 5/10**

`_ANSWER_SYSTEM_PROMPT` (line 584) contains "Koristi SAMO informacije iz konteksta." This is a prompt instruction, not a verification pass. There is no code that runs after generation to check whether cited articles were actually in the retrieved context. The `coverage` field indicates partial/sufficient but does not catch fabricated citations.

**retrieve.py + main.py: 8/10**

`_proveri_halucinaciju()` in main.py explicitly parses the LLM output, extracts cited article numbers using regex, and checks whether each cited article appears in the retrieved docs list. If a citation is not found in context, the response is flagged. `_verifikuj_pravne_greske()` checks 10 known domain-specific error patterns — e.g., incorrect zastarelost periods, misuse of "automatski" for legal consequences (which Serbian law specifically prohibits), criminal vs civil confusion. These are programmatic guards, not prompt instructions.

### 2.2 Citation Accuracy

**multi_query_rag.py: 8/10**

Structured output forces `{zakon, clan, tekst}` per citation (line 595-601). Machine-parseable. Frontend can verify each citation, display it separately, link to source. No citation can be silently missing a law name.

**retrieve.py + main.py: 5/10**

Free-form markdown. "CITAT ZAKONA:" section contains free text. Citations extracted post-hoc by regex for the hallucination check. Format inconsistent across responses — sometimes "ZOO čl. 200", sometimes "Zakon o obligacionim odnosima, član 200", sometimes just "čl. 200". This is the correct format for human lawyers to read, but poor for programmatic processing.

### 2.3 Confidence Calibration

**multi_query_rag.py: 4/10**

`_compute_coverage()` (line 689) returns "sufficient" if ≥2 distinct laws OR ≥3 articles, otherwise "partial." This is a retrieval-count metric, not a semantic confidence score. It doesn't distinguish between "found 3 articles in the right law" and "found 3 articles from 3 wrong laws." The LLM may override this in its output. No routing logic — every query goes through the full generation pipeline regardless of confidence.

**retrieve.py + main.py: 9/10**

`get_confidence_level()` (line 306) maps Pinecone cosine scores to HIGH/MEDIUM/LOW using thresholds calibrated against the 30-question benchmark (comment at line 293-299). The gate is structural, not advisory:
- LOW (< 0.52) → immediate refusal, no LLM call, no hallucination risk
- MEDIUM (0.52-0.65) → raw article text returned directly, no LLM interpretation
- HIGH (≥ 0.65) → full gpt-4o interpretation

The MEDIUM path is architecturally elegant: the user gets the actual statute text when confidence is borderline, which is more useful and more honest than a hedged LLM interpretation. multi_query_rag.py has no equivalent.

### 2.4 Conflict Detection

**multi_query_rag.py: 8/10**

`analyze_documents()` (lines 514-577) runs a gpt-4o-mini pass over the top-8 retrieved articles and extracts `{rules, exceptions, conditions, conflicts}`. The `conflicts` string is injected into the generation prompt (line 635) and appears in the final output's `konflikti` field. Users can see "Detected conflict between ZOO 154 and ZOO 192."

**retrieve.py + main.py: 2/10**

No conflict detection. `_verifikuj_pravne_greske()` checks for known static patterns (e.g., incorrect zastarelost period stated as 3 years when it should be 5). But it cannot detect a conflict between two articles that both appear in the retrieved context.

### 2.5 Output Structure for Legal Professionals

**multi_query_rag.py: 7/10**

Structured JSON is clean for API consumers and frontend rendering. However, `zakljucak` is a short summary, not the multi-section legal analysis a Serbian lawyer needs. The output lacks lex specialis/lex generalis hierarchy, procesni koraci (procedural steps), ključno pitanje (decision-relevant question), risk flags, or the explicit link to Sl. glasnik sources.

**retrieve.py + main.py: 9/10**

The HIGH-path system prompt (SYSTEM_PROMPT_FALLBACK, line 206) produces a 12-section format: KRATAK ZAKLJUČAK (3-sentence constraint), HIJERARHIJA IZVORA, PRAVNI ZAKLJUČAK, ANALIZA ŠTETE (when applicable), CITAT ZAKONA, PRAVNI OSNOV, POUZDANOST, RIZICI I IZUZECI, PROCESNI KORACI, KLJUČNO PITANJE, DODATNA PITANJA. Each section has explicit constraints ("ZABRANJENO: definitivne tvrdnje", "NIKADA: fiksnu cifru za naknadu štete"). This format was clearly designed by someone who consulted with Serbian lawyers. It is richer and more useful than multi_query_rag.py's generic {zakljucak, clanovi} output.

---

## DIMENSION 3 — Production Readiness

### 3.1 Error Handling and Fallbacks

**multi_query_rag.py: 6/10**

Each stage has try/except. Empty retrieval returns a structured error dict (lines 739-747). `<2 docs` and `single-law scope` log warnings (lines 754-761). JSON parse errors in generation return a structured error response (line 679). No recovery mechanism when retrieval is genuinely poor — the pipeline always runs through all steps regardless.

**retrieve.py + main.py: 7/10**

CRAG loop (line 897) attempts self-correction when relevance is DELIMIČNO or NIJE RELEVANTNO. ZOO fallback (lines 874-890) injects known useful articles when confidence is low — but uses a zero vector (bug A6 from audit), which undermines the mechanism. LOW confidence gate (main.py) prevents bad answers by refusing rather than guessing. CRAG is a genuine recovery mechanism that multi_query_rag.py lacks.

### 3.2 Logging and Observability

**multi_query_rag.py: 9/10**

9 distinct log prefixes: `[PIPELINE]`, `[INTENT]`, `[DECOMPOSE]`, `[RETRIEVE_MULTI]`, `[DEDUP]`, `[RERANK]`, `[CONTEXT]`, `[ANALYZE]`, `[GENERATE]`. Each log includes counts, scores, and key values. Pipeline elapsed time logged at end. A developer can reconstruct exactly what happened from logs alone.

**retrieve.py + main.py: 8/10**

`[RETRIEVE]`, `[CRAG]`, `[HyDE]`, `[MULTI_Q]`, `[COHERE]`, `[FORMAT]`, `[PINECONE]`. Per-doc logging for top-3 results. Confidence level and score logged with each query. Slightly less structured than multi_query_rag.py but comprehensive.

### 3.3 LLM Cost per Query

**multi_query_rag.py: 5/10**

Every query, regardless of how obvious or simple, runs:
- `classify_query_intent()`: gpt-4o-mini, ~10 tokens (skipped if rule-based is unambiguous)
- `decompose_query()`: gpt-4o-mini, max 500 tokens
- `analyze_documents()`: gpt-4o-mini, max 600 tokens (**always runs, even for simple queries**)
- `generate_structured_answer()`: gpt-4o, max 1800 tokens

Total per query: 2-3× gpt-4o-mini (1100-1110 tokens) + 1× gpt-4o (1800 tokens). `analyze_documents()` is the key waste — it adds a full LLM call for every query, including simple definitional questions where conflict analysis is meaningless.

**retrieve.py + main.py: 7/10**

HIGH path:
- `_dekomponuj_query()`: gpt-4o-mini, max 300 tokens
- `_generiši_hyde()`: gpt-4o-mini, max 150 tokens
- `_prosiri_query_gpt_wrapper()`: gpt-4o-mini, max 200 tokens (background, max 3s)
- `_oceni_relevantnost()` CRAG: gpt-4o-mini, max 20 tokens
- gpt-4o answer: max 2200 tokens

Total HIGH: 4× gpt-4o-mini (670 tokens) + 1× gpt-4o (2200 tokens). Slightly more gpt-4o-mini calls, but the MEDIUM path skips gpt-4o entirely. For a legal product where borderline queries are common, the MEDIUM optimization is significant.

TTL query cache (main.py lines 163-194) further reduces costs for repeat queries.

### 3.4 Latency Profile

**multi_query_rag.py: 5/10**

Pipeline stages run mostly sequentially: classify → decompose → retrieve_multi (parallel) → dedup → rerank → **analyze_documents** (blocking) → generate. `analyze_documents()` is a mandatory blocking gpt-4o-mini call before generation can start. Expected total: 10-18 seconds.

**retrieve.py + main.py: 7/10**

Parallelism is aggressive: decompose + HyDE run in a 2-worker executor (line 758-762). All Pinecone searches run with 12 workers (line 660). GPT expansion runs in a background 1-worker executor with a 3-second timeout (lines 789-804) — it doesn't block the main pipeline. CRAG relevance check (max 20 tokens) is fast. MEDIUM path skips gpt-4o entirely. Expected: 3-8 seconds MEDIUM, 5-12 seconds HIGH.

### 3.5 State Management

**multi_query_rag.py: 8/10**

Fully stateless. Imports singleton clients from retrieve.py (`_get_client`, `_get_cohere`, `_get_embeddings`, `_get_index` — lines 26-33). No shared mutable state.

**retrieve.py + main.py: 9/10**

Singleton clients with lazy initialization (`_PINECONE_INDEX`, `_EMBEDDINGS`, `_CLIENT`, `_COHERE_CLIENT`). Query cache in main.py (lines 163-194) with TTL and LRU eviction. `proveri_zdi_indeksiranost()` exported for health checks.

---

## DIMENSION 4 — Code Quality

### 4.1 Modularity and Testability

**multi_query_rag.py: 9/10**

10 distinct functions with single responsibilities. `LegalDoc` dataclass (lines 79-109) carries all document metadata. `classify_query_intent()`, `decompose_query()`, `retrieve_multi()`, `deduplicate_and_group()`, `rerank_documents()`, `build_structured_context()`, `analyze_documents()`, `generate_structured_answer()` — each testable in isolation with mock inputs. Functions are pure where possible.

**retrieve.py + main.py: 4/10**

`retrieve_documents()` is a 200-line orchestration function (lines 731-925). Internal helpers like `_izracunaj_skor()` (lines 546-595) mix generic scoring with domain-specific Serbian law hardcodes (magic `skor += 80` for ZOO Član 200 when "nematerijalna šteta" detected, line 581). Testing this requires a live Pinecone connection or extensive mocking. `_jedan_retrieval_krug()` (lines 645-726) is 80 lines and does 7 different things.

### 4.2 Dead Code

**multi_query_rag.py: 8/10**

Internally clean. No dead functions. Every function is called by `run_multi_query_rag()`. (The module itself is unreachable from main.py, but internally there is no dead code.)

**retrieve.py + main.py: 3/10**

`klasifikuj_pitanje()` in main.py is dead — `ask_agent()` v3 does not call it (confirmed: the function exists but there is no call site in ask_agent). Four system prompts — `SYSTEM_PROMPT_COMPLIANCE`, `SYSTEM_PROMPT_PORESKI`, `SYSTEM_PROMPT_PARNICA`, `SYSTEM_PROMPT_DEFINICIJA` — are built into a dict that `ask_agent()` no longer references. `SYSTEM_PROMPT_QA` is explicitly marked "legacy." `OBAVEZNE_SEKCIJE_QA`, `SEKCIJE_COMPLIANCE`, `SEKCIJE_PORESKI`, `SEKCIJE_PARNICA`, `SEKCIJE_DEFINICIJA` — all defined but unused. Roughly 400 lines of dead code in main.py alone.

### 4.3 Configuration Management

**multi_query_rag.py: 9/10**

Named constants at module level: `TOP_K_PER_QUERY = 4` (line 40), `SOFT_CAP_DOCS = 10` (line 43), `_CONTEXT_TOTAL_BUDGET = 12_000` (line 465). `_PRIORITY_WEIGHTS` (lines 51-65) is a structured list, not scattered literals.

**retrieve.py + main.py: 4/10**

Magic numbers throughout: `top_k=30` (line 668), `top_k=6` (line 672), `top_k=8` (line 780), `top_k=3` (various expansion terms), `top_k=5` (sub-queries line 698). Domain-specific score boosts embedded in `_izracunaj_skor()`: `skor += 30`, `skor += 50`, `skor += 80`, `skor += 70`, `skor += 45`, `skor += 40` — with no explanation for why these specific values were chosen. Confidence thresholds (0.65, 0.52) are well-named constants. `LAW_HINTS` is a large but readable dict.

### 4.4 Documentation

**multi_query_rag.py: 9/10**

Module docstring enumerates FIX-1 through FIX-9 changes (lines 1-15). Every function has a docstring. Inline FIX comments at each improvement site. `_PRIORITY_WEIGHTS` has inline comments explaining each tier.

**retrieve.py + main.py: 5/10**

retrieve.py module docstring references "all 5 sprints." Most functions have docstrings. `_izracunaj_skor()` has no explanation for domain-specific magic numbers. The sub-query pollution fix comment (lines 810-823) is detailed and excellent. main.py has inconsistent documentation — some sections well-commented, others (the dead classification code) left without notice that they are dead.

---

## DIMENSION 5 — Extensibility

### 5.1 Adding a New Law

**multi_query_rag.py: 9/10**

Add one entry to `_PRIORITY_WEIGHTS` at the appropriate tier. Retrieval is dynamic. No other changes needed.

**retrieve.py + main.py: 7/10**

Add keyword entries to `LAW_HINTS` (retrieve.py lines 42-179), add to `SL_GLASNIK_MAP` (main.py), add to `ZAKON_SHORTCODES` in semantic_chunker.py. If the law has specific vocabulary, add to the domain-specific trigger sets. More work, but `LAW_HINTS` already covers the pattern.

### 5.2 Adding Sudska Praksa (Case Law)

**multi_query_rag.py: 9/10**

Add an entry to `_PRIORITY_WEIGHTS` with an appropriate weight (e.g., 0.08 for VKS decisions, 0.04 for lower courts). The priority hierarchy naturally accommodates a new source tier.

**retrieve.py + main.py: 3/10**

No hierarchy mechanism. Would require adding custom boost logic to `_izracunaj_skor()` as hardcoded score additions. Fragile and non-systematic.

### 5.3 Swapping Embedding Model

**multi_query_rag.py: 8/10**

Uses `_get_embeddings()` imported from retrieve.py. One constant to change (`EMBEDDING_MODEL` in retrieve.py line 37).

**retrieve.py + main.py: 9/10**

`EMBEDDING_MODEL = "text-embedding-3-large"` (line 37). All embedding calls go through `_get_embeddings()`. One change propagates everywhere.

### 5.4 Adding New Query Types / Intent Handling

**multi_query_rag.py: 9/10**

Add keywords to `_INTENT_RULES` (lines 131-142) and an angle template to `_INTENT_ANGLES` (lines 208-251). Clean, named extension points. The new intent gets its own retrieval angles automatically.

**retrieve.py + main.py: 3/10**

`klasifikuj_pitanje()` in main.py exists (4 types: COMPLIANCE, PORESKI, PARNICA, DEFINICIJA) but is dead — ask_agent v3 no longer calls it. Extending it would also require reconnecting the dead classification path to ask_agent. The 4 system prompts in main.py each need separate maintenance.

---

## Scorecard Summary

| Dimension | Sub-dimension | multi_query_rag.py | retrieve.py + main.py |
|-----------|--------------|:-----------------:|:--------------------:|
| **Retrieval** | Query understanding | 8 | 6 |
| | Source hierarchy | **9** | 4 |
| | Context assembly | 8 | 6 |
| | Cohere integration | 8 | 7 |
| | Cross-law conflict (retrieval) | 7 | 5 |
| **Generation** | Hallucination guards | 5 | **8** |
| | Citation accuracy | 8 | 5 |
| | Confidence calibration | 4 | **9** |
| | Conflict detection | **8** | 2 |
| | Output structure (legal fit) | 7 | **9** |
| **Production** | Error handling | 6 | 7 |
| | Logging | **9** | 8 |
| | Cost efficiency | 5 | **7** |
| | Latency | 5 | **7** |
| | State management | 8 | **9** |
| **Code Quality** | Modularity | **9** | 4 |
| | Dead code | 8 | 3 |
| | Configuration | **9** | 4 |
| | Documentation | **9** | 5 |
| **Extensibility** | New law | **9** | 7 |
| | Sudska praksa | **9** | 3 |
| | Embedding swap | 8 | **9** |
| | New intent types | **9** | 3 |
| **Totals** | | **174** | **147** |

Multi_query_rag.py scores higher on totals — but the scorecard hides the single most important asymmetry.

---

## The Asymmetry That Overrides the Scorecard

**retrieve.py + main.py has the confidence gate. multi_query_rag.py does not.**

For a legal AI, this is not a feature. It is the primary safety mechanism.

The confidence gate (retrieve.py lines 302-312, main.py ask_agent) routes:
- LOW confidence → immediate refusal. No LLM call. No hallucination possible.
- MEDIUM confidence → raw statute text returned directly. Zero interpretation, zero fabrication risk.
- HIGH confidence → full gpt-4o interpretation.

multi_query_rag.py generates an LLM answer for every query regardless of retrieval quality. A query that produces cosine similarity of 0.40 (clearly wrong law or wrong article) still gets a generated `zakljucak`. There is no gate.

In a product serving Serbian lawyers, a confidently wrong answer about zastarelost or uslovni otpust can cause real harm. The confidence gate is what makes the current pipeline acceptable for legal use even in its current imperfect state.

This is the decisive difference. multi_query_rag.py is architecturally cleaner and has more sophisticated retrieval. But it lacks the one mechanism that prevents the pipeline from confidently asserting wrong law to a lawyer.

---

## Verdict: Option C — Hybrid (implemented as porting into retrieve.py + main.py)

**What this means concretely: keep retrieve.py + main.py as the foundation. Port 5 specific improvements from multi_query_rag.py. Delete multi_query_rag.py when done.**

This is Option B done with surgical precision — not "delete multi_query_rag.py and move on" but "extract what matters from it."

### What to Port (from multi_query_rag.py into retrieve.py + main.py)

**Port 1: FIX-1 — Intent-aware decomposition**  
Replace `_dekomponuj_query()` (retrieve.py line 356) with the intent-classification + angle-template pattern. Copy `classify_query_intent()`, `_INTENT_RULES`, `_INTENT_ANGLES`, and update `decompose_query()`. This is self-contained and does not touch any other pipeline stage.  
*Effort: 2 hours*

**Port 2: FIX-3 — Combined query for Cohere**  
Change `_cohere_rerank(query, ...)` (retrieve.py line 832) to accept `sub_queries` and build `combined_query = query + " | " + sub_queries[:4]`. Sub-queries are already computed by `_dekomponuj_query()` earlier in the same function.  
*Effort: 30 minutes*

**Port 3: FIX-6 — Source hierarchy weighting**  
Copy `_PRIORITY_WEIGHTS` and `_get_priority_score()` into retrieve.py. Apply additive boost in `_izracunaj_skor()` (line 546): `skor += _get_priority_score(zakon_doc) * 100`. Replaces the hardcoded `skor += 30` law-match logic with something systematic.  
*Effort: 1 hour*

**Port 4: FIX-7 — Semantic conflict analysis**  
Copy `analyze_documents()` from multi_query_rag.py. Call it in main.py's HIGH path, after retrieve_documents() but before gpt-4o generation. Inject the conflict/exceptions result into the generation prompt. Skip for MEDIUM path (cost savings).  
*Effort: 1 hour*

**Port 5: FIX-8 — Structured JSON output for HIGH path**  
Rework main.py's gpt-4o prompt for HIGH path to return structured JSON. Keep the 12-section format that was designed for Serbian lawyers, but enforce JSON container so the frontend can parse citations programmatically. The human-readable narrative sections can remain inside the JSON.  
*Effort: 2-3 hours*

**Also do (not from multi_query_rag.py, but required):**  
- Delete dead code in main.py (klasifikuj_pitanje, 4 unused prompts, SYSTEM_PROMPT_QA, OBAVEZNE_SEKCIJE_QA): 30 minutes  
- Delete multi_query_rag.py after porting: 5 minutes

**Total Option C effort: 7-8 hours**

### Why Not Option A (wire multi_query_rag.py as primary)?

To make multi_query_rag.py production-safe, you would need to:
- Add a confidence gate (rebuild from scratch — multi_query_rag.py has no Pinecone cosine scores accessible post-generation)
- Add CRAG self-correction loop
- Add citation verification (`_proveri_halucinaciju`)
- Add 10 legal error pattern checks (`_verifikuj_pravne_greske`)
- Add PII stripping
- Add query TTL cache
- Reconnect domain-specific triggers (ZDI, KZ, ZPDG, Smart contract)
- Preserve the sub-query pollution fix (orig_score_map)
- Preserve the cross-law Cohere tie-breaker

This is rebuilding retrieve.py + main.py inside multi_query_rag.py. You end up with the same codebase, inverted. Nothing is gained by starting from the other side.  
*Effort: 15-20 hours. High regression risk.*

### Why Not Option B (delete multi_query_rag.py, port nothing)?

Multi_query_rag.py's FIX-6 (source hierarchy) is the most undervalued improvement in the codebase. A question about constitutional rights currently gives the Constitution zero priority over a municipal bylaw. A question answered by both a statute and a bylaw gives them equal weight. This is legally incorrect. The hierarchy weighting costs 1 hour to port and should not be thrown away.  
FIX-1 (intent decomposition) and FIX-7 (conflict detection) also have clear value. Deleting without porting means rebuilding them later at higher cost.

---

## Ranked Importance of Each Port

| # | Port | Legal impact | Dev cost | Verdict |
|---|------|-------------|----------|---------|
| 1 | FIX-6 source hierarchy | **HIGH** — constitutional questions return wrong ranking today | Low (1h) | Do immediately |
| 2 | FIX-7 conflict detection | **HIGH** — cross-article contradictions invisible today | Low (1h) | Do immediately |
| 3 | FIX-1 intent decomposition | MEDIUM — better sub-queries, especially for deadlines/jurisdiction | Medium (2h) | Do next sprint |
| 4 | FIX-8 structured JSON output | MEDIUM — frontend integration, audit logging | Medium (2-3h) | Do next sprint |
| 5 | FIX-3 combined Cohere query | LOW — marginal reranking improvement | Trivial (30min) | Do with FIX-1 |

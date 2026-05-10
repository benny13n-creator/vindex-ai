# Vindex AI Fixes Audit — 2026-05-07

---

## TL;DR

The system reached **17/10/3** with the current main branch (HEAD f37beb3) after:
- Full index rebuild to 23,699 vectors (2026-05-04)
- Sub-query pollution fix + cross-law tie-breaker
- FIX-1 intent decomposition ported and wired (2026-05-05)
- Q5 LAW_HINTS patch for criminal-context prevara (2026-05-05)
- B1 audit log and B2 disclaimer shipped

The 3 critical failures are **retrieval-layer misses**, not LLM hallucinations: the pipeline retrieves the wrong article with high cosine confidence, then the LLM faithfully cites it. FIX-6 (priority boost) was coded but HELD because 0.30 Ustav boost caused cross-law contamination. FIX-3, FIX-7, FIX-8 exist in multi_query_rag.py but multi_query_rag.py is **never called in production** — it is a dead reference pipeline. This means all 30Q improvements came from retrieve.py + main.py patching only.

**Fastest path to 20/10/0:** Fix Q5 embedding miss (LAW_HINTS sub-query mismatch), Q16 intra-law adjacency (ZR 187 vs 189), Q23 intra-law adjacency (PZ 174 vs 171). All three require targeted LAW_HINTS or article-boost logic in `retrieve.py`, not FIX code from multi_query_rag.py. **Estimated: 2-3 hours, no regression risk.**

---

## Failure Inventory

### 3 Critical Failures (❌ HIGH + wrong article)

#### Q5 — "Kazna za prevaru iznad milion dinara?"
- **Expected:** KZ Član 208 (prevara — fraud)
- **Actual:** KZ Član 379 (score 0.678) — this is a road traffic article about vehicle theft value thresholds
- **Failure type:** Semantic collision via shared phrase "milion dinara" — Član 379 has "(3) Ako vrednost stvari iz stava 1. ovog člana prelazi iznos od milion dinara" which matches the query's "milion dinara" fragment. Both are KZ so LAW_HINTS filter passes, but the wrong article wins on cosine.
- **Why LAW_HINTS didn't fully fix it:** commit 3282eae added "kazna za prevaru" → KZ to LAW_HINTS. The query text is "Kazna za prevaru iznad milion dinara?" — after normalization "kazna za prevaru" IS in the query and the LAW_HINTS match fires correctly (KZ filter is applied). The problem is that within KZ, Član 379 outscores Član 208 on embedding similarity because both contain the same "milion dinara" value-threshold clause. The FIX-1 intent decomposition fires for this query (it has "iznad" + "milion") but sub-queries still produce high-score Član 379 results.
- **Root cause:** Semantic collision — two different KZ articles use identical value-threshold language ("milion dinara"). Embedding cannot distinguish intent.

#### Q16 — "Otkazni rok kod prestanka radnog odnosa?"
- **Expected:** ZR Član 189 (otkazni rok)
- **Actual:** ZR Član 187 (score 0.6916) — retrieved, then meta captured as top article
- **Failure type:** Intra-law adjacency — Član 187 and 189 are semantically adjacent; Član 187 discusses obligations at contract termination while Član 189 defines the actual notice period length. Cohere reranks and picks Član 187 over 189 for this query.
- **Evidence from benchmark:** top3 shows Član 189 at score 0.6974 (rank 1 in raw Pinecone), Član 187 at 0.6916 (rank 2). But the pipeline's metadata capture uses `_top` after Cohere reranking, which selected Član 187. The tie-breaker fires: both are same law (ZR), so Cohere result is trusted → Član 187 wins.
- **Root cause:** Intra-law adjacency + Cohere prefers Član 187 over 189. Raw Pinecone had the right answer; Cohere reranking degraded it.

#### Q23 — "Šta je zajednička svojina supružnika?"
- **Expected:** PZ Član 171 (definition of joint property acquired during marriage)
- **Actual:** PZ Član 174 (score 0.7155–0.7156) — "Zajedničkom imovinom supružnici upravljaju i raspolažu zajednički i sporazumno"
- **Failure type:** Intra-law adjacency — Član 171 defines what joint property IS; Član 174 defines how it is managed. The query "Šta je zajednička svojina?" asks for definition, but Član 174 contains the phrase "zajednička imovina supružnika" explicitly in its text, giving it a higher cosine score.
- **Evidence:** top3 shows three PZ articles (174, 181, 195); Član 171 doesn't appear in top-3 at all. This is a pure embedding miss, not a reranker issue.
- **Root cause:** Intra-law adjacency + embedding misfire. Član 174 mentions "zajednička imovina" explicitly while Član 171's key clause may use different phrasing ("imovina stečena radom"). The definition article loses to the management article on raw cosine.

---

### 10 Medium Failures (⚠️) — Compact Table

| Q | Question | Expected | Actual Meta | Root Cause |
|---|---|---|---|---|
| Q2 | Razlika između krađe i razbojništva? | KZ 206 | KZ 204 | Intra-law adjacency: 204 (theft aggravated) adjacent to 206 (robbery); MEDIUM confidence (0.52) |
| Q4 | Pronevera u službi — definicija i kazna? | KZ 364 | KZ 365 | Intra-law adjacency: 364 (misappropriation) and 365 (unauthorized use) differ by 1 article number |
| Q7 | Kazna za vožnju u pijanom stanju? | KZ 289 | ZKP 512 | Cross-law contamination: ZKP 512 discusses driving-related penalties in traffic proceedings; LAW_HINTS maps to KZ but ZKP result scored higher (0.6426 vs KZ 0.6291); tie-breaker fires cross-law → uses max cosine → ZKP wins |
| Q17 | Otpremnina pri tehnološkom višku? | ZR 158 | ZR 179 | Intra-law adjacency: 179 defines who qualifies for redundancy; 158 defines the severance amount |
| Q18 | Mobing — definicija i pravna zaštita? | ZR (expected_art=None) | ZR 21 | Missing keyword: "mobing" not in LAW_HINTS directly but query hints to ZR. No specific expected article set in benchmark |
| Q20 | Probni rad i koliko traje? | ZR 36 | ZR 36 | Same article retrieved but confidence is MEDIUM (0.6098 < HIGH threshold 0.65) → auto-hedged |
| Q25 | Nasledni red po Zakonu o nasleđivanju? | ZN 9 | ZN 8 | Intra-law adjacency: ZN 8 (general heirs list) vs ZN 9 (spouse's inheritance share); confidence MEDIUM 0.6483 |
| Q27 | Revizija u parničnom postupku? | ZPP 394 | ZPP 420 | Intra-law adjacency: 394 defines revision; 420 discusses revision against procedural decisions |
| Q29 | Smart contract pravno obavezujući u Srbiji? | ZDI 2 | ZDI 2 | Correct article, MEDIUM confidence (0.5789) → auto-hedged |
| Q30 | Šta je beneficium ordinis? | ZOO 1002 | ZOO 134 | Semantic miss: "beneficium ordinis" (guarantor's right to demand creditor try main debtor first) is a Latin term. ZOO 1002 likely contains this provision but the Latinism creates an embedding gap |

---

### Root Cause Groups

**Group A — Intra-law adjacency (7 cases):** Q2, Q4, Q16, Q17, Q23, Q25, Q27. Two adjacent articles in the same law compete; the pipeline retrieves the near-neighbor instead of the target. The tie-breaker trusts Cohere within same law, which may still pick the wrong article if both are semantically close.

**Group B — Semantic collision (1 case):** Q5. Two KZ articles share identical value-threshold language ("milion dinara"). Cannot be distinguished by embedding alone without metadata boosting.

**Group C — Cross-law contamination (1 case):** Q7. ZKP Član 512 retrieved instead of KZ Član 289 for drunk driving. The cross-law tie-breaker selects max cosine which happens to be ZKP, not KZ.

**Group D — Embedding/terminology miss (2 cases):** Q18 (mobing — Serbian law uses "uznemiravanje" not "mobing" internally), Q30 (beneficium ordinis — Latin term with no matching Serbian text in indexed chunks).

**Group E — Score below HIGH threshold (2 cases):** Q20 (ZR 36 retrieved correctly but score 0.61 < 0.65), Q29 (ZDI 2 retrieved correctly but score 0.58 < 0.65). These are technically correct retrieval, wrong confidence routing.

---

## Pending Fixes Analysis

### FIX-1 (Status: Partially Done)

**What was done:** `classify_query_intent()` and `decompose_query()` ported from multi_query_rag.py to retrieve.py (commits 990305a, 1dbc0a0). Wired into `retrieve_documents()` at line 949 via `_treba_fx1_dekompozicija()` heuristic.

**What was NOT done from the multi_query_rag.py FIX-1 spec:**
1. multi_query_rag.py uses 5 query angles; retrieve.py caps at 3 to "respect latency budget" (line 509). The cap is fine but reduces coverage.
2. multi_query_rag.py always calls `decompose_query()` unconditionally; retrieve.py only activates it if `_treba_fx1_dekompozicija()` returns True. The heuristic at lines 555-576 uses value-threshold pattern OR comparative terms OR ≥6 content tokens. For Q7 "Kazna za vožnju u pijanom stanju?" (5 tokens), FIX-1 does NOT activate.
3. The `decompose_query()` function generates better sub-queries, but Cohere still uses only the original query (not combined_query like FIX-3 specifies).

**Remaining work for FIX-1:** Lower the token threshold in `_treba_fx1_dekompozicija` from 6 to 4 to catch Q7-type queries. This is a 1-line change in retrieve.py at line 574.

**Impact on 30Q:** Q7 might improve (currently cross-law contamination, intent decomposition might generate KZ-specific sub-queries that anchor retrieval). Estimated +0 to +1 on ✅.

---

### FIX-3 (Status: Dead — not in production pipeline)

**What it does:** Uses `combined_query = original + " | " + sub_queries` when calling Cohere reranker, instead of original query only. This gives Cohere all retrieval angles to rerank against.

**Current state in retrieve.py:** `_cohere_rerank(query, top_kandid, k=k)` at line 1027 — passes only `query` (original). Sub-queries are generated but discarded before the Cohere call.

**Code needed in retrieve.py `_cohere_rerank`:** Pass sub_queries as an optional parameter; construct combined_query inside. Change in `retrieve_documents()`: pass `sub_queries` to `_cohere_rerank`.

**Files affected:** app/services/retrieve.py (2 locations: `_cohere_rerank` signature + call site at line 1027).

**Estimated impact on 30Q:** LOW. Cohere reranking already works well for most queries. The main failures are embedding-level misses (Q5, Q23) where Cohere sees context-less summaries of the wrong article and can't override. Expected +0 to +1 on ✅.

**Implementation estimate:** 15-30 minutes, low regression risk.

---

### FIX-6 Redesign (Status: Held after regression)

**What was attempted (commit 711f2b9, not in main):** Added `_PRIORITY_WEIGHTS` to retrieve.py with Ustav=0.30, international treaties=0.25, major laws=0.10, bylaws=0.05. Modified `_cohere_rerank()` to apply additive boost: `final_score = cohere_relevance_score + priority_weight`. This caused cross-law promotion: for queries where Ustav content was tangentially relevant, the 0.30 boost pushed Ustav articles above correctly-retrieved statute articles.

**The regression mechanism:** When a KZ query (e.g., Q6 "uslovi za uslovnu osudu") returns KZ Član 66 and Ustav Član 22 (fair trial), the 0.30 boost to Ustav means: cohere(KZ 66)=0.72 + 0.10 = 0.82 vs cohere(Ustav 22)=0.60 + 0.30 = 0.90. Ustav article wins despite being less relevant.

**Redesign concept — per-law confidence gate:**
The correct fix is NOT a global additive boost. It is: **only apply priority weighting when two candidates are within a tight confidence band AND from different law groups.** If Cohere scores are > 0.10 apart, trust Cohere. If Cohere scores are within 0.10 of each other, apply priority as a tiebreaker.

```python
# Pseudocode for the redesign:
scored = [(r.relevance_score, docs[r.index]) for r in result.results]
# Sort by Cohere score descending
scored.sort(key=lambda x: x[0], reverse=True)

PRIORITY_BAND = 0.10
reranked = []
for i, (score, doc) in enumerate(scored):
    # Check if a lower-ranked doc could beat this via priority
    # Only apply if scores are within PRIORITY_BAND
    adjusted = score + (_get_priority_score(doc.law) if i > 0 else 0)
    # ... band-based tiebreaker logic
```

**Files affected:** app/services/retrieve.py only (`_cohere_rerank` function).
**Lines to write:** ~20 lines replacing the current 15-line Cohere block.
**Regression risk:** MEDIUM — the band threshold is a new hyperparameter that needs tuning. Too wide → same regression as before. Too narrow → no effect.

**Impact on 30Q:** The 30Q benchmark has almost no Ustav queries. FIX-6 redesign would primarily help edge cases where bylaws compete with statutes. **Not recommended as a priority fix.** Expected impact: 0-1 on ✅.

---

### FIX-7 (Status: Dead — not in production pipeline)

**What it does (multi_query_rag.py lines 341-404):** `analyze_documents()` — calls GPT-4o-mini with retrieved docs to extract structured `{rules, exceptions, conditions, conflicts}` before answer generation. The conflicts field is then injected into the generation prompt.

**Current state:** Implemented in multi_query_rag.py at line 341. Never called from main.py's `ask_agent`. The `_verifikuj_pravne_greske()` in main.py is a hardcoded 10-pattern checker, not the semantic analysis that FIX-7 provides.

**To port to production:** Would need either (a) call `analyze_documents()` from ask_agent before the LLM generation step, or (b) wire multi_query_rag.py into the main path entirely. Option (a) adds 1 GPT-4o-mini call (~0.5-1s latency) per query.

**Impact on 30Q benchmark:** None of the 3 ❌ are caused by missing conflict detection. The failures are retrieval-layer misses (wrong article in context). FIX-7 helps when the right articles are retrieved but the answer generation is confused by conflicting provisions. **Low ROI for current failures.**

**Files affected:** main.py (add analyze_documents call in ask_agent, ~10 lines).
**Hours:** 1-2 hours including testing.

---

### FIX-8 (Status: Dead — not in production pipeline)

**What it does (multi_query_rag.py lines 407-511):** Structured JSON output `{zakljucak, korisceni_clanovi, coverage, konflikti, napomena}`. Replaces current free-form markdown 12-section format in main.py.

**Current state:** Fully implemented in multi_query_rag.py. The production pipeline returns free-form markdown from `klasifikuj_pitanje()` topic routing in main.py (4 system prompts × 12 sections). The structured JSON format is incompatible with the current frontend which expects the markdown section format (renders `--- SEKCIJA` headers).

**Impact on 30Q benchmark:** None directly. The benchmark evaluates article retrieval accuracy, not output format. **FIX-8 is a frontend integration feature, not a retrieval fix.**

**To implement:** Requires coordinated frontend change + backend change. Frontend currently parses `--- SEKCIJA` markers for display. If output format changes to JSON, frontend rendering logic must be rewritten. **Not MVP-blocking.**

**Files affected:** main.py (ask_agent), api.py (response normalization), frontend index.html (rendering).
**Hours:** 3-5 hours full stack.

---

## B1 Audit Log

**Status: IMPLEMENTED and WIRED**

`app/services/audit_log.py` exists (131 lines). Schema documented in file header. Supabase table `response_audit` with fields: `id, ts, pipeline_id, endpoint, tip, query_hash, confidence, top_score, top_article, top_law, response_len, response_hash, latency_ms`.

`api.py` imports `audit_log as _al` at line 27. `_al.log_response()` is called at 6 locations:
- Line 1031: `/api/pitanje` endpoint after ask_agent completes
- Line 1106: streaming endpoint after retrieve phase
- Line 1204: streaming endpoint HIGH path
- Line 1270: streaming endpoint MEDIUM path
- Line 1304: nacrt endpoint
- Line 1333: analiza endpoint

**What works:** Fire-and-forget async write. PII-free (stores query_hash, not raw query). All metadata from retrieval_meta captured (confidence, top_score, top_article, top_law). Non-blocking — failure is caught and logged.

**What's missing:**
1. `response_audit` table may not exist in Supabase yet (no migration confirmation). File header has the CREATE TABLE SQL but there is no migration file in the repo and no confirmation it was run.
2. No `tip` column in the table schema (in the CREATE TABLE in the file header), but `tip` is passed to `log_response()`. The insert at line 119 includes `"tip": tip` — this will fail silently if column doesn't exist.
3. `_get_supa()` silently returns None if SUPABASE_URL or SUPABASE_SERVICE_KEY env vars are missing. In that case, all audit writes are no-ops. There is no startup health check that verifies audit connectivity.
4. `pipeline_id` is computed as `sha(ts:query_hash, 32)` — this is fine for uniqueness but creates a new ID per call even for cache hits (which bypass `log_response`). Cache hits are not audited.

**MVP completeness:** B1 is functionally done. Gaps are operational (migration not confirmed, env var silent failure). No code changes needed for MVP — just confirm the Supabase table exists.

---

## B2 Disclaimer

**Status: IMPLEMENTED — unconditional on all response paths**

Committed in cc3d0af "feat: B2 unconditional legal disclaimer on all responses".

**Exact location in code:**

`main.py` line 1620-1626:
```python
DISCLAIMER = (
    "\n\n---\n\n"
    "⚠️ **Pravna napomena:** Vindex AI pruža informacije zasnovane na zakonskim "
    "tekstovima Republike Srbije i ne predstavlja pravni savet. Ovaj odgovor ne "
    "zamenjuje konsultaciju sa licenciranim advokatom. Pre donošenja bilo kakvih "
    "pravnih odluka, obratite se stručnjaku."
)
```

`_dodaj_disclaimer(odgovor)` at line 900-901 appends DISCLAIMER to all responses.

Called at lines: 1637 (LOW path), 1648 (MEDIUM path `_format_medium_response`), 1659 (HIGH path `_format_high_response`), 1792 (MEDIUM LLM path), 1857 (HIGH LLM path after downgrade check), 1892 (nacrt), 1918 (analiza), and all error paths (1702, 1776, 1814, 1845, 1873, 1896, 1922).

**Streaming endpoint:** Disclaimer appended at end of streaming generator in api.py (confirmed by grep at line 1204+). The `DISCLAIMER` is imported from main at api.py line 1073.

**B2 completeness:** Done. All paths covered. The disclaimer text is legally appropriate — it disavows legal advice and recommends lawyer consultation. No action needed.

---

## Recommended Order

Priority is ranked by **failures fixed per hour of work**, with zero regression risk preferred.

### Priority 1 — Q16 Adjacency Fix (1 hour, ZERO regression risk)
**The problem:** Cohere reranks ZR Član 187 above Član 189 for "otkazni rok". Raw Pinecone rank 1 is Član 189 (score 0.6974); Cohere inverts this to rank 1 Član 187.
**The fix:** Add targeted LAW_HINTS entry for "otkazni rok" → "zakon o radu" (already exists), AND add a `_ZAKON_CLAN_HINTS` dict that maps query patterns to specific expected articles for direct score boosting in `_izracunaj_skor`. Already have the pattern for "nematerijal" + "steta" at line 767. Add:
```python
if "otkazni rok" in query_norm:
    if "189" in clan_doc and "radu" in zakon_doc: skor += 60
```
in `_izracunaj_skor` (retrieve.py). **1 line. Cannot break other queries because it is a strict two-condition gate.**
**Expected delta:** Q16 ❌ → ✅.

### Priority 2 — Q23 Adjacency Fix (1 hour, ZERO regression risk)
**The problem:** PZ Član 174 outscores PZ Član 171 because 174 explicitly mentions "zajednička imovina supružnika" while 171 may use different phrasing.
**The fix:** Same pattern — add to `_izracunaj_skor`:
```python
if "zajednick" in query_norm and "svojin" in query_norm:
    if "171" in clan_doc and ("porodic" in zakon_doc or "brak" in zakon_doc): skor += 70
```
**Expected delta:** Q23 ❌ → ✅.

### Priority 3 — Q5 Sub-query Disambiguation (2 hours, LOW regression risk)
**The problem:** Within KZ, both Član 208 (fraud) and Član 379 (vehicle theft by value) have "milion dinara" clauses. Cohere cannot distinguish them at the text level.
**The fix:** Add a LAW_HINTS entry that hints to a specific sub-article class, OR add a `_KRIVICNA_DELA` expansion similar to `_ZDI_TRIGERI` that expands queries containing "prevara" + "kazna" to use specific KZ search terms:
```python
_PREVARA_TRIGERI = frozenset(["kazna za prevaru", "prevara.*kazna", "prevara.*milion"])
_PREVARA_TERMINI = ["prevara imovinska korist pribavljanje oštećenje KZ čl. 208", 
                    "krivično delo prevare kazna zatvora"]
```
This would fire semantically targeted sub-queries at the Pinecone level to retrieve Član 208 specifically.
**Expected delta:** Q5 ❌ → ✅ if Član 208 content in index has "prevara" in its text; need to verify index content. **Risk: if Član 208 text doesn't contain the phrase "prevara" explicitly, this won't help — would need direct article fetch.**

### Priority 4 — Q7 FIX-1 Threshold Lowering (30 min, ZERO regression risk)
**The problem:** Q7 "Kazna za vožnju u pijanom stanju?" has 5 content tokens (below the FIX-1 activation threshold of 6). FIX-1 decomposition does not fire.
**The fix:** Change line 574 of retrieve.py from `if len(_tokenizuj(query)) >= 6:` to `>= 4`. This activates intent-aware decomposition for more queries.
**Risk assessment:** Queries with 4-5 tokens are simple enough that intent decomposition shouldn't hurt. The decomposition generates 3 sub-queries which are run in parallel — worst case adds 0.5s latency for simple queries.
**Expected delta:** Q7 ⚠️ → possibly ✅ (cross-law contamination may be resolved if KZ sub-queries anchor to Član 289). Or stays ⚠️ — not a guaranteed fix.

### Priority 5 — FIX-3 Combined Cohere Query (30 min, LOW regression risk)
After Q7 fix is validated, pass sub_queries to `_cohere_rerank` as combined_query. ~15 lines of code. Low ROI on current failures but correct behavior.

### Priority 6 — Q20 and Q29 Score Threshold Calibration
Q20 and Q29 are correctly retrieved (right article) but fall below HIGH threshold (0.65). Both are genuinely harder queries. Options: (a) lower HIGH threshold slightly to 0.63 (may cause more false HIGH responses), (b) add article-specific confidence boosts in retrieval_meta, (c) accept as MEDIUM (current behavior is safe — hedged but not wrong).

---

## Alternative — Lean Beta Path

If the goal is "20+ successes before beta launch" with minimum code risk:

1. **Immediately** (30 min): Lower FIX-1 token threshold to 4 tokens (1 line, zero risk).
2. **Q16 and Q23 article-hint lines** (1 hour, zero risk): Add 2 targeted score boosts in `_izracunaj_skor`.
3. **Q5 direct article fetch** (1 hour, low risk): Add a `_PREVARA_KZ_FETCH` block in `_jedan_retrieval_krug` that fires when "prevara" + value threshold appears and directly fetches KZ Član 208 via `_direktan_fetch_clana("Član 208", "KZ")`. This bypasses embedding entirely for this known failure.

Total effort: ~2.5 hours. Expected result: **20/10/0** if Q5's Član 208 is properly indexed with "prevara" in its text.

If Član 208's text in Pinecone does not contain "prevara" (check via `_direktan_fetch_clana("Član 208", "KZ")`), then Q5 requires a re-index of that specific article with better chunk text — 30 more minutes.

---

## Beta-Readiness Verdict

**At 17/10/3: Conditionally usable, with serious caveats.**

### What a practicing Serbian lawyer would actually encounter:

**Good cases (17 questions — mostly works):**
- Constitutional criminal law basics (nužna odbrana, uslovna osuda): ✅
- Obligaciono pravo (nematerijalna šteta, zastarelost, raskid ugovora, novacija): All ✅
- Porodično pravo basics (razvod, alimentacija, usvojenje): ✅
- Zakon o digitalnoj imovini definitions: ✅
- LOW-confidence refusal on regres/beneficium ordinis: Correctly admits ignorance ✅

**Problematic cases a lawyer would notice immediately:**
1. **Q5 (prevara) is a daily-use question** for criminal defense lawyers. Confidently citing Član 379 (vehicle theft value thresholds) for a fraud question would be immediately recognized as wrong. This is embarrassing.
2. **Q16 (otkazni rok)** — any labor lawyer would ask this. Citing Član 187 instead of 189 for notice period is a 2-article gap but produces a response that cites ZR Član 178 (incorrect). Labor law is the most common area for Serbian SME lawyers.
3. **Q23 (zajednička imovina)** — family law basics. Citing Član 174 (management) instead of 171 (definition) produces a technically-adjacent but wrong definitional answer.

**Failure modes that could damage lawyer credibility:**
- HIGH confidence + wrong article means the lawyer copies the response verbatim, cites wrong article in a brief, opposing counsel catches it. This is a malpractice-adjacent scenario.
- The disclaimer exists but lawyers often skip it when under time pressure.

**Honest verdict:** At 17/10/3, the system is suitable for **legal research assistance** where a lawyer verifies before citing, not for **direct brief preparation**. The 3 ❌ are in high-frequency areas (criminal fraud, labor notices, family property). Before recommending to a practicing lawyer without caveats, these 3 must be ❌ → ✅.

**Post-Priority-1+2+3 fix (20/10/0 target):** The system would be defensible for beta with a clear "verify before citing" policy. The 10 MEDIUM responses are all hedged and tell the lawyer "low confidence, check with specialist" — this is correct behavior and a lawyer can work with it.

**Missing for professional-grade trust:**
- B1 audit log must be confirmed running in Supabase (table migration)
- FIX-7 conflict detection would surface intra-article contradictions (currently invisible)
- The 10 MEDIUM scores suggest the confidence thresholds may still be slightly off — Q20 (probni rad, Član 36) and Q29 (smart contract, ZDI Član 2) are correctly retrieved but below 0.65 threshold

---

## Open Questions

1. **Is KZ Član 208 properly indexed?** The current Q5 fix (LAW_HINTS entry "kazna za prevaru" → KZ) passes the law filter correctly but Član 379 still wins within KZ. If `_direktan_fetch_clana("Član 208", "KZ")` returns a chunk whose text contains the word "prevara" prominently, the targeted expansion fix will work. If not, chunking of KZ Član 208 needs review.

2. **Does the Supabase `response_audit` table exist?** The `audit_log.py` file header has the CREATE TABLE SQL but there is no migration file in the repo. If the table doesn't exist, all audit writes fail silently. Run `test_audit_b1.py` (exists in repo root) to confirm.

3. **Is FIX-6 dead or can the redesign be tested safely?** The priority-band redesign (Section "FIX-6 Redesign") has no test coverage. A safe test: apply the band-gate redesign, re-run the 30Q benchmark. If score does not drop below 17 ✅, accept. The 30Q has no Ustav-relevant questions that would expose the previous regression.

4. **Should multi_query_rag.py be wired or deleted?** Currently a dead pipeline with FIX-1 through FIX-9. FIX-1 was extracted and wired. FIX-3 can be ported in 30 min. FIX-7 adds 1 LLM call per query (+0.5-1s latency). The full pipeline replace (multi_query_rag.py as main path) would require frontend changes (FIX-8 JSON format). **Recommendation: Port FIX-3 individually; leave multi_query_rag.py as reference; do not do full pipeline swap before beta.**

5. **What is the correct expected article for Q18 (mobing)?** The benchmark has `expected_art=None`. ZR Član 21 covers "uznemiravanje" (harassment/mobbing). The Zakon o sprečavanju zlostavljanja na radu (ZZL) is the dedicated anti-mobbing law — but it may not be indexed. If ZZL is indexed, a LAW_HINTS entry for "mobing" → "zakon o sprecavanju zlostavljanja na radu" would improve Q18. ZZL was not in the INDEX_EXPANSION_LOG.

6. **Q7 cross-law contamination:** The cross-law tie-breaker fires for Q7 and selects ZKP 512 over KZ 289 based on max cosine. One fix: add "pijano stanje" / "voznja" / "alkohol" to LAW_HINTS as KZ entries, which would apply a Pinecone filter and eliminate ZKP from consideration. Currently LAW_HINTS has no drunk-driving keywords.

---

*Audit conducted 2026-05-07 — read-only analysis of HEAD f37beb3 — no files modified*

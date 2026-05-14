# Phase 1 Codebase Compatibility Audit — Sudska Praksa Integration

**Audit date:** 2026-05-10
**Branch:** main / HEAD: 52776fb (post-P0.4)
**Mode:** READ-ONLY
**Scope:** Vindex AI legal RAG — `C:\Users\Benny\moj_prvi_agent\src\moj_prvi_agent\legal-agent\`

---

## Section 1 — Inventory

### Module Map

| File | Lines | Role |
|------|-------|------|
| `main.py` | ~1940 | ask_agent v3, 4-type classifier, prompt templates, DISCLAIMER |
| `api.py` | ~1539 | FastAPI entry: auth, credits, all endpoints |
| `app/services/retrieve.py` | ~1329 | Pinecone RAG v3: embedding, retrieval, Cohere, CRAG, confidence gate |
| `app/services/multi_query_rag.py` | 644 | Legacy multi-query pipeline — tracked but NOT primary path |
| `app/services/audit_log.py` | 131 | B1 fire-and-forget audit → Supabase |
| `run_test_30q.py` | ~316 | 30Q benchmark runner + self-eval |
| `semantic_chunker.py` | 254 | Article-boundary chunker (Član N regex) |
| `ingest_laws.py` | — | One-time ingestion: ZOO/ZR/PZ/ZN laws |
| `ingest_kz.py` | — | One-time ingestion: KZ (Krivični zakonik) |
| `test_audit_b1.py` | — | B1 smoke test |
| `test_disclaimer_b2.py` | ~66 | B2 smoke test |

### Entry Points

- **FastAPI app:** `api.py` — `app = FastAPI(title="Vindex AI", ...)` (line 336)
- **Agent logic:** `main.py` — `ask_agent(pitanje, history)` (line 1678)
- **Retrieval:** `app/services/retrieve.py` — `retrieve_documents(query, k=6)` (line 947)
- **Chunker:** `semantic_chunker.py` — `podeli_zakon_na_chunkove(tekst, zakon_naziv)` (line 139)
- **Gate logic:** `app/services/retrieve.py` — `get_confidence_level(score)` (line 312)
- **Ingest/upsert:** `ingest_laws.py`, `ingest_kz.py`
- **Test runner:** `run_test_30q.py` — `run_tests()` (line 190)

---

## Section 2 — Pinecone Retrieval Layer Audit

### Primary Query Function

**`_semanticka_pretraga` — retrieve.py lines 323–334:**
```python
def _semanticka_pretraga(query: str, k: int = 10, filter_zakon: Optional[str] = None) -> list:
    index = _get_index()
    vektor = _ugradi_query(query)
    filter_dict = {"law": {"$eq": filter_zakon}} if filter_zakon else None
    try:
        matches = index.query(vector=vektor, top_k=k, include_metadata=True, filter=filter_dict).matches
        ...
        return matches
    except Exception as exc:
        ...
        return []
```

**Current filter field:** `law` (string equality). One filter per call. No `namespace`, no `doc_type`.

**Secondary query (zero-vector direct fetch) — `_direktan_fetch_clana` — lines 347–357:**
```python
def _direktan_fetch_clana(label_clana: str, zakon: Optional[str] = None) -> list:
    index = _get_index()
    filter_dict: dict = {"article": {"$eq": label_clana}}
    if zakon:
        filter_dict = {"$and": [{"article": {"$eq": label_clana}}, {"law": {"$eq": zakon}}]}
    dummy = [0.0] * 3072
    return index.query(vector=dummy, top_k=5, include_metadata=True, filter=filter_dict).matches
```

### Upsert Metadata Schema

From `semantic_chunker.py` output (lines 144–159) — one chunk dict:
```python
{
    "id":   "<MD5 hash>",
    "text": "<embedding text, ≤300 chars>",
    "metadata": {
        "zakon":        "ZOO",
        "clan":         200,
        "stav":         1,
        "parent_id":    "ZOO_200",
        "parent_text":  "<full article text, ≤3000 chars>",
        "tekst_preview": "<first 100 chars>",
        # backward-compat fields used by LAW_HINTS filter:
        "law":     "zakon o obligacionim odnosima",
        "article": "Član 200",
        "text":    "<statement text, ≤300 chars>",
    }
}
```

**`doc_type` field:** NOT present. Every vector currently has implicit `doc_type = "zakon"`.

### Constants (retrieve.py)

| Constant | Line | Value |
|----------|------|-------|
| `EMBEDDING_MODEL` | 37 | `"text-embedding-3-large"` |
| `PINECONE_INDEX` | 38 | `"vindex-ai"` |
| `CONFIDENCE_HIGH_THRESHOLD` | 308 | `0.65` |
| `CONFIDENCE_MEDIUM_THRESHOLD` | 309 | `0.52` |
| `_ZDI_TRIGERI` | 833 | frozenset of 10 crypto keywords |
| `_KZ_TRIGERI` | 836 | frozenset of 7 criminal-law keywords |
| `_ZPDG_TRIGERI` | 839 | frozenset of 5 tax-crypto keywords |
| `_ZOO_FALLBACK_CLANOVI` | 846 | `["Član 154", "Član 155", "Član 200", "Član 189"]` |
| `_PREVARA_KZ_TERMINI` | 852 | `["krivično delo prevare lažnim prikazivanjem imovinska korist KZ 208"]` |
| `dummy dim` | 353 | `[0.0] * 3072` (hardcoded in `_direktan_fetch_clana`) |

### Phase 1 Verdict — Adding `doc_type` Filter

**Complexity: TRIVIAL**

The current `_semanticka_pretraga` already accepts an arbitrary `filter_dict`. Adding a `doc_type` parallel filter requires:

1. Add `doc_type: Optional[str] = None` parameter to `_semanticka_pretraga` (~3 lines)
2. Extend `filter_dict` to `{"$and": [{"law": ...}, {"doc_type": ...}]}` when both present (~4 lines)
3. Add `doc_type="zakon"` to upsert metadata in `semantic_chunker.py` (~1 line)
4. Add `doc_type="sudska_praksa"` to the new case-law chunker (~1 line)
5. Update `_jedan_retrieval_krug` to run a parallel `doc_type=sudska_praksa` branch (~15 lines)

**Estimated change: ~25 lines.** Zero architectural risk. The Pinecone `$and` filter operator is already used in `_direktan_fetch_clana` (line 351–352).

---

## Section 3 — Chunker (v3) Coupling Audit

### File: `semantic_chunker.py`

**Main function signature (line 139):**
```python
def podeli_zakon_na_chunkove(tekst: str, zakon_naziv: str) -> list[dict]:
```

**Input:** Raw plain text of a law (`tekst`) + short law identifier (`zakon_naziv`, e.g. `"ZOO"`). Input is pre-cleaned plain text — NOT HTML.

**Article boundary detection — lines 164–167:**
```python
clan_pattern = re.compile(
    r'(?m)^[ \t]*(?:Član|ČLAN|Čl\.|ČL\.)\s+(\d+[a-zA-Zа-яА-Я]?)\b',
    re.UNICODE,
)
```

`"Član N"` detection is **core** to the chunker. There is no config flag to disable it. The chunker also detects section headers (Glava, Deo, Odeljak) and paragraph structure, but the fundamental split is on `Član N`.

**Constants (lines 43–46):**
```
MIN_STAV_DUZINA  = 60
MAX_STAV_DUZINA  = 300
MAX_PARENT_DUZINA = 3000
STUB_THRESHOLD   = 200
```

**Output schema** — each chunk is a `dict` matching the upsert schema shown in Section 2.

### Case-Law Applicability

A court decision (presuda/rešenje) has narrative structure: header (sud, broj, datum, sastav veća) → "U ime naroda" → činjenice → obrazloženje → dispozitiv. There is NO `Član N` hierarchy. The `clan_pattern` regex would match zero times on a decision text.

**Verdict: NEW MODULE `chunker_case_law.py`**

Rationale:
- The `clan_pattern` detection is not a config flag — it is the structural backbone of `podeli_zakon_na_chunkove`. Inserting a `doc_type` switch would turn a clean single-purpose function into a branchy monster.
- Case-law chunks need different metadata fields (`court`, `decision_number`, `decision_date`, `legal_area`, `cited_articles[]`) that don't exist in the current schema.
- Section-header detection (`_SECTION_HEADER_RE`, lines 50–62) would need to be rewritten entirely for decisions.
- A parallel `chunker_case_law.py` follows the same pattern as `ingest_kz.py` vs `ingest_laws.py` — law-specific ingestion logic, shared Pinecone index.

The v3 constants (`MIN_STAV_DUZINA`, `MAX_PARENT_DUZINA`) can be reused in the new chunker.

---

## Section 4 — Pipeline Async-Readiness Audit

### Call Chain

```
/api/pitanje (async def)
  └─ pokreni(ask_agent, pitanje, history)          ← asyncio.to_thread wraps sync
       └─ ask_agent(pitanje, history)               ← sync def
            ├─ retrieve_documents(query, k=10)      ← sync def
            │    ├─ _ugradi_query(query)            ← sync (OpenAI embeddings.embed_query)
            │    ├─ _jedan_retrieval_krug(...)      ← sync, uses ThreadPoolExecutor internally
            │    │    └─ _semanticka_pretraga(...)  ← sync (Pinecone index.query)
            │    ├─ _cohere_rerank(...)             ← sync (Cohere client.rerank)
            │    └─ _dohvati_parent_text(...)       ← sync (reads Pinecone metadata)
            └─ _pozovi_openai(...)                  ← sync (OpenAI chat.completions.create)
```

**All I/O is synchronous** — no `await` inside `ask_agent` or `retrieve_documents`. Concurrency is handled by:
- `asyncio.to_thread` at the API layer (`pokreni`, line 474–476)
- `ThreadPoolExecutor` inside `_jedan_retrieval_krug` for parallel Pinecone queries

### Adding `asyncio.gather([retrieve(zakon), retrieve(praksa)])`

Two approaches:

**Option A — Add second sync retrieval inside `_jedan_retrieval_krug` (RECOMMENDED)**
Zero async refactoring. `_jedan_retrieval_krug` already uses `ThreadPoolExecutor` and `as_completed`. Adding a parallel `doc_type=sudska_praksa` branch is a ~15-line addition. The results from both branches are deduplicated and ranked together in `_izracunaj_skor`.

**Option B — `asyncio.gather` at the `retrieve_documents` level**
Would require making `retrieve_documents` async, then `ask_agent` async, then removing `asyncio.to_thread` wrapper. Change count: ~4 functions need `async def`. This is unnecessary complexity given Option A.

**Verdict: TRIVIAL — Option A. No async refactoring needed.** The ThreadPoolExecutor-inside-sync-function pattern already handles parallel Pinecone calls.

---

## Section 5 — Confidence Gate Scalability Audit

### Function: `get_confidence_level` — retrieve.py lines 312–318

```python
def get_confidence_level(score: float) -> str:
    """Map Pinecone cosine score to HIGH / MEDIUM / LOW."""
    if score >= CONFIDENCE_HIGH_THRESHOLD:   # 0.65
        return "HIGH"
    elif score >= CONFIDENCE_MEDIUM_THRESHOLD:  # 0.52
        return "MEDIUM"
    return "LOW"
```

**Input:** Single float (top Pinecone cosine score of the top-ranked result after Cohere reranking).
**Output:** String band ("HIGH" / "MEDIUM" / "LOW").
**Assumption:** Single-source. One call, one band, one top result.

### Gating Usage in `ask_agent` (main.py)

```python
confidence = retrieval_meta["confidence"]   # set by retrieve_documents
if confidence == "LOW":   → instant refusal (no LLM)
if confidence == "MEDIUM": → hedged LLM call
else (HIGH):               → full LLM call
```

### Two-Source Extension

For Phase 1, we need:
- `zakon_band`: confidence band for the top zakoni result
- `praksa_band`: confidence band for the top sudska_praksa result

`get_confidence_level` is a pure function of a single score — it already handles both independently. The change required is in `retrieve_documents`:

1. Return two separate top-scores from `_jedan_retrieval_krug` (one per `doc_type`)
2. Call `get_confidence_level` twice — no modification to the function itself
3. Return `{"zakon_confidence": ..., "praksa_confidence": ...}` in `retrieval_meta`
4. `ask_agent` decides synthesis strategy based on both bands

**Estimated change: ~20 lines in `retrieve_documents` + ~30 lines in `ask_agent` synthesis logic.** `get_confidence_level` itself: 0 lines changed.

---

## Section 6 — Response Schema Audit

### `normalizuj_rezultat` — api.py lines 479–492

```python
def normalizuj_rezultat(rezultat: dict, credits_remaining: Optional[int] = None) -> dict:
    resp: dict = {}
    if not isinstance(rezultat, dict):
        resp["odgovor"] = str(rezultat)
    elif rezultat.get("status") == "success":
        resp["odgovor"] = rezultat.get("data", "")
    else:
        resp["odgovor"] = rezultat.get("message", "Došlo je do greške...")
    if credits_remaining is not None:
        resp["credits_remaining"] = credits_remaining
    return resp
```

**Current API response shape:** `{"odgovor": "<text>", "credits_remaining": N}` — flat, text-only. No `citations`, `confidence_band`, `source_type`, or `case_metadata` fields.

### Adding Case-Law Citation Fields

**Would break current consumers?** The API currently returns only `odgovor`. Adding new optional fields (`source_type`, `case_metadata`) is backward-compatible for any consumer that reads only `odgovor`. However:
- Frontend at `vindex.rs` — **frontend repo not in scope** (not present in this repo). Verify independently.
- `/api/bot/ask` (Telegram bot) — uses same `normalizuj_rezultat`, returns `{"odgovor": ...}`. Adding fields is backward-compatible since the bot reads only `odgovor`.
- `run_test_30q.py` — calls `ask_agent` directly (not via API), reads `result.get("confidence")` etc. Not affected by API schema changes.

**`PitanjeReq` model — api.py lines 410–413:**
```python
class PitanjeReq(BaseModel):
    pitanje: str = Field(..., min_length=3, max_length=2000)
    history: List[HistoryItem] = Field(default_factory=list, max_length=3)
```

No `source_filter` or `doc_type` preference field. Adding an optional `include_praksa: bool = False` would be backward-compatible.

---

## Section 7 — Test Infrastructure Audit

### `run_test_30q.py` — QUESTIONS list (lines 27–96)

Each entry is a 4-tuple: `(question, expected_law_hint, expected_article_hint, category)`

```python
QUESTIONS = [
    ("Koja je kazna za osnovnu krađu?",            "KZ", "203", "KAT1"),
    ("Koja je razlika između krađe i razbojništva?","KZ", "206", "KAT1"),
    ("Koja je kazna za tešku krađu?",              "KZ", "204", "KAT1"),
    ("Šta je pronevera u službi i koja je kazna?", "KZ", "364", "KAT1"),
    ("Kazna za prevaru iznad milion dinara?",       "KZ", "208", "KAT1"),
    ...
    ("Mobing - definicija i pravna zaštita?",      "zakon o radu", None, "KAT4"),  # no exp_art
    ...
    ("Šta je beneficium ordinis?",                 "zakon o obligacionim odnosima", "1002", "KAT6"),
]
```

### `_self_eval` — run_test_30q.py lines 149–186

```python
def _self_eval(result: dict, top3: list[dict], exp_law: str, exp_art: str | None) -> tuple[str, str]:
    confidence  = result.get("confidence", "UNKNOWN")
    top_article = result.get("top_article", "")
    response    = result.get("data", "")

    if confidence == "LOW":
        return "✅", f"LOW: pouzdan odmah odbio (score={result.get('top_score',0):.3f})"

    if confidence == "MEDIUM":
        return "⚠️", f"MEDIUM: hedged odgovor | meta-član: {top_article} | očekivano: Član {exp_art}"

    if confidence == "HIGH":
        art_m = re.search(r"(\d+[a-zA-Z]?)", top_article or "")
        meta_art = art_m.group(1) if art_m else ""
        cited_in_resp = re.findall(r"[Čč]lan\s+(\d+[a-zA-Z]?)", response)
        if exp_art == meta_art or exp_art in cited_in_resp:
            return "✅", f"HIGH: tačan član {exp_art} citiran"
        return "❌", f"HIGH + POGREŠAN ČLAN: meta={top_article} citiran={cited_in_resp} očekivano=Član {exp_art}"
```

### Schema Clarity Check — **TEST DESIGN DEFECT FOUND**

Each QUESTIONS tuple has one field for expected article: `expected_article_hint`. This field is used both as:
- **ground-truth citation** (what the LLM SHOULD answer — e.g. "203" for osnovna krađa)
- conflated with `meta_art` (what `retrieve_documents` returns as `top_article` — e.g. "210" for the same question)

`_self_eval` passes if `exp_art == meta_art` **OR** `exp_art in cited_in_resp`. This means Q01 passes because "203" appears in the LLM response even though `top_article="Član 210"`. The distinction is implicit in the OR logic, not explicit in the data schema.

**Flag:** The tuple has no separate `meta_article_expected` field. The runner reports `top_art_meta=Član 210` alongside `expected=Član 203` in the output, which caused the P0.4 smoke test spec to use KZ/210 as expected when it should have been KZ/203. **30P should not inherit this ambiguity.** Recommend:

```python
# 30P entry schema:
{
    "question":            "...",
    "expected_law":        "KZ",
    "ground_truth_art":    "203",   # what LLM must cite — the answer
    "meta_article_hint":   "210",   # what retrieve typically surfaces as top_article (informational only)
    "category":            "KAT1",
}
```

### 30P Extension

The runner is easily extensible — `run_tests()` iterates over `QUESTIONS` and `_self_eval` is a pure function. To add a 30P suite: create a parallel `PRAKSA_QUESTIONS` list with case-law-specific fields (`case_number`, `court`, `expected_rule`), reuse `_self_eval` or write a variant, write results to `docs/VINDEX_PRAKSA_TEST.md`. No structural rebuild required.

---

## Section 8 — LAW_HINTS / Keyword Routing Audit

### `LAW_HINTS` — retrieve.py lines 42–185 (complete)

```python
LAW_HINTS = {
    # Zakon o radu (10 entries)
    "prestanak radnog odnosa", "otkaz ugovora o radu", "ugovor o radu",
    "tehnoloski visak", "visak zaposlenih", "radni odnos",
    "disciplinska", "otkaz", "zarada", "rad"  → "zakon o radu"

    # Porodični zakon (5 entries)
    "staratelj", "aliment", "porodic", "razvod", "brak", "dete"  → "porodicni zakon"

    # KZ / criminal law (20+ entries)
    "krivicni postupak" → ZKP
    "krivicni","krivicno","krivic","kradj","razbojn","ubistvo","ubojstv",
    "uslovna osuda","uslovni otpust","zatvorska kazna","novcan kazna kz",
    "opojne droge","narkotik","iznuda","ucena","silovanje","nasilje u porodici"  → "KZ"
    "kazna za prevaru","krivicna prevara","prevara krivicn"  → "KZ" (guarded)

    # ZPP (4 entries): "parnica","parnic","tuzba","presuda"
    # ZIO (3 entries): "obezbedjenj","izvrsenje","izvrs"
    # ZOO (18 entries): "imovinska steta","nematerijalna steta","izgubljena dobit",
    #   "izmakla korist","prekid zastarelosti","zastarel","rok zastarelosti",
    #   "kada zastari","zastarelo potrazivanje","obligaci","naknada","ugovor","steta"
    # ZPD (6 entries): "privredn","drustv","apr","registracija","osnivanje","zastupnik"
    # Upravni (8 entries): ZUS + ZUP
    # Diskriminacija (3): "diskriminacij","teret dokazivanja","nejednako postupanje"→ ZR
    # ZVP (1): "vanparnic"
    # ZN (2): "nasledj","ostavina"
    # Ustav (1): "ustav"
    # ZZP (1): "potrosac"
    # ZSPNFT (8 entries): AML/KYC
    # ZDI (17 entries): crypto/blockchain/NFT/smart contract
    # Web3 criminal → KZ (7 entries): "kripto ukraden","novcanik hakovan", etc.
    # ZPDG (5 entries): crypto tax
}
```

### `_prepoznaj_zakon` — retrieve.py lines 277–283

```python
def _prepoznaj_zakon(query: str) -> Optional[str]:
    q = _normalizuj(query)
    sortirani = sorted(LAW_HINTS.items(), key=lambda x: len(x[0]), reverse=True)
    for kljuc, zakon in sortirani:
        if _normalizuj(kljuc) in q:
            return zakon
    return None
```

**Consumed at query time** — called inside `retrieve_documents` (line ~980) to set the `filter_zakon` passed to `_jedan_retrieval_krug`. This is a **Pinecone hard filter** — `{"law": {"$eq": zakon}}`. Misclassification excludes the correct law entirely.

### Routing Architecture for Case Law

`LAW_HINTS` maps keyword → specific law name. For case law, queries route by **legal area** (oblast), not specific law. A query like "Može li radnik tražiti nadoknadu zbog mobbinga?" hits the ZR branch, but the relevant sudska praksa may span ZR + ZOO + KZ depending on the ruling.

The current architecture conflates "which law to filter" with "what topic is this". This works for law-only retrieval because each zakoni result has a `law` field matching the LAW_HINTS values.

**Recommendation: Parallel `AREA_HINTS` — NOT a unified `TOPIC_ROUTER`**

A unified TOPIC_ROUTER that replaces LAW_HINTS would require rewriting the entire routing logic and risk regressions in the 30Q suite. Instead:

```python
AREA_HINTS = {
    # Maps normalized keywords → legal area label used as doc_type filter complement
    "radni odnos": "radno_pravo",
    "otkaz":       "radno_pravo",
    "steta":       "obligaciono_pravo",
    "ugovor":      "obligaciono_pravo",
    "krivicn":     "krivicno_pravo",
    "porodic":     "porodicno_pravo",
    ...
}
```

`AREA_HINTS` feeds a `legal_area` filter on the `doc_type=sudska_praksa` branch only. `LAW_HINTS` continues to drive the `doc_type=zakon` branch unchanged. The two systems are orthogonal.

---

## Section 9 — Configuration / Environment Audit

### `"vindex-ai"` Hardcoded Locations

| File | Line | Context |
|------|------|---------|
| `app/services/retrieve.py` | 38 | `PINECONE_INDEX = "vindex-ai"` (constant, used as fallback) |
| `app/services/retrieve.py` | 214 | `index_name = os.getenv("PINECONE_INDEX_NAME", PINECONE_INDEX)` ← reads env first |
| `api.py` | ~524 | `pc.Index("vindex-ai")` in `/test-pinecone` endpoint |
| `api.py` | ~584 | `pc.Index("vindex-ai")` in `/api/diagnose` endpoint |

**Note:** The primary path (`_get_index`, line 204) reads `PINECONE_INDEX_NAME` from env with fallback. The two diagnostic endpoints hardcode the name directly — minor risk.

### `3072` (Embedding Dimension) Hardcoded Locations

| File | Line | Context |
|------|------|---------|
| `app/services/retrieve.py` | 353 | `dummy = [0.0] * 3072` in `_direktan_fetch_clana` |

Only one location. The primary embedding path uses `OpenAIEmbeddings(model=EMBEDDING_MODEL)` and lets the model determine dimensions implicitly. The dummy vector is used for metadata-only queries (zero-vector fetch) — this would need updating if the embedding model changes.

### `"text-embedding-3-large"` Hardcoded Locations

| File | Line | Context |
|------|------|---------|
| `app/services/retrieve.py` | 37 | `EMBEDDING_MODEL = "text-embedding-3-large"` (constant) |
| `app/services/retrieve.py` | 239 | `OpenAIEmbeddings(model=EMBEDDING_MODEL)` ← reads constant |
| `api.py` | ~526 | `OpenAIEmbeddings(model="text-embedding-3-large")` in `/test-pinecone` |
| `api.py` | ~592 | `OpenAIEmbeddings(model="text-embedding-3-large")` in `/api/diagnose` |

**If model changes:** The primary path changes in 1 line (retrieve.py:37). The two diagnostic endpoints need manual updates. Ingest scripts would also need updating (currently use the same `EMBEDDING_MODEL` constant).

### Pinecone Env Vars (retrieve.py)

| Env Var | Line | Usage |
|---------|------|-------|
| `PINECONE_API_KEY` | 207 | Client init |
| `PINECONE_HOST` | 213 | Direct host connection (preferred path) |
| `PINECONE_INDEX_NAME` | 214 | Index name, with `PINECONE_INDEX` fallback |
| `COHERE_API_KEY` | 255 | Optional Cohere reranker |

---

## Section 10 — Surprises and Risks

### 1. `multi_query_rag.py` — Tracked but Dead in Production

`app/services/multi_query_rag.py` (644 lines) is git-tracked and imported by some test scripts but is **not called** from `ask_agent`, `retrieve_documents`, or any API handler. The production path uses `retrieve.py` exclusively. Multi-query decomposition is re-implemented in `retrieve.py` via `_dekomponuj_query` (FIX-1). The module has `analyze_documents`, `run_multi_query_rag`, `generate_structured_answer` which overlap conceptually with Phase 1 synthesis needs.

**Risk:** If a Phase 1 implementer imports `multi_query_rag.py` functions thinking they're production-tested, they're wrong. The module is not covered by the 30Q benchmark.

**Recommendation:** Delete `multi_query_rag.py` and `example_multi_rag.py` before Phase 1 implementation begins (flagged in P0.4 docs as pending cleanup).

### 2. `_treba_fx1_dekompozicija` — FIX-1 Fires for Nearly Everything

**retrieve.py lines 555–576:**
```python
def _treba_fx1_dekompozicija(query: str) -> bool:
    ...
    # multi-concept: 4+ content tokens (lowered from 6 to catch Q7-type short queries)
    if len(_tokenizuj(query)) >= 4:
        return True
    return False
```

With the ≥4 token threshold, virtually every real legal question triggers sub-query decomposition (3× GPT-4o-mini calls + 3× additional Pinecone queries). For Phase 1, case-law questions would similarly trigger FIX-1 automatically — this is correct behavior but adds ~$0.01 per query in sub-query LLM cost.

### 3. Confidence Thresholds Were Calibrated on 17,688 Zakoni Vectors

From the comment at retrieve.py lines 300–306:
```python
# Calibrated 2026-05-04 against 30Q benchmark (23,699-vector index)
# Score distribution: P25=0.64, median=0.67, P75=0.71
# Re-calibrate when index expands beyond current ZOO/KZ/ZKP scope.
```

*Note: comment says 23,699 but index has 17,688.* Adding 5,000–30,000 case-law vectors will shift the score distribution. A sudska_praksa result might score 0.66 (HIGH threshold) for a legal question where the zakon result scored 0.72 — the pipeline would pick the praksa result if it ranks first after Cohere. **Re-calibrate thresholds after Phase 1 ingest.** Consider separate thresholds per `doc_type`.

### 4. Cohere Reranker Sees All Results Mixed

`_cohere_rerank` receives the combined candidate list from all parallel branches. After adding sudska_praksa results, Cohere will see zakoni chunks and praksa chunks interleaved. Cohere has no knowledge of `doc_type`, so it may rerank a relevant VKS decision above a directly cited law article.

**Risk:** The Phase 1 synthesis strategy (confidence gate applied independently per doc_type) conflicts with how Cohere currently operates on the merged list. The post-Cohere overrides (Q5, Q15, Q16) hardcode article numbers — they would not be affected by praksa results. But the general Cohere ordering could surface a praksa result as `_top`, setting `top_article` to a decision number and `top_law` to a court name, which the gate would treat as HIGH confidence.

**Required change:** Either (a) run two separate Cohere reranks (one per doc_type), or (b) use the post-processing `doc_type` field to extract the top zakon and top praksa results independently after a single merged Cohere pass.

### 5. ZOO Fallback Uses Hardcoded Article List

`_ZOO_FALLBACK_CLANOVI = ["Član 154", "Član 155", "Član 200", "Član 189"]` fires when no HIGH/MEDIUM result is found. This fallback will not need changes for Phase 1 (it's law-specific) but must not accidentally include praksa chunks.

### 6. No TODO/FIXME Comments Referencing Case Law

Searched `retrieve.py`, `main.py`, `multi_query_rag.py` for "praksa", "sudsk", "presud", "case.law", "TODO.*praksa" — **none found**. Phase 1 integration is greenfield from the code's perspective.

---

## Section 11 — API Band Exposure / Debug-Mode Readiness Audit

### `normalizuj_rezultat` — api.py lines 479–492 (full, quoted in Section 6)

**Where `confidence_band` is stripped:** Line 483 — `risultat.get("data", "")` is extracted; `confidence`, `top_score`, `top_article`, `top_law` keys are silently dropped.

### Upstream Availability

`ask_agent` (main.py line 1678) returns:
```python
{
    "status": "success",
    "data": "...",
    "confidence": "HIGH"/"MEDIUM"/"LOW",  ← available
    "top_score": 0.72,                    ← available
    "top_article": "Član 200",            ← available
    "top_law": "zakon o obligacionim odnosima"  ← available
}
```

These fields are present in `rezultat` when `normalizuj_rezultat` is called. They are NOT lost before the call — they are simply not transferred to `resp`.

### Response Flow After `normalizuj_rezultat`

**`/api/pitanje` handler (api.py lines 1031–1043):**
```python
_al.log_response(
    endpoint="/api/pitanje",
    confidence=rezultat.get("confidence"),   ← captured BEFORE stripping
    ...
)
return normalizuj_rezultat(rezultat, credits_remaining=...)
```

### Minimal Change for Debug-Mode Band Exposure

**Cleanest insertion point: modify `normalizuj_rezultat` signature.** Add `debug: bool = False` parameter:

```python
def normalizuj_rezultat(rezultat: dict, credits_remaining=None, debug: bool = False) -> dict:
    resp = {}
    if isinstance(rezultat, dict) and rezultat.get("status") == "success":
        resp["odgovor"] = rezultat.get("data", "")
    else:
        resp["odgovor"] = rezultat.get("message", "Greška...")
    if credits_remaining is not None:
        resp["credits_remaining"] = credits_remaining
    if debug:
        resp["confidence_band"] = rezultat.get("confidence")
        resp["top_score"]       = rezultat.get("top_score")
        resp["top_article"]     = rezultat.get("top_article")
        resp["top_law"]         = rezultat.get("top_law")
    return resp
```

Then in the `/api/pitanje` handler, add `debug: bool = Query(default=False)` to the signature and pass through. **Change footprint: ~10 lines across 2 locations** (`normalizuj_rezultat` + handler signature).

**Authentication:** The debug param should be gated — either require `ADMIN_DEBUG_KEY` header or restrict to `FOUNDER_EMAILS`. Raw `top_score` and `top_article` are not secrets, but exposing them publicly could let users game the confidence system or fingerprint articles. Recommend: `?debug=true` silently ignored unless `X-Admin-Key` header matches `ADMIN_DEBUG_KEY` env var. Same pattern already used by `/api/test-pitanje` (api.py line 852–854).

**Estimated change: ~12 lines total.**

---

## Section 12 — `.gitignore` Hygiene Audit

### Current `.gitignore` Content (post-P0.4 commit 65a6de2)

```
vector_store/
__pycache__/
*.pyc
.env
vector_store.zip
nvector_store/
.claude/
```

### Checklist

| Pattern | Status | Recommendation |
|---------|--------|----------------|
| `.claude/` | ✓ Added in P0.4 | Correct — covers future `.claude/settings.local.json` etc. |
| `.venv/`, `venv/` | ✗ MISSING | Add — `.venv/` is present as a directory |
| `__pycache__/` | ✓ Present | Correct |
| `.env` | ✓ Present | Correct |
| `.env.local`, `.env.production` | ✗ MISSING | Add both as precaution |
| `*.log`, `server.log` | ✗ MISSING | Add `*.log` |
| `30q_*.txt` | ✗ MISSING | Add `30q_*.txt` |
| `*.pyc`, `*.pyo` | ✓ `*.pyc` present | Add `*.pyo` |
| `.vscode/`, `.idea/` | ✗ MISSING | Add both |
| `*.lock` (generic) | ✗ MISSING | Add `*.lock` (or `scheduled_tasks.lock` specifically) |

### Files Currently Tracked That Should Be Ignored

Found via `git ls-files` filtering for `.lock`, `.log`, `30q_`, `server.`:

| Tracked File | Type | Action Needed |
|------|------|---------------|
| `.claude/scheduled_tasks.lock` | Claude Code scheduler state | `git rm --cached .claude/scheduled_tasks.lock` + `.claude/` already in .gitignore |
| `30q_after_subquery_fix.txt` | Benchmark result | `git rm --cached` + add `30q_*.txt` to .gitignore |
| `30q_corrected_baseline.txt` | Benchmark result | same |
| `ingest_laws_run.log` | Ingest run log | `git rm --cached` + add `*.log` |
| `web3_integracija/logs/error.log` | Module log | same |

**None of these affect production code.** But they will continue to appear in `git status` and may accumulate over time. Recommend a hygiene commit: `git rm --cached` the above five + expand `.gitignore`.

---

## Section 13 — B1/B2 Audit-Logging Verification

### B1 — Audit Logger Module

**`app/services/audit_log.py` — complete file (131 lines)**

Logger setup (lines 1–10 of module):
```python
logger = logging.getLogger("vindex.audit")
```

Schema (from the SQL comment at top of file):
```sql
CREATE TABLE response_audit (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    ts            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pipeline_id   VARCHAR(32) NOT NULL,      ← correlation ID
    endpoint      VARCHAR(60) NOT NULL,
    tip           VARCHAR(20),               ← query classification
    query_hash    VARCHAR(16) NOT NULL,      ← SHA256[:16] of query
    confidence    VARCHAR(10),
    top_score     FLOAT,
    top_article   TEXT,
    top_law       TEXT,
    response_len  INTEGER     NOT NULL DEFAULT 0,
    response_hash VARCHAR(32) NOT NULL,      ← SHA256[:32] of response text
    latency_ms    INTEGER     NOT NULL DEFAULT 0
);
```

**Structured format:** Key-value via Supabase insert dict. No free-text log entries for these fields.
**PII check:** `query_hash` is SHA256[:16] of the normalized query — raw query text is NOT stored. Email is NOT stored. `response_hash` is SHA256 of response text — not the text itself. ✓ PII-safe.

### B1 — Call Sites in `api.py`

| Line | Endpoint | Condition | Fields Logged |
|------|----------|-----------|---------------|
| 1031 | `/api/pitanje` | Always (after LLM response) | endpoint, query_hash, tip, confidence, top_score, top_article, top_law, response_text, latency_ms |
| 1106 | `/api/pitanje/stream` | LOW band path | same |
| 1204 | `/api/pitanje/stream` | MEDIUM band path | same |
| 1270 | `/api/pitanje/stream` | HIGH band path | same |
| 1304 | `/api/nacrt` | Always | same (tip=nacrt) |
| 1333 | `/api/analiza` | Always | same (tip=analiza) |

**Total: 6 call sites — 6/6 wired.**

**`/api/bot/ask` (line 999–1015): NOT wired for B1 audit.** The bot handler calls `normalizuj_rezultat` but does NOT call `_al.log_response`. This is a gap — bot usage is not audited.

### B1 Verdict

**5/6 production endpoints wired correctly.** `/api/bot/ask` is missing. For Phase 1, add 1 call site to `/api/bot/ask` and plan for 2 new call sites: one for the `/api/pitanje` sudska_praksa retrieval branch, one for the dedicated praksa endpoint (if added separately).

### B2 — Disclaimer Wiring

**`DISCLAIMER` constant — main.py lines 1620–1626:**
```python
DISCLAIMER = (
    "\n\n---\n\n"
    "⚠️ **Pravna napomena:** Vindex AI pruža informacije zasnovane na zakonskim "
    "tekstovima Republike Srbije i ne predstavlja pravni savet. Ovaj odgovor ne "
    "zamenjuje konsultaciju sa licenciranim advokatom. Pre donošenja bilo kakvih "
    "pravnih odluka, obratite se stručnjaku."
)
```

**All response paths in `ask_agent`:**

| Path | Function | DISCLAIMER present |
|------|----------|--------------------|
| LOW confidence | `_format_low_response(top_score)` line 1629 | ✓ `+ DISCLAIMER` |
| MEDIUM success | `_dodaj_disclaimer(odgovor)` line 1792 | ✓ |
| HIGH success | `_dodaj_disclaimer(odgovor)` line 1857 | ✓ |
| Legal error (MEDIUM path) | `_odgovor_pravna_greska(...)` line 1785 | ✓ (DISCLAIMER in `_odgovor_pravna_greska`) |
| Legal error (HIGH path) | `_odgovor_pravna_greska(...)` line 1850 | ✓ |
| Server busy (all paths) | `"...Pokušajte ponovo." + DISCLAIMER` lines 1702, 1776, 1814, 1845, 1873, 1896, 1922 | ✓ |

**One path that does NOT include DISCLAIMER:**

`ask_agent("")` — empty question validation (line 1686):
```python
return {"status": "error", "message": "Pitanje ne može biti prazno."}
```
This is correct — it's a client validation error, not a legal response. `test_disclaimer_b2.py` explicitly acknowledges this (line 54: `"INFO ask_agent('') → validation error (no disclaimer expected)"`).

**B2 Verdict: UNCONDITIONAL ✓** — All legal response paths include the disclaimer. The only DISCLAIMER-free return is the empty-input validation error, which is expected.

### Phase 1 New Log Points Needed

For sudska_praksa integration, analogous to the 6 existing points:

| New Point | Location | Fields to Add |
|-----------|----------|---------------|
| praksa retrieval confidence | `retrieve_documents` (after separate praksa branch) | `praksa_confidence`, `praksa_top_score`, `praksa_decision_number` |
| synthesis decision | `ask_agent` synthesis logic | `synthesis_type` ("zakon_only" / "praksa_only" / "combined") |
| `/api/bot/ask` B1 gap (existing) | api.py line ~1012 | same fields as `/api/pitanje` |

**Recommended new count: 3 additional log points** (2 new + 1 fix for existing gap).

---

## Summary Table — Phase 1 Impact Assessment

| Area | Phase 1 Impact | Severity | Estimated Lines |
|------|---------------|----------|----------------|
| Pinecone filter (`doc_type`) | Add field to upsert + filter param | Trivial | ~25 |
| Chunker (case law) | New `chunker_case_law.py` | Moderate | ~200 new |
| Retrieval parallel branch | Add to `_jedan_retrieval_krug` | Trivial | ~15 |
| Cohere rerank (mixed results) | Separate rerank OR post-process split | Moderate | ~30 |
| Confidence gate (two sources) | `retrieve_documents` returns 2 bands | Trivial | ~20 |
| `ask_agent` synthesis | New synthesis block for zakon+praksa | Moderate | ~60 |
| Response schema | Optional new fields (backward-compat) | Trivial | ~15 |
| `LAW_HINTS` / routing | Add parallel `AREA_HINTS` | Trivial | ~30 |
| 30Q → 30P runner extension | Add `PRAKSA_QUESTIONS` list | Trivial | ~100 new |
| Debug mode band exposure | `normalizuj_rezultat` + handler | Trivial | ~12 |
| `.gitignore` cleanup | `git rm --cached` + expand | Trivial | ~10 |
| B1 `/api/bot/ask` gap | Add `_al.log_response` call | Trivial | ~10 |
| Dead code (`multi_query_rag.py`) | Delete 2 files | Cleanup | −644 lines |
| Confidence threshold recalibration | After ingest, update 2 constants | Trivial | ~2 |

**No section requires a MAJOR refactor.** The codebase is well-structured for the proposed Phase 1 architecture. The most significant new work is the case-law chunker (~200 lines) and the synthesis logic in `ask_agent` (~60 lines). Everything else is additive and backward-compatible.

### Architectural Surprises That Force Plan Changes

1. **Cohere reranks the merged candidate list** — the plan must explicitly decide whether to run two independent Cohere passes or extract per-`doc_type` tops from a single merged pass. The current code has no mechanism for this.

2. **Confidence thresholds must be recalibrated after praksa ingest** — the current thresholds are calibrated on 17,688 zakoni vectors. Adding 5,000–30,000 case-law vectors will shift score distributions, potentially causing correct zakoni results to be displaced by HIGH-scoring praksa chunks.

3. **30Q `_self_eval` conflates `meta_article` with `ground_truth_art`** — the test design defect means 30P must use a new schema to be reliable. Do not copy the current 4-tuple format.

4. **`/api/bot/ask` is unaudited** — B1 logging gap for all bot traffic. Should be fixed before Phase 1 adds praksa traffic that also flows through this endpoint.

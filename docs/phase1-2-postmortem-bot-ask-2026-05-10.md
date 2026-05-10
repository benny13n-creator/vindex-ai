# /api/bot/ask Retrieval Postmortem

**Date:** 2026-05-10
**Branch:** phase1-sudska-praksa
**HEAD:** f37642e
**Inspection type:** READ-ONLY

---

## Step 1 — Handler location

**Route declaration** — `api.py:997-999`:
```python
@app.post("/api/bot/ask")
@limiter.limit("120/minute")
async def bot_ask(req: PitanjeReq, request: Request, x_api_key: str = Header(default="")):
```

**Handler body** — `api.py:1005-1028`:
```python
    bot_key = os.getenv("BOT_API_KEY", "").strip()
    if not bot_key or x_api_key != bot_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    qh = _q_hash(req.pitanje)
    logger.info("Bot pitanje [q=%s]", qh)
    try:
        t0 = _time.monotonic()
        rezultat = await pokreni(ask_agent, req.pitanje, None)    # <── DISPATCHES HERE
        latency_ms = int((_time.monotonic() - t0) * 1000)
        _al.log_response(
            endpoint="/api/bot/ask",
            query_hash=qh,
            tip=None,
            confidence=rezultat.get("confidence"),
            top_score=rezultat.get("top_score"),
            top_article=rezultat.get("top_article"),
            top_law=rezultat.get("top_law"),
            response_text=rezultat.get("data", ""),
            latency_ms=latency_ms,
        )
        return normalizuj_rezultat(rezultat)
    except Exception:
        logger.exception("Greška u /api/bot/ask [q=%s]", qh)
        return greska_odgovor(500, "Greška servera.")
```

`pokreni` — `api.py:474-476`:
```python
async def pokreni(fn, *args):
    """Pokreće sinhronu funkciju u thread poolu."""
    return await asyncio.to_thread(fn, *args)
```

The handler:
1. Authenticates via `X-Api-Key` header against `BOT_API_KEY` env var
2. Calls `pokreni(ask_agent, req.pitanje, None)` — wraps synchronous `ask_agent` in `asyncio.to_thread`
3. Returns `normalizuj_rezultat(rezultat)` — a flat `{"odgovor": str}` JSON

---

## Step 2 — Retrieval path

**Call chain:**

```
/api/bot/ask  →  pokreni(ask_agent, ...)  →  ask_agent()  →  retrieve_documents()
                                                                    ↓
                                               _jedan_retrieval_krug()  [parallel ThreadPoolExecutor]
                                                    ├── _direktan_fetch_clana()
                                                    ├── _pretraga_vec()  [law-filtered, k=30]
                                                    ├── _pretraga_vec()  [no filter, k=6]
                                                    └── _semanticka_pretraga()  [sub-queries, expansions]
```

**`ask_agent`** — `main.py:1697-1699`:
```python
        # KORAK 1: Retrieve with confidence metadata
        try:
            docs, retrieval_meta = retrieve_documents(pitanje_api, k=10)
```

**`retrieve_documents`** — `app/services/retrieve.py:947`:
```python
def retrieve_documents(query: str, k: int = 6) -> tuple[list[str], dict]:
```

**All three Pinecone `index.query()` calls in the call chain:**

`_semanticka_pretraga` — `retrieve.py:328`:
```python
        matches = index.query(vector=vektor, top_k=k, include_metadata=True, filter=filter_dict).matches
```

`_pretraga_vec` — `retrieve.py:341`:
```python
        return index.query(vector=vektor, top_k=k, include_metadata=True, filter=filter_dict).matches
```

`_direktan_fetch_clana` — `retrieve.py:354`:
```python
        return index.query(vector=dummy, top_k=5, include_metadata=True, filter=filter_dict).matches
```

| Pinecone query | File:Line | namespace | filter | wrapped in | top_k |
|----------------|-----------|-----------|--------|------------|-------|
| `_direktan_fetch_clana` | retrieve.py:354 | **NOT PASSED** (default only) | `{"article": {"$eq": label_clana}}` optionally + law | ThreadPoolExecutor | 5 |
| `_pretraga_vec` (law-filtered) | retrieve.py:341 | **NOT PASSED** (default only) | `{"law": {"$eq": filter_zakon}}` | ThreadPoolExecutor | max(k, 30) |
| `_pretraga_vec` (no filter) | retrieve.py:341 | **NOT PASSED** (default only) | None | ThreadPoolExecutor | 6 |
| `_semanticka_pretraga` (sub-queries, multi per call) | retrieve.py:328 | **NOT PASSED** (default only) | `{"law": {"$eq": filter_zakon}}` or None | ThreadPoolExecutor | 3–10 |
| HyDE `_pretraga_vec` (law-filtered) | retrieve.py:1002 | **NOT PASSED** (default only) | `{"law": {"$eq": zakon}}` | sync call | 8 |
| HyDE `_pretraga_vec` (no filter) | retrieve.py:1002 | **NOT PASSED** (default only) | None | sync call | 5 |
| CRAG `_semanticka_pretraga` (expansion) | retrieve.py:1248-1249 | **NOT PASSED** (default only) | law or None | sync loop | 5 or 3 |

**Total queries per `/api/bot/ask` call:** 6–15+ parallel Pinecone queries (varies by query content — ZDI/KZ/ZPDG triggers add expansion batches)

**Namespaces hit:** **default namespace ONLY** — the 17,688 zakon vectors.

The `sudska_praksa` namespace (1,479 VKS case law chunks) is **never queried** in any production code path.

---

## Step 3 — Multi-namespace mechanism

**Mechanism in play: NONE — no multi-namespace retrieval exists**

Every `index.query()` call in `retrieve.py` omits the `namespace=` parameter. In Pinecone SDK v3, omitting `namespace` queries the **default namespace only**. The `sudska_praksa` namespace is invisible to the production pipeline.

**Proof** — all three query functions share the same pattern, e.g. `retrieve.py:323-334`:
```python
def _semanticka_pretraga(query: str, k: int = 10, filter_zakon: Optional[str] = None) -> list:
    index = _get_index()
    vektor = _ugradi_query(query)
    filter_dict = {"law": {"$eq": filter_zakon}} if filter_zakon else None
    try:
        matches = index.query(vector=vektor, top_k=k, include_metadata=True, filter=filter_dict).matches
```

No `namespace=` argument. Same pattern at `retrieve.py:341` and `retrieve.py:354`.

The string "sudska_praksa" does not appear in `retrieve.py`, `main.py`, or `api.py` in any query-related context.

---

## Step 4 — Synthesis

**Synthesis function:** `ask_agent` at `main.py:1678`. After retrieval it:

1. Classifies query intent via `klasifikuj_pitanje()` → one of `COMPLIANCE / PORESKI / PARNICA / DEFINICIJA`
2. Selects a `system_prompt` from a prompt map — `main.py:1739-1744`:
```python
        _prompt_map = {
            "COMPLIANCE": (SYSTEM_PROMPT_COMPLIANCE, SEKCIJE_COMPLIANCE, "gpt-4o", 2000),
            "PORESKI":    (SYSTEM_PROMPT_PORESKI,    SEKCIJE_PORESKI,    "gpt-4o", 2000),
            "PARNICA":    (SYSTEM_PROMPT_PARNICA,    SEKCIJE_PARNICA,    "gpt-4o", 2500),
            "DEFINICIJA": (SYSTEM_PROMPT_DEFINICIJA, SEKCIJE_DEFINICIJA, "gpt-4o", 1500),
        }
```
3. Builds a single context block — `main.py:1747`:
```python
        kontekst = "\n\n---\n\n".join(filtrirani)
```
4. Passes everything to GPT-4o as — `main.py:1805-1808`:
```python
        user_content = (
            f"{history_blok}"
            f"PITANJE: {pitanje_api}\n\n"
            f"KONTEKST IZ BAZE ZAKONA:\n{kontekst}"
        )
```

**Distinguishes zakon vs praksa by:** NOTHING. There is no distinction. All docs feed into a single unlabeled context block.

**The "Sudska praksa: ..." prefix in production responses:**

This is NOT retrieved from the `sudska_praksa` namespace. It is generated by GPT-4o following a hardcoded **prompt instruction** in `SYSTEM_PROMPT_PARNICA` at `main.py:1360`:
```
[Sudska praksa: raspon naknade — SAMO raspon, NIKADA fiksna cifra]
```
and at `main.py:1374`:
```
• Nematerijalna šteta: Sudska praksa: [X.XXX] – [Y.YYY] RSD (zavisno od težine i trajanja posledica)
```

The production response "Sudska praksa: raspon kazne za osnovnu krađu je novčana kazna ili zatvor do tri godine" is GPT-4o's own training-data knowledge formatted according to this template — not VKS decision data from Pinecone.

**Different treatment for zakon vs praksa:** NO — because no praksa is retrieved. The system prompt instructs the LLM to supply case law context from its own knowledge.

---

## Step 5 — Confidence gate

**Gate location:** `retrieve.py:308-318` (threshold constants) and `retrieve.py:312-318` (function):
```python
CONFIDENCE_HIGH_THRESHOLD   = 0.65
CONFIDENCE_MEDIUM_THRESHOLD = 0.52

def get_confidence_level(score: float) -> str:
    """Map Pinecone cosine score to HIGH / MEDIUM / LOW."""
    if score >= CONFIDENCE_HIGH_THRESHOLD:
        return "HIGH"
    elif score >= CONFIDENCE_MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"
```

**Operates on:** the top-ranked match from the zakon (default namespace) retrieval only. The score used is the cosine similarity of the best zakon chunk — `retrieve.py:1085-1087`:
```python
        _top_score   = _top.score
        _top_article = _top_meta_raw.get("article", "—")
        _top_law     = _top_meta_raw.get("law", "—")
```

**Comment in code at retrieve.py:300-305:**
```
# Calibrated 2026-05-04 against 30Q benchmark (23,699-vector index)
# Score distribution: P25=0.64, median=0.67, P75=0.71
# HIGH=0.65 → 67% coverage (20/30 queries routed to structured answer)
# MEDIUM=0.52 → catches Q14, Q30 (true LOW — wrong law returned) correctly
# Known limitation: Q06 (uslovna osuda) routes to ZKP instead of KZ
# Re-calibrate when index expands beyond current ZOO/KZ/ZKP scope.
```

Thresholds are calibrated against the zakon-only 17,688-vector corpus. Praksa chunks (cosine range observed in sanity queries: 0.43–0.63) are not in this calibration.

**Reconciliation:** UNDETERMINED — no dual-source gate logic exists yet.

---

## Step 6 — Response schema

`normalizuj_rezultat` — `api.py:479-492`:
```python
def normalizuj_rezultat(rezultat: dict, credits_remaining: Optional[int] = None) -> dict:
    resp: dict = {}
    if not isinstance(rezultat, dict):
        resp["odgovor"] = str(rezultat)
    elif rezultat.get("status") == "success":
        resp["odgovor"] = rezultat.get("data", "")
    else:
        resp["odgovor"] = rezultat.get(
            "message",
            "Došlo je do greške prilikom obrade zahteva. Pokušajte ponovo.",
        )
    if credits_remaining is not None:
        resp["credits_remaining"] = credits_remaining
    return resp
```

Response JSON returned to the client:
```json
{
  "odgovor": "<full response text as single string>",
  "credits_remaining": <int, only for /api/pitanje>
}
```

- **`source_type` field present:** NO
- **Per-citation structured fields:** NO — all citations are embedded in the `odgovor` string via markdown formatting
- **`case_law` array:** NO
- **Frontend can distinguish citation types:** NO — only by regex-parsing the `odgovor` text for markers like `ZAKON:`, `ČLAN:`, section headers

The `ask_agent` internal dict does have `top_article` and `top_law` fields but these are used only for audit logging — they are not surfaced in the client response.

---

## Step 7 — Comparison to /api/pitanje

**`/api/pitanje` handler** — `api.py:1031-1062`:
```python
@app.post("/api/pitanje")
@limiter.limit("10/minute")
async def pitanje(req: PitanjeReq, request: Request, user: dict = Depends(require_credits)):
    ...
    rezultat = await pokreni(ask_agent, req.pitanje, history)
    ...
    return normalizuj_rezultat(rezultat, credits_remaining=max(preostalo, 0))
```

- **Same retrieval logic as `/api/bot/ask`:** YES — identical `pokreni(ask_agent, ...)` call pattern. Both go through `ask_agent → retrieve_documents`.
- **Picks up `sudska_praksa` namespace:** NO — same `retrieve.py` pipeline, no namespace parameter.
- **Difference from `/api/bot/ask`:** Only auth (Supabase JWT vs `X-Api-Key`) and credit deduction. The retrieval and synthesis are identical.

`/api/pitanje/stream` (`api.py:1065`) also calls `retrieve_documents` directly — `api.py:1101`:
```python
            docs, retrieval_meta = await asyncio.to_thread(retrieve_documents, pitanje_api, 10)
```

Also default-namespace-only.

**All three production endpoints (`/api/bot/ask`, `/api/pitanje`, `/api/pitanje/stream`) hit only the default namespace.**

---

## Step 8 — Phase 1.3 gap analysis

| Component | Already done? | Gap | Scope |
|-----------|---------------|-----|-------|
| Parallel retrieval (query `sudska_praksa`) | **NO** | `_semanticka_pretraga`, `_pretraga_vec`, `_direktan_fetch_clana` all omit `namespace=`. Need a new query path that passes `namespace="sudska_praksa"`, run concurrently with default-namespace queries via `ThreadPoolExecutor`. | **MODERATE** (~40-60 lines in `retrieve.py`) |
| Context labeling (zakon vs praksa) | **NO** | All docs are concatenated unlabeled into `"KONTEKST IZ BAZE ZAKONA:"`. Praksa docs need separate formatting function (uses `court`, `decision_number`, `matter` metadata instead of `law`/`article`/`parent_text`). Need `_formatiraj_praksa_match()` and split context sections: `"KONTEKST IZ BAZE ZAKONA:"` + `"KONTEKST IZ SUDSKE PRAKSE:"`. | **MODERATE** (~30-50 lines in `retrieve.py` + `main.py`) |
| System prompt update | **YES (partial)** | System prompts already instruct GPT to output a `Sudska praksa:` line — but it's filled from LLM training knowledge, not actual retrieved VKS data. Once praksa context is passed, prompts need to instruct GPT to cite `decision_number + court` instead of generating ranges from memory. Small wording changes per prompt. | **TRIVIAL** (~10-20 lines across 4 prompts in `main.py`) |
| Confidence gate for dual sources | **NO** | Thresholds (HIGH=0.65, MEDIUM=0.52) are calibrated on zakon-only corpus. Praksa cosines observed at 0.43–0.63 (sanity queries). If gate uses only the zakon top score, HIGH-confidence zakon queries will suppress praksa context even when praksa match is strong. Gate recalibration needed or separate per-source confidence. | **MODERATE** (~20-30 lines in `retrieve.py`, requires re-benchmarking) |
| Response schema (structured citations) | **NO** | `normalizuj_rezultat` returns a flat `{"odgovor": str}`. No `source_type`, no `case_law` array. Frontend cannot distinguish citation types without text parsing. Whether this needs to change depends on whether the frontend needs structured data. If only text output is needed (Telegram bot), scope is TRIVIAL. If the web frontend needs structured citations, scope is MAJOR. | **TRIVIAL** (Telegram bot / existing frontend) or **MAJOR** (structured citations) |
| Other endpoints coverage | **PARTIAL** | If parallel retrieval is added to `retrieve_documents()`, all three endpoints (`/api/bot/ask`, `/api/pitanje`, `/api/pitanje/stream`) get it automatically — they all call `retrieve_documents`. No per-endpoint changes needed for retrieval itself. `/api/nacrt` and `/api/analiza` (if they exist) need separate investigation. | **TRIVIAL** (if `retrieve_documents` is the integration point) |

---

## Verdict

**Phase 1.3 scope based on findings:**

The `sudska_praksa` namespace is completely absent from the production retrieval pipeline. The 1,479 VKS vectors ingested in Phase 1.2 are not queried by any endpoint. The "Sudska praksa: ..." line in production responses is GPT-4o following a prompt template instruction (`main.py:1360`) — the model supplies case law context from its own training knowledge, not from Pinecone.

Phase 1.3 must build from scratch: (1) a namespace-scoped query function in `retrieve.py` that queries `sudska_praksa` in parallel with the existing default-namespace pipeline; (2) a praksa-specific formatter (`_formatiraj_praksa_match`) that uses `court`/`decision_number`/`matter` metadata; (3) separate context blocks in the LLM user message so GPT knows which chunks are zakon text and which are VKS decisions; (4) system prompt refinements to cite actual `decision_number + court` instead of generating ranges from memory. The confidence gate also needs recalibration for the expanded corpus. No changes are needed to the API handler layer or response schema (assuming flat `odgovor` string output is sufficient for the current frontend).

---

## Notes for Phase 1.3 prompt design

### Integration point
The cleanest integration point is `retrieve_documents` in `retrieve.py:947`. Add a parallel branch there that queries `namespace="sudska_praksa"`, keeping results separate from zakon results through formatting.

### New formatter needed
`_formatiraj_match` (`retrieve.py:805-828`) reads `law`, `article`, `parent_text` — fields that don't exist on praksa chunks. Praksa chunks have `court`, `decision_number`, `matter`, `section`, `cited_articles_raw`. A `_formatiraj_praksa_match` must output e.g.:

```
SUDSKA PRAKSA: Vrhovni sud
ODLUKA: Kzz 754/2025
OBLAST: Krivična
SEKCIJA: OBRAZLOŽENJE
TEKST: ...
```

### Context section labels for LLM
In `ask_agent` (`main.py:1747-1808`), the context is built as:
```python
kontekst = "\n\n---\n\n".join(filtrirani)
user_content = f"PITANJE: {pitanje_api}\n\nKONTEKST IZ BAZE ZAKONA:\n{kontekst}"
```
For Phase 1.3, split into two labeled blocks:
```python
user_content = (
    f"PITANJE: {pitanje_api}\n\n"
    f"KONTEKST IZ BAZE ZAKONA:\n{zakon_kontekst}\n\n"
    f"KONTEKST IZ SUDSKE PRAKSE:\n{praksa_kontekst}"
)
```

### System prompt wording change
In `SYSTEM_PROMPT_PARNICA` (`main.py:1360`), replace:
```
[Sudska praksa: raspon naknade — SAMO raspon, NIKADA fiksna cifra]
```
with an instruction to cite the actual retrieved decision:
```
[Sudska praksa: ako postoji KONTEKST IZ SUDSKE PRAKSE — navedi odluku po formatu "Vrhovni sud, Kzz/Rev/Uzp br. X/GGGG: [kratki citat]". Ako nema — izostavi sekciju.]
```

### Parallel execution pattern (already present — reuse it)
`_jedan_retrieval_krug` already uses `ThreadPoolExecutor(max_workers=12)` for parallel Pinecone queries. The new praksa query can be added as another `executor.submit(...)` job in that pool (`retrieve.py:871-924`), keeping the return value separate from zakon matches.

### Confidence gate for praksa
Praksa sanity scores: 0.43–0.63 (from Phase 1.2 final verification). Current LOW threshold = 0.52. A standalone praksa query at score 0.55 (MEDIUM by zakon standards) is likely a good praksa match. Consider separate gate thresholds for praksa: `PRAKSA_HIGH_THRESHOLD = 0.55`, `PRAKSA_MEDIUM_THRESHOLD = 0.42`.

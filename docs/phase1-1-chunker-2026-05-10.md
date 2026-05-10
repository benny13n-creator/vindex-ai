# Phase 1.1 — chunker_case_law.py Report

**Date:** 2026-05-10
**Branch:** phase1-sudska-praksa
**Commits:** `de483d3` (chunker code + tests), `cd0ab92` (chunked dataset + manifest)
**Pushed:** YES

---

## Architecture confirmation

- Storage strategy for Phase 1.2: Pinecone **NAMESPACE** `sudska_praksa` (not metadata filter)
- Reason: namespace-scoped queries scan only that namespace — faster and cheaper than full-index metadata filter
- Chunk metadata still includes `doc_type: "sudska_praksa"` as documentation/safety field
- Existing 17,688 zakon vectors stay in default namespace; no re-ingest needed
- Chunker output is namespace-agnostic — `chunk_decision()` produces chunks; Phase 1.2 assigns namespace

---

## Phase A — Setup

### Existing chunker location

- **File:** `semantic_chunker.py` (repo root — no file named `chunker_v3.py` exists)
- **Public function:** `podeli_zakon_na_chunkove(tekst, zakon_naziv) -> list[dict]`

### Existing chunk schema (semantic_chunker.py)

```python
{
    "id": str,          # MD5 hash
    "text": str,        # embedding text, ≤300 chars
    "metadata": {
        "zakon": str,           # law short code (KZ, ZR, ...)
        "clan": int,            # article number
        "stav": int,            # paragraph number
        "parent_id": str,       # "ZOO_200" format
        "parent_text": str,     # full article ≤3000 chars
        "tekst_preview": str,   # first 100 chars
        "law": str,             # full law name
        "article": str,         # "Član N"
        "text": str,            # paragraph text
    }
}
```

New `chunker_case_law.py` schema matches structurally but uses larger chunks (600 tokens vs ~200 chars) and adds case-law-specific fields (`decision_number`, `matter`, `section`, `cited_articles_raw`).

### ZAKON_SHORTCODES mapping (found in semantic_chunker.py)

```python
ZAKON_SHORTCODES = {
    "krivicni zakonik": "KZ",
    "zakonik o krivicnom postupku": "ZKP",
    "zakon o obligacionim odnosima": "ZOO",
    "zakon o radu": "ZR",
    "zakon o parnicnom postupku": "ZPP",
    # ... 18 total entries
}
```

`cited_articles_normalized` is left empty because article numbers extracted from decisions cannot be reliably attributed to a specific law without full context extraction (deferred to Phase 1.3).

### Dependencies

- `tiktoken` — installed (cl100k_base encoding, 2 tokens for "test string" ✓)
- `json`, `re`, `pathlib`, `datetime` — stdlib
- Python 3.13.12 ✓

---

## Phase B — Chunker module

- **File:** `chunker_case_law.py` (repo root, alongside `semantic_chunker.py`)

### Public API

```python
def chunk_decision(decision_json: dict) -> dict
def chunk_corpus(raw_dir: Path, output_dir: Path) -> dict
def split_into_sections(text: str) -> list[tuple[str, str]]
def chunk_section(section_name, section_text, target_tokens=600, overlap_tokens=50) -> list[str]
def extract_cited_articles(text: str) -> list[str]
def count_tokens(text: str) -> int
```

### Section markers discovered and used

The task spec assumed plain `IZREKA:` / `OBRAZLOŽENJE:` markers. The actual VKS scraped text uses **spaced-letter headings**:

| Pattern in text | Section name |
|-----------------|--------------|
| `R E Š E NJ E` (on its own line) | `IZREKA` |
| `P R E S U D U` (on its own line) | `IZREKA` |
| `O b r a z l o ž e nj e` (on its own line) | `OBRAZLOŽENJE` |
| `REŠENJE`, `PRESUDA` (plain, fallback) | `IZREKA` |
| `IZREKA`, `OBRAZLOŽENJE` (plain, fallback) | `IZREKA` / `OBRAZLOŽENJE` |
| `Iz obrazloženja:` (1 decision in corpus) | `IZ_OBRAZLOZENJA` |

Text before the first marker → `HEADER`. No markers → single `BODY` section.

### Chunk size strategy

- Target: 600 tokens, 50-token overlap
- Split text: first on `\n` (paragraph lines), then on `. ` for paragraphs >400 tokens
- Overlap: decode last 50 token IDs from prior chunk, prepend to next chunk
- Hard-split failsafe: any chunk >800 tokens is split on token boundary (never triggered in practice)

### cited_articles regex patterns

```python
re.compile(r"\bčlan\w*\s+(\d+[a-zšćčžđ]?)", re.IGNORECASE)  # covers: član, člana, članu, članovima, etc.
re.compile(r"\bčl\.\s*(\d+[a-zšćčžđ]?)", re.IGNORECASE)     # covers: čl. 203, čl.203
```

### Tests

6/6 PASS — `tests/test_chunker_case_law.py`:

| Test | Result |
|------|--------|
| `test_section_splitting_with_markers` | PASS |
| `test_section_splitting_presuda_marker` | PASS |
| `test_section_splitting_no_markers` | PASS |
| `test_chunk_size_bounds` | PASS |
| `test_cited_articles_extraction` | PASS (fixed after initial failure — `članu` dative form was missed by `\bčlanova?`; fixed to `\bčlan\w*`) |
| `test_empty_decision_number_fallback` | PASS |

---

## Phase C — Application

| Matter | Decisions | Total chunks | Avg/decision | Min | Max |
|--------|-----------|--------------|--------------|-----|-----|
| Krivična | 50 | 362 | 7.24 | 4 | 19 |
| Građanska | 50 | 409 | 8.18 | 3 | 15 |
| Upravna | 50 | 388 | 7.76 | 4 | 21 |
| Zaštita prava | 50 | 320 | 6.40 | 4 | 9 |
| **TOTAL** | **200** | **1479** | **7.39** | **3** | **21** |

**Errors during processing:** 0

---

## Phase D — Validation

### D.1 Schema validation

**PASS — 1479/1479 chunks pass all checks:**
- All 13 top-level fields present on every decision file
- `chunks` array non-empty for all files
- All 7 chunk fields and all 13 metadata fields present
- `chunk_index` sequential 0..N-1 for all
- `chunk_total` matches array length for all
- All `token_count` in range [1, 800]
- All `section` values in `{HEADER, IZREKA, OBRAZLOŽENJE, IZ_OBRAZLOZENJA, BODY}`
- All `doc_type` = `"sudska_praksa"`

### D.2 Distribution

- **Total chunks:** 1479 (within 400–1500 range ✓)
- **Token distribution:** p10=112, p50=446, p90=586

### D.3 Section coverage

| Coverage | Count |
|----------|-------|
| Had IZREKA | 200/200 |
| Had OBRAZLOŽENJE | 200/200 |
| Had both | 200/200 |
| Fallback BODY only | 0/200 |

Section chunk breakdown: HEADER=200, IZREKA=202, OBRAZLOŽENJE=1077, IZ_OBRAZLOZENJA=0, BODY=0.

Note: 202 IZREKA chunks (not 200) because 2 decisions have an IZREKA section long enough to split into 2 chunks.

### D.4 Sample audit (10 random, seed=42) — 10/10 PASS

| # | Matter | Decision | Section | Tokens | cited_articles_raw (first 3) | PASS |
|---|--------|----------|---------|--------|------------------------------|------|
| 1 | Zaštita prava | Rž1 u 366/2025 | OBRAZLOŽENJE | 189 | ['4', '16', '18'] | ✅ |
| 2 | Krivična | Kzz 196/2026 | OBRAZLOŽENJE | 283 | ['60', '63', '71'] | ✅ |
| 3 | Krivična | Ks 1/2026 | OBRAZLOŽENJE | 590 | ['35', '36', '195'] | ✅ |
| 4 | Građanska | Rev 10755/2025 | IZREKA | 55 | ['28', '403', '410'] | ✅ |
| 5 | Građanska | Rev2 3202/2024 | OBRAZLOŽENJE | 554 | ['75', '104', '403'] | ✅ |
| 6 | Građanska | Rev2 3004/2025 | HEADER | 317 | ['154', '164', '170'] | ✅ |
| 7 | Krivična | Kzz 252/2026 | OBRAZLOŽENJE | 291 | ['42', '74', '86'] | ✅ |
| 8 | Krivična | Kzz 192/2026 | IZREKA | 116 | ['71', '74', '348'] | ✅ |
| 9 | Zaštita prava | Rž1 u 394/2025 | IZREKA | 52 | ['4', '16', '18'] | ✅ |
| 10 | Upravna | Uzp 428/2025 | OBRAZLOŽENJE | 417 | ['3', '8', '49'] | ✅ |

Sample chunk texts are coherent, section assignments match content, cited article numbers are plausible for the matter type (e.g. ZKP articles 60–90 in Krivična decisions, ZPP articles 400+ in Građanska).

---

## Phase E — Commits + push

- **Commit 1 (code):** `de483d3` — `chunker_case_law.py` + `tests/test_chunker_case_law.py`
- **Commit 2 (data):** `cd0ab92` — 200 chunked JSON files + `chunked_manifest.json`
- **Push:** SUCCESS — `origin/phase1-sudska-praksa`

---

## Final Verdict

| Check | Result |
|-------|--------|
| Branch correct (`phase1-sudska-praksa`) | ✓ |
| Tests pass (6/6) | ✓ |
| Schema valid for all 1479 chunks | ✓ |
| 0 processing errors | ✓ |
| Total chunks 1479 (within 400–1500) | ✓ |
| Sample audit 10/10 PASS | ✓ |
| Section detection 200/200 (IZREKA + OBRAZLOŽENJE) | ✓ |
| Main NOT touched | ✓ |
| Production code NOT touched | ✓ |
| **Phase 1.1 COMPLETE** | **YES** |
| **Ready for Phase 1.2 (Pinecone ingest into namespace `sudska_praksa`)** | **YES** |

---

## Notes for Phase 1.2 (Pinecone ingest)

- **Embedding model:** `text-embedding-3-large` (3072-dim cosine — same as existing zakon vectors)
- **Target Pinecone index:** `vindex-ai` (existing index — do NOT create a new index)
- **Target namespace:** `sudska_praksa` (new namespace within existing index; default namespace untouched)
- **Estimated upsert volume:** 1479 vectors
- **Estimated embedding cost:** 1479 chunks × ~450 tokens avg = ~665K tokens → ~$0.013 at $0.02/1M tokens for `text-embedding-3-large`
- **Chunks warranting review before ingest:** None. All pass schema validation. The 3 partial decisions (empty `decision_number`) are handled via `decision_id_fallback` in metadata.
- **Cross-reference opportunity:** `cited_articles_raw` contains article numbers extracted from each decision. Phase 1.3 could use these as explicit zakon-↔-praksa links — e.g., when a zakon chunk for KZ 203 is retrieved, also surface any praksa chunk with `cited_articles_raw` containing `"203"` and `matter == "Krivična"`.
- **Section weighting (optional for Phase 1.3):** IZREKA chunks are the operative ruling — may warrant a retrieval boost. OBRAZLOŽENJE chunks contain legal reasoning. HEADER chunks (court info, parties) are lower relevance for Q&A. Could use section metadata to adjust ranking.

---

## Bug found and fixed during Phase B

**Regex for article extraction:** Initial pattern `\bčlanova?` did not cover the dative form `članu` (as in "prema članu 203"). The Serbian word "član" has many inflected forms. Fixed by replacing `\bčlanova?` with `\bčlan\w*` which matches all inflected forms. The fix was validated by the `test_cited_articles_extraction` test case.

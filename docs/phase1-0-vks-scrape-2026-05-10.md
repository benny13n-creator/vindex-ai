# Phase 1.0 — VKS Decision Scraper Report

**Date:** 2026-05-10
**Branch:** `phase1-sudska-praksa`
**Commit:** `113332e`
**Source:** https://www.vrh.sud.rs (official VKS only)

---

## Phase A — Setup

### A.1 Environment

- Branch created from: `main` @ `2c6b068` (post-hygiene, working tree clean)
- Working directory: `data/sudska_praksa/`
- Scraper: `data/sudska_praksa/scraper_phase10.py` (version 1.0)
- Dependencies: `httpx`, `beautifulsoup4`, `lxml` (all already in environment)

### A.2 robots.txt Compliance

```
User-agent: *
Crawl-delay: 10
```

Observed: `CRAWL_DELAY = 10.5` (10.5s between all HTTP requests — both search page fetches and individual decision fetches). Timestamps in scrape log confirm >10s gap between consecutive GET requests to `vrh.sud.rs`.

### A.3 Discovery — VKS Search API

The VKS Drupal 7 site at `vrh.sud.rs` exposes a Solr-backed search. Key finding:

- Search URL: `https://www.vrh.sud.rs/sr-lat/solr-search-page/results`
- Method: **POST** with body `{op: Pretraga, level: 1}` — filter params go in the **GET query string only**
- Required params: `court_type=sc&matter=<id>&sorting=by_date_down&results=50&page=<n>`
- If filter params are sent in POST body instead of URL, the server ignores them and returns all 46,377 decisions unfiltered

### A.4 Matter Codes

VKS search form has exactly 4 matter types (no Privredna/commercial category — those decisions appear under Građanska with `Prev` registrant):

| Slug | Label | matter_id | Registrant examples |
|------|-------|-----------|---------------------|
| krivicna | Krivična | 33 | Kzz, Kd, Ks, Kzz PR, Kzz P |
| gradjanska | Građanska | 19 | Rev, Rev1, Rev2, Prev |
| upravna | Upravna | 9 | Us, Uzp, Przz |
| zastitaprava | Zaštita prava | 8 | Rž1, Rž, Kž1 |

### A.5 Decision Parsing

Decision body: `div.field-name-body` (Drupal field).

Decision number regex (final, after fix for multi-word registrants):
```python
re.search(r"^(.+?)\s+(\d+/\d{4})", h1_text)
```

The initial pattern `([A-Za-zžćčšđŽĆČŠĐ0-9]+(?:\s+[IVX]+)?)\s+(\d+/\d{4})` failed on `Rž1 u 31/2026` (registrant `Rž1 u` contains a space). The greedy `^(.+?)` pattern handles all registrant forms without assumptions.

---

## Phase B — Stratification Strategy

**Target:** 50 decisions × 4 matter types = 200 total

**Justification for matter selection:**

| Matter | Rationale |
|--------|-----------|
| Krivična | Core Vindex AI use case (criminal law Q&A) |
| Građanska | Largest VKS volume; includes Prev (commercial) decisions |
| Upravna | Administrative law — different legal register from criminal |
| Zaštita prava | Procedural corpus; structurally distinct (short, žalba-format decisions) |

**Note on Privredna:** The task spec assumed a separate Privredna matter category. VKS has no such category. Commercial decisions are classified under Građanska — the first Građanska result fetched was `Prev 102/2025` (Privredni revizioni), confirming commercial decisions are accessible via matter=19.

---

## Phase C — Scrape Results

### C.1 Per-Matter Summary

| Matter | matter_id | Collected | Partial | Failed | Wall time |
|--------|-----------|-----------|---------|--------|-----------|
| Krivična | 33 | 50 | 0 | 0 | 526s |
| Građanska | 19 | 50 | 0 | 0 | 536s |
| Upravna | 9 | 50 | 0 | 0 | 535s |
| Zaštita prava | 8 | 50 | 3 | 0 | 789s |
| **TOTAL** | | **200** | **3** | **0** | **~2386s (~40 min)** |

### C.2 Partial Decisions (3)

All 3 partials are in zastitaprava. The h1 heading was absent or non-standard on these pages — decision body text was still collected, but decision_number could not be extracted.

| decision_id | date | Warning |
|-------------|------|---------|
| id_b4d6052a4905 | 2026-01-29 | `decision_number extracted from URL (h1 parse failed)`, `MISSING: decision_number` |
| id_a7c570ecc568 | 2026-01-29 | `decision_number extracted from URL (h1 parse failed)`, `MISSING: decision_number` |
| id_bd7b55f076d5 | 2025-12-11 | `decision_number extracted from URL (h1 parse failed)`, `MISSING: decision_number` |

All 3 have non-empty `raw_text` and saved `raw_html_path`. They are counted as "collected" (content present) but flagged partial (decision_number missing). The `chunker_case_law.py` in Phase 1.1 must handle empty `decision_number` gracefully.

### C.3 Date Ranges by Matter

| Matter | Oldest | Newest |
|--------|--------|--------|
| Krivična | 2026-02-11 | 2026-04-15 |
| Građanska | 2026-03-11 | 2026-06-19 |
| Upravna | 2024-06-28 | 2025-12-29 |
| Zaštita prava | 2025-12-11 | 2026-03-05 |

Upravna dates are older because the VKS Upravna queue has fewer recent decisions — the scraper collected the 50 most recent by date, which extend back to mid-2024.

### C.4 Zaštita Prava Wall Time Anomaly

Zaštita prava took 789s vs ~530s for other matters. Cause: the search result list for matter=8 includes many decisions with very short text (procedural žalba-na-nedonošenje-odluke format). The scraper still had to observe the 10.5s crawl-delay for each fetch, and the matter has some pagination overhead since 50 results spanned 2 pages.

---

## Phase D — Dataset Files

### D.1 Directory Layout

```
data/sudska_praksa/
├── scraper_phase10.py       # scraper (committed)
├── manifest.json            # machine-readable index (committed)
├── scrape_log.txt           # runtime log (committed)
└── raw/
    ├── _dryrun/             # 5 dryrun HTML+JSON pairs from Phase A testing
    ├── krivicna/            # 50 HTML + 50 JSON
    ├── gradjanska/          # 50 HTML + 50 JSON
    ├── upravna/             # 50 HTML + 50 JSON
    └── zastitaprava/        # 50 HTML + 50 JSON (3 partial)
```

### D.2 JSON Schema per Decision

```json
{
  "decision_id": "Kzz_754_2025",
  "source_url": "https://www.vrh.sud.rs/sr-lat/...",
  "court": "Vrhovni sud",
  "decision_number": "Kzz 754/2025",
  "decision_date": "2026-04-15",
  "matter": "Krivična",
  "registrant": "Kzz",
  "raw_text_length": 7538,
  "raw_text": "...",
  "raw_html_path": "raw/krivicna/Kzz_754_2025.html",
  "scraped_at": "2026-05-10T11:07:23.272Z",
  "scraper_version": "1.0",
  "parse_warnings": []
}
```

### D.3 Commit

- **Commit SHA:** `113332e`
- **Message:** `feat(phase1.0): VKS decision dataset — 4 matter types, ~50 each (200 total)`
- **Files:** 414 files added, 83,622 insertions
- **Branch:** `phase1-sudska-praksa`

### D.4 Push

- **Push:** `git push -u origin phase1-sudska-praksa` — SUCCESS
- **Remote:** `https://github.com/benny13n-creator/vindex-ai.git`
- PR creation page: `https://github.com/benny13n-creator/vindex-ai/pull/new/phase1-sudska-praksa`

---

## Phase E — Quality Audit

Sampled 10 decisions at random (seed=42) across all 4 matter types. All 10 passed all checks.

| # | Matter | Decision number | raw_text_length | PASS |
|---|--------|-----------------|-----------------|------|
| 1 | Zaštita prava | Rž1 u 405/2025 | 3203 | ✅ |
| 2 | Krivična | Kzz 177/2026 | 7538 | ✅ |
| 3 | Krivična | Kzz 238/2026 | 11730 | ✅ |
| 4 | Zaštita prava | Rž 1 u 397/2025 | 7055 | ✅ |
| 5 | Građanska | Rev2 3004/2025 | 8117 | ✅ |
| 6 | Građanska | Rev 13546/2025 | 6434 | ✅ |
| 7 | Građanska | Rev 2549/2026 | 7176 | ✅ |
| 8 | Krivična | Kzz 167/2026 | 4802 | ✅ |
| 9 | Zaštita prava | Rž 1 u 386/2025 | 8944 | ✅ |
| 10 | Krivična | Kzz 123/2026 | 15054 | ✅ |

Checks per sample: decision_number non-empty, date parses as YYYY-MM-DD, raw_text_length ≥ 500, HTML file exists on disk.

**Audit result: 10/10 PASS**

**Observed text length range:** 2661 (Zaštita prava procedural) – 15,054 (Krivična merits). Zaštita prava decisions are shorter by design (they rule on žalba-na-nedonošenje-odluke, not on the merits of a case).

---

## Final Verdict

| Check | Result |
|-------|--------|
| Correct branch (`phase1-sudska-praksa`) | ✓ |
| Source is `vrh.sud.rs` only | ✓ |
| robots.txt Crawl-delay respected (10.5s) | ✓ |
| 200/200 collected | ✓ |
| 0 failed | ✓ |
| 3 partial (metadata only, body present) | ✓ noted |
| manifest.json written | ✓ |
| Quality audit 10/10 PASS | ✓ |
| Commit on feature branch | ✓ `113332e` |
| Feature branch pushed to origin | ✓ |
| main branch NOT touched | ✓ |
| Production NOT touched | ✓ |
| **Phase 1.0 COMPLETE** | **YES** |

---

## Notes for Phase 1.1 (Chunker)

### Expected chunk size

- Target: 400–800 tokens per chunk with 50-token overlap
- Krivična/Građanska/Upravna decisions: 4K–15K chars → 3–12 chunks each
- Zaštita prava decisions: 2.6K–9K chars → 2–7 chunks each
- Total estimated chunks: ~600–1200

### Metadata to carry on each chunk

```python
{
    "doc_type": "sudska_praksa",
    "court": "Vrhovni sud",
    "decision_number": "Kzz 754/2025",
    "decision_date": "2026-04-15",
    "matter": "Krivična",
    "registrant": "Kzz",
    "source_url": "https://www.vrh.sud.rs/sr-lat/...",
    "chunk_index": 0,
    "chunk_total": 3
}
```

### Edge cases to handle

1. **Empty `decision_number`** — 3 partials in zastitaprava. Use `decision_id` as fallback in display.
2. **Short decisions** — Zaštita prava procedural decisions may produce only 1–2 chunks. Minimum viable — keep them.
3. **Encoding** — All JSON files saved as UTF-8. Read with `open(..., encoding="utf-8")`.
4. **Sectioning** — VKS decisions have identifiable sections: `IZREKA:`, `OBRAZLOŽENJE:`, `Iz obrazloženja:`. Consider splitting on these to keep semantic units together.

### Pinecone namespace suggestion

Use `doc_type` field for namespace: `"sudska_praksa"` (separate from existing law-article vectors in default namespace). This keeps retrieval concerns cleanly separated until Phase 1.3 decides whether to merge or blend.

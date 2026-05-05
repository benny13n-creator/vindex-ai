# Vindex AI — Pre-Ingestion Reconnaissance Report
**Date:** 2026-05-04  
**Scope:** Full read-only inventory of ingestion scripts, PDFs, chunkers, metadata, and index state  
**Branch:** v3-confidence-gate-2026-05-04  
**Purpose:** Establish ground truth before wipe-and-rebuild of the Pinecone index  

---

## SECTION 1 — Ingestion Scripts

Five Python files write vectors to Pinecone. They fall into three generations.

---

### 1.1 Script inventory

| Script | Laws covered | Chunker | Last commit | Status |
|---|---|---|---|---|
| `reindex.py` | All 18 PDFs in bulk (via glob) | Internal: simple article split, 2000-char hard cut | 2026-04-24 (fae3cde) | **LEGACY — DELETE** |
| `ingest_kz_zpdg.py` | KZ, ZPDG, ZPD | Internal: article split + dual-chunk for priority articles | 2026-04-24 (fae3cde) | **LEGACY — DELETE** |
| `reindex_shortcodes.py` | KZ, ZPDG (rename-only script) | Re-uses `ingest_kz_zpdg.py` | 2026-04-24 (fae3cde) | **LEGACY — one-shot fix, now stale** |
| `ingest_kz.py` | KZ only | `semantic_chunker.podeli_zakon_na_chunkove` | 2026-05-04 (2f80cc3) | **CANONICAL for KZ** |
| `ingest_laws.py` | 13 laws (see §1.3) | `semantic_chunker.podeli_zakon_na_chunkove` | 2026-05-04 (2f80cc3) | **CANONICAL for all other laws** |
| `reindex_agentic.py` | All 18 PDFs in bulk (via glob) | `semantic_chunker.podeli_zakon_na_chunkove` | 2026-05-04 (2f80cc3) | **DEPRECATED BULK RUNNER — do not use** |

> `reindex_agentic.py` uses semantic_chunker but was designed as a one-time v1→v2 migration tool. Its key flaw: it does NOT delete old vectors before uploading — it accumulates. It also uses glob-based law discovery, which picks up `zakon_o_zastiti_potrosaca copy.pdf` and would produce a duplicate law entry.

---

### 1.2 Why the two canonical scripts are correct

**`ingest_kz.py`:**
- Delete-by-filter first (`law="KZ"`), then ingest KZ
- Uses `semantic_chunker` → full metadata with `parent_text`
- Post-ingest verification with 5 test queries
- Requires `PINECONE_HOST` env var (A1 fix applied)

**`ingest_laws.py`:**
- Delete-by-filter first for each law (primary name + all known alt names via `del_alts`)
- Uses `semantic_chunker` → full metadata with `parent_text`
- `--dry-run`, `--law SHORTCODE`, `--skip-delete` flags for safe operation
- Logs each law to `docs/INDEX_EXPANSION_LOG.md`
- Requires `PINECONE_HOST` env var (A1 fix applied)

---

### 1.3 Laws covered by `ingest_laws.py`

The LAWS list has **13 entries** (the docstring says "14" — it was counting KZ from `ingest_kz.py`):

| # | SC | Canonical law name (stored in `law` metadata field) | Source file |
|---|---|---|---|
| 1 | ZKP | `zakonik o krivicnom postupku` | `zakon_o_krivicnom_postupku.pdf` |
| 2 | ZOO | `zakon o obligacionim odnosima` | `zakon_o_obligacionim_odnosima.pdf` |
| 3 | ZPP | `zakon o parnicnom postupku` | `zakon_o_parnicnom_postupku.pdf` |
| 4 | ZR | `zakon o radu` | `zakon_o_radu.pdf` |
| 5 | PZ | `porodicni zakon` | `porodicni_zakon.pdf` |
| 6 | ZN | `zakon o nasledjivanju` | `zakon_o_nasledjivanju.pdf` |
| 7 | ZPD | `zakon o privrednim drustvima` | `zakon_o_privredin_drustvima.pdf` |
| 8 | ZOUP | `zakon o opstem upravnom postupku` | `zakon_o_opstem_upravnom_postupku.pdf` |
| 9 | ZIO | `zakon o izvrsenju i obezbedjenju` | `zakon_o_izvrsenju_i_obezbedjenju.pdf` |
| 10 | ZDI | `zakon o digitalnoj imovini` | `zakon_o_digitalnoj_imovini.pdf` |
| 11 | ZSPNFT | `zakon o sprecavanju pranja novca i finansiranja terorizma` | `zakon_o_sprecavanju_pranja_novca.pdf` |
| 12 | ZPDG | `zakon o porezu na dohodak gradjana` | `zakon_o_porezu_na_dohodak_gradjana.pdf` |
| 13 | USTAV | `ustav republike srbije` | `ustav_republike_srbije.pdf` |

**KZ is handled separately by `ingest_kz.py`** → `law="KZ"` (shortcode, not full name — this is intentional and consistent with `ZAKON_SHORTCODES`).

**Total canonical coverage: 14 laws.**

---

## SECTION 2 — PDF Source Files

Directory: `data/laws/pdfs/`

| Filename | Size | Last modified | Canonical law name | SC | Ingest script |
|---|---|---|---|---|---|
| `krivicni_zakonik.pdf` | 361 KB | 2026-04-25 | `KZ` | KZ | ingest_kz.py ✓ |
| `porodicni_zakon.pdf` | 151 KB | 2026-03-16 | `porodicni zakon` | PZ | ingest_laws.py ✓ |
| `ustav_republike_srbije.pdf` | 116 KB | 2026-03-16 | `ustav republike srbije` | USTAV | ingest_laws.py ✓ |
| `zakon_o_digitalnoj_imovini.pdf` | 186 KB | 2026-04-21 | `zakon o digitalnoj imovini` | ZDI | ingest_laws.py ✓ |
| `zakon_o_izvrsenju_i_obezbedjenju.pdf` | 361 KB | 2026-03-16 | `zakon o izvrsenju i obezbedjenju` | ZIO | ingest_laws.py ✓ |
| `zakon_o_krivicnom_postupku.pdf` | 487 KB | 2026-03-16 | `zakonik o krivicnom postupku` | ZKP | ingest_laws.py ✓ |
| `zakon_o_nasledjivanju.pdf` | 80 KB | 2026-03-16 | `zakon o nasledjivanju` | ZN | ingest_laws.py ✓ |
| `zakon_o_obligacionim_odnosima.pdf` | 452 KB | 2026-03-17 | `zakon o obligacionim odnosima` | ZOO | ingest_laws.py ✓ |
| `zakon_o_opstem_upravnom_postupku.pdf` | 138 KB | 2026-03-16 | `zakon o opstem upravnom postupku` | ZOUP | ingest_laws.py ✓ |
| `zakon_o_parnicnom_postupku.pdf` | 257 KB | 2026-03-16 | `zakon o parnicnom postupku` | ZPP | ingest_laws.py ✓ |
| `zakon_o_porezu_na_dohodak_gradjana.pdf` | 208 KB | 2026-04-25 | `zakon o porezu na dohodak gradjana` | ZPDG | ingest_laws.py ✓ |
| `zakon_o_privredin_drustvima.pdf` | 647 KB | 2026-04-25 | `zakon o privrednim drustvima` | ZPD | ingest_laws.py ✓ |
| `zakon_o_radu.pdf` | 165 KB | 2026-03-16 | `zakon o radu` | ZR | ingest_laws.py ✓ |
| `zakon_o_sprecavanju_pranja_novca.pdf` | 252 KB | 2026-04-22 | `zakon o sprecavanju pranja novca i finansiranja terorizma` | ZSPNFT | ingest_laws.py ✓ |
| `zakon_o_upravnim_sporovima.pdf` | **38 KB** | 2026-03-16 | `zakon o upravnim sporovima` | ZUS | **NO CANONICAL SCRIPT ⚠️** |
| `zakon_o_vanparnicnom_postupku.pdf` | 122 KB | 2026-03-16 | `zakon o vanparnicnom postupku` | ZVP | **NO CANONICAL SCRIPT ⚠️** |
| `zakon_o_zastiti_podataka_o_licnosti,.pdf` | 174 KB | 2026-03-16 | `zakon o zastiti podataka o licnosti` | ZZPL | **NO CANONICAL SCRIPT + BAD FILENAME ⚠️** |
| `zakon_o_zastiti_potrosaca.pdf` | 221 KB | 2026-03-17 | `zakon o zastiti potrosaca` | ZZP | **NO CANONICAL SCRIPT ⚠️** |
| `zakon_o_zastiti_potrosaca copy.pdf` | 221 KB | 2026-03-17 | *(duplicate of above)* | ZZP | **DUPLICATE — DELETE ⚠️** |

**19 files total. 1 duplicate. 1 bad filename. 14 have canonical ingest paths. 4 do not.**

### Anomalies requiring action before re-ingestion

**Anomaly 1: `zakon_o_zastiti_podataka_o_licnosti,.pdf`** — trailing comma in filename.  
This is not a PDF file in the binary sense — all `*.pdf` files here are plain text scraped from paragraf.rs. The comma causes fragile glob/stem matching. `reindex.py` hardcoded this key including the comma: `"zakon_o_zastiti_podataka_o_licnosti,": "zakon o zastiti podataka o licnosti"`. The canonical scripts have no entry for ZZPL at all.  
**Fix required:** Rename the file to `zakon_o_zastiti_podataka_o_licnosti.pdf` before ingestion.

**Anomaly 2: `zakon_o_zastiti_potrosaca copy.pdf`** — identical size (221,383 bytes) to `zakon_o_zastiti_potrosaca.pdf`.  
This is a duplicate. `reindex_agentic.py` strips " copy" suffix and would ingest this as the same law, doubling the ZZP vectors.  
**Fix required:** Delete `zakon_o_zastiti_potrosaca copy.pdf` before ingestion.

**Anomaly 3: `zakon_o_upravnim_sporovima.pdf`** — 38 KB. Extremely small for a full law.  
For context, even the smallest full law (Ustav) is 116 KB. At 38 KB, ZUS is likely an incomplete extract, a table of contents only, or the wrong file.  
**Fix required:** Verify content before ingestion.

**Anomaly 4: `zakon_o_privredin_drustvima.pdf`** — typo in filename (`privredin` not `privrednim`).  
This is already handled in `ingest_laws.py`'s LAWS entry (`"file": "zakon_o_privredin_drustvima.pdf"`). Not blocking — just ugly.

---

## SECTION 3 — Chunker Usage

**`semantic_chunker.py` is the only chunker in the repo.** No alternative implementations exist.

| Script | Uses semantic_chunker? | Fallback/alternative |
|---|---|---|
| `ingest_kz.py` | **Yes** — `from semantic_chunker import podeli_zakon_na_chunkove` | None |
| `ingest_laws.py` | **Yes** — `from semantic_chunker import podeli_zakon_na_chunkove` | None |
| `reindex_agentic.py` | **Yes** — same import | None |
| `reindex.py` | **No** — inline `_podeli_na_clanove()`, 2000-char limit, no `parent_text` | Legacy |
| `ingest_kz_zpdg.py` | **No** — inline `_podeli_na_clanove()`, 2000-char limit, no `parent_text`, "dual chunk" feature | Legacy |

**The chunker is NOT configurable via arguments.** Constants in `semantic_chunker.py`:
- `MIN_STAV_DUZINA = 60` — min chunk length to include
- `MAX_STAV_DUZINA = 300` — max search chunk length (embedded text)
- `MAX_PARENT_DUZINA = 3000` — max parent_text stored in metadata
- `STUB_THRESHOLD = 200` — parent_text shorter than this triggers a warning log

The chunker fix (v3, commit `292b060`) added the numbered-header branch to `_SECTION_HEADER_RE`. This is the version that should be used for re-ingestion.

---

## SECTION 4 — Metadata Schema

Three generations of metadata schemas exist in the live index simultaneously.

### Schema A — Old (reindex.py, ingest_kz_zpdg.py) — 3 fields

```python
{
    "law":     "krivicni zakonik",     # or "zakon o privrednim drustvima" etc.
    "article": "Član 203",
    "text":    "ZAKON: KZ\n<full article text, ≤2000 chars>",
}
```

**Critical defects:**
- No `parent_text` — retrieve.py falls back to `text` field, which is the same as the embedding text, not the full article
- `law` field uses inconsistent names ("krivicni zakonik" vs "KZ")
- `text` field includes the embedding prefix `"ZAKON: ..."` — not clean article text
- Single chunk per article regardless of length — no stav-level granularity

### Schema B — Current v2 (ingest_kz.py, ingest_laws.py, reindex_agentic.py via semantic_chunker) — 9 fields

```python
{
    # Semantic chunker fields
    "zakon":        "KZ",                    # short code
    "clan":         203,                     # article number (int)
    "stav":         1,                       # paragraph index within article (int)
    "parent_id":    "KZ_203",                # short code + article number
    "parent_text":  "<full article, ≤3000 chars, NO section headers>",
    "tekst_preview": "<first 100 chars of stav>",
    # Backward-compat fields (used by retrieve.py filters):
    "law":     "KZ",                         # full zakon_naziv passed to chunker
    "article": "Član 203",                   # human-readable label
    "text":    "<stav text, ≤300 chars>",    # clean stav text, no prefix
}
```

**retrieve.py dependency:** The pipeline reads `parent_text`, `law`, and `article` from metadata. The `zakon` field (short code) is currently used only by `reindex_agentic.py`'s verification query (`filter={"zakon": {"$eq": "ZPD"}}`). retrieve.py uses `law` (full name) for all filters.

**Schema B is the target for all re-ingested vectors.**

### Schema consistency across canonical scripts

Both `ingest_kz.py` and `ingest_laws.py` pass the full chunk metadata dict directly to Pinecone upsert (`metadata: chunk["metadata"]`). Both produce identical Schema B. The only difference: `ingest_kz.py` passes `"KZ"` as `zakon_naziv` → `law="KZ"`, while `ingest_laws.py` passes the full name → e.g., `law="zakon o obligacionim odnosima"`.

---

## SECTION 5 — Law Name Normalization

### What retrieve.py expects

`retrieve.py` uses two mechanisms to filter by law:

1. **`LAW_HINTS` keyword map** (`retrieve.py:42`) — 80+ keyword→law-name mappings. These are the exact strings used as Pinecone `law` filter values. Every filter in retrieve.py uses these exact law names.

2. **`ZAKON_SHORTCODES` in semantic_chunker.py** — maps full names → short codes for the `zakon` field. The `law` field stores the raw `zakon_naziv` argument passed to `podeli_zakon_na_chunkove()`.

### Canonical law names (as used in `retrieve.py` LAW_HINTS and `ingest_laws.py` LAWS)

| SC | `law` field value (stored in Pinecone) | In LAW_HINTS? |
|---|---|---|
| KZ | `"KZ"` | ✓ (via "krivicno delo", "kazna" etc.) |
| ZOO | `"zakon o obligacionim odnosima"` | ✓ |
| ZR | `"zakon o radu"` | ✓ |
| PZ | `"porodicni zakon"` | ✓ |
| ZKP | `"zakonik o krivicnom postupku"` | ✓ |
| ZPP | `"zakon o parnicnom postupku"` | ✓ |
| ZIO | `"zakon o izvrsenju i obezbedjenju"` | ✓ |
| ZN | `"zakon o nasledjivanju"` | ✓ |
| ZPD | `"zakon o privrednim drustvima"` | ✓ |
| ZOUP | `"zakon o opstem upravnom postupku"` | ✓ |
| ZUS | `"zakon o upravnim sporovima"` | ✓ |
| ZVP | `"zakon o vanparnicnom postupku"` | ✓ |
| ZZP | `"zakon o zastiti potrosaca"` | ✓ |
| ZSPNFT | `"zakon o sprecavanju pranja novca i finansiranja terorizma"` | ✓ |
| ZDI | `"zakon o digitalnoj imovini"` | ✓ |
| ZPDG | `"zakon o porezu na dohodak gradjana"` | **NOT in LAW_HINTS** ⚠️ |
| ZZPL | `"zakon o zastiti podataka o licnosti"` | **NOT in LAW_HINTS** ⚠️ |
| USTAV | `"ustav republike srbije"` | **NOT in LAW_HINTS** ⚠️ |

**ZPDG, ZZPL, and USTAV have no keyword triggers in LAW_HINTS.** Queries about income tax, data protection, or constitutional rights go to unfiltered search across all 23,699 vectors. This is an existing gap in retrieve.py that is separate from the ingestion fix, but worth noting.

### Where normalization fails (root cause of 7,858 unaccounted vectors)

The 7,858 unaccounted vectors from the ARCHITECTURAL_AUDIT are almost certainly old v1 vectors from `reindex.py` runs. `reindex.py` used these law names that do NOT match any current key:

| `reindex.py` law name stored | Current expected name | Status |
|---|---|---|
| `"krivicni zakonik"` | `"KZ"` | **Not in ZAKON_SHORTCODES → unaccounted** |
| `"zakon o krivicnom postupku"` *(possible)* | `"zakonik o krivicnom postupku"` | **Different prefix** |

`reindex_shortcodes.py` was a one-shot patch to rename `"krivicni zakonik"` → `"KZ"`. If it ran successfully, those vectors were fixed. But if it ran before the index was fully populated, or if `reindex.py` was run again afterward, the old names would re-appear.

Additionally, `reindex_agentic.py` ran without deleting first — it added v2 vectors on top of whatever v1 vectors existed. If some laws had their v1 vectors deleted (via `reindex_shortcodes.py` or individual law deletes) but the agentic `--cleanup` was never run for all laws, the index now contains a mix of v1 (3-field schema) and v2 (9-field schema) vectors for the same articles.

**The only reliable way to resolve this is a full index wipe.** Incremental delete-by-filter cannot catch all old names reliably. See §6 below.

---

## SECTION 6 — Pinecone Index State

### Current state
- **Total vectors:** ~23,699 (at time of ARCHITECTURAL_AUDIT, 2026-05-04)
- **Accounted (matching known law names):** ~15,841
- **Unaccounted (unknown law names):** ~7,858 (33%)

### Delete-then-insert behavior in canonical scripts

**`ingest_laws.py`** deletes by `law` filter using `del_alts` list before ingesting each law. For example, ZKP deletes:
- `law="zakonik o krivicnom postupku"` 
- `law="ZKP"`
- `law="zakonik o krivičnom postupku"` (diacritics variant)

This is thorough for names that are KNOWN to exist. It does NOT catch names that were never anticipated (e.g., `"zakon o krivicnom postupku"` — note different prefix).

**`ingest_kz.py`** deletes only `law="KZ"`. Does not delete `"krivicni zakonik"` or `"krivični zakonik"`.

### Idempotency

Both canonical scripts are idempotent by ID: the v2 chunk ID is `md5("v2|{zakon_naziv}|{clan_num}|{stav_idx}")`. If you run the same script twice with the same input file, Pinecone upsert overwrites the existing vectors with identical IDs. No duplication from double-run.

However, if the file changes (different article numbering or text), the stav count may change, producing new IDs while old ones persist. The `del_alts` delete step prevents this for the canonical scripts, since deletion by filter removes ALL vectors for the law regardless of ID.

### Recommended approach for clean rebuild

The safest path is **delete the entire index namespace** (or delete-all-vectors), then run:
1. `python ingest_kz.py` — KZ only (with `--skip-delete` since index is empty after wipe)
2. `python ingest_laws.py` — all 13 laws (with `--skip-delete` since index is empty)

This eliminates the 7,858 unaccounted vectors with zero risk of missing any old law name variant. The `--skip-delete` flag skips the per-law filter deletes, which is safe when starting from empty.

Note: Pinecone's free/starter tier supports `delete_all()` via namespace. The canonical scripts don't implement this — it would need to be called once manually via SDK or dashboard before ingestion.

---

## SECTION 7 — Recommended Canonical Law List

Based on everything above: **17 laws should be in a clean Vindex index** (14 with existing canonical ingest + 3 that need ingest_laws.py additions).

| # | SC | Law name (canonical) | PDF available | Ingest script | Action needed |
|---|---|---|---|---|---|
| 1 | KZ | `KZ` | ✓ (361 KB) | `ingest_kz.py` | None — ready |
| 2 | ZKP | `zakonik o krivicnom postupku` | ✓ (487 KB) | `ingest_laws.py` | None — ready |
| 3 | ZOO | `zakon o obligacionim odnosima` | ✓ (452 KB) | `ingest_laws.py` | None — ready |
| 4 | ZPP | `zakon o parnicnom postupku` | ✓ (257 KB) | `ingest_laws.py` | None — ready |
| 5 | ZR | `zakon o radu` | ✓ (165 KB) | `ingest_laws.py` | None — ready |
| 6 | PZ | `porodicni zakon` | ✓ (151 KB) | `ingest_laws.py` | None — ready |
| 7 | ZN | `zakon o nasledjivanju` | ✓ (80 KB) | `ingest_laws.py` | None — ready |
| 8 | ZPD | `zakon o privrednim drustvima` | ✓ (647 KB) | `ingest_laws.py` | None — ready |
| 9 | ZOUP | `zakon o opstem upravnom postupku` | ✓ (138 KB) | `ingest_laws.py` | None — ready |
| 10 | ZIO | `zakon o izvrsenju i obezbedjenju` | ✓ (361 KB) | `ingest_laws.py` | None — ready |
| 11 | ZDI | `zakon o digitalnoj imovini` | ✓ (186 KB) | `ingest_laws.py` | None — ready |
| 12 | ZSPNFT | `zakon o sprecavanju pranja novca i finansiranja terorizma` | ✓ (252 KB) | `ingest_laws.py` | None — ready |
| 13 | ZPDG | `zakon o porezu na dohodak gradjana` | ✓ (208 KB) | `ingest_laws.py` | None — ready |
| 14 | USTAV | `ustav republike srbije` | ✓ (116 KB) | `ingest_laws.py` | None — ready |
| 15 | ZVP | `zakon o vanparnicnom postupku` | ✓ (122 KB) | **Add to ingest_laws.py** | Add LAWS entry |
| 16 | ZZP | `zakon o zastiti potrosaca` | ✓ (221 KB) | **Add to ingest_laws.py** | Add LAWS entry |
| 17 | ZZPL | `zakon o zastiti podataka o licnosti` | ✓ (174 KB) | **Add to ingest_laws.py** | Rename PDF + add LAWS entry |

**Laws intentionally excluded:**

| SC | Reason |
|---|---|
| ZUS | PDF is 38 KB — suspiciously small. Verify content before deciding. If the PDF is a full law text, add to ingest_laws.py. If it's an extract or table of contents, replace the PDF first. |

**Pre-ingestion file cleanup required:**
1. Delete `zakon_o_zastiti_potrosaca copy.pdf`
2. Rename `zakon_o_zastiti_podataka_o_licnosti,.pdf` → `zakon_o_zastiti_podataka_o_licnosti.pdf`
3. Inspect `zakon_o_upravnim_sporovima.pdf` content (38 KB)

---

## Summary

| Item | Count | Notes |
|---|---|---|
| Total PDFs in data/laws/pdfs/ | 19 | |
| Duplicate PDFs to delete | 1 | `zakon_o_zastiti_potrosaca copy.pdf` |
| PDFs with bad filenames | 1 | ZZPL has trailing comma |
| PDFs to verify before use | 1 | ZUS (38 KB) |
| Canonical ingest scripts | 2 | `ingest_kz.py` + `ingest_laws.py` |
| Legacy scripts (should not run) | 3 | `reindex.py`, `ingest_kz_zpdg.py`, `reindex_shortcodes.py` |
| Laws ready to ingest today | 14 | KZ + 13 in ingest_laws.py |
| Laws needing ingest_laws.py addition | 3 | ZVP, ZZP, ZZPL |
| Laws under review | 1 | ZUS (PDF size suspect) |
| Unaccounted live index vectors | ~7,858 | Old law names from v1 runs — cleared by full wipe |
| Recommended rebuild approach | Full wipe → ingest all | Incremental delete cannot catch all old name variants |

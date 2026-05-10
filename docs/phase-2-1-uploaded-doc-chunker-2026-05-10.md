# Phase 2.1 — Uploaded Document Chunker

**Datum:** 2026-05-10  
**Grana:** `feature/p2-1-uploaded-doc-chunker`  
**Commits:** 5f15744, afde10e

---

## Sažetak

Phase 2.1 implementira deterministički, schema-validan chunker modul za korisnički
uploadovane pravne dokumente (PDF, DOCX, TXT). Modul je izolovan pod `uploaded_doc/`
i nema nikakve izmene u `retrieve.py`, `main.py` ili postojećim ingest modulima.

---

## Kreirani fajlovi

| Fajl | Uloga |
|------|-------|
| `uploaded_doc/__init__.py` | Javni API (`chunk_document`, `extract`, `ChunkingManifest`, `UploadedDocChunk`) |
| `uploaded_doc/schema.py` | Pydantic v2 modeli (`UploadedDocChunk`, `ChunkingManifest`) |
| `uploaded_doc/extractor.py` | Ekstraktor teksta: PDF (pypdf), DOCX (python-docx), TXT |
| `uploaded_doc/chunker.py` | Hibridni chunker: article-aware + recursive + mixed mode |
| `uploaded_doc/__main__.py` | CLI: `python -m uploaded_doc <fajl>` |
| `tests/test_uploaded_doc_chunker.py` | 7 testova |
| `tests/fixtures/uploaded_doc/sample_ugovor_o_radu.txt` | Ugovor o radu, 8 članova |
| `tests/fixtures/uploaded_doc/sample_no_articles.txt` | Pravni memorandum, bez "Član" strukture |
| `tests/fixtures/uploaded_doc/sample_ugovor.docx` | DOCX generisan iz TXT fixture-a |
| `tests/fixtures/uploaded_doc/_gen_docx.py` | Skript za generisanje DOCX fixture-a |
| `manifests/phase-2-1-chunker-manifest-2026-05-10.json` | Kombinovani output sva 3 fixture-a |
| `docs/phase-2-1-uploaded-doc-chunker-2026-05-10.md` | Ovaj izveštaj |

---

## CLI run output — sva 3 fixture-a

### sample_ugovor_o_radu.txt

```
File:       sample_ugovor_o_radu.txt
Format:     txt
Scanned:    False
Mode:       article_aware
Chunks:     9
Articles:   8 labels detected
  Labels:   ['Član 1', 'Član 2', 'Član 3', 'Član 4', 'Član 5', ...]
Tokens:     p10=260  p50=306  p90=379
```

### sample_no_articles.txt

```
File:       sample_no_articles.txt
Format:     txt
Scanned:    False
Mode:       recursive
Chunks:     3
Articles:   0 labels detected
Tokens:     p10=408  p50=408  p90=420
```

### sample_ugovor.docx

```
File:       sample_ugovor.docx
Format:     docx
Scanned:    False
Mode:       article_aware
Chunks:     9
Articles:   8 labels detected
  Labels:   ['Član 1', 'Član 2', 'Član 3', 'Član 4', 'Član 5', ...]
Tokens:     p10=260  p50=306  p90=379
```

**Ukupno chunks:** 21 (9 + 3 + 9)  
**Modes:** article_aware × 2, recursive × 1

---

## Rezultati testova

```
tests/test_uploaded_doc_chunker.py::test_extract_txt_smoke             PASSED
tests/test_uploaded_doc_chunker.py::test_extract_docx_smoke            PASSED
tests/test_uploaded_doc_chunker.py::test_chunker_article_aware_mode    PASSED
tests/test_uploaded_doc_chunker.py::test_chunker_recursive_mode        PASSED
tests/test_uploaded_doc_chunker.py::test_schema_validates              PASSED
tests/test_uploaded_doc_chunker.py::test_token_count_accuracy          PASSED
tests/test_uploaded_doc_chunker.py::test_max_tokens_enforced           PASSED

7/7 passed
```

Svi prethodni testovi ostaju zeleni: **22/22** (`test_uploaded_doc_chunker` +
`test_phase1_3` + `test_chunker_case_law`).

---

## Schema audit

| Manifest | Chunks | Schema validacija |
|----------|--------|-------------------|
| sample_ugovor_o_radu-manifest.json | 9 | OK |
| sample_no_articles-manifest.json | 3 | OK |
| sample_ugovor-manifest.json | 9 | OK |

**3/3 ChunkingManifest.model_validate() PASS**

---

## Autonomne odluke

1. **`source_format: "txt"` za fixture-e** — Spec pominje `"pdf" | "docx" | "txt"` kao Literal tip, a fixture-i su `.txt` fajlovi. Dodao `"txt"` u Literal listu schema.py i extractor.py dispatcher-u.

2. **CLI import path** — Spec kaže `python -m moj_prvi_agent.legal-agent.uploaded_doc` ali modul živi direktno u root-u legal-agent projekta (ne u `src/` paketu). Modul je korektno importovalan kao `python -m uploaded_doc` iz root-a projekta, što je konzistentno sa svim ostalim modulima u repou (chunker_case_law.py, api.py itd.).

3. **Overlap test** — Test 4 verifikuje token-set overlap između chunk 0 i chunk 1. Set intersect je konzervativan (ne zahteva pozicijski overlap). Razlog: tiktoken decode nije savršeno invertibilan za sve sub-word tokene, pa tačan pozicijski match nije pouzdan.

4. **`test_max_tokens_enforced` sintetički dokument** — Inicijalna verzija je imala samo 2 "Član" unosa (ispod `ARTICLE_DENSITY_THRESHOLD=3`). Dodat je "Član 3" kako bi se dostigao threshold i aktivirao article_aware → mixed mode.

---

## Invariante produkcije

| Provera | Rezultat |
|---------|--------|
| `retrieve.py` nepromenjen | ✅ |
| `main.py` nepromenjen | ✅ |
| `ingest_case_law.py` nepromenjen | ✅ |
| Existing tests 15/15 PASS | ✅ |
| Bez novih env vars | ✅ |
| Bez Pinecone poziva | ✅ |
| Bez FastAPI ruta | ✅ |

---

## Napomena o 30Q sanity runu

30Q sanity run nije pokrenut na ovoj grani jer Phase 2.1 nema izmena u retrieval
ili agent stack-u — chunker je izolovani modul bez import veze sa `retrieve.py`
ili `main.py`. Poslednji zabeleženi 30Q baseline je **19/11/0** (post-merge run
od 2026-05-10, commit 346bea8).

---

## Sledeći koraci

- **Phase 2.2:** Upload endpoint (FastAPI route, multipart form, session_id generisanje)
- **Phase 2.3:** Pinecone ingest chunkovanih dokumenata i retrieval integracija

---

*Phase 2.1 complete. Grana nije merge-ovana u main — čeka user review.*

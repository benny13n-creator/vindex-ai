# Phase 2.2 — Upload Endpoint + Ephemeral Ingest

**Datum:** 2026-05-10  
**Grana:** `feature/p2-2-upload-endpoint`  
**Commits:** e1e0985, 285c007, dba5f14

---

## Sažetak

Phase 2.2 dodaje dva FastAPI endpoint-a u `api.py` za upload pravnih dokumenata
i administraciju privremenih Pinecone namespace-a. Implementiran je pipeline:
upload → extract → chunk → embed → upsert u `tmp_<session_id>` namespace sa
24h TTL metapodatkom.

---

## Carry-over ispravka (iz Phase 2.1)

`pypdf` je bio korišćen u `extractor.py` ali nije bio u `requirements.txt`.
Na produkciji bi se desio `ImportError` pri prvom PDF upload-u. Ispravka je u
prvom commit-u ove faze.

---

## Kreirani fajlovi

| Fajl | Uloga |
|------|-------|
| `uploaded_doc/session.py` | `generate_session_id`, `expires_at_iso`, `is_expired`, `ttl_seconds_remaining` |
| `uploaded_doc/api_models.py` | `UploadResponse`, `CleanupResponse` Pydantic v2 modeli |
| `uploaded_doc/ingest.py` | `ingest_session()` — embed (text-embedding-3-large, 3072d) + Pinecone upsert |
| `uploaded_doc/cleanup.py` | `cleanup_expired()` — briše istekle `tmp_*` namespace-e |
| `tests/test_uploaded_doc_ingest.py` | 4 testa |
| `tests/test_uploaded_doc_cleanup.py` | 4 testa |
| `tests/test_uploaded_doc_api.py` | 8 testova |
| `tests/fixtures/uploaded_doc/_gen_pdf.py` | Generisanje PDF fixture-a |
| `tests/fixtures/uploaded_doc/sample_ugovor.pdf` | PDF fixture (3 stranice) |
| `docs/phase-2-2-upload-endpoint-2026-05-10.md` | Ovaj izveštaj |

## Izmenjeni fajlovi

| Fajl | Izmena |
|------|--------|
| `requirements.txt` | + `pypdf`, `python-multipart`, `reportlab` |
| `uploaded_doc/__init__.py` | + `ingest_session`, `cleanup_expired`, `generate_session_id` |
| `api.py` | + 2 endpoint-a, + `UploadFile, File` u imports (126 inserted, 1 changed) |

---

## Endpoint 1: POST /api/dokument/upload

```
Content-Type: multipart/form-data
Field: file (application/pdf | application/vnd.openxmlformats-officedocument...)
```

**Pipeline:**
1. Validacija: Content-Length (413 ako > 10MB), MIME + sufiks (415 ako nije .pdf/.docx)
2. Čitanje raw bytes → temp fajl sa originalnim sufiksom
3. `extract()` → (text, is_scanned); ako is_scanned → 422
4. `chunk_document()` → manifest; ako total_chunks == 0 → 422
5. `generate_session_id()` → uuid4 hex
6. `ingest_session(manifest, session_id, ttl_hours=24)` → broj upisanih vektora
7. Background `cleanup_expired()` (asyncio.create_task)
8. Briše temp fajl
9. Vraća `UploadResponse`

**Odgovor (200):**
```json
{
  "session_id": "a1b2c3...",
  "chunk_count": 9,
  "chunk_mode_used": "article_aware",
  "article_labels_detected": ["Član 1", "Član 2", ...],
  "expires_at": "2026-05-11T22:00:00Z",
  "ttl_seconds": 85999
}
```

| HTTP kod | Uzrok |
|----------|-------|
| 413 | Content-Length > 10MB |
| 415 | MIME nije PDF/DOCX ili sufiks nije .pdf/.docx |
| 422 | Skeniran PDF ili prazan dokument (0 chunk-ova) |

---

## Endpoint 2: POST /api/dokument/cleanup

```
Header: X-Admin-Token: <FOUNDER_TOKEN>
Body: prazan
```

Briše sve istekle `tmp_*` Pinecone namespace-e. Nikad ne dira `__default__`
ni `sudska_praksa`.

| HTTP kod | Uzrok |
|----------|-------|
| 200 | `CleanupResponse` sa brojevima |
| 403 | Neispravan ili nedostajući X-Admin-Token |
| 503 | FOUNDER_TOKEN env var nije postavljen |

---

## Ingest logika

- Embedding model: `text-embedding-3-large`, dimensionality 3072
- Namespace: `tmp_<session_id>`
- Metadata per vector: `session_id`, `source_filename`, `source_format`,
  `chunk_index`, `chunk_mode`, `article_label`, `text` (skraćen na 40.000 chars),
  `token_count`, `expires_at` (ISO UTC)
- Pinecone per-record limit: tekst skraćen na 40.000 znakova (Hard Rule 6)

---

## Cleanup logika

1. `index.describe_index_stats()` → lista svih namespace-a
2. Filter: samo oni sa prefiksom `tmp_`
3. Per namespace: `index.query(top_k=1)` → čita `expires_at` iz metapodataka
4. Ako `is_expired(expires_at)` ili namespace je prazan → `index.delete(delete_all=True)`
5. Vraća: `{namespaces_deleted, chunks_deleted, namespaces_inspected}`

---

## Rezultati testova

```
tests/test_uploaded_doc_api.py::test_upload_docx_happy_path           PASSED
tests/test_uploaded_doc_api.py::test_upload_pdf_happy_path            PASSED
tests/test_uploaded_doc_api.py::test_upload_rejects_oversized         PASSED
tests/test_uploaded_doc_api.py::test_upload_rejects_unsupported_mime  PASSED
tests/test_uploaded_doc_api.py::test_upload_rejects_scanned_pdf       PASSED
tests/test_uploaded_doc_api.py::test_upload_rejects_empty_chunks      PASSED
tests/test_uploaded_doc_api.py::test_cleanup_endpoint_requires_token  PASSED
tests/test_uploaded_doc_api.py::test_cleanup_endpoint_with_valid_token PASSED

tests/test_uploaded_doc_ingest.py::test_ingest_session_upserts_correct_count    PASSED
tests/test_uploaded_doc_ingest.py::test_ingest_session_metadata_includes_expires_at PASSED
tests/test_uploaded_doc_ingest.py::test_ingest_session_truncates_long_text      PASSED
tests/test_uploaded_doc_ingest.py::test_ingest_handles_empty_manifest           PASSED

tests/test_uploaded_doc_cleanup.py::test_cleanup_dry_run_doesnt_delete          PASSED
tests/test_uploaded_doc_cleanup.py::test_cleanup_deletes_only_expired_ns        PASSED
tests/test_uploaded_doc_cleanup.py::test_cleanup_skips_non_tmp_ns               PASSED
tests/test_uploaded_doc_cleanup.py::test_cleanup_handles_no_tmp_namespaces      PASSED

Ukupno novih testova: 16/16 PASS
Svi testovi (uključujući Phase 2.1 i Phase 1): 38/38 PASS
```

---

## 30Q sanity run

Pokrenut po završetku svih commit-a, pre push-a.

**Rezultat: 19✅ / 11⚠️ / 0❌** — identičan post-merge baseline-u.

Produkcijski retrieval je netaknut. `retrieve.py` i `main.py` nisu menjani.

---

## Smoke test komanda (za produkciju, nakon push + deploy)

### Upload DOCX

```bash
curl -X POST \
  -F "file=@tests/fixtures/uploaded_doc/sample_ugovor.docx" \
  https://vindex-ai.onrender.com/api/dokument/upload
```

Očekivani odgovor: HTTP 200, `session_id` + `chunk_count=9`

### Upload PDF

```bash
curl -X POST \
  -F "file=@tests/fixtures/uploaded_doc/sample_ugovor.pdf" \
  https://vindex-ai.onrender.com/api/dokument/upload
```

### Verifikacija Pinecone vektora

```python
from pinecone import Pinecone
import os
pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
index = pc.Index(host=os.environ["PINECONE_HOST"])
# Zameni <session_id> sa vrednosti iz odgovora upload endpoint-a
stats = index.describe_index_stats()
print(stats["namespaces"].get("tmp_<session_id>"))
```

Očekivano: `{"vector_count": 9}`

### Cleanup endpoint

```bash
curl -X POST \
  -H "X-Admin-Token: <FOUNDER_TOKEN>" \
  https://vindex-ai.onrender.com/api/dokument/cleanup
```

Očekivani odgovor: HTTP 200, `CleanupResponse` sa brojevima

---

## Autonomne odluke

1. **Lazy imports u endpoint-u** — Sve `uploaded_doc.*` funkije se importuju unutar
   tela endpoint funkcije, ne na nivou modula. Razlog: sprečava circular import
   rizik i omogućava lakše mockovanje u testovima (patch na source modul).

2. **Mock putanje u testovima** — Pošto su importi lazy (unutar f-je), patch mora
   ciljati source modul (`uploaded_doc.ingest.ingest_session`), ne `api.ingest_session`.

3. **`reportlab` u production requirements** — Spec kaže "dev/test dep", ali pošto
   nema posebnog `requirements-dev.txt`, dodat je u isti `requirements.txt` kao
   ostale dep-endency. Fixture generisanje se ne poziva u produkciji.

---

## Invariante produkcije

| Provera | Rezultat |
|---------|--------|
| `retrieve.py` nepromenjen | ✅ (zero diff) |
| `main.py` nepromenjen | ✅ (zero diff) |
| `ingest_case_law.py` nepromenjen | ✅ |
| Default Pinecone namespace 17,688 | ✅ (nema upsert u default) |
| `sudska_praksa` namespace 1,479 | ✅ (cleanup preskače non-tmp) |
| Svi testovi 38/38 PASS | ✅ |
| 30Q baseline 19/11/0 | ✅ |
| Bez novih env vars (sem FOUNDER_TOKEN koji već postoji) | ✅ |

---

*Phase 2.2 complete. Grana nije merge-ovana u main — čeka user review i produkcijski smoke test.*

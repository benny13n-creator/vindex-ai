# BETA-DATA-ID-01 — Forenzički inventar identiteta vektora (§2, §3)

**Baseline:** `82450875`
**Metod:** samo čitanje. Nijedan produkcijski fajl, test ni migracija nisu menjani.
Prema Pinecone-u pozvani su samo `describe_index_stats()` i `Index.list()` (samo ID-evi).
Prema Supabase-u samo `select(...)` — nijedan `insert`/`update`/`delete`.
**Pravilo dokaza:** svaka tvrdnja nosi `fajl:linija` ili izmereni izlaz. Gde dokaza nema — `OPEN GAP`.

---

## 0. UPOZORENJE: radno stablo se promenilo TOKOM revizije

Na početku revizije radno stablo je bilo čisto na `82450875`. Na kraju:

```
 M routers/law_upload.py
 M uploaded_doc/ingest.py
?? shared/vector_identity.py
```

Drugi agent paralelno implementira model identiteta (§4+ iste misije). **Ceo inventar
ispod opisuje BASELINE `82450875`** (svi fajlovi su pročitani pre nastanka drifta, što je
potvrđeno `git diff`-om). Analiza drifta je u §7 — sadrži jedan nalaz koji bi, ako se ne
ispravi, oborio jednog postojećeg pisača.

---

## 1. KORAK 1 — INVENTAR (§2)

Skraćenice u kolonama: `DET?` = deterministički, `AUTH?` = koristi se za autorizaciju,
`DEL?` = koristi se za brisanje, `RETRY?` = koristi se za idempotenciju/ponavljanje.

### A. Izvori `document_id`

| FILE | LINE | FUNCTION | CURRENT ID | SOURCE | DET? | AUTH? | DEL? | RETRY? |
|---|---|---|---|---|---|---|---|---|
| `supabase_setup.sql` | 356 | DDL | `predmet_dokumenti.id` | `gen_random_uuid()` (Postgres) | ne (nasumičan), ali **kanonski PK** | ne | ne | ne |
| `api.py` | 5301 | `upload_predmet_dokument` | `_dok_id` | `_ins.data[0]["id"]` — **tek POSLE Pinecone upsert-a** | n/a | ne | ne | ne |
| `routers/smart_intake.py` | 1524 | `finalize_intake_job` | `dokument_id_i` | `dok_ins.data[0]["id"]` — **tek POSLE Pinecone upsert-a** | n/a | ne | ne | ne |
| `routers/drafting.py` | 414 | `_promote_staged_draft_to_pinecone` | — | insert bez čitanja `id` | n/a | ne | ne | ne |
| `routers/dokument.py` | 288 | `dokument_upload` | **ne postoji** | dokument nikad ne dobija red | — | — | — | — |
| `shared/intake_documents.py` | — | `create_document` | `intake_documents.id` | odvojen PK, **nikad ne ulazi u Pinecone** | ne | ne | ne | da (`delete_partial_document`) |
| `routers/law_upload.py` | 207 | `upload_zakon` | `doc_id = uuid4()` | **generisan PRE ingesta**, upisan u `law_docs.id` | ne (uuid4) ali **postoji pre upsert-a** | ne | ne | ne |
| `routers/knowledge_base.py` | 186 | `knowledge_save` | `entry_id` | `user_knowledge.id`, **pribavljen PRE Pinecone-a** | n/a | ne | **DA** (:386) | **DA** (upsert prepisuje) |

**Kanonski ID dokumenta je `predmet_dokumenti.id`** (`uuid`, PK, potvrđeno živom sondom §3).
Nijedan vektor u `pred_*` namespace-u ga ne nosi ni u ID-u ni u metapodacima —
`uploaded_doc/ingest.py:96-108` (baseline) upisuje `session_id`, `predmet_id`,
`kancelarija_id`, ali **nikad `document_id`**.

### B. Izvori verzije dokumenta

| FILE | LINE | FUNCTION | CURRENT ID | SOURCE | DET? | AUTH? | DEL? | RETRY? |
|---|---|---|---|---|---|---|---|---|
| `migrations/095_intake_bulletproofing.sql` | 21 | DDL | `content_sha256` | SHA-256 ekstrahovanog teksta | **DA** | ne | ne | **DA** (jedini pravi mehanizam) |
| `api.py` | 5164 | upload | `_content_sha256` | `sha256(raw)` — **heš BAJTOVA FAJLA** | DA | ne | ne | ne (samo informativan flag, :5796) |
| `routers/smart_intake.py` | 1341 | finalize | `content_hash` | `sha256(seg_text)` — **heš TEKSTA** | DA | ne | ne | **DA** (:1352-1372) |
| `migrations/105_...sql` | 22 | DDL | `redni_broj` | max+1 po predmetu | ne | ne | ne | ne |
| `migrations/106_...sql` | 28 | DDL | `UNIQUE(predmet_id, redni_broj)` | — | — | — | — | DA (23505 → retry) |

**Pojam verzije dokumenta NE POSTOJI.** `content_sha256` je *identitet sadržaja*, ne
verzija: nema kolone koja bi rekla „ovo je v2 istog dokumenta", nema self-FK na prethodnu
verziju, nema `supersedes`. `redni_broj` je redni broj dokumenta *u predmetu* (DOK-01,
DOK-02), ne verzija jednog dokumenta.

**Merena nekonzistentnost:** `api.py:5164` hešira **bajtove fajla**, `smart_intake.py:1341`
hešira **ekstrahovani tekst**. Isti PDF kroz dva pipeline-a daje **dva različita**
`content_sha256`. Dedup između Pipeline A i Pipeline C stoga ne radi. `OPEN GAP`.

### C. Generatori `chunk_id`

| FILE | LINE | FUNCTION | CURRENT ID | SOURCE | DET? | AUTH? | DEL? | RETRY? |
|---|---|---|---|---|---|---|---|---|
| `uploaded_doc/chunker.py` | **157** | `chunk_document` | `str(uuid.uuid4())` | čist slučaj | **NE** | ne | ne | ne |
| `semantic_chunker.py` | 107 | `_chunk_id` | `md5("v2\|{zakon}\|{clan}\|{stav}")` | semantika | **DA** | ne | ne | DA (prepisuje) |
| `chunker_case_law.py` | 279 | — | `{decision_id}__chunk_{idx}` | ID odluke | **DA** | ne | ne | DA |
| `scripts/ingest_sudskapraksa.py` | 428 | — | `sp_{odluka_id}__chunk_{i}` | ID odluke | **DA** | ne | ne | DA |
| `routers/law_upload.py` | 137 | `_run_ingest_sync` | `{safe_id}_c{ci}` | `law_docs.id` + index | **DA** (uz dati `doc_id`) | ne | ne | DA |
| `routers/auto_discovery.py` | 199-200 | `_upiši_pinecone` | `discovery_{sha256(chunk)[:32]}` | heš sadržaja | **DA** | ne | ne | DA |
| `routers/batch_ingest.py` | 93 | — | `{ascii_id}_c{i}` | `decision_id` + index | **DA** | ne | ne | DA |
| `routers/knowledge_base.py` | 107 | `_kb_embed_and_upsert` | `kb_{uid}_{beleska_id}` | vlasnik + PK reda | **DA** | ne | **DA** | **DA** |
| `drafting/playbook.py` | 82 | `ingest_playbook` | `pb_{uid}_{i}_{uuid4[:8]}` | delom slučaj | **NE** | ne | ne | ne |
| `interni_stavovi.py` | 76 | `ingest_stav` | `is_{uid[:8]}_{i}_{uuid4[:8]}` | delom slučaj | **NE** | ne | ne | ne |

`uploaded_doc/chunker.py:157` je jedini generator za **sve dokumente predmeta** i on je
`uuid4()`. `uploaded_doc/ingest.py:110` (baseline) taj `chunk_id` koristi doslovno kao
Pinecone `id`.

### D. Pinecone metadata polja — po svakom pisaču (iscrpno)

| PISAČ | FILE:LINE | POLJA |
|---|---|---|
| **P1 — `ingest_session` (zajednički sink)** | `uploaded_doc/ingest.py:96-108` | `session_id`, `source_filename`, `source_format`, `chunk_index`, `chunk_mode`, `article_label`, `text` (do 40k), `token_count`, `expires_at` |
| P1 + `extra_metadata` (Pipeline A) | `api.py:5208-5218` | `predmet_id`, `kancelarija_id`, `type="case_doc"`, `origin=CLIENT_DOC`, `parent_id=""`, `origin_chain`, `created_at`, `golden_template=False` |
| P1 + `extra_metadata` (Pipeline C) | `routers/smart_intake.py:1404-1413` | isto kao gore |
| P1 + `extra_metadata` (nacrt) | `routers/drafting.py:359-368` | `predmet_id`, `kancelarija_id`, `type="draft_final"`, `origin=LAWYER_VERIFIED`, `parent_id=staging_row.id`, `origin_chain=[AI_GENERATED, LAWYER_VERIFIED]`, `created_at`, `golden_template=False` |
| P1 + `extra_metadata` (tmp) | `routers/dokument.py:302-311` | **samo** `origin=CLIENT_DOC`, `owner_user_id` |
| **P2 — playbook** | `drafting/playbook.py:84-89` | `user_id`, `filename`, `chunk_index`, `text` |
| **P3 — interni stavovi** | `interni_stavovi.py:78-84` | `user_id`, `naslov`, `chunk_index`, `text`, `tip="interni_stav"` |
| **P4 — baza znanja** | `routers/knowledge_base.py:109-116` | `beleska_id`, `naslov`, `sadrzaj`, `tagovi`, `predmet_id`, `user_id` |
| **P5 — upload zakona** | `routers/law_upload.py:128-135` | `text`, `naziv_zakona`, `broj_sl_glasnika`, `chunk_index`, `doc_id`, `source="admin_law_upload"` |
| **P6 — batch ingest** | `routers/batch_ingest.py:95-100` | `text`, `chunk_index`, `decision_id`, + prosleđeni metapodaci |
| **P7 — auto discovery** | `routers/auto_discovery.py:201-205` | prosleđeni metapodaci + `text` (1500), `chunk_index` |

**Nijedan pisač ne upisuje `document_id`.** `predmet_id` upisuju samo P1 (Pipeline A/C/nacrt)
i P4. `owner_user_id` upisuje samo `routers/dokument.py`.

### E. `upsert` pozivi ka Pinecone-u (produkcijski kod)

Nezavisan AST-scan (ne grep) nad produkcijskim direktorijumima; kriterijum
`Call.func.attr == "upsert"` sa `vectors=`/`namespace=` (Supabase `upsert` ima
pozicioni dict, pa se ne meša):

| # | FILE:LINE | NAMESPACE |
|---|---|---|
| 1 | `uploaded_doc/ingest.py:124` | `namespace_override` ili `{prefix}{session_id}` |
| 2 | `drafting/playbook.py:94` | `playbook_{user_id}` |
| 3 | `interni_stavovi.py:89` | `interni_stavovi_{user_id}` |
| 4 | `routers/knowledge_base.py:105` | `kb_{uid}` |
| 5 | `routers/law_upload.py:92` | `"zakoni_rs"` (hard-kodovan) |
| 6 | `routers/batch_ingest.py:63` | parametar |
| 7 | `routers/auto_discovery.py:212` | parametar |

**Ispravka ranijih sprinteva:** „6 pisaca ingesta" iz prethodnih izveštaja nisu upsert
mesta nego *pozivaoci*. Fizičkih upsert mesta u produkcijskom kodu ima **7**.
`routers/auto_discovery.py:212` i `routers/batch_ingest.py:63` **nisu bili u zadatoj listi**
— pronađeni su AST prolazom (v. §5, negativna kontrola).

### F. Generatori namespace-a

| FILE | LINE | FUNCTION | OBRAZAC | DET? | AUTH? | DEL? | RETRY? |
|---|---|---|---|---|---|---|---|
| `shared/kancelarija_utils.py` | 57-59 | `rag_owner_namespace` | `kancelarija_{id}` / `user_{id}` | **DA** | ne (filter je zaseban) | ne | ne |
| `uploaded_doc/ingest.py` | 68 | `ingest_session` | `tmp_{session_id}` | ne (uuid4) | ne | **DA** (cleanup) | ne |
| `uploaded_doc/session.py` | 7 | `generate_session_id` | `uuid4().hex` | **NE** | ne | ne | ne |
| `drafting/playbook.py` | 18 | — | `playbook_{user_id}` | DA | **implicitno** | DA (delete_all) | ne |
| `interni_stavovi.py` | 18 | — | `interni_stavovi_{user_id}` | DA | **implicitno** | DA (delete_all) | ne |
| `routers/knowledge_base.py` | 118 | — | `kb_{uid}` | DA | **implicitno** | DA | DA |
| `app/services/retrieve.py` | — | — | `zakoni_rs`, `sudska_praksa`, `misljenja` konstante | DA | ne | ne | ne |

### G. Retry putanje

| FILE | LINE | ŠTA PONAVLJA | IDEMPOTENTNO? |
|---|---|---|---|
| `shared/llm_retry.py` (`@llm_retry`) | `routers/knowledge_base.py:52,59` | OpenAI embed/tag poziv | DA — upsert ide na isti `kb_{uid}_{id}` |
| `uploaded_doc/ingest.py` | 121-132 | **ne ponavlja**; podiže izuzetak, već upisani batch-evi **ostaju** (komentar :115-118) | **NE** |
| `routers/law_upload.py` | 139-144 | **ne ponavlja**; pali batch se loguje i preskače, `status="done"` ako je `upserted>0` | **NE** — delimičan indeks prijavljen kao gotov |
| `shared/intake_worker.py` | 445-460 | segment; `delete_partial_document` čisti DB red | DA za DB — **Pinecone se u ovom sloju ne dodiruje uopšte** (0 pogodaka za `pinecone`/`upsert` u fajlu) |
| `routers/smart_intake.py` | 1352-1372 | preskače dokument ako `content_sha256` već postoji u istom predmetu | DA — **ali samo ako je prethodni pokušaj stigao do DB insert-a** |
| `routers/smart_intake.py` | 1494-1521 | `redni_broj` 23505 konflikt, 3 pokušaja | DA (samo DB) |
| `routers/drafting.py` | 1276-1295 | atomsko `status: pending→approved` pre promocije | DA |

### H. Pisci statusa dokumenta

| FILE | LINE | VREDNOST | IZVOR ODLUKE |
|---|---|---|---|
| `supabase_setup.sql` | 362 | `'na_cekanju'` (DEFAULT) | — |
| `api.py` | 5279 | `indeksirano` / `sacuvano` | `ingest_je_potpun(count, total_chunks)` |
| `routers/smart_intake.py` | 1436 | `indeksirano` / `sacuvano` | isto |
| `routers/drafting.py` | 398 | `indeksirano` / `sacuvano` | isto |
| `routers/intake.py` | 314 | `sacuvano` (fiksno) | wizard samo povezuje |
| `routers/onboarding.py` | 284 | `demo` (fiksno) | sintetički red |
| `routers/law_upload.py` | 155-168 | `pending`/`running`/`done`/`failed`/`obrisan` | **druga tabela** (`law_docs`) |

### I. Delete / remove putanje

| FILE | LINE | ŠTA BRIŠE | GRANULARNOST |
|---|---|---|---|
| `routers/knowledge_base.py` | 385-388 | `index.delete(ids=[f"kb_{uid}_{id}"], namespace=...)` | **PO ZAPISU** — jedini precizan delete u repou |
| `drafting/playbook.py` | 131 | `delete_all=True` na `playbook_{uid}` | ceo namespace |
| `interni_stavovi.py` | 133 | `delete_all=True` na `interni_stavovi_{uid}` | ceo namespace |
| `uploaded_doc/cleanup.py` | 90 | `delete_all=True` na istekle `tmp_*` | ceo namespace |
| `routers/evidence.py` | 436-441 | soft delete `predmet_dokazi.deleted_at` | **druga tabela**, Pinecone netaknut |
| `routers/law_upload.py` | 277 | `law_docs.status='obrisan'` | soft, **„NE briše iz Pinecone"** (docstring :269) |

**Za `predmet_dokumenti` ne postoji nijedan delete endpoint.** Popis svih 28
`@router.delete`/`@app.delete` ruta u `routers/`, `api.py`, `klijenti/` ne sadrži nijednu
koja briše dokument predmeta ni njegove vektore. `routers/gdpr.py:201`
(`DELETE /api/gdpr/account`) nema **nijednu** referencu na Pinecone (0 pogodaka).

### J. Re-ingest putanje

| FILE | LINE | OKIDAČ | DUPLIRA VEKTORE? |
|---|---|---|---|
| `routers/knowledge_base.py` | 338-347 | `PUT /api/knowledge/{id}` re-embed | **NE** — isti ID prepisuje |
| `routers/law_upload.py` | 173 | ponovljen upload istog PDF-a | **DA** — nov `uuid4` `doc_id` → nov `safe_id` |
| `api.py` | 5205 | ponovljen upload istog fajla | **DA** — novi `uuid4` chunk ID-evi |
| `routers/smart_intake.py` | 1401 | ponovljen finalize | NE ako je prethodni stigao do DB; **DA** inače |
| `routers/evidence.py` | 447 | `reklasifikuj` | ne dodiruje Pinecone |
| `routers/drafting.py` | 357 | ponovni approve | NE (claim gate) |

### K. Upload putanje

`UploadFile` se pojavljuje u 11 fajlova. Putanje koje vode do vektora:

| # | ENDPOINT | FILE:LINE | → VEKTORI |
|---|---|---|---|
| U1 | `POST /api/predmeti/{id}/dokument` | `api.py:5205` | `kancelarija_`/`user_` |
| U2 | `POST /api/dokument/upload` | `routers/dokument.py:301` | `tmp_{session}` |
| U3 | Smart Intake finalize | `routers/smart_intake.py:1401` | `kancelarija_`/`user_` |
| U4 | `POST /api/playbook` | `routers/drafting.py:570` | `playbook_{uid}` |
| U5 | `POST /api/admin/law/upload` | `routers/law_upload.py:173` | `zakoni_rs` |
| U6 | `POST /interni-stavovi/dodaj` | `routers/interni.py:37` | `interni_stavovi_{uid}` |
| U7 | `POST /api/knowledge/save` | `routers/knowledge_base.py:159` | `kb_{uid}` |
| U8 | client portal upload | `routers/client_portal.py:588` | **NE** — samo Storage |
| U9 | `routers/voice.py`, `csv_import.py`, `import_klijenti.py` | — | **NE** |

### L. Mesta gde se ISTI dokument može ponovo indeksirati

1. `api.py:5183-5190` — duplikat se **detektuje ali ne blokira**; `_mozda_duplikat` se samo
   vraća u odgovoru (`api.py:5796`). Novi upload = novi `uuid4` ID-evi = duplirani vektori.
2. `routers/law_upload.py:173` — nema provere sadržaja uopšte.
3. `routers/smart_intake.py:1401` — rupa je uzak prozor: upsert (:1401) prolazi, proces
   padne pre insert-a (:1508); `content_sha256` nikad nije zapisan; retry ne vidi duplikat
   i upsertuje **drugi komplet uuid4 ID-eva**. Prvi komplet je trajno neizbrisiv.
4. `routers/dokument.py:301` — svaki upload novi `tmp_` namespace, bez provere.
5. `drafting/playbook.py:94`, `interni_stavovi.py:89` — nema provere; ID sadrži `uuid4[:8]`.

### M. Funkcije koje koriste `uuid4` za chunk/vector ID

| FILE | LINE | FUNCTION | UPOTREBA |
|---|---|---|---|
| `uploaded_doc/chunker.py` | **157** | `chunk_document` | `chunk_id` → **direktno Pinecone `id`** (`ingest.py:110`) |
| `drafting/playbook.py` | 82 | `ingest_playbook` | `uuid4().hex[:8]` sufiks u ID-u |
| `interni_stavovi.py` | 76 | `ingest_stav` | `uuid4().hex[:8]` sufiks u ID-u |
| `routers/evidence_graph.py` | 378 | — | ID čvora grafa, **ne Pinecone vektor** |
| `uploaded_doc/session.py` | 7 | `generate_session_id` | `session_id` → ime namespace-a |
| `routers/law_upload.py` | 207 | `upload_zakon` | `doc_id` → prefiks vektora (ali **stabilan tokom ingesta**) |

---

## 2. KORAK 2 — REDOSLED OPERACIJA (kritično)

| # | PISAČ | Pinecone upsert | `predmet_dokumenti` insert | **REDOSLED** |
|---|---|---|---|---|
| 1 | `api.py::upload_predmet_dokument` | `:5205` | `:5290 / :5293 / :5299` | **POSLE** (DB red nastaje posle upsert-a) |
| 2 | `routers/smart_intake.py::finalize_intake_job` | `:1401` | `:1508` | **POSLE** |
| 3 | `routers/drafting.py::_promote_staged_draft_to_pinecone` | `:357` | `:414 / :425` | **POSLE** |
| 4 | `routers/dokument.py::dokument_upload` | `:301` | — | **NE KREIRA RED** |
| 5 | `interni_stavovi.py::ingest_stav` | `:89` | — | **NE KREIRA RED** (nijednu tabelu) |
| 6 | `drafting/playbook.py::ingest_playbook` | `:94` | — | **NE KREIRA RED** (nijednu tabelu) |
| 7 | `routers/law_upload.py::_run_ingest_sync` | `:92` | — (`law_docs`) | **PRE** — `law_docs.id` nastaje na `:207`, upsert tek u pozadinskom tasku (`:230`) |
| 8 | `routers/knowledge_base.py::_kb_embed_and_upsert` | `:105` | — (`user_knowledge`) | **PRE** — `entry_id` sa `:186`, upsert tek na `:197` |

**Odgovor na ključno pitanje:** kod sva tri pisača koji uopšte prave `predmet_dokumenti`
red (1, 2, 3), `document_id` postoji **tek POSLE** upsert-a. Bez promene redosleda
`predmet_dokumenti.id` **ne može** ući u ID vektora.

**Ali promena redosleda nije potrebna**, jer postoje dva identifikatora koja su poznata
PRE upsert-a i već su u šemi:
* `predmet_id` — poznat na ulazu u zahtev (`api.py:5205` ga već šalje u metapodacima),
* `content_sha256` — izračunat pre chunk-ovanja (`api.py:5164`, `smart_intake.py:1341`).

Pisači 7 i 8 **već rade PRE** i zato već imaju determinističke ID-eve. To nije slučajnost
nego posledica redosleda.

---

## 3. KORAK 3 — ŠEMA `predmet_dokumenti` (§16)

Dobijeno iz **žive baze** preko PostgREST OpenAPI definicije + potvrđeno po koloni sondom
`select(<kolona>).limit(0)` (nijedan red nije pročitan).

| # | KOLONA | TIP | POREKLO | POSTOJI UŽIVO |
|---|---|---|---|---|
| 1 | `id` | uuid PK | `supabase_setup.sql:356` | ✓ |
| 2 | `predmet_id` | uuid FK→`predmeti` CASCADE | `supabase_setup.sql:357` | ✓ |
| 3 | `user_id` | uuid FK→`auth.users` (RESTRICT, mig. 077) | `supabase_setup.sql:358` | ✓ |
| 4 | `naziv_fajla` | text NOT NULL | `supabase_setup.sql:359` | ✓ |
| 5 | `storage_path` | text NOT NULL | `supabase_setup.sql:360` | ✓ |
| 6 | `pinecone_namespace` | text NOT NULL | `supabase_setup.sql:361` | ✓ |
| 7 | `status` | text DEFAULT `'na_cekanju'` | `supabase_setup.sql:362` | ✓ |
| 8 | `velicina_kb` | integer | `supabase_setup.sql:363` | ✓ |
| 9 | `created_at` | timestamptz | `supabase_setup.sql:364` | ✓ |
| 10 | `tekst_sadrzaj` | text | **mig. 105** | ✓ |
| 11 | `redni_broj` | integer | **mig. 105** | ✓ |
| 12 | `tip_dokaza` | text | mig. 016 | ✓ |
| 13 | `pravni_elementi` | text[] | mig. 016 | ✓ |
| 14 | `ai_tags` | jsonb | mig. 016 | ✓ |
| 15 | `klasifikovan_at` | timestamptz | mig. 016 | ✓ |
| 16 | `source_intake_job_segment_id` | uuid FK | **mig. 094** | ✓ |
| 17 | `content_sha256` | text | **mig. 095** | ✓ |
| 18 | `source_intake_job_id` | uuid FK | **mig. 095** | ✓ |

**Ukupno 18 kolona.** Indeksi: `idx_pdok_tip`, `uq_predmet_dokumenti_source_segment`
(UNIQUE), `idx_predmet_dokumenti_content_sha256` na `(user_id, content_sha256)`,
`idx_predmet_dokumenti_source_job`, `predmet_dokumenti_predmet_redni_unique`
(UNIQUE `(predmet_id, redni_broj)`, mig. 106).

**Potvrđeno ODSUTNE** (sonda vratila `42703`): `session_id`, `updated_at`, `deleted_at`,
`version`, `verzija`, `vector_ids`, `pinecone_ids`, `chunk_count`, `doc_hash`,
`original_sha256`, `mime_type`, `storage_bucket`, `kljucne_cinjenice`.

**Migracije 094, 095, 105, 106 SU primenjene uživo** — dokazano sondom, ne pretpostavkom.

### Da li je identitet moguć BEZ nove kolone?

**DA.** Šema već ima sve što treba:
* `predmet_id` — granica vlasništva/brisanja, **poznata pre upsert-a**;
* `content_sha256` — deterministička verzija sadržaja, **poznata pre upsert-a**, indeksirana;
* `id` — kanonski PK za povratnu vezu (upisiv u metapodatke posle upsert-a ili
  `Index.update(id=..., set_metadata=...)`).

Jedina nedostajuća komponenta je **verzija chunking šeme**, koja ne pripada bazi nego kodu
(konstanta), pa nova kolona nije potrebna ni za nju.

**Uslov:** `content_sha256` mora prestati da se računa na dva različita ulaza
(bajtovi vs. tekst) — inače „verzija" nije jedna vrednost. To je izmena koda, ne šeme.

### Nefunkcionalna kolona (nalaz)

`routers/intake.py:318` pokušava insert sa `{**r, "session_id": sid}`. **Kolona
`session_id` ne postoji** (potvrđeno sondom). Svaki takav insert baca 42703 i tiho pada na
fallback `:324` bez `session_id`. Wizard-ova veza sesija→dokument je **zauvek izgubljena**,
bez ijedne greške ka korisniku.

---

## 4. KORAK 4 — MAPA ŽIVOTNOG CIKLUSA (§3)

| # | PRELAZ | IDENTIFIKATOR KOJI POVEZUJE | STATUS |
|---|---|---|---|
| 1 | upload → storage | `api.py:5100` `{user.id}/{predmet_id}/{uuid4}{suffix}`; `smart_intake.py:181` `{user_id}/{uuid4}` | **VEZA POSTOJI** (Pipeline A/C). Za `routers/dokument.py` **nema Storage upisa uopšte** → `OPEN GAP` |
| 2 | storage → DB red | `predmet_dokumenti.storage_path` | **VEZA POSTOJI** za A/C. `smart_intake.py:1428` upisuje `f"session/{session_id}"` — **labela, ne dereferencibilan put** → `OPEN GAP` |
| 3 | DB red → verzija | — | **OPEN GAP** — pojam verzije ne postoji; `content_sha256` je identitet sadržaja, ne verzija; kod 0/43 živa reda popunjen |
| 4 | verzija → chunk | — | **OPEN GAP** — `chunk_document` (`chunker.py:126`) prima samo tekst i `source_meta`; nikakav ID dokumenta/verzije ne ulazi u chunk |
| 5 | chunk → embedding | pozicija u listi (`zip`, `ingest.py:94`) | **VEZA POSTOJI**, ali samo pozicijom. Zaštićena provera dužine (`ingest.py:87-91`) |
| 6 | embedding → vektor | `chunk.chunk_id` = `uuid4()` (`ingest.py:110`) | **OPEN GAP** — ID ne nosi nijednu informaciju o dokumentu, verziji, predmetu ni redosledu |
| 7 | vektor → metadata | `predmet_id`, `session_id`, `chunk_index`, `type`, `origin` | **DELIMIČNA VEZA** — `predmet_id` postoji, **`document_id` NE POSTOJI ni u jednom pisaču** → `OPEN GAP` |
| 8 | metadata → retrieval | `kancelarija_namespace` + filter `predmet_id $in dozvoljeni` (`retrieve.py:1860-1873`, `shared/rag_acl.py`) | **VEZA POSTOJI** — autorizacija ide preko `predmet_id` metapodatka, **nikad preko ID-a vektora** |
| 9 | retrieval → dokument | — | **OPEN GAP** — iz pogotka se ne može reći iz kog `predmet_dokumenti` reda potiče; citiranje pada na `source_filename` |
| 10 | dokument → deletion | — | **OPEN GAP (najteži)** — nema endpoint-a, nema `Index.delete` po dokumentu, nema liste ID-eva. GDPR čl. 17 nad Pinecone kopijom je **neizvodljiv postojećim kodom** |
| 11 | predmet → deletion | `predmeti` CASCADE briše `predmet_dokumenti` | DB veza postoji, **Pinecone ostaje** → `OPEN GAP` |
| 12 | nalog → deletion | `routers/gdpr.py:201` | **OPEN GAP** — 0 referenci na Pinecone u celom fajlu |

### Izmereno stanje veze (živi podaci)

```
predmet_dokumenti rows                 : 43
distinct pinecone_namespace u DB       : 43
žive namespace vrednosti u Pinecone-u  : 11
DB namespace-ovi koji POSTOJE u Pinecone: 0     <-- svih 43 reda pokazuje u prazno
žive pred_* bez ijednog DB reda        : 6      <-- 30 vektora bez vlasnika
status distribucija                    : {'sacuvano': 43}   <-- nijedan 'indeksirano'
content_sha256 popunjen                : 0 od 43
```

Oblik ID-a vektora, izmereno `Index.list()`-om (samo ID-evi, bez metapodataka i bez teksta):

```
pred_*         (6 ns, dokumenti klijenata) : goli UUID4  8-4-4-4-12   <-- nedeterministički
sudska_praksa  (407.795 vektora)           : {decision_id}__chunk_{n}
zakoni_rs      ( 25.822 vektora)           : md5("v2|{zakon}|{clan}|{stav}")
web3_zdi_mca   (    479 vektora)           : mica_{tema}_chunk_{n}
carf_dac8      (     17 vektora)           : carf_section{n}_{tema}
misljenja      (     74 vektora)           : UUID4                    <-- nedeterministički
```

Oba `pred_*` skupa (u DB i uživo) su `pred_{uuid4().hex}` (32 znaka, bez crtica) — dakle
`pred_{session_id}`, **nijedan nije `pred_{predmet_id}`** (0 od 6 i 0 od 43 suffiksa se
poklapa sa `predmeti.id`).

**Posledica:** `routers/dokument.py:191-198` (`_verify_pred_namespace_ownership`) za
`ns_prefix == "pred_"` proverava `predmeti.id == session_id`. Nijedan stvarni `pred_*`
namespace tome ne odgovara, pa ta grana **uvek vraća 404**. Komentar na `:452-455`
(„body.session_id IS predmeti.id") je **činjenično netačan** u odnosu na živ podatak.
Bezbednosno je fail-closed (uža, ne šira, prava), ali funkcionalno je putanja mrtva.

**Nijedan `kancelarija_*` ni `user_*` namespace ne postoji uživo.** Šema vlasnika iz
2026-07-26 nema **nijedan** vektor u produkciji.

---

## 5. KORAK 5 — NEGATIVNA KONTROLA

**Metod 1 (grep `.upsert(`)** — dao je 7 produkcijskih upsert mesta, ali **NIJE našao
nijedan od 3 zadata živa pisača** (`api.py:5205`, `smart_intake.py:1401`,
`drafting.py:357`), jer oni ne zovu `upsert` nego `ingest_session`.

**Metod je zbog toga ispravljen** — dodat je drugi prolaz nad pozivaocima sink funkcija
(`ingest_session` / `ingest_playbook` / `ingest_stav`):

```
api.py:5048  import ingest_session      api.py:5205  poziv
routers/dokument.py:236  import         routers/dokument.py:301  poziv
routers/drafting.py:333  import         routers/drafting.py:357  poziv
routers/smart_intake.py:1264 import     routers/smart_intake.py:1401 poziv
routers/interni.py:16    import         routers/interni.py:37    poziv
routers/drafting.py:569  import         routers/drafting.py:570  poziv
```

**Dokaz da metod vidi žive tokove (≥3 zahtevana):**

1. `api.py:5205` — nađen; potvrđen živim tragom: 43 `predmet_dokumenti` reda sa
   `pinecone_namespace` prefiksom `pred_`, statusom `sacuvano`, što je tačno grana
   `api.py:5279` `"indeksirano" if _pinecone_ok else "sacuvano"`.
2. `routers/smart_intake.py:1401` — nađen; potvrđen živim tragom: `intake_jobs` ima 4 reda.
3. `routers/dokument.py:301` — nađen; potvrđen živim tragom: obrazac `tmp_{uuid4}` +
   `expires_at` i `uploaded_doc/cleanup.py` koji ga briše (0 živih `tmp_*` = cleanup radi).
4. `routers/knowledge_base.py:105` — nađen oba metoda; `user_knowledge` = 0 redova
   (funkcija nije korišćena, ali kod je živ i registrovan).
5. `routers/law_upload.py:92` — nađen oba metoda; `law_docs` = **0 redova**.

**Dva pisača koja NISU bila u zadatoj listi**, a AST prolaz ih je našao:
`routers/batch_ingest.py:63` i `routers/auto_discovery.py:212`. Oba imaju determinističke
ID-eve, pa ne menjaju zaključak — ali potvrđuju da je zadata lista bila nepotpuna.

**Priznata granica metoda:** AST prolaz prepoznaje `upsert` po imenu atributa. Upsert
sakriven iza `getattr`/dinamičkog imena ne bi bio nađen. Grep za `getattr.*upsert` u
produkcijskom kodu daje 0 pogodaka, pa je granica u ovom repou prazna — ali je granica.

---

## 6. LISTA OPEN GAP-ova

| ID | GAP | DOKAZ |
|---|---|---|
| **G-01** | ID vektora dokumenta predmeta je `uuid4()` — ne nosi dokument, verziju, predmet ni redni broj | `uploaded_doc/chunker.py:157` → `ingest.py:110`; izmereno: svi `pred_*` ID-evi su goli UUID4 |
| **G-02** | Nijedan vektor ne nosi `document_id` | popis metapodataka §1.D — nijedan od 7 pisača ne upisuje |
| **G-03** | Pojam verzije dokumenta ne postoji | 18 kolona §3; nema `version`/`supersedes`/self-FK |
| **G-04** | `content_sha256` se računa na dva različita ulaza | `api.py:5164` (bajtovi) vs `smart_intake.py:1341` (tekst) |
| **G-05** | `content_sha256` popunjen na 0 od 43 živa reda | živa sonda |
| **G-06** | **Ne postoji brisanje vektora dokumenta** | 28 delete ruta popisano, nijedna; `gdpr.py` 0 referenci na Pinecone |
| **G-07** | `predmeti` CASCADE briše DB redove, Pinecone ostaje | `supabase_setup.sql:357` + odsustvo delete koda |
| **G-08** | DOCUMENT→VECTOR veza je 100% prekinuta uživo | 43 DB namespace-a, 0 postoji u Pinecone-u; 6 živih `pred_*` bez DB reda |
| **G-09** | `_verify_pred_namespace_ownership` `pred_` grana uvek 404 | `dokument.py:191-198` vs izmereno `pred_{uuid4}` (0/6 su `predmeti.id`) |
| **G-10** | Šema vlasnika (`kancelarija_`/`user_`) nema nijedan živi vektor | `describe_index_stats()`: 11 namespace-ova, nijedan takav |
| **G-11** | Nijedan živi dokument nije `indeksirano` | 43/43 `sacuvano` |
| **G-12** | `routers/intake.py:318` piše u nepostojeću kolonu `session_id` | sonda 42703 + fallback `:324` |
| **G-13** | Delimičan batch u `ingest_session` ostavlja neizbrisive vektore | `uploaded_doc/ingest.py:115-131` (sam kod to priznaje) |
| **G-14** | `law_upload` prijavljuje `done` uz delimičan indeks | `law_upload.py:139-152` |
| **G-15** | Uzak prozor duplikata u Smart Intake retry-ju | upsert `:1401` pre insert-a `:1508`; `content_sha256` gate zavisi od insert-a |
| **G-16** | `smart_intake.py:1428` upisuje `storage_path = "session/{id}"` — nije dereferencibilan | `smart_intake.py:1428` (`api.py:5266` ima pravi put) |
| **G-17** | `misljenja` namespace (74 vektora) ima UUID4 ID-eve | `Index.list()` |
| **G-18** | `playbook_*` i `interni_stavovi_*` ID-evi sadrže `uuid4[:8]` → re-ingest duplira | `playbook.py:82`, `interni_stavovi.py:76` |

---

## 7. ANALIZA DRIFTA (izmene nastale tokom revizije)

Paralelni agent je uveo `shared/vector_identity.py` i izmenio `uploaded_doc/ingest.py`
i `routers/law_upload.py`. Ovo nije deo baseline nalaza; navodi se jer sadrži **jedan
regresioni rizik koji forenzika vidi, a implementacija možda nije**:

1. **`routers/drafting.py:344` bi pao.** Novi kod (`ingest.py`, dodato posle `:90`) diže
   `NedovoljanIdentitet` kad je `manifest.source_sha256` prazan. `_promote_staged_draft_to_pinecone`
   gradi `source_meta` sa `"source_sha256": ""` (`drafting.py:344`) — dakle **svaka
   promocija odobrenog nacrta bi od sada bacala izuzetak**. Izuzetak se hvata na
   `drafting.py:369-372` i vraća `False`, pa se ne bi videla kao greška nego kao tiho
   „promocija nije uspela". To je regresija petog pisača.
2. **Tvrdnja u docstring-u je netačna.** `shared/vector_identity.py` kaže da obrazac
   „već radi u produkciji — `routers/law_upload.py:126`". Izmereno: `law_docs` ima
   **0 redova**, a `zakoni_rs` vektori imaju md5 oblik iz `semantic_chunker.py:107`,
   ne `{safe_id}_c{n}` oblik iz `law_upload.py`. Obrazac koji **stvarno** radi u
   produkciji na 407.795 vektora je `{decision_id}__chunk_{n}`
   (`chunker_case_law.py:279` / `scripts/ingest_sudskapraksa.py:428`).
3. Scope izbor (`predmet_id` kad postoji, inače `session_id`) je konzistentan sa nalazom
   §2 — `predmet_id` je jedini identifikator poznat PRE upsert-a. To je ispravno.

---

## 8. ZAKLJUČAK ZA ODLUKU O MODELU

* **Kanonski deterministički obrazac u repou POSTOJI i ne treba ga izmišljati.**
  Dominantan, dokazan na 407.795 živih vektora: **`{stabilni_id_izvora}__chunk_{index}`**
  (`chunker_case_law.py:279`, `scripts/ingest_sudskapraksa.py:428`,
  `scripts/ingest_bilten_to_pinecone.py:203`). Varijante iste ideje:
  `{scope}_{pk}` (`knowledge_base.py:107` — **jedini koji ima i precizan delete**),
  `{safe_id}_c{n}` (`law_upload.py:137`), `md5(semantika)` (`semantic_chunker.py:107`),
  `{prefix}_{sha256(chunk)[:32]}` (`auto_discovery.py:199`).
* **Identitet je moguć BEZ ijedne nove kolone** — `predmet_id` + `content_sha256`
  (mig. 095, potvrđeno uživo) + `predmet_dokumenti.id`.
* **Redosled nije prepreka**: `predmet_id` i `content_sha256` su poznati pre upsert-a kod
  sva tri pisača koji prave DB red. `document_id` (poznat tek posle) nije neophodan u ID-u
  vektora — dovoljan je u metapodacima, gde može ući i naknadno.
* **Najteži gap nije ID nego brisanje (G-06/G-07/G-12):** čak i sa savršenim ID-em, nijedna
  ruta u repou ne briše vektor dokumenta. Identitet je preduslov, ne rešenje.

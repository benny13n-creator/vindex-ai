# PINE-01 — Životni ciklus dokumenta i brisanje

**Forenzički nalaz · §7, §8, §11, §12, §13**
Datum: 2026-08-13 · Baseline: `690981cc`
Metod: čitanje koda (fajl:linija) + izmereni izlaz (`describe_index_stats()`, `describe_index()`, read-only SELECT nad Supabase)

Nijedan produkcijski fajl nije menjan. Nijedan `upsert`/`delete`/`query` nad Pinecone-om nije izvršen — samo `list_indexes()`, `describe_index()`, `describe_index_stats()`. Nijedan upis u Supabase. Nijedan sadržaj klijentskog dokumenta nije čitan ni ispisan; iz baze su čitane samo strukturne kolone i agregati.

---

## 0. Sažetak za odlučivanje

| Pitanje | Odgovor | Dokaz |
|---|---|---|
| Postoji li **deterministička identifikacija** svih vektora jednog dokumenta? | **NE** | §8 |
| Podržava li ovaj Pinecone setup `delete(filter=...)`? | **Indeks je SERVERLESS** — brisanje po metadata filteru nije oslonac na koji se sme računati; nije mereno (zabrana pisanja) | §8.4 |
| Postoji li `@router.delete` za predmet ili dokument? | **NE, nigde** — ni backend ni frontend | §11.1 |
| Da li GDPR brisanje naloga dodiruje Pinecone? | **NE** | §11.4 |
| Postoji li mehanizam pomirenja pri delimičnom neuspehu? | **NE** — nijedan | §12 |
| Postoji li alat za orphan detekciju? | **NE** | §13.1 |
| Izmereno orphan stanje | **100 % u OBA smera**: 43/43 DB dokumenata bez vektora, 6/6 Pinecone `pred_*` namespace-ova (30 vektora) bez DB reda. Presek = **0** | §13.2 |

---

## 1. Izmereno stanje infrastrukture

`pinecone==8.1.1` (`requirements.txt:7`), potvrđeno instalirano.

```
INDEX: vindex-ai | dim: 3072 | metric: cosine
  SPEC: {'serverless': {'cloud': 'aws', 'region': 'us-east-1',
                        'read_capacity': {'mode': 'OnDemand', ...}}}
  STATUS: {'ready': True, 'state': 'Ready'}

total_vector_count: 434217 | namespace_count: 11

SCHEME                      | namespaces | vectors
sudska_praksa               |     1 | 407795
zakoni_rs                   |     1 |  25822
web3_zdi_mca                |     1 |    479
misljenja                   |     1 |     74
pred_<REDACTED>             |     6 |     30
carf_dac8                   |     1 |     17
```

Supabase (read-only, `count="exact"`):

```
predmet_dokumenti   43 reda
predmeti            19
klijenti             5
user_knowledge       0
staging_memory       0
intake_documents     1
```

Profil svih 43 `predmet_dokumenti` redova:

```
pinecone_namespace scheme : {'pred_*': 43}      distinct namespaces: 43
status                    : {'sacuvano': 43}
storage_path shape        : {'session/<uuid>': 43}
tekst_sadrzaj present     : 43/43
distinct user_id          : 1        distinct predmet_id: 17
created_at                : 2026-07-18 → 2026-07-21
```

**Ne postoji nijedan `kancelarija_*` ni `user_*` namespace** — dakle od uvođenja aktuelne šeme (2026-07-26, `fa7129ff`) nijedan trajni dokument nije stigao u Pinecone. **Ne postoji nijedan `tmp_*` namespace.**

---

## 2. §8 — IDENTIFIER FORENSICS (kapija)

### 2.1 Kako se gradi ID vektora

```
uploaded_doc/chunker.py:157   chunk_id=str(uuid.uuid4())
uploaded_doc/ingest.py:94     "id": chunk.chunk_id
```

Pinecone `id` je **goli `uuid4`** — bez prefiksa, bez ikakve strukture, bez veze sa dokumentom, predmetom ili korisnikom. Ne postoji nigde u sistemu mesto na kojem se ta lista ID-eva čuva.

Kontrast — obrazac koji **već postoji u istom repou**:

| Modul | ID šema | Brisanje |
|---|---|---|
| `routers/knowledge_base.py:106` | `f"kb_{uid}_{beleska_id}"` | `:367` `delete(ids=[...], namespace=...)` — radi |
| `routers/law_upload.py:126` | `f"{safe_id}_c{ci}"` | soft delete, namerno bez Pinecone (`:262-280`) |
| `routers/batch_ingest.py:93`, `scripts/ingest_case_law.py:77` | deterministički iz izvornog ID-a | — |

### 2.2 Odnos identifikatora — izmereno

| Identifikator | Gde nastaje | Gde se čuva | Veza ka vektoru |
|---|---|---|---|
| `document_id` (`predmet_dokumenti.id`) | Postgres, **posle** Pinecone upsert-a (`api.py:5219-5230`) | DB | **NIJE u metadata nijednog vektora** |
| `predmet_id` | DB | DB + **vector metadata** (`api.py:5155`) | granularnost = PREDMET, ne dokument |
| `user_id` / `kancelarija_id` | DB | `kancelarija_id` u metadata; `user_id` samo na `tmp_` (`owner_user_id`, `routers/dokument.py:309`) i `kb_*` | granularnost = VLASNIK |
| `session_id` (`uuid4().hex`, `uploaded_doc/session.py:8`) | RAM pri uploadu | **u metadata svakog vektora** (`ingest.py:81`); u DB **samo ako storage upis padne** | jedini per-dokument ključ — v. 2.3 |
| `chunk_id` = `vector_id` | `chunker.py:157`, `uuid4` | **nigde** | — |
| `pinecone_namespace` (kolona) | DB (`api.py:5251`) | DB | danas `kancelarija_*`/`user_*` = deljen, ne identifikuje dokument |

### 2.3 `session_id` — jedini kandidat, i on je regresirao

`session_id` je jedini identifikator koji je (a) u metadata svakog vektora dokumenta i (b) jedinstven po dokumentu. Ali njegov opstanak u bazi zavisi od grane koda:

| Putanja | `storage_path` upisan | `session_id` povratno dobavljiv? |
|---|---|---|
| `api.py:5247` Pipeline A, **storage upis USPEO** (normalan slučaj danas) | pravi storage ključ `{user_id}/{predmet_id}/{uuid}.ext` | **NE — trajno izgubljen** |
| `api.py:5247` Pipeline A, storage upis PAO | `f"session/{session_id}"` | DA |
| `routers/smart_intake.py:1423` | `f"session/{session_id}"` | DA |
| `routers/drafting.py:387` | `f"draft/{session_id}"` | DA |

Ovo je **regresija uvedena popravkom**: Program Intake Sprint 001 (`api.py:5093-5122`) je dodao stvarno čuvanje originalnog fajla i time prepisao jedino polje koje je nosilo `session_id`. Pre te izmene dokument je bio identifikovan u Pinecone-u, a original izgubljen; posle nje original je sačuvan, a identifikacija u Pinecone-u izgubljena. Nijedna verzija nije imala oboje.

Izmereno na postojećem korpusu: **43/43 reda ima `storage_path` oblika `session/<uuid>` i taj `<uuid>` je identičan sufiksu `pinecone_namespace`-a** — dakle za legacy korpus veza JESTE očuvana. Za svaki sledeći upload kroz Pipeline A neće biti.

### 2.4 Da li je brisanje po filteru uopšte moguće

Izmereno: indeks `vindex-ai` je **serverless** (`spec.serverless`, aws/us-east-1), a ne pod-based.

Šta je utvrđeno iz koda i SDK-a:

- SDK `pinecone==8.1.1` **prima** `filter=` u `Index.delete()` (`pinecone/db_data/index.py`, docstring nabraja tri međusobno isključiva režima).
- Sam OpenAPI opis operacije koju SDK poziva glasi uže: *„Delete vectors by id from a single namespace."* (`pinecone/core/openapi/db_data/api/vector_operations_api.py:71`).
- SDK **jeste** eksplicitan o serverless ograničenjima na drugim mestima (`describe_index_stats_request.py:149`: *„Serverless indexes do not support filtering `describe_index_stats` by metadata"*; `manage_indexes_api.py`: *„Serverless indexes do not support collections"*), ali za `delete(filter=...)` takvu napomenu ne nosi.

**Status: UNKNOWN — nije mereno.** Merenje bi zahtevalo stvarni `delete` poziv, što je ovoj misiji zabranjeno. Dohvaćena Pinecone dokumentacija (`docs.pinecone.io/guides/manage-data/delete-data`) na tom mestu ne navodi ograničenje po tipu indeksa, pa se ni ona ne može uzeti kao dokaz ni u jednom smeru.

**Praktična posledica je ista bez obzira na ishod:** čak i da `delete(filter=...)` radi, najuži filter koji se danas može sastaviti je `{"predmet_id": X, "type": "case_doc"}` — to briše **ceo predmet**, ne jedan dokument. Nijedan filter ne može izolovati jedan dokument, jer nijedan per-dokument identifikator nije u metadata na način koji se iz baze može rekonstruisati (2.3).

**Šta serverless sigurno podržava, i što je stvarni put napred:** `Index.list()` / `list_paginated(prefix=..., namespace=...)` (potvrđeno prisutno u SDK-u) enumerише ID-eve po **prefiksu**. Da su ID-evi oblika `{document_id}_c{chunk_index}`, `list(prefix=f"{document_id}_")` bi dao tačan, potpun skup ID-eva jednog dokumenta, a `delete(ids=[...])` bi ga obrisao — bez ikakvog oslanjanja na metadata filter i bez nove tabele. Danas je taj mehanizam beskoristan jer su ID-evi goli `uuid4`.

### 2.5 Postoji li već kolona/tabela za listu ID-eva

**NE.** Iscrpna pretraga migracija (`grep 'vector_ids|pinecone_ids|vector_id' migrations/`) daje nula pogodaka. Jedine Pinecone-vezane kolone u šemi:

- `predmet_dokumenti.pinecone_namespace` (piše se, ali je od 2026-07-26 deljena vrednost)
- `kancelarije.pinecone_namespace` (`migrations/045_firm_intelligence.sql:20`) — `firm_*` šema koja se **čita** (`api.py:3360`, `3493`) a nikad ne piše
- `staging_memory.pinecone_namespace` (`migrations/088_staging_memory.sql:45`)

Potpuna lista kolona `predmet_dokumenti` (izmereno): `id, predmet_id, user_id, naziv_fajla, storage_path, pinecone_namespace, status, velicina_kb, redni_broj, content_sha256, tekst_sadrzaj, tip_dokaza, ai_tags, pravni_elementi, klasifikovan_at, created_at, source_intake_job_id, source_intake_job_segment_id`.

### 2.6 ODGOVOR NA KAPIJU

> **NE. Ne postoji deterministički način da se identifikuju svi Pinecone vektori jednog dokumenta.**

Za dokument otpremljen danas kroz Pipeline A sa uspešnim storage upisom, najuže što se iz baze može izvesti jeste **(namespace vlasnika, `predmet_id`)** — skup koji sadrži vektore *svih* dokumenata tog predmeta i nijedan podatak koji ih razdvaja osim `source_filename`, koje nije jedinstveno i menja se pri re-uploadu.

**Posledica koja mora biti zapisana:** brisanje se **NE SME** implementirati po sličnosti, po tekstu, ni po `source_filename`-u. Svaka takva implementacija bi brisala tuđe ili susedne vektore bez traga. Preduslov za bilo kakav delete path je izmena ID šeme (`{document_id}_c{chunk_index}`), a za već postojeće vektore — `delete_all` po namespace-u ili prihvatanje da se ne mogu adresirati.

---

## 3. §7 — Pun životni ciklus

| # | KORAK | DATA | LOCATION | IDENTIFIER | OWNER | RETENTION | DELETE PATH | AUDIT |
|---|---|---|---|---|---|---|---|---|
| 1 | UPLOAD | sirov PDF/DOCX ≤10 MB | RAM (`api.py:5085`) | — | `user.id` (`api.py:5060` `.eq("user_id", …)`) | trajanje zahteva | — | — |
| 2 | STORAGE | AES-GCM šifrovan original | bucket `intake-dokumenti`, ključ `{user_id}/{predmet_id}/{uuid}.ext` (`api.py:5111-5119`) | storage ključ | `user_id` u ključu | **trajno** (`retention_service.py:14-18`, pravna odluka) | **samo** kompenzacija pri padu obrade (`api.py:5288-5303`) | `dokument_upload` (`api.py:5313-5322`) |
| 3 | OCR | plaintext u RAM-u + privremeni fajl **nešifrovan** | `tempfile.NamedTemporaryFile` (`api.py:5140`) | — | proces | trajanje zahteva | `tmp_path.unlink()` u `finally` (`api.py:5157-5160`) | `[OCR]` log, bez sadržaja |
| 4 | CHUNK | `UploadedDocChunk` | RAM (`chunker.py:151-170`) | `chunk_id=uuid4` | — | trajanje zahteva | GC | — |
| 5 | EMBEDDING | plaintext svakog chunk-a → **OpenAI** | treća strana (`ingest.py:29-36,75`) | — | deljen API ključ, bez tenant granice | po OpenAI politici — **nije verifikovano u kodu** | **nijedan iz aplikacije** | — |
| 6 | PINECONE | vektor + **plaintext chunk-a u metadata** (`ingest.py:87`) | `vindex-ai`, ns `kancelarija_{id}`/`user_{uid}` (`api.py:5154`) | **`uuid4`, nigde zapisan** | namespace | **NEOGRANIČENO** — `expires_at=""` (`ingest.py:69`), `cleanup_expired` gleda samo `tmp_*` (`cleanup.py:38-42`) | **NE POSTOJI** | `[INGEST]` log (`ingest.py:102`) |
| 7 | DB ZAPIS | metapodaci + `tekst_sadrzaj` do 100 000 znakova | `predmet_dokumenti` (`api.py:5219-5230`) | `predmet_dokumenti.id` | `user_id` | trajno | **NE POSTOJI** | `dokument_upload` |
| 8 | RETRIEVAL | pasusi u LLM kontekst | `retrieve.py:1847-1870` → `shared/rag_acl.py` | filter `{predmet_id ∈ dozvoljeni, type ∈ [case_doc, draft_final]}` | ACL po predmetu | — | — | **RAG čitanja unutar `ask_agent` nisu auditovana** |
| 9 | DELETE DOCUMENT | — | — | — | — | — | **ENDPOINT NE POSTOJI** | akcija `dokument_delete` je *rezervisana* u `shared/audit_immutable.py:72`, bez ijednog pozivaoca |
| 10 | DELETE PREDMET | — | — | — | — | — | **ENDPOINT NE POSTOJI** | akcija `predmet_delete` rezervisana (`audit_immutable.py:66`), bez pozivaoca |
| 11 | RETENTION | — | `retention_service.py:102-119` → `cleanup_expired()` | `tmp_*` prefiks | — | 90/90/180 dana za `security_events`/`user_daily_activity`/`ai_forensics` | **`tmp_*` i samo `tmp_*`** | `cron_daily` Modul 9 (`api.py:2069-2091`) |
| 12 | GDPR DELETE | — | `routers/gdpr.py:201-254` | `uid` | — | — | anonimizuje **samo** `profiles.email/full_name` + gasi `korisnik_email_notif`; **nijedan Pinecone, Storage ni dokument poziv** | `gdpr_erasure` (`gdpr.py:239-245`) |

---

## 4. §11 — Forenzika postojećih putanja brisanja

### 4.1 Iscrpan popis `@router.delete` / `@app.delete`

29 delete endpoint-a ukupno. **Nema `predmet` i nema `dokument`** — potvrđeno grep-om nad `routers/`, `api.py`, `app/`, `klijenti/`, `drafting/`, `workers/`, `integrations/`. Isto potvrđuje i sam kod: `shared/audit_immutable.py:58-72` eksplicitno beleži da su `predmet_delete` i `dokument_delete` *rezervisani* unosi bez ijednog endpoint-a.

**Frontend to potvrđuje:** `static/vindex.js` ima 20 `'DELETE'` poziva, nijedan ka predmetu ili dokumentu. Grep na `obrisiPredmet|obrisiDokument|Obriši predmet|Obriši dokument` = 0 pogodaka. **Korisnik dokument ne može obrisati nikako.**

### 4.2 Tabela: šta preživi po svakoj putanji

| Putanja | STORAGE | DATABASE | PINECONE | AUDIT/PROVENANCE | CACHE | POZADINSKI POSLOVI |
|---|---|---|---|---|---|---|
| **Dokument** — ne postoji | sve preživi | sve preživi | sve preživi | — | — | — |
| **Predmet** — ne postoji | sve preživi | sve preživi | sve preživi | — | — | — |
| **Klijent** `klijenti/router.py:524` | preživi (Trezor blobovi netaknuti) | **soft**: `status='soft_deleted'`, red ostaje šifrovan | **preživi u celosti** — klijentovo ime/JMBG su unutar `text` metadata vektora predmeta | `klijenti_audit` + `audit_immutable` `klijent_delete` (`:566-570`) | — | predmeti i dokumenti klijenta ostaju aktivni |
| **Nalog / GDPR** `routers/gdpr.py:201` | **sve preživi** | samo `profiles.email`/`full_name` → `deleted_<8hex>@deleted.vindex.rs`; `predmeti`/`klijenti`/`predmet_dokumenti` netaknuti (`tests/test_gdpr_delete.py:130` to i **tvrdi kao invariantu**) | **sve preživi, uključujući `user_id` u metadata `tmp_`/`kb_` vektora** | `gdpr_erasure` upisan preko `_spawn_bg` — nereferenciran task, gubi se pri redeploy-u (`gdpr.py:237-238`, priznato u komentaru) | — | — |
| **Beleška znanja** `routers/knowledge_base.py:352` | — | hard DELETE | **DA, briše se** — `delete(ids=[f"kb_{uid}_{entry_id}"])` (`:365-371`) | `audit_immutable` | — | fire-and-forget task; neuspeh se **ne prijavljuje korisniku** |
| **Playbook** `routers/drafting.py:569` | — | — | `delete(delete_all=True, ns=playbook_{uid})` (`drafting/playbook.py:123`) | — | — | — |
| **Interni stavovi** `routers/interni.py:51` | — | — | `delete(delete_all=True, ns=interni_stavovi_{uid})` (`interni_stavovi.py:125`) | — | — | — |
| **Zakon (admin)** `routers/law_upload.py:262` | — | soft: `status='obrisan'` | **preživi — izričito** (docstring `:271`: „NE briše iz Pinecone") | `[LAW_UPLOAD]` log | — | zakon i dalje izlazi u RAG rezultatima |
| **Dokaz** `routers/evidence.py:416` | — | soft: `deleted_at` | preživi (dokaz nema svoje vektore, ali izvorni dokument da) | — | — | — |
| **Portal upload** `routers/client_portal.py:750` | **DA, `storage.remove()`** (`:777`) | hard DELETE | n/a (nije indeksiran) | — | — | storage brisanje ide **pre** DB brisanja (`:795-801`, priznato) |
| **Retention (dnevni cron)** `retention_service.py:122` | — | `security_events`>90d, `user_daily_activity`>90d, `ai_forensics`>180d | **samo istekli `tmp_*`** (`cleanup.py:38-42,90`) | — | — | `usage_events`, `response_audit` namerno van dometa (`:64`) |
| **Član kancelarije** `routers/kancelarija.py:520` / `:591` | — | `status='REMOVED'` | **sve preživi** — dokumenti otpremljeni u `kancelarija_{id}` ostaju firmi trajno | SeatService | — | uklonjeni član gubi pristup; njegov doprinos ostaje |
| **Nepotpun intake dokument** `shared/intake_documents.py:184` | preživi | hard DELETE `extracted_entities` → `intake_review_queue` → `intake_documents` | n/a (briše se pre indeksiranja) | `[INTAKE_DOCUMENTS]` warning | — | — |
| **Bulk import rollback** `routers/intake.py:1021` | — | hard `predmeti.delete()` — **kompenzacija, ne korisnička radnja** | n/a | — | — | — |

### 4.3 Namerno vs. nenamerno

| Preživeli podatak | Namerno? | Dokaz |
|---|---|---|
| Predmeti/klijenti/dokumenti pri GDPR brisanju naloga | **NAMERNO** — pravna obaveza advokata (Zakon o advokaturi) | `retention_service.py:14-18`; `gdpr.py:250-253` to i saopštava korisniku |
| Zakoni u Pinecone-u posle soft delete-a | **NAMERNO** | docstring `law_upload.py:271` |
| Doprinos uklonjenog člana u `kancelarija_{id}` | **verovatno namerno** (firma je vlasnik znanja), ali **nigde nije zapisano niti saopšteno** | `kancelarija_utils.py:45-58`, bez ijedne napomene o brisanju |
| **Pinecone vektori pri brisanju klijenta** | **NENAMERNO** | nijedna referenca; ime i JMBG klijenta žive kao plaintext unutar `text` metadata dok su DB kolone šifrovane |
| **Pinecone vektori — nepostojanje delete path-a uopšte** | **NENAMERNO** | `audit_immutable.py:58-72` govori o „budućem delete endpoint-u" kao o nečemu što treba da postoji |
| **Original u Storage-u pri GDPR brisanju** | **NENAMERNO / nedosledno** | isti podatak: DB šifrovan, Storage šifrovan, Pinecone plaintext, brisanje nijedno |

---

## 5. §12 — Delimičan neuspeh

**Nalaz: ne postoji nijedan mehanizam pomirenja, ponavljanja ni vidljivog stanja.** Nema outbox tabele, nema reconciliation posla, nema retry reda, nema „needs_cleanup" flag-a. Ni jedan `TODO` u tom pravcu.

### 5.1 Redosled operacija (`api.py`, Pipeline A)

```
5093-5122  Storage upload (šifrovan original)   ─┐
5142-5192  Pinecone upsert                       │  kompenzacija POSTOJI samo za storage
5219-5230  predmet_dokumenti INSERT              │  (5288-5303), i to samo za blob
5244-5248  ako _dok_id is None → HTTP 500        ─┘
```

| Scenario | Šta se desi | Vidljivo? |
|---|---|---|
| Pinecone uspeo, **DB pao** | `HTTPException 500`; storage blob se briše (`api.py:5288-5303`); **Pinecone vektori ostaju zauvek** i nijedan red ih više ne referencira | Kod to priznaje u komentaru `api.py:5232-5243` („Pinecone vektor ostaje … deferred, INTAKE-001-shape"). Korisnik ne vidi ništa; nijedan alat ih ne može naći |
| **Pinecone pao** (429/quota/storage), DB uspeo | `_pinecone_ok=False`, `count=0`, `status='sacuvano'` (`api.py:5192-5200,5253`) — **dokument je sačuvan ali nevidljiv RAG-u** | Samo kao vrednost `status` kolone. **Nijedan UI element, nijedan alert, nijedan retry.** Izmereno: **43/43 dokumenata je danas u tom stanju** (§13.2) |
| Pinecone pao iz **bilo kog drugog razloga** | `HTTPException 500`, blob obrisan, DB red nikad ne nastane | korisnik vidi grešku — jedini ispravno zatvoren slučaj |
| **Storage pao**, ostalo uspelo | `logger.warning`, obrada se **nastavlja**; `storage_path` ostaje `session/<id>` labela (`api.py:5120-5122,5247`) | Nema signala korisniku da original nije sačuvan |
| Smart Intake, Pinecone pao | **non-fatal**, `pinecone_ok=False`, obrada se nastavlja (`smart_intake.py:1414-1416`) | isto — samo `status` kolona |
| Drafting promote, Pinecone pao | `return False`, DB red se **ne kreira** (`drafting.py:375-378`) | čisto — jedini put bez razilaženja |
| Brisanje beleške znanja: DB uspeo, **Pinecone pao** | `logger.warning` + Sentry, korisnik dobija `{"ok": true}` (`knowledge_base.py:373-375`) | **NE.** Vektor sa `sadrzaj[:1000]` preživi „uspešno" brisanje |

### 5.2 Zaključak

Sistem nema pojam „delimično stanje". Svaka nekonzistentnost završi ili kao ćutljivi orphan (Pinecone bez DB) ili kao ćutljivo neindeksiran dokument (DB bez Pinecone). Jedina razlika između ta dva ishoda je koja je strana pala prva — nijedna se ne prijavljuje, ne meri i ne popravlja.

---

## 6. §13 — Orphan detekcija

### 6.1 Postojeći alati

**Nijedan alat ne postoji.** Provereno je svih ~70 skripti u `scripts/` i korenske dijagnostičke skripte:

| Alat | Šta radi | Detektuje orphan? |
|---|---|---|
| `check_pinecone_ns.py` | ispisuje `describe_index_stats()` po namespace-u | **NE** — ne dodiruje bazu |
| `scripts/check_ns.py` | isto + hardkodirani očekivani brojevi za `sudska_praksa`/default | **NE** |
| `uploaded_doc/cleanup.py` | briše istekle `tmp_*` | **NE** — ne poredi sa bazom |
| `services/retention_service.py` | poziva gornje | **NE** |

Ne postoji endpoint, cron modul, admin ekran ni test koji poredi `predmet_dokumenti` sa Pinecone stanjem.

- **(a) dokument u bazi bez vektora** — nedetektabilno automatski. `status='sacuvano'` je *indicija*, ne dokaz (postavlja se samo pri 429/quota grešci; ako su vektori naknadno nestali, status ostaje `indeksirano`).
- **(b) vektor bez dokumenta u bazi** — **nedetektabilno u principu**, dok je ID `uuid4` a `document_id` van metadata. Jedina raspoloživa granularnost je namespace, a od 2026-07-26 namespace je deljen po vlasniku.

### 6.2 IZMERENO ORPHAN STANJE

Poređenje `predmet_dokumenti.pinecone_namespace` (43 reda, read-only SELECT) sa `describe_index_stats()`:

```
DB predmet_dokumenti rows:                                   43
DB distinct pinecone_namespace values:                       43
Pinecone pred_* namespaces:                                   6
Pinecone pred_* vectors:                                     30   (6 × po 5)
PRESEK (DB namespace koji postoji u Pinecone-u):              0
Orphan tip A — DB red bez ijednog vektora:                   43   (100 %)
Orphan tip B — Pinecone pred_* bez DB reda:                   6   (100 %, 30 vektora)
```

Dodatne izmerene činjenice:

```
pred_ sufiks oblik (Pinecone): uuid4hex     sufiks koji JESTE predmeti.id: 0 / 6
pred_ sufiks oblik (DB):       uuid4hex     sufiks koji JESTE predmeti.id: 0 / 43
storage_path sufiks == namespace sufiks:                     43 / 43
```

**Razilaženje je potpuno, u oba smera.** Ne postoji nijedan dokument u sistemu čiji DB red i Pinecone vektori istovremeno postoje.

Uzroci, razdvojeni:

1. **43 DB dokumenata bez vektora** — svih 43 ima `status='sacuvano'`. Verzija `api.py` koja je bila živa u periodu njihovog nastanka (2026-07-18…21, commit `ff584d23`, linije 3857-3870) postavlja `sacuvano` **isključivo** kad Pinecone baci grešku sa `429`/`storage`/`Too Many` u tekstu. Dakle: **Pinecone ingest je pao za svih 43 dokumenata (kvota/popunjen prostor), dokumenti su sačuvani, i nikad nisu indeksirani.** Sav njihov RAG sadržaj postoji samo kao `tekst_sadrzaj` u bazi. Nijedan retry nikad nije pokrenut jer retry mehanizam ne postoji (§12).

2. **6 Pinecone namespace-ova / 30 vektora bez DB reda** — poreklo **UNKNOWN**. Sufiksi su `uuid4hex` (ne `predmeti.id`), ne poklapaju se ni sa jednim `pinecone_namespace` u bazi, i svaki ima **tačno 5 vektora** — uniformnost koja upućuje na sintetički izvor pre nego na stvarne dokumente, ali to nije dokazano i **nije se smelo dokazivati** (zahtevalo bi query nad tuđim/nepoznatim sadržajem). Sadržaj se **ne sme pretpostaviti kao bezopasan.** Ovih 30 vektora je istovremeno:
   - **nedostupno** — `_verify_pred_namespace_ownership` (`routers/dokument.py:191-198`) traži `predmeti.id == session_id`; izmereno **0/6** sufiksa je `predmeti.id`, pa provera **nikad ne prolazi** (fail-closed, bezbednosno ispravno);
   - **neobrisivo** — nijedan delete path ne pokriva `pred_*` (`cleanup.py:38-42` gleda samo `tmp_*`).

3. **`kancelarija_*` / `user_*` — 0 namespace-ova, 0 vektora.** Aktuelna šema (od `fa7129ff`, 2026-07-26) nije primila nijedan vektor. Kombinovano sa nalazom (1): **trajni dokument nije uspešno indeksiran u Pinecone od kada `predmet_dokumenti` postoji.** Sav „RAG nad klijentskim dokumentima" danas radi isključivo iz `tekst_sadrzaj` kolone, ne iz Pinecone-a.

### 6.3 Kako bi detekcija izgledala da je moguća

Za orphan tip A dovoljno je poređenje koje je ovaj nalaz upravo izvršio (`pinecone_namespace` ⋈ `describe_index_stats().namespaces`) — izvodljivo **samo dok je namespace per-dokument**. Za aktuelnu deljenu šemu (`kancelarija_*`) ni to više ne važi: postojanje namespace-a ne dokazuje postojanje vektora *tog* dokumenta.

Za orphan tip B ne postoji izvodljiv postupak dok se ne promeni ID šema. Prefiks-enumeracija (`Index.list(prefix=...)`, §2.4) bi ga učinila trivijalnim.

---

## 7. Metod i granice

Izvršeno:
- `list_indexes()`, `describe_index("vindex-ai")`, `describe_index_stats()` nad produkcionim `PINECONE_HOST` — sve read-only, control-plane i statistički pozivi.
- Read-only `SELECT` nad Supabase (`predmet_dokumenti`, `predmeti`, `klijenti`, `user_knowledge`, `staging_memory`, `intake_documents`) preko service ključa. Čitane su strukturne kolone i agregati; `tekst_sadrzaj` je proveravan **samo na prisustvo** (`bool(strip())`), nikad ispisan.
- Statičko čitanje svakog `@router.delete`/`@app.delete`, svakog `index.delete(` i `.delete()` poziva u repou, `static/vindex.js` delete putanja.
- `git show`/`git log -S` nad `ff584d23`, `606f3a29`, `fa7129ff` radi utvrđivanja koja je verzija koda proizvela izmereni korpus.
- Čitanje izvornog koda `pinecone==8.1.1` SDK-a i njegovog generisanog OpenAPI sloja.

Nije izvršeno / ne tvrdi se:
- **Nijedan `upsert`, `delete` ni `query` nad Pinecone-om.** Zato `delete(filter=...)` na serverless indeksu ostaje **UNKNOWN**, ne „ne radi".
- Nijedan upis u Supabase.
- Poreklo 6 `pred_*` namespace-ova (30 vektora) nije utvrđeno — utvrđivanje bi tražilo čitanje njihove metadata.
- Pinecone vendor-side enkripcija at rest i OpenAI retention nisu verifikovani — ugovorne, ne kodne činjenice.
- Merenja su snimak stanja 2026-08-13.

Napomena o stanju radnog stabla: u trenutku ovog nalaza `api.py`, `app/services/retrieve.py` i dva test fajla imaju **neukomitovane** izmene u odnosu na baseline `690981cc` (BETA-DATA-CONFIDENTIALITY-003 / F-01: uvođenje `shared/rag_acl.py::dozvoljeni_predmeti` + `filter_za_namespace_vlasnika` u `retrieve.py:1847-1870`, sa fail-closed ponašanjem kad filter vrati `None`). Te izmene nisu delo ove misije. Sve citirane linije `api.py` u ovom nalazu su ispod tačke umetanja (`api.py:5428`) i time nepromenjene u odnosu na baseline; navod u koraku 8 tabele §7 opisuje **radno stablo**, ne baseline. Time je F-01 iz `docs/security/PINECONE_BOUNDARY_FORENSICS.md` zatvoren u radnom stablu, ali još nije u istoriji.

---

## 8. Nalazi, po težini

| ID | Nalaz | Težina |
|---|---|---|
| **PINE01-01** | Vektor ID je `uuid4` i nigde se ne čuva → **nijedan per-dokument delete nije tehnički moguć**. Preduslov za sve ostalo. | **CRITICAL** |
| **PINE01-02** | `predmet_dokumenti` nema kolonu koja povezuje red sa njegovim vektorima; `session_id` (jedini kandidat) se **od Sprint 001 više ne upisuje** za Pipeline A jer je `storage_path` prenamenjen | **CRITICAL** |
| **PINE01-03** | Ne postoji delete endpoint za dokument ni za predmet — ni backend ni frontend. „Pravo na zaborav" je nesprovodivo nad Storage-om, Pinecone-om i `predmet_dokumenti` istovremeno | **CRITICAL** |
| **PINE01-04** | `DELETE /api/gdpr/account` ne dodiruje Pinecone ni Storage; `tests/test_gdpr_delete.py:130` tu granicu **potvrđuje kao invariantu** | **HIGH** |
| **PINE01-05** | Izmereno: 43/43 dokumenata u bazi **nikad nije indeksirano** (`status='sacuvano'` = Pinecone kvota), bez ijednog signala korisniku i bez retry-ja | **HIGH** |
| **PINE01-06** | Izmereno: 30 vektora u 6 `pred_*` namespace-ova je istovremeno **nedostupno** (fail-closed ownership provera nikad ne prolazi) i **neobrisivo** (nijedan delete path ih ne pokriva) | **HIGH** |
| **PINE01-07** | Nijedan mehanizam pomirenja, ponavljanja ni vidljivog stanja pri delimičnom neuspehu | **HIGH** |
| **PINE01-08** | Nijedan alat za orphan detekciju; za tip B detekcija nije ni moguća pri sadašnjoj ID šemi | **MEDIUM** |
| **PINE01-09** | Brisanje klijenta ostavlja njegovo ime/JMBG kao plaintext u Pinecone `text` metadata, dok su iste vrednosti u bazi šifrovane | **MEDIUM** |
| **PINE01-10** | Re-upload istog dokumenta upsertuje nov skup `uuid4` vektora; stari ostaje, nevidljiv i neobrisiv (`chunker.py:157`) | **MEDIUM** |
| **PINE01-11** | `knowledge_delete` vraća `{"ok": true}` i kad Pinecone brisanje padne (fire-and-forget, `knowledge_base.py:373-375`) | **LOW** |

**Redosled koji sledi iz zavisnosti, ne iz težine:** PINE01-01 i PINE01-02 su kapija — dok se ID šema ne promeni u `{document_id}_c{chunk_index}` (obrazac koji već postoji u `knowledge_base.py:106` i `law_upload.py:126`) i dok se `document_id` ne unese u metadata, PINE01-03/04/08 **nemaju izvodljivo rešenje** osim `delete_all` po namespace-u, što danas znači brisanje cele kancelarije.

*Nijedno ovlašćenje za implementaciju nije traženo ni dato ovim nalazom.*

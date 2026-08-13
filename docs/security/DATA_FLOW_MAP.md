# DATA_FLOW_MAP.md — Mapa toka podataka i kriptografska forenzika

**Misija:** BETA-DATA-CONFIDENTIALITY-001
**Agent:** A — Data-Flow & Crypto Forensics
**Datum:** 2026-08-13
**Baseline commit:** `0df948ec`
**Metod:** čitanje izvornog koda + jedan lokalni kriptografski eksperiment (sintetički ključ).
**Nula izmena produkcijskog koda. Nula upita ka produkcionoj bazi. Nula mutacija.**

---

## 0. Pravila dokaza

- Tvrdnja bez `fajl:linija` = `UNKNOWN`. Komentar u kodu nije dokaz implementacije.
- Gde je izvor istine ručna radnja van repozitorijuma (npr. Supabase Dashboard), verdikt je
  `UNKNOWN` a ne `PASS` — bez obzira šta komentar tvrdi.
- Merenja u §2 izvedena su sintetičkim ključem (`os.urandom(32)`), ne produkcionim
  `FIELD_ENCRYPTION_KEY`. Nijedan kredencijal nije pročitan ni ispisan.

---

## 1. Život jednog dokumenta — korak po korak

U aplikaciji postoje **četiri nezavisna ulaza za dokument**, ne jedan. Prati se svaki.

### 1.A Pipeline A — `POST /api/predmeti/{predmet_id}/upload`

Kanonski put advokata. Definicija: `api.py:4978` (`predmet_upload_auto_analyze`).

| # | fajl:linija | funkcija | pozivalac | ulazni oblik | izlazni oblik | plaintext/šifrovano | persistuje | izlazi napolje |
|---|---|---|---|---|---|---|---|---|
| A1 | `api.py:4999-5005` | `_require_auth_async` + `PermissionService.require` | HTTP | `Authorization` header | `user` dict | — | ne | ne |
| A2 | `api.py:5008` | vlasništvo predmeta | endpoint | `predmet_id`,`user_id` | red iz `predmeti` | plaintext | ne | ne |
| A3 | `api.py:5023-5028` | MIME/suffix/veličina guard | endpoint | `UploadFile` | `raw: bytes` u RAM | **PLAINTEXT (RAM)** | ne | ne |
| A4 | `api.py:5045-5056` | `routers.smart_intake._encrypt` → `storage.upload` | endpoint | `raw` | AES-GCM blob u `intake-dokumenti` | **ŠIFROVANO** | **DA (trajno)** | Supabase Storage |
| A5 | `api.py:5077-5079` | `tempfile.NamedTemporaryFile(delete=False)` | endpoint | `raw` | fajl na lokalnom disku | **PLAINTEXT NA DISKU** | privremeno | ne |
| A6 | `uploaded_doc/extractor.py:178` / `:316` | `extract_pdf` / `extract_image` | `api.py:5081` | putanja temp fajla | `text: str` | **PLAINTEXT (RAM)** | ne | ne |
| A6b | `uploaded_doc/extractor.py:104-157` | `_ocr_image` (pytesseract) | `extract_pdf` | `PIL.Image` iz `io.BytesIO` | OCR tekst | **PLAINTEXT (RAM)** | ne | ne (lokalni tesseract) |
| A7 | `api.py:5096-5099` | `finally: tmp_path.unlink()` | endpoint | putanja | — | — | briše A5 | ne |
| A8 | `api.py:5140` → `uploaded_doc/chunker.py` | `chunk_document` | endpoint | `text` | `manifest.chunks` | **PLAINTEXT (RAM)** | ne | ne |
| A9 | `uploaded_doc/ingest.py:74-75` | `embeddings_client.embed_documents` | `ingest_session` | lista chunk tekstova | vektori | **PLAINTEXT** | ne | **DA — OpenAI Embeddings API** |
| A10 | `uploaded_doc/ingest.py:79-101` | `index.upsert` | `ingest_session` | chunk tekst | Pinecone vektor + `metadata["text"]` do 40.000 zn. | **PLAINTEXT** | **DA (trajno, `kancelarija_*`/`user_*` ns)** | **DA — Pinecone** |
| A11 | `api.py:5179`, `api.py:5219` | `predmet_dokumenti.insert` | endpoint | `text[:100_000]` | red u bazi | **PLAINTEXT** | **DA (trajno)** | ne |
| A12 | `api.py:5310-5329` | `emit_durable` (outbox) | endpoint | naziv fajla | event red | plaintext (samo naziv) | DA | ne |
| A13 | `api.py:5441-5448`, `:5464`, `:5505` | konstrukcija promptova | endpoint | `text[:3000]`/`[:8000]`, `[:6000]`, `[:4000]` | prompt string | **PLAINTEXT, BEZ `_skini_pii`** | ne | **DA — OpenAI gpt-4o / gpt-4o-mini** |
| A14 | `api.py:5521-5526` | 3 paralelna `chat.completions.create` | endpoint | prompt | odgovor | plaintext | ne | **DA — OpenAI** |
| A15 | `api.py:5572-5578`, `:5638-5644` | `predmet_istorija.insert` | endpoint | AI odgovor / metapodaci JSON | red u bazi | **PLAINTEXT** | **DA (trajno)** | ne |
| A16 | `api.py:5608-5617` → `:4961` | `_insert_hronologija_rows` | endpoint | GPT događaji (`dogadjaj[:500]`, `akter[:200]`) | redovi `predmet_hronologija` | **PLAINTEXT** | **DA** | ne |
| A17 | `security/ai_forensics.py:96`,`:110` | `set_prompt`/`set_response` | provenance wrapper | prompt/odgovor | **samo SHA-256** | hash | DA (`ai_forensics`) | ne |
| A18 | `api.py:5272-5279` | `audit_immutable.log_action` | endpoint | `{predmet_id, naziv_fajla}` | audit red | plaintext (naziv fajla) | DA | ne |
| A19 | `api.py:5849-5913` | `predmet_dokument_preview` | UI | `dok_id` | `{"tekst": ...}` | **PLAINTEXT ka pretraživaču** | ne | ne |

**Zaključak Pipeline A:** original je šifrovan (A4), ali **izvedeni pun tekst dokumenta postoji
nešifrovan na četiri trajna mesta**: lokalni disk (A5, privremeno), Pinecone metadata (A10),
`predmet_dokumenti.tekst_sadrzaj` (A11) i `predmet_istorija.odgovor` (A15).

### 1.B Pipeline B — `POST /api/dokument/upload`

`routers/dokument.py:219`. Ad-hoc analiza bez predmeta.

| # | fajl:linija | šta radi | plaintext/šifrovano | persistuje |
|---|---|---|---|---|
| B1 | `routers/dokument.py:247` | `raw = await file.read()` | PLAINTEXT (RAM) | ne |
| B2 | `routers/dokument.py:254-256` | temp fajl `delete=False` | **PLAINTEXT NA DISKU** | privremeno |
| B3 | `routers/dokument.py:259` | `extract()` | PLAINTEXT (RAM) | ne |
| B4 | `routers/dokument.py:300-310` | `ingest_session` → `tmp_<uuid4>` ns | **PLAINTEXT u Pinecone metadata** | **DA — 24h TTL** |
| B5 | `routers/dokument.py:342` → `:84` | `_klasifikuj_dokaz(text, filename)` | `tekst[:2000]` **PLAINTEXT, bez `_skini_pii`** | ne — **izlazi ka OpenAI** |
| B6 | `routers/dokument.py:372-376` | `finally: unlink()` | briše B2 | — |

**Original se NIKAD ne čuva** u ovom putu — nema Storage upisa. Jedini trag je Pinecone
`tmp_*` sa 24h TTL. To je dizajnerski izbor, ne propust, i on je ovde ocenjen kao PASS.

### 1.C Pipeline C — Smart Intake (`POST /api/smart-intake/documents`)

| # | fajl:linija | šta radi | plaintext/šifrovano |
|---|---|---|---|
| C1 | `routers/smart_intake.py:184-192` | `_encrypt` + upload u `intake-dokumenti` | **ŠIFROVANO** |
| C2 | `shared/intake_worker.py:472-487` | `_download_and_decrypt` | dešifruje u RAM |
| C3 | `shared/intake_worker.py:213-215` | temp fajl sa **dešifrovanim** bajtovima | **PLAINTEXT NA DISKU** |
| C4 | `shared/intake_worker.py:218-222` | `finally: unlink()` | briše C3 |
| C5 | `routers/smart_intake.py:1275-1287` | isti obrazac u `finalize` fazi | **PLAINTEXT NA DISKU**, briše se |

### 1.D Pipeline D — Klijentski portal (`routers/client_portal.py`)

| # | fajl:linija | šta radi | plaintext/šifrovano | persistuje |
|---|---|---|---|---|
| D1 | `routers/client_portal.py:563` | `sadrzaj = await fajl.read()` | PLAINTEXT | ne |
| D2 | `routers/client_portal.py:586-588` | `storage_path = "{uid}/{predmet_id}/{uuid}_{bezbedan_naziv}"` | **originalno ime fajla u putanji** | — |
| D3 | `routers/client_portal.py:591-599` | `bucket.upload(file=sadrzaj, content-type=<pravi MIME>)` | **PLAINTEXT** | **DA (trajno)** |
| D4 | `routers/client_portal.py:701-705` | `create_signed_url(_p, 3600)` | **PLAINTEXT preko bearer URL-a, 60 min** | — |

**Ovo je jedini od četiri upload puta bez ijednog kriptografskog koraka.**

---

## 2. Šifrovanje — forenzika `security/crypto.py`

### 2.1 Šta je dokazano iz koda

| Svojstvo | Vrednost | Dokaz |
|---|---|---|
| Algoritam | AES-256-GCM (AEAD) | `security/crypto.py:160-165` |
| Izvor ključa | env `FIELD_ENCRYPTION_KEY`, base64url | `security/crypto.py:123-140` |
| Izvođenje ključa (KDF) | **NEMA GA** — sirovi bajtovi, `key_bytes[:32]` | `security/crypto.py:140` |
| Dužina nonce-a | 12 bajta (96 bita) | `security/crypto.py:49`, `:163` |
| Generator nonce-a | `os.urandom(12)` (CSPRNG OS-a) | `security/crypto.py:163` |
| AAD (dodatni autentifikovani podaci) | **`None` na svih 5 mesta** | `crypto.py:165`, `:204`, `smart_intake.py:104`, `klijenti/router.py:801`, `:973` |
| Auth tag | 16 bajta, ugrađen u ciphertext | mereno, §2.3 |
| Fail-fast validacija na startu | DA, `sys.exit(1)` | `security/crypto.py:55-117`, poziv `api.py:78-80` |

### 2.2 Jedan ključ za sve

`_get_field_key()` je **jedini ključ u sistemu**. Njime se šifruje:

| Namena | Pozivalac |
|---|---|
| JMBG / broj pasoša / PIB klijenta | `klijenti/router.py:276-280`, `:493-498` |
| Naziv fajla u Trezoru | `klijenti/router.py:822` |
| Blob dokumenta klijenta (`klijent-dokumenti`) | `klijenti/router.py:798` |
| Blob intake dokumenta (`intake-dokumenti`) | `routers/smart_intake.py:101` |
| Original dokumenta predmeta (Pipeline A) | `api.py:5049` → `smart_intake._encrypt` |
| SEF API ključ integracije | `routers/sef.py:293` |

Nema razdvajanja ključeva po nameni ni po zakupcu. Kompromitacija jedne env promenljive
otključava istovremeno: sve JMBG-ove, sve blobove svih kancelarija i sve SEF integracione
ključeve.

### 2.3 EKSPERIMENT — nonce bezbednost (mereno, ne pretpostavljeno)

Skripta: `scratchpad/nonce_exp.py` (van repozitorijuma, sintetički ključ). Rezultati:

```
EKSPERIMENT 1 — kolizija nonce-a (N=100.000 x 12 bajta)
  generisano      : 100000
  jedinstvenih    : 100000
  kolizija        : 0
  teorijska P(bar 1 kolizija) = N(N-1)/2 / 2^96 = 6.311e-20

EKSPERIMENT 2 — Shannon entropija po bajt-poziciji
  bajt  0..11: H = 7.99788 .. 7.99855 bita / 8.0  (svih 256 vrednosti prisutno na svakoj poziciji)
  najniza po-bajt entropija: 7.997880 / 8.0
  bit-bias min=0.49692 max=0.50411  (idealno 0.50000)

EKSPERIMENT 3 — nezavisnost izmedju procesa (gunicorn ima vise worker-a)
  proces A nonce: CE30E04318679FFD6C68AED8
  proces B nonce: CBBAFEA40C96933B1F34913D
  IDENTICNI?     : NE — ispravno (nema deljenog PRNG stanja preko fork-a)

EKSPERIMENT 4 — verifikacija authentication tag-a
  ciphertext+tag duzina: 41 (plaintext 25 + tag 16)
  4a tamper ciphertext : InvalidTag — tag SE proverava
  4b tamper tag        : InvalidTag — tag SE proverava
  4c AAD               : encrypt(..., None) na svih 5 mesta — ciphertext NIJE
                         vezan za tabelu/kolonu/red

EKSPERIMENT 5 — NIST SP 800-38D granica za nasumican 96-bitni nonce
  q=2^20 poziva -> P(ponavljanja) = 6.939e-18
  q=2^24 poziva -> P(ponavljanja) = 1.776e-15
  q=2^32 poziva -> P(ponavljanja) = 1.164e-10
  q=2^33 poziva -> P(ponavljanja) = 4.657e-10
  NIST limit za random nonce: 2^32 poziva po kljucu
```

**Odgovor na pitanje misije: NE, ponavljanje nonce-a NIJE praktično moguće. NIJE CRITICAL.**

Obrazloženje: nonce dolazi iz `os.urandom` (CSPRNG operativnog sistema), entropija je
7,9979/8,0 bita po bajtu, nula kolizija na 100.000 uzoraka, i procesi ne dele PRNG stanje.
Ne postoji brojač, timestamp ni deterministički izvor koji bi mogao da se resetuje.
Da bi se dostigla NIST-ova granica od 2^32 poziva na jednom ključu, trebalo bi ~4,3 milijarde
operacija šifrovanja — u redu veličine daleko iznad realne upotrebe aplikacije.

**Ali:** aplikacija nema **nijedan brojač poziva po ključu** i nema **funkcionalnu rotaciju**
(§2.4), pa je ta granica nenadgledana. To je nadzorna, ne kriptografska rupa.

### 2.4 KEY_ID je dekorativan — rotacija je deklarisana, nije implementirana

Format `enc_v1:k{kid}:<data>` sugeriše podršku za rotaciju (docstring `crypto.py:29-35`).
Stvarnost: `decrypt_field` **parsira `kid` i zatim ga baca**:

```python
# security/crypto.py:190-198
if rest.startswith("k") and ":" in rest:
    kid_str, data = rest.split(":", 1)
    # kid_str = "k1", "k2", itd. — za sada koristimo isti ključ (Faza 10a)
    # Faza 10b: _get_key_by_id(int(kid_str[1:])) za multi-key support
else:
    data = rest
key = _get_field_key()   # <-- uvek isti, jedini ključ
```

Posledica: rotacija `FIELD_ENCRYPTION_KEY` **trenutno i trajno uništava čitljivost svih
postojećih podataka** — JMBG-ova, svih blobova u dva bucket-a i svih SEF ključeva. To je
scenario nepovratnog gubitka podataka, ne samo nedostajuća funkcija.

### 2.5 Neuspeh dešifrovanja se guta

```python
# security/crypto.py:205-207
except Exception as e:
    logger.error("[CRYPTO] decrypt_field greška: %s", e)
    return "[GREŠKA DEKRIPTOVANJA]"
```

`AESGCM.decrypt` **ispravno** baca `InvalidTag` na izmenjen ciphertext (dokazano, §2.3/4a-4b).
Ali `decrypt_field` pretvara integritetni neuspeh u **prikazni string**. Pozivalac ne može
razlikovati: (a) namernu izmenu podatka u bazi, (b) pogrešan ključ, (c) oštećen zapis.
Nema izuzetka, nema alarma, nema `security_events` upisa. Napad izmenom ciphertext-a je
kriptografski detektovan a operativno nevidljiv.

Blob putevi se ponašaju drugačije — tamo `InvalidTag` propagira do `except` bloka i vraća 500
(`klijenti/router.py:974-976`), što je bolje, ali i dalje bez bezbednosnog alarma.

### 2.6 Koliko dugo plaintext živi u memoriji

Python `str`/`bytes` su nepromenljivi i nema `zeroize`/`memset` nigde u repozitorijumu
(provereno: nijedan `bytearray` scrub, nijedan `ctypes.memset`). Plaintext ostaje u heap-u
do GC-a i može završiti u core dump-u ili swap-u.

| Objekat | Nastaje | Poslednja referenca | Realno trajanje |
|---|---|---|---|
| `raw` (originalni bajtovi) | `api.py:5026` | kraj funkcije `api.py:~5700` | ceo zahtev (uklj. 3 GPT poziva do 60 s) |
| `text` (izvučeni tekst) | `api.py:5081` | `api.py:5464` | ceo zahtev |
| `_tekst_preview` (100k zn.) | `api.py:5179` | `api.py:5219` | do insert-a |
| `raw_bytes` (dešifrovan blob) | `shared/intake_worker.py:210` | `:215` | kratko, ali stiže na disk (C3) |
| temp fajl na disku | `api.py:5077` / `dokument.py:254` / `intake_worker.py:213` / `smart_intake.py:1276` / `drafting.py:539` | `finally: unlink()` | trajanje `extract()` uklj. OCR (može biti desetine sekundi) |

---

## 3. Svi pisci sadržaja dokumenta

Iscrpna pretraga obrazaca: `storage.from_().upload`, `open(...,'w'/'wb')`, `tempfile.*`,
`/tmp`, `shutil.*`, `Path.write_*`, `to_csv`/`to_excel`, PDF/DOCX generatori,
`zipfile(...,'w')`, `pickle.dump`, `json.dump`.

### 3.1 Supabase Storage — 4 pisca

| Pisac | Bucket | Ključ | Šifrovano | Kompenzujuće brisanje |
|---|---|---|---|---|
| `api.py:5051` | `intake-dokumenti` | `{uid}/{predmet_id}/{uuid}{suffix}` | **DA** | DA — `api.py:5254` |
| `routers/smart_intake.py:186` | `intake-dokumenti` | `{uid}/{uuid4hex}` | **DA** | DA — `smart_intake.py:217` |
| `klijenti/router.py:811` | `klijent-dokumenti` | `encrypted_blob_<uuid4>` | **DA** | DA — `klijenti/router.py:841` |
| **`routers/client_portal.py:594`** | **`portal-uploads`** | **`{uid}/{predmet_id}/{uuid}_{ime_fajla}`** | **NE** | DA — `:635`, `:779` |

### 3.2 Privremeni fajlovi — 5 pisaca, svi plaintext

| Lokacija | Šta upisuje | `delete=` | Brisanje | Bezbedno brisanje |
|---|---|---|---|---|
| `api.py:5077-5079` | originalni upload | `False` | `finally` `:5096-5099` | NE (`unlink`, bez prepisivanja) |
| `routers/dokument.py:254-256` | sesijski upload | `False` | `finally` `:372-376` | NE |
| `shared/intake_worker.py:213-215` | **dešifrovan** blob | `False` | `finally` `:218-222` | NE |
| `routers/smart_intake.py:1276-1279` | **dešifrovan** blob | `False` | `finally` `:1283-1287` | NE |
| `routers/drafting.py:539-541` | playbook kancelarije | `False` | `finally` `:562-568` | NE |

Svih pet ima `except Exception: pass` oko `unlink()`. Neuspelo brisanje ostavlja plaintext
dokument na disku **bez ikakvog traga u logu**. Ako proces bude ubijen (OOM, SIGKILL,
gunicorn `timeout = 120`) između upisa i `finally`, fajl trajno ostaje.

### 3.3 Odsutni obrasci (PASS)

- `shutil.copy/move/make_archive` u produkcijskom kodu — **nema nijednog**.
- `pickle.dump` — **nema nijednog u celom repozitorijumu**.
- `to_csv` / `to_excel` / `ExcelWriter` / `xlsxwriter` — **nema nijednog**.
- `get_public_url` — **nema nijednog**.
- PDF/DOCX/ZIP generatori (`dossier_pdf.py:100`, `predmet_pdf.py:131`, `docx_export.py:91`,
  `routers/data_export.py:99`, `routers/drafting.py:1160`, `routers/billing.py:1127`,
  `klijenti/router.py:1023`) — **svi u `io.BytesIO`, nijedan ne dodiruje disk**.
- CSV/XLSX uvoz (`routers/import_klijenti.py:75,86`, `routers/csv_import.py:209`) —
  `io.StringIO`/`io.BytesIO`, samo čitanje.

### 3.4 Ostali pisci na disk

| Lokacija | Šta | Ocena |
|---|---|---|
| `security/chain_anchor.py:170-172` | `open(os.getenv("ANCHOR_FILE_PATH","/tmp/vindex_anchors.jsonl"),"a")` | Merkle/hash sidra audit lanca. **Nije sadržaj dokumenta.** Append-only, nikad se ne briše. Podrazumevani backend je `supabase_secondary`, ovo je dev fallback. |
| `uploaded_doc/__main__.py:51-53` | `manifests/{stem}-manifest.json` sa `manifest.model_dump_json()` | Chunk zapisi + `source_filename` + sha256. **PLAINTEXT, trajno, nikad se ne briše.** Dostupno samo preko CLI `python -m uploaded_doc`, ne preko servera. |
| `scripts/genome_bootstrap_sample.py:97-108` | `tekst_sadrzaj_excerpt[:6000]` u lokalni JSON | **Plaintext isečci stvarnih korisničkih dokumenata na disk.** Ručno pokretana skripta, nije serverski put. |

---

## 4. Baza — kolone koje nose poverljiv sadržaj

| Tabela | Kolona | Šta nosi | Stanje | Upis | Retencija | Put brisanja |
|---|---|---|---|---|---|---|
| `predmet_dokumenti` | `tekst_sadrzaj` | **pun izvučeni tekst, do 100.000 zn., uklj. OCR izlaz** | **PLAINTEXT** | `api.py:5219`, `routers/drafting.py:388`, `routers/smart_intake.py:1485` | **NEMA** | samo `ON DELETE CASCADE` sa `predmeti` — **`user_id` FK je `RESTRICT`** (migr. `077:149`), pa brisanje `auth.users` reda NE briše dokumente |
| `predmet_dokumenti` | `naziv_fajla` | originalno ime fajla | PLAINTEXT | `api.py:5196` | NEMA | cascade |
| `predmet_dokumenti` | `storage_path` | putanja ka blobu | PLAINTEXT | `api.py:5203` | NEMA | cascade |
| `predmet_dokumenti` | `content_sha256` | hash sadržaja | hash | `api.py:5215` | NEMA | cascade |
| `predmet_istorija` | `odgovor` | **pun AI odgovor o dokumentu** | **PLAINTEXT** | `api.py:5572-5578`, `:4895-4901` | **NEMA** | cascade |
| `predmet_istorija` | `pitanje` | činjenice slučaja `[:500]` | **PLAINTEXT** | `api.py:4898` | NEMA | cascade |
| `predmet_hronologija` | `dogadjaj`,`akter`,`dokument_naziv` | izvedeni događaji iz dokumenta | **PLAINTEXT** | `api.py:5608-5617` | NEMA | cascade |
| `predmet_beleske` | `sadrzaj` | beleške advokata | **PLAINTEXT** | čita se `api.py:5453` | NEMA | cascade |
| `client_portal_uploads` | `fajl_naziv`,`napomena`,`storage_path` | ime fajla + poruka klijenta | **PLAINTEXT** | `routers/client_portal.py:610-620` | NEMA | `:779` |
| `klijent_dokumenti` | `naziv_fajla_encrypted` | ime fajla | **ŠIFROVANO** | `klijenti/router.py:822` | NEMA | soft-delete `deleted_at` |
| `klijenti` | `jmbg_encrypted`,`broj_pasosa_encrypted`,`pib_encrypted` | lični identifikatori | **ŠIFROVANO** | `klijenti/router.py:276-280`, `:493-498` | NEMA | soft-delete |
| `klijenti` | `adresa`, `telefon`, `email`, `ime`, `prezime` | **PII** | **PLAINTEXT** | `klijenti/router.py:265-268` | NEMA | soft-delete |
| `ai_forensics` | `prompt_hash`,`response_hash`,`document_hashes`,`system_prompt_hash`,`user_prompt_hash` | **samo SHA-256** | hash | `security/ai_forensics.py:96`,`:110`,`:103` | **180 dana** (`services/retention_service.py:58`) | retention |
| `ai_forensics` | `error_message` | `str(error)[:500]` iz SDK-a | **PLAINTEXT** | `shared/ai_client.py:462` | 180 dana | retention |
| `ai_forensics` | `retrieval_query` | sirov tekst upita — **kolona i plumbing postoje, nijedan pozivalac je ne puni danas** | **latentno** | migr. `089:43`; `shared/ai_provenance.py:103` | 180 dana | retention |
| `ai_forensics` | `knowledge_sources` | **imena fajlova** | PLAINTEXT | `routers/copilot.py:475` | 180 dana | retention |
| `audit_immutable` | `metadata` (JSON) | `{predmet_id, naziv_fajla}` | PLAINTEXT (ime fajla) | `shared/audit_immutable.py:362`,`:388` | **NEMA — trigger blokira DELETE i UPDATE** (migr. `043:49-52`) | **nema** |
| `klijenti_audit` | `user_email`, `ip_adresa` | **plaintext email + plaintext IP** | **PLAINTEXT** | `klijenti/audit.py:56`,`:61` | **NEMA — append-only trigger** (migr. `002:119-127`) | **nema** |
| `ai_corrections` | `original_output`, `edited_output` | **pun AI tekst i advokatova ispravka, po 8.000 zn.** | **PLAINTEXT** | `routers/corrections.py:293-294` | NEMA | nema |
| `staging_memory` | `tekst` | **pun AI nacrt podneska** | **PLAINTEXT** | `routers/drafting.py:295` | NEMA | nema |
| `extracted_entities` | `value`, `corrected_value` | **imena tužioca/tuženog/sudije, broj predmeta, iznosi — izvučeni iz dokumenta** | **PLAINTEXT** | `shared/intake_documents.py:70`,`:308` | NEMA | `shared/intake_documents.py:193` |
| `notification_log` | `message_text` | pun tekst poslate SMS/Viber/WhatsApp poruke | **PLAINTEXT** | `shared/notify_quiet.py:75-77` | NEMA | nema |
| `api_kljucevi` | `kljuc` | **API ključ korisnika** | **PLAINTEXT** | `routers/export.py:68-70` | NEMA | `routers/export.py:125` |
| `predmet_dokazi` | `tvrdnja` | činjenica/dokaz izvučen iz dokumenta | **PLAINTEXT** | `routers/evidence.py:299`,`:315`,`:411` | NEMA | nema |
| `uploaded_documents` | `extracted_text` | ekstrahovani tekst (orphan tabela, bez pisaca) | — | migr. `057:166` | NEMA | nema |
| `feature_usage_log` | `feature_key`,`user_id`,`predmet_id`,`correlation_id` | **bez sadržaja** | — | migr. `065:175`, `112:51-52` | NEMA | nema |
| `security_events` | — | bezbednosni događaji | — | — | 90 dana (`retention_service.py:56`) | retention |
| `user_daily_activity` | — | agregat aktivnosti | — | — | 90 dana (`retention_service.py:57`) | retention |
| `intake_jobs` | `original_filename`,`storage_path`,`idempotency_key` | ime fajla + `uid:sha256` | PLAINTEXT | `routers/smart_intake.py` | NEMA | nema |

**Kolone koje nose poverljiv tekst dokumenta nešifrovano:** `predmet_dokumenti.tekst_sadrzaj`,
`predmet_istorija.odgovor`, `predmet_istorija.pitanje`, `predmet_hronologija.dogadjaj/akter`,
`predmet_beleske.sadrzaj`, `client_portal_uploads.napomena`.

**Napomena o `tekst_sadrzaj` (`migrations/105`):** kolona je godinama postojala samo u živoj
bazi, van sistema migracija — migracija 105 je retroaktivno beleži. Njena istorija znači da
nijedna ranija bezbednosna analiza šeme nije mogla da je vidi iz repozitorijuma.

### 4.1 Retencija i brisanje

`services/retention_service.py::execute_retention_cleanup` pokriva **tačno četiri stvari**:
`security_events` (90 d, `:88-89`), `user_daily_activity` (90 d, `:92-94`),
`ai_forensics` (180 d, `:97-99`), Pinecone `tmp_*` (`:102-118`).

**Ne pokriva:** `predmet_dokumenti.tekst_sadrzaj`, `predmet_istorija`, `predmet_hronologija`,
nijedan Storage bucket, i trajne Pinecone namespace-ove (`kancelarija_*`/`user_*`).

Za sadržaj dokumenata **ne postoji nijedna retenciona politika**.

### 4.2 GDPR brisanje naloga je samo anonimizacija profila

`routers/gdpr.py:219-228` menja **isključivo** `profiles.email`/`full_name` i gasi email
notifikacije. Odgovor to i priznaje (`:250-253`, poziv na Zakon o advokaturi).

Ne dodiruje: `predmet_dokumenti.tekst_sadrzaj`, blobove u tri bucket-a, Pinecone vektore
(trajni `kancelarija_*`/`user_*` ns), `predmet_istorija`, `klijenti`.
Za advokatsku kancelariju zakonska obaveza čuvanja spisa jeste legitiman osnov —
ali **nema mehanizma da se pravo na zaborav izvrši ni kad taj osnov ne postoji**.

---

## 5. Privremeni fajlovi i keš

| Artefakt | Lokacija | Zadržavanje | Šifrovanje | Brisanje |
|---|---|---|---|---|
| Temp upload fajlovi (5 mesta, §3.2) | OS temp dir | trajanje `extract()` | **NE** | `finally: unlink()`, guta greške |
| OCR međurezultati | RAM (`io.BytesIO`, `extractor.py:234`) | do GC | NE | GC |
| Keširan OCR | **ne postoji** | — | — | — |
| Keširani AI odgovori | **ne postoji keš na disku** — `predmet_istorija` je trajan zapis, ne keš | trajno | **NE** | nema |
| Generisani PDF/DOCX/ZIP | RAM (`io.BytesIO`) | do GC | NE | GC — **nikad ne dodiruju disk** |
| Preview fajlovi | **ne postoje** — `/preview` čita iz baze (`api.py:5895`) | — | — | — |
| `/tmp/vindex_anchors.jsonl` | disk | trajno (append-only) | NE | **nikad** — ali sadrži hash sidra, ne sadržaj |
| `manifests/*-manifest.json` | repo dir | trajno | NE | **nikad** — samo CLI put |
| Pinecone `tmp_*` | Pinecone | 24 h TTL | **NE (plaintext metadata)** | `cleanup_expired` |
| Pinecone `kancelarija_*`/`user_*` | Pinecone | **trajno** | **NE (plaintext metadata)** | **nikad** |

---

## 6. Registar nalaza

Format: `IZVOR | TIP PODATKA | ULAZ | IZLAZ | KONTROLA | MOGUĆ BYPASS | DOKAZ | VERDIKT`

---

**DFM-001 — Klijentski portal čuva original nešifrovan**
`IZVOR` `routers/client_portal.py:591-599`
`TIP PODATKA` Pun originalni dokument klijenta (PDF/DOCX/JPG/PNG/TXT)
`ULAZ` `sadrzaj = await fajl.read()` (`:563`) — sirovi bajtovi
`IZLAZ` `bucket.upload(path=storage_path, file=sadrzaj, file_options={"content-type": <pravi MIME>})` u `portal-uploads`
`KONTROLA` Magic-bytes validacija (`:573-583`), token-hash autorizacija, RLS na `client_portal_uploads` (migr. `013:29-35`)
`MOGUĆ BYPASS` Blob je čitljiv svakome ko ima pristup Storage sloju: kompromitovan `SUPABASE_SERVICE_ROLE_KEY`, greška u politici bucket-a, backup snapshot, insajder sa Dashboard pristupom. RLS štiti *tabelu metapodataka*, ne *objekat u bucket-u*. Dodatno: putanja sadrži originalno ime fajla (`:588`), pa i sam listing bucket-a odaje sadržaj (`Tuzba_Petrovic_protiv_Beograd.pdf`).
`DOKAZ` Sopstveno čitanje, ne fork-ov izveštaj. Nema `_encrypt`, `encrypt_field` ni `AESGCM` nigde u `routers/client_portal.py` (grep `_get_field_key|AESGCM|_encrypt` → 0 pogodaka u fajlu). Suprotno: sva ostala tri upload puta (`api.py:5049`, `smart_intake.py:184`, `klijenti/router.py:798`) šifruju. `security/crypto.py:10` deklariše kao HARD RULE: „Storage putanje → `generate_storage_key()` — randomizovani UUID, nikad ime fajla"; `smart_intake.py:97` tvrdi „nikad plaintext u bucket-u".
`VERDIKT` **FAIL — CRITICAL.** Najozbiljniji nalaz misije. Jedini put koji krši dva eksplicitno zapisana pravila projekta.

---

**DFM-002 — 60-minutni signed URL ka nešifrovanom blobu**
`IZVOR` `routers/client_portal.py:701-705`
`TIP PODATKA` Pun originalni dokument klijenta
`ULAZ` `storage_path` iz `client_portal_uploads`
`IZLAZ` `create_signed_url(_p, 3600)` → URL u JSON odgovoru ka pretraživaču advokata
`KONTROLA` Vlasništvo predmeta provereno pre generisanja (`:670-678`); URL ističe posle 60 min
`MOGUĆ BYPASS` Signed URL je **bearer kredencijal bez autentifikacije** — ko god ga ima, dobija dokument. Generiše se za **svih do 50 uploada odjednom** (`:687`) pri svakom otvaranju liste, čak i za one koje advokat nikad ne otvori. URL završava u istoriji pretraživača, `Referer` zaglavljima, deljenim snimcima ekrana, korporativnim proxy logovima. Pošto je blob plaintext (DFM-001), URL daje **dešifrovan** dokument — kod šifrovanih bucket-a ista greška bi odala samo neupotrebljiv ciphertext.
`DOKAZ` `create_signed_url(_p, 3600)` je jedini poziv te vrste u repozitorijumu (grep → 1 pogodak).
`VERDIKT` **FAIL — HIGH.** Uvećava DFM-001; sam po sebi bi bio MEDIUM.

---

**DFM-003 — `portal-uploads` privatnost bucket-a nije dokaziva iz koda**
`IZVOR` `migrations/013_client_portal_uploads.sql:5`
`TIP PODATKA` Konfiguracija bucket-a
`ULAZ` — `IZLAZ` —
`KONTROLA` Komentar: „Dashboard → Storage → New bucket → Ime: `portal-uploads` → Private"
`MOGUĆ BYPASS` Ako je bucket ikad kreiran ili izmenjen kao public, svi klijentski dokumenti su javno čitljivi bez ikakvog kredencijala. Nema testa, nema startup provere, nema migracije koja to obezbeđuje.
`DOKAZ` Poređenje: `migrations/073_intake_foundations.sql:362-363` **jeste** `INSERT INTO storage.buckets (id, name, public) VALUES ('intake-dokumenti','intake-dokumenti', false)`. Za `portal-uploads` i `klijent-dokumenti` **ne postoji nijedan takav upis** (grep `storage.buckets` → 1 pogodak u celom repozitorijumu).
`VERDIKT` **UNKNOWN — potencijalno CRITICAL.** Ne mogu da tvrdim ni da jeste ni da nije privatan. Zahteva ručnu proveru u Supabase Dashboard-u; do tada se mora tretirati kao neverifikovana kontrola.

---

**DFM-004 — Nonce AES-GCM: kolizija nije praktično moguća**
`IZVOR` `security/crypto.py:163`, `:103`; `routers/smart_intake.py:102`; `klijenti/router.py:799`
`TIP PODATKA` Kriptografski nonce
`ULAZ` — `IZLAZ` 12 bajta iz `os.urandom`
`KONTROLA` CSPRNG operativnog sistema, 96 bita
`MOGUĆ BYPASS` Teorijski birthday bound na 2^32 poziva po ključu (NIST SP 800-38D). Nema brojača poziva, pa se ta granica ne nadzire. Nema determinističkog/brojačkog izvora koji bi se mogao resetovati.
`DOKAZ` Mereno, §2.3: 0/100.000 kolizija, entropija 7,99788/8,0 po bajtu, bit-bias 0,49692–0,50411, nezavisni procesi daju različite nizove.
`VERDIKT` **PASS.** Eksplicitno: **NIJE CRITICAL.** Preporuka je nadzorna (brojač poziva), ne popravka.

---

**DFM-005 — AAD se ne koristi: ciphertext nije vezan za kontekst**
`IZVOR` `security/crypto.py:165`, `:204`; `routers/smart_intake.py:104`; `klijenti/router.py:801`, `:973`; `shared/intake_worker.py:487`
`TIP PODATKA` Svi šifrovani podaci (JMBG, PIB, pasoš, blobovi, SEF ključevi)
`ULAZ` plaintext `IZLAZ` `aesgcm.encrypt(nonce, data, None)` — treći argument je AAD
`KONTROLA` Auth tag štiti **integritet bajtova**, ali ne i **identitet zapisa**
`MOGUĆ BYPASS` Napadač sa pravom upisa u bazu (kompromitovan service-role ključ, SQL injection u budućnosti, insajder) može **premestiti ceo ciphertext** iz jednog reda u drugi. Šifrovani JMBG klijenta A upisan u `klijenti.jmbg_encrypted` klijenta B **dešifruje se čisto**, tag prolazi, `[GREŠKA DEKRIPTOVANJA]` se ne javlja. Isto važi za blob: `storage_path` jedne kancelarije zamenjen putanjom druge, blob se dešifruje jer je ključ jedan (DFM-006). Nema kriptografske veze ka `user_id`/`klijent_id`/nazivu kolone.
`DOKAZ` Eksperiment 4c, §2.3. Grep `encrypt(` po svim 5 mesta → treći argument je `None` na svakom.
`VERDIKT` **FAIL — MEDIUM.** Nije curenje poverljivosti samo po sebi; jeste rupa u integritetu i preduslov za tihu zamenu podataka između zakupaca.

---

**DFM-006 — Jedan ključ za svih šest namena, bez KDF-a**
`IZVOR` `security/crypto.py:122-140`
`TIP PODATKA` Glavni ključ
`ULAZ` `FIELD_ENCRYPTION_KEY` (base64url) `IZLAZ` `key_bytes[:32]` — **sirovo, bez HKDF/PBKDF2**
`KONTROLA` Fail-fast validacija na startu (`:55-117`, poziv `api.py:78-80`); min 32 bajta
`MOGUĆ BYPASS` Kompromitacija jedne env promenljive otključava istovremeno: sve JMBG-ove/pasoše/PIB-ove svih klijenata svih kancelarija, sve blobove u `klijent-dokumenti` i `intake-dokumenti`, i sve SEF integracione ključeve (`routers/sef.py:293`). Nema izvođenja po nameni (`HKDF(info=b"blob")` vs `info=b"pii"`), nema izolacije po zakupcu. U kombinaciji sa DFM-005 (bez AAD) ne postoji nijedna prepreka premeštanju ciphertext-a između domena.
`DOKAZ` Šest pozivalaca `_get_field_key()`/`encrypt_field()`, popisani u §2.2, svi bez ikakve derivacije.
`VERDIKT` **FAIL — MEDIUM.** Arhitektonski, ne implementacioni propust.

---

**DFM-007 — Rotacija ključa je deklarisana ali neimplementirana**
`IZVOR` `security/crypto.py:190-198` vs docstring `:29-35`
`TIP PODATKA` Metapodatak formata (`kid`)
`ULAZ` `enc_v1:k{kid}:<data>` `IZLAZ` `kid` se parsira i **odbacuje**; uvek `_get_field_key()`
`KONTROLA` Nijedna
`MOGUĆ BYPASS` Nije napadački vektor nego operativna zamka: **rotacija `FIELD_ENCRYPTION_KEY` trajno uništava čitljivost svih postojećih šifrovanih podataka.** Pošto `decrypt_field` guta grešku (DFM-008), gubitak se manifestuje kao `[GREŠKA DEKRIPTOVANJA]` u UI-ju, ne kao pad — potencijalno neprimećen danima. Ovo direktno blokira reagovanje na iscureli ključ.
`DOKAZ` Komentar u samom kodu: „za sada koristimo isti ključ (Faza 10a)"; `_get_key_by_id` **ne postoji** u repozitorijumu (grep → 0 pogodaka izvan tog komentara).
`VERDIKT` **FAIL — MEDIUM.** `KEY_ROTATION_ANALYSIS.md` opisuje sposobnost koju kod nema.

---

**DFM-008 — Neuspeh provere integriteta se pretvara u prikazni string**
`IZVOR` `security/crypto.py:205-207`
`TIP PODATKA` Signal integriteta
`ULAZ` izmenjen/oštećen ciphertext `IZLAZ` `"[GREŠKA DEKRIPTOVANJA]"` + `logger.error`
`KONTROLA` `AESGCM.decrypt` **ispravno** baca `InvalidTag` (dokazano, §2.3/4a-4b) — tag SE proverava
`MOGUĆ BYPASS` Namerna izmena podatka u bazi je kriptografski otkrivena a operativno nevidljiva: bez izuzetka, bez `security_events` upisa, bez alarma. Pozivalac ne razlikuje napad od pogrešnog ključa. Sentinel string može završiti u AI promptu ili PDF izveštaju kao da je legitimna vrednost.
`DOKAZ` Eksperiment 4a/4b potvrđuje da tag radi; `security/crypto.py:205-207` potvrđuje da se rezultat guta.
`VERDIKT` **FAIL — MEDIUM.** Kriptografija je ispravna, obrada greške nije.

---

**DFM-009 — Pun tekst dokumenta nešifrovan u bazi, bez retencije**
`IZVOR` `api.py:5179` + `api.py:5219`; `routers/drafting.py:388`
`TIP PODATKA` Kompletan izvučeni tekst pravnog dokumenta, do 100.000 znakova
`ULAZ` `_tekst_preview = text[:100_000]` `IZLAZ` `predmet_dokumenti.tekst_sadrzaj` (TEXT)
`KONTROLA` RLS `auth.uid() = user_id` (`supabase_setup.sql:372`); `.eq("user_id", uid)` u svim čitanjima
`MOGUĆ BYPASS` RLS se zaobilazi service-role ključem — koji ova aplikacija koristi za sve upite. Zaštita je time aplikativna, ne bazna. Original je šifrovan (`api.py:5049`), ali njegov **pun tekstualni sadržaj stoji odmah pored, u čistom obliku** — šifrovanje originala ne štiti ništa dok tekst postoji nešifrovan u istoj bazi. Bez retencije, bez brisanja.
`DOKAZ` Čita se na 10+ mesta: `api.py:5863`, `routers/case_dna.py:812`,`:1014`,`:1244`, `routers/evidence.py:459`, `routers/multi_agent.py:444`, `routers/search.py:96`, `routers/case_commander.py:149`, `routers/evidence_graph.py:210`. `services/retention_service.py` je ne pominje.
`VERDIKT` **FAIL — HIGH.** Najveća koncentracija poverljivog teksta u sistemu.

---

**DFM-010 — Pun tekst dokumenta nešifrovan u Pinecone-u, trajno**
`IZVOR` `uploaded_doc/ingest.py:79-101`
`TIP PODATKA` Chunk-ovi teksta dokumenta, do 40.000 znakova po vektoru (`_TEXT_TRUNCATE`, `:12`)
`ULAZ` `text_stored = chunk.text[:_TEXT_TRUNCATE]` `IZLAZ` `metadata["text"]` u Pinecone
`KONTROLA` Izolacija po namespace-u; `owner_user_id` metadata za `tmp_` (`routers/dokument.py:309`)
`MOGUĆ BYPASS` Pinecone je **treća strana van EU/Srbije** i podaci su tamo u čistom obliku. Trajni `kancelarija_*`/`user_*` namespace-ovi (`api.py:5154`) **nemaju TTL ni put brisanja** — `cleanup_expired` po svojoj definiciji briše isključivo `tmp_*` (`uploaded_doc/cleanup.py:38-42`), što `api.py:5147-5148` i sam priznaje. Namespace-ovi su deljeni po kancelariji: izolacija između predmeta oslanja se na metadata filter u upitu, ne na fizičku pregradu.
`DOKAZ` `uploaded_doc/ingest.py:87` (`"text": text_stored`), `uploaded_doc/cleanup.py:38-42`, `services/retention_service.py:102-118`.
`VERDIKT` **FAIL — HIGH.** Poverljivi tekst kod treće strane, nešifrovan, bez roka i bez puta brisanja.

---

**DFM-011 — Pipeline A šalje dokument OpenAI-u bez PII maskiranja**
`IZVOR` `api.py:5441-5448`, `:5464`, `:5505`, `:5521-5526`; `routers/dokument.py:102`
`TIP PODATKA` Tekst dokumenta: `[:3000]`/`[:8000]` (procena), `[:6000]` (hronologija), `[:4000]` (metapodaci), `[:2000]` (klasifikacija)
`ULAZ` sirovi `text` `IZLAZ` `chat.completions.create` ka OpenAI
`KONTROLA` **Nijedna na ovom putu.** `_skini_pii` **nije pozvan.**
`MOGUĆ BYPASS` Nije bypass — funkcija se prosto ne poziva. Aplikacija deklariše pseudonimizaciju kao GDPR/ZZPL tehničku meru (`main.py:1078-1079`) i primenjuje je na `/api/dokument/analiza` (`main.py:4145-4146`), `/api/pitanje` (`main.py:3221`) i drafting (`routers/drafting.py:654`,`:779`,`:864`) — ali **ne** na primarni upload put kojim advokat zaista radi. JMBG, brojevi računa i brojevi sudskih predmeta odlaze nemaskirani.
`DOKAZ` Grep `_skini_pii` → 18 pozivnih mesta, **nijedno u `predmet_upload_auto_analyze` (`api.py:4978-5700`)** i **nijedno u `_klasifikuj_dokaz` (`routers/dokument.py:84-118`)**.
`VERDIKT` **FAIL — MEDIUM.** Nedosledna primena deklarisane kontrole na najprometnijem putu.

---

**DFM-011b — I gde se primenjuje, `_skini_pii` maskira samo identifikatore**
`IZVOR` `main.py:1048-1069`
`TIP PODATKA` Obrasci PII-ja
`ULAZ` tekst `IZLAZ` tekst sa maskiranim JMBG/PIB/MB/LK/pasoš/telefon/IBAN/račun/broj predmeta
`KONTROLA` 12 regex obrazaca
`MOGUĆ BYPASS` **Imena stranaka, adrese, nazivi firmi i cela činjenična naracija se NE maskiraju.** Za pravni dokument to je najveći deo poverljivosti. Tvrdnja „pseudonimizacija kao tehnička mera zaštite" (`main.py:1079`) je time delimično tačna.
`DOKAZ` `_PII_ZAMENE` sadrži isključivo numeričke/formatske obrasce (`main.py:1048-1069`); nema NER-a ni liste imena.
`VERDIKT` **FAIL — LOW.** Kontrola postoji i radi ono što radi; javna tvrdnja je šira od implementacije.

---

**DFM-012 — Plaintext temp fajlovi sa best-effort brisanjem**
`IZVOR` `api.py:5077-5079`; `routers/dokument.py:254-256`; `shared/intake_worker.py:213-215`; `routers/smart_intake.py:1276-1279`; `routers/drafting.py:539-541`
`TIP PODATKA` Kompletan originalni dokument u bajtovima
`ULAZ` `raw` / **dešifrovan** `raw_bytes` `IZLAZ` fajl u OS temp direktorijumu, `delete=False`
`KONTROLA` `finally: tmp_path.unlink()` na svih pet mesta
`MOGUĆ BYPASS` (1) `except Exception: pass` oko `unlink()` — neuspelo brisanje ne ostavlja **nikakav trag u logu**. (2) `SIGKILL`/OOM/gunicorn `timeout = 120` (`gunicorn.conf.py`) između upisa i `finally` ostavlja fajl trajno. (3) `unlink()` samo odvezuje inode — sadržaj ostaje na disku do prepisivanja; nema `shred`/`zeroize`. (4) Za `intake_worker.py:213` i `smart_intake.py:1276` fajl sadrži sadržaj koji je **namerno bio šifrovan u Storage-u** i sad izlazi iz te zaštite na lokalni FS.
`DOKAZ` Sopstveno čitanje svih pet mesta. `delete=False` je nužan jer `extract()` prima `Path` i sam otvara fajl — nalaz je o cleanup-u, ne o izboru API-ja.
`VERDIKT` **FAIL — MEDIUM.**

---

**DFM-013 — GDPR brisanje naloga ne dodiruje nijedan dokument**
`IZVOR` `routers/gdpr.py:201-254`
`TIP PODATKA` Svi podaci korisnika
`ULAZ` `DELETE /api/gdpr/account` `IZLAZ` izmena `profiles.email`/`full_name` + gašenje notifikacija
`KONTROLA` Founder nalog zaštićen (`:214-215`); nepromenjivi audit zapis (`:239-245`)
`MOGUĆ BYPASS` Nije bypass nego nedostajuća funkcija. Ne dodiruje: `predmet_dokumenti.tekst_sadrzaj`, blobove u `intake-dokumenti`/`klijent-dokumenti`/`portal-uploads`, trajne Pinecone vektore, `predmet_istorija`, `klijenti`. Odgovor to **iskreno priznaje** (`:250-253`) pozivom na Zakon o advokaturi — što je legitiman osnov za advokatske spise, ali ne postoji **nijedan** mehanizam izvršenja prava na zaborav kad taj osnov ne važi.
`DOKAZ` Sopstveno čitanje `_delete()` (`:219-228`): tačno dva poziva, obe na `profiles` i `korisnik_email_notif`.
`VERDIKT` **FAIL — MEDIUM.** Poštena dokumentacija ne zamenjuje nepostojeći put brisanja.

---

**DFM-014 — Za sadržaj dokumenata ne postoji nijedna retenciona politika**
`IZVOR` `services/retention_service.py:56-58`, `:122-149`
`TIP PODATKA` Konfiguracija retencije
`ULAZ` — `IZLAZ` briše `security_events` (90 d), `user_daily_activity` (90 d), `ai_forensics` (180 d), Pinecone `tmp_*`
`KONTROLA` Dnevni cron dispečer (`api.py:2045`)
`MOGUĆ BYPASS` Ne pokriva ni jednu kolonu sa sadržajem dokumenta, nijedan Storage bucket, ni trajne Pinecone namespace-ove. `usage_events` i `response_audit` su eksplicitno izuzeti kao neodlučeni (`:64`).
`DOKAZ` Četiri `_cleanup_*` funkcije, popisane u §4.1.
`VERDIKT` **FAIL — MEDIUM.**

---

**DFM-015 — Transkript glasovne komande se loguje na INFO nivou**
`IZVOR` `routers/voice.py:532`
`TIP PODATKA` Transkribovana govorna komanda advokata, do 120 znakova
`ULAZ` `text` iz Whisper-a `IZLAZ` `logger.info("[VOICE] uid=%.8s text='%s'", uid, text[:120])`
`KONTROLA` `uid` skraćen na 8 znakova; tekst nije
`MOGUĆ BYPASS` INFO je podrazumevano uključen u produkciji, za razliku od DEBUG. Advokat izgovara imena klijenata i brojeve predmeta. Log ide u agregator/kolektor van aplikacije.
`DOKAZ` Sopstveno čitanje `routers/voice.py:528-532`. Poređenje: `main.py:287` koristi `_hash_za_log(pitanje)`, `security/prompt_guard.py:201-203` koristi `_short_hash(text)` — projekat zna ispravan obrazac i primenjuje ga drugde.
`VERDIKT` **FAIL — LOW.**

---

**DFM-016 — DEBUG logovi sa isečcima dokumenta i AI odgovora**
`IZVOR` `main.py:3695`, `main.py:4206`
`TIP PODATKA` 200 znakova teksta dokumenta / 200 znakova AI odgovora
`ULAZ` `tekst_api` / `raw` `IZLAZ` `logger.debug(... %r, ...[:200])`
`KONTROLA` DEBUG nivo (obično isključen); `main.py:3695` loguje **posle** `_skini_pii` (`:3691`)
`MOGUĆ BYPASS` Uključivanje DEBUG-a radi dijagnostike izlaže sadržaj dokumenata. `main.py:4206` loguje AI odgovor, koji **nije** prošao PII maskiranje.
`DOKAZ` Sopstveno čitanje `main.py:3688-3698`.
`VERDIKT` **FAIL — LOW.**

---

**DFM-017 — Poruka izuzetka trećeg servisa se prosleđuje klijentu**
`IZVOR` `api.py:5175`; `routers/dokument.py:319`
`TIP PODATKA` Sirova poruka greške Pinecone SDK-a
`ULAZ` `_pe_str = str(_pe)` `IZLAZ` `HTTPException(500, detail=f"Greška pri obradi dokumenta: {_pe_str}")`
`KONTROLA` Nijedna
`MOGUĆ BYPASS` Pinecone greške pri `upsert`-u (npr. prekoračenje veličine metadata) mogu da uključe deo problematičnog `metadata` objekta — a taj objekat sadrži `metadata["text"]`, tj. tekst dokumenta. Ograničeno: odgovor ide **istom autentifikovanom korisniku koji je dokument i poslao**, pa nije curenje između zakupaca. Da li Pinecone stvarno vraća sadržaj u telu greške nije verifikovano bez pozivanja naplativog API-ja.
`DOKAZ` Sopstveno čitanje oba mesta.
`VERDIKT` **UNKNOWN — LOW.** Obrazac je loš bez obzira; posledica nije dokazana.

---

**DFM-018 — PostgREST filter injekcija u pretrazi dokumenata**
`IZVOR` `routers/search.py:94-99`
`TIP PODATKA` Korisnički upit pretrage
`ULAZ` `q2 = q.replace("%", "")` `IZLAZ` `.or_(f"naziv_fajla.ilike.%{q2}%,tekst_sadrzaj.ilike.%{q2}%,tip_dokaza.ilike.%{q2}%")`
`KONTROLA` Uklanja se samo `%`. Zarez, tačka i zagrade **ostaju** — a zarez je separator uslova u PostgREST `or=` izrazu.
`MOGUĆ BYPASS` Upit sa zarezom ubacuje dodatne OR uslove u izraz. **Ne omogućava čitanje tuđih podataka** — `.eq("user_id", uid)` (`:97`) je zaseban AND uslov na nivou upita i injekcija u `or_` grupu ga ne može poništiti. Praktičan domet je izmena rangiranja/filtriranja unutar sopstvenih podataka i eventualno malformisan upit (500).
`DOKAZ` Sopstveno čitanje `routers/search.py:94-99`.
`VERDIKT` **FAIL — LOW.** Nepotpuna sanitizacija; nema dokazanog prelaza granice zakupca.

---

**DFM-019 — PII klijenta nedosledno šifrovan**
`IZVOR` `klijenti/router.py:265-280`
`TIP PODATKA` Lični podaci klijenta
`ULAZ` `KlijentRequest` `IZLAZ` red u `klijenti`
`KONTROLA` `jmbg`/`broj_pasosa`/`pib` prolaze `encrypt_field` (`:276-280`)
`MOGUĆ BYPASS` `adresa` (`:266`), `telefon` (`:265`), `email`, `ime`, `prezime` idu **plaintext**. Kućna adresa fizičkog lica je osetljiv podatak po ZZPL isto koliko i JMBG; kombinacija ime+adresa+telefon je pun identitet i bez JMBG-a. `security/crypto.py:8` navodi HARD RULE samo za „JMBG, pasoš, PIB", pa je implementacija u skladu sa sopstvenim pravilom — ali je samo pravilo preusko.
`DOKAZ` Sopstveno čitanje `klijenti/router.py:265-280`, `:481-498`.
`VERDIKT` **FAIL — LOW.**

---

**DFM-020 — CLI/skript artefakti sa plaintext sadržajem, trajni**
`IZVOR` `uploaded_doc/__main__.py:51-53`; `scripts/genome_bootstrap_sample.py:97-108`
`TIP PODATKA` Chunk-ovi dokumenta + `source_filename` + sha256 / `tekst_sadrzaj_excerpt[:6000]`
`ULAZ` — `IZLAZ` `manifests/{stem}-manifest.json` / `genome_bootstrap_mapping_LOCAL_ONLY.json`
`KONTROLA` Nijedna — bez brisanja, bez šifrovanja
`MOGUĆ BYPASS` Nedostupno preko FastAPI aplikacije (samo `python -m uploaded_doc` / ručno pokretanje). Rizik je operativni: fajlovi mogu završiti u repozitorijumu ili backup-u ako se skripta pokrene nad stvarnim dokumentom.
`DOKAZ` Sopstveno čitanje `uploaded_doc/__main__.py:45-53`.
`VERDIKT` **FAIL — LOW (van serverskog puta).**

---

**DFM-021 — Kontrole koje su dokazano ISPRAVNE**

| Kontrola | Dokaz | Verdikt |
|---|---|---|
| `ai_forensics` čuva prompt i odgovor **isključivo kao SHA-256** | `security/ai_forensics.py:96`,`:110`,`:103`; allowlist kolona `:364-366`. **Ograničeno — v. DFM-027 za `error_message` i `retrieval_query`** | **PASS uz izuzetak** |
| `feature_usage_log` ne nosi sadržaj | migr. `065:175-189`, `112:51-52` | **PASS** |
| Fail-fast validacija ključa pre prvog zahteva (`sys.exit(1)`) | `security/crypto.py:55-117`, poziv `api.py:78-80` | **PASS** |
| Sentry `send_default_pii=False` | `api.py:47` | **PASS** |
| Cohere (jedini izlaz van OpenAI/Pinecone) podrazumevano isključen | `app/services/retrieve.py:532-542` | **PASS** |
| Nijedan PDF/DOCX/ZIP generator ne piše na disk | `dossier_pdf.py:100`, `predmet_pdf.py:131`, `docx_export.py:91`, `data_export.py:99` — svi `io.BytesIO` | **PASS** |
| Nema `pickle.dump`, `shutil.copy/move`, `to_csv`, `get_public_url` u produkciji | iscrpan grep, §3.3 | **PASS** |
| `generate_storage_key()` daje `encrypted_blob_<uuid4>` bez imena fajla | `security/crypto.py:215-222`, korišćen `klijenti/router.py:791` | **PASS** |
| Auth tag AES-GCM se stvarno proverava | eksperiment 4a/4b, §2.3 | **PASS** |
| `tmp_` namespace ownership provera preko `owner_user_id` | `routers/dokument.py:200-214`, `:309` | **PASS** |
| Trezor download upisuje audit **pre** vraćanja fajla | `klijenti/router.py:951-957` | **PASS** |
| `cleanup_expired` ne briše namespace na prazan upit (eventual consistency) | `uploaded_doc/cleanup.py:57-73` | **PASS** |

---

**DFM-022 — API ključevi korisnika u bazi u čistom obliku**
`IZVOR` `routers/export.py:66-72`; provera `routers/integracije.py:73-76`
`TIP PODATKA` Dugoživeći API kredencijal (`vndx_...`), do 3 po PRO korisniku
`ULAZ` `kljuc = _generiši_api_kljuc()` `IZLAZ` `api_kljucevi.insert({"kljuc": kljuc, ...})`
`KONTROLA` Nijedna — provera radi `.eq("kljuc", api_key)`, što **zahteva** plaintext zapis
`MOGUĆ BYPASS` Ko pročita tabelu (dump baze, backup, service-role ključ, insajder) dobija upotrebljive kredencijale za `/api/integracije/*` bez ijedne dalje prepreke.
`DOKAZ` `security/crypto.py:19-20` imenuje **tačno ovaj scenario** kao svrhu postojećeg Argon2id primitiva: „hash dugotrajnog API/integracionog tokena pre upisa u bazu". `hash_password()` je implementiran, testiran i **nema nijedno pozivno mesto** (`crypto.py:14-16`). Rešenje je već u repozitorijumu i nije priključeno.
`VERDIKT` **FAIL — HIGH.**

---

**DFM-023 — Pun AI tekst i advokatove ispravke, nešifrovano i bez roka**
`IZVOR` `routers/corrections.py:293-294`; `routers/drafting.py:295`
`TIP PODATKA` `ai_corrections.original_output` / `edited_output` (po 8.000 zn.); `staging_memory.tekst` (pun nacrt podneska)
`ULAZ` AI izlaz + advokatova redakcija `IZLAZ` redovi u bazi
`KONTROLA` RLS po `user_id`/`kancelarija_id`
`MOGUĆ BYPASS` Ovo je najosetljiviji mogući sadržaj — nacrt podneska pre podnošenja i tačna razlika između onoga što je AI predložio i onoga što je advokat potpisao. Nijedna retencija, nijedan put brisanja, nijedno šifrovanje.
`DOKAZ` Sopstveno čitanje oba mesta upisa.
`VERDIKT` **FAIL — MEDIUM.**

---

**DFM-024 — Imena stranaka i sudija izvučena iz dokumenta, plaintext**
`IZVOR` `shared/intake_documents.py:70`, `:308`
`TIP PODATKA` `extracted_entities.value` / `corrected_value` — `plaintiff`, `defendant`, `judge`, `case_number`, `amount`
`ULAZ` GPT ekstrakcija iz dokumenta `IZLAZ` redovi u `extracted_entities`
`KONTROLA` RLS
`MOGUĆ BYPASS` Ovo je **strukturisan, upitljiv indeks identiteta stranaka** — opasniji od slobodnog teksta jer se može direktno pretraživati („svi predmeti gde je tuženi X"). Šifrovanje JMBG-a (`klijenti/router.py:276`) ne štiti ništa dok isti identitet stoji ovde u čistom obliku.
`DOKAZ` Sopstveno čitanje; kolona definisana migr. `074:75`, `:79`.
`VERDIKT` **FAIL — MEDIUM.**

---

**DFM-025 — `klijenti_audit` trajno čuva plaintext IP i email, bez mogućnosti brisanja**
`IZVOR` `klijenti/audit.py:53-62`; trigger migr. `002_klijenti_crm.sql:119-127`
`TIP PODATKA` `user_email` (plaintext), `ip_adresa` (**plaintext, ne hash**)
`ULAZ` svaka CRM akcija `IZLAZ` red u `klijenti_audit`
`KONTROLA` Append-only trigger blokira `UPDATE` i `DELETE`
`MOGUĆ BYPASS` Nije napad nego trajna nesaglasnost: `audit_immutable` za istu svrhu čuva **`ip_hash`** (migr. `043:24-25`), a `klijenti_audit` čuva sirovu IP adresu. IP je lični podatak po ZZPL/GDPR. Trigger znači da ni GDPR zahtev ni operator ne mogu to ukloniti — nepromenjivost audita ovde radi **protiv** minimizacije podataka.
`DOKAZ` Sopstveno čitanje `klijenti/audit.py:53-62`; poređenje sa `shared/audit_immutable.py`.
`VERDIKT` **FAIL — MEDIUM.**

---

**DFM-026 — Trajni zapisi koji sadrže imena fajlova, bez roka i bez brisanja**
`IZVOR` `shared/audit_immutable.py:388`; upis `api.py:5278`, `:5889`; `notification_log` preko `shared/notify_quiet.py:75-77`
`TIP PODATKA` `audit_immutable.metadata.naziv_fajla`; `notification_log.message_text`
`ULAZ` naziv fajla / tekst notifikacije `IZLAZ` trajni redovi
`KONTROLA` Trigger blokira `DELETE`/`UPDATE` na `audit_immutable` (migr. `043:49-52`)
`MOGUĆ BYPASS` Naziv fajla u advokatskoj praksi sam po sebi otkriva stranke i predmet (`Tuzba_Petrovic_protiv_Delta.pdf`). Tekst notifikacije nosi naziv predmeta i rok. Oba su trajna po dizajnu — što je ispravno za integritet audita, ali znači da minimizacija mora da se dogodi **pre** upisa, a ne dogodi se.
`DOKAZ` Sopstveno čitanje `api.py:5278`, `:5889`.
`VERDIKT` **FAIL — LOW.**

---

**DFM-027 — Dva kanala kojima plaintext može ući u hash-only audit tabelu**
`IZVOR` `shared/ai_client.py:462`; migr. `089_ai_provenance_extension.sql:43`
`TIP PODATKA` (a) `ai_forensics.error_message = str(error)[:500]` — **aktivno se piše**; (b) `ai_forensics.retrieval_query` TEXT — **kolona i plumbing postoje, danas bez pisca**
`ULAZ` (a) izuzetak OpenAI/Pinecone SDK-a; (b) `case_context(retrieval_query=...)`
`KONTROLA` (a) skraćivanje na 500 zn.; (b) nijedna
`MOGUĆ BYPASS` (a) Poruke grešaka LLM provajdera rutinski uključuju deo problematičnog zahteva — dakle fragment prompta, koji sadrži tekst dokumenta. Tabela je projektovana kao hash-only (`security/ai_forensics.py:14-16`), pa ovaj kanal tiho ruši tu garanciju. (b) Kolona čeka prvog pozivaoca; kad se pojavi, upisaće sirov tekst upita u tabelu koja po dizajnu ne sme da ga ima — bez ijednog upozorenja u kodu.
`DOKAZ` Grep `retrieval_query` → 8 pogodaka, **svi u definiciji/plumbingu, nijedan pozivalac ga ne prosleđuje**. `error_message` verifikovan na `shared/ai_client.py:462`.
`VERDIKT` (a) **FAIL — LOW.** (b) **UNKNOWN — latentno.** Nije danas curenje; jeste postavljena zamka.

---

## 7. Rezime po ozbiljnosti

| ID | Nalaz | Verdikt |
|---|---|---|
| DFM-001 | Klijentski portal čuva original **nešifrovan** u `portal-uploads` | **CRITICAL** |
| DFM-003 | Privatnost `portal-uploads` bucket-a nedokaziva iz koda | **UNKNOWN / potencijalno CRITICAL** |
| DFM-002 | 60-min signed URL ka tom nešifrovanom blobu | HIGH |
| DFM-009 | `predmet_dokumenti.tekst_sadrzaj` — 100k zn. plaintext, bez retencije | HIGH |
| DFM-010 | Pinecone metadata — 40k zn. plaintext po vektoru, trajno, treća strana | HIGH |
| DFM-022 | API ključevi korisnika plaintext u bazi (Argon2id postoji, nije priključen) | HIGH |
| DFM-005 | AAD se ne koristi — ciphertext nije vezan za kontekst | MEDIUM |
| DFM-023 | `ai_corrections`/`staging_memory` — pun nacrt i redakcija, plaintext, bez roka | MEDIUM |
| DFM-024 | `extracted_entities.value` — imena stranaka/sudija, plaintext, pretraživo | MEDIUM |
| DFM-025 | `klijenti_audit` — plaintext IP i email, append-only, neizbrisivo | MEDIUM |
| DFM-006 | Jedan ključ za 6 namena, bez KDF-a | MEDIUM |
| DFM-007 | Rotacija ključa deklarisana ali neimplementirana | MEDIUM |
| DFM-008 | `InvalidTag` se guta i vraća kao string | MEDIUM |
| DFM-011 | Pipeline A šalje dokument OpenAI-u bez `_skini_pii` | MEDIUM |
| DFM-012 | Plaintext temp fajlovi, best-effort brisanje | MEDIUM |
| DFM-013 | GDPR brisanje ne dodiruje nijedan dokument | MEDIUM |
| DFM-014 | Nema retencije za sadržaj dokumenata | MEDIUM |
| DFM-011b | `_skini_pii` ne maskira imena/adrese | LOW |
| DFM-015 | Transkript glasa u INFO logu | LOW |
| DFM-016 | DEBUG logovi sa isečcima | LOW |
| DFM-018 | PostgREST filter injekcija (bez prelaza zakupca) | LOW |
| DFM-019 | `adresa`/`telefon` klijenta plaintext | LOW |
| DFM-020 | CLI artefakti sa plaintext sadržajem | LOW |
| DFM-026 | Imena fajlova trajno u `audit_immutable`, tekst poruka u `notification_log` | LOW |
| DFM-027a | `ai_forensics.error_message` može nositi fragment prompta | LOW |
| DFM-017 | Poruka Pinecone greške ka klijentu | UNKNOWN / LOW |
| DFM-027b | `ai_forensics.retrieval_query` — plumbing bez pisca (latentno) | UNKNOWN |
| DFM-004 | **Nonce AES-GCM — kolizija nije praktično moguća** | **PASS** |
| DFM-021 | 12 dokazano ispravnih kontrola (jedna uz izuzetak) | PASS |

**Ukupno: 1 CRITICAL, 1 UNKNOWN-potencijalno-CRITICAL, 4 HIGH, 8 MEDIUM, 8 LOW, 2 UNKNOWN, 13 PASS.**

---

## 8. Otvorena pitanja (`UNKNOWN` — ne mogu se zatvoriti iz koda)

1. **Da li je `portal-uploads` bucket zaista privatan?** Nema migracije, samo komentar
   (DFM-003). Zahteva ručnu proveru u Supabase Dashboard-u.
2. **Da li je `klijent-dokumenti` bucket privatan?** Isto — nema `INSERT INTO storage.buckets`.
3. Da li Pinecone SDK vraća sadržaj `metadata` u telu greške (DFM-017). Provera bi zahtevala
   poziv naplativog API-ja — nije izvedena.
4. Stvarni sadržaj produkcione baze nije čitan (nula upita), pa je popis kolona u §4 izveden
   iz `migrations/`, `supabase_setup.sql` i pozivnih mesta u kodu, ne iz žive šeme.
5. Da li `klijenti.jmbg_mb` (legacy plaintext JMBG kolona) i dalje postoji u živoj bazi.
   `DROP` naredba postoji u `supabase_migration.sql:192`, ali je u `migrations/002_klijenti_crm.sql:67`
   **zakomentarisana**. Ne može se utvrditi iz repozitorijuma.
6. Da li se `integracije.access_token`/`refresh_token` (migr. `058:56-57`) igde pune — nijedan
   pisac nije nađen u `routers/integracije.py` ni `routers/integrations.py`. Kolone postoje,
   upisi nisu dokazani.
7. `ai_sessions` (koristi se `api.py:3227`,`:3248`) **nema definiciju ni u jednoj migraciji** —
   njen sadržaj i retencija se ne mogu proceniti iz repozitorijuma.

---

## 9. Ograničenja ove analize

- Isključivo statička analiza + jedan lokalni kriptografski eksperiment sa sintetičkim ključem.
- **Nijedan produkcijski fajl nije izmenjen.** Ovaj dokument je jedini novi fajl.
- **Nula upita ka produkcionoj bazi, nula mutacija.**
- `F2-001` i 13 odloženih helpera nisu dirani.
- Kredencijali nisu čitani ni ispisivani.
- Verdikti se odnose na stanje na commit-u `0df948ec`.

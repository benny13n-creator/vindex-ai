# BETA-DATA-ID-02 — Forenzika 43 dokumenta + ponovni sweep pisaca (§5, §13, §15)

**Baseline:** `78ff5d73`
**Metod:** samo čitanje. Nijedan produkcijski fajl, test ni migracija nisu menjani ovim izveštajem.
Prema Supabase-u pozvani su samo `select(...)`, `storage.list_buckets()` i `storage.from_(...).list(path=...)`.
Prema Pinecone-u samo `describe_index_stats()` i `Index.list()` (vraća **isključivo ID-eve**) —
nijedan `fetch`/`query`, dakle nijedan metapodatak ni tekst dokumenta nije pročitan.
**0 upisa, 0 brisanja, 0 upsert-a.**

**PII:** svi identifikatori su skraćeni na 8 znakova. Nijedan naziv fajla, sadržaj dokumenta,
ime klijenta ni kredencijal nije ispisan.

**Pravilo dokaza:** svaka tvrdnja nosi `fajl:linija` ili izmereni izlaz. Gde dokaza nema — `UNKNOWN`.

---

## 0. UPOZORENJE: radno stablo se PONOVO promenilo TOKOM revizije

Na `78ff5d73` radno stablo je bilo čisto od izmena praćenih fajlova. Tokom ove revizije:

```
 M api.py
 M routers/dokument.py
 M routers/drafting.py
 M routers/smart_intake.py
 M shared/vector_identity.py
```

Paralelni agent implementira ID-02 model (`verzija_dokumenta`, `EXTRACTION_VERSION`).
**Isti obrazac kao u ID-01 §7 — drugi put zaredom.** Sekcije 1–3 opisuju **BASELINE**,
a §4 analizira drift; drift sadrži **tri nalaza koja implementacija ne vidi**, od kojih
**D-5 tiho obara upravo ono zbog čega ID-02 postoji** — mogućnost da se iz reda u bazi
nađu vektori tog dokumenta.

---

# ZADATAK A — KLASIFIKACIJA 43 DOKUMENTA (§5)

## A.1 Izmereno stanje (živa baza + živi Pinecone)

Broj redova **verifikovan sam**, ne preuzet iz sprinta 003/004:

```
predmet_dokumenti rows                          : 43     (count="exact")
distinct predmet_id                             : 17
distinct user_id                                : 1
distinct pinecone_namespace                     : 43     (1 namespace po dokumentu)
created_at raspon                               : 2026-07-18T20:49 .. 2026-07-21T20:47

status distribucija                             : {'sacuvano': 43}      <-- 0 'indeksirano'
content_sha256 popunjen                         : 0 od 43
tekst_sadrzaj popunjen                          : 43 od 43   (77..580 znakova)
storage_path oblik                              : 'session/{id}' na 43/43
naziv_fajla ekstenzija                          : .docx na 43/43
```

Sva tri nasleđena tvrđenja iz sprinta 003/004 su **POTVRĐENA**. Dodato je četvrto,
koje nijedan raniji sprint nije zabeležio: **`tekst_sadrzaj` je popunjen na 43/43**, i to
je jedini razlog zbog kog uopšte postoji kategorija A umesto C.

### Pinecone, mereno

```
ukupno vektora                                  : 434.217
namespace-ova                                   : 11
  sudska_praksa   407.795 | zakoni_rs 25.822 | web3_zdi_mca 479
  misljenja            74 | carf_dac8     17
  6 x pred_{hex32}      5 svaki  = 30 vektora
DB namespace-ova koji POSTOJE u Pinecone-u      : 0 od 43
živih pred_* koji odgovaraju nekom DB redu      : 0 od 6
živih pred_* čiji sufiks je predmet_id          : 0 od 6
oblik ID-a u svih 6 živih pred_*                : uuid4 (8-4-4-4-12), 30/30
```

### Definitivna provera „postoji li ijedan vektor za ijedan od 43 dokumenta"

Ranije sprintove je zaustavljalo to što je `content_sha256` prazan, pa se kanonski prefiks
nije mogao konstruisati. **Ovde jeste konstruisan** — iz `tekst_sadrzaj`, po ID-01/ID-02 modelu:

```
prefiks = {scope}__{verzija}__k1_c
  scope   = predmet_id           (poznat iz baze)
  verzija = sha256("e1|" + tekst_sadrzaj)[:32]
```

Provereno je i sekundarno tumačenje (`scope = session_id` iz `pinecone_namespace`).

```
86 jedinstvenih prefiksa  ×  11 živih namespace-ova  =  946 Index.list(prefix=...) sondi
POGODAKA: 0        grešaka: 0
```

**Nijedan od 43 dokumenta nema nijedan vektor, nigde u indeksu, ni pod jednim modelom scope-a.**
Ovo je prva egzaktna (a ne posredna, „namespace ne postoji") potvrda.

## A.2 Da li originalni artefakt još postoji — DOKAZ, ne pretpostavka

`storage_path` je na sva 43 reda oblika `session/{session_id}`. To je **labela, ne put**:

* živi bucket-i (`storage.list_buckets()`): **`intake-dokumenti`, `portal-uploads`** — oba
  `public=false`. Bucket `klijent-dokumenti` (`klijenti/router.py:812`) **ne postoji uživo**.
* `storage.from_(<bucket>).list(path="session")` nad sva tri imena bucket-a: **0 objekata, 0 grešaka**.

Provenijencija je dokazana iz istorije, ne pogađana. Verzija `api.py` na `c3e00386`
(2026-07-20, unutar raspona `created_at`) piše:

```
api.py:3859   ingest_session(..., namespace_prefix="pred_")
api.py:3872   _tekst_preview = text[:100_000]
api.py:3890   "storage_path":       f"session/{session_id}"
api.py:3891   "pinecone_namespace": f"pred_{session_id}"
api.py:3893   "status": "indeksirano" if _pinecone_ok else "sacuvano"
```

Sva četiri merena oblika (`session/…`, `pred_{hex32}` dužine 37, `tekst_sadrzaj` ≤ 100k,
`sacuvano`) se poklapaju. **Pisač je Pipeline A (`api.py`), era pre 2026-08-04.**
U toj verziji koda **nije postojao nijedan `storage.upload` poziv na toj putanji** — upis
originala u `intake-dokumenti` uveden je tek Sprintom Intake 001 (`api.py:5099-5108`).

**Zaključak: original NIKAD nije ni sačuvan.** Nije obrisan — nije ni postojao. Kategorija B
je time prazna po konstrukciji, ne slučajno.

### Šta `status='sacuvano'` na 43/43 DOKAZUJE

U julskoj verziji `_pinecone_ok = False` postoji **tačno jedna** grana (`api.py:3862-3866`):
izuzetak iz `ingest_session` čija poruka sadrži `"429"`, `"Too Many"` ili — po tadašnjem,
presnažnom klasifikatoru — **`"storage"`**. Svaki drugi izuzetak dizao je HTTP 500 i red se
ne bi ni napravio.

Dakle za sva 43 uploada: `ingest_session` je **podigao izuzetak** i `count = 0`.
Da li je to bila stvarna Pinecone kvota **nije dokazivo** — klasifikator je hvatao i svaku
poruku koja sadrži reč „storage". → `UNKNOWN`, ne „verovatno kvota".

Da nije ostao delimičan upis: svih 43 tekstova daje **`total_chunks == 1`** (mereno pravim
produkcijskim `chunk_document`-om nad `tekst_sadrzaj`-em: `{1: 43}`). Jedan chunk = jedan
batch = sve-ili-ništa. Slaže se sa mernim rezultatom 0 vektora.

## A.3 Rekonstruktivnost identiteta

Pod ID-01/ID-02 modelom identitet vektora je `{scope}__{verzija}__k{schema}_c{index}`:

| komponenta | izvor | dostupna? | dokaz |
|---|---|---|---|
| `scope` = `predmet_id` | `predmet_dokumenti.predmet_id` | **DA** 43/43 | živa sonda |
| `verzija` = `sha256("e1\|"+tekst)[:32]` | `predmet_dokumenti.tekst_sadrzaj` | **DA** 43/43 | izračunato za svih 43 |
| `chunk_schema` = 1 | `shared/vector_identity.py:71` konstanta | DA | kod |
| `chunk_index` | ponovni chunking istog teksta | **DA** — 1 chunk po dokumentu | mereno |

**Da li je `tekst_sadrzaj` ISTI tekst koji je bio chunk-ovan?** Da, i to je dokazivo, ne
verovatno: u istoj funkciji ista promenljiva `text` ide i u `chunk_document(text, …)`
(`api.py:3848`) i u `_tekst_preview = text[:100_000]` (`:3872`). Jedina razlika bila bi
skraćivanje na 100.000 znakova — **mereni maksimum je 580 znakova, 0 redova ≥ 100k**.

Zato je identitet **rekonstruktivan iz same baze, bez originalnog fajla**.

**Provereno i pod drugim izvođenjem verzije.** Drift je u drugom talasu premestio izvođenje
u `uploaded_doc/ingest.py:115-131`, gde se hešira **spojeni tekst chunk-ova**, a ne izvorni
tekst (v. nalaz D-5). Za ovih 43 to ne menja ništa — svi imaju `total_chunks == 1`, pa je
spojeni tekst identičan izvornom: **43 od 43 daju istu vrednost pod oba izvođenja, 0 razlike**
(mereno). Klasifikacija A ostaje važeća bez obzira koje izvođenje na kraju preživi.

> **Granica koja se mora priznati:** rekonstruiše se identitet po **ID-02 (tekst) konvenciji**.
> Verzija po staroj `api.py` konvenciji — `sha256(bajtovi_fajla)` — je **trajno nepovratna**,
> jer bajtova nema nigde. To ovde ne šteti samo zato što **nijedan vektor ne postoji** pa
> nema sa čim da se uparuje. Da postoji makar jedan vektor upisan pod bajt-hešom, ovih 43
> bi bili kategorija **C**, ne A. Rekonstrukcija je ovde moguća zato što je skup vektora
> prazan — to je sreća zatečenog stanja, ne svojstvo modela.

## A.4 KLASIFIKACIJA — tačni brojevi

Kategorije iz mandata leže na **dve različite ose** i moraju se tako i brojati:

* **A/B/C** = osa *rekonstruktivnosti identiteta* (objekat = DB dokument)
* **D** = osa *potvrđenosti ingesta* (objekat = DB dokument)
* **E** = osa *siročadi* (objekat = **vektor**, ne dokument)

| KAT | definicija | **BROJ** | dokaz |
|---|---|---|---|
| **A** | identitet se može **dokazano** rekonstruisati | **43** dokumenta | `predmet_id` 43/43 + `tekst_sadrzaj` 43/43 (77–580 zn., 0 na granici 100k) + 1 chunk/dok |
| **B** | rekonstrukcija moguća, ali **samo iz izvornog artefakta** | **0** | original nikad nije upisan (`api.py` te ere nema `storage.upload`); 0 objekata u 3 bucket-a |
| **C** | identitet **nije** dokazivo rekonstruisati | **0** | — |
| **D** | DB red postoji, **ingest vektora nikad potvrđen** | **43** dokumenta | `status='sacuvano'` 43/43; 0/43 namespace-a živ; **946/946 prefiks-sondi bez pogotka** |
| **E** | Pinecone vektor postoji, **veza sa DB nije dokaziva** | **30 vektora** u **6** namespace-ova | 6 živih `pred_*`, 0 odgovara ijednom DB redu ili `predmeti.id`; svi ID-evi `uuid4` |

**Svih 43 dokumenata je istovremeno A i D.** To nije nedoslednost: A kaže *„znamo koji bi
im ID bio"*, D kaže *„taj ID trenutno ne postoji ni u jednom vektoru"*. Skupovi A i D se
ovde poklapaju u celosti.

**E se ne preklapa ni sa jednim od 43** — 30 siročadi su vektori bez DB reda, a 43 dokumenta
su DB redovi bez vektora. Presek je prazan u oba smera.

### Zašto E ostaje E i ne može se rešiti ovom revizijom

Identitet 30 siročadi bio bi utvrdiv jedino iz njihovih **metapodataka** (`session_id`,
`predmet_id`, `source_filename`). Njih vraća `fetch`/`query`, a to su pozivi koje mandat
zabranjuje (i koji bi vratili `text` do 40.000 znakova — sadržaj dokumenta). ID `uuid4`
sam po sebi ne nosi ništa. **`UNKNOWN` po konstrukciji, ne po propustu.**

### A.5 Negativna kontrola koju je merenje oborilo

Radna hipoteza: pošto je od ID-01 `verzija` deo ID-a vektora, dva dokumenta **istog sadržaja
u istom predmetu** dobila bi identičan ID i drugi bi `upsert`-om prepisao prvi.

Mereno nad stvarnih 43: **19 jedinstvenih tekstova na 43 dokumenta** (isti tekst se javlja
u 2 predmeta ×15, u 3 predmeta ×3, u 4 predmeta ×1). Kolizije unutar istog `predmet_id`:
**0 grupa, 0 dokumenata**. Duplikati postoje **isključivo preko granica predmeta**, gde ih
`scope` razdvaja — RULE 12 radi tačno kako je projektovan.

**Hipoteza oborena na postojećim podacima.** Ali oborena je *zatečenim rasporedom*, ne
garancijom: ništa u šemi ne sprečava dva dokumenta istog sadržaja u istom predmetu.
Vidi §4, nalaz D-2, gde isti mehanizam **jeste** proizveo sudar.

---

# ZADATAK B — PONOVNI SWEEP SVIH INGEST PISACA (§13)

## B.0 Metod i njegove granice

Nezavisan **AST** prolaz (`ast.walk`, ne grep) nad 396 `.py` fajlova; kriterijumi:
`Call.func.attr == "upsert"` **sa** `vectors=`/`namespace=` (Supabase `upsert` prima
pozicioni dict — 34 takva poziva su tako i odbačena), `embed_documents`/`embed_query`/
`embeddings.create`, referenca na `ingest_session`/`ingest_playbook`/`ingest_stav`,
i `delete` sa `ids=`/`delete_all=`.

**Dve priznate granice metoda, jedna od njih se OSTVARILA:**

1. Prvi prolaz je tražio `ast.Name.id in SINKS` i **promašio `routers/interni.py:37`**, jer je
   uvoz aliasiran (`from interni_stavovi import ingest_stav as _ingest_stav`, `:16`).
   Ispravljeno drugim prolazom. **Zadata lista je time potvrđena kao nepotpuna po istoj
   mehanici kojom je bila nepotpuna i u ID-01.**
2. `getattr`-om sakriven upsert ne bi bio nađen. Grep za `getattr(.*upsert` / `"upsert"` daje
   **3 pogotka, sva tri su `file_options={"upsert": "false"}` u Supabase Storage-u** — dakle
   granica je u ovom repou prazna, ali je granica.

**`ingest_session` NIJE tabela.** Sonda: `public.ingest_session` i `public.ingest_sessions`
**ne postoje**. To je isključivo deljena sink funkcija `uploaded_doc/ingest.py:39`.
Kolona „koristi `ingest_session`?" ispod se odnosi na nju.

## B.1 Rezultat: 19 fizičkih upsert mesta (ne 7, ne 10)

Zadata lista imenuje 10 **fajlova**; od toga 4 (`api.py`, `smart_intake.py`, `drafting.py`,
`dokument.py`) uopšte nisu upsert mesta nego **pozivaoci sink funkcije**. Fizičkih upsert
poziva ima **19**: **7 u runtime kodu aplikacije** + **12 u batch/CLI skriptama koje pišu u
ISTE žive namespace-ove**.

### B.1.a PISAČI U RUNTIME-u APLIKACIJE (7 upsert mesta + 6 pozivalaca)

| # | fajl:linija | `ingest_session`? | deterministički ID? obrazac | odbrana od delimičnog embeddinga | status koji upisuje | greška: propagira/guta | idempotentan? |
|---|---|---|---|---|---|---|---|
| **W1** | `uploaded_doc/ingest.py:170` (sink) | — *(on JESTE sink)* | **DA** — `{scope}__{verzija}__k1_c{i}` (`vector_identity.py:144`) | **DA** — `len(vectors_raw) != len(chunks)` → `raise` (`:87-91`) | ne piše status | **PROPAGIRA** (`:168 raise`) | **DA** za ceo dokument; **NE** za delimičan batch — već upisani batch-evi ostaju (`:162-168`, kod to sam priznaje) |
| **W1a** | `api.py:5211` (pozivalac) | **DA** | preko W1; `verzija` = heš teksta *(drift)* | preko W1 + `ingest_je_potpun` (`:5233`) | `indeksirano`/`sacuvano` (`:5285`) | kvota → guta i `sacuvano`; ostalo → **HTTP 500** | DA — isti tekst = isti ID-evi |
| **W1b** | `routers/smart_intake.py:1413` | **DA** | preko W1 | preko W1 + `ingest_je_potpun` (`:1432`) | `indeksirano`/`sacuvano` (`:1448`) | **GUTA** (`:1439-1441 log.warning`, `pinecone_ok=False`) | DA (uz `content_sha256` gate `:1352`) |
| **W1c** | `routers/drafting.py:368` | **DA** | preko W1 | preko W1 + `ingest_je_potpun` (`:389`) | `indeksirano`/`sacuvano` (`:409`) | **GUTA** (`:381-383` → `return False`) | DA |
| **W1d** | `routers/dokument.py:304` | **DA** | preko W1; scope = `session_id` (nema predmeta) | preko W1 + `ingest_je_potpun` | **ne pravi DB red uopšte** | kvota → guta; ostalo → propagira | **NE** — svaki upload novi `tmp_{uuid4}` namespace |
| **W2** | `drafting/playbook.py:94` | ne | **NE** — `pb_{user_id}_{i}_{uuid4[:8]}` (`:82`) | **DA** (`:75-79 raise`) | ne piše status | **PROPAGIRA** | **NE** — ponovni ingest duplira |
| **W3** | `interni_stavovi.py:89` | ne | **NE** — `is_{user_id[:8]}_{i}_{uuid4[:8]}` (`:76`) | **DA** (`:69-73 raise`) | ne piše status | **PROPAGIRA** | **NE** — ponovni ingest duplira |
| **W4** | `routers/knowledge_base.py:105` | ne | **DA** — `kb_{uid}_{beleska_id}` (`:107`) | n/a (1 vektor po belešci) | ne piše status | **GUTA** (`:121-123`) — a poziv je `asyncio.create_task` fire-and-forget (`:197`), pa API vraća `{"ok": true}` i kad Pinecone padne | **DA** — jedini pisač sa preciznim `delete(ids=…)` (`:385`) |
| **W5** | `routers/law_upload.py:92` | ne | **DA** — `{safe_id}_c{i}` (`:137`), `safe_id` iz `law_docs.id` | **DA** za embed (`:126 raise`, `:129-133 raise`) | `pending`/`running`/`done`/`failed` u **`law_docs`** | **embed: propagira; upsert: GUTA** (`:154-155`) | **NE** — `doc_id = uuid4()` (`:207`), ponovni upload istog PDF-a = nov prefiks = duplikat |
| **W6** | `routers/batch_ingest.py:63` | ne | **DA** — `{ascii_decision_id}_c{i}` (`:93`) | **NE** | `done`/`failed` u **`ingest_jobs`** (`:160`) | **GUTA** (embed `:145-147`, upsert `:155-157`) | DA (deterministički ID prepisuje) |
| **W7** | `routers/auto_discovery.py:212` | ne | **DA** — `discovery_{sha256(chunk)[:32]}` (`:199-200`) | **DELIMIČNO** — pad se puni nula-vektorima (`:178`) koji se kasnije tiho preskaču (`:197-198`) | status u `discovery_queue` | **GUTA** (embed `:175-178`, upsert `:219-224`) | DA po sadržaju, ali **bez scope-a** — v. nalaz L-5 |

Deljeni sink `uploaded_doc/ingest.py:39` je **jedini pisač sa punim identitetom**. Sva tri
njegova pozivaoca koja prave `predmet_dokumenti` red (`api.py`, `smart_intake.py`,
`drafting.py`) rade upsert **pre** insert-a — nepromenjeno u odnosu na ID-01 §2.

### B.1.b PISAČI VAN RUNTIME-a — batch/CLI, pišu u ISTE žive namespace-ove

Ovi nisu u zadatoj listi **nijednog** ranijeg sprinta, a njihov proizvod je **99,99 %
sadržaja produkcijskog indeksa** (434.187 od 434.217 vektora).

| # | fajl:linija | ciljni namespace | deterministički ID? | zaštita od delimičnog | greška | idempotentan? |
|---|---|---|---|---|---|---|
| **S1** | `ingest_misljenja.py:160` | `misljenja` (**74 živa vektora**) | **NE** — `str(uuid.uuid4())` (`:250`) | **NE** — `zip()` bez provere (`:249`) | **`except → log → continue`** (`:243-247`) | **NE** |
| **S2** | `scripts/ingest_sudskapraksa.py:342` | `sudska_praksa` (**407.795**) | DA — `sp_{odluka_id}__chunk_{i}` (`:428`) | NE — `zip()` bez provere (`:333`) | propagira | DA |
| **S3** | `scripts/ingest_case_law.py:173` | `sudska_praksa` | DA — `_ascii_vector_id(chunk_id)` | NE — `zip()` bez provere (`:328/414/585`) | propagira | DA; **ali ima `delete(delete_all=True)` na ceo `sudska_praksa`** (`:347`, `:542`) |
| **S4** | `scripts/ingest_bilten_to_pinecone.py:209` | `sudska_praksa` | DA — `_ascii_vector_id(chunk_id)` (`:203`) | NE — `zip()` bez provere (`:207`) | propagira | DA |
| **S5** | `routers/law_upload.py` ↔ `ingest_laws.py:297` | `zakoni_rs` (**25.822**) | DA — `md5("v2\|{zakon}\|{clan}\|{stav}")` (`semantic_chunker.py:107`) | NE | propagira | DA |
| **S6** | `ingest_kz.py:129` | default `""` | DA — `chunk["id"]` | NE | propagira | DA |
| **S7** | `ingest_glossary_vasp_casp.py:177` | default `""` | DA — konstanta `CHUNK_ID` | n/a (1 vektor) | propagira | DA |
| **S8** | `ingest_short_15.py:154` | default `""` | DA — `_chunk_id(zakon, broj, 1)` | NE | propagira | DA |
| **S9** | `scrape_zdi_mca.py:118` | `web3_zdi_mca` (**479**) | DA — konstante `mica_*` | NE | propagira | DA |
| **S10** | `scripts/ingest_web3_addendum.py:214` | `web3_zdi_mca` | DA — konstante | NE | propagira | DA |
| **S11** | `scripts/ingest_carf_dac8.py:536` | `carf_dac8` (**17**) | DA — konstante `carf_section*` | NE | propagira | DA |
| **S12** | `diag_zpp_revizija.py:196` | default `""` | UNKNOWN | NE | propagira | UNKNOWN — **dijagnostička skripta koja PIŠE u produkcijski indeks** |

### B.1.c Brisači (kompletnost slike identiteta)

| fajl:linija | granularnost | rizik |
|---|---|---|
| `routers/knowledge_base.py:385` | `delete(ids=[…])` — **po zapisu** | jedini precizan |
| `drafting/playbook.py:131` | `delete_all` na `playbook_{uid}` | ceo namespace |
| `interni_stavovi.py:133` | `delete_all` na `interni_stavovi_{uid}` | ceo namespace |
| `uploaded_doc/cleanup.py:90` | `delete_all` na istekle `tmp_*` | ceo namespace |
| `scripts/ingest_case_law.py:347,542` | **`delete_all` na `sudska_praksa`** | **407.795 vektora jednim pozivom iz CLI skripte** |
| `ingest_misljenja.py:221` | `delete_all` na `misljenja` | ceo namespace |

**Za `predmet_dokumenti` i dalje ne postoji nijedan brisač vektora** (G-06 iz ID-01 — nepromenjen).

## B.2 OPEN nalazi — pisači sa nasleđenom semantikom

| ID | pisač | nasleđena semantika | dokaz | posledica |
|---|---|---|---|---|
| **L-1** | `ingest_misljenja.py:160` | **sva tri obrasca odjednom**: `uuid4` ID + `except → continue` + `zip()` bez provere | `:250`, `:243-247`, `:249` | Jedini pisač koji ispunjava sva tri kriterijuma mandata. Njegovih **74 živa vektora u `misljenja`** su neizbrisivi po dokumentu i neponovljivi bez dupliranja. **Nije bio ni u jednoj ranijoj listi.** |
| **L-2** | `routers/law_upload.py:150-157` | upsert petlja hvata izuzetak i **nastavlja**; zatim `if upserted > 0 → status "done"` | `:154-158` | **G-14 iz ID-01 je i dalje OTVOREN.** Embed strana je popravljena u ID-01 (`:126 raise`), **upsert strana nije**. Zakon sa rupama se prijavljuje kao potpuno indeksiran. |
| **L-3** | `routers/batch_ingest.py:138-147` | `for j, emb in enumerate(embeddings)` — **nijedna provera dužine** prema `batch_texts`; `except → failed += n → continue`; `status="done" if processed > 0` | `:138`, `:145-147`, `:160` | Isti „delimičan ingest prijavljen kao gotov" koji je CONFIDENTIALITY-004 zatvorio na 6 pisaca. **Sedmi pisač je preskočen.** Piše u `sudska_praksa` i `misljenja`. |
| **L-4** | `drafting/playbook.py:82`, `interni_stavovi.py:76` | `uuid4().hex[:8]` u ID-u | — | Ponovni ingest duplira; brisanje moguće samo `delete_all` nad celim korisničkim namespace-om. `interni_stavovi` uz to seče `user_id[:8]`. **G-18 nepromenjen.** |
| **L-5** | `routers/auto_discovery.py:199-200` | ID = `discovery_{sha256(chunk)[:32]}` — **čist heš sadržaja, bez scope-a** | `:199` | Suprotno RULE 12: dva različita izvora sa identičnim pasusom dobijaju **isti ID** i drugi prepisuje prvi. Namespace je slobodan parametar iz `discovery_queue.namespace` (`:243`), pa upis nije ograničen na jedan korpus. |
| **L-6** | `routers/knowledge_base.py:121-123` + `:197` | upsert greška se guta, a poziv je `asyncio.create_task` bez `await` | — | API vraća `{"ok": true}` i kada vektor nikad nije nastao. Beleška postoji u bazi, ne postoji u pretrazi, korisnik ne dobija nikakav signal. |
| **L-7** | `routers/drafting.py:405-441` | `predmet_dokumenti` red **bez `content_sha256`** | grep: `content_sha256` postoji samo u `api.py` i `routers/smart_intake.py` | Treći pisač DB reda ne popunjava kolonu na kojoj počiva ceo ID-02 model. Isto važi za `routers/intake.py:318` i `routers/onboarding.py:274`. **Svaki budući backfill po `content_sha256` promašiće nacrte.** |
| **L-8** | `routers/drafting.py:412` | `storage_path = f"draft/{session_id}"` | — | Ista klasa kao G-16: labela koja nije dereferencibilna. Nacrt nikad nema artefakt → za nacrte bi kategorija **B bila prazna po konstrukciji**, kao i za ovih 43. |
| **L-9** | `diag_zpp_revizija.py:196` | dijagnostička skripta sa `idx.upsert(...)` u produkcijski indeks | — | Nije writer po nameni, jeste po efektu. |
| **L-10** | `scripts/ingest_case_law.py:347,542` | `delete(delete_all=True, namespace="sudska_praksa")` | — | 407.795 vektora, 94 % indeksa, iza jednog CLI flag-a. |

**Pisač koji nijedan raniji inventar nije prijavio, a ispunjava sve kriterijume mandata
(nasumičan ID + `except: continue` + `zip()` bez provere): `ingest_misljenja.py`.**
Njegov proizvod je merljiv — 74 `uuid4` ID-a u živom `misljenja` namespace-u.

---

# 4. ANALIZA DRIFTA (izmene nastale TOKOM ove revizije)

Nije deo baseline nalaza. Navodi se jer sadrži dva nalaza koje forenzika vidi.

**D-1 — odluka je ispravna i rešava G-04.** `verzija_dokumenta(tekst)` ujednačava heš na
*izvučeni tekst* kod sva četiri pisača (`api.py:5170`, `smart_intake.py:1346`,
`dokument.py:284`, `drafting.py:356`). Time nestaje G-04 („dva ulaza, dve vrednosti").
`EXTRACTION_VERSION` je tačno rešenje za tihu promenu parsera/OCR-a.

**D-2 — sudar ID-eva vektora koji je implementacija sama otkrila i popravila je REALAN.**
`smart_intake.py:1394` (baseline) je koristio `sha256(raw_bytes)`, a `raw_bytes` se dohvata **jednom pre
petlje po dokumentima** (`:1273`). Svi segmenti jednog posla dobijali su isti `source_sha256`,
pa od ID-01 i **identične ID-eve vektora** — drugi dokument bi `upsert`-om prepisao prvi.
Forenzika ovo **potvrđuje kao klasu problema**, uz mereno ograničenje: `intake_jobs` ima
**4 reda**, `intake_documents` **1 red**, a **0 od 43 postojeća dokumenta ima
`source_intake_job_id`** — dakle **nijedan živi podatak nije nastradao**. Regresija je bila
uvedena ID-01-om i zatvorena pre nego što je proizvela žrtvu.

**D-3 — NALAZ KOJI DRIFT NE POKRIVA: promena semantike `content_sha256` bez migracije.**
Kolona `predmet_dokumenti.content_sha256` (mig. 095) do sada je primala **64 heks znaka**
(`hashlib.sha256(...).hexdigest()`). `verzija_dokumenta` vraća **32** (`_VERZIJA_DUZINA`).
Od sada u istoj koloni mogu stajati dve nespojive vrednosti različite dužine i različitog
ulaza. Dedup upiti (`api.py:5192`, `smart_intake.py:1352`) porede `eq(...)` — stara i nova
vrednost se **nikad ne poklapaju**.
**Merena olakšica:** kolona je popunjena **0 od 43** puta, pa mešanih podataka **trenutno
nema** — prozor za ovu promenu je otvoren tačno sada. Ali `smart_intake.py:155`
(`content_sha256` **posla** = heš bajtova, 64 znaka) je **namerno ostavljen na bajtovima**,
a ime promenljive je isto. Dve različite vrednosti pod istim imenom u istom fajlu ostaju
izvor buduće zabune; `shared/vector_identity.py` to imenuje u komentaru, ali kod ne razdvaja.

**D-5 — NAJTEŽI NALAZ NAD DRIFT-om: `content_sha256` u bazi ≠ verzija u ID-u vektora.**
Drift je (u drugom talasu, `uploaded_doc/ingest.py:115-131`) premestio izvođenje verzije
u sam sink:

```
_tekst_dokumenta = "
".join(c.text for c in manifest.chunks)
_verzija         = verzija_dokumenta(_tekst_dokumenta)     # ← ide u ID VEKTORA
```

a `api.py:5170` u `predmet_dokumenti.content_sha256` upisuje

```
_content_sha256  = verzija_dokumenta(text)                 # ← ide u BAZU
```

**To nisu iste vrednosti.** `chunk_document` deli tekst sa preklapanjem
(`chunker.py:22 OVERLAP_TOKENS = 100`), pa spajanje chunk-ova **duplira preklapajući
tekst** i dodaje separatore. Mereno pravim produkcijskim `chunk_document`-om:

```
tekst od 31.600 znakova → 24 chunk-a → spojeno 36.428 znakova
  content_sha256   = eecc1760...
  verzija u ID-u   = 8255abfd...            RAZLIČITO
```

**Posledica:** `prefiks_dokumenta(predmet_id, content_sha256)` — jedini upit kojim se
vektori jednog dokumenta uopšte mogu naći — **vraća prazan skup za svaki dokument duži od
jednog chunk-a** (≈ 600 tokena / 2.400 znakova). To je brisanje po dokumentu (PINE-01),
GDPR čl. 17 i orphan detekcija — **sve tri i dalje neizvodljive, ali od sada tiho**: upit
ne puca, samo ne nalazi ništa.

**Zašto merenje nad postojećim podacima to NE pokazuje:** svih 43 dokumenta imaju
`total_chunks == 1`, a za jedan chunk je spojeni tekst jednak originalu. Mereno:
**43 od 43 se poklapa, 0 razlikuje.** Divergencija nastaje tek na prvom dokumentu
preko jednog chunk-a — dakle na prvom stvarnom pravnom dokumentu.

**Zašto testovi to ne hvataju:** `tests/test_id01_vector_identity.py:263` i `:280` sami
računaju očekivanu vrednost kao `prefiks_dokumenta("pred-A", verzija_dokumenta(_spojen))`
— dakle **iz spojenih chunk-ova, isto kao implementacija**. Test i implementacija mere
istu stranu ugovora; strana koja stoji u bazi (`content_sha256`) se ne poredi nigde.
Zelen test, prekinuta veza.

**D-4 — `routers/dokument.py:282-284` koristi `__import__("shared.vector_identity", fromlist=…)`**
umesto običnog `from … import`. Funkcionalno je isto, ali je **jedino mesto u repou** koje
dinamički razrešava ovaj modul — a AST sweep upravo takve pozive ne vidi po imenu.
Nije bug, jeste smanjena vidljivost za svaki naredni sweep.

---

# ZADATAK C — ORPHAN DOKAZNI MODEL (§15, SAMO DEFINICIJA)

**Nijedna akcija nije izvršena.** Ovo je specifikacija dokaza, ne implementacija.

Preduslov za sve slučajeve: veza vektor↔dokument mora biti **u ID-u ili u metapodacima**.
Danas je ID-01 obezbeđuje samo za vektore upisane **posle** `78ff5d73`. Za sve ranije
(30 živih `pred_*` siročadi + 407.795 `sudska_praksa` + 25.822 `zakoni_rs`) veza je
`UNKNOWN` i nijedan upit je ne može proizvesti.

| # | slučaj | **UPIT/PROVERA koja to DOKAZUJE** | **OČEKIVANA AKCIJA** |
|---|---|---|---|
| **A** | DB dokument postoji **+** vektor postoji *(upit važi tek kad se zatvori D-5)* | 1. `select id, predmet_id, content_sha256 from predmet_dokumenti`; 2. `prefiks = prefiks_dokumenta(predmet_id, content_sha256)`; 3. `Index.list(namespace=pinecone_namespace, prefix=prefiks)`; 4. **dokaz potpunosti**: `len(ids) == ingest_je_potpun` očekivani broj chunk-ova. Manje → **B, ne A**. | **KEEP** |
| **B** | DB dokument postoji **+** vektor nedostaje | Isti upit, rezultat prazan **ili nepotpun**. Dodatna grana: `status='indeksirano'` uz prazan rezultat je **teži nalaz** (baza laže) od `status='sacuvano'`. **Izmereno danas: 43 dokumenta, svi `sacuvano` — 946/946 sondi prazno.** | **REINDEX** — ako je `tekst_sadrzaj` popunjen (43/43 danas) ili artefakt postoji u Storage-u; inače **QUARANTINE**, jer bez izvora reindeks nema ulaz |
| **C** | vektor postoji **+** DB dokument nedostaje | `Index.list(namespace=…)` → parsiraj `scope` iz ID-a → `select 1 from predmeti where id = scope` **i** `select 1 from predmet_dokumenti where predmet_id = scope`. Prazno u oba = siroče. **Dokaz važi samo ako ID nosi scope**; za `uuid4` ID ovaj upit je neprimenljiv → slučaj **F**. | **DELETE** — ali tek posle potvrde da `predmeti` red nije samo soft-deleted; inače **QUARANTINE** |
| **D** | vektor postoji **+** pogrešan tenant | `Index.list(prefix=…)` daje `scope`; uporedi `predmeti.user_id`/`kancelarija_id` za taj `scope` sa vlasnikom namespace-a (`kancelarija_{id}`/`user_{id}`, `shared/kancelarija_utils.py:57-59`). Neslaganje = cross-tenant. **Za `pred_*` i `tmp_*` provera je neizvodljiva** — ti namespace-ovi ne kodiraju vlasnika. | **QUARANTINE, pa DELETE** — nikad KEEP. Cross-tenant vektor je poverljivost, ne higijena; ali brisanje bez prethodnog snimka uništava dokaz incidenta |
| **E** | vektor postoji **+** pogrešna verzija | Iz ID-a izdvoji `verzija` i `k{chunk_schema}`; uporedi sa `predmet_dokumenti.content_sha256` i `CHUNK_SCHEMA_VERSION` (`vector_identity.py:71`). Različito = zastarela verzija. **Preduslov: obe strane moraju biti na ISTOJ konvenciji heša** — v. nalaz D-3; 64-znakovna i 32-znakovna vrednost se ne mogu porediti | **DELETE stare + REINDEX tekuće**, kao jedna transakcija. Samo DELETE ostavlja dokument bez ijednog vektora; samo REINDEX ostavlja dve verzije u pretrazi |
| **F** | vektor postoji **+** nepoznat identitet | ID ne odgovara nijednom poznatom obrascu (`{scope}__{ver}__k{n}_c{i}`, `{src}__chunk_{n}`, `kb_*`, `{safe}_c{n}`, `discovery_*`, `md5`). **Izmereno: 30 `uuid4` u 6 `pred_*` + 74 `uuid4` u `misljenja` = 104 vektora u ovom stanju.** Metapodaci bi ih možda razrešili, ali njihovo čitanje vraća `text` do 40.000 znakova → to je čitanje sadržaja dokumenta, ne identiteta | **UNKNOWN → QUARANTINE.** Nikad DELETE: `misljenja` (74) je legitiman živi korpus koji samo ima loše ID-eve, a ne siroče. **Automatsko brisanje po „nepoznat ID" obrisalo bi ceo `misljenja` namespace.** Razrešenje zahteva ponovni ingest sa determinističkim ID-evima, pa `delete_all` starih — ne obrnuto |

## C.1 Šta ovaj model NE može da dokaže na zatečenom stanju

| ograničenje | posledica | zašto se ne može zaobići |
|---|---|---|
| ID-01 identitet važi samo za vektore posle `78ff5d73` | 434.217 postojećih vektora ne može se klasifikovati po A–E, samo po **F** | ID je već upisan; menjanje ID-a je novi upsert + delete, dakle akcija |
| `content_sha256` prazan na 43/43 | grane A/B/E se **ne mogu izvršiti** nad postojećim dokumentima | rekonstruisati se može (§A.3), ali upis je akcija — mandat je zabranjuje |
| 6 živih `pred_*` ne kodira vlasnika | slučaj **D** je neizvodljiv nad njima | namespace je `pred_{session_id}`, a `session_id` nije ni u jednoj tabeli |
| razlikovanje **C** od **F** zavisi od oblika ID-a | `uuid4` siroče uvek pada u F, nikad u C | iz `uuid4` se scope ne izvodi ni pod kojim upitom |
| `routers/drafting.py`, `intake.py`, `onboarding.py` ne pišu `content_sha256` | njihovi redovi su **B ili F** i posle svakog backfill-a | v. nalaz L-7 |
| `content_sha256` (heš teksta) ≠ verzija u ID-u vektora (heš spojenih chunk-ova) | **grane A, B i E su neispravne za svaki dokument > 1 chunk-a** — prefiks iz baze ne nalazi vektore koji postoje, pa se A pogrešno klasifikuje kao B | v. nalaz D-5; ovo je **preduslov za ceo model**, ne detalj |

**Redosled koji model nalaže:** F pre C (nepoznat identitet nije siroče), QUARANTINE pre
DELETE u svakom slučaju sem A, i **nijedan DELETE dok ne postoji brisač po dokumentu** —
koji, po §B.1.c, za `predmet_dokumenti` i dalje ne postoji.

---

## 5. SAŽETAK

| pitanje | odgovor | dokaz |
|---|---|---|
| Koliko dokumenata? | **43** | `count="exact"` |
| Kategorija A | **43** | `predmet_id` + `tekst_sadrzaj` na 43/43 |
| Kategorija B | **0** | original nikad nije upisan; 0 objekata u 3 bucket-a |
| Kategorija C | **0** | — |
| Kategorija D | **43** | `sacuvano` 43/43; **946/946 prefiks-sondi prazno** |
| Kategorija E | **30 vektora / 6 namespace-ova** | 0/6 odgovara DB redu ili `predmeti.id` |
| Fizičkih Pinecone upsert mesta | **19** (7 runtime + 12 batch/CLI) | AST prolaz nad 396 fajlova |
| Pisača sa nasleđenom semantikom | **10** (L-1 … L-10) | v. §B.2 |
| Najgori pojedinačni | **`ingest_misljenja.py`** — `uuid4` + `except: continue` + `zip()` bez provere, **74 živa vektora** | `:250`, `:243-247`, `:249` |
| Nalaz nad drift implementacijom (1) | **D-5** — `content_sha256` (heš teksta) ≠ verzija u ID-u vektora (heš spojenih chunk-ova sa preklapanjem). Poklapa se na 43/43 postojećih samo zato što svi imaju 1 chunk; puca na prvom dokumentu > 1 chunk-a | mereno: 31.600 zn. → 24 chunk-a → 36.428 zn. → drugi heš |
| Nalaz nad drift implementacijom (2) | **D-3** — `content_sha256` menja dužinu 64→32 bez migracije; prozor je otvoren jer je kolona prazna 0/43 | grep + `vector_identity.py:75` |

---

# DODATAK — SVIH 43 REDOVA, POJEDINAČNO

Identifikatori skraćeni na 8 znakova (§7 mandata). `storage_path` se ne ispisuje doslovno
jer sadrži `user_id` i naziv fajla — ispisuje se samo njegov OBLIK. „rekonstruisana verzija"
je `sha256("e1|" + tekst_sadrzaj)[:32]`, skraćena na 8 znakova za prikaz; ona **nije upisana
nigde** — izračunata je u memoriji radi klasifikacije i odbačena.

Kolona „vektor u Pinecone-u" = rezultat `Index.list(prefix=…)` nad **svih 11 živih
namespace-ova**, pod oba modela scope-a (`predmet_id` i `session_id`): 946 sondi, 0 pogodaka.

| # | document_id | predmet_id | status | content_sha256 | tekst_sadrzaj | pinecone_namespace | storage_path | original u Storage-u | vektor u Pinecone-u | rekonstruisana verzija | KAT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `abf8101c` | `00a56895` | sacuvano | **prazan** | da (533 zn.) | `pred_9f28d681...` | `session/...` (labela) | **NE** | **NE** | `f6339d82...` | **A + D** |
| 2 | `3ed20dae` | `00a56895` | sacuvano | **prazan** | da (527 zn.) | `pred_7d441f1c...` | `session/...` (labela) | **NE** | **NE** | `6cc189eb...` | **A + D** |
| 3 | `39b7463a` | `00a56895` | sacuvano | **prazan** | da (424 zn.) | `pred_b745d169...` | `session/...` (labela) | **NE** | **NE** | `aa51923b...` | **A + D** |
| 4 | `0d39c48a` | `0129f973` | sacuvano | **prazan** | da (533 zn.) | `pred_22e55b18...` | `session/...` (labela) | **NE** | **NE** | `f6339d82...` | **A + D** |
| 5 | `3d177a32` | `0129f973` | sacuvano | **prazan** | da (527 zn.) | `pred_3510e4d9...` | `session/...` (labela) | **NE** | **NE** | `6cc189eb...` | **A + D** |
| 6 | `67536829` | `0129f973` | sacuvano | **prazan** | da (424 zn.) | `pred_948c84ed...` | `session/...` (labela) | **NE** | **NE** | `aa51923b...` | **A + D** |
| 7 | `a93ef3df` | `01f137cf` | sacuvano | **prazan** | da (328 zn.) | `pred_fcba3203...` | `session/...` (labela) | **NE** | **NE** | `7e7c56f7...` | **A + D** |
| 8 | `f9f6c5f2` | `01f137cf` | sacuvano | **prazan** | da (265 zn.) | `pred_2013f000...` | `session/...` (labela) | **NE** | **NE** | `8700a520...` | **A + D** |
| 9 | `11d3e4a9` | `01f137cf` | sacuvano | **prazan** | da (227 zn.) | `pred_e96e7f3d...` | `session/...` (labela) | **NE** | **NE** | `6adef833...` | **A + D** |
| 10 | `0577f41e` | `01f137cf` | sacuvano | **prazan** | da (206 zn.) | `pred_b2ec64ad...` | `session/...` (labela) | **NE** | **NE** | `6b992662...` | **A + D** |
| 11 | `d363a085` | `1f909976` | sacuvano | **prazan** | da (405 zn.) | `pred_7f69cb08...` | `session/...` (labela) | **NE** | **NE** | `f1dfb14e...` | **A + D** |
| 12 | `1880fc72` | `1f909976` | sacuvano | **prazan** | da (312 zn.) | `pred_659d79d1...` | `session/...` (labela) | **NE** | **NE** | `02f28aee...` | **A + D** |
| 13 | `3828c17b` | `1f909976` | sacuvano | **prazan** | da (580 zn.) | `pred_97d0f6df...` | `session/...` (labela) | **NE** | **NE** | `b6e18244...` | **A + D** |
| 14 | `52e76915` | `26c12a60` | sacuvano | **prazan** | da (346 zn.) | `pred_00f7b374...` | `session/...` (labela) | **NE** | **NE** | `e55b7d0a...` | **A + D** |
| 15 | `b5ed492e` | `26c12a60` | sacuvano | **prazan** | da (77 zn.) | `pred_6a3c9e4c...` | `session/...` (labela) | **NE** | **NE** | `599fec9a...` | **A + D** |
| 16 | `88c36999` | `26c12a60` | sacuvano | **prazan** | da (282 zn.) | `pred_4a9b4c48...` | `session/...` (labela) | **NE** | **NE** | `545342a7...` | **A + D** |
| 17 | `72c461f5` | `47b4884e` | sacuvano | **prazan** | da (405 zn.) | `pred_4cd9edb0...` | `session/...` (labela) | **NE** | **NE** | `f1dfb14e...` | **A + D** |
| 18 | `565aaaad` | `47b4884e` | sacuvano | **prazan** | da (312 zn.) | `pred_a3829f0e...` | `session/...` (labela) | **NE** | **NE** | `02f28aee...` | **A + D** |
| 19 | `42cd5e12` | `47b4884e` | sacuvano | **prazan** | da (580 zn.) | `pred_c1d411c8...` | `session/...` (labela) | **NE** | **NE** | `b6e18244...` | **A + D** |
| 20 | `0050a23f` | `47dc4817` | sacuvano | **prazan** | da (548 zn.) | `pred_0bafd596...` | `session/...` (labela) | **NE** | **NE** | `dd541bad...` | **A + D** |
| 21 | `f77f8881` | `4f28f4b9` | sacuvano | **prazan** | da (323 zn.) | `pred_96f2ff18...` | `session/...` (labela) | **NE** | **NE** | `3a43c209...` | **A + D** |
| 22 | `c6481d9b` | `4f28f4b9` | sacuvano | **prazan** | da (370 zn.) | `pred_542411df...` | `session/...` (labela) | **NE** | **NE** | `1a3d3140...` | **A + D** |
| 23 | `8f45a0c5` | `4f28f4b9` | sacuvano | **prazan** | da (263 zn.) | `pred_5e5bf9f0...` | `session/...` (labela) | **NE** | **NE** | `eb8dd4db...` | **A + D** |
| 24 | `db85b0d1` | `4f28f4b9` | sacuvano | **prazan** | da (107 zn.) | `pred_5c27f9ef...` | `session/...` (labela) | **NE** | **NE** | `875d3881...` | **A + D** |
| 25 | `3006377a` | `6c07ab5d` | sacuvano | **prazan** | da (328 zn.) | `pred_f847a9b2...` | `session/...` (labela) | **NE** | **NE** | `7e7c56f7...` | **A + D** |
| 26 | `4f1b1afc` | `6c07ab5d` | sacuvano | **prazan** | da (265 zn.) | `pred_b0860b50...` | `session/...` (labela) | **NE** | **NE** | `8700a520...` | **A + D** |
| 27 | `b48e303a` | `6c07ab5d` | sacuvano | **prazan** | da (227 zn.) | `pred_42ee3ef6...` | `session/...` (labela) | **NE** | **NE** | `6adef833...` | **A + D** |
| 28 | `45eab367` | `6c07ab5d` | sacuvano | **prazan** | da (206 zn.) | `pred_71b0db53...` | `session/...` (labela) | **NE** | **NE** | `6b992662...` | **A + D** |
| 29 | `b7d3e1a5` | `720c36b2` | sacuvano | **prazan** | da (256 zn.) | `pred_b7d68917...` | `session/...` (labela) | **NE** | **NE** | `872fd0e8...` | **A + D** |
| 30 | `e9fba600` | `7faf7d8e` | sacuvano | **prazan** | da (323 zn.) | `pred_249b8c34...` | `session/...` (labela) | **NE** | **NE** | `3a43c209...` | **A + D** |
| 31 | `3333a2d9` | `7faf7d8e` | sacuvano | **prazan** | da (370 zn.) | `pred_3312c214...` | `session/...` (labela) | **NE** | **NE** | `1a3d3140...` | **A + D** |
| 32 | `4c8daf1a` | `7faf7d8e` | sacuvano | **prazan** | da (263 zn.) | `pred_d3e4f500...` | `session/...` (labela) | **NE** | **NE** | `eb8dd4db...` | **A + D** |
| 33 | `96901dfb` | `7faf7d8e` | sacuvano | **prazan** | da (107 zn.) | `pred_37d28107...` | `session/...` (labela) | **NE** | **NE** | `875d3881...` | **A + D** |
| 34 | `4a4ce1e5` | `87b76dc2` | sacuvano | **prazan** | da (548 zn.) | `pred_fe9835c2...` | `session/...` (labela) | **NE** | **NE** | `dd541bad...` | **A + D** |
| 35 | `a1903480` | `ab37c832` | sacuvano | **prazan** | da (548 zn.) | `pred_1f15df49...` | `session/...` (labela) | **NE** | **NE** | `dd541bad...` | **A + D** |
| 36 | `a1c4c90c` | `b3f7eae5` | sacuvano | **prazan** | da (548 zn.) | `pred_53fcb9b9...` | `session/...` (labela) | **NE** | **NE** | `dd541bad...` | **A + D** |
| 37 | `d1883f57` | `d2fb1e1f` | sacuvano | **prazan** | da (256 zn.) | `pred_c66ca31a...` | `session/...` (labela) | **NE** | **NE** | `872fd0e8...` | **A + D** |
| 38 | `c8574c9f` | `e0a54af1` | sacuvano | **prazan** | da (533 zn.) | `pred_1416c63d...` | `session/...` (labela) | **NE** | **NE** | `f6339d82...` | **A + D** |
| 39 | `456334e3` | `e0a54af1` | sacuvano | **prazan** | da (527 zn.) | `pred_7c9f7cb1...` | `session/...` (labela) | **NE** | **NE** | `6cc189eb...` | **A + D** |
| 40 | `9ec336aa` | `e0a54af1` | sacuvano | **prazan** | da (424 zn.) | `pred_7c4e88d1...` | `session/...` (labela) | **NE** | **NE** | `aa51923b...` | **A + D** |
| 41 | `96c62120` | `f4bbb99b` | sacuvano | **prazan** | da (346 zn.) | `pred_3bcace31...` | `session/...` (labela) | **NE** | **NE** | `e55b7d0a...` | **A + D** |
| 42 | `07077228` | `f4bbb99b` | sacuvano | **prazan** | da (77 zn.) | `pred_a264a4b4...` | `session/...` (labela) | **NE** | **NE** | `599fec9a...` | **A + D** |
| 43 | `814e386a` | `f4bbb99b` | sacuvano | **prazan** | da (282 zn.) | `pred_95afbd3a...` | `session/...` (labela) | **NE** | **NE** | `545342a7...` | **A + D** |

**43/43 = kategorija A (identitet rekonstruktivan) + kategorija D (ingest nikad potvrđen).**
Nijedan red nije B, nijedan nije C. Nijedan od ovih 43 nije E — E su vektori bez reda, a ne
redovi bez vektora.

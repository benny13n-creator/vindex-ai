# BETA-DATA-ID-02 — Klasifikacija svih postojećih vektora (§6, §7, §8)

**Baseline:** `78ff5d73`
**Datum merenja:** 2026-08-13
**Indeks:** `vindex-ai` (serverless, aws/us-east-1, `dimension=3072`), klijent `pinecone==8.1.1`

**Metod — samo čitanje.** Prema Pinecone-u pozvani su isključivo `describe_index_stats()`,
`Index.list()` (vraća samo ID-eve) i `fetch()` po ID-u. **Nijedan `upsert`, `delete`,
`delete_all` ni re-ingest nije izvršen.** Prema Supabase-u isključivo `select(...)`.
Nijedan produkcijski fajl, test ni migracija nisu menjani.

**Higijena podataka.** Sadržaj klijentskih dokumenata (`text`, `tekst`, `sadrzaj`) nije
ispisan nigde u ovom izveštaju — beleži se samo PRISUSTVO ključa i dužina u znakovima.
Kredencijali nisu ispisani.

**Pravilo dokaza.** Svaka tvrdnja nosi izmereni izlaz ili `fajl:linija`. Gde dokaza nema —
`UNKNOWN`. Heuristika je zabranjena; nijedan ID nije svrstan „po osećaju".

> **Napomena o radnom stablu.** U trenutku merenja radno stablo NIJE čisto na `78ff5d73`:
> `git status` prijavljuje `M api.py`, `M routers/dokument.py`, `M routers/drafting.py`,
> `M routers/smart_intake.py`, `M shared/vector_identity.py` — izmene drugog agenta koje
> ovaj izveštaj nije dodirnuo. To ne utiče na merenja: sva merenja su nad ŽIVIM stanjem
> Pinecone-a i Supabase-a, ne nad radnim stablom.

---

## 0. Sažetak

| Pitanje | Odgovor |
|---|---|
| Ukupno vektora | **434.217** (potpun popis, ne uzorak) |
| Namespace-ova | **11** |
| Vektora u NOVOM ID-01 modelu (`{scope}__{verzija}__k{n}_c{i}`) | **0** |
| Vektora sa `predmet_id` u metapodacima | **0** |
| Vektora sa `vx_scope` / `vx_verzija` / `vx_chunk_schema` | **0** |
| Vektora sa bilo kakvim hešom izvora u metapodacima | **0** |
| UNKNOWN obrazac ID-a (posle dokazane rezolucije) | **0** |
| Vektora KLIJENTSKIH dokumenata | **30** |
| Od toga dokazano vezanih za DB red (BOUND) | **0** |
| Od toga ORPHAN | **30** |
| Vektora javnog pravnog sadržaja | **434.187** |

---

## 1. KORAK 0 — Verifikacija zatečenih brojeva

Brojevi iz mandata nisu uzeti na reč; ponovo su izmereni `describe_index_stats()`-om.

```
DIMENSION: 3072
TOTAL:     434217
NAMESPACES: 11
  sudska_praksa                          407795
  zakoni_rs                               25822
  web3_zdi_mca                              479
  misljenja                                  74
  carf_dac8                                  17
  pred_dfe8d28812144d80a19b58ca76ca95d8        5
  pred_26904a63c3134f708c55f2f913fa40b6        5
  pred_c41b9afc28c04349ba98fd515a23626f        5
  pred_17d3edb4c74847109a58bd23b1385dcc        5
  pred_7d7e8e141e0a45f3995a3b6d0bdb7c21        5
  pred_c326f5bbddbd4a578c6fc534b6fec981        5
```

**Zaključak: svi brojevi iz mandata su POTVRĐENI**, uključujući 6 × `pred_*` sa ukupno 30
vektora. Nijedan `kancelarija_*`, `user_*`, `tmp_*`, `kb_*`, `playbook_*` ni
`interni_stavovi_*` namespace ne postoji uživo.

---

## 2. KORAK 1 — Klasifikator obrazaca ID-a (§7)

### 2.1 Obrasci i njihovi pisači

Svaki obrazac je vezan za konkretnog pisača u repou. Obrazac bez dokazanog pisača se ne
uvodi.

| # | Obrazac | Regex | Pisač |
|---|---|---|---|
| 1 | `ID01_NEW` | `^[A-Za-z0-9_.\-]+__[A-Za-z0-9_.\-]{1,32}__k\d+_c\d+$` | `shared/vector_identity.py::canonical_vector_id` |
| 2 | `CASE_LAW__chunk_` | `^.+__chunk_\d+$` | `chunker_case_law.py:279` |
| 3 | `MD5_BARE_32` | `^[0-9a-f]{32}$` | `semantic_chunker.py:107` — `md5("v2\|{zakon}\|{clan}\|{stav}")` |
| 4 | `KB_uid_beleska` | `^kb_[0-9a-fA-F\-]{36}_[0-9a-fA-F\-]{36}$` | `routers/knowledge_base.py:107` |
| 5 | `DISCOVERY_sha256` | `^discovery_[0-9a-f]{32}$` | `routers/auto_discovery.py:199` |
| 6 | `LAW_UPLOAD_cN` | `^[A-Za-z0-9_.\-]+_c\d+$` | `routers/law_upload.py:137` |
| 7 | `UUID4_BARE` | `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` | `uploaded_doc/chunker.py:157` (`str(uuid.uuid4())`), `ingest_misljenja.py:250` |
| 8 | `UUID_NON_V4` | UUID bilo koje druge verzije | nepoznat pisač |
| 9 | `WEB3_slug_chunk_N` | `^[A-Za-z0-9_.\-]+_chunk_\d+$` | `scrape_zdi_mca.py:165,188`, `scripts/ingest_web3_addendum.py:39` |
| 10 | `GLOSSARY_colon` | `^[A-Za-z0-9_.\-]+(::[A-Za-z0-9_.\-]+)+$` | `ingest_glossary_vasp_casp.py:18` |
| 11 | `CURATED_LITERAL` | tačan skup literala izvučen `ast`-om iz izvora | `scripts/ingest_carf_dac8.py`, `scripts/ingest_web3_addendum.py`, `scrape_zdi_mca.py` |

Klasifikator proverava SVE obrasce i beleži svaki višestruki pogodak; razrešenje ide po
fiksnom prioritetu (specifičniji pobeđuje), a ne po redosledu u kodu.

### 2.2 Negativne kontrole — DOKAZ, ne tvrdnja

Klasifikator je pokrenut nad 12 kontrolnih ulaza. Za svaki je definisano i šta MORA da
pogodi i koji obrasci NE SMEJU da pogode. Izmereni izlaz:

```
[OK ] '7f3a1c2e-9b4d-4a1f-8c2e-1122334455aa'          -> UUID4_BARE        pogodaka=['UUID4_BARE','UUID_NON_V4']
[OK ] 'Rev-1234-2019__chunk_7'                        -> CASE_LAW__chunk_  pogodaka=['CASE_LAW__chunk_','WEB3_slug_chunk_N']
[OK ] 'd41d8cd98f00b204e9800998ecf8427e'              -> MD5_BARE_32       pogodaka=['MD5_BARE_32']
[OK ] 'kb_<uuid>_<uuid>'                              -> KB_uid_beleska    pogodaka=['KB_uid_beleska']
[OK ] 'discovery_0123456789abcdef0123456789abcdef'    -> DISCOVERY_sha256  pogodaka=['DISCOVERY_sha256']
[OK ] 'zakon-o-radu_c12'                              -> LAW_UPLOAD_cN     pogodaka=['LAW_UPLOAD_cN']
[OK ] 'pred123__ab12...cd34__k1_c0'                   -> ID01_NEW          pogodaka=['ID01_NEW','LAW_UPLOAD_cN']
[OK ] 'mica_casp_chunk_3'                             -> WEB3_slug_chunk_N pogodaka=['WEB3_slug_chunk_N']
[OK ] 'ZDI::cl_56::alias_glossary::chunk_0'           -> GLOSSARY_colon    pogodaka=['GLOSSARY_colon']
[OK ] 'carf_section1_obligations'                     -> CARF_DAC8_SLUG    pogodaka=['CARF_DAC8_SLUG']
[OK ] 'neki nasumican string bez obrasca'             -> UNKNOWN           pogodaka=[]
[OK ] ''                                              -> UNKNOWN           pogodaka=[]
=== REZULTAT: SVE PROSLO ===
```

Traženi dokazi su eksplicitno zadovoljeni:

- **uuid4 NE ulazi u `__chunk_` obrazac** — `pogodaka` za uuid4 ne sadrži `CASE_LAW__chunk_`.
- **`__chunk_` ID NE ulazi u uuid4 obrazac** — `pogodaka` za `Rev-1234-2019__chunk_7` ne
  sadrži `UUID4_BARE`.
- Prazan string i nasumičan tekst daju `UNKNOWN`, a ne „najbliži" obrazac.

### 2.3 Priznata preklapanja (ne skrivena)

Klasifikator je izmerio dva sistematska preklapanja i razrešio ih prioritetom. Prijavljuju
se otvoreno, jer bi prećutkivanje bilo isto što i heuristika:

| Preklapanje | Broj vektora | Razrešenje | Obrazloženje |
|---|---|---|---|
| `CASE_LAW__chunk_` ∧ `WEB3_slug_chunk_N` | 407.795 | → `CASE_LAW__chunk_` | `__chunk_` (dvostruka donja crta) je uži slučaj od `_chunk_`; oba pravila su iz koda, ali samo `chunker_case_law.py:279` piše u `sudska_praksa` |
| `UUID4_BARE` ∧ `UUID_NON_V4` | 104 | → `UUID4_BARE` | v4 je specijalizacija generičkog UUID oblika |

`ID01_NEW` takođe pogađa `LAW_UPLOAD_cN` (oba se završavaju na `_c{n}`); prioritet daje
`ID01_NEW`. Uticaj na merenje: **nula, jer nijedan živi vektor nije `ID01_NEW`.**

### 2.4 Rezolucija 3 UNKNOWN vektora — dokazom, ne pretpostavkom

Regex prolaz je ostavio **3 UNKNOWN** ID-a u `web3_zdi_mca`:

```
zdi_b2b_razmena_vodic
zdi_barter_vs_placanje_distinkcija
zdi_crossborder_vodic
```

Umesto nagađanja, izvorni kod je parsiran `ast`-om i izvučeni su svi literalni `"id"`
stringovi iz kuratorskih ingest skripti:

```
scripts/ingest_carf_dac8.py       17 literala
scripts/ingest_web3_addendum.py    5 literala  (uključuje sva 3 gornja)
scrape_zdi_mca.py                  9 literala
ingest_glossary_vasp_casp.py       0  (ID je u konstanti CHUNK_ID, ne u dict literalu)
```

Sva 3 ID-a su **doslovno prisutna** u `scripts/ingest_web3_addendum.py:72,107,136`. Time
su svrstana u `CURATED_LITERAL` na osnovu dokaza o pisaču, a ne obrasca. Isti dokaz
pokriva i 17 `carf_dac8` vektora (17 literala ↔ 17 vektora, tačno poklapanje).

**Preostali UNKNOWN posle rezolucije: 0.**

---

## 3. KORAK 2 — Brojevi, ne utisci (§6)

### 3.1 Pokrivenost merenja

`Index.list()` je nabrojao **SVAKI** ID u **SVAKOM** namespace-u — ovo NIJE uzorak.

```
declared_total 434217   listed_total 434217   poklapanje: True
```

Svaki namespace pojedinačno: `listed == declared`. Nema propuštenih stranica.

### 3.2 Tabela namespace × obrazac ID-a × broj (POTPUN POPIS)

| Namespace | Vektora | `CASE_LAW__chunk_` | `MD5_BARE_32` | `WEB3_slug_chunk_N` | `UUID4_BARE` | `CURATED_LITERAL` | `GLOSSARY_colon` | `ID01_NEW` | UNKNOWN |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `sudska_praksa` | 407.795 | **407.795** | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `zakoni_rs` | 25.822 | 0 | **25.818** | 0 | 0 | 0 | **4** | 0 | 0 |
| `web3_zdi_mca` | 479 | 0 | 0 | **476** | 0 | **3** | 0 | 0 | 0 |
| `misljenja` | 74 | 0 | 0 | 0 | **74** | 0 | 0 | 0 | 0 |
| `carf_dac8` | 17 | 0 | 0 | 0 | 0 | **17** | 0 | 0 | 0 |
| `pred_dfe8d288…` | 5 | 0 | 0 | 0 | **5** | 0 | 0 | 0 | 0 |
| `pred_26904a63…` | 5 | 0 | 0 | 0 | **5** | 0 | 0 | 0 | 0 |
| `pred_c41b9afc…` | 5 | 0 | 0 | 0 | **5** | 0 | 0 | 0 | 0 |
| `pred_17d3edb4…` | 5 | 0 | 0 | 0 | **5** | 0 | 0 | 0 | 0 |
| `pred_7d7e8e14…` | 5 | 0 | 0 | 0 | **5** | 0 | 0 | 0 | 0 |
| `pred_c326f5bb…` | 5 | 0 | 0 | 0 | **5** | 0 | 0 | 0 | 0 |
| **UKUPNO** | **434.217** | **407.795** | **25.818** | **476** | **104** | **20** | **4** | **0** | **0** |

4 `GLOSSARY_colon` ID-a u `zakoni_rs` su: `ZDI::cl_56::alias_glossary::chunk_0`,
`ZOO::cl_110::chunk_0`, `ZPDG::cl_64::chunk_0`, `ZPDG::cl_77::chunk_0`.

**Obrasci sa nula živih vektora** (pisač postoji u kodu, produkt ne postoji u indeksu):
`ID01_NEW` (0), `KB_uid_beleska` (0), `DISCOVERY_sha256` (0), `LAW_UPLOAD_cN` (0),
`UUID_NON_V4` (0 razrešeno).

### 3.3 Metapodaci — uzorak, jasno označen

`fetch()` je pozvan po namespace-u. Za 8 malih namespace-ova uzorak je **potpun popis**;
za 3 velika je **uzorak od 100 vektora**, što je izričito naznačeno.

| Namespace | Veličina uzorka | Pun popis? | `predmet_id` | `vx_scope`/`vx_verzija`/`vx_chunk_schema` | `chunk_index` | heš izvora | `user_id` |
|---|---:|:--:|---:|---:|---:|---:|---:|
| `sudska_praksa` | **100 / 407.795 (UZORAK)** | ne | 0 | 0 | 100 | 0 | 0 |
| `zakoni_rs` | **100 / 25.822 (UZORAK)** | ne | 0 | 0 | 0 | 0 | 0 |
| `web3_zdi_mca` | **100 / 479 (UZORAK)** | ne | 0 | 0 | 0 | 0 | 0 |
| `misljenja` | 74 / 74 | **da** | 0 | 0 | 74 | 0 | 0 |
| `carf_dac8` | 17 / 17 | **da** | 0 | 0 | 0 | 0 | 0 |
| 6 × `pred_*` | 30 / 30 | **da** | **0** | **0** | **30** | **0** | **0** |

Ključevi metapodataka po namespace-u (samo imena ključeva; vrednosti nisu ispisane):

- `pred_*` — `article_label, chunk_index, chunk_mode, expires_at, session_id,
  source_filename, source_format, text, token_count`
- `sudska_praksa` — `chunk_index, chunk_total, cited_articles_normalized,
  cited_articles_raw, court, decision_date, decision_id_fallback, decision_number,
  doc_type, matter, registrant, section, source_url, text`
- `zakoni_rs` — `article, clan, jurisdiction, law, parent_id, parent_text, source_type,
  stav, tekst_preview, text, zakon`
- `misljenja` — `broj, chunk_index, datum, ministarstvo, naziv, oblast, source, text, tip, url`
- `carf_dac8` / `web3_zdi_mca` — `izvor, naslov, propis, tekst, tip`

### 3.4 Ukupni brojevi po traženim kategorijama

| Kategorija | Broj | Osnov |
|---|---:|---|
| NOVI model (ID-01) | **0** | potpun popis, nijedan ID ne pogađa `ID01_NEW` |
| LEGACY (svi ostali prepoznati obrasci) | **434.217** | potpun popis |
| UNKNOWN | **0** | 3 regex-UNKNOWN razrešena `ast` dokazom |
| ORPHAN (klijentski vektori bez DB reda) | **30** | §4 |
| AMBIGUOUS | **0** | §4 |
| Sa `predmet_id` | **0** | potpun popis nad `pred_*`+`misljenja`+`carf_dac8`, uzorak 100 nad ostalima |
| Sa hešom izvora | **0** | isto |
| Sa `vx_*` | **0** | isto |

> **Ograničenje uzorka — izričito.** Za `sudska_praksa`, `zakoni_rs` i `web3_zdi_mca`
> tvrdnja „0 vektora ima `predmet_id`/`vx_*`/heš" počiva na uzorku od 100 vektora po
> namespace-u, ne na potpunom popisu metapodataka. To je **procena**, ne merenje. Procena
> je potkrepljena kodom: pisači ta tri korpusa (`chunker_case_law.py:279`,
> `semantic_chunker.py`, `scrape_zdi_mca.py`, `scripts/ingest_web3_addendum.py`) nemaju
> nijedan `predmet_id`, `vx_*` ni heš u metapodacima. Za 30 klijentskih vektora, koji
> jedini nose rizik, tvrdnja je **potpun popis** — nije procena.

---

## 4. KORAK 3 — Veza sa bazom (§8)

### 4.1 Merenje nad Supabase-om (samo `select`)

```
predmet_dokumenti — ukupno redova            : 43
predmet_dokumenti — distinct pinecone_namespace : 43
predmet_dokumenti — redova sa content_sha256 : 0
predmeti — ukupno redova                     : 19
DB namespace-ova sa prefiksom pred_          : 43   (svi)
DB pred_ namespace-ova koji POSTOJE u Pinecone-u : 0
DB pred_ sufiksa koji jesu predmeti.id       : 0 od 43
```

### 4.2 Klasifikacija 6 živih `pred_*` namespace-ova

| Namespace | Vektora | Red u `predmet_dokumenti`? | Sufiks == `predmeti.id`? | `predmet_id` u metapodacima? | Klasifikacija |
|---|---:|:--:|:--:|:--:|---|
| `pred_dfe8d28812144d80a19b58ca76ca95d8` | 5 | **ne (0 redova)** | ne | **ne** | **ORPHAN** |
| `pred_26904a63c3134f708c55f2f913fa40b6` | 5 | **ne (0 redova)** | ne | **ne** | **ORPHAN** |
| `pred_c41b9afc28c04349ba98fd515a23626f` | 5 | **ne (0 redova)** | ne | **ne** | **ORPHAN** |
| `pred_17d3edb4c74847109a58bd23b1385dcc` | 5 | **ne (0 redova)** | ne | **ne** | **ORPHAN** |
| `pred_7d7e8e141e0a45f3995a3b6d0bdb7c21` | 5 | **ne (0 redova)** | ne | **ne** | **ORPHAN** |
| `pred_c326f5bbddbd4a578c6fc534b6fec981` | 5 | **ne (0 redova)** | ne | **ne** | **ORPHAN** |
| **UKUPNO** | **30** | — | — | — | **30 ORPHAN, 0 BOUND, 0 AMBIGUOUS, 0 UNKNOWN** |

### 4.3 Zašto ORPHAN, a ne AMBIGUOUS — lanac dokaza

`AMBIGUOUS` bi značilo „metapodaci ne dozvoljavaju ni potvrdu ni poricanje". Ovde nije
tako: **ključ za spajanje postoji i pretraga po njemu vraća nulu.**

1. Pisač `606f3a29` (`fix(dokumenti): trajno cuvanje — pred_ namespace`) je u ISTOJ
   transakciji pisao Pinecone namespace `pred_{session_id}` i DB kolonu
   `predmet_dokumenti.pinecone_namespace = f"pred_{session_id}"`. Dakle za svaki živi
   `pred_*` namespace red u bazi **MORA da postoji po dizajnu**.
2. `session_id` je `uuid.uuid4().hex` (`uploaded_doc/session.py:7`) — 32 znaka bez crtica.
   Izmereno: svih 6 sufiksa je dužine tačno 32. Šema se poklapa.
3. Metapodaci svih 30 vektora nose `session_id` čija je vrednost identična sufiksu
   namespace-a — dakle ključ za spajanje je prisutan i nedvosmislen.
4. Pretraga tog ključa u `predmet_dokumenti.pinecone_namespace` (43 reda, iscrpno) vraća
   **0 pogodaka za svih 6**.
5. Kontrolna provera druge moguće šeme (`pred_{predmet_id}`): nijedan sufiks nije
   `predmeti.id` (0 od 19 predmeta), pa ni ta grana ne veže.
6. Nijedna tabela u `migrations/*.sql` ni `supabase_setup.sql` ne čuva `session_id` kao
   kolonu, pa ne postoji ni treće mesto gde bi vezа mogla da postoji.

Zaključak je **poricanje dokazano pretragom**, ne odsustvo podatka → **ORPHAN**.

### 4.4 Vektori sa `predmet_id` u metapodacima

**Nema ih — 0.** Nijedan od 30 klijentskih vektora ne nosi `predmet_id`, a ni jedan vektor
u uzorcima javnih korpusa. Provera „da li DB red postoji za `predmet_id`" je stoga prazna
po ulazu, ne po izlazu.

### 4.5 Šta NIJE zaključeno (zabrane iz mandata poštovane)

- **Nije zaključeno „namespace = dokument".** 6 namespace-ova nije prijavljeno kao 6
  dokumenata; prijavljeno je 6 namespace-ova sa 30 vektora.
- **Nije zaključeno „ime fajla = identitet".** Metapodatak `source_filename` ima **identičnu
  vrednost u svih 6 namespace-ova**. To je zabeleženo kao činjenica, ali iz toga **NIJE**
  izvedeno da je reč o istom dokumentu, istom korisniku, ni o duplikatima. Bez heša
  sadržaja (kog nema — v. §3.3) identitet dokumenta je **UNKNOWN**.
- **Nije zaključeno „sličnost = isti dokument".** Nijedno poređenje embedding-a nije
  izvršeno.

### 4.6 Izvedeni nalaz: veza DOKUMENT → VEKTOR je prekinuta u OBA smera

| Smer | Merenje | Posledica |
|---|---|---|
| DB → Pinecone | 43 reda u `predmet_dokumenti` pokazuju na 43 namespace-a; **0 ih postoji u Pinecone-u** | Svaki dokument u bazi tvrdi da ima vektore kojih nema |
| Pinecone → DB | 6 živih `pred_*` namespace-ova; **0 ih ima red u bazi** | 30 vektora klijentskog sadržaja bez ijednog vlasnika |

Za GDPR čl. 17 to znači: brisanje pokrenuto iz aplikacije (koje ide preko
`predmet_dokumenti.pinecone_namespace`) **ne može da dohvati nijedan od ovih 30 vektora**,
jer nijedan od njih nije naveden ni u jednom DB redu.

---

## 5. KORAK 4 — Razdvajanje javnih korpusa od klijentskih podataka

### 5.1 Klasifikacija namespace-ova

| Namespace | Vektora | Priroda sadržaja | Dokaz | GDPR čl. 17? |
|---|---:|---|---|:--:|
| `sudska_praksa` | 407.795 | **JAVNO** — objavljene sudske odluke | metapodaci `court, decision_number, decision_date, source_url, registrant`; pisač `chunker_case_law.py` sa `doc_type="sudska_praksa"` | ne |
| `zakoni_rs` | 25.822 | **JAVNO** — tekst propisa RS | metapodaci `zakon, clan, stav, law, jurisdiction, source_type`; pisač `semantic_chunker.py` | ne |
| `web3_zdi_mca` | 479 | **JAVNO** — MiCA i ZDI, kuratorski vodiči | metapodaci `izvor, propis, naslov, tip`; pisači `scrape_zdi_mca.py`, `scripts/ingest_web3_addendum.py` | ne |
| `misljenja` | 74 | **JAVNO** — mišljenja ministarstava | metapodaci `ministarstvo, broj, datum, oblast, url` | ne |
| `carf_dac8` | 17 | **JAVNO** — OECD CARF / EU DAC8 | metapodatak `izvor` = „OECD (2023) CARF, Part I…" | ne |
| **6 × `pred_*`** | **30** | **KLIJENTSKI** — otpremljeni dokument predmeta | metapodaci `source_filename` (.pdf), `source_format`, `session_id`; pisač `uploaded_doc/ingest.py` preko korisničkog upload-a | **DA** |

**Ukupno javno: 434.187. Ukupno klijentski: 30.**

### 5.2 Zašto je razdvajanje pouzdano, a ne stvar imena namespace-a

Razdvajanje ne počiva na imenu namespace-a nego na dva nezavisna merenja:

1. **Poreklo pisača.** Pet javnih korpusa piše `scripts/`/`ingest_*.py`/`scrape_*.py` —
   batch skripte koje se pokreću ručno nad javnim izvorima, bez ijednog korisničkog
   zahteva. `pred_*` piše `uploaded_doc/ingest.py`, pozvan isključivo iz HTTP upload
   rute autentifikovanog korisnika.
2. **Oblik metapodataka.** Nijedan javni korpus nema `session_id`, `source_filename` ni
   `source_format`; svih 30 `pred_*` vektora ima sva tri. Obrnuto, nijedan `pred_*` vektor
   nema `url`, `izvor`, `court` ni `ministarstvo` — polja javne provenijencije.

Presek ta dva skupa je prazan, pa nema graničnih slučajeva.

### 5.3 Posledica za brisanje

Javnih 434.187 vektora **nisu predmet GDPR brisanja** i **ne smeju** se mešati sa
klijentskim vektorima ni u jednoj operaciji čišćenja. Svaka buduća `delete` operacija mora
biti ograničena na namespace-ove sa prefiksom `pred_` (i buduće `ID01_NEW` scope-ove),
nikad na `delete_all` nad indeksom.

---

## 6. Nalazi

| # | Nalaz | Ozbiljnost | Dokaz |
|---|---|---|---|
| **ID02-001** | 30 vektora klijentskog dokumenta je ORPHAN — nijedan nema DB red, nijedan nema `predmet_id` ni `user_id` | **KRITIČNO** | §4.2, §4.3 — potpun popis |
| **ID02-002** | Nijedan živi vektor ne koristi novi ID-01 model; `shared/vector_identity.py` ima 0 produkata u indeksu | **VISOKO** | §3.2 — potpun popis, `ID01_NEW = 0` |
| **ID02-003** | Nijedan vektor u indeksu (u granicama merenja) nema heš izvora u metapodacima; `predmet_dokumenti.content_sha256` je NULL u svih 43 reda | **VISOKO** | §3.3, §4.1 |
| **ID02-004** | Veza DOKUMENT→VEKTOR prekinuta u oba smera: 43 DB reda pokazuju u prazno, 6 živih namespace-ova bez vlasnika | **KRITIČNO** | §4.6 |
| **ID02-005** | 104 vektora nose nedeterministički `uuid4` ID (30 klijentskih + 74 `misljenja`) — ponovni ingest bi duplirao umesto da prepiše | **SREDNJE** | §3.2 |
| **ID02-006** | 3 vektora nose ID koji nijedan obrazac ne prepoznaje; razrešeni tek `ast` čitanjem izvora, što znači da automatska klasifikacija bez izvornog koda nije moguća | **NISKO** | §2.4 |
| **ID02-007** | Identitet dokumenta iza 6 `pred_*` namespace-ova je **UNKNOWN** — `source_filename` je identičan u svih 6, ali bez heša sadržaja se ne sme tvrditi da je reč o istom dokumentu | **NISKO (informativno)** | §4.5 |

---

## 7. Šta ovaj izveštaj NE tvrdi

- Ne tvrdi da su 30 orphan vektora bezbedni za brisanje. Utvrđuje samo da nemaju vlasnika.
  Odluka o brisanju nije u opsegu ove misije i ovde nije doneta.
- Ne tvrdi ništa o metapodacima 433.996 vektora u tri velika namespace-a koji nisu bili u
  uzorku od 100. Ta tvrdnja je označena kao **procena** (§3.4).
- Ne tvrdi da su 6 `pred_*` namespace-ova isti dokument, isti korisnik, ni duplikati.
- Ne tvrdi da je bilo šta popravljeno. **Nijedna izmena nije izvršena.**

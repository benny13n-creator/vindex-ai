# PINE-02 — LEGACY MAPPING: 43 DOKUMENTA, 30 ORPHAN VEKTORA

```
BASELINE:              053c3cc4
REŽIM:                 READ-ONLY
PRODUCTION MUTATIONS:  0   — nijedan UPDATE, DELETE, upsert, reindex, migracija
IZMENJENIH PRODUKCIJSKIH FAJLOVA: 0
NOVIH FAJLOVA:         2   — ovaj izveštaj + plan SQL-a (nije izvršen)
```

---

# VERDIKT

## 🟡 YELLOW — backfill je bezbedan kao PODATAK, ali menja PONAŠANJE

| Pitanje | Odgovor |
|---|---|
| Koliko od 43 je `RECONSTRUCTABLE`? | **43 / 43** |
| Koliko od 30 orphana je dokazivo mapirano? | **0 / 30** — svih 30 `ORPHAN_UNIDENTIFIABLE` |
| Je li ijedan `tekst_sadrzaj` skraćen na 100 000? | **NE — 0 / 43.** Najduži je **580** znakova |
| Koliko redova je `SAFE` za upis? | **43 / 43 SAFE**, 0 `UNSAFE` |
| Je li bezbedno popuniti `content_sha256`? | **DA za vrednost, NE bez odluke o posledici** — v. PINE02-F1 |

Jedan nalaz je nov i nije ga imao nijedan raniji sprint: upis ove kolone nije
neutralan. `routers/smart_intake.py:1376` koristi baš tu kolonu kao kapiju, a
izmereno je da **svih 19 različitih sadržaja već postoji u ≥2 predmeta**. Dok je
kolona prazna, ta kapija je mrtva. Čim se popuni, ona oživi.

---

# §1 — MAPIRANJE 43 DOKUMENTA

## Izmereno stanje

```
redova u predmet_dokumenti:        43     (verifikovano, ne pretpostavljeno)
tekst_sadrzaj NULL:                 0
tekst_sadrzaj prazan string:        0
dužina teksta:                     77 – 580 znakova
redova na granici 100 000:          0
redova ≥ 99 000:                    0
content_sha256 popunjen:            0     (NULL na 43/43, ne prazan string)
status:                            'sacuvano' 43/43
storage_path:                      'session/{id}' 43/43
pinecone_namespace:                'pred_{id}' 43/43, svih 43 RAZLIČITIH
različitih predmet_id:             17
različitih user_id:                 1
različitih naziva fajla:           19
različitih kanonskih identiteta:   19
created_at raspon:                 2026-07-18 → 2026-07-21  (3 dana)
```

## Kako je identitet izračunat

Isključivo pozivom produkcijske funkcije, bez ijedne sopstvene implementacije
heša:

```python
from shared.vector_identity import verzija_dokumenta, canonical_vector_id, prefiks_dokumenta
verzija = verzija_dokumenta(red["tekst_sadrzaj"])          # EXTRACTION_VERSION = 1
prefiks = prefiks_dokumenta(red["predmet_id"], verzija)     # {scope}__{verzija}__k1_c
vid     = canonical_vector_id(red["predmet_id"], verzija, 0)
```

Broj očekivanih vektora nije procenjen nego **izmeren produkcijskim chunker-om**:
`chunk_document(tekst)` je pokrenut nad sva 43 teksta →
**`total_chunks == 1` na 43/43**. Zato je očekivani skup ID-eva tačno jedan
vektor po dokumentu, `…__k1_c0`, i ništa više.

## Zašto RECONSTRUCTABLE za svih 43

Sva četiri ulaza u identitet stoje u samom redu baze:

| Ulaz | Odakle | Nedostaje ijednom redu? |
|---|---|---|
| `tekst` | `predmet_dokumenti.tekst_sadrzaj` | ne — 43/43 popunjen |
| `scope` | `predmet_dokumenti.predmet_id` | ne — 43/43 popunjen |
| `chunk_index` | 0 (izmereno `total_chunks == 1`) | ne |
| `chunk_schema` | `CHUNK_SCHEMA_VERSION = 1`, konstanta | ne |

Nijedna vrednost ne traži originalni fajl, nijedna ne koristi similarity, ime
fajla, veličinu ni datum. **Nema nijednog reda sa nedoumicom**, pa nema nijednog
`NOT_RECONSTRUCTABLE`.

## §2 — DVE RAZLIČITE TVRDNJE, RAZDVOJENE

Ovo je najvažnija granica u celom izveštaju i ne sme se stopiti u jednu rečenicu.

| | Tvrdnja | Status |
|---|---|---|
| **T1** | *Kanonski identitet svakog od 43 dokumenta može se izračunati danas, deterministički, iz podataka koji već stoje u bazi.* | **DOKAZANO** — 43/43 |
| **T2** | *Istorijski Pinecone vektor tog dokumenta je dobio taj ID.* | **OBORENO** — nijedan takav vektor ne postoji, pa ni tvrdnja nema predmet |

T2 nije „nedokazana" nego **oborena**, i to trostruko:

1. **Nijedan od 43 `pinecone_namespace` ne postoji u Pinecone-u.** Indeks ima 11
   namespace-ova; presek sa 43 iz baze je **prazan**.
2. **516 sondi po prefiksu — 0 pogodaka.** Za svaki dokument je
   `Index.list(prefix=…)` pokrenut u njegovom sopstvenom namespace-u **i u svih
   11 živih**. Nijedna nije vratila ijedan ID.
3. **Obrnut smer je isto prazan.** Generisano je 430 kanonskih ID-eva
   (43 dokumenta × chunk 0–9); presek sa 30 postojećih klijentskih vektora je **0**.

Uzrok je pronađen u istoriji koda, ne pretpostavljen: `status = 'sacuvano'` na
43/43 znači da je u tadašnjem `api.py` (`7328c5d3:api.py:3893`) izvršena grana
`_pinecone_ok = False` — **ingest u Pinecone je pao za sva 43**. Zato vektori ne
postoje. Nisu obrisani; nikad nisu ni upisani.

> Praktična posledica: upisati `content_sha256` znači upisati identitet
> dokumenta, **ne** adresu postojećih vektora. Nijedan vektor time ne postaje
> obrisiv, jer nijedan ne postoji.

## §Pitanje skraćivanja — `text[:100_000]`

**Nijedan od 43 nije skraćen. 0 na granici, 0 iznad 99 000, najduži 580 znakova.**

Provereno je i da to važi za pisač koji je te redove stvarno napravio, ne samo za
današnji kod. Oba istorijska pisača u trenutku nastanka redova
(`7328c5d3:api.py:3902` i `7328c5d3:routers/smart_intake.py:545`) upisuju
`text[:100_000]` — **istu promenljivu `text`** koja je prosleđena
`chunk_document(text, …)`. Dakle za tekstove ispod 100 000 znakova stoji u bazi
tačno ono što je išlo u chunker.

### Ipak, jedna kalibracija koju ne prećutkujem

`velicina_kb` je **35–36 KB na svih 43**, a `tekst_sadrzaj` je **77–580 znakova**.
Odnos bajtova fajla prema znakovima teksta je 60–450×. Za PDF to nije samo po
sebi anomalija (režijski deo formata), ali **ne mogu to ni dokazati ni oboriti**:
`storage_path` je labela `session/{id}`, a `storage.list("session")` nad oba
bucket-a vraća **0 objekata** — original ne postoji, pa ponovna ekstrakcija nije
moguća.

Tačna formulacija koja se sme braniti:

> `tekst_sadrzaj` je **dokazano ceo tekst koji je aplikacija tada izvukla i
> prosledila chunker-u**. Da li je taj tekst bio ceo sadržaj fajla zavisi od
> ekstraktora iz jula 2026 i **nije proverljivo**, jer izvorni artefakt ne
> postoji.

Za sam identitet to nije prepreka — kanonski identitet je po definiciji
(`shared/vector_identity.py:177-205`) heš **izvučenog teksta**, ne bajtova. Ali
jeste ograničenje koje mora biti zapisano, i vodi u nalaz PINE02-F2.

## Tabela — svih 43 reda


| # | `document_id` | `predmet_id` | `tekst_sadrzaj` | zn. | trenutni `content_sha256` | izračunat kanonski identitet | očekivani ID vektora | dokaziva veza sa Pinecone vektorom | ishod |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `abf8101c` | `00a56895` | DA | 533 | **NULL** | `f6339d82e41dc682a7c942abe353c37d` | `00a56895…__f6339d82…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 2 | `3ed20dae` | `00a56895` | DA | 527 | **NULL** | `6cc189eba5fc07ffad3b329888d3441d` | `00a56895…__6cc189eb…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 3 | `39b7463a` | `00a56895` | DA | 424 | **NULL** | `aa51923b2408eaf07d828dea7951bf86` | `00a56895…__aa51923b…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 4 | `0d39c48a` | `0129f973` | DA | 533 | **NULL** | `f6339d82e41dc682a7c942abe353c37d` | `0129f973…__f6339d82…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 5 | `3d177a32` | `0129f973` | DA | 527 | **NULL** | `6cc189eba5fc07ffad3b329888d3441d` | `0129f973…__6cc189eb…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 6 | `67536829` | `0129f973` | DA | 424 | **NULL** | `aa51923b2408eaf07d828dea7951bf86` | `0129f973…__aa51923b…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 7 | `a93ef3df` | `01f137cf` | DA | 328 | **NULL** | `7e7c56f7f68d5f7e7a8284c1b33abe45` | `01f137cf…__7e7c56f7…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 8 | `f9f6c5f2` | `01f137cf` | DA | 265 | **NULL** | `8700a5205ff96b8feb6cfb9b6db66e0f` | `01f137cf…__8700a520…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 9 | `11d3e4a9` | `01f137cf` | DA | 227 | **NULL** | `6adef833812a6b28af66392a5e84b0ce` | `01f137cf…__6adef833…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 10 | `0577f41e` | `01f137cf` | DA | 206 | **NULL** | `6b992662ea7c400054d9c0a3de9d7ca7` | `01f137cf…__6b992662…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 11 | `d363a085` | `1f909976` | DA | 405 | **NULL** | `f1dfb14e71d1fe8f9376ee58a6a89e62` | `1f909976…__f1dfb14e…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 12 | `1880fc72` | `1f909976` | DA | 312 | **NULL** | `02f28aee6617badfb449cf4591009c93` | `1f909976…__02f28aee…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 13 | `3828c17b` | `1f909976` | DA | 580 | **NULL** | `b6e182440e98f5d03d787fb0d0c7e47e` | `1f909976…__b6e18244…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 14 | `52e76915` | `26c12a60` | DA | 346 | **NULL** | `e55b7d0adec4cd80df8fd5a60a08746e` | `26c12a60…__e55b7d0a…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 15 | `b5ed492e` | `26c12a60` | DA | 77 | **NULL** | `599fec9a0d9e0968c1b2e708b4e431ed` | `26c12a60…__599fec9a…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 16 | `88c36999` | `26c12a60` | DA | 282 | **NULL** | `545342a763a4b0b1598908d6ae8a2d67` | `26c12a60…__545342a7…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 17 | `72c461f5` | `47b4884e` | DA | 405 | **NULL** | `f1dfb14e71d1fe8f9376ee58a6a89e62` | `47b4884e…__f1dfb14e…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 18 | `565aaaad` | `47b4884e` | DA | 312 | **NULL** | `02f28aee6617badfb449cf4591009c93` | `47b4884e…__02f28aee…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 19 | `42cd5e12` | `47b4884e` | DA | 580 | **NULL** | `b6e182440e98f5d03d787fb0d0c7e47e` | `47b4884e…__b6e18244…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 20 | `0050a23f` | `47dc4817` | DA | 548 | **NULL** | `dd541bad555c71c94969569d323c234b` | `47dc4817…__dd541bad…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 21 | `f77f8881` | `4f28f4b9` | DA | 323 | **NULL** | `3a43c209ac80feb48cdd05ba42a6e03f` | `4f28f4b9…__3a43c209…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 22 | `c6481d9b` | `4f28f4b9` | DA | 370 | **NULL** | `1a3d3140ef6bf10119240ec609f1ea60` | `4f28f4b9…__1a3d3140…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 23 | `8f45a0c5` | `4f28f4b9` | DA | 263 | **NULL** | `eb8dd4dbe114882e0f41a226689977f3` | `4f28f4b9…__eb8dd4db…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 24 | `db85b0d1` | `4f28f4b9` | DA | 107 | **NULL** | `875d3881a8c84c996127d31ca42a0591` | `4f28f4b9…__875d3881…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 25 | `3006377a` | `6c07ab5d` | DA | 328 | **NULL** | `7e7c56f7f68d5f7e7a8284c1b33abe45` | `6c07ab5d…__7e7c56f7…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 26 | `4f1b1afc` | `6c07ab5d` | DA | 265 | **NULL** | `8700a5205ff96b8feb6cfb9b6db66e0f` | `6c07ab5d…__8700a520…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 27 | `b48e303a` | `6c07ab5d` | DA | 227 | **NULL** | `6adef833812a6b28af66392a5e84b0ce` | `6c07ab5d…__6adef833…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 28 | `45eab367` | `6c07ab5d` | DA | 206 | **NULL** | `6b992662ea7c400054d9c0a3de9d7ca7` | `6c07ab5d…__6b992662…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 29 | `b7d3e1a5` | `720c36b2` | DA | 256 | **NULL** | `872fd0e83660e2a56d49868abf1522bc` | `720c36b2…__872fd0e8…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 30 | `e9fba600` | `7faf7d8e` | DA | 323 | **NULL** | `3a43c209ac80feb48cdd05ba42a6e03f` | `7faf7d8e…__3a43c209…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 31 | `3333a2d9` | `7faf7d8e` | DA | 370 | **NULL** | `1a3d3140ef6bf10119240ec609f1ea60` | `7faf7d8e…__1a3d3140…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 32 | `4c8daf1a` | `7faf7d8e` | DA | 263 | **NULL** | `eb8dd4dbe114882e0f41a226689977f3` | `7faf7d8e…__eb8dd4db…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 33 | `96901dfb` | `7faf7d8e` | DA | 107 | **NULL** | `875d3881a8c84c996127d31ca42a0591` | `7faf7d8e…__875d3881…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 34 | `4a4ce1e5` | `87b76dc2` | DA | 548 | **NULL** | `dd541bad555c71c94969569d323c234b` | `87b76dc2…__dd541bad…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 35 | `a1903480` | `ab37c832` | DA | 548 | **NULL** | `dd541bad555c71c94969569d323c234b` | `ab37c832…__dd541bad…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 36 | `a1c4c90c` | `b3f7eae5` | DA | 548 | **NULL** | `dd541bad555c71c94969569d323c234b` | `b3f7eae5…__dd541bad…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 37 | `d1883f57` | `d2fb1e1f` | DA | 256 | **NULL** | `872fd0e83660e2a56d49868abf1522bc` | `d2fb1e1f…__872fd0e8…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 38 | `c8574c9f` | `e0a54af1` | DA | 533 | **NULL** | `f6339d82e41dc682a7c942abe353c37d` | `e0a54af1…__f6339d82…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 39 | `456334e3` | `e0a54af1` | DA | 527 | **NULL** | `6cc189eba5fc07ffad3b329888d3441d` | `e0a54af1…__6cc189eb…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 40 | `9ec336aa` | `e0a54af1` | DA | 424 | **NULL** | `aa51923b2408eaf07d828dea7951bf86` | `e0a54af1…__aa51923b…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 41 | `96c62120` | `f4bbb99b` | DA | 346 | **NULL** | `e55b7d0adec4cd80df8fd5a60a08746e` | `f4bbb99b…__e55b7d0a…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 42 | `07077228` | `f4bbb99b` | DA | 77 | **NULL** | `599fec9a0d9e0968c1b2e708b4e431ed` | `f4bbb99b…__599fec9a…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |
| 43 | `814e386a` | `f4bbb99b` | DA | 282 | **NULL** | `545342a763a4b0b1598908d6ae8a2d67` | `f4bbb99b…__545342a7…__k1_c0` (1 chunk) | **NE** (0 pogodaka / 12 sondi) | **RECONSTRUCTABLE** |

---

# §5 — VERIFIKACIJA 30 ORPHAN VEKTORA

## Popis

Šest namespace-ova `pred_*`, po **5** vektora — ukupno **30**, potvrđeno
`describe_index_stats()` i punim `list()` po svakom namespace-u.

```
pred_17d3edb4…  5      pred_c326f5bb…  5
pred_26904a63…  5      pred_c41b9afc…  5
pred_7d7e8e14…  5      pred_dfe8d288…  5
```

Oblik ID-a: **`uuid4` sa crticama na 30/30.** Nijedan nije kanonskog oblika.

## Koja polja postoje (bez ispisivanja sadržaja)

Svih 30 ima **identičan** skup od 9 ključeva:

| Polje | Vrednost |
|---|---|
| `session_id` | 6 različitih; svaki jednak sufiksu svog namespace-a |
| `chunk_index` | 0,1,2,3,4 — po 6 vektora na svaki indeks |
| `chunk_mode` | `recursive` (30/30) |
| `source_format` | `pdf` (30/30) |
| `source_filename` | **jedna jedina vrednost na svih 30** |
| `token_count` | 5 različitih vrednosti, svaka tačno 6× |
| `text` | 19–1435 znakova, 5 različitih dužina |
| `expires_at` | **prazan na 30/30** |
| `article_label` | prazan na 30/30 |

**Polja identiteta koja NE postoje ni na jednom:** `vx_scope`, `vx_verzija`,
`vx_chunk_schema`, `vx_document_id`, `predmet_id`, `content_sha256`, `user_id`.
Dakle **0/30** nosi ijednu vezu ka bazi ili ka vlasniku.

## Merena struktura: šest identičnih kopija jednog dokumenta

Grupisanjem po `chunk_index` i heširanjem `text`-a:

```
chunk_index=0 → 1 različit heš preko 6 namespace-ova
chunk_index=1 → 1
chunk_index=2 → 1
chunk_index=3 → 1
chunk_index=4 → 1
```

Šest namespace-ova sadrži **bajt-identičan skup od 5 chunk-ova**. To je jedan
dokument ingestovan šest puta pod šest različitih sesija — činjenica, ne
zaključak o tome čiji je.

## Pokušaj dokaza mapiranja — tri dozvoljena dokaza, sva tri oborena

### Dokaz 1 — podudaranje `session_id` sa poljem u bazi: **NEMA**

Pretraženo je **13 tabela·kolona** × 6 `session_id` × 2 oblika (sa crticama i bez)
+ `ilike` podniz:

`predmeti.id`, `predmet_dokumenti.id`, `.storage_path`, `.pinecone_namespace`,
`.source_intake_job_id`, `.source_intake_job_segment_id`, `ai_sessions.session_id`,
`aktivne_sesije.session_id`, `intake_jobs.id`, `intake_documents.id`,
`intake_job_segments.id`, `ingest_jobs.id`, `predmet_dokazi.id`.

```
UKUPNO POGODAKA: 0
```

Posebno je proveren najjači kandidat: `predmet_dokumenti.storage_path` je
`session/{id}` na 43/43, i `pred_` + taj id **jeste** `pinecone_namespace` istog
reda (43/43 poklapanja — dakle kolona zaista nosi session id). Presek tih 43
session id-eva sa 6 orphan session id-eva je **prazan**, i direktno i posle
uklanjanja crtica.

### Dokaz 2 — podudaranje kanonskog heša teksta: **NEMA**

`text` metapodatak svakog od 30 vektora upoređen je sa `tekst_sadrzaj` svakog od
43 dokumenta, kroz **pet nezavisnih normalizacija**: sirovo, `strip`, sažimanje
belina, NFC + sažimanje belina, NFKC + mala slova + sažimanje belina.

```
POKLAPANJA: 0 / 30      (0 od 1290 parova × 5 normalizacija)
```

Dodatno je proveren i slabiji, širi test — je li ijedan tekst iz baze **podniz**
nekog orphan chunk-a ili obrnuto:

```
PODNIZ-POGODAKA: 0
```

Odgovor na izričito postavljeno pitanje misije glasi brojem: **0 od 30 orphan
vektora poklapa se sa ijednim od 43 `tekst_sadrzaj`.**

Uz to postoji i **strukturna nemogućnost**, nezavisna od poređenja: jedan orphan
namespace nosi **5210 znakova** teksta, a najduži `tekst_sadrzaj` u bazi ima
**580**. Nijedan red baze nije ni dovoljno velik da bude taj dokument. Čak i
najduži pojedinačni orphan chunk (1435 zn.) je duži od svakog reda u bazi.

### Dokaz 3 — `chunk_index` + broj chunk-ova: **OBORENO**

Orphani imaju **5 chunk-ova** po dokumentu (indeksi 0–4, potpun niz).
Produkcijski `chunk_document` pokrenut nad sva 43 teksta daje
**`total_chunks == 1` na 43/43.**

```
5 ≠ 1   →   nijedan od 43 ne može biti izvor nijednog orphan skupa
```

Ovo je jedini od tri dokaza koji ne samo da ne potvrđuje mapiranje nego ga
**aktivno isključuje**.

### Šta NIJE korišćeno kao dokaz — i zašto se ipak beleži

`source_filename` je **identičan na svih 30** i **ne pojavljuje se ni u jednom**
od 19 naziva u bazi (presek = 0). Vremenska blizina, sličnost vektora i „jedini
preostali kandidat" nisu ni računati. Ovo je zapisano kao činjenica jer je
merena, a **izričito ne ulazi u klasifikaciju** — misija to zabranjuje, i s
razlogom: čak i da se ime poklopilo, 43 reda dele svega 19 naziva, pa ime ne bi
razlikovalo dokument od dokumenta.

## Ishod

**`ORPHAN_UNIDENTIFIABLE` — 30 / 30.** `MAPIRANO` — 0.

Razlog nije „nismo našli" nego **„izmereno je da veze nema"**: 0 pogodaka po
session_id kroz 13 kolona, 0 poklapanja teksta kroz 5 normalizacija, i strukturna
kontradikcija 5 ≠ 1 chunk. Karantin je konačan ishod, ne međukorak — vektor čiji
identitet ne znamo ne sme se obrisati po pretpostavci.

### Jedan nalaz koji stoji uz karantin

`expires_at` je **prazan na svih 30**, a `cleanup_expired` gleda isključivo
`tmp_*` namespace-ove. Ovih 30 vektora nema **nikakav mehanizam isteka** — ostaju
kod Pinecone-a neograničeno. To je isti nalaz koji je PINE-01 zaveo kao PINE-F i
ovaj sprint ga potvrđuje merenjem, ne prepisivanjem.

## Tabela — svih 30 vektora


| # | namespace | vektor `id` (8 zn.) | `chunk_index` | `session_id` (8 zn.) | `session_id` u bazi? | heš teksta = ijedan `tekst_sadrzaj`? | broj chunk-ova (5) = ijedan dokument (1)? | ishod |
|---|---|---|---|---|---|---|---|---|
| 1 | `pred_17d3edb4…` | `1e832e44` | 0 | `17d3edb4` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 2 | `pred_17d3edb4…` | `f331aac4` | 1 | `17d3edb4` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 3 | `pred_17d3edb4…` | `ad8e6c09` | 2 | `17d3edb4` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 4 | `pred_17d3edb4…` | `141ae06e` | 3 | `17d3edb4` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 5 | `pred_17d3edb4…` | `d69f89c1` | 4 | `17d3edb4` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 6 | `pred_26904a63…` | `39a6a847` | 0 | `26904a63` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 7 | `pred_26904a63…` | `82e8d3b1` | 1 | `26904a63` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 8 | `pred_26904a63…` | `d9eb0f7b` | 2 | `26904a63` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 9 | `pred_26904a63…` | `756f4bf6` | 3 | `26904a63` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 10 | `pred_26904a63…` | `9559df61` | 4 | `26904a63` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 11 | `pred_7d7e8e14…` | `6552885e` | 0 | `7d7e8e14` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 12 | `pred_7d7e8e14…` | `0f92db17` | 1 | `7d7e8e14` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 13 | `pred_7d7e8e14…` | `a2183625` | 2 | `7d7e8e14` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 14 | `pred_7d7e8e14…` | `15a9f2ac` | 3 | `7d7e8e14` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 15 | `pred_7d7e8e14…` | `50dbdf1f` | 4 | `7d7e8e14` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 16 | `pred_c326f5bb…` | `149f9efe` | 0 | `c326f5bb` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 17 | `pred_c326f5bb…` | `df643187` | 1 | `c326f5bb` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 18 | `pred_c326f5bb…` | `92583523` | 2 | `c326f5bb` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 19 | `pred_c326f5bb…` | `456796bc` | 3 | `c326f5bb` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 20 | `pred_c326f5bb…` | `4aea9862` | 4 | `c326f5bb` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 21 | `pred_c41b9afc…` | `0fa3d6ce` | 0 | `c41b9afc` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 22 | `pred_c41b9afc…` | `40234462` | 1 | `c41b9afc` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 23 | `pred_c41b9afc…` | `69f256fc` | 2 | `c41b9afc` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 24 | `pred_c41b9afc…` | `6605105e` | 3 | `c41b9afc` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 25 | `pred_c41b9afc…` | `62d65887` | 4 | `c41b9afc` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 26 | `pred_dfe8d288…` | `c0ae8912` | 0 | `dfe8d288` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 27 | `pred_dfe8d288…` | `36ce2377` | 1 | `dfe8d288` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 28 | `pred_dfe8d288…` | `9f194cc1` | 2 | `dfe8d288` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 29 | `pred_dfe8d288…` | `80d95446` | 3 | `dfe8d288` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |
| 30 | `pred_dfe8d288…` | `a58deeae` | 4 | `dfe8d288` | **NE** (0/13 tabela·kolona) | **NE** (0/5 normalizacija, 0 podstringova) | **NE** (5 ≠ 1) | **ORPHAN_UNIDENTIFIABLE** |

---

# §3 — PLAN MUTACIJE (NIJE IZVRŠEN)

SQL: **`docs/beta_gate/PINE_02_BACKFILL_content_sha256.sql`** — napisan, **nije
pokrenut**. Nijedan `UPDATE` nije izvršen u ovom sprintu.

## Definicija ocene — da se ne bi čitala šire nego što tvrdi

`SAFE` znači **tačno četiri stvari**, sve četiri izmerene za taj red:

1. vrednost je izlaz produkcijske funkcije `verzija_dokumenta()` nad
   `tekst_sadrzaj` **istog tog reda** — bez pretpostavke o originalnom fajlu;
2. vrednost ne zavisi ni od jedne heuristike (similarity, ime, veličina, datum);
3. `(predmet_id, verzija)` ne sudara se ni sa jednim drugim redom — **provereno,
   0 sudara, 43 različita ID-a vektora**;
4. `content_sha256` je NULL, pa se ništa ne prepisuje.

`SAFE` **ne** znači „bez posledice po ponašanje aplikacije". Ta posledica je
odvojena i imenovana kao PINE02-F1 ispod.

```
SAFE:   43 / 43
UNSAFE:  0 / 43
```

Nijedan red nije `LIKELY`, `PROBABLY` ni `BEST_EFFORT` — te ocene ovde ne postoje.

## Tabela plana — svih 43 reda


| # | `document_id` | stari `content_sha256` | novi kanonski | razlog | izvor dokaza | ocena |
|---|---|---|---|---|---|---|
| 1 | `abf8101c` | **NULL** | `f6339d82e41dc682a7c942abe353c37d` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (533 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 2 | `3ed20dae` | **NULL** | `6cc189eba5fc07ffad3b329888d3441d` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (527 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 3 | `39b7463a` | **NULL** | `aa51923b2408eaf07d828dea7951bf86` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (424 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 4 | `0d39c48a` | **NULL** | `f6339d82e41dc682a7c942abe353c37d` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (533 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 5 | `3d177a32` | **NULL** | `6cc189eba5fc07ffad3b329888d3441d` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (527 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 6 | `67536829` | **NULL** | `aa51923b2408eaf07d828dea7951bf86` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (424 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 7 | `a93ef3df` | **NULL** | `7e7c56f7f68d5f7e7a8284c1b33abe45` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (328 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 8 | `f9f6c5f2` | **NULL** | `8700a5205ff96b8feb6cfb9b6db66e0f` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (265 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 9 | `11d3e4a9` | **NULL** | `6adef833812a6b28af66392a5e84b0ce` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (227 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 10 | `0577f41e` | **NULL** | `6b992662ea7c400054d9c0a3de9d7ca7` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (206 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 11 | `d363a085` | **NULL** | `f1dfb14e71d1fe8f9376ee58a6a89e62` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (405 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 12 | `1880fc72` | **NULL** | `02f28aee6617badfb449cf4591009c93` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (312 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 13 | `3828c17b` | **NULL** | `b6e182440e98f5d03d787fb0d0c7e47e` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (580 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 14 | `52e76915` | **NULL** | `e55b7d0adec4cd80df8fd5a60a08746e` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (346 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 15 | `b5ed492e` | **NULL** | `599fec9a0d9e0968c1b2e708b4e431ed` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (77 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 16 | `88c36999` | **NULL** | `545342a763a4b0b1598908d6ae8a2d67` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (282 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 17 | `72c461f5` | **NULL** | `f1dfb14e71d1fe8f9376ee58a6a89e62` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (405 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 18 | `565aaaad` | **NULL** | `02f28aee6617badfb449cf4591009c93` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (312 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 19 | `42cd5e12` | **NULL** | `b6e182440e98f5d03d787fb0d0c7e47e` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (580 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 20 | `0050a23f` | **NULL** | `dd541bad555c71c94969569d323c234b` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (548 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 21 | `f77f8881` | **NULL** | `3a43c209ac80feb48cdd05ba42a6e03f` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (323 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 22 | `c6481d9b` | **NULL** | `1a3d3140ef6bf10119240ec609f1ea60` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (370 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 23 | `8f45a0c5` | **NULL** | `eb8dd4dbe114882e0f41a226689977f3` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (263 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 24 | `db85b0d1` | **NULL** | `875d3881a8c84c996127d31ca42a0591` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (107 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 25 | `3006377a` | **NULL** | `7e7c56f7f68d5f7e7a8284c1b33abe45` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (328 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 26 | `4f1b1afc` | **NULL** | `8700a5205ff96b8feb6cfb9b6db66e0f` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (265 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 27 | `b48e303a` | **NULL** | `6adef833812a6b28af66392a5e84b0ce` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (227 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 28 | `45eab367` | **NULL** | `6b992662ea7c400054d9c0a3de9d7ca7` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (206 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 29 | `b7d3e1a5` | **NULL** | `872fd0e83660e2a56d49868abf1522bc` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (256 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 30 | `e9fba600` | **NULL** | `3a43c209ac80feb48cdd05ba42a6e03f` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (323 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 31 | `3333a2d9` | **NULL** | `1a3d3140ef6bf10119240ec609f1ea60` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (370 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 32 | `4c8daf1a` | **NULL** | `eb8dd4dbe114882e0f41a226689977f3` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (263 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 33 | `96901dfb` | **NULL** | `875d3881a8c84c996127d31ca42a0591` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (107 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 34 | `4a4ce1e5` | **NULL** | `dd541bad555c71c94969569d323c234b` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (548 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 35 | `a1903480` | **NULL** | `dd541bad555c71c94969569d323c234b` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (548 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 36 | `a1c4c90c` | **NULL** | `dd541bad555c71c94969569d323c234b` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (548 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 37 | `d1883f57` | **NULL** | `872fd0e83660e2a56d49868abf1522bc` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (256 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 38 | `c8574c9f` | **NULL** | `f6339d82e41dc682a7c942abe353c37d` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (533 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 39 | `456334e3` | **NULL** | `6cc189eba5fc07ffad3b329888d3441d` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (527 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 40 | `9ec336aa` | **NULL** | `aa51923b2408eaf07d828dea7951bf86` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (424 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 41 | `96c62120` | **NULL** | `e55b7d0adec4cd80df8fd5a60a08746e` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (346 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 42 | `07077228` | **NULL** | `599fec9a0d9e0968c1b2e708b4e431ed` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (77 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |
| 43 | `814e386a` | **NULL** | `545342a763a4b0b1598908d6ae8a2d67` | kolona prazna; identitet je funkcija isključivo `tekst_sadrzaj` (282 zn., < 100 000) | `verzija_dokumenta(predmet_dokumenti.tekst_sadrzaj)` — produkcijska funkcija, `shared/vector_identity.py:208` | **SAFE** |

---

# ODGOVOR NA GLAVNO PITANJE

> **Je li bezbedno popuniti `content_sha256` za svih 43?**

## Kao podatak — DA, i to je dokazano

Vrednost je za svaki red deterministički izvedena iz onoga što u tom redu već
stoji, produkcijskom funkcijom, bez ijedne pretpostavke. Nema sudara, nema
prepisivanja, nema nagađanja. **43/43 SAFE.**

Provereno je i šta bi se desilo posle upisa, pokretanjem **produkcijskog** helper-a
`shared/vector_deletion._izlistaj_po_prefiksu` nad stvarnim prefiksom stvarnog
reda:

```
_izlistaj_po_prefiksu(index, ns, prefiks)  →  []      (ne None)
→ obrisi_vektore_dokumenta bi vratio ALREADY_ABSENT
```

Dakle backfill **ne može** izazvati brisanje — ni tačno, ni pogrešno. Servis
prelazi iz `REFUSED` u `ALREADY_ABSENT`, što je istinit iskaz: vektora nema.

## Kao promena ponašanja — NE bez izričite odluke

Ovo je nalaz koji nijedan raniji sprint nije naveo, i on je razlog zašto verdikt
nije zelen.

### PINE02-F1 — kolona je mrtva kapija koja se budi upisom | **HIGH**

`routers/smart_intake.py:1348-1388` čita **baš tu kolonu** i na osnovu nje
donosi dve odluke:

| Grana | Uslov | Posledica |
|---|---|---|
| `same_case_dup` | isti heš, **isti** predmet | dokument se **preskače** — `vec_obradjen_preskocen` |
| `other_case_dup` | isti heš, **drugi** predmet | dokument se **ne povezuje** — `duplikat_u_drugom_predmetu`, review |

Dok je kolona NULL, `.eq("content_sha256", …)` ne pogađa nikad i obe grane su
mrtve. Posle backfill-a ožive. A izmereno je:

```
19 različitih sadržaja
19 / 19 postoji u ≥2 RAZLIČITA predmeta        ← cross-case duplikat: 100%
 0 / 19 duplirano unutar istog predmeta
svih 43 reda pripada JEDNOM user_id            ← domet promene
```

Konkretna posledica: kad taj korisnik ubuduće pošalje kroz Smart Intake bilo koji
od tih 19 sadržaja, dokument **neće biti automatski povezan** nego poslat u
review. Uz to, ta 43 reda imaju **status `sacuvano` i nula vektora** — pa bi
sistem odbio da poveže dokument, pozivajući se na red koji ni sam nije indeksiran.

To nije kvar u backfill-u nego postojeće ponašanje koje backfill **aktivira**.
Domet je jedan korisnik i 19 sadržaja, ali odluka mora biti svesna.

`api.py:5188-5199` (Pipeline A) je bezbedan po istom pitanju: njegova provera je
**informativna i ne menja tok uploada** (`api.py:5805` to izričito kaže).

### PINE02-F2 — `e1` je deklaracija, ne merenje | **MEDIUM**

`verzija_dokumenta()` u heš ugrađuje `EXTRACTION_VERSION = 1`, čime tvrdi „ovaj
tekst je izlaz ekstrakcije verzije 1". Za ova 43 dokumenta ta tvrdnja je
**neproverljiva**:

- `EXTRACTION_VERSION` je uveden **2026-08-13** (`dcbf3fd9`), tri nedelje **posle**
  nastanka redova (2026-07-18 → 07-21);
- `uploaded_doc/extractor.py` je od tada izmenjen **5 puta**
  (`c5116e1e`, `3bd882eb`, `1aab80a5`, `14bfc666`, `06ea1e45`);
- original ne postoji (`storage.list("session")` = **0 objekata** u oba bucket-a),
  pa ponovna ekstrakcija radi provere nije moguća.

Za svrhu identiteta to nije prepreka — vrednost je stabilan ključ i biće ista pri
svakom računanju. Ali kad se `EXTRACTION_VERSION` jednom poveća, ovih 43 će
nositi oznaku koja ne odgovara ekstraktoru koji ih je stvarno proizveo. Zapisano
da se ne bi kasnije pročitalo kao garancija koju nikad nije davalo.

### PINE02-F3 — backfill ne pravi nijedan vektor | **INFO, ali se mora reći naglas**

Posle upisa i dalje važi:

```
dokumenata sa vektorima:  0 / 43
fizički obrisivo:         ništa
```

Backfill zatvara **PINE-A** (prazan identitet), ne **PINE-B** (ne postoji DELETE
endpoint) i ne nedostatak vektora. Ako se ovih 43 želi učiniti pretraživim,
potreban je **reindex**, koji je zasebna odluka i u ovom mandatu izričito zabranjen.

## Preporuka

**Uslovno DA.** Upis je tehnički ispravan i reverzibilan (rollback je u SQL fajlu,
poklapa se i po `id` i po vrednosti). Preporučeni redosled:

1. Vlasnik potvrđuje PINE02-F1 — prihvata da Smart Intake ubuduće šalje tih 19
   sadržaja u review umesto automatskog povezivanja.
2. Pokreće se SQL, koji sam sebe prekida ako pre upisa ne zatekne tačno 43 NULL
   reda i ako posle upisa ostane ijedan NULL ili ijedna nekanonska vrednost.
3. **Tek onda** PINE-03 (DELETE endpoint) ima na čemu da radi.

Ako se F1 ne prihvata, tačan potez nije preskočiti backfill nego prvo razdvojiti
dedup semantiku od kolone identiteta — to je izmena koda, ne podataka.

---

# PINE02-F4 — KANONSKA FUNKCIJA SE PROMENILA TOKOM MERENJA | **INFO / provereno**

Ovo se prijavljuje jer bi prećutano poništilo vrednost celog izveštaja.

Tokom ovog sprinta je **drugi, uporedan proces** izmenio radno stablo:

```
shared/vector_identity.py    +60 / -8    (dodat `kanonski_tekst()`,
                                          `verzija_dokumenta` sada normalizuje ulaz)
shared/vector_deletion.py    +55        (dodata nova funkcija POSLE `klasifikuj_orphan`)
```

Vrednosti u tabelama iznad su računane produkcijskom funkcijom — ali se ta
funkcija promenila **ispod merenja**, pa tvrdnja „izračunato produkcijskom
funkcijom" više nije jednoznačna dok se ne kaže **kojom**.

Zato je izvršena izričita provera invarijantnosti: modul sa baseline-a
`053c3cc4` je učitan iz `git show` u zaseban prostor imena i pokrenut **naporedo**
sa verzijom iz radnog stabla, nad ista 43 teksta.

```
verzija_dokumenta baseline == verzija_dokumenta radno stablo :  43 / 43
kanonski_tekst() menja tekst                                :   0 / 43
tabela iznad se poklapa sa baseline-om                      :  43 / 43
tabela iznad se poklapa sa radnim stablom                   :  43 / 43
```

Razlog invarijantnosti je merljiv, ne srećan: nova normalizacija dira NFC,
`CRLF`/`CR`, repove redova i 3+ uzastopnih preloma — a nijedan od 43 teksta
(77–580 znakova) ne sadrži nijednu od tih pojava.

Provereno je i da `prefiks_dokumenta`, `canonical_vector_id` i
`obrisi_vektore_dokumenta` **nisu dirani** — izmena u `vector_deletion.py` je
čisto dodavanje nove funkcije iza `klasifikuj_orphan`.

**Zaključak: SQL literali u planu mutacije važe pod obe verzije funkcije.**
Ako se `kanonski_tekst()` ubuduće promeni tako da dira i kratke tekstove, plan
se mora ponovo izračunati pre pokretanja — vrednosti su literali baš zato da bi
se to videlo, umesto da SQL tiho izračuna nešto drugo.

---

# METOD — ŠTA JE STVARNO POKRENUTO

| Provera | Obim | Rezultat |
|---|---|---|
| `SELECT *` nad `predmet_dokumenti` | 43 reda, 18 kolona | osnov svega |
| `verzija_dokumenta()` — produkcijska funkcija | 43 poziva | 43 identiteta, 19 različitih |
| `chunk_document()` — produkcijski chunker | 43 poziva | `total_chunks == 1` na 43/43 |
| `describe_index_stats()` | 11 namespace-ova, 434.217 vektora | 6 `pred_*` sa po 5 |
| `Index.list()` po orphan namespace-u | 6 namespace-ova | 30 ID-eva |
| `Index.fetch()` | 30 vektora | 9 polja, 0 identitetskih |
| `Index.list(prefix=…)` | **516 sondi** (43 × 12 ns) | **0 pogodaka** |
| poređenje teksta | 30 × 43 × 5 normalizacija + podniz test | **0 poklapanja** |
| pretraga `session_id` po bazi | 13 tabela·kolona × 6 × 2 oblika + `ilike` | **0 pogodaka** |
| `storage.list()` | 2 bucket-a, path `session` | **0 objekata** |
| `_izlistaj_po_prefiksu()` — produkcijski helper | 1 stvarni red | `[]` → `ALREADY_ABSENT` |
| istorija koda | `git show` na `7328c5d3` (2026-07-22) | pisač identifikovan |
| invarijantnost heša baseline vs radno stablo | 43 × 2 funkcije | **43/43 identično** (v. PINE02-F4) |

Nijedna od ovih operacija ne menja stanje. Nijedan `UPDATE`, `DELETE`, `upsert`,
reindex ni migracija nije izvršen.

---

# ZAVRŠNA REČ

Prethodni sprint je ostavio jednu rečenicu kao sledeći blokator: *„popuniti
`content_sha256` za 43 dokumenta"*. Ovaj sprint je izmerio da je taj potez
izvodljiv na svih 43 i bezbedan kao podatak — ali i da nije bez posledice, jer
budi kapiju u Smart Intake-u koja je do sada bila mrtva, i to na sadržajima koji
su **100% cross-case duplikati**.

Druga stvar koju vredi reći bez ublažavanja: brojka „43 dokumenta bez vektora"
nije misterija. `status = 'sacuvano'` na 43/43 znači da je ingest u Pinecone
tada **pao** i da vektori nikad nisu ni napravljeni. Popunjavanje identiteta to
ne popravlja i ne treba da ostavi utisak da popravlja.

Za 30 orphan vektora zaključak je konačan i podupret trima nezavisnim merenjima,
od kojih jedno mapiranje ne samo da ne potvrđuje nego ga isključuje: 5 chunk-ova
ne može poticati iz dokumenta koji ih daje 1. **Karantin ostaje, brisanja nema.**


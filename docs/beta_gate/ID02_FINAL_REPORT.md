# BETA-DATA-ID-02 — CANONICAL CONTENT IDENTITY & LEGACY RECONCILIATION

# VERDICT

## 🟡 YELLOW

Kanonski identitet sadržaja je definisan, ožičen na svim runtime pisačima i
dokazan mutacijama. Zatvorena su **dva sudara ID-eva koje je uveo prethodni
sprint** — oba bi tiho gubila podatke.

Nije GREEN iz jednog razloga koji se ne da zaobići: **postojeći podaci se ne
mogu pomiriti.** 43 dokumenta nemaju nijedan vektor, 30 vektora nema nijedan
dokument, i presek je prazan u oba smera. Za njih PINE-01 ostaje neizvodljiv.

```
BASELINE:              78ff5d73
TEST COUNT:            5359 → 5378   (+19)
MIGRATIONS:            0   — kolona je TEXT, dužina 64→32 ne traži migraciju
PRODUCTION MUTATIONS:  0   — nijedan upis/brisanje u Pinecone ni Supabase
```

---

# CANONICAL IDENTITY

| Nivo | Vrednost |
|---|---|
| **document** | `predmet_dokumenti.id` (postoji, nije u ID-u vektora — v. ID-01) |
| **content** | **`verzija_dokumenta(tekst)` = SHA-256(`e{EXTRACTION_VERSION}\|tekst`)[:32]** |
| **version** | ista vrednost — izmenjen tekst je nova verzija |
| **chunk** | `chunk_index` + `CHUNK_SCHEMA_VERSION` |
| **vector** | `{scope}__{verzija}__k{chunk_schema}_c{chunk_index}` |

## Odluka (§3): kanonski izvor je IZVUČENI TEKST, ne bajtovi

**Ne zbog jednostavnosti, nego zato što bajtovi ne identifikuju dokument.**

`routers/smart_intake.py` deli JEDAN otpremljen fajl na N dokumenata (petlja
`for idx, doc_entry in enumerate(documents)`), a `raw_bytes` dohvata **jednom
pre petlje**. Heš bajtova je zato isti za sve segmente. Bajtovi identifikuju
**upload**, ne **dokument**.

Potvrda iz same šeme: komentar migracije 095 već propisuje
*„SHA-256 of the document's own extracted text (never filename/size/upload-date)"*.
Kanonska odluka se poklapa sa dokumentovanom namerom; `api.py` je bio
odstupanje.

## §4 — četiri semantike ostaju razdvojene

| Semantika | Vrednost | Gde |
|---|---|---|
| identitet **posla** | heš **bajtova** | `smart_intake.py:155` — **namerno ostaje** |
| identitet **dokumenta/verzije** | heš teksta + verzija ekstrakcije | `shared/vector_identity.py` |
| identitet **chunk-a** | index + verzija šeme | isto |
| identitet **vektora** | scope + verzija + chunk | isto |

## §10 — verzija ekstrakcije

`EXTRACTION_VERSION = 1` ulazi u heš. Bez nje bi nadogradnja OCR-a tiho
promenila identitet svakog skeniranog dokumenta — *„isti dokument danas → heš A,
sutra → heš B"*. Sa njom je promena vidljiva i namerna.

---

# DVA SUDARA KOJE JE UVEO ID-01

## Sudar 1 — segmenti istog posla (dokazan merenjem)

```
dokument 1 chunk0 = pred-A__8f4bd21e...__k1_c0
dokument 2 chunk0 = pred-A__8f4bd21e...__k1_c0     ← ISTI ID
```

Drugi dokument bi `upsert`-om **prepisao prvi**. Pre ID-01 sudara nije bilo jer
su ID-evi bili `uuid4` — dakle rupu je otvorio prethodni sprint.

## Sudar 2 — D-5, razilaženje dve strane ugovora

Nađen tek u forenzičkom inventaru, **posle** moje prve popravke.

ID vektora se računao iz **spojenih chunk-ova**, a `content_sha256` iz
**originalnog teksta**. `chunk_document` deli sa preklapanjem
(`OVERLAP_TOKENS = 100`), pa spajanje duplira tekst — mereno: 31.600 znakova →
24 chunk-a → spojeno **36.428 znakova**, drugi heš.

Posledica: `prefiks_dokumenta(predmet_id, content_sha256)` — **jedini upit kojim
se vektori dokumenta uopšte mogu naći** — vraćao bi prazno za svaki dokument
duži od jednog chunk-a. Tiho: upit ne puca, samo ne nalazi ništa.

**Zašto nijedan zeleni test to nije video:** testovi su računali očekivanu
vrednost istim postupkom kao implementacija, dakle merili su **istu stranu
ugovora**. Strana koja stoji u bazi nije se poredila nigde. Svih 43 postojeća
dokumenta imaju tačno 1 chunk, pa se razilaženje na produkcionim podacima ne bi
ni videlo.

**Prva popravka je bila pogrešna, i puna regresija ju je oborila.** Uveo sam
`verzija_iz_manifesta()` koju su zvale obe strane — ali sam je u
`routers/smart_intake.py` primenio POSLE provere duplikata, pa je ista
promenljiva nosila dve različite vrednosti u istoj funkciji. **24 testa su
pala.** To je tačno ono što §4 zabranjuje.

**Konačna popravka:** kanonska vrednost se računa **jednom, iz teksta
dokumenta**, i prosleđuje `ingest_session` izričitim parametrom
`verzija_dokumenta_id` (fail-closed ako izostane). Ista vrednost ide u proveru
duplikata, u `predmet_dokumenti.content_sha256` i u ID vektora. Time nestaje i
problem preklapanja chunk-ova — nijedna strana više ne spaja chunk-ove.

Uz to, `ingest_session` odbija svaku vrednost koja nije kanonskog oblika (32
heks znaka). To hvata **tačno** grešku koju su pisci pravili:
`hashlib.sha256(raw).hexdigest()` ima 64 znaka i pada odmah, umesto da tiho
proizvede vektore pod pogrešnim identitetom.

---

# PUT DO KONAČNOG DIZAJNA — TRI POKUŠAJA

Vredi zapisati redosled, jer su dva prva bila pogrešna i oborena merenjem, ne
razmišljanjem.

1. **Verzija od pozivaoca** (`manifest.source_sha256`, iz ID-01). Oboreno:
   pisci su punili to polje različitim stvarima → sudar među segmentima.
2. **Verzija iz manifesta** (spojeni chunk-ovi). Oboreno **punom regresijom** —
   24 testa. Uz to je forenzika pokazala D-5: chunk-ovi se preklapaju, pa se
   vrednost razlikuje od one u bazi.
3. **Verzija iz teksta dokumenta, računata jednom, prosleđena izričito.**
   Ista vrednost u proveri duplikata, u bazi i u ID-u vektora.

Uz (3) ide i strukturna brana: `ingest_session` odbija vrednost koja nije
kanonskog oblika (32 heks znaka), čime hvata tačno grešku koju su pisci pravili
— `hexdigest()` bajtova ima 64 znaka.

---

# LEGACY INVENTORY (pun popis, ne uzorak)

`Index.list()` je nabrojao **svaki** ID u **svakom** namespace-u:
`declared_total 434.217 == listed_total 434.217`.

| Obrazac | Broj |
|---|---|
| `{id}__chunk_{n}` (`sudska_praksa`) | 407.795 |
| md5 bez prefiksa (`zakoni_rs`) | 25.818 |
| `_chunk_N` (`web3_zdi_mca`) | 476 |
| **`uuid4`** | **104** (74 `misljenja` + 30 klijentskih) |
| kurirani literali | 20 |
| `::` glosar | 4 |
| **novi ID-01 model** | **0** |
| **UNKNOWN** | **0** |

```
ukupno:     434.217
legacy:     434.217
novi model: 0
orphan:     30
ambiguous:  0
```

## Javni korpusi vs klijentski podaci — 434.187 : 30

Razdvajanje počiva na **dva nezavisna merenja**, ne na imenovanju namespace-a:
poreklo pisača (javne korpuse pišu ručno pokretane skripte nad javnim izvorima;
`pred_*` samo autentifikovana HTTP ruta) i oblik metapodataka (nijedan javni
vektor nema `session_id`/`source_filename`/`source_format`; svih 30 klijentskih
ima sva tri). **Presek je prazan.** Javni skup nije predmet čl. 17 i ne sme se
uvući u čišćenje.

---

# 43 DOKUMENTA

| KAT | Broj | Osnov |
|---|---|---|
| **A** — identitet rekonstruktivan | **43** | `tekst_sadrzaj` popunjen **43/43** (77–580 zn.) → verzija izračunata za sve; `total_chunks == 1` na 43/43 |
| **B** — samo iz izvornog artefakta | **0** | original **nikad nije ni sačuvan**: `storage_path='session/{id}'` je labela na 43/43; `list(path="session")` nad 3 bucket-a = **0 objekata** |
| **C** — nije rekonstruktivan | **0** | — |
| **D** — ingest nikad potvrđen | **43** | `status='sacuvano'` 43/43; **946/946 prefix sondi bez pogotka** |
| **E** — vektor bez DB veze | **30 vektora / 6 ns** | svih 30 `uuid4`; `session_id` iz metapodataka ne postoji ni u jednom od 43 reda |

Sva 43 su **istovremeno A i D**. Presek sa E je prazan u oba smera.

`tekst_sadrzaj` popunjen na 43/43 je **novo** i jedini je razlog zašto je
kategorija A, a ne C — identitet se može izračunati bez originalnog fajla.

---

# WRITERS

```
fizičkih upsert mesta:  19   (ne 7 i ne 10)
u runtime-u:             7
u batch/CLI skriptama:  12   — pišu u ISTE žive namespace-ove (99,99% indeksa)
```

## Popravljeno u ovom sprintu

| Pisač | Šta |
|---|---|
| `uploaded_doc/ingest.py` | izričit `verzija_dokumenta_id`, fail-closed + provera kanonskog oblika |
| `api.py` | jedna vrednost: provera duplikata = baza = ID vektora |
| `routers/smart_intake.py` | isto; `source_sha256` više nije heš celog posla |
| `routers/dokument.py` | kanonski ugovor |
| `routers/drafting.py` | poravnat na kanonsku funkciju |

## OPEN — legacy semantika ostaje (L-1…L-10)

| ID | Pisač | Problem |
|---|---|---|
| **L-1** | `ingest_misljenja.py` | **sva tri obrasca odjednom**: `uuid4` ID + `except → continue` + `zip()` bez provere. Proizvod: **74 živa vektora**. Nije bio ni u jednoj ranijoj listi |
| **L-2** | `law_upload.py:150` | embed strana popravljena u ID-01, **upsert strana nije** — `except → log → continue`, pa `status="done" if upserted > 0` |
| **L-3** | `batch_ingest.py:138` | `enumerate(embeddings)` bez ijedne provere dužine |
| **L-5** | `auto_discovery.py:199` | ID je čist heš sadržaja **bez scope-a** — suprotno RULE 12 |
| **L-7** | `drafting.py`, `intake.py`, `onboarding.py` | ne pišu `content_sha256` → backfill po toj koloni promašuje nacrte |

---

# SECURITY

| Svojstvo | Ishod |
|---|---|
| cross-tenant | **odvojen** — `scope` u ID-u; isti sadržaj, dva predmeta → različiti ID-evi |
| cross-document | **odvojen** — sudar 1 zatvoren |
| retry | **idempotentan** — isti tekst → isti ID-evi → `upsert` prepisuje |
| partial ingest | **nemoguć** — kapija pre prvog upisa (004), i dalje važi |
| duplicate | ponovni upload istog teksta ne povećava broj vektora |

---

# MUTATION

| # | Mutacija | Očekivano | Stvarno |
|---|---|---|---|
| A | verzija se uzima od pozivaoca (stari ID-01 ugovor) | pad | **7 pada** |
| B | `smart_intake` → heš bajtova posla | pad | **ne obara test** — v. „priznata rupa" |
| C | uklonjena verzija ekstrakcije | pad | **1 pada** |
| D | kanonski identitet → nasumičan | pad | **12 pada** |
| E | `api.py` → heš bajtova | pad | **ne obara test** — isti razlog kao B |
| **D-5** | razilaženje dve strane ugovora | pad | **1 pada** |

## Priznata rupa u pokrivenosti

Mutacije B i E menjaju **ožičenje pisača**, a postojeći intake testovi mokuju
`ingest_session` u celini — pa mutaciju ne vide. Ne predstavljam to kao uspeh.

Ono što jeste zatvoreno: posledica više nije tiha. Provera kanonskog oblika diže
izuzetak, `smart_intake` ga hvata kao neuspeh ingesta, dokument dobija status
`sacuvano` — a to advokat **vidi**, zahvaljujući Playwright-dokazanoj UI popravci
iz sprinta 004. Ranije bi isti kvar proizveo vektore pod pogrešnim identitetom
i prijavio uspeh.

Izvršni test nad ožičenjem `smart_intake`/`api.py` ostaje **OPEN** (ID02-08).

---

# ORPHAN MODEL (§15 — definicija, ništa izvršeno)

| Slučaj | Dokaz | Akcija |
|---|---|---|
| A — dokument + vektor | `prefiks_dokumenta(predmet_id, content_sha256)` pogađa `total_chunks` | KEEP |
| B — dokument bez vektora | isti upit vraća 0 | REINDEX |
| C — vektor bez dokumenta | `vx_scope` + `vx_verzija` → nema reda | **QUARANTINE**, ne DELETE |
| D — pogrešan tenant | `vx_scope` ≠ vlasnikov predmet | QUARANTINE |
| E — pogrešna verzija | `vx_verzija` ≠ `content_sha256` reda | QUARANTINE |
| F — nepoznat identitet | nema `vx_*` polja | **NIKAD DELETE** |

**F pre C**, i za F nikad brisanje: automatsko brisanje po „nepoznat ID" obrisalo
bi ceo legitiman `misljenja` namespace (74 vektora).

---

# OPEN FINDINGS

| ID | Nalaz | Nivo |
|---|---|---|
| **ID02-01** | veza dokument ↔ vektor **prekinuta u oba smera**: 43 reda / 0 vektora, 6 ns / 0 redova | **RED** |
| **ID02-02** | GDPR brisanje ide kroz `pinecone_namespace` i **ne može dosegnuti nijedan od 30 vektora** | **RED** |
| **L-1** | `ingest_misljenja.py` — tri legacy obrasca, 74 živa vektora | **HIGH** |
| **L-2** | `law_upload.py` upsert strana i dalje guta grešku | **HIGH** |
| **L-3** | `batch_ingest.py` bez provere dužine | **HIGH** |
| **L-5** | `auto_discovery.py` ID bez scope-a | MEDIUM |
| **L-7** | tri pisača ne pišu `content_sha256` | MEDIUM |
| **ID02-07** | 6 `pred_*` ns ima **identičan `source_filename`**; zabeleženo kao činjenica, **bez zaključka** o istom dokumentu | UNKNOWN |
| **ID02-08** | ožičenje `smart_intake`/`api.py` nije pokriveno izvršnim testom — postojeći intake testovi mokuju `ingest_session` | **HIGH** |

---

# PINE-01 STATUS

## PARTIALLY UNBLOCKED

**Odblokiran** za dokumente ingestovane od sada:
`prefiks_dokumenta(predmet_id, content_sha256)` izdvaja tačno chunk-ove te
verzije tog dokumenta, i **obe strane ugovora sada koriste istu vrednost** —
dokazano testom na višechunk dokumentu.

**Blokiran** za postojeće podatke, iz tri merena razloga:

1. **43 dokumenta nemaju nijedan vektor** (946/946 prefix sondi bez pogotka), a
   **30 vektora nema nijedan dokument**. Presek prazan u oba smera.
2. **`content_sha256` je NULL na 43/43 reda.** Identitet se **može** izračunati
   (kategorija A, `tekst_sadrzaj` postoji), ali upis te vrednosti je izmena
   produkcionih podataka — §20 to zabranjuje bez zasebne odluke.
3. **Svih 30 postojećih klijentskih vektora ima `uuid4` ID** i nijedno `vx_*`
   polje. Za njih deterministički identitet **ne postoji retroaktivno** i ne može
   se izvesti — jedini put je karantin, ne brisanje.

---

# ZAVRŠNA REČ

Sprint je odgovorio na svoje pitanje, ali je usput našao nešto teže od njega:
**prethodni sprint je uveo dva tiha sudara ID-eva**, a jedan od njih (D-5) nije
mogao biti otkriven testovima koji mere samo jednu stranu ugovora.

Ono što se sme reći bez ograde: od sada je za svaki nov dokument moguće tačno
reći koji vektori mu pripadaju, i ta tvrdnja je dokazana na dokumentu koji ima
više chunk-ova — dakle tamo gde su svi raniji dokazi ćutali.

Ono što se ne sme reći: da je GDPR brisanje moguće. Za postojećih 30 vektora
sistem ne zna čiji su, i to se **ne popravlja nagađanjem**.

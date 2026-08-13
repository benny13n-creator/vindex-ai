# BETA-DATA-PINE-02 — LEGACY IDENTITY RECONSTRUCTION + WRITER CLOSURE

# VERDICT

## 🟡 YELLOW

Zatvoren je **STOP uslov iz §4** koji nijedan raniji sprint nije video: isti
dokument je kroz dva legalna pipeline-a dobijao **dva identiteta**. Uvedena je
jedna kanonska normalizacija, sistemska brava protiv proizvoljnog ID-a, i
fail-closed brana nad globalnim brisanjem.

Nije GREEN zato što **produkcijska mutacija nije izvedena** — i ne sme biti bez
vaše odluke. Uz to je nađena posledica backfill-a koju treba svesno prihvatiti
pre nego što se izvede (PINE02-F1).

```
BASELINE:              053c3cc4
TEST COUNT:            5400 → 5418   (+18)
MIGRATIONS:            0
PRODUCTION MUTATIONS:  0   — nijedan UPDATE, DELETE, upsert, reindex
```

---

# A–K — ODGOVORI

| | Pitanje | Odgovor |
|---|---|---|
| **A** | 43 dokumenta — kanonski heš izračunljiv? | **43 izračunljivo, 0 nije.** 19 različitih vrednosti, **0 sudara**, 43 različita ID-a vektora |
| **B** | 30 orphana — dokazivo mapirano? | **0 mapirano, 30 `ORPHAN_UNIDENTIFIABLE`** |
| **C** | Za svaki mapirani orphan: dokaz | **nema ih** — v. §Orphani |
| **D** | Bezbedno popuniti `content_sha256` za 43? | **Kao podatak — da. Kao promena ponašanja — ne bez vaše odluke** (PINE02-F1) |
| **E** | Bezbedno fizički obrisati ijedan postojeći vektor? | **NE.** Nijedan od 30 nema dokaziv identitet |
| **F** | Koliko od 19 pisača koristi kanonski identitet? | **1** (`uploaded_doc/ingest.py`) — ali sada je **jedini put kroz koji ijedan runtime pisač prolazi** |
| **G** | Koliko ih još krši ugovor? | **18**, od toga **15 su CLI skripte nad javnim korpusima**, 3 su runtime |
| **H** | Postoji li production path za globalni delete? | **Više ne bez brane** — v. §7 |
| **I** | Da li svaki production upsert fail-closed kad identitet nije validan? | **DA** za sve koji idu kroz `ingest_session`; dokazano nad 6 oblika nekanonske vrednosti |
| **J** | Koja tačno produkcijska mutacija je potrebna sledeće noći? | **43 `UPDATE`-a nad `predmet_dokumenti.content_sha256`** — SQL napisan, **nije izvršen** |
| **K** | Sledeći blokator posle PINE-02? | **PINE-03**: nijedan dokument nema vektore, pa delete nema šta da briše — treba re-ingest, pa DELETE endpoint |

---

# §4 — STOP USLOV KOJI JE BIO STVARAN

Mandat kaže: *„Ako dva pipeline-a mogu proizvesti različit tekst za isti
dokument: STOP."* To nije bila teorija.

`uploaded_doc/extractor.py` u OCR grani vraća **dve različite reprezentacije
istog dokumenta**:

```python
ocr_text = "\n\n".join(p for p in ocr_pages if p)     # :247  prazne strane ISPADAJU
return ocr_text, False, True, ocr_pages, ocr_confidence  # :250  ocr_pages ih ZADRŽAVA
```

`api.py` hešira `text`. `routers/smart_intake.py` za segment hešira
`"\n\n".join(pages[a:b])`. Skenirani PDF sa **jednom** neprepoznatom stranom je
dovoljan:

```
api.py       -> 'Prva strana.\n\nTreca strana.'      -> 9b6c3ee4...
smart_intake -> 'Prva strana.\n\n\n\nTreca strana.'  -> 478efa88...
```

## Popravka: `kanonski_tekst()` — jedna funkcija, jedan oblik

NFC · prelomi reda (CRLF/CR → LF) · rep reda · **3+ uzastopnih preloma → 2** ·
rubovi. Poslednje je ono što zatvara razliku između dva pipeline-a.

Kontrolisano da normalizacija **ne spaja** stvarno različite dokumente, i da je
idempotentna.

Dva stara ID-02 testa su **namerno prevedena, ne oslabljena**: tvrdila su da rep
reda i CRLF daju različit identitet — a baš je ta osetljivost proizvela
razilaženje. Zamenjeni su izričitom suprotnom tvrdnjom.

---

# §1 — 43 DOKUMENTA: 43/43 RECONSTRUCTABLE

Sva četiri ulaza u identitet stoje u samom redu:

| Ulaz | Stanje |
|---|---|
| `tekst_sadrzaj` | **43/43 popunjen**, 77–580 znakova |
| `predmet_id` | 43/43 |
| `chunk_index` | 0 — izmereno produkcijskim `chunk_document`, `total_chunks == 1` na 43/43 |
| `CHUNK_SCHEMA_VERSION` | 1 |

**Bez skraćivanja:** 0 na granici 100.000, najduži **580** znakova.

## §2 — dve tvrdnje razdvojene, kako mandat traži

| Tvrdnja | Status |
|---|---|
| **T1** — identitet se može izračunati danas | **DOKAZANO** |
| **T2** — istorijski vektor je dobio taj ID | **OBORENO**, ne samo nedokazano |

T2 je oboren merenjem: **516 prefix-sondi (43 × 12 namespace-ova) → 0 pogodaka**;
obrnut smer, 430 generisanih ID-eva ∩ 30 orphana = **0**.

Uzrok nađen u istoriji koda: `status='sacuvano'` na 43/43 znači da je opalila
grana `_pinecone_ok = False` u `7328c5d3:api.py:3893` — **ingest je pao, vektori
nikad nisu ni napravljeni.** Nema šta da se mapira jer ne postoji.

---

# §5 — ORPHANI: 0/30 MAPIRANO

Sva tri dozvoljena dokaza oborena:

| Dokaz | Rezultat |
|---|---|
| `session_id` ↔ baza | **0 pogodaka** kroz 13 tabela·kolona × 6 × 2 oblika + `ilike`. Najjači kandidat `storage_path='session/{id}'` na 43/43 jeste session id — ali je presek sa 6 orphan sesija **prazan** |
| heš teksta | **0/30** kroz 5 normalizacija, 0 podniz-pogodaka |
| `chunk_index` + broj chunk-ova | **aktivno isključuje** mapiranje: orphani imaju **5** chunk-ova, dokumenti **1**; jedan orphan nosi **5.210** znakova, a najduži red u bazi **580** |

Metapodaci: 9 polja, **0 identitetskih** — nema nijednog `vx_*`, `predmet_id`
ni `content_sha256`.

Uzgredno merenje: svih 6 namespace-ova sadrži **bajt-identičan** skup od 5
chunk-ova. Zabeleženo kao činjenica; **nikakav zaključak o istom dokumentu se
iz toga ne izvodi** — to bi bilo nagađanje.

---

# §3 — PLAN MUTACIJE: 43 SAFE, 0 UNSAFE

`SAFE` je definisan uz četiri **merena** uslova, ne procenu: vrednost dolazi iz
produkcijske funkcije nad tekstom istog reda; nema heuristike; **0 sudara**
`(predmet_id, verzija)`; kolona je NULL pa se ništa ne prepisuje.

SQL: `docs/beta_gate/PINE_02_BACKFILL_content_sha256.sql` — 43 `UPDATE`-a plus
rollback. **Nije izvršen.** Sam sebe prekida ako pre upisa ne zatekne tačno 43
NULL reda, i ako posle upisa ostane ijedan NULL ili nekanonska vrednost.

## PINE02-F1 (HIGH) — posledicu backfill-a treba svesno prihvatiti

Nalaz koji nijedan raniji sprint nije naveo:
`routers/smart_intake.py:1348-1388` koristi **baš tu kolonu kao kapiju**. Dok je
NULL, kapija je mrtva.

Izmereno: **19/19 različitih sadržaja već postoji u ≥2 predmeta** (0 duplikata
unutar istog predmeta), svih 43 pod **jednim** `user_id`. Čim se kolona popuni,
svaki budući Smart Intake upload tih sadržaja ide u
`duplikat_u_drugom_predmetu` → review — pozivajući se na redove koji ni sami
nemaju nijedan vektor.

`api.py` je po istom pitanju bezbedan — njegova provera je informativna i ne
menja tok.

**Provereno da backfill ne može izazvati brisanje:** produkcijski
`_izlistaj_po_prefiksu` nad stvarnim redom vraća `[]`, pa delete servis posle
backfill-a daje `ALREADY_ABSENT`.

**Provereno da normalizacija iz ovog sprinta ne menja nijednu vrednost:**
baseline modul iz `git show 053c3cc4` upoređen naporedo sa radnim stablom —
**43/43 identično.** SQL literali važe pod obe verzije.

---

# §7 — BRANA NAD GLOBALNIM BRISANJEM

`scripts/ingest_case_law.py` je imao **dve** rollback grane sa
`delete(delete_all=True, namespace="sudska_praksa")`. Napisane su kad je taj
namespace bio prazan i punio ga je samo taj skript. Danas u njemu stoji
**407.795 vektora iz tri izvora**.

**Namerno NISAM sužavao brisanje na „svoje" vektore.** To bi tražilo dokaz o
opsegu koji ne postoji, a §7 izričito zabranjuje pretvaranje globalnog brisanja
u „malo sigurnije" bez dokazanog opsega.

Brana radi jedino što je pošteno: izmeri koliko bi nestalo, odbije, i traži
izričitu dozvolu. **„Ne znam koliko ih ima" nikad ne postaje „slobodno briši"** —
neuspelo merenje je odbijanje.

---

# §8 — SISTEMSKA BRAVA

Svaki upsert kroz `ingest_session` mora imati kanonsku verziju; sve ostalo je
odbijeno **pre ijednog upisa**. Dokazano nad 6 oblika nekanonske vrednosti:
heš bajtova od 64 znaka, velika slova, ne-heks, prekratko, predugačko,
proizvoljna oznaka pisača. Izostavljena verzija je odbijanje, ne fallback.

---

# §9 — MUTATION RESULTS

| # | Mutacija | Ishod |
|---|---|---|
| 1 | ukloni kanonski heš (normalizaciju) | **7 pada** |
| 2 | vrati pun 64-znakovni heš | **35 pada** |
| 3 | ukloni verziju ekstrakcije | **1 pada** |
| 6 | ukloni chunk index iz ID-a | **14 pada** |
| 7 | ukloni schema version iz ID-a | **1 pada** |
| 11 | dozvoli pisaču proizvoljan ID | **prvo 0 → testovi popravljeni → 6 pada** |
| 12 | vrati `zip` truncation | **3 pada** |

## Mutacija 11 me je uhvatila

Nije obarala ništa jer **svi testovi prosleđuju kanonsku vrednost**, pa uklonjena
provera nije imala šta da uhvati. §9 nalaže da se istraži test, ne da se menja
produkcija. Dodati su testovi koji voze **pravi** `ingest_session` sa
nekanonskim vrednostima.

---

# OPEN FINDINGS

| ID | Nalaz | Nivo |
|---|---|---|
| **PINE-A** | `content_sha256` prazan na 43/43 — SQL spreman, **čeka odluku** | **RED (blokiran na odluci)** |
| **PINE-B** | nijedan dokument nema vektore; DELETE endpoint ne postoji | **RED** |
| **PINE02-F1** | backfill oživljava mrtvu kapiju duplikata u `smart_intake` | **HIGH — traži svesnu odluku** |
| **PINE02-F2** | ne može se proveriti da li je `tekst_sadrzaj` bio **ceo** sadržaj fajla: `velicina_kb` je 35–36 KB na svih 43, tekst do 580 znakova, a original ne postoji | **HIGH** |
| **PINE-D** | tri sanitizera ID-a pišu u isti `sudska_praksa` namespace | HIGH |
| **PINE-G** | 6 pisača ima identitet **slep na sadržaj** (MD5 nad `v2\|{zakon}\|{clan}\|{stav}`) | MEDIUM |

**PINE02-F2 zaslužuje da se ne prećuti:** `extractor.py` je od tada menjan 5
puta, a `EXTRACTION_VERSION=1` uveden tek 3 nedelje kasnije. Identitet izračunat
danas je identitet **teksta koji stoji u bazi**, a ne dokazano identitet
originalnog fajla. Za GDPR svrhe to je dovoljno; za tvrdnju „ovo je taj
dokument" nije.

---

# J — TAČNA PRODUKCIJSKA MUTACIJA KOJA SE TRAŽI

> **43 `UPDATE`-a nad `predmet_dokumenti.content_sha256`.**
> Fajl: `docs/beta_gate/PINE_02_BACKFILL_content_sha256.sql`
> Nije izvršen. Traži vašu izričitu potvrdu, uz svesno prihvatanje PINE02-F1.

---

# K — SLEDEĆI BLOKATOR

**PINE-03.** Backfill zatvara PINE-A, ali **ne pravi nijedan vektor** i ne
zatvara PINE-B. Posle njega delete servis i dalje vraća `ALREADY_ABSENT` za svih
43 — jer vektora nema.

Redosled: backfill → **re-ingest 43 dokumenta** (prvi upis ikad kroz kanonski
put) → autorizovan DELETE endpoint.

---

# ZAVRŠNA REČ

Cilj sprinta nije bio da se očiste 43 reda nego da Vindex dobije trajno ispravan
identity lifecycle. To je postignuto: postoji jedna kanonska normalizacija, jedna
funkcija identiteta, brava koja odbija svaki nekanonski ID pre upisa, i brana
koja ne dozvoljava globalno brisanje bez dokaza.

Ali brojka koja opisuje stvarnost i dalje nije broj testova: **nijedan od 43
dokumenta nema nijedan vektor, a nijedan od 30 vektora nema dokument.** Ovaj
sprint je pripremio da to više nikad ne nastane — nije to popravio.

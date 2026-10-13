# OCR001 — pouzdan prijem dokumenata, OCR i prikačivanje: zatvaranje

**Polazište:** `main` = `f0186c18acafbecc2a0955d08b7118d7fef2d3db` (PR #20 spojen). Produkcija: proverljiv dokaz o tačnom SHA koji radi na Render-u nije dostupan iz ovog okruženja (nema Render pristupa). **UNKNOWN.**
**Grana:** `fix/ocr001-document-ingestion-reliability`, Draft PR #21. **Završni kandidat (kod): `7a9b2873`.** Ništa nije spojeno ni pušteno. Nema migracija. Produkcioni podaci nisu dirani.

Oznake: **PROVEN** (reprodukovano testom ili merenjem), **INFERRED** (iz koda, nije reprodukovano), **UNKNOWN**.

## 1. Korenski uzrok

### Prikačivanje (QA posao `27251467-0a46-4121-af72-7926b10c3d7d`)

- **PROVEN — mehanizam stanja.** Svaka neočekivana greška u `routers/smart_intake.py::_finalize_intake_job_core` posle `claim_intake_finalize` (migracija 092/095) izlazila je kao 500, a zauzeće (`finalizing_at`) se nije oslobađalo. Ostaje tačno stanje iz incidenta: `status=completed`, `predmet_id=NULL`, `assimilation_complete=false`, `finalizing_at` postavljen, 0 dokumenata. Isto stanje ostavlja i proces ubijen posle zauzeća. Reprodukovano u `tests/test_ocr001_finalizacija.py`.
- **PROVEN — nekonzistentan UI.** Posle 5xx greške V2 je ponovo čitao posao (`completed`, bez `predmet_id`) i nudio „Prikači ovom predmetu“, a server je narednih 120 s odgovarao 409 („Posao trenutno nije u stanju…“). Posle osvežavanja stranice posao se gubio iz liste.
- **PROVEN — lažni uspeh (drugi put, nije incident).** Ako upis u `predmet_dokumenti` ne uspe unutar petlje (izuzetak se tamo hvata), ruta je vraćala `200 ok:true`, a posao je dobijao `predmet_id`. V2 je tada javljao „Dokument je prikačen predmetu“ i „Prikačeno ovom predmetu“, iako u bazi nije bilo dokumenta. Dokazano stvarnim V2 /app nad stvarnim `api.app` na starom kodu: `uspeh:Dokument je prikačen predmetu…`, `dokumenti=0`.
- **PROVEN — duplikat predmeta.** Posle „otvori predmet iz dokumenta“ bez upisanog dokumenta, ponovni pokušaj je otvarao DRUGI predmet: oporavak je čitao samo `predmet_dokumenti`, ne i `predmet_id` posla.
- **PROVEN — BETA-DEF-003.** Odbijen predmet (404) zaključavao je posao na 120 s.
- **UNKNOWN — tačan izuzetak u produkciji.** Nemam pristup Render logovima, pa se nije moglo utvrditi da li je u 18:28:33Z bio pad baze, istek vremena, ubijen radnik (OOM, redeploy) ili nešto drugo.
- **INFERRED — kandidat za uzrok.** Finalize ponovo pokreće ceo OCR unutar HTTP zahteva (`extract()` nad celim fajlom), dok 4 gunicorn radnika istovremeno pokreću i intake worker sa OCR-om (300 dpi, `srp+srp_latn+eng`). Ubijanje procesa zbog memorije posle zauzeća daje tačno posmatrano stanje, ali to nije dokazano.

### OCR

- **PROVEN.** `uploaded_doc/extractor.py::extract_pdf` je PDF sa ispravnim digitalnim tekstom kraćim od 80 znakova (dostavnica od tri reda) tretirao kao sken. OCR je zamenjivao digitalni tekst. Ako OCR pukne, nije dostupan ili vrati manje od 100 znakova, ishod je bio `""` i „OCR nije uspeo“, pa dokument nije imao nijedan podatak. Pojavilo se u e2e testu ove misije: „Ostalo (pouzdanost 0%) · tekst pročitan OCR-om“ za digitalnu dostavnicu.
- **PROVEN.** Strana mešovitog PDF-a čiji OCR ne uspe ostajala je prazna, a posao je išao u `completed` bez ikakvog signala. Pouzdanost je prosek samo pročitanih strana.
- **PROVEN.** Bez srpskih paketa `_detect_ocr_lang` tiho prelazi na `eng`. Dockerfile instalaciju paketa toleriše (`|| true`). CI zahteva pakete u produkcionoj slici, ali Render gradi sopstvenu sliku.

### Ekstrakcija

- **PROVEN — mehanizam.** `plaintiff` i `defendant` dolaze isključivo iz modela (`extract_free_text_entities`), bez provere i bez naknadnog mapiranja. Model je primaoca sa dostavnice stavio u `plaintiff`. Ponovni poziv pravog modela nije urađen (plaćen poziv, nema ključa), pa je reprodukovan izlaz modela iz QA nalaza.

## 2. Šta je ispravljeno (commit-ovi)

| Commit | Faza | Izmena |
|---|---|---|
| `9a3b0c97` | A/D | `_finalize_intake_job_core` je granica greške: svaka greška posle zauzeća oslobađa zauzeće uz CAS na trenutak zauzeća i vraća 503. `ok` je true samo za potvrđeno potpuno prikačivanje, uz polje `prikacivanje` (POTPUNO/DELIMICNO/NIJE_PRIKACENO). Nepotpun ishod odmah oslobađa zauzeće. Izabran predmet se beleži pre dokumenata, a nastavak ide u isti predmet i samo u predmet pozivaoca. Paket ne broji neprikačen posao kao uspeh. GET `/jobs/{id}` vraća `prikacivanje` (PRIKACENO/U_TOKU/NEPOTPUNO/NIJE_PRIKACENO) i `potrebne_provere`. V2 prikazuje „Prikačeno“ samo uz potvrdu servera i nudi „Ponovi prikačivanje“. Stanja u toku/prekinuto nemaju dugme. 409 i 5xx ponovo čitaju stanje, ništa se ne šalje samo od sebe. |
| `3dc97227` | B | Digitalni sloj ostaje kad OCR nije duži (po strani) i kad OCR pukne. `necitljive_strane_pdf`: strana < 30 znakova sa vidljivim sadržajem (≥ 0,5 % tamnih piksela na 50 dpi) nije pročitana; prazna strana nije greška. Worker takav dokument, kao i OCR bez srpskog paketa, šalje na pregled (postojeći razlog `ocr_failed`, sa tačnim stranama). Ugovor od 5 elemenata nije menjan. |
| `3d3984bf` | C | Uloga iz modela ostaje samo ako je navedena u tekstu: sve značajne reči imena moraju stajati posle oznake te uloge (latinica/ćirilica, padeži), pre sledeće uloge ili „protiv“. Inače nema tvrdnje (None, pouzdanost 0, ide na pregled). |
| `2102e228` | E | Sintetički QA korpus, merenje stvarnim Tesseract-om u produkcionoj slici, CI izveštaj `OCR001 image`. |
| `311cf159` | B | Posle CI merenja: (1) dokument kome OCR ništa ne dodaje, a ispod je praga, ostaje označen kao nepročitan (`is_scanned=True` → pregled; `api.py`/`dokument.py` i dalje 422), ali se njegov digitalni tekst više ne briše — zadržan postojeći ugovor `test_extractor_pdf_empty`. (2) Prosečna OCR pouzdanost < 0,75 šalje dokument na pregled: okrenut sken je davao CER 82 % uz ≥ 30 znakova „teksta“. |
| `7a9b2873` | E | CI izveštaj navodi instalirane OCR jezike (samo test). |

**Nije menjano:**
- taksonomija (`other` za dostavnicu i zapisnik je ispravan izlaz postojećeg skupa);
- regex broja predmeta (`TEST-2026-014` nije sudski broj; stvarni srpski oblici prolaze);
- logika rokova (već isključuje „dostavljeno“ i nepotvrđene AI rokove iz podsetnika);
- šema, OCR provajder, model.

## 3. Osporeno i odbačeno

- „BETA-DEF-003 je uzrok incidenta“ — **odbačeno kao dokaz**. Mehanizam je isti (zauzeće se ne oslobađa), ali u V2 predmet je osnivačev i 404 nastaje samo za obrisan predmet. Ispravljeno je jer je ista klasa.
- „Regex broja predmeta je pokvaren jer ne hvata `TEST-2026-014`“ — **odbačeno**: to nije sudski broj. „P 4321/2026“, „П 4321/2026“, „Gž 123/2025“ i „Rev 77/2024“ prolaze (test).
- „`other` sa 30 % je pogrešna klasifikacija“ — **odbačeno**: taksonomija nema dostavnicu ni zapisnik.
- „Postoji naknadno mapiranje koje firmu pretvara u tužioca“ — **odbačeno**: jedini izvor je model.
- „Sporni datumi postaju rok“ — **odbačeno testom**: `extract_deadline` vraća `None` za sva tri dokumenta, a AI rok bez potvrde ne prolazi `filtriraj_izvrsive`.

## 4. OCR rezultati

Mereno stvarnim Tesseract-om 5.5.0 u CI-ju, `7a9b2873`/`311cf159`. Tri izmišljena dokumenta i dva otežana slučaja; to **nije** opšta tačnost srpskih pravnih dokumenata. CER/WER su stopa greške po znaku/reči posle NFKD normalizacije. Trajanje je jedna strana na CI runner-u.

**Produkciona slika** (isti Dockerfile kao Render; `srp+srp_latn+eng`):

| Slučaj | CER | WER | Pouzdanost | Kritično | Strane | Pregled | s |
|---|---|---|---|---|---|---|---|
| A tužba, digitalna | — (bez OCR-a) | — | — | 47.912,00 RSD, 17.03.2025, TEST-2026-014 ✓ | 1/1 | vrsta nesigurna | — |
| B dostavnica, ćirilični sken | 0,028 | 0,077 | 0,918 | 25.03.2025 ✓, primalac ✓ | 1/1 | vrsta nesigurna | 1,0 |
| C mešovit, sken strana 2 | 0,000 | 0,000 | 0,948 | oba datuma ✓ | 2/2 | vrsta nesigurna | 0,96 |
| Okrenut sken 90° | 0,824 | 1,000 | 0,45 | ✗ | 2/2 | **„OCR pouzdanost 45 %“** | 1,24 |
| Bled sken (kontrast 0,25) | 0,000 | 0,000 | 0,947 | ✓ | 2/2 | — | 0,96 |

**Okruženje bez srpskog paketa** (posao `OCR proof`, samo `eng`): ćirilica CER 0,71–0,92 uz pouzdanost 0,25–0,62. Svaki takav dokument dobija pregled „OCR bez srpskog jezičkog paketa“, a OCR001 i „OCR pouzdanost X %“. Ranije je takav tekst prolazio kao pročitan.

**Ceo tok** (stvaran OCR → worker → pregled → prikačivanje, model namerno vraća primaoca kao tužioca):
- 3/3 dokumenta su u predmetu i sva kritična mesta (iznos, oba datuma, oznaka) su u tekstu predmeta;
- `tuzilac` je `null` za sva tri;
- nijedan red u hronologiji (nema roka).
- Klasifikacija: tužba = `lawsuit`, dostavnica i zapisnik = `other` (taksonomija nema te vrste); sve tri ispod praga automatskog prihvatanja → pregled.

**Jezički paketi u produkcionoj slici:** `srp`, `srp_latn` i `eng` dokazani u CI-ju (`VINDEX_EXPECT_SRP=1`). Render gradi sopstvenu sliku i taj build nije posmatran; ako paket tamo nedostaje, OCR001 to sada označava na svakom OCR dokumentu.

## 5. Prikačivanje — trajno ponašanje

| Scenario (stvarne rute, stvaran worker) | Pre | Posle |
|---|---|---|
| Istek naredbe baze posle zauzeća | 500, zauzeće 120 s, 409 | 503, zauzeće oslobođeno, ponovni pokušaj odmah → 1 dokument |
| Proces ubijen pre/posle upisa dokumenta | stanje iz incidenta, UI „spremno“ | `U_TOKU` (bez dugmeta), 409; posle zastarevanja nastavak → 1 dokument |
| Upis dokumenta ne uspe (ruta završi) | `200 ok:true`, UI „prikačen“, 0 dokumenata | `ok:false`, `NIJE_PRIKACENO`, UI „NIJE prikačen“, ponovni pokušaj → 1 |
| Nov predmet, upis ne uspe, ponovni pokušaj | drugi predmet | isti predmet, 1 dokument |
| Odbijen tuđi predmet, pa sopstveni | 409 120 s | 200 odmah |
| Izgubljen odgovor posle uspeha | — | `already_finalized`, bez ponovne ekstrakcije, 1 dokument, 1 vektor |
| Paket sa neprikačenim poslom | „uspešno 1“ | „uspešno 0“ |

## 6. Bezbednost

- Tuđ korisnik ne može da finalizuje niti da zauzme tuđ posao (404, zauzeće nedirnuto).
- Nastavak iz stanja posla ide samo u predmet pozivaoca (namerno oštećen `predmet_id` → 404).
- Broj tuđeg predmeta i „instrukcija“ u tekstu dokumenta ne vode u tuđ predmet: B otvara sopstveni.
- Sadržaj dokumenta ne ide u log (kanarinac, `caplog` na nivou DEBUG).
- Telo 5xx greške je maskirano: bez SQLSTATE-a i bez poruke baze.
- e2e: nijedna veza van 127.0.0.1, svi upisi pripadaju A, B ne vidi predmet A.

## 7. Testovi i dokazi

**Novi testovi:**

| Fajl | Broj | Na `main`-u (negativna kontrola) |
|---|---|---|
| `tests/test_ocr001_finalizacija.py` (stvarne rute, stvaran worker, kvarovi na granici baze) | 13 | 10 pada; 3 čuvara ponašanja prolaze |
| `tests/test_ocr001_ocr_korpus.py` (bez Tesseract-a 21; sa Tesseract-om +5 u CI-ju) | 26 | 10 pada; 11 čuvara ponašanja prolazi |
| `frontend-v2-ng/tests/live-prijem.mjs` grupa H | 7 | stari UI pada (lažni „prikačen“, nema „Ponovi“) |
| `e2e:prijem-oporavak` — stvaran V2 /app nad stvarnim `api.app`, kvarovi baze i ubijen proces | 18 | stari kod: `uspeh:Dokument je prikačen predmetu`, a u bazi `dokumenti=0` |

**Mutacije:** 19/19 uhvaćeno. Obuhvataju:
- oslobađanje zauzeća i 404 granu;
- `ok` uvek true i nepotpuno bez oslobađanja;
- nastavak iz posla, proveru vlasnika i ranu namera-upis;
- paket i stanje U_TOKU;
- zamenu digitalnog teksta, odbacivanje na padu i oznaku ispod praga;
- prag vidljivog sadržaja, worker koji ignoriše nepročitano i prag pouzdanosti;
- upozorenje o jeziku, kapiju uloge, granicu „protiv“ i pravilo „sve reči“.

Dve su prvo preživele (M10, M11): lokalno nema `pytesseract`, pa test nije ulazio u OCR petlju. Popravljeni su testovi, ne prag.

**Regresija (isto seme, `main` `f0186c18` naspram grane):**

| Provera | Rezultat |
|---|---|
| Lokalno ceo Python paket, `2102e228` | 20 naspram 19 padova; jedini nov `test_extractor_pdf_empty::test_near_empty_pdf_flagged_as_scanned` → ispravljeno u `311cf159` |
| CI Test Suite 3.11 / 3.13, `311cf159` | 174 / 174 (osnovica 174), **0 novih** |
| CI Production Runtime Parity, `311cf159` | 196 (osnovica 196), **0 novih**; Docker build/boot uspeh; OCR u produkcionoj slici 58 prošlo |
| CI Security, `311cf159` | uspeh |
| CI V2 NG, `311cf159` | svih 14 e2e (uključujući `e2e:prijem-oporavak`) prolazi; `verify:live-matrix` 151/152 zbog poznatog `FLAKY-DEMO-PIKSEL` (4 piksela u regionu loga) → pokrenut ponovo samo pali posao, prag nije menjan |
| Lokalno svih 46 V2 paketa (`verify:*` + `e2e:*`) | **46/46 PASS** |

**Završni kandidat `7a9b28737dc0d2d3ee6dd53d6c5647b6dee099e3`:**

| Provera | Run | Rezultat |
|---|---|---|
| Test Suite 3.11 / 3.13 | 38302962751 | 174 / 174, osnovica 174 → **0 novih** |
| Production Runtime Parity | 38302962825 | 196, osnovica 196 → **0 novih**; Docker build/boot uspeh; OCR u produkcionoj slici 58 prošlo, `srp=True`, `srp_latn=True` |
| Security Checks | 38302962752 | uspeh |
| V2 NG | 38302967288 | uspeh (iz prvog pokušaja) |

## 8. Preostali rizici

1. **Finalize ponovo radi OCR unutar HTTP zahteva** (INFERRED kao mogući uzrok incidenta). Tekst iz worker-a se ne čuva, pa izbegavanje traži novu kolonu. Odluka osnivača: čuvati izvučeni tekst (migracija) ili prihvatiti rizik.
2. **Prozor zauzeća je 120 s, a finalize velikog skena može trajati duže.** ZATVOREN u aplikaciji završnim gejtom (§11): zauzeće se potvrđuje i obnavlja pre svakog nepovratnog upisa. Ostaje jedan prozor koji zatvara samo predlog migracije 138 (§11).
3. **Ukupno trajanje OCR-a nema gornju granicu** (INFERRED): 500 strana × (45 s + 30 s) po strani. Posao stariji od 300 s u obradi `reap_stale_jobs` vraća u red dok ga prvi radnik još obrađuje.
4. **Uloga stranke iz pravog modela** nije ponovo merena (plaćen poziv). Kapija je deterministička i dokazana nad izlazom modela iz QA nalaza.
5. **Okrenut sken se ne ispravlja, samo označava** (pouzdanost 0,45 → pregled). Automatsko okretanje (Tesseract OSD) je nova mogućnost i traži odluku.
6. **Kratak dokument ispod praga** (npr. dostavnica od tri digitalna reda) i dalje ide na pregled kao „OCR nije uspeo“, kao i ranije. Razlika je u tome što se njegov tekst više ne gubi pri prikačivanju.
7. **Strana sa ≥ 30 znakova digitalnog teksta i skeniranim telom** (npr. digitalno zaglavlje nad skenom) i dalje se ne OCR-uje. Nije izmereno na stvarnim dokumentima.
8. **Produkcija: nije LIVE VERIFIED.**

## 9. Postupak oporavka QA posla `27251467` (izvršava se tek uz odobrenje osnivača)

Bez ijednog direktnog upisa u bazu. Ništa se ne briše i ne menja ručno.

1. **Provera, samo čitanje:** posao je `completed`, `assimilation_complete=false`, `finalizing_at` stariji od 2 minuta. Ako je `assimilation_complete=true`, postupak se ne radi.
2. V2 → QA predmet → Prijem → ponovo otpremiti isti fajl `03_zapisnik_mesoviti_pdf.pdf`. Isti sadržaj daje isti posao, bez duplikata.
3. Ako stoji „Prikači ovom predmetu“ ili „Ponovi prikačivanje“, kliknuti jednom. Zauzeće je zastarelo, pa ga postojeći `claim_intake_finalize` preuzima. Isti sadržaj se ne upisuje dvaput (`content_sha256`).
4. Proveriti listu dokumenata predmeta i posle osvežavanja. Uspeh je samo „Prikačeno ovom predmetu“; sve drugo se prijavljuje bez ponovnog klika.
5. Isto za dokumente 01 i 02 ako nisu u predmetu.

Pre puštanja OCR001 isti postupak radi i na sadašnjoj produkciji, ali tada neuspeh može ponovo ostaviti zaključan posao (120 s) i UI može tvrditi „prikačen“ bez dokumenta. Zato se preporučuje tek posle odobrenog puštanja.

## 10. Odluke osnivača

1. Odobrenje spajanja tačnog kandidata iz §11 (zamenjuje `7a9b2873`; spajanje na `main` pokreće puštanje u produkciju).
2. Odobrenje postupka oporavka QA posla (§9), posle puštanja.
3. Rizik 1: čuvanje izvučenog teksta (migracija) da finalize ne radi OCR ponovo.
4. Rizik 3: gornja granica ukupnog trajanja OCR-a.
6. Predlog migracije 138 (§11): odobriti ili odbiti. Kod je ispravan i bez nje.
5. Pristup Render logovima za utvrđivanje stvarnog izuzetka u 18:28:33Z.

## 11. Završni gejt: konkurentna finalizacija istog posla (A i B)

**Pitanje:** može li isti dokument istog posla biti upisan dvaput kad prvi finalize proces radi duže od 120 s, a drugi preuzme zastarelo zauzeće?

**PROVEN na kodu pre ove izmene** (`tests/test_ocr001_konkurentna_finalizacija.py`, stvarne HTTP rute, dva zahteva u dve niti, kontrolisan sat, barijere na granici baze, jedinstveni indeksi tačno iz migracija 094/106 sa Postgres semantikom NULL-a). Nesegmentiran dokument (`source_intake_job_segment_id = NULL`), oba redosleda upisa:

| Mera | Pre ispravke | Posle ispravke |
|---|---|---|
| Redova u `predmet_dokumenti` za posao | **2** (redni broj 1 i 2, isti `content_sha256`) | 1 |
| Novih predmeta (novi predmet iz dokumenta) | 1 | 1 |
| `NewEvidenceRegistered` događaja | **2** | 1 |
| `DocumentAccepted` | 1 (stabilan identitet po poslu) | 1 |
| Pinecone: pozivi / identiteta vektora | 2 / 1 (isti ID-evi, prepis) | 2 / 1 |
| A | 409 posle upisa („preuzeta… ručna provera“) | 409 PRE upisa („nije ništa upisao“) |
| B | 200 `ok:true`, „1 dokument“ — **netačno, u predmetu su 2** | 200 `ok:true`, 1 dokument |
| `assimilation_complete` / `finalizing_at` | true / B-ov token | true / B-ov token |
| Ponovni pokušaj posle trke | 200, već prikačeno, 2 reda | 200, već prikačeno, 1 red |

Uz to, dva dodatna dokazana kvara iste klase:
- **Segmentiran dokument:** indeks 094 odbija drugi upis, ali kod je odbijanje tretirao kao „kolona ne postoji“ i prelazio na užu varijantu upisa bez `source_intake_job_segment_id`, `content_sha256` i `source_intake_job_id` — isti dokument drugi put, **bez identiteta**. Isto bi se desilo i sa bilo kojim novim jedinstvenim indeksom: **migracija sama ne bi bila dovoljna.**
- **Zastareo snimak posla:** B je stanje posla čitao PRE zauzeća; dokument bez broja predmeta tada je mogao da otvori drugi predmet.

**Pravi PostgreSQL** (`tests/test_ocr001_trka_postgres.py`, privremen klaster 17, doslovan DDL iz 094/095/106): `claim_intake_finalize` daje zauzeće B-u dok A radi; SELECT-pa-INSERT dva procesa daje 2 reda; indeks 094 se zaobilazi upisom bez kolone segmenta; poruka 23505 ima isti oblik kao emulacija. Izvršeno lokalno; u CI se preskače ako nema `psycopg`.

**Ispravka** (`routers/smart_intake.py`, bez migracije):
1. `_potvrdi_zauzece` pre otvaranja novog predmeta i pre svakog upisa dokumenta. Dok je proteklo vreme od zauzeća (monotoni sat zabeležen PRE poziva zauzeća) manje od 120 − 30 s, niko drugi ne može da ga preuzme. Posle toga se obnavlja: CAS oslobađanje sopstvenog tokena, pa novo zauzeće; svako tuđe zauzeće u međuvremenu promenilo je token, pa proces odustaje pre upisa (409). Dug finalize bez takmaca se obnavlja i završava.
2. Nastavak čita predmet iz reda koji vraća zauzeće (`RETURNING *`), ne iz snimka pre zauzeća.
3. 23505 na indeksu identiteta (sve osim `redni_broj`) više ne pada na užu varijantu: postojeći red istog sadržaja u istom predmetu istog korisnika se poveže kao već prikačen.

**Preostali prozor (samo baza ga zatvara):** upis poslat dok je zauzeće važilo, a koji „visi“ u mreži ili bazi duže od 30 s i stigne posle B-ovog upisa. Test `test_zaglavljen_poslat_upis_zatvara_samo_indeks_baze` to dokumentuje: bez indeksa 2 reda, sa predlogom 138 jedan red. Predlog: `docs/v2-execution/OCR001_PREDLOG_MIGRACIJE_138.sql` — provera postojećih podataka, primena, potvrda, rollback. Opseg je samo Smart Intake (`source_intake_job_id IS NOT NULL`); ručno otpremanje (api.py) koje svesno dozvoljava isti sadržaj dvaput nije pogođeno (dokazano na pravom Postgres-u). NIJE primenjen.

**Negativna kontrola:** na kodu pre ispravke pada 12 od 14 novih testova trke; prolaze samo test koji dokumentuje preostali prozor bez indeksa i test tuđeg korisnika. **Mutacije:** 10/10 uhvaćeno (bez provere pre upisa, bez provere pre predmeta, snimak pre zauzeća, uža varijanta posle 23505, sukob bez povezivanja, provera uvek prolazi, obnova bez CAS-a, token završnog CAS-a, progutan gubitak zauzeća, rezerva nula).

**Bezbednost:** tuđi korisnik u trci dobija 404 i ne dira zauzeće; A zatim uspešno završava, vektori samo u A-ovom predmetu i prostoru imena. Ponovna provera postojećeg reda posle 23505 je ograničena na `user_id` pozivaoca i predmet posla.

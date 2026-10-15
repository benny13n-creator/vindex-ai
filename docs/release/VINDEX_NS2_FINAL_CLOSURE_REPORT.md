# VINDEX — NS2 FINAL BETA RELIABILITY CLOSURE — PR #34 (2026-10-15)

**Verdikt: `GO_FOR_FOUNDER_REVIEW`**. Nijedan prihvaćen PDF ni slika nisu oborili radnika u izmerenoj konfiguraciji (512 MiB, gunicorn, 1 radnik). Izvoz se ne isporučuje bez dokazanog upisa u audit log. Sva tri zadatka su prošla nezavisni pregled. Spajanje i puštanje i dalje čekaju odluke osnivača iz H i G.

**Šta nije urađeno.** Ništa nije spojeno u `main`, ništa nije deployovano, Render nije menjan, nijedna migracija nije pokrenuta, nijedan produkcioni zapis nije menjan. Ništa nije LIVE VERIFIED.

Oznake: **PROVEN** (izmereno ili testirano), **INFERRED** (izvedeno), **ASSUMED** (pretpostavljeno), **UNKNOWN** (nepoznato). Ograničenja:
- Prolaz unit testa nije dokaz o memoriji.
- Prolaz CI-ja nije dokaz da je produkcija ispravna.

Repo: https://github.com/benny13n-creator/vindex-ai · PR: https://github.com/benny13n-creator/vindex-ai/pull/34

---

## A. Stanje repozitorijuma
| Stavka | Vrednost | Status |
|---|---|---|
| `origin/main` | `eb1a34a69f4eb3fbcc393dc991b3fb6760919800`, nepromenjen; produkcija `/health` prijavljuje `commit: eb1a34a` | PROVEN |
| PR #34 na početku | `da345f26d21e8d0d1d67f7ea61a000f9f19c5af0` (potvrđeno u fazi 0) | PROVEN |
| PR #34 kod | [`7bc15515`](https://github.com/benny13n-creator/vindex-ai/commit/7bc15515); fast-forward bez force-push-a; ovaj izveštaj je sledeći commit (samo dokumenti) | PROVEN |
| Stanje PR-a | Draft, nije spojen | PROVEN |

Commitovi ovog ciklusa (svaka ispravka je na svojoj grani, a zatim spojena merge commitom):
| Zadatak | Commitovi | Spoj |
|---|---|---|
| C — audit izvoza, fail-closed | [`6e3d64a3`](https://github.com/benny13n-creator/vindex-ai/commit/6e3d64a3) | `ef386cf1` |
| B — format samostalne slike | [`dfae3dbe`](https://github.com/benny13n-creator/vindex-ai/commit/dfae3dbe), [`02cc9419`](https://github.com/benny13n-creator/vindex-ai/commit/02cc9419) | `893a5c80` |
| A — memorija PDF rastera | [`d7a4e4a8`](https://github.com/benny13n-creator/vindex-ai/commit/d7a4e4a8), [`88c593a0`](https://github.com/benny13n-creator/vindex-ai/commit/88c593a0), [`76d54093`](https://github.com/benny13n-creator/vindex-ai/commit/76d54093), [`cc0a6d6f`](https://github.com/benny13n-creator/vindex-ai/commit/cc0a6d6f) (ispravka nalaza pregleda N1/N2) | `47578018`, `7bc15515` |

Izmenjeni fajlovi (14): `uploaded_doc/extractor.py`, `routers/data_export.py`, `api.py` (+5 linija), `routers/smart_intake.py` (+6 linija) i testovi:
- novi: `tests/test_ns3_a_pdf_raster.py`, `tests/test_ns3b_format_slike.py`, `tests/test_ns3_export_audit_fail_closed.py`;
- prilagođeni stari: `test_ns2b_ocr_jpeg_koeficijenti`, `test_ns2b_export_audit_ordering`, `test_c1_export_stages`, `test_sprint4_silent_failures`, `test_extractor_image`, `test_lawyerday_predmet_upload_images`, `test_smart_intake_upload_validation`.

Bez šeme, migracija, novih servisa, redova čekanja ili izmena pravnog teksta.

Prethodni izveštaj [`VINDEX_NS2_FINAL_RELEASE_GATE_REPORT.md`](VINDEX_NS2_FINAL_RELEASE_GATE_REPORT.md) je bio samo lokalan. Sada je objavljen neizmenjen, uz pregled JPEG zadatka iz tog ciklusa ([`ns2b-evidence/`](ns2b-evidence/)).

## B. PDF OOM — zadatak A
**Status: CLOSED, nezavisni pregled GO WITH NOTES.**

**Gde nastaje opasna alokacija (PROVEN, izvorni kod MuPDF 1.28.2 i merenje)**
- CMYK slike: `page.get_pixmap` smanjuje sliku 2× samo kada je pola veličine i dalje ≥ veličine na rasteru + 2 px. CMYK slika od 30 MP na A4 pri 300 dpi zato se dekodira u punoj veličini: 114 MiB CMYK + 86 MiB RGB konverzije → OOM.
- Umetnute slike (`BI…ID…EI`) MuPDF dekodira u punoj veličini čim interpretira sadržaj strane.

**Ispravka.** `_odbij_pdf_preveliki_raster` radi pre prve rasterizacije, pri dpi-ju koji će se stvarno koristiti, u tri koraka:
1. **Sirovo skeniranje sadržaja**, bez MuPDF interpretera. Pokriva sadržaj strane, ugnježdene forme, šare, meke maske, Type3 i izgled anotacija. Svaki objekat se obilazi jednom, uz budžet od 20.000 posete.
2. **Prolaz kroz MuPDF sa uređajem koji samo beleži.** Za svaku sliku beleži veličinu, tip, smeštaj i JPEG zaglavlje. Broji transparentne grupe i meke maske kao slojeve veličine površine; sabiraju se samo slojevi otvoreni u isto vreme.
3. **Procena vrha memorije strane.** Iznad `MAX_PDF_RASTER_BAJTOVA` = 150 MiB fajl se odbija.

Statusi odbijanja (svaki ima svoju poruku na srpskom):

| Situacija | Poruka |
|---|---|
| Strana prevelika za obradu | postojeća poruka `DocumentSafetyLimitExceeded` |
| Bezbednost se ne može utvrditi | `PORUKA_PDF_NEPROVERLJIV` |
| Fajl nije PDF | `PORUKA_NIJE_PDF` |

Na uploadu sva tri vraćaju **413**. U intake radniku posao se odmah završava kao neuspeh (dead-letter), bez ponovnih pokušaja.

**Šta ova provera košta (PROVEN)**
- 0,6–21 MiB i ≤ 0,08 s po dokumentu, uključujući PDF od 300 strana.
- Pregled je potvrdio da provera ništa ne dekodira i ne puni keš.
- Procena je uvek na ili iznad stvarnog troška: RGB/sivo/JPX 0–3 MiB iznad; CMYK do 12 MiB ispod izmerenog rasta, što je uračunato u izmereni vrh kontejnera.

**Merenja** (produkciona Docker slika, gunicorn, 1 radnik, cgroup 512 MiB, vrh celog kontejnera, 3 ponavljanja, prikazan najviši rezultat). Runda 1: [run 38696441586](https://github.com/benny13n-creator/vindex-ai/actions/runs/38696441586), [sažetak a](ns3-evidence/A_round1_measurement_summary_a.md), [sažetak b](ns3-evidence/A_round1_measurement_summary_b.md). Potvrda: [run 38703852856](https://github.com/benny13n-creator/vindex-ai/actions/runs/38703852856), [sažetak](ns3-evidence/A_round2_confirmation_summary.md). Merna grana: `measure/ns3-pdf-ocr` (`cb91979a`), generatori `ns2_measure/gen*.py`. U obe runde: **0 OOM ubistava** (PROVEN).

Pre ispravke (ista slika, provera isključena):

| Ulaz | Vrh (MiB) |
|---|---|
| CMYK 30 MP u A4 PDF-u | OOM ubijen 3/3 |
| Meka maska | 484,9 |
| CMYK 20 MP | 469,1 |
| RGB 34,6 MP | 451,7 |

Odbijeni ulazi (rednim brojem je naveden fiksni slučaj iz zadatka):

| # | Ulaz | Vrh (MiB) |
|---|---|---|
| 1 | CMYK 30 MP | 297,6 |
| 2 | CMYK 34,6 MP | 301,3 |
| 3 | Progresivni 40 MP | 280,1 |
| 7 | Sken 9 str. + CMYK 30 | 311,7 |
| 8 | 2× CMYK 20 MP | 304,9 |
| 9 | Meka maska | 277,0 |
| 10 | ASCIIHex+DCT / Flate+DCT / Flate CMYK | 278–293 |
| 11 | Umetnuta CMYK 30 MP | 280,2 |
| — | Anotacija | 298,6 |
| — | JPX sivo 600 dpi | 273,9 |
| — | TIFF+PDF poliglot | 275,4 |
| — | Ugnježdene transparentne grupe ×2/×4/×8 | ≤ 274,6 |

Prihvaćeni ulazi (tekst i granice strana nepromenjeni, isti hash teksta između ponavljanja):

| # | Ulaz | Vrh (MiB) | Rezerva (MiB) |
|---|---|---|---|
| — | CMYK 40 MP | 413,2 | 98,8 |
| — | RGB 24 MP | 419,0 | 93 |
| — | JPX u boji, 300 dpi | 425,5 | 86,5 |
| 5 | Sken 10 str. | 395,7 | 116 |
| 6 | Mešovit 6 str. | 384,7 | 127 |
| 8 | 4 slike na strani | 407,3 | — |
| — | A3 | 407,4 | — |
| 11 | Mala umetnuta slika | 378,9 | — |
| 14 | Digitalni PDF 10 str., bez OCR-a, nije odbijen | 283,0 | 229 |
| — | Lanac objekata (dag_22), provera 0,001 s | 355,2 | — |

Obični dokumenti sa providnošću su prihvaćeni:

| Ulaz | Vrh (MiB) |
|---|---|
| Grupa strane (Word/LibreOffice) | 363,7 |
| Sken 300 dpi u grupi | 383,7 |
| Logo + anotacija + grupa | 258,8 |
| Meka maska grafičkog stanja | 359,6 |

Ponavljanje i istovremeni rad:

| # | Scenario | Vrh (MiB) | Rezerva (MiB) |
|---|---|---|---|
| 12 | 4 odbijena pa 4 dobra fajla zaredom (zaključavanja oslobođena) | 430,7 | — |
| 13 | Sken 10 str. + CMYK 30 (odbijen; sken završen) | 403,8 | — |
| 13 | Sken 10 str. + CMYK 40 | 442,1 | 69,9 |
| 13 | Sken 10 str. + RGB 24 | 440,6 | 71,4 |
| 13 | Sken 10 str. + JPX u boji | 446,6 | 65,4 |

**Prihvatni kriterijumi**
- **A1** PROVEN — nijedan prethodno pogubni fiksni slučaj više ne izaziva OOM.
- **A2** PROVEN — testovi zabranjuju rasterizaciju, OCR i (za umetnute slike) interpreter pre odbijanja.
- **A3/A4** PROVEN — tekst, granice strana i OCR legitimnih skenova su nepromenjeni.
- **A5** — pouzdanost OCR-a i pravilo da se OCR entiteti nikad ne prihvataju automatski nisu dirani.
- **A6** PROVEN — odbijanje je terminalno, bez ponovnih pokušaja.
- **A7** — izolacija i identitet dokumenta nisu dirani.
- **A8** — kad dokument radi sam, rezerva je ≥ 86 MiB. U istovremenom radu, na granici, rezerva je 65–71 MiB, ispod internog cilja od 75 MiB, ali bez OOM-a → odluka osnivača (H2).
- **A9** — vidi F.
- **A10** — vidi gore.

**Testovi i mutacije**
- `test_ns3_a_pdf_raster.py` 39/39.
- Mutacije: autor 22/22 ([log](ns3-evidence/A_mutations.txt)); pregled ubio 4/4 svoje.

**Preostalo (nije izmereno kao OOM)**
- Konstruisani bafer šare (tiling pattern) i JBIG2 sa unutrašnjom stranom većom od deklarisane nisu uračunati (INFERRED).
- Precenjivanje (konzervativno):
  - Knockout grupa oko skena je precenjena za ~40 MiB. Jedan sintetički uzorak sa ugnježđenom knockout grupom oko skena od 12 MP je lažno odbijen (PROVEN, sintetički). Da li se to javlja u pravim Word/LibreOffice izvozima: UNKNOWN.
  - Grupa strane dodaje ~33 MiB procene, pa bi sken teži od ~300 dpi u boji unutar grupe bio odbijen (INFERRED).
- Nova (namerna) odbijanja:
  - progresivni 4:2:0 od ~22 MP na celoj strani;
  - RGB na celoj strani ≥ ~26 MP;
  - CMYK na celoj strani ≥ ~15 MP;
  - skenovi u boji od 400 dpi i ≥ 600 dpi;
  - JPX sivo 600 dpi.

## C. Provera formata slike — zadatak B
**Status: CLOSED, nezavisni pregled GO WITH NOTES.**
- **Šta se prihvata.** Samostalna slika (`.jpg/.jpeg/.png`) prolazi samo ako je sadržaj stvarno JPEG ili PNG.
  - Provera puni potpis iz bajtova (`format_slike_po_sadrzaju`) radi pre bilo kog `Image.open`.
  - Kao drugi sloj, svaki `Image.open` dobija `formats=("JPEG","PNG")`.
  - Ekstenzija i MIME koji šalje klijent se ne uzimaju u obzir.
- **Gde se odbija.**

  | Ruta | Ishod | Kada |
  |---|---|---|
  | Upload u predmet (`api.py`) | **415** | pre čuvanja fajla |
  | Smart Intake | `ok:false` | pre čuvanja i pre pravljenja posla |
  | Intake radnik | terminalni neuspeh | posle 1 pokušaja |

  Poruka: „Fajl nije prava JPEG ili PNG slika — njegov sadržaj je u drugom formatu, bez obzira na ekstenziju…“
- **Odbijeni maskirani formati (PROVEN):**
  - TIFF→.jpg (+1 MiB umesto +333 MiB);
  - TIFF→.png, GIF→.jpg, BMP→.png, WebP→.jpg, PDF→.jpg;
  - nasumični bajtovi i prazan fajl;
  - pogrešan MIME;
  - JPEG SOI + TIFF telo, PNG potpis + GIF.
- **Pokazano je da do dekodiranja ne dolazi:** testovi prolaze i kada `Image.open`, `ImageFile.load` i OCR namerno bacaju grešku.
- **Prihvaćeno (PROVEN):**
  - JPEG `.jpg/.jpeg`, PNG;
  - CMYK i sivi JPEG, progresivni, ICC profil;
  - paletni/RGBA/16-bitni PNG;
  - MPO (dekodira se samo prvi kadar, pa i JPEG zaštita gleda njega);
  - zamenjene podržane ekstenzije (sadržaj bira dekoder i zaštitu memorije; namerno).
- **Zaštita memorije za JPEG i dalje radi.** MPO i JPEG imenovan `.png` iznad praga se odbijaju pre dekodiranja (PROVEN).
- **Oštećeni i skraćeni fajlovi** sa ispravnim potpisom i dalje uredno padaju kao „nečitljivo“, bez lažnog OCR uspeha (PROVEN).
- **Ostale rute (PROVEN, grep):** postoje samo dve upload rute i radnik, i sve idu kroz `extract()`. `routers/dokument.py` prima samo PDF/DOCX (to je fiksirano testom), a drafting samo DOCX/TXT.
- **Testovi i mutacije:** `test_ns3b_format_slike.py` 66/66; mutacije autora 11/11 ([log](ns3-evidence/B_mutations.txt)).
- **Napomene iz pregleda** ([pregled](ns3-evidence/B_independent_review.md)):

  | Napomena | Ozbiljnost | Status |
  |---|---|---|
  | Legacy `static/vindex.js:20534` za 415 prikazuje „Podržani formati: PDF, DOCX“; V2 Dosije prikazuje opštu poruku. Ništa ne puca; nema UI izmene (zabrana redizajna). | P3 | PROVEN |
  | `frontend-v2-ng/src/prijem-predmeta.js:185` za neuspeo posao kaže „posle više pokušaja“, iako je posao završen posle jednog. Postojalo je i ranije. | P3 | PROVEN |
  | PNG je ograničen samo na 40 MP; RGBA PNG od 40 MP dodaje +283 MiB (Windows, u procesu). Ranije izmereno kao bezbedno u produkcionom okruženju. | — | ASSUMED, nije ponovo mereno |
  | JPEG-LS (`FF D8 FF F7`) prolazi potpis, ali Pillow ga odbija pri čitanju zaglavlja (nečitljivo, bez dekodiranja). | — | PROVEN |

## D. Audit izvoza — zadatak C
**Status: CLOSED, nezavisni pregled GO WITH NOTES.**
- **Kako se dokazuje upis.** `_build_and_insert` vraća `id` reda koji vrati INSERT (UUID primarni ključ, postgrest 2.28.3 vraća upisani red). Nijedan put ne vraća istinitu vrednost bez upisa (PROVEN). Da je red i commitovan, izvedeno je iz toga što je to jedna naredba (INFERRED).
- **Novi tok `/api/export/complete`** (`routers/data_export.py`):
  1. svi podaci pročitani;
  2. arhiva potpuno sastavljena u memoriji;
  3. `log_action` sa vremenskim ograničenjem od 15 s (`asyncio.wait_for`);
  4. **kao uspeh se računa samo neprazan string id**;
  5. tek tada se vraća ZIP.
- **Kada se ZIP NE vraća.**
  - Rezultat je `None`, prazna vrednost, izuzetak, `ConnectionError` iz sink-a ili timeout.
  - Tada se arhiva odbacuje i vraća se **503**: „Izvoz vam nije poslat jer upis u nepromenjivi audit log nije potvrđen. Pokušajte ponovo za koji minut.“
  - Pokušava se i upis `data_export_failed` sa fazom `audit_unproven`, osim posle timeout-a.
  - Sve ovo je PROVEN testovima (mock i stvarna nit koja visi).
- **Postojeće faze neuspeha su sačuvane:** `pre_retrieval`, `retrieval` (503), `serialization` (500). Ni u jednoj se ZIP ne vraća (PROVEN).
- **Semantika.** Uspešan zapis kaže `archive_generated` i `delivery: not_verified_by_server`, a nikad „preuzeto“. Ako se odgovor prekine posle upisa, ostaje jedan istinit zapis (PROVEN).
- **PII.**
  - Nova metapodaci uspeha **više ne sadrže e-poštu**: `user_id` je već u redu, a stranica o bezbednosti obećava samo `user_id`, vreme i format. Grep nije našao nikog ko čita to polje (PROVEN).
  - Istorijski zapisi nisu dirani.
  - Log ruteru sadrži samo akciju i razlog (ime klase, `timeout` ili `not_persisted`).
- **Izolacija (PROVEN).** Bez prijave korisnik dobija 401 i ne čita se ništa. Svih 8 tabela se filtrira po korisniku iz JWT-a, a tuđi id u upitu ili zaglavlju se ignoriše.
- **Testovi i mutacije.**
  - `test_ns3_export_audit_fail_closed.py` ima 21 slučaj.
  - Stari testovi koji su očekivali „audit pao → izvoz isporučen“ prepisani su na fail-closed, uz zadržane provere da e-pošta i tekst izuzetka nisu u logu.
  - Povezani skup: 109 prolazi.
  - Mutacije: autor 6/6, pregled 10/10 ([log](ns3-evidence/C_mutations.txt), [pregled](ns3-evidence/C_independent_review.md)).
- **Produkcija (GET, samo zbirni brojevi, 2026-10-15T06:45Z):** u `audit_immutable` ima 4 reda u poslednja 24 h i 123 u poslednjih 7 dana. `data_export` ukupno 2, `data_export_failed` 0. Sink je aktivan, pa izvoz ne bi trebalo masovno da vraća 503 (INFERRED).
- **Napomene iz pregleda.**
  - Posle timeout-a nit može kasnije ipak da upiše `archive_generated`: istinito, ali zbunjujuće (INFERRED).
  - Najgori slučaj je ~30 s čekanja na audit; to je ispod 120 s koliko dozvoljava gunicorn.
  - Korisnik u oba klijenta vidi opštu (istinitu) poruku umesto teksta 503 (PROVEN).
  - `GET /api/gdpr/export` (uži JSON, bez audita, bez poziva iz UI-ja) je van opsega i ostaje za naknadno rešavanje.
  - `shared/audit_immutable.py:296` loguje tekst izuzetka baze (postojalo je i ranije).

## E. Dokazi o regresijama
**Lokalno** (Windows, `-p no:randomly`, pun paket, `7bc15515`): **19 failed, 10621 passed**. ID-jevi padova su identični `main` baseline-u: 0 novih, 0 nestalih (PROVEN). Ovih 19 su postojeći padovi `main`-a, i to lokalni: tessdata, coi trio, bu001 itd.

**GitHub CI na `7bc15515`** (ID-jevi padova poređeni sa logovima `main`-a) — PROVEN:

| Posao | Kandidat (failed) | `main` (failed) | Novi | Nestali |
|---|---|---|---|---|
| [Test Suite](https://github.com/benny13n-creator/vindex-ai/actions/runs/38708696931) pytest 3.11 | 174 (10073 passed) | 174 | 0 | 0 |
| Test Suite pytest 3.13 | 174 (10073 passed) | 174 | 0 | 0 |
| [Production Runtime Parity](https://github.com/benny13n-creator/vindex-ai/actions/runs/38708696863), pun paket na produkcionom Python-u 3.11 | 195 (9543 passed) | 196 | 0* | 1 (`test_b3_ocr_bez_laznog_uspeha::test_o2_stvarni_ocr_daje_tekst_i_tacan_status` sada prolazi) |
| Parity: produkciona slika + boot-check, byte-compile | success | success | — | — |
| [Security Checks](https://github.com/benny13n-creator/vindex-ai/actions/runs/38708696985) | success | success | — | — |

\* Jedan „nov“ ID je samo odsečen naziv u `##[notice]` liniji. Pun ID `test_wave9_voice_isolation::test_h_env_kill_switch_odbija_bez_obzira_na_tarifu[enterprise]` pada isto i na `main`.

**Crveni CI je postojeći baseline `main`-a, ne zelen CI.**

**Playwright na integraciji** (A+B+C, pre ispravke N1/N2, koja menja samo proveru PDF-a na serveru) — PROVEN:

| Skup | Rezultat |
|---|---|
| live-rok-odluka | 75/75 |
| live-danas | 53/53 |
| live-rad-predmeta | 44/44 |
| live-matter | 56/56 |
| live-prijem-carobnjak | 37/37 |
| live-prijem-oporavak | 18/18 |
| live-prijem | 53/53 |
| live-kancelarija | 20/20 |

**Ciljani skupovi na `7bc15515`:** OCR/extractor/intake/upload/pdf skup 410 passed i 9 skipped; A+B+C ns3/ns2b skup 182 passed.

**Sačuvano (testovi prolaze):**
- A1/A2/A3 rokovi i NS2b zaštita od zastarele potvrde roka;
- B2 kratak sken;
- C1 straničenje izvoza;
- ACL i izolacija (wave7/wave9/n05);
- hash lanac audita;
- podržani formati dokumenata;
- čuvanje originala.

**Resursi:** vidi B (cgroup run 38696441586 i 38703852856).

## F. Nezavisni pregled
| Zadatak | Reprodukovani napadi | Prihvaćene ispravke | Nerešeno značajno |
|---|---|---|---|
| A | N1: ugnježdene transparentne grupe (PDF od 2–5 KB → +316 MiB pri N=4) — **OOM klasa**. N2: lanac objekata → 33 s pod globalnim OCR zaključavanjem. | `cc0a6d6f`: oba zatvorena i ponovo pregledana (N=4 → procena 356 naspram stvarnih 316 MiB, odbijen; dag_22 0,00 s). Potvrđeno i u cgroup rundi 2. | Knockout precenjivanje (LOW); šare/JBIG2 (INFERRED) |
| B | Maskirani formati, lažni potpisi, MPO sa ogromnim 2. kadrom, APNG, sve rute | `02cc9419`: tri preživele mutacije zatvorene testovima | UI tekst za 415 (P3) |
| C | Timeout, `None`/istinite ne-string vrednosti, sink nedostupan, tenant, 401, mock fidelity | — (nema blokera) | 503 ako sink padne u produkciji (posledica ugovora) |
| JPEG (prethodni ciklus) | F1: segment dužine 0/1 zaobilazi proveru | `99416dd8` | — |

Izveštaji pregleda: [A](ns3-evidence/A_independent_review.md), [B](ns3-evidence/B_independent_review.md), [C](ns3-evidence/C_independent_review.md), [JPEG](ns2b-evidence/A_jpeg_independent_review.md).

## G. Preostale odluke (samo ono što je bitno za betu)
1. **Render `WEB_CONCURRENCY`:** potvrditi efektivnu vrednost 1 pre spajanja (vidi H).
2. **Prag PDF rastera 150 MiB ili ~129 MiB:**
   - 150: bez OOM-a; u istovremenom radu na granici rezerva 65–71 MiB.
   - 129: rezerva ≥ 75 MiB, ali se odbijaju i JPX skenovi u boji od 300 dpi i RGB strane ≥ ~20 MP, koji danas rade.
   - Preporuka: **150**, jer nijedan merni slučaj nije pao, a 129 bi odbijao legitimne skenove.
3. **Ostaje za osnivača (nije menjano po pravilima):**
   - pravni tekst izvoza (PROPOSAL na `ns2/export`);
   - A4 — 78 istorijskih zapisa;
   - dugmad od 32 px na telefonu;
   - tekst greške 415 u legacy UI-ju.

## H. Preduslovi za puštanje u produkciju (izvršava osnivač)
- **Trenutno stanje.**
  - Vrednost `WEB_CONCURRENCY` na Renderu se **ne može pročitati** (nema pristupa).
  - Produkcija `/health` (GET, 2026-10-15) vraća `workers: 1`, isti `pid: 25` i `commit: eb1a34a`.
  - Polje `workers` je eho promenljive sa podrazumevanom vrednošću 1, pa je promenljiva **1 ili nije postavljena** (INFERRED).
  - Prema ranijem merenju: isti pid na 59/59 zahteva → jedan proces (INFERRED).
  - Komandu za pokretanje osnivač navodi kao `gunicorn api:app -c gunicorn.conf.py` (`Procfile`). `Dockerfile` CMD je `uvicorn` i ignoriše se ako je Docker Command postavljen (ASSUMED).
- **Potrebno:** `WEB_CONCURRENCY` = tačno `1`, ili nepostavljeno. Kod na PR #34 podrazumeva 1 (`gunicorn.conf.py`). **Nikako** prazan string: `.env.example` ima `WEB_CONCURRENCY=` i takvo pokretanje pada.
- **Posledice.**
  - Izmena promenljive na Renderu → „Save and deploy“: novi deploy bez prekida (stari proces dobija SIGTERM posle 60 s).
  - Spajanje PR #34 → automatski deploy.
  - Nema migracija.
- **Redosled.**
  1. Pročitati (ne menjati) Environment i Docker Command.
  2. Ako je vrednost bilo šta osim `1` ili prazno-nepostavljeno → postaviti `1` → „Save and deploy“ na trenutnom `main`-u → proveriti.
  3. Ukloniti Draft i spojiti PR #34 (merge commit).
  4. Smoke testovi.
- **Provere posle deploy-a.**
  - Log: tačno jedna linija „Booting worker“.
  - ~30 GET `/health` u razmaku od 8 s: svi `status: ok`, isti `pid`, i `commit` jednak SHA-u merge commita.
  - Render Metrics: memorija ravna, ~200–230 MiB.
- **Ciljani smoke testovi.** Raditi samo na sopstvenom nalogu, sa sintetičkim fajlovima, bez klijentskih dokumenata.

  | Test | Očekivano |
  |---|---|
  | Telefonska fotografija | prihvaćena, OCR tekst vidljiv, entiteti traže pregled |
  | TIFF preimenovan u `.jpg` | odbijen jasnom porukom |
  | Kratak skenirani PDF | OCR |
  | Digitalni PDF | tekst bez OCR-a |
  | Rok u V2 Danas: potvrdi pa odbij | posle odbijanja potvrda iz starog taba → „osvežite stranicu“ |
  | Kompletan izvoz sopstvenih podataka | ZIP stiže; u auditu postoji `data_export` bez e-pošte |

- **Rollback.**
  - Render → Deploys → „Rollback“ na deploy `eb1a34a`.
  - Rollback vraća i staro okruženje i gasi autodeploy. Posle toga ponovo proveriti `WEB_CONCURRENCY` i uključiti autodeploy.
  - Baza se ne vraća (nema migracija).
  - Ako je samo promena promenljive dala problem: vratiti prethodno zapisanu vrednost.

## I. Preporuka
**`GO_FOR_FOUNDER_REVIEW`**
- Sva tri zadatka su zatvorena merenjem, testovima i nezavisnim pregledom.
- Nijedan prihvaćen ulaz ne izaziva OOM u izmerenoj konfiguraciji.
- Nema novih regresija ni lokalno ni u CI-ju.
- Spajanje zavisi od H (Render) i odluke G2.

## J. Izvršni rezime
1. PR #34 je fast-forward na `7bc15515` (plus ovaj izveštaj); Draft; ništa spojeno ni pušteno; `main` = `eb1a34a6` = produkcija.
2. **PDF:** CMYK 30–35 MP, umetnute slike, maske, lanci filtera, poliglot i transparentne grupe sada se odbijaju pre dekodiranja. 0 OOM u 2 cgroup runde.
3. Obični skenovi, mešoviti i digitalni PDF-ovi rade sa ≥ 86 MiB rezerve kad dokument radi sam. U istovremenom radu, na granici, rezerva je 65–71 MiB → odluka o pragu 150/129.
4. **Slike:** prolaze samo pravi JPEG i PNG. TIFF/GIF/BMP/WebP/PDF preimenovani u `.jpg`/`.png` odbijaju se pre otvaranja (415 / `ok:false` / terminalni status).
5. **Izvoz:** ZIP se šalje samo posle dokazanog upisa u nepromenjivi audit; inače 503. E-pošta je uklonjena iz novih audit metapodataka.
6. Nezavisni pregled: A je našao 2 rupe (jedna OOM klasa) — zatvorene i ponovo pregledane. B 3 rupe u testovima — zatvorene. C bez blokera.
7. Testovi: lokalno 19 padova = `main`; CI 174/174/195 naspram 174/174/196 (0 novih); Security zeleno; Playwright 8 skupova, sve PASS.
8. Pre spajanja: potvrditi `WEB_CONCURRENCY` = 1 ili nepostavljeno na Renderu. Produkcija danas prijavljuje `workers: 1`.
9. Verdikt: **GO_FOR_FOUNDER_REVIEW**.

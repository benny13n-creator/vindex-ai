# VCR002 — dokazi testova

Svi testovi su sintetički. Imena, brojevi predmeta i činjenice su izmišljeni. Pravi email, SMS i pozivi modela nisu korišćeni.

## Novi testovi

| Fajl | Testova | Zadatak | Šta meri | Mutacije (uhvaćeno) |
|---|---|---|---|---|
| `tests/test_vcr002_t02_ocr_korpus.py` | 11 | T02 | OCR korpus A/C/D, isto ime + drugi sadržaj, > 25 MB, oštećen PDF, pad baze posle ekstrakcije i pri prikačivanju, ponovljeno prikačivanje, tuđ predmet | 2/2 (+1 neodlučna: lažni RPC) |
| `tests/test_vcr002_t03_visedokumentni_predmet.py` | 7 | T03 | 3 dokumenta → tvrdnje → protivrečnost → hronologija → rok → akcija → potvrda → pitanje → istorija → brisanje izvora | 3/3 |
| `tests/test_vcr002_t04_podsetnici.py` | 10 | T04 | dva roka istog dana, dva predmeta, ponovljen cron, predmet u brisanju, stvarna kapija potvrde (4 stanja), pad lanca odluka, autentikacija cron ključa | 3/3 |
| `tests/test_vcr002_t05_paralelni_savetnici.py` | 22 | T05 | vlasništvo, granica poverenja (dokument i opis), citati (provereni, izmišljeni, bez izvora, pad pretrage, dokument ≠ zakon, izuzet član na `/run`), delimičan neuspeh, naplata, budžet, duplikati, 5 pogrešnih ulaza, konkurencija A/B | 8/8 |
| `tests/test_vcr002_t06_niz_savetnika.py` | 19 | T06 | tri koraka, izlaz u granici, završni ne nasleđuje proveru, prenesena halucinacija, tuđ predmet, pad 1. i 2. koraka, neočekivan izuzetak, budžet, 5 pogrešnih ulaza, 5 slučajeva trajne idempotencije | 6/6 |
| `frontend-v2-ng/tests/live-agenti.mjs` | 43 provere (+20) | T07 | UI sva tri načina (fixture) | — |
| `frontend-v2-ng/tests/live-savetnici-e2e.mjs` | 18 provera | T07 | UI ↔ pravi `api.app` (pozivi, naplata, granica, idempotencija, reload) | — |

## Izvršenja

| Šta | Rezultat | Nivo |
|---|---|---|
| T02 OCR u **produkcionoj Docker slici** (CI run 38218538250, `VINDEX_REQUIRE_OCR=1 VINDEX_EXPECT_SRP=1`) | **32 passed** (NS005 B + T14 + T02 korpus), srp+srp_latn+eng, mešovit PDF: digitalna strana 1.0, ćirilični sken 1.0 udeo reči | ISOLATED (produkciona slika) |
| T02 lokalno (bez Tesseract-a) | 10 passed, 11 skipped (OCR deo) | LOCAL |
| T03 regresija (brisanje, dokazi, evidence, OSB002/003, VCR001, NS006, FRG001, Wave 2) | 484 passed, 1 skipped | LOCAL |
| T04 regresija podsetnika (B10, Wave 4, LZ001, Living System, nedeljni pregled, FAZA 6.x) | 368 passed | LOCAL |
| T05 i T06 regresija savetnika i idempotencije (NS005 A2, VCR001 T06, `test_multi_agent`, CELINA 3) | 124 passed, 9 skipped | LOCAL |
| T09 NS007 nad **stvarnim PostgreSQL-om 17.9** (izolovan klaster, 127.0.0.1:55432) | **163 passed, 0 skipped** | ISOLATED |
| T07 `verify:live-agenti` | 43/43 | BROWSER_INTEGRATION (fixture) |
| T07 `e2e:savetnici` | 18/18 | BROWSER_INTEGRATION (pravi `api.app`) |
| Svi frontend paketi (`verify*` + `e2e:*`, 45) | vidi `VCR002_RELEASE_HANDOFF.md` §7 | BROWSER_INTEGRATION |
| CI na kandidatu (Test Suite, Runtime + Docker, Security, V2 NG) | vidi `VCR002_RELEASE_HANDOFF.md` §6 | CI |

## Mutacioni harness

Harness je binaran (`rb`/`wb`, poštuje CRLF) i posle svakog pokretanja proverava da je fajl vraćen bajt-identično. Specifikacije su u scratchpad-u sesije (`mut_t02…t06*.json`).

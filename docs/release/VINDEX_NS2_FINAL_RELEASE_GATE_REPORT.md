# VINDEX — NS2 FINAL CORRECTIVE CYCLE — PR #34 RELEASE GATE (2026-10-15)

**Verdict: PARTIAL_WITH_EXPLICIT_HOLDS**
Ništa nije spojeno u `main`, ništa nije deployovano, Render produkcija nije menjana, nijedna migracija nije pokrenuta, nijedan produkcioni zapis nije menjan. Ništa nije LIVE VERIFIED.

Oznake: **PROVEN** (izmereno/testirano ovde), **INFERRED** (izvedeno iz dokaza), **ASSUMED** (pretpostavka), **UNKNOWN**.

---

## A. Stanje repozitorijuma
| Stavka | Vrednost | Status |
|---|---|---|
| `origin/main` | `eb1a34a69f4eb3fbcc393dc991b3fb6760919800` — nepromenjen tokom ciklusa | PROVEN |
| PR #34 pre ciklusa | `dd619e9ae871f5a2192c37d7c4ecf31617c6fa5c` | PROVEN |
| PR #34 posle ciklusa | **`da345f26`** — fast-forward push (bez force-push, bez prepisivanja istorije); `dd619e9a` je predak | PROVEN |
| Draft / spojeno | Draft, nije spojen | PROVEN |

Komponente dodate preko `dd619e9a` (svaka ispravka sledljiva do svog commita i grane):
| Zadatak | Grana | Commitovi | Spoj u kandidatu |
|---|---|---|---|
| C stale potvrda | `ns2b/rok-stale` | `97fe99dc`, `bf6e62fe` | `d47d18da` |
| D audit izvoza | `ns2b/export-audit` | `3a333b34`, `06615f48` | `3452e6e7` |
| B runtime | `ns2b/runtime` | `6e08073b` | `8bdd265c` |
| A JPEG | `ns2b/ocr-jpeg` | `79d826e1`, `0db59e19`, `befe2300`, `99416dd8` | `4768db94`, `da345f26` |

24 fajla, +1799/−96 u odnosu na `dd619e9a`. Bez konflikata. `static/sw.js` CACHE_NAME ostaje `vindex-v152` (nijedna ispravka ne menja legacy statiku).
Radne kopije sačuvane: `C:/vindex-ns2b/{integ, rok-stale, export-audit, runtime, ocr-jpeg, ocr-jpeg-measure, review-a}`. Merna grana `measure/ns2b-ocr-jpeg` (`aa181107`) i `measure/ns2b-runtime` (`efffee37`) pushovane; ostale `ns2b/*` grane su lokalne.

## B. JPEG (odluka A: odbiti samo dokazano nebezbedne JPEG ulaze pre dekodiranja)
**Status: FOTOGRAFIJE CLOSED (GO WITH NOTES); PDF HOLD.**

Mehanizam (`uploaded_doc/extractor.py`):
- Iz zaglavlja (bez dekodiranja) računa se vrh memorije dekodiranja: dekodirana slika u razmeri koju dekoder bira (1/1–1/8, nikad ispod A4@300 dpi) × bajtova po pikselu (L=1, RGB/CMYK=4) + najveće od: bafer koeficijenata (progresivni ili višeprolazni), konverzija u sivo (CMYK preko RGB kopije), promena veličine. — PROVEN (procena = izmereni vrh ±2 MiB na 68 sintetičkih JPEG-ova, run 38644578306, 38656160021).
- Jedno pravilo: procena > **150 MiB** → odbijeno (`MAX_JPEG_DEKODIRANJA_BAJTOVA`). Ruta za upload vraća **413** sa jasnom srpskom porukom (bez tehničkih brojeva); intake radnik posao odmah šalje u dead-letter (1 pokušaj umesto 5) i ne označava ništa kao obrađeno. — PROVEN (testovi, pregled).
- PDF: samo pravilo bafera koeficijenata (> 64 MiB), izmereno bezbedno u run 38649305321. — PROVEN.

Merenja (produkciona Docker slika, gunicorn, `WEB_CONCURRENCY=1`, cgroup 512 MiB, 3 ponavljanja), run 38656160021 / 38660479790:
| Ulaz | Pre (`dd619e9a`) | Posle (`da345f26`) |
|---|---|---|
| Običan CMYK 30–34,6 MP fotografija | **OOM ubistvo** (34,6 MP 3/3; sa skenom 3/3) | odbijeno, vrh 256–266 MiB — PROVEN |
| Progresivni 4:4:4 40 MP | ~494 MiB (16 MiB rezerve) | odbijeno — PROVEN |
| Pozitivne kontrole: CMYK 40 MP, telefon 12 MP, RGB 40 MP, PNG 40 MP, progresivni 4:2:0 40 MP, tik ispod praga | prihvaćeno | prihvaćeno, 366–409 MiB, 0 OOM — PROVEN |
| Najgori prihvaćen slučaj + istovremeni sken 10 str. | — | 436–437 MiB (≥ 75 MiB rezerve) — PROVEN |
| Običan RGB/sivi JPEG bilo koje veličine do 40 MP | — | nikad ne prelazi prag (mreža veličina × 4 razmere) — PROVEN (test) |

Nezavisni pregled A (`ns2b/ocr-jpeg/review_a.md`): **GO WITH NOTES** posle ispravke F1.
- **F1 HIGH (PROVEN) — ZATVORENO u `99416dd8`:** segment dužine 0/1 (npr. `FF FE 00 00` iza SOI) zaobilazio je proveru, a Pillow takav fajl dekodira → 40 MP prog444 bi prošao i oborio radnika. Sada se tretira kao prazan segment (isto kao libjpeg); regresioni test 3 varijante, mutacija (stari kod) ubijena 3/3.
- **F2 MEDIUM (PROVEN), samo namerno konstruisani PDF:** lanac filtera `[/ASCIIHexDecode /DCTDecode]`, inline slike (`BI…ID…EI`) i (INFERRED) slike u anotacijama nisu provereni. → HOLD.
- **F3 MEDIUM (PROVEN), postojalo i ranije (nije regresija):** `extract_image` otvara svaki format koji Pillow zna; CMYK TIFF preimenovan u `.jpg` prihvaćen (+347 MiB). Ograničavanje formata je van odobrene odluke → odluka osnivača.
- **F4 LOW:** odbijaju se i neki „obični“ ulazi koji su izmereno nebezbedni: običan CMYK 17,5–34,7 MP, progresivni 4:4:4 > ~22,4 MP (npr. kamera 24 MP progresivna 4:4:4). Sve fotografije sa telefona (12/24/40 MP, 4:2:0) prolaze. — PROVEN (procena) / INFERRED (da je to retko u praksi).
- **F5 LOW:** mutacija `<=`→`<` na `MAX_OCR_PIXELS` preživljava (razlika samo tačno na 15.000.000 px).
- **F6 UNKNOWN:** lossless (SOF3) i 12-bitni JPEG sa libjpeg-turbo 3 — nije bilo enkodera za proveru.
- Potvrđeno: `extractor.py` je jedino mesto sa PIL/PyMuPDF; pokrivene obe upload rute, intake radnik (i Smart Intake). Parser je fail-closed na izuzetak.

Testovi: `tests/test_ns2b_ocr_jpeg_koeficijenti.py` 49/49; mutacije autora 27/27 + pregled 7/8 + F1 1/1. OCR/extractor/intake skup na `da345f26`: 279 passed, 9 skipped.

**PDF HOLD (PROVEN):** običan CMYK JPEG ~30–35 MP postavljen na celu A4 stranu u PDF-u i dalje ubija radnika (3/3, sam i sa skenom). Postojao je i u `dd619e9a` i (INFERRED) u `main`. Pokušaj ispravke (`page.get_image_rects`) sam je dekodirao slike i izazvao OOM → vraćen u `befe2300`; čist revert potvrđen pregledom. Za popravku je potrebna treća runda merenja (parsiranje content stream-a bez dekodiranja, ili pretpostavka „slika ispunjava stranu“) — **treba odobrenje osnivača.**
Ostali poznati jazovi: V2 prikazuje opšti tekst greške umesto poruke 413 (INFERRED iz koda, UI nije menjan po zabrani redizajna); mešovit PDF sa jednom odbijenom slikom odbija se ceo.

## C. Runtime (odluka B: `WEB_CONCURRENCY=1` za 512 MiB Render)
**Status: CLOSED u kodu (GO WITH NOTES); akcija na Renderu čeka osnivača.**
- `gunicorn.conf.py`: podrazumevano **1** radnik kad promenljiva nije postavljena (ranije 4). Test `tests/test_ns2b_gunicorn_workers_default.py`. — PROVEN.
- Merenje run 38643777266: stara konfiguracija bez promenljive = 4 radnika, OOM petlja, `/health` nikad ne odgovori; nova = 1 radnik, 213 MiB; `WEB_CONCURRENCY=2` i dalje poštovan (~388 MiB); Dockerfile uvicorn komanda 195 MiB. — PROVEN.
- Produkcija: isti pid na 59/59 GET zahteva → jedan proces — INFERRED. Da li produkcija pokreće gunicorn ili Dockerfile uvicorn komandu — UNKNOWN. Polje `workers` u `/health` je eho promenljive, ne broj procesa — PROVEN.
- Render dokumentacija: servisi napravljeni posle 2025-12-08 na 512 MB podrazumevaju 1; Docker Command u dashboard-u ima prednost nad CMD iz Dockerfile-a — ASSUMED (dokumentacija, ne provereno na nalogu).

## D. Stanje roka (odluka C: zastarela potvrda posle odbijanja ne potvrđuje rok)
**Status: CLOSED (GO WITH NOTES posle ponovnog pregleda).**
`shared/rok_potvrda.odluke()` je monotono izvođenje iz CELOG lanca odluka (`procitaj_lanac()`: straničenje po celobrojnom `seq`, strane ≤ 1000, strogo rastuće, id-jevi u grupama po 100, ograničen broj strana — popravlja odsecanje PostgREST max-rows koje je moglo sakriti odbijanje).

| Prethodno stanje | Akcija | Rezultat | Upis |
|---|---|---|---|
| NEPOTVRĐEN (nema odluka) | potvrdi | POTVRĐEN | da |
| NEPOTVRĐEN | odbij | ODBIJEN | da |
| POTVRĐEN | potvrdi (ponovo) | POTVRĐEN | ne (osim ponovne potvrde posle uklanjanja izvornog dokumenta, N03-FD6) |
| POTVRĐEN | odbij | ODBIJEN | da |
| ODBIJEN | potvrdi (npr. iz starog prozora) | **409** „Rok je već odbijen. Potvrda posle odbijanja nije moguća iz ovog prozora — osvežite stranicu.“ | **ne** |
| ODBIJEN | odbij (ponovo) | ODBIJEN | ne |
| bilo koje + nepoznata akcija u lancu | — | ODBIJEN zauvek | — |
| lanac nečitljiv | potvrdi | **503**, stanje NEPOZNATO (ne potvrđen) | ne |

- `shared/rok_izvor.py` usklađen; V2 `danas.js` na 409 ponovo učitava. — PROVEN (testovi, e2e 75/75).
- Produkcija (GET, samo agregat): 15 redova odluka na 13 rokova; **0 menja stanje** novim pravilom. — PROVEN (agregat).
- Mutacije 7/7 i 8/8 ubijene. — PROVEN.
- Napomene: upit `SourceInvalidated` događaja nije straničen (može samo izostaviti upozorenje); ponovljena potvrda bez upisa ne emituje `_javi_odluku`; ~2× upita po korisniku u cron-u. Ponovno otvaranje odbijenog roka = buduća, posebno auditovana operacija.

## E. Audit izvoza (odluka D)
**Status: CLOSED (GO WITH NOTES); ugovorni tekst je eskalacija osnivaču.**
- `routers/data_export.py`: upis audita se **čeka pre slanja odgovora** (ranije pozadinski task koji umire sa procesom). Uspeh i sve tri faze neuspeha (`pre_retrieval`, `retrieval`, `serialization`) upisani pre nego što klijent dobije bajt. — PROVEN (`tests/test_ns2b_export_audit_ordering.py`, simulacija gašenja procesa).
- E-pošta iz metapodataka nikad ne ide u log upozorenja; tekst izuzetka ne curi. — PROVEN (mutacija R3 ubijena).
- **Granica (PROVEN):** `log_action` je po ugovoru best-effort (`shared/audit_immutable.py:274`). Ako audit sink ne radi, izvoz se **ipak isporučuje**, pad je vidljiv samo u logu. `static/security.html:283` tvrdi „Svaki kompletan izvoz upisuje se u nepromenjivi audit log“. → Odluka osnivača: (a) 503 kad audit ne uspe, (b) trajni outbox, ili (c) izmena pravnog teksta.
- Stariji, neizmenjeni nalazi: `gdpr_erasure` audit i dalje pozadinski (`routers/gdpr.py:267`) naspram `security.html:271`; `/api/gdpr/export` nema audit; e-pošta se čuva u append-only auditu; sinhroni `_fetch` blokira event loop; nema eksplicitnog timeout-a audita (najgore ~240–360 s, INFERRED).

## F. CI diferencijal
Lokalno (Windows, `-p no:randomly`, pun paket): integracija A+B+C+D **19 failed, 10492 passed** = identični ID-jevi kao `main` baseline (0 novih, 0 nestalih). — PROVEN. (Ispravka F1 je spojena posle tog prolaza; na finalnom `da345f26` ponovo pokrenut OCR/extractor/intake skup: 279 passed.)
Playwright na integraciji: live-rok-odluka 75/75, live-danas 53/53, live-rad-predmeta 44/44, live-matter 56/56. — PROVEN.

GitHub CI na `da345f26` (poređenje ID-jeva padova sa `main` logovima, regex `(FAILED|ERROR) tests/…::…`): — PROVEN
| Posao | Kandidat | `main` | Novi | Nestali |
|---|---|---|---|---|
| Test Suite pytest 3.11 (run 38667113343) | 174 failed / 9949 passed | 174 | 0 | 0 |
| Test Suite pytest 3.13 | 174 failed / 9948 passed | 174 | 0 | 0 |
| Production Runtime Parity — full suite na prod Python 3.11 (run 38667113440) | 195 failed / 9418 passed | 196 | 0* | 1 (`test_b3_ocr_bez_laznog_uspeha::test_o2_stvarni_ocr_daje_tekst_i_tacan_status` sada prolazi) |
| Parity — build produkcione slike + boot-check; byte-compile | success | success | — | — |
| Security Checks (run 38667113356) | success | success | — | — |

\* Jedan „nov“ ID (`test_M3_dve_intra_d`) je odsečen naziv u `##[notice]` liniji; pun ID `test_M3_dve_intra_dokumentne_kontradikcije_prezive` pada identično i na `main`. Crveni CI statusi su postojeći baseline `main`-a (CI baseline restoration nije deo ovog ciklusa).

## G. Nezavisni pregled
| Zadatak | Pregled | Verdikt |
|---|---|---|
| A JPEG | adversarialni pregled `befe2300` (F1 ispravljen u `99416dd8`) | GO WITH NOTES |
| B runtime | pregled + merenje | GO WITH NOTES |
| C stale potvrda | pregled → F1 (odsecanje lanca) ispravljen u `bf6e62fe` → ponovni pregled | GO WITH NOTES |
| D audit izvoza | pregled → F1 (e-pošta u logu) ispravljen u `06615f48` | GO WITH NOTES |

## H. Preostali HOLD-ovi (svaki je odluka osnivača)
1. **Render `WEB_CONCURRENCY=1`** — postaviti pre spajanja (procedura u J).
2. **OCR PDF:** običan CMYK JPEG ~30–35 MP u PDF-u i dalje OOM; plus konstruisani PDF jazovi (F2). Odobriti 3. rundu merenja ili prihvatiti rizik (postoji i danas).
3. **OCR formati (F3):** ograničiti `extract_image` na JPEG/PNG ili prihvatiti (postojeći rizik).
4. **Audit izvoza:** politika pri padu audita naspram `security.html:283` (i `:271` za brisanje).
5. **Pravni tekst izvoza** (`dpa.html`/`security.html`, PROPOSAL na grani `ns2/export`) — pravnik.
6. **A4:** 78 istorijskih zapisa bez `vrsta` — nisu dirani.
7. Dugmad Potvrdi/Odbij na telefonu 32 px (cilj 40 px) — nije rađeno (zabrana redizajna).

## I. Release candidate
- **Kandidat: PR #34, `release/ns2-beta-rc-2026-10-14` @ `da345f26`** (Draft). Zamenjuje #31, #33, #26.
- SAFE SUBSET nije potreban: svaka ispravka je strogo bezbednija od `dd619e9a`; PDF HOLD je postojeći rizik, nije uveden ovim ciklusom (INFERRED: isti put postoji i u `main`).
- Uslov spajanja: korak 1 iz J (Render `WEB_CONCURRENCY=1`) mora biti završen i proveren pre spajanja.

## J. Priprema puštanja (izvršava osnivač; ovde ništa nije izvršeno)
**Konfiguracija**
- Render → servis → Environment: `WEB_CONCURRENCY` = tačno `1` (ne prazno — prazna vrednost obara pokretanje; `.env.example` ima `WEB_CONCURRENCY=` prazno, ne kopirati).
- Samo pročitati (ne menjati) polje **Docker Command** u Settings: zapisati da li je prazno, gunicorn ili uvicorn.

**Redosled**
1. Postaviti `WEB_CONCURRENCY=1` → „Save and deploy“ na **trenutnom `main`** (`eb1a34a6`), pre spajanja.
2. Proveriti (vidi smoke testove). Ako nešto nije u redu → vratiti promenljivu, NE spajati.
3. Ukloniti Draft, spojiti PR #34 (merge commit) → auto-deploy.
4. Smoke testovi na novom deploy-u.

**Smoke testovi**
- Log: tačno jedna linija „Booting worker“.
- ~30 GET `/health` u razmaku 8 s: isti `pid` svaki put; memorija u Render Metrics ravna ~200–230 MiB.
- V2 Danas: potvrdi pa odbij test-rok na sopstvenom nalogu; posle odbijanja potvrda iz starog taba daje poruku „osvežite stranicu“.
- Upload obične fotografije telefonom (prihvaćena) — bez slanja klijentskih dokumenata.
- Kompletan izvoz sopstvenih podataka: ZIP preuzet; u auditu postoji red `data_export`.

**Rollback**
- Kod: Render → Deploys → „Rollback“ na prethodni deploy (`eb1a34a6`). Napomena: rollback vraća i staro okruženje i gasi autodeploy — posle rollback-a ponovo proveriti `WEB_CONCURRENCY=1` i uključiti autodeploy.
- Konfiguracija: ako je u koraku 1 nešto pošlo naopako, vratiti prethodnu vrednost promenljive (zapisanu pre promene).
- Nema migracija u ovom kandidatu → nema rollback-a baze.

## K. Izvršni rezime
1. PR #34 dopunjen na `da345f26` (fast-forward), Draft, ništa spojeno ni pušteno.
2. **C:** odbijen rok više ne može da se potvrdi iz starog prozora (409, bez upisa); ceo lanac odluka se čita bez odsecanja. GO.
3. **D:** audit izvoza se upisuje pre isporuke. GO; pad audit sistema i dalje ne blokira izvoz → odluka o tekstu `security.html`.
4. **B:** kod podrazumeva 1 radnika; 4 radnika na 512 MiB izmereno padaju. GO; Render promenljivu postavlja osnivač pre spajanja.
5. **A:** fotografije koje bi oborile server (npr. CMYK 30–35 MP, progresivni 40 MP 4:4:4) sada se odbijaju jasnom porukom; telefonske i obične fotografije prolaze; 0 OOM u merenju. Pregled našao rupu od 4 bajta — zatvorena.
6. **HOLD:** isti CMYK JPEG ugrađen u PDF i dalje može da obori server (postojeći rizik); traži odobrenje 3. runde merenja.
7. Testovi: lokalno 19 padova = `main`; Playwright 75/53/44/56 PASS; GitHub CI 174/174/195 naspram `main` 174/174/196 — 0 novih padova; Security zeleno.
8. **Verdikt: PARTIAL_WITH_EXPLICIT_HOLDS** — kandidat je spreman za pregled osnivača uz 7 navedenih odluka.

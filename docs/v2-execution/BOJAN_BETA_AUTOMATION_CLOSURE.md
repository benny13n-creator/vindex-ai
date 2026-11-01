# BOJAN BETA AUTOMATION & B5/B7 CLOSURE — ledger

Ugovor: osnivačev „VINDEX AI — BOJAN BETA AUTOMATION & B5/B7 CLOSURE — MASTER NIGHT SPRINT“ (2026-10-31), S00–S11, strogo redom.
Pravila: `docs/governance/VINDEX-CANONICAL-OPERATING-RULES.md` (ACTIVE, SHA-256 `b1df798d5ff58e8e16daa93f36de246660d4c10cccee98c19e1a951065303056`).
Oznake: PROVEN / INFERRED / ASSUMED / UNKNOWN. Nivoi: LOCAL · ISOLATED · BROWSER_INTEGRATION · LIVE · REAL_USER_ACCEPTED.
LIVE ovde znači: posmatrano u produkciji nad sintetičkim predmetom koji je osnivač uneo; to nije Bojanovo prihvatanje.

Grana `bojan/beta-automation-closure` (worktree `C:/vindex-beta-auto`) iz `origin/main`; lokalni commitovi, bez push-a.

---

## S00 — preflight, requirements lock, baseline

### Kanonski dokument
| Provera | Rezultat | Oznaka |
|---|---|---|
| Izvor | `C:\Users\Benny\Downloads\VINDEX-S00-CANONICAL-READY\docs\governance\VINDEX-CANONICAL-OPERATING-RULES.md` (na `C:\vindex-ba01\docs\governance\` ga nije bilo) | PROVEN |
| SHA-256 izvora | `b1df798d…303056` = očekivani heš | PROVEN |
| Status | `Status: ACTIVE`, 164 reda, 5.541 B, LF | PROVEN |
| Kopija u grani | bajt-identična (isti SHA-256) | PROVEN |

### Osnovica
| Stavka | Vrednost | Oznaka |
|---|---|---|
| `origin/main` | `a45b34ba5246f5432e07dad03d295ddb96019347` (Merge PR #62; #63 spojen kao `c1709799`) | PROVEN |
| Produkcija `/health` | `commit: a45b34b`, `workers: 1`, `redis: true` | PROVEN |
| Render deploy evidencija | nema pristupa Render-u; GitHub nema deployment zapise za SHA → jedini dokaz je `/health` | PROVEN (odsustvo) |
| Sprint grana | `bojan/beta-automation-closure` = `a45b34ba`, merge-base = `origin/main` | PROVEN |
| CI na `a45b34ba` | **11/11 success** (push run 2026-10-31 13:20Z; Security, Test Suite, Production Runtime Parity) | PROVEN |
| Otvoreni PR-ovi | 14 Draft PR-ova (#2–#50), nijedan Bojanov tok BA/N nije otvoren; #61/#62/#63 spojeni | PROVEN |
| Lokalna regresiona osnovica | vidi „Puna svita osnovice“ ispod | — |

### Migracije 142–145 (produkcija, samo GET, `limit=0`)
| Migracija | Provera | Rezultat | Oznaka |
|---|---|---|---|
| 142 | `email_podsetnik_dogadjaj` (sve 13 kolona), `email_podsetnik_pokretanje` | HTTP 200, oba **0 redova** | PROVEN |
| 143 | javni (publishable) ključ čita tabele podsetnika | 401 / `42501 permission denied` za obe | PROVEN |
| 144 | `predmet_hronologija.obaveza_kljuc` | postoji; novi rokovi nose ključ | PROVEN |
| 144 UNIQUE indeks | nema DB URL-a; PostgREST ne izlaže indekse | — | UNKNOWN (INFERRED primenjen po spajanju #61) |
| 145 | `predmet_hronologija.dogadjaj_event_id` | postoji; 4/4 rokova predmeta `11eaeffc` ga nose | PROVEN |
| 145 UNIQUE indeks | isto kao 144 | — | UNKNOWN |

### Današnji mobilni Golden Case (produkcija, samo GET, bez sadržaja dokumenata)
Predmet `11eaeffc` („Jelena Markovic protiv Delta Test d.o.o.“, 2026-10-31 14:36Z):
- 4 dokumenta (`01_Digitalni_PDF.pdf`, `02_Skenirani_PDF.pdf`, `scan.pdf` ×2); OCR stvarno izvršen na 3 (`ocr_used=true`, 0,949–0,951) — PROVEN LIVE.
- `predmet_dokazi` 24: `egzaktan` 22, `normalizovan` 1, `nije_pronadjen` 1; svi `ai_klasifikacija`, svi sa `dokument_id` — potvrđuje ugovor S01. PROVEN.
- `predmeti.opis` prazan, `predmet_klijenti` 0 — potvrđuje ugovor S03. PROVEN.
- `predmet_issues` 3, sva `DISCOVERED`: „Sintetički test“, „Razlika u datumu dokumenta“, „Razlika u rokovima za uplatu takse“ (B7 slučaj). Ugovor S02 imenuje samo treći; prva dva se pregledaju u S02. PROVEN.
- Hronologija: 4 roka, svi `AI_AUTONOMOUS` (nepotvrđeni), svi sa `obaveza_kljuc` i `dogadjaj_event_id`; dva različita `scan.pdf` sa istim datumom 2026-11-27 ostaju dva reda. PROVEN.
- `case_actions`: 4 `PLANIRATI_ROKOVE` otvorene, 2 `PRIBAVITI_DOKAZ`, 3 `RAZRESITI_KONTRADIKCIJU` (1 otvorena). Ročišta 0, stavke naplate 0, email rezervacije 0.

Raniji predmet P7714 (`71c5e673`, 2026-10-30): klijent 1, opis postoji, 4 roka (dva 2026-11-12 iz dva `scan.pdf`), 14 dokaza `egzaktan`, 1 issue „Razlika u datumu odluke“.

**Nije obuhvaćeno mobilnim testom (PROVEN odsustvom podataka):** veza klijent–predmet i opis/cilj (čarobnjak), provera sukoba, ročišta i kalendar (N3), potvrda/odbijanje/ispravka roka, podsetnici i isporuka (B10, `email-cron.yml` je `disabled_manually` od 2026-10-28; obe tabele 142 prazne), naplata (N5), izveštaji (N6), N8/N9 pravno rezonovanje, tenant B, retry/konkurentnost/prekid veze, DOCX i JPG/PNG format.

### Mapiranje identifikatora (bez novih zahteva)
| Bojanov tekst | N | A018 B | BA |
|---|---|---|---|
| wizard, podaci klijenta, cilj/spor, zavođenje predmeta | N1, N2 | B1, B2, B4 | BA-01 |
| skenirana dokumentacija | N1 | B3 | BA-02 |
| (izvlačenje podataka iz dokumenata) | N1 | B5, B6 | BA-03 |
| zakazivanje u kalendaru, ročišta | N3 | — | — |
| rokovi, podsetnici | N4 | B9, B10 | BA-05, BA-06, BA-07 |
| evidencija o naplati | N5 | — | — |
| izveštaji | N6 | — | — |
| ažuriranje predmeta | N7 | B8, B11, B12, B6 | BA-04, BA-08 |
| nadležnost | N8 | — | — |
| višestruki povrat čl. 55a | N9 | — | — |
| (inženjerske) protivrečnosti, ceo lanac | — | B7, B13 | — |

N0 = zaključavanje izvora zahteva (ne funkcionalnost).

### Acceptance matrica na ulazu u sprint
Kolona „Najviši nivo“ = najviši STVARNO posmatran nivo do S00 (istorijski dokaz označen izvorom).

| ID | Izvor | Kod (vlasnik) | Najviši nivo pre sprinta | Nije dokazano | Potvrđen otvoren defekt | Etapa |
|---|---|---|---|---|---|---|
| B1 | A018 | `routers/predmeti.py`, `routers/intake.py` | LIVE (P7714, `11eaeffc`) | — | ne | S03 |
| B2 | A018 | `routers/smart_intake.py` | LIVE (4/4 posla `completed` na oba predmeta) | DOCX/JPG u produkciji | ne | S03 |
| B3 | A018 | `uploaded_doc/extractor.py`, `shared/intake_worker.py` | LIVE (OCR na 3+3 dokumenta) | foto JPG/PNG uživo | ne | S03 |
| B4 | A018 | `predmet_dokumenti.id` | LIVE | — | ne | S03 |
| B5 | A018 | `shared/evidence_write.py`, `routers/evidence.py` | LIVE (24 dokaza sa `dokument_id`) | semantička tačnost, adversarial A–K | **UNKNOWN** — S01 | S01 |
| B6 | A018 | `case_dna` + katalog tvrdnji | LIVE (4 dokumenta, tvrdnje po dokumentu) | — | ne | S08 |
| B7 | A018 | `routers/case_dna.py`, `shared/issue_v2.py` | LIVE | identitet obaveze pre kategoričnog nalaza | **DA (prijavljeno, reprodukcija u S02)** | S02 |
| B8 | A018 | `predmet_hronologija` + `genome_contract` | LIVE (rokovi sa izvorom) | — | ne | S05/S08 |
| B9 | A018 | `shared/rokovi.py`, lanac odluka | LIVE (4 nepotvrđena kandidata) | potvrda/odbijanje uživo | ne | S05 |
| B10 | A018 | `routers/email_notif.py`, `email-cron.yml` | ISOLATED (lokalni SMTP, PG17) | bilo kakvo produkciono slanje; cron isključen | operativno (BLOCKED_AUTHORITY u ranijim sprintovima) | S11 |
| B11 | A018 | `services/case_evolution.py` | LIVE (`PLANIRATI_ROKOVE` iz rokova) | — | ne | S08 |
| B12 | A018 | `routers/case_dna.py` | LIVE (3 verzije istorije po predmetu) | — | ne | S08 |
| B13 | A018 | ceo lanac | LIVE delimično (bez klijenta, ročišta, naplate, podsetnika) | ceo lanac | ne | S10 |
| N1 | N0/N1 ledger | prijem (V2 + Smart Intake) | BROWSER_INTEGRATION (zlatni E2E 48/48) + LIVE delimično | — | ne | S03 |
| N2 | N2–N9 ledger | čarobnjak, COI (UI kapija) | BROWSER_INTEGRATION (27/27) | uživo klijent+opis | ne (serverski COI = odluka osnivača, otvorena) | S03 |
| N3 | N2–N9 ledger | ročišta, Danas | BROWSER_INTEGRATION (24/24) | uživo | ne | S04 |
| N4 | N2–N9 + Sektor 2 | rokovi, podsetnici | ISOLATED / BROWSER_INTEGRATION | isporuka | operativno | S05/S11 |
| N5 | N2–N9 ledger | naplata | BROWSER_INTEGRATION (16/16) | uživo | ne | S06 |
| N6 | N2–N9 ledger | izveštaji | BROWSER_INTEGRATION (8/8) | uživo | ne | S07 |
| N7 | N2–N9 ledger | ažuriranje predmeta | ISOLATED + LIVE (novi dokumenti → dokazi, Genome, akcije) | — | ne | S08 |
| N8 | N2–N9 ledger | `ask_agent` + provere | ISOLATED (stvaran model, baza zatvorena) | — | ne (ograničenja F8, ZUS van korpusa) | S09 |
| N9 | N2–N9 ledger | `shared/visestruki_povrat.py` | ISOLATED (stvaran model) | — | ne | S09 |
| BA-01 | BA01 ledger | prijem | BROWSER_INTEGRATION | uživo klijent+opis (mobilni test bez njih) | ne | S03 |
| BA-02 | BA01 ledger | prijem/OCR | LIVE | foto uživo | ne | S03 |
| BA-03 | BA01 ledger | ekstrakcija | ISOLATED | — | ne | S01/S03 |
| BA-04 | BA01 ledger | procesna hronologija | BROWSER_INTEGRATION (37/37) | — | ne | S05 |
| BA-05 | BA01 + PR #61/#62 | `shared/rokovi.py`, 144/145 | LIVE (P7714: 4 kandidata; `11eaeffc`: 4) | — | ne | S05 |
| BA-06 | BA01 ledger | lanac odluka | ISOLATED (PG) | uživo | ne | S05 |
| BA-07 | BA01 ledger | podsetnici | ISOLATED | isporuka | operativno | S11 |
| BA-08 | BA01 ledger | ažuriranje predmeta | ISOLATED + LIVE | — | ne | S08 |

Nijedna stavka nema nivo REAL_USER_ACCEPTED.

### Puna svita osnovice (lokalno, Windows, Python 3.11, stvaran Tesseract, `-p no:randomly`)
`a45b34ba` (worktree `C:/vindex-base-a45`): **9 failed / 12.815 passed / 396 skipped / 2 xfailed**. Padovi su isti ID-jevi kao na `c5f739f1` i ranijim osnovicama: `test_faza1_izvor_pod` ×6 (Playwright font merilo), `test_ns003_protocol::test_fixture_hesevi_su_zakljucani` (CRLF heš), `test_rc_cold_start` ×2 (git/commit okruženje). Svi su okruženje radne stanice; isti kod u CI-ju je 11/11. Svaka kasnija regresija se poredi sa ovim skupom po ID-ju.

### Gate S00: `PROVEN_CLOSED`
Izvor zahteva (kanon + 7 dokumenata), kod (`a45b34ba` = produkcija), migracije (142, 143, 144, 145 kolone PROVEN; UNIQUE indeksi UNKNOWN) i osnovica potvrđeni; nema divergentne istorije. Otvoreno i preneto: UNIQUE indeksi 144/145 (nema DB pristupa — INFERRED iz uspešnog spajanja #61/#62 i ponašanja: 4 roka, 4 `dogadjaj_event_id`, bez duplikata).

---

## S01 — B5: evidence provenance & fact integrity

**Zahtevi:** B5, BA-03 (delimično), INV-02, INV-04, INV-13, INV-14. **Preflight SHA:** `72fbb980` (= `a45b34ba` + S00 dokumentacija).

### Problem (PROVEN, reprodukovano pre izmene)
1. **Negacija/pripisivanje gubi se, a tvrdnja ostaje „Iz dokumenta“.** `shared/evidence_write.py::lociraj_tvrdnju` je prihvatala pogodak USRED rečenice. AI tvrdnja „isplatio zaradu za mart 2026. godine.“ iz rečenice „Tuženi **nije** isplatio zaradu …“ dobijala je `nacin_pronalaska = egzaktan` → `poreklo_tvrdnje` = SOURCE_FACT → V2 „Iz dokumenta“, „pronađeno u dokumentu“ (obrnut smisao). Isto: „zakup placen …“ iz „Tužilac tvrdi da je zakup placen …“ (navod stranke prikazan kao navod dokumenta bez pripisivanja), red-nastavak „hidroizolaciju krova.“ iz „Nosaci … **nisu** ostetili⏎hidroizolaciju krova.“ (MIR001 zlatni spis), odsečen broj („iznosi 500“ u „iznosi 5000“). Dokaz: novi test fajl na nepromenjenoj osnovici `a45b34ba` → **41 failed / 32 passed** (svi padovi su slučajevi koji moraju biti AI analiza).
2. **V2 „Pitanje“ tvrdi više od backend-a.** `frontend-v2-ng/src/pitanje-predmeta.js`: „Odgovor je dat uz beleške i **utvrđene činjenice** ovog predmeta“ / „nema … utvrđenih činjenica“, iako backend kontekst (VCR002 RC FIX 3) izričito kaže da nijedna tvrdnja nije utvrđena činjenica; postojeći `live-pitanje.mjs` je zaključavao taj tekst.
3. **V2 „Pripremljeno“ prazno stanje:** „U spisu nema **potvrđenih** činjenica.“ za listu stavki čije je poreklo navod/AI.

### Šta je već bilo ispravno (PROVEN postojećim testovima, nepromenjeno)
A doslovna rečenica (SOURCE_FACT, „navod iz dokumenta“ — nikad „utvrđeno“); B normalizovana (SOURCE_FACT); C parafraza (AI_ANALYSIS); F pogrešno pročitan iznos/datum (nije pronađen → AI); G ručna tvrdnja advokata (HUMAN_CONFIRMED, ponovna AI klasifikacija ne briše ljudske redove — `reklasifikuj` samo dodaje; čuvar `klasifikovan_at`); H obrisan dokument povlači svoje AI tvrdnje u istoj transakciji (137; `test_vcr002_rc_fix1_migracija137_pg`, `test_mir001_t03_kontinuitet::test_obrisan_izvor…`); I tenant B → 404/bez upisa (`test_impl001…g/g2`, `test_ns006_t4…b_ne_vidi_a`, `test_mir001_t03…korisnik_b…`); J retry/konkurentnost (`klasifikovan_at` čuvar, `test_vcr002_rc_fix1…konkurentan_upis`); K navod stranke ostaje navod (oznake „navod iz dokumenta, pronađen u tekstu“, „nijedna nije sudski utvrđena činjenica“, MIR001 TASK-03).

### Minimalna izmena
- `shared/evidence_write.py`: lokacija se vraća samo ako (1) pogodak počinje rečenicu (ispred: samo interpunkcija/navodnici/jedna oznaka nabrajanja), (2) ne seče reč ili broj. Granica rečenice je konzervativna (kad nije sigurno — nije granica → bezbedna strana „AI analiza“): tačka/upitnik/uzvičnik pred velikim slovom, ne posle skraćenice/inicijala/datuma; prelom reda samo posle zatvorenog reda (interpunkcija, zaglavlje velikim slovima koje se ne završava veznikom, naslov od jedne reči, ceo red = broj predmeta, oznaka „Naziv: ime/broj“) ili pred redom-nabrajanjem/oznakom. Normalizovana grana proverava isto na tekstu iste dužine sa sačuvanim prelomima (`_ws_sa_prelomima`, 1:1 sa `_normalize_ws`, fuzz 200.000 nizova).
- `routers/evidence.py`: prompt ekstrakcije — deo rečenice uvek od početka rečenice.
- `frontend-v2-ng/src/pitanje-predmeta.js`, `pripremljeno.js`: tekst bez „utvrđene/potvrđene činjenice“.
- **Non-goals / namerno nedirano:** šema i migracije, `poreklo_tvrdnje`, DC-005 (`snaga`), identitet tvrdnje, 137 invalidacija, Genome, postojeći produkcioni redovi (nema masovnog prepisivanja — postojeći `egzaktan` iz starog koda ostaju; produkcioni uzorak: 0 pogođenih), legacy `static/vindex.js` `reklasifikuj` (vidi rizike).

### Testovi i dokazi
| Šta | Rezultat |
|---|---|
| `tests/test_s01_poreklo_tvrdnji.py` (nov; matrica A–F, K, nalazi 3 kruga pregleda, E+D kroz stvaran prijem: dva `scan.pdf`, model vraća delove rečenica i rečenice DRUGOG dokumenta) | **73/73**; na osnovici 41 pada |
| Ciljana regresija (svih 159 test fajlova koji dodiruju dokaze/poreklo/Genome-v2) | **2556 passed / 0 failed** / 52 skipped |
| Browser: `live-pitanje.mjs` | 45/45 |
| Browser: `live-pripremljeno.mjs` (+ nov slučaj praznog stanja) | 54/54 |
| Mutacije (binarno, vraćanje svake grane ispravke i UI teksta) | **22/22 ubijeno** |
| Kolateral na stvarnim podacima | 38 tvrdnji iz 2 sintetička produkciona predmeta (samo čitanje): 0 promena; sačuvani izlazi stvarnog modela (MIR001 C2): 99/99 i 2/2 i dalje locirani, 5/5 fragmenata usred navoda stranke ispravno AI |
| Puna svita (lokalno) | **9 failed / 12.888 passed** — isti ID-jevi kao osnovica `a45b34ba` (0 novih padova; +73 nova testa) |

Izmenjeni postojeći testovi (promena ugovora, ne ublažavanje): ispuna zalepljena za citat („AAAA“+citat) odvojena granicom (akcija2 ×2, impl001, claim_identity); QA06 ×2 citat od početka rečenice („Dana 15.08.2026. predato je …“ umesto „predato je …“); MIR001 C2 red-okidač zatvoren tačkom; MIR001 T03 — dva reda-nastavka sada AI analiza (ostali navodi i dalje „Iz dokumenta“); `live-pitanje.mjs` — zaključan pogrešan tekst zamenjen proverom da tekst NE tvrdi utvrđene činjenice.

### Nezavisni adversarial pregled (3 kruga, zaseban agent, samo čitanje + probe)
- Krug 1: 2 HIGH (prelom reda pred velikim slovom prenosi negaciju; odsečen iznos/datum), MEDIUM skraćenice/datumi, FN nabrajanja, UI „potvrđenih činjenica“, prompt traži „deo rečenice“ — sve ispravljeno.
- Krug 2: HIGH oznaka govornika kao uvod u navod („Svedok: Ne sećam se da je⏎Tuženi …“), MEDIUM datum pred velikim slovom, hiljade sa razmakom, preširoka pravila zatvorenog reda, FN lista posle „:“ — ispravljeno.
- Krug 3: HIGH red koji se samo završava referencom („… ugovorom br. 15/2026⏎Tuženi …“), MEDIUM zaglavlje „NIJE TAČNO DA JE“ — ispravljeno; ostalo ocenjeno kao malo realno. Pregled potvrđuje: lažno pozitivni nisu zamenjeni neprihvatljivim lažno negativnim (svi preostali FN su na bezbednoj strani, stvarni izlazi modela bez gubitka).

### Preostali rizici (poznati, dokumentovani)
- LOW: kraj rečenice se ne zahteva — „Zakup je plaćen“ iz „Zakup je plaćen, navodi tužilac.“ ostaje „Iz dokumenta“ (tekst jeste u dokumentu; UI svuda kaže „navod, nije utvrđena činjenica“).
- LOW: „… br. 15/2026. Tuženi …“ u istom redu (tačka iza rednog broja pred velikim slovom je granica, zbog „Član 1. Ugovorna …“); ostali malo realni slučajevi iz kruga 3 (`scratchpad/s01/review/probe3.py`).
- LOW (bezbedna strana): neki tačni citati posle zaglavlja malim slovima bez interpunkcije („Zapisnik o glavnoj raspravi⏎Tuženi …“) postaju AI analiza.
- Postojeći produkcioni redovi nisu ponovo locirani (nema backfill-a — zabranjeno bez odobrenja); uzorak 38/38 nepogođen.
- Legacy `static/vindex.js` → `POST /reklasifikuj` dodaje AI tvrdnje istog dokumenta ponovo (duplikati); nije V2 tok, nije menjano.
- Leksička provera ne razume semantiku (tekst postoji u dokumentu ≠ istinit); to je ugovor (INV-04), ne kvar.

**Gate S01: `PROVEN_CLOSED` (nivo LOCAL + BROWSER_INTEGRATION; nije LIVE — kod nije pušten).**

**S01 lokalni commit:** `68848d84`.

---

## S02 — B7: semantic contradiction integrity — `BLOCKED_PRODUCT_DECISION`

**Zahtevi:** B7, INV-07, INV-08, INV-09, INV-13. **Preflight SHA:** `68848d84`.

### Problem (PROVEN)
- **Produkcija, samo čitanje (sintetički predmeti):** Genome je u dva predmeta proizveo 4 neutemeljene protivrečnosti.
  - `11eaeffc`:
    - „Razlika u rokovima za uplatu takse“ — rok za sudsku taksu 04.12. ↔ rok za DODATNU sudsku taksu 27.11. Stanje: **OPEN**, aktivna, sa akcijom.
    - „Razlika u datumu dokumenta“ — „DATUM TEST DOKUMENTA: 30.10.“ ↔ „Tužba je pripremljena 31.10.“. Stanje: NOT_OBSERVED.
    - „Sintetički test“ — dve izjave istog dokumenta. Stanje: NOT_OBSERVED.
  - P7714: „Razlika u datumu odluke“ — rok za žalbu 05.11. ↔ „Odluka je doneta 20.10.“. Stanje: NOT_OBSERVED.
  - Zajednički obrazac: izvori i `claim_ids` su ispravni, ali nije dokazano da se tvrdnje odnose na isti događaj ili obavezu. Svaki naredni Genome ih ponovo predlaže, u drugom obliku.
- **Izolovana reprodukcija (stvaran prijem, dispečer, V2 paket, `genome-v2`, Case Actions; zamenjen samo model):** produkcioni par taksi, rokovi za podnesak dve stranke i rok ↔ datum odluke postaju **AKTIVNA** V2 sporna tačka sa akcijom „Razrešiti kontradikciju“ (3/3 testa padaju na `68848d84`).

### Šta je pokušano (nacrt, lokalna grana `bojan/s02-b7-istovetnost-nacrt` @ `affae433`, NIJE na sprint grani)
- Materijalizacija dobija treći ishod, „za pregled“, za protivrečnost čija istovetnost nije dokazana. Ne postaje V2 sporna tačka, ne pravi akciju, opažanje ostaje nekompletno (ništa se ne zatvara), a prikazuje se pod „traži vaš pregled“. Ranije sačuvana aktivna sporna tačka ne menja se nego dobija oznaku.
- **Pravilo istovetnosti, verzija 1** — „fraza obaveze nije identična“. Nezavisni pregled: **HIGH**, svaka parafraza iste obaveze postaje pregled. To su rok bez „godine“, ćirilica, „dana“, tekst posle datuma i drugačiji opisni oblik. Recenzentov e2e: 3 stvarne protivrečnosti u pregledu, a lažna „dve radnje istog dana“ aktivna.
- **Pravilo istovetnosti, verzija 2** — pozitivan dokaz razlike: R1 druga stranka, R2 odrednica više, R3 OCR. Testovi: 17/17 S02, ciljano 4209/0, browser 47/47 i 50/50, mutacije 12/12.
  - Nezavisni pregled, krug 2 — **HIGH:** R2 kratak i pun naziv iste obaveze proglašava za dve obaveze („rok za uplatu takse“ ↔ „… sudske takse“; „rok za žalbu“ ↔ „… na rešenje“; „rok za odgovor“ ↔ „… na tužbu“).
  - **MEDIUM:** R1 čita uvodne reči kao stranku („Prema rešenju, …“ ↔ „Prema nalogu, …“).
  - **MEDIUM:** obavezni negativni slučajevi koji i dalje ostaju AKTIVNI:
    - dve nezavisne radnje istog datuma;
    - rok ↔ događaj (produkcioni „datum odluke“);
    - raniji rok ↔ nova zasebna obaveza sa drugačijim predmetom;
    - različita lica kada stranka nije u istom redu;
    - opisni oblik obaveza;
    - dva produkciona lažna nalaza bez roka.

### Zašto je ovo blocker, a ne nastavak
Da li dve tvrdnje opisuju ISTU obavezu ili događaj je semantičko pitanje. Ugovor zabranjuje filter po rečima („taksa“) i univerzalno pravilo „različiti datumi nisu protivrečnost“. Leksičko pravilo zato mora da bira između dve vrste greške, a obe krše prihvatne kriterijume S02:
- lažno pozitivne — neutemeljen aktivni nalaz;
- lažno negativne — stvarna protivrečnost skinuta sa aktivnih.

Postojeći ugovor ima reprezentaciju neodređenosti (`ZA_PREGLED` u prikazu; `DISCOVERED` = „provizorna, bez trajnih posledica“; `CONFIRMED` = „tek tada sme nositi akcije“ — `shared/issue_v2.py`). Međutim, danas svaka V2 sporna tačka u stanju `DISCOVERED` nosi akciju i prikazuje se kao aktivna. Koji podrazumevani status AI protivrečnost dobija pre advokatove odluke je **produktna odluka**.

### Minimalne opcije za osnivača
| Opcija | Šta znači | Posledica |
|---|---|---|
| **A. Pregled pre aktivnog** (preporuka) | Svaka AI protivrečnost u stanju `DISCOVERED` prikazuje se pod „traži vaš pregled“ (sa oba izvora). Aktivna je i nosi akciju tek kad je advokat potvrdi — tačno ono što `issue_v2` već definiše (`DISCOVERED` / `CONFIRMED`). | Rešava SVE lažne pozitive bez semantičkog pogađanja. Advokat jednim klikom potvrđuje stvarne. Menja današnji prikaz i akcije; traži potvrdu protivrečnosti u V2 (postojeći status `CONFIRMED`, verovatno bez migracije — proveriti). |
| B. Model iskazuje istovetnost | Genome za svaku protivrečnost vraća „isti događaj/obaveza: da/ne/nepoznato“ + predmet. Backend: sve osim „da“ ide u pregled. | Manja promena prikaza. Oslanja se na model koji je i napravio lažni nalaz (delimično pouzdano). Nova polja u izlazu modela. |
| C. Ostaviti aktivno uz oznaku | Sve AI protivrečnosti sa datumima ostaju aktivne uz oznaku „nije provereno da je isti događaj/obaveza“. | Najmanja promena. Ne ispunjava „ne daje neutemeljen aktivni nalaz“. |
| D. Nacrt `affae433` | Uže pravilo (R1–R3). | Rešava tačan produkcioni par. Nezavisni pregled ga ocenjuje kao neprihvatljiv rizik lažno negativnih. Nije preporučeno. |

### Stanje
- Ništa iz S02 nije na sprint grani.
- Produkcioni `predmet_issues` / `predmet_contradictions` redovi nisu dirani.
- Sprint je zaustavljen po ugovoru („na prvom neotklonjenom blocker-u zaustavi ceo sprint“).
- S03–S11 nisu započeti.

### S02 nastavak — odluka osnivača: OPCIJA A (2026-10-31/11-01) — `PROVEN_CLOSED`

**Odluka (citat suštine):** AI protivrečnost je kandidat za pregled advokata, ne potvrđena protivrečnost; aktivna i izvršiva je tek posle izričite potvrde ovlašćenog advokata; odbijeni kandidat izlazi iz aktivnih tokova uz istoriju i audit. Bez leksičkih pravila, bez AI sudije, bez automatske potvrde.

**Postojeća infrastruktura koja je to već podržavala (PROVEN čitanjem SQL-a i PG testom):** `predmet_issues.status` DISCOVERED („provizorna“) / CONFIRMED („tek tada sme nositi akcije“) / RESOLVED + `close_reason = WITHDRAWN` (migracija 119); RPC opažanja (120–125) status teme nikad ne menja i ponovo opaženu temu nalazi po otisku početnog skupa tvrdnji. Bez migracije, bez nove tabele.

**Implementacija (najmanji ceo tok):**
- `routers/sporna_tacka.py` (nova ruta): `POST /api/predmeti/{pid}/sporne-tacke/{iid}/potvrdi|odbij`. Pravila:
  - vlasnik predmeta i teme (`user_id`); 404 za tuđe i neispravan UUID;
  - obavezno `ocekivano` {status, odluka_at, sadrzaj} = ono što je advokat VIDEO → inače 409;
  - uslovni upis (status + `updated_at`); vreme odluke = vreme baze (`'now'`);
  - provera verzije sadržaja pre i POSLE upisa (opažanje drži zaključan red teme), pa vraćanje i 409;
  - obavezan audit (`sporna_tacka_potvrdjena` / `_odbijena`, sa prethodnim stanjem i verzijom sadržaja); bez audita se odluka vraća i odgovor je 503;
  - odluka se može promeniti u oba smera, svaki put uz audit; ponovljen klik ne piše ništa;
  - događaj `ManualCorrectionApplied` usklađuje akcije.
- `shared/issue_v2.py`:
  - `efektivna_odluka` / `novo_posle_odluke`: odluka važi samo za sadržaj koji je postojao kad je doneta; nova tvrdnja ili relacija → ponovo „čeka odluku“;
  - `verzija_sadrzaja`;
  - `oznaci_kontradikcije_analize`: za AI potrošače izostavlja odbijene i označava ostale.
- `services/v2_projection.py`: akcija „Razrešiti kontradikciju“ samo za efektivno potvrđene; čitači nose vreme odluke i vremena opažanja; `kontradikcije_analize_za_ai`.
- `services/v2_contradiction_persistence.py`: nova tema čiji otisak već postoji šalje se sa tom temom i njenim `xmin`. Opažanje pročitano pre odluke tada pada (55000), umesto da tiho doda sadržaj pod odluku. Ishod identiteta je isti kao RPC-ov sopstveni put po otisku (potvrdio pregled).
- `shared/genome_contract.py`:
  - stanja NEPOTVRDJENA (za pregled, sa dugmadima), AKTIVNA (samo potvrđena), ODBIJENA (istorija, „Ipak potvrdi“);
  - protivrečnosti iz analize samo kad predmet nema nijednu V2 temu (ne vraćaju se odbijene);
  - verzija sadržaja u `odluka.sadrzaj`;
  - kontekst pitanja razlikuje potvrđenu, nepotvrđenu i odbijenu.
- `services/case_evolution.py`:
  - legacy Rule 3 (akcija iz analize bez V2) uklonjen — nepotvrđeno ne nosi akciju;
  - istinit razlog zatvaranja V2 radnje (`PROTIVRECNOST_ODBIJENA` / `PROTIVRECNOST_NIJE_POTVRDJENA`; završen predmet zadržava opšti razlog).
- AI potrošači:
  - `shared/case_context` → gap_engine (sudska prognoza, priprema ročišta, CIO, copilot): oznaka „[nepotvrđena …]“, odbijene izostavljene;
  - `routers/case_intelligence` (čita iz konteksta), `strategy_simulator`, `copilot` (slabosti, upozorenja) i `multi_agent` (sporne tačke + Genome blok, potvrđene prve);
  - graf dokaza: samo potvrđene.
- V2 UI (`analiza-predmeta.js`, `index.html`):
  - naslov „Predlozi analize — nisu potvrđeni, čekaju vašu odluku“;
  - Potvrdi / dvostepeno Odbaci / „Ipak potvrdi“;
  - šalje viđeno stanje i sadržaj;
  - poruka tvrdi samo zabeleženu odluku; fokus i živi region.

**Dokazi:**
| Šta | Rezultat |
|---|---|
| `tests/test_s02_kontradikcije_potvrda.py` (stvarne rute nad bazom u memoriji) | 19 testova. Pokriva: kandidati sa izvorima i bez akcije; potvrda, odbijanje i istorija; osvežavanje bez duplikata; promena odluke uz audit; zastareo prozor; tenant B i neprijavljen; audit pad; kontekst pitanja; analiza bez tvrdnji; H1, H2 i M1; razlog zatvaranja; UUID; R2-H1 (pre i tokom upisa); R3-M2 |
| `tests/test_s02_odluka_postgres.py` (PostgreSQL 17.9, migracije 119–125) | 5/5. Pokriva: odbijena se ne vraća, potvrđena opstaje; trka dve odluke (tačno jedna); opažanje pre odluke odbijeno; odluka ne važi za kasniji sadržaj; paket pre „Ipak potvrdi“ (55000) |
| Browser `live-s02-protivrecnost-e2e.mjs` (pravi api.app, 390 px) | 21/21. Pokriva: kandidati; potvrda u UI-ju; radnja samo za potvrđenu; B 404; API bez viđenog stanja 409; dvostepeno odbijanje; „Ipak potvrdi“; osvežavanje; zastareo prozor; 0 spoljnih veza i 0 grešaka |
| Browser regresija | `live-analiza` 46/46, `live-cg001-kontinuitet` 50/50, `live-pitanje` 45/45, `live-pripremljeno` 54/54, `live-solo-tok-e2e` 23/23, `live-matter` 56/56, `live-zlatni-prijem-e2e` 48/48. Jedan od tri prolaza `live-analiza` i `live-zlatni-prijem` imao je padove tajminga pod opterećenjem; ponovljeno 2× potpuno zeleno |
| Ciljana regresija (svi testovi protivrečnosti, akcija, Genome-a i konteksta, uz PG) | 6697 passed / 7 failed. Svih 7 su poznati padovi okruženja iz osnovice |
| Mutacije (binarno) | prva grana 9/9; konačna 20/20 (B1–B20) |
| Puna svita | **9 failed / 12.886 passed** — isti ID-jevi kao osnovica `a45b34ba` |
| Nezavisni pregled (4 kruga) | 2 HIGH + 4 MEDIUM → 1 HIGH + 2 MEDIUM → 2 MEDIUM → **bez HIGH/MEDIUM; „S02 acceptance (Option A) is met“** |

**Izmenjeni postojeći testovi (promena ugovora, opisano u svakom):**
- tokovi POTVRĐENIH protivrečnosti dobijaju potvrdu advokata: prekidač `ns006_fake.ADVOKAT_POTVRDJUJE` i `CONFIRMED` + vreme odluke u fiksturama — MIR001, NS006, NS007, CG001, A015;
- prikaz analize bez tvrdnji: „za pregled“ umesto „aktivne“;
- `test_omega_sprint003…rule3` pretvoren u dokaz da nepotvrđene ne prave akciju;
- 19 testova detalja uklonjene legacy Rule 3 putanje preskočeno uz razlog: A003 ×14 (jedan bi prolazio nad praznom listom), omega004 ×2, sigma002 ×2, singlebrain ×2;
- `ns006_fake` emulira pronalaženje teme po otisku (kao migracija 120, dokazano PG testom).

**Produkcija (samo čitanje, ništa nije menjano):**
- stanje: 10 spornih tačaka, sve DISCOVERED (potvrda do sada nije bila moguća); 5 otvorenih V2 protivrečnosti; **5 otvorenih V2 radnji „Razrešiti kontradikciju“ u 4 predmeta**;
- posle puštanja: protivrečnosti postaju kandidati za odluku; tih 5 radnji zatvara se pri prvom sledećem događaju svog predmeta, sa razlogom `PROTIVRECNOST_NIJE_POTVRDJENA`;
- produkcioni par „takse“ biće kandidat, ne aktivna protivrečnost.

**Preostali rizici (LOW):**
- odluka nad temom bez otvorenih kontradikcija moguća je samo kroz API (konstantna verzija sadržaja);
- `law_brain` broji DISCOVERED u sličnosti profila (označeno kao AI rad);
- zaštita od trke u jednom procesu važi kao i ranije;
- ručno osvežavanje Genome-a ne usklađuje akcije samo po sebi — to radi sledeći događaj (postojeće ponašanje).

**Nacrt `bojan/s02-b7-istovetnost-nacrt` (`affae433`)** ostaje kao istorija; nije deo rešenja.

---

## S03 — BOJAN N1/N2: kompletan prijem — `PROVEN_EXISTING_NO_CHANGE` (proizvod) + ispravljen testni orakl

**Pokriva:** N1 (prijem), N2 (čarobnjak), INV-01, INV-02, INV-03, INV-10, INV-13. **Preflight:** `c9da66dc` (S02), radno stablo čisto.

**Zahtev → dokaz (svi nad pravim api.app i bazom koja upisuje, simulirani samo modeli/embedding/prijava):**
| Acceptance | Dokaz | Nivo |
|---|---|---|
| Tačno jedan predmet | `live-zlatni-prijem-e2e` G; `live-n2-carobnjak-e2e` 4 (istovremeni zahtevi → 1 predmet, drugi 409); `test_n1_zlatni_prijem` | BROWSER_INTEGRATION |
| Tačna veza klijent–predmet | zlatni G (1 klijent, 1 veza, posle reload-a klijent prikazan); N2 1/2 (imenjaci — vezan IZABRANI) | BROWSER_INTEGRATION |
| Opis i cilj sačuvani | zlatni G (`opis_sacuvan`; posle reload-a „Cilj: …“ u izmeni predmeta); `test_n1` (`MARKER` i „Cilj:“ u `predmeti.opis`) | BROWSER_INTEGRATION |
| Svaki validan dokument → isti predmet | zlatni G **sa stvarnim Tesseract OCR-om: 4/4 formata (digitalni PDF, sken PDF, PNG, DOCX)**, poreklo = posao prijema A; bez OCR-a: 2 čitljiva prikačena, sken/foto vidljivo neprikačeni | BROWSER_INTEGRATION |
| Nema lažnog OCR uspeha | zlatni G bez OCR-a (bez „pročitan OCR-om“, tačan razlog); **nov E4b: stvaran OCR koji delimično pogrešno pročita sliku („05.02.2028“) → NIJE prikačen, razlog rečen**; `test_n1::test_neprocitan_sken…` | BROWSER_INTEGRATION |
| Bez dupliranja na retry | zlatni E (dupli klik → 1 dokument; nepoznat ishod iz opisa i iz dokumenta → 1 predmet; ponovljen sadržaj → postojeći posao); `live-prijem-oporavak-e2e` (kvar baze, ubijen proces posle zauzeća); `test_ocr001_trka_postgres` (PostgreSQL trka finalize-a) | BROWSER_INTEGRATION + ISOLATED (PG) |
| Tuđ nalog 403/404 | zlatni E6 (predmet, dokument, posao, ispravka, finalize, klijent → 404/403; B ništa nije promenio); N2 4 | BROWSER_INTEGRATION |
| COI pravilo nepromenjeno | nijedan COI fajl nije diran; zlatni E5, N2 2b/2c/2d, `test_coi_intake_convergence`, `test_n4_coi001…` | BROWSER_INTEGRATION |

V2 nema poseban ekran klijenta: „ponovo učitaj klijenta“ = klijent u predmetu posle reload-a (zlatni G) + kartoteka u čarobnjaku (N2). Nov ekran nije u opsegu.

**Pronađeno i ispravljeno (samo test):** browser zlatni tok nikad nije bio pokrenut sa stvarnim OCR-om (lokalno nema Tesseract-a; CI ne pokreće V2 browser testove). Sa OCR-om (env311) pao je 3/46. Fotografija je bila nacrtana PIL podrazumevanim fontom od ~10 px; Tesseract je pročitao delimično i pogrešno (`UUrucenodana05.02.2028`), a ekstraktor ju je **s pravom** odbio (`_kratak_ocr_procitan`, prag 0,75) uz tačnu poruku. Proizvod je ispravan; orakl je bio pogrešan. Izmena:
- fotografija se pravi kao u Python zlatnom testu (helv 20 pt, 200 dpi);
- stara sitna slika postaje negativni slučaj E4b;
- OCR provera G zahteva `ocr === 2` i oba slikovna dokumenta prikačena sa tekstom (ranije je prolazila i kad fotografija nije prikačena).

**Dokazi:**
| Šta | Rezultat |
|---|---|
| Python prijem/N1/N2/COI/PG trka (14 fajlova) | 174 passed |
| `live-zlatni-prijem-e2e` stvaran OCR | pre: 43/46 (3 FAIL) → posle: **47/47** (OCR pročitao 2 dokumenta) |
| `live-zlatni-prijem-e2e` bez OCR-a | 48/48 |
| `live-n2-carobnjak-e2e` / `live-prijem-carobnjak-e2e` / `live-prijem-oporavak-e2e` / `live-prijem` / `live-prijem-pracenje` | 27/27 · 37/37 · 18/18 · 53/53 · 29/29 |
| Mutacija M1 (kratak OCR prihvaćen bez praga pouzdanosti) | UBIJENA — E4b pada |
| Nezavisni pregled | tvrdnja „proizvod ispravan, fikstura pogrešna“ potvrđena; prijavljena 2 MEDIUM UX nalaza (dole) |

**Pokušana pa vraćena ispravka (zapis radi istine):** po nalazu pregleda probao sam da zaglavlje i dugmad za nepročitan dokument budu tačni i posle reload-a. Signal je bio `ocr_failed` bez polja. Mutacije i regresija su to oborile: **kratak digitalni PDF dobija isti trag (`is_scanned=True`, `ocr_failed []`) a ima tekst koji finalize prikačuje**, pa bi ispravka sakrila dugme „Prikači“ za dokument koji se može prikačiti (`live-prijem-oporavak` pao). Istinita ispravka traži trajni podatak koji danas ne postoji (kolona/migracija ili promena sadržaja reda pregleda koji advokat vidi) — van minimalnog opsega. Izmena proizvoda je u potpunosti vraćena; regresija posle vraćanja zelena.

**Preostali rizici:**
- MEDIUM (UX, poznato, nije lažan uspeh): za dokument iz kog nije izdvojen tekst, zaglavlje posle „Potvrđujem pregled“ kaže „Obrađeno — spremno za prikačivanje“ i nudi „Prikači“. Pokušaj daje tačnu poruku „Dokument NIJE prikačen … Ponovno prikačivanje neće pomoći“. Ako se posle neuspeha stranica ponovo učita, nudi se „Ponovite prikačivanje“, a ponovni pokušaj opet daje tačnu poruku. Nema prikačivanja, nema lažnog teksta, nema duplikata. Ispravka traži odluku o trajnom znaku „tekst nije izdvojen“ (verovatno migracija).
- LOW: G proverava da je fotografija pročitana i prikačena, ne i tačan sadržaj (datum). Tačnost OCR-a meri `test_ocr001_ocr_korpus` (CER/WER) u produkcionoj slici.
- LOW: CI ne pokreće V2 browser testove; ovaj rezultat je lokalni BROWSER_INTEGRATION.
- LOW: postojeći `nistaProcitano` u UI-ju sakriva vrstu dokumenta i kod kratkog digitalnog PDF-a dok pregled nije potvrđen (isti dvosmislen trag) — postojeće ponašanje, nije menjano.

**Fajlovi:** izmenjen samo `frontend-v2-ng/tests/live-zlatni-prijem-e2e.mjs`. Namerno nedirnuti: `routers/smart_intake.py`, `frontend-v2-ng/src/prijem-predmeta.js`, `uploaded_doc/extractor.py`, `shared/intake_worker.py`, COI.

**Kapija S03: `PROVEN_EXISTING_NO_CHANGE`** (proizvod), uz ispravljen i pojačan testni orakl.

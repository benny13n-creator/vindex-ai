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

# VCR002 — predaja kandidata za izdanje

## Presuda: **CONDITIONAL GO — VERIFIED CANDIDATE, EXACT LIMITED DEPENDENCY**

Kandidat je bezbedan za spajanje: nema materijalnog bezbednosnog kvara ni kvara integriteta, a svaki proizvodni kvar nađen u programu je ispravljen i dokazan. Uslov je samo ono što ovaj program **ne može** da dokaže bez vas: prijavljena provera u produkciji (QA nalog), tajna za podsetnike i stvaran pilot predmet. Ti uslovi ne blokiraju spajanje. Blokiraju samo tvrdnju „radi u produkciji za prijavljenog advokata“.

## 1. Kandidat

- **Grana:** `program/vcr002-beta-operational-closure`, Draft PR **#20**.
- **Kandidat (kod):** `38ac5fcd` (poslednja kodna izmena). Docs commit-i posle njega ne menjaju kod.
- **Osnova:** `main` = produkcija `b36235a3`.

## 2. Obim izmena (bez migracija, tajni, cena, Cron-a)

| Oblast | Fajlovi |
|---|---|
| Brisanje dokumenta povlači AI tvrdnje | `api.py` (`predmet_dokument_obrisi`) |
| Podsetnici | `routers/email_notif.py`, `.github/workflows/sms-cron.yml` |
| Savetnici (paralelno, niz, citati, granica poverenja) | `routers/multi_agent.py`, `security/prompt_guard.py` (+1 oznaka), `shared/idempotency.py` (+1 ruta) |
| V2 | `frontend-v2-ng/index.html`, `src/agenti-predmeta.js`, `src/app.css` |
| CI | `production-runtime.yml` (T02 korpus u produkcionoj slici), `.gitleaksignore` (1 obrazložen lažno pozitivan nalaz u dokumentaciji) |
| Testovi | 5 novih Python fajlova, 2 frontend testa, fixture, `osb003_solo_server.py` (blok uz `VX_AGENTI=1`) |

## 3. Tačno dokazane sposobnosti

| Sposobnost | Nivo |
|---|---|
| OCR skenirane srpske ćirilice, i u mešovitom PDF-u, kroz stvaran worker do teksta dokumenta predmeta | ISOLATED u **produkcionoj Docker slici** (32/32) |
| Predmet sa više dokumenata: identiteti, tvrdnje po izvoru, protivrečnost, hronologija sa izvorom, rok → potvrda → akcija, pitanje, istorija | ISOLATED (stvarne rute) |
| Obrisan izvor više nije merodavan | ISOLATED + mutacije |
| Podsetnik samo za potvrđen rok; dva roka istog dana; predmet u brisanju | ISOLATED (stvarna kapija potvrde) |
| Paralelni savetnici i niz savetnika sa istim ugovorom kao pojedinačni | ISOLATED + mutacije 14/14 |
| Sva tri načina rada savetnika u V2 | BROWSER_INTEGRATION nad pravim `api.app` (18/18) i fixture-om (43/43) |
| Autonomija NS007 | ISOLATED nad **stvarnim PostgreSQL-om** (163/163) |

## 4. Tačna nerazrešena ograničenja

- **`LIM-T01`:** nijedan prijavljen tok nije posmatran u produkciji (nema QA naloga).
- **`LIM-T02-1`:** posle neočekivane greške baze tokom prikačivanja, ponovni pokušaj oko 120 s dobija 409 „u toku… za par sekundi“. Integritet je očuvan, a poruka je netačna u trajanju.
- **`LIM-T06-1`:** pad radnika usred niza ostavlja ključ u stanju IN_PROGRESS. Nova radnja advokata ponovo naplaćuje već plaćene korake prekinutog izvršenja.
- **`OBS-T03-1`:** kontekst pravnog pitanja AI tvrdnje naziva „Utvrđene činjenice … snaga=jaka“, i dve protivrečne bez oznake (tekst prompta; odluka).
- **`OBS-T03-2`:** rok iz obrisanog dokumenta ostaje u hronologiji kao istorija bez izvora, ali **nepotvrđen**, pa nikad nije operativan.
- **`LIM-T03-3`:** sačuvan Genome (`case_dna.kontradikcije`) može do sledećeg osvežavanja da navodi protivrečnost čija je tvrdnja povučena brisanjem dokumenta. Sledeće osvežavanje je ne vidi (dokazano).
- **Podsetnici i SMS:** isporuka nije posmatrana (tajna). SMS ruta prima samo osnivačev JWT.
- `FLAKY-DEMO-PIKSEL` (nasleđeno, prag nije menjan).

## 5. Knjiga zadataka

`VCR002_TASK_LEDGER.md` (T00–T10) · `VCR002_MASTER_STATE.md` · `VCR002_REQUIREMENTS_STATE.md` · `VCR002_T09_AUTONOMY_ACTIVATION.md` · `VCR002_TEST_EVIDENCE.md`.

## 6. CI na kandidatu (poređenje identiteta palih testova sa `main` `b36235a3`)

Popunjeno u §6a (posle poslednjeg pokretanja).

## 7. Frontend (lokalno, sve `verify*` + `e2e:*` skripte)

**45/45 PASS** na `aabbff26` (frontend nije menjan posle toga), uključujući `verify:live-agenti` 43/43 i `e2e:savetnici` 18/18. CI V2 NG na `aabbff26`: **success**.

## 8. Produkcioni testovi i rezultat

| Provera (bez prijave) | Rezultat |
|---|---|
| `/health` | `commit b36235a`, redis ok |
| `/app`, `/app-legacy`, VCR001 moduli | 200 |
| zaštićene rute bez tokena | 401 |
| `/email-notif/send-reminders` bez ključa | 403 |
| `/api/cron/autonomy` bez tajne | 401 |
| zakazani email posao (6 dana) | 6/6 HTTP 403 |
| zakazani SMS posao | 401, prijavljen kao uspeh (ispravljeno u kandidatu) |

**Postupak za živu proveru**, kad postoji QA nalog:
1. prijava → reload → odjava;
2. nov predmet;
3. upload 3 sintetička PDF-a iz `tests/test_vcr002_t02_ocr_korpus.py` (generišu se lokalno), od kojih je jedan ćirilični sken;
4. pregled teksta;
5. potvrda roka;
6. pitanje;
7. jedan savetnik, pa paralelno, pa niz (≤ 7 plaćenih poziva);
8. nacrt → izmena → odobrenje → DOCX;
9. reload.

## 9. Efekti na naplatu

- Cene i tarife nisu menjane.
- Paralelno: naplata po isporučenom odgovoru (kao pre); **nova provera budžeta pre poziva** (402 umesto plaćenih poziva bez naplate); dupli savetnik se više ne plaća dvaput.
- Niz: provera budžeta za ceo niz pre prvog koraka; naplata po koraku (kao pre).
- Ponovljen mrežni zahtev sa istim `Idempotency-Key` više se ne naplaćuje (trajno, migracija 134).

## 10. Bezbednosna presuda

**Nema novog bezbednosnog nalaza.** Ojačano:
- granica poverenja za opis predmeta i izlaz prethodnog savetnika;
- vlasništvo predmeta u paralelnom radu;
- sirove greške provajdera više ne izlaze.

Gitleaks: 1 lažno pozitivan nalaz u dokumentaciji (vrednost kolone `ai_klasifikacija`), pročitan iz blob-a i obrazložen u `.gitleaksignore`. JWT izuzetak (do 2027-01-09) je nepromenjen.

## 11. Kompatibilnost baze

Nijedna nova kolona, tabela ni RPC.
- Koriste se postojeće tabele i kolone: `predmet_dokazi.deleted_at` / `izvor_tvrdnje` / `nacin_pronalaska`, `predmeti.brisanje_zapoceto` i `v2_mutation_idempotency`.
- `brisanje_zapoceto` ima rezervni upit ako kolona ne postoji.

## 12. Zahtevi za migracije

Nema. Migracija 136 (autonomija) je zasebna odluka (T09).

## 13. Spoljne zavisnosti

- GitHub Actions (planirani poslovi se izvršavaju sa `main`-a, pa ispravka SMS posla deluje tek posle spajanja);
- Render (`CRON_SECRET`, SMTP);
- OpenAI / Pinecone (nepromenjeno).

## 14. Ograničenja vraćanja

Vraćanje na `b36235a3` je čisto: nema šeme ni podataka koje kandidat jedini razume. Posle vraćanja nestaju ispravke i V2 načini rada. Meko povučene tvrdnje (`deleted_at`) ostaju povučene.

## 15. Odluke osnivača

1. **Puštanje kandidata** `38ac5fcd` (spajanje PR #20 → automatski deploy).
2. **QA nalog** za prijavljenu proveru (T01), uz kanal za kredencijale van repo-a.
3. **Podsetnici:**
   - uskladiti `CRON_SECRET` (Render) i `CRON_TOKEN` (GitHub), ili postaviti `CRON_SECRET`;
   - potvrditi `EMAIL_SMTP_*`;
   - odobriti jedan test primalac za jednu probnu isporuku.
4. **SMS cron:** dodati prihvatanje cron ključa (uključuje stvarno slanje SMS-a korisnicima) ili ugasiti posao.
5. **Autonomija:** migracija 136, tajna, budžet, prvi ciklus, kadenca, Cron (`VCR002_T09_AUTONOMY_ACTIVATION.md`).
6. **Pilot predmet** sa 3–4 stvarna dokumenta (B13 stvaran), uz dozvolu i pravila poverljivosti.
7. **Miroslavljev izvorni dokument** (nije u repo-u ni na Drive-u).
8. **Strategija, prediktor, šabloni u V2** (AI-pomaže / AI-odlučuje).
9. **`OBS-T03-1`:** tekst konteksta pitanja („Utvrđene činjenice“ → npr. „Tvrdnje iz dokumenata (AI, neproverene)“, uz oznaku protivrečnosti).

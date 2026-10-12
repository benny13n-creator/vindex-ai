# VCR002 — predaja kandidata za izdanje

## Presuda (posle zatvaranja izdanja, 2026-10-12): **GO za spajanje kandidata `056a48e6` uz vaše odobrenje tačno tog kandidata**

Tri rizika koja su blokirala spajanje su zatvorena: integritet brisanja dokumenta, oporavak plaćenog niza i „utvrđene činjenice“. Sva tri su reprodukovana, imaju regresione testove i mutacije, a CI nema nijedan nov pad (detalji u `VCR002_RELEASE_CLOSURE.md`).

Ono što ostaje **ne blokira spajanje**, već tvrdnju „radi u produkciji za prijavljenog advokata“:
- QA nalog;
- tajna za podsetnike;
- pilot predmet;
- primena migracije 137. Bez nje radi bezbedan put sa kompenzacijom.

Prethodna presuda (CONDITIONAL GO za `38ac5fcd`) je **zamenjena**. Kandidat `38ac5fcd` se više ne preporučuje.

## 1. Kandidat

- **Grana:** `program/vcr002-beta-operational-closure`, Draft PR **#20**.
- **Kandidat (kod):** **`056a48e6`** (`38ac5fcd` + FIX 1 `80dc114e` + FIX 2 `a1468152` + FIX 3 `056a48e6`). Docs commit-i posle njega ne menjaju kod.
- **Osnova:** `main` = produkcija `b36235a3`.

## 2. Obim izmena (jedna nova migracija u repo-u — 137, NIJE primenjena; bez tajni, cena, Cron-a)

| Oblast | Fajlovi |
|---|---|
| Brisanje dokumenta povlači AI tvrdnje (atomski, RC FIX 1) | `api.py` (`predmet_dokument_obrisi`), `services/event_bus.py`, **migracija 137 (nije primenjena)** |
| Kontekst pravnog pitanja: poreklo tvrdnji i sporne tačke (RC FIX 3) | `api.py` (`pitanje`), `shared/genome_contract.py` |
| Podsetnici | `routers/email_notif.py`, `.github/workflows/sms-cron.yml` |
| Savetnici (paralelno, niz, citati, granica poverenja) | `routers/multi_agent.py`, `security/prompt_guard.py` (+1 oznaka), `shared/idempotency.py` (+1 ruta) |
| V2 (niz savetnika isključen, RC FIX 2) | `frontend-v2-ng/index.html`, `src/agenti-predmeta.js`, `src/app.css` |
| CI | `production-runtime.yml` (T02 korpus u produkcionoj slici), `.gitleaksignore` (1 obrazložen lažno pozitivan nalaz u dokumentaciji) |
| Testovi | 5 novih Python fajlova, 2 frontend testa, fixture, `osb003_solo_server.py` (blok uz `VX_AGENTI=1`) |

## 3. Tačno dokazane sposobnosti

| Sposobnost | Nivo |
|---|---|
| OCR skenirane srpske ćirilice, i u mešovitom PDF-u, kroz stvaran worker do teksta dokumenta predmeta | ISOLATED u **produkcionoj Docker slici** (32/32) |
| Predmet sa više dokumenata: identiteti, tvrdnje po izvoru, protivrečnost, hronologija sa izvorom, rok → potvrda → akcija, pitanje, istorija | ISOLATED (stvarne rute) |
| Obrisan izvor više nije merodavan | ISOLATED + mutacije |
| Podsetnik samo za potvrđen rok; dva roka istog dana; predmet u brisanju | ISOLATED (stvarna kapija potvrde) |
| Paralelni savetnici sa istim ugovorom kao pojedinačni | ISOLATED + mutacije |
| U V2: jedan savetnik i tri pogleda; niz je isključen i ne šalje zahtev | BROWSER_INTEGRATION nad pravim `api.app` (16/16) i fixture-om (38/38) |
| Brisanje dokumenta: nema uspeha dok AI tvrdnje ostaju aktivne; pad, greška i ponovni pokušaj | ISOLATED (ruta) + **pravi PostgreSQL 17** (migracija 137) + mutacije 7/7 |
| Pravno pitanje: poreklo svake tvrdnje, SPORNO iz trajnih V2 protivrečnosti, bez „utvrđeno“ | ISOLATED (tačan tekst ka modelu) + mutacije 7/7 |
| Autonomija NS007 | ISOLATED nad **stvarnim PostgreSQL-om** (163/163) |

## 4. Tačna nerazrešena ograničenja

- **`LIM-T01`:** nijedan prijavljen tok nije posmatran u produkciji (nema QA naloga).
- **`LIM-T02-1`:** posle neočekivane greške baze tokom prikačivanja, ponovni pokušaj oko 120 s dobija 409 „u toku… za par sekundi“. Integritet je očuvan, a poruka je netačna u trajanju.
- **`LIM-T06-1` → zatvoreno isključenjem (RC FIX 2):**
  - niz savetnika nije dostupan u V2;
  - backend ruta postoji, ali je niko ne poziva;
  - ponovno uključenje traži trajnu evidenciju koraka (nova šema, posebno odobrenje).
  - Isti pad u **jednom** i **paralelnom** savetniku moguć je samo u milisekundama između naplate i upisa odgovora. Kod niza su to minuti, pa ovo ostaje imenovano ograničenje.
- **`OBS-T03-1` → ispravljeno (RC FIX 3).**
- **`LIM-RC-1` (pre migracije 137):**
  - Pad radnika tačno između povlačenja AI tvrdnji i brisanja reda ostavlja dokument u listi bez njegovih AI tvrdnji. Vektori su već uklonjeni, a uspeh nije prijavljen.
  - Ponovni pokušaj završava brisanje.
  - Migracija 137 zatvara ovaj prozor.
- **`OBS-T03-2`:** rok iz obrisanog dokumenta ostaje u hronologiji kao istorija bez izvora, ali **nepotvrđen**, pa nikad nije operativan.
- **`LIM-T03-3`:** sačuvan Genome (`case_dna.kontradikcije`) može do sledećeg osvežavanja da navodi protivrečnost čija je tvrdnja povučena brisanjem dokumenta. Sledeće osvežavanje je ne vidi (dokazano).
- **Podsetnici i SMS:** isporuka nije posmatrana (tajna). SMS ruta prima samo osnivačev JWT.
- `FLAKY-DEMO-PIKSEL` (nasleđeno, prag nije menjan).

## 5. Knjiga zadataka

`VCR002_TASK_LEDGER.md` (T00–T10) · `VCR002_MASTER_STATE.md` · `VCR002_REQUIREMENTS_STATE.md` · `VCR002_T09_AUTONOMY_ACTIVATION.md` · `VCR002_TEST_EVIDENCE.md`.

## 6. CI na kandidatu (poređenje identiteta palih testova sa `main` `b36235a3`)

**Zatvaranje izdanja — kandidat `056a48e6`:**

| Workflow | Rezultat | Padovi | Novo u odnosu na `main` |
|---|---|---|---|
| Security Checks (38249352222) | **success** | — | — |
| Test Suite 3.11 / 3.13 (38249352253) | failure (nasleđeno) | 174 / 174 (8787 passed) | **0** |
| Production Runtime Parity (38249352357) | failure (nasleđeno) | 196 | **0** |
| ↳ Docker build + boot; OCR u produkcionoj slici | **success**; OCR 32 passed | — | — |
| V2 NG (38249372047) | **success** posle ponovnog pokretanja jednog posla | prvi pokušaj: `verify:live-matrix` → `demo-piksel`. Snimak HEAD naspram HEAD-a razlikovao se za 15 piksela po jednu nijansu. To je nasleđeni `FLAKY-DEMO-PIKSEL`; prag nije menjan. | — |

**Prethodno, kandidat `38ac5fcd` (`53d7d60a`):**

| Workflow | Rezultat | Padovi | Novo u odnosu na `main` |
|---|---|---|---|
| Security Checks (38226846712) | **success** | — | — |
| Test Suite 3.11 / 3.13 (38226846654) | failure (nasleđeno) | 174 / 174 (8766 passed) | **0** |
| Production Runtime Parity (38226846662) | failure (nasleđeno) | pun paket 196 | **0** |
| ↳ Byte-compile; Docker build + boot; OCR u produkcionoj slici | **success**; OCR 32 passed | — | — |
| V2 NG (38226842140) | **success** | — | — |

- **Međukorak `aabbff26`** je otkrio jednu pravu regresiju i jedan bezbednosni signal; oba su zatvorena u `38ac5fcd`:
  - **Regresija** `test_p1_charge_on_failure.py::test_multi_agent_charges_only_for_agents_that_succeeded`: zakucan izvorni uslov `not r.get("greska")` je vraćen uz `stanje`. Ponašanje je isto. Lekcija iz VCR001 o punom paketu pre zatvaranja nije bila primenjena u T05.
  - **Gitleaks** lažno pozitivan nalaz u dokumentaciji.
- **Lokalno, pun Python paket na `38ac5fcd`:** kandidat 21 failed, 9296 passed; osnovica (`main`-ovo stablo) 22 failed, 9231 passed. Jedine razlike su Playwright testovi starog V1 UI-ja, koji kandidat ne dira. Pokrenuti sami prolaze 15/15 (paralelno opterećenje). **0 novih.**

## 7. Frontend (lokalno, sve `verify*` + `e2e:*` skripte)

**Zatvaranje izdanja, `056a48e6`:** **45/45 PASS**, uključujući `verify:live-agenti` 38/38 i `e2e:savetnici` 16/16 (niz isključen).

Prethodno:

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

Nijedna nova kolona ni tabela. **Jedna nova RPC funkcija u migraciji 137** (`invalidate_dokument_and_ai_claims_and_emit_event`, novo ime, stara funkcija netaknuta). Aplikacija radi i pre i posle njene primene.
- Koriste se postojeće tabele i kolone: `predmet_dokazi.deleted_at` / `izvor_tvrdnje` / `nacin_pronalaska`, `predmeti.brisanje_zapoceto` i `v2_mutation_idempotency`.
- `brisanje_zapoceto` ima rezervni upit ako kolona ne postoji.

## 12. Zahtevi za migracije

- **Migracija 137** (`migrations/137_atomic_dokument_ai_claims_invalidation.sql`):
  - preporučena **posle** spajanja, a pokrećete je vi;
  - zavisi od 016, 073, 117 i 135, koje su sve već u produkciji;
  - bez nje važi put sa kompenzacijom i `LIM-RC-1`;
  - testirana samo nad izolovanim lokalnim PostgreSQL-om 17, ne na produkciji.
- Migracija 136 (autonomija) je zasebna odluka (T09).

## 13. Spoljne zavisnosti

- GitHub Actions (planirani poslovi se izvršavaju sa `main`-a, pa ispravka SMS posla deluje tek posle spajanja);
- Render (`CRON_SECRET`, SMTP);
- OpenAI / Pinecone (nepromenjeno).

## 14. Ograničenja vraćanja

Vraćanje na `b36235a3` je čisto: nema šeme ni podataka koje kandidat jedini razume. Posle vraćanja nestaju ispravke i V2 načini rada. Meko povučene tvrdnje (`deleted_at`) ostaju povučene.

## 15. Odluke osnivača

1. **Puštanje kandidata `056a48e6`** (spajanje PR #20 → automatski deploy). Odobrenje važi samo za tačno taj kandidat.
1a. **Migracija 137** (posle spajanja; zatvara `LIM-RC-1`).
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
9. ~~`OBS-T03-1`~~ — ispravljeno u RC FIX 3. **Novo:** da li i kada graditi trajnu evidenciju koraka niza savetnika (nova šema), kako bi se niz u V2 ponovo uključio.

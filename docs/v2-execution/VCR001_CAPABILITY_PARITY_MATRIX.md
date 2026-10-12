# VCR001 — matrica sposobnosti V1 ↔ V2 (Task 00)

Osnova: `main` = produkcija `6ad0b13a` (`/health`, 2026-10-11).

**Kako je izmereno (P):**
- Statički inventar API poziva: V2 (`frontend-v2-ng/src`, 37 ruta iz 15 modula) i stari UI (`static/vindex.js`, 226 ruta).
- Registar funkcija (`migrations/064`).
- `shared/permissions.py`.

**Prava pristupa (P):** osnivač prolazi tarifne provere (`minimum_plan`/addon). Blokiraju ga samo prekidač za gašenje funkcije i neispravna zavisnost. Za osnivača, dakle, „vidi malo“ znači **da V2 nema ulaz**, a ne da mu je pristup ograničen. Običan korisnik na tarifi `basic` dobija 403 za `professional` funkcije; to je ugovor, ne kvar.

**Živi status:** prijavljena produkcija **nije** proverena (nema test naloga), pa „LIVE“ znači javno dostupno i CI/E2E na istom kodu.

Legenda statusa: `V2` = ALREADY_WORKING_V2 · `LEG` = WORKING_LEGACY_ONLY · `UI` = BACKEND_READY_UI_MISSING · `BRK` = BROKEN_INTEGRATION · `PRQ` = MISSING_PRODUCTION_PREREQUISITE · `OFF` = INTENTIONALLY_DISABLED · `UNS` = UNSUPPORTED_REQUIREMENT

| Funkcija | V1 ulaz | Backend vlasnik | V2 ulaz | Pravo pristupa | Status | Potreban rad |
|---|---|---|---|---|---|---|
| Predmeti (CRUD, lista, detalj) | `/app-legacy` | `routers/predmeti.py` | Predmeti, Nov predmet | `predmeti_crud` basic | V2 | — |
| Klijenti: kreiranje, povezivanje sa predmetom | CRM | `klijenti/router.py`, `/api/predmeti/{id}/confirm-links` | `klijenti-predmeta.js` | basic | V2 | — |
| Prijem „dokument prvo“: prikačiti postojećem predmetu | Smart Intake | `routers/smart_intake.py` | kartica „Prijem dokumenata“ | basic | V2 | T01 (OCR dokaz) |
| Prijem „dokument prvo“: **nov predmet iz dokumenta** | čarobnjak `vindex.js:22355` | `finalize` bez `predmet_id` | — | basic | UI | **T02** |
| Prijem „**problem prvo**“ (opis → predlog → predmet + klijent) | čarobnjak (`/api/intake/ekstrakcija`, `/kreiraj`) | `routers/intake.py` | — | `intake_ai` professional | UI | **T02** |
| Šabloni predmeta (7 tipova sa hronologijom) | `/api/intake/from-template` | `routers/intake.py` | — | basic | LEG — **namerno nije izložen u V2** | T07: šablon upisuje hronologiju sa IZMIŠLJENIM datumima (danas + pomak, „Template (AI)“) — nisu činjenice predmeta; defekt `TPL-DATUMI`, odluka osnivača |
| OCR (sken PDF, JPG/PNG, srp ćirilica i latinica) | upload | `uploaded_doc/extractor.py`, `shared/intake_worker.py` | Prijem dokumenata | basic | V2 kod; produkcija **0 izvršenja** (A018 B3) | **T01** |
| `.doc` (stari Word) | upload | extractor nema handler | — | — | UNS → mora jasna greška | T01 |
| Dokazi (Evidence Vault): pregled + ručni unos | Dokazi | `routers/evidence.py`, `genome-v2` | Analiza („Dodaj tvrdnju“) | `evidence` professional | **V2** (T07, `fa5ac520`) | — (bez snage: nema lažne procene advokata) |
| Case Genome / Living Matter | Genome | `routers/case_dna.py` | Analiza, Pregled | `case_dna` professional | V2 (T04: ulazi = dokumenti + činjenice, potvrđeno) | — |
| Case Actions | — | `routers/case_actions.py` | Pregled (živi pregled) | — | V2 | T03 |
| Hronologija i beleške | predmet | `/api/predmeti/{id}` | Rad na predmetu | basic | V2 | T03 (izvor kao `dokument_id`, A018 B8) |
| Rokovi (kandidati, potvrda) i ročišta | kalendar | `routers/rokovi*.py`, `/api/rocista` | Danas, ročišta | `rokovi` basic | V2 | T03 |
| Podsetnici (email) | `/email-notif` | `routers/email_notif.py` + spoljni cron | — | — | PRQ — BLK-3 (workflow „Email Podsetnici“ pada; A018 B10 🔴) | odluka osnivača / produkcioni preduslov (T07: nije menjano) |
| Pravno pitanje (RAG, čuvar citata) | Pitanje | `main.py`, `/api/pitanje` | Pravno pitanje | `ai_pravna_pitanja` basic | V2 (T04, `f995f709`: pretraga zna za trenutni predmet; stanje konteksta) | — |
| Law Brain (znanje, pretraga) | — | `routers/law_brain*.py` | Znanje, Law Brain | `firm_memory` professional | V2 | — |
| Sudska praksa, interni stavovi | Praksa | `routers/praksa*`, `interni_stavovi` | Znanje | basic / professional | V2 | — |
| Nacrti podnesaka + staging + DOCX | Nacrti | `routers/drafting.py`, `/api/staging`, `/api/nacrti/export/docx` | Nacrt podneska | `drafting` professional | V2 (T05, `5fc726ea`: otvori / sačuvaj / odobri sačuvan tekst) | — |
| **Multi-agent** (6 agenata: run / parallel / pipeline) | Tim savetnika | `routers/multi_agent.py` | Pravno pitanje → „Savetnik za ovaj predmet“ | `multi_agent` professional | **V2** za `run` (T06, `53de12de`/`fa5ac520`): čuvar citata, granica poverenja | `run-parallel`/`pipeline` nisu izloženi (isti čuvar treba dodati pre izlaganja) |
| Strategija, Red Team, AI Judge | Strategija | `routers/strategija*.py` | — (delimično: savetnik „Parnična strategija“, T06) | `strategija` professional | LEG | odluka osnivača: granica AI-pomaže/AI-odlučuje (Product Philosophy DRAFT) |
| Court predictor | Prediktor | `routers/court_predictor.py` | — | professional | LEG — **namerno nije izložen u V2** | model generiše `procenat_min/max` šanse za uspeh — protivno Deterministic Intelligence Framework-u; odluka osnivača |
| Zastarelost | Zastarelost | `routers/zastarelost.py` | Rad → „Zastarelost potraživanja“ | javna ruta (bez prijave; deterministička, bez podataka) | **V2** (T07, `fa5ac520`) | — (prekid/zastoj se ne računaju — izričito rečeno) |
| Zadaci | Zadaci | `routers/zadaci.py` | Rad → „Zadaci“ + Radna lista | basic / `zadaci_ai` | **V2** (T07, `3dc32630`): dodaj/rok/prioritet/završeno | AI predlog zadataka (`ai-analiziraj`) nije izložen |
| Pretraga dokumenata | Pretraga | `/api/search` | Pretraga | basic | V2 | — |
| Naplata (tajmer, AKS tarifa, fakture) | Finansije | `routers/billing*.py` | Naplata | `finansije` basic | V2 | — |
| COI | čarobnjak | `routers/intake.py`, `routers/conflict_check.py` | Klijenti predmeta | `conflict_check` professional | V2 | — |
| Kancelarija (tim, delegacija) | Tim | `routers/kancelarija*.py`, `enterprise` | Kancelarija (pregled) | enterprise | V2 (čitanje) / LEG (upravljanje) | očuvati; beta je solo |
| Autonomija A2/A3 (NS007) | — | `routers/autonomy.py`, `services/autonomy.py` | Pripremljeno (isključeno) | — | OFF (nema 136, nema Cron-a) | T08 (odluka) |
| Copilot, glas, Client Twin, portal klijenta, web3, admin | razno | razno | — | professional / interno | LEG / OFF | van bete; očuvati |

## Radna lista za T01–T09 (bez duplikata)
1. **T01:** OCR kroz stvaran tok prijema (worker) u produkcionoj slici; ponašanje za `.doc`, slike i mešovite PDF-ove.
2. **T02:** V2 čarobnjak: (a) „problem prvo“ preko postojećih `/api/intake/ekstrakcija` i `/kreiraj`; (b) nov predmet iz dokumenta preko postojećeg `finalize`.
3. **T03:** hronologija i rokovi iz dokumenata sa identitetom izvora; nesigurni rokovi ostaju predlozi.
4. **T04:** potvrditi da se kontekst predmeta stvarno koristi u pitanju i Genome-u.
5. **T05:** trajni, ponovo otvorljiv radni proizvod (nacrt) uz ljudsko odobrenje.
6. **T06:** V2 ulaz za postojeće agente, kroz čuvar citata.
7. **T07:** šabloni, zadaci, strategija, zastarelost, prediktor, podsetnici, ručni unos dokaza; svaki dobija status iz matrice.
8. **T08:** autonomija: izolovano; aktivacija BLOCKED_AUTHORITY.
9. **T09:** zatvaranje Bojan B1–B13; Miroslav: izvor zahteva nije dostupan.

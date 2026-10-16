# Vindex AI — Overnight Beta Hardening Sprint (2026-10-15/16)

**Grana:** `beta/overnight-source-integrity-2026-10-15` · **Baza:** `main` = `649583c7` · **Draft PR:** Draft PR (ova grana → `main`)
**Oznake dokaza:** **PROVEN** = kod, test ili izvršenje · **INFERRED** = obrazloženo, nije izvršeno · **UNKNOWN** = nema dokaza.
Svi testovi koriste sintetičke podatke. Model (OpenAI) je u svim testovima **zamenjen (mock)**. Ponašanje stvarnog modela nije provereno ni u jednom zadatku.

## A. Stanje

| Stavka | Vrednost | Dokaz |
|---|---|---|
| Početni `main` | `649583c783125991d83b8935a51924c76ff95dc3` (Merge PR #35) | `git rev-parse origin/main` |
| Produkcija na početku | isti SHA, `identity_proven: true`, start 2026-10-15T21:50:17Z | `GET https://vindex.rs/api/version` |
| #40, #36, #35 u istoriji `main` | DA: `74202135`, `b0013c79`, `649583c7` | `git log` |
| PR #38 | Draft, `50cf7988`, nepromenjen | GitHub API |
| Paralelni agenti / necommitovane izmene | nema drugih sesija; nova grana iz svežeg `origin/main`, čisto radno stablo | `ListAgents`, `git status` |
| CANONICAL OPERATING RULES | **nisu pronađeni** u radnom okruženju; nisu čitani | — |
| Završni `main` | `649583c783125991d83b8935a51924c76ff95dc3`, nepromenjen | `git rev-parse origin/main` |
| Merge / deploy / migracija / upis u produkciju / Render | **nijedan** | — |

Commit-i na grani:

| Commit | Zadatak | Sadržaj |
|---|---|---|
| `5fe3dc40` | TASK 01 | naziv fajla nedostavljenog dokumenta u odgovoru se označava |
| `f17ecd28` | TASK 02 | Case Genome u granici poverenja; deklaracija granice u system poruci savetnika |
| `5d2e8065` | TASK 03 | regresioni čuvari (Playwright + Python) |
| `f7e0c687` | TASK 01/02 | jedna uska korekcija posle nezavisnog pregleda (F1, F6) |
| commit izveštaja | TASK 05 | ovaj izveštaj |

## B. Rezultati po zadacima

### TASK 01 — QA-06: naziv fajla nedostavljenog dokumenta → `GO_FOR_FOUNDER_REVIEW`

- **Početni dokaz (PROVEN):** `routers/multi_agent.py::_pominje_nedostavljene` je na `649583c7` prepoznavao samo oznake DOK-NN.
- **Reprodukcija:** sintetički predmet sa 7 dokumenata; model dobija 5, a DOK-02 i DOK-01 su izostavljeni. Novi test-fajl `tests/test_qa06_naziv_nedostavljenog.py` je na `649583c7` dao **8 padova i 13 prolaza**:
  - pali su svi slučajevi pominjanja **tačnim nazivom fajla** (B), u `/run`, `/run-parallel` i `/pipeline`;
  - A (oznaka), C (sličan prefiks), D (dostavljen dokument) i E (naziv iz tuđeg predmeta) već su prolazili.
- **Implementacija:**
  - Tačan naziv fajla iz spiska **ovog** predmeta prevodi se u „DOK-NN (naziv)“. Spisak čine metapodaci koje je `_kontekst_predmeta` već pročitao, pa nema novog upita.
  - Nema delimičnog poklapanja: duži poznat naziv zauzima mesto kraćem, naziv koji je i dostavljen i nedostavljen se preskače, a nazivi kraći od 5 znakova se ne porede.
  - Pun spisak naziva je interno polje `_nazivi`. `_javni_izvori` ga skida iz svakog API odgovora.
  - Odgovor modela se ne menja.
- **Testovi:** 24 nova (uključujući nesaglasnost iz TASK 03 i F1 iz pregleda), QA-08 43/43. **Mutacije: 8/8 uhvaćeno** (7 + F1).
- **Kriterijumi:**

  | | |
  |---|---|
  | A1 | oznaka → upozorenje |
  | A2 | tačan naziv → upozorenje |
  | A3 | dostavljen → bez upozorenja |
  | A4 | sličan naziv → bez poklapanja |
  | A5 | tuđ predmet: bez upozorenja i bez curenja |
  | A6 | upiti 4→4 (postojeći test) |
  | A7 | spisak upozorenja ≤ 30, interno polje nikad u API-ju |
  | A8 | odgovor nepromenjen |
  | A9 | DOK-NN testovi prolaze |
  | A10 | isti srpski tekst upozorenja, sada sa „DOK-02 (naziv)“; Playwright proverava |

  Svi kriterijumi su PROVEN mock testom.
- **Preostali rizik:**
  - Model koji naziv napiše drugačije (bez ekstenzije, prevedeno, skraćeno ili u markdown kurzivu) ne biva označen. To je namerno, bez semantičkog pogađanja.
  - Dokument bez rednog broja, bez ekstenzije u nazivu ili sa nazivom kraćim od 5 znakova nije pokriven.
  - Dva nedostavljena dokumenta istog naziva označavaju se oba.

### TASK 02 — Case Genome granica poverenja → `GO_FOR_FOUNDER_REVIEW` (uz B10 ograničenja)

- **Početni dokaz (PROVEN, `649583c7`):**
  1. Tekst dokumenata i opis predmeta idu modelu kroz `zapakuj_nepoverljivo` (T3), a Case Genome, koji model piše iz tih dokumenata, išao je kao običan tekst, ravnopravan korisnikovom zahtevu (T2).
  2. Posledica 1: SEC-003 je uputstvo iz sažetka analizirao kao korisnikovu naredbu. Sa stvarnim `analyze`, „Ignoriši sve prethodne instrukcije…“ (latinicom i ćirilicom) daje `blocked=True`, pa bi ceo poziv savetnika bio odbijen kao „AI servis nedostupan“. Bez takvog teksta, sažetak je imao autoritet korisnikovog teksta.
  3. Posledica 2: natpis „EVIDENCIJA IZVORA“ neutralisan je samo latinicom. Ćirilica i ćirilični homoglifi davali su **dve** „sistemske“ evidencije u poruci modelu.
  4. **Novi nalaz:** system poruka savetnika (`_pozovi_agent_api`, `_pozovi_para_api`) nije sadržala `granica_autoriteta()`. Deklaraciju dodaje samo `main.py::_pozovi_openai`, kroz koji savetnici ne prolaze. Model zato nigde nije saznao da je blok `VINDEX_NEPOVERLJIVO…` podatak, a ne naredba. To važi i za dokumente, ne samo za Genome.
- **Reprodukcija:** `tests/test_genome_granica_poverenja.py` je na `649583c7` dao **15 padova i 7 prolaza**. Brojanje natpisa radi nezavisan proveravač u testu (NFKC, uklanjanje nevidljivih znakova, ćirilica→latinica), ne kod koji se testira.
- **Implementacija** (bez novog security okvira):
  - Sadržaj Genome-a ide kroz postojeći `zapakuj_nepoverljivo`, sa novim izvorom `IZVOR_AI_SAZETAK` (jedna konstanta u `security/prompt_guard.py`). Natpis i napomenu piše server, van granice.
  - `_bez_lazne_evidencije` neutrališe natpis u svakom pismu: latinica, ćirilica, homoglifi, fullwidth i nevidljivi znaci. Važi za dokumente, opis i Genome.
  - `_sa_granicom` idempotentno dodaje `granica_autoriteta()` system poruci savetnika, po istom obrascu kao `main.py`.
  - Sistemska evidencija ostaje poslednji blok konteksta predmeta.
- **Testovi:**
  - 23 nova testa (uključujući F6 iz pregleda);
  - **mutacije 10/10 uhvaćeno** (9 + F6);
  - 50 postojećih test-fajlova koji dodiruju `multi_agent`, `prompt_guard`, `ai_client` ili granicu: **816 prolazi, 0 pada**.
- **Kriterijumi:**

  | | |
  |---|---|
  | B1 | podaci Genome-a i dalje u poruci |
  | B2 | Genome je registrovan T3 |
  | B3 | lažni natpis u 6 varijanti neutralisan; evidencija `izvori_predmeta` identična sa i bez lažne tvrdnje u sažetku; odgovor koji ponovi tvrdnju sažetka označen |
  | B4 | 4 oblika lažnog zatvaranja granice ostaju unutar T3 |
  | B5 | autorizacija nije dirana |
  | B6 | izvori i dokumenti identični sa i bez Genome-a |
  | B7 | omotač Genome-a +147 znakova (samo kad Genome postoji); deklaracija u system poruci +615 znakova (≈150–200 tokena) po pozivu savetnika |
  | B8 | 816/0 |

  B9: nezavisni pregled je niže. B10: ograničenja su odmah ispod.
- **Šta mock test NE dokazuje (B10):**
  - da stvarni model neće izvršiti instrukciju iz T3 bloka; granica je deklaracija modelu, ne tehnička nemogućnost;
  - da je Genome tačan;
  - ponašanje 16 drugih modula koji čitaju `case_dna` i pozivaju AI (`api.py`, `routers/copilot.py`, `routers/strategy_simulator.py`, `services/legal_reasoning_engine.py` i dr.). Oni nisu revidirani.
- **Napomena o ponašanju:** uputstvo u sažetku više **ne obara** poziv savetnika (T3 se beleži kao izolovan pokušaj, ne blokira). Ovo je isti ugovor koji već važi za dokumente (TARGET-2). Uputstvo u **korisnikovom** zahtevu se i dalje blokira (test `test_B2_korisnikovo_uputstvo_se_i_dalje_blokira`).

### Nezavisni adversarial pregled (TASK 01 + TASK 02, B9)

Reviewer je bio zaseban agent sa zasebnim worktree-jem (`f17ecd28`). Dobio je tačan diff i zadatak da sruši izmenu. Napisao je 36 sopstvenih proba.

- **Verdikt: GO WITH NOTES.** Jedan nalaz je MATERIAL, ostali su napomene.
- **Šta nije uspeo da obori:**
  - Sa **pravim** SEC-003 guard-om (zamenjen je samo provajder, ne `_pozovi_agent_api`), Genome sa ubačenim uputstvom prolazi kao T3 u `/run`, `/run-parallel` i `/pipeline`. Granica registrovana u `_kontekst_predmeta` vidljiva je i u `to_thread`, `gather` i koracima niza.
  - System poruka nosi deklaraciju tačno jednom.
  - Korisnikovo uputstvo (T2) se i dalje blokira: `/run` vraća 503 bez poziva modela, `/run-parallel` 3× NEUSPEH.
  - `_nazivi` ne izlazi ni u jednom odgovoru, ni pri idempotentnom ponavljanju niza.
  - Unicode, NFD i specijalni znaci u nazivima rade.
  - Izolacija korisnika važi.
- **F1 (MATERIAL), ispravljeno u `f7e0c687`:** naziv bez ekstenzije („dokument“, rezervni naziv pri prijemu u `api.py` i `smart_intake.py`, ili „Tužba“) pogađao je običnu rečenicu, pa je davao lažno upozorenje. Sada se poredi samo naziv sa ekstenzijom fajla. Negativni testovi su dodati, mutacija je uhvaćena.
- **F6, ispravljeno u `f7e0c687`:** verzija Genome-a je u natpisu van granice; sada prolazi samo ceo broj. Test je dodat, mutacija uhvaćena.
- **Napomene (dug, nije ispravljano):**
  - F2: tačan naziv u markdown kurzivu (`_ime.pdf_`) se ne prepoznaje; ne prepoznaje se ni naziv bez dijakritika, sa razmakom umesto `_` ili transliterisan.
  - F3: `arhiva/ugovor.pdf` se prepoznaje kao `ugovor.pdf`.
  - F4: neutralizator natpisa ne hvata grčke i matematičke homoglife, `EVIDENCIJA-IZVORA`/`_`/`:`, tačke između slova, kombinovane akcente ni U+180E/U+2062/U+2063. Rizik je nizak jer je sadržaj ionako u T3; da li bi stvarni model bio zaveden, nije provereno.
  - F5: legitiman ćirilični tekst „евиденција извора …“ sada se prepisuje u „evidencija-izvora (navod)“. Isti kompromis kao za latinicu iz #40 je sada proširen na ćirilicu, uz malo odstupanje od pravila B4-M2 o doslovnom tekstu.
  - F7: najgori slučaj prepoznavanja naziva je 0,25–0,47 s (1.000 naziva i odgovor od oko 18 hiljada znakova), na event loop-u, po savetniku.
  - F8: rast konteksta je objašnjen (B7).
  - F9 (postojeće stanje, nije novo): fajl nazvan `DOK-03.pdf` aktivira oznaku DOK-03.
- **Otkrivanje (reviewer):** pri prvoj probi P15 guard još nije bio instaliran, pa je jedan zahtev verovatno otišao na `api.openai.com` sa lažnim ključem `sk-test-dummy`, koji je morao biti odbijen. Nije poslat nikakav predmetni podatak (sintetički test). Posle toga reviewer je koristio samo stub. Nije bilo poziva ka produkciji, bazi ni vindex.rs, a nije bilo ni commita ni push-a.
- Posle korekcije: ciljani testovi 90/90, 50 povezanih fajlova 817/0, sve mutacije 18/18, `live-savetnici-e2e` 16/16.

### TASK 03 — Regresioni čuvari → `CLOSED_WITH_EVIDENCE`

| Oblast | Postojeće pokriće (prolazi) | Nov test (samo konkretna rupa) |
|---|---|---|
| QA-08: 1/7/12 dokumenata, najstariji tražen, ne postoji, bez teksta, greška metapodataka, greška teksta, paralelno, isti naziv kod dva korisnika | `test_qa08_izvori_savetnika.py` 43/43 | — |
| QA-08: server dostavio DOK-01, model tvrdi da ga nije pročitao | nije postojalo | Python `test_nesaglasnost_*` + Playwright `Q.nesaglasnost`. Evidencija ostaje serverova, nema lažnog upozorenja, oba podatka su vidljiva. Rečenicu modela sistem **ne tumači**; to je poznato ograničenje, bez krhkog regex-a. |
| QA-06 u V2: upozorenje po nazivu, naziv kao tekst (XSS) | nije postojalo | Playwright `Q.pominje` (naziv) |
| QA-03: `contract`/`response`/`law_cited`/`Case Evolution Engine`, stari zapisi, bez rečnika | `live-nazivi-e2e` | — |
| QA-03: sačuvan `podnesak` sa nazivom „Odgovor na tuzbu…“ | nije postojalo | `live-nazivi-e2e`: ostaje „Podnesak“ |
| QA-C: dva korisnika, vraćanje konteksta, neuspeh handlera, retry, bez identiteta, nekanonski identitet, `correlation_id`, tenant | `test_qa_c_dispatch_provenance_identity.py` **31/31**, svih 8 scenarija | — (ne dupliram) |

- Playwright: `live-agenti` **52/52** (ranije 50, +2), `live-nazivi-e2e` **54/54** (pravi `api.app`, stari zapisi), `live-savetnici-e2e` **16/16** (pravi `api.app`, i posle korekcije).
- Ceo Python paket: 19 padova na `main` i na grani, **identičan skup**; grana +44 prolaza (sekcija D).

### TASK 04 — QA-C produkciona forenzička provera → **NOT YET VERIFIED** (`PARTIAL_WITH_EXPLICIT_HOLDS`)

- **D1 PROVEN:** produkcija = `649583c7` (`/api/version`, `identity_proven: true`), start 2026-10-15T21:50:17Z.
- **D2, delimično:**
  - `governance.active=true`, `ai_blocked=false`;
  - `/health`: `status ok`, `redis true`, `workers 1`, jedan proces (`pid 23` u 5 uzastopnih poziva);
  - stanje pozadinskog dispečera **nije javno izloženo**, pa je UNKNOWN.
- **D3/D4 NOT YET VERIFIED:**
  - nema read-only pristupa bazi ni Render logovima (`SUPABASE_DB_URL`, `DATABASE_URL`, `RENDER_API_KEY` nisu postavljeni) i nisam tražio zaobilazne puteve;
  - `/health.provenance.prosirena_sema = null` u tom procesu znači da od starta (≈32 min pre provere, 22:22Z) **nije pokušan nijedan upis AI provenance zapisa**. To je INFERRED, uz uslov da nema drugih instanci;
  - prirodan pozadinski AI događaj posle deploya zato nije potvrđen.
- **D6:** #35 rešava pripisivanje identiteta; ne garantuje trajnu isporuku svakog forenzičkog zapisa (upis je fire-and-forget, `shared/bg.spawn`).
- **Procedura za kasniju proveru** (osnivač ili ovlašćena osoba, read-only uloga, samo agregati, bez teksta):

```sql
BEGIN READ ONLY;
-- R1: pozadinski događaji posle deploya
SELECT event_type, (dispatched_at IS NOT NULL) AS isporucen, (last_error IS NOT NULL) AS greska, count(*)
FROM public.events WHERE created_at >= '2026-10-15T21:50:17Z' GROUP BY 1, 2, 3;
-- R2: forenzički zapisi posle deploya — samo brojevi
SELECT count(*) AS ukupno, count(user_id) AS sa_korisnikom, count(correlation_id) AS sa_korelacijom, count(tenant_id) AS sa_tenantom
FROM public.ai_forensics WHERE created_at >= '2026-10-15T21:50:17Z';
-- R3: ukrštanje identiteta — forenzički korisnik ≠ vlasnik događaja iste korelacije
SELECT count(*) FILTER (WHERE f.user_id = e.user_id) AS poklapa,
       count(*) FILTER (WHERE f.user_id IS DISTINCT FROM e.user_id) AS ne_poklapa
FROM public.ai_forensics f JOIN public.events e ON f.correlation_id = e.correlation_id
WHERE f.created_at >= '2026-10-15T21:50:17Z' AND e.created_at >= '2026-10-15T21:50:17Z';
ROLLBACK;
```

  Nazivi kolona su uzeti iz koda (`services/event_bus.py`, `security/ai_forensics.py`), ne iz baze; pre pokretanja ih treba potvrditi. Očekivano posle #35: R3 `ne_poklapa = 0`, a R2 `sa_korisnikom` jednako broju zapisa iz dispečera. Ako je R1 prazan, rezultat ostaje NOT YET VERIFIED, ne PASS.

### TASK 05 — Paket odluka → `HOLD_REQUIRES_FOUNDER_DECISION` (odluke), dokumentacija gotova

Sekcija F i `docs/release/QA01_DEADLINE_DECISION_PACKAGE.md` (Draft PR #41). Nijedna opcija nije izabrana ni implementirana.

**QA-01: pet odluka** (dokazi u QA-01 paketu, `main` `ed0662be`; od tada nema izmena u tim fajlovima):

| # | Trenutno ponašanje (PROVEN) | Rizik | Najmanja opcija | Alternativa | Ako se odloži | Migracija |
|---|---|---|---|---|---|---|
| 1. Kategorije datuma | Jedna `vrsta='rok'` za događaj, ugovornu obavezu, procesni rok i internu radnju | izvršena radnja prikazana kao obaveza | prikaz na osnovu postojećih polja (`vrsta`, `datum`), bez nove kolone | kolona `kategorija` (4 vrednosti) | lažna hitnost ostaje; beta testeri moraju znati da je „rok“ predlog | alternativa DA, najmanja NE |
| 2. Ko sme „kritičan“ | Genome uvek upisuje `kritičan` u kodu; Rule 6 daje `critical` za ≤3 dana | sve izgleda hitno, pa se pravi rok gubi u šumu | Genome upisuje `važan`; „kritičan“ samo potvrđen procesni rok | prag + potvrda advokata | šum na Radnoj listi i legacy dashboard-u | NE |
| 3. Prošli datumi | Genome bez filtera; Pipeline do 1 godine unazad; Rule 6 daje prošlom datumu `critical` | izvršen događaj postaje „kritična“ stavka | prošli datum ide samo u hronologiju kao događaj | ostaje kandidat, ali sa oznakom „prošao“ i bez prioriteta | isto kao danas; izvršive posledice su i dalje zaključane potvrdom | NE |
| 4. Ponovni nastanak odbijenog | dedup po tekstu; odbijanje čuva audit, ali drugačija formulacija pravi nov kandidat (INFERRED) | advokat isti rok odbija više puta | provera „odbijen isti datum + isti izvorni dokument“ pre upisa | trajni ključ izvora roka | ponavljanje odbijenih predloga | najmanja verovatno NE (audit postoji), alternativa DA |
| 5. Legacy prikazi | `/api/predmeti/dashboard` i `/workspace` broje samo `vaznost=="kritičan"`, bez potvrde | stari ekran prikazuje nepotvrđene AI rokove kao urgentne | uskladiti filter (`vrsta` + potvrda) | ugasiti legacy prikaz posle V2 prelaza | razlika V2 i legacy ostaje | NE |

**QA-02 / PR #38** (rezultati završnog pregleda, bez novih eksperimenata):
- Manje samouvereno pogrešnih: 69 → 16 na 215 sintetičkih zaglavlja.
- Mnogo više slanja modelu: 28 (13%) → 159 (74%). Krajnji ishod tih 159 klasifikacija **nije izmeren** (model je u testu mock).
- Pri nedostupnosti OpenAI-ja, 159 umesto 28 dokumenata dobija `other` („nepoznato“). „Nepoznato“ nije pogrešna klasifikacija, ali nije ni ispravna: dokument ostaje bez vrste dok ga neko ne klasifikuje.
- Trošak u novcu nije računat. Oko 610 dodatnih poziva na 1.000 dokumenata je INFERRED iz namerno teškog korpusa.
- **Opcije:**
  - (a) zadržati produkciju (stara heuristika);
  - (b) spojiti #38 kakav jeste;
  - (c) tražiti uži #38: samo zaglavlja sa najvećom greškom, uz mali prag za slanje modelu.

  Svaka opcija je odluka, ne tehnička činjenica.

**QA-04:** HOLD. U ovom sprintu nije reprodukovan nov deterministički defekt.

**QA-06: razdvajanje četiri pojma:**

| Pojam | Stanje posle ovog sprinta |
|---|---|
| Dostavljen izvor | PROVEN: server beleži tačno šta je dato (`izvori_predmeta`) |
| Izvor koji model **tvrdi** da koristi | delimično: označava se pominjanje nedostavljenog dokumenta po oznaci ili tačnom nazivu; tvrdnja „nisam pročitao“ za dostavljen dokument se ne tumači |
| Citirani odlomak | **ne postoji** provera da je navedeni tekst zaista u dokumentu |
| Činjenična podrška tvrdnji | **ne postoji** |

Evidencija dostavljenih dokumenata **ne dokazuje** pravnu pouzdanost odgovora.

**Spremnost** (bez automatskog prenosa GO-a između nivoa):

| Nivo | Ocena |
|---|---|
| A. Kontrolisani sintetički QA | **Spremno** uz ovaj PR (posle odluke osnivača); mock model, sintetički podaci. |
| B. Nadgledani pilot (odabrani testeri, zaštićeni podaci) | **Uslovno**: posle odluke o ovom PR-u; testere uputiti da dokumente traže oznakom DOK-NN; QA-01 rokove tretirati kao predloge. Nijedan zahtev Bojana ili Miroslava nije potvrđen u ovom sprintu, pa ih ovde ne navodim. |
| C. Stvarni poverljivi predmeti | **NIJE SPREMNO**: nema provere citiranog odlomka ni činjenične podrške; ponašanje stvarnog modela prema granici nije mereno; 16 drugih Genome potrošača nije revidirano; QA-01 i #38 čekaju odluke. |

## C. Izmenjeni fajlovi

| Fajl | Razlog | Commit | Zašto je u opsegu |
|---|---|---|---|
| `routers/multi_agent.py` | `_nazivi_nedostavljenih_u_odgovoru`, `_javni_izvori`, interno `_nazivi`; Genome u granici; natpis u svim pismima; `_sa_granicom` | `5fe3dc40`, `f17ecd28`, `f7e0c687` | samo postojeći mehanizam evidencije i postojeći `prompt_guard`; bez nove šeme, upita, agenta ili autorizacije |
| `security/prompt_guard.py` | +1 konstanta `IZVOR_AI_SAZETAK` | `f17ecd28` | postojeća lista izvora; logika granice nepromenjena |
| `tests/test_qa06_naziv_nedostavljenog.py` | nov | `5fe3dc40`, `5d2e8065` | čuvar TASK 01 |
| `tests/test_genome_granica_poverenja.py` | nov | `f17ecd28` | čuvar TASK 02 |
| `frontend-v2-ng/tests/live-agenti.mjs` | +2 scenarija | `5d2e8065` | prikaz upozorenja i nesaglasnosti |
| `frontend-v2-ng/tests/fixtures/pisanje-api.mjs` | opcioni `odgovor` u fixture-u | `5d2e8065` | samo test |
| `frontend-v2-ng/tests/live-nazivi-e2e.mjs` | +1 dokument `podnesak` | `5d2e8065` | QA-03 rupa |
| `docs/release/VINDEX_OVERNIGHT_BETA_HARDENING_REPORT.md` | ovaj izveštaj | commit izveštaja | — |

Nema migracija, promena rokova, klasifikacije, UX redizajna, `services/event_bus.py` ni frontend koda aplikacije (V2 kod nije menjan, samo testovi).

## D. Dokazi o regresiji

**Novi testovi:**

| Fajl | Broj | Na `649583c7` | Očekivani način pada |
|---|---|---|---|
| `tests/test_qa06_naziv_nedostavljenog.py` | 24 | 8 pada (naziv fajla), ostali prolaze | upozorenje izostaje ili je lažno |
| `tests/test_genome_granica_poverenja.py` | 23 | 15 pada | Genome van T3, dve „evidencije“, granica bez deklaracije |
| `live-agenti.mjs` Q.pominje (naziv) + Q.nesaglasnost | 2 | — (samo prikaz) | upozorenje bez naziva, XSS, lažno upozorenje |
| `live-nazivi-e2e.mjs` podnesak | 1 | — | naziv fajla menja vrstu |

**Mutacije:** 18/18 uhvaćeno (TASK 01: 8, TASK 02: 10). Fajl se čita i piše binarno, a posle svake mutacije vraća se originalni sadržaj.

**Ceo Python paket** (`pytest tests -p no:randomly -q`, isti alat, ista mašina, poređenje **tačnog skupa** naziva palih testova):

| | `main` `649583c7` | grana `5d2e8065` |
|---|---|---|
| Pada | 19 | 19, **identičan skup** |
| Prolazi | 10.739 | 10.783 (+44, novi testovi) |
| Novi padovi | — | **0** |

Baseline padovi (stari, nezavisni; nisu dirani ni isključeni): `test_bu001_briefing_schema_contract` (3), `test_coi_intake_convergence` (3), `test_faza1_izvor_pod` (1), `test_faza1_pristupacnost` (3), `test_ns003_protocol` (1), `test_phoenix_mission_013_infra_reliability` (1), `test_prg_night_register` (5), `test_rc_cold_start` (2). Isti skup kao na `ed0662be`.

Korekcija `f7e0c687` dira samo `routers/multi_agent.py` i dva nova test-fajla. Posle nje su ponovljeni ciljani testovi (90/90), 50 povezanih fajlova (817/0), sve mutacije i `live-savetnici-e2e` (16/16). Ceo paket **nije** ponovo pokrenut nad `f7e0c687`.

**Mock / live:** svi testovi koriste mock model. Live-model ponašanje je **UNKNOWN**; spoljni model nije pozivan namerno (nema odobrenog budžeta). Izuzetak je slučajni zahtev reviewer-a sa lažnim ključem, opisan u sekciji B.

## E. Bezbednost i poreklo

- **Dokazano (mock):**
  - Genome je T3 i SEC-003 ga tako razvrstava;
  - lažna evidencija iz sažetka u 6 pisama ne postaje serverova;
  - lažno zatvaranje granice ostaje unutar T3;
  - korisnikovo (T2) uputstvo se i dalje blokira;
  - tuđi naziv fajla ne curi i ne pravi upozorenje;
  - interna polja ne izlaze u API.
- **Promena bezbednosne granice:**
  - DA, uska: Genome je prešao iz T2 u T3, a deklaracija granice je dodata system poruci savetnika;
  - autorizacija, RLS i tenant izolacija nisu menjani.
- **Neprovereno:** ponašanje stvarnog modela; 16 drugih modula koji koriste Genome; produkcioni forenzički zapisi (TASK 04).
- **Read-only produkcija:** samo `GET /api/version` i `GET /health`. Bez upisa i bez AI poziva.

## F. Odluke za osnivača (najviše pet)

1. **Ovaj Draft PR (TASK 01 + 02 + 03):** pregledati i, ako je u redu, spojiti. Merge u `main` automatski pokreće Render deploy. Rollback: Render Rollback na `649583c7` ili revert merge commit-a. Podaci i šema se ne menjaju.
2. **Deklaracija granice u system poruci savetnika:** prihvatiti +615 znakova (≈150–200 tokena) po pozivu savetnika kao cenu zaštite. Bez nje granica postoji samo kao tekst koji model ne razume kao pravilo.
3. **QA-01 rokovi:** pet odluka iz tabele u TASK 05. Najmanji paket bez migracije čine 2, 3 i 5; kategorije (1) traže migraciju.
4. **PR #38:** (a) zadržati produkciju, (b) spojiti kakav jeste ili (c) tražiti uži #38. Pre odluke izračunati trošak po važećem OpenAI cenovniku.
5. **Produkciona forenzika (TASK 04) i QA-06 arhitektura:** odobriti read-only proveru po proceduri iz TASK 04 (potrebna je osoba sa read-only pristupom bazi); odlučiti da li se pokreće poseban projekat za proveru citiranog odlomka i činjenične podrške (QA-06).

## G. Jutarnja preporuka

- **Prvo pregledati:**
  - sekciju B, TASK 02, deo „Šta mock test NE dokazuje“;
  - diff `routers/multi_agent.py` (oko 150 linija).
- **Odobriti ako prođe:** ovaj Draft PR. Posle deploya proveriti `GET /api/version`, pa u V2 pitati savetnika za DOK-01 u sintetičkom predmetu.
- **Ostaviti na HOLD:** #38, QA-01 (do odluka), QA-04 i QA-06 arhitekturu.
- **Sledeći korak ka Bojan/Miroslav beta-validaciji:**
  - dogovoriti 2–3 stvarna, ali odobrena toka rada (na primer: pregled ugovora uz traženi DOK-NN, priprema odgovora na tužbu);
  - pratiti ih na zaštićenim pilot podacima, uz evidenciju izvora uključenu na ekranu;
  - posle prvog prirodnog pozadinskog AI događaja pokrenuti forenzičku proceduru iz TASK 04.

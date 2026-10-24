# MIR001 FINAL RELEASE R4 — integracija, odluka o puštanju, redosled i povratak

> **GATE-PUBLIC (osnivač, opcija 2):** na `origin` ide jedan zbirni commit nad `f33dcce8` (grana
> `release/mir001-clean`), ne istorija `night/miroslav-recovery`. Kod je bajt-identičan pregledanom `52e67b09`
> (`git diff 52e67b09 -- . ':(exclude)docs/v2-execution'` prazno); razlika je samo u dokumentaciji: produkcioni brojevi
> i izlazi produkcionih skripti uklonjeni, lokalne putanje zamenjene (`VINDEX_ENV_FILE`, `VINDEX_SCRATCH`, `<scratchpad>`,
> `<python>`). SHA-ovi R1–R4 i ostalih zadataka u ovim dokumentima odnose se na lokalnu istoriju (vrh `52e67b09`), koja se
> čuva nepromenjena i nije javna.

Grana `night/miroslav-recovery` (lokalno, NIJE push). **Kandidat koda: `ee33484b`** (`f33dcce8` + 52 commita; posle
njega na grani je samo commit ovog izveštaja — bez izmene koda). Produkcija = `origin/main` = `f33dcce8` (provereno
`git ls-remote`, 2026-10-24). Pušta se VRH grane (uključuje izveštaj), ne stariji commit (npr. `06987253` bi pao na QA-03).
Jedina nova migracija: `141_staging_memory_bez_direktnog_upisa.sql`. Grane `night/miroslav-recovery` i
`rollback/mir001-f33dcce8-guard` NE postoje na `origin`.

Izvršilac nije izvršio nijedan produkcioni korak (bez push-a, merge-a, deploy-a, migracije, NS007, Cron-a). Produkciji je
pristupio samo read-only skriptama (GET/HEAD, agregatni brojevi).

## 1. Pun skup testova (tačke 1–2)

Pokretanje: `python -m pytest tests -p no:randomly` (zaključan redosled), OCR okruženje (`VINDEX_REQUIRE_OCR=1`),
`OPENAI_API_KEY=sk-fake-test`, bez PostgreSQL DSN-a (PG testovi se pokreću posebno, §3). Izlazi:
`final_release/r4_pun_skup.txt` (lista padova sva tri merenja).

| merenje | rezultat |
|---|---|
| `f33dcce8` (produkcija, odvojen worktree) | 22 failed, 11.675 passed, 372 skipped, 2 xfailed |
| `81bd7684` (početak C3b FINAL CLOSURE; `t04/pun_skup.txt`) | 23 failed, 12.024 passed |
| `06987253` (R4 ispravka naplate) | 23 failed, 12.074 passed, 398 skipped, 2 xfailed |
| kandidat (`06987253` + ispravka QA-03 skenera, radna kopija) | 22 failed, 12.076 passed, 398 skipped, 2 xfailed — **skup padova identičan `f33dcce8`** |

**Razvrstavanje:**
- **22 OSNOVA** — padaju identično na produkcionom `f33dcce8` (postojeći padovi, nisu MIR001): e-pošta podsetnika (7,
  `test_alerts_email_integration`), COI/trio (3), legacy pristupačnost `test_faza1_pristupacnost` (3), zaključani heševi
  fixture-a `test_ns003_protocol` (1), kanarinac mreže `test_ns3_n01_mreza_kanarinac` (1), registracija/trio
  `test_prg_night_register` (5), cold start/commit izvor `test_rc_cold_start` (2). Ranije razvrstani kao padovi
  okruženja (`MIR001_C3B_FINAL_CLOSURE_REPORT.md` §7); ovde je presudno da su ISTI na produkciji.
- **1 REGRESIJA (test, ne proizvod) — ISPRAVLJENA:** `test_qa03_nazivi_akteri::test_svaki_interni_potpis_ima_srpski_naziv`
  (prolazi na `f33dcce8`, pada od C3b STRUCTURAL). Leksički skener potpisa `predmet_hronologija.akter` je hvatao
  `"akter": "SUD"` / `"NEPOZNAT"` iz `shared/procesno_stanje.py`, koji ključ `akter` koristi za interno pripisivanje
  događaja spisa (blok za model, snimak predloga) i nikad ne piše hronologiju. Ispravka: skener izuzima taj jedan fajl, a
  novi test `test_procesno_stanje_ne_upisuje_hronologiju` dokazuje uslov izuzetka (fajl ne piše bazu; nijedan upisivač
  hronologije ne uvozi procesno stanje). Proizvod nepromenjen.
- **0 OKRUŽENJE van osnove.**

## 2. MIR001 E2E i tok staging → usvajanje → izmena → novo odobrenje → DOCX (tačke 3–4)

V2 kroz Playwright nad pravim `api.app` (solo server, lažan samo poziv modela), posle R4 ispravke:

| E2E | rezultat |
|---|---|
| `live-c3b-usvajanje-e2e.mjs` — AI predlog → usvajanje po stavci → procesne tačke → izmena → odobrenje → DOCX → nova verzija/odbijanje → izolacija → trošak | **47/47** |
| `live-mir001-spis-e2e.mjs` — prijem Golden Case spisa kroz OCR → nacrt iz spisa | **17/17** |
| `live-nacrt.mjs` | **54/54** |
| `live-agenti.mjs` | **52/52** |
| `live-savetnici-e2e.mjs` (uklj. novi odeljak E, R4) | **21/21** |
| `live-law-brain.mjs` | **45/45** |

Pytest ugovor usvajanja (`test_mir001_c3b_usvajanje.py`, R1 testovi) i R4 naplata su u širem skupu (88 fajlova:
**1220 passed, 0 failed**) i u punom skupu.

## 3. RLS negativni testovi (tačka 5)

Izolovan PostgreSQL 17.9 (`127.0.0.1:55441`, klaster u privremenom direktorijumu; nikad produkcija):
`tests/test_mir001_r2_staging_pg.py` + `tests/test_ns005_a2_idempotency.py` → **52 passed, 0 skipped** (R2: rupa pre 141
dokazana; posle 141 klijent ne menja status/odobrenje/poreklo, ne ubacuje odobren red, ne briše, ne radi TRUNCATE;
`service_role` tokovi rade; migracija 134 dokazana nad PostgreSQL-om).

## 4. Dvostruka naplata (tačke 6–7) — ispravljeno, `06987253`, GATE-R4-IDEM PASS (2 prolaza)

| scenario | pre R4 | posle R4 |
|---|---|---|
| mrežno ponavljanje istog zahteva (V2, isti `Idempotency-Key`) | 1 naplata (trajna idempotencija, migracija 134 — primenjena u produkciji) | isto |
| isti ključ, drugo telo | 409, bez izvršenja | isto |
| drugi klik u 30 s posle upisanog predloga (novi ključ ili klijent bez ključa) | **2 poziva modela, 2 naplate, 1 predlog** — drugi tiho odbačen kao duplikat | 409 PRE modela i naplate („ništa nije pokrenuto ni naplaćeno") |
| drugi klik pre nego što je prvi predlog upisan (trka; upis je pozadinski) | **2 naplate, 1 predlog** | 2 naplate, **2 predloga** (svaka naplata ima svoj predlog) |
| dve izričite izrade van prozora | 2 naplate, 2 predloga | isto (ugovor) |
| neuspela izrada (502) | 0 naplata | isto |

V2 poruka: 409 mrežnog ponavljanja (`IDEMPOTENCY_IN_PROGRESS`/`CONFLICT`) ostaje „ishod nepoznat — ne ponavljajte
odmah" (GATE-R4 1. prolaz B1 zatvoren). Dokaz: `tests/test_mir001_r4_naplata_ponavljanje.py` 7/7 (stvarna ruta i
stvarni middleware), E2E savetnici 21/21 (odeljak E), C3b E2E 47/47; mutacije: bez provere 2 pada, vraćeno odbacivanje 1,
redosled poruka 4/2/1.

Preostalo (postojeće stanje, nije MIR001 regresija): legacy `/app-legacy` (`static/vindex.js`) ne šalje
`Idempotency-Key` — mrežno ponavljanje tamo nije trajno zaštićeno ni za jednog savetnika. Za nacrt iz spisa R4 to
ublažava (409 ako je prvi predlog već upisan; inače dva predloga, bez gubitka).

## 5. NS007 i read-only procena produkcije (tačke 8–9)

`MIR001_R4_PROD_PROVERA.py` (HEAD + `count=exact`, plus ponovljen R3 inventar), izlaz se čuva
lokalno, van javnog repoa:

| provera | rezultat | značenje |
|---|---|---|
| kontrole (nepostojeća tabela / kolona) | 404 / 400 | upiti zaista rade |
| `autonomy_cycles`, `autonomy_work_items` (migracija 136) | 404 / 404 | **NS007 neaktivan**: `/api/cron/autonomy` pada na `zauzmi_ciklus` → 503 `CLAIM_UNAVAILABLE`, ništa ne upisuje. Dokaz su tabele, ne repo: Render Cron se podešava u kontrolnoj tabli (`render.yaml` ne postoji) — osnivač u Render-u potvrđuje da Cron za autonomiju ne postoji |
| `v2_mutation_idempotency` (134) | 200 | trajna idempotencija postoji |
| `staging_memory.promocija_token` (140) | 200 | migracija 140 primenjena |
| `staging_memory` | 0 redova | nijedan zapis nije pogođen ni puštanjem ni povratkom |
| `predmeti` / `predmet_dokumenti` / otvorene `case_actions` | izmereno (lokalno, van javnog repoa) | obim; MIR001 ih ne menja pri puštanju |

## 6. Tačan redosled (izvršava OSNIVAČ; izvršilac ništa od ovoga ne radi)

0. **Pre svega:** push grane `rollback/mir001-f33dcce8-guard` (`7e764891`) na `origin` — BEZ PR-a i spajanja. Cilj
   povratka mora postojati pre prvog puštanja (R3).
1. **Read-only pre:** `VINDEX_ENV_FILE=<putanja do .env> python -I -X utf8 docs/v2-execution/MIR001_R4_PROD_PROVERA.py` → `staging_memory` mora biti 0
   (ili poznat broj); sačuvati izlaz.
2. **Migracija 141 — preflight** (Supabase SQL editor kao `postgres`; blok PREFLIGHT u fajlu migracije): sačuvati izlaz
   (osnov za povratak). STOP uslovi iz fajla (pogled / SECURITY DEFINER funkcija nad tabelom, `service_role` bez svih
   prava, RLS isključen) → ne nastavljati, javiti.
3. **Migracija 141 — primena** (telo fajla). Bezbedno PRE deploy-a: postojeća produkcija (`f33dcce8`) koristi samo
   `service_role` (BYPASSRLS, prava netaknuta). Kratka ACCESS EXCLUSIVE brava, bez prepisivanja podataka.
4. **Migracija 141 — postflight** (blok POSTFLIGHT): `anon`/`authenticated` bez ijednog prava; politike su tačno
   `staging_memory_sopstveni_citanje` (SELECT, authenticated) i `staging_memory_service_role` (ALL, iz 088);
   `service_role` ima sva prava.
5. **Kratka provera produkcije** posle 141, pre deploy-a: postojeći V2 „Nacrt" (lista nacrta na pregledu) radi
   (backend = `service_role`). Ako ne radi → povratak 141 (blok ROLLBACK), STOP.
6. **Push** `night/miroslav-recovery` → PR u `main` → CI. Poređenje sa **CI osnovom** `f33dcce8` (poslednji CI na
   `main`), ne sa lokalnih 22 (izmereno na Windows-u; CI je Linux); nov pad = STOP.
7. **Spajanje u `main`** → Render automatski pušta. GitHub pravi merge commit (kao #46 → `cc8bd548`), pa se pušten
   `commit` iz `GET https://vindex.rs/api/version` poredi sa SHA tog merge commita na `main`, a sadržaj sa granom:
   `git rev-parse <merge>^{tree}` = `git rev-parse night/miroslav-recovery^{tree}` (grana je potomak `f33dcce8`, pa
   spajanje ne unosi tuđe izmene).
8. **QA posle puštanja** (sintetički predmet, nikad stvarni spis): `mir001_c3b_model/final_closure/t04/PRODUKCIJA_I_QA.md`
   §B koraci 1–11, plus: (a) drugi klik „Pisanje podnesaka" u 30 s → poruka „upravo izrađen … ništa nije naplaćeno",
   krediti nepromenjeni; (b) DOCX odobrenog dokumenta bez `DOK-nn`, bez naslova i podnožja sistema.
9. **Read-only posle QA:** ponovo korak 1 — očekivano samo QA redovi (`nacrt_iz_spisa`, `dokument_za_sud`), nijedan
   `pinecone_indexed = true` za ta dva tipa, `predmet_dokumenti_iz_promocije_nacrta` = 0.

NS007 se NE aktivira (migracija 136 i Cron nisu deo ovog puštanja).

Keš: `static/sw.js` se ne menja i ne treba — V2 asseti se služe pod `/v2/app/@<commit>/` (`immutable`, novi commit = nova
adresa), service worker zaobilazi `/v2/`, a `/app` se šalje sa `no-store`. Nema novih env promenljivih ni zavisnosti.

Javnost: repo je javan — izlazi produkcionih skripti (agregati) i produkcioni brojevi nisu u javnom stablu (GATE-PUBLIC, opcija 2 osnivača: jedan očišćen zbirni commit); čuvaju se lokalno, van javnog repoa.

## 7. Povratak (zamenjuje `t04/PRODUKCIJA_I_QA.md` §C — tamo opisan povratak na goli `f33dcce8` je ZABRANJEN, R3)

- Jedini dozvoljeni cilj: **`rollback/mir001-f33dcce8-guard`** (`7e764891`, pushovan u koraku 0). Postupak u Render-u:
  (1) Settings servisa → Branch: `rollback/mir001-f33dcce8-guard` → sačuvati; (2) Manual Deploy → „Deploy latest commit";
  (3) potvrditi `GET /api/version` → `commit` = `7e764891…`; (4) read-only provera (korak 1). Dok je grana servisa
  promenjena, push na `main` NE pušta ništa. Posle ispravke: vratiti Branch na `main` i pustiti ispravljen `main` (opet
  §6 od koraka 6).
- **Zabranjeno:** Render „Rollback" na prethodni deploy, ručni deploy golog `f33dcce8`, `git revert` koji vraća kod na
  `f33dcce8` bez zaštite.
- Migracija 141 se pri povratku aplikacije NE vraća (zaštita i `f33dcce8` koriste samo `service_role`). Povratak 141 (blok
  ROLLBACK u fajlu) samo ako korak 5 pokaže potrošača sa korisničkim JWT-om.
- Ne menjati produkcione zapise; read-only provera (korak 1) pre i posle povratka.
- Ispravka R4 (dvostruka naplata) ne zahteva ništa pri povratku: zaštita nema put nacrta iz spisa kroz `/api/agents/run`.

## 8. Presuda

**READY_FOR_FOUNDER_PRODUCTION_APPROVAL** (posle nezavisnog GATE-R4) — presuda NE ovlašćuje izvršioca da pušta
produkciju; svaki korak §6 izvršava osnivač.

Osnov: bezbednost (R2: migracija 141 pripremljena, 52/52 PG, nije primenjena), integritet DOCX-a (R1: 0/120 sa internom
oznakom), povratak (R3: samo grana sa zaštitom), naplata (R4: dvostruka naplata nacrta zatvorena), regresija (skup padova =
produkcija), produkcija (0 pogođenih zapisa, NS007 neaktivan).

**Uslovi koji ostaju osnivaču (nisu blokeri koda):** (1) push grane povratka pre prvog puštanja; (2) preflight/primena/
postflight 141 pre deploy-a; (3) CI na PR-u = CI osnova `f33dcce8` (poređenje po stablu / merge SHA, §6 koraci 6–7); (4) QA §6 korak 8 na
sintetičkom predmetu; (5) odluka o javnosti agregatnih izlaza (§6, „Javnost").

**Ograničenje kvaliteta AI teksta ostaje** (C3b izveštaj §8): AI predlog i dalje sadrži materijalne greške — zato je
dokument za sud moguć samo izričitim usvajanjem po stavci i odobrenjem advokata. Ova presuda ne tvrdi PRODUCTION_READY
ni prihvatanje od stvarnog korisnika.

**GATE-R4 (nezavisni recenzent): PASS** — nijedan BLOCKED_* nije opravdan. Recenzent je nezavisno: uporedio sva tri
puna izlaza (skup padova kandidata = `f33dcce8`), potvrdio poštenje ispravke QA-03 tri mutacije (sve padaju), pokrenuo
82 testa (sa PG, 0 skipped) i C3b E2E 47/47, potvrdio da je 141 pre deploy-a bezbedan za `f33dcce8` (svi potrošači preko
`service_role`) i jednom pokrenuo read-only skript (izlaz identičan). Napomene 1–7 su unete u ovaj dokument (SHA
kandidata, broj commita, politike u postflight-u, merge commit i stablo, Render postupak povratka, CI osnova, Cron dokaz);
napomena 8 (javnost agregata) je odluka osnivača. Postojeći dug (nije regresija): `/app-legacy` bez `Idempotency-Key`.

**Odstupanje u kapiji (prijavljeno):** recenzent je, mimo dozvoljenog skripta, poslao jedan `HEAD https://vindex.rs/`
(početna strana, bez ključa, bez sadržaja, odgovor 200). Ništa nije upisano; prijavljeno osnivaču.

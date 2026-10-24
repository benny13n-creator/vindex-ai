# MIR001 C3b FINAL CLOSURE — završni izveštaj

**Konačna presuda: `C3B_CONTROLLED_DRAFTING_READY`**

To znači spremnost za osnivačev **release review ograničenog, ljudski kontrolisanog izrađivanja nacrta**. To NE znači
da su AI pravne tvrdnje postale pouzdane, NE znači `REAL_USER_ACCEPTED` i NE znači da je pun MIR-03 ispunjen. Ništa
nije pushovano, spojeno ni pušteno. Detalji: `MIR001_C3B_FINAL_CLOSURE_LEDGER.md`.

## 1. Početni i završni SHA

| | SHA |
|---|---|
| `origin/main` (produkcija), provereno `git ls-remote` | `f33dcce8` (nepromenjen) |
| početni lokalni HEAD (`night/miroslav-recovery`) | `81bd7684` (GATE-03 `C3B_FAIL`) |
| TASK-00: leksička kapija povučena, AI predlog DOCX 409 | `908d83a1` |
| TASK-01: ugovor izričitog usvajanja | `aeb6073e` |
| TASK-02: V2 tok (tri dela, usvajanje po stavci) | `dee9d8b0` |
| TASK-03: prethodna registracija | `6f9b584b` |
| TASK-03: merenje i dokazi | `c6d67252` |
| TASK-04: ovaj izveštaj | poslednji commit grane (`git log -1`) |

## 2. Tačan obuhvat diff-a

**C3b FINAL CLOSURE** (`81bd7684..HEAD`, bez `docs/`): 19 fajlova.
- Proizvod:
  - `routers/drafting.py` (ugovor usvajanja, DOCX dokumenta za sud, zaštite postojećih ruta);
  - `routers/multi_agent.py` (predlog umesto kapije, snimak);
  - `shared/usvajanje_nacrta.py` (nov);
  - `shared/nacrt_za_sud.py` (`predlog`, kapija van toka);
  - `services/law_brain.py` (oba tipa su `AI_WORK_PRODUCT`);
  - V2: `index.html`, `src/nacrt-predmeta.js`, `src/agenti-predmeta.js`, `src/app.css`.
- Testovi:
  - `test_mir001_c3b_usvajanje.py` (nov) i `c3b_usvajanje_pomoc.py`;
  - E2E `live-c3b-usvajanje-e2e.mjs` (nov);
  - izmenjeni testovi C3, C3b, C4, T06 i T10, `live-nacrt`;
  - `osb003_solo_server.py` (podrazumevane vrednosti 088, zamena modela uz zastavicu).

**Cela grana prema `origin/main`:** 47 commitova (uključujući ovaj izveštaj), 68 fajlova van `docs/`. Sadrži i ceo raniji MIR001 rad (T00–T10,
C0–C4, C3b STRUCTURAL), koji takođe nikad nije pušten.
- **Bez migracija** (`git diff f33dcce8 HEAD -- migrations` je prazan).
- Bez promena infrastrukture (Render, Cron, requirements, Docker, `.env`, `sw.js`).
- NS007 nije aktiviran (`case_change_brief` je samo registrovan u postojećem ugovoru, MIR001 T08).

## 3. Koji nebezbedan mehanizam je uklonjen ili izolovan

- **`shared/nacrt_za_sud.zastiti`**, leksička kapija „teksta za sud“, više nije u toku.
  - Kroz nju su prošli potvrđeni materijalni nalazi GATE-03, a tačni tekstovi su brisani u 9/10 scenarija.
  - Modul i njegovi čisti testovi ostaju kao dokaz merenja.
- Nacrt iz spisa više nema put do sudskog DOCX-a kao „očišćen tekst“: AI predlog se ne izvozi, ne odobrava i ne menja
  (409), uključujući ranije sačuvane i ranije „odobrene“ (bez retroaktivnog označavanja).
- Opšti izvoz teksta iz pregledača odbija tip nacrta iz spisa i tip dokumenta za sud.
- `_RE_SAMO_OZNAKA` nema ulogu ni u jednom toku; pozivaju ga samo testovi C3.
- Law Brain više ne prikazuje odobren nacrt iz spisa kao `LAWYER_VERIFIED_ARTIFACT` (znanje kancelarije).

## 4. Novi korisnički tok (V2, kartica Nacrt)

1. Savetnik za nacrte uz predmet daje odgovor pod naslovom „AI radni predlog — samo za pregled, ne ide u dokument za
   sud“. Na pregledu je red „AI predlog — za pregled, ne izvozi se“.
2. Otvoren predlog prikazuje tri dela, a razliku nose **naslovi i reči, ne boja**:
   - **„1. AI predlog — samo za pregled. Ovaj tekst NE ide u dokument za sud.“** Stavke su pasusi. Uz svaku stoje
     „Izvori koje navodi AI (nisu provereni)“, dokument koji se otvara iz same stavke i stanje rečima. Dugmad su
     „Proverio sam — usvajam u dokument za sud“ i „Ne usvajam“. „Usvoji sve“ ne postoji.
   - **„2. Procesne informacije — vaša provera pre odobrenja“.** Ima 8 tačaka: osnovni zahtev, dodatni zahtev,
     povlačenje ili izmena, odluke suda, nalog, uplata, rok, nedostajući ili nečitljiv dokument. Uz svaku su doslovni
     izvodi („značenje nije utvrđeno“). Odluku donosi advokat (potvrđujem, ispravljam, nepoznato, nije primenljivo,
     plus opis), a ništa nije unapred izabrano.
   - **„3. Tekst koji će biti izvezen u dokument za sud“.** Dokument počinje prazan; sadrži samo usvojene stavke i
     advokatov tekst. Dugmad: Sačuvaj i Odobri, uz spisak razloga koji sprečavaju odobrenje. Posle odobrenja tekst je
     zaključan, a nude se „Preuzmi odobren dokument (.docx)“ i „Nova verzija (bez odobrenja)“.
3. Odobrava se samo ono što je sačuvano. Nesačuvan tekst ili odluka zaustavlja odobrenje uz poruku.

## 5. Dokaz serverske kontrole usvajanja

Bez nove šeme: `staging_memory.tip`, zapis je u `quality_detail` (jsonb).
- **Vlasništvo:** svaka ruta čita i piše samo red korisnika iz tokena; tuđ red daje 404.
- **Poreklo:** dokument za sud nosi `predlog_id` i `predlog_sha256`. Usvajanje radi samo nad istim predmetom, nad
  neodbačenim predlogom čiji je tekst nepromenjen (sha), i samo po id-u stavke. Tekst stavke dodaje server iz snimka,
  a ne iz pregledača.
- **Šta je advokat pregledao i potvrdio:**
  - zapis o svakoj stavci (USVOJENO ili ODBACENO, sha, ko, kada);
  - odluke o 8 tačaka (ko, kada, opis); sistem ih nikad ne popunjava;
  - audit `dokument_za_sud_*`.
- **Odobrenje** (`{sha256, rev}`) važi za tačan tekst i reviziju zapisa koju je advokat video. Uslovi: svih 8 odluka,
  bez serverskih natpisa i nerazrešenih mesta, bez doslovne neusvojene AI stavke (zamka za grešku, ne dokaz).
- **Svaki upis** je uslovan (na čekanju, isti tekst, ista revizija); paralelan upis daje 409.
- Posle odobrenja nema izmene: nova verzija ne nasleđuje odobrenje ni odluke.
- Nema promocije u bazu znanja i nema poziva modela; usvajanje se ne naplaćuje.
- Ništa se ne označava kao `SOURCE_VERIFIED`. Prikaz nosi `provera_izvora: NIJE_IZVRSENA_SERVEROM`, a citat uz
  stavku ne čini je potvrđenom.

Gejtovi:
- GATE-00 PASS;
- GATE-01 PASS u 2. prolazu (1. prolaz: trka koja je brisala odluku);
- GATE-02 PASS u 3. prolazu (1. i 2. prolaz: nesačuvane odluke, lažna oznaka, nova verzija sa starim izborima).

## 6. Dokaz da DOCX sadrži odobren sadržaj

- `POST /api/staging/{dok}/docx` izvozi samo odobren dokument za sud čiji tekst ima tačno odobren sha256.
  - Nema automatskog naslova („NACRT IZ SPISA (SAVETNIK)“ je uklonjen) ni podnožja „Generisano … Vindex AI“.
  - Zaglavlje kancelarije (podaci korisnika) ostaje.
  - Ostali izvozi su nepromenjeni.
- Dozvoljeno formatiranje: red sa „# “ postaje naslov, `**` postaje podebljano (oznake na ekranu to kažu).
- Proveren preuzet fajl (python-docx), a ne tekst sa servera:
  - E2E 44/44;
  - TASK-03: 120/120 DOCX-a (110 replay + 10 stvarnih). Pasusi su jednaki odobrenom tekstu, a odobren tekst je TAČNO
    spoj usvojenih stavki uz advokatove izmene (K1b).

## 7. Negativni testovi i nezavisna recenzija

**TASK-03 (prethodna registracija `6f9b584b`, GATE-03 PASS):**
- **Deo A:** 100 snimljenih SIROVIH izlaza gpt-4o iz neuspelog GATE-03 i 10 sa ubačenom netačnom tvrdnjom.
  - Kroz novu rutu: 110/110 odobreno i izvezeno, **0 povreda granice**.
  - Ubačena tvrdnja je u 10/10 slučajeva AI predlog, a u 0/10 je u dokumentu.
  - Harness hvata 7/7 namerno pokvarenih servera.
- **Deo B:** 10 stvarnih poziva gpt-4o, nezavisan „advokat“ (B1) i dva odvojena slepa ocenjivača (B2: AI predlog,
  B3: dokument za sud).
  - 10/10 je odobreno, **0 povreda**.
  - Dokumenti za sud (B3): **M = 0/10**, neprazan i koherentan 10/10, Q 3,4.
- Negativni testovi 1–10 iz zadatka su mapirani na automatske testove (ledger, TASK-03 K8); svi prolaze.

**Regresije:**
- Pun skup (`t04/pun_skup.txt`): `81bd7684` daje 23 failed i 12.024 passed, a HEAD 23 failed i 12.043 passed.
  **Skup padova je identičan**; svih 23 su postojeći padovi okruženja (e-pošta, COI/trio, legacy pristupačnost,
  kanarinac mreže, registracija, cold start).
- Browser: `live-c3b-usvajanje-e2e` 44/44, `live-nacrt` 54/54, `live-agenti` 52/52, `live-savetnici-e2e` 16/16,
  `live-law-brain` 45/45, `live-mir001-spis-e2e` 17/17.
- Regresija je ovde merena prema `81bd7684` (početak ovog sprinta). Raniji neobjavljen MIR001 rad na istoj grani
  (T00–T10, C0–C4, C3b STRUCTURAL) ima svoje dokaze bez regresije prema svojim osnovama u ranijim gejtovima:
  `MIR001_FINAL_CLOSURE_REPORT.md` i `MIR001_C3B_STRUCTURAL_LEDGER.md` („pun paket … 0 novih padova“). Pun paket
  prema `f33dcce8` nije ponovljen u ovom sprintu.

## 8. Preostala ograničenja kvaliteta AI teksta (AI CONTENT QUALITY)

- **AI predlog i dalje sadrži materijalne greške.** Slepi B2 nad 10 novih predloga: M1 3/10, M2 2/10, M5 7/10,
  M7 4/10, sistemski tekst 6/10, Q 2,8. GATE-03: potvrđeni nalazi u 24/100.
  - Iste klase: „4.200.000 uključuje 600.000“, prećutana odluka suda ili dopis o uplati, nečitljiv zapisnik prikazan
    kao poznat.
  - **Ovo nije popravljeno i ne tvrdi se.**
  - Granica radi samo ako advokat zaista čita: izričito usvojena pogrešna stavka ulazi u dokument kao advokatova
    odluka.
- Procesne tačke se ne porede sa tekstom (namerno, nema leksičke kapije).
- AI rezervisana mesta van spiska (npr. „[POTREBNO JE DOSTAVITI POTPIS …]“) prolaze ako ih advokat usvoji.
- **Odluka osnivača:** izvod koji umeće server, oblika „(DOK-07, zapisnik … 15.07.2026.: „…“)“, nosi internu
  numeraciju DOK-nn i tekst bez dijakritika. Ulazi u DOCX kad advokat usvoji stavku (74 od 120). Treba odlučiti da
  li je to prihvatljivo u sudskom dokumentu ili se pre puštanja prikazuje drugačije.
- B1–B3 su instance istog modela, a ne ljudi; izolacija je bila samo po uputstvu. Ovo nije prijem stvarnog korisnika.
- Mehanički advokat dela A meri granicu, a ne sadržaj.

Ostala preostala ograničenja (kontrola i proizvod):
- **Opšti izvoz teksta iz pregledača** (`/api/nacrti/export/docx`, V2 i `/app-legacy`): ručno kopiran AI predlog
  (bez granice internih napomena, sa `tip` koji nije zaštićen) izvozi se kao DOCX sa naslovom i podnožjem sistema.
  Ovo je van zaštićenog toka i nije označeno kao odobreno.
- **`isti()`** (kasni odgovor drugog AI predloga u istom predmetu) nema test; utvrđen je samo čitanjem koda.
- **RLS 088** dozvoljava vlasniku direktan upis u `staging_memory` mimo ruta (§9).
- **NS007:** `case_change_brief` (MIR001 T08) je u listi agenata (`workers/background_agents.py`). Nije aktiviran, ali
  postaje živ u istom trenutku kada se NS007 aktivira (Cron ili okidač).
- **Trošak:** ponovljena izrada predloga u kratkom roku za isti predmet naplaćuje drugi poziv modela, a drugi predlog
  se ne upisuje na pregled (zaštita od duplikata; od ranije, nepromenjeno).
- **Kozmetika:**
  - Poruka za 409 kod izvoza drugih nacrta sa pregleda (`frontend-v2-ng/src/nacrt-predmeta.js`, `docx()`) i dalje
    pominje `[IZOSTAVLJENO …]` iz povučene kapije.
  - Grana `iz_spisa` dalje u `staging_approve` je posle ranog 409 nedostižna.
  - Kandidati tačaka prikazuju sirove nazive vrsta (`stranka_predlaze`).

## 9. Produkcioni preduslovi i plan povratka

Read-only procena uticaja: `mir001_c3b_model/final_closure/t04/PRODUKCIJA_I_QA.md`. Ukratko:
- **Preduslovi:**
  1. Read-only upiti iz plana (očekivano 0 redova tipa `nacrt_iz_spisa` i `dokument_za_sud`).
  2. Pregled RLS-a za `staging_memory`. Politika 088 `FOR ALL` za vlasnika verovatno dozvoljava vlasniku direktan
     upis „odobreno“ mimo ruta. To je postojeće stanje, ali kontrola odobrenja važi za rute aplikacije. Zatvaranje je
     migracija i odluka osnivača.
  3. Prvi korak kontrolisanog QA-a potvrđuje da PostgREST prihvata filter `quality_detail->>usvajanje_rev` u UPDATE-u
     (u lažnoj bazi je proveren; isti obrazac postoji u `routers/evidence.py`). Ako ga ne prihvati, rute padaju
     zatvoreno (409 ili 500), a ne tiho.
  4. Odluka o izvodu DOK-nn (§8).
- **Povratak:** ponovo pustiti `f33dcce8`. Migracija nema, pa nema ni vraćanja baze.
  - Stari kod vidi redove `dokument_za_sud` i `nacrt_iz_spisa` kao obične nacrte. Red na čekanju stari „odobri“ može
    uneti u bazu znanja. **Odobren** red (`pinecone_indexed = false`, ocena ≥ 0,85, a ocenu dobija pri izmeni teksta)
    unosi stari „Ponovi upis“ (GATE-04 B1).
  - Plan navodi read-only upit za obe grupe i osnivačevu odluku pre povratka (upis radi osnivač, ne izvršilac).
  - Bez te odluke povratak krši invarijantu „nikad u znanje“.

## 10. Konačna presuda

**`C3B_CONTROLLED_DRAFTING_READY`** — uslovi iz zadatka:

| uslov | stanje |
|---|---|
| funkcionalna razlika AI predlog / usvojen tekst | ✓ (server: poseban red, nepromenljiv predlog; UI: tri dela rečima) |
| korisnik pregledao i izričito usvojio relevantan sadržaj | ✓ (po stavci; 8 tačaka; odobren sha + rev) |
| nemoguće neprimetno izvesti neodobren AI predlog kroz ovaj tok | ✓ (409 svuda; 120/120 bez povrede) |
| DOCX verno sadrži odobren tekst | ✓ (preuzet fajl = odobren tekst; K1b) |
| nema sistemskog teksta u sudskom dokumentu | ✓ (naslov i podnožje uklonjeni; B3 M8 0/10); izvod DOK-nn je odluka osnivača (§8) |
| nema štetnog leksičkog uklanjanja | ✓ (kapija van toka; K4: ceo izlaz modela u predlogu) |
| negativni testovi prolaze | ✓ |
| relevantne regresije prolaze | ✓ (identičan skup padova) |
| nema novog neprihvatljivog bezbednosnog ili podatkovnog rizika | ✓ uz napomenu: RLS 088 (postojeće stanje) i opšti izvoz teksta iz pregledača (van zaštićenog toka) su prijavljeni |

Šta beta korisnik **može**:
- da dobije AI radni predlog iz spisa i vidi izvore;
- da odluči o svakoj stavci i o 8 procesnih informacija;
- da napiše i ispravi tekst;
- da odobri i izveze DOCX tačno tog teksta.

Šta **ne može**:
- da se osloni na AI tvrdnje kao proverene;
- da dobije automatski „očišćen“ sudski tekst.

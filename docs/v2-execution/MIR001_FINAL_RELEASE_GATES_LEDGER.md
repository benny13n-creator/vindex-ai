# MIR001 FINAL RELEASE GATES — ledger (bezbednost, integritet DOCX-a, povratak)

Zadatak osnivača: „VINDEX — MIR001 FINAL RELEASE GATES / SCOPE: SECURITY, DOCX INTEGRITY, ROLLBACK“. Polazno stanje:
- C3b FINAL CLOSURE je završen: `C3B_CONTROLLED_DRAFTING_READY`, `MIR001_C3B_FINAL_CLOSURE_REPORT.md`.
- Arhitektura draftinga se ne otvara ponovo.

**Provera pre rada:**
- grana `night/miroslav-recovery`, HEAD `ba9e48e9`;
- radno stablo čisto;
- `origin/main` = `f33dcce8`, i u `git ls-remote` i posle `fetch`;
- grana je 47 commitova ispred, 0 iza.

Dokument „VINDEX — CANONICAL OPERATING RULES“ nije u repou kao zaseban fajl. Pročitan je njegov izvršni zapis
`docs/v2-execution/VINDEX_V2_FOUNDER_EXECUTION_DIRECTION.md` (PRESERVE → … → RELEASE, definicija završenog, očuvanje).

## TASK-R1 — razdvajanje izvora od teksta za sud u DOCX-u

**Početno ponašanje (izmereno):**
- U merenju TASK-03 (`t03/replay`, `t03/primeni`) **svih 120 od 120** izvezenih DOCX-a sadrži `DOK-nn`.
- Izvori su dva:
  - **izvod koji umeće server** (`[[PS-nn]]` → „(DOK-07, zapisnik … 15.07.2026.: „…“)“), u 74/120 (GATE-03 napomena 3);
  - **oznake koje je napisao AI** („(DOK-05)“), koje je advokat usvojio uz stavku.
- `DOK-nn` je Vindexova numeracija dokumenata u spisu; sud je ne poznaje.

**Izmena (najmanja; generički DOCX izvoz i drugi tokovi nepromenjeni):**
1. `shared/nacrt_za_sud.prikaz_izvoda_za_dokument` i `predlog()`:
   - predlog sada daje dve verzije istog teksta modela: `tekst` za pregled (izvod sa `DOK-nn`, izvor za proveru) i
     `tekst_za_dokument` (isti doslovan izvod, sa naslovom i datumom dokumenta, bez interne oznake);
   - server više ne umeće interni metapodatak u tekst za sud.
2. `shared/usvajanje_nacrta`:
   - snimak predloga je **verzija 2**: svaka stavka nosi `tekst_za_dokument` i `sha256_za_dokument`;
   - `DOK-nn` je strukturni nedozvoljen sadržaj, kao `[PROVERITI`;
   - odobrenje se zaustavlja uz razlog koji navodi oznaku i dokument („DOK-06 = 06 Izjasnjenje na nalaz vestaka.pdf“);
   - **tekst se ne briše niti „čisti“**: advokat zamenjuje oznaku, a njegov namerni citat ostaje.
3. `routers/drafting.py`:
   - usvajanje unosi `tekst_za_dokument`, a zapis nosi oba sha;
   - stariji snimak (verzija 1) se **ne usvaja i ne proglašava kompatibilnim** (409 i pri kreiranju dokumenta za sud i
     pri usvajanju);
   - izvoz odobrenog teksta koji sadrži `DOK-nn` (odobren pre R1) daje 409 uz objašnjenje: odobren tekst se pri izvozu
     ne menja, nego ide u novu verziju.
4. `routers/multi_agent.py` predaje obe verzije snimku.
5. V2 (`nacrt-predmeta.js`):
   - stavka čiji se tekst za dokument razlikuje prikazuje „U dokument za sud ulazi (izvod bez interne oznake spisa)“;
   - stavka sa `DOK-nn` upozorava da sud oznaku ne poznaje i da blokira odobrenje;
   - izvor (`DOK-nn`, dokument koji se otvara) ostaje u panelu za proveru.

**Dokaz:**
- Testovi `test_mir001_c3b_usvajanje.py`, T06, C4, T10, C3, C3b i NS008 artefakti: **236 passed**. Novi su:
  - R1 izvod servera (pregled sa DOK-07, dokument bez nje, DOCX bez `DOK-`, oba sha u zapisu);
  - oznaka zaustavlja odobrenje bez brisanja, a citat korisnika ostaje;
  - odobren tekst sa oznakom se pri izvozu ne menja (409);
  - stari snimak se ne usvaja;
  - dve verzije iste strukture.
- Testovi koji usvajaju AI stavke sa `(DOK-nn)` sada pre odobrenja rade **radnju advokata** (`U.bez_oznaka`), a
  sistem to ne radi sam. U testu ugovora osnovne stavke su bez oznaka.
- E2E `live-c3b-usvajanje-e2e.mjs`: **47/47**. Novi koraci:
  - stavka sa izvodom prikazuje šta ulazi u dokument (bez DOK-07), a pregled ga zadržava;
  - stavka sa „(DOK-05)“ upozorava;
  - odobrenje se zaustavlja uz razlog „DOK-05 = 05 Nalaz i misljenje vestaka.pdf“, a tekst nije promenjen;
  - advokat zamenjuje oznaku, pa sledi odobrenje;
  - u DOCX-u nema `DOK-`.
- `live-nacrt` 54/54.
- **Ponovljeno merenje na stvarnim izlazima** (harness `t03/t03_fc.py`, prilagođen R1):
  - mehanički advokat i B1 zamenjuju `DOK-nn` kao radnju advokata;
  - K2 dodatno traži da u DOCX-u nema `DOK-`;
  - rezultati su u novim folderima `t03/replay_r1/` i `t03/primeni_r1/`; prethodni dokazi nisu dirani.
  - 110 replay (100 izlaza GATE-03 i 10 sa ubačenom tvrdnjom) + 10 stvarnih: **120/120 odobreno, povreda K1–K7: 0,
    DOCX sa `DOK-nn`: 0/120** (pre R1: 120/120).
  - Sve zamene advokata B1 su primenjene.
- Mutacije (`scratchpad/r1_mut.py`), **6/6 ubijeno**:
  - usvajanje teksta za pregled;
  - oznaka ne blokira;
  - stari snimak prihvaćen;
  - izvoz „čisti“ odobren tekst;
  - izvod za dokument sa oznakom;
  - kreiranje dokumenta iz starog snimka.

**Uticaj na korisnost:** advokat pre odobrenja mora da zameni AI oznake `DOK-nn`; u stvarnim predlozima ima ih više po
dokumentu. To je namerno: sistem ne prepravlja AI tekst sam, a sud oznaku ne poznaje.

**GATE-R1, nezavisni recenzent: PASS.**
- Testovi: 248 passed, E2E 47/47, `live-nacrt` 54/54.
- Prethodni dokazi `replay/` i `primeni/` nisu menjani.
- Nezavisno merenje:
  - `DOK-nn` je u DOCX-u bio u 120/120, a sada je u **0/120**;
  - izvod servera je bio u 74/120, što se poklapa sa zadatkom;
  - rekonstrukcija drugim putem je identična u 120/120.
- Recenzentove mutacije: 5/5 ubijeno.
- Ocena odluke „AI-napisan `DOK-nn` blokira, ne briše se“: ispravna (tačke 3 i 5).
- Napomene:
  - **N1 (ozbiljna):** pravilo je hvatalo samo `DOK-05`. Varijante (`dok-06`, `DOK 05`, ćirilica, Unicode crte, vodeće
    nule, `Dok-5`) stizale su u DOCX.
  - **N2:** poruka pri izvozu za dokument iz predloga v1 vodila je u ćorsokak.
  - **N3:** izvod bez oznake se ne razlikuje za dva dokumenta istog naslova i datuma (izvor je jasan u panelu).
  - **N4:** korisnost: advokat zamenjuje u proseku oko 2,6 oznaka po dokumentu.
  - **N5:** zapis predloga je nastajao posle naplate.
  - **N6:** merenje 0/120 delom nastaje po konstrukciji (zamenu radi harness-advokat); `core.xml` „python-docx“ je od
    ranije.

**Zatvoreno posle PASS-a:**
- **N1:**
  - `_RE_OZNAKA` i `oznake_u()` prepoznaju oznaku velikim slovima (latinica ili ćirilica) uz bilo koji razdvajač
    (razmak, NBSP, tačka, crtica, U+2010–U+2015, U+2212) i vodeće nule, ili bilo kojim slovima uz crticu;
  - mala slova bez crtice se ne broje („dok 15 dana“);
  - oznaka se svodi na „DOK-nn“ iz spiska;
  - V2 primenjuje isto pravilo.
- **N2:** poruka pominje i novi predlog.
- **N5:** zapis predloga se pravi pre naplate (502 bez naplate i upisa).
- Testovi:
  - 12 varijanti oznake blokira;
  - 6 običnih reči ne blokira;
  - pad zapisa pre naplate ne naplaćuje i ne upisuje.

**GATE-R1, potvrda istog recenzenta nad ispravkama: PASS.**
- Testovi: 264 passed (8 fajlova), E2E 47/47, `live-nacrt` 54/54.
- Probe P1 i P2: sve varijante koje su ranije stizale u DOCX sada daju 409.
- Lažni pogoci: nema ih u 120 odobrenih tekstova, 120 DOCX-a, Golden Case-u, 100 sirovih izlaza ni u 902 `.md`/`.txt`
  fajla repoa.
- N5 ne menja uspešan tok: harness 110/110 i 10/10 je identičan sa `replay_r1` i `primeni_r1`.
- Preostale napomene:
  - **N3a:** NBSP i tačka nisu bili razdvajači. Zatvoreno: dodati su na server i u V2; testovi dobijaju 3 varijante,
    ukupno 276 passed.
  - **N3b:** tekst velikim slovima „ROK DOK 15 DANA“ se blokira kao `DOK-15`. Ništa se ne briše; advokat preformuliše.
  - **N3c:** za 6 i više cifara V2 upozorava, a server ne blokira. Kozmetika.

**TASK-R1 / GATE-R1: PASS.**

## TASK-R2 — zatvaranje direktnog upisa u `staging_memory`

**Nalaz osnivača** (read-only provera produkcije):
- politika `staging_memory_sopstveni` je `FOR ALL`;
- `authenticated` ima `UPDATE` i `INSERT`;
- kolone odobrenja menja korisnik;
- nema okidača.

**Legitimni pristupi** (dokazano grep-om i čitanjem koda):
- **Backend** pristupa samo kao `service_role` (`shared/deps._get_supa`, `SUPABASE_SERVICE_KEY`, BYPASSRLS). To
  pokriva:
  - sve rute `/api/staging/*` (pregled, PATCH, usvajanje, procesne tačke, odobrenje, odbijanje, DOCX, ponovni upis);
  - `routers/multi_agent.py` (upis predloga kroz `_stage_draft_for_review`);
  - `services/law_brain.py` i `law_brain_promocija.py`;
  - `shared/predmet_deletion.py`;
  - `app/services/retrieve.py`;
  - RPC iz 140 (SECURITY INVOKER, EXECUTE samo `service_role`).
- U `api.py` nema korisničkog JWT klijenta prema bazi; pomen je samo komentar uz izolovan klijent za prijavu.
- **Frontend** (`static/`, `frontend-v2-ng/`) ne čita i ne piše tabelu direktno, nego samo kroz `/api/staging/*`.
- Nema pogleda ni okidača nad tabelom. Pominju je samo migracije 088, 136 (komentar) i 140.

**Izmena:** `migrations/141_staging_memory_bez_direktnog_upisa.sql`. Ista je kao obrazac 138 (najmanje; bez novog
okvira autorizacije):
- `REVOKE ALL ON public.staging_memory FROM PUBLIC, anon, authenticated` (uključujući TRUNCATE, REFERENCES, TRIGGER);
- politika `FOR ALL` je zamenjena politikom `staging_memory_sopstveni_citanje` (`FOR SELECT TO authenticated`). To je
  odbrana u dubini: ako bi se upis ponovo dodelio, bez politike za INSERT, UPDATE i DELETE ne prolazi.
- Backend se ne menja, a podaci se ne menjaju.
- Fajl sadrži tačan SQL, **preflight** (prava, politike, okidači, RLS), **postflight** (očekivano 0 prava za
  anon/authenticated, dve politike, prava `service_role`, QA aplikacije) i **povratak**.
- **Migracija NIJE primenjena u produkciji; primenjuje je osnivač.**

**Dokaz na stvarnoj PostgreSQL bazi:**
- `tests/test_mir001_r2_staging_pg.py`: izolovan klaster PG 17.9 na `127.0.0.1:55441`, uloge `anon`,
  `authenticated` i `service_role` (BYPASSRLS), `auth.uid()` i Supabase podrazumevana prava (`tests/ns4f_pg.py`),
  migracije 088 do 140, pa 141. Rezultat: **22 passed**.
- **Pre 141:** A svojim JWT-om direktno odobrava svoj dokument za sud, ubacuje odobren red, menja `predmet_id` i radi
  TRUNCATE. Rupa je potvrđena.
- **Posle 141:**
  1. A ne odobrava (42501), a red ostaje na čekanju.
  2. A ne ubacuje odobren red.
  3. A ne menja `status`, `is_lawyer_approved`, `approved_by`, `quality_detail`, `tekst`, `predmet_id`, `tip` ni
     `pinecone_indexed`, i ne briše red. TRUNCATE je odbijen za `authenticated` i `anon`. Prava `anon`,
     `authenticated` i PUBLIC su prazna, a politike su tačno dve.
  4. B ne čita, ne menja i ne briše A-ov red. Ni A više ne čita direktno.
  5. Backend (`service_role`) radi iste uslovne upise kao rute: usvajanje po statusu, tekstu i
     `quality_detail->>'usvajanje_rev'`; zastarela revizija daje 0 redova; odobrenje i odbijanje rade, a RPC 140 se
     izvršava. Ovo ujedno potvrđuje filter po JSON putanji u stvarnom PostgreSQL-u (C3b GATE-01 N-b), mada ne i kroz
     sam PostgREST.
  6. Nova verzija nastaje bez odobrenja (podrazumevane vrednosti 088), a A ne može da je odobri.
  7. Dva istovremena uslovna upisa nad istom revizijom: tačno jedan prolazi (stvarna brava reda i ponovna provera
     uslova). Ponovljen zahtev sa starom revizijom daje 0.
  8. `anon`: SELECT, INSERT, UPDATE, DELETE i TRUNCATE su odbijeni.
- Postojeći PG testovi (`ns4f_pg_rls`, `ns4f_pg_promocija`, `ns4f_pg_ishod`) nad istim klasterom: 130 passed. Uz R2
  testove ukupno 152; 2 preskočena (`test_mir001_t08_pg` koristi drugu promenljivu okruženja, nije vezan za ovo).

**Ograničenja:**
- Ponašanje PostgREST-a i Supabase JWT-a je simulirano ulogama i `request.jwt.claim.sub`, a ne pravim PostgREST
  procesom.
- U produkciji mogu postojati dodatne politike ili prava koje lokalni klaster nema; zato je preflight upit obavezan
  pre primene.

**GATE-R2, nezavisni adversarijalni recenzent: PASS (bez blokera).**
- **Inventar ponovljen nezavisno:** samo `service_role`; frontend čita samo `conversations`, `profiles` i
  `reported_errors`; nema realtime, pogleda, okidača ni SECURITY DEFINER funkcija. REVOKE SELECT ne ruši nijedan tok.
- **Napad na migraciju:**
  - dvostruka primena je idempotentna;
  - kolonska prava data pre migracije nestaju;
  - ponovna dodela `GRANT ALL` posle 141: DML i dalje blokira RLS (UPDATE i DELETE 0 redova, INSERT odbijen), ali
    **TRUNCATE ponovo prolazi** (N2);
  - redosled sa 138/140 je nebitan.
- **Rezultati:** R2 22/22, postojeći PG 130, usvajanje 43/43.
- **Recenzentove mutacije migracije:** 8 od 10 uhvaćeno. Preživele su:
  - kolonski `GRANT UPDATE` (N4);
  - politika čitanja `USING(true)` (N5).
- **Napomene:**
  - **N1:** preflight i postflight nisu prikazivali kolonska prava, vlasnika, funkcije i poglede.
  - **N2:** odbrana u dubini ne pokriva TRUNCATE.
  - **N3:** formulacija „samo čitanje“, a SELECT je oduzet.
  - **N6:** test 7 nije dokazivao da T2 zaista čeka bravu.
  - **N7:** u ledger-u je bilo napisano 152 umesto 130.
- **Van obima R2 (od ranije):** `routers/drafting.py`, opšti `reject` za tipove koji nisu dokument za sud, menja
  status po samom `id`. Može da odbije već odobren i indeksiran nacrt, a `pinecone_indexed=true` ostaje. Ovo ide u
  R3/R4 inventar.

**Zatvoreno posle PASS-a:**
- **N1:**
  - preflight sada prikazuje `has_table_privilege` za svako pravo, `has_any_column_privilege`, vlasnika, `relacl` i
    `attacl`, politike, okidače, funkcije (`prosecdef`, `proacl`) i poglede koji pominju tabelu, uz uslove za STOP;
  - postflight se poziva na te upite;
  - **svi upiti su izvršeni na test bazi pre i posle 141**: `mir001_c3b_model/final_release/r2_preflight_test_baza.txt`.
- **N3:** zaglavlje opisuje uspavanu politiku čitanja i TRUNCATE.
- **N4:** test 3b proverava svako pravo nad tabelom i kolonama; novi test 3c pokazuje da kolonska prava data pre
  migracije nestaju, uz dvostruku primenu.
- **N5:** novi test 4b vraća `GRANT ALL`: B ne vidi A-ov red, A vidi svoja dva, UPDATE i DELETE menjaju 0 redova,
  INSERT odbija RLS.
- **N6:** test 7 preko `pg_stat_activity` (`wait_event_type='Lock'`) dokazuje da T2 čeka bravu koju drži T1.
- **N7:** broj je ispravljen.
- **R2 testovi: 24 passed.**
- **N2 nije implementiran**, jer bi okidač bio novi mehanizam van najmanje izmene. Preporuka osnivaču:
  - posle svake buduće dodele prava nad šemom `public` ponoviti postflight (a);
  - ili u release gejt dodati proveru `has_table_privilege('authenticated','public.staging_memory','TRUNCATE') = false`.

**TASK-R2 / GATE-R2: PASS.** Migracija 141 je pripremljena, a primenu u produkciji radi osnivač.

## TASK-R3 — granice izvoza i povratka

Analiza i odluka su u **`docs/v2-execution/MIR001_R3_IZVOZ_I_POVRATAK.md`**.

**Izvoz:**
- Kategorije su razdvojene:
  - predmetni izvoz odobrene verzije: dokument za sud, samo tačno odobren sha;
  - AI radni predlog: 409;
  - drugi nacrti sa pregleda: sačuvan tekst, uz naslov i podnožje alata;
  - generički izvoz proizvoljnog teksta: `/api/nacrti/export/docx` i `/export/docx`.
- Nijedan opšti izvoz ne tvrdi odobrenje ni pregled.
- Tvrdnja izvršioca je ograničena: zaštićeni predmetni tok ne dozvoljava neodobrenu promociju ni predstavljanje kao
  pregledanog. Ručno kopiranje AI teksta u generički izvoz ili drugi editor se ne može zabraniti i to se ne tvrdi.
- Kod izvoza nije menjan (granice postoje od C3b/R1).

**Read-only inventar produkcije** (`MIR001_R3_PROD_INVENTAR.py`, samo GET, agregatno, ništa nije upisano):
- `staging_memory` = 0 redova (`count=exact` daje `*/0`; nepostojeća kolona daje 400, dakle upit radi);
- nacrti iz promocije: 0;
- obim (`predmeti`, `predmet_dokumenti`, otvorene `case_actions`) izmeren — brojevi lokalno, van javnog repoa;
- `autonomy_work_items` daje 404 (tabela ne postoji; migracija 136 nije primenjena).

**Povratak:** `f33dcce8` nad redovima novog toka:
- odobrava AI predlog i upisuje ga u bazu znanja (ocena ≥ 0,85);
- nudi i izvršava „Ponovi upis“ za odobren dokument za sud;
- PATCH briše zapis usvajanja;
- Law Brain prikazuje dokument kao `LAWYER_VERIFIED_ARTIFACT`;
- izvozi tekst sa internim napomenama;
- `reject` odbija odobren dokument za sud.

**Prost povratak na goli `f33dcce8` je ZABRANJEN čim je MIR001 bar jednom pušten** (vidi pravilo posle B1).

**Najmanja bezbedna alternativa:** lokalna grana `rollback/mir001-f33dcce8-guard` (worktree `C:/vindex-mir001-rollback`,
lokalni commit `7e764891`, nije push).
- Obuhvat: 3 fajla, +37/−3.
- Za oba nova tipa u ovim putanjama vraća 409:
  - approve, PATCH i ponovni upis;
  - `reject` odobrenog dokumenta za sud;
  - opšti izvozi teksta sa granicom ili sa tipom novog toka.
- `_ponovni_upis_moguc` vraća false, a Law Brain klasu `AI_WORK_PRODUCT`.
- Test `tests/test_mir001_r3_rollback_guard.py`:
  - **5/5** sa zaštitom;
  - **na golom `f33dcce8` 4/5 pada** (opasnost dokazana);
  - sa susednim staging testovima **50 passed**.
- Širi skup (70 fajlova iz `fc_siri.txt` koji postoje na `f33dcce8`): **863 passed, 0 failed**, i sa zaštitom i bez
  nje.

**Pravilo (posle GATE-R3 1. prolaz, B1):**
- Čim je MIR001 bar jednom pušten, jedini dozvoljeni cilj povratka je `rollback/mir001-f33dcce8-guard`
  (`7e764891`, lokalni commit).
- Goli `f33dcce8` i Render „Rollback“ na prethodni deploy su zabranjeni.
- Granu pushuje osnivač pre prvog puštanja; agent ne pushuje.
- Migracija 141 se pri povratku aplikacije ne vraća.

**GATE-R3, 1. prolaz — nezavisni recenzent: FAIL (jedan bloker, u pravilu, ne u kodu).**
- **Šta je potvrđeno:**
  - izvoz je potpun i ni jedan izvoz ne tvrdi odobrenje;
  - spisak opasnih putanja u `f33dcce8` je potpun, a recenzent je svaku potvrdio probom na golom `f33dcce8`;
  - zaštita pokriva sve putanje: 5/5; na golom 4/5 pada;
  - recenzentove probe: 9/9 sa zaštitom, a na golom 7/9 pada;
  - svako uklanjanje neke od 8 zaštitnih linija obara test;
  - regresija: 250 passed;
  - skript je samo GET, a izlaz je 0.
- **B1:** pravilo 1 je dozvoljavalo goli `f33dcce8` na osnovu inventara koji zastareva pre i tokom povratka (novi red
  nastaje dok se povratak deploy-uje), a recenzent je izmerio da stari approve tada promoviše AI predlog.
- **Napomene:**
  - **N1:** „jedan commit“, a izmena nije bila commitovana.
  - **N2:** dodatni brojevi i NS007 404 nisu izlazili iz skripta.
  - **N3:** red o NS007 je bio nepotpun (`f33dcce8` već ima NS007 infrastrukturu).
  - **N4:** `case_actions.dokaz.zadrzano` (C1) se gubi povratkom.
  - **N5:** `POST /api/nacrt` sa `vrsta` kao slobodnim stringom; `pravna_aktuelnost` nad celim tekstom.

**Ispravke posle 1. prolaza (samo dokument, skript i commit grane povratka; kod MIR001 grane nije menjan):**
- **B1:** pravilo je prepisano. Goli povratak je zabranjen čim je MIR001 bar jednom pušten, uključujući Render
  „Rollback“. Grana sa zaštitom je jedini cilj, a pushuje je osnivač pre prvog puštanja.
- **N1:** zaštita je commitovana lokalno kao `7e764891` na `rollback/mir001-f33dcce8-guard` (nije push).
- **N2:** skript sada sam daje `kontrola_upit_radi`, `staging_count_exact`, `predmeti`, `predmet_dokumenti`,
  `case_actions_otvorene` i `ns007_autonomy_work_items_http`. Izlaz je u
  lokalnom izlazu (van javnog repoa): `staging_memory` 0, obim izmeren, NS007 404.
- **N3, N4, N5:** dopunjeni u tabeli i napomenama R3 dokumenta.

**GATE-R3, 2. prolaz — isti nezavisni recenzent: PASS.**
- B1 zatvoren (§2 zaključak, §3 pravilo 1–5, ledger); N1–N5 potvrđeni.
- `7e764891` je jedini commit nad `f33dcce8` (4 fajla, +125/−3), worktree čist; isti kod kao u 1. prolazu (razlika samo
  CRLF/LF, sha256 bez CR jednak za sva 4 fajla); zaštitni test 5/5; grana ne postoji na `origin`.
- Skript pročitan (samo GET/HEAD, bez sadržaja) i pokrenut jednom: izlaz se poklapa sa lokalnim izlazom.
- Preostale napomene (nisu blokeri): (1) zastareo red „nije commitovana do GATE-R3" — usklađen ovde; (2) širi skup
  „70 fajlova / 863 passed" recenzent nije ponovio (sam je pokrenuo 17 relevantnih fajlova: 250 passed) — tvrdnja ostaje
  agentova, ponavlja se u TASK-R4.
- Preostaje osnivaču: push grane `rollback/mir001-f33dcce8-guard` pre prvog puštanja MIR001.

## TASK-R4 — integracija i odluka o puštanju

Izveštaj: `MIR001_R4_PUSTANJE_I_POVRATAK.md` (redosled §6, povratak §7, presuda §8).

- **Pun skup** (OCR, `-p no:randomly`): `f33dcce8` (produkcija) 22 failed / kandidat `ee33484b` 22 failed — **skup padova
  identičan** (22 osnova). Jedina razlika na `06987253` bila je QA-03 (leksički skener potpisa hronologije hvatao interno
  pripisivanje `shared/procesno_stanje.py`) — ispravljena u `ee33484b` uz zaštitni test.
- **E2E:** C3b usvajanje 47/47, MIR001 spis 17/17, nacrt 54/54, agenti 52/52, savetnici 21/21, Law Brain 45/45.
  Širi skup (88 fajlova) 1220 passed.
- **RLS / idempotencija nad PG:** 52 passed, 0 skipped (izolovan klaster).
- **Dvostruka naplata** (`06987253`, GATE-R4-IDEM PASS u 2. prolazu): mrežno ponavljanje — 1 naplata (postojeći
  `Idempotency-Key`, migracija 134); drugi klik u 30 s posle upisanog predloga — pre: 2 naplate i 1 predlog (drugi tiho
  odbačen), posle: 409 pre modela i naplate; trka pre upisa — posle: 2 naplate i 2 predloga. 1. prolaz FAIL (B1: V2
  poruka „ništa nije naplaćeno" i za 409 mrežnog ponavljanja) → ispravljeno, E2E odeljak E + mutacije.
- **Produkcija (read-only, HEAD/GET):** `staging_memory` 0; NS007 tabele 404 (neaktivan); 134 i 140 primenjene.
- **GATE-R4 (nezavisno): PASS**; napomene 1–7 unete u izveštaj, 8 (javnost agregata) odluka osnivača. Odstupanje:
  recenzent je poslao jedan nedozvoljen `HEAD https://vindex.rs/` (bez ključa, bez upisa) — prijavljeno.
- **Presuda: READY_FOR_FOUNDER_PRODUCTION_APPROVAL.** Ne ovlašćuje izvršioca da pušta produkciju.

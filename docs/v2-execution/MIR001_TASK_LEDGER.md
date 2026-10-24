# MIR001 — Miroslav Requirements Recovery — knjiga zadataka

Jedan zapis po zadatku. Nivoi: PROVEN / INFERRED / ASSUMED / UNKNOWN × LOCAL / ISOLATED / BROWSER_INTEGRATION / LIVE / REAL_USER_ACCEPTED.

---

## TASK-00 — Current reality & requirements lock

**User outcome:** zna se tačno šta od Miroslavljevih zahteva postoji, gde, i na kom nivou dokaza — bez nagađanja.

**Baseline SHA:** `f33dcce812c655807ee90f06f11a8f772c6bc6c3` (`origin/main`).

### Stanje repozitorijuma i produkcije (PROVEN, 2026-10-22)

| Stavka | Nalaz |
|---|---|
| `origin/main` | `f33dcce8` (Merge PR #51) |
| Lokalni `main` (glavni radni direktorijum) | `f798b820`, **16 lokalnih commitova / 546 iza** `origin/main`; prljavo stablo (obrisani `site/*.html`, izmenjena 128, stotine neprećenih izveštaja). **Ne diran.** Stara lokalna grana iz Z014 perioda (`git cherry`: deo je već u `origin/main` kao drugi SHA). |
| Radna grana ovog sprinta | `night/miroslav-recovery` u izolovanom worktree-u `C:/vindex-miroslav`, od `origin/main`. Bez push-a. |
| Produkcija | `GET https://vindex.rs/health` → `"commit":"f33dcce"` = `origin/main`. **LIVE — PROVEN.** |
| NS007 u produkciji | `POST /api/cron/autonomy` bez tajne → **401** (LIVE — PROVEN). Tabele `autonomy_*` u produkciji: poslednja provera VCR002 (2026-10-12) = ne postoje; danas nije ponovo proverena (nema DB pristupa) → **INFERRED isključeno**. |

### Ulazi u V2 (`frontend-v2-ng/src/`, PROVEN čitanjem koda)

| Posao | V2 modul | Backend |
|---|---|---|
| Nov predmet | `nov-predmet.js`, `nov-predmet-prijem.js` | `/api/intake/ekstrakcija`, `/api/intake/kreiraj`, `/api/conflict-check` |
| Prijem dokumenata | `prijem-predmeta.js` | `/api/smart-intake/documents`, `/jobs/{id}`, `/finalize`, `/review/resolve` → `shared/intake_worker.py`, `uploaded_doc/extractor.py` (OCR) |
| Analiza / hronologija / protivrečnosti | `analiza-predmeta.js`, `predmet.js` | `/api/predmeti/{id}/genome-v2`, `/genome-v2/promene`, `/api/evidence/predmeti/...` |
| Pravno pitanje | `pitanje-predmeta.js` | `/api/pitanje` (`api.py:3879`) — `predmet_dokazi` (20), beleške, istorija + pretraga dokumenata nad svim predmetima kojima korisnik ima pristup, sa pojačanjem tekućeg predmeta |
| Savetnici (strategija) | `agenti-predmeta.js` | `/api/agents/run`, `/run-parallel` (niz isključen u V2) — `routers/multi_agent.py`, agenti `litigation`, `drafting` … |
| Nacrt | `nacrt-predmeta.js` | `/api/podnesak`, `/api/staging/*`, `/api/nacrti/export/docx` |
| Sledeće radnje | `rad-predmeta.js`, `danas.js` | `/api/case-actions/predmeti/{id}` ← `services/case_evolution.py` |
| Law Brain (NS008) | `law-brain.js`, `app.js`, `pripremljeno.js` | `/api/law-brain/*` |
| Proaktivni rad | `pripremljeno.js` | `/api/autonomy/work-items` ← `routers/autonomy.py`, `workers/background_agents.py` |

`routers/strategija.py` (red-team, sudija, kompletna-analiza…) **nema V2 ulaz**. Strateški sadržaj u V2: savetnici (`litigation`), Genome strategija u Analizi (`analiza-predmeta.js:29,184-186`) i Law Brain sinteza (`POST /api/law-brain/predmeti/{id}/sinteza`, `law-brain.js:200`).

### Ograničenja konteksta savetnika (`routers/multi_agent.py:425-821`, PROVEN čitanjem)

- najviše **5** dokumenata, ukupno **12.500** znakova, 2.500 po dokumentu, **5.000** za izričito tražen;
- izbor: traženi (oznaka `DOK-NN`, „dokument br. N“ ili tačan naziv fajla) prvi, zatim **najnoviji po rednom broju**;
- opis rečima („tužba“, „prvi podnesak“) **ne bira** dokument;
- `izvori_predmeta` (ukljuceni / izostavljeni / bez_teksta / trazeni_nisu_dostavljeni / svi_dokumenti_u_celini) vraća server, ne model; `pominje_nedostavljene` označava odgovor koji pominje nepročitan dokument;
- Genome sažetak je u granici poverenja, nije „izvor istine“.
- dokument bez teksta zauzima jedno od 5 mesta (`:698-700`);
- Posledica za spis od 7 dokumenata bez oznaka u pitanju: DOK-01 i DOK-02 **nisu u kontekstu**, ali se to **otkriva** (`izostavljeni`).

### Entitlement (PROVEN iz `migrations/064/065`; produkcione vrednosti UNKNOWN — politike su u bazi)

`ai_pravna_pitanja` = basic · `multi_agent`, `drafting`, `case_dna`, `evidence` = professional. Planirani testovi su LOCAL/ISOLATED i ne zavise od produkcione tabele; negativna kontrola entitlement-a ide kroz `PermissionService.require` sa lažnom politikom.

### Matrica `requirement → workflow → evidence → gap`

| MIR | Workflow (kod) | Postojeći testovi | Najviši dokaz danas | Gap |
|---|---|---|---|---|
| **MIR-01** Case Continuity | Prijem → Smart Intake → worker/OCR → `predmet_dokumenti` → `evidence_write` (tvrdnje sa `dokument_id`) → `case_dna` refresh → `genome-v2` (hronologija sa izvorom, protivrečnosti) | `test_vcr002_t02_ocr_korpus.py` (OCR u prod. Docker slici, CI), `test_vcr002_t03_visedokumentni_predmet.py` (**3** dokumenta), `test_vcr002_rc_fix1_*` (brisanje izvora) | ISOLATED — PROVEN (3 dok.); OCR = ISOLATED u prod. slici | nikad dokazano sa **7** procesnih dokumenata (tužba…zapisnik); stranački navod vs. utvrđeno nije mereno nad tužbom/odgovorom; nema LIVE prijavljenog toka (nema QA naloga) |
| **MIR-02** Case-Grounded Strategy | V2 savetnici → `multi_agent._kontekst_predmeta` → `litigation`; Genome strategija; Law Brain sinteza | `test_qa08_izvori_savetnika.py` (28; 7-dok. predmet, DOK-01 tražen), `test_vcr002_t05/t06` | ISOLATED — PROVEN (izbor izvora i evidencija; model zamenjen) | sadržinski kvalitet strategije nad spisom **nikad meren**; pitanje „uporedi tužbu i zapisnik“ bez oznaka → stariji dokumenti van konteksta (otkriveno, ali nepotpuno zaključivanje) |
| **MIR-03** Case-Grounded Drafting | (a) V2 Nacrt → `/api/podnesak` → staging → approve/reject → DOCX; (b) V2 savetnik „Pisanje podnesaka“ (agent `drafting`, `/api/agents/run` + `predmet_id`) | `test_sprint6c1_drafting_authorization.py`, `test_sprint6c2_podnesak_binding.py`, `test_phoenix_mission_010_drafting_rag_grounding.py`, `test_drafting_*`, `test_qa08_*` | ISOLATED — PROVEN za vlasništvo, RAG zakona, staging; (b) za izbor izvora | **(a) nema determinističkog oslonca na spis**: handler (`routers/drafting.py:934-1142`) ne čita `predmet_dokumenti`/`predmet_dokazi`/`case_dna`; činjenice dolaze iz korisnikovog `opis`. Jedini dodir sa spisom je usputna semantička pretraga `retrieve_documents` (`app/services/retrieve.py:1932-1938, 2407-2476`) nad vektorima vlasnika (+0,05 za tekući predmet), vođena `opis`-om; posle `docs[:4]` (`shared/drafting_grounding.py:24`) delovi spisa obično otpadaju iza zakona, a **mogu doći i iz drugih predmeta kojima korisnik ima pristup (`shared/rag_acl.dozvoljeni_predmeti`, uklj. delegirane)** (rizik ukrštanja predmeta u podnesku). (b) je uzemljen u spis (5 dok., evidencija izvora), ali je van šablona, staging-a i DOCX-a. Gap: kanonski Nacrt tok nije uzemljen u spis; uzemljen tok nije u pregledu/izvozu. `_recent_generation_exists` = prozor od 30 s (drugi `opis` u 30 s vraća stari nacrt). |
| **MIR-04** Corporate Workflow | ugovori: `/api/nacrt`, `/api/analiza`, `/api/sazmi` (`routers/drafting.py`), Smart Intake | razni | UNKNOWN za Miroslavljeve procese | konkretni procesi nisu definisani → očekivano `BLOCKED_REQUIREMENTS_DETAIL` |
| **MIR-05** Bounded Proactivity | (a) Case Evolution: novi dokument → događaj → `case_actions` (Rule 6 itd.) → V2 Rad/Danas; (b) NS007: `HEARING_PREP`, `PRECEDENT_IMPACT` izvršioci | `test_case_evolution.py`, `test_phoenix_mission_007_*`, `test_ns007_*` (163 nad pravim PG 17 u VCR002 — **preneto, u MIR001 nije ponovo pokrenuto**) | (a) LIVE delimično (TASK9: dokaz→događaj→akcija — **preneto, u MIR001 nije ponovo provereno**); (b) ISOLATED — PROVEN, prod. BLOCKED_AUTHORITY | **`CASE_CHANGE_BRIEF` NEMA izvršioca**: dozvoljen u `routers/autonomy.py:120`, CHECK u migraciji 136 i labela u `pripremljeno.js`, ali `workers/background_agents._agent_modules()` registruje samo `court_portal_watcher`, `precedents_radar`, `hearing_prep`. Upravo Miroslavljev slučaj („promena → interni pregled bez zahteva“) nema put. |

**Miroslavljev izvor:** autentični tekst je u ovom masterpromptu (founder input, 2026-10-22). VCR002 `BLOCKED_REQUIREMENTS_SOURCE` time je razrešen za MIR-01…05; stari `M-01…M-07` se ne koriste.

**Changed files:** samo ovaj ledger. **Root cause / fix:** n/a (read-only).

**Positive/negative tests executed:** read-only komande (`git rev-list`, `git cherry`, `curl /health`, `curl -X POST /api/cron/autonomy`, `grep`/`sed` nad kodom).

**Evidence level:** gore, po stavci.

**Independent reviewer finding (GATE-00, 1. prolaz): FAIL** — (1) tvrdnja „`/api/podnesak` ne čita NIŠTA iz predmeta“ netačna: postoji usputna semantička pretraga vlasnikovih vektora sa pojačanjem tekućeg predmeta (`retrieve.py:1932-1938, 2407-2476`), obično odsečena sa `[:4]`, i može povući delove drugih predmeta; (2) izostavljen uzemljen V2 put savetnika „Pisanje podnesaka“; (3) „strategija isključivo preko savetnika“ prenaglašeno (Genome strategija, Law Brain); (4) TASK9/VCR002 dokazi moraju biti označeni kao preneti. Potvrđeno: limiti QA-08, nepostojanje izvršioca `CASE_CHANGE_BRIEF`, `/api/pitanje` izvori, tarife iz 064, T03 = 3 dokumenta. Sve četiri stavke ispravljene u matrici iznad.

**GATE-00, 2. prolaz: FAIL** — oznake „preneto“ u MIR-05 nisu bile upisane; 5 sitnih netačnosti (pozivaoci Law Brain-a, formulacija `/api/pitanje`, `rag_acl`, agent `drafting`, opseg linija). **3. prolaz: PASS** — sve ispravke potvrđene uz `file:line`.

**Remaining limitations:** produkcione politike entitlement-a i postojanje tabela autonomije danas nisu čitani iz baze (nema DB pristupa); prijavljen produkcioni tok i dalje bez QA naloga.

**Commit SHA:** vidi `git log` (commit `docs(mir001): TASK-00 ...`)

**GATE-00: PASS**

---

## TASK-01 — Miroslav Golden Case

**User outcome:** postoji proverljiv sintetički sudski spis kojim se Miroslavljev tok može dokazati ili oboriti.

**Baseline SHA:** `c9ba6abb`.

**Changed files:** `tests/mir001_golden_case.py` (korpus), `tests/test_mir001_t01_golden_case.py` (samoprovera korpusa).

**Sadržaj:** P 9901/2026, Alfa Fiktiv DOO protiv Beta Primer Gradnja DOO (sve SINTETICKI). DOK-01 tužba · DOK-02 odgovor · DOK-03 podnesak tužioca · DOK-04 podnesak tuženog · **DOK-05 nalaz veštaka (sken bez tekstualnog sloja)** · DOK-06 izjašnjenje na nalaz · DOK-07 zapisnik · DOK-08 kasnija dopuna nalaza (nov rok). Očekivanja: navodi N-01…N-15 sa stranom, protivrečnosti K-01 (prijem reklamacije 08.09 vs 20.11.2025) i K-02 (paneli 10.08 vs 10.10.2025), hronologija čiji prvi događaj potiče iz DOK-07 (≠ redosled čitanja), stare činjenice N-02/N-05 van pet najnovijih, prelomna N-09/N-10 samo u skenu, nedostupno (dnevnik jun 2025, ime odgovornog izvođača; definisan odgovor i posle DOK-08), povučen N-07 (N-13) i zamenjen zahtev N-03→N-15, brisanje izvora DOK-03, rok DOK-08 = 2026-10-28 (izračunljiv iz teksta), zamrznuto `SADA`, korisnik B sa markerom `SIFRA-B-77Q`.

**Positive tests:** `pytest tests/test_mir001_t01_golden_case.py` → **21 passed, 1 skipped** (bez Tesseract-a); **22 passed** sa lokalnim Tesseract 5.5.3 `srp+srp_latn+eng` (conda okruženje u scratchpad-u) — stvaran `uploaded_doc.extractor` iz skena vraća N-09 i N-10, 9/10 redova tačno, pouzdanost 0,91.

**Negative/adversarial:** 5/5 mutacija korpusa uhvaćeno (protivrečnost nestala, sken postao digitalan, stara činjenica među najnovijih 5, nedostupno postalo dostupno, datum bez izvora); determinizam = isti sha256 svih 9 PDF-ova u dva odvojena procesa.

**Evidence level:** korpus — PROVEN, LOCAL. OCR skena — PROVEN, LOCAL (Tesseract 5.5.3, conda); produkciona slika = Debian Tesseract — za taj sken **nije** posmatrano (INFERRED ekvivalentno; T02 VCR002 dokazao isti put u produkcionoj slici u CI-ju).

**Independent reviewer finding:** 1. prolaz **FAIL** — P1 hronologija = redosled dokumenata (sistem koji samo čita redom bi prošao); P2 „nedostupno“ delimično dostupno posle DOK-08; P3 rok računat od datuma dokumenta, vezan za kalendar; P4 determinizam meren u jednom procesu (prazan test); P5 zamenjen tužbeni zahtev nije očekivanje; P6 slabe provere odsustva. 2. prolaz: P1/P3/P4/P5 **PASS**; uočeno da izmena testa za P2/P6 nije bila upisana (moja tiha greška zamene). 3. prolaz posle upisa: **PASS**. Preostalo (neblokirajuće): provera imenovanih osoba hvata samo prezime „Izmisljeni“; bajtovi su reproduktivni za fiksne verzije reportlab/PyMuPDF.

**Remaining limitations:** jedan skeniran dokument (latinica); ćirilični sken je pokriven u VCR002 T02.

**GATE-01: PASS**

---

## TASK-02 — Complete case intake (MIR-01)

**User outcome:** advokat u V2 otvori predmet, izabere ceo spis (7 fajlova, jedan skeniran) jednim otpremanjem i svi dokumenti završe u tom predmetu sa pročitanim tekstom.

**Baseline SHA:** `b58d604a`.

**Changed files:** samo testovi — `tests/test_mir001_t02_prijem_spisa.py`, `frontend-v2-ng/tests/live-mir001-spis-e2e.mjs`. **Kod proizvoda nije menjan** (svi kriterijumi prošli na postojećem kodu).

**Root cause / minimal fix:** n/a.

**Positive tests executed:**
- `pytest tests/test_mir001_t02_prijem_spisa.py` (stvarne rute, stvaran intake worker, **stvaran Tesseract 5.5.3** srp+srp_latn+eng, `VINDEX_REQUIRE_OCR=1`) → **5 passed**.
- `node tests/live-mir001-spis-e2e.mjs` (Chromium → pravi V2 `/app` → pravi `api.app` iz `tests/osb003_solo_server.py`, stvaran OCR) → **17/17 PASS**: predmet kroz formu „Nov predmet“; 7 fajlova u jednom `FormData` zahtevu; 7× „Prikačeno ovom predmetu“; baza `[7]` u jednom predmetu; sken nosi „tekst pročitan OCR-om“; posle reload-a 7 dokumenata i OCR tekst nalaza (N-09, N-10) vidljiv u predmetu.

**Negative/adversarial tests executed:** oštećen PDF u istom predmetu → posao `failed`, `NIJE_PRIKACENO`, poruka „nije ispravan PDF“, finalize **409**, predmet i dalje 7; isti bajtovi ponovo → isti neuspeli posao. Ponovljeno otpremanje istih 7 fajlova i ponovljeno prikačivanje → isti poslovi, bez novih redova (`predmet_dokumenti`, `intake_jobs`, `predmet_dokazi`). Korisnik B: detalj, lista, preview, čitanje/finalize poslova A, ubacivanje B dokumenta u predmet A → 403/404; reviewer dodatno: preuzimanje/brisanje dokumenta A, promena vrste, ispravka entiteta, resolve/reject, `finalize-batch` → sve 404. **Mutacije (binarni harness, bajt-identičan povratak):** uklonjen `uploaded_by` filter u `GET /jobs/{id}` → uhvaćeno; `_ocr_image` vraća prazan tekst → uhvaćeno.

**Regression tests executed:** `test_mir001_t01`, `test_mir001_t02`, `test_osb002_solo_tok`, `test_vcr002_t02_ocr_korpus`, `test_vcr002_t03_visedokumentni_predmet`, `test_ns005_t14_smart_intake` (sa OCR-om) → **65 passed**.

**Evidence level:** prijem, prikačivanje, identitet, izolacija, ponavljanje — **PROVEN, BROWSER_INTEGRATION** (baza u memoriji, ne Postgres/RLS). OCR — **PROVEN, LOCAL** (stvaran Tesseract na istom putu ekstrakcije, Windows/conda); OCR u Debian produkcionoj slici je dokazan samo drugim korpusima (VCR002 T02) — za ovaj sken **nije** posmatran. LIVE — **NOT_RUN** (nema QA naloga).

**Independent reviewer finding:** **PASS uz napomene.** Suženo po nalazu: (1) „produkciono-ekvivalentan OCR“ se ne tvrdi; sken je čist (18 pt, 200 dpi, ASCII) — lak slučaj; (2) neuspeh je dokazan na API-ju, **UI prikaz neuspeha nije izvršen u ovom browser toku** (pokriva ga postojeći `live-prijem.mjs` nad fixture-om); (3) **vrsta dokumenta je simulirana** u harness-u (svih 7 = „Dopis“) — ništa o tačnosti klasifikacije vrste se ne tvrdi; (4) test oštećenog fajla imao je uslovnu granu i različite bajtove pri ponavljanju → **ispravljeno** (isti bajtovi, bez uslova), 5 passed; (5) browser test nije u CI-ju (ručno pokretanje); svih 5 Python testova se preskače bez Tesseract-a.

**Remaining limitations:** klasifikacija vrste dokumenta (tužba/odgovor/nalaz…) nije merena; neidealan sken (šum, iskošenost, ćirilica) nije meren u ovom korpusu; harness korisnički ID nije UUID (AI provenance posla se ne beleži u harness-u).

**GATE-02: PASS**

---

## TASK-03 — Case continuity and source integrity (MIR-01)

**User outcome:** iz celog spisa (7 dokumenata) advokat vidi ispravan vremenski sled sa izvorom, šta je ko tvrdio, i obe sporne tačke između stranaka — bez lažne saglasnosti i bez navoda stranke prikazanog kao utvrđena činjenica.

**Baseline SHA:** `5b3a56ba`.

**Root cause (reprodukovan nad Golden Case-om):** Genome osvežavanje modelu daje najviše **20** živih tvrdnji (`shared/claim_catalog.MAKS_TVRDNJI`), birano po UUID-u (proizvoljno). Spis od 7 dokumenata ima do 35 tvrdnji (≤ 5 po dokumentu). Posledice izmerene na postojećem kodu: tvrdnje tužbe i odgovora (N-01, N-04, N-06) nikad ne stižu do modela → protivrečnost **K-01 nikad ne nastaje**, a **K-02 se zatvara kao `NOT_OBSERVED`** iako nije razrešena (`services/v2_observation.py`: `kompletno = not odbijeni`), dok `genome-v2` tvrdi `kompletnost: COMPLETE`. Isti lažni „kompletno“ nastaje i kad čitanje tvrdnji padne (`[]`). U V2 su navodi stranaka prikazani pod naslovom „Ključne činjenice“, obe strane protivrečnosti bez oznake.

**Minimal fix:**
- `shared/claim_catalog.py`: granica 20 → **60** (≈ 6.000 znakova uz 60.000 znakova dokumenata; najviše ≈ 3–4k tokena po osvežavanju);
- `routers/case_dna.py`: `_fetch_dokazi_kontekst` vraća `_Tvrdnje` sa `potpune=False` kad je lista odsečena (`limit+1`) ili nepročitana; `_extract_genome` tada beleži `_tvrdnje_van_analize`; oba poziva `upisi_v2_opazanje` prosleđuju `tvrdnje_potpune`;
- `services/v2_observation.py`: `kompletno = not odbijeni and tvrdnje_potpune` — sporna tačka čije tvrdnje model nije video se **ne zatvara**;
- `shared/genome_contract.py`: tada `kompletnost = PARTIAL` i stavka nesigurnosti `tvrdnje_izostavljene` (razlog nije prećutan);
- V2 (`frontend-v2-ng/index.html`, `src/analiza-predmeta.js`): naslov „Ključni navodi iz dokumenata“; navod u aktivnoj protivrečnosti nosi „SPORNO — <sporna tačka>“ i ide prvi; preko 12 navoda najava „Prikazano 12 od N“.

**Changed files:** gore + `tests/test_mir001_t03_kontinuitet.py` (nov), `tests/test_mir001_t02_prijem_spisa.py` (izdvojen `primi_spis`), `frontend-v2-ng/tests/live-analiza.mjs` (+3 provere, dijagnostika jedne postojeće).

**Positive tests executed:** `test_mir001_t03_kontinuitet.py` (stvarne rute, worker, OCR, dispečer, Genome osvežavanje, V2 projekcija; zamenjeni samo modeli — klasifikator i Genome čitaju STVARAN ulaz i navode samo ono što je u njemu) → **9 passed**: hronologija 9 događaja tačnim redom sa tačnim `dokument_id` (prvi iz DOK-07); 15 ključnih navoda sa po jednim izvorom, poreklo `SOURCE_FACT`; K-01 i K-02 aktivne, odvojene, učesnici iz dokumenata suprotnih strana; `COMPLETE` uz 35 tvrdnji. `live-analiza.mjs` (stvaran backend fixture) → **46/46**.

**Negative/adversarial tests executed:** dva osvežavanja (ručno) → isti ID-jevi protivrečnosti, isti brojevi redova u 4 tabele; odsečen katalog (granica 20) i kroz ručno osvežavanje i kroz događaj `DocumentAccepted` → `PARTIAL` + razlog, obe sporne tačke i dalje aktivne, ništa zatvoreno; greška čitanja tvrdnji → isto; brisanje DOK-03 (B dobija 404, A 200) → N-06/N-07 povučeni, K-02 nije aktivna, K-01 ostaje, DOK-03 nije u promptu ni u hronologiji/navodima; korisnik B → 403/404 na `genome-v2`, `/promene`, `/evidence`, refresh, bez curenja teksta. **Mutacije (binarni harness, bajt-identičan povratak): 7/7 backend** (granica 20, `kompletno` bez potpunosti, `COMPLETE` uprkos odsecanju, greška = potpuno, odsecanje bez oznake, svaki od dva poziva bez prosleđivanja) **+ 1 nesigurnost + 3/3 UI** (bez „SPORNO“, bez redosleda, stari naslov) — sve uhvaćene.

**Regression tests executed:** 138 Python fajlova koji diraju `case_dna`/`v2_observation`/`claim_catalog`/`genome_contract`/`v2_contradiction` → **2726 passed, 0 failed** (dva puta, pre i posle dopune). Frontend: `verify`, `verify:demo-otisak`, `verify:live-matter` 56/56, `verify:live-matrix` 152/152, `e2e:solo-tok` 23/23, `e2e:dokaz-zastarelost` 23/23. `live-analiza`: 1 pad u 28 pokretanja na postojećoj proveri „Izvor: Dostavnica“ (klik u odeljku protivrečnosti koji izmena ne dira; reviewer: trka u brojanju preview zahteva) — dodata dijagnostika.

**Evidence level:** PROVEN, ISOLATED (stvaran backend nad bazom u memoriji; modeli zamenjeni) + BROWSER_INTEGRATION (UI nad stvarnim backend fixture-om). Razumevanje spisa stvarnim modelom: **NOT_RUN** (TASK-04/05).

**Independent reviewer finding:** 1. prolaz **PASS** uz obaveze: PARTIAL bez razloga; V2 „Ključne činjenice“ prikazuje navode stranaka kao činjenice bez „SPORNO“ (postojeći nedostatak, u opsegu kriterijuma); obelodaniti ograničenja. Sve ispravljeno; 2. prolaz **PASS** (ključ `tvrdnja_id` = `stavka.id` iz iste funkcije; tekst kroz `textContent`; isprekidani pad nije posledica izmene).

**Remaining limitations (obelodanjeno, NIJE rešeno):**
- **LIM-MIR-03-1 (najveće za MIR-01):** klasifikator dokumenta vidi samo **prvih 1.500 znakova** (`routers/evidence.py:98`) i čuva **najviše 5 tvrdnji po dokumentu** (`:285`). U stvarnoj višestraničnoj tužbi navodi posle prve strane ne postaju tvrdnje, pa ni njihove protivrečnosti ne mogu nastati. Golden Case dokumenti su kratki (278–636 znakova) i zamena modela stavlja ključne navode prve — ovo testovi **ne mere**.
- **LIM-MIR-03-2:** predmet sa > 60 živih tvrdnji (≈ > 12 dokumenata) ostaje trajno `PARTIAL`; vidljiv podskup bira UUID; protivrečnosti van njega ne nastaju, a postojeće se ne zatvaraju (bezbedno, ali bez automatskog zatvaranja).
- **LIM-MIR-03-3:** sporne tačke „za pregled“ (REVIEW_REQUIRED) nisu označene „SPORNO“ u listi navoda (u praksi se ne perzistiraju — A013 GAP-2); navod porekla AI_ANALYSIS ne ulazi u listu navoda (vidljiv u odeljku protivrečnosti).
- Test sa granicom 20 hvata mutaciju potpunosti samo u delu pokretanja (zavisi od UUID-a); pouzdano je hvata test greške čitanja.
- Vrsta dokumenta (tužba/odgovor…) i dalje simulirana („Dopis“); strana se vidi iz naziva izvornog dokumenta.

**GATE-03: PASS**

---

## TASK-04 — Cross-document AI reasoning (MIR-01, MIR-02)

**User outcome:** Miroslav postavi pitanje savetniku nad celim spisom (bez oznaka DOK-NN) i dobije odgovor iz pravih dokumenata, sa obe strane spora, bez izmišljanja nedostavljenog.

**Baseline SHA:** `4b6c19aa`.

**Root cause (reprodukovan nad TAČNIM produkcionim promptom i stvarnim modelom):**
1. Savetnik je dobijao najviše **5** dokumenata (najnoviji, osim izričito traženih oznakom/nazivom fajla). U spisu od 7 tužba (DOK-01) i odgovor na tužbu (DOK-02) **nikad** nisu stizali do modela za pitanje bez oznake. Stvaran gpt-4o je tada na „garantni rok po ugovoru“ odgovarao opštim zakonom („dve godine“) umesto „pet godina, čl. 9 Ugovora 12/2024“, propuštao iznos iz tužbe, i izneo „tuženi je primio reklamaciju 08.09.2025“ kao činjenicu.
2. I sa svim dokumentima, model je na pravnu posledicu (P6) zaključivao na navodu jedne strane: savetnik nije dobijao sporne tačke koje `/api/pitanje` već dobija (VCR002 RC FIX 3).

**Minimal fix (`routers/multi_agent.py`):** (1) do **12** dokumenata u ISTOM budžetu teksta dokumenata (12.500): netražen dokument `min(2.500, preostalo/preostalih)`, tražen do 5.000, isečak < 500 se ne šalje (dokument prijavljen kao izostavljen); razlog „premašen budžet teksta“ razlikovan od „ograničenja broja“; (2) `_sporne_tacke_za_savetnika` — isti učitavač (`ucitaj_v2_kontradikcije_za_prikaz`) i isti formater (`kontekst_tvrdnji`) kao `/api/pitanje`, samo navodi iz aktivnih/na-pregledu spornih tačaka (≤ 10), u granici poverenja; greška čitanja → izričito „NEPOZNATO“. Važi za `/run`, `/run-parallel`, `/pipeline`. Nova arhitektura pretrage, vektorska baza ni rast budžeta teksta: nema.

**Changed files:** `routers/multi_agent.py`; testovi `tests/test_mir001_t04_savetnik_spis.py` (nov), `tests/test_qa08_izvori_savetnika.py` (scenariji izostavljanja pomereni sa 7 na 14/16/20 dokumenata, +5 novih testova), `tests/test_qa06_naziv_nedostavljenog.py` i `tests/test_genome_granica_poverenja.py` (isto pomeranje); dokaz `docs/v2-execution/MIR001_T04_STVARNI_MODEL.json`.

**Positive tests executed:** `test_mir001_t04_savetnik_spis.py` (stvaran put prijema + OCR + Genome/protivrečnosti + `/api/agents/run`) → **3 passed**: za svih 7 pitanja model dobija svih 7 dokumenata u celini, stare i nove navode obe strane; P6 nosi „SPORNE TAČKE“ sa obe strane K-01 i K-02 označene SPORNO; P7 prijavljuje DOK-09 kao „ne postoji“. **Stvaran model (3 uzorka × 7 pitanja, `MIR001_T04_STVARNI_MODEL.json`), pravilo prisustva:** pre ispravke **5/18** (P1–P6), posle **21/21**. Čitanjem (reviewer): P4 i P6 3/3 iznose obe strane kao navode uz povratnicu PK-4471; P5 3/3 iskreno „dnevnik nije dostavljen“; P7 3/3 ne izmišlja DOK-09.

**Negative/adversarial tests executed:** greška čitanja spornih tačaka → „NEPOZNATO“, bez SPORNO; korisnik B ne dobija spis A kroz savetnika; ≤ 5 dugih dokumenata bez traženja = isto kao ranije (2.500 svaki); 7 dugih = svaki delimično, zbir ≤ 12.500; premali preostali deo → izostavljen, ne isečak; tražen-a-izostavljen-zbog-budžeta nosi tačan razlog; broj upita: + tačno 1 (`predmet_issues`) kad nema spornih tačaka. **Mutacije 6/6** (granica 5, bez pravednog deljenja, bez donje granice, bez spornih tačaka, sporne bez oznake, greška tiho prazna).

**Regression tests executed:** svi Python testovi koji diraju `multi_agent`/`agents/run`/`_kontekst_predmeta` (17 fajlova) → **439 passed, 3 skipped**; V2 `verify:live-agenti` 52/52, `e2e:savetnici` 16/16.

**Evidence level:** izbor izvora i sadržaj poruke modelu — PROVEN, ISOLATED. Ponašanje stvarnog modela — PROVEN na 3 uzorka po pitanju nad **kratkim sintetičkim** dokumentima (LOCAL, stvaran gpt-4o); pouzdanost nad dugim stvarnim spisima — **UNKNOWN**. LIVE / REAL_USER — NOT_RUN.

**Independent reviewer finding:** 1. prolaz **PASS uz uslove**: netačna tvrdnja „≤ 5 dokumenata isto“ (nije kad je dokument tražen: 5.000 + 4 × 1.875) i „nikad više znakova“ (budžet teksta isti, ali poruka raste ≈ +36% tokena u Golden Case-u: zaglavlja + sporne tačke); pogrešan razlog „ograničenje 12 dokumenata“ kad je uzrok budžet; test broja upita nije brojao nove tabele; jedan uzorak po pitanju nije dovoljan. Sve ispravljeno; 2. prolaz **PASS**, uz napomenu da je 21/21 samo „prisustvo“.

**Remaining limitations / dug (NIJE rešeno):**
- **DEBT-MIR-04-1:** navodi u bloku spornih tačaka nemaju oznaku dokumenta i mogu doneti tekst iz dokumenta prijavljenog kao nedostavljen (spis > 12 dok. ili preko budžeta); `odgovor_pominje_nedostavljene` to ne hvata.
- **DEBT-MIR-04-2 (ponašanje modela):** P1 2/3 iznosi „pet godina“ kao ugovoreno (navod tužioca; ugovor nije u spisu); P7 „veštak utvrdio“; P2 izračunat rok 30.07.2026 kao činjenica; P3 1/3 pripisuje zahtev od 600.000 tužbi (dodat u DOK-03); P6 1/3 citira pogrešan član (prodaja) — čuvar citata ga označava NEPROVERENI; prozni pravni iskazi bez citata nisu hvatani; čuvar citata označava i „čl. 9 Ugovora“ (šum).
- **LIM-MIR-04-3:** u širokom spisu dugačak dokument dobija kraći početni isečak (≈ 1.785 umesto 2.500 znakova pri 7 dokumenata) — za stvarnu tužbu to je pretežno zaglavlje; obeleženo DELIMIČNO, ali korist nad dugim dokumentima nije merena.
- **LIM-MIR-04-4:** savetnik ne koristi pretragu po relevantnosti (početni isečci, ne delovi relevantni za pitanje); pitanje čiji je odgovor duboko u dugom dokumentu i dalje zavisi od izričitog traženja dokumenta.
- Svaki poziv savetnika: +1 upit (+3 kad postoje sporne tačke); `/pipeline` po koraku.

**GATE-04: PASS**

---

## TASK-05 — Case-grounded legal strategy (MIR-02)

**User outcome:** Miroslav traži strategiju od postojećeg savetnika „Parnična strategija“ i dobija radni materijal iz konkretnog spisa: procesno stanje, stavove stranaka, sporno/potkrepljeno, nalaz veštaka, nedostajuće dokaze, opcije, sledeće korake — i vidi šta novi dokument menja.

**Baseline SHA:** `b549b9fc`.

**Root cause (merenjem stvarnog modela nad tačnim produkcionim promptom):** okvir savetnika „litigation“ je kritika protivničkog advokata bez ijednog pravila za rad sa spisom: strategija nije navodila izvore, nije počinjala od procesnog stanja, posle novog dokumenta nije govorila šta se menja, kontekst nije imao današnji datum (istekli rokovi kao tekući), a kontekst je nosio „Snaga predmeta: 50%“ uprkos zabrani procenata.

**Minimal fix (`routers/multi_agent.py`, bez novog agenta):** blok „KADA SU DOSTAVLJENI DOKUMENTI PREDMETA (spis)“ u postojećem promptu (izvor DOK-NN uz svaku činjenicu; navod/nalaz ≠ utvrđeno, „veštak u nalazu navodi“; proveri da li je dokaz već u spisu; rokovi prema današnjem datumu; prva sekcija „## 0. PROCESNO STANJE“; stavka „Šta menja <najnoviji dokument>“; pomenut a nedostavljen dokaz = nedostajući); serverski upisan „Današnji datum“ na početku konteksta savetnika; procenat snage uklonjen iz konteksta savetnika.

**Changed files:** `routers/multi_agent.py`; `tests/test_mir001_t05_strategija.py` (nov); `tests/test_genome_granica_poverenja.py` (više ne očekuje procenat u kontekstu); dokaz `docs/v2-execution/MIR001_T05_STVARNI_MODEL.json`.

**Positive tests executed:** `test_mir001_t05_strategija.py` → **2 passed**: strategija dobija svih 15 ključnih navoda svih 7 dokumenata, sporne tačke, današnji datum, bez procenta; posle STVARNOG prijema DOK-08 poruka sadrži DOK-08 i njegov rok; sva pravila u sistemskom promptu. **Stvaran model, stroga merila upisana pre pokretanja, 5 uzoraka po uslovu:** osnova (originalni prompt) 30/66 · prva ispravka 35/66 · konačno 75/110 po skripti — **posle ručne ispravke reviewer-a manje** (vidi dole). Čitanjem (reviewer): 10/10 vezuje činjenice za DOK-NN, obe strane datuma, sledeće ročište; 0/10 procenata ili citata zakona/prakse; navodi stranaka korektno kao navodi; 5/5 „Šta menja DOK-08“ sa rokom od 8 dana.

**Negative/adversarial tests executed:** korisnik ispod tarife (`multi_agent` = professional) → **403** na `/run` i `/run-parallel`, **0 poziva modela, 0 naplata**; mutacije pravila (izvor, navod≠činjenica, procesno stanje) uhvaćene determinističkim testom.

**Regression tests executed:** svi testovi savetnika → **439 passed, 5 skipped**; `test_genome_granica_poverenja` + T05 → 25 passed; V2 `verify:live-agenti` 52/52, `e2e:savetnici` 16/16 (ponovljeno na konačnom kodu `d5c7a6c0`).

**Evidence level:** sadržaj poruke modelu, tarifa, ACL — PROVEN, ISOLATED. Ponašanje modela — „posmatrano u k/5 uzoraka“, jedan sintetički predmet, temperatura 0,35 (LOCAL, stvaran gpt-4o); **nije stopa pouzdanosti**.

**Independent reviewer finding:** 1. prolaz **FAIL** (sadržaj: „veštak je utvrdio“ 6/6, PK-4471 ignorisan, nalaz o dnevniku okrenut, istekao rok kao tekući, „šta menja“ 0/6, procenat u kontekstu; merila mere poslušnost formatu, R3 proširen posle uvida). 2. prolaz **FAIL samo zbog netačnih ocena**: moja merila su imala slepe tačke — ispravljeno: **R13 3/5** (ne 5/5), **R10 8/10** (ne 10/10), **R9 ispravno 1/10** (dva „prolaza“ su preporuka da se povratnica PRIBAVI). Uz ovaj zapis: **PASS**.

**Remaining limitations (ponašanje modela, izmereno, NIJE rešeno):**
- **DEBT-MIR-05-1:** posle DOK-08 nalaz „dnevnik nema upisa o probi vodonepropusnosti“ pročitan kao **protiv** klijenta u **2/5**.
- **DEBT-MIR-05-2:** povratnica PK-4471 (DOK-03) ignorisana i savetovano njeno „pribavljanje“ u ≈ **9/10**; netačno „nedostaje dokaz o datumu prijema“ u **2/10**.
- **DEBT-MIR-05-3:** nalog od 15 dana od 15.07.2026 nije označen kao istekao u **10/10** (iako je današnji datum u kontekstu); rok 28.10.2026 izračunat u **2/5**.
- „veštak potvrđuje“ posle DOK-08 — reviewer: odbranjivo (DOK-08: „ostaje pri nalazu“).
- Sistemski prompt savetnika i dalje sadrži tvrdo upisane članove ZPP (stari rizik, nije TASK-05; čuvar citata označava nepotvrđene).
- Merila prisustva/regex imaju slepe tačke; konačna presuda je ručno čitanje.

**GATE-05: PASS** (uz ispravljene ocene i dug iznad)

---

## TASK-06 — Case-grounded drafting (MIR-03)

**User outcome:** iz aktuelnog spisa Miroslav dobija nacrt podneska (npr. izjašnjenje na nalaz veštaka) koji ide na njegov pregled u V2 kartici Nacrt: izmena → odobri/odbij → DOCX; ništa se ne šalje sudu.

**Baseline SHA:** `d0862d00`.

**Root cause:** (1) šablonski `/api/podnesak` nema determinističkog oslonca na spis i ima zatvoren spisak od 12 vrsta (tužbe, žalbe, predlozi) — **nema vrste za podnesak u toku postupka** (izjašnjenje na nalaz); (2) uzemljen put (savetnik „Pisanje podnesaka“, posle TASK-04 ceo spis + sporne tačke) nije ulazio u pregled/odobravanje/DOCX.

**Minimal fix:**
- `routers/multi_agent.py`: rezultat savetnika `drafting` sa potvrđenim predmetom ide u **postojeći** pregled nacrta (`_stage_draft_for_review`, vrsta `nacrt_iz_spisa`) uz serversku napomenu „PROVERA PRE UPOTREBE“: neprovereni pravni citati (postojeći čuvar), nepročitani/delimični dokumenti, tražen-a-nedostavljen dokument, i **odluke suda i rokovi iz spisa** sa oznakom dokumenta i današnjim datumom (deterministički, bez modela; interno, ne ide u API ni u prompt); pravila za rad sa spisom u postojećem promptu (činjenice samo iz dokumenata uz DOK-NN, `[PROVERITI: …]`, sporno ostaje sporno, „veštak u nalazu navodi“, bez nepotvrđenih članova, procesno stanje).
- `routers/drafting.py`: odobren `nacrt_iz_spisa` **nikad** ne ulazi u bazu znanja kancelarije ni u dokumente predmeta (ni odobravanjem iznad praga, ni ponovnim upisom: bez dugmeta, ruta 409 pre preuzimanja) — AI tekst ne postaje „izvor“ za dalju analizu.
- `frontend-v2-ng/src/nacrt-predmeta.js`: poruka za taj ishod odobravanja.

**Changed files:** gore + `tests/test_mir001_t06_nacrt_iz_spisa.py` (nov); dokaz `docs/v2-execution/MIR001_T06_STVARNI_MODEL.json`.

**Positive tests executed:** `test_mir001_t06_nacrt_iz_spisa.py` → **6 passed** (5 uzastopnih i 3 nasumična redosleda stabilno; zadatak upisa se hvata i izvršava deterministički): nacrt iz aktuelnog spisa → staging `pending` sa napomenom (`čl. 999 ZOO` neproveren; „DOK-07: Sud prihvata predlog za dopunu vestacenja.“, nalog sa rokom, ročište) → V2 lista → izmena → odobren je **izmenjeni** tekst → DOCX sadrži izmenjen tekst; odobren nacrt iz spisa sa ocenom 0,95 → bez upisa u znanje i dokumente; ponovni upis 409.

**Negative/adversarial tests executed:** odbijen nacrt nije odobren ni kasnijim odobravanjem; korisnik B ne vidi ni ne odobrava; bez predmeta / drugi savetnik / tuđ predmet → **nijedan upis nije ni zakazan**; nijedna spoljna veza (nema slanja); obrisan DOK-06 nije u kontekstu i u napomeni stoji „Tražen u zadatku, a NIJE dostavljen: DOK-06“. **Mutacije 10/10, stabilno** (bez pregleda, bez napomene, svaki savetnik, bez vlasništva, bez [PROVERITI], bez odluka suda, bez traženog-nedostavljenog, promocija pri odobravanju, dugme ponovnog upisa, ruta ponovnog upisa).

**Regression tests executed:** 86 fajlova (nacrti, staging, ponovni upis, trka odobravanja, savetnici) → **2126 passed, 0 failed**; V2 `verify:live-nacrt` 51/51, `verify:live-agenti` 52/52, `e2e:savetnici` 16/16, `e2e:solo-tok` 23/23.

**Evidence level:** tok nacrt → pregled → izmena → odluka → DOCX — PROVEN, ISOLATED (rute, baza u memoriji). Sadržaj stvarnog modela — posmatrano u k/5 (2 kruga po 5 uzoraka, jedan sintetički predmet). LIVE — NOT_RUN.

**Independent reviewer finding:** 1. prolaz **FAIL**: nacrti ne koriste aktuelno procesno stanje (4/5 i 3/5 traže odbijanje dopune koju je sud već prihvatio); testovi nedeterministički (pozadinski zadatak se gasi u harness-u — moji „5 passed“ i mutacije nisu bili pouzdani); napomena bez traženog-nedostavljenog i bez signala procesnog stanja; odobren AI nacrt može postati dokument predmeta i znanje kancelarije. 2. prolaz **FAIL**: zaštita od upisa zaobiđena kroz ponovni upis (dokazano probom). 3. prolaz **PASS**.

**Remaining limitations (izmereno, NIJE rešeno — obavezan ljudski pregled; napomena ukazuje na odluke suda):**
- **DEBT-MIR-06-1 (ponašanje modela):** zastareo procesni predlog (traži odbijanje već prihvaćene dopune) **4/5** (krug 1) i **3/5** (krug 2); pravilo u promptu nije izmerljivo pomoglo. Nijedan nacrt ne primećuje da je rok od 15 dana (od 15.07.2026) istekao.
- **DEBT-MIR-06-2:** nalaz veštaka prikazan kao utvrđen („utvrdio“) **10/10**; pojedini iskazi bez izvora; 10/10 osporava tvrdnju o neizvršenom uvidu u dnevnik bez izvora.
- **LIM-MIR-06-3:** svako pokretanje savetnika „Pisanje podnesaka“ na predmetu ide na pregled (i planovi/checkliste); ponovljeno u 30 s se tiho ne upisuje; savetnik u V2 ne kaže da je nacrt poslat na pregled.
- **LIM-MIR-06-4 (postojeće):** odbijanje radi i nad već odobrenim nacrtom; DOCX se pravi iz teksta na ekranu, ne iz sačuvanog nacrta; šablonski `/api/podnesak` i dalje nema oslonac na spis.
- Napomena ne otkriva da nacrt protivreči odluci — samo je navodi; preko 12 redova odluka najnovije mogu ispasti.

**GATE-06: PASS**

---

## TASK-07 — Event → consequence → next action (MIR-01, MIR-05)

**User outcome:** nova činjenica u spisu (dopuna nalaza sa rokom) sama otvara odgovarajuću radnju sa razlogom i izvorom; kad izvor nestane (obrisan dokument ili povučena tvrdnja), posledica ne ostaje tiho aktivna — ni u Rad/Danas, ni u listi rokova za potvrdu.

**Baseline SHA:** `3c4ae1ea`.

**Root cause (reprodukovan nad Golden Case-om, kroz stvaran prijem i dispečer):** posledice nisu pratile povlačenje izvora — klasa sa četiri primerka: (1) rok iz obrisanog DOK-08 ostajao je otvorena radnja „čeka vašu potvrdu“ (Pravilo 6, `dokument_id` NULL posle FK); (2) Danas ga je i dalje nudio na **potvrdu** (`/api/rokovi/kandidati`) — advokat je mogao da učini obavezujućim rok iz nepostojećeg dokumenta; (3) radnje „razrešiti protivrečnost“ ostajale su otvorene posle brisanja dokumenta jedne strane (V2 učitavač je brojao povučene tvrdnje); (4) kad V2 nema živih strana, Pravilo 3 je padalo na staru granu (`case_dna.kontradikcije`) i **vaskrsavalo** istu protivrečnost pod drugim ključem — i posle brisanja dokumenta i posle povlačenja pojedinačne tvrdnje. Moj prvi test povučenog izvora bio je **prazan** (prolazio jer je `dokument_id` postao NULL) — otkriveno probom i pooštreno.

**Minimal fix:** `shared/rokovi.py::izvor_povucen` — JEDNO pravilo (Genome rok, naziv izvora upisan iz razrešenog id-a, id NULL, nema dokumenta tog naziva) za Pravilo 6 i za `/api/rokovi/kandidati` (`izvor_povucen` po redu; V2 Danas tada ne nudi „Potvrdi“, nudi „Odbij“ i kaže zašto); `services/v2_projection.py`: povučena tvrdnja nije strana sporne tačke, tačka sa < 2 žive strane nije radnja + `predmet_ima_v2`; `services/case_evolution.py`: Pravilo 6 preskače rok sa povučenim izvorom, stara grana Pravila 3 preskače protivrečnost čiji dokument više ne postoji, i **ne radi uopšte** za predmet koji ima V2 („ili-ili“ po predmetu, ne po trenutnoj listi).

**Changed files:** `shared/rokovi.py`, `services/v2_projection.py`, `services/case_evolution.py`, `routers/rok_odluka.py`, `frontend-v2-ng/src/danas.js`; testovi `tests/test_mir001_t07_dogadjaj_posledica.py` (nov), `tests/test_a003_contradiction_action_provenance.py` (lažnjak vraća dokumente na koje protivrečnosti pokazuju — stvarna invarijanta), `frontend-v2-ng/tests/live-danas.mjs` (+1 scenario), `frontend-v2-ng/tests/fixtures/pisanje-api.mjs` (prosleđuje oznaku).

**Positive tests executed:** `test_mir001_t07_dogadjaj_posledica.py` → **9 passed**: DOK-08 kroz stvaran prijem → rok u hronologiji sa `dokument_id` DOK-08 → tačno jedna radnja `PLANIRATI_ROKOVE` „čeka vašu potvrdu“ sa izvorom i `correlation_id`, vidljiva kroz `/api/case-actions/predmeti/{id}`; ponovljen događaj ×2 + ručno osvežavanje → bez nove radnje; terminalan predmet → nijedna otvorena; neutralan dokument (punomoćje) → nijedna nova radnja (no-consequence, reviewer: smislen, Genome i događaji stvarno izvršeni). V2: `live-danas` 54/54 (nov: predlog bez izvora bez „Potvrdi“).

**Negative/adversarial tests executed:** brisanje DOK-08 → radnja zatvorena, rok ostaje istorija (NULL id, naziv sačuvan), ostale posledice netaknute; brisanje DOK-02 → obe radnje protivrečnosti zatvorene u ISTOM usklađivanju, 0 poziva Genome-a; brisanje nepovezanog DOK-04 → netaknute; povlačenje pojedinačnih tvrdnji (dokument ostaje) → zatvorene, bez vaskrsavanja; kandidati `izvor_povucen` false → true; granice pravila (Smart Intake red ostaje, stari Genome red čiji naziv postoji ostaje); korisnik B ne vidi radnje. **Mutacije 9/9 backend + 1 UI** (povučen izvor, terminal, izvor radnje, dedupe, V2 broji povučene, stara grana vaskrsava, kandidati bez oznake, predikat bez provere naziva, stara grana kad predmet ima V2; Danas nudi potvrdu).

**Regression tests executed:** 185 fajlova (Case Evolution, case_actions, rokovi, hronologija, V2 projekcija, kandidati) → **3638 passed**; jedini pad `test_wave3_f4…_unchanged_by_this_session` meri NEKOMITOVAN git diff (prolazi posle commita — provereno ispod). A003 samostalno bez `OPENAI_API_KEY` pada 2/14 i na osnovi (nasleđena zavisnost od redosleda; sa ključem 14/14 na osnovi i sa ispravkom). V2: `verify:live-rad-predmeta` 44/44, `verify:live-danas` 54/54, `e2e:rok-odluka` 76/76, `e2e:solo-tok` 23/23, `verify:live-analiza` 46/46.

**Evidence level:** PROVEN, ISOLATED (stvarne rute, worker, dispečer, Genome osvežavanje i rekoncilijacija nad bazom u memoriji; zamenjen samo Genome model) + BROWSER_INTEGRATION (Danas nad fixture-om). LIVE — NOT_RUN.

**Independent reviewer finding:** 1. prolaz **FAIL** (radnje protivrečnosti posle brisanja izvora ostaju; Danas nudi potvrdu povučenog roka — ispravljen samo jedan primerak klase). 2. prolaz **FAIL** (moja ispravka uvela vaskrsavanje iz stare grane kod povlačenja pojedinačne tvrdnje — dokazano probom). 3. prolaz **PASS**.

**Remaining limitations (obelodanjeno):**
1. Smart Intake i Pipeline (AI) rok iz obrisanog dokumenta zadržava otvorenu radnju (nema dokazive veze sa dokumentom).
2. Dva dokumenta istog naziva, jedan obrisan → njegov rok ostaje otvoren.
3. Rok prisutan i u drugom dokumentu: brisanje prvog zatvara radnju, a rok se ne upisuje ponovo (hronologija deduplikuje po događaju i datumu).
4. Zatvorena radnja ne beleži razlog (povučen izvor izgleda isto kao „urađeno“).
5. `correlation_id` nosi poslednji događaj, ne izvorni (poznati Phase 2 gap; izvorni je u `audit_immutable`).
6. Direktan poziv `/api/rokovi/{id}/potvrdi` i dalje prihvata rok sa povučenim izvorom (V2 ga ne nudi).
7. Predmet bez V2: stara protivrečnost bez `dokument_id_1/2` i dalje može da se vrati.
8. Predmet sa V2 nikad ne prikazuje stare (legacy) protivrečnosti, i kad V2 nema nijednu.
9. **Promena ponašanja pri puštanju:** na predmetima sa V2 otvorene legacy radnje protivrečnosti se zatvaraju pri sledećem usklađivanju; otvorene Genome radnje roka čiji je dokument već obrisan takođe — bez upisanog razloga.

**GATE-07: PASS**

---

## TASK-08 — Bounded proactive AI (MIR-05)

**User outcome:** posle materijalne promene u predmetu (prihvaćen nov dokument koji je promenio analizu) Vindex, **bez zasebnog zahteva advokata**, u ciklusu autonomije priprema interni pregled promene — šta se promenilo, iz kog izvora, koje nove radnje je promena otvorila — kao radni proizvod `READY_FOR_REVIEW`; ništa ne šalje, ne potpisuje, ne podnosi i ne menja predmet.

**Baseline SHA:** `150feb7f`.

**Faza A — postojeće NS007 sposobnosti (bez izmene koda):** `tests/test_ns007_*.py` nad **stvarnim PostgreSQL-om 17.9** (izolovan privremen klaster u scratchpad-u, `127.0.0.1:55432`, stvarna migracija 136) → **163 passed, 0 skipped**: deterministički okidači, idempotencija (isti okidač = jedan posao), rezervacija budžeta pod konkurencijom, zakup/ponovno zauzimanje/dead-letter, ograničenja, izolacija korisnika, revizija, `READY_FOR_REVIEW`, prihvati/odbaci, zastarevanje izvora, RLS/prava.

**Faza B — root cause:** `CASE_CHANGE_BRIEF` je bio dozvoljen ugovorom (CHECK migracije 136, `routers/autonomy.py`, V2 labela), ali **nije imao izvršioca** — Miroslavljev slučaj („promena → pregled bez zahteva“) nije imao put. Utvrđeno: staje u POSTOJEĆI NS007 ugovor — nova tabela, migracija ni ovlašćenje nisu potrebni.

**Minimal fix:** `services/agent_tasks/case_change_brief.py` (planer + izvršilac u istom ugovoru kao `hearing_prep`): okidač = `DocumentAccepted`/`DocumentBatchCompleted` u poslednjih 7 dana, isti vlasnik, predmet aktivan, Genome ≥ v2; ključ i `trigger_ref` **po verziji** (`{predmet}:g{v}` — pregled poredi dve fiksne verzije, novija ga ne poništava); `cost_class FREE`, **bez poziva modela**; izvršenje: vlasništvo prvo, verzija ista kao pri planiranju, **dokaz da je verziju proizveo baš prijem dokumenta** (inače `CHANGE_NOT_FROM_DOCUMENT`), sadržaj isključivo iz NS006 `genome-v2/promene` + **nove** otvorene radnje; promena samo brojača = `NO_MATERIAL_CHANGE` (pošten neuspeh, bez proizvoda); registracija u `workers/background_agents._agent_modules` (legacy dnevni cron nepromenjen); V2 `pripremljeno.js` prikaz šeme `cb-1` (samo tekst).

**Changed files:** `services/agent_tasks/case_change_brief.py` (nov), `workers/background_agents.py`, `frontend-v2-ng/src/pripremljeno.js`; testovi `tests/test_mir001_t08_proaktivnost.py`, `tests/test_mir001_t08_pg.py` (novi), `frontend-v2-ng/tests/live-pripremljeno.mjs` (+1 scenario), `tests/test_ns007_t25_daily_cron_regression.py` i `tests/test_ns007_t3_scheduler_boundary.py` (samo skup agenata trajnog rada; tvrdnja „legacy registar nepromenjen“ ostaje).

**Positive tests executed:** `test_mir001_t08_proaktivnost.py` → **7 passed** (Golden Case kroz stvaran prijem → događaji → Genome verzije → Case Actions → **stvaran `run_autonomy_cycle`**): bez zahteva nastaje `READY_FOR_REVIEW` pregled v7 → v8 sa „Nov rok u analizi: 2026-10-28“ (poreklo AI_ANALYSIS) i jednom NOVOM radnjom (rok čeka potvrdu), `source_refs` (verzija + radnja), `DETERMINISTIC`, 0 poziva modela, 0 naplate, ništa poslato. `test_mir001_t08_pg.py` (stvaran PG) → **2 passed**: kandidat oblika planera prolazi CHECK, bez duplikata, FREE zauzimanje pri budžetu 0, nepoznat tip odbijen. V2 `live-pripremljeno` **53/53** (sekcije `cb-1`, tekst iz podataka se ne izvršava).

**Negative/adversarial tests executed:** ponovljen ciklus → isti jedan posao; nova (nematerijalna) verzija → materijalni pregled ostaje, novi = `NO_MATERIAL_CHANGE` bez sadržaja; ručno osvežavanje u prozoru događaja → `CHANGE_NOT_FROM_DOCUMENT` (ne tvrdi nov dokument); završen predmet → bez kandidata; događaji van prozora → bez posla; posao korisnika B nad predmetom A → `MATTER_NOT_ACCESSIBLE`; B ne čita ni ne prihvata tuđ rad (404); prihvatanje ne menja nijednu drugu tabelu, upisuje reviziju. **Mutacije 9/9** (registracija, plaćen posao, brojači kao materijalni, stare radnje kao nove, završen predmet, ključ bez verzije, bez prozora, bez dokaza okidača, `trigger_ref` po predmetu) + **UI 1/1**.

**Regression tests executed:** NS007 + svi testovi autonomije/agenata, **uključujući stvaran PG** → **355 passed**; V2 `e2e:pre136` 21/21 (kontrolna grupa pada kako je očekivano), `e2e:demo-ns007` 5/5.

**Evidence level:** NS007 infrastruktura — PROVEN, ISOLATED (stvaran PostgreSQL 17.9). `CASE_CHANGE_BRIEF` ceo tok — PROVEN, ISOLATED (lažna baza čiji RPC preslikava migraciju 136; ugovor novog tipa na stvarnom PG-u). V2 prikaz — BROWSER_INTEGRATION (fixture). **Produkcija — BLOCKED_AUTHORITY** (migracija 136 nije primenjena, Cron/tajna nisu postavljeni; `/api/cron/autonomy` → 401; nijedna radnja nije preduzeta).

**Independent reviewer finding:** 1. prolaz **FAIL** — P1: pregled je mogao da tvrdi „primljen je nov dokument“ kad je verziju proizvelo ručno osvežavanje (dokazano probom); P2: kasnija nematerijalna verzija poništavala je nepregledan materijalni pregled. 2. prolaz **PASS**. Posle toga uklonjena i preostala nepreciznost: razlog upisan pri planiranju više ne tvrdi uzročnost.

**Remaining limitations / odluke:**
- **BLOCKED_AUTHORITY:** aktivacija u produkciji (migracija 136, `AUTONOMY_CRON_SECRET`, budžet, kadenca, Render Cron — `VCR002_T09_AUTONOMY_ACTIVATION.md`) je odluka osnivača; dodavanje trećeg agenta menja opterećenje ciklusa kad se uključi (planer: najviše 500 najnovijih događaja prijema u 7 dana preko svih korisnika; deli globalnu granicu od 25 poslova po ciklusu sa plaćenom pripremom ročišta).
- Posao u redu za v8 kad stigne v9 završava `SOURCE_VERSION_CHANGED` (pošten neuspeh; ta promena nema pregled). Pregledi se gomilaju po verziji dok se ne pregledaju (ograničeno brojem verzija).
- Datum u razlogu je najnoviji događaj prijema za predmet (ne nužno onaj koji je proizveo verziju).
- „Samoprovera analize“ (`provera_analize`) se ne smatra materijalnom; nove radnje se prepoznaju po `created_at ≥` trenutka verzije (može da potceni, ne precenjuje).
- PG test novog tipa koristi ručni SQL istog oblika kao planer (ne izlaz planera).

**GATE-08: PASS** (izolovano) · **produkcija: BLOCKED_AUTHORITY**

---

## TASK-09 — Corporate workflow fit (MIR-04) — samo dokazi

**User outcome:** jasno je šta Vindex danas nudi za Miroslavljev rad sa ugovorima i ponavljajućim korporativnim procesima, i šta mora prvo da se definiše — bez izmišljenih zahteva i bez implementacije.

**Baseline SHA:** `c474e3b5`. **Changed files:** samo ovaj zapis. **Kod nije menjan** (zadatak je evidence-only).

**Izvor zahteva:** isključivo tekst osnivača u masterpromptu MIR001 (2026-10-22). Drugog izvora nema (VCR002: „Miroslav“ u repo-u i na Drive-u = 0 rezultata).

| # | Iskaz (doslovno ili parafraza iz masterprompta) | Postojeća sposobnost (kod) | Gde je dostupna | Šta mora da se definiše | Dokazni nivo |
|---|---|---|---|---|---|
| S1 | „radi kao pravni savetnik u kompaniji“ | — (kontekst, ne zahtev) | — | — | — |
| S2 | „veliki broj ugovora“ | (a) šabloni nacrta `/api/nacrt` — 18 vrsta, od kojih ugovorni: kupoprodaja, zakup nepokretnosti, ugovor o radu (neodređeno/određeno), aneks, sporazumni raskid, punomoćje, obaveštenje o otkazu ugovora (`drafting/templates`); (b) analiza teksta `/api/analiza` (do 50.000 znakova, bez veze sa predmetom); (c) sažetak `/api/sazmi` | **samo stari interfejs** (`/app-legacy`, `static/vindex.js`); V2 ih **ne poziva** | koje vrste ugovora; šta radi sa njima (izrada iz šablona, pregled rizika, poređenje verzija, evidencija rokova/obnova, odobravanje); obim; da li ugovori pripadaju „predmetu“ ili posebnom registru | postojeći testovi `test_drafting_*`, `test_faza3_drafting_engine_*` — LOCAL; V2 — **NOT_AVAILABLE**; korisnik — UNKNOWN |
| S3 | „veliki broj … dokumenata“ | Smart Intake + OCR + prikačivanje (TASK-02), izdvajanje entiteta | V2 Prijem, **vezano za predmet** | da li je jedinica rada predmet, ugovor ili poslovni proces; koje vrste dokumenata | PROVEN, BROWSER_INTEGRATION (Golden Case, sudski spis — ne korporativni dokumenti) |
| S4 | „različiti poslovni procesi“ / „automatizacija mu je posebno značajna“ | autonomija NS007: `HEARING_PREP`, `PRECEDENT_IMPACT`, `CASE_CHANGE_BRIEF` — sve **parnične** | V2 „Vindex je pripremio“ (produkcija isključena) | konkretni procesi: ulaz, pravilo, izlaz, ko odobrava, učestalost (npr. „svaki novi ugovor dobavljača proveri na X i javi Y“) | za korporativne procese — **nema sposobnosti**; **BLOCKED_REQUIREMENTS_DETAIL** |
| S5 | „AI koji prepozna korake koje sam može da uradi bez eksplicitne instrukcije“ | za sudski predmet: posledice događaja (TASK-07) i pregled promene bez zahteva (TASK-08) | V2 Rad/Danas; „Pripremljeno“ (izolovano) | za ugovore/procese: koji događaj je okidač i koji radni proizvod se očekuje | parnični deo PROVEN ISOLATED (TASK-07/08); korporativni deo **BLOCKED_REQUIREMENTS_DETAIL** |

**Dopuna inventara (GATE-09):** postoje i — **sve samo u starom interfejsu** (`static/vindex.js`), V2 ih ne poziva:
- **workflow šabloni** (`routers/workflow.py`, `api.py:825`): koraci sa `rok_dana`, `auto_assign`, eskalacija i cron eskalacije — **vezani za predmet** (`PokretanjeRequest.predmet_id`); relevantno za S4, ali nije proces izvan predmeta;
- **dokument modul** (`routers/dokument.py`, `api.py:707`): upload, pitanja nad dokumentom, `/api/dokument/analiza` (do 80.000 znakova, sesija, bez predmeta) i `/api/dokument/rokovi` (izdvajanje rokova iz bilo kog dokumenta, uklj. kategoriju „otkaz“ — `uploaded_doc/deadline_parser.py`) — samo izdvajanje, bez praćenja; relevantno za S2/S3;
- **poređenje 2–5 dokumenata** (`routers/cross_doc.py:268`, i varijanta predmeta `:310`): traži sukobe — nije poređenje verzija (redline);
- **deterministička provera ugovora o radu prema Zakonu o radu** (`drafting/compliance.py`, u `/api/nacrt` za dve vrste ugovora o radu) — provera ugovora prema zakonu, samo za te dve vrste;
- manje: provera stila (`routers/style_checker.py`, nijedan interfejs je ne poziva), APR pretraga firmi (`routers/apr.py`, stari CRM).

**Ne postoji (i ne implementira se bez definicije):** registar ugovora, tok odobravanja, praćenje ugovornih obaveza i rokova obnove, poređenje verzija ugovora (redline), šabloni kompanije (playbook postoji samo kao upload uz `/api/nacrt`), **korporativni proces izvan predmeta** (postoji samo predmetni workflow šablon u starom interfejsu).

**Najmanje pitanje za Miroslava (da bi MIR-04 postao merljiv):** „Navedite 2–3 ponavljajuća posla sa ugovorima koje danas radite ručno: šta stiže (vrsta dokumenta), šta radite sa tim (provera, izmena, evidencija, obaveštenje), šta je rezultat i ko ga odobrava, i koliko često.“

**Positive/negative tests executed:** nijedan nov (evidence-only); pregled koda: `frontend-v2-ng/src` ne poziva `/api/nacrt`, `/api/analiza`, `/api/sazmi`; `static/vindex.js` ih poziva; `drafting.templates.get_types_list()` = 18 vrsta.

**Evidence level:** kao u tabeli; nijedna sposobnost nije REAL_USER_ACCEPTED.

**Independent reviewer finding:** 1. prolaz **FAIL samo zbog propusta u inventaru** (workflow šabloni, dokument modul sa rokovima, poređenje dokumenata, provera ugovora o radu prema ZR); nijedan zahtev nije izmišljen, nijedna sposobnost nije precenjena, BLOCKED_REQUIREMENTS_DETAIL opravdan. Dopunjeno iznad.

2. prolaz **PASS** (dopuna tačna, bez novih precenjivanja ni izmišljenih zahteva).

**GATE-09: PASS** — ishod zadatka: **BLOCKED_REQUIREMENTS_DETAIL** za MIR-04.

---

## TASK-10 — Final Miroslav acceptance gate

**Baseline SHA:** `2a2312b2` (grana `night/miroslav-recovery` od `origin/main` = produkcija `f33dcce8`; **14 commitova**). **Ništa nije pushovano** (`git ls-remote origin night/miroslav-recovery` prazno), spojeno ni pušteno; nijedna migracija (`git diff f33dcce8..HEAD -- migrations/` prazno), tajna ni Cron nisu dirani.

**Changed files:** `tests/test_mir001_t10_ceo_tok.py` (nov) + ovaj zapis. Kod nije menjan.

### Jedan neprekinut scenario (`tests/test_mir001_t10_ceo_tok.py`: jedna test funkcija, isti proces, ista baza u memoriji, isti korisnik `uid-A`, isti predmet) → **12/12 provera testa, 2 uzastopna pokretanja**

Kolone: **u scenariju** (šta dokazuje ovaj neprekinuti test) i **dodatno** (posebni dokazi iz ranijih zadataka). „Browser nad fixture-om“ nije BROWSER_INTEGRATION.

| Segment osnivača | Provera testa | U scenariju | Dodatno |
|---|---|---|---|
| nov predmet | 01 | PASS_ISOLATED (`POST /api/predmeti`) | PASS_BROWSER_INTEGRATION — V2 forma „Nov predmet“ nad pravim `api.app` (`live-mir001-spis-e2e.mjs`, ponovljeno na konačnom kodu: 17/17) |
| sedam dokumenata | 01 | PASS_ISOLATED (stvarne rute prijema, worker) | PASS_BROWSER_INTEGRATION — isti e2e (jedno otpremanje, 7× „Prikačeno“) |
| OCR | 02 | PASS_LOCAL (stvaran Tesseract 5.5.3, conda) | produkciona Docker slika za ovaj sken — NOT_RUN |
| činjenice | 03 | PASS_ISOLATED (15 navoda, po jedan izvor) | V2 „SPORNO“ — browser nad fixture-om (`live-analiza`) |
| vremenski sled | 04 | PASS_ISOLATED (9 događaja, tačan redosled i izvor) | — |
| protivrečnosti | 05 | PASS_ISOLATED (K-01, K-02 aktivne) | zatvaranje pri povlačenju izvora — PASS_ISOLATED (TASK-07) |
| pravno pitanje | 06 | PASS_ISOLATED — **kroz savetnika `research`** (`/api/agents/run`); V2 ekran „Pravno pitanje“ (`/api/pitanje`) nije u scenariju | stvaran gpt-4o: 21/21 **samo prisustvo** (3 uzorka × 7 pitanja); greške modela u uzorcima: DEBT-MIR-04-2 |
| strategija | 07 | PASS_ISOLATED (pravila, današnji datum, bez procenta u poruci) | stvaran gpt-4o: 30/66 → 75/110 **po skripti, niže posle ručne ispravke** (R13 3/5, R10 8/10, R9 ispravno 1/10); DEBT-MIR-05-1..3 |
| nacrt | 08 | PASS_ISOLATED (nacrt → pregled sa napomenom) | stvaran gpt-4o: **3–4/5 predlaže već odlučeno** (DEBT-MIR-06-1); nalaz veštaka kao utvrđen 10/10 (DEBT-MIR-06-2) |
| pregled / izvoz | 08 | PASS_ISOLATED (izmena sačuvana, odobren izmenjen tekst, nije promovisan) — DOCX se pravi iz poslatog teksta, ne iz sačuvanog nacrta (LIM-MIR-06-4), pa je provera DOCX-a slaba | V2 kartica Nacrt — browser nad fixture-om (`live-nacrt` 51/51) |
| nova informacija | 09 | PASS_ISOLATED (DOK-08 kroz stvaran prijem → rok sa izvorom) | — |
| sledeća radnja | 10 | PASS_ISOLATED (jedna radnja sa razlogom i izvorom) | Danas — browser nad fixture-om (`live-danas` 54/54) |
| autonomna priprema | 11 | PASS_ISOLATED (`CASE_CHANGE_BRIEF`, bez zahteva, bez modela) | NS007 163/163 na stvarnom PG-u; V2 „Pripremljeno“ — browser nad fixture-om; **produkcija: BLOCKED_AUTHORITY** |
| izolacija | 12 | PASS_ISOLATED — B dobija 403/404 na predmet, `genome-v2`, radni proizvod autonomije, nacrt (staging); radnje (`case-actions`) nisu u ovoj proveri (pokrivene u TASK-07) | — |
| LIVE (prijavljen tok u produkciji) | — | **NOT_RUN** | nema QA naloga; ispravke ovog sprinta NISU u produkciji |
| REAL_USER_ACCEPTED | — | **NOT_RUN** | nijedan automatski test ga ne zamenjuje |

**Regresija na kraju sprinta:** pun Python paket — osnova `f33dcce8`: **15 failed / 11.736 passed / 318 skipped**; grana: **15 failed / 11.807 passed / 318 skipped** (+71 novih testova), **identičan skup padova (0 novih)**; nasleđeni padovi provereni uzorkom (fixture heš, sitan tekst u legacy `static/`, prazan commit u svežem procesu) — van ovog diff-a. V2 frontend: **51/51 skripti** (`verify*` + `e2e*`).

### Završna presuda po zahtevu

| MIR | Isporučeno | Dokazano / nivo | Blokirano / dug (obelodanjeno) | Spremno za Miroslavljevu stvarnu proveru? |
|---|---|---|---|---|
| **MIR-01** povezivanje spisa | prijem celog spisa bez izmene koda (TASK-02); Genome do 60 tvrdnji, nepotpuno opažanje ne zatvara sporne tačke, V2 „SPORNO“ (TASK-03); povučen izvor ne ostavlja posledice (TASK-07; uz izuzetke u koloni duga) | BROWSER_INTEGRATION (prijem; baza u memoriji) + ISOLATED | LIVE; **LIM-MIR-03-1**: klasifikator vidi prvih **1.500 znakova (≈ 1 strana)** i ≤ 5 tvrdnji po dokumentu; **vrsta dokumenta nije merena** (simulirana „Dopis“); LIM-MIR-03-2 (> 60 tvrdnji → trajno PARTIAL); TASK-07 ogr. 1 (Smart Intake/Pipeline rok iz obrisanog dokumenta ostaje), 2 (isti naziv fajla), 6 (direktan `/potvrdi` prihvata rok povučenog izvora); 3, 7, 8 (rok i u drugom dokumentu se ne upisuje ponovo; legacy protivrečnosti bez `dokument_id`; predmet sa V2 ne prikazuje legacy) | **Da, uz obelodanjena ograničenja** — kontrolisan pilot sa **kratkim dokumentima (≤ ~1.500 znakova)** |
| **MIR-02** strategija iz spisa | savetnik vidi ceo spis (do 12 dok., isti budžet teksta) + sporne tačke (TASK-04); „Parnična strategija“ radi sa spisom: procesno stanje, šta menja novi dokument, današnji datum (TASK-05) | ISOLATED + stvaran model (k/5, kratki sintetički dokumenti) | DEBT-MIR-04-1 (blok spornih tačaka bez oznake dokumenta, može doneti tekst nedostavljenog dokumenta); DEBT-MIR-04-2 (navod kao činjenica, izračunat datum kao činjenica…); LIM-MIR-04-3 (kraći početni isečci kod dugih dokumenata); LIM-MIR-04-4 (bez pretrage po relevantnosti); DEBT-MIR-05-1..3; pouzdanost nad dugim stvarnim spisom — UNKNOWN | **Da, kao radni materijal za pregled advokata** |
| **MIR-03** nacrt iz spisa | nacrt savetnika ide na postojeći pregled sa napomenom (citati, nepročitano, tražen-nedostavljen, odluke suda i rokovi) → izmena → odobrenje → DOCX; ne postaje znanje ni izvor (TASK-06) | ISOLATED + browser nad fixture-om | **DEBT-MIR-06-1 (materijalno)**: 3–4/5 nacrta predlaže već odlučeno; **DEBT-MIR-06-2**: nalaz veštaka kao utvrđen 10/10; LIM-MIR-06-3 (svako pokretanje ide na pregled, 30 s dedupe, bez obaveštenja u savetniku); LIM-MIR-06-4 (DOCX iz teksta na ekranu; odbijanje i nad odobrenim; šablonski `/api/podnesak` bez oslonca na spis) | **Delimično** — samo uz obavezan pregled i uputstvo da se proveri odeljak „Odluke suda“ u napomeni |
| **MIR-04** korporativni rad | inventar (TASK-09) | — | **BLOCKED_REQUIREMENTS_DETAIL** (procesi nisu definisani; šabloni/analiza ugovora i predmetni workflow postoje samo u starom interfejsu) | **Ne** — treba odgovor na pitanje iz TASK-09 |
| **MIR-05** kontrolisana proaktivnost | posledice događaja bez ponovnog unosa (TASK-07); `CASE_CHANGE_BRIEF` u postojećem NS007 ugovoru (TASK-08) | ISOLATED (+ stvaran PG za NS007) | **BLOCKED_AUTHORITY** za produkciju (migracija 136, tajna, budžet, kadenca, Cron); **posledica puštanja (TASK-07 ogr. 9)**: na predmetima sa V2 otvorene legacy radnje protivrečnosti i radnje roka čiji je dokument već obrisan zatvoriće se pri sledećem usklađivanju, **bez upisanog razloga**; zatvorena radnja nema razlog (ogr. 4); `correlation_id` = poslednji događaj (ogr. 5); TASK-08: posao u redu za staru verziju → `SOURCE_VERSION_CHANGED`, deli granicu od 25 poslova po ciklusu, planer do 500 događaja / 7 dana | Posledice (Rad/Danas): **da, posle puštanja**; autonomija: **ne** dok osnivač ne odobri aktivaciju |

### Ukupna odluka: **PARTIAL_READY_WITH_DISCLOSED_LIMITATIONS**
uz **BLOCKED_AUTHORITY** (puštanje grane i aktivacija autonomije su odluke osnivača) i **BLOCKED_REQUIREMENTS_DETAIL** (MIR-04). Miroslavljevo prihvatanje **nije** proglašeno.

### Najmanje odluke osnivača
1. Pregled i puštanje grane `night/miroslav-recovery` (**14 commitova** od `f33dcce8`; push/PR/merge/deploy — nije urađeno), uz svest o posledici puštanja iz TASK-07 ogr. 9.
2. QA nalog za jednu prijavljenu proveru istog scenarija u produkciji (LIVE).
3. Da li Miroslav dobija kontrolisan pilot sa sintetičkim ili sopstvenim (anonimizovanim) spisom, uz pisano upozorenje za LIM-MIR-03-1 i DEBT-MIR-06-1/2.
4. Aktivacija autonomije (paket `VCR002_T09_AUTONOMY_ACTIVATION.md`) — tek posle 1–3.
5. Pitanje Miroslavu za MIR-04 (TASK-09).

**Independent reviewer finding:** 1. prolaz **FAIL** — završne tabele su izostavile ili ublažile dugove ranijih kapija (MIR-01: „kratki/srednji“ umesto ≈ 1 strane, nemerena vrsta dokumenta, LIM-MIR-03-2, TASK-07 ogr. 1/2/6/9; MIR-02: DEBT-MIR-04-1/2, LIM-MIR-04-3/4; MIR-03: DEBT-MIR-06-2, LIM-MIR-06-3/4; TASK-08 ograničenja); „browser“ pripisan testovima nad fixture-om; 75/110 bez napomene o ručnoj ispravci; „10 commitova“ (tačno 14); neusklađena numeracija i spisak izolacije; „pravno pitanje“ je savetnik `research`. Scenario, regresija i ukupna odluka potvrđeni. Sve ispravljeno u ovom odeljku.

2. prolaz **PASS** (sve ispravke potvrđene; dve opcione dopune unete).

**GATE-10: PASS** — završna odluka **PARTIAL_READY_WITH_DISCLOSED_LIMITATIONS** (+ BLOCKED_AUTHORITY, + BLOCKED_REQUIREMENTS_DETAIL za MIR-04). Broj commitova na grani: vidi `git log f33dcce8..night/miroslav-recovery` (14 kod/kapija + zapisi završnog pregleda).

---

# MIR001 FINAL CLOSURE — SEQUENTIAL CORRECTIVE SPRINT

Redosled: C0 → GATE-C0 → C1 → GATE-C1 → C2 → GATE-C2 → C3 → GATE-C3 → C4. Push, merge, migracije, deploy i NS007 aktivacija NISU odobreni i nisu rađeni.

## TASK-C0 — Verify MIR001 baseline (bez izmene koda)

**Stanje grane:** `night/miroslav-recovery`, HEAD `cd83b789feaa386a04b661b357bdcb7d01496d0f`; `origin/main` = `f33dcce8` (= produkcija, `/health` → `f33dcce`); **16 ispred / 0 iza** (`git rev-list --left-right --count origin/main...HEAD` → `0 16`); `git ls-remote origin night/miroslav-recovery` prazno (nije pushovano); radno stablo čisto; `git diff f33dcce8..HEAD -- migrations/` prazno (nijedna migracija). **Ponašanje izmenjeno u kodu grane, ništa nije pušteno:**
- Savetnici: `/api/agents/run`, `/run-parallel`, `/pipeline` (`routers/multi_agent.py` ≈ l. 949/1133/1330, zajednički `_kontekst_predmeta`) — do 12 dokumenata u podeljenom budžetu (min. 500 zn.), blok spornih tačaka, današnji datum, uklonjen „Snaga predmeta %“, nova pravila sistemskog prompta; `/run` za drafting + predmet upisuje nacrt u staging (`nacrt_iz_spisa`).
- Staging: `/api/staging/{id}/approve` i `ponovi-upis` (`nacrt_iz_spisa` se ne promoviše; 409 `NACRT_IZ_SPISA`).
- Genome: `POST /api/predmeti/{id}/case-dna/refresh` (`routers/case_dna.py` ≈ l. 1325) i potrošač događaja — tvrdnje u promptu 20 → 60 (`shared/claim_catalog.py`), `_tvrdnje_van_analize`, V2 opažanje može biti nepotpuno; `shared/genome_contract.sastavi` (koristi i `multi_agent`) može vratiti PARTIAL + `tvrdnje_izostavljene`.
- Radnje predmeta: `_compute_target_actions` (`izvor_povucen`, `predmet_ima_v2`) i `services/v2_projection.py` (povučene tvrdnje ispadaju) → menja se izlaz `/api/case-actions/predmeti/{id}`, Danas i šta brisanje dokumenta zatvara.
- Rokovi: `/api/rokovi/kandidati` (`izvor_povucen` po redu).
- Autonomija: `workers/background_agents.py` registruje `case_change_brief` u NS007 ciklusu (NS007 nije aktiviran u produkciji).
- Frontend `/app`: `frontend-v2-ng/` (`danas.js`, `analiza-predmeta.js`, `pripremljeno.js`, `nacrt-predmeta.js`, `index.html`).

**Tačne putanje tri slabosti:**
1. Zatvaranje radnje — `services/case_evolution.py::_consequence_refresh_case_actions` (≈ l. 1377–1399): radnja čiji ključ nije u novom ciljnom skupu (`_compute_target_actions`) dobija `status='closed', closed_at`; audit `case_action_refreshed` (l. 1404) beleži `closed_actions: [{id, dedupe_key}]` + `event_id`/`correlation_id` reda. **Razlog i izvor zatvaranja PO RADNJI ne postoje** ni na redu ni u stavci `closed_actions`; poreklo postoji samo posredno, na nivou događaja (`event_id` → `events`, u R1 to je `SourceInvalidated` obrisanog dokumenta).
2. Ekstrakcija — `routers/evidence.py::_klasifikuj_dokument` l. 98 `tekst_izvod[:1500]` (pozivalac l. 211 prosleđuje ceo `tekst`), l. 285 `cinjenice[:5]`; Genome `routers/case_dna.py` `_GENOME_MAX_CHARS_PER_DOC = 4500` (l. 271).
3. Nacrt — `routers/multi_agent.py` (drafting prompt „KADA SU DOSTAVLJENI DOKUMENTI PREDMETA“ + PROCESNO STANJE; `_napomena_za_pregled` / `_odluke_suda`) → `routers/drafting.py` staging.

**Reprodukcije** (proba `docs/v2-execution/MIR001_C0_REPRODUKCIJE.py`, pokreće se iz korena: `python -m pytest docs/v2-execution/MIR001_C0_REPRODUKCIJE.py -p tests.conftest -q -s -p no:randomly` uz OCR env; **3 passed**):

| # | Slabost | Reprodukcija | Izlaz | Status |
|---|---|---|---|---|
| R1 | zatvaranje bez razloga | Golden Case + DOK-08 kroz stvaran prijem → otvorena radnja roka iz DOK-08 → `DELETE /api/predmeti/{pid}/dokumenti/{d8}` → dispečer | radnja `closed`; audit `closed_actions=[{"id":…, "dedupe_key":…}]`, ključevi metapodataka `closed, closed_actions, created, created_actions, event_id, open_total, updated, updated_actions` — **bez razloga/izvora po radnji** (`razlog` na redu je razlog OTVARANJA); poreklo samo preko `event_id` reda → `SourceInvalidated` | **REPRODUKOVANO NA GRANI (ISOLATED)**. Ovo zatvaranje proizvodi pravilo TASK-07 (`izvor_povucen`, commit `150feb7f`); na produkciji `f33dcce8` simptom je drugačiji — po zapisu TASK-07 takva radnja ostaje OTVORENA bez izvora (nije ponovo pokrenuto na `f33dcce8` u C0) |
| R2a | činjenica na 2.589/2.698 | dug PDF kroz stvaran prijem + **pravi** `_klasifikuj_dokument` (uhvaćen pri uvozu, pre zamene u fixture-u; zamenjen samo poziv modela) | klasifikator 1 poziv, tekst u poruci **1500** znakova, činjenica **odsutna**; Genome prompt **sadrži** činjenicu (assert) | **REPRODUKOVANO** — tvrdnje (`predmet_dokazi`) je ne dobijaju; Genome je vidi |
| R2b | činjenica na 5.139/5.248 | isto | klasifikator: odsutna; Genome: **odsutna** (granica 4.500/dok., assert) | **REPRODUKOVANO** — činjenica ne stiže ni do klasifikatora ni do Genome-a |
| R3 | nacrt predlaže već odlučeno | stvaran gpt-4o iz TASK-06 (`MIR001_T06_STVARNI_MODEL.json`); **u C0 nije ponovo pokrenuto** | **4/5 (1. krug: N0, N1, N2, N4), 3/5 (2. krug: N2, N3, N4) — isključivo ručnim čitanjem**; automatska mera u JSON-u se ne slaže: 1. krug nema polje `D12_ne_trazi_vec_odluceno`, u 2. krugu D12 je False 4/5 (N1 je lažno negativan meri — ne protivi se dopuni, ali nalaz veštaka iznosi kao utvrđen, D7b) | **REPRODUKOVANO (stvaran model, k/5, ručna ocena)** |

**Hipoteze (nisu reprodukovane u C0):** uticaj na postojeće produkcione radnje (C1 procena samo čitanjem); da li `cinjenice[:5]` sam gubi presudnu činjenicu kod dokumenta sa > 5 činjenica u prvih 1.500 znakova; da li činjenica iz R2a (vidljiva Genome-u, ne i klasifikatoru) može da postane V2 protivrečnost — V2 protivrečnost traži tvrdnje, pa verovatno ne može (zaključak, nije reprodukovano); uzrok R3 (prompt vs. model) — C3.

**Regresiona osnova (iz TASK-10, nepromenjena):** 15 nasleđenih padova, identičan skup na `f33dcce8` i grani; V2 frontend 51/51.

**Changed files:** ovaj zapis + `docs/v2-execution/MIR001_C0_REPRODUKCIJE.py` (proba, nije u `tests/`). Kod nije menjan.

**Independent reviewer finding:** 1. prolaz **FAIL** — (1) spisak izmenjenog ponašanja nepotpun (savetnici run/run-parallel/pipeline, Genome refresh + `genome_contract`, radnje/`v2_projection`/Danas, NS007 registracija, frontend); (2) R1 „bez izvora u auditu“ preterano — poreklo postoji posredno preko `event_id`; (3) R1 je posledica koda grane (TASK-07), na produkciji simptom je drugačiji; (4) R2a: protivrečnosti nisu dokazane, Genome vidljivost nije bila assert; (5) R3: brojevi samo iz ručnog čitanja, automatska mera se ne slaže; (6) zbunjujući uvoz u probi. Sve ispravljeno. 2. prolaz **PASS**; dve neblokirajuće napomene (assert da je Genome pozvan; l. 1404) unete.

**GATE-C0: PASS**

## TASK-C1 — Auditable action invalidation

**Baseline SHA:** `645dc4fe` (C0). **Changed files:** `services/case_evolution.py` (+69/−4), `tests/test_mir001_c1_zatvaranje_radnji.py` (nov, 10 testova), usklađena 3 postojeća testa (v. dole). Bez migracije, bez nove kolone/tabele, bez backfill-a.

**Mehanizam (pre):** jedini kod koji menja `case_actions.status` je `_consequence_refresh_case_actions` (ostali pozivi — `api.py`, `routers/case_dna.py`, `case_pipeline.py`, `workspace.py`, `case_actions.py`, `case_context`, `hearing_prep`, `copilot` — samo čitaju; nijedan RPC iz migracija ne piše status; nema korisničke rute koja menja status). Radnja koja ispadne iz ciljnog skupa zatvarala se bez razloga po radnji (R1).

**Može li postojeći audit da nosi razlog i izvor?** Da — `audit_immutable.metadata` (JSONB) već nosi `closed_actions`, a `case_actions.dokaz` (JSONB, migracija 099) prima ključ bez izmene šeme (čitaoci `dokaz`-a — `workspace.py`, `frontend-v2-ng/src/radna-lista.js` — čitaju samo ključeve najvišeg nivoa koje ovo ne dira). Migracija nije potrebna → nije `BLOCKED_DECISION`.

**Ispravka (najmanja):**
1. `veza_sa_izvorom(akcija, source_type, source_id)` — veza je dokaziva SAMO iz polja koja je radnja sama nosila pri nastanku: `dokument` → `dokaz.dokument_id`, `dokument_id_1/2`, `dokument_ids`, ili `izvor_dokumenti`; `dokaz` (tvrdnja) → `dokaz.claim_ids`; `rociste` → `dokaz.rociste_id`. Nikad naziv fajla, pozicija ni vreme; `None` nikad nije veza.
2. `SourceInvalidated` (atomski RPC 131/133/137 uvek nosi `source_type/source_id`) zatvara samo radnju sa dokazivom vezom. Radnja koja ispada iz ciljnog skupa **bez** dokazive veze ostaje `open`; zadržavanje se piše **na red** (`dokaz.zadrzano = {razlog: VEZA_SA_POVUCENIM_IZVOROM_NIJE_DOKAZIVA, source_type, source_id, event_type, event_id, zadrzano_at}`; ponovljena isporuka ga ne prepisuje) i u audit (`zadrzane_actions`). `SourceInvalidated` bez izvora ne zatvara ništa.
3. Svako zatvaranje nosi razlog u ISTOM UPDATE-u kao status: `dokaz.zatvaranje = {razlog: IZVOR_POVUCEN | CINJENICA_VISE_NE_VAZI, source_type, source_id, veza, event_type, event_id, zatvoreno_at[, posle_zadrzavanja]}` — razlog otvaranja i ostatak `dokaz`-a netaknuti. Ako je radnja ranije bila zadržana, zatvaranje drugim događajem **navodi** to zadržavanje i obrisani izvor (`posle_zadrzavanja`), pa se ne pripisuje samo nepovezanom događaju. Audit: `closed_actions[] = {id, dedupe_key, zatvaranje, prethodno: {status: open, updated_at, tip, razlog, prioritet, rok, dokaz}}`.

**Prihvatni kriterijumi** (`tests/test_mir001_c1_zatvaranje_radnji.py`, Golden Case kroz stvarne rute brisanja, RPC događaj, dispečer; **10/10**):

| Kriterijum | Test | Ishod |
|---|---|---|
| bez tihe promene statusa | `…relevantnog_dokumenta…`, `…nedokaziva_veza…`, `…zavrsen_predmet_zatvara_sa_razlogom` (`MatterBecameTerminal` → `CINJENICA_VISE_NE_VAZI`) | PASS |
| brisanje nepovezanog dokumenta ne zatvara | DOK-04: statusi identični, `closed_actions` prazno | PASS (regresiona zaštita — prolazi i na starom kodu) |
| brisanje relevantnog reaguje ispravno | rok iz DOK-08 (`veza=dokument_id`); obe protivrečnosti pri brisanju DOK-02 (`dokument_ids`); povlačenje tvrdnji — **po događaju** zatvara tačno radnje čiji `claim_ids` sadrži tu tvrdnju, ostale su zadržane | PASS |
| nedokaziva veza ne zatvara | Genome rok koji dokument imenuje samo nazivom → posle brisanja `open`, `dokaz.zadrzano` sa izvorom i događajem, `zadrzane_actions`; događaj bez izvora → ništa | PASS |
| audit proverljiv | razlog na redu == razlog u auditu; `prethodno` == stanje pre zatvaranja; kasnije zatvaranje navodi zadržavanje | PASS |
| replay idempotentan | ponovljena isporuka kroz dispečer: svi redovi identični; ponovljeno povlačenje ne prepisuje zadržavanje; direktno ponovno usklađivanje: `created=0 closed=0`, statusi i zatvaranja identični — postojeća UPDATE grana ponovo upisuje iste vrednosti iz ciljnog skupa (`razlog/dokaz/prioritet/rok/izvor_dokumenti/correlation_id`) i nov `updated_at`/`event_id` OTVORENIH radnji | PASS |
| B ne menja radnje A | `DELETE` dokumenta A sa nalogom B → 404, nijedan `SourceInvalidated`, radnje A identične; `/api/case-actions/predmeti/{pid}` za B → 403/404 | PASS (regresiona zaštita) |
| čista funkcija veze | tačan/pogrešan izvor, pogrešna vrsta izvora, `None` u listi, prazan izvor/dokaz | PASS |

**Mutacije** (binarni harness, vraćeno bajt-identično): **10/10 uhvaćeno** — zatvaranje bez provere veze; razlog nije na redu; audit bez prethodnog stanja; veza bez poređenja oznake (uhvaćena testom čiste funkcije); `zadrzane_actions` se ne beleže; događaj bez izvora kao opšte usklađivanje; zadržavanje se ne piše na red; kasnije zatvaranje ne navodi zadržavanje; zadržavanje se prepisuje pri ponavljanju; `None` u listi poklapa „None“ (uhvaćena tek dodatim slučajem).

**Usklađeni postojeći testovi** (koristili su `SourceInvalidated` sa praznim payload-om kao opšti okidač — oblik koji produkcioni RPC nikad ne šalje): `test_ns006_t8_case_actions._reconcile` → `ManualCorrectionApplied` (scenariji: otkazano ročište, V2 stanje, završen predmet — nisu povlačenje izvora); `test_wave2_2d_source_invalidation` → događaj nosi `{rociste, roc-del-1}`, radnja nosi `dokaz.rociste_id` (kao stvarna radnja ročišta, Rule 1); `test_wave2_2f…stale_delayed_event…` → događaj brisanja nosi `{rociste, roc-1}`. Nijedna tvrdnja nije oslabljena.

**Procena uticaja na produkciju (READ-ONLY, samo GET; čitani tip, status, datumi, `predmet_id` i OZNAKE iz polja veze radi provere siročadi — bez ikakvog teksta; 2026-10-22):** izmerena; brojevi radnji i predmeta čuvaju se lokalno, van javnog repoa. Bitno za puštanje: većina otvorenih radnji (radnje motora rizika/Genome-a bez oznake izvora) nema polje dokazive veze; **0** otvorenih upućuje na dokument koji više ne postoji (provera siročadi gleda samo polja dokumenta, ne `rociste_id`); **nijedna** zatvorena radnja nema razlog (istorija ostaje bez razloga — backfill nije rađen niti je dozvoljen).

**Posledice puštanja (obelodanjeno):**
- Brisanje izvora više NE zatvara nijednu od tih radnji bez polja veze; ona od njih koja pri brisanju ispadne iz ciljnog skupa dobija `dokaz.zadrzano` i zatvara se tek sledećim opštim usklađivanjem (prijem dokumenta, ispravka, završetak predmeta), uz `CINJENICA_VISE_NE_VAZI` + `posle_zadrzavanja`.
- Za radnje motora rizika čiji `dedupe_key` zavisi od teksta problema: ako brisanje dokaza promeni tekst problema, stara radnja ostaje otvorena (zadržana), a nova se otvara — advokat do sledećeg opšteg događaja vidi obe.

**Odluka osnivača (BLOCKED_DECISION, podtačka — ne blokira C1):** zadržana radnja se danas zatvara **odloženo**, sledećim opštim događajem (koji ne mora biti povezan), uz navođenje zadržavanja. Alternativa — zadržana radnja ostaje otvorena dok je advokat ne zatvori — traži ručno zatvaranje radnje u V2 (nova funkcionalnost, van ovog sprinta). Preporuka: prihvatiti odloženo zatvaranje sa navođenjem.

**Preostala ograničenja:**
- `CINJENICA_VISE_NE_VAZI` kaže da činjenica više nije u stanju predmeta i koji događaj je to utvrdio; ne kaže ZAŠTO je nestala.
- Upis u audit ostaje non-fatal (postojeće); razlog na redu je atomičan sa statusom, pa zatvaranja nema bez razloga ni kad audit ne uspe.
- Trka dva usklađivanja: postojeća optimistička zaštita (`updated_at`), bez izmene; upis zadržavanja koristi isti uslov — ako ga istovremeni upis preduhitri, zadržavanje ostaje samo u auditu (`zadrzane_actions`), a kasnije zatvaranje ga neće navesti (status se ni tada ne menja tiho).
- Na redu se čuva samo POSLEDNJE zadržavanje: radnja zadržana brisanjem X pa brisanjem Y u `posle_zadrzavanja` navodi samo Y; X ostaje u auditu (`zadrzane_actions`).
- UI ne prikazuje `dokaz.zatvaranje`/`zadrzano` (nije menjan).

**Regresija:** širi skup (reconcile, NS006/NS007/NS008, Omega, Wave 2, VCR, workspace, A014–A017, MIR001), uz izolovan PG: **989 passed / 0 skipped / 0 failed**. Pun Python paket (pre dorade zadržavanja, bez podignutog PG-a): **15 failed / 11.797 passed / 337 skipped**; razlika prema osnovi (15 / 11.807 / 318): +9 testova C1; 19 PG testova preskočeno → posebno uz `VX_TEST_PG_DSN` (5 fajlova) **32 passed, 1 failed** = `test_wave10_test_db_bootstrap::test_deljeni_klasteri_i_dalje_rade` (isti nasleđeni pad); `test_optimistic_ui_contract_playwright::test_komentar_pad_mreze_CUVA_tekst` pao jednom na `Page.goto: Timeout 30000ms` (statička stranica, ne dodiruje Case Evolution) — sam 3/3, ceo fajl 15/15 → prolazna greška okruženja. Skup padova uz isto okruženje = osnova (0 novih). Pun paket se ponavlja u C4 na konačnom kodu.

**Independent reviewer finding:** 1. prolaz **FAIL** — (1) zadržana radnja se zatvarala sledećim nepovezanim događajem, a zatvaranje ga je pripisivalo samo tom događaju; ledger je to nazvao „pravilom osnivača“ → ispravljeno u kodu (`dokaz.zadrzano` + `posle_zadrzavanja`) i alternativa zabeležena kao odluka osnivača; (2) neobelodanjen efekat `dedupe_key` motora rizika; (3–4, 7) netačni numstat, opis idempotentnosti i opis procene produkcije; (5–6) test tvrdnji nije proveravao po događaju, nije bilo testa za završen predmet; (8) `None` u listi. Sve ispravljeno; mutacije 10/10. 2. prolaz **PASS**; neblokirajuće napomene (samo poslednje zadržavanje na redu; neprovereni upis zadržavanja pri trci; zastareli komentar testa; obim „dobijaju zadrzano“) unete; pun paket na konačnom kodu — C4.

**GATE-C1: PASS**

## TASK-C2 — Full document evidence extraction

**Baseline SHA:** `a30de1b2` (C1). **Changed files:** `routers/evidence.py`, `shared/evidence_graph.py`, `routers/case_dna.py` (zaglavlje skraćenog teksta), `tests/test_mir001_c2_ceo_dokument.py` (nov, 10 testova), `tests/test_ns006_t4_evidence_graph.py` (pooštren), `tests/test_mir001_t03_kontinuitet.py` (zastareo komentar „najviše 5“); dokaz stvarnog modela u `docs/v2-execution/mir001_c2_model/` (sirovi izlazi 1–5) + skripta `docs/v2-execution/MIR001_C2_STVARNI_MODEL.py`. Bez migracije, bez nove arhitekture.

**Granica i putanje (C0, R2):** `routers/evidence.py::_klasifikuj_dokument` slao je modelu `tekst[:1500]`; `klasifikuj_i_sacuvaj` upisivao ≤ 5 činjenica. Pozivalac dobija ceo `tekst` (Smart Intake finalize → `_consequence_evidence_classify` čita ceo `tekst_sadrzaj`). Genome čita ≤ 4.500 znakova teksta po dokumentu, ostatak je odbacivao **tiho**; tvrdnje (katalog ≤ 60) su jedini kanal kojim kasna činjenica stiže do Genome-a i V2 protivrečnosti. Posle C2 proba R2 iz C0 **pada po nameri** (činjenica je u poruci klasifikatora; dokument od 5.248 znakova → 2 poziva) — R2 u tabeli C0 je ovim zamenjen.

**Ispravka (postojeća infrastruktura: isti klasifikator i poziv modela, isti primitiv upisa `upisi_dokaze` koji tvrdnju utemeljuje u CELOM tekstu):**
1. `_klasifikuj_ceo_dokument` — prozori od **4.000 znakova, preklop 200, najviše 6 (≈ 23.000 znakova, ≤ 6 poziva gpt-4o-mini)**. Prvi prozor daje vrstu, elemente, oznake i činjenice; sledeći samo činjenice. Duplikati (ista činjenica, normalizovan razmak/velika slova/završna tačka) se spajaju. Prozor čiji poziv padne — ili je **prekinut** (`finish_reason == "length"`) — ostaje NEpročitan; prvi prozor u tom slučaju = neuspeh klasifikacije kao i do sada.
2. **Granica od 20 činjenica po dokumentu (ranije 5) deli se naizmenično po prozorima** (prva iz svakog prozora, pa druga…), a model ih vraća „od najodlučnije“ — odbacivanje ne pogađa samo kraj dokumenta. Pravni element prvog prozora (model ga daje po poziciji, bez veze sa činjenicom) više ne prelazi na činjenice kasnijih prozora.
3. **Stanje čitanja je eksplicitno**: `ai_tags._ekstrakcija = {ukupno_znakova, procitano_znakova, potpuno, prozora, neprocitani_prozori, cinjenica_izdvojeno, cinjenica_odbaceno, cinjenice_potpune}`; graf dokaza (`/api/predmeti/{id}/genome-v2` → `dokazi.dokumenti[].klasifikacija.citanje`) izlaže `potpuno`, znakove, `cinjenica_odbaceno` i `cinjenice_potpune`. Bez zapisa ključ `citanje` ne postoji = nepoznato — nikad „potpuno“.
4. Genome: zaglavlje skraćenog dokumenta `TEKST SKRAĆEN: prikazano prvih N od M znakova; činjenice iz ostatka mogu biti samo u bloku EVIDENCE VAULT ispod (ako su izdvojene)`.
5. **Upit klasifikatora**: činjenice su **doslovni izvodi** iz teksta (ista slova, bez dodavanja dijakritika, ista interpunkcija, bez spajanja podataka iz različitih rečenica), do 8 po izvodu, poređane od najodlučnije, sa prednošću priznanja, odluka, rokova, uručenja, iznosa i datuma „bez obzira na to gde se u izvodu nalaze“; pojašnjenje taksonomije: izjašnjenje stranke je `podnesak` i kad se odnosi na nalaz veštaka.
6. **Izlazni budžet modela 600 → 1.500 tokena** (eksplicitna konstanta, izmeren: gust prozor 397–911 izlaznih; sa 1.000 je 1/25 poziva prekinuto) + otkrivanje prekida (tačka 1).

**Stvaran gpt-4o-mini** (produkcioni parametri iz koda; samo sintetički tekst; sirovi izlazi u `docs/v2-execution/mir001_c2_model/`):

*A. Gust dokument (KONAČNO, fajl 4; skripta `MIR001_C2_STVARNI_MODEL.py`):* 16.082 znaka, 5 prozora, ~40 datiranih činjenica u konkurenciji (fakture, uplate, otpremnice, reklamacije); presudno priznanje duga (dopis 118/26, 2.345.678,00 din.) na poziciji 12.370 = **4. prozor**, obična rečenica bez najave. Isti tekst, stari upit (`a30de1b2`) naspram novog, oba kroz nove prozore, k/5:

| Mera | stari upit | novi upit |
|---|---|---|
| presudna činjenica postaje tvrdnja (posle granice od 20) | 0/5 | **5/5** |
| produkcioni lokator (`lociraj_tvrdnju`) je nalazi u tekstu | 0/5 | **5/5** |
| locirane činjenice ukupno | 0/66 | **99/100** |
| prekinut odgovor | 0/25 | 0/25 |
| tokeni po dokumentu (ulaz / izlaz) | ≈ 9.060 / ≈ 2.600 | ≈ 9.940 / ≈ 3.500 |

Izdvojeno 34–40 činjenica, upisano 20 (`cinjenica_odbaceno` 14–20, `cinjenice_potpune: False` — vidljivo). Jedina nelocirana činjenica ima **pogrešan datum** (reklamacija „11.03.2025.“ umesto 13.02.2025. — datum iz susedne rečenice): 1/100 izmišljeno pripisivanje, lokator ga ispravno ne locira (tvrdnja nije „pronađena u dokumentu“). Sa izlaznim budžetom 1.000 (fajl 3) isti test: 5/5 i 98/100, ali **1/25 poziva prekinut** (3. prozor, otkriveno, `potpuno: False`) → budžet 1.500.

*B. Kratak dokument, prva verzija upita (fajlovi 1–2; skripta `mir001_c2_model/skripta_kratak_v1.py`):* 4.599 znakova, priznanje na 4.364, uvedeno rečima „Odlučno je da…“ u kratkom 2. prozoru (≈ 800 znakova) — **lak test**. Prozori + stari upit: 0/5 (model vraća opšte opise, „tuženi priznao dug“ bez iznosa/datuma/akta u 4/5); prozori + upit v1 („što bliže doslovnom“): 5/5 izdvojeno, ali **nijednom locirano** (parafraza, dijakritike) i u 4/5 izmišljeno „platio prvu turu 15.01.2025.“ (datum isporuke pripisan plaćanju). To je razlog za upit v2 (doslovni izvod). „Stari put“ (1 izvod od 1.500) u fajlu 1 meren je starim upitom (≈ 1.011 ulaznih / ≈ 196 izlaznih tokena), u fajlu 2 novim — činjenica na 4.364 u oba slučaja nije u izvodu, pa je 0/5 trivijalno.

*C. Vrsta dokumenta, 7 kratkih Golden Case dokumenata (fajl 5 + ugrađeno u fajlove 3–4):* 3× po upitu: identično, 3/3 po dokumentu. Ukupno kroz sve krugove DOK-06 (izjašnjenje na nalaz): stari upit `podnesak` 4/5, `vestacki_nalaz` 1/5 (nestabilan već na osnovi); novi upit sa pojašnjenjem taksonomije `podnesak` 4/4; novi upit BEZ pojašnjenja (fajl 3) `vestacki_nalaz` 1/1 — razlog za pojašnjenje.

**Ovo su sintetički dokumenti, k/5 — nije stopa pouzdanosti nad stvarnim spisima.**

**Prihvatni kriterijumi** (`tests/test_mir001_c2_ceo_dokument.py`; stvaran prijem, PDF ekstrakcija, dispečer, PRAVI klasifikator; zamena modela „vidi“ samo poslati prozor; **10/10**):

| Kriterijum | Test | Ishod |
|---|---|---|
| kasna činjenica dostupna | iza 4.500. znaka → tvrdnja; Genome je vidi kroz katalog tvrdnji; gust dokument (8 činjenica po prozoru, 6 prozora) — odlučna činjenica u prozoru ≥ 4 preživi granicu od 20 | PASS |
| izvori ostaju ispravni | `dokument_id` svog dokumenta; pravni element samo uz svoju činjenicu; izmišljena činjenica nije `LOCIRANA_U_DOKUMENTU`, stvarna jeste | PASS |
| više dokumenata može da protivreči | dve kasne činjenice (iza 4.500. znaka) iz dva dokumenta → V2 protivrečnost sa stranama u oba dokumenta | PASS |
| bez tihog izostavljanja / eksplicitne granice | > 23.000 znakova → `potpuno: False`, kasna činjenica nije tvrdnja, graf to kaže; pad prozora i prekinut odgovor → `neprocitani_prozori: [2]`, `potpuno: False`; > 20 činjenica → `cinjenica_odbaceno`, `cinjenice_potpune: False`, vidljivo u grafu; Genome „TEKST SKRAĆEN“ | PASS |
| bez duplikata | činjenica u preklopu (3.800–4.000), poslata u oba prozora → jedna tvrdnja | PASS |
| bez OCR regresije / kratak dokument kao ranije | 1 poziv, ista tvrdnja; Golden Case (sken DOK-05, Tesseract) i OCR testovi u regresiji | PASS |

**Mutacije** (binarni harness, vraćeno bajt-identično): **12/12 uhvaćeno** — samo prvi prozor; `potpuno` uvek True; bez spajanja duplikata; pad prozora računat kao pročitan; granica 5; element prvog prozora uz kasne činjenice; bez preklopa; Genome tiho skraćuje; `citanje` se ne izlaže; granica po redu prozora (kasne prve ispadaju); prekinut odgovor se ne otkriva (uhvaćena tek kad je test vratio ISPRAVAN JSON uz `length`); `cinjenice_potpune` uvek True. Upit nije mutaciono proverljiv zamenom modela — meri ga stvaran model (A–C).

**Pooštren postojeći test:** `test_ns006_t4_evidence_graph::test_pala_klasifikacija_ostaje_neuspeh` — uspešno klasifikovan D1 mora nositi i `citanje = {potpuno: True, 163/163, odbačeno 0, cinjenice_potpune: True}`; pala i neklasifikovana klasifikacija nemaju `citanje`.

**Regresija:** evidence/Genome/case_dna/MIR001/NS006/NS007/VCR/A01x/Wave 2/Smart Intake/OCR, uz izolovan PG: **1.237 passed / 1 skipped / 0 failed**. Pun paket — C4.

**Preostala ograničenja (obelodanjeno):**
- Dokument duži od ≈ 23.000 znakova (≈ 8–10 strana) čita se DELIMIČNO (zabeleženo); činjenica iza te granice ne postaje tvrdnja.
- 20 tvrdnji po dokumentu: kod gustog dokumenta odbačeno je 14–20 izdvojenih činjenica (zabeleženo, `cinjenice_potpune: False`); naizmenična podela čuva najodlučnije iz svakog prozora samo ako ih model zaista stavi na vrh — sa 6 prozora preživi ≈ prve 3 po prozoru; u A je presudna bila 3. u svom prozoru u 4/5 i 2. u 1/5 (tesna margina).
- Genome i dalje čita ≤ 4.500 znakova teksta po dokumentu; kasne činjenice stižu SAMO kroz katalog tvrdnji (≤ 60, LIM-MIR-03-2) — sa do 20 po dokumentu, predmet od 3+ gusta dokumenta udara u tu granicu (tada `tvrdnje_izostavljene` + PARTIAL, eksplicitno).
- Model i dalje može pogrešno pripisati podatak (1/100 u A); lokator to hvata (tvrdnja nije „pronađena u dokumentu“), ali je tvrdnja upisana.
- Duplikati se spajaju samo pri istom tekstu; drugačije sročena ista činjenica iz dva prozora ostaje dvaput (doslovni izvodi to čine retkim).
- Upit važi za sve dokumente; vrsta je merena na 7 kratkih sintetičkih (identično starom), ne na stvarnim.
- `reklasifikuj` ne proverava `klasifikovan_at`, a `upisi_dokaze` ne deduplikuje: ponovna klasifikacija upisuje do 20 novih tvrdnji pored starih (ranije do 5) — postojeće ponašanje, uvećano. Zato ponovna klasifikacija starih dokumenata NIJE preporučena bez odluke osnivača.
- Na dokumentu kom je advokat odredio vrstu, ponovna klasifikacija upisuje nove tvrdnje, a `_ekstrakcija` može ostati iz ranije ekstrakcije (QA-02 ne prepisuje `ai_tags`).
- Prazan tekst se beleži kao delimičan (`potpuno: False`, 0/0) — konzervativno.
- UI ne prikazuje `citanje` (nije menjan); vidi ga API.
- Stari dokumenti (pre puštanja) ostaju pročitani 1.500 znakova bez zapisa (`citanje` = nepoznato).
- Trošak: do 6 poziva gpt-4o-mini po dugom dokumentu; gust dokument od 16.000 znakova ≈ 9.900 ulaznih + 3.500 izlaznih tokena (pre C2: 1 poziv, ≈ 1.000 + 200).

**Independent reviewer finding:** 1. prolaz **FAIL** — (1) granica od 20 je odbacivala kasne prozore uz `potpuno: True`; (2) produkcioni lokator nije nalazio presudnu činjenicu 5/5 (parafraza, dijakritike) — ledger je tvrdio „gotovo doslovne“; (3) „bez izmišljenih podataka“ netačno (izmišljen datum plaćanja 4/5); (4) izlaz blizu 600 tokena, prekid neotkriven; (5–8) pogrešna osnova troška, neponovljiv JSON, lak sintetički test, nedostajuća ograničenja. Ispravljeno u kodu (naizmenična granica + `cinjenice_potpune`, doslovni izvodi, otkrivanje prekida, budžet 1.500 izmeren) i ponovo izmereno stvarnim modelom na težem dokumentu; mutacije 12/12. 2. prolaz **PASS** (reviewer je sam rekonstruisao tekst i pustio produkcioni lokator nad sirovim izlazima); neblokirajuće napomene unete (preciznija formulacija veze elementa, margina rangiranja, string umesto liste činjenica → ignoriše se).

**GATE-C2: PASS**

## TASK-C3 — Procedural-state-aware drafting

**Baseline SHA:** `3c8e1de8` (C2). **Changed files:** `routers/multi_agent.py` (+113/−2), `tests/test_mir001_c3_procesno_stanje.py` (nov, 9 testova); dokaz stvarnog modela `docs/v2-execution/mir001_c3_model/` (snimljene poruke, svi nacrti, `SLEPE_OZNAKE.md` — nezavisno ručno čitanje, `c3_provera_konacno.json`, `ponovi_t06.py`). Bez novog agenta, bez nove orkestracije (nijedan dodatni poziv modela), bez migracije; pregled, izmena, odobrenje i DOCX nepromenjeni (T06 testovi 6/6).

**Reprodukcija (isti sintetički slučaj, stvaran gpt-4o, produkcioni parametri):** TASK-06 i ponovo na `3c8e1de8` (posle C1/C2). Po slepom čitanju (`SLEPE_OZNAKE.md`): **A** (traži odbijanje / protivi se dopuni koju je sud prihvatio u DOK-07) — TASK-06 4/5 i 3/5, osnova 3/5; **B strogo** (A ili, bilo kojim rečima, da je naložena dopuna / uvid u dnevnik nepotreban) — 4/5, 3/5, 4/5.

**Da li odluka stiže do nacrta i zašto je model ignoriše:** STIŽE — „Sud prihvata predlog za dopunu vestacenja.“ je u poruci (tekst DOK-07, znak 1.542 od 6.226). Ali je zakopana usred spisa pod opštim pravilom „utvrdi procesno stanje“, a zadatak traži izjašnjenje na DOK-06 u kom tuženi PREDLAŽE dopunu — model polemiše sa predlogom. Server je odluke već izdvajao deterministički (`_odluke_suda`, TASK-06) — samo u napomenu za advokata, ne u poruku.

**Ispravka:**
1. `_procesno_stanje_za_nacrt` — za `/api/agents/run`, agent `drafting`, verifikovan predmet: izdvojene odluke idu u poruku kao blok **PROCESNO STANJE — ODLUKE SUDA, NALOZI I ROKOVI**, posle spisa, neposredno pre zahteva; redovi (tekst dokumenta, T3) u **granici poverenja** (`zapakuj_nepoverljivo`); natpis i pravilo piše server („ne predlaži ponovo, ne protivi se i ne tvrdi da je nepotrebno; navedi odluku sa oznakom i predloži ono što procesno sledi; ako ne možeš pouzdano da utvrdiš — `[PROVERITI PROCESNO STANJE: …]`“). **Bez pronađene odluke blok se ne dodaje.**
2. `_protivreci_odlukama` + `_oznaci_protivrecnosti` — leksička provera POSLE modela: rečenica koja sa odlukom deli ≥ 2 osnove reči (latinica bez dijakritika, đ → dj) i kaže da je prihvaćeno/naloženo nepotrebno (`nije/nisu potreb|neophod|nužan…`, `ne postoji/nema potreb`, `nepotreb`, `suvišn`, `izlišn`), protivi mu se ili traži odbijanje — ili ponovo predlaže ono što je sud ODBIO — dobija `[PROVERITI PROCESNO STANJE: DOK-NN — odluka]` posle TAČNE rečenice (po poziciji; ponovljena rečenica = dve oznake; kraj rečenice je `.!?` iza kog sledi razmak ili novi red — tačka u iznosu/datumu („3.150.000“, „15.07.2026.“) i posle skraćenice („br.“, „čl.“, „str.“) NIJE kraj, pa oznaka nikad ne seče iznos), u odgovoru i u nacrtu na pregledu; napomena dodaje „PAŽNJA: N mesto/a … možda protivreči odluci suda“. Ne označava: negiranu negaciju („ne protivi se“, „neće se protiviti“, „nema primedbi“) i protivljenje navodima stranke — osim kad rečenica pominje i predlog, a NE navodi da je sud o njemu već odlučio. **Čuvar citata i evidencija izvora rade nad tekstom modela PRE oznake** (oznaka nosi tekst dokumenta i ne sme postati „citat“). Zaključci se ne menjaju, ništa se ne briše.

**Stvaran gpt-4o — po SLEPOM čitanju** (nezavisni označivač, bez uvida u proveru; `SLEPE_OZNAKE.md`):

| Mera | pre C3 (TASK-06 ×2 + osnova = 15 nacrta) | posle C3 (blok; 40 nacrta) |
|---|---|---|
| (A) traži odbijanje / protivi se dopuni kao otvorenom pitanju | 10/15 | **0/40** |
| nacrt navodi odluku (DOK-07) | 2/5 (osnova) | **40/40** |
| (B strogo) A ili tvrdnja da je naložena mera nepotrebna | 11/15 | **20/40** (+ 9 graničnih) |
| od (B strogo) — označeno na mestu provere | — | **18/20**; neoznačeno **2/40** (+ 9 graničnih neoznačenih) |

**Pravilo u upitu samo za sebe uklanja (A), ali NE (B)**: polovina nacrta i dalje tvrdi da je naložena dopuna ili uvid u dnevnik nepotreban, najčešće odmah posle priznanja da je sud to naložio (samoprotivrečno). Procesnu doslednost tu pokriva samo oznaka na mestu + napomena — nacrt ostaje radni materijal na pregledu advokata. **Ovo NE ispunjava u potpunosti zahtev „spreči samouverene preporuke koje protivreče poznatoj odluci“**: izričit zahtev za odbijanje je uklonjen (0/40), ali samouverena tvrdnja „nije potrebno“ ostaje u 20/40 nacrta, od kojih je 2 neoznačeno.

**Provera — merenje (pošteno):** pravila su građena i doterivana nad ovim nacrtima, pa je sve osim prvog prolaza **unutar uzorka**. **Prvi prolaz nad nacrtima koje pravila nisu videla (val1–val4, 20 nacrta):** 8/9 protivrečnih nacrta označeno (promašaj „nije nužan“ — greška obrasca), 0 lažno pozitivnih nacrta, 1 lažno pozitivna rečenica („protivi se tvrdnjama tuženog …, jer je sud već prihvatio predlog …“, val3 N1); oba ispravljena posle toga (lažno pozitivna rečenica se u 2. prolazu kapije vratila zbog izuzetka „predlog“ — ponovo ispravljena i pokrivena testom; na konačnom kodu 0 lažno pozitivnih rečenica u 55 nacrta prema slepom čitanju je TVRDNJA UNUTAR UZORKA). Konačna provera naspram slepih oznaka na svih 55 nacrta sa DOK-07: **29/31 (B strogo), 0 lažno pozitivnih nacrta, 0/10 graničnih** — unutar uzorka. Ručne oznake iz 1. prolaza kapije bile su vezane za rečnik provere i promašile su očigledne protivrečnosti — zamenjene slepim. **Jedan sintetički slučaj, jedna vrsta odluke — nije stopa pouzdanosti nad stvarnim spisima.**

**Negativni scenario** (DOK-07 obrisan stvarnom rutom; nema odluke u spisu): blok se ne dodaje, provera se ne pokreće, nema oznake; stvaran gpt-4o 5/5 normalno argumentuje (protivljenje dopuni je tu legitimno), 0/5 tvrdi nepostojeću odluku suda, 0/5 `[PROVERITI PROCESNO STANJE]` — **nije pogrešno blokiran**. (Isti skup ima druge greške izvora — v. ograničenja.)

**Ostali kriterijumi (stvaran model, 35 nacrta sa konačnim pravilom, merila iz TASK-06):** tvrdnje sa izvorom (DOK-05 i DOK-06 navedeni) 35/35; nedostajući podaci označeni `[PROVERITI]` 34/35; bez izmišljene adrese 35/35 (merilo prepoznaje samo ulicu/broj — v. ograničenja); „nepotvrđeni član zakona ne kao potvrđen“ 35/35 je **prazno merenje** — nijedan nacrt ne navodi član zakona, pa to nije dokaz da čuvar citata radi; trošak: +935 znakova poruke (≈ 250 tokena) po nacrtu sa odlukama, bez dodatnog poziva modela.

**Testovi** (`tests/test_mir001_c3_procesno_stanje.py`, Golden Case, stvarna ruta, staging; **9/9**): blok sa DOK-07 u granici poverenja, posle spisa, pre zahteva, pravilo van granice; bez odluke (DOK-07 obrisan rutom) — bez bloka i oznake; protivrečne rečenice označene u odgovoru i na pregledu + napomena; dosledan nacrt netaknut; drugi savetnici bez bloka i oznake; ponovni predlog odbijenog, negirane negacije, navodi stranke, jedna opšta reč, „nužan“, đ → dj; ivični slučajevi kapije (zakazivanje se ne veže, ponovljena rečenica = dve oznake na dva mesta, množina, „ne postoji potreba“, „izlišna“, navodi + predlog); čuvar citata vidi tekst modela bez oznake; iznos/datum/skraćenica u označenoj rečenici (oznaka ne seče „3.150.000“), val3 N1 nije označen.

**Mutacije** (binarni harness, vraćeno bajt-identično): **15/15 uhvaćeno** — blok se ne dodaje; blok van granice poverenja; blok i bez odluka; provera isključena; negirana negacija ignorisana; prag jedna zajednička osnova; đ → d; napomena ne broji; blok za sve savetnike; odbijena odluka se ne prepoznaje; oznaka po tekstu umesto po poziciji (uhvaćena tek kad je test dobio dve IDENTIČNE rečenice); čuvar citata posle oznake; navodi stranke izuzeti i kad pominju predlog; stari delilac rečenica (tačka u iznosu); navodi uz odluku suda nisu izuzeti.

**Regresija:** savetnici/nacrti/staging/DOCX/MIR001/QA-08/prompt_guard/OSB/NS005–NS008 (119 fajlova), uz izolovan PG: **1.243 passed / 9 skipped / 0 failed**. Pun paket — C4.

**Preostala ograničenja (obelodanjeno):**
- **(B) ostaje u 20/40 nacrta**; provera ih označava, ali ne sprečava; promašaji provere (potvrđeni slepim čitanjem): „dodatna veštačenja nisu potrebna“ (samo jedna zajednička osnova — „dodatno veštačenje“ nije „dopuna“), „nalaz … ne zahteva dodatne dokaze“; granični oblici („dodatni uvid neće promeniti utvrđene činjenice“, „nalaz je potpun“) se ne označavaju.
- Provera NE hvata: implicitan zahtev da se odluči bez naložene dopune („da sud na osnovu postojećeg nalaza donese odluku“ — oznaka tada stoji samo na drugoj rečenici istog nacrta), niti **ponovno predlaganje već PRIHVAĆENE/naložene radnje** (npr. „predlaže dopunu veštačenja“ kao nov dokaz — val3 N2) — ponovni predlog se proverava samo za ODBIJENE odluke.
- **(G1) Istekao rok**: nalog od 15.07.2026 „u roku od 15 dana“ istekao je ≈ 30.07.2026; nijedan nacrt sa DOK-07 ne pita da li je tuženi postupio, više njih ga tretira kao tekući. Blok ne računa ishod roka.
- Ponovljena radnja („i povlači zahtev … 600.000“, već učinjeno 15.07) u 2 nacrta (+3 granično); datum ročišta 18.11.2026 izostaje u većini nacrta; DEBT-MIR-06-2 (nalaz veštaka kao „utvrđen“) u većini nacrta.
- Odluke se prepoznaju **obrascem** (`_RE_ODLUKA_SUDA`), samo u DOSTAVLJENIM dokumentima, do 12 redova; redovi se uzimaju iz CELOG teksta uključenog dokumenta, pa i iz dela koji zbog budžeta nije poslat modelu (evidencija izvora tada kaže „delimično“, a blok ipak prenosi odluku); „u roku od N dana“ može biti i iz podneska stranke (natpis bloka kaže „po obrascu“).
- Samo `/api/agents/run` (`drafting`); `/run-parallel`, `/pipeline` i šablonski `/api/podnesak` nemaju ni blok ni proveru.
- Negativni skup: izmišljeno mesto („U Beogradu“), nalaz veštaka pripisan tuženom (neg N0), neusklađena vrednost spora — greške izvora koje C3 ne meri ni ne sprečava.
- Oznaka `[PROVERITI PROCESNO STANJE: …]` ulazi u tekst nacrta; advokat je uklanja pre podnošenja (kao postojeće `[PROVERITI: …]`).
- Delilac rečenica: datum ili oznaka sa brojem na KRAJU rečenice („…od 15.07.2026.“ bez „godine“, „…u DOK-07.“) spaja je sa sledećom; ako spojena rečenica sadrži negiranu negaciju („ne protivi se“), protivrečnost u drugoj rečenici se ne označava (potvrđeno sondom; u 60 stvarnih nacrta nije nastupilo).
- Izuzetak „sud je već odlučio“: rečenica koja se protivi navodima stranke i predlogu, prizna da ga je sud prihvatio, pa ga ipak nazove nepotrebnim, ne označava se (potvrđeno sondom; u nacrtima nije nastupilo).

**Independent reviewer finding:** 1. prolaz **FAIL** — ručne oznake vezane za rečnik provere (promašene očigledne protivrečnosti), „0/40“ i „55/55“ netačni, held-out precenjen, neobelodanjeni lažno negativni obrasci, lažno pozitivan nalaz za red zakazivanja, sudar oznaka, oznaka pre čuvara citata, zastareo komentar, nevidljive procesne nedoslednosti (istekao rok, ponovljeno povlačenje, 18.11), prazno merenje člana zakona → slepo ponovno označavanje nezavisnim označivačem, ispravke koda, testovi, ograničenja. 2. prolaz **FAIL** — delilac rečenica sekao iznos („3.150.000“) i propuštao rečenice sa datumom/skraćenicom; vraćena lažno pozitivna rečenica val3 N1 → ispravljeno, testovi, mutacije 15/15. 3. prolaz **PASS**; dve neblokirajuće napomene (datum na kraju rečenice; izuzetak „sud je već odlučio“) upisane u ograničenja.

**GATE-C3: PASS** — uz izričito obelodanjen preostali rizik: tvrdnja „nepotrebno“ o naloženoj meri ostaje u 20/40 nacrta (označeno 18/20).

## TASK-C4 — Release candidate evidence

**Baseline SHA:** `ea1bfba5` (C3). **Changed files:** `tests/test_mir001_c4_e2e.py` (nov), `docs/v2-execution/MIR001_FINAL_CLOSURE_REPORT.md` (nov), `docs/v2-execution/MIR001_C4_PROD_PROCENA.py` (nov, read-only GET skripta), ovaj zapis. Kod nije menjan.

**Jedan neprekinut E2E** (`tests/test_mir001_c4_e2e.py`; isti proces, baza, korisnik `uid-A`, predmet; stvarne rute, worker, Tesseract, dispečer, Genome, V2 projekcija, PRAVI klasifikator sa prozorima, usklađivanje case_actions, staging, DOCX, ruta brisanja; zamenjeni: pozivi modela, Pinecone, Supabase i prijava (baza u memoriji), atomski RPC brisanja (Python zamena, ne SQL funkcije 131/133/137), dozvole i naplata, `audit.log_action`, ocena kvaliteta nacrta, `asyncio.create_task` u savetniku) — **12/12 segmenata, 2 uzastopna pokretanja**: (01) spis 7 dok. + OCR; (02) dug dokument — činjenica iza 4.500. znaka postaje tvrdnja, `potpuno: True`, ≥ 2 prozora; (03) graf dokaza izlaže `citanje`; (04) Genome vidi činjenicu kroz katalog, tekst označen „TEKST SKRAĆEN“; (05) DOK-08 otvara rok-radnju; (06) odluka suda iz DOK-07 u poruci nacrta, u granici poverenja, pre zahteva; (07) protivrečna rečenica označena na mestu, iznos „3.150.000“ netaknut; (08) napomena broji, izmena, odobrenje bez promocije (broj vektora nepromenjen), DOCX bez oznake; (09) brisanje nepovezanog dokumenta ne zatvara ništa (pre brisanja ≥ 2 otvorene radnje, uključujući rok-radnju); (10) brisanje DOK-08 zatvara SAMO povezanu radnju sa `IZVOR_POVUCEN` i prethodnim stanjem u auditu; (11) ponovljena isporuka istog povlačenja ne menja ništa; (12) korisnik B ne vidi ni ne menja ništa od predmeta A.

**Regresija na konačnom kodu (`ea1bfba5` + C4 test), izolovan PG podignut:** pun Python paket **16 failed / 11.836 passed / 318 skipped / 2 xfailed** (osnova `f33dcce8`: 15 / 11.736 / 318; grana posle TASK-10: 15 / 11.807 / 318). +29 prolaza = 30 novih testova (C1 10, C2 10, C3 9, C4 1) − 1 prolazni pad. 15 padova = **identičan skup osnove**; 16. = `test_deadline_domain_playwright::test_ui_prazan_dan_ne_uzbunjuje`, `Page.goto: Timeout 30000ms` (statička stranica; `static/` grana ne menja) — sam 3/3, ceo fajl 5/5 (ista klasa kao jednokratni Playwright timeout u C1). V2 frontend: **51/51** skripti (`verify*` + `e2e*`); 3 skripte (`verify`, `verify:pozadina`, `verify:refinement`) traže lokalni server `serve.mjs` na 4317 — prvo pokretanje bez servera `ERR_CONNECTION_REFUSED`, sa serverom PASS (isto okruženje kao TASK-10).

**Pojedinačna klasifikacija 15 nasleđenih padova** (svi padaju i na `f33dcce8`, TASK-10; nijedan ne dodiruje fajlove ove grane):

| # | Test | Uzrok (iz poruke greške) | Klasa |
|---|---|---|---|
| 1–3 | `test_coi_intake_convergence::test_t8_slucaj_A/B/C…[trio]` | `ModuleNotFoundError: No module named 'trio'` (anyio parametrizacija) | okruženje — opcioni paket nije instaliran |
| 4–8 | `test_prg_night_register::…[trio]` (5) | isto: `No module named 'trio'` | okruženje |
| 9 | `test_faza1_pristupacnost::test_nema_teksta_ispod_11px` | 16 elemenata ispod 11px u legacy UI | postojeći dug legacy `static/` |
| 10 | `test_faza1_pristupacnost::test_gustina_nije_zrtvovana` | najmanja veličina 8.3px | postojeći dug legacy `static/` |
| 11 | `test_faza1_pristupacnost::test_izvor_van_zakljucanog_nema_sitan_tekst` | `vindex.css` 45 veličina < 11px | postojeći dug legacy `static/` |
| 12 | `test_ns003_protocol::test_fixture_hesevi_su_zakljucani` | heš zaključanog fixture-a se ne poklapa | postojeći (fixture menjan pre ove grane) |
| 13 | `test_rc_cold_start::test_r5_p0a_ugovor_commit_i_commit_source` | `commit` prazan u svežem procesu (nema `RENDER_GIT_COMMIT`) | okruženje |
| 14 | `test_rc_cold_start::test_r7_verify_prolazi_u_svezem_procesu` | `test_db.py verify` — klaster 127.0.0.1:55433 ne radi | okruženje (deljeni test klasteri) |
| 15 | `test_wave10_test_db_bootstrap::test_deljeni_klasteri_i_dalje_rade` | očekuje oba deljena klastera (55432, 55433) | okruženje |

**Pregled celog diff-a prema `origin/main`:** 79 fajlova, +8.746/−91 (pre C4 commita). Proizvodni kod: `routers/{case_dna,drafting,evidence,multi_agent,rok_odluka}.py`, `services/{case_evolution,v2_observation,v2_projection}.py`, `services/agent_tasks/case_change_brief.py` (nov), `shared/{claim_catalog,evidence_graph,genome_contract,rokovi}.py`, `workers/background_agents.py`, `frontend-v2-ng/{index.html, src/analiza-predmeta.js, danas.js, nacrt-predmeta.js, pripremljeno.js}`. **Nema**: migracija, izmena `requirements`/`pyproject`/`package.json`, `render.yaml`/Docker, `static/` (legacy UI), novih promenljivih okruženja u proizvodnom kodu, Cron-a. NS007 `case_change_brief` je registrovan, ali u produkciji ciklus autonomije ne radi (migracija 136 i Cron nisu napravljeni).

**Bojanovi tokovi** (klijent → predmet → otpremanje/OCR → klasifikacija → hronologija → rokovi/podsetnici → radnje → AI pregled): svi testovi tog lanca u punom paketu prolaze (`test_osb002_solo_tok`, `test_ns005_t11_rokovi_danas`, `test_ns005_t14_smart_intake`, `test_smart_intake_*`, `test_rokovi_lanac`, `test_ns3_n11_hronologija_poreklo`, `test_vcr002_t04_podsetnici`, …). Tok radi, ali je **ponašanje IZMENJENO** u ovim karikama:
- *Klasifikacija* (C2): novi dokumenti se čitaju celi (prozori, ≤ 6 poziva, ≤ 20 tvrdnji, nov upit, `_ekstrakcija`).
- *Rokovi* (TASK-07): rok iz obrisanog dokumenta se ne nudi na potvrdu (`/api/rokovi/kandidati` `izvor_povucen`, Danas bez „Potvrdi“).
- *Radnje* (TASK-07 + C1): legacy grana protivrečnosti isključena za predmete sa V2; protivrečnost iz obrisanog dokumenta se preskače; brisanje izvora zatvara samo radnje sa dokazivom vezom, uz razlog (`dokaz.zatvaranje` / `zadrzano`); `SourceInvalidated` bez izvora i brisanje ročišta bez `dokaz.rociste_id` ne zatvaraju radnju.
- *AI pregled — Genome* (TASK-03 + C2): sporne tačke se ne zatvaraju kad model nije video sve tvrdnje; do 60 tvrdnji u katalogu; zaglavlje „TEKST SKRAĆEN“.
- *AI pregled — savetnici* (TASK-04/05 + C3): ceo spis (do 12 dok.) i sporne tačke u kontekstu, današnji datum, bez „Snaga predmeta %“; parnična strategija sa procesnim stanjem; nacrt sa blokom procesnog stanja i oznakama protivrečnosti.
- *Pregled nacrta* (TASK-06): nacrt savetnika iz spisa ide na staging; odobren `nacrt_iz_spisa` se NIKAD ne indeksira u bazu znanja.
- *Autonomija* (TASK-08): `CASE_CHANGE_BRIEF` registrovan u NS007 (u produkciji ne radi bez migracije 136 i Cron-a).
Legacy UI (`static/`) nije menjan.

**Izmenjeni postojeći testovi** (14; „0 novih padova“ delom počiva na njima — svaka izmena kodira nameravanu promenu ponašanja):

| Test | Commit | Razlog |
|---|---|---|
| `test_qa08_izvori_savetnika` (+79/−19) | `b549b9fc` | TASK-04: granica 12 dokumenata u istom budžetu umesto 5; + upit spornih tačaka |
| `test_qa06_naziv_nedostavljenog` | `b549b9fc` | TASK-04: granica 12 — 14 dokumenata da bi DOK-01/02 i dalje bili izostavljeni |
| `test_genome_granica_poverenja` | `b549b9fc`, `d5c7a6c0` | TASK-04 granica 12; TASK-05 procenat snage se savetniku ne daje |
| `test_a003_contradiction_action_provenance` | `150feb7f` | TASK-07: lažna baza vraća dokumente na koje kontradikcije pokazuju (obrisan dokument se ne projektuje) |
| `test_ns007_t25_daily_cron_regression`, `test_ns007_t3_scheduler_boundary` | `c474e3b5` | TASK-08: `CASE_CHANGE_BRIEF` u registru agenata trajnog rada |
| `test_ns006_t8_case_actions` | `a30de1b2` | C1: opšti okidač `ManualCorrectionApplied` umesto `SourceInvalidated` bez izvora |
| `test_wave2_2d_source_invalidation`, `test_wave2_2f_integrated_adversarial` | `a30de1b2` | C1: događaj nosi izvor kao produkcioni RPC; radnja nosi `rociste_id` |
| `test_ns006_t4_evidence_graph` | `3c8e1de8` | C2: uspešna klasifikacija nosi `citanje` (pooštreno) |
| frontend `live-analiza`, `live-danas`, `live-pripremljeno`, `fixtures/pisanje-api` | `4b6c19aa`, `150feb7f`, `c474e3b5` | dodate provere novog prikaza (SPORNO, izvor povučen, pregled promene); fixture usklađen |

**Zavisnosti od produkcije bez odobrenja:** nema — sve provere lokalne/izolovane; produkcija je samo ČITANA, isključivo GET: C1 procena (tip, status, oznake polja veze) i C4 procena `MIR001_C4_PROD_PROCENA.py` (radnje, sporne tačke, akter/naziv/`dokument_id` reda hronologije, nazivi fajlova — bez teksta). C4 rezultat: legacy protivrečnosti na predmetima sa V2 0/3, radnje pregleda roka sa povučenim izvorom 0/4 → očekivano masovno zatvaranje pri puštanju = 0 (meriti ponovo pre puštanja). Stvarni modeli (gpt-4o-mini, gpt-4o) pozivani su ključem iz `.env` isključivo nad sintetičkim tekstom.

**Završni izveštaj:** `docs/v2-execution/MIR001_FINAL_CLOSURE_REPORT.md` — tabela `Requirement | Scenario | Evidence | Level | PASS/FAIL/BLOCKED | Remaining risk`, rešena i preostala ograničenja, migracije (nijedna), uticaj na produkcione podatke, plan kontrolisane produkcione E2E provere, plan povlačenja, odluke osnivača, tačni SHA-ovi. **Status: READY_FOR_FOUNDER_RELEASE_REVIEW** (sve četiri kapije PASS; C3b izričito FAIL — odluka osnivača). Nije `PRODUCTION_READY` ni `REAL_USER_ACCEPTED`.

**Independent reviewer finding:** 1. prolaz **FAIL** — izveštaj je potcenio zamene u E2E (baza, prijava, RPC brisanja, dozvole, naplata, audit), izostavio masovno zatvaranje pri prvom usklađivanju (TASK-07 ogr. 9), nepotpuno opisao izmene Bojanovog toka, nije obelodanio 14 izmenjenih postojećih testova, plan povlačenja bez rizika staging-a i „treperenja“ radnji, plan provere bez merenja pre/posle; seg. 08/09 slabi → sve ispravljeno, seg. pooštreni. 2. prolaz **FAIL** — radnje pregleda roka (pravilo `izvor_povucen`) nisu bile izmerene; zastareli navodi o čitanju produkcije; korak 0 na pogrešnom mestu; skripta bez straničenja → skripta proširena (straničenje, mera b), izmereno 0/4, navodi ispravljeni.

2. prolaz napomena: recenzent nije pokretao skriptu nad produkcijom (zabrana iz zadatka) — brojevi 0/3 i 0/4 su iz pokretanja koordinatora; skripta proverena čitanjem (samo GET). 3. prolaz **PASS**.

**GATE-C4: PASS** — MIR001 FINAL CLOSURE: **READY_FOR_FOUNDER_RELEASE_REVIEW** (sve četiri kapije PASS; C3b FAIL obelodanjen kao odluka osnivača). Nije PRODUCTION_READY ni REAL_USER_ACCEPTED.

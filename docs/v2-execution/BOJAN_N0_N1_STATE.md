# BOJAN N0 + N1 — REQUIREMENTS LOCKDOWN & SINGLE INTAKE CLOSURE — izvršni dnevnik

**Grana:** `feature/bojan-n0-n1-intake-closure` · **Početak:** `origin/main` = produkcija = `11475df8` (2026-10-26) ·
**Produkcija:** NOT_DEPLOYED (ništa spojeno, ništa pušteno) · Oznake: PROVEN / INFERRED / ASSUMED / UNKNOWN.

---

## N0 — izvor zahteva

### Pretraženo
- `docs/product/A018_BOJAN_REQUIREMENTS_REALITY_MATRIX.md`, `docs/product/BOJAN_WORKFLOW_GAP_ANALYSIS_2026-08-02.md`,
  `docs/product/BETA_CRITICAL_PATH_2026-08-02.md`
- `docs/v2-execution/VCR001_REQUIREMENTS_MATRIX.csv`, `docs/v2-execution/VCR002_REQUIREMENTS_STATE.md`
- `.vindex_ai_team/EXECUTION_STATE/2026-08-02_bojan-beta-mission-001-intake-integrity.md`
- neverzionisani izveštaji u glavnom radnom stablu: `A018 — BOJAN REQUIREMENTS REALITY MATRIX.md`, `BOJAN-BETA-FORENSIC-AUDIT-001.md`,
  `SPRINT-B2 — BOJAN WORKFLOW CLOSURE REPORT.md`, `FOUNDER-ACCESS-BOJAN — HARD STOP FINDING.md`,
  `VINDEX-MIROSLAV-BOJAN-CANONICAL-STATE-FORENSIC-REPORT.md`
- transkripti sesija: avgustovske sesije (2026-08-02, kada je osnivač preneo Bojanov tok) **nisu sačuvane**; najraniji
  sačuvan unos sa „Bojan“ je MIR001 (2026-10-22), i on se odnosi na Miroslava.
- Dokument „VINDEX — CANONICAL OPERATING RULES“ nije pronađen pod tim imenom u repou (pravila se primenjuju iz zadatka).

### Nalaz
| # | Zahtev (kako je zapisan) | Izvor | Oznaka | Stanje |
|---|---|---|---|---|
| R1 | Intelligent Intake: novi klijent → predmet → upload → OCR + ekstrakcija → popunjavanje predmeta | gap analiza, Phase 1 (osnivačev prenos, prevod) | INFERRED | **N1 ovog sprinta** |
| R2 | Automatic Case Organization: klasifikacija, hronologija iz sadržaja dokumenata | gap analiza, Phase 2 | INFERRED | klasifikacija postoji; više događaja iz dokumenta NE postoji (N2) |
| R3 | Deadlines & Obligations: rokovi, obaveze, podsetnici | gap analiza, Phase 3; A018 B9–B11 | INFERRED | jedan rok po dokumentu; podsetnici: kod u main-u (PR #57), Render `CRON_SECRET` čeka osnivača |
| R4 | AI Case Assistant („razumi moj predmet“) | gap analiza, Phase 4 | INFERRED | Genome postoji; lanac događaj → posledica nije potpun (kanon audit 2026-09-10) |
| R5 | Court Workflow (najniži prioritet) | gap analiza, Phase 5 | INFERRED | nije istraživano (van N1) |

- **Doslovni Bojanov tekst: `REQUIREMENT_SOURCE_MISSING`** (nijedan od pet). Pet faza su osnivačev prenos, ne Bojanove reči.
- **Kontradikcija (UNKNOWN):** A018 kaže „od njegove **četiri** izričite stavke“, a imenuje samo dve (podsetnici, OCR skeniranog
  dokumenta). Izvor četiri stavke nije pronađen. Ne menja N1: obe imenovane su pokrivene (OCR ovde; podsetnici N-kasnije).
- B1–B13 (A018) **nisu** proglašeni za pet zahteva — to je inženjerska matrica, ne Bojanov tekst.

### N1 acceptance ugovor (zaključan)
**Ulaz:** nov ili postojeći klijent; opis problema/cilja; ≥ 4 sintetička dokumenta (digitalni PDF, skenirani PDF, fotografija
JPG/PNG, DOCX); bar jedan sa izdvojivim strukturisanim podacima.
**Obrada:** prijava; provera sukoba; OCR i obrada; AI ekstrakcija gde postoji; pregled i ispravka; jedan predmet (nov ili
postojeći); svi dokumenti vezani za taj predmet.
**Izlaz:** 1 predmet; ispravan klijent; dokumenti vezani za taj predmet (4 kad je OCR dostupan); sačuvan opis; očuvano poreklo
(posao → dokument → entitet, original + ispravka); istinita stanja obrade; nastavak posle reload-a; predloženi rok NIJE potvrđen.
**N0 GATE: PARTIAL_SOURCE_MISSING** — ugovor je dovoljno određen za N1; izvorni tekst nedostaje.

---

## N1.1 — postojeći tok pre izmena (PROVEN merenjem)

Tok koji V2 nudi za Bojanov opis: **Nov predmet → Iz opisa problema** (predlog → klijent → provera sukoba → `POST /api/intake/kreiraj`)
→ **Predmet → Prijem** (Smart Intake: otpremanje više fajlova → worker/OCR → pregled/ispravka → prikačivanje ISTOM predmetu).
Drugi ulaz: **Iz dokumenta** (finalize bez `predmet_id` otvara predmet, ostali dokumenti sesije idu u njega).

Osnovno stanje (pre izmena, `11475df8`): `live-prijem-carobnjak-e2e` 37/37, `live-prijem-oporavak-e2e` 18/18, `live-solo-tok-e2e`
23/23; pytest intake/OCR/COI/klijenti 920 pass, 3 fail (`[trio]` — `trio` nije instaliran lokalno; `[asyncio]` varijante prolaze).

Zlatni E2E (`frontend-v2-ng/tests/live-zlatni-prijem-e2e.mjs`) nad nepromenjenim kodom: **29/38**. Pet stvarnih prekida:

| # | Prioritet | Defekt | Dokaz | Oznaka |
|---|---|---|---|---|
| D1 | A identitet | „Iz dokumenta“, nepoznat ishod finalize-a: server JE otvorio predmet, UI kaže „Ovaj dokument je već prikačen **drugom** vašem predmetu“, a sledeći dokument nudi „Otvori predmet iz ovog dokumenta“ → drugi predmet iz iste sesije | E4 (route: fetch pa prekid veze) | PROVEN |
| D2 | F finalizacija | „Iz opisa“, nepoznat ishod `kreiraj`: dugme ostaje aktivno; posle prozora od 5 s ponovni klik pravi **drugi predmet** | E3: 2 predmeta istog naziva | PROVEN |
| D3 | E OCR | worker pri neuspelom OCR-u upisuje `intake_documents.ocr_used=True`; posle potvrde pregleda V2 piše „tekst pročitan OCR-om“ za dokument koji nije pročitan; metrika OCR-a broji neuspeh (krši B3) | UI tekst posla „08 …“; red u bazi | PROVEN |
| D4 | E OCR | finalize dokumenta bez teksta vraća `razlog: "prazan_tekst"` (nikad se ne prikačuje), a UI kaže „Ponovite prikačivanje — ništa neće biti duplirano“ i nudi dugme koje ne može da uspe | pytest dijagnoza + UI | PROVEN |
| D5 | D dokumentacija | `.pdf`/`.docx` primljen po ekstenziji: tekst pod `ugovor.docx` šifrovan, sačuvan i ponavljan kao prolazna greška (minutima) do „failed“ | pytest: `received`, `attempts=1`, „Package not found“ | PROVEN |

Nije defekt (proveriti, ne menjati):
- **Provera sukoba nije serverska nigde** (ni `/api/intake/kreiraj`, ni `/api/predmeti/{id}/confirm-links`, ni `/api/predmeti`).
  U V2 je kapija u UI-ju na svakom putu koji povezuje klijenta (Iz opisa, kartica Klijenti), a „Iz dokumenta“ izričito kaže da je
  provera zakazana u pozadini i da to nije rezultat. Direktan API poziv prijavljenog advokata može je preskočiti za SVOJ predmet;
  tuđe podatke ne otvara. PROVEN. **Serverska obaveznost = poslovna odluka osnivača** (menja semantiku „ručno“ i „iz dokumenta“).
- Opis spora se ne prikazuje u pregledu predmeta, ali je dostupan u „Izmeni podatke“ (`izm-opis`). PROVEN.
- Posle reload-a poslovi prijema nisu izlistani u predmetu; poslovi na pregledu su u Radnoj listi (`/api/workspace` → za_pregled),
  a ponovno otpremanje istog sadržaja prikazuje postojeći posao sa ispravkama. PROVEN (dizajn, ne menjano).
- Pravilo „predmetu se prikačuje samo dokument sa izdvojenim tekstom“ (`prazan_tekst`) **nije menjano** — popravljeno je samo da
  UI kaže istinu (D4). Da li nepročitan sken treba prikačiti bez teksta: odluka osnivača.

---

## N1.2 — ispravke (najmanje potpune)

| # | Fajl | Izmena |
|---|---|---|
| D1 | `frontend-v2-ng/src/prijem-predmeta.js` | `trenutni.otvara` = ID posla koji otvara predmet (vlasnik): dok ishod nije poznat, DRUGI dokument ne sme da otvori predmet i to mu se kaže; ponovno čitanje posla (`usvojiIliOslobodi`) usvaja `job.predmet_id` kao predmet sesije; posao bez predmeta NE skida blokadu (zahtev može još biti u redu na serveru) — samo isti posao sme da ponovi otvaranje (server ga atomski zauzima, zakasneli prvi zahtev ne otvara drugi predmet) |
| D2 | `frontend-v2-ng/src/nov-predmet-prijem.js` | pre slanja: ID-jevi predmeta tačno tog naziva (`GET /api/predmeti?q=&view=summary`); posle nepoznatog ishoda (uz 2,5 s čekanja na upis u toku): ponovno čitanje i poređenje — 1 nov = otvoren (prelaz na njega), 0 = nije (sme ponovo), inače otvaranje pod TIM nazivom zaključano (`sumnja = naziv`) |
| D3 | `shared/intake_worker.py` | `ocr_used=bool(ocr_used)` (stvarna vrednost ekstraktora) umesto `True` |
| D4 | `frontend-v2-ng/src/prijem-predmeta.js` | `prazan_tekst` u odgovoru prikačivanja → tačna poruka („ponovno prikačivanje neće pomoći“), bez dugmeta „Ponovi prikačivanje“; isto za otvaranje iz dokumenta; segmentiran dokument sa delom bez teksta kaže da taj deo neće biti prikačen. **Ograničenje:** posle reload-a stanje posla ne nosi razlog, pa se prvo prikaže opšte „Ponovite prikačivanje“; jedan pokušaj zatim vraća tačan razlog |
| D5 | `routers/smart_intake.py` | potpis sadržaja pri otpremanju: PDF (`%PDF-` u prvih 1024 B), DOCX (`PK\x03\x04`) — isto pravilo kao postojeće za JPEG/PNG; odbijen fajl se ne čuva i nema posla |

Bez migracija, bez nove rute, bez promene vizuelnog identiteta. Izmenjeni postojeći testovi (staro očekivanje protivreči zahtevu D):
- `tests/test_vcr001_t01_prijem_adversarial.py::test_png_pod_imenom_pdf_nije_lazno_zavrsen` — ranije „primljen, pa nikad lažno
  završen“; sada „odbijen odmah, bez posla“ (invarijanta „nikad prikačen“ ostaje i jača je).
- `tests/test_sprint002_pipeline_b_orphan_prevention.py` — podrazumevani sadržaj `b"fake bytes"` → `b"%PDF-1.4 fake bytes"`; predmet
  testova (skladište/red) nepromenjen.

Test harness: `tests/osb003_solo_server.py` dobija `GET /__osb003/zlatni` (relacije i identiteti, bez sadržaja dokumenata).
CI: `tests/test_n1_zlatni_prijem.py` dodat u oba OCR koraka `production-runtime.yml` (stvaran Tesseract; produkciona slika sa srpskim paketima).

---

## Dokazi

### Zlatni E2E (browser) — `node tests/live-zlatni-prijem-e2e.mjs` → **48/48 PASS** (lokalno, bez Tesseract-a; pre ispravki 29/38)
Stvarno: V2 /app u Chromium-u, `api.app` rute, provere vlasništva, intake worker, ekstraktor (pypdf/python-docx), dedupe, finalize.
**Simulirano:** predlog iz opisa (model), klasifikacija kad heuristika ne odluči, stranke iz slobodnog teksta, embedding/Pinecone,
prijava (token). **OCR nije simuliran** — lokalno nedostaje, pa test meri vidljiv neuspeh; stvaran OCR meri backend zlatni test u CI-ju.

| Tvrdnja | Ishod |
|---|---|
| 1 predmet, vlasnik A, opis + cilj sačuvani | PASS |
| 1 klijent, 1 veza klijent–predmet | PASS |
| rok iz predloga nije upisan bez potvrde | PASS |
| 4 dokumenta u jednom otpremanju; čitljiva (PDF, DOCX) prikačena ISTOM predmetu; bez OCR-a sken i fotografija vidljivo odbijeni, bez izmišljenog teksta, bez lažnog „ponovite“, bez „pročitan OCR-om“ | PASS |
| ispravka vezana za tačan dokument, original sačuvan | PASS |
| reload: naziv, klijent, dokumenti, opis | PASS |
| ponovljen sadržaj: isti posao, sa ispravkom, bez novog dokumenta | PASS |
| `.doc` odbijen pre slanja; lažan DOCX odbijen po sadržaju | PASS |
| dupli klik na prikačivanje → 1 dokument | PASS |
| nepoznat ishod (opis): 1 predmet, advokat prebačen na njega | PASS (pre: FAIL, 2 predmeta) |
| nepoznat ishod (dokument): 1 predmet, prepoznat kao OVAJ; drugi dokument u ISTI predmet | PASS (pre: FAIL) |
| nepoznat ishod (dokument), zahtev nije stigao: drugi dokument NE otvara predmet i kaže zašto; isti dokument ponovi → 1 predmet; drugi dokument zatim u isti | PASS |
| nepoznat ishod (opis), zahtev nije stigao: „NIJE otvoren (provereno)“ → ponovni pokušaj → 1 predmet | PASS |
| nepoznat ishod (opis), lista nečitljiva: otvaranje pod tim nazivom zaključano i posle izmene pa vraćanja naziva | PASS |
| dokument već prikačen drugom predmetu se ne kopira | PASS |
| sukob interesa: zaustavljeno, bez kategorične tvrdnje | PASS |
| B: predmet/dokument/posao/ispravka/prikačivanje/klijent A → 404; B ništa nije promenio; B u pregledaču ne vidi predmet A | PASS |
| promena korisnika tokom obrade: poslovi A nestaju, ništa prikačeno bez odluke | PASS |
| 0 spoljnih veza, 0 JS grešaka, 0 odgovora 5xx | PASS |

### Zlatni backend — `python -m pytest tests/test_n1_zlatni_prijem.py` → **6/6 PASS** lokalno (grana bez OCR-a)
U CI-ju (Tesseract, `VINDEX_REQUIRE_OCR=1`) isti test traži 4/4 prikačena, `ocr_used=True` za sken i fotografiju i ≥ 3
očekivane reči u tekstu svakog.

**Stvaran OCR — CI `c997a8f4` (prvi pokušaj):**
- posao „Import app + full suite on production Python (3.11)“ (Tesseract bez srpskog paketa): korak OCR proof PASS, uključujući N1 zlatni test (4/4).
- produkciona Docker slika (srp + srp_latn): **4/4 dokumenta prikačena** (`len(dok) == 4` prošao), ali je moja provera
  „OTKAZU u tekstu“ pala jer je stvaran OCR pročitao `RESENJE О ОТКАДЈ UGOVORA О RADU … MILICA ДАПС IZ BEOGRADA` — **ćirilična slova
  u latiničnom tekstu**. Provera je ispravljena da traži pročitane reči umesto tačnosti koju OCR nema. Nalaz kvaliteta OCR-a (izbor
  jezičkog modela za latinične skenove) je van N1 i prijavljen je kao rizik.

### Mutacije (svaka ispravka vraćena na staro, binarno; `scratchpad/n1_mutacije.py`) — **9/9 ubijeno**
D3 (pytest 2 pada) · D5 (pytest 3) · D1 usvajanje (E2E 2) · D1 vlasnik otvaranja (E2E 2) · D2 ponovno čitanje (E2E 4) ·
D2 zaključavanje (E2E 1) · D4 (E2E 1) · D3 u browseru (E2E 3) · D5 u browseru (E2E 1).
Napomena: kod D3 u browseru lažno `ocr_used=True` menja i detekciju „OCR dostupan“ u testu — pada drugim proverama, ali pada.

### Nezavisni adversarial pregled (zaseban agent, samo čitanje + ciljani testovi)
Bez regresije izolacije i autorizacije; D2, D3, D5 potvrđeni. Nalazi i ishod:

| Nalaz | Ishod |
|---|---|
| D1: blokada se skidala kad ponovno čitanje pokaže posao bez predmeta, a zahtev je mogao još biti u redu → drugi dokument otvara drugi predmet (materijalno, usko) | ISPRAVLJENO: vlasnik otvaranja; blokada se ne skida; test E4d + mutacija |
| D1: drugi dokumenti su ćutke ignorisali klik dok je ishod nepoznat | ISPRAVLJENO: poruka „predmet se upravo otvara iz drugog dokumenta“ |
| D1: poruka „ponovite prikačivanje“ dok je prikačivanje u toku, ostajala i posle uspeha | ISPRAVLJENO: poruka po stanju (U_TOKU/NEPOTPUNO/PRIKACENO), osvežava se |
| D4: segmentiran dokument sa delom bez teksta → „ponovite za ostatak“ | ISPRAVLJENO |
| D4: posle reload-a razlog nije poznat | OSTAJE (bez serverske izmene): opšta poruka, jedan pokušaj vraća tačan razlog |
| D2: zaključavanje se skidalo bilo kojom izmenom naziva | ISPRAVLJENO: zaključan TAJ naziv; test E3c + mutacija |
| D2: upis u toku u trenutku ponovnog čitanja | UBLAŽENO: 2,5 s čekanja; serverski prozor od 5 s ostaje druga zaštita |
| D2: istoimeni predmet iz drugog prozora između dva čitanja se usvaja | OSTAJE (prihvatljivo: isti korisnik, isti naziv) |
| D5: lozinkom zaštićen DOCX dobija poruku „drugi format“ | ISPRAVLJENO: poruka pominje lozinku |
| D5: druge rute otpremanja (`api.py`, `routers/dokument.py`) nemaju proveru potpisa | OSTAJE (postojeće, van V2 prijema) |
| testovi nisu pokrivali granu „ništa nije kreirano“, zaključavanje, drugi dokument dok je ishod nepoznat | DODATO: E3b, E3c, E4d |
| dnevnik je tvrdio više od koda za D4 i D1 | ISPRAVLJENO u ovom dokumentu |

### Regresija (lokalno, Windows)
| Komanda | Ukupno | Pass | Fail | Skip |
|---|---|---|---|---|
| pytest 152 fajla (intake/OCR/COI/klijenti/prijem/izolacija/upload, uklj. N1) | 1736 | 1614 | 3 (`[trio]`: `trio` nije instaliran; `[asyncio]` varijante prolaze) | 119 |
| `live-prijem-carobnjak-e2e` | 37 | 37 | 0 | — |
| `live-prijem-oporavak-e2e` | 18 | 18 | 0 | — |
| `live-solo-tok-e2e` | 23 | 23 | 0 | — |
| `live-prijem` | 53 | 53 | 0 | — |
| `live-prijem-pracenje` | 29 | 29 | 0 | — |
| `live-nov-predmet` | 41 | 41 | 0 | — |
| `live-klijenti` | 40 | 40 | 0 | — |
| `live-isolation` | 25 | 25 | 0 | — |
| `live-session` | 38 | 38 | 0 | — |
| `live-primary-e2e` | 51 | 51 | 0 | — |
| `live-api` | 49 | 49 | 0 | — |
| `live-send` | 100 | 100 | 0 | — |
| `live-vrsta-dokumenta-e2e` | 15 | 15 | 0 | — |
| `live-organizacija-e2e` | 16 | 16 | 0 | — |
| `live-states` | 99 | 99 | 0 | — |
| `live-runtime` | 92 | 92 | 0 | — |
| `verify` (uz `serve.mjs`) | 98 | 98 | 0 | — |
| `brand-identity` | 335 | 335 | 0 | — |
| `live-pre136-e2e` | OK | — | 0 | — |
| `live-mir001-spis-e2e` | — | — | 1 | NOT_VERIFIED: traži Tesseract (okruženje) |

CI ne pokreće V2 browser testove za PR ka `main` — rezultati iznad su lokalni.

---

## Preostali rizici / odluke osnivača
1. Serverska obaveznost provere sukoba (sada UI kapija na svim V2 putevima; API je ne traži nigde).
2. Nepročitan sken: danas se ne prikačuje predmetu (`prazan_tekst`); alternativa je prikačiti ga bez teksta uz oznaku.
3. „Iz dokumenta“ za nepročitan dokument otvara predmet pa ne prikači dokument → predmet bez dokumenata (postojeće ponašanje
   servera; UI to sada tačno kaže).
4. „Ručno“ (`POST /api/predmeti`) ima istu klasu kao D2 (nepoznat ishod → poruka, bez ponovnog čitanja); van N1 (nije na listi tokova).
5. Doslovni Bojanov tekst — `REQUIREMENT_SOURCE_MISSING`; izvor „četiri izričite stavke“ (A018) — UNKNOWN.
6. **Kvalitet OCR-a u produkcionoj slici:** latinični sken je pročitan sa ćiriličnim slovima umešanim u reči (CI `c997a8f4`). Tekst
   stiže do predmeta, ali pretraga i ekstrakcija nad njim mogu promašiti. Izbor jezika OCR-a za latinične dokumente — zaseban zadatak.
7. Ostanak u istoj sesiji „Iz dokumenta“ posle otvaranja predmeta prikačuje nove dokumente TOM predmetu (dizajn, UI to prikazuje);
   za nov predmet advokat napušta stranicu. Da li to odgovara očekivanju advokata: UNKNOWN (pitanje za Bojana).

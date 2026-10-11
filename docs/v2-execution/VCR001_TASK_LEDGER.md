# VCR001 — knjiga zadataka

Program na grani `program/vcr001` (worktree `C:/vindex-vcr001`), počev od `main` = produkcija `6ad0b13a`. Nivoi dokaza:

| Oznaka | Nivo |
|---|---|
| LU | lokalno, unit |
| LI | lokalno, integraciono (stvarne rute, fake baza) |
| BM | pregledač + mock provajder |
| BR | pregledač + pravi backend (fake baza) |
| CI | GitHub Actions / Docker slika |
| LIVE | produkcija |

---

## T00 — osnovica sposobnosti i prava pristupa — `PASS_IMPLEMENTED` (analiza)
- **Izvor zahteva:** direktiva VCR001 T00; `docs/product/BOJAN_WORKFLOW_GAP_ANALYSIS_2026-08-02.md`; A018 (kopija u `docs/product/A018_BOJAN_REQUIREMENTS_REALITY_MATRIX.md`).
- **Početni SHA:** `6ad0b13a`.
- **Fajlovi:**
  - `docs/v2-execution/VINDEX_V2_FOUNDER_EXECUTION_DIRECTION.md`;
  - `VCR001_CAPABILITY_PARITY_MATRIX.md`, `VCR001_REQUIREMENTS_MATRIX.csv`, `VCR001_CHECKPOINT.json`, ovaj fajl;
  - kopija A018.
- **Nalazi (P, statički inventar i kod):**
  1. Osnivač prolazi tarifne provere (`shared/permissions.py`), pa „vidi malo funkcija“ znači **da V2 nema ulaz**, ne da mu je pristup ograničen.
  2. V2 poziva 37 ruta iz 15 modula; stari UI 226.
  3. Bez V2 ulaza su: prijem „problem prvo“, nov predmet iz dokumenta, multi-agent, šabloni, strategija, prediktor, zastarelost, zadaci, ručni unos dokaza i podsetnici.
  4. Istorijski kvar `predmet_klijenti.user_id` u `routers/intake.py` **više ne postoji** (umetanja ne šalju `user_id`).
  5. Miroslavljev izvor zahteva nije pronađen: `REQUIREMENT_SOURCE_UNAVAILABLE`.
- **Van obima:** redizajn navigacije; nadogradnja naloga.
- **Testovi:** nema (analiza).
- **Produkcija:** prijavljeni tok **nije proveren** (nema test naloga).
- **Završni SHA:** v. commit „docs(vcr001): T00 …“.

---

## T01 — OCR: kompletno čitanje dokumenata — `PASS_IMPLEMENTED`
- **Izvor:** VCR001 T01; A018 B3 („OCR nikad nije izvršen u produkciji“).
- **Početni SHA:** `79d2c1b5` · **commit:** `a8a7e16b`.
- **Kvar (P, reprodukovan):** mešovit PDF (digitalna strana + skenirana strana bez tekstualnog sloja). Prosek znakova po strani je prelazio prag, OCR se nije pokretao i tekst skenirane strane se **tiho gubio**.
- **Ispravka:** `uploaded_doc/extractor.py::_ocr_strane_pdf`. OCR se pokreće samo za strane sa manje od 30 znakova; potpuno digitalan PDF ne poziva OCR; neuspeh ostavlja stranu praznom.
- **Testovi:**
  - `tests/test_vcr001_t01_mesoviti_pdf.py` (4, LU sa zamenjenim OCR-om; **negativna kontrola:** 1 pada na starom kodu);
  - `tests/test_ns005_b_ocr.py::test_F_mesoviti_pdf_skenirana_strana_kroz_pravi_ocr` (pravi Tesseract, ćirilica, **CI u produkcionoj slici: 21 passed** naspram ranijih 20, run 38177931357);
  - `tests/test_vcr001_t01_prijem_adversarial.py` (2, LI: opasno ime fajla ne ulazi u putanju skladišta; PNG pod imenom `.pdf` nikad nije lažno završen).
- **Već pokriveno postojećim testovima:**
  - `.doc` se odbija pri otpremanju (`test_smart_intake_upload_validation`);
  - JPG/PNG (`test_extractor_image`, `test_smart_intake_upload_validation`);
  - prevelik i prazan fajl; oštećen PDF; tuđ posao i pogrešan predmet (OSB002); ponavljanje, istovremenost i oporavak (OSB003/FRG001);
  - ćirilični sken kroz worker do teksta predmeta (u slici).
- **Regresija:** lokalno 252 passed; CI produkcioni Python 197 = 197 nasleđenih, 0 novih.
- **Produkcija:** OCR uživo **U** (nema test naloga).
- **Ograničenja:** OCR je i dalje sinhron u worker-u (300 dpi po strani bez teksta); `.doc` se ne podržava (jasna greška).

## T02 — V2 čarobnjak za prijem — `PASS_IMPLEMENTED`
- **Izvor:** VCR001 T02; Bojan tok (novi klijent → predmet → upload); matrica T00 (UI nedostaje).
- **Početni SHA:** `a8a7e16b` · **commit:** v. „feat(v2): čarobnjak za prijem …“.
- **Implementacija (samo postojeći backend):**
  - **Problem prvo:** `POST /api/intake/ekstrakcija` (predlog, ne upisuje) → ispravka → klijent (postojeći ili nov, `POST /klijenti`) → provera sukoba (`/api/conflict-check`, isto pravilo kao kartica Klijenti) → `POST /api/intake/kreiraj`. Rok iz opisa se upisuje samo uz izričitu potvrdu.
  - **Dokument prvo:** `src/prijem-predmeta.js` u režimu bez predmeta (prefiks `nd`). Prvi finalize otvara predmet (`klijent_strana` po izboru), ostali dokumenti se prikače istom predmetu.
- **Fajlovi:**
  - `frontend-v2-ng/index.html`, `src/nov-predmet-prijem.js` (nov), `src/prijem-predmeta.js`, `src/app.js`, `src/app.css`, `package.json`;
  - `tests/live-prijem-carobnjak-e2e.mjs` (nov), `tests/osb003_solo_server.py` (zamena za ekstrakciju), `tests/test_vcr001_t02_carobnjak_api.py` (nov).
- **E2E (BR, pravi `api.app` + fake baza, Chromium): 37/37.**
  - Oba toka, ispravka predloga, rok ne bez potvrde, drugi dokument u isti predmet, tvrdnje posle prijema.
  - Provera sukoba („mogući … potrebna provera“, otvaranje zaustavljeno, bez kategorične tvrdnje).
  - Reload, samo vlasnik, 0 spoljnih veza, bez JS grešaka i bez 5xx.
  - Simulirani su samo modeli (ekstrakcija, klasifikacija), embedding i prijava.
- **Negativne kontrole (mutacije):** 3/3 uhvaćene (rok bez potvrde, bez provere sukoba, drugi dokument otvara nov predmet).
- **Backend (LI): 6/6:**
  - predlog ne upisuje i naplaćuje `intake_ai` po postojećem ugovoru;
  - rok samo uz potvrdu, sa izvorom AI;
  - tuđ klijent daje 404 bez predmeta; neprijavljen 401; dupli klik 409;
  - dokument prvo: tuđ korisnik 404, a `coi_status` nikad nije „čisto“.
- **Regresija frontenda:** svih 31 `verify*` i `e2e:solo-tok`, `e2e:pre136`: 33/33.
  - Usput uhvaćen i ispravljen moj sudar ID-jeva (`np-*` pripada Naplati), kao i broj `.tabs__item` u testu kartica.
- **Van obima:** zahtev za proveru protivne strane u V2 (V2 proverava klijenta, isto kao kartica Klijenti); šabloni predmeta (T07).
- **Produkcija:** nije deployovano (traži odluku o izdanju).

## T03 — inteligencija dokumenata i organizacija predmeta — `PASS_IMPLEMENTED`
- **Izvor:** VCR001 T03; A018 B8 (hronologija bez izvora), B9 (rokovi), B11/S5 (obaveza iz nalaza sa poreklom).
- **Početni SHA:** `b6c5991d`.
- **Zatečeno (P, kod):**
  - rokovi iz Genome-a se već upisuju sa `dokument_id` (migracija 126), izvorom `AI_AUTONOMOUS` (127) i `vrsta=rok` (129);
  - stanje odluke je u lancu odluka (FAZA 6.5), a V2 Danas ga potvrđuje ili odbija.

  Ovo nije ponovo rađeno.
- **Jaz 1 (B8):** V2 hronologija (`genome-v2` ← `datumi_kljucni`) nije imala izvor. Ispravka:
  - Genome šema `datumi_kljucni[].lokacija` („DOK-NN“);
  - `shared/genome_contract._hronologija` razrešava izvor istim zatvorenim razrešavačem (nepoznato → `None`);
  - V2 Analiza prikazuje dugme izvora.
- **Jaz 2 (B11):** rok iz dokumenta koji čeka odluku nije davao obavezu. Ispravka:
  - Rule 6 u `services/case_evolution._compute_target_actions`, postojeći tip `PLANIRATI_ROKOVE` (CHECK 099, bez migracije);
  - poreklo: `hronologija_id`, `dokument_id`, datum; samo za AI rokove bez odluke;
  - nepročitana hronologija ili lanac odluka (`odluke(strogo=True)`, nov opcioni parametar) → izuzetak, akcije se ne menjaju;
  - bez migracije 129 pravilo se preskače.
- **Jaz 3:** odluka o roku nije osvežavala akcije. Ispravka:
  - `routers/rok_odluka` posle potvrde ili odbijanja emituje trajni `MANUAL_CORRECTION_APPLIED`;
  - registrovan u `CONSEQUENCE_REGISTRY` (refresh_case_actions + projekcija obaveštenja) i pretplaćen u `event_bus`.
- **Rok NE postaje obavezujuć bez potvrde:** akcija je pregled, a podsetnik i dalje traži potvrdu (postojeći ugovor).
- **Testovi:**
  - `tests/test_vcr001_t03_organizacija.py` (9, LI): izvor u hronologiji (razrešen, nepoznat, nepročitani dokumenti, stari Genome); akcija sa poreklom; potvrda i odbijanje je zatvaraju; ručni rok ne daje akciju; nepročitana hronologija; nečitljiv lanac ne otvara ponovo potvrđen rok; bez 129.
  - **Mutacije:** 5/5 uhvaćene.
- **E2E (BR):** `frontend-v2-ng/tests/live-organizacija-e2e.mjs` **16/16**.
  - Dokument → Genome → izvor datuma u Analizi; akcija „Planirati rokove … čeka vašu potvrdu“ u živom pregledu.
  - Potvrda na ekranu Danas zatvara akciju (i u bazi); reload; samo vlasnik; 0 spoljnih veza; bez 5xx.
  - Simulirani su Genome model, embedding i prijava.
- **E2E server (`tests/osb003_solo_server.py`):** opciona varijanta `VX_GENOME_IZVORI=1`; upis u lanac odluka (harness je gasio `log_action`, pa je potvrda roka vraćala 503).
- **Regresija:**
  - Python 399 passed (27 fajlova);
  - frontend `live-analiza` 43, `live-danas` 50, `live-pregled-zivi` 30, `live-radna-lista` 25;
  - E2E `solo-tok` 23, `prijem-carobnjak` 37, `primary` 51, `fastapi` 62, `pre136` OK.
- **Ograničenja:**
  - izvor se pojavljuje tek posle sledećeg osvežavanja Genome-a (stari blobovi nemaju `lokacija`);
  - živi pregled se ne osvežava sam posle obrade u pozadini (ponovno otvaranje predmeta).

## R1 — kapija prijema (T00–T03) — `PASS`
- **Kandidat:** `b817fd2d`; paket dokaza u `docs/v2-execution/VCR001_R1_GATE.md`.
- **CI:**
  - Test Suite 3.11/3.13: 175/175 = `main` (0 novih);
  - Runtime: Docker build/boot zeleno, pun paket 197 nasleđenih;
  - V2 NG zeleno; Security zeleno.
- **Ispravke tokom kapije:**
  - curenje sonde 129 između testova (20 CI padova, T03);
  - pojačana ns006 demo provera;
  - zastarela dokumentacija registra.
- **Merge/deploy:** NIJE izvršen — čeka odluku osnivača za R1 kandidat.

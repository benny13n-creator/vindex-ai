# NS006 — LIVING MATTER / PROFESSIONAL CASE GENOME — DOKAZI

Grana `feature/vindex-v2-ns006-living-matter` (worktree `C:\vindex-ns006`), osnova
`origin/main` = `99d2c6b9724ed72299efdd97cbb987a88fab6a97` (provereno pre grananja).
PAD-001 zaključan u `2fbb9459` (`docs/v2/VINDEX_V2_PRODUCT_ARCHITECTURE_DECISION_PAD_001.md`).

Oznake tvrdnji: PROVEN (izmereno/izvršeno), INFERRED (izvedeno iz koda, nije izvršeno),
ASSUMED, UNKNOWN.

---

## TASK 0 — MAPA ARHITEKTURE (bez izmene koda)

### A. Izvor istine (PROVEN čitanjem koda na `99d2c6b9`)

| Pojam | Izvor istine | Napomena |
|---|---|---|
| Trenutni Genome | `predmeti.case_dna` (JSON, ceo se zamenjuje pri refresh-u) | `verzija` raste za 1 po uspešnom refresh-u |
| Prethodne verzije Genome-a | `predmet_genome_history.genome_data` (PUN snimak stare verzije, upisuje se PRE zamene) | `trigger_event`, `snaga_procent`, `created_at`; GET `/case-dna/history` vraća samo metapodatke (max 20) |
| Tvrdnje / dokazi | `predmet_dokazi` (soft delete `deleted_at`) | `identitet` (116), grounding `stranica/paragraf/start_offset/end_offset` (080), `nacin_pronalaska` (117), `izvor_snage` (118) |
| Dokumenti | `predmet_dokumenti` | `redni_broj` UNIQUE po predmetu (106) → oznaka `DOK-NN` |
| V2 kontradikcije | `predmet_issues` + `predmet_contradictions` + `predmet_contradiction_claims` (119–125) | stanja `OPEN/RESOLVED/NOT_OBSERVED/SUPERSEDED/REVIEW_REQUIRED`; `observation_version` na `predmeti` |
| Legacy kontradikcije | `case_dna.kontradikcije[]` | identitet `shared/contradiction_identity.py` (lokacija_1/2) |
| Šta treba uraditi | `case_actions` (099), parcijalni UNIQUE `(predmet_id, dedupe_key) WHERE status='open'` | jedini pisac: `services/case_evolution.py::_consequence_refresh_case_actions` |
| Događaji | `events` outbox (073, 091, 115, 130) | `dispatch_pending_events`, max 5 pokušaja, DEAD_LETTER |
| Posledice | `case_evolution_consequences` (po `(event_id, ime)`) | atomski claim, stale 300 s |
| Procesni rizik | `services/risk_engine.py::calculate_procesni_rizik` (čista funkcija) | ulaz: dokazi, dokumenti, ročišta |
| Spremnost | `shared/case_readiness.py::compute_case_readiness` (čista funkcija nad `case_actions`) | 5 stanja, bez GPT-a |

### B. Vlasnici upisa (PROVEN)

| Tabela/kolona | Pisac |
|---|---|
| `predmeti.case_dna` | `routers/case_dna.py::_do_genome_refresh` (pozadina, Case Evolution) i `_refresh_case_dna_body` (ručni POST `/case-dna/refresh`) — oba posle `services/v2_observation.py::upisi_v2_opazanje` |
| `predmet_genome_history` | `routers/case_dna.py::_save_genome_history` |
| `predmet_dokazi` | `shared/evidence_write.py::upisi_dokaze` (jedini); pozivaoci: `routers/evidence.py::add_dokaz` (čovek) i `klasifikuj_i_sacuvaj` (GPT klasifikacija, iz posledice `evidence_classification`) |
| V2 kontradikcije | RPC `persist_observation_package` / `v2_persist_contradiction` (jedini pisac), preko `services/v2_contradiction_persistence.py` |
| `case_actions` | `services/case_evolution.py::_consequence_refresh_case_actions` (i direktan poziv iz `routers/predmeti_close.py` sa istim reconcile-om) |
| `predmet_health_log` | `routers/matter_intel.py::_log_and_fetch_health` — **pri GET-u** |

### C. Proizvođači događaja (PROVEN, `grep` + čitanje)

| Događaj | Proizvođač | Posledice (CONSEQUENCE_REGISTRY) |
|---|---|---|
| `predmet_kreiran` | `api.py` POST predmet (direktan insert, retry), Smart Intake, reaper | on_predmet_kreiran (Case Pipeline) — nije u Case Evolution registru |
| `DocumentAccepted` | `api.py` upload auto-analyze (6233), Smart Intake finalize (1817) | genome_refresh, timeline_entry, refresh_case_actions, project_notifications |
| `DocumentBatchCompleted` | Smart Intake batch finalize | genome_refresh, timeline_entry, case_intelligence_summary, refresh_case_actions, project_notifications |
| `ReviewAccepted` / `ReviewRejected` | Smart Intake review resolve/reject | genome_refresh…/audit |
| `NewEvidenceRegistered` | `routers/evidence.py::add_dokaz` (408), `api.py` (6221), Smart Intake (1748) | evidence_classification, refresh_case_actions (**bez genome_refresh**) |
| `NewClientLinked` | samo Smart Intake (1291) | conflict_check |
| `rociste_zakazano` | `routers/rocista.py` POST (216) i PATCH (328) | genome_refresh, refresh_case_actions, project_notifications |
| `SourceInvalidated` | RPC-ovi 130/131 (brisanje dokaza/dokumenta/ročišta, atomski) | refresh_case_actions |
| `MatterBecameTerminal` | `routers/predmeti_close.py` (direktan reconcile, bez outbox reda) | refresh_case_actions |
| `GenomeUpdated` | `routers/case_dna.py::_emit_genome_event` | on_genome_updated (alarm) — nije u Case Evolution registru |
| `health_score_promenjen` / `rok_kritican` | `routers/matter_intel.py` **pri GET-u** (in-process `emit`, uz dedup po nepročitanom alarmu) | proaktivni alarmi |

### D. Šta V2 (`frontend-v2-ng/src`) danas poziva (PROVEN)

Predmeti (lista, detalj, izmena, beleške, nov predmet), klijenti + `confirm-links` + conflict-check, ročišta,
pretraga, pravno pitanje, znanje/interni stavovi, nacrt podneska, naplata, kancelarija, Danas
(`/api/kalendar/pregled`, `/api/rokovi/kandidati`, potvrdi/odbij), Smart Intake.
**V2 NE čita:** `case-dna`, `case-dna/history`, `evidence`, `case-actions`, `workspace`, `matter-intel`.

### E. Okidači Genome refresh-a (PROVEN)

Automatski (Case Evolution `genome_refresh`): `DocumentAccepted`, `DocumentBatchCompleted`,
`ReviewAccepted`, `rociste_zakazano`. Ručno: POST `/api/predmeti/{id}/case-dna/refresh`.
**Ne osvežava Genome:** `NewEvidenceRegistered` (ručni dokaz), potvrda/odbijanje roka, izmena
predmeta, povezivanje klijenta, brisanje izvora.

### F. Okidači `case_actions` reconcile-a (PROVEN)

`DocumentAccepted`, `DocumentBatchCompleted`, `ReviewAccepted`, `NewEvidenceRegistered`,
`rociste_zakazano`, `SourceInvalidated`, `MatterBecameTerminal`, zatvaranje predmeta (direktno).

### G. Dupli mehanizmi (PROVEN)

1. Dva verifikatora tokena: `api.py::_verify_token` i `shared/deps.py::verify_token_local/_verify_token`.
2. Dva proizvođača Genome opažanja (pozadina i ručni refresh) — A017 ih je već sveo na jedan
   V2 ulaz (`upisi_v2_opazanje`).
3. Dve projekcije kontradikcija u `case_actions` (V2 ima prednost, legacy samo kad V2 prazan) — A015, namerno „ili-ili".
4. Filter terminalnih predmeta: `routers/workspace.py` ima doslovnu listu
   `["zatvoren","arhiviran","odbijen"]`, ostali koriste `shared/constants.py::TERMINALNI_STATUSI_PREDMETA`
   (iste vrednosti danas — rizik od razilaženja, ne kvar).

### H. Poznate rupe (PROVEN osim gde piše drugačije)

1. **Istorijski trag „ručni dokaz ne emituje događaj" — OPOVRGNUT.** `routers/evidence.py::add_dokaz`
   emituje `NewEvidenceRegistered` (Case Evolution Spine, 2026-09-11). Preostalo: upis i emitovanje
   nisu atomični (pad procesa između njih gubi događaj; emit je non-fatal), i taj događaj ne
   osvežava Genome.
2. `_compute_target_actions` čita dokaze/dokumente/ročišta sa `return_exceptions=True` i **pad čitanja
   tretira kao praznu listu**. Posledica (INFERRED iz koda, test u Task 8/16): pad čitanja ročišta
   zatvara otvorenu akciju za ročište; pad čitanja dokaza otvara lažnu kritičnu akciju „nema dokaza".
3. `GET /api/matter-intel/predmeti/{id}` piše `predmet_health_log`, emituje alarme i pad izvora
   tretira kao prazno → V2 ga ne sme koristiti za čitanje.
4. `predmet_dokazi` **nema kolonu porekla tvrdnje** (čovek vs AI klasifikacija). `izvor_snage` beleži ko je
   odlučio o snazi, ne ko je napisao tvrdnju; ručni unos bez snage i AI unos koji DC-005 nije našao
   daju isto (`podrazumevano`). Poreklo starih redova je UNKNOWN.
5. V2 `confirm-links` (povezivanje klijenta) ne emituje `NewClientLinked` (samo Smart Intake emituje).
6. Potvrda/odbijanje roka (`routers/rok_odluka.py`) ne emituje događaj, a `_compute_target_actions`
   uopšte ne čita potvrđene rokove (`predmet_hronologija`) — samo ročišta.
7. `PATCH /api/predmeti/{id}` dozvoljava `status` (i terminalni) bez `MatterBecameTerminal`; V2 ne šalje
   `status` (proveren ugovor u `rad-predmeta.js`), legacy može.
8. `ROCISTE_ZAKAZANO`/`DOCUMENT_ACCEPTED` refresh Genome-a u pozadini troši AI kredit po postojećem ugovoru.

### Osnova testova

- Pun pytest na `99d2c6b9` (lokalno, `-p no:randomly`, bez Postgres-a): pokrenut u pozadini; rezultat se
  upisuje u Task 21.
- `pip-audit` (isto kao CI, `--ignore-vuln PYSEC-2026-1325`): 12 nalaza — `python-jose` 3.5.0
  (CVE-2026-85394, bez ispravke) i `pypdf` 6.15.0 (11 PYSEC, ispravke 6.16.0–6.19.0).

---

## TASK 1 — SIGURNOST GRANICE UNOSA DOKUMENATA

**PROBLEM.** `pypdf` 6.15.0 ima 11 poznatih ranjivosti (DoS: vreme/memorija). `python-jose` 3.5.0 ima
CVE-2026-85394 (javni ključ prihvaćen kao HMAC tajna).

**TRENUTNI DOKAZ.**
- `uploaded_doc/extractor.py::extract_pdf` poziva `pypdf.PdfReader(...).extract_text()` nad SVAKIM PDF-om
  koji korisnik otpremi (Smart Intake radnik, upload) — PROVEN čitanjem; ranjivosti PYSEC-2026-3911
  (XForm), 4153 (zaglavlja objekata), 4154 (ToUnicode), 4155 (Widths), 4156 (FlateDecode) su na tom putu.
  Ostala mesta: `klijenti/router.py::_add_pdf_watermark` (merge stranica korisničkog PDF-a),
  `routers/auto_discovery.py` i `routers/law_upload.py` (admin).
- JWT: oba verifikatora dozvoljavaju HS256 samo sa `SUPABASE_JWT_SECRET`, a asimetrične ključeve samo sa
  `algorithms=[RS256|ES256]`.

**POKUŠAJ OPOVRGAVANJA.** Falsifikovani tokeni (HS256 potpisan javnim ključem u PEM/DER/JWK/x‖y obliku;
zaglavlje ES256 i RS256 sa HMAC potpisom; `alg=none`) protiv `api.py::_verify_token`,
`shared/deps.py::verify_token_local` i `shared/deps.py::_verify_token`, sa SDK putem koji pada.
Kontrola osetljivosti: ranjiva konfiguracija (DER javni ključ + `algorithms=["HS256"]`) na instaliranoj
python-jose 3.5.0 **prihvata** falsifikat — napad je stvaran (PROVEN), Vindex ga odbija u sva tri
verifikatora (PROVEN, 13/13 falsifikata).

**ODLUKA.**
- `pypdf` 6.15.0 → **6.19.0** (najmanja verzija koja zatvara svih 11 nalaza; jedina izmena zavisnosti).
- `python-jose`: nema ispravljene verzije; kroz stvarni Vindex verifikator NIJE iskoristiv (PROVEN). Skener
  se ne utišava globalno; nalaz ostaje vidljiv u `pip-audit`.

**IMPLEMENTACIJA.** `requirements.txt`: `pypdf==6.19.0`. Kod nepromenjen.

**FAJLOVI.** `requirements.txt`, `tests/test_ns006_t1_ingestion_boundary.py`,
`tests/test_ns006_t1_jwt_alg_confusion.py`.

**TESTOVI** (Python 3.11.9, sav `requirements.txt` sa `pypdf` 6.19.0, `pip check` čist; stvarni Tesseract
5.5.3 sa srp/srp_latn):
- `test_ns006_t1_*`: 23/23 (pin ≥ 6.19.0; instalirano == pin; digitalni PDF; samo vlasnička lozinka;
  šifrovan / smeće / odsečen PDF → izuzetak bez teksta; Smart Intake radnik beleži `failed`, nikad
  `completed`; 13 falsifikata odbijeno; pozitivna kontrola; kontrola osetljivosti).
- OCR + Smart Intake regresija (`test_ns005_b_ocr`, `test_ns005_t14_smart_intake`, `test_b3_ocr…`,
  `test_extractor_ocr`, `test_extractor_pdf_empty`, `test_intake_worker_guess_suffix`,
  `test_intake_original_file_storage`): 45 passed, 2 skipped, **1 failed** — vidi ispod.
- Ponašanje extractora je **identično** na 6.15.0 i 6.19.0 za digitalni, šifrovan, samo-vlasnički, smeće i
  odsečen PDF (PROVEN, ista proba nad obe verzije).

**`test_b3_ocr_bez_laznog_uspeha::test_o2` — POSTOJEĆI PAD, NIJE NS006.** Pada identično sa 6.15.0 i 6.19.0.
Uzrok (PROVEN): test crta 20 znakova Pillow-ovim podrazumevanim fontom; Tesseract to čita kao
`'BOTA TA ANA'` (11 znakova), a `extract_pdf` traži > 100 znakova OCR teksta (prag zaključan u NS005) i
pošteno vraća „OCR nije uspeo". Ovo je i pad iz NS005 CI posla prod-py311 koji tada nije imao poruku.
Nije menjan (ispravka testa nije u opsegu NS006).

**TENANT.** Nije primenljivo (biblioteka + verifikator).

**FAILURE.** Nečitljiv PDF → izuzetak → posao `failed` (bez izmišljenog teksta).

**MUTACIJE (2/2 ubijene).** J1: `shared/deps.py` ES/RS grana prima HS256 sa DER javnim ključem →
`test_falsifikat…[es256-zaglavlje/der]` pada. J2: `api.py` prihvata `alg=none` → `test_falsifikat…[none]` pada.

**OGRANIČENJA.**
- Produkciona Docker slika lokalno nije dostupna (nema Dockera); paritet dokazuje CI posao „Production
  Runtime" (build + OCR + Smart Intake u slici) — UNKNOWN do CI-ja.
- Šifrovan PDF se ponavlja do `max_attempts` (5) pre konačnog `failed` — postojeće ponašanje, dug.
- Eksploit PDF-ovi za svaki PYSEC nisu konstruisani; zaštita je verzija biblioteke + čuvar pina.

**SLEDEĆA KAPIJA.** Task 2 — pokrivenost Case Evolution događaja.

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

---

## TASK 2 — POTPUNOST CASE EVOLUTION DOGAĐAJA

**PROBLEM.** Da li svaka promena predmeta dostupna iz V2 proizvodi trajan događaj i odgovarajuću posledicu.

**MATRICA POKRIVENOSTI** (putanje dostupne iz V2; „test" = postojeći test koji to izvršava):

| Putanja (V2) | Trajni događaj | Case Evolution | Genome refresh | Dokazi | Case Actions | Dokaz |
|---|---|---|---|---|---|---|
| Nov predmet (`POST /api/predmeti`) | `predmet_kreiran` (retry + reaper) | ne (Case Pipeline) | ne (nema dokumenata) | — | ne | PROVEN: test_case_pipeline, test_blk21 |
| Izmena predmeta (`PATCH`, bez `status`) | **ne** | — | — | — | **ne** | PROVEN (čitanje): naziv/opis ne menjaju stanje; `tip` menja očekivane tipove dokumenata → dug |
| Beleška | ne (nije semantička promena stanja) | — | — | — | — | PROVEN (čitanje) |
| Prihvaćen dokument / Smart Intake finalize | `DocumentAccepted` / `DocumentBatchCompleted` | da | **da** | klasifikacija | da | PROVEN: test_case_evolution, test_delta_sprint003/004 |
| Smart Intake review resolve / reject | `ReviewAccepted` / `ReviewRejected` | da | da (posle finalize) / ne | — | da / ne | PROVEN: test_delta_sprint002 |
| Ručni dokaz (`POST /api/evidence/predmeti/{id}/dokaz`) | `NewEvidenceRegistered` | da | **ne** (namerno, vidi ispod) | klasifikacija samo sa `dokument_id` | **da** | PROVEN: **test_ns006_t2** |
| Povezivanje klijenta (`confirm-links`) | **ne** | — | — | — | — | odluka ispod |
| Ročište kreirano | `rociste_zakazano` | da | da | — | da | PROVEN: test_beta_gate_rociste_consistency, test_omega_sprint003 |
| Ročište izmenjeno (datum/vreme/status, uključujući otkazivanje) | `rociste_zakazano` (`trigger=rociste_updated`) | da | da | — | da | PROVEN: test_beta_gate_rociste_consistency |
| Ročište obrisano | `SourceInvalidated` (atomski RPC) | da | ne | — | da | PROVEN: test_wave2_2d_corrective_atomic_invalidation |
| Rok potvrđen / odbijen (Danas) | **ne** | — | — | — | **ne čita rokove** | Task 8 |
| Zatvaranje predmeta | `MatterBecameTerminal` (direktan reconcile) | da | ne | — | zatvara sve | PROVEN: test_wave2_2f |

**TRENUTNI DOKAZ / OPOVRGNUTO.** Istorijski trag „ručni dokaz ne emituje događaj" je OPOVRGNUT (emitovanje postoji
od 2026-09-11). Pronađena PRAVA rupa na istoj putanji (PROVEN čitanjem): upis događaja je bio **jedan pokušaj bez
identiteta**, a neuspeh se gutao uz `ok: true` — odgovor identičan uspehu, dok Case Evolution nikad ne sazna za tvrdnju.

**POKUŠAJ OPOVRGAVANJA ODLUKA.**
- *Treba li ručni dokaz da osvežava Genome?* NE. `api.py` (upload) i Smart Intake emituju `NewEvidenceRegistered`
  ZAJEDNO sa `DocumentAccepted`, koji već osvežava Genome — dodavanje `genome_refresh` ovom događaju bi udvostručilo
  plaćeni AI poziv po otpremanju. Posledica ručnog dokaza je `refresh_case_actions` (dokazano), a Genome vidi tvrdnju
  pri sledećem osvežavanju (`_fetch_dokazi_kontekst`). Profesionalni pregled dokaza (Task 4) čita tvrdnje direktno,
  bez AI-ja.
- *Treba li `confirm-links` da emituje `NewClientLinked`?* NE. Jedina posledica (`conflict_check`) traži ime
  PROTIVNE strane, koje ova ruta nema — izvođenje bi bilo nagađanje. V2 pre povezivanja već radi eksplicitnu
  proveru sukoba (NS005 T4, PROVEN). Ostaje kao zabeležena odluka, ne rupa.
- *Izmena `status` kroz `PATCH`* nije dostupna iz V2 (ugovor `rad-predmeta.js`); legacy dug, nije menjano.

**IMPLEMENTACIJA.** `routers/evidence.py::add_dokaz`: deterministički `event_id = uuid5(NS, "NewEvidenceRegistered:dokaz:<id>")`
(isti obrazac kao S6 `NewClientLinked` i `SourceInvalidated`), do 3 pokušaja (0,2 s · n), i aditivno polje odgovora
`dogadjaj: ZAKAZAN | NIJE_ZAKAZAN`. Dispečer, registar posledica i šema NEPROMENJENI.

**FAJLOVI.** `routers/evidence.py`; `tests/ns006_fake.py` (nov: jedinstvenost iz migracija 073/096/099,
`ignore_duplicates`, `.not_`, RPC `claim_pending_events` 091 — NS005 harness netaknut);
`tests/test_ns006_t2_evidence_event_chain.py`.

**ENDPOINTI.** `POST /api/evidence/predmeti/{id}/dokaz` (aditivno polje `dogadjaj`).

**TESTOVI.** `test_ns006_t2_*` 6/6 kroz STVARNU rutu, `emit_durable`, `dispatch_pending_events`,
`handle_case_changed`, reconcile i `risk_engine`:
dokaz → 1 red sa izvedenim id-jem → dispečer → `evidence_classification` (`skipped_no_dokument_id`) i
`refresh_case_actions` `completed` → akcija „Nema uploadovanih dokaza" ZATVORENA, ostale otvorene i ažurirane
(`event_id` = ovaj događaj), bez duplikata; ponovljen dispečer → 0 obrađeno. Regresija: 64 postojeća fajla koja
dodiruju dokaze/Case Evolution/`emit_durable` → 1133 passed.

**TENANT.** B → predmet A: 404; B-ov predmet + A-ov `dokument_id`: 400; 0 dokaza i 0 događaja.

**FAILURE.** Prolazna greška → drugi pokušaj sa ISTIM id-jem → 1 događaj. Iscrpljeno → `NIJE_ZAKAZAN`, tvrdnja
ostaje (nije poništiva bez transakcije; prijavljuje se). Pad posledice → `dispatch_attempts=1`, `failed`; sledeći
prolaz završava SAMO `refresh_case_actions` (klasifikacija ostaje `completed`, ne ponavlja se).

**MUTACIJE (6 ubijenih, 1 preživela po dizajnu).** E1 bez emitovanja → 4 testa padaju; E2 bez identiteta → 3;
E3 bez retry-ja → 1; E4 neuspeh prijavljen kao ZAKAZAN → 1; E7 bez `refresh_case_actions` u registru → 3;
E6 obe brave vlasništva uklonjene → tenant test pada. **E5 (samo provera u ruti uklonjena) PREŽIVLJAVA**: nezavisna
druga brava `shared/evidence_write.py::_proveri_vlasnistvo` (INVARIANT 1) i dalje vraća 404 — to je odbrana u dubini,
ne rupa u testu.

**OGRANIČENJA.** Prozor pada procesa između upisa tvrdnje i upisa događaja i dalje postoji (zatvaranje traži RPC kao
migracija 131 — migracija se ne primenjuje u ovom sprintu). Izmena `tip`-a predmeta ne pokreće reconcile (dug).

**SLEDEĆA KAPIJA.** Task 3 — profesionalni Genome ugovor.

---

## TASK 3 — PROFESIONALNI UGOVOR ŽIVOG PREDMETA (3A/3B/3C)

**PROBLEM.** `predmeti.case_dna` je sirov izlaz modela; V2 nema ugovor koji razdvaja izvor, ljudsku potvrdu,
izvođenje i analizu, niti stabilan identitet stavki.

**TRENUTNI DOKAZ.** (PROVEN čitanjem) `case_dna` nema polje vremena osvežavanja; `dokazi_rang`/`kontradikcije`/
`rokovi_kriticni` već nose `dokument_id` razrešen pri upisu (A001/A002/B8, fail-closed); `kontradikcije[].claim_refs`
su efemerne `CLAIM-NNN` oznake (shared/claim_catalog.py — „oznaka nije identitet"); u kodu NE postoji provera koja
par (zakon, član) potvrđuje kao važeći izvor (`validate_law_refs` = samo naziv zakona; `quality_gate._verify_citation`
= da li postoji bilo koji „Član N", bez zakona).

**POKUŠAJ OPOVRGAVANJA.** Da li se `CLAIM-NNN` sme razrešiti pri čitanju? NE — katalog se gradi nad trenutnim
tvrdnjama; nova tvrdnja pomera oznake, pa bi `CLAIM-001` pokazao na drugu tvrdnju. Da li `quality_gate` sme da potvrdi
„ZOO čl. 262"? NE — potvrdio bi i „Zakon o radu čl. 262" istim upitom. Da li predmet bez Genome-a sme imati prazne
sekcije? NE — „nije izračunato" ≠ „nema ničega".

**ODLUKA.** Aditivan, čist modul `shared/genome_contract.py` (pomoćnik vlasnika Genome-a, kao `genome_validator`):
`sastavi(predmet, case_dna, dokumenti, dokazi, izvori, osvezeno)` → ugovor `pg-1`. Ne piše, ne zove model, ne
dohvata sam. Stari potrošači (`/case-dna`, Case Evolution, alarmi) nepromenjeni.

**UGOVOR (pg-1).** `metapodaci` (genome_verzija, osvezeno, dokumenata u predmetu/analizirano/izostavljeno/bez teksta,
provera analize, kompletnost COMPLETE|PARTIAL|DEGRADED|UNKNOWN, stanje izvora), `identitet`, `cinjenice` (= tvrdnje
`predmet_dokazi`, id = `predmet_dokazi.id`), `stranke`, `pravna_pitanja` (+ `pravni_osnovi_neprovereni`,
`potvrdjeni_pravni_izvori: []`, `potvrda_izvora.stanje = NIJE_DOSTUPNA`), `hronologija`, `strategija`, `nedostaje`,
`metrike`, `nesigurnost`. Svaka stavka: `id`, `id_vrsta` (`izvor` | `sadrzaj`), `poreklo`, `vrednost`.
Stanja sekcije: OK / EMPTY / UNKNOWN / DEGRADED / INVALID. Kontradikcije, dokazi kao graf, rokovi, ročišta, spremnost
i akcije se dodaju u Task 4–8.

**KLASE POREKLA.** SOURCE_FACT, HUMAN_CONFIRMED, DETERMINISTIC_DERIVATION, AI_ANALYSIS, UNKNOWN (eksplicitno kad
poreklo nije zabeleženo — ne pogađa se). Tvrdnja: `izvor_tvrdnje=covek` ili `izvor_snage=covek` → HUMAN_CONFIRMED;
pronađena u tekstu svog dokumenta → SOURCE_FACT; `ai_klasifikacija` nepronađena → AI_ANALYSIS; ostalo → UNKNOWN.
Sve iz `case_dna` → AI_ANALYSIS.

**3A.** DOK-NN važi samo za tačno jedan dokument OVOG predmeta; upisani `dokument_id` samo ako je i sada dokument
ovog predmeta; nikad po nazivu fajla. Neispravan datum → `datum: null, datum_neispravan: true`; vrednost van skupa
(uloga, značaj, hitnost) → `null`; stranka bez imena se ne prikazuje (`odbaceno`). Neispravna savetodavna sekcija →
`INVALID`, ostatak ugovora radi.

**3B.** Svaki pravni osnov iz modela: `poverenje: UNVERIFIED_AI_ANALYSIS`, uz determinističke signale
`naziv_zakona_prepoznat` i `broj_clana_moguc` (postojeći validatori, ne nova provera).

**3C.** `snaga_predmeta_procent` = mixed (faktori modela, zbir backend-om), `heatmap.*`/`kriticnost`/`snaga_score`/
`genome_kompletnost` = model_derived, `_analiza_osnov.*`/`_genome_docs_*` = deterministic. Svaka metrika nosi
„NIJE verovatnoća ishoda ni predviđanje suda". Nova metrika uspeha NIJE uvedena.

**FAJLOVI.** `shared/genome_contract.py` (nov), `tests/test_ns006_t3_genome_contract.py` (nov).

**TESTOVI.** 14/14: isti izvori → bajt-identičan ugovor pri 5 nasumičnih redosleda; AI ključevi stabilni i označeni
`sadrzaj`; poreklo 4 tvrdnje (SOURCE_FACT/HUMAN_CONFIRMED/AI_ANALYSIS/UNKNOWN); DOK-07 nepoznat, DOK-02 sa dva
kandidata, naziv fajla, tuđi `dokument_id` → nerazrešeno; `CLAIM-001/CLAIM-999` se ne pojavljuju u ugovoru; bez Genome-a
→ UNKNOWN + nesigurnost; pao izvor → DEGRADED; ulaz nepromenjen; 3A/3B/3C.

**TENANT / FAILURE.** Čista funkcija — opseg vlasnika obezbeđuje učitavanje (Task 9). Pao izvor → DEGRADED, nikad
prazno (PROVEN).

**MUTACIJE (10/10 ubijeno).** G1 nepoznat DOK → prvi dokument; G2 tuđi `dokument_id` prihvaćen; G3 SOURCE_FACT → AI;
G3b AI → SOURCE_FACT; G4 pao izvor → prazno; G5 osnov „VERIFIED"; G6 neispravan datum prihvaćen; G7 mixed →
deterministic; G8 sirove kontradikcije sa CLAIM oznakama u ugovoru; G9 „verovatnoća uspeha".

**OGRANIČENJA.** Vreme osvežavanja nije u `case_dna`; ugovor prima `osvezeno` od pozivaoca (Task 9: iz istorije, ili
`null`). Poreklo starih tvrdnji bez `izvor_tvrdnje` i bez lokacije je UNKNOWN.

**SLEDEĆA KAPIJA.** Task 4 — graf dokaza.

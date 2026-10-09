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

---

## TASK 4 — GRAF DOKAZA

**PROBLEM.** Dokazi su ravna lista; ljudska tvrdnja i tvrdnja modela se ne razlikuju trajno.

**TRENUTNI DOKAZ.** (PROVEN) `predmet_dokazi` nema kolonu autora tvrdnje. Dva pisca kroz jedan primitiv
(`upisi_dokaze`): `add_dokaz` (čovek) i `klasifikuj_i_sacuvaj` (model). `izvor_snage=covek` piše SAMO ručni unos
sa eksplicitnom snagom → dokazuje ljudski unos i bez nove kolone. Pala klasifikacija dokumenta upisuje `tip_dokaza`
„ostalo" uz `ai_tags._klasifikacija_greska` (Phoenix 006).

**POKUŠAJ OPOVRGAVANJA.** Može li se autor izvesti bez nove kolone? Delimično (`izvor_snage=covek`), ali ručni unos
BEZ snage i AI unos koji DC-005 nije našao su identični (`podrazumevano`) → potrebna kolona. Može li se kolona
popuniti podrazumevanom vrednošću? NE — izmislila bi autora starih redova.

**ODLUKA.**
- Migracija **135** (KREIRANA, NIJE primenjena): `predmet_dokazi.izvor_tvrdnje TEXT` nullable, bez DEFAULT-a,
  bez backfill-a, bez CHECK-a (obrazac 118). Vokabular: `shared/evidence_write.py::IZVORI_TVRDNJE`.
- Jedini pisac (`upisi_dokaze`) upisuje autora kad ga pozivalac zna; `add_dokaz` → `covek`,
  `klasifikuj_i_sacuvaj` → `ai_klasifikacija`. Kolona se odbacuje SAMO kad greška baš nju imenuje (PGRST204/42703):
  bez 135 → tačno 2 pokušaja i `izvor_snage` zadržan; bez 118 → autor zadržan; bez obe → upis uspeva bez obe.
- Graf je PROJEKCIJA (`shared/evidence_graph.py`), ne nova tabela: tvrdnje (iz `predmet_dokazi`), dokumenti (sa
  stanjem klasifikacije USPESNA / NEUSPESNA / NIJE_KLASIFIKOVAN), pravni elementi (determinističko grupisanje),
  veze `potpora` / `element` / `protivrecnost` (samo iz perzistiranih V2 kontradikcija sa trajnim UUID tvrdnji).
- Ruta za čitanje `GET /api/predmeti/{id}/genome-v2` (routers/case_dna.py — vlasnik Genome-a): vlasništvo prvo
  (`predmeti.user_id`), pa svi upiti ograničeni na isti predmet I istog korisnika; svaki izvor nosi stanje
  OK/GRESKA; `Cache-Control: no-store`; nema upisa, nema modela; tuđ i nepostojeći predmet → ISTI 404.

**ODGOVORI PO TVRDNJI.** šta (`vrednost`), ko (`poreklo`), koji dokument (`dokument_id` — samo ovog predmeta), gde
(`lokacija` samo ako je pronađena), pravni element (ili `null`), protivrečnosti (lista ili `null` = NEPOZNATO kad
kontradikcije nisu pročitane ili postoje samo u analizi bez veze na tvrdnje), potpora (LOCIRANA_U_DOKUMENTU /
DOKUMENT_BEZ_LOKACIJE / BEZ_POTPORE).

**FAJLOVI.** `migrations/135_predmet_dokazi_izvor_tvrdnje.sql`, `shared/evidence_write.py`, `routers/evidence.py`,
`shared/evidence_graph.py` (nov), `shared/genome_contract.py` (vokabular autora uvozi od pisca), `routers/case_dna.py`
(ruta + učitavanje), `tests/ns006_fake.py` (nepostojeće kolone kao PostgREST), `tests/test_ns006_t4_evidence_graph.py`.

**ENDPOINTI.** NOV: `GET /api/predmeti/{id}/genome-v2`. Izmenjen ponašanjem upisa (aditivno): `POST
/api/evidence/predmeti/{id}/dokaz`.

**TESTOVI.** `test_ns006_t4_*` 9/9 (tvrdnje nastaju STVARNIM putevima: ruta za čoveka, `klasifikuj_i_sacuvaj` za
model sa zamenjenim odgovorom modela — 0 poziva modela). Regresija 191 fajl (dokazi, Case Evolution, `case_dna`,
migracije): 2883 passed, 5 failed = `test_prg_night_register` (svih 5 su u osnovi `99d2c6b9`).
**Uhvaćena sopstvena greška:** prva verzija pisca odbacivala je autora na SVAKU grešku upisa →
`test_impl_task003b_izvor_snage::test_fallback_degradira_tacno_jedan_stepen` je pao; ispravljeno (kolona se odbacuje
samo kad je greška imenuje) i zaključano mutacijom V9.

**TENANT.** B → predmet A: 404, telo bajt-identično nepostojećem predmetu (nema orakla), bez ijednog A podatka u
odgovoru; C (bez predmeta) → 404. A-ov dokument za B-ov predmet → 400 (Task 2).

**FAILURE.** Kontradikcije nepročitane → protivrečnosti NEPOZNATE (ne prazne); tvrdnje nepročitane → graf i
činjenice DEGRADED; sve to bez 5xx.

**MUTACIJE (8/8 ubijeno).** V1 bez opsega vlasnika; V2 ljudska tvrdnja upisana kao AI; V3 pala klasifikacija kao
uspeh; V4 nepročitane kontradikcije kao nijedna; V5 čitanje upisuje; V6 pisac ne beleži autora; V7 izmišljena
lokacija; V9 autor odbačen na svaku grešku.

**OGRANIČENJA.** Do primene 135, nove ljudske tvrdnje BEZ snage su UNKNOWN (pošteno, ne „ljudske"). Graf je ograničen
na 500 tvrdnji i 500 dokumenata (`metapodaci.skraceno`). Prikaz samo OTVORENIH V2 kontradikcija (Task 5 proširuje).

**SLEDEĆA KAPIJA.** Task 5 — profesionalne kontradikcije.

---

## TASK 5 — PROFESIONALNE KONTRADIKCIJE

**PROBLEM.** V2 nema prikaz kontradikcija; analiza ih daje kao slobodan tekst sa efemernim oznakama.

**TRENUTNI DOKAZ.** (PROVEN) Kanonski identitet već postoji: `shared/contradiction_materializer.py` (CLAIM → UUID,
fail-closed) + `shared/issue_v2.py` (identitet po skupu tvrdnji i tipu relacije, kontinuitet sadržavanjem) +
perzistencija 119–125 (stanja OPEN/REVIEW_REQUIRED/RESOLVED/NOT_OBSERVED/SUPERSEDED; zatvaranje neopaženih kroz
`NOT_OBSERVED` pri kompletnom opažanju, A016.2B). `stranica` tvrdnje je PROCENA (`offset // 2500 + 1`).

**POKUŠAJ OPOVRGAVANJA.** (1) Da li postojeći domen zaista daje 2 tačke za isti par dokumenata? Izvršeno kroz
`materializuj` + `razresi_paket`: DA (dva različita skupa tvrdnji → 2× NEW_ISSUE). (2) Tri tvrdnje o istoj tački →
1 sa 3 člana: DA. (3) Nova tvrdnja koja pojačava tačku → ISTA tačka: `razresi_kontinuitet` → CONTINUATION, isti
`issue_id`. (4) `CLAIM-999` → UNRESOLVED_CLAIM_REF. Nijedan nov mehanizam identiteta nije potreban.
**Pronađen sopstveni propust (Task 3):** ugovor je prikazivao procenu kao `strana` — preimenovano u `strana_procena`
(tvrdnja) i `strana_po_analizi` (navod modela).

**ODLUKA.** Prikaz nad perzistiranim V2 stanjem; isto „ili-ili" pravilo kao Case Actions (A015): otvorene V2 → aktivne
su one; inače aktivne su kontradikcije iz analize, kao AI_ANALYSIS bez tvrdnji (`NEPOTVRDJENA_TVRDNJAMA`), sa
dokumentom samo ako se `DOK-NN` zatvoreno razreši i SLAŽE sa upisanim `dokument_id` (neslaganje → `null` +
`neslaganje: true`). Zatvorene V2 kontradikcije su istorija (`zatvorene`), za pregled odvojeno (`za_pregled`).

**IMPLEMENTACIJA.** `services/v2_projection.py::ucitaj_v2_kontradikcije_za_prikaz` (nova funkcija čitanja, sva
stanja + razlog + vremena + svi članovi; postojeća `ucitaj_v2_kontradikcije` za Case Actions NEPROMENJENA);
`shared/genome_contract.py::sastavi_kontradikcije`; ruta `genome-v2` dobija sekciju `kontradikcije`, a graf dokaza
dobija samo OPEN kao protivrečnost tvrdnje.

**SVAKA KONTRADIKCIJA.** jedna `sporna_tacka`, `relacija`, `tezina` (samo iz skupa), `stanje` (AKTIVNA / ZA_PREGLED /
RAZRESENA / VISE_SE_NE_OPAZA / ZAMENJENA), `ucesnici` (tvrdnja, poreklo, dokument, lokacija sa `strana_procena`),
`povuceni_ucesnici`, `dokumenti`, `bez_izvora` (učesnici bez dokumenta — vidljivo, ne pogođeno).

**FAJLOVI.** `services/v2_projection.py`, `shared/genome_contract.py`, `routers/case_dna.py`,
`tests/test_ns006_t3_genome_contract.py` (preimenovano polje), `tests/test_ns006_t5_contradictions.py`.

**TESTOVI.** 9/9 (4 kroz stvarni domen identiteta, 5 kroz rutu). Regresija: svi NS006 testovi + A-serija
(`test_a00*`, `test_a01*`, `test_contradiction_v2_domain`, `test_case_dna*`) → 532 passed, 1 skipped.

**TENANT.** Čitanje kontradikcija ide tek posle provere vlasništva nad predmetom (Task 4 ruta); V2 tabele su
ograničene na `predmet_issues.predmet_id`.

**FAILURE.** Pad čitanja kontradikcija → `DEGRADED`, `sazetak: null` (ne „0 kontradikcija").

**MUTACIJE (8/8 ubijeno).** K1 (#15 iz mandata) učesnik bez izvora vezan za pogođen dokument; K2 zatvorena
prikazana kao aktivna; K3 CLAIM oznake prenete; K4 analiza ima prednost nad V2; K5 nevažeća težina; K6 nepročitano
kao prazno; K7 procena nazvana „strana"; K8 neslaganje oznake i upisanog id-a razrešeno u korist upisanog.
Napomena: K4 je prvi put „preživela" zbog greške u MOM mutacionom alatu (dve izmene istog fajla su se pregazile) —
alat ispravljen, mutacija ponovljena i ubijena. K8 je preživela zbog praznine u testu — test dopunjen.

**OGRANIČENJA.** `RESOLVED` u V2 i dalje nema pisca (postojeće, A016.2B); prikaz ga podržava kad nastane. Kontradikcije
iz analize bez veze na tvrdnje ne mogu imati učesnike.

**SLEDEĆA KAPIJA.** Task 6 — verzije Genome-a i deterministička razlika.

---

## TASK 6 — VERZIJE GENOME-A I DETERMINISTIČKA RAZLIKA

**PROBLEM.** „Šta se promenilo u ovom predmetu od prethodne verzije?" bez modela i bez lažnih promena.

**TRENUTNI DOKAZ.** (PROVEN) `predmet_genome_history.genome_data` čuva PUN snimak verzije N−1 i upisuje se tik pre
upisa verzije N (njegov `created_at` = trenutak nastanka verzije N; `trigger_event` = okidač verzije N, za Case
Evolution `case_evolution:<event_id>`). **Pronađen postojeći kvar:** `_compute_delta` (alarm „Genome ažuriran") poredi
kontradikcije dve verzije po `CLAIM-NNN` oznakama, a one su EFEMERNE — katalog je sortiran po UUID-u tvrdnji, pa svaka
nova tvrdnja koja sortira ispred postojećih pomera numeraciju. Ista sporna tačka (a, b) postaje `[CLAIM-001,
CLAIM-002]` → `[CLAIM-002, CLAIM-003]`, što nije sadržavanje → „1 nova + 1 eliminisana" za nepromenjen predmet.

**POKUŠAJ OPOVRGAVANJA.** Može li se istorijska oznaka razrešiti naknadno? NE — katalog starog snimka nije sačuvan.
Može li se porediti po lokacijama? Ne pouzdano — A005: dve tačke nad istim parom dokumenata se spajaju. Zato: trajni
identitet od sada, „nepoznato" za stare snimke.

**ODLUKA.**
- Proizvođač (`_extract_genome`, oba puta: pozadina i ručni refresh) upisuje uz `claim_refs` i `claim_ids` —
  iste reference razrešene ISTIM katalogom koji je model video (`razresi_reference`), fail-closed: jedna nepoznata,
  duplirana ili tuđa referenca → `None` za celu stavku (nikad delimična lista). Aditivno, kao `dokument_id`
  (A001/A002); `claim_refs` netaknute (V2 materijalizacija ih čita).
- `shared/contradiction_identity.py`: `contradiction_identity_stable` + `identitet_seme_stabilna`; `kljucevi`/
  `razdvoji_kontradikcije`/`uporedi_kontradikcije` primaju funkciju identiteta (podrazumevano nepromenjeno).
- `_compute_delta` daje prednost stabilnoj šemi kad je imaju OBE verzije (postojeće ponašanje za stare snimke
  nepromenjeno — dug, vidi ograničenja).
- `shared/genome_contract.py::promene_genome` (čista): `promene` = strukturne sa trajnim identitetom
  (kontradikcija_dodata/nestala po `claim_ids`; dokumenti i tvrdnje u analizi — prebrojani; rok_dodat/uklonjen/
  promenjen po (dokument, datum); provera analize); `analiticke` = procene modela (snaga — „nije verovatnoća ishoda",
  broj nedostajućih) ODVOJENO; `nepoznato` kad trajnog identiteta nema. Slobodan tekst modela se ne poredi.
- Ruta `GET /api/predmeti/{id}/genome-v2/promene`: trenutna/prethodna verzija (prethodna MORA biti N−1, inače
  UNKNOWN), `nastala`, `okidac`, `dogadjaj_id`, akcije koje je isti događaj osvežio (`case_actions.event_id`),
  poslednjih 10 verzija. Samo čitanje; vlasništvo prvo; istorija ograničena na predmet i korisnika.

**FAJLOVI.** `routers/case_dna.py`, `shared/contradiction_identity.py`, `shared/genome_contract.py`,
`tests/test_ns006_t6_genome_changes.py`.

**ENDPOINTI.** NOV: `GET /api/predmeti/{id}/genome-v2/promene`.

**TESTOVI.** 13/13: `_compute_delta` pri pomerenim oznakama → 0/0, stvarna nova tačka → 1; proizvođač razrešava
`claim_ids` (nepoznata / duplikat / delimična lista → `None`, `claim_refs` netaknute); v17→v18 iz jednog novog dokumenta →
tačno {dokumenti 2→3, nova kontradikcija (C,D), nov rok 2025-05-10, tvrdnje 4→6} + odvojeno 2 analitičke; ista analiza
regenerisana (obrnut redosled, preformulisan tekst, pomerene oznake, drugi naziv roka) → 0 promena; isti ulaz → isti
izlaz; snimak bez trajnih veza → kontradikcije „nepoznato"; rok promenjen po dokumentu; prva verzija → bez promena;
ruta: promene + događaj + akcije, 0 upisa; B → 404 identičan nepostojećem; nedostajuća N−1 → UNKNOWN; pad istorije →
DEGRADED. Regresija (25 postojećih fajlova sa `contradiction_identity`/`_compute_delta`/`_extract_genome` + NS006):
587 passed, 1 skipped.

**TENANT.** B ne vidi istoriju A (404 bez orakla).

**FAILURE.** Istorija nepročitana → DEGRADED (ne „bez promena"); N−1 ne postoji → UNKNOWN.

**MUTACIJE (8 ubijeno, 1 preživela po dizajnu).** P1 `_compute_delta` bez stabilne šeme (= stanje pre ispravke);
P2 delimična lista `claim_ids`; P3 razlika po oznakama; P4 slobodan tekst kao promena; P5 nepoznato prećutano; P6 bilo
koja prethodna verzija; P7 pad istorije kao bez promena; P9 (#7 iz mandata) ruta istorije bez provere vlasništva →
B vidi istoriju → test pada. **P8 (filter `user_id` na upitu istorije uklonjen) PREŽIVLJAVA**: provera vlasništva nad
predmetom (P9) je prava brava, filter po korisniku je dodatni sloj.

**OGRANIČENJA.** Snimci napravljeni PRE ove izmene nemaju `claim_ids`: za njih je razlika kontradikcija „nepoznato", a
postojeći alarm `_compute_delta` i dalje može da prijavi lažnu promenu kontradikcije za takav par (dug koji nestaje
posle dva osvežavanja). Promene ročišta/potvrđenih rokova nisu deo snimka Genome-a (prikazuju se kroz akcije i Danas).

**SLEDEĆA KAPIJA.** Task 7 — rizik i spremnost bez pseudo-predviđanja.

---

## TASK 7 — RIZIK I SPREMNOST BEZ PSEUDO-PREDVIĐANJA

**PROBLEM.** Genome mora biti koristan advokatu, ne dekorativan, i ne sme da glumi predviđanje ishoda.

**TRENUTNI DOKAZ.** (PROVEN, izvršeno u lažnoj bazi) `GET /api/matter-intel/predmeti/{id}` pri čitanju upisuje
`predmet_health_log`, emituje alarme (`health_score_promenjen`, `rok_kritican`) i pad izvora tretira kao prazno
(`return_exceptions=True` → `[]`). `risk_engine.calculate_procesni_rizik` i `case_readiness.compute_case_readiness`
su čiste funkcije.

**POKUŠAJ OPOVRGAVANJA.** Da li se „0 tvrdnji" i „tvrdnje nisu pročitane" sada razlikuju? DA (test). Da li pale
akcije daju READY? Pre izmene bi `compute_case_readiness([])` vratio READY — zato se ne poziva kad akcije nisu pročitane.

**ODLUKA.** Bez novog motora rizika. U kanonskog vlasnika spremnosti (`shared/case_readiness.py`) dodata čista
`pregled_spremnosti`: dimenzije (pokrivenost procene „N od M tvrdnji", nedostajući tipovi dokumenata, zakazana ročišta
30/7/propuštena, procesni rizik (pravilo) sa faktorima, aktivne kontradikcije, operativna spremnost nad otvorenim
akcijama), svaka sa `znacenje`, `izvor`, `stanje`, `klasa: deterministic`. Izvor koji nije pročitan → `DEGRADED` i
`vrednost: None`; procesni rizik se ne računa ako bilo koji od 3 ulaza nije pročitan. Ruta `genome-v2` dobija sekciju
`spremnost` i čita `rocista` i otvorene `case_actions` (ograničeno na predmet; ročišta i na korisnika). `matter_intel`
nije menjan (legacy ga i dalje koristi).

**FAJLOVI.** `shared/case_readiness.py`, `routers/case_dna.py`, `tests/test_ns006_t7_readiness.py`.

**TESTOVI.** 11/11: vrednosti jednake kanonskim vlasnicima (isti `calculate_procesni_rizik`); 5 parametrizovanih padova
izvora → tačno pogođene dimenzije DEGRADED, ostale OK; prazno ≠ palo; nijedna reč o verovatnoći/šansi/predviđanju; ruta
→ 0 upisa i 0 konstruisanih klijenata modela (OpenAI/AsyncOpenAI zamenjeni klasom koja puca); KONTRAST: legacy
`matter_intel` GET u istoj bazi upisuje `predmet_health_log`. Regresija (37 fajlova sa readiness/risk/matter_intel +
NS006): 722 passed, 1 skipped.

**TENANT.** Isto kao Task 4 (vlasništvo prvo, 404 bez orakla).

**MUTACIJE (7/7 ubijeno).** R1 (#5 iz mandata) pao izvor prikazan kao 0; R2 pale akcije = spremno; R3 rizik iz delimičnih
podataka; R4 otvaranje ekrana upisuje; R5 otvaranje ekrana zove model; R6 (#14) „verovatnoća uspeha"; R7 otkazano ročište
se broji. Napomena: R1–R3 su prvi put prijavljene kao NEISPRAVNE (ne preživele) jer je blok dodat heredoc-om imao LF u
CRLF fajlu — fajl ujednačen, alat ojačan, mutacije ponovljene i ubijene.

**OGRANIČENJA.** Potvrđeni rokovi (`predmet_hronologija`) nisu deo procesnog rizika (risk_engine čita ročišta) —
postojeće ponašanje, vidi Task 8.

**SLEDEĆA KAPIJA.** Task 8 — integritet motora akcija.

---

## TASK 8 — INTEGRITET MOTORA AKCIJA

**PROBLEM.** Genome koji vidi problem a ne proizvede kanonsku akciju je beskoristan; akcija mora biti tačna, bez
duplikata, i nikad zatvorena/otvorena na osnovu podataka koje sistem nije pročitao.

**MATRICA (PROVEN kroz stvarni reconcile):**

| Stanje | Akcija (postojeća semantika) |
|---|---|
| bez tvrdnji | PRIBAVITI_DOKAZ „nema dokaza", critical (Task 2: nov dokaz je ZATVARA) |
| nedostajući tip dokumenta | PRIBAVITI_DOKAZ „Nedostaje …", high |
| zakazano ročište ≤ 30 dana | PRIPREMITI_PODNESAK, rok = datum, prioritet po danima; pomereno → ISTA akcija ažurirana |
| propušteno zakazano ročište | ostaje critical, „PROPUŠTENO" (ne nestaje sa satom) |
| otkazano ročište | akcija se zatvara |
| otvorena V2 kontradikcija | RAZRESITI_KONTRADIKCIJU (`v2:contradiction:<id>`), prioritet po težini; NOT_OBSERVED → zatvara se |
| terminalan predmet | sve otvorene se zatvaraju; Workspace ga ne prikazuje ni kad reconcile nije pokrenut |
| tvrdnje bez procene | NEMA akcije (postojeća odluka: `classify_case_problem` → None) — zabeleženo, nije menjano |
| potvrđen rok (`predmet_hronologija`) | NEMA akcije — vidi odluku ispod |

**PRONAĐEN I ZATVOREN KVAR (PROVEN izvršavanjem pre izmene).** `_compute_target_actions` je pad čitanja izvora
tretirao kao prazan izvor (`return_exceptions=True` → `[]`): pad čitanja `rocista` → `created=0 updated=3 closed=1` —
akcija „Ročište (Osnovni sud u Beogradu) za 5 dana" je ZATVORENA; pad čitanja `predmet_dokazi` → `created=1` — lažna
kritična „Nema uploadovanih dokaza za radni predmet". Ista klasa u `_consequence_case_intelligence_summary` (trajan
sažetak rizika iz nepročitanih izvora). Sada oba podižu izuzetak → posledica `failed` → postojeći retry/DEAD_LETTER;
nijedna akcija i nijedan sažetak se ne menjaju na osnovu delimičnih podataka. `matter_intel` (legacy prikaz) nije diran.

**ODLUKA O ROKOVIMA.** Potvrđeni rokovi NISU uvedeni u `case_actions`: vlasnik obaveze je domen rokova
(`shared/rokovi.py`/`rok_potvrda`), a V2 Danas ih već prikazuje iz kalendara; druga reprezentacija iste obaveze u
`case_actions` bi dala dva zapisa za jedan rok na istom ekranu (krši „1 koncept = 1 vlasnik"). Zabeleženo kao dug za
odluku foundera, ne kao rupa koju ovaj sprint popunjava.

**FAJLOVI.** `services/case_evolution.py`, `tests/test_ns006_t8_case_actions.py`.

**TESTOVI.** 15/15 kroz stvarni reconcile i dispečer: ročište → akcija i pomeranje ažurira ISTI red (isti id); otkazano
zatvara; propušteno ostaje kritično; V2 kontradikcija otvara/zatvara; zatvoren predmet zatvara sve i nestaje iz
`/api/workspace`; terminalan bez reconcile-a i dalje skriven; razlog i izvor na svakoj akciji, bez izmišljenog roka; isti
događaj dvaput i PARALELNO → po jedna otvorena akcija po ključu (delimičan UNIQUE iz 099); „restart" → `created=0` i
isti skup; pad čitanja (3 tabele) → izuzetak i NEPROMENJENE akcije; kroz dispečer: pad → `greske=1` i akcija preživljava,
sledeći prolaz uspeva; sažetak se ne upisuje iz nepročitanih izvora (2 tabele), a uz ispravne se upisuje. Regresija (88
fajlova sa case_evolution/case_actions/workspace): 1499 passed, 1 failed = `test_phoenix_mission_013…` (u osnovi).

**TENANT.** Reconcile je po predmetu (pozivalac je kanonski događaj); Workspace po korisniku (postojeće).

**MUTACIJE (8/8 ubijeno).** A1 (#9) bez filtera terminalnog predmeta; A2 (#10) nestabilan ključ ročišta; A3 (#10) bez
dedupe; A4 bez razloga; A5 pad čitanja ponovo = prazno; A6 sažetak iz nepročitanih izvora; A7 propušteno ročište ispada;
A8 Workspace bez filtera terminalnih predmeta. A7 i A8 su prvo PREŽIVELE (praznine u testu) — dodata 2 testa.

**OGRANIČENJA.** Legacy `PATCH status` i dalje ne emituje `MatterBecameTerminal` (akcije ostaju `open` u bazi, ali su
skrivene u Workspace-u i worklist-u). Reconcile i dalje nema transakcijsku serijalizaciju (postojeći SINGULAR2-DEBT).

**SLEDEĆA KAPIJA.** Task 9 — V2 API površina.

---

## TASK 9 — V2 API POVRŠINA ŽIVOG PREDMETA

**PROBLEM.** Najmanja čista površina za čitanje, bez aliasa i bez curenja između kancelarija.

**ODLUKA (PROVEN pregledom ruta).** Nove rute su samo dve: `GET /api/predmeti/{id}/genome-v2` (ugovor: identitet,
činjenice, stranke, pravna pitanja, hronologija, strategija, nedostaje, metrike, nesigurnost, `dokazi` (graf),
`kontradikcije`, `spremnost`) i `GET /api/predmeti/{id}/genome-v2/promene`. Postojeće se ponovo koriste:
`GET /api/case-actions/predmeti/{id}` (otvorene akcije predmeta) i `GET /api/workspace` (tabla). Graf, kontradikcije i
spremnost su SEKCIJE jednog odgovora, ne zasebne rute (jedan zahtev pri otvaranju Analize).

**PRONAĐENO I ISPRAVLJENO.** Postojeća `GET /api/case-actions/predmeti/{id}` (koju V2 ponovo koristi) za neispravan
id vraća 500 (Postgres 22P02) — izmereno kad je lažna baza naučila 22P02 za `predmeti.id`. Sada, kao i nove rute: isti
404 za tuđ, nepostojeći i neispravan id.

**FAJLOVI.** `routers/case_dna.py` (provera formata), `routers/case_actions.py` (provera formata),
`tests/ns006_fake.py` (22P02 za `predmeti.id`), `tests/test_ns006_t9_api_surface.py`.

**TESTOVI.** 12/12: sve 4 rute traže prijavu (401); za 3 rute po predmetu: tuđ / nepostojeći / neispravan id →
bajt-identičan 404, bez ijednog podatka A; vlasnik dobija 200; Workspace B ne vidi akcije A; član kontradikcije iz
DRUGOG predmeta → tekst NE curi (`tvrdnja: null`, UNKNOWN); 620 tvrdnji → 500 + `skraceno.dokazi: true`; samo GET i
tačno 2 nove rute. Regresija: 104 NS006 + 939 (case_actions) passed.

**MUTACIJE (5/5 ubijeno).** S1 postojeća ruta bez provere formata; S2 nova ruta bez provere formata; S3 404 sa
traženim id-jem; S4 bez granice; S5 tvrdnje bez opsega predmeta.

**OGRANIČENJA.** Granica 500 tvrdnji/dokumenata/ročišta/akcija po odgovoru; iznad toga UI vidi `skraceno`.

**SLEDEĆA KAPIJA.** Task 10 — V2 UI „Analiza".

---

## TASK 10 — V2 UI „ANALIZA" (profesionalni Case Genome)

**PROBLEM.** Advokat treba da vidi razumevanje predmeta (Genome), dokaze, protivrečnosti, rizike i spremnost sa
POREKLOM svake stavke, bez trošenja AI kredita pri otvaranju i bez pseudo-predviđanja.

**ODLUKA.** Tačno jedna nova kartica predmeta („Analiza", druga, posle Pregleda); bočni meni nepromenjen. Modul
`frontend-v2-ng/src/analiza-predmeta.js` (`VxAnalizaPredmeta`) čita SAMO `GET genome-v2` i `GET genome-v2/promene`
(lenjo: tek kad se kartica otvori, jednom po predmetu). Poreklo je i REČ i stil (AI = isprekidan okvir, nikad isto kao
„iz dokumenta"). Ocene modela su u zasebnom bloku, svaka sa „NIJE verovatnoća ishoda". DEGRADED/UNKNOWN/INVALID imaju
sopstvene poruke; greška servera ≠ prazno. „Izvor: …" otvara Dokumente sa izabranim dokumentom.

**FAJLOVI.** `frontend-v2-ng/src/analiza-predmeta.js` (nov), `index.html` (kartica + odeljak + skript pod build
tokenom), `src/app.js` (ruta `/analiza`, otvaranje dokumenta iz Analize), `src/app.css` (traka kartica se pomera unutar
sebe na svim širinama; `.an-*`, `.prov`), `package.json` (`verify:live-analiza`), `tests/live-analiza.mjs`,
`tests/ns006_ui_fixture.py` + `tests/ns006_realni_predmet.py` (odgovori su STVARNI backend odgovori nad realističnim
predmetom, ne ručno pisani), `tests/live-primary-e2e.mjs` (očekivani spisak kartica: dodata tačno „Analiza").

**TESTOVI.** `live-analiza` 41/41: sadržaj iz ugovora, 4 klase porekla kao reč, promene (strukturne odvojene od
analitičkih), pala klasifikacija = neuspeh, pravni osnovi = „predlog analize", protivrečnost sa izvorima i procenjenom
stranom, spremnost bez predviđanja; cena: tačno 2 GET, ništa van ugovora, povratak ne čita ponovo, Pregled ne čita
genome-v2; DEGRADED = stanje GREŠKA (ne PRAZNO); 500/404 jasna poruka bez sadržaja; prelazak A→B i prelazak na drugi
predmet istog korisnika dok odgovor kasni → ništa od A na ekranu; XSS kao tekst; 360–1440 px u obe teme bez preliva;
0 spoljnih zahteva; nijedan token u konzoli. Ceo NG paket protiv NS006 servera: 30/30 skripti zeleno (posle ažuriranja
očekivanih kartica `e2e:primary` 51/51).

**MUTACIJE (9/9 ubijeno + dokaz dvostruke brave).** U1 dodatni refresh poziv pri otvaranju; U2 ponovno čitanje pri
povratku; U4 metrika nazvana „verovatnoća uspeha"; U5 spljošteno poreklo; U6 DEGRADED kao prazno; U7 greška = prazna
analiza; U8 tvrdnja kao HTML; U9 skript van build tokena (`test_ns0051` pada). Prvi prolaz je ostavio U1/U4/U6
žive → test dopunjen (lista dozvoljenih zahteva, `textContent` zatvorenih blokova, vrsta stanja). U3 (uklonjena samo
provera generacije) PREŽIVLJAVA s razlogom: abort zahteva je druga, nezavisna brava; U3a (uklonjen samo abort) takođe
preživljava; U3b (obe uklonjene) je UBIJENA — test hvata zastareo prikaz.

**OGRANIČENJA.** Analiza se ne osvežava sama dok je otvorena (bez ankete); nova verzija se vidi pri sledećem otvaranju
predmeta. Ocene modela su prikazane, ali uvek kao analitičke.

**SLEDEĆA KAPIJA.** Task 11 — Pregled svestan događaja.

---

## TASK 11 — PREGLED SVESTAN DOGAĐAJA

**PROBLEM.** Advokat koji otvori predmet treba odmah da vidi šta se promenilo od prošle verzije analize, šta traži
pažnju i koji je sledeći korak — bez druge AI sinteze i bez drugog motora preporuka.

**ODLUKA.** Blok „Stanje predmeta" na vrhu Pregleda (`frontend-v2-ng/src/zivi-pregled.js`, `VxZiviPregled`):
A. Šta se promenilo ← `GET genome-v2/promene` (najviše 4 + veza „Detalji u Analizi"); B. Šta traži pažnju ← kanonske
`case-actions`, samo kritične i visoke; C. Sledeći korak ← ista lista, prva po kanonskom redosledu (prioritet, pa
rok). Prioritet ima sopstveni stil (ne meša se sa oznakom porekla). Lenjo: samo kad je Pregled aktivan, jednom po
predmetu.

**FAJLOVI.** `src/zivi-pregled.js` (nov), `index.html` (blok + skript pod build tokenom), `src/app.js` (ožičenje,
čišćenje), `src/app.css`, `package.json` (`verify:live-pregled-zivi`), `tests/live-pregled-zivi.mjs`,
`tests/live-analiza.mjs` (Pregled sada čita promene, ali i dalje NE pun Genome).

**TESTOVI.** `live-pregled-zivi` 30/30 (stvarni backend odgovori): promene iz ugovora + veza na Analizu; pažnja = samo
kritične/visoke (i kad su srednje/niske prve u odgovoru); sledeći korak po kanonskom redosledu (bez kritičnih:
srednji pre niskog); svaka radnja kaže ZAŠTO i rok; ništa izmišljeno; cena: tačno 2 GET, ništa van ugovora, povratak
ne čita ponovo, Dokumenti ne čitaju; pad promena / radnji → GREŠKA „ne znači da nema", nikad „nema radnji"; pošteno
prazno i prva verzija; zakasneli odgovor A ne na drugom predmetu ni kod korisnika B; prelazak na tuđ predmet prazni
blok i u skrivenom DOM-u; XSS kao tekst; 360/768/1440 bez preliva. Ceo NG paket: 32/32 skripte zeleno.

**MUTACIJE (12/13 ubijeno + 1 dokazana druga brava).** P1 pad radnji = prazno; P2 pad promena = prazno; P3 pažnja sa
niskim prioritetima; P4 bez kanonskog redosleda; P5 čita pun Genome; P6 ponovno čitanje; P7 aktivira se na svim
karticama; P8 razlog kao HTML; P9 izmišljena promena; P10 veza na pogrešnu karticu; P11 izlazak ne prazni blok;
P12b abort i generacija uklonjeni; P13 skript van build tokena. Prvi prolaz ostavio P3 i P11 žive → dodati scenariji.
P12a (samo abort uklonjen) preživljava: generacija je nezavisna brava.

**SLEDEĆA KAPIJA.** Task 12 — Danas povezan sa kanonskom tablom.

# VINDEX — QA-02 Final Beta Blocker: ljudska ispravka vrste dokumenta

**Datum:** 2026-10-16 · **Grana:** `beta/qa02-rucna-vrsta-2026-10-16` (lokalna, od `main` `649583c7`) · **NO PUSH · NO MERGE · NO DEPLOY · NO PRODUCTION WRITES**

## 1. Životni ciklus vrste dokumenta (izmereno u kodu)

| Faza | Gde živi vrsta | Ko piše (pre ove grane) |
|---|---|---|
| Prijem (posle obrade) | `intake_documents.document_type` (CHECK: 13 engleskih šifri, mig. 074) | samo worker (heuristika 0,85 ili model) — nijedan ljudski put |
| Prikačivanje (finalize) | kopira se u `predmet_dokumenti.tip_dokaza` | `routers/smart_intake.py` |
| Posle prikačivanja | `predmet_dokumenti.tip_dokaza` | `routers/evidence.py::klasifikuj_i_sacuvaj` (posledica `NEW_EVIDENCE_REGISTERED` i ručno „Reklasifikuj“) — **bezuslovno prepisuje** sa srpskom AI šifrom |

Veze: `predmet_dokumenti.source_intake_job_id` (095) i `source_intake_job_segment_id` (094) postoje i upisuju se pri svakom prikačivanju; `intake_job_segments.document_id` vezuje deo posla za `intake_documents` red. `intake_processing_outcomes.segment_id` (093) razlikuje delove istog posla.

**Dokazan uzrok blokera:** (a) nije postojala ruta koja menja vrstu; (b) i kad bi postojala, pozadinska AI klasifikacija bi je posle prikačivanja tiho prepisala (bihejvioralni RED ispod).

## 2. Ispravka (bez migracije, bez nove arhitekture)

| Deo | Izmena |
|---|---|
| Pre prikačivanja | `POST /api/smart-intake/documents/{id}/vrsta {vrsta, prethodna}` — vlasništvo `intake_jobs.uploaded_by`; vrsta iz `DOCUMENT_TYPES`; CAS na `prethodna`; za vreme upisa drži postojeće zauzeće finalizacije (`claim_intake_finalize`); ljudska odluka = red u `intake_processing_outcomes` (`user_corrected`, `fields_corrected=['document_type']`, nova vrsta); audit `dokument_vrsta_ispravljena` (staro → novo, akter). Pad zapisa ili audita → vrsta se vraća (CAS), 503. |
| Prikačivanje | `vrste_advokata()` — dokument nosi ljudsku vrstu samo ako je njegova TRENUTNA vrsta neka koju je advokat izabrao, povezana preko segmenta (ili nesegmentiran posao sa tačno jednim dokumentom), nikad po nazivu. Takav red ulazi u predmet sa `ai_tags._vrsta_advokat`. Pad čitanja → 503, zauzeće oslobođeno. |
| Posle prikačivanja | `POST /api/evidence/predmeti/{p}/dokumenti/{d}/vrsta {vrsta, prethodna}` — vlasništvo predmet+dokument; `tip_dokaza` i oznaka jednim CAS UPDATE-om; audit; pad → vraćanje vrste i `ai_tags`, 503. |
| AI klasifikacija | `klasifikuj_i_sacuvaj` piše vrstu samo `WHERE ai_tags->>'_vrsta_advokat' IS NULL` (isti UPDATE, bez čitanja-pa-pisanja); red sa oznakom dobija samo pravne elemente i tvrdnje. Ako baza odbije uslov: čitanje oznake pa upis (logovano). „Reklasifikuj“ kaže da je vrsta zadržana. |
| Prikaz | GET posla vraća `document_id`, `tip_odredio_advokat` (`null` = nepoznato) i `dozvoljene_vrste`; `evidence_graph` prikazuje ljudsku vrstu kao uspešnu klasifikaciju. V2: izbor + „Sačuvaj vrstu“ u prijemu (po delu fajla) i u detalju dokumenta predmeta. |

Fajlovi: `routers/smart_intake.py`, `routers/evidence.py`, `shared/intake_documents.py`, `shared/evidence_graph.py`, `shared/audit_immutable.py` (+1 akcija u dozvoli), `frontend-v2-ng/src/{prijem-predmeta,app}.js`; testovi `tests/test_qa02_rucna_vrsta.py`, `frontend-v2-ng/tests/live-vrsta-dokumenta-e2e.mjs`; test-infra `tests/ns005_harness.py` (`kolona->>ključ` kao Postgres), `tests/osb003_solo_server.py` (+vrste/brojač audita u `/__osb003/stanje`).

## 3. Dokazi

### Prihvatni testovi (`tests/test_qa02_rucna_vrsta.py`, stvarne rute + worker + finalize + posledica AI klasifikacije, lažna baza)

| # | Zahtev | Test(ovi) | RED na `649583c7` | GREEN |
|---|---|---|---|---|
| 1 | tužba → žalba, prikaz + baza | `test_1_*` | pada (ruta ne postoji; akcija nije u dozvoli audita) | prolazi |
| 2 | opstaje kroz prikačivanje + AI | `test_2_ispravka_opstaje…` (+ kontrola bez ispravke) | pada | prolazi |
| 3 | ispravka već prikačenog | `test_3_4_…` | pada | prolazi |
| 4 | AI ne poništava | `test_4_AI_ne_prepisuje_red_sa_oznakom_advokata_bez_rute` ×2 — **bihejvioralni RED: `'podnesak' == 'appeal'`**; `test_4_uslov_odbijen…` | pada | prolazi |
| 5 | izolacija korisnika | `test_5_*` (404 pre/posle, 401 bez tokena) | pada | prolazi |
| 6 | isti naziv fajla | `test_6_*` | pada | prolazi |
| 7 | segmentiran upload | `test_7_*` (stvaran 3-strani PDF → 2 dela), `test_7b_*` (nepouzdana veza → 409) | pada | prolazi |
| 8 | dvoklik / konkurentnost | `test_8_*` ×4 (jedan zapis; zastareo prikaz 409; finalize ne dobija zauzeće tokom ispravke; AI upis između čitanja i upisa → 409) | pada | prolazi |
| 9 | nedozvoljena vrsta | `test_9_*` ×5 | pada | prolazi |
| 10 | pad upisa/audita ≠ uspeh | `test_10_*` ×9 (audit None/izuzetak u obe faze, pad zapisa odluke, pad vraćanja → „ishod nije poznat“, pad upisa vrste, pad čitanja u finalize i u GET) | pada | prolazi |
| 11 | V2 taksonomija | `test_11_*` | — | prolazi |

Na `649583c7`: 25/26 (prva verzija fajla) pada; jedini prolazni je kontrola „bez ispravke AI i dalje određuje vrstu“. Ukupno na grani: **31/31**.

**Mutacije** (`mut_qa02v.py`, binarno, vraćanje u `finally`): 17/18 ubijeno + M19 (audit izuzetak) ubijena. Preživela M13 (provera `prethodna` u ruti) jer isti slučaj drži CAS u `ispravi_vrstu`; kombinovana mutacija obe zaštite → `test_8_zastareo…` pada.

### Playwright nad PRAVIM `api.app` (`live-vrsta-dokumenta-e2e.mjs`, solo server: stvarne rute, worker, dispečer događaja) — **15/15**
UI i baza u svakom koraku: izbor „Tužba“ → „Žalba“ (baza `appeal`, 1 audit); reload; zastareo prozor → 409 poruka + osvežen prikaz; prikačivanje + AI „dopis“ → u predmetu `judgment*`; izmena u predmetu → `appeal*`; audit pada → „Ishod nije poznat“, baza nepromenjena; korisnik B 404/404; 0 spoljnih veza; 0 JS grešaka.
**Ovaj test je našao kvar** koji pytest nije: audit kao izuzetak u ruti predmeta ostavljao je promenu bez zapisa — ispravljeno, dodat test i mutacija M19.

### Regresija
- Postojeći Playwright: `live-prijem` 53/53, `live-prijem-oporavak-e2e` 18/18, `live-prijem-carobnjak-e2e` 37/37, `live-solo-tok-e2e` 23/23, `live-nazivi-e2e` 53/53, `live-matter` 56/56, `live-analiza` 43/43, `live-prijem-pracenje` 29/29.
- Ceo paket na `d9e94dc3`: 90 padova (19 baznih + 71 novih: stari testovi finalizacije, `vrste_advokata` je uzimala svoj Supabase klijent; i `test_error_disclosure_boundary` — dinamički 503 detalj). Ispravljeno u `9c3a7660` bez izmene starih testova; 12 pogođenih fajlova: 284/284.
- Ceo paket na `9c3a7660`: **19 padova / 10.770 prolaza — skup padova IDENTIČAN baseline-u `649583c7`** (bu001 ×3, coi_intake_convergence ×3, faza1_izvor_pod ×1, faza1_pristupacnost ×3, ns003_protocol ×1, phoenix_013 ×1, prg_night_register ×5, rc_cold_start ×2). Komanda: `OPENAI_API_KEY=sk-test-dummy python -m pytest tests -q -p no:randomly`; Python 3.13.12 lokalno (produkcija 3.11.17 — CI nije pokrenut jer grana nije pushovana). Nijedan stvaran poziv modela.

## 4. Adversarial pregled (sopstveni, nije nezavisan)

| Nalaz | Ozbiljnost | Status |
|---|---|---|
| `risk_engine` „nedostajući dokumenti“ poredi sa srpskim šiframa (`podnesak`…). Izmereno: `tip_dokaza='appeal'` ili `'lawsuit'` → „nedostaje podnesak“. Isto važi već danas za nesigurno klasifikovane dokumente (finalize upisuje englesku šifru, AI se preskače); ljudska ispravka to proširuje na ispravljene dokumente. | MATERIAL (postojeći dug) | NIJE ispravljeno — odluka osnivača (jedinstven rečnik ili mapiranje) |
| `ai_tags->>…` uslov: klijent generiše `ai_tags->>_vrsta_advokat=is.null` (provereno, postgrest 2.28.3); prihvatanje na stvarnom PostgREST-u je INFERRED (dokumentovana sintaksa), nije izvršeno. Ako ga baza odbije: rezervni put čuva odluku (test). | MINOR | dokumentovano |
| Ispravka pre prikačivanja drži zauzeće finalizacije; ako proces padne usred, prikačivanje čeka do 120 s (prikaz kaže „u toku“). Dva dela istog posla se ne mogu ispravljati istovremeno (drugi dobija 409). | MINOR | prihvaćeno |
| Delimično prikačen posao: ispravka u prijemu odbijena („ispravite u predmetu“) i za još neprikačen deo. | MINOR | prihvaćeno |
| Dokument istog sadržaja već u predmetu (dedupe) ne prenosi ljudsku vrstu na postojeći red. | MINOR | prihvaćeno |
| Promena vrste u predmetu ne emituje događaj (Genome/analize se ne osvežavaju same). | MINOR | van opsega (bez novih workflow-a) |
| Ljudska oznaka u `ai_tags` (kolona nazvana „AI“) — semantički nezgrapno, ali atomično sa vrstom i bez migracije. | INFO | — |
| V2 kod 5xx kaže „Ishod nije poznat“ i ponovo čita stanje (postojeći ugovor `api.send`), iako server kaže „vrsta je ostala prethodna“. | INFO | konzervativno |

## 5. Invarijante

| Invarijanta | Status |
|---|---|
| Vrsta iz dozvoljene taksonomije | PASS |
| Tačno jedan dokument | PASS (segment/ID, nikad naziv) |
| Bez ovlašćenja nema promene | PASS (404/401) |
| Ljudska odluka > kasniji AI | PASS (uslovni UPDATE) |
| Opstaje kroz refresh/finalize/pozadinu | PASS (pytest + Playwright) |
| Audit staro → novo + akter, inače nema uspeha | PASS |
| Novija ljudska ispravka se ne gazi | PASS (CAS + zauzeće) |
| Dozvole, RLS, migracije, gejt rokova | nepromenjeno |
| Stvarni PostgREST / produkcija | UNKNOWN (bez produkcionih upisa) |

## 6. Verdikt

**PASS_FOR_SUPERVISED_BETA** — bloker „advokat ne može da ispravi vrstu dokumenta“ zatvoren i dokazan kroz stvarne rute, worker, prikačivanje, AI posledicu i pravi pregledač nad pravim `api.app`. Uz napomene iz §4 (MATERIAL: rečnik za `risk_engine`; INFERRED: PostgREST JSON uslov na stvarnoj bazi).****

Odluke osnivača: (1) push grane i Draft PR; (2) jedinstven rečnik vrsta za `risk_engine` (postojeći dug); (3) da li QA-02 #38 (heuristika → model) uopšte ide pre ovog puta ispravke — ova grana je od `main` i ne sadrži #38.

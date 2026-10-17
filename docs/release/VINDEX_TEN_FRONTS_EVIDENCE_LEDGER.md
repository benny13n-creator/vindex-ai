# VINDEX — Ten Fronts Evidence Ledger (Night Sprint II)

Grana `night/canonical-ten-fronts` (lokalna, bez upstream-a), worktree `C:/vindex-qa/ten-fronts`.
Produkciona baza `d2f8d7d94bd328dde21711b9728e7e970ed0e881`; nasleđen alerts HEAD `40d98288` (7 commita, NIJE deo ovog sprinta).
Brojevi testova su iz stvarnih pokretanja (`python -m pytest … -p no:randomly`), Windows, Python 3.13 (lokalno).

## M01 — Daily Cron false-success propagation
| Field | Content |
|---|---|
| Canonical source | `api.py::cron_daily` (email modul); nalaz T05 prethodnog sprinta |
| Starting commit | `40d98288` |
| Observed defect | email modul dobija konstantu `"status":"ok"`, `_broj_grešaka` se ne povećava → `greske`/`neisporuceno`>0 i nevalidan oblik daju `ok:true`, heartbeat `broj_gresaka` bez njih, `cron_runs.status="ok"` |
| Claim classification | PROVEN (stvarni dispečer kroz TestClient) |
| Negative test | `tests/test_tenfronts_m01_cron_daily_email.py` — pre izmene **12 failed / 8 passed** (svi neuspešni/nevalidni ishodi = "ok", ok:true; 1 od 12 = nedostajuća oznaka `nema_primalaca`) |
| Implementation | helper `_email_podsetnici_status` (4 brojača, isti ugovor kao email-cron.yml) → ok / nema_primalaca / neisporuceno / greska; poslednja dva +1 greška; `poslato` se broji kad je ceo broj > 0 |
| Files changed | api.py; tests/test_tenfronts_m01_cron_daily_email.py (nov, 20); tests/test_cron_daily_dispatcher.py (fixture: 2-polja → 4-polja stvarni oblik posle T05; tvrdnje iste) |
| Positive test | legitiman ishod (3 poslato / 0 / preskoceno / nema profila) → ok:true, broj_gresaka 0 |
| Adversarial test | mutacija „helper uvek ok“ → 13 pada; „bez +1 greške“ → 12 pada; izuzetak → greska; timeout → timeout; email neuspeh ne obara retention/heartbeat; poziv tačno 1 (nema ponavljanja) |
| Nalaz (postojeći, nije menjan) | `test_cron_daily_dispatcher` harness ne zamenjuje `reap_missing_pipeline_events`, `reap_missing_rociste_events`, `reap_orphan_fakture` → test pokušava STVARAN mrežni poziv (`getaddrinfo failed`) i `ok` je uvek false. M01 test ih zamenjuje lokalno |
| Tests passed | 39 (m01 20 + dispatcher 10 + failclosed_auth + ns007_t25) |
| Tests failed / skipped | 0 / 0 |
| Tests not run | ceo paket |
| Known uncertainty | da li Render Cron poziva `/api/cron/daily`: UNKNOWN |
| Local commit | `e945ff8b` |
| Status | ACCEPTED_VERIFIED |
| Next allowed | YES |

## M02 — Legacy email settings truthful state
| Field | Content |
|---|---|
| Canonical source | `routers/email_notif.py::get_profil`; potrošač `static/vindex.js::emailNotifLoad`; nalaz T09 prethodnog sprinta |
| Starting commit | `e945ff8b` |
| Observed defect | Istorijska tvrdnja („UI prikazuje lažno upozorenje“) u STVARNOM izvršavanju NIJE reprodukovana: sa `supabase==2.28.3` (requirements) `maybe_single().execute()` vraća `None` za 0 redova → `res.data` → **HTTP 500** za svakog korisnika bez profila; UI na `!r.ok` tiho izlazi (adresa „—“, bez stanja SMTP-a). Upozorenje bi se pojavilo tek kad bi ruta vratila skraćen oblik (dokazano Node testom stvarne funkcije) |
| Claim classification | PROVEN (500 + odsustvo `smtp_ok`); istorijsko „lažno upozorenje“ = NOT REPRODUCED u runtime-u, PROVEN kao latentno ponašanje potrošača |
| Negative test | `tests/test_tenfronts_m02_email_profil.py` pre izmene **5 failed / 3 passed** (500) |
| Implementation | `res is None or not res.data` → isti oblik + `smtp_ok: bool(_SMTP_HOST)` |
| Files changed | routers/email_notif.py (+6/-2); tests/test_tenfronts_m02_email_profil.py (nov, 8; 3 izvršavaju stvarnu `emailNotifLoad` u Node-u) |
| Positive test | postojeći profil: zastavice i `smtp_ok` nepromenjeni (konfigurisan/nekonfigurisan) |
| Adversarial test | mutacija `smtp_ok: True` → 2 pada; nema upisa profila, nema slanja, vrednost hosta nije u odgovoru; UI sa stvarnim odgovorom: upozorenje samo kad SMTP stvarno nije konfigurisan |
| Harness ispravka | Node `-e` argv indeks (prvo [2]→[1]) — greška harness-a pre RED-a, ne koda |
| Tests passed | 8 + 36 (alerts api_shape/integracija, b10, gdpr) |
| Tests failed / skipped | 0 / 0 |
| Nalaz klase (NIJE menjan) | 66 poziva `maybe_single().execute()` u routers/shared — svaki koji čita `.data` bez provere `None` ima isti 500 za 0 redova. Van scope-a M02 |
| Local commit | `a0a00e19` |
| Status | ACCEPTED_VERIFIED |
| Next allowed | YES |

## M03 — Global search: team comments (LD-006)
| Field | Content |
|---|---|
| Canonical source | `.vindex_ai_team/MISSION_BOARD.md:129` LD-006; `routers/search.py::_SEARCHERS` |
| Starting commit | `a0a00e19` |
| Observed defect | `predmet_komentari` nije pretraživan; ⌘K paleta starog UI-ja bira kategorije iz fiksnih lista (bez backend-a i bez liste rezultat bi ostao nevidljiv) |
| Visibility model | `routers/komentari.py::get_komentari`: komentare predmeta vidi vlasnik predmeta (`predmeti.user_id=uid`); POST takođe samo vlasnik. PROVEN iz koda. (Uzgred: tuđ predmet → `maybe_single` None → 500 umesto 403; fail-closed, ista klasa kao M02) |
| Claim classification | PROVEN |
| Negative test | `tests/test_tenfronts_m03_search_komentari.py` pre izmene **7 failed / 7 passed** (7 negativnih trivijalno zeleno jer pretrage nije bilo) |
| Implementation | `_search_komentari` kroz `_get_user_predmet_ids` (isti skup/limit kao beleške), `_PO_PREDMETIMA`; legacy: `komentari` na kraj `_cmdkVrste` i „Sve“ `data-vrste`, `_CMDK_ORDER`, `_CMDK_TIP_MAP`, `_CMDK_ICONS`; `sw.js` v152→v153 |
| Files changed | routers/search.py, static/vindex.js, index.html, static/sw.js, tests/test_tenfronts_m03_search_komentari.py (nov, 14) |
| Positive test | sopstveni komentar nađen (eksplicitno i podrazumevano), tip `komentar`, `meta.predmet_id` (postojeći `cmdkSelect` otvara predmet) |
| Adversarial test | tuđi komentar i anomalija (A-ov user_id na B-ovom predmetu) se NE nalaze; B vidi tačno ono što vidi GET komentara; beleške nisu proširene; 4 posebna unosa (%/,/)/SQL); pad → `nepotpuno:["komentari"]`; limit; mutacija „bez in_ filtera“ → 5 pada |
| Fixture/kompatibilnost | prvo umetnuto u sredinu liste → `test_cmdk_search_includes_zadaci` (tačan podniz) pao → `komentari` premešten na kraj; test NIJE menjan |
| Baseline padovi (nisu moji) | `test_faza1_pristupacnost` 3 pada i na `40d98288` |
| Tests passed | 132 (m03 14 + search/bu002/lz003/iron_lawyer/build_identity/wave11/lambda001) |
| Tests failed / skipped | 0 / 0 (u izabranom skupu) |
| Not run | Playwright za ⌘K paletu (nije pokrenut); V2 nije menjan (nema prikaz komentara — po V2 pravilu „samo otvorive vrste“) |
| Local commit | `277435d4` |
| Status | ACCEPTED_VERIFIED |
| Next allowed | YES |

## M04 — Global search silent truncation
| Field | Content |
|---|---|
| Canonical source | `routers/search.py::_get_user_predmet_ids` (`.limit(500)`), `pids[:200]` u 3 pretraživača |
| Starting commit | `277435d4` |
| Observed defect | korisnik sa >200 predmeta: zapis u predmetu van prvih 200 se ne nalazi, a odgovor NEMA `nepotpuno` → izgleda potpuno (predmeti/dokumenti/billing/zadaci nisu pogođeni — idu direktno po `user_id`) |
| Claim classification | PROVEN |
| Negative test | `tests/test_tenfronts_m04_search_ogranicenje.py` pre izmene **9 failed / 5 passed** (201/499/500/501 bez oznake; tekst poruka) |
| Implementation | `_MAX_PREDMETA_PO_UPITU=200`; ako `len(cached_pids) > 200` → tražene vrste iz `_PO_PREDMETIMA` u `nepotpuno`; tekst poruka: V2 „nije u potpunosti pretraženo“, legacy „⚠ Deo pretrage nije potpun“ |
| Files changed | routers/search.py, frontend-v2-ng/src/pretraga.js, static/vindex.js, tests/test_tenfronts_m04_search_ogranicenje.py (nov, 14) |
| Positive test | 0/1/199/200 → bez oznake, rezultati nađeni |
| Adversarial test | mutacija „bez oznake“ → 7 pada; mutacija `>=` → 1 pad (granica 200). PRVI pokušaj `>=` mutacije NIJE izvršen (Windows Python nije video `/tmp`) — rezultat odbačen, ponovljen ispravno |
| Bounded | 1 upit nad `predmeti`, isti `.limit(500)`, isti `pids[:200]` |
| Tests passed | 14 (m04) + 94 (m03, search, bu002, lz003, iron_lawyer) = 108 |
| Tests failed / skipped | 0 / 0 |
| Known uncertainty | redosled `predmeti` bez `.order` → koji predmeti ulaze u prvih 200 nije definisano (postojeće ponašanje, nije menjano); Playwright za poruke NOT_RUN |
| Local commit | `30e39d6f2db615b2b445a26efe31728f411591e2` |
| Status | ACCEPTED_VERIFIED |
| Next allowed | YES |

## M05 — Document upload orphan vectors (PHOENIX-004)
| Field | Content |
|---|---|
| Canonical source | `.vindex_ai_team/MISSION_BOARD.md:316` PHOENIX-004; `api.py::predmet_upload_auto_analyze` (komentar Sentinel: „Pinecone vektor ostaje“) |
| Starting commit | `30e39d6f` |
| Observed defect | ingest upisuje vektore (`scope=predmet_id`, deterministički ID) pre reda u bazi; pad sva 3 pokušaja `insert` → 500, vektori ostaju u deljenom `_owner_ns` |
| Safety finding | ISTI sadržaj u ISTOM predmetu deli ISTE ID-eve → naivno brisanje po prefiksu bi obrisalo vektore postojećeg ispravnog dokumenta. Rešeno proverom baze pre (i posle) brisanja |
| Claim classification | PROVEN (stvarni endpoint + lažni indeks koji drži ID-eve u memoriji) |
| Negative test | `tests/test_tenfronts_m05_orphan_vektori.py::test_upload_pad_upisa_reda_uklanja_svoje_vektore` — pre izmene api.py **FAILED „orphan vektori ostali“** |
| Implementation | `shared/vector_deletion.py::obrisi_vektore_neupisanog_dokumenta` (vlasništvo `_sme_predmet`; namespace; kanonska verzija; REFUSED ako red istog identiteta postoji ili provera padne; listanje po prefiksu; provera stranaca; delete; `_cekaj_da_nestanu`; post-provera trke → VERIFICATION_FAILED); api.py poziva je samo kad `count>0`, pre iste 500 |
| Files changed | api.py, shared/vector_deletion.py, tests/test_tenfronts_m05_orphan_vektori.py (nov, 15), tests/test_sentinel_reliability_fixes.py + tests/test_sprint002_pipeline_a_orphan_cleanup.py (zamena `_get_pinecone_index`; tvrdnje iste) |
| Positive test | brišu se tačno 3 vektora ovog upload-a; drugi dokument istog predmeta, isti sadržaj u drugom predmetu i drugi namespace netaknuti |
| Adversarial test | postojeći red istog identiteta → REFUSED (i na endpointu); pad provere baze / tuđi predmet / prazan ns / prazna/legacy64/nekanonska verzija / prazan predmet / pad listanja → REFUSED bez brisanja; pad delete → PARTIAL_FAILURE; neverifikovano → nije uspeh; ponovljeno čišćenje → ALREADY_ABSENT bez brisanja drugih. Mutacije: bez provere baze → 3 pada; bez poziva u api.py → 1; prefiks bez verzije → 3 (prvi pokušaj ove mutacije NIJE primenjen zbog CRLF — odbačen i ponovljen) |
| Group regression finding | u grupnom pokretanju 2 postojeća testa su pokušala STVARAN Pinecone poziv (conftest blokira, `NetworkAccessBlocked` nije `Exception`) — novi saradnik na grani „insert pao“; dodata zamena indeksa u ta 2 harness-a |
| Tests passed | 467 (20 fajlova koji dodiruju upload/vector_deletion) |
| Tests failed / skipped | 0 / 2 (`test_qa05_slika_finalize` — Tesseract nije instaliran lokalno) |
| Known uncertainty | stvarni Pinecone `list(prefix)`/`delete` NIJE pozvan (LOCAL_TEST_ONLY); rezidualna trka istovremenog uspešnog upload-a istog sadržaja → otkriva se post-proverom (VERIFICATION_FAILED + ERROR „potrebna reindeksacija“), ne sprečava; dokument upisan kroz fallback bez `content_sha256` ne bi bio prepoznat kao vlasnik istih vektora (kolona 095 primenjena u prod) ; ingest koji sam baci ne-kvota izuzetak (pre upisa reda) nije u scope-u |
| Local commit | `cddf2c9f` |
| Status | **DEFERRED** — vraćeno u korektivnoj kapiji PR #45 (v. kraj ledgera); prvobitno ACCEPTED_VERIFIED |
| Next allowed | YES |

## M06 — Background processing durable failure evidence (KEYSTONE-003)
| Field | Content |
|---|---|
| Canonical source | `.vindex_ai_team/MISSION_BOARD.md:350` KEYSTONE-003 |
| Starting commit | `cddf2c9f` |
| Current facts | Istorijski nalaz (log-only) VEĆINOM ZASTAREO: svi okidači (api.py upload, smart_intake, rocista) prešli na `emit_durable` → `case_evolution.handle_case_changed`; izuzetak posledice → `_mark_failed` (trajan `case_evolution_consequences.status='failed'` + greška) → retry/dead-letter event bus-a. Genome refresh je verify-or-raise (verzija mora da se promeni). Klasifikacija je verify-or-raise na `klasifikovan_at`. Ručni `/case-dna/refresh` je sinhron (neuspeh u HTTP odgovoru). Preostali `create_task` pogoci su samo komentari |
| Observed defect | AI klasifikacija padne → fallback upisuje `klasifikovan_at` → posledica `completed` sa `result_ref = dokument_id` (isto kao uspeh). Bez ljudske vrste zastavica postoji u `ai_tags` reda; SA ljudskom vrstom (QA-02 oznaka) uslovni upis ne dira `ai_tags` → neuspeh NIJE nigde trajno zabeležen |
| Claim classification | PROVEN (stvarni QA-02 harness, stvarna posledica i `klasifikuj_i_sacuvaj`) |
| Negative test | `tests/test_tenfronts_m06_pozadinski_neuspeh.py` pre izmene **2 failed / 2 passed** |
| Implementation | `_consequence_evidence_classify` vraća `"<dokument_id>:ai_klasifikacija_neuspesna"` kada je `_klasifikacija_greska`; `handle_case_changed` (nepromenjen) to upisuje u `_mark_completed` i `audit_immutable` metapodatke |
| Files changed | services/case_evolution.py (+5), tests/test_tenfronts_m06_pozadinski_neuspeh.py (nov, 4) |
| Positive test | uspeh → `result_ref == dokument_id` (nepromenjeno) |
| Adversarial test | QA-02 invarijanta potvrđena (ljudska vrsta i oznaka ostaju, AI `ai_tags` se ne upisuje); bez automatskog ponavljanja (`klasifikovan_at` upisan); mutacija vraćanja starog `result_ref` → 2 pada. Duplikat okidača: postojeći čuvar `skipped_already_classified` (nepromenjen). Pad audit upisa: postojeći best-effort, `case_evolution_consequences` red i dalje nosi `result_ref` |
| Tests passed | 4 + 211 (20 fajlova: evidence_classification/result_ref/_klasifikacija_greska) |
| Tests failed / skipped | 0 / 0 |
| Known uncertainty | Nijedan UI/operativni prikaz ne čita `result_ref` — trag je trajan i u auditu, ali nema novog obaveštenja (nova notifikacija = van scope-a / odluka). Posledica čita dokument samo po `id` (bez predmet/user filtera) — događaje pravi server sa sopstvenim ID-em; nije menjano |
| Local commit | `f7106674` |
| Status | ACCEPTED_VERIFIED |
| Next allowed | YES |

## M07 — Case Genome background refresh ownership (BL-004)
| Field | Content |
|---|---|
| Canonical source | `.vindex_ai_team/MISSION_BOARD.md:144` BL-004 |
| Starting commit | `f7106674` |
| Current facts | `_do_genome_refresh` prvi upit: `predmeti.select(case_dna).eq(id).eq(user_id).single()`; postgrest 2.28.3 `SyncSingleRequestBuilder.execute` diže `APIError` za svaki ne-2xx (PostgREST 406/PGRST116 za 0 redova); spoljni `except Exception` → `logger.warning` i povratak. Ništa posle prvog upita se ne izvršava |
| Observed defect | NIJE pronađen — istorijska tvrdnja („nema hard-return“) je tačna samo doslovno; kontrola toka (izuzetak) već zatvara put |
| Claim classification | PROVEN (bezbedno) |
| Proof test | `tests/test_tenfronts_m07_genome_vlasnistvo.py` — 5 passed: tuđi / nepostojeći / prazan uid / timeout → 0 GPT poziva, 0 upisa, 0 događaja, dokumenti nečitani; vlasnik → 1 GPT poziv (kontrola) |
| Adversarial test | mutacija „bez `.eq(user_id)`“ → 2 pada (tuđi, prazan uid) — test zaista hvata gubitak granice |
| Files changed | samo test (nov, 5); produkcioni kod NIJE menjan |
| Known uncertainty | lažna baza modeluje `single()` prema izvoru postgrest 2.28.3; stvarni PostgREST nije pozvan. Defense-in-depth izmena NIJE urađena jer nije potrebna (nije izmišljena ranjivost) |
| Local commit | `9bb13bf8b5e9b44c30a7e0c999882c7207d34c76` (samo test) |
| Status | NO_CHANGE_NEEDED_PROVEN |
| Next allowed | YES |

## M08 — Case Genome staleness after case edit (KEYSTONE-005)
| Field | Content |
|---|---|
| Canonical source | `.vindex_ai_team/MISSION_BOARD.md:352` KEYSTONE-005 (legacy `tip`/`rizik`) |
| Starting commit | `9bb13bf8` |
| Current facts | V2 izmena: `rad-predmeta.js::POLJA` = naziv, tip, tuzilac, tuzeni, vrednost_spora, opis → `PATCH /api/predmeti/{id}`. Genome ulaz (`_do_genome_refresh` → `_extract_genome`): `predmet_dokumenti` (tekst) + `predmet_dokazi` (tvrdnje); iz `predmeti` se čita samo `case_dna` (prethodna verzija). V2 analiza prikazuje „Analiza vN · osvežena <datum>“, abort + `trenutni.id !== id` čuvar. Genome nema zavisnost od izmenjenih polja |
| Observed defect | NIJE pronađen — istorijska premisa ne važi: nijedno izmenjivo polje nije ulaz analize, pa izmena ne može da je učini zastarelom u odnosu na njen ulaz |
| Claim classification | PROVEN (bez defekta) |
| Proof test | `tests/test_tenfronts_m08_genome_ulazi.py` 4 passed: isti dokumenti + različiti metapodaci → identičan ulaz ekstrakcije; spisak V2 polja; tabele pre ekstrakcije; čuvar zastarelog odgovora |
| Adversarial test | mutacija „metapodaci predmeta u ulazu“ → 2 pada |
| Files changed | samo test (nov, 4); kod NIJE menjan |
| Known uncertainty (INFERRED) | Genome `stranke` potiču iz DOKUMENATA; ako advokat ručno promeni tužioca/tuženog, analiza i dalje prikazuje stranke iz dokumenata — to je razlika izvora, ne zastarelost; nije menjano (bila bi nova semantika prikaza) |
| Local commit | `b4cc5b107880caaa453270571dd2bd00c190325f` (samo test) |
| Status | NO_CHANGE_NEEDED_PROVEN |
| Next allowed | YES |

## M09 — Case Genome refresh timeout honesty (KEYSTONE-006)
| Field | Content |
|---|---|
| Canonical source | `.vindex_ai_team/MISSION_BOARD.md:353` KEYSTONE-006 |
| Starting commit | `b4cc5b10` |
| Current facts | V2 nema watcher (bez polling-a). Watcher postoji u starom UI-ju: `static/vindex.js::_genomeBackgroundWatch` (posle `pred_upload_doc`), 6 × 15 s GET `/case-dna` |
| Observed defect | posle isteka hint se vraća na podrazumevani „Obično traje 15–20 sekundi — AI čita sve dokumente predmeta.“ — nepotvrđen ishod izgleda kao obično stanje |
| Claim classification | PROVEN (stvarna funkcija izvršena u Node-u, lažni `setInterval`/`fetch`) |
| Negative test | `tests/test_tenfronts_m09_genome_watcher.py` pre izmene **2 failed / 4 passed** (istek; istek uz pad mreže) |
| Implementation | na isteku isti element: „Osvežavanje analize nije potvrđeno ni posle 90 s — možda je još u toku ili nije uspelo. Prikazana je prethodna verzija; …“; `sw.js` v153→v154 |
| Files changed | static/vindex.js, static/sw.js, tests/test_tenfronts_m09_genome_watcher.py (nov, 6) |
| Positive test | nova verzija → render + podrazumevani hint; tokom čekanja „u toku“ |
| Adversarial test | istek ne pokreće novo osvežavanje (samo GET `/case-dna`); promena predmeta → poruka prethodnog predmeta se ne prenosi, polling staje; pad mreže → isto „nije potvrđeno“ |
| Tests passed | 6 + 89 (build_identity, iron_lawyer, wave11, lambda001, m03, m04) |
| Tests failed / skipped | 0 / 0 |
| Known uncertainty | Playwright NOT_RUN; watcher je samo u `/app-legacy` (V2 ga nema) |
| Local commit | `0a2cff7b` |
| Status | ACCEPTED_VERIFIED |
| Next allowed | YES |

## M10 — Email reminder recipient identity consistency
| Field | Content |
|---|---|
| Canonical source | `docs/v2-execution/VCR002_TASK_LEDGER.md:202` — „Primalac: isključivo vlasnik profila (`profiles.email` po `user_id`)“ (PR #20, spojen) |
| Starting commit | `0a2cff7b` |
| Current facts | `profiles.email` piše samo registracija (`api.py:3266`) i GDPR anonimizacija (`routers/gdpr.py:231`); aplikacija nema promenu adrese za prijavu (`updateUser` samo za lozinku, `static/vindex.js:616`). Zakazani podsetnik: `profiles.email`. GET profil („Šalje se na:“) i POST test: adresa iz JWT-a |
| Observed defect | ekran može da pokaže adresu na koju podsetnici NE idu; probni email ne proverava stvarnog primaoca i šalje se i kad profil nema adresu (a podsetnik tada ne ide nikuda) |
| Claim classification | PROVEN (kod + test); učestalost razlike u produkciji UNKNOWN |
| Policy | NIJE izmišljena: primenjeno postojeće kanonsko pravilo VCR002 (zato ne `BLOCKED_FOUNDER_RECIPIENT_POLICY`) |
| Negative test | `tests/test_tenfronts_m10_primalac.py` pre izmene **4 failed / 4 passed** |
| Implementation | `_adresa_primaoca(supa, uid)` = `profiles.email` po `id` (maybe_single None-safe); GET profil `email` i POST test koriste nju; bez adrese test → 400 |
| Files changed | routers/email_notif.py; tests/test_tenfronts_m10_primalac.py (nov, 9); tests/test_tenfronts_m02_email_profil.py (fixture: `profiles` red — MEĐUMISIJSKA izmena, tvrdnje iste) |
| Positive test | sve adrese iste → ista adresa; zakazani podsetnik i dalje na `profiles.email` |
| Adversarial test | tačno jedan primalac (nikad obe); tuđi profil se nikad ne koristi; bez reda/adrese nema slanja; probni email nosi samo „Test rok“ (bez podataka predmeta); mutacije: probni na JWT → 3 pada; oznaka na JWT → PRVO PREŽIVELA (test nije pokrivao granu sa postojećim notif profilom) → dodat test → 1 pad |
| Tests passed | 9 (m10) + 624 (email/cron/alerts/tenfronts unija) |
| Tests failed / skipped | 0 / 0 |
| Known uncertainty | da li se `profiles.email` i adresa za prijavu razlikuju kod stvarnih korisnika: UNKNOWN (zahteva čitanje produkcije); zastareli `profiles.email` posle promene adrese van aplikacije (Supabase dashboard) ostaje mogući — sada bar VIDLJIV na ekranu i proverljiv probnim emailom |
| Local commit | `662df513` |
| Status | ACCEPTED_VERIFIED |
| Next allowed | YES |

## R01 — Request context propagation (ALPHA-001) — rezerva, procenjena
| Field | Content |
|---|---|
| Canonical source | `.vindex_ai_team/MISSION_BOARD.md:414` ALPHA-001 |
| Starting commit | `662df513` |
| Current facts | S2-3 (2026-08-09) uveo `api.py::_require_auth_async` koji upisuje kontekst u korutinu pozivaoca; `grep`: 0 direktnih `to_thread(_require_auth, …)` poziva osim samog omotača, 14 poziva omotača |
| Proof (izvršeno, nije komitovano) | 20 istovremenih zahteva (A/B) kroz `_require_auth_async` → svaki vidi svoj `user_id` u `_request_ctx`; kontrola: sirov `to_thread` sa `set_request_context` → `None` (klasa defekta realna, ali više nema pozivaoca) |
| Files changed | none |
| Status | NO_CHANGE_NEEDED_PROVEN (nije zamenila primarnu misiju kao nova implementacija) |
| R02–R04 | NIJE procenjeno: R02 verovatno traži novu politiku obaveštenja (STOP uslov rezerve), R03/R04 su otvorena pretraga backlog-a — van „ne lovi backlog“ pravila |

## HANDOFF 2026-10-17 — ispravka dokaza pre Draft PR-a

**M03/M04 (zahtev osnivača: „izostavljeni iz tabele“).** Provereno: oba su u matrici izveštaja (odeljak C) i u ovom ledgeru; nedostajao je samo pun SHA za M04 (i M07/M08) u redu „Local commit“ — ispravljeno gore. Implementacija nije menjana.

| | M03 | M04 |
|---|---|---|
| Pun SHA | `277435d4993dbbb846b4210cafcb72afa179821e` | `30e39d6f2db615b2b445a26efe31728f411591e2` |
| Izmenjeni fajlovi | index.html, routers/search.py, static/sw.js, static/vindex.js, tests/test_tenfronts_m03_search_komentari.py | frontend-v2-ng/src/pretraga.js, routers/search.py, static/vindex.js, tests/test_tenfronts_m04_search_ogranicenje.py |
| Negativni test PONOVLJEN 2026-10-17 na kodu pre ispravke (`git archive` roditelja + test fajl) | `a0a00e19`: **7 failed / 7 passed** (isto kao zapis) | `277435d4`: **9 failed / 5 passed** (isto kao zapis) |
| Posle ispravke | 14 passed | 14 passed (zajedno 28 passed) |
| Granica | komentari samo iz `_get_user_predmet_ids` = `predmeti.eq("user_id", uid)` — ista granica kao `komentari.py::get_komentari`; tuđi komentar i anomalija se ne nalaze; mutacija „bez `in_` filtera“ → 5 pada | 1 upit nad `predmeti` (`.limit(500)`), `pids[:200]` po upitu; >200 → `nepotpuno`; 200 → bez oznake; mutacije „bez oznake“ (7) i `>=` (1) padaju |

**Mrežni poziv u `tests/test_cron_daily_dispatcher.py`.**
- Snimač „deny-all“ (pytest plugin u scratchpad-u, odbija svaki DNS upit i svaki ne-loopback `connect`, beleži host i stek; NIJEDAN stvaran zahtev nije poslat): **21 pokušaj, svi `getaddrinfo('fake.supabase.co')`** — 3 po testu × 7 testova koji zovu dispečer.
- Izvor: sam dispečer (`api.py::cron_daily`) poziva `services/event_bus.py::reap_missing_pipeline_events` (`:1260`), `reap_missing_rociste_events` (`:1330`) i `routers/billing.py::reap_orphan_fakture` (`:1268`); njihov `.execute()` u `asyncio.to_thread` niti gađa Supabase klijent sa test URL-om. Ne test, ne pozadinski zadatak.
- Kategorija odredišta: izmišljeni test host (`fake.supabase.co`, sankcionisan u `tests/conftest.py` i u CI `tests.yml`/`production-runtime.yml`/`v2-ng.yml`); conftest odbija produkcione Supabase kredencijale i blokira upravljane DB hostove → nije produkcija, nema upisa.
- Ispravka (samo test): tri `reap_*` zamenjena u postojećem `_patch_submodules` fixture-u, istim oblikom koji vraćaju stvarne funkcije (`checked/backfilled`, `checked/reaped`). Tvrdnje nepromenjene.
- Posle: **0 pokušaja**, 10 passed. Mutacija `_email_podsetnici_status → "greska"` u `api.py` → 3 pada (test i dalje izvršava stvarni dispečer); `api.py` vraćen, bez izmene.
- Isti razred, NIJE menjano (van naloga): `tests/test_cron_daily_failclosed_auth.py::…test_secret_configured_and_header_matches_passes_auth` — 11 DNS upita ka `fake.supabase.co`.

**CI nalaz posle otvaranja PR #45 (2026-10-17) — stvarni pozivi ka produkciji iz alerts testova.**
- 13 novih CI padova (`test_alerts_email_cron_contract.py` ×6, `test_alerts_email_integration.py` ×7) sa „HTTP 403“: lažni `curl` je pisan bez izvršnog bita; Windows/Git Bash to ne proverava, Linux runner preskače takav fajl na PATH-u i izvršava PRAVI `curl` → workflow korak je slao `POST https://vindex.rs/email-notif/send-reminders` sa sintetičkim ključem (`test-kljuc-…`).
- Posledica: produkcija je odbila svaki zahtev u `_require_cron_or_founder` (403 pre bilo kakvog rada) — nema slanja, rezervacije ni upisa. Testovi koji očekuju neuspeh su pri tome „prošli“ iz pogrešnog razloga.
- Ispravka (samo test, `pokreni`): `chmod 0o755` lažnih alata + fail-closed proba `curl --vindex-lazni-curl` pre pokretanja koraka; ako `curl` nije lažni → `pytest.fail`, korak se ne pokreće. Mutacija „lažni curl van PATH-a“ → 35/36 pada na probi (pravi curl na nepoznatu opciju izlazi bez mreže). Lokalno 44 passed.

## KOREKTIVNA KAPIJA PR #45 — M05 (2026-10-17)

| Field | Content |
|---|---|
| Polazni HEAD | `8b9c693311b0cd384f14ef2c4eae4328f519c9f9` |
| T01 — RED (stvarna funkcija, lažna baza + indeks u memoriji) | A: provera baze (nema reda) → `list()` → `delete()`; B (isti sadržaj, isti predmet) upisuje iste ID-eve i red. (1) B-ov red upisan pre A-ovog `delete()` → B-ovi vektori obrisani, A = `VERIFICATION_FAILED` (otkriveno tek POSLE gubitka). (2) B-ov red upisan posle A-ove završne provere → B-ovi vektori obrisani, A = **`DELETED`** (bez signala). **2 failed** |
| T02 — analiza | Pinecone nema uslovno brisanje; ID-evi su deterministički (predmet + verzija), B upisuje vektore PRE reda u bazi, pa nijedna provera baze (ni neposredno pre `delete()`) ne vidi B u letu; procesni lock ne pokriva više radnika/instanci; metapodatak vlasnika bi B prepisao upsert-om, a provera→brisanje ostaje prozor. Bezbedno rešenje traži migraciju, nov protokol ili promenu identiteta vektora — van ovlašćenja |
| Odluka | **DEFERRED** — vraćen samo `cddf2c9f` (aktivacija u `api.py`, helper, `test_tenfronts_m05_orphan_vektori.py`, zamene indeksa u `test_sentinel_reliability_fixes.py` i `test_sprint002_pipeline_a_orphan_cleanup.py`). Sva 4 izmenjena fajla bajt-identična stanju `30e39d6f` |
| Nerešeno | posle neuspelog upisa reda vektori ostaju u namespace-u vlasnika i dostupni su pretrazi predmeta (prvobitni PHOENIX-004) |
| Nov test | `tests/test_m05_bez_destruktivnog_ciscenja.py` (3): neuspeo upis → 500 i NIJEDAN poziv indeksa; uspešan upload → bez brisanja; helper ne postoji. Mutacija „vrati M05“ → 2 pada |
| T03 | sa odloženim M05 nema destruktivnog čišćenja: normalan upload, neuspeo upis, isti sadržaj, istovremeni upis, drugi predmet, deljen namespace, timeout, pad Pinecone-a i ponovljeno čišćenje svode se na „indeks se ne dira“ |
| Regresija | 22 fajla koji koriste `vector_deletion`/upload + svi Ten Fronts testovi + nov test: **539 passed, 2 skipped, 0 failed** |
| T04 — V2 | `frontend-v2-ng` nema build skriptu (ES moduli bez bundlera); propisana provera je job „V2 NG frontend suites“ iz `v2-ng.yml`: `npm ci` + svaki `verify*` skript uz `serve.mjs 4317`, Node 24.15.0, Chromium (Playwright). Lokalno (Windows): **32/32 PASS, listed 32 = executed 32**; `verify:live-rocista-pretraga` 38/38. Jobovi `e2e`, `python311` i `docker` iz istog workflow-a NISU pokretani |

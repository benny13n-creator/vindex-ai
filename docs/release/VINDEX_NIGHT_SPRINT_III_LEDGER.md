# VINDEX — Night Sprint III „Iron Continuity“ — Evidence Ledger

Grana `night/iron-continuity-ns3` (lokalna, bez upstream-a), worktree `C:/vindex-qa/night-iii`.
Baza: `469085b6a2a4a92b4ddfd929a5d88433743c66cc` = `origin/main` = produkcija (`/api/version` → `commit`, `branch: main`, `sw_cache: vindex-v154`), provereno 2026-10-17.
Okruženje: Windows 10, Python 3.13.12 (lokalno; CI koristi 3.11/3.13), Node 24.15.0, pytest 9.0.3, supabase/postgrest 2.28.3, Playwright (Chromium), Tesseract NIJE instaliran (OCR testovi preskočeni).
Komande testova: `PYTHONIOENCODING=utf-8 OPENAI_API_KEY=sk-test-dummy python -m pytest <fajlovi> -q -p no:randomly` (lokalni `FOUNDER_EMAILS` gde je naveden).
Klasifikacija tvrdnji: PROVEN / INFERRED / ASSUMED / UNKNOWN.

---

## N01 — Izolacija podprocesa i mreže u testovima
| Polje | Sadržaj |
|---|---|
| Početni commit | `469085b6` |
| Problem | Cron/notifikacioni testovi — da li išta izlazi na mrežu (incident PR #45: pravi `curl` ka produkciji) |
| Izvor | `tests/test_cron_daily_failclosed_auth.py`, `tests/test_vcr002_t04_podsetnici.py`, `tests/conftest.py` |
| Status tvrdnje | PROVEN (izmereno) |
| Pre | 16 fajlova pod novom zabranom: 160 passed, **12 pokušaja** `CONNECT fake.supabase.co:443` (11 u pozitivnoj kontroli failclosed — 9 modula dispečera radilo stvarno, uklj. email podsetnike; 1 Bearer → `_verify_token` JWKS) |
| Implementacija | `tests/_ns3_mreza_zabrana.py` (Python DNS/connect zabrana + proksi-sink za podprocese); zamene samo u 2 testa |
| Izmenjeni fajlovi | tests/_ns3_mreza_zabrana.py (nov), tests/test_ns3_n01_mreza_kanarinac.py (nov), tests/test_cron_daily_failclosed_auth.py, tests/test_vcr002_t04_podsetnici.py |
| Pozitivan | loopback servis radi (urllib + curl) |
| Negativan | namerni beg iz Pythona (DNS, IP connect, urllib) i pravi `curl` iz podprocesa → zabeleženo, bez izlaska |
| Mutacija | failclosed vraćen → kanarinac pada (11 imenovanih); vcr002 vraćen → pada (1); sink ne beleži → test pravog curl-a pada |
| Bezbednost | produkcioni kod 0 izmena; tvrdnje nepromenjene |
| Nerešeno | harness koji gradi env podprocesa od nule zaobilazi proksi sloj; kanarinac pokriva 16 imenovanih fajlova |
| Commit | `63bb7bfa6766989ce2e16a31bc2577b5b5579aad` |
| Status | **FIXED_VERIFIED** |
| Dalje | DA |

## N02 — CI baseline: uzroci
| Polje | Sadržaj |
|---|---|
| Početni commit | `63bb7bfa` |
| Problem | 174 (3.11/3.13) / 196 jedinstvenih (runtime) CI padova na `469085b6` |
| Izvor | GitHub Actions logovi `469085b6` (read-only), `.github/workflows/tests.yml`, `production-runtime.yml`, `requirements.txt` |
| Status | PROVEN (lokalno) / INFERRED (udaljeni efekat) |
| Matrica (3.11 / runtime) | A async bez plugina 143/143; B git istorija 13+1 / 33 (kontejner bez git-a); bu001 šema 3/3; psycopg 4/3; opcioni AI SDK 2/2; font pod 1/1 (namerno, odluka osnivača); phoenix013 1/1; r7 PG 1; node u kontejneru 0/1 |
| Pre | `-p no:asyncio` nad 15 fajlova: 148 failed/48 passed; depth-1 klon: faza661+wave11 14 failed/3 skipped; bu001 3 failed |
| Implementacija | `requirements-dev.txt` (pytest-asyncio==1.4.0; Dockerfile ga ne koristi); tests.yml/production-runtime.yml: `-r requirements-dev.txt`, `fetch-depth: 0`, git u kontejneru pre checkout-a; wave7 curenje zakrpe (otkriva ga G1); bu001 `izvor` |
| Izmenjeni fajlovi | requirements-dev.txt (nov), .github/workflows/tests.yml, .github/workflows/production-runtime.yml, tests/test_wave7_ab_forensics.py, tests/test_bu001_briefing_schema_contract.py |
| Posle | 196 passed; puna istorija 56 passed; bu001 22 passed; wave7+blackswan 37 passed (3 semena) |
| Mutacija | bu001: nepostojeća kolona → 3 failed; wave7: bez spoljnog patch-a → blackswan pada |
| Nerešeno | udaljeni CI NIJE pokrenut (bez push-a); git u runtime kontejneru lokalno nedokazivo (nema Dockera); mogući ranije maskirani padovi |
| Commit | `d24b1b5a6caa5f16ea2f3bfa6731e235d0e32488` |
| Status | **FIXED_VERIFIED** (lokalno) |
| Dalje | DA |

## N03 — Ugnežđeni neuspeh u dnevnom cron-u
| Polje | Sadržaj |
|---|---|
| Početni commit | `d24b1b5a` |
| Problem | `onboarding` i `nedeljni_sazetak` dobijali `"status": "ok"` i za `greske > 0` / None |
| Izvor | `api.py::cron_daily`; ugovor `routers/email_notif.py::onboarding_cron`, `posalji_nedeljni_sazetak` |
| Status | PROVEN |
| Pre | `tests/test_ns3_n03_cron_ugnezdeni_neuspeh.py` 16 failed / 13 passed |
| Implementacija | `_poslato_greske_status` (dva nenegativna cela broja; greške/nevalidno = greska, +1, ok:false) |
| Izmenjeni fajlovi | api.py, tests/test_ns3_n03_cron_ugnezdeni_neuspeh.py |
| Posle | 29 passed; cron grupa 68 passed |
| Mutacija | zanemarene greške → 4 failed; bez +1 → 9 failed |
| Bezbednost | bez retry-a, bez promene primalaca/tajni/auth; ostali moduli nezavisni (test) |
| Commit | `4beaa97f4421150847bfb7d49295aeb3339115ae` |
| Status | **FIXED_VERIFIED** |
| Dalje | DA |

## N04 — Operativna spremnost email podsetnika
| Polje | Sadržaj |
|---|---|
| Početni commit | `4beaa97f` |
| Problem | put do jednog proverenog beta podsetnika; dupli okidači; ugovori |
| Izvor | `.github/workflows/email-cron.yml`, `routers/email_notif.py`, `static/vindex.js::emailNotifDeaktivaj` |
| Status | PROVEN: GitHub email-cron 2026-10-12..17 sva zakazana pokretanja failure; 2026-10-17 11:48 UTC na `469085b6` **HTTP 403**. UNKNOWN: ko poziva `/api/cron/daily` |
| Defekt | stari UI „Deaktiviraj“ prikazivao uspeh i za 500/429/401/503 |
| Pre | `tests/test_ns3_n04_deaktivacija_email.py` 5 failed / 4 passed (stvarna funkcija u Node-u) |
| Implementacija | provera `r.ok` + ponovno učitavanje stanja; sw.js v155; runbook `docs/release/VINDEX_NS3_N04_EMAIL_PODSETNICI_RUNBOOK.md` |
| Izmenjeni fajlovi | static/vindex.js, static/sw.js, tests/test_ns3_n04_deaktivacija_email.py, runbook (nov) |
| Posle | 9 passed; 81 fajl (vindex.js/sw.js) 1495 passed / 8 failed — isti 8 na `469085b6` |
| Odloženo (dokazano) | provera duplikata po (korisnik, datum, dana_pre) tiho preskače rok drugog predmeta istog dana (`scratchpad/ns3/n04_demo_dup_po_danu.py`: drugo pokretanje 0/0/0/0) — odluka o granularnosti |
| Commit | `b2053a2c56814d9acad6651a3a09bf6578a5753e` (+ ispravka runbook-a u N10) |
| Status | **FIXED_VERIFIED** (deaktivacija) + **DEFECT_PROVEN_DEFERRED** (dup po danu) |
| Dalje | DA |

## N05 — Veza klijent → predmet
| Polje | Sadržaj |
|---|---|
| Početni commit | `b2053a2c` |
| Problem | Smart Intake `klijent_dodat = bool(klijent_ime) and not nesiguran` i kad upis veze/klijenta/razrešavanje padne → V2 „Klijent … je povezan“ |
| Izvor | `routers/smart_intake.py::finalize_intake_job`; `frontend-v2-ng/src/prijem-predmeta.js` |
| Status | PROVEN |
| Pre | 4 failed / 4 passed (stvarni handler) |
| Implementacija | `klijent_povezan` True tek posle upisa `predmet_klijenti` |
| Izmenjeni fajlovi | routers/smart_intake.py, tests/test_ns3_n05_klijent_veza_smart_intake.py |
| Posle | 8 passed; 36 Smart Intake fajlova 559 passed |
| Mutacija | „povezan pre upisa“ → 2 failed |
| Opis-prvo tok | već ispravan (test_ns001_faza1_klijent_predmet 3b/3c/3d; 44 passed) |
| Nerešeno | `POST /api/intake/from-template` guta pad veze — nijedan UI ga ne poziva |
| Commit | `104a8e56fa8f6de9a278407de28e166d11118dc2` |
| Status | **FIXED_VERIFIED** |

## N06 — Prijem slika i PDF-a
| Polje | Sadržaj |
|---|---|
| Početni commit | `104a8e56` |
| Problem | oštećen/lažan PDF → pypdf izuzetak → worker ponavlja do 5 puta (~7,5 min) i završava sirovim engleskim tekstom |
| Izvor | `uploaded_doc/extractor.py::extract_pdf`, `shared/intake_worker.py::_tick` |
| Status | PROVEN (stvarni ekstraktor nad sintetičkim fajlovima) |
| Pre | 8 failed / 2 passed |
| Implementacija | `pypdf.errors.PdfReadError` → `DocumentSafetyLimitExceeded(poruka=PORUKA_NIJE_PDF)` (postojeći terminalni put) |
| Izmenjeni fajlovi | uploaded_doc/extractor.py, tests/test_ns3_n06_pdf_neispravan.py |
| Posle | 10 passed; 54 fajla 839 passed, 22 skipped |
| Mutacija | samo `PdfStreamError` → 2 failed |
| Postojeće (PROVEN) | ekstenzija, JPEG/PNG po sadržaju, prazan, 25 MB, granice piksela, PDF raster, 500 strana |
| Nerešeno | stvarni OCR nije pokrenut (nema tesseract-a) |
| Commit | `69b90002e1e695efe2ce57ddceb0820a39d00e3d` |
| Status | **FIXED_VERIFIED** |

## N07 — Životni ciklus Smart Intake posla
| Polje | Sadržaj |
|---|---|
| Početni commit | `69b90002` |
| Nalaz | prelazi atomski (RPC + SKIP LOCKED), reaper, idempotentnost, 404 za tuđi posao; V2 „Ponovni pokušaj zakazan“ |
| Dokaz | 40 postojećih fajlova: 700 passed, 21 skipped, 0 failed |
| Zapažanje (odluka) | trajno neuspeo posao se ponovnim otpremanjem istog fajla ne obrađuje ponovo (idempotency_key) |
| Commit | nema |
| Status | **NO_CHANGE_NEEDED_PROVEN** |

## N08 — Integritet finalize-a
| Polje | Sadržaj |
|---|---|
| Početni commit | `69b90002` |
| Nalaz | obavezni scenariji pokriveni postojećim testovima; neizvršena grana „original nedostaje“ dobila test |
| Pre/posle | nov test 3 passed (postojeće ponašanje tačno); mutacija „tekst posle pada“ → 2 failed |
| Zamka harness-a | spoljna zakrpa `_download_and_decrypt` pregažena unutrašnjom (n03 harness) → lažan RED; ispravljeno pre zaključka |
| Izmenjeni fajlovi | tests/test_ns3_n08_finalize_original_nedostaje.py |
| Commit | `0cf7779f843350e01d0b55e48a930bf945842a16` (samo test) |
| Status | **NO_CHANGE_NEEDED_PROVEN** |

## N09 — Dokument → Genome
| Polje | Sadržaj |
|---|---|
| Nalaz | finalize → DOCUMENT_ACCEPTED (trajno) → case_evolution genome_refresh (dedup po event_id, verifikacija verzije, „greska“ ne prepisuje, vlasništvo M07) |
| Dokaz | 38 fajlova 469 passed; test_ns006_t13 stvarni lanac, tuđi korisnik ne pokreće obradu |
| Commit | nema |
| Status | **NO_CHANGE_NEEDED_PROVEN** |

## N10 — Granice potvrde rokova
| Polje | Sadržaj |
|---|---|
| Nalaz | `sme_pristupiti`: ACTION/CLIENT/EXPORT traže CONFIRMED za SVAKI red (FAZA 6.4.2); tip ZPP lanca bira advokat; case_actions za nepotvrđen AI rok pravi samo zadatak pregleda; V2 Danas ima potvrdu/odbijanje |
| Dokaz | 23 fajla 1306 passed; HUMAN_DIRECT nepotvrđen → poslato 0, potvrđen → 1 |
| Ispravka | MOJA greška u N04 runbook-u („ljudski rok bez potvrde“) + zastareo komentar u email_notif |
| Commit | `d342c94d6c7597574f9777338edc2fbabf435152` (dokument/komentar) |
| Status | **NO_CHANGE_NEEDED_PROVEN** |

## N11 — Hronologija i poreklo
| Polje | Sadržaj |
|---|---|
| Problem | legacy `/intelligence-timeline` nije razlikovao rok koji čeka odluku / potvrđen / odbijen |
| Pre | 3 failed / 3 passed (stvarni handler) |
| Implementacija | `stanje_odluke` + postojeći `badge` samo za `vrsta='rok'`, lanac strogo, pad = UNKNOWN + `degraded_sources` |
| Izmenjeni fajlovi | routers/intelligence_timeline.py, tests/test_ns3_n11_hronologija_poreklo.py |
| Posle | 6 passed; 104 passed (timeline/provenance/gate) |
| Mutacija | pad čitanja = UNCONFIRMED → 1 failed |
| Nerešeno | pipeline korak 3 piše marker posle upisa rokova (INFERRED prozor za duplikate); boja „kritican“ bez dijakritika nikad ne pogađa |
| Commit | `bcddb89f9e08c3cb17af2a7f644daeefc4eb53c8` |
| Status | **FIXED_VERIFIED** |

## N12 — Pretraga kroz oba toka unosa
| Polje | Sadržaj |
|---|---|
| Nalaz | svih 6 pisaca `predmet_dokumenti` upisuje `user_id` (PROVEN čitanjem); defekt: pretraga ne poštuje tombstone (BETA-DEL-001) |
| Pre | 2 failed / 3 passed — 6 rezultata iz predmeta u brisanju |
| Implementacija | jedan upit `not_.is_(brisanje_zapoceto, null)` + filtriranje; bez kolone 114 prazan skup; drugi pad → fail-closed + `nepotpuno` |
| Izmenjeni fajlovi | routers/search.py, tests/test_ns3_n12_pretraga_tombstone.py, tests/_schema_fake.py, tests/ns005_harness.py, tests/test_tenfronts_m04_search_ogranicenje.py |
| Posle | 5 passed; 51 fajl 943 passed |
| Mutacija | bez filtriranja → 2 failed |
| Commit | `6f0856bee498fef49edc4c98191e10836e0f9ea6` |
| Status | **FIXED_VERIFIED** |

## N13 — Nacrt / izvoz
| Polje | Sadržaj |
|---|---|
| Put | POST /api/podnesak → staging → POST /api/nacrti/export/docx (V2) |
| Problem | prazne vrednosti modela („ostavi prazno“) brisale `[… — POPUNITI]` oznake („Tužilac: ,“) |
| Pre | 36 failed / 14 passed (stvarna `popuni_sablon`, 12 tipova × 3) |
| Implementacija | prazno/None/razmaci = nepoznato |
| Izmenjeni fajlovi | templates/podnesci.py, tests/test_ns3_n13_nacrt_prazna_polja.py |
| Posle | 50 passed; 58 fajlova 988 passed, 1 failed (isti na bazi; lokalni FOUNDER_EMAILS) |
| Commit | `bb0e266a2824593ef34f18ba8e8ea43ecc634884` |
| Status | **FIXED_VERIFIED** |

## N14 — V2 u pravom pregledaču
| Polje | Sadržaj |
|---|---|
| Izvršeno | Playwright/Chromium: live-analiza 43/43 (učitavanje, degradirano, 500, zakasneli odgovor drugog predmeta se ne iscrtava, 0 spoljnih zahteva, 0 JS grešaka), live-matters 64/64, live-rad-predmeta 44/44, live-rocista-pretraga 38/38 = 189/189 |
| Ograničenje | sintetika; nije validacija korisnika; e2e:* i docker nisu pokrenuti |
| Commit | nema |
| Status | **NO_CHANGE_NEEDED_PROVEN** |

## N15 — Nepostojeći red → 500
| Polje | Sadržaj |
|---|---|
| Biblioteka | postgrest 2.28.3 `maybe_single().execute()` → `None` za 0 redova (izvor pročitan) |
| Inventar | 184 čitanja; nezaštićeno van try 68 → 60; `docs/release/VINDEX_NS3_N15_MAYBE_SINGLE_INVENTAR.md` |
| Pre | 10 failed / 2 passed (5 stvarnih handlera) |
| Implementacija | gdpr_export (email + profil), whatsapp get_pretplata, `_proveri_vlasnistvo_predmeta`, `get_case_dna`, `rokovi_lanac` — samo nameravano prazno stanje / 404 |
| Posle | 12 passed; 85 fajlova 2237 passed |
| Mutacija | stara provera vraćena → 2 failed |
| Bezbednost | nijedan red vlasništva nije postao dozvola; 500 → 404 |
| Commit | `a42fd95a51f43645e463e660e771fc8ad1da4a4c` |
| Status | **FIXED_VERIFIED** |

## N16 — M05 arhitektura
| Polje | Sadržaj |
|---|---|
| Isporuka | `docs/architecture/VINDEX_M05_ORPHAN_VECTOR_DECISION.md` |
| Novi nalazi (PROVEN) | Kontraprimer 0 — brisanje jednog od dva dokumenta istog sadržaja u istom predmetu briše vektore i drugog (`scratchpad/ns3/n16_deljeni_identitet_demo.py`: DELETED 3, drugi ostaje 0/3); brisanje predmeta briše vektore po redovima (siročad preživljava); upload ruta ne proverava tombstone |
| Preporuka | Faza 1 C0+C1+C2 (bez migracije/novog identiteta); Faza 2 opciono Opcija A |
| Implementacija | nema |
| Commit | `05b5c22be1efac204523eb404a9aca27ed04fef4` |
| Status | **DEFECT_PROVEN_DEFERRED** |

## Završni gejt — pun lokalni suite (grana naspram baseline-a)
| Polje | Sadržaj |
|---|---|
| Okruženje | Windows, Python 3.13, `-p no:randomly` (zaključan redosled), `FOUNDER_EMAILS` uklonjen, `HTTP(S)_PROXY`/`ALL_PROXY` = mrtav port `127.0.0.1:9` (podproces ne može da izađe), `OPENAI_API_KEY` lažan |
| Grana `night/iron-continuity-ns3` (`05b5c22b`) | 16 failed, 11292 passed, 227 skipped, 2 xfailed (43 min) |
| Baseline `469085b6` | 19 failed, 11153 passed, 227 skipped, 2 xfailed (43 min) |
| Novi padovi na grani | **0** (poređenje po ID-u testa) |
| Popravljeni u odnosu na baseline | 3 — `test_bu001_briefing_schema_contract.py` (N02) |
| Preostalih 16 (isti na oba) | 8 `[trio]` (trio nije instaliran lokalno), 4 `test_faza1_*` (pod veličine fonta), `test_ns003_protocol::test_fixture_hesevi_su_zakljucani`, `test_phoenix_mission_013…timeout`, 2 `test_rc_cold_start` (r5/r7) |
| Napomena | +139 passed na grani = novi NS3 testovi. Plugin `_ns3_mreza_zabrana` je u punom suite-u NIJE učitan (namerno, vidi N01); zaštita je bila mrtav proxy + postojeća brana u `conftest.py`. Udaljeni CI NIJE pokrenut (nema push-a). |

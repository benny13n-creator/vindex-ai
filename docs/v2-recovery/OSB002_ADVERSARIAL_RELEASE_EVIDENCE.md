# OSB002 — adversarijalni dokazi za solo betu

Datum: 2026-10-11. Grana `feature/vindex-osb002-solo-beta-hardening` (radni direktorijum `C:/vindex-osb002`),
napravljena od vrha PR #12 `ad028bde`. Draft PR #13 → `release/v2-rc1`
(https://github.com/benny13n-creator/vindex-ai/pull/13). **Ništa nije spojeno ni deployovano.**

Oznake: **P** = izmereno u ovoj sesiji · **I** = zaključeno iz koda · **A** = pretpostavka · **U** = nepoznato.

## 0. Preflight (P)
| Ref | Očekivano | Izmereno |
|---|---|---|
| `main` | `80c3902b…` | `80c3902be2e06654490972a027a391dbf667dbb4` |
| `release/v2-rc1` | `036854c0…` | `036854c0824b5aaf3d5ae49abf0a2cd8cbbcf54e` |
| PR #12 vrh | `ad028bde…` | `ad028bdef3b3454607a613cb93186aebd93867bb` |
| Produkcija `/health` | `80c3902` | `80c3902` |

Nijedan ref se nije pomerio tokom sprinta; na kraju je ponovo provereno (`git ls-remote`).

## 1. Task 1 — neprekinut solo tok (P, lokalno, simulirani provajderi)
`tests/test_osb002_solo_tok.py`, 10 testova, exit 0. Jedan korisnik i jedan predmet kroz ceo tok:

| Segment | Šta je stvarno | Šta je simulirano |
|---|---|---|
| Prijava | — | Supabase Auth → deterministički token |
| Klijent, predmet, veza | stvarne rute i upis | — |
| Otpremanje i obrada | stvarna ruta Smart Intake, stvaran worker, pypdf ekstrakcija, šifrovano skladište u memoriji | embedding/Pinecone upis |
| Pregled, prikačivanje | stvarne rute | — |
| Dokazi, Genome, akcije | stvaran dispečer događaja i posledice | modeli klasifikacije i Genome-a |
| V2 čitanja | stvarne rute genome-v2, case-actions, workspace, law-brain | — |
| Pravno pitanje, nacrt | stvarne rute, provera vlasništva | model odgovora i nacrta, pretraga korpusa |
| OCR | **nije u ovom toku** (PDF ima tekstualni sloj) | — |

### Nađen i ispravljen kvar (P)
**Dokument otpremljen kroz V2 nikad nije dobijao tvrdnje u dokazima.** Smart Intake je pri upisu stavljao
`klasifikovan_at`, kanonski znak završene klasifikacije dokaza i čuvar idempotencije. Posledica
`evidence_classification` je zato uvek vraćala `skipped_already_classified`. Stari upload nije pogođen.
- Namera je zapisana na tri mesta u kodu (Smart Intake: događaj „MIGRATES“ direktan poziv klasifikacije;
  `routers/evidence.py:193`: znak je kanonski; `services/case_evolution.py:638`: znak je čuvar te funkcije).
- Ispravka: 1 linija u `routers/smart_intake.py` (commit `c148d342`). `tip_dokaza` i tekst se i dalje čuvaju.
- Bez ispravke tok pada (dokazi = `[]`); sa njom prolazi. Ponovljen događaj ne duplira tvrdnje (P).
- 53 povezana test fajla (intake, dokazi, Case Evolution): padovi identični polaznoj grani po identitetu testa,
  11 = 11 (lokalno okruženje: nema `trio`, `OPENAI_API_KEY`) (P).
- Produkcija (read-only brojanje): 49 dokumenata, od toga 3 iz Smart Intake-a; 126 tvrdnji, nijedna sa
  `izvor_tvrdnje` popunjenim. Produkcija ne može ni da potvrdi ni da opovrgne kvar zbog malog uzorka (P).

### Razlike lažne baze ispravljene u testu, ne u proizvodu (P)
- `predmeti.case_dna`: nema definicije u migracijama; produkcija ima 0 od 148 NULL, 125 `{}`. Test sada koristi `{}`.
- `predmeti.observation_version`: migracija 124 `NOT NULL DEFAULT 0`.

### Adversarijalni slučajevi
| Slučaj | Rezultat |
|---|---|
| Isti PDF dva puta | isti posao, `already_submitted`; dupla finalizacija = 1 dokument (P) |
| Dupli predmet u 5 s | 409, jedan red (P) |
| Prekinuta obrada | posao vraćen u red sa backoff-om, ne „završen“; finalizacija odbijena; ponovni pokušaj završava bez duplikata (P) |
| PDF bez teksta | pregled sa razlogom `ocr_failed`, nikad `completed`, finalizacija 409 (P) |
| Oštećen PDF | prihvaćen (202), worker iscrpljuje pokušaje, nikad `completed`, finalizacija 409 (P) |
| Tuđi predmet / tuđi posao | 404, nijedan upis; **BETA-DEF-003**: zauzeće se ne oslobađa 120 s (P, niska ozbiljnost, nije ispravljeno) |
| Ustajao Genome | drugi dokument → verzija 2, nove tvrdnje vidljive (P) |
| Pad Genome modela | verzija se ne upisuje, događaj ostaje za ponovni pokušaj, akcije ne pokazuju na nepostojeće dokumente (P) |
| Tvrdnja modela kao proverena | nijedna tvrdnja modela nije `HUMAN_CONFIRMED`; `SOURCE_FACT` uvek pokazuje na dokument (P) |
| 0 od N dokumenata povezano | API vraća 200 sa brojem; V2 ga prikazuje („Prikačeno je X od Y“) (I, `prijem-predmeta.js:242`) |

## 2. Task 2 — isključena autonomija kao ponovljiv e2e (P)
`npm run e2e:pre136` (`frontend-v2-ng/tests/live-pre136-e2e.mjs`), stvaran `api.py` + stvaran V2 `/app` u Chromium-u.
- Režim `pre136`: **21/21**. Danas, Pregled predmeta i direktna adresa rada `#/pripremljeno/<id>`: stanje
  `NIJE_UKLJUCENO`, nijedna tvrdnja, nijedna akcija, rad 404, 0 upisa/RPC (nema naplate ni upisa radnog proizvoda),
  0 poziva cron-a, samo GET, 0 spoljnih veza (nema poziva modela), 0 JS grešaka.
- Pozitivna kontrola `spremno` (tabela postoji, spreman rad): pada 9 provera, uključujući blok, tvrdnju, Pregled i
  dugmad odluke. Skript pada ako kontrola ne padne.
- **Oboreno ranije uverenje:** u ONS001/solo-beta browser dokazu provera „nema akcije“ bila je slepa. Dugmad glase
  „Prihvatam“/„Odbacujem“, a obrazac `/prihvati|odbaci/` nije pogađao nijedno. Sada se proverava i po id-u elementa.
- Harness promena je opciona (`VX_E2E_AUTONOMIJA`); postojeći e2e nepromenjeni: fastapi 62/62, primary 51/51,
  sw-isolation 28/28 (P).
- Raspoređivač: NS007 motor pokreće samo `POST /api/cron/autonomy` (`routers/autonomy.py:77`), zaštićen tajnom.
  Dnevni registar je `court_portal_watcher`, `precedents_radar`, `hearing_prep`; `precedents_radar.run` ne zove
  `planiraj`/`izvrsi` (samo autonomni ciklus ih zove) (I + P kroz `test_ons001_t1_pre_migracija_136`).

## 3. Task 3 — granica solo / tim (P)
`tests/test_osb002_tim_granica.py`, 5 testova, exit 0. Skup od 58 timskih ruta izvodi se iz `api.app.routes`.

| Grupa ruta | Potrebna dozvola (I) | UI dostupnost | Uticaj na solo | Poznat kvar | Preporuka |
|---|---|---|---|---|---|
| `/api/kancelarija/kreiraj` | prijava | stari UI (`/app-legacy`) | solo može da napravi kancelariju preko API-ja | — | dokumentovati da nije podržano u beti |
| `/api/kancelarija/pozovi`, `uloga`, `suspenduj`, `ukloni`, `reaktiviraj` | admin kancelarije | stari UI | nema (solo nije admin) | BETA-DEF-001 (`saradnik` → 500) | van solo opsega |
| `/api/kancelarija/prihvati`, `odbij` | pozivnica na email iz tokena | stari UI; V2 samo tekst „prihvatate u klasičnom prikazu“ | nema bez pozivnice | — | — |
| `/api/kancelarija/moja`, `mesta`, `istorija`, `naziv`, `napusti` | prijava / član | V2 Kancelarija (samo čitanje) | solo vidi „Niste član nijedne kancelarije“ | — | — |
| `/api/kancelarija/predmeti` | član | stari UI | solo: prazno | spisak nosi metapodatke predmeta kolega (postojeći dizajn) | zadržati |
| `/api/enterprise/predmet/delegiraj`, `delegiranja`, `statistike`, `kapacitet` | vlasnik predmeta + ista kancelarija | nema UI dugmeta | solo dobija 404 | BETA-DEF-002 (nema opoziva) | van solo opsega |
| `/api/firma-memorija/*`, `/api/memory-graph/*` | prijava, ACL memorije (RH001) | stari UI / chat kontekst | solo ne vidi ništa tuđe | — | — |
| `/api/zadaci/*`, `/api/workflow/*`, `/api/learning/firm-dna*`, `/api/firm/health-index`, `/api/saradnja/uloga/*` | prijava (+ vlasništvo) | delom V2 (indeks zdravlja) | bez curenja | — | — |
| `/api/workflow/eskalacije/cron` | tajna cron-a | — | — | — | — |

Izmereno:
- Bez tokena: svih 58 ruta vraća 401/403/422, nijedan upis.
- Solo A nad solo B: nijedna od 58 ruta ne vraća ni bajt B-ovih podataka (oznaka u svakom B-ovom redu); B-ovi redovi
  netaknuti; solo ne može da delegira ni svoj ni tuđ predmet (404).
- Članstvo u kancelariji samo po sebi ne otvara detalj, Genome, dokument, akcije ni Law Brain kolege (403/404).
  Admin vidi SPISAK predmeta člana (samo metapodatke), član ne vidi admina.
- ACL ispravka RH001 je očuvana: `test_rh001_legacy_memory_acl` 18/18 (P).
- Migracija nije potrebna za solo tok (P: ceo Task 1 tok radi na šemi bez 136).
- **Neslaganje opsega, ne ranjivost:** stari UI na `/app-legacy` i dalje nudi pravljenje kancelarije i pozive.
  Odluka o tome je osnivačeva (vidi odluku 2 u `OSB002_FOUNDER_RELEASE_DECISION.md`).

## 4. Task 4 — JWT i skeniranje tajni
### JWT (python-jose CVE-2026-85394 / GHSA-3qf3-8w2g-rqmx)
- Upozorenje (P, GitHub advisory, 2026-10-11): kritično (CVSS 9.3), `python-jose <= 3.5.0`, **ispravljena verzija ne
  postoji**; PyPI najnovija 3.5.0 (P). Mehanizam: DER javni ključ prihvaćen kao HMAC tajna. Preduslovi: napadač ima
  javni ključ **i algoritmi nisu eksplicitno ograničeni**.
- Vindex (I, pročitan svaki poziv): 5 `jose_jwt.decode` poziva u `api.py` i `shared/deps.py`, svaki sa jednim
  dozvoljenim algoritmom. HS256 se proverava isključivo tajnom; javni ključ samo za ES256/RS256.
- Preostala tačka (I): `api.py::_verify_via_live_jwks` uzima `alg` iz JWKS ključa. Bilo bi opasno samo ako bi
  Supabase objavio ključ sa `alg=HS256`. Produkcioni JWKS danas: jedan ključ `EC / ES256 / P-256 / sig` (P).
- Negativni testovi: `test_ns006_t1_jwt_alg_confusion` 15/15 (P); ONS001 sonda 0/78 falsifikata prihvaćeno (P, ranije).
- Izuzetak u `security.yml` je nepromenjen u OSB002 (P: `git diff ad028bde HEAD -- .github requirements.txt` prazan).
- **Odobrenje osnivača: NIJE dato.**

### Gitleaks (P)
| Opseg | Commita | Nalaza |
|---|---|---|
| `main..RC1` (`80c3902b..036854c0`) | 88 | 0 |
| `RC1..OSB002` | 6 | 0 |
| `main..OSB002` | 94 | 0 |
| `main..OSB002` bez allowlist-e i ignore fajla | 94 | 0 |
| cela istorija `main`-a, konfiguracija repoa | — | 1: testna vrednost `SECRET_KEY` u `tests/test_wave10_rate_limiter_isolation.py:35` (od 2026-08-11), lažno pozitivno |
| kontrola osetljivosti (lažni AWS par u privremenom direktorijumu) | — | 2 nađena |

**Zašto je CI `secret-scan` crven (P):** `gitleaks/gitleaks-action@v2` preuzima gitleaks **8.24.3**, a
`.gitleaks.toml` koristi `[[allowlists]]` (sintaksa novijih verzija; lokalno 8.30.1 je primenjuje). Ista istorija
lokalno sa konfiguracijom bez `[[allowlists]]` blokova daje **tačno 876**: 875 × `generic-api-key` u
`data/sudska_praksa/raw/**` (javni tokeni iz preuzetog HTML-a sudova) + 1 testna vrednost. To je i CI broj na obe
grane (1794 commita). Dakle: nije nova tajna, nego verzija alata. Čak i sa novom verzijom ostaje 1 nalaz (testna
vrednost nije u `.gitleaksignore`), pa bi `secret-scan` i dalje bio crven i na `main`-u.
Nijedna tajna nije uneta kroz RC1 ni OSB002. CI konfiguracija NIJE menjana (van ovlašćenja).

## 5. Task 5 — OCR i pravna pouzdanost
- Lanac otpremanje → posao → worker → ekstrakcija → sačuvan tekst → vidljiv u V2: **P za digitalni PDF** (Task 1).
- Skeniran PDF: lokalno nema Tesseract-a ni PyMuPDF-a (testovi preskočeni). U CI-ju `VINDEX_REQUIRE_OCR=1` u
  produkcionom image-u (vidi §6).
- Oštećen, prazan, prekinut, ponovni pokušaj: P (§1). Nijedan ne daje lažno „završeno“.
- Pravni autoritet, 21 fajl: 19 prolazi; 2 imaju padove identične polaznoj grani (lokalno okruženje) (P). Pokriveno:
  izmišljen član se odbija bez modela, bez pouzdanog izvora nema odgovora, pad korpusa nije odsustvo propisa,
  kritika menja izmišljen navod, neproveren ishod nije potvrđen u Law Brain-u, opozvana/tuđa memorija ne ulazi u
  kontekst, trovanje i ispravke.
- **U:** živi OCR u produkciji; tačnost odgovora na stvarnom srpskom korpusu.

- **Rizik (P iz build loga):** produkcioni image instalira `tesseract-ocr`, `-eng`, `-osd`, **bez srpskog paketa**.
  CI OCR korak namerno meri baš to stanje. Kvalitet OCR-a za srpske dijakritike i ćirilicu na stvarnim skenovima je **U**.

## 6. Task 6 — integracija i CI (P)
CI pokrenut ručno (`workflow_dispatch`) na OSB002 `de319714` i na polaznoj PR #12 `ad028bde`; padovi poređeni po
identitetu testa.

| Tok / posao | OSB002 | Polazna | Novi padovi |
|---|---|---|---|
| Test Suite, Python 3.11 | 175 pada, 8511 prošlo | 175 pada, 8495 prošlo | **0** |
| Test Suite, Python 3.13 | 175 pada, 8511 prošlo | 175 pada, 8496 prošlo | **0** |
| Production Runtime: byte-compile, build image + boot | uspeh | uspeh | — |
| Production Runtime: OCR dokaz (stvaran Tesseract, `VINDEX_REQUIRE_OCR=1`) | uspeh | uspeh | — |
| Production Runtime: cela svita na produkcionom Python-u | 197 pada, 7970 prošlo | 197 pada, 7955 prošlo | **0** |
| V2 NG: frontend svite, e2e (8/8, uklj. `e2e:pre136`), Python 3.11 ugovori, Docker | uspeh | uspeh | — |
| Security: sast, semgrep, dependency-scan (pip-audit) | uspeh | uspeh | — |
| Security: secret-scan | pad (876, vidi §4) | pad (876) | — |

Run ID-jevi: Test Suite 38124244851 / 38124246126; Production Runtime 38124250118 / 38124251397;
V2 NG 38124253043 / 38124254354; Security 38124247373 / 38124248752.

Lokalno (Python 3.13, 87 fajlova: OSB002, ONS001, RH, NS005–NS008, V2 NG): 944 prošlo naspram 929 na polaznoj,
3 greške okruženja identične na obe grane, **0 novih**. Lokalnog Dockera nema; build i boot su dokazani u CI-ju.

pip-audit prolazi samo zbog postojećeg JWT izuzetka iz RC1 (nepromenjen; odobrenje osnivača NIJE dato).

## 7. Commitovi i fajlovi
| Commit | Fajlovi |
|---|---|
| `c148d342` fix(intake) | `routers/smart_intake.py` (−2/+6, od toga 1 izmenjena linija koda i komentar), `tests/test_osb002_solo_tok.py` |
| `35baeffe` test(v2-ng) | `tests/v2_ng_e2e_harness.py`, `frontend-v2-ng/tests/live-pre136-e2e.mjs`, `frontend-v2-ng/package.json` |
| `81934a23` test(acl) | `tests/test_osb002_tim_granica.py` |
| `de319714` test(intake) | `tests/test_osb002_solo_tok.py` |
| (ovaj) docs | ovaj fajl, `OSB002_FOUNDER_RELEASE_DECISION.md`, `defects/BETA-DEF-003_finalize_404_zakljucava_posao.md` |

## 8. Kontrolne tačke
| Task | Status | Dokaz | Preostala neizvesnost |
|---|---|---|---|
| 1 solo tok | PASS posle ispravke | 10 testova, mutacija (bez ispravke pada) | modeli i auth simulirani; OCR nije u toku |
| 2 autonomija isključena | PASS | e2e 21/21 + kontrola pala 9, CI `e2e:pre136` PASS | — |
| 3 solo/tim | PASS (neslaganje opsega u starom UI-ju → odluka osnivača) | 5 testova nad 58 ruta | — |
| 4 JWT / tajne | rizik okarakterisan; JWT odobrenje ČEKA osnivača | advisory, 5 decode poziva, JWKS, gitleaks opsezi | ponašanje budućeg JWKS-a |
| 5 OCR / autoritet | PASS za testirane ugovore | §1, §5, CI OCR korak | živi OCR, srpski paket, tačnost na korpusu |
| 6 integracija | PASS: 0 novih padova | §6 | — |

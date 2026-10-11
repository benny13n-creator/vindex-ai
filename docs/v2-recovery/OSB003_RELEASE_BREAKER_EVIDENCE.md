# OSB003 — Release Breaker: dokazi

Datum: 2026-10-11. Grana `feature/vindex-osb003-release-breaker` (radni direktorijum `C:/vindex-osb003`), od vrha
PR #13 `8901a249`. Draft PR #14 (https://github.com/benny13n-creator/vindex-ai/pull/14), **naslonjen na granu PR #13**.
Ništa nije spojeno ni deployovano.

Oznake: **P** izmereno ovde · **I** zaključeno iz koda/tragova · **A** pretpostavka · **U** nepoznato.

## 0. Preflight (P)
| Ref | SHA |
|---|---|
| `main` / produkcija `/health` | `80c3902be2e06654490972a027a391dbf667dbb4` / `80c3902` |
| `release/v2-rc1` | `036854c0824b5aaf3d5ae49abf0a2cd8cbbcf54e` |
| PR #12 | `ad028bdef3b3454607a613cb93186aebd93867bb` |
| PR #13 (polazna) | `8901a249a59836d33bd53b8d42025b3fced72d9e` |

Poreklo (P, `git merge-base --is-ancestor`): `main ⊂ RC1 ⊂ PR #13`, `PR #12 ⊂ PR #13`. PR #13 iznad PR #12 ima tačno 5
commita (OSB002). OSB003 je naslonjen na PR #13; ništa nije replay-ovano.
**Ograničenje:** fajl „VINDEX — CANONICAL OPERATING RULES“ ne postoji u repou (tražen po imenu i sadržaju); pročitan je
`docs/v2/VINDEX_V2_PRODUCT_ARCHITECTURE_DECISION_PAD_001.md` (sistemi zapisa, očuvanje sposobnosti).

## Task 1 — Smart Intake: obaranje ispravke (PASS posle nove ispravke)
**Nađen kvar (P):** `routers/evidence.py::klasifikuj_i_sacuvaj` je upisivao `klasifikovan_at` PRE tvrdnji, a grešku
upisa tvrdnji samo logovao. Jedna prolazna greška baze → posledica `evidence_classification` proglašena završenom →
ponovni pokušaj preskočen (`skipped_already_classified`) → **tvrdnje trajno izgubljene**. Star kvar, oba puta otpremanja.
- Ugovor: `klasifikovan_at` je znak ZAVRŠENE klasifikacije i čuvar idempotencije (`case_evolution.py:638`).
- Ispravka `db5255d2`: tip/elementi/oznake se upisuju kao i ranije; `klasifikovan_at` tek kad tvrdnje uspeju.
- Negativni test pre: pada (`tvrdnje su trajno izgubljene`). Posle: prolazi. Bez ispravke padaju 2 testa (P).
- `c7625b11`: dva postojeća testa su tvrdila „tačno jedan update“; namera zadržana, dodata invarijanta; na starom kodu
  sada padaju (stroži, ne slabiji) (P).
- Preostali prozor (P): ako padne baš upis znaka POSLE tvrdnji, ponovni pokušaj daje drugi red iste tvrdnje sa **istim
  `identitet`** (migracija 116, namerno ne UNIQUE) — vidljiv duplikat, ne gubitak.

Matrica (`tests/test_osb003_intake_lom.py`, `tests/test_osb002_solo_tok.py`, `tests/test_ns005_t14_smart_intake.py`):
| # | Napad | Rezultat |
|---|---|---|
| 1 | digitalni srpski PDF | P: latinica (solo tok) i ćirilica (lokalno, bez OCR-a) tačno izvučene |
| 2 | skenirani PDF | P u produkcionoj slici (Task 2) |
| 3 | više dokumenata u jednom slanju | P: 2 posla, svaki dokument svoje tvrdnje, DOK-01/02, nijedno ukrštanje |
| 4 | dupli upload | P: isti posao, `already_submitted` |
| 5 | ponovljena finalizacija | P: 1 dokument, `already_finalized` |
| 6 | delimično obrađen batch | P: 0 od N povezano → 200 sa brojem, V2 prikazuje (OSB002) |
| 7 | pad ekstrakcije | P: posao u red sa backoff-om, nikad `completed` |
| 8 | prazan dokument | P: pregled `ocr_failed`, finalizacija 409 |
| 9 | oštećen PDF | P: iscrpljuje pokušaje, nikad `completed` |
| 10 | već legitimno klasifikovan | P: ponovni događaj → `skipped_already_classified`, iste tvrdnje |
| 11 | retry posle delimičnog pada | P: tvrdnje nastaju posle oporavka (posle ispravke) |
| 12 | dve istovremene finalizacije | P: drugi dobija 409 dok prvi drži zauzeće, ništa ne upisuje; atomičnost je SQL (`claim_intake_finalize`, I) |
| 13 | tuđi korisnik finalizuje | P: 404, nijedan upis |
| 14 | pogrešan predmet | P: 404; BETA-DEF-003 (120 s zaključavanje) |
| 15 | prekid između klasifikacije i tvrdnji | P: ovo je nađeni kvar; zatvoren |

AI tvrdnje su uvek `izvor_tvrdnje = ai_klasifikacija`, nikad „potvrdio advokat“ (P).

## Task 2 — srpski OCR: pomirenje protivrečnosti (PASS)
**Istina (P, CI build log, run 38124250118 i 38127244939):** image izgrađen iz Dockerfile-a kandidata instalira
`tesseract-ocr-srp` i `tesseract-ocr-srp-latn` (Debian trixie, `1:4.1.0-2`); `tesseract --list-langs` u build-u:
`eng, osd, srp, srp_latn`; Tesseract 5.5.0; izabran jezik `srp+srp_latn+eng`.
**OSB002 tvrdnja „produkcioni image nema srpski paket“ je bila POGREŠNA.** Odnosila se na poseban CI posao
„Import app + full suite“ koji sam instalira `tesseract-ocr` bez srpskog (i tako se i zove: „no Serbian pack“), a ja
sam pročitao samo zavisnosti prve `apt` linije iz Docker build-a.

Merenje unutar produkcione slike (korak „OCR proof inside the production image“, `VINDEX_EXPECT_SRP=1`, 20 prošlo,
0 preskočeno):
| Slučaj | Rezultat |
|---|---|
| Tesseract startuje | P (5.5.0) |
| digitalni PDF latinica (kontrola, bez OCR-a) | P: 100 % reči, OCR nije pozvan |
| digitalni PDF ćirilica (bez OCR-a) | P: 100 % reči |
| skenirani PDF latinica | P: 21/21 reči, dijakritici ć č š ž, pouzdanost 0.95–0.96 |
| **skenirani PDF ćirilica** (novo) | **P: 21/21 reči, 147 ćiriličnih znakova, pouzdanost 0.95** |
| ćirilični sken kroz stvaran intake worker do teksta predmeta (novo) | P: prošao (≥ 80 % reči) |
| prazna/kratka/oštećena slika, oštećen PDF | P: nikad lažan uspeh |
Ako srpski paket nestane iz slike, novi testovi padaju (`VINDEX_EXPECT_SRP=1`).

**Render:** u repou nema Render konfiguracije (`railway.toml` traži Dockerfile; `Procfile` postoji). Produkcija
prijavljuje `pid: 7` i `workers: 1`, što odgovara Docker `CMD` (jedan uvicorn u kontejneru), a ne Procfile-u
(gunicorn, 4 workera) — **I: produkcija radi iz Docker slike**. Potvrda: Render dashboard → Runtime. Živi OCR u
produkciji: **U** (nije meren, zabranjeno bez odobrenja).

## Task 3 — dokument → Genome → akcije (PASS; BETA-DEF-004 zabeležen)
`tests/test_osb003_lanac.py` (5 testova, stvaran dispečer):
- ceo lanac: `evidence_classification`, `genome_refresh`, `timeline_entry`, `refresh_case_actions` završeni; akcija
  `PRIPREMITI_PODNESAK` iz ročišta; genome-v2 tvrdnje pokazuju na postojeće dokumente; workspace vidi predmet (P);
- **nepročitan izvor ne zatvara akcije** (P): za svaki od `rocista`, `predmet_dokazi`, `predmet_dokumenti` usklađivanje
  JESTE pokušano i odbijeno, otvorene akcije nepromenjene; mutacija (nepročitano = prazno) obara test;
- replay svih događaja (isti `event_id`) ne menja tvrdnje, akcije, hronologiju ni verziju Genome-a (P);
- pad Genome modela → isti događaj ostaje za ponovni pokušaj; posle oporavka verzija 1, nijedan nov događaj (P);
- **BETA-DEF-004** (P, karakterizacija, NIJE ispravljeno): pad upisa događaja odmah posle upisa dokumenta → 200,
  dokument postoji, tvrdnje i Genome nikad ne nastaju, ponovna finalizacija ne šalje događaj ponovo. Ispravka menja
  ugovor ili traži RPC/migraciju — granica. Predlog: `docs/v2-recovery/defects/BETA-DEF-004_dogadjaj_posle_dokumenta.md`.

## Task 4 — JWT, kancelarija, stari UI (PASS)
**JWT** — ulazne tačke (I, pročitane): `api.py::_verify_token` (HS256 tajnom; ES256 hardkod ključ; `_verify_via_live_jwks`),
`shared/deps.py::verify_token_local` i `_verify_token`. Svaki `decode` ima tačno jedan algoritam.
- `tests/test_osb003_jwt.py`: 4 varijante JWKS-a (produkcijski ES256 sa `alg`, bez `alg`, `alg=HS256` van invarijanti,
  EC+RSA) × 13 falsifikata (HS256 sa PEM/DER/JWK/xy, ES256/RS256 zaglavlje, `none`) × 5 verifikatora:
  **0 prihvaćenih** (P).
- **Nađen kvar (P):** sa JWKS ključem bez `alg`, `verify_token_local` je propuštao `JWKError` → 500 umesto 401 na rutama
  preko `shared.deps`. Fail-closed, ali krši ugovor „None pri neuspehu“ i, ako SDK ne radi, isto bi pogodilo i prave
  tokene. Ispravka `0709728d`: hvata se `JOSEError`. Pre: 2 slučaja 500; posle: svi 401/403.
- Produkcioni JWKS (P, javni endpoint): jedan ključ `EC / ES256 / P-256 / sig`.
- Klasifikacija: **MITIGATED / NOT REACHABLE UNDER TESTED INVARIANTS**, ne „nemoguće“.

**Kancelarija i stari UI** (P): `test_rh001_legacy_memory_acl`, `test_ns008_t21_revocation`, `test_ns008_t19_acl_matrix`,
`test_ns006_t15_tenant_matrix`, `test_ns007_t19_tenant_matrix`, `test_osb002_tim_granica`, `test_knowledge_graph`:
58 prošlo — kolegine beleške/veze nedostupne i nepromenljive, upis u graf za tuđi predmet odbijen, opoziv delegacije
odmah zatvara pristup, 58 timskih ruta bez curenja. Stari UI (`/app-legacy`) i dalje nudi kancelariju/pozive
(OSB002, odluka osnivača 2) — nije uklanjano.

## Task 5 — gitleaks (PASS)
- Dokazano (P): `gitleaks-action@v2` preuzima **8.24.3**; 8.24.3 + `.gitleaks.toml` nad istorijom = **876** (875 javni
  tokeni u `data/sudska_praksa/raw` + 1 testna vrednost) — tačno CI broj; 8.30.1 = 1. Uzrok: 8.24.3 ne čita `[[allowlists]]`.
- Ispravka `b8ac7935`: `GITLEAKS_VERSION: "8.30.1"` (fiksno, ne „latest“) + jedan tačan otisak za
  `tests/test_wave10_rate_limiter_isolation.py:35` (vrednost pročitana iz blob-a `e2dadc55`: ista testna vrednost kao već
  prihvaćeni fixture-i). Nijedno pravilo ni putanja nisu proširene.
- Posle (P, lokalno 8.30.1, isti `detect` kao akcija): 1867 commita, **0 nalaza**.
- Pozitivna kontrola (P, odbačen klon): nova lažna AWS tajna u `tests/` otkrivena, exit 1 (i na 8.24.3 i na 8.30.1).
- **Preostali rizik (P):** tajna upisana u `data/sudska_praksa/raw/**` NE bi bila otkrivena — postojeća allowlist
  putanje za javni HTML sudova. Nije menjano; ako se želi, uži obrazac (samo `theme_token`) je zaseban posao.

## Task 6 — pravna pouzdanost (PASS posle ispravke)
| # | Slučaj | Dokaz |
|---|---|---|
| 1 | nepostojeći citat | P: `test_ns005_t6` izmišljen član odbijen bez modela; čuvar blokira |
| 2 | stvaran izvor, pogrešan član | **P: kvar nađen i ispravljen** (ispod) |
| 3 | zastareo propis | P: `test_ns008_t17_validity` (zastareo nikad kao važeći) |
| 4 | odluka sa pogrešnim brojem | P: `test_ns007_t9_t10` (izmišljen izvod/drugi izvori odbačeni; nedostupno ≠ nepostojeće) |
| 5 | AI tvrdnja kao „potvrdio advokat“ | P: OSB002/OSB003 tok; `test_faza64_provenance_contract` |
| 6 | grafička napomena kao ishod | P: `test_ns008_t2_outcomes` (legacy „uspešno“ nije ishod) |
| 7 | zatvoren predmet bez ishoda | P: `test_ns008_t2` (zatvoren bez ishoda = nepoznat) |
| 8 | opozvana memorija u kontekstu | P: `test_ns008_t21_revocation`, `test_rh001_legacy_memory_acl` |
| 9 | nedostajući dokaz kao činjenica | P: `test_ns006_t14` (`BEZ_POTPORE`), `test_b4_source_authority` (pad ≠ prazno) |
| 10 | prazna pretraga | P: `test_ns005_t6` (nema pouzdanog izvora → nema odgovora, model se ne zove) |
Mapirani testovi: 207 prošlo (P).

**Nađen kvar (P):** `main.py::_proveri_halucinaciju` (ugovor: SVAKI citiran član mora biti u kontekstu; koristi ga
strukturni čuvar na putu odgovora, `main.py:3205`) tražio je samo „Član N“. **„U članu 9999“, „Članom 201“,
„člana N“ i „čl. N“ prolazili su neprovereni.** Ispravka `1c188ea3`: isti obrazac proširen na padeže i „čl.“, i na
kontekst (padež u tekstu zakona više ne daje lažan blok). 12 testova; stari kod pada na 7. Regresija 10 fajlova
čuvara/pitanja (167 testova): 0 novih padova.
**Ograničenje (P, testom zabeleženo):** isti broj člana iz drugog zakona prolazi — čuvar ne poredi naziv zakona.

## Task 7 — V2 u pravom pregledaču (PASS posle ispravke)
`npm run e2e:solo-tok` (`frontend-v2-ng/tests/live-solo-tok-e2e.mjs` + `tests/osb003_solo_server.py`): pravi uvicorn sa
pravim `api.app`, primarni V2 `/app` u Chromium-u, baza u memoriji koja STVARNO upisuje (bez migracije 136, kao
produkcija). **23/23 (P).** Svaki korak proveren u UI-ju i u bazi:
Danas → nov predmet → klijent i veza (COI „nije pronađen sukob“) → otpremanje PDF-a → obrada → pregled → prikačivanje →
tvrdnje i Genome v1 → Dokumenti → Pregled/Analiza (tvrdnja 17.03.2025) → Rad na predmetu → pitanje (izvor Član 185) →
nacrt („pre podnošenja ga mora pregledati advokat“) → 500 na akcijama (bez lažnog „nema akcija“) → Danas → 1024×768.
0 spoljnih zahteva, 0 upisa u autonomy, 0 JS grešaka, 0 neočekivanih 5xx; simulirani modeli: pitanje, nacrt.

**Nađen kvar (P):** nov korisnik bez predmeta video je na Danas blok „Vindex je pripremio — Rad koji je Vindex sam
pripremio…“ iako je autonomija isključena. Uzrok: bez predmeta `_fetch_prepared_work` nije pitao bazu, pa je stanje
bilo `OK` umesto `NIJE_UKLJUCENO`. Ispravka `9994b976`: jeftina provera postojanja tabele (1 red, samo svoj); rezultat
ostaje `[]`. 4 pytest testa (2 padaju bez ispravke); bez ispravke browser test pada tačno na koraku Danas. 65 workspace
testova identično polaznoj grani.
Postojeći `e2e:pre136` nije uhvatio ovo jer njegov korisnik ima 12 predmeta.

## §8. Task 8 — integracija i CI (P)
CI ručno pokrenut na OSB003 (`74d2f04f`; V2 NG ponovljen na `b8bda9da`) i na polaznoj PR #13 (`8901a249`); padovi
poređeni po identitetu testa.

| Tok / posao | OSB003 | Polazna PR #13 | Novi padovi |
|---|---|---|---|
| Test Suite, Python 3.11 | 175 pada, 8544 prošlo | 175 pada, 8510 prošlo | **0** |
| Test Suite, Python 3.13 | 175 pada, 8544 prošlo | 175 pada, 8510 prošlo | **0** |
| Production Runtime: byte-compile, build image + boot, OCR u slici (srp/srp_latn, ćirilica 21/21) | uspeh | uspeh | — |
| Production Runtime: cela svita na produkcionom Python-u | 197 pada, 8008 prošlo | 197 pada, 7970 prošlo | **0** (12 × `test_p0d2_*` = nedostaje async plugin, isto na obe grane) |
| V2 NG: frontend svite, Python 3.11 ugovori, Docker | uspeh | uspeh | — |
| V2 NG: e2e (9/9, uklj. `e2e:pre136` i novi `e2e:solo-tok` 23/23) | uspeh (run 38130102533) | uspeh (8/8) | — |
| Security: sast, semgrep, pip-audit | uspeh | uspeh | — |
| **Security: secret-scan** | **uspeh — gitleaks 8.30.1, 1804 commita, 0 nalaza** | pad — 8.24.3, 876 | — |

Run ID-jevi: Test Suite 38129106178 / 38129107807; Production Runtime 38129111858 / 38129113246;
V2 NG 38130102533 (i 38129114570) / 38129115851; Security 38129109266 / 38129110589.
Broj padova (175 / 197) je isti kao na `main`-u u ranijim merenjima (OSB002), i ovde identičan po identitetu sa PR #13.

Lokalno (Python 3.13, 151 fajl: OSB002/OSB003, ONS001, RH, NS005–NS008, V2 NG, intake/dokazi/Case Evolution, čuvari,
workspace): **1681 prošlo naspram 1647, 18 = 18 padova okruženja, identični po identitetu, 0 novih.**
Lokalnog Dockera nema; build, boot i OCR u slici su dokazani u CI-ju.
pip-audit prolazi zbog postojećeg JWT izuzetka iz RC1 (nepromenjen; odobrenje osnivača NIJE dato).

## Commitovi (iznad `8901a249`)
| Commit | Vrsta | Fajlovi |
|---|---|---|
| `db5255d2` | ispravka | `routers/evidence.py`, `tests/test_osb003_intake_lom.py` |
| `41501c2c` | test | `tests/test_ns005_b_ocr.py`, `tests/test_ns005_t14_smart_intake.py` |
| `681dc5ad` | test + defekt | `tests/test_osb003_lanac.py`, `docs/v2-recovery/defects/BETA-DEF-004_*.md` |
| `0709728d` | ispravka | `shared/deps.py`, `tests/test_osb003_jwt.py` |
| `c7625b11` | test | `tests/test_evidence_klasifikacija.py`, `tests/test_sigma_sprint002_timestamp_literal_bugs.py` |
| `b8ac7935` | CI | `.github/workflows/security.yml`, `.gitleaksignore` |
| `1c188ea3` | ispravka | `main.py`, `tests/test_osb003_pravni_autoritet.py` |
| `9994b976` | ispravka | `routers/workspace.py`, `tests/test_osb003_danas_bez_predmeta.py` |
| `74d2f04f` | test | `tests/osb003_solo_server.py`, `frontend-v2-ng/tests/live-solo-tok-e2e.mjs`, `frontend-v2-ng/package.json`, `tests/test_osb002_solo_tok.py` |
| `b8bda9da` | test | `tests/osb003_solo_server.py` |
| (ovaj) | docs | ovaj fajl, `OSB003_FOUNDER_MORNING_BRIEF.md` |

## Kontrolne tačke
| Task | Status | Preostala neizvesnost |
|---|---|---|
| 1 Smart Intake | PASS posle ispravke `db5255d2` | prozor znaka posle tvrdnji = vidljiv duplikat istog identiteta |
| 2 srpski OCR | PASS (P u slici, ćirilica i latinica) | Render runtime I; živi OCR U |
| 3 lanac | PASS; BETA-DEF-004 zabeležen | pad upisa događaja posle dokumenta |
| 4 JWT/kancelarija | PASS posle ispravke `0709728d`; JWT odobrenje ČEKA osnivača | budući oblik JWKS-a |
| 5 gitleaks | PASS (`b8ac7935`) | tajna u `data/sudska_praksa/raw/**` se ne bi otkrila |
| 6 pravna pouzdanost | PASS posle ispravke `1c188ea3` | čuvar ne poredi naziv zakona |
| 7 V2 u pregledaču | PASS posle ispravke `9994b976` | modeli simulirani; produkcija nemerena |
| 8 integracija | PASS: 0 novih padova (CI i lokalno) | — |

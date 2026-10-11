# ONS001: RC1 beta release closure, dokazi

## Kontrolna tačka (konačna)
- **Grana:** `feature/vindex-rc1-ons001-closure`
  - početak: `release/v2-rc1` `036854c0824b5aaf3d5ae49abf0a2cd8cbbcf54e`
  - kod: `ae1897a1588ac99bb7063f6c6838392df0067521`
- **Draft PR:** https://github.com/benny13n-creator/vindex-ai/pull/12 (→ `release/v2-rc1`, Draft, bez merge-a)
- **Završeno:** T1 PASS · T2 NOT REACHABLE · T3 BLOCKED · T4 BLOCKED · T5 NOT APPLICABLE · T6 PASS
- **Blokeri:** T3 i T4 traže odluke osnivača (`ONS001_FOUNDER_DECISION_BRIEF.md`)
- **Sledeće:** nema dodatnog ovlašćenog zadatka. STOP.

## Preflight
- **Produkcija:** `/health` → `80c3902`. `origin/main` = `80c3902be2e06654490972a027a391dbf667dbb4` (provereno na početku i na kraju).
- **RC1:** `origin/release/v2-rc1` = `036854c0…`, bez novih commitova od izveštaja.
- **Dokument „CANONICAL OPERATING RULES“:** nije pronađen u repou. Primenjeni su direktiva, PAD-001 i RH001/RH002/RC1 dokazi.

## T1: RC1 bez migracije 136 i bez Cron-a: **PASS**
**Stanje produkcije** (PROVEN, read-only):
- `predmet_dokazi.izvor_tvrdnje` (mig. 135) postoji;
- `autonomy_cycles` i `autonomy_work_items` ne postoje (PGRST205).

**Putanje zavisne od 136:**

| Putanja | Fajl |
|---|---|
| ruta cron-a | `routers/autonomy.py` (`/api/cron/autonomy`) |
| pregled rada | `routers/autonomy.py` (`/api/autonomy/work-items*`) |
| korpa „Danas“ | `routers/workspace.py` |
| ciklus | `workers/background_agents.py::run_autonomy_cycle` |
| planeri i izvršioci | `services/agent_tasks/hearing_prep.py`, `services/agent_tasks/precedents_radar.py` (`planiraj`/`izvrsi`) |
| servis | `services/autonomy.py` |
| Law Brain promocija | `services/law_brain_promocija.py` |

Postojeći dnevni cron (`api.py:2293` → `run_background_agents`) pokreće samo `court_portal_watcher` i `precedents_radar.run`, kao i ranije. `hearing_prep` nema `run`.

**Metoda 1, diferencijalna simulacija:** pytest plugin van repoa (`pre136_plugin.py`) postavlja PGRST205 za obe tabele i PGRST202 za RPC u svakoj lažnoj bazi harness-a. Pokrenuta su sva 60 harness fajla (ns005–ns008, rh001), sa `timeout 900`, a ishod je čitan iz JUnit XML-a.

| Pokretanje | Exit | Rezultat |
|---|---|---|
| bez simulacije | 0 | 512 passed, 20 skipped |
| sa simulacijom | 1 | 393 passed, 119 failed, 20 skipped |

Trijaža svih 119: svi seju ili izvršavaju autonomni rad u pripremi testa, tj. ugovor **posle** migracije (t3, t5, t6–t10, t12, t13, t17–t19, t22, ns008_t15). Posebno su provereni:
- `t13`: pada u `_gotov`, koji direktno zove ciklus, ne u ruti `/api/agent-notifications`;
- `ns008_t3`: pada u direktnom pozivu planera; PATCH završnog statusa prolazi.

Preko HTTP-a su dostižna samo **4 stvarna nalaza**:

| Ruta pre 136 | Bilo | Uzrok |
|---|---|---|
| `GET /api/autonomy/work-items/{id}` | 500 | PGRST205 nije uhvaćen |
| `POST …/{id}/accept`, `…/{id}/reject` | 500 | isto |
| `POST /api/law-brain/rad/{id}/predlozi-znanje` | 503 | isto |

UI pre migracije nema nijednu stavku, pa se do ovih ruta dolazi samo ručno sastavljenim zahtevom. Korupcije podataka nema.

**Ispravka** `ae1897a1` (`routers/autonomy.py`, `services/law_brain_promocija.py`): nepostojeća tabela daje isti 404 kao nepostojeći rad. To je postojeći ugovor `NIJE_UKLJUCENO` liste i workspace-a. Svaka druga greška baze ostaje vidljiva.

**Metoda 2, namenski test** `tests/test_ons001_t1_pre_migracija_136.py` (15 testova):
- 15 V2 ruta (workspace/Danas, predmeti, predmet, hronologija, genome-v2, dokazi/dokumenti, Case Actions ×2, matter-intel, ročišta, Law Brain kontekst/znanje/pretraga, agent-notifications, lista rada) vraćaju **isti** status i telo sa i bez 136. Izuzetak je polje stanja (`OK` ↔ `NIJE_UKLJUCENO`). Kontrola: sve su 200 i posle migracije, a telo sadrži stvaran predmet i dokument.
- PATCH u završni status upisuje status i `MatterBecameTerminal` bez 136.
- Cron bez ispravne tajne, u 5 oblika (nema tajne, nema zaglavlja, kratka, pogrešna…): isti 401, **0** pristupa bazi.
- Cron sa tajnom a bez šeme: 503 `CLAIM_UNAVAILABLE`, **0** poziva planera/izvršilaca/`run`, **0** upisa u `usage_events`, `audit_immutable` i `autonomy_work_items`.
- Registar dnevnog crona: tačno `{court_portal_watcher, precedents_radar}`.
- Radni proizvod pre 136 → isti 404 kao nepostojeći (4 rute).
- Druga greška baze nije prikrivena kao 404 (500 / 503 ostaju).

Rezultati:
- sa ispravkom: exit 0, **15 passed**;
- bez ispravke (mutacija `git stash`): **4 failed**, 11 passed.

**UI:** `frontend-v2-ng/src/pripremljeno.js:78` pri `NIJE_UKLJUCENO` skriva blok „Vindex je pripremio“ i ništa ne tvrdi. Utvrđeno čitanjem koda; browser test baš za to stanje ne postoji.

**Regresija:** harness fajlovi i ACL/delegacija/chat/RH001 skupovi, `--randomly-seed=12345`: exit 0, **744 passed, 20 skipped**. Prvo pokretanje je imalo 1 pad, `test_ns006_t8_case_actions::test_rociste_akcija_i_pomeranje_azurira_istu` („za 5 dan“ vs „za 4 dan“): pokretanje je prešlo ponoć, a `DANAS` se računa pri uvozu. Isti test prolazi i na RC1 i na sprint grani kad se ponovi. Postojeća nestabilnost, nije regresija.

## T2: python-jose CVE-2026-85394: **NOT REACHABLE** (mitigirano ograničenjem algoritma i tipa ključa)
- **Verzije:** `python-jose[cryptography]==3.5.0` (pin i instalirano), `ecdsa 0.19.2`, `cryptography 46.0.5`. PyPI najnovija = **3.5.0**: zakrpljena verzija **ne postoji**.
- **Savetnik** (OSV `GHSA-3qf3-8w2g-rqmx`, alias CVE-2024-33663 / CVE-2026-85394; CRITICAL; CWE-347; pogođeno ≤3.5.0): HMAC inicijalizacija prihvata DER javni ključ. Napadač koji zna javni ključ falsifikuje **HS256** token koji prolazi **kada verifikator prosledi javni ključ, a algoritmi nisu ograničeni**. Nepotpuna popravka CVE-2024-33663.
- **Vindex verifikatori:** `api.py::_verify_token` i `_verify_via_live_jwks`, `shared/deps.py::verify_token_local` i `_verify_token`.
  - HS256 se dekodira **samo** sa `SUPABASE_JWT_SECRET` i `algorithms=["HS256"]`.
  - Javni ključ ide **samo** u granu `alg in ("RS256","ES256")`, kao konstruisan `ECKey` objekat (ne bajtovi), sa `algorithms=[alg]` ograničenim na tu jednu vrednost.
  - Živi JWKS koristi `algorithms=[jwk.alg ili alg iz zaglavlja]`, a zaglavlje je već ograničeno na RS256/ES256.
- **Produkcioni JWKS** (javni endpoint): 1 ključ `EC/ES256/P-256`, `alg` prisutan.
- **Napad** (sintetički tokeni, javni ključ, bez produkcionih JWT-ova): 13 falsifikata (HS256/ES256-zaglavlje/RS256-zaglavlje × PEM/DER/JWK/x‖y, plus `alg=none`) × 3 verifikatora × {JWKS sa `alg`, bez `alg`} × {HS256 tajna postavljena, nije}:

| Skup | Exit | Rezultat |
|---|---|---|
| postojeći `test_ns006_t1_jwt_alg_confusion.py` | 0 | 15 passed (uklj. kontrolu osetljivosti: ranjiva konfiguracija bi prihvatila) |
| sonda: tajna postavljena i nepostavljena | — | 26/26 odbijeno |
| sonda: brojanje prihvatanja (78 pokušaja) | 0 | **0 prihvaćenih** |

- **Uzgredno (nije ranjivost):** kad JWKS ključ **nema** `alg`, `deps.verify_token_local` baca `JWKError` (hvata samo `JWTError`). Rezultat je i dalje odbijanje, ne prihvatanje. Produkcioni JWKS ima `alg`, pa nije reprodukovano; nije ispravljano.
- **Preporuka:** izuzetak u `security.yml` (uveden u NS006, deo RC1) **zahteva izričito odobrenje osnivača**. Ova direktiva zabranjuje uvođenje izuzetaka bez odobrenja, a ONS001 ga nije ni proširivao ni menjao.

## T3: BETA-DEF-001 `saradnik`: **BLOCKED**
- **Kod:** `routers/kancelarija.py` `ULOGE=("admin","partner","saradnik","citanje")`, `PozovReq.uloga` default `"saradnik"`.
- **Repo migracija 018:** CHECK dozvoljava `saradnik`. Produkcija ga odbija (PROVEN, RH002 FINAL); tačna definicija ograničenja: UNKNOWN (nema read-only DB pristupa).
- **Semantika:** `routers/workflow.py:68` i `routers/zadaci.py:118` tretiraju `("admin","partner")` kao `is_admin`; `saradnik` je član **bez** administratorskih prava. `shared/rbac.zahtevaj_dozvolu` aplikacija nigde ne poziva. Mapiranje `saradnik`→`partner` bilo bi eskalacija privilegija; `saradnik`→`citanje` menja značenje.
- **Produkcija:** `kancelarija_clanovi` ima **0 redova** (read-only zbir), pa nema postojećih podataka.
- **Zaključak:** popravka traži migraciju ograničenja ili odluku o skupu uloga. Oba su zabranjena ili čekaju odluku osnivača. Kod nije menjan.

## T4: BETA-DEF-002 opoziv delegacije: **BLOCKED**
- **Postoji:** `POST /api/enterprise/predmet/delegiraj` (samo vlasnik predmeta, cilj mora biti član iste kancelarije) i `GET …/delegiranja`. **Nema** rute za opoziv, a **nema UI-ja** ni za davanje ni za opoziv (V2 NG i legacy `static/vindex.js`).
- **Šema u repou (mig. 054):** `status IN ('aktivno','zavrseno','otkazano')`. RH002 FINAL je u produkciji upisao `opozvano`, i to je prihvaćeno (INFERRED iz testa G4), što ukazuje na odstupanje šeme. ACL gleda samo `status='aktivno'`.
- **Nije definisano:** ko sme da opozove (davalac? vlasnik? admin? delegat sam?), koja je završna vrednost statusa, audit zapis i mesto u UI-ju.
- **Produkcija:** `predmet_delegiranja` ima **0 redova**. Bez članova kancelarije delegacija se ne može ni napraviti, pa danas nema izloženosti.
- **Zaključak:** samo API ruta ne ispunjava uslov „ceo podržan tok“. Kod nije menjan.

## T5: dodatne beta regresije: **NOT APPLICABLE**
Van T1 nema reprodukovanog release-kritičnog kvara. Napomene van opsega, ništa menjano:
- `JWKError` (T2), nereprodukovan u produkciji;
- `/api/predmeti/{id}/workspace` u harness-u vraća 500 zbog nedostajućeg `feature_registry` reda u lažnoj bazi; ruta nije iz RC1;
- `/api/law-brain/pretraga` bez zamene embedding-a pogađa testni čuvar mreže `NetworkAccessBlocked`.

## T6: integracija: **PASS**
- **Diff** `036854c0..ae1897a1`: 3 fajla, +173/−5 (`routers/autonomy.py`, `services/law_brain_promocija.py`, `tests/test_ons001_t1_pre_migracija_136.py`) plus ovi dokumenti. Bez zavisnosti, migracija i izuzetaka.
- **CI** (GitHub Actions, `workflow_dispatch` na sprint grani) vs `main` `80c3902b`, poređenje po tačnom ID-ju testa:

| Posao | main | ONS001 | Novi padovi |
|---|---|---|---|
| pytest 3.11 (run 38090005675) | 175 failed / 7877 passed | 175 failed / 8495 passed | **0** |
| pytest 3.13 | 175 / 7877 | 175 / 8495 | **0** |
| Produkcioni Python 3.11, ceo skup (38090007216) | 197 / 7337 | 197 / 7955 | **0** |
| Docker build i boot-check | 17 passed | 17 passed | 0 |
| Byte-compile 3.11 | success | success | — |
| V2 NG, 4 posla (38090010235) | — | success | — |
| V2 NG na RC1, osnovica (38090034266) | — | success | — |
| sast/semgrep core i full | success | success | — |
| dependency-scan (pip-audit) | **failure** (CVE bez izuzetka) | success (izuzetak iz RC1) | — |
| secret-scan (gitleaks) | success (push, samo novi commitovi) | **failure** | vidi ispod |

- **Gitleaks:** ručno pokretanje skenira **celu istoriju** (1.788 commitova). Svih 876 nalaza su u commitovima `113332e6`, `92cd20f1`, `e2dadc55`, koji su **u istoriji `main`-a** (PROVEN, `merge-base --is-ancestor`):
  - 875 su `theme_token` u preuzetim HTML stranicama sudske prakse (`data/sudska_praksa/raw/**`);
  - 1 je testna `SECRET_KEY` zamena.
  - U sprint diff-u: 0 nalaza (pretraga obrazaca).
  - Nije regresija. Ishod gitleaks-a za budući PR RC1→main: UNKNOWN dok se ne pokrene.
- **Bazna lista od 175/197 padova:** postojeća CI osnovica, ista na produkciji. Sprint je ne menja i ne potiskuje.

## Šta je gde dokazano
- **Lokalno:** T1 (simulacija, namenski test, mutacija, regresija), T2 (napad).
- **CI:** T6 tabela.
- **Produkcija:** samo read-only stanja (SHA, šema 135/136, JWKS, 0 članova, 0 delegacija).
- Nijedan lokalni rezultat nije dokaz produkcionog deploy-a. Deploy nije rađen.

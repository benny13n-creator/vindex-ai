# JWT-RISK-001 — ciljana procena CVE-2026-85394 (python-jose)

- **Kandidat:** `release/v2-solo-final-candidate` `c09d87dbbba02daf62738115ac144f15aba88dfc`.
- **Produkcija:** `80c3902be2e06654490972a027a391dbf667dbb4`.
- **Grana procene:** `security/jwt-risk-001`, sa kandidatom kao osnovom.

Oznake: **P** dokazano · **I** zaključeno · **A** pretpostavljeno · **U** nepoznato.

## 1. Ranjivost (zvanični izvori, P)
| Polje | Vrednost |
|---|---|
| ID | CVE-2026-85394 · GHSA-3qf3-8w2g-rqmx |
| Paket / verzije | `python-jose` ≤ 3.5.0 (Vindex: 3.5.0, `requirements.txt`) |
| Zakrpa | **nema**. PyPI najnovije izdanje je 3.5.0 (2025-05-28), proverio sam 2026-10-11 |
| Suština | nepotpuna ispravka CVE-2024-33663: DER javni ključ bez PEM omotača ili SSH prefiksa prihvata se kao HMAC tajna (`jose/backends/native.py`, `jose/utils.py`) |
| Preduslovi | napadač ima javni ključ servisa **i** verifikacija ne ograničava algoritme |
| CVSS v4 | 9.3 (EPSS 0.222%) |
| Mitigacija iz advisory-ja | eksplicitno ograničenje algoritama pri verifikaciji |

**Reprodukcija ranjivog ponašanja (P):** `decode(tok, JAVNI_DER, algorithms=["HS256"])` na instaliranoj 3.5.0 **prihvata** falsifikat za produkcioni EC, sintetički EC i sintetički RSA ključ. PEM oblik biblioteka odbija. Vindex ovakav poziv nema (§3).

## 2. Inventar dostižnih verifikatora (P, kod kandidata)
| # | Fajl / funkcija | Pozivaoci | Izvor tokena | Algoritmi i ključ | iss / aud / exp | kid | Greška i rezerva | Daje pristup |
|---|---|---|---|---|---|---|---|---|
| V1 | `api.py::_verify_token` | `api.get_current_user` (19 ruta u `api.py`), `_require_auth(_async)` | `Authorization: Bearer` | (1) SDK `supa.auth.get_user` (server Supabase Auth); (2a) `alg` iz zaglavlja == HS256 → samo `SUPABASE_JWT_SECRET`, `algorithms=["HS256"]`; (2b) `alg ∈ {RS256, ES256}` → ugrađeni produkcioni EC/ES256 JWK, `algorithms=[alg]` | iss ne; aud isključen; **exp da** (podrazumevano); `sub` obavezan | ignoriše se | 2b greška → **V1b** | da |
| V1b | `api.py::_verify_via_live_jwks` | samo V1 (2b) | isti | živi JWKS (`SUPABASE_URL`, keš 1 h); svaki ključ: `algorithms=[jwk.alg ili alg iz zaglavlja]`; ulaz je samo za RS256/ES256 zaglavlje | kao V1 | ignoriše se (proba sve ključeve) | greška dohvatanja → None; greška ključa → sledeći | da |
| V2 | `shared/deps.py::_verify_token` | `shared.deps.get_current_user` (~100 routera, `permissions.require`); **WebSocket** `routers/voice_realtime.py` (token u `?token=`) | Bearer / query | (1) SDK; (2) V3 | kao V3 | — | SDK greška → V3 | da |
| V3 | `shared/deps.py::verify_token_local` | V2; `api.user_rate_limit_middleware` (**samo grupisanje za rate limit**, nije autorizacija) | Bearer | HS256 → samo tajna, `["HS256"]`; RS256/ES256 → `_get_jwks_key(alg)` (JWKS keš 1 h; greška → ugrađeni EC ključ), `algorithms=[alg]` | iss ne; aud isključen; exp da; `sub` obavezan | ignoriše se | `JOSEError` → None (OSB003) | V2: da; middleware: ne |

- Ostalo (P, grep): drugih `jwt.decode`, `get_unverified_*` ili `auth.get_user` poziva u kodu aplikacije nema. `scripts/` i `tests/` nisu dostižni u produkciji. Pozadinski poslovi i interne rute ne primaju korisnički JWT (cron koristi zasebnu tajnu).
- Između produkcije (`main`) i kandidata verifikatori se razlikuju samo u OSB003 izmeni (`JWTError` → `JOSEError`, 500 → 401).

## 3. Invarijante (Task C)
**Invarijanta 1 — HS256 se verifikuje samo simetričnom tajnom: VAŽI (P).** U V1 i V3 grana HS256 prosleđuje isključivo `SUPABASE_JWT_SECRET`. Nijedan javni ključ ne stiže do HMAC grane. Svi HS256 falsifikati potpisani javnim ključem (PEM/DER/PKCS1/JWK; EC i RSA) su odbijeni.

**Invarijanta 2 — asimetrična verifikacija sa asimetričnim ključem i ograničenim algoritmom: VAŽI za produkcionu konfiguraciju (P), uz jedan uslovni izuzetak (F2).** Algoritam je ograničen na `alg` iz zaglavlja, a ulaz u granu je samo za RS256/ES256.
- **F2:** python-jose proverava `alg` iz zaglavlja, ali potpis računa algoritmom **objekta ključa**. V3 (`_get_jwks_key`) ima rezervu `keys[0]`. Ako bi JWKS sadržao **isključivo** simetričan ključ (`kty=oct`, `alg=HS256`), V2/V3 bi prihvatili token sa zaglavljem ES256/RS256 potpisan tim ključem (P, test `test_nalaz_f2_*`). V1/V1b odbijaju.
- **Zašto F2 nije materijalan:** zahteva da napadač kontroliše sadržaj JWKS-a (Supabase endpoint ili `SUPABASE_URL`). Ko kontroliše JWKS već može da objavi sopstveni EC ključ i potpiše „ispravan“ ES256 token. F2 ne daje novu sposobnost.
- Produkcioni JWKS (javni GET, 2026-10-11, P): 1 ključ, `kty=EC`, `alg=ES256`, `crv=P-256`, `key_ops=[verify]`, bez privatnog dela i bez `oct` ključa. `kid` i koordinate su identični ključu ugrađenom u kod.

**Pokušaj obaranja:**
| Pitanje | Odgovor |
|---|---|
| Može li zaglavlje izabrati pogrešan tip ključa? | Zaglavlje bira granu, ali HS256 grana ima samo tajnu, a asimetrična samo JWKS/ugrađeni EC (P) |
| Prihvata li se algoritam koji bira napadač? | samo HS256/RS256/ES256, uvek sa ključem svoje porodice; ostali (HS384/512, ES384, PS256, EdDSA, none, lista, null, bez alg) se odbijaju (P) |
| Može li JWKS metapodatak promeniti ograničenje? | V1b koristi `jwk.alg`; JWKS `alg=HS256` na EC ključu → odbijeno (P). Jedini slučaj je F2 |
| Može li isti ključ stići u obe grane? | ne u kodu; jedino ako bi neko u `SUPABASE_JWT_SECRET` upisao javni ključ (pogrešna konfiguracija, **U**: vrednost nije čitana) |
| Slabi li rezerva proveru? | ne: svaka rezerva i dalje traži potpis; neispravan JWKS daje „odbijeno“ (P, 5 režima kvara) |
| Konfiguracija bez promene koda | (a) JWKS sa samo simetričnim ključem (F2); (b) javni ključ u `SUPABASE_JWT_SECRET`. Oba su okidači za ponovni pregled |

## 4. Matrica napada (Task B; `tests/test_jwt_risk_001_matrica.py`, sintetički ključevi, bez mreže)
**78 slučajeva × 3 verifikatora (V1, V2, V3) = 234 provere:** 71 napad, **0 prihvaćenih falsifikata, 0 izuzetaka**; 7 pozitivnih kontrola.

| # | Slučaj | Ishod |
|---|---|---|
| 1–5 | HS256 / ES256 / RS256 zaglavlje (± `kid`), HMAC javnim ključem (produkcioni EC, sint. EC, sint. RSA × PEM, DER, DER-PKCS1, JWK) | 52 slučaja, sva odbijena |
| 6 | HS384, HS512, `hs256`, `Hs256`, ES384, PS256, EdDSA, `alg` kao lista; ES256 zaglavlje + HMAC tajnom; RS256 zaglavlje + EC potpis | odbijeni |
| 7 | `none` / `None` / `NONE`, sa i bez lažnog potpisa | odbijeni |
| 8 | bez `alg` (DER i prava tajna), `alg=null`, zaglavlje nije JSON, dva dela, prazan token | odbijeni |
| 9–11 | bez `kid`, nepoznat `kid`, `kid` produkcionog ključa sa drugim pouzdanim ključem | **prihvaćeni samo ispravni potpisi pouzdanim ključem** (`kid` se ignoriše, potpis odlučuje); potpis nepoznatim ključem → odbijen |
| 12–14 | JWKS: bez `alg`, EC sa `alg` RS256/HS256, RSA sa `alg` ES256, `oct` sa ES256/bez alg, EC + `oct` | odbijeni (izuzetak F2: samo `oct`/HS256 u V2/V3) |
| 15 | JWKS: mreža pada, nije JSON, `keys` nije lista, ključ je smeće, prazno — **stvarni put dohvatanja** | fail-closed; HS256 kontrola i dalje radi |
| 16 | istekao (HS/ES), `nbf` u budućnosti | odbijeni |
| 17 | izmenjen potpis, izmenjen payload (`sub`) | odbijeni |
| 18 | bez `sub`, prazan `sub` | odbijeni |
| HTTP | prave zavisnosti `deps.get_current_user` i `api.get_current_user` | falsifikati 401/403, pravi tokeni 200 |
| WS | `voice_realtime` | svi falsifikati zatvoreni kodom 4401 pre ičega |
| SDK | server prihvata | identitet je serverov (`resp.user.id`), ne iz tokena |

**Pozitivne kontrole (P):** HS256 tajnom, ES256 i RS256 sintetičkim ključem prolaze u V1. U V2/V3 ES256 prolazi, a RS256 **ne** (F1).

**Ostali nalazi (nisu prihvatanje falsifikata):**
- **F1, funkcionalni:** `_get_jwks_key` vraća prvi EC/RSA ključ bez obzira na `alg`, pa uz JWKS [EC, RSA] RS256 u V2/V3 nikad ne prolazi. Produkcija koristi samo ES256, pa bez uticaja.
- **F3, nizak:** ispravno potpisan token **bez `exp`** se prihvata (nije obavezan). Proizvesti ga može samo vlasnik tajne ili privatnog ključa; Supabase uvek upisuje `exp`.

## 5. Regresija (Task E; tačan kod kandidata)
- `tests/test_jwt_risk_001_matrica.py` (20), `test_ns006_t1_jwt_alg_confusion.py`, `test_osb003_jwt.py`, auth/sec testovi (`celina5_secops`, `sec001_predmet_ownership`, `sec005_rate_limiting`, `cron_daily_failclosed_auth`, `wave4_preflight_b_email_cron_auth`, `sec058`, `bu004n1_f1`, `b4_source_authority`), RH001/RH002 (`rh001_legacy_memory_acl`, `rh001_law_brain_authority`, `rh001_hearing_prep_authority`, `rh001_scheduler_crash_window`): **305 passed, exit 0**, JUnit.
- CI na kandidatu (FRI001): Security zelen; pip-audit „No known vulnerabilities, 3 ignored“.

## 6. Životni ciklus izuzetka (Task D)
- `.github/workflows/security.yml`: `--ignore-vuln CVE-2026-85394` (samo taj ID) uz `PYSEC-2026-1325` (drugi, stariji izuzetak). Obrazloženje je u komentaru workflow-a, sa uslovom „ukloniti kad upstream izda ispravku ili ako se ugovor verifikatora promeni“.
- **Nedostaje (P):** imenovan vlasnik, datum isteka i datum odobrenja. Promenu koda verifikatora ne prati ništa automatski, osim JWT testova u CI-ju (NS006/OSB003/JWT-RISK-001), koji bi pali na regresiju.
- Izuzetak **nije menjan**.

## 7. Zaključak
Svi kriterijumi za prihvatanje su ispunjeni:
- nijedan napad nije prihvaćen; pozitivne kontrole prolaze;
- separacija važi u svim dostižnim verifikatorima za produkcionu konfiguraciju;
- SDK rezerva ne zaobilazi potpis; kvarovi JWKS-a su fail-closed;
- izuzetak je uzak; ispravljena verzija ne postoji.

Preostala neizvesnost je ograničena i navedena: F2, vrednost `SUPABASE_JWT_SECRET` (U) i to da produkcija pokreće isti kod (I, Docker iz istog repoa).

**Preporuka: PRIHVATITI IZUZETAK**, uz uslove u `JWT_RISK_001_FOUNDER_DECISION.md`.

**Predlog ispravke F2 (nije primenjen, nije uslov za izdanje):** u `_get_jwks_key` i `_verify_via_live_jwks` prihvatiti samo ključ čiji `kty` odgovara porodici algoritma iz zaglavlja (ES* → EC, RS* → RSA) i ukloniti rezervu `keys[0]`. Isto bi ispravilo i F1.

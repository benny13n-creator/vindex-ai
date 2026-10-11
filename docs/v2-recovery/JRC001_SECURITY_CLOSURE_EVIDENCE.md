# JRC001 — dokazi zatvaranja JWT-RISK-001

Oznake: **P** dokazano · **I** zaključeno · **U** nepoznato.

## 0. Preflight (P, 2026-10-11)
| Ref | SHA |
|---|---|
| `origin/main` (produkcija, `/health` `commit: 80c3902`) | `80c3902be2e06654490972a027a391dbf667dbb4` |
| `release/v2-solo-final-candidate` = PR #16 → `main` (draft) | `c09d87dbbba02daf62738115ac144f15aba88dfc` (**nepromenjen**) |
| `security/jwt-risk-001` | `ed87f4a5` (kandidat je predak) |
| **`security/jrc001-jwt-risk-acceptance`** (ova grana) | `bb87e746` kod + zapis; završni commit dodaje samo dva JRC001 dokumenta |
| Draft PR #17 → `release/v2-solo-final-candidate` | https://github.com/benny13n-creator/vindex-ai/pull/17 |

Divergencije nema: produkcija i kandidat odgovaraju očekivanim vrednostima.

## 1. Zapis odluke (Task 1)
`docs/v2-recovery/JWT_CVE_2026_85394_RISK_ACCEPTANCE.md`
- doslovan citat odluke; odobreno 2026-10-11; važi do 2027-01-09; vlasnik: osnivač;
- dokazi iz JWT-RISK-001, kompenzacione kontrole, F2, F1/F3, okidači, istek;
- PRIHVAĆENO / NIJE PRIHVAĆENO / NIJE ODOBRENO;
- bez potpisa i bez tajni.

Mašinski par: `security/izuzeci_ranjivosti.json`.

## 2. Granica CI izuzetka (Task 2) — P
- `pip-audit -r requirements.txt --ignore-vuln PYSEC-2026-1325 --ignore-vuln CVE-2026-85394`, blokirajuće, bez `continue-on-error`. Poziv je **nepromenjen**.
- Odobrenje pokriva **samo** `CVE-2026-85394`. `PYSEC-2026-1325` (python-ecdsa timing) je zasebna, ranija odluka, dokumentovana u komentaru `security.yml`; ovaj zapis je ne pokriva.
- `requirements.txt`: `python-jose[cryptography]==3.5.0` (tačna, zakucana verzija). `--ignore-vuln` je po ID-ju, pa nova kontrola zahteva i tačnu verziju; svaka promena pada i traži ponovni pregled.
- Runtime JWT kod u odnosu na kandidata: **0 izmenjenih fajlova** (`api.py`, `shared/`, `routers/`, `services/`, `main.py`). Ograničenje algoritama i tipova ključeva je isto kao u JWT-RISK-001.
- Regresioni testovi gađaju stvarne verifikatore:
  - `api._verify_token` i `_verify_via_live_jwks`;
  - `deps._verify_token` i `verify_token_local`;
  - HTTP zavisnosti i WebSocket.

Obim izuzetka ne prelazi odluku, pa nema BLOCKED.

## 3. Kontrola roka (Task 3) — P
- `security/izuzeci_ranjivosti.py` (samo standardna biblioteka) i nov **blokirajući** korak u postojećem poslu `dependency-scan`, **pre** pip-audit-a. Nema novog servisa, rasporeda, tabele ni funkcije aplikacije.
- **Pada kada:**
  - je posle 2027-01-09 ili pre 2026-10-11 (UTC);
  - trajanje je veće od 90 dana;
  - zapis nedostaje, nije JSON, prazan je, nema polje ili ima loš datum;
  - dokument odluke ne postoji;
  - verzija u `requirements.txt` nije `==3.5.0`;
  - pip-audit ignoriše nepoznat ID, odobreni ID nedostaje ili se ponavlja.
- Ne potiskuje ništa i ne produžava rok.
- **Testovi** `tests/test_jrc001_izuzetak_rok.py`: 21 prolazi.
  - Ubačeni datumi: 2026-10-10 ✗, 2026-10-11 ✓, 2026-12-31 ✓, 2027-01-09 ✓, 2027-01-10 ✗, 2027-06-01 ✗; `main()` daje 0, odnosno 1.
  - Takođe pokrivaju 10 vrsta pokvarenog zapisa, verziju, proširenje izuzetka i redosled koraka.
- **Mutacije:** 5/5 uhvaćene (bez provere isteka, verzije, nepoznatih ID-jeva, praznog zapisa i limita od 90 dana).
- **CI:** Security Checks run 38170409233 na `bb87e746` = **success**. Korak je ispisao `OK: CVE-2026-85394 (python-jose==3.5.0) … do 2027-01-09 — još 90 dana`, a pip-audit „No known vulnerabilities found, 3 ignored“ (isto kao pre).
- **Napomena:** ispis dijakritika u CI logu je kozmetički izobličen (`errors="replace"`); provera radi.

## 4. JWT regresija (Task 4) — P
16 fajlova, seme `12345`, JUnit, ukupno **314 passed, exit 0**:
- JRC001 rok (21), JWT-RISK-001 matrica (20), NS006 alg-confusion, OSB003 JWT;
- auth/sec: `celina5_secops`, `sec001_predmet_ownership`, `sec005_rate_limiting`, `sec058`, `cron_daily_failclosed_auth`, `wave4_preflight_b_email_cron_auth`, `bu004n1_f1`, `b4_source_authority`;
- RH001/RH002: `legacy_memory_acl`, `law_brain_authority`, `hearing_prep_authority`, `scheduler_crash_window`.

Rezultat: 0 prihvaćenih falsifikata; pozitivne kontrole prolaze; JWKS kvarovi su fail-closed; nema regresije autorizacije.

**CI Test Suite** na `bb87e746`: run 38170411990 — Python 3.11 i 3.13: **175 failed / 8642 passed** naspram kandidata `c7b809f1` 175 / 8601; poređenje po zaglavljima padova: **0 novih, 0 nestalih** (+41 = 20 JWT-RISK-001 + 21 JRC001). Workflow je „failure“ samo zbog istih nasleđenih padova.

## 5. Paket izdanja (Task 5)
- PR #16 je **nepromenjen** (`c09d87db`). Sadrži `main`, RC1, ONS001 (#12), OSB002 (#13), OSB003 (#14), FRG001 (#15), `hotfix/rh001-memory-acl`, `rh001-ns008`, NS006/NS007/NS008 i FRI001 (P, `merge-base --is-ancestor`).
- **Testiran kod kandidata:** `c7b809f1` (FRI001 CI: 175/175/197 starih padova, 0 novih; Docker, OCR, e2e 23/23, Security zelen). Kod kandidata od tada nije menjan.
- **Zapis odobrenja i kontrola roka NISU u PR #16.** Nalaze se u PR #17 (`security/jrc001-jwt-risk-acceptance`), iznad #16.
- **Predlog integracije:** posle pregleda, PR #17 se spaja u granu kandidata. Novi SHA kandidata tada traži ponovno pokretanje Security i Test Suite. Runtime kod je isti, pa Docker i e2e dokaz ostaju primenljivi (stablo se razlikuje samo u dokumentima, testovima, `security/` i jednom CI koraku). Alternativa je da se #16 spoji prvi, pa #17 posebno.
- **Nasleđeni padovi:** Test Suite 175 (3.11 i 3.13), produkcioni Python 197, isti identiteti kao na `main`.
- **Preostale odluke izdanja:** B (COI semantika za betu) i C (spajanje i deploy tačnog SHA). Odluka A (JWT) je ovim zatvorena.

## 6. Bezbednost
Bez merge-a, push-a na `main`, deploy-a, izmena promenljivih ili ključeva, migracija, Cron-a, produkcionih naloga ili podataka i plaćenih AI poziva. Runtime JWT verifikacija nije menjana. U produkciji je samo pročitan `/health` (GET).

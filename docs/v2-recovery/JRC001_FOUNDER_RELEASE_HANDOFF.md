# JRC001 — predaja osnivaču

## BEZBEDNOSNA ODLUKA
- **JWT izuzetak: ODOBREN** (vaša odluka od 2026-10-11, zapisana doslovno u `docs/v2-recovery/JWT_CVE_2026_85394_RISK_ACCEPTANCE.md`).
- **Obim:** samo `CVE-2026-85394` (GHSA-3qf3-8w2g-rqmx) za `python-jose==3.5.0`. `PYSEC-2026-1325` je zasebna, ranija odluka.
- **Odobreno:** 2026-10-11 · **ističe:** 2027-01-09 (uključivo) · **vlasnik:** osnivač.
- **Raniji ponovni pregled** je obavezan ako:
  - izađe ispravljena verzija python-jose;
  - promeni se produkcioni JWKS;
  - promeni se `SUPABASE_URL` ili `SUPABASE_JWT_SECRET`;
  - izmeni se ili doda JWT verifikator;
  - padne JWT regresija.
- **Preostala ograničenja:**
  - F2: JWKS samo sa simetričnim ključem (danas nije dostižno; predlog ispravke postoji);
  - F1: RS256 u `shared/deps` ne radi (funkcionalno);
  - F3: token bez `exp`.

## IMPLEMENTACIJA
- **Grana:** `security/jrc001-jwt-risk-acceptance`; kod i zapis na `bb87e746`, završni commit dodaje samo ova dva dokumenta.
- **Draft PR #17** → `release/v2-solo-final-candidate`: https://github.com/benny13n-creator/vindex-ai/pull/17
- **Fajlovi:**
  - `docs/v2-recovery/JWT_CVE_2026_85394_RISK_ACCEPTANCE.md`;
  - `security/izuzeci_ranjivosti.json` i `.py`;
  - `.github/workflows/security.yml` (jedan nov blokirajući korak pre nepromenjenog pip-audit-a);
  - `tests/test_jrc001_izuzetak_rok.py`;
  - JRC001 dokumenti.
  - PR sadrži i JWT-RISK-001 procenu i matricu (`ed87f4a5`).
- **Runtime JWT kod: nije menjan.**
- **Testovi:**
  - lokalno 314 passed, exit 0 (JWT, auth, RH001/RH002, rok);
  - mutacije kontrole roka 5/5.
- **CI na `bb87e746`:**
  - Security **success**; novi korak ispisuje „važi do 2027-01-09 — još 90 dana“, a pip-audit „3 ignored“ kao pre;
  - Test Suite: 175 = 175 nasleđenih padova, **0 novih**.
- **Kontrola roka je proverena:** posle 2027-01-09, uz drugu verziju paketa, neispravan zapis ili nov izuzetak, CI pada.

## IZDANJE
- **Zaključan kandidat:** PR #16, `c09d87dbbba02daf62738115ac144f15aba88dfc`, **nepromenjen** (testiran kod: `c7b809f1`).
- **Zapis o prihvatanju rizika NIJE u PR #16.** Nalazi se u PR #17, iznad njega.
- **Novi CI je potreban** samo ako se #17 spoji u granu kandidata. Tada je SHA nov, pa treba ponovo pokrenuti Security i Test Suite. Runtime kod je isti.
- **Preostala odluka B (COI):** COI iz Smart Intake-a radi samo u starom čarobnjaku i V2 ga ne prikazuje; stara provera „ime prvo“ i dalje piše „Ne možete zastupati…“.
- **Preostala odluka C:** spajanje i deploy tačnog SHA.
- **Produkcija:** nepromenjena (`80c3902`).

## KONAČNI STATUS
- `JWT_RISK_ACCEPTANCE = APPROVED`
- `JWT_CLOSURE_RECORD = PASS`
- `JWT_EXPIRY_CONTROL = PASS`
- `JWT_REGRESSIONS = PASS`
- `FINAL_RELEASE_CANDIDATE = VERIFIED` (`c09d87db`, nepromenjen; JRC001 je zasebno, u PR #17)
- `PRODUCTION_RELEASE = NOT AUTHORIZED`

## JEDAN SLEDEĆI KORAK
Odlučite o **B (COI semantika za betu)**. Posle toga ostaje samo odluka C za tačan SHA.

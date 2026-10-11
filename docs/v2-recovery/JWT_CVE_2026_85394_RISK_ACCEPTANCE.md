# Prihvatanje rizika — CVE-2026-85394 (python-jose 3.5.0)

**Kanonski zapis odluke osnivača.** Mašinski čitljiv par: `security/izuzeci_ranjivosti.json`. Proverava ga `security/izuzeci_ranjivosti.py` u CI poslu `dependency-scan`.

## 1. Ranjivost i zavisnost
- **CVE-2026-85394** (alias GHSA-3qf3-8w2g-rqmx), CVSS v4 9.3.
- DER javni ključ se u python-jose prihvata kao HMAC tajna kada verifikacija ne ograniči algoritme.
- **Paket:** `python-jose[cryptography]==3.5.0` (`requirements.txt`). Pogođene su verzije ≤ 3.5.0; ispravljene verzije nema (PyPI, provereno 2026-10-11).

## 2. Odluka (tekst osnivača, doslovno)
> On **2026-10-11**, the founder explicitly approved the narrowly scoped residual-risk exception for:
> - Vulnerability: `CVE-2026-85394`
> - Package: `python-jose==3.5.0`
> - Scope: existing exception in `.github/workflows/security.yml`
> - Maximum duration: 90 days
> - Approval date: `2026-10-11`
> - Latest permitted validity date: `2027-01-09`
> - Approval owner: Vindex founder
>
> This authorization accepts the specified residual vulnerability risk under the documented compensating controls.
>
> **It does NOT authorize merging, deploying, changing production configuration or weakening JWT validation.**

Odluka je data kao poruka osnivača u radnoj sesiji (direktiva JRC001). Ovaj zapis nema potpis ni elektronski potpis i ne predstavlja odobrenje bilo koga drugog.

| Polje | Vrednost |
|---|---|
| Odobreno | 2026-10-11 |
| Važi najkasnije do | **2027-01-09** (uključivo; 90 dana) |
| Vlasnik | osnivač Vindex AI |

## 3. Dokazi (JWT-RISK-001, grana `security/jwt-risk-001`, `ed87f4a5`, kandidat `c09d87db`)
- Svi dostižni verifikatori su popisani:
  - `api.py::_verify_token` i `_verify_via_live_jwks`;
  - `shared/deps.py::_verify_token` (rute i WebSocket);
  - `verify_token_local` (samo rate limit).
- 78 slučajeva × 3 verifikatora = 234 provere; 71 napad, **0 prihvaćenih falsifikata**.
- Pozitivne kontrole (HS256, ES256) prolaze.
- JWKS kvarovi (5 režima) su fail-closed.
- Namerno ranjiva postavka reprodukuje CVE, pa napad nije izmišljen.
- Produkcioni javni JWKS (2026-10-11): jedan EC/ES256 ključ, identičan ugrađenom.
- Izveštaj: `docs/v2-recovery/JWT_RISK_001_FINAL_ASSESSMENT.md`.

## 4. Kompenzacione kontrole (postojeće)
1. HS256 se proverava **isključivo** tajnom `SUPABASE_JWT_SECRET`, sa `algorithms=["HS256"]`; javni ključ nikad ne stiže do HMAC grane.
2. ES256/RS256 se proveravaju samo ključem iz JWKS-a ili ugrađenim EC ključem, sa tačno jednim dozvoljenim algoritmom.
3. Svaka rezerva (SDK, živi JWKS) i dalje traži važeći potpis; greške daju „odbijeno“.
4. CI testovi napadaju stvarne verifikatore:
   - `tests/test_ns006_t1_jwt_alg_confusion.py`;
   - `tests/test_osb003_jwt.py`;
   - `tests/test_jwt_risk_001_matrica.py`.
5. Kontrola roka i obima: `security/izuzeci_ranjivosti.py` (v. §7).

## 5. Preostali rizik F2 (JWKS / tip ključa)
Ako bi JWKS sadržao **isključivo** simetričan ključ (`kty=oct`, `alg=HS256`), `shared/deps` bi prihvatio token sa ES256/RS256 zaglavljem potpisan tim ključem. Uzroci su rezerva `keys[0]` i to što python-jose potpis proverava algoritmom objekta ključa.
- Danas nije dostižno, jer produkcioni JWKS ima samo EC/ES256.
- Ko kontroliše JWKS već može da podmetne sopstveni EC ključ, pa F2 ne daje novu sposobnost.
- Predložena ispravka (biranje ključa po `kty`, bez `keys[0]`) **nije** primenjena i nije deo ovog odobrenja.

## 6. Zasebno dokumentovana ograničenja (nisu deo prihvaćenog CVE rizika)
- **F1:** RS256 se u `shared/deps` ne verifikuje kada je u JWKS-u EC ključ prvi. To je funkcionalni nedostatak; produkcija koristi samo ES256.
- **F3:** ispravno potpisan token bez `exp` se prihvata. Napraviti ga može samo vlasnik tajne ili privatnog ključa.

## 7. Obavezan raniji ponovni pregled
1. Izađe ispravljena verzija python-jose.
2. Promeni se produkcioni JWKS.
3. Promeni se konfiguracija `SUPABASE_URL` ili `SUPABASE_JWT_SECRET`.
4. Promeni se postojeći JWT verifikator.
5. Uvede se nov put JWT verifikacije.
6. Padne bilo koji obavezan JWT bezbednosni regresioni test.

Automatski se hvata: promena verzije paketa u `requirements.txt`, nov ili uklonjen `--ignore-vuln` ID i istek roka (CI korak pada). Okidači 2–6 hvataju se pregledom i JWT testovima u CI-ju.

## 8. Istek
Posle **2027-01-09** CI korak „Odobreni izuzeci ranjivosti“ pada (posao `dependency-scan` je blokirajući). Produženje traži **novo izričito odobrenje osnivača** i izmenu zapisa. Automatskog produženja nema.

## 9. Obim
- **PRIHVAĆENO:** samo opisani preostali rizik CVE-2026-85394 za `python-jose==3.5.0`, uz kontrole iz §4, do 2027-01-09.
- **NIJE PRIHVAĆENO:**
  - druge ili buduće ranjivosti;
  - druga verzija paketa;
  - nove ili izmenjene JWT konfiguracije (uključujući JWKS sa simetričnim ključem);
  - bilo koja bezbednosna regresija.
  - `PYSEC-2026-1325` (python-ecdsa) je **zasebna, ranija** odluka i nije pokrivena ovim zapisom.
- **NIJE ODOBRENO:** spajanje, deploy, produkciono izdanje i izmena produkcione konfiguracije. To ostaju zasebne odluke osnivača.

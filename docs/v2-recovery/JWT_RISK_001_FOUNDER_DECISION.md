# JWT-RISK-001 — odluka za osnivača

## IZVRŠNI VERDIKT: **PRIHVATITI IZUZETAK** (uslovno, najviše 90 dana od vašeg odobrenja)

Biblioteka koju Vindex koristi za proveru prijave (`python-jose` 3.5.0) ima poznatu kritičnu grešku, a ispravljena verzija ne postoji. Napad radi samo ako aplikacija pri proveri ne ograniči algoritam. Vindex ga ograničava na svim mestima gde proverava prijavu, a 71 vrsta falsifikovanog tokena je bez izuzetka odbijena.

Oznake: **P** dokazano · **I** zaključeno · **U** nepoznato.

## DOKAZI
- **Kandidat:** `c09d87dbbba02daf62738115ac144f15aba88dfc`. Produkcija `80c3902b` ima isti kod provere prijave, osim OSB003 ispravke (500 → 401).
- **Mesta provere (sva dostižna):** `api.py::_verify_token` i njegova rezerva sa živim JWKS-om; `shared/deps.py::_verify_token` (rute i WebSocket glasa); `verify_token_local` (rate limit). Svako prvo pita Supabase server, pa tek onda proverava lokalno.
- **Napadi:** 78 slučajeva × 3 verifikatora = 234 provere; 71 napad.
  - **Prihvaćenih falsifikata: 0 (P).** Izuzetaka (500): 0.
  - Kroz HTTP falsifikati daju 401/403; WebSocket ih zatvara pre bilo čega.
- **Pozitivne kontrole (P):** pravi HS256 i ES256 tokeni prolaze, pa test nije „odbij sve“. RS256 prolazi u `api.py`, a u `deps` ne (F1, funkcionalno; produkcija ga ne koristi).
- **Negativne kontrole (P):** namerno ranjiva konfiguracija na istoj verziji biblioteke **prihvata** falsifikat. Napad je stvaran, samo nije dostižan u Vindex kodu.
- **Fail-closed (P):** nedostupan ili pokvaren JWKS (5 režima kvara) ne propušta nijedan falsifikat.
- **Pretpostavke:**
  - HS256 se proverava samo tajnom (P).
  - ES256/RS256 se proveravaju samo ključem iz JWKS-a sa jednim dozvoljenim algoritmom (P).
  - Produkcioni JWKS ima jedan EC/ES256 ključ, isti kao ugrađeni (P, javni GET).
  - Vrednost tajne nije čitana (U).
- **Zvanični status (P):** CVE-2026-85394 / GHSA-3qf3-8w2g-rqmx, CVSS 9.3, pogađa ≤ 3.5.0, **zakrpe nema** (PyPI najnovije = 3.5.0).
- **Regresija (P):** 305 testova (JWT, auth, RH001/RH002), exit 0. CI Security na kandidatu je zelen.

## PREOSTALI RIZIK
- **F2 (ojačavanje):** kad bi JWKS sadržao samo simetričan ključ, `shared/deps` bi prihvatio podmetnut token. Danas nije tako, a ko kontroliše JWKS već može da falsifikuje i bez ovoga. Predložena je mala ispravka (biranje ključa po tipu), koja nije primenjena.
- **F3:** ispravno potpisan token bez roka važenja se prihvata. Proizvesti ga može samo vlasnik tajne.
- **Procena prestaje da važi ako se dogodi bilo šta od sledećeg:**
  - izađe nova verzija `python-jose`;
  - promeni se ili doda ključ u produkcionom JWKS-u (posebno simetričan);
  - promeni se `SUPABASE_URL` ili `SUPABASE_JWT_SECRET`;
  - doda se nova ruta ili kod koji čita JWT;
  - promeni se ijedna od funkcija iz inventara;
  - pređe se na drugu biblioteku za JWT.

## PREPORUČENI USLOVI ODOBRENJA
- **Izuzetak:** samo **CVE-2026-85394** (GHSA-3qf3-8w2g-rqmx), samo za `python-jose==3.5.0`, samo u CI pip-audit proveri (postojeći red u `.github/workflows/security.yml`, bez proširenja).
- **Trajanje:** najviše **90 dana od datuma vašeg odobrenja**. Istek znači ponovni pregled, ne automatsko produženje.
- **Vlasnik:** vi, kao osnivač; tehnički pregled radi agent na vaš zahtev.
- **Obavezan ponovni pregled pre isteka** kad nastupi bilo šta iz liste „Procena prestaje da važi ako…“.
- **Preporuka (nije uslov):** u sledećem bezbednosnom koraku primeniti ispravku F2/F1 i obavezan `exp`.
- **Podsetnik:** zapišite datum isteka u kalendar. Nisam pravio ponavljajuće zadatke ni infrastrukturu.

## BEZBEDNOST PRODUKCIJE
- Bez napada na produkciju i bez falsifikovanih tokena poslatih produkciji.
- Bez pravih tokena i bez čitanja tajni.
- Bez produkcionih upisa, izmena konfiguracije ili ključeva.
- Bez izmena izuzetka i allowlist-e.
- Bez merge-a i deploy-a.
- U produkciji je izvršen samo jedan javni GET JWKS-a (javni ključ).

## JEDAN SLEDEĆI KORAK
**Odobrite ili odbijte** izuzetak za CVE-2026-85394 pod gornjim uslovima, i upišite datum odobrenja (od njega teče 90 dana). Ovo **nije** odobrenje izdanja: merge i deploy SHA `c09d87db` ostaju zasebna odluka (FRI001, odluka C).

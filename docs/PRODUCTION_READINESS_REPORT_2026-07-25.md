# Vindex AI — Production Readiness Report (2026-07-25)

**Metod:** 3 paralelna istraživanja (env/security, DB/migracije, guardrails/GDPR)
+ direktna provera test suite-a i cron/WS/background-servisa. Sve tvrdnje
ispod imaju file:line ili komandu-i-izlaz dokaz. Gde repo NE MOŽE potvrditi
stanje žive produkcije (npr. da li je migracija stvarno pokrenuta u
Supabase-u), to je eksplicitno označeno — nijedna tvrdnja o živoj bazi nije
data bez pristupa bazi.

**Verdikt u jednoj rečenici:** Kod je testno zdrav (2202/2202 prolazi) i
osnovne zaštite (CORS, XSS/SQLi, GDPR delete, audit log) rade — ali postoje
**3 konkretne stavke koje treba proveriti/popraviti PRE prvog javnog
pokretanja**, navedene u Preporukama na kraju.

---

## 1. Konfiguracija okruženja i bezbednost

| Stavka | Status | Dokaz |
|---|---|---|
| `.env.example` pokrivenost | ⚠ | Fajl ima 8 varijabli; kod stvarno čita **50**. 42 nisu dokumentovane — uključujući `SECRET_KEY` (routers/client_portal.py:64 — `raise RuntimeError` ako nedostaje, dakle OBAVEZNA), `SENTRY_DSN`, `BRIEFING_CRON_SECRET`, `VAPID_*`, `TWILIO_*`, `VIBER_*`, `EMAIL_SMTP_*`, `REDIS_URL`, `AZURE_OPENAI_*` i drugi |
| Neiskorišćene/pogrešne dokumentovane varijable | ⚠ | `COHERE_API_KEY` je u `.env.example` ali se nigde ne čita (0 pogodaka u kodu). `SUPABASE_ANON_KEY` je u `.env.example`, ali backend je ne čita — stvarno je hardkodovana u `static/vindex.js:236` (publishable ključ, po dizajnu javan, zaštićen RLS-om — nije bezbednosni propust, ali `.env.example` red ne odgovara stvarnom mehanizmu) |
| `.env` postojanje / gitignore | ✓ | Lokalno postoji, `.gitignore:4,31-32` ga isključuje (`.env`, `.env.local`, `.env.production`) |
| DEBUG režim | ✓ | 0 pogodaka za `DEBUG=`, `debug=True`, `reload=True` u `api.py` — nema šta da procuri u produkciju |
| CORS | ✓ | `api.py:903-915` — `ALLOWED_ORIGINS` iz env-a (default `https://vindex.rs`), NIJE `"*"`, `allow_credentials=True` uz eksplicitnu listu (bezbedna kombinacija), metode/headeri eksplicitno ograničeni |
| Hardkodovani tajni ključevi u kodu | ✓ | 0 pogodaka za `sk-`, `sk-ant-`, `AKIA...` kroz `.py`/`.js` van `.env*` |

---

## 2. Baza podataka i migracije

**Sve iz repo koda — bez pristupa živoj Supabase bazi; gde nešto NE MOŽE biti potvrđeno, to je eksplicitno navedeno.**

| Stavka | Status | Dokaz |
|---|---|---|
| Broj/redosled migracija | ⚠ | 76 fajlova u `migrations/` (002→084, nema 001). Numerička rupa 027-035 (9 brojeva nedostaje), neobjašnjena u repo-u |
| **Migration direktorijum kolizija** | ✗ | I DALJE STOJI (poznat nalaz): poseban `supabase_migrations/` direktorijum (044, 045) koristi ISTE brojeve kao `migrations/044_anomaly_detection.sql` i `migrations/045_firm_intelligence.sql` — potpuno drugačiji sadržaj pod istim brojem u 2 fascikle |
| **Duplirani broj unutar `migrations/`** | ✗ | `050_cio_dnevni_izvestaj.sql` i `050_pinecone_capacity_monitoring.sql` — isti broj, dva različita fajla |
| Bazne tabele (predmeti/klijenti/korisnici) | ⚠ | **Nema CREATE TABLE ni u jednoj migraciji** — nastale direktno u Supabase Dashboard-u pre migration-konvencije. **Fresh environment se NE MOŽE rekonstruisati čistim replay-om `migrations/*.sql`** |
| `security_events`/`audit_log` | ✓ | CREATE TABLE potvrđen (043, 041/073) |
| RLS politike | ⚠ | 54 `ENABLE ROW LEVEL SECURITY` + 185 `CREATE POLICY` u migracijama, ALI `scripts/export_rls_policies.py` (postoji, nikad pokrenut) tvrdi da se RLS danas menja ISKLJUČIVO ručno u Supabase Dashboard-u — **migracioni brojevi su istorijski snapshot, ne pouzdan izvor trenutnog stanja**. 1 mogući gap: `case_benchmarks` ima user-kolonu, RLS enable nije pronađen (nepotvrđeno da li namerno) |
| Indeksiranje | ✓ | 196 `CREATE INDEX` ukupno, 11 na `predmet_id`/`korisnik_id`/`datum`. Nula pgvector/ivfflat — očekivano, vektorska pretraga ide isključivo preko Pinecone-a |
| Tracking primenjenih migracija | ✗ | **Ne postoji nijedan mehanizam** (CHANGELOG, tracking tabela) koji beleži šta je stvarno pokrenuto u produkciji. Status živi raštrkano po `docs/architecture/*.md` i sesijskoj memoriji. **NE MOŽE SE POTVRDITI iz repo-a** da li su migracije 081-084 pokrenute u produkciji |

---

## 3. Integracioni testovi i pozadinski servisi

| Stavka | Status | Dokaz |
|---|---|---|
| Pun pytest suite | ✓ | `python -m pytest -q` → **2202 passed, 1 skipped**, 0 grešaka. Skip je namerno gated (`tests/test_apr_integration.py`, `SKIP_LIVE_APR_TEST` env, default skip — poznat, dokumentovan APR reCAPTCHA blok iz ranije ove sesije, ne regresija) |
| `voice_realtime.py` WS endpoint | ✓ | Registrovan (`api.py:710`), `tests/test_voice_realtime.py` 30/30 prolazi. Frontend povezan ovom istom sesijom (`static/vindex.js` VindexLive) |
| Background agenti (KORAK B) | ✓ | Pozivaju se iz `/api/cron/daily` (jedinstveni dispečer, `api.py:1503-1801`, Modul 10) — komentar u kodu (`api.py:1691-1704`) dokumentuje da je RANIJI duplirani `/api/cron/daily` u `routers/email_notif.py` tiho "pobeđivao" u rutiranju i sprečavao ovaj dispečer da ikad izvrši — **taj bug je pronađen i ispravljen (SEC-002, ranija sesija), potvrđeno i dalje ispravno ovom proverom** |
| Word Add-in manifest | ⚠ | Fajlovi postoje i servirani su (`/word_addin` mount, `api.py`), 20/20 testova prolazi — ALI `manifest.xml` je i dalje **lokalni dev manifest** (`https://localhost:8000/...` URL-ovi, placeholder GUID) — v. `docs/WORD_ADDIN_SIDELOAD.md`, mora se ažurirati na produkcione URL-ove pre javnog sideload-a |

---

## 4. Kritični zidovi zaštite (Guardrails) i GDPR/DPA

| Stavka | Status | Dokaz |
|---|---|---|
| Rate Limiter — fail-open ponašanje | ✓ | `tests/test_sec005_failopen_limiter.py` 6/6 — potvrđeno da Redis/Upstash pad ne obara zahteve (`in_memory_fallback_enabled=True`, `swallow_errors=True`, namerno, dokumentovan koren: ranija Upstash kvota-havarija) |
| Rate Limiter — pokrivenost | ⚠ | Nema `SlowAPIMiddleware`/globalne registracije — samo **29 od ~573 ruta** ima eksplicitan `@limiter.limit(...)`. `default_limits=["60/hour"]` iz `shared/rate.py` se NE primenjuje globalno bez po-ruti dekoracije |
| XSS/SQLi sanitizacija | ✓ | `tests/test_xss_sanitization_sweep.py` **58/58** prolazi. 114 parametrizovanih `.table(...)` poziva, 0 raw SQL string-interpolacije |
| Log scrubbing (JMBG/lozinke/tokeni) | ⚠ | Nema nađenog redaction sloja (logging.Filter, redact/scrub helper) — odsustvo potvrđeno, ali sken ne može garantovati da se osetljivo polje NIKAD ne loguje u ~500-rutnom kodu |
| GDPR account delete | ✓ | `tests/test_gdpr_delete.py` 5/5 — `DELETE /api/gdpr/account` anonimizuje profil, namerno NE briše predmete/klijente (po dizajnu, usklađeno sa javnim tekstom u privacy.html/dpa.html) |
| DPA/Privacy stranice | ✓ | `privacy.html` (168 l.), `static/dpa.html` (154), `static/security.html` (335), `static/bezbednosni-list.html` (82) — sve postoje sa realnim sadržajem |
| Audit log (security_events) | ✓ | Tabela iz `migrations/043_security_bulletproof.sql`, upis potvrđen na `api.py:1951` |

---

## Dodatni nalaz (otkriven ukrštanjem sekcija 1 i 4)

**`BRIEFING_CRON_SECRET` fail-open ako nije podešen.** `api.py:1518-1521`:

```python
cron_secret = os.getenv("BRIEFING_CRON_SECRET", "")
x_secret = request.headers.get("X-Cron-Secret", "")
if cron_secret and x_secret != cron_secret:
    raise HTTPException(status_code=403, detail="Neovlašćen pristup.")
```

Ako `BRIEFING_CRON_SECRET` NIJE podešen u produkcionom `.env` (a nije
dokumentovan u `.env.example` — v. Sekcija 1), `cron_secret` je prazan
string, `if cron_secret and ...` se skraćuje na `False`, i provera se
**potpuno preskače** — `/api/cron/daily` (koji pokreće retention cleanup,
background agente i sve dnevne module) postaje pozivan BEZ IKAKVE
autentifikacije od bilo koga ko zna URL.

---

## Preporuke pre prvog javnog pokretanja

1. **[KRITIČNO] Potvrditi da je `BRIEFING_CRON_SECRET` stvarno podešen u produkcionom `.env`** (Render.com env vars) — bez toga je `/api/cron/daily` javno pozivan bez auth-a. Dodati ga i u `.env.example` da se ovo ne ponovi u budućem deployment-u.
2. **[VISOK PRIORITET] Ažurirati `.env.example`** da pokriva svih 42 nedokumentovanih varijabli koje kod stvarno čita — posebno `SECRET_KEY` (obavezan, ruši startup ako nedostaje) i ostale auth/webhook secrete. Ukloniti ili ispraviti `COHERE_API_KEY` (neiskorišćen) i `SUPABASE_ANON_KEY` (pogrešno opisan mehanizam) redove.
3. **[VISOK PRIORITET] Rešiti migration direktorijum koliziju** (`migrations/` vs `supabase_migrations/`, brojevi 044/045) i **duplirani broj 050** unutar `migrations/` — makar preimenovanjem i jasnom napomenom koji fajl je stvarno primenjen, da se spreči da neko slučajno pokrene pogrešan/stari fajl.
4. **[SREDNJI PRIORITET] Rate limiter pokrivenost** — razmotriti da li 29/573 ruta sa eksplicitnim limitom je namerno (samo osetljive/skupe rute) ili treba globalna `SlowAPIMiddleware` registracija kao baseline zaštita za ostatak.
5. **[SREDNJI PRIORITET] Word Add-in manifest** — pre javnog sideload-a, zameniti `https://localhost:8000/...` produkcionim URL-ovima i generisati pravi GUID (već dokumentovano u `docs/WORD_ADDIN_SIDELOAD.md`, samo podsetnik da ostaje otvoreno).
6. **[NIZAK PRIORITET, ali vredi jednom uraditi] Jedan izvor istine za "šta je primenjeno u produkciji"** — trenutno ne postoji, status živi raštrkano po docs/ izveštajima. Ne mora biti složen mehanizam — i prost `MIGRATIONS_APPLIED.md` koji se ažurira posle svakog ručnog pokretanja bio bi dovoljan da se izbegne buduća nesigurnost tipa "da li je 081-084 primenjeno".

**Sve ostalo iz zahtevanih 4 celine je verifikovano i zdravo** — CORS,
DEBUG isključen, XSS/SQLi zaštita, GDPR delete, audit log, indeksiranje,
pun test suite i pozadinski servisi (voice WS, background agenti) rade
kako je dokumentovano.

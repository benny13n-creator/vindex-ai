# VINDEX — Email podsetnici: put do jednog proverenog beta podsetnika (NS3-N04)

Stanje koda: `night/iron-continuity-ns3` na bazi `469085b6` (produkcija). Ovaj dokument NE aktivira ništa.
Oznake: **PROVEN** (izvršeno ili pročitano iz koda/zapisa), **INFERRED**, **UNKNOWN**.

## 1. Okidači koji danas mogu da pokrenu `posalji_podsetnike`

| # | Okidač | Raspored | Autentikacija | Stanje |
|---|---|---|---|---|
| 1 | GitHub `.github/workflows/email-cron.yml` → `POST https://vindex.rs/email-notif/send-reminders` | `0 8 * * *` UTC (GitHub kasni; stvarna pokretanja 11:48–17:06 UTC) | `X-Cron-Key` = GitHub secret `CRON_TOKEN`, ruta poredi sa Render `CRON_SECRET` | **PROVEN**: poslednjih 6 zakazanih pokretanja = failure; 2026-10-17 11:48 UTC na `469085b6`: **HTTP 403** → ključevi nisu usklađeni |
| 2 | `POST /api/cron/daily` (dispečer, modul email_podsetnici + onboarding + nedeljni ponedeljkom) | nijedan raspored u repou (`*.yml/*.toml/Procfile`) | `X-Cron-Secret` = `BRIEFING_CRON_SECRET` | **UNKNOWN** da li ga išta spolja poziva (komentari pominju Render cron / cron-job.org; nije konfigurisano u repou) |
| 3 | Ručno: isti endpoint kao #1 sa osnivačevim Bearer JWT-om | — | `FOUNDER_EMAILS` | dostupno |

SMS: `sms-cron.yml` ima samo `workflow_dispatch` (raspored uklonjen u Alerts sprintu) — ostaje isključen.

## 2. Dupli okidač — šta štiti od duplog slanja (PROVEN iz koda i testova)

- Pre slanja se upisuje rezervacija u `email_notif_log` (UNIQUE `user_id, predmet_id, datum_roka, dana_pre`, migracija 021). Drugi proces dobija 23505 → `preskoceno`, ne šalje. Test: `tests/test_b10_reminder_claim.py`, `tests/test_alerts_email_integration.py::test_ponovljen_lanac_istog_dana_ne_salje_duplikat`.
- Garancija je **at-most-once pokušaj**, ne exactly-once isporuka. SMTP pad posle rezervacije = `neisporuceno` (nema automatskog ponavljanja).
- Nedeljni sažetak koristi `dana_pre = 0`; dnevni podsetnici `1/3/7` → ne sudaraju se.

## 3. Ko dobija podsetnik (PROVEN)

Red u `korisnik_email_notif` sa `aktivan = true` i uključenim `dan_7/dan_3/dan_1` · predmet aktivan (nije zatvoren/arhiviran/odbijen/u brisanju) · rok `vaznost` iz `_ACTIONABLE_VAZNOST` · rok ljudski ili AI rok koji je advokat potvrdio (INV-2) · adresa = `profiles.email` vlasnika (jedini primalac; isto važi za probni email i oznaku „Šalje se na“ posle TENFRONTS-M10) · `EMAIL_SMTP_HOST` podešen (inače `greske`, bez rezervacije).

Uključivanje: **samo stari UI** (`/app-legacy` → podešavanja email obaveštenja → `POST /email-notif/profil`; ruta vraća 503 bez `EMAIL_SMTP_HOST`). V2 (`/app`) nema taj ekran. Poslednje read-only merenje (pre ovog sprinta): 0 aktivnih profila.

## 4. Kako čitati ishod posla

| Odgovor `send-reminders` | Znači | Ne znači |
|---|---|---|
| HTTP 403 | ključ nije prihvaćen; ništa nije pokušano | — |
| `poslato > 0`, ostalo 0 | SMTP server je **prihvatio** poruku | da je stigla u sanduče |
| `napomena: Nema aktivnih profila` | niko nije uključen | isporuku |
| `greske > 0` | poznat neuspeh bez slanja (nema adrese, nema SMTP-a, pad rezervacije ili provere predmeta) | — |
| `neisporuceno > 0` | rezervisano, SMTP pao → ishod nepoznat, ručna provera | da poruka nije stigla |
| `preskoceno > 0` | drugi proces je već rezervisao | grešku |

Prijem u sanduče potvrđuje samo primalac (ili log provajdera). Ništa u Vindex-u to ne meri.

## 5. Redosled koraka — SAMO osnivač (ništa od ovoga nije urađeno)

1. Render: postaviti `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT` (587, STARTTLS), `EMAIL_SMTP_USER`, `EMAIL_SMTP_PASS`, po želji `EMAIL_FROM`. Restart servisa.
2. GitHub secret `CRON_TOKEN` postaviti na **istu** vrednost kao Render `CRON_SECRET` (oba neprazna).
3. Odlučiti da li se `/api/cron/daily` zakazuje (i gde). Ako da — oba okidača rade isti posao; rezervacija sprečava duplo slanje istog (korisnik, predmet, datum, dana_pre).
4. Jedan beta nalog: u `/app-legacy` uključiti email obaveštenja (stvara red `korisnik_email_notif`); proveriti oznaku „Šalje se na“ = adresa iz profila.
5. „Pošalji test email“ → očekivano `✓ Test email poslat na <adresa>`; potvrditi **prijem** u sandučetu tog naloga.
6. Uneti (ili potvrditi AI) kritičan rok za sutra u aktivnom predmetu tog naloga.
7. GitHub → Actions → „Email Podsetnici za rokove“ → Run workflow. Zeleno = HTTP 2xx + 4 validna brojača + `greske = 0` + `neisporuceno = 0`.
8. Potvrditi prijem podsetnika u sanduče. Tek tada: „jedan podsetnik isporučen“ — za taj nalog, taj dan.

## 6. Nalazi ovog zadatka

- **ISPRAVLJENO (NS3-N04):** stari UI je na „Deaktiviraj“ uvek prikazivao „Email notifikacije deaktivirane.“, i kad `DELETE /email-notif/profil` vrati 500/429/401 — podsetnici bi i dalje stizali. Sada se prikazuje greška i ponovo učitava stvarno stanje. Test: `tests/test_ns3_n04_deaktivacija_email.py`.
- **DOKAZANO, ODLOŽENO (odluka o proizvodu):** provera duplikata pre rezervacije radi po (korisnik, datum, dana_pre), ne po predmetu. Ako isti dan posle prvog pokretanja drugi predmet dobije potvrđen rok za isti datum, drugo pokretanje ga **tiho preskače** (`0/0/0/0`, isto kao „ništa nije dospelo“). Demonstracija nad stvarnim `posalji_podsetnike` (lažna baza, lažan SMTP): drugo pokretanje `poslato 0`, rezervacija samo za prvi predmet. Ispravka bi značila drugi email istog dana (ili ponovljen sadržaj prvog predmeta) — to je odluka o granularnosti obaveštenja.

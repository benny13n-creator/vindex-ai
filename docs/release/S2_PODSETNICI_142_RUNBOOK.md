# Runbook — puštanje podsetnika (migracija 142) i Bojanovog kandidata

Grana `feature/bojan-n2-n9` (stacked na PR #58 `feature/bojan-n0-n1-intake-closure`). **Nijedan korak ispod nije izvršen.**
Svaki produkcioni korak traži izričito odobrenje osnivača. Dokazi: `docs/v2-execution/BOJAN_N2_N9_STATE.md` (Sektor 2, noćni sprint).

## 0. Stanje produkcije pre puštanja (samo čitanje, 2026-10-27/28)

| Činjenica | Dokaz |
|---|---|
| Migracija 142 NIJE primenjena | PostgREST `email_podsetnik_dogadjaj` / `email_podsetnik_pokretanje` → 404 `PGRST205` |
| `email_notif_log` ima 0 redova | `count=exact` → `*/0` — stara istorija podsetnika ne postoji, rizik prelaza sa starog dnevnika = 0 |
| 1 uključen email profil (`korisnik_email_notif.aktivan`) | `count=exact` → `1` |
| `email-cron.yml` radi (403 do 23.10, uspeh od 24.10), stvarni početak 11–17 h UTC | GitHub API |
| `ai_cache`: 1 sintetički red iz sprinta (`3a2eb061…`), nijedan nov red posle 2026-10-27 01:00Z | `count=exact` |

## 1. Pre puštanja

1. **Rezerva**: potvrditi da Supabase projekat ima važeću rezervnu kopiju / PITR za današnji dan (Supabase Dashboard → Database →
   Backups). Bez potvrđene rezerve — STOP.
2. **CI**: PR #58 mora biti zelen (ponoviti `pytest (Python 3.13)` — jedini pad je `test_website_v2_remediacija::…` koji lokalno
   prolazi 5/5) i spojen PRE stacked PR-a ove grane. Stacked PR mora proći ceo CI.
3. **Redosled migracija**: 142 je jedina nova migracija; broj 142 nije zauzet ni na jednoj grani na remote-u (provereno).

## 2. Migracija 142 (pokreće osnivač, SQL Editor)

- Samo DODAJE dve tabele; `email_notif_log` i njen UNIQUE se ne menjaju. Ponovljiva (`IF NOT EXISTS`), i posle delimične primene.
- Posle primene, provera (samo čitanje):
  ```sql
  SELECT to_regclass('public.email_podsetnik_dogadjaj'), to_regclass('public.email_podsetnik_pokretanje');
  SELECT privilege_type FROM information_schema.role_table_grants
   WHERE table_name IN ('email_podsetnik_dogadjaj','email_podsetnik_pokretanje') AND grantee='service_role';
  ```
  Očekivano: obe tabele postoje; `dogadjaj` SELECT/INSERT/UPDATE, `pokretanje` SELECT/INSERT.
- **Stari kod nad novom šemom radi nepromenjeno** (dokazano matricom, §4) — migracija se može primeniti danima pre koda.

## 3. Puštanje koda — stari dispečer NE SME da ima okidač tokom prelaza

Dokaz (lažna baza, stari modul `342824d1` i nov modul, isti dan):

| Kombinacija | Ishod |
|---|---|
| stari kod + stara šema | 1 email |
| stari kod + nova šema | 1 email (nove tabele se ne čitaju) |
| nov kod + nova šema | 1 email |
| nov kod + stara šema | 0 emailova, posao CRVEN („Migracija 142 nije primenjena“) |
| isti dan: stari pa nov | 1 email (nov kod čita stari dnevnik) |
| isti dan: nov pa stari | **2 emaila** (stari kod ne zna za nove rezervacije) |
| istovremeno stari i nov | **2 emaila** |
| nov danas, stari sutra (vraćanje posle slanja) | bez duplikata |

**Okidači slanja podsetnika u STAROM kodu (`11475df8`, provereno čitanjem izvora 2026-10-28):**

| Okidač | Ko ga poziva | Stanje u produkciji |
|---|---|---|
| `POST /email-notif/send-reminders` | `email-cron.yml` (raspored `0 8 * * *`, stvarni početak 11–17 h UTC; i `workflow_dispatch`); ručno osnivačev JWT | radi od 24.10 (GitHub API) |
| `POST /api/cron/daily` (poziva `posalji_podsetnike`) | spoljni raspored (dokumentacija: Render cron 07:00 UTC, `X-Cron-Secret`) | `chain_anchors` = **0 redova** → nijedan run nije završen; da li je raspored uopšte podešen: UNKNOWN (Render dashboard) |
| petlja u procesu | — | NE postoji u starom kodu (nema je pre ove grane) |

`VINDEX_EMAIL_PODSETNICI_PAUZA` postoji SAMO u novom kodu — stari kod je ignoriše, pa pauza nije zaštita prelaza.
`email_notif_log` = 0 redova: stari kod rezerviše pre slanja, dakle do sada nije poslao nijedan podsetnik.

Zato se prelaz ne oslanja na čekanje cron-a, nego na **gašenje okidača starog koda**:
1. Primeniti 142 (§2).
2. GitHub → Actions → „Email Podsetnici za rokove“ → **Disable workflow**; potvrditi da nema run-a `queued`/`in_progress`.
3. Render → Cron Jobs: ako postoji posao koji zove `/api/cron/daily`, **Suspend**. Ako ne postoji — zabeležiti (zatvara UNKNOWN).
4. Ne pokretati ručno `send-reminders` ni `/api/cron/daily`.
   Od ovog trenutka stari kod nema nijedan okidač slanja podsetnika → ne može da pošalje (ni tokom preklapanja instanci pri deploy-u).
5. Pustiti kod (spajanje u `main` → automatski deploy). Sačekati `/health` → `commit` = nov SHA (stara instanca ugašena).
6. Smoke (§6).
7. Vratiti okidače: **Enable workflow** (i Resume Render posla, ako je bio suspendovan). Sledeći run služi nov kod.
   Ako je stari kod danas već poslao: „stari pa nov“ = bez duplikata (matrica).

Kad se okidači ne mogu ugasiti: puštati tek kad današnji `email-cron.yml` run ima `completed` (stari postupak) — slabije, jer ne
pokriva `/api/cron/daily` čiji raspored nije poznat.

## 4. Prelaz i stara istorija

- Nov kod stari dnevnik samo ČITA: stari red pokriva događaj izvršiv pre starog slanja; kasnije izvršiv nije pokriven; nepoznato
  vreme → NIJE pokriveno (bez tihog gašenja; najviše jedan suvišan podsetnik). U produkciji je `email_notif_log` prazan.
- Nov kod ne piše `email_notif_log` (nedeljni pregled ga i dalje piše za `dana_pre = 0`).
- Prvo slanje posle puštanja može poslati **dodatni** podsetnik za događaje kojima najkasniji uključen prag nikad nije poslat
  (npr. rok za danas/sutra) — to je D2, ograničeno na događaje u prozoru najkasnijeg praga.

## 5. Pozadinski poslovi novog koda

- Hitna provera posle radnje: pozadinski zadatak rute + trajna posledica `email_podsetnik_hitno` (red `events`).
- Periodična hitna provera na 10 min (startup petlja u `api.py`). Podrazumevano radi SAMO kad postoji env `RENDER`
  (Render ga postavlja sam); lokalno je isključena. Izričito: `VINDEX_PODSETNICI_PETLJA=1` / `=0`. Smoke: u logu
  „[EMAIL-HITNO] periodična provera pokrenuta“ posle deploy-a — ako ga nema, postaviti `VINDEX_PODSETNICI_PETLJA=1`.
- Sigurno nepredata poruka: najviše 6 pokušaja, razmak 10 · 2^(k−1) min (10, 20, 40, 80, 160) — pokriva ~5 h prekida
  SMTP-a; posle toga vidljiva greška u dnevnom poslu.
- Svi koriste isti ključ rezervacije → bez duplikata i kod više procesa (`/health` workers=1).

## 6. Smoke posle puštanja (samo čitanje + jedan kontrolisan test)

1. `/health` → 200, workers=1.
2. GitHub Actions: sledeći `email-cron.yml` run → `JOB_EXECUTED`/`SMTP_ACCEPTED`, bez `JOB_FAILED`.
3. `SELECT stanje, count(*) FROM email_podsetnik_dogadjaj GROUP BY 1;` — nema `nepoznato`/`odbijeno` bez objašnjenja.
4. **Kontrolisan email test** (tek uz odobrenog test primaoca i sintetički nalog): profil test naloga → sintetički predmet →
   ročište DANAS u 23:59 → očekivan jedan email „Podsetnik: ročište uskoro“ u test sanduče, red `kasni/poslato`. Bez odobrenja:
   `LIVE_EMAIL_DELIVERY_NOT_VERIFIED`.

## 7. Period posmatranja (7 dana)

Dnevno: ishod `email-cron.yml`; `zaostalo_nepoznato`, `greske` u odgovoru; `email_podsetnik_dogadjaj` po stanjima;
broj događaja `events` u dead-letter-u za `rociste_zakazano` / `ManualCorrectionApplied`.

## 8. Oporavak — nedestruktivno (NIKAD DROP posle stvarnih zapisa)

| Situacija | Radnja |
|---|---|
| Sumnja na pogrešno slanje | Render env `VINDEX_EMAIL_PODSETNICI_PAUZA=1` (redeploy env-a): dnevno slanje i hitne provere ne šalju; dnevni posao CRVEN „pauzirani“ (oznaka dnevnog slanja se i tada upisuje). Istorija ostaje. Posle ukidanja periodična provera (≤10 min) šalje i današnji prag i dodatne podsetnike. |
| Vraćanje koda | Tek POSLE današnjeg dnevnog slanja (ili sutra pre njega). Stari kod ignoriše nove tabele; vraćanje istog dana posle slanja novog koda = mogući 1 duplikat po predmetu/datumu/pragu. Tabele OSTAJU. |
| `nepoznato` / zaglavljeno `rezervisano` | Ne ponavlja se automatski (D4); dnevni posao ga prijavi jednom (`zaostalo_nepoznato`). Operater proverava kod provajdera da li je poruka otišla. |
| Odustajanje od 142 | Samo ako nijedan zapis ne postoji — zaštićen blok `[ODUSTAJANJE]` u migraciji (zaključava tabele i odbija brisanje čim postoji zapis). |
| Nepovratno | Poslat email se ne može povući; `poslato` = SMTP prihvatio, ne prijem u sanduče. |

## 9. Kriterijumi za prekid puštanja

- 142 nije primenjena ili prava nisu kao u §2.
- PR #58 / stacked PR CI nije zelen.
- Dnevni posao posle puštanja CRVEN zbog `greske` (osim namerne pauze) ili `neisporuceno` > 0 bez objašnjenja.
- Bilo kakav email primaocu koji nije vlasnik profila.

## 10. Ostale zavisnosti istog kandidata

- **Ključ keša odgovora** `_CACHE_VERZIJA = 2026-10-28-s3`: posle deploy-a svi keširani pravni odgovori se jednom ponovo računaju
  (privremeno veći trošak OpenAI/Pinecone poziva, jednokratno).
- **Pravni korpus** (Pinecone, produkcija): KZ je zaključno sa 94/2024 — izmena **63/2026** (čl. 55a, primena od 18.07.2026) i
  Zakon o uređenju sudova (10/2023) i Zakon o sedištima i područjima sudova (101/2013, 9/2026, 56/2026) NISU u bazi. Kod ih
  pokriva determinističkim, proverenim tekstom (čl. 55a, stvarna nadležnost, napomena o 1.3.2027) i označava stari tekst čl. 55a.
  Ažuriranje korpusa = poseban, odobren upis u Pinecone (nije deo ovog puštanja).
- **`ai_cache` red iz incidenta** — plan čišćenja (NE izvršen):
  ```sql
  BEGIN;
  -- preduslov: tačno jedan red, ključ prefiksa 3a2eb061, upisan 2026-10-27 00:32:36Z (sintetičko pitanje M1, bez podataka klijenta)
  SELECT count(*) FROM public.ai_cache
   WHERE cache_key LIKE '3a2eb061%' AND created_at = '2026-10-27 00:32:36.051401+00';      -- očekivano: 1
  DELETE FROM public.ai_cache
   WHERE cache_key LIKE '3a2eb061%' AND created_at = '2026-10-27 00:32:36.051401+00'
  RETURNING left(cache_key, 8), created_at;                                                -- očekivano: 1 red
  -- ako nije tačno 1 red: ROLLBACK;
  COMMIT;
  SELECT count(*) FROM public.ai_cache WHERE cache_key LIKE '3a2eb061%';                    -- očekivano: 0
  ```
  Red je logički istekao posle `expires_at` 2026-11-03 00:32Z (čitanje filtrira), ali se fizički ne briše sam. Sadržaj je
  sintetički; povraćaj nije potreban (ponovo bi se izračunao na isto pitanje). Brisanje izvršava osnivač kroz uobičajeni
  administratorski tok i beleži ga u ledger.

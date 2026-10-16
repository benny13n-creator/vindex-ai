# VINDEX NIGHT SPRINT — ACTUAL RESULTS
## Operation Canonical Continuity · Deadlines → Alerts · 2026-10-17

**Završni status: `LOCAL_SPRINT_COMPLETE_RELEASE_HOLD`**

Svih 10 misija je lokalno, redom i dokazivo zatvoreno. Ništa nije pushovano, spojeno ni pušteno; produkcija i GitHub tajne nisu dirani; nijedan email ni SMS nije poslat; nijedan cron nije pokrenut. Email podsetnici u produkciji i dalje NE rade dok osnivač ne uskladi ključ, ne potvrdi SMTP i ne spoji ove izmene — ovaj sprint NE dokazuje isporuku (`CODE_VERIFIED / PRODUCTION_UNVERIFIED`).

- Baza: `d2f8d7d94bd328dde21711b9728e7e970ed0e881` (= `origin/main` pri `git fetch`, PR #44)
- Grana: `night/deadlines-alerts-vcr002` (lokalna, bez upstream-a), worktree `C:/vindex-qa/alerts`

## 1. Executive verdict

Dokazani prekid „potvrđen rok → podsetnik“ imao je, pored neusklađenog ključa (konfiguracija, osnivač), i četiri kodna defekta koji bi i POSLE usklađivanja ključa prikazivali neuspeh kao uspeh ili slali pogrešno. Sva četiri su lokalno ispravljena uz RED→GREEN i mutacije:

1. **Lažno zelen cron** — workflow je gledao samo HTTP kod; 200 sa `greske`/`neisporuceno`, nevalidan JSON, nenumerički kod bili su zeleni, a prazan ključ je slat serveru.
2. **Nevidljiv / potrošen podsetnik** — aktivan profil bez adrese preskakan bez traga; bez SMTP-a rezervacija upisana pa slanje palo → podsetnik trajno „potrošen“ i pogrešno označen kao nepoznat ishod.
3. **Fail-open za predmet u brisanju** — bilo koja greška upita prelazila je na rezervni upit bez `brisanje_zapoceto` → podsetnik za predmet u brisanju.
4. **Nekonzistentan oblik odgovora** bez profila.

SMS automatsko pokretanje je lokalno isključeno (svakodnevni 401, provider nepotvrđen).

## 2. T01–T10 status matrica

| Task | Status | Tests (stvarno izvršeno) | Commit | Evidence |
|---|---|---|---|---|
| T01 | ACCEPTED_VERIFIED | 35 pass / 0 fail (postojeći scope) | — | git: baza tačna, worktree čist, bez upstream-a |
| T02 | ACCEPTED_VERIFIED | — (Code) | — | ugovor iz svih `return`/izuzetaka u `_run`; lažno zeleno dokazano iz teksta workflow-a |
| T03 | ACCEPTED_VERIFIED (dijagnoza) | 21 RED / 10 GREEN na originalu (posle UTF-8 popravke harness-a: 23 RED / 13 GREEN) | — | stvarni `run` korak, lažni curl |
| T04 | ACCEPTED_VERIFIED (LOCAL_TEST_ONLY za runner) | 36 + 5 pass / 0 fail; 6 mutacija uhvaćeno | `59cdb9a6` | `bash -n`, `ast.parse`, `yaml.safe_load` |
| T05 | ACCEPTED_VERIFIED | RED 1 → 4 pass; potrošači 31 pass | `c8fea6fa` | stvarni endpoint + FakeBaza |
| T06 | ACCEPTED_VERIFIED | RED 2 → 77 pass (9 fajlova); 3 mutacije uhvaćene | `5a828e63` | `smtplib.SMTP` puca ako se konstruiše |
| T07 | ACCEPTED_VERIFIED | RED 5 → 87 pass; 1 mutacija uhvaćena | `24b0c8b7` | baza projektuje kolone kao PostgREST |
| T08 | ACCEPTED_VERIFIED (lokalno) | RED 2 → 6 pass; 1 mutacija uhvaćena | `78e3b389` | YAML okidači; `routers/sms.py` diff prazan |
| T09 | ACCEPTED_VERIFIED (kod); produkcija UNKNOWN | NOT_RUN (bez izmene) | — | runbook iz koda (§7) |
| T10 | ACCEPTED_VERIFIED | integracija 8 pass (na bazi 5 RED); regresija 534 pass / 0 fail (26 fajlova); `import api` OK | `fa72920c` + ovaj izveštaj | vidi §4–§5 |

## 3. Šta je zaista popravljeno / samo provereno / već radi / ne radi

**Popravljeno (lokalno, nije u produkciji):** validacija rezultata email cron-a (T04); oblik odgovora (T05); profil bez adrese i nekonfigurisan SMTP više nisu nevidljivi niti troše rezervaciju (T06); fail-closed provera predmeta u brisanju (T07); SMS bez zakazanog pokretanja (T08).

**Samo provereno:** ugovor odgovora i semantika brojača (T02); opt-in put u `/app-legacy` (T09, iz koda, ne u pregledaču); zavisnosti SMTP konfiguracije (T09).

**Dokazano da već radi (NO_CHANGE potrebna):** X-Cron-Key autorizacija i 403 za pogrešan/prazan ključ; non-2xx i timeout su već bili crveni; rezervacija pre slanja i bez duplikata (b10, vcr002, integracija); nepotvrđen AI rok ne šalje; zatvoren/arhiviran/odbijen ne šalje; bez opt-in nema primaoca; tuđi predmet ne ulazi u email.

**I dalje ne radi (produkcija):** email cron dobija 403 svaki dan (ključ); SMS cron dobija 401 svaki dan (do spajanja T08); 0 aktivnih email profila prema početnom dokazu (nije ponovo provereno); V2 nema opt-in.

**Nije testirano:** stvarni GitHub runner (zahteva push); stvarni SMTP; prijem u sanduče; produkcioni Supabase/PostgREST; stvarni beta korisnik; ponašanje `/app-legacy` u pregledaču.

**Zahteva osnivača:** §7 runbook (ključ, SMTP, opt-in, test, potvrda prijema), odluka o spajanju, odluka o SMS-u, odluka o `/api/cron/daily` nalazu.

**Zahteva stvarnog beta korisnika:** uključivanje u `/app-legacy`, pristanak na test email, potvrda prijema, potvrda jednog stvarnog roka (Wave 4 W4-B-3).

**Preporučeni sledeći produkcioni korak:** Draft PR iz `night/deadlines-alerts-vcr002` → `main` (traži novo odobrenje), CI poređenje sa baseline-om, pa spajanje; tek posle toga runbook koraci 1–2.

## 4. RED → GREEN (stvarno menjan kod)

| Izmena | RED na bazi | GREEN posle | Mutacije |
|---|---|---|---|
| email-cron.yml | 23 od 36 slučajeva lažno/nepotpuno (npr. `200 {"neisporuceno":1}` → exit 0; `HTTP 204x` → exit 0; prazan ključ → HTTP poslat) | 36/36 | 6/6 uhvaćeno (HTTP mutacija prvo preživela → dodat test „ne-2xx sa validnim telom“) |
| odgovor bez profila | 1 RED | 4/4 | — |
| bez adrese / bez SMTP | 2 RED | 9/9 (+68 postojećih) | 3/3 |
| predmet u brisanju pri grešci | 5 RED (podsetnik POSLAT) | 13/13 | 1/1 |
| sms-cron.yml | 2 RED | 3/3 | 1/1 |
| lanac kraj-do-kraja | 5/8 RED | 8/8 | — |

## 5. Adversarial nalazi

| Tvrdnja | Opovrgnuta? | Dokaz |
|---|---|---|
| „Cron je zelen, dakle email je isporučen.“ | DA | zeleno = najviše `SMTP_ACCEPTED / INBOX_UNCONFIRMED`; `NO_RECIPIENTS` i `JOB_EXECUTED` zeleni bez slanja (contract + integracija) |
| „HTTP 200 znači da nije bilo grešaka.“ | DA | ruta vraća 200 sa `greske=1`/`neisporuceno=1` (api_shape, integracija) |
| „SMTP accepted znači inbox delivered.“ | DA | `poslato` = `sendmail` bez izuzetka; nijedan mehanizam ne potvrđuje prijem (kod `_smtp_send`) |
| „Jednom rezervisan podsetnik sme bezbedno da se ponovi.“ | DA | ponavljanje bi duplo slalo ako je prvi pokušaj stigao; rezervacija ga blokira (b10 r4, integracija dedup) |
| „Nepotvrđen AI rok je dovoljno pouzdan za slanje.“ | DA | `_filtriraj_izvrsive` + `_potvrdjeni_ids` (eligibility, integracija, faza62) |
| „SMS je bezbedan za aktivaciju jer postoji aktivan profil.“ | DA | ruta prima samo osnivačev JWT (401 svaki dan); provider nepotvrđen; T08 |
| „Svaka DB greška može da pređe na slabiji fallback.“ | DA | 4 vrste grešaka su slale za predmet u brisanju (T07 RED) |
| „Ako nijedan test ne pada, produkcioni provider je ispravan.“ | DA | svi testovi zamenjuju SMTP; produkcioni SMTP/ključ UNKNOWN (T09) |

**Nalazi van scope-a (dokumentovani, NISU menjani):**
- `api.py::cron_daily` (`/api/cron/daily`, tajna `BRIEFING_CRON_SECRET`) poziva istu funkciju i upisuje `"status":"ok"` i kada su `greske`/`neisporuceno` > 0 — drugi lažno-zeleni put. Da li ga Render Cron poziva: UNKNOWN.
- Stari UI za korisnika bez profila prikazuje „⚠ Email server nije konfigurisan“ i kada jeste (GET profil bez reda ne vraća `smtp_ok`) — lažno crveno.
- Podsetnik ide na `profiles.email`, test email na adresu iz prijave — mogu se razlikovati.
- Neaktivan `email-cron.yml` u korenu repoa (van `.github/workflows`).

## 6. Preostali blokeri

1. GitHub `CRON_TOKEN` ≠ Render `CRON_SECRET` → 403 (konfiguracija, osnivač).
2. SMTP konfiguracija u produkciji: UNKNOWN.
3. 0 aktivnih email profila (početni dokaz, nije ponovo proveren); V2 nema opt-in.
4. Izmene nisu spojene — u produkciji i dalje važe stari workflow i stari kod.

## 7. Operativni koraci rezervisani za osnivača — runbook — aktivacija email podsetnika (sve korake radi osnivač; svaki je FOUNDER-ONLY)

Preduslov: izmene iz ovog sprinta su spojene i puštene (do tada cron ostaje stari, a T06/T07 zaštite ne važe u produkciji).

1. **Uskladi cron ključ (bez ispisivanja vrednosti nigde).**
   - Render → servis → Environment: proveri da li postoji `CRON_SECRET` (samo da postoji i da nije prazan; vrednost ne kopiraj u chat, tikete ni logove).
   - Ako postoji: GitHub → repo → Settings → Secrets and variables → Actions → `CRON_TOKEN` → Update → nalepi ISTU vrednost. Render se ne dira (najmanji zahvat; `CRON_SECRET` čita i `routers/whatsapp_notif.py`).
   - Ako ne postoji ili je prazan: lokalno napravi novu vrednost (npr. `python -c "import secrets;print(secrets.token_urlsafe(48))"`), upiši je u Render `CRON_SECRET` (Render restartuje servis — kod čita vrednost pri pokretanju) i u GitHub `CRON_TOKEN`.
   - Provera: GitHub → Actions → „Email Podsetnici za rokove“ → Run workflow (ručno, jednom). Očekivano: `HTTP 200` i jedna od linija `NO_RECIPIENTS` / `JOB_EXECUTED` / `SMTP_ACCEPTED / INBOX_UNCONFIRMED`. `HTTP 403` = ključ i dalje nije usklađen. Ovo pokretanje MOŽE poslati stvarne podsetnike ako postoje aktivni profili sa dospelim potvrđenim rokom — pokreni ga tek kada si spreman za to.
2. **Proveri SMTP konfiguraciju (bez slanja).**
   - Render → Environment: postoje i nisu prazni `EMAIL_SMTP_HOST`, `EMAIL_SMTP_USER`, `EMAIL_SMTP_PASS`, `EMAIL_FROM` (opciono, inače se koristi USER); `EMAIL_SMTP_PORT` (podrazumevano 587, STARTTLS).
   - Kod: `_smtp_send` koristi `smtplib.SMTP(host, port)` + `starttls()` + `login()`; bez `EMAIL_SMTP_HOST` aktivacija profila vraća 503, a cron (posle ovog sprinta) broji `greske` bez rezervacije.
   - Napomena: u starom interfejsu korisnik BEZ profila vidi „⚠ Email server nije konfigurisan“ čak i kada jeste (GET `/email-notif/profil` ne vraća `smtp_ok` kada red ne postoji) — to upozorenje tada nije dokaz.
3. **Korisnik uključuje email obaveštenja (postojeći interfejs).**
   - V2 (`/app`) NEMA ovo podešavanje. Korisnik otvara `https://vindex.rs/app-legacy` → kartica „Podešavanja“ → odeljak email obaveštenja → štiklira 7/3/1 dan → „Aktiviraj“ (POST `/email-notif/profil`). Put je potvrđen čitanjem koda (`settingsLoad` → `emailNotifLoad`), NIJE proveren u pregledaču.
   - Podsetnik ide na `profiles.email` tog korisnika (ne na adresu iz prijave). Da li je `profiles.email` popunjen za beta korisnike: UNKNOWN.
4. **Jedan kontrolisani test email — samo uz pristanak primaoca.**
   - Primalac (sam, prijavljen) u istom odeljku klikne „Pošalji test“ (POST `/email-notif/test`, 3/min). Šalje se na adresu iz prijave, ne na `profiles.email`.
   - `{"ok":true}` = SMTP je prihvatio poruku (SMTP_ACCEPTED). To NIJE prijem.
5. **Potvrda prijema u stvarno sanduče.**
   - Primalac potvrdi da je poruka „Vindex AI — Test email notifikacija“ stigla (Inbox ili Spam — zabeležiti gde). Bez te potvrde status ostaje INBOX_UNCONFIRMED.
6. **Jedan stvarno potvrđen rok, bez duplikata.**
   - Na pilot predmetu primaoca postoji rok sa datumom tačno sutra (ili za 3/7 dana, prema štikliranim danima), potvrđen u V2 „Danas“ (Potvrdi). Nepotvrđen AI rok namerno NE šalje.
   - Narednog zakazanog izvršavanja (08:00 UTC): u GitHub Actions očekuj `SMTP_ACCEPTED / INBOX_UNCONFIRMED: ... 1 poruka`; primalac potvrđuje prijem.
   - Duplikat: ručno pokretanje istog dana mora dati `poslato=0` i `preskoceno>=0` (rezervacija u `email_notif_log` po korisnik/predmet/datum/dan), a primalac ne sme dobiti drugi email.
7. **Kada isporuka nije potvrđena.**
   - `DELIVERY_UNCONFIRMED` (neisporuceno>0): NE pokretati ponovo — rezervacija sprečava ponovno slanje, a ishod je nepoznat (poruka je možda otišla). Proveriti Render logove (`[EMAIL-CRON] NEISPORUČENO`, samo skraćen uid) i SMTP provajder, pa javiti advokatu rok direktno.
   - `JOB_FAILED` sa `greske`: ništa nije poslato za te slučajeve (nema adrese / SMTP nije konfigurisan / pad provere predmeta ili rezervacije) — ispraviti uzrok; podsetnik za isti dan se može poslati ponovnim pokretanjem jer rezervacija nije upisana.
   - Isporuka bez potvrde primaoca ostaje UNKNOWN — ne smatrati podsetnik poslatim advokatu.

## 8. Precizan release scope

Commit-i (lokalni, redom): `59cdb9a6` (T04), `c8fea6fa` (T05), `5a828e63` (T06), `24b0c8b7` (T07), `78e3b389` (T08), `fa72920c` (T10 integracija), + commit ovog izveštaja.
Fajlovi: `.github/workflows/email-cron.yml`, `.github/workflows/sms-cron.yml`, `routers/email_notif.py`, 5 novih `tests/test_alerts_*.py`, harness izmene u `tests/test_b10_reminder_claim.py`, `tests/test_faza62_gate_e2e_paths.py`, `tests/test_lz001_reminder_vocabulary.py`, `tests/test_vcr002_t04_podsetnici.py` (samo modelovanje konfigurisanog SMTP hosta; nijedna tvrdnja nije menjana), ovaj izveštaj.
Nema migracija, nema promene autorizacije, RLS-a, tenant izolacije, UI-ja ni novih kanala.

## 9. Non-goals i odložene odluke

Van ovog sprinta: opt-in u V2 (novi UI), autorizacija SMS rute cron ključem, Twilio, `/api/cron/daily` status, `smtp_ok` u GET profil bez reda, potvrda prijema (bounce/DSN), exactly-once isporuka (namerno nije cilj — at-most-once pokušaj).

## 10. Preporuka

**GO za predaju na review** (Draft PR, uz novo odobrenje). **HOLD za puštanje** dok osnivač ne odobri spajanje i ne izvrši §7 korake 1–2; isporuka ostaje `INBOX_UNCONFIRMED` dok stvarni korisnik ne potvrdi prijem.


## Prilog A — Evidence ledger (po misiji) — night/deadlines-alerts-vcr002

| Polje | T01 |
|---|---|
| Starting SHA | d2f8d7d94bd328dde21711b9728e7e970ed0e881 (`git fetch origin main` → identičan) |
| Files examined | git worktree list; tests/ (scope) |
| Files changed | none |
| Claim | Izolovan radni prostor na tačnoj bazi |
| Evidence type | runtime (git) |
| Falsification attempted | provera: ne postoji lokalna/remote grana istog imena; novi worktree `C:/vindex-qa/alerts`; `git status` 0 linija; bez upstream-a (push ne može slučajno); `int-beta` i dalje samo 2 nekomitovana dijagnostička fajla |
| Result | PASS |
| Tests passed | 35 (postojeći: wave4_preflight_b, vcr002_t04, b10_reminder_claim, omega007_sms_dedup, lz001) |
| Tests failed | 0 |
| Tests not run | ostalih ~14 fajlova koji pominju email_notif (pokreću se u T10 ako ih izmene dodirnu) |
| Invariants | sačuvane; nijedna produkciona operacija |
| Status | ACCEPTED_VERIFIED |
| Next mission allowed | YES |

## T02 — Email delivery contract & failure model

Postojeći oblici odgovora `POST /email-notif/send-reminders` (routers/email_notif.py:271-405, d2f8d7d9):
- A. nema aktivnih profila → `{"poslato":0,"greske":0,"napomena":"Nema aktivnih profila"}` (NEMA `preskoceno`/`neisporuceno`)
- B. uobičajeno → `{"poslato":int,"greske":int,"preskoceno":int,"neisporuceno":int}`
- C. izuzetak u upitima (profiles, dup, rokovi, fallback predmeti) → HTTP 500
- D. auth → 403 (`_require_cron_or_founder`); rate limit → 429

Semantika brojača (iz koda): `poslato` = SMTP `sendmail` vratio bez izuzetka (SMTP_ACCEPTED, ne inbox); `greske` = rezervacija nije uspela iz ne-duplikat razloga (ništa nije poslato); `preskoceno` = rezervacija već postoji (23505); `neisporuceno` = rezervacija upisana, SMTP bacio izuzetak (ishod nepoznat, bez automatskog ponavljanja).

Ugovor za workflow (klasifikacija, ne nova arhitektura):
| Uslov | Klasa | Job |
|---|---|---|
| prazan ključ | JOB_FAILED (pre HTTP) | fail |
| transport/timeout (curl ≠ 0) | JOB_FAILED | fail |
| HTTP ≠ 2xx | JOB_FAILED | fail |
| telo nije JSON objekat / prazno | JOB_FAILED | fail |
| neko od 4 polja nedostaje ili nije nenegativan ceo broj (bool odbijen) | JOB_FAILED | fail |
| greske > 0 | JOB_FAILED | fail |
| neisporuceno > 0 | DELIVERY_UNCONFIRMED | fail (ručna provera, bez ponavljanja) |
| sva 4 = 0 i napomena „Nema aktivnih profila“ | NO_RECIPIENTS | success, bez tvrdnje o isporuci |
| poslato > 0, greske=0, neisporuceno=0 | SMTP_ACCEPTED (INBOX_UNCONFIRMED) | success |
| sve 0 bez napomene | JOB_EXECUTED (0 poslato) | success |

Dokazana lažno-zelena putanja (iz koda workflow-a): proverava samo `http_code` 200-299 → `200 {"neisporuceno":1,...}` i `200 {"greske":1,...}` i `200` sa nevalidnim/praznim telom završavaju `exit 0`.
Dodatno iz koda servisa (za T05/T06): oblik A nema 2 polja; profil bez adrese → `continue` bez brojača; SMTP nekonfigurisan → rezervacija se upisuje PA `RuntimeError` → `neisporuceno` (poznat ne-pokušaj klasifikovan kao nepoznat, podsetnik trajno „potrošen“).

Najmanja ispravka: workflow validira telo po tabeli (T04); API oblik A dobija `preskoceno:0, neisporuceno:0` (T05).

| Polje | T02 |
|---|---|
| Starting SHA | d2f8d7d9 |
| Files examined | routers/email_notif.py, .github/workflows/email-cron.yml, tests/test_wave4_preflight_b_email_cron_auth.py |
| Files changed | none |
| Evidence type | Code |
| Falsification attempted | traženi svi `return` u `_run` i svi izuzeci; lažno zeleno potvrđeno na tekstu workflow-a (reprodukcija u T03) |
| Tests passed / failed / not run | 0 / 0 / reprodukcija u T03 |
| Status | ACCEPTED_VERIFIED |
| Next mission allowed | YES |

## T03 — RED testovi za lažno zelen cron

| Polje | T03 |
|---|---|
| Starting SHA | d2f8d7d9 (radni prostor, workflow neizmenjen) |
| Files examined | .github/workflows/email-cron.yml |
| Files changed | tests/test_alerts_email_cron_contract.py (nov, 31 slučaj) |
| Claim | Stvarni `run` korak prijavljuje uspeh za neuspešne ishode |
| Evidence type | deterministic test (stvarni YAML korak, `bash --noprofile --norc -eo pipefail`, lažni `curl` prvi na PATH-u — 0 mrežnih poziva) |
| Falsification attempted | 15 lažno-zelenih tela na HTTP 200, 6 HTTP kodova, timeout, prazan/razmak ključ, provera da nema ponovnog poziva |
| Result | **21 RED / 10 GREEN** (očekivani eksperiment, exit ≠ 0 pytest-a). RED defekti: greske>0 (2), neisporuceno>0 (2), nevalidan/prazan/niz/null JSON (4), nedostajući/nevalidni brojači (7), prazan ključ i ključ od razmaka šalju HTTP (2), neisporuceno test (1). RED samo zbog nedostajuće klasifikacije u izlazu (3: uspeh, NO_RECIPIENTS, JOB_EXECUTED — izlaz koda je već 0). GREEN već danas: 403/401/429/500/502/302, timeout (curl≠0 pod `-e`), X-Cron-Key + bez ispisa tajne, preskoceno, bez retry-ja |
| Tests passed | 10 |
| Tests failed | 21 (očekivani RED) |
| Tests not run | none |
| Invariants | nijedan stvaran HTTP; sintetički ključ `test-kljuc-7f3a9c` |
| Status | ACCEPTED_VERIFIED (dijagnoza; NIJE popravka) |
| Next mission allowed | YES |

## T04 — Ispravka validacije email cron rezultata

| Polje | T04 |
|---|---|
| Starting SHA | d2f8d7d9 |
| Files examined | .github/workflows/email-cron.yml, tests/test_wave4_preflight_b_email_cron_auth.py |
| Files changed | .github/workflows/email-cron.yml; tests/test_alerts_email_cron_contract.py |
| Commit | `59cdb9a6` (lokalno) |
| Claim | Nijedan neuspešan/nepoznat/nevalidan ishod nije zelen; X-Cron-Key protokol nepromenjen |
| Evidence type | deterministic test (stvarni YAML korak) + `bash -n` + `ast.parse` + `yaml.safe_load` |
| Falsification attempted | 6 mutacija workflow-a (ukloni greske / neisporuceno / proveru ključa; `isinstance` umesto `type is int`; HTTP regex `^[0-9]+$`; NO_RECIPIENTS uvek) — sve uhvaćene (2/3/2/1/3/1 pada). Mutacija HTTP-a je prvo PREŽIVELA (telo `{"detail"}` je padalo na JSON ugovoru) → dodat test „ne-2xx sa validnim telom“ (5 slučajeva), posle toga uhvaćena. Harness izmenjen posle RED-a (UTF-8 dekodiranje) → original ponovo pušten: 23 RED / 13 GREEN (dva nova RED-a: HTTP kod `204x` i prazan kod → original `exit 0`) |
| Result | GREEN |
| Tests passed | 36 (contract) + 5 (wave4_preflight_b, nepromenjen) |
| Tests failed | 0 |
| Tests not run | stvarni GitHub runner (NOT_RUN — zahtevao bi push) |
| Invariants | autorizacija nepromenjena (isti header, ista tajna); bez retry-ja, bez `continue-on-error`, bez `|| true`; tajna nije u izlazu (test) |
| Status | ACCEPTED_VERIFIED (LOCAL_TEST_ONLY za GitHub runner) |
| Next mission allowed | YES |
| Napomena za T05 | strogi ugovor odbija stari oblik „Nema aktivnih profila“ (bez `preskoceno`/`neisporuceno`) → do T05 bi takav dan bio CRVEN (fail-closed, ne lažno zelen) |

## T05 — Usklađen oblik API odgovora

| Polje | T05 |
|---|---|
| Starting SHA | 59cdb9a6 |
| Files examined | routers/email_notif.py (svi `return` u `_run`), api.py `/api/cron/daily` (drugi potrošač) |
| Files changed | routers/email_notif.py (+3/-1); tests/test_alerts_email_api_shape.py (nov, 4) |
| Commit | vidi git log (T05) |
| Claim | Svaki odgovor ima 4 nenegativna cela brojača; značenje nepromenjeno |
| Evidence type | deterministic test (stvarni endpoint, FakeBaza, SMTP zamenjen) |
| Falsification attempted | RED pre izmene: 1 pad (oblik bez profila: nema `preskoceno`/`neisporuceno`); SMTP pad → neisporuceno=1 (ne poslato); pad rezervacije → greske=1 bez slanja |
| Result | GREEN 4/4; potrošači b10 + vcr002_t04 + cron_daily_dispatcher prolaze |
| Tests passed | 35 (4 nova + 31 postojećih) |
| Tests failed | 0 |
| Tests not run | none u scope-u |
| Invariants | brojači i napomena nepromenjeni; samo dodata dva nulta polja |
| Nalaz (dokumentovan, NIJE menjan) | `api.py::cron_daily` (`/api/cron/daily`) poziva istu funkciju i upisuje `"status":"ok"` i kad je greske/neisporuceno > 0 — drugi lažno-zeleni put. Da li ga Render Cron poziva: UNKNOWN (konfiguracija nije u repou). Van liste komponenti ove misije → odluka osnivača. Takođe: neaktivan `email-cron.yml` u korenu repoa (nije u `.github/workflows`, ne izvršava se). |
| Status | ACCEPTED_VERIFIED |
| Next mission allowed | YES |

## T06 — Odgovornost za neuspeh isporuke

| # | Slučaj | Pre (d2f8d7d9) | Posle |
|---|---|---|---|
| 1 | aktivan profil, nema adrese | `continue` bez brojača — NEVIDLJIVO (RED) | greske+=1 samo ako ima dospeo potvrđen rok; bez rezervacije; log bez adrese |
| 2 | SMTP nije konfigurisan | rezervacija upisana → RuntimeError → `neisporuceno` — podsetnik trajno potrošen (RED) | greske+=1, rezervacija NIJE upisana, nema SMTP konekcije |
| 3 | SMTP odbija | `neisporuceno` (nepoznat, bez ponavljanja) | nepromenjeno — konzervativno |
| 4 | rezervacija uspe, SMTP padne | `neisporuceno`, rezervacija ostaje | nepromenjeno (test_smtp_pad_ostaje_nepotvrden, b10 r3) |
| 5 | rezervacija ne uspe | `greske`, bez slanja | nepromenjeno (test_pad_rezervacije, b10) |
| 6 | ponovni cron posle rezervacije | bez duplikata | nepromenjeno (b10 r2/r4/r5, vcr002) |

| Polje | T06 |
|---|---|
| Starting SHA | c8fea6fa |
| Files changed | routers/email_notif.py (+9/-2); tests/test_alerts_email_api_shape.py (+5 testova); harness-i b10/faza62/lz001/vcr002 (modeluju konfigurisan SMTP host) |
| Commit | `5a828e63` |
| Evidence type | deterministic test (stvarni endpoint; `smtplib.SMTP` puca ako se konstruiše) |
| Falsification attempted | RED pre izmene: 2 pada (slučajevi 1 i 2). 3 mutacije (bez provere hosta / bez provere adrese / bez brojača) — sve uhvaćene. Bez dospelog roka ni host ni adresa ne prave grešku (2 testa). PII: `@` i test adresa nisu u logu |
| Nalaz tokom rada | 18 postojećih testova u 4 fajla je palo jer menjaju `_smtp_send` a ne i `_SMTP_HOST` (test okruženje nema host = model „SMTP nije konfigurisan“). Ispravljen MODEL harness-a (presedan: test_recurring `_EMAIL_SMTP_HOST`), nijedna tvrdnja nije menjana |
| Tests passed | 77 (9 fajlova koji pozivaju funkciju) |
| Tests failed | 0 |
| Invariants | bez retry-ja; dedup nepromenjen; rezervacija pre slanja nepromenjena; bez PII |
| Semantika | `greske` sada obuhvata i „poznat razlog, ništa nije rezervisano ni poslato“ (ranije samo pad rezervacije) — isto značenje za cron: ništa nije poslato |
| Status | ACCEPTED_VERIFIED |
| Next mission allowed | YES |

## T07 — Fail-closed podobnost roka

| Polje | T07 |
|---|---|
| Starting SHA | 5a828e63 |
| Files examined | routers/email_notif.py (predmeti upit, rokovi upit, `_filtriraj_izvrsive`/`_potvrdjeni_ids`); grep istog obrasca u sms/notifications/morning_briefing — samo jedno mesto |
| Files changed | routers/email_notif.py (+10/-1); tests/test_alerts_email_eligibility.py (nov, 13) |
| Commit | vidi git log (T07) |
| Claim | Greška provere aktivnog stanja ne postaje dozvola |
| Evidence type | deterministic test; baza PROJEKTUJE kolone kao PostgREST (prva verzija harness-a projektovala u `select` pa je `.eq(user_id)` praznio rezultat — lažno „bezbedno“; ispravljeno da projektuje u `execute`) |
| Falsification attempted | RED pre izmene: 5 (reset/timeout/57014/PGRST301 → podsetnik POSLAT za predmet u brisanju; aktivan predmet: greška nevidljiva). Mutacija „uvek zatvori“ → uhvaćena (42703 kontrola). Kontrola: legitimna 42703 i dalje koristi rezervni upit |
| Invariants potvrđene testom | potvrđen rok šalje; nepotvrđen AI rok ne; zatvoren/arhiviran/odbijen ne; u brisanju ne (i pri grešci); bez opt-in ne; tuđi predmet ne |
| Tests passed | 87 (13 novih + 74 u 8 fajlova koji pozivaju funkciju) |
| Tests failed | 0 |
| Tests not run | QA-01 paket (namerno; dodirne tačke pokrivene) |
| Status | ACCEPTED_VERIFIED |
| Next mission allowed | YES |

## T08 — Bezbedno isključenje SMS cron-a

| Polje | T08 |
|---|---|
| Starting SHA | 24b0c8b7 |
| Files examined | .github/workflows/sms-cron.yml; routers/sms.py (`posalji_podsetnike`); svi workflow-i koji pominju `/sms/` |
| Files changed | .github/workflows/sms-cron.yml (uklonjen `schedule`, +komentar); tests/test_alerts_sms_cron_disabled.py (nov, 3) |
| Commit | `78e3b389` |
| Claim | Lokalno pripremljena izmena nema automatski SMS okidač; SMS ruta bez novog bypass-a |
| Evidence type | deterministic test (YAML okidači; `inspect` izvora rute) + `git diff` (routers/sms.py prazan) |
| Falsification attempted | original → 2 RED (schedule postoji); mutacija `push:` → 2 pada; provera svih workflow-a koji pominju `/sms/` |
| Tests passed | 6 (3 nova + 3 omega007 sms dedup) |
| Tests failed | 0 |
| Tests not run | ručni `workflow_dispatch` (zabranjeno) |
| Napomena | `/sms/status konfigurisan:false` je POČETNI dokaz iz brifa — u ovom sprintu NIJE ponovo proveren (UNKNOWN trenutno stanje). Izmena NE važi na GitHub-u dok osnivač ne spoji; produkcioni SMS cron i dalje radi po starom rasporedu (i pada sa 401). |
| Status | ACCEPTED_VERIFIED (lokalno) |
| Next mission allowed | YES |

## T09 — Opt-in i spremnost providera

| Polje | T09 |
|---|---|
| Starting SHA | 78e3b389 |
| Files examined | routers/email_notif.py (GET/POST/DELETE profil, test, `_smtp_send`, konstante), index.html (#email-notif-section), static/vindex.js (`settingsLoad`→`emailNotifLoad`, „Podešavanja“ tab), api.py (`/app-legacy`, `cron_daily` tajna, profiles upsert), routers/whatsapp_notif.py (`CRON_SECRET`), migrations/061 |
| Files changed | none (runbook u izveštaju) |
| Nalazi | (a) V2 nema opt-in; postoji samo u `/app-legacy` → Podešavanja (INFERRED iz koda, nije Playwright). (b) POST profil vraća 503 bez `EMAIL_SMTP_HOST` → bez SMTP-a niko ne može da se uključi. (c) GET profil bez reda ne vraća `smtp_ok` → stari UI tada prikazuje lažno „⚠ Email server nije konfigurisan“ (lažno crveno, nije menjano). (d) Podsetnik ide na `profiles.email`, test email na adresu iz JWT — mogu se razlikovati. (e) `CRON_SECRET` čita i whatsapp_notif → najmanji zahvat je GitHub `CRON_TOKEN` := postojeći Render `CRON_SECRET`. (f) `/api/cron/daily` koristi ZASEBNU tajnu `BRIEFING_CRON_SECRET`. (g) Bezbedna read-only potvrda prisustva SMTP/CRON konfiguracije iz ovog okruženja NE postoji (treba Render dashboard ili prijavljena sesija) → UNKNOWN |
| Evidence type | Code |
| Tests | NOT_RUN (nema izmene) |
| Status | ACCEPTED_VERIFIED (runbook = kod); produkcija UNKNOWN |
| Next mission allowed | YES |

## T10 — Integracija, adversarial, predaja

| Polje | T10 |
|---|---|
| Starting SHA | 78e3b389 |
| Files changed | tests/test_alerts_email_integration.py (nov, 8); docs/release/VINDEX_NIGHT_SPRINT_CANONICAL_ALERTS_REPORT.md |
| Commit | `fa72920c` + commit izveštaja |
| Evidence type | deterministic integration (stvarni workflow korak → TestClient → stvarna ruta i `_require_cron_or_founder` → JSON → workflow) |
| Falsification attempted | isti integracioni testovi na baznim verzijama workflow-a i `email_notif.py`: 5 RED / 3 GREEN (403, prazna serverska tajna, dedup su već radili) |
| Regresija | 26 fajlova (svi koji pominju email_notif / email-cron / sms-cron / routers.sms + 5 novih): **534 passed, 0 failed, 0 skipped** |
| Import | `import api` sa sintetičkim `FIELD_ENCRYPTION_KEY` (kao CI): OK; `/email-notif/send-reminders` i `/sms/send-reminders` registrovane. Prvi pokušaj bez ključa: rc=1 (startup zaštita, očekivano) |
| Tests not run | ceo pytest paket; QA-01/02/06, PR #42, Playwright, PostgREST (bez razloga izazvanog izmenama); stvarni GitHub runner; stvarni SMTP |
| Status | ACCEPTED_VERIFIED |

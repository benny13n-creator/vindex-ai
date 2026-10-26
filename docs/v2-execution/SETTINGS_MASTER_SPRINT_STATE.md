# Settings Master Sprint — izvršna evidencija

Grana `feature/v2-professional-settings` od `origin/main` `c4a698ae` (= produkcija `c4a698ae`, sw v163, 2026-10-25).
Ništa nije spojeno ni pušteno. Produkcioni status svih stavki: **PENDING** dok osnivač ne spoji i ne prođe smoke test.

| Task | Problem (dokazano) | Fajlovi | Commit | Testovi | Adversarial | Impl. | Prod. |
|---|---|---|---|---|---|---|---|
| P0.1–P0.4 | `POST /email-notif/test` je uvek slao šablon „Za 3 dana“ (`dana_pre=3`, routers/email_notif.py:258 na `c4a698ae`) | routers/email_notif.py, frontend-v2-ng/{index.html,src/podesavanja.js,tests/live-podesavanja.mjs}, tests/test_p0_b10_interval_correctness.py, tests/test_tenfronts_m10_primalac.py | `7b5b9a22` | novi: 49 passed; 30 B10 fajlova: 668 passed; V2: podesavanja 24/24, primary 51/51, api 49/49, send 100/100, session 38/38, isolation 25/25 | 5/5 mutacija ubijeno (hardkod 3, UTC dan, bool kao interval, bez provere uključenosti, bez oznake TEST) | VERIFIED | PENDING |
| P1.1 | Podešavanja su bila jedan B10 ekran bez strukture | frontend-v2-ng/{index.html,src/podesavanja.js,src/app.js,src/app.css} | `45fda1a6` | live-podesavanja-sekcije (6 odeljaka) 21/21: desktop, telefon, tastatura, osvežavanje, nepoznat odeljak | odeljak bez kontrolera se ne prikazuje (nema praznih kartica) | VERIFIED | PENDING |
| P1.2 | V2 nije imao nalog/plan/odjavu u podešavanjima | src/podesavanja-nalog.js | `45fda1a6` | p1 „Nalog“ 13 provera | ime za prikaz NIJE izloženo (V1 samo localStorage, nema serverske rute); lozinka → postojeći Supabase tok u klasičnom prikazu | VERIFIED | PENDING |
| P1.3 | Izvoz/brisanje/pravni dokumenti nedostupni u V2 | src/podesavanja-privatnost.js, src/api.js (GET preuzmi; PUT/DELETE samo na izričitim putanjama) | `a7d7b0e7` | p1 „Privatnost“ 14; live-send 100/100 (PUT/DELETE i dalje odbijeni drugde) | brisanje = anonimizacija (tačan opis servera; prijava se ne gasi); nijedno stvarno brisanje u testovima | VERIFIED | PENDING |
| P1.4 | SMS/WhatsApp: proizvodni `/sms/status` = `{"konfigurisan":false}`, sms-cron bez rasporeda | index.html (napomena) | `f5f0bbf4` | p1 2 provere (nema /sms ni /api/whatsapp poziva) | aktivacija se NE nudi | VERIFIED (bez kontrola) | PENDING |
| P1.5a | `routers/kancelarija.py`: `maybe_single()`→None ⇒ `/moja` 503 za sve osim admina, novi poziv 500, 403/404 kao 500 | routers/kancelarija.py, shared/audit_immutable.py | `ff7468f7` | tests/test_p1_kancelarija_podesavanja.py 38 (≥30 pada na starom kodu); srodni paketi 3123 passed | naziv i uloga sada u audit_immutable; IDOR nije postojao ni ranije | VERIFIED | PENDING |
| P1.5b | V2 nema upravljanje kancelarijom | src/podesavanja-kancelarija.js | `8a0e160a` | p1 „Kancelarija“ 24; live-kancelarija 20/20 | član koji zaobiđe UI → 403; uklanjanje traži 2. klik; V1 `vindex_firma` se ne čita | VERIFIED | PENDING |
| P1.6a | `routers/sef.py`: bez reda lažno „nije konfigurisano“ + poruka o migraciji, greška baze skrivena, POST 500 sa sirovim izuzetkom, pregled ključa 8 znakova | routers/sef.py | `79625816` | tests/test_p1_sef_podesavanja.py 10 (5 pada na starom); test_sef zelen | pregled = `***` + 4 znaka | VERIFIED | PENDING |
| P1.6b | V2 nema plan/potrošnju/satnicu/SEF | src/podesavanja-finansije.js | `3f26f9d4` | p1 „Finansije“ 21 | ključ samo za upis (`autocomplete=new-password`), nije u DOM-u/skladištu; nema slanja faktura; AKS stavke NISU izložene (ostaju u klasičnom prikazu) | VERIFIED | PENDING |
| P1 izgled | — | src/app.css, tests/podesavanja-snimci.mjs | `77662224` | snimci 24/24 (6 odeljaka × tamna/svetla × 1400/375; bez preliva) | pregledani ručno | VERIFIED | PENDING |
| P2.1 | Tema postoji samo kao prekidač u traci | src/app.js (`VxTema`, događaj `vx-tema`), src/podesavanja-izgled.js | `7b57ac36` | live-podesavanja-p2 10/10 (sinhrono u oba smera, tastatura, osvežavanje, promena naloga) | ista funkcija `postaviTemu`; tema = postavka uređaja, bez zahteva | VERIFIED | PENDING |
| P2.2 | V1 ćirilica (`cirilicaElement`, static/vindex.js:74) prevodi CELO podstablo AI odgovora, uklj. citate zakona i izvore; nije trajna | — | — | — | menjala bi originalne citate | **BLOCKED — potrebna specifikacija** (šta je izvorni tekst, a šta Vindex tekst) | — |
| P2.3 | Provera pristupačnosti Podešavanja | tests/live-podesavanja-a11y.mjs | `7f7407c2` | 56/56 (8 odeljaka × 2 teme × kontrast/oznake/fokus + zum 200%) | mutacija (slab kontrast, polje bez oznake, fokus bez obrisa) pada u obe teme | VERIFIED_NO_CHANGE_REQUIRED | PENDING |
| P2.4 | Radne preferencije | — | — | — | V2 nema ugovor za početni ekran, trajno sortiranje ni način prikaza; postojeće (skupljena navigacija, širina liste dokumenata) već imaju kontrole na mestu dejstva | NOT_IMPLEMENTED (nema potvrđenog ugovora) | — |
| P3.1–3.2 | Nijedna integracija nema pun lanac (matrica ispod) | index.html (odeljak Integracije), src/podesavanja-privatnost.js | `ab13d0c2` | live-podesavanja-p3 11/11 | bez kontrola, putanja, ključeva; otvaranje ne zove integracione rute | VERIFIED (samo stanje) | PENDING |
| SEC-SSRF | `routers/integracije.py` (user_webhooks): bilo koji URL pri upisu + serverski POST na njega u test ruti (prati preusmeravanja), uvek `success: True` | routers/integracije.py (grana `security/user-webhook-ssrf`, PR #56) | `9da6abef` | tests/test_sec_user_webhook_ssrf.py 18 (17 pada na starom); webhook/integracije 326 passed | isti validator kao NIGHT-009, bez preusmeravanja, stvaran ishod | VERIFIED | PENDING |
| SEC-pypdf | `dependency-scan` pada: pypdf 6.21.1, CVE-2026-115572/115580/115585 (CI log 2026-10-25 21:03) | requirements.txt (grana `security/pypdf-6.21.2`, PR #55) | `0580e9c2` | pip-audit (isti izuzeci kao CI): 0 ranjivosti; PDF testovi 152 passed / 15 skipped (nema OCR alata) | odvojeno od Settings scope-a | VERIFIED | PENDING |

## P0 — zaključci bez izmene koda
- Zakazivanje (`posalji_podsetnike`) bira `dan_N` za rok na `date.today() + N` ispravno; matrica 7/3/1, kombinacija, nepotvrđen,
  zatvoren/arhiviran/odbijen, u brisanju, dupli cron, neizvestan SMTP i prelazak godine dokazani testovima — `VERIFIED_NO_CHANGE_REQUIRED`.
- Vremenska zona zakazivanja: cron radi u 08:00 UTC (`email-cron.yml`) i 07:00 UTC (`/api/cron/daily`) = 09–10 h u Srbiji,
  pa je UTC dan isti kao beogradski — `VERIFIED_NO_CHANGE_REQUIRED`. Ručno pokretanje između 22–24 h UTC bi koristilo UTC dan (nije dokazan kvar; nije menjano).
- TEST primer koristi beogradski dan (`_danas_beograd`, pravilo EU, provereno prema tz bazi za svaki polusat 2026).

## P1 exit gate
Za svaku oblast: snimci obe teme desktop/telefon (24/24), stvarni backend ugovor (mock prati rute + backend testovi za izmenjene rute),
prijavljen/neprijavljen, negativna autorizacija (403/404 na serveru, član zaobilazi UI), promena naloga A→B u otvorenom ekranu,
bez spoljnih radnji (brojači: 0 email, 0 brisanja osim izričito potvrđenog u mocku). V2 regresija: primary 51/51, api 49/49,
send 100/100, session 38/38, isolation 25/25, kancelarija 20/20, podesavanja 24/24, p1 71/71.

## P3.1 Matrica integracija (main `c4a698ae`)
| Integracija | EXISTS | AUTHORIZED | CONFIGURED | TESTED | USER_VISIBLE | Napomena |
|---|---|---|---|---|---|---|
| SEF podaci prodavca | da (routers/sef.py) | da (JWT, vlasnik) | po korisniku | da (test_sef, test_p1_sef_podesavanja) | V1 + V2 (P1.6) | slanje faktura nije izloženo u V2 |
| Email podsetnici (B10) | da | da | SMTP da; cron 403 dok Render `CRON_SECRET` ≠ GitHub `CRON_TOKEN` | da | V1 + V2 | čeka osnivača |
| SMS (Twilio) | da (routers/sms.py) | send-reminders samo founder | **ne** (`/sms/status` → false, 2026-10-26) | delimično | V1 (forma) | sms-cron bez rasporeda |
| WhatsApp (whatsapp_notif.py) | da | da / cron ili founder | UNKNOWN (posebni env) | nepoznato | nigde | nijedan pozivalac |
| REST API ključevi (/api-kljucevi, /v1/*) | da | `require_pro` | ne traži env | delimično | V1 (Predmeti → ključ) | ključ u bazi **u čistom tekstu**; „dnevni“ limit broji ukupne pozive i nikad se ne resetuje (posle 500 poziva trajno 429) |
| Webhooks (user_webhooks / webhooks) | da, dva sistema | da | — | CRUD da | V1 statički tekst | **oba `trigger_webhook` imaju 0 pozivalaca** — ne stiže nijedan događaj; SSRF u user_webhooks (PR #56) |
| Clio webhook | da | HMAC, fail-closed bez tajne | UNKNOWN | nepoznato | ne | jedna globalna tajna, pošiljalac bira `vindex_user_id` (dizajnerski rizik granice zakupca) |
| iManage webhook | stub (samo log) | token | UNKNOWN | — | ne | ništa se ne čuva |
| Google Calendar | kod postoji | JWT | env potreban; podrazumevani redirect stari onrender POST | ne | ne | `state` = user_id; tokeni u čistom tekstu (`integracije`) |

## Bezbednosni nalazi sprinta
| ID | Nalaz | Status |
|---|---|---|
| SEC-pypdf | 3 CVE u pypdf 6.21.1 (dependency-scan pada) | ispravka PR #55, čeka spajanje |
| SEC-SSRF | slepi SSRF u user_webhooks | ispravka PR #56, čeka spajanje — preporuka: prioritet |
| SEC-SEF-PREVIEW | pregled SEF ključa nosio 8 znakova tajne | ispravljeno u ovoj grani (`79625816`) |
| SEC-API-KEY-PLAINTEXT | `api_kljucevi.kljuc` u čistom tekstu | otvoreno, van scope-a (traži migraciju/odluku) |
| SEC-GCAL | OAuth `state`=user_id, tokeni u čistom tekstu | otvoreno; integracija nije korisnički dostupna |
| SEC-CLIO-TENANT | globalna Clio tajna + `vindex_user_id` iz tela | otvoreno; integracija nije korisnički dostupna |
| FUNC-API-LIMIT | „dnevni“ limit API ključa bez resetovanja | otvoreno, van scope-a |

# Settings Master Sprint — izvršna evidencija

Grana `feature/v2-professional-settings` od `origin/main` `c4a698ae` (= produkcija `c4a698ae`, sw v163, 2026-10-25).
Ništa nije spojeno ni pušteno. Produkcioni status svih stavki: **PENDING** dok osnivač ne spoji i ne prođe smoke test.

| Task | Problem (dokazano) | Fajlovi | Commit | Testovi | Adversarial | Impl. | Prod. |
|---|---|---|---|---|---|---|---|
| P0.1–P0.4 | `POST /email-notif/test` je uvek slao šablon „Za 3 dana“ (`dana_pre=3`, routers/email_notif.py:258 na `c4a698ae`) | routers/email_notif.py, frontend-v2-ng/{index.html,src/podesavanja.js,tests/live-podesavanja.mjs}, tests/test_p0_b10_interval_correctness.py, tests/test_tenfronts_m10_primalac.py | `7b5b9a22` | novi: 49 passed; 30 B10 fajlova: 668 passed; V2: podesavanja 24/24, primary 51/51, api 49/49, send 100/100, session 38/38, isolation 25/25 | 5/5 mutacija ubijeno (hardkod 3, UTC dan, bool kao interval, bez provere uključenosti, bez oznake TEST) | VERIFIED | PENDING |
| SEC-pypdf | `dependency-scan` pada: pypdf 6.21.1, CVE-2026-115572/115580/115585 (CI log 2026-10-25 21:03) | requirements.txt (grana `security/pypdf-6.21.2`, PR #55) | `0580e9c2` | pip-audit (isti izuzeci kao CI): 0 ranjivosti; PDF testovi 152 passed / 15 skipped (nema OCR alata) | odvojeno od Settings scope-a | VERIFIED | PENDING |

## P0 — zaključci bez izmene koda
- Zakazivanje (`posalji_podsetnike`) bira `dan_N` za rok na `date.today() + N` ispravno; matrica 7/3/1, kombinacija, nepotvrđen,
  zatvoren/arhiviran/odbijen, u brisanju, dupli cron, neizvestan SMTP i prelazak godine dokazani testovima — `VERIFIED_NO_CHANGE_REQUIRED`.
- Vremenska zona zakazivanja: cron radi u 08:00 UTC (`email-cron.yml`) i 07:00 UTC (`/api/cron/daily`) = 09–10 h u Srbiji,
  pa je UTC dan isti kao beogradski — `VERIFIED_NO_CHANGE_REQUIRED`. Ručno pokretanje između 22–24 h UTC bi koristilo UTC dan (nije dokazan kvar; nije menjano).
- TEST primer koristi beogradski dan (`_danas_beograd`, pravilo EU, provereno prema tz bazi za svaki polusat 2026).

# NS005 — Overnight Evidence Log

Grana `feature/vindex-v2-recovery-ns005` iz `origin/main` `51164c92`. Forenzička mapa: `850596d8` (čitana sa `git show`, nije spojena).
Lokalno: Node 24.15.0, Playwright Chromium, Python 3.x (pytest). Bez produkcije, bez Render-a, bez baze.

## TASK 0 — BASELINE + FORENSIC LOCK — PROVEN
- `origin/main` = `51164c92ed39638c289f5dc201920a80430090be` (fetch), `850596d8` postoji, 5 artefakata čitljivo; worktree `C:\vindex-recovery-ns005` nov, čist.
- CAP za noćas: 004 005 006 007 030 031 032 188 074 160 040 042 045 060 061 062 063 186 090 091 095 100 101 099 070 071 072 075 080 081 010 011 020 014.
- NG pre misije: `src/api.js` (samo GET), `predmeti.js`, `predmet.js`, `detalj.js`, `live.js`, `session.js`, `runtime.js`, `app.js`; tačno 3 GET rute.
- Donori (`/app-v2`): `v2/platform/http.js`, `v2/features/{predmeti,dosije,klijent,pretraga,znanje,kancelarija,rokovi,danas}/*`.
- NG baseline (19 skripti iz package.json, sa `serve.mjs`): sve zelene (verify 98, pozadina 45, refinement 86, demo-otisak, live-runtime 92, live-api 49, live-session 38, live-matters 64, live-states 99, live-isolation 25, live-matrix 152, session-contract 33, brand 335, live-matter 56, e2e:fastapi 62, e2e:sw-isolation 28, e2e:primary 41, e2e:site 57).
- Python baseline na `main`: vidi „PYTHON BASELINE" ispod (puni `pytest tests -p no:randomly`, 8475 testova sakupljeno).

## TASK 1 — V2 SAFE MUTATION TRANSPORT — PROVEN
- FILES: `frontend-v2-ng/src/api.js` (+`send`), `tests/live-send.mjs` (nov), `tests/live-api.mjs` (1 tvrdnja: get+send umesto samo get), `package.json` (`verify:live-send`).
- ENDPOINTS: nijedan novi (transport).
- TESTS: `verify:live-send` 76/76; `verify:live-api` 49/49 (GET nepromenjen); svih 20 NG skripti zeleno.
- ADVERSARIAL: 6/6 mutacija ubijeno i vraćeno (sha256 api.js isti pre/posle): bez Authorization; spoljni host; automatsko ponavljanje; mreža→„nije sačuvano"; `user_id` u telu; 5xx kao poznat neuspeh.
- KNOWN LIMITATIONS: (1) Chromium SAM ponovo šalje POST kada se PONOVO KORIŠĆENA keep-alive veza prekine pre odgovora (izmereno: 2 zahteva za 1 fetch); sloj ne ponavlja (1 fetch), sveža veza = 1 zahtev. Zaštita bi bila idempotentni ključ na serveru — van NS005 (bez backend promene). (2) DELETE i PUT nisu izloženi.
- NEXT GATE: Task 2 — novi predmet.

## PYTHON BASELINE (main 51164c92, lokalno, `pytest tests -p no:randomly`)
- 21 failed, 8275 passed, 179 skipped (18 min). Imena padova: test_prg_night_register (5), test_faza1_pristupacnost (3), test_coi_intake_convergence (3), test_bu001_briefing_schema_contract (3), test_rc_cold_start (2), phoenix013, ns003_protocol, faza1_izvor_pod, ca_trust_boundary, b4_authority_playwright (po 1). Pravilo: nijedno NOVO ime pada.

## TASK 2 — NEW MATTER (CAP-004) — PROVEN
- FILES: `frontend-v2-ng/src/nov-predmet.js` (nov), `src/app.js` (ruta `#/predmeti/nov`, link, osvežavanje registra), `index.html` (forma, „Nov predmet" u alatima registra), `src/app.css` (forme; `[data-pogled]` uopšten), `tests/live-nov-predmet.mjs`, `tests/fixtures/pisanje-api.mjs`, `tests/ns005_harness.py` (stvarne rute + baza u memoriji, 2 korisnika, blokirana mreža), `tests/test_ns005_t2_nov_predmet.py`.
- ENDPOINTS: `POST /api/predmeti` (telo naziv/tip/opis; bez user_id), posle uspeha `GET /api/predmeti/{id}` i osvežen `GET /api/predmeti`.
- TESTS: backend 7/7 (stvarna ruta: id vraćen, vlasnik iz tokena, user_id iz tela ignorisan, B → 404 i nema u listi, 401/400 bez upisa, 409 za dupli); NG `verify:live-nov-predmet` 41/41; svih 21 NG skripti zeleno (DEMO otisak i piksel-matrica nepromenjeni); `test_v2_ng_*` + website 142 passed.
- ADVERSARIAL: 5/5 ubijeno — vlasnik iz tela (backend), bez owner filtera na detalju (backend), kasni odgovor prihvaćen posle A→B, nepoznat ishod prikazan kao „nije otvoren", dupli submit.
- UX: 500/prekid/2xx-bez-id = „Ishod nije poznat… predmet je možda otvoren"; 4xx = „nije otvoren"; unos ostaje; dugme zaključano tokom slanja; DEMO nema ulaz.
- KNOWN LIMITATIONS: stranke/broj/vrednost se ne unose pri otvaranju (ugovor rute) — Task 3. Provera sukoba interesa — Task 4.
- NEXT GATE: Task 3.

## TASK 3 — MATTER EDIT + NOTES + CHRONOLOGY (CAP-005 edit, 006, 007) — PROVEN
- FILES: `src/rad-predmeta.js` (nov), `src/predmet.js` (opis, updated_at, beleske/hronologija iz ISTOG odgovora; null = „nije učitano"), `src/detalj.js` (`osvezi`), `src/app.js` (tab `#/predmeti/<id>/rad`), `index.html`, `src/app.css`, `tests/live-rad-predmeta.mjs`, fixture `pisanje-api.mjs` (+PATCH, +beleške), `predmeti-api.mjs` (detalj vraća beleške/hronologiju fixture-a), `tests/test_ns005_t3_izmena_beleske.py`.
- BACKEND FIX (dokazan kvar, najmanja izmena): `api.py::update_predmet` — `maybe_single()` vraća None (postgrest 2.28.3) → tuđ/nepostojeći predmet je davao 500 umesto 404 (ista klasa kao NS004 `get_predmet`). `if not exists or not exists.data`. Autorizacija nepromenjena; regresioni test `test_tudja_izmena_404_i_red_netaknut`.
- ENDPOINTS: `PATCH /api/predmeti/{id}` (samo izmenjena polja naziv/tip/tuzilac/tuzeni/vrednost_spora/opis + `if_updated_at`), `POST /api/predmeti/{id}/beleske`; beleške/hronologija iz postojećeg `GET /api/predmeti/{id}` (bez novih zahteva). Posle upisa predmet se PONOVO čita.
- NE NUDI SE: broj predmeta (server ga ne prima), status (tok zatvaranja), rizik (računa program), „istorija" (to je AI Q&A dnevnik, ne događaji — ručni unos bi bio lažan), brisanje beleški.
- TESTS: backend 11/11 (+ 61 postojećih testova ove rute zeleno); NG `verify:live-rad-predmeta` 44/44; svih 21 NG skripti zeleno; 214 ciljanih Python testova zeleno.
- ADVERSARIAL: ubijeno 7 — neuspeh kao uspeh, bez if_updated_at, nedostajuće beleške kao prazna lista, nepoznat ishod kao „nije sačuvano", PATCH bez owner filtera, beleška bez provere vlasnika, vraćen 500 za tuđ PATCH. PREŽIVELA 1 (namerno prijavljeno): uklanjanje SAMO generacijske provere — kasni odgovor i dalje blokiraju abort + čišćenje pri učitavanju; kombinovana mutacija (generacija + abort) UBIJENA.
- KNOWN LIMITATIONS: `POST beleske` u tuđ predmet vraća 500 (`.single()`), ne 404 — fail-closed, ništa upisano; nije ispravljano jer postojeći bezbednosni testovi zavise od oblika upita, a V2 formu nudi samo na otvorenom (sopstvenom) predmetu. Delegirani čitalac bi pri pokušaju beleške video „ishod nepoznat".
- NEXT GATE: Task 4.

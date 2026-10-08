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

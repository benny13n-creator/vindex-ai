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

## TASK 4 — CLIENTS + LINKING + CONFLICT CHECK (CAP-030/031/032/188) — PROVEN
- FILES: `src/klijenti-predmeta.js` (nov), `src/api.js` (dozvoljen JEDINO dodatni prefiks `/klijenti`; odbijaju se `..`, `.`, `#`, `\`), `src/app.js` (blok Klijenti uvek vidljiv; prazan niz = „nijedan klijent"), `index.html`, `src/app.css`, `tests/live-klijenti.mjs`, `tests/live-send.mjs` (+6 putanja), fixture `api-fixture.mjs` (`/klijenti` ide API-ju), `pisanje-api.mjs` (+klijenti, COI, confirm-links), `tests/ns005_harness.py` (projekcija kolona + ugnježđene tabele kao PostgREST; zamena `_get_supa`/`_verify_token` u svim ruterima), `tests/test_ns005_t4_klijenti_coi.py`.
- ENDPOINTS: `GET /klijenti?pretraga=&limit=20`, `POST /klijenti` (tip, ime, prezime, firma, email, telefon — bez JMBG/PIB/pasoša), `POST /api/conflict-check`, `POST /api/predmeti/{id}/confirm-links` (`uloga: "stranka"`; uspeh = id u `linked_klijenti`, ne HTTP 200).
- COI PRAVILO: čita se ishod backenda (domain/konflikt.js). Sukob → BLOKIRANO (bez zaobilaženja); pregled/nepotpuna/neizvršena → samo uz izričitu potvrdu; čisto+potpuno → slobodno. Jedina izmena: nalazi O ISTOM predmetu se izostavljaju (predmet nije u sukobu sam sa sobom), status se izvodi ISTIM pravilom kao `conflict_check.py` (`_AKTIVNI_STATUSI`). Podudaranje se ne dira. Serverska poruka (emodži) se ne prikazuje.
- TESTS: backend 10/10 (vlasnik klijenta iz tokena; pretraga samo svojih; lista bez šifrovanih polja; tuđ klijent izostavljen iz veze; tuđ predmet odbijen; COI samo nad podacima pozivaoca; pad sloja ≠ čisto); NG `verify:live-klijenti` 40/40; `verify:live-send` 82/82; svih 22 NG skripti zeleno; ciljani Python 239 passed + 3 pada = ISTA imena kao baseline (`test_coi_intake_convergence` t8 A/B/C `[trio]`).
- ADVERSARIAL: 10/10 ubijeno — sukob ne blokira; pad provere kao čisto; bez izostavljanja istog predmeta; uspeh veze po 200; greška pretrage kao prazno; zastarela COI (generacija+abort); confirm-links bez vlasnika klijenta; lista bez owner filtera; COI čita tuđe predmete; transport propušta bilo koju putanju.
- OPEN PRODUCT DECISION (founder): `conflict_check` vraća „conflict" i za POSTOJEĆEG sopstvenog klijenta koji ima DRUGI aktivan predmet (sloj `klijenti`, tip `klijent_u_sistemu`). Po zaključanom pravilu Z017.1 §4 V2 to BLOKIRA → ponovljeni klijent sa aktivnim predmetom trenutno ne može da se poveže u V2 (legacy i `/app-v2` imaju isto pravilo za stranke). Treba odluka: da li `klijent_u_sistemu` sme biti „pregled" umesto „sukob" (backend semantika), ne frontend zaobilaženje.
- KNOWN LIMITATIONS: uloga klijenta je uvek „stranka" (COI tumači „tuženi" u ulozi kao suprotnu stranu, pa se uloga namerno ne nudi). Izmena podataka klijenta i kartoteka kao zaseban ekran nisu deo ovog zadatka.
- NEXT GATE: Task 5.

## TASK 5 — HEARINGS + GLOBAL SEARCH (CAP-074, CAP-160) — PROVEN
- FILES: `src/rocista-predmeta.js`, `src/pretraga.js` (novi), `src/app.js` (ruta `#/pretraga`, link „Pretraga" u gornjoj traci samo za prijavljenog; ročišta lenjo na „Rad na predmetu"), `index.html`, `src/app.css`, `tests/live-rocista-pretraga.mjs`, fixture `pisanje-api.mjs` (+ročišta, +pretraga), `tests/live-rad-predmeta.mjs` (suzena provera teksta), `tests/ns005_harness.py` (+`offset`), `tests/test_ns005_t5_rocista_pretraga.py`.
- ENDPOINTS: `GET /api/rocista?predmet_id=&limit=100`, `POST /api/rocista` (predmet_id, sud, datum, vreme?, sudnica?, broj_predmeta_suda?, napomena?), `GET /api/search?q=&vrste=predmeti,dokumenti,beleske,hronologija&limit=10`.
- PRAVILA: lista ročišta se čita tek na odeljku „Rad na predmetu" (pregled/dokumenti bez dodatnog zahteva — NS004 tok nepromenjen, dokazano); red drugog predmeta u odgovoru → ceo odgovor odbijen; pretraga traži samo vrste koje V2 ume da otvori (klijenti izostavljeni — nema ekrana klijenta); `nepotpuno` se prikazuje kao „pretraga nije potpuna", ne kao „nema rezultata"; 1 znak → bez zahteva. Zakazivanje ne šalje podsetnike; status/brisanje ročišta nisu izloženi.
- TESTS: backend 8/8 (zakazivanje na svom predmetu, vlasnik iz tokena; tuđ predmet 404 bez upisa; tuđa ročišta nevidljiva; 422 datum; pretraga samo svoje; pad grane = `nepotpuno`; kratak upit 422); NG `verify:live-rocista-pretraga` 38/38; svih 23 NG skripti zeleno; ciljani Python 215 passed.
- ADVERSARIAL: 9/9 ubijeno (+3 ponovljeno posle lenjog učitavanja) — greška pretrage kao prazno; `nepotpuno` ignorisano; greška liste ročišta kao prazno; red drugog predmeta prihvaćen; zastarela lista (generacija+abort); zastarela pretraga posle A→B (generacija+abort); ročište bez provere vlasnika predmeta; lista bez owner filtera; pretraga bez owner filtera.
- REGRESIJA UHVAĆENA I ISPRAVLJENA: prvo (eager) učitavanje ročišta pri otvaranju predmeta oborilo je `e2e:fastapi` (3) i `e2e:primary` (1) — dodatni zahtev u NS004 toku i spoljni DNS iz neopatchovanog `shared.deps._get_supa` u starom harness-u. Rešenje: lenjo učitavanje (bez izmene harness-a).
- NEXT GATE: Task 6 — pravno pitanje sa izvorima.

## FULL PYTHON @ 09f4330f (posle Task 5) — 20 failed / 8312 passed / 179 skipped
- NOVA imena padova u odnosu na baseline: **0**. Nestao 1 (`test_b4_authority_playwright::test_b4_ui_parcijalan_odgovor_MORA_biti_oznacen` — Playwright, nije diran ovim radom; tretira se kao nestabilan, ne kao zasluga).

## TASK 6 — GROUNDED LEGAL QUESTION (CAP-040) — PROVEN
- FILES: `src/pitanje-predmeta.js` (nov; tumačenje preuzeto iz `v2/domain/znanje.js` bez izmene pravila), `src/app.js` (tab `#/predmeti/<id>/pitanje`; odgovor preživljava osvežavanje ISTOG predmeta, briše se pri promeni predmeta/korisnika), `index.html`, `src/app.css`, `tests/live-pitanje.mjs`, fixture `pisanje-api.mjs` (+pitanje), `tests/test_ns005_t6_pravno_pitanje.py`.
- ENDPOINT: `POST /api/pitanje {pitanje, predmet_id}` — bez istorije, bez user_id; nikad automatsko ponavljanje.
- BACKEND DOKAZ (stvarna ruta + STVARNI `ask_agent`, model zamenjen funkcijom koja PUCA ako se pozove): bez pouzdanog izvora → `confidence: LOW`, bez `izvori`, „Nemam pouzdan odgovor", model NIJE pozvan; izmišljen član (9999) → odbijanje, model NIJE pozvan; pad korpusa (`izvori_neuspeh: [zakon]`) → `retrieval_unavailable: true`, model NIJE pozvan; sopstveni predmet → beleške ulaze u upit, `kontekst_predmeta: true`, upis u istoriju; TUĐ predmet → beleške A NE ulaze u upit B, `kontekst_predmeta: false`, nema upisa u istoriju A; bez tokena 401. 7/7.
- UI PRAVILA: izvori SAMO iz odgovora (red bez zakona ispada); sigurnost rečima; tri stanja (pad korpusa / deo nije proveren / bez pogotka) se ne spajaju; `kontekst_predmeta:false` se izričito saopštava; napomena backend-a se ne duplira; `**` i ikonice iz serverskog teksta se ne prikazuju (sadržaj ostaje); 5xx/prekid = „odgovor nije dobijen, pitanje je možda obrađeno".
- TESTS: NG `verify:live-pitanje` 42/42; svih 24 NG skripti zeleno; ciljani Python 175 passed (uključujući `test_hallucination_guard`, `test_bu003`, `test_b4_source_authority`, `test_bu004n1`).
- ADVERSARIAL: 9/9 ubijeno — izmišljen izvor na klijentu; bez upozorenja kad nema izvora; pad korpusa sakriven; serverska greška kao odgovor; zastareo odgovor (generacija+abort); `kontekst_predmeta:false` prećutan; beleške tuđeg predmeta u upitu (backend); izmišljen član bez odbijanja (backend `main.py`); model pozvan bez izvora (backend `main.py`).
- **OPEN BLOCKER (founder, backend): DUPLO/TROSTRUKO NAPLAĆENO PITANJE.** Izmereno: kada se veza prekine pre odgovora na PONOVO KORIŠĆENOJ keep-alive vezi, Chromium sam ponovo šalje POST — server je primio **3** pitanja za **1** fetch aplikacije. Za `/api/pitanje` to znači moguće višestruko oduzimanje kredita i duplu istoriju. Aplikacija ne ponavlja (dokazano: 1 fetch). Jedina zaštita: idempotentni ključ na serveru — van NS005 (bez backend promene).
- KNOWN LIMITATIONS: (1) pri padu korpusa API vraća generički tekst („Došlo je do greške…") jer `normalizuj_rezultat` za status "error" čita samo `message`, a agent piše objašnjenje u `data` — V2 se oslanja na zastavicu `retrieval_unavailable` (prolazi granicu); (2) serverski tekst odbijanja sadrži „Score: 0.120" — prikazuje se doslovno (sadržaj backend-a se ne menja); (3) prethodna pitanja predmeta (`istorija`) se ne prikazuju u V2.
- NEXT GATE: Task 7 — praksa + interni stavovi (Znanje).

# RH001 — V2 Release Hardening: dokazi

**Datum:** 2026-10-10 · **Režim:** lokalni inženjering + CI na GitHub-u · **Ništa nije spojeno, deployovano, migrirano, obrisano ni aktivirano.**

Oznake: **PROVEN** (izmereno ovde) · **INFERRED** (izvedeno iz koda/dokaza) · **ASSUMED** (preuzeto iz zapisa, nije ponovo provereno) · **UNKNOWN**.

---

## A. Tačno završno stanje

### Release grane (nepromenjene — PROVEN, `git ls-remote` + GitHub API)

| Grana | SHA | Osnova | Ahead |
|---|---|---|---|
| `main` | `99d2c6b9` | — | — |
| `feature/vindex-v2-ns006-living-matter` | `dac1f6dd` | main `99d2c6b9` | +24 |
| `feature/vindex-v2-ns007-while-you-sleep` | `deac5d99` | NS006 `dac1f6dd` | +24 |
| `feature/vindex-v2-ns008-law-brain` | `79c1071b` | NS007 `deac5d99` | +31 |

Topologija linearna (merge-base = glava prethodne grane, 0 behind). Nijedna grana nema GitHub zaštitu (`protected=false`, uključujući `main`).
Produkcija (Render): `/health` → `"commit":"99d2c6b"` (PROVEN, javni odgovor). `/app` služi V2 NG (`/v2/app/@99d2c6b`, PROVEN); legacy UI je na `/app-legacy` (200, nije linkovan iz V2 osim auth preusmerenja).

### RH001 grane (nove, pushovane, bez PR-a ka main-u)

| Grana | Glava | Sadržaj |
|---|---|---|
| `feature/vindex-v2-rh001-ns006` | `11e4dcc3` | NS006 + 2 CI commita (V2 NG zaista izvršava pakete) |
| `feature/vindex-v2-rh001-ns007` | `5cc59d7c` | NS007 + rh001-ns006 + Hearing Prep pravni autoritet + test crash prozora |
| `feature/vindex-v2-rh001-ns008` | (ovaj dokument) | NS008 + rh001-ns007 + bezbednosna popravka legacy memorije + sinteza + ovi dokumenti |
| `hotfix/rh001-memory-acl` | `4dcaa985` | main + ista bezbednosna popravka, izolovano za eventualni produkcioni hotfix |

Svaka RH001 grana je potomak odgovarajuće release grane → founder je može fast-forward spojiti bez rebase-a.

### PR-ovi
- **#10** (NOVO, Draft) `feature/vindex-v2-ns008-law-brain` → `feature/vindex-v2-ns007-while-you-sleep`, 31 commit — https://github.com/benny13n-creator/vindex-ai/pull/10
- #9 (postojeći, Draft) NS006 → main, `dac1f6dd`.

### Izmenjeni fajlovi (RH001, ukupno)
- CI: `.github/workflows/v2-ng.yml`, `frontend-v2-ng/package.json` (e2e:demo-ns006/7/8)
- NS007: `shared/pravni_autoritet.py` (novo), `services/agent_tasks/hearing_prep.py`
- NS008: `shared/memorija_vidljivost.py` (novo), `routers/firm_memory.py`, `routers/memory_graph.py`, `api.py` (`_fetch_firm_memory_context`), `services/law_brain.py`, `services/law_brain_sinteza.py`
- Testovi: `tests/test_rh001_hearing_prep_authority.py`, `tests/test_rh001_scheduler_crash_window.py`, `tests/test_rh001_legacy_memory_acl.py`, `tests/test_rh001_law_brain_authority.py`; fixture dopuna u `tests/test_phoenix_mission_003_institutional_memory.py`

---

## B. Matrica kapija

| Kapija | NS006 | NS007 | NS008 |
|---|---|---|---|
| Docker build produkcione slike | **PASS** (run 37992392490, attempt 3, `dac1f6dd`) | INFERRED PASS (V2 NG docker posao na `5cc59d7c`) | vidi §G |
| Kontejner sa podrazumevanim CMD (uvicorn) + `/health` | **PASS** (V2 NG run 38056360863/38057271937) | **PASS** (V2 NG run 38057274307) | vidi §G |
| `import api` na Python 3.11 u slici | **PASS** | vidi §G | vidi §G |
| Ceo backend paket, produkcioni interpreter (3.11, kontejner) | **PASS** — 197=197 padova po imenu vs main, 0 novih | vidi §E | vidi §E |
| Test Suite 3.11 + 3.13 | **PASS** — 175=175 po imenu, 0 novih | vidi §E | vidi §E |
| V2 NG paketi u CI | **PASS** (prvi put stvarno izvršeni) | **PASS** | vidi §E |
| Pravna pouzdanost (implicitni autoritet) | n/a | **PASS** (popravljeno, §C2) | **PASS** (popravljeno u sintezi, §C3) |
| Crash prozor rasporedivača | n/a | **KLASIFIKOVANO** — gubi najviše 1 prozor (§C5) | n/a |
| Poverljivost legacy memorije | — | — | **PASS posle popravke** (bio FAIL, §C1) |
| Opoziv overenih radova (read-time) | — | — | **PASS** (§F) |
| Legacy procene uspeha % | — | — | **KLASIFIKOVANO** — odluka foundera (§H) |
| Migracija 136 | — | **BLOCKED** (nije primenjena — ASSUMED iz zapisa; DB pristup nedostaje) | — |
| Render Cron | — | **BLOCKED** (nije napravljen, namerno) | — |
| Latencija na stvarnim podacima | UNKNOWN | UNKNOWN | UNKNOWN |
| gitleaks | UNKNOWN (alat nije instaliran) | UNKNOWN | UNKNOWN |

---

## C. Potvrđeni defekti

### C1. [BEZBEDNOST — BLOKATOR] Legacy memorija kancelarije zaobilazi ACL predmeta (postoji i u PRODUKCIJI)

- **PROBLEM:** advokat B (ista kancelarija, bez delegacije) dobija A-ove beleške vezane za predmet i klijenta i veze u grafu sa ishodom: `/api/firma-memorija/{sve,pretrazi,klijent,kontekst-za-ai}`, `/api/memory-graph/{entitet,upit,preporuka}` (uključujući GPT prompt) i **sistemsku poruku chata** (`api._fetch_firm_memory_context`). B može i da potvrdi ili deaktivira A-ovu belešku.
- **DOKAZ (PROVEN):** `tests/test_rh001_legacy_memory_acl.py` nad stvarnim rutama: pre popravke 6/7 pada na NS008 i 6/7 na **main `99d2c6b9`**; B-ov `/sve` sadrži „Petrović protiv Gradnja Invest DOO" i „Klijent A popušta pod pritiskom"; B-ov chat prompt sadrži `[Petrović protiv Gradnja Invest DOO] Klijent A popušta pod pritiskom`; 16 ruta odgovara različito u svetu sa i bez A-ovih podataka.
- **UZROK:** legacy rute filtriraju samo po `kancelarija_id`. NS008 Law Brain je istu granicu primenio na iste tabele, ali u privatnim pomoćnim funkcijama — legacy rute je nikad nisu dobile.
- **ODLUKA:** jedan vlasnik pravila, bez nove politike deljenja — postojeće NS008 pravilo (predmet → `rag_acl.dozvoljeni_predmeti`; klijent → vlasnik klijenta; sudija/firma/partner/argument/strategija → kancelarija).
- **IZMENA:** `shared/memorija_vidljivost.py`; primenjeno u Law Brain-u (refaktor bez promene ponašanja), `firm_memory.py`, `memory_graph.py`, `api._fetch_firm_memory_context`. Filter PRE limita rute (ograničeno čitanje 1000 redova) — inače broj vidljivih stavki odaje skrivene. Skriven red na `potvrdi`/`DELETE` = isti 404 kao nepostojeći.
- **NON-GOALS:** opšte beleške i veze kancelarije rade kao ranije (test); `client_memory`/`judge_patterns`/`partner_profiles` nepromenjeni (vidi §H); nijedan modul nije ugašen.
- **TEST:** 7 testova (curenje, bajt-identičnost uklj. `?limit=1` orakul, potvrdi/brisanje, opšte znanje, vlasnik, delegacija + opoziv, chat prompt).
- **ADVERSARIJALNO:** 6 mutacija (svaki sloj ugašen pojedinačno, limit-pre-filtera) — sve ubijene. Zaštita od prazne provere: test pada ako ijedan odgovor dobije 401/403/429 (prva verzija testa je „prolazila" na 401 — uhvaćeno i ispravljeno).
- **REZIDUAL:** kancelarija sa >1000 beleški/veza: rangiranje se računa nad najnovijih/najjačih 1000 (bez curenja, ali nepotpuno). Produkcija ostaje izložena dok se hotfix ne odobri.

### C2. [PRAVNA POUZDANOST] NS007 Hearing Prep propušta implicitni pravni autoritet

- **DOKAZ (PROVEN, `deac5d99`):** „Prema ustaljenoj praksi Vrhovnog suda…", „Sudska praksa nalaže…", „Vrhovni sud smatra…", „Teret dokazivanja je uvek na tuženom" — sve prolazi `proveri_ai_stavke` uz važeću referencu (16/16 adversarijalnih).
- **NALAZ MERENJA:** lista obrazaca sama hvata **3/15** nezavisno napisanih formulacija → regex nije dovoljan.
- **ODLUKA (postojeći ugovor modula):** činjenice dolaze ISKLJUČIVO iz baze; model daje pitanja i beleške za pripremu. Dva nezavisna sloja: (1) **oblik** — AI stavka mora biti pitanje ili zadatak koji počinje glagolom pripreme (deklarativna rečenica pada bez obzira na reči); (2) **`shared/pravni_autoritet`** — autoritet (praksa/sudovi/zakon/teret dokazivanja) pada i unutar dozvoljenog oblika; pravna pravila (rokovi, zastarelost, zaključci) prolaze samo kao jasno označeno pitanje za proveru.
- **TEST:** 89 testova; mutacije: bez sloja oblika 19 pada, bez sloja autoriteta 5 pada; 0/26 preživelih mutacija pojedinačnih obrazaca. Postojeći NS007 testovi: 237 passed, 11 skipped (PG); demo 5/5; `live-pripremljeno` 51/51.
- **REZIDUAL:** zadatak koji umota pravnu tvrdnju bez poznatih markera („Pripremite se na to da kamata teče od dospeća") može da prođe. Uz to stoji postojeća oznaka „Predlog analize (AI) — nije utvrđena činjenica ni pravni izvor".

### C3. Ista klasa u NS008 Law Brain sintezi
- **DOKAZ (PROVEN, `79c1071b`):** 3/4 tvrdnje autoriteta prihvaćene (`_ZABRANJENO` hvata samo „sudska praksa", „zakon", „uvek", „nikad").
- **IZMENA:** `proveri_sintezu` odbija sa razlogom `PRAVNI_AUTORITET_BEZ_IZVORA` preko istog deljenog pravila (sinteza je deklarativna po ugovoru, pa pravilo oblika ovde ne važi). Mutacija: 34 testa padaju.

### C4. [CI] V2 NG paketi nikad nisu izvršeni u CI-ju za NS006/NS007/NS008
- **DOKAZ:** svako V2 NG pokretanje na NS006 (`b724d6be`…), NS007 i NS008 pada na koraku „unwired" (`tests/ns00X-demo.mjs` bez verify/e2e skripte) → korak „Run all suites" se preskače. Lokalnih „2147/2147" iz NS008 izveštaja NIJE bio CI dokaz.
- **Drugi sloj (otkriven čim je prvi popravljen):** `live-analiza`, `live-pregled-zivi`, `live-radna-lista` pokreću Python fixture, a frontend posao nema Python → `ModuleNotFoundError: pytest`.
- **IZMENA:** demo skripte povezane kao `e2e:demo-ns00X` (e2e posao ih SADA izvršava — pojačanje, ne slabljenje); frontend posao dobija Python 3.11 + `requirements.txt`. Nijedan paket, tvrdnja ni kapija nije oslabljena.
- **REZULTAT:** V2 NG zelen na `rh001-ns006` (run 38057271937) i `rh001-ns007` (run 38057274307).

### C5. Crash prozor rasporedivača — klasifikacija (bez izmene koda)
- **PROVEN** (`tests/test_rh001_scheduler_crash_window.py`, pravi ruter/planer/izvršilac): proces umre posle INSERT-a u `autonomy_cycles` → ciklus ostaje RUNNING; isti UTC sat → SKIPPED, 0 poslova, 0 modela; sledeći sat → ročište se planira i priprema tačno jednom.
- **Klasifikacija:** prihvatljiv rezidual. Gubitak je ograničen na jedan prozor rasporeda jer je planer deterministički nad trenutnim stanjem baze. Vremenski trošak zavisi od kadence (NS007_RENDER_CRON_PLAN): opcija A (noćno) i podrazumevani prozor 0–1 dan → ročište se pokušava dve noći, pa jedan pad i dalje daje pripremu ujutru na dan ročišta; dva uzastopna pada = nema pripreme. Nema alarma za RUNNING ciklus koji je star → founder odluka (§H).

---

## D. Opovrgnute hipoteze

1. **„NS006 Docker neuspeh je defekt aplikacije"** — OPOVRGNUTO. Log: `auth.docker.io/token: 504 Gateway Timeout` i `Client.Timeout exceeded` pre ikakvog Vindex koda. Ponovno pokretanje istog commita: build, import, OCR (srp + srp_latn), Python 3.11.17 — sve PASS. Nijedna linija koda nije menjana.
2. **„NS006 uvodi nove padove u CI"** — OPOVRGNUTO. 175 = 175 (Test Suite 3.11/3.13) i 197 = 197 (produkcioni interpreter u kontejneru), po imenu, prema main `99d2c6b9`.
3. **„Opozvan overen rad je dostupan kroz alternativni put čitanja"** — OPOVRGNUTO (§F).
4. **„/api/outcome-intel curi među kolegama"** — OPOVRGNUTO: čita samo predmete korisnika (`.eq("user_id", uid)`).
5. **„Legacy procenti uspeha su vidljivi u primarnom proizvodu"** — OPOVRGNUTO za V2 primarni (nijedan V2 izvor ne poziva te rute, PROVEN pretragom); vidljivi su na nelinkovanom `/app-legacy` i kroz API.

---

## E. Test dokazi

### Lokalno (Windows, Python 3.13, `-p no:randomly`)
| Skup | Rezultat |
|---|---|
| `tests/test_rh001_hearing_prep_authority.py` | 89 passed (fail-before na `deac5d99`: 19 failed) |
| `tests/test_rh001_scheduler_crash_window.py` | 1 passed |
| NS007 svi `test_ns007_*` + RH001 | 237 passed, 11 skipped (PostgreSQL) |
| `tests/test_rh001_legacy_memory_acl.py` | 7 passed (fail-before: 6/7 na NS008 i 6/7 na main-u) |
| `tests/test_rh001_law_brain_authority.py` + `test_ns008_t12_synthesis.py` | 54 passed |
| svi `test_ns008_*` + svi RH001 + Phoenix | 292 passed |
| Postojeći testovi koji dodiruju memoriju (`beta_hardening_001`, `ca_trust_boundary`, `closure_trust_contract`) | 27 failed = **isti 27 po imenu** na `79c1071b` (okruženje), 0 novih |
| NG: `live-law-brain` 45/45, `live-znanje` 33/33, `live-pripremljeno` 51/51, `live-analiza` 43/43, demo ns006 4/4, ns007 5/5, ns008 7/7 | PASS |

### CI (GitHub Actions, Ubuntu)
Poređenje po **imenu testa** sa main `99d2c6b9` (Test Suite 37964409178, Parity 37964409248). Main bazna linija: 175 padova (3.11/3.13), 197 u produkcionom kontejneru.

| Grana (head) | Run | Job | Padovi | Prošlo | NOVI padovi vs main | Status |
|---|---|---|---|---|---|---|
| rh001-ns007 `5cc59d7c` | Test Suite 38058556838 | 3.11 / 3.13 | 175 / 175 | 8225 / 8225 | 0 / 0 | PASS (PROVEN) |
| rh001-ns007 | Parity 38058558548 | prod 3.11 kontejner | 197 | 7685 | 0 | PASS (PROVEN) |
| rh001-ns008 `5713bd9d` | Test Suite 38058560250 | 3.11 / 3.13 | 175 / 175 | 8469 / 8469 | 0 / 0 | PASS (PROVEN) |
| rh001-ns008 | Parity 38058562118 | prod 3.11 kontejner | 197 | 7929 | 0 | PASS (PROVEN) |
| rh001-ns008 | V2 NG 38058404043 | frontend + e2e + py311 + docker | — | sve | — | **zeleno** (PROVEN) |
| hotfix `4dcaa985` | Test Suite 38058541376 | 3.11 / 3.13 | 175 / 175 | 7867 / 7867 | 0 / 0 | PASS (PROVEN) |
| hotfix | Parity 38058543111 | prod 3.11 kontejner | 197 | 7327 | 0 | PASS (PROVEN) |

Zaključak workflow-a je „failure“ jer main sam ima 175/197 postojećih padova (CI bazna linija nije obnovljena; vidi raniji CI baseline rad). Nijedan test nije preskočen, obrisan ni oslabljen da bi se dobio ovaj rezultat; broj prošlih testova raste za tačno dodate RH001/NS testove. Jedina „GONE“ stavka u diffu je log linija `vindex.rokovi ... predmet_hronologija.izvor`, ne test.

### Statička analiza
- Bandit 1.9.4 (`-ll`) nad svim izmenjenim Python fajlovima: **0 nalaza**.
- Semgrep `p/python`: 5 nalaza u `api.py` (linije 321, 537, 539, 541, 1171) — **identični na `79c1071b`**, van RH001 izmena → 0 novih.
- Tajne: regex sken diff-a (`sk-…`, JWT, AKIA, privatni ključ, `password=`/`api_key=`) — 0. **To NIJE gitleaks**; gitleaks nije instaliran → UNKNOWN.

---

## F. Adversarijalni dokazi: bezbednost i pravno poverenje

- **Curenje među korisnicima (legacy memorija):** §C1 — reprodukovano, popravljeno, bajt-identičnost dokazana na 16 ruta + 4 upisa + chat prompt.
- **Autorizacija predmeta:** delegacija otvara predmetnu belešku/vezu, opoziv je zatvara od sledećeg zahteva (test). Klijentska beleška ostaje samo vlasniku i pri delegaciji predmeta.
- **Opoziv (Law Brain + opšti RAG):** jedino pravilo `services/law_brain.vazece_overe`, primenjeno u `retrieve_documents` (jedina grana koja čita `draft_final` iz `kancelarija_*`/`user_*` prostora, ~linija 2398) i u Law Brain pretrazi; fail-closed. Ostali Pinecone upiti čitaju druge prostore (`zakoni_rs`, `sudska_praksa`, `upravna_praksa`, `tmp_*`, `kb_*`, `playbook_*`, `interni_stavovi_*`) — PROVEN pretragom svih `index.query` mesta. Čitači `staging_memory` van Law Brain-a vraćaju korisniku njegov sopstveni nedavni nacrt (idempotentno ponavljanje), ne overeno znanje. Testovi `test_ns008_t21_revocation` prolaze na hardening grani.
- **Fizička izloženost (rezidual):** opozvani vektori ostaju u Pinecone-u (tekst u metapodacima). Dostupni su samo onome ko ima Pinecone ključ ili konzolu, ili budućem kodu koji bi čitao prostor bez `vazece_overe`.
- **Minimalni dizajn brisanja (odluka foundera):** ID vektora je deterministički (`canonical_vector_id(prostor, verzija_dokumenta(tekst), chunk)`), pa se pri prelazu `approved → rejected`/povlačenju odobrenja ID-jevi mogu izračunati iz `staging_memory.tekst` + prostora vlasnika i obrisati `delete(ids=…)`. Nema novog skladišta i nema migracije. Potrebna je odluka o zadržavanju i o tome da li se briše odmah ili posle grace perioda.
- **Nepodržane pravne tvrdnje:** §C2/§C3.
- **Spoljne akcije:** nijedna RH001 izmena ne šalje ništa napolje; Hearing Prep i dalje bez spoljne akcije (NS007 ugovor, A5 nepromenjen).

---

## G. Produkcioni paritet

- **Docker (NS006):** PASS na tačnom `dac1f6dd` (Production Runtime Parity run 37992392490, attempt 3): build realnog Dockerfile-a, `compileall`, `import api` u slici, OCR sa srpskim paketima (17 passed), Python 3.11.17; podrazumevani CMD + `/health` 200 + legacy rute 200 (V2 NG docker rehearsal na `59c885a4` = `dac1f6dd` + `package.json`).
- **Docker (NS007/NS008/hotfix):** PASS (PROVEN) — job „Build production image and boot-check it“ zelen na sve tri grane: rh001-ns007 (38058558548), rh001-ns008 (38058562118), hotfix (38058543111); OCR/boot provera 17 passed na svakoj, byte-compile 0 grešaka. V2 NG docker rehearsal zelen na rh001-ns008 (38058404043).
- **Migracije:** 135 primenjena (ASSUMED, founder zapis 2026-10-09). 136 NIJE primenjena (ASSUMED iz zapisa NS007). Nezavisna read-only provera istorije migracija: UNKNOWN (nema `SUPABASE_DB_URL` u ovom okruženju). RH001 ne dodaje migracije.
- **Deploy:** produkcija `99d2c6b` (PROVEN). Ništa iz NS006–NS008/RH001 nije u produkciji.
- **Otvorene release kapije:** NS007 — migracija 136, Render Cron + `AUTONOMY_CRON_SECRET`, izbor kadence; sve — merenje latencije na stvarnim podacima; gitleaks.

**Procedura merenja latencije (gate ostaje otvoren):** na staging/preview okruženju sa kopijom stvarnih podataka jedne kancelarije (≥ 50 predmeta, ≥ 200 beleški): 20 uzastopnih zahteva po ruti (`GET /api/law-brain/predmeti/{id}`, `/znanje`, `/api/firma-memorija/sve`, `/api/memory-graph/entitet/...`), zabeležiti p50/p95 iz `Server-Timing`/logova; prag za beta: p95 < 1,5 s za čitanja bez modela. Lažna baza nije merenje performansi.

---

## H. Odluke foundera

1. **Produkcioni hotfix za curenje memorije (§C1)** — `hotfix/rh001-memory-acl` je spreman (main + popravka + testovi). Rupa je u produkciji danas, a ispravka u NS008 liniji stiže tek posle NS006 → NS007 → NS008. Preporuka: otvoriti PR ka main-u, pregledati, spojiti i deployovati kao zaseban hotfix.
2. **`client_memory` (profil klijenta po imenu: „NIKAD ne prihvata nagodbu", rizik profil)** je kancelarijski vidljiv po dizajnu i nema vlasnika. Da li je to namerno deljeno znanje ili poverljivo? RH001 nije izmislio politiku.
3. **Legacy procene uspeha u procentima** — model izmišlja broj u rasponu 5–90 (`/api/procena`, `/api/predmeti/{id}/upload`, `strategija.ai_judge_v2`, `outcome-intel` sa izmišljenim procentima faktora, `court_predictor`, `copilot.verovatnoca_uspeha`, `benchmarking/win-rate`, `cio`, `case_intelligence`). Vidljivo na `/app-legacy` (bez disclaimer-a u bloku „verovatnoća uspeha tužioca") i kroz API; nije vidljivo u V2 primarnom. Opcije: ukinuti te sekcije ili rute, ili zatvoriti `/app-legacy` za korisnike osim auth toka.
4. **Fizičko brisanje opozvanih vektora** (dizajn u §F) i pravilo zadržavanja.
5. **Alarm za RUNNING ciklus stariji od 2 h** (NS007) — uz izbor kadence.
6. **Zaštita grana na GitHub-u** — `main` i release grane nemaju zaštitu.

---

## I. Preporučena sledeća akcija

**Pregledati i spojiti `hotfix/rh001-memory-acl` u main kao zaseban produkcioni hotfix** (PR → CI → deploy uz founder odobrenje). To je jedini potvrđeni bezbednosni propust koji je danas u produkciji.

---

## J. Eksplicitno NEURAĐENO

- Nije spojen nijedan PR; PR #10 je Draft; PR #9 nije diran.
- Nijedna release grana (main, NS006, NS007, NS008) nije menjana, rebase-ovana ni force-pushovana.
- Nema deploy-a, nema produkcione migracije (136 nije primenjena), nema Render Cron-a ni nove usluge.
- Nijedan Pinecone vektor nije obrisan.
- Nema nove baze znanja, novog agenta, nove sidebar stavke ni nove autonomne akcije.
- Task 18 (Law Brain u autonomiji) i migracija 137 nisu rađeni.
- Produkcione tajne nisu čitane ni ispisivane. GitHub token iz git credential helper-a korišćen je samo za API (CI, PR) i nije ispisan.

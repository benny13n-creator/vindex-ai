# RH002 — SECURITY INCIDENT CLOSURE & CONTROLLED V2 RELEASE — EVIDENCE

Datum: 2026-10-10. Oznake: **PROVEN** (izmereno ovde), **INFERRED** (zaključeno iz koda/dokaza), **ASSUMED** (preuzeto iz zapisa), **UNKNOWN**.
Ništa nije spojeno u `main`, ništa nije deployovano, nijedna migracija nije primenjena, Cron nije napravljen ni pokrenut, ništa nije obrisano.

---

## 1. Tačno stanje repozitorijuma i produkcije

| Ref | SHA | Napomena |
|---|---|---|
| `main` | `99d2c6b9` | PROVEN, nepromenjen |
| produkcija (Render) | `99d2c6b` | PROVEN — `GET https://vindex.rs/health` → `"commit":"99d2c6b"` |
| `hotfix/rh001-memory-acl` | `9dac6774` | PROVEN — `main` + 2 commita (`4dcaa985` RH001, `9dac6774` RH002) |
| `feature/vindex-v2-ns006-living-matter` | `dac1f6dd` | PROVEN, nepromenjen |
| `feature/vindex-v2-ns007-while-you-sleep` | `deac5d99` | PROVEN, nepromenjen |
| `feature/vindex-v2-ns008-law-brain` | `79c1071b` | PROVEN, nepromenjen |
| `feature/vindex-v2-rh001-ns006` | `11e4dcc3` | ⊃ NS006 |
| `feature/vindex-v2-rh001-ns007` | `5cc59d7c` | ⊃ NS007 i rh001-ns006 |
| `feature/vindex-v2-rh001-ns008` | vidi §10 | ⊃ NS008, rh001-ns007 i (od RH002) ceo hotfix |

Topologija (PROVEN, `git merge-base --is-ancestor`): `main ⊂ NS006 ⊂ NS007 ⊂ NS008`; `NSx ⊂ rh001-nsx`; `rh001-ns006 ⊂ rh001-ns007 ⊂ rh001-ns008`; `main ⊂ hotfix ⊂ rh001-ns008`.

PR-ovi (PROVEN, GitHub API):
- **#11** `hotfix/rh001-memory-acl → main` — DRAFT, otvoren u RH002.
- **#9** `NS006 → main` — DRAFT, head `dac1f6dd` (bez RH001 CI popravke).
- **#10** `NS008 → NS007` — DRAFT, head `79c1071b` — **i dalje pokazuje na originalni NS008 BEZ RH001/RH002 popravki** (vidi §5).
- Ne postoji PR za NS007 → NS006 (INFERRED: NS007 je čekao NS006).

Migracije: 135 primenjena (ASSUMED, founder 2026-10-09). 136 **nije primenjena** (ASSUMED iz NS007 zapisa); nezavisna read-only provera: **UNKNOWN** — `SUPABASE_DB_URL` nije dostupan ovom okruženju, a produkcioni kod (`99d2c6b`) ne dodiruje `autonomy_*` tabele, pa ni HTTP ne može da je posredno potvrdi.

Repozitorijum je **javan** (PROVEN, `visibility: public`). Svaki push hotfix grane objavljuje opis i reprodukciju propusta.

## 2. Bezbednosni incident

**Klasa:** curenje poverljivih podataka između advokata iste kancelarije + neovlašćena promena stanja + ubacivanje sadržaja u tuđ predmet.

| # | Put | Šta je B dobijao / mogao | Status na `99d2c6b9` |
|---|---|---|---|
| 1 | `GET /api/firma-memorija/sve`, `/pretrazi`, `/klijent/{ime}`, `/kontekst-za-ai` | A-ove beleške uz A-ove predmete i klijente (sadržaj, naziv predmeta) | PROVEN (RH001) |
| 2 | `GET /api/memory-graph/entitet`, `/upit`, `/preporuka` | A-ove veze sa ishodom, kontekstom i nazivom predmeta; i u LLM promptu | PROVEN (RH001) |
| 3 | chat — `api._fetch_firm_memory_context` | A-ove predmetne/klijentske beleške u SISTEMSKOJ poruci B-ovog chata | PROVEN (RH001) |
| 4 | `POST /potvrdi/{id}`, `DELETE /{id}` | potvrda / deaktivacija A-ove beleške; status odaje postojanje | PROVEN (RH001) |
| 5 | `POST /api/memory-graph/dodaj-vezu` | **RH002:** veza sa slobodnim tekstom (`kontekst`, `ishod`) pripojena A-ovom predmetu/klijentu kroz `from_id`/`to_id`; A je vidi u `/entitet` i u svom `/upit` promptu | **PROVEN (RH002)** |

Klase podataka: beleške advokata o predmetu i klijentu (strategija, ponašanje klijenta), nazivi predmeta, ishodi i kontekst iz grafa.

Preduslovi napada: prijavljen nalog, AKTIVNO članstvo u ISTOJ kancelariji kao žrtva; za graf rute i `memory_graph` dozvola. Neprijavljeni korisnici i članovi drugih kancelarija nisu pogođeni (INFERRED iz `kancelarija_id` filtera na svim upitima).

Produkcija je **i dalje izložena** (PROVEN: deployovan je `99d2c6b`, koji ne sadrži popravku).

## 3. Verifikacija hotfix-a

### A2 — pokušaj obaranja potpunosti
Pregledani su svi Python čitači i pisci `memory_entries` / `memory_graph_edges` (`git grep`): `api.py` (chat kontekst + noćno čišćenje po `confidence`/`zastarela` — nije čitanje za korisnika), `routers/firm_memory.py`, `routers/memory_graph.py`, `routers/proof.py` (samo provera postojanja kolona, `LIMIT 1`, bez sadržaja korisniku), `shared/predmet_deletion.py` (brisanje), `scripts/proof_direct.py` (skripta). Nijedan frontend ne poziva `dodaj-vezu` (PROVEN, `git grep`).

| Provera | Rezultat |
|---|---|
| Upis beleške `POST /firma-memorija/dodaj` | već štićen (CONF-011: `predmet`/`klijent` mora biti korisnikov, 404) — PROVEN iz koda, bez izmene |
| `dodaj-vezu`, tuđ `from_type=predmet` | **pre: 200 + upis**; posle: 404, bez upisa — PROVEN |
| `dodaj-vezu`, tuđ `to_type=predmet` | pre: 200; posle: 404 — PROVEN |
| `dodaj-vezu`, tuđ klijent na `from`/`to` | pre: 200; posle: 404 — PROVEN |
| sopstveni `predmet_id` + tuđ čvor | pre: 200; posle: 404 — PROVEN |
| `predmet_id` izostavljen + tuđ čvor | pre: 200; posle: 404 — PROVEN |
| tuđ `predmet_id` | 404 i pre i posle (postojeća zaštita) — PROVEN |
| tuđ vs nepostojeći čvor | identičan status i telo (bez proročišta) — PROVEN |
| vlasnik: svoj klijent → svoj predmet | 200, vidljivo vlasniku — PROVEN |
| opšta veza (argument → sudija) | 200 za svakog člana (postojeći ugovor) — PROVEN |
| delegat | upis kroz čvor odlučuje se ISTO kao kroz `predmet_id` (vlasnik; postojeći CONF-011 ugovor za upis) — PROVEN; čitanje delegatu otvara, opoziv odmah zatvara — PROVEN (RH001) |
| zaobilaženje tipa (`Predmet`, ` predmet`) | 400 (`_VALID_TYPES` tačno poklapanje); čitanje koristi isto tačno poklapanje — PROVEN iz koda |

**Popravka (RH002, `9dac6774`):** `routers/memory_graph.py` `dodaj_vezu` — čvor tipa `predmet`/`klijent` u `from_id`/`to_id` prolazi kroz `shared.ownership.zahtevaj` (isti vlasnik pravila i isti 404 kao `firma-memorija/dodaj`). 8 linija koda; nema nove semantike deljenja.

### A3 — zaštita pri čitanju
- `tests/test_rh001_legacy_memory_acl.py` (17 testova, od toga 7 parametrizovanih slučajeva `dodaj-vezu`; zajedno sa Phoenix memorijskim testom 23 passed): za svaku legacy čitajuću rutu i chat kontekst B ne vidi nijednu A-ovu tajnu; B-ovi odgovori su **bajt-identični** u svetu SA i BEZ A-ovih podataka (status, telo, broj, redosled; i prompt modela) — pokriva curenje kroz `count`/`limit` (`?limit=1` slučajevi).
- Zaštita od prazne provere: test pada ako ijedan odgovor bude 401/403/429.
- Opšta memorija kancelarije (sudija, opšta veza) ostaje vidljiva i potvrdiva kolegi — PROVEN.
- Greška ACL upita → ruta vraća grešku, chat bez memorije (zatvoreno) — INFERRED iz koda (`memorija_vidljivost` propušta izuzetak; `api._fetch_firm_memory_context` ga hvata u spoljnom `except` i vraća bez memorije).
- Law Brain (NS008) koristi isti modul: `shared/memorija_vidljivost.py`, `routers/firm_memory.py`, `routers/memory_graph.py` su bajt-identični između hotfix-a i `rh001-ns008` (PROVEN, `git diff`), pa popravka ne menja Law Brain autorizaciju.

### A4 — testovi, Docker, tajne
- Pre (na `99d2c6b9`): 6/7 RH001 testova padaju; 8 RH002 testova pada (200 + upis). Posebna proba: B-ov tekst se pojavljuje u A-ovom `/entitet` odgovoru i u A-ovom `/upit` promptu — PROVEN.
- Posle: incident + Phoenix: **23 passed**. Okolni bezbednosni skup (37 fajlova: ownership/ACL/delegacija/tenant/trust boundary/error disclosure/Phoenix…): **643 passed, 1 failed** na hotfix-u i **643 passed, 1 failed** na `main` — isti pad (`test_ca_trust_boundary::test_M19_dokaz_prezivljava_granu_sa_predmetom`), postojeći dug.
- CI: vidi §4.
- **gitleaks 8.30.1** (zvanično izdanje, SHA-256 proveren prema `checksums.txt`), `git log main..HEAD`: **no leaks found** sa konfiguracijom repoa, i **no leaks found** sa podrazumevanim pravilima bez `.gitleaksignore` — PROVEN. Pokriva samo hotfix commite, ne celu istoriju (istorijski SEC-KEY-001 nalaz je ranije zatvoren).

Preostala neizvesnost: ponašanje na pravoj bazi (indeksi, 1000-redni upiti, latencija) — UNKNOWN do produkcione provere; lažna baza ne meri PostgREST semantiku `in_()` nad stvarnim tipovima.

## 4. Produkcioni paket

- **PR #11** (DRAFT) `hotfix/rh001-memory-acl → main`: https://github.com/benny13n-creator/vindex-ai/pull/11 — bez NS006/NS007/NS008/RH001 feature koda; bez migracije; bez novih env promenljivih.
- Izmenjeni fajlovi: `shared/memorija_vidljivost.py` (nov), `routers/firm_memory.py`, `routers/memory_graph.py`, `api.py`, `tests/test_rh001_legacy_memory_acl.py` (nov), `tests/test_phoenix_mission_003_institutional_memory.py` (fixture dobija kolone koje prava tabela ima; nijedna provera uklonjena).
- **CI (hotfix `9dac6774`)** — poređenje po tačnom identitetu testa sa `main` (Test Suite 37964409178, Parity 37964409248):

| Run | Job | Padovi (main → hotfix) | Prošlo (main → hotfix) | NOVI padovi | Status |
|---|---|---|---|---|---|
| Test Suite 38066203225 | Python 3.11 | 175 → 175 | 7860 → 7877 | 0 | PASS (PROVEN) |
| Test Suite 38066203225 | Python 3.13 | 175 → 175 | 7860 → 7877 | 0 | PASS (PROVEN) |
| Parity 38066204665 | full suite u produkcionom 3.11 kontejneru | 197 → 197 | 7320 → 7337 | 0 | PASS (PROVEN) |
| Parity 38066204665 | Build production image + boot-check (OCR srp) | 0 | 17 passed | 0 | PASS (PROVEN) |
| Parity 38066204665 | Byte-compile 3.11 | 0 | — | 0 | PASS (PROVEN) |

+17 prošlih = tačno dodati testovi incidenta. Nijedan test nije preskočen, obrisan ni oslabljen. Zaključak workflow-a je „failure" samo zbog postojeće crvene bazne linije `main` (175/197).

- **Rollback:** samo kod, bez šeme → Render „Rollback" na `99d2c6b`, ili `git revert -m 1 <merge>`. Rollback ponovo otvara propust.
- **Produkciona verifikacija:** `/health` = merge SHA; sintetički nalozi A/B u posebnoj test kancelariji (nikad pravi klijenti); matrica iz PR #11; brisanje sintetičkih podataka.
- **Praćenje:** 5xx na `/api/firma-memorija/*` i `/api/memory-graph/*` (Render log, Sentry) — ACL greška se sada vidi kao 500, ne kao podatak; stopa 404 na `dodaj-vezu`/`potvrdi`/`DELETE`; latencija `/sve` i `/pretrazi`.

### Istorijski obim izloženosti — UNKNOWN
- Ove rute **nisu** u `shared/audit.py` `_AUDIT_PATHS` (PROVEN iz koda): nema zapisa po korisniku ko je šta čitao. Chat audit (`audit_log`) čuva samo hash upita, ne ubačenu memoriju. Render HTTP logovi (ako su još u periodu čuvanja) imaju putanju i status, ne sadržaj.
- `memory_graph_edges` nema kolonu autora (PROVEN: `dodaj_vezu` ne upisuje `user_id`): eventualno ranije ubačene veze ne mogu se pripisati.
- Odsustvo prijave incidenta NIJE dokaz da izloženosti nije bilo.
- Prvi korak koji čuva privatnost: founder sam, u Supabase SQL editoru, izvršava read-only brojanja (samo brojevi, bez sadržaja; ništa se ne kopira u AI sisteme) — koliko kancelarija ima više od jednog AKTIVNOG člana i koliko predmetnih/klijentskih beleški i veza postoji u njima. Ako je broj takvih kancelarija 0, stvarna površina izloženosti je bila prazna. Upite agent ne izvršava (nema pristup bazi) i ne šalje se migracioni SQL.
- Obaveze obaveštavanja klijenata / prijave incidenta (npr. ZZPL, poverilac poverljivosti advokatske tajne) agent NE procenjuje — za odluku foundera i pravnu procenu.

## 5. Graf zavisnosti V2 izdanja

Probna spajanja bez menjanja ijedne grane (`git merge-tree --write-tree`, PROVEN):

| hotfix → | rezultat |
|---|---|
| NS006 `dac1f6dd` | čisto |
| NS007 `deac5d99` | čisto |
| NS008 `79c1071b` | čisto |
| rh001-ns006 | čisto |
| rh001-ns007 | čisto |
| rh001-ns008 (pre RH002) | konflikt samo u `tests/test_rh001_legacy_memory_acl.py` (add/add — razlika jedino u import liniji harness-a) |
| rh001-ns008 (posle RH002 merge-a) | **čisto** (hotfix je predak) |

RH002 je spojio hotfix u `rh001-ns008` (merge commit, ne rebase): kod je bajt-identičan hotfix-u, test se razlikuje samo u importu harness-a (`ns008_fake`). Time RH002 popravka upisa NIJE ostala samo na main liniji — prenesena je i na V2 kraj lanca.

Spajanje upstream grane NE prenosi popravke automatski: originalne NS006/NS007/NS008 grane NE sadrže ni RH001 ni hotfix.

**PR #10 pokazuje na originalni NS008 (`79c1071b`)** — bez RH001 i RH002. GitHub ne dozvoljava promenu head grane PR-a. Najmanja ispravka (preporuka, NIJE izvršena): founder odobrava **fast-forward** svake release grane na njen RH001 par (`NS006 → rh001-ns006`, `NS007 → rh001-ns007`, `NS008 → rh001-ns008`). FF ne prepisuje istoriju (svaka rh001 grana je potomak svoje NS grane — PROVEN), postojeći PR #9 i #10 automatski dobijaju popravke, nema force-push-a. Alternativa bez diranja release grana: novi PR-ovi `rh001-nsX → nsX`.

### Kontrolisani redosled (svaki korak = odobrenje foundera)

| Korak | Base ← Head | Testovi pre spajanja | Migracija | Invarijante | Odobrenje |
|---|---|---|---|---|---|
| 1. Hotfix | `main ← hotfix/rh001-memory-acl` (PR #11) | CI po imenu vs main; incident suite | nema | §3 matrica | merge + deploy + produkciona verifikacija |
| 2. NS006 | `main ← NS006` (PR #9, posle FF na rh001-ns006) | Test Suite + Parity po imenu vs novi main; V2 NG zeleno | 135 (ASSUMED primenjena) | `/app` V2, `/app-legacy` radi; memorijski ACL i dalje važi posle spajanja (incident suite na rezultatu spajanja) | FF + merge + deploy |
| 3. NS007 | novi PR `main ← NS007` (posle FF na rh001-ns007) | isto + `test_rh001_scheduler_crash_window`, `test_rh001_hearing_prep_authority` | **136 pre deploy-a** (aditivna, vidi §6) | autonomija ugašena dok nema tajne; A5 granica | 136 + merge + deploy; Cron odvojeno |
| 4. NS008 | novi PR `main ← NS008` ili PR #10 retarget na `main` (posle FF na rh001-ns008) | isto + `test_ns008_*`, `test_rh001_law_brain_authority`, V2 NG | nema (137 NE postoji) | Law Brain ACL = memorijski ACL; opozvano znanje isključeno | merge + deploy |

Ništa nije spojeno, rebase-ovano ni fast-forward-ovano.

## 6. NS007 — preostale kapije

- **Migracija 136** (`migrations/136_autonomy_work_items.sql`, 259 linija) — INFERRED iz pregleda: samo NOVI objekti (`CREATE TABLE/INDEX IF NOT EXISTS` za `autonomy_cycles`, `autonomy_work_items`; RLS; `CREATE OR REPLACE FUNCTION autonomy_claim_work_item`; `REVOKE` od `anon`/`authenticated`, `GRANT` samo `service_role`, `authenticated` samo `SELECT` sopstvenih stavki). Ne menja postojeće tabele → bezbedna za primenu PRE deploy-a NS007 koda; `main` kod je ignoriše. Produkcioni status: **UNKNOWN** (ASSUMED nije primenjena).
- **Env ugovor** (imena, iz koda; vrednosti nisu čitane): `AUTONOMY_CRON_SECRET` (obavezna, ≥ 32 znaka, inače ruta 401 — fail-closed), `AUTONOMY_BUDGET_PER_ORG_DAILY` (20; neispravno = nijedno plaćeno izvršenje), `AUTONOMY_LEASE_SECONDS` (300, granice 30–3600), `AUTONOMY_MAX_ITEMS_PER_CYCLE` (25), `AUTONOMY_ITEM_TIMEOUT_SECONDS` (120), `AUTONOMY_HEARING_WINDOW_DAYS` (**1**, granice 0–7). Cron servis: samo `AUTONOMY_TRIGGER_URL` + `AUTONOMY_CRON_SECRET`.
- **Render Cron plan:** `docs/v2-recovery/NS007_RENDER_CRON_PLAN.md` — NIJE napravljen. Opcije: A `0 3 * * *` (noćno), B `0 3,10 * * *`, C `0 6-17 * * 1-5`.
- **Idempotentnost / zakup / budžet:** prozor = UTC sat, `UNIQUE(window_key)` → drugi okidač u istom satu `SKIPPED`; posao postaje RUNNING samo kroz `autonomy_claim_work_item` (zakup + rezervacija budžeta atomski); isti okidač = jedan posao — PROVEN testovima NS007 (RH001: 237 passed, 11 skipped) i CI.
- **Prozor pada (ispravka RH001 formulacije):** pad posle zauzimanja ostavlja ciklus RUNNING samo za taj UTC sat; sledeće **zakazano** okidanje radi normalno, bez duplog rada (PROVEN, `test_rh001_scheduler_crash_window`). Gubitak = **jedan ciklus kadence, ne „najviše jedan sat"**:
  - A (noćno): pripreme kasne **~24 h** — uz podrazumevani prozor od 1 dana, ročište zakazano za sutra dobija pripremu tek u 03:00 UTC na sam dan ročišta (bez večeri za pregled);
  - B: kasnjenje do ~7 h ili ~17 h;
  - C: do 1 h radnim danima, ali pad u petak 17:00 UTC kasni do ponedeljka 06:00 UTC.
- **Poslovni zahtev:** nije dokumentovan koliko unapred advokat mora da ima pripremu. Bez toga kadenca se NE bira ovde. Uz opciju A, `AUTONOMY_HEARING_WINDOW_DAYS ≥ 2` čini jedan propušten ciklus podnošljivim (INFERRED).
- **Praćenje (potrebno pre uključivanja):** Render obaveštenje za neuspešan cron run (skripta vraća ≠ 0 na 401/500/503/timeout); upozorenje za `autonomy_cycles` u RUNNING duže od 2× trajanja ciklusa; Sentry na `[AUTONOMY]`; dnevni broj `usage_events(feature='autonomy')` naspram budžeta.
- **Pravne tvrdnje:** Hearing Prep forma + `shared/pravni_autoritet` (RH001) — PROVEN.
- **A5 granica:** prihvati/odbaci menja samo stanje pregleda; ne šalje, ne podnosi, ne izvršava Case Action (PROVEN iz koda `routers/autonomy.py` i NS007 testova). Autonomija je A2 (Prepare), u skladu sa PAD-001 §G.

## 7. NS008 — preostale kapije

- **Poreklo koda/PR-a:** popravke su na `rh001-ns008`; PR #10 nije (§5).
- **Law Brain ↔ hotfix:** isti modul, bajt-identičan (§3) — PROVEN.
- **Opozvano znanje:** `services/law_brain.vazece_overe` u `retrieve_documents` i Law Brain-u; `test_ns008_t21_revocation` — PROVEN. Fizičko brisanje iz Pinecone-a NIJE rađeno.
- **Nepodržan pravni autoritet:** `PRAVNI_AUTORITET_BEZ_IZVORA` u sintezi; `test_rh001_law_brain_authority` — PROVEN.
- **Idempotentna sinteza i krediti:** `test_ns008_t12_synthesis`, `test_ns008_t26_cost` — PROVEN (lokalno).
- **Lokalno na `rh001-ns008` posle RH002 merge-a:** 30 NS008/RH001 test fajlova — **340 passed** — PROVEN. CI: `rh001-ns008` `4b3b4da6`: Test Suite 38066321126 — 3.11 i 3.13: 175 padova, 8479 prošlo, **0 novih**; Parity 38066322857 — 197 padova, 7939 prošlo, **0 novih**, Docker build/boot 17 passed; **V2 NG 38066541175 zeleno** — PROVEN.
- **Performanse:** `test_ns008_t22_scale` meri ponašanje na sintetičkom skupu; p95 na reprezentativnim produkcionim podacima — **UNKNOWN** (produkcioni podaci nisu preuzimani, po direktivi).

## 8. Zaštita grana (preporuka — NIJE primenjena)

Stanje (PROVEN): repo javan, 1 saradnik (founder, admin), 0 ruleset-a, `main` bez zaštite, GitHub Actions dozvoljava sve akcije, 4 Render environment-a bez pravila. Render deploy-uje `main` (INFERRED iz `/health` = `main`), pa je zaštita `main` = zaštita produkcije.

Ključna činjenica: agent radi sa **founderovim admin kredencijalom** (`git credential`). Svako „admin bypass" pravilo važi i za automatizaciju.

Minimalni ruleset (dostupan za javne repoe na besplatnom planu):
1. **`main`:** zabrana force-push-a; zabrana brisanja; obavezan PR (0 obaveznih odobrenja — jedini saradnik ne može da odobri sopstveni PR); obavezni statusi SAMO trenutno zeleni poslovi: `Production Runtime Parity / Byte-compile on production Python (3.11)` i `… / Build production image and boot-check it` (NE `Test Suite` dok je bazna linija crvena — inače trajno blokira izdanja); **bez bypass liste**.
2. **`feature/vindex-v2-ns00*`, `hotfix/*`:** zabrana force-push-a i brisanja.
3. Provera posle primene: `git push origin HEAD:main` sa test commitom mora biti odbijen; PR sa zelenim obaveznim poslovima mora biti spojiv iz UI-ja; `git push --force` na NS granu odbijen.

Ograničenje: ruleset sprečava direktan push i prepisivanje, ali NE sprečava da neko sa admin tokenom spoji PR preko API-ja. Kontrola nad spajanjem ostaje proces: agent ne spaja (ova direktiva) i ne dobija zaseban token sa većim pravima. Promena podešavanja traži posebno odobrenje foundera.

## 9. Odluke foundera

1. Odobriti spajanje PR #11 u `main` i deploy, pa sprovesti produkcionu verifikaciju iz §4.
2. Pokrenuti read-only brojanja izloženosti (§4) i, uz pravni savet, odlučiti o obaveštavanju.
3. Odobriti fast-forward NS006/NS007/NS008 na rh001 parove (ili nove PR-ove) — §5.
4. NS007: kada i da li primeniti 136; kadenca (A/B/C) i `AUTONOMY_HEARING_WINDOW_DAYS`; tek onda Cron.
5. Ruleset iz §8.
6. Otvoreno iz RH001: da li su profili klijenata (`client_memory`) namerno deljeni u kancelariji.

## 10. Izričita ne-dejstva

- NIJE spojeno ništa u `main` ni u release grane; nije rađen rebase, fast-forward ni force-push.
- NIJE deployovano ništa (produkcija ostaje `99d2c6b`).
- NIJE primenjena nijedna migracija (136 ni bilo koja); migracija 137 nije napravljena.
- NIJE napravljen ni pokrenut Render Cron; env promenljive nisu čitane ni menjane.
- NIJE obrisan nijedan Pinecone vektor ni red baze; nijedna grana nije obrisana.
- NISU menjane GitHub zaštite.
- NISU čitani pravi klijentski podaci ni produkcioni skupovi; ništa iz produkcije nije poslato AI sistemima.
- Pushovano (izolovane grane): `hotfix/rh001-memory-acl` `9dac6774`; `feature/vindex-v2-rh001-ns008` (merge `4b3b4da6` + ovaj dokument). Otvoren Draft PR #11.

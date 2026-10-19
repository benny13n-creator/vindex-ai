# NIGHT SPRINT IV — završno zatvaranje (O1, O2, O3, G1, G2)

**Konačni status: B. NS4 CODE COMPLETE — RELEASE APPROVAL REQUIRED**

Svih pet stavki je ispravljeno i dokazano lokalno (O2 bez migracije; O1, G1/G2 i O3 kroz tri aditivne migracije
138–140, dokazane nad stvarnim PostgreSQL-om). Kod G1/G2 i O3 **zahteva** migracije 139 i 140 — prema pravilu
„produkcijski DDL je zaseban gejt", migracije NISU izvršene na produkciji, pa se **kod ne spaja i ne pušta** dok
osnivač ne odobri i ne primeni migracije. Ništa nije spojeno u `main` i ništa nije pušteno.

---

## 1. Identitet

| Stavka | Vrednost | Status |
|---|---|---|
| Osnova (`origin/main`, produkcija) | `cc8bd5485210f0a9ea67d6f725fc2060a2957b50` | PROVEN (`git fetch`, `/health` → `"commit":"cc8bd54"`) |
| Prethodni NS4 commitovi | `2388df33` (NS4), `28f7535f` (NS4R) | PROVEN |
| Završni commit koda (ova faza) | `ed7c7ee299d128cce3ab7ca657a05a8c99054c84` (roditelj `28f7535f`); izveštaj u sledećem commitu | PROVEN |
| Grana | `night/ns4-institutional-intelligence` | PROVEN |
| Razilaženje `main` | nema (`merge-base HEAD origin/main` = `cc8bd548`) | PROVEN |

## 2. PRE-FLIGHT

| Provera | Nalaz | Status |
|---|---|---|
| Grana, HEAD, čist status | `night/ns4-institutional-intelligence`, `28f7535f…`, čisto | PROVEN |
| `origin/main` / merge-base / poreklo | `cc8bd548` / `cc8bd548` / `cc8bd548 → 2388df33 → 28f7535f` | PROVEN |
| Nepovezani commitovi ili fajlovi | nema (samo 2 NS4 commita iznad osnove) | PROVEN |
| Mehanizam migracija u produkciji | ručno, osnivač pokreće SQL u Supabase (nema automatskog alata u repou; `migrations/NNN_*.sql`) | INFERRED (ustaljena praksa, memorija projekta; nijedan CI korak ne primenjuje SQL) |
| Platforma, servis, izvor | Render web servis iz `main`; `/health` vraća SHA | PROVEN (SHA), INFERRED (Render iz istorije OPERATION LIVE) |
| Push na `main` → automatski deploy | da (Render AutoDeploy, ~60 s posle spajanja PR #16/#46) | INFERRED (istorijski posmatrano, ne ponovo meren danas) |
| Staging/test okruženje | ne postoji zaseban staging; izolovan lokalni PostgreSQL 17 za dokaze | PROVEN |
| Rollback | Render „Rollback" na prethodni deploy ili revert commit na `main` | INFERRED |
| Produkcijska šema relevantnih tabela | poklapa se sa migracijama (OpenAPI, samo čitanje): `staging_memory` bez `promocija_*`, nema funkcija iz 139/140, 137 primenjena | PROVEN |
| Broj redova (2026-10-19, samo čitanje) | `outcome_log` 0, `case_patterns` 0, `client_memory` 0, `staging_memory` 0, `kancelarije` 0, `kancelarija_clanovi` 0, `memory_entries` 0, `memory_graph_edges` 0, `workflow_instances` 0, `workflow_steps` 0, `zadaci` 2, `workflow_templates` 4 | PROVEN |
| Efektivna prava `anon` | SELECT nad svim tabelama memorije (PostgREST 200 `[]`, ne „permission denied") | PROVEN (javni ključ iz `static/vindex.js`) |
| Efektivna prava `authenticated` | nije mereno direktno (nema sintetičkog naloga; JWT se ne kuje produkcijskom tajnom) | UNKNOWN — Supabase podrazumevano isto kao `anon`; migracija 138 oduzima obe |

## 3. Odluka o obimu (Faza 1)

| Stavka | Dostupno u produktu | Beta tok | Bezbednost / integritet | Rešivo bez šeme | Šema nužna | Pokušaj obaranja plana |
|---|---|---|---|---|---|---|
| **O1** RLS `aktivan` + grana `admin_uid` | da: svaki prijavljen korisnik može da napravi kancelariju (`POST /api/kancelarija/kreiraj`) i čita preko Data API-ja | ne (solo beta), ali dostupno | **poverljivost** (admin čita tuđe beleške uz predmet/klijenta) | ne — pravo pristupa je u bazi | da (REVOKE) | zamena `aktivan`→`ACTIVE` dokazano ŠIRI pristup (test); REVOKE ne dira backend (service_role) ni frontend (ne koristi tabele) |
| **O2** `client_memory` po imenu | API (bez UI potrošača) | ne, ali dostupno | **poverljivost** (kolega čita/menja tuđi profil) | **da** (postojeći `klijent_id` + `klijenti.user_id`) | ne | ključ `klijent:<uuid>` pretvara postojeći UNIQUE(kancelarija, klijent_ime) u jedinstvenost po identitetu — bez migracije, bez sudara istoimenih |
| **G1** ne-atomski preračun | da (`/api/learning/outcome`) | da (zatvaranje predmeta sa ishodom) | **integritet** (zastareo zbir) | ne — potrebna transakcija | da (funkcija) | „brava samo na preračunu" ne pokriva pad između upisa ishoda i preračuna → ishod + zbir u JEDNOJ transakciji |
| **G2** bez straničenja | da | da | **integritet** (prekid iznad 1000 redova) | delimično | rešeno istom funkcijom | skupovni SQL bez limita |
| **O3** oporavak promocije | da (V2 odobrenje nacrta) | da | dostupnost; R2 već fail-closed | ne — nema kolone za „pokušaj u toku" (`pinecone_indexed` NOT NULL, nema `updated_at`) | da (2 kolone + 2 funkcije + indeks) | bez tokena: istovremeni pokušaji i pokušaj prekinut padom se ne razlikuju |

## 4. Dispozicije

| Stavka | Dispozicija | Uslov važenja |
|---|---|---|
| O1 | **FIXED** (migracija 138, dokazano na PostgreSQL-u) | deluje tek kada osnivač primeni 138; do tada rupa POSTOJI u produkciji (nezavisno od ovog release-a; 0 kancelarija danas) |
| O2 | **FIXED** (samo kod) | deluje sa deploy-om koda |
| G1 | **FIXED** (migracija 139 + kod) | kod zahteva 139 |
| G2 | **FIXED** (migracija 139 + kod) | kod zahteva 139 |
| O3 | **FIXED** (migracija 140 + kod + V2) | kod zahteva 140 |

Nijedna stavka nije prijavljena kao „SAFELY CONTAINED".

### 4.1 O2 — profil klijenta samo vlasniku, po identitetu
- `routers/firm_memory.py`: `_moj_klijent` — UUID klijenta čiji je vlasnik pozivalac, nije obrisan; inače `None`
  (isti ishod za tuđ/nepostojeći/neispravan/obrisan). Greška baze se propušta (503, bez detalja).
- `GET /klijent/{klijent_ref}`: samo sopstveni klijent po identitetu; ime → prazan odgovor, bajt-identičan
  nepostojećem klijentu. `POST /klijent/sacuvaj`: obavezan `klijent_id`; tuđ → 404 bez upisa; ime ne učestvuje;
  istovremeni prvi upis → UNIQUE → ažuriranje pobednikovog reda. `kontekst-za-ai`: klijentski deo samo uz
  `klijent_id` sopstvenog klijenta; pad provere → izostavljeno.
- Stari redovi (ključ = ime) se ne služe i ne spajaju (produkcija: 0 redova).
- Promena ugovora: pretraga profila po imenu više ne postoji (UI potrošača nema — grep `static/`, `frontend-v2-ng/`).
- Deljen/delegiran klijent: postojeći model nema deljenje klijenata (`shared/memorija_vidljivost`: klijent → samo
  vlasnik) — nije izmišljena nova politika.

### 4.2 O1 — migracija 138
- REVOKE ALL od `anon`, `authenticated` na: `memory_entries`, `memory_graph_edges`, `client_memory`,
  `partner_profiles`, `judge_patterns`, `firm_style_profile`, `workflow_instances`, `workflow_steps`.
- Politike se NE menjaju (mrtve grane `aktivan` ostaju mrtve; nema „zamene stringa").
- Namerno van obima: `zadaci` (žive grane su kreirao/dodeljen), `workflow_templates` (sistemski šabloni).
- Bez SECURITY DEFINER zaobilaženja.

### 4.3 G1/G2 — migracija 139
- `zabelezi_ishod_predmeta(...)`: brava `pg_advisory_xact_lock` po korisniku → vlasništvo predmeta i vrsta spora
  čitani u transakciji → upsert `outcome_log` → zbir nove i stare vrste skupovno iz `outcome_log`. Greška → rollback
  svega. SECURITY INVOKER, `search_path` fiksiran, EXECUTE samo `service_role`; INSERT/UPDATE/DELETE na
  `outcome_log`/`case_patterns` oduzet od `anon`/`authenticated` (SELECT ostaje).
- `routers/learning.py`: Python preračun (`_preracunaj_obrasce`, `_STRANA`) uklonjen; ruta zove jedan RPC.
- Drugi pisac `services/learning_engine.log_outcome` nema pozivaoca (mrtav kod, piše nepostojeću kolonu
  `ukupno_predmeta`) — nije diran; zabeleženo.

### 4.4 O3 — migracija 140 + kod + V2
- `staging_memory.promocija_token`, `promocija_preuzeta_at`; `preuzmi_ponovni_upis_nacrta` (vlasnik, `approved`,
  overen, nije indeksiran, ocena ≥ prag, nema aktivnog pokušaja ili mu je istekao rok od 600 s);
  `zavrsi_promociju_nacrta` (samo isti token; `pinecone_indexed=true` samo ako je i dalje odobren).
- Delimični UNIQUE indeks `predmet_dokumenti(storage_path) WHERE storage_path LIKE 'draft/staging/%'`; knjigovodstveni
  red nacrta ima stabilnu putanju `draft/staging/<id>` i ažurira se pri ponovnom pokušaju.
- Prvo odobrenje uzima token u istom prelazu pending → approved (ponovni upis ne može uporedo).
- `POST /api/staging/{id}/ponovi-upis`; lista vraća `ponovni_upis_moguc`; V2 prikazuje dugme samo tada.
- Garancija: **bar jednom + idempotentno**, NE „tačno jednom" preko PostgreSQL-a i Pinecone-a. Isti tekst → isti
  ID-evi vektora (`shared/vector_identity`). Pinecone uspeo + baza pala → pokušaj ostaje „u toku" (ne služi se),
  posle roka nov pokušaj prepisuje iste vektore. Baza napredovala + Pinecone pao → nije označeno kao potpuno.
- Nije uveden pozadinski radnik ni orkestracija.

## 5. Dokazi

### 5.1 RED na `28f7535f` (novi testovi nad starim kodom)
Novi i izmenjeni testovi rute pokrenuti nad izdvojenom kopijom `28f7535f` (`C:/vindex-qa/ns4f/red_na_28f7535f.log`):
- `test_ns4f_o2_profil_klijenta.py`: **23 pada, 2 prolaze** — prolaze samo kontrole „druga kancelarija" (Y), koju je
  stari kod već štitio. Jedan test je u prvoj verziji prolazio na starom kodu iz pogrešnog razloga (stari model je
  odbijao zahtev bez `klijent_ime`) — pooštren da šalje i ime; sada pada na starom kodu.
- `test_ns4f_o3_ponovni_upis.py`: 13 pada (ruta ne postoji / nema oporavka); 3 „404 za tuđ/nepostojeći" prolaze i
  na starom kodu (ruta ne postoji → 404) — negativne kontrole, ne dokaz ispravke.
- `test_ns4_t2…::test_kolega_ne_vidi_profil_tudjeg_klijenta`: pada (bio strogi xfail).
- `test_ns4r_granice_dokaz.py`, `test_ns4_t3…::test_zbir_racuna_jedna_transakcija…`: padaju (ne-atomski put postoji).
- O1: stanje PRE 138 reprodukovano nad PostgreSQL-om (`test_pre_138_admin_kancelarije_cita_tudje_poverljive_redove`).

### 5.2 Stvarni PostgreSQL 17.9 (izolovan lokalni klaster, port 54329, pravi SQL iz `migrations/`)
`VINDEX_PG_TEST_DSN=postgresql://postgres@127.0.0.1:54329/postgres` — **130 passed** (bez promenljive: 130 skipped).
- `test_ns4f_pg_ishod.py` (G1/G2, 19): ispravka pobeda→poraz, ponovljen zahtev, promena vrste spora u istoj
  transakciji, deduplikacija/prvih 10/0 faktora/nagodba, tuđ predmet (P0002, ništa upisano), ishod drugog korisnika
  (42501), **izuzetak usred preračuna → ni ishod nije upisan**, **prekid veze pre commit-a → ništa**, **drugi pisac
  čeka bravu (pg_locks) i vidi prvi upis → (1,1,2)**, 8 niti × 6 upisa sa ispravkama i promenama vrste → 0 odstupanja
  od proročišta, unakrsna promena vrste bez zastoja, **tačno 1000 i 1300 faktora** sa zastarelim postojećim redovima,
  anon/authenticated ne izvršavaju funkciju i ne pišu tabele (i direktno `has_function_privilege`), vlasnik i dalje
  čita svoj zbir, migracija ponovljiva.
- `test_ns4f_pg_promocija.py` (O3, 20): 6 istovremenih preuzimanja → tačno 1; pending/rejected/ispod praga/već
  indeksiran/bez overe/tuđ → ne preuzima se; rok napuštenog pokušaja + zastareo token ne zatvara noviji; opoziv
  tokom pokušaja → nije indeksiran; neuspeh čisti token; jedinstven knjigovodstveni red (23505), stari oblik putanje
  netaknut; EXECUTE samo service_role; migracija ponovljiva, postojeći redovi netaknuti.
- `test_ns4f_pg_rls.py` (O1, 91): matrica 9 uloga × 8 tabela posle 138 → 42501; upis takođe odbijen; service_role
  čita; PRE 138 admin čita tuđe; **kontraprimer** zamene `aktivan`→`ACTIVE`; `zadaci`/`workflow_templates` nepromenjeni.

### 5.3 Mutacije (izdvojena kopija, binarno, vraćanje proverено)
`C:/vindex-qa/ns4f/mutacije.py` + `mutacije2.py` (logovi `mutacije_prolaz1.log`, `mutacije_prolaz2.log`):
**25 mutacija, sve uhvaćene posle drugog prolaza.**

| Mutacija | Rezultat |
|---|---|
| G1a bez brave po korisniku | uhvaćena (prvi put je test VISIO umesto da padne — ojačan: `finally` + `lock_timeout`) |
| G1b bez nuliranja pre preračuna; G1c bez stare vrste; G2 bez „prvih 10/dedup"; G1e bez provere vlasništva | uhvaćene |
| G1d EXECUTE ostaje korisniku | **prvi prolaz NIJE uhvaćena** — poziv je i dalje padao zbog drugog sloja (oduzet upis u tabele); dodata direktna provera `has_function_privilege` → uhvaćena |
| O3a bez provere aktivnog pokušaja; O3b završetak bez tokena; O3c bez jedinstvenog indeksa; O3d bez praga; O3e indeksiran posle opoziva; O3j EXECUTE preuzimanja | uhvaćene |
| O1a `client_memory` van REVOKE; O1b `workflow_instances` van REVOKE | uhvaćene (10 padova svaka) |
| O2a samo filter vlasnika uklonjen; O2a2 samo poređenje vlasnika uklonjeno | **NISU uhvaćene pojedinačno** — vlasništvo se proverava u dva sloja (upit + poređenje); O2e (OBA sloja) → uhvaćena (8 padova) |
| O2b stari red po imenu; O2c obrisan klijent; O2d AI kontekst po imenu | uhvaćene |
| O3f odobrenje bez tokena; O3g knjigovodstvo uvek nov red; O3h dugme ispod praga; O3i ruta ignoriše završetak | uhvaćene |

### 5.4 Kontraprimeri (zašto ne jednostavnije)
- Zamena `aktivan`→`ACTIVE`: B (aktivan član bez delegacije) vidi belešku uz A-ov predmet — `test_zamena_aktivan_u_active_bi_prosirila_pristup`.
- Brava samo na preračunu: pad između upisa ishoda i preračuna — rešeno jednom transakcijom; `test_prekid_procesa_pre_commit_ne_ostavlja_nista`, `test_izuzetak_usred_preracuna_vraca_i_ishod`.
- Bez tokena: istovremeni pokušaji — `test_podoban_nacrt_preuzima_tacno_jedan_od_istovremenih` (6 niti → tačno 1).

## 6. Izmenjeni postojeći testovi (bez slabljenja asertacija)
| Fajl | Izmena | Zašto |
|---|---|---|
| `tests/ns005_harness.py` | registruje Python verzije RPC-a 139/140 (`tests/ns4f_rpc_fake.py`) | ruta sada zove RPC; lažna baza ranije nije imala implementaciju (vraćala `[]`) |
| `tests/test_beta_gate_staging_approve_race.py` | dvojnik reda dobija `rpc` (ista semantika tokena kao SQL) | završetak promocije je RPC; MagicMock `rpc` bi vraćao MagicMock |
| `tests/test_ns4_t5_promocija_iskreno.py` | isto (1 red) | isto |
| `tests/test_vcr001_t05_nacrt_trajan.py` | proksi prosleđuje `rpc` | proksi je prosleđivao samo `table` |
| `tests/test_ns4_t2_kancelarija_granica.py` | uklonjen strogi xfail O2 | test sada stvarno prolazi (na `28f7535f` pada) |
| `tests/test_ns4_t3_ishod_brojaci.py` | test Python straničenja zamenjen testom ožičenja | mehanizam `_STRANA` uklonjen; svojstvo (granica 1000 / >1000) prebačeno u PG test |
| `tests/test_ns4r_granice_dokaz.py` | strogi xfail G1/G2 zamenjeni čuvarom „nema ne-atomskog puta" | svojstva G1/G2 sada prolaze nad stvarnim PostgreSQL-om (`test_ns4f_pg_ishod.py`) |
| `tests/test_sprint1_background_tasks.py` | sidro izvornog koda `table("outcome_log").upsert(` → `supa.rpc(_RPC_ISHOD` | mesto upisa promenjeno; asercije iste |

## 7. Regresija
| Skup | Rezultat |
|---|---|
| Novi NS4F testovi rute (O2 25, O3 16) | 41 passed |
| PostgreSQL dokazi | 130 passed |
| Ciljni skup (`test_ns4*`, `test_ns008*`, `test_rh001*`, staging/VCR001/disclosure/sprint1) | 520 passed, 130 skipped (PG bez DSN) |
| Pun skup, osnova `cc8bd548` (merenje 2026-10-18, ista konfiguracija; `main` nepromenjen od tada) | 16 failed, 11227 passed, 227 skipped, 2 xfailed |
| Pun skup, grana (radna kopija pre commita, sa PG dokazima, bez `FOUNDER_EMAILS`) | 17 failed, 11477 passed, 227 skipped, 2 xfailed |
| Poređenje ID-eva | 16 identičnih osnovi; **1 dodatni** = `test_web3_founder_access::test_F_izmena_ne_dira_tenant_ni_rbac` — test radi `git diff HEAD` i pada na NEKOMITOVANIM migracijama; posle commita `ed7c7ee2` prolazi (proveren) → **0 novih padova** |

Napomene: prvi pun prolaz je greškom pokrenut sa `FOUNDER_EMAILS=x@example.invalid` (29 padova, od toga 12 testova
osnivačkog pristupa zbog okruženja) — odbačen i ponovljen u konfiguraciji osnove. Jedini stvarni nalaz iz njega:
`test_sprint1_background_tasks::test_learning_outcome_failure_does_not_report_success` čita izvorni kod i sidrio se
na stari `table("outcome_log").upsert(` — presidren na `supa.rpc(_RPC_ISHOD`, asercije (HTTPException + „NIJE
zatvoren" + bez starog upozorenja) nepromenjene.
- Python 3.11.9: `py_compile` izmenjenih fajlova OK; import aplikacije na 3.11 lokalno nije moguć (zavisnosti nisu
  instalirane za 3.11) → CI `production-runtime`. Python 3.13: import i svi testovi OK. `node --check` OK.
  `git diff --check` čist. Pretraga tajni u izmenjenim fajlovima: čisto.
- Docker: nije dostupan lokalno → CI `production-runtime`.

## 8. Migracije — inventar, redosled, izvršenje

| # | Fajl | Zahteva ga kod | Kompatibilna sa trenutno puštenim kodom (`cc8bd548`) | Zaključavanje |
|---|---|---|---|---|
| 138 | `138_ns4_memorija_bez_direktnog_pristupa.sql` | ne (nezavisna) | da — backend koristi `service_role`, frontend ne čita ove tabele | kratka brava po tabeli, bez prepisivanja |
| 139 | `139_ns4_atomski_ishod_predmeta.sql` | **da** | da — dodaje funkciju; oduzima samo upis `anon`/`authenticated` (stari kod piše kao `service_role`) | kratka |
| 140 | `140_ns4_oporavak_promocije_nacrta.sql` | **da** | da — NULL kolone, funkcije, indeks samo za novi oblik putanje | `CREATE UNIQUE INDEX` čita `predmet_dokumenti` jednom (SHARE brava) |

**Redosled:** 138 → 139 → 140 (svaka u svojoj transakciji, idempotentne) → tek ONDA spajanje koda.
Primenjeno lokalno dva puta (ponovljivost dokazana), sa Supabase podrazumevanim pravima.
Bez DROP-a, bez prepisivanja podataka, bez masovnog backfill-a. Provera posle primene i povratak su u zaglavlju
svakog fajla. **Nijedna nije izvršena na produkciji.**

## 9. CI

Draft PR **#47** (https://github.com/benny13n-creator/vindex-ai/pull/47), head `16dbc3a4` (kod `ed7c7ee2` + izveštaj).
Poređenje ID-eva padova sa CI-jem osnove `cc8bd548` (isti poslovi):

| Posao | Grana (job id) | Osnova (job id) | ID-evi padova |
|---|---|---|---|
| pytest (Python 3.11) | 9 failed, 11058 passed, 219 skipped (118230434522) | 9 failed, 10936 passed, 90 skipped (117748418770) | identični, 0 novih |
| pytest (Python 3.13) | 9 failed, 11058 passed, 219 skipped (118230434047) | 9 failed, 10936 passed, 90 skipped (117748419042) | identični, 0 novih |
| Import app + full suite (3.11, prod) | 10 failed, 10533 passed (118230432993) | 10 failed, 10412 passed (117748419093) | identični, 0 novih |
| Byte-compile 3.11, Docker build + boot, SAST, semgrep, dependency-scan, secret-scan | success | — | — |

+129 preskočenih = PostgreSQL dokazi (CI nema PostgreSQL servis; lokalno 130 passed). Padovi osnove su postojeći,
nepovezani sa NS4 (isti ID-evi pre i posle). PR NIJE spojen.

## 10. Plan puštanja (posle odobrenja)
1. Osnivač primenjuje 138, 139, 140 u Supabase SQL editoru i pokreće provere iz zaglavlja (očekivani rezultati navedeni).
2. Ponovno čitanje šeme (OpenAPI): funkcije `zabelezi_ishod_predmeta`, `preuzmi_ponovni_upis_nacrta`,
   `zavrsi_promociju_nacrta` postoje; `staging_memory.promocija_*` postoje.
3. Spajanje PR-a u `main` → Render AutoDeploy (posmatrati, ne pokretati drugi).
4. Smoke (bez stvarnih predmeta klijenata):
   - `/health` → `commit` = SHA spajanja;
   - anon `GET /rest/v1/memory_entries?select=id&limit=1` sa javnim ključem → 401/42501 (ne više `200 []`);
   - neprijavljen `POST /api/learning/outcome` → 401; `POST /api/staging/<nepostojeći>/ponovi-upis` sa nalogom → 404;
   - `GET /api/firma-memorija/klijent/<ime>` → prazan profil;
   - sintetički nalog (ako osnivač odobri): ishod predmeta → `case_patterns` = provera (b) iz migracije 139 (0 razlika).
5. Logovi Render-a: bez novih izuzetaka `[LEARNING] upis ishoda nije uspeo` / `[STAGING_RETRY]`.

## 11. Povratak
- Kod: Render rollback na `cc8bd548` ili revert commita. Migracije 138–140 su kompatibilne sa starim kodom → šema
  se NE vraća pri vraćanju koda.
- Šema: samo ako je neophodno, po uputstvu iz zaglavlja (139/140: najpre vratiti kod; kolone `promocija_*` ostaju).

## 12. Preostala ograničenja (nisu blokeri ovog release-a)
- `authenticated` prava u produkciji nisu merena direktno (nema sintetičkog naloga) — 138 ih oduzima nezavisno od toga.
- Ugovor sa pravim modelom za „slične predmete" (pun id) nije meren (NS4R).
- `kljucne_odluke` u profilu klijenta: dva istovremena dopisivanja odluke mogu izgubiti jedno (čitanje-izmena-upis;
  isti obrazac kao ranije, samo vlasnik piše).
- Opoziv odobrenja tokom upisa: vektori mogu fizički ostati u Pinecone-u; ne služe se (`vazece_overe` traži
  `approved` + `pinecone_indexed`), brisanje je postojeći NS008 T21 put.
- PostgreSQL dokazi su lokalni (CI nema PostgreSQL servis); bez `VINDEX_PG_TEST_DSN` PG testovi se preskaču.
- Docker build/boot nije pokrenut lokalno (nema Docker-a) — pokriva CI `production-runtime`.
- Poznat pad zavisan od redosleda `test_ns008_t21_revocation::test_deaktivirana_beleska_nestaje` (i na osnovi).
- Učenje kancelarije NIJE potvrđeno u produkciji (0 ishoda, 0 kancelarija, 0 nacrta na overi).

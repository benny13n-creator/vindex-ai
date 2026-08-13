# §4 RETRIEVAL BYPASS SWEEP — popis svih putanja koje čitaju iz Pinecone-a

**Datum:** 2026-08-13
**Baseline (committed HEAD):** `690981ccc8e5229e1ae846773174d7823d81c958`
**Metod:** statička AST analiza svih 726 praćenih `.py` fajlova + ručno praćenje pozivalaca + runtime negativna kontrola sa snimajućim lažnim indeksom (bez mreže).
**Ograničenja mandata:** nijedan produkcijski fajl nije menjan. Nijedan upis/brisanje u Pinecone. Nijedan sadržaj stvarnog klijentskog dokumenta nije čitan ni ispisan.

---

## 0. VAŽNO — stanje radnog direktorijuma se promenilo TOKOM ove analize

Na početku sesije `git status` nije prijavljivao nijednu izmenu produkcijskog koda.
U toku analize u radnom direktorijumu su se pojavile **necommit-ovane** izmene koje
zatvaraju upravo F-01:

| Fajl | Stanje | blob hash |
|---|---|---|
| `shared/rag_acl.py` | NOVI, untracked | `ef891bd0a26fece5a9f1a4094cad98d3ce63a972` |
| `app/services/retrieve.py` | izmenjen (`M`) | `1c51f5bf0f946b8adcc5cabbbc195aa01d6bcc0d` |
| `api.py` | izmenjen (`M`) | `148ac84a5617f2133785255aced1b06e5a08ce1b` |

Ovaj izveštaj razlikuje dva stanja i **oba su činjenice**:

- **BASELINE (`690981cc`, ono što je commit-ovano):** F-01 je **OTVOREN**.
- **RADNI DIREKTORIJUM (necommit-ovano):** F-01 je **ZATVOREN** guard-om
  `shared/rag_acl.py`; nalaz je verifikovan runtime-om (§5).

Sve dok izmena nije commit-ovana i deploy-ovana, **produkcija radi po baseline-u**.

---

## 1. AUTORIZACIONI UGOVOR ZA PRISTUP PREDMETU

Ovo je merilo sa kojim se retrieval mora porediti. Utvrđeno iz koda, ne iz dokumentacije.

**Kanonska kapija:** `api.py:4163-4189` — `GET /api/predmeti/{predmet_id}` → `get_predmet`.

```
api.py:4168   .table("predmeti").select("*").eq("id", predmet_id).eq("user_id", user.id)
api.py:4179   ILI: .table("predmet_delegiranja").select("id")
                     .eq("predmet_id", predmet_id).eq("na_user_id", user.id)
                     .eq("status", "aktivno")
api.py:4189   inače -> 404
```

**Ugovor glasi: predmet sme da vidi tačno dva subjekta.**

1. **Vlasnik** — `predmeti.user_id == pozivalac`.
2. **Izričito delegirani korisnik** — aktivan red u `predmet_delegiranja`
   (`na_user_id == pozivalac`, `status == 'aktivno'`), migracija 054,
   pisac: `routers/enterprise.py:258`.

**Šta ugovor NIJE:**

- **Članstvo u kancelariji NIJE osnov.** Nigde u `get_predmet` ne postoji provera
  `kancelarija_id`. Član firme koji nije vlasnik i nije delegiran dobija **404**.
- **`predmet_saradnici` NIJE osnov — iako tabela postoji i puni se.**
  Tabela: `migrations/011_saradnja.sql:6` (`predmet_id`, `owner_user_id`,
  `saradnik_user_id`, `uloga ∈ {citanje, saradnja, vodenje}`, RLS uključen).
  Piše je `routers/saradnja.py:160` (upsert). Čita je `routers/saradnja.py:314`
  (`/api/saradnja/moji-predmeti` — vraća `id, naziv, opis, tip, status`) i
  `routers/saradnja.py:390` (`uloga` za UI).
  **Ali `get_predmet` je nikad ne konsultuje** — saradnik vidi naziv predmeta u
  listi, a `GET /api/predmeti/{id}` mu vraća 404. To je postojeća nekonzistentnost
  proizvoda, evidentirana ovde jer se retrieval mora meriti prema `get_predmet`,
  ne prema `predmet_saradnici`.
- **Upload putanja je STROŽA od `get_predmet`:** `api.py:5060`
  (`POST /api/predmeti/{id}/upload`) traži `.eq("user_id", user.id)` bez
  delegiranja — samo vlasnik.

---

## 2. KOMPLETNA TABELA POZIVNIH MESTA (produkcijski kod)

AST sweep: **106 read call-site-ova** ukupno u repou, **34** izvan `tests/`, `scripts/`
i root diag/ingest skripti. Diag/ingest/test skripte su isključene iz tabele
(nisu import-ovane iz aplikacije; nabrojane u §6).

Legenda: **PC** = predmet check, **TC** = tenant check.

### 2.1 Javni korpusi (zakoni / praksa / mišljenja / web3) — nema tenanta, po dizajnu

| # | CALLER (fajl:linija:funkcija) | NAMESPACE (izvor imena) | FILTER | AUTORIZACIJA | PC | TC | RESULT |
|---|---|---|---|---|---|---|---|
| 1 | `app/services/retrieve.py:901:_semanticka_pretraga` | `_ZAKONI_NS` = `"zakoni_rs"` (const `:746`) | `{"law":{"$eq":…}}` ili `None` | nema (javni korpus) | ne | ne | tekst zakonskih članova |
| 2 | `app/services/retrieve.py:916:_pretraga_vec` | `_ZAKONI_NS` hardkod | `{"law":…}` ili `None` | nema | ne | ne | isto |
| 3 | `app/services/retrieve.py:927:_pretraga_misljenja` | `_MISLJENJA_NS` hardkod | nema | nema | ne | ne | mišljenja ministarstava |
| 4 | `app/services/retrieve.py:943:_pretraga_praksa` | `_PRAKSA_NS` hardkod | nema | nema | ne | ne | sudska praksa |
| 5 | `app/services/retrieve.py:1017:_direktan_fetch_clana` | `_ZAKONI_NS` hardkod | `{"$and":[{"clan":…},{"zakon":…}]}` | nema | ne | ne | članovi zakona |
| 6 | `app/services/retrieve.py:2675:retrieve_grupisano` | `_PRAKSA_NS` hardkod | nema, `top_k=300` | nema | ne | ne | praksa grupisana po ishodu |
| 7 | `app/services/retrieve.py:2732:retrieve_grupisano` | `_PRAKSA_NS` hardkod | `{"decision_number":{"$eq":…}}` | nema | ne | ne | chunk-ovi jedne odluke |
| 8 | `routers/praksa.py:206:_praksa_search_sync` | `_PRAKSA_NS_SEARCH` hardkod | `{matter,court}` ili `None`, `top_k` do 1500 | endpoint auth | ne | ne | praksa |
| 9 | `routers/praksa.py:148:_keyword_fallback_sync` | `_PRAKSA_NS_SEARCH` hardkod | isti `filter_dict`, `top_k*4` | isto | ne | ne | praksa (fallback grana) |
| 10 | `routers/praksa.py:426:_fetch_decision_chunks` | petlja `("sudska_praksa","upravna_praksa")` hardkod | `{"decision_number":{"$eq":dn}}` | endpoint auth | ne | ne | pun tekst odluke |
| 11 | `api.py:4712:_fetch_relevantne_presude_sync` | petlja `("sudska_praksa","upravna_praksa")` hardkod → `_pretraga_ns` | **nema (`filter=None`)** | poziva se iz auto-analize | ne | ne | top presude za sekciju 22 |
| 12 | `web3_compliance.py:305/321:web3_pretraga_sync` | `_WEB3_NAMESPACE` hardkod | nema | endpoint auth | ne | ne | ZDI/MiCA odredbe |
| 13 | `web3_compliance.py:402:compliance_check_sync` | `_WEB3_NAMESPACE` hardkod | nema | endpoint auth | ne | ne | isto |
| 14 | `web3_compliance.py:900:carf_dac8_readiness_sync` | `_CARF_DAC8_NAMESPACE` hardkod | nema | endpoint auth | ne | ne | CARF/DAC8 odredbe |

### 2.2 Privatni namespace-ovi — ovde se meri ACL

| # | CALLER | NAMESPACE (izvor imena) | FILTER | AUTORIZACIJA | PC | TC | RESULT |
|---|---|---|---|---|---|---|---|
| 15 | **`app/services/retrieve.py:1850:retrieve_documents`** (baseline) | `kancelarija_namespace` param ← `api.py:5072` `rag_owner_namespace(user.id, kancelarija_id)` → `kancelarija_{id}` ili `user_{id}` (`shared/kancelarija_utils.py:46`) | **`{"type":{"$in":["case_doc","draft_final"]}}` — BEZ `predmet_id`** | `api.py:5060` dokazuje vlasništvo nad **jednim** predmetom, ne nad ostatkom namespace-a | **NE** | **DA** (firma) | doslovni pasusi dokumenata iz **svih** predmeta cele kancelarije, ubaceni u LLM kontekst (`retrieve.py:2166`) |
| 15′ | isto, **radni direktorijum** | isto | `{"type":{"$in":[…]}, "predmet_id":{"$in": dozvoljeni}}`; `None` → namespace se preskače (`retrieve.py:1856-1874` novi) | `shared/rag_acl.py:dozvoljeni_predmeti` ogledalo `get_predmet` | **DA** | DA | pasusi samo iz predmeta koje pozivalac sme da vidi |
| 16 | `app/services/retrieve.py:966:_pretraga_ns` (generički wrapper) | `namespace` argument pozivaoca | `if filter:` — **opcion**; prazan/`{}` ⇒ **filter se uopšte ne šalje** | nema sopstvenu; nasleđuje pozivaočevu | zavisi | zavisi | sirovi `matches` |
| 17 | `routers/dokument.py:131:_query_ns` (u `_fetch_session_tekst`) | `f"{namespace_prefix}{session_id}"`, prefix ∈ `{tmp_,pred_}` iz tela zahteva | nema, `top_k=1000` | pozivaoci zovu `_verify_pred_namespace_ownership` (`:583`, `:520`, `:610`) | DA za `pred_` (vlasnik) | DA | rekonstruisan **pun tekst** dokumenta |
| 18 | `routers/dokument.py:205:_verify_pred_namespace_ownership` | `f"tmp_{session_id}"` | nema, `top_k=1` | **ovo JESTE provera**: poredi `metadata.owner_user_id == uid`, inače 404 | n/p | DA | samo `owner_user_id` iz metadate |
| 19 | `uploaded_doc/session.py:47:validate_session` | `f"{namespace_prefix}{session_id}"` | nema, `top_k=1` | **NIJEDNA sopstvena** — čista provera postojanja + TTL | ne | ne | `bool` |
| 20 | `routers/knowledge_base.py:227:knowledge_search` | `f"kb_{uid}"`, `uid` iz `PermissionService.require(...)` | nema, prag `score>=0.3` | per-user namespace | ne (vraća `predmet_id` u meta) | DA (user) | naslov + **pun `sadrzaj`** beleške |
| 21 | `drafting/playbook.py:101:search_playbook` | `f"playbook_{user_id}"`, `user_id` ← `drafting/router.py:489` ← `routers/drafting.py:654` `user["user_id"]` | nema | per-user namespace | ne | DA (user) | tekst chunk-ova playbook-a |
| 22 | `interni_stavovi.py:96:search_stavovi` | `f"interni_stavovi_{user_id}"` ← `routers/interni.py:46` `user["user_id"]` | nema, prag `score>0.5` | per-user namespace | ne | DA (user) | tekst + naslov stava |
| 23 | `uploaded_doc/cleanup.py:50:cleanup_expired` | `ns` iz `describe_index_stats().namespaces`, filtrirano `startswith("tmp_")` | nema, `top_k=1` | **sistemski posao, bez korisničkog konteksta** | ne | ne | čita samo `expires_at` iz metadate; ne vraća se korisniku |

### 2.3 Samo statistika (ne vraća sadržaj)

| # | CALLER | Metod | AUTORIZACIJA |
|---|---|---|---|
| 24 | `app/services/retrieve.py:475:_get_index` | `describe_index_stats` | n/p (health probe pri init-u) |
| 25 | `routers/admin_dashboard.py:335:pinecone_capacity` | `describe_index_stats` **[bare-ref → `asyncio.to_thread`]** | `_require_founder(user)` |
| 26 | `routers/proof.py:88:_test_pinecone` | `describe_index_stats` | endpoint-level |
| 27 | `routers/drafting.py:587:playbook_status` | `describe_index_stats` | `PermissionService.require("drafting")` |
| 28 | `drafting/playbook.py:120:delete_playbook` | `describe_index_stats` | per-user |
| 29 | `interni_stavovi.py:122/138` | `describe_index_stats` | per-user |
| 30 | `uploaded_doc/cleanup.py:35` | `describe_index_stats` | sistemski |
| 31 | `api.py:2479:_run_checks`, `api.py:3120` | `describe_index_stats` | admin/debug |
| 32 | **`api.py:2413/2416:test_pinecone`** | `describe_index_stats` **+ `query` BEZ `namespace`** | `X-Admin-Key == ADMIN_DEBUG_KEY`, 404 ako nije postavljen | — v. §3.1 |

---

## 3. OPASNI OBRASCI

### 3.1 Upit bez namespace-a (`__default__`)
`api.py:2416` (`GET /test-pinecone`) — `index.query(vector=…, top_k=3, include_metadata=True)`
**bez `namespace=`**, dakle Pinecone `__default__`. Vraća
`test_results.matches[0].metadata` — **celu metadatu prvog pogotka**, uključujući
`text`. Gejtovan `X-Admin-Key` (`api.py:2404-2406`, fail-closed ako env var nije
postavljen). **UNKNOWN:** da li `__default__` namespace danas sadrži bilo koji
klijentski vektor. Nije provereno — provera bi zahtevala živi `describe_index_stats`,
a i tada bi bila samo brojanje. Nijedan piscački put u repou ne piše u `__default__`
(svi upsert-i navode namespace: `uploaded_doc/ingest.py:101`, `routers/law_upload.py:92`,
`routers/batch_ingest.py:63`, `drafting/playbook.py:86`, `interni_stavovi.py:81`,
`routers/auto_discovery.py:212`), pa je preostali sadržaj istorijski.

### 3.2 Opcion filter — `{}` znači „bez ograničenja"
`app/services/retrieve.py:963-965`:
```python
kwargs = {"vector": vektor, "top_k": k, "namespace": namespace, "include_metadata": True}
if filter:
    kwargs["filter"] = filter
```
Prazan dict, prazna lista, `None` — sve tri vrednosti tiho uklanjaju filter i
pretražuju **ceo namespace**. Ovo je mehanizam kojim se F-01 može ponovo otvoriti
jednom budućom greškom. Novi `shared/rag_acl.py:filter_za_namespace_vlasnika`
to eksplicitno adresira vraćanjem `None` (= „ne pretražuj uopšte") umesto `{}`,
ali `_pretraga_ns` sam po sebi ostaje neizmenjen i i dalje prihvata `{}`.

### 3.3 Fallback putanje
| Putanja | Ponašanje | Ocena |
|---|---|---|
| `routers/praksa.py:212-219` → `_keyword_fallback_sync` | okida kad `max_score < _KEYWORD_FALLBACK_THRESHOLD`; **prosleđuje isti `filter_dict` i isti javni namespace**, samo širi `top_k` na `top_k*4` | ne proširuje obim autorizacije |
| `routers/dokument.py:150-164` | **ranije** je padao na *drugi* prefiks (`tmp_`↔`pred_`) kad deklarisani vrati prazno; uklonjeno (S6B Phase A) — sada `return _query_ns(f"{prefix}{session_id}")` bez fallback-a | zatvoreno, potvrđeno u kodu |
| `app/services/retrieve.py:_crag_petlja` / `_prosiri_pretragu_crag` | corrective re-query; runtime kontrola (§5, PATH 1) pokazuje da dodatni krugovi udaraju **isključivo `zakoni_rs`** | ne proširuje obim |
| `api.py:5453-5456` | `asyncio.TimeoutError`/`Exception` → nastavlja **bez** RAG-a | fail-closed |

### 3.4 Retry putanje
Nijedna retry putanja ne menja namespace ni filter. `_pretraga_ns`, `_pretraga_praksa`,
`_semanticka_pretraga` na izuzetak vraćaju `[]` (fail-soft, bez ponovnog upita sa
labavijim parametrima).

### 3.5 Ime namespace-a iz korisničkog ulaza
Jedini kanal: `POST /api/dokument/pitanje`, `POST /api/dokument/rokovi`,
`POST /api/dokument/*` — telo zahteva nosi `namespace_prefix` i `session_id`,
a efektivni namespace je njihova konkatenacija.
- `namespace_prefix` je **klemovan** na `{"tmp_","pred_"}` (`routers/dokument.py:418-419`,
  `:580-581`); sve ostalo se tiho svodi na `tmp_`.
- `session_id` je slobodan string, ali `_verify_pred_namespace_ownership`
  (`:189-210`) fail-closed odbija: za `pred_` traži `predmeti.id == session_id AND
  user_id == uid`; za `tmp_` traži `metadata.owner_user_id == uid` na prvom vektoru.
  Legacy vektori bez `owner_user_id` → 404 (fail-closed).
- **Nije eksploatabilno**, ali jeste **funkcionalno pokvareno:** `static/vindex.js:15662`
  `dokUcitajZaAnalizu(ns,…)` radi `ns.replace(/^(pred_|tmp_)/,'')`. Za dokument
  otpremljen posle 2026-07-26 `pinecone_namespace` je `kancelarija_{uuid}`/`user_{uuid}`,
  pa prefiks ne otpada: klijent šalje `session_id="kancelarija_<uuid>"`,
  `prefix="tmp_"`, backend pita `tmp_kancelarija_<uuid>` → prazno → 404.
  Fail-closed, ali „Analiza dokumenta" iz kartice predmeta ne radi za nove dokumente.
  **Nije ACL nalaz — evidentirano jer je otkriveno istim sweep-om.**

### 3.6 Hardkodirani namespace-ovi
`zakoni_rs`, `sudska_praksa`, `upravna_praksa`, `misljenja`, web3/CARF-DAC8 —
svi javni korpusi. Nijedan hardkodiran namespace ne sadrži klijentske podatke.

---

## 4. PUTANJE SA TENANT AUTORIZACIJOM ALI BEZ PREDMET AUTORIZACIJE

Ovo je tražena lista. Kriterijum: poziv dokazuje *kome pripada* namespace,
ali ne dokazuje *koje predmete* pozivalac sme da vidi unutar njega.

| # | Putanja | Tenant dokaz | Šta nedostaje | Može li vratiti više nego što sme |
|---|---|---|---|---|
| **F-01** | `app/services/retrieve.py:1850` ← `api.py:5435` ← `POST /api/predmeti/{id}/upload` | `kancelarija_{id}` izveden iz `get_kancelarija_id(supa, user.id)` — pozivalac je dokazan ACTIVE član firme | **`predmet_id` nema u filteru** dok metadata vektora ima `predmet_id` (`api.py:5209`, `routers/drafting.py:359`, `routers/smart_intake.py:1402`) | **DA — potvrđeno.** Član firme koji nije vlasnik i nije delegiran dobija 404 na `GET /api/predmeti/{tudji_id}`, a ovom putanjom dobija **doslovan tekst** (do 5 pasusa, `retrieve.py:2163`) iz dokumenata tog predmeta u LLM kontekstu. Za solo advokata (`user_{id}`) razlike nema — namespace je ionako samo njegov. |
| 2 | `routers/knowledge_base.py:227` (`kb_{uid}`) | namespace = sam pozivalac | rezultat nosi `predmet_id` u metadati, bez provere da li je taj predmet i dalje pozivaočev | **NE** — sve beleške su njegove; `predmet_id` je samo oznaka. Nema drugog tenanta u namespace-u. |
| 3 | `drafting/playbook.py:101` (`playbook_{user_id}`) | namespace = sam pozivalac | n/p (nema predmeta u modelu) | **NE.** Napomena: prompt kaže „PLAYBOOK KANCELARIJE" (`drafting/router.py:491`) a namespace je per-user — to je *funkcionalni manjak deljenja*, ne curenje. |
| 4 | `interni_stavovi.py:96` (`interni_stavovi_{user_id}`) | namespace = sam pozivalac | n/p | **NE.** Isti nesklad naziva („stavovi firme", namespace per-user). |
| 5 | `routers/dokument.py:131` `_fetch_session_tekst` sa `pred_` | `_verify_pred_namespace_ownership` traži `predmeti.user_id == uid` | ništa — ovo je **stroža** provera od `get_predmet` (ne priznaje delegiranje) | **NE.** Namerno strože. |
| 6 | `uploaded_doc/session.py:47` `validate_session` | **nikakav** | funkcija sama po sebi nema autorizaciju | **NE u praksi** — sva tri poziva (`routers/dokument.py:423, 521, 611`) su *posle* `_verify_pred_namespace_ownership`. **Ali je to disciplina pozivaoca, ne svojstvo funkcije**: svaki budući pozivalac koji zaboravi redosled dobija golu proveru postojanja namespace-a. Evidentirano kao strukturni rizik. |
| 7 | `uploaded_doc/cleanup.py:50` | nikakav (sistemski posao) | n/p | **NE** — čita samo `expires_at`, ne vraća sadržaj nijednom korisniku. |
| 8 | `api.py:4712` `_fetch_relevantne_presude_sync` | nikakav | `filter=None` nad `sudska_praksa`/`upravna_praksa` | **NE** — javni korpus. |

**Zaključak §4: tačno JEDNA putanja ima tenant autorizaciju bez predmet
autorizacije nad podacima klijenata — F-01.** Ostale su ili per-user namespace-ovi
(gde je tenant = jedini subjekt) ili javni korpusi.

---

## 5. NEGATIVNA KONTROLA — dokaz da sweep vidi žive tokove

Metod: `app.services.retrieve._get_index` zamenjen snimajućim lažnim indeksom
(bez mreže, bez Pinecone klijenta, bez upisa), pa su pokrenute 4 poznato-žive
retrieval putanje. Ispis je **izmeren**, nije pročitan iz koda:

```
=== PATH 1  retrieve_documents(query, k=6)  [multi_agent / voice_tools / legal_reasoning_engine / oblasti / integracije / drafting] ===
   ns=sudska_praksa   top_k=5    filter=None
   ns=zakoni_rs       top_k=10   filter={'$and': [{'clan': {'$eq': 179}}, {'zakon': {'$eq': 'ZR'}}]}
   ns=zakoni_rs       top_k=30   filter={'law': {'$eq': 'zakon o radu'}}
   ns=zakoni_rs       top_k=6    filter=None

=== PATH 2  retrieve_documents(..., kancelarija_namespace='kancelarija_KKK-111') [api.py:5435] ===
   [RAG_ACL] namespace vlasnika je tražen bez izračunate autorizacije — pretraga se odbija (fail-closed)
   [KANC_NS:kancelarija_KKK-111] preskacem namespace vlasnika -- nema autorizovanih predmeta
   ns=sudska_praksa   top_k=5    filter=None
   ns=zakoni_rs       top_k=30   filter={'law': {'$eq': 'zakon o radu'}}
   ns=zakoni_rs       top_k=6    filter=None

=== PATH 3  retrieve_documents(..., extra_namespaces=['tmp_SESSION-abc']) [main.py:3227 ask_agent] ===
   ns=sudska_praksa    top_k=5   filter=None
   ns=tmp_SESSION-abc  top_k=5   filter=None
   ns=zakoni_rs        top_k=30  filter=None
   ns=zakoni_rs        top_k=6   filter=None

=== PATH 4  retrieve_sudska_praksa() [court_predictor / copilot / precedents_radar / ambient_analyzer] ===
   ns=sudska_praksa   top_k=20   filter=None
```

**Šta ovo dokazuje:**

1. Sve tri klase namespace-a koje sam klasifikovao statički (javni korpus,
   `tmp_*` doc-sesija, namespace vlasnika) stvarno se pogađaju u runtime-u —
   klasifikacija nije pogrešna.
2. PATH 1 i PATH 4 **nikad** ne dodiruju privatni namespace — dakle svi pozivaoci
   koji zovu `retrieve_documents(q, k)` bez `kancelarija_namespace`
   (`routers/multi_agent.py:570,739`, `shared/voice_tools.py:114`,
   `services/legal_reasoning_engine.py:113`, `services/ambient_analyzer.py:88`,
   `routers/oblasti.py:163`, `routers/integracije.py:115`, `drafting/router.py:504`,
   `routers/drafting.py:958`, `api.py:3078,3136`) čitaju **samo javne korpuse**.
   Ovo je merena činjenica, ne pretpostavka.
3. PATH 2 je uhvatio ono što statičko čitanje nije: radni direktorijum više ne
   izvršava baseline granu. **Runtime je otkrio necommit-ovanu izmenu koju
   `git status` snapshot na početku sesije nije prijavljivao.**

**Metod je pao jednom i popravljen je.** Prva verzija AST skenera hvatala je samo
`ast.Call` čvorove i **propustila `routers/admin_dashboard.py:335`**:
`asyncio.to_thread(idx.describe_index_stats)` — gola referenca na metodu, pozvana
tek u thread pool-u. Skener je proširen na `ast.Attribute` čvorove koji nisu
odmah pozvani; broj produkcijskih call-site-ova je posle popravke porastao
33 → 34. Isti obrazac (`to_thread(bare_method)`) postoji i u testovima, što
potvrđuje da popravka hvata klasu, ne jedan slučaj.

---

## 6. ISKLJUČENO IZ OCENE (nije aplikacioni kod)

Ovi call-site-ovi postoje ali nisu import-ovani ni iz jednog FastAPI rutera,
servisa ni worker-a — to su jednokratne dijagnostičke/ingest skripte koje se
pokreću ručno sa `PINECONE_API_KEY` iz okruženja operatera:

`diag.py`, `diag_a6_prod.py`, `diag_q07_q27_investigation.py`, `diag_short_18_laws.py`,
`diag_zpp_revizija.py`, `diag_crypto_coverage.py`, `debug_rag.py`, `check_208.py`,
`check_pinecone_ns.py`, `audit_chunks.py`, `ingest_kz.py`, `ingest_laws.py`,
`ingest_misljenja.py`, `ingest_short_15*.py`, `ingest_glossary_vasp_casp.py`,
`test_chunker_fix*.py`, `scripts/check_ns.py`, `scripts/dr_runbook.py`,
`scripts/ingest_*.py`, `scripts/smoke_test_sp.py`, `scripts/proof_direct.py`.

Nekoliko njih (`diag_crypto_coverage.py:153`, `debug_rag.py:43`, `check_208.py:18`,
`ingest_kz.py:65/159`, `test_chunker_fix*.py`) upituju **bez `namespace=`**, dakle
`__default__`. Nije bezbednosni nalaz jer ne postoji HTTP putanja do njih, ali
jeste razlog da se `__default__` ne smatra praznim.

---

## 7. OCENA IN-FLIGHT ISPRAVKE (necommit-ovano, `shared/rag_acl.py`)

Traženo nije bilo, ali je nužno jer menja zaključak §4.

**Šta je dobro:**
- `dozvoljeni_predmeti` (`shared/rag_acl.py:56`) je **tačno ogledalo** `get_predmet`:
  `predmeti.user_id == uid` **plus** `predmet_delegiranja.status == 'aktivno'`.
  Nijedan širi osnov nije izmišljen.
- `predmet_saradnici` je **namerno izostavljen**, sa napisanim obrazloženjem —
  uključiti ga značilo bi dati pristup koji kanonska kapija ne daje.
- Sentinel `None` ≠ prazna lista: `filter_za_namespace_vlasnika` vraća `None`
  (= „ne pretražuj uopšte") umesto `{}`, čime se izbegava tačno `if filter:`
  zamka iz §3.2. Runtime (§5, PATH 2) to potvrđuje: bez ACL-a namespace se ne dira.
- Default `dozvoljeni_predmeti=None` u potpisu `retrieve_documents` znači da
  **svaki budući pozivalac koji prosledi `kancelarija_namespace` bez ACL-a
  automatski fail-closed preskoči namespace**, umesto da ga otvori.

**Preostali rizici — evidentirani, ne ocenjeni kao zatvoreni:**
1. **Veličina `$in` liste.** `{"predmet_id": {"$in": dozvoljeni}}` nosi **sve**
   ID-eve predmeta korisnika. Ponašanje Pinecone metadata filtera na velikim
   `$in` listama (limit broja elemenata / veličine upita) **nije provereno** →
   **UNKNOWN**. Advokat sa nekoliko hiljada predmeta je realan scenario;
   ako Pinecone odbije upit, `_pretraga_ns` ga guta u `except` i vraća `[]`
   (`retrieve.py:967-970`) — fail-closed, ali tiho i bez signala korisniku.
2. **Dva dodatna DB upita po uploadu** (`predmeti`, `predmet_delegiranja`) unutar
   4-sekundnog `asyncio.wait_for` budžeta (`api.py:5443`). Nije mereno.
3. **Pokrivenost je 1/1 danas, ali ugovor nije iznuđen tipom.**
   `kancelarija_namespace` i `dozvoljeni_predmeti` su dva nezavisna opciona
   parametra; ništa u potpisu ne sprečava da se prosledi samo prvi. Trenutno
   ponašanje je bezbedno (skip), ali je to *runtime* garancija.
4. **Izmena nije commit-ovana.** Dok se ne commit-uje i deploy-uje, produkcija
   izvršava baseline granu iz reda 15 tabele §2.2.

---

## 8. SAŽETAK

| Stavka | Nalaz |
|---|---|
| Ukupno read call-site-ova u repou | 106 (AST, posle popravke metoda) |
| Produkcijski (ne-test, ne-skripta) | 34 |
| Nad javnim korpusima | 14 |
| Nad privatnim namespace-ovima | 9 |
| Samo `describe_index_stats` | 11 |
| **Tenant DA / predmet NE, nad klijentskim podacima** | **1 — F-01** |
| Upit bez namespace-a u aplikaciji | 1 (`api.py:2416`, admin-key gated) |
| Fallback putanja koje šire obim | 0 |
| Retry putanja koje šire obim | 0 |
| Namespace iz korisničkog ulaza | 1 kanal, klemovan + ownership-gated |
| Otvorenih UNKNOWN-a | 2 (sadržaj `__default__`; limit `$in` liste) |

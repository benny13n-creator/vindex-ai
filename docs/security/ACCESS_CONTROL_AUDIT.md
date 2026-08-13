# ACCESS CONTROL & IDOR FORENZIKA

**Misija:** BETA-DATA-CONFIDENTIALITY-001 · Agent B
**Baseline:** commit `0df948ec`, radno stablo čisto
**Datum:** 2026-08-13
**Metod:** statička analiza celog repoa (AST, 5 nezavisnih prolaza) + **izvršeno merenje**
nad stubovanom bazom. Nula izmena produkcijskih fajlova. Nula upita ka produkcionoj bazi.
Nijedan stvarni korisnički podatak nije korišćen — svi ID-jevi su izmišljeni.

---

## 0. Sažetak

| # | Nalaz | Klasa | Ozbiljnost | Dokazano |
|---|---|---|---|---|
| **AC-01** | `PUT /api/users/{target_user_id}/role` — partner jedne kancelarije menja rolu korisnika **bilo koje druge** kancelarije | Cross-tenant privilege modification | **VISOKA** | izmereno |
| **AC-02** | `POST /api/zadaci/kreiraj` prima **tuđi** `predmet_id`; `GET /api/zadaci/moji` ga vraća zajedno sa `predmeti(naziv)` | IDOR (čitanje) | **SREDNJA** | izmereno |
| **AC-03** | `POST /api/pitanje` i `POST /api/procena` upisuju u `predmet_istorija` sa neproverenim `predmet_id`; vlasnik to vidi u svom spisu | Cross-tenant write / integritet spisa | **SREDNJA-VISOKA** | dokazano čitanjem koda, oba kraja lanca |
| **AC-04** | `PATCH /api/zadaci/{id}/dodeli` i `POST /api/zadaci/kreiraj` dodeljuju zadatak **bilo kom** `user_id` u sistemu | Cross-tenant push | NISKA-SREDNJA | izmereno |
| **AC-05** | `privremeni_pristup` token: šalje se u URL-u, traje do 168h, **ne postoji nijedna putanja opoziva** | Token lifecycle | SREDNJA | dokazano (grep) |
| **AC-06** | `portal-uploads` je jedini bucket u koji se piše **nešifrovano**, a piše u njega neautentifikovana spoljna strana | Storage | SREDNJA | dokazano |
| **AC-07** | Javnost/privatnost bucket-a `klijent-dokumenti` i `portal-uploads` se **ne može dokazati iz repoa** | Storage | UNKNOWN | — |
| **AC-08** | Nijedna putanja brisanja/anonimizacije ne uklanja blob iz Storage-a | Retencija | SREDNJA | dokazano |
| **AC-09** | `.or_(f"...{uid}...")` — interpolacija u PostgREST filter string | Hardening | NISKA | dokazano, nije iskoristivo |

**Ono što NIJE nađeno, iako je traženo agresivno:** nijedna ruta koja vraća **dokument
ili sadržaj dokumenta** ne propušta tuđi dokument. 15 od 15 testiranih ruta za pristup
spisu vratilo je 404 napadaču. Klijentski portal ne curi između klijenata. Nijedan
signed URL se ne izdaje bez prethodne provere vlasništva.

---

## 1. Popis ruta koje vraćaju dokument ili sadržaj predmeta

Obim: **160 ruta** ima `{*_id}` u putanji; **207 handlera** dodiruje bar jednu tabelu sa
sadržajem predmeta/klijenta. Ispod je popis za šest fajlova iz zadatka. Kolona
„vlasništvo" navodi **tačan predikat u samom upitu**, ne opis.

### 1.1 `routers/dokument.py` — analiza otpremljenog dokumenta

| Ruta | Linija | Auth | Provera vlasništva | Tenant | RBAC | Direktan pristup po ID-ju |
|---|---|---|---|---|---|---|
| `POST /api/dokument/upload` | 219 | `PermissionService.require("document_analysis")` | n/a (kreira sesiju) | ne | entitlement | — |
| `POST /api/dokument/pitanje` | 404 | isto | `_verify_pred_namespace_ownership` (:170) | ne | entitlement | `session_id` |
| `POST /api/dokument/analiza` | 491 | isto | isto, `tmp_` grana (:520) | ne | entitlement | `session_id` |
| `POST /api/dokument/klasifikuj-sesija` | 566 | `get_current_user` | isto (:583) | ne | ne | `session_id` |
| `POST /api/dokument/rokovi` | 593 | `PermissionService.require` | isto (:610) | ne | entitlement | `session_id` |
| `POST /api/dokument/cleanup` | 380 | `X-Admin-Token` == `FOUNDER_TOKEN` | n/a (globalno) | ne | admin | — |

`_verify_pred_namespace_ownership` (`routers/dokument.py:170-214`) je jedina prava kapija
ovde i radi na dva različita načina:
- `pred_<id>`: `predmeti.eq("id", session_id).eq("user_id", uid)` → 404 (**ne** 403, namerno
  da ne potvrdi postojanje tuđeg predmeta).
- `tmp_<id>`: čita `owner_user_id` iz Pinecone metapodataka i poredi ga sa pozivaocem;
  **fail-closed** kad vektor nema vlasnika (nasleđeni vektori pre ispravke).

Izmereno: `pred_` grana odbija napadača (HTTP 404). Vidi §2.3.

### 1.2 `klijenti/router.py` — CRM i Dokumentacioni trezor

Autentikacija ide kroz `_auth_from_request` (:1490), ne kroz `Depends` — zato je automatski
skener prvo prijavio „auth=NONE"; ručnom proverom potvrđeno da je autentikacija prisutna
na **svakoj** ruti.

| Ruta | Linija | Provera vlasništva | RBAC |
|---|---|---|---|
| `GET /klijenti/{klijent_id}` | 369 | `.eq("user_id", uid)` | `filter_klijent(role)` po klasifikaciji polja |
| `PUT /klijenti/{klijent_id}` | 456 | `.eq("user_id", uid)` | `edit_client` |
| `DELETE /klijenti/{klijent_id}` | 522 | `.eq("user_id", uid)` | `soft_delete_client` = PARTNER |
| `GET /klijenti/{klijent_id}/audit` | 712 | `_verify_owns_klijent` (:726) | `view_audit_log` = PARTNER |
| `POST /klijenti/{klijent_id}/dokumenti` | 756 | `_verify_owns_klijent` (:772) | `upload_document` |
| `GET /klijenti/{klijent_id}/dokumenti` | 895 | `_verify_owns_klijent` (:899) | — |
| **`GET /klijenti/{klijent_id}/dokumenti/{doc_id}/download`** | 914 | `_verify_owns_klijent` (:933) **+** `.eq("id", doc_id).eq("klijent_id", klijent_id)` (:938-942) | `download_document` = ADVOKAT |
| `POST /klijenti/{klijent_id}/komunikacija` | 1052 | `_verify_owns_klijent` (:1060) | — |
| `GET /klijenti/{klijent_id}/timeline` | 1082 | `_verify_owns_klijent` (:1089) | — |
| `GET /klijenti/{klijent_id}/relationship` | 1316 | `.eq("user_id", uid)` | — |
| **`PUT /api/users/{target_user_id}/role`** | **1196** | **NEMA NIJEDNU** | samo „pozivalac je PARTNER" |

Ruta za preuzimanje dokumenta je najjača u sistemu: dvostruki predikat, obavezan audit
upis **pre** vraćanja bajtova (:945-951), AES-GCM dekripcija u memoriji i PDF watermark sa
email-om preuzimaoca. Nijedan signed URL se ne izdaje — bajtovi idu kroz aplikaciju.

### 1.3 `routers/client_portal.py` — spoljni klijent

| Ruta | Linija | Auth | Vlasništvo |
|---|---|---|---|
| `POST /api/client-portal/token/{predmet_id}` | 216 | `get_current_user` | `.eq("user_id", uid)`, uz `predmet_saradnici` fallback za ulogu `vodenje` (:236-257) |
| `GET /api/client-portal/tokens/{predmet_id}` | 315 | `get_current_user` | `.eq("user_id", uid)` × 2 |
| `DELETE /api/client-portal/token/{token_id}` | 354 | `get_current_user` | `.eq("user_id", uid)` |
| `GET /api/client-portal/view` | 385 | **X-Portal-Token, bez logina** | `predmet_id` isključivo iz HMAC tokena |
| `POST /api/client-portal/dokument` | 514 | **X-Portal-Token, bez logina** | isto |
| `GET /api/client-portal/uploads/{predmet_id}` | 658 | `get_current_user` | `.eq("user_id", uid)` + `.eq("advokat_user_id", uid)` |
| `PATCH .../uploads/{upload_id}/pregledano` | 727 | `get_current_user` | `.eq("advokat_user_id", uid)` |
| `DELETE .../uploads/{upload_id}` | 750 | `get_current_user` | `.eq("advokat_user_id", uid)` × 2 |
| `PATCH /api/client-portal/potvrdi-pregled` | 821 | **X-Portal-Token** | token hash |

### 1.4 `api.py` — `/api/predmeti/...`

Svih 12 `{predmet_id}` ruta nosi `.eq("user_id", ...)` u samom upitu nad `predmeti`:

| Ruta | Linija | Napomena |
|---|---|---|
| `GET /api/predmeti/{predmet_id}` | 4126 | + namerni delegirani pristup, §5 |
| `PATCH /api/predmeti/{predmet_id}` | 4207 | |
| `PATCH .../kanban-faza` | 4295 | |
| `POST .../beleske` | 4336 | |
| `DELETE .../beleske/{beleska_id}` | 4360 | |
| `POST .../istorija` | 4368 | provera dodata SEC-001, 2026-07-23 (:4372) |
| `POST .../upload` | 4980 | |
| `GET .../hronologija` | 5735 | |
| `GET .../ai-preporuka` | 5772 | |
| **`GET .../dokumenti/{dok_id}/preview`** | 5851 | `.eq("id", dok_id).eq("predmet_id", ...).eq("user_id", uid)` — trostruki predikat |
| `GET .../workspace` | 5920 | |
| `POST .../confirm-links` | 6298 | provera `klijent_id`-jeva dodata Lambda 002 |
| `GET /api/portal/predmet` | 2570 | **bez logina**, `privremeni_pristup` token — §4.2 |

**Bitno:** nakon što `get_predmet` (4126) i `workspace` (5920) dokažu vlasništvo nad
predmetom, podupiti nad `predmet_beleske`, `predmet_istorija`, `predmet_dokumenti`,
`predmet_hronologija`, `predmet_komentari` idu **samo po `predmet_id`**
(`api.py:4153-4158`, `:5949-5961`). Za čitanje je to ispravno. Za **integritet** nije —
vidi AC-03 u §2.4.

### 1.5 `routers/evidence.py` i `routers/case_actions.py`

| Ruta | Linija | Vlasništvo |
|---|---|---|
| `GET /api/evidence/predmeti/{predmet_id}` | 328 | `.eq("user_id", uid)` nad `predmeti` (:336) pre bilo čega |
| `POST .../dokaz` | 380 | isto (:387) + `dokument_id` vezan za `predmet_id` (:395) |
| `DELETE .../dokaz/{dokaz_id}` | 418 | `.eq("id", dokaz_id).eq("user_id", uid)` u samoj UPDATE naredbi |
| `POST .../reklasifikuj/{dok_id}` | 448 | `predmeti.eq(user_id)` **i** `predmet_dokumenti.eq("id", dok_id).eq("user_id", uid)` |
| `GET /api/case-actions/worklist` | 61 | izvedeno, §2.5 |
| `GET /api/case-actions/predmeti/{predmet_id}` | 120 | `.eq("id", predmet_id).eq("user_id", uid)` (:127) |

### 1.6 `routers/smart_intake.py`

Vlasništvo se svuda izražava kolonom `intake_jobs.uploaded_by`, ne `user_id`:

| Ruta | Linija | Vlasništvo |
|---|---|---|
| `POST /api/smart-intake/documents` | 110 | upisuje `uploaded_by = uid`, ključ `{user_id}/{uuid4}` |
| `GET /api/smart-intake/jobs/{job_id}` | 259 | `.eq("id", job_id).eq("uploaded_by", uid)` |
| `POST .../jobs/{job_id}/review/resolve` | 358 | isto |
| `POST .../jobs/{job_id}/review/reject` | 455 | isto |
| `POST .../entities/{entity_id}/correct` | 516 | lanac `extracted_entities → intake_documents → intake_jobs.uploaded_by` (:549-575) |
| `POST .../jobs/{job_id}/finalize` | 767 | u `_finalize_intake_job_core` (:812-818), `.eq("uploaded_by", uid)` |

---

## 2. IDOR / BOLA — napad na klasu, ne na pojedinačnu rutu

### 2.1 Metod merenja

Napisan je stub baze koji se ponaša **kao prava baza sa service ključem**: vraća red kad
ga upit traži, bez obzira čiji je. Ako ruta ne filtrira po vlasniku, stub joj **vraća tuđi
red** — dakle test meri, ne glumi.

- stub: `fakedb.py` (minimalni PostgREST: `eq/neq/in_/is_/gte/lte/or_/not_.in_/single/maybe_single`,
  `insert/update/upsert/delete`, `storage.from_()`)
- napad: `test_idor_measure.py`, `test_idor_round2.py`, `test_idor_round3.py`
- lokacija: privatni scratchpad ove sesije, **nijedan fajl nije dodat u repo**
  (deliverable je tačno jedan dokument)
- okruženje: `SUPABASE_URL/SERVICE_KEY/DB_URL` se brišu pre ijednog `import`-a i
  postavljaju na `fake.supabase.co` — isti obrazac kao `tests/conftest.py:44-78`

**Kontrolni test (obavezan da rezultat nešto znači):** ista ruta, isti stub, ali kao
vlasnik A → vraća `TAJNA`, `presuda.pdf`, `TAJNA TVRDNJA`. Dakle 404 za napadača dolazi od
**koda**, ne od praznog stub-a.

### 2.2 Rezultat: 15 ODBIJEN / 1 PRAZNO / 1 PROPUSTIO

Korisnik B traži ID korisnika A:

| Ruta | Ishod |
|---|---|
| `GET /api/evidence/predmeti/{predmet_id}` | ODBIJEN 404 |
| `GET /api/case-actions/predmeti/{predmet_id}` | ODBIJEN 404 |
| `GET /api/case-actions/worklist` | PRAZNO (200, nula tuđih redova) |
| `GET /api/client-portal/uploads/{predmet_id}` | ODBIJEN 404 |
| `DELETE /api/client-portal/uploads/{upload_id}` | ODBIJEN 404 |
| `GET /api/client-portal/tokens/{predmet_id}` | ODBIJEN 404 |
| `GET /klijenti/{klijent_id}/dokumenti` | ODBIJEN 404 |
| `GET /klijenti/{klijent_id}/dokumenti/{doc_id}/download` | ODBIJEN 404 |
| `GET /klijenti/{klijent_id}/audit` | ODBIJEN 404 |
| `GET /klijenti/{klijent_id}/timeline` | ODBIJEN 404 |
| `GET /api/smart-intake/jobs/{job_id}` | ODBIJEN 404 |
| `GET /api/simulator/partija/{partija_id}` | ODBIJEN 404 |
| `GET /api/predmeti/{predmet_id}/reasoning-graph` | ODBIJEN 404 |
| `GET /api/learning/feedback-questions/{predmet_id}` | ODBIJEN 404 |
| `GET /api/predmeti/{predmet_id}/replay/timeline` | ODBIJEN 404 |
| `POST /api/dokument/pitanje` (`pred_` tuđeg predmeta) | ODBIJEN 404 |
| **`PUT /api/users/{target_user_id}/role`** | **PROPUSTIO** |

### 2.3 AC-01 (VISOKA) — `PUT /api/users/{target_user_id}/role`

`klijenti/router.py:1196-1216`

```python
user = await _auth_from_request(request)
if user["role"] < Role.PARTNER:
    raise HTTPException(status_code=403, ...)
...
supa.table("user_roles").upsert({"user_id": target_user_id, "rola": rola},
                                on_conflict="user_id").execute()
```

Jedina provera je „**pozivalac** je partner". `target_user_id` se uzima direktno iz URL-a i
ne poredi ni sa čim. Tabela je globalna — `migrations/002_klijenti_crm.sql:10-17`:
`user_roles(user_id UUID PRIMARY KEY, rola TEXT, ...)`, bez `kancelarija_id`.

**Izmereno:**

```
user_roles PRE  : [{"user_id": A, "rola": "partner"}, {"user_id": B, "rola": "partner"}]
poziv           : B → PUT /api/users/A/role  rola=sekretarica  →  200 {"status":"postavljeno"}
user_roles POSLE: [{"user_id": A, "rola": "sekretarica"}, {"user_id": B, "rola": "partner"}]
```

**Posledica po žrtvu.** `klijenti/permissions.py:86-103`: `sekretarica` gubi
`download_document`, `access_confidential`, `archive_client`, `view_audit_log`, i sva polja
klase `INTERNAL`/`CONFIDENTIAL`/`HIGHLY_CONFIDENTIAL` (telefon, email, adresa, JMBG, pasoš,
PIB). Partner kancelarije X može advokatu kancelarije Y **oduzeti pristup sopstvenim
klijentima i sopstvenim dokumentima**, i to trajno dok neko ne vrati rolu. Suprotan smer
(dizanje sebi ili saučesniku role) je isto otvoren.

**Šta ograničava eksploataciju (pošteno rečeno).** Napadač mora već biti `PARTNER`.
Repo-wide grep pokazuje da `user_roles` upisuje **isključivo ova jedna ruta**
(`klijenti/router.py:1210`), a `_is_founder` daje `PARTNER` bez reda u tabeli
(`klijenti/router.py:60-62`). Danas, dakle, partner postoji samo ako ga je founder napravio.
Ali to je operativno ograničenje, ne kontrola — čim postoji drugi partner, ruta je
cross-tenant. Mora se znati i UUID žrtve (nije nabrojiv, ali curi kroz podršku, snimke
ekrana, deljene linkove).

**Napomena o RLS-u:** `migrations/002:22-30` postavlja `user_roles_select_own` i
`user_roles_service_all`. Nijedna od te dve politike se ne primenjuje ovde jer aplikacija
piše service ključem (§6). Politika **nije** odbrana; ona je dokumentacija namere koja u
ovom pozivu ne postoji.

### 2.4 AC-02 i AC-03 — pisanje u tuđi predmet, čitanje nazad

Ovo je klasa, ne ruta: **`predmet_id` iz tela zahteva se upisuje bez provere vlasništva**.
Statički prolaz je našao 21 write rutu koja upisuje `predmet_id`/`klijent_id` iz zahteva bez
ijednog `predmeti.eq("user_id")` u istom handleru. Od toga:

- 13 je lažno pozitivno (koriste `_verifikovan_predmet_id`, `routers/court_predictor.py:426`
  i sl., ili pišu samo u sopstveni `kancelarija_id` prostor).
- 3 su bez putanje čitanja nazad (`memory_graph`, `style_analize`, `twin_simulacije`).
- **3 imaju dokazanu putanju čitanja nazad** i navedene su niže.
- 2 su `client_portal` (`predmet_id` dolazi iz potpisanog tokena — ispravno).

#### AC-02 (SREDNJA) — `zadaci` · IZMERENO

`routers/zadaci.py:143-180` — `POST /api/zadaci/kreiraj` upisuje
`"predmet_id": payload.predmet_id` bez ijedne provere.
`routers/zadaci.py:213-217` — `GET /api/zadaci/moji` čita
`.select("*, predmeti(naziv)").eq("dodeljen_uid", uid)`. `predmeti(naziv)` je PostgREST
embed, izvršen service ključem — dakle **razrešava se za bilo koji `predmet_id`**.

Izmereno (napadač B, tuđi predmet A):

```
1) POST /api/zadaci/kreiraj  {predmet_id: "PRED-A", dodeljen_uid: B}  → 200 ok:true
2) GET  /api/zadaci/moji                                             → 200
   {"zadaci":[{... "predmet_id":"PRED-A", "predmeti":{"naziv":"Petrovic protiv Banke — TAJNI SPOR"}}]}

>>> NAZIV TUĐEG PREDMETA VRAĆEN NAPADAČU: True
```

Drugi smer iste rupe: red koji je B upisao **pojavljuje se u spisu žrtve**.
`routers/zadaci.py:454-461` (`GET /api/zadaci/predmet/{predmet_id}`) — pošto dokaže
vlasništvo, čita `zadaci` **samo** po `predmet_id`. Advokat A vidi zadatak koji je napisao
neko izvan njegove kancelarije. Ironija je da je baš ta ruta ranije popravljena
(`tests/test_beta_lockdown_zadaci_predmet_idor.py`) — zatvoren je **read**, a ista klasa je
ostala otvorena na **write** strani.

#### AC-03 (SREDNJA-VISOKA) — `predmet_istorija` · oba kraja lanca u kodu

| Pisač | Provera vlasništva |
|---|---|
| `api.py:4368-4381` `POST /api/predmeti/{predmet_id}/istorija` | **DA** — `.eq("id", predmet_id).eq("user_id", user.id)` (:4372), dodato SEC-001 |
| `api.py:3375-3383` `POST /api/pitanje` | **NE** — `predmet_id = (req.predmet_id or "").strip()` (:3316) pa direktno `insert` |
| `api.py:4894-4901` `POST /api/procena` | **NE** — isto |

Čitalac: `api.py:4154` u `get_predmet` →
`supa.table("predmet_istorija").select("*").eq("predmet_id", predmet_id)` — **bez
`user_id`**, i vraća se korisniku kao `"istorija"` (`api.py:4197`).

Dakle: bilo koji autentifikovan korisnik koji zna tuđi `predmet_id` može u tuđi pravni spis
ubaciti proizvoljan par pitanje/odgovor (do 500 + 3000 znakova), koji će vlasnik videti kao
deo istorije **svog** predmeta. Za pravni proizvod to nije samo poverljivost nego integritet
spisa: injektovan tekst izgleda isto kao stvarna AI analiza tog predmeta.

Ovo nije izmereno end-to-end (izvršavanje `/api/pitanje` traži ceo RAG lanac i naplatu, što
bi značilo stvarne AI pozive). Oba kraja su, međutim, doslovno pročitana i navedena gore —
zaključak je dedukcija iz koda, ne pretpostavka. Preporuka: pre ispravke, potvrditi jednim
upitom `SELECT count(*) FROM predmet_istorija pi JOIN predmeti p ON p.id = pi.predmet_id
WHERE pi.user_id <> p.user_id;` — ako vrati 0, rupa nikad nije iskorišćena.

#### AC-04 (NISKA-SREDNJA) — dodela zadatka bilo kome · IZMERENO

`routers/zadaci.py:346-368` `PATCH /api/zadaci/{zadatak_id}/dodeli` i
`routers/zadaci.py:172` (`kreiraj`) upisuju `dodeljen_uid` iz tela zahteva bez provere da li
je taj korisnik uopšte član iste kancelarije.

```
B → PATCH /api/zadaci/Z-B/dodeli  {dodeljen_uid: A}  → 200
red: {id:"Z-B", kreirao_uid:B, dodeljen_uid:A, predmet_id:"PRED-B"}
```

Zadatak sa nazivom, opisom i rokom predmeta kancelarije B završi u
`GET /api/zadaci/moji` korisnika A. Smer je „guranje", ne „povlačenje" — napadač curi
sopstvene podatke ka žrtvi. Ozbiljno kao vektor phishinga unutar proizvoda („Zadatak: pozovi
ovaj broj radi potvrde"), ne kao curenje tuđih podataka.

### 2.5 Odgovor na traženo pitanje: `case_actions` nema `user_id` — kako je izolovana?

`migrations/099_case_actions.sql` — tabela nosi samo `predmet_id`. Izolacija je
**izvedena**, i danas je ispravna:

`routers/case_actions.py:77-85` prvo dohvati `predmeti.select("id,naziv").eq("user_id", uid)`,
pa tek onda `_fetch_open_actions(supa, predmet_ids)` radi `.in_("predmet_id", predmet_ids)`
(`:51-58`). Filter se primenjuje **nad listom ID-jeva koja je već dokazano pozivaočeva**, ne
posle dohvatanja. Isto važi za `GET /api/case-actions/predmeti/{predmet_id}` (:126-131).

Provereno svih 15 mesta u kodu koja čitaju `case_actions`:

| Fajl:linija | Kako je izolovano |
|---|---|
| `routers/case_actions.py:52` | `.in_(predmet_ids)` iz vlasnikovog upita |
| `api.py:4022` | `.in_(pred_ids)`, `pred_ids` iz `predmeti.eq(user_id)` |
| `api.py:5961` | posle `get_predmet`-ove kapije |
| `routers/workspace.py:143` | `.in_(predmet_ids)` iz vlasnikovog upita |
| `routers/copilot.py:528` | posle kapije rute |
| `routers/case_pipeline.py:105`, `services/case_pipeline.py:822` | posle kapije rute |
| `routers/predmeti_close.py:211,396` | posle kapije rute |
| `shared/case_context.py:245` | posle `case_context`-ove sopstvene kapije (`:170-190`) |
| `services/case_evolution.py:1032,1055,1061,1076,1163` | pozadinski, `predmet_id` iz event reda |

**Rizik nije današnji nego strukturni:** izolacija ne postoji u samoj tabeli, nego u
disciplini 15 pozivalaca. Prvi budući čitalac koji zaboravi da prvo razreši
`predmet_ids` curi ceo tuđi radni spisak. Preporuka: `user_id` kolona sa FK i backfill-om
(`scripts/backfill_case_actions.py` već postoji), ili barem jedan zajednički helper koji je
jedini ulaz u tu tabelu.

### 2.6 AC-09 (NISKA) — interpolacija u PostgREST filter

`routers/zadaci.py:314` i `:326`:

```python
.or_(f"dodeljen_uid.eq.{uid},kreirao_uid.eq.{uid}")
```

`uid` ide u filter string kroz f-string, bez escape-a. **Nije iskoristivo danas**: `uid` je
`sub` claim iz JWT-a čiji je potpis verifikovan (`shared/deps.py:196-226`), dakle UUID koji
je izdao Supabase, a ne korisnički unos. Navedeno kao hardening jer je obrazac („string
filter sastavljen konkatenacijom") pogrešan i lako se kopira na mesto gde vrednost **jeste**
korisnički unos.

---

## 3. Supabase Storage

### 3.1 Koji bucketi postoje

Repo-wide grep za `.storage.from_(` daje tačno **tri** bucket-a u produkcijskom kodu:

| Bucket | Pisač | Ključ objekta | Šifrovanje pre uploada |
|---|---|---|---|
| `klijent-dokumenti` | `klijenti/router.py:809` | `generate_storage_key()` → `encrypted_blob_<uuid4>` | **DA** — AES-256-GCM, `klijenti/router.py:797-806` |
| `intake-dokumenti` | `routers/smart_intake.py:185`, `api.py:5051` | `{user_id}/{uuid4().hex}` | **DA** — `_encrypt()`, `routers/smart_intake.py:96-105` |
| `portal-uploads` | `routers/client_portal.py:591` | `{advokat_uid}/{predmet_id}/{uuid4().hex}_{ime}` | **NE** — `sadrzaj` se šalje sirov (`:593-599`) |

### 3.2 Javni ili privatni — dokaz, ne pretpostavka

| Bucket | Dokaz iz repoa | Zaključak |
|---|---|---|
| `intake-dokumenti` | `migrations/073_intake_foundations.sql:362-364`: `INSERT INTO storage.buckets (id,name,public) VALUES ('intake-dokumenti','intake-dokumenti', false) ON CONFLICT (id) DO NOTHING` | **Deklarisan privatnim** — ali `ON CONFLICT DO NOTHING` znači da ako je bucket ranije ručno napravljen kao javan, migracija ga **ne** ispravlja. Migracija to i priznaje u komentaru na `:360`. |
| `portal-uploads` | `migrations/013_client_portal_uploads.sql:5`: `-- Dashboard → Storage → New bucket → Ime: "portal-uploads" → Private` | **UNKNOWN.** To je uputstvo čoveku u SQL komentaru, ne naredba. Ništa u repou ne postavlja ni ne proverava `public`. |
| `klijent-dokumenti` | nijedna migracija, nijedan `INSERT INTO storage.buckets`, nijedan `CREATE POLICY ON storage.objects` | **UNKNOWN.** Bucket je napravljen ručno u Dashboard-u i njegov status je nevidljiv za reviziju koda. |

Isto važi za RLS nad Storage-om: **nigde u repou ne postoji `CREATE POLICY` nad
`storage.objects`**. To potvrđuje i ranija revizija (`docs/lambda/RLS_CERTIFICATION.md:96`),
i ovaj prolaz to nezavisno potvrđuje.

**Zaključak koji se sme izgovoriti:** privatnost bucket-a se **ne može dokazati iz koda ni
za jedan od tri**, a za dva ne postoji ni pokušaj da se postavi. Zaštita koja stvarno
postoji je: (a) nepogodivi `uuid4` ključ, (b) obavezna provera vlasništva u aplikaciji pre
svakog izdavanja bajtova ili signed URL-a, (c) AES-GCM za dva od tri bucket-a.

**Jedno konkretno pitanje za osnivača (jedan upit, read-only):**
`SELECT id, public FROM storage.buckets ORDER BY id;`

### 3.3 AC-06 — asimetrija koja je najgora tamo gde ne bi trebalo da bude

`portal-uploads` je jedini bucket koji sadrži **nešifrovane** bajtove — i to je bucket u koji
piše **neautentifikovana spoljna strana** (klijent sa tokenom, `routers/client_portal.py:514`,
bez logina). To je tačno obrnuto od željenog rasporeda rizika. `klijenti/router.py` i
`routers/smart_intake.py` oba koriste isti `security.crypto._get_field_key()` + AESGCM
obrazac; `client_portal` ga ne poziva.

Ako je `portal-uploads` javan (nedokazano), sadržaj je dohvatljiv svakome ko zna ključ —
a ključ sadrži `{advokat_uid}/{predmet_id}/` prefiks, pa jedan poznat par UUID-jeva sužava
prostor na `uuid4().hex` po fajlu (i dalje nenabrojiv, ali plaintext).

### 3.4 Potpisani URL-ovi

Postoji **tačno jedan** put koji generiše signed URL u celom repou:
`routers/client_portal.py:701-705`.

- **Ko ih pravi:** `GET /api/client-portal/uploads/{predmet_id}`, tek nakon
  `predmeti.eq("id").eq("user_id", uid)` (:670-678) **i** `.eq("advokat_user_id", uid)` (:685).
- **Koliko traju:** `create_signed_url(_p, 3600)` — 60 minuta.
- **Ko sme da ih traži:** samo vlasnik predmeta. Klijent kroz portal ih **ne dobija** —
  `client_portal_view` ne vraća nijedan dokument (§4.1).
- **Kešira li se:** ne. Generiše se novi na svaki poziv.
- **Ostatak:** URL je bearer — ko ga dobije u roku od sat vremena, dohvata fajl. To je
  standardno ponašanje Supabase Storage-a i nije nalaz, ali jeste činjenica koju treba znati
  ako se URL nekad ubaci u email ili log.

Preuzimanje iz `klijent-dokumenti` **ne koristi** signed URL — bajtovi se dekriptuju i
streamuju kroz aplikaciju uz watermark (`klijenti/router.py:960-993`). To je jača postavka.

### 3.5 AC-08 — brisanje: iz baze ili iz Storage-a?

| Putanja | Briše iz Storage-a | Briše iz baze |
|---|---|---|
| `DELETE /api/client-portal/uploads/{upload_id}` (`:750-816`) | **DA** (:778-780) | DA (:785-791) |
| kompenzujuće brisanje sirotčeta — `client_portal.py:635`, `smart_intake.py:216`, `klijenti/router.py:841`, `api.py:5254` | DA | n/a |
| `DELETE /api/gdpr/account` (`routers/gdpr.py:201-251`) | **NE** | ne — samo anonimizuje `profiles` |
| `predmet_dokumenti` | — | **ne postoji nijedna ruta za brisanje** |
| `klijent_dokumenti` | — | kolona `deleted_at` postoji, **nijedan kod je ne postavlja** |

`routers/gdpr.py:249-252` to i kaže korisniku otvoreno: *„Predmeti, klijenti i dokumenti
nisu anonimizovani ovim postupkom i zadržavaju se…"*.

Posledica: šifrovani originali u sva tri bucket-a **ostaju zauvek** posle brisanja/
anonimizacije naloga. To nije rupa u kontroli pristupa (niko drugi time ne dobija pristup),
ali jeste stvarna praznina u retenciji za proizvod koji drži pravne spise. Slaže se sa
nalazom iz `docs/lambda/STORAGE_SECURITY_REPORT.md`; ovde je nezavisno potvrđeno i prošireno
činjenicom da ni `predmet_dokumenti` ni `klijent_dokumenti` nemaju putanju brisanja uopšte.

---

## 4. Klijentski portal

U proizvodu postoje **dva** nezavisna portal sistema. To je samo po sebi nalaz — dva
mehanizma za istu stvar, sa različitim garancijama.

### 4.1 Sistem 1: HMAC portal token (`routers/client_portal.py`) — ISPRAVAN

**Oblik tokena** (`:81-88`): `base64url("{predmet_id}:{user_id}:{exp}") + "." + HMAC-SHA256(SECRET_KEY, isto)`.
U bazi (`client_portal_tokens.token_hash`) čuva se samo SHA-256 tokena — curenje baze ne
otkriva token.

**Šta klijent tačno vidi** (izmereno, `client_portal_view` :484-496):

```
['predmet', 'hronologija', 'rocista', 'kriticni_rokovi', 'token_expires_at']
```

- `predmet`: samo `naziv`, `opis`, `tip`, `status`, `created_at` — SELECT je već sužen na
  te kolone (:427), ne filtrira se posle.
- `hronologija`: bez događaja sa prefiksom `[INTERNI]` i bez `vaznost == "interni"` (:471-476).
- `rocista`: bez otkazanih; **bez internih napomena** — kolona `napomena` se ne selektuje.
- **Nijedan dokument.** Ni naziv, ni metapodatak, ni signed URL. Klijent može samo da
  *pošalje* fajl (`POST /api/client-portal/dokument`), nikad da preuzme.

**Može li token jednog klijenta da dohvati dokument drugog?** Ne. Izmereno:

| Napad | Ishod |
|---|---|
| legitiman token klijenta B | 200, „Predmet B" |
| **payload zamenjen na `PRED-A`, potpis ostavljen** | **401** (`hmac.compare_digest` pada, `:123`) |
| token opozvan (`is_active = false`) | 401 |
| token istekao (`exp` u prošlosti) | 401 |
| ubacivanje `predmet_id` kroz query/header | **nemoguće** — potpis funkcije je `(request, x_portal_token)`; `predmet_id` nije parametar rute nigde u portal delu |

`predmet_id` postoji **samo** unutar potpisanog payload-a. To je ispravan dizajn i drži.

**Koliko token traje:** podrazumevano 30 dana, maksimalno 90
(`_DEFAULT_VALJANOST_DANA = 30`, `_MAX_VALJANOST_DANA = 90`, `:68-69`). Opoziv postoji i
radi: `DELETE /api/client-portal/token/{token_id}` (:352) i provera `is_active` na svakom
pozivu (:415).

**Sitno, vredno beleške:** token se šalje u `X-Portal-Token` **header-u**, ali email koji
advokat šalje klijentu sadrži `{base_url}/portal?token={token}` (:292) — token dakle
**jeste** u URL-u u email-u i u istoriji pregledača, iako ne u API pozivu. Komentar na
`:393-394` tvrdi da se header koristi „da se smanji log leakage"; to važi za API sloj, ne za
ulaznu tačku.

### 4.2 Sistem 2: `privremeni_pristup` (`routers/saradnja.py` + `api.py`) — AC-05

Drugi, stariji mehanizam:

- kreira se u `routers/saradnja.py:416-465`, token `secrets.token_urlsafe(32)`, **čuva se
  u bazi u čistom obliku** (`:440`) — za razliku od Sistema 1 koji čuva samo hash
- troši se u `api.py:2570-2663` `GET /api/portal/predmet?token=...`, **bez logina**
- trajanje: do **168 sati** (`:427`)

Nalazi:

1. **Ne postoji nijedna putanja opoziva.** Kolona `iskoriscen` se proverava
   (`api.py:2589`), ali repo-wide grep pokazuje da je **nijedan kod nikad ne postavlja na
   `true`**. Nema ni DELETE rute, ni `is_active` ekvivalenta. Jednom izdat token važi punih
   7 dana, i tačka.
2. **Token ide u URL** — `link = f"{base_url}/app?privremeni_token={token}"` (`:457`).
   URL-ovi završavaju u istoriji pregledača, Referer zaglavljima i logovima obrnutog
   proksija.
3. **Polje `dozvole` se piše (`:441`) i nikad ne čita.** `api.py:2570` ne konsultuje ga.
   „Samo čitanje" nasuprot bilo čemu drugom je deklaracija bez izvršenja.
4. **Link je pokvaren.** `/app` servira `index.html` (`api.py:2554-2556`); jedini potrošač
   `privremeni_token` parametra je `client_portal.html:251`, koji se servira na `/portal`
   (`api.py:2559-2565`). Poslati link ne otvara ništa upotrebljivo. Funkcionalni bug, ali
   objašnjava zašto ovaj sistem verovatno nema stvarnih korisnika — što snižava praktičnu
   ozbiljnost tačaka 1-3, ne i njihovu tačnost.

Ono što ova ruta **jeste** ispravno uradila: `predmet_id` i `vlasnik_user_id` uzima
isključivo iz reda u bazi (`api.py:2603-2604`), pa nema IDOR-a preko parametra. Odgovor je
sužen na 9 polja (`:2653-2662`) i ne sadrži dokumente (`"dokumenti": []`).

**Preporuka:** ugasiti Sistem 2 u korist Sistema 1, ne popravljati ga. Dva portala su dupli
napadni prostor za jednu funkciju.

---

## 5. Admin / service-role zaobilaženje

| Putanja | Namerno? | Zabeleženo? |
|---|---|---|
| `predmet_delegiranja` — `api.py:4131-4147` | **DA.** Ako `predmeti.eq(user_id)` ne nađe red, proverava se aktivna delegacija `.eq("predmet_id").eq("na_user_id", user.id).eq("status","aktivno")` i tek onda se predmet čita bez `user_id` filtera | **DA**, komentar `:4131-4139` izričito ograničava ovo na READ; write akcije ostaju samo vlasniku |
| `predmet_saradnici` uloga `vodenje` — `routers/client_portal.py:236-257`, `routers/saradnja.py:305-345` | DA | DA |
| `FOUNDER_EMAILS` → `Role.PARTNER` — `klijenti/router.py:60-62`, `klijenti/permissions.py:131-135` | DA | DA |
| `X-Admin-Token == FOUNDER_TOKEN` — `routers/dokument.py:390-394` | DA, i dodiruje samo istekle `tmp_` namespace-ove | DA |
| `_require_admin` — `routers/batch_ingest.py:257`, `routers/law_upload.py:267` | DA, i dodiruje samo globalne resurse (`ingest_jobs`, `law_docs`), nikad podatke kancelarije | DA |
| `FOUNDER_EMAILS` gate — `routers/status_page.py:115-117`, `routers/waitlist.py:209-210`, `routers/smart_intake.py:89-92` | DA | DA |

**Nema nijedne rute na kojoj founder ili admin vidi tuđi dokument ili sadržaj predmeta.**
Founder-ov privilegovan status se u kodu koristi za: neograničene kredite
(`shared/deps.py:534`, `:594`), `PARTNER` rolu, i administraciju globalnog korpusa zakona i
waitliste. Ni jedan founder gate ne otvara `predmeti`, `predmet_dokumenti`,
`klijent_dokumenti` ni `client_portal_uploads`.

**Jedini nenameran „admin" put je AC-01** — i on nije čitanje tuđih dokumenata, nego izmena
tuđih prava.

---

## 6. Da li je i dalje tačno da RLS ne štiti?

**Da, i to je i dalje tačna formulacija za javni sajt — ali je sada nepotpuna.**

### 6.1 Backend: potvrđeno, ništa se nije promenilo

`shared/deps.py:88-93` je jedina konstrukcija klijenta u backend putanji:

```python
if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise RuntimeError(...)
_supa = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
```

`api.py:169` je isti obrazac (nasleđena kopija). Repo-wide grep za `create_client` u
produkcijskom kodu daje **samo ta dva mesta**, oba sa `SUPABASE_SERVICE_KEY`. Service ključ
po definiciji zaobilazi RLS. Svaka izolacija koju je ovaj audit merio je **ručni `.eq()` u
Python kodu**, ne baza. `CONTENT_TRUTH_MAP.md` je i dalje u pravu: tvrdnja „zaštićeno na
nivou baze" se **ne sme** pojaviti na sajtu.

### 6.2 Šta se promenilo: postoji drugi kanal na kome RLS **jeste** jedina odbrana

`static/vindex.js:236,242` — pregledač pravi **sopstveni** Supabase klijent sa **anon**
ključem (`sb_publishable_...`, hardkodiran u JS-u, kako i treba za anon ključ). Kroz taj
klijent frontend direktno gađa bazu na tri mesta:

| Poziv | Fajl:linija | Jedina odbrana |
|---|---|---|
| `profiles.update({full_name})` | `static/vindex.js:713` | RLS + column GRANT |
| `conversations.insert / select.eq(session_id)` | `:989`, `:1000` | RLS politika `conversations_own` |
| `reported_errors.insert` | `:8068` | RLS insert-own politika |

Za **te tri tabele** RLS nije dekorativan — on je jedina kontrola. Relevantno stanje:

- `migrations/103_lambda002_profiles_column_lockdown.sql` (`REVOKE UPDATE ... GRANT UPDATE (full_name)`)
  — zabeleženo kao **VERIFIED APPLIED**, `docs/beta_gate/BETA_GATE_BLOCKER_CLOSURE_REPORT.md:29,63`
- `migrations/102_lambda002_rpc_ownership_lockdown.sql` — **VERIFIED APPLIED**, isti izvor
- `migrations/110_rls_lockdown_idempotent.sql` — **APPLIED + VERIFIED**,
  `docs/beta_gate/MIGRATION_110_VERIFICATION.md` (109 je pao i superseded je)
- `conversations` — `migrations/077_sec031_restrict_auth_users_cascade.sql:58,96,146` tvrdi
  da tabela **ne postoji** u ovoj bazi („ocekivano: false, trajno"). Ako je to tačno,
  `saveTurnToSupabase`/`loadChatHistory` tiho ne rade ništa (oba su u `try/catch` sa
  `console.warn`) i rizik je nula. **Nije potvrđeno u ovoj sesiji** — nemam pristup bazi.

**Precizna formulacija koju predlažem umesto „RLS ne štiti":**

> Aplikacija se povezuje service ključem koji zaobilazi RLS; izolacija podataka predmeta i
> klijenata je ručni filter u kodu, ne baza. RLS je stvarna kontrola samo na tri tabele
> koje pregledač dohvata direktno anon ključem (`profiles`, `conversations`,
> `reported_errors`), i tamo je pojačan kolonskim GRANT-om (migracije 102/103/110,
> potvrđene primenjenim).

---

## 7. Šta ovaj audit NE tvrdi

- **Nije provereno živo stanje baze.** `SUPABASE_DB_URL` nije dostupan (izostaje od
  Operation Black Swan, 2026-08-02). Sve o `storage.buckets.public`, o postojanju
  `conversations`, i o tome da li je AC-03 ikad iskorišćen — **UNKNOWN**, ne „u redu".
- **Nisu testirane trke (TOCTOU).** Merenje je jednonitno.
- **Nije provereno šta radi Pinecone sloj** izvan `_verify_pred_namespace_ownership`.
- **AC-03 nije izmeren end-to-end**, samo dokazan čitanjem oba kraja lanca (§2.4).
- Merenje pokriva **17 ruta** od 160 sa `{*_id}`. Ostale su prošle statičku proveru
  (predikat vlasništva prisutan u samom upitu ili u dokazanom helper-u), što je slabiji
  dokaz od izvršavanja.

---

## 8. Redosled ispravki (predlog, ništa nije menjano)

1. **AC-01** — `klijenti/router.py:1196`. Ograničiti `target_user_id` na istu kancelariju
   kao pozivalac, ili (bolje) dodati `kancelarija_id` u `user_roles` i skopirati celu rolu
   na kancelariju. Dok to ne postoji, ruta je globalna.
2. **AC-03** — `api.py:3377` i `api.py:4895`. Dodati istu proveru koju `api.py:4372` već
   ima. Tri linije, isti obrazac koji već postoji u istom fajlu.
3. **AC-02 / AC-04** — `routers/zadaci.py:143` i `:346`. Provera vlasništva nad
   `payload.predmet_id`; provera članstva u kancelariji za `dodeljen_uid`.
4. **AC-07** — jedan read-only upit osnivaču: `SELECT id, public FROM storage.buckets;`
   Dok odgovor ne stigne, javna tvrdnja o privatnosti fajlova nije dozvoljena.
5. **AC-06** — šifrovati `portal-uploads` istim `_encrypt` obrascem koji već postoji na
   druga dva bucket-a.
6. **AC-05** — ugasiti `privremeni_pristup`; Sistem 1 pokriva isti scenario ispravno.
7. **§2.5** — `user_id` kolona na `case_actions`, ili jedan zajednički helper kao jedini
   ulaz u tabelu.
8. **AC-08** — brisanje blobova pri GDPR anonimizaciji; posebna odluka o retenciji.

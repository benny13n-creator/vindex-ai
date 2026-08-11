# BETA RELEASE CANDIDATE — FINAL STABILITY & DEPLOY GATE

---

# RELEASE GATE

| Gate | Status |
|---|---|
| Migration 111 | 🟢 ispravna i dokazana lokalno · **produkcija = vlasnikovo svedočenje** |
| Migration 112 | 🟢 ispravna i dokazana lokalno · **produkcija = vlasnikovo svedočenje** |
| Cold start | 🟢 dva puna ciklusa, governance bit-po-bit identičan |
| Governance runtime | 🟢 aktivan u svežem procesu i u pravom uvicorn serveru |
| Context isolation | 🟢 cross-tenant odbijen na 4 fronta odjednom |
| Billing atomicity | 🟢 6 ugovora nad pravim PostgreSQL-om |
| Zero-credit protection | 🟢 0 GPT poziva pri 0 kredita |
| Retry safety | 🟢 isti `job_id`, jedna naplata |
| Frontend duplicate-click | 🟢 stvarno izvršavanje JS-a, 1 zahtev |
| Beta smoke | 🟢 6 tokova od kraja do kraja |
| Full regression | 🟢 **4758 passed / 1 skipped / 0 failed** |
| Worktree clean | 🟢 |

---

# REGRESSION

| | |
|---|---|
| Baseline | `4643 passed / 1 skipped / 0 failed` (`3097529a`) |
| **Final** | **`4758 passed / 1 skipped / 0 failed`** (`65fe0705`) |

**+115 testova, 0 padova, 0 novih skipova.** Jedini `skipped` je i dalje
`test_apr_integration.py:394` — namerni live-network test iza env prekidača,
isti kao u baseline-u. Nijedan test nije obrisan, oslabljen ni skipovan; nijedan
timeout nije podignut.

---

# CHANGES — stvarne produkcione izmene

Tačno **jedna**.

### `shared/usage.py` — RC-112-DEBT-001

`feature_usage_log.predmet_id` je tipa `uuid` (migracija 112). Upis vrednosti
koja nije UUID daje PostgreSQL grešku **22P02**. Ta poruka ne sadrži `42703`,
`does not exist`, `PGRST204` ni `schema cache` — pa `_nedostaje_kolona()` vraća
`False`, uzak fallback se **ne aktivira**, i **ceo red naplatne telemetrije tiho
nestaje**, zajedno sa `user_id`, `feature_key` i `krediti_potroseni`.

Popravka validira UUID pre upisa i odbacuje **samo to polje**. Zašto ne širenjem
`_nedostaje_kolona` na 22P02: to bi odbacilo **oba** provenance polja, a
`correlation_id` je taj koji tranzitivno vodi do predmeta preko `ai_forensics`.

Neispravan **eksplicitan** argument briše i vrednost iz konteksta — pogrešna
atribucija naplate je gora od `NULL`-a.

> Danas nedostižno (0 pozivalaca prosleđuje `predmet_id`). Postaje dostižno čim
> prvi počne. Naplata se ni u jednom slučaju ne obara zbog telemetrije — fail-soft
> ugovor je zasebno dokazan.

Sve ostalo su testovi, skripte i dokumentacija.

---

# DVA VAKUUMSKA TESTA ZATVORENA

Nijedan nije obrisan ni oslabljen — oba su **pooštrena**.

### RC-BILLING-002 — test koji je razoružao sam sebe

`tests/test_wave6_preflight_balance.py::test_d` postoji tačno da uhvati „naplati
pre AI posla". Merio je poziciju prvog `asyncio.to_thread(` kao mesto AI posla.
Kad je pisan, to je bilo tačno.

Ali **pre-flight kapija, dodata u istom Wave 6 sprintu**, uvela je raniji
`asyncio.to_thread(_get_credits, uid)`. Od tada `poz_thread` pokazuje na čitanje
bilansa. Pošto kapija po konstrukciji uvek prethodi naplati, uslov je bio
zadovoljen **bez obzira gde AI posao stoji**.

Kako je nađen: mutacija „naplata pre AI posla" oborila je **8 drugih testova** —
a baš ovaj, jedini napisan za taj redosled, prošao je zeleno.

Sada meri poziciju **stvarnog** AI posla, uz negativnu kontrolu samog merenja.
Verifikovano: pod istom mutacijom sada **pada**.

### RC-TEST-DEBT-001 — vrednosti koje produkcija odbija

`tests/test_wave9_usage_provenance.py` je koristio `"PRED-42"` kao `predmet_id`.
Nad lažnim klijentom prolazi, produkciona šema odbija. **Tvrdnje su
nepromenjene** — zamenjen je samo ulaz produkciono-realnim UUID-evima, da test
meri ono što tvrdi da meri.

---

# NOVI GATE-OVI — 115 testova

| Fajl | Testova | Šta dokazuje |
|---|---|---|
| `test_rc_cold_start.py` | 23 | Cold start ×2 u **podprocesima koji ništa ne nasleđuju**. Governance bit-po-bit identičan, svih 8 SDK metoda nosi `_vindex_guarded`, 5 potrošača deli **jednu** `Limiter` instancu, drugi patch ne ugnežđuje wrapper. Aplikacija se stvarno digne i ugasi dvaput; `pid` različit. |
| `test_rc_migration_gate.py` | 35 | Ceo lanac migracija `064→112` nad svežom bazom, svaki `.sql` čitan sa diska. 112 idempotentna (Wave 9 to nije pokrivao), redosled 111/112 ne utiče na ishod, **0 konflikata među 238 imena indeksa**, `feature_analytics` VIEW preživeo. |
| `test_rc_beta_flows.py` | 33 | 6 tokova od kraja do kraja. Cross-tenant sada tvrdi i **četvrtu** stvar koju nijedan test nije pokrivao: nijedan trajan zapis za nedozvoljen predmet. Governance meren na **jednom** pozivu sa poklapanjem `correlation_id`-a kroz sve karike. |
| `test_rc_billing_gate.py` | 24 | 6 ugovora nad pravim PG-om **bez ugašenih delova puta** — postojeći dokazi gase ili `_log_usage_event` ili `_claim_cooldown_atomic`; ovde se meri i novac i telemetrija. |

**20 mutacija izvršeno, sve obaraju očekivane testove.**

---

# ŠTA NIJE DOKAZANO — izričito

| | |
|---|---|
| **Produkciona primena migracija** | Vlasnik je potvrdio da su 111 i 112 pokrenute. **To je svedočenje, ne dokaz.** Nemamo `SUPABASE_DB_URL` i po pravilima sprinta ga ne tražimo. |
| **Produkcioni `/api/version`** | Vraća **HTTP 403 na ivici** (bot zaštita). Nisam pokušavao da je zaobiđem. |
| **Registracija/login kao HTTP tok** | Auth chokepoint je zamenjen `dependency_overrides`-om, po obrascu celog repoa. Verifikacija tokena nije izvršena. |
| **Cross-worker garancije** | `_jobs` store i dedupe su po procesu — što `create_job_deduped` i sam priznaje. Dokazano unutar jednog workera. |
| **Ulazni guard „je opalio"** | `_analyze` je u zatvorenju i ne može se zameniti špijunom bez deinstalacije guarda. Meren **efektom** (injection ne stigne do provajdera) — slabija tvrdnja, i tako je označena. |

---

# OWNER ACTIONS — 2, obe opcione potvrde

**1. Potvrda migracija** (PowerShell, koren repoa):

```powershell
$env:SUPABASE_DB_URL = '<connection string>'
python scripts/verify_migration_111.py ; echo "111 -> $LASTEXITCODE"
python scripts/verify_migration_112.py ; echo "112 -> $LASTEXITCODE"
Remove-Item Env:SUPABASE_DB_URL
```

Obe skripte su read-only (`default_transaction_read_only=on`) i **nikad ne
ispisuju connection string**. `0` = primenjeno, `1` = FAIL sa imenovanom tačkom,
`2` = nedostaje `psycopg`/env.

⚠ Poslednja linija nije kozmetika: `tests/conftest.py` namerno obara kolekciju ako
`SUPABASE_DB_URL` ostane u shell-u.

**2. Produkcioni `/api/version` u pretraživaču** — potvrditi `commit` i
`governance.active: true` na deployed build-u.

---

# DEFERRED — NOT RELEASE BLOCKING

| ID | Nalaz | Zašto nije blocker |
|---|---|---|
| `RC-111-OBSERVE-001` | `conflict_check` ostaje `minimum_plan='professional'` | **Provereno merenjem:** intake čarobnjak zove `/api/intake/conflict-check`, koja je `Depends(get_current_user)` — negejtovana. Basic korisnik može da kreira predmet. Gejtovana je samo eksplicitna CRM akcija; 403 je tamo normalno ponašanje proizvoda. |
| `RC-112-OBSERVE-002` | 112 nema `BEGIN;/COMMIT;` (111 ima) | Sve je `IF NOT EXISTS`; ponovno pokretanje dovršava posao. |
| `RC-DEDUPE-001` | Retry posle `done` pokreće novu, naplaćenu analizu | Po dizajnu je to nova analiza. Granica nije vidljiva klijentu — kandidat za DB-backed dedupe. |
| `RC-PREFLIGHT-001` | 7 pojedinačnih modula nema pre-flight kapiju bilansa | Izloženost je 1 GPT poziv umesto 8; odnos trošak/rizik je drugačiji. |
| `RC-ORDER-001` | 7 modula nema čuvara redosleda naplate | Redosled je **danas ispravan**, provereno AST prolazom svih 9 funkcija. Rizik regresije, ne aktivan defekt. |
| `RC-COURT-001` | `court_predictor` čita `activePredmetId`, ostalih 7 `dataset.predId` | Svesno (PROGBETA-001) — dira readiness cap. |
| `RC-STARTUP-001` | Startup zove Pinecone pre prvog zahteva | Fail-soft; cold start zavisi od izlazne mreže. |

---

# 🟢 **RELEASE VERDICT: GO**

**Beta release candidate je stabilan.**

Lanac je dokazan **cel**, ne po delovima:

```
CODE → DATABASE → CLEAN PROCESS → RUNTIME → USER FLOW → BILLING → GOVERNANCE → REGRESSION
```

Nijedna karika nije proglašena zelenom na osnovu toga što testovi prolaze —
svaka ima mutaciju koja je obara.

**GO je uslovljen jednom stvari koja nije inženjerska:** produkciona primena
migracija 111 i 112 počiva na vašoj potvrdi. Dve read-only komande iznad tu
poslednju kariku pretvaraju iz svedočenja u dokaz. Do tada je ispravno reći:
*build je spreman za prvog beta korisnika, a stanje produkcione baze je
potvrđeno od vlasnika a ne od gate-a.*

---

# NAJVREDNIJI NALAZ OVE NOĆI

Nije nijedan od popravljenih defekata. Nego ovo:

> **Wave 6 popravka je razoružala Wave 6 test.**
> Test napisan tačno da uhvati „naplata pre AI posla" bio je jedini koji tu
> mutaciju nije uhvatio — dok ju je 8 drugih uhvatilo.

To je podsetnik da zeleni test nije dokaz dok se ne vidi kako pada. Ceo ovaj
program stoji na tome; ovde je taj princip uhvatio sopstvenu prošlost.

# BETA HARDENING WAVE 10 — ENVIRONMENT & RELEASE LOCK

Remediation sprint. Dva rizika dokazana u Wave 9, ništa novo traženo.

---

# BASELINE → FINAL

| | Pre | Posle |
|---|---|---|
| HEAD | `4300b51b` | `e2dadc55` |
| Testovi | 4582 passed / 1 skipped / 0 failed | **4643 passed / 1 skipped / 0 failed** |
| Stablo | čisto | čisto |

Jedini `skipped` je `test_apr_integration.py:394` — namerni live-network test iza
env prekidača, isti kao u baseline-u. Nijedan test nije obrisan, oslabljen ni
označen `skip`; nijedan timeout nije podignut.

---

# CLOSED

## 1. Production DB write protection

**Wave 9 je problem rešavao na nivou DNS-a**, sa allowlist-om od 115 imena, i
pošteno ga označio kao *„sadržano, ne zatvoreno"*. Wave 10 ga rešava na nivou
**konfiguracije**, gde je i nastao.

| Sloj | Šta radi |
|---|---|
| **1 — konfiguracija** *(primarni)* | `.env` DB kredencijali se više ne uvoze u test proces |
| **1b — kapija** | izričito izvezena produkciona konfiguracija obara kolekciju **pre prvog testa** |
| **2 — DNS** *(dubinski)* | blokira KLASU hostova upravljanih baza |

Sloj 1 nije *„pametno prebacivanje na drugu bazu"* nego odbijanje da se
produkciona konfiguracija uveze — posle njega baze prosto **nema**. Postavljene
sankcionisane vrednosti su postojeća konvencija repoa (`fake.supabase.co`, koju
24 test fajla već koriste preko `setdefault`) — konvencija koja je do sada bila
**nedelotvorna baš zato što je `.env` učitan prvi**, pa `setdefault` nije imao
šta da postavi.

**Detekcija** (`tests/prod_db_guard.py`) gleda **host, port, ime baze, oblik
ključa i environment marker** — ne samo hostname. Fail-closed u oba smera:
neparsabilna ili nepoznata konfiguracija tretira se kao produkcija.

Izdvojena je u zaseban modul **baš zato da bi mogla da se pozove sa izmišljenom
konfiguracijom i posmatra kako pada**. Provera zakopana u `conftest.py` izvršava
se jednom i niko ne može da dokaže da radi — Wave 9 je već pokazao šta se dešava
sa takvom zaštitom.

## 2. Merenje koje je promenilo pristup

Sa sankcionisanim kredencijalima, od **455 testova u tih 42 fajla pada TAČNO
JEDAN**:

`tests/test_ztc_scenario_b_attach.py` → `routers/smart_intake.py:1525` →
`shared/audit_immutable.log_action` → `_get_last_hash(supa)` — stvarno je čitao i
pisao u **produkcioni hash-lančani ledger na svakom pokretanju suite-a**.
Popravljen mokom.

Ostalih **114** je produkciju dodirivalo isključivo kroz fail-soft putanje koje
se identično ponašaju i kad hosta nema.

> **Allowlist nikad nije ni trebao.** Bio je posledica rešavanja problema na
> pogrešnom sloju. Lista je ispražnjena, brojač spušten sa **115 na 0**.

## 3. Append-only production isolation

`audit_immutable` i `ai_provenance` su append-only iza BEFORE UPDATE/DELETE
trigera i hash-lančane — upisan red se **ne može obrisati**. Zato se dokazuje da
konekcija pada **pre** write-a, a ne da se zapis naknadno čisti.

Usput zatvoren još jedan **meren** hazard: 4 PostgreSQL testa imala su fallback
na port **5432** — trajni servis na ovoj mašini, sluša na `0.0.0.0`, nosi stvarne
podatke. Ti testovi **prave i brišu baze**. „Loopback" nije isto što i
„potrošno". Fallback uklonjen; bez podignutog klastera se sada preskaču umesto da
tiho koriste pogrešnu bazu.

## 4. Rate limiter state isolation

Postojale su **dve žive instance** (`shared/rate.py` za dekoratore ruta,
`api.py:554` za `app.state.limiter` i `SlowAPIMiddleware`), a posle
`importlib.reload` i **tri**. Gašenje limitera preko `shared.rate` gasilo je
instancu koju rute ne koriste — izolovano zeleno, u punom suite-u **84 pada**.

| | Pre | Posle |
|---|---|---|
| Žive instance *(mereno po `id()`)* | 2 (+1 posle reload-a) | **1** |

`reset_limiter_state()` je produkciona funkcija: briše brojače, `_fallback_storage`
i vraća instancu iz *„storage je mrtav"* režima — ne samo `enabled = False`.
Autouse fixture je primenjuje na svaki test.

`importlib.reload` je iz testa **uklonjen, ne zakrpljen**: isto se postiže preko
`monkeypatch.setattr(rate_module, "_REDIS_URL", …)`, bez ponovnog izvršavanja tela
modula.

## 5. Test DB bootstrap

`scripts/test_db.py` — `up` / `status` / `verify` / `down`, tačno četiri koraka iz
mandata. Data dir u sistemskom temp-u, idempotentan `up`, nikad ne ispisuje
lozinku ni pun DSN.

`verify` ima **7 fail-closed kriterijuma**. K1–K3 su statički i idu **pre**
povezivanja. K4–K7 pitaju **server** (`inet_server_addr()`, stvarni port,
`data_directory`, odsustvo Supabase šema) umesto da veruju tekstu DSN-a — bez njih
bi **tunelovana produkcija na `127.0.0.1:55432`** prošla sve statičke provere.

`P0_CLOSURE_LEDGER.md` ručna procedura označena zastarelom: `-m immediate stop` +
bezuslovni `Remove-Item` brišu klaster i kad je u upotrebi, a `pg_ctl start` sa
nasleđenim pipe-om se na Windows-u **zaglavi** (mereno: >180 s bez povratka).

---

# VERIFIED

| | |
|---|---|
| **Targeted testovi** | 34 (`prod_db_guard`) + 7 (`rate_limiter_isolation`) + 15 (`test_db_bootstrap`) + 15 (`network_guard`) |
| **115-test diferencijal** | **455 passed / 0 failed** u 42 fajla |
| **Puna regresija** | **4643 passed / 1 skipped / 0 failed** |
| **Stablo** | čisto |

## Mutation evidence

| # | Mutacija | Očekivano | Stvarno |
|---|---|---|---|
| **M1** | uklonjena kapija za produkcionu konfiguraciju | pad | `test_e` — *„suite se pokrenuo uprkos produkcionoj konfiguraciji"* |
| **M2** | zaobiđena detekcija `SUPABASE_URL` | pad | **5 testova** palo |
| **M3** | `api.py` ponovo gradi svoju instancu | pad | `test_d` — *„postoji više od jedne žive Limiter instance"* |
| **M4** | reset samo jedne reference, ruteri drže staru | pad | **5 testova** palo |
| **M5** | uklonjena provera hosta iz `verify` | pad | **3 testa** pala |

**Dve mutacije su otkrile greške u samim testovima — i to je njihova najveća
vrednost u ovom sprintu:**

**M4** je prvo prolazila neprimećeno. Uzrok: testovi su uvozili `api`/`routers.*`
*unutar* test funkcija, pa lazy uvoz pokupi novu instancu **posle** fixture-a.
Uvozi su premešteni na nivo modula — kao u produkciji — i tek tada je mutacija
uhvaćena.

**Sopstveni `test_b`** je uhvatio pravu rupu u detektoru: host
`neki-host.example-corp.net` prolazio je kao test target zbog **podniza**
„example". Prešlo se na poklapanje po **labelama**. Lažno negativan u smeru koji
košta — nepoznat produkcioni host proglašen bezbednim.

---

# OWNER BLOCKED

**Nijedna stavka iz opsega ovog sprinta.**

Migracije **111** i **112** ste pokrenuli — time su i dve preostale owner stavke
iz Wave 9 zatvorene. Verifikacija migracije 111 se po želji pokreće sa:

```
SUPABASE_DB_URL='<conn>' python scripts/verify_migration_111.py
```

Skripta je read-only i nikad ne ispisuje connection string. To nije blokada
sprinta nego opciona potvrda.

---

# DEFERRED_DISCOVERY

Evidentirano tokom rada, **nije popravljeno** — ne pripada opsegu ovog sprinta.

| # | Nalaz |
|---|---|
| **D1** | `api.py` ima ~27 sopstvenih `@limiter.limit()` dekoratora. Ranije su bili na privatnoj instanci zajedno sa middleware-om, pa je `api.py` bio interno konzistentan a ruteri odvojen svet. Sada dele storage sa ruterima. Semantika key-ovanja je nepromenjena, ali vredi svesna potvrda pre deploy-a. |
| **D2** | `shared/rate.py:45` — `_REDIS_URL` se čita jednom, na import-u. Promena `REDIS_URL` posle importa je nevidljiva. Nije bug, ali je zamka — i bio je razlog zašto je stari test morao na `reload`. |
| **D3** | `pg_ctl start` preda nasleđene pipe-ove dugoživećem `postgres` procesu, pa se `subprocess.run(capture_output=True)` **zaglavi zauvek**. Zaobiđeno u `scripts/test_db.py`; ako neki drugi skript u repou radi isto, ima istu bombu. |
| **D4** | `tests/test_sec005_rate_limiting.py::TestApiPyUsesRealIp` — preostala dva testa su i dalje source-position. `"verify_token_local" in api_src` dokazuje samo da tekst postoji, ne da se koristi. |
| **D5** | `tests/test_wave9_strategy_context.py::_okruzenje` i dalje gasi limiter preko `enabled = False` umesto da resetuje brojače. Sada kad `reset_limiter_state()` postoji, moglo bi se pojednostaviti. |

---

# FINAL GATE

```
CLOSED:
  production DB write protection     ZATVORENO   (konfiguracija + kapija + DNS klasa)
  test DB bootstrap                  ZATVORENO   (scripts/test_db.py, 7 kriterijuma)
  append-only production isolation   ZATVORENO   (konekcija pada pre write-a)
  rate limiter state isolation       ZATVORENO   (1 instanca, reset po testu)

VERIFIED:
  targeted tests        71 passed
  mutation tests         5 / 5 diskriminišu
  115-test differential 455 passed / 0 failed
  full regression      4643 passed / 1 skipped / 0 failed

OWNER BLOCKED:  nijedna stavka iz opsega
WORKTREE:       CLEAN
HEAD:           e2dadc55
```

## 🟢 **GREEN**

Sva četiri uslova iz mandata su ispunjena, i to merenjem a ne tvrdnjom:

1. nijedan test ne može pisati u produkcionu bazu — kredencijali ne ulaze u proces;
2. nijedan test ne ostavlja trajni zapis u append-only tabelama — jedini koji je to
   radio je pronađen, imenovan i popravljen;
3. suite eksplicitno odbija produkcionu konfiguraciju — dokazano podprocesom, sa
   negativnom kontrolom da ne odbija sve;
4. rate-limiter state je izolovan — jedna instanca, reset pre i posle svakog testa.

Wave 9 je ovaj nalaz ostavio kao **„sadržano, ne zatvoreno"**. Sada je zatvoreno,
i to na sloju na kome je i nastao.

# Test DB Bootstrap — kanonska procedura

Jedini podržani put do test PostgreSQL klastera. Sve ostalo (ručni `initdb`,
pasus u `P0_CLOSURE_LEDGER.md`) je istorija — koristiti `scripts/test_db.py`.

Alat: `scripts/test_db.py`
Testovi alata: `tests/test_wave10_test_db_bootstrap.py`

---

## Zašto ovo postoji — pročitati pre svega ostalog

Oko **59 testova naplatnog sloja** izvršavaju migracije **doslovno** nad pravim
PostgreSQL-om, umesto da mockuju bazu:

| Fajl | Šta dokazuje |
|---|---|
| `tests/test_beta_gate_credit_race_postgres.py` | migracija 107 — trka za kredite |
| `tests/test_atomic_usage_counters_postgres.py` | migracija 108 — atomični brojači |
| `tests/test_wave9_migration_111.py` | migracija 111 — fantomske AI naplate |
| `tests/test_wave9_billing_invariant.py` | invarijanta naplate |

Svi imaju `pytest.mark.skipif` na „nema dostupnog PostgreSQL servera".

**Ako klaster ne radi, oni se TIHO PRESKAČU.** Suite prijavi zeleno, izlazni kod
je 0, nijedna linija nije crvena — a najvredniji dokazi o naplati te noći nisu
izvršeni. Zato je gašenje klastera opasnije od pada testa: pad se vidi,
preskakanje se ne vidi.

Klasteri žive u `%TEMP%` i **ne preživljavaju restart mašine.**

**Kontrola pre svakog ozbiljnog pokretanja: `0 skipped` na ta četiri fajla.**

---

## Četiri koraka

### 1. Startuj test DB

```powershell
python scripts/test_db.py up
```

Podiže klastere na **55432** i **55433** (`%TEMP%\vindex_pg_<port>`).
Idempotentno: nad već pokrenutim klasterom ne radi ništa i ne dira podatke.
Prvi put traje ~7 s po klasteru (`initdb`), posle toga ~1 s.

`initdb` **odbija da radi iz elevirane (Administrator) sesije** — koristiti
običan, ne-elevirani terminal.

### 2. Proveri da je to test DB

```powershell
python scripts/test_db.py verify
```

Izlazni kod **0** = dokazano testna. **Bilo šta drugo = ne pokretati suite.**
Za pregled stanja bez tvrdnje:

```powershell
python scripts/test_db.py status
```

### 3. Pokreni suite

```powershell
python -m pytest -q -p no:randomly `
  tests/test_beta_gate_credit_race_postgres.py `
  tests/test_atomic_usage_counters_postgres.py `
  tests/test_wave9_migration_111.py `
  tests/test_wave9_billing_invariant.py
```

Očekivano: **0 skipped**. Ako vidiš `skipped`, klaster nije podignut — vrati se
na korak 1. Ne nastavljati dalje sa „pa zeleno je".

**NE postavljati `VINDEX_TEST_PG_DSN`.** Auto-otkrivanje koristi keyword formu
DSN-a i time zaobilazi poznat problem `P0E-001`.

### 4. Ugasi test DB

```powershell
python scripts/test_db.py down
```

Klaster ostaje na disku i sledeći `up` ga samo pokrene (bez `initdb`, bez
gubitka podataka). Za potpuno brisanje:

```powershell
python scripts/test_db.py down --purge
```

---

## Kako se proverava da je baza testna

`verify` je **fail-closed**: ako ne može da *dokaže* testnost, izlazni kod je
različit od nule. Nema „verovatno je testna".

Redosled je bitan — **statičke provere (K1–K3) idu PRE povezivanja**, pa skript
nikad ne otvori konekciju ka nečemu što nije dokazano lokalno.

| # | Kriterijum | Zašto |
|---|---|---|
| **K1** | host je `127.0.0.1` / `localhost` / `::1`, i **mora biti eksplicitan** | Produkcija je udaljeni Supabase host. Izostavljen host bi libpq popunio pretpostavkom — pretpostavka nije dokaz. |
| **K2** | port je 55432 / 55433 / 55434 (ili `$VINDEX_TEST_PG_PORTS`) | **5432 je namerno odbijen**: na razvojnoj mašini je to trajni servis sa stvarnim podacima. Loopback ne znači throwaway. |
| **K3** | ime baze je `postgres` ili `vindex_*` | Isključuje očigledno pogrešne mete. Sam po sebi slab (i Supabase baza se zove `postgres`) — nosivi dokaz daju K4–K7. |
| **K4** | server potvrđuje `inet_server_addr()` = loopback | Ne veruje se tekstu DSN-a, nego serveru. |
| **K5** | stvarni port servera je testni | Isto — server, ne DSN. |
| **K6** | `data_directory` je u sistemskom temp-u | Najjači pojedinačni marker: throwaway klaster po definiciji živi u temp-u. Na produkciji uloga **nije superuser**, upit pukne → fail-closed. |
| **K7** | nema Supabase šema (`auth`, `storage`, `realtime`, `vault`, …) ni uloga (`supabase_admin`, `authenticator`, …) | Hvata i slučaj kad je produkcija tunelovana na 127.0.0.1 i K1–K5 prođu. |

Zašto K4–K7 uopšte postoje kad K1–K3 gledaju host: **SSH tunel može izložiti
produkciju na `127.0.0.1:55432`.** Tada DSN izgleda savršeno testno. K4–K7 pitaju
sam server šta je.

`anon`, `authenticated` i `service_role` **nisu** markeri produkcije — postojeći
testovi ih sami kreiraju na test klasteru
(`test_beta_gate_credit_race_postgres.py:111`), pa bi davali lažno pozitivan
rezultat, i to odloženo u vremenu.

Skript **nikad** ne ispisuje lozinku ni pun connection string — ni u uspehu, ni u
grešci, ni u tekstu izuzetka iz drajvera.

---

## Posle restarta mašine

Klasteri su u `%TEMP%` i Windows ih ne pokreće sam. Data direktorijumi obično
prežive restart, ali `%TEMP%` ume da bude očišćen.

```powershell
python scripts/test_db.py status   # skoro sigurno: NE RADI
python scripts/test_db.py up       # ako dir postoji -> samo start; ako ne -> initdb
python scripts/test_db.py verify
```

`up` sam odlučuje da li treba `initdb`, pa je ista komanda ispravna u oba
slučaja.

---

## UPOZORENJE — nikad ne uperiti suite u produkcionu bazu

- **Nikad** ne postavljati `VINDEX_TEST_PG_DSN` na produkcioni DSN. Testovi
  prave i **brišu** baze i tabele.
- **Nikad** ne dodavati produkcioni port u `$VINDEX_TEST_PG_PORTS` da bi `verify`
  „prošao". Ako `verify` odbija — meta je pogrešna, ne kriterijum.
- **Nikad** ne pokretati suite ako `verify` vrati kod različit od nule.
- Ne popravljati crveni `verify` popuštanjem kriterijuma. Fail-closed kapija
  koja se relaksira dok ne prođe nije kapija.

---

## Izolacija od paralelnog rada

Portovi **55432** i **55433** su deljeni — koriste ih testovi naplate i paralelni
agenti. `down` bez `--port` gasi baš njih, pa ga ne pokretati dok neko drugi radi
regresiju.

Port **55434** je rezervisan za `tests/test_wave10_test_db_bootstrap.py`, koji
sam podiže i gasi svoj klaster i deljene nikad ne dira. Dve provere to i
dokazuju (`test_teardown_ne_moze_da_gasi_deljene_klastere`,
`test_deljeni_klasteri_i_dalje_rade`), umesto da se oslanjaju na disciplinu.

---

## Okruženje

| Stavka | Vrednost na ovoj mašini |
|---|---|
| PostgreSQL | **17.9**, `C:\Program Files\PostgreSQL\17\bin` |
| Data dir | `%TEMP%\vindex_pg_<port>` — **nikad u repou** |
| Log | `%TEMP%\vindex_pg_<port>.log` |
| Autentikacija | `--auth=trust` |
| Drajver | `psycopg` 3.x |

`--auth=trust` je prihvatljiv **isključivo** zato što klaster sluša na
`-h 127.0.0.1`: bez lozinke, ali i bez ijednog mrežnog puta do servera. Da
klaster sluša na `0.0.0.0`, `--auth=trust` bi bio neprihvatljiv i `verify` bi ga
morao odbiti (K4).

Alati se traže redom: `$VINDEX_PG_BIN` → `PATH` → `C:\Program Files\PostgreSQL\*\bin`
(najviša verzija). Ako nisu nađeni: jasna poruka i **izlazni kod 2**, bez trace-a.

### Izlazni kodovi

| Kod | Značenje |
|---|---|
| 0 | uspeh / dokazano testna |
| 1 | operacija ili verifikacija nije uspela |
| 2 | `initdb`/`pg_ctl` nisu pronađeni |
| 3 | `psycopg` nije instaliran → testnost se ne može dokazati → fail-closed |

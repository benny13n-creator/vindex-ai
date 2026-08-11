# P0 CLOSURE LEDGER — noćna misija 2026-08-10/11

Prati zatvaranje P0 stavki iz `BETA_TRUTH_MATRIX.md`. Matrica je snimak i **ne prepravlja se**;
napredak živi ovde.

Stanja se **ne sabijaju**: `IMPLEMENTED` ≠ `TESTED` ≠ `VERIFIED` ≠ `CLOSED`.

| | P0 | IMPL | TEST | VERIF | Stanje |
|---|---|---|---|---|---|
| **A** | Identitet build-a | ✔ | ✔ 20 | ✖ | **PRODUCTION VERIFICATION PENDING OWNER** |
| **B** | Mrtav onboarding | ✔ | ✔ 10 | ✖ | **IMPLEMENTED + TESTED** (nema browser QA) |
| **C** | Naplata bez AI poziva | ✔ kod | ✔ 11 | ✖ | **MIGRATION PENDING OWNER** (111) |
| **D** | Integritet konteksta predmeta | ✔ | ✔ 33+40 | ✔ adversarijalno | **CLOSED (kod)** — v. dole |
| **E** | Provera naplatnog sloja nad bazom | ✔ | ✔ **59** | ✔ | **CLOSED (kod)** / produkcija: 108 telo neprovereno |
| **F** | Javni cenovnik | ✔ | n/a | ✔ | **CLOSED** |
| **§9** | Voice van beta površine | ✔ | ✔ 6 | ✖ | **MIGRATION PENDING OWNER** (112 nije pisana — v. dole) |

Testovi: **4007 passed, 1 skipped, 0 failed** (bilo 3893 / 60 skipped).

---

## P0-E — jedini potpuno zatvoren, i najveće iznenađenje noći

**59 testova naplatnog sloja se prvi put izvršilo.** Nije trebao ni `SUPABASE_DB_URL`, ni Docker,
ni lozinka postojećeg Postgres servera. Mašina već ima `initdb.exe`, pa se pravi jednokratni
klaster koji testovi **sami pronađu** — oni probaju `127.0.0.1:55432` i `:55433` kao fallback
(`tests/test_beta_gate_credit_race_postgres.py:64-92`).

Blokada nije bila tehnička nego dokumentaciona: `test_beta_gate_credit_race_postgres.py:35`
upućuje na „setup u closure report-u", a taj dokument setup ne sadrži. Zato ovo ovde stoji.

### Procedura (ne-elevirani PowerShell — `initdb` odbija Administrator sesiju)

```powershell
$PGBIN = "C:\Program Files\PostgreSQL\17\bin"
$A = "$env:TEMP\vindex_pg_55432"; $B = "$env:TEMP\vindex_pg_55433"

& "$PGBIN\initdb.exe" -D $A -U postgres --auth=trust --encoding=UTF8
& "$PGBIN\initdb.exe" -D $B -U postgres --auth=trust --encoding=UTF8
& "$PGBIN\pg_ctl.exe" -D $A -o "-p 55432 -h 127.0.0.1" -l "$env:TEMP\pg_a.log" start
& "$PGBIN\pg_ctl.exe" -D $B -o "-p 55433 -h 127.0.0.1" -l "$env:TEMP\pg_b.log" start

pytest tests/test_beta_gate_credit_race_postgres.py tests/test_atomic_usage_counters_postgres.py -q

& "$PGBIN\pg_ctl.exe" -D $A -m immediate stop
& "$PGBIN\pg_ctl.exe" -D $B -m immediate stop
Remove-Item -Recurse -Force $A, $B
```

**NE postavljati `VINDEX_TEST_PG_DSN`.** Auto-discovery koristi keyword formu DSN-a i time
zaobilazi `P0E-001` (dole). Kontrola pre pokretanja: mora biti `59 collected, 0 skipped`.

### Zašto je ovo bezbedno

Testovi prave sopstvenu bazu `vindex_creditrace_<uuid>` / `vindex_counters_<uuid>`, kreiraju
svoje tabele, i brišu je na kraju. Nula `TRUNCATE`, nula `DELETE`. Ništa se ne povezuje na
Supabase. `tests/conftest.py:86-138` uz to blokira DNS ka svim naplativim hostovima.

### Šta je time DOKAZANO

Telo migracija 107 i 108 se izvršava nad pravim PostgreSQL-om: atomični odbitak sa balance
guardom, 5 konkurentnih scenarija, refund/deduct interleaving, ACL, mesečna kvota, i
**negativna kontrola koja dokazuje da staro telo STVARNO probija bilans**. Do sada su ostali
kreditni testovi mock-ovali RPC — validirali su ugovor koji kod OČEKUJE, ne onaj koji baza NUDI.
To je tačno ista slepa tačka koja je pustila ranjivo telo `deduct_n_credits` u produkciju uz
zeleni CI.

### Šta NIJE dokazano

Da produkciona baza ima to telo. Migracija 107 je verifikovana katalogom 2026-08-08; telo 108
ostaje `UNVERIFIED — REQUIRES DB`.

---

## Otvoreni nalazi iz P0-E

| # | Nalaz | Gde |
|---|---|---|
| **P0E-001** | `target = admin.replace("dbname=postgres", ...)` — string replace. Sa URL-formom DSN-a tiho ne uradi ništa i cela test šema se izvrši u ADMIN bazi. Isti bug je već nađen i popravljen u `test_atomic_usage_counters_postgres.py:85-94` (`conninfo_to_dict` + `assert`), ali ispravka nije preneta | `tests/test_beta_gate_credit_race_postgres.py:117` |
| **P0E-002** | Referenca na setup koji ne postoji — zbog toga je 59 testova bilo nepokretljivo iako je mašina imala sve potrebno. **Zatvoreno ovim dokumentom** | `tests/…:35` |
| **P0E-003** | `psycopg` je instaliran ali nije u `requirements.txt` | — |
| **P0E-004** | `.github/workflows/tests.yml` nema `services: postgres`, pa CI ovih 59 nikad ne izvršava. Sada je dokazano da je dovoljan **prazan** Postgres — uključivanje je jeftino | — |

---

## P0-D — ZATVOREN 2026-08-11 (`0bb847be`, `d35497ba`)

> **Status ažuriran.** Odeljak ispod je zadržan kao zapis onoga što je bilo utvrđeno pre
> implementacije — mapa je bila tačna i implementacija ju je pratila bez odstupanja.
>
> **Šta je urađeno:** `predmet_id` je uveden kao opcion na `/kompletna-analiza`; kanonski
> kontekst se gradi u ruti preko `build_case_context(..., include_documents=True)` i prosleđuje
> orkestratoru kao **keyword-only** `case_context_blok`; `if/else` na `:666,676` zamenjen je
> jednom dokaznom osnovom koju vidi **svih 8 GPT poziva**. Vlasništvo se proverava **sinhrono u
> ruti, pre kreiranja posla** (gate-first, po `matter_intel.py:514-521`).
>
> **Adversarijalno dokazano:** svaka od 5 namernih mutacija (gubitak opisa, gubitak kanonskog
> konteksta, nizvodni korak vraćen na samo-opis, pozicioni peti parametar, uklonjena kapija)
> obara tačno očekivane testove. Sve vraćeno, 4072 passed / 1 skipped / 0 failed.
>
> **Greška uhvaćena u sopstvenom radu:** `replace_all` je pogodio i `ai_judge_v2_sync` (druga
> funkcija, bez `_osnova`) — `NameError` na živoj putanji AI Sudije. `py_compile` to ne vidi.
> Zatvoreno testom koji vrti `pyflakes` F821 nad tri modula.
>
> **Kontaminacija promptova** (`d35497ba`): preostala 3 prompta očišćena; `_ORK_PRESUDA_SYSTEM`
> uopšte nije imao anti-halucinacioni blok — dodat. Detektor prebačen sa nedovršive liste
> skraćenica (propuštala `ZOO`, 6 pojava, i `ZR ` sa razmakom) na regex koji traži **broj**.
>
> **Ostaje otvoreno:** ostalih 8 strategija endpointa i dalje nema `predmet_id` (samo
> `/kompletna-analiza` je migriran); frontend još ne šalje `predmet_id` — polje je spremno,
> UI wiring je zaseban zadatak.

### Zapis stanja pre implementacije

### Šta je dokazano

`static/vindex.js:3590` šalje samo `opis_predmeta`. Ali problem je dublji od jednog polja:

- `dokumenti` i `iskazi_svedoka` su **mrtvi na celom putu** — 0 frontend pošiljalaca, 0 testova,
  0 produkcionih poziva. Grane `strategija.py:666,676,686` nikad ne izvršavaju „ima dokumenata"
  varijantu.
- **Frontend fizički NE POSEDUJE tekst dokumenata.** `api.py:5611` (workspace endpoint) ne
  selektuje `tekst_sadrzaj`. Jedini endpoint koji ga vraća je per-dokument sa rate limitom
  20/min.
- `strategija.py:666,676` su **ekskluzivni `if/else`** — kad dokumenti postoje, `opis_predmeta`
  se odbacuje. Nijedan korak u lancu nikada ne vidi i opis i dokumente.
- Dodatan, nezavisan gubitak: `strategija.py:779-782` ne upisuje `tuzilac_txt`/`branilac_txt` u
  `kontekst`, pa Sinteza ne vidi dva puna GPT odgovora koje je sistem već platio.

### Kanonski put postoji i dokazan je prebrojavanjem

`shared/case_context.py::build_case_context(predmet_id, uid, supa, include_documents=True)` **već
vraća stvarni tekst dokumenata** u `relevant_documents.value.included[].excerpt` (do 15 dok ×
1500 znakova), i **već postoje 4 serijalizatora** koji ga pretvaraju u blok za prompt
(`court_predictor.py:195`, `hearing_cc.py:246`, `digital_twin.py:221`, `case_intelligence.py:234`).

| obrazac | broj modula |
|---|---|
| `predmet_id` → backend dovlači kontekst | **8** |
| tekst dokumenata kroz payload | **1** (`cross_doc`) |
| strategija endpointi sa `predmet_id` | **0 od 9** |

`routers/court_predictor.py` je **presedan migracije istog oblika**: modul koji je bio „nalepi
opis", dobio je `Optional[predmet_id]` (`:106`), fail-soft wrapper (`:266`), ownership
verifikaciju (`:295`) i serijalizator (`:195`).

### Zamka koju sledeći mora znati

`routers/strategija.py:394-400` zove orkestrator **pozicijski**. Dodavanje parametra bilo gde
osim na kraj tiho pomera argumente — a poziv je u `asyncio.to_thread`, u background job-u sa
`except Exception` na nivou runnera, dakle **otkazalo bi tiho u produkciji**. Svih 13 test
poziva koristi keyword, pa testovi to NE bi uhvatili. Bezbedno: `*, novi_param=None` na kraju.

Uz to, `tests/test_celina4_tech_debt_2026_07_24.py:166` hardkoduje
`src.count("_pozovi_strategija_api(") == 12`, a svih 13 testova ima `side_effect` liste od
**tačno 7** odgovora. Svaka izmena broja GPT poziva obara ih sve.

### Negativna kontrola je već obezbeđena

Test koji tvrdi da `opis_predmeta` stiže u Korak 1 kad su prosleđeni `dokumenti` **pada danas**,
zbog `strategija.py:666`. Red-green ciklus postoji pre nego što se išta dirne.

---

## P0-D, deo A — kontaminacija promptova (odvojen nalaz)

Commit `790d6704` je očistio 2 prompta. Ostalo je **4**, i jedan je nov:

| prompt | linija | navod |
|---|---|---|
| `_ORK_DUE_DILIGENCE_SYSTEM` | `:483,485,496,497` | „čl. 16 Zakona o postupku upisa, Sl. gl. RS 41/2018", „čl. 454 ZOO" + *„To je tvoja stručnost, ne halucinacija"* |
| `_ORK_PRESUDA_SYSTEM` | `:558` | „čl. 18 st. 1 ZUSP", „čl. 9 ZUP" |
| **`_ORK_SYNTHESIS_SYSTEM`** | `:583` | **„ZR čl. 195" — NOV NALAZ** |
| van orkestratora | `:78,94,108,110,336` | `_RED_TEAM_*`, `_WITNESS_SYSTEM` |

**`test_e_witness_i_synthesis_ostaju_cisti` je lažno zeleno.** Token u `ZABRANJENI` je `'ZR"'`
(ZR + navodnik) i ne hvata `ZR čl. 195` (ZR + razmak). Regresioni pojas propušta baš ono što
treba da štiti.

Dva strukturna uzroka zašto se ZUP pojavio u privrednom sporu:
1. Orkestrator **nema `tip_postupka`** — za razliku od `_RED_TEAM_*` promptova koji su
   branch-scoped. Nema pojma o grani prava.
2. **Nigde u repou ne postoji provera da citiran član stvarno postoji.** `main.py::_proveri_halucinaciju`
   nije primenljiva: orkestrator nema `pinecone_context` (pa guard rano izlazi), a regex
   `[ČčCc]lan\s+(\d+)` ne hvata `čl. 205` — format koji promptovi **izričito nalažu**.

Nezavisan defekt: `[Opšti pravni princip]` — `:512` (Witness) ga **nalaže**, a `:463`, `:485`,
`:536` ga **zabranjuju**. Svih pet u istom akumuliranom kontekstu.

---

## Preostalo vlasniku

| # | Radnja | Otključava |
|---|---|---|
| 1 | Posle deploy-a: `GET /api/version` → uporediti `commit` sa `git rev-parse HEAD` | zatvara P0-A; tek tada je tvrdnja „kreditna trka je zatvorena" dokaziva |
| 2 | Pokrenuti `migrations/111_phantom_ai_charges.sql` | zatvara P0-C u produkciji |
| 3 | Odluka o voice-u za betu; ako da — `UPDATE feature_registry SET aktivno=false WHERE feature_key='voice'` | gasi netelemetrisan glasovni kanal; mehanizam je testiran (6 testova), migracija namerno nije pisana dok odluka ne padne |
| 4 | Potvrditi uklanjanje cenovnika ili `git revert 3381d59f` | P0-F je izvršen po dokumentovanoj nameri, ali je komercijalna odluka vaša |
| 5 | `SUPABASE_DB_URL` | telo migracije 108 u produkciji, integritet audit lanca |

# NS001-P0-001B — FINALNI FORENZIČKI IZVEŠTAJ

**Sprint:** NIGHT STABILIZATION 002B
**Baseline:** `a7c1ecd5` (potvrđen; worktree čist, sinhronizovan sa `origin/main`)
**Datum:** 2026-08-16

---

## VERDICT

# 🔴 RED

Kvar iz mandata je **dokazan na nivou koda i popravljen** — neuspeh pravnog dela
više ne briše potvrđenu činjenicu iz dokumenta. Ali NS001-P0-001B **se ne
zatvara**, iz dva razloga koja sam sebi nisam smeo da progledam kroz prste:

1. **Popravljeni put nije bio pređen u produkciji.** U 30 stvarnih E2E pokušaja
   guard **nijednom nije opalio**. 20/20 na kritičnom pitanju je tačno, ali ne
   dokazuje popravku — dokazuje da tih 20 pitanja nije ni stiglo do blokade.
2. **Ostao je pad bez ijedne blokade.** Jedan od 10 pokušaja kombinovanog
   pitanja nije vratio podatak iz dokumenta uz `blocked=False` — dakle postoji
   **treći mehanizam** koji ovaj sprint nije ni dodirnuo.

---

## ROOT CAUSE

Jedan bulean — „da li su PRAVNE reference proverljive" — odlučivao je o sudbini
**celog** odgovora, pa je uz neproverljivu pravnu referencu nestajala i činjenica
iz advokatovog dokumenta koju je retrieval već potvrdio.

---

## EXACT BREAKPOINT

```
main.py:_parsiraj_strukturni_odgovor:2899, 2933, 2951
        → return False, _format_halucination_block(razlog)
main.py:_format_halucination_block:2449
        → tekst koji ZAMENJUJE ceo odgovor
main.py:ask_agent:~3540 (MEDIUM), ~3620 (HIGH)
        → if not _json_ok: return {"blocked": True, "data": <ta poruka>}
```

`docs` je već bio parametar `_parsiraj_strukturni_odgovor` — pasusi dokumenta su
bili nadohvat ruke i nisu korišćeni.

---

## CHARACTERIZATION — PRE → POSLE

Baseline, pravi model / prava baza / pravi Pinecone, dokument sa dve jedinstvene
činjenice (**17.350 EUR**, **13 dana**):

| Scenario | Pre |
|---|---|
| A — samo dokument (FACT-A) | 5/5 |
| B — samo dokument (FACT-B) | 5/5 |
| C — FACT-A + pravna analiza | **4/5** |
| D — FACT-B + pravna analiza | 5/5 |
| E — dva podatka + pravna analiza | 5/5 |
| F — činjenica + nepotkrepljeno pravno pitanje | 5/5 |
| **ukupno** | **29/30** |

Deterministički (bez modela), na nivou funkcije:

| | Pre | Posle |
|---|---|---|
| blokiran odgovor sadrži činjenicu iz dokumenta | **NE** | **DA** |
| blokiran odgovor sadrži nepotvrđen član zakona | NE | **NE** (nepromenjeno) |
| bez pasusa dokumenta — izlaz | canned tekst | **identičan** |

---

## PRODUCTION FIX

`main.py` — dve funkcije, jedan poziv provučen:

- **`_dokumentarni_citat(docs)`** (novo) — izdvaja pasuse čiji header počinje
  `KORISNIKOV DOKUMENT`, ograničeno na 1200 znakova.
- **`_format_halucination_block(razlog, docs=None)`** — kad takvih pasusa ima,
  prilaže ih doslovno u sekciji `--- IZ VAŠEG DOKUMENTA (doslovan citat,
  potvrđen izvor)` i pravni deo izričito označava kao blokiran. Kad ih nema,
  izlaz je **bajt-identičan** ranijem.
- `_parsiraj_strukturni_odgovor` prosleđuje svoj postojeći `docs` na sva tri
  mesta blokade.

### WHY THIS FIX

**Zašto ovaj sloj:** to je jedina funkcija koja proizvodi zamenski tekst pri
blokadi. Sve tri putanje blokade prolaze kroz nju, pa je ovo jedina tačka na
kojoj se ponašanje menja jednom, a ne na tri mesta.

**Zašto se citira dokument, a ne rečenica modela:** blokada postoji zato što se
rečenici modela ne veruje. Zato se ne propušta ništa što je model napisao —
prilaže se pasus iz retrieval-a, podatak koji je već proveren. Halucinacija ovim
putem nije moguća.

**Šta nije oslabljeno:** nijedan neproveren član zakona i dalje ne izlazi
(`test_2c`, `test_4b`). Bez pasusa dokumenta ponašanje je nepromenjeno
(`test_2`, `test_2b`, `test_4c`) — fail-closed za nepostojeću činjenicu ostaje.

---

## SOURCE SEPARATION

| | Status |
|---|---|
| document fact | citira se doslovno iz retrieval pasusa, sa imenom fajla i chunk-om |
| legal analysis | blokira se nepromenjeno; izričito označeno kao neproverljivo |
| combined answer | dva odvojena bloka, bez mešanja |

Pokriveni slučajevi iz mandata: CASE 1 (nepromenjen), **CASE 2 (zatvoren)**,
CASE 3/4 (nepromenjeni, fail-closed), CASE 5 (dokument se citira doslovno,
ne pretvara se u izvedenu tvrdnju).

---

## E2E

| Test | Pokušaja | PASS | Blokada opalila | Verdikt |
|---|---|---|---|---|
| Kritično pitanje (mandat §9) | 20 | **20** | **0** | PASS, ali ne dokazuje popravku |
| Kombinovano (oblik iz NS002 J) | 10 | 9 | **0** | **FAIL** |

**Ovo je najvažniji red izveštaja:** u 30 stvarnih pokušaja blokada nije opalila
nijednom, pa popravljena grana u produkciji **nije pređena**. 20/20 je ispunilo
slovo kriterijuma, ali ne i njegovu svrhu.

---

## ADVERSARIAL

| Test | Ishod |
|---|---|
| A — zakon nudi drugi iznos, dokument 17.350 | PASS (`test_5`) — zakonski broj se ne pojavljuje |
| B — dokument 13 dana vs zakonski rok | PASS — zakonski pasusi se nikad ne propuštaju (`test_2c`) |
| C — dokument nema podatak, zakon ima generički | PASS (`test_2`, `test_4c`) — ništa se ne izmišlja |
| D — dva različita iznosa u dokumentima | PASS (`test_5b`) — oba se navode, nema proizvoljnog izbora |
| E — pitanje gura model da ignoriše dokument | PASS (`test_5c`) — labela izvora ostaje u citatu |

---

## MUTATION

**5/5 ubijeno.**

| Mutacija | Ishod |
|---|---|
| uklonjen prioritet dokumentarne činjenice | 10 testova pada |
| uklonjeno razdvajanje dokument/zakon | 4 pada |
| generički fallback umesto fail-closed | 2 pada |
| uklonjena atribucija izvora | 1 pada |
| guard više ne prosleđuje `docs` | 1 pada |

---

## REGRESSION

| | Baseline | Posle |
|---|---|---|
| passed | 5672 | **5688** |
| failed | 0 | 2 u međuprolazu → **0** u završnom |
| skipped | 1 | 2 |

Dva pada u međuprolazu:

1. `test_ns002_document_fact_authority::test_2_KVAR_...` — **karakterizacioni
   test koji je odradio svoj posao**: tvrdio je kvar i imao izričitu uputu da
   mora pasti kad se blocker zatvori. Prepisan uz OLD/NEW/WHY; bezbednosna
   tvrdnja (blokada pravnog dela ostaje) je zadržana i pojačana.
2. `test_get_supa_thread_safe_single_client_created` — poznat flake
   (`BR001-FLAKE-001`), samostalno prolazi.

Nijedan test nije obrisan, nijedan security assertion oslabljen.

---

## FALSE-GREEN ATTACK

1. **„20/20 dokazuje popravku."** **NE.** Guard nije opalio nijednom u tih 20
   pokušaja — popravljena grana nije pređena. Zato je verdikt RED, ne GREEN.
2. **„Model zna 17.350 iz memorije."** Iznos je izmišljen, uz marker
   `VX-2B-4471` koji ne postoji nigde van testnog dokumenta.
3. **„Test prolazi i bez retrieval-a."** `test_4` vozi pravi
   `_parsiraj_strukturni_odgovor` sa `docs` iz retrieval-a; bez pasusa dokumenta
   (`test_4c`) izlaz nema citat.
4. **„Provenance može biti lažan."** Citira se header pasusa iz retrieval-a
   (ime fajla + chunk), ne tvrdnja modela. `test_5c` drži labelu ranijeg predmeta.
5. **„Legal fallback bi generisao isti broj."** `test_5` ubacuje zakonski pasus
   sa drugim iznosom (5.000 EUR) — u izlazu ostaje samo dokumentov.
6. **„Test proverava samo substring."** `test_1b` traži doslovnu rečenicu,
   `test_1c` proverava atribuciju, `test_2c` proverava odsustvo zakonskog teksta.
7. **„Postoji drugi izvršni put guard-a."** Sva tri `_format_halucination_block`
   poziva su provučena; `test_4` meri put kroz pravu funkciju.

---

## DATA CLEANUP

| | Pre sprinta | Posle |
|---|---|---|
| Pinecone total | 434.217 | **434.217** |
| Pinecone namespace-ova | 11 | **11** |
| `predmeti` | 19 | **19** |
| `klijenti` | 5 | **5** |
| `predmet_dokumenti` | 43 | **43** |

Testni nalog obrisan; Pinecone proveravan u petlji do odsustva namespace-a.

---

## REMAINING BLOCKERS

- **NS001-P0-001B — OTVOREN.** Popravljena grana nije verifikovana u produkciji
  (blokada nije opalila u 30 pokušaja).
- **NS002B-OPEN-001 — NOV.** Kombinovano pitanje pada 1/10 **bez ijedne
  blokade** (`blocked=False`). Postoji treći mehanizam gubitka dokumentarne
  činjenice, u samoj sintezi, koji ovaj sprint nije istražio.
- **NS002-MEH-1 — i dalje otvoren.** DOC GATE zaključan iza `extra_namespaces`;
  u NS002 je dokazano da ga nije bezbedno otvoriti samostalno.

---

## CERTIFICATION

**NS001-P0-001B NIJE ZATVOREN.**

Vindex Beta ostaje **NO-GO**. Ovaj sprint nije menjao status ostalih tokova.

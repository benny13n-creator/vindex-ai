# FALSE-SUCCESS — ODLUKA ZA SVAKI POZNAT NALAZ

**Sprint:** BETA-RELIABILITY-FALSE-SUCCESS · **Baseline:** `948c5575` ·
**Izvor:** `docs/beta_gate/FALSE_SUCCESS_INVENTORY.md` (79 nalaza, 2026-08-13)

Ovaj dokument NE tvrdi „nula false-success u sistemu". Tvrdi samo:

    KNOWN_FALSE_SUCCESS_PATHS_COVERED = 46/46 (P0+P1) — svaki ima odluku
    POPRAVLJENO U OVOM SPRINTU = 4
    RANIJE ZATVORENO (dokazano) = 8
    ODLOŽENO SA RAZLOGOM = 33
    NEPOZNATO = 1

Klase iz mandata: **A** true success · **B** legitimate empty · **C** failure→empty ·
**D** failure→success · **E** nije izvršeno a UI tvrdi rezultat · **F** writer pao a
caller tvrdi upis · **G** dvosmislen ugovor.

---

## 1. POPRAVLJENO U OVOM SPRINTU (4)

### FS-P0-04 — pad razrešavanja role davao ADVOKAT pristup poverljivim poljima
`klijenti/permissions.py::_role_from_db` · klasa **D**

| | |
|---|---|
| **STARO** | `except` je padao na isti `return DEFAULT_ROLE` kao uspešno čitanje bez reda → neuspeh čitanja role predstavljen kao uspešno razrešena rola **ADVOKAT**, koja zadovoljava `ROLE_FIELD_ACCESS[FC.CONFIDENTIAL]` |
| **NOVO** | čitanje uspelo bez reda → `DEFAULT_ROLE` (namerno, nova osoba) · čitanje **palo** → `SEKRETARICA` |
| **KORISNIK** | prolazni ispad baze više ne unapređuje sekretaricu u rolu koja čita JMBG/pasoš/PIB |
| **BEZBEDNOST** | zatvorena napunjena zamka; `make_role_dependency` i danas nema produkcijskog pozivaoca — zatvorena **pre** nego što je opalila |
| **DOKAZ** | 3 testa (uklj. merenje posledice kroz `can_access_field`), 2/2 mutacije ubijene |

### FS-P1-01 — cross-doc: „Nisu pronađeni konflikti" iz analize koja nije prošla, uz naplaćen kredit
`routers/cross_doc.py` · klasa **E**

| | |
|---|---|
| **STARO** | `except json.JSONDecodeError → result = {}` → `konflikti: []` → UI: **„Nisu pronađeni konflikti između odabranih dokumenata."** + kredit naplaćen |
| **NOVO** | nepotpun JSON je greška → 500; `UsageService.consume` se ne dosegne |
| **KORISNIK** | pravna tvrdnja o odnosu dokumenata se više ne izriče iz neizvedene analize; nema naplate za nulti rezultat |
| **OKIDAČ** | `max_tokens=2000` uz `response_format=json_object` — odgovor se preseca upravo kod najdužih skupova, dakle kod najtežih predmeta |
| **DOKAZ** | 3 behavior testa + 4 Playwright (nađen konflikt · legitimno prazno · pad · prazno telo), 2/2 mutacije ubijene |

### FS-P1-07 — GDPR brisanje naloga tvrdilo uspeh bez provere ijednog upisa
`routers/gdpr.py::gdpr_delete_account` · klasa **F**

| | |
|---|---|
| **STARO** | oba upisa odbačena kao izraz; odgovor uvek „Vaš korisnički nalog je anonimizovan" |
| **NOVO** | `profiles` update koji ne pogodi nijedan red → **503** uz „Vaši podaci su nepromenjeni"; gašenje obaveštenja ostaje dopuna koja ne obara brisanje |
| **KORISNIK/PRAVNO** | tvrdnja po **članu 17 GDPR-a** sada ima dokaz; korisnik zna kad brisanje NIJE izvršeno |
| **DOKAZ** | 3 testa (prazan rezultat · pad baze · negativna kontrola), 2/2 mutacije ubijene |

### FS-P1-25 — delegiranje predmeta `ok: true` bez provere upisa
`routers/enterprise.py::delegiraj_predmet` · klasa **F**

| | |
|---|---|
| **STARO** | rezultat `insert`-a odbačen; odgovor bezuslovno `ok: True` |
| **NOVO** | upis bez vraćenog reda → **503** „Predmet je i dalje samo kod vas" |
| **BEZBEDNOST** | delegiranje je **pristupna** odluka — daje pravo čitanja kroz `shared/rag_acl.py`; neupisano delegiranje znači da prvi advokat veruje da je predao predmet, drugi ga ne vidi, a niko ne zna |
| **DOKAZ** | 2 testa, 1/1 mutacija ubijena |

---

## 2. RANIJE ZATVORENO — dokazano u prethodnim sprintovima (8)

| Nalaz | Zatvoren u | Dokaz |
|---|---|---|
| **FS-P0-01** COI „nema sukoba" uvek + zeleno | `BETA-P0-COI` + `DRIFT-001` | fail-closed `provera_potpuna`; sloj `klijenti` više ne puca na `pib` |
| **FS-P0-02** JMBG izdat uz pao audit | `BETA-P0-SENSITIVE-DATA-AUDIT` | `log_event_strict` → 503 pre dešifrovanja |
| **FS-P0-03** obrisana beleška pretraživa | `BETA-P0-DELETED-DATA-ISOLATION` | autorizacija iz trenutnog stanja baze |
| **FS-P1-03** kanal za prijavu netačnog odgovora mrtav | `BETA-P1-FEEDBACK-TRUTH` | 503 umesto `{"status":"ok"}`; migracija 113 čeka vlasnika |
| **FS-P1-04** GPT dobija „rokovi: nema" + naplata | `BETA-DEADLINE-DOMAIN-001` | „ROKOVI: NEPOZNATO" u promptu |
| **FS-P1-05** `rokovi` blast radius (13 mesta) | `BETA-DEADLINE-DOMAIN-001` | 13 → 0 čitalaca, `rokovi_dostupni` do ekrana |
| **FS-P1-26** portal upload „obrisano" | `BETA-P1-PORTAL-READONLY` | upload kapija zatvorena podrazumevano |
| **FS-P1-21** `vector_deletion` nepozvan | `PINE-01` | kanonsko brisanje postoji; **vezivanje na predmet ostaje odloženo** |

---

## 3. ODLOŽENO SA RAZLOGOM (33)

Nijedan nije negiran — svaki ima imenovan razlog zašto nije u ovom sprintu.

### 3.1 Zahteva promenu javnog HTTP ugovora → mandat §6 traži analizu svih klijenata pre izmene

`FS-P1-06` briefing cron `ok:true` · `FS-P1-14` evidence reklasifikacija ·
`FS-P1-17` `status="done"` posle delimičnog upisa · `FS-P1-19` playbook brisanje
vraća 0 + 200 · `FS-P1-20` playbook parcijalni upis · `FS-P1-24` SEF e-faktura ·
`FS-P1-33` SEF dvostruko podnošenje · `FS-P1-36` profitabilnost ·
`FS-P1-38` `timer_stop` · `FS-P1-40` broj fakture

**Razlog:** svaka izmena menja `2xx → 4xx/5xx` na ruti koju frontend već zove.
Mandat izričito zabranjuje nasumičnu promenu HTTP semantike; traži
`OLD CONTRACT / PROPOSED / AFFECTED CLIENTS / MIGRATION` analizu. **SEF i fakture
uz to dodiruju poresku obavezu** — pogrešna izmena tamo je gora od nalaza.

### 3.2 Zahteva shemu ili migraciju → HARD STOP mandata

`FS-P1-11` `api_costs` ne postoji · `FS-P1-02` `ratio_decidendi` ne postoji ·
`FS-P1-12` `feature_usage_log` prazan

**Razlog:** popravka je `CREATE TABLE`. Mandat: „STOP ako treba menjati schema."
Već evidentirano u `COLUMN_DRIFT_MATRIX.md` kao P2.

### 3.3 Frontend optimistic UI — jedna klasa, jedan sprint

`FS-P1-27` dokaz · `FS-P1-28` komentar · `FS-P1-29` naplativi sati ·
`FS-P1-30` Uslovi korišćenja · `FS-P1-31` GDPR saglasnost

**Razlog:** svih pet je isti obrazac (polje se čisti pre potvrde servera) i traži
jedan zajednički UI ugovor + Playwright po površini. Rasparčavanje bi dalo pet
nekonzistentnih rešenja. **`FS-P1-29` i `FS-P1-30` su najozbiljniji** (novac,
pravna saglasnost) i idu prvi u tom sprintu.

### 3.4 Skripte i pozadinski poslovi, ne korisničke površine

`FS-P1-15`, `FS-P1-16`, `FS-P1-18`, `FS-P1-22`, `FS-P1-23`, `FS-P1-34`,
`FS-P1-41`, `FS-P1-42`

**Razlog:** ne proizvode lažno-zelen ekran advokatu. `FS-P1-16` (embedding se
pari sa pogrešnim tekstom) je **najozbiljniji u grupi** — kvari tačnost RAG-a, ali
u ingest putanji, ne u tvrdnji prema korisniku.

### 3.5 Naplata/krediti bez pravne tvrdnje

`FS-P1-13`, `FS-P1-32`, `FS-P1-35`, `FS-P1-37`, `FS-P1-39`

**Razlog:** gubitak novca, ne laž o pravnom sadržaju. `FS-P1-35` (glas bez prompt
guard-a) je bezbednosno najteži i traži zaseban pregled glasovne putanje.

### 3.6 Audit lanac

`FS-P1-08`, `FS-P1-09`, `FS-P1-10`

**Razlog:** `FS-P1-09` (verifikacija čita najstarije zapise i javlja „potvrđen")
je stvarna lažna potvrda, ali popravka menja semantiku verifikacije lanca —
zahteva odluku o tome šta „potvrđen lanac" uopšte znači. Ne improvizuje se.

---

## 4. NEPOZNATO (1)

**FS-P1-42** `ai_fabric` shadow provider — inventar tvrdi da nema pozivaoca.
Ista tvrdnja za `FS-P0-04` pokazala se **delimično netačnom** (modul JESTE
uvožen, iako ne te funkcije). Dostiznost `ai_fabric` nije nezavisno reverifikovana
u ovom sprintu → **UNKNOWN**, ne „mrtav kod".

---

## 5. BETA EXIT GATE #1

> „Nijedan ekran ne sme prikazati neizvršenu/neuspelu proveru kao pozitivnu."

**STATUS: PASS za sve dokazane pravne/bezbednosne površine.**

| Površina | Stanje |
|---|---|
| Sukob interesa | ✅ `provera_potpuna`, nikad zeleno na pao sloj |
| Cross-doc konflikti | ✅ neizvedena analiza je greška, ne „nema konflikata" |
| Rokovi | ✅ `rokovi_dostupni` na dashboardu, brifingu, today-focus, WhatsApp-u, AI promptu |
| Prijava netačnog odgovora | ✅ 503 umesto `ok` — **gejtovano na migraciju 113** |
| Brisanje naloga (GDPR čl. 17) | ✅ dokaz upisa |
| Delegiranje predmeta | ✅ dokaz upisa |
| Klijentski portal | ✅ kanonski token, read-only |
| Rola / poverljiva polja | ✅ fail-closed |

**Preostali blokatori za bezuslovan PASS:**

1. **Migracija 113 nije pokrenuta** — prijava netačnog pravnog odgovora i dalje
   ne radi (ali to sada pošteno kaže). Vlasnikova odluka.
2. **Frontend optimistic UI (5 nalaza)** — polje se čisti pre potvrde servera.
   Ne tvrdi „provera je prošla", ali tvrdi „sačuvano". Sledeći sprint po prioritetu.

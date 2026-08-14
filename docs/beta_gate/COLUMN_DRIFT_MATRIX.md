# COLUMN DRIFT MATRIX — BETA-P1-COLUMN-DRIFT-007

**Baseline:** `b324b604` · **Režim:** READ-ONLY prema produkciji (nijedan DDL/DML;
sve tvrdnje „ne postoji" su `GET /rest/v1/…?select=<kolona>&limit=0` sonde koje su
vratile `400 / 42703`, odnosno `404 / PGRST205` za tabele).

**Izvor istine:** PostgREST OpenAPI koren — **167 objekata, 1.637 kolona, 16 RPC**.

**Metod (kod):** dubinski-svestan parser nad **825 fajlova** (`*.py`, `*.js`, `*.html`,
`*.ts`, `*.tsx`, `*.vue`) — **6.544 pristupna mesta**. Ugnježdeni PostgREST resursi
(`predmeti(naziv,status)`) pripisuju se **svojoj** tabeli, ne roditeljskoj; aliasi
(`alias:kolona`), kastovi (`::tip`) i JSON putanje (`meta->x`) se normalizuju.
Pretraga **nije** ograničena na `*.py` — ta greška je već jednom dala pogrešan
zaključak o `reported_errors`.

---

## 0. Rezime

| Mera | Broj |
|---|---|
| Referenci na **nepostojeće kolone** (runtime kod) | **163** |
| Korenskih uzroka (tabela + kolona) | **84** |
| Referenci na **nepostojeće tabele** | 123 |
| Jedinstvenih upita nad nepostojećim tabelama | **18** |
| Nepostojećih tabela | **5** (`rokovi`, `api_costs`, `ratio_decidendi`, `klijenti_dokumenti`, `user_activity_profile`) |
| Mesta gde greška **izlazi** (glasno) | 68 |
| Mesta gde je greška **progutana** (tiho) | **59** |

**163 reference ≠ 163 bugova.** Duplikati istog korenskog uzroka (npr.
`predmet_komentari.created_at` u 7 fajlova) broje se jednom.

---

## 1. Klasifikacija

| Klasa | Značenje | Broj korenskih uzroka |
|---|---|---|
| **E** — LIVE + OPASNO | neuspeh proizvodi lažno-pozitivan/negativan nalaz, tiho gubljenje podatka ili pogrešno pravno stanje | **3 dokazana** (1 zatvoren) |
| **D** — LIVE + POKVARENO | pravi korisnički put stiže do njega, produkcija odbija | **~24** (podskup dokazan) |
| **C** — USLOVNO ŽIVO | izvršava se samo uz određenu konfiguraciju/stanje | ~12 |
| **B** — MRTAV KOD | nedostižno iz produkcije | UNKNOWN — nije dokazivano po stavci |
| **A** — LAŽNO POZITIVNO | validno (drugi izvor, dinamički upit, samo test/komentar) | 3 reference (test/skripta) |

**Pravilo prioriteta:** E > D > C > B > A, ali **uticaj nadjačava broj**.

---

## 2. Rangirano prema Beta Exit Gate-u

Tri uslova gejta su jedini merodavni kriterijum:

1. Nijedan ekran ne sme prikazati neizvršenu/neuspelu proveru kao pozitivnu.
2. Nijedan dokument ne sme biti dohvatljiv drugom advokatu.
3. Svako obećanje koje UI daje mora biti istinito.

### P0 — nijedan

Nijedan nalaz iz ovog popisa ne obara uslov 2 (izolacija dokumenata). Sve
nepostojeće kolone **sužavaju** rezultat ili obaraju upit; nijedna ne proširuje
opseg čitanja.

### P1 — blokira gejt

| ID | Mesto | Nalaz | Klasa | Status |
|---|---|---|---|---|
| **DRIFT-001** | `routers/conflict_check.py:207` | `klijenti.pib` ne postoji → **ceo sloj „klijenti" padao na SVAKOM pozivu**; pretraga po klijentima nikad izvršena; `provera_potpuna` uvek `False`; provera se nikad nije naplatila | **E** | ✅ **PROVEN FIXED** |
| **DRIFT-002** | `routers/voice.py:142` `_fetch_rokovi` | `predmet_hronologija.naziv` ne postoji → `except → return []` → glasovni asistent kaže da **nema rokova** | **E** | ⛔ **PROVEN LIVE** |
| **DRIFT-003** | `routers/morning_briefing.py:1137` `today_focus` | tabela `rokovi` ne postoji → `except → pass` → „nemate hitnih rokova" | **E** | ⛔ **PROVEN LIVE** |
| **DRIFT-004** | `rokovi` — 13 upita u 10 fajlova | tabela ne postoji uopšte; `morning_briefing` (3), `case_commander` (2), `whatsapp_notif` (2), `dashboard`, `zadaci`, `zastarelost`, `integrations`, `decision_replay`, `api.py` | **D/E** | ⛔ **PROVEN LIVE** (po stavci neproveravano) |

`DRIFT-002/003/004` dele jedan pojam — **rok** — i jedan korenski uzrok:
kanonski vlasnik rokova je `predmet_hronologija` (zatvoreno u
`BETA-P1-DEADLINE-TRUTH`), a ovih 13 mesta i dalje gađa tabelu `rokovi` koja
nikad nije napravljena.

### P2 — ne blokira gejt, ali tiho gubi podatke

| Mesto | Nalaz |
|---|---|
| `shared/cost.py:97` | `api_costs` ne postoji → trošak AI poziva se **ne meri** (`warning()`) |
| `routers/praksa.py:311,330` | `ratio_decidendi` ne postoji → keš nikad ne radi, svaki poziv plaća LLM |
| `services/learning_engine.py` (5 mesta) | `case_patterns.ukupno_predmeta`, `recommendation_log.tekst/tip` → učenje iz ishoda ne radi |
| `routers/court_predictor.py` (6 mesta) | `predictor_analize.Sud/Sudija/Adv/…` (velika slova!) → profili sudija se ne upisuju |
| `api.py:2195,2203` · `routers/proof.py:290` | `chain_anchors.anchored_at/hash_256` → dokazni lanac se ne sidri |
| `workers/background_agents.py:91,110` | `kancelarija_clanovi.clan_id` → razrešavanje kancelarija pada |

### P3 — kozmetika / analitika

`client_twin`, `knowledge_graph`, `health_index`, `outcome_intel`,
`benchmarking`, `corrections`, `confidence_audit` — savetodavne površine gde
prazan rezultat ne tvrdi ništa pravno obavezujuće.

### UNKNOWN

68 mesta gde greška **izlazi glasno** (bez `try`) nisu pojedinačno vožena do
UI-ja. Ona ne mogu proizvesti lažno-zeleno (zahtev pada), ali **mogu** obarati
ekran u 500. Klasifikacija B vs D za njih ostaje **UNKNOWN** dok se ne dokaže
dostižnost po stavci.

---

## 3. DRIFT-001 — zatvoren nalaz, pun trag

**Sonda nad produkcijom:**

```
?select=id,ime,prezime,firma,email,pib  → 400 / 42703
                                          "column klijenti.pib does not exist"
?select=id,ime,prezime,firma,email      → 200
```

Stvarne kolone: PIB se čuva **šifrovan**, kao `pib_encrypted`.

**Zašto je bilo živo:** `/api/conflict-check` je dokazano živa putanja
(Playwright, `BETA-P0-COI`). Upit sloja 2 ide bezuslovno na svakom pozivu.

**Zašto je bilo pokvareno:** PostgREST odbija **ceo** zahtev. `except` je to
upisivao kao `sloj_status["klijenti"] = "greška"`.

**Tri stalne posledice:**

1. Pretraga po tabeli `klijenti` (ime · prezime · firma · email → `predmet_klijenti`
   → uloga u predmetu) **nikad se nije izvršila**. Sukob sa nekim ko je zaveden
   kao *klijent*, a ne kao tužilac/tuženi u `predmeti`, nije mogao biti pronađen.
2. `provera_potpuna` uvek `False` → svaka provera prikazuje „⚠️ PROVERA NIJE
   POTPUNA". Upozorenje koje se pali **uvek** prestaje da bude upozorenje.
3. `conflict_check` se nikad nije naplatio (`if _provera_potpuna: consume`).

**Zašto testovi nisu uhvatili:** `tests/test_beta_p0_conflict_of_interest.py::_Supa.select()`
prima **bilo koje** ime kolone. Test i implementacija su bili na istoj strani
ugovora — nijedan ne zna šta baza stvarno ima.

**Zašto `pib` NIJE preimenovan u `pib_encrypted`:** poređenje otvorenog PIB-a iz
forme sa šifrovanom vrednošću se nikad ne bi poklopilo → **tih lažno-negativan
nalaz** umesto glasne greške. Dešifrovanje svih klijenata na svakoj proveri bi
zaobišlo strogi audit trag iz `BETA-P0-SENSITIVE-DATA-AUDIT`. Zahtev sa PIB-om
zato **degradira** proveru na nepotpunu.

**Uz to:** `_slojevi_greska` se izvodi iz `v != "ok"` umesto `v == "greška"` —
fail-closed **po konstrukciji**, ne po nabrajanju stanja.

---

## 4. Šta ovaj sprint NIJE uradio

- Nije dirao 80 preostalih korenskih uzroka. Popravka bez dokaza dostižnosti je
  zabranjena mandatom.
- Nije kreirao tabelu `rokovi`. Kanonski vlasnik pojma „rok" je već odlučen
  (`predmet_hronologija`); kreiranje druge tabele bi udvostručilo vlasnika.
- Nije menjao nijednu migraciju niti produkcione podatke.

# FAZA 6.2.1 — PROVENANCE BOUNDARY REPORT

## 1. Environment proof
0 GPT poziva · 0 email-a · 0 SMS · 0 push/deploy · 0 novih produkcionih observation-a ·
0 promena fixture-a · 0 confirmation zapisa. Dokazano brojacima u §16.

## 2. Starting SHA
```
HEAD (lokalno)  27a4dd87      origin/main = production  044c5310
```
FAZA 6.2 commit i dalje NIJE pushovan.

## 3. Code path analyzed
`shared/rokovi.py::sme_pokrenuti_obavezu` → `je_ai_poreklo` → `AI_AKTERI`,
i svih 16 pisaca `predmet_hronologija`.

## 4. Source of `akter`
**Kljucni nalaz: `akter` NIJE polje provenijencije. Preopterecen je.**

| Pisac | `akter` | Priroda |
|---|---|---|
| `case_dna.py:899` | `"Genome (AI)"` | potpis proizvodjaca, **autonomno** |
| `case_pipeline.py:376` | `"Pipeline (AI)"` | potpis proizvodjaca, **autonomno** |
| **`api.py:6108`** | **`str(ev.get("akter") or "")`** | **TEKST IZ MODELA** |
| `smart_intake.py:1384` | `"Smart Intake"` | potpis; rok AI-ekstrahovan, covek klikce „Kreiraj predmet" |
| `api.py:7187` | `"Auto-detect (AI)"` | ruta `POST .../confirm-links` → **covek potvrdio** |
| `copilot.py:812` | `"Copilot (AI)"` | advokat kuca „Dodaj rok…" → **covek u petlji** |
| `intake.py:318` | `"Intake Wizard (AI)"` | `body.prvi_rok` iz forme → **covek** |
| `intake.py:451` | `"Intake Wizard — šablon"` | covek bira sablon |
| `intake.py:1042` | `"Template (AI)"` | covek bira sablon |
| `rokovi_lanac.py:450` | `"Automatski — ZPP lanac \| …"` | deterministicki, covek pokrece |
| `rocista.py:399` | `"Advokat"` | covek |
| `ugovor_zastupanja.py:337` | `f"Advokat {ime}"` | covek |
| `predmeti_close.py:190` | `hron_akter[:300]` | **promenljiva, ne moze se nabrojati** |
| `learning.py:274` | `"Learning Engine"` | posledica ljudske akcije |
| `case_evolution.py:399` | `"Case Evolution Engine"` | deterministicka posledica |
| `onboarding.py:246` | `"Demo predmet"` | demo |

## 5. Query projection audit
Svih 7 gejtovanih upita (email ×3, SMS ×2, notifikacije ×2) **eksplicitno dovlaci
`akter`**. Call-site disciplina je uredna — ali ona ne dokazuje runtime granicu,
sto je i poenta ovog audita.

## 6. Exact implementation behavior
```python
def je_ai_poreklo(akter): return (akter or "") in AI_AKTERI

def sme_pokrenuti_obavezu(red, potvrdjeni_ids=None):
    if not je_ai_poreklo(red.get("akter")): return True     # <- ALLOW
    rid = red.get("id")
    if not rid: return False
    return rid in (potvrdjeni_ids or set())
```
`AI_AKTERI = ("Genome (AI)", "Pipeline (AI)")` — **whitelist, ne detekcija.**
Sve van liste je „ljudsko" po definiciji.

## 7. Truth table (mereno pozivanjem funkcije, `potvrdjeni_ids=set()`)

| Scenario | `akter` | Rezultat | Kod koji ga proizvodi |
|---|---|---|---|
| Known AI #1 | `"Genome (AI)"` | **DENY** | `je_ai_poreklo`→True, `rid` nije u skupu |
| Known AI #2 | `"Pipeline (AI)"` | **DENY** | isto |
| Human | `"Advokat"` | ALLOW | `je_ai_poreklo`→False |
| NULL | `None` | **ALLOW** | `(None or "") == ""`, `"" not in AI_AKTERI` |
| Empty | `""` | **ALLOW** | isto |
| Missing field | kljuc ne postoji | **ALLOW** | `.get()`→None, isto kao NULL |
| Unknown | `"Future AI Agent"` | **ALLOW** | nije u whitelist-i |
| Unknown | `"Unknown"` | **ALLOW** | nije u whitelist-i |

## 8–11. Missing / NULL / Empty / Unknown — rezultat
Sva cetiri: **ALLOW**. Testovi `MISSING_2` … `MISSING_6`.

## 12. Harness fidelity check
Provereno pozivanjem FAZA 6.2 harness-a: upit `select("id, dogadjaj, datum_iso,
predmet_id")` vraca red **bez kljuca `akter`** — harness ga NE dodaje i NE maskira.
```
upit bez akter -> ['datum_iso', 'dogadjaj', 'id', 'predmet_id']
upit sa  akter -> ['akter', 'dogadjaj', 'id']
```
Harness je veran. Nije menjan u ovom auditu.

## 13. Bypass result — 🔴 POTVRDJEN, I AKTIVAN JE DANAS

`POST /api/predmeti/{predmet_id}/upload` → `predmet_upload_auto_analyze` je
**autonomna AI ekstrakcija hronologije iz advokatovog dokumenta**. Njena prompt
shema (`api.py:5176`) trazi `"akter": "Ko je preduzeo radnju (osoba, firma, sud...)"`,
i ta vrednost se upisuje **u isto polje iz kog kapija cita poreklo**.

Posledica, mereno na produkciji u trenutku audita:
```
ukupno redova u predmet_hronologija        55
PROLAZI kapiju (bez ijedne potvrde)        49
  od toga sa `dokument_naziv` (AI upload)  49 / 49
  od toga podobno za podsetnik             27      <- kritičan/važan
blokirano kapijom                           6      <- samo Genome/Pipeline
```
Vrednosti `akter` koje prolaze: `DOO Alfa Trejd` (12), `Zaposleni Marko Petrović` (9),
`Zaposleni Marko Jovanović` (8), `Kupac Agrocentar DOO` (4), `Vladimir Rakić` (4),
`Poslodavac DOO Sever` (3), … — **sve su imena stranaka koja je izvukao model.**

Pretpostavka iz FAZE 6.2 („`akter` = ime stranke ⇒ ljudski unos") je **oborena**.
Kapija danas pokriva **6/55 redova**.

## 14. Code changes
**NIJEDNA.** `git status` nad `shared/`, `routers/`, `api.py`, `services/`,
`migrations/`, `static/` je prazan. Dodat je samo
`tests/test_faza621_provenance_boundary.py` (26 prosli, 1 `xfail(strict=True)`
koji oznacava otvorenu rupu i javice se cim bude zatvorena).

Popravka NIJE izvrsena jer izbor izmedju fail-open i fail-closed je bezbednosna
politika — v. §17.

## 15. Regression result
`74 passed, 1 xfailed` nad ciljanim skupom (FAZA 6.2 gate, E2E putevi, B10, ovaj
audit). Kod nije menjan, pa siri regression subset nije relevantan; poznati
`test_prg_night_register` [trio] padovi ostaju pre-postojeci i nisu dirani.

## 16. Production impact
```
predmeti 23 · predmet_dokumenti 44 · predmet_hronologija 55
predmet_genome_history 26 · case_actions 31 · predmet_dokazi 12
potvrde/odbijanja u audit_immutable: 0
```
Identicno stanju pre audita. Fixture iz FAZE 6.1 netaknut.

## 17. FINAL VERDICT

🔴 **RED** — AI observation moze izgubiti provenance signal i zatim proizvesti
side effect. Nije hipoteticki: **27 produkcionih redova je danas podobno za
podsetnik bez ijedne ljudske potvrde**, i svi poticu sa autonomnog AI upload puta.

### Zasto nisam sam popravio

Koren nije u kapiji nego u tome sto `akter` nosi dva razlicita znacenja. Svaka
popravka je bezbednosna politika, ne sitnica:

**Opcija A — obrnuti whitelist (samo poznati LJUDSKI potpisi prolaze).**
Danas bi blokirala 49 redova (27 izvrsivih), od kojih su **svi AI**, i **0 stvarno
ljudskih** — jer u produkciji danas nema nijednog reda unetog rukom. Ali lista se
**ne moze zatvoriti**: `predmeti_close.py:190` upisuje promenljivu `hron_akter`,
pa bi svaki nepredvidjen ljudski potpis bio tiho ugasen. Rizik: **tihi gubitak
legitimnih rokova** — tacno ono sto §9 zabranjuje da odlucim sam.

**Opcija B — pravo polje provenijencije** (`predmet_hronologija.izvor` sa CHECK
`AI|COVEK|SISTEM`, puni ga svaki pisac). Cisto i konacno, ali trazi **migraciju**
koju pokrece vlasnik; do tada kolona ne postoji i kapija nema sta da cita.

**Opcija C — ostaviti kako jeste.** Tiha opasnost ostaje: prvi advokat koji ukljuci
email podsetnike dobija opomene za rokove koje je izmislio model iz njegovog
dokumenta, bez ijedne potvrde.

## 18. Push / deploy
**NIJE pushovano. NIJE deployovano.** `origin/main` = `044c5310`. Cekam izricitu
naredbu.

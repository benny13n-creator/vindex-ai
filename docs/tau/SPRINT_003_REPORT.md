# Mission Report — Program Tau, Master Sprint 003: Canonical AI Decision Boundary

**Datum**: 2026-08-06
**Program**: Tau (treći sprint)
**Tim**: 5 forenzičkih foreka (4 za Phase 1 dekompoziciju + 1 za live-caller verifikaciju) + direktna
implementacija/testiranje.

---

## Zatvorenje misije

Cilj: GPT nikad nije vlasnik poslovne istine. Kanonski sistemi (Case Actions/Case Readiness/Gap
Engine/Risk Engine/Genome/Evidence) ostaju vlasnici; GPT objašnjava, sažima, rasuđuje — nikad ne odlučuje
iznova.

## Otkriveno

**Kritična ispravka pre bilo kakve implementacije**: prvobitni grep `static/vindex.js`-a sugerisao je da su
`case_intelligence.py`-ovi endpoint-i mrtvi (isti obrazac kao Case Commander pre Sigma 005). Ovo je bilo
**pogrešno** — stvarni HTML button markup ove aplikacije živi u `index.html`, ne u `vindex.js`-u. Direktna
provera tamo pronašla je stvarne, ožičene `onclick` handlere za `case_intelligence.py`, `copilot.py`, i
svih 9 `strategija.py` endpoint-a. Samo `morning_briefing.py` je potvrđeno mrtav/bez UI-ja. Ovo je
fundamentalno promenilo obim Faze 3: 3 od 4 fajla zahtevaju očuvanje TAČNOG postojećeg response oblika (bez
razbijajuće restrukturacije bez i frontend izmene); samo `morning_briefing.py` je slobodan od tog
ograničenja.

**4 paralelna foreka** mapirala su svaki preostali GPT decision surface: `case_intelligence.py`/`copilot.py`
(6 jasno neobezbeđenih polja + 2 meta-polja), `morning_briefing.py` (4 neobezbeđena polja kroz 3 poziva),
`strategija.py` (9 endpoint-a, arhitektonski nemoguć redirect jer ne postoji `predmet_id` nigde — ~90%
polja legitimno GPT Advisory po ispravnoj klasifikaciji, ne po propustu), i sweep preostalih modula
(potvrdio da su `court_predictor.py`-ova verovatnoća pobede i `evidence_graph.py`-ove kontradikcije već
poznate, veće fragmentacije iz Programa Beta — ne novi Tau 003 nalaz).

## Popravljeno

1. **`case_intelligence.py`** — `sledeci_korak`/`razlog`/`hitnost` sada bezuslovno iz `case_actions`
   (GPT više uopšte nije pitan). `kljucni_rizici` iz `case_context`-a (Gap Engine/Risk Engine). `napomena`
   i `pouzdanost_briefinga` deterministički (kompletnost podataka), nikad GPT samoprocena. Kao nusprodukt:
   ispravljen postojeći bag gde je frontend čitao `izvori.pouzdanost_briefinga`, a backend je pisao samo u
   `briefing.pouzdanost_briefinga` — sada piše na oba mesta.
2. **`copilot.py`** (oba handlera) — `sledeci_korak` override bezuslovan. `slabosti`/`upozorenja` iz
   Genome-a (`shared/gap_engine.py`). `verovatnoca_uspeha` iz Genome-ovog `snaga_predmeta_procent`
   direktno, ne duplirani GPT broj. `kriticni_rokovi` su stvarni `predmet_hronologija` redovi, ne GPT-ova
   parafraza.
3. **`morning_briefing.py::_generiši_briefing`** — "Danas zahteva pažnju"/"Ključni rok"/"Preporuka za
   danas" sada u potpunosti kod-generisani iz `case_actions`/`rocista`/`rokovi`, rangirano istim kanonskim
   redosledom kao ceo Sigma 005 (`shared/attention_priority.py`). GPT pitan za TAČNO jednu rečenicu
   ("Dobro jutro" uvod) — strukturno nesposoban da dopre do 3 odlučujuće sekcije.
4. **`strategija.py`** (svih 9 endpoint-a) — dodat `_ai_advisory` provenance (owner/napomena/generated_by/
   timestamp), reusing `commander_schema.py`-ov idiom. `_V2_SYSTEM` prompt eksplicitno diskredituje
   `procenat` kao izračunatu statistiku.

## Dokazano

**Novi testovi ovaj sprint**: `tests/test_tau003_decision_boundary.py` (novo, 6 testova), 3 nova testa u
`tests/test_tau002_morning_briefing_context.py`, 1 nov test u `tests/test_case_intelligence_briefing_alerts_fix.py`,
2 postojeća testa preimenovana i re-asertovana (`test_sigma_sprint004_case_readiness.py`, `test_case_intelligence_briefing_alerts_fix.py`)
jer su testirala STARO, sada namerno uklonjeno ponašanje (uslovni GPT fallback). Svi ostali postojeći
testovi u dodirnim fajlovima (copilot 64, case_intelligence 21, morning_briefing 5, strategija 22) prolaze
NEPROMENJENI.

**Regresija**: 0. Puna test suita: **2.838 passed, 1 skipped, 0 failed** (bilo 2.828 na kraju Tau Master
Sprint 002).

## Faza 4 — Forenzički napad na granicu odlučivanja

Svih 7 imenovanih napada iz misije, sa direktnim test-dokazom:

1. **Izmisli prioritet** — PADA na svakoj migriranoj površini (poison test za `hitnost`, `sledeci_korak.prioritet` bezuslovno iz `case_actions`, rangiranje kroz predmete kanonski).
2. **Izmisli spremnost** — PADA strukturno; nijedan GPT prompt u 4 fajla ne pita za readiness/spremnost polje uopšte.
3. **Izmisli rokove** — PADA; `kriticni_rokovi`/`Ključni rok` čitaju stvarne DB redove, poison test dokazuje da GPT-ov izmišljeni "rok je danas!" ostaje zarobljen u uvodnoj rečenici.
4. **Izmisli nedostajuće dokaze** — PADA; već kanonski (Sigma 003/004), `napomena` sada takođe determinističan.
5. **Izmisli kontradikcije** — PADA; poison test dokazuje da samo prava Genome kontradikcija preživljava u `slabosti`.
6. **Izmisli sledeći korak** — PADA na sve 3 migrirane površine, uslovni fallback (TAU-002/003-ov sopstveni predmet) sada bezuslovan.
7. **Izmisli pravne činjenice** — van obima ovog sprinta (`legal_reasoning_engine.py`-ov domen, nepromenjen); svako polje ovog sprinta koje bi moglo biti pobrkano sa proverenom činjenicom sada je ili determinističko ili eksplicitno obeleženo kao GPT mišljenje.

**Sprint ne pada ni na jednom od 7 imenovanih napada za migrirane površine.**

## Odloženo

`TAU-010` (novo) — `today_focus` i dalje slobodno bira, sa nekonzistentnim fallback-om naspram
success-path-a; van obima flagship-poziva koji je ovaj sprint prioritizovao, ali imenovano, ne prećutano.
`morning_briefing.py`-ov `_ai_prioritizacija_alertova` već ispravno skopiran (nepromenjen). `strategija.py`-ovih
`faze[].koraci[].prioritet` polja ostaju GPT Advisory po nužnosti (nema case zapisa za proveru) — ispravno
obeleženo, ne prisilno preusmereno. `court_predictor.py`/`evidence_graph.py`-ove veće, ranije poznate
fragmentacije namerno nisu dirane ovaj sprint.

## Zaključak

Ovaj sprint ne tvrdi da je svaki GPT poziv na platformi sada obezbeđen — `strategija.py`-ov sopstveni domen
(bez case zapisa) ostaje inherentno savetodavan po dizajnu, ne po propustu, i sada je to i strukturno
označeno. Ono što JESTE dokazano: za 3 od 4 imenovana kritična modula (`case_intelligence.py`, `copilot.py`,
`morning_briefing.py`-ov flagship poziv), GPT više ne može — ni greškom, ni namernim "poison" testom —
izmisliti prioritet, sledeći korak, rok, nedostajući dokaz ili kontradikciju koja zaobiđe kanonski izvor.
Cilj nije bio da GPT prestane da razmišlja. Cilj je bio da GPT prestane da odlučuje — i za ova četiri
pitanja, u ova tri modula, sada je tako.

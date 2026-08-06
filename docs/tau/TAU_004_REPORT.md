# Mission Report — Program Tau, Master Sprint 004: Canonical Legal Reasoning & GPT-5.5 Intelligence Layer

**Datum**: 2026-08-06
**Program**: Tau (četvrti sprint)
**Tim**: 7 imenovanih uloga (Architect, Forensic Auditor, Legal Reasoning Engineer, GPT Integration
Engineer, Performance Engineer, Test Engineer, Documentation Engineer), izvedene kroz 5 paralelnih
forenzičkih foreka + direktna implementacija.

---

## Zatvorenje misije

Cilj: ne novi AI, ne novi model, ne nove funkcije — sloj koji omogućava GPT-u da ZAISTA razume predmet, kao
vrhunski pravni analitičar, ne generator teksta. Ovo je prvi sprint koji je mapirao CELU platformu (ne samo
4 fajla iz Tau 003), i prvi koji je otkrio da je fragmentacija koju je Tau 002/003 popravio za ta 4 fajla
mnogo veća širom platforme.

## Otkriveno

**Faza 1 (Pipeline Map)**: Tačno 2 fajla (`case_intelligence.py`, `morning_briefing.py`) zovu kanonski
`build_case_context()`. **17+ case-linked fajlova** ima sopstveni, nezavisan context fetch — nijedan ne
uvozi `shared.case_context`. Najozbiljniji nalaz: `court_predictor.py` prima `predmet_id` na svih 7
endpoint-a, ali ga koristi ISKLJUČIVO za audit logging — stvarni AI unos je slobodan tekst koji korisnik
zalepi u svaki poziv. Advokat može poslati pravi ID predmeta i AI predikcija nikad ne dodirne trenutno
stanje tog predmeta (Genome, dokumenti, dokazi). `hearing_cc.py` ima sopstveni bogat 7-tabelni context
builder — treća nezavisna implementacija "sakupi sve o predmetu" u platformi.

**Faza 2 (Kvalitet konteksta)**: od 15 stavki sa liste misije, 8 potpuno pokriveno, 2 uski isečak (Genome —
samo 3 od ~10 stvarnih polja; prethodna ročišta — prisutna ali nerazlikovana od budućih, **popravljeno ovaj
sprint**), 4 postoje negde drugde u platformi ali nisu povezana (OCR metapodaci, istorija klijenta,
prethodne strategije, istorija sudije — poslednje je već poznat `ALPHA-005`), 1 uopšte ne postoji nigde
(strukturirani podaci o sudu van imena).

**Faza 4 (Legal Reasoning Verification)**: 3 od 5 površina imaju pravi dokazni lanac
(`legal_reasoning_engine.py`, Genome kontradikcije, evidence_graph OSPORAVA ivice). 2 nemaju:
`najslabija_tacka`/`snaga_predmeta_procent` (najozbiljniji nalaz — Genome je kanonska istina platforme, a
ovaj par nema NIKAKAV zahtev za citiranje, **delimično popravljeno ovaj sprint**) i `court_predictor.py`-ova
verovatnoća pobede (bez citiranja konkretne prakse — imenovano, ne popravljeno).

**Faza 5 (Ekstremna skala)**: 300 rokova, 50 kontradikcija, predmet star 20 godina — sve prolazi ispravno
kroz `build_case_context()`. Nijedan bag pronađen (500/1000 dokumenata već dokazano u Tau 002).

**Faza 6 (Adversarial)**: gušći "malicious OCR" napad i dalje ispravno blokiran (SEC-003, bez regresije).
Suptilniji, jednofrazni pokušaj injekcije bodovan je ISPOD praga blokiranja tokom istraživačkog testiranja
— imenovano, ne popravljeno (menjanje bezbednosnog praga bez opsežnog testiranja lažnih pozitiva je
neopravdan rizik u ovom sprintu). Duplirani dokazi se tiho duplo broje; hronologija se ne proverava na
logičku moguću; citiranje članova zakona van `legal_reasoning_engine.py` nema stvarnu proveru postojanja.

**Faza 7 (Troškovi)**: najskuplja POJEDINAČNA operacija je `strategija.py`-ov `kompletna-analiza`
orkestrator (~$0.20/pokretanje, 8 uzastopnih gpt-4o poziva). Genome ekstrakcija je najskuplji POJEDINAČNI
poziv (~$0.078) ali NE skalira sa brojem dokumenata (već kapiran na 25 dok/60000 karaktera, Program Celina
2026-07-24). Procena za kancelariju od 1000 predmeta: ≈$138/mesečno, pod eksplicitno navedenom
pretpostavkom (nema stvarne telemetrije učestalosti poziva nigde u kodu).

**Faza 8 (GPT-5.5 mogućnosti)**: najjača preporuka — prompt caching (~90% jeftinije na ponovljenim system
prompt tokenima, do 80% manja latencija), skoro nulti inženjerski trošak, nula arhitektonskih promena,
skoro svaki od ~130 poziva već koristi dug, statičan system prompt.

## Popravljeno (Faza 9)

1. **`routers/case_dna.py` + `shared/genome_validator.py`** — `najslabija_tacka` sada ima `lokacija` polje
   (isto DOK-XX pravilo kao `kontradikcije`), i nova `_validate_najslabija_tacka_lokacija` provera (kopira
   `_validate_kontradikcije_lokacije` polje-po-polje, ne izmišlja novi mehanizam) hard-flaguje izmišljenu
   DOK-XX referencu. Prazno polje NIJE greška (holistička slabost je legitimna). 4 nova testa, 51/51 u
   `test_genome_validator.py` prolaze.
2. **`shared/case_context.py`** — `deadlines` polje sada nosi `proslo` (bool) po redu, izračunato iz
   `datum` naspram danas — zatvara "prethodna ročišta nerazlikovana od budućih" nalaz iz Faze 2, bez
   dodavanja novog izvora podataka.

## Dokazano

**16 novih testova**: 4 u `test_genome_validator.py` (najslabija_tacka grounding), 1 u
`test_tau002_case_context.py` (proslo/upcoming), 4 u novom `test_tau004_extreme_scale.py` (Faza 5), 7 u
novom `test_tau004_adversarial.py` (Faza 6). Svi postojeći testovi u dodirnim fajlovima prolaze
NEPROMENJENI.

**Regresija**: 0. Puna test suita: **2.854 passed, 1 skipped, 0 failed** (bilo 2.838 na kraju Tau Master
Sprint 003).

## Odloženo

6 novih debt stavki, nijedna prenagljena: `TAU-011` (court_predictor.py context gap, Critical — kandidat za
sledeći Sigma-005-obimni sprint), `TAU-012` (17+ fajlova van kanonskog buildera, High), `TAU-013` (4 stavke
sa liste postoje negde ali nisu povezane sa kanonskim ugovorom, Medium), `TAU-014` (court_predictor.py
verovatnoća bez citiranja, Medium), `TAU-015` (SEC-003 prag propušta suptilniji napad, Medium-High),
`TAU-016` (3 manja adversarial nalaza, Low-Medium).

## Zaključak

Ovaj sprint ne tvrdi da GPT sada "zaista razume predmet" na celoj platformi — to bi bilo netačno za 17+
fajlova koji i dalje rade sa nezavisnim, neproverenim kontekstom, i posebno netačno za
`court_predictor.py`, koji trenutno proizvodi predikcije koje uopšte ne konsultuju predmet na koji se
navodno odnose. Ono što JESTE urađeno: celokupna mapa problema sada postoji (nije više nagađanje), Genome-ov
najozbiljniji negrounding nalaz je zatvoren za jedno od dva polja, a šest preostalih nalaza je imenovano sa
dovoljno preciznosti da sledeći sprint može direktno da počne od njih, bez ponovnog otkrivanja. Cilj nije
bio da se sve popravi u jednom sprintu — cilj je bio da se zna, precizno, koliko je platforma zaista daleko
od "GPT kao vrhunski pravni analitičar," i da se ono što je bezbedno popravljivo odmah popravi.

# Mission Report — Program Sigma, Master Sprint 003: Legal Gap & Missing Evidence Engine

**Datum**: 2026-08-06
**Program**: Sigma (treći sprint)
**Tim**: uloge izvedene direktno u ovoj sesiji (2 forenzička foreka + direktna implementacija/testiranje).

---

## Zatvorenje misije

Cilj: dokazati da sistem može automatski da prepozna nedostajuće dokumente, dokaze, procesne radnje,
rokove, prekinute lance događaja, neusaglašene činjenice i nepotvrđene tvrdnje — i da ih prikaže kao
proverljive hipoteze, nikada kao činjenice, kroz JEDAN kanonski mehanizam, bez paralelnih algoritama.

## Otkriveno

**Najkonkretniji, najjasniji nalaz ovog sprinta**: `routers/copilot.py` je sadržao **2 potpuno nezavisna
GPT generatora "šta nedostaje"**, nijedan povezan sa `EXPECTED_DOCS` niti pouzdano čitajući Genome:
`_handle_analiza_predmeta`'s sopstveno `"nedostaju"` polje (delimično svesno Genome konteksta za DRUGA
polja, ali ne za ovo), i `_handle_plan_predmeta`'s sopstveno `"nedostaje"` polje — **potpuno slepo za
Genome, nula konteksta**. Zajedno sa Genome-ovim sopstvenim `nedostaje[]`, to je **3 nezavisna GPT-
generisana "šta nedostaje" izvora** — direktan, živ dokaz kršenja ovog programa sopstvenog "jedan mehanizam
postaje vlasnik" principa, ne hipotetički rizik.

**Relevantan "near-miss" pronađen u Legal Reasoning Engine-u**: `services/legal_reasoning_engine.py`'s
sopstveni `generate_reasoning_graph` tiho odbacuje (`continue`-preskače) svaki pravni element bez podrške —
tačno mesto gde bi "nedostaje pravni element" signal trebalo da se pojavi, a trenutno se baca. **Namerno
NIJE povezano ovog sprinta** — modul sopstveni docstring nosi eksplicitnu, osnivačevu Fazu 0 ogradu
("Wired to nothing... no downstream consumer reads this yet") iz 2026-07-23 — poštovana, ne zaobiđena.

**Fazâ 3/4 (Document Expectation, Chain Completeness) — potvrđeno, ne postoje danas.** Nijedan mehanizam ne
zaključuje "ugovor pominje aneks → očekuj aneks" niti proverava parove poput žalba→dokaz predaje. Pravi,
potvrđen gap, ne wiring problem.

**Fazâ 5 (Hypothesis status) — pronađen jak, već dokazan presedan**: `lessons_learned.status_lekcije`
(migracija 039) već implementira skoro tačno traženi obrazac (`predlog_ai → usvojena_praksa (partner
potvrdi) | odbijena | zastarela`, sa odvojenom `pouzdanost` kolonom) — dizajn za Gap Engine treba da se
gradi na ovome, ne od nule.

**Samo-pronađena duplikacija, u kodu koji je OVAJ sprint upravo napisao**: `shared/gap_engine.py`-ov
sopstveni `gaps_from_case_problems` je nezavisno ponovo izgradio ISTU tekst-klasifikacionu kaskadu koju
`services/case_evolution.py`-ova Rule 2 već koristi — dva nezavisna if/elif lanca nad istim
`identify_case_problems()` izlazom. Pronađeno primenom Faze 7 sertifikacije na sopstveni kod ovog sprinta,
ne samo na postojeći.

## Popravljeno

1. **`shared/gap_engine.py`** (novo) — JEDNA kanonska tačka agregacije nad 3 postojeća izvora
   (`identify_case_problems`, Genome `nedostaje[]`, Genome `kontradikcije[]`), svaki Gap zapis nosi
   tip/izvor/razlog/pouzdanost/očekivano/pronađeno/zašto/hipoteza — Faza 2-ov zahtev, ispunjen bez ijednog
   novog detektora.
2. **`routers/copilot.py::_handle_analiza_predmeta`** — `"nedostaju"` sada čita direktno iz Genome-a preko
   `gap_engine`, ne iz nezavisnog GPT poziva; fallback na GPT samo kad Genome ne postoji.
3. **`routers/copilot.py::_handle_plan_predmeta`** — dodat `case_dna` u sopstveni select (prethodno ga
   NIJE imao uopšte); `"nedostaje"` sada isto čita iz Genome-a preko `gap_engine`.
4. **`shared/gap_engine.py::classify_case_problem`** — ekstraktovana JEDNA klasifikaciona funkcija;
   `services/case_evolution.py`-ova Rule 2 sada je koristi umesto sopstvenog, duplog if/elif lanca —
   samo-pronađena i samo-popravljena duplikacija, u istom sprintu u kom je nastala.

## Dokazano

**14 novih testova** (`tests/test_sigma_sprint003_gap_engine.py`): sve 4 normalizacione funkcije pojedinačno
(uključujući da je deterministički izvor uvek `hipoteza=False`, GPT izvori uvek `hipoteza=True`), stabilnost
`dedupe_key`-a za kontradikcije (ponovno korišćenje Sprint 002-ove sopstvene funkcije), agregacija sva 3
izvora, sortiranje/prevod za oba Copilot potrošača, **direktan dokaz stvarnog baga**: GPT-ova sopstvena
nezavisna `"nedostaju"`/`"nedostaje"` vrednost mora biti IGNORISANA kad Genome postoji (2 dedikovana testa),
fallback kad Genome ne postoji (2 testa), i eksplicitna potvrda da Rule 2 i Gap Engine sada dele JEDNU
klasifikacionu funkciju (izvorno-kodna inspekcija).

**Regresija**: 0. Puna test suita: **2.759 passed, 1 skipped, 0 failed** (bilo 2.745 na kraju Sigma Master
Sprint 002).

## Faza 6 — Case Impact

Case Actions/Workspace/Dashboard već primaju gap podatke kroz `_compute_target_actions` (sad deleći
klasifikator sa Gap Engine-om); Copilot sada ispravno čita Genome umesto da nagađa. Nema još jedinstvenog
`GET /predmeti/{id}/gaps` endpoint-a koji izlaže PUNU `collect_case_gaps` agregaciju (uključujući
`hipoteza`/`pouzdanost` polja) — imenovano kao `SIGMA-017`, mehanički, nizak rizik, odloženo samo zbog
prioriteta zatvaranja živog baga.

## Faza 7 — Forenzička sertifikacija

Lažno pozitivni (deterministički izvor ne može biti; GPT izvor ispravno označen `hipoteza=True`, nije nova
pojava); propušteni GAP-ovi (potvrđeno, Faza 3/4 primeri, imenovano ne popravljeno); duplikati (**pronađen i
popravljen — sopstvena duplikacija ovog sprinta**); kontradikcije između GAP izvora (nisu bag — 2 genuinski
različita pitanja, ispravno atributovana); nestabilni rezultati (kontradikcije stabilne od Sprint 002,
Genome-ovo sopstveno `nedostaje[]` još NIJE — `SIGMA-015`, imenovano).

## Odloženo

`SIGMA-012` (Legal Reasoning Engine ne povezan — poštuje eksplicitnu osnivačevu Fazu 0 ogradu), `SIGMA-013`
(document-to-document expectation reasoning — potrebno proširenje Genome prompta, live verifikacija),
`SIGMA-014` (chain completeness/punomoćje — potrebna proizvodna odluka o obimu po tipu predmeta),
`SIGMA-015` (Genome nedostaje[] nema stabilan identitet kroz refresh-eve — preduslov za `SIGMA-016`),
`SIGMA-016` (puna hipoteza status šema — dizajn gotov, ne implementiran, zavisi od `SIGMA-015`), `SIGMA-017`
(nema jedinstvenog gap read endpoint-a).

## Zaključak

Ovaj sprint ne tvrdi lažnu potpunu pobedu. Zatvara jedan konkretan, živ, dokazan bag (3 nezavisna "šta
nedostaje" generatora, sad 1) i jednu samo-pronađenu duplikaciju u sopstvenom kodu ovog sprinta — primenom
iste forenzičke discipline na NOVI kod kao i na postojeći. Imenuje 6 novih debt stavki (`SIGMA-012` do
`SIGMA-017`), svaka sa preciznim razlogom zašto zahteva osnivačevu odluku, novi GPT prompt eksperiment, ili
shema dizajn — ne mehaničku popravku.

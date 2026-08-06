# Mission Report — Program Tau, Master Sprint 002: Canonical Case Context Engine

**Datum**: 2026-08-06
**Program**: Tau (drugi sprint)
**Tim**: 2 forenzička foreka (Phase 1 diskavery) + direktna implementacija/testiranje.

---

## Zatvorenje misije

Cilj: jedan kanonski `CaseContext` mehanizam koji AI-u daje predmet + stranke + dokumente + činjenice +
dokaze + kontradikcije + nedostatke + rokove + akcije + readiness + vremensku liniju u jednoj,
determinističkoj, auditabilnoj strukturi — zamenjujući 4+ nezavisna, fragmentisana context buildera koje
je Tau Sprint 001 pronašao.

## Otkriveno

**Faza 1 (2 paralelna foreka)**: 7 stvarnih context-assembly funkcija u repou (ne samo 4 ranije poznate) —
`case_commander.py`, `case_intelligence.py`, `copilot.py` (2 handlera), `morning_briefing.py`,
`multi_agent.py`, `evidence_graph.py`, plus `case_dna.py`-ova sopstvena ekstrakcija (van obima po dizajnu).
Precizirani tačni brojevi tamo gde je Tau 001 imao grublje procene (npr. `case_intelligence.py`-ov skriveni
`[:10000]` char cutoff, `case_commander.py`-ovih tačnih 20-fetched/10-shown/8000-char granica).

**Ključna korekcija obima**: `routers/strategija.py` — jedan od 4 obavezna Phase 5 modula — **nije context
builder uopšte**. Nema `predmet_id` polje ni na jednom od svojih 7 request modela; nikad ne upituje
`predmet_dokumenti`/`predmet_dokazi`/`case_dna`/`case_actions`. Migracija bi značila DODAVANJE novog
`predmet_id` režima (feature), ne zamenu postojećeg context buildera (plumbing). Ovo ispravlja Tau 001-ovu
sopstvenu pretpostavku (11 "call sites" labelovanih kao "strategija.py" bez razlikovanja 2 odvojena fajla
sa istim imenom) — nije nova greška, nego neprecizna ranija klasifikacija ispravljena direktnom verifikacijom.

## Popravljeno

1. **`shared/case_context.py`** (novo) — `build_case_context(predmet_id, uid, supa, include_documents=True)`,
   13 kontraktnih polja, svako umotano `context_field(value, source, owner, refresh)` + timestamp. Čita
   isključivo iz postojećih kanonskih izvora (`services/risk_engine.py`, `shared/gap_engine.py`,
   `shared/case_readiness.py`, `case_actions`, `rocista`, `predmet_hronologija`, `predmet_dokazi`) — nula
   novih poslovnih odluka.
2. **Document Visibility Engine** (Faza 3, isti fajl) — `_select_documents` (Layer 4: 5
   uvek-najsvežijih + deterministički stride sample preko CELOG skupa, ne statičan `[:N]` na
   neuređenom fetch-u — tačan bag koji je ovaj sprint postojao da reši), `_excerpt` (reuse
   `cross_doc.py::_uzorkuj_dokument`, ne novi sampler), `get_document_full_text` (Layer 5, on-demand
   retrieval po `dokument_id`, RLS-scoped). Dokazano (testovima, ne tvrdnjom): svaki dokument je ili u
   `included` ili u `not_included_but_retrievable` — nijedan trajno nevidljiv, na 500- i 1000-dokument skali.
3. **`include_documents=False`** (lightweight mode) — za portfolio-wide pozivaoce (morning_briefing.py) koji
   ne trebaju sadržaj dokumenata; preskače `predmet_dokumenti` upit u potpunosti, ali polje ostaje ispravno
   oblikovano sa eksplicitnim "not fetched" markerom, nikad tiho prazno.
4. **`routers/copilot.py`** — oba context buildera (`_handle_analiza_predmeta`, `_handle_plan_predmeta`)
   sada šalju stvarni sadržaj dokumenta (preko Document Visibility Engine-a), ne samo imena fajlova.
   Genome/case_actions logika iz Sigma 003/004 nepromenjena (nije bila pokvarena).
5. **`routers/case_intelligence.py`** — `_gather_case_data`/`_build_context_text` sada dodaju
   dokumenti/dokazi/otvorene akcije/ročišta (ranije: nula pristupa bilo čemu od toga). Postojeći bogati
   Genome prikaz nepromenjen.
6. **`routers/morning_briefing.py`** — `_generiši_briefing` (glavni, najvidljiviji poziv) sada prikazuje
   kanonski readiness status po predmetu; ostala 2 poziva eksplicitno označena LEGACY (misija sama
   dozvoljava ovu opciju kad puna migracija nije bezbedna u ovom sprintu).
7. **`docs/architecture` registri**: nije menjano ovaj sprint (Case Context Contract ne uvodi nove
   DC-brojane odluke — sve odluke koje čita već su DC-001..DC-015).

## Dokazano

**31 novi test** ukupno: `tests/test_tau002_case_context.py` (26 — schema oblik, sva 13 polja, dokumenti na
500/1000 skali, determinizam kroz simulirane restarte, paralelni pozivi za isti/različite predmete, Genome
refresh između poziva, više kontradikcija, veliki broj dokaza, aktivna akcija bez dokumenata, lightweight
mode), `tests/test_tau002_morning_briefing_context.py` (2), `tests/test_synapse_copilot_genome_context.py`
(1 novi), `tests/test_case_intelligence_briefing_alerts_fix.py` (2 nova). Svi postojeći testovi u dodirnim
fajlovima (copilot ×63, case_intelligence ×66, morning_briefing ×32) prolaze NEPROMENJENI.

**Regresija**: 0. Puna test suita: **2.828 passed, 1 skipped, 0 failed** (bilo 2.797 na kraju Tau Master
Sprint 001).

## Faza 6 — Performance & Cost

Nula novih GPT poziva, nula promenjenih modela. Query-count uticaj: `copilot.py` 0 (isti broj, širi
`select`), `case_intelligence.py` +7 (jedan dodatni round-trip depth), `morning_briefing.py` do +60 po
korisniku po jutarnjem pokretanju (paralelizovano, prihvaćeno kao trošak za cron posao sa satima
tolerancije, per Tau 001-ov sopstveni nalaz). Puna analiza: `CONTEXT_PERFORMANCE_ANALYSIS.md`.

## Faza 7 — Forenzički napad

Svih 5 imenovanih napada iz misije, sa direktnim test-dokazom (ne samo tvrdnjom):

1. **Dokument koji nikada ne ulazi u kontekst** — `test_select_documents_500_scale_every_document_accounted_for`,
   `..._1000_scale_...`: `included_ids ∪ not_included_ids == svi_ids`, uvek. Nijedan dokument nestaje bez traga.
2. **Kontradikcija koju AI ne može videti** — `test_multiple_contradictions_all_captured_not_just_first`:
   sve kontradikcije iz `case_dna` stižu u `contradictions` polje, nezavisno od Document Visibility Engine-a
   (ne prolaze kroz dokumentni sloj uopšte).
3. **Rok koji nije vidljiv** / **aktivna akcija koja nije uključena** —
   `test_active_action_always_included_even_with_zero_documents`: `active_actions`/`deadlines` čitaju
   `case_actions`/`rocista` bezuslovno — dokumentni sloj im ne može ništa sakriti jer nikad ne prolaze kroz njega.
4. **Različiti rezultati za isti predmet bez promene podataka** —
   `test_select_documents_deterministic_across_repeated_calls`,
   `test_select_documents_out_of_input_order_still_deterministic`,
   `test_build_case_context_deterministic_across_simulated_restarts`: isti skup dokumenata/podataka →
   identičan rezultat, bez obzira na redosled dolaska ili broj procesa/restartova.
5. **Genome refresh tokom AI poziva** — `test_genome_refresh_between_calls_is_reflected_immediately`: nema
   keš sloja (namerna arhitektonska odluka, `CANONICAL_CASE_CONTEXT_CONTRACT.md`'s own Non-goals), pa je
   promena vidljiva već na sledećem pozivu.

**Ekstremni test scenariji, mapirani na testove**: 500 dokumenata ✓, 1000 dokumenata ✓, dokumenti van
redosleda ✓, više kontradikcija ✓, veliki broj dokaza ✓ (200 zapisa, bez tihog odsecanja), paralelni AI
zahtevi ✓ (isti i različiti predmeti), restart ✓ (simuliran kroz sveže `_FakeSupa` instance). **Event
replay**: nije izvršen kao live test (infrastruktura za event replay je van obima ovog sprinta), ali
strukturno dokazano — `build_case_context` je čista funkcija čitanja trenutnog DB stanja, nema zavisnost od
event log-a samog; šta god replay ostavi kao konačno DB stanje, sledeći poziv će ga tačno odraziti, po
konstrukciji, ne po pretpostavci.

## Odloženo

`TAU-003` (morning_briefing.py-ova sopstvena "Danas zahteva pažnju" i dalje GPT-autorska, ne kanonska —
namerno van obima ovog sprinta, koji rešava VIDLJIVOST konteksta, ne granicu odlučivanja); Layer 5
(`get_document_full_text`) nije ožičen u live GPT tool-calling petlju ni za jedan potrošač — mehanizam
postoji i testiran je samostalno, ali nijedan modul ga još ne poziva automatski kad upit pomene dokument
van Layer 4 uzorka; `strategija.py`-ova `predmet_id` podrška (nova funkcionalnost, ne migracija).

## Zaključak

Ovaj sprint ne tvrdi da je AI sada svevidljiv za svaki predmet u svakoj situaciji — to bi bilo lažno pri
500+ dokumenata. Tvrdi ono što je dokazano: postoji tačno JEDAN Case Context Contract; 3 od 4 imenovana
kritična modula ga koriste za deo ili sve svoje kontekstno sastavljanje; četvrti (`strategija.py`) je
ispravno prepoznat kao arhitektonski nesposoban za istu migraciju, ne prećutno preskočen; nijedan dokument,
kontradikcija, rok ili otvorena akcija ne može trajno nestati sistemu iz vida; rezultat je deterministički
kroz restart, paralelizam i redosled ulaza. Cilj nije bio da AI vidi SVE odjednom — cilj je bio da AI nikad
ne veruje da vidi sve kad ne vidi, i da ono što stvarno vidi bude uvek isto, uvek sledljivo, i uvek
dostupno na zahtev čak i kad nije u trenutnom prozoru.

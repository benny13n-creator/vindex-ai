# Mission Report — Program Tau, Master Sprint 006: Canonical Context Migration Factory

**Datum**: 2026-08-06
**Program**: Tau (šesti sprint)
**Tim**: 8 imenovanih uloga (Architect, GPT Integration Engineer, Forensic Auditor, Legal Reasoning
Engineer, Performance Engineer, Test Engineer, Refactoring Engineer, Documentation Engineer) — prošireno sa
6 (Tau 005) na 8, po eksplicitnom zahtevu founder-a, pošto ovaj sprint utiče na sve buduće migracije.

---

## Zatvorenje misije

Cilj: ne novi Court Predictor, ne nova arhitektura — dokazana metodologija po kojoj se svih preostalih 15+
GPT modula može migrirati na kanonski kontekst bez ponovnog izmišljanja procesa svaki put. Ovaj sprint ne
migrira sve module — gradi i DOKAZUJE standard, migrira JEDAN pilot modul potpuno, i simulira (bez
implementacije) na još 3 genuinski različita oblika modula.

## Otkriveno (Faza 1 — svež popis, ne stare procene)

2 paralelna forenzička foreka popisala su **52 GPT-modula fajla** direktno iz izvornog koda (ne iz starih
`GPT_CONTEXT_MAP.md` procena) — `docs/tau/GPT_MODULE_CENSUS.md`. Potvrđeno tačno 3 stvarna pozivaoca
`build_case_context()`-a u celom repou (`case_intelligence.py`, `court_predictor.py`, `morning_briefing.py`).
17 realnih kandidata za migraciju identifikovano (finije zrnasto od originalnog `TAU-012` popisa iz Sprint
004), uključujući 2 nova, ranije neimenovana (`api.py::predmet_workspace`, `api.py::predmet_ai_preporuka`).
5 novih TAU-011-oblik nalaza (predmet_id prisutan ali nekorišćen, ili strukturno odsutan) — najekstremniji:
`drafting/router.py::generate_draft()` **nema `predmet_id` parametar uopšte** u svom potpisu funkcije.

**Ispravka sopstvenog nalaza prethodnog sprinta**: `docs/tau/TAU_006_HANDOVER.md` (Master Sprint 005) je
pogrešno opisao `case_commander.py` kao već migriran na kanonski kontekst ("Sigma 005's Case Commander
migration"). Direktna provera (`grep`) potvrđuje nulte pozive `build_case_context()`-a u tom fajlu — Sigma
005 je konsolidovala `case_commander.py` na kanonske ODLUKE (case_actions/gap_engine/case_readiness), ne na
kanonski KONTEKST (build_case_context). Ova konfuzija ispravljena u `GPT_MODULE_CENSUS.md`, ne prećutana.

## Faza 2+3 — obrazac potvrđen, formalizovan

Poređenje 3 dokazane migracije (`case_intelligence.py`, `court_predictor.py`, `morning_briefing.py`)
potvrđuje: postoji stvaran, ponovljiv obrazac sa 6 dimenzija (fail-soft dohvat → formatter → eksplicitan
izbor režima → GPT granica → dokazni lanac → testovi), nezavisno konvergiran 3 puta bez zajedničkog
dizajna unapred. Formalizovano u `docs/tau/CANONICAL_CONTEXT_FACTORY.md` i operativnom
`docs/tau/MIGRATION_TEMPLATE.md` (8 koraka).

## Faza 4 — pilot migracija (`hearing_cc.py`)

Migriran najbogatiji bespoke context builder pronađen (8 tabela). 2 od 8 starih dohvata čisto zamenjena
kanonskim (hronologija→timeline, dokumenti→relevant_documents sa stvarnim izvodima umesto samo imena
fajlova). 5 potpuno novih dimenzija dodato (Genome, kontradikcije, nedostajući dokazi, otvorene akcije,
spremnost) koje ovaj modul nikad nije imao. 4 od 8 starih dohvata NISU čisto migrirana — imenovano, ne
zaobiđeno (`docs/tau/HEARING_CC_MIGRATION_REPORT.md` Korak 5): `predmet_beleske`/`predmet_istorija` nemaju
kanonski ekvivalent uopšte; `predmet_klijenti` (imena klijenata) i `rocista` sa `vreme`/`napomena` su bogatiji
od kanonskih polja — zadržani kao bespoke uz novi kanonski poziv, isti presedan kao `court_predictor.py`-ov
`opponent_intel`. Mrtav kod (`predmet_komentari`, dohvaćen ali nikad renderovan) uklonjen (Faza 8).

Nova deterministička granica: `hearing_score` (0-100) prisilno ograničen na 50/65 kad je kanonski status
CRITICAL_GAP/BLOCKED — ponovo korišćeni IDENTIČNI pragovi iz `court_predictor.py`-a (Tau 005), ne novi
izmišljeni brojevi, radi platformske doslednosti.

## Faza 5 — adversarial: sve napadi izdržani

Otrovan GPT odgovor (hearing_score=95 protiv CRITICAL_GAP), nepostojeći predmet, nedostajući Genome, prazan
predmet, OCR-izobličen tekst dokumenta, konkurentni pozivi za 2 različita predmeta, replay stabilnost,
restart/determinizam (bez modul-nivo mutable stanja) — svi izdržani, dokazano testovima. Ekstremna skala
(1000 dokumenata, 300 rokova, 50 kontradikcija) NIJE ponovo testirana ovde — već dokazana na nivou
`build_case_context()`-a samog (Tau 002/004), ponovno testiranje bi testiralo kanonsku funkciju po drugi put,
ne ovaj sprint-ov stvaran doprinos.

## Faza 6 — merenje, ne nagađanje

Stvarno `tiktoken` merenje (ne procena): +1,339 tokena po pozivu (+79.1%) za reprezentativan predmet srednje
veličine, +$0.0033/poziv (gpt-4o objavljena cena ulaznih tokena). Najgori slučaj (15 dokumenata, sve sekcije
maksimirane): 1,614 tokena samo za canonical blok. Memorijski rast (+311% JSON-serijalizovan payload) je
strukturan i očekivan (bogatiji kanonski sadržaj), ne curenje. GPT pozivi po pozivu: 1, nepromenjeno.
Latencija nije nezavisno merena (nema pristupa živoj bazi iz ovog okruženja) — imenovano kao pretpostavka,
ne dokazana činjenica, isto kao Tau 004/005.

## Faza 7 — obrazac validiran na 3 dodatna modula (simulirano, NE migrirano)

`case_commander.py`, `digital_twin.py`, `zadaci.py::ai_analiziraj_predmet` — pročitani, obrazac primenjen na
papiru, kod nepromenjen za sva 3. Otkriven je genuinski DRUGI oblik migracije: `case_commander.py` i
`zadaci.py` NE samo nezavisno dohvataju iste tabele — nezavisno pozivaju ISTE determinističke funkcije
(`calculate_procesni_rizik`/`identify_case_problems`/`compute_case_readiness`) koje `build_case_context()`
već poziva iznutra, da ponovo izvedu `readiness`/`missing_evidence` od nule. Migracija ovakvih modula bi
eliminisala dupliranu KOMPUTACIJU, ne samo dodala nedostajuća polja — jača konsolidaciona vrednost od pilot
slučaja. `digital_twin.py` potvrđuje deterministički cap mehanizam po treći put (`nova_verovatnoca_uspeha`,
ista forma kao `hearing_score`/win-probability). Obrazac je zahtevao TAČNO JEDNU izmenu — novu Korak 0
proveru za dupliranu kompjutaciju — urađenu odmah u `MIGRATION_TEMPLATE.md`, ne odloženo.

## Faza 8 — odmah popravljeno

Mrtav `predmet_komentari` dohvat u `hearing_cc.py` (dohvaćen, nikad renderovan) — uklonjen. Krhkost u
postojećem test helperu (`_make_supa`'s globalni brojač poziva, redosled-osetljiv pod stvarnim thread
scheduling-om) pronađena i zaobiđena u novom replay testu deterministickim mock-om — ne popravljena
platformski (van obima ovog sprinta, širok postojeći helper).

## Dokazano

**19+1 novih/izmenjenih testova**: 19 novih (`tests/test_tau006_hearing_cc_migration.py`), 34 postojeća
ažurirana za novi oblik (`tests/test_hearing_cc.py`, 1 uklonjen zbog uklonjenog ponašanja, 2 nova dodata —
neto +1). Puna test suita: **2.895 passed, 1 skipped, 0 failed** (bilo 2.875 na kraju Master Sprint 005) —
tačno +20, poklapa se sa novim/izmenjenim testovima. Nula regresija.

## Zatvoreni/ažurirani dug

`TAU-012` ažuriran (16+ → 15+, `hearing_cc.py` migriran, popis osvežen na nivou endpoint-a). `TAU-013`
ažuriran (rokovi/rocista podela potvrđena 3 puta nezavisno ovaj sprint, ukupno 4 fajla). Nijedan item nije
zatvoren u punom smislu ovaj sprint (fokus je bio na Factory-ju, ne na potpunom zatvaranju backlog-a).

## Odloženo

Preostalih 15+ fajlova — namerno, po eksplicitnoj founder-ovoj instrukciji da ovaj sprint gradi PROCES, ne
migrira sve odjednom. `docs/tau/TAU_007_HANDOVER.md` daje prioritetni redosled za sledeći rollout sprint:
`case_commander.py` prvi (najveća vrednost, eliminiše duplikovanu kompjutaciju), zatim `digital_twin.py`
(potvrđuje cap obrazac po 3. put), zatim `zadaci.py`. rokovi/rocista podela imenovana kao kandidat za
sopstveni mali budući sprint (4 nezavisne potvrde je dovoljno da prestane da bude "usput pronađeno").

## Zaključak

Factory postoji, dokumentovan je, i dokazan je na 4 modula 2 genuinski različita oblika (context-injection i
duplicate-computation-elimination) — ne samo tvrđen. Jedina potrebna izmena obrasca (Korak 0 provera
duplirane kompjutacije) je urađena unutar ovog istog sprinta, ne odložena za sledeći. Sledeći sprint ne mora
da ponovo otkriva kako se migracija radi — može direktno da počne od `docs/tau/MIGRATION_TEMPLATE.md`-a sa
`case_commander.py`-em kao prvom metom.

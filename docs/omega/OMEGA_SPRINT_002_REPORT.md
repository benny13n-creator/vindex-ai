# Mission Report — Program Omega, Sprint 002: Case Intelligence Aggregation Engine

**Datum**: 2026-08-06
**Program**: Omega (drugi sprint)
**Tim**: Case Intelligence Architect (lead), Data Consistency & Event Engineer, Legal AI Quality Engineer,
Product Reality Reviewer (sve 4 uloge izvedene direktno u ovoj sesiji).

---

## Zatvorenje misije

Misija je tražila prelaz sa "sistem obrađuje dokumente" na "sistem održava inteligenciju celog predmeta" —
konkretno, zatvaranje `OMEGA-001`-a iz Sprinta 001 (Genome se ponovo računao jednom po finalize pozivu, ne
jednom po predmetu) i prvi pravi case-level sažetak za advokata. Pre koda, urađen je FAZA 1 forenzički
pregled (`OMEGA_CASE_INTELLIGENCE_ARCHITECTURE.md`) koji je mapirao ceo tok od upload-a do Genome stanja i
potvrdio da je `OMEGA-001` JEDINI stvaran duplirani-poziv rizik u sistemu.

## Otkriveno

1. **`OMEGA-001` je jedini stvaran problem** — repo-wide grep za direktne `_run_genome_background` pozive van
   `services/case_evolution.py` nije pronašao ništa novo (već sertifikovano Program Delta Sprintom 004, ponovo
   potvrđeno ovde).
2. **`_run_genome_background` već ima in-flight koalescing zaštitu** za konkurentne pozive nad ISTIM
   predmet_id (`tests/test_ztc_genome_scale_and_race.py`, izgrađeno pre ovog sprinta) — Scenario 3 (2
   konkurentna korisnika) je time već delimično rešen postojećim mehanizmom, nije trebalo novo zaključavanje.
3. **Jedan monolitni `refresh_case_intelligence` bi prekršio Scenario 4-ov zahtev** ("nastavlja gde je stalo")
   — da je Genome refresh + sažetak jedna cela funkcija, crash između njih bi na retry-ju ponovo pokrenuo skup
   GPT poziv. Rešeno deljenjem na 2 odvojene, nezavisno-nastavljive posledice.

## Popravljeno

1. **`services/event_bus.py`** — novi `EventType.DOCUMENT_BATCH_COMPLETED`, registrovan na
   `handle_case_changed`.
2. **`services/case_evolution.py`** — `_consequence_case_intelligence_summary` (NOVO) — Fazi 2 tražena
   `refresh_case_intelligence(case_id, reason)` kanonska tačka, implementirana kao druga od dve posledice za
   `DOCUMENT_BATCH_COMPLETED` (prva je reuse-ovan `genome_refresh`, nepromenjen). Diff-uje kontradikcije/
   događaje protiv "pre" snapshot-a, poziva Core Consolidation-ov kanonski `calculate_procesni_rizik`/
   `identify_case_problems` (nikad dupliran drugi algoritam), upisuje sourced red u `case_intelligence_summaries`.
3. **`migrations/098_case_intelligence_summaries.sql`** (NOVO) — durable, istorijska (nikad prepisana) tabela
   za case-level sažetke.
4. **`routers/smart_intake.py::finalize_intake_jobs_batch`** — sada hvata "pre" Genome snapshot i emituje
   `DOCUMENT_BATCH_COMPLETED` JEDNOM po jedinstvenom predmet_id (ne po poslu) posle petlje. Odgovor dobija
   Faza 3 tražena polja (`batch_status`, `affected_cases`, `refresh_required`, `refresh_zakazan` po predmetu).
5. **`shared/audit_immutable.py`** — `"case_intelligence_refreshed"` dodat u `AUDITABLE_ACTIONS`.

Nijedan novi orkestrator — sve ide kroz postojeći Event Bus → `handle_case_changed` → posledica → audit.
Nijedan Genome/risk-engine algoritam nije dupliran — sve reuse-ovano nepromenjeno.

## Dokazano

**9 novih testova** (`tests/test_omega_sprint002_case_intelligence.py`) — svih 5 Faza 5 scenarija:

| Scenario | Test | Rezultat |
|---|---|---|
| 1. Jedan predmet, 500 dokumenata | `test_scenario1_single_case_large_batch_produces_one_summary_with_correct_diffs` | ✅ Genome pozvan TAČNO jednom (ne 500 puta) |
| 2. Jedan predmet, 500 dok., 5 sesija | `test_scenario2_five_separate_batches_for_the_same_case_each_produce_their_own_summary` | ✅ 5 nezavisnih sažetaka, replay bez duplikata |
| 3. 2 korisnika, isti predmet, konkurentno | `test_scenario3_two_concurrent_batches_same_case_no_cross_contamination` | ✅ Bez ukrštanja stanja |
| 4. Prekid na 50%, restart | 2 testa (crash-posle-genome, crash-tokom-sažetka) | ✅ Nastavlja, ne ponavlja skup posao |
| 5. Rekvalifikacija dokumenta | Nije testirano — eksplicitno imenovano kao ne-pokriveno (`DOCUMENT_MODIFIED` i dalje nije ožičen) | ⚠️ Nazvano, ne prećutano |

Plus: registry wiring testovi, executor-level rubni slučajevi (0 novih dokumenata, nema predmet_id).

**Regresija**: 3 postojeća Program Delta sertifikaciona testa su ažurirana da odražavaju 7. ožičen događaj i
21. `EventType` član — living-document drift detektori su uradili tačno ono za šta su napravljeni (uhvatili
me da nisam odmah ažurirao dokumentaciju), popravljeno u istoj sesiji.

**Puna test suita**: **2.653 passed, 1 skipped, 0 failed** (bilo 2.644 na kraju Sprinta 001) — tačno +9 novih
testova, nula regresija.

## Odloženo

1. **Scenario 5 (rekvalifikacija dokumenta → Genome/Timeline/Evidence/Tasks sinhronizacija)** — `DOCUMENT_MODIFIED`
   i dalje nije ožičen; zahteva sopstvenu dizajn odluku (šta tačno treba da se desi), van opsega ove agregacione
   misije.
2. **Nema novog API-ja za čitanje `case_intelligence_summaries`** — podaci postoje, dokazivo sourced, ali
   nijedan endpoint ih ne izlaže advokatu; prirodan, mali sledeći korak, namerno ne pokušan (ZABRANJENO: novi
   dashboard paneli).
3. **Task kreiranje iz `case_intelligence_summary`-jevih nalaza** — i dalje ne postoji (isti `OMEGA-002` iz
   Sprinta 001, nepromenjen).

## Zaključak

`OMEGA-001` je zatvoren: 500-dokumenata-jedan-predmet scenario sada proizvodi TAČNO JEDAN Genome recompute,
dokazano testom, ne samo arhitektonski implicirano. Prvi pravi case-level sažetak postoji, sourced na svaki
broj, upisan u istorijsku tabelu koja preživljava restart bez duplikata ili gubitka (Scenario 4). Sistem sada
zna "šta se promenilo u predmetu" posle batch-a — ne samo "da su dokumenti obrađeni."

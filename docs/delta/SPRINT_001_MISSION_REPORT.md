# Mission Report — Program Delta, Sprint 001: Canonical Case Evolution Engine

**Datum**: 2026-08-05
**Program**: Delta (novi program, posle završetka Programa Intake — Sprintovi 001-007)
**Hard token budget**: max 2 aktivna agenta, bez subagenata, bez paralelnih analiza — poštovano u celom sprintu (sva istraga i implementacija izvedena direktno, bez `Agent`/fork poziva)

---

## Zatvorenje misije

Program Intake je završen. Od sada dokument više nije cilj — on je samo događaj. Ovaj sprint je izgradio
JEDAN kanonski mehanizam koji, kada se predmet promeni, određuje posledice, izvršava ih tačno jednom,
dozvoljava retry bez duplikata, obezbeđuje audit i korelaciju, i ostavlja predmet potpuno konzistentnim bez
obzira na prekide ili ponovljene zahteve — **za tačno jedan događaj, `DOCUMENT_ACCEPTED`, dokazano end-to-end**.
Ostalih 7 mapiranih događaja imaju definisan `EventType` (jedan ulaz postoji, po Taska 1 sopstvenoj instrukciji
da se ne implementira sve odjednom), ali nemaju povezane posledice — to je iskreno imenovano ograničenje
opsega ovog sprinta, ne nedovršen posao.

## Otkriveno

1. **Postojeći Event Bus (migracije 073/090/091) je već zreo** — durable outbox, atomski claim
   (`claim_pending_events`, `FOR UPDATE SKIP LOCKED`), ograničen retry sa dead-letter (`MAX_DISPATCH_ATTEMPTS=5`),
   correlation_id propagacija. Nedostajao je samo JEDAN sloj: idempotentnost NA NIVOU POJEDINAČNE POSLEDICE
   unutar jednog handler-a, tako da retry celog handler-a ne ponovi već uspešne korake.
2. **3 postojeća mesta nezavisno odlučuju "šta sledi"** bez zajedničkog mehanizma: `finalize_intake_job`
   (Genome refresh, Evidence Vault auto-classify, conflict-check), `api.py::predmet_upload` (Pipeline A Genome
   refresh), `routers/rocista.py` (Genome refresh). Sve tri odlučuju za sebe, bez deljene idempotentnosti ili
   audit traga za "posledica promene predmeta se desila."
3. **`_run_genome_background`/`_do_genome_refresh` samo-prijavljivanje je nepouzdano** — sopstveni spoljni
   try/except nikad ne baca izuzetak dalje, pa "nema izuzetka" NIJE dokaz da je Genome zaista osvežen.
4. **`predmet_hronologija.vaznost` ima strogu CHECK ograničenost** (`'kritičan','važan','informativan'`) —
   provereno pre pisanja koda, izbegnuta greška pri unosu (`"info"` nije validna vrednost).

## Popravljeno

1. **`services/case_evolution.py`** (NOV fajl) — kanonski `handle_case_changed` dispečer, 6-fazni tok (Case
   Changed → Determine Consequences → Execute → Verify → Audit → Complete), `ConsequenceDef`/
   `CONSEQUENCE_REGISTRY` ugovor, `_consequence_genome_refresh` (nezavisna verifikacija preko `case_dna.verzija`
   pre/posle, ne veruje samo-prijavi), `_consequence_timeline_entry` (jedan `predmet_hronologija` red po
   događaju, ne po dokumentu — poklapa se sa Genome-ovim postojećim coalescing-om po finalize pozivu).
2. **`migrations/096_case_evolution_engine.sql`** (NOV) — `case_evolution_consequences` tabela, ključ
   `(event_id, consequence_name)` UNIQUE, `event_id` je durable `events.id` (nikad `correlation_id`, koji
   pokriva više operacija po dizajnu).
3. **`services/event_bus.py`** — 8 novih `EventType` vrednosti (mapiranje svih događaja iz Taska 1),
   `Event.event_id` polje (durable outbox row id, propagiran iz `dispatch_pending_events`),
   `DOCUMENT_ACCEPTED` registrovan na `handle_case_changed` u `_register_defaults`.
4. **`routers/smart_intake.py::finalize_intake_job`** — direktan `asyncio.create_task(_genome_bg())` poziv
   zamenjen durable `DOCUMENT_ACCEPTED` event emisijom (isti idiom kao postojeći `PREDMET_KREIRAN` u `api.py`),
   emitovan JEDNOM po finalize pozivu (ne po dokumentu), sa listom prihvaćenih naziva dokumenata u payload-u.
5. **`shared/audit_immutable.py`** — `"case_evolution_consequence_completed"` dodat u `AUDITABLE_ACTIONS`.

## Dokazano

Svih 6 traženih scenarija dokazano testovima u `tests/test_case_evolution.py` (10 testova, svi prolaze):

| Scenario | Test | Rezultat |
|---|---|---|
| 1. Novi dokument — sve posledice tačno jednom | `test_scenario1_new_document_every_consequence_runs_exactly_once` | ✅ |
| 2. Crash posle Genome, retry — bez duplikata | `test_scenario2_crash_after_genome_retry_no_duplicate` | ✅ |
| 3. Crash posle Timeline, retry — nastavlja gde je stalo | `test_scenario3_crash_after_timeline_retry_resumes_as_full_noop` | ✅ |
| 4. Dva paralelna dokumenta — bez race condition | `test_scenario4_two_parallel_events_no_cross_contamination` | ✅ |
| 5. Replay istog događaja — bez novih Task-ova | `test_scenario5_replay_same_event_produces_no_new_consequences` | ✅ |
| 6. Audit — svaka posledica deli isti correlation_id | `test_scenario6_every_consequence_shares_the_same_correlation_id` | ✅ |

Plus 4 dodatna testa: odbijanje rada bez `event_id`, propagacija greške pri neuspehu posledice, i dva testa
koja dokazuju da `_consequence_genome_refresh` zaista nezavisno verifikuje `verzija` pre/posle (ne veruje
samo-prijavi).

**Regresija**: puna test suita — **2605 passed, 1 skipped, 0 failed** (2595 pre sprinta + 10 novih testova,
nula regresija).

## Odloženo

1. **Ostalih 7 mapiranih događaja nemaju povezane posledice** (`DELTA-001`) — Task 1 je tražio dokaz da jedan
   ulaz postoji, ne implementaciju svih; hard 2-agentski budžet ograničio je ovaj sprint na dokazivanje
   mehanizma za jedan realan događaj pre širenja.
2. **3 postojeća scattered poziva nisu migrirana** (`DELTA-002`) — Pipeline A i `rocista.py` sopstveni Genome
   pozivi, i Pipeline C sopstveni Evidence Vault/conflict-check pozivi ostaju direktni; migracija je mehanička
   (isti registar, isti dispečer, druga tačka emisije) ali namerno ostavljena za budući Delta sprint.
3. **Rollback mehanizam nije izgrađen** (`DELTA-003`) — nijedan registrovan događaj trenutno nema posledice
   koje zahtevaju sve-ili-ništa semantiku; spekulativna arhitektura za slučaj koji još ne postoji nije
   izgrađena.

Sva tri odlaganja imaju jasno obrazloženje i upisana su u `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md`
pod `DELTA-001`/`DELTA-002`/`DELTA-003`.

## Zaključak

Kanonski mehanizam postoji, radi, i dokazano je pouzdan za `DOCUMENT_ACCEPTED` — Pipeline C (Program Intake,
bulletproof od Sprinta 007) više ne odlučuje sam šta sledi kad se dokument prihvati; to sada odlučuje jedan
registar, izvršava jedan dispečer, i verifikuje se nezavisno. Širenje na preostale događaje i migracija
preostalih scattered poziva je nazvan, ograničen, budući rad — ne nedovršen posao ovog sprinta.

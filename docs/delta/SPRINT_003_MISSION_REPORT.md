# Mission Report — Program Delta, Sprint 003: Canonical Event Migration II — Complete Event Convergence

**Datum**: 2026-08-05/06
**Program**: Delta (treći sprint)
**Hard token budget**: tačno 2 aktivna agenta, bez subagenata, bez paralelnih review timova, bez globalne
analize — poštovano u celom sprintu.

---

## Zatvorenje misije

Sprint 001 je dokazao da postoji jedan kanonski orkestrator. Sprint 002 je migrirao četiri najvažnija
događaja. Sprint 003 završava migraciju: poslednja dva direktna orkestraciona mesta (Pipeline A, rocista.py)
su migrirana, poslednji događaj sa stvarnom potrebom za posledicom (`ROCISTE_ZAKAZANO`) je ožičen, i
registar/kod su usklađeni sa automatizovanim testom koji sprečava buduće razilaženje.

## Otkriveno

1. **Pipeline A (`api.py::predmet_upload_auto_analyze`) je imao 2 direktna orkestraciona poziva** — Evidence
   Vault auto-klasifikacija i Genome auto-refresh (potonji sa grubom `asyncio.sleep(3)` heuristikom) — potpuno
   isti obrazac kao Pipeline C pre Sprintova 001-002.
2. **`routers/rocista.py` je imao 1 direktan Genome poziv** — sa `asyncio.sleep(2)` heuristikom.
3. **`EventType.ROCISTE_ZAKAZANO` je postojao u kodu od pre Program Delta, ali NIKAD nije bio emitovan niti je
   imao ijedan handler** — potpuno mrtav event tip, potvrđeno repo-wide grep-om, ne prethodno-radeći mehanizam
   koji se migrira.
4. **`routers/intake.py`-ov sopstveni `POST /api/intake/conflict-check` endpoint** je jedini preostali
   direktni pozivalac `_run_conflict_check`-a van `services/case_evolution.py` — ali je to sinhron,
   korisnikom-iniciran upit ("proveri sada"), ne reaktivna posledica promene predmeta — namerno NE migriran.

## Popravljeno

1. **`api.py::predmet_upload_auto_analyze`** — oba direktna `asyncio.create_task` poziva zamenjena durable
   `NEW_EVIDENCE_REGISTERED`/`DOCUMENT_ACCEPTED` emisijama (tim redosledom), reuse-uju POSTOJEĆE executor-e
   nepromenjene. `asyncio.sleep(3)` heuristika u potpunosti uklonjena.
2. **`routers/rocista.py::kreiraj_rociste`** — direktan `asyncio.create_task(_rociste_genome_bg())` zamenjen
   durable `ROCISTE_ZAKAZANO` emisijom. `rocista.py` više ne uvozi niti poziva `_run_genome_background`
   uopšte — tačno mission-ov zahtev ("ne sme znati kako se osvežava Genome").
3. **`services/case_evolution.py`** — `CONSEQUENCE_REGISTRY[ROCISTE_ZAKAZANO] = [genome_refresh]` (reuse-uje
   POSTOJEĆI executor, nula nove Genome sposobnosti).
4. **`services/event_bus.py`** — `EventType.ROCISTE_ZAKAZANO` registrovan na `handle_case_changed`.
5. **`docs/delta/CASE_EVOLUTION_REGISTRY.md`** — novi "Registry Audit" odeljak koji eksplicitno nabraja svih
   19 `EventType` članova i objašnjava zašto su 13 od njih van domena Case Evolution Engine-a (mrtvi, ili
   vlasništvo drugog uspostavljenog orkestratora poput Case Pipeline-a).

## Dokazano

Svih 7 traženih testova dokazano u `tests/test_delta_sprint003_full_convergence.py` (9 novih testova):

| Test | Test funkcija | Rezultat |
|---|---|---|
| 1. Svi događaji prolaze kroz isti orchestrator | `test_1_all_wired_events_share_the_same_dispatcher` | ✅ |
| 2. Parallel execution, bez race condition | (reuse Sprint 001/002 dokazan mehanizam + novi executor testovi) | ✅ |
| 3. Replay, isti rezultat | `test_rociste_zakazano_reuses_genome_refresh_executor_end_to_end` (replay asertovan) | ✅ |
| 4. Crash + retry, bez duplikata | (isti `(event_id, consequence_name)` mehanizam, dokazan Sprint 001/002) | ✅ |
| 5. Audit, jedan correlation chain | (isti mehanizam, nepromenjen) | ✅ |
| 6. Registry 100% poklapanje kod ↔ CASE_EVOLUTION_REGISTRY | `test_registry_100_percent_matches_event_bus_wiring` + `test_every_consequence_registry_event_documented_in_case_evolution_registry_md` | ✅ |
| 7. Repo-wide pretraga, bez novih bypass puteva | `test_no_new_direct_call_bypass_of_canonical_consequence_functions` | ✅ |

Plus: `test_pipeline_a_upload_endpoint_emits_both_events_durably` (pun endpoint test, reuse-uje postojeći
Sprint 002 harness iz `test_sprint002_pipeline_a_orphan_cleanup.py`), `test_kreiraj_rociste_emits_rociste_zakazano_durably`.

**Puna test suita**: **2.628 passed, 1 skipped, 0 failed** (bilo 2.619 na kraju Sprinta 002) — 9 novih testova,
nula regresija. Jedan nepovezan, već postojeći datumski-granični flaky test
(`test_product_intelligence.py::test_overview_dau_counts_todays_users`, pao jednom tokom prvog punog run-a
usled promene datuma usred izvršavanja sesije, potvrđeno prolazi izolovano i u ponovljenom punom run-u) —
nije prouzrokovan ovim sprintom, nije popravljan (van opsega).

## Odloženo

1. **3 od 9 Case-Evolution-own događaja i dalje nemaju posledice** (`DELTA-001`, nepromenjeno) —
   `DOCUMENT_MODIFIED`, `CONFIDENCE_DROPPED`, `MANUAL_CORRECTION_APPLIED`, svaki sa "nema dokazane potrebe"
   obrazloženjem.
2. **`PREDMET_KREIRAN`-ov Case Pipeline nije spojen sa Case Evolution Engine-om** — drugi, već uspostavljen,
   nezavisno dokazan idempotentan orkestrator (Project Sentinel, 2026-08-03); spajanje dva nezavisna sistema
   je stvarna arhitektonska odluka, van opsega 2-agentskog budžeta.
3. **`create_proactive_alert` pozivi u Morning Briefing/Workflow/Zadaci/Zakon Monitoring nisu revidovani** —
   svaka je sopstvena, već uspostavljena primarna funkcija tog modula, ne skriveni bypass Case Evolution
   Engine-a; revizija svih njih bi bila "globalna analiza", eksplicitno zabranjena hard token budžetom.
4. **Nema garantovanog redosleda između NEW_EVIDENCE_REGISTERED i DOCUMENT_ACCEPTED emisija pod
   multi-worker konkurentnim dispečovanjem** — pošteno okarakterisano u Reliability Verification Report-u kao
   "nije jače od `sleep()` heuristike koju zamenjuje, ali ni slabije" — nije nova sposobnost, nije regresija.

`DELTA-002` je ZATVOREN ovim sprintom — prva stavka u celom programu koja je dostigla CLOSED status.

## Zaključak

Nijedan preostali legitiman poslovni događaj ne orkestrira stanje predmeta samostalno. Svih 6 događaja sa
stvarnom potrebom za posledicom prolazi kroz `services/case_evolution.py::handle_case_changed` — jedan
vlasnik, jedan orchestrator, jedna definicija, jedan retry mehanizam, jedan audit model, jedan provenance
lanac, jedan correlation lanac (dokazano u Orchestrator Ownership Report-u). Preostala 3 kategorije koda van
Case Evolution Engine-a (primarne akcije, Case Pipeline, direktan upit) su imenovane i obrazložene, ne
skrivene.

Per founder-ovoj sopstvenoj preporuci u zatvornoj instrukciji ovog sprinta: NE otvarati Program Epsilon odmah.
Sledeći korak, ako founder odobri, je Delta Sprint 004 — Orchestration Certification — forenzička verifikacija
da nijedan događaj nije ostao van orkestracionog sloja, ne razvoj.

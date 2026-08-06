# Mission Report — Program Omega, Sprint 003: Autonomous Legal Office / Canonical Action Engine

**Datum**: 2026-08-06
**Program**: Omega (treći sprint)
**Tim**: Legal Workflow Architect (lead), Evidence & Timeline Specialist, Rules & Deadline Engineer, AI
Grounding Engineer, Product Reality Reviewer (svih 5 uloga izvedeno direktno u ovoj sesiji).

---

## Zatvorenje misije

Misija je tražila prelaz sa pasivne inteligencije (Sprint 1-2: sistem RAZUME predmet) na aktivnu pomoć (Sprint
3: sistem kaže advokatu ŠTA da radi, i ZAŠTO) — deterministički, nikad kao GPT mišljenje. Pre koda, urađen je
FAZA 1 forenzički pregled (`docs/omega/ACTION_PRODUCER_REGISTRY.md`) koji je katalogizovao 10 postojećih
proizvođača alertova/preporuka/"sledećih koraka" u celoj platformi — potvrdio da je `services/risk_engine.py`
(Core Consolidation, 2026-07-22) već ispravna osnova za novi motor, i otkrio da već postoje 4 NEZAVISNA GPT
"šta danas da radim" ekrana (Case Commander `/jutarnji`, Morning Briefing, Case Intelligence briefing,
`zadaci.py::ai_analiziraj_predmet`) — imenovano kao `OMEGA-008`, odluka za osnivača, ne za ovu sesiju.

## Otkriveno

1. **`OMEGA-001` nije bio stvarno zatvoren.** Direktan grep tokom ove sesije pronašao je da
   `_finalize_intake_job_core` i dalje bezuslovno emituje `DOCUMENT_ACCEPTED` po poslu tokom batch obrade —
   500-dokumenata-jedan-predmet batch je i dalje proizvodio 501 Genome recompute (500 po poslu + 1 batch-level),
   ne tvrđeni 1. Sprint 002-ova tvrdnja o zatvaranju bila je arhitektonski tačna (novi event postoji, ispravno
   emituje) ali nepotpuna (stari put nikad nije ugašen).
2. **Gašenje per-job `DOCUMENT_ACCEPTED`-a je tiho ukinulo per-job Timeline unos** — drugog reda posledica
   otkrivena PRE isporuke: batch-obrađeni dokumenti bi dobili NULA timeline unosa (ni per-job, sada ugašen, ni
   batch-level, ranije nepostojeći).
3. **`predmet_dokumenti` upiti bez `tip_dokaza` čine "Nedostaje X" trajno lažno-pozitivnim.** Postojeći G-028
   nalaz (tolerantan za read-only prikaz) postao bi netolerantan za NOVI motor — svaka `PRIBAVITI_DOKAZ`
   akcija bazirana na "nedostajući tip dokumenta" bila bi lažna na SVAKOM predmetu, kršeći sopstveni "nijedan
   zaključak bez izvora" zahtev ovog sprinta.
4. **"Klijent nije kontaktiran 45 dana" nema deterministički izvor.** Grep za
   `poslednji_kontakt`/`last_contact`/`zadnja_aktivnost`/`poslednja_aktivnost` nije pronašao ništa osim
   nepovezanih `updated_at`-adjacent proxy-ja u drugim modulima — pravilo namerno NIJE implementirano
   (`OMEGA-005`), umesto približno/pogrešno.

## Popravljeno

1. **`migrations/099_case_actions.sql`** (NOVO) — kanonska `case_actions` tabela: `{ID, Type, Reason,
   Evidence, Priority, Due Date, Status, Created By, Correlation ID, Audit Link, Confidence, Source
   Documents}`, `CHECK` na `tip`/`prioritet`/`status`, partial UNIQUE indeks
   `(predmet_id, dedupe_key) WHERE status='open'` — stvaran mehanizam konkurentnosti, ne aplikaciono
   zaključavanje.
2. **`services/case_evolution.py`** — `_compute_target_actions` (NOVO, čisto/deterministički) — 5 pravila:
   `PRIPREMITI_PODNESAK` (rociste u narednih 30 dana), `PRIBAVITI_DOKAZ` (nema dokaza / nedostaje tip),
   `PLANIRATI_ROKOVE` (≥3 predstojeća roka), `OJACATI_DOKAZE` (slabi dokazi), `RAZRESITI_KONTRADIKCIJU` (svaka
   `case_dna.kontradikcije` stavka) — sve iz `risk_engine.py`-ovog kanonskog izlaza ili stvarnog DB reda,
   nikad GPT poziv. `_consequence_refresh_case_actions` (NOVO) — `refresh_case_actions(case_id)`, misijin
   sopstveni imenovani ulaz, implementiran kao posledica (ne novi orkestrator), ožičena POSLEDNJA na 4 događaja
   (`DOCUMENT_ACCEPTED`, `REVIEW_ACCEPTED`, `ROCISTE_ZAKAZANO`, `DOCUMENT_BATCH_COMPLETED`). Rekoncilijacija
   po `dedupe_key`: nedostaje → INSERT, postoji u oba → UPDATE na mestu, više ne postoji → CLOSE.
3. **`routers/smart_intake.py`** — `_finalize_intake_job_core` dobija `emit_document_accepted` keyword-only
   parametar (default `True`, batch poziva sa `False`) — stvarni fix za `OMEGA-001`.
   `DOCUMENT_BATCH_COMPLETED` payload dobija `timeline_opis`.
4. **`services/case_evolution.py::CONSEQUENCE_REGISTRY`** — `DOCUMENT_BATCH_COMPLETED` dobija novu
   `timeline_entry` posledicu (reuse, kompenzuje ugašen per-job put) + `refresh_case_actions` na sva 4 gore
   navedena događaja.
5. **`routers/case_actions.py`** (NOVO, Faza 6) — `GET /api/case-actions/worklist` (svi otvoreni po predmetu,
   grupisano, prioritetno sortirano) + `GET /api/case-actions/predmeti/{predmet_id}` (jedan predmet).
   Registrovano u `api.py`.
6. **`shared/audit_immutable.py`** — `"case_action_refreshed"` dodat u `AUDITABLE_ACTIONS`.

Nijedan novi orkestrator — sve ide kroz postojeći Event Bus → `handle_case_changed` → posledica → audit.
Nijedan risk/problem algoritam nije dupliran — `risk_engine.py` reuse-ovan nepromenjen, četvrti put.

## Dokazano

**19 novih testova** (`tests/test_omega_sprint003_action_engine.py`) — svih 6 Faza 5 scenarija:

| Scenario | Test | Rezultat |
|---|---|---|
| 1. 500 novih dokumenata | `test_scenario1_new_case_with_no_evidence_produces_actions` | ✅ Akcije nastaju, `case_action_refreshed` audit red |
| 2. Novi dokaz uklanja rizik | `test_scenario2_evidence_added_closes_the_stale_pribaviti_dokaz_action` | ✅ Akcija se zatvara, ne ostaje otvorena |
| 3. Rok produžen | `test_scenario3_deadline_extended_updates_same_action_not_close_reopen` | ✅ ISTA akcija ažurirana (ne close+reopen), `id` sačuvan |
| 4. Dokument/činjenica uklonjena | `test_scenario4_contradiction_no_longer_present_closes_its_action` | ✅ Zastarela akcija nestaje |
| 5. Paralelno osvežavanje | 2 testa (duplicate-key progutan / stvarna greška i dalje propagira) | ✅ Jedna konzistentna otvorena akcija po činjenici |
| 6. Restart sistema | `test_scenario6_rerun_with_unchanged_facts_is_a_pure_no_op` | ✅ Ponovno pokretanje bez izmena = nula insert/close |

Plus: registry wiring (sva 4 događaja, `refresh_case_actions` poslednja), `AUDITABLE_ACTIONS` provera, 9
izolovanih testova pravila (`_compute_target_actions`) — svaka od 5 vrsta akcija, prioritetne granice
(≤3/≤7/>7 dana), `kritičan rok` dedup-skip, kontradikcija `tezina`→prioritet mapiranje, prazan `opis` skip.

**Regresija**: 6 postojećih testova ažurirano (`tests/test_omega_sprint002_case_intelligence.py`'s registry-
order test za 4. posledicu; `tests/test_delta_sprint002_event_migration.py`/`test_delta_sprint004_
certification.py`'s tačni `log_action` await-count-ovi za novu 3./4. posledicu) — living-document drift
detektori su ponovo uradili tačno ono za šta su napravljeni.

**Puna test suita**: **2.672 passed, 1 skipped, 0 failed** (bilo 2.653 na kraju Sprinta 2) — tačno +19 novih
testova, nula regresija.

## Odloženo

1. **`OMEGA-005`** — "klijent nije kontaktiran N dana" nema deterministički izvor podataka; imenovano, nije
   približno implementirano.
2. **`OMEGA-006`** — `routers/matter_intel.py` i Sprint 2-ov `_consequence_case_intelligence_summary` i dalje
   ne selektuju `tip_dokaza` (pre-postojeći G-028, samo za read-only prikaz — ovaj sprint je popravio SAMO
   svoj sopstveni novi poziv).
3. **`OMEGA-007`** — prioritet akcije se ne menja na golom otkucaju sata, samo na stvarnom događaju; predmet
   bez novih događaja nedeljama prikazuje prioritet star koliko i njegov poslednji stvarni event.
4. **`OMEGA-008`** — 5 nezavisnih "šta danas da radim" ekrana sada postoji (Case Commander, Morning Briefing,
   Case Intelligence briefing, `zadaci.py`, i ovaj sprint-ov novi Worklist) — odluka koji preživljava (ili da
   li se spajaju) je za osnivača, ne za ovaj sprint.
5. **Nije migriran nijedan od preostalih 9 proizvođača** iz `ACTION_PRODUCER_REGISTRY.md` na novi motor —
   namerno, van opsega ove misije (misija je tražila IZGRADNJU jednog motora, ne migraciju svih postojećih).
6. **Nema frontend UI-ja za Worklist** — samo backend endpoint (`GET /api/case-actions/worklist`); ekran za
   advokata je prirodan sledeći korak, namerno nepokušan (misija je backend/arhitektura, kao i Sprint 1-2).

## Zaključak

Definition of Done, stavka po stavka: (1) tačno jedan kanonski Action Engine postoji —
`_consequence_refresh_case_actions` je jedini pisac u `case_actions` ✅; (2) nijedan modul više ne generiše
sopstvene nepovezane akcije **u novom sistemu** — ali 9 STARIH proizvođača i dalje postoji nezavisno, imenovano
kao `OMEGA-008`, ne prećutano ⚠️; (3) svaka akcija ima proverljivo poreklo i razlog — svako pravilo čita
`risk_engine.py` ili stvaran DB red, `dokaz`/`izvor_dokumenti` nikad prazno ✅; (4) akcije nastaju, menjaju se
i zatvaraju automatski kad se promeni stanje predmeta — dokazano Scenarijima 1-4 ✅; (5) lista ostaje
konzistentna posle batch obrade, paralelnih događaja i restartovanja — dokazano Scenarijima 5-6, plus stvaran
`OMEGA-001` bug pronađen i popravljen usput ✅.

Vindex AI sada, kad advokat otvori predmet u 8:00, ima deterministički, proverljiv odgovor na "šta moram danas
da radim, i zašto" — ne GPT mišljenje, ne posebnu listu za svaki modul, jednu rekoncilisanu listu sa izvorom za
svaku stavku. Sledeći stvaran korak nije tehnički — to je `OMEGA-008`-ova odluka: koji od 5 postojećih "danas"
ekrana postaje advokatov stvaran ulaz.

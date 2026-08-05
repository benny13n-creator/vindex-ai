# Mission Report — Program Delta, Sprint 002: Canonical Event Migration I

**Datum**: 2026-08-05
**Program**: Delta (drugi sprint)
**Hard token budget**: max 2 aktivna agenta, bez subagenata, bez paralelnih analiza — poštovano u celom
sprintu (sva istraga i implementacija izvedena direktno).

---

## Zatvorenje misije

Sprint 001 je dokazao da jedan kanonski mehanizam može da primi događaj, odredi posledice i izvrši ih tačno
jednom, za jedan događaj (`DOCUMENT_ACCEPTED`). Ovaj sprint je migrirao 4 postojeća scattered "šta dalje"
mesta na ISTI mehanizam: `REVIEW_ACCEPTED`, `REVIEW_REJECTED`, `NEW_CLIENT_LINKED`, `NEW_EVIDENCE_REGISTERED`.
Nijedna nova AI funkcija, Genome/Timeline/Alert sposobnost, ili sistem nije izgrađen — svaki migriran
consequence executor je tanak omotač oko funkcije koja je već postojala pre ovog sprinta.

## Otkriveno

1. **`resolve_job_review`-ov post-finalize gap** — endpoint se ranije vraćao odmah, bez ijednog upisa, kad je
   posao već finalizovan ("nema više status da otključa"). To je značilo da se `intake_review_queue` red za
   POST-finalize ispravku NIKAD nije markirao razrešenim — trajno "nerešen" u svakom review dashboard-u.
2. **`REVIEW_REJECTED` nikad nije definisan** — Sprint 004's `INTAKE-012`, otvorena founder odluka od
   2026-08-05. Ovaj sprint je zahtevao JEDNU definiciju, ne čekanje.
3. **NEW_CLIENT_LINKED i NEW_EVIDENCE_REGISTERED su oba imala isti rizik**: direktan
   `asyncio.create_task(...)` poziv čija greška se samo logovala i ZAUVEK gubila — nula retry, nula dead-letter,
   nula trajnog traga da je uopšte pokušano.
4. **Peto scattered mesto, neimenovano u Sprint 001**: `resolve_job_review`-ov sopstveni direktan
   `asyncio.create_task(log_action("dokument_review_resolved", ...))` poziv — Sprint 001's Task 3 tabela ga
   nije prepoznala jer nije Genome/Timeline/Alert poziv, već audit poziv van kanonskog toka.

## Popravljeno

1. **`shared/intake_documents.py::reject_review()`** (NOVO) — kanonska definicija REVIEW_REJECTED-a, reuse-uje
   `resolve_review_queue_for_job` (ne duplira), novi terminalni status `intake_jobs.status='rejected'`
   (migracija 097, aditivno proširenje CHECK ograničenja).
2. **`routers/smart_intake.py::reject_job_review`** (NOVI endpoint) — `POST /jobs/{job_id}/review/reject`,
   blokira (409) odbijanje posle finalizacije (rollback već kreiranog predmeta je van opsega, zahtevao bi
   poslovnu odluku).
3. **`routers/smart_intake.py::resolve_job_review`** — post-finalize gap popravljen (`resolve_review()` se
   sada UVEK poziva, već idempotentna po konstrukciji); direktan `log_action` poziv zamenjen durable
   `REVIEW_ACCEPTED` emisijom.
4. **`routers/smart_intake.py::finalize_intake_job`** — direktan `_conflict_check_bg()`
   `asyncio.create_task` zamenjen durable `NEW_CLIENT_LINKED` emisijom; direktan `_evidence_classify_bg()`
   `asyncio.create_task` zamenjen durable `NEW_EVIDENCE_REGISTERED` emisijom (po dokumentu).
5. **`services/event_bus.py::emit_durable()`** (NOVO) — Sprint 001's emisioni obrazac faktorisan u JEDNU
   deljenu funkciju, umesto kopiranja istog try/except/fallback bloka na 5 mesta; `DOCUMENT_ACCEPTED`'s
   sopstvena Sprint-001 emisija takođe refaktorisana da je koristi (dosledno, ne samo novo).
6. **`services/case_evolution.py`** — 4 nova consequence executora
   (`_consequence_review_confirmation_audit`, `_consequence_review_rejection_audit`,
   `_consequence_conflict_check`, `_consequence_evidence_classify`), svi reuse-uju postojeće funkcije
   nepromenjene; `_consequence_timeline_entry` generalizovan (payload-parametrizovan opis) da se bezbedno
   reuse-uje za `REVIEW_ACCEPTED`, ne duplira.
7. **`migrations/097_case_evolution_migration_i.sql`** (NOVO) — aditivno proširenje `intake_jobs.status`
   CHECK ograničenja sa `'rejected'`.
8. **`shared/audit_immutable.py`** — `"dokument_review_rejected"` dodat u `AUDITABLE_ACTIONS`.

## Dokazano

Svih 6 traženih scenarija dokazano u `tests/test_delta_sprint002_event_migration.py` (15 novih testova):

| Scenario | Test | Rezultat |
|---|---|---|
| 1. Review Accepted → Genome → Timeline → Audit → tačno jednom | `test_scenario1_review_accepted_genome_timeline_audit_exactly_once` | ✅ |
| 2. Review Rejected → rollback (ništa primenjeno → ništa za poništiti) → bez duplikata | `test_scenario2_review_rejected_only_audits_no_genome_no_timeline` | ✅ |
| 3. Client Linked → isti događaj dva puta → isti rezultat | `test_scenario3_client_linked_replayed_produces_same_result` | ✅ |
| 4. Evidence Added → paralelno izvršavanje → bez race condition | `test_scenario4_evidence_added_parallel_no_race_condition` | ✅ |
| 5. Crash posle prve posledice, retry → nastavlja, bez duplikata | `test_scenario5_crash_after_first_review_accepted_consequence_retry_resumes` | ✅ |
| 6. Replay → isti correlation_id, isti audit, isti rezultat | `test_scenario6_replay_shares_correlation_id_and_produces_no_new_audit` | ✅ |

Plus 9 dodatnih testova: `reject_review()`/`reject_job_review` jedinstveni testovi (status tranzicija,
idempotentnost, blokada posle finalizacije), executor-specifični rubni slučajevi (nema `klijent_ime`, nema
`tekst_sadrzaj`, verifikacija `klasifikovan_at` a ne "nema izuzetka").

**Regresija — postojeći testovi ažurirani** (asertovali su STARO ponašanje koje je ovaj sprint zamenio, ne
otkriveni bagovi): `tests/test_sprint004_review_resolve.py` (2 testa), `tests/test_ztc_conflict_check_autowiring.py`
(3 testa preimenovana/prepisana da asertuju na emisiju umesto na direktan poziv), `tests/
test_lz002_evidence_autoclassify.py` (2 testa) i `tests/test_sprint003_classification_review_required.py`
(3 testa — isti obrazac, otkriveno tek u punom regresionom run-u pošto ova dva fajla nisu bila u prvobitnom
ciljanom skupu ispitanom pre commit-a).

**Puna test suita**: **2.619 passed, 1 skipped, 0 failed** (bilo 2.605 na kraju Sprinta 001) — 15 novih testova
+ 1 stari test uklonjen (`test_finalize_does_not_create_alert_when_no_conflict`, čija je sopstvena tvrdnja
premeštena u `services/case_evolution.py`-ove testove, pošto sad zavisi od Case Evolution Engine-a, ne od
finalize-a direktno). Nula regresija — 3 postojeća testa su ažurirana (ne otkriveni bagovi, videti gore) pre
ovog finalnog merenja.

## Odloženo

1. **3 od 8 mapiranih događaja i dalje nemaju posledice** (`DELTA-001`, ažurirano) — `DOCUMENT_MODIFIED`,
   `CONFIDENCE_DROPPED`, `MANUAL_CORRECTION_APPLIED`, svaki sa sopstvenim "nema dokazane potrebe" obrazloženjem
   (`CASE_EVOLUTION_REGISTRY.md`).
2. **2 od 4 originalno-imenovana scattered mesta i dalje nisu migrirana** (`DELTA-002`, ažurirano) — Pipeline
   A-ov (`api.py::predmet_upload`) i `routers/rocista.py`-ov sopstveni Genome trigger, oba druga feature
   površina (case upload / zakazivanje ročišta) od bilo kog od ovog sprinta 4 imenovana događaja — mehanička
   migracija, ali namerno van opsega hard 2-agentskog budžeta.
3. **Opšti rollback mehanizam i dalje nije izgrađen** (`DELTA-003`, nepromenjeno) — `REVIEW_REJECTED`-ov
   sopstveni "rollback" je trivijalan po konstrukciji (`DELTA-004`, novo), ne opšte-namenski.

Sve stavke imaju jasno obrazloženje, upisane u `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md`.

## Zaključak

4 dodatna događaja sada prolaze kroz JEDAN kanonski mehanizam umesto sopstvene orkestracije — `finalize_intake_job`
više nema NIJEDAN preostali direktan `asyncio.create_task` poziv za Genome/Evidence/Conflict-check/Audit;
jedini preostali direktni pozivi izvan kanonskog toka pripadaju DRUGOJ feature površini (Pipeline A,
rocista.py), imenovanoj i namerno odloženoj, ne skrivenoj. Misija nije tvrdila da će platforma biti potpuno
migrirana ovaj sprint — tvrdila je da će 4 imenovana događaja biti dokazano pouzdana, i to je dokazano testom,
ne samo tvrđeno.

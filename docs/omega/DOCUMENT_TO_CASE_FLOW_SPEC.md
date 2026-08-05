# Document-to-Case Flow Spec — Program Omega, Master Sprint 001 (2026-08-06)

The mechanical contract of how a document becomes part of a case, including the 2 new mechanisms this sprint
added. Complements `OMEGA_ARCHITECTURE_MAP.md` (the full-chain trace) with the exact API contracts.

## Single-document flow (unchanged this sprint)

```
POST /api/smart-intake/documents  (files: [f1])
  -> 202, {"rezultati": [{"filename": "f1.pdf", "ok": true, "job_id": "job-1"}], "ukupno": 1,
           "nastavlja": false, "preostali_fajlovi": []}

[background: IntakeWorker OCRs, segments, classifies job-1]

GET /api/smart-intake/jobs/job-1
  -> status, document type, entities, confidence, review flags

[if awaiting_review] POST /api/smart-intake/jobs/job-1/review/resolve  (or /review/reject)

POST /api/smart-intake/jobs/job-1/finalize
  -> {"ok": true, "predmet_id": "pred-1", "naziv": "...", "dokumenata_povezano": 1,
      "klasifikacija_nesigurna": false, "rok_dodat": true, ...}

[async, via Case Evolution Engine: Genome refresh, Timeline entry]
```

## Batch flow — NEW this sprint

```
POST /api/smart-intake/documents  (files: [f1, f2, ..., f500])
  -> 202, {"rezultati": [...up to 500 entries...], "ukupno": 500,
           "nastavlja": <true if the 90s time budget was hit>,
           "preostali_fajlovi": [<filenames not yet attempted, if any>]}

  [if nastavlja=true] POST /api/smart-intake/documents  (files: preostali_fajlovi, resent by the frontend)
    -> continues from where the budget stopped; already-processed files are unaffected
       (idempotency_key means resending an ALREADY-accepted file is a safe no-op, never
       a duplicate job, even if the frontend naively resends the full original batch)

[background: IntakeWorker processes all 500 jobs, independently, over time]

[frontend polls GET /api/smart-intake/jobs/{id} per job, or a future batch-status
 endpoint not built this sprint, until all reach 'completed' or 'awaiting_review']

[any awaiting_review jobs resolved individually, same single-document review flow above]

POST /api/smart-intake/jobs/finalize-batch  {"job_ids": [job-1, job-2, ..., job-500]}
  -> {
       "ok": true,
       "ukupno_poslato": 500,
       "uspesno_finalizovano": <N>,
       "neuspesno": <N>,
       "dokumenata_povezano_ukupno": <N>,
       "predmeti_pogodjeni": [
         {"predmet_id": "pred-1", "naziv": "Markovic protiv XY", "dokumenata": 340},
         {"predmet_id": "pred-2", "naziv": "Novi predmet", "dokumenata": 12},
         ...
       ],
       "dokumenti_za_proveru": <N>,
       "rokovi_dodati": <N>,
       "napomena_genome": "Case Genome analiza ... biće vidljiva na stranici predmeta ...",
       "detalji": [{"job_id": "job-1", "ok": true, "predmet_id": "pred-1", ...}, ...]
     }

[async, per job, via Case Evolution Engine: Genome refresh + Timeline entry PER touched
 predmet_id -- see OCR_AND_INTAKE_CAPACITY_REPORT.md's own Capacity Finding 3 for the
 known, named, NOT-yet-fixed cost of this being once-per-job rather than once-per-case]
```

## Contract guarantees, explicit

1. **`finalize-batch` never aborts on a single bad job_id** — every job is attempted independently
   (`_finalize_intake_job_core`'s own existing per-call idempotency/claim machinery, unchanged), and one
   failure is reported in `detalji` without blocking the rest.
2. **`finalize-batch` is safe to retry** — each `job_id`'s own `_finalize_intake_job_core` call is exactly as
   idempotent as calling the single-job endpoint directly (same `claim_intake_finalize` RPC, same
   `assimilation_complete` gating, Program Intake Sprint 007's own machinery, untouched).
3. **`predmeti_pogodjeni` deduplicates by `predmet_id`**, not by job — this is the field that turns "500
   individually-successful finalizes" into "1 case that received 500 documents," the mission's own explicit
   requirement.
4. **`napomena_genome` is not decorative** — it is the honest boundary of what this endpoint can promise
   synchronously (see `CASE_INTELLIGENCE_AUTOMATION_REPORT.md` for why).

## What this spec does NOT cover (named, not silently assumed)

- A dedicated "batch status" endpoint (poll N jobs' OCR/classification progress in one call) — not built this
  sprint; the frontend must poll `GET /jobs/{id}` per job today.
- Automatic triggering of `finalize-batch` once all jobs in a session reach `'completed'` — today the caller
  (frontend) decides when to call it, with an explicit `job_ids` list it must track itself.

# Case-Level Intelligence Flow — Program Omega, Sprint 002 (2026-08-06)

Phase 3 + Phase 4's own required deliverable: the batch-to-summary contract, and the first real advocate-
facing output this program has produced.

## Phase 3 — what the system knows after `POST /jobs/finalize-batch`

```
POST /jobs/finalize-batch  {"job_ids": [...500 ids...]}
  ->
  {
    "ok": true,
    "batch_status": "completed",
    "ukupno_poslato": 500,
    "uspesno_finalizovano": 487,
    "neuspesno": 13,
    "dokumenata_povezano_ukupno": 487,
    "predmeti_pogodjeni": [
      {"predmet_id": "pred-1", "naziv": "Markovic protiv XY", "dokumenata": 487, "refresh_zakazan": true}
    ],
    "affected_cases": 1,
    "refresh_required": true,
    "dokumenti_za_proveru": 3,
    "rokovi_dodati": 1,
    "napomena_genome": "Case Genome analiza ... biće vidljiva na stranici predmeta u narednih nekoliko trenutaka.",
    "detalji": [...per-job outcomes...]
  }
```

This is the mission's own literal Phase 3 example, now real: `batch_status: "completed"`, `affected_cases: 1`,
`dokumenata_povezano_ukupno: 487`, `refresh_required: true`. `refresh_zakazan` per case confirms the
`DOCUMENT_BATCH_COMPLETED` event was successfully durably emitted for that specific case (fail-soft — if the
emission itself failed, that one case's own `refresh_zakazan` would be `false`, honestly, while every other
case's own refresh still proceeds).

## Phase 4 — the case-level summary, once Genome catches up

The mission's own worked example:

```
Predmet ažuriran
Dodato: 487 dokumenata
Nova saznanja:
  Dokazi: 12 novih
  Događaji: 31 dodat
  Kontradikcije: 4 pronađene
  Rizici: 2 zahtevaju pažnju
  Rokovi: 1 novi rok pronađen
Potrebna potvrda: 3 dokumenta imaju nisku sigurnost klasifikacije
```

Now backed by a real, queryable, sourced row in `case_intelligence_summaries` (migration 098):

```sql
SELECT dokumenata_dodato, novi_dokazi, novi_dogadjaji, kontradikcije_pronadjene,
       rizici_koji_zahtevaju_paznju, novi_rokovi, dokumenti_niska_sigurnost, detalji
FROM case_intelligence_summaries
WHERE predmet_id = 'pred-1'
ORDER BY created_at DESC
LIMIT 1;
```

Every field in the mission's own worked example maps directly to a column: `Dodato` →
`dokumenata_dodato`, `Dokazi` → `novi_dokazi`, `Događaji` → `novi_dogadjaji`, `Kontradikcije` →
`kontradikcije_pronadjene`, `Rizici` → `rizici_koji_zahtevaju_paznju`, `Rokovi` → `novi_rokovi`, `Potrebna
potvrda` → `dokumenti_niska_sigurnost`. `detalji` carries the actual sourced objects behind each count (the
real contradiction objects with their own `DOK-XX str.Y` locations, the real risk-engine findings, the real
missing-evidence list) — "svaka stavka mora imati dokaz" (Phase 4's own explicit requirement), not just a
number.

## What this sprint does NOT build (named, not silently assumed)

- **No new UI panel** displays this summary — explicitly forbidden by the mission's own "ZABRANJENO" list
  ("nove dashboard panele"). `case_intelligence_summaries` is the durable, queryable backend record; a future
  sprint would build the actual lawyer-facing surface for it.
- **No polling/webhook endpoint** to fetch the summary once it's ready — the row exists in the DB the moment
  `case_intelligence_summary`'s own consequence completes (typically a few seconds after `finalize-batch`
  returns, once the async dispatch loop picks up the `DOCUMENT_BATCH_COMPLETED` event), but no new API
  surface was added to fetch it in this sprint specifically (a natural, small follow-up, not attempted here
  to keep this sprint's own footprint to what the mission asked for: the Genome recompute fix + the
  summary-generation mechanism, not a full read-side API).

## Timing, honestly stated

`finalize-batch`'s own HTTP response returns BEFORE `case_intelligence_summary` has necessarily run (Case
Evolution consequences are dispatched asynchronously, via the existing `dispatch_pending_events` poller,
~3s cadence). The `napomena_genome` field in the response says so explicitly. This is not a regression from
Sprint 001's own same honesty — it is the SAME architectural boundary, now serving a richer summary instead
of just a Genome-refresh promise.

# Case Refresh Engine Spec — Program Omega, Sprint 002 (2026-08-06)

Phase 2's own required deliverable: the mechanical contract of `refresh_case_intelligence(case_id, reason)`,
Agent 1's own canonical entry point.

## Where it lives, and why it's not a new orchestrator

The mission named the function `refresh_case_intelligence(case_id, reason)`. It is implemented as
`services/case_evolution.py::_consequence_case_intelligence_summary(event)` — a CONSEQUENCE, dispatched
through the SAME `handle_case_changed` loop every other Case Evolution consequence already goes through, not
a standalone function callable from anywhere. This is a deliberate interpretation of the mission's own Rule 1
("nema novog orkestratora") and Rule 2 ("bilo koji novi business flow mora ići kroz Event → Canonical Handler
→ Consequence → Audit") — `case_id`/`reason` arrive as `event.predmet_id`/`event.payload["reason"]`, not as
direct function arguments a caller can invoke out-of-band.

## The contract, split into 2 consequences (not 1)

Registered together for `EventType.DOCUMENT_BATCH_COMPLETED`, in this exact order:

```python
CONSEQUENCE_REGISTRY[EventType.DOCUMENT_BATCH_COMPLETED] = [
    ConsequenceDef(name="genome_refresh", executor=_consequence_genome_refresh),        # REUSED, unchanged
    ConsequenceDef(name="case_intelligence_summary", executor=_consequence_case_intelligence_summary),  # NEW
]
```

**Why 2, not 1**: the mission's own Phase 2 description ("proveriti promene, prikupiti podatke, osvežiti
komponente, napraviti audit zapis") reads as one cohesive unit, but a single monolithic executor would mean a
crash between "Genome refreshed" and "summary written" forces a RETRY to redo the expensive GPT-based Genome
recompute — directly contradicting Phase 5's own Scenario 4 requirement ("nastavlja gde je stalo", not
"restarts from zero"). Splitting into 2 named consequences gives each its OWN `(event_id, consequence_name)`
idempotency row (migration 096, already-proven mechanism) — a crash after `genome_refresh` completes leaves
it marked `completed`, so retry skips it and only reruns `case_intelligence_summary`.

## Step by step

1. **"Proveriti promene"** (check for changes) — two guards: (a) the EMITTER
   (`finalize_intake_jobs_batch`) only emits `DOCUMENT_BATCH_COMPLETED` for a `predmet_id` that actually got
   1+ documents linked; (b) `_consequence_case_intelligence_summary` itself independently refuses to run if
   `payload["dokumenata_dodato"] <= 0`.
2. **"Prikupiti relevantne podatke"** (gather relevant data) — the "before" Genome snapshot
   (`pre_verzija`/`pre_kontradikcije`/`pre_dogadjaji`) was captured by the emitter BEFORE any refresh ran, and
   travels in the event's own durable payload (survives a crash/retry unchanged, unlike a value read
   mid-consequence). The "after" state is read fresh from `predmeti.case_dna` — guaranteed to reflect the
   JUST-COMPLETED `genome_refresh` consequence, thanks to `handle_case_changed`'s own sequential
   per-consequence loop.
3. **"Osvežiti potrebne komponente"** (refresh needed components) — `genome_refresh` (reused, unchanged)
   refreshes Case Genome itself; `case_intelligence_summary` additionally queries `predmet_dokazi`/
   `predmet_dokumenti`/`rocista` and calls Core Consolidation's own canonical
   `calculate_procesni_rizik`/`identify_case_problems` (`services/risk_engine.py`, established 2026-07-22 as
   the platform's ONE algorithm for "what's wrong with this case" — deliberately reused, never duplicated).
4. **"Napraviti audit zapis"** (write an audit record) — a durable `case_intelligence_summaries` row
   (migration 098) PLUS a domain-specific `case_intelligence_refreshed` audit action (added to
   `AUDITABLE_ACTIONS`), in addition to the generic `case_evolution_consequence_completed` row
   `handle_case_changed` already writes for every consequence.

## Every number, sourced (Agent 3's own "no conclusion without source" rule)

| Summary field | Source |
|---|---|
| `dokumenata_dodato` | Emitter's own count of successfully-linked documents for this predmet_id in this batch (each one individually verified by `_finalize_intake_job_core`'s own per-document logic) |
| `novi_dokazi` | Same count — every linked document is itself an evidence candidate (Evidence Vault classification already ran per-document, via the existing `NEW_EVIDENCE_REGISTERED` consequence, unchanged) |
| `novi_dogadjaji` | `len(case_dna.datumi_kljucni AFTER) - payload["pre_dogadjaji"]`, clamped to ≥0 — a real diff against a snapshot captured before this batch's own refresh |
| `kontradikcije_pronadjene` | `len(case_dna.kontradikcije AFTER) - payload["pre_kontradikcije"]`, clamped to ≥0 — same diff pattern; each contradiction object itself carries `lokacija_1`/`lokacija_2` (`"DOK-XX str.Y"`), Genome's own pre-existing sourcing discipline |
| `rizici_koji_zahtevaju_paznju` | `len([p for p in identify_case_problems(...) if p["ozbiljnost"] in ("kritican","vazan")])` — Core Consolidation's own canonical algorithm, not invented here |
| `novi_rokovi` | `payload["rokovi_dodati"]` — the emitter's own already-verified count of jobs where a deadline was actually inserted this batch |
| `dokumenti_niska_sigurnost` | `payload["dokumenti_za_proveru"]` — the emitter's own already-verified count of jobs flagged `klasifikacija_nesigurna` |
| `genome_verzija_pre`/`_posle` | `payload["pre_verzija"]` / the freshly-read `case_dna.verzija` after refresh |
| `detalji.kontradikcije` | The actual NEW contradiction objects (last N entries of the after-list, N = the computed diff) — not just a count, the real objects with their own source locations |
| `detalji.nedostajuci_dokazi` | `calculate_procesni_rizik(...)["nedostajuci_dokazi"]` — the canonical function's own real output |
| `detalji.rizici` | The actual `identify_case_problems(...)` objects flagged serious, not just a count |
| `detalji.job_ids` | `payload["job_ids"]` — traces every summary row back to the exact jobs that produced it |

Every field is either a real DB-sourced value or carried verbatim from an already-verified upstream
computation — nothing in this summary is invented or estimated.

## What refresh_case_intelligence deliberately does NOT do

- Does not call Genome itself directly (that remains `genome_refresh`'s own job, reused unchanged) — avoids a
  second Genome-triggering code path.
- Does not decide WHETHER a batch happened (that's the emitter's job) — only what to do once notified.
- Does not read or write anything outside `predmeti`/`predmet_dokazi`/`predmet_dokumenti`/`rocista`/
  `case_intelligence_summaries` — no Firm Brain, Memory Graph, Task, or Alert writes (none of those were ever
  produced by document acceptance before this sprint, per Program Delta Sprint 004's own certified Event
  Coverage Matrix, and none are invented here).

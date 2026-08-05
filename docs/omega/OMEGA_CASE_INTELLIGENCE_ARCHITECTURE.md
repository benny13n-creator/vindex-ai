# Omega Case Intelligence Architecture — Program Omega, Sprint 002 (2026-08-06)

Phase 1's own mandatory forensic review, produced before any code was written: a map of the CURRENT Case
Intelligence flow, from document upload to Genome state, as it existed at the start of this sprint (i.e.,
after Program Omega Sprint 001's own 2 fixes, before this sprint's own changes).

## The flow as it existed at sprint start

```
Document finalized (single-job OR batch, per-job)
  -> DOCUMENT_ACCEPTED emitted (once per finalize call, per Program Delta Sprint 001's own coalescing)
  -> Case Evolution Engine (services/case_evolution.py::handle_case_changed)
      -> genome_refresh consequence -> _run_genome_background() -> case_dna updated, verzija++
      -> timeline_entry consequence -> one predmet_hronologija row
```

**The gap, precisely**: `POST /jobs/finalize-batch` (Program Omega Sprint 001) loops calling
`_finalize_intake_job_core` per job. Each job that successfully links a document to a case still emits its
OWN `DOCUMENT_ACCEPTED` — meaning N jobs finalized into the SAME case produce N separate `DOCUMENT_ACCEPTED`
events, each independently triggering a full Genome recompute. This was named honestly as `OMEGA-001` in
Sprint 001's own Architectural Debt Register entry and deliberately deferred.

## Every call, base, AI call, and event mapped (Phase 1's own explicit requirement)

| Layer | What runs | Duplicate risk? |
|---|---|---|
| DB writes | `predmet_dokumenti` (per document), `predmeti.case_dna` (per Genome refresh), `predmet_hronologija` (per timeline consequence) | None found — each write is scoped to its own triggering event's own idempotency key |
| AI calls | `_run_genome_background` → `_do_genome_refresh` (GPT-based full case recompute) | **Confirmed the ONLY real duplicate-call risk**, and only at BATCH scale (N finalize calls for 1 case = N recomputes) — not a bug (each individual call is correct), a COST problem |
| Events | `DOCUMENT_ACCEPTED`, `NEW_EVIDENCE_REGISTERED`, `NEW_CLIENT_LINKED`, `REVIEW_ACCEPTED`, `REVIEW_REJECTED`, `ROCISTE_ZAKAZANO` | All already certified bypass-free (Program Delta Sprint 004) — re-confirmed clean by this sprint's own repo-wide bypass tests (still passing, unmodified allowlist except this sprint's own 2 new, intentional call sites) |
| Hidden refresh mechanisms | Searched (repo-wide grep, same method as Program Delta Sprint 003/004's own Hidden Orchestrator Hunt) for any OTHER direct `_run_genome_background(` caller — none found beyond `services/case_evolution.py`'s own 2 consequence executors (`genome_refresh`, reused; this sprint adds zero new direct callers) | Clean |
| AI results without provenance | Case Genome's own `kontradikcije` field already requires `lokacija_1`/`lokacija_2` in `"DOK-XX str.Y"` form (`routers/case_dna.py`'s own prompt, "NIKAD ne nagađaj ili izmišljaj lokaciju") — confirmed, not a new finding, already the platform's own established discipline | Clean |

## Stale data risk, specifically checked

Case Genome's own `_run_genome_background` already has in-flight coalescing for concurrent triggers on the
SAME `predmet_id` (`tests/test_ztc_genome_scale_and_race.py::test_concurrent_trigger_for_same_predmet_is_coalesced_not_dropped`,
built well before this sprint) — a concurrent second trigger while one is already running does NOT silently
overwrite or get dropped, it coalesces. This is the exact protection Phase 5's own Scenario 3 (two users,
same case, concurrent upload) needs, and it already existed — this sprint reuses it unchanged, adds no new
locking.

## What this sprint builds on top of the mapped flow

```
Batch finalize completes (N jobs, M unique cases touched)
  -> for each unique predmet_id: "before" Genome snapshot captured (kontradikcije/datumi_kljucni counts)
  -> DOCUMENT_BATCH_COMPLETED emitted ONCE per predmet_id (not per job)
  -> Case Evolution Engine (SAME dispatcher, no new orchestrator)
      -> genome_refresh consequence (REUSED unchanged) -> ONE recompute per case, not per document
      -> case_intelligence_summary consequence (NEW) -> diffs before/after, queries Core Consolidation's
         own canonical risk engine, writes ONE sourced case_intelligence_summaries row + audit
```

This directly closes `OMEGA-001`: a 500-document single-case batch now produces exactly ONE Genome recompute
(via `DOCUMENT_BATCH_COMPLETED`), not 500 (via 500 separate `DOCUMENT_ACCEPTED` emissions) — because
`finalize_intake_jobs_batch` still emits per-job `DOCUMENT_ACCEPTED`/`NEW_EVIDENCE_REGISTERED` for evidence
classification and timeline continuity (unchanged, still valuable at document granularity), but the EXPENSIVE
Genome recompute is now case-scoped, once, via the new batch-completion event.

## Answers to Agent 1's own 4 required questions

1. **Ko je vlasnik trenutnog stanja predmeta?** `predmeti.case_dna` remains the single source of truth,
   unchanged. No new state store competes with it — `case_intelligence_summaries` (migration 098) is a
   HISTORY of what changed, never a second copy of current state.
2. **Kada se Genome osvežava?** Exactly when one of the 7 now-wired Case Evolution events fires
   (`DOCUMENT_ACCEPTED`, `REVIEW_ACCEPTED`, `ROCISTE_ZAKAZANO`, or the new `DOCUMENT_BATCH_COMPLETED`) — never
   from any other call site (confirmed, repo-wide).
3. **Ko odlučuje da li je refresh potreban?** Two layers: the emitter decides WHETHER to emit at all (only
   for predmet_ids that actually got 1+ documents linked); the consequence itself additionally refuses to run
   with zero new documents, as a second independent guard.
4. **Kako znamo da je rezultat zasnovan na kompletnim podacima?** `DOCUMENT_BATCH_COMPLETED` is only emitted
   AFTER the entire batch's document-linking loop completes (never mid-batch) — so when Genome refreshes for
   that event, every document the batch successfully linked is already in `predmet_dokumenti`.

Full mechanical spec: `CASE_REFRESH_ENGINE_SPEC.md`. Full advocate-facing flow: `CASE_LEVEL_INTELLIGENCE_FLOW.md`.

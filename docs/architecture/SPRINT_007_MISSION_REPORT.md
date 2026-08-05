# Mission Report — Program Intake Sprint 007 (2026-08-05)
## "Intake Finalization – Bulletproof Intake"

Per this sprint's own required deliverable shape: Otkriveno / Popravljeno / Dokazano / Odloženo. Full
technical detail in the companion documents (`DUPLICATE_DETECTION_REPORT.md`, `RETRY_RELIABILITY_REPORT.md`,
`CASE_NUMBER_NORMALIZATION_SPECIFICATION.md`, updated `INTAKE_ARCHITECTURE_REPORT.md`); this report is the
founder-facing summary.

**Hard token budget honored**: 2 active agents throughout (Reliability & Failure Recovery Engineer, Chief
Systems Architect, both embodied directly rather than delegated to subagents, matching the sprint's own
explicit instruction to keep footprint minimal). The 3rd agent (Code Quality/Refactoring Reviewer) was never
activated — no written justification arose for it; a direct self-review confirmed no parallel/competing
implementation was created (case number normalization is a genuinely new function, not a duplicate of the
extraction-layer regexes; the content-hash mechanism is the ONE new identity check, reused for both Debt 1 and
Debt 2; the claim RPC was extended in place, not duplicated).

---

## Otkriveno (Found)

1. **Sprint 006's own `INTAKE-019` finding was more severe than its own description implied.** The idempotency
   gate (`if job.get("predmet_id")`) didn't just fail to retry a "soft" partial failure — it also meant a
   **hard crash** before the durable `predmet_id` write would let a retry run Ownership Resolution completely
   fresh, creating a genuinely **second, duplicate case** for a "create new" scenario. This was the single
   most severe risk this sprint closed.
2. **`normalize_case_number`'s prefix character set (a NEW function written this sprint) had a real gap**,
   found during this sprint's own test-writing: mixed-case two-letter Cyrillic prefixes ("Пж", "Гж" — the
   actual shape Serbian court abbreviations use) did not match the parser's original character class
   (uppercase Cyrillic only), silently falling back to a non-canonical form instead of the intended canonical
   one.
3. **The atomic finalize claim's own gate (`predmet_id IS NULL`, Sprint 002) was the structural reason
   `INTAKE-019` could never be closed without touching it** — no amount of application-code retry logic could
   have worked around a claim mechanism that treats any set `predmet_id` as permanently un-reclaimable.

## Popravljeno (Fixed)

1. **One deterministic content identity** (`predmet_dokumenti.content_sha256`, migration 095) — SHA-256 of a
   document's own extracted text, never filename/size/date — answers both "was this content already
   assimilated anywhere" (Debt 1) and "did this segment's own insert already happen" (Debt 2, retry
   idempotency) with the same lookup.
2. **Crash recovery via a generalized lineage FK** (`predmet_dokumenti.source_intake_job_id`, migration 095,
   extending Sprint 006's segment-only FK to every document) — a retried finalize call recovers an
   already-resolved `predmet_id` instead of creating a duplicate case.
3. **The claim mechanism itself widened** — `claim_intake_finalize`'s WHERE clause changed from
   `predmet_id IS NULL` to a new `intake_jobs.assimilation_complete = false` check, so both a hard crash and a
   soft partial failure remain correctly retryable, closing `INTAKE-019` completely (not partially).
4. **Case number canonicalization** — a real 3-part parser (prefix/number/year) replacing the
   whitespace-collapse-only placeholder, handling every punctuation/spacing convention the mission named plus
   the mixed-case-Cyrillic gap found during this sprint's own testing.
5. **Best-effort side effects (client-linking, deadline insertion, conflict-check) correctly skipped on
   resume** — re-running them on every retry would have created duplicate `proactive_alerts` entries (that
   endpoint has no idempotency guard of its own); recognized and avoided during design, not discovered after
   shipping.

## Dokazano (Proven)

The mission's own closing definition, checked directly by test, not merely claimed:

- *Isti dokument može biti otpremljen više puta* — proven by 5 duplicate-detection tests (`isti PDF`, `isti
  sadržaj pod drugim imenom`, `isti sadržaj drugi upload`, `isti sadržaj posle retry`, plus the cross-case
  review-required case).
- *Obrada može biti prekinuta u bilo kom trenutku* — proven for both interruption shapes: a hard crash before
  the completion marker is ever written (`test_crash_recovery_reuses_existing_predmet_not_a_new_one`), and a
  soft partial failure after it is written (`test_soft_partial_failure_job_is_not_treated_as_already_finalized`).
- *Korisnik može ponoviti zahtev više puta* — proven by
  `test_partial_retry_resumes_only_the_unresolved_segment` (per-document resumability, not all-or-nothing) and
  `test_assimilation_complete_only_set_when_all_documents_linked` (the completion signal is never
  optimistically set).
- *Sistem će i dalje završiti sa jednim tačnim dokumentom, jednim tačnim predmetom, jednim lineage lancem i
  jednim audit/provenance zapisom* — proven structurally: the idempotent-skip path returns before any
  lineage/audit/provenance code ever runs for an already-assimilated document (`RETRY_RELIABILITY_REPORT.md`'s
  own "why this is actually true" section), and the fully-done fast-exit path is unchanged for the common case
  (`test_fully_complete_job_still_takes_the_fast_exit_path`).
- Case number identity: 30+ representations of the same number, one canonical result
  (`test_thirty_plus_case_number_variants_resolve_to_one_canonical_identity`).

## Odloženo (Deferred, with reasoning)

Full detail: `ARCHITECTURAL_DEBT_REGISTER.md`, `INTAKE-021`/`INTAKE-022`.

1. **The dedup/retry mechanism is only wired into Pipeline C** (`finalize_intake_job`). Pipelines A and
   A-ephemeral have no equivalent yet. Deliberate scope boundary — this mission's charter named 3 specific
   debts against the segmentation/assimilation work already living in Pipeline C; extending the same
   (pipeline-agnostic) mechanism elsewhere is a bounded future step, not attempted here to honor the hard
   token budget.
2. **No automatic backoff/dead-letter ceiling for a document that keeps failing across manual retries.**
   Finalize is lawyer-initiated, not an automatic loop — a human already decides whether to retry, and each
   retry is cheap and safe.

Neither of these blocks the mission's own success criterion — every document assimilated via Pipeline C is
provably never lost, never duplicated, and every retry converges correctly, which is the literal claim the
mission asked to be proven.

## Nothing found outside Intake this sprint

Per the mission's own instruction ("ako se pronađe problem van Intake-a: evidentirati, ne popravljati") — no
such finding arose. This sprint's investigation and implementation stayed entirely within
`routers/smart_intake.py`, `shared/case_assimilation.py`, `shared/intake_segments.py`, and the intake-specific
migrations. OCR, AI models, classification, segmentation internals, Genome, Copilot, Strategy, Timeline,
Tasks, and Search were not touched, per the mission's explicit prohibition.

## Section: Merljivo poboljšanje platforme (Measurable improvement)

| Metric | Before this sprint | After this sprint |
|---|---|---|
| Deterministic cross-upload document identity | 0 (filename/size/date were the only signals, all explicitly forbidden by the mission) | 1 (`content_sha256`) |
| Scenarios where a hard crash could create a duplicate case on retry | Present (unfixed `INTAKE-019` shape) | Eliminated (crash recovery via `source_intake_job_id`) |
| Scenarios where a soft partial failure permanently blocked retry | Present (unfixed `INTAKE-019`) | Eliminated (`assimilation_complete`-gated claim) |
| Case number format variants correctly recognized as the same identity | 1 (only whitespace-collapsed exact matches) | Unbounded — any of the mission's 5 named formats + 25 more tested variants + mixed-case Cyrillic |
| New dedicated tests | 0 | 14 (`tests/test_sprint007_bulletproof_intake.py`, including 4 case-number-normalization tests) plus 2 pre-existing `test_case_assimilation.py` assertions updated for the new canonical format |
| Full regression suite | 2,581 passed, 1 skipped, 0 failed (Sprint 006 close) | **2,595 passed, 1 skipped, 0 failed** — zero regressions from this sprint's changes |

**Platform state at the end of this sprint, honestly assessed**: Intake now satisfies its own mission-defined
bulletproof criterion for Pipeline C, the pipeline Sprints 005/006 already built segmentation and Ownership
Resolution into. Two genuine scope boundaries (not gaps) remain, both named with reasoning. Per the mission's
own final instruction, Intake is now a closed, stable subsystem for Pipeline C — future work (Timeline,
Genome, Case Evolution, Tasks, Alerts, Briefing, Copilot) can build on it without expecting further
architectural reconstruction of this pipeline.

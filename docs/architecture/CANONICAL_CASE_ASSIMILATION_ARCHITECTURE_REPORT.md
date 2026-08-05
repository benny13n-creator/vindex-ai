# Canonical Case Assimilation Architecture Report — Program Intake Sprint 006 (2026-08-05)
## "Canonical Case Assimilation"

Mission: Sprint 005 proved one PDF can contain multiple logical documents. Sprint 006 proves each of those
documents becomes part of a *specific, correctly-identified* case (`predmet`) and client (`klijent`) —
deterministically, never a guess. Segmentation is no longer the goal; it is the input. The goal is fully
deterministic document-into-case assimilation.

**Governing rule, checked at every design decision below** (the mission's own, stated with absolute
priority): a document assigned to the wrong case is a more serious problem than ten documents waiting for a
human to confirm. Every function in this sprint's design returns an explicit "review required" outcome
rather than picking the "most likely" match.

---

## Phase 1 — Complete Assimilation Audit (what already existed)

Full audit transcript: this sprint's own investigation fork. Summary of confirmed findings, each with
exact file:line citations gathered during the audit:

1. **`predmeti` had NO structured case-number column at all.** Confirmed across every migration and every
   `predmeti` insert call site (`api.py`, `routers/smart_intake.py`, `routers/intake.py`, `routers/
   integracije.py`, `routers/onboarding.py`). `finalize_intake_job` only ever wrote the extracted case number
   as free text inside `opis` ("Broj predmeta: ..."). **Consequence: no pipeline could ever recognize "this
   incoming document's case number matches an already-open case"** — every non-interactive intake either
   required the lawyer to manually supply an existing `predmet_id`, or unconditionally created a brand-new
   case. This is not a duplicated-authority problem (the kind Core Consolidation usually finds); it is a
   missing-capability problem.
2. **`predmet_id` resolution, per pipeline**: Pipeline A (`api.py`'s per-case upload) already has the case
   scoped by the URL itself (a lawyer uploading into an already-open case). Pipeline A-ephemeral and Pipeline
   B (Sprint 005's staging worker) never assign a `predmet_id` at all (out of scope by design). Pipeline C
   (`finalize_intake_job`) had exactly 2 paths: an explicit `predmet_id` supplied by the caller (`attach_
   existing`), or an unconditional brand-new `predmet` insert — never content-based matching.
3. **A live client-name-matching bug**: `finalize_intake_job`'s client lookup compared a full "First Last"
   extracted party name against `klijenti.ime`, a first-name-only column, via `.ilike("ime", klijent_ime)`
   with `.limit(1)` and no disambiguation. This query could essentially never match a real two-word name
   correctly, and its `.limit(1)` meant that on the rare occasion it DID over-match, it silently picked an
   arbitrary row — precisely the mission's own named "two clients, same surname" failure mode, unmitigated.
4. **`predmet_klijenti`'s once-tracked `user_id`-column bug is already fixed** — confirmed stale in prior-
   session memory; Mission 001 (2026-08-02) and Night Shift M-012 already corrected all current insert call
   sites. Re-confirmed fresh during this sprint, not re-fixed.
5. **Zero audit/provenance calls for document-into-case registration in Pipeline C.** `finalize_intake_job`
   had no `log_action` call anywhere for the actual moment a document enters a case — unlike Pipeline A's
   per-case upload, which always logs `dokument_upload`. The single most consequential operation in the
   whole intake arc (creating/attaching a case and linking a document to it) left no audit trace.
6. **No lineage FK from `predmet_dokumenti` back to `intake_jobs`/`intake_documents`/`intake_job_segments`.**
   Sprint 001's long-open `INTAKE-003` gap, still fully open at the start of this sprint.
7. **A confirmed live false-success bug**: `finalize_intake_job` computed `doc_linked = bool(dok_ins and
   dok_ins.data)` but never checked it before returning `{"ok": True, ...}` or before writing `intake_jobs.
   predmet_id`. If the `predmet_dokumenti` insert failed for every fallback variant, the case was still
   created/attached and marked finalized while containing zero of its source documents — the same "false
   success" shape this whole engagement has repeatedly found and fixed elsewhere (Sprint 001's original
   finding, Sentinel's `predmet_upload_auto_analyze` fix), here unfixed in the newest pipeline.
8. **A structural incompatibility with Sprint 005's own multi-segment output**: `finalize_intake_job` and
   `GET /jobs/{job_id}` both still called `intake_documents.get_job_result()`, whose `.maybe_single()` call
   raises the moment a job has 2+ `intake_documents` rows (which Sprint 005 can legitimately produce). Any
   segmented job reaching either endpoint would crash — and even without the crash, only ONE of N segments
   would ever have been assimilated, the rest permanently orphaned.
9. **Genome, Evidence Vault, and Timeline consumption is clean.** Neither makes an independent case/client
   decision — both derive `predmet_id`/`document_id` from whatever Pipeline A/C already resolved in local
   scope. No competing authority found here.

---

## Phase 3 — Canonical Assimilation Pipeline (what this sprint built)

The mission's own diagram: Upload → Segment → Classification → Ownership Resolution → Evidence Registration
→ Timeline Candidate → Genome Input Queue → Audit → Provenance → Completed.

| Stage | Owner | Reuse / New |
|---|---|---|
| Upload → Segment → Classification | Sprints 001-005, unchanged | Reuse |
| **Ownership Resolution** | New `shared/case_assimilation.py::resolve_case_ownership()` / `resolve_client_ownership()` | New logic, one new column (`predmeti.broj_predmeta`) |
| Evidence Registration | `predmet_dokumenti` insert (existing) + Evidence Vault auto-classify (existing) | Reuse + new lineage FK |
| Timeline Candidate | `predmet_hronologija` insert (existing, deadline-gated) | Reuse, unchanged this sprint |
| Genome Input Queue | `case_dna.py::_run_genome_background()` (existing) | Reuse, triggered once per finalize call regardless of document count |
| Audit | `shared/audit_immutable.py::log_action()` (existing primitive, new call site) | Reuse the primitive, close the missing call-site gap |
| Provenance | `shared/ai_provenance.py::case_context()` (existing primitive, new call site) | Reuse the primitive, close the missing call-site gap |
| Completed | `intake_jobs.predmet_id` write (existing) + honest per-document outcome reporting (new) | Reuse + extend |

**One single flow, no alternative paths**: every document produced by a job (1 for the common case, N for a
Sprint-005-segmented job) now passes through the exact same `_process_segments`-style per-document loop
inside `finalize_intake_job` — the same code path, not a special case for N>1.

**Scope decision, matching Sprint 005's own precedent**: Ownership Resolution for the *case* stays a
whole-job decision (one `predmet_id` per finalize call), not a per-segment one — except for one explicit
guard: if 2+ documents in the same job carry genuinely DIFFERENT extracted case numbers, that is treated as
real evidence of a mis-bundled multi-case upload, and the whole finalize call is blocked with an explicit,
actionable error rather than silently assimilating everything under whichever document was read first.

Full detail: `OWNERSHIP_RESOLUTION_SPECIFICATION.md`, `LINEAGE_VERIFICATION_REPORT.md`,
`CASE_ASSIMILATION_FAILURE_RECOVERY_REPORT.md`, `EVIDENCE_INTEGRITY_REPORT.md`.

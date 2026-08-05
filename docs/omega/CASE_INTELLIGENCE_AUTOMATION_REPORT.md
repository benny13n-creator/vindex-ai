# Case Intelligence Automation Report — Program Omega, Master Sprint 001 (2026-08-06)

Agent 3/4's own central questions: *"Kada dokument uđe, da li predmet postaje pametniji?"* and *"Da li advokat
mora ručno da organizuje posledice?"*

## What is already automatic (as of Program Delta Sprint 004's own certification, unchanged by Omega)

| Consequence | Automatic? | Mechanism |
|---|---|---|
| Genome refresh (facts, parties, contradictions, strength) | ✔ | `DOCUMENT_ACCEPTED`/`REVIEW_ACCEPTED`/`ROCISTE_ZAKAZANO` → `genome_refresh` |
| Timeline entry | ✔ | Same events → `timeline_entry` |
| Evidence classification (`tip_dokaza`) | ✔ | `NEW_EVIDENCE_REGISTERED` → `evidence_classification` |
| Conflict-of-interest alert | ✔ | `NEW_CLIENT_LINKED` → `conflict_check` |
| Deadline extraction (per-document, confidence-gated) | ✔ | `_finalize_intake_job_core`'s own primary action (not a Case Evolution consequence — happens inline during finalize) |
| Copilot/AI Briefing context | ✔ (for free) | Both read Case Genome directly — no separate wiring needed, benefit from every Genome refresh automatically |
| Search indexing | ✔ | Synchronous Pinecone ingest, primary action |
| Audit trail | ✔ | Comprehensive, correlation_id-linked, certified |

## What is NOT automatic — real, honest gaps

| Consequence | Automatic? | Why not |
|---|---|---|
| **Task creation from document acceptance** | ✘ | Confirmed by Program Delta Sprint 004's own Event Coverage Matrix — every one of the 6 Case Evolution events shows `NE` for "Tasks." `routers/zadaci.py`'s own task-creation is lawyer-initiated or driven by a SEPARATE, older AI endpoint (`ai_analiziraj_predmet`), never triggered by document acceptance itself |
| **Missing-evidence detection surfaced automatically per document** | Partial | `identify_case_problems()`/`calculate_procesni_rizik()` already compute this correctly (Project Synapse/Nexus era) but are not auto-run and auto-surfaced as a CONSEQUENCE of document acceptance — a lawyer must visit the case page / ask Copilot to see it. This sprint's own `finalize-batch` endpoint does NOT call these per-document either (see below) |
| **Contradiction detection surfaced in the immediate upload response** | Partial | Genome computes `kontradikcije` as part of its own regular refresh, but that refresh is ASYNCHRONOUS (Case Evolution's own certified design) — never available synchronously in the same request that triggered it |
| **Firm Brain auto-population from accepted documents** | ✘ | Confirmed, again, zero writer exists (pre-existing gap, `WOW-003`) |
| **Memory Graph auto-population** | ✘ | Confirmed, again, zero writer exists (pre-existing gap, `IF-005`) |

## Why the batch-finalize summary this sprint does NOT include live contradiction/missing-evidence counts

This was a deliberate design decision, not an oversight — worth stating explicitly since the mission's own
worked example implies these numbers should appear in the same response. Reading `predmeti.case_dna.
kontradikcije` or calling `identify_case_problems()` synchronously, right after the finalize-batch loop
completes, would either:

1. **Read STALE data** — Genome's own refresh for documents accepted moments ago has very likely not been
   processed yet by the async dispatch loop (which polls every ~3s), so the numbers would reflect PRE-batch
   state, silently wrong in a way that looks authoritative.
2. **Require calling Genome refresh directly from the batch endpoint** — which would be exactly the kind of
   SECOND orchestrator (a hidden bypass of the Case Evolution Engine) Program Delta spent 4 sprints proving
   does not exist anywhere in this codebase. Reopening that certification to make one response look more
   complete would be a real, serious architectural regression, not a minor shortcut.

Instead, `finalize-batch`'s own response includes an honest `napomena_genome` field explaining that Genome-
derived intelligence is being computed asynchronously and will appear on the case page shortly — true
transparency (Priority 5: "advokat mora znati šta je sistem uradio... sa kojim stepenom sigurnosti") over a
fabricated instant number.

## Recommended direction for a future Omega sprint (named, not attempted here)

1. **Wire `NEW_EVIDENCE_REGISTERED` (or a new, deliberately-scoped event) to Task creation** — e.g., "missing
   evidence detected" → an automatic task. This is the single highest-leverage fix for Priority 4 ("automatski
   rokovi i zadaci") that remains, and fits cleanly into the existing Case Evolution registry pattern (same
   dispatcher, a new consequence definition, no new orchestrator).
2. **A "batch complete" webhook/polling endpoint** the frontend can call a few seconds after `finalize-batch`
   returns, to fetch the NOW-current Genome-derived numbers (contradictions, missing evidence) per touched
   case — closes the "eventually consistent" gap honestly, without faking synchronicity.
3. **De-duplicate Genome refresh across a same-case batch** (see `OCR_AND_INTAKE_CAPACITY_REPORT.md`'s own
   Capacity Finding 3) — directly reduces the GPT cost and latency of a large single-case upload.

None of these were attempted this sprint — each is either a real new capability (forbidden by this sprint's
own "no new isolated functions" principle without a dedicated design pass) or carries meaningful regression
risk to already-hardened, heavily-tested machinery that deserved its own focused sprint rather than being
squeezed in alongside the upload-timeout and batch-finalize fixes already made.

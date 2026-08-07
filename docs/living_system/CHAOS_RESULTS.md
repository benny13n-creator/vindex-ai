# Operation Living System — Extreme Events & Red Team

7 read-only agents: 3 chaos-engineering teams (infra failure, data integrity, concurrency) and
4 Red Team groups attacking all 20 named systems. Disposition key as in
`LAWYER_DAY_SIMULATION.md`.

## Infra chaos: worker restart, Supabase/OpenAI failures, slow uploads

| Finding | Severity | Disposition |
|---|---|---|
| OpenAI failure during evidence classification is silently laundered into a fake success (`tip_dokaza:"ostalo"`, `klasifikovan_at` stamped, indistinguishable from a real result); the manual "reklasifikuj" retry charges a credit before the background task even starts, with no refund path | HIGH | DEBT (`LIVINGSYS-DEBT-009`) |
| Dashboard/Workspace Supabase calls have no per-call timeout — a genuine hang stalls up to ~120s (the client library default) with no fast-fail, though the failure is eventually visible, not silent | MEDIUM | DEBT (`LIVINGSYS-DEBT-040`) |
| Slow/large file upload has no progress indicator or explicit app-level timeout | LOW-MEDIUM | DEBT (`LIVINGSYS-DEBT-041`) |
| Event Bus worker-restart reclaim (`claim_pending_events`, stale-claim reclaim, heartbeat refresh, bounded dead-letter at 5 attempts), `@llm_retry` coverage across all 5 flagship AI features, Smart Intake finalize resumability | — | **CONFIRMED CLEAN** |

## Data integrity chaos: partial writes, duplicate/lost events

| Finding | Severity | Disposition |
|---|---|---|
| HTTP-layer retry on Smart Intake review resolve/reject has no idempotency gate — a double-click emits 2 distinct durable events for one logical fact, producing a full duplicate consequence chain (2x GPT genome cost, duplicate timeline/audit rows) | HIGH | DEBT (`LIVINGSYS-DEBT-010`) |
| 7 of 8 Case-Evolution event types have zero recovery net if the durable-outbox insert itself is lost (only `PREDMET_KREIRAN` has both a retry-with-backoff and a dedicated reaper) | HIGH | DEBT (`LIVINGSYS-DEBT-042`) |
| 5 of 9 consequence executors (`genome_refresh`, `timeline_entry`, `review_confirmation_audit`, `review_rejection_audit`, `case_intelligence_summary`) have no idempotency guard beneath the outer claim — a crash-then-reclaim window (the same 300s window Certification 004/005 deliberately built) causes real re-execution: duplicate GPT cost, duplicate timeline/audit rows | MEDIUM-HIGH | DEBT (`LIVINGSYS-DEBT-011`) |
| Hearing creation (`POST /api/rocista`) has no idempotency check, cascading into duplicate `ROCISTE_ZAKAZANO` on retry | MEDIUM | DEBT (`LIVINGSYS-DEBT-043`) |
| Partial-chain crash correctly resumes from where it stopped, not restart-the-chain (verified by code trace, not just the docstring's own claim); `refresh_case_actions`/`project_notifications` (the 2 reconcile-based executors) are naturally idempotent by construction | — | **CONFIRMED CLEAN** |

## Concurrency chaos: concurrent AI requests, uploads, edits, F5 spam

| Finding | Severity | Disposition |
|---|---|---|
| Case Commander's `/jutarnji` morning briefing has the exact same unprotected double-charge race CIO's `/daily` was fixed for in Part A — never received the same fix, and has no rate limit at all | HIGH | DEBT (`LIVINGSYS-DEBT-006`) |
| Near-universal absence of `cooldown_seconds` (only 3 of ~60 feature_registry rows have one) plus a real TOCTOU race in `UsageService.consume()` for the few that do — a double-click on almost any AI button risks 2 full GPT calls + 2 charges | HIGH | DEBT (`LIVINGSYS-DEBT-012`, needs a migration to seed `cooldown_seconds` values — outside the coordinator's authority) |
| Document sequence number (`redni_broj`) can collide under concurrent finalize calls to the same case — a citation/reference-integrity risk (GPT cites "DOK-05" ambiguously), not data loss | MEDIUM | DEBT (`LIVINGSYS-DEBT-044`) |
| Genome coalescing guard has a false-failure blind spot: 2 concurrent document uploads can trigger up to 3 genome refreshes where 1-2 would suffice — wasted GPT cost, final `case_dna` content is not corrupted | MEDIUM | DEBT (`LIVINGSYS-DEBT-045`) |
| CIO `/daily`'s credit-charge race is fixed (Part A), but every concurrent request in the race window still pays the full GPT compute cost before losing the claim; `/run` (force regenerate) has no claim/lock at all | LOW/MEDIUM | DEBT (`LIVINGSYS-DEBT-046`) |
| Manual/automatic Genome refresh mutual exclusion (in-process guard, explicitly documented as not crossing worker processes), Genome write atomicity (never a partial/interleaved merge), credit-ledger atomicity, document-row creation, AI-result display determinism | — | **CONFIRMED CLEAN** |

## Red Team: sustained attack on all 20 named systems

38 findings reproduced across 4 Red Team groups. Full per-system detail in each group's own
report; consolidated ledger below, most severe first.

| Finding | System | Severity | Disposition |
|---|---|---|---|
| `/api/nacrt`'s quick-draft path asks GPT to invent a specific ZOO statute article number for a real damages lawsuit, with zero RAG grounding and zero critique pass — a fabricated citation could reach a filed court document | Drafting | **CRITICAL** | DEBT (`LIVINGSYS-DEBT-013`) |
| Billing `PATCH`/`DELETE /entries/{id}` checked `obracunato` in a separate read from the write — a concurrent invoice creation could still edit/delete an already-invoiced amount, corrupting the PDF's own totals | Billing | HIGH | **FIXED** (Fix L3) |
| Collaborator-generated Client Portal tokens were built with the collaborator's own uid instead of the real case owner's — the link permanently 404'd for the client (who was still emailed a "success" link) and the real owner had no visibility or revoke power | Client Portal | HIGH | **FIXED** (Fix L5) |
| Copilot's `_handle_akcija_rok` asked GPT for a 3-value vocabulary that doesn't match the DB's actual CHECK constraint — 2 of 3 possible outputs, and the code's own fallback, always threw on insert; the natural-language "add deadline" feature was structurally broken for most inputs | Copilot | HIGH | **FIXED** (Fix L4) |
| Genome's backend correctly detects a post-GPT DB-write failure and reports it honestly (`case_dna_persisted:false`), but the frontend's only caller never read that field — a silently-failed save still showed a green success toast | Genome | HIGH | **FIXED** (Fix L6) |
| Silent blank (not a visible `[POPUNITI]` placeholder) for missing name/address/JMBG/amount fields across both drafting paths — the extraction prompts explicitly instruct GPT to return `""` rather than omit the key, defeating the visible-placeholder safety net the module's own docstring promises | Drafting | HIGH | DEBT (`LIVINGSYS-DEBT-014`) |
| Hallucination critique pass (`_critique_and_refine_draft`) silently no-ops on any failure, returning the unreviewed draft with no signal distinguishing "reviewed clean" from "review didn't run" | Drafting | HIGH | DEBT (`LIVINGSYS-DEBT-015`) |
| `NEW_EVIDENCE_REGISTERED` never triggers `refresh_case_actions` — readiness can lag live risk within the same `build_case_context()` response, a self-documented ordering gap with no re-refresh once evidence classification completes | Risk Engine / Readiness | HIGH | DEBT (`LIVINGSYS-DEBT-016`) |
| `argument_reputation`'s `relevantne_odluke` (decision count) is fully hallucinated for arguments 6-10 (only the first 5 get real RAG retrieval, but all 10 get an AI-invented count presented identically) | Court Predictor | HIGH | DEBT (`LIVINGSYS-DEBT-047`) |
| Matter Intelligence's main endpoint has no hearing-status filter — a cancelled/completed hearing scores as a live "critical deadline," persisting a real false alert to the notification center | Matter Intelligence | HIGH | DEBT (`LIVINGSYS-DEBT-048`) |
| Calendar's per-source `return_exceptions=True` degradation has zero `degraded`/error signal — a genuinely partial-failure month renders identically to a genuinely empty one, on the one screen whose entire job is not missing a hearing | Calendar | HIGH | DEBT (`LIVINGSYS-DEBT-038`, same item as Day 3's calendar finding) |
| `semantic_registry.py` (the machine-readable Truth Contract index built by the immediately-preceding mission) has no entry at all for "Probability," a concept with 4 named generators and a known unfixed violator in the human contract — the registry itself silently understates real fragmentation | Semantic Registry | MEDIUM-HIGH | DEBT (`LIVINGSYS-DEBT-017`) |
| Two entire subsystems (Memory Graph + Firm Memory's full CRUD/query surface) have zero UI entry points — real engineering investment, zero current reachability | Memory Graph | HIGH (product, not correctness) | DEBT (`LIVINGSYS-DEBT-049`) |
| Notification read-state is client-`localStorage`-only, never reconciled against the server's own `procitano` field — badge counts can legitimately disagree between 2 open sessions indefinitely | Notifications | MEDIUM | DEBT (`LIVINGSYS-DEBT-050`) |
| Case closure renders as 2 separate Timeline entries (one from the hronologija row, one synthesized unconditionally whenever `status=="zatvoren"`, no de-dup between them) | Timeline | MEDIUM | DEBT (`LIVINGSYS-DEBT-051`) |
| Duplicate tenant-resolution logic in `memory_graph.py` (byte-identical to `firm_memory.py`'s, missed by the 2026-07-26 consolidation that extracted the shared helper) | Memory Graph | MEDIUM | DEBT (`LIVINGSYS-DEBT-052`) |
| Non-deadline narrative entries (case-closure notes, hearing follow-ups) render on the firm-wide deadline Calendar tagged identically to real filing deadlines | Calendar | MEDIUM | DEBT (`LIVINGSYS-DEBT-053`) |
| `faktura_create` never validates `predmet_id` actually matches the billed entries — any of a user's own billing entries can be invoiced under an arbitrary case ID | Billing | MEDIUM | DEBT (`LIVINGSYS-DEBT-054`) |
| Bare `except: pass` in `calculate_procesni_rizik`'s hearing-date loop silently drops any malformed-date hearing from risk scoring, with no counter/flag | Risk Engine | MEDIUM | DEBT (`LIVINGSYS-DEBT-055`) |
| ~15 lower-severity findings (dead endpoints, cosmetic labeling gaps, `profitabilnost.py`'s RLS-reliant tenant filter needing verification, per-source silent-failure gaps in Timeline/Health Index's weak-signals block, `case_commander.py`'s computed-but-unenforced hard_flags) | Various | LOW | Consolidated into `LIVINGSYS-DEBT-056` through `-063` |
| Workspace's fan-out degradation, Smart Intake's confidence clamping across both classification and extraction, Case Commander's `validate_predmet_reference` guard, Genome's grounding checks (`validate_dok_reference`/`validate_graph_edge_references`), Court Predictor's probability clamping/readiness-capping (5 of 6 checked fields), Digital Twin's per-scenario clamp, Health Index's cache-staleness disclosure and canonical risk/strength sourcing, Canonical Context's total-failure error surfacing, Client Portal's HMAC/RLS/upload-validation hardening | — | **CONFIRMED CLEAN** |

## Summary

Chaos + Red Team combined: 3 fixed (all HIGH), ~47 deferred across the full severity range,
1 CRITICAL (drafting hallucination risk) among them. The clean-bill-of-health list is
substantial and real — this is not a platform in crisis, but a platform where a genuinely
adversarial, full-day simulation (the first of its kind run against it) found real, reproducible
gaps concentrated exactly where 15+ prior narrower-scope missions hadn't yet looked: financial
edge cases under concurrency, the drafting pipeline's hallucination boundary, and declared
protections never actually wired to their live callers.

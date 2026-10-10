# V2 NS008 — Law Brain / Institutional Intelligence

**DRAFT — DO NOT MERGE. DO NOT DEPLOY.**

- Base: `feature/vindex-v2-ns007-while-you-sleep` (`deac5d99`), NOT main and NOT NS006
- Head: `feature/vindex-v2-ns008-law-brain`
- `gh` is not available on this machine, so this PR was not opened automatically. Open it as a **Draft** with this text.

## What this is

A canonical **retrieval + trust + synthesis layer** over existing domain owners. It is not a chatbot, a new knowledge database, a second Genome, or a second Pinecone universe.

| Knowledge | Single owner (unchanged) | Law Brain trust class |
|---|---|---|
| Outcome of a matter | `outcome_log` (human, via `POST /api/learning/outcome`) | HUMAN_CONFIRMED_OUTCOME |
| Final work product | `staging_memory` approved + lawyer-approved (+ Pinecone if score ≥ 0.85) | LAWYER_VERIFIED_ARTIFACT |
| Lessons | `lessons_learned.status_lekcije` + `potvrdio` | confirmed / AI_CANDIDATE_LESSON / UNKNOWN_LEGACY |
| Office notes / relations | `memory_entries` / `memory_graph_edges` | HUMAN_MEMORY_NOTE / EXPLICIT_GRAPH_RELATION |
| Case facts / AI analysis | `predmeti`, evidence, hearings / Genome, contradictions | SOURCE_CASE_FACT / AI_WORK_PRODUCT |
| Corrections | `extracted_entities.corrected_value` (judge/court only) | HUMAN_CORRECTION |

Raw-matter authorization is **only** `shared/rag_acl.dozvoljeni_predmeti` (owner + active delegation). Same office ≠ access, and this is proven byte-for-byte (Task 19).

## New surface

- `GET /api/law-brain/predmeti/{id}`: matter context (similar matters with "Sličan jer: …", verified work, confirmed lessons, office notes, descriptive outcomes, data quality). **0 model calls, 0 credits, read-only**; a failed source → `DEGRADED`, never empty.
- `GET /api/law-brain/znanje`: office experience overview for Znanje.
- `GET /api/law-brain/pretraga?q=`: **explicit** verified-knowledge search (1 embedding, 0 completions, no credit).
- `POST /api/law-brain/predmeti/{id}/sinteza`: **the only model call**. Explicit click only, existing `precedenti` entitlement and price, durable idempotency. Claims are validated against supplied sources; invented refs, %, "šansa", law citations, and unsupported numbers are dropped.
- `POST /api/law-brain/rad/{work_id}/predlozi-znanje`: an **explicit** path from an ACCEPTED NS007 product to the **existing** staging review. Acceptance itself never becomes knowledge.
- V2 UI: an "Iskustvo kancelarije" section in **Znanje** and in **Matter → Analiza** (no new sidebar item, no new tab), plus "Znanje kancelarije" on accepted prepared work.

## Fixed along the way (pre-existing defects found by NS008)

- The generic `PATCH /api/predmeti/{id}` and the learning outcome route closed matters **without** a terminal event, leaving Case Actions open. There is now one durable `emit_matter_terminal` with a deterministic id.
- Outcome resubmission inflated `case_patterns` counters and re-ran GPT lessons.
- `learning_engine.save_lessons` accepted a caller-supplied "usvojena_praksa" status.
- Approved artifacts and lessons were reported as legally current with no evidence (false freshness). Their status is now UNKNOWN + "proverite izmene propisa" when they cite law.
- A revoked lawyer-verified draft kept being served by RAG. There is now one read-time validity rule (`vazece_overe`), applied in `retrieve_documents` and Law Brain.
- `rag_acl` did not apply the deletion tombstone to **delegated** matters.
- `vector_origin.freshness_weight` crashed on a naive `created_at`. One such vector emptied the entire office RAG branch, and a naive `valid_until` was ignored.
- Batched Supabase reads could be silently cut at 1000 rows. They are now paginated.
- ADR-0006 "case memory" lookup never existed. Office-scoped deterministic correction suggestions now exist for judge/court names.

## Not done on purpose

- **Task 18 skipped:** NS007 work items are version-gated by Genome and hearing, and Law Brain references have no version, so a revoked artifact could not invalidate a prepared product. The design for a future sprint is in the evidence file.
- **No migration 137:** bounded, sublinear reads were measured, so a materialized index is not justified yet.
- Physical deletion of revoked vectors (needs `content_sha256` on promoted documents). Revoked vectors are already excluded at read time everywhere.

## Evidence

The full task-by-task evidence (problem, owner, falsification, decision, tests, tenant, mutation, limitations) is in `docs/v2-recovery/NS008_OVERNIGHT_EVIDENCE.md`. Test totals are in its final section.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

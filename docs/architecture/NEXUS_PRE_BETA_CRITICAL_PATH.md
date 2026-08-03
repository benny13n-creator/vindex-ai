# Pre-Beta Critical Path (Intelligence Integrity)

**Mission:** Project Nexus, 2026-08-03. This is the intelligence-flow-specific critical path — it
layers on top of, not replaces, `docs/product/BETA_CRITICAL_PATH_2026-08-02.md`'s 9 named lawyer
scenarios (already verified completable end-to-end across `docs/product/LAWYER_DAY_REPORT.md` and
`docs/product/BETA_LOCKDOWN_REPORT.md`). This path is specifically about whether the intelligence a
lawyer receives is internally consistent, durable, and provenance-tracked — not whether the workflow
screens exist.

---

## Must-fix before Beta (Critical Flow Integrity + Security, per the mission's own priority order)

1. **Resolve `PREDMET_KREIRAN`'s durability gap** (`NEXUS_TOP_20_BREAKPOINTS.md` #9) — the single
   highest-priority open item. Before fixing: verify `services/case_pipeline.py::run_case_pipeline`'s
   idempotency (safe to run twice for the same case?). If yes, mirror `GENOME_UPDATED`'s durable-outbox
   pattern. If no, a different durability strategy is needed — this is a real architecture decision,
   not a guess.
2. **Write Smart Intake's extracted judge/court/opponent entities onto `predmeti.tuzilac`/`tuzeni`**
   (`NEXUS_TOP_20_BREAKPOINTS.md` #8) — small, well-scoped, unlocks 2 more Litigation Intelligence
   features with zero lawyer typing required.
3. **Decide the AI action provenance strategy** (`model`, `prompt version`, `output hash` — currently
   captured nowhere). For a legal product, an inability to answer "which model version produced this
   analysis, and can we verify the output hasn't been altered" is a real compliance-adjacent gap, not
   just a nice-to-have. This needs a founder-level decision on how much provenance infrastructure to
   build (a schema change across multiple tables), not a quick patch.

## Should-fix before Beta (Reliability)

4. **`DOCUMENT_JOB_FAILED` needs a real handler** — a failed OCR/classification job currently produces
   zero signal to anyone.
5. **Fold Case Genome/Briefing into at least one existing hallucination guardrail** — Quality Gate's
   citation-existence check or the Legal Reasoning Engine's SOURCE-n constraint, whichever is the
   smaller integration lift once scoped.

## Can wait past Beta (Automation, Optimization)

6. Outcome Intelligence / Judge-Court Profiler reading Case Genome (same low-risk pattern already
   proven twice this engagement).
7. `knowledge_profiles`'s phantom-data-source problem — founder decision on build-vs-retire.
8. Memory Graph's data-population strategy — founder decision.
9. The two founder-decision-gated duplicate-feature pairs (CSV import, WhatsApp) — unchanged from
   Beta Lockdown/Invisible Features.
10. `cron_daily`'s duplicate `_check_escalations()` call — cosmetic, self-healing, zero urgency.

---

## What does NOT need further work (verified, not assumed)

- The 9 named lawyer scenarios in `BETA_CRITICAL_PATH_2026-08-02.md` — confirmed completable end to
  end, most recently re-verified in `docs/product/BETA_LOCKDOWN_REPORT.md`'s Beta Acceptance Test.
- Tenant isolation on the highest-traffic data paths — swept in Beta Lockdown, one real gap found and
  fixed (`BL-001`), everything else confirmed correctly scoped.
- Case Genome's core reasoning quality (rich, domain-specific, with a working rule-based verification
  layer for contradiction claims) — no defect found this mission.
- Semantic search — confirmed the best-connected node in the entire system, zero action needed.

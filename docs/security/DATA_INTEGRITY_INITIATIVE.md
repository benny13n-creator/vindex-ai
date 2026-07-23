# Vindex AI — Data Integrity Initiative (Epic)

**Date opened:** 2026-07-23
**Status:** Epic opened, **not scoped in detail, not started.** This document exists to give the pattern discovered as SEC-033 a name and a home, deliberately without solving it now — per explicit instruction not to resolve this "usput" (in passing) while focused on SEC-031.
**Lifecycle stage:** 1 — Observation, being formally converted into a tracked initiative rather than left as a single Gap Register line. See `FINDING_LIFECYCLE.md`.

---

## Why this is an epic, not a bug fix

SEC-033 started as one observation: `klijenti.user_id` has no foreign key to `auth.users`. While building `SEC031_FK_GRAPH.md`, the same shape — an owner/creator/reference column with zero `REFERENCES` constraint — was independently confirmed, by direct reading of the `CREATE TABLE` source (not inference), in at least 8 more tables across 4 feature areas built at different points in this project's history:

- **Firm/workflow subtree** (`migrations/018_kancelarija.sql`, `045_firm_intelligence.sql`): `kancelarije.admin_uid`, `kancelarija_clanovi.user_id`, `zadaci.kreirao_uid`/`dodeljen_uid`/`predmet_id`
- **Org intelligence subtree** (`migrations/040_faza5_org_intelligence.sql`): `style_profili.user_id`, `style_analize.user_id`, `knowledge_profiles.user_id`, `knowledge_upiti.user_id`
- **Learning loop** (`migrations/037_learning_loop.sql`): `recommendation_log.user_id`
- **Intake pipeline** (`migrations/073_intake_foundations.sql`): `intake_jobs.uploaded_by`, `intake_jobs.predmet_id` (also typed `TEXT` instead of the `UUID` used everywhere else)

Four unrelated features, built at different times, independently missing the same constraint. That is not a single bug — it's an **architectural smell**: something about how new tables get created in this project doesn't reliably carry a "reference columns get a real FK" step. Fixing `klijenti` alone would leave the actual cause (whatever it is — no schema-review checklist, no linting for it, copy-pasted patterns propagating the gap) untouched, and the same shape would likely appear again in the next feature.

---

## Proposed scope (for future scoping, not decided now)

1. **Systematic census** — every table in the schema, every column that is clearly meant to reference another table (by name convention: `*_id`, `*_uid`, plus the known non-conforming ones like `admin_uid`, `uploaded_by`, `kreirao_uid`) but has no `REFERENCES` clause.
2. **Categorize each finding**: missing FK entirely / type mismatch (`TEXT` vs `UUID`) / nullable where it probably shouldn't be / FK present but wrong `ON DELETE` semantics (a SEC-031-adjacent question, worth cross-checking against that work rather than duplicating it).
3. **Orphan-row check** — for each, whether production actually has rows whose reference value doesn't correspond to a real parent row (this needs production access, same "can't prove from repo" boundary as SEC-031's Production Reality Gate).
4. **Root-cause question, not just a symptom fix** — why did this pattern repeat four times. Candidates worth asking about (not concluded here): no schema-change checklist/review step, a specific early table used as a copy-paste template that itself lacked the FK, or a deliberate-but-undocumented choice (e.g., avoiding FK overhead for tables expected to be high-write) that later got copied without the original reasoning.
5. **One coherent remediation**, once the above is understood — not N one-off migrations designed independently of each other.

---

## Explicit boundaries

- **Not started.** No table beyond the ones already found by accident has been checked yet.
- **Not blocking SEC-031.** SEC-031's migration plan and `klijenti`'s specific gap are already fully separated in the existing documents; this epic does not need to resolve before SEC-031 can proceed through its own gates.
- **Not assumed to be security-critical** at the same severity as SEC-031 — most likely outcome is data-quality/integrity risk (orphaned rows, silent inconsistency) rather than a destruction or access risk, but this is itself an assumption that the census (once done) should confirm or correct, not something concluded here.

## Next step, when this is picked up

Scope a proper `SEC033_INTEGRITY_AUDIT.md` following the same discipline as SEC-031's chain (impact analysis → design → plan → proof), starting from the systematic census in §2 above — not from assuming the fix shape in advance.

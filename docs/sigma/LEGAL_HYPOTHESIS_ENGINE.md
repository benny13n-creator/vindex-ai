# Legal Hypothesis Engine — Program Sigma, Master Sprint 003 (2026-08-06)

Phase 5 deliverable: every Gap is a hypothesis, never an automatically-confirmed fact. Statuses: OPEN,
CONFIRMED, REJECTED, RESOLVED, SUPERSEDED. The system must never auto-confirm a hypothesis without evidence.

## What's already built this sprint, satisfying part of this requirement

`shared/gap_engine.py` (new this sprint) already carries a `hipoteza: bool` field on every Gap record —
`False` only for `identify_case_problems`' own deterministic findings (literally true by construction, not
an inference), `True` for everything GPT-derived (Genome's `nedostaje[]`, Genome's `kontradikcije[]`). This
is the epistemic-honesty half of Phase 5's own requirement, already satisfied by construction: nothing in
this module ever asserts a GPT-derived finding as fact.

**What's NOT yet built**: a persisted, queryable STATUS lifecycle (OPEN → CONFIRMED/REJECTED/RESOLVED/
SUPERSEDED) for a Gap over time. Today, a Gap record is computed fresh on every read (`collect_case_gaps`)
— there is no row anywhere recording "a lawyer looked at this specific finding and confirmed/rejected it."

## The existing precedent this design is built on

`lessons_learned.status_lekcije` (`migrations/039_epistemic_confidence.sql:12-16`) already implements
almost exactly this pattern, live, proven, for a different domain (AI-proposed practice lessons):

```sql
status_lekcije   TEXT CHECK (status_lekcije IN ('predlog_ai', 'usvojena_praksa', 'odbijena', 'zastarela')),
pouzdanost       TEXT CHECK (pouzdanost IN ('niska', 'srednja', 'visoka')),  -- SEPARATE from status
potvrdio         TEXT,        -- who confirmed
potvrdjeno_at    TIMESTAMPTZ, -- when
```

The key design property worth reusing: **confidence (`pouzdanost`) and status are separate columns.** A
finding can be `predlog_ai` (proposed, unconfirmed) with `visoka` confidence — confidence describes how
sure the SYSTEM is; status describes whether a HUMAN has acted on it. Never auto-transitioning `predlog_ai`
→ `usvojena_praksa` without `potvrdio` being set is exactly Phase 5's own "sistem nikada ne sme automatski
potvrditi hipotezu bez dokaza" rule, already implemented once in this codebase.

Two weaker cousins confirm this is a recurring, deliberate pattern, not a one-off:
`migrations/082_agent_recommendations.sql:21` (`pending/accepted/rejected`) and
`migrations/088_staging_memory.sql:40` (`pending/approved/rejected`).

## Mapping Phase 5's own 5-state vocabulary onto this precedent

| Mission's state | `lessons_learned` equivalent | Meaning for a Gap |
|---|---|---|
| OPEN | `predlog_ai` | Computed, shown to the lawyer, not yet acted on |
| CONFIRMED | `usvojena_praksa` | A lawyer explicitly confirmed the gap is real (e.g. "yes, we're missing this document") |
| REJECTED | `odbijena` | A lawyer explicitly said this isn't actually missing (a false positive, human-confirmed) |
| RESOLVED | *(new — no direct equivalent)* | The underlying fact changed — the document/evidence was subsequently provided |
| SUPERSEDED | `zastarela` | A newer Genome refresh or document made this specific finding obsolete without a human explicitly resolving it |

## Why a full persisted implementation was not built this sprint

Two real design decisions need product input before a migration is safe to write:

1. **Where does a Gap's own stable identity live for status tracking to attach to?** Deterministic gaps
   (`identify_case_problems`) and contradiction gaps (Sprint 002's own `contradiction_dedupe_key`) already
   have stable identity. Genome's own holistic `nedostaje[]` items do NOT yet have one — two Genome
   refreshes describing "we're missing a delivery receipt" in slightly different words would need the SAME
   kind of stable-identity fix Sprint 002 built for contradictions (anchor on something more stable than
   free text) BEFORE a status column would mean anything reliable across refreshes. Building this without
   that anchor first would risk the identical flicker bug Sprint 002 found and fixed for contradictions —
   recorded as `SIGMA-015`, a prerequisite for any Gap-status migration.
2. **Which table owns Gap status?** A new dedicated `case_gaps` table (mirroring `case_actions`' own
   dedupe_key + partial-UNIQUE-index pattern, this program's own twice-proven idiom), or an extension of
   `case_actions.status`'s own CHECK constraint (adding `confirmed`/`rejected`/`superseded` alongside
   `open`/`closed`)? The former keeps `case_actions` semantically clean (still purely "what needs doing");
   the latter reuses more infrastructure but changes an already-shipped, already-tested table's own
   contract. A real architecture decision, not a mechanical one.

## Recommended direction (not implemented this sprint)

A NEW `case_gaps` table, modeled directly on `lessons_learned.status_lekcije`'s own proven column shape
(`status`, separate `pouzdanost`, `potvrdio`/`potvrdjeno_at`), keyed by a stable Gap identity (requires
`SIGMA-015` first for the Genome-sourced gap types). `shared/gap_engine.py`'s own `collect_case_gaps`
becomes the TARGET-set computation (mirroring `_compute_target_actions`'s own already-proven role) that a
new, equally-mirrored reconcile consequence would diff against existing open `case_gaps` rows — the EXACT
established idiom this whole engagement has used 3 times now (`case_actions` migration 099,
`notifications` migration 101, both Program Omega/Sigma) — a 4th application of a proven pattern, not a
new one. Recorded as `SIGMA-016`, depends on `SIGMA-015`.

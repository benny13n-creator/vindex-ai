# DOCUMENTATION_CERTIFICATION — Program Lambda, Certification 008

Covers Team 12 (Documentation Drift), Team 13 (Migration & Schema Drift), and Team 11 (Frontend/Backend
Consistency — a form of drift between two live systems rather than doc-vs-code, included here since it's
the same underlying failure class: a claim/signal one side makes that the other side never checks).

## Documentation drift — fixed this sprint

**`docs/architecture/SOURCE_OF_TRUTH_REGISTRY.md`** listed 4 duplicate-authorship bugs as unresolved
Critical items (Court Predictor `procenat`, business audit trail, request correlation ID, correlation ID
minting) that were actually fixed in commit `a5f4eeb` ("Program Alpha," 2026-08-04) — the registry doc
itself was committed 33 seconds after that fix, in the same session, but its table content was never
updated to match. The document's own "Critical: 6" tally was consequently wrong. Corrected this sprint,
with one further correction the coordinator caught independently while fixing the doc: the certifying
team's own recount ("2 remaining Critical") was itself off by one — direct verification against current
code confirmed the true count is 3 (Strategy Engine win-probability, document classification, and firm
memory for AI — the last of which both `api.py::_fetch_firm_memory_context` and
`routers/firm_memory.py::kontekst_za_ai` still independently implement).

**Duplicate debt-register tracking**: `LAMBDA-003` and `LAMBDA007-DEAD-001` were two separate entries
describing the identical finding (`routers/onboarding.py`'s dead endpoints) — Certification 007's own
investigation didn't cross-check the register before logging it as new. Merged into one tracked entry.

## Migration & schema drift — fixed this sprint

**`predmet_dokumenti.redni_broj`/`.tekst_sadrzaj`** are core, pervasively-used columns (including in
INSERT statements) with **zero migration file, anywhere in the repository, ever creating them** — added
directly to live Supabase outside the tracked migration system at some point. `api.py`'s own code even
carries a comment referencing a migration that doesn't exist. A fresh environment built from `migrations/`
alone would break document upload/citation numbering entirely. Fixed via a new migration (105, drafted,
idempotent `ADD COLUMN IF NOT EXISTS`) that makes the schema reproducible from this repo, plus a defensive
fallback in `routers/drafting.py` (the one write site with no prior guard) for the window before it's
applied.

**Migration numbering gap 027-035** (9 numbers never used, confirmed via full git history, not a lost file)
— noted, cosmetic, no functional impact, no action needed.

## Frontend/backend consistency — fixed this sprint

3 confirmed cases of "the backend computes an honest signal, the frontend silently never reads it" — the
same failure shape 2 prior missions already found and fixed once each (ZTC-002, NEX-003), now closed at 3
more sites: Smart Intake finalize's `dokument_povezan`/`klijent_nesiguran` fields, Court Predictor's
`sud_neslaganje_sa_predmetom` court-mismatch warning, and Global Search's `nepotpuno` partial-failure
signal. All 3 fixed by wiring the existing backend field into the existing frontend response handler — zero
backend changes needed, the data was already there.

## Verified accurate, no drift found

All 6 spot-checked claims in `VINDEX_CORE_CONSOLIDATION.md` verified true against current code (a
self-correcting document). Migration-count claims in `docs/lambda/RLS_CERTIFICATION.md` verified correct
(94 migrations at time of writing, now 96 with this sprint's own 2 additions). `SECURITY_SPRINT_PHASE1.md`'s
"79 migracija" figure is a dated point-in-time report, not a living doc — not counted as drift.

**Verdict**: 2 genuine documentation-drift findings, 2 schema-drift findings, 3 frontend/backend consistency
findings — all 7 fixed this sprint. The certification process itself demonstrated its own value here: a
sub-team's own count was independently caught and corrected by the coordinator before publication, the
exact kind of cross-check this program's evidence discipline exists to enforce.

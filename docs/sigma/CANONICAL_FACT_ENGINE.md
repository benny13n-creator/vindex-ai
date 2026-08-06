# Canonical Fact Engine — Program Sigma, Master Sprint 002 (2026-08-06)

Phase 2/3 deliverable: prove facts (events, evidence, dates, participants) have exactly one owner, that
ambiguity routes to review rather than silent merge, and assess Phase 3's own requirement that a timeline
stay consistent as documents add/modify/close/void events.

## Phase 2 — no silent merging, confirmed

Every canonical "find-or-create" mechanism this sprint traced (client, case) never auto-merges ambiguous
matches — routes to `review_required`/`ambiguous` instead (`shared/case_assimilation.py`, unchanged from
Sprint 001, re-verified this sprint). This is the mission's own explicit requirement
("Ako postoje različite interpretacije, nikada ih ne spajati automatski. Route to Review Required.") —
already satisfied for the 2 fact types that HAVE merge logic at all.

**Where this requirement does not yet apply, because no merge logic exists to violate it**: evidence
(`predmet_dokazi`) and timeline events (`predmet_hronologija`) have NO find-or-create/merge step
whatsoever — every new extraction is blindly inserted as a new row. This trivially satisfies "never
silently merge" (there's no merge to be silent about) but also means there is no DEDUPLICATION at all for
these 2 fact types — a genuinely different problem (duplicate facts, not wrongly-merged facts), tracked as
`SIGMA-004`'s own extension (Evidence Graph doc) and `TIMELINE_FORENSIC_REPORT.md`'s own Phase 7 findings.

## Phase 3 — Canonical Timeline Engine: what a new document can and cannot do today

The mission's own Phase 3 requires a new document be able to: add an event, modify an event, close an
event, void an event, change a date, change a procedural status — while the timeline stays consistent.

**Add**: fully supported — any of `predmet_hronologija`'s own 15 canonical writers (`TIMELINE_REGISTRY.md`).

**Modify / close / void an existing timeline entry**: **not supported today** — `predmet_hronologija` is
strictly append-only (zero UPDATE/DELETE call sites, confirmed this sprint). A later document cannot
reference or retract an earlier `predmet_hronologija` row.

**This is not uniformly true across the platform** — 2 adjacent tables ALREADY support exactly this kind
of state transition, for their own narrower fact types:
- `rocista` (hearings) has a `status` column (`zakazano`/`održano`/`otkazano`) — `case_actions`' own Rule 1
  reads it directly, and a hearing's status genuinely transitions.
- `case_actions` has `status` (`open`/`closed`) with `closed_at` — an action genuinely closes when its
  underlying fact resolves, reconciled automatically on every Case Evolution refresh (Sprint 003).

**The gap is specific to `predmet_hronologija` itself** — the raw narrative/deadline log. Adding
supersede/void semantics there would mean: a new column (e.g. `status`, `superseded_by`, `voided_at`,
`void_reason`), and — more consequentially — updating some subset of the 15 independent writers to actually
USE it (an append-only writer doesn't need to change; a writer that wants to correct/retract a PRIOR entry
would). This is a genuine schema and behavior decision (which writers get supersede capability, and what
lawyer-facing UI would trigger "void this timeline entry"), not a bug fix.

**Why not fixed this sprint**: this is new functionality, not a mechanical wiring gap (unlike Master Sprint
001's `PREDMET_KREIRAN` fix) — retrofitting revision semantics onto a 15-writer append-only table without a
clear design for WHO gets to supersede/void an entry and WHY (only the same writer that created it? any
later document? only a lawyer manually?) risks exactly the kind of rushed, unreliable change this
engagement's own established discipline avoids. Recorded as `SIGMA-009`.

**What already IS consistent, without needing revision semantics**: because `predmet_hronologija` never
deletes or silently overwrites, "nikada ne brisati staru činjenicu" (never delete an old fact) is satisfied
BY CONSTRUCTION for this table — a structural strength worth stating plainly, not just a gap. The
consistency the mission asks for ("Timeline mora ostati konzistentan") holds for the ADD-only case today;
it is untested/unsupported for the modify/close/void case, which is the honest, precise scope of what
remains open.

## Recommended direction for `SIGMA-009` (not designed in full this sprint, a starting point only)

A minimal, additive schema extension — `status TEXT DEFAULT 'active'` +
`superseded_by UUID REFERENCES predmet_hronologija(id)` + `voided_at TIMESTAMPTZ` — would let a FUTURE
document reference and supersede a SPECIFIC prior entry by its own stable `id`, without requiring every one
of the 15 existing writers to change (new writes default to `status='active'`, old rows are unaffected).
The harder design question — which lawyer/system action actually triggers a supersede/void, and how a
lawyer discovers a prior entry was superseded — needs product input before implementation, consistent with
this whole engagement's own standing practice of escalating UX-shaped decisions rather than guessing.

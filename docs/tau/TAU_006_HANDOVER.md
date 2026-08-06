# Tau 006 Handover — Canonical Context Migration Factory

Program Tau, Master Sprint 005 migrated `court_predictor.py` (7 endpoints) onto `shared/case_context.py`
exclusively — the 2nd file-scale migration after Sigma 005's Case Commander work. This is the founder's own
proposed direction for what comes next: **not** a 3rd individually-scoped file migration sprint, but a
standardized migration pattern so the remaining 16+ files (`TAU-012`) can move with much lower risk and
much less token spend per sprint than treating each one as its own project.

## Why a factory approach is justified now, not earlier

Two file-scale migrations (Sigma 005's Case Commander, this sprint's Court Predictor) is exactly enough data
points to extract a real, tested pattern rather than a guessed one. Both migrations independently converged
on the same 3-part shape without being designed as a template in advance:

1. **A fail-soft fetch wrapper** around exactly one `build_case_context()` call — `None` on missing
   `predmet_id` or on any exception, never raises, never blocks the endpoint's own pre-existing behavior.
   (This sprint: `_dohvati_case_context_ako_postoji`. Case Commander: its own equivalent from Sigma 005.)
2. **A presentation/formatting function** over the canonical output — turns the dict into prompt text, adds
   nothing the canonical source didn't already provide. (This sprint: `_case_context_blok`. Case Commander:
   `_formatiraj_kontekst`. `case_intelligence.py`: `_build_context_text`.) **Three independent
   implementations of the same shape** is itself evidence this is a stable pattern, not a one-off.
   Named because the mission's own "no new context builder" prohibition otherwise reads (wrongly) as
   forbidding this necessary, non-competing step — worth writing down once so future sprints don't
   re-litigate whether a formatting function counts as a violation.
3. **Per-endpoint mode/depth decision, made explicitly, not defaulted** — full context (with documents) vs
   lightweight (readiness/gaps/deadlines text only) vs consistency-check-only (no injection, just a
   cross-check field), chosen by what the endpoint's own reasoning task actually needs, not applied
   uniformly. `judge_profile`'s no-case-description-field shape was this sprint's clearest proof that a
   uniform "always inject full context" rule would have been wrong for at least 1 of 7 endpoints — this
   won't be the last file where that's true.

## What a factory sprint should produce

Not code shared across files (a real shared helper risks becoming exactly the "new wrapper" the mission
language keeps prohibiting, for good reason — each file's own call shape differs enough that force-sharing
code would fight the endpoints instead of fitting them). Instead, produce a **repeatable checklist/template
document** (`docs/tau/CANONICAL_MIGRATION_TEMPLATE.md` or similar) capturing the sequence proven twice now:

1. Forensic re-verification per endpoint (not per file) — confirm live-caller status, request shape,
   whether a case-description field exists at all, before assuming the standard treatment applies.
2. Fail-soft fetch wrapper (copy the shape, not the code) + local formatting function, both file-local.
3. Explicit mode decision per endpoint: full / lightweight / consistency-check-only / none (with a stated
   reason, following this sprint's own certification-table format).
4. Where a deterministic grounding hook is possible (a hard cap, a cross-check field, a replace-not-add
   scoring rule) — prefer it over pure prompt instruction, and adversarially test it (this sprint's
   readiness-cap test is the concrete example to point at).
5. Full `supa.table()` call-site inventory at the end, to prove no bypass — this sprint's
   `GPT_CONTEXT_USAGE_AUDIT.md` format is the reusable template for that specific step.
6. Token/cost delta measurement before/after, same shape as `PERFORMANCE_IMPACT_REPORT.md`.

The goal of writing this down is that a factory-sprint's own token budget per file should shrink
substantially versus this sprint's — most of what took real reasoning time here (working out the 3-part
shape from scratch, deciding how to handle `judge_profile`'s exception, designing the DC-004-invariant-safe
`confidence_check` extension) is now a documented decision, not something the next sprint has to re-derive.

## Which of the 16+ remaining files to pilot the factory on

Per `TAU-012`'s own list (`drafting.py`, `matter_intel.py`, `hearing_cc.py`, `evidence_graph.py`,
`multi_agent.py`, `digital_twin.py`, `decision_replay.py`, `strategy_simulator.py`, `health_index.py`,
`outcome_intel.py`, `precedenti.py`, `zastarelost.py`, `evidence.py`, `doc_templates.py`, `zadaci.py`):

- **`hearing_cc.py`** — still the single best pilot candidate (named by Master Sprint 004's own handover,
  still true). It has its own rich 7-table bespoke builder (`_load_all_context`) — a genuine 3rd independent
  "gather everything" implementation, functionally overlapping `build_case_context()` almost entirely. This
  makes the migration more mechanical (swap an existing rich builder for the canonical one, verify no field
  is lost) than building case-awareness from near-zero the way `court_predictor.py` required — a good first
  test of whether the factory template actually reduces effort, since the harder "does GPT even see the
  case" question is already answered yes for this file.
- **2-3 more from the list, chosen by actual traffic** if available (no traffic telemetry exists anywhere in
  this codebase per Master Sprint 004's own finding — this itself might be the factory sprint's own Phase 1,
  same as this sprint's Phase 1 was forensic re-verification before touching code).

## What NOT to do

- Don't build a shared, importable helper module for the fetch-wrapper/formatter pair — each file's own
  request shape and reasoning task differs enough (proven twice now: Case Commander's shape, Court
  Predictor's 7-endpoint variety including `judge_profile`'s exception) that a shared abstraction would
  either be too generic to be useful or would silently force a wrong mode on some endpoint. Template the
  PATTERN, not the code.
- Don't skip Phase 1 forensic re-verification per file just because the overall pattern is now known — this
  sprint's own Phase 1 found a genuinely new detail (`judge_profile`'s missing case-description field) that
  a rushed pass would have missed, and that detail changed the correct migration for one endpoint.
- Don't expand `shared/case_context.py`'s own contract (`TAU-013`) in the same sprint as a migration push —
  changing the target while migrating multiple files onto it compounds risk for no benefit, same reasoning
  Master Sprint 004's own handover already gave for `TAU-011`/`TAU-012` sequencing.

## What's already solid, don't re-litigate

`shared/case_context.py`'s 13-field contract, the Document Visibility Engine (500/1000-doc scale, reused
unmodified a 2nd time this sprint), the deterministic-cap grounding pattern (now proven twice: DC-004's
`confidence_check` scoring, this sprint's readiness-based percentage cap) are all confirmed sound across two
independent file migrations. Build on them.

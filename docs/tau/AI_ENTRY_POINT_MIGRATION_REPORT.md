# AI Entry Point Migration Report — Program Tau, Master Sprint 002, Phase 5

**Mission's own mandatory list**: `case_intelligence.py`, `copilot.py`, `morning_briefing.py`, `strategija.py`.
**Status**: 3 of 4 migrated onto the Canonical Case Context (`shared/case_context.py::build_case_context`).
The 4th (`strategija.py`) is explicitly out of scope, not deferred — see below for why, verified against
current code, not assumed.

---

## `routers/strategija.py` — cannot be migrated; not a context builder

`CONTEXT_BUILDER_REGISTRY.md`'s own scoping correction, restated here since it directly affects this
report: `routers/strategija.py`'s 7 request models have **no `predmet_id` field on any of them**
(confirmed by reading `routers/strategija.py:65-399` in full) — it never queries
`predmet_dokumenti`/`predmet_dokazi`/`case_dna`/`case_actions` anywhere. It is architecturally a "paste
your own case description" tool, not a case-ID-driven endpoint. There is no existing context-fetch code to
swap for `build_case_context()` — migrating it would mean **adding** a `predmet_id`-based invocation mode,
a feature change, not the plumbing change every other item in this report is. Not implemented this sprint;
flagged as a legitimate future feature request, not a bug, not deferred debt.

(`TAU-004` — `strategija.py`'s `_V2_SYSTEM` prompt GPT-inventing risks/gaps/next-steps — is a *separate*,
unaffected finding from Tau Sprint 001, about decision-making boundary, not context visibility.)

---

## `routers/copilot.py` — migrated (both GPT context-building handlers)

**Before**: `_handle_analiza_predmeta` and `_handle_plan_predmeta` both queried
`predmet_dokumenti.select("naziv_fajla,status")` — GPT knew filenames existed, never saw a word of
content.

**After**: both now fetch `id, naziv_fajla, created_at, tekst_sadrzaj, status, redni_broj` (ordered by
`redni_broj`) and run the fetched rows through the Document Visibility Engine's own Layer 4 functions
(`shared.case_context._select_documents` / `_excerpt`, imported directly — reused, not reimplemented),
capped at 5 documents with an 800-char excerpt budget each (copilot is a lightweight assistant, not a
full case dossier — a smaller budget than `case_commander.py`'s own 2000/doc, deliberately). Documents not
shown are counted in a trailing note ("+ još N dokumenata u dosijeu"), not silently dropped.

**Deliberately NOT changed**: the existing Genome-summary rendering (`genome_ctx`), the `case_actions`
next-action override (`shared.case_readiness.top_open_action`), and the `shared.gap_engine` missing-evidence
override — all already correct, already tested, fixed in Sigma Sprint 003/004. This sprint's own finding
(Phase 1) was specifically "document content is structurally excluded" — that is the one thing changed
here; rewriting already-proven logic would have been unnecessary risk for no benefit.

**Tests**: `tests/test_synapse_copilot_genome_context.py::test_document_content_reaches_prompt_program_tau_002`
proves real document text now reaches the GPT-facing prompt. All 63 pre-existing copilot-adjacent tests
pass unchanged.

## `routers/case_intelligence.py` — migrated (added, not replaced)

**Before**: `_gather_case_data` had zero query for `predmet_dokumenti` or `predmet_dokazi` anywhere —
confirmed by a full read in Phase 1. The briefing synthesized lessons/firm-DNA/patterns/alerts/decisions
with no view of the case's own documents, evidence, open actions, or deadlines.

**After**: `_gather_case_data`'s own `asyncio.gather` now includes a `build_case_context(predmet_id,
user_id, supa)` call alongside its existing 5 sub-queries. `_build_context_text` renders 4 new sections
(DOKUMENTI U DOSIJEU, DOKAZI, OTVORENE AKCIJE, ROČIŠTA/ROKOVI) from the result, bounded (4 documents, 500
chars/excerpt; evidence/actions/deadlines are already terse structured rows) to protect the existing
10,000-char total budget (`_pozovi_briefing_api`) from being consumed by the new sections at the expense
of the pre-existing lessons/firm-DNA/decisions content.

**Cost accepted**: one redundant `predmeti` row fetch (`build_case_context`'s own internal fetch, in
addition to `_gather_case_data`'s own narrower-column fetch) — a single indexed-row read, judged an
acceptable, minor cost against building a second bespoke document/evidence/action reader.

**Deliberately NOT changed**: the existing rich Genome rendering (built directly from raw `case_dna`,
more detailed than `CaseContext.key_facts`' own minimal 3-field projection) is untouched — Phase 1 did not
find it broken.

**Tests**: `tests/test_case_intelligence_briefing_alerts_fix.py`'s 2 new tests
(`test_context_text_includes_documents_evidence_actions_deadlines_program_tau_002`,
`test_context_text_omits_new_sections_when_case_context_missing`) prove the new sections render correctly
and degrade to nothing (not a crash, not an empty header) when `case_context` is absent. All 5
pre-existing tests in that file, plus 61 other case-intelligence-adjacent tests, pass unchanged.

## `routers/morning_briefing.py` — migrated (flagship call site only; 2 others marked LEGACY)

**Before**: zero references to `predmet_dokumenti`/`case_dna`/`predmet_dokazi` anywhere in the file, across
all 3 of its own GPT call sites (confirmed by a fresh full-file grep, Phase 1).

**After** (`_generiši_briefing`, `GET /api/briefing/daily` + `POST /api/briefing/cron` — the flagship,
highest-visibility call site): each of the (up to 10) cases shown in the "AKTIVNI PREDMETI" section now
gets a `build_case_context(predmet_id, uid, supa, include_documents=False)` call, and the case's canonical
`readiness.status` is appended to its own line (e.g. `readiness: CRITICAL_GAP`). `include_documents=False`
is the **lightweight mode added this sprint specifically for this consumer** (`shared/case_context.py`) —
a portfolio-wide loop over multiple cases doesn't need document excerpts for a one-line status annotation,
and paying for a document fetch + excerpt pass on every case, every morning, for signal this digest
doesn't use would be exactly the kind of unnecessary cost Phase 6 exists to prevent. A failed
`build_case_context()` call for one case degrades that one case's line (no `readiness:` suffix), not the
whole briefing — matching this file's own established fail-soft convention for every other sub-query.

**Explicitly marked LEGACY this sprint** (per the mission's own escape valve — "ako neki modul ne može
odmah biti migriran, mora biti eksplicitno blokiran ili označen kao LEGACY"), not silently skipped:
- `_ai_prioritizacija_alertova` (`POST /api/briefing/nightly-intelligence`) — operates on an
  already-fetched, already-derived alert list (from `_generiši_alerts_za_korisnika`, itself reading
  `rocista`/deadline tables only), not raw case data. A smaller, lower-priority gap than the flagship
  digest; not migrated this sprint.
- The `today_focus` call site (`GET /today-focus`, `max_tokens=120`) — same metadata-only shape, same
  reasoning.

**Scope boundary, stated explicitly**: this migration closes the CONTEXT gap only (GPT now sees real
readiness signal instead of bare case names). It does NOT address whether GPT should still be the one
*authoring* "Danas zahteva pažnju"/"Preporuka za danas" at all — that is a decision-boundary question
(`TAU-003`, Program Tau Master Sprint 001's own debt register), deliberately out of this sprint's own
"Canonical Case Context Engine" scope.

**Tests**: `tests/test_tau002_morning_briefing_context.py` (2 new tests) prove readiness status reaches the
GPT prompt and that a per-case lookup failure degrades gracefully. 32 pre-existing morning-briefing-adjacent
tests pass unchanged.

---

## Summary

| Module | Migrated? | What changed | What didn't |
|---|---|---|---|
| `case_commander.py` | Already done (Sigma 005) | N/A — reference implementation | N/A |
| `copilot.py` | Yes, both handlers | Document filenames → real excerpts (Document Visibility Engine) | Genome/case_actions logic (already correct) |
| `case_intelligence.py` | Yes | Added documents/evidence/actions/deadlines (previously zero) | Existing rich Genome rendering |
| `morning_briefing.py` | Partial — 1 of 3 call sites | `_generiši_briefing` now shows per-case readiness | 2 metadata-only call sites, explicitly marked LEGACY |
| `strategija.py` | No — not applicable | N/A | Not a context builder; would need a new `predmet_id` feature, not a migration |

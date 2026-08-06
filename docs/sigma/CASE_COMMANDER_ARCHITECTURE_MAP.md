# Case Commander Architecture Map — Program Sigma, Master Sprint 005 (2026-08-06)

Phase 1 deliverable: every Case Commander GPT recommendation surface, mapped endpoint → prompt → input →
output → consumer → evidence source → classification (A/valid projection, B/duplicated intelligence,
C/stale, D/no legal origin). Two forensic forks, re-verified against actual code, not summary.

## Headline finding, before the per-function map: zero live callers, contradicting a prior sprint's own claim

Repo-wide grep of `static/vindex.js` (the only frontend file) for the literal string `commander` returns
**exactly one hit — a code comment**, no live `fetch`/XHR call anywhere. That comment documents that
Program Omega, Final Sprint 005 (2026-08-06) deleted ~440 lines of dead frontend code, including the
functions that called `POST /api/commander/analiza` and `GET /api/commander/jutarnji`, because their own
DOM targets were unreachable — see `docs/omega/SHADOW_WORKFLOW_AUDIT.md:12-37`. **That audit's own written
verdict** (lines 34-37, 112-119) claimed the backend endpoints themselves "remain unaffected" — implying
some other live caller existed. **Direct, repo-wide re-verification this sprint found no such caller
anywhere** — this is a correction to that prior sprint's own conclusion, not a new regression. This is why
this sprint's own migration carried zero live-user risk: no product surface today displays any Case
Commander response, in the old shape or the new one.

## Per-function map

| # | Function | Endpoint | Model | Input reads canonical sources? | Live caller? | Evidence field (pre-sprint) | Classification (pre-sprint) |
|---|---|---|---|---|---|---|---|
| 1 | `commander_analiza`'s own STATUS/NEDOSTAJE/RIZICI/PREPORUCENI POTEZ/VREMENSKI PRITISAK sections | `POST /api/commander/analiza` | gpt-4o | No — raw `predmeti`/`rokovi`/`predmet_dokumenti`/`predmet_komentari` only | None found | None | D (no legal origin) — corrected from Sprint 004's "duplicated intelligence" framing to DEAD-and-evidence-less |
| 1b | `commander_analiza`'s own PROTIVNIKOVA STRATEGIJA/SUDSKA PRAKSA sections | (same endpoint) | gpt-4o | No — and correctly so, no canonical source exists for these questions | None found | None | A — legitimately GPT-advisory, no canonical duplicate to defer to |
| 2 | `commander_quick_check` | `POST /api/commander/quick-check` | gpt-4o-mini | No | None found | None | D (pre-sprint) |
| 3 | `commander_checklist` | `POST /api/commander/checklist` | gpt-4o-mini | No (generic procedural template, not case-specific) | None found | None, and `completed` was GPT-asserted with zero evidence | D for the `completed` field specifically; A for the template-generation concept itself |
| 4 | `_cross_case_analiza`'s own `nalazi[tip=="rizik"]` | (shared logic behind #5/#6) | gpt-4o | No | N/A (see #5/#6) | None | B (duplicated `identify_case_problems`) |
| 5 | `_cross_case_analiza`'s own `prioritet` | (shared logic) | gpt-4o | No | N/A | None | B (duplicated `shared/case_readiness.py`, built one sprint earlier in this same program) |
| 6 | `_cross_case_analiza`'s own `nalazi[tip=="kontradikcija"]` | (shared logic) | gpt-4o | No, and correctly so | N/A | Grounding check only (`validate_predmet_reference`, proves the CITED case is real, not that the claim itself is true) | D — genuinely no canonical source for cross-document/cross-case contradiction detection |
| 7 | `_cross_case_analiza`'s own `nalazi[tip=="nepovezan_dokument"]` | (shared logic) | gpt-4o | No, and correctly so | N/A | Same grounding check only | D — genuinely no canonical source for this cross-document reference check |
| 8 | `commander_jutarnji` / `commander_jutarnji_refresh` | `GET/POST /api/commander/jutarnji[/refresh]` | (delegates to #4-7) | No | None found (contradicts `SHADOW_WORKFLOW_AUDIT.md`'s own claim) | Self-disclaimed since Program Omega Sprint 004 as "NE kanonski operativni pogled" | C (already correctly self-demoted) |

## What changed this sprint (see `CASE_COMMANDER_DECISION_REGISTRY.md` for the full before/after)

Functions #1 (4 of 6 sections), #2, #4, #5 — the genuinely duplicated/evidence-less decision-making — were
migrated to read `case_actions`/`shared/gap_engine.py`/`shared/case_readiness.py` directly. Functions #1b,
#6, #7 — genuinely GPT-advisory content with no canonical duplicate — were KEPT as GPT output, but now
explicitly tagged `gpt_advisory` (never asserted as fact) via `shared/commander_schema.py`. Function #3's
own template-generation concept was kept; its `completed` field was fixed to never assert unverified
completion. Function #8 inherits all of #4-7's own fixes automatically (pure delegation, unchanged itself
beyond a docstring update).

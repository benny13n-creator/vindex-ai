# Action Producer Registry — Program Omega, Sprint 003 (2026-08-06)

Phase 1's own required deliverable: a forensic catalogue of every existing producer of alerts,
reminders, tasks, notifications, recommendations, "next action"/"sledeći korak" fields, follow-ups,
or risk warnings in this repo — the sprawl the new Canonical Action Engine
(`services/case_evolution.py::_compute_target_actions` / `_consequence_refresh_case_actions`,
writing to the new `case_actions` table, migration 099) is meant to eventually sit alongside, and in
some cases unify. This registry documents the BEFORE state as of 2026-08-06. Unifying every producer
below is explicitly OUT OF SCOPE for this sprint — the mission named Sprint 003's own job as building
ONE new canonical engine reusing `services/risk_engine.py`, not migrating every existing producer onto
it. Every claim below cites a file:line actually read during this audit (Evidence-Based Claims Policy,
"no conclusion without source").

## Producer 1 — `services/risk_engine.py::calculate_procesni_rizik` / `identify_case_problems`

- **File:line**: `services/risk_engine.py:21` / `services/risk_engine.py:157`
- **Produces**: a deterministic risk score + a list of `{"problem": str, "ozbiljnost": "kritican"|"vazan"|"info"}` findings (missing evidence, missing document types, upcoming/critical deadlines, weak evidence).
- **Storage**: none of its own — pure computation, returned to whichever caller invoked it.
- **Deterministic or GPT**: fully deterministic. Established as THE canonical "what's wrong with this case" algorithm by Core Consolidation (2026-07-22), replacing 3 independent guessers (Cockpit GPT, Matter Intel rule-based, Case Ready Score GPT).
- **Consumed by**: `routers/matter_intel.py` (its own former independent next-action logic was retired in favor of this — confirmed no `_compute_next_action`/`sledeca_akcija`/`next_action` text remains in that file), `services/case_evolution.py::_compute_target_actions` (this sprint's new Action Engine, Rule 2/4/5), `routers/zadaci.py::ai_analiziraj_predmet` (grounds its own GPT prompt in this function's output, `routers/zadaci.py:615-622`).
- **Overlap flag**: none — this is the shared foundation everything else below either duplicates or (in 2 confirmed cases) correctly reuses.

## Producer 2 — `shared/proactive_alerts.py::create_proactive_alert` + its callers

- **File:line**: `shared/proactive_alerts.py:50` (the canonical writer, Program Alpha 2026-08-04, replacing 12 previously-independent insert call sites).
- **Produces**: a `proactive_alerts` row (`tip`, `naslov`, `opis`, `urgentnost`, `predmet_id`).
- **Storage**: `proactive_alerts` table.
- **Deterministic or GPT**: the writer itself is a dumb insert; each of its ~10 call sites decides independently, and each decision is itself deterministic (a threshold or event trigger), not GPT:
  - `services/event_bus.py:127` — `on_rok_kritican`, fired on `EventType.ROK_KRITICAN`.
  - `services/event_bus.py:211` — `on_health_score_promenjen`, fired on `EventType.HEALTH_SCORE_PROMENJEN` when score < 30.
  - `services/event_bus.py:259` — `on_document_job_failed`, fired on `EventType.DOCUMENT_JOB_FAILED` (permanently-failed OCR/intake).
  - `routers/case_dna.py:451,778,928`, `routers/morning_briefing.py:748`, `routers/zakon_monitoring.py:264,544`, `routers/zadaci.py:124`, `routers/workflow.py:81`, `services/case_evolution.py:305` — each its own independent trigger condition (Genome verification, law-change monitoring, task assignment, workflow step, evidence classification, etc.).
- **Consumed by**: read by whatever UI surface renders "obaveštenja"/notifications (not audited here — out of scope, confirmed only that the writer and its 10 triggers are real).
- **Overlap flag**: **structural, not functional** — `proactive_alerts` and the new `case_actions` are conceptually adjacent (both say "something needs attention") but serve different jobs: an alert is a point-in-time notification, a `case_action` is a persistent, reconciled worklist item with lifecycle (open→closed). `HEALTH_SCORE_PROMENJEN` firing an alert does NOT currently also refresh `case_actions` (that EventType isn't in `CONSEQUENCE_REGISTRY`) — not a functional gap today, since a dropping health score is itself just a symptom of facts (missing evidence, critical deadlines) the new engine's Rule 1/2/3 already independently detect straight from `risk_engine.py`.

## Producer 3 — `routers/case_commander.py` ("AI Command Center" — self-described "srce platforme")

- **File:line**: `routers/case_commander.py:217` (`POST /api/commander/analiza`), `:280` (`POST /api/commander/quick-check`), `:629` (`GET /api/commander/jutarnji`).
- **Produces**: free-text GPT "Chief of Staff" case analysis (`/analiza`); 3 quick warnings (`/quick-check`); a daily cross-case brief with `rizici`/`kontradikcije`/`nepovezani dokumenti`/**`prioritet`** — literally "which ONE case should be today's priority and why" (`_cross_case_analiza`, `routers/case_commander.py:488-554`).
- **Storage**: `commander_analize` (`routers/case_commander.py:259`), `commander_jutarnji` (upserted per user/day, `routers/case_commander.py:700-704`).
- **Deterministic or GPT**: fully GPT (`gpt-4o` / `gpt-4o-mini`), zero grounding in `risk_engine.py`.
- **Consumed by**: `GET /api/commander/jutarnji` is documented in its own docstring as "AI Command Center jutarnji brifing — srce platforme" (`routers/case_commander.py:634`) — i.e. this is very likely the platform's existing main daily-view surface, cached once per user per day, 0 credits (`routers/case_commander.py:638`).
- **Overlap flag**: **HIGH — the single biggest overlap found**. This is an existing, GPT-driven, already-shipped "what should I work on today, across all my cases" surface — conceptually the exact same job as Sprint 003's new `GET /api/case-actions/worklist`, arrived at completely independently (GPT synthesis vs. deterministic reconciliation), with no shared code path.

## Producer 4 — `routers/morning_briefing.py`

- **File:line**: `routers/morning_briefing.py:79` (`_generiši_briefing`), exposed at `GET /api/briefing/daily`, `POST /api/briefing/cron` (sends to all users), `POST /api/briefing/send-email`, `GET /api/briefing/history`.
- **Produces**: a deterministic bucketing of `rokovi`/`rocista` (`rokovi_hitni` ≤2 days, `rokovi_uskoro` ≤7 days, `rocista_danas`/`rocista_sedmica`, `routers/morning_briefing.py:134-137`) fed into ONE GPT-4o call that writes free-text "Danas zahteva pažnju" / "Preporuka za danas" (`routers/morning_briefing.py:178-216`).
- **Storage**: emailed via SMTP; a 7-day history is queryable (`GET /api/briefing/history`) — the exact underlying table wasn't confirmed in this pass.
- **Deterministic or GPT**: hybrid — deterministic bucketing feeds a GPT free-text synthesis step, same pattern as Producer 5 below.
- **Consumed by**: emailed directly to the lawyer; also readable on-demand.
- **Overlap flag**: **HIGH** — reads from a *different* table (`rokovi`, not `rocista`+`predmet_dokazi`+`predmet_dokumenti` the way `risk_engine.py`/the new Action Engine do) for what is conceptually the same "what needs attention today" question as Producers 3 and this sprint's own new Worklist. Three independent "today" surfaces now confirmed to exist (Commander's `/jutarnji`, this, and the new `/api/case-actions/worklist`).

## Producer 5 — `routers/zadaci.py::ai_analiziraj_predmet`

- **File:line**: `routers/zadaci.py:489`, `POST /ai-analiziraj/{predmet_id}`, rate-limited 10/hour.
- **Produces**: real, persisted `zadaci` (task) rows — not just text. Checks: missing punomoć, deadlines overdue/near, missing key documents, unpaid billing >30 days, no case activity >14 days (`routers/zadaci.py:496-506`).
- **Storage**: `zadaci` table, inserted at `routers/zadaci.py:722`.
- **Deterministic or GPT**: **hybrid, and already partially converged onto the same foundation this sprint's engine uses**. Its own comment (Project Nexus, 2026-08-03, `routers/zadaci.py:605-614`) states it used to be "a 5th independent, non-deterministic (GPT) detector" that bypassed `risk_engine.py::identify_case_problems`, and was fixed to ground its GPT prompt in that function's real output (`routers/zadaci.py:615-622,634-636`) — GPT still independently decides on 2 items `risk_engine.py` doesn't cover (`dana_neaktivnosti > 14`, unpaid billing >50 000 RSD, `routers/zadaci.py:665-666`) plus wording/prioritization of the grounded findings.
- **Consumed by**: the `zadaci` task list UI (not audited further, out of scope).
- **Overlap flag**: **HIGHEST of all producers found — the strongest candidate for a future consolidation sprint.** It already reuses the exact same canonical source (`risk_engine.py`) the new `case_actions` engine reuses, but (a) it's on-demand (button click), not automatic on every case-changing event the way `case_actions` now is, (b) it writes to a structurally different table (`zadaci`, no `dedupe_key`/lifecycle reconciliation — a re-click can create duplicate tasks for the same underlying fact, unlike `case_actions`'s partial-unique-index-guaranteed one-row-per-fact), and (c) its 2 GPT-only checks (inactivity >14 days, unpaid billing >50k) are genuine coverage `case_actions` does NOT have yet — closely related to, but not identical to, the already-named gap `OMEGA-005` ("client not contacted" has no deterministic source; "case inactive >14 days" via `predmeti.updated_at` is a real, already-implemented, GPT-decided rule here, just not yet ported to the new deterministic engine).

## Producer 6 — Case Genome's own `case_dna` fields (`nedostaje`, `upozorenja`, `strategija`, `najslabija_tacka.preporuka`)

- **File:line**: `routers/case_dna.py:105-127` (the GPT extraction prompt template defining these fields).
- **Produces**: `nedostaje` (missing-document list with `hitnost`), `upozorenja` (free-text warning list), `strategija.primarni_cilj`/`rezervni_plan`/`scenariji` (a full contingency plan: "if witness recants, do X"), `najslabija_tacka.preporuka` (one GPT-generated recommendation) — all embedded directly inside the `case_dna` JSON blob written by Genome extraction.
- **Storage**: `predmeti.case_dna` (the same column the new Action Engine itself reads for `kontradikcije`, Rule 3).
- **Deterministic or GPT**: fully GPT, one extraction call per document-triggered Genome refresh.
- **Consumed by**: read directly by numerous UI surfaces platform-wide (not enumerated here, out of scope) — this is the most deeply embedded producer of all, baked into the same object several other systems treat as ground truth.
- **Overlap flag**: **HIGH, but structurally the hardest to touch** — `nedostaje`/`upozorenja`/`strategija` are GPT opinion mixed into the same JSON object Core Consolidation already established as canonical for FACTS (`kontradikcije`, `datumi_kljucni`). Untangling opinion fields from fact fields inside one GPT-authored JSON blob is a materially bigger undertaking than any other item on this list — named here, not attempted.

## Producer 7 — `routers/copilot.py::_handle_analiza_predmeta` ("sledeći korak")

- **File:line**: `routers/copilot.py:299-346`.
- **Produces**: a GPT JSON object with `procena`/`prednosti`/`slabosti`/`nedostaju`/**`sledeci_korak`** (`{"opis", "rok", "prioritet"}`)/`verovatnoca_uspeha`.
- **Storage**: none — ephemeral chat response only.
- **Deterministic or GPT**: fully GPT (`gpt-4o` family), reads `case_dna` as context but does not call `risk_engine.py`.
- **Consumed by**: the chat Copilot UI, single-turn.
- **Overlap flag**: **self-documented HIGH** — its own comment (Project Synapse, 2026-08-03, `routers/copilot.py:307-313`) literally calls this "a 4th independent case-strength synthesis path (alongside Case Genome, the AI Briefing, and Matter Intelligence)."

## Producer 8 — `routers/case_intelligence.py` (cross-module briefing synthesizer)

- **File:line**: `routers/case_intelligence.py:37-79`, `POST /api/intelligence/predmeti/{predmet_id}/briefing`.
- **Produces**: a GPT JSON object explicitly including `"sledeci_korak": "<JEDNA najhitnija konkretna akcija>"` (`routers/case_intelligence.py:68`), synthesizing lessons-learned, Firm DNA, case patterns, alerts, and decision log into "JEDNU preporuku" (one recommendation) — its own docstring's stated purpose (`routers/case_intelligence.py:5-9`).
- **Storage**: not confirmed in this pass (out of scope — endpoint behavior was the focus).
- **Deterministic or GPT**: fully GPT.
- **Consumed by**: not confirmed in this pass.
- **Overlap flag**: **HIGH, ironic** — this endpoint's own stated mission ("JEDAN endpoint koji ulancava sve module i vraca JEDNU preporuku", "bez otvaranja deset ekrana") is functionally the same ambition as this sprint's own Canonical Action Engine, arrived at through GPT synthesis of *other producers'* outputs rather than deterministic business rules over raw facts.

## Producer 9 — `routers/strategija.py` (on-demand simulation/advisory tools)

- **File:line**: 9 POST endpoints, `routers/strategija.py:85-382` (`/red-team`, `/litigation`, `/sudija`, `/due-diligence`, `/revizor`, `/witness`, `/sudija-v2`, `/kompletna-analiza`, `/v2/analiza`).
- **Produces**: adversarial-simulation and strategic-advisory GPT output; `/kompletna-analiza` includes `kljucni_rizici: [{"rizik", "tezina", "preporuka"}]` (`routers/strategija.py:360`) — per-risk recommendations.
- **Storage**: not audited (out of scope).
- **Deterministic or GPT**: fully GPT, always on-demand (never automatic).
- **Consumed by**: strategy/simulation UI surfaces.
- **Overlap flag**: **LOW** — these are explicitly advisory "what-if" simulation tools a lawyer deliberately invokes, not automatic "what must I do" producers. Included for completeness, not flagged as a consolidation candidate.

## Producer 10 (historical) — `routers/matter_intel.py`

- **File:line**: confirmed via grep, no `_compute_next_action`/`sledeca_akcija`/`sledeci_korak`/`next_action` text remains anywhere in the file.
- **Status**: **already consolidated** onto `services/risk_engine.py` (Core Consolidation, 2026-07-22 — see `services/risk_engine.py:14-15`, "Logika je 1:1 prenesena iz routers/matter_intel.py"). Listed here as proof that consolidating an independent producer onto the canonical algorithm is achievable — it has already happened once.

## Summary table

| # | Producer | File | Storage | GPT or deterministic | Unified by new Action Engine? |
|---|---|---|---|---|---|
| 1 | `risk_engine.py` | `services/risk_engine.py` | none (pure function) | Deterministic | DA — direct dependency |
| 2 | `proactive_alerts` (+10 callers) | `shared/proactive_alerts.py` + callers | `proactive_alerts` | Deterministic triggers | NE — different concern (notification vs. worklist item), van obima |
| 3 | Case Commander | `routers/case_commander.py` | `commander_analize`, `commander_jutarnji` | GPT | NE — ostaje nezavisan, van obima ovog sprinta |
| 4 | Morning Briefing | `routers/morning_briefing.py` | email + history | Hybrid (deterministic bucket → GPT text) | NE — ostaje nezavisan, van obima ovog sprinta |
| 5 | `ai_analiziraj_predmet` | `routers/zadaci.py` | `zadaci` | Hybrid (grounded in #1) | NE, ali NAJBLIŽI kandidat — već deli #1 kao osnovu |
| 6 | Genome `nedostaje`/`upozorenja`/`strategija` | `routers/case_dna.py` (prompt) | `predmeti.case_dna` | GPT | NE — najteže za razdvajanje, van obima |
| 7 | Copilot `sledeci_korak` | `routers/copilot.py` | ephemeral | GPT | NE — ostaje nezavisan, van obima ovog sprinta |
| 8 | Case Intelligence briefing | `routers/case_intelligence.py` | not confirmed | GPT | NE — ostaje nezavisan, van obima ovog sprinta |
| 9 | Strategija simulacije | `routers/strategija.py` | not audited | GPT | NE — nizak prioritet, drugačija namena (savetodavno, na zahtev) |
| 10 | Matter Intel (istorijski) | `routers/matter_intel.py` | — | — (već konsolidovano) | DA — već urađeno 2026-07-22 |

## Preporuka za budući sprint

Producer 5 (`routers/zadaci.py::ai_analiziraj_predmet`) is the strongest consolidation candidate for a
future sprint: it already grounds itself in the same canonical `risk_engine.py` output this sprint's
Action Engine reuses, meaning the deterministic half of its work is already duplicated logic, not just
duplicated *concept*. A future sprint could retire its deterministic findings entirely in favor of
reading `case_actions`, keeping only its 2 genuinely GPT-only checks (inactivity >14 days, unpaid
billing >50 000 RSD) as new deterministic rules on the canonical engine instead. Producers 3, 4, and 8
(Case Commander's `/jutarnji`, Morning Briefing, and Case Intelligence's briefing) are three
independently-built "what should I focus on today" GPT surfaces that a founder-level product decision —
not a code decision — should resolve: which one (if any) becomes the lawyer's actual daily entry point
alongside (or instead of) the new deterministic `/api/case-actions/worklist`. This sprint does not make
that call.

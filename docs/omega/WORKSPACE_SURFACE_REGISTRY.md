# Workspace Surface Registry — Program Omega, Sprint 004 (2026-08-06)

Phase 1's own required deliverable: a forensic catalogue of every surface that shows a lawyer "what to
work on," verified against the ACTUAL frontend (`static/vindex.js`), not assumed. Sprint 003's own
`docs/omega/ACTION_PRODUCER_REGISTRY.md` (read first — this registry builds on it, does not repeat it)
was scoped to "action/alert *producers*" and did not check which of them the frontend actually renders.
This registry closes that gap: it traces the home page's own `dash_load()` function
(`static/vindex.js:1206`, the "Kontrolni Centar" / Control Center) call by call, and confirms — for the
first time in this whole engagement — which surfaces are genuinely LIVE on a lawyer's home screen versus
architecturally real but frontend-dead. Every claim cites a file:line actually read.

## The home page itself: `dash_load()` — `static/vindex.js:1206`

On login, the frontend's own Control Center loads **7 independent backend calls in sequence/parallel**,
each rendering its own widget with its own loading/error state:

```
dash_load()
 ├─ Promise.all: /api/dashboard/command-center, /billing/pregled, /api/inbox   (:1213-1218)
 ├─ notif_load()                → GET /notifications                          (:1227, :11267)
 ├─ loadBriefing(false)         → GET /api/briefing/daily                     (:1228, :1747)
 ├─ _ccCaricaAiAnaliza(hdr)     → GET /api/commander/jutarnji                 (:1229, :1504)
 ├─ _cioLoad(hdr)               → GET /api/cio/daily                         (:1230, :17261)
 └─ _healthIndexLoad(hdr)       → GET /api/firm/health-index                 (:1232, :1245)
```

This single function call graph IS the forensic proof the mission asked for: the home page today is
already a composite of (at least) 6 independently-built "what's going on" surfaces, each with its own
widget, its own loading skeleton, its own failure message, and — critically — its own idea of what
counts as urgent. No single one of them is "the" home screen; all of them are, simultaneously, in
different corners of the same page.

## Surface 1 — Command Center (`routers/dashboard.py:30`, `GET /api/dashboard/command-center`)

- **Vlasnik**: `routers/dashboard.py::command_center`.
- **Svrha**: the main body of the home page — today's hearings, week's deadlines, risk changes, inactive
  cases, recent documents, unpaid invoices, top 5 active cases, a short rule-based recap.
- **Podaci**: `danasnja_rocista`, `rokovi_7` (hitni/uskoro), `predmeti_visok_rizik`, `pad_procene`,
  `novi_dokumenti`, `neaktivni_predmeti`, `top_aktivni_predmeti`, `neplaceno_fakture_rsd`, `ai_preporuke`
  (rule-based recap, NOT an LLM call — `dashboard.py:273-294`).
- **Izvor podataka**: `predmeti`, `rocista` (today's + next-90-days), `predmet_hronologija` (deadlines),
  **`rokovi`** — a SECOND, independent deadlines table (`dashboard.py:113-120`, joined with
  `predmet_hronologija`'s own rows at `:189-209`, each row tagged with its own `izvor` field so the
  duplication is at least visible in the response), `predmet_istorija` rows whose `pitanje` field starts
  with `"[Rizik]"` (`dashboard.py:76-82` — **a THIRD independent risk computation**, alongside
  `risk_engine.py` and `case_dna`), `predmet_beleske`/`predmet_istorija` recency (for "inactive >30 days"
  — **the SAME "case inactivity" concept** `zadaci.py::ai_analiziraj_predmet` independently computes as
  "`dana_neaktivnosti > 14`", `routers/zadaci.py:665`, a different threshold for the same underlying
  question), `fakture`.
- **Uživo na frontendu?**: **DA — potvrđeno**, `static/vindex.js:1215`, the first and largest call in
  `dash_load()`.
- **Jedinstvena ili duplirana**: **Duplirana iznutra** — this ONE endpoint alone reads 2 independent
  deadline sources and computes a 3rd independent risk signal never reconciled against
  `risk_engine.py::calculate_procesni_rizik` (the platform's own established canonical risk algorithm,
  Core Consolidation 2026-07-22). It is also functionally the SAME "what needs attention" question as
  every surface below, arrived at completely independently.

## Surface 2 — Morning Briefing (`routers/morning_briefing.py:79`, `GET /api/briefing/daily`)

- **Vlasnik**: `routers/morning_briefing.py::_generiši_briefing`.
- **Svrha**: a "briefing-card" widget on the SAME home page — urgent deadlines, today's hearings, GPT
  "Preporuka za danas."
- **Podaci**: `statistike` (`rokovi_hitni`, `rocista_danas`, `aktivni_predmeti`, `rokovi_uskoro`),
  `hitni_rokovi` (top 3 shown), free-text GPT recommendation.
- **Izvor podataka**: `rokovi` table + `rocista` (bucketed deterministically, `morning_briefing.py:134-137`)
  fed into one GPT-4o call.
- **Uživo na frontendu?**: **DA — potvrđeno**, `static/vindex.js:1747` (`loadBriefing`), rendered into a
  `#briefing-card` element that visibly coexists on the same page as Surface 1's own `hitni_rokovi`.
- **Jedinstvena ili duplirana**: **Duplirana** — reads the SAME `rokovi`/`rocista` tables Surface 1 reads,
  computes its own separate "hitan" bucket (≤2 days here vs. Surface 1's own ≤2-day `in_2_iso` window —
  same threshold, independently coded twice), and adds a GPT opinion layer on top.

## Surface 3 — Case Commander `/jutarnji` (`routers/case_commander.py:629`, `GET /api/commander/jutarnji`)

- **Vlasnik**: `routers/case_commander.py::jutarnji_brifing`, self-documented "AI Command Center jutarnji
  brifing — srce platforme" (`:634`).
- **Svrha**: a THIRD widget on the SAME home page (`#cc-ai-nalazi`) — cross-case GPT findings: `rizici`,
  `kontradikcije`, `nepovezani dokumenti`.
- **Podaci**: `nalazi` (a list of `{tip, predmet_naziv, naslov, predmet_id_prefix}` findings), each with
  its own icon (`static/vindex.js:1515-1516`).
- **Izvor podataka**: `commander_jutarnji` (cached per user/day) — computed by a `gpt-4o`/`gpt-4o-mini`
  cross-case scan, zero grounding in `risk_engine.py` (confirmed again this pass, unchanged from Sprint 3's
  own finding).
- **Uživo na frontendu?**: **DA — potvrđeno**, `static/vindex.js:1502-1541` (`_ccCaricaAiAnaliza`), renders
  directly into the home page next to the Morning Briefing card.
- **Jedinstvena ili duplirana**: **Duplirana** — same "rizici/kontradikcije, what needs attention" question
  as Surfaces 1, 2, and (below) 4, arrived at via independent GPT synthesis.

## Surface 4 (NEW — not in Sprint 003's registry) — CIO Daily Report (`routers/cio.py:1`, `GET /api/cio/daily`)

- **Vlasnik**: `routers/cio.py` — "Chief Intelligence Officer" — its own system prompt states the mission
  in almost the exact words as this Sprint's own charter: *"Tvoj posao nije da odgovaraš na pitanja. Tvoj
  posao je da dolaziš sa odgovorima"* (`cio.py:37`).
- **Svrha**: a FOURTH widget on the SAME home page (`#kc-cio-section`) — portfolio-wide daily scan.
- **Podaci**: `cio_preporuka` (**"JEDNA konkretna akcija sa najvećim uticajem — danas"** — literally the
  mission's own stated goal for the Unified Workspace, `cio.py:44`), `najveci_rizik`, `najveca_prilika`,
  `zapostavljen_predmet` (**"dana_bez_aktivnosti"** — a FOURTH independent case-inactivity computation,
  alongside Surface 1's `neaktivni_predmeti` and `zadaci.py`'s own `dana_neaktivnosti`), `neprimecena_
  kontradikcija`, `portfolio_zdravlje`.
- **Izvor podataka**: GPT-4o, reading "Case Genome modele predmeta + Firm DNA + Lekcije + Obrasce uspeha"
  (`cio.py:40`) — cached 6h.
- **Uživo na frontendu?**: **DA — potvrđeno**, `static/vindex.js:17257-17271` (`_cioLoad`), a 4th widget on
  the home page, right below Case Commander's own findings section.
- **Jedinstvena ili duplirana**: **HIGH duplikat — najbliži konceptualno Sprint 3-ovom Action Engine-u od
  svih GPT površina.** Its own `cio_preporuka` field IS "the one action for today" — the exact deliverable
  Sprint 003's deterministic Worklist was built to provide, produced instead by GPT synthesis with zero
  reconciliation against `case_actions`.

## Surface 5 (NEW — not in Sprint 003's registry) — Notification Engine (`routers/notifications.py:1`, `GET /notifications`)

- **Vlasnik**: `routers/notifications.py::get_notifications`.
- **Svrha**: the bell icon + dropdown, visible on every page (not just the home page) — "šta se
  promenilo."
- **Podaci**: a `notifications` row list, each with its own `tip` from a 16-entry taxonomy
  (`NOTIF_TIPOVI`, `notifications.py:28-52` — deadlines, hearings, inactivity, collaboration, invoicing,
  "AI analysis done") and its own `priority` (`urgent`/`high`/`normal`/`low`/`info`,
  `notifications.py:54` — **a FIFTH independent priority scale**, alongside `case_actions.prioritet`
  (critical/high/medium/low/informational), `identify_case_problems`'s `ozbiljnost`
  (kritican/vazan/info), and 2 more informal ones inside Surfaces 1 and 3).
- **Izvor podataka**: its OWN `notifications` table (`notifications.py:117`, distinct from BOTH
  `proactive_alerts` AND `case_actions`), computed from `predmet_hronologija`, `predmeti`,
  `predmet_beleske` (`notifications.py:151-198`) — **a SIXTH independent deadline/inactivity computation**.
- **Uživo na frontendu?**: **DA — potvrđeno, i to na SVAKOJ stranici**, `static/vindex.js:11267`
  (`notif_load`), the bell badge shown globally.
- **Jedinstvena ili duplirana**: **Duplirana, i strukturno najozbiljniji nalaz ove faze.** This is a THIRD
  independent alert-producing/storing system, alongside `shared/proactive_alerts.py`'s own
  `proactive_alerts` table (Sprint 3's Producer 2) and Sprint 003's own `case_actions`. Three tables, three
  independently-computed "something needs attention" signals, one bell icon showing only this one.

## Surface 6 — Health Index widget (`routers/health_index.py:414`, `GET /api/firm/health-index`)

- **Vlasnik**: `routers/health_index.py`.
- **Svrha**: a firm-wide (not per-case) portfolio health score widget, also on the home page.
- **Podaci/izvor**: not read in depth this pass (firm-level aggregate, out of the "per-case action" scope
  this registry is chasing) — flagged for completeness, not for consolidation priority.
- **Uživo na frontendu?**: **DA**, `static/vindex.js:1232,1245` (`_healthIndexLoad`).
- **Jedinstvena ili duplirana**: **LOW overlap** — a portfolio-level metric, not a "what should I do"
  producer; conceptually adjacent, not a duplicate of the per-case action surfaces above.

## Surface 7 — `shared/proactive_alerts.py` — CORRECTION to Sprint 003's own finding

Sprint 003's `ACTION_PRODUCER_REGISTRY.md` (Producer 2) stated `proactive_alerts` is "read by whatever UI
surface renders obaveštenja/notifications (not audited here)." This pass audited it: **`proactive_alerts`
is read by at least 4 modules** — `routers/case_intelligence.py:143`, `routers/decision_replay.py:130`,
`routers/matter_intel.py:148,160`, `routers/morning_briefing.py:798,825,849,1034` (feeding Surface 2's own
briefing). It is NOT the same table Surface 5's notification bell reads (`notifications`, a different
table) — so `proactive_alerts` and `notifications` are two SEPARATE, both-real, both-consumed alert
tables, neither aware of the other.

## Surface 8 — Zadaci (`routers/zadaci.py`) — team task assignment, genuinely distinct feature

- **Vlasnik**: `routers/zadaci.py`.
- **Svrha**: human-assigned team tasks (a partner assigns work to an associate) — NOT an AI-detected
  action, a genuinely different, real feature (manual task assignment/tracking).
- **Podaci**: `naziv`, `status` (`otvoreno`/`u_toku`/**`ceka`**/`zavrseno`/`otkazano` —
  `zadaci.py:53` — **`"ceka"` is a real, already-modeled "waiting" status**, directly usable for the
  mission's own "Waiting" bucket, unlike anything found for `OMEGA-005`), `prioritet`
  (`hitno`/`visoko`/normalan/nisko — a 7th independent priority scale), `rok_datum`, `dodeljen_uid`,
  `predmet_id`.
- **Izvor podataka**: `zadaci` table — human-entered, not derived.
- **Uživo na frontendu?**: **DELIMIČNO.** `GET /api/zadaci/predmet/{id}` (per-case task panel) — DA,
  `static/vindex.js:22587`. `GET /api/zadaci/tim` (office-wide board) — DA, `static/vindex.js:22650`
  (`zadaci_g_load`). **`GET /api/zadaci/moji` (personal cross-case "my tasks" view, `zadaci.py:188`) — NE,
  no reference anywhere in `static/vindex.js`** — the one endpoint shaped most like a personal daily
  worklist is currently dead from the frontend's own perspective.
- **Jedinstvena ili duplirana**: **Jedinstvena za SVOJ deo** (human-assigned work has no other source) —
  but its "waiting"/"prioritet" concepts are yet more independently-invented vocabulary a Unified
  Workspace would need to either display honestly as its own category or explicitly not attempt to merge
  with AI-detected `case_actions`.

## Surface 9 — `zadaci.py::ai_analiziraj_predmet` (`POST /api/zadaci/ai-analiziraj/{predmet_id}`)

Already fully documented as Producer 5 in `ACTION_PRODUCER_REGISTRY.md` — re-confirmed live this pass,
`static/vindex.js:22862` (button on the case detail page, on-demand, not automatic).

## Surface 10 — Case Intelligence briefing (`routers/case_intelligence.py`)

Already documented as Producer 8 in `ACTION_PRODUCER_REGISTRY.md`. **Clarification this pass**: confirmed
live, `static/vindex.js:17127,17190` — but ONLY as a per-case, on-demand button (takes a `predmetId`
parameter), not a home-page/landing surface. Lower overlap priority than Surfaces 1-5 for THIS sprint's
"what does the lawyer see when they open Vindex AI" question.

## Surface 11 — `case_actions` Worklist (Sprint 003, `routers/case_actions.py`)

- **Vlasnik**: `routers/case_actions.py`.
- **Svrha**: THE new deterministic engine's own read surface.
- **Uživo na frontendu?**: **NE — potvrđeno, nula referenci** u `static/vindex.js` za `/api/case-actions/`
  bilo koje putanje. The most architecturally correct surface (deterministic, sourced, lifecycle-managed)
  is currently the LEAST visible one to an actual lawyer.
- **Jedinstvena ili duplirana**: functionally duplicates Surfaces 1/2/3/4's own "what needs attention"
  question, but is the only one that is (a) deterministic, (b) has a persistent lifecycle (open→closed,
  not a daily-regenerated GPT blob), (c) has per-item sourcing (`dokaz`/`izvor_dokumenti`).

## Surface 12 — `case_intelligence_summaries` (Sprint 002, migration 098)

Re-confirmed **still true**: no router anywhere selects from this table. `OMEGA-004` remains open,
unchanged by this pass.

## Summary table

| # | Površina | Vlasnik (file) | Podaci | Izvor podataka | Uživo na frontendu | Jedinstvena/duplirana |
|---|---|---|---|---|---|---|
| 1 | Command Center | `routers/dashboard.py` | rokovi, ročišta, rizik, neaktivni, dokumenti, fakture | `predmeti`,`rocista`,`predmet_hronologija`,**`rokovi`**,`predmet_istorija["[Rizik]"]`,`beleske`,`fakture` | **DA** (glavno telo) | Duplirana (3 izvora unutar sebe) |
| 2 | Morning Briefing | `routers/morning_briefing.py` | statistike + GPT preporuka | `rokovi`,`rocista` → GPT | **DA** (widget) | Duplirana |
| 3 | Case Commander `/jutarnji` | `routers/case_commander.py` | GPT nalazi (rizici/kontradikcije) | `commander_jutarnji` ← GPT | **DA** (widget) | Duplirana |
| 4 | CIO Daily | `routers/cio.py` | "JEDNA akcija danas" + rizik/prilika/zapostavljenost | GPT nad Genome/Firm DNA | **DA** (widget) | Duplirana, najbliža Action Engine-u |
| 5 | Notifications | `routers/notifications.py` | 16 tipova, 5 prioriteta | sopstvena `notifications` tabela | **DA** (zvonce, svuda) | Duplirana (3. alert tabela) |
| 6 | Health Index | `routers/health_index.py` | firma-nivo zdravlje | nije detaljno auditovano | **DA** (widget) | Niska (drugi nivo) |
| 7 | `proactive_alerts` | `shared/proactive_alerts.py` | alert redovi | sopstvena tabela | DA (4 čitaoca, uklj. Briefing) | Duplirana (3. alert tabela) |
| 8 | Zadaci (tim/predmet) | `routers/zadaci.py` | ljudski dodeljeni zadaci | `zadaci` tabela | DA (`/predmet`,`/tim`); **NE** (`/moji`) | Jedinstvena (ljudski unos) |
| 9 | `ai_analiziraj_predmet` | `routers/zadaci.py` | AI zadaci (grounded) | `risk_engine.py` + 2 GPT provere | DA (dugme, po predmetu) | Duplirana (v. `ACTION_PRODUCER_REGISTRY.md`) |
| 10 | Case Intelligence briefing | `routers/case_intelligence.py` | GPT "JEDNA preporuka" | više modula → GPT | DA (dugme, po predmetu) | Duplirana, niži prioritet (nije home) |
| 11 | `case_actions` Worklist | `routers/case_actions.py` | determinističke akcije | `risk_engine.py`,`rocista`,`case_dna` | **NE — nula referenci** | Jedinstvena arhitektonski, nevidljiva |
| 12 | `case_intelligence_summaries` | migracija 098 | sourced case-level sažetak | Case Evolution | **NE — nema read API** | Neiskorišćena |

## Najvažniji nalaz ove faze

Home page (`dash_load()`) VEĆ pokušava da bude "jedan operativni centar" — ali kompozicijom 6 nezavisnih
poziva (Command Center, Morning Briefing, Case Commander, CIO, Notifications, Health Index), svaki sa
sopstvenim učitavanjem, sopstvenim pragovima ("hitno" znači različit broj dana na 3 različita mesta),
sopstvenom terminologijom prioriteta (najmanje 5 različitih skala pronađenih: `case_actions.prioritet`,
`identify_case_problems.ozbiljnost`, `notifications.priority`, `zadaci.prioritet`, CIO-ova neformalna
"kriticnost" 0-100). Sprint 003-ov deterministički, sourced `case_actions` — arhitektonski najispravnija
površina — nema NIJEDNU frontend referencu. Ovo nije "izgraditi nešto novo" zadatak — to je "od 6+
postojećih glasova, odabrati/spojiti u JEDAN" zadatak, tačno kako misija kaže.

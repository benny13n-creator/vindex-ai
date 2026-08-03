# Invisible Features Census — Operation Invisible Features (BETA-003)

Read-only investigation. All claims grounded in direct file reads and grep evidence from this
session; no code changed. `static/vindex.js` is the only real frontend app file (`index.html` holds
the tab-bar markup that `vindex.js` manipulates); `client_portal.html`, `landing.html`, `pricing.html`,
`privacy.html`, `terms.html`, `static/status.html`, `static/*.html` are separate, non-SPA pages —
confirmed no other JS file exists under `static/`.

**One false alarm avoided, worth recording**: initially suspected a backslash-vs-forward-slash typo
in `loadBriefing()`'s fetch URL (`static/vindex.js:1693`) based on how the Read tool rendered the
line. Verified with a raw Python file read before reporting it — the actual bytes on disk are
`'/api/briefing/daily'`, correct forward slashes throughout. This was a Read-tool display artifact,
not a real bug. Flagging this so it isn't independently "found" again and reported as real.

---

## 1. The 17 flagged routers — verified bucket per router

`scripts/audit_routers.py`'s heuristic (path-substring match against `vindex.js` + other `.py` files)
has real false negatives (dynamic path construction like `'/api/oblasti/' + variable` isn't detected)
and at least one false-negative-masking bug (`/health`-containing routes get bucketed "maybe
external" instead of "dead", which is exactly what hid Smart Intake last session). Every router below
was independently re-verified by reading the actual router file and searching `vindex.js` for both
literal and dynamically-constructed calls.

| Router | Bucket | Evidence |
|---|---|---|
| `agent_notifications` | **A — dead** | `routers/agent_notifications.py`: background-agent recommendation feed (accept/reject), Human-in-the-Loop pattern, real logic (115 lines). Zero references anywhere in `vindex.js`, literal or dynamic. |
| `auto_discovery` | **A — dead** (admin-only by design) | Bulk PDF ingestion for Pinecone (`pokreni`/`dodaj-url`/`upload`/`status`), explicitly admin-facing per its own docstring. Zero frontend references. No separate admin panel HTML found either — likely intended to be run via direct API call/script, not a lawyer-facing gap. Lower priority than lawyer-facing findings below. |
| `case_intelligence` | **A — dead** | One-call cross-module case briefing aggregator (lessons + DNA + knowledge profile + comms profile + court predictor + decision log — "bez otvaranja deset ekrana"). Zero references to `/api/intelligence` in `vindex.js`. Distinct from `morning_briefing.py` (below) — this is a PER-CASE briefing, not the daily cross-case one. Real, unbuilt-frontend value: exactly the kind of "reduce clicks" win this mission is looking for. |
| `gdpr` | **A — dead** (partially by design) | `/gdpr/unsubscribe` is a public email-link endpoint, correctly not UI-linked. `/api/gdpr/export` and `/api/gdpr/account` (self-service data export / account deletion — real GDPR/ZZPL rights) have zero frontend references — a lawyer has no self-service way to exercise these rights today. |
| `import_klijenti` | **A — dead, and a real duplicate** | 3-step CSV/XLSX import: template download → preview with column-mapping → execute-after-confirmation (`routers/import_klijenti.py`). Zero frontend references. **The frontend instead calls a different, live endpoint**: `klijenti/router.py:1435`'s `POST /klijenti/import-csv` — a simpler one-shot import with fixed expected columns, no preview, no confirmation step (`static/vindex.js:4946`). The unused implementation is the *safer* one (preview before committing); the live one just imports directly. |
| `knowledge_hygiene` | **A — dead** | Personal-knowledge-base maintenance tool: scan/report/find-contradictions/archive-stale/merge-duplicates. Zero frontend references. |
| `knowledge_transfer` | **A — dead** | Knowledge-profile extraction from external sources (`/api/knowledge/profili`). Zero frontend references. |
| `oblasti` | **E — false positive, actually wired** | `static/vindex.js:5658`: `oblastiPokreni()` calls `fetch(BASE_URL + '/api/oblasti/' + _oblastTrenutna, ...)` — a dynamic path the heuristic script cannot detect via substring match. Confirmed working, reachable via the AI Workspace tab's "Pravne oblasti" mode. |
| `onboarding` | **C — deliberately superseded** | `vindex.js:288`/`:19286` explicit comments: "Onboarding — jedini flow je onboardingCheck (stari onboard_show je deaktiviran)" / "deaktivirano — onboardingCheck() je jedini onboarding flow". The live onboarding flow calls a *different* endpoint (`/api/auth/onboarding/complete`, `vindex.js:15383`), not this router's 5 endpoints. Confirmed intentional, not a gap. |
| `region` | **A — dead** | Regional legal-support differentiator (courts/deadlines/AI-advice by country). Zero real references — the one grep hit for "region" was a coincidental code comment about CARF/DAC8 near the Web3 section, not a call to this router. |
| `status_page` | **A — dead (from the app)**, separately served | Zero references in `vindex.js`. `static/status.html` exists as a standalone public status page but wasn't confirmed (time-boxed) to actually call `/api/status/public` vs. having its own inline mock data — worth a direct follow-up read of `status.html`'s own `<script>` before assuming it's wired. |
| `strategy_simulator` | **A — dead** | Legal strategy game-tree simulator (`nova-partija`/`sledeci-potez` — chess-like "new match"/"next move" framing for case strategy). The only "simulator" hits in `vindex.js` are for a completely unrelated Web3 feature (`reporting_simulator`, `/web3/reporting-simulator`) — confirmed zero real overlap, this router is genuinely unreferenced. |
| `style_checker` | **A — dead** | Writing-style profile builder/analyzer for the lawyer's own drafting style. Zero frontend references. |
| `ugovor_zastupanja` | **E — false positive, actually wired** | `static/vindex.js:21223`: `fetch(BASE_URL + '/api/ugovor-zastupanja/generi%C5%A1i'` — URL-encoded Cyrillic/diacritic character (š → %C5%A1) that the heuristic's raw-string substring match against the router's literal (unencoded) route definition can't match. Confirmed working. |
| `whatsapp_notif` | **A — dead, and a real duplicate** | Dedicated WhatsApp subscription system via Twilio (`registruj`/`posalji-rok`/`dnevni-brifing-wa`/`pretplata`, its own `whatsapp_pretplate`/`whatsapp_send_log` tables). Zero frontend references. **`routers/sms.py` is the actual live system** — same Twilio integration, a single `whatsapp: bool` flag on the SMS profile (`vindex.js:2836`/`:2858` → `POST /sms/telefon`) that IS read and used to route messages via WhatsApp-formatted numbers (`routers/sms.py:201-202,285-287`). Genuine duplicate: two full WhatsApp-via-Twilio implementations, only the simpler one live. |
| `smart_intake` | (already known — see prior session's Blocker Report) | Confirmed again: only its `/admin/health` route trips the audit script's `/health` external-trigger heuristic, masking that `/documents` and `/jobs/{id}/finalize` have zero frontend callers. No new evidence beyond what's already documented. |
| `viber` | **D — genuine external webhook** | `/viber/webhook` — correctly external-triggered (Viber platform calls this, not our frontend). No action needed. |

**Bucket A tally (genuinely dead, no known reason): 12** — `agent_notifications`, `auto_discovery`
(lower priority, admin-only), `case_intelligence`, `gdpr`, `import_klijenti`, `knowledge_hygiene`,
`knowledge_transfer`, `region`, `status_page` (needs one more check), `strategy_simulator`,
`style_checker`, `whatsapp_notif`.
**Bucket B (frontend exists, just needs a nav link): 0 found in this list** — every genuinely-dead
router here has NO frontend code calling it at all, not just a missing nav link. Real Bucket B
candidates (if any) are more likely in the broader capability census below, not among routers this
heuristic already flagged.
**Bucket C/D/E (no action needed): 5** — `onboarding`, `viber`, `oblasti`, `ugovor_zastupanja`,
`smart_intake` (already tracked separately).

---

## 2. Capability matrix — 7 areas beyond this session's already-known systems

| Area | Router(s) | Implemented? | Backend connected? | Frontend reachable? | Nav-visible? | Notes |
|---|---|---|---|---|---|---|
| Analytics | `routers/analytics.py` | Yes — `/analytics/track` (event log) + `/analytics/usage` (aggregated N-day view) | Yes, `_track_event` called from many places this session | **Yes** — `/analytics/usage` referenced `vindex.js:14702` | Not confirmed which tab (time-boxed) | Real, working, reachable — not an invisible-feature finding. |
| Reports (billing) | `routers/billing_reports.py` | Yes — yearly/CSV/aging/by-type reports | Yes | **Yes** — `/billing/report` referenced 6× across `vindex.js` (lines 2780, 13537-13540, 13616, 20251) | Yes — "Finansije" tab (`fin`) per `index.html:1469`'s in-app link | Fully wired, working. |
| Exports | `routers/data_export.py` (GDPR full-account ZIP) + `routers/export.py` (DOCX/PDF/API-keys/external v1 query) | Both real | Both connected | **Both reachable** — `/api/export` (`vindex.js:797`), `/export/docx`+`api-kljucevi`+`pdf-export`+`/v1/query` (9 combined hits) | Not confirmed precisely which tab each lives under | Two similarly-named routers, NOT duplicates — GDPR full-export vs. per-document/API-key export serve different purposes. Both wired; no finding here. |
| Voice | `routers/voice.py` (command engine) + `routers/voice_realtime.py` (WebSocket realtime session) | Both real, `voice_realtime.py` notably sophisticated (routes tool calls through the same auth/permission/RAG layer as everything else, not direct-to-OpenAI) | Yes | **Yes** — `/api/voice` referenced 4× in `vindex.js`; a dedicated mic button exists directly in `index.html:569` main UI chrome (not buried in a submenu), with a graceful non-Chrome/Edge fallback message | Yes — always-visible mic icon | Fully wired, working, no finding. |
| Knowledge Graph | `routers/knowledge_graph.py` (predmet↔klijenti↔zakoni↔presude↔dokumenti↔rokovi network) | Real | Yes | **Yes** — `/api/knowledge-graph` referenced once (`vindex.js:18943`) | Not confirmed which tab | Wired; single reference suggests a specific action button rather than a prominent nav item — not independently verified further given time. |
| Web3 / Digital Asset Compliance (AML/CARF/DAC8/MiCA/Whitepaper) | `routers/web3.py` (search/compliance-checker/whitepaper-analysis/MiCA-readiness/ZDI-license-checker) + `routers/wallet_provenance.py` (wallet age/activity/OFAC-SDN screening) | Both real, substantial | Yes | **Yes, heavily** — `/web3/` referenced 14×, `ofac`/`wallet_provenance` referenced 10× across `vindex.js` | **Deliberately gated**, not missing: `index.html:2769` — `<button ... id="aiws-pill-dim" ... style="display:none;">Vindex AI - Digitalna imovina & usklađenost</button>` — hidden by default, shown only when a settings flag enables it. This matches the founder's own prior product decision (memory: "AIWS mode gejtovan iz Settings") — **not an invisible-feature bug, an intentional gate.** No action recommended without confirming the founder still wants it gated. |
| Case Linking / Client Management | — | Not conclusively determined in the time available | — | No hits found for `povezani_predmeti`/`linked_predmet`/case-link-style naming in `vindex.js` | — | **Time-boxed, not confidently classified** — could mean no dedicated case-linking UI exists under any name, or it uses terminology this search didn't anticipate. Flagged as needing a direct follow-up rather than guessed at. |

### A finding beyond the requested 7 areas: three separate "graph" systems, one of them fully dead
- `routers/evidence_graph.py` (`/api/evidence-graph`) — single-case entity/relationship graph (GPT-4o extracts persons/documents/events/claims/dates from ONE case, D3/Cytoscape-ready). **Wired** — 4 references in `vindex.js` (lines 21385-21418).
- `routers/knowledge_graph.py` (`/api/knowledge-graph`) — cross-entity legal network (case↔client↔law↔judgment↔document↔deadline). **Wired** — 1 reference.
- `routers/memory_graph.py` (`/api/memory-graph`) — explicit relationship queries across cases/arguments/judges/outcomes ("show me every case where partner A used argument X before judge Z and won"). **Zero references anywhere in `vindex.js` — genuinely dead, no UI label or button found under any name searched ("Memory Graph", "Mreža argumenata" or similar).** This is a real Bucket A finding, and arguably the most interesting one in this whole census: exactly the kind of institutional-memory query the founder's own product philosophy documents describe as valuable, sitting completely unreachable.

These three are NOT duplicates of each other — each answers a genuinely different question — but three
independently-built "graph" features is worth the founder knowing about as a set, not just as three
unrelated line items.

---

## 3. Main navigation audit

Ground truth is `index.html`'s tab bar (`vindex.js` only manipulates `document.getElementById` on IDs
this file defines). Top-level tabs, in order:

| Tab ID | Label/purpose (inferred from ID + surrounding code) | Backend area |
|---|---|---|
| `tab-btn-h` | Home / dashboard (KPIs, morning briefing, priority cases) | Multiple — dashboard aggregator, `morning_briefing.py` |
| `tab-btn-p` | Predmeti (cases) | Core case CRUD |
| `tab-btn-k` | Klijenti (clients) | `klijenti/router.py` |
| `tab-btn-kal` | Kalendar (calendar/deadlines) | `kalendar.py`, `rokovi_lanac.py` |
| `tab-btn-aiws` | AI Workspace — internal mode-switcher with 5+ sub-modes (`zakon`/`analiza`/`nacrti`/`strategija`/`oblasti`, plus the gated `digitalna_imovina` Web3 mode) | `oblasti.py` (confirmed wired here), Web3 module (gated) |
| `tab-btn-s` | Search (sudska praksa / case law search) | Legal-research search, distinct from the app's own document/case search |
| `tab-btn-dok` | Dokumenti (documents) | Document management |
| `tab-btn-doctpl` | Document templates (separate button, not a tab — opens a modal via `docTplOpen()`) | Templates |
| `tab-btn-zadaci-g` | Zadaci (tasks) | `zadaci.py` |
| `tab-btn-fin` | Finansije (finance/billing) — confirmed hosts `billing_reports.py` | `billing_reports.py`, likely `profitabilnost.py` |
| `tab-btn-kanc` | Kancelarija (firm/office settings) | Firm-level settings |
| `tab-btn-pi` | Poslovna inteligencija (business intelligence) — **hidden tab** (`vx-hidden-tab` class), reached only via an internal link (`index.html:498`, from the finance tab's "izveštaji naplate" cross-link), not a normal top-level nav click | Likely `profitabilnost.py` and/or `analytics.py` |
| `tab-btn-settings` | Settings | Various, including the Web3 mode gate |
| `tab-btn-notif` | Notification dropdown trigger — **hidden tab** (`vx-hidden-tab` class), not a real navigable tab, just a hook for the notification bell | Notifications |

**No top-level nav item exists for**: Smart Intake (already known — the headline finding from the
prior session), Case Genome (reached only as a sub-panel within a case's own detail view, not
independently — expected, since it's case-scoped, not a standalone feature), Evidence Vault (same —
case-scoped), Memory Graph (confirmed dead above), any of the 12 Bucket-A dead routers.

**Structural observation**: several real capabilities (`oblasti`, the gated Web3/`digitalna_imovina`
mode, `evidence-graph`, `knowledge-graph`) are reached not via top-level nav but via the AI Workspace
tab's internal mode-pill system or from within a case's detail view — meaning "is it in the main nav"
is the wrong single test for this app's structure. A more accurate question, not fully answered in
the time available: for each Bucket-A dead router, would it belong as a NEW AIWS mode pill (cheap,
consistent with the existing pattern) or does it need its own top-level tab? Recommend the
orchestrator make this call per-capability rather than uniformly.

---

## 4. Duplicate-logic findings

1. **Client CSV import — two full implementations, only the less-safe one live** (detailed in section
   1 above: `import_klijenti.py`'s preview-then-confirm flow vs. `klijenti/router.py`'s direct-execute
   `/klijenti/import-csv`).
2. **WhatsApp notifications — two full Twilio-based implementations, only the simpler one live**
   (detailed in section 1: `whatsapp_notif.py`'s dedicated subscription system vs. `sms.py`'s
   single-flag approach).
3. **Three independent "graph" visualization systems** (section 2 above) — not duplicates of each
   other functionally, but worth the founder seeing as a set given how much overlap "graph
   visualization of case relationships" implies at a glance.
4. **Search**: confirmed `routers/search.py` (the global search this session already extended to 7
   types) is the only GENERAL search implementation. The `tab-btn-s` tab's "sudska praksa" search is a
   legal-research search over external case-law/statute content (a fundamentally different corpus —
   not a duplicate of the app's own case/document/task search). No duplicate search logic found beyond
   this expected, intentional split.
5. **Notification scheduling**: confirmed no third scheduling mechanism beyond the already-known email
   cron (`email_notif.py`) and the SMS/WhatsApp cron path (`sms.py`) — `whatsapp_notif.py`'s own send
   logic is dead code, not a live third scheduler (see finding #2).
6. **Document linking**: not independently re-checked beyond what LZ-series/ZTC-series already
   confirmed clean this session (no new evidence of a duplicate document-linking mechanism found
   during this census).

---

## 5. Prioritized Bucket-B candidates for tonight's wiring

**None of the 17 originally-flagged routers are true Bucket B** (frontend built, just missing a nav
link) — every genuinely-dead one among them has zero frontend code referencing it at all, meaning
"just add a nav link" isn't available as a fix; each would need at minimum a new button/modal wired
to an existing, working backend endpoint. That is still "safe frontend exposure" per this mission's
Phase 4 charter (no backend changes, no architecture changes) — just not as cheap as a single nav-menu
line addition.

Ranked by (a) genuine lawyer value, (b) how small the needed frontend addition is, (c) zero
architectural/design ambiguity:

1. **`case_intelligence`'s per-case briefing** (`POST /api/intelligence/predmeti/{id}/briefing`) — a
   single "AI Briefing" button inside the existing case-detail view, calling one existing endpoint,
   rendering one aggregated result. Smallest plausible frontend addition of anything on this list;
   directly matches the founder's own "bez otvaranja deset ekrana" framing.
2. **`gdpr` self-service export/delete** (`/api/gdpr/export`, `/api/gdpr/account`) — two buttons in the
   existing Settings tab (`tab-btn-settings`, already exists), calling two existing endpoints. Real
   legal/compliance value (a lawyer's own GDPR obligations to their own account), low frontend cost.
3. **`memory_graph`'s relationship query** (`GET /api/memory-graph/upit`) — higher value but a bigger
   frontend lift (a genuine new query UI, not a single button) — likely belongs as a new AIWS mode
   pill given the existing pattern, but that's a design choice worth the orchestrator confirming rather
   than assuming.
4. **`import_klijenti`'s safer 3-step import** — this one is more of a "which of two existing
   implementations should be live" product decision (replace `/klijenti/import-csv` entirely, or add
   the safer flow as an alternative "advanced import" option) than a pure wiring task — flagging for
   the orchestrator's judgment rather than picking one.
5. **`whatsapp_notif`'s dedicated subscription granularity** — lowest priority: `sms.py`'s simpler
   single-flag approach already covers the core need (WhatsApp vs. SMS delivery). Reconnecting the
   dedicated router would mostly duplicate what already works, not add clearly new lawyer value — a
   candidate for deletion/cleanup rather than reconnection, on the evidence gathered here.

Not confidently rankable without more time: `agent_notifications`, `auto_discovery` (admin-only,
lower lawyer-facing priority regardless), `knowledge_hygiene`, `knowledge_transfer`, `region`,
`status_page`, `strategy_simulator`, `style_checker` — all genuinely dead, all real features, none
independently assessed for relative value/effort beyond confirming they exist and are unreachable.

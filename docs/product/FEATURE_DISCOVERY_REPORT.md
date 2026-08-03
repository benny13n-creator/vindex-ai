# Feature Discovery Report

**Mission:** Operation Invisible Features (BETA-003), founder's Master Prompt, 2026-08-03.
**Mission success condition:** the number of production-ready but unreachable features is measurably
reduced — not measured by new code written.
**Result:** 2 real invisible features connected and shipped tonight (both verified as genuinely useful,
non-duplicate, low-risk additions to existing UI); 3 more found and correctly escalated as founder
decisions rather than guessed at; a fresh, corrected census of every backend router's true reachability
status, superseding the repo's own two-week-old audit tool output.

Full investigation: `.vindex_ai_team/decisions/2026-08-03_invisible_features_CENSUS.md`.

---

## Implemented Features (this session, this mission)

| Feature | What changed | Why prioritized |
|---|---|---|
| **GDPR self-service account deletion** (IF-001) | New button in Settings → Nalog, wired to the already-working `DELETE /api/gdpr/account`. | The public security whitepaper (`static/bezbednosni-list.html`) explicitly promises this button is "in preparation" — this fulfills an existing public commitment, not a speculative feature. |
| **Per-case AI Briefing** (IF-002) | New button in the case-detail view's Case Intelligence section, wired to the already-working `POST /api/intelligence/predmeti/{id}/briefing`. | Directly matches the founder's own "bez otvaranja deset ekrana" framing for this exact endpoint's docstring — one aggregated recommendation instead of five separate panels. |

Both: zero backend changes, zero schema changes, zero new AI logic — pure frontend wiring to
already-correct, already-tested backend code. Full regression suite re-run: 2306 passed, 1 skipped, 0
failed (unchanged from before this mission — no backend was touched).

## Reachable Features (confirmed working, no action needed)

Analytics (`/analytics/usage`), billing reports (`/billing/report`, "Finansije" tab), both export
routers (GDPR-narrower `/api/gdpr/export` is a live-but-inferior duplicate of the wired
`/api/export/complete`; `/export/docx`+API-keys+PDF export all separately wired), Voice (both command
and realtime-session engines, with an always-visible mic button in the main UI chrome — the single
most prominently-wired AI feature in the app), Evidence Graph (`/api/evidence-graph`, 4 references),
Knowledge Graph (`/api/knowledge-graph`, cross-entity legal network), the Web3/Digital Asset Compliance
Suite (AML/CARF/DAC8/MiCA/whitepaper-analysis — heavily wired, 14+ references), `oblasti` and
`ugovor_zastupanja` (both false negatives from the repo's own audit tool — see below).

## Invisible Features (genuinely dead, real value, no known reason)

12 routers confirmed to have real logic and zero frontend callers of any kind:

| Router | What it does | Relative priority |
|---|---|---|
| `case_intelligence` | Per-case AI briefing | **Fixed tonight (IF-002)** |
| `gdpr` (account deletion half) | Self-service erasure | **Fixed tonight (IF-001)** |
| `memory_graph` | Cross-case relationship queries ("every case where X argued Y before judge Z and won") | Highest remaining value — but NOT safely wireable as-is (see Founder Decisions below) |
| `agent_notifications` | Accept/reject feed for background-agent recommendations | Real, unranked this session |
| `import_klijenti` | Safer 3-step CSV client import (preview + confirm) | Product decision needed (see below) — a genuine duplicate, safer implementation is the dead one |
| `knowledge_hygiene` | Personal knowledge-base maintenance (scan/contradictions/archive/merge) | Real, unranked this session |
| `knowledge_transfer` | External knowledge-profile extraction | Real, unranked this session |
| `region` | Country-specific legal support (courts/deadlines/AI advice) | Real, unranked this session |
| `status_page` | Admin-facing public status/incident management | Standalone `status.html` exists — needs one direct follow-up read to confirm if it's independently wired or also dead |
| `strategy_simulator` | Chess-like case-strategy game-tree simulator | Real, unranked this session |
| `style_checker` | Lawyer's own writing-style profile builder | Real, unranked this session |
| `whatsapp_notif` | Dedicated WhatsApp subscription system | Product decision needed (see below) — likely a deletion candidate, not a reconnection one |
| `auto_discovery` | Bulk PDF ingestion for Pinecone | Admin-only by design, lower lawyer-facing priority regardless of reachability |

## Partially Connected Features

None found this session in the strict sense (backend built, frontend built, just missing a nav link) —
every genuinely-dead router above has **zero** frontend code referencing it, not merely a missing menu
entry. The nearest thing to "partially connected": Memory Graph's query endpoint is technically
wireable, but the table it reads has no automatic writer anywhere — connecting the query UI alone would
show every real user a permanently empty result (see Founder Decisions).

## Dead Features (deliberately, correctly, no action needed)

- `routers/onboarding.py`'s 5 endpoints — confirmed **deliberately superseded**: explicit code comments
  in `vindex.js` ("stari onboard_show je deaktiviran") confirm the live onboarding flow calls a
  different endpoint entirely. Not a bug, not touched.
- `/viber/webhook` — genuine external webhook (Viber platform calls it), correctly has no frontend
  caller by design.

## Duplicate Features

1. **Client CSV import** — a safer, unused 3-step flow vs. a simpler, live one-shot flow. Founder
   decision required (see below).
2. **WhatsApp notifications** — a dedicated, unused subscription system vs. a simpler, live
   flag-on-SMS-profile approach. Founder decision required (see below).
3. **Three independent "graph" systems** (Evidence Graph, Knowledge Graph, Memory Graph) — confirmed
   NOT duplicates of each other (each answers a genuinely different question: one case's internal
   entity relationships, cross-entity legal network, cross-case argument/outcome history) — but worth
   the founder seeing as a set, since two of the three are fully wired and one is fully dark.
4. **GDPR export** — `/api/gdpr/export` (dead) is a narrower duplicate of the already-wired
   `/api/export/complete`. Correctly left unconnected; wiring it would have shipped a duplicate for no
   benefit.

## Recommended Wiring (not attempted tonight, no architectural blocker — just not reached)

`agent_notifications`, `knowledge_hygiene`, `knowledge_transfer`, `region`, `strategy_simulator`,
`style_checker` — all genuinely dead, all real, unranked relative to each other this session. Per the
North Star discipline established earlier in this multi-night engagement, these should be prioritized
by actual lawyer value once someone assesses each individually, not wired reflexively just because they
were found. `status_page` needs one direct follow-up (read `static/status.html`'s own script — it may
already be independently wired with its own client-side code, not through `vindex.js`).

## Founder Decisions Required

1. **Client CSV import**: keep the live one-shot flow, replace it with the safer preview-then-confirm
   flow, or offer both? Full evidence: `.vindex_ai_team/decisions/2026-08-03_IF-DECISIONS_duplicates_and_memory_graph_BLOCKER_REPORT.md`.
2. **WhatsApp notifications**: confirm the simpler flag-based approach (already live) is the intended
   final design, so the dedicated unused subscription system can be either reconnected (if more granular
   control is actually wanted) or deleted (if it's dead weight) — a decision this mission won't make
   unilaterally either way.
3. **Memory Graph**: manual relationship entry as the intended UX (needs UI for both adding AND
   querying), or automatic extraction from existing case data (new AI logic, explicitly out of this
   mission's scope, needs its own future mission)? Shipping only a query box tonight would show every
   real lawyer a permanently empty graph — worse than leaving it dark, since it would look broken rather
   than simply not-yet-built.

## Estimated Lawyer Value

Both features shipped tonight are immediately usable with zero training or workflow change: a settings
button and a case-detail button, both producing results a lawyer already implicitly expects from
software with this feature set (self-service data rights; one aggregated recommendation instead of five
panels). The three escalated items are each larger in potential value (institutional memory search
being the most novel) but require a design decision this mission's own discipline says shouldn't be
guessed — shipping them blind risks either a duplicate UX (import/WhatsApp) or a feature that looks
broken on day one (Memory Graph).

## A note on tooling accuracy

This mission's investigation found the repo's own pre-existing dead-router audit script
(`scripts/audit_routers.py`) has both false negatives (a route containing "health" masks a genuinely
dead module as "maybe external" — this is exactly what hid Smart Intake from the prior mission's
investigation until manually checked) and false positives (dynamically-constructed frontend paths like
`fetch(BASE_URL + '/api/oblasti/' + var)` aren't detected, wrongly flagging `oblasti` and
`ugovor_zastupanja` as dead when both work correctly). Every finding in this report was independently
re-verified by reading actual code and frontend usage, not taken from the script's raw output. Improving
the script itself was not attempted (out of this mission's "connect existing, don't build new" scope),
but is worth naming as a small, cheap, high-leverage fix for whoever runs the next audit.

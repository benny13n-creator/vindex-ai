# Context Builder Registry — Program Tau, Master Sprint 002, Phase 1

**Date**: 2026-08-06
**Purpose**: exhaustive map of every AI context-assembly function in the repo — what it sees, what it
doesn't, exact document/token caps, and consumers — ahead of designing the single Canonical Case Context
Contract (Phase 2). Produced by 2 independent forensic forks, one deepening the 4 builders already known
from Tau Sprint 001's `CASE_CONTEXT_ARCHITECTURE.md`, one sweeping the rest of the repo. Every claim below
cites file:line; gaps in verification are stated explicitly, not silently assumed.

---

## Critical scoping correction before the registry itself

**`strategija.py` is NOT a context builder and cannot be migrated the same way as the other 3 mandatory
Phase 5 modules.** This resolves an open question Tau 001 itself flagged rather than answered. Two
distinct files share the name in casual reference:

- Top-level `strategija.py` (the reasoning engine — `red_team_analiza_sync`, `litigation_simulator_sync`,
  `orkestrator_kompletna_analiza_sync`, etc.) has exactly one import (`shared.llm_retry`), zero Supabase
  access, and every function takes case text as a plain string **parameter**.
- `routers/strategija.py` (the actual FastAPI router — a separate file; Tau 001's Agent 1 counted "11
  call sites" under one label without distinguishing the two) exposes 7 request models, **none of which
  has a `predmet_id` field** (confirmed by reading `routers/strategija.py:65-399` in full). It never
  queries `predmet_dokumenti`/`predmet_dokazi`/`case_dna`/`case_actions` anywhere — zero grep hits for all
  four across the whole file.

It is architecturally a "paste your own case description" tool, not a case-ID-driven endpoint. Migrating
it onto `build_case_context()` would mean **adding** a `predmet_id`-based invocation mode — a feature
change — not swapping a context builder for a canonical one — a plumbing change. This is addressed
directly in `AI_ENTRY_POINT_MIGRATION_REPORT.md` (Phase 5) rather than forced into the same migration
shape as the other 3. (Separately: `TAU-004`, the finding that `strategija.py`'s `_V2_SYSTEM` prompt
GPT-invents risks/gaps/next-steps, is about decision-making boundary, not context visibility, and is
unaffected by this finding — that debt item still stands.)

---

## The 4 builders named in Tau 001 / this sprint's mandatory Phase 5 scope (3 of 4 — see above)

### `routers/case_commander.py::_dohvati_predmet_kontekst` + `_formatiraj_kontekst`
- **Lokacija**: `_dohvati_predmet_kontekst` case_commander.py:85-175; `_formatiraj_kontekst` case_commander.py:272-324.
- **Ulazni podaci**: `predmeti.*` (incl. `case_dna`), `rokovi` (10, ordered), `predmet_dokumenti` (`naziv_fajla, created_at, tekst_sadrzaj, tip_dokaza, status`, no `.order()`), `predmet_komentari` (5), `case_actions` (open only), `predmet_dokazi` (`snaga, kategorija, pravni_element`), `rocista`.
- **Šta vidi (u GPT-facing tekstu)**: case metadata, all 10 fetched rokovi, **10 of the up to 20 fetched documents**, truncated to a shared budget.
- **Šta ne vidi (u GPT-facing tekstu)**: `case_dna`/Genome and `dokazi`/evidence ARE fetched but never appear in `_formatiraj_kontekst`'s own output — consumed only by `_kanonski_nalazi`'s structured/canonical path (Sigma 005). `case_actions` likewise fetched but not in GPT text.
- **Maksimalni broj dokumenata**: fetch-capped at **20** (case_commander.py:123, no `.order()` — default DB order); GPT-text-capped at **10** (case_commander.py:302).
- **Token/karakter ograničenje**: **8000 chars total, 2000 chars/doc max** (case_commander.py:268-269).
- **Potrošači**: `commander_analiza` (free-text path); `_kanonski_nalazi`'s structured output feeds `commander_quick_check`/`commander_checklist` separately. Zero live frontend callers confirmed (Tau 001).

### `routers/case_intelligence.py::_gather_case_data` + `_build_context_text`
- **Lokacija**: `_gather_case_data` case_intelligence.py:83-212; `_build_context_text` case_intelligence.py:215-338; GPT call `_pozovi_briefing_api` case_intelligence.py:37-49.
- **Ulazni podaci**: `predmeti` (incl. full `case_dna`), `lessons_learned` (5), `firm_dna` (5), `case_patterns` (3), `proactive_alerts` (5), `decision_log` (5), `client_twin_profili` (1), `knowledge_profiles` (top 2).
- **Šta vidi**: full structured Genome narrative (pravna teorija, snaga %, najslabija tačka, strategija/scenariji, finansije, nedostaje[:3], heatmap, kontradikcije[:3]) plus lessons/firm-DNA/patterns/alerts/decisions metadata.
- **Šta ne vidi**: **zero** query for `predmet_dokumenti` or `predmet_dokazi` anywhere — no document text, no evidence records, ever.
- **Maksimalni broj dokumenata**: **0** — document content never queried.
- **Token/karakter ograničenje**: **10,000 chars** hard cut of the whole assembled narrative (case_intelligence.py:45).
- **Potrošači**: `POST /api/intelligence/predmeti/{predmet_id}/briefing`. **Live-caller status not yet verified** — flagged for Phase 5, do not assume live or dead without checking `static/vindex.js`.
- **Governance note** (context-adjacent, not context-visibility): `sledeci_korak`/`hitnost` follow the override-with-GPT-fallback pattern (`top_open_action` overrides only when an open action exists, case_intelligence.py:381-397, falls back to GPT's own guess otherwise or on exception) — this is `TAU-002`'s subject, unaffected by Phase 5's context work alone.

### `routers/copilot.py` — 2 real GPT context builders (a 3rd handler found this sprint is deterministic, not in scope)
- **`_handle_analiza_predmeta`** (copilot.py:299-465): fetches `predmeti` (incl. `case_dna`), `predmet_beleske` (5), `predmet_dokumenti` (**`naziv_fajla,status` only — no `tekst_sadrzaj` column, copilot.py:317**), `predmet_hronologija` (8), `predmet_istorija` (2), `case_actions` (open, next-action override). Sees compact Genome summary, document **filenames only** (zero content), no evidence.
- **`_handle_plan_predmeta`** (copilot.py:468-585): same shape — `predmet_dokumenti.select("naziv_fajla,status")`, **max 6 filenames** joined into one line (copilot.py:531), zero content. Pulls up to 5 Pinecone `sudska_praksa` matches (external, not case-internal). `nedostaje` partially canonical via `shared/gap_engine.py::missing_evidence_plan_items` (copilot.py:574-576), same fallback shape as case_intelligence.py.
- **`_handle_predlozi`** (copilot.py:811+): **not a GPT context builder** — deterministic rule-based (checks upcoming rokovi/hronologija, no `case_dna` selected). Noted for completeness, out of Case Context Contract scope.
- **Maksimalni broj dokumenata**: 0 content chars in either handler (filenames only, capped at 6 in the plan handler).
- **Potrošači**: copilot.py's own message-routing dispatcher (dispatcher logic not traced this pass — flag for Phase 5).

### `routers/morning_briefing.py` — 3 GPT call sites, ALL metadata-only
- **`_generiši_briefing`** (morning_briefing.py:86-230, `max_tokens=600`): fetches `predmeti` (20, **no `case_dna` in select**), `rokovi`/`rocista` (7-day window), `klijenti` (100). Consumers: `GET /api/briefing/daily`, `POST /api/briefing/cron` (external cron, 06:00 UTC daily).
- **`_ai_prioritizacija_alertova`** (morning_briefing.py:632-664, `max_tokens=250`): operates on an already-fetched deadline-derived alert list, no document/Genome/evidence input. Consumer: `POST /api/briefing/nightly-intelligence`.
- **Third call site** (`max_tokens=120`, morning_briefing.py:1083): feeds `GET /today-focus`, same metadata-only shape.
- **Maksimalni broj dokumenata**: **0** across all 3 — document table never queried anywhere in this file.

---

## Additional real context builders found this sprint (not in Tau 001's registry, out of Phase 5's mandatory list but relevant to the Canonical Context design)

### `routers/multi_agent.py::run` (inline context block, ~L424-540)
- **Ulazni podaci**: `predmeti`, `predmet_dokumenti` (`.limit(10)`, ordered by `redni_broj`), `rocista` (`.limit(5)`), `case_dna` (gated behind `if dok_rows:`, L473-477).
- **Šta vidi**: up to 5 of 10 fetched documents (2500 chars/doc), a genuinely rich Genome summary (pravni identitet, osnov odgovornosti, uzročna veza, snaga %, najslabija tačka + preporuka, `nedostaje[]`), deadlines. **The richest existing "documents + Genome + deadlines together" builder found in this sprint.**
- **Šta ne vidi**: `predmet_dokazi` (evidence) — zero references; `case_actions` — zero references.
- **Maksimalni broj dokumenata**: 10 fetched, 5 shown, 2500 chars/doc.
- **Potrošači**: `POST /multi-agent/run`, `/run-parallel`, `/pipeline`.
- **Assessment**: still a 5th independent hand-rolled implementation — exactly the fragmentation this sprint exists to end, even though it's the closest existing approximation of the target shape.

### `routers/evidence_graph.py::generisi_graf` (~L195-247)
- **Ulazni podaci**: `predmeti` metadata, `predmet_dokumenti` (`id,naziv_fajla,tip_dokaza,tekst_sadrzaj`, `.limit(15)`, no explicit order), `predmet_komentari` (10), `rocista` (10).
- **Šta vidi**: up to 15 documents (per-document truncation logic lives inside `_izgradj_kontekst`, **not independently verified this pass** — read that helper directly before relying on this entry for Phase 3), comments, deadlines.
- **Šta ne vidi**: `case_dna` — zero query; `predmet_dokazi` — zero query; `case_actions` — zero query (confirmed via the full parallel-fetch block, L207-228).
- **Potrošači**: contradiction-detection endpoint (Program Gamma, 2026-08-04).

### `routers/case_dna.py` — Genome's own extraction-side context (flagged as likely out of Phase 2/3 scope)
Fetches `predmet_dokazi` and document text to **compute** `case_dna` itself via GPT — this is the Genome's
own source-of-truth-generation step, not a consumer reading already-computed Genome. Document/truncation
limits not verified this pass (out of budget). **Scope decision for Phase 2**: this stays out of the
Canonical Case Context Contract, which is about assembling context for reasoning ABOUT an existing case,
not about how Genome itself gets computed — that's Genome's own concern (`DC-003`/`DC-007`), unchanged by
this sprint.

### `services/legal_reasoning_engine.py` — already deeply covered by Tau 001, unchanged
`.select("id,naziv,tip,opis,case_dna")` + `predmet_dokazi` + `genome = predmet.get("case_dna")`. Already
documented by Tau 001 as "the strongest existing anti-hallucination pattern in the codebase" (SOURCE-n
citations built only from real retrieved tuples). No new findings this sprint; re-listed for registry
completeness only.

### `routers/cross_doc.py` — the existing document-scale-correct sampler (Phase 3's template)
Already documented in depth by Tau 001 (`CASE_CONTEXT_ARCHITECTURE.md`): `_uzorkuj_dokument`
(cross_doc.py:~120-150) uses stride-based sampling (`segments[::korak]`) across a document's full length,
not naive head-truncation, specifically so late-document content has a chance of being sampled. This is
the reference pattern Phase 3's Document Visibility Engine Layer 4 reuses rather than reinvents, per this
sprint's own explicit "ne praviti paralelne context builder-e" constraint.

---

## Confirmed NOT context builders (negative finding, grep-verified: zero hits for `predmet_dokumenti`/`predmet_dokazi`/`case_dna`/`case_actions`)

`routers/court_predictor.py`, `drafting/router.py`, `web3_compliance.py`, `klijenti/router.py`. Grep-level
confirmation only, not an exhaustive line-by-line read — a case-content query under a different table
alias is theoretically possible but was not found.

## Not conclusively checked this sprint (explicitly flagged, not assumed either way)

`routers/drafting.py` (L303-320 shows a `predmet_dokumenti` INSERT for a newly-drafted document — not
clearly a multi-document READ for GPT context; needs a closer read before classification). `copilot.py`'s
own message-routing dispatcher (which handler gets called when — not traced).

## Summary

**7 real context-assembly surfaces total**: the 3 migratable mandatory ones (`case_commander.py` — already
migrated for its structured path in Sigma 005, still gapped on its free-text path; `case_intelligence.py`;
`copilot.py`), `morning_briefing.py` (mandatory but currently the most metadata-only), plus 3 non-mandatory
ones relevant to Phase 2/3 design (`multi_agent.py`, `evidence_graph.py`, `case_dna.py`'s extraction side —
the last one out of scope by design). `strategija.py` is not a context builder at all (see scoping
correction above). `legal_reasoning_engine.py` and `cross_doc.py` are already well-understood reference
patterns, not migration targets themselves.

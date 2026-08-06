# Case Context Architecture — Program Tau, Master Sprint 001, Agent 3

**Datum**: 2026-08-06
**Scope**: how Vindex assembles case context before every AI call — does GPT see the complete case (documents + Genome + evidence) or a partial/blind view? Analysis only, no code changed.

---

## Headline finding

**There is no single "complete case context" builder in this repo.** Four independent, hand-rolled context-assembly functions exist across `routers/case_commander.py`, `routers/case_intelligence.py`, `routers/copilot.py`, and `routers/morning_briefing.py` — each with a *different, non-overlapping* blind spot. None of the four gives GPT documents + Genome + evidence together. A GPT-5.1 reasoning layer sitting on top of any one of these will reason confidently over an incomplete picture, regardless of model quality — this is a context problem, not a model problem, and upgrading the model alone does not fix it.

| Function | Sees document TEXT? | Sees Genome (`case_dna`) as text? | Sees evidence (`predmet_dokazi`)? | Sees `case_actions`/readiness? |
|---|---|---|---|---|
| `case_commander.py::_formatiraj_kontekst` (case_commander.py:272-324) | Partial — 10 of up to 20 fetched docs, 2000 chars/doc, 8000 total | **No** — `case_dna` fetched via `select("*")` at case_commander.py:99 and used in `_kanonski_nalazi` (canonical math only, case_commander.py:187-262) but never appears in `_formatiraj_kontekst`'s own text | **No** — `dokazi` fetched (case_commander.py:141-147) for canonical math only, never in GPT-facing text | Fetched but also canonical-only, not in GPT text |
| `case_intelligence.py::_build_context_text` (case_intelligence.py:215-338) | **No** — `predmet_dokumenti` is never queried in `_gather_case_data` at all | Yes — full structured Genome dump (case_intelligence.py:223-289: pravna teorija, snaga, najslabija tačka, strategija, finansije, kontradikcije) | **No** — `predmet_dokazi` never queried | N/A (different endpoint family) |
| `copilot.py` (2 context builders, copilot.py:307-350 and :475-575) | **Metadata only** — `predmet_dokumenti.select("naziv_fajla,status")` (copilot.py:317, :483) — filename/status, content column deliberately excluded | Yes — `case_dna` included in the same `select(...)` (copilot.py:315, :481) | **No** — no `predmet_dokazi` query anywhere in the file | Not checked beyond genome |
| `morning_briefing.py` | **No** — zero references to `predmet_dokumenti` or `tekst_sadrzaj` anywhere in the file (grep: no matches) | **No** — zero references to `case_dna` (grep: no matches) | **No** — zero references to `predmet_dokazi` | Reads `predmeti`/`rokovi`/`rocista`/`proactive_alerts`/`lessons_learned` only (morning_briefing.py:96-123, 932-1041) |

Every row was verified by direct grep + read of the named file, not inferred.

## Per-function detail

### 1. `case_commander.py` — document-partial, Genome-blind (in GPT text)

`_dohvati_predmet_kontekst` (case_commander.py:85-175) fetches `predmet_dokumenti` with `.limit(20)` (case_commander.py:120-124, no explicit `order()` — default DB order, not recency- or relevance-ranked). `_formatiraj_kontekst` (case_commander.py:272-324) then further restricts to `ctx["dokumenta"][:10]` (case_commander.py:302) — **only 10 of the (already-capped-at-20) fetched documents are named at all**, with a shared 8000-char / 2000-char-per-doc budget (case_commander.py:268-269, comment explicitly notes this is deliberate — avoids 2-3 large docs eating the whole budget, Program Celina 2, 2026-07-24).

For the mission's own named "500 documents" extreme-scale scenario: 490 of 500 documents are invisible to this endpoint's GPT call — not summarized, not sampled, simply never fetched. The 10 that are shown get on the order of ~800 chars each on average.

`case_dna` (Genome) and `dokazi` (evidence) ARE fetched (case_commander.py:99, 141-147) and used correctly in `_kanonski_nalazi` (case_commander.py:187-262, Sigma Sprint 005's own canonical-reads migration) — but that function returns structured `canonical_field()` dicts for the API response, not text injected into the GPT prompt. The GPT call in `commander_analiza` (case_commander.py:377-390) sends only `_formatiraj_kontekst`'s output, which never mentions Genome or evidence. This is *correct* under Sigma 005's GPT Boundary Policy (GPT is only asked for 2 narrow advisory fields — protivnikova strategija, sudska praksa — not for anything Genome/evidence would inform) but means those 2 advisory answers are themselves being generated blind to the case's own strength assessment and evidence inventory, which is a real quality gap for advisory output.

### 2. `case_intelligence.py` — Genome-rich, document-blind

`_gather_case_data` (case_intelligence.py:83-212) never queries `predmet_dokumenti` or `predmet_dokazi` at all — confirmed by full read of the function; its `asyncio.gather` (case_intelligence.py:115-162) covers only `lessons_learned`, `firm_dna`, `case_patterns`, `proactive_alerts`, `decision_log`, plus `client_twin_profili` and `knowledge_profiles`. `_build_context_text` (case_intelligence.py:215-338) builds a genuinely rich Genome narrative (kontradikcije, najslabija tačka, heatmap, scenariji) — but GPT reasoning here has zero access to the underlying document text or evidence records that the Genome was originally computed from. If Genome is stale relative to newly uploaded documents, this endpoint has no way to know.

### 3. `copilot.py` — Genome-aware, document-name-only

Both context builders (copilot.py:307-350, :475-575) select `case_dna` alongside `predmeti` core fields, but their own `predmet_dokumenti` query is explicitly `select("naziv_fajla,status")` (copilot.py:317, :483) — `tekst_sadrzaj` is not in the column list, so document content is structurally excluded, not merely truncated. GPT here knows document *names* exist (e.g. "ugovor.pdf — status: obrađen") but never sees a single word of their content.

### 4. `morning_briefing.py` — metadata-only, fully document/Genome/evidence-blind

Confirmed via grep across the whole file: no reference to `predmet_dokumenti`, `tekst_sadrzaj`, `case_dna`, or `predmet_dokazi` anywhere. Its GPT calls (morning_briefing.py:208, 645, 1078) work purely from `predmeti`/`rokovi`/`rocista`/`klijenti`/`proactive_alerts`/`lessons_learned` metadata rows. This is likely intentional given its "digest" framing, but it means any GPT-5.1 reasoning applied here inherits zero case substance — only schedule/status metadata.

### 5. The one system that *does* handle document scale correctly: `routers/cross_doc.py`

`_uzorkuj_dokument` (cross_doc.py:~120-150) uses stride-based sampling (`segments[::korak]`, cross_doc.py:137) across a document's full length rather than naive head-truncation, with an explicit comment (cross_doc.py:134, 144) that this exists specifically so late-document content (e.g. page 80) has a chance of being sampled — this is Program Celina, AKCIJA 2 (2026-07-24)'s own fix, confirmed still in place (not regressed). `cross_doc.py:336` even has a comment noting the OLD `[:4000]` hard-cut was replaced. **This sampling logic is not reused by any of the 4 functions above** — each reinvents its own cruder truncation (`[:2000]` per-doc slices in case_commander.py, no document text at all in the other 3) instead of calling into `cross_doc.py`'s existing, better-tested sampler.

## Token-budget sanity check (mission's own "500 documents" scenario)

None of the 4 case-context builders would fit a 500-document case in a normal context window even if they tried — and none of them try. `case_commander.py` caps at 10 named documents; the other 3 don't fetch document content at all. There is no chunking/embedding-retrieval/map-reduce step in any of the 4 — `cross_doc.py`'s map-reduce sampler is the only piece of the codebase built for that scale, and it lives in an unrelated, unconnected endpoint family (document comparison, not case-wide reasoning).

## What this means for GPT-5.1 specifically

A stronger reasoning model does not compensate for missing input — it will reason more confidently over the same incomplete context, which is a bigger risk than a weaker model doing the same, not a smaller one. Any GPT-5.1 "reasoning layer" work should treat unifying/completing case context as a prerequisite, not a follow-on — this is a candidate for Agent 8's roadmap to flag as a blocking dependency, not a nice-to-have.

## What I could not verify

- `routers/strategija.py` and `routers/multi_agent.py` were not deep-read (grep for document/genome/evidence terms in `strategija.py` returned zero matches — either it doesn't touch case-level content either, or it reads through a helper imported from elsewhere not caught by the grep; flagging rather than asserting).
- Whether Supabase's default row order for the un-ordered `predmet_dokumenti` queries (case_commander.py:120-124) is consistently insertion-order or could vary — not verified against the actual DB, only inferred from the absence of an `.order()` call.

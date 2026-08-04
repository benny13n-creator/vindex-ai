# Program Gamma — Domain Inventory: Search / Intake-Evidence Classification / Firm Brain / Case Pipeline

**Mission:** Masterprompt 003, "Canonical Decision Engine — Eliminate Entire Classes of Decision
Fragmentation." Third lens on the same codebase Program Alpha (structural duplication) and Program Beta
(AI-reasoning defects) already covered same-day. Gamma's question: is a BUSINESS OR LEGAL DECISION
(document significance, case status, escalation need, fact classification, case quality, etc.)
independently produced by more than one module. Read-only, no code/git touched. All claims re-verified
against current code today, not cited from prior missions on faith.

**Scope:** `routers/search.py::global_search`, `shared/intake_classify.py` + `routers/evidence.py`'s
classifier (reframing Program Alpha's ALPHA-003), `routers/firm_memory.py` vs.
`api.py::_fetch_firm_memory_context` (reframing ALPHA-005), `services/case_pipeline.py`'s 9 steps vs.
`services/risk_engine.py` and other decision-owning modules.

**Prior art read first:** `docs/architecture/AI_DECISION_GRAPH.md` (Program Beta), `docs/architecture/
BUSINESS_LOGIC_INVENTORY.md` + `ARCHITECTURAL_DEBT_REGISTER.md`'s ALPHA-003/004/005 (Program Alpha).
Not re-derived from scratch — reframed under the Decision-ownership lens where new evidence changes the
picture, cited as prior art where it doesn't.

---

## 1. `routers/search.py::global_search` — CONFIRMED clean, no decision-making

Full file read (295 lines). Re-verifies Program Alpha's own inventory item #22 ("1 — clean") independently.

- Every per-type helper (`_search_predmeti`, `_search_klijenti`, `_search_dokumenti`, `_search_zadaci`,
  `_search_billing`, `_search_hronologija`, `_search_beleske`, lines 38–216) is a direct Supabase `.ilike()`
  / `.or_()` query. **Zero LLM calls, zero scoring, zero ranking logic anywhere in the file** (grepped for
  `openai|gpt-|chat_completion` — no matches).
- The one place a "decision" could hide — cross-type result ordering/significance — does not exist: results
  are grouped by `tip` and returned in whatever order Postgres returns matching rows (`global_search`,
  lines 267–294), not re-ranked by relevance, recency, or importance across types. This means there is no
  "document significance" or "which result matters most" judgment anywhere in Search — a structural
  non-finding, but worth stating explicitly since the mission's own framing (§ document significance/
  ranking) implies this is exactly the kind of thing to check for.
- `nepotpuno` (line 281) is a data-quality signal (which per-type sub-search failed), not a decision.

**Verdict: confirmed independently — Search makes no business or legal decision of any kind. Nothing to
reconcile with any other module.**

---

## 2. Document classification — ALPHA-003 reframed under the Decision lens

**Prior art (ALPHA-003):** two independent AI taxonomies — `shared/intake_classify.py::classify()`
(English, 13 types incl. `other`) and `routers/evidence.py::_klasifikuj_dokument()` (Serbian, 9 types) —
both answer "what type of document is this," with Evidence's classifier running second and overwriting
the field as a patch, not a fix.

**New for Gamma — which one is the actual source of truth TODAY, in practice, and what specifically
breaks in the gap:**

Read `routers/smart_intake.py:660–735` and `shared/intake_worker.py:150–204` in full to trace the live
sequencing precisely (this had not been done at file:line granularity in the ALPHA-003 writeup itself).

1. **Synchronous first write:** `shared/intake_worker.py::IntakeWorker._process` (line 173) calls
   `intake_classify.classify()` and writes `document_type` (English vocabulary: `lawsuit`, `judgment`,
   etc.) via `intake_documents.create_document`. Separately, in the Smart Intake finalize flow,
   `routers/smart_intake.py:676` inserts `predmet_dokumenti` with `tip_dokaza: doc_type` — **this write is
   synchronous, inside the request path, and lands in the DB before either background task below starts.**
2. **Asynchronous second write, not guaranteed to ever land:** `routers/smart_intake.py:725–735`
   (`_evidence_classify_bg`) fires `routers/evidence.py::klasifikuj_i_sacuvaj` via **`asyncio.create_task`
   — fire-and-forget, not awaited, no retry-on-caller-side, failure only logged
   (`logger.warning("[SMART_INTAKE] Evidence Vault auto-klasifikacija greška...")`, line 733–734)**. Its own
   in-code comment (lines 702–720) states the reason this second write exists at all: the first write's
   vocabulary (`lawsuit`/`judgment`/...) **structurally can never match**
   `shared/constants.py::EXPECTED_DOCS`'s vocabulary (`sudska_odluka`/`podnesak`/...), which
   `services/risk_engine.py`'s missing-document detector reads directly.
3. **Consequence, stated precisely:** for any window between step 1's synchronous write and step 2's
   background task completing (a real GPT-4o-mini round trip, not instant) — or permanently, if step 2
   throws and is only logged — `predmet_dokumenti.tip_dokaza` holds a value from a vocabulary that
   `EXPECTED_DOCS`-based missing-document detection can never recognize. A document that IS a "sudska
   odluka" reads as `tip_dokaza="judgment"` during that window, which is invisible to
   `identify_case_problems`'s missing-doc check — a **false "this document type is still missing"** signal,
   not a false positive/negative on the classification itself, but on everything downstream that depends
   on the classification matching a known vocabulary.
4. **No confidence arbitration exists between the two writes.** `evidence.py::_klasifikuj_dokument` (routers/
   evidence.py:73–93) returns no confidence field at all — unlike `intake_classify.py`'s classifier, which
   does compute one (heuristic 0.85 fixed, or LLM self-reported). The second write is not "the more
   confident one wins" — it is unconditionally "whoever runs second wins, if it runs at all," confirmed by
   direct code read of the `UPDATE` at `routers/evidence.py:210–215`, which overwrites `tip_dokaza`
   unconditionally.

**Answer to the mission's specific question ("which one is the actual source of truth for the decision
today, in practice"):** Evidence's classifier (`routers/evidence.py::klasifikuj_i_sacuvaj`) is the
*intended* and *eventual* source of truth by design (its vocabulary is the one `EXPECTED_DOCS` and
`risk_engine.py` actually consume) — but it is **not structurally guaranteed to be the actual one at any
given read time**, because it runs as an unawaited background task with silent failure. Intake's classifier
is the *reliable* one (synchronous, always lands) but is *provably the wrong vocabulary* for every
downstream consumer that matches against `EXPECTED_DOCS`. **Neither classifier is a safe single answer to
"what type of document is this" on its own — the correct one only "wins" probabilistically, not
deterministically.** This is a sharper, evidence-backed version of ALPHA-003's own concurrency caveat
("nothing structurally guarantees that ordering holds"), now traced to the exact code paths and the exact
downstream consumer (`risk_engine.py`'s `EXPECTED_DOCS` match) that a wrong-window read corrupts.

**Note, not previously stated:** this "correct-vocabulary classifier as an unawaited fire-and-forget
background task with silently-swallowed failure" pattern means Evidence's classification is best modeled
as *eventually consistent, with no floor on how long "eventually" takes and no visible indicator to the
lawyer when it never completes* — a genuine gap distinct from ALPHA-003's "two taxonomies" framing, which
described the duplication but not this specific reliability shape of the fix that was layered on top of it.

**Severity: Critical-tier, consistent with ALPHA-003's own rating** — reframing doesn't change the
severity, it sharpens the mechanism. Same "why not fixed this mission" reasoning applies (real taxonomy/
migration decision, correctly deferred).

---

## 3. Firm institutional memory — ALPHA-005 reframed under the Decision lens

**Prior art (ALPHA-005):** `api.py::_fetch_firm_memory_context` (live, called from Copilot) vs.
`routers/firm_memory.py::kontekst_za_ai` (dead, zero callers, more complete — also reads `judge_patterns`
and `client_memory`).

**New for Gamma — does the dead version's completeness translate into an actual DIFFERENT decision, not
just "more context," and is that decision made anywhere else live:**

Read both functions in full (`api.py:1265–1372`, `routers/firm_memory.py:252–360+`).

1. **`api.py::_fetch_firm_memory_context` (live path) queries exactly two tables — `memory_entries` and
   `partner_profiles` (lines 1300–1320) — confirmed by direct re-read, no `judge_patterns` or
   `client_memory` reference anywhere in the function.**
2. **`routers/firm_memory.py::kontekst_za_ai`'s dead path additionally computes a concrete decision the
   live path cannot produce at all: a judge win-rate percentage.** Lines 314–318:
   `wr = round((jp.data.get("pobede", 0) or 0) / uk * 100)` → rendered as
   `f"Istorija: {wr}% win rate ({uk} predmeta)"` — a genuine "how favorable is this judge" assessment,
   backed by real recorded win/loss counts (`judge_patterns.pobede`/`porazi`), not an LLM guess.
   It also surfaces judge-specific procedural preferences (`insistira_na`/`odbija`, lines 311–314) and,
   for clients, a settlement-receptiveness/risk-profile decision (`client_memory.prihvata_nagodbu`,
   `rizik_profil`, lines 341–346) — e.g. "Klijent NIKAD ne prihvata nagodbu" / "Visokorizičan klijent."
   **None of these three decisions (judge favorability, judge procedural preference, client settlement
   posture) exist anywhere in the live `_fetch_firm_memory_context` path.**
3. **Confirmed via repo-wide grep: `judge_patterns` and `client_memory` are referenced in exactly 3 files
   total — `routers/firm_memory.py` (the dead function itself), and two audit/proof scripts
   (`routers/proof.py`, `scripts/proof_direct.py`) that are not runtime AI consumers.** No other module —
   including `routers/court_predictor.py`, which independently produces its own GPT-self-reported
   "confidence" percentage per Program Alpha's inventory item #5 — reads `judge_patterns` at all.

**Reframed finding, sharper than ALPHA-005's original "one dead, one live, dead is more complete":** this
is not simply two implementations of one decision where the wrong one is disconnected. **The specific
decision "how favorable is Judge X historically, based on real recorded outcomes" has a computed,
real-data implementation that is completely orphaned from every live decision consumer in the platform.**
Court Predictor's confidence — the platform's other "should we expect to win" signal — is a structurally
different, LLM-self-reported number (per Program Alpha's #4/#5, and independently re-confirmed here that it
never touches `judge_patterns`) with zero connection to this real win/loss data. **The gap isn't "two
authors disagreeing" (Program Alpha's framing) — it's "one real, evidence-backed answer to a decision the
platform asks elsewhere (via Court Predictor), sitting completely unused while the platform's actual live
answer to a related question is either absent (Copilot: no judge signal at all) or ungrounded (Court
Predictor: LLM guess, no real win/loss data)."** This is arguably a more urgent framing than ALPHA-005's
own, because it connects a Critical-tier Program Alpha finding to a Critical-tier Program Beta finding
(Court Predictor's confidence duplication, #4/#5 in the Alpha inventory, PROGBETA-adjacent) that neither
prior mission connected to each other.

**Severity: Critical-tier, consistent with ALPHA-005's own rating**, with an added cross-mission linkage
(Court Predictor confidence ↔ orphaned judge win-rate data) not previously documented anywhere in
`.vindex_ai_team/decisions/`.

---

## 4. `services/case_pipeline.py` — the 9-step decision audit (the mission's one unverified risk)

Full file read (751 lines). Each step assessed for (a) does it make a decision, (b) if so, does that
decision duplicate one made elsewhere in the platform.

| Step | Function | Makes a decision? | Duplicate elsewhere? |
|---|---|---|---|
| 1 | `_step_analiza_dokumenata` (159–193) | No — pure existence/marker check | N/A |
| 2 | `_step_auto_linking` (196–216) | No — pure existence check (see caveat below) | N/A |
| 3 | `_step_ekstrakcija_rokova` (219–328) | **Yes** — extracts dates AND classifies each one's `vaznost` (kritičan/bitan/normalan) via GPT | **Partial/unconfirmed — see 4.3** |
| 4 | `_step_kalendar` (331–348) | No — pure existence check | N/A |
| 5 | `_step_strategija` (351–415) | **Yes** — GPT case-outlook narrative (spor type, optimistic/neutral/pessimistic outlook, recommended strategy) | **Yes — confirmed, see 4.1** |
| 6 | `_step_hcc` (418–497) | **Yes** — GPT pre-hearing briefing (what to prepare) | **Yes — confirmed, see 4.2** |
| 7 | `_step_risk_snapshot` (500–566) | Yes, but **already fixed** — reads `services.risk_engine.calculate_procesni_rizik` exclusively (line 526, 542) | **No — confirmed clean, see 4.4** |
| 8 | `_step_copilot_preporuka` (569–625) | Yes, but **already fixed** — reads `services.risk_engine.identify_case_problems` exclusively (line 585, 611) | **No — confirmed clean, see 4.4** |
| 9 | `_step_istorija` (628–669) | No — pure logging/summary of steps 1–8's own results | N/A |

### 4.1 Step 5 (`_step_strategija`) — a 5th independent "case outlook" generator, not counted by Program Beta

Program Beta's own `AI_DECISION_GRAPH.md` (§ Strategy Engine, lines 65–78) names **4** independent
generators of "case outlook/success probability" inside `strategija.py`/`routers/strategija.py` (litigation
simulator, sudija-v2 ×2, v2/analiza, kompletna-analiza) as the mission's most serious finding
(PROGBETA-001). **`case_pipeline.py`'s step 5 is a 5th, structurally identical generator that neither
Program Alpha's nor Program Beta's inventory counted**, because both scoped their strategy-domain audit to
`strategija.py`/`routers/strategija.py` specifically, not to `case_pipeline.py`.

- **Confirmed independent:** `routers/strategija.py`'s 9 endpoints never write to `predmet_istorija` at
  all (grepped for `predmet_istorija` in that file — zero matches); they return results directly to the
  caller. `case_pipeline.py`'s step 5 writes its own narrative to `predmet_istorija` under tag
  `[Strategija Pipeline]` (line 405). No shared tag, no shared storage, no cross-reference between them —
  two fully disconnected write paths for conceptually the same judgment.
  Prompt (lines 378–386) asks the model for: vrsta spora, "Procena izgleda (optimistično / neutralno /
  pesimistično)", preporučena strategija (tužba/odbrana/nagodba), sledeći koraci — this is a qualitative
  version of exactly the "how good is this case" question the 4 counted generators answer quantitatively
  (win probability %).
- **Practical consequence:** `calculate_case_ready_score`'s own checklist item "Strategija generisana"
  (line 117–123: `has_strat = any("[Strategija" in (r.get("pitanje") or "") for r in istorija)`) is
  satisfied **solely** by this lite pipeline step for most cases, since it's the only one of the 5
  generators that auto-fires on case creation — meaning the Case Ready Score's "strategy done" checkbox is
  green based on the least rigorous of 5 independent strategy assessments in the platform, with no
  indication to the lawyer that this is a preliminary/lite pass, not the same thing as running the actual
  Strategy Engine.
- **Not yet independently observed:** whether a lawyer has ever seen this lite assessment and one of the
  4 heavier generators disagree in the same session (would require live usage data, out of scope for a
  read-only code audit) — flagged as the same class of risk Program Beta's own Phase 7 cross-module
  consistency table already names for the other 4, now provably a 5-way risk, not 4-way.

### 4.2 Step 6 (`_step_hcc`) — a cruder, auto-fired duplicate of the paid Hearing Command Center

This is a genuinely new finding, not present in either prior mission's inventory (grepped
`.vindex_ai_team/decisions/*.md` and `docs/architecture/*.md` for `hearing_cc`/`command-center`/`HCC` —
matched only unrelated sentinel/keystone files and UX docs, none analyzing this specific duplication).

- **`routers/hearing_cc.py`** (493 lines, read in full) is `POST /api/rociste/command-center` — the
  platform's real, deliberate "what does the lawyer need for this hearing" decision engine: **PRO-only, 3
  credits, `gpt-4o`**, case-type-specific system prompts (5 variants: `gradjanski`/`krivicni`/`upravni`/
  `privredni`/`radni`, lines 43–99), producing a 12-field structured brief including `executive_brief`,
  `win_lose_matrix`, `opposing_counsel` strategy, `judge_attack_mode`, `missing_evidence`,
  `cross_examination` questions, `hearing_checklist`, **and its own `hearing_score` + `risk_breakdown.overall`
  (NIZAK/SREDNJI/VISOK)** — i.e. yet another independent risk-level judgment alongside `risk_engine.py`'s
  `calculate_procesni_rizik`, Court Predictor's confidence, and Strategy Engine's percentages (lines
  103–116).
- **`case_pipeline.py`'s step 6, tagged `[HCC Pipeline]` (line 487) — the same "HCC" abbreviation** — is a
  free, automatic, `gpt-4o-mini`, single-prompt version of the same underlying question ("what should the
  lawyer prepare before this hearing," lines 460–464: "Vrati 3-5 konkretnih napomena šta advokat treba da
  uradi pre ročišta"). It fires automatically for any predmet with a hearing in the next 90 days (line
  426–439), with **no PRO gate, no credit charge, no cross-reference to `hearing_cc.py`, no shared prompt,
  no shared schema** — a structurally cruder, silently-auto-generated answer to the exact question the
  platform sells as a premium, deliberate action elsewhere.
- **Consequence:** a lawyer with an upcoming hearing may see a bare 3–5 line `[HCC Pipeline]` note in
  `predmet_istorija` from the free automatic pass and never realize a materially deeper, paid,
  case-type-aware 12-section brief (with its own risk assessment) exists one click away — or worse, could
  read the free lite version's advice as complete prep, when `hearing_cc.py`'s deeper analysis (teret
  dokazivanja, prekluzija, specific ZPP/ZKP/ZUP articles depending on case type) is the one actually
  designed to catch case-type-specific procedural traps the lite version's generic prompt has no way to
  surface.
- **This is structurally the same pathology as ALPHA-005** (a cruder auto/live path vs. a more capable
  path that exists but isn't reached automatically) — except here **both paths are reachable and both
  actually run**, just never reconciled or cross-labeled, which is arguably worse than ALPHA-005's dead-code
  case: a lawyer could genuinely receive two different, unlabeled answers to "am I ready for this hearing."

### 4.3 Step 3 (`_step_ekstrakcija_rokova`)'s `vaznost` classification — a different-kind, not confirmed-conflicting, voice on deadline criticality

Program Alpha's own deadline-domain inventory (item #13, `2026-08-04_alpha_domain_deadlines_tasks_alerts_
INVENTORY.md`, lines 13/41–55) found **≥6 independent inline copies of a day-count threshold** ("is this
deadline critical" = `days_until <= 3` or `<= 7`, two conflicting values) as a duplicate decision. Step 3's
`vaznost` field (kritičan/bitan/normalan, lines 293–295) is a **different kind of mechanism** — a one-time
GPT classification made at extraction time, stored on the row — not a dynamically re-evaluated
day-threshold check.

- Confirmed via grep: `predmet_hronologija.vaznost` is read by 16 files across the platform (`api.py`,
  `routers/copilot.py`, `routers/intelligence_timeline.py`, `routers/kalendar.py`, `routers/portfolio.py`,
  `routers/client_portal.py`, etc.) — a genuinely consumed, live field, not a write-only artifact.
- **What was not established in this fork, and should be flagged rather than asserted:** whether any of
  Alpha's 6 threshold-based "is this deadline critical" call sites re-derive their own criticality judgment
  from the *same* `predmet_hronologija` rows this step creates (which would mean the same deadline gets two
  independently-computed, potentially disagreeing criticality labels — a real duplicate), or whether the
  threshold-based checks operate on a structurally separate deadline source (e.g. `rokovi`/`rocista` tables
  via `rokovi_lanac.py`, which this fork's grep for that file's own threshold pattern returned no matches
  for, suggesting it may use a different mechanism entirely not yet located). **This is the one item in
  this fork's findings that needs a dedicated follow-up trace (which of the 16 `vaznost` readers actually
  cross-checks or overrides a GPT-assigned `vaznost` against a day-count rule) before it can be stated as a
  confirmed duplicate rather than a plausible one.**

### 4.4 Steps 7 & 8 — confirmed CLEAN, the domain's positive reference pattern

Both steps carry in-code comments explicitly documenting a prior fix: step 7's docstring (lines 502–510)
states it "used to run its own independent GPT-4o-mini call... producing a second, disconnected 'risk'
number" and now "reads it, it never computes its own," citing **Core Consolidation Sec 1.1 (2026-07-22)**.
Step 8's docstring (lines 572–582) states the same for its former independent "next action" GPT call,
citing **Core Consolidation Sec 1.2**. Direct code read confirms both claims: step 7 imports and calls only
`calculate_procesni_rizik` (line 526, 542); step 8 imports and calls only `identify_case_problems` (line
585, 611), and even its fallback-when-step7-was-skipped path (lines 590–609) recomputes via the *same*
`calculate_procesni_rizik` call, not an approximation. **This is the single cleanest example in this
fork's scope of a previously-duplicated decision being fully retired down to one canonical source, not
just deferred or documented — worth citing as the reference pattern for how ALPHA-003/ALPHA-005/§4.1/§4.2
above should eventually be resolved.**

### Minor observation, not a decision-fragmentation finding

Step 2's docstring claims "we also search klijenti for additional matches from predmet opis" (line 199),
but the implementation (lines 202–216) only queries existing `predmet_klijenti` rows — no search of `opis`
text against the `klijenti` table exists anywhere in the function. This is stale/aspirational documentation,
not a second implementation of a decision (there's only one implementation, and it does less than its own
comment claims) — noted for completeness, not counted in the findings above.

---

## Prioritized list

1. **[Critical, new for Gamma]** Step 6 `_step_hcc` vs. `routers/hearing_cc.py` — two unlabeled, unreconciled
   answers to "is this lawyer ready for the hearing," one free/auto/crude, one paid/deliberate/deep, no
   cross-reference. §4.2.
2. **[Critical, new for Gamma]** Step 5 `_step_strategija` — confirmed 5th independent "case outlook"
   generator, on top of Program Beta's already-flagged 4; the auto-fired one also happens to be the sole
   satisfier of the Case Ready Score's "Strategija generisana" checklist item. §4.1.
3. **[Critical, reframed]** ALPHA-005 sharpened: judge win-rate/procedural-preference/client-settlement-
   posture decisions exist, computed from real data, completely orphaned from every live AI consumer
   including Court Predictor — connects two previously separate Critical findings across missions. §3.
4. **[Critical, reframed]** ALPHA-003 sharpened: traced to the exact unawaited-background-task mechanism
   that makes the "correct" classifier's win probabilistic, not deterministic, and named the exact
   downstream consumer (`EXPECTED_DOCS` matching) a wrong-window read corrupts. §2.
5. **[Medium, unconfirmed — flagged for follow-up]** Step 3's GPT-assigned `vaznost` vs. Alpha's 6
   threshold-based deadline-criticality copies — plausible additional voice on the same underlying
   question, not confirmed to actually collide on the same rows. §4.3.
6. **[Clean — confirmed, no action needed]** `routers/search.py::global_search` — no decision-making of any
   kind. §1.
7. **[Clean — confirmed, cite as reference pattern]** `case_pipeline.py` steps 7 & 8 — fully consolidated
   onto `risk_engine.py`, the domain's best example of a duplicate decision retired down to one source.
   §4.4.

---

## Summary for parent

**Case Pipeline's 9 steps do duplicate canonical decisions found elsewhere — confirmed for 2 of 9, plausible
for a 3rd, clean for 2 of 9 (the other 4 make no decision at all):**

- **Step 5 (`_step_strategija`) is a 5th independent "case outlook/success" generator**, joining the 4
  Program Beta already found inside `strategija.py`/`routers/strategija.py` — fully disconnected (different
  storage, no shared tag), and it's the one that auto-satisfies the Case Ready Score's "strategy generated"
  checkbox for most cases, meaning the least rigorous of the 5 generators is the one silently marked "done."
- **Step 6 (`_step_hcc`) is a free, automatic, `gpt-4o-mini` shadow of `routers/hearing_cc.py`'s paid,
  deliberate, `gpt-4o`, case-type-specific Hearing Command Center** — both literally use "HCC" as their
  name, both answer "is the lawyer ready for this hearing," neither knows the other exists. This is new —
  neither Program Alpha's nor Program Beta's inventory mentions `hearing_cc.py` at all.
- **Steps 7 and 8 are confirmed CLEAN** — both were already fixed on 2026-07-22 (Core Consolidation Sec
  1.1/1.2) to read exclusively from `services/risk_engine.py`, replacing former independent GPT calls. This
  is the domain's best positive pattern: a duplicate fully retired, not just documented.
- **Step 3's deadline-importance classification is a plausible but unconfirmed 4th-or-later voice** on
  "how critical is this deadline," alongside Alpha's already-found 6 threshold-based copies — flagged for
  follow-up, not asserted as a confirmed collision, since this fork did not trace whether the same
  `predmet_hronologija` rows are re-evaluated by any of Alpha's 6 threshold sites.

**ALPHA-003 and ALPHA-005, reframed under the Decision-ownership lens, both got sharper, not just
relabeled:** ALPHA-003's "two taxonomies" is now traced to a specific unawaited-fire-and-forget-with-
silent-failure mechanism that makes the correct classifier's win probabilistic rather than guaranteed.
ALPHA-005's "dead vs. live" is now shown to be specifically about judge win-rate/preference and client
settlement-posture decisions with real data behind them, sitting unused while Court Predictor (a separate
Program Alpha/Beta finding) answers a related question with no real data at all — a cross-mission linkage
neither prior mission documented.

**`routers/search.py` is confirmed, independently, to make no decision of any kind** — clean, matches
Program Alpha's own inventory, nothing further to reconcile.

# Program Gamma — Domain Inventory: Risk / Task Priority / Dashboard / Alerts / Next-Action

**Mission:** Masterprompt 003, "Canonical Decision Engine — Eliminate Entire Classes of Decision
Fragmentation." Lens: is a BUSINESS OR LEGAL DECISION (procesni rizik, promena rizika, hitnost, prioritet,
eskalacija, sledeći korak, nedostajući dokument, procesno upozorenje) independently produced by more than
one module — broader than Program Alpha's structural-duplication lens and Program Beta's
confidence/hallucination lens. Read-only, no code/git changes. Every claim re-verified against current
code today, not cited from prior mission reports on faith.

**Scope:** `services/risk_engine.py`, `routers/zadaci.py`, `routers/dashboard.py`, `routers/ccc.py`,
`shared/proactive_alerts.py` + `routers/case_dna.py`'s alert-triggering logic, `routers/matter_intel.py`,
plus a platform-wide grep sweep for `rizik_score`/`health_score`/`hitnost`/`prioritet` to catch anything
the 3 previously-fixed duplicate instances might have missed, and a "next recommended action" ownership
check across Task Engine / Genome / Dashboard / Case Commander / Case Intelligence.

---

## 0. Regression check — the 3 previously-fixed duplicate-health-score instances

| Instance | Prior fix (mission) | Verified today |
|---|---|---|
| `routers/ccc.py` health_score | Project Nexus, 2026-08-03 | **STILL FIXED.** `ccc.py:14,135-140` imports and calls `calculate_procesni_rizik`, reads `_rizik["health_score"]` directly — no local formula. Comment at `ccc.py:121-131` explicitly documents the old bug and the fix. |
| `routers/dashboard.py::matter_health_score` | Project Sentinel, 2026-08-03 | **STILL FIXED.** `dashboard.py:383-406` imports `calculate_procesni_rizik, identify_case_problems` and returns `rizik["health_score"]` as `"score"` — no independent arithmetic. Comment at line 400 explicitly says "ne izmišljaju se novi pragovi nad health_score, isto kao ccc.py fix." |
| `routers/matter_intel.py` (original G-027 source of the bug) | risk_engine.py extraction, pre-Nexus | **STILL FIXED / canonical origin.** `risk_engine.py`'s own docstring (lines 1-16) states this logic was extracted 1:1 from `matter_intel.py`; matter_intel.py itself now calls the extracted function (confirmed via grep: `health_score`/`procesni_rizik` matches only reference the imported result, `ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN` event emission at the documented lines). |

**Verdict: no regression.** All 3 previously-fixed instances are confirmed still delegating 100% to
`services/risk_engine.py`. `services/case_pipeline.py:551` (`rizik["nedostajuci_dokazi"]`) and
`services/confidence_calibrator.py:184` also confirmed as pure consumers of the same canonical dict, not
independent computers.

A platform-wide grep for `health_score|rizik_score|procesni_rizik` across `routers/` and `services/`
turned up exactly 3 files with real "case risk" logic (`zadaci.py`, `dashboard.py`, `ccc.py`, plus
`matter_intel.py` and `case_pipeline.py`/`event_bus.py` as pure consumers) — no undiscovered rogue
formula for **case procedural risk** exists.

**Adjacent, confirmed-different domain (not a duplicate under Gamma's definition):** `routers/web3.py`'s
`rizik_score` (AML/crypto-transaction risk, 1-10 scale, raw GPT, e.g. `web3.py:71,300,348,381,391,411,466`)
and `web3_compliance.documentation_health_score_sync` (F11.7, shared canonically between
`routers/strategy_simulator.py:42` and `routers/source_of_funds.py:30`) answer a genuinely different
business question — "is this crypto transaction/documentation AML-compliant" — not "is this legal case
procedurally at risk." They share a name pattern with `risk_engine.py`'s concepts but are architecturally
and semantically unrelated (per project memory: Web3 module = Digital Asset Compliance & Due Diligence,
deliberately scoped away from case/portfolio risk). Flagged here only so a future auditor doesn't
re-discover the name collision and assume it's the same finding.

---

## 1. NEW — case_intelligence.py's alert query uses columns that do not exist (Critical, live, unfixed)

**`routers/case_intelligence.py:120-129`**, inside `_gather_case_data()`:

```python
asyncio.to_thread(
    lambda: supa.table("proactive_alerts")
    .select("tekst_alerta, tip_alerta, hitnost")
    .eq("user_id", user_id)
    .eq("predmet_id", predmet_id)
    .eq("procitana", False)
    .order("created_at", desc=True)
    .limit(5)
    .execute()
),
```

The real `proactive_alerts` schema (`migrations/036_decision_log.sql:40-51`) has columns
`id, user_id, predmet_id, tip, naslov, opis, urgentnost, procitana, created_at`. There is **no**
`tekst_alerta`, `tip_alerta`, or `hitnost` column — the correct names are `tip`/`naslov`+`opis`/`urgentnost`.

This is the **exact same mistake**, on the **exact same table**, that `routers/case_dna.py`'s own comment
(lines 758-765) documents as having been found and fixed on 2026-07-18 ("Reality Validation" pass) —
`case_dna.py` used to insert with `tekst_alerta`/`tip_alerta`/`hitnost` and silently failed on every call
(`PGRST204`) until caught. `case_intelligence.py` has the identical wrong-column mistake, in a `.select()`
instead of an `.insert()`, **still present today, in a different file, never caught by that same audit
pass** (its own comment doesn't reference this file, and this file isn't in `risk_engine.py`'s or
`proactive_alerts.py`'s consumer lists).

**Why this matters for Gamma specifically:** the `asyncio.gather(...)` call at `case_intelligence.py:85-138`
has **no `return_exceptions=True`**. A Postgres/PostgREST "column does not exist" error on the alerts
query will propagate up through `_gather_case_data()` uncaught by anything inside it, and land in the
broad `except Exception as e: ... raise HTTPException(500, ...)` at `case_intelligence.py:380-383`. In
other words: **every call to `POST /predmeti/{predmet_id}/briefing` — the endpoint that decides
`sledeci_korak` (next recommended action) and `hitnost` (urgency) for a case — is very likely returning
500 on every invocation right now**, not degraded output, a hard failure.

**Severity escalation vs. a purely cosmetic bug:** Mission `IF-002` (`.vindex_ai_team/decisions/2026-08-03_IF-002_case_intelligence_briefing_MISSION_REVIEW.md`)
wired this exact endpoint to a new "AI Briefing — sledeći korak" button in the case-detail UI on
2026-08-03, explicitly noting "No backend code changed" for that mission (it was a frontend-only wiring
task, so it never exercised or audited this query). That means a previously-unreachable, previously-broken
backend feature was just made reachable from the UI without anyone re-verifying its DB calls — the
regression-check discipline that caught this exact bug class in `case_dna.py` was not re-applied here
because it looked like "just a button."

**Recommended fix (not performed — read-only mission):** correct the `.select()` to
`"tip, naslov, opis, urgentnost"` (or reuse a shared alert-fetch helper if one gets created), and add
`return_exceptions=True` to the `asyncio.gather()` so one failing sub-query degrades that one section of
the briefing instead of hard-failing the whole "next recommended action" endpoint — matching the fail-soft
pattern `case_commander.py`'s own comment (line 561-567) already applies for its cross-case GPT call.

---

## 2. NEW — "sledeći preporučeni korak" (next recommended action) has at least 5 independent, unreconciled owners

`services/risk_engine.py::identify_case_problems`'s own docstring calls itself "jedini deterministicki
izvor 'sledece akcije' u celoj platformi" (Core Consolidation Sec 1.2, 2026-07-22) and claims to have
replaced three prior independent generators. **That claim is true for the specific systems it names**
(Cockpit, Matter Intel's old rule-based version, Case Ready Score) and for its actual current consumer set
(`api.py`, `ccc.py`, `dashboard.py`, `matter_intel.py`, `zadaci.py`, `case_pipeline.py` — all confirmed
delegating in §0). **It is not true platform-wide.** Confirmed today, at least 4 more surfaces
independently generate "what should the lawyer do next" / "what's missing" / "how urgent is this" content
for the same case, none of which read `identify_case_problems`'s output or defer to it:

| Surface | Location | What it independently decides | Vocabulary used |
|---|---|---|---|
| **Case Genome `strategija`/`najslabija_tacka.preporuka`/`nedostaje`** | `routers/case_dna.py`'s `_extract_genome` prompt, schema at lines 105-121 | `strategija.primarni_cilj`/`rezervni_plan`/`scenariji` (what to do), `najslabija_tacka.preporuka` (what fixes the weak point), `nedostaje` (missing documents) | `nedostaje[].hitnost`: `kriticno\|vazno\|pozeljno` |
| **Strategy Engine V2** | `routers/strategija.py::strategija_v2_analiza`, schema at lines 353-365 | `nedostajuci_dokazi` (missing evidence), `sledeci_koraci` (next steps) | `nedostajuci_dokazi[].vaznost`: `kritican\|bitan\|korisno`; `sledeci_koraci[].prioritet`: `hitan\|normalan\|opciono` |
| **Case Commander cross-case briefing** | `routers/case_commander.py::_cross_case_analiza`, prompt at lines 528-554 | Which **single case**, across the whole portfolio, should be today's priority (`"PRIORITET — koji JEDAN predmet treba da bude prioritet danas i zašto"`) | free text `razlog`, no numeric/enum urgency field |
| **Case Intelligence Briefing** | `routers/case_intelligence.py`'s `_BRIEFING_SYSTEM` prompt, lines 52-78 (currently broken, see §1) | `sledeci_korak` ("JEDNA najhitnija konkretna akcija") + `razlog` + `hitnost` | `hitnost`: `odmah\|ovu_nedelju\|ovaj_mesec` |

None of these four call sites read `risk_engine.py::identify_case_problems`'s output, and
`identify_case_problems`'s consumers don't read these either. `shared/genome_validator.py`'s
`_validate_snaga_konzistentnost` (line 229) — the one existing cross-check in this area — only compares
Genome's `snaga_predmeta_procent` against its own `dokazi_rang` stars; it does **not** check Genome's
`nedostaje` against `risk_engine`'s `nedostajuci_dokazi`/`ozbiljnost` for the same case, so the two "what
documents are missing" answers for one predmet can silently disagree with no detection mechanism.

**Confirmed live consumption, not just display:** `routers/cio.py:148` —
`ned_kriticno = sum(1 for n in (genome.get("nedostaje") or []) if n.get("hitnost") == "kriticno")` —
aggregates Genome's raw-GPT `nedostaje.hitnost` field into the portfolio-wide CIO daily count. This is not
a cosmetic UI-only field; it's fed into another module's own aggregate number, with no grounding check
that the GPT-generated `nedostaje` list agrees with the deterministic `EXPECTED_DOCS`-based
`nedostajuci_dokazi` risk_engine already computes for the same case.

**Relationship to prior tracked findings:** `AI_DECISION_GRAPH.md`'s Phase 7 table and
`BUSINESS_LOGIC_INVENTORY.md`'s decision #6/PROGBETA-001 already track Strategy Engine's "4 nezavisna
generatora" for **procena uspeha (success percentage)** as the domain's most serious open item. This
finding does not re-litigate that — it establishes that the **same 4-generator fragmentation extends
beyond the percentage** to `nedostajuci_dokazi` and `sledeci_koraci/prioritet` (both present in the same
V2 JSON schema, `strategija.py:361,363`), and that it has company: Genome and Case Commander/Case
Intelligence are two more independent "what's missing"/"what's next" narrators that were not previously
named as part of this specific fragmentation pattern (they were reviewed for confidence/grounding by
Program Beta, not for decision-ownership by Program Gamma's broader definition).

**Positive counter-example, still holding:** `routers/zadaci.py::ai_analiziraj_predmet` remains the one
surface that correctly treats `identify_case_problems` as upstream fact (`zadaci.py:615-622,634-636`,
confirmed unchanged from Program Beta's fork). One softening worth naming precisely: in the **primary
(LLM-success) path**, the model still freely chooses each generated task's `prioritet` field
(`zadaci.py:717`, `z.get("prioritet", "normalan")`, only enum-validated, not derived from
`p["ozbiljnost"]`) — only the **fallback path** (`zadaci.py:696-701`, GPT failure) hard-maps
`"visoko" if p["ozbiljnost"] == "kritican" else "normalan"`. So a task generated from a `kritican`
deterministic finding is not code-guaranteed to get `hitno`/`visoko` priority in the common path — the
prompt asks for it but nothing enforces it. Lower severity than the four-surface fragmentation above
(single call site, soft guardrail only, not a second independent computation), but a real gap in the
"exactly one algorithm decides urgency" principle this mission is chartered to find.

---

## 3. NEW — case_dna.py computes the same alert-urgency formula independently twice, inline (Low)

`routers/case_dna.py:757` and `routers/case_dna.py:916` both contain the **identical, literal** line:

```python
hitnost = "hitna" if snaga_d >= 15 or delta_obj.get("kontr_nove", 0) > 1 else "normalna"
```

— one inside the auto-refresh code path (`_extract_genome` → auto trigger), one inside the manual-refresh
endpoint. Not extracted into a shared helper (e.g. `_delta_hitnost(delta_obj)`), despite `_delta_alert_text`
and `_delta_significant` already existing as shared helpers for the adjacent concerns (alert text, "is this
delta worth alerting on at all") right above it in the same file. Values cannot currently diverge (byte-
identical code), so this is not a live bug — but it is precisely the anti-pattern Gamma is chartered to
name: the urgency **decision** for this alert type has two independent authors in the same file, one edit
away from silently diverging (e.g. someone tuning the manual-refresh threshold without noticing the
auto-refresh copy).

**Recommended fix (not performed):** extract to a one-line shared function next to `_delta_significant`.

---

## 4. Summary for parent

**Regression check: PASS.** All 3 previously-fixed duplicate-health-score instances (`ccc.py`,
`dashboard.py`, `matter_intel.py`) are confirmed still delegating 100% to
`services/risk_engine.py::calculate_procesni_rizik`/`identify_case_problems` — no regression, no new rogue
formula found anywhere in a platform-wide `routers/`+`services/` sweep for case procedural risk. The
Web3/AML `rizik_score`/`documentation_health_score` surfaces are a confirmed-different business domain,
not a duplicate under this mission's definition.

**New findings, this pass:**
1. **Critical, live, previously undetected**: `routers/case_intelligence.py:120-129`'s alert query selects
   nonexistent columns (`tekst_alerta`/`tip_alerta`/`hitnost` vs. real schema
   `tip`/`naslov`/`opis`/`urgentnost`, `migrations/036_decision_log.sql:40-51`) — the exact bug class
   already found-and-fixed in `case_dna.py` on 2026-07-18, unfixed here, and now reachable from the UI
   since Mission IF-002 (2026-08-03) wired an "AI Briefing" button to this exact endpoint without
   re-auditing its DB calls. No `return_exceptions=True` on the enclosing `asyncio.gather` means this
   almost certainly 500s the entire "next recommended action" endpoint on every call today.
2. **Medium-High, direct hit on the mission's "next recommended action" question**: no single owner exists
   for "what should the lawyer do next"/"what's missing." At least 5 independent generators found: Task
   Engine (correctly deferential, confirmed clean, one soft priority-enforcement gap), Case Genome's
   `strategija`/`nedostaje` (raw GPT, own `hitnost` vocabulary, consumed further by `cio.py`), Strategy
   Engine V2's `nedostajuci_dokazi`/`sledeci_koraci` (extends the already-tracked PROGBETA-001
   fragmentation beyond just the success percentage), Case Commander's cross-case `PRIORITET` (which of
   ALL cases to work today), and Case Intelligence's per-case `sledeci_korak`/`hitnost` (currently broken,
   see #1). No cross-check exists between any of them for the same predmet.
3. **Low**: `case_dna.py` computes its alert-urgency threshold formula independently twice, inline,
   byte-identical, at lines 757 and 916 — not yet divergent, but unextracted and one edit away from being
   so.

**Single highest-priority item for Program Gamma's synthesis phase**: finding #1 is not a decision-
fragmentation finding in the classic sense (nobody else computes a competing answer) — it is a broken
single source that likely makes one of the "next recommended action" surfaces fail outright, which is
arguably worse for a mission about decision integrity than a duplicate would be, since it means a lawyer
clicking "AI Briefing" gets a 500 error, not even a wrong-but-present answer. Recommend founder/Phase-5
synthesis treat it as a P0 live-bug ticket independent of the broader canonicalization design work implied
by finding #2.

# Program Gamma — Domain Inventory: Copilot / Briefing / Drafting (Decision-Fragmentation Lens)

Read-only investigation. No code/git changes made. All claims verified against current code.

**Lens, distinct from Program Alpha (structural duplication) and Program Beta (AI-reasoning defects,
same file scope, `2026-08-04_beta_domain_copilot_briefing_drafting_INVENTORY.md`):** does more than one
module independently produce the SAME business/legal decision — a preporuka, a next-step, a
readiness/quality verdict, an urgency classification, a status — for the same predmet, with no shared
vocabulary and no cross-check? Prior art read in full before writing this: `AI_DECISION_GRAPH.md`,
`EVIDENCE_CHAIN_REGISTRY.md`, `HALLUCINATION_ELIMINATION_REPORT.md`, `CONFIDENCE_MODEL_SPECIFICATION.md`,
`ARCHITECTURAL_DEBT_REGISTER.md` (PROGBETA-003/005), `DUPLICATE_DECISION_REPORT.md`, and
`G030_NEXT_ACTION_DECISION_MODEL.md` — G-030 (2026-07-22) already found 3 competing "next action"
authorities (Cockpit, Matter Intel, Case Ready Score) and left the decision unresolved, un-implemented.
This fork's job was to extend that from the NEW lens, in this fork's specific file scope, not repeat it.

**Headline result: G-030's "three competing authorities" framing is now stale and undercounts the real
fragmentation.** Within this fork's scope alone (Copilot + `ask_agent` + Drafting/`quality_gate`) there
are **3 additional, independent "next action" generators** G-030 never saw (it predates Copilot's PLAN/
PREDLOZI intents and never opened `main.py::ask_agent`'s prompt body), bringing the platform total to at
least 7. There is also a literal **same-named-field collision** (`nedostaje`) between Genome and Copilot's
PLAN intent with incompatible value vocabularies, and **6 independently-defined 3-value urgency
taxonomies** for what is conceptually one "how urgent is this" decision, found in this scope alone.

---

## Decision inventory — who decides what, in this fork's scope

| Decision type | Producer | Mechanism | Vocabulary | Persisted? | Cross-checked against anything? |
|---|---|---|---|---|---|
| "Next recommended action" (case-scoped) | `main.py::ask_agent`'s `brza_procena_koraci` (via Copilot PRAVNO_PITANJE) | Pure GPT-4o/mini, prompt-only | `prioritet`: kritično\|važno\|korisno | No — conversational, ephemeral | No |
| "Next recommended action" (case-scoped) | `routers/copilot.py::_handle_plan_predmeta` (PLAN intent) | Pure GPT-4o-mini, temp=0.1, JSON schema | `koraci[].prioritet`: hitan\|normalan\|odložen | No — returned to chat only | No |
| "Next recommended action" (case + firm-scoped) | `routers/copilot.py::_handle_predlozi` (PREDLOZI intent) | Deterministic, bespoke SQL reads (hronologija/dokumenti/beleske) | `predlozi[].prioritet`: hitan\|normalan\|info | No | No — does not call `risk_engine.py`/`identify_case_problems` at all |
| "Next recommended action" | `routers/zadaci.py::ai_analiziraj_predmet` | Deterministic `identify_case_problems()` pre-computed, injected into prompt | `prioritet` (code-constrained) | Yes — `zadaci` table | Shares root with Dashboard health score (good — see Beta's AI_DECISION_GRAPH note) |
| "Next recommended action" | Cockpit `prioritet` (G-029, pre-existing) | Fully GPT-decided | own | Yes | No (G-030) |
| "Next recommended action" | Matter Intel | Deterministic, reuses `risk_engine.py` | own | Yes | No (G-030) |
| "Next recommended action" | Case Ready Score `copilot_preporuka` | Own separate GPT risk assessment | own | Manually triggered | No (G-030) |
| "What's missing" (documents/evidence) | Genome `nedostaje` (`routers/case_dna.py`) | GPT extraction, case-document-grounded | `hitnost`: kritično\|važno\|poželjno | Yes — `case_dna` JSONB | No |
| "What's missing" (broader items) | Copilot PLAN `nedostaje` (`routers/copilot.py::_handle_plan_predmeta`) | GPT-4o-mini, free JSON | `hitnost`: visoka\|srednja\|niska | No | No — **same field name as Genome's, different vocabulary, zero awareness of each other** |
| Deadline/event urgency (write to system-of-record) | Copilot `_handle_akcija_rok` (`vaznost`) | GPT extraction (undifferentiated fact+inference, PROGBETA-005) | kritičan\|bitan\|normalan | Yes — `predmet_hronologija` | No |
| Deadline "hitan" flag | Copilot PREDLOZI (`_handle_predlozi`) | Hardcoded `today + timedelta(days=2)` | hitan / normalan (binary) | No | No — 4th distinct threshold value alongside ALPHA-007's 3-day/7-day/30-day findings |
| "Is this document ready to use" | Drafting `quality_gate.confidence_score` | Deterministic `0.6*citation+0.4*completeness` | float 0.00–1.00, gate at 0.85 | Yes — `staging_memory` | No |
| "Is this document ready to use" | Strategy Engine Pravni Revizor `ocena` | Pure GPT-4o, temp=0.15, prompt-only, zero RAG | SPREMAN ZA UPOTREBU \| POTREBNE IZMENE \| NEUPOTREBLJIV | No — returned to chat only | No |
| Case strategy / recommended approach | Genome `strategija.primarni_cilj`/`rezervni_plan` | GPT extraction from case documents | free text | Yes — `case_dna` JSONB | No |
| Case strategy / recommended approach (per-question) | `ask_agent`'s "PRAVNI ZAKLJUČAK" + `brza_procena_koraci` | GPT, RAG-law-grounded, NOT case-document-grounded | free text | No | No |

---

## Finding 1 — `nedostaje` field-name collision, Genome vs. Copilot PLAN, incompatible vocabularies (HIGH)

`routers/case_dna.py:119-121` (Genome's extraction schema):
```json
"nedostaje": [
  {"dokument": "...", "hitnost": "kriticno|vazno|pozeljno", "opis": "..."}
]
```
`routers/case_dna.py:141`: *"nedostaje: samo ono sto ZAISTA nedostaje za dokazivanje."*

`routers/copilot.py:475` (`_handle_plan_predmeta`'s `_PLAN_SYSTEM` prompt, PLAN intent):
```json
"nedostaje": [{"stavka": str, "hitnost": "visoka|srednja|niska"}]
```

Both fields answer the same underlying legal question — "what is missing from this case that I need to
go get" — for the same predmet, both written by independent GPT-4o(-mini) calls, both use the identifier
`nedostaje` and both use a sub-key literally named `hitnost`, and yet the two enums do not overlap at all
(`kritično/važno/poželjno` vs. `visoka/srednja/niska`). Neither call site imports from, reads, or checks
against the other. A lawyer who opens Genome's tab and then asks Copilot "šta mi nedostaje?" (routing to
PLAN) for the same predmet can get two different-shaped, non-reconcilable "nedostaje" lists in the same
session, with no code anywhere that would notice the disagreement, let alone reconcile it. This is the
single cleanest instance of "two independently-prompted GPT calls producing the same named decision" found
in this fork — sharper than a conceptual overlap because the field name itself collides.

**Why this matters more than a generic duplicate**: unlike Court Predictor's `procenat` (Program Alpha),
where a human reading the code would immediately recognize two implementations of "the same idea," here
the *field name identity* creates a false impression of a single canonical vocabulary if anyone (a future
engineer, a frontend component, an export/API consumer) ever merges or displays both without checking —
the schemas will silently type-mismatch or silently discard one, and neither prompt's docstring
acknowledges the other exists.

## Finding 2 — "Next recommended action" has no single owner; G-030 undercounted (HIGH, extends G-030)

G-030 (`docs/architecture/G030_NEXT_ACTION_DECISION_MODEL.md`, 2026-07-22) documented exactly 3 competing
authorities (Cockpit, Matter Intel, Case Ready Score) and left the decision unresolved. This fork's file
scope alone adds 3 more that G-030 never examined (it predates Copilot's PLAN/PREDLOZI intents in their
current form and never opened `ask_agent`'s prompt body):

1. `main.py::ask_agent`'s `brza_procena_koraci` (`main.py:1459-1461`, `main.py:1538`) — "STRATEŠKA
   PREPORUKA — 1-3 koraka PO PRIORITETU," reachable case-scoped via Copilot's PRAVNO_PITANJE intent
   (see Finding 3 below for why this is case-scoped despite a code comment claiming otherwise).
2. `routers/copilot.py::_handle_plan_predmeta` (PLAN intent, `routers/copilot.py:425-524`) — a full
   agentic action plan (`faze`/`koraci` with `prioritet`), pure GPT-4o-mini, no deterministic layer,
   does not call `risk_engine.py` or `identify_case_problems` (Task Engine's own canonical source).
3. `routers/copilot.py::_handle_predlozi` (PREDLOZI intent, `routers/copilot.py:753-892`) — deterministic
   but its own bespoke logic, independently reading `predmet_hronologija`/`predmet_dokumenti`/
   `predmet_beleske` directly rather than routing through `risk_engine.py::identify_case_problems`
   (which Task Engine and Dashboard both correctly share, per Beta's `AI_DECISION_GRAPH.md` Phase 7 table).

**Total confirmed independent "next action" producers platform-wide: at least 7** (G-030's 3 + Task
Engine + these 3). Of the 7, only Task Engine and Matter Intel are deterministic and share a common root
(`risk_engine.py`); the other 5 are either pure-GPT or independently-coded deterministic logic with no
shared source of truth. None of the 7 cross-check any other. A lawyer could plausibly see, in a single
session, four different "what do I do next" outputs for the same predmet (Cockpit's card, a Copilot PLAN
answer, a Copilot PREDLOZI answer, and a Task Engine-generated task) that agree by coincidence more often
than by design.

**This is not a re-statement of G-030** — G-030's own document explicitly scoped itself to "discovery
complete" for the 3 authorities it found and asked for a founder decision; this finding is new evidence
that widens the scope of that same undecided question, discovered specifically because Program Gamma's
mandate was to open `ask_agent`'s prompt body and Copilot's non-`PRAVNO_PITANJE` intents, which neither
G-030 nor Program Beta's sibling fork did (Beta's fork inventoried `ask_agent`/akcija-handlers/Briefing/
Drafting only for AI-reasoning-defect purposes — grounding/confidence/hallucination — not for
decision-ownership purposes).

## Finding 3 — `ask_agent`'s recommendation is case-scoped in fact, case-agnostic in the audit trail (MEDIUM)

`routers/copilot.py:210-224` (`_handle_pravno_pitanje`):
```python
q = f"{predmet_ctx}\n\n{poruka}".strip() if predmet_ctx else poruka
# ... "ask_agent was ... re-verified this mission as a single flat function,
# no case scope by design (matches Strategy Engine's own precedent of calling
# case_context() with predmet_id=None)"
with _ai_case_ctx(module_name="ask_agent", operation_name="pravno_pitanje"):
    rezultat = await asyncio.to_thread(_ask, q, history or None)
```
`predmet_ctx` is populated by `_load_predmet_context` (`routers/copilot.py:190-207`) with the predmet's
`naziv`/`opis`/`tip`/`status` and prepended to the actual question text sent to `ask_agent`. The GPT-visible
prompt is therefore genuinely case-specific whenever `predmet_id` is present on the Copilot request — and
`ask_agent`'s own prompt format explicitly produces a `brza_procena_koraci` "STRATEŠKA PREPORUKA" tailored
to "OVAJ slučaj, ne generički" (`main.py:1450`). But the `case_context()` call one line above passes no
`predmet_id` at all, on the stated rationale that `ask_agent` has "no case scope by design." **That
rationale is true only for the audit/provenance parameter, not for the actual decision being made** — the
comment conflates "the function signature has no predmet_id parameter" with "the output is not
case-specific," which is false the moment `predmet_ctx` is non-empty. Consequence: any future audit-log
reconstruction of "what recommendations has the AI made about predmet X" (exactly the kind of query
Program Beta's PROGBETA-002/Evidence Chain work is building toward) will silently miss every
`ask_agent`-sourced recommendation made through Copilot for that predmet, because it was never tagged with
the predmet_id it was actually about.

**Distinct from PROGBETA-002** (RAG provenance threading) — that finding is about `retrieval_query`/
`retrieved_context_ids` not being populated; this finding is about `predmet_id` itself, a coarser and more
consequential gap for this specific call site, not previously documented.

## Finding 4 — Drafting `quality_gate` vs. Strategy Engine Pravni Revizor: two "is this ready" verdicts, no shared vocabulary (MEDIUM-HIGH)

`services/quality_gate.py::evaluate_draft_quality` — deterministic `confidence_score` (0.00–1.00,
`0.6*citation_score + 0.4*completeness_score`), gates auto-promotion to Pinecone at `>= 0.85`
(`routers/drafting.py:247,1055`). Runs automatically on every Drafting-generated nacrt.

`routers/strategija.py:205-227` (`POST /strategija/revizor` → `pravni_revizor_sync`,
`routers/strategija.py:294`) — pure GPT-4o, temp=0.15, **zero RAG call, zero backend verification**
(confirmed by Beta's own sibling fork, `2026-08-04_beta_domain_legal_reasoning_strategy_INVENTORY.md:15`),
takes **any** pasted document text ≥100 chars and returns a qualitative `ocena`: `SPREMAN ZA UPOTREBU |
POTREBNE IZMENE | NEUPOTREBLJIV` (`routers/strategija.py:294,477`).

Both endpoints answer the identical underlying question — "is this legal document ready to use" — for
what can be the exact same text: nothing in either code path restricts Pravni Revizor's input to
non-AI-generated documents, and nothing in Drafting's flow prevents a lawyer from copying a
just-generated nacrt (visible in the staging review UI, `static/vindex.js:21369-21404`, which shows
`confidence_score` as a percentage) and pasting it into Pravni Revizor's free-text field
(`index.html:3088`, a separate "Strategija" tab). There is **no code link between the two features** —
confirmed by searching `static/vindex.js` for cross-references (none found) — so this is a real,
user-reachable path, not a hypothetical. The two verdicts use structurally incompatible representations
(a calibrated float with a named approval threshold vs. an ungrounded 3-value GPT self-report) and could
disagree on the identical text with nothing in the product surfacing that disagreement, or even that two
separate "readiness" opinions exist. This directly confirms the question this fork was chartered to check:
**yes, these are the same underlying decision via 2 completely separate mechanisms with no shared
vocabulary.**

## Finding 5 — Six independently-defined 3-value urgency taxonomies for one concept, in this scope alone (MEDIUM, extends ALPHA-007's spirit to the "hitnost" decision rather than pure numeric thresholds)

For the single decision "how urgent/critical is this," this fork's scope contains six unreconciled
enumerations:

| Vocabulary | Source | File:line |
|---|---|---|
| `kritičan \| bitan \| normalan` | Copilot `_handle_akcija_rok`'s `vaznost`, written to `predmet_hronologija` | `routers/copilot.py` (akcija handlers, PROGBETA-005) |
| `kriticno \| vazno \| pozeljno` | Genome `nedostaje[].hitnost` | `routers/case_dna.py:120` |
| `visoka \| srednja \| niska` | Copilot PLAN `nedostaje[].hitnost` | `routers/copilot.py:475` |
| `hitan \| normalan \| odložen` | Copilot PLAN `koraci[].prioritet` | `routers/copilot.py:473` |
| `hitan \| normalan \| info` | Copilot PREDLOZI `predlozi[].prioritet` | `routers/copilot.py:799,872,889` (+ its own hardcoded 2-day threshold, distinct from ALPHA-007's cataloged 3/7/30-day values) |
| `kritično \| važno \| korisno` | `ask_agent`'s `brza_procena_koraci[].prioritet` | `main.py:1460,1538` |

No shared enum, no mapping table, no single "urgency" type anywhere in this scope. This is the concrete,
enumerable form of the "hitnost zadatka" decision type named in this mission's charter — not a hypothesis,
a direct count from the actual prompt/schema text of 6 independently-authored vocabularies for the same
concept, all reachable for the same predmet within a few clicks of each other in Copilot alone.

## Relationship check — `zadaci.py::ai_analiziraj_predmet` to Copilot/Briefing (as scoped: relationship only, not full audit)

`routers/zadaci.py:622` calls `identify_case_problems(_rizik, tip_predmeta)` — **the same deterministic
function Dashboard's health score uses** (confirmed already in Beta's `AI_DECISION_GRAPH.md` Phase 7
table: "Task Engine task-prioritet vs. Dashboard health score | Ne — obe koriste isti
identify_case_problems | Zajednički koren"). Task Engine does **not** share anything with Copilot's PLAN
or PREDLOZI intents, nor with `ask_agent`'s `brza_procena_koraci` — three independently-computed
"next action" surfaces exist immediately adjacent to Task Engine's well-grounded one, none of which import
`identify_case_problems` or any Task Engine output. Task Engine remains, as Beta's fork already found, "a
positive reference pattern" — but it is an isolated positive pattern, not a canonical one other next-action
producers route through.

---

## Prioritized list

1. **Finding 2 — no single "next recommended action" owner, 7 confirmed independent producers** (Critical
   for product-identity reasons, per G-030's own framing: "dashboard with several AI opinions" vs. "one
   command center"). Not new in kind (G-030 already flagged this as unresolved) but materially escalated
   in scope — this fork found the count is more than double what G-030's document currently states.
   Recommend: re-open G-030 with the updated 7-producer count before any further Copilot intent work adds
   an 8th.
2. **Finding 1 — `nedostaje` field-name collision, Genome vs. Copilot PLAN** (High). Narrow, mechanical
   fix in principle (rename one field or share one enum) but requires a vocabulary decision, not a blind
   rename — same discipline Program Alpha applied to ALPHA-003's taxonomy question.
3. **Finding 4 — Drafting quality_gate vs. Pravni Revizor, no shared "readiness" vocabulary** (Medium-High).
   Confirms this fork's chartered question directly. A systemic fix in the shape PROGBETA-003 already
   recommends (extend `quality_gate`'s citation-verification machinery to Strategy Engine) would only
   solve the citation half — the categorical-vs-numeric readiness-verdict mismatch is a separate, still
   undesigned problem.
4. **Finding 5 — 6 unreconciled urgency vocabularies** (Medium). Same root cause pattern as
   `DUPLICATE_DECISION_REPORT.md`'s Pattern A ("no enforced convention catches this at write time"),
   applied to a decision's *vocabulary* rather than to a numeric threshold or a function body.
5. **Finding 3 — `ask_agent` recommendation mislabeled case-agnostic in audit trail** (Medium). Narrower
   than PROGBETA-002 but a real, previously-undocumented gap in exactly the provenance chain Program Beta
   is building toward completing.

## Summary for parent

**Decision-fragmentation instances found in this fork's scope: 5 distinct findings**, plus a relationship
check on Task Engine confirming it stays outside the fragmentation (shares Dashboard's deterministic root,
does not participate in Copilot's or `ask_agent`'s parallel next-action generation).

**Most severe: Finding 2** — "next recommended action" does **not** have a single owner anywhere in the
platform. G-030 (2026-07-22) already flagged this as an open, founder-blocked product-identity decision
with 3 known competing authorities; this fork found **3 more** independent producers inside Copilot/
`ask_agent` alone that G-030's original discovery pass never examined (`ask_agent`'s `brza_procena_koraci`,
Copilot's PLAN intent, Copilot's PREDLOZI intent) — bringing the confirmed platform total to **at least 7
independent "what should the lawyer do next" generators** for the same predmet, only 2 of which
(Task Engine, Matter Intel) share a common deterministic root. The second-most concrete finding is
Finding 1 (`nedostaje` field-name collision between Genome and Copilot PLAN, incompatible vocabularies,
zero mutual awareness) — the cleanest single "two GPT calls, one name, one decision, no reconciliation"
instance in the domain. Finding 4 directly confirms this fork's chartered hypothesis: Drafting's
`quality_gate.confidence_score` and Strategy Engine's Pravni Revizor `ocena` are indeed the same
"is this ready" decision produced by two structurally incompatible, uncoordinated mechanisms, reachable on
the same document text by an ordinary user workflow with no code link between them.

**Does "next recommended action" have a clear single owner? No** — confirmed, not a new answer but a
significantly larger confirmed scope than G-030 previously documented. This should be escalated back to
G-030's still-open founder decision, not treated as a fresh finding requiring its own new ADR.

# Intelligence Propagation Map

**Mission:** Project Synapse, 2026-08-03. For each of the founder's 4 named trigger examples: the
IDEAL propagation chain, the CURRENT actual chain (verified against real code, not assumed), and
what this mission connected vs. what remains a gap.

---

## 1. Client created

**Ideal**: Client created → Conflict Check → Relationship Graph → Firm Memory → Search → Risk Profile
→ Recommendations.

**Actual, verified**:
- Client creation itself: `routers/intake.py` / `klijenti/router.py`.
- Conflict Check: real, but **manual** — `POST /api/intake/conflict-check` requires the lawyer to
  type names; only auto-fires today inside Smart Intake's finalize (`ZTC-003`, a prior mission), not
  from plain client creation.
- Relationship Graph: Evidence Graph and Knowledge Graph both exist but are case-scoped, not
  client-creation-triggered.
- Search: client becomes searchable immediately (already correct, confirmed this engagement).
- Risk Profile / Recommendations: nothing case-specific exists yet at client-creation time (no case
  exists) — this chain's later links are naturally case-scoped, not client-scoped.

**Verdict**: partially real, not because of missing wiring but because several links (Relationship
Graph, Risk Profile) are inherently CASE-scoped concepts being asked to fire on a CLIENT-scoped event
— the chain as described doesn't fully map onto this repo's actual data model. Not force-fit; noted
honestly rather than building a hollow connection.

## 2. Document uploaded

**Ideal**: Document uploaded → OCR → Classification → Entity Extraction → Case Genome → Chronology →
Deadlines → Missing Documents → Evidence Analysis → Strategy → Briefing → Search Index → Knowledge
Graph.

**Actual, verified** (this is the most mature chain in the repository, confirmed across 3 prior
missions plus this one):
```
Upload (Smart Intake or the reachable per-case path)
  → OCR (uploaded_doc/extractor.py)                                    ✅
  → Classification (shared/intake_classify.py)                        ✅
  → Entity Extraction (shared/intake_extract.py)                      ✅
  → Chronology + Deadlines (predmet_hronologija, correct vocabulary)   ✅
  → Case Genome refresh (background task)                             ✅
  → Missing Documents (services/risk_engine.py, reads tip_dokaza)      ✅
  → Evidence Analysis (routers/evidence.py, auto-classify)             ✅
  → Search Index (predmet_dokumenti.tekst_sadrzaj, searchable)         ✅
  → Strategy / Briefing                                                ⚠️ reachable, not auto-triggered
  → Knowledge Graph                                                    ❌ not wired to per-upload events specifically
```
**What this mission connected**: Case Genome now also reaches Firm Brain and Copilot's analysis (2
more downstream consumers than before). **What remains a gap, documented not fixed**: Strategy/
Briefing generation is still lawyer-initiated (a button), not automatically triggered by document
upload — this is a deliberate, previously-made product decision (an LLM call this expensive shouldn't
fire silently on every upload without lawyer awareness of the cost), not an oversight.

## 3. Deadline changed

**Ideal**: Deadline changed → Calendar → Notifications → Risk Analysis → Timeline → Strategy.

**Actual, verified**:
```
Deadline written to predmet_hronologija
  → Calendar (aggregates directly, always current)                    ✅
  → Notifications (email cron, 7/3/1 days out, correct vocabulary)     ✅
  → Risk Analysis (services/risk_engine.py's kriticni_rokovi count)    ✅
  → Timeline (intelligence_timeline.py aggregator)                     ✅
  → Strategy                                                            ❌ no automatic re-trigger
```
**What this mission connected**: `ROK_KRITICAN` — a real, working proactive-alert handler that was
never emitted by anything — now fires from Matter Intelligence's own already-computed critical-hearing
detection, with mandatory dedup against an existing unread alert (see Orchestration Report). This is
the clearest, most literal instance of "connect an island" in this whole mission.

**What remains a gap**: a changed/added deadline doesn't automatically re-trigger Strategy generation
or the AI Briefing. Given both are real LLM calls with real cost, auto-firing them on every deadline
edit was deliberately not implemented — this is the same "don't spend a lawyer's credits without their
awareness" reasoning applied consistently by this engagement's prior missions (e.g., the Winning
Strategy Brief was kept as a separate button from plain AI Briefing for exactly this reason).

## 4. Case updated

**Ideal**: Case updated → Similarity Search → Winning Strategy → Firm Intelligence → Learning Engine.

**Actual, verified**:
```
Case updated (any field, any document, any status change)
  → Similarity Search (Firm Brain / precedenti.py)                     ⚠️ reachable, not auto-triggered
  → Winning Strategy (this engagement's own composition, prior mission) ⚠️ reachable, not auto-triggered
  → Firm Intelligence (firm_dna table)                                 — write path exists, not tied to "case updated" specifically
  → Learning Engine (services/learning_engine.py)                      confirmed exists, reads via semantic search, not further traced this mission (out of this mission's audit scope)
```
**Verdict**: the same pattern as items 2/3 — the reasoning-heavy links (Similarity, Winning Strategy)
are deliberately lawyer-triggered, not event-triggered, because they cost real LLM credits per call.
This is a consistent, repeated architectural choice across this whole engagement, not an oversight
specific to this chain.

---

## Cross-cutting finding: this repository's propagation model is deliberately two-tiered

Every chain above shows the same shape: **deterministic, cheap steps propagate automatically**
(OCR → classification → extraction → chronology → search indexing → risk scoring), while
**expensive, LLM-based synthesis steps require an explicit lawyer action** (Strategy, Briefing,
Winning Strategy Brief, Firm Brain, Outcome Intelligence). This is not an inconsistency to fix — it's
the correct, deliberate design given real per-call billing costs, and this mission's own additions
(the Event Bus wiring) were chosen specifically because they extend the CHEAP, deterministic tier
(an `emit()` call, not a new GPT call) rather than force automatic triggering onto the expensive tier.

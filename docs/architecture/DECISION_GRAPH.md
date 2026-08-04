# Decision Graph — Program Gamma (Masterprompt 003)

For every branch: is this module a **source** of a decision (it decides) or
a **consumer** (it uses a decision already made elsewhere)? Per the
mission's own rule: a module producing a decision it should not produce is
marked **Critical**.

```
Upload → OCR → Extraction
                  │
                  ▼
          Evidence Vault ── SOURCE: claim strength (DC-005, canonical)
                  │          SOURCE: document classification (FRAGMENTED — ALPHA-003,
                  │                  2 independent taxonomies, "correct" one wins only
                  │                  probabilistically — see DECISION_CONSISTENCY_REPORT.md)
                  ▼
             Case Genome ── SOURCE: case-strength % (DC-003, canonical)
                  │          SOURCE: contradictions (FRAGMENTED — 4 authors)
                  │          SOURCE: "what's missing"/"next step" (FRAGMENTED —
                  │                  own vocabulary, 1 of 18 next-action producers)
                  │          SOURCE: heatmap/najslabija_tacka (raw GPT, PROGBETA-004, open)
                  ▼
          ┌───────┼──────────────────┬─────────────────┐
          ▼       ▼                  ▼                 ▼
   Compare Docs  Evidence Graph  Case Commander    Case Intelligence
   SOURCE:       SOURCE:         SOURCE:           SOURCE:
   contradiction contradiction   contradiction,     "next step"
   (evidence-    (evidence-      next-action×3      (FRAGMENTED,
   checked,      checked THIS    (evidence-checked   was CRITICAL LIVE
   DC-009)       MISSION,        for predmet-ref     BUG until this
                 DC-009)         THIS MISSION,        mission's fix)
                                 DC-009; still NOT
                                 checked for the
                                 "next-action"
                                 content itself)
                  │
                  ▼
          Legal Reasoning Engine ── SOURCE: Claim nodes (ORPHANED by design,
                  │                         Phase 0 — correctly not wired yet)
                  │          CONSUMER: retrieve_documents()'s retrieval_meta
                  │                    (SOURCE-n grounding — proven mechanism,
                  │                    wired only into Drafting)
                  ▼
          ┌───────┴────────────────────┬─────────────────────┐
          ▼                            ▼                      ▼
    Strategy Engine              Court Predictor          Case Pipeline
    SOURCE: win-probability %    SOURCE: confidence         (steps 1-9)
    (FRAGMENTED — PROGBETA-001,  (DC-004, canonical —       SOURCE (step 3):
    4 generators)                Program Alpha fix)         deadline vaznost
    SOURCE: strategic            SOURCE: strategic          (plausible dup of
    recommendation (FRAGMENTED,  recommendation ×4          Alpha's 6 threshold
    3 more generators inside     endpoints (part of the     copies, unconfirmed)
    this router alone)           18 "next action" total, GAMMA-001)   SOURCE (step 5):
    SOURCE: document readiness   SOURCE: argument color/    5th independent
    ×2 (standalone vs.           profile confidence         "case outlook"
    orchestrator step, unrec-    (DC-012, fixed THIS        generator (joins
    onciled)                     MISSION — was raw,         Strategy Engine's 4)
    SOURCE: cross-step conflict  now derived)                SOURCE (step 6):
    detection (DC-011, partly                                free shadow of
    fixed THIS MISSION —                                     hearing_cc.py,
    categorical subset now                                   unlabeled duplicate
    code-computed)                                            CONSUMER (steps
                                                               7/8): risk_engine
                                                               (canonical — Core
                                                               Consolidation
                                                               2026-07-22)
          │                            │
          ▼                            ▼
       Copilot ── SOURCE: "next action" ×3 (PLAN, PREDLOZI, ask_agent's
          │        brza_procena_koraci) — none read risk_engine or Genome
          │        SOURCE: "nedostaje" (field-name collision with Genome's
          │        own `nedostaje`, incompatible vocab)
          │        CONSUMER: ask_agent's law-citation grounding (DC-canonical-
          │        adjacent — strongest evidence chain in the platform)
          ▼
       Briefing (Morning) ── CONSUMER: alert list (already-computed)
          │                  SOURCE: prose prioritization (low-stakes,
          │                          courtesy text only)
          ▼
       Task Engine ── CONSUMER: identify_case_problems (DC-002, canonical —
          │                     "positive reference pattern," Program Beta)
          │           SOURCE (soft gap): task `prioritet` in LLM-success path
          │                     not code-enforced from `ozbiljnost` (fallback
          │                     path only)
          ▼
       Alert Engine ── CONSUMER: create_proactive_alert (DC-013, canonical —
          │                      Program Alpha)
          │            SOURCE: alert urgency (DC-006, canonical — Program
          │                    Gamma dedup this mission)
          ▼
       Dashboard ── CONSUMER: calculate_procesni_rizik (DC-001, canonical)
          │
          ▼
       Search ── makes NO decision (confirmed clean, Program Gamma)
          │
          ▼
       Memory Graph ── fully isolated, zero consumers (confirmed dead,
          │            multiple prior missions)
          ▼
       Firm Brain ── SOURCE (orphaned): judge win-rate/procedural preference/
                      client settlement posture — real data, zero live
                      consumers (ALPHA-005, sharpened this mission)
```

## Source-vs-consumer summary

| Module | Role | Critical? |
|---|---|---|
| `services/risk_engine.py` | Pure source (2 canonical decisions) | No — the reference pattern |
| Case Genome | Source (case strength — clean; contradictions/next-action — fragmented) | **Yes**, for the fragmented outputs |
| Compare Docs, Evidence Graph, Case Commander | Source (contradiction/reference decisions), now evidence-checked | Partially mitigated this mission |
| Case Intelligence | Source ("next step") | Was Critical (live 500 bug), fixed this mission |
| Strategy Engine | Source (win-probability, strategic recommendation, readiness) | **Yes** — largest single-router fragmentation |
| Court Predictor | Source (confidence — clean; strategic recommendation — fragmented) | Partially — confidence is canonical, recommendation is not |
| Case Pipeline | Mixed — steps 7/8 consumer (clean), steps 3/5/6 source (fragmented/duplicate) | **Yes**, for steps 5/6 |
| Copilot | Source ("next action" ×3, "nedostaje") | **Yes** |
| Task Engine | Consumer (clean, positive pattern) | No |
| Alert Engine | Consumer + 1 clean source (urgency) | No |
| Dashboard, Search | Pure consumer / no decisions | No |
| Firm Brain | Source, but orphaned (no live consumer at all) | No live risk, but a missed-opportunity finding |

## The single dominant pattern across this entire graph

Every module in this platform that touches "what should the lawyer do
next" independently asks an LLM the question, rather than reading a shared
answer. `services/risk_engine.py` proves the alternative works — it is
consumed cleanly by 6+ modules with zero divergence — but it was built for
one narrower decision (procedural risk / missing documents), and nothing
generalized its "compute once, consume everywhere" shape to the broader
"strategic recommendation" decision when Strategy Engine, Court Predictor,
Copilot, Case Commander, and Case Intelligence were each built as
independent product surfaces. This is the graph-level evidence for
`CANONICAL_DECISION_ENGINE.md`'s central design decision.

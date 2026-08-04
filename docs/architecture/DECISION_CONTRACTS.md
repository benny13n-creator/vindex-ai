# Decision Contracts — Program Gamma (Masterprompt 003)

Every canonical decision in `DECISION_REGISTRY.md` gets a contract:
**Ulazi / Preuslovi / Algoritam / Dozvoljeni izlazi / Objašnjenje / Evidence
Chain / Audit Payload / Version / Failure Behavior / Confidence
Methodology.** None of these 13 functions are new — this is the first time
their contract has been written down explicitly rather than left implicit
in code comments.

---

### DC-001 — Procesni rizik (case risk / health score)
- **Function**: `services/risk_engine.py::calculate_procesni_rizik(predmet_id, supa)`
- **Ulazi**: `predmet_id`, a live Supabase client (queries `predmet_dokumenti`, `predmet_dokazi`, `rocista`, `zadaci`).
- **Preuslovi**: predmet must exist and be owned by the caller (enforced by callers, not this function).
- **Algoritam**: weighted deterministic tally over document count, evidence count, upcoming/missed deadlines. No LLM call.
- **Dozvoljeni izlazi**: `{"health_score": int 0-100, "nivo": "zdrav"|"upozorenje"|"kriticno", ...}`.
- **Objašnjenje**: score is a sum of named, inspectable components — every consumer can show its breakdown.
- **Evidence Chain**: implicit — every component is a real DB count, not an LLM claim.
- **Audit Payload**: none dedicated (pure computation, not an AI call) — callers log their own action.
- **Version**: unversioned function; behavior changes are tracked via git history, not a schema version field (no consumer persists a stale copy of the formula's output long enough to need one).
- **Failure Behavior**: caller-responsibility; function itself has no try/except (pure computation over already-fetched data).
- **Confidence Methodology**: N/A — deterministic, not a probabilistic estimate.

### DC-002 — Sledeći koraci (deterministic missing-item detection)
- **Function**: `services/risk_engine.py::identify_case_problems(rizik, tip_predmeta)`
- **Ulazi**: the `rizik` dict DC-001 already produced, case type.
- **Algoritam**: rule-based (`EXPECTED_DOCS` match, deadline thresholds). No LLM.
- **Dozvoljeni izlazi**: `list[{"problem": str, "ozbiljnost": "kritican"|"srednji"|"nizak"}]`.
- **Objašnjenje**: each finding names the specific missing document type or overdue deadline.
- **Evidence Chain**: `EXPECTED_DOCS`-based, traceable to real `predmet_dokumenti.tip_dokaza` rows.
- **Failure Behavior**: same as DC-001 — pure function, caller-responsibility.
- **Confidence Methodology**: N/A — deterministic rule match, not a probability.
- **Known limitation** (not this contract's fault): consumers downstream of `intake_classify.py`'s classifier can feed this function a `tip_dokaza` in the wrong vocabulary during the classification race window (`ALPHA-003`) — the function itself is correct; its input can be corrupted upstream.

### DC-003 — Case-strength percentage (Genome)
- **Function**: `shared/genome_validator.py::compute_snaga_score(genome)`
- **Ulazi**: the Genome dict, specifically `snaga_faktori` (LLM-extracted, case-specific) and `genome_kompletnost`.
- **Algoritam**: `baseline 50 + Σ(uticaj factors)`, clamped [0,100], categorized by named thresholds (≥75 jaka, <35 slaba).
- **Dozvoljeni izlazi**: `{"snaga_predmeta_procent": int, "snaga_predmeta": str, "snaga_faktori": list}`.
- **Objašnjenje**: every factor's `uticaj`/`opis` is returned alongside the score — fully inspectable.
- **Evidence Chain**: factors come from `_extract_genome`'s own case-document-grounded extraction.
- **Failure Behavior**: never raises; malformed `snaga_faktori` degrades to `neto=0` (baseline 50).
- **Confidence Methodology**: N/A — deterministic arithmetic, not a probability. Explicitly designed (2026-07-18) to replace an LLM self-report that anchored on a prompt example.

### DC-004 — Court Predictor confidence
- **Function**: `routers/court_predictor.py::_calc_confidence_nivo` / `_procenat_iz_score`
- **Ulazi**: RAG hit count, VKS hit count, `case_patterns` firm history, evidence count.
- **Algoritam**: 0-9 score from named thresholds → level (NISKO/SREDNJE/VISOKO) and 20-80%-bounded percentage from the same score.
- **Dozvoljeni izlazi**: `(nivo, boja, faktori_plus, faktori_minus, score)`.
- **Objašnjenje**: `faktori_plus`/`faktori_minus` name which signals contributed.
- **Evidence Chain**: every signal is a real count (RAG/VKS hits, firm history rows).
- **Failure Behavior**: the accompanying GPT call (`_pozovi_confidence_api`) is explicitly barred from touching the number — instructed "NE navodi procenat ni broj."
- **Confidence Methodology**: bounded 20-80% by deliberate design — never claims certainty. The platform's most-cited reference pattern (Program Alpha, 2026-08-04).

### DC-005 — Evidence Vault claim strength
- **Function**: `routers/evidence.py::_snaga_iz_lokacije(tvrdnja, lokacija)`
- **Ulazi**: the extracted claim text, `_lociraj_tvrdnju`'s grounding result.
- **Algoritam**: "jaka" only if found AND claim length in [20,100] chars (bounds added Program Beta Faza 10, after 2 independent governance reviewers found the same over-claim risk); else "srednja".
- **Dozvoljeni izlazi**: `"jaka"` | `"srednja"`.
- **Objašnjenje**: UI tooltip (Program Beta) shows grounding location for "jaka".
- **Evidence Chain**: `_lociraj_tvrdnju`'s page/paragraph/offset.
- **Failure Behavior**: `_lociraj_tvrdnju` never raises, always returns a dict with `start_offset` (possibly `None`).
- **Confidence Methodology**: binary, not a probability — explicitly scoped to "was this verbatim-locatable," not general evidentiary weight (documented after Legal Domain Expert governance finding).

### DC-006 — Genome delta significance / alert urgency
- **Function**: `routers/case_dna.py::_delta_significant` / `_delta_hitnost`
- **Ulazi**: the delta dict from `_compute_delta` (old vs. new Genome snapshot).
- **Algoritam**: named thresholds (`snaga_delta`≥5 for significance, ≥15 or `kontr_nove`>1 for urgency).
- **Dozvoljeli izlazi**: `bool` (significant) / `"hitna"` | `"normalna"`.
- **Objašnjenje**: threshold values are named constants in the function body.
- **Evidence Chain**: delta components are all real diffs of two persisted Genome snapshots.
- **Failure Behavior**: pure function, no I/O, cannot fail except on malformed input (returns `False`/`"normalna"` on empty dict).
- **Confidence Methodology**: N/A.
- **Note**: `_delta_hitnost` is a Program Gamma extraction — previously inlined identically at 2 call sites (routers/case_dna.py:757,916 pre-fix), a real "second author, one edit from divergence" risk this mission closed.

### DC-007 — Genome internal consistency / escalation need
- **Function**: `shared/genome_validator.py::verify_genome` / `routers/case_dna.py::_maybe_alert_require_review`
- **Ulazi**: Genome dict + case documents.
- **Algoritam**: 4 independent checks (doc-existence for `dokazi_rang`, DOK-XX existence for `kontradikcije`, soft law-ref check, internal strength consistency), each fail-soft/isolated.
- **Dozvoljeni izlazi**: `{"odluka": "approve"|"approve_with_warning"|"require_review", "hard_flags": list, "soft_flags": list, "provereno_u_ms": float}`.
- **Objašnjenje**: every flag names the specific field and reason.
- **Evidence Chain**: hard-flags check against real document/DOK-XX identity.
- **Failure Behavior**: never raises — each sub-check is independently try/excepted.
- **Confidence Methodology**: N/A — rule-based, not probabilistic. Advisory (non-blocking at the DB layer), but the UI (Genome's `_verifikacija` block) surfaces it prominently, non-collapsibly.

### DC-008 — Draft readiness (citation half)
- **Function**: `services/quality_gate.py::evaluate_draft_quality` (citation_score component)
- **Ulazi**: draft text, real indexed legal corpus.
- **Algoritam**: `_extract_article_citations` + `_verify_citation` batch-checked against the corpus; `confidence_score = 0.6*citation_score + 0.4*completeness_score`.
- **Dozvoljeni izlazi**: `confidence_score: float 0.00-1.00`, gate at `>=0.85`.
- **Objašnjenje**: module docstring explicitly documents the formula and its limits ("a fair proxy, not a full Legal Reasoning Engine").
- **Evidence Chain**: citation half is fully grounded; completeness half is presence-only, not correctness (documented limitation, not a defect — see `PROGBETA-003`).
- **Failure Behavior**: citation-verification batch failure → neutral 0.5, never blocks.
- **Confidence Methodology**: documented, reproducible, the domain's best example (Program Beta).

### DC-009 — Reference existence validators
- **Functions**: `validate_dok_reference`, `validate_graph_edge_references`, `validate_predmet_reference` — `shared/genome_validator.py`
- **Ulazi**: free text or a node/edge structure, plus the known-valid set of references (documents, graph nodes, predmet IDs) actually in scope for the call.
- **Algoritam**: pattern-match candidate references in the text/structure, flag any not in the known set.
- **Dozvoljeni izlazi**: `list[{"polje": str, "razlog": str, "stavka": str}]` — empty list = no invented reference found.
- **Objašnjenje**: each flag names exactly which reference was invented and why it's flagged.
- **Evidence Chain**: this function IS the evidence-chain mechanism for its callers.
- **Failure Behavior**: never raises — non-string/malformed input returns `[]`, not an exception (Program Beta + Gamma governance findings both hardened this).
- **Confidence Methodology**: N/A — binary existence check, not probabilistic.
- **Reuse note**: one principle ("a referenced entity must exist in the known scope"), 3 ID schemes (DOK-NN numbers, graph node ids, predmet-ID prefixes) — proof the pattern generalizes cheaply once designed once.

### DC-010 — Strategy Synthesis low-confidence aggregation
- **Location**: inline block, `strategija.py::orkestrator_kompletna_analiza_sync`
- **Ulazi**: `confidence` field from 4-5 prior orchestrator steps.
- **Algoritam**: counts `confidence=="NISKA"` (+ off-spec anomalies, conservatively), separately counts JSON-parse-failure steps; triggers at ≥2 genuine-NISKA or any technical failure.
- **Dozvoljeni izlazi**: `sistemsko_upozorenje: str | None`.
- **Objašnjenje**: message names how many steps and of what kind (low-confidence vs. technical error vs. anomaly).
- **Failure Behavior**: overrides the LLM's own output in both directions — code is authoritative, not advisory.
- **Confidence Methodology**: N/A — deterministic count, not a probability. Program Beta's canonical example of "LLM rezonuje, platforma računa."

### DC-011 — Strategy Synthesis categorical co-occurrence signals (structurally-checkable subset)
- **Location**: inline block, `strategija.py::orkestrator_kompletna_analiza_sync`
- **Ulazi**: `korak1.ocena`, `korak2.ukupna_ocena`, `korak2.preporuka`, `korak4.ukupna_ranjivost`, `korak5.presuda.izreka` (all constrained-vocabulary enums already present when Synthesis is called).
- **Algoritam**: 2 named categorical co-occurrence checks, each appends a labeled, hedged string to `detektovani_konflikti` if triggered. Rule 2 is additionally gated: only fires when `korak2.preporuka` is litigation-shaped (`PODNETI`/`ISPRAVITI_PA_PODNETI`/`NE_PODNETI`), since Korak 5 (the simulated judge) runs unconditionally even for transactional matters where a "TUZBA USVOJENA/ODBIJENA" verdict is not actually applicable.
- **Dozvoljeni izlazi**: appends to the existing `detektovani_konflikti: list[str]` field — additive, does not replace the LLM's own semantic conflict findings.
- **Objašnjenje**: each computed entry is prefixed `[Izračunato — proverite]` and names the exact two steps/values, using hedged ("moguća napetost") not assertive ("↔ nekonzistentno") language.
- **Failure Behavior**: additive only — if the deterministic check finds nothing, the LLM's own list is untouched.
- **Confidence Methodology**: N/A — binary category match, not a legal-substance judgment.
- **Explicit scope limit, stated honestly — corrected after Olympus Faza 10 governance review (2026-08-04, Legal Domain Expert)**: this is **NOT** a logical-contradiction detector, despite the mission's own earlier draft calling these "incompatible pairs" — that language overclaimed. These are **correlated categorical co-occurrence heuristics** that can and do fire on legally coherent, non-contradictory scenarios (e.g. rule 1: a well-drafted document — Revizor's narrow procedural/formal scope — supporting a substantively weak case — Red Team's merits scope — is normal, not a defect; the Synthesis prompt's own example qualifies this pairing with "zbog iste klauzule," a causal link the code cannot verify). Wording softened to "moguća napetost — proverite" and rule 2 scoped to litigation-shaped matters specifically to reduce false-positive/alert-fatigue risk; both remain advisory-only co-occurrence signals, not confirmed contradictions.

### DC-012 — Court Predictor derived categorical fields
- **Location**: inline blocks, `routers/court_predictor.py::argument_reputation` / `judge_profile`
- **Ulazi**: `uspesnost_procena` (0-100, already returned by the same call — int, float, or numeric string all handled) / `ukupno_odluka_analizirano` (real RAG hit count).
- **Algoritam**: `boja` = zelena(≥65)/žuta(35-64)/crvena(<35), per the prompt's own stated rule; `pouzdanost_profila` = visoka(≥10)/srednja(5-9)/niska(<5 or no RAG).
- **Dozvoljeni izlazi**: the 2 named enums.
- **Objašnjenje**: rule is stated verbatim in the prompt AND enforced in code — no divergence possible between `boja` and its own `uspesnost_procena`.
- **Failure Behavior**: post-processes the already-parsed JSON; numeric-string values are coerced (Olympus Faza 10 governance review, AI Governance, found the original fix only handled `int`/`float`); if `uspesnost_procena` is still missing/non-numeric after coercion, the raw (possibly wrong) LLM value is left untouched rather than crashing (fail-soft).
- **Confidence Methodology**: `pouzdanost_profila` is itself a confidence-in-the-analysis signal, now fully code-derived (the middle band 5-9 was the one gap, closed this mission). **Explicit scope limit (Legal Domain Expert)**: `boja` only guarantees internal self-consistency with its own `uspesnost_procena` — it does NOT validate that the underlying percentage itself is well-calibrated (it remains an ungrounded per-argument LLM self-report, unlike DC-004's separately RAG/VKS-grounded confidence). A lawyer seeing "zelena" should read it as "internally consistent," not "independently verified reliable."

### DC-013 — Canonical alert creation
- **Function**: `shared/proactive_alerts.py::create_proactive_alert`
- **Ulazi**: `supa`, `user_id`, `predmet_id`, `tip`, `naslov`, `opis`, `urgentnost`, `retry_internally: bool = True`.
- **Algoritam**: single INSERT with schema-correct columns; `retry_internally=False` variant for callers (Event Bus handlers) that already have their own outer retry, added Program Alpha's own Phase 9 governance fix.
- **Dozvoljeni izlazi**: the created alert row (or raises, per `retry_internally`).
- **Objašnjenje**: N/A (a write operation, not a reasoning decision) — included because it is the canonical single-write-path Program Alpha established, and every other decision contract in this file that produces an alert routes through it.
- **Version**: `retry_internally` parameter added 2026-08-04 (Program Alpha Phase 9).
- **Failure Behavior**: documented per caller — the exact defect class this parameter was added to prevent (retry compounding with the durable-outbox batch loop under sustained outage) is written up in `ARCHITECTURAL_DEBT_REGISTER.md`'s Program Alpha section.

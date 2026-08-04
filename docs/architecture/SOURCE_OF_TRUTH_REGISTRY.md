# Source of Truth Registry — Program Alpha, Phase 4

For every data area the founder's mission prompt names explicitly (Risk Score, Confidence, Timeline,
Deadlines, Health, Case Status, Evidence, Knowledge Index, Memory, Genome, Search, Audit, Correlation),
plus every area the Phase 1 inventory found a decision for: **who decides, who may read, who may write,
who must not exist.** Per the mission's own rule: *"Ako postoje dva autora istog podatka: to je
Critical."*

| Data area | Who decides (the one author) | Who may read | Who may write | Who must NOT exist (found or confirmed absent) | Verdict |
|---|---|---|---|---|---|
| Risk / health score | `services/risk_engine.py::calculate_procesni_rizik` | api.py, ccc.py, dashboard.py, matter_intel.py, zadaci.py | Only the canonical function itself | No second author found | **Clean** |
| Next-action / problem detection | `services/risk_engine.py::identify_case_problems` | Same set | Only the canonical function | No second author found | **Clean** |
| Case Genome strength % | `shared/genome_validator.py::compute_snaga_score` | Genome UI, Copilot, Firm Brain | Only the canonical function | No second author found | **Clean**, but see UI-perception note below |
| Court Predictor confidence LEVEL (`nivo`) | `_calc_confidence_nivo()` | Court Predictor response | Only the canonical function | No second author | **Clean** |
| Court Predictor confidence PERCENTAGE (`procenat`) | **Two authors**: the deterministic tally above (indirectly) AND a separate, unchecked GPT call | Same response, displayed adjacent to `nivo` | Both | **The GPT call must not exist as an independent author** — either delete it or make it read-only, deriving from `nivo` | **Critical — two authors of one perceived value** |
| Strategy Engine litigation win-probability | **No deterministic author at all** | Strategy Engine PRO endpoint | Raw LLM completion | A grounding layer must exist before this number is presented as fact | **Critical — zero authoritative source, not merely duplicated** |
| Evidence "strength" (auto-classification path) | Nominally `routers/evidence.py:221`, but the value is a hardcoded literal, not a real computation | Risk Engine's tally | The classification handler | A real per-fact confidence signal must exist here, currently doesn't | **Compromised — the nominal author isn't actually deciding anything** |
| Document classification (`tip_dokaza`) | **Two authors**: `shared/intake_classify.py` (writes first, wrong vocabulary) then `routers/evidence.py`'s classifier (writes second, overwrites with correct vocabulary) | `predmet_dokumenti`, `predmet_dokazi`, Evidence Vault UI, missing-doc detector | Both, in a specific, un-enforced order | **`intake_classify.py`'s independent taxonomy/AI call must not exist** — it should feed a heuristic pre-filter into the one real classifier, not maintain a parallel decision | **Critical — held together by implicit call-order, not architecture** |
| Entity extraction (parties/court/amounts/dates) | Two authors: `shared/intake_extract.py` and `routers/evidence.py`'s `ai_tags` | Different fields/tables, no active overwrite conflict | Both, independently | The weaker (Evidence's unstructured, no-confidence) implementation should defer to the stronger canonical one | **Duplicate, lower severity** — no active correctness bug today, real future-drift risk |
| Missing-document detection | `shared/constants.py::EXPECTED_DOCS` → `risk_engine.py`'s detector | matter_intel.py, ccc.py | Only the canonical constant/function | No second author found | **Clean, already consolidated** |
| RAG/legal document retrieval | `app/services/retrieve.py::retrieve_documents()` | ~15 call sites | Only the canonical function | No second author found across ~20+ call sites | **Clean — the model to replicate elsewhere** |
| Query embedding | `app/services/retrieve.py::_ugradi_query()` | ~6 call sites | Only the canonical function | No second author found | **Clean** |
| Document embedding (ingestion) | **No single author** — 5 independent call sites each hardcode the model name | Pinecone index | 5 routers, independently | A shared `get_embedding_model_name()` (or equivalent) must be the only source | **Latent — harmless by coincidence today, not by design** |
| Pinecone namespace identity | **No single author** — 3 hardcoded query-side constants + 2 more independent ingest-side sources | Query path (fixed set) / Ingest path (2 separate, un-synchronized sources) | Multiple, independently | A single registry (constants module or DB table) must be the only source | **Compromised — a write can succeed into a namespace no read path ever queries** |
| Firm institutional memory for AI | **Two authors**: `api.py::_fetch_firm_memory_context` (live, incomplete) and `routers/firm_memory.py::kontekst_za_ai` (dead, more complete) | Copilot/RAG (live path only) | Neither writes state, both independently *retrieve* — but retrieval logic itself is the "decision" here | The incomplete, ad hoc `api.py` version should not remain the sole live implementation | **Critical — the more capable implementation is dead code** |
| Case Pipeline trigger | `on_predmet_kreiran` Event Bus handler | New predmet creation only | Only this handler | No second trigger point found | **Clean** |
| Memory Graph | `routers/memory_graph.py` | Nobody | Nobody (isolated) | N/A — not a duplicate-authorship problem, a connectivity problem (tracked separately, `KEYSTONE-002`) | **Isolated, not duplicated** |
| Business audit trail | `shared/audit_immutable.py` (canonical, hash-chained) | Everywhere | Should be: only `log_action`/`log_action_sync` | **`response_audit`/`app/services/audit_log.py::log_response` must not exist** — write-only, zero readers, overlapping fields with `ai_forensics` | **Duplicate — one side is dead weight, actively still written** |
| Request correlation ID (externally visible) | **Two fully independent authors**: `api.py`'s HTTP middleware (external, client-visible) and `shared/ai_provenance.py` (internal, everywhere else) | External: HTTP clients via `X-Correlation-ID` header. Internal: `audit_immutable`, `ai_forensics`, `events` | Both, completely disconnected | **The middleware must not mint its own value — it must read from/write into `ai_provenance.py`'s context** | **Critical — the one externally-visible id doesn't match anything internally recorded** |
| Correlation ID minting | `shared/ai_provenance.py::new_correlation_id()` | Everywhere | Should be: only this function | **2 ad hoc inline `uuid.uuid4()` calls in `case_dna.py` must not exist** | **Duplicate, low severity** |
| Business event distribution | `services/event_bus.py` (`emit()` + durable outbox) | Everywhere | Only this module's functions | No new non-durable path found beyond the 2 already tracked (`SENT-001`) | **Clean, 2 known tracked exceptions** |
| Outbound email | **No single author** — 5 independent `smtplib` implementations | N/A | 5 routers, independently | A single `send_email()` must be the only sender — `email_notif.py::_smtp_send` is the best existing candidate (already correctly reused by `client_portal.py`) | **Duplicate — proven by 5 different hardcoded timeout values** |
| Current-user verification | `shared/deps.py::get_current_user` | Everywhere | 1 canonical + 1 legacy path, both correctly wired into the same correlation context | Legacy path (`api.py::_require_auth`) not independently investigated this pass (flagged for a security-domain fork, not this mission) | **Not re-litigated here** |

## UI-perception note (not a source-of-truth violation, but adjacent)

Genome's `snaga_predmeta_procent` and Risk Engine's `snaga_dokaza`/`snaga_pct` are BOTH legitimately
single-sourced (each has exactly one author) but answer a closely related question with no UI label
distinguishing them — a lawyer could see two different "strength" numbers for the same case with no
explanation. Not ranked Critical (no actual dual-authorship), but tracked as a real UX-clarity risk in
`ARCHITECTURAL_DEBT_REGISTER.md`.

## Verdict counts

**Critical (two authors of one data point, or zero authoritative source where one is expected): 6** —
Court Predictor `procenat`, Strategy Engine litigation %, document classification (`tip_dokaza`), firm
memory for AI, business audit trail, request correlation ID.
**Compromised (nominally single-sourced but the source isn't actually deciding anything real): 1** —
Evidence auto-classification strength.
**Latent (harmless today, a defect waiting for a normal-looking future change to trigger): 2** — embedding
model, Pinecone namespace.
**Duplicate, lower severity: 3** — entity extraction, correlation-id minting, outbound email.
**Clean, confirmed single-sourced: 14.**

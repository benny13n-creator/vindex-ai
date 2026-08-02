# Vindex AI — Trust Architecture Traceability Matrix

**Date:** 2026-08-01
**Position in hierarchy:** this document sits directly under
`docs/architecture/VINDEX_TRUST_ARCHITECTURE_BLUEPRINT.md` (the constitution) and connects it to
the existing implementation-evidence layer (`SECURITY_MATURITY_DASHBOARD.md`,
`security/SECURITY_GAP_REGISTER.md`, `security/STRIDE_THREAT_MODEL.md`, `security/SECURITY_ROADMAP.md`).
It performs Phases 1, 3 and 4 of the reconciliation the founder requested on 2026-08-01: map
existing documents onto the Blueprint's 10 capabilities, identify genuine architectural gaps
(net-new Programs, not known implementation bugs), and sequence those Programs into a
regression-minimizing dependency order.

**What this document deliberately does NOT do:** re-run the security assessment. Every finding
cited below already exists in the Gap Register/Dashboard/STRIDE model; this document adds a
capability-mapping lens on top, not a new audit. No code was changed to produce this document.

**Method:** direct reading of all documents listed below (not sampled), plus targeted `grep`/code
verification of specific claims where a document appeared to disagree with current code state
(noted inline where that happened).

---

## Part 1 — Document → Capability Traceability Matrix

Capability numbers refer to Blueprint §1.9:
**1** Auth/authz · **2** Data classification & protection · **3** Case/document-level access
control · **4** AI Governance Layer · **5** Prompt-injection/LLM-attack defense · **6** Forensic
audit of AI decisions · **7** Controlled use of external AI models · **8** Backup & recovery ·
**9** Anomaly/abuse detection · **10** Traceability of critical operations

| Document | Date | Capabilities | What it evidences |
|---|---|---|---|
| `security/SECURITY_GAP_REGISTER.md` | 2026-07-23, updated 2026-07-24 | 1,2,3,5,8,9,10 | Primary evidence-only findings register, 36 IDs, `file:line` cited. SSOT for "what's broken." |
| `SECURITY_MATURITY_DASHBOARD.md` | 2026-07-26 | 1,2,3,6,8,9,10 | SSOT for current maturity per domain, 9-stage lifecycle-mapped status. |
| `security/FINDING_LIFECYCLE.md` | 2026-07-23 | all (methodology) | Defines the 9-stage maturity scale used by the Dashboard; project-wide, not security-only. |
| `security/SECURITY_ROADMAP.md` | 2026-07-23 | 1,2,3,5,8,9,10 | P0–P3 sequencing of Gap Register findings. |
| `security/STRIDE_THREAT_MODEL.md` | 2026-07-24 | 1,2,3,5,6,8,9,10 | Structural per-module (Genome/Draft/OCR/RAG/Supabase/Billing) threat enumeration; explicitly states the single-service-role-key fact means **no independently-enforced trust boundary exists** (§0.1) — direct evidence against Blueprint Principle 5 (Zero Trust) being met today. |
| `security/EXECUTIVE_SECURITY_SUMMARY.md` | 2026-07-23 | all (narrative) | Score history 45→70/100; honest "not yet enterprise-grade" verdict; **this document's per-sprint entries are the single best evidence trail for capability 1/3/5/9/10 status below.** |
| `security/PUBLIC_SECURITY_CLAIMS.md` | 2026-07-23 | 1,2,3,4,5,6,7,8 | What can/cannot be claimed publicly; List B explicitly forbids "Zero-trust architecture" and "AI Governance"-implying claims beyond narrow scope — **this document is itself evidence that capability 4 is not yet claimable.** Needs re-running per its own §"How to use" note (several List B items may have moved to List A since 2026-07-23; not re-verified in this pass). |
| `security/AUTHORIZATION_PATTERN_RECOMMENDATION.md` | 2026-07-23 | 1,3 | Designed-not-implemented consolidation of ~18 independently-written ownership-check call sites into one dependency. Direct evidence capability 3 is functionally present but architecturally fragmented. |
| `security/DATA_INTEGRITY_INITIATIVE.md` | 2026-07-23 | 1,2,3,10 | Names SEC-033's pattern (owner/creator columns missing FK constraints, confirmed in 8+ tables across 4 feature areas) as an epic, deliberately unscoped. Evidence of a recurring "no schema-review checkpoint" process gap, not a single bug. |
| `security/DISASTER_RECOVERY_PLAN.md` | 2026-07-24 | 8 | RTO ≤2h / RPO ≤15min policy; **explicitly flags RPO as unverified** — PITR status unconfirmed, true RPO may be 24h; no uptime monitoring wired (detection gap); first backup-restore drill (2026-07-24) found and fixed 2 latent bugs in the audit-chain verifier itself. |
| `security/PUBLIC_SECURITY_CLAIMS.md` (duplicate ref, capability 6) | — | 6 | "Audit logs immutable" (List A) is narrowly, correctly scoped — do not broaden to "full audit coverage." |
| `security/AUDIT_CHAIN_INCIDENT_2026-07-24.md` | 2026-07-24 | 6, 10 | `verify_chain_integrity()` had 2 bugs (timestamp false-positive, concurrent-write race) undetected from migration 043 (2026-07-07) until the first real drill — 2.5 weeks where a forensic-integrity mechanism was unverified. Both fixed. Direct evidence for capability 6's "documented but not exercised until now" status. |
| `security/SEC031_*` cluster (8 files: FK_GRAPH, IMPACT_ANALYSIS, MIGRATION_DRY_RUN, MIGRATION_SAFETY_PLAN, PEER_REVIEW_CONSENSUS, PRODUCTION_ASSUMPTIONS, PRODUCTION_EXECUTION_LOG, REMEDIATION_DESIGN) | 2026-07-23 | 8, 2 | Full evidence chain for the one finding that has completed all 9 Finding Lifecycle stages (Closed, production-verified). Capability 8 (safe storage/recovery of data integrity) — this specific FK-cascade risk is closed; **SEC-033/Data Integrity Initiative above shows the same class of gap recurs elsewhere, unscoped.** |
| `security/P0_FIX_VERIFICATION.md`, `security/P1_P2_FIX_VERIFICATION.md` | 2026-07-23 | 3, 5 | Proof packages for SEC-001/003/007/008/023 closures. `P0_FIX_VERIFICATION.md` explicitly names the "trust boundary" between system/user message roles that `wrap_for_ai()`/the central guard rely on — the one place in the whole doc set (besides the Blueprint itself) where "trust boundary" is used as a specific technical concept, not a generality. |
| `ENTITLEMENT_AUDIT_PHASE1.md` | 2026-07-14 (commit `66912e2`) | 1, 3 | **Strongest single document for capability 1.** Found 5 overlapping, partially-dead authorization mechanisms with no single source of truth; ~135/~160 AI-cost-bearing endpoints ungated at time of writing; 2 confirmed unauthenticated cost-incurring endpoints. **Verified in this pass, not assumed:** both unauthenticated endpoints (`api.py:1894` uses a signed 256-bit token by design, not a bug; `routers/praksa.py`'s 3 endpoints now carry `Depends(get_current_user)`) are fixed in the same commit as this doc. `PermissionService` (`shared/permissions.py`) and `UsageService` (`shared/usage.py`) — the doc's own proposed Phase 2 build — **both exist in code today**, confirming Phase 2 shipped at some point after 2026-07-14, though no document records that completion or its actual endpoint-coverage — flagged as a documentation gap, not a functionality gap. |
| `architecture/VINDEX_TRUST_LAYER_ANALYSIS.md`, `TRUST_LAYER_IMPLEMENTATION_PLAN.md`, `TRUST_LAYER_BETA_FREEZE_2026-07-19.md` | 2026-07-19 | 6, 10 | **Naming collision, flagged explicitly**: this project's "Trust Layer" means AI-output confidence/explainability UX (can a lawyer see why the AI concluded X), not security access control — a different concept from the Blueprint's "Trust Architecture." 5/6 v1 items live on `main`; 1 item (Smart Intake confidence display) stuck on an unmerged branch pending an unrelated product decision. Superseded as the active governing doc by `VINDEX_CORE_CONSOLIDATION.md`. |
| `architecture/VINDEX_CORE_CONSOLIDATION.md` | 2026-07-22 (ACTIVE) | 4 (precursor), 10 | §1.6's unified `intelligence-timeline` merging `audit_immutable` as a 6th source is real, shipped evidence for capability 10. Faza 3's "AI never decides where a deterministic algorithm exists" rule is the **closest existing precedent** to capability 4 (AI Governance) — but it is framed as a business-logic-ownership rule (who computes a score), not a named control layer over LLM calls. Bridge, not a match. |
| `architecture/KNOWN_RELIABILITY_RISKS.md` | — | 6 | `verify_genome()` can silently return `"approve"` if all 5 sub-checks fail simultaneously — fail-open, not fail-loud. Open, deliberately unfixed (low probability, high trust-impact). Direct evidence capability 6 has a known fail-open path. |
| `architecture/VINDEX_OPERATIONAL_GAP_REGISTER.md`, `architecture/OPERATING_SYSTEM_CONNECTIVITY_AUDIT_V2.md` | 2026-07-18/22 | 9, 10 (tangential) | Product/workflow connectivity registers, not security documents — only tangentially touch capability 9/10 (event-wiring completeness, not security anomaly detection). Orthogonal to this matrix, listed for completeness. |

**Cross-cutting fact, verified independently via direct `grep` across the entire `docs/` tree
(not just the files above):** the phrases **"AI Governance Layer,"** **"Data Classification
Engine,"** and **"Response Firewall"** do not appear anywhere in this project's documentation
before the Blueprint itself. **"Trust Boundary"** appears exactly twice as a specific technical
concept (not a generality): once narrowly (`P0_FIX_VERIFICATION.md`, describing the
system/user-message role distinction `prompt_guard` relies on), and once as an explicit **negative**
statement (`PUBLIC_SECURITY_CLAIMS.md`: SEC-004 means there is *not* "an independently-enforced
trust boundary"). This is the clearest single piece of evidence for Phase 3 below.

---

## Part 2 — Capability Status (Blueprint §1.9, current state)

| # | Capability | Status | Evidence | Gap vs. Blueprint |
|---|---|---|---|---|
| 1 | Auth & authorization | 🟡 Partially implemented | Supabase Auth (JWT) delegated login works; SEC-001 ownership pattern closed (24/24 mutation endpoints). `PermissionService`/`UsageService` exist and are live for some features. | No single source of truth (`ENTITLEMENT_AUDIT_PHASE1.md`: 5 overlapping mechanisms at time of writing, one confirmed dormant since inception). Auth itself is delegated to Supabase, not owned (Blueprint 1.3 implies Vindex mediates all access — true for data, not for the identity layer itself, which is an accepted, disclosed architectural choice). |
| 2 | Data classification & protection | 🟡 Partially implemented | AES-256-GCM field encryption for JMBG/PIB (`security/crypto.py`); legal-basis tracking per client record. | No systematic classification scheme — protection is per-field, ad hoc, and **inconsistent for the same value** (SEC-032: `klijenti.pib_encrypted` encrypted, `fakture.klijent_pib` plaintext). No sensitivity tiers, no registry. SEC-032 already proposes a "PII field registry" but it's explicitly "not urgent standalone." |
| 3 | Case/document-level access control | 🟡 Partially implemented, functionally correct | SEC-001 full sweep: all 24 `{predmet_id}`-scoped mutation endpoints ownership-checked. | Architecturally fragmented — 3 independently-invented mechanisms, ~18 call sites (`AUTHORIZATION_PATTERN_RECOMMENDATION.md`), consolidation **designed, not implemented**. Zero independent DB-level enforcement (SEC-004: service-role key bypasses RLS entirely) — 100% app-layer discipline, no defense-in-depth at the data-store boundary. |
| 4 | AI Governance Layer | ❌ Documented but missing as a unified capability | Three real, uncoordinated controls exist: `security/prompt_guard.py` (input-side, all 130 OpenAI call sites, SEC-003 closed), `services/quality_gate.py` (output-side, drafting only, confidence≥0.85 + lawyer sign-off), `shared/genome_validator.py` (citation plausibility, weak, SEC-012 open). No shared policy engine, no per-data-classification AI-access decision point, no single place that answers "may this AI model see this data." | This is the largest true gap against the Blueprint's headline requirement (§1.3: "Nijedan AI model nema direktan pristup podacima. Pristup uvek odobrava Vindex AI"). See Program 1, Part 3. |
| 5 | Prompt-injection / LLM-attack defense | ✅ Implemented (input-side) | SEC-003 closed 2026-07-23 — central OpenAI SDK patch, all 130 call sites, 12 regression tests, zero-network-call proof for blocked injections. | Residual, explicitly disclosed boundary: does not catch "plausible-sounding false content in an otherwise-legitimate document" (STRIDE Genome §1) — a detection-class limit, not a missing control. |
| 6 | Forensic audit of AI decisions | 🟡 Partially implemented | Genome refreshes logged via `audit_immutable`; Trust Layer v1 (confidence + evidence-basis labels) live for 5/6 planned items. | Repudiation is "the least-covered STRIDE category" outside Genome (STRIDE §7.1) — drafts, billing entries, RAG retrievals are not hash-chained. `verify_genome()` fail-open bug (`KNOWN_RELIABILITY_RISKS.md`). The chain-integrity verifier itself was unverified/buggy for 2.5 weeks (`AUDIT_CHAIN_INCIDENT_2026-07-24.md`) before its first real drill. |
| 7 | Controlled use of external AI models | 🟡 Partially implemented | OpenAI is the sole external LLM; input-controlled (Cap 5), partially output-controlled (Cap 4's quality_gate, drafting only), partially cost-controlled (rate limiting ~70% route coverage per SEC-010/011). | No formal "which model/vendor may process which data classification tier" policy — depends directly on Cap 2 and Cap 4 not existing yet. |
| 8 | Backup & recovery | 🟡 Partially implemented, partially unverified | DRP exists (2026-07-24) with explicit RTO/RPO targets; first backup-restore drill run once, found+fixed 2 real bugs. SEC-031 (auth.users cascade) fully closed, production-verified — the project's one 9-stage-complete finding. | PITR status **unconfirmed** — real RPO may be 24h, not the stated 15min, pending a founder dashboard check the DRP itself flags as blocking. No uptime monitoring wired (detection gap, `DRP §4.5`). Drill has run once, not yet on the recommended monthly cadence. SEC-033/Data Integrity Initiative shows the same *class* of gap (missing FK/cascade discipline) recurring elsewhere, unscoped. |
| 9 | Anomaly / abuse detection | 🟡 Partially implemented, recently revived from fully dead | Per-user rate limit + behavioral anomaly-detection middleware **had never executed once since being written** (`request.state.user_id` never set) — found and fixed SEC-005 round 2, code/test-verified, **not yet production-verified**. | No behavioral/ML-based anomaly detection beyond rate-limit thresholds exists. Production verification (does it actually fire against real traffic) is an open, disclosed item. |
| 10 | Traceability of critical operations | 🟡 Partially implemented | `audit_immutable` (hash-chained, DB-trigger-enforced immutability) covers predmet/dokument/client CRUD + admin actions; `login_failed` now logged (SEC-017 closed 2026-07-24). | `login_success` remains architecturally invisible (delegated to Supabase Auth, disclosed limitation). Drafts/billing/RAG retrievals not hash-chained (same gap as Cap 6). `api_key_rotation` audit action defined, zero call sites (SEC-030, open P3). |

**Summary: 1 of 10 capabilities (#5) is fully implemented. 8 are partially implemented with
specific, evidenced gaps. 1 (#4, AI Governance Layer) is a genuine, named architectural absence —
the closest existing precedent is a business-logic rule (Core Consolidation Faza 3), not a
control layer.**

---

## Part 3 — Architectural Gaps → Future Programs

These are gaps *the Blueprint's existence itself surfaces* — distinct from the ~15 open items
already tracked in the Gap Register (which are implementation bugs against capabilities that
already exist in some form). A Program here means "this capability does not exist as a coherent
thing yet," not "this control has a bug."

| Program | Capability | Current state | Evidence of absence | Risk if unaddressed | Criticality | Regression risk of building it | Complexity | Verification strategy |
|---|---|---|---|---|---|---|---|---|
| **P1 — AI Governance Layer** | 4 (primary), 5/6/7 (extends) | 3 uncoordinated controls (prompt_guard, quality_gate, genome_validator), no unifying policy engine | Zero hits for "AI Governance Layer" as a named concept anywhere pre-Blueprint; `PUBLIC_SECURITY_CLAIMS.md` forbids the claim today | AI calls proceed today based on per-feature ad hoc rules, not a stated, auditable policy — cannot answer "why did/didn't this AI model see this data" as a single question | High — this is the Blueprint's headline requirement (§1.3) | Medium — must not break the 130 already-guarded call sites; should wrap/compose existing `prompt_guard`/`quality_gate`, not replace them | Large | Contract tests per data-classification tier (once P2 exists) asserting AI call denial/redaction; regression suite re-run against all 130 existing call sites |
| **P2 — Data Classification Engine** | 2 (primary), feeds P1 | Ad hoc field encryption only; SEC-032's "PII field registry" proposed, unbuilt | No sensitivity-tier scheme anywhere; SEC-032 gap register entry is the closest prior art | P1 cannot make principled AI-access decisions without knowing what's sensitive; SEC-032-class inconsistencies (same value, different protection per table) likely recur | Medium-High — blocks P1 | Low — additive (a registry + lookup), does not change existing storage/encryption | Medium | Registry completeness check against `security/crypto.py`'s existing encrypted-field list + all `klijenti`/`predmeti`/`fakture` schema columns; must not regress SEC-009 (bulk-import encryption path) |
| **P3 — Unified Access Control / Trust Boundary Consolidation** | 1 & 3 (primary) | Functionally correct (SEC-001 closed) but architecturally fragmented (~18 call sites, 3 mechanisms); 5 overlapping entitlement mechanisms per `ENTITLEMENT_AUDIT_PHASE1.md` | `AUTHORIZATION_PATTERN_RECOMMENDATION.md`'s own design, not yet implemented; `PUBLIC_SECURITY_CLAIMS.md`'s explicit "no independently-enforced trust boundary" admission | Lowest-cost future SEC-001-v2 recurrence vector — the same human-inconsistency root cause is still live at every new endpoint | High — foundational, and the fix is already fully designed | Low — the recommendation doc explicitly designs for this (dependency, not middleware; raw-function split for `api.py`'s non-`Depends()` style) specifically to minimize regression | Medium (mostly migration of existing correct logic, not new logic) | Per-file before/after regression test, same discipline as SEC-001 fix; full 1,900+ suite re-run after each file migrated, not batched |
| **P4 — Complete Forensic Traceability** | 6 & 10 (primary) | `audit_immutable` covers CRUD+auth+admin only; drafts/billing/RAG retrievals uncovered; chain verifier itself was silently buggy for 2.5 weeks | STRIDE §7.1 "least-covered STRIDE category"; `AUDIT_CHAIN_INCIDENT_2026-07-24.md`; `KNOWN_RELIABILITY_RISKS.md`'s fail-open `verify_genome()` | A dispute over "what did the AI actually generate/bill" relies on application logs, not tamper-evident records, for 3 of the app's highest-stakes outputs | Medium — no active exploit, but directly undermines Blueprint Goal 4 (Complete Auditability) | Low — additive logging to existing hash-chain mechanism | Medium | Extend `scripts/verify_backup_restore.py`-style drill to cover new chained categories; fix `verify_genome()`'s fail-open path with a dedicated regression test forcing all 5 sub-checks to fail |
| **P5 — Operational Resilience & Detection** | 8 & 9 (primary) | DR policy exists, unverified in 2 material ways (PITR status, no uptime monitoring); anomaly detection just revived from total silent failure, unverified in production | `DISASTER_RECOVERY_PLAN.md` §2.1/§4.5; SEC-005 round 2 | Detection depends on manual observation/user reports today; a real per-user abuse pattern would not be caught until a human notices | Medium — mostly a verification/ops gap, not a missing mechanism | Very low — infra/config work (PITR confirmation, UptimeRobot-class monitor), not app-logic change | Low | Founder confirms PITR in Supabase Dashboard + records in DRP §8; live production check that SEC-005's fixed middleware fires against real traffic |

---

## Part 4 — Implementation Dependency Graph

```
                         ┌─────────────────────────────┐
                         │  P5 — Operational Resilience │   (independent — runs in
                         │  & Detection (Cap 8, 9)       │    parallel with everything;
                         └─────────────────────────────┘    lowest coupling, lowest risk)

  ┌───────────────────┐      ┌────────────────────────┐      ┌──────────────────────┐      ┌────────────────────────┐
  │ P3 — Unified       │ ───► │ P2 — Data              │ ───► │ P1 — AI Governance    │ ───► │ P4 — Complete Forensic  │
  │ Access Control /   │      │ Classification Engine  │      │ Layer                 │      │ Traceability            │
  │ Trust Boundary      │      │ (Cap 2)                │      │ (Cap 4, extends 5/6/7)│      │ (Cap 6, 10 — extends to │
  │ (Cap 1, 3)          │      │                        │      │                       │      │  cover P1's decisions)  │
  └───────────────────┘      └────────────────────────┘      └──────────────────────┘      └────────────────────────┘
```

**Ordering rationale:**

1. **P3 first.** Already fully designed (`AUTHORIZATION_PATTERN_RECOMMENDATION.md`), lowest
   complexity, and closes the standing "next SEC-001 could happen anywhere" risk before anything
   else is layered on top of the access-control foundation. Every other Program reads/writes data
   through this layer.
2. **P2 before P1.** The Blueprint's own stated pipeline (§1.3) is classify → protect → control →
   audit → *then* AI access. Building an AI Governance policy engine (P1) before data has
   classification tiers means the policy engine has nothing principled to enforce — it would
   default to the same ad hoc, per-feature rules it's meant to replace.
3. **P1 depends on P2 and benefits from P3.** The single largest build in this graph — a policy
   engine wrapping the existing `prompt_guard`/`quality_gate`/`genome_validator` controls, gated by
   P2's classification tiers and P3's access-control identity.
4. **P4 after P1.** Once P1 exists, forensic audit must extend to cover *its* decisions
   ("why did the AI Governance Layer allow/deny this"), not just the pre-existing Genome-refresh
   audit trail. Extending `audit_immutable` coverage to drafts/billing/RAG (already a known,
   scoped gap) can start independently but its AI-Governance-specific extension gates on P1.
5. **P5 is fully parallel.** Infra/ops work (PITR confirmation, uptime monitoring, production
   verification of the already-fixed anomaly detector) has no code dependency on P1–P4 and the
   lowest regression risk of the five — it should not wait for anything above, and nothing above
   waits for it.

**This dependency order, not a full re-implementation, is Phase 4's deliverable.** Per the
Blueprint's own governing rule (Part II, final note) and the founder's explicit instruction, no
Program above is authorized for implementation by this document. Program 1 (the Blueprint's own
named next step) requires a separate, explicit review and go-ahead before any code is written —
consistent with `FINDING_LIFECYCLE.md`'s stage-4/5 gates (Remediation Candidate → Architecture
Approved, requiring independent peer review and a Production Reality Gate) already governing every
other significant change in this project.

**Revision, 2026-08-01, same day:** the founder correctly challenged the P3 → P2 → P1 → P4
sequencing above — if P1 is the central orchestrator, its contract requirements should shape P2's
(and P3's AI-facing) interfaces, not the other way around. Re-examining Vindex's own data flow
confirmed this: Classification is a stage **inside** the Governance pipeline, not an independent
upstream program, so it cannot be responsibly implemented before P1 is at least specified. Access
Control (P3) remains genuinely independent — ownership/entitlement resolve at the API layer,
before any AI call is constructed — so it is unaffected by this revision. **Revised order:**
(1) `docs/architecture/PROGRAM_1_AI_GOVERNANCE_ARCHITECTURE_SPEC.md` — Program 1 specification
only, zero code; (2) implement P3 (parallel with step 1); (3) implement P2, now built to the exact
contract §6 of that spec defines; (4) implement P1 itself; (5) implement P4. P5 unchanged, still
fully parallel. Full reasoning: see that document's header section.

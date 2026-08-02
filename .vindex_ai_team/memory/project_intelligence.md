# Project Intelligence Snapshot

**Purpose:** the mental map an agent needs before reasoning about any change, so it doesn't start
from zero every time. This file answers "what does the system currently look like," not "what
happened" (`project_memory.md`) or "what's the current priority" (`current_state.md`) or "what
specific risks exist" (`known_risks.md`) — those files stay separate on purpose; this one is the
map, they are the history/status/risk layers on top of it.

**Last verified against actual code:** 2026-08-02, via the full-codebase forensic implementation
audit. Treat any claim here as accurate as of that date — re-verify against code before relying on
a specific number or file path for anything consequential, the same evidence-over-assumption
discipline this whole project applies to itself.

## Stack
FastAPI (Python) backend, Supabase (Postgres + Auth + Storage), Pinecone (vector DB), OpenAI
(chat/embeddings/audio/Realtime), Cohere (reranking — currently undisclosed as a subprocessor,
SEC-051), Render/Railway hosting (host uncertain, see SEC-025), gunicorn + Uvicorn workers.

## Scale, as last measured
~90 files under `routers/`, ~516 routes there + ~60 in `api.py` + ~20 in `klijenti/router.py` ≈
**596 total HTTP endpoints**. `api.py` itself is ~5,000+ lines (the oldest, largest single file —
many newer features live in `routers/*.py` instead). 148 Postgres tables, 143 with RLS enabled (2
without — SEC-060's siblings). ~69 migration files under `migrations/`, plus the older
`supabase_setup.sql` as the original schema source.

## Core product concepts (the things Core Consolidation already unified — do not re-fragment these)
- **Case Genome** (`routers/case_dna.py`, `services/legal_reasoning_engine.py`) — the single
  source-of-truth case model: AI-extracted legal theory, strength score, contradictions, missing
  evidence. Read by Cockpit, Multi-Agent Engine, CIO, Health Index.
- **Legal Reasoning Engine** — Phase 0 implemented (per `docs/architecture/LEGAL_REASONING_ARCHITECTURE.md`),
  identity-based citation verification, not yet wired into the primary Genome pipeline (SEC-012).
- **Entitlement system** — `shared/permissions.py::PermissionService` (can this account use this
  feature at all) + `shared/usage.py::UsageService` (credit/budget remaining) — deliberately
  separate axes, correctly designed.
- **Audit system** — `shared/audit_immutable.py` — hash-chained, trigger-protected, append-only.
  Coverage is narrow (~24 action types, ~4 path prefixes of the audit *middleware* specifically —
  see `shared/audit.py` vs. the immutable logger, two different mechanisms).
- **AI Governance Layer (Program 1)** — specified, NOT implemented. Currently Stage 4 of the
  Finding Lifecycle. See `docs/architecture/PROGRAM_1_AI_GOVERNANCE_ARCHITECTURE_SPEC.md`.
- **klijenti/ (CRM) module** — the one genuinely correct RBAC implementation in the codebase
  (`klijenti/permissions.py`), field-level encryption for JMBG/passport/PIB, per-client audit log.
- **kancelarija (firm) system** — multi-seat firm membership, `routers/kancelarija.py`, real and
  tenant-scoped, distinct role vocabulary from `klijenti/permissions.py` (a known inconsistency,
  SEC-041).
- **Smart Intake** — encrypted document ingestion pipeline with AI entity extraction, distinct from
  the older, less-protected client-portal upload path (SEC-056).
- **Drafting Engine** — 3 deliberately-separate mechanisms, frozen pending pilot comparison per
  `VINDEX_CORE_CONSOLIDATION.md` §1.4 — this is an intentional, documented exception to the
  single-owner rule, not an oversight; do not "fix" it without checking that section first.

## Critical data flows
1. **Document upload → OCR → Classification (informal) → embed → Pinecone + Postgres storage →
   Case Genome extraction.** PII scrubbing (`main.py::_skini_pii`) covers 4 call sites, numeric
   identifiers + email + heuristic addresses only — **not** person names, and **not** the Genome
   extraction path itself (SEC-006).
2. **Auth**: login/password/MFA/session entirely delegated to Supabase Auth client-side
   (`static/vindex.js`) — this backend only ever verifies an already-issued JWT
   (`shared/deps.py::get_current_user`). This backend cannot prove anything about the login flow
   itself, only about what happens after a token exists.
3. **Every DB access** goes through one Supabase client built with the service-role key
   (`shared/deps.py:29,72-81`) — RLS is inert for 100% of application traffic; tenant isolation is
   100% hand-written `.eq("user_id", ...)` discipline (SEC-004, standing architectural fact).
4. **Every OpenAI chat-completions call** (~130 sites, 53 files) passes through one monkeypatched
   chokepoint (`shared/ai_client.py::_patch_prompt_guard`) — structurally comprehensive
   prompt-injection coverage for this one surface. Embeddings/audio/Realtime API are separate
   surfaces, not yet covered by an equivalent chokepoint as of the last audit (Program 1 §1.1
   specifies the fix, not yet implemented).

## Security posture summary (see `docs/security/FORENSIC_IMPLEMENTATION_AUDIT_2026-08-02.md` for full detail)
Overall score 52/100 as of 2026-08-02. Dominant failure pattern: **narrow, inconsistent application
of an already-correct pattern**, not missing competence — see that audit's executive summary,
worth re-reading before assuming a new finding is a novel problem type rather than the same pattern
recurring in a new place. Two live-severity items outstanding: SEC-037 (exposed key), SEC-038
(profiles RLS gap) — check `memory/current_state.md` for current resolution status before assuming
either is closed.

## Active priorities (check `memory/current_state.md` for the current, up-to-date version — this
section may drift; that file is the one meant to stay current)
As of 2026-08-02: forensic audit remediation (just beginning, per `EXECUTION_STATE/`), Program 1
Stage 4→5 (one targeted re-check away).

## Where the actual detailed truth lives, by topic
| Topic | Source of truth |
|---|---|
| Security findings | `docs/security/SECURITY_GAP_REGISTER.md` |
| Security maturity | `docs/security/SECURITY_MATURITY_DASHBOARD.md` |
| Full implementation audit | `docs/security/FORENSIC_IMPLEMENTATION_AUDIT_2026-08-02.md` |
| Trust architecture / governing principles | `docs/architecture/VINDEX_TRUST_ARCHITECTURE_BLUEPRINT.md` |
| AI Governance Layer design | `docs/architecture/PROGRAM_1_AI_GOVERNANCE_ARCHITECTURE_SPEC.md` |
| System-wide architecture | `docs/architecture/VINDEX_AI_ARCHITECTURE_BIBLE_v1.0.md` |
| Consolidation decisions | `docs/architecture/VINDEX_CORE_CONSOLIDATION.md` |
| Public security claims (what can be said externally) | `docs/security/PUBLIC_SECURITY_CLAIMS.md` |

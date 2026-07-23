# Vindex AI — Security Roadmap

**Date:** 2026-07-23
**Source:** `SECURITY_GAP_REGISTER.md` (30 findings). This document sequences them into P0–P3. Every item states ROI, Risk Reduction, and Complexity — these are judgment calls made from the evidence in the Gap Register, not a formula.

**Sequencing principle:** fix confirmed, live, evidence-based issues before architectural or defense-in-depth work — same discipline as the rest of this project's engineering practice this cycle (measure, confirm, fix the smallest correct thing, verify, move on).

---

## P0 — Immediate (confirmed live/critical, or trivial-and-high-value)

| ID | Item | ROI | Risk Reduction | Complexity |
|---|---|---|---|---|
| SEC-031 | **Impact analysis first (no schema change yet)** on the `ON DELETE CASCADE` chain from `auth.users` through `predmeti`/`klijenti`/`fakture`/evidence/etc. — confirm full cascade graph, confirm whether the GDPR endpoint can trigger it, confirm production migration state, then choose RESTRICT / soft-delete / archive-anonymization | Very High | Addresses a potentially catastrophic, irreversible legal/financial record-loss path — reprioritized above SEC-002 per founder review, since it changes the whole security picture, not just the GDPR-message question | Analysis: Small. Fix: Medium–Large (pending chosen strategy) |
| SEC-001 | ~~Fix ownership check on `predmet_beleske`/`predmet_istorija` insert; audit and fix any sibling endpoints with the same gap~~ **DONE 2026-07-23** — fixed, full 24-endpoint sweep completed (no siblings found), 6 regression tests added, commit pending | Very High | Closed a confirmed, reproducible cross-tenant data-injection vulnerability | Low (isolated patch), full sweep took longer than the patch itself but found nothing else |
| SEC-011 | Register `SlowAPIMiddleware` so `default_limits` actually applies app-wide | Very High | Potentially closes rate-limiting gap on ~30% of all routes with a one-line change | Trivial |
| SEC-003 | Wrap all GPT call sites in existing `prompt_guard.wrap_for_ai()`; extend `analyze()` blocking to document-ingestion paths | Very High | Closes the largest AI-safety gap using code that already exists | Low–Medium |
| SEC-002 | Founder decision + fix on GDPR erasure scope (real anonymization vs. corrected user-facing claim). Minimum safe message fix proposed in `docs/security/SEC002_DATA_RETENTION_ANALYSIS.md` §4, ready to apply independent of the larger retention-policy question | Very High | Removes a materially false compliance claim; legal exposure | Medium (decision) + Small–Medium (implementation) |
| SEC-009 | Route bulk CSV/XLSX client import through `encrypt_field()`, matching the manual-entry path | High | Closes a real "NIKAD plaintext" policy violation | Low |
| SEC-008 (instance) | Fix the confirmed unescaped `innerHTML` in the court-portal widget | High | Closes a confirmed, exploitable XSS instance | Low |

**Why these seven:** each is either a confirmed live issue (SEC-001, SEC-002, SEC-008-instance, SEC-009), a fix so cheap relative to its potential impact (SEC-011, SEC-003) that sequencing it later has no justification, or — SEC-031 specifically — a newly-discovered risk whose blast radius (irreversible loss of legal/financial records) is high enough to require analysis before anything else proceeds, even though the analysis itself is the only thing authorized right now. None require architectural change to *start*; SEC-031's eventual fix may.

---

## P1 — Near-term (real gaps, credible exploit path, moderate effort)

| ID | Item | ROI | Risk Reduction | Complexity |
|---|---|---|---|---|
| SEC-005 | Migrate rate limiter + anomaly detection to Redis (already a dependency) | High | Restores real effective rate limits and anomaly-baseline accuracy across all 4 workers | Medium |
| SEC-010 | Add `@limiter.limit()` to all AI-cost-bearing and PII-touching routes currently undecorated (klijenti/router.py, legal_reasoning.py, case_dna.py, health_index.py, intelligence_timeline.py) | High | Closes direct cost-abuse and brute-force surface on sensitive routes | Low |
| SEC-006 | Disclose PII-masking scope accurately now (docs/claims); scope NER-based name/address masking as separate follow-on work | Medium (disclosure) / High (eventual fix) | Prevents overstated privacy claims now; real exposure reduction later | Low (disclosure) / Large (fix) |
| SEC-007 | Add decompressed-size check before DOCX parsing | High | Closes a real, concrete DoS vector | Low |
| SEC-008 (sweep) | Scripted sweep of all ~419 `.innerHTML =` sites for missing `escHtml`/`_htmlEsc` | High | Closes the XSS class beyond the one confirmed instance | Medium |
| SEC-013 | Apply `FOR UPDATE SKIP LOCKED` to the event dispatch loop (pattern already proven in `intake_worker.py`) | Medium | Eliminates duplicate event processing under concurrent workers | Low–Medium |
| SEC-017 | Wire login success/failure audit logging | Medium | Enables brute-force/credential-stuffing detection from this system's own logs | Low–Medium |
| SEC-018 | Verify and clean up legacy `jmbg_mb` plaintext column | Medium | Closes a possible live-plaintext-PII gap | Low |
| SEC-020 | Pin all dependency versions exactly; add a lock file | Medium | Prevents uncontrolled drift on security-critical libraries | Low |
| SEC-023 | Correct `security/crypto.py` documentation to reflect actual auth delegation to Supabase | Low (docs) | Prevents an inaccurate internal/public claim | Trivial |
| SEC-025 | Confirm and correct DR runbook host references (Render vs. Railway) | High (incident-response value) | Prevents a misdirecting runbook during a real incident | Trivial |

---

## P2 — Medium-term (real but bounded, mitigated, or requires larger scoping)

| ID | Item | ROI | Risk Reduction | Complexity |
|---|---|---|---|---|
| SEC-012 | Integrate `services/legal_reasoning_engine.py`'s identity-based citation verification into the live Genome pipeline | High | Closes the legal-hallucination gap properly rather than patching the heuristic checker | Large (integration project, not a patch) |
| SEC-014 | Reduce CSP `'unsafe-inline'` reliance (migrate `onclick=` handlers to `addEventListener`) | Medium | Restores CSP as a real XSS mitigation, not just a present-but-weak header | Large |
| SEC-015 | Magic-byte file validation + clean error handling on parse failure | Medium | Improves robustness against MIME spoofing/malformed files | Low |
| SEC-016 | Confirm original files are never re-served as downloads; add AV scanning if they are | Medium | Closes malware-distribution risk if the precondition holds | Medium |
| SEC-019 | Enable RLS + deny-by-default policy on `zakoni_monitoring`/`case_benchmarks` | Low (already mitigated by GRANTs) | Defense-in-depth | Trivial |
| SEC-021 | Add DB ping to `/health` | Medium | Faster incident detection | Low |
| SEC-022 | Set and verify explicit JWT audience claim | Low–Medium | Closes a theoretical cross-project token-reuse gap | Low |
| SEC-024 | Implement multi-key lookup for encryption key rotation | Medium | Enables key rotation without a full re-encryption event | Medium |
| SEC-026 | Remove/relocate hardcoded JWKS fallback key | Low–Medium | Removes stale-key denial-of-auth risk | Low |
| SEC-032 | Build a PII field registry (per-field policy: encrypted/hashed/searchable/retention/export) and fix `fakture.klijent_pib` plaintext-vs-`klijenti.pib_encrypted` inconsistency as its first application | Medium | Closes a confirmed non-uniform-protection gap on a real identifier, and prevents the same inconsistency recurring elsewhere | Medium (registry) / Small (this one field) |

---

## P3 — Backlog (low severity, or requires a product/scope decision first)

| ID | Item | ROI | Risk Reduction | Complexity |
|---|---|---|---|---|
| SEC-027 | Add PDF page-count cap | Low | Defense-in-depth on an already-mitigated risk | Low |
| SEC-028 | Fix or remove `.doc` handling inconsistency | Low | Robustness only | Trivial |
| SEC-030 | Wire `api_key_rotation` audit logging into a real rotation runbook | Low | Improves traceability of a currently-manual process | Low |
| SEC-029 | Intra-tenant RBAC | N/A pending product decision | N/A | N/A — confirm product intent (multi-attorney firms) before scoping any work |

---

## What this roadmap deliberately does not do

It does not sequence SEC-004 (total blast radius of the service-role key) as a single ticket — that finding is architectural, not a patch, and is mitigated over time by closing every SEC-001-class gap plus operational practices (key rotation cadence, access logging) rather than by one change. It is tracked in the Gap Register as ongoing, not scheduled into a single phase.

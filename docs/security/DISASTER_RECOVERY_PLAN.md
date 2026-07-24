# Vindex AI — Disaster Recovery Plan (DRP)

**Status:** Official policy document — Celina 5 (SecOps, Operational Readiness & Observability), 2026-07-24
**Supersedes:** `scripts/dr_runbook.py`'s informal RPO/RTO comments (24h/4h) — this document is now the
single source of truth for recovery targets. The script remains the *automated verification tool*
for the procedures defined here (see §6).
**Owner:** Founder (sole operator at time of writing — see §5 for the single-person-team caveat).

---

## 1. Purpose and Scope

This plan defines how Vindex AI recovers from a loss of availability or integrity of its
production infrastructure: the application host (Render.com), the database (Supabase/Postgres),
and the two external AI dependencies (OpenAI, Pinecone). It does **not** cover office/workstation
disaster recovery, which is out of scope for a hosted SaaS product.

---

## 2. Recovery Targets

| Target | Definition | Value | Status |
|---|---|---|---|
| **RPO** (Recovery Point Objective) | Maximum acceptable data loss, measured in time since the last durable, restorable snapshot | **≤ 15 minutes** | **POLICY TARGET — requires Supabase Point-in-Time Recovery (PITR) to be active. See §2.1 for current confirmed state.** |
| **RTO** (Recovery Time Objective) | Maximum acceptable time from incident detection to restored service | **≤ 2 hours** | **POLICY TARGET — achievable with the procedures in §4, contingent on the caveats in §4.4.** |

### 2.1 Honest current-state caveat (read before treating RPO ≤ 15 min as a settled fact)

This project's own security documentation discipline (`docs/security/SECURITY_GAP_REGISTER.md`,
`PUBLIC_SECURITY_CLAIMS.md`) is explicit that claims must be evidence-based, not aspirational. In
that spirit:

- **What is confirmed from the repository alone:** Supabase is a managed Postgres provider with
  automatic backups on paid tiers. The previous DR runbook (`scripts/dr_runbook.py`, written before
  this policy) assumed **daily** backups and stated an informal RPO target of 24 hours — consistent
  with Supabase's **daily backup** tier, not continuous WAL/PITR.
- **What is NOT confirmed from the repository:** whether the live Supabase project has **Point-in-Time
  Recovery (PITR)** enabled. PITR is a paid-tier feature (Supabase Pro/Team and above) that continuously
  archives the write-ahead log, enabling restoration to *any point in time* within a retention window
  (typically down to the minute). Without PITR, the true RPO is bounded by the backup snapshot
  interval — if that interval is 24 hours, the true RPO is up to 24 hours, not 15 minutes, no matter
  what this document says the target is.
- **This is a billing/plan decision, not a code decision.** It cannot be verified by reading this
  repository — it requires the founder to confirm in the Supabase Dashboard (Project Settings →
  Database → Backups) whether PITR is enabled and what its retention window is.
- **Action item (blocking the RPO ≤ 15 min claim from being a verified fact rather than a target):**
  Founder to confirm PITR status and record the result in §8 (Verification Log) of this document.
  Until that entry exists, treat the effective RPO as **24 hours** (the confirmed daily-backup floor)
  for incident-response planning purposes, and the 15-minute figure as the policy this project is
  committing to reach, not a promise already met.

This caveat is deliberately kept prominent rather than buried — an incident responder who reads only
the RPO number in §2 without this context would make a false assumption at exactly the moment
accuracy matters most.

### 2.2 RTO ≤ 2 hours — feasibility

Unlike RPO, RTO is primarily a *procedural* target (how fast can the team execute the recovery
steps), not a billing-tier dependency. The step-by-step procedures in §4 are designed to fit inside
2 hours for the P0 (total outage) scenario, based on the component-level time estimates already
validated in `scripts/dr_runbook.py`'s prior 1–2 hour P0 estimate. This target is **achievable with
current tooling**, provided:
- The founder (or whoever is on-call) is reachable and has the required dashboard access (§5).
- The Supabase restore itself does not exceed ~30–45 minutes (consistent with Supabase's own
  published restore-time guidance for typical database sizes at Vindex's current scale).

---

## 3. Recovery Point Objective — what "15 minutes of data" actually means here

If PITR is confirmed active (§2.1), a 15-minute RPO means: in the worst case, the following
categories of data created or modified in the 15 minutes immediately before an incident could be
lost on restore:

- New/updated `predmeti`, `klijenti`, `predmet_dokumenti`, `billing_entries` rows.
- New `audit_immutable` entries (the hash-chain itself is still verifiable up to the restore point —
  §4.3 explains why a chain break at the exact restore boundary is *expected*, not evidence of
  tampering). See also `docs/security/AUDIT_CHAIN_INCIDENT_2026-07-24.md` — the chain-verification
  tool itself had two bugs (a timestamp-formatting false positive and a since-fixed concurrent-write
  race at seq=32) found by this DRP's own §6 drill; both are resolved, but read that document before
  treating any *new* `verify_chain_integrity()` failure as automatically real — confirm it isn't a
  variant of the same class of false positive first.
- In-flight AI Genome/Draft generations not yet written back to `predmeti.case_dna`.

Anything already persisted to Pinecone (vector index) or already sent to OpenAI is **not** subject
to the Postgres RPO — those are separate systems with their own durability (Pinecone: managed,
replicated; OpenAI: stateless, no data at rest on Vindex's side of that boundary).

---

## 4. Recovery Procedures

Each scenario below assumes the incident has already been **detected** (see §4.5) — the clock for
RTO starts at detection, not at the moment the underlying outage began.

### 4.1 Scenario P0 — Total outage (Render AND Supabase both unreachable)

This is the worst case and the one the 2-hour RTO target is calibrated against.

| Step | Action | Owner | Target time (cumulative) |
|---|---|---|---|
| 1 | Confirm scope: check `https://status.render.com` and `https://status.supabase.com`. If both show incidents, this is a P0, not a code bug — do not start debugging application code. | On-call (founder) | 0–5 min |
| 2 | Post an internal status note (even a personal note/Slack-to-self) with start time — this becomes the RTO clock reference for the post-incident review in §7. | On-call | 5 min |
| 3 | If Render is down: Render Dashboard → the Vindex service → "Manual Deploy" → redeploy the latest `main` commit, or wait for Render's own recovery if the outage is platform-wide (redeploying during a platform-wide Render outage will not help — check status page first). | Founder | 5–15 min |
| 4 | If Supabase is down: Supabase Dashboard → Project → confirm outage scope. If project-specific corruption/deletion (not a platform outage), proceed to §4.2's restore procedure. If platform-wide, wait for Supabase's own recovery — do not attempt a restore against a still-down platform. | Founder | 15–45 min (parallel with step 3) |
| 5 | Once both platforms report healthy: run `python scripts/dr_runbook.py --quick` from a machine with the production `.env` (or Render Shell) to confirm connectivity to Supabase, OpenAI, and Pinecone before declaring recovery. | Founder | +5 min |
| 6 | Run `python scripts/verify_backup_restore.py` (see §6) against the restored database to produce a timestamped, signed verification report — this is the evidence that the restore is not just "connected" but *structurally sound*. | Founder | +10–15 min |
| 7 | Run the audit chain integrity check: `GET /api/admin/security/audit-verify` (or `python scripts/dr_runbook.py --check chain`). A chain break exactly at the restore boundary is expected (§4.3) — anywhere else is a tampering signal requiring separate investigation, not a "recovery failed" signal. | Founder | +5 min |
| 8 | Send the incident notification (template in `scripts/dr_runbook.py`'s `INCIDENT_EMAIL_TEMPLATE`, GDPR čl. 33-34 / ZZPL čl. 52-53 compliant) if the incident involved any data loss or exceeded 1 hour of downtime. | Founder | +10 min |
| 9 | Declare recovery complete. Total elapsed should be within the 2-hour RTO target for a project at Vindex's current scale; if it exceeds 2 hours, that overage itself becomes an input to §7's post-incident review (the target may need revisiting, or the procedure has a gap). | Founder | ≤ 120 min |

### 4.2 Scenario P1 — Database-only outage or corruption (Supabase down or data corrupted, Render OK)

1. Supabase Dashboard → Project Settings → **Backups**.
2. If PITR is active: select "Restore to point in time" and choose the timestamp immediately
   before the incident (from the internal status note in §4.1 step 2, or from the last known-good
   entry in `audit_immutable`/application logs).
3. If only daily backups are active (PITR not confirmed — see §2.1): select the most recent daily
   snapshot. **This is where the true RPO gap between "15 minutes" and "up to 24 hours" becomes
   concrete** — communicate this honestly in the incident notification if it applies.
4. Point the application at the restored database (Supabase restores in-place for the same
   project in most cases; a distinct restore-to-new-project would additionally require updating
   `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` in Render's environment variables and redeploying).
5. Run §4.1 steps 5–7 (connectivity check, backup-restore verification, audit chain check).
6. Target: 30–60 minutes (well inside the 2-hour RTO).

### 4.3 Why a chain break at the restore boundary is expected, not a tampering alarm

`shared/audit_immutable.py`'s hash-chain (`verify_chain_integrity`) links every audit entry to the
one before it. A database restore to timestamp T necessarily truncates any entries written after T.
The **next** entry written after the restore will have a `prev_hash` pointing to the last entry
*before* the restore (correct), but if any entries existed *after* T before the crash and are now
gone, that is data loss (expected, within RPO), not chain tampering. Tampering looks different: an
entry whose `entry_hash` does not match its own recomputed hash, or a `prev_hash` mismatch **in the
middle** of an otherwise-continuous sequence that was never touched by a restore. `scripts/dr_runbook.py
--check chain` and `GET /api/admin/security/audit-verify` both report the exact `seq` number where a
break occurs — cross-reference that number against the restore timestamp before concluding tampering.

### 4.4 Known limitations of the RTO target

- **Single operator.** At time of writing, the founder is the sole person with Render/Supabase
  dashboard access (see §5). A 2-hour RTO assumes the founder is reachable within a reasonable
  window of incident detection. If unreachable (illness, travel without connectivity), RTO for
  that incident is bounded by reachability, not by the technical procedure. This is a real,
  named risk, not an oversight — see §5 for the mitigation path.
- **External dependency outages.** If OpenAI or Pinecone themselves are down (not Vindex's
  infrastructure), no restore procedure fixes that — Vindex's own RTO target does not apply to
  third-party outages outside its control. The honest response in that case is degraded-mode
  operation (if feasible) or waiting, not a "recovery," and should be communicated as such.

### 4.5 Detection

Vindex currently has no dedicated uptime-monitoring/paging service wired in (confirmed gap — not
claimed otherwise). Detection today relies on:
- Manual/founder observation (using the product, checking `/health`).
- User reports.
- Render/Supabase's own status pages and dashboard alerts (if configured).

**Recommendation (not yet implemented, tracked here rather than silently assumed done):** wire an
external uptime check (e.g. a free-tier UptimeRobot/Better Uptime monitor against `/health`) so
detection does not depend on someone happening to notice. This is explicitly out of scope for this
Celina's code changes (it is a third-party account setup, not a code change) but is recorded here
as the concrete next step for closing the detection gap.

---

## 5. Responsible Parties

| Role | Who (at time of writing) | Responsibilities |
|---|---|---|
| Incident Commander / sole on-call | Founder | Executes §4 procedures, makes the restore-vs-wait call, sends incident notifications |
| Render account owner | Founder | Redeploys, checks platform status, manages env vars |
| Supabase account owner | Founder | Executes restore, confirms PITR status (§2.1 action item) |
| Data Protection contact (GDPR čl. 33-34 / ZZPL čl. 52-53 notifications) | Founder | Same person, different hat — notification template already exists in `scripts/dr_runbook.py` |

**Named risk:** this is a single-person team. There is no secondary on-call. This is stated
explicitly rather than glossed over, consistent with this project's own standing rule against
overstating operational maturity. If/when Vindex adds a second operator, this table — and the
"reachability" caveat in §4.4 — should be the first thing updated.

---

## 6. Automated Verification Tooling

Two scripts implement the checks this plan describes:

| Script | Purpose | Relationship to this plan |
|---|---|---|
| `scripts/dr_runbook.py` | Pre-incident and post-incident **connectivity + configuration** check (Supabase/OpenAI/Pinecone reachability, env vars present, audit chain integrity) | Implements §4.1 steps 5 and 7 |
| `scripts/verify_backup_restore.py` (new, Celina 5) | Simulates and verifies a backup-restore drill, producing a timestamped, checksummed JSON report (`backup_restore_verification.json`) | Implements §4.1 step 6 — the *structural soundness* check that connectivity alone does not cover |

Both scripts are safe to run against production for read-only verification (neither performs a
destructive restore against the live database — an actual Supabase point-in-time restore must be
triggered manually via the Supabase Dashboard, per §4.2, as a deliberate, human-confirmed action;
no script in this repository automates that irreversible step).

**Recommended cadence:** run `scripts/dr_runbook.py --quick` after every deploy (already low-cost),
and `scripts/verify_backup_restore.py` monthly as a scheduled drill, not only during a real incident
— an untested recovery procedure is not a verified one. Record each drill's output in §8.

---

## 7. Post-Incident Review (template — fill in after any real P0/P1 event)

```
Date of incident:
Detected at (UTC):
Detected by / how:
Root cause:
Scenario followed (P0/P1/P2):
Actual RPO experienced (data loss window):
Actual RTO experienced (detection → recovery declared):
Deviations from this plan and why:
Action items raised:
```

---

## 8. Verification Log

Record every DR drill, backup-restore verification run, and any confirmation of the §2.1 PITR
action item here — this section is the evidence trail that turns "we have a DR plan" into "we have
a *tested* DR plan."

| Date | Action | Result | Evidence |
|---|---|---|---|
| 2026-07-24 | DRP authored (Celina 5) | Policy targets set; PITR status confirmation still pending (§2.1) | This document |
| 2026-07-24 | First live run of `scripts/verify_backup_restore.py` against production | 13/13 checks passed after fixing 2 real bugs the drill itself surfaced (audit-chain timestamp false positive + a genuine, non-malicious concurrent-write race at seq=32; no evidence of tampering anywhere in the 358-row table) | `docs/security/AUDIT_CHAIN_INCIDENT_2026-07-24.md`; `backup_restore_verification.json` (HMAC-signed, key source: `FIELD_ENCRYPTION_KEY`) |

---

## 9. Related Documents

- `docs/security/SECURITY_GAP_REGISTER.md` — SEC-017 (login audit, closed 2026-07-24, see §1 of
  `STRIDE_THREAT_MODEL.md`'s companion Celina 5 work), SEC-025 (Render vs. Railway host reference —
  see note below), SEC-021 (`/health` has no dependency check — relevant to §4.5's detection gap).
- `docs/security/STRIDE_THREAT_MODEL.md` — threat analysis; Disaster Recovery is the operational
  response to several of that document's Denial-of-Service and Repudiation-class threats.
- `scripts/dr_runbook.py`, `scripts/verify_backup_restore.py` — automated tooling (§6).

**Note on SEC-025 (Render vs. Railway):** this document assumes **Render.com** is the live
production host, based on strong repository evidence — multiple hardcoded production URLs across
the codebase (`routers/morning_briefing.py`, `routers/zakon_monitoring.py`, and others) point to
`https://vindex-ai.onrender.com`, a Render-specific subdomain pattern, not a custom domain that
could plausibly sit on either provider. However, a `railway.toml` file also exists at the repo root
with a complete, non-trivial configuration (build/deploy/healthcheck settings) — this is not
consistent with a total non-user, and its presence is unexplained by the evidence above. **Action
item for the founder:** confirm whether Railway is a leftover from an earlier evaluation/migration
attempt (safe to delete) or an active secondary/staging environment (must be documented, not
deleted). Until confirmed, do not delete `railway.toml` — flagged here rather than acted on
unilaterally, per this project's own standing rule on hard-to-reverse actions.

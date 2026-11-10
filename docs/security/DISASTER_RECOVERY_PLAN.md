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
| **RPO** (Recovery Point Objective) | Maximum acceptable data loss, measured in time since the last durable, restorable snapshot | **≤ 15 minutes** | **POLICY TARGET — current production RPO UNKNOWN; no provider backup artifact/PITR evidence. See §2.1.** |
| **RTO** (Recovery Time Objective) | Maximum acceptable time from incident detection to restored service | **≤ 2 hours** | **POLICY TARGET — current production RTO UNKNOWN; no production-equivalent timed restore. See §2.2.** |

### 2.1 Honest current-state caveat (read before treating RPO ≤ 15 min as a settled fact)

This project's own security documentation discipline (`docs/security/SECURITY_GAP_REGISTER.md`,
`PUBLIC_SECURITY_CLAIMS.md`) is explicit that claims must be evidence-based, not aspirational. In
that spirit:

- **Current read-only account evidence (2026-11-10):** the production project
  `czsxymueizfqrbbgqqob` is associated with organization `prdvzjpvjxermmrglufm`, whose connected
  Supabase control-plane record reports plan `free`. Supabase documents automatic daily backups on
  Pro, Team and Enterprise plans. No guaranteed automatic production database backup or PITR has
  been demonstrated for this Free organization. The historic 24-hour value is not a confirmed
  production floor.
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
  Until provider evidence and a restorable artifact are recorded, effective production RPO is
  **UNKNOWN**. The 15-minute value remains a policy target, not a current capability.

This caveat is deliberately kept prominent rather than buried — an incident responder who reads only
the RPO number in §2 without this context would make a false assumption at exactly the moment
accuracy matters most.

### 2.2 RTO ≤ 2 hours — feasibility

RTO is a policy target. It has not been demonstrated by a timed production-equivalent recovery. A
local synthetic drill does not establish production RTO. Evidence needed to call the two-hour target
met includes an available production backup, recoverable original Storage objects, key recovery and a
timed restore to an approved destination. Until then RTO is **UNKNOWN**. The target depends on:
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
| 5 | Once both platforms report healthy: run `python scripts/dr_runbook.py --quick` from an authorized machine to check Supabase connectivity only. The quick mode does not verify OpenAI or Pinecone. | Founder | +5 min |
| 6 | Run `python scripts/verify_backup_restore.py` against the restored database for read-only structural checks. Its report explicitly says `restore_status=NOT_PERFORMED`; this step is not evidence that a backup existed or that the restore succeeded. | Founder | +10–15 min |
| 7 | Run the audit chain integrity check: `GET /api/admin/security/audit-verify` (or `python scripts/dr_runbook.py --check chain`). A chain break exactly at the restore boundary is expected (§4.3) — anywhere else is a tampering signal requiring separate investigation, not a "recovery failed" signal. | Founder | +5 min |
| 8 | Send the incident notification (template in `scripts/dr_runbook.py`'s `INCIDENT_EMAIL_TEMPLATE`, GDPR čl. 33-34 / ZZPL čl. 52-53 compliant) if the incident involved any data loss or exceeded 1 hour of downtime. | Founder | +10 min |
| 9 | Declare recovery complete only after verifying the actual restored database and original Storage objects. Record total elapsed; the 2-hour RTO remains a policy target until a production-equivalent timed restore proves it. | Founder | RTO target ≤ 120 min, unproven |

### 4.2 Scenario P1 — Database-only outage or corruption (Supabase down or data corrupted, Render OK)

1. Supabase Dashboard → Project Settings → **Backups**.
2. If PITR is active: select "Restore to point in time" and choose the timestamp immediately
   before the incident (from the internal status note in §4.1 step 2, or from the last known-good
   entry in `audit_immutable`/application logs).
3. If provider evidence confirms a scheduled backup but PITR is not active, select the latest
   available snapshot and record its timestamp. Do not assume daily availability or a 24-hour RPO;
   communicate the actual measured recovery point. If no restorable artifact is available, stop and
   follow the approved provider recovery path.
4. Point the application at the restored database (Supabase restores in-place for the same
   project in most cases; a distinct restore-to-new-project would additionally require updating
   `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` in Render's environment variables and redeploying).
5. Run §4.1 steps 5–7 (connectivity check, backup-restore verification, audit chain check).
6. Record elapsed time. The 30–60 minute estimate is unverified and does not establish the 2-hour
   RTO target.

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
| `scripts/verify_backup_restore.py` (Celina 5) | Read-only connectivity, schema, limited audit and relationship checks. It does not perform a backup or restore. Its report retains `restore_status=NOT_PERFORMED`. | Structural health only; not proof of completed restore. |

Both scripts are safe to run against production for read-only verification (neither performs a
destructive restore against the live database — an actual Supabase point-in-time restore must be
triggered manually via the Supabase Dashboard, per §4.2, as a deliberate, human-confirmed action;
no script in this repository automates that irreversible step).

`scripts/isolated_restore_drill.py` performs an actual synthetic local CREATE → BACKUP → DESTROY →
RESTORE exercise over a SQLite matter store and encrypted object files. This proves only that local
synthetic procedure. It does not establish production backup availability, Storage coverage, key
escrow, schedule, RPO or RTO. Its separate synthetic recovery key is test material, not a production
key-management procedure.

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
| 2026-07-24 | First live run of the read-only structural verifier against production (not a backup/restore drill) | 13/13 structural checks passed after fixing 2 bugs (audit-chain timestamp false positive + genuine concurrent-write race at seq=32; no evidence of tampering in the 358-row table). No backup artifact was restored by this run. | `docs/security/AUDIT_CHAIN_INCIDENT_2026-07-24.md`; historical `backup_restore_verification.json` (HMAC-signed, key source: `FIELD_ENCRYPTION_KEY`) |
| 2026-11-10 | Read-only production account metadata + isolated synthetic restore | Organization plan is `free`; production backup artifact/schedule, PITR, Storage-object backup, production key recovery, RPO and RTO remain unverified. Synthetic local SQLite + encrypted-object CREATE/BACKUP/DESTROY/RESTORE passed in 0.062s; 2 tenants, 2 matters, 2 documents, 2 audit rows. This timing is not production RTO. | PR #84 evidence package `vindex-backup-restore-drill-final`; backup SHA-256 `47c3dfd9dbd662f69932d120ebe3c5db79bb12a8cfee04dc500270762c6a55c1`; manifest SHA-256 `bcd73e59ebe0f748d8dda26f495d1071855730f8489415631fd57bb9abab324e`; report SHA-256 `11b94c4f5bc1ba4b943f4f93173aef2e075d7d55bb1f0e1aefd0a98f4a1eb908`. Manifest is retained separately from the deleted primary state; synthetic recovery key is separate test material, not a production secret. |

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

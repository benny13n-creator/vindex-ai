# SEC-031 — Remediation Design: User Lifecycle Model

**Date:** 2026-07-23
**Status:** Design only. **No schema or code changed by this document.** Follows `SEC031_IMPACT_ANALYSIS.md` (the "what's at risk" survey) — this document proposes "what to build," not the build itself. Implementation requires a separate, explicit founder go-ahead, same discipline as every other architecture document this cycle.
**Trigger:** Founder rejected the immediate-fix framing ("just close SEC-031") and reframed the remediation choice itself: for a legal-records product, `DELETE USER → CASCADE EVERYTHING` is the wrong default shape regardless of which of the three §6 strategies gets picked in isolation. The right shape is a lifecycle — a sequence of deliberate, auditable states — not a single irreversible action. This document designs that lifecycle.

---

## 1. Why "soft delete" alone is not the answer

`SEC031_IMPACT_ANALYSIS.md` §6 offered three strategies (RESTRICT / soft-delete / archive-anonymization) as independent options. The founder's framing correctly rejects treating them as alternatives to choose between — they are **stages**, not competing designs:

- **RESTRICT** (§6A) is not a destination, it's a guardrail — it stops the accidental-catastrophic case, but says nothing about what *should* eventually happen to a closed account's data.
- **Soft-delete** (§6B) alone just relocates the same all-or-nothing decision to a `deleted_at` flag — it doesn't answer "deleted for whom, visible to whom, for how long," which is exactly the question SEC-002's retention matrix showed has a different answer per table (`predmeti` ≠ `notifications` ≠ `audit_immutable`).
- **Archive/anonymization** (§6C) is the right *eventual* state for most tables, but arriving there in one step from "active" skips the part where a closure might be reversible (an accidental request, a client dispute, a re-engagement) — legal-records products specifically need that grace window more than a typical SaaS product does, because the record being closed is often evidence, not just user convenience data.

**The lifecycle model treats these three as sequential stages of one state machine, not three mutually exclusive fixes.**

---

## 2. Proposed lifecycle

```
   ACTIVE
      |
      |  (account closure requested — by user, or by firm admin for a
      |   departing member, see §5)
      v
  DEACTIVATED
      |
      |  (retention clock starts; login blocked; data untouched and
      |   fully intact; reversible)
      v
  RETENTION PERIOD
      |
      |  (duration is per-table, per SEC-002's matrix — NOT one global
      |   number; clock length REQUIRES LEGAL CONFIRMATION per category)
      v
  ANONYMIZED / ARCHIVED
      (terminal state — table-specific: some rows anonymized in place,
       some moved to a restricted archive, some tables' rows survive
       untouched if genuinely required to remain attributable, e.g.
       audit_immutable — see SEC-002 §1's audit_immutable treatment)
```

### State definitions

**ACTIVE** — current behavior, no change. User can log in, all data fully live.

**DEACTIVATED** — login blocked (mechanism: `REQUIRES IMPLEMENTATION DECISION`, likely a `profiles.account_status` flag checked at auth-gate time, or Supabase's own user-ban capability — both need evaluation, not decided here). **No data touched at all in this state.** This is the reversible window — if closure was requested in error, or a firm needs to un-deactivate a departing associate's account for a records request, this state can be undone with zero data loss, because nothing has happened yet except blocking login.

**RETENTION PERIOD** — the account is deactivated and a countdown has started, per-table, using SEC-002's matrix as the source of per-table durations once those are legally confirmed. This is a logical/reporting state (derived from `deactivated_at` + the applicable table's retention duration), not necessarily its own stored flag — `REQUIRES IMPLEMENTATION DECISION` whether to model it explicitly or compute it on read.

**ANONYMIZED / ARCHIVED** — terminal. What happens here is **not uniform across tables** — this is the direct continuation of SEC-002's per-table matrix, now given an actual mechanism instead of being a one-time manual action:
- Tables where the retention question resolves to "no obligation to keep, safe to anonymize" (e.g. `profiles`, communication logs, session tables — SEC-002 §2's lower-stakes tiers): anonymize in place, same idea as the current `profiles` handling, extended.
- Tables where a professional/tax/legal retention obligation is confirmed (candidates: `predmeti` and its children, `fakture`, `billing_entries`, `tarife` — pending the `REQUIRES LEGAL CONFIRMATION` items in SEC-002 §1): move to a restricted-access archive (same data, no longer reachable through normal application queries, visible only through a deliberate, audited, founder-or-legal-authorized retrieval path) rather than either deleting or leaving it live-and-queryable.
- `audit_immutable`: excluded from this lifecycle entirely, as already noted in SEC-002 §1 — its own tamper-evident design means it should not be touched by account closure at all except possibly pseudonymizing the `user_id` reference, which is a narrower, separate mechanism.

---

## 3. How this closes SEC-031 specifically

The lifecycle model only closes SEC-031 if the mechanical guardrail from §6A is applied alongside it — the lifecycle is meaningless if a direct `auth.users` deletion can still bypass all of it. Concretely:

1. **`auth.users` rows are never hard-deleted by this design** — "deletion" in user-facing language always means entering the lifecycle above, terminating at ANONYMIZED/ARCHIVED, never an actual `DELETE FROM auth.users`. The Supabase Auth row itself either stays (disabled/banned) or is removed only after every dependent table has already been individually resolved by the lifecycle — never as the triggering action.
2. **Every `ON DELETE CASCADE` in `SEC031_IMPACT_ANALYSIS.md` §1/§2 changes to `RESTRICT`** (§6A, now positioned as this design's mechanical floor, not a standalone strategy). This makes accidental catastrophic deletion structurally impossible — even if someone reaches for the Supabase dashboard despite the containment rule in §0 of the impact analysis, Postgres itself refuses the operation as long as any dependent row exists, which (by design) is always true until the lifecycle has actually processed that table.
3. This is why RESTRICT is not "one of three options" but the load-bearing safety property underneath whichever lifecycle-stage logic is built on top — worth stating plainly since the impact analysis originally presented it as a peer alternative to B/C.

---

## 4. What this requires before it can be built (explicitly not decided here)

- **Per-table retention durations** — SEC-002's matrix marks these `REQUIRES LEGAL CONFIRMATION`; this design cannot assign a concrete countdown length to `predmeti`/`fakture`/etc. without that answer. The lifecycle's *shape* doesn't depend on the answer, but its *parameters* do.
- **Who can initiate DEACTIVATED → RETENTION PERIOD → ANONYMIZED transitions** — self-service (user-initiated, same trust level as today's GDPR endpoint) vs. requiring a review step given the stakes (a legal record, not a typical SaaS account) — `REQUIRES PRODUCT-POLICY DECISION`.
- **Where "firm" fits** — §5 below.
- **What the archive access path looks like** — who can retrieve archived data, under what circumstances, with what audit trail — needs its own design once the legal retention questions are answered, since its shape depends on *why* the data is being kept.

None of these block writing this design, but all of them block building it — flagging explicitly rather than silently picking defaults.

---

## 5. Firm/multi-attorney complication (carried over from SEC-002 §2)

SEC-002's matrix already flagged this: a departing associate's account closure should almost certainly not enter the same lifecycle as a solo practitioner's account closure, if the underlying `predmeti`/`klijenti` data actually belongs to a firm rather than an individual. Current schema (`user_id` ownership throughout) doesn't distinguish these cases. This design's lifecycle applies cleanly to the solo-account case; the firm case needs either (a) a product decision that data ownership transfers to a remaining firm member before an individual's account lifecycle proceeds, or (b) an explicit firm-level ownership concept that doesn't exist yet. **Not designed here** — noted so it isn't lost, consistent with how it was first flagged.

---

## 6. What this document does not do

- Does not propose a migration or any DDL.
- Does not assign concrete retention durations — those come from SEC-002's still-open legal-confirmation items.
- Does not decide whether DEACTIVATED→RETENTION PERIOD transitions are automatic or require manual review.
- Does not design the archive-access/retrieval mechanism in detail.
- Does not resolve the firm-ownership question (§5).

## Recommendation summary

1. Treat RESTRICT (§3.2) as the immediate mechanical floor — it's compatible with every future direction and removes the accidental-catastrophic case regardless of how long the rest of this design takes to build.
2. Build the lifecycle (ACTIVE → DEACTIVATED → RETENTION PERIOD → ANONYMIZED/ARCHIVED) as the durable account-closure mechanism, replacing the current single-step `gdpr_delete_account` function once built.
3. Sequence: resolve SEC-002's `REQUIRES LEGAL CONFIRMATION` retention-duration questions → apply RESTRICT as a schema change → design and build the lifecycle state machine and archive mechanism → migrate the GDPR endpoint onto it.
4. **This document does not authorize step 2 of that sequence (the RESTRICT schema change) or any later step.** It is a design for founder review, following immediately from the impact analysis, per the explicit "design first, code later" instruction.

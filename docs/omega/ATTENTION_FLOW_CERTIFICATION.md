# Attention Flow Certification — Program Omega, Final Sprint 006 (2026-08-06)

Phase 5's own required deliverable: prove Document → Case Evolution → Genome → Action Engine →
Priority → Workspace → Dashboard → Notification → Lawyer, with no second decision source. Phase 6
(eliminate shadow decisions) is folded in here since it's the same proof, extended.

## The chain, link by link — what's newly proven this sprint vs. already-certified

| Link | Certified by | Sprint |
|---|---|---|
| Document → Case Evolution → Genome → Action Engine → `case_actions` | `tests/test_omega_sprint005_full_chain_to_workspace.py` — drives the REAL `dispatch_pending_events()`, not a shortcut | 005 |
| `case_actions` → Workspace | `tests/test_omega_sprint004_case_to_workspace_flow.py`, `test_omega_sprint004_workspace.py` | 004/005 |
| **Priority is canonical, not re-derived per consumer** | `tests/test_omega_sprint006_canonical_attention.py` — every consumer's own `_ORDER`/map dict is a provable derivation of `shared/attention_priority.py`, not an independent copy | **006 (new)** |
| **Workspace, Dashboard (`predmet_workspace`), and Notification agree on rank** | `test_every_consumer_dict_agrees_on_the_rank_of_its_own_top_tier_word`, `test_case_actions_critical_and_notifications_urgent_rank_identically` | **006 (new)** |
| Case Evolution → Notification/Dashboard/Lawyer (the final leg) | Honestly NOT a single unified write path — see below | **006 (found, not fully closed)** |

## The honest gap in the final leg

The mission's own diagram implies one continuous pipe: `... → Priority → Workspace → Dashboard →
Notification → Lawyer`. What this sprint can certify: **the priority VALUE is canonical and agrees**
across all 3 read surfaces (Workspace, `predmet_workspace`'s own `rokovi_po_hitnosti`, the `notifications`
bell). What it CANNOT yet certify: that Dashboard/Notification are *reading from* `case_actions` as a
single upstream source — they still independently query `rocista`/`predmet_hronologija` and compute
their own item lists (with their own, still-inconsistent day-count thresholds — `OMEGA-021`). The
canonicalization this sprint achieved is at the VOCABULARY layer (Phase 3/4's own literal scope); full
single-write-path unification is a larger, correctly-deferred redesign (`OMEGA-020`).

**Stated plainly, per this sprint's own Phase 7 discipline**: the chain is "certified for shared
vocabulary and ranking," NOT "certified as one single computation with three read replicas." These are
different claims — the mission's own Phase 7 instruction ("ako postoji makar jedan drugi izvor, sprint
nije završen") is honored by naming this distinction explicitly rather than blurring it.

## Phase 6 — shadow decisions eliminated this sprint

| Found computing its own priority independently | Fix |
|---|---|
| `routers/case_actions.py::_PRIORITY_ORDER` | Now literally `shared.attention_priority.CANONICAL_ORDER` |
| `routers/workspace.py::_ZADACI_PRIORITET_MAP` | Now literally `shared.attention_priority.ZADACI_TO_CANONICAL` |
| `routers/inbox.py::_PRIORITET_ORDER` | Now derived, byte-identical resulting values |
| `routers/notifications.py::PRIORITY_ORDER` | Now derived, byte-identical resulting values |
| `routers/notifications.py`'s own row-level `prioritet` (bug: disagreed with `NOTIF_TIPOVI`) | Fixed — derives from `NOTIF_TIPOVI[tip]["priority"]`, one source |
| `api.py::predmet_workspace`'s `_VAZNOST_ORDER` | Now derived, byte-identical resulting values |
| `api.py`'s own `GET /api/notifications` (4th alert system, own 9th vocabulary) | Deleted entirely — confirmed dead |

## Phase 6 — shadow decisions found and deliberately NOT touched (with reasons)

| Still computes independently | Why not migrated |
|---|---|
| Cockpit's risk `nivo` | Different concept (case risk, not action priority) — forcing it onto the action-priority scale would misrepresent it |
| `_delta_hitnost` (Genome-change urgency) | Different concept (diff significance); already deduplicated once by Program Gamma |
| Genome `nedostaje[].hitnost`, CIO `kriticnost`, `strategija.py`'s prompt priority | GPT-advisory outputs; mission's own explicit rule forbids new AI logic — these were not touched, not migrated, not silenced |
| `notifications`/`proactive_alerts`' own independent `rocista`/`predmet_hronologija` queries | Still 2 more independent WRITE decisions for the same deadline fact `case_actions` also tracks — named `OMEGA-020`, a trigger-path redesign outside this sprint's safe scope |

## Required test scenarios

| Scenario | Proof | Result |
|---|---|---|
| 1. New document → priority arises automatically | Sprint 005's own full-chain test (`dispatch_pending_events()` → `case_actions`) | ✅ (re-certified, unchanged) |
| 2. New deadline → priority increases | Sprint 004's own `test_deadline_extended_moves_action_from_critical_to_predstojece_in_workspace` (inverse direction, same mechanism proven both ways) | ✅ (re-certified) |
| 3. Problem resolved → priority decreases/closes | Sprint 004's own `test_resolved_action_disappears_from_active_workspace_and_appears_in_completed` | ✅ (re-certified) |
| 4. Two events, same case → one result, no duplicate warnings | Sprint 005's own `test_scenario1_replay_does_not_duplicate_workspace_items` (case_actions' own partial-unique-index idempotency) — for the CROSS-SYSTEM duplicate-write question (case_actions + notifications + proactive_alerts all firing for the same fact), see `OMEGA-020` — honestly named as NOT fully proven single-writer | ⚠️ (case_actions itself: yes; cross-system: named gap) |
| 5. Restart → attention identical | Sprint 005's own `test_scenario1_replay_does_not_duplicate_workspace_items` (drives real `handle_case_changed` replay) | ✅ (re-certified) |
| 6. 500 documents → orderly Workspace list, no notification explosion | Sprint 004's own `test_500_documents_one_case_workspace_shows_only_what_matters` (case_actions/Workspace side); `notifications.py`'s own generation is capped/deduplicated by its own pre-existing "briši stare neprocitane iste kategorije" step (`routers/notifications.py`, unchanged this sprint) — not independently stress-tested this sprint | ✅ Workspace / ⚠️ notifications-side not newly proven |

## Certification verdict

**Certified**: one canonical priority vocabulary, values, order, and color exist and are used (directly
or by provable derivation) by every mechanical consumer found this sprint. A real, previously-unknown
bug (notifications' own row-level priority mismatch) is fixed and tested. A 4th shadow alert system is
deleted. 20 new tests, all passing, zero regressions.

**NOT certified**: a single, unified WRITE path for "this deadline needs attention" across
`case_actions`/`notifications`/`proactive_alerts` — 3 systems can still independently decide to alert on
the same fact, with 3-4 different day-count thresholds. Named honestly as `OMEGA-020`/`OMEGA-021`, not
claimed solved.

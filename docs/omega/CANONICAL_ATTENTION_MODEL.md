# Canonical Attention Model — Program Omega, Final Sprint 006 (2026-08-06)

Phase 2 (Attention Ownership) + Phase 3 (Canonical Priority Model)'s own required deliverable. Every
surface from `docs/omega/ATTENTION_SURFACE_REGISTRY.md` gets exactly one verdict —
**SOURCE**, **CONSUMER**, or **RETIRED**. No surface is both Source and Consumer without proof.

## The canonical vocabulary — not invented, adopted

`critical` / `high` / `medium` / `low` / `informational` — `case_actions.prioritet`'s own existing,
DB-enforced (migration 099 CHECK constraint) values. Chosen as the anchor because it is:
1. The only vocabulary enforced by the database itself (a CHECK constraint), not just convention.
2. Already what `GET /api/workspace` (Sprint 004/005) treats as canonical for the one deterministic
   "what needs attention" domain this whole Program Omega arc has built.
3. Free of GPT involvement — every value is produced by `services/case_evolution.py::
   _compute_target_actions` (Sprint 003) from real DB rows or `risk_engine.py`'s own deterministic
   output, never an LLM guess.

Implemented in `shared/attention_priority.py` (new this sprint) — the ONE module every mechanical
consumer below now imports from, instead of keeping its own copy.

## Ownership matrix — every surface, one verdict

| Surface | Verdict | Reasoning |
|---|---|---|
| `case_actions.prioritet` / `services/case_evolution.py::_compute_target_actions` | **SOURCE** | The canonical anchor itself — deterministic, DB-enforced, zero GPT |
| `services/risk_engine.py::identify_case_problems` (`ozbiljnost`) | **SOURCE** (for its own facts) / translated by consumers | Core Consolidation's own canonical "what's wrong" algorithm — `case_actions` already reuses it directly (not a translation, a direct call) |
| `routers/case_actions.py::_PRIORITY_ORDER` | **CONSUMER** | Now `= shared.attention_priority.CANONICAL_ORDER` (Sprint 006) — no longer its own copy |
| `routers/workspace.py::_ZADACI_PRIORITET_MAP` | **CONSUMER** | Now `= shared.attention_priority.ZADACI_TO_CANONICAL` (Sprint 006) |
| `routers/inbox.py::_PRIORITET_ORDER` | **CONSUMER** | Now derived from `INBOX_TO_CANONICAL` (Sprint 006), byte-identical resulting values |
| `routers/notifications.py::PRIORITY_ORDER` | **CONSUMER** | Now derived from `NOTIFICATIONS_TO_CANONICAL` (Sprint 006), byte-identical resulting values |
| `routers/notifications.py`'s own row-level `prioritet` field | **CONSUMER**, was accidentally acting as an uncoordinated 2nd SOURCE | Bug: `_generate_notifications` wrote hand-typed values that disagreed with `NOTIF_TIPOVI`'s own tip-based priority — fixed this sprint to derive from `NOTIF_TIPOVI[tip]["priority"]`, one source (`tip`) |
| `api.py::predmet_workspace`'s `_VAZNOST_ORDER` | **CONSUMER** | Now derived from `VAZNOST_TO_CANONICAL` (Sprint 006), byte-identical resulting values |
| `zadaci.prioritet` (the underlying DB column/API) | **SOURCE** (for its own concept: human-assigned task priority) | Genuinely different concept (a human's own explicit choice, not a computed fact) — stays its own source, translated at the boundary by consumers, never rewritten |
| `api.py`'s (was) `GET /api/notifications` | **RETIRED** | Confirmed zero frontend callers, fully self-contained (no writes), safe, real elimination |
| Cockpit risk `nivo` | **SOURCE** (different concept: case RISK, not action priority) | Not merged — `calculate_procesni_rizik`'s own canonical risk level, a genuinely different question than "how urgent is this specific action" |
| `_delta_hitnost` (Genome-change urgency) | **SOURCE** (different concept: diff significance) | Not merged — already deduplicated once (Program Gamma) into 1 shared function; measures "how much did Genome change," not case/action priority |
| Genome `nedostaje[].hitnost`, CIO `kriticnost`, `strategija.py` prompt priority | **SOURCE** (GPT-advisory, on-demand) | Not merged — mission's own explicit rule forbids new AI logic; these remain their own, clearly-labeled, non-canonical advisory outputs |
| `static/vindex.js::_WS_PRIO_COLOR` | **CONSUMER** (of `CANONICAL_COLOR`, by value) | JS cannot literally import a Python constant — kept as a hand-synced copy, cross-referenced by comment, values identical |

## The translation layer, exactly

```python
# shared/attention_priority.py
CANONICAL_VALUES = ("critical", "high", "medium", "low", "informational")
CANONICAL_ORDER   = {critical: 0, high: 1, medium: 2, low: 3, informational: 4}
CANONICAL_COLOR   = {critical: "#ef4444", high: "#fb923c", medium: "#4aa8ff", low: "#94a3b8", informational: "#64748b"}
CANONICAL_LABEL_SR = {critical: "Kritično", high: "Visok", medium: "Srednji", low: "Nizak", informational: "Info"}

ZADACI_TO_CANONICAL        = {hitno: critical, visoko: high, normalan: medium, nisko: low}
OZBILJNOST_TO_CANONICAL    = {kritican: critical, vazan: high, info: informational}
NOTIFICATIONS_TO_CANONICAL = {urgent: critical, high: high, normal: medium, low: low, info: informational}
INBOX_TO_CANONICAL         = {kriticno: critical, visok: high, srednji: medium, nizak: low}
VAZNOST_TO_CANONICAL       = {kritičan: critical, bitan: high, normalan: medium, ostalo: low}
```

Every translation is **lossless and reversible in spirit** — no source vocabulary had more granularity
than the canonical 5 accommodate, so nothing was collapsed/lost in the mapping. Every consumer's own
resulting `_ORDER`/map dict is verified byte-identical to its pre-Sprint-006 value
(`tests/test_omega_sprint006_canonical_attention.py`) — this sprint changes WHERE the value comes from,
never WHAT the value is, for every mechanical consumer.

## What is deliberately NOT unified, and why

Eliminating a "synonym" only makes sense when two words describe the SAME concept. 3 genuinely different
concepts were found wearing priority-like clothing and were deliberately left alone:

1. **Case risk level** (`nizak`/`srednji`/`visok`) — answers "how risky is this CASE overall," not "how
   urgent is this ACTION." `calculate_procesni_rizik`'s own canonical output.
2. **Genome-change significance** (`hitna`/`normalna`) — answers "how much did THIS Genome refresh
   change," not a case or action priority at all.
3. **GPT-advisory scores** (Genome's `nedostaje[].hitnost`, CIO's `kriticnost`, `strategija.py`'s own
   `prioritet`) — opinions, not decisions the platform automatically acts on. Forcing these onto the
   canonical scale would misrepresent them as equally authoritative as `case_actions`' own deterministic
   values — exactly the AR-01 violation this whole engagement has spent months eliminating elsewhere.

## What remains open, honestly

Deadline-urgency DAY-COUNT THRESHOLDS (≤2 vs ≤3 days for "critical") are still inconsistent across
`case_actions`, `notifications.py`, `dashboard.py` — a real product decision (which threshold is
actually correct), not a wording synonym, named as `OMEGA-021` rather than guessed at.

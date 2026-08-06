# -*- coding: utf-8 -*-
"""
Vindex AI — shared/attention_priority.py

Program Omega, Final Sprint 006 (2026-08-06) — "Canonical Attention Engine".

Phase 3's own required deliverable: ONE canonical priority vocabulary, and a translation table from
every other vocabulary this repo independently invented for the same underlying concept — "how urgent
is this." Nothing here computes a NEW priority — every function is a pure lookup/translation over a
value some other, already-existing, already-correct system produced. See
docs/omega/CANONICAL_ATTENTION_MODEL.md for the full inventory this was built from
(`docs/omega/ATTENTION_SURFACE_REGISTRY.md`).

## Why `case_actions.prioritet` is the anchor, not something new

`critical`/`high`/`medium`/`low`/`informational` is not invented here — it is
`case_actions.prioritet`'s own existing, DB-enforced (migration 099 CHECK constraint) vocabulary,
already the read model `GET /api/workspace` (Program Omega Sprint 004/005) treats as canonical for the
one deterministic "what needs attention" domain this whole Program Omega arc has built
(`services/case_evolution.py::_compute_target_actions`, Sprint 003). Reusing it here — rather than
inventing a 13th scale — IS the canonicalization this sprint's own charter demands.

## What this module does NOT do

- Does not change any underlying table's own CHECK constraint or stored values — `zadaci.prioritet`
  stays `hitno`/`visoko`/`normalan`/`nisko` in the database and in `routers/zadaci.py`'s own API,
  exactly as before. Translation happens at the READ boundary, the same "translate, don't rewrite the
  source" idiom `routers/workspace.py::_ZADACI_PRIORITET_MAP` already established in Sprint 004 (that
  dict is superseded by this module — see `docs/omega/CANONICAL_ATTENTION_MODEL.md`).
- Does not touch any GPT prompt or attempt to make an LLM output the canonical vocabulary directly —
  several vocabularies below (Genome's own `nedostaje[].hitnost`, `routers/strategija.py`'s own
  `sledeci_koraci[].prioritet`, CIO's own `kriticnost` score) are GPT-advisory, not action-tracking,
  and are listed here for completeness/documentation, not because anything currently wires them into
  the canonical Attention Engine.
- Does not merge concepts that are genuinely different. Cockpit's own risk `nivo`
  (`nizak`/`srednji`/`visok`, case-level RISK) and `_delta_hitnost`'s own `hitna`/`normalna`
  (Genome-change SIGNIFICANCE) are related but distinct from action PRIORITY — deliberately kept in
  their own, separately-labeled sections below rather than force-mapped onto the same 5 values.
"""
from __future__ import annotations

# ─── The one canonical vocabulary ────────────────────────────────────────────
# Identical to case_actions.prioritet's own DB-enforced values (migration 099).
CRITICAL = "critical"
HIGH = "high"
MEDIUM = "medium"
LOW = "low"
INFORMATIONAL = "informational"

CANONICAL_VALUES = (CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL)

# Sort order — identical to routers/case_actions.py::_PRIORITY_ORDER (Sprint 003), now the ONE copy;
# that module and every other consumer below import this instead of keeping their own copy.
CANONICAL_ORDER: dict[str, int] = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFORMATIONAL: 4}

# Display color — one canonical mapping, reused by every UI surface that renders a priority-colored
# dot/badge (Workspace, the case-detail "Otvorene akcije" panel, and any future consumer), matching the
# hex values `static/vindex.js::_WS_PRIO_COLOR` (Sprint 005) already used for case_actions/zadaci.
CANONICAL_COLOR: dict[str, str] = {
    CRITICAL: "#ef4444", HIGH: "#fb923c", MEDIUM: "#4aa8ff", LOW: "#94a3b8", INFORMATIONAL: "#64748b",
}

# Serbian display label — one canonical set of words, for any future UI surface that wants to show the
# canonical value directly instead of a source-vocabulary word.
CANONICAL_LABEL_SR: dict[str, str] = {
    CRITICAL: "Kritično", HIGH: "Visok", MEDIUM: "Srednji", LOW: "Nizak", INFORMATIONAL: "Info",
}


# ─── ACTION-PRIORITY vocabularies — the same underlying concept, different words ────────────────────
# Every mapping below is a straight, lossless translation of an ALREADY-EXISTING enum/CHECK-constraint
# value onto the canonical 5 above — verified against docs/omega/ATTENTION_SURFACE_REGISTRY.md's own
# file:line citations, not guessed.

# zadaci.prioritet (migration 045 CHECK constraint) — routers/zadaci.py, routers/workspace.py.
ZADACI_TO_CANONICAL: dict[str, str] = {
    "hitno": CRITICAL, "visoko": HIGH, "normalan": MEDIUM, "nisko": LOW,
}

# services/risk_engine.py::identify_case_problems's own "ozbiljnost" field — the canonical "what's
# wrong with this case" algorithm (Core Consolidation, 2026-07-22), already reused unchanged by
# case_actions' own Rule 2/4/5 (Sprint 003).
OZBILJNOST_TO_CANONICAL: dict[str, str] = {
    "kritican": CRITICAL, "vazan": HIGH, "info": INFORMATIONAL,
}

# routers/notifications.py::NOTIF_TIPOVI's own "priority" field, and the notifications table's own
# "priority" sort key (PRIORITY_ORDER).
NOTIFICATIONS_TO_CANONICAL: dict[str, str] = {
    "urgent": CRITICAL, "high": HIGH, "normal": MEDIUM, "low": LOW, "info": INFORMATIONAL,
}

# routers/inbox.py's own "kriticno/visok/srednji/nizak" vocabulary (used by its now-narrower item set
# post-Sprint-005 — dokument/naplata/neaktivan only, rociste/rok removed).
INBOX_TO_CANONICAL: dict[str, str] = {
    "kriticno": CRITICAL, "visok": HIGH, "srednji": MEDIUM, "nizak": LOW,
}

# predmet_hronologija.vaznost — read independently by api.py::predmet_workspace (its own
# _VAZNOST_ORDER), routers/dashboard.py, routers/notifications.py, and api.py's own (retired this
# sprint) GET /api/notifications. The underlying COLUMN is unchanged; this is the read-side translation.
VAZNOST_TO_CANONICAL: dict[str, str] = {
    "kritičan": CRITICAL, "bitan": HIGH, "normalan": MEDIUM, "ostalo": LOW,
}

# Program Omega, Final Sprint 007 (2026-08-06) — the reverse direction, needed once a canonical
# writer (case_actions) needs to PROJECT into a consumer's own vocabulary instead of just reading
# one. Used by services/case_evolution.py::_consequence_project_case_actions_to_notifications to
# translate case_actions' own canonical prioritet into notifications.py's own NOTIF_TIPOVI/
# PRIORITY_ORDER vocabulary when writing a projected notification row. Deliberately only covers the
# canonical values case_actions' own Rule 1 (_priority_by_days) can actually produce (critical/high/
# medium) plus low/informational for completeness — not a general N:1 inverse (NOTIFICATIONS_TO_
# CANONICAL is not injective: "info" and no other word maps to INFORMATIONAL, so inversion is
# unambiguous here, but would not be for a table with true many-to-one collisions).
CANONICAL_TO_NOTIFICATIONS: dict[str, str] = {
    CRITICAL: "urgent", HIGH: "high", MEDIUM: "normal", LOW: "low", INFORMATIONAL: "info",
}


def to_canonical(value: str | None, vocabulary: dict[str, str], default: str = MEDIUM) -> str:
    """Translate a source-vocabulary value to the canonical scale. Unknown/missing values fall back to
    MEDIUM (never silently CRITICAL/LOW) so a translation gap degrades to "needs a normal look," not
    "gets hidden" or "falsely screams urgent.\""""
    if not value:
        return default
    return vocabulary.get(value, default)


def canonical_sort_key(value: str) -> int:
    return CANONICAL_ORDER.get(value, len(CANONICAL_ORDER))


# ─── Related, but deliberately NOT merged into action-priority ──────────────────────────────────────
# Documented here for completeness (Phase 1's own "repo-wide, bez izuzetaka" mandate) — NOT translated
# to CRITICAL/HIGH/MEDIUM/LOW/INFORMATIONAL because they measure a genuinely different thing.

# Case-level RISK (not action priority) — services/risk_engine.py::calculate_procesni_rizik's own
# "nivo" field, rendered by static/vindex.js::pred_renderCockpit's own risk badge.
RISK_LEVEL_VALUES = ("nizak", "srednji", "visok")

# Genome-change ALERT SIGNIFICANCE (not case/action priority) — routers/case_dna.py::_delta_hitnost,
# already deduplicated from 2 inline copies into 1 shared function by Program Gamma (2026-08-04).
GENOME_DELTA_URGENCY_VALUES = ("hitna", "normalna")

# GPT-advisory document importance — Genome's own case_dna.nedostaje[].hitnost (extraction prompt,
# routers/case_dna.py) — an LLM opinion embedded in Genome's own output, not a decision case_actions or
# Workspace currently reads.
GENOME_MISSING_DOC_HITNOST_VALUES = ("kriticno", "vazno", "pozeljno")

# GPT-advisory next-step priority — routers/strategija.py's own system prompt,
# `sledeci_koraci[].prioritet` — on-demand strategic simulation output, not an automatic action.
STRATEGIJA_PRIORITET_VALUES = ("hitan", "normalan", "opciono")

# GPT-advisory portfolio urgency score — routers/cio.py's own informal 0-100 "kriticnost" field.

# -*- coding: utf-8 -*-
"""
Vindex AI — shared/case_readiness.py

Program Sigma, Master Sprint 004 (2026-08-06) — "Legal Case Readiness & Action
Planning Engine". Two things, both pure functions over ALREADY-COMPUTED data,
inventing no new detection algorithm — per this sprint's own explicit
architectural constraint ("NE praviti novi Task/Action/Priority/Recommendation
sistem"):

1. `top_open_action()` — the ONE canonical "what should the lawyer do next"
   reader, over `case_actions`' own already-canonical rows (migration 099,
   `services/case_evolution.py::_compute_target_actions`), ordered by
   `shared/attention_priority.py`'s own already-canonical priority order. Every
   consumer that used to independently GPT-guess "the one most urgent action"
   (routers/case_intelligence.py's own AI Briefing, routers/copilot.py's own
   _handle_analiza_predmeta) now calls this instead.

2. `compute_case_readiness()` — the Legal Readiness Model (Phase 4): a
   deterministic 5-state classification (READY/PARTIALLY_READY/BLOCKED/
   CRITICAL_GAP/UNKNOWN), computed EXCLUSIVELY from `case_actions.prioritet`
   (case_actions' own already-canonical, already-deterministic priority — see
   `shared/attention_priority.py`) plus whether any Gap Engine hypothesis-only
   finding exists with no deterministic backing. No GPT call, no GPT number, no
   GPT status string — the exact opposite of `routers/matter_intel.py::
   preflight_check`'s own GPT-generated `status` field (found this sprint, see
   `CASE_READINESS_MODEL.md` for why that field was NOT touched/replaced this
   sprint despite the overlap).

## Why this is 2 functions in 1 new module, not 2 new modules

Both read the exact same input shape (a case's own open `case_actions` rows)
and both exist to answer variations of the mission's own one question ("what
should the lawyer do, and how ready is the case") — splitting them into 2
files would itself be exactly the kind of unnecessary proliferation this
sprint's own founding principle warns against.
"""
from __future__ import annotations

from shared.attention_priority import CANONICAL_ORDER, canonical_sort_key


def top_open_action(case_actions: list[dict]) -> dict | None:
    """Returns the single highest-priority OPEN case_actions row for a case,
    or None if there are none. THE canonical answer to "what's the one most
    urgent thing" — callers that used to ask GPT to invent this (case_
    intelligence.py's own briefing, copilot.py's own _handle_analiza_predmeta)
    now call this instead.

    `case_actions` here is the caller's own already-fetched list of OPEN rows
    for one predmet (this function does no DB I/O of its own, matching every
    other pure function in this codebase's own "no new AI/DB infrastructure"
    idiom for Sprint 003/004's own canonical aggregators)."""
    open_rows = [a for a in (case_actions or []) if a.get("status", "open") == "open"]
    if not open_rows:
        return None
    return min(open_rows, key=lambda a: (canonical_sort_key(a.get("prioritet")), a.get("rok") or "9999-99-99"))


# ─── Legal Readiness Model (Phase 4) ──────────────────────────────────────────

READY            = "READY"
PARTIALLY_READY  = "PARTIALLY_READY"
BLOCKED          = "BLOCKED"
CRITICAL_GAP     = "CRITICAL_GAP"
UNKNOWN          = "UNKNOWN"

READINESS_STATES = (READY, PARTIALLY_READY, BLOCKED, CRITICAL_GAP, UNKNOWN)

# Operation Single Brain (2026-08-07): this exact dict -- {CRITICAL_GAP: 50, BLOCKED: 65}
# -- was independently copy-pasted into 3 GPT success-probability generators
# (routers/hearing_cc.py, routers/digital_twin.py, routers/court_predictor.py), each with
# its own comment explaining it "reuses the same threshold as the other 2 files". A future
# threshold change would need 3 synchronized edits with no compiler/test signal if one was
# missed -- the definition of a duplicate truth this mission's mandate targets. One shared
# constant now; the 3 routers import this instead of redeclaring it.
CAP_BY_READINESS = {CRITICAL_GAP: 50, BLOCKED: 65}

_BLOCKING_TIPOVI = {"PRIBAVITI_DOKAZ", "RAZRESITI_KONTRADIKCIJU"}


def compute_case_readiness(
    case_actions: list[dict] | None,
    gaps: list[dict] | None = None,
    genome_computed: bool = True,
) -> dict:
    """Deterministic 5-state Legal Readiness Model, computed exclusively from
    already-canonical signals:
      - case_actions.prioritet (shared/attention_priority.py's own canonical
        order) — the SAME priority every open action already carries, not a
        new number.
      - shared/gap_engine.py's own Gap records — specifically, whether any
        gap exists that is ONLY a GPT hypothesis (hipoteza=True) with no
        deterministic (hipoteza=False) backing, which caps confidence at
        PARTIALLY_READY even with zero open case_actions (an unconfirmed
        GPT-only concern is not the same as a clean case).

    Rules (checked in this exact order — first match wins):
      1. UNKNOWN         -- Genome has never run for this case (genome_computed=False)
                             AND no case_actions exist yet -- not enough signal to assess.
      2. CRITICAL_GAP     -- any open case_actions row has prioritet == "critical".
      3. BLOCKED          -- any open PRIBAVITI_DOKAZ/RAZRESITI_KONTRADIKCIJU
                             action has prioritet == "high" (a hard
                             prerequisite not yet critical, but blocking
                             confident progress).
      4. PARTIALLY_READY  -- any other open case_actions row exists at all
                             (medium/low/informational), OR a GPT-only
                             (hipoteza=True) gap exists with no deterministic
                             backing for the same concern.
      5. READY            -- zero open case_actions, zero unresolved gaps.

    Returns {"status": one of READINESS_STATES, "razlog": str, "izvor": list[str]}
    -- "razlog"/"izvor" so this is traceable, not a bare label (Phase 6's own
    "svaki element mora imati trag porekla" requirement)."""
    case_actions = case_actions or []
    gaps = gaps or []
    open_actions = [a for a in case_actions if a.get("status", "open") == "open"]

    if not genome_computed and not open_actions:
        return {"status": UNKNOWN, "razlog": "Genome još nije izračunat za ovaj predmet, nema dovoljno signala.", "izvor": []}

    critical = [a for a in open_actions if a.get("prioritet") == "critical"]
    if critical:
        return {
            "status": CRITICAL_GAP,
            "razlog": critical[0].get("razlog") or "Otvorena akcija kritičnog prioriteta.",
            "izvor": [a.get("dedupe_key") for a in critical if a.get("dedupe_key")],
        }

    blocking_high = [
        a for a in open_actions
        if a.get("tip") in _BLOCKING_TIPOVI and a.get("prioritet") == "high"
    ]
    if blocking_high:
        return {
            "status": BLOCKED,
            "razlog": blocking_high[0].get("razlog") or "Nedostaje dokaz ili nerazrešena kontradikcija visokog prioriteta.",
            "izvor": [a.get("dedupe_key") for a in blocking_high if a.get("dedupe_key")],
        }

    hypothesis_only = [g for g in gaps if g.get("hipoteza") is True]
    if open_actions or hypothesis_only:
        source_keys = [a.get("dedupe_key") for a in open_actions if a.get("dedupe_key")]
        source_keys += [g.get("dedupe_key") for g in hypothesis_only if g.get("dedupe_key")]
        razlog = (
            open_actions[0].get("razlog") if open_actions
            else (hypothesis_only[0].get("razlog") or "Genome sugeriše mogući nedostatak, nije potvrđeno.")
        )
        return {"status": PARTIALLY_READY, "razlog": razlog, "izvor": source_keys}

    return {"status": READY, "razlog": "Nema otvorenih akcija niti neotklonjenih praznina.", "izvor": []}

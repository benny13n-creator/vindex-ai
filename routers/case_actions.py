# -*- coding: utf-8 -*-
"""
Vindex AI — routers/case_actions.py

Program Omega, Sprint 003 (2026-08-06) — "Autonomous Legal Office / Canonical
Action Engine", Phase 6 (Worklist). Read-only surface over the ONE canonical
`case_actions` table (services/case_evolution.py::_consequence_refresh_case_actions
is the ONLY writer — see migrations/099_case_actions.sql). No module besides
that consequence may write to `case_actions`; this router never does.

Not a dashboard: an operational board. The mission's own framing — the
lawyer opens Vindex AI at 8:00 wanting an answer to exactly one question,
"What must I do today, and why?" — answered here by grouping every OPEN,
deterministically-computed action by case, ordered by priority.

Endpoints:
  GET /api/case-actions/worklist              — every open action across all
                                                  of the user's cases, grouped
                                                  by predmet, priority-ordered
  GET /api/case-actions/predmeti/{predmet_id}  — open actions for one case
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from shared.attention_priority import CANONICAL_ORDER as _PRIORITY_ORDER
from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.case_actions")
router = APIRouter(prefix="/api/case-actions", tags=["case_actions"])

# Program Omega Sprint 003's own Priority Engine — the ONE ordering. As of
# Program Omega Sprint 006 (2026-08-06, Canonical Attention Engine), this is
# an alias for shared/attention_priority.py::CANONICAL_ORDER — case_actions'
# own vocabulary IS the canonical one (see that module's own docstring for
# why), so this file keeps the name `_PRIORITY_ORDER` for every existing
# caller below, now backed by the single shared copy instead of a local
# dict. See docs/omega/CANONICAL_ATTENTION_MODEL.md.


def _sort_key(action: dict) -> tuple:
    return (_PRIORITY_ORDER.get(action.get("prioritet"), 9), action.get("rok") or "9999-12-31")


async def _fetch_open_actions(supa, predmet_ids: list[str]) -> list[dict]:
    if not predmet_ids:
        return []
    res = await asyncio.to_thread(
        lambda: supa.table("case_actions")
            .select("id,predmet_id,tip,razlog,dokaz,prioritet,rok,status,correlation_id,confidence,izvor_dokumenti,created_at,updated_at")
            .in_("predmet_id", predmet_ids)
            .eq("status", "open")
            .execute()
    )
    return list(res.data or [])


@router.get("/worklist")
async def get_worklist(request: Request, user: dict = Depends(get_current_user)):
    """Every open case_actions row for cases the current user owns, grouped
    by predmet — the daily 8:00 operational board. Each case bucket is
    counted by priority so the lawyer sees, at a glance, "Case A (2 critical
    actions), Case B (1 deadline)..." without opening a single case."""
    uid = user["user_id"]
    supa = _get_supa()

    predmeti_r = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("id,naziv").eq("user_id", uid).execute()
    )
    predmeti_rows = list(predmeti_r.data or [])
    predmet_naziv = {p["id"]: p.get("naziv") or p["id"] for p in predmeti_rows}
    predmet_ids = list(predmet_naziv.keys())

    actions = await _fetch_open_actions(supa, predmet_ids)

    by_predmet: dict[str, list[dict]] = {}
    for a in actions:
        by_predmet.setdefault(a["predmet_id"], []).append(a)

    cases = []
    for predmet_id, case_actions in by_predmet.items():
        case_actions.sort(key=_sort_key)
        broj_po_prioritetu = {p: 0 for p in _PRIORITY_ORDER}
        for a in case_actions:
            broj_po_prioritetu[a.get("prioritet", "medium")] = broj_po_prioritetu.get(a.get("prioritet", "medium"), 0) + 1
        cases.append({
            "predmet_id": predmet_id,
            "naziv": predmet_naziv.get(predmet_id, predmet_id),
            "broj_akcija": len(case_actions),
            "broj_po_prioritetu": broj_po_prioritetu,
            "akcije": case_actions,
        })

    # Cases ordered by their own most-urgent open action first.
    cases.sort(key=lambda c: _sort_key(c["akcije"][0]) if c["akcije"] else (9, "9999-12-31"))

    ukupno_kriticnih = sum(c["broj_po_prioritetu"].get("critical", 0) for c in cases)
    ukupno_visokih = sum(c["broj_po_prioritetu"].get("high", 0) for c in cases)

    return {
        "predmeta_sa_akcijama": len(cases),
        "ukupno_otvorenih_akcija": len(actions),
        "ukupno_kriticnih": ukupno_kriticnih,
        "ukupno_visokih": ukupno_visokih,
        "predmeti": cases,
    }


@router.get("/predmeti/{predmet_id}")
async def get_predmet_actions(predmet_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Open case_actions for a single case — used by a case detail view."""
    uid = user["user_id"]
    supa = _get_supa()

    own_r = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", uid).maybe_single().execute()
    )
    if not (own_r and own_r.data):
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")

    actions = await _fetch_open_actions(supa, [predmet_id])
    actions.sort(key=_sort_key)
    return {"predmet_id": predmet_id, "broj_akcija": len(actions), "akcije": actions}

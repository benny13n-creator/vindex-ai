# -*- coding: utf-8 -*-
"""
Vindex AI — routers/workspace.py

Program Omega, Sprint 004 (2026-08-06) — "Unified Legal Workspace". The ONE
canonical answer to "what does this lawyer see when they open Vindex AI" —
see docs/omega/CANONICAL_WORKSPACE_SPEC.md for the full model.

This is an AGGREGATION layer, not a new data source. Every item shown here
is read from an already-existing, already-owned table — this router writes
nothing:
  - `case_actions` (Program Omega Sprint 003) — deterministic, system-detected
    required actions. Owner: services/case_evolution.py::_consequence_refresh_case_actions.
  - `zadaci` — manually-created/assigned tasks (team task management, a
    genuinely different concept: something a human decided to track, not
    something the system detected). Owner: routers/zadaci.py.
  - `intake_jobs` (status='awaiting_review') — documents Smart Intake
    processed but a human must confirm before they become case facts.
    Owner: routers/smart_intake.py.

No new capability is invented here — every query below selects columns that
already exist for an already-established purpose. The only new "logic" is
bucketing (Today/Critical/Upcoming/Review Required/Waiting/Completed) and a
priority-vocabulary translation for `zadaci` (see `_ZADACI_PRIORITET_MAP`,
documented in WORKSPACE_DATA_OWNERSHIP.md) so items from 2 differently-worded
tables sort consistently in one list.

Endpoint:
  GET /api/workspace — the canonical operational board
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request

from routers.case_actions import _fetch_open_actions, _PRIORITY_ORDER, _sort_key
from shared.attention_priority import ZADACI_TO_CANONICAL as _ZADACI_PRIORITET_MAP
from shared.deps import _get_supa, get_current_user
from shared.query_timeout import gather_with_timeout

logger = logging.getLogger("vindex.workspace")
router = APIRouter(prefix="/api/workspace", tags=["workspace"])

# zadaci.py's own priority vocabulary ("hitno"/"visoko"/"normalan"/"nisko") is
# DIFFERENT wording for the same concept case_actions already uses
# ("critical"/"high"/"medium"/"low"). Translated here, for THIS view only —
# the underlying `zadaci` table/column is NOT touched, no migration needed.
# As of Program Omega Sprint 006, this local dict is an alias for
# shared/attention_priority.py::ZADACI_TO_CANONICAL (the one shared copy) —
# see docs/omega/CANONICAL_ATTENTION_MODEL.md.

# How far back "recently completed" looks — an operational board shows what
# JUST changed, not a full history (that already exists elsewhere: case_actions
# rows are never deleted, zadaci rows keep their own status).
_COMPLETED_WINDOW_DAYS = 3


def _normalize_case_action(a: dict, naziv: str) -> dict:
    return {
        "vrsta": "case_action",
        "id": a["id"],
        "predmet_id": a["predmet_id"],
        "predmet_naziv": naziv,
        "naslov": a.get("razlog") or a.get("tip"),
        "tip": a.get("tip"),
        "prioritet": a.get("prioritet"),
        "rok": a.get("rok"),
        "izvor": {"dokaz": a.get("dokaz"), "izvor_dokumenti": a.get("izvor_dokumenti")},
        "created_at": a.get("created_at"),
    }


def _normalize_zadatak(z: dict, naziv: str | None) -> dict:
    return {
        "vrsta": "zadatak",
        "id": z["id"],
        "predmet_id": z.get("predmet_id"),
        "predmet_naziv": naziv,
        "naslov": z.get("naziv"),
        "tip": "ZADATAK",
        "prioritet": _ZADACI_PRIORITET_MAP.get(z.get("prioritet"), "medium"),
        "rok": z.get("rok_datum"),
        "izvor": {"zadatak_status": z.get("status"), "kreirao": z.get("kreirao_uid")},
        "created_at": z.get("created_at"),
    }


def _normalize_review(job: dict, naziv: str | None) -> dict:
    return {
        "vrsta": "review",
        "id": job["id"],
        "predmet_id": job.get("predmet_id"),
        "predmet_naziv": naziv,
        "naslov": f"Pregled potreban: {job.get('original_filename') or 'dokument'}",
        "tip": "PREGLED_DOKUMENTA",
        # A pending review blocks Smart Intake's own automation for that
        # document until a human resolves it — always at least "high",
        # never silently low-priority.
        "prioritet": "high",
        "rok": None,
        "izvor": {"job_id": job["id"], "status": job.get("status")},
        "created_at": job.get("created_at"),
    }


async def _fetch_review_jobs(supa, uid: str) -> list[dict]:
    res = await asyncio.to_thread(
        lambda: supa.table("intake_jobs")
            .select("id,predmet_id,original_filename,status,created_at")
            .eq("uploaded_by", uid)
            .eq("status", "awaiting_review")
            .execute()
    )
    return list(res.data or [])


async def _fetch_waiting_zadaci(supa, uid: str) -> list[dict]:
    # Program Phoenix, Mission 015 (LIVINGSYS-DEBT-029): was .eq("status", "ceka")
    # only -- zadaci.py's own valid vocabulary is {otvoreno, u_toku, ceka, zavrseno,
    # otkazano}, and a freshly-created task defaults to "otvoreno" (routers/
    # zadaci.py's own create endpoint). A task in "otvoreno"/"u_toku" due TODAY was
    # invisible on this canonical daily board. Reuses the exact "any non-terminal
    # status counts as active" filter zadaci.py itself already applies 5 other
    # places (.not_.in_(["zavrseno","otkazano"])) instead of a narrower single-value
    # match.
    res = await asyncio.to_thread(
        lambda: supa.table("zadaci")
            .select("id,naziv,opis,prioritet,status,rok_datum,predmet_id,kreirao_uid,created_at")
            .eq("dodeljen_uid", uid)
            .not_.in_("status", ["zavrseno", "otkazano"])
            .execute()
    )
    return list(res.data or [])


async def _fetch_recently_completed(supa, predmet_ids: list[str], uid: str,
                                    degradirani: list[str] | None = None) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=_COMPLETED_WINDOW_DAYS)).isoformat()
    closed_actions_task = (
        asyncio.to_thread(
            lambda: supa.table("case_actions")
                .select("id,predmet_id,tip,razlog,prioritet,rok,dokaz,izvor_dokumenti,closed_at")
                .in_("predmet_id", predmet_ids)
                .eq("status", "closed")
                .gte("closed_at", since)
                .execute()
        )
        if predmet_ids else _empty_result()
    )
    closed_zadaci_task = asyncio.to_thread(
        lambda: supa.table("zadaci")
            .select("id,naziv,opis,prioritet,status,rok_datum,predmet_id,kreirao_uid,zavrseno_u")
            .eq("dodeljen_uid", uid)
            .eq("status", "zavrseno")
            .gte("zavrseno_u", since)
            .execute()
    )
    # Program Phoenix, Mission 013 (LIVINGSYS-DEBT-040): bounded to 15s.
    actions_res, zadaci_res = await gather_with_timeout(
        closed_actions_task, closed_zadaci_task, label="workspace.recently_completed"
    )
    # N5-A-001 (dopuna, 2026-08-19): ova dva pada su bila jedini preostali tihi
    # gutači u ovoj ruti. Bez njih bi `provera_potpuna` mogao tvrditi `True`
    # dok je korpa „Završeno nedavno" lažno prazna — dakle sam signal
    # potpunosti bi bio netačan.
    _degradirano = degradirani if degradirani is not None else []
    if isinstance(actions_res, Exception):
        logger.error("[WORKSPACE] izvor 'zavrsene akcije' NIJE procitan: %s", actions_res)
        _degradirano.append("završene akcije")
    if isinstance(zadaci_res, Exception):
        logger.error("[WORKSPACE] izvor 'zavrseni zadaci' NIJE procitan: %s", zadaci_res)
        _degradirano.append("završeni zadaci")
    closed_actions = (actions_res.data if not isinstance(actions_res, Exception) else []) or []
    closed_zadaci = (zadaci_res.data if not isinstance(zadaci_res, Exception) else []) or []
    return closed_actions, closed_zadaci


async def _empty_result():
    class _R:
        data = []
    return _R()


@router.get("")
async def get_workspace(request: Request, user: dict = Depends(get_current_user)):
    """The canonical operational board: Today, Critical, Upcoming, Review
    Required, Waiting, Completed. Every bucket is grounded in a real,
    already-owned data source — see the module docstring."""
    uid = user["user_id"]
    supa = _get_supa()
    danas = date.today().isoformat()

    # Program Phoenix, Mission 013 (LIVINGSYS-DEBT-040): bounded to 15s -- a
    # timeout degrades to an empty case-name map (predmet_ids=[]), which the
    # rest of this function already treats as a valid, empty-board input
    # (see _fetch_recently_completed's own existing predmet_ids-empty branch).
    #
    # Final Beta Gate F18 (CRITICAL): this query had no status filter at all,
    # so a closed/archived case's still-open case_actions rows kept showing
    # up on the daily Workspace board -- the ONE screen a lawyer checks every
    # morning. The sibling endpoint get_worklist (routers/case_actions.py)
    # already carries this exact filter (Phoenix Mission 001,
    # LIVINGSYS-DEBT-036) -- this applies the same fix here.
    # N5-A-001 — PRAZNA TABLA IZ PALOG UPITA NIJE „SVE JE POD KONTROLOM".
    #
    # `single_with_timeout` na timeout vraća `_EmptyResult()` čiji je `.data`
    # prazna lista (njegova sopstvena „fail-open philosophy"), a gather ispod
    # je izuzetke svodio na `[]` uz `logger.warning` — dakle SAMO na server.
    # Rezultat: `ukupno_aktivnih == 0` i `static/vindex.js:1848` iscrta zeleni
    # ✓ „Sve je pod kontrolom — Nema otvorenih akcija koje zahtevaju pažnju."
    # na ekranu koji advokat gleda svako jutro. Odgovor pri padu bio je
    # identičan odgovoru pri stvarno praznoj tabli.
    #
    # `gather_with_timeout` se koristi i za ovaj jedan upit jer na timeout
    # vraća `TimeoutError` koji se MOŽE prepoznati — `single_with_timeout`
    # vraća prazan rezultat koji se ne može razlikovati od stvarno praznog.
    # Isti obrazac objave koji `routers/kalendar.py` već koristi
    # (`degraded_sources`), bez menjanja HTTP ugovora.
    degradirani_izvori: list[str] = []

    (predmeti_r,) = await gather_with_timeout(
        asyncio.to_thread(
            lambda: supa.table("predmeti").select("id,naziv").eq("user_id", uid)
                .not_.in_("status", ["zatvoren", "arhiviran", "odbijen"]).execute()
        ),
        label="workspace.predmeti",
    )
    if isinstance(predmeti_r, Exception):
        logger.error("[WORKSPACE] izvor 'predmeti' NIJE procitan: %s", predmeti_r)
        degradirani_izvori.append("predmeti")
        _predmeti_data: list = []
    else:
        _predmeti_data = predmeti_r.data or []
    predmet_naziv = {p["id"]: p.get("naziv") or p["id"] for p in _predmeti_data}
    predmet_ids = list(predmet_naziv.keys())

    # Program Lambda, Certification 004 (2026-08-06): Reliability Architect
    # fork found (Adversarial Certification-confirmed) this gather had no
    # return_exceptions=True, unlike this same file's own
    # _fetch_recently_completed gather (line ~151) -- a transient failure
    # in ANY ONE of these 3 sub-fetches raised unhandled, taking down the
    # WHOLE daily operational board (Today/Critical/Upcoming/Review/Waiting
    # all lost together) even when only one data source hiccupped. Now
    # degrades gracefully per-bucket, matching the sibling gather's own
    # already-correct pattern.
    # Program Phoenix, Mission 013 (LIVINGSYS-DEBT-040): bounded to 15s.
    _actions_r, _zadaci_r, _review_r = await gather_with_timeout(
        _fetch_open_actions(supa, predmet_ids),
        _fetch_waiting_zadaci(supa, uid),
        _fetch_review_jobs(supa, uid),
        label="workspace.main",
    )
    for _name, _res in (("otvorene akcije", _actions_r), ("zadaci na čekanju", _zadaci_r), ("stavke za pregled", _review_r)):
        if isinstance(_res, Exception):
            # N5-A-001: ranije samo `logger.warning` — korisnik nije saznao ništa.
            logger.error("[WORKSPACE] izvor '%s' NIJE procitan: %s", _name, _res)
            degradirani_izvori.append(_name)
    actions = _actions_r if not isinstance(_actions_r, Exception) else []
    zadaci_ceka = _zadaci_r if not isinstance(_zadaci_r, Exception) else []
    review_jobs = _review_r if not isinstance(_review_r, Exception) else []
    # `degradirani_izvori` se prosleđuje kao akumulator, a ne vraća kao treća
    # vrednost: povratni ugovor (2-torka) ostaje netaknut za sve pozivaoce.
    closed_actions, closed_zadaci = await _fetch_recently_completed(
        supa, predmet_ids, uid, degradirani=degradirani_izvori)

    danas_stavke: list[dict] = []
    kriticno_stavke: list[dict] = []
    predstojece_stavke: list[dict] = []

    for a in actions:
        item = _normalize_case_action(a, predmet_naziv.get(a["predmet_id"], a["predmet_id"]))
        if item["rok"] == danas:
            danas_stavke.append(item)
        elif item["prioritet"] == "critical":
            kriticno_stavke.append(item)
        elif item["prioritet"] in ("high", "medium"):
            predstojece_stavke.append(item)
        # low/informational open actions exist but don't crowd the daily
        # board — still reachable via GET /api/case-actions/predmeti/{id}.

    for z in zadaci_ceka:
        if z.get("rok_datum") == danas:
            danas_stavke.append(_normalize_zadatak(z, predmet_naziv.get(z.get("predmet_id"))))

    za_pregled_stavke = [_normalize_review(j, predmet_naziv.get(j.get("predmet_id"))) for j in review_jobs]
    na_cekanju_stavke = [
        _normalize_zadatak(z, predmet_naziv.get(z.get("predmet_id")))
        for z in zadaci_ceka if z.get("rok_datum") != danas
    ]

    zavrseno_stavke = (
        [_normalize_case_action(a, predmet_naziv.get(a["predmet_id"], a["predmet_id"])) for a in closed_actions]
        + [_normalize_zadatak(z, predmet_naziv.get(z.get("predmet_id"))) for z in closed_zadaci]
    )

    for bucket in (danas_stavke, kriticno_stavke, predstojece_stavke, za_pregled_stavke, na_cekanju_stavke):
        bucket.sort(key=_sort_key)
    zavrseno_stavke.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    ukupno_aktivnih = (
        len(danas_stavke) + len(kriticno_stavke) + len(predstojece_stavke)
        + len(za_pregled_stavke) + len(na_cekanju_stavke)
    )
    predmeta_sa_akcijama = len({
        item["predmet_id"] for item in (danas_stavke + kriticno_stavke + predstojece_stavke)
        if item.get("predmet_id")
    })

    return {
        "generisano": datetime.now(timezone.utc).isoformat(),
        "danas": danas_stavke,
        "kriticno": kriticno_stavke,
        "predstojece": predstojece_stavke,
        "za_pregled": za_pregled_stavke,
        "na_cekanju": na_cekanju_stavke,
        "zavrseno_nedavno": zavrseno_stavke,
        "ukupno_aktivnih": ukupno_aktivnih,
        "predmeta_sa_akcijama": predmeta_sa_akcijama,
        # N5-A-001: bez ovog polja frontend ne može da razlikuje „nema ničega"
        # od „nismo uspeli da pročitamo". Prazna lista = provera je potpuna.
        "degradirani_izvori": degradirani_izvori,
        "provera_potpuna": not degradirani_izvori,
    }

# -*- coding: utf-8 -*-
"""
Vindex AI — Portfolio Intelligence

GET /portfolio/dashboard  — firma-level pregled: aktivni predmeti, rokovi,
                             neaktivni, hitni dogadjaji, distribucija po tipu/statusu
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.portfolio")
router = APIRouter(tags=["portfolio"])


@router.get("/portfolio/dashboard")
@limiter.limit("30/minute")
async def portfolio_dashboard(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Firma-level intelligence dashboard.
    Vraca: aktivni predmeti, distribucija, rokovi 7/14 dana,
    neaktivni 30 dana, hitni rokovi, narativni summary.
    """
    uid = user["user_id"]
    supa = _get_supa()

    today     = date.today()
    today_iso = today.isoformat()
    in_7_iso  = (today + timedelta(days=7)).isoformat()
    in_14_iso = (today + timedelta(days=14)).isoformat()
    ago_30    = (today - timedelta(days=30)).isoformat()

    # ── Parallel fetch ────────────────────────────────────────────────────────
    predmeti_r, rokovi_r, hron_recent_r, bel_recent_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id, naziv, tip, status, updated_at")
            .eq("user_id", uid)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("predmet_id, dogadjaj, datum_iso, vaznost")
            .eq("user_id", uid)
            .gte("datum_iso", today_iso)
            .lte("datum_iso", in_14_iso)
            .order("datum_iso")
            .limit(50)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("predmet_id")
            .eq("user_id", uid)
            .gte("created_at", ago_30)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_beleske")
            .select("predmet_id")
            .eq("user_id", uid)
            .gte("created_at", ago_30)
            .execute()),
        return_exceptions=True,
    )

    predmeti     = predmeti_r.data if not isinstance(predmeti_r, Exception) and predmeti_r.data else []
    rokovi       = rokovi_r.data if not isinstance(rokovi_r, Exception) and rokovi_r.data else []
    hron_pids    = {r["predmet_id"] for r in (hron_recent_r.data or [])} if not isinstance(hron_recent_r, Exception) else set()
    bel_pids     = {r["predmet_id"] for r in (bel_recent_r.data or [])} if not isinstance(bel_recent_r, Exception) else set()
    active_pids  = hron_pids | bel_pids

    pred_by_id: dict[str, dict] = {p["id"]: p for p in predmeti}

    # ── Distribucija ──────────────────────────────────────────────────────────
    po_statusu: dict[str, int] = {}
    po_tipu: dict[str, int] = {}
    aktivni_count = 0

    for p in predmeti:
        s = p.get("status") or "aktivan"
        t = p.get("tip") or "opsti"
        po_statusu[s] = po_statusu.get(s, 0) + 1
        po_tipu[t] = po_tipu.get(t, 0) + 1
        if s not in ("zatvoren", "arhiviran", "odbijen"):
            aktivni_count += 1

    # ── Rokovi ────────────────────────────────────────────────────────────────
    rokovi_7:  list[dict] = []
    rokovi_14: list[dict] = []

    for r in rokovi:
        pid = r.get("predmet_id", "")
        datum = r.get("datum_iso") or ""
        entry = {
            "predmet_id":    pid,
            "predmet_naziv": pred_by_id.get(pid, {}).get("naziv", "Nepoznat predmet"),
            "dogadjaj":      r.get("dogadjaj", ""),
            "datum_iso":     datum,
            "vaznost":       r.get("vaznost", ""),
        }
        if datum <= in_7_iso:
            rokovi_7.append(entry)
        else:
            rokovi_14.append(entry)

    hitni_rokovi = [r for r in rokovi_7 if r.get("vaznost") == "kritičan"]

    # ── Neaktivni predmeti (30+ dana bez beleske/hronologije) ─────────────────
    neaktivni: list[dict] = []
    for p in predmeti:
        if p.get("status") in ("zatvoren", "arhiviran"):
            continue
        if p["id"] not in active_pids:
            neaktivni.append({
                "predmet_id":         p["id"],
                "naziv":              p.get("naziv", ""),
                "poslednja_izmena":   (p.get("updated_at") or "")[:10],
            })

    # ── Narativni summary ─────────────────────────────────────────────────────
    delovi = [f"Portfolio: {aktivni_count} aktivnih predmeta."]
    if rokovi_7:
        delovi.append(f"{len(rokovi_7)} rok{'a' if len(rokovi_7) != 1 else ''} u narednih 7 dana.")
    if hitni_rokovi:
        delovi.append(f"⚠ {len(hitni_rokovi)} HITNIH rokova odmah!")
    if neaktivni:
        delovi.append(f"{len(neaktivni)} predmet{'a' if len(neaktivni) != 1 else ''} bez aktivnosti 30+ dana.")
    if not rokovi_7 and not neaktivni:
        delovi.append("Sve je pod kontrolom — nema hitnih rokova ni neaktivnih predmeta.")

    return {
        "ukupno_predmeta":   len(predmeti),
        "ukupno_aktivnih":   aktivni_count,
        "po_statusu":        po_statusu,
        "po_tipu":           po_tipu,
        "rokovi_7_dana":     rokovi_7,
        "rokovi_14_dana":    rokovi_14,
        "hitni_rokovi":      hitni_rokovi,
        "neaktivni_30_dana": neaktivni,
        "summary":           " ".join(delovi),
    }

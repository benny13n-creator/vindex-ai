# -*- coding: utf-8 -*-
"""
Vindex AI — Notification Engine

GET    /notifications               — lista obaveštenja (auto-refresh > 6h)
POST   /notifications/refresh       — forsiraj regeneraciju
PATCH  /notifications/{id}/read     — označi kao pročitano
PATCH  /notifications/read-all      — označi sva kao pročitana
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.notifications")
router = APIRouter(tags=["notifications"])

_REFRESH_HOURS = 6


async def _generate_notifications(uid: str) -> int:
    """
    Generiše nova obaveštenja:
      - Rokovi u narednih 7 dana (tip: rok / hitan_rok)
      - Predmeti bez aktivnosti 30+ dana (tip: neaktivnost)
    Pre upisivanja briše stare neprocitane iste kategorije.
    Vraca broj generisanih.
    """
    supa = _get_supa()
    today     = date.today()
    today_iso = today.isoformat()
    in_7_iso  = (today + timedelta(days=7)).isoformat()
    in_2_iso  = (today + timedelta(days=2)).isoformat()
    ago_30    = (today - timedelta(days=30)).isoformat()

    new_notifs: list[dict] = []

    # ── 1. Rokovi u narednih 7 dana ───────────────────────────────────────────
    try:
        rokovi_r, predmeti_r = await asyncio.gather(
            asyncio.to_thread(lambda: supa.table("predmet_hronologija")
                .select("predmet_id, dogadjaj, datum_iso, vaznost")
                .eq("user_id", uid)
                .gte("datum_iso", today_iso)
                .lte("datum_iso", in_7_iso)
                .order("datum_iso")
                .limit(30)
                .execute()),
            asyncio.to_thread(lambda: supa.table("predmeti")
                .select("id, naziv")
                .eq("user_id", uid)
                .execute()),
            return_exceptions=True,
        )
        pred_map: dict[str, str] = {}
        if not isinstance(predmeti_r, Exception) and predmeti_r.data:
            pred_map = {p["id"]: p.get("naziv", "") for p in predmeti_r.data}

        if not isinstance(rokovi_r, Exception):
            for r in (rokovi_r.data or []):
                pid   = r.get("predmet_id", "")
                naziv = pred_map.get(pid, "Predmet")
                datum = r.get("datum_iso", "")
                hitan = datum <= in_2_iso
                new_notifs.append({
                    "user_id":    uid,
                    "tip":        "hitan_rok" if hitan else "rok",
                    "naslov":     f"{'⚠ Hitan rok' if hitan else 'Nadolazeći rok'} — {naziv}",
                    "poruka":     f"{r.get('dogadjaj', '')} ({datum})",
                    "predmet_id": pid,
                    "prioritet":  "hitan" if hitan else "normalan",
                })
    except Exception as e:
        logger.error("[NOTIF-GEN] rokovi greška: %s", e)

    # ── 2. Predmeti bez aktivnosti 30+ dana ───────────────────────────────────
    try:
        pred_r, hron_r, bel_r = await asyncio.gather(
            asyncio.to_thread(lambda: supa.table("predmeti")
                .select("id, naziv, status")
                .eq("user_id", uid)
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
        active_pids: set[str] = set()
        if not isinstance(hron_r, Exception):
            active_pids |= {r["predmet_id"] for r in (hron_r.data or [])}
        if not isinstance(bel_r, Exception):
            active_pids |= {r["predmet_id"] for r in (bel_r.data or [])}

        if not isinstance(pred_r, Exception):
            for p in (pred_r.data or []):
                if p.get("status") in ("zatvoren", "arhiviran"):
                    continue
                if p["id"] not in active_pids:
                    new_notifs.append({
                        "user_id":    uid,
                        "tip":        "neaktivnost",
                        "naslov":     f"Predmet bez aktivnosti — {p.get('naziv', '')}",
                        "poruka":     "Nema beleški ni događaja u poslednjih 30 dana.",
                        "predmet_id": p["id"],
                        "prioritet":  "info",
                    })
    except Exception as e:
        logger.error("[NOTIF-GEN] neaktivnost greška: %s", e)

    if not new_notifs:
        return 0

    # ── Briši stare neprocitane iste kategorije ───────────────────────────────
    tipovi = list({n["tip"] for n in new_notifs})
    try:
        await asyncio.to_thread(
            lambda: supa.table("notifications")
                .delete()
                .eq("user_id", uid)
                .eq("procitano", False)
                .in_("tip", tipovi)
                .execute()
        )
    except Exception as e:
        logger.warning("[NOTIF-GEN] brisanje starih greška: %s", e)

    # ── Upiši nova ────────────────────────────────────────────────────────────
    try:
        await asyncio.to_thread(
            lambda: supa.table("notifications").insert(new_notifs).execute()
        )
    except Exception as e:
        logger.error("[NOTIF-GEN] insert greška: %s", e)
        return 0

    return len(new_notifs)


@router.get("/notifications")
@limiter.limit("60/minute")
async def get_notifications(
    request: Request,
    user: dict = Depends(get_current_user),
    samo_neprocitane: bool = False,
):
    """
    Vraca lista obaveštenja. Ako je prošlo > 6h od poslednje generacije,
    pokreće auto-refresh u pozadini.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    # Auto-refresh provera
    try:
        last_r = await asyncio.to_thread(
            lambda: supa.table("notifications")
                .select("created_at")
                .eq("user_id", uid)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
        )
        last_ts = None
        if last_r.data:
            ts_str = last_r.data[0].get("created_at", "")
            if ts_str:
                try:
                    last_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except Exception:
                    pass

        age_h = (
            (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
            if last_ts else 999
        )
        if age_h > _REFRESH_HOURS:
            asyncio.create_task(_generate_notifications(uid))

    except Exception as e:
        logger.error("[NOTIF] auto-refresh provera greška: %s", e)

    # Fetch
    try:
        q = supa.table("notifications").select("*").eq("user_id", uid)
        if samo_neprocitane:
            q = q.eq("procitano", False)
        r = await asyncio.to_thread(
            lambda: q.order("created_at", desc=True).limit(50).execute()
        )
        data = r.data or []
        neprocitane = sum(1 for n in data if not n.get("procitano"))
        return {
            "notifications": data,
            "ukupno":        len(data),
            "neprocitane":   neprocitane,
        }
    except Exception as e:
        logger.error("[NOTIF] fetch greška: %s", e)
        return {"notifications": [], "ukupno": 0, "neprocitane": 0}


@router.post("/notifications/refresh")
@limiter.limit("5/minute")
async def refresh_notifications(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Forsiraj regeneraciju obaveštenja (sinhrono)."""
    n = await _generate_notifications(user["user_id"])
    return {"generisano": n, "ok": True}


@router.patch("/notifications/read-all")
@limiter.limit("30/minute")
async def mark_all_read(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Označi sva obaveštenja kao pročitana."""
    uid  = user["user_id"]
    supa = _get_supa()
    try:
        await asyncio.to_thread(
            lambda: supa.table("notifications")
                .update({"procitano": True})
                .eq("user_id", uid)
                .eq("procitano", False)
                .execute()
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Greška pri ažuriranju.")


@router.patch("/notifications/{notif_id}/read")
@limiter.limit("120/minute")
async def mark_read(
    notif_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Označi jedno obaveštenje kao pročitano."""
    uid  = user["user_id"]
    supa = _get_supa()
    try:
        await asyncio.to_thread(
            lambda: supa.table("notifications")
                .update({"procitano": True})
                .eq("id", notif_id)
                .eq("user_id", uid)
                .execute()
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Greška pri ažuriranju.")

# -*- coding: utf-8 -*-
"""
Vindex OS — routers/dashboard.py
Faza: Vindex OS

GET /api/dashboard/command-center  — agregirani OS pregled (PRIORITET 1)
GET /api/predmeti/{id}/health      — Matter Health Score 0-100 (PRIORITET 2)
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.dashboard")
router = APIRouter(tags=["dashboard"])

_RISK_LEVEL = {"nizak": 1, "srednji": 2, "visok": 3}


# ─── Command Center ───────────────────────────────────────────────────────────

@router.get("/api/dashboard/command-center")
@limiter.limit("30/minute")
async def command_center(
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    today      = date.today()
    today_iso  = today.isoformat()
    in_2_iso   = (today + timedelta(days=2)).isoformat()
    in_7_iso   = (today + timedelta(days=7)).isoformat()
    ago_30_iso = (today - timedelta(days=30)).isoformat()
    ago_24h    = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    # ── 7 parallel batch queries ──────────────────────────────────────────────
    (predmeti_r, rocista_r, rokovi_r, risk_r,
     beleske_r, dokumenti_r, ist_recent_r) = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id,naziv,tip,status,updated_at")
            .eq("user_id", uid)
            .execute()),
        asyncio.to_thread(lambda: supa.table("rocista")
            .select("id,predmet_id,sud,datum,vreme,status")
            .eq("user_id", uid)
            .eq("datum", today_iso)
            .order("vreme")
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("predmet_id,dogadjaj,datum_iso,vaznost")
            .eq("user_id", uid)
            .gte("datum_iso", today_iso)
            .lte("datum_iso", in_7_iso)
            .order("datum_iso")
            .limit(100)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("predmet_id,odgovor,created_at")
            .eq("user_id", uid)
            .like("pitanje", "[Rizik]%")
            .order("created_at", desc=True)
            .limit(300)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_beleske")
            .select("predmet_id")
            .eq("user_id", uid)
            .gte("created_at", ago_30_iso)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti")
            .select("id,naziv_fajla,predmet_id,created_at")
            .eq("user_id", uid)
            .gte("created_at", ago_24h)
            .order("created_at", desc=True)
            .limit(20)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("predmet_id")
            .eq("user_id", uid)
            .gte("created_at", ago_30_iso)
            .execute()),
        return_exceptions=True,
    )

    def _safe(r):
        if isinstance(r, Exception):
            return []
        return r.data or []

    predmeti   = _safe(predmeti_r)
    pred_by_id = {p["id"]: p for p in predmeti}
    aktivni    = [p for p in predmeti if p.get("status") not in ("zatvoren", "arhiviran", "odbijen")]
    aktivni_count = len(aktivni)

    # Top 5 aktivnih predmeta za KC panel (sortiran po updated_at)
    top_aktivni_predmeti = [
        {"id": p["id"], "naziv": p.get("naziv", "—"), "status": p.get("status", "—"), "tip": p.get("tip", "")}
        for p in sorted(aktivni, key=lambda p: p.get("updated_at") or "", reverse=True)[:5]
    ]

    # 1. Danasnja ročišta
    danasnja_rocista = [
        {
            "id":            r.get("id"),
            "predmet_id":    r.get("predmet_id", ""),
            "predmet_naziv": pred_by_id.get(r.get("predmet_id", ""), {}).get("naziv", "—"),
            "sud":           r.get("sud", ""),
            "vreme":         (r.get("vreme") or "")[:5],
            "status":        r.get("status", ""),
        }
        for r in _safe(rocista_r)
    ]

    # 2. Rokovi 7 dana + hitni (<48h)
    rokovi_7 = [
        {
            "predmet_id":    h.get("predmet_id", ""),
            "predmet_naziv": pred_by_id.get(h.get("predmet_id", ""), {}).get("naziv", "—"),
            "dogadjaj":      h.get("dogadjaj", ""),
            "datum_iso":     h.get("datum_iso", ""),
            "vaznost":       h.get("vaznost", ""),
        }
        for h in _safe(rokovi_r)
    ]
    hitni_rokovi = [r for r in rokovi_7 if (r.get("datum_iso") or "9999") <= in_2_iso]

    # 3. Visok rizik + pad procene (from risk history)
    risk_by_pred: dict[str, list] = {}
    for r in _safe(risk_r):
        pid = r.get("predmet_id")
        if pid and len(risk_by_pred.get(pid, [])) < 2:
            try:
                risk_by_pred.setdefault(pid, []).append(json.loads(r.get("odgovor", "{}")))
            except Exception:
                pass

    predmeti_visok_rizik: list[dict] = []
    pad_procene: list[dict] = []
    for pid, risks in risk_by_pred.items():
        if not risks:
            continue
        nivo = risks[0].get("nivo", "")
        if nivo == "visok":
            predmeti_visok_rizik.append({
                "predmet_id":    pid,
                "predmet_naziv": pred_by_id.get(pid, {}).get("naziv", "—"),
                "rizik_nivo":    nivo,
                "faktori":       risks[0].get("faktori_minus", [])[:3],
            })
        if len(risks) >= 2:
            prev_nivo = risks[1].get("nivo", "")
            if _RISK_LEVEL.get(nivo, 0) > _RISK_LEVEL.get(prev_nivo, 0):
                pad_procene.append({
                    "predmet_id":      pid,
                    "predmet_naziv":   pred_by_id.get(pid, {}).get("naziv", "—"),
                    "prethodni_rizik": prev_nivo,
                    "trenutni_rizik":  nivo,
                })

    # 4. Neaktivni predmeti (>30 dana)
    active_pids = (
        {r.get("predmet_id") for r in _safe(beleske_r)}
        | {r.get("predmet_id") for r in _safe(ist_recent_r)}
    )
    neaktivni_predmeti = [
        {
            "predmet_id":      p["id"],
            "naziv":           p.get("naziv", ""),
            "poslednja_izmena": (p.get("updated_at") or "")[:10],
        }
        for p in aktivni
        if p["id"] not in active_pids
    ]

    # 5. Novi dokumenti (zadnjih 24h)
    novi_dokumenti = [
        {
            "id":            d.get("id"),
            "predmet_id":    d.get("predmet_id", ""),
            "predmet_naziv": pred_by_id.get(d.get("predmet_id", ""), {}).get("naziv", "—"),
            "naziv_fajla":   d.get("naziv_fajla", ""),
            "created_at":    d.get("created_at", ""),
        }
        for d in _safe(dokumenti_r)
    ]

    # 6. AI preporuke (rule-based — without AI call)
    preporuke: list[str] = []
    if danasnja_rocista:
        n = len(danasnja_rocista)
        preporuke.append(f"Danas imate {n} ročiš{'te' if n == 1 else 'ta'} — proverite pripremu.")
    if hitni_rokovi:
        n = len(hitni_rokovi)
        preporuke.append(f"⚠ {n} hitan{'ih' if n > 1 else ''} rok{'ova' if n > 1 else ''} ističe za <48h — odmah reagujte.")
    if predmeti_visok_rizik:
        n = len(predmeti_visok_rizik)
        preporuke.append(f"{n} predmet{'a' if n > 1 else ''} visokog rizika zahteva pažnju.")
    if pad_procene:
        n = len(pad_procene)
        preporuke.append(f"Rizik se pogoršao na {n} predmet{'a' if n > 1 else ''} — analizirajte.")
    if novi_dokumenti:
        n = len(novi_dokumenti)
        preporuke.append(f"{n} novi{'h' if n > 1 else ''} dokument{'a' if n > 1 else ''} — pokrenite AI analizu.")
    if neaktivni_predmeti:
        n = len(neaktivni_predmeti)
        preporuke.append(f"{n} predmet{'a' if n > 1 else ''} bez aktivnosti >30 dana — proverite status.")

    summary = " ".join(preporuke[:2]) if preporuke else "Sve je pod kontrolom — nema hitnih upozorenja."

    return {
        # Backward compatible with existing /portfolio/dashboard consumer
        "ukupno_predmeta":   len(predmeti),
        "ukupno_aktivnih":   aktivni_count,
        "rokovi_7_dana":     rokovi_7,
        "hitni_rokovi":      hitni_rokovi,
        "neaktivni_30_dana": neaktivni_predmeti,
        "summary":           summary,
        # New OS fields
        "danasnja_rocista":     danasnja_rocista,
        "predmeti_visok_rizik": predmeti_visok_rizik,
        "pad_procene":          pad_procene,
        "novi_dokumenti":       novi_dokumenti,
        "ai_preporuke":         preporuke,
        "top_aktivni_predmeti": top_aktivni_predmeti,
        "statistike": {
            "ukupno_aktivnih":      aktivni_count,
            "danasnja_rocista":     len(danasnja_rocista),
            "hitni_rokovi":         len(hitni_rokovi),
            "predmeti_visok_rizik": len(predmeti_visok_rizik),
            "pad_procene":          len(pad_procene),
            "novi_dokumenti":       len(novi_dokumenti),
            "neaktivni":            len(neaktivni_predmeti),
        },
    }


# ─── Matter Health Score ──────────────────────────────────────────────────────

@router.get("/api/predmeti/{predmet_id}/health")
@limiter.limit("60/minute")
async def matter_health_score(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    today     = date.today()
    today_iso = today.isoformat()
    in_2_iso  = (today + timedelta(days=2)).isoformat()
    ago_7_iso = (today - timedelta(days=7)).isoformat()

    # Verify ownership + parallel fetch
    pred_r, bel_r, risk_r, kom_r, hron_r, dok_r, roc_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id,status").eq("id", predmet_id).eq("user_id", uid).limit(1).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_beleske")
            .select("id").eq("predmet_id", predmet_id).gte("created_at", ago_7_iso).limit(1).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("odgovor").eq("predmet_id", predmet_id)
            .like("pitanje", "[Rizik]%").order("created_at", desc=True).limit(1).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_komentari")
            .select("id").eq("predmet_id", predmet_id).gte("kreirano", ago_7_iso).limit(1).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("datum_iso,vaznost").eq("predmet_id", predmet_id)
            .gte("datum_iso", today_iso).order("datum_iso").limit(20).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti")
            .select("id").eq("predmet_id", predmet_id).limit(50).execute()),
        asyncio.to_thread(lambda: supa.table("rocista")
            .select("datum").eq("predmet_id", predmet_id).gte("datum", today_iso).limit(1).execute()),
        return_exceptions=True,
    )

    if isinstance(pred_r, Exception) or not (pred_r.data if not isinstance(pred_r, Exception) else []):
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    score    = 0
    razlozi: list[str] = []

    def _ok(r):
        return not isinstance(r, Exception) and bool(r.data)

    # Aktivnost: 0-25
    if _ok(bel_r) or _ok(kom_r):
        score += 25
    else:
        razlozi.append("Nema aktivnosti (beleška/komentar) u poslednjih 7 dana")

    # Procena rizika: 0-25
    if _ok(risk_r):
        try:
            risk = json.loads(risk_r.data[0].get("odgovor", "{}"))
            nivo = risk.get("nivo", "")
            if nivo == "nizak":
                score += 25
            elif nivo == "srednji":
                score += 13
                razlozi.append("Srednji nivo rizika — razmotriti mere")
            else:
                razlozi.append("Visok nivo rizika — hitna pažnja")
        except Exception:
            score += 8
            razlozi.append("Procena rizika nije parsabilna — ponovo analizirajte")
    else:
        score += 8
        razlozi.append("Nedostaje procena rizika — pokrenite analizu predmeta")

    # Rokovi: 0-25
    hron_data = (hron_r.data if not isinstance(hron_r, Exception) else []) or []
    hitni = [h for h in hron_data if (h.get("datum_iso") or "9999") <= in_2_iso and h.get("vaznost") == "kritičan"]
    if not hitni:
        score += 25
    elif len(hitni) == 1:
        score += 12
        razlozi.append("1 hitan rok u narednih 48h")
    else:
        razlozi.append(f"{len(hitni)} hitnih rokova u narednih 48h")

    # Dokumentacija: 0-15
    dok_count = len((dok_r.data if not isinstance(dok_r, Exception) else []) or [])
    if dok_count >= 5:
        score += 15
    elif dok_count >= 2:
        score += 10
    elif dok_count >= 1:
        score += 5
        razlozi.append("Mala dokumentacija — dodajte relevantne dokumente")
    else:
        razlozi.append("Nema dokumenata — dodajte dokumentaciju predmeta")

    # Ročište: 0-10
    if _ok(roc_r):
        score += 10
    else:
        razlozi.append("Nema zakazanih ročišta")

    if score >= 75:
        status = "zdrav"
    elif score >= 50:
        status = "upozorenje"
    else:
        status = "kriticno"

    return {
        "predmet_id": predmet_id,
        "score":      score,
        "status":     status,
        "razlozi":    razlozi,
        "faktori": {
            "aktivnost":     min(25, score if score <= 25 else 25),
            "dokumentacija": dok_count,
            "hitnih_rokova": len(hitni),
            "ima_rociste":   _ok(roc_r),
        },
    }

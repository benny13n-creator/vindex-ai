# -*- coding: utf-8 -*-
"""
Vindex OS — routers/inbox.py
Faza: Vindex OS — PRIORITET 3

GET /api/inbox  — Unified Inbox: agregirani, sortirani feed svih aktivnosti
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.inbox")
router = APIRouter(tags=["inbox"])

_PRIORITET_ORDER = {"kriticno": 0, "visok": 1, "srednji": 2, "nizak": 3}


@router.get("/api/inbox")
@limiter.limit("30/minute")
async def unified_inbox(
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
    ago_7_iso  = (today - timedelta(days=7)).isoformat()

    # ── Batch fetch ───────────────────────────────────────────────────────────
    (predmeti_r, rocista_r, rokovi_r,
     dokumenti_r, billing_r, beleske_r, ist_r) = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id,naziv,status")
            .eq("user_id", uid)
            .execute()),
        asyncio.to_thread(lambda: supa.table("rocista")
            .select("id,predmet_id,sud,datum,vreme,status")
            .eq("user_id", uid)
            .gte("datum", today_iso)
            .lte("datum", in_7_iso)
            .order("datum")
            .limit(50)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("predmet_id,dogadjaj,datum_iso,vaznost")
            .eq("user_id", uid)
            .gte("datum_iso", today_iso)
            .lte("datum_iso", in_7_iso)
            .order("datum_iso")
            .limit(100)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti")
            .select("id,predmet_id,naziv_fajla,created_at")
            .eq("user_id", uid)
            .gte("created_at", ago_24h)
            .order("created_at", desc=True)
            .limit(20)
            .execute()),
        asyncio.to_thread(lambda: supa.table("billing_entries")
            .select("id,predmet_id,opis,iznos_rsd,datum")
            .eq("user_id", uid)
            .eq("obracunato", False)
            .lte("datum", ago_7_iso)
            .order("datum")
            .limit(30)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_beleske")
            .select("predmet_id")
            .eq("user_id", uid)
            .gte("created_at", ago_30_iso)
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
    aktivni    = [p for p in predmeti if p.get("status") not in ("zatvoren", "arhiviran", "odbijen")]
    pred_by_id = {p["id"]: p for p in predmeti}

    items: list[dict] = []

    # ── Ročišta (next 7 days) ─────────────────────────────────────────────────
    for r in _safe(rocista_r):
        datum = r.get("datum", "")
        prioritet = "kriticno" if datum <= in_2_iso else "visok"
        lbl = "DANAS" if datum == today_iso else datum
        items.append({
            "tip":           "rociste",
            "prioritet":     prioritet,
            "naslov":        f"Ročište — {r.get('sud', '—')}",
            "opis":          f"{lbl} u {(r.get('vreme') or '?')[:5]}",
            "predmet_id":    r.get("predmet_id", ""),
            "predmet_naziv": pred_by_id.get(r.get("predmet_id", ""), {}).get("naziv", "—"),
            "datum":         datum,
            "id":            r.get("id", ""),
        })

    # ── Rokovi (next 7 days) ──────────────────────────────────────────────────
    for h in _safe(rokovi_r):
        datum    = h.get("datum_iso", "")
        vaznost  = h.get("vaznost", "")
        if datum <= in_2_iso or vaznost == "kritičan":
            prioritet = "kriticno"
        elif vaznost == "bitan":
            prioritet = "visok"
        else:
            prioritet = "srednji"
        items.append({
            "tip":           "rok",
            "prioritet":     prioritet,
            "naslov":        h.get("dogadjaj", "Rok"),
            "opis":          datum,
            "predmet_id":    h.get("predmet_id", ""),
            "predmet_naziv": pred_by_id.get(h.get("predmet_id", ""), {}).get("naziv", "—"),
            "datum":         datum,
            "id":            "",
        })

    # ── Novi dokumenti (last 24h) ─────────────────────────────────────────────
    for d in _safe(dokumenti_r):
        items.append({
            "tip":           "dokument",
            "prioritet":     "srednji",
            "naslov":        d.get("naziv_fajla", "Dokument"),
            "opis":          "Novi dokument — pokrenite AI analizu",
            "predmet_id":    d.get("predmet_id", ""),
            "predmet_naziv": pred_by_id.get(d.get("predmet_id", ""), {}).get("naziv", "—"),
            "datum":         (d.get("created_at") or "")[:10],
            "id":            d.get("id", ""),
        })

    # ── Nenaplaćene stavke (>7 dana stare, nije obračunato) ──────────────────
    for b in _safe(billing_r):
        items.append({
            "tip":           "naplata",
            "prioritet":     "nizak",
            "naslov":        f"Nenaplaćena stavka — {b.get('opis', '')[:60]}",
            "opis":          f"{int(b.get('iznos_rsd') or 0):,} RSD — nije fakturisano",
            "predmet_id":    b.get("predmet_id", ""),
            "predmet_naziv": pred_by_id.get(b.get("predmet_id", ""), {}).get("naziv", "—"),
            "datum":         b.get("datum", ""),
            "id":            b.get("id", ""),
        })

    # ── Neaktivni predmeti (>30 dana) ─────────────────────────────────────────
    active_pids = (
        {r.get("predmet_id") for r in _safe(beleske_r)}
        | {r.get("predmet_id") for r in _safe(ist_r)}
    )
    for p in aktivni:
        if p["id"] not in active_pids:
            items.append({
                "tip":           "neaktivan",
                "prioritet":     "nizak",
                "naslov":        f"Predmet bez aktivnosti — {p.get('naziv', '—')}",
                "opis":          "Bez beleški ili analiza >30 dana",
                "predmet_id":    p["id"],
                "predmet_naziv": p.get("naziv", "—"),
                "datum":         (p.get("updated_at") or "")[:10],
                "id":            p["id"],
            })

    # ── Sort: prioritet → datum ───────────────────────────────────────────────
    items.sort(key=lambda x: (
        _PRIORITET_ORDER.get(x["prioritet"], 9),
        x.get("datum") or "9999-12-31",
    ))

    return {
        "stavke":   items,
        "ukupno":   len(items),
        "kriticno": sum(1 for i in items if i["prioritet"] == "kriticno"),
        "visok":    sum(1 for i in items if i["prioritet"] == "visok"),
        "srednji":  sum(1 for i in items if i["prioritet"] == "srednji"),
        "nizak":    sum(1 for i in items if i["prioritet"] == "nizak"),
    }

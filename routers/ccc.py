# -*- coding: utf-8 -*-
"""
Case Command Center — jedan API poziv koji agregira sve podatke predmeta.

GET /api/ccc/predmeti/{predmet_id}
Vraća: predmet, matter_intel, dokazi, rokovi, billing, aktivnosti, sudska_praksa
"""
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.ccc")
router = APIRouter(prefix="/api/ccc", tags=["ccc"])


@router.get("/predmeti/{predmet_id}")
async def get_ccc(predmet_id: str, user=Depends(get_current_user)):
    supa = _get_supa()
    uid  = user["user_id"]

    # ── Ownership check ─────────────────────────────────────────────────────
    pr = supa.table("predmeti").select(
        "id,naziv,tip,status,oblast,tuzilac,tuzeni,rizik,vrednost_spora,opis,created_at"
    ).eq("id", predmet_id).eq("user_id", uid).execute()
    if not pr.data:
        raise HTTPException(status_code=404)
    predmet = pr.data[0]

    # ── Dokazi statistika ────────────────────────────────────────────────────
    dokazi_r = supa.table("predmet_dokazi").select(
        "snaga,kategorija"
    ).eq("predmet_id", predmet_id).is_("deleted_at", "null").execute()
    dokazi = dokazi_r.data or []
    dok_stats = {"jaka": 0, "srednja": 0, "slaba": 0, "ukupno": len(dokazi)}
    for d in dokazi:
        s = d.get("snaga", "srednja")
        if s in dok_stats:
            dok_stats[s] += 1

    # ── Dokumenti broji ─────────────────────────────────────────────────────
    dok_count_r = supa.table("predmet_dokumenti").select("id,tip_dokaza").eq(
        "predmet_id", predmet_id).is_("deleted_at", "null").execute()
    tip_stat: dict = {}
    for d in (dok_count_r.data or []):
        t = d.get("tip_dokaza") or "neklafikovan"
        tip_stat[t] = tip_stat.get(t, 0) + 1

    # ── Rokovi (sledeći 60 dana) ─────────────────────────────────────────────
    rok_r = supa.table("predmet_rokovi").select(
        "id,naziv,datum_isteka,status"
    ).eq("predmet_id", predmet_id).order("datum_isteka").limit(10).execute()
    now = datetime.now(timezone.utc)
    rokovi_data = []
    predstojeći = 0
    for r in (rok_r.data or []):
        dana = None
        try:
            dt_str = r.get("datum_isteka", "")
            if dt_str:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                dana = (dt - now).days
                if 0 <= dana <= 30:
                    predstojeći += 1
        except Exception:
            pass
        rokovi_data.append({**r, "dana_ostalo": dana})

    # ── Billing summary ──────────────────────────────────────────────────────
    billing_data = {"uneseno": 0, "nenaplaceno": 0, "naplaceno": 0}
    try:
        be_r = supa.table("billing_entries").select(
            "iznos,obracunato"
        ).eq("predmet_id", predmet_id).is_("deleted_at", "null").execute()
        for e in (be_r.data or []):
            iznos = float(e.get("iznos") or 0)
            billing_data["uneseno"] += iznos
            if e.get("obracunato"):
                billing_data["naplaceno"] += iznos
            else:
                billing_data["nenaplaceno"] += iznos
    except Exception as exc:
        logger.debug("[CCC] billing greška: %s", exc)

    # ── Tim aktivnosti (iz hronologije, posled. 8) ───────────────────────────
    hron_r = supa.table("predmet_hronologija").select(
        "dogadjaj,akter,datum,vaznost"
    ).eq("predmet_id", predmet_id).order("datum_iso", desc=True).limit(8).execute()

    # ── Klijenti ─────────────────────────────────────────────────────────────
    klijenti = []
    try:
        kl_r = supa.table("predmet_klijenti").select(
            "uloga,klijenti(ime,prezime,firma)"
        ).eq("predmet_id", predmet_id).limit(4).execute()
        for k in (kl_r.data or []):
            ki = k.get("klijenti") or {}
            klijenti.append({
                "uloga": k.get("uloga", ""),
                "ime": ((ki.get("ime","") + " " + ki.get("prezime","")).strip()
                        or ki.get("firma","Klijent"))
            })
    except Exception as exc:
        logger.debug("[CCC] klijenti greška: %s", exc)

    # ── Matter Intelligence (brzo, bez GPT-a) ───────────────────────────────
    health_score = _compute_health(dok_stats, predstojeći, len(dokazi))

    return {
        "predmet":          predmet,
        "klijenti":         klijenti,
        "dok_stats":        dok_stats,
        "tip_stat":         tip_stat,
        "rokovi":           rokovi_data,
        "predstojeći":      predstojeći,
        "billing":          billing_data,
        "aktivnosti":       hron_r.data or [],
        "health_score":     health_score,
    }


def _compute_health(dok_stats: dict, predstojeći: int, ukupno_dokaza: int) -> int:
    score = 50  # baseline
    jaka   = dok_stats.get("jaka", 0)
    srednja = dok_stats.get("srednja", 0)
    slaba  = dok_stats.get("slaba", 0)
    if ukupno_dokaza == 0:
        score -= 15
    else:
        score += min(25, jaka * 8 + srednja * 3 - slaba * 5)
    if predstojeći == 0:
        score += 10
    elif predstojeći <= 2:
        score -= 5
    else:
        score -= 15
    return max(0, min(100, score))

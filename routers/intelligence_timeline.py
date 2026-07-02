# -*- coding: utf-8 -*-
"""
Intelligence Timeline — "život predmeta"
Agregira događaje iz 5 tabela u jedan hronološki tok.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.intel_timeline")
router = APIRouter(prefix="/api/predmeti", tags=["intelligence_timeline"])

_MESECI = ["", "jan", "feb", "mar", "apr", "maj", "jun", "jul", "avg", "sep", "okt", "nov", "dec"]


def _fmt(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return f"{dt.day}. {_MESECI[dt.month]} {dt.year}."
    except Exception:
        return (iso or "")[:10]


def _sort_key(ev: dict) -> str:
    return ev.get("datum_iso") or "0000-00-00"


@router.get("/{predmet_id}/intelligence-timeline")
async def intelligence_timeline(predmet_id: str, user=Depends(get_current_user)):
    supa = _get_supa()
    uid = user["user_id"]

    pr = supa.table("predmeti").select(
        "id,naziv,status,oblast,tip,created_at,case_dna"
    ).eq("id", predmet_id).eq("user_id", uid).execute()
    if not pr.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")
    predmet = pr.data[0]

    events: list[dict] = []

    # 1) Predmet otvoren
    cr = predmet.get("created_at") or ""
    events.append({
        "tip": "predmet_otvoren",
        "datum_iso": cr,
        "datum_label": _fmt(cr),
        "naslov": "Predmet otvoren",
        "detalj": predmet.get("naziv") or "",
        "ikona": "📁",
        "boja": "#4aa8ff",
    })

    # 2) Dokumenti
    try:
        dok_r = supa.table("predmet_dokumenti").select(
            "naziv_fajla,created_at,velicina_kb"
        ).eq("predmet_id", predmet_id).eq("user_id", uid).order("created_at").execute()
        for d in dok_r.data or []:
            cr_d = d.get("created_at") or ""
            kb = d.get("velicina_kb") or 0
            events.append({
                "tip": "dokument",
                "datum_iso": cr_d,
                "datum_label": _fmt(cr_d),
                "naslov": d.get("naziv_fajla") or "Dokument",
                "detalj": f"{int(kb)} KB" if kb else "",
                "ikona": "📎",
                "boja": "#c9a84c",
            })
    except Exception as e:
        logger.warning("[ITL] dokumenti: %s", e)

    # 3) Ročišta
    try:
        roc_r = supa.table("rocista").select(
            "sud,datum,vreme,status,napomena"
        ).eq("predmet_id", predmet_id).eq("user_id", uid).order("datum").execute()
        for r in roc_r.data or []:
            datum_str = r.get("datum") or ""
            vreme_str = (r.get("vreme") or "09:00")[:5]
            iso = f"{datum_str}T{vreme_str}:00" if datum_str else ""
            status_roc = r.get("status") or ""
            badge = "✓ odrzano" if status_roc == "odrzano" else ("⟳ odlozeno" if status_roc == "odlozeno" else None)
            events.append({
                "tip": "rociste",
                "datum_iso": iso,
                "datum_label": _fmt(iso),
                "naslov": r.get("sud") or "Ročište",
                "detalj": r.get("napomena") or "",
                "ikona": "⚖️",
                "boja": "#a78bfa",
                "badge": badge,
                "status": status_roc,
            })
    except Exception as e:
        logger.warning("[ITL] rocista: %s", e)

    # 4) Hronologija (AI-generisana iz dokumenata)
    try:
        hron_r = supa.table("predmet_hronologija").select(
            "dogadjaj,akter,datum,datum_iso,vaznost"
        ).eq("predmet_id", predmet_id).eq("user_id", uid).order("datum_iso").execute()
        for h in hron_r.data or []:
            iso_h = h.get("datum_iso") or h.get("datum") or ""
            vaznost = h.get("vaznost") or "informativan"
            boja = "#ff6060" if vaznost == "kritican" else "#ffaa40" if vaznost == "vazan" else "#4aa8ff"
            events.append({
                "tip": "hronologija",
                "datum_iso": iso_h,
                "datum_label": _fmt(iso_h),
                "naslov": h.get("dogadjaj") or "",
                "detalj": h.get("akter") or "",
                "ikona": "📋",
                "boja": boja,
                "vaznost": vaznost,
            })
    except Exception as e:
        logger.warning("[ITL] hronologija: %s", e)

    # 5) Genome promene (consecutive deltas iz genome_history)
    try:
        ghr = supa.table("predmet_genome_history").select(
            "snaga_procent,verzija,created_at,trigger_event"
        ).eq("predmet_id", predmet_id).eq("user_id", uid).order("created_at").execute()
        hist = ghr.data or []
        current_dna = predmet.get("case_dna") or {}
        current_score = current_dna.get("snaga_predmeta_procent")

        for i, h in enumerate(hist):
            stari = h.get("snaga_procent")
            if stari is None:
                continue
            novi = hist[i + 1].get("snaga_procent") if i + 1 < len(hist) else current_score
            if novi is None:
                continue
            delta = int(novi) - int(stari)
            badge = f"+{delta}" if delta >= 0 else str(delta)
            boja_g = "#7de0a0" if delta >= 0 else "#ff9090"
            cr_g = h.get("created_at") or ""
            events.append({
                "tip": "genome",
                "datum_iso": cr_g,
                "datum_label": _fmt(cr_g),
                "naslov": "Procena predmeta ažurirana",
                "detalj": f"{int(stari)}% → {int(novi)}%",
                "ikona": "🧬",
                "boja": boja_g,
                "badge": badge,
                "score_old": int(stari),
                "score_new": int(novi),
            })
    except Exception as e:
        logger.warning("[ITL] genome_history: %s", e)

    # 6) Predmet zatvoren
    if predmet.get("status") == "zatvoren":
        all_tmp = sorted(events, key=_sort_key)
        last_iso = all_tmp[-1]["datum_iso"] if all_tmp else cr
        events.append({
            "tip": "predmet_zatvoren",
            "datum_iso": last_iso,
            "datum_label": _fmt(last_iso),
            "naslov": "Predmet zatvoren",
            "detalj": predmet.get("naziv") or "",
            "ikona": "✅",
            "boja": "#7de0a0",
        })

    events_sorted = sorted(events, key=_sort_key)
    return {
        "events": events_sorted,
        "predmet": {
            "naziv": predmet.get("naziv"),
            "status": predmet.get("status"),
        },
        "ukupno": len(events_sorted),
    }

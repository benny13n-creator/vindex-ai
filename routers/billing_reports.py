# -*- coding: utf-8 -*-
"""
Vindex AI — routers/billing_reports.py

Billing izveštaji i export:

GET /billing/report/godisnji?godina=YYYY     — godišnji pregled s mesečnim breakdownom
GET /billing/report/csv?od=&do=              — CSV export stavki za period
GET /billing/report/zastarele               — aging: 0-30/31-60/61-90/90+ dana
GET /billing/report/po-tipu                 — prihodi grupisani po tipu predmeta
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.billing_reports")
router = APIRouter(prefix="/billing/report", tags=["billing"])


def _db(fn):
    return asyncio.to_thread(fn)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _month_range(godina: int) -> list[str]:
    return [f"{godina}-{m:02d}" for m in range(1, 13)]


def _ym(iso_date: str) -> str:
    return iso_date[:7] if iso_date else ""


# ─── GET /billing/report/godisnji ────────────────────────────────────────────

@router.get("/godisnji")
@limiter.limit("20/minute")
async def billing_godisnji(
    request: Request,
    godina:  Optional[int] = None,
    user:    dict          = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    if godina is None:
        godina = date.today().year
    if godina < 2000 or godina > 2100:
        raise HTTPException(status_code=422, detail="Nevalidna godina.")

    od = f"{godina}-01-01"
    do = f"{godina}-12-31"

    entries_r, fakture_r, predmeti_r, klijenti_r = await asyncio.gather(
        _db(lambda: supa.table("billing_entries")
            .select("iznos_rsd, datum, obracunato, predmet_id")
            .eq("user_id", uid)
            .gte("datum", od).lte("datum", do)
            .execute()),
        _db(lambda: supa.table("fakture")
            .select("iznos_sa_pdv, iznos_rsd, status, datum_fakture, klijent_id")
            .eq("user_id", uid)
            .gte("datum_fakture", od).lte("datum_fakture", do)
            .execute()),
        _db(lambda: supa.table("predmeti")
            .select("id, naziv, tip")
            .eq("user_id", uid)
            .execute()),
        _db(lambda: supa.table("klijenti")
            .select("id, ime, prezime, naziv_firme")
            .eq("user_id", uid)
            .execute()),
        return_exceptions=True,
    )

    entries  = (entries_r.data  or []) if not isinstance(entries_r,  Exception) else []
    fakture  = (fakture_r.data  or []) if not isinstance(fakture_r,  Exception) else []
    predmeti = (predmeti_r.data or []) if not isinstance(predmeti_r, Exception) else []
    klijenti = (klijenti_r.data or []) if not isinstance(klijenti_r, Exception) else []

    pred_map = {p["id"]: p for p in predmeti}
    kl_map   = {k["id"]: " ".join(filter(None, [k.get("ime"), k.get("prezime"), k.get("naziv_firme")])) for k in klijenti}

    # Mesečni breakdown
    meseci: dict[str, dict] = {m: {"mesec": m, "uneseno": 0.0, "naplaceno": 0.0, "stavki": 0} for m in _month_range(godina)}
    for e in entries:
        ym = _ym(e.get("datum", ""))
        if ym in meseci:
            meseci[ym]["uneseno"] += float(e.get("iznos_rsd") or 0)
            meseci[ym]["stavki"]  += 1
    for f in fakture:
        ym = _ym(f.get("datum_fakture", ""))
        if ym in meseci and f.get("status") == "placena":
            meseci[ym]["naplaceno"] += float(f.get("iznos_sa_pdv") or 0)

    # Ukupni KPIs
    ukupno_uneseno  = sum(float(e.get("iznos_rsd") or 0) for e in entries)
    ukupno_naplaceno = sum(float(f.get("iznos_sa_pdv") or 0) for f in fakture if f.get("status") == "placena")
    ukupno_fakturisano = sum(float(f.get("iznos_sa_pdv") or 0) for f in fakture)
    stopa = round(ukupno_naplaceno / ukupno_fakturisano * 100, 1) if ukupno_fakturisano else 0.0

    # Top klijenti (po fakturisanom)
    kl_iznosi: dict[str, float] = {}
    for f in fakture:
        kid = f.get("klijent_id") or "_bez_klijenta"
        kl_iznosi[kid] = kl_iznosi.get(kid, 0.0) + float(f.get("iznos_sa_pdv") or 0)
    top_klijenti = sorted(
        [{"klijent_id": kid, "naziv": kl_map.get(kid, "—"), "iznos": round(izn, 2)}
         for kid, izn in kl_iznosi.items() if kid != "_bez_klijenta"],
        key=lambda x: x["iznos"], reverse=True
    )[:5]

    # Top tipovi predmeta
    tip_iznosi: dict[str, float] = {}
    tip_brojevi: dict[str, set] = {}
    for e in entries:
        pid  = e.get("predmet_id", "")
        pred = pred_map.get(pid, {})
        tip  = pred.get("tip") or "ostalo"
        tip_iznosi[tip]  = tip_iznosi.get(tip, 0.0) + float(e.get("iznos_rsd") or 0)
        tip_brojevi.setdefault(tip, set()).add(pid)
    top_tipovi = sorted(
        [{"tip": t, "iznos": round(izn, 2), "predmeta": len(tip_brojevi.get(t, set()))}
         for t, izn in tip_iznosi.items()],
        key=lambda x: x["iznos"], reverse=True
    )[:5]

    return {
        "godina":              godina,
        "ukupno_uneseno_rsd":  round(ukupno_uneseno, 2),
        "ukupno_fakturisano":  round(ukupno_fakturisano, 2),
        "ukupno_naplaceno_rsd": round(ukupno_naplaceno, 2),
        "stopa_naplate_pct":   stopa,
        "po_mesecima":         list(meseci.values()),
        "top_klijenti":        top_klijenti,
        "top_tipovi_predmeta": top_tipovi,
    }


# ─── GET /billing/report/csv ─────────────────────────────────────────────────

@router.get("/csv")
@limiter.limit("10/minute")
async def billing_csv_export(
    request: Request,
    od:      Optional[str] = None,
    do:      Optional[str] = None,
    user:    dict          = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    today    = date.today()
    od_date  = od or date(today.year, 1, 1).isoformat()
    do_date  = do or today.isoformat()

    try:
        date.fromisoformat(od_date)
        date.fromisoformat(do_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Nevalidan format datuma (YYYY-MM-DD).")

    entries_r, predmeti_r, klijenti_r = await asyncio.gather(
        _db(lambda: supa.table("billing_entries")
            .select("datum, predmet_id, klijent_id, tarifa_sifra, tarifa_naziv, opis, sati, iznos_rsd, obracunato, faktura_id")
            .eq("user_id", uid)
            .gte("datum", od_date).lte("datum", do_date)
            .order("datum")
            .execute()),
        _db(lambda: supa.table("predmeti").select("id, naziv").eq("user_id", uid).execute()),
        _db(lambda: supa.table("klijenti").select("id, ime, prezime, naziv_firme").eq("user_id", uid).execute()),
        return_exceptions=True,
    )

    entries  = (entries_r.data  or []) if not isinstance(entries_r,  Exception) else []
    predmeti = (predmeti_r.data or []) if not isinstance(predmeti_r, Exception) else []
    klijenti = (klijenti_r.data or []) if not isinstance(klijenti_r, Exception) else []

    pred_map = {p["id"]: p.get("naziv", "") for p in predmeti}
    kl_map   = {k["id"]: " ".join(filter(None, [k.get("ime"), k.get("prezime"), k.get("naziv_firme")])) for k in klijenti}

    buf = io.StringIO()
    w   = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    w.writerow(["Datum", "Predmet", "Klijent", "Šifra tarife", "Naziv tarife", "Opis", "Sati", "Iznos RSD", "Obračunato", "Faktura ID"])

    for e in entries:
        w.writerow([
            e.get("datum", ""),
            pred_map.get(e.get("predmet_id", ""), ""),
            kl_map.get(e.get("klijent_id", ""), ""),
            e.get("tarifa_sifra", ""),
            e.get("tarifa_naziv", ""),
            e.get("opis", ""),
            e.get("sati", ""),
            e.get("iznos_rsd", ""),
            "da" if e.get("obracunato") else "ne",
            e.get("faktura_id", ""),
        ])

    filename = f"billing_{od_date}_{do_date}.csv"
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── GET /billing/report/zastarele ───────────────────────────────────────────

@router.get("/zastarele")
@limiter.limit("20/minute")
async def billing_zastarele(
    request: Request,
    user:    dict = Depends(get_current_user),
):
    """Nenaplaćene stavke grupisane po starosti (aging report)."""
    uid   = user["user_id"]
    supa  = _get_supa()
    today = date.today()

    entries_r, klijenti_r = await asyncio.gather(
        _db(lambda: supa.table("billing_entries")
            .select("id, datum, iznos_rsd, opis, predmet_id, klijent_id")
            .eq("user_id", uid)
            .eq("obracunato", False)
            .order("datum")
            .execute()),
        _db(lambda: supa.table("klijenti")
            .select("id, ime, prezime, naziv_firme")
            .eq("user_id", uid)
            .execute()),
        return_exceptions=True,
    )

    entries  = (entries_r.data  or []) if not isinstance(entries_r,  Exception) else []
    klijenti = (klijenti_r.data or []) if not isinstance(klijenti_r, Exception) else []
    kl_map   = {k["id"]: " ".join(filter(None, [k.get("ime"), k.get("prezime"), k.get("naziv_firme")])) for k in klijenti}

    buckets = {
        "do_30_dana":  {"iznos": 0.0, "stavki": 0, "stavke": []},
        "31_60_dana":  {"iznos": 0.0, "stavki": 0, "stavke": []},
        "61_90_dana":  {"iznos": 0.0, "stavki": 0, "stavke": []},
        "starije_90":  {"iznos": 0.0, "stavki": 0, "stavke": []},
    }
    kl_iznosi: dict[str, float] = {}

    for e in entries:
        try:
            d    = date.fromisoformat(e.get("datum", today.isoformat()))
            dana = (today - d).days
        except ValueError:
            dana = 0

        if   dana <= 30:  bucket = "do_30_dana"
        elif dana <= 60:  bucket = "31_60_dana"
        elif dana <= 90:  bucket = "61_90_dana"
        else:             bucket = "starije_90"

        iznos = float(e.get("iznos_rsd") or 0)
        buckets[bucket]["iznos"]  += iznos
        buckets[bucket]["stavki"] += 1
        buckets[bucket]["stavke"].append({
            "id":          e["id"],
            "datum":       e.get("datum"),
            "opis":        e.get("opis"),
            "iznos_rsd":   iznos,
            "predmet_id":  e.get("predmet_id"),
            "dana_staro":  dana,
        })

        kid = e.get("klijent_id") or "_"
        kl_iznosi[kid] = kl_iznosi.get(kid, 0.0) + iznos

    for b in buckets.values():
        b["iznos"] = round(b["iznos"], 2)

    top_duznici = sorted(
        [{"klijent_id": kid, "naziv": kl_map.get(kid, "—"), "iznos": round(izn, 2)}
         for kid, izn in kl_iznosi.items() if kid != "_"],
        key=lambda x: x["iznos"], reverse=True
    )[:10]

    ukupno = round(sum(b["iznos"] for b in buckets.values()), 2)
    return {
        "ukupno_nenaplaceno_rsd": ukupno,
        "aging":                  buckets,
        "top_duznici":            top_duznici,
    }


# ─── GET /billing/report/po-tipu ─────────────────────────────────────────────

@router.get("/po-tipu")
@limiter.limit("20/minute")
async def billing_po_tipu(
    request: Request,
    od:      Optional[str] = None,
    do:      Optional[str] = None,
    user:    dict          = Depends(get_current_user),
):
    """Prihodi grupisani po tipu predmeta — koja oblast prava donosi najviše prihoda."""
    uid  = user["user_id"]
    supa = _get_supa()

    today   = date.today()
    od_date = od or date(today.year, 1, 1).isoformat()
    do_date = do or today.isoformat()

    entries_r, predmeti_r = await asyncio.gather(
        _db(lambda: supa.table("billing_entries")
            .select("iznos_rsd, predmet_id, sati")
            .eq("user_id", uid)
            .gte("datum", od_date).lte("datum", do_date)
            .execute()),
        _db(lambda: supa.table("predmeti")
            .select("id, tip, naziv")
            .eq("user_id", uid)
            .execute()),
        return_exceptions=True,
    )

    entries  = (entries_r.data  or []) if not isinstance(entries_r,  Exception) else []
    predmeti = (predmeti_r.data or []) if not isinstance(predmeti_r, Exception) else []
    pred_map = {p["id"]: p for p in predmeti}

    tipovi: dict[str, dict] = {}
    for e in entries:
        pred = pred_map.get(e.get("predmet_id", ""), {})
        tip  = pred.get("tip") or "ostalo"
        if tip not in tipovi:
            tipovi[tip] = {"tip": tip, "iznos_rsd": 0.0, "stavki": 0, "sati": 0.0, "predmeta": set()}
        tipovi[tip]["iznos_rsd"] += float(e.get("iznos_rsd") or 0)
        tipovi[tip]["stavki"]    += 1
        tipovi[tip]["sati"]      += float(e.get("sati") or 0)
        if e.get("predmet_id"):
            tipovi[tip]["predmeta"].add(e["predmet_id"])

    ukupno_iznos = sum(t["iznos_rsd"] for t in tipovi.values())
    result = sorted([
        {
            "tip":          t["tip"],
            "iznos_rsd":    round(t["iznos_rsd"], 2),
            "stavki":       t["stavki"],
            "sati":         round(t["sati"], 2),
            "predmeta":     len(t["predmeta"]),
            "ucesce_pct":   round(t["iznos_rsd"] / ukupno_iznos * 100, 1) if ukupno_iznos else 0.0,
        }
        for t in tipovi.values()
    ], key=lambda x: x["iznos_rsd"], reverse=True)

    return {
        "od":           od_date,
        "do":           do_date,
        "ukupno_rsd":   round(ukupno_iznos, 2),
        "po_tipu":      result,
    }

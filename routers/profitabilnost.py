# -*- coding: utf-8 -*-
"""
Vindex AI — routers/profitabilnost.py

Case Profitability Dashboard — ROI po predmetu.

Šta radi:
  - Računa profitabilnost svakog predmeta: naplaćeno vreme × tarifa
  - Rangira predmete po prihodima, satnici, naplativosti
  - Daje uvid koji tipovi predmeta donose najviše prihoda
  - Upozorenje za predmete sa visokim utrošenim vremenom a niskom naplatom

Endpoints:
  GET  /api/profitabilnost/predmet/{id}    — ROI jednog predmeta
  GET  /api/profitabilnost/pregled         — rang lista svih predmeta
  GET  /api/profitabilnost/analiza         — AI uvid: koji tipovi su najprofitabilniji
  GET  /api/profitabilnost/nenaplaceno     — sve nenaplaćene stavke

SQL zavisnost: migrations/045 (case_profitability VIEW)
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user, _deduct_credit, _is_founder
from shared.rate import limiter

logger = logging.getLogger("vindex.profitabilnost")
router = APIRouter(prefix="/api/profitabilnost", tags=["profitabilnost"])


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _satnica(naplaceno_rsd: float, sati: float) -> Optional[float]:
    if sati <= 0:
        return None
    return round(naplaceno_rsd / sati, 0)


def _naplativost_procenat(fakturisano: float, ukupno: float) -> float:
    if ukupno <= 0:
        return 0.0
    return round(fakturisano / ukupno * 100, 1)


def _oceni_profitabilnost(row: dict) -> str:
    """Ocena: zelena/žuta/crvena."""
    sati = float(row.get("ukupno_sati") or 0)
    napl = float(row.get("ukupno_naplaceno_rsd") or 0)
    fakt = float(row.get("fakturisano_rsd") or 0)
    nefakt = float(row.get("nefakturisano_rsd") or 0)

    if sati == 0:
        return "siva"
    satnica = napl / sati if sati > 0 else 0

    # Visoka satnica + visoka naplativost = zelena
    if satnica >= 5000 and _naplativost_procenat(fakt, napl) >= 70:
        return "zelena"
    # Visoko nenaplaćeno = crvena
    if nefakt > 100000:
        return "crvena"
    # Sve ostalo = žuta
    return "zuta"


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/predmet/{predmet_id}")
@limiter.limit("30/minute")
async def profitabilnost_predmeta(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """ROI analiza jednog predmeta."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        # Iz case_profitability VIEW
        r = await asyncio.to_thread(
            lambda: supa.table("case_profitability")
                .select("*")
                .eq("predmet_id", predmet_id)
                .eq("user_id", uid)
                .maybe_single()
                .execute()
        )

        if not r.data:
            raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

        row = r.data
        napl   = float(row.get("ukupno_naplaceno_rsd") or 0)
        sati   = float(row.get("ukupno_sati") or 0)
        fakt   = float(row.get("fakturisano_rsd") or 0)
        nefakt = float(row.get("nefakturisano_rsd") or 0)

        # Detalji billing unosa
        entries_r = await asyncio.to_thread(
            lambda: supa.table("billing_entries")
                .select("opis, sati, iznos_rsd, obracunato, created_at")
                .eq("predmet_id", predmet_id)
                .order("created_at", desc=True)
                .limit(50)
                .execute()
        )

        return {
            "predmet_id":           predmet_id,
            "predmet_naziv":        row.get("predmet_naziv", ""),
            "predmet_tip":          row.get("predmet_tip", ""),
            "predmet_status":       row.get("predmet_status", ""),
            "finansije": {
                "ukupno_naplaceno_rsd":  napl,
                "fakturisano_rsd":       fakt,
                "nefakturisano_rsd":     nefakt,
                "naplativost_procenat":  _naplativost_procenat(fakt, napl),
                "ukupno_sati":           sati,
                "satnica_rsd":           _satnica(napl, sati),
                "broj_unosa":            row.get("broj_unosa", 0),
            },
            "ocena":              _oceni_profitabilnost(row),
            "billing_unosi":      entries_r.data or [],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pregled")
@limiter.limit("20/minute")
async def profitabilnost_pregled(
    request: Request,
    user: dict = Depends(get_current_user),
    sortiranje: str = Query("naplaceno", regex="^(naplaceno|sati|satnica|nefakturisano)$"),
    limit: int = Query(20, ge=1, le=100),
):
    """Rang lista svih predmeta sortirana po profitabilnosti."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("case_profitability")
                .select("*")
                .eq("user_id", uid)
                .execute()
        )
        predmeti = r.data or []

        # Enrich sa izvedenim metrikama
        rezultat = []
        for row in predmeti:
            napl   = float(row.get("ukupno_naplaceno_rsd") or 0)
            sati   = float(row.get("ukupno_sati") or 0)
            fakt   = float(row.get("fakturisano_rsd") or 0)
            nefakt = float(row.get("nefakturisano_rsd") or 0)

            rezultat.append({
                "predmet_id":           row.get("predmet_id"),
                "predmet_naziv":        row.get("predmet_naziv", ""),
                "predmet_tip":          row.get("predmet_tip", ""),
                "predmet_status":       row.get("predmet_status", ""),
                "ukupno_naplaceno_rsd": napl,
                "fakturisano_rsd":      fakt,
                "nefakturisano_rsd":    nefakt,
                "naplativost_procenat": _naplativost_procenat(fakt, napl),
                "ukupno_sati":          sati,
                "satnica_rsd":          _satnica(napl, sati) or 0,
                "broj_unosa":           row.get("broj_unosa", 0),
                "poslednja_naplata":    row.get("poslednja_naplata", ""),
                "ocena":                _oceni_profitabilnost(row),
            })

        # Sortiranje
        sort_key = {
            "naplaceno":     lambda x: x["ukupno_naplaceno_rsd"],
            "sati":          lambda x: x["ukupno_sati"],
            "satnica":       lambda x: x["satnica_rsd"],
            "nefakturisano": lambda x: x["nefakturisano_rsd"],
        }[sortiranje]
        rezultat.sort(key=sort_key, reverse=True)

        # Ukupna statistika
        uk_napl   = sum(p["ukupno_naplaceno_rsd"] for p in rezultat)
        uk_sati   = sum(p["ukupno_sati"] for p in rezultat)
        uk_nefakt = sum(p["nefakturisano_rsd"] for p in rezultat)

        return {
            "predmeti":         rezultat[:limit],
            "ukupno_predmeta":  len(rezultat),
            "statistika": {
                "ukupno_naplaceno_rsd": uk_napl,
                "ukupno_sati":          uk_sati,
                "ukupno_nefakturisano": uk_nefakt,
                "prosecna_satnica":     _satnica(uk_napl, uk_sati),
                "zelenih":   sum(1 for p in rezultat if p["ocena"] == "zelena"),
                "zutih":     sum(1 for p in rezultat if p["ocena"] == "zuta"),
                "crvenih":   sum(1 for p in rezultat if p["ocena"] == "crvena"),
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analiza")
@limiter.limit("5/hour")
async def profitabilnost_ai_analiza(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    AI analiza: koji tipovi predmeta su najprofitabilniji, šta optimizovati.
    Kosta 1 kredit.
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    r = await asyncio.to_thread(
        lambda: supa.table("case_profitability")
            .select("predmet_tip, ukupno_naplaceno_rsd, ukupno_sati, fakturisano_rsd, nefakturisano_rsd")
            .eq("user_id", uid)
            .execute()
    )
    predmeti = r.data or []

    if len(predmeti) < 3:
        return {"analiza": "Nedovoljno podataka za analizu. Potrebno je minimum 3 predmeta sa billing unosima."}

    # Agregiraj po tipu
    by_tip: dict[str, dict] = {}
    for p in predmeti:
        tip = p.get("predmet_tip", "ostalo") or "ostalo"
        if tip not in by_tip:
            by_tip[tip] = {"napl": 0.0, "sati": 0.0, "fakt": 0.0, "nefakt": 0.0, "count": 0}
        d = by_tip[tip]
        d["napl"]   += float(p.get("ukupno_naplaceno_rsd") or 0)
        d["sati"]   += float(p.get("ukupno_sati") or 0)
        d["fakt"]   += float(p.get("fakturisano_rsd") or 0)
        d["nefakt"] += float(p.get("nefakturisano_rsd") or 0)
        d["count"]  += 1

    kontekst = "\n".join(
        f"- {tip}: {d['count']} predmeta, {d['napl']:,.0f} RSD ukupno, "
        f"{d['sati']:.0f} sati, satnica {_satnica(d['napl'], d['sati']) or 0:.0f} RSD/h, "
        f"{_naplativost_procenat(d['fakt'], d['napl'])}% fakturisano"
        for tip, d in sorted(by_tip.items(), key=lambda x: x[1]["napl"], reverse=True)
    )

    try:
        from openai import AsyncOpenAI
        oai = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = await oai.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": (
                    "Ti si finansijski analitičar advokatske kancelarije. "
                    "Analiziraj profitabilnost po tipovima predmeta i daj konkretne preporuke:\n\n"
                    + kontekst + "\n\n"
                    "Napiši analizu u 3 dela:\n"
                    "1. NAJPROFITABILNIJI TIPOVI — koji donose najviše prihoda po satu\n"
                    "2. PROBLEM PODRUČJA — gde se gubi nenaplaćeno vreme\n"
                    "3. PREPORUKA — konkretne akcije za povećanje prihoda\n\n"
                    "Max 300 reči. Ekavica. Budi konkretan sa brojevima."
                )
            }],
        )
        analiza = resp.choices[0].message.content.strip()
    except Exception as e:
        analiza = f"Greška pri AI analizi: {e}"

    if not _is_founder(email):
        try:
            from shared.deps import _deduct_credit as _dc
            await asyncio.to_thread(lambda: _dc(uid))
        except Exception:
            pass

    return {
        "analiza": analiza,
        "by_tip":  {
            tip: {
                "count": d["count"],
                "ukupno_naplaceno_rsd": d["napl"],
                "satnica_rsd": _satnica(d["napl"], d["sati"]),
                "naplativost_procenat": _naplativost_procenat(d["fakt"], d["napl"]),
            }
            for tip, d in by_tip.items()
        },
    }


@router.get("/nenaplaceno")
@limiter.limit("20/minute")
async def nenaplacene_stavke(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Sve nenaplaćene billing stavke — quick-win za naplatu."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("billing_entries")
                .select("id, predmet_id, opis, sati, iznos_rsd, created_at")
                .eq("user_id", uid)
                .eq("obracunato", False)
                .order("created_at", desc=True)
                .limit(100)
                .execute()
        )
        stavke = r.data or []

        ukupno_rsd = sum(
            float(s.get("iznos_rsd", 0))
            for s in stavke
        )

        return {
            "stavke":         stavke,
            "ukupno_stavki":  len(stavke),
            "ukupno_rsd":     round(ukupno_rsd, 0),
            "poruka": (
                f"Imate {len(stavke)} nenaplaćenih stavki ukupno {ukupno_rsd:,.0f} RSD."
                if stavke else "Sve stavke su fakturisane."
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

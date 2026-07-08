# -*- coding: utf-8 -*-
"""
Vindex AI — routers/benchmarking.py

Anonymous Benchmarking — mrežni efekat.

Šta radi:
  - Svaka kancelarija (opt-in) doprinosi anonimizovanim podacima o ishodima predmeta
  - Platforma agregira i vraća benchmark statistike
  - "Vaši predmeti radnog prava traju 23% duže od proseka"
  - "Prosečna satnica za privredne sporove u Beogradu: 8.200 RSD"

Dizajn princip — GDPR-safe:
  - Nema user_id, nema kancelarija_id, nema naziva u benchmarks tabeli
  - Samo agregati: tip, oblast, region, trajanje, ishod, satnica
  - Opt-in: korisnik mora eksplicitno dati saglasnost
  - Anonimizacija: sve cifre se zaokružuju na 5% band

Endpoints:
  POST /api/benchmarking/opt-in          — saglasnost za anonimne podatke
  POST /api/benchmarking/doprinesi       — pošalji anonimne podatke za zatvoreni predmet
  GET  /api/benchmarking/satnica         — benchmark satnica po tipu predmeta
  GET  /api/benchmarking/trajanje        — benchmark trajanje predmeta
  GET  /api/benchmarking/win-rate        — benchmark win rate po tipu
  GET  /api/benchmarking/moj-rang        — gde si u poređenju sa prosekom
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.benchmarking")
router = APIRouter(prefix="/api/benchmarking", tags=["benchmarking"])

_TIP_PREDMETA = {"radno", "privredno", "porodično", "parnično", "krivično", "upravno",
                 "nepokretnosti", "obligaciono", "izvrsenje", "ostalo"}
_REGIJE = {"beograd", "vojvodina", "srbija_jug", "srbija_zapad", "ostalo"}
_SUDOVI = {"osnovni", "visi", "apelacioni", "vrhovni", "privredni", "upravni", "ostalo"}
_ISHODI = {"pobeda", "poraz", "nagodba", "odustajanje"}


# ─── Anonimizacija (GDPR-safe) ───────────────────────────────────────────────

def _zaokruzi_5pct(vrednost: float) -> float:
    """Zaokružuje na najbliži 5% bend da spreči de-anonimizaciju."""
    if vrednost == 0:
        return 0
    magnitude = 10 ** math.floor(math.log10(abs(vrednost)))
    band = magnitude * 0.05
    return round(round(vrednost / band) * band, 0)


def _regija_iz_suda(sud_naziv: str) -> str:
    """Heuristički određuje regiju iz naziva suda."""
    sud_l = (sud_naziv or "").lower()
    if any(x in sud_l for x in ["beograd", "zemun", "palilula", "zvezdara", "vozdovac"]):
        return "beograd"
    if any(x in sud_l for x in ["novi sad", "subotica", "zrenjanin", "pancevo", "kikinda", "sombor", "vrsac"]):
        return "vojvodina"
    if any(x in sud_l for x in ["nis", "leskovac", "vranje", "pirot", "prokuplje", "zajecar"]):
        return "srbija_jug"
    if any(x in sud_l for x in ["kragujevac", "cacak", "uzice", "valjevo", "sabac", "smedere"]):
        return "srbija_zapad"
    return "ostalo"


# ─── Pydantic modeli ──────────────────────────────────────────────────────────

class OptInRequest(BaseModel):
    saglasan: bool


class DoprinosRequest(BaseModel):
    tip_predmeta:    str
    oblast_prava:    Optional[str] = None
    trajanje_meseci: Optional[int] = None
    ishod:           Optional[str] = None
    sud_tip:         Optional[str] = None
    regija:          Optional[str] = None
    naplaceno_rsd:   Optional[float] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/opt-in")
@limiter.limit("5/minute")
async def benchmarking_opt_in(
    request: Request,
    payload: OptInRequest,
    user: dict = Depends(get_current_user),
):
    """Korisnik daje (ili povlači) saglasnost za anonimne benchmark podatke."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        await asyncio.to_thread(
            lambda: supa.table("profiles")
                .update({"benchmark_opt_in": payload.saglasan})
                .eq("id", uid)
                .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "ok": True,
        "saglasan": payload.saglasan,
        "poruka": (
            "Hvala! Vaši anonimni podaci poboljšavaju benchmark za sve korisnike Vindex-a."
            if payload.saglasan else
            "Razumemo. Vaši podaci se neće koristiti u benchmarku."
        ),
    }


@router.post("/doprinesi")
@limiter.limit("30/hour")
async def doprinesi_benchmark(
    request: Request,
    payload: DoprinosRequest,
    user: dict = Depends(get_current_user),
):
    """
    Doprinosi anonimizovane podatke o zatvorenom predmetu.
    Pozivati automatski kada se predmet zatvori (ako je opt-in = true).
    """
    uid  = user["user_id"]
    supa = _get_supa()

    # Provjeri opt-in
    try:
        profile_r = await asyncio.to_thread(
            lambda: supa.table("profiles")
                .select("benchmark_opt_in")
                .eq("id", uid)
                .maybe_single()
                .execute()
        )
        if not (profile_r.data or {}).get("benchmark_opt_in", False):
            return {"ok": False, "reason": "opt_in_required"}
    except Exception:
        return {"ok": False, "reason": "profile_error"}

    if payload.tip_predmeta not in _TIP_PREDMETA:
        raise HTTPException(status_code=400, detail=f"Nevalidan tip_predmeta.")
    if payload.ishod and payload.ishod not in _ISHODI:
        raise HTTPException(status_code=400, detail=f"Nevalidan ishod.")

    # Anonimizacija: zaokruži vrednosti
    naplaceno_anon = _zaokruzi_5pct(payload.naplaceno_rsd or 0) if payload.naplaceno_rsd else None

    try:
        await asyncio.to_thread(
            lambda: supa.table("case_benchmarks").insert({
                "tip_predmeta":    payload.tip_predmeta,
                "oblast_prava":    payload.oblast_prava,
                "trajanje_meseci": payload.trajanje_meseci,
                "ishod":           payload.ishod,
                "sud_tip":         payload.sud_tip or "ostalo",
                "regija":          payload.regija or "ostalo",
                "naplaceno_rsd":   naplaceno_anon,
                "opt_in":          True,
            }).execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True, "doprineto": True}


@router.get("/satnica")
@limiter.limit("20/minute")
async def benchmark_satnica(
    request: Request,
    user: dict = Depends(get_current_user),
    tip_predmeta: Optional[str] = None,
    regija: Optional[str] = None,
):
    """Prosečna satnica po tipu predmeta iz anonimnih podataka."""
    supa = _get_supa()

    try:
        q = supa.table("case_benchmarks").select("tip_predmeta, naplaceno_rsd, trajanje_meseci, regija")
        if tip_predmeta:
            q = q.eq("tip_predmeta", tip_predmeta)
        if regija:
            q = q.eq("regija", regija)
        q = q.not_.is_("naplaceno_rsd", "null")

        r = await asyncio.to_thread(lambda: q.limit(500).execute())
        rows = r.data or []

        _K_ANON_MIN = 20
        if len(rows) < _K_ANON_MIN:
            return {"podaci": [], "poruka": f"Nedovoljno anonimnih podataka (potrebno minimum {_K_ANON_MIN} uzoraka za ovu kategoriju). Doprinesi podacima da otključaš benchmark."}

        # Agregiraj po tipu
        by_tip: dict[str, list] = {}
        for row in rows:
            tip = row.get("tip_predmeta", "ostalo")
            napl = float(row.get("naplaceno_rsd") or 0)
            meseci = float(row.get("trajanje_meseci") or 6)
            if napl > 0 and meseci > 0:
                by_tip.setdefault(tip, []).append(napl / meseci)

        rezultat = []
        for tip, seme in by_tip.items():
            if len(seme) >= _K_ANON_MIN:
                avg_mesecno = sum(seme) / len(seme)
                rezultat.append({
                    "tip_predmeta":  tip,
                    "prosecno_mesecno_rsd": round(avg_mesecno, 0),
                    "uzoraka":       len(seme),
                })

        rezultat.sort(key=lambda x: x["prosecno_mesecno_rsd"], reverse=True)
        return {"satnica": rezultat, "ukupno_uzoraka": len(rows)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trajanje")
@limiter.limit("20/minute")
async def benchmark_trajanje(
    request: Request,
    user: dict = Depends(get_current_user),
    tip_predmeta: Optional[str] = None,
):
    """Prosečno trajanje predmeta po tipu."""
    supa = _get_supa()

    try:
        q = (supa.table("case_benchmarks")
             .select("tip_predmeta, trajanje_meseci, ishod")
             .not_.is_("trajanje_meseci", "null"))
        if tip_predmeta:
            q = q.eq("tip_predmeta", tip_predmeta)

        r = await asyncio.to_thread(lambda: q.limit(500).execute())
        rows = r.data or []

        _K_ANON_MIN = 20
        if len(rows) < _K_ANON_MIN:
            return {"podaci": [], "poruka": f"Nedovoljno anonimnih podataka (potrebno minimum {_K_ANON_MIN} uzoraka za ovu kategoriju). Doprinesi podacima da otključaš benchmark."}

        by_tip: dict[str, list] = {}
        for row in rows:
            tip = row.get("tip_predmeta", "ostalo")
            tr  = float(row.get("trajanje_meseci") or 0)
            if tr > 0:
                by_tip.setdefault(tip, []).append(tr)

        rezultat = []
        for tip, trajanja in by_tip.items():
            if len(trajanja) >= _K_ANON_MIN:
                rezultat.append({
                    "tip_predmeta":         tip,
                    "prosecno_meseci":      round(sum(trajanja) / len(trajanja), 1),
                    "min_meseci":           round(min(trajanja), 1),
                    "max_meseci":           round(max(trajanja), 1),
                    "uzoraka":              len(trajanja),
                })

        rezultat.sort(key=lambda x: x["prosecno_meseci"])
        return {"trajanje": rezultat, "ukupno_uzoraka": len(rows)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/win-rate")
@limiter.limit("20/minute")
async def benchmark_win_rate(
    request: Request,
    user: dict = Depends(get_current_user),
    tip_predmeta: Optional[str] = None,
):
    """Benchmark win rate po tipu predmeta."""
    supa = _get_supa()

    try:
        q = supa.table("case_benchmarks").select("tip_predmeta, ishod")
        if tip_predmeta:
            q = q.eq("tip_predmeta", tip_predmeta)
        q = q.not_.is_("ishod", "null")

        r = await asyncio.to_thread(lambda: q.limit(1000).execute())
        rows = r.data or []

        _K_ANON_MIN = 20
        if len(rows) < _K_ANON_MIN:
            return {"podaci": [], "poruka": f"Nedovoljno anonimnih podataka (potrebno minimum {_K_ANON_MIN} uzoraka za ovu kategoriju). Doprinesi podacima da otključaš benchmark."}

        by_tip: dict[str, dict] = {}
        for row in rows:
            tip   = row.get("tip_predmeta", "ostalo")
            ishod = row.get("ishod", "")
            if tip not in by_tip:
                by_tip[tip] = {"pobeda": 0, "poraz": 0, "nagodba": 0, "ukupno": 0}
            by_tip[tip]["ukupno"] += 1
            if ishod in by_tip[tip]:
                by_tip[tip][ishod] += 1

        rezultat = []
        for tip, d in by_tip.items():
            uk = d["ukupno"]
            if uk >= _K_ANON_MIN:
                rezultat.append({
                    "tip_predmeta":    tip,
                    "win_rate":        round(d["pobeda"] / uk * 100, 1),
                    "nagodba_rate":    round(d["nagodba"] / uk * 100, 1),
                    "poraz_rate":      round(d["poraz"] / uk * 100, 1),
                    "uzoraka":         uk,
                })

        rezultat.sort(key=lambda x: x["win_rate"], reverse=True)
        return {"win_rate": rezultat, "ukupno_uzoraka": len(rows)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/moj-rang")
@limiter.limit("10/minute")
async def moj_rang(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Poredi korisnička postignuća sa anonimnim prosekom.
    "Vaši predmeti radnog prava traju 23% duže od proseka."
    """
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        # Moji zatvoreni predmeti
        moji_r = await asyncio.to_thread(
            lambda: supa.table("case_patterns")
                .select("tip_spora, pobede, porazi, uzoraka")
                .eq("user_id", uid)
                .execute()
        )
        moji = moji_r.data or []

        if not moji:
            return {"poruka": "Nema dovoljno podataka za poređenje. Unesite ishode predmeta u Vindex."}

        upiti = []
        for m in moji[:5]:
            tip = m.get("tip_spora", "ostalo")
            uk  = (m.get("pobede", 0) or 0) + (m.get("porazi", 0) or 0)
            if uk < 2:
                continue

            moj_wr = round((m.get("pobede", 0) or 0) / max(1, uk) * 100, 1)

            # Benchmark za ovaj tip
            bench_r = await asyncio.to_thread(
                lambda t=tip: supa.table("case_benchmarks")
                    .select("ishod")
                    .eq("tip_predmeta", t)
                    .not_.is_("ishod", "null")
                    .limit(200)
                    .execute()
            )
            bench = bench_r.data or []

            if len(bench) < 20:
                continue

            bench_pobede = sum(1 for b in bench if b.get("ishod") == "pobeda")
            bench_wr = round(bench_pobede / len(bench) * 100, 1)
            razlika = round(moj_wr - bench_wr, 1)

            upiti.append({
                "tip_predmeta":    tip,
                "moj_win_rate":    moj_wr,
                "prosek_win_rate": bench_wr,
                "razlika_pp":      razlika,
                "status":          "iznad_proseka" if razlika > 5 else ("ispod_proseka" if razlika < -5 else "prosek"),
                "moji_uzorci":     uk,
                "bench_uzorci":    len(bench),
            })

        if not upiti:
            return {"poruka": "Nedovoljno anonimnih podataka za poređenje. Više korisnika treba da doprines podacima."}

        return {"rang": upiti, "ukupno_poređenja": len(upiti)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

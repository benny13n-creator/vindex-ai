# -*- coding: utf-8 -*-
"""
Vindex AI — routers/strategija.py

F5, F7.1, F9: AI Strategija moduli (PRO only).
  F5.1  — Red Team analiza
  F5.2  — Litigation Simulator
  F5.3  — AI Sudija
  F5.4  — Due Diligence
  F7.1  — AI Pravni Revizor
  F9.1  — Witness Analyzer
  F9.2  — AI Judge v2
"""
import asyncio
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _audit, _deduct_credit, _deduct_n_credits, _get_credits, _is_founder, require_pro
from shared.cost import begin_cost_tracking, log_cost_to_db
from shared.rate import limiter
from strategija import (
    red_team_analiza_sync,
    litigation_simulator_sync,
    ai_judge_mode_sync,
    due_diligence_analiza_sync,
    pravni_revizor_sync,
    witness_analyzer_sync,
    ai_judge_v2_sync,
    orkestrator_kompletna_analiza_sync,
)

router = APIRouter()

logger = __import__("logging").getLogger("vindex.api")


class StrategijaRequest(BaseModel):
    tekst: str = Field(..., max_length=20000)


@router.post("/strategija/red-team")  # F5.1
@limiter.limit("5/minute")
async def post_red_team(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F5.1 — Red Team analiza predmeta iz perspektive protivne strane (PRO)."""
    if len(req.tekst.strip()) < 50:
        raise HTTPException(status_code=422, detail="Opis predmeta mora imati najmanje 50 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "red_team", ""))
    try:
        rezultat = await asyncio.to_thread(
            red_team_analiza_sync, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "red_team", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F5] red_team greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju analize. Pokušajte ponovo.")


@router.post("/strategija/litigation")  # F5.2
@limiter.limit("5/minute")
async def post_litigation(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F5.2 — Litigation Simulator — procena ishoda sa % verovatnoće (PRO)."""
    if len(req.tekst.strip()) < 50:
        raise HTTPException(status_code=422, detail="Opis predmeta mora imati najmanje 50 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "litigation", ""))
    _praksa_context = ""
    try:
        from app.services.retrieve import _pretraga_praksa, _ugradi_query, _formatiraj_praksa_match
        _vec = await asyncio.wait_for(
            asyncio.to_thread(_ugradi_query, req.tekst[:500]), timeout=8.0
        )
        _matches = await asyncio.wait_for(
            asyncio.to_thread(_pretraga_praksa, _vec, 3), timeout=5.0
        )
        if _matches:
            _parts = [_formatiraj_praksa_match(m) for m in _matches]
            _parts = [p for p in _parts if p and len(p.strip()) > 30]
            if _parts:
                _praksa_context = "\n\n---\n\n".join(_parts[:3])
    except (asyncio.TimeoutError, Exception) as _pe:
        logger.warning("[F5] litigation praksa greška: %s", _pe)
    try:
        rezultat = await asyncio.to_thread(
            litigation_simulator_sync, req.tekst, os.getenv("OPENAI_API_KEY", ""), _praksa_context
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "litigation", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F5] litigation greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju simulacije. Pokušajte ponovo.")


@router.post("/strategija/sudija")  # F5.3
@limiter.limit("5/minute")
async def post_sudija(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F5.3 — AI Sudija — neutralna sudska perspektiva (PRO)."""
    if len(req.tekst.strip()) < 50:
        raise HTTPException(status_code=422, detail="Opis predmeta mora imati najmanje 50 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "ai_sudija", ""))
    try:
        rezultat = await asyncio.to_thread(
            ai_judge_mode_sync, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "sudija", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F5] sudija greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju analize. Pokušajte ponovo.")


@router.post("/strategija/due-diligence")  # F5.4
@limiter.limit("5/minute")
async def post_due_diligence(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F5.4 — Due Diligence analiza dokumenta (PRO)."""
    if len(req.tekst.strip()) < 100:
        raise HTTPException(status_code=422, detail="Tekst dokumenta mora imati najmanje 100 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "due_diligence", ""))
    try:
        rezultat = await asyncio.to_thread(
            due_diligence_analiza_sync, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "due_diligence", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F5] due_diligence greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju analize. Pokušajte ponovo.")


@router.post("/strategija/revizor")  # F7.1
@limiter.limit("5/minute")
async def post_revizor(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F7.1 — AI Pravni Revizor — pregled dokumenta sa predlozima izmena (PRO)."""
    if len(req.tekst.strip()) < 100:
        raise HTTPException(status_code=422, detail="Tekst dokumenta mora imati najmanje 100 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "pravni_revizor", ""))
    try:
        rezultat = await asyncio.to_thread(
            pravni_revizor_sync, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "revizor", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F7] pravni_revizor greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju revizije. Pokušajte ponovo.")


@router.post("/strategija/witness")  # F9.1
@limiter.limit("5/minute")
async def post_witness(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F9.1 — AI Witness Analyzer — analiza iskaza/svedočenja (PRO)."""
    if len(req.tekst.strip()) < 50:
        raise HTTPException(status_code=422, detail="Iskaz mora imati najmanje 50 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "witness_analyzer", ""))
    try:
        rezultat = await asyncio.to_thread(
            witness_analyzer_sync, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "witness", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F9] witness_analyzer greška")
        raise HTTPException(status_code=500, detail="Greška pri analizi iskaza. Pokušajte ponovo.")


@router.post("/strategija/sudija-v2")  # F9.2
@limiter.limit("3/minute")
async def post_sudija_v2(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F9.2 — AI Judge v2 — tužilac vs branilac → sudija (PRO, 3-round chain)."""
    if len(req.tekst.strip()) < 100:
        raise HTTPException(status_code=422, detail="Opis predmeta mora imati najmanje 100 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "sudija_v2", ""))
    try:
        rezultat = await asyncio.to_thread(
            ai_judge_v2_sync, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {
            "tuzilac":  rezultat["tuzilac"],
            "branilac": rezultat["branilac"],
            "presuda":  rezultat["presuda"],
            "modul":    "sudija_v2",
            "credits_remaining": max(preostalo, 0),
        }
    except Exception:
        logger.exception("[F9] sudija_v2 greška")
        raise HTTPException(status_code=500, detail="Greška pri simulaciji debate. Pokušajte ponovo.")


class OrkestratorRequest(BaseModel):
    opis_predmeta: str = Field(..., min_length=100, max_length=30000)
    dokumenti: Optional[List[str]] = Field(None, description="Opcioni tekstovi dokumenata za Pravni Revizor i Due Diligence")
    iskazi_svedoka: Optional[List[str]] = Field(None, description="Opcioni iskazi svedoka za Witness Analyzer")


@router.post("/strategija/kompletna-analiza")  # F10
@limiter.limit("1/hour")
async def post_kompletna_analiza(
    req: OrkestratorRequest,
    request: Request,
    background_tasks: "BackgroundTasks",
    user: dict = Depends(require_pro),
):
    """
    F10 — Strateški Orkestrator — 6 sekvencijalnih analiza (PRO, 6 kredita, 8 GPT-4o poziva).

    Vraća job_id odmah (HTTP 202). Klijent poluje GET /api/jobs/{job_id} dok status != done|error.
    Ovo sprečava HTTP timeout na Render (60s) — analiza traje 30-90s.
    """
    from fastapi import BackgroundTasks as _BT
    from routers.jobs import create_job, run_in_background

    uid   = user["user_id"]
    email = user.get("email", "")

    if not _is_founder(email):
        credits_pre = await asyncio.to_thread(_get_credits, uid)
        if credits_pre < 6:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "NO_CREDITS",
                    "message": f"Kompletna analiza zahteva 6 kredita. Trenutno imate {credits_pre}. Dopunite kredit paket.",
                    "credits_remaining": credits_pre,
                },
            )

    asyncio.create_task(_audit(uid, "kompletna_analiza", ""))

    async def _run_analiza():
        begin_cost_tracking()
        rezultat = await asyncio.to_thread(
            orkestrator_kompletna_analiza_sync,
            req.opis_predmeta,
            os.getenv("OPENAI_API_KEY", ""),
            req.dokumenti,
            req.iskazi_svedoka,
        )
        asyncio.create_task(log_cost_to_db(uid, "kompletna_analiza"))
        await asyncio.to_thread(_deduct_n_credits, uid, email, 6)
        return {**rezultat, "modul": "kompletna_analiza", "credits_deducted": 6}

    jid = create_job(uid, "kompletna_analiza")
    background_tasks.add_task(run_in_background, jid, _run_analiza)

    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=202,
        content={
            "job_id":   jid,
            "status":   "pending",
            "poruka":   "Analiza pokrenuta. Pratite napredak na GET /api/jobs/" + jid,
            "poll_url": f"/api/jobs/{jid}",
        },
    )


# ── P5 — Strategija V2 (Structured JSON Output) ───────────────────────────────

_V2_SYSTEM = """Ti si iskusni srpski advokat i pravni strateg.
Data je situacija predmeta. Vrati ISKLJUČIVO JSON bez ikakvog teksta van JSON-a.

Struktura odgovora:
{
  "procena_uspeha": {
    "procenat": int (0-100),
    "objasnjenje": str (1-2 rečenice),
    "faktori_plus": [str],
    "faktori_minus": [str]
  },
  "kljucni_rizici": [{"rizik": str, "tezina": "visoka|srednja|niska", "preporuka": str}],
  "nedostajuci_dokazi": [{"dokaz": str, "vaznost": "kritican|bitan|korisno", "nacin_pribavljanja": str}],
  "potencijalni_napadi": [{"napad": str, "tip": "pravni|cinjenicni|proceduralni", "odbrana": str}],
  "sledeci_koraci": [{"korak": str, "rok": str, "prioritet": "hitan|normalan|opciono"}],
  "relevantna_praksa": [{"opis": str, "zakljucak": str, "korist_za_nas": str}]
}

faktori_plus: konkretne okolnosti koje povećavaju šanse (maks 4)
faktori_minus: konkretne slabosti ili rizici koji umanjuju šanse (maks 4)
Maksimalno 5 stavki po ostalim kategorijama.
Budi konkretan i oslanjaj se na važeće srpsko pravo.
Ne halucinuj zakone — ako nisi siguran, navedi to otvoreno."""


class StrategijaV2Request(BaseModel):
    opis_predmeta: str = Field(..., min_length=50, max_length=8000)
    tip_predmeta: Optional[str] = Field(default=None, max_length=100)
    stranke: Optional[str] = Field(default=None, max_length=500)


@router.post("/strategija/v2/analiza")
@limiter.limit("5/minute")
async def strategija_v2_analiza(
    req: StrategijaV2Request,
    request: Request,
    user: dict = Depends(require_pro),
):
    """
    Strategija V2 — strukturiran JSON output sa procenom uspeha, rizicima,
    nedostajućim dokazima, potencijalnim napadima, sledećim koracima i praksom.
    """
    import os as _os, json as _json
    from openai import AsyncOpenAI

    uid   = user["user_id"]
    email = user.get("email", "")
    asyncio.create_task(_audit(uid, "strategija_v2", ""))

    user_msg = f"Opis predmeta:\n{req.opis_predmeta}"
    if req.tip_predmeta:
        user_msg = f"Tip predmeta: {req.tip_predmeta}\n{user_msg}"
    if req.stranke:
        user_msg += f"\n\nStranke: {req.stranke}"

    oai = AsyncOpenAI(api_key=_os.getenv("OPENAI_API_KEY", ""))
    try:
        begin_cost_tracking()
        resp = await oai.chat.completions.create(
            model="gpt-4o",
            temperature=0.1,
            max_tokens=3000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _V2_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
        )
        analiza = _json.loads(resp.choices[0].message.content or "{}")
        asyncio.create_task(log_cost_to_db(uid, "strategija_v2"))
        preostalo = await asyncio.to_thread(_deduct_credit, uid, email)
        return {
            **analiza,
            "modul": "strategija_v2",
            "credits_remaining": preostalo,
        }
    except _json.JSONDecodeError as je:
        logger.error("[V2] JSON parse greška: %s", je)
        raise HTTPException(status_code=500, detail="Greška pri parsiranju AI odgovora.")
    except Exception:
        logger.exception("[V2] strategija_v2 greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju strategije.")

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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _audit
from shared.permissions import PermissionService
from shared.usage import UsageService
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
    tip_postupka: Optional[str] = Field(None, description="gradjansko|krivicno|upravno|privredno|radno")


async def _fetch_praksa_ctx(tekst: str, k: int = 3) -> str:
    """Dohvata sudsku praksu iz Pinecone — shared helper za strategija module."""
    try:
        from app.services.retrieve import _pretraga_praksa, _ugradi_query, _formatiraj_praksa_match
        vec = await asyncio.wait_for(asyncio.to_thread(_ugradi_query, tekst[:500]), timeout=8.0)
        matches = await asyncio.wait_for(asyncio.to_thread(_pretraga_praksa, vec, k), timeout=5.0)
        if matches:
            parts = [_formatiraj_praksa_match(m) for m in matches]
            parts = [p for p in parts if p and len(p.strip()) > 30]
            return "\n\n---\n\n".join(parts[:k])
    except Exception as e:
        logger.warning("[F5] praksa fetch greška: %s", e)
    return ""


@router.post("/strategija/red-team")  # F5.1
@limiter.limit("5/minute")
async def post_red_team(req: StrategijaRequest, request: Request, user: dict = Depends(PermissionService.require("strategija"))):
    """F5.1 — Red Team analiza predmeta iz perspektive protivne strane (PRO)."""
    if len(req.tekst.strip()) < 50:
        raise HTTPException(status_code=422, detail="Opis predmeta mora imati najmanje 50 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "red_team", ""))
    _praksa_context = await _fetch_praksa_ctx(req.tekst)
    try:
        rezultat = await asyncio.to_thread(
            red_team_analiza_sync, req.tekst, os.getenv("OPENAI_API_KEY", ""), _praksa_context,
            req.tip_postupka or "gradjansko"
        )
        # Ovi moduli su pojedinačni pozivi (bazna cena) — kompletna_analiza je
        # jedina varijanta koja koristi feature_registry.credit_multiplier (6x,
        # pokreće svih 6 modula odjednom), pa multiplier=1 mora biti eksplicitan
        # override ovde da ne bi tiho nasledio 6x od deljenog "strategija" feature_key-a.
        preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "strategija", multiplier=1)
        return {"rezultat": rezultat, "modul": "red_team", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F5] red_team greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju analize. Pokušajte ponovo.")


@router.post("/strategija/litigation")  # F5.2
@limiter.limit("5/minute")
async def post_litigation(req: StrategijaRequest, request: Request, user: dict = Depends(PermissionService.require("strategija"))):
    """F5.2 — Litigation Simulator — procena ishoda sa % verovatnoće (PRO)."""
    if len(req.tekst.strip()) < 50:
        raise HTTPException(status_code=422, detail="Opis predmeta mora imati najmanje 50 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "litigation", ""))
    _praksa_context = await _fetch_praksa_ctx(req.tekst)
    try:
        rezultat = await asyncio.to_thread(
            litigation_simulator_sync, req.tekst, os.getenv("OPENAI_API_KEY", ""), _praksa_context
        )
        # Ovi moduli su pojedinačni pozivi (bazna cena) — kompletna_analiza je
        # jedina varijanta koja koristi feature_registry.credit_multiplier (6x,
        # pokreće svih 6 modula odjednom), pa multiplier=1 mora biti eksplicitan
        # override ovde da ne bi tiho nasledio 6x od deljenog "strategija" feature_key-a.
        preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "strategija", multiplier=1)
        return {"rezultat": rezultat, "modul": "litigation", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F5] litigation greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju simulacije. Pokušajte ponovo.")


@router.post("/strategija/sudija")  # F5.3
@limiter.limit("5/minute")
async def post_sudija(req: StrategijaRequest, request: Request, user: dict = Depends(PermissionService.require("strategija"))):
    """F5.3 — AI Sudija — neutralna sudska perspektiva (PRO)."""
    if len(req.tekst.strip()) < 50:
        raise HTTPException(status_code=422, detail="Opis predmeta mora imati najmanje 50 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "ai_sudija", ""))
    _praksa_context = await _fetch_praksa_ctx(req.tekst)
    try:
        rezultat = await asyncio.to_thread(
            ai_judge_mode_sync, req.tekst, os.getenv("OPENAI_API_KEY", ""), _praksa_context
        )
        # Ovi moduli su pojedinačni pozivi (bazna cena) — kompletna_analiza je
        # jedina varijanta koja koristi feature_registry.credit_multiplier (6x,
        # pokreće svih 6 modula odjednom), pa multiplier=1 mora biti eksplicitan
        # override ovde da ne bi tiho nasledio 6x od deljenog "strategija" feature_key-a.
        preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "strategija", multiplier=1)
        return {"rezultat": rezultat, "modul": "sudija", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F5] sudija greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju analize. Pokušajte ponovo.")


async def _fetch_zakon_ctx(tekst: str, k: int = 4) -> str:
    """Dohvata relevantne zakonske odredbe iz Pinecone — za due diligence."""
    try:
        from app.services.retrieve import _pretraga_vec, _ugradi_query, _formatiraj_match
        vec = await asyncio.wait_for(asyncio.to_thread(_ugradi_query, tekst[:600]), timeout=8.0)
        matches = await asyncio.wait_for(asyncio.to_thread(_pretraga_vec, vec, k), timeout=5.0)
        if matches:
            parts = [_formatiraj_match(m) for m in matches]
            parts = [p for p in parts if p and len(p.strip()) > 30]
            return "\n\n---\n\n".join(parts[:k])
    except Exception as e:
        logger.warning("[DD] zakon fetch greška: %s", e)
    return ""


@router.post("/strategija/due-diligence")  # F5.4
@limiter.limit("5/minute")
async def post_due_diligence(req: StrategijaRequest, request: Request, user: dict = Depends(PermissionService.require("strategija"))):
    """F5.4 — Due Diligence analiza dokumenta sa RAG zakonskim kontekstom (PRO)."""
    if len(req.tekst.strip()) < 100:
        raise HTTPException(status_code=422, detail="Tekst dokumenta mora imati najmanje 100 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "due_diligence", ""))
    _zakon_context = await _fetch_zakon_ctx(req.tekst)
    try:
        rezultat = await asyncio.to_thread(
            due_diligence_analiza_sync, req.tekst, os.getenv("OPENAI_API_KEY", ""), _zakon_context
        )
        # Ovi moduli su pojedinačni pozivi (bazna cena) — kompletna_analiza je
        # jedina varijanta koja koristi feature_registry.credit_multiplier (6x,
        # pokreće svih 6 modula odjednom), pa multiplier=1 mora biti eksplicitan
        # override ovde da ne bi tiho nasledio 6x od deljenog "strategija" feature_key-a.
        preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "strategija", multiplier=1)
        return {"rezultat": rezultat, "modul": "due_diligence", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F5] due_diligence greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju analize. Pokušajte ponovo.")


@router.post("/strategija/revizor")  # F7.1
@limiter.limit("5/minute")
async def post_revizor(req: StrategijaRequest, request: Request, user: dict = Depends(PermissionService.require("strategija"))):
    """F7.1 — AI Pravni Revizor — pregled dokumenta sa predlozima izmena (PRO)."""
    if len(req.tekst.strip()) < 100:
        raise HTTPException(status_code=422, detail="Tekst dokumenta mora imati najmanje 100 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "pravni_revizor", ""))
    try:
        rezultat = await asyncio.to_thread(
            pravni_revizor_sync, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        # Ovi moduli su pojedinačni pozivi (bazna cena) — kompletna_analiza je
        # jedina varijanta koja koristi feature_registry.credit_multiplier (6x,
        # pokreće svih 6 modula odjednom), pa multiplier=1 mora biti eksplicitan
        # override ovde da ne bi tiho nasledio 6x od deljenog "strategija" feature_key-a.
        preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "strategija", multiplier=1)
        return {"rezultat": rezultat, "modul": "revizor", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F7] pravni_revizor greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju revizije. Pokušajte ponovo.")


@router.post("/strategija/witness")  # F9.1
@limiter.limit("5/minute")
async def post_witness(req: StrategijaRequest, request: Request, user: dict = Depends(PermissionService.require("strategija"))):
    """F9.1 — AI Witness Analyzer — analiza iskaza/svedočenja (PRO)."""
    if len(req.tekst.strip()) < 50:
        raise HTTPException(status_code=422, detail="Iskaz mora imati najmanje 50 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "witness_analyzer", ""))
    try:
        rezultat = await asyncio.to_thread(
            witness_analyzer_sync, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        # Ovi moduli su pojedinačni pozivi (bazna cena) — kompletna_analiza je
        # jedina varijanta koja koristi feature_registry.credit_multiplier (6x,
        # pokreće svih 6 modula odjednom), pa multiplier=1 mora biti eksplicitan
        # override ovde da ne bi tiho nasledio 6x od deljenog "strategija" feature_key-a.
        preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "strategija", multiplier=1)
        return {"rezultat": rezultat, "modul": "witness", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F9] witness_analyzer greška")
        raise HTTPException(status_code=500, detail="Greška pri analizi iskaza. Pokušajte ponovo.")


@router.post("/strategija/sudija-v2")  # F9.2
@limiter.limit("3/minute")
async def post_sudija_v2(req: StrategijaRequest, request: Request, user: dict = Depends(PermissionService.require("strategija"))):
    """F9.2 — AI Judge v2 — tužilac vs branilac → sudija (PRO, 3-round chain)."""
    if len(req.tekst.strip()) < 100:
        raise HTTPException(status_code=422, detail="Opis predmeta mora imati najmanje 100 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "sudija_v2", ""))
    try:
        rezultat = await asyncio.to_thread(
            ai_judge_v2_sync, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        # Ovi moduli su pojedinačni pozivi (bazna cena) — kompletna_analiza je
        # jedina varijanta koja koristi feature_registry.credit_multiplier (6x,
        # pokreće svih 6 modula odjednom), pa multiplier=1 mora biti eksplicitan
        # override ovde da ne bi tiho nasledio 6x od deljenog "strategija" feature_key-a.
        preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "strategija", multiplier=1)
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
@limiter.limit("10/hour")
async def post_kompletna_analiza(
    req: OrkestratorRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: dict = Depends(PermissionService.require("strategija")),
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
        # multiplier čita se iz feature_registry.credit_multiplier (migracija 069,
        # Admin Console editabilno) — ne hardkoduje se ovde.
        await UsageService.consume(uid, email, "strategija")
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
    user: dict = Depends(PermissionService.require("strategija")),
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
        # Pojedinačan poziv (bazna cena) — vidi napomenu iznad o multiplier=1 override-u.
        preostalo = await UsageService.consume(uid, email, "strategija", multiplier=1)
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

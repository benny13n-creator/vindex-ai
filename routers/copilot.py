# -*- coding: utf-8 -*-
"""
Vindex AI — Copilot (Faza 4)

Orkestrator koji advokatu daje jedinstven chat interfejs nad svim postojećim
modulima. Ne dodaje nove AI modele — poziva postojeće servise interno.

POST /copilot/chat
  - Prihvata poruku + opcioni predmet_id
  - Detektuje nameru (intent detection)
  - Rutira na odgovarajući servis
  - Vraća strukturiran odgovor

Podržane namere:
  PRAVNO_PITANJE    → /api/pitanje (RAG zakon)
  SUDSKA_PRAKSA     → /api/praksa/search
  NACRT             → /api/nacrt (generisanje dokumenta)
  ANALIZA_PREDMETA  → /api/analiza
  ROKOVI            → /zastarelost/kalkulisi
  PRETRAGA          → /api/search
  STRATEGIJA        → /strategija/litigation (PRO)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user, require_credits, _deduct_credit
from shared.rate import limiter

logger = logging.getLogger("vindex.copilot")
router = APIRouter(tags=["copilot"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

_INTENT_SYSTEM = """Ti si detektor namere za srpski pravni AI asistent.
Na osnovu korisničke poruke, vrati SAMO jednu od sledećih reči (bez ikakvog drugog teksta):
PRAVNO_PITANJE — korisnik pita šta zakon kaže, koji član, kakvo je pravo
SUDSKA_PRAKSA — korisnik traži sudske odluke, presude, praksu VKS
NACRT — korisnik traži da se napiše, generiše ili napravi dokument (tužba, ugovor, žalba...)
ANALIZA_PREDMETA — korisnik traži analizu, procenu predmeta, strategiju
ROKOVI — korisnik pita o rokovima, zastarelosti, kalendarskim terminima
PRETRAGA — korisnik traži određenu osobu, predmet ili dokument u sistemu
OSTALO — ništa od navedenog

Vrati SAMO jednu reč, ništa više."""

_INTENT_CHOICES = {
    "PRAVNO_PITANJE", "SUDSKA_PRAKSA", "NACRT",
    "ANALIZA_PREDMETA", "ROKOVI", "PRETRAGA", "OSTALO",
}


class CopilotReq(BaseModel):
    poruka: str = Field(..., min_length=3, max_length=4000)
    predmet_id: Optional[str] = None
    session_id: Optional[str] = None


async def _detect_intent(poruka: str) -> str:
    from openai import AsyncOpenAI
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    try:
        r = await oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _INTENT_SYSTEM},
                {"role": "user",   "content": poruka[:500]},
            ],
            temperature=0,
            max_tokens=20,
        )
        intent = (r.choices[0].message.content or "").strip().upper()
        return intent if intent in _INTENT_CHOICES else "OSTALO"
    except Exception:
        return "PRAVNO_PITANJE"


async def _load_predmet_context(predmet_id: str, user_id: str) -> str:
    """Učitava naziv+opis predmeta za kontekst copilota."""
    try:
        supa = _get_supa()
        r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("naziv, opis, tip, status")
                .eq("id", predmet_id)
                .eq("user_id", user_id)
                .single()
                .execute()
        )
        if r.data:
            d = r.data
            return f"[Predmet: {d.get('naziv','')} | {d.get('tip','')} | {d.get('status','')}]\n{d.get('opis','')}"
    except Exception:
        pass
    return ""


async def _handle_pravno_pitanje(poruka: str, predmet_ctx: str, user: dict) -> dict:
    """Poziva RAG zakon pipeline direktno."""
    from app.services.retrieve import retrieve_documents
    from main import ask_agent as _ask
    try:
        q = f"{predmet_ctx}\n\n{poruka}".strip() if predmet_ctx else poruka
        chunks = await asyncio.to_thread(retrieve_documents, q, 5)
        odgovor = await asyncio.to_thread(_ask, q, chunks)
        return {"tip": "PRAVNO_PITANJE", "odgovor": odgovor, "chunks": len(chunks)}
    except Exception as e:
        logger.error("[COPILOT] pravno_pitanje greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri pravnom istraživanju.")


async def _handle_sudska_praksa(poruka: str) -> dict:
    """Poziva Pinecone praksa namespace."""
    from app.services.retrieve import retrieve_sudska_praksa as _rp
    try:
        results = await asyncio.to_thread(_rp, poruka, top_k=5)
        return {"tip": "SUDSKA_PRAKSA", "presude": results}
    except Exception as e:
        logger.warning("[COPILOT] sudska_praksa greška: %s — fallback", e)
        return {
            "tip": "SUDSKA_PRAKSA",
            "odgovor": "Upotrebite modul Sudska praksa za detaljnu pretragu.",
            "presude": [],
        }


async def _handle_nacrt(poruka: str, predmet_ctx: str, user: dict) -> dict:
    """Vraća uputstvo za nacrt — korisnik mora otvoriti modul za draft."""
    return {
        "tip": "NACRT",
        "odgovor": (
            "Prepoznao sam zahtev za generisanje dokumenta. "
            "Otvorite tab **Nacrte** i odaberite tip dokumenta — sistem će "
            "iskoristiti kontekst ovog predmeta automatski."
        ),
        "akcija": "otvori_nacrt",
    }


async def _handle_pretraga(poruka: str, user_id: str) -> dict:
    """Cross-entity search."""
    supa = _get_supa()
    q = poruka[:100]
    results = []
    for table, fields, tip, url_prefix in [
        ("klijenti",          "id, ime, prezime, firma", "klijent",  "/klijenti/"),
        ("predmeti",          "id, naziv",                "predmet",  "/predmeti/"),
        ("predmet_beleske",   "id, sadrzaj, predmet_id",  "beleska",  "/predmeti/"),
    ]:
        try:
            filter_col = "sadrzaj" if table == "predmet_beleske" else ("naziv" if table == "predmeti" else "ime")
            r = await asyncio.to_thread(
                lambda t=table, f=fields, c=filter_col: supa.table(t).select(f).eq("user_id", user_id).ilike(c, f"%{q}%").limit(3).execute()
            )
            for row in (r.data or []):
                naziv = row.get("naziv") or row.get("sadrzaj","")[:80] or f"{row.get('ime','')} {row.get('prezime','')}".strip()
                url = url_prefix + row.get("predmet_id", row.get("id", ""))
                results.append({"tip": tip, "naziv": naziv, "url": url})
        except Exception:
            pass
    return {"tip": "PRETRAGA", "rezultati": results}


async def _handle_ostalo(poruka: str, predmet_ctx: str) -> dict:
    """Generalni odgovor bez RAG — kratki savet."""
    from openai import AsyncOpenAI
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    ctx_line = f"\nKontekst predmeta: {predmet_ctx}" if predmet_ctx else ""
    try:
        r = await oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "Ti si pravni asistent za srpsko pravo. Daj kratak, konkretan odgovor. "
                    "Ako ne znaš tačan zakon, kaži to otvoreno." + ctx_line
                )},
                {"role": "user", "content": poruka},
            ],
            temperature=0.2,
            max_tokens=600,
        )
        return {"tip": "OSTALO", "odgovor": r.choices[0].message.content or ""}
    except Exception as e:
        logger.error("[COPILOT] ostalo greška: %s", e)
        return {"tip": "OSTALO", "odgovor": "Molim precizite pitanje."}


@router.post("/copilot/chat")
@limiter.limit("30/minute")
async def copilot_chat(
    req: CopilotReq,
    request: Request,
    user: dict = Depends(require_credits),
):
    """
    Vindex Copilot — orkestrator svih modula.
    Detektuje nameru i automatski rutira na odgovarajući servis.
    """
    uid      = user["user_id"]
    email    = user.get("email", "")
    predmet_ctx = ""

    if req.predmet_id:
        predmet_ctx = await _load_predmet_context(req.predmet_id, uid)

    intent = await _detect_intent(req.poruka)
    logger.info("[COPILOT] uid=%.8s intent=%s predmet=%s", uid, intent, req.predmet_id or "-")

    handlers = {
        "PRAVNO_PITANJE": lambda: _handle_pravno_pitanje(req.poruka, predmet_ctx, user),
        "SUDSKA_PRAKSA":  lambda: _handle_sudska_praksa(req.poruka),
        "NACRT":          lambda: _handle_nacrt(req.poruka, predmet_ctx, user),
        "ANALIZA_PREDMETA": lambda: _handle_pravno_pitanje(req.poruka, predmet_ctx, user),
        "ROKOVI":         lambda: _handle_pravno_pitanje(req.poruka, predmet_ctx, user),
        "PRETRAGA":       lambda: _handle_pretraga(req.poruka, uid),
        "OSTALO":         lambda: _handle_ostalo(req.poruka, predmet_ctx),
    }

    handler = handlers.get(intent, handlers["OSTALO"])
    result  = await handler()

    # Oduzmi kredit
    await asyncio.to_thread(_deduct_credit, uid, email)

    return {
        "intent":     intent,
        "predmet_id": req.predmet_id,
        **result,
    }

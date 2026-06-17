# -*- coding: utf-8 -*-
"""
Vindex AI — routers/cross_doc.py

POST /api/analiza/cross-doc
  Višedokumentna pravna analiza: konflikti, sličnosti, preporuke.
  GPT-4o poredi 2-5 dokumenata/odlomaka u kontekstu datog pravnog pitanja.
"""
import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from shared.deps import get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.api")
router = APIRouter()


# ─── Modeli ───────────────────────────────────────────────────────────────────

class DokumentUnos(BaseModel):
    naziv:  str = Field(..., min_length=1, max_length=200, description="Naziv dokumenta")
    tekst:  str = Field(..., min_length=10, max_length=5000, description="Sadržaj dokumenta")


class CrossDocReq(BaseModel):
    dokumenti:      list[DokumentUnos] = Field(..., min_length=2, max_length=5)
    pravno_pitanje: str                = Field(..., min_length=10, max_length=500)
    kontekst:       Optional[str]      = Field(default=None, max_length=500,
                                                description="Dodatni kontekst (opciono)")

    @field_validator("dokumenti")
    @classmethod
    def _check_unique_nazivi(cls, v: list) -> list:
        nazivi = [d.naziv for d in v]
        if len(set(nazivi)) != len(nazivi):
            raise ValueError("Svi dokumenti moraju imati različite nazive.")
        return v


# ─── GPT prompt ───────────────────────────────────────────────────────────────

_SYSTEM = (
    "Ti si pravni analitičar specijalizovan za srpsko pravo. "
    "Analiziraš više pravnih dokumenata i pronalaziš konflikte, sličnosti i daješ preporuke. "
    "Odgovori ISKLJUČIVO u JSON formatu:\n"
    "{\n"
    '  "rezime": "1-2 rečenice o ukupnom nalazu",\n'
    '  "konflikti": [\n'
    '    {"dokument_a": str, "dokument_b": str, "opis": str, "ozbiljnost": "visoka"|"srednja"|"niska"}\n'
    '  ],\n'
    '  "slicnosti": [\n'
    '    {"dokumenti": [str, ...], "opis": str}\n'
    '  ],\n'
    '  "preporuke": [\n'
    '    {"prioritet": int (1=najvažnija), "akcija": str, "obrazloženje": str}\n'
    '  ],\n'
    '  "pravni_zakljucak": "Zaključni pravni stav na osnovu analize svih dokumenata"\n'
    "}\n"
    "Budi koncizan, precizan, srpski jezik (ekavica). Ne halucinuj."
)


def _format_dokumenti(dokumenti: list[DokumentUnos]) -> str:
    delovi = []
    for i, d in enumerate(dokumenti, 1):
        delovi.append(f"[DOKUMENT {i}: {d.naziv}]\n{d.tekst.strip()}")
    return "\n\n---\n\n".join(delovi)


# ─── Sync helper (za asyncio.to_thread) ──────────────────────────────────────

def _cross_doc_sync(
    dokumenti: list[DokumentUnos],
    pravno_pitanje: str,
    kontekst: Optional[str],
) -> dict:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=os.getenv("OPENAI_API_KEY"))

    doc_blok = _format_dokumenti(dokumenti)
    user_msg = (
        f"PRAVNO PITANJE / TEMA ANALIZE:\n{pravno_pitanje}\n"
        + (f"\nDODATNI KONTEKST:\n{kontekst}\n" if kontekst else "")
        + f"\n\nDOKUMENTI:\n\n{doc_blok}"
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.1,
            max_tokens=2000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
        )
        raw = resp.choices[0].message.content or "{}"
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("[CROSS_DOC] JSON parse greška: %s", exc)
        result = {}
    except Exception as exc:
        logger.error("[CROSS_DOC] GPT greška: %s", exc)
        raise

    return {
        "pravno_pitanje":  pravno_pitanje,
        "broj_dokumenata": len(dokumenti),
        "nazivi":          [d.naziv for d in dokumenti],
        "rezime":          result.get("rezime", ""),
        "konflikti":       result.get("konflikti", []),
        "slicnosti":       result.get("slicnosti", []),
        "preporuke":       sorted(result.get("preporuke", []), key=lambda x: x.get("prioritet", 99)),
        "pravni_zakljucak": result.get("pravni_zakljucak", ""),
    }


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/api/analiza/cross-doc")
@limiter.limit("10/minute")
async def cross_doc_analiza(
    req: CrossDocReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Višedokumentna pravna analiza.
    Poredi 2-5 dokumenata i identifikuje konflikte, sličnosti i daje prioritetne preporuke.
    """
    try:
        result = await asyncio.to_thread(
            _cross_doc_sync,
            req.dokumenti,
            req.pravno_pitanje,
            req.kontekst,
        )
        return result
    except Exception:
        logger.exception("Greška u /api/analiza/cross-doc")
        return JSONResponse(
            status_code=500,
            content={"error": "Greška pri analizi dokumenata. Pokušajte ponovo."},
        )

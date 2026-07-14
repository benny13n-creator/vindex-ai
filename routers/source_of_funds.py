# -*- coding: utf-8 -*-
"""
Vindex AI — routers/source_of_funds.py

F16: Source-of-Funds / Source-of-Wealth Compliance Dossier (Faza 4) — spaja
u jedan PDF dokument:
  1. Documentation Health Score (F11.7, web3_compliance.documentation_health_score_sync)
  2. CARF/DAC8 Readiness (F11.9, web3_compliance.carf_dac8_readiness_sync)
  3. Wallet Provenance (F15, opciono — routers.wallet_provenance.sakupi_wallet_provenance)

2 kredita (dva GPT poziva unutra) — isti princip kao F12 Smart Contract
Analyzer koji takođe deduktuje više od 1 kredita za kompozitnu analizu.
"""
import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response as _Resp
from pydantic import BaseModel, Field, field_validator

from dossier_pdf import generisi_dossier_pdf
from routers.wallet_provenance import _ETH_ADDRESS_RE, sakupi_wallet_provenance
from shared.deps import _audit
from shared.permissions import PermissionService
from shared.usage import UsageService
from shared.rate import limiter
from web3_compliance import (
    carf_dac8_readiness_sync as _carf_dac8_readiness,
    documentation_health_score_sync as _documentation_health_score,
)

router = APIRouter()
logger = logging.getLogger("vindex.source_of_funds")

_DEFAULT_CARF_PITANJE = (
    "Koje su opšte kategorije obaveza izveštavanja koje CARF/DAC8 okvir predviđa "
    "za pružaoce usluga digitalne imovine, i šta to znači za korisnika koji sam vodi evidenciju?"
)


class DossierRequest(BaseModel):
    opis_dokumentacije: str = Field(..., max_length=8000)
    carf_pitanje: str = Field(default="", max_length=2000)
    wallet_adresa: str = Field(default="", max_length=42)

    @field_validator("opis_dokumentacije")
    @classmethod
    def val_opis(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 30:
            raise ValueError("Opis dokumentacije mora imati najmanje 30 karaktera.")
        return v

    @field_validator("wallet_adresa")
    @classmethod
    def val_wallet(cls, v: str) -> str:
        v = v.strip()
        if v and not _ETH_ADDRESS_RE.match(v):
            raise ValueError("Wallet adresa mora biti validna Ethereum adresa (0x + 40 hex karaktera) ili prazna.")
        return v


@router.post("/web3/source-of-funds-dossier")  # F16.1
@limiter.limit("5/minute")
async def post_source_of_funds_dossier(
    req: DossierRequest, request: Request,
    user: dict = Depends(PermissionService.require("da_source_of_funds")),
):
    """F16.1 — Source-of-Funds Compliance Dossier: PDF izveštaj (PRO, 2 kredita)."""
    email = user.get("email", "")
    preostalo = await UsageService.consume(user["user_id"], email, "da_source_of_funds")

    asyncio.create_task(_audit(user["user_id"], "source_of_funds_dossier", ""))

    api_key = os.getenv("OPENAI_API_KEY", "")
    carf_pitanje = req.carf_pitanje.strip() or _DEFAULT_CARF_PITANJE

    try:
        health_task = asyncio.to_thread(_documentation_health_score, req.opis_dokumentacije, api_key)
        carf_task = asyncio.to_thread(_carf_dac8_readiness, carf_pitanje, api_key)
        health_rezultat, carf_odgovor = await asyncio.gather(health_task, carf_task)
    except Exception:
        logger.exception("[F16] Greška pri generisanju AI sekcija dossier-a")
        raise HTTPException(status_code=500, detail="Greška pri analizi. Pokušajte ponovo.")

    wallet_podaci = None
    if req.wallet_adresa:
        try:
            wallet_podaci = await sakupi_wallet_provenance(req.wallet_adresa)
        except HTTPException as exc:
            # Wallet provera nije dostupna (npr. ETHERSCAN_API_KEY nije konfigurisan) —
            # dossier se svejedno generiše bez te sekcije, ne blokiramo ceo izveštaj.
            logger.warning("[F16] Wallet provenance sekcija preskočena: %s", exc.detail)

    try:
        pdf_bytes = await asyncio.to_thread(
            generisi_dossier_pdf,
            {
                "korisnik_email": email,
                "health_data": health_rezultat.get("health_data"),
                "carf_odgovor": carf_odgovor,
                "carf_pitanje": carf_pitanje,
                "wallet": wallet_podaci,
            },
        )
    except Exception as exc:
        logger.exception("[F16] Greška pri generisanju PDF-a")
        raise HTTPException(status_code=500, detail=f"Greška pri generisanju PDF-a: {exc}")

    filename = f"vindex_source_of_funds_dossier_{user['user_id'][:8]}.pdf"
    return _Resp(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Credits-Remaining": str(max(preostalo, 0)),
        },
    )

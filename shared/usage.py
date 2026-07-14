# -*- coding: utf-8 -*-
"""
Vindex AI — shared/usage.py

UsageService — odvojen sloj od PermissionService. PermissionService odgovara
"ima li nalog PRAVO da pristupi funkciji" (tarifa/addon); UsageService
odgovara "da li ima BUDžET da je iskoristi ovog meseca" (krediti/paketi).

Upotreba u routeru — DVA ODVOJENA poziva, tim redosledom:

    from shared.permissions import PermissionService
    from shared.usage import UsageService
    from shared.features import FEATURE_CASE_DNA

    @router.post("/api/case-dna/refresh")
    async def refresh(
        user: dict = Depends(PermissionService.require(FEATURE_CASE_DNA)),
    ):
        ... (generiši AI odgovor) ...
        await UsageService.consume(user["user_id"], user["email"], FEATURE_CASE_DNA, credits=3)

Ne prikazuje tehničke detalje (OpenAI tokene, broj poziva modelu) nikad
korisniku — samo "Mesečni AI fond" i preostali broj kredita. To ostaje
frontend-ova odgovornost (postojeći userCredits/updateCreditDisplay obrazac),
ovaj servis samo upravlja brojem na backend-u.

Ponovo koristi POSTOJEĆE, već testirane atomične RPC primitive iz
shared/deps.py (_deduct_credit, _deduct_n_credits, _get_credits,
_refund_one_credit) — ne duplira logiku, samo je centralizuje iza jednog
konzistentnog API-ja i ispravlja neusaglašenost pronađenu u auditu (founder
je u nekim fajlovima preskakao pre-proveru ali ne i samo oduzimanje kredita).
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import HTTPException, status

from shared.deps import (
    _deduct_credit,
    _deduct_n_credits,
    _get_credits,
    _is_founder,
    _refund_one_credit,
)

logger = logging.getLogger("vindex.usage")

FOUNDER_BALANCE = 9999


class UsageService:
    @staticmethod
    async def consume(user_id: str, email: str, feature: str, credits: int = 1) -> int:
        """
        Atomično proverava i oduzima N kredita. Founder NIKAD ne plaća — ni
        pre-proverom ni stvarnim oduzimanjem (ispravlja neusaglašenost iz
        digital_twin.py/evidence_graph.py/court_predictor.py pronađenu u auditu).

        Vraća preostali broj kredita. Baca HTTPException(402) ako nema dovoljno.
        """
        if _is_founder(email):
            return FOUNDER_BALANCE

        trenutno = await asyncio.to_thread(_get_credits, user_id)
        if trenutno < credits:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "NO_CREDITS",
                    "feature": feature,
                    "message": (
                        "Nemate dovoljno kredita u mesečnom AI fondu za ovu funkciju. "
                        "Dokupite dodatni paket kredita ili sačekajte mesečni reset."
                    ),
                    "credits_remaining": trenutno,
                },
            )

        if credits == 1:
            preostalo = await asyncio.to_thread(_deduct_credit, user_id, email)
        else:
            preostalo = await asyncio.to_thread(_deduct_n_credits, user_id, email, credits)

        if preostalo < 0:
            # Race condition — neko drugi je potrošio kredite između provere i oduzimanja.
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "NO_CREDITS",
                    "feature": feature,
                    "message": "Nemate dovoljno kredita u mesečnom AI fondu za ovu funkciju.",
                    "credits_remaining": 0,
                },
            )
        return preostalo

    @staticmethod
    async def balance(user_id: str, email: str) -> int:
        if _is_founder(email):
            return FOUNDER_BALANCE
        return await asyncio.to_thread(_get_credits, user_id)

    @staticmethod
    async def refund(user_id: str, email: str, credits: int = 1) -> None:
        """Best-effort refund (npr. cache-hit posle pre-deduction, ili greška u generisanju)."""
        if _is_founder(email):
            return
        for _ in range(credits):
            await asyncio.to_thread(_refund_one_credit, user_id)

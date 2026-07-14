# -*- coding: utf-8 -*-
"""
Vindex AI — shared/usage.py

UsageService — odvojen sloj od PermissionService. PermissionService odgovara
"ima li nalog PRAVO da pristupi funkciji" (tarifa/addon); UsageService
odgovara "da li ima BUDžET da je iskoristi ovog meseca/danas" (krediti,
dnevni/mesečni limit) — sve čitano iz feature_registry (migracija 064), NE
prosleđeno kao parametar iz endpoint-a.

Upotreba u routeru — DVA ODVOJENA poziva, tim redosledom:

    from shared.permissions import PermissionService
    from shared.usage import UsageService
    from shared.features import FEATURE_CASE_DNA

    @router.post("/api/case-dna/refresh")
    async def refresh(
        user: dict = Depends(PermissionService.require(FEATURE_CASE_DNA)),
    ):
        ... (generiši AI odgovor) ...
        await UsageService.consume(user["user_id"], user["email"], FEATURE_CASE_DNA)

Endpoint NE zna koliko feature košta — to je Registry-jeva odgovornost.
Ne prikazuje tehničke detalje (OpenAI tokene, broj poziva modelu) nikad
korisniku — samo "Mesečni AI fond" i preostali broj kredita (frontend-ova
odgovornost preko postojećeg userCredits/updateCreditDisplay obrasca).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

from fastapi import HTTPException, status

from shared.deps import (
    _deduct_credit,
    _deduct_n_credits,
    _get_credits,
    _get_supa,
    _is_founder,
    _refund_one_credit,
)
from shared.feature_registry import get_policy

logger = logging.getLogger("vindex.usage")

FOUNDER_BALANCE = 9999


def _today_iso() -> str:
    return date.today().isoformat()


def _month_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def _get_usage_row(user_id: str, feature: str) -> dict | None:
    def _q():
        return (
            _get_supa()
            .table("feature_usage")
            .select("broj_koriscenja, mesec")
            .eq("user_id", user_id)
            .eq("feature_key", feature)
            .eq("dan", _today_iso())
            .maybe_single()
            .execute()
        )
    try:
        res = await asyncio.to_thread(_q)
        return res.data
    except Exception as exc:
        logger.warning("[USAGE] _get_usage_row greška (non-fatal): %s", exc)
        return None


async def _get_monthly_count(user_id: str, feature: str) -> int:
    def _q():
        return (
            _get_supa()
            .table("feature_usage")
            .select("broj_koriscenja")
            .eq("user_id", user_id)
            .eq("feature_key", feature)
            .eq("mesec", _month_iso())
            .execute()
        )
    try:
        res = await asyncio.to_thread(_q)
        return sum((r.get("broj_koriscenja") or 0) for r in (res.data or []))
    except Exception as exc:
        logger.warning("[USAGE] _get_monthly_count greška (non-fatal): %s", exc)
        return 0


async def _increment_usage(user_id: str, feature: str, credits_spent: float) -> None:
    today = _today_iso()
    mesec = _month_iso()

    def _upsert():
        supa = _get_supa()
        existing = (
            supa.table("feature_usage")
            .select("broj_koriscenja, krediti_potroseni")
            .eq("user_id", user_id)
            .eq("feature_key", feature)
            .eq("dan", today)
            .maybe_single()
            .execute()
        )
        if existing.data:
            supa.table("feature_usage").update({
                "broj_koriscenja": (existing.data.get("broj_koriscenja") or 0) + 1,
                "krediti_potroseni": float(existing.data.get("krediti_potroseni") or 0) + credits_spent,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("user_id", user_id).eq("feature_key", feature).eq("dan", today).execute()
        else:
            supa.table("feature_usage").insert({
                "user_id": user_id,
                "feature_key": feature,
                "dan": today,
                "mesec": mesec,
                "broj_koriscenja": 1,
                "krediti_potroseni": credits_spent,
            }).execute()

    try:
        await asyncio.to_thread(_upsert)
    except Exception as exc:
        # Ne blokiraj korisnika zbog greške u brojanju upotrebe — kredit je već
        # (ili nije) potrošen preko atomičnog RPC-a, to je izvor istine za novac.
        logger.warning("[USAGE] _increment_usage greška (non-fatal): %s", exc)


class UsageService:
    @staticmethod
    async def consume(user_id: str, email: str, feature: str) -> int:
        """
        Proverava dnevni/mesečni limit, zatim atomično oduzima kredite —
        SVE vrednosti čitane iz feature_registry (Admin Feature Console),
        NIKAD prosleđene kao parametar. Founder nikad ne plaća i ne trpi
        dnevni/mesečni limit (samo aktivno=false kill-switch ga zaustavlja,
        to je provereno u PermissionService pre ovog poziva).

        Vraća preostali broj kredita. Baca HTTPException(402/429) ako nema
        budžeta.
        """
        policy = await get_policy(feature)
        credits = float(policy.get("krediti") or 0)
        dnevni_limit = policy.get("dnevni_limit")
        mesecni_limit = policy.get("mesecni_limit")

        if _is_founder(email):
            return FOUNDER_BALANCE

        if dnevni_limit is not None:
            row = await _get_usage_row(user_id, feature)
            used_today = (row or {}).get("broj_koriscenja") or 0
            if used_today >= dnevni_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "code": "DAILY_LIMIT",
                        "feature": feature,
                        "message": "Dostigli ste dnevni limit korišćenja za ovu funkciju. Pokušajte sutra.",
                    },
                )

        if mesecni_limit is not None:
            used_month = await _get_monthly_count(user_id, feature)
            if used_month >= mesecni_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "code": "MONTHLY_LIMIT",
                        "feature": feature,
                        "message": "Dostigli ste mesečni limit korišćenja za ovu funkciju.",
                    },
                )

        if credits > 0:
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
                preostalo = await asyncio.to_thread(_deduct_n_credits, user_id, email, int(credits))
            if preostalo < 0:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "code": "NO_CREDITS",
                        "feature": feature,
                        "message": "Nemate dovoljno kredita u mesečnom AI fondu za ovu funkciju.",
                        "credits_remaining": 0,
                    },
                )
        else:
            preostalo = await asyncio.to_thread(_get_credits, user_id)

        await _increment_usage(user_id, feature, credits)
        return preostalo

    @staticmethod
    async def balance(user_id: str, email: str) -> int:
        if _is_founder(email):
            return FOUNDER_BALANCE
        return await asyncio.to_thread(_get_credits, user_id)

    @staticmethod
    async def refund(user_id: str, email: str, feature: str) -> None:
        """Best-effort refund (npr. greška u generisanju posle uspešnog consume())."""
        if _is_founder(email):
            return
        policy = await get_policy(feature)
        credits = int(policy.get("krediti") or 0)
        for _ in range(max(credits, 0)):
            await asyncio.to_thread(_refund_one_credit, user_id)

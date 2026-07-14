# -*- coding: utf-8 -*-
"""
Vindex AI — shared/permissions.py

PermissionService — JEDINI mehanizam kojim endpoint proverava da li nalog
sme da pristupi funkciji. Zamenjuje require_pro, direktne is_pro provere,
i sve ad-hoc "if plan == ..." obrasce pronađene u docs/ENTITLEMENT_AUDIT_PHASE1.md.

Politika (minimalna tarifa, addon, da li je funkcija uopšte uključena) NIJE
ovde — čita se isključivo iz feature_registry tabele preko
shared/feature_registry.py (Admin Feature Console je jedini način da se
promeni, ne izmena koda).

Upotreba u routeru:

    from shared.permissions import PermissionService
    from shared.features import FEATURE_CASE_DNA

    @router.post("/api/case-dna/refresh")
    async def refresh(user: dict = Depends(PermissionService.require(FEATURE_CASE_DNA))):
        ...

PermissionService odgovara SAMO na pitanje "ima li nalog pravo pristupa
funkciji" — ne zna ništa o kreditima/limitima potrošnje. Za to postoji
UsageService (shared/usage.py), namerno odvojen sloj.

Founder uvek prolazi tarifu/addon proveru. Kill-switch (feature_registry.
aktivno = false) VAŽI I ZA FOUNDERA — namerno, to je hitna kočnica za
nekontrolisan trošak, ne treba da ima rupu.

Legacy Professional nalozi (subscription_expires_at u prošlosti) se tretiraju
kao da su pali na 'basic' — automatski, po specifikaciji.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, HTTPException, status

from shared.deps import _ensure_profile, _is_founder, get_current_user
from shared.feature_registry import get_policy

logger = logging.getLogger("vindex.permissions")

_TIER_ORDER = {"basic": 0, "professional": 1, "enterprise": 2}


def _is_expired(expires_at) -> bool:
    if not expires_at:
        return False
    try:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        return expires_at < datetime.now(timezone.utc)
    except Exception:
        logger.warning("[PERMISSIONS] Ne mogu da parsiram subscription_expires_at=%r", expires_at)
        return False


def effective_tier(profil: dict) -> str:
    """Efektivna tarifa naloga, uzimajući u obzir istek Legacy Professional statusa."""
    subscription_type = profil.get("subscription_type") or "basic"
    if _is_expired(profil.get("subscription_expires_at")) and subscription_type != "basic":
        return "basic"
    return subscription_type


def _tier_satisfies(user_tier: str, required_tier: str) -> bool:
    return _TIER_ORDER.get(user_tier, -1) >= _TIER_ORDER.get(required_tier, 999)


class PermissionService:
    """Statička fabrika FastAPI dependency-ja — svaki poziv .require(FEATURE_X)
    pravi NOVU dependency funkciju zatvorenu nad konkretnim feature-om."""

    @staticmethod
    def require(feature: str) -> Callable:
        async def _dependency(user: dict = Depends(get_current_user)) -> dict:
            email = user.get("email", "")
            policy = await get_policy(feature)

            # Kill-switch važi za SVE, bez izuzetka — namerna hitna kočnica.
            if not policy.get("aktivno", True):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Ova funkcija je privremeno onemogućena. Pokušajte kasnije.",
                )

            if _is_founder(email):
                user["subscription_type"] = "enterprise"
                user["addons"] = []
                user["_feature_policy"] = policy
                return user

            profil = await asyncio.to_thread(_ensure_profile, user["user_id"], email)
            addon_required = policy.get("addon")

            if addon_required:
                user_addons = profil.get("addons") or []
                if addon_required not in user_addons and f"{addon_required}_standalone" not in user_addons:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=(
                            "Ova funkcija zahteva Vindex AI - Digitalna imovina & usklađenost "
                            "dodatak. Aktivirajte ga u Podešavanjima ili nas kontaktirajte."
                        ),
                    )
                user["subscription_type"] = effective_tier(profil)
                user["addons"] = user_addons
                user["_feature_policy"] = policy
                return user

            required_tier = policy.get("minimum_plan")
            if required_tier:
                user_tier = effective_tier(profil)
                if not _tier_satisfies(user_tier, required_tier):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=(
                            f"Ova funkcija zahteva {required_tier.capitalize()} tarifu ili višu. "
                            f"Vaša trenutna tarifa: {user_tier.capitalize()}."
                        ),
                    )
                user["subscription_type"] = user_tier
            else:
                user["subscription_type"] = effective_tier(profil)

            user["addons"] = profil.get("addons") or []
            user["_feature_policy"] = policy
            return user

        return _dependency

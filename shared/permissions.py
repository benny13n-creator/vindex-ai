# -*- coding: utf-8 -*-
"""
Vindex AI — shared/permissions.py

PermissionService — JEDINI mehanizam kojim endpoint proverava da li nalog
sme da pristupi funkciji. Zamenjuje require_pro, direktne is_pro provere,
i sve ad-hoc "if plan == ..." obrasce pronađene u docs/ENTITLEMENT_AUDIT_PHASE1.md.

Upotreba u routeru:

    from shared.permissions import PermissionService
    from shared.features import FEATURE_CASE_DNA

    @router.post("/api/case-dna/refresh")
    async def refresh(user: dict = Depends(PermissionService.require(FEATURE_CASE_DNA))):
        ...

PermissionService odgovara SAMO na pitanje "ima li nalog pravo pristupa
funkciji" — ne zna ništa o kreditima/limitima potrošnje. Za to postoji
UsageService (shared/usage.py), namerno odvojen sloj.

Founder uvek prolazi (isti obrazac kao _is_founder svuda u projektu).
Legacy Professional nalozi (subscription_expires_at u prošlosti) se
tretiraju kao da su pali na 'basic' — automatski, bez ručne intervencije,
tačno po specifikaciji: "Posle toga: automatski prelaze na Basic ako ne
kupe Professional."
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, HTTPException, status

from shared.deps import _ensure_profile, _is_founder, get_current_user
from shared.features import (
    FEATURE_ADDON,
    FEATURE_TIER,
    has_addon,
    tier_satisfies,
)

logger = logging.getLogger("vindex.permissions")


def _is_expired(expires_at) -> bool:
    if not expires_at:
        return False
    try:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        return expires_at < datetime.now(timezone.utc)
    except Exception:
        # Nepoznat format — ne blokiraj korisnika zbog parsing greške, samo loguj.
        logger.warning("[PERMISSIONS] Ne mogu da parsiram subscription_expires_at=%r", expires_at)
        return False


def effective_tier(profil: dict) -> str:
    """
    Efektivna tarifa naloga, uzimajući u obzir istek Legacy Professional statusa.
    Ne dira bazu — čisto izračunavanje nad već pročitanim profilom.
    """
    subscription_type = profil.get("subscription_type") or "basic"
    if _is_expired(profil.get("subscription_expires_at")) and subscription_type != "basic":
        return "basic"
    return subscription_type


class PermissionService:
    """Statička fabrika FastAPI dependency-ja — svaki poziv .require(FEATURE_X)
    pravi NOVU dependency funkciju zatvorenu nad konkretnim feature-om."""

    @staticmethod
    def require(feature: str) -> Callable:
        if feature not in FEATURE_TIER and feature not in FEATURE_ADDON:
            # Programerska greška, ne korisnička — Feature Matrix mora biti kompletna.
            raise RuntimeError(
                f"PermissionService.require('{feature}'): feature nije mapiran ni u "
                f"FEATURE_TIER ni u FEATURE_ADDON (shared/features.py). Dodaj ga tamo pre upotrebe."
            )

        async def _dependency(user: dict = Depends(get_current_user)) -> dict:
            email = user.get("email", "")

            if _is_founder(email):
                user["subscription_type"] = "enterprise"
                user["addons"] = []
                return user

            profil = await asyncio.to_thread(_ensure_profile, user["user_id"], email)

            if feature in FEATURE_ADDON:
                if not has_addon(profil.get("addons", []), feature):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=(
                            "Ova funkcija zahteva Vindex AI - Digitalna imovina & usklađenost "
                            "dodatak. Aktivirajte ga u Podešavanjima ili nas kontaktirajte."
                        ),
                    )
                user["subscription_type"] = effective_tier(profil)
                user["addons"] = profil.get("addons", [])
                return user

            required_tier = FEATURE_TIER[feature]
            user_tier = effective_tier(profil)
            if not tier_satisfies(user_tier, required_tier):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        f"Ova funkcija zahteva {required_tier.capitalize()} tarifu ili višu. "
                        f"Vaša trenutna tarifa: {user_tier.capitalize()}."
                    ),
                )
            user["subscription_type"] = user_tier
            user["addons"] = profil.get("addons", [])
            return user

        return _dependency

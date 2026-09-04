# -*- coding: utf-8 -*-
"""
Vindex AI — shared/permissions.py

PermissionService — JEDINI mehanizam kojim endpoint proverava da li nalog
sme da pristupi funkciji. Zamenjuje require_pro, direktne is_pro provere,
i sve ad-hoc "if plan == ..." obrasce pronađene u docs/ENTITLEMENT_AUDIT_PHASE1.md.

Politika (minimalna tarifa, addon, status, vidljivost, zavisnosti) NIJE
ovde — čita se isključivo iz feature_registry/feature_dependencies preko
shared/feature_registry.py (Admin Feature Console je jedini način da se
promeni, ne izmena koda).

Upotreba u routeru — feature_key je RAW STRING, isti onaj koji stoji u
feature_registry.feature_key koloni. Namerno nema Python FEATURE_* konstanti
— to bi bio drugi izvor istine pored baze i vremenom bi se rasinhronizovao
(tačno se to i desilo u prvoj verziji ovog modula pre nego što je uklonjeno).
Typo se hvata glasno: PermissionService.require() baca RuntimeError iz
get_policy() ako feature_key ne postoji u bazi.

    from shared.permissions import PermissionService

    @router.post("/api/case-dna/refresh")
    async def refresh(user: dict = Depends(PermissionService.require("case_dna"))):
        ...

PermissionService odgovara SAMO na pitanje "ima li nalog pravo pristupa
funkciji" — ne zna ništa o kreditima/limitima potrošnje. Za to postoji
UsageService (shared/usage.py), namerno odvojen sloj.

Redosled provera (prva koja padne — blokira):
  1. Kill-switch (aktivno=false)     — blokira SVE, uključujući foundera.
  2. Zavisnosti (feature_dependencies) — blokira SVE ako je bilo koja
     zavisna funkcija neaktivna/deprecated — ovo je provera ispravnosti
     sistema, ne kontrola pristupa, pa ni founder ne prolazi.
  3. status = DEPRECATED / COMING_SOON — blokira obične korisnike, founder
     prolazi (da može da testira/debaguje pre lansiranja ili posle gašenja).
  4. status = INTERNAL               — SAMO founder prolazi.
  5. addon / minimum_plan            — standardna tarifna provera, founder
     uvek prolazi.

Legacy Professional nalozi (subscription_expires_at u prošlosti) se tretiraju
kao da su pali na 'basic' — automatski, po specifikaciji.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, HTTPException, status as http_status

from shared.deps import _ensure_profile, _is_founder, get_current_user
from shared.feature_registry import get_dependencies, get_policy

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
        # S4-1 (2026-08-09): direction deliberately UNCHANGED, visibility fixed.
        #
        # An unparsable value here is our own data, written by our own code --
        # corruption or a schema change, never a user action. Both directions
        # are wrong: failing closed silently drops a paying lawyer to basic
        # mid-case, failing open silently grants Professional to a lapsed legacy
        # account. Locking a lawyer out of their own case file is the worse of
        # the two, so the direction stays.
        #
        # The actual defect was that it was INVISIBLE: logger.warning in a
        # system with no alerting is a message nobody reads. ERROR, with the
        # offending value, so it can be found and fixed at the source.
        logger.error(
            "[PERMISSIONS] NEPARSIV subscription_expires_at=%r — tretiram kao "
            "NEISTEKAO (fail-open na entitlement). Podatak je pokvaren i treba "
            "ga ispraviti u bazi.",
            expires_at,
        )
        return False


def effective_tier(profil: dict) -> str:
    """Efektivna tarifa naloga, uzimajući u obzir istek Legacy Professional statusa."""
    subscription_type = profil.get("subscription_type") or "basic"
    if _is_expired(profil.get("subscription_expires_at")) and subscription_type != "basic":
        return "basic"
    return subscription_type


def _tier_satisfies(user_tier: str, required_tier: str) -> bool:
    return _TIER_ORDER.get(user_tier, -1) >= _TIER_ORDER.get(required_tier, 999)


async def _check_dependencies(feature: str) -> None:
    """Ako feature zavisi od druge funkcije koja je neaktivna/deprecated,
    blokira SVE pozive (uključujući foundera) — ovo je provera ispravnosti,
    ne kontrola pristupa."""
    deps = await get_dependencies(feature)
    for dep_key in deps:
        try:
            dep_policy = await get_policy(dep_key)
        except RuntimeError:
            continue  # zavisnost referencira nepostojeći feature — ne blokiraj zbog toga
        if not dep_policy.get("aktivno", True) or dep_policy.get("status") in ("DEPRECATED", "COMING_SOON"):
            raise HTTPException(
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"Ova funkcija trenutno nije dostupna jer zavisi od funkcije "
                    f"'{dep_policy.get('naziv', dep_key)}' koja je privremeno isključena."
                ),
            )


class PermissionService:
    """Statička fabrika FastAPI dependency-ja — svaki poziv .require(feature_key)
    pravi NOVU dependency funkciju zatvorenu nad konkretnim feature-om."""

    @staticmethod
    def require(feature: str) -> Callable:
        async def _dependency(user: dict = Depends(get_current_user)) -> dict:
            email = user.get("email", "")
            policy = await get_policy(feature)
            is_founder = _is_founder(email)

            # 1) Kill-switch — blokira SVE, bez izuzetka.
            if not policy.get("aktivno", True):
                raise HTTPException(
                    status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Ova funkcija je privremeno onemogućena. Pokušajte kasnije.",
                )

            # 2) Zavisnosti — provera ispravnosti sistema, važi i za foundera.
            await _check_dependencies(feature)

            feature_status = policy.get("status", "ACTIVE")

            # 2.5) ROLLOUT — interna kapija za postepeno puštanje (migracija 128).
            #
            # Stoji IZNAD svakog founder izuzetka, i to je cela poenta ove grane.
            # Za ROLLOUT tip postoji tačno jedna osa koja odlučuje: da li je
            # feature_key dodeljen ovom nalogu u `profiles.rollout_flags`. Nema
            # tarife, nema addon-a, nema founder prečice. Da founder izuzetak
            # ostao iznad, opoziv se ne bi mogao dokazati ni na jednom founder
            # nalogu — dodela i oduzimanje davali bi isti ishod.
            #
            # Zašto ovo ne menja nijednu zatečenu funkciju: grana se otvara samo
            # za `feature_type == "ROLLOUT"`, a nijedan od 70 zatečenih redova
            # nema tu vrednost (pre migracije 128 je CHECK constraint nije ni
            # dozvoljavao). Ponašanje ostalih redova je zato bajt u bajt isto.
            if policy.get("feature_type") == "ROLLOUT":
                # Životni ciklus reda blokira SVE, bez founder izuzetka —
                # rollout kapija koja je ugašena mora biti ugašena i za foundera.
                if feature_status in ("DEPRECATED", "COMING_SOON"):
                    raise HTTPException(
                        status_code=http_status.HTTP_404_NOT_FOUND,
                        detail="Ova funkcija nije dostupna.",
                    )

                profil = await asyncio.to_thread(_ensure_profile, user["user_id"], email)
                dodele = profil.get("rollout_flags")

                # Fail-closed na svaki oblik neispravnog podatka: NULL, pogrešan
                # tip, jsonb objekat ili string. Kod stringa bi `in` radio
                # poklapanje PODNIZA, pa bi npr. "nema_v2_pristupa" propustilo
                # "v2_pristup" — zato lista, ili ništa.
                if not isinstance(dodele, list) or feature not in dodele:
                    raise HTTPException(
                        status_code=http_status.HTTP_403_FORBIDDEN,
                        detail="Restricted.",
                    )

                user["subscription_type"] = effective_tier(profil)
                user["addons"] = profil.get("addons") or []
                user["_feature_policy"] = policy
                return user

            # 3) DEPRECATED / COMING_SOON — obični korisnici blokirani, founder prolazi.
            if feature_status in ("DEPRECATED", "COMING_SOON") and not is_founder:
                msg = (
                    "Ova funkcija je ukinuta."
                    if feature_status == "DEPRECATED"
                    else "Ova funkcija uskoro stiže."
                )
                raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=msg)

            # 4) INTERNAL — samo founder.
            if feature_status == "INTERNAL" and not is_founder:
                raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Restricted.")

            if is_founder:
                user["subscription_type"] = "enterprise"
                user["addons"] = []
                user["_feature_policy"] = policy
                return user

            # 5) Standardna tarifna/addon provera.
            profil = await asyncio.to_thread(_ensure_profile, user["user_id"], email)
            addon_required = policy.get("addon")

            if addon_required:
                user_addons = profil.get("addons") or []
                if addon_required not in user_addons and f"{addon_required}_standalone" not in user_addons:
                    raise HTTPException(
                        status_code=http_status.HTTP_403_FORBIDDEN,
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
                        status_code=http_status.HTTP_403_FORBIDDEN,
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

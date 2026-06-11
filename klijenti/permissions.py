# -*- coding: utf-8 -*-
"""
Klijenti — Role-based access control.

Hijerarhija rola (od visokog do niskog):
  partner > advokat > pripravnik > sekretarica

Field classification:
  PUBLIC             — svi vide
  INTERNAL           — sekretarica ne vidi
  CONFIDENTIAL       — partner + advokat (JMBG, pasoš, PIB)
  HIGHLY_CONFIDENTIAL — partner + advokat + eksplicitni click + audit
"""
from __future__ import annotations

import logging
from enum import IntEnum
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

logger = logging.getLogger("vindex.klijenti.permissions")


# ─── Role definicija ──────────────────────────────────────────────────────────

class Role(IntEnum):
    SEKRETARICA = 0
    PRIPRAVNIK  = 1
    ADVOKAT     = 2
    PARTNER     = 3


ROLE_STR: dict[str, Role] = {
    "sekretarica": Role.SEKRETARICA,
    "pripravnik":  Role.PRIPRAVNIK,
    "advokat":     Role.ADVOKAT,
    "partner":     Role.PARTNER,
}
ROLE_NAMES: dict[Role, str] = {v: k for k, v in ROLE_STR.items()}

DEFAULT_ROLE = Role.ADVOKAT


# ─── Field classification ─────────────────────────────────────────────────────

class FC:
    PUBLIC             = "public"
    INTERNAL           = "internal"
    CONFIDENTIAL       = "confidential"
    HIGHLY_CONFIDENTIAL = "highly_confidential"


KLIJENT_FIELD_CLASS: dict[str, str] = {
    # PUBLIC
    "id":                        FC.PUBLIC,
    "tip":                       FC.PUBLIC,
    "ime":                       FC.PUBLIC,
    "prezime":                   FC.PUBLIC,
    "firma":                     FC.PUBLIC,
    "status":                    FC.PUBLIC,
    "datum_nastanka":            FC.PUBLIC,
    "datum_poslednje_aktivnosti": FC.PUBLIC,
    "kreirano":                  FC.PUBLIC,
    "azurirano":                 FC.PUBLIC,
    "aktivan":                   FC.PUBLIC,
    # INTERNAL
    "telefon":                   FC.INTERNAL,
    "email":                     FC.INTERNAL,
    "adresa":                    FC.INTERNAL,
    "maticni_broj":              FC.INTERNAL,
    "napomena":                  FC.INTERNAL,
    "pravni_osnov_obrade":       FC.INTERNAL,
    # CONFIDENTIAL
    "jmbg_mb":                   FC.CONFIDENTIAL,
    "jmbg_encrypted":            FC.CONFIDENTIAL,
    "broj_pasosa_encrypted":     FC.CONFIDENTIAL,
    "pib_encrypted":             FC.CONFIDENTIAL,
    # HIGHLY_CONFIDENTIAL
    "connected_persons":         FC.HIGHLY_CONFIDENTIAL,
    "saglasnost_datum":          FC.HIGHLY_CONFIDENTIAL,
    "saglasnost_dokument_id":    FC.HIGHLY_CONFIDENTIAL,
    "deleted_at":                FC.HIGHLY_CONFIDENTIAL,
}

ROLE_FIELD_ACCESS: dict[str, frozenset[Role]] = {
    FC.PUBLIC:             frozenset({Role.SEKRETARICA, Role.PRIPRAVNIK, Role.ADVOKAT, Role.PARTNER}),
    FC.INTERNAL:           frozenset({Role.PRIPRAVNIK, Role.ADVOKAT, Role.PARTNER}),
    FC.CONFIDENTIAL:       frozenset({Role.ADVOKAT, Role.PARTNER}),
    FC.HIGHLY_CONFIDENTIAL: frozenset({Role.ADVOKAT, Role.PARTNER}),
}

# Minimum rola za akcije
ACTION_MIN_ROLE: dict[str, Role] = {
    "create_client":          Role.SEKRETARICA,
    "edit_client":            Role.SEKRETARICA,
    "soft_delete_client":     Role.PARTNER,
    "archive_client":         Role.ADVOKAT,
    "view_audit_log":         Role.PARTNER,
    "view_conflict_results":  Role.PRIPRAVNIK,
    "access_confidential":    Role.ADVOKAT,
    "download_document":      Role.ADVOKAT,
}


def can_access_field(role: Role, field: str) -> bool:
    classification = KLIJENT_FIELD_CLASS.get(field, FC.INTERNAL)
    return role in ROLE_FIELD_ACCESS.get(classification, frozenset())


def can_perform(role: Role, action: str) -> bool:
    required = ACTION_MIN_ROLE.get(action, Role.PARTNER)
    return role >= required


def filter_klijent(klijent: dict, role: Role) -> dict:
    """Filtrira dict klijenta prema dozvoljenoj roli."""
    return {
        k: v for k, v in klijent.items()
        if can_access_field(role, k)
    }


# ─── FastAPI dependencies ──────────────────────────────────────────────────────

def _role_from_db(user_id: str, email: str, supa) -> Role:
    """
    Čita rolu korisnika iz user_roles tabele.
    Founder → PARTNER; nezapisan korisnik → DEFAULT_ROLE (ADVOKAT).
    """
    # Founders uvek dobijaju PARTNER
    founder_emails_raw = __import__("os").getenv("FOUNDER_EMAILS", "")
    founder_emails = {e.strip().lower() for e in founder_emails_raw.split(",") if e.strip()}
    if (email or "").lower() in founder_emails:
        return Role.PARTNER

    try:
        res = supa.table("user_roles").select("rola").eq("user_id", user_id).single().execute()
        if res.data:
            return ROLE_STR.get(res.data.get("rola", ""), DEFAULT_ROLE)
    except Exception as e:
        logger.warning("[PERMISSIONS] user_roles read greška za uid=%.8s: %s", user_id, e)
    return DEFAULT_ROLE


def make_role_dependency(supa_getter):
    """
    Factory za FastAPI dependency koji prikači rolu na user dict.
    Koristiti: user_with_role = Depends(make_role_dependency(_get_supa))
    """
    async def _get_user_role(user: dict = Depends(_get_current_user_stub)):
        import asyncio
        supa = supa_getter()
        role = await asyncio.to_thread(_role_from_db, user["user_id"], user.get("email", ""), supa)
        user["role"] = role
        user["role_str"] = ROLE_NAMES.get(role, "advokat")
        return user
    return _get_user_role


# Placeholder — biće overridden u router-u koji ima pravi get_current_user
def _get_current_user_stub():
    raise RuntimeError("Koristite make_role_dependency sa pravim get_current_user")


def require_role(min_role: Role):
    """Dependency koji proverava minimum rolu. Koristiti posle role_dep."""
    def _check(user: dict):
        role = user.get("role", DEFAULT_ROLE)
        if role < min_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Ova akcija zahteva rolu '{ROLE_NAMES.get(min_role, '?')}' ili višu.",
            )
        return user
    return _check


def require_action(action: str):
    """Dependency koji proverava da user role dozvoljava određenu akciju."""
    def _check(user: dict):
        role = user.get("role", DEFAULT_ROLE)
        if not can_perform(role, action):
            min_r = ACTION_MIN_ROLE.get(action, Role.PARTNER)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Nedovoljno prava za akciju '{action}'. Potrebna rola: {ROLE_NAMES.get(min_r, '?')}.",
            )
        return user
    return _check

# -*- coding: utf-8 -*-
"""
Klijenti — Append-only audit log.

Tabela: klijenti_audit
RLS: INSERT only za service_role. NEMA UPDATE ni DELETE za iko.

Svaka akcija nad klijentom (VIEW, EDIT, DOWNLOAD, itd.) mora biti
zabeležena OVDE — ne u generalnom audit_log.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("vindex.klijenti.audit")


class Akcija:
    VIEW              = "VIEW"
    VIEW_CONFIDENTIAL = "VIEW_CONFIDENTIAL"
    CREATE            = "CREATE"
    EDIT              = "EDIT"
    SOFT_DELETE       = "DELETE_SOFT"
    ARCHIVE           = "ARCHIVE"
    DOWNLOAD          = "DOWNLOAD"
    EXPORT            = "EXPORT"
    CONFLICT_FLAGGED  = "CONFLICT_CHECK_FLAGGED"
    KOMUNIKACIJA_ADD  = "KOMUNIKACIJA_ADD"


async def log_event(
    *,
    supa,
    user_id: str,
    user_email: str,
    user_role: str,
    akcija: str,
    entitet_id: Optional[str] = None,
    entitet_tip: str = "klijent",
    detalji: Optional[dict] = None,
    ip_adresa: Optional[str] = None,
) -> None:
    """
    Fire-and-forget audit log. Greška ne blokira odgovor.
    MORA biti pozvan pre vraćanja CONFIDENTIAL podataka.
    """
    try:
        await asyncio.to_thread(
            lambda: supa.table("klijenti_audit").insert({
                "user_id":     user_id,
                "user_email":  user_email,
                "user_role":   user_role,
                "akcija":      akcija,
                "entitet_tip": entitet_tip,
                "entitet_id":  entitet_id,
                "detalji":     detalji or {},
                "ip_adresa":   ip_adresa,
            }).execute()
        )
        logger.debug("[AUDIT] %s uid=%.8s eid=%s", akcija, user_id, entitet_id)
    except Exception as e:
        logger.warning("[AUDIT] log_event greška (non-blocking): %s", e)


def get_client_ip(request) -> Optional[str]:
    """Izvlači IP adresu iz request headera (Render proxy-aware)."""
    if request is None:
        return None
    forwarded_for = (request.headers.get("x-forwarded-for") or "").split(",")
    if forwarded_for and forwarded_for[0].strip():
        return forwarded_for[0].strip()
    return getattr(getattr(request, "client", None), "host", None)

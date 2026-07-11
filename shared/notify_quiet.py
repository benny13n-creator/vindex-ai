# -*- coding: utf-8 -*-
"""
Vindex AI — shared/notify_quiet.py

Zajednička logika za Viber/SMS notifikacije:
  - is_quiet_now()     — da li je korisnik u tihom periodu (per-user quiet_start/quiet_end)
  - log_notification() — audit upis u notification_log za svako slanje (cron-trigerovano)

Koriste: routers/portal_monitoring.py, routers/sms.py
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from shared.deps import _get_supa

logger = logging.getLogger("vindex.notify_quiet")


def is_quiet_now(profile: Optional[dict], critical: bool = False) -> bool:
    """
    Vraća True ako je sada tihi period za ovaj profil i notifikacija NE sme da se pošalje.
    profile: red iz korisnik_viber_profil / korisnik_sms_profil (quiet_start, quiet_end, allow_critical_override).
    critical=True — hitna notifikacija koja može da zaobiđe tihi period ako je allow_critical_override aktivan.
    Nema podešen quiet_start/quiet_end -> nikad tih (default ponašanje, bez ograničenja).
    """
    if not profile:
        return False

    qs = profile.get("quiet_start")
    qe = profile.get("quiet_end")
    if qs is None or qe is None:
        return False

    h = datetime.now().hour
    if qs == qe:
        u_periodu = False
    elif qs < qe:
        u_periodu = qs <= h < qe
    else:
        u_periodu = h >= qs or h < qe  # period preko ponoći, npr. 22 -> 8

    if not u_periodu:
        return False

    if critical and profile.get("allow_critical_override", True):
        return False

    return True


async def log_notification(
    user_id: str,
    channel: str,
    tip: str,
    delivery_status: str,
    ref_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """Fire-and-forget audit upis svakog cron-trigerovanog Viber/SMS slanja."""
    try:
        supa = _get_supa()
        row = {
            "user_id":         user_id,
            "channel":         channel,
            "tip":             tip[:50],
            "ref_id":          ref_id,
            "delivery_status": delivery_status,
            "error_message":   error_message,
        }
        await asyncio.to_thread(lambda: supa.table("notification_log").insert(row).execute())
    except Exception as e:
        logger.debug("[NOTIFY_QUIET] Log greška: %s", e)

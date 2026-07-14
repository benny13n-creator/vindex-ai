# -*- coding: utf-8 -*-
"""
Vindex AI — shared/seats.py

SeatService — jedini izvor istine za korisnička mesta (seats) u firmi
(kancelarija_clanovi), istog obrasca kao PermissionService/UsageService:
jedna služba, jedna formula, jedan audit trag. Migracija 067.

Model (5 stanja, founder-ov zahtev):
    ACTIVE    — član aktivno koristi mesto
    INVITED   — poziv poslat, još nije prihvaćen
    PENDING   — registrovan, čeka odobrenje (rezervisano za budući self-serve
                "zahtev za pridruživanje" tok — danas se nigde ne piše)
    SUSPENDED — privremeno isključen
    REMOVED   — istorijski zapis, ne zauzima mesto

Formula (namerno JEDNOSTAVNA, čitljiva na prvi pogled — ovo je upravo mesto
gde je greška najskuplja):
    iskorišćena_mesta = COUNT(status='ACTIVE') + COUNT(status='INVITED')

Zašto INVITED troši mesto: bez toga bi admin na paketu od 3 mesta mogao
poslati 300 pozivnica i nijedna se ne bi računala dok se ne prihvati — svaka
bi mogla biti prihvaćena istog trena i preplaviti kapacitet. INVITED je
REZERVACIJA mesta, ne samo obaveštenje.

Svaka promena statusa MORA proći kroz ovu službu i upisati red u
kancelarija_seat_audit — nikad direktan UPDATE nad kancelarija_clanovi.status
iz routera.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status as http_status

from shared.deps import _get_supa

logger = logging.getLogger("vindex.seats")

# Samo enterprise tarifa ima multi-seat koncept — basic/professional su
# single-user po dizajnu (jedan nalog = jedan korisnik, bez tim funkcije).
BASE_INCLUDED_SEATS: dict[str, int] = {
    "basic": 1,
    "professional": 1,
    "enterprise": 3,
}

SEAT_CONSUMING_STATUSES = ("ACTIVE", "INVITED")

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "INVITED":   {"ACTIVE", "REMOVED"},              # accept / decline
    "ACTIVE":    {"SUSPENDED", "REMOVED"},            # suspend / remove-or-leave
    "SUSPENDED": {"ACTIVE", "REMOVED"},                # reactivate / remove
    "PENDING":   {"ACTIVE", "REMOVED"},                # approve / reject (future flow)
    "REMOVED":   {"INVITED"},                          # re-invite reuses the same row; audit trail
                                                        # keeps the original REMOVED transition on record
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SeatService:
    @staticmethod
    async def get_seat_summary(kancelarija_id: str, admin_uid: str) -> dict:
        """Vraća kompletan pregled iskorišćenosti mesta za jednu firmu.
        admin_uid mora biti profiles.id čiji subscription_type/
        subscription_seats_extra definiše kapacitet (firma = admin-ova tarifa)."""
        supa = _get_supa()

        def _fetch():
            prof_r = (
                supa.table("profiles")
                .select("subscription_type, subscription_seats_extra")
                .eq("id", admin_uid)
                .maybe_single()
                .execute()
            )
            clan_r = (
                supa.table("kancelarija_clanovi")
                .select("status")
                .eq("kancelarija_id", kancelarija_id)
                .execute()
            )
            return prof_r.data or {}, clan_r.data or []

        profile, clanovi = await asyncio.to_thread(_fetch)

        tier = profile.get("subscription_type") or "basic"
        extra = int(profile.get("subscription_seats_extra") or 0)
        base = BASE_INCLUDED_SEATS.get(tier, 1)
        total_allowed = base + extra

        breakdown = {"ACTIVE": 0, "INVITED": 0, "PENDING": 0, "SUSPENDED": 0, "REMOVED": 0}
        for c in clanovi:
            st = c.get("status")
            if st in breakdown:
                breakdown[st] += 1
        # Admin sam po sebi zauzima jedno od uključenih mesta (nema svoj red
        # u kancelarija_clanovi — vidi routers/kancelarija.py komentar).
        used = 1 + breakdown["ACTIVE"] + breakdown["INVITED"]

        return {
            "tier": tier,
            "base_included_seats": base,
            "extra_seats_purchased": extra,
            "total_allowed_seats": total_allowed,
            "used_seats": used,
            "available_seats": max(0, total_allowed - used),
            "breakdown": breakdown,
        }

    @staticmethod
    async def assert_seat_available(kancelarija_id: str, admin_uid: str) -> dict:
        """Baca 403 ako nema slobodnog mesta. Vraća seat_summary ako ima (da
        pozivalac ne mora da ga ponovo učita)."""
        summary = await SeatService.get_seat_summary(kancelarija_id, admin_uid)
        if summary["available_seats"] <= 0:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "NO_SEATS_AVAILABLE",
                    "message": (
                        f"Nema slobodnih mesta. Iskorišćeno {summary['used_seats']}/"
                        f"{summary['total_allowed_seats']} ({summary['tier']} tarifa). "
                        f"Dokupite dodatno mesto (49€/mesečno) ili uklonite neaktivnog člana."
                    ),
                    **summary,
                },
            )
        return summary

    @staticmethod
    async def transition(
        kancelarija_id: str,
        clan_id: Optional[str],
        clan_email: str,
        actor_uid: str,
        actor_email: str,
        action: str,
        from_status: Optional[str],
        to_status: str,
        extra_fields: Optional[dict] = None,
    ) -> None:
        """JEDINO mesto koje sme da menja kancelarija_clanovi.status. Validira
        prelaz, upisuje ga (ako clan_id nije None — INVITED-kreiranje upisuje
        clan_id nakon insert-a, obrađeno u routers/kancelarija.py), i piše
        trajan audit red. Baca ValueError na nevalidan prelaz (programerska
        greška, ne korisnička — routers sloj ne sme dozvoliti da se to desi)."""
        if from_status is not None:
            allowed = _VALID_TRANSITIONS.get(from_status, set())
            if to_status not in allowed:
                raise ValueError(
                    f"Nevalidan prelaz {from_status} → {to_status} (dozvoljeno iz {from_status}: {allowed or 'ništa — terminalno stanje'})"
                )

        supa = _get_supa()

        def _write():
            if clan_id:
                update = {"status": to_status, **(extra_fields or {})}
                supa.table("kancelarija_clanovi").update(update).eq("id", clan_id).execute()
            supa.table("kancelarija_seat_audit").insert({
                "kancelarija_id": kancelarija_id,
                "clan_id":        clan_id,
                "clan_email":     clan_email,
                "actor_uid":      actor_uid,
                "actor_email":    actor_email,
                "action":         action,
                "from_status":    from_status,
                "to_status":      to_status,
                "created_at":     _now(),
            }).execute()

        try:
            await asyncio.to_thread(_write)
        except Exception as exc:
            logger.error(
                "[SEATS] Neuspeo upis prelaza %s: %s→%s za %s (kancelarija=%s): %s",
                action, from_status, to_status, clan_email, kancelarija_id, exc,
            )
            raise HTTPException(
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Greška pri upisu promene članstva. Pokušajte ponovo.",
            )

# -*- coding: utf-8 -*-
"""
Vindex AI — shared/tier_config.py

Runtime čitač tier_config tabele (migracija 068) — JEDINI put kojim bilo koji
deo aplikacije saznaje cenu i uključena mesta jedne tarife. Isti obrazac kao
shared/feature_registry.py, ali za tier_key (basic/professional/enterprise)
umesto feature_key.

In-memory keš sa dva mehanizma osvežavanja (identično feature_registry.py):
  1. Eksplicitna invalidacija — Admin Feature Console poziva invalidate()
     posle svake izmene, promena je vidljiva ODMAH.
  2. TTL bezbednosna mreža (60s).
"""
from __future__ import annotations

import asyncio
import logging
import time

from shared.deps import _get_supa

logger = logging.getLogger("vindex.tier_config")

_CACHE: dict[str, dict] = {}
_CACHE_LOADED_AT: float = 0.0
_CACHE_TTL_S = 60.0

# Fallback ako baza/migracija 068 nije dostupna — isti brojevi koji su bili
# hardkodovani pre ove migracije, NIKAD korišćeni ako je _CACHE popunjen makar
# jednom (samo štiti od potpunog pucanja pri prvom pozivu ako migracija kasni).
_FALLBACK = {
    "basic":        {"tier_key": "basic", "display_name": "Basic", "monthly_price_eur": 29, "included_seats": 1, "extra_seat_price_eur": None},
    "professional": {"tier_key": "professional", "display_name": "Professional", "monthly_price_eur": 79, "included_seats": 1, "extra_seat_price_eur": None},
    "enterprise":   {"tier_key": "enterprise", "display_name": "Enterprise", "monthly_price_eur": 249, "included_seats": 3, "extra_seat_price_eur": 49},
}


def _load_sync() -> dict[str, dict]:
    res = _get_supa().table("tier_config").select("*").execute()
    return {row["tier_key"]: row for row in (res.data or [])}


async def _ensure_loaded(force: bool = False) -> None:
    global _CACHE, _CACHE_LOADED_AT
    now = time.monotonic()
    if force or not _CACHE or (now - _CACHE_LOADED_AT) > _CACHE_TTL_S:
        try:
            fresh = await asyncio.to_thread(_load_sync)
            if fresh:
                _CACHE = fresh
                _CACHE_LOADED_AT = now
            elif not _CACHE:
                logger.error(
                    "[TIER_CONFIG] tier_config tabela je prazna ili nedostupna "
                    "(migracija 068 pokrenuta?) — koristim fallback vrednosti."
                )
        except Exception as exc:
            logger.warning(
                "[TIER_CONFIG] Osvežavanje keša neuspešno (%s) — koristim stari keš ako postoji.",
                type(exc).__name__,
            )
            if not _CACHE:
                raise


async def get_tier(tier_key: str) -> dict:
    """Vraća tier_config red za dati tier_key. Baca RuntimeError ako
    tier_key nije jedan od basic/professional/enterprise — namerno glasno."""
    if tier_key not in ("basic", "professional", "enterprise"):
        raise RuntimeError(f"tier_config: '{tier_key}' nije validna tarifa (basic/professional/enterprise).")
    await _ensure_loaded()
    return _CACHE.get(tier_key) or _FALLBACK[tier_key]


async def get_all_tiers() -> list[dict]:
    await _ensure_loaded()
    if not _CACHE:
        return sorted(_FALLBACK.values(), key=lambda t: t.get("sort_order", 0))
    return sorted(_CACHE.values(), key=lambda t: t.get("sort_order", 0))


def invalidate() -> None:
    """Poziva Admin Feature Console posle svake izmene — sledeći get_tier()
    poziv će forsirano osvežiti keš iz baze."""
    global _CACHE_LOADED_AT
    _CACHE_LOADED_AT = 0.0


async def force_reload() -> None:
    await _ensure_loaded(force=True)

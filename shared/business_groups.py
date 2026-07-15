# -*- coding: utf-8 -*-
"""
Vindex AI — shared/business_groups.py

Runtime čitač business_groups tabele (migracija 071) — JEDINI put kojim bilo
koji deo aplikacije saznaje poslovnu celinu (Pricing Modal Nivo 1 karticu)
kojoj funkcija pripada. Isti obrazac kao shared/tier_config.py, ali po
group_key umesto tier_key.

In-memory keš sa dva mehanizma osvežavanja (identično tier_config.py):
  1. Eksplicitna invalidacija — Admin Console poziva invalidate() posle
     svake izmene, promena je vidljiva ODMAH.
  2. TTL bezbednosna mreža (60s).
"""
from __future__ import annotations

import asyncio
import logging
import time

from shared.deps import _get_supa

logger = logging.getLogger("vindex.business_groups")

_CACHE: dict[str, dict] = {}
_CACHE_LOADED_AT: float = 0.0
_CACHE_TTL_S = 60.0


def _load_sync() -> dict[str, dict]:
    res = _get_supa().table("business_groups").select("*").execute()
    return {row["key"]: row for row in (res.data or [])}


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
                    "[BUSINESS_GROUPS] business_groups tabela je prazna ili nedostupna "
                    "(migracija 071 pokrenuta?)."
                )
        except Exception as exc:
            logger.warning(
                "[BUSINESS_GROUPS] Osvežavanje keša neuspešno (%s) — koristim stari keš ako postoji.",
                type(exc).__name__,
            )
            if not _CACHE:
                raise


async def get_group(group_key: str) -> dict:
    """Vraća business_groups red za dati key. Baca RuntimeError ako group_key
    nije poznat — namerno glasno, isti obrazac kao tier_config.get_tier()."""
    await _ensure_loaded()
    if group_key not in _CACHE:
        raise RuntimeError(f"business_groups: '{group_key}' ne postoji.")
    return _CACHE[group_key]


async def get_all_groups() -> list[dict]:
    await _ensure_loaded()
    return sorted(_CACHE.values(), key=lambda g: g.get("display_order", 0))


def invalidate() -> None:
    """Poziva Admin Console posle svake izmene — sledeći poziv će forsirano
    osvežiti keš iz baze."""
    global _CACHE_LOADED_AT
    _CACHE_LOADED_AT = 0.0


async def force_reload() -> None:
    await _ensure_loaded(force=True)

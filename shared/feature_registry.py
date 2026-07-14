# -*- coding: utf-8 -*-
"""
Vindex AI — shared/feature_registry.py

Runtime čitač feature_registry tabele (migracija 064) — JEDINI put kojim
PermissionService i UsageService saznaju politiku (tarifa, addon, krediti,
limiti) za neku funkciju. Ništa od ovoga nije hardkodirano u Python kodu.

In-memory keš sa dva mehanizma osvežavanja:
  1. Eksplicitna invalidacija — Admin Feature Console poziva invalidate()
     posle svake izmene, promena je vidljiva ODMAH, bez čekanja.
  2. TTL bezbednosna mreža (60s) — u slučaju da neko izmeni bazu mimo
     Admin Console-a (direktno u Supabase Dashboard-u), keš se ionako
     osveži u roku od minuta, ne ostaje trajno zastareo.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from shared.deps import _get_supa

logger = logging.getLogger("vindex.feature_registry")

_CACHE: dict[str, dict] = {}
_CACHE_LOADED_AT: float = 0.0
_CACHE_TTL_S = 60.0

_DEPS_CACHE: dict[str, list[str]] = {}
_DEPS_CACHE_LOADED_AT: float = 0.0


def _load_sync() -> dict[str, dict]:
    res = _get_supa().table("feature_registry").select("*").execute()
    return {row["feature_key"]: row for row in (res.data or [])}


def _load_deps_sync() -> dict[str, list[str]]:
    res = _get_supa().table("feature_dependencies").select("feature_key, depends_on").execute()
    out: dict[str, list[str]] = {}
    for row in (res.data or []):
        out.setdefault(row["feature_key"], []).append(row["depends_on"])
    return out


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
                    "[FEATURE_REGISTRY] feature_registry tabela je prazna ili nedostupna "
                    "(migracija 064 pokrenuta?) — keš ostaje prazan."
                )
        except Exception as exc:
            logger.warning(
                "[FEATURE_REGISTRY] Osvežavanje keša neuspešno (%s) — koristim stari keš ako postoji.",
                type(exc).__name__,
            )
            if not _CACHE:
                raise


async def _ensure_deps_loaded(force: bool = False) -> None:
    global _DEPS_CACHE, _DEPS_CACHE_LOADED_AT
    now = time.monotonic()
    if force or (now - _DEPS_CACHE_LOADED_AT) > _CACHE_TTL_S:
        try:
            _DEPS_CACHE = await asyncio.to_thread(_load_deps_sync)
            _DEPS_CACHE_LOADED_AT = now
        except Exception as exc:
            logger.debug(
                "[FEATURE_REGISTRY] Zavisnosti nisu učitane (migracija 065 pokrenuta?) — %s",
                type(exc).__name__,
            )


async def get_policy(feature_key: str) -> dict:
    """Vraća politiku za feature_key. Baca RuntimeError ako feature_key nije
    registrovan u bazi — namerno glasno, ne tiho (sprečava tihu propusnost)."""
    await _ensure_loaded()
    policy = _CACHE.get(feature_key)
    if policy is None:
        raise RuntimeError(
            f"Feature Registry: '{feature_key}' nema red u feature_registry tabeli. "
            f"Pokrenuta migracija 064? Ako je ovo nova funkcija, dodaj red preko "
            f"Admin Feature Console-a pre upotrebe."
        )
    return policy


async def get_all_policies() -> list[dict]:
    await _ensure_loaded()
    return list(_CACHE.values())


async def get_dependencies(feature_key: str) -> list[str]:
    """Vraća listu feature_key-eva od kojih feature_key zavisi (feature_dependencies
    tabela, migracija 065). Prazna lista ako nema zavisnosti ili tabela ne postoji."""
    await _ensure_deps_loaded()
    return _DEPS_CACHE.get(feature_key, [])


def invalidate() -> None:
    """Poziva Admin Feature Console posle svake izmene — sledeći get_policy()
    poziv će forsirano osvežiti keš iz baze."""
    global _CACHE_LOADED_AT, _DEPS_CACHE_LOADED_AT
    _CACHE_LOADED_AT = 0.0
    _DEPS_CACHE_LOADED_AT = 0.0


async def force_reload() -> None:
    await _ensure_loaded(force=True)
    await _ensure_deps_loaded(force=True)

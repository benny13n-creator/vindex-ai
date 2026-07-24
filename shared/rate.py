# -*- coding: utf-8 -*-
"""
Shared SlowAPI rate limiter — singleton importovan od api.py i svih router modula.

SEC-005 (2026-07-23) — Fail-Open Redis-backed rate limiting.

Istorijski kontekst (ne brisati ovaj razlog — sledeći inženjer mora znati
ZAŠTO je fail-open obavezan, ne samo da postoji): ranije u produkciji je
Upstash free-tier (256MB) kvota bila prekoračena, i `redis.ResponseError`
je izašao iz slowapi dekoratora PRE nego što je endpoint telo izvršeno,
zaobilazeći svaki try/except unutar same rute — obarajući SVE rate-limited
rute odjednom. Zbog toga je limiter posle toga bio UVEK in-memory, bez
ijednog pokušaja da se Redis vrati na bezbedan način.

Ovaj fajl to rešava koristeći ugrađene slowapi/limits mehanizme (NE custom
Storage wrapper — provereno čitanjem izvora: `Limiter._check_request_limit`
već hvata SVAKI izuzetak iz storage sloja u jednom `except Exception`):
  - `in_memory_fallback_enabled=True` + `in_memory_fallback=<isti limiti>`:
    na PRVU Redis grešku, slowapi interno prebacuje na in-memory limitere
    (po radniku — svaki gunicorn worker ima svoj), i periodično proverava
    da li se Redis oporavio (`storage.check()`) da se vrati na deljene
    Redis brojače.
  - `swallow_errors=True`: krajnja bezbednosna mreža — ako i in-memory
    fallback putanja iz nekog razloga baci grešku, zahtev se PROPUŠTA
    (logged kao warning), nikad ne postane HTTP 500 zbog rate limitera.

Bez REDIS_URL (lokalni dev, testovi) — Limiter ostaje čist in-memory,
identično prethodnom ponašanju, nema Redis zavisnosti da otkaže.
"""
import logging
import os
from typing import Callable

from slowapi import Limiter
from starlette.requests import Request

logger = logging.getLogger("vindex.rate")

# Isti default set koristi se i kao normalni limit i kao in-memory fallback
# limit — namerno identičan, tako da se ponašanje ne menja semantički tokom
# Redis ispada, samo koji storage stoji iza brojača.
_DEFAULT_LIMITS = ["60/hour"]

_REDIS_URL = os.getenv("REDIS_URL", "").strip()


def _get_real_ip(request: Request) -> str:
    """Čita pravi IP klijenta iza Render/Cloudflare proxy-ja.
    X-Forwarded-For: <client>, <proxy1>, <proxy2>
    Uzimamo samo prvu vrednost (leftmost = klijent).
    Fallback: request.client.host (direktna konekcija).
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def build_limiter(key_func: Callable[[Request], str], default_limits: list[str] | None = None) -> Limiter:
    """
    Fabrika koja gradi identično konfigurisan Limiter za api.py i za
    shared.rate — dve odvojene Limiter instance i dalje postoje u ovom kodu
    (api.py poziva `build_limiter(_get_real_ip)` da napravi svoju, umesto da
    uvozi `limiter` odavde direktno — arhitektonska duplikacija, poznata,
    van obima SEC-005; obe sad koriste isti `_get_real_ip` key_func i istu
    Redis+fail-open konfiguraciju, samo kroz dve odvojene instance).
    """
    limits = default_limits or _DEFAULT_LIMITS
    if _REDIS_URL:
        logger.info("[RATE] Redis-backed limiter (fail-open na in-memory ako Redis padne)")
        return Limiter(
            key_func=key_func,
            default_limits=limits,
            storage_uri=_REDIS_URL,
            # Kratak socket timeout — bez ovoga, otkrivanje da je Redis mrtav
            # koristi OS-nivo TCP timeout (može biti 10-30+ sekundi), što bi
            # svaki zahtev tokom ispada držalo da "visi" umesto brzog
            # fail-open-a. 1s je dovoljno velikodušno da ne pogodi normalnu
            # Upstash latenciju, a dovoljno kratko da ispad bude neprimetan.
            storage_options={"socket_connect_timeout": 1.0, "socket_timeout": 1.0},
            in_memory_fallback_enabled=True,
            in_memory_fallback=limits,
            swallow_errors=True,
        )
    logger.info("[RATE] In-memory limiter (REDIS_URL nije postavljen)")
    return Limiter(key_func=key_func, default_limits=limits)


limiter = build_limiter(_get_real_ip)

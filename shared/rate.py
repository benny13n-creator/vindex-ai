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
import time
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
    Fabrika koja gradi konfigurisan Limiter (Redis + fail-open ako REDIS_URL
    postoji, inače čist in-memory).

    Wave 10 (2026-08-11): ranije je api.py zvao ovu fabriku da napravi
    SOPSTVENU, drugu instancu pored `shared.rate.limiter`, pa su postojala
    dva odvojena skupa brojača. Ta duplikacija je uklonjena — api.py sada
    uvozi `limiter` odavde. Ova fabrika ostaje javna jer je i dalje jedini
    ispravan način da se napravi IZOLOVANA instanca (testovi fail-open
    ponašanja grade svoju po testu, umesto da diraju kanonsku).
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


# ═══════════════════════════════════════════════════════════════════════════
# KANONSKA INSTANCA — jedina u procesu.
#
# Svi ruteri rade `from shared.rate import limiter` i dekorišu rute sa
# `@limiter.limit(...)`, `api.py` je stavlja u `app.state.limiter` odakle je
# `SlowAPIMiddleware` koristi za podrazumevani limit. Jedan objekat, jedan
# storage, jedan lifecycle.
#
# NE PRAVITI drugu instancu ovog objekta na nivou modula i NE raditi
# `importlib.reload(shared.rate)` — reload ponovo izvrši ovaj red i napravi
# NOV objekat, dok dekoratori u ruterima i dalje drže staru referencu. Tada
# gašenje/reset preko `shared.rate.limiter` tiho promašuje instancu koju rute
# stvarno koriste. Ako treba izolovana instanca, koristi `build_limiter()`.
# ═══════════════════════════════════════════════════════════════════════════
limiter = build_limiter(_get_real_ip)


def reset_limiter_state(target: Limiter | None = None) -> None:
    """Vraća limiter na deterministički početno stanje — BRIŠE BROJAČE.

    Nije test-only hack: isti postupak treba i produkciji kada se limiter mora
    ručno rasteretiti (npr. posle incidenta u kome je pogrešan `key_func`
    nagomilao brojače pod jednim identitetom), i posle oporavka Redis-a kada
    in-memory fallback brojači treba da se odbace.

    Šta tačno briše (provereno nad instaliranim slowapi 0.1.9 / limits 5.8.0,
    ne pretpostavljeno):
      - `Limiter._storage` — glavni storage (`MemoryStorage` ili `RedisStorage`).
        `.reset()` na `MemoryStorage` prazni `storage/expirations/events/locks`;
        na Redis-u briše ključeve limitera. Gašenje `enabled` NIJE dovoljno —
        brojači bi ostali i limit bi se odmah ponovo aktivirao.
      - `Limiter._fallback_storage` — postoji SAMO kada je
        `in_memory_fallback_enabled=True`; poseban `MemoryStorage` sa svojim
        brojačima, koji `_storage.reset()` ne dodiruje.
      - `Limiter._storage_dead` + interni brojači provere backend-a
        (`_Limiter__check_backend_count`, `_Limiter__last_check_backend`) —
        bez ovoga bi instanca ostala „zaglavljena" u fallback režimu.
      - `Limiter.enabled` → `True` (podrazumevano iz `Limiter.__init__`).

    Namerno NE dira `_route_limits` / `_dynamic_route_limits` / `_default_limits`:
    to je KONFIGURACIJA (koja ruta ima koji limit), ne stanje. Njihovo brisanje
    bi razoružalo rate limiting umesto da ga resetuje.

    `target` je opcion — podrazumevano se resetuje kanonska instanca.
    """
    lim = limiter if target is None else target

    for storage in (getattr(lim, "_storage", None), getattr(lim, "_fallback_storage", None)):
        if storage is None:
            continue
        try:
            storage.reset()
        except Exception as e:  # noqa: BLE001 — reset nikad ne sme oboriti pozivaoca
            logger.warning("[RATE] reset storage-a %s nije uspeo: %s", type(storage).__name__, e)

    lim._storage_dead = False
    # name-mangled atributi iz Limiter.__init__ — pisani doslovno jer im je
    # to stvarno ime u `vars(limiter)`; getattr/setattr sa istim imenom.
    if hasattr(lim, "_Limiter__check_backend_count"):
        setattr(lim, "_Limiter__check_backend_count", 0)
    if hasattr(lim, "_Limiter__last_check_backend"):
        setattr(lim, "_Limiter__last_check_backend", time.time())
    lim.enabled = True

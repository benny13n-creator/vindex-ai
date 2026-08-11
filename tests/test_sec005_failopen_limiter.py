# -*- coding: utf-8 -*-
"""
SEC-005 — Fail-Open Redis rate limiter regression tests.

Kontekst (vidi shared/rate.py docstring i docs/security/P1_P2_FIX_VERIFICATION.md
SS0): ranije u produkciji, Upstash kvota-prekoračenje je uzrokovalo
redis.ResponseError koji je izlazio iz slowapi dekoratora PRE endpoint tela,
obarajući SVE rate-limited rute. Ovi testovi dokazuju da varijanta ugrađena
ovde (in_memory_fallback_enabled + swallow_errors, koristeći slowapi/limits
sopstveni mehanizam, ne custom wrapper) to više ne radi — ni za mrežne greške
(ConnectionError) ni za TAČAN originalni scenario (ResponseError, Redis
dostupan ali vraća grešku, ne mrežni pad).

VAŽNA, EMPIRIJSKI POTVRĐENA NIJANSA (ne pretpostavka): kada Redis storage
padne, slowapi NE zadržava pojedinačni ("30/minute" na ovoj ruti, "10/minute"
na onoj) limit po ruti — umesto toga, SVE rute privremeno dele JEDAN,
globalni `in_memory_fallback` limit dok se Redis ne oporavi. Ovo je
provereno direktnim čitanjem slowapi izvora (Limiter._check_request_limit)
i potvrđeno eksperimentalno pre pisanja ovih testova — testovi ispod
testiraju STVARNO ponašanje, ne ono što bi neko intuitivno očekivao.
"""
import asyncio
import os

import pytest
import redis
from limits.storage import RedisStorage
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")


def _make_request(client_ip: str, path: str = "/x") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [(b"x-forwarded-for", client_ip.encode())],
        "client": (client_ip, 12345),
        "query_string": b"",
    }
    return Request(scope)


def _redis_key(request: Request) -> str:
    return request.headers.get("x-forwarded-for")


def _build_redis_backed_limiter(redis_url: str, fallback_limits: list[str]) -> Limiter:
    """Isti obrazac kao shared.rate.build_limiter(), izolovano konstruisan
    po testu tako da testovi ne dele stanje preko istog Limiter singltona
    (svaki test treba svoj MemoryStorage/_storage_dead da bi bio nezavisan)."""
    return Limiter(
        key_func=_redis_key,
        default_limits=["60/hour"],
        storage_uri=redis_url,
        storage_options={"socket_connect_timeout": 0.3, "socket_timeout": 0.3},
        in_memory_fallback_enabled=True,
        in_memory_fallback=fallback_limits,
        swallow_errors=True,
    )


class TestFailOpenOnConnectionFailure:
    """Redis potpuno nedostupan (pogrešan port — garantovan ConnectionError)."""

    def test_requests_never_raise_uncaught_exception(self):
        limiter = _build_redis_backed_limiter("redis://localhost:1/0", ["5/minute"])

        @limiter.limit("2/minute")
        async def route(request: Request):
            return {"ok": True}

        for _ in range(4):
            try:
                result = asyncio.run(route(request=_make_request("203.0.113.50")))
                assert result == {"ok": True}
            except RateLimitExceeded:
                pass  # 429 je legitiman ishod, NE 500/uncaught
            except Exception as e:
                pytest.fail(
                    f"Rate limiter je propustio {type(e).__name__} umesto da padne "
                    f"na fallback ili swallow-uje grešku: {e}"
                )

    def test_fallback_limit_still_provides_real_protection(self):
        """Fail-open ne sme značiti 'bez ikakve zaštite' — dokazuje da je
        in_memory_fallback limit stvarno primenjen (blokira posle N poziva),
        ne samo 'sve prolazi'."""
        limiter = _build_redis_backed_limiter("redis://localhost:1/0", ["3/minute"])

        @limiter.limit("100/minute")  # rutin sopstveni limit — NE koristi se dok je storage mrtav
        async def route(request: Request):
            return {"ok": True}

        allowed = blocked = 0
        for _ in range(8):
            try:
                asyncio.run(route(request=_make_request("203.0.113.51")))
                allowed += 1
            except RateLimitExceeded:
                blocked += 1
        assert allowed == 3, f"Fallback limit je '3/minute' — očekivano tačno 3 dozvoljena, dobijeno {allowed}"
        assert blocked == 5


class TestFailOpenOnExactOriginalIncident:
    """Simulira TAČAN originalni incident: Redis dostupan (nema mrežne
    greške), ali vraća redis.ResponseError (npr. Upstash 'OOM command not
    allowed when used memory > maxmemory')."""

    def test_response_error_does_not_crash_requests(self, monkeypatch):
        def _boom(*a, **kw):
            raise redis.ResponseError(
                "OOM command not allowed when used memory > maxmemory-clients."
            )

        monkeypatch.setattr(RedisStorage, "incr", _boom)

        limiter = _build_redis_backed_limiter("redis://localhost:6399/0", ["2/minute"])

        @limiter.limit("30/minute")  # tipičan skup LLM ruti limit
        async def expensive_llm_route(request: Request):
            return {"ok": True}

        crashed = 0
        for _ in range(5):
            try:
                asyncio.run(expensive_llm_route(request=_make_request("203.0.113.60")))
            except RateLimitExceeded:
                pass
            except Exception:
                crashed += 1
        assert crashed == 0, (
            "redis.ResponseError (tačan originalni incident) je izazvao neuhvaćen "
            "izuzetak umesto fail-open ponašanja."
        )

    def test_response_error_still_enforces_fallback_limit(self, monkeypatch):
        def _boom(*a, **kw):
            raise redis.ResponseError("OOM command not allowed")

        monkeypatch.setattr(RedisStorage, "incr", _boom)

        limiter = _build_redis_backed_limiter("redis://localhost:6399/0", ["2/minute"])

        @limiter.limit("30/minute")
        async def route(request: Request):
            return {"ok": True}

        allowed = blocked = 0
        for _ in range(5):
            try:
                asyncio.run(route(request=_make_request("203.0.113.61")))
                allowed += 1
            except RateLimitExceeded:
                blocked += 1
        assert allowed == 2
        assert blocked == 3


class TestNoRedisUrlUnchangedBehavior:
    """Bez REDIS_URL (lokalni dev/test) — mora ostati čist in-memory limiter,
    identično ponašanje kao pre ovog fixa, bez ikakve Redis zavisnosti."""

    def test_plain_in_memory_limiter_when_no_redis_url(self):
        import shared.rate as rate_module

        # Ovaj proces test suite-a nikad ne postavlja REDIS_URL (conftest/
        # env fixture-i ga ne dodaju) — build_limiter() bez env var-e mora
        # vratiti čist in-memory Limiter, ne pokušati Redis konekciju.
        assert rate_module._REDIS_URL == "" or os.getenv("REDIS_URL") == rate_module._REDIS_URL
        fresh = rate_module.build_limiter(rate_module._get_real_ip)
        from limits.storage import MemoryStorage
        if not os.getenv("REDIS_URL"):
            assert isinstance(fresh._storage, MemoryStorage)


class TestApiIntegration:
    """Konfiguracija fabrike kojom app STVARNO gradi svoj limiter na startu —
    `shared.rate.build_limiter`, ista funkcija koju `shared/rate.py` poziva za
    kanonsku instancu koju uvoze i `api.py` i svi ruteri."""

    def test_build_limiter_with_broken_redis_url_is_failopen_configured(self, monkeypatch):
        """Sa nedostupnim REDIS_URL, `build_limiter()` mora vratiti Limiter
        koji je konfigurisan fail-open (in-memory fallback + swallow_errors) i
        ne sme baciti pri samoj konstrukciji — to je putanja kojom app startuje
        kada je Redis pogrešno konfigurisan ili mrtav.

        Wave 10 — RANIJA VERZIJA OVOG TESTA JE RADILA `importlib.reload(shared.rate)`
        i to je bio izvor curenja globalnog stanja: reload ponovo izvrši telo
        modula i red `limiter = build_limiter(...)` napravi NOV objekat, dok
        svaki ruter (`from shared.rate import limiter` pri svom uvozu) i dalje
        drži staru referencu na koju je `@limiter.limit(...)` trajno vezan.
        Posle ovog testa `shared.rate.limiter` je pokazivao na instancu koju
        nijedna ruta ne koristi, pa je svaki kasniji test koji preko njega gasi
        ili resetuje limiter tiho promašivao cilj — izmereno: 84 pada sa HTTP 429
        u punom suite-u, zeleno izolovano.

        Wave 9 je to zakrpio čuvanjem i vraćanjem objekta. Wave 10 uklanja uzrok:
        `_REDIS_URL` se čita iz modula pri konstrukciji, pa je dovoljno privremeno
        zameniti TU vrednost (monkeypatch vraća original automatski) — reload
        više nije potreban i modulski `limiter` objekat se ne dodiruje uopšte.
        Tvrdnje testa su nepromenjene.
        """
        import shared.rate as rate_module

        _kanonski = rate_module.limiter

        monkeypatch.setenv("REDIS_URL", "redis://localhost:1/0")
        monkeypatch.setattr(rate_module, "_REDIS_URL", "redis://localhost:1/0")

        limiter = rate_module.build_limiter(rate_module._get_real_ip)
        assert limiter._in_memory_fallback_enabled is True
        assert limiter._swallow_errors is True
        assert limiter is not _kanonski, "fabrika mora vratiti novu, izolovanu instancu"

        # Kanonska instanca je netaknuta — ni identitet ni storage.
        assert rate_module.limiter is _kanonski, (
            "test je zamenio kanonsku instancu limitera — tačno curenje koje je "
            "Wave 9 morao da krpi; nijedan test ne sme menjati shared.rate.limiter"
        )

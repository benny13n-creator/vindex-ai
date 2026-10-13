# -*- coding: utf-8 -*-
"""
OCR001-STATUS-RECOVERY — limit rute stanja Smart Intake posla tokom Redis ispada.

Produkcioni log: GET /api/smart-intake/jobs/{id} je dobijao 429 sa `60/hour`, iako ruta ima `@limiter.limit("60/minute")`.
Uzrok (slowapi 0.1.9, `Limiter._check_request_limit`): kad je Redis storage mrtav, NEPRAZNA lista `in_memory_fallback`
ZAMENJUJE limit svake rute. `shared/rate.py` je prosleđivao `in_memory_fallback=["60/hour"]`.

Svi testovi grade limiter PRAVOM fabrikom `shared.rate.build_limiter` (sa REDIS_URL) i pravom aplikacijom
(FastAPI + SlowAPIMiddleware), a limit rute stanja čitaju iz registra kanonskog limitera — ne prepisuju ga.

Negativna kontrola: `_stari_limiter` je tačna stara konfiguracija; isti testovi sa njom padaju (vidi `test_*_stara_*`).
"""
import os
import socket
import types

import pytest
import redis
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from limits.storage import RedisStorage
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")

import shared.rate as rate  # noqa: E402

MRTAV_REDIS = "redis://localhost:1/0"          # ConnectionError: niko ne sluša na portu 1
STATUS_RUTA = "routers.smart_intake.intake_job_status"
FINALIZE_RUTA = "routers.smart_intake.finalize_intake_jobs_batch"   # "5/minute"


def _limit_rute(ime: str) -> str:
    """Limit rute iz registra KANONSKOG limitera (dekorator u routers/smart_intake.py), kao tekst za `limiter.limit`."""
    import routers.smart_intake  # noqa: F401 — registruje dekoratore
    stavke = rate.limiter._route_limits.get(ime) or []
    assert len(stavke) == 1, f"{ime}: očekivan tačno jedan limit, registar ima {stavke!r}"
    it = stavke[0].limit
    return f"{it.amount} per {it.multiples} {it.GRANULARITY.name}"


def _novi_limiter(monkeypatch, url: str) -> Limiter:
    monkeypatch.setattr(rate, "_REDIS_URL", url)
    return rate.build_limiter(rate._get_real_ip)


def _stari_limiter(url: str) -> Limiter:
    """Tačna konfiguracija pre ispravke (samo negativna kontrola)."""
    return Limiter(key_func=rate._get_real_ip, default_limits=rate._DEFAULT_LIMITS, storage_uri=url,
                   storage_options={"socket_connect_timeout": 1.0, "socket_timeout": 1.0},
                   in_memory_fallback_enabled=True, in_memory_fallback=rate._DEFAULT_LIMITS, swallow_errors=True)


def _aplikacija(lim: Limiter, limit_stanja: str, limit_strog: str = "5 per 1 minute") -> TestClient:
    app = FastAPI()
    app.state.limiter = lim
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/jobs/{job_id}")
    @lim.limit(limit_stanja)
    async def stanje_posla(job_id: str, request: Request):
        return {"id": job_id}

    @app.post("/jobs/{job_id}/finalize")
    @lim.limit(limit_strog)
    async def strog(job_id: str, request: Request):
        return {"id": job_id}

    @app.get("/bez-dekoratora")          # podrazumevani limit (60/hour) preko SlowAPIMiddleware
    async def bez_dekoratora():
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=True)


class _Sat:
    def __init__(self):
        import time as _t
        self.t = _t.time()

    def time(self):
        return self.t


@pytest.fixture
def sat(monkeypatch):
    """Lažni sat za in-memory brojače (limits MemoryStorage čita samo `time.time()`)."""
    import limits.storage.memory as mem
    s = _Sat()
    monkeypatch.setattr(mem, "time", types.SimpleNamespace(time=s.time, sleep=lambda *_: None))
    return s


def _kodovi(k: TestClient, putanja: str, n: int, metod: str = "get") -> list[int]:
    return [getattr(k, metod)(putanja).status_code for _ in range(n)]


@pytest.fixture
def response_error(monkeypatch):
    """Redis „dostupan“, ali vraća grešku (originalni Upstash incident: OOM)."""
    def _boom(*a, **kw):
        raise redis.ResponseError("OOM command not allowed when used memory > maxmemory")
    monkeypatch.setattr(RedisStorage, "incr", _boom)
    monkeypatch.setattr(RedisStorage, "check", lambda self: False)


# ── Konfiguracija ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_ruta_stanja_ima_60_u_minuti():
    assert _limit_rute(STATUS_RUTA) == "60 per 1 minute"


def test_fabrika_ne_zamenjuje_limite_rute_tokom_ispada(monkeypatch):
    lim = _novi_limiter(monkeypatch, MRTAV_REDIS)
    assert lim._in_memory_fallback_enabled is True and lim._swallow_errors is True
    assert lim._in_memory_fallback == [], "neprazna lista zamenjuje limit svake rute dok je Redis mrtav"
    assert [str(g.limit) for grupa in lim._default_limits for g in grupa] == ["60 per 1 hour"]


# ── Redis mrtav: ConnectionError i ResponseError ───────────────────────────────────────────────────────────────────

def _ruta_stanja_je_60_u_minuti(k: TestClient, sat: _Sat) -> list[int]:
    prvi = _kodovi(k, "/jobs/j1", 61)
    sat.t += 61                                              # novi minut
    drugi = _kodovi(k, "/jobs/j1", 1)
    return prvi + drugi


@pytest.mark.parametrize("ispad", ["connection_error", "response_error"])
def test_redis_ispad_ruta_stanja_zadrzava_60_u_minuti(monkeypatch, sat, request, ispad):
    if ispad == "response_error":
        request.getfixturevalue("response_error")
    lim = _novi_limiter(monkeypatch, MRTAV_REDIS if ispad == "connection_error" else "redis://localhost:6399/0")
    k = _aplikacija(lim, _limit_rute(STATUS_RUTA))
    kodovi = _ruta_stanja_je_60_u_minuti(k, sat)
    assert lim._storage_dead is True, "test mora stvarno ići kroz in-memory fallback putanju"
    assert kodovi[:60] == [200] * 60 and kodovi[60] == 429, "60 u minuti, 61. zahtev odbijen"
    assert kodovi[61] == 200, "posle minuta ruta stanja ponovo prolazi (stara konfiguracija: 60/hour → 429)"
    assert 500 not in kodovi


@pytest.mark.parametrize("ispad", ["connection_error", "response_error"])
def test_redis_ispad_podrazumevani_limit_i_dalje_stiti(monkeypatch, sat, request, ispad):
    if ispad == "response_error":
        request.getfixturevalue("response_error")
    lim = _novi_limiter(monkeypatch, MRTAV_REDIS if ispad == "connection_error" else "redis://localhost:6399/0")
    k = _aplikacija(lim, _limit_rute(STATUS_RUTA))
    prvi = _kodovi(k, "/bez-dekoratora", 61)
    sat.t += 61
    posle_minuta = _kodovi(k, "/bez-dekoratora", 1)
    sat.t += 3600
    posle_sata = _kodovi(k, "/bez-dekoratora", 1)
    assert lim._storage_dead is True
    assert prvi[:60] == [200] * 60 and prvi[60] == 429, "podrazumevani 60/hour važi i bez Redis-a"
    assert posle_minuta == [429], "podrazumevani prozor je sat, ne minut"
    assert posle_sata == [200]


def test_redis_ispad_strog_limit_rute_nije_olabavljen(monkeypatch, sat):
    lim = _novi_limiter(monkeypatch, MRTAV_REDIS)
    k = _aplikacija(lim, _limit_rute(STATUS_RUTA), _limit_rute(FINALIZE_RUTA))
    kodovi = _kodovi(k, "/jobs/j1/finalize", 7, "post")
    assert kodovi == [200] * 5 + [429] * 2, f"finalize ima {_limit_rute(FINALIZE_RUTA)}; dobijeno {kodovi}"


def test_redis_ping_radi_a_incr_pada_bez_500_i_bez_gubitka_limita(monkeypatch, sat):
    """Upstash OOM: `PING` prolazi (provera oporavka kaže „Redis je živ“), a `INCR` vraća grešku. Limiter tada pri
    svakoj proveri skače Redis → greška → in-memory. Zahtev nikad ne postaje 500 i limit rute stanja ostaje 60/minute."""
    def _boom(*a, **kw):
        raise redis.ResponseError("OOM command not allowed when used memory > maxmemory")
    monkeypatch.setattr(RedisStorage, "incr", _boom)
    monkeypatch.setattr(RedisStorage, "check", lambda self: True)
    lim = _novi_limiter(monkeypatch, "redis://localhost:6399/0")
    k = _aplikacija(lim, _limit_rute(STATUS_RUTA))
    kodovi, prelazi = [], 0
    for _ in range(61):
        setattr(lim, "_Limiter__last_check_backend", 0)      # svaka provera oporavka je dospela
        setattr(lim, "_Limiter__check_backend_count", 0)
        kodovi += _kodovi(k, "/jobs/j1", 1)
        prelazi += lim._storage_dead is True
    sat.t += 61                                              # novi minut: 60/minute propušta, stari 60/hour ne bi
    setattr(lim, "_Limiter__last_check_backend", 0)
    setattr(lim, "_Limiter__check_backend_count", 0)
    kodovi += _kodovi(k, "/jobs/j1", 1)
    assert prelazi == 61, "svaki zahtev je prošao kroz pokušaj Redis-a i povratak na in-memory"
    assert 500 not in kodovi
    assert kodovi[:60] == [200] * 60 and kodovi[60] == 429 and kodovi[61] == 200


# ── Jedan i pet istovremenih poslova (isti korisnik = ista IP adresa) ───────────────────────────────────────────────

@pytest.mark.parametrize("poslova", [1, 5])
@pytest.mark.parametrize("razmak_s", [10])
def test_redis_ispad_pracenje_poslova_bez_429(monkeypatch, sat, poslova, razmak_s):
    """Frontend prati svaki posao na 10 s, najduže 5 minuta. Limiter broji po IP adresi i putanji (`key_style="url"`),
    pa svaki posao ima svoj brojač: 30 čitanja po poslu za 5 minuta, daleko ispod 60/minute — i za jedan i za pet.
    Test čuva ponašanje (prolazi i sa starom konfiguracijom); razliku hvataju testovi sa pomerenim satom."""
    lim = _novi_limiter(monkeypatch, MRTAV_REDIS)
    k = _aplikacija(lim, _limit_rute(STATUS_RUTA))
    kodovi = []
    for _ in range(300 // razmak_s):
        for j in range(poslova):
            kodovi += _kodovi(k, f"/jobs/j{j}", 1)
        sat.t += razmak_s
    assert lim._storage_dead is True
    assert kodovi.count(429) == 0 and len(kodovi) == poslova * 30


# ── Negativne kontrole: stara konfiguracija pada na istim proverama ──────────────────────────────────────────────────

def test_stara_konfiguracija_ruta_stanja_dobija_60_na_sat(sat):
    k = _aplikacija(_stari_limiter(MRTAV_REDIS), _limit_rute(STATUS_RUTA))
    kodovi = _ruta_stanja_je_60_u_minuti(k, sat)
    assert kodovi[61] == 429, "kontrola: stara konfiguracija primenjuje 60/hour na rutu stanja (produkcioni simptom)"


def test_stara_konfiguracija_olabavljuje_strog_limit(sat):
    k = _aplikacija(_stari_limiter(MRTAV_REDIS), _limit_rute(STATUS_RUTA), _limit_rute(FINALIZE_RUTA))
    assert _kodovi(k, "/jobs/j1/finalize", 7, "post") == [200] * 7, "kontrola: stara konfiguracija daje finalize-u 60/hour"


def test_stara_konfiguracija_tri_sekunde_daje_429(sat):
    """Produkcioni simptom: praćenje na 3 s (staro) posle 60 zahteva = 3 minuta dobija 429."""
    k = _aplikacija(_stari_limiter(MRTAV_REDIS), _limit_rute(STATUS_RUTA))
    kodovi = []
    for _ in range(100):
        kodovi += _kodovi(k, "/jobs/j1", 1)
        sat.t += 3
    assert kodovi.index(429) == 60


# ── Zdrav Redis (pravi server; preskače se ako nije dostupan) ──────────────────────────────────────────────────────

def _zdrav_redis_url() -> str | None:
    url = os.getenv("VINDEX_TEST_REDIS_URL", "").strip()
    if not url:
        return None
    try:
        redis.Redis.from_url(url, socket_connect_timeout=0.5).ping()
    except Exception:
        return None
    return url


@pytest.mark.skipif(_zdrav_redis_url() is None, reason="VINDEX_TEST_REDIS_URL nije postavljen ili Redis nije dostupan")
def test_zdrav_redis_ruta_stanja_60_u_minuti_bez_fallback_a(monkeypatch):
    url = _zdrav_redis_url()
    redis.Redis.from_url(url).flushdb()
    lim = _novi_limiter(monkeypatch, url)
    k = _aplikacija(lim, _limit_rute(STATUS_RUTA))
    kodovi = _kodovi(k, "/jobs/j1", 61)
    assert lim._storage_dead is False, "zdrav Redis ne sme preći na in-memory"
    assert kodovi[:60] == [200] * 60 and kodovi[60] == 429
    r = redis.Redis.from_url(url)
    kljucevi = [kl for kl in r.keys("*") if b"/jobs/j1/60/1/minute" in kl]
    assert kljucevi, "brojač rute stanja mora biti u Redis-u"
    assert all(0 < r.ttl(kl) <= 60 for kl in kljucevi), "prozor rute stanja je minut"
    podr = _kodovi(k, "/bez-dekoratora", 61)
    assert podr[:60] == [200] * 60 and podr[60] == 429
    assert all(3540 < r.ttl(kl) <= 3600 for kl in r.keys("*") if b"/bez-dekoratora/60/1/hour" in kl)
    assert lim._storage_dead is False
    r.flushdb()

# -*- coding: utf-8 -*-
"""
Production Readiness Report (2026-07-25), stavka #1 -- /api/cron/daily
fail-open fix.

Pre ove izmene, api.py:1518-1521 je glasio:
    if cron_secret and x_secret != cron_secret:
        raise HTTPException(status_code=403, ...)
Kad BRIEFING_CRON_SECRET NIJE podešen, `cron_secret` je prazan string i
`if cron_secret and ...` se skraćuje na False -- provera se PRESKAČE
u potpunosti, a /api/cron/daily (retention cleanup, background agenti,
svi dnevni moduli) postaje pozivan bez ikakve autentifikacije od bilo koga
ko zna URL.

Ispravka: fail CLOSED -- `if not cron_secret or x_secret != cron_secret`
-- odsustvo env varijable sada znači "endpoint je zaključan", ne "endpoint
je otvoren za sve". Ovaj fajl testira TAČNO to ponašanje, nezavisno od
tests/test_cron_daily_dispatcher.py (koji testira dispečer/modul logiku uz
VALIDAN cron secret, ne auth granične slučajeve).
"""
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")
os.environ.setdefault("FOUNDER_EMAILS", "founder@example.com")


class _FakeResult:
    def __init__(self, data=None):
        self.data = data


class _FakeQuery:
    """Lenient no-op fake -- isti obrazac kao test_cron_daily_dispatcher.py.
    Cilj ovog fajla je auth granica, ne dispečer/modul logika, pa namerno
    NE mock-ujemo svaki submodul pojedinačno: dispečerova sopstvena
    per-modul try/except izolacija (dokumentovana u cron_daily's docstring-u)
    je dovoljna da pozitivna kontrola ispod dobije 200 bez posebnog mockovanja."""

    def __init__(self, table_name):
        self._table = table_name

    def select(self, *a, **kw): return self
    def eq(self, *a, **kw): return self
    def lt(self, *a, **kw): return self
    def order(self, *a, **kw): return self
    def limit(self, *a, **kw): return self
    def maybe_single(self): return self
    def insert(self, data): return self
    def upsert(self, data): return self
    def delete(self): return self
    def not_(self): return self
    def is_(self, *a, **kw): return self
    def in_(self, *a, **kw): return self

    def execute(self):
        return _FakeResult(data=None)


class _FakeSupa:
    def table(self, name):
        return _FakeQuery(name)


def _client():
    from fastapi.testclient import TestClient
    from api import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def _patch_supa():
    with patch("api._get_supa", return_value=_FakeSupa()):
        yield


@pytest.fixture(autouse=True)
def _patch_pinecone_tmp_cleanup():
    """The one test below that gets PAST auth runs the whole cron_daily
    dispatcher, and its retention module calls
    uploaded_doc.cleanup.cleanup_expired() -- which opens a real Pinecone
    client, lists namespaces and DELETES the expired tmp_* ones. PINECONE_HOST
    is only setdefault'ed above, so on any machine with the real host in its
    environment (a developer laptop, or CI with the deployment secrets) this
    auth test was issuing destructive writes against the production index.

    Stubbed with the summary dict the real function returns on a clean run.
    _cleanup_pinecone_tmp_buffers only reads counters off it, and this file
    asserts on the HTTP status code, so the auth boundary under test is
    untouched.
    """
    _clean_run = {"namespaces_deleted": 0, "chunks_deleted": 0, "namespaces_inspected": 0}
    with patch("uploaded_doc.cleanup.cleanup_expired", return_value=_clean_run):
        yield


@pytest.fixture(autouse=True)
def _patch_zakon_monitoring_scan():
    """VCR001: ponedeljkom (UTC) dispečer pokreće `routers.zakon_monitoring._skeniraj_sl_glasnik`, koji dohvata
    stvarni RSS Službenog glasnika (pravno-informacioni-sistem.rs). Test koji prođe auth je tada svakog ponedeljka
    izlazio na mrežu (i rušio NS005 `test_nema_spoljne_mreze` zavisno od redosleda). Ovaj fajl meri samo HTTP status."""
    from unittest.mock import AsyncMock
    with patch("routers.zakon_monitoring._skeniraj_sl_glasnik", new=AsyncMock(return_value={"skenirano": 0, "novih": 0})):
        yield


@pytest.fixture(autouse=True)
def _patch_dispatcher_io():
    """NS3-N01: pozitivna kontrola prolazi auth i izvršava CEO dispečer. Bez ovih zamena devet modula je stvarno
    radilo — među njima i `posalji_podsetnike` (email podsetnici), zadrška/brisanje, pozadinski agenti i `reap_*`
    — i pokušavalo 11 mrežnih poziva ka `SUPABASE_URL` (izmereno NS3 zabranom mreže). Ovaj fajl meri samo auth
    granicu (HTTP status); modularna logika ima svoje testove. Oblik povratnih vrednosti = stvarni ugovor."""
    from contextlib import ExitStack
    from unittest.mock import AsyncMock
    zamene = {
        "routers.workflow._check_escalations": {"proverenih": 0, "eskaliranih": 0},
        "routers.portal_monitoring.cron_proveri": {"provereno": 0, "promena": 0},
        "routers.email_notif.posalji_podsetnike": {"poslato": 0, "greske": 0, "preskoceno": 0, "neisporuceno": 0},
        "routers.email_notif.onboarding_cron": {"poslato": 0, "greske": 0},
        "routers.email_notif.posalji_nedeljni_sazetak": {"poslato": 0, "greske": 0},
        "services.retention_service.execute_retention_cleanup": {"_summary": {"ukupno_obrisano": 0, "greske": 0}},
        "services.event_bus.reap_missing_pipeline_events": {"checked": 0, "backfilled": 0},
        "services.event_bus.reap_missing_rociste_events": {"checked": 0, "backfilled": 0},
        "routers.billing.reap_orphan_fakture": {"checked": 0, "reaped": 0},
        "workers.background_agents.run_background_agents": {"korisnika_obradjeno": 0, "greske": 0},
    }
    with ExitStack() as stek:
        for meta, rez in zamene.items():
            stek.enter_context(patch(meta, new=AsyncMock(return_value=rez)))
        yield


class TestCronDailyFailsClosed:
    def test_missing_secret_env_and_missing_header_returns_401(self, monkeypatch):
        """Glavni regresioni test za nalaz iz izveštaja: BRIEFING_CRON_SECRET
        NIJE podešen, header NIJE poslat -- endpoint MORA odbiti, ne
        proslediti zahtev dalje."""
        monkeypatch.delenv("BRIEFING_CRON_SECRET", raising=False)
        r = _client().post("/api/cron/daily")
        assert r.status_code == 401
        assert r.json()["detail"] == "Neovlašćen pristup."

    def test_missing_secret_env_even_with_a_header_returns_401(self, monkeypatch):
        """Čak i ako neko POGODI/pošalje BILO KOJI header, prazan
        server-side secret ne sme nikad da se "poklopi" sa bilo čim."""
        monkeypatch.delenv("BRIEFING_CRON_SECRET", raising=False)
        r = _client().post("/api/cron/daily", headers={"X-Cron-Secret": ""})
        assert r.status_code == 401

    def test_secret_configured_but_header_missing_returns_401(self, monkeypatch):
        monkeypatch.setenv("BRIEFING_CRON_SECRET", "real-secret-value")
        r = _client().post("/api/cron/daily")
        assert r.status_code == 401

    def test_secret_configured_but_header_wrong_returns_401(self, monkeypatch):
        monkeypatch.setenv("BRIEFING_CRON_SECRET", "real-secret-value")
        r = _client().post("/api/cron/daily", headers={"X-Cron-Secret": "wrong-guess"})
        assert r.status_code == 401

    def test_secret_configured_and_header_matches_passes_auth(self, monkeypatch):
        """Pozitivna kontrola -- dokazuje da fail-closed izmena ne blokira
        LEGITIMAN cron poziv, samo neautentifikovane. Ako bi auth provera
        slučajno postala fail-closed-za-sve (npr. neko kasnije doda dodatan
        uslov koji uvek baca 401), ovaj test bi pao."""
        monkeypatch.setenv("BRIEFING_CRON_SECRET", "real-secret-value")
        r = _client().post("/api/cron/daily", headers={"X-Cron-Secret": "real-secret-value"})
        assert r.status_code == 200

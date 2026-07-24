# -*- coding: utf-8 -*-
"""
SEC-002 — /api/cron/daily routing-collision fix + module wiring tests.

Context: routers/email_notif.py used to define its OWN /api/cron/daily
(email reminders only), registered via app.include_router() BEFORE api.py's
own @app.post("/api/cron/daily") (the richer "unified" dispatcher --
idempotency guard, heartbeat, workflow escalations, weekly zakon_monitoring,
memory cleanup). Starlette dispatches to the FIRST matching route, so
api.py's dispatcher had never actually executed since it was written --
confirmed by directly inspecting app.routes before the fix (2 matches,
routers.email_notif first).

The duplicate route in email_notif.py was removed; its 3 underlying
functions (posalji_podsetnike, onboarding_cron, posalji_nedeljni_sazetak)
are now called directly from api.py's dispatcher as new modules, alongside
the new SEC-002 retention_cleanup module.
"""
import os
from unittest.mock import AsyncMock, patch

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
    """Lenient fake covering every Supabase query-builder call cron_daily
    makes (select/eq/maybe_single/insert/upsert/delete/lt) -- returns empty/
    no-op results so the dispatcher's own bookkeeping (idempotency check,
    heartbeat, cron_runs) doesn't crash, independent of the module logic
    under test."""

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

    def execute(self):
        return _FakeResult(data=None)


class _FakeSupa:
    def table(self, name):
        return _FakeQuery(name)


@pytest.fixture(autouse=True)
def _patch_supa():
    # api.py defines its OWN _get_supa() (separate from shared.deps._get_supa,
    # a pre-existing architectural duplication, not something this test
    # fixes) -- must patch where it's USED (api.py), not where a
    # similarly-named function happens to live elsewhere.
    with patch("api._get_supa", return_value=_FakeSupa()):
        yield


@pytest.fixture(autouse=True)
def _patch_submodules():
    """Isolates the dispatcher-wiring test from each module's own internal
    complexity -- we're testing that cron_daily calls these and assembles
    the result correctly, not re-testing each module's own logic (already
    covered by their own test files)."""
    with patch("routers.workflow._check_escalations", new=AsyncMock(return_value={"proverenih": 5, "eskaliranih": 1})), \
         patch("routers.portal_monitoring.cron_proveri", new=AsyncMock(return_value={"provereno": 3, "promena": 0})), \
         patch("routers.email_notif.posalji_podsetnike", new=AsyncMock(return_value={"poslato": 4, "greske": 0})), \
         patch("routers.email_notif.onboarding_cron", new=AsyncMock(return_value={"poslato": 2, "greske": 0})), \
         patch("routers.email_notif.posalji_nedeljni_sazetak", new=AsyncMock(return_value={"poslato": 7, "greske": 0})), \
         patch(
             "services.retention_service.execute_retention_cleanup",
             new=AsyncMock(return_value={
                 "security_events": {"status": "ok", "obrisano": 12},
                 "user_daily_activity": {"status": "ok", "obrisano": 3},
                 "ai_forensics": {"status": "ok", "obrisano": 0},
                 "pinecone_tmp_buffers": {"status": "ok", "namespaces_deleted": 2, "chunks_deleted": 8, "namespaces_inspected": 5},
                 "_summary": {"ukupno_obrisano": 17, "tabele_van_dometa": ["usage_events", "response_audit"], "greske": 0},
             }),
         ):
        yield


def _client():
    from fastapi.testclient import TestClient
    from api import app
    return TestClient(app)


class TestRoutingCollisionFixed:
    def test_exactly_one_handler_registered(self):
        from api import app
        matches = [r for r in app.routes if getattr(r, "path", None) == "/api/cron/daily"]
        assert len(matches) == 1, f"Expected exactly 1 route, found {len(matches)}: {[(r.endpoint.__module__, r.endpoint.__name__) for r in matches]}"

    def test_the_one_handler_is_apis_own_dispatcher(self):
        from api import app
        matches = [r for r in app.routes if getattr(r, "path", None) == "/api/cron/daily"]
        assert matches[0].endpoint.__module__ == "api"
        assert matches[0].endpoint.__name__ == "cron_daily"

    def test_email_notif_no_longer_defines_the_route(self):
        import routers.email_notif as en
        assert not hasattr(en, "cron_daily"), (
            "routers/email_notif.py still defines cron_daily -- the duplicate "
            "route removal was supposed to delete this function entirely"
        )


class TestCronDailyCallsAllModules:
    """NAPOMENA o danu u nedelji: cron_daily čita `datetime.now()` preko
    LOKALNOG `from datetime import datetime as _dt` unutar same funkcije
    (ne postoji kao `api._dt` modul-level atribut), pa se ne može čisto
    mock-ovati bez rizika da se pokvari ostatak funkcije (koja koristi isti
    import i za run_id timestamps). Testovi ispod su namerno neutralni na
    dan u nedelji -- `nedeljni_sazetak` je ili "ok" ili "preskoceno" u
    zavisnosti od stvarnog datuma kad se testovi pokrenu, oba su ispravna
    stanja i oba se eksplicitno dozvoljavaju."""

    def test_response_includes_all_new_modules(self):
        client = _client()
        r = client.post("/api/cron/daily")
        assert r.status_code == 200
        body = r.json()
        assert body["email_podsetnici"]["poslato"] == 4
        assert body["email_podsetnici"]["status"] == "ok"
        assert body["onboarding"]["poslato"] == 2
        assert body["retention_cleanup"]["status"] == "ok"
        assert body["retention_cleanup"]["obrisano"] == 17

    def test_nedeljni_sazetak_is_ok_or_skipped_never_crashes(self):
        client = _client()
        r = client.post("/api/cron/daily")
        body = r.json()
        assert body["nedeljni_sazetak"]["status"] in ("ok", "preskoceno")
        if body["nedeljni_sazetak"]["status"] == "ok":
            assert body["nedeljni_sazetak"]["poslato"] == 7

    def test_retention_module_failure_does_not_block_heartbeat(self):
        """The core isolation guarantee: if the new retention module blows
        up, every other module (including the final heartbeat/cron_runs
        bookkeeping) must still complete."""
        client = _client()
        with patch("services.retention_service.execute_retention_cleanup",
                   new=AsyncMock(side_effect=RuntimeError("boom"))):
            r = client.post("/api/cron/daily")
        assert r.status_code == 200
        body = r.json()
        assert body["retention_cleanup"]["status"] == "greska"
        assert "boom" in body["retention_cleanup"]["greska"]
        # Everything else still ran despite the retention failure:
        assert body["email_podsetnici"]["status"] == "ok"
        assert body["heartbeat"]["status"] == "ok"
        assert body["run_id"]

    def test_email_reminder_failure_does_not_block_retention(self):
        """Same isolation guarantee, opposite direction."""
        client = _client()
        with patch("routers.email_notif.posalji_podsetnike",
                   new=AsyncMock(side_effect=RuntimeError("smtp down"))):
            r = client.post("/api/cron/daily")
        assert r.status_code == 200
        body = r.json()
        assert body["email_podsetnici"]["status"] == "greska"
        assert body["retention_cleanup"]["status"] == "ok"
        assert body["retention_cleanup"]["obrisano"] == 17


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

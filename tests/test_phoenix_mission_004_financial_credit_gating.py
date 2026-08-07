# -*- coding: utf-8 -*-
"""
Program Phoenix, Mission 004 -- Financial Credit-Gating Consolidation.
Closes LIVINGSYS-DEBT-006, -002, -027.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    from starlette.requests import Request as StarletteRequest
    scope = {"type": "http", "method": "POST", "path": "/", "headers": [],
              "query_string": b"", "app": MagicMock(), "state": MagicMock(),
              "client": ("127.0.0.1", 1234)}
    return StarletteRequest(scope=scope)


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-006 — Case Commander /jutarnji had the exact unprotected
# double-charge race CIO /daily was fixed for in Part A.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_commander_jutarnji_concurrent_calls_charge_only_once():
    import routers.case_commander as cc

    rows = {}

    class _Builder:
        def __init__(self, kind, payload=None):
            self.kind = kind
            self.payload = payload
            self.filters = {}
        def eq(self, col, val):
            self.filters[col] = val
            return self
        def select(self, *a, **k):
            return self
        def limit(self, *a, **k):
            return self
        def execute(self):
            res = MagicMock()
            if self.kind == "select":
                key = (self.filters.get("user_id"), self.filters.get("datum"))
                res.data = [rows[key]] if key in rows else []
                return res
            if self.kind == "insert":
                key = (self.payload["user_id"], self.payload["datum"])
                if key in rows:
                    raise Exception('duplicate key value violates unique constraint "commander_jutarnji_user_id_datum_key"')
                rows[key] = dict(self.payload)
                res.data = [rows[key]]
                return res
            if self.kind == "update":
                key = (self.filters.get("user_id"), self.filters.get("datum"))
                if key in rows:
                    rows[key].update(self.payload)
                    res.data = [rows[key]]
                else:
                    res.data = []
                return res
            res.data = None
            return res

    def _table(name):
        assert name in ("commander_jutarnji", "profiles")
        t = MagicMock()
        if name == "profiles":
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"email": "a@b.com"}
            return t
        t.select.side_effect = lambda *a, **k: _Builder("select")
        t.insert.side_effect = lambda payload: _Builder("insert", payload)
        t.update.side_effect = lambda payload: _Builder("update", payload)
        return t

    supa = MagicMock()
    supa.table.side_effect = _table
    user = {"user_id": "u1", "email": "a@b.com"}

    with patch.object(cc, "_get_supa", return_value=supa), \
         patch.object(cc, "_dohvati_sve_predmete_za_analizu", new=AsyncMock(return_value={"predmeti": [{"id": "p1"}]})), \
         patch.object(cc, "_cross_case_analiza", new=AsyncMock(return_value={"nalazi": [], "hitni_rokovi": []})), \
         patch.object(cc, "UsageService") as mock_usage:
        mock_usage.consume = AsyncMock(return_value=100)
        await cc.commander_jutarnji(user)
        await cc.commander_jutarnji(user)

    assert mock_usage.consume.await_count == 1


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-002 — /api/nacrt charged a credit even when draft generation
# completely failed.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_nacrt_does_not_charge_on_generation_failure():
    import routers.drafting as dr

    class Req:
        vrsta = "tuzba"
        opis = "Dovoljno dugačak opis za validaciju zahteva."
        predmet_id = None

    with patch.object(dr, "_drafting_generate", return_value={"status": "error", "message": "AI greška"}), \
         patch.object(dr, "UsageService") as mock_usage, \
         patch.object(dr, "_audit", new=AsyncMock()):
        mock_usage.consume = AsyncMock(return_value=100)
        mock_usage.balance = AsyncMock(return_value=100)
        result = await dr.nacrt(Req(), _req(), {"user_id": "u1", "email": "a@b.com"})

    mock_usage.consume.assert_not_awaited()
    mock_usage.balance.assert_awaited_once()
    assert "credits_remaining" in result


@pytest.mark.anyio
async def test_nacrt_charges_on_genuine_success():
    import routers.drafting as dr

    class Req:
        vrsta = "tuzba"
        opis = "Dovoljno dugačak opis za validaciju zahteva."
        predmet_id = None

    with patch.object(dr, "_drafting_generate", return_value={"status": "success", "data": "Nacrt teksta ovde."}), \
         patch.object(dr, "UsageService") as mock_usage, \
         patch.object(dr, "_audit", new=AsyncMock()):
        mock_usage.consume = AsyncMock(return_value=99)
        mock_usage.balance = AsyncMock(return_value=100)
        result = await dr.nacrt(Req(), _req(), {"user_id": "u1", "email": "a@b.com"})

    mock_usage.consume.assert_awaited_once()
    mock_usage.balance.assert_not_awaited()
    assert result["odgovor"] == "Nacrt teksta ovde."


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-027 — /api/podnesak always charged even when entity
# extraction (the step that matters most) silently degraded to empty.
# ═══════════════════════════════════════════════════════════════════════════

def test_podnesak_skips_charge_only_when_entiteti_empty():
    src = open(os.path.join(REPO_ROOT, "routers", "drafting.py"), encoding="utf-8").read()
    marker = "nacrt = await _critique_and_refine_draft(nacrt, kontekst, req.tip, log_id)"
    block = src.split(marker, 1)[1][:1200]
    assert "if entiteti:" in block
    assert 'await UsageService.consume(user["user_id"]' in block

# -*- coding: utf-8 -*-
"""
Program Lambda, Certification 003 (2026-08-06) -- Horizontal Privilege
Escalation fork found a systemic pattern, independently re-verified and
upheld by the Adversarial Certification fork: 3 files fetched a case's
sibling data (document text, notes, timeline) via asyncio.gather()
CONCURRENTLY with the ownership-scoped `predmeti` query, instead of after
it. Every caller already discarded the sibling data on a 404/not-found, so
this was NOT an active leak -- but a foreign tenant's document text/notes
transited process memory on every guessed predmet_id, and the pattern was
"one bad refactor away from an actual leak."

Fix: hoist the ownership query out of the gather in all 3 files
(routers/case_commander.py::_dohvati_predmet_kontekst,
routers/digital_twin.py::_dohvati_kontekst_predmeta,
routers/copilot.py::_handle_analiza_predmeta/_handle_plan_predmeta) so the
sibling queries structurally cannot fire for an unowned predmet_id.

These tests prove the sibling queries are never invoked when ownership
fails, and that the legitimate-owner path is unaffected.
"""
import sys
import os
import asyncio
from unittest.mock import MagicMock, patch

os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _tracking_supa(owned: bool):
    """A Supabase mock where `predmeti` reports unowned/owned, and every
    OTHER table records that it was called -- used to prove sibling
    queries never fire when ownership fails."""
    called = {"siblings": []}

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            if owned:
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
                    {"id": "p1", "naziv": "Test", "tip": "parnica", "status": "aktivan",
                     "rizik": "srednji", "opis": "", "created_at": "2026-01-01", "case_dna": None}
                ]
                t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                    "id": "p1", "naziv": "Test", "tip": "parnica", "status": "aktivan",
                    "rizik": "srednji", "opis": "", "created_at": "2026-01-01", "case_dna": None,
                }
                sr = MagicMock()
                sr.data = {"naziv": "Test", "opis": "", "tip": "parnica", "status": "aktivan", "case_dna": None}
                t.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = sr
            else:
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
                t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
                t.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.side_effect = Exception("PGRST116: 0 rows")
        else:
            called["siblings"].append(name)
            t.select.return_value.eq.return_value.execute.return_value.data = []
            t.select.return_value.eq.return_value.order.return_value.execute.return_value.data = []
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        return t

    supa = MagicMock()
    supa.table.side_effect = _table
    return supa, called


# ─── case_commander.py::_dohvati_predmet_kontekst ─────────────────────────────


@pytest.mark.anyio
async def test_case_commander_skips_siblings_when_not_owned():
    from routers.case_commander import _dohvati_predmet_kontekst
    supa, called = _tracking_supa(owned=False)
    result = await _dohvati_predmet_kontekst("p1", "u1", supa)
    assert result["predmet"] == {}
    assert called["siblings"] == [], f"sibling tables queried despite failed ownership check: {called['siblings']}"


@pytest.mark.anyio
async def test_case_commander_fetches_siblings_when_owned():
    from routers.case_commander import _dohvati_predmet_kontekst
    supa, called = _tracking_supa(owned=True)
    result = await _dohvati_predmet_kontekst("p1", "u1", supa)
    assert result["predmet"]
    assert set(called["siblings"]) == {"rokovi", "predmet_dokumenti", "predmet_komentari"}


# ─── digital_twin.py::_dohvati_kontekst_predmeta ──────────────────────────────


@pytest.mark.anyio
async def test_digital_twin_skips_siblings_when_not_owned():
    from routers.digital_twin import _dohvati_kontekst_predmeta
    from fastapi import HTTPException
    supa, called = _tracking_supa(owned=False)
    with pytest.raises(HTTPException) as exc:
        await _dohvati_kontekst_predmeta(supa, "p1", "u1")
    assert exc.value.status_code == 404
    assert called["siblings"] == [], f"sibling tables queried despite failed ownership check: {called['siblings']}"


@pytest.mark.anyio
async def test_digital_twin_fetches_siblings_when_owned():
    from routers.digital_twin import _dohvati_kontekst_predmeta
    supa, called = _tracking_supa(owned=True)
    result = await _dohvati_kontekst_predmeta(supa, "p1", "u1")
    assert result["predmet"]
    assert set(called["siblings"]) == {"rocista", "predmet_dokumenti", "predmet_komentari"}


# ─── copilot.py::_handle_analiza_predmeta / _handle_plan_predmeta ────────────


@pytest.mark.anyio
async def test_copilot_analiza_predmeta_skips_siblings_when_not_owned():
    from routers.copilot import _handle_analiza_predmeta
    supa, called = _tracking_supa(owned=False)
    with patch("routers.copilot._get_supa", return_value=supa):
        result = await _handle_analiza_predmeta("Analiziraj predmet", "p1", "u1")
    assert result["tip"] == "ANALIZA_PREDMETA"
    assert "nije pronađen" in result["odgovor"]
    assert called["siblings"] == [], f"sibling tables queried despite failed ownership check: {called['siblings']}"


@pytest.mark.anyio
async def test_copilot_plan_predmeta_skips_siblings_when_not_owned():
    from routers.copilot import _handle_plan_predmeta
    supa, called = _tracking_supa(owned=False)
    with patch("routers.copilot._get_supa", return_value=supa):
        result = await _handle_plan_predmeta("Napravi plan", "p1", "u1")
    assert result["tip"] == "PLAN"
    assert "nije pronađen" in result["odgovor"]
    assert called["siblings"] == [], f"sibling tables queried despite failed ownership check: {called['siblings']}"

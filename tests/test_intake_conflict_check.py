# -*- coding: utf-8 -*-
"""
Tests for POST /api/intake/conflict-check

All tests run without live services — Supabase is fully mocked.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request as StarletteRequest


def _fake_user():
    return {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "email":   "advokat@vindex.rs",
        "role":    "advokat",
    }


def _fake_request():
    scope = {
        "type": "http", "method": "POST",
        "headers": [], "query_string": b"",
        "path": "/api/intake/conflict-check",
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _make_supa(clients: list[dict], predmeti: list[dict], pk_by_client: dict[str, list]):
    """Build a Supabase mock that returns the given data."""
    mock = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "klijenti":
            t.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = clients
        elif name == "predmeti":
            t.select.return_value.eq.return_value.execute.return_value.data = predmeti
        elif name == "predmet_klijenti":
            # Return rows based on klijent_id filter
            def _eq_chain(col, val):
                inner = MagicMock()
                inner.execute.return_value.data = pk_by_client.get(val, [])
                return inner
            t.select.return_value.eq.return_value.eq.side_effect = _eq_chain
            # Handle single .eq() chain
            t.select.return_value.eq.side_effect = _eq_chain
        return t

    mock.table.side_effect = _table
    return mock


# ─── T1: protivna strana je već vaš klijent → BLOKIRAJUCI ────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_opposing_is_existing_client():
    """protivna_strana matches a client you already represent → BLOKIRAJUCI."""
    from routers.intake import ConflictCheckIntakeReq, intake_conflict_check

    clients = [{"id": "kl-001", "ime": "Ana", "prezime": "Jović", "firma": "", "pib_encrypted": None}]
    predmeti = [{"id": "pred-001", "naziv": "Radni spor Marković", "tuzilac": "", "tuzeni": ""}]
    pk = {"kl-001": [{"predmet_id": "pred-001", "uloga_klijenta": "stranka"}]}

    body = ConflictCheckIntakeReq(
        novi_klijent_ime="Marko Marković",
        protivna_strana="Ana Jović",
    )

    mock_supa = MagicMock()
    mock_supa.table.side_effect = lambda name: _table_router(name, clients, predmeti, pk)

    with patch("routers.intake._get_supa", return_value=mock_supa):
        result = await intake_conflict_check(body, _fake_request(), _fake_user())

    assert result["conflict_detected"] is True
    assert result["has_blocker"] is True
    blocker = next((c for c in result["conflicts"] if c["tip"] == "opposing_already_client"), None)
    assert blocker is not None, "Expected 'opposing_already_client' conflict"
    assert "Ana" in blocker["opis"]


# ─── T2: novi klijent je već suprotna strana → BLOKIRAJUCI ───────────────────

@pytest.mark.anyio
async def test_new_client_is_opposing_party():
    """novi_klijent_ime matches someone already listed as opposing party → BLOKIRAJUCI."""
    from routers.intake import ConflictCheckIntakeReq, intake_conflict_check

    clients = [{"id": "kl-002", "ime": "Zoran", "prezime": "Simić", "firma": "", "pib_encrypted": None}]
    predmeti = [{"id": "pred-002", "naziv": "Ugovorni spor ABC", "tuzilac": "", "tuzeni": ""}]
    pk = {"kl-002": [{"predmet_id": "pred-002", "uloga_klijenta": "protivna_strana"}]}

    body = ConflictCheckIntakeReq(
        novi_klijent_ime="Zoran Simić",
        protivna_strana="",
    )

    mock_supa = MagicMock()
    mock_supa.table.side_effect = lambda name: _table_router(name, clients, predmeti, pk)

    with patch("routers.intake._get_supa", return_value=mock_supa):
        result = await intake_conflict_check(body, _fake_request(), _fake_user())

    assert result["conflict_detected"] is True
    assert result["has_blocker"] is True
    blocker = next((c for c in result["conflicts"] if c["tip"] == "client_is_opposing"), None)
    assert blocker is not None, "Expected 'client_is_opposing' conflict"


# ─── T3: duplikat klijenta → UPOZORENJE ──────────────────────────────────────

@pytest.mark.anyio
async def test_duplicate_client_warning():
    """novi_klijent_ime matches existing client with role stranka → UPOZORENJE."""
    from routers.intake import ConflictCheckIntakeReq, intake_conflict_check

    clients = [{"id": "kl-003", "ime": "Milica", "prezime": "Stanković", "firma": "", "pib_encrypted": None}]
    predmeti = [{"id": "pred-003", "naziv": "Naknada štete", "tuzilac": "", "tuzeni": ""}]
    pk = {"kl-003": [{"predmet_id": "pred-003", "uloga_klijenta": "stranka"}]}

    body = ConflictCheckIntakeReq(
        novi_klijent_ime="Milica Stanković",
        protivna_strana="Firma XYZ",
    )

    mock_supa = MagicMock()
    mock_supa.table.side_effect = lambda name: _table_router(name, clients, predmeti, pk)

    with patch("routers.intake._get_supa", return_value=mock_supa):
        result = await intake_conflict_check(body, _fake_request(), _fake_user())

    assert result["conflict_detected"] is True
    assert result["has_blocker"] is False, "Duplicate client must not block — only warn"
    dup = next((c for c in result["conflicts"] if c["tip"] == "duplicate_client"), None)
    assert dup is not None
    assert dup["severity"] == "UPOZORENJE"


# ─── T4: bez konflikta → čisto ────────────────────────────────────────────────

@pytest.mark.anyio
async def test_no_conflict_clean():
    """Completely different names → conflict_detected=False."""
    from routers.intake import ConflictCheckIntakeReq, intake_conflict_check

    clients = [{"id": "kl-004", "ime": "Bojan", "prezime": "Ilić", "firma": "", "pib_encrypted": None}]
    predmeti = [{"id": "pred-004", "naziv": "Nasleđe", "tuzilac": "Bojan Ilić", "tuzeni": ""}]
    pk = {"kl-004": [{"predmet_id": "pred-004", "uloga_klijenta": "stranka"}]}

    body = ConflictCheckIntakeReq(
        novi_klijent_ime="Dragan Nikolić",
        protivna_strana="Tamara Vučić",
    )

    mock_supa = MagicMock()
    mock_supa.table.side_effect = lambda name: _table_router(name, clients, predmeti, pk)

    with patch("routers.intake._get_supa", return_value=mock_supa):
        result = await intake_conflict_check(body, _fake_request(), _fake_user())

    assert result["conflict_detected"] is False
    assert result["has_blocker"] is False
    assert result["conflicts"] == []


# ─── T5: protivna strana u tekstu predmeta → UPOZORENJE ──────────────────────

@pytest.mark.anyio
async def test_opposing_in_predmet_text():
    """protivna_strana found in predmeti.tuzeni text field → UPOZORENJE (soft check)."""
    from routers.intake import ConflictCheckIntakeReq, intake_conflict_check

    clients: list = []
    predmeti = [{"id": "pred-005", "naziv": "Privreda spor", "tuzilac": "", "tuzeni": "Firma ABC doo"}]
    pk: dict = {}

    body = ConflictCheckIntakeReq(
        novi_klijent_ime="Petar Petrović",
        protivna_strana="Firma ABC",
    )

    mock_supa = MagicMock()
    mock_supa.table.side_effect = lambda name: _table_router(name, clients, predmeti, pk)

    with patch("routers.intake._get_supa", return_value=mock_supa):
        result = await intake_conflict_check(body, _fake_request(), _fake_user())

    assert result["conflict_detected"] is True
    assert result["has_blocker"] is False
    soft = next((c for c in result["conflicts"] if c["tip"] == "opposing_in_predmet_text"), None)
    assert soft is not None
    assert soft["severity"] == "UPOZORENJE"


# ─── T6: validacija — ime prekratko ───────────────────────────────────────────

def test_conflict_check_req_min_length():
    """novi_klijent_ime must be at least 2 characters."""
    from pydantic import ValidationError
    from routers.intake import ConflictCheckIntakeReq

    with pytest.raises(ValidationError):
        ConflictCheckIntakeReq(novi_klijent_ime="A")


# ─── helpers ──────────────────────────────────────────────────────────────────

def _table_router(name, clients, predmeti, pk):
    t = MagicMock()
    if name == "klijenti":
        t.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = clients
    elif name == "predmeti":
        t.select.return_value.eq.return_value.execute.return_value.data = predmeti
    elif name == "predmet_klijenti":
        def _pk_chain(col, val):
            inner = MagicMock()
            inner.execute.return_value.data = pk.get(val, [])
            return inner
        t.select.return_value.eq.side_effect = _pk_chain
    return t

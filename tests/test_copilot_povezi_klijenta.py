# -*- coding: utf-8 -*-
"""
Tests for routers/copilot.py::_handle_akcija_povezi_klijenta -- Night Shift
M-012 (2026-08-02), technical debt: two bugs on predmet_klijenti, same root
cause as Mission 001 (predmet_klijenti has no `id` column -- composite PK --
and no `user_id` column -- ownership derived via predmet_id -> predmeti.user_id).

Found while fixing the already-known .select("id") bug: the insert two lines
below it also sent user_id, a 6th call site of Mission 001's bug class that
mission's own sweep missed.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _mock_gpt_response(content: dict):
    choice = MagicMock()
    choice.message.content = json.dumps(content)
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.anyio
async def test_povezi_klijenta_insert_does_not_send_user_id():
    """User scenario: lawyer asks the copilot to link a client to the
    current case by name. The insert must succeed -- before this fix,
    PostgREST would reject it (PGRST204: no such column `user_id`), the
    same silent failure Mission 001 fixed at 5 other call sites."""
    from routers.copilot import _handle_akcija_povezi_klijenta

    mock_supa = MagicMock()
    insert_calls = []

    def _table(name):
        t = MagicMock()
        if name == "klijenti":
            t.select.return_value.eq.return_value.or_.return_value.limit.return_value.execute.return_value.data = [
                {"id": "kl-001", "ime": "Ana", "prezime": "Jović", "firma": ""}
            ]
        elif name == "predmet_klijenti":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []  # not yet linked
            def _insert(payload):
                insert_calls.append(payload)
                i = MagicMock()
                i.execute.return_value.data = [payload]
                return i
            t.insert.side_effect = _insert
        return t

    mock_supa.table.side_effect = _table

    with patch("routers.copilot._get_supa", return_value=mock_supa), \
         patch("routers.copilot._pozovi_gpt4o_mini", new=AsyncMock(
             return_value=_mock_gpt_response({"ime_klijenta": "Ana Jović", "uloga": "stranka"})
         )):
        result = await _handle_akcija_povezi_klijenta("poveži Anu Jović sa ovim predmetom", "pred-001", "uid-001")

    assert result["uspeh"] is True
    assert len(insert_calls) == 1
    assert "user_id" not in insert_calls[0], "predmet_klijenti insert must not send user_id (no such column)"
    assert insert_calls[0]["predmet_id"] == "pred-001"
    assert insert_calls[0]["klijent_id"] == "kl-001"


@pytest.mark.anyio
async def test_povezi_klijenta_duplicate_check_uses_real_column():
    """The duplicate-link check must use a real predmet_klijenti column
    (predmet_id/klijent_id), never `id` -- the table has no id column
    (composite PK). Before this fix this select would raise, preventing the
    duplicate check from ever completing."""
    from routers.copilot import _handle_akcija_povezi_klijenta

    mock_supa = MagicMock()
    select_columns = []

    def _table(name):
        t = MagicMock()
        if name == "klijenti":
            t.select.return_value.eq.return_value.or_.return_value.limit.return_value.execute.return_value.data = [
                {"id": "kl-002", "ime": "Marko", "prezime": "Petrović", "firma": ""}
            ]
        elif name == "predmet_klijenti":
            def _select(cols):
                select_columns.append(cols)
                s = MagicMock()
                s.eq.return_value.eq.return_value.execute.return_value.data = [{"predmet_id": "pred-002"}]  # already linked
                return s
            t.select.side_effect = _select
        return t

    mock_supa.table.side_effect = _table

    with patch("routers.copilot._get_supa", return_value=mock_supa), \
         patch("routers.copilot._pozovi_gpt4o_mini", new=AsyncMock(
             return_value=_mock_gpt_response({"ime_klijenta": "Marko Petrović", "uloga": "stranka"})
         )):
        result = await _handle_akcija_povezi_klijenta("poveži Marka", "pred-002", "uid-001")

    assert select_columns == ["predmet_id"]
    assert "id" not in select_columns
    assert result["uspeh"] is True
    assert "već vezan" in result["odgovor"]

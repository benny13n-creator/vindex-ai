# -*- coding: utf-8 -*-
"""
Final Beta Gate — F21 (MEDIUM): _grupiraj_notifikacije collapses N same-tip
notifications ("3 x Hitan rok") onto ONE representative dict for display.
Clicking that group used to only ever PATCH the representative row's own id
(routers/notifications.py::mark_read) -- the other N-1 rows stayed
procitano=false server-side; the group merely re-collapsed onto the same
representative on the next load, so it LOOKED read. Fixed by (1) attaching
the full id list to the grouped dict, (2) a new batch endpoint
PATCH /notifications/read-group, (3) the frontend calling it with all ids
when a group was clicked.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {"type": "http", "method": "PATCH", "path": "/notifications/read-group", "headers": [],
              "query_string": b"", "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


def test_grouped_notification_carries_all_member_ids():
    from routers.notifications import _grupiraj_notifikacije, NOTIF_TIPOVI

    notifs = [
        {"id": "n1", "tip": "hitan_rok", "prioritet": NOTIF_TIPOVI["hitan_rok"]["priority"], "naslov": "Rok A"},
        {"id": "n2", "tip": "hitan_rok", "prioritet": NOTIF_TIPOVI["hitan_rok"]["priority"], "naslov": "Rok B"},
        {"id": "n3", "tip": "hitan_rok", "prioritet": NOTIF_TIPOVI["hitan_rok"]["priority"], "naslov": "Rok C"},
    ]
    result = _grupiraj_notifikacije(notifs)

    assert len(result) == 1
    grouped = result[0]
    assert grouped["grouped_count"] == 3
    assert sorted(grouped["ids"]) == ["n1", "n2", "n3"]
    # representative id/fields still present (spread from items[0]) -- backward compatible
    assert grouped["id"] == "n1"


def test_single_notification_of_a_type_has_no_ids_field():
    """A single (non-grouped) item must NOT gain an "ids" field it never had
    before -- the frontend's fallback to the single-id endpoint depends on
    this field being absent/length-1 for non-grouped notifications."""
    from routers.notifications import _grupiraj_notifikacije, NOTIF_TIPOVI

    notifs = [{"id": "n1", "tip": "hitan_rok", "prioritet": NOTIF_TIPOVI["hitan_rok"]["priority"], "naslov": "Rok A"}]
    result = _grupiraj_notifikacije(notifs)

    assert len(result) == 1
    assert "ids" not in result[0]


@pytest.mark.anyio
async def test_mark_group_read_updates_every_id_in_one_call():
    from routers.notifications import mark_group_read, MarkGroupReadReq

    supa = MagicMock()
    chain = MagicMock()
    chain.eq.return_value = chain
    chain.in_.return_value = chain
    chain.execute.return_value = MagicMock(data=[{"id": "n1"}, {"id": "n2"}, {"id": "n3"}])
    supa.table.return_value.update.return_value = chain

    body = MarkGroupReadReq(ids=["n1", "n2", "n3"])

    with patch("routers.notifications._get_supa", return_value=supa):
        result = await mark_group_read(body, _req(), {"user_id": "u1"})

    assert result == {"ok": True}
    chain.in_.assert_called_once_with("id", ["n1", "n2", "n3"])
    chain.eq.assert_called_once_with("user_id", "u1")


@pytest.mark.anyio
async def test_mark_group_read_scoped_to_owning_user():
    """The update must still be eq("user_id", uid)-scoped -- a group read
    request must never be able to mark another user's notification rows."""
    from routers.notifications import mark_group_read, MarkGroupReadReq

    supa = MagicMock()
    chain = MagicMock()
    chain.eq.return_value = chain
    chain.in_.return_value = chain
    chain.execute.return_value = MagicMock(data=[])
    supa.table.return_value.update.return_value = chain

    body = MarkGroupReadReq(ids=["some-other-users-notif-id"])

    with patch("routers.notifications._get_supa", return_value=supa):
        await mark_group_read(body, _req(), {"user_id": "attacker-uid"})

    chain.eq.assert_called_once_with("user_id", "attacker-uid")

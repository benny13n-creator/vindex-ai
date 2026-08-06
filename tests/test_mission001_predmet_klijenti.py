# -*- coding: utf-8 -*-
"""
Mission 001 (2026-08-02) — predmet_klijenti ownership integrity.

Regression tests for the `predmet_klijenti.user_id` bug: the table has no `user_id` column
(supabase_setup.sql:610-615, a pure join table — ownership is derived transitively via
predmet_id -> predmeti.user_id), but 5 insert call sites sent it anyway, causing PostgREST to
reject the insert (PGRST204) and the link to silently never persist.

Also covers the api.py `.select("id")` duplicate-check bug (same nonexistent-column class, folded
into this mission per the founder's scope-boundary ruling: it sat directly in front of one of the
5 inserts already being fixed here) and the bulk-import compensating-delete fix for the
orphan-predmet risk.

All tests run without live services — Supabase is fully mocked.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from starlette.requests import Request as StarletteRequest


def _fake_user():
    return {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "email":   "advokat@vindex.rs",
        "role":    "advokat",
    }


def _fake_request(path="/api/intake/kreiraj"):
    scope = {
        "type": "http", "method": "POST",
        "headers": [], "query_string": b"",
        "path": path,
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _capture_insert_mock(predmeti_id="pred-001", extra_tables=None):
    """
    Supabase mock: predmeti.insert().execute() returns a row with the given id;
    predmet_klijenti.insert(...) is captured (via a MagicMock whose call args we can inspect)
    and succeeds. `extra_tables` lets a caller register additional table behavior.
    """
    mock = MagicMock()
    pk_insert_mock = MagicMock()
    pk_insert_mock.return_value.execute.return_value.data = [{"predmet_id": predmeti_id, "klijent_id": "kl-001"}]
    pk_table = MagicMock()
    pk_table.insert.side_effect = pk_insert_mock

    def _table(name):
        if name == "predmeti":
            t = MagicMock()
            t.insert.return_value.execute.return_value.data = [{"id": predmeti_id}]
            return t
        elif name == "predmet_klijenti":
            return pk_table
        elif extra_tables and name in extra_tables:
            return extra_tables[name](MagicMock())
        return MagicMock()

    mock.table.side_effect = _table
    mock._pk_insert_mock = pk_insert_mock
    return mock


# ─── Sites #1-#3 (routers/intake.py) and #5 (routers/onboarding.py): user_id must be absent ──


@pytest.mark.anyio
async def test_intake_kreiraj_does_not_send_user_id():
    from routers.intake import IntakeKreirajReq, intake_kreiraj

    mock_supa = _capture_insert_mock()
    body = IntakeKreirajReq(klijent_id="kl-001", naziv="Naknada štete — Marković")

    with patch("routers.intake._get_supa", return_value=mock_supa):
        await intake_kreiraj(body, _fake_request(), _fake_user())

    sent = mock_supa._pk_insert_mock.call_args[0][0]
    assert "user_id" not in sent, "predmet_klijenti insert must not send user_id (no such column)"
    assert sent["predmet_id"] == "pred-001"
    assert sent["klijent_id"] == "kl-001"


@pytest.mark.anyio
async def test_from_template_does_not_send_user_id():
    from routers.intake import FromTemplateReq, post_from_template

    mock_supa = _capture_insert_mock()
    body = FromTemplateReq(template_id="tpl-gradjansko-steta", naziv="Naknada štete — Marković", klijent_id="kl-001")

    with patch("routers.intake._get_supa", return_value=mock_supa):
        await post_from_template(_fake_request(), body, _fake_user())

    sent = mock_supa._pk_insert_mock.call_args[0][0]
    assert "user_id" not in sent, "predmet_klijenti insert must not send user_id (no such column)"


@pytest.mark.anyio
async def test_onboarding_demo_case_does_not_send_user_id():
    import inspect
    import routers.onboarding as onboarding_mod

    src = inspect.getsource(onboarding_mod)
    # Structural check: the specific insert this mission fixed must not contain user_id in its payload.
    idx = src.index('supa.table("predmet_klijenti").insert({')
    payload_snippet = src[idx: idx + 300]
    assert '"user_id"' not in payload_snippet, (
        "routers/onboarding.py's predmet_klijenti insert must not send user_id (no such column)"
    )


# ─── Site #3 (bulk-import): user_id absent AND compensating delete on link failure ───────────


@pytest.mark.anyio
async def test_bulk_import_does_not_send_user_id_and_succeeds():
    from routers.intake import BulkImportReq, BulkImportRed, intake_bulk_import

    mock_supa = MagicMock()
    pk_table = MagicMock()
    pk_table.insert.return_value.execute.return_value.data = [{"predmet_id": "pred-new"}]

    def _table(name):
        if name == "klijenti":
            t = MagicMock()
            t.select.return_value.eq.return_value.eq.return_value.neq.return_value.limit.return_value.execute.return_value.data = []
            t.insert.return_value.execute.return_value.data = [{"id": "kl-new"}]
            return t
        elif name == "predmeti":
            t = MagicMock()
            t.insert.return_value.execute.return_value.data = [{"id": "pred-new"}]
            return t
        elif name == "predmet_klijenti":
            return pk_table
        return MagicMock()

    mock_supa.table.side_effect = _table
    body = BulkImportReq(redovi=[BulkImportRed(ime="Marko", prezime="Marković", naziv_predmeta="Spor 1")])

    with patch("routers.intake._get_supa", return_value=mock_supa):
        result = await intake_bulk_import(_fake_request("/api/intake/bulk-import"), body, _fake_user())

    assert result["greske_broj"] == 0
    sent = pk_table.insert.call_args[0][0]
    assert "user_id" not in sent, "predmet_klijenti insert must not send user_id (no such column)"


@pytest.mark.anyio
async def test_bulk_import_compensating_delete_on_link_failure():
    """
    If the predmet_klijenti insert fails after the predmet row already committed, the predmet
    row must be deleted (compensating action) rather than left as an orphan with a misleading
    "row failed" error that doesn't match what actually happened in the database.
    """
    from routers.intake import BulkImportReq, BulkImportRed, intake_bulk_import

    mock_supa = MagicMock()
    delete_calls = []

    def _table(name):
        t = MagicMock()
        if name == "klijenti":
            t.select.return_value.eq.return_value.eq.return_value.neq.return_value.limit.return_value.execute.return_value.data = []
            t.insert.return_value.execute.return_value.data = [{"id": "kl-new"}]
        elif name == "predmeti":
            t.insert.return_value.execute.return_value.data = [{"id": "pred-orphan-risk"}]
            def _delete():
                d = MagicMock()
                def _eq(col, val):
                    delete_calls.append((col, val))
                    e = MagicMock()
                    e.execute.return_value = MagicMock()
                    return e
                d.eq.side_effect = _eq
                return d
            t.delete.side_effect = _delete
        elif name == "predmet_klijenti":
            t.insert.return_value.execute.side_effect = Exception("PGRST204: simulated link failure")
        return t

    mock_supa.table.side_effect = _table
    body = BulkImportReq(redovi=[BulkImportRed(ime="Ana", prezime="Jović", naziv_predmeta="Spor 2")])

    with patch("routers.intake._get_supa", return_value=mock_supa):
        result = await intake_bulk_import(_fake_request("/api/intake/bulk-import"), body, _fake_user())

    assert result["greske_broj"] == 1, "the row must be reported as failed"
    assert delete_calls == [("id", "pred-orphan-risk")], (
        "the just-created predmet row must be deleted when the client link insert fails, "
        "so a 'row failed' error accurately means nothing was persisted"
    )


# ─── api.py confirm-links endpoint: select() uses a real column; no duplicate insert ─────────


@pytest.mark.anyio
async def test_confirm_links_finds_existing_link_and_skips_duplicate_insert():
    """
    User Scenario Test (per Mission 001's Definition-of-Done rule): link a client to a case
    that is already linked -- the duplicate check must actually find the existing row (not
    error on the nonexistent `id` column predmet_klijenti never had) and must not insert a
    second row. Exercises the real endpoint function, not a source-text inspection.
    """
    from api import ConfirmLinksReq, predmet_confirm_links

    insert_calls = []

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {"id": "pred-001"}
        elif name == "klijenti":
            # Lambda 002 ownership-check query: kl-001 belongs to the caller.
            t.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = [{"id": "kl-001"}]
        elif name == "predmet_klijenti":
            # Simulate: (pred-001, kl-001) is already linked.
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"predmet_id": "pred-001"}]
            def _insert(payload):
                insert_calls.append(payload)
                i = MagicMock()
                i.execute.return_value.data = [payload]
                return i
            t.insert.side_effect = _insert
        return t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table
    req = ConfirmLinksReq(klijent_ids=["kl-001"])

    with patch("api._get_supa", return_value=mock_supa), patch("api._audit", return_value=None):
        result = await predmet_confirm_links("pred-001", req, _fake_request("/api/predmeti/pred-001/confirm-links"), _fake_user())

    assert insert_calls == [], (
        "duplicate check must find the existing link and skip the insert -- "
        "before the fix, selecting a nonexistent 'id' column would raise before "
        "this decision was ever reached"
    )
    assert result["linked_klijenti"] == ["kl-001"]

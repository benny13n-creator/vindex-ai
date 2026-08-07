# -*- coding: utf-8 -*-
"""
Program Phoenix, Mission 011 -- Billing & Reference Integrity.
Closes LIVINGSYS-DEBT-054 (faktura_create predmet_id validation) and
LIVINGSYS-DEBT-044 (redni_broj concurrent-finalize collision).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from starlette.requests import Request as StarletteRequest

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

from test_sprint006_finalize_assimilation import (  # noqa: E402
    _doc_entry, _make_supa, _run_finalize_and_drain,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    scope = {
        "type": "http", "method": "POST", "path": "/", "headers": [],
        "query_string": b"", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 1234),
    }
    return StarletteRequest(scope=scope, receive=receive)


def _chain(execute_return=None, execute_side_effect=None):
    m = MagicMock()
    for method in ("select", "eq", "neq", "insert", "update", "limit", "order",
                   "is_", "in_", "gte", "lte", "like", "maybe_single"):
        setattr(m, method, MagicMock(return_value=m))
    m.not_ = m
    if execute_side_effect is not None:
        m.execute = MagicMock(side_effect=execute_side_effect)
    else:
        m.execute = MagicMock(return_value=execute_return)
    return m


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-054 -- faktura_create never validated predmet_id matches the
# billed entries' actual case.
# ═══════════════════════════════════════════════════════════════════════════

def _faktura_body(predmet_id="p1"):
    from routers.billing import FakturaReq
    return FakturaReq(predmet_id=predmet_id, entry_ids=["e1", "e2"], klijent_naziv="Klijent D.O.O.", pdv_stopa=20)


def test_faktura_create_rejects_entry_from_different_case():
    import asyncio
    import routers.billing as billing
    from fastapi import HTTPException

    entries_chain = _chain(MagicMock(data=[
        {"id": "e1", "predmet_id": "p1", "iznos_rsd": 1000, "obracunato": False},
        {"id": "e2", "predmet_id": "p-OTHER-CASE", "iznos_rsd": 500, "obracunato": False},
    ]))
    supa = MagicMock()
    supa.table.side_effect = lambda name: entries_chain if name == "billing_entries" else _chain(MagicMock(data=[]))

    with patch.object(billing, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(billing.faktura_create(_faktura_body(), _req(), {"user_id": "u1", "email": "a@b.com"}))

    assert exc.value.status_code == 400


def test_faktura_create_succeeds_when_all_entries_match_predmet_id():
    """Regression: the normal, correct case (every entry genuinely belongs to
    the invoiced case) must still succeed exactly as before this mission."""
    import asyncio
    import routers.billing as billing

    entries_chain = _chain(MagicMock(data=[
        {"id": "e1", "predmet_id": "p1", "iznos_rsd": 1000, "obracunato": False},
        {"id": "e2", "predmet_id": "p1", "iznos_rsd": 500, "obracunato": False},
    ]))
    broj_select_chain = _chain(MagicMock(data=[]))
    insert_ok_chain = _chain(MagicMock(data=[{"id": "f1", "broj_fakture": "2026/0001"}]))
    update_chain = _chain(MagicMock(data=[{"id": "e1"}, {"id": "e2"}]))

    be_calls = {"n": 0}

    class _FakturaTable:
        select = broj_select_chain.select
        eq = broj_select_chain.eq
        like = broj_select_chain.like
        order = broj_select_chain.order
        limit = broj_select_chain.limit
        execute = broj_select_chain.execute

        @staticmethod
        def insert(_row):
            return insert_ok_chain

    def _table(name):
        if name == "billing_entries":
            be_calls["n"] += 1
            return entries_chain if be_calls["n"] == 1 else update_chain
        if name == "fakture":
            return _FakturaTable
        return _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(billing, "_get_supa", return_value=supa):
        result = asyncio.run(billing.faktura_create(_faktura_body(), _req(), {"user_id": "u1", "email": "a@b.com"}))

    assert result["faktura"]["id"] == "f1"


# ═══════════════════════════════════════════════════════════════════════════
# LIVINGSYS-DEBT-044 -- redni_broj (document sequence number) could collide
# under concurrent finalize calls to the same predmet_id.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_redni_broj_conflict_retries_with_next_number_and_succeeds():
    """Original-scenario reproduction: the DB rejects the first candidate
    redni_broj (another concurrent finalize call already claimed it) -- the
    retry must pick the next number and still successfully link the document,
    not silently fail or crash."""
    from routers.smart_intake import FinalizeReq

    doc, _ = _doc_entry("dok-001")
    mock_supa = _make_supa()
    real_table = mock_supa.table.side_effect
    conflict_err = Exception(
        'duplicate key value violates unique constraint "predmet_dokumenti_predmet_redni_unique" 23505'
    )
    state = {"attempts": 0}

    def _conflict_table(name):
        t = real_table(name)
        if name == "predmet_dokumenti":
            def _insert(row):
                state["attempts"] += 1
                if row.get("redni_broj") == 1:
                    raise conflict_err
                res = MagicMock()
                res.data = [{"id": "pdok-final"}]
                return res
            t.insert = MagicMock(side_effect=_insert)
        return t
    mock_supa.table.side_effect = _conflict_table

    result = await _run_finalize_and_drain(mock_supa, [doc], FinalizeReq())

    assert result["dokumenata_povezano"] == 1
    assert state["attempts"] == 2  # 1 conflict (redni_broj=1) + 1 success (redni_broj=2)


@pytest.mark.anyio
async def test_redni_broj_conflict_exhausts_retries_without_crashing():
    """A pathological always-conflicting sequence must fail the single document
    gracefully (bounded 3 attempts), not crash the whole finalize call or loop
    forever."""
    from routers.smart_intake import FinalizeReq

    doc, _ = _doc_entry("dok-001")
    mock_supa = _make_supa()
    real_table = mock_supa.table.side_effect
    conflict_err = Exception(
        'duplicate key value violates unique constraint "predmet_dokumenti_predmet_redni_unique" 23505'
    )
    state = {"attempts": 0}

    def _always_conflict_table(name):
        t = real_table(name)
        if name == "predmet_dokumenti":
            def _insert(row):
                state["attempts"] += 1
                raise conflict_err
            t.insert = MagicMock(side_effect=_insert)
        return t
    mock_supa.table.side_effect = _always_conflict_table

    result = await _run_finalize_and_drain(mock_supa, [doc], FinalizeReq())

    assert result["dokumenata_povezano"] == 0
    assert state["attempts"] == 3


@pytest.mark.anyio
async def test_non_conflict_insert_failure_does_not_trigger_redni_retry():
    """Regression: a non-conflict insert failure (schema mismatch, connection
    blip) must NOT be treated as a redni_broj race -- it should exhaust the
    existing 6-variant fallback ladder once and stop, exactly like before this
    mission (proven by the untouched test_one_document_insert_failure_does_not_
    lose_or_block_sibling in test_sprint006_finalize_assimilation.py); this is
    an additional direct assertion on attempt count for that same guarantee."""
    from routers.smart_intake import FinalizeReq

    doc, _ = _doc_entry("dok-001")
    mock_supa = _make_supa()
    real_table = mock_supa.table.side_effect
    state = {"attempts": 0}

    def _boom_table(name):
        t = real_table(name)
        if name == "predmet_dokumenti":
            def _insert(row):
                state["attempts"] += 1
                raise RuntimeError("insert boom")
            t.insert = MagicMock(side_effect=_insert)
        return t
    mock_supa.table.side_effect = _boom_table

    result = await _run_finalize_and_drain(mock_supa, [doc], FinalizeReq())

    assert result["dokumenata_povezano"] == 0
    # All 6 fallback variants tried exactly once (no redni_broj retry loop
    # triggered by a non-conflict error).
    assert state["attempts"] == 6

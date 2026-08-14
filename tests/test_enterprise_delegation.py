# -*- coding: utf-8 -*-
"""
Regression tests — case delegation (routers/enterprise.py + api.py::get_predmet).

NIGHTLY REPAIR (2026-07-24), Faza 2 item 6: delegiraj_predmet wrote a
predmet_delegiranja row but (a) never verified advokat_user_id actually
belonged to the delegator's firm, and (b) nothing ELSE in the codebase
ever read predmet_delegiranja to grant access -- delegating a case to a
colleague silently gave them zero actual access anywhere. This fixes the
same-firm check on the write side and wires a real (read-only) access
grant into GET /api/predmeti/{id} on the read side. Write actions (notes,
edits) remain gated on original ownership only -- a deliberate, disclosed
scope decision, not an oversight.

Pure unit tests -- no live Supabase.
"""
import asyncio
import os
import sys
import types
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from starlette.requests import Request as StarletteRequest  # noqa: E402

import api  # noqa: E402
import routers.enterprise as enterprise  # noqa: E402


def _req(path="/api/x") -> StarletteRequest:
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    scope = {
        "type": "http", "method": "GET", "path": path,
        "headers": [], "query_string": b"", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 12345),
    }
    return StarletteRequest(scope=scope, receive=receive)


def _chain(execute_return):
    m = MagicMock()
    for method in ("select", "eq", "maybe_single", "in_", "single"):
        setattr(m, method, MagicMock(return_value=m))
    m.execute = MagicMock(return_value=execute_return)
    return m


# ═══════════════════════════════════════════════════════════════════════════
# routers/enterprise.py::delegiraj_predmet — same-firm check
# ═══════════════════════════════════════════════════════════════════════════

def test_delegiraj_rejects_target_not_in_same_firm():
    pred_chain = _chain(MagicMock(data={"naziv": "X", "user_id": "u1"}))
    admin_chain = _chain(MagicMock(data={"id": "firm1"}))
    members_chain = _chain(MagicMock(data=[{"user_id": "u1", "uloga": "admin"}, {"user_id": "u2", "uloga": "advokat"}]))

    def _table(name):
        return {
            "predmeti": pred_chain,
            "kancelarije": admin_chain,
            "kancelarija_clanovi": members_chain,
        }[name]

    supa = MagicMock()
    supa.table.side_effect = _table

    payload = enterprise.DelegiranjeRequest(predmet_id="p1", advokat_user_id="napadac-nije-u-firmi")
    with patch.object(enterprise, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(enterprise.delegiraj_predmet(_req(), payload, {"user_id": "u1", "email": "a@b.com"}))

    assert exc_info.value.status_code == 400


def test_delegiraj_succeeds_for_same_firm_member():
    pred_chain = _chain(MagicMock(data={"naziv": "X", "user_id": "u1"}))
    admin_chain = _chain(MagicMock(data={"id": "firm1"}))
    members_chain = _chain(MagicMock(data=[{"user_id": "u1", "uloga": "admin"}, {"user_id": "u2", "uloga": "advokat"}]))
    insert_chain = _chain(MagicMock(data=[{"id": "deleg1"}]))
    insert_chain.insert = MagicMock(return_value=insert_chain)

    call_count = {"n": 0}
    def _table(name):
        if name == "predmet_delegiranja":
            return insert_chain
        return {"predmeti": pred_chain, "kancelarije": admin_chain, "kancelarija_clanovi": members_chain}[name]

    supa = MagicMock()
    supa.table.side_effect = _table

    payload = enterprise.DelegiranjeRequest(predmet_id="p1", advokat_user_id="u2")
    with patch.object(enterprise, "_get_supa", return_value=supa):
        result = asyncio.run(enterprise.delegiraj_predmet(_req(), payload, {"user_id": "u1", "email": "a@b.com"}))

    assert result["ok"] is True
    inserted = insert_chain.insert.call_args[0][0]
    assert inserted["na_user_id"] == "u2"


def test_delegiraj_rejects_unowned_predmet():
    pred_chain = _chain(MagicMock(data=None))
    supa = MagicMock()
    supa.table.return_value = pred_chain

    payload = enterprise.DelegiranjeRequest(predmet_id="tudje", advokat_user_id="u2")
    with patch.object(enterprise, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(enterprise.delegiraj_predmet(_req(), payload, {"user_id": "u1", "email": "a@b.com"}))

    assert exc_info.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# api.py::get_predmet — delegated colleague gets real read access
# ═══════════════════════════════════════════════════════════════════════════

def _fake_user(uid: str):
    return types.SimpleNamespace(id=uid, email="test@vindex.rs")


def test_get_predmet_owner_access_unchanged():
    pred_data = {"id": "p1", "naziv": "Test", "user_id": "owner"}
    owner_chain = _chain(MagicMock(data=pred_data))
    empty_chain = _chain(MagicMock(data=[]))

    def _table(name):
        return owner_chain if name == "predmeti" else empty_chain

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(api, "_require_auth", return_value=_fake_user("owner")), \
         patch.object(api, "_get_supa", return_value=supa):
        result = asyncio.run(api.get_predmet("p1", _req(), authorization="Bearer faketoken"))

    assert result["predmet"]["id"] == "p1"


def test_get_predmet_grants_access_via_active_delegation():
    """Nucleus of the fix: a colleague with NO ownership but an ACTIVE
    delegation must now be able to read the case, where before this would
    have been a 404 regardless of the delegation record's existence."""
    pred_data = {"id": "p1", "naziv": "Test", "user_id": "owner"}

    owner_check = _chain(MagicMock(data=None))       # eq(user_id=colega) -> not owner
    deleg_check = _chain(MagicMock(data={"id": "deleg1"}))  # active delegation found
    full_pred   = _chain(MagicMock(data=pred_data))   # re-fetch without user_id filter
    empty_chain = _chain(MagicMock(data=[]))

    call_count = {"n": 0}
    def _table(name):
        if name == "predmeti":
            call_count["n"] += 1
            return owner_check if call_count["n"] == 1 else full_pred
        if name == "predmet_delegiranja":
            return deleg_check
        return empty_chain

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(api, "_require_auth", return_value=_fake_user("kolega")), \
         patch.object(api, "_get_supa", return_value=supa):
        result = asyncio.run(api.get_predmet("p1", _req(), authorization="Bearer faketoken"))

    assert result["predmet"]["id"] == "p1"
    deleg_check.eq.assert_any_call("na_user_id", "kolega")
    deleg_check.eq.assert_any_call("status", "aktivno")


def test_get_predmet_no_delegation_still_404():
    owner_check = _chain(MagicMock(data=None))
    deleg_check = _chain(MagicMock(data=None))  # no active delegation either

    def _table(name):
        return owner_check if name == "predmeti" else deleg_check

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(api, "_require_auth", return_value=_fake_user("stranac")), \
         patch.object(api, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(api.get_predmet("p1", _req(), authorization="Bearer faketoken"))

    assert exc_info.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# FS-P1-25 — `ok: True` BEZ DOKAZA DA JE DELEGIRANJE UPISANO
# ═══════════════════════════════════════════════════════════════════════════
#
# STARI UGOVOR: rezultat `insert`-a se odbacivao; odgovor je uvek `ok: True`.
# NOVI UGOVOR:  upis koji ne vrati nijedan red je 503 uz izričitu poruku da je
#               predmet ostao samo kod prvog advokata.
# ZAŠTO JE STARI BIO POGREŠAN: delegiranje je PRISTUPNA odluka — drugi advokat
#               dobija pravo čitanja kroz `shared/rag_acl.py`. Neupisano
#               delegiranje znači da prvi veruje da je predao predmet, drugi ga
#               ne vidi, i niko ne zna da se to desilo.

def _delegiranje_supa(insert_data):
    pred_chain = _chain(MagicMock(data={"naziv": "X", "user_id": "u1"}))
    admin_chain = _chain(MagicMock(data={"id": "firm1"}))
    members_chain = _chain(MagicMock(data=[{"user_id": "u1", "uloga": "admin"},
                                           {"user_id": "u2", "uloga": "advokat"}]))
    insert_chain = _chain(MagicMock(data=insert_data))
    insert_chain.insert = MagicMock(return_value=insert_chain)

    def _table(name):
        if name == "predmet_delegiranja":
            return insert_chain
        return {"predmeti": pred_chain, "kancelarije": admin_chain,
                "kancelarija_clanovi": members_chain}[name]

    supa = MagicMock()
    supa.table.side_effect = _table
    return supa


def test_delegiranje_bez_upisanog_reda_NIJE_uspeh():
    """NAJVAŽNIJI TEST U FAJLU."""
    from fastapi import HTTPException

    payload = enterprise.DelegiranjeRequest(predmet_id="p1", advokat_user_id="u2")
    with patch.object(enterprise, "_get_supa", return_value=_delegiranje_supa([])):
        with pytest.raises(HTTPException) as e:
            asyncio.run(enterprise.delegiraj_predmet(
                _req(), payload, {"user_id": "u1", "email": "a@b.com"}))

    assert e.value.status_code == 503
    assert "NIJE sačuvano" in e.value.detail
    assert "samo kod vas" in e.value.detail


def test_delegiranje_sa_upisanim_redom_i_dalje_prolazi():
    """Negativna kontrola."""
    payload = enterprise.DelegiranjeRequest(predmet_id="p1", advokat_user_id="u2")
    with patch.object(enterprise, "_get_supa",
                      return_value=_delegiranje_supa([{"id": "deleg1"}])):
        result = asyncio.run(enterprise.delegiraj_predmet(
            _req(), payload, {"user_id": "u1", "email": "a@b.com"}))
    assert result["ok"] is True

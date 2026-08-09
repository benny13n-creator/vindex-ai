# -*- coding: utf-8 -*-
"""
V35 — kanonski audit za komentar_delete i integration_webhook_delete.

NAMESPACE JE SUŠTINA OVE GRUPE
Dve rute brišu webhook-e iz DVE različite tabele koje dele prostor ID-eva:

    integracije.py::webhook_brisi   -> user_webhooks -> "user_webhook"  (V34)
    integrations.py::delete_webhook -> webhooks      -> "webhook"       (V35)

Zajednički resource_type dao bi forenzički nerazlučive zapise: isti
resource_id, ista akcija, a različit resurs. Test 8 to prikucava u oba smera.

BEST-EFFORT SE MERI NA PRAVOJ GRANICI
Kao u V34: otkaz se ubrizgava u _build_and_insert (sink ISPOD log_action), a ne
zamenom log_action-a, jer bi zamena uklonila upravo guard koji se dokazuje
(shared/audit_immutable.py L219-230, dva except Exception bez re-raise-a).
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request as _SReq

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

A, B = "user-A", "user-B"


class _Store:
    def __init__(self, rows):
        self.rows = list(rows)

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, store, table):
        self.s, self.t, self.f = store, table, {}

    def delete(self):
        return self

    def eq(self, col, val):
        self.f[col] = val
        return self

    def execute(self):
        hit = [r for r in self.s.rows
               if r.get("_t") == self.t and all(r.get(k) == v for k, v in self.f.items())]
        for r in hit:
            self.s.rows.remove(r)
        res = MagicMock()
        res.data = hit
        return res


class _Audit:
    def __init__(self):
        self.calls = []

    async def __call__(self, action, **kw):
        self.calls.append({"action": action, **kw})
        return "audit-id"


def _http():
    return _SReq(scope={"type": "http", "method": "DELETE", "headers": [], "query_string": b"",
                        "path": "/x", "client": ("127.0.0.1", 1),
                        "app": MagicMock(), "state": MagicMock()})


def _komentar(store, audit, rid, uid):
    import routers.komentari as m
    with patch.object(m, "_get_supa", return_value=store), \
         patch("shared.audit_immutable.log_action", audit):
        return asyncio.run(m.delete_komentar(rid, _http(), {"user_id": uid}))


def _webhook(store, audit, rid, uid):
    import routers.integrations as m
    with patch.object(m, "_get_supa", return_value=store), \
         patch("shared.audit_immutable.log_action", audit):
        return asyncio.run(m.delete_webhook(rid, {"user_id": uid}))


CASES = [
    ("komentar", _komentar, "predmet_komentari", "komentar_delete", "komentar"),
    ("webhook",  _webhook,  "webhooks",          "integration_webhook_delete", "webhook"),
]


def _store_for(table):
    return _Store([{"_t": table, "id": "res-A", "user_id": A},
                   {"_t": table, "id": "res-B", "user_id": B}])


def _run(call, store, audit, rid, uid):
    try:
        call(store, audit, rid, uid)
        return 200
    except HTTPException as e:
        return e.status_code


@pytest.mark.parametrize("name,call,table,action,rtype", CASES)
def test_1_success_emits_exactly_one_audit(name, call, table, action, rtype):
    st, au = _store_for(table), _Audit()
    assert _run(call, st, au, "res-A", A) == 200
    assert len(au.calls) == 1, f"{name}: tačno jedan audit, dobijeno {len(au.calls)}"
    c = au.calls[0]
    assert c["action"] == action
    assert c["resource_type"] == rtype
    assert c["resource_id"] == "res-A"
    assert c["user_id"] == A
    assert "correlation_id" not in c, "correlation se auto-izvodi"


@pytest.mark.parametrize("name,call,table,action,rtype", CASES)
def test_2_nonexistent_emits_no_audit(name, call, table, action, rtype):
    st, au = _store_for(table), _Audit()
    assert _run(call, st, au, "ne-postoji", A) == 404
    assert au.calls == []


@pytest.mark.parametrize("name,call,table,action,rtype", CASES)
def test_3_foreign_owner_no_audit_and_row_survives(name, call, table, action, rtype):
    st, au = _store_for(table), _Audit()
    assert _run(call, st, au, "res-B", A) == 404
    assert au.calls == [], f"{name}: tuđi resurs ne sme proizvesti audit"
    assert any(r["id"] == "res-B" for r in st.rows), f"{name}: red korisnika B mora ostati"


@pytest.mark.parametrize("name,call,table,action,rtype", CASES)
def test_4_audit_sink_failure_does_not_break_mutation(name, call, table, action, rtype):
    """Otkaz u sinku ISPOD log_action -- pravi guard se izvršava."""
    import shared.audit_immutable as ai

    # F-V39-002: injector MORA biti sinhron. log_action zove
    # `await asyncio.to_thread(_build_and_insert, ...)`, pa async zamena u
    # radnoj niti samo VRATI coroutine objekat i nikad ne digne -- log_action
    # tada ide SUCCESS granom i vraca taj coroutine kao da je upis uspeo.
    # Dokazano: async injector telo se izvrsi 0 puta. `raised` ispod tvrdi
    # da je otkaz stvarno nastupio, pa test vise ne moze proci prazan.
    raised = []

    def _boom_sink(*a, **k):
        raised.append(1)
        raise RuntimeError("audit DB down")

    st = _store_for(table)
    with patch.object(ai, "_build_and_insert", _boom_sink):
        code = _run(call, st, ai.log_action, "res-A", A)
    assert raised, "sink otkaz se nije ni desio -- test bi bio prazan"
    assert code == 200, f"{name}: pad audit sinka ne sme dati {code}"
    assert not [r for r in st.rows if r["id"] == "res-A"], "red mora ostati obrisan"


def test_8_webhook_namespace_separation_both_directions():
    """webhooks -> "webhook"; user_webhooks -> "user_webhook". Nikad obrnuto."""
    import routers.integracije as ig_user

    st, au = _store_for("webhooks"), _Audit()
    _run(_webhook, st, au, "res-A", A)
    assert au.calls[0]["resource_type"] == "webhook"
    assert au.calls[0]["action"] == "integration_webhook_delete"

    st2, au2 = _store_for("user_webhooks"), _Audit()
    with patch.object(ig_user, "_get_supa", return_value=st2), \
         patch("shared.audit_immutable.log_action", au2):
        asyncio.run(ig_user.webhook_brisi("res-A", _http(), {"user_id": A}))
    assert au2.calls[0]["resource_type"] == "user_webhook"
    assert au2.calls[0]["action"] == "user_webhook_delete"

    assert au.calls[0]["resource_type"] != au2.calls[0]["resource_type"]
    assert au.calls[0]["resource_id"] == au2.calls[0]["resource_id"] == "res-A", (
        "isti ID u dve tabele -- razlikuje ih ISKLJUČIVO resource_type"
    )


def test_9_actions_registered():
    from shared.audit_immutable import AUDITABLE_ACTIONS
    for _, _, _, action, _ in CASES:
        assert action in AUDITABLE_ACTIONS

# -*- coding: utf-8 -*-
"""
V36 ruta 1 — kanonski audit za billing_entry_delete.

ZAŠTO AUDIT NIJE POSLE SELECT-A
Handler radi SELECT pa DELETE. SELECT proverava vlasništvo i preduslov
(`obracunato`), ali NIJE poslovni događaj: između njega i DELETE-a stavka može
biti fakturisana, pa DELETE nosi `.eq("obracunato", False)` i tada vraća 0
redova uz HTTP 409. Audit posle SELECT-a tvrdio bi brisanje koje se nije desilo.
Test 4 pokriva baš taj prozor.

RUTE 2 I 3 NISU OVDE
recurring_template_delete je BLOKIRAN: odbacuje rezultat DELETE-a, pa uslov
uspeha nije dokaziv. client_portal_upload_delete nije ni započet, po protokolu
zaustavljanja na prvom blokeru.
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
    """Modeluje i SELECT (maybe_single) i DELETE sa punim predikatima."""

    def __init__(self, rows):
        self.rows = list(rows)

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, store, table):
        self.s, self.t, self.f, self.op = store, table, {}, "select"

    def select(self, *a, **k):
        self.op = "select"
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, col, val):
        self.f[col] = val
        return self

    def maybe_single(self):
        return self

    def execute(self):
        hit = [r for r in self.s.rows
               if r.get("_t") == self.t and all(r.get(k) == v for k, v in self.f.items())]
        res = MagicMock()
        if self.op == "delete":
            for r in hit:
                self.s.rows.remove(r)
            res.data = hit
        else:
            res.data = hit[0] if hit else None      # maybe_single
        return res


class _Audit:
    def __init__(self):
        self.calls = []

    async def __call__(self, action, **kw):
        self.calls.append({"action": action, **kw})
        return "audit-id"


def _http():
    return _SReq(scope={"type": "http", "method": "DELETE", "headers": [], "query_string": b"",
                        "path": "/entries/x", "client": ("127.0.0.1", 1),
                        "app": MagicMock(), "state": MagicMock()})


def _store(rows=None):
    return _Store(rows if rows is not None else [
        {"_t": "billing_entries", "id": "e-A", "user_id": A, "obracunato": False},
        {"_t": "billing_entries", "id": "e-B", "user_id": B, "obracunato": False},
    ])


def _call(store, audit, eid, uid):
    import routers.billing as m
    with patch.object(m, "_get_supa", return_value=store), \
         patch("shared.audit_immutable.log_action", audit):
        return asyncio.run(m.billing_entry_delete(eid, _http(), {"user_id": uid}))


def _run(store, audit, eid, uid):
    try:
        _call(store, audit, eid, uid)
        return 200
    except HTTPException as e:
        return e.status_code


def test_1_success_emits_exactly_one_audit():
    st, au = _store(), _Audit()
    assert _run(st, au, "e-A", A) == 200
    assert len(au.calls) == 1
    c = au.calls[0]
    assert c["action"] == "billing_entry_delete"
    assert c["resource_type"] == "billing_entry"
    assert c["resource_id"] == "e-A"
    assert c["user_id"] == A
    assert "correlation_id" not in c
    assert not [r for r in st.rows if r["id"] == "e-A"]


def test_2_nonexistent_emits_no_audit():
    st, au = _store(), _Audit()
    assert _run(st, au, "ne-postoji", A) == 404
    assert au.calls == []


def test_3_foreign_entry_no_audit_and_row_survives():
    st, au = _store(), _Audit()
    assert _run(st, au, "e-B", A) == 404
    assert au.calls == [], "tuđa stavka ne sme proizvesti audit"
    assert any(r["id"] == "e-B" for r in st.rows), "stavka korisnika B mora ostati"


def test_4_already_invoiced_emits_no_audit():
    """SELECT prolazi vlasništvo, ali obracunato=True -> 409, bez audita."""
    st = _store([{"_t": "billing_entries", "id": "e-A", "user_id": A, "obracunato": True}])
    au = _Audit()
    assert _run(st, au, "e-A", A) == 409
    assert au.calls == [], "fakturisana stavka ne sme proizvesti audit"
    assert any(r["id"] == "e-A" for r in st.rows), "stavka mora ostati"


def test_5_audit_sink_failure_does_not_break_mutation():
    import shared.audit_immutable as ai

    # F-V39-002: injector MORA biti sinhron. log_action zove
    # `await asyncio.to_thread(_build_and_insert, ...)`, pa async zamena u
    # radnoj niti samo VRATI coroutine objekat i nikad ne digne -- log_action
    # tada ide SUCCESS granom i vraca taj coroutine kao da je upis uspeo.
    # Dokazano: async injector telo se izvrsi 0 puta. `raised` ispod tvrdi
    # da je otkaz stvarno nastupio, pa test vise ne moze proci prazan.
    raised = []

    def _boom(*a, **k):
        raised.append(1)
        raise RuntimeError("audit DB down")

    st = _store()
    with patch.object(ai, "_build_and_insert", _boom):
        code = _run(st, ai.log_action, "e-A", A)
    assert raised, "sink otkaz se nije ni desio -- test bi bio prazan"
    assert code == 200
    assert not [r for r in st.rows if r["id"] == "e-A"]


def test_6_action_registered():
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "billing_entry_delete" in AUDITABLE_ACTIONS

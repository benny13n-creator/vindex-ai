# -*- coding: utf-8 -*-
"""
V36-C — kanonski audit za recurring_template_delete.

ZAVISNOST OD V36-B
Ova ruta nije mogla dobiti audit dok nije imala zero-row guard: do V36-B je
DELETE rezultat bio odbačen, pa uspeh nije bio dokaziv i audit bi tvrdio
brisanje koje handler ne može da potvrdi. Test 5 vozi upravo taj prozor.

ZAŠTO NE POSLE SELECT-A
SELECT proverava vlasništvo i preduslov `aktivan`. Nije poslovni događaj --
između njega i DELETE-a red može nestati. Audit stoji posle guarda na DELETE-u.

BEST-EFFORT SE MERI NA PRAVOJ GRANICI
Otkaz se ubrizgava u _build_and_insert (sink ISPOD log_action), ne zamenom
log_action-a, jer bi zamena uklonila guard koji se dokazuje.
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
            res.data = hit[0] if hit else None
        return res


class _Audit:
    def __init__(self):
        self.calls = []

    async def __call__(self, action, **kw):
        self.calls.append({"action": action, **kw})
        return "audit-id"


def _http():
    return _SReq(scope={"type": "http", "method": "DELETE", "headers": [], "query_string": b"",
                        "path": "/billing/recurring/x", "client": ("127.0.0.1", 1),
                        "app": MagicMock(), "state": MagicMock()})


def _store(rows=None):
    return _Store(rows if rows is not None else [
        {"_t": "recurring_templates", "id": "t-A", "user_id": A, "aktivan": False},
        {"_t": "recurring_templates", "id": "t-B", "user_id": B, "aktivan": False},
    ])


def _run(store, audit, tid, uid):
    import routers.recurring as m
    with patch.object(m, "_get_supa", return_value=store), \
         patch("shared.audit_immutable.log_action", audit):
        try:
            asyncio.run(m.delete_recurring(tid, _http(), {"user_id": uid}))
            return 200
        except HTTPException as e:
            return e.status_code


def test_1_success_emits_exactly_one_audit():
    st, au = _store(), _Audit()
    assert _run(st, au, "t-A", A) == 200
    assert len(au.calls) == 1, f"tačno jedan audit, dobijeno {len(au.calls)}"
    c = au.calls[0]
    assert c["action"] == "recurring_template_delete"
    assert c["resource_type"] == "recurring_template"
    assert c["resource_id"] == "t-A"
    assert c["user_id"] == A
    assert "correlation_id" not in c, "correlation se auto-izvodi"
    assert not [r for r in st.rows if r["id"] == "t-A"]


def test_2_nonexistent_emits_no_audit():
    st, au = _store(), _Audit()
    assert _run(st, au, "ne-postoji", A) == 404
    assert au.calls == []


def test_3_foreign_template_no_audit_and_row_survives():
    st, au = _store(), _Audit()
    assert _run(st, au, "t-B", A) == 404
    assert au.calls == [], "tuđi šablon ne sme proizvesti audit"
    assert any(r["id"] == "t-B" for r in st.rows)


def test_4_active_template_409_no_audit():
    st = _store([{"_t": "recurring_templates", "id": "t-A", "user_id": A, "aktivan": True}])
    au = _Audit()
    assert _run(st, au, "t-A", A) == 409
    assert au.calls == [], "aktivan šablon ne sme proizvesti audit"
    assert any(r["id"] == "t-A" for r in st.rows)


def test_5_toctou_zero_row_emits_no_audit():
    """SELECT prođe, DELETE ne pogodi ništa -> 404 i NULA audita.

    Bez V36-B guarda ovaj put bi vratio uspeh, a audit bi tvrdio brisanje koje
    se nije desilo. To je razlog zašto je audit čekao guard.
    """
    import routers.recurring as m

    st, au = _store(), _Audit()
    real_table = st.table

    def _vanishing(name):
        q = real_table(name)
        orig = q.execute

        def _exec():
            if q.op == "delete":
                st.rows.clear()
            return orig()
        q.execute = _exec
        return q

    st.table = _vanishing
    with patch.object(m, "_get_supa", return_value=st), \
         patch("shared.audit_immutable.log_action", au):
        try:
            asyncio.run(m.delete_recurring("t-A", _http(), {"user_id": A}))
            code = 200
        except HTTPException as e:
            code = e.status_code
    assert code == 404
    assert au.calls == [], "zero-row DELETE ne sme proizvesti audit"


def test_6_audit_sink_failure_does_not_break_delete():
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
        code = _run(st, ai.log_action, "t-A", A)
    assert raised, "sink otkaz se nije ni desio -- test bi bio prazan"
    assert code == 200, f"pad audit sinka ne sme dati {code}"
    assert not [r for r in st.rows if r["id"] == "t-A"], "red mora ostati obrisan"


def test_7_action_registered():
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "recurring_template_delete" in AUDITABLE_ACTIONS

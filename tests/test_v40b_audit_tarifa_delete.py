# -*- coding: utf-8 -*-
"""
V40-B2 — kanonski audit za tarifa_delete.

ZAŠTO ZASEBNA AKCIJA, A NE tarifa_update
Uklanjanje tarife ima sopstveni rani return i ne menja iznos -- emitovanje
`tarifa_update` tvrdilo bi izmenu koja se nije desila. Test 9 drži tu granicu.

ZAŠTO AUDIT STOJI UNUTAR `if existing`
Idempotentna grana (nema tarife) vraća removed:True ali NIJE poslovni događaj:
ništa nije obrisano. Audit tamo bi izmislio brisanje. Test 4 to zaključava.

GRANICA USPEHA
Zero-row guard iz V40-A (F-V38-001). Pre njega uspeh nije bio dokaziv, pa audit
nije ni mogao biti bezbedno postavljen -- zato su A i B razdvojeni sprintovi.

F-V39-002: injector u testu 6 je SINHRON, jer log_action zove
`await asyncio.to_thread(_build_and_insert, ...)`.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request as _SReq

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

A, B = "advokat-A", "advokat-B"
K = "klijent-1"
T = "tarifa-1"


class _Store:
    def __init__(self, rows=None, vanish_before_delete=False):
        self.rows = rows if rows is not None else [
            {"_t": "tarife", "id": T, "user_id": A, "klijent_id": K, "tarifa_po_satu": 5000.0},
        ]
        self.vanish = vanish_before_delete

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, s, t):
        self.s, self.t, self.f, self.op = s, t, {}, "select"

    def select(self, *a, **k):
        self.op = "select"
        return self

    def update(self, p):
        self.op, self.patch = "update", p
        return self

    def insert(self, r):
        self.op, self.row = "insert", r
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, c, v):
        self.f[c] = v
        return self

    def limit(self, n):
        return self

    def execute(self):
        res = MagicMock()
        if self.op == "delete":
            if self.s.vanish:
                self.s.rows = [r for r in self.s.rows if r.get("_t") != "tarife"]
            hit = [r for r in self.s.rows
                   if r.get("_t") == self.t and all(r.get(k) == v for k, v in self.f.items())]
            for r in hit:
                self.s.rows.remove(r)
            res.data = hit
        elif self.op == "select":
            res.data = [r for r in self.s.rows
                        if r.get("_t") == self.t and all(r.get(k) == v for k, v in self.f.items())]
        else:
            res.data = [{"id": T, "klijent_id": K, "tarifa_po_satu": 1.0}]
        return res


class _Audit:
    def __init__(self):
        self.calls = []

    async def __call__(self, action, **kw):
        self.calls.append({"action": action, **kw})
        return "audit-id"


def _http():
    return _SReq(scope={"type": "http", "method": "PUT", "headers": [], "query_string": b"",
                        "path": "/api/tarife/klijent/x", "client": ("127.0.0.1", 1),
                        "app": MagicMock(), "state": MagicMock()})


def _remove(store, audit, uid=A, klijent_id=K):
    import routers.tarife as m
    body = m.KlijentTarifaReq(tarifa_po_satu=None)
    with patch.object(m, "_get_supa", return_value=store), \
         patch("shared.audit_immutable.log_action", audit):
        try:
            return asyncio.run(m.put_klijent_tarifa(klijent_id, body, _http(), {"user_id": uid})), 200
        except HTTPException as e:
            return None, e.status_code


def test_1_successful_removal_emits_exactly_one_audit():
    st, au = _Store(), _Audit()
    out, code = _remove(st, au)
    assert code == 200 and out["removed"] is True
    assert len(au.calls) == 1
    c = au.calls[0]
    assert c["action"] == "tarifa_delete"
    assert c["resource_type"] == "tarifa"
    assert c["user_id"] == A


def test_2_resource_id_is_the_tarifa_row():
    st, au = _Store(), _Audit()
    _remove(st, au)
    assert au.calls[0]["resource_id"] == T
    assert au.calls[0]["resource_id"] != K, "klijent je vlasnik odnosa, ne resurs"
    assert au.calls[0]["metadata"]["klijent_id"] == K


def test_3_toctou_zero_row_emits_no_audit():
    st, au = _Store(vanish_before_delete=True), _Audit()
    out, code = _remove(st, au)
    assert code == 404
    assert au.calls == [], "nepotvrđeno brisanje ne sme proizvesti audit"


def test_4_idempotent_no_tarifa_emits_no_audit():
    """removed:True bez ijednog obrisanog reda NIJE poslovni događaj."""
    st, au = _Store(rows=[]), _Audit()
    out, code = _remove(st, au)
    assert code == 200 and out["removed"] is True
    assert au.calls == [], "ništa nije obrisano -> nema šta da se auditira"


def test_5_foreign_tarifa_emits_no_audit_and_survives():
    st, au = _Store(), _Audit()
    out, code = _remove(st, au, uid=B)
    assert code == 200
    assert au.calls == []
    assert any(r["_t"] == "tarife" for r in st.rows), "tuđa tarifa mora ostati"


def test_6_audit_sink_failure_does_not_break_removal():
    """Sinhroni injector: log_action zove _build_and_insert kroz to_thread."""
    import shared.audit_immutable as ai

    raised = []

    def _boom(*a, **k):
        raised.append(1)
        raise RuntimeError("audit DB down")

    st = _Store()
    with patch.object(ai, "_build_and_insert", _boom):
        out, code = _remove(st, ai.log_action)
    assert raised, "sink otkaz se nije ni desio -- test bi bio prazan"
    assert code == 200, f"pad audit sinka ne sme dati {code}"
    assert not [r for r in st.rows if r["_t"] == "tarife"], "brisanje mora opstati"


def test_7_second_removal_emits_no_second_audit():
    st, au = _Store(), _Audit()
    _remove(st, au)
    assert len(au.calls) == 1
    _remove(st, au)
    assert len(au.calls) == 1, "idempotentni drugi poziv ne sme dodati audit"


def test_8_namespace_and_correlation():
    st, au = _Store(), _Audit()
    _remove(st, au)
    c = au.calls[0]
    assert c["action"] != "tarifa_update", "brisanje nije izmena iznosa"
    assert "correlation_id" not in c, "correlation se auto-izvodi"


def test_9_update_branch_still_emits_tarifa_update_only():
    """Dve grane, dve akcije -- nijedna ne sme curiti u drugu."""
    import routers.tarife as m
    st, au = _Store(), _Audit()
    body = m.KlijentTarifaReq(tarifa_po_satu=7000.0)
    with patch.object(m, "_get_supa", return_value=st), \
         patch("shared.audit_immutable.log_action", au):
        asyncio.run(m.put_klijent_tarifa(K, body, _http(), {"user_id": A}))
    assert [c["action"] for c in au.calls] == ["tarifa_update"]


def test_10_action_registered():
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "tarifa_delete" in AUDITABLE_ACTIONS
    assert "tarifa_update" in AUDITABLE_ACTIONS

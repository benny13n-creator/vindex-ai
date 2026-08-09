# -*- coding: utf-8 -*-
"""
V38 — kanonski audit za tarifa_update.

TRI GRANE, DVE AUDITOVANE
put_klijent_tarifa ima:

  1. body.tarifa_po_satu is None -> DELETE (rezultat odbačen) -> rani return
  2. postojeća tarifa            -> UPDATE -> guard -> return
  3. nema tarife                 -> INSERT -> guard -> return

Grane 2 i 3 stižu do `if not r.data` guarda i tek tamo je uspeh dokazan. Grana 1
NIJE auditovana: to je uklanjanje tarife, zaseban poslovni događaj sa ranim
return-om i odbačenim DELETE rezultatom (F-V38-001). Test 7 tvrdi da ta grana ne
emituje `tarifa_update` -- ne zato što je pokrivena drugde, nego zato što bi
lagala o tome šta se desilo.

RESOURCE_ID JE ID TARIFE, NE KLIJENTA
Klijent je vlasnik odnosa; promenjen resurs je red u `tarife`. Test 4 to tvrdi
eksplicitno, jer je klijent_id ovde najprivlačnija pogrešna vrednost.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request as _SReq

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

A = "user-A"
KLIJENT = "klijent-777"
TARIFA_ID = "tarifa-111"


class _Store:
    def __init__(self, existing=None, mutate_empty=False):
        self.existing = existing          # postojeći red ili None
        self.mutate_empty = mutate_empty  # UPDATE/INSERT vrati []
        self.deleted = []
        self.ops = []

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, store, table):
        self.s, self.t, self.op, self.f = store, table, "select", {}

    def select(self, *a, **k):
        self.op = "select"
        return self

    def update(self, patch):
        self.op, self.patch = "update", patch
        return self

    def insert(self, row):
        self.op, self.row = "insert", row
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
        self.s.ops.append(self.op)
        res = MagicMock()
        if self.op == "select":
            res.data = [{"id": TARIFA_ID}] if self.s.existing else []
        elif self.op == "delete":
            self.s.deleted.append(self.f.get("id"))
            res.data = [{"id": self.f.get("id")}]
        else:  # update / insert
            if self.s.mutate_empty:
                res.data = []
            else:
                val = getattr(self, "patch", getattr(self, "row", {})).get("tarifa_po_satu")
                res.data = [{"id": TARIFA_ID, "klijent_id": KLIJENT, "tarifa_po_satu": val}]
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


def _run(store, audit, iznos=5000.0):
    import routers.tarife as m
    body = m.KlijentTarifaReq(tarifa_po_satu=iznos)
    with patch.object(m, "_get_supa", return_value=store), \
         patch("shared.audit_immutable.log_action", audit):
        try:
            return asyncio.run(m.put_klijent_tarifa(KLIJENT, body, _http(), {"user_id": A})), 200
        except HTTPException as e:
            return None, e.status_code


def test_1_update_branch_emits_exactly_one_audit():
    st, au = _Store(existing=True), _Audit()
    out, code = _run(st, au)
    assert code == 200
    assert "update" in st.ops, "mora ići kroz UPDATE granu"
    assert len(au.calls) == 1
    c = au.calls[0]
    assert c["action"] == "tarifa_update"
    assert c["resource_type"] == "tarifa"
    assert c["user_id"] == A
    assert "correlation_id" not in c


def test_2_insert_branch_emits_exactly_one_audit():
    st, au = _Store(existing=None), _Audit()
    out, code = _run(st, au)
    assert code == 200
    assert "insert" in st.ops, "mora ići kroz INSERT granu"
    assert len(au.calls) == 1
    assert au.calls[0]["action"] == "tarifa_update"


def test_3_resource_id_is_the_tarifa_row_id():
    st, au = _Store(existing=True), _Audit()
    _run(st, au)
    assert au.calls[0]["resource_id"] == TARIFA_ID


def test_4_resource_id_is_not_klijent_id():
    """Najprivlačnija pogrešna vrednost -- klijent je vlasnik, ne resurs."""
    st, au = _Store(existing=True), _Audit()
    _run(st, au)
    assert au.calls[0]["resource_id"] != KLIJENT, (
        "resource_id mora biti ID tarife, ne klijenta"
    )


def test_5_mutation_returning_no_row_emits_no_audit():
    """UPDATE/INSERT vrati [] -> 500 -> nula audita."""
    st, au = _Store(existing=True, mutate_empty=True), _Audit()
    out, code = _run(st, au)
    assert code == 500
    assert au.calls == [], "neuspela mutacija ne sme proizvesti audit"


def test_6_audit_sink_failure_does_not_break_update():
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

    st = _Store(existing=True)
    with patch.object(ai, "_build_and_insert", _boom):
        out, code = _run(st, ai.log_action)
    assert raised, "sink otkaz se nije ni desio -- test bi bio prazan"
    assert code == 200, f"pad audit sinka ne sme dati {code}"
    assert "update" in st.ops


def test_7_removal_branch_emits_no_tarifa_update():
    """F-V38-001: uklanjanje tarife je zaseban događaj, nije tarifa_update.

    Emitovanje `tarifa_update` ovde tvrdilo bi izmenu iznosa koja se nije desila.

    V40-B2 ISPRAVKA TVRDNJE (ne slabljenje): originalna verzija je tvrdila
    `au.calls == []`, tj. "nula audita uopšte". To je bilo tačno samo dok grana
    brisanja nije imala SVOJ audit -- vezivalo je test za tadašnje stanje
    implementacije umesto za trajni invarijant. Kad je V40-B2 dodao
    `tarifa_delete`, tvrdnja je pukla iako se ništa što ovaj test štiti nije
    pokvarilo. Trajni invarijant je: grana brisanja ne sme emitovati
    `tarifa_update`. Isti obrazac greške zabeležen je i u V31->V35 i
    V36-B->V36-C; istorija je sačuvana u git-u.
    """
    import routers.tarife as m

    st, au = _Store(existing=True), _Audit()
    body = m.KlijentTarifaReq(tarifa_po_satu=None)
    with patch.object(m, "_get_supa", return_value=st), \
         patch("shared.audit_immutable.log_action", au):
        out = asyncio.run(m.put_klijent_tarifa(KLIJENT, body, _http(), {"user_id": A}))

    assert out.get("removed") is True
    assert TARIFA_ID in st.deleted, "red JESTE obrisan"
    assert [c for c in au.calls if c["action"] == "tarifa_update"] == [], (
        "uklanjanje ne sme emitovati tarifa_update"
    )


def test_8_cardinality_one_event_one_audit():
    st, au = _Store(existing=True), _Audit()
    _run(st, au)
    assert len(au.calls) == 1
    _run(st, au)
    assert len(au.calls) == 2, "svaki uspešan update je sopstveni događaj"


def test_9_action_registered():
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "tarifa_update" in AUDITABLE_ACTIONS

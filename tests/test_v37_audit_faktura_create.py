# -*- coding: utf-8 -*-
"""
V37 — kanonski audit za faktura_create.

NAJSLOŽENIJA GRANICA USPEHA U CELOM V33-V39 SETU
Handler ima tri izlaza posle INSERT-a fakture:

  1. except Exception -> rollback DELETE fakture -> raise 500
     (ako i rollback padne: ORPHANED, i dalje raise 500)
  2. updated_count < len(entries) -> rollback DELETE fakture -> raise 409
  3. uspeh -> logger.info -> return

INSERT fakture NIJE dokaz uspeha: faktura postoji i u granama 1 i 2, gde se
potom briše. Jedini dokaz je prolazak kroz updated_count guard. Audit stoji tek
tamo; obe rollback grane dižu izuzetak pa su strukturno nedostižne za audit.

JEDAN ZAPIS PO FAKTURI, NE PO STAVCI
N billing_entries su tehnički redovi jednog poslovnog događaja -- to dokazuje
sam rollback: ako UPDATE stavki padne, faktura se briše. Test 7 to tvrdi sa N=3.
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


class _Store:
    """Modeluje SELECT/INSERT/UPDATE/DELETE nad billing_entries i fakture."""

    def __init__(self, entries, update_hits=None, update_raises=False,
                 rollback_raises=False):
        self.entries = list(entries)
        self.fakture = []
        self.deleted_fakture = []
        self.update_hits = update_hits          # None -> sve stavke
        self.update_raises = update_raises
        self.rollback_raises = rollback_raises

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, store, table):
        self.s, self.t, self.op, self.f = store, table, "select", {}

    def select(self, *a, **k):
        self.op = "select"
        return self

    def insert(self, row):
        self.op, self.row = "insert", row
        return self

    def update(self, patch):
        self.op = "update"
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, c, v):
        self.f[c] = v
        return self

    def in_(self, c, vals):
        self.f[c] = vals
        return self

    def maybe_single(self):
        return self

    def execute(self):
        res = MagicMock()
        if self.t == "billing_entries":
            if self.op == "select":
                res.data = list(self.s.entries)
            elif self.op == "update":
                if self.s.update_raises:
                    raise RuntimeError("update failed")
                n = self.s.update_hits if self.s.update_hits is not None else len(self.s.entries)
                res.data = self.s.entries[:n]
        elif self.t == "fakture":
            if self.op == "insert":
                row = {"id": "fak-1", **self.row}
                self.s.fakture.append(row)
                res.data = [row]
            elif self.op == "delete":
                if self.s.rollback_raises:
                    raise RuntimeError("rollback failed")
                self.s.deleted_fakture.append(self.f.get("id"))
                self.s.fakture = [f for f in self.s.fakture if f["id"] != self.f.get("id")]
                res.data = [{"id": self.f.get("id")}]
        return res


class _Audit:
    def __init__(self):
        self.calls = []

    async def __call__(self, action, **kw):
        self.calls.append({"action": action, **kw})
        return "audit-id"


def _http():
    return _SReq(scope={"type": "http", "method": "POST", "headers": [], "query_string": b"",
                        "path": "/billing/faktura", "client": ("127.0.0.1", 1),
                        "app": MagicMock(), "state": MagicMock()})


def _entries(n=2):
    return [{"id": f"e-{i}", "user_id": A, "predmet_id": "p-1",
             "obracunato": False, "iznos_rsd": 1000.0} for i in range(n)]


def _run(store, audit, n=2):
    import routers.billing as m
    req = m.FakturaReq(predmet_id="p-1", entry_ids=[f"e-{i}" for i in range(n)],
                       klijent_naziv="Klijent d.o.o.")
    with patch.object(m, "_get_supa", return_value=store), \
         patch.object(m, "_sledeci_broj_fakture", new=_broj), \
         patch("shared.audit_immutable.log_action", audit):
        try:
            asyncio.run(m.faktura_create(req, _http(), {"user_id": A}))
            return 200
        except HTTPException as e:
            return e.status_code


async def _broj(supa, uid):
    return "2026-0001"


def test_1_success_emits_exactly_one_audit():
    st, au = _Store(_entries()), _Audit()
    assert _run(st, au) == 200
    assert len(au.calls) == 1
    c = au.calls[0]
    assert c["action"] == "faktura_create"
    assert c["resource_type"] == "faktura"
    assert c["resource_id"] == "fak-1"
    assert c["user_id"] == A
    assert "correlation_id" not in c


def test_2_update_failure_rollback_emits_no_audit():
    """UPDATE stavki padne -> faktura se briše -> 500, bez audita."""
    st, au = _Store(_entries(), update_raises=True), _Audit()
    assert _run(st, au) == 500
    assert au.calls == [], "rollback grana ne sme proizvesti audit"
    assert "fak-1" in st.deleted_fakture, "faktura mora biti rollbackovana"


def test_3_orphaned_branch_emits_no_audit():
    """UPDATE padne I rollback DELETE padne -> ORPHANED -> 500, bez audita.

    Faktura ostaje u bazi bez povezanih stavki. Audit bi taj kvar overio kao
    uspešno kreiranje.
    """
    st, au = _Store(_entries(), update_raises=True, rollback_raises=True), _Audit()
    assert _run(st, au) == 500
    assert au.calls == [], "ORPHANED grana ne sme proizvesti audit"
    assert st.fakture, "faktura je ostala -- to je ORPHANED stanje"


def test_4_partial_update_conflict_emits_no_audit():
    """updated_count < len(entries) -> 409 + rollback, bez audita."""
    st, au = _Store(_entries(3), update_hits=2), _Audit()
    assert _run(st, au, n=3) == 409
    assert au.calls == [], "delimičan UPDATE ne sme proizvesti audit"
    assert "fak-1" in st.deleted_fakture


def test_5_audit_sink_failure_does_not_break_faktura():
    import shared.audit_immutable as ai

    async def _boom(*a, **k):
        raise RuntimeError("audit DB down")

    st = _Store(_entries())
    with patch.object(ai, "_build_and_insert", _boom):
        code = _run(st, ai.log_action)
    assert code == 200, f"pad audit sinka ne sme dati {code}"
    assert st.fakture, "faktura mora ostati kreirana"
    assert st.deleted_fakture == [], "ne sme biti rollbacka"


def test_6_no_entries_emits_no_audit():
    st, au = _Store([]), _Audit()
    assert _run(st, au) == 404
    assert au.calls == []


def test_7_cardinality_one_audit_per_faktura_not_per_entry():
    """Tri stavke -> jedna faktura -> JEDAN audit."""
    st, au = _Store(_entries(3)), _Audit()
    assert _run(st, au, n=3) == 200
    assert len(au.calls) == 1, f"jedan zapis po fakturi, dobijeno {len(au.calls)}"
    assert au.calls[0]["resource_id"] == "fak-1"


def test_8_action_registered():
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "faktura_create" in AUDITABLE_ACTIONS

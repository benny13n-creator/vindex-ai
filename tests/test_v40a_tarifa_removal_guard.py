# -*- coding: utf-8 -*-
"""
V40-A / F-V38-001 — zero-row guard za uklanjanje tarife klijenta.

TRI DEFEKTA U JEDNOJ GRANI
`PUT /api/tarife/klijent/{klijent_id}` sa `tarifa_po_satu = null`:

  1. rezultat DELETE-a se odbacivao -> uspeh nedokaziv
  2. `user_id` je stajao samo u SELECT-u iznad, ne u samoj DELETE naredbi
  3. `removed: True` se vraćao bezuslovno

Test 4 vozi TOCTOU prozor koji je to činio vidljivim: SELECT nađe red, DELETE
ne zatekne nijedan, ruta je i dalje tvrdila da je tarifa uklonjena.

ŠTA NAMERNO NIJE PROMENJENO
Grana bez ijedne tarife (`existing is None`) i dalje vraća removed:True. PUT sa
null znači "neka ne postoji tarifa", pa je brisanje nepostojeće idempotentan
no-op. 404 bi ovde bio izmena API ugovora (F-V40-001). Test 5 to zaključava da
neko kasnije ne bi "popravio" i to.
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
    """DELETE uklanja red samo ako SVI .eq() predikati poklope."""

    def __init__(self, rows=None, vanish_before_delete=False):
        self.rows = rows if rows is not None else [
            {"_t": "tarife", "id": T, "user_id": A, "klijent_id": K, "tarifa_po_satu": 5000.0},
        ]
        self.vanish = vanish_before_delete
        self.deletes = []

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
            self.s.deletes.append(dict(self.f))
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


def _http():
    return _SReq(scope={"type": "http", "method": "PUT", "headers": [], "query_string": b"",
                        "path": "/api/tarife/klijent/x", "client": ("127.0.0.1", 1),
                        "app": MagicMock(), "state": MagicMock()})


def _remove(store, uid=A, klijent_id=K):
    import routers.tarife as m
    body = m.KlijentTarifaReq(tarifa_po_satu=None)
    with patch.object(m, "_get_supa", return_value=store):
        try:
            return asyncio.run(m.put_klijent_tarifa(klijent_id, body, _http(), {"user_id": uid})), 200
        except HTTPException as e:
            return None, e.status_code


def test_1_successful_removal_deletes_the_row():
    st = _Store()
    out, code = _remove(st)
    assert code == 200
    assert out["removed"] is True
    assert not [r for r in st.rows if r["_t"] == "tarife"], "red mora biti obrisan"


def test_2_owner_predicate_is_inside_the_delete_statement():
    """Vlasništvo iz prethodnog SELECT-a nije dokaz za naknadni DELETE."""
    st = _Store()
    _remove(st)
    assert st.deletes, "DELETE se mora izvršiti"
    assert st.deletes[0].get("user_id") == A, (
        "user_id mora biti predikat SAME DELETE naredbe, ne samo SELECT-a"
    )
    assert st.deletes[0].get("id") == T


def test_3_foreign_tarifa_is_never_reached():
    """B ne vidi tarifu korisnika A u SELECT-u -> nema šta da briše."""
    st = _Store()
    out, code = _remove(st, uid=B)
    assert code == 200 and out["removed"] is True
    assert st.deletes == [], "tuđa tarifa ne sme ni doći do DELETE-a"
    assert any(r["_t"] == "tarife" for r in st.rows), "tuđa tarifa mora ostati"


def test_4_toctou_zero_row_delete_is_now_404():
    """SELECT nađe red, DELETE ne zatekne nijedan -> removed:True bi bila laž."""
    st = _Store(vanish_before_delete=True)
    out, code = _remove(st)
    assert code == 404, f"zero-row DELETE mora biti prijavljen, dobijeno {code}"
    assert out is None


def test_5_no_tarifa_at_all_stays_idempotent_200():
    """NAMERNO nepromenjeno (F-V40-001): PUT null nad nepostojećom tarifom.

    Nije greška nego no-op; 404 bi ovde bio izmena API ugovora.
    """
    st = _Store(rows=[])
    out, code = _remove(st)
    assert code == 200
    assert out == {"ok": True, "removed": True}
    assert st.deletes == [], "nema šta da se briše"


def test_6_second_removal_cannot_report_a_second_success():
    st = _Store()
    _, code1 = _remove(st)
    assert code1 == 200
    out2, code2 = _remove(st)
    # Red više ne postoji -> SELECT prazan -> idempotentna grana, bez DELETE-a.
    assert code2 == 200
    assert len(st.deletes) == 1, "drugi poziv ne sme izvršiti drugi DELETE"


def test_7_update_branch_unaffected():
    """Regresioni pojas: izmena iznosa i dalje radi i ne dira granu brisanja."""
    import routers.tarife as m
    st = _Store()
    body = m.KlijentTarifaReq(tarifa_po_satu=7000.0)
    with patch.object(m, "_get_supa", return_value=st):
        out = asyncio.run(m.put_klijent_tarifa(K, body, _http(), {"user_id": A}))
    assert out["ok"] is True
    assert st.deletes == [], "grana izmene ne sme brisati"

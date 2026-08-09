# -*- coding: utf-8 -*-
"""
V36-B — zero-row guard za recurring.py::delete_recurring (F-V36-001).

DEFEKT
Handler je izvršavao owner-scoped DELETE i ODBACIVAO rezultat:

    await _db(lambda: supa.table("recurring_templates").delete()
        .eq("id", template_id).eq("user_id", uid).execute())

SELECT iznad dokazuje da je red postojao i da je pozivaočev, ali NE dokazuje da
je obrisan. Između SELECT-a i DELETE-a red može nestati, a handler bi svejedno
vratio uspeh.

Ovo je treći slučaj iste klase: V30 ga je našao u komentari i integrations, V31
ih zatvorio. Ovde je promakao statičkoj proveri u V29 jer handler JESTE imao
guard -- samo na pogrešnoj operaciji.

OBIM
Bez audita. V36 ruta 2 dobija log_action tek kada je uspeh dokaziv, što je
upravo ono što ovaj commit omogućava. Test 4 to prikucava.
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


def _http():
    return _SReq(scope={"type": "http", "method": "DELETE", "headers": [], "query_string": b"",
                        "path": "/billing/recurring/x", "client": ("127.0.0.1", 1),
                        "app": MagicMock(), "state": MagicMock()})


def _store(rows=None):
    return _Store(rows if rows is not None else [
        {"_t": "recurring_templates", "id": "t-A", "user_id": A, "aktivan": False},
        {"_t": "recurring_templates", "id": "t-B", "user_id": B, "aktivan": False},
    ])


def _run(store, tid, uid):
    import routers.recurring as m
    with patch.object(m, "_get_supa", return_value=store):
        try:
            asyncio.run(m.delete_recurring(tid, _http(), {"user_id": uid}))
            return 200
        except HTTPException as e:
            return e.status_code


def test_1_own_template_deleted():
    st = _store()
    assert _run(st, "t-A", A) == 200
    assert not [r for r in st.rows if r["id"] == "t-A"], "red mora biti obrisan"


def test_2_nonexistent_is_404_and_deletes_nothing():
    st = _store()
    assert _run(st, "ne-postoji", A) == 404
    assert len(st.rows) == 2, "ništa se ne sme obrisati"


def test_3_foreign_template_is_404_and_row_survives():
    st = _store()
    assert _run(st, "t-B", A) == 404
    assert any(r["id"] == "t-B" for r in st.rows), "šablon korisnika B mora ostati"


def test_4_zero_row_after_valid_select_is_404():
    """Srž F-V36-001: SELECT pronađe red, ali DELETE ne pogodi ništa.

    Modeluje TOCTOU prozor -- red nestane između dve operacije. Stari kod je i
    tada vraćao uspeh; guard sada zahteva dokaz iz samog DELETE-a.
    """
    import routers.recurring as m

    st = _store()
    real_table = st.table

    def _vanishing(name):
        q = real_table(name)
        orig = q.execute

        def _exec():
            if q.op == "delete":
                st.rows.clear()          # red nestao pre DELETE-a
            return orig()
        q.execute = _exec
        return q

    st.table = _vanishing
    with patch.object(m, "_get_supa", return_value=st):
        try:
            asyncio.run(m.delete_recurring("t-A", _http(), {"user_id": A}))
            code = 200
        except HTTPException as e:
            code = e.status_code
    assert code == 404, f"DELETE bez pogođenog reda mora biti 404, dobijeno {code}"


def test_5_active_template_still_409():
    """Postojeći preduslov nije promenjen."""
    st = _store([{"_t": "recurring_templates", "id": "t-A", "user_id": A, "aktivan": True}])
    assert _run(st, "t-A", A) == 409
    assert any(r["id"] == "t-A" for r in st.rows)


def test_6_zero_row_guard_survives():
    """Guard mora ostati prisutan i posle kasnijih izmena handlera.

    ISTORIJA: u V36-B je glasila "log_action ne sme postojati" -- tačno za taj
    commit, koji je namerno razdvojio HTTP guard od audita. V36-C je audit dodao
    po planu, pa je formulacija istekla. Zamenjena je invarijantom koja traje:
    guard koji V36-B uvodi i dalje stoji. Original je u istoriji na eed65e75.

    Ovo je drugi put da je "nema audita" tvrdnja vezana za handler umesto za
    commit (prvi: test_v31_zero_row_guard). Buduće guard-only faze treba da
    tvrde prisustvo guarda, ne odsustvo audita.
    """
    import inspect
    import routers.recurring as m
    src = inspect.getsource(m.delete_recurring)
    assert "if not r.data" in src, "delete_recurring je izgubio zero-row guard"
    assert "404" in src, "delete_recurring više ne vraća 404 na zero-row"

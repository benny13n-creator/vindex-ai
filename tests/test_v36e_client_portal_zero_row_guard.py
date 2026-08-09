# -*- coding: utf-8 -*-
"""
V36-E — zero-row guard za client_portal_obrisi_upload (F-V36-002).

DEFEKT
Handler je izvršavao owner-scoped DELETE i ODBACIVAO rezultat, pa je vraćao
{"ok": True} i kad nijedan red nije poklopljen.

Četvrti slučaj iste klase: V31 (komentari, integrations), V36-B (recurring),
sada client_portal.

ZAŠTO JE OVDE GORE NEGO KOD OSTALIH
Storage brisanje se izvršava PRE DB DELETE-a i namerno je ne-fatalno. U
redosledu "storage uspeh -> DB nula redova" stari kod je vraćao 200 iako je fajl
uklonjen a metapodatak ostao -- korisnik dobija potvrdu brisanja, a red i dalje
pokazuje na nepostojeći objekat. Test 4 vozi tačno taj redosled.

OBIM
Guard-only. Bez audita, bez promene storage semantike, bez promene redosleda.
Storage-pre-DB ostaje kao zabeleženo arhitektonsko ograničenje.
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


class _Store:
    def __init__(self, rows):
        self.rows = list(rows)
        self.storage_removed = []
        self.storage = _Storage(self)     # instancni atribut, ne property

    def table(self, name):
        return _Q(self, name)


class _Storage:
    def __init__(self, store):
        self.s = store

    def from_(self, bucket):
        self.bucket = bucket
        return self

    def remove(self, paths):
        self.s.storage_removed.extend(paths)
        return MagicMock()


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
                        "path": "/api/client-portal/uploads/x", "client": ("127.0.0.1", 1),
                        "app": MagicMock(), "state": MagicMock()})


def _store(rows=None):
    return _Store(rows if rows is not None else [
        {"_t": "client_portal_uploads", "id": "u-A", "advokat_user_id": A, "storage_path": "p/u-A"},
        {"_t": "client_portal_uploads", "id": "u-B", "advokat_user_id": B, "storage_path": "p/u-B"},
    ])


def _run(store, uid_param, uid):
    import routers.client_portal as m
    with patch.object(m, "_get_supa", return_value=store):
        try:
            asyncio.run(m.client_portal_obrisi_upload(uid_param, _http(), {"user_id": uid}))
            return 200
        except HTTPException as e:
            return e.status_code


def test_1_own_upload_deleted():
    st = _store()
    assert _run(st, "u-A", A) == 200
    assert not [r for r in st.rows if r["id"] == "u-A"], "red mora biti obrisan"
    assert "p/u-A" in st.storage_removed, "storage objekat mora biti uklonjen"


def test_2_nonexistent_is_404_and_deletes_nothing():
    st = _store()
    assert _run(st, "ne-postoji", A) == 404
    assert len(st.rows) == 2
    assert st.storage_removed == [], "SELECT guard staje pre storage-a"


def test_3_foreign_upload_is_404_and_row_survives():
    st = _store()
    assert _run(st, "u-B", A) == 404
    assert any(r["id"] == "u-B" for r in st.rows), "upload advokata B mora ostati"
    assert st.storage_removed == [], "tuđi storage objekat se ne sme dirati"


def test_4_toctou_zero_row_after_storage_removal_is_404():
    """Srž F-V36-002 i najgori redosled u ovom setu.

    SELECT prođe, storage brisanje se IZVRŠI, pa DB DELETE ne pogodi ništa.
    Stari kod je vraćao 200 -- korisnik dobija potvrdu, fajl je nestao, a
    metapodatak ostaje i pokazuje na nepostojeći objekat.
    """
    import routers.client_portal as m

    st = _store()
    real_table = st.table

    def _vanishing(name):
        q = real_table(name)
        orig = q.execute

        def _exec():
            if q.op == "delete":
                st.rows.clear()      # red nestao posle storage brisanja
            return orig()
        q.execute = _exec
        return q

    st.table = _vanishing
    with patch.object(m, "_get_supa", return_value=st):
        try:
            asyncio.run(m.client_portal_obrisi_upload("u-A", _http(), {"user_id": A}))
            code = 200
        except HTTPException as e:
            code = e.status_code

    assert code == 404, f"nula obrisanih redova mora biti 404, dobijeno {code}"
    assert "p/u-A" in st.storage_removed, (
        "storage JESTE obrisan pre DB-a -- to ograničenje V36-E namerno ne menja"
    )


def test_5_storage_failure_remains_non_fatal():
    """Postojeća semantika: pad storage-a ne prekida brisanje."""
    import routers.client_portal as m

    st = _store()

    class _BadStorage:
        def from_(self, b):
            return self

        def remove(self, paths):
            raise RuntimeError("storage down")

    st.storage = _BadStorage()
    try:
        with patch.object(m, "_get_supa", return_value=st):
            asyncio.run(m.client_portal_obrisi_upload("u-A", _http(), {"user_id": A}))
            code = 200
    except HTTPException as e:
        code = e.status_code

    assert code == 200, "pad storage-a je ne-fatalan i to ostaje nepromenjeno"
    assert not [r for r in st.rows if r["id"] == "u-A"], "DB red mora biti obrisan"


def test_6_zero_row_guard_present_and_no_audit():
    """V36-E je HTTP ugovor. Audit dolazi u V36-F, kad uspeh postane dokaziv.

    Tvrdnja je vezana za PRISUSTVO guarda, ne za odsustvo audita -- pouka iz
    V31/V35 i V36-B/V36-C, gde je "nema audita" tvrdnja dvaput istekla čim je
    sledeća faza dodala log_action.
    """
    import inspect
    import routers.client_portal as m
    src = inspect.getsource(m.client_portal_obrisi_upload)
    assert "if not r.data" in src, "handler je izgubio zero-row guard"
    assert "404" in src

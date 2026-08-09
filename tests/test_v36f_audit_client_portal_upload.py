# -*- coding: utf-8 -*-
"""
V36-F — kanonski audit za client_portal_upload_delete. Poslednja ruta V36.

ZAVISNOST OD V36-E
Audit je čekao zero-row guard: do V36-E je DELETE rezultat bio odbačen, pa je
handler vraćao uspeh i kad nijedan red nije poklopljen. Test 4 vozi taj prozor.

GRANICA POSLOVNOG USPEHA
Dokaz je neprazan `r.data` iz DB DELETE-a. Audit NIJE uslovljen ishodom storage
brisanja: ono je ne-fatalno po postojećoj semantici, pa bi vezivanje audita za
njega izmislilo distribuiranu transakciju koju kod nema. Test 5 to prikucava --
pad storage-a, ali DB brisanje uspeva, dakle TAČNO JEDAN audit.

BEST-EFFORT SE MERI NA PRAVOJ GRANICI
Test 6 ubrizgava otkaz u _build_and_insert (sink ISPOD log_action) i pušta
PRAVI log_action da se izvrši -- zamena cele funkcije uklonila bi guard koji se
dokazuje.
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
        self.storage = _Storage(self)

    def table(self, name):
        return _Q(self, name)


class _Storage:
    def __init__(self, store):
        self.s = store

    def from_(self, bucket):
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


class _Audit:
    def __init__(self):
        self.calls = []

    async def __call__(self, action, **kw):
        self.calls.append({"action": action, **kw})
        return "audit-id"


def _http():
    return _SReq(scope={"type": "http", "method": "DELETE", "headers": [], "query_string": b"",
                        "path": "/api/client-portal/uploads/x", "client": ("127.0.0.1", 1),
                        "app": MagicMock(), "state": MagicMock()})


def _store(rows=None):
    return _Store(rows if rows is not None else [
        {"_t": "client_portal_uploads", "id": "u-A", "advokat_user_id": A, "storage_path": "p/u-A"},
        {"_t": "client_portal_uploads", "id": "u-B", "advokat_user_id": B, "storage_path": "p/u-B"},
    ])


def _run(store, audit, uid_param, uid):
    import routers.client_portal as m
    with patch.object(m, "_get_supa", return_value=store), \
         patch("shared.audit_immutable.log_action", audit):
        try:
            asyncio.run(m.client_portal_obrisi_upload(uid_param, _http(), {"user_id": uid}))
            return 200
        except HTTPException as e:
            return e.status_code


def test_1_success_emits_exactly_one_audit():
    st, au = _store(), _Audit()
    assert _run(st, au, "u-A", A) == 200
    assert len(au.calls) == 1
    c = au.calls[0]
    assert c["action"] == "client_portal_upload_delete"
    assert c["resource_type"] == "client_portal_upload"
    assert c["resource_id"] == "u-A"
    assert c["user_id"] == A
    assert not [r for r in st.rows if r["id"] == "u-A"]
    assert "p/u-A" in st.storage_removed


def test_2_nonexistent_emits_no_audit():
    st, au = _store(), _Audit()
    assert _run(st, au, "ne-postoji", A) == 404
    assert au.calls == []


def test_3_foreign_upload_no_audit_row_and_storage_survive():
    st, au = _store(), _Audit()
    assert _run(st, au, "u-B", A) == 404
    assert au.calls == []
    assert any(r["id"] == "u-B" for r in st.rows), "upload advokata B mora ostati"
    assert st.storage_removed == [], "tuđi storage objekat se ne sme dirati"


def test_4_toctou_zero_row_emits_no_audit():
    """F-V36-002 regresija: storage obrisan, DB DELETE ne pogodi ništa."""
    import routers.client_portal as m

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
            asyncio.run(m.client_portal_obrisi_upload("u-A", _http(), {"user_id": A}))
            code = 200
        except HTTPException as e:
            code = e.status_code

    assert code == 404
    assert au.calls == [], "zero-row DELETE ne sme proizvesti audit"
    assert "p/u-A" in st.storage_removed, "storage je već bio obrisan -- ograničenje ostaje"


def test_5_storage_failure_still_audits_successful_db_delete():
    """Storage otkaz je ne-fatalan; DB brisanje uspeva -> TAČNO JEDAN audit.

    Audit predstavlja postojeću definiciju uspeha rute. Uslovljavanje audita
    storage ishodom izmislilo bi transakciju koju kod nema.
    """
    import routers.client_portal as m

    class _BadStorage:
        def from_(self, b):
            return self

        def remove(self, paths):
            raise RuntimeError("storage down")

    st, au = _store(), _Audit()
    st.storage = _BadStorage()
    with patch.object(m, "_get_supa", return_value=st), \
         patch("shared.audit_immutable.log_action", au):
        asyncio.run(m.client_portal_obrisi_upload("u-A", _http(), {"user_id": A}))

    assert len(au.calls) == 1, "DB uspeh -> jedan audit, uprkos padu storage-a"
    assert not [r for r in st.rows if r["id"] == "u-A"]


def test_6_audit_sink_failure_does_not_break_deletion():
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
        code = _run(st, ai.log_action, "u-A", A)
    assert raised, "sink otkaz se nije ni desio -- test bi bio prazan"
    assert code == 200, f"pad audit sinka ne sme dati {code}"
    assert not [r for r in st.rows if r["id"] == "u-A"]


def test_7_cardinality_one_invocation_one_audit():
    st, au = _store(), _Audit()
    _run(st, au, "u-A", A)
    assert len(au.calls) == 1
    _run(st, au, "u-A", A)          # drugi put -- red je već obrisan
    assert len(au.calls) == 1, "drugi poziv je 404 i ne sme dodati audit"


def test_8_namespace_and_correlation():
    st, au = _store(), _Audit()
    _run(st, au, "u-A", A)
    c = au.calls[0]
    assert c["resource_type"] == "client_portal_upload"
    assert c["resource_type"] not in ("upload", "document", "webhook", "user_webhook")
    assert c["resource_id"] == "u-A"
    assert "correlation_id" not in c, "correlation se auto-izvodi"


def test_9_owner_predicate_inside_delete():
    """Vlasništvo mora biti u samoj DELETE naredbi, ne samo u SELECT-u."""
    import inspect
    import routers.client_portal as m
    src = inspect.getsource(m.client_portal_obrisi_upload)
    after_delete = src.split(".delete()", 1)[1]
    assert 'eq("advokat_user_id", uid)' in after_delete, (
        "owner predikat mora ostati unutar DELETE naredbe"
    )


def test_10_action_registered():
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "client_portal_upload_delete" in AUDITABLE_ACTIONS

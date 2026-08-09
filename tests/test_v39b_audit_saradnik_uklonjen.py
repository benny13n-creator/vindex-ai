# -*- coding: utf-8 -*-
"""
V39-B — kanonski audit za saradnik_uklonjen.

OPTION A: DVA SINKA, NE ZAMENA
Ruta je jedina u V33-V39 setu koja je VEĆ imala audit -- domenski `_audit_log`
u `saradnja_audit`, koji korisnik vidi preko GET /api/saradnja/audit/{predmet_id}.
`log_action` se DODAJE uz njega. Test 12 prikucava da oba i dalje pale; brisanje
domenskog zapisa oborilo bi korisniku vidljivu istoriju predmeta.

ZAŠTO resource_id NIJE predmet_id
Predmet nije obrisan -- obrisan je red u `predmet_saradnici`. Pravilo kroz
V34-V38 je "ID reda koji je mutiran". Test 5 tvrdi ID reda veze, test 6 tvrdi
da to NIJE predmet_id, jer je predmet_id ovde najprivlačnija pogrešna vrednost
(dostupna je kao parametar funkcije i "izgleda" kao resurs).

REGISTRY BLOKER IZ V39-A
Do V39-A2 akcija nije bila u AUDITABLE_ACTIONS, pa bi `log_action` tiho vratio
None -- kod bi izgledao implementirano a ne bi upisao ništa. Test 13 to drži
zaključanim.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request as _SReq

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

A, B = "vlasnik-A", "vlasnik-B"
P = "predmet-1"
S = "saradnik-9"
VEZA_ID = "veza-42"


class _Store:
    """Modeluje predmeti + predmet_saradnici + saradnja_audit.

    DELETE uklanja red samo ako SVI .eq() predikati poklope -- ista semantika
    kao PostgREST, gde je owner predikat unutar same naredbe.
    """

    def __init__(self, rows=None, delete_raises=False):
        self.rows = rows if rows is not None else [
            {"_t": "predmeti", "id": P, "user_id": A, "naziv": "Predmet 1", "status": "aktivan"},
            {"_t": "predmet_saradnici", "id": VEZA_ID, "predmet_id": P,
             "owner_user_id": A, "saradnik_user_id": S, "uloga": "citanje"},
        ]
        self.delete_raises = delete_raises
        self.saradnja_audit = []

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

    def insert(self, row):
        self.op, self.row = "insert", row
        return self

    def eq(self, col, val):
        self.f[col] = val
        return self

    def limit(self, n):
        return self

    def execute(self):
        res = MagicMock()
        if self.t == "saradnja_audit" and self.op == "insert":
            self.s.saradnja_audit.append(self.row)
            res.data = [self.row]
            return res
        if self.op == "delete" and self.s.delete_raises:
            raise RuntimeError("DB down")
        hit = [r for r in self.s.rows
               if r.get("_t") == self.t and all(r.get(k) == v for k, v in self.f.items())]
        if self.op == "delete":
            for r in hit:
                self.s.rows.remove(r)
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
                        "path": "/api/saradnja/ukloni/x/y", "client": ("127.0.0.1", 1),
                        "app": MagicMock(), "state": MagicMock()})


def _run(store, audit, predmet_id=P, saradnik=S, uid=A):
    import routers.saradnja as m
    with patch.object(m, "_get_supa", return_value=store), \
         patch("shared.audit_immutable.log_action", audit):
        try:
            asyncio.run(m.ukloni_saradnika(predmet_id, saradnik, _http(), {"user_id": uid}))
            return 200
        except HTTPException as e:
            return e.status_code


# ─── SUCCESS ─────────────────────────────────────────────────────────────────

def test_1_success_emits_exactly_one_audit():
    st, au = _Store(), _Audit()
    assert _run(st, au) == 200
    assert len(au.calls) == 1


def test_2_action_is_saradnik_uklonjen():
    st, au = _Store(), _Audit()
    _run(st, au)
    assert au.calls[0]["action"] == "saradnik_uklonjen"


def test_3_actor_is_the_owner():
    st, au = _Store(), _Audit()
    _run(st, au)
    assert au.calls[0]["user_id"] == A


def test_4_resource_type():
    st, au = _Store(), _Audit()
    _run(st, au)
    assert au.calls[0]["resource_type"] == "predmet_saradnik"


def test_5_resource_id_is_the_junction_row_id():
    st, au = _Store(), _Audit()
    _run(st, au)
    assert au.calls[0]["resource_id"] == VEZA_ID


def test_6_resource_id_is_not_predmet_id():
    """Najprivlačnija pogrešna vrednost -- predmet NIJE obrisan."""
    st, au = _Store(), _Audit()
    _run(st, au)
    assert au.calls[0]["resource_id"] != P, (
        "resource_id mora biti ID reda veze; predmet_id bi tvrdio brisanje predmeta"
    )


def test_7_metadata_carries_predmet_and_saradnik():
    """Bez ovoga je ID obrisanog reda forenzički neupotrebljiv."""
    st, au = _Store(), _Audit()
    _run(st, au)
    md = au.calls[0]["metadata"]
    assert md["predmet_id"] == P
    assert md["saradnik_user_id"] == S


# ─── NEGATIVE ────────────────────────────────────────────────────────────────

def test_8_foreign_predmet_no_audit_and_row_survives():
    """B pokušava da ukloni saradnika sa predmeta korisnika A."""
    st, au = _Store(), _Audit()
    assert _run(st, au, uid=B) == 404
    assert au.calls == []
    assert any(r["id"] == VEZA_ID for r in st.rows), "tuđa saradnja mora ostati"


def test_9_nonexistent_saradnik_no_audit():
    st, au = _Store(), _Audit()
    assert _run(st, au, saradnik="ne-postoji") == 404
    assert au.calls == []


def test_10_delete_exception_500_no_audit():
    st, au = _Store(delete_raises=True), _Audit()
    assert _run(st, au) == 500
    assert au.calls == [], "greška DB mutacije ne sme proizvesti audit"


def test_11_zero_row_delete_no_audit():
    """Predmet postoji i vlasnik je A, ali red veze je nestao pre DELETE-a."""
    st, au = _Store(), _Audit()
    st.rows = [r for r in st.rows if r["_t"] != "predmet_saradnici"]
    assert _run(st, au) == 404
    assert au.calls == [], "zero-row DELETE ne sme proizvesti audit"


# ─── OPTION A: OBA SINKA ─────────────────────────────────────────────────────

def test_12_domain_audit_still_fires_alongside_canonical():
    """saradnja_audit je korisniku vidljiva istorija -- ne sme biti zamenjen."""
    st, au = _Store(), _Audit()
    assert _run(st, au) == 200
    assert len(st.saradnja_audit) == 1, "domenski zapis mora i dalje da nastane"
    d = st.saradnja_audit[0]
    assert d["akcija"] == "saradnik_uklonjen"
    assert d["predmet_id"] == P
    assert d["user_id"] == A
    assert len(au.calls) == 1, "i kanonski zapis mora nastati -- OPTION A je DODAVANJE"


def test_13_action_registered():
    """V39-A blocker: neregistrovana akcija -> log_action tiho vraća None."""
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "saradnik_uklonjen" in AUDITABLE_ACTIONS


# ─── SINK FAILURE ────────────────────────────────────────────────────────────

def test_14_audit_sink_failure_does_not_break_removal():
    """Otkaz se ubrizgava u _build_and_insert (sink ISPOD log_action).

    Zamena celog log_action-a uklonila bi upravo onaj guard koji se dokazuje.

    _boom MORA biti sinhron: log_action zove `await asyncio.to_thread(
    _build_and_insert, ...)`, pa async zamena samo vrati coroutine objekat iz
    niti, nikada ne digne, i guard se ne dotakne -- test bi prolazio prazno
    (F-V39-002). `raised` ispod dokazuje da je otkaz stvarno nastupio.
    """
    import shared.audit_immutable as ai

    raised = []

    def _boom(*a, **k):
        raised.append(1)
        raise RuntimeError("audit DB down")

    st = _Store()
    with patch.object(ai, "_build_and_insert", _boom):
        code = _run(st, ai.log_action)
    assert raised, "sink otkaz se nije ni desio -- test bi bio prazan"
    assert code == 200, f"pad audit sinka ne sme dati {code}"
    assert not [r for r in st.rows if r.get("_t") == "predmet_saradnici"], (
        "saradnja mora ostati uklonjena uprkos padu audita"
    )


# ─── CARDINALITY / NAMESPACE ─────────────────────────────────────────────────

def test_15_cardinality_second_call_is_404_and_adds_nothing():
    st, au = _Store(), _Audit()
    _run(st, au)
    assert len(au.calls) == 1
    assert _run(st, au) == 404
    assert len(au.calls) == 1, "drugi poziv ništa ne uklanja i ne sme dodati audit"


def test_16_namespace_and_correlation():
    st, au = _Store(), _Audit()
    _run(st, au)
    c = au.calls[0]
    assert c["resource_type"] not in ("predmet", "saradnja", "klijent", "user")
    assert "correlation_id" not in c, "correlation se auto-izvodi iz request konteksta"


def test_17_owner_predicate_inside_delete():
    """Vlasništvo mora ostati u samoj DELETE naredbi, ne samo u _proveri_vlasnistvo."""
    import inspect
    import routers.saradnja as m
    src = inspect.getsource(m.ukloni_saradnika)
    after_delete = src.split(".delete()", 1)[1]
    assert 'eq("owner_user_id", uid)' in after_delete, (
        "owner predikat mora ostati unutar DELETE naredbe"
    )


def test_18_audit_call_is_outside_try_block():
    """Unutar try-ja bi `except Exception` pretvorio pad audita u HTTP 500."""
    import inspect
    import routers.saradnja as m
    src = inspect.getsource(m.ukloni_saradnika)
    tail = src.split('detail="Greška pri uklanjanju saradnika."', 1)[1]
    assert "log_action(" in tail, "log_action mora stajati POSLE except bloka"

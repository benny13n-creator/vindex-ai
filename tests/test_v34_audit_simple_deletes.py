# -*- coding: utf-8 -*-
"""
V34 — kanonski audit za četiri proste DELETE rute.

OBIM
rociste_delete · zadatak_delete · knowledge_delete · user_webhook_delete

ŠTA SE DOKAZUJE
Audit nastaje ISKLJUČIVO kad je poslovna mutacija stvarno izvršena. Sve četiri
rute imaju owner predikat unutar same DELETE naredbe i zero-row guard, pa je
"nijedan red nije poklopljen" nerazlučivo od "tuđi resurs" -- oba daju 404 i
oba moraju dati NULA audit zapisa.

PLACEMENT KOJI JE ODLUČIO IMPLEMENTACIJU
zadaci.py i knowledge_base.py imaju success granu unutar `try/except Exception
-> HTTPException(500)`. Audit poziv unutar tog bloka pretvorio bi neuspeh
audita u HTTP 500 i prekršio best-effort ugovor log_action(). Zato je u obe
rute audit IZVAN try bloka. Test 4 to prikucava: log_action koji baci izuzetak
ne sme promeniti ishod rute.

NAMESPACE
user_webhook_delete koristi resource_type="user_webhook" (tabela
user_webhooks). integrations.py::delete_webhook briše iz `webhooks` i dobija
"webhook" -- to je V35, ovde se samo tvrdi da ova ruta NE emituje "webhook".
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
    """Briše red samo kad SVI .eq() predikati poklope -- stvarna DELETE semantika."""

    def __init__(self, rows):
        self.rows = list(rows)

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, store, table):
        self.s, self.t, self.f = store, table, {}

    def delete(self):
        return self

    def eq(self, col, val):
        self.f[col] = val
        return self

    def execute(self):
        hit = [r for r in self.s.rows
               if r.get("_t") == self.t and all(r.get(k) == v for k, v in self.f.items())]
        for r in hit:
            self.s.rows.remove(r)
        res = MagicMock()
        res.data = hit
        return res


class _Audit:
    """Beleži svaki log_action poziv sa svim argumentima."""

    def __init__(self, boom=False):
        self.calls = []
        self.boom = boom

    async def __call__(self, action, **kw):
        self.calls.append({"action": action, **kw})
        if self.boom:
            raise RuntimeError("audit sink down")
        return "audit-id"


def _http(path="/x"):
    return _SReq(scope={"type": "http", "method": "DELETE", "headers": [], "query_string": b"",
                        "path": path, "client": ("127.0.0.1", 1),
                        "app": MagicMock(), "state": MagicMock()})


# ── po jedan pozivač za svaku rutu ────────────────────────────────────────

def _rociste(store, audit, rid, uid):
    import routers.rocista as m
    with patch.object(m, "_get_supa", return_value=store), \
         patch("shared.audit_immutable.log_action", audit):
        return asyncio.run(m.obrisi_rociste(rid, _http(), {"user_id": uid}))


def _zadatak(store, audit, zid, uid):
    import routers.zadaci as m
    with patch.object(m, "_get_supa", return_value=store), \
         patch.object(m, "_get_firma_info", new=_afirma), \
         patch("shared.audit_immutable.log_action", audit):
        return asyncio.run(m.obrisi_zadatak(zid, _http(), {"user_id": uid}))


async def _afirma(supa, uid):
    return {"is_admin": False, "kancelarija_id": None}


def _knowledge(store, audit, eid, uid):
    import routers.knowledge_base as m
    with patch.object(m, "_get_supa", return_value=store), \
         patch.object(m, "_get_pinecone_index", return_value=MagicMock()), \
         patch("shared.audit_immutable.log_action", audit):
        return asyncio.run(m.knowledge_delete(eid, _http(), {"user_id": uid}))


def _webhook(store, audit, wid, uid):
    import routers.integracije as m
    with patch.object(m, "_get_supa", return_value=store), \
         patch("shared.audit_immutable.log_action", audit):
        return asyncio.run(m.webhook_brisi(wid, _http(), {"user_id": uid}))


CASES = [
    ("rociste",      _rociste,   "rocista",        "user_id",     "rociste_delete",      "rociste"),
    ("zadatak",      _zadatak,   "zadaci",         "kreirao_uid", "zadatak_delete",      "zadatak"),
    ("knowledge",    _knowledge, "user_knowledge", "user_id",     "knowledge_delete",    "knowledge"),
    ("user_webhook", _webhook,   "user_webhooks",  "user_id",     "user_webhook_delete", "user_webhook"),
]


def _store_for(table, owner_col):
    return _Store([{"_t": table, "id": "res-A", owner_col: A},
                   {"_t": table, "id": "res-B", owner_col: B}])


def _run(call, store, audit, rid, uid):
    try:
        call(store, audit, rid, uid)
        return 200
    except HTTPException as e:
        return e.status_code


@pytest.mark.parametrize("name,call,table,owner,action,rtype", CASES)
def test_1_success_emits_exactly_one_audit(name, call, table, owner, action, rtype):
    st, au = _store_for(table, owner), _Audit()
    assert _run(call, st, au, "res-A", A) == 200
    assert len(au.calls) == 1, f"{name}: tačno jedan audit, dobijeno {len(au.calls)}"
    c = au.calls[0]
    assert c["action"] == action
    assert c["resource_type"] == rtype
    assert c["resource_id"] == "res-A"
    assert c["user_id"] == A, "actor mora biti autentifikovani korisnik"
    assert "correlation_id" not in c, "correlation se auto-izvodi, ne prosleđuje ručno"


@pytest.mark.parametrize("name,call,table,owner,action,rtype", CASES)
def test_2_nonexistent_emits_no_audit(name, call, table, owner, action, rtype):
    st, au = _store_for(table, owner), _Audit()
    assert _run(call, st, au, "ne-postoji", A) == 404
    assert au.calls == [], f"{name}: zero-row ne sme proizvesti audit"


@pytest.mark.parametrize("name,call,table,owner,action,rtype", CASES)
def test_3_foreign_owner_emits_no_audit_and_row_survives(name, call, table, owner, action, rtype):
    st, au = _store_for(table, owner), _Audit()
    assert _run(call, st, au, "res-B", A) == 404
    assert au.calls == [], f"{name}: tuđi resurs ne sme proizvesti audit"
    assert any(r["id"] == "res-B" for r in st.rows), f"{name}: red korisnika B mora ostati"


@pytest.mark.parametrize("name,call,table,owner,action,rtype", CASES)
def test_4_audit_sink_failure_does_not_break_mutation(name, call, table, owner, action, rtype):
    """Best-effort ugovor -- meren na PRAVOJ granici.

    Prva verzija ovog testa zamenjivala je ceo log_action mock-om koji baca, čime
    je uklonila upravo guard koji treba dokazati. Stvarni log_action ima dva
    `try/except Exception` bez re-raise-a (shared/audit_immutable.py L219-230),
    pa se otkaz mora ubrizgati u SINK ispod njega, a ne umesto njega.
    """
    import shared.audit_immutable as ai

    async def _boom_sink(*a, **k):
        raise RuntimeError("audit DB down")

    st = _store_for(table, owner)
    with patch.object(ai, "_build_and_insert", _boom_sink):
        code = _run(call, st, ai.log_action, "res-A", A)   # PRAVI log_action
    assert code == 200, f"{name}: pad audit sinka ne sme dati {code}"
    assert not [r for r in st.rows if r["id"] == "res-A"], "red mora ostati obrisan"


def test_5_user_webhook_never_emits_plain_webhook():
    """Namespace: user_webhooks != webhooks. V35 pokriva drugu rutu."""
    st, au = _store_for("user_webhooks", "user_id"), _Audit()
    _run(_webhook, st, au, "res-A", A)
    assert au.calls[0]["resource_type"] == "user_webhook"
    assert au.calls[0]["action"] == "user_webhook_delete"


def test_6_actions_are_registered():
    from shared.audit_immutable import AUDITABLE_ACTIONS
    for _, _, _, _, action, _ in CASES:
        assert action in AUDITABLE_ACTIONS, f"{action} mora biti u registru (V33)"

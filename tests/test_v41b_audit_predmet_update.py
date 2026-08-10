# -*- coding: utf-8 -*-
"""
V41-B — kanonski audit za predmet_update.

ZAVISNOST OD F-V41-001
Audit je morao da sačeka guard. Do V41 je zero-row UPDATE bez opcionog
`if_updated_at` tokena vraćao {"ok": True}, pa bi audit postavljen tu tvrdio
izmenu predmeta koji ne postoji ili nije korisnikov. Test 3 i 4 voze upravo te
putanje i tvrde nula zapisa.

DVA SISTEMA, NE DUPLIKAT
Middleware u shared/audit.py već upisuje ovaj PATCH u `audit_log`, ali kao
string "PATCH:<uuid>" bez resource_type i bez hash lanca. Kanonski zapis se
DODAJE (OPTION A, isti obrazac kao saradnik_uklonjen), pa test 8 tvrdi tačno
JEDAN kanonski zapis -- ne nula (jer middleware nije zamena) i ne dva.

METADATA NE SME NOSITI SADRŽAJ
`audit_immutable` je append-only sa BEFORE UPDATE OR DELETE trigerom. Upis
naziva/opisa/tuzioca u ledger trajno bi duplirao lične podatke na mesto sa kog
se ne mogu obrisati. Test 6 tvrdi da metadata nosi samo IMENA polja.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

A, B = "advokat-A", "advokat-B"
P = "predmet-1"


class _Store:
    def __init__(self):
        self.rows = [
            {"_t": "predmeti", "id": P, "user_id": A, "naziv": "Stari",
             "opis": "tajna", "updated_at": "T1"},
            {"_t": "predmeti", "id": "predmet-B", "user_id": B, "naziv": "Tudji",
             "updated_at": "T1"},
        ]

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, s, t):
        self.s, self.t, self.f, self.op = s, t, {}, "select"

    def select(self, *a, **k):
        self.op = "select"
        return self

    def update(self, patch):
        self.op, self.patch = "update", patch
        return self

    def eq(self, c, v):
        self.f[c] = v
        return self

    def maybe_single(self):
        return self

    def execute(self):
        hit = [r for r in self.s.rows
               if r.get("_t") == self.t and all(r.get(k) == v for k, v in self.f.items())]
        res = MagicMock()
        if self.op == "update":
            for r in hit:
                r.update(self.patch)
                r["updated_at"] = "T2"
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


def _patch(store, audit, predmet_id, uid, body):
    import api as m

    async def _auth(_a):
        return MagicMock(id=uid)

    req = MagicMock()
    req.url.path = f"/api/predmeti/{predmet_id}"
    req.client.host = "10.0.0.9"

    async def _json():
        return body
    req.json = _json

    with patch.object(m, "_require_auth_async", _auth), \
         patch.object(m, "_get_supa", return_value=store), \
         patch.object(m, "sanitize_user_input", lambda x: x), \
         patch("shared.audit_immutable.log_action", audit):
        try:
            return asyncio.run(m.update_predmet.__wrapped__(predmet_id, req, "Bearer t")), 200
        except HTTPException as e:
            return None, e.status_code


def test_1_success_emits_exactly_one_audit():
    st, au = _Store(), _Audit()
    out, code = _patch(st, au, P, A, {"naziv": "Novi"})
    assert code == 200
    assert len(au.calls) == 1
    c = au.calls[0]
    assert c["action"] == "predmet_update"
    assert c["resource_type"] == "predmet"
    assert c["user_id"] == A


def test_2_resource_id_is_the_predmet():
    st, au = _Store(), _Audit()
    _patch(st, au, P, A, {"naziv": "Novi"})
    assert au.calls[0]["resource_id"] == P


def test_3_foreign_predmet_emits_no_audit():
    """Pre F-V41-001 je ova putanja vraćala 200 -- audit bi tvrdio tuđu izmenu."""
    st, au = _Store(), _Audit()
    out, code = _patch(st, au, "predmet-B", A, {"naziv": "Otet"})
    assert code == 404
    assert au.calls == []
    assert [r for r in st.rows if r["id"] == "predmet-B"][0]["naziv"] == "Tudji"


def test_4_nonexistent_predmet_emits_no_audit():
    st, au = _Store(), _Audit()
    out, code = _patch(st, au, "ne-postoji", A, {"naziv": "X"})
    assert code == 404
    assert au.calls == []


def test_5_stale_precondition_409_emits_no_audit():
    st, au = _Store(), _Audit()
    out, code = _patch(st, au, P, A, {"naziv": "Novi", "if_updated_at": "ZASTARELO"})
    assert code == 409
    assert au.calls == [], "konflikt nije izmena"


def test_6_metadata_carries_field_names_never_values():
    """append-only ledger ne sme primiti sadržaj predmeta (GDPR: nema brisanja)."""
    st, au = _Store(), _Audit()
    _patch(st, au, P, A, {"naziv": "Poverljivo ime", "opis": "tajni opis"})
    md = au.calls[0]["metadata"]
    assert md["polja"] == ["naziv", "opis"]
    blob = repr(md)
    assert "Poverljivo ime" not in blob and "tajni opis" not in blob, (
        "vrednosti polja ne smeju ući u nepromenljivi audit zapis"
    )


def test_7_no_valid_fields_400_emits_no_audit():
    st, au = _Store(), _Audit()
    out, code = _patch(st, au, P, A, {"nepostojece": 1})
    assert code == 400
    assert au.calls == []


def test_8_cardinality_one_edit_one_audit():
    st, au = _Store(), _Audit()
    _patch(st, au, P, A, {"naziv": "A1"})
    assert len(au.calls) == 1
    _patch(st, au, P, A, {"naziv": "A2"})
    assert len(au.calls) == 2, "svaka uspešna izmena je sopstveni događaj"


def test_9_audit_sink_failure_does_not_break_update():
    """Sinhroni injector (F-V39-002): _build_and_insert ide kroz to_thread."""
    import shared.audit_immutable as ai

    raised = []

    def _boom(*a, **k):
        raised.append(1)
        raise RuntimeError("audit DB down")

    st = _Store()
    with patch.object(ai, "_build_and_insert", _boom):
        out, code = _patch(st, ai.log_action, P, A, {"naziv": "Novi"})
    assert raised, "sink otkaz se nije ni desio -- test bi bio prazan"
    assert code == 200, f"pad audit sinka ne sme dati {code}"
    assert [r for r in st.rows if r["id"] == P][0]["naziv"] == "Novi"


def test_10_namespace_and_correlation():
    st, au = _Store(), _Audit()
    _patch(st, au, P, A, {"naziv": "Novi"})
    c = au.calls[0]
    assert c["action"] != "predmet_create", "izmena nije kreiranje"
    assert "correlation_id" not in c, "correlation se auto-izvodi"


def test_11_action_registered():
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "predmet_update" in AUDITABLE_ACTIONS

# -*- coding: utf-8 -*-
"""
V48 / F-V41-002 — zero-row guard za PUT /api/predmeti/komentari/{komentar_id}.

ROOT CAUSE
Ruta je odbacivala rezultat UPDATE-a i bezuslovno vraćala {"status":
"izmenjeno"} -- doslovno tvrdnju da je komentar izmenjen -- i za nepostojeći i
za tuđi komentar_id.

UGOVOR DOLAZI IZ SUSEDA, NE IZ SLIČNOSTI SA DRUGIM SPRINTOVIMA
delete_komentar je odmah ispod u istom fajlu, radi nad istom tabelom, sa istim
oblikom id-a, i od V31 ima zero-row guard sa 404. Test 6 to zaključava kao izvor
iz kog je ugovor izveden.

NEMA IDEMPOTENTNOG ČITANJA
Za razliku od singleton odjava (V46), ovde korisnik imenuje konkretan red.
"Izmenio sam komentar koji ne postoji" nije istinita tvrdnja ni o kakvom
krajnjem stanju.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

A, B = "advokat-A", "advokat-B"


class _Store:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else [
            {"id": "k-A", "user_id": A, "tekst": "stari", "izmenjeno": None},
            {"id": "k-B", "user_id": B, "tekst": "tudji", "izmenjeno": None},
        ]
        self.updates = []

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, s, t):
        self.s, self.t, self.f, self.op = s, t, {}, "select"

    def update(self, patch):
        self.op, self.patch = "update", patch
        return self

    def eq(self, c, v):
        self.f[c] = v
        return self

    def execute(self):
        hit = [r for r in self.s.rows if all(r.get(k) == v for k, v in self.f.items())]
        if self.op == "update":
            self.s.updates.append(dict(self.f))
            for r in hit:
                r.update(self.patch)
        res = MagicMock()
        res.data = hit
        return res


def _http():
    req = MagicMock()
    req.client.host = "127.0.0.1"
    return req


def _put(store, komentar_id, uid=A, tekst="novi tekst"):
    import routers.komentari as m
    body = m.KomentarUpdateRequest(tekst=tekst)
    with patch.object(m, "_get_supa", return_value=store):
        try:
            return asyncio.run(
                m.put_komentar.__wrapped__(komentar_id, body, _http(), {"user_id": uid})
            ), 200
        except HTTPException as e:
            return None, e.status_code


def test_1_own_comment_edited():
    st = _Store()
    out, code = _put(st, "k-A")
    assert code == 200 and out == {"status": "izmenjeno"}
    row = [r for r in st.rows if r["id"] == "k-A"][0]
    assert row["tekst"] == "novi tekst"
    assert row["izmenjeno"] is not None


def test_2_nonexistent_comment_is_404():
    """Pre fixa: {"status": "izmenjeno"} za komentar koji ne postoji."""
    st = _Store()
    out, code = _put(st, "ne-postoji")
    assert code == 404, f"nepostojeći komentar mora dati 404, dobijeno {code}"
    assert out is None


def test_3_foreign_comment_is_404_and_unchanged():
    st = _Store()
    out, code = _put(st, "k-B", uid=A)
    assert code == 404, "tuđi komentar mora dati 404"
    assert [r for r in st.rows if r["id"] == "k-B"][0]["tekst"] == "tudji", (
        "tuđi komentar je oduvek bio zaštićen -- curio je samo lažan odgovor"
    )


def test_4_owner_predicate_is_inside_the_update():
    st = _Store()
    _put(st, "k-A")
    assert st.updates[0].get("user_id") == A
    assert st.updates[0].get("id") == "k-A"


def test_5_repeated_edit_stays_200():
    """Red i dalje poklapa -> nije zero-row."""
    st = _Store()
    _, c1 = _put(st, "k-A", tekst="prva")
    _, c2 = _put(st, "k-A", tekst="druga")
    assert (c1, c2) == (200, 200)
    assert [r for r in st.rows if r["id"] == "k-A"][0]["tekst"] == "druga"


def test_6_sibling_delete_route_has_the_same_guard():
    """Izvor ugovora: isti fajl, ista tabela, isti oblik id-a (V31)."""
    import inspect
    import routers.komentari as m
    src = inspect.getsource(m.delete_komentar)
    assert "status_code=404" in src, (
        "delete_komentar mora zadržati zero-row guard -- to je izvor iz kog je "
        "izveden ugovor put_komentar-a"
    )


def test_7_no_audit_is_emitted_by_the_edit():
    """komentar_delete postoji u registru; izmena nema svoju akciju i ne izmišlja je."""
    calls = []

    async def _spy(action, **kw):
        calls.append(action)
        return "id"

    st = _Store()
    with patch("shared.audit_immutable.log_action", _spy):
        _put(st, "k-A")
    assert calls == []

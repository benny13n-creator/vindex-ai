# -*- coding: utf-8 -*-
"""
V44 / F-V41-002 — zero-row guard za DELETE /api/evidence/predmeti/{p}/dokaz/{d}.

ROOT CAUSE
Ruta radi soft-delete (`deleted_at = now`) preko UPDATE-a, odbacivala je
rezultat i vraćala {"ok": True} bezuslovno. Korisnik dobija potvrdu da je dokaz
uklonjen iz predmeta i za nepostojeći i za tuđi `dokaz_id` -- u dokaznom
materijalu to znači da advokat veruje da je nešto povučeno iz spisa, a nije.

VLASNIŠTVO NIJE BILO PROBIJENO
`.eq("user_id", uid)` je oduvek u samoj UPDATE naredbi, pa tuđi dokaz nije mogao
biti označen obrisanim. Test 3 tvrdi oboje: 404 i da tuđi red ostane sa
deleted_at = None.

PONOVLJENO BRISANJE NIJE ZERO-ROW
Već soft-obrisan red i dalje poklapa `id` + `user_id`, pa UPDATE vraća red i
ruta ostaje 200 (test 5). To nije lažan uspeh nego istinita tvrdnja o krajnjem
stanju; pretvaranje u 404 bilo bi izmišljanje semantike koju kod nema.

predmet_id JE U PUTANJI ALI NIJE PREDIKAT
Zabeleženo, NIJE menjano u ovom sprintu: `predmet_id` se ne koristi u mutaciji.
Sigurnosno je pokriveno `user_id`-em; dodavanje predikata bilo bi izmena
ponašanja van obima. Test 6 zaključava trenutno stanje da promena ne prođe
neprimećeno.
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
    def __init__(self, rows=None, raises=False):
        self.rows = rows if rows is not None else [
            {"_t": "predmet_dokazi", "id": "d-A", "user_id": A, "predmet_id": P, "deleted_at": None},
            {"_t": "predmet_dokazi", "id": "d-B", "user_id": B, "predmet_id": P, "deleted_at": None},
        ]
        self.raises = raises
        self.updates = []

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

    def execute(self):
        if self.s.raises:
            raise RuntimeError("DB down")
        hit = [r for r in self.s.rows
               if r.get("_t") == self.t and all(r.get(k) == v for k, v in self.f.items())]
        res = MagicMock()
        if self.op == "update":
            self.s.updates.append(dict(self.f))
            for r in hit:
                r.update(self.patch)
        res.data = hit
        return res


def _http():
    req = MagicMock()
    req.client.host = "127.0.0.1"
    return req


def _delete(store, dokaz_id, uid=A, predmet_id=P):
    import routers.evidence as m
    with patch.object(m, "get_supa", return_value=store):
        try:
            return asyncio.run(
                m.delete_dokaz.__wrapped__(_http(), predmet_id, dokaz_id, {"user_id": uid})
            ), 200
        except HTTPException as e:
            return None, e.status_code


def test_1_own_dokaz_soft_deleted_successfully():
    st = _Store()
    out, code = _delete(st, "d-A")
    assert code == 200 and out == {"ok": True}
    row = [r for r in st.rows if r["id"] == "d-A"][0]
    assert row["deleted_at"] is not None, "soft delete mora upisati timestamp"


def test_2_nonexistent_dokaz_is_404_not_fake_success():
    """F-V41-002: pre fixa je vraćalo {"ok": True} bez ijedne izmene."""
    st = _Store()
    out, code = _delete(st, "ne-postoji")
    assert code == 404, f"nepostojeći dokaz mora dati 404, dobijeno {code}"
    assert out is None


def test_3_foreign_dokaz_is_404_and_survives():
    st = _Store()
    out, code = _delete(st, "d-B", uid=A)
    assert code == 404, "tuđi dokaz mora dati 404"
    assert [r for r in st.rows if r["id"] == "d-B"][0]["deleted_at"] is None, (
        "tuđi dokaz je oduvek bio zaštićen -- curio je samo lažan odgovor"
    )


def test_4_owner_predicate_is_inside_the_update():
    st = _Store()
    _delete(st, "d-A")
    assert st.updates, "UPDATE se mora izvršiti"
    assert st.updates[0].get("user_id") == A, "owner predikat mora biti u samoj naredbi"
    assert st.updates[0].get("id") == "d-A"


def test_5_repeated_delete_stays_200_not_zero_row():
    """Već obrisan red i dalje poklapa -> nije zero-row slučaj."""
    st = _Store()
    _, code1 = _delete(st, "d-A")
    assert code1 == 200
    _, code2 = _delete(st, "d-A")
    assert code2 == 200, "ponovljeno brisanje je istinita tvrdnja o krajnjem stanju"
    assert len(st.updates) == 2


def test_6_predmet_id_is_not_a_predicate_current_behavior():
    """Zabeleženo stanje, van obima V44: predmet_id iz putanje se ne koristi.

    Sigurnosno je pokriveno user_id-em. Test drži trenutno ponašanje vidljivim
    da eventualna izmena ne prođe neprimećeno.
    """
    st = _Store()
    out, code = _delete(st, "d-A", predmet_id="sasvim-drugi-predmet")
    assert code == 200
    assert "predmet_id" not in st.updates[0]


def test_7_db_exception_propagates_unchanged():
    st = _Store(raises=True)
    with pytest.raises(RuntimeError):
        import routers.evidence as m
        with patch.object(m, "get_supa", return_value=st):
            asyncio.run(m.delete_dokaz.__wrapped__(_http(), P, "d-A", {"user_id": A}))


def test_8_no_audit_is_emitted():
    """Ruta nema audit; V44 popravlja mutaciju i ne uvodi ga."""
    calls = []

    async def _spy(action, **kw):
        calls.append(action)
        return "id"

    st = _Store()
    with patch("shared.audit_immutable.log_action", _spy):
        _delete(st, "d-A")
    assert calls == []

# -*- coding: utf-8 -*-
"""
V43 / F-V41-002 — zero-row guard za DELETE /api/export/api-kljucevi/{kljuc_id}.

ZAŠTO JE OVO NAJTEŽA INSTANCA KLASE
Ruta soft-opoziva API ključ (`aktivan = False`) i vraćala je
{"status": "opozvan"} bezuslovno, bez gledanja u rezultat UPDATE-a. Kod običnog
resursa lažan success znači "mislio sam da sam sačuvao". Ovde znači da korisnik
dobija potvrdu da je KREDENCIJAL opozvan i prestaje da ga tretira kao aktivan --
posle pogrešnog id-a, tuđeg id-a ili obične greške u kucanju.

VLASNIŠTVO NIJE BILO PROBIJENO
`.eq("user_id", ...)` je oduvek u samoj UPDATE naredbi, pa tuđi ključ nije mogao
biti deaktiviran. Test 3 tvrdi oboje: 404 i da tuđi ključ ostaje aktivan.

PONOVLJENI OPOZIV NIJE GREŠKA
Već neaktivan ključ i dalje poklapa `id` + `user_id`, pa UPDATE vraća red i
ruta i dalje vraća 200. To NIJE zero-row slučaj i namerno se ne pretvara u 404
(test 5) -- opoziv već opozvanog ključa je istinita tvrdnja o krajnjem stanju.
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
            {"_t": "api_kljucevi", "id": "k-A", "user_id": A, "aktivan": True},
            {"_t": "api_kljucevi", "id": "k-B", "user_id": B, "aktivan": True},
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

    def order(self, *a, **k):
        return self

    def execute(self):
        hit = [r for r in self.s.rows
               if r.get("_t") == self.t and all(r.get(k) == v for k, v in self.f.items())]
        res = MagicMock()
        if self.op == "update":
            for r in hit:
                r.update(self.patch)
        res.data = hit
        return res


def _revoke(store, kljuc_id, uid=A):
    import routers.export as m
    with patch.object(m, "_get_supa", return_value=store):
        try:
            return asyncio.run(m.delete_api_kljuc(kljuc_id, {"user_id": uid})), 200
        except HTTPException as e:
            return None, e.status_code


def test_1_own_key_revoked_successfully():
    st = _Store()
    out, code = _revoke(st, "k-A")
    assert code == 200 and out == {"status": "opozvan"}
    assert [r for r in st.rows if r["id"] == "k-A"][0]["aktivan"] is False


def test_2_nonexistent_key_is_404_not_fake_revocation():
    """F-V41-002: pre fixa je korisnik dobijao potvrdu opoziva bez opoziva."""
    st = _Store()
    out, code = _revoke(st, "ne-postoji")
    assert code == 404, f"nepostojeći ključ mora dati 404, dobijeno {code}"
    assert out is None


def test_3_foreign_key_is_404_and_stays_active():
    st = _Store()
    out, code = _revoke(st, "k-B", uid=A)
    assert code == 404, "tuđi ključ mora dati 404"
    assert [r for r in st.rows if r["id"] == "k-B"][0]["aktivan"] is True, (
        "tuđi ključ je oduvek bio zaštićen -- curio je samo lažan odgovor"
    )


def test_4_owner_predicate_is_inside_the_update():
    import inspect
    import routers.export as m
    src = inspect.getsource(m.delete_api_kljuc)
    after = src.split('.update({"aktivan": False})', 1)[1]
    assert 'eq("user_id", user["user_id"])' in after, (
        "owner predikat mora ostati unutar UPDATE naredbe"
    )


def test_5_revoking_an_already_revoked_key_is_still_200():
    """Nije zero-row: red i dalje poklapa, pa je tvrdnja o krajnjem stanju istinita."""
    st = _Store(rows=[{"_t": "api_kljucevi", "id": "k-A", "user_id": A, "aktivan": False}])
    out, code = _revoke(st, "k-A")
    assert code == 200, "ponovljeni opoziv nije greška"
    assert out == {"status": "opozvan"}


def test_6_no_audit_is_emitted():
    """Ruta nema audit i V43 ga ne uvodi -- popravka mutacije je zaseban posao."""
    calls = []

    async def _spy(action, **kw):
        calls.append(action)
        return "id"

    st = _Store()
    with patch("shared.audit_immutable.log_action", _spy):
        _revoke(st, "k-A")
    assert calls == [], "api_key_rotation nije dokazana akcija za ovu rutu"

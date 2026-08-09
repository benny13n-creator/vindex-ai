# -*- coding: utf-8 -*-
"""
V39-C — kanonski audit za intake_bulk_import (klijent_create + predmet_create).

DVA RAZLIČITA SUCCESS BOUNDARY-JA U ISTOM REDU
Ovo je jedina ruta u V33-V39 setu gde dva entiteta iz istog reda imaju različit
dokaz uspeha:

  klijent -> INSERT je konačan. Kompenzujući DELETE ispod briše SAMO `predmeti`,
             nikad klijenta. Red koji padne posle kreiranja klijenta OSTAVLJA
             tog klijenta u bazi -> audit MORA da nastane (test 5).
  predmet -> INSERT NIJE konačan. Ako `predmet_klijenti` insert padne, predmet
             se briše i izuzetak se re-raise-uje -> audit NE SME da nastane
             (test 10). Emitovanje odmah posle INSERT-a tvrdilo bi postojanje
             reda koji je obrisan.

ZAŠTO SE AUDIT EMITUJE POSLE PETLJE
Telo svakog reda je u `except Exception -> greske.append`. log_action pozvan
unutar petlje pretvorio bi, ako bi ikada digao, uspešan red u prijavljenu
grešku -- audit bi menjao poslovni ishod. Test 17 vozi stvarni otkaz sinka i
tvrdi da `uspeh` ostaje netaknut.

F-V39-002: injector je SINHRON
log_action zove `await asyncio.to_thread(_build_and_insert, ...)`. Async
zamena bi u niti samo vratila coroutine objekat i nikad ne bi digla -- test bi
prolazio prazno. `raised` dokazuje da je otkaz stvarno nastupio.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request as _SReq

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

A = "advokat-A"


class _Store:
    """klijenti + predmeti + predmet_klijenti sa kontrolisanim otkazima."""

    def __init__(self, klijenti=None, klijent_insert_empty=False,
                 predmet_insert_empty=False, link_raises=False):
        self.klijenti = list(klijenti or [])      # postojeći redovi
        self.predmeti = []
        self.veze = []
        self.klijent_insert_empty = klijent_insert_empty
        self.predmet_insert_empty = predmet_insert_empty
        self.link_raises = link_raises
        self._n = 0

    def next_id(self, p):
        self._n += 1
        return f"{p}-{self._n}"

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, s, t):
        self.s, self.t, self.f, self.op = s, t, {}, "select"

    def select(self, *a, **k):
        self.op = "select"
        return self

    def insert(self, row):
        self.op, self.row = "insert", row
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, c, v):
        self.f[c] = v
        return self

    def neq(self, c, v):
        self.f["!" + c] = v
        return self

    def limit(self, n):
        return self

    def execute(self):
        res = MagicMock()
        if self.t == "klijenti":
            if self.op == "select":
                res.data = [k for k in self.s.klijenti
                            if k.get("user_id") == self.f.get("user_id")
                            and k.get("email") == self.f.get("email")
                            and k.get("status") != self.f.get("!status")]
            else:
                if self.s.klijent_insert_empty:
                    res.data = []
                else:
                    row = {"id": self.s.next_id("kl"), **self.row}
                    self.s.klijenti.append(row)
                    res.data = [row]
        elif self.t == "predmeti":
            if self.op == "insert":
                if self.s.predmet_insert_empty:
                    res.data = []
                else:
                    row = {"id": self.s.next_id("pr"), **self.row}
                    self.s.predmeti.append(row)
                    res.data = [row]
            elif self.op == "delete":
                gone = self.f.get("id")
                self.s.predmeti = [p for p in self.s.predmeti if p["id"] != gone]
                res.data = [{"id": gone}]
        elif self.t == "predmet_klijenti":
            if self.s.link_raises:
                raise RuntimeError("link insert failed")
            self.s.veze.append(self.row)
            res.data = [self.row]
        return res


class _Audit:
    def __init__(self):
        self.calls = []

    async def __call__(self, action, **kw):
        self.calls.append({"action": action, **kw})
        return "audit-id"

    def of(self, action):
        return [c for c in self.calls if c["action"] == action]


def _http():
    return _SReq(scope={"type": "http", "method": "POST", "headers": [], "query_string": b"",
                        "path": "/api/intake/bulk-import", "client": ("10.0.0.7", 1),
                        "app": MagicMock(), "state": MagicMock()})


def _red(naziv, email="", ime="Ime", **kw):
    return {"ime": ime, "email": email, "naziv_predmeta": naziv, **kw}


def _run(store, audit, redovi, uid=A):
    import routers.intake as m
    body = m.BulkImportReq(redovi=[m.BulkImportRed(**r) for r in redovi])
    with patch.object(m, "_get_supa", return_value=store), \
         patch("shared.audit_immutable.log_action", audit):
        return asyncio.run(m.intake_bulk_import(_http(), body, {"user_id": uid}))


# ─── CLIENT ──────────────────────────────────────────────────────────────────

def test_1_one_new_client_one_audit():
    st, au = _Store(), _Audit()
    out = _run(st, au, [_red("P1", "a@x.rs")])
    assert out["uspeh"] == 1
    assert len(au.of("klijent_create")) == 1


def test_2_three_new_clients_three_audits():
    st, au = _Store(), _Audit()
    out = _run(st, au, [_red("P1", "a@x.rs"), _red("P2", "b@x.rs"), _red("P3", "c@x.rs")])
    assert out["uspeh"] == 3
    assert len(au.of("klijent_create")) == 3, "N kreiranih klijenata = N audita"


def test_3_resource_id_matches_actually_created_client():
    st, au = _Store(), _Audit()
    _run(st, au, [_red("P1", "a@x.rs")])
    created = [k["id"] for k in st.klijenti]
    assert au.of("klijent_create")[0]["resource_id"] in created
    assert au.of("klijent_create")[0]["resource_type"] == "klijent"


def test_4_reused_existing_client_emits_no_klijent_create():
    """Ponovno korišćenje NIJE kreiranje -- najveći izvor lažnog audita."""
    st = _Store(klijenti=[{"id": "kl-stari", "user_id": A, "email": "a@x.rs", "status": "aktivan"}])
    au = _Audit()
    out = _run(st, au, [_red("P1", "a@x.rs")])
    assert out["uspeh"] == 1
    assert au.of("klijent_create") == [], "postojeći klijent ne sme dati create audit"
    assert len(au.of("predmet_create")) == 1


def test_5_client_survives_failed_row_so_audit_must_fire():
    """Predmet padne POSLE kreiranja klijenta -- klijent ostaje u bazi.

    Kompenzujući DELETE briše samo `predmeti`. Izostavljanje audita ovde
    lagalo bi izostankom: klijent postoji, a ničim nije zabeležen.
    """
    st, au = _Store(predmet_insert_empty=True), _Audit()
    out = _run(st, au, [_red("P1", "a@x.rs")])
    assert out["uspeh"] == 0 and out["greske_broj"] == 1
    assert len(st.klijenti) == 1, "klijent JESTE ostao u bazi"
    assert len(au.of("klijent_create")) == 1, "klijent postoji -> mora biti auditovan"
    assert au.of("predmet_create") == [], "predmet nije kreiran"


def test_6_failed_client_insert_emits_nothing():
    st, au = _Store(klijent_insert_empty=True), _Audit()
    out = _run(st, au, [_red("P1", "a@x.rs")])
    assert out["greske_broj"] == 1
    assert au.calls == []


# ─── PREDMET ─────────────────────────────────────────────────────────────────

def test_7_one_predmet_one_audit():
    st, au = _Store(), _Audit()
    _run(st, au, [_red("P1", "a@x.rs")])
    assert len(au.of("predmet_create")) == 1


def test_8_two_rows_same_email_one_client_two_predmeti():
    """Drugi red pogodi SELECT -> 1 klijent, 2 predmeta. Kardinalnost nije 1:1."""
    st, au = _Store(), _Audit()
    out = _run(st, au, [_red("P1", "a@x.rs"), _red("P2", "a@x.rs")])
    assert out["uspeh"] == 2
    assert len(au.of("klijent_create")) == 1
    assert len(au.of("predmet_create")) == 2


def test_9_predmet_resource_id_matches_created_row():
    st, au = _Store(), _Audit()
    out = _run(st, au, [_red("P1", "a@x.rs"), _red("P2", "b@x.rs")])
    ids = [p["predmet_id"] for p in out["predmeti"]]
    assert [c["resource_id"] for c in au.of("predmet_create")] == ids
    assert all(c["resource_type"] == "predmet" for c in au.of("predmet_create"))


def test_10_rolled_back_predmet_emits_no_predmet_create():
    """predmet_klijenti padne -> kompenzujući DELETE -> predmeta više nema."""
    st, au = _Store(link_raises=True), _Audit()
    out = _run(st, au, [_red("P1", "a@x.rs")])
    assert out["uspeh"] == 0 and out["greske_broj"] == 1
    assert st.predmeti == [], "predmet je rollbackovan"
    assert au.of("predmet_create") == [], "rollbackovan predmet ne sme biti auditovan"
    assert len(au.of("klijent_create")) == 1, "klijent nije rollbackovan -> ostaje auditovan"


def test_11_partial_batch_audits_only_survivors():
    st, au = _Store(), _Audit()
    real = st.table
    pokusaji = []

    def _flaky(name):
        q = real(name)
        if name == "predmet_klijenti":
            pokusaji.append(1)
            if len(pokusaji) == 2:      # pada TAČNO drugi red
                def _bad():
                    raise RuntimeError("link failed")
                q.execute = _bad
        return q

    st.table = _flaky
    out = _run(st, au, [_red("P1", "a@x.rs"), _red("P2", "b@x.rs"), _red("P3", "c@x.rs")])
    assert out["uspeh"] == 2 and out["greske_broj"] == 1
    ok_ids = [p["predmet_id"] for p in out["predmeti"]]
    assert [c["resource_id"] for c in au.of("predmet_create")] == ok_ids
    assert len(au.of("klijent_create")) == 3, "sva tri klijenta su kreirana i ostala"


# ─── CROSS-BINDING ───────────────────────────────────────────────────────────

def test_12_predmet_metadata_binds_the_actually_linked_client():
    st = _Store(klijenti=[{"id": "kl-stari", "user_id": A, "email": "a@x.rs", "status": "aktivan"}])
    au = _Audit()
    _run(st, au, [_red("P1", "a@x.rs"), _red("P2", "novi@x.rs")])
    md = [c["metadata"] for c in au.of("predmet_create")]
    assert md[0]["klijent_id"] == "kl-stari", "mora nositi POSTOJEĆI klijent id"
    assert md[1]["klijent_id"] == au.of("klijent_create")[0]["resource_id"]
    assert st.veze[0]["klijent_id"] == md[0]["klijent_id"], "mora se poklopiti sa vezom u bazi"


def test_13_metadata_source_and_row_number():
    st, au = _Store(), _Audit()
    _run(st, au, [_red("P1", "a@x.rs"), _red("P2", "b@x.rs")])
    assert [c["metadata"]["red"] for c in au.of("klijent_create")] == [1, 2]
    assert all(c["metadata"]["source"] == "bulk_import" for c in au.calls)


# ─── ACTOR / DUPLICATION ─────────────────────────────────────────────────────

def test_14_actor_is_authenticated_user_not_input():
    st, au = _Store(), _Audit()
    _run(st, au, [_red("P1", "a@x.rs")], uid="drugi-advokat")
    assert len(au.calls) == 2, "bez zapisa je tvrdnja o akteru vakuumska"
    assert all(c["user_id"] == "drugi-advokat" for c in au.calls)
    assert all(k["user_id"] == "drugi-advokat" for k in st.klijenti)


def test_15_input_cannot_inject_foreign_actor():
    """BulkImportRed nema nijedno polje koje nosi identitet korisnika."""
    import routers.intake as m
    assert not {"user_id", "uid", "owner_user_id", "advokat_user_id"} & set(
        m.BulkImportRed.model_fields
    )


def test_16_no_aggregate_audit_and_no_duplicate_producer():
    import inspect
    import re
    import routers.intake as m
    st, au = _Store(), _Audit()
    _run(st, au, [_red("P1", "a@x.rs"), _red("P2", "b@x.rs")])
    assert len(au.calls) == 4, "2 klijenta + 2 predmeta, bez agregatnog zapisa"
    src = inspect.getsource(m.intake_bulk_import)
    assert len(re.findall(r"await log_action\(", src)) == 1, (
        "tačno jedan producer koji emituje sakupljene događaje"
    )


# ─── SINK FAILURE ────────────────────────────────────────────────────────────

def test_17_audit_sink_failure_does_not_change_business_outcome():
    """Ceo red je u `except Exception -> greske`. Otkaz audita ne sme ga oboriti."""
    import shared.audit_immutable as ai

    raised = []

    def _boom(*a, **k):
        raised.append(1)
        raise RuntimeError("audit DB down")

    st = _Store()
    with patch.object(ai, "_build_and_insert", _boom):
        out = _run(st, ai.log_action, [_red("P1", "a@x.rs"), _red("P2", "b@x.rs")])
    assert raised, "sink otkaz se nije ni desio -- test bi bio prazan"
    assert out["uspeh"] == 2, "uspešni redovi moraju ostati uspešni"
    assert out["greske_broj"] == 0, "audit otkaz ne sme postati poslovna greška"
    assert len(st.predmeti) == 2


def test_18_actions_registered():
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "klijent_create" in AUDITABLE_ACTIONS
    assert "predmet_create" in AUDITABLE_ACTIONS

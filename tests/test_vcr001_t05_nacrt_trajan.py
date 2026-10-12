# -*- coding: utf-8 -*-
"""VCR001 T05 — nacrt je trajan, ponovo otvorljiv radni proizvod; odobrava se ono što je advokat video.

GET  /api/staging/{id}        → ceo nacrt (tekst), samo vlasnik; tuđ → 404 bez sadržaja.
PATCH /api/staging/{id}/tekst → izmena SAMO dok je nacrt na čekanju; posle odluke 409; Quality Gate se računa
                                 nad izmenjenim tekstom; audit `nacrt_izmenjen` (dužina + otisak, ne tekst).
POST /api/staging/{id}/approve → u bazu znanja ide tekst iz PREUZETOG reda (izmena posle čitanja nije izgubljena).
"""
import pytest

from tests.ns005_harness import zaglavlje
from tests.test_ns005_t8_nacrti import ok  # noqa: F401


def _red(b, sid):
    return next(x for x in b.tabele["staging_memory"] if x["id"] == sid)


def test_vlasnik_otvara_ceo_nacrt(ok):  # noqa: F811
    k, b, *_ = ok
    _red(b, "st-A")["tekst"] = "TUŽBA za naknadu štete — pun tekst"
    r = k.get("/api/staging/st-A", headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["tekst"] == "TUŽBA za naknadu štete — pun tekst" and d["status"] == "pending" and d["izmenio_advokat"] is False


def test_tudj_nacrt_404_bez_sadrzaja(ok):  # noqa: F811
    k, b, *_ = ok
    r = k.get("/api/staging/st-B", headers=zaglavlje("A"))
    assert r.status_code == 404 and "TAJN" not in r.text


def test_izmena_se_cuva_i_kvalitet_se_racuna_nad_novim_tekstom(ok, monkeypatch):  # noqa: F811
    k, b, *_ = ok
    import services.quality_gate as QG
    ocenjeno = []

    async def _kvalitet(t, tip):
        ocenjeno.append(t)
        return {"confidence_score": 0.91, "detail": {"citations_found": 1}}
    monkeypatch.setattr(QG, "evaluate_draft_quality", _kvalitet)
    audit = []
    import shared.audit_immutable as A

    async def _log(**kw):
        audit.append(kw)
    monkeypatch.setattr(A, "log_action", _log)
    r = k.patch("/api/staging/st-A/tekst", json={"tekst": "Izmenjen tekst advokata, čl. 154 ZOO"}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    red = _red(b, "st-A")
    assert red["tekst"] == "Izmenjen tekst advokata, čl. 154 ZOO" and float(red["confidence_score"]) == 0.91
    assert red["quality_detail"]["izmenio_advokat"] is True and red["status"] == "pending"
    assert ocenjeno == ["Izmenjen tekst advokata, čl. 154 ZOO"]
    g = k.get("/api/staging/st-A", headers=zaglavlje("A")).json()
    assert g["tekst"] == red["tekst"] and g["izmenio_advokat"] is True and g["izmenjeno_at"]
    assert audit and audit[0]["action"] == "nacrt_izmenjen" and "Izmenjen" not in str(audit[0]["metadata"])


def test_tudj_nacrt_se_ne_menja(ok):  # noqa: F811
    k, b, *_ = ok
    r = k.patch("/api/staging/st-B/tekst", json={"tekst": "napad"}, headers=zaglavlje("A"))
    assert r.status_code == 404 and _red(b, "st-B")["tekst"] == "TAJNO"


@pytest.mark.parametrize("status", ["approved", "rejected"])
def test_posle_odluke_izmena_409(ok, status):  # noqa: F811
    k, b, *_ = ok
    _red(b, "st-A")["status"] = status
    r = k.patch("/api/staging/st-A/tekst", json={"tekst": "kasna izmena"}, headers=zaglavlje("A"))
    assert r.status_code == 409 and _red(b, "st-A")["tekst"] == "x"


@pytest.mark.parametrize("tekst", ["", "   \n  "])
def test_prazan_tekst_422(ok, tekst):  # noqa: F811
    k, b, *_ = ok
    assert k.patch("/api/staging/st-A/tekst", json={"tekst": tekst}, headers=zaglavlje("A")).status_code == 422
    assert _red(b, "st-A")["tekst"] == "x"


def test_odobrenje_unosi_izmenjen_tekst_u_bazu_znanja(ok, monkeypatch):  # noqa: F811
    k, b, *_ = ok
    import routers.drafting as D
    import services.quality_gate as QG

    async def _kvalitet(t, tip):
        return {"confidence_score": 0.95, "detail": {}}
    monkeypatch.setattr(QG, "evaluate_draft_quality", _kvalitet)
    uneto = []

    async def _promovisi(supa, red):
        uneto.append(red["tekst"])
        return True
    monkeypatch.setattr(D, "_promote_staged_draft_to_pinecone", _promovisi)
    assert k.patch("/api/staging/st-A/tekst", json={"tekst": "PREGLEDAN tekst"}, headers=zaglavlje("A")).status_code == 200
    r = k.post("/api/staging/st-A/approve", headers=zaglavlje("A"))
    assert r.status_code == 200 and r.json()["indexed"] is True
    assert uneto == ["PREGLEDAN tekst"]


def test_odobrenje_koristi_preuzeti_red_a_ne_zastarelo_citanje(ok, monkeypatch):  # noqa: F811
    """Izmena sačuvana IZMEĐU čitanja reda i brave pending→approved: promoviše se tekst iz preuzetog reda."""
    k, b, *_ = ok
    import routers.drafting as D
    pravi = D._get_supa

    class _Staro:
        def __init__(self, q):
            self.q = q

        def __getattr__(self, n):                 # ceo lanac (.eq/.maybe_single) ostaje umotan
            a = getattr(self.q, n)
            return (lambda *x, **y: _Staro(a(*x, **y))) if callable(a) else a

        def execute(self):
            r = self.q.execute()
            if isinstance(r.data, dict) and "tekst" in r.data:
                r.data = {**r.data, "tekst": "ZASTARELO", "confidence_score": 0.95}
            return r

    class _Proksi:
        def __init__(self, s):
            self.s = s

        def table(self, ime):
            t = self.s.table(ime)
            if ime != "staging_memory":
                return t
            stari_select = t.select

            def _select(kol="*", *a, **kw):
                q = stari_select(kol, *a, **kw)
                return _Staro(q) if kol == "*" else q
            t.select = _select
            return t
    monkeypatch.setattr(D, "_get_supa", lambda: _Proksi(pravi()))
    red = _red(b, "st-A")
    red["tekst"], red["confidence_score"] = "SVEŽE", 0.95
    uneto = []

    async def _promovisi(supa, r):
        uneto.append(r["tekst"])
        return True
    monkeypatch.setattr(D, "_promote_staged_draft_to_pinecone", _promovisi)
    assert k.post("/api/staging/st-A/approve", headers=zaglavlje("A")).status_code == 200
    assert uneto == ["SVEŽE"]

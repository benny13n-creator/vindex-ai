# -*- coding: utf-8 -*-
"""NS005 Task 9 — Kancelarija: tim, portfolio, zdravlje — stvarne rute.

GET /api/kancelarija/moja   — admin i član iste kancelarije vide tim; druga kancelarija ne;
                              pad čitanja → 503 (ranije lažno {"status": "no_firma"}).
GET /portfolio/dashboard    — samo predmeti pozivaoca; pad izvora → 503 (ranije „Sve je pod
                              kontrolom — nema hitnih rokova").
GET /api/firm/health-index  — pad izvora → 503 (ranije izračunata ocena nad nepročitanim podacima).
"""
import pytest

from tests.ns005_harness import pripremi, ocisti, zaglavlje, SPOLJNI_POKUSAJI, TOKENI


def _baza():
    return {
        "kancelarije": [{"id": "k1", "naziv": "Jović i partneri", "admin_uid": "uid-A", "created_at": "2026-01-01"},
                        {"id": "k2", "naziv": "TAJNA kancelarija B", "admin_uid": "uid-B", "created_at": "2026-01-01"}],
        "kancelarija_clanovi": [
            {"id": "c1", "kancelarija_id": "k1", "user_id": "uid-C", "email": "c@primer.test", "uloga": "saradnik", "status": "ACTIVE", "invited_at": "2026-02-01"},
            {"id": "c2", "kancelarija_id": "k2", "user_id": "uid-X", "email": "tajni@b.test", "uloga": "partner", "status": "ACTIVE", "invited_at": "2026-02-01"},
        ],
        "predmeti": [{"id": "pA", "user_id": "uid-A", "naziv": "Predmet A", "tip": "parnicni", "status": "aktivan", "updated_at": "2026-10-01"},
                     {"id": "pB", "user_id": "uid-B", "naziv": "TAJNI predmet B", "tip": "radni", "status": "aktivan", "updated_at": "2026-10-01"}],
    }


@pytest.fixture
def ok(monkeypatch):
    TOKENI["tok-D"] = "uid-D"
    k, b = pripremi(monkeypatch, _baza())
    import shared.permissions as perm
    import shared.usage as us

    async def _politika(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

    async def _nista(*a, **kw):
        return None
    monkeypatch.setattr(perm, "get_policy", _politika)
    monkeypatch.setattr(perm, "_check_dependencies", _nista)
    monkeypatch.setattr(us.UsageService, "consume", staticmethod(_nista))
    import routers.health_index as H
    H._CACHE.clear()

    async def _bez_ai(*a, **kw):
        return ""
    monkeypatch.setattr(H, "_compute_chief_partner", _bez_ai)
    yield k, b
    TOKENI.pop("tok-D", None)
    ocisti()


def test_admin_vidi_svoj_tim(ok):
    k, _ = ok
    d = k.get("/api/kancelarija/moja", headers=zaglavlje("A")).json()
    assert d["status"] == "aktivan" and d["moja_uloga"] == "admin" and d["firma"]["naziv"] == "Jović i partneri"
    assert [c["email"] for c in d["clanovi"]] == ["c@primer.test"]


def test_clan_vidi_isti_tim_sa_svojom_ulogom(ok):
    k, _ = ok
    d = k.get("/api/kancelarija/moja", headers=zaglavlje("C")).json()
    assert d["status"] == "aktivan" and d["moja_uloga"] == "saradnik" and d["firma"]["id"] == "k1"


def test_druga_kancelarija_nevidljiva(ok):
    k, _ = ok
    r = k.get("/api/kancelarija/moja", headers=zaglavlje("B"))
    d = r.json()
    assert d["firma"]["id"] == "k2" and "Jović" not in r.text and "c@primer.test" not in r.text
    a = k.get("/api/kancelarija/moja", headers=zaglavlje("A"))
    assert "TAJNA" not in a.text and "tajni@b.test" not in a.text


def test_bez_kancelarije_je_no_firma(ok):
    k, _ = ok
    assert k.get("/api/kancelarija/moja", headers=zaglavlje("D")).json() == {"status": "no_firma"}


def test_pad_citanja_kancelarije_je_503_ne_no_firma(ok):
    k, b = ok
    b.greske["kancelarije"] = RuntimeError("baza nedostupna")
    r = k.get("/api/kancelarija/moja", headers=zaglavlje("A"))
    assert r.status_code == 503 and "no_firma" not in r.text


def test_portfolio_samo_svoji_predmeti(ok):
    k, _ = ok
    r = k.get("/portfolio/dashboard", headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ukupno_predmeta"] == 1 and "TAJNI" not in r.text


def test_portfolio_pad_rokova_nije_sve_pod_kontrolom(ok):
    k, b = ok
    b.greske["predmet_hronologija"] = RuntimeError("baza nedostupna")
    r = k.get("/portfolio/dashboard", headers=zaglavlje("A"))
    assert r.status_code == 503 and "pod kontrolom" not in r.text


def test_zdravlje_pad_izvora_nije_ocena(ok):
    k, b = ok
    b.greske["billing_entries"] = RuntimeError("baza nedostupna")
    r = k.get("/api/firm/health-index", headers=zaglavlje("A"))
    assert r.status_code == 503 and "score" not in r.text


def test_zdravlje_vraca_deterministicku_ocenu(ok):
    k, _ = ok
    r = k.get("/api/firm/health-index", headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d.get("score"), int) and 0 <= d["score"] <= 100


def test_nema_spoljne_mreze():
    assert SPOLJNI_POKUSAJI == []

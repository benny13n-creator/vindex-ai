# -*- coding: utf-8 -*-
"""NS008 Task 16 — ispravka advokata iz kancelarije A pomaže budućoj ekstrakciji u kancelariji A; B nije pogođena.

Postojeći izričit ugovor (`POST /api/smart-intake/entities/{id}/correct`) upisuje `corrected_value`; nova
ekstrakcija istog (normalizovanog) naziva sudije/suda kod KOLEGE iz iste kancelarije dobija PREDLOG sa poreklom
(„ispravio je … (datum)"). Imena stranaka se nikad ne prenose; dvosmislene ispravke ne daju predlog; vrednost se
ne menja bez potvrde; druga kancelarija ne vidi ništa.
"""
import pytest

import tests.ns008_fake as f8

KA, KB = "e1e1e1e1-1616-4000-8000-000000000001", "e2e2e2e2-1616-4000-8000-000000000002"
J_STARI, J_NOVI, J_B, J_STRANKA = (f"aaaa000{i}-1616-4000-8000-00000000000{i}" for i in range(1, 5))
D_STARI, D_NOVI, D_B = (f"bbbb000{i}-1616-4000-8000-00000000000{i}" for i in range(1, 4))
E_SUDIJA_STARI, E_STRANKA_STARI, E_SUD_STARI = (f"cccc000{i}-1616-4000-8000-00000000000{i}" for i in range(1, 4))
E_SUDIJA_NOVI, E_STRANKA_NOVI, E_SUD_NOVI, E_SUDIJA_B = (f"dddd000{i}-1616-4000-8000-00000000000{i}" for i in range(1, 5))


def _e(eid, did, tip, v, ispravka=None):
    return {"id": eid, "document_id": did, "entity_type": tip, "value": v, "confidence": 0.6, "extraction_method": "regex",
            "reviewed": bool(ispravka), "corrected_value": ispravka}


@pytest.fixture
def svet(monkeypatch):
    k, b = f8.pripremi(monkeypatch, {
        "kancelarije": [{"id": KA, "admin_uid": "uid-X"}, {"id": KB, "admin_uid": "uid-Y"}],
        # A i C su kolege (kancelarija A); B je u kancelariji B
        "kancelarija_clanovi": [{"kancelarija_id": KA, "user_id": "uid-A", "status": "ACTIVE"},
                                {"kancelarija_id": KA, "user_id": "uid-C", "status": "ACTIVE"},
                                {"kancelarija_id": KB, "user_id": "uid-B", "status": "ACTIVE"}],
        "intake_jobs": [{"id": J_STARI, "uploaded_by": "uid-C", "status": "completed", "source": "dropzone",
                         "content_sha256": "1", "storage_path": "x", "created_at": "2026-09-01T00:00:00+00:00"},
                        {"id": J_NOVI, "uploaded_by": "uid-A", "status": "awaiting_review", "source": "dropzone",
                         "content_sha256": "2", "storage_path": "y", "created_at": "2026-10-09T00:00:00+00:00"},
                        {"id": J_B, "uploaded_by": "uid-B", "status": "awaiting_review", "source": "dropzone",
                         "content_sha256": "3", "storage_path": "z", "created_at": "2026-10-09T00:00:00+00:00"}],
        "intake_documents": [{"id": D_STARI, "intake_job_id": J_STARI, "document_type": "presuda", "classification_confidence": 0.9, "ocr_used": False, "created_at": "2026-09-01"},
                             {"id": D_NOVI, "intake_job_id": J_NOVI, "document_type": "presuda", "classification_confidence": 0.9, "ocr_used": False, "created_at": "2026-10-09"},
                             {"id": D_B, "intake_job_id": J_B, "document_type": "presuda", "classification_confidence": 0.9, "ocr_used": False, "created_at": "2026-10-09"}],
        "extracted_entities": [
            _e(E_SUDIJA_STARI, D_STARI, "judge", "Sudija Petrovic", "Sudija Petrović"),
            _e(E_STRANKA_STARI, D_STARI, "plaintiff", "Marko Markovic", "Marko Marković"),
            _e(E_SUD_STARI, D_STARI, "court", "Osnovni sud u Beogradu"),
            _e(E_SUDIJA_NOVI, D_NOVI, "judge", "SUDIJA  PETROVIC"),
            _e(E_STRANKA_NOVI, D_NOVI, "plaintiff", "Marko Markovic"),
            _e(E_SUD_NOVI, D_NOVI, "court", "Osnovni sud u Beogradu"),
            _e(E_SUDIJA_B, D_B, "judge", "Sudija Petrovic"),
        ],
        "intake_review_queue": [],
        "audit_immutable": [{"action": "entity_corrected", "resource_id": E_SUDIJA_STARI, "created_at": "2026-09-02T10:00:00+00:00"}],
    })
    yield k, b
    f8.ocisti()


def _ent(k, job, ko):
    r = k.get(f"/api/smart-intake/jobs/{job}", headers=f8.zaglavlje(ko))
    assert r.status_code == 200, r.text
    return r.json(), {e["entity_id"]: e for e in r.json()["entiteti"]}


def test_kolega_iz_iste_kancelarije_dobija_predlog_sa_poreklom(svet):
    k, _ = svet
    d, e = _ent(k, J_NOVI, "A")
    p = e[E_SUDIJA_NOVI]["predlog_ispravke"]
    assert p["vrednost"] == "Sudija Petrović" and p["trust_class"] == "HUMAN_CORRECTION"
    assert "ispravio je „SUDIJA  PETROVIC“ u „Sudija Petrović“ (02.09.2026.)" in p["razlog"]
    assert e[E_SUDIJA_NOVI]["value"] == "SUDIJA  PETROVIC", "vrednost se ne menja bez potvrde"
    assert d["predlozi_ispravki_stanje"] == "OK"
    assert "predlog_ispravke" in d["dokumenti"][0]["entiteti"][[x["entity_id"] for x in d["dokumenti"][0]["entiteti"]].index(E_SUDIJA_NOVI)]


def test_imena_stranaka_se_nikad_ne_prenose(svet):
    k, _ = svet
    _, e = _ent(k, J_NOVI, "A")
    assert "predlog_ispravke" not in e[E_STRANKA_NOVI]
    assert "predlog_ispravke" not in e[E_SUD_NOVI], "neispravljen sud nema predlog"


def test_druga_kancelarija_nije_pogodjena(svet):
    k, _ = svet
    _, e = _ent(k, J_B, "B")
    assert "predlog_ispravke" not in e[E_SUDIJA_B]


def test_uklonjen_clan_vise_ne_doprinosi(svet):
    k, b = svet
    next(c for c in b.tabele["kancelarija_clanovi"] if c["user_id"] == "uid-C")["status"] = "REMOVED"
    _, e = _ent(k, J_NOVI, "A")
    assert "predlog_ispravke" not in e[E_SUDIJA_NOVI]


def test_dvosmislena_ispravka_bez_predloga(svet):
    k, b = svet
    b.tabele["extracted_entities"].append(_e("eeee0001-1616-4000-8000-000000000001", D_STARI, "judge", "Sudija Petrovic", "Sudija Petrovićka"))
    _, e = _ent(k, J_NOVI, "A")
    assert "predlog_ispravke" not in e[E_SUDIJA_NOVI]


def test_postojeca_ruta_ispravke_odmah_hrani_predloge(svet):
    k, b = svet
    # B ispravlja svoju sudiju — tek tada se B-ova kancelarija uči; A i dalje vidi samo ispravku kancelarije A
    r = k.post(f"/api/smart-intake/entities/{E_SUDIJA_B}/correct", headers=f8.zaglavlje("B"), json={"corrected_value": "Sudija Petrović B"})
    assert r.status_code == 200, r.text
    _, e = _ent(k, J_NOVI, "A")
    assert e[E_SUDIJA_NOVI]["predlog_ispravke"]["vrednost"] == "Sudija Petrović"


def test_pad_pregleda_ne_obara_posao(svet):
    k, b = svet
    import services.law_brain_ispravke as li

    def _pad(*a, **kw):
        raise RuntimeError("down")
    import pytest as _p
    mp = _p.MonkeyPatch()
    mp.setattr(li, "ispravke_kancelarije", _pad)
    try:
        d, e = _ent(k, J_NOVI, "A")
        assert d["predlozi_ispravki_stanje"] == "DEGRADED" and "predlog_ispravke" not in e[E_SUDIJA_NOVI]
    finally:
        mp.undo()


def test_normalizacija():
    from services.law_brain_ispravke import normalizuj
    assert normalizuj("SUDIJA  PETROVIĆ.") == normalizuj("Sudija Petrovic") == "sudija petrovic"
    assert normalizuj("Đorđević") == normalizuj("Djordjevic")

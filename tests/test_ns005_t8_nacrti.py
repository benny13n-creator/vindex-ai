# -*- coding: utf-8 -*-
"""NS005 Task 8 — nacrt podneska u predmetu + staging (advokatska overa): stvarne rute.

POST /api/podnesak (routers/drafting.py): tip iz zatvorenog spiska (422 pre ikakvog
poziva modela), predmet_id mora biti pozivaočev (404 pre poziva modela), critique pass
menja izmišljen navod placeholder-om, `critique_applied` kaže da li je provera
potvrđena, neuspela ekstrakcija se ne naplaćuje.
GET/POST /api/staging/... : samo sopstveni nacrti; tuđ id → 404, stanje netaknuto.
Svi pozivi modela i pretrage su zamenjeni (nijedan ne ide na OpenAI/Pinecone).
"""
import json
import types

import pytest

from tests.ns005_harness import pripremi, ocisti, zaglavlje, SPOLJNI_POKUSAJI

PA, PB = "pred-A-1", "pred-B-1"
OPIS = "Tužilac Ana Jović traži naknadu štete od tuženog Petra Petrovića zbog saobraćajne nezgode od 1.3.2026."


def _baza():
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Jović protiv Petrovića", "status": "aktivan"},
                     {"id": PB, "user_id": "uid-B", "naziv": "Tajni B", "status": "aktivan"}],
        "staging_memory": [
            {"id": "st-A", "user_id": "uid-A", "predmet_id": PA, "tip": "tuzba_naknada_stete", "naziv": "Tužba", "tekst": "x",
             "confidence_score": 0.4, "status": "pending", "is_lawyer_approved": False, "pinecone_indexed": False, "created_at": "2026-10-01"},
            {"id": "st-B", "user_id": "uid-B", "predmet_id": PB, "tip": "tuzba_naknada_stete", "naziv": "TAJNI nacrt B", "tekst": "TAJNO",
             "confidence_score": 0.9, "status": "pending", "is_lawyer_approved": False, "pinecone_indexed": False, "created_at": "2026-10-01"},
        ],
    }


def _odgovor(tekst):
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=tekst))])


@pytest.fixture
def ok(monkeypatch):
    k, b = pripremi(monkeypatch, _baza())
    import shared.permissions as perm
    import shared.usage as us
    import routers.drafting as D

    async def _politika(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

    async def _nista(*a, **kw):
        return None
    naplate = []

    async def _naplati(*a, **kw):
        naplate.append(a)
    monkeypatch.setattr(perm, "get_policy", _politika)
    monkeypatch.setattr(perm, "_check_dependencies", _nista)
    monkeypatch.setattr(us.UsageService, "consume", staticmethod(_naplati))
    pozivi = []

    def _model(oai, **kw):
        pozivi.append(kw.get("model"))
        if kw.get("max_tokens") == 900:   # ekstrakcija entiteta
            return _odgovor(json.dumps({"tuzilac": "Ana Jović", "tuzeni": "Petar Petrović"}))
        return _odgovor(json.dumps({"pravni_osnov": "čl. 154 ZOO"}))
    monkeypatch.setattr(D, "_pozovi_drafting_api", _model)
    import app.services.retrieve as R
    monkeypatch.setattr(R, "retrieve_documents", lambda *a, **kw: (["Zakon o obligacionim odnosima, Član 154: Ko drugome prouzrokuje štetu..."], {}))
    kritike = {"vrednost": {"ima_izmisljenih_navoda": False}}

    async def _kriticar(oai, nacrt, kontekst, tip):
        v = kritike["vrednost"]
        if isinstance(v, Exception):
            raise v
        return v
    monkeypatch.setattr(D, "_pozovi_kriticara", _kriticar)
    import services.quality_gate as QG

    async def _kvalitet(t, tip):
        return {"confidence_score": 0.5, "detail": {}}
    monkeypatch.setattr(QG, "evaluate_draft_quality", _kvalitet)
    yield k, b, pozivi, kritike, naplate
    ocisti()


def test_nepodrzan_tip_422_bez_poziva_modela(ok):
    k, b, pozivi, _, _ = ok
    r = k.post("/api/podnesak", json={"tip": "tuzba_za_svemir", "opis": OPIS, "predmet_id": PA}, headers=zaglavlje("A"))
    assert r.status_code == 422
    assert pozivi == []


def test_tudj_predmet_404_bez_poziva_modela(ok):
    k, b, pozivi, _, naplate = ok
    r = k.post("/api/podnesak", json={"tip": "tuzba_naknada_stete", "opis": OPIS, "predmet_id": PB}, headers=zaglavlje("A"))
    assert r.status_code == 404
    assert pozivi == [] and naplate == []


def test_nacrt_se_generise_nosi_napomenu_i_ide_na_overu(ok):
    k, b, pozivi, _, naplate = ok
    r = k.post("/api/podnesak", json={"tip": "tuzba_naknada_stete", "opis": OPIS, "predmet_id": PA}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "success" and d["critique_applied"] is True and d["ai_generated"] is True
    assert "mora biti pregledan od strane ovlašćenog advokata" in d["odgovor"]
    assert len(naplate) == 1


def test_staging_upis_samo_za_sopstveni_predmet(ok):
    """`_stage_draft_for_review` je fire-and-forget u ruti; ovde se zove direktno."""
    import asyncio
    import routers.drafting as D
    k, b, _, _, _ = ok
    pre = len(b.tabele["staging_memory"])
    asyncio.run(D._stage_draft_for_review({"user_id": "uid-A"}, PA, "zalba_parnicna", "Žalba", "Tekst nacrta"))
    novi = b.tabele["staging_memory"][pre:]
    assert len(novi) == 1 and novi[0]["user_id"] == "uid-A" and novi[0]["predmet_id"] == PA and novi[0].get("status", "pending") == "pending"
    asyncio.run(D._stage_draft_for_review({"user_id": "uid-A"}, PB, "zalba_parnicna", "Žalba", "Upad"))
    assert not [x for x in b.tabele["staging_memory"] if x.get("tekst") == "Upad"]


def test_kritika_menja_izmisljen_clan_placeholderom(ok):
    k, b, pozivi, kritike, _ = ok
    kritike["vrednost"] = {"ima_izmisljenih_navoda": True, "izmisljeni_navodi": ["čl. 9999 ZOO"],
                           "ispravljen_tekst": "TUŽBA ... u skladu sa [proveriti relevantan član] ..."}
    d = k.post("/api/podnesak", json={"tip": "tuzba_naknada_stete", "opis": OPIS, "predmet_id": PA}, headers=zaglavlje("A")).json()
    assert "[proveriti relevantan član]" in d["odgovor"] and "9999" not in d["odgovor"]
    assert d["critique_applied"] is True


def test_pad_kritike_je_vidljiv_signal(ok):
    k, b, pozivi, kritike, _ = ok
    kritike["vrednost"] = RuntimeError("model nedostupan")
    d = k.post("/api/podnesak", json={"tip": "tuzba_naknada_stete", "opis": OPIS, "predmet_id": PA}, headers=zaglavlje("A")).json()
    assert d["critique_applied"] is False


def test_potpuno_neuspela_ekstrakcija_se_ne_naplacuje(ok, monkeypatch):
    k, b, pozivi, _, naplate = ok
    import routers.drafting as D

    def _puca(oai, **kw):
        raise RuntimeError("openai dole")
    monkeypatch.setattr(D, "_pozovi_drafting_api", _puca)
    r = k.post("/api/podnesak", json={"tip": "tuzba_naknada_stete", "opis": OPIS, "predmet_id": PA}, headers=zaglavlje("A"))
    assert r.status_code == 200
    assert naplate == []


def test_staging_samo_sopstveni(ok):
    k, b, _, _, _ = ok
    a = k.get(f"/api/staging/predmet/{PA}", headers=zaglavlje("A")).json()
    assert [x["id"] for x in a["stavke"]] == ["st-A"] and "tekst" not in a["stavke"][0]
    bb = k.get(f"/api/staging/predmet/{PA}", headers=zaglavlje("B")).json()
    assert bb["stavke"] == []


def test_tudj_nacrt_se_ne_odobrava_ni_odbija(ok):
    k, b, _, _, _ = ok
    assert k.post("/api/staging/st-B/approve", headers=zaglavlje("A")).status_code == 404
    assert k.post("/api/staging/st-B/reject", headers=zaglavlje("A")).status_code == 404
    red = [x for x in b.tabele["staging_memory"] if x["id"] == "st-B"][0]
    assert red["status"] == "pending" and red["is_lawyer_approved"] is False


def test_odobren_ispod_praga_ne_ulazi_u_bazu_znanja(ok):
    k, b, _, _, _ = ok
    d = k.post("/api/staging/st-A/approve", headers=zaglavlje("A")).json()
    assert d["status"] == "approved" and d["indexed"] is False
    red = [x for x in b.tabele["staging_memory"] if x["id"] == "st-A"][0]
    assert red["is_lawyer_approved"] is True and red["approved_by"] == "uid-A"


def test_nema_spoljne_mreze():
    assert SPOLJNI_POKUSAJI == []

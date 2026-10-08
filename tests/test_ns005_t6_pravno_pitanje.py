# -*- coding: utf-8 -*-
"""NS005 Task 6 — pravno pitanje u predmetu: stvarna ruta POST /api/pitanje.

STVARNO: api.py ruta, prompt guard, kontekst predmeta, `normalizuj_rezultat`,
i (u testovima bez izvora) STVARNI `main.ask_agent` sa citation/halucination
guard-om. ZAMENJENO: pretrage korpusa/prakse/mišljenja i poziv modela
(`_pozovi_openai`) — model PUCA ako ga iko pozove, pa „nema izvora → model se
ne poziva" postaje proverljivo. Ništa ne ide na OpenAI/Pinecone.
"""
import contextlib
from unittest.mock import patch

import pytest

from tests.ns005_harness import pripremi, ocisti, zaglavlje, SPOLJNI_POKUSAJI

PA = "pred-A-1"


def _baza():
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Jović protiv Petrovića", "status": "aktivan"}],
        "predmet_beleske": [{"id": "b1", "predmet_id": PA, "user_id": "uid-A", "sadrzaj": "TAJNA BELESKA A o svedoku", "created_at": "2026-10-01"}],
        "predmet_istorija": [],
    }


@pytest.fixture
def ok(monkeypatch):
    k, b = pripremi(monkeypatch, _baza())
    import shared.permissions as perm
    import shared.usage as us

    async def _politika(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

    async def _nista(*a, **kw):
        return None

    async def _kredit(*a, **kw):
        return 10
    monkeypatch.setattr(perm, "get_policy", _politika)
    monkeypatch.setattr(perm, "_check_dependencies", _nista)
    monkeypatch.setattr(us.UsageService, "consume", staticmethod(_kredit))
    monkeypatch.setattr(us.UsageService, "refund", staticmethod(_nista))
    import api
    monkeypatch.setattr(api, "_fetch_firm_memory_context", _nista, raising=False)
    monkeypatch.setattr(api, "_get_firma_namespace", _nista, raising=False)
    monkeypatch.setattr(api, "klasifikuj_pitanje", lambda *a, **kw: "opste", raising=False)
    yield k, b
    ocisti()


def _model_zabranjen(*a, **kw):
    raise AssertionError("model je pozvan iako nema pouzdanog izvora")


@contextlib.contextmanager
def _agent_bez_mreze(docs, meta, clan=(None, None), direktno=None):
    """Pravi ask_agent; zamenjene su samo spoljne pretrage i model (koji puca)."""
    import main as M
    with patch.object(M, "retrieve_documents", return_value=(docs, meta)), \
         patch.object(M, "retrieve_sudska_praksa", return_value=[]), \
         patch.object(M, "retrieve_misljenja", return_value=[]), \
         patch.object(M, "ekstrakcija_clana", return_value=clan), \
         patch.object(M, "_direktan_fetch_clana", return_value=direktno or []), \
         patch.object(M, "_pozovi_openai", side_effect=_model_zabranjen) as llm:
        yield llm


def test_bez_pouzdanog_izvora_nema_odgovora_i_model_se_ne_poziva(ok):
    k, _ = ok
    meta = {"confidence": "LOW", "top_score": 0.12, "top_article": "", "top_law": "", "doc_passages": [], "praksa_matches": []}
    with _agent_bez_mreze([], meta) as llm:
        r = k.post("/api/pitanje", json={"pitanje": "Koji je rok zastarelosti za naknadu nematerijalne štete u avio prevozu?"},
                   headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert "izvori" not in d and d.get("confidence") == "LOW"
    assert "Nemam pouzdan odgovor" in d["odgovor"]
    llm.assert_not_called()


def test_izmisljen_clan_se_odbija_bez_modela(ok):
    k, _ = ok
    meta = {"confidence": "HIGH", "top_score": 0.71, "top_article": "Član 200", "top_law": "zakon o obligacionim odnosima",
            "doc_passages": [], "praksa_matches": []}
    docs = ["Zakon o obligacionim odnosima, Član 200: Svako ko drugome prouzrokuje štetu dužan je da je naknadi." * 2]
    with _agent_bez_mreze(docs, meta, clan=("Član 9999", "zakon o obligacionim odnosima")) as llm:
        r = k.post("/api/pitanje", json={"pitanje": "Šta kaže Član 9999 ZOO?"}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert "izvori" not in d
    assert "Član 9999" in d["odgovor"] and "nije pronađen" in d["odgovor"]
    llm.assert_not_called()


def test_pad_korpusa_nije_odsustvo_propisa(ok):
    k, _ = ok
    from app.services.retrieve import IZVOR_ZAKON
    meta = {"confidence": "LOW", "top_score": 0.0, "top_article": "", "top_law": "", "doc_passages": [], "praksa_matches": [],
            "izvori_neuspeh": [IZVOR_ZAKON]}
    with _agent_bez_mreze([], meta) as llm:
        r = k.post("/api/pitanje", json={"pitanje": "Koji je rok za žalbu u parničnom postupku?"}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("retrieval_unavailable") is True and "izvori" not in d
    # POZNATO OGRANIČENJE (NS005, nije ispravljano): ask_agent nosi objašnjenje u
    # `data`, a `normalizuj_rezultat` za status "error" čita samo `message`, pa API
    # vraća generički tekst. Zastavica `retrieval_unavailable` PRELAZI granicu i na
    # njoj V2 gradi upozorenje — tekst odgovora se ne sme čitati kao tvrdnja o zakonu.
    assert "zakon" not in d["odgovor"].lower() or "NIJE" in d["odgovor"]
    llm.assert_not_called()


def _hvataj(uhvaceno, rezultat):
    async def _pokreni(fn, pitanje_za_agenta, *a, **kw):
        uhvaceno.append(pitanje_za_agenta)
        return rezultat
    return _pokreni


ODGOVOR = {"status": "success", "data": "--- PRAVNI ZAKLJUČAK\nOdgovor.", "confidence": "HIGH", "top_score": 0.8,
           "confidence_detail": {"nivo": "HIGH"}, "izvori": [{"zakon": "zakon o obligacionim odnosima", "clan": "Član 200"}]}


def test_kontekst_sopstvenog_predmeta_ulazi_u_upit(ok, monkeypatch):
    k, b = ok
    import api
    uhv = []
    monkeypatch.setattr(api, "pokreni", _hvataj(uhv, dict(ODGOVOR)))
    r = k.post("/api/pitanje", json={"pitanje": "Kako dokazati štetu?", "predmet_id": PA}, headers=zaglavlje("A"))
    d = r.json()
    assert r.status_code == 200 and d["kontekst_predmeta"] is True
    assert "TAJNA BELESKA A" in uhv[0]
    assert d["izvori"] == [{"zakon": "zakon o obligacionim odnosima", "clan": "Član 200"}]
    assert [x["pitanje"] for x in b.tabele["predmet_istorija"]] == ["Kako dokazati štetu?"]


def test_tudj_predmet_ne_ulazi_u_upit_i_ne_upisuje_se(ok, monkeypatch):
    k, b = ok
    import api
    uhv = []
    monkeypatch.setattr(api, "pokreni", _hvataj(uhv, dict(ODGOVOR)))
    r = k.post("/api/pitanje", json={"pitanje": "Kako dokazati štetu?", "predmet_id": PA}, headers=zaglavlje("B"))
    d = r.json()
    assert r.status_code == 200
    assert d["kontekst_predmeta"] is False
    assert "TAJNA BELESKA A" not in uhv[0] and "TAJNA" not in r.text
    assert b.tabele["predmet_istorija"] == []


def test_bez_tokena_401(ok):
    k, _ = ok
    assert k.post("/api/pitanje", json={"pitanje": "Pitanje bez prijave?"}).status_code == 401


def test_nema_spoljne_mreze():
    assert SPOLJNI_POKUSAJI == []

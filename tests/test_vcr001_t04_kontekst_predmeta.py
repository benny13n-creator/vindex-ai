# -*- coding: utf-8 -*-
"""VCR001 T04 — kontekst predmeta se STVARNO koristi u pravnom pitanju.

A) Pretraga dokumenata zna za trenutni predmet. `/api/pitanje` nikad nije prosleđivao `current_predmet_id`, pa su
   pojačanje istog predmeta i suženje posle `rag_acl._MAX_IN` bili mrtvi. Sada ruta poziva `ask_agent` unutar
   kanonskog `shared/ai_provenance.case_context`, a `retrieve_documents` iz njega čita predmet. ACL ostaje jedina
   kapija: predmet iz konteksta ne proširuje dozvoljeni skup.
B) Odgovor kaže ZAŠTO kontekst nije ušao (`kontekst_predmeta_stanje`): predmet bez beleški i činjenica NIJE
   „predmet nije mogao da se pročita“.
"""
from unittest.mock import MagicMock, patch

import pytest

from shared.ai_provenance import _case_ctx, case_context
from tests.ns005_harness import zaglavlje
from tests.test_institutional_rag_upgrade import _stub_retrieve_llm
from tests.test_ns005_t6_pravno_pitanje import ODGOVOR, PA, ok  # noqa: F401


# ── A) retrieval ──────────────────────────────────────────────────────────────────────────────────────────────────
def _match(pid, score, tekst):
    m = MagicMock()
    m.metadata = {"predmet_id": pid, "type": "case_doc", "chunk_index": 0, "article_label": "", "text": tekst}
    m.score = score
    return m


def _trazi(dozvoljeni, **kw):
    from app.services.retrieve import retrieve_documents
    idx = MagicMock()
    uhv = []

    def _q(**a):
        uhv.append(a.get("filter"))
        r = MagicMock()
        r.matches = ([_match("predmet-NEW", 0.60, "Sadržaj iz trenutnog predmeta."),
                      _match("predmet-OLD", 0.62, "Sadržaj iz ranijeg predmeta.")]
                     if a.get("namespace") == "kancelarija_kanc-1" else [])
        return r
    idx.query.side_effect = _q
    emb = MagicMock()
    emb.embed_query.return_value = [0.0] * 3072
    coh = MagicMock()
    coh.rerank.side_effect = Exception("no cohere")
    with _stub_retrieve_llm(), patch("app.services.retrieve._get_index", return_value=idx), \
            patch("app.services.retrieve._get_embeddings", return_value=emb), \
            patch("app.services.retrieve._get_cohere", return_value=coh):
        _, meta = retrieve_documents("upit", kancelarija_namespace="kancelarija_kanc-1",
                                     dozvoljeni_predmeti=dozvoljeni, **kw)
    return meta["doc_passages"], uhv


def test_predmet_iz_konteksta_daje_prioritet_trenutnom_predmetu():
    with case_context(predmet_id="predmet-NEW", module_name="pravno_pitanje"):
        pas, _ = _trazi(["predmet-NEW", "predmet-OLD"])
    assert pas[0]["predmet_id"] == "predmet-NEW" and pas[0]["same_case"] is True
    assert {p["predmet_id"]: p["same_case"] for p in pas}["predmet-OLD"] is False


def test_bez_konteksta_nema_prioriteta_kontrola():
    """Negativna kontrola: isti pogoci bez konteksta — viši sirovi skor (raniji predmet) je prvi, ništa nije
    „isti predmet“. Dokazuje da prethodni test meri kontekst, a ne rangiranje fixture-a."""
    pas, _ = _trazi(["predmet-NEW", "predmet-OLD"])
    assert pas[0]["predmet_id"] == "predmet-OLD" and not any(p["same_case"] for p in pas)


def test_eksplicitan_parametar_ima_prednost_nad_kontekstom():
    with case_context(predmet_id="predmet-OLD"):
        pas, _ = _trazi(["predmet-NEW", "predmet-OLD"], current_predmet_id="predmet-NEW")
    assert pas[0]["predmet_id"] == "predmet-NEW"


def test_predmet_iz_konteksta_ne_prosiruje_acl():
    """Predmet iz konteksta koji NIJE u dozvoljenom skupu: filter ostaje tačno dozvoljeni skup."""
    with case_context(predmet_id="predmet-TUDJ"):
        _, filteri = _trazi(["predmet-NEW", "predmet-OLD"])
    kanc = [f for f in filteri if f and "predmet_id" in str(f)]
    assert kanc and all("predmet-TUDJ" not in str(f) for f in kanc)


def test_iznad_max_in_suzava_na_trenutni_predmet_iz_konteksta():
    from shared import rag_acl
    mnogo = ["predmet-NEW"] + [f"p-{i}" for i in range(rag_acl._MAX_IN + 5)]
    with case_context(predmet_id="predmet-NEW"):
        _, filteri = _trazi(mnogo)
    kanc = [f for f in filteri if f and "predmet_id" in str(f)]
    assert kanc and all("p-1" not in str(f) and "predmet-NEW" in str(f) for f in kanc)


# ── ruta /api/pitanje ─────────────────────────────────────────────────────────────────────────────────────────────
def _hvataj_kontekst(uhv):
    async def _pokreni(fn, pitanje_za_agenta, *a, **kw):
        uhv.append((_case_ctx.get() or {}).get("predmet_id"))
        return dict(ODGOVOR)
    return _pokreni


def test_ruta_poziva_agenta_u_kontekstu_sopstvenog_predmeta(ok, monkeypatch):  # noqa: F811
    k, _ = ok
    import api
    uhv = []
    monkeypatch.setattr(api, "pokreni", _hvataj_kontekst(uhv))
    r = k.post("/api/pitanje", json={"pitanje": "Kako dokazati štetu?", "predmet_id": PA}, headers=zaglavlje("A"))
    assert r.status_code == 200 and uhv == [PA]
    assert r.json()["kontekst_predmeta_stanje"] == "UKLJUCEN"
    assert (_case_ctx.get() or {}).get("predmet_id") is None          # kontekst ne curi posle zahteva


def test_tudj_predmet_ne_ulazi_u_kontekst_pretrage(ok, monkeypatch):  # noqa: F811
    k, _ = ok
    import api
    uhv = []
    monkeypatch.setattr(api, "pokreni", _hvataj_kontekst(uhv))
    r = k.post("/api/pitanje", json={"pitanje": "Kako dokazati štetu?", "predmet_id": PA}, headers=zaglavlje("B"))
    assert r.status_code == 200 and uhv == [None]
    assert r.json()["kontekst_predmeta"] is False and r.json()["kontekst_predmeta_stanje"] == "NIJE_PROCITAN"


def test_pitanje_bez_predmeta_nema_stanja(ok, monkeypatch):  # noqa: F811
    k, _ = ok
    import api
    uhv = []
    monkeypatch.setattr(api, "pokreni", _hvataj_kontekst(uhv))
    r = k.post("/api/pitanje", json={"pitanje": "Kako dokazati štetu?"}, headers=zaglavlje("A"))
    assert r.status_code == 200 and uhv == [None]
    assert r.json()["kontekst_predmeta"] is None and "kontekst_predmeta_stanje" not in r.json()


# ── B) stanje konteksta ───────────────────────────────────────────────────────────────────────────────────────────
def test_prazan_predmet_je_prazan_a_ne_neprocitan(ok, monkeypatch):  # noqa: F811
    k, b = ok
    import api
    b.tabele["predmet_beleske"].clear()
    monkeypatch.setattr(api, "pokreni", _hvataj_kontekst([]))
    d = k.post("/api/pitanje", json={"pitanje": "Kako dokazati štetu?", "predmet_id": PA}, headers=zaglavlje("A")).json()
    assert d["kontekst_predmeta"] is False and d["kontekst_predmeta_stanje"] == "PRAZAN"


def test_sumnjiva_beleska_je_izostavljena(ok, monkeypatch):  # noqa: F811
    k, b = ok
    import api
    import security.prompt_guard as pg
    pravi = pg.analyze
    monkeypatch.setattr(pg, "analyze", lambda t: MagicMock(blocked=True) if "TAJNA" in (t or "") else pravi(t))
    monkeypatch.setattr(api, "pokreni", _hvataj_kontekst([]))
    d = k.post("/api/pitanje", json={"pitanje": "Kako dokazati štetu?", "predmet_id": PA}, headers=zaglavlje("A")).json()
    assert d["kontekst_predmeta"] is False and d["kontekst_predmeta_stanje"] == "IZOSTAVLJEN"


def test_pad_citanja_je_neprocitan(ok, monkeypatch):  # noqa: F811
    k, b = ok
    import api
    b.greske["predmet_beleske"] = Exception('{"code": "57014", "message": "statement timeout"}')
    monkeypatch.setattr(api, "pokreni", _hvataj_kontekst([]))
    d = k.post("/api/pitanje", json={"pitanje": "Kako dokazati štetu?", "predmet_id": PA}, headers=zaglavlje("A")).json()
    assert d["kontekst_predmeta"] is False and d["kontekst_predmeta_stanje"] == "NIJE_PROCITAN"

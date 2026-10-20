# -*- coding: utf-8 -*-
"""Night Sprint IV — Task 7: jedan sintetički tok institucionalnog znanja kroz STVARNE rute i stvaran kod.

Svet: izmišljena kancelarija iz `tests/ns008_scenario.py` (A vlasnik, B kolega iste kancelarije, nije delegiran).
Lažna baza u memoriji; model, Pinecone ingest i provera citata su zamenjeni. Nijedan spoljni poziv: conftest
mrežni čuvar obara svaki pokušaj, a test na kraju proverava da su sve tačke spoljnog sveta bile lažne.

Koraci (redosled iz zadatka):
  1  sintetički predmet i vlasništvo            7  AI nacrt → izmena advokata → odobrenje → pad promocije
  2–3 dokument sa PRIMAOCEM, model tvrdi tužioca  8  oporavak: ponovno odobrenje ne duplira — oporavak NE POSTOJI
  4  korekcija advokata, profil pada pa uspe      9  B (neovlašćen) ne dobija ništa od A-ovog predmeta
  5  potvrđen ishod                              10  novi A-ov predmet: znanje kancelarije sa poreklom
  6  ponovljen ishod se ne broji dvaput          11  ograničenja pouzdanosti i tvrdnje vidljive korisniku
                                                12  bez mreže, produkcijske baze i pravog vektorskog indeksa
"""
import asyncio
import json

import pytest

import tests.ns008_fake as f8
from tests import ns008_scenario as sc
from tests.test_n06_semantika_ekstrakcije import _obradi_tekst

IZMENA = "IZMENA ADVOKATA: dodat predlog za saslušanje svedoka Jovanovića."
DOSTAVNICA = "\n".join(["DOSTAVNICA", "Pošiljalac: Osnovni sud u Beogradu", "Primalac: Tehnoprom DOO",
                        "Uručeno dana 12.09.2026. godine."])


@pytest.fixture
def svet(monkeypatch):
    t = sc.tabele()
    t.update({"ai_corrections": [], "firm_style_profile": []})
    k, b = f8.pripremi(monkeypatch, t)
    import routers.corrections as C
    import routers.drafting as D
    import shared.permissions as perm
    import shared.usage as us
    import app.services.retrieve as rt
    import uploaded_doc.ingest as ing
    import uploaded_doc.chunker as chk
    st = {"ingest": [], "tekst_promocije": [], "model": 0}

    async def _pol(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

    async def _nista(*a, **kw):
        return None

    async def _model_pada(*a, **kw):
        st["model"] += 1
        raise RuntimeError("model nedostupan (test)")

    def _ingest_pada(manifest, *a, **kw):
        st["ingest"].append(kw.get("namespace_override"))
        raise RuntimeError("pinecone 503 (test)")

    pravi_chunk = chk.chunk_document

    def _chunk(tekst, meta):
        st["tekst_promocije"].append(tekst)
        return pravi_chunk(tekst, meta)

    monkeypatch.setattr(perm, "get_policy", _pol)
    monkeypatch.setattr(perm, "_check_dependencies", _nista)
    monkeypatch.setattr(us.UsageService, "consume", staticmethod(_nista))
    monkeypatch.setattr(C, "_pozovi_correction_api", _model_pada)
    import routers.learning as L

    def _model_pada_sync(*a, **kw):
        st["model"] += 1
        raise RuntimeError("model nedostupan (test)")
    monkeypatch.setattr(L, "_pozovi_learning_api", _model_pada_sync)
    monkeypatch.setattr(rt, "_direktan_fetch_clana", lambda *a, **kw: [{"id": "clan-test"}])
    monkeypatch.setattr(ing, "ingest_session", _ingest_pada)
    monkeypatch.setattr(chk, "chunk_document", _chunk)
    try:
        from shared.rate import limiter
        monkeypatch.setattr(limiter, "enabled", False)
    except Exception:
        pass
    yield k, b, st
    f8.ocisti()


def _H(ko):
    return f8.zaglavlje(ko)


def test_tok_institucionalnog_znanja(svet):
    k, b, st = svet
    import routers.corrections as C
    import routers.drafting as D
    import routers.learning as L

    # 1. sintetički predmet i vlasništvo
    assert {p["id"]: p["user_id"] for p in b.tabele["predmeti"]}[sc.OLD1] == "uid-A"
    assert k.get(f"/api/law-brain/predmeti/{sc.OLD1}", headers=_H("B")).status_code == 404

    # 2–3. dostavnica sa PRIMAOCEM; model tvrdi da je primalac tužilac → nije prihvaćeno
    _, e = _obradi_tekst(DOSTAVNICA, {"document_type": "other", "confidence": 0.2},
                         plaintiff=("Tehnoprom DOO", 0.95))
    assert e["plaintiff"]["value"] is None, "PRIMALAC je postao TUŽILAC"

    # 4. korekcija advokata: hvatanje (model klasifikacije pada → korekcija ipak sačuvana)
    r = k.post("/api/corrections/capture", headers=_H("A"), json={
        "original_output": "Predlažemo da sud usvoji tužbeni zahtev u celosti i obaveže tuženog na troškove.",
        "edited_output": "Predlažemo da sud usvoji tužbeni zahtev.\n- troškovi postupka\n- kamata",
        "context_type": "drafting", "predmet_id": sc.OLD1})
    assert r.status_code == 200 and r.json()["captured"] is True, r.text
    assert len(b.tabele["ai_corrections"]) == 1 and b.tabele["ai_corrections"][0]["processed"] is False
    b.greske["firm_style_profile"] = Exception("db down (test)")
    rez = asyncio.run(C._update_style_profile(sc.K1, b))
    assert rez["ok"] is False and b.tabele["ai_corrections"][0]["processed"] is False, "korekcija izgubljena"
    del b.greske["firm_style_profile"]
    rez = asyncio.run(C._update_style_profile(sc.K1, b))
    assert rez["ok"] is True and rez["processed"] == 1 and b.tabele["ai_corrections"][0]["processed"] is True
    assert b.tabele["firm_style_profile"][0]["korekcija_count"] == 1

    # 5–6. potvrđen ishod; ponovljeno slanje se ne broji
    telo = {"predmet_id": sc.OLD1, "ishod": "pobeda", "presudni_faktori": ["svedoci"]}
    r1 = k.post("/api/learning/outcome", headers=_H("A"), json=telo)
    r2 = k.post("/api/learning/outcome", headers=_H("A"), json=telo)
    assert r1.status_code == r2.status_code == 200 and r2.json()["ponovljen_ishod"] is True
    assert len(b.tabele["outcome_log"]) == 1
    cp = [x for x in b.tabele["case_patterns"] if x["user_id"] == "uid-A"]
    assert [(x["faktor"], x["pobede"], x["porazi"], x["ukupno"]) for x in cp] == [("svedoci", 1, 0, 1)]

    # 7. AI nacrt → izmena advokata (sačuvana) → odobrenje → pad promocije
    izmenjen = sc.TEKST_TUZBE + " Sud je nadležan — član 15. Zakona o radu. " + IZMENA
    r = k.patch(f"/api/staging/{sc.S_TUZBA}/tekst", headers=_H("A"), json={"tekst": izmenjen})
    assert r.status_code == 200 and r.json()["confidence_score"] >= D._APPROVAL_CONFIDENCE_THRESHOLD, r.text
    r = k.post(f"/api/staging/{sc.S_TUZBA}/approve", headers=_H("A"))
    d = r.json()
    assert r.status_code == 200 and d["indexed"] is False and d["razlog"] == "INDEKSIRANJE_NIJE_USPELO", d
    assert "ispod praga" not in d["poruka"]
    assert len(st["ingest"]) == 1 and st["ingest"][0] == f"kancelarija_{sc.K1}"
    assert st["tekst_promocije"] == [izmenjen], "promovisan je zastareo tekst pre izmene advokata"
    red = next(x for x in b.tabele["staging_memory"] if x["id"] == sc.S_TUZBA)
    assert (red["status"], red["is_lawyer_approved"], red["pinecone_indexed"]) == ("approved", True, False)

    # 8. oporavak: ponovno odobrenje ne promoviše ponovo (bez duplikata) — ali oporavka NEMA (blocker u izveštaju)
    r = k.post(f"/api/staging/{sc.S_TUZBA}/approve", headers=_H("A"))
    assert r.json()["indexed"] is False and len(st["ingest"]) == 1

    # 9. B (ista kancelarija, nije delegiran) ne dobija ništa od A-ovog predmeta
    for ruta in (f"/api/law-brain/predmeti/{sc.OLD1}", f"/api/law-brain/predmeti/{sc.CUR}"):
        assert k.get(ruta, headers=_H("B")).status_code == 404
    z = json.dumps(k.get("/api/law-brain/znanje", headers=_H("B")).json(), ensure_ascii=False)
    for tajna in (sc.OLD1, "Marković protiv", IZMENA, sc.S_TUZBA):
        assert tajna not in z, tajna
    for ruta in ("/api/firma-memorija/sve", "/api/firma-memorija/pretrazi"):
        assert IZMENA not in k.get(ruta, headers=_H("B")).text

    # 10. novi A-ov predmet: znanje kancelarije sa poreklom
    d = k.get(f"/api/law-brain/predmeti/{sc.CUR}", headers=_H("A")).json()
    slicni = d["similar_cases"]["stavke"]
    assert slicni and slicni[0]["predmet_id"] == sc.OLD1 and slicni[0]["zasto"]
    radovi = d["verified_artifacts"]["stavke"]
    assert [a["source_ref"]["id"] for a in radovi] == [sc.S_TUZBA]
    assert radovi[0]["lineage"] == ["AI_GENERATED", "LAWYER_VERIFIED"]
    assert sc.S_NACRT2 not in json.dumps(d), "neodobren AI nacrt ušao u znanje kancelarije"

    # 11. ograničenja pouzdanosti i tvrdnje vidljive korisniku
    o = d["descriptive_outcomes"]
    assert o["uzorak"] == 1 and o["mali_uzorak"] is True
    tekst = json.dumps(d, ensure_ascii=False).lower()
    for zabranjeno in ("šansa", "verovatnoć", "win rate", "%"):
        assert zabranjeno not in tekst, zabranjeno
    assert "nije pravni izvor" in d["napomena"].lower()
    s = asyncio.run(L.slicni_predmeti(predmet_id=sc.CUR, request=_lazni_request(), user={"user_id": "uid-A"}))
    assert s["stanje"] == "NEDOVOLJNO_PODATAKA" and "%" not in s["strategija_preporuka"]

    # 12. bez mreže, produkcijske baze i pravog indeksa: svaka spoljna tačka je bila lažna
    assert D._get_supa() is b and L._get_supa() is b and C._get_supa() is b
    assert st["model"] >= 1, "model je zamenjen (pad), ne pozvan"
    import uploaded_doc.ingest as ing
    assert ing.ingest_session.__name__ == "_ingest_pada"


def _lazni_request():
    from starlette.requests import Request
    return Request({"type": "http", "method": "GET", "path": "/api/learning/slicni-predmeti", "headers": [],
                    "query_string": b"", "client": ("127.0.0.1", 0), "server": ("testserver", 80),
                    "scheme": "http", "root_path": "", "app": None})

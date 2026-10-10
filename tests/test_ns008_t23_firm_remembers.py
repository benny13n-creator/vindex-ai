# -*- coding: utf-8 -*-
"""NS008 Task 23 — „Kancelarija pamti": realističan E2E kroz STVARNE rute (tests/ns008_scenario.py).

Istorija nastaje rutama (ishod zatvara predmet + trajni događaj, advokat odobrava tužbu, advokat potvrđuje
lekciju). Zatim: CURRENT se otvara → Law Brain nalazi OLD-1, objašnjava zašto, OLD-2 nije iznad njega, vezuje
overen rad i potvrđenu lekciju, opisuje ishode sa imeniocem, ne govori o šansi, ne pretvara iskustvo u pravni
autoritet; sinteza citira samo stvarne izvore; pre klika nema poziva modela. Opoziv rada i lekcije se odmah vidi.
"""
import json
import re

import pytest

import tests.ns008_fake as f8
from tests import ns008_scenario as sc


@pytest.fixture
def kancelarija(monkeypatch):
    k, b = f8.pripremi(monkeypatch, sc.tabele())
    import routers.drafting as drafting
    import shared.permissions as perm
    import shared.usage as us
    import services.law_brain_sinteza as S
    stanje = {"promote": [], "model": [], "krediti": [], "odgovor": None}

    async def _promote(supa, row):
        stanje["promote"].append(row["id"])
        return True

    async def _pol(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

    async def _nista(*a, **kw):
        return None

    async def _kredit(*a, **kw):
        stanje["krediti"].append(a[2] if len(a) > 2 else None)

    async def _model(prompt, pid):
        stanje["model"].append(prompt)
        return json.dumps(stanje["odgovor"](prompt))
    monkeypatch.setattr(drafting, "_promote_staged_draft_to_pinecone", _promote)
    monkeypatch.setattr(perm, "get_policy", _pol)
    monkeypatch.setattr(perm, "_check_dependencies", _nista)
    monkeypatch.setattr(us.UsageService, "consume", staticmethod(_kredit))
    monkeypatch.setattr(S, "_pozovi_model_sinteze", _model)
    istorija = sc.pripremi_istoriju(k, f8.zaglavlje)
    yield k, b, stanje, istorija
    f8.ocisti()


def _model_iz_prompta(prompt):
    r = dict(re.findall(r"^(R\d+) (\[[A-Z_]+\].*)$", prompt, re.M))
    slican = next(x for x, t in r.items() if "Raniji predmet 1" in t)
    ishod = next(x for x, t in r.items() if "HUMAN_CONFIRMED_OUTCOME" in t)
    rad = next(x for x, t in r.items() if "Overen rad" in t)
    lek = next(x for x, t in r.items() if "Potvrđena lekcija" in t)
    return {"tvrdnje": [
        {"tekst": "Kancelarija je vodila sličan spor o otkazu pred istim sudom.", "vrsta": "iskustvo", "refs": [slican]},
        {"tekst": "U tom sporu advokat je zabeležio ishod pobeda.", "vrsta": "ishod", "refs": [ishod]},
        {"tekst": "Postoji overena tužba za poništaj rešenja o otkazu koja može biti polazna osnova.", "vrsta": "overen_rad", "refs": [rad]},
        {"tekst": "Potvrđena praksa kancelarije: odmah pribaviti dostavnicu rešenja i svedoke.", "vrsta": "overen_rad", "refs": [lek]},
        {"tekst": "Šansa za uspeh je velika.", "vrsta": "iskustvo", "refs": [slican]},
        {"tekst": "Prema Zakonu o radu otkaz je nezakonit.", "vrsta": "iskustvo", "refs": [slican]},
    ]}


def test_kancelarija_pamti(kancelarija):
    k, b, st, ist = kancelarija
    # istorija nastala stvarnim rutama
    assert all(r.status_code == 200 for r in ist.values()), {n: r.status_code for n, r in ist.items()}
    assert {p["id"]: p["status"] for p in b.tabele["predmeti"]}[sc.OLD1] == "zatvoren"
    assert sum(1 for e in b.tabele["events"] if e.get("event_type") == "MatterBecameTerminal") == 2, "trajni događaj zatvaranja"
    assert st["promote"] == [sc.S_TUZBA]

    # 1. CURRENT se otvara (bez modela i kredita)
    r = k.get(f"/api/law-brain/predmeti/{sc.CUR}", headers=f8.zaglavlje("A"))
    assert r.status_code == 200
    d = r.json()
    assert st["model"] == [] and st["krediti"] == [], "11. nema poziva modela pre klika"

    # 2–4. nalazi OLD-1, objašnjava zašto, OLD-2 nije iznad njega
    sl = d["similar_cases"]["stavke"]
    assert sl and sl[0]["predmet_id"] == sc.OLD1
    assert sl[0]["zasto"] == ("Sličan jer: isti tip predmeta (radni); ista oblast (radno); isti sud (Osnovni sud u Beogradu); "
                              "iste vrste dokaza (dokaz, svedok); iste vrste protivrečnosti (cinjenica_cinjenica).")
    assert sl[0]["bodovi"] == 3 + 2 + 1 + 2 + 1 and [x["bodovi"] for x in sl[0]["razlozi"]] == [3, 2, 1, 2, 1]
    ids = [s["predmet_id"] for s in sl]
    assert sc.OLD2 not in ids or ids.index(sc.OLD2) > ids.index(sc.OLD1)

    # 5. overen završni rad (ne AI nacrt na čekanju)
    radovi = d["verified_artifacts"]["stavke"]
    assert [a["source_ref"]["id"] for a in radovi] == [sc.S_TUZBA]
    assert radovi[0]["trust_class"] == "LAWYER_VERIFIED_ARTIFACT" and radovi[0]["lineage"] == ["AI_GENERATED", "LAWYER_VERIFIED"]

    # 6. potvrđena lekcija (predlog AI nije smernica)
    assert [x["source_ref"]["id"] for x in d["confirmed_lessons"]["stavke"]] == [sc.L_POTVRDJENA]
    assert d["confirmed_lessons"]["kandidata"] == 1

    # 7. opis ishoda sa imeniocem
    o = d["descriptive_outcomes"]
    assert o["po_ishodu"] == {"pobeda": 1} and o["uzorak"] == 1 and o["mali_uzorak"] is True
    assert "Veličina uzorka: 1." in o["recenice"]

    # 8–9. bez šanse, iskustvo nije pravni autoritet
    tekst = json.dumps(d, ensure_ascii=False).lower()
    for zabranjeno in ("šansa", "verovatnoć", "win rate", "%"):
        assert zabranjeno not in tekst, zabranjeno
    assert "nije pravni izvor" in d["napomena"].lower()

    # 10. sinteza: samo stvarni izvori, tačno jedan poziv modela i jedan kredit
    st["odgovor"] = _model_iz_prompta
    s = k.post(f"/api/law-brain/predmeti/{sc.CUR}/sinteza", headers=f8.zaglavlje("A")).json()
    assert len(st["model"]) == 1 and st["krediti"] == ["precedenti"]
    assert len(s["tvrdnje"]) == 4 and s["odbaceno"] == 2
    poznati = {json.dumps(x["source_ref"], sort_keys=True) for x in s["reference"]}
    assert all(json.dumps(r_, sort_keys=True) in poznati for t in s["tvrdnje"] for r_ in t["source_refs"])
    assert {r_["id"] for t in s["tvrdnje"] for r_ in t["source_refs"]} >= {sc.S_TUZBA, sc.L_POTVRDJENA}

    # Opoziv: advokat odbija tužbu i odbacuje lekciju → CURRENT odmah to vidi
    assert k.post(f"/api/staging/{sc.S_TUZBA}/reject", headers=f8.zaglavlje("A")).status_code == 200
    assert k.patch(f"/api/learning/lessons/{sc.L_POTVRDJENA}/potvrdi", headers=f8.zaglavlje("A"),
                   json={"akcija": "odbaci", "komentar": "Zastarelo posle izmene prakse."}).status_code == 200
    d2 = k.get(f"/api/law-brain/predmeti/{sc.CUR}", headers=f8.zaglavlje("A")).json()
    assert d2["verified_artifacts"]["stavke"] == [] and d2["confirmed_lessons"]["stavke"] == []
    assert d2["similar_cases"]["stavke"][0]["predmet_id"] == sc.OLD1, "istorija predmeta ostaje; samo opozvano nestaje"
    st["odgovor"] = lambda prompt: {"tvrdnje": []}
    s2 = k.post(f"/api/law-brain/predmeti/{sc.CUR}/sinteza", headers=f8.zaglavlje("A")).json()
    assert sc.S_TUZBA not in json.dumps(s2) and sc.L_POTVRDJENA not in json.dumps(s2)
    assert TEKST_U_PROMPTU not in st["model"][-1]


TEKST_U_PROMPTU = "TUŽBA radi poništaja rešenja o otkazu"


def test_kolega_iz_kancelarije_ne_vidi_istoriju_advokata_a(kancelarija):
    k, _, _, _ = kancelarija
    z = k.get("/api/law-brain/znanje", headers=f8.zaglavlje("B")).json()
    t = json.dumps(z, ensure_ascii=False)
    assert "Marković" not in t and "TUŽBA" not in t and "dostavnicu" not in t
    assert "tabelarni pregled rokova" in t, "opšta beleška kancelarije je deljena"

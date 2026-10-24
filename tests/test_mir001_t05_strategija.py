# -*- coding: utf-8 -*-
"""MIR001 TASK-05 (MIR-02) — strategija zasnovana na spisu kroz POSTOJEĆI put: V2 savetnik „litigation“
(`POST /api/agents/run` + `predmet_id`). Novi agent se ne uvodi.

Deterministički deo: šta strateški savetnik STVARNO dobija (svih 7 dokumenata, sporne tačke obe strane, zabrana
procenata u sistemskom promptu), šta se menja kad kroz STVARAN prijem stigne materijalno značajan DOK-08, i da korisnik
bez tarife dobija odbijanje bez poziva modela i bez naplate. Sa `MIR001_SNIMAK` snimljene poruke (pre i posle DOK-08)
idu na STVARAN model van ovog procesa (scratchpad), gde se meri sadržaj.
"""
import json
import os

import pytest

from tests import mir001_golden_case as gc
from tests.test_mir001_t02_prijem_spisa import _obradi_sve, _otpremi_sve, _prikaci
from tests.test_mir001_t04_savetnik_spis import _OCR, _pitaj, savetnik  # noqa: F401
from tests.test_osb002_solo_tok import A, _do_kraja_dogadjaja, solo  # noqa: F401

treba_ocr = pytest.mark.skipif(_OCR is None, reason="Tesseract nije dostupan — DOK-05 (sken) se ne može pročitati")

PITANJE = ("Pripremi radnu strategiju za tuzioca za dalji tok ovog postupka: procesno stanje, stav tuzioca, stav tuzenog, "
           "koje cinjenice su potkrepljene a koje sporne, sta je relevantno iz nalaza vestaka, koji dokazi nedostaju, "
           "moguce procesne opcije, argumenti za i protiv i sledeci koraci koje advokat treba da razmotri.")


def _dodaj_kasniji(k, b, pid):
    [x] = _otpremi_sve(k, [gc.KASNIJI])
    assert x["ok"], x
    _obradi_sve()
    f = _prikaci(k, x["job_id"], pid)
    assert f.status_code == 200 and f.json()["dokumenata_povezano"] == 1, f.text
    _do_kraja_dogadjaja(b, najvise=40)


@treba_ocr
def test_strategija_dobija_ceo_spis_sporne_tacke_i_promenu(savetnik):
    k, b, pid, doks, snimljeno = savetnik
    o1 = _pitaj(k, pid, "litigation", PITANJE)
    pre = snimljeno[-1]
    iz1 = o1["izvori_predmeta"]
    assert iz1["dokumenata_u_predmetu"] == 7 and iz1["svi_dokumenti_u_celini"] is True
    tekst = pre["user"].rsplit("Zahtev:", 1)[0]
    for nid in gc.NAVODI:                                          # svaki ključni navod spisa je u poruci modelu
        assert gc.NAVODI[nid]["tekst"] in tekst, nid
    assert "SPORNE TAČKE PREDMETA" in tekst and all(x["pitanje"] in tekst for x in gc.PROTIVRECNOSTI)
    assert "Ne navoditi procentualne šanse" in pre["system"]         # zabrana procenata je u sistemskom promptu
    # pravila rada sa spisom (TASK-05): izvor uz svaku činjenicu, navod ≠ činjenica, procesno stanje prvo, šta menja novo
    for pravilo in ("veži za oznaku dokumenta", "nije utvrđena činjenica", "nikad „veštak je utvrdio/potvrdio“",
                    "## 0. PROCESNO STANJE", "**Šta menja <oznaka najnovijeg dokumenta>:**", "navedi kao nedostajući",
                    "proveri da li je već u spisu", "istekao rok navedi kao istekao"):
        assert pravilo in pre["system"], pravilo
    from datetime import date
    assert f"Današnji datum: {date.today().isoformat()}" in tekst                # rokovi se mogu računati
    assert "Snaga predmeta" not in tekst and "%" not in tekst.split("EVIDENCIJA IZVORA")[0].split("[KRAJ DOKUMENATA]")[-1]
    assert gc.KASNIJA_PROMENA["navod"] not in tekst

    _dodaj_kasniji(k, b, pid)
    o2 = _pitaj(k, pid, "litigation", PITANJE)
    posle = snimljeno[-1]
    iz2 = o2["izvori_predmeta"]
    assert iz2["dokumenata_u_predmetu"] == 8 and iz2["svi_dokumenti_u_celini"] is True
    tekst2 = posle["user"].rsplit("Zahtev:", 1)[0]
    assert gc.KASNIJA_PROMENA["navod"] in tekst2 and "rok od 8 dana od dana dopune" in tekst2
    assert "[DOK-08: " + gc.KASNIJI["ime"] in tekst2
    put = os.environ.get("MIR001_SNIMAK")
    if put:
        with open(put, "w", encoding="utf-8") as f:
            json.dump({"S_pre": {"agent": "litigation", "pitanje": PITANJE, "poruka": pre},
                       "S_posle": {"agent": "litigation", "pitanje": PITANJE, "poruka": posle}}, f, ensure_ascii=False, indent=1)


@treba_ocr
def test_bez_tarife_odbijanje_bez_poziva_modela_i_bez_naplate(savetnik, monkeypatch):
    k, b, pid, doks, snimljeno = savetnik
    import shared.permissions as perm

    async def _politika(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "minimum_plan": "professional"}
    monkeypatch.setattr(perm, "get_policy", _politika)
    monkeypatch.setattr(perm, "_ensure_profile", lambda uid, email="": {"id": uid, "subscription_type": "basic"})
    monkeypatch.setattr(perm, "effective_tier", lambda profil: "basic")
    n_model, n_naplata = len(snimljeno), len(b.naplate)
    r = k.post("/api/agents/run", json={"agent": "litigation", "task": PITANJE, "predmet_id": pid}, headers=A)
    assert r.status_code == 403 and "Professional" in r.json()["detail"], r.text
    assert len(snimljeno) == n_model and len(b.naplate) == n_naplata
    r = k.post("/api/agents/run-parallel", json={"task": PITANJE, "predmet_id": pid}, headers=A)
    assert r.status_code == 403 and len(snimljeno) == n_model

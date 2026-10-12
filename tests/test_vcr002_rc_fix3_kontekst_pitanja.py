# -*- coding: utf-8 -*-
"""VCR002 Release Closure — FIX 3: kontekst predmeta u `/api/pitanje` ne sme AI tvrdnju da proglasi utvrđenom činjenicom.

Stvaran predmet iz T03 (tri dokumenta kroz Smart Intake, tvrdnje kroz kanonski pisac, Genome kroz stvaran dispečer;
zamenjen je samo model) — tok sam upisuje trajnu V2 protivrečnost između datuma uručenja iz tužbe (17.03.2025) i iz
dostavnice (25.03.2025). Meri se TAČAN tekst koji ide modelu (`pokreni` je zamenjen i beleži upit).

Pravila:
  * poreklo svake tvrdnje dolazi iz kanonskog `shared.genome_contract.poreklo_tvrdnje` (advokat / navod pronađen u
    tekstu dokumenta / AI izdvojio a nije pronađeno / nepoznato) — nikad „utvrđeno“;
  * snaga se navodi samo kad ju je procenio advokat (`izvor_snage = covek`); podrazumevana vrednost kolone nije procena;
  * protivrečnost se označava kao SPORNO samo iz trajnih V2 protivrečnosti (aktivna ili za pregled), ograničenih na
    predmet I korisnika; razrešena nije sporna; bez klasifikatora i bez nove ocene sigurnosti;
  * kad se protivrečnosti ne mogu pročitati, to se kaže — tvrdnje se ne predstavljaju kao međusobno saglasne.
"""
import re
from unittest.mock import patch

import pytest

from tests.test_osb002_solo_tok import A, solo  # noqa: F401
from tests.test_vcr002_t03_visedokumentni_predmet import predmet  # noqa: F401

PITANJE = "Koji datum uručenja je merodavan za rok za tužbu?"


def _upit(k, pid):
    import api
    upiti = []

    async def _pokreni(fn, pitanje_za_agenta, *a, **kw):
        upiti.append(pitanje_za_agenta)
        return {"status": "success", "data": "Odgovor.", "confidence": "HIGH", "top_score": 0.8,
                "confidence_detail": {}, "izvori": []}
    with patch.object(api, "pokreni", _pokreni):
        r = k.post("/api/pitanje", json={"pitanje": PITANJE, "predmet_id": pid}, headers=A)
    assert r.status_code == 200 and r.json()["kontekst_predmeta"] is True, r.text
    return upiti[0]


def _red(upit, deo):
    redovi = [r for r in upit.splitlines() if deo in r]
    assert len(redovi) == 1, (deo, redovi)
    return redovi[0]


def _kontradikcija(b):
    [k] = b.tabele["predmet_contradictions"]
    return k


def test_ai_tvrdnja_nikad_nije_utvrdjena_cinjenica(predmet):
    k, b, pid, doks = predmet
    upit = _upit(k, pid)
    assert "Utvrđen" not in upit and "utvrđene činjenice" not in upit.lower()
    assert re.search(r"nijedna nije (sudski )?utvrđena", upit), "zaglavlje mora reći da tvrdnje nisu utvrđene"
    for deo in ("17.03.2025", "25.03.2025", "Rok za izjasnjenje"):
        red = _red(upit, deo)
        assert "navod iz dokumenta" in red and "AI izdvojio" in red, red          # poreklo, ne kategorija istine
        assert "snaga=" not in red and "jaka" not in red, red                     # DC-005 „jaka“ nije procena advokata


def test_ai_tvrdnja_koja_nije_nadjena_u_dokumentu_je_neproverena(predmet):
    k, b, pid, doks = predmet
    t = next(t for t in b.tabele["predmet_dokazi"] if "Rok za izjasnjenje" in t["tvrdnja"])
    t["nacin_pronalaska"] = "nije_pronadjen"
    red = _red(_upit(k, pid), "Rok za izjasnjenje")
    assert "nije pronađen" in red and "neproveren" in red, red


def test_advokatova_tvrdnja_i_njegova_procena_snage_ostaju_njegove(predmet):
    k, b, pid, doks = predmet
    r = k.post(f"/api/evidence/predmeti/{pid}/dokaz", headers=A,
               json={"tvrdnja": "Advokat: poslodavac nije sproveo postupak upozorenja.", "kategorija": "cinjenica", "snaga": "jaka"})
    assert r.status_code == 200, r.text
    red = _red(_upit(k, pid), "Advokat: poslodavac")
    assert "uneo advokat" in red and "procena advokata: jaka" in red and "AI" not in red, red


def test_aktivna_protivrecnost_oznacava_obe_tvrdnje_kao_sporne(predmet):
    k, b, pid, doks = predmet
    assert _kontradikcija(b)["state"] == "OPEN"
    upit = _upit(k, pid)
    for deo in ("17.03.2025", "25.03.2025"):
        assert "SPORNO" in _red(upit, deo), deo
    assert "SPORNO" not in _red(upit, "Rok za izjasnjenje")
    labela = b.tabele["predmet_issues"][0]["label"]
    assert "Sporne tačke" in upit and labela in upit


def test_protivrecnost_za_pregled_je_sporna_a_razresena_nije(predmet):
    k, b, pid, doks = predmet
    _kontradikcija(b)["state"] = "REVIEW_REQUIRED"
    assert "SPORNO" in _red(_upit(k, pid), "17.03.2025")
    _kontradikcija(b)["state"] = "RESOLVED"
    upit = _upit(k, pid)
    assert "SPORNO" not in upit and "Sporne tačke" not in upit


def test_tudja_sporna_tacka_ne_menja_kontekst(predmet):
    k, b, pid, doks = predmet
    for i in b.tabele["predmet_issues"]:
        i["user_id"] = "uid-B"
    assert "SPORNO" not in _upit(k, pid)


def test_pad_citanja_protivrecnosti_se_kaze_a_tvrdnje_ostaju_neproverene(predmet):
    k, b, pid, doks = predmet
    b.greske["predmet_contradictions"] = Exception("PostgREST 503")
    upit = _upit(k, pid)
    assert "protivrečnosti nije dostupna" in upit
    assert "SPORNO" not in upit and "navod iz dokumenta" in _red(upit, "17.03.2025")


def test_kontekst_ostaje_u_granici_poverenja(predmet):
    k, b, pid, doks = predmet
    upit = _upit(k, pid)
    pocetak, kraj = upit.index("VINDEX_NEPOVERLJIVO"), upit.rindex("VINDEX_NEPOVERLJIVO")
    for deo in ("17.03.2025", "Sporne tačke"):
        assert pocetak < upit.index(deo) < kraj, deo

# -*- coding: utf-8 -*-
"""Operation Bojan BA-01 — procesni događaji u hronološkom toku predmeta (Task 7, BA-04).

`GET /api/predmeti/{id}` nosi `procesni_dogadjaji` = ista projekcija kao Analiza (`genome_contract._hronologija`),
bez nove persistencije. Poreklo ostaje AI_ANALYSIS; izvor se razrešava samo unutar predmeta; `datum_u_izvoru` je
deterministička provera da li tekst izvornog dokumenta navodi taj datum. Ništa se ne upisuje u `predmet_hronologija`.
"""
import copy
import json

import routers.case_dna as cd
import tests.test_osb002_solo_tok as osb
from shared.genome_contract import AI_ANALYSIS, NEPOZNATO, OK, procesni_dogadjaji
from tests.test_ba01_rok_identitet import _osvezi, _predmet, _prikaci
from tests.test_n7_azuriranje_predmeta import lanac  # noqa: F401 — fixture
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401 — fixture

DOK = [{"id": "d1", "redni_broj": 1, "naziv_fajla": "01 Presuda.pdf",
        "tekst_sadrzaj": "PRESUDA\nPresuda je doneta 20.10.2026. godine.\nU Beogradu, dana 21.10.2026."},
       {"id": "d2", "redni_broj": 2, "naziv_fajla": "02 Dostava.pdf",
        "tekst_sadrzaj": "POTVRDA O DOSTAVI\nPresuda je urucena tuzenom 23.10.2026. godine."}]


def _g(*datumi):
    return {"datumi_kljucni": [dict(opis=o, datum=d, znacaj="bitno", lokacija=l) for o, d, l in datumi]}


def test_dogadjaji_sa_izvorom_i_proverom_datuma():
    s = procesni_dogadjaji(_g(("Presuda doneta", "2026-10-20", "DOK-01"), ("Presuda uručena tuženom", "2026-10-23", "DOK-02")), DOK)
    assert s["stanje"] == OK
    assert [(x["datum"], x["vrednost"], x["lokacija"]["dokument_id"], x["datum_u_izvoru"], x["poreklo"]) for x in s["stavke"]] == [
        ("2026-10-20", "Presuda doneta", "d1", True, AI_ANALYSIS), ("2026-10-23", "Presuda uručena tuženom", "d2", True, AI_ANALYSIS)]


def test_model_dodaje_dogadjaj_koji_izvor_ne_navodi():
    [x] = procesni_dogadjaji(_g(("Ročište održano", "2026-10-25", "DOK-01")), DOK)["stavke"]
    assert x["lokacija"]["dokument_id"] == "d1" and x["datum_u_izvoru"] is False


def test_nerazresen_izvor_i_neodredjen_datum_se_ne_izmisljaju():
    s = procesni_dogadjaji(_g(("Dostava", "2026-10-24", "DOK-09"), ("Uručenje", "17. mart", "DOK-02"), ("Prijem", None, "")), DOK)
    po = {x["vrednost"]: x for x in s["stavke"]}
    assert po["Dostava"]["lokacija"]["dokument_id"] is None and po["Dostava"]["datum_u_izvoru"] is None
    assert po["Uručenje"]["datum"] is None and po["Uručenje"]["datum_neispravan"] is True and po["Uručenje"]["datum_u_izvoru"] is None
    assert po["Prijem"]["datum"] is None and po["Prijem"]["datum_u_izvoru"] is None


def test_dva_dokumenta_isti_dogadjaj_ili_razliciti_datumi_ostaju_odvojeni():
    s = procesni_dogadjaji(_g(("Presuda uručena", "2026-10-23", "DOK-02"), ("Presuda uručena", "2026-10-24", "DOK-01")), DOK)
    assert [(x["datum"], x["lokacija"]["dokument_id"], x["datum_u_izvoru"]) for x in s["stavke"]] == [
        ("2026-10-23", "d2", True), ("2026-10-24", "d1", False)]


def test_tudj_dokument_se_ne_razresava():
    """Projekcija dobija SAMO dokumente ovog predmeta; DOK-NN koji ne postoji među njima je nerazrešen."""
    [x] = procesni_dogadjaji(_g(("Dostava", "2026-10-23", "DOK-02")), DOK[:1])["stavke"]
    assert x["lokacija"]["dokument_id"] is None


def test_bez_analize_stanje_nepoznato():
    assert procesni_dogadjaji({}, DOK)["stanje"] == NEPOZNATO
    assert procesni_dogadjaji({"greska": "model nije odgovorio"}, DOK)["stanje"] == NEPOZNATO
    assert procesni_dogadjaji(None, None)["stanje"] == NEPOZNATO


class _Model:
    def __init__(self, datumi):
        self.datumi = datumi

    async def __call__(self, client, combined, n):
        g = copy.deepcopy(osb.rp._genome(0, False, 0, 0))
        for polje in ("verzija", "_analiza_osnov", "_genome_docs_count", "_genome_docs_preskoceno", "_dokumenti_bez_teksta", "_verifikacija"):
            g.pop(polje, None)
        g["rokovi_kriticni"] = []
        g["datumi_kljucni"] = copy.deepcopy(self.datumi)
        return json.dumps(g, ensure_ascii=False)


def test_detalj_predmeta_nosi_dogadjaje_bez_upisa_u_hronologiju_i_osvezava_se(lanac, monkeypatch):
    k, b = lanac
    model = _Model([{"opis": "Presuda doneta", "datum": "2026-10-20", "znacaj": "kriticno", "lokacija": "DOK-01"}])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    _prikaci(k, b, pid, ["PRESUDA", "Presuda je doneta 20.10.2026. godine."], "01 Presuda.pdf")
    hron_pre = len(b.tabele["predmet_hronologija"])
    d = k.get(f"/api/predmeti/{pid}", headers=A).json()
    dok1 = next(x["id"] for x in d["dokumenti"] if x["naziv_fajla"] == "01 Presuda.pdf")
    assert [(x["datum"], x["vrednost"], x["lokacija"]["dokument_id"], x["datum_u_izvoru"]) for x in d["procesni_dogadjaji"]["stavke"]] == [
        ("2026-10-20", "Presuda doneta", dok1, True)]
    # nov dokument → nova analiza → detalj pokazuje NOVO stanje (bez zastarele kopije)
    model.datumi = model.datumi + [{"opis": "Presuda uručena tuženom", "datum": "2026-10-23", "znacaj": "bitno", "lokacija": "DOK-02"}]
    _prikaci(k, b, pid, ["POTVRDA O DOSTAVI", "Presuda je urucena tuzenom 23.10.2026. godine."], "02 Dostava.pdf")
    d = k.get(f"/api/predmeti/{pid}", headers=A).json()
    assert [x["datum"] for x in d["procesni_dogadjaji"]["stavke"]] == ["2026-10-20", "2026-10-23"]
    assert len(b.tabele["predmet_hronologija"]) == hron_pre + 1                # samo „Dokument prihvaćen" za nov dokument
    assert not [h for h in b.tabele["predmet_hronologija"] if h["predmet_id"] == pid and "Presuda doneta" in (h.get("dogadjaj") or "")]
    assert k.get(f"/api/predmeti/{pid}", headers=B).status_code == 404


def test_pad_projekcije_je_nije_ucitano_a_ne_prazno(lanac, monkeypatch):
    k, b = lanac
    pid = _predmet(k)
    import shared.genome_contract as gc

    def _pada(*a, **kw):
        raise RuntimeError("pokvaren case_dna")
    monkeypatch.setattr(gc, "procesni_dogadjaji", _pada)
    d = k.get(f"/api/predmeti/{pid}", headers=A)
    assert d.status_code == 200 and d.json()["procesni_dogadjaji"] is None and isinstance(d.json()["hronologija"], list)

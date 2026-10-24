# -*- coding: utf-8 -*-
"""MIR001 FINAL CLOSURE — TASK-C0: reprodukcije (bez izmene repo-a). Pokretanje iz C:/vindex-miroslav:
python -m pytest <ovaj fajl> -p tests.conftest --rootdir=C:/vindex-miroslav -q -s -p no:randomly"""
import io
import pytest
import json
from unittest.mock import MagicMock, patch

from tests import mir001_golden_case as gc
from tests.test_mir001_t07_dogadjaj_posledica import _dodaj, spis  # noqa: F401
from tests.test_osb002_solo_tok import A, _do_kraja_dogadjaja, _novi_predmet, _otpremi, _radnik, solo  # noqa: F401
from tests.test_vcr002_t03_visedokumentni_predmet import _atomsko_rpc, _brisanje_rpc
from routers.evidence import _klasifikuj_dokument as _PRAVI_KLASIFIKATOR   # pre fixture-a (koji ga zamenjuje)


def test_R1_zatvaranje_radnje_posle_brisanja_izvora_bez_razloga(spis):
    k, b, pid, doks = spis
    d8 = _dodaj(k, b, pid, gc.KASNIJI)
    [a] = [x for x in b.tabele["case_actions"] if x["predmet_id"] == pid and x["status"] == "open"
           and (x.get("dokaz") or {}).get("dokument_id") == d8]
    n_audit = len(b.tabele["audit_immutable"])
    from shared.vector_deletion import Ishod, Rezultat
    b.rpc_impl["invalidate_dokument_relational_and_emit_event"] = _brisanje_rpc
    b.rpc_impl["invalidate_dokument_and_ai_claims_and_emit_event"] = _atomsko_rpc
    with patch("shared.vector_deletion.obrisi_vektore_dokumenta", lambda *x, **kw: Rezultat(Ishod.DELETED, obrisano=1, ocekivano=1)), \
            patch("uploaded_doc.ingest._get_pinecone_index", lambda: MagicMock()):
        assert k.delete(f"/api/predmeti/{pid}/dokumenti/{d8}", headers=A).status_code == 200
    _do_kraja_dogadjaja(b, najvise=40)
    sada = next(x for x in b.tabele["case_actions"] if x["id"] == a["id"])
    audit = [r for r in b.tabele["audit_immutable"][n_audit:] if r.get("action") == "case_action_refreshed"]
    zatv = [c for r in audit for c in (r.get("metadata") or {}).get("closed_actions", []) if c.get("id") == a["id"]]
    print("R1_STATUS", sada["status"], "| polja radnje:", sorted(k2 for k2 in sada if "razlog" in k2 or "close" in k2))
    print("R1_AUDIT", json.dumps(zatv, ensure_ascii=True), "| metapodaci reda:", sorted((audit[-1].get("metadata") or {}).keys()) if audit else None)
    assert sada["status"] == "closed" and zatv and not any("razlog" in c or "reason" in c for c in zatv)


def _dug_pdf(redovi):
    from reportlab.pdfgen import canvas
    bb = io.BytesIO()
    c = canvas.Canvas(bb, invariant=1)
    y = 800
    for r in redovi:
        if y < 60:
            c.showPage(); y = 800
        c.drawString(40, y, r); y -= 16
    c.showPage(); c.save()
    return bb.getvalue()


@pytest.mark.parametrize("n_uvod", [30, 60])
def test_R2_cinjenica_iza_1500_znakova_ne_stize_do_ekstrakcije(solo, monkeypatch, n_uvod):
    k, b = solo
    import routers.evidence as ev
    poruke = []

    def _model(client, user_msg):
        poruke.append(user_msg)
        r = MagicMock(); r.choices = [MagicMock()]
        r.choices[0].message.content = json.dumps({"tip_dokaza": "podnesak", "pravni_elementi": [], "kljucne_cinjenice": []})
        return r
    import importlib
    ev_mod = importlib.import_module("routers.evidence")
    monkeypatch.setattr(ev_mod, "_klasifikuj_dokument", _PRAVI_KLASIFIKATOR)
    monkeypatch.setattr(ev_mod, "_pozovi_evidence_api", _model)
    uvod = [f"Recenica uvoda broj {i}: tuzilac opisuje okolnosti ugovora i tok saradnje sa tuzenim." for i in range(n_uvod)]
    kasna = "PRESUDNA CINJENICA: tuzeni je pismeno priznao dug od 2.345.678 dinara dana 03.03.2026. godine."
    redovi = ["PRIVREDNI SUD (SINTETICKI)", "PODNESAK (SINTETICKI)"] + uvod + [kasna] + ["Kraj podneska."]
    _, pid = _novi_predmet(k, b)
    r = _otpremi(k, _dug_pdf(redovi), ime="Dug podnesak.pdf")
    jid = r.json()["rezultati"][0]["job_id"]
    while _radnik():
        pass
    if next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)["status"] == "awaiting_review":
        k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=A)
    assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A).status_code == 200
    _do_kraja_dogadjaja(b, najvise=20)
    [dok] = [d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid]
    tekst = " ".join((dok.get("tekst_sadrzaj") or "").split())
    pozicija = tekst.find("PRESUDNA CINJENICA")
    print("\nR2_DOKUMENT", len(tekst), "znakova; cinjenica na poziciji", pozicija)
    print("R2_KLASIFIKATOR", len(poruke), "poziva; cinjenica u poruci:", any("PRESUDNA" in p for p in poruke),
          "| duzina teksta u poruci:", [len(p.split("max 1500 znakova):\n", 1)[-1]) for p in poruke])
    g = b.genome_pozivi[-1] if b.genome_pozivi else ""
    print("\nR2_GENOME", len(b.genome_pozivi), "poziva; cinjenica u poslednjem Genome promptu:", "PRESUDNA" in g, "| u bilo kom:", any("PRESUDNA" in x for x in b.genome_pozivi), "| tekst dok. u promptu:", g.count("Recenica uvoda"))
    assert pozicija > 1500 and poruke and not any("PRESUDNA" in p for p in poruke)
    # Genome: čita do 4.500 znakova po dokumentu — vidi činjenicu ispod te granice, ne vidi iznad
    assert b.genome_pozivi, "Genome nije pozvan"
    assert ("PRESUDNA" in g) == (pozicija < 4500), (pozicija, "PRESUDNA" in g)

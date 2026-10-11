"""NS006 Task 17 — cena čitanja živog predmeta.

  • otvaranje predmeta, Analize (sve sekcije su u JEDNOM odgovoru), promena i Danas/Workspace: 0 poziva modela
    (OpenAI/AsyncOpenAI konstruktori zamenjeni klasom koja puca);
  • broj upita bazi je KONSTANTAN u odnosu na broj tvrdnji, dokumenata, kontradikcija i akcija (nema N+1):
    meri se iz dnevnika lažne baze za mali i za 40× veći predmet;
  • Workspace: broj upita ne raste sa brojem predmeta.
"""
import pytest

from tests import ns006_realni_predmet as rp
from tests.ns006_fake import pripremi, ocisti, zaglavlje

RUTE = [f"/api/predmeti/{rp.PA}/genome-v2", f"/api/predmeti/{rp.PA}/genome-v2/promene", f"/api/case-actions/predmeti/{rp.PA}",
        "/api/workspace", f"/api/predmeti/{rp.PA}"]


def _uvecaj(t, n):
    """n× više tvrdnji, dokumenata, kontradikcija i akcija u ISTOM predmetu."""
    for i in range(n):
        did = f"dd{i:06d}-0000-4000-8000-000000000000"
        t["predmet_dokumenti"].append({"id": did, "predmet_id": rp.PA, "user_id": "uid-A", "naziv_fajla": f"Prilog {i}.pdf",
                                       "redni_broj": 10 + i, "tip_dokaza": "dopis", "klasifikovan_at": "2026-10-01T09:00:00+00:00"})
        for j in range(3):
            t["predmet_dokazi"].append({"id": f"cc{i:04d}{j:02d}-0000-4000-8000-000000000000", "predmet_id": rp.PA, "user_id": "uid-A",
                                        "dokument_id": did, "tvrdnja": f"Tvrdnja {i}-{j}", "izvor_tvrdnje": "ai_klasifikacija", "deleted_at": None})
        iid = f"ii{i:06d}-0000-4000-8000-000000000000"
        t["predmet_issues"].append({"id": iid, "predmet_id": rp.PA, "user_id": "uid-A", "label": f"tačka {i}", "status": "DISCOVERED"})
        kid = f"kk{i:06d}-0000-4000-8000-000000000000"
        t["predmet_contradictions"].append({"id": kid, "issue_id": iid, "relation_type": "cinjenica_cinjenica", "state": "OPEN"})
        for j in range(2):
            t["predmet_contradiction_claims"].append({"contradiction_id": kid, "dokaz_id": f"cc{i:04d}{j:02d}-0000-4000-8000-000000000000", "removed_at": None})
        t["case_actions"].append({"id": f"aa{i:06d}", "predmet_id": rp.PA, "tip": "PRIBAVITI_DOKAZ", "razlog": f"r{i}",
                                  "prioritet": "high", "status": "open", "dedupe_key": f"k{i}"})
    for i in range(n):   # i više predmeta istog korisnika (za Workspace)
        t["predmeti"].append({"id": f"pp{i:06d}-0000-4000-8000-000000000000", "user_id": "uid-A", "naziv": f"Predmet {i}",
                              "tip": "radno", "status": "aktivan", "case_dna": {}})
    return t


def _izmeri(monkeypatch, n):
    t = rp.tabele()
    t["predmet_beleske"], t["predmet_klijenti"], t["predmet_hronologija"] = [], [], []
    k, baza = pripremi(monkeypatch, _uvecaj(t, n))
    pozivi_modela = []

    class _Zabranjeno:
        def __init__(self, *a, **kw):
            pozivi_modela.append(1)
            raise AssertionError("model se ne sme zvati pri čitanju")
    import openai
    monkeypatch.setattr(openai, "OpenAI", _Zabranjeno)
    monkeypatch.setattr(openai, "AsyncOpenAI", _Zabranjeno)
    upiti = {}
    try:
        for ruta in RUTE:
            pre = len(baza.dnevnik)
            r = k.get(ruta, headers=zaglavlje("A"))
            assert r.status_code == 200, (ruta, r.status_code, r.text[:200])
            nove = baza.dnevnik[pre:]
            assert not [z for z in nove if z["radnja"] in ("insert", "update", "upsert", "delete")], (ruta, "čitanje piše")
            upiti[ruta] = len(nove)
    finally:
        ocisti()
    return upiti, pozivi_modela


def test_citanje_ne_zove_model_i_nema_n_plus_1(monkeypatch):
    malo, m1 = _izmeri(monkeypatch, 1)
    mnogo, m2 = _izmeri(monkeypatch, 40)
    assert m1 == [] and m2 == [], "nijedan poziv modela pri čitanju"
    for ruta in RUTE[:4]:
        assert malo[ruta] == mnogo[ruta], f"{ruta}: {malo[ruta]} upita za mali, {mnogo[ruta]} za 40× veći predmet (N+1)"
    # Analiza je JEDAN zahtev sa svim sekcijama i ograničenim brojem upita
    assert malo[RUTE[0]] <= 10, malo

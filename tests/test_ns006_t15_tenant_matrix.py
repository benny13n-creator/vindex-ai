"""NS006 Task 15 — matrica zakupaca i sesija (konsolidacija + odbrana u dubinu).

Već dokazano drugde (ne ponavlja se):
  • tuđ / nepostojeći / neispravan id → bajt-identičan 404 za genome-v2, promene, case-actions (T9);
  • Workspace B ne vidi radnje A (T9, T14); klijent B ne vidi ništa od realnog predmeta (T14);
  • tuđi korisnik ne pokreće obradu tuđeg predmeta (T13);
  • UI: prelazak A→B i prelazak na drugi predmet dok odgovor kasni — Analiza, Pregled, Danas (live-analiza,
    live-pregled-zivi, live-radna-lista), sa mutacijama koje uklanjaju obe brave (generacija + abort).

Ovde — ODBRANA U DUBINU: redovi koji nose `predmet_id` predmeta A, ali pripadaju korisniku B (oštećen ili ručno
unet red, pogrešan uvoz). Provera vlasništva predmeta prolazi (A je vlasnik), pa jedino filter `user_id` na SVAKOM
čitanju sprečava da tekst B uđe u odgovor A. Mutacije uklanjaju te filtere jedan po jedan.
"""
import json

import pytest

from tests import ns006_realni_predmet as rp
from tests.ns006_fake import pripremi, ocisti, zaglavlje

TRAG = "UTECENO-OD-B"


def _zagadjene_tabele():
    t = rp.tabele()
    t["predmet_dokazi"].append({"id": "b0b0b0b0-0000-4000-8000-0000000000b0", "predmet_id": rp.PA, "user_id": "uid-B",
                                "dokument_id": None, "tvrdnja": TRAG + " tvrdnja", "izvor_tvrdnje": "covek", "deleted_at": None})
    t["predmet_dokumenti"].append({"id": "b1b1b1b1-0000-4000-8000-0000000000b1", "predmet_id": rp.PA, "user_id": "uid-B",
                                   "naziv_fajla": TRAG + ".pdf", "redni_broj": 99, "tip_dokaza": "dopis"})
    t["rocista"].append({"id": "b2b2b2b2-0000-4000-8000-0000000000b2", "predmet_id": rp.PA, "user_id": "uid-B",
                         "sud": TRAG + " sud", "datum": "2026-10-12", "vreme": "09:00", "status": "zakazano"})
    # tuđa „najnovija" verzija istorije: ako se uzme, promene bi poredile pogrešan par verzija
    t["predmet_genome_history"].append({"id": "hb", "predmet_id": rp.PA, "user_id": "uid-B", "verzija": 99,
                                        "genome_data": {"verzija": 99, "pravna_teorija": {"sustina_spora": TRAG}},
                                        "trigger_event": "case_evolution:" + TRAG, "created_at": "2026-10-09T23:00:00+00:00"})
    # V2 sporna tačka korisnika B zakačena za predmet A (paketni RPC to ne dozvoljava — GUARD u SQL-u; ovde čitalac)
    t["predmet_issues"].append({"id": "ib", "predmet_id": rp.PA, "user_id": "uid-B", "label": TRAG + " sporna tačka", "status": "DISCOVERED"})
    t["predmet_contradictions"].append({"id": "kb", "issue_id": "ib", "relation_type": "cinjenica_cinjenica", "state": "OPEN",
                                        "opis": TRAG, "tezina": "kriticna"})
    t["predmet_contradiction_claims"].append({"contradiction_id": "kb", "dokaz_id": rp.T1, "removed_at": None})
    return t


@pytest.fixture
def k(monkeypatch):
    klijent, _ = pripremi(monkeypatch, _zagadjene_tabele())
    yield klijent
    ocisti()


def test_redovi_b_sa_predmet_id_od_a_ne_ulaze_u_genome_v2(k):
    r = k.get(f"/api/predmeti/{rp.PA}/genome-v2", headers=zaglavlje("A"))
    assert r.status_code == 200
    assert TRAG not in r.text, "red korisnika B ušao u živi predmet A"
    ziv = r.json()
    assert all(t["id"] != "b0b0b0b0-0000-4000-8000-0000000000b0" for t in ziv["dokazi"]["tvrdnje"])
    assert all(x["id"] != "kb" for x in ziv["kontradikcije"]["aktivne"]), "V2 sporna tačka korisnika B prikazana kod A"
    rocista = next(d for d in ziv["spremnost"]["dimenzije"] if d["kljuc"] == "rocista")["vrednost"]
    assert rocista["u_narednih_7_dana"] == 1, rocista   # samo ročište A (rp.ROCISTE), ne i tuđe


def test_tudja_verzija_istorije_ne_menja_promene(k):
    r = k.get(f"/api/predmeti/{rp.PA}/genome-v2/promene", headers=zaglavlje("A"))
    assert r.status_code == 200 and TRAG not in r.text
    x = r.json()
    assert x["prethodna_verzija"] != 99 and x["trenutna_verzija"] != 99, x
    # i bez curenja, tuđa „najnovija" verzija ne sme da prikrije stvarnu razliku lažnim „prethodna nije sačuvana"
    assert x["stanje"] == "OK" and x["prethodna_verzija"] == x["trenutna_verzija"] - 1, x


def test_b_ne_vidi_ni_sopstvene_redove_kroz_predmet_a(k):
    """B je vlasnik zagađenih redova, ali NE i predmeta A → isti 404, bez ijednog bajta."""
    for put in (f"/api/predmeti/{rp.PA}/genome-v2", f"/api/predmeti/{rp.PA}/genome-v2/promene", f"/api/case-actions/predmeti/{rp.PA}"):
        r = k.get(put, headers=zaglavlje("B"))
        assert r.status_code == 404 and TRAG not in r.text and "Petrović" not in r.text


def test_workspace_a_ne_sadrzi_nista_od_b(k):
    r = k.get("/api/workspace", headers=zaglavlje("A"))
    assert r.status_code == 200 and TRAG not in r.text
    assert all(s["predmet_id"] != rp.PB for kp in ("danas", "kriticno", "predstojece") for s in r.json()[kp])

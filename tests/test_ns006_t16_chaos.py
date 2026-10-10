"""NS006 Task 16 — ponašanje kad jedan podsistem padne (dopuna; ostali slučajevi su u T2/T4/T5/T6/T7/T8).

Već dokazano drugde (ne ponavlja se):
  • pad čitanja dokaza / kontradikcija / istorije / izvora rizika → DEGRADED, nikad 0 ni prazno (T3/T4/T5/T6/T7);
  • pad čitanja izvora pri reconcile-u akcija → izuzetak, akcije NEPROMENJENE (T8);
  • ponovni pokušaj dispečera i duplikat akcije u trci → jedna akcija (T2/T8);
  • UI: 500/404 i pad izvora → jasna poruka, bez beskonačnog učitavanja (live-analiza).

Ovde:
  A. model pada usred `genome_refresh` → `case_dna` NETAKNUT (ista verzija, isti sadržaj), posledica `failed`,
     događaj ostaje za ponovni pokušaj; sledeći prolaz uspeva — model je pozvan tačno onoliko puta koliko je bilo
     pokušaja (nema dvostruke analize posle uspeha);
  B. paketni RPC V2 opažanja pada → `case_dna` NIJE upisan (A017 redosled), posledica `failed`, oporavak u retry-ju;
  C. trajno pokvarena posledica → posle 5 pokušaja DEAD_LETTER u `events.last_error` (vidljivo, ne tiho izgubljeno);
  D. API timeout na frontendu → poruka (proverava live-analiza: 500/mrežna greška daju tekst, `ucitavanje` se gasi).
"""
import copy
import json
import re
from datetime import date, timedelta

import pytest

from tests import ns006_realni_predmet as rp
from tests.ns006_fake import pripremi, ocisti, dispecuj, zaglavlje
from tests.test_ns006_t13_autonomous_chain import _pocetne_tabele, _model_iz_prompta

DATUM = (date.today() + timedelta(days=9)).isoformat()


@pytest.fixture
def svet(monkeypatch):
    k, baza = pripremi(monkeypatch, _pocetne_tabele())
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-bez-mreze")
    yield k, baza, monkeypatch
    ocisti()


def _rociste(k):
    r = k.post("/api/rocista", json={"predmet_id": rp.PA, "sud": "Osnovni sud u Beogradu", "datum": DATUM}, headers=zaglavlje("A"))
    assert r.status_code == 200


def _posledice(baza):
    return {c["consequence_name"]: c["status"] for c in baza.tabele["case_evolution_consequences"]}


def test_a_model_pada_genome_netaknut_pa_oporavak_bez_dvostruke_analize(svet):
    k, baza, mp = svet
    import routers.case_dna as cd
    pozivi, pravi = [], _model_iz_prompta([])
    stanje = {"pad": True}

    async def _model(client, combined, n):
        pozivi.append(1)
        if stanje["pad"]:
            raise TimeoutError("model nije odgovorio (test)")
        return await pravi(client, combined, n)
    mp.setattr(cd, "_pozovi_genome_api", _model)
    pre = copy.deepcopy(baza.tabele["predmeti"][0]["case_dna"])
    _rociste(k)
    r1 = dispecuj()[0]
    assert r1["greske"] == 1
    assert baza.tabele["predmeti"][0]["case_dna"] == pre, "neuspela analiza ne sme da dira postojeći Genome"
    assert _posledice(baza)["genome_refresh"] == "failed"
    ev = baza.tabele["events"][0]
    assert ev["dispatched_at"] is None and ev["dispatch_attempts"] == 1
    neuspelih = len(pozivi)
    stanje["pad"] = False
    r2 = dispecuj()[0]
    assert r2["dispecovano"] == 1 and baza.tabele["predmeti"][0]["case_dna"]["verzija"] == 4
    assert len(pozivi) == neuspelih + 1, "posle uspeha nema dodatne analize"
    dispecuj(2)
    assert len(pozivi) == neuspelih + 1


def test_b_pad_v2_paketa_ne_upisuje_case_dna(svet):
    k, baza, mp = svet
    import routers.case_dna as cd
    mp.setattr(cd, "_pozovi_genome_api", _model_iz_prompta([]))
    baza.greske["rpc:v2_persist_observation_package"] = RuntimeError("transakcija vraćena (test)")
    pre = copy.deepcopy(baza.tabele["predmeti"][0]["case_dna"])
    istorija_pre = len(baza.tabele["predmet_genome_history"])
    _rociste(k)
    assert dispecuj()[0]["greske"] == 1
    assert baza.tabele["predmeti"][0]["case_dna"] == pre and len(baza.tabele["predmet_genome_history"]) == istorija_pre
    assert baza.tabele["predmet_contradictions"] == []
    del baza.greske["rpc:v2_persist_observation_package"]
    assert dispecuj()[0]["dispecovano"] == 1
    assert baza.tabele["predmeti"][0]["case_dna"]["verzija"] == 4 and len(baza.tabele["predmet_contradictions"]) == 1


def test_c_trajno_pokvarena_posledica_ide_u_dead_letter(svet):
    k, baza, mp = svet
    import routers.case_dna as cd

    async def _uvek_pada(client, combined, n):
        raise TimeoutError("model trajno nedostupan (test)")
    mp.setattr(cd, "_pozovi_genome_api", _uvek_pada)
    _rociste(k)
    for _ in range(5):
        dispecuj()
    ev = baza.tabele["events"][0]
    assert ev["dispatched_at"] is not None and str(ev["last_error"]).startswith("DEAD_LETTER"), ev.get("last_error")
    assert ev["dispatch_attempts"] == 5

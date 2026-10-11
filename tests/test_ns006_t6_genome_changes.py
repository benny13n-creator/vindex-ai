"""NS006 Task 6 — verzije Genome-a i deterministička razlika („Šta se promenilo").

Dokazuje:
  • POSTOJEĆI KVAR zatvoren za nove snimke: `_compute_delta` je kontradikcije poredio po
    efemernim `CLAIM-NNN` oznakama — dodata tvrdnja pomera numeraciju i ista sporna tačka
    izgleda kao „1 nova + 1 eliminisana". Sa `claim_ids` (trajni UUID) → 0/0;
  • proizvođač (`_extract_genome`) razrešava `claim_ids` ISTIM katalogom, fail-closed;
  • v17 → v18 iz jednog novog dokumenta: tačno stvarne strukturne promene, procene modela odvojeno;
  • ista analiza regenerisana (drugi redosled, preformulisan tekst, pomerene oznake) → nijedna promena;
  • isti ulaz → isti izlaz (restart); snimak bez trajnih veza → kontradikcije „nepoznato", ne lažne;
  • ruta: A vidi, B dobija 404 identičan nepostojećem; prva verzija; nedostajuća N−1; pad istorije;
    čitanje ne piše; akcije koje je osvežio isti događaj su vezane preko `event_id`.
"""
import asyncio
import copy
import json

import pytest

from shared.genome_contract import promene_genome
from tests.ns006_fake import pripremi, ocisti, zaglavlje

PA = "11111111-1111-4111-8111-11111111111a"
D1, D2, D3 = "d1000000-0000-4000-8000-000000000001", "d2000000-0000-4000-8000-000000000002", "d3000000-0000-4000-8000-000000000003"
A, B, C, D = ("aa000000-0000-4000-8000-00000000000a", "bb000000-0000-4000-8000-00000000000b",
              "cc000000-0000-4000-8000-00000000000c", "dd000000-0000-4000-8000-00000000000d")
DOGADJAJ = "e1000000-0000-4000-8000-0000000000e1"


def _k(label, refs, ids, rel="cinjenica_cinjenica", opis="opis"):
    return {"issue_label": label, "claim_refs": refs, "claim_ids": ids, "relation_type": rel, "opis": opis}


V17 = {"verzija": 17, "_genome_docs_count": 2, "_analiza_osnov": {"dokumenata": 2, "cinjenica": 4},
       "kontradikcije": [_k("datum uručenja", ["CLAIM-001", "CLAIM-002"], [A, B])],
       "rokovi_kriticni": [{"naziv": "Žalbeni rok", "datum": "2025-04-01", "dokument_id": D1}],
       "_verifikacija": {"odluka": "approve"}, "nedostaje": [{"dokument": "x"}, {"dokument": "y"}],
       "snaga_predmeta_procent": 60, "najslabija_tacka": {"rizik": "Nema dostavnice", "kriticnost": 70}}
V18 = {"verzija": 18, "_genome_docs_count": 3, "_analiza_osnov": {"dokumenata": 3, "cinjenica": 6},
       # nova tvrdnja C sortira ispred A i B → oznake su se pomerile; ista tačka (A,B) + nova (C,D)
       "kontradikcije": [_k("Datum uručenja rešenja", ["CLAIM-002", "CLAIM-003"], [A, B], opis="preformulisano"),
                         _k("iznos duga", ["CLAIM-001", "CLAIM-004"], [C, D])],
       "rokovi_kriticni": [{"naziv": "Rok za žalbu", "datum": "2025-04-01", "dokument_id": D1},
                           {"naziv": "Rok za izjašnjenje", "datum": "2025-05-10", "dokument_id": D3}],
       "_verifikacija": {"odluka": "approve"}, "nedostaje": [{"dokument": "x"}],
       "snaga_predmeta_procent": 64, "najslabija_tacka": {"rizik": "Dostavnica nedostaje", "kriticnost": 71}}


# ── postojeći kvar u _compute_delta ──────────────────────────────────────────

def test_compute_delta_bez_lazne_promene_pri_pomeranju_oznaka():
    from routers.case_dna import _compute_delta
    stari = {"snaga_predmeta_procent": 60, "kontradikcije": [_k("t", ["CLAIM-001", "CLAIM-002"], [A, B])]}
    novi = {"snaga_predmeta_procent": 60, "kontradikcije": [_k("t", ["CLAIM-002", "CLAIM-003"], [A, B])]}
    d = _compute_delta(stari, novi)
    assert (d["kontr_nove"], d["kontr_eliminisane"]) == (0, 0), "ista sporna tačka, pomerene oznake ≠ promena"
    # stvarna nova tačka i dalje se vidi
    novi2 = {"snaga_predmeta_procent": 60, "kontradikcije": novi["kontradikcije"] + [_k("u", ["CLAIM-001", "CLAIM-004"], [C, D])]}
    assert _compute_delta(stari, novi2)["kontr_nove"] == 1


def test_proizvodjac_razresava_claim_ids_istim_katalogom(monkeypatch):
    import routers.case_dna as cd
    from shared.claim_catalog import napravi_katalog
    dokazi = [{"id": x, "predmet_id": PA, "tvrdnja": f"tvrdnja {x[:2]}", "deleted_at": None} for x in (A, B, C)]
    kat = napravi_katalog(dokazi, PA)
    o = {v: k for k, v in kat.items()}
    odgovor = {"kontradikcije": [
        {"issue_label": "ok", "claim_refs": [o[B], o[A]], "relation_type": "cinjenica_cinjenica", "lokacija_1": "DOK-01"},
        {"issue_label": "nepoznata", "claim_refs": [o[A], "CLAIM-999"], "relation_type": "cinjenica_cinjenica"},
        {"issue_label": "duplikat", "claim_refs": [o[A], o[A]], "relation_type": "cinjenica_cinjenica"},
        {"issue_label": "delimicna", "claim_refs": [o[A], o[B], "CLAIM-999"], "relation_type": "cinjenica_cinjenica"}],
        "snaga_faktori": [{"faktor": "x", "uticaj": "+5"}]}

    async def _model(client, combined, n):
        return json.dumps(odgovor)
    monkeypatch.setattr(cd, "_pozovi_genome_api", _model)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    g = asyncio.run(cd._extract_genome([{"id": D1, "naziv_fajla": "a.pdf", "redni_broj": 1, "tekst_sadrzaj": "tekst"}],
                                       dokazi=dokazi, predmet_id=PA))
    k = {x["issue_label"]: x for x in g["kontradikcije"]}
    assert k["ok"]["claim_ids"] == sorted([A, B]) and k["ok"]["claim_refs"] == [o[B], o[A]], "claim_refs netaknute"
    assert k["nepoznata"]["claim_ids"] is None and k["duplikat"]["claim_ids"] is None
    assert k["delimicna"]["claim_ids"] is None, "jedna nepoznata referenca obara CELU listu (bez delimičnog skupa)"


# ── razlika ──────────────────────────────────────────────────────────────────

def test_v17_v18_jedan_nov_dokument_samo_stvarne_promene():
    r = promene_genome(V17, V18)
    vrste = [(p["vrsta"], p["staro"], p["novo"]) for p in r["promene"]]
    assert vrste == [
        ("dokumenti_analize", 2, 3),
        ("kontradikcija_dodata", None, None),
        ("rok_dodat", None, "2025-05-10"),
        ("tvrdnje_analize", 4, 6),
    ], vrste
    nova = next(p for p in r["promene"] if p["vrsta"] == "kontradikcija_dodata")
    assert nova["tvrdnje"] == sorted([C, D]) and nova["oznaka"] == "+"
    assert {p["vrsta"] for p in r["analiticke"]} == {"analiticka_ocena", "nedostajuce_po_analizi"}
    assert all("nije verovatnoća ishoda" in p["opis"] for p in r["analiticke"] if p["vrsta"] == "analiticka_ocena")
    assert r["nepoznato"] == []


def test_ista_analiza_regenerisana_nema_promena():
    v18b = copy.deepcopy(V18)
    v18b["kontradikcije"] = list(reversed([dict(k, opis="sasvim drugačije rečeno", claim_refs=list(reversed(k["claim_refs"])))
                                           for k in v18b["kontradikcije"]]))
    v18b["rokovi_kriticni"] = list(reversed([dict(x, naziv=x["naziv"].upper()) for x in v18b["rokovi_kriticni"]]))
    v18b["najslabija_tacka"] = {"rizik": "Potpuno drugi tekst iste slabosti", "kriticnost": 71}
    v18b["verzija"] = 19
    r = promene_genome(V18, v18b)
    assert r["promene"] == [] and r["analiticke"] == [] and r["nepoznato"] == []


def test_isti_ulaz_isti_izlaz():
    a = json.dumps(promene_genome(copy.deepcopy(V17), copy.deepcopy(V18)), sort_keys=True)
    b = json.dumps(promene_genome(copy.deepcopy(V17), copy.deepcopy(V18)), sort_keys=True)
    assert a == b


def test_snimak_bez_trajnih_veza_je_nepoznato():
    stari = copy.deepcopy(V17)
    for k in stari["kontradikcije"]:
        k.pop("claim_ids")
    r = promene_genome(stari, V18)
    assert not any(p["vrsta"].startswith("kontradikcija") for p in r["promene"])
    assert [n["oblast"] for n in r["nepoznato"]] == ["kontradikcije"]


def test_rok_promenjen_po_dokumentu():
    v = copy.deepcopy(V17)
    v["rokovi_kriticni"][0]["datum"] = "2025-04-08"
    r = promene_genome(V17, v)
    assert [(p["vrsta"], p["staro"], p["novo"], p["oznaka"]) for p in r["promene"]] == [("rok_promenjen", "2025-04-01", "2025-04-08", "!")]


def test_prva_verzija_bez_promena():
    assert promene_genome(None, V17) == {"stanje": "PRVA_VERZIJA", "promene": [], "analiticke": [], "nepoznato": []}


# ── ruta ─────────────────────────────────────────────────────────────────────

def _tabele(istorija, case_dna=V18, akcije=()):
    return {"predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Petrović", "tip": "radno", "status": "aktivan", "case_dna": case_dna}],
            "predmet_genome_history": istorija, "case_actions": list(akcije)}


def _h(genome, trigger, kada):
    return {"id": f"h{genome['verzija']}", "predmet_id": PA, "user_id": "uid-A", "verzija": genome["verzija"],
            "genome_data": genome, "trigger_event": trigger, "created_at": kada}


@pytest.fixture
def ruta(monkeypatch):
    stanje = {}

    def _otvori(tabele, kor="A", pid=PA):
        if "k" not in stanje:
            stanje["k"], stanje["baza"] = pripremi(monkeypatch, tabele)
        return stanje["k"].get(f"/api/predmeti/{pid}/genome-v2/promene", headers=zaglavlje(kor)), stanje["baza"]
    yield _otvori
    ocisti()


def test_ruta_promene_dogadjaj_i_akcije(ruta):
    v16 = dict(copy.deepcopy(V17), verzija=16)
    akcija = {"id": "akc-1", "predmet_id": PA, "tip": "RAZRESITI_KONTRADIKCIJU", "razlog": "iznos duga", "prioritet": "high",
              "status": "open", "event_id": DOGADJAJ, "dedupe_key": "v2:contradiction:k2"}
    r, baza = ruta(_tabele([_h(v16, "manual_refresh", "2026-10-01T09:00:00+00:00"),
                            _h(V17, "case_evolution:" + DOGADJAJ, "2026-10-09T10:00:00+00:00")], akcije=[akcija]))
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    t = r.json()
    assert (t["trenutna_verzija"], t["prethodna_verzija"], t["stanje"]) == (18, 17, "OK")
    assert t["nastala"] == "2026-10-09T10:00:00+00:00" and t["dogadjaj_id"] == DOGADJAJ
    assert [a["id"] for a in t["akcije_dogadjaja"]] == ["akc-1"]
    assert [v["verzija"] for v in t["verzije"]] == [17, 16]
    assert {p["vrsta"] for p in t["promene"]} == {"dokumenti_analize", "kontradikcija_dodata", "rok_dodat", "tvrdnje_analize"}
    assert [z for z in baza.dnevnik if z["radnja"] in ("insert", "update", "upsert", "delete", "rpc")] == []


def test_ruta_b_ne_vidi_istoriju_a(ruta):
    tudji, _ = ruta(_tabele([_h(V17, "manual_refresh", "2026-10-09T10:00:00+00:00")]), kor="B")
    nepostojeci, _ = ruta(None, kor="B", pid="99999999-9999-4999-8999-999999999999")
    assert tudji.status_code == nepostojeci.status_code == 404 and tudji.content == nepostojeci.content
    assert "datum uručenja" not in tudji.text


def test_ruta_nedostajuca_prethodna_verzija(ruta):
    v15 = dict(copy.deepcopy(V17), verzija=15)
    t = ruta(_tabele([_h(v15, "manual_refresh", "2026-10-01T09:00:00+00:00")]))[0].json()
    assert t["stanje"] == "UNKNOWN" and t["promene"] == [] and "v17" in t["nepoznato"][0]["razlog"]


def test_ruta_prva_verzija(ruta):
    t = ruta(_tabele([], case_dna=dict(copy.deepcopy(V17), verzija=1)))[0].json()
    assert t["stanje"] == "PRVA_VERZIJA" and t["promene"] == [] and t["prethodna_verzija"] is None


def test_ruta_pad_istorije_nije_bez_promena(ruta, monkeypatch):
    r, baza = ruta(_tabele([_h(V17, "manual_refresh", "2026-10-09T10:00:00+00:00")]))
    baza.greske["predmet_genome_history"] = RuntimeError("istorija nedostupna (test)")
    t = ruta(None)[0].json()
    assert t["stanje"] == "DEGRADED" and t["promene"] == []

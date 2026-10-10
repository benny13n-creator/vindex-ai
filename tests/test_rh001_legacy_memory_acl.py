# -*- coding: utf-8 -*-
"""RH001 Faza C — legacy `/api/firma-memorija/*` i `/api/memory-graph/*` kroz STVARNE rute.

NS008 Law Brain primenjuje kanonsku granicu na iste tabele (`memory_entries`, `memory_graph_edges`): beleška ili
veza vezana za PREDMET vidljiva je samo onome ko taj predmet sme da vidi (`shared/rag_acl.dozvoljeni_predmeti`:
vlasnik + aktivna delegacija), vezana za KLIJENTA samo vlasniku klijenta; opšti entiteti (sudija, firma, partner,
argument, strategija) su izričit put deljenja u kancelariji. Prolazna Law Brain ACL matrica NE dokazuje ništa o
legacy rutama nad istim tabelama — ovaj test dokazuje.

Svet: A i B u kancelariji K1, B NIJE delegiran. A ima privatan predmet, belešku uz taj predmet, belešku uz svog
klijenta i vezu u grafu sa ishodom. Opšta beleška o sudiji i opšta veza su namerno deljene.
Pravilo bajt-identičnosti: svaki B-ov odgovor je isti u svetu SA i BEZ A-ovih privatnih podataka.
"""
import json
import types

import pytest

import tests.ns008_fake as f8

K1 = "e1e1e1e1-1919-4000-8000-000000000001"
PA = "aaaaaaaa-1919-4000-8000-0000000000a1"
PB = "bbbbbbbb-1919-4000-8000-0000000000b1"
KL_A = "c1c1c1c1-1919-4000-8000-0000000000c1"
TAJNO = ("Petrović protiv Gradnja Invest DOO", "Klijent A popušta pod pritiskom", "Klijent Marković izbegava ročišta",
         "Zastarelost u predmetu A", PA, KL_A, "m-pred", "m-klij", "g-tajna")


def _svet(sa_a=True):
    t = {
        "predmeti": [{"id": PB, "user_id": "uid-B", "naziv": "B tekući", "tip": "radni", "status": "aktivan",
                      "opis": "B opis"}],
        "klijenti": [], "predmet_delegiranja": [],
        "kancelarije": [{"id": K1, "admin_uid": "uid-X"}],
        "kancelarija_clanovi": [{"kancelarija_id": K1, "user_id": "uid-A", "status": "ACTIVE"},
                                {"kancelarija_id": K1, "user_id": "uid-B", "status": "ACTIVE"}],
        "memory_entries": [{"id": "m-opsta", "kancelarija_id": K1, "user_id": "uid-A", "entity_type": "sudija",
                            "entity_id": "Petrović", "entity_name": "Sudija Petrović", "tip": "obrazac",
                            "sadrzaj": "Sudija traži tabelu rokova.", "vaznost": "normalna", "aktivan": True,
                            "izvor": "manual", "potvrde_count": 1, "created_at": "2026-09-01T00:00:00+00:00"}],
        "memory_graph_edges": [{"id": "g-opsta", "kancelarija_id": K1, "from_type": "argument", "from_id": "rok",
                                "from_naziv": "Propušten rok", "to_type": "sudija", "to_id": "Petrović",
                                "to_naziv": "Sudija Petrović", "relacija": "koristio_argument", "predmet_id": None,
                                "ishod": None, "snaga": 0.5, "kontekst": None, "created_at": "2026-09-01T00:00:00+00:00"}],
        "judge_patterns": [], "client_memory": [], "partner_profiles": [],
    }
    if sa_a:
        t["predmeti"].append({"id": PA, "user_id": "uid-A", "naziv": TAJNO[0], "tip": "radni", "status": "zatvoren",
                              "opis": "A opis"})
        t["klijenti"].append({"id": KL_A, "user_id": "uid-A", "ime": "Marković"})
        t["memory_entries"] += [
            {"id": "m-pred", "kancelarija_id": K1, "user_id": "uid-A", "entity_type": "predmet", "entity_id": PA,
             "entity_name": TAJNO[0], "tip": "napomena", "sadrzaj": TAJNO[1], "vaznost": "visoka", "aktivan": True,
             "izvor": "manual", "potvrde_count": 1, "created_at": "2026-09-02T00:00:00+00:00"},
            {"id": "m-klij", "kancelarija_id": K1, "user_id": "uid-A", "entity_type": "klijent", "entity_id": KL_A,
             "entity_name": "Marković", "tip": "preferencija", "sadrzaj": TAJNO[2], "vaznost": "visoka", "aktivan": True,
             "izvor": "manual", "potvrde_count": 1, "created_at": "2026-09-03T00:00:00+00:00"},
        ]
        t["memory_graph_edges"].append(
            {"id": "g-tajna", "kancelarija_id": K1, "from_type": "argument", "from_id": "zast", "from_naziv": TAJNO[3],
             "to_type": "predmet", "to_id": PA, "to_naziv": TAJNO[0], "relacija": "pobedio_pred", "predmet_id": PA,
             "ishod": "pobeda", "snaga": 0.9, "kontekst": "Klijent A popustio", "created_at": "2026-09-04T00:00:00+00:00"})
    return t


@pytest.fixture
def svet(monkeypatch):
    stanje = {"promptovi": []}

    def _napravi(sa_a=True):
        if "k" in stanje:
            f8.ocisti()
        stanje["k"], stanje["b"] = f8.pripremi(monkeypatch, _svet(sa_a))
        stanje["promptovi"] = []
        import shared.permissions as perm
        import shared.usage as us
        import routers.memory_graph as mg

        async def _politika(feature):
            return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

        async def _nista(*a, **kw):
            return None

        async def _model(oai, **kw):
            stanje["promptovi"].append(json.dumps(kw.get("messages"), ensure_ascii=False))
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="odgovor"))])
        monkeypatch.setattr(perm, "get_policy", _politika)
        monkeypatch.setattr(perm, "_check_dependencies", _nista)
        monkeypatch.setattr(us.UsageService, "consume", staticmethod(_nista))
        monkeypatch.setattr(mg, "_pozovi_mg_api", _model)
        try:
            from shared.rate import limiter
            monkeypatch.setattr(limiter, "enabled", False)
        except Exception:
            pass
        return stanje["k"], stanje["b"]
    yield _napravi, stanje
    f8.ocisti()


def H(ko):
    return {"Authorization": f"Bearer tok-{ko}"}      # tests/ns005_harness.TOKENI: tok-A → uid-A, tok-B → uid-B


# Svaka B-ova legacy čitajuća ruta (i one koje vraćaju postojanje kroz status: potvrdi, brisanje).
CITANJA = [
    ("GET", "/api/firma-memorija/sve"),
    ("GET", "/api/firma-memorija/sve?entity_type=predmet"),
    ("GET", "/api/firma-memorija/sve?limit=1"),           # tuđe „visoka" beleške su prve: limit PRE filtera bi odao postojanje
    ("GET", "/api/firma-memorija/pretrazi?limit=1"),
    ("GET", "/api/firma-memorija/pretrazi"),
    ("GET", "/api/firma-memorija/pretrazi?q=klijent"),
    ("GET", f"/api/firma-memorija/pretrazi?entity_type=predmet&entity_id={PA}"),
    ("GET", f"/api/firma-memorija/pretrazi?entity_type=klijent&entity_id={KL_A}"),
    ("GET", "/api/firma-memorija/sudija/Petrović"),
    ("GET", f"/api/firma-memorija/klijent/{KL_A}"),
    ("GET", f"/api/firma-memorija/kontekst-za-ai?sudija_ime=Petrović&klijent_ime={KL_A}"),
    ("GET", f"/api/memory-graph/entitet/predmet/{PA}"),
    ("GET", "/api/memory-graph/entitet/argument/zast"),
    ("GET", "/api/memory-graph/entitet/sudija/Petrović"),
    ("GET", "/api/memory-graph/upit?q=koji+argumenti+su+uspeli"),
    ("GET", f"/api/memory-graph/preporuka/{PB}"),
]
PISANJA_TUDJEG = [("POST", "/api/firma-memorija/potvrdi/m-pred"), ("POST", "/api/firma-memorija/potvrdi/m-klij"),
                  ("DELETE", "/api/firma-memorija/m-pred"), ("DELETE", "/api/firma-memorija/m-klij")]


def _odgovori(k, ko, rute):
    out = {f"{m} {p}": (r.status_code, r.text) for m, p in rute for r in [k.request(m, p, headers=H(ko))]}
    # zaštita od prazne provere: odbijena autentifikacija bi „sakrila" sve i test bi prošao bez ijedne provere
    assert not [r for r, (kod, _) in out.items() if kod in (401, 403, 429)], out
    return out


def test_B_ne_vidi_tudje_predmetne_i_klijentske_beleske_ni_veze(svet):
    napravi, st = svet
    k, _ = napravi(True)
    sa = _odgovori(k, "B", CITANJA)
    for ruta, (kod, telo) in sa.items():
        for t in TAJNO:
            if t in ruta:            # eho onoga što je B SAM poslao (npr. "entitet": {"id": ...}) nije otkriće
                continue
            assert t not in telo, (ruta, t)
    for p in st["promptovi"]:
        for t in TAJNO:
            assert t not in p, ("prompt modela", t)


def test_B_odgovori_bajt_identicni_sa_i_bez_A(svet):
    """Ni brojevi, ni redosled, ni status ne smeju da odaju da A-ovi privatni podaci postoje."""
    napravi, st = svet
    k, _ = napravi(True)
    sa, prompt_sa = _odgovori(k, "B", CITANJA + PISANJA_TUDJEG), list(st["promptovi"])
    k, _ = napravi(False)
    bez, prompt_bez = _odgovori(k, "B", CITANJA + PISANJA_TUDJEG), list(st["promptovi"])
    razlike = [r for r in sa if sa[r] != bez[r]]
    assert razlike == [], razlike
    assert prompt_sa == prompt_bez


def test_B_ne_moze_da_potvrdi_ni_obrise_tudju_belesku(svet):
    napravi, _ = svet
    k, b = napravi(True)
    for m, p in PISANJA_TUDJEG:
        assert k.request(m, p, headers=H("B")).status_code == 404, p
    redovi = {r["id"]: r for r in b.tabele["memory_entries"]}
    assert redovi["m-pred"]["aktivan"] is True and redovi["m-klij"]["aktivan"] is True
    assert int(redovi["m-pred"].get("potvrde_count") or 0) == 1


def test_opsta_znanja_kancelarije_i_dalje_deljena(svet):
    """Postojeći ugovor: beleška o sudiji i opšta veza su vidljive kolegi; B može da ih potvrdi."""
    napravi, _ = svet
    k, _ = napravi(True)
    sve = k.get("/api/firma-memorija/sve", headers=H("B")).json()
    assert [m["id"] for m in sve["memorije"]] == ["m-opsta"] and sve["by_type"] == {"sudija": 1}
    assert "Sudija traži tabelu rokova." in k.get("/api/firma-memorija/sudija/Petrović", headers=H("B")).text
    e = k.get("/api/memory-graph/entitet/sudija/Petrović", headers=H("B")).json()
    assert e["ukupno_veza"] == 1
    assert k.post("/api/firma-memorija/potvrdi/m-opsta", headers=H("B")).status_code == 200


def test_vlasnik_A_vidi_sve_svoje(svet):
    napravi, st = svet
    k, _ = napravi(True)
    sve = k.get("/api/firma-memorija/sve", headers=H("A")).json()
    assert {m["id"] for m in sve["memorije"]} == {"m-opsta", "m-pred", "m-klij"}
    e = k.get(f"/api/memory-graph/entitet/predmet/{PA}", headers=H("A")).json()
    assert e["ukupno_veza"] == 1
    k.get("/api/memory-graph/upit?q=koji+argumenti+su+uspeli", headers=H("A"))
    assert TAJNO[3] in st["promptovi"][-1]


def test_delegiranje_otvara_predmetnu_belesku_a_opoziv_je_zatvara(svet):
    """Delegat vidi belešku i vezu delegiranog predmeta (kanonski ACL); klijent ostaje vlasnikov. Opoziv važi odmah."""
    napravi, _ = svet
    k, b = napravi(True)
    b.tabele["predmet_delegiranja"].append({"predmet_id": PA, "na_user_id": "uid-B", "status": "aktivno"})
    ids = {m["id"] for m in k.get("/api/firma-memorija/sve", headers=H("B")).json()["memorije"]}
    assert ids == {"m-opsta", "m-pred"}
    assert k.get(f"/api/memory-graph/entitet/predmet/{PA}", headers=H("B")).json()["ukupno_veza"] == 1
    b.tabele["predmet_delegiranja"][0]["status"] = "opozvano"
    ids = {m["id"] for m in k.get("/api/firma-memorija/sve", headers=H("B")).json()["memorije"]}
    assert ids == {"m-opsta"}

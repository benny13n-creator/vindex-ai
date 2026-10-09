"""NS007 Task 8 — izvršilac HEARING_PREP nad realističnim predmetom (tests/ns006_realni_predmet.py), ročište sutra.

Model je zamenjen funkcijom koja čita PRAVI prompt. Dokazuje se:
  • tačno jedan poziv modela; podaci o ročištu, činjenice, protivrečnosti i radnje su iz baze, sa poreklom i izvorima;
    svaka referenca u proizvodu postoji u bazi; prompt ne sadrži ništa iz tuđeg predmeta;
  • izmišljena referenca, citat propisa/odluke i predviđanje ishoda se odbacuju (i broje);
  • pad modela → priprema iz baze se čuva (DETERMINISTIC), bez ponovnog poziva;
  • kapije pre modela: otkazano / pomereno ročište, zatvoren predmet, promenjena verzija Genome-a, tuđ predmet →
    FAILED bez poziva modela; nepročitan izvor konteksta ili izgubljen zakup → bez poziva modela, bez proizvoda;
  • nijedan spoljni efekat: upisi samo u tabele autonomnog rada i računovodstvo.
"""
import asyncio
import json
import re
from datetime import date, timedelta

import pytest

import tests.ns007_fake as f7
from services import autonomy as au
from services.agent_tasks import hearing_prep as hp
from tests import ns006_realni_predmet as rp

DANAS = date(2026, 10, 10)
DOZVOLJENI_UPISI = {"autonomy_work_items", "autonomy_cycles", "usage_events", "audit_immutable", "ai_provenance",
                    "ai_call_log"}


def _model(odgovor=None, pada=False):
    stanje = {"pozivi": [], "prompt": None}

    async def poziv(prompt, predmet_id):
        stanje["pozivi"].append(predmet_id)
        stanje["prompt"] = prompt
        if pada:
            raise TimeoutError("model nije odgovorio")
        if odgovor is not None:
            return json.dumps(odgovor(prompt), ensure_ascii=False)
        ids = re.findall(r"\[([0-9a-f-]{36}|ai:[0-9a-f]+)\]", prompt)
        kontr = next(i for i in ids if i.startswith("ffff"))
        return json.dumps({"pitanja": [{"tekst": "Proveriti koji je datum uručenja tačan pre ročišta.", "refs": [kontr]}],
                           "beleske": [{"tekst": "Pripremiti dostavnicu kao dokaz o datumu uručenja.", "refs": [ids[1]]}]},
                          ensure_ascii=False)
    return poziv, stanje


@pytest.fixture
def svet(monkeypatch):
    t = rp.tabele(danas=DANAS)
    t["rocista"][0]["datum"] = (DANAS + timedelta(days=1)).isoformat()
    t["rocista"][0]["sudnica"] = "12"
    t["predmeti"][0]["kancelarija_id"] = None
    t.setdefault("kancelarija_clanovi", [])
    _, baza = f7.pripremi(monkeypatch, t)
    monkeypatch.setattr(hp, "_danas", lambda: DANAS)
    import workers.background_agents as ba
    monkeypatch.setattr(ba, "_agent_modules", lambda: [hp])
    monkeypatch.setenv("AUTONOMY_BUDGET_PER_ORG_DAILY", "5")
    yield baza, ba, monkeypatch
    f7.ocisti()


def _ciklus(ba):
    return asyncio.run(ba.run_autonomy_cycle("run-t8"))


def _posao(baza):
    return baza.tabele["autonomy_work_items"][0]


def test_priprema_iz_baze_jedan_poziv_modela_sve_reference_postoje(svet):
    baza, ba, mp = svet
    model, st = _model()
    mp.setattr(hp, "_pozovi_model", model)
    s = _ciklus(ba)
    assert s["spremno"] == 1 and len(st["pozivi"]) == 1
    p = _posao(baza)
    assert p["status"] == "READY_FOR_REVIEW" and p["quality_state"] == "AI_PREPARED_FOR_REVIEW"
    c = p["content_json"]
    roc = baza.tabele["rocista"][0]
    assert c["rociste"] == {"id": rp.ROCISTE, "datum": roc["datum"], "vreme": "10:00", "sud": "Osnovni sud u Beogradu",
                            "sudnica": "12", "poreklo": "SOURCE_FACT"}, "ročište je iz baze, ne od modela"
    assert c["predmet"]["genome_verzija"] == 4 and c["predmet"]["naziv"] == "Petrović protiv Gradnja Invest DOO"
    assert c["kljucne_cinjenice"] and all(x["poreklo"] in ("SOURCE_FACT", "HUMAN_CONFIRMED") for x in c["kljucne_cinjenice"])
    assert len(c["protivrecnosti"]) == 1 and c["protivrecnosti"][0]["sporna_tacka"] == "datum uručenja rešenja o otkazu"
    assert c["ai"]["stanje"] == "PRIPREMLJENO" and len(c["ai"]["pitanja"]) == 1 and len(c["ai"]["beleske"]) == 1
    assert all(i["poreklo"] == "AI_ANALYSIS" for i in c["ai"]["pitanja"] + c["ai"]["beleske"])
    assert "nije utvrđena činjenica" in c["ai"]["napomena"]
    # svaka referenca postoji u bazi
    tabela = {"tvrdnja": {r["id"] for r in baza.tabele["predmet_dokazi"]}, "dokument": {r["id"] for r in baza.tabele["predmet_dokumenti"]},
              "kontradikcija": {r["id"] for r in baza.tabele["predmet_contradictions"]}, "rociste": {rp.ROCISTE},
              "case_action": {str(r["id"]) for r in baza.tabele["case_actions"]}}
    for ref in p["source_refs"]:
        if ref["tip"] == "genome":
            assert ref["verzija"] == 4
        else:
            assert ref["id"] in tabela[ref["tip"]], ref
    assert p["title"] == "Priprema za ročište 11.10.2026. — Petrović protiv Gradnja Invest DOO"
    assert p["summary"].startswith("Ročište sutra u 10:00, Osnovni sud u Beogradu.")
    # prompt ne nosi ništa iz tuđeg predmeta
    assert "Jovanović" not in st["prompt"] and rp.PB not in st["prompt"]
    assert p["budget_units"] == 1


def test_izmisljeno_citat_i_predvidjanje_se_odbacuju(svet):
    baza, ba, mp = svet

    def odgovor(prompt):
        pravi = re.findall(r"\[([0-9a-f-]{36})\]", prompt)[1]
        return {"pitanja": [{"tekst": "Da li je sudija Marković već odlučivao?", "refs": ["izmisljen-id"]},
                            {"tekst": "Pozvati se na čl. 179 Zakona o radu.", "refs": [pravi]},
                            {"tekst": "Verovatnoća uspeha je 80%.", "refs": [pravi]},
                            {"tekst": "Uporediti sa odlukom Rev 1234/2023.", "refs": [pravi]},
                            {"tekst": "Bez reference."},
                            {"tekst": "Proveriti dostavnicu.", "refs": [pravi]}],
                "beleske": "nije lista"}
    model, _ = _model(odgovor)
    mp.setattr(hp, "_pozovi_model", model)
    _ciklus(ba)
    ai = _posao(baza)["content_json"]["ai"]
    assert [x["tekst"] for x in ai["pitanja"]] == ["Proveriti dostavnicu."] and ai["beleske"] == []
    assert ai["odbaceno"] == 5


def test_sve_odbaceno_znaci_bez_ai_dela(svet):
    baza, ba, mp = svet
    model, _ = _model(lambda p: {"pitanja": [{"tekst": "Šansa za uspeh je velika.", "refs": [rp.T1]}], "beleske": []})
    mp.setattr(hp, "_pozovi_model", model)
    _ciklus(ba)
    p = _posao(baza)
    assert p["quality_state"] == "DETERMINISTIC" and p["content_json"]["ai"]["stanje"] == "NIJE_PRIPREMLJENO"


def test_pad_modela_cuva_pripremu_iz_baze_bez_ponovnog_poziva(svet):
    baza, ba, mp = svet
    model, st = _model(pada=True)
    mp.setattr(hp, "_pozovi_model", model)
    _ciklus(ba)
    _ciklus(ba)
    p = _posao(baza)
    assert p["status"] == "READY_FOR_REVIEW" and p["quality_state"] == "DETERMINISTIC"
    assert p["content_json"]["ai"]["razlog"] == "MODEL_NEDOSTUPAN" and p["content_json"]["kljucne_cinjenice"]
    assert len(st["pozivi"]) == 1


@pytest.mark.parametrize("izmena,kod", [
    (lambda b: b.tabele["rocista"][0].update(status="otkazano"), "HEARING_NOT_ACTIVE"),
    (lambda b: b.tabele["rocista"][0].update(vreme="13:00"), "HEARING_CHANGED"),
    (lambda b: b.tabele["predmeti"][0].update(status="zatvoren"), "MATTER_NOT_ACTIVE"),
    (lambda b: b.tabele["predmeti"][0]["case_dna"].update(verzija=5), "SOURCE_VERSION_CHANGED"),
    (lambda b: b.tabele["rocista"].clear(), "HEARING_NOT_FOUND"),
])
def test_kapije_pre_modela_konacan_neuspeh(svet, izmena, kod):
    baza, ba, mp = svet
    model, st = _model()
    mp.setattr(hp, "_pozovi_model", model)
    plan = asyncio.run(hp.planiraj(baza))
    asyncio.run(au.upisi_kandidata(baza, plan["kandidati"][0]))
    izmena(baza)
    # izvršenje BEZ ponovnog planiranja (stanje se promenilo između plana i izvršenja)
    mp.setattr(hp, "planiraj", lambda supa: _prazno())
    _ciklus(ba)
    p = _posao(baza)
    assert st["pozivi"] == [] and p["status"] == "FAILED" and p["safe_error_code"] == kod, (p["status"], p["safe_error_code"])
    assert p["content_json"] is None


async def _prazno():
    return {"kandidati": [], "ponisteni": []}


def test_tudj_predmet_konacan_neuspeh_bez_modela(svet):
    baza, ba, mp = svet
    model, st = _model()
    mp.setattr(hp, "_pozovi_model", model)
    plan = asyncio.run(hp.planiraj(baza))
    k = dict(plan["kandidati"][0], predmet_id=rp.PB)       # posao koji tvrdi da je ročište A u predmetu B
    asyncio.run(au.upisi_kandidata(baza, k))
    mp.setattr(hp, "planiraj", lambda supa: _prazno())
    _ciklus(ba)
    assert st["pozivi"] == [] and _posao(baza)["safe_error_code"] == "HEARING_NOT_FOUND"


def test_predmet_vise_nije_vlasnikov_konacan_neuspeh_bez_modela(svet):
    """Ročište i posao su dosledni, ali predmet više ne pripada korisniku (NS006 vlasništvo → 404)."""
    baza, ba, mp = svet
    model, st = _model()
    mp.setattr(hp, "_pozovi_model", model)
    asyncio.run(au.upisi_kandidata(baza, asyncio.run(hp.planiraj(baza))["kandidati"][0]))
    baza.tabele["predmeti"][0]["user_id"] = "uid-B"
    mp.setattr(hp, "planiraj", lambda supa: _prazno())
    _ciklus(ba)
    p = _posao(baza)
    assert st["pozivi"] == [] and p["status"] == "FAILED" and p["safe_error_code"] == "MATTER_NOT_ACCESSIBLE"


@pytest.mark.parametrize("pad", ["predmet_dokazi", "rocista_kontekst", "zakup"])
def test_nepročitan_kontekst_ili_izgubljen_zakup_bez_modela_i_bez_proizvoda(svet, pad):
    baza, ba, mp = svet
    model, st = _model()
    mp.setattr(hp, "_pozovi_model", model)
    if pad == "predmet_dokazi":
        baza.greske["predmet_dokazi"] = RuntimeError("izvor nedostupan")
    elif pad == "rocista_kontekst":
        baza.greske["case_actions"] = RuntimeError("izvor nedostupan")
    else:
        async def nije_nas(supa, wid, owner):
            return False
        mp.setattr(au, "jos_vazi_zakup", nije_nas)
    s = _ciklus(ba)
    p = _posao(baza)
    assert st["pozivi"] == [] and s["prolazno"] == 1 and p["status"] == "RUNNING" and p["content_json"] is None


def test_nijedan_spoljni_efekat(svet):
    baza, ba, mp = svet
    model, _ = _model()
    mp.setattr(hp, "_pozovi_model", model)
    pre = len(baza.dnevnik)
    _ciklus(ba)
    upisi = {z["tabela"] for z in baza.dnevnik[pre:] if z["radnja"] in ("insert", "update", "upsert", "delete")}
    assert upisi <= DOZVOLJENI_UPISI, upisi - DOZVOLJENI_UPISI
    assert "predmeti" not in upisi and "case_actions" not in upisi and "staging_memory" not in upisi


def test_izvori_imaju_naziv_dokumenta(svet):
    baza, ba, mp = svet
    model, _ = _model()
    mp.setattr(hp, "_pozovi_model", model)
    _ciklus(ba)
    c = _posao(baza)["content_json"]
    nazivi = {d["id"]: d["naziv_fajla"] for d in baza.tabele["predmet_dokumenti"]}
    for x in c["kljucne_cinjenice"]:
        assert x["dokument_naziv"] == nazivi.get(x["dokument_id"])
    assert {u["dokument_naziv"] for u in c["protivrecnosti"][0]["ucesnici"]} == {"Rešenje o otkazu.pdf", "Dostavnica.pdf"}

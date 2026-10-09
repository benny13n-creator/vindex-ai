"""NS007 Task 9–10 — PRECEDENT_IMPACT iz PROVERENE preporuke Precedents Radar-a.

Planer (0 poziva modela): posao samo kad preporuka važi, predmet je vlasnikov/aktivan/sa Genome-om, identitet odluke
je ispravan, odnos utemeljen, a ODLUKA POSTOJI u korpusu i sud se poklapa. Izmišljena odluka → nikad; korpus
nedostupan → ne u ovom ciklusu (pa da, kad se vrati); ista odluka dva dana zaredom + ista analiza → jedan posao,
bez ponovne provere izvora.
Izvršilac (jedan poziv modela): izvor ponovo proveren; identitet odluke iz korpusa; uticaj se prikazuje SAMO uz
doslovan izvod iz odluke; drugi propisi/odluke, procenti i predviđanje se odbacuju; klasifikacija bez potkrepljenog
uticaja nije odbranjiva; izvor nestao posle planiranja → FAILED bez modela; korpus nedostupan → bez modela.
"""
import asyncio
import json
import re
from datetime import datetime, timezone

import pytest

import tests.ns007_fake as f7
from services import autonomy as au
from services.agent_tasks import precedents_radar as pr
from tests import ns006_realni_predmet as rp
from tests import ns007_korpus as kor

REC = "dddd0001-0000-4000-8000-000000000001"


def _rec(rid=REC, dn=kor.ODLUKA, odnos="podupire", status="pending", user="uid-A", predmet=rp.PA, sud="Vrhovni sud", obr="Ide u prilog."):
    return {"id": rid, "user_id": user, "predmet_id": predmet, "agent_type": "precedents_radar", "status": status,
            "naslov": "Nova praksa", "dedup_key": f"precedent:{predmet}:{dn}", "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": {"odnos": odnos, "obrazlozenje": obr,
                        "odluka": {"decision_number": dn, "court": sud, "date": "2023-05-10", "matter": "radno", "score": 0.81}}}


@pytest.fixture
def svet(monkeypatch):
    t = rp.tabele()
    t["agent_recommendations"] = [_rec()]
    t.setdefault("kancelarija_clanovi", [])
    _, baza = f7.pripremi(monkeypatch, t)
    ind = kor.postavi(monkeypatch)
    import workers.background_agents as ba
    monkeypatch.setattr(ba, "_agent_modules", lambda: [pr])
    monkeypatch.setenv("AUTONOMY_BUDGET_PER_ORG_DAILY", "5")
    yield baza, ind, ba, monkeypatch
    f7.ocisti()


def _plan(baza):
    return asyncio.run(pr.planiraj(baza))


def _model(odgovor=None, pada=False):
    st = {"pozivi": [], "prompt": None}

    async def poziv(prompt, predmet_id):
        st["pozivi"].append(predmet_id)
        st["prompt"] = prompt
        if pada:
            raise TimeoutError("model nije odgovorio")
        if odgovor:
            return json.dumps(odgovor(prompt), ensure_ascii=False)
        ids = re.findall(r"\[([^\]]+)\]", prompt.split("SPORNA PITANJA PREDMETA:")[1])
        kontr = next(i for i in ids if i.startswith("ffff"))
        return json.dumps({"klasifikacija": "u_prilog",
                           "uticaj": [{"tekst": "Odluka daje prednost datumu iz dostavnice — to podupire tvrdnju klijenta o kasnijem uručenju.",
                                       "refs": [kontr], "izvod": "dan uručenja utvrđen u dostavnici ima prednost nad datumom navedenim u samom rešenju"}],
                           "pitanja": [{"tekst": "Da li je dostavnica potpisana lično od klijenta?", "refs": [kontr]}],
                           "razmotriti_argument": {"da": True, "razlog": "Argument o roku za tužbu treba vezati za datum iz dostavnice."}},
                          ensure_ascii=False)
    return poziv, st


# ── Task 9: planer ──────────────────────────────────────────────────────────────

def test_proverena_preporuka_jedan_kandidat_bez_modela(svet):
    baza, ind, _, mp = svet
    import openai

    class _Z:
        def __init__(self, *a, **k):
            raise AssertionError("planer ne zove model")
    mp.setattr(openai, "OpenAI", _Z)
    mp.setattr(openai, "AsyncOpenAI", _Z)
    p = _plan(baza)
    assert len(p["kandidati"]) == 1
    k = p["kandidati"][0]
    assert k["trigger_ref"] == kor.ODLUKA and k["recommendation_id"] == REC and k["source_version"] == 4
    assert k["dedupe_key"] == f"PRECEDENT_IMPACT:{rp.PA}:{kor.ODLUKA}:g4" and k["cost_class"] == "PAID"
    assert "u prilog predmeta" in k["reason"] and "Vrhovni sud Rev 1234/2023 od 2023-05-10" in k["reason"] and "proveren" in k["reason"]


@pytest.mark.parametrize("rec,razlog", [
    (_rec(dn="Rev 9999/2099"), "IZVOR_NIJE_PRONADJEN"),
    (_rec(sud="Apelacioni sud u Nišu"), "IZVOR_NE_ODGOVARA"),
    (_rec(status="rejected"), None),                          # odbačene se ni ne čitaju (filter u upitu)
    (_rec(odnos="neutralno"), "ODNOS_NIJE_UTEMELJEN"),
    (_rec(obr=""), "ODNOS_NIJE_UTEMELJEN"),
    (_rec(dn="_unk_140234"), "IDENTITET_ODLUKE_NEISPRAVAN"),
    (_rec(dn="Rev"), "IDENTITET_ODLUKE_NEISPRAVAN"),
    (_rec(predmet=rp.PB), "VLASNIK_SE_NE_POKLAPA"),
])
def test_nepodobna_preporuka_nema_posla(svet, rec, razlog):
    baza, *_ = svet
    baza.tabele["agent_recommendations"] = [rec]
    p = _plan(baza)
    assert p["kandidati"] == [] and p["preskoceno"] == ({razlog: 1} if razlog else {}), p["preskoceno"]


def test_zatvoren_predmet_nema_posla(svet):
    baza, *_ = svet
    baza.tabele["predmeti"][0]["status"] = "zatvoren"
    assert _plan(baza)["preskoceno"] == {"PREDMET_ZAVRSEN": 1}


def test_korpus_nedostupan_ne_u_ovom_ciklusu_pa_da(svet):
    baza, ind, *_ = svet
    ind.nedostupan = True
    p = _plan(baza)
    assert p["kandidati"] == [] and p["preskoceno"] == {"IZVOR_NEDOSTUPAN": 1}
    ind.nedostupan = False
    assert len(_plan(baza)["kandidati"]) == 1


def test_ista_odluka_dva_dana_zaredom_jedan_posao_bez_nove_provere(svet):
    baza, ind, ba, mp = svet
    model, st = _model()
    mp.setattr(pr, "_pozovi_model_uticaj", model)
    asyncio.run(ba.run_autonomy_cycle("dan1"))
    upita_posle_prvog = len(ind.upiti)
    baza.tabele["agent_recommendations"].append(_rec(rid="dddd0002-0000-4000-8000-000000000002"))   # radar sutra ponovo
    s = asyncio.run(ba.run_autonomy_cycle("dan2"))
    assert len(baza.tabele["autonomy_work_items"]) == 1 and len(st["pozivi"]) == 1
    assert s["planirano"] == 0
    assert len(ind.upiti) == upita_posle_prvog, "isti okidač: izvor se ne proverava ponovo"


def test_nova_verzija_genoma_nova_analiza_uticaja(svet):
    baza, *_ = svet
    asyncio.run(au.upisi_kandidata(baza, _plan(baza)["kandidati"][0]))
    baza.tabele["predmeti"][0]["case_dna"]["verzija"] = 5
    p = _plan(baza)
    assert len(p["kandidati"]) == 1 and p["kandidati"][0]["dedupe_key"].endswith(":g5")


def test_fetch_odluke_razlikuje_nedostupno_od_nepostojeceg(svet):
    from app.services.retrieve import RetrievalUnavailable
    from routers.praksa import _fetch_decision_chunks
    _, ind, *_ = svet
    meta, tekst = _fetch_decision_chunks(kor.ODLUKA, True)
    assert meta["broj"] == kor.ODLUKA and meta["sud"] == "Vrhovni sud" and "dostavnici ima prednost" in tekst
    with pytest.raises(ValueError):
        _fetch_decision_chunks("Rev 9999/2099", True)
    ind.nedostupan = True
    with pytest.raises(RetrievalUnavailable):
        _fetch_decision_chunks(kor.ODLUKA, True)
    with pytest.raises(ValueError):
        _fetch_decision_chunks(kor.ODLUKA)                  # postojeći pozivaoci: ponašanje nepromenjeno


# ── Task 10: izvršilac ──────────────────────────────────────────────────────────

def _posao(baza):
    return baza.tabele["autonomy_work_items"][0]


def test_analiza_uticaja_sa_proverenim_izvorom_i_izvodom(svet):
    baza, ind, ba, mp = svet
    model, st = _model()
    mp.setattr(pr, "_pozovi_model_uticaj", model)
    s = asyncio.run(ba.run_autonomy_cycle("r1"))
    assert s["spremno"] == 1 and len(st["pozivi"]) == 1
    p = _posao(baza)
    c = p["content_json"]
    assert p["status"] == "READY_FOR_REVIEW" and p["quality_state"] == "AI_PREPARED_FOR_REVIEW"
    assert c["izvor"]["broj"] == kor.ODLUKA and c["izvor"]["sud"] == "Vrhovni sud" and c["izvor"]["datum"] == "2023-05-10"
    assert c["izvor"]["provereno"] is True and c["izvor"]["poreklo"] == "SOURCE_FACT"
    assert c["ai"]["klasifikacija"] == "podupire" and len(c["ai"]["uticaj"]) == 1
    u = c["ai"]["uticaj"][0]
    assert u["izvod_proveren"] and u["izvod_iz_odluke"].lower() in (kor.TEKST_OBRAZLOZENJE.lower())
    assert c["ai"]["razmotriti_argument"]["da"] is True and "nije utvrđena činjenica" in c["ai"]["napomena"]
    assert c["zasto"]["odnos_radar"] == "podupire" and c["zasto"]["poreklo"] == "AI_ANALYSIS"
    assert p["title"] == f"Nova praksa: {kor.ODLUKA} (Vrhovni sud) — Petrović protiv Gradnja Invest DOO"
    assert {"tip": "odluka", "broj": kor.ODLUKA, "sud": "Vrhovni sud", "datum": "2023-05-10", "korpus": "sudska_praksa"} in p["source_refs"]
    assert {"tip": "preporuka", "id": REC} in p["source_refs"]
    assert "Jovanović" not in st["prompt"] and kor.TEKST_IZREKA in st["prompt"]
    assert p["recommendation_id"] == REC


def test_izmisljen_izvod_drugi_izvori_procenti_i_predvidjanje_se_odbacuju(svet):
    baza, ind, ba, mp = svet

    def odgovor(prompt):
        k = re.findall(r"\[(ffff[^\]]+)\]", prompt)[0]
        return {"klasifikacija": "u_prilog",
                "uticaj": [{"tekst": "Odluka kaže da poslodavac uvek gubi.", "refs": [k], "izvod": "poslodavac uvek gubi spor o otkazu"},
                           {"tekst": "Uporedi sa Rev 555/2020.", "refs": [k], "izvod": "dan uručenja utvrđen u dostavnici ima prednost"},
                           {"tekst": "Šanse su 70%.", "refs": [k], "izvod": "dan uručenja utvrđen u dostavnici ima prednost"},
                           {"tekst": "Sud će usvojiti tužbu.", "refs": [k], "izvod": "dan uručenja utvrđen u dostavnici ima prednost"},
                           {"tekst": "Bez izvoda.", "refs": [k]},
                           {"tekst": "Izmišljena referenca.", "refs": ["nema-ga"], "izvod": "dan uručenja utvrđen u dostavnici ima prednost"}],
                "pitanja": [], "razmotriti_argument": {"da": True, "razlog": "Verovatnoća uspeha raste."}}
    model, _ = _model(odgovor)
    mp.setattr(pr, "_pozovi_model_uticaj", model)
    asyncio.run(ba.run_autonomy_cycle("r1"))
    ai = _posao(baza)["content_json"]["ai"]
    assert ai["uticaj"] == [] and ai["odbaceno"] == 6
    assert ai["klasifikacija"] == "nije_utvrdjeno" and ai["razmotriti_argument"] == {"da": False, "razlog": None}
    assert _posao(baza)["quality_state"] == "DETERMINISTIC"


@pytest.mark.parametrize("izmena,kod,prolazno", [
    (lambda b, i: i.korpus.clear(), "SOURCE_NOT_VERIFIED", False),
    (lambda b, i: setattr(i, "nedostupan", True), None, True),
    (lambda b, i: b.tabele["agent_recommendations"][0].update(status="rejected"), "RECOMMENDATION_NOT_ACTIVE", False),
    (lambda b, i: b.tabele["predmeti"][0].update(status="zatvoren"), "MATTER_NOT_ACTIVE", False),
    (lambda b, i: b.tabele["predmeti"][0]["case_dna"].update(verzija=9), "SOURCE_VERSION_CHANGED", False),
])
def test_kapije_posle_planiranja_bez_modela(svet, izmena, kod, prolazno):
    baza, ind, ba, mp = svet
    model, st = _model()
    mp.setattr(pr, "_pozovi_model_uticaj", model)
    asyncio.run(au.upisi_kandidata(baza, _plan(baza)["kandidati"][0]))
    izmena(baza, ind)

    async def prazno(supa):
        return {"kandidati": [], "ponisteni": []}
    mp.setattr(pr, "planiraj", prazno)
    s = asyncio.run(ba.run_autonomy_cycle("r1"))
    p = _posao(baza)
    assert st["pozivi"] == [] and p["content_json"] is None
    if prolazno:
        assert s["prolazno"] == 1 and p["status"] == "RUNNING"
    else:
        assert p["status"] == "FAILED" and p["safe_error_code"] == kod


def test_ponovljen_ciklus_jedan_proizvod_jedan_poziv(svet):
    baza, ind, ba, mp = svet
    model, st = _model()
    mp.setattr(pr, "_pozovi_model_uticaj", model)
    for i in range(3):
        asyncio.run(ba.run_autonomy_cycle(f"r{i}"))
    assert len(baza.tabele["autonomy_work_items"]) == 1 and len(st["pozivi"]) == 1


def test_pad_modela_cuva_proveren_izvor_bez_ponovnog_poziva(svet):
    baza, ind, ba, mp = svet
    model, st = _model(pada=True)
    mp.setattr(pr, "_pozovi_model_uticaj", model)
    asyncio.run(ba.run_autonomy_cycle("r1"))
    asyncio.run(ba.run_autonomy_cycle("r2"))
    p = _posao(baza)
    assert p["status"] == "READY_FOR_REVIEW" and p["quality_state"] == "DETERMINISTIC"
    assert p["content_json"]["ai"]["razlog"] == "MODEL_NEDOSTUPAN" and p["content_json"]["izvor"]["provereno"] is True
    assert len(st["pozivi"]) == 1


def test_bez_spornih_pitanja_nema_genericke_analize(svet):
    baza, ind, ba, mp = svet
    model, st = _model()
    mp.setattr(pr, "_pozovi_model_uticaj", model)
    g = baza.tabele["predmeti"][0]["case_dna"]
    g.pop("pravna_teorija", None)
    g["kontradikcije"] = []                                  # i analiza (NS006 „ili-ili" bi inače prešla na nju)
    baza.tabele["predmet_contradictions"].clear()
    asyncio.run(ba.run_autonomy_cycle("r1"))
    p = _posao(baza)
    assert st["pozivi"] == [] and p["status"] == "FAILED" and p["safe_error_code"] == "NO_MATTER_ISSUES"


def test_klasifikacija_bez_potkrepljenog_uticaja_nije_odbranjiva(svet):
    """Pitanja za pregled su ispravna, ali uticaj nema doslovan izvod → klasifikacija „u prilog" se NE prikazuje."""
    baza, ind, ba, mp = svet

    def odgovor(prompt):
        k = re.findall(r"\[(ffff[^\]]+)\]", prompt)[0]
        return {"klasifikacija": "u_prilog",
                "uticaj": [{"tekst": "Odluka je povoljna.", "refs": [k], "izvod": "tekst koga nema u odluci uopšte nigde"}],
                "pitanja": [{"tekst": "Proveriti potpis na dostavnici.", "refs": [k]}],
                "razmotriti_argument": {"da": True, "razlog": "Preispitati rok."}}
    model, _ = _model(odgovor)
    mp.setattr(pr, "_pozovi_model_uticaj", model)
    asyncio.run(ba.run_autonomy_cycle("r1"))
    ai = _posao(baza)["content_json"]["ai"]
    assert ai["stanje"] == "PRIPREMLJENO" and len(ai["pitanja"]) == 1 and ai["uticaj"] == []
    assert ai["klasifikacija"] == "nije_utvrdjeno" and ai["razmotriti_argument"]["da"] is False

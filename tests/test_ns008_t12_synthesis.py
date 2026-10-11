# -*- coding: utf-8 -*-
"""NS008 Task 12 — POST /api/law-brain/predmeti/{id}/sinteza: jedini poziv modela, samo na izričit klik.

Model vidi SAMO autorizovane reference; tvrdnja sa izmišljenom referencom, pogrešnom vrstom, procentom,
propisom, uopštavanjem ili brojem bez izvora se odbacuje. Dva fizička POST-a sa istim ključem = 1 poziv
modela, 1 naplata, isti odgovor. Bez osnova → bez modela i bez kredita. Pad modela → 503, bez kredita.
"""
import json
import uuid

import pytest

import tests.ns008_fake as f8
from tests.test_ns008_t11_api import PA_CUR, PA_OLD, PB_CUR, _tabele

PRAZAN = "aaaaaaaa-1212-4000-8000-0000000000ee"


@pytest.fixture
def svet(monkeypatch):
    t = _tabele()
    t["predmeti"].append({"id": PRAZAN, "user_id": "uid-A", "naziv": "Bez iskustva", "tip": "upravni",
                          "oblast": "upravno", "status": "aktivan", "case_dna": {}})
    k, b = f8.pripremi(monkeypatch, t)
    import shared.permissions as perm
    import shared.usage as us
    import services.law_brain_sinteza as S

    async def _politika(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

    async def _nista(*a, **kw):
        return None
    krediti = []

    async def _naplati(*a, **kw):
        krediti.append((a, kw))
    monkeypatch.setattr(perm, "get_policy", _politika)
    monkeypatch.setattr(perm, "_check_dependencies", _nista)
    monkeypatch.setattr(us.UsageService, "consume", staticmethod(_naplati))
    pozivi = []
    odgovor = {"v": None}

    async def _model(prompt, predmet_id):
        pozivi.append(prompt)
        if isinstance(odgovor["v"], Exception):
            raise odgovor["v"]
        return json.dumps(odgovor["v"])
    monkeypatch.setattr(S, "_pozovi_model_sinteze", _model)
    yield k, b, krediti, pozivi, odgovor
    f8.ocisti()


def _refs(prompt):
    return {red.split(" ", 1)[0]: red for red in prompt.splitlines()[1:]}


def _post(k, pid, ko="A", kljuc=None):
    h = f8.zaglavlje(ko)
    if kljuc:
        h["Idempotency-Key"] = kljuc
    return k.post(f"/api/law-brain/predmeti/{pid}/sinteza", headers=h)


def _model_izlaz_iz(prompt):
    r = _refs(prompt)
    ishod = next(x for x, red in r.items() if "HUMAN_CONFIRMED_OUTCOME" in red)
    overen = next(x for x, red in r.items() if "LAWYER_VERIFIED_ARTIFACT" in red and "Overen rad" in red)
    slican = next(x for x, red in r.items() if "Raniji predmet 1" in red)
    beleska = next(x for x, red in r.items() if "Beleška kolege" in red)
    return {"tvrdnje": [
        {"tekst": "Raniji sličan predmet je istog tipa i pred istim sudom.", "vrsta": "iskustvo", "refs": [slican]},
        {"tekst": "U ranijem predmetu ishod je bio nagodba.", "vrsta": "ishod", "refs": [ishod]},
        {"tekst": "Kancelarija ima overenu tužbu koja može poslužiti kao polazna osnova.", "vrsta": "overen_rad", "refs": [overen]},
        {"tekst": "Kolega beleži da sudija traži tabelu rokova.", "vrsta": "neproverena_beleska", "refs": [beleska]},
        {"tekst": "Izmišljen predmet sa ishodom pobeda.", "vrsta": "ishod", "refs": ["R99"]},
        {"tekst": "Ishod se vidi iz beleške.", "vrsta": "ishod", "refs": [beleska]},
        {"tekst": "Šansa za uspeh je 70%.", "vrsta": "iskustvo", "refs": [slican]},
        {"tekst": "Prema članu 154 Zakona o obligacionim odnosima šteta se nadoknađuje.", "vrsta": "iskustvo", "refs": [slican]},
        {"tekst": "Sudija uvek traži tabelu.", "vrsta": "neproverena_beleska", "refs": [beleska]},
        {"tekst": "Kancelarija je vodila 12 takvih predmeta.", "vrsta": "iskustvo", "refs": [slican]},
        {"tekst": "Bez reference.", "vrsta": "iskustvo", "refs": []},
    ]}


def test_utemeljena_sinteza_odbacuje_neutemeljeno(svet):
    k, b, krediti, pozivi, odgovor = svet
    odgovor["v"] = None
    # prvo saznamo reference koje ruta šalje, pa sastavimo izlaz modela nad njima
    import services.law_brain_sinteza as S
    from datetime import date
    from services import law_brain as lb
    ctx = lb.kontekst_predmeta(b, "uid-A", PA_CUR, today=date.today())
    refs = S.reference_za_sintezu(ctx)
    prompt = "REFERENCE:\n" + "\n".join(f"{r['ref']} [{r['trust_class']}] {r['tekst']}" for r in refs)
    odgovor["v"] = _model_izlaz_iz(prompt)

    r = _post(k, PA_CUR)
    assert r.status_code == 200, r.text
    d = r.json()
    assert pozivi[0] == prompt, "model vidi tačno autorizovane reference"
    assert d["stanje"] == "OK" and len(d["tvrdnje"]) == 4 and d["odbaceno"] == 7
    assert set(d["razlozi_odbacivanja"]) == {"IZMISLJENA_ILI_NEDOSTAJUCA_REFERENCA", "VRSTA_NE_ODGOVARA_IZVORU",
                                             "ZABRANJEN_SADRZAJ", "BROJ_BEZ_IZVORA"}
    poznati = {json.dumps(x["source_ref"], sort_keys=True) for x in d["reference"]}
    for t in d["tvrdnje"]:
        assert t["source_refs"] and all(json.dumps(s, sort_keys=True) in poznati for s in t["source_refs"])
    ishod = next(t for t in d["tvrdnje"] if t["vrsta"] == "ishod")
    assert ishod["source_refs"] == [{"table": "outcome_log", "id": "o1"}]
    assert "%" not in json.dumps(d["tvrdnje"], ensure_ascii=False)
    assert "nije pravni savet" in d["napomena"].lower() and "model_pozvan" not in d
    assert len(krediti) == 1 and krediti[0][0][2] == "precedenti" and krediti[0][1]["predmet_id"] == PA_CUR


def test_ponavljanje_istim_kljucem_jedan_model_jedna_naplata(svet):
    k, _, krediti, pozivi, odgovor = svet
    odgovor["v"] = {"tvrdnje": []}
    kljuc = str(uuid.uuid4())
    r1, r2 = _post(k, PA_CUR, kljuc=kljuc), _post(k, PA_CUR, kljuc=kljuc)
    assert r1.status_code == r2.status_code == 200
    assert r1.content == r2.content
    assert len(pozivi) == 1 and len(krediti) == 1


def test_bez_osnova_bez_modela_i_kredita(svet):
    k, _, krediti, pozivi, _ = svet
    d = _post(k, PRAZAN).json()
    assert d["stanje"] == "NEMA_OSNOVA" and d["tvrdnje"] == []
    assert pozivi == [] and krediti == []


def test_pad_modela_503_bez_kredita(svet):
    k, _, krediti, pozivi, odgovor = svet
    odgovor["v"] = TimeoutError("spor model")
    r = _post(k, PA_CUR)
    assert r.status_code == 503   # telo 5xx maskira globalna granica otkrivanja (api.py) — namerno
    assert len(pozivi) == 1 and krediti == []


def test_neispravan_json_modela_je_pad(svet):
    k, _, krediti, _, odgovor = svet
    import services.law_brain_sinteza as S

    async def _los(prompt, pid):
        return "nije json"
    import pytest as _p
    mp = _p.MonkeyPatch()
    mp.setattr(S, "_pozovi_model_sinteze", _los)
    try:
        assert _post(k, PA_CUR).status_code == 503 and krediti == []
    finally:
        mp.undo()


def test_tudj_predmet_404_bez_modela(svet):
    k, _, krediti, pozivi, _ = svet
    assert _post(k, PA_CUR, ko="B").status_code == 404
    assert pozivi == [] and krediti == []


def test_kolega_ne_salje_tudje_podatke_modelu(svet):
    k, _, _, pozivi, odgovor = svet
    odgovor["v"] = {"tvrdnje": []}
    _post(k, PB_CUR, ko="B")
    sve = " ".join(pozivi)
    for zabranjeno in ("Petrović protiv", PA_OLD, "Tekst tužbe", "Pribaviti", "nagodba"):
        assert zabranjeno not in sve


def test_otvaranje_konteksta_ne_zove_model(svet):
    k, _, krediti, pozivi, _ = svet
    assert k.get(f"/api/law-brain/predmeti/{PA_CUR}", headers=f8.zaglavlje("A")).status_code == 200
    assert pozivi == [] and krediti == []


def test_proveri_sintezu_cista_funkcija():
    import services.law_brain_sinteza as S
    refs = [{"ref": "R1", "trust_class": "SOURCE_CASE_FACT", "tekst": "Raniji predmet 1: 3 svedoka", "source_ref": {"id": "x"}}]
    ok, odb, _ = S.proveri_sintezu({"tvrdnje": [{"tekst": "Bila su 3 svedoka.", "vrsta": "iskustvo", "refs": ["R1"]}]}, refs)
    assert len(ok) == 1 and odb == 0
    for los in ({"tvrdnje": "x"}, None, {"tvrdnje": [1, {"tekst": "a"}]}):
        assert S.proveri_sintezu(los, refs)[0] == []


def test_mesovite_reference_sa_izmisljenom_se_odbacuju():
    import services.law_brain_sinteza as S
    refs = [{"ref": "R1", "trust_class": "SOURCE_CASE_FACT", "tekst": "Raniji predmet 1", "source_ref": {"id": "x"}}]
    ok, odb, razlozi = S.proveri_sintezu({"tvrdnje": [{"tekst": "Isti tip.", "vrsta": "iskustvo", "refs": ["R1", "R7"]}]}, refs)
    assert ok == [] and odb == 1 and razlozi == ["IZMISLJENA_ILI_NEDOSTAJUCA_REFERENCA"]


def test_ishod_ponovo_otvorenog_predmeta_nije_referenca_ishoda():
    import services.law_brain_sinteza as S
    from services import law_brain as lb
    item = {"source_ref": {"table": "outcome_log", "id": "o9"}, "trust_class": lb.HUMAN_CONFIRMED_OUTCOME}
    ctx = {"similar_cases": {"stavke": [{"predmet_id": "p1", "zasto": "Sličan jer: isti tip.",
                                         "ishod": {"status": lb.OUTCOME_REOPENED, "ishod": "pobeda", "item": item}}]}}
    refs = S.reference_za_sintezu(ctx)
    assert [r["vrsta_izvora"] for r in refs] == ["slican_predmet"]
    assert not any(r["trust_class"] == lb.HUMAN_CONFIRMED_OUTCOME for r in refs)

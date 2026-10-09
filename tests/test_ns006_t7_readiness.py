"""NS006 Task 7 — rizik i spremnost bez pseudo-predviđanja (shared/case_readiness.py::pregled_spremnosti).

Dokazuje:
  • svaka dimenzija ima značenje, izvor i stanje; vrednosti potiču od kanonskih vlasnika
    (risk_engine, compute_case_readiness), ne od nove formule;
  • pao izvor → DEGRADED i `vrednost: None` — nikad 0 i nikad „spremno" (FAILED != EMPTY);
  • procesni rizik se NE računa iz delimičnih podataka;
  • nijedna reč o šansi/verovatnoći/predviđanju ishoda;
  • otvaranje ekrana ne piše u bazu i ne zove model — za razliku od postojećeg
    `GET /api/matter-intel/predmeti/{id}`, koji pri čitanju upisuje `predmet_health_log`
    (izmereno u istoj lažnoj bazi, kao kontrast).
"""
import json
from datetime import date, timedelta

import pytest

from shared.case_readiness import pregled_spremnosti
from tests.ns006_fake import pripremi, ocisti, zaglavlje

PA = "11111111-1111-4111-8111-11111111111a"
D1 = "d1000000-0000-4000-8000-000000000001"
DANAS = date.today()

DOKAZI = [
    {"id": "c1", "snaga": "jaka", "izvor_snage": "covek", "kategorija": "cinjenica"},
    {"id": "c2", "snaga": "srednja", "izvor_snage": "dc005", "kategorija": "cinjenica"},
    {"id": "c3", "snaga": "srednja", "izvor_snage": "podrazumevano", "kategorija": "cinjenica"},
]
DOKUMENTI = [{"id": D1, "tip_dokaza": "sudska_odluka", "naziv_fajla": "resenje.pdf"}]
ROCISTA = [{"id": "r1", "datum": (DANAS + timedelta(days=5)).isoformat(), "status": "zakazano", "sud": "OS Beograd"},
           {"id": "r2", "datum": (DANAS + timedelta(days=20)).isoformat(), "status": "zakazano", "sud": "OS Beograd"},
           {"id": "r3", "datum": (DANAS - timedelta(days=2)).isoformat(), "status": "zakazano", "sud": "OS Beograd"},
           {"id": "r4", "datum": (DANAS + timedelta(days=3)).isoformat(), "status": "otkazano", "sud": "OS Beograd"}]
AKCIJE = [{"id": "a1", "tip": "PRIBAVITI_DOKAZ", "prioritet": "high", "status": "open", "razlog": "Nedostaje ugovor", "dedupe_key": "k1"}]
KONTR = {"sazetak": {"aktivnih": 2, "kriticnih_aktivnih": 1, "za_pregled": 0, "aktivnih_bez_veze_na_tvrdnje": 0}}


def _p(**k):
    return pregled_spremnosti(tip_predmeta=k.get("tip", "radno"), dokazi=k.get("dokazi", DOKAZI),
                              dokumenti=k.get("dokumenti", DOKUMENTI), rocista=k.get("rocista", ROCISTA),
                              akcije=k.get("akcije", AKCIJE), kontradikcije=k.get("kontradikcije", KONTR),
                              genome_izracunat=k.get("genome", True), izvori=k.get("izvori"))


def _d(p):
    return {x["kljuc"]: x for x in p["dimenzije"]}


def test_dimenzije_iz_kanonskih_vlasnika():
    from services.risk_engine import calculate_procesni_rizik
    from shared.constants import EXPECTED_DOCS
    p = _p()
    d = _d(p)
    assert p["stanje"] == "OK" and p["degradirano"] == []
    assert d["pokrivenost_procene"]["vrednost"] == {"procenjeno": 2, "ukupno": 3, "status": "EVIDENCE_PARTIAL"}
    assert d["rocista"]["vrednost"] == {"u_narednih_30_dana": 2, "u_narednih_7_dana": 1, "propustena": 1}, "otkazano se ne broji"
    ocekivano = calculate_procesni_rizik(dokazi=DOKAZI, dokumenti=DOKUMENTI,
                                         rocista=[r for r in ROCISTA if r["status"] == "zakazano"],
                                         tip_predmeta="radno", expected_docs=EXPECTED_DOCS)
    assert d["procesni_rizik"]["vrednost"] == ocekivano["nivo"]
    assert d["nedostajuci_tipovi"]["vrednost"] == ocekivano["nedostajuci_dokazi"]
    assert d["kontradikcije"]["vrednost"]["kriticnih"] == 1
    assert d["operativna_spremnost"]["vrednost"] == "BLOCKED" and d["operativna_spremnost"]["otvorenih_akcija"] == 1
    for x in p["dimenzije"]:
        assert x["znacenje"] and x["izvor"] and x["klasa"] == "deterministic"


@pytest.mark.parametrize("izvor,pogodjene", [
    ("dokazi", {"pokrivenost_procene", "procesni_rizik", "nedostajuci_tipovi"}),
    ("dokumenti", {"nedostajuci_tipovi", "procesni_rizik"}),
    ("rocista", {"rocista", "procesni_rizik", "nedostajuci_tipovi"}),
    ("akcije", {"operativna_spremnost"}),
    ("kontradikcije", {"kontradikcije"}),
])
def test_pao_izvor_nije_nula_ni_spremno(izvor, pogodjene):
    p = _p(izvori={izvor: "GRESKA"})
    d = _d(p)
    assert p["stanje"] == "DEGRADED" and set(p["degradirano"]) == pogodjene, p["degradirano"]
    for k in pogodjene:
        assert d[k]["stanje"] == "DEGRADED" and d[k]["vrednost"] is None, k
    for k in set(d) - pogodjene:
        assert d[k]["stanje"] == "OK", k


def test_prazno_i_palo_se_razlikuju():
    prazno = _d(_p(dokazi=[], akcije=[]))
    palo = _d(_p(izvori={"dokazi": "GRESKA", "akcije": "GRESKA"}))
    assert prazno["pokrivenost_procene"]["vrednost"]["ukupno"] == 0 and palo["pokrivenost_procene"]["vrednost"] is None
    assert prazno["operativna_spremnost"]["vrednost"] == "READY" and palo["operativna_spremnost"]["vrednost"] is None


def test_bez_reci_o_ishodu():
    tekst = json.dumps(_p(), ensure_ascii=False).lower()
    for zabranjeno in ("verovatnoća", "šansa", "šanse", "predviđanje uspeha", "predviđen ishod", "probability", "chance"):
        assert zabranjeno not in tekst, zabranjeno


# ── ruta: čitanje ne piše, model se ne zove ───────────────────────────────────

def _tabele():
    return {"predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Petrović", "tip": "radno", "status": "aktivan",
                          "rizik": None, "opis": None, "case_dna": {}}],
            "predmet_dokumenti": [dict(d, predmet_id=PA, user_id="uid-A") for d in DOKUMENTI],
            "predmet_dokazi": [dict(d, predmet_id=PA, user_id="uid-A", tvrdnja="t " + d["id"], deleted_at=None) for d in DOKAZI],
            "rocista": [dict(r, predmet_id=PA, user_id="uid-A") for r in ROCISTA],
            "case_actions": [dict(a, predmet_id=PA) for a in AKCIJE],
            "predmet_genome_history": [], "predmet_issues": [], "predmet_health_log": [], "proactive_alerts": []}


@pytest.fixture
def okr(monkeypatch):
    k, baza = pripremi(monkeypatch, _tabele())
    pozivi_modela = []

    class _Zabranjeno:
        def __init__(self, *a, **kw):
            pozivi_modela.append("konstruktor")
            raise AssertionError("model se ne sme zvati pri čitanju")
    import openai
    monkeypatch.setattr(openai, "OpenAI", _Zabranjeno)
    monkeypatch.setattr(openai, "AsyncOpenAI", _Zabranjeno)
    yield k, baza, pozivi_modela
    ocisti()


def _pisanja(baza, od=0):
    return [z for z in baza.dnevnik[od:] if z["radnja"] in ("insert", "update", "upsert", "delete", "rpc")]


def test_v2_citanje_ne_pise_i_ne_zove_model(okr):
    k, baza, pozivi = okr
    r = k.get(f"/api/predmeti/{PA}/genome-v2", headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    d = _d(r.json()["spremnost"])
    assert d["operativna_spremnost"]["vrednost"] == "BLOCKED" and d["rocista"]["vrednost"]["propustena"] == 1
    assert _pisanja(baza) == [] and pozivi == []


def test_kontrast_matter_intel_get_pise(okr):
    """Postojeće ponašanje koje V2 NE koristi: legacy GET upisuje dnevni zapis zdravlja."""
    k, baza, _ = okr
    pre = len(baza.dnevnik)
    r = k.get(f"/api/matter-intel/predmeti/{PA}", headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    assert any(z["tabela"] == "predmet_health_log" for z in _pisanja(baza, pre))


def test_pao_izvor_u_ruti(okr):
    k, baza, _ = okr
    baza.greske["case_actions"] = RuntimeError("akcije nedostupne (test)")
    d = _d(k.get(f"/api/predmeti/{PA}/genome-v2", headers=zaglavlje("A")).json()["spremnost"])
    assert d["operativna_spremnost"]["stanje"] == "DEGRADED" and d["operativna_spremnost"]["vrednost"] is None

# -*- coding: utf-8 -*-
"""ONS001 Task 1 — RC1 BEZ migracije 136 i BEZ Render Cron-a (stanje produkcije 2026-10-10).

Simulacija produkcione šeme: `autonomy_cycles` i `autonomy_work_items` NE POSTOJE (PostgREST PGRST205), RPC
`autonomy_claim_work_item` ne postoji. Ista realistična baza (`ns006_realni_predmet`) se gleda dvaput — sa šemom
posle migracije i bez nje — i svaka V2 ruta mora da vrati ISTI odgovor (osim polja koje namerno kaže „nije
uključeno"). Autonomija: bez tajne nema ničega; sa tajnom a bez šeme nijedan agent se ne izvršava, ništa se ne
naplaćuje i ništa ne tvrdi da je rad pripremljen. Radni proizvod koji ne može da postoji → isti 404 kao nepostojeći.
"""
import json
import re

import pytest

import tests.ns007_fake as f7
from tests import ns006_realni_predmet as rp

TAJNA = "t" * 40
NEPOSTOJECI = "00000000-0000-4000-8000-0000000000ff"


def _pgrst205(t):
    return RuntimeError('{"code": "PGRST205", "message": "Could not find the table \'public.%s\' in the schema cache"}' % t)


def _bez_136(baza):
    for t in ("autonomy_cycles", "autonomy_work_items"):
        baza.tabele.pop(t, None)
        baza.greske[t] = _pgrst205(t)
    baza.greske["rpc:autonomy_claim_work_item"] = RuntimeError('{"code": "PGRST202", "message": "function not found"}')


@pytest.fixture
def svet(monkeypatch):
    import app.services.retrieve as rt
    monkeypatch.setattr(rt, "_ugradi_query", lambda *a, **kw: [0.0] * 8)    # spoljni servisi (embedding/Pinecone)
    monkeypatch.setattr(rt, "_pretraga_ns", lambda vec, ns, kk, filt: [])

    def _napravi(pre_migracije):
        f7.ocisti()
        k, baza = f7.pripremi(monkeypatch, rp.tabele())
        if pre_migracije:
            _bez_136(baza)
        return k, baza
    yield _napravi
    f7.ocisti()


A = f7.zaglavlje("A")
V2_RUTE = ["/api/workspace", "/api/predmeti", f"/api/predmeti/{rp.PA}", f"/api/predmeti/{rp.PA}/hronologija",
           f"/api/predmeti/{rp.PA}/genome-v2", f"/api/evidence/predmeti/{rp.PA}", f"/api/case-actions/predmeti/{rp.PA}",
           "/api/case-actions/worklist", f"/api/matter-intel/predmeti/{rp.PA}", "/api/rocista",
           f"/api/law-brain/predmeti/{rp.PA}", "/api/law-brain/znanje", "/api/law-brain/pretraga?q=otkaz",
           "/api/agent-notifications", "/api/autonomy/work-items"]
_SADA = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+\+00:00")   # vreme generisanja odgovora (podaci ga nemaju)


def _telo(x):
    return _SADA.sub("T", x.text)


def test_v2_rute_iste_sa_i_bez_migracije_136(svet):
    k, _ = svet(False)
    posle = {r: (x.status_code, _telo(x)) for r in V2_RUTE for x in [k.get(r, headers=A)]}
    assert {r: s for r, (s, _) in posle.items() if s != 200} == {}, "kontrola: svaka ruta radi i posle migracije"
    assert "Petrović" in posle["/api/predmeti"][1] and "Rešenje o otkazu" in posle[f"/api/evidence/predmeti/{rp.PA}"][1]
    k, _ = svet(True)
    pre = {r: (x.status_code, _telo(x)) for r in V2_RUTE for x in [k.get(r, headers=A)]}
    ocekivane = {"/api/workspace": ('"vindex_je_pripremio_stanje":"OK"', '"vindex_je_pripremio_stanje":"NIJE_UKLJUCENO"'),
                 "/api/autonomy/work-items": ('"stanje":"OK"', '"stanje":"NIJE_UKLJUCENO"')}
    for r in V2_RUTE:
        s_pre, t_pre = pre[r]
        s_posle, t_posle = posle[r]
        if r in ocekivane:
            t_posle = t_posle.replace(*ocekivane[r])
        assert (s_pre, t_pre) == (s_posle, t_posle), r
    w = json.loads(pre["/api/workspace"][1])
    assert w["provera_potpuna"] is True and w["degradirani_izvori"] == [] and w["vindex_je_pripremio"] == []


def test_zavrsni_status_predmeta_bez_migracije(svet):
    """NS008 Task 3 (PATCH u završni status) ne sme da zavisi od 136: status i trajni događaj se upisuju."""
    k, baza = svet(True)
    r = k.patch(f"/api/predmeti/{rp.PA}", json={"status": "zatvoren"}, headers=A)
    assert r.status_code == 200, r.text
    assert [p["status"] for p in baza.tabele["predmeti"] if p["id"] == rp.PA] == ["zatvoren"]
    assert [e for e in baza.tabele.get("events", []) if e.get("event_type") == "MatterBecameTerminal"]


@pytest.mark.parametrize("tajna_env,zaglavlje", [(None, None), (None, TAJNA), ("kratka", "kratka"), (TAJNA, None),
                                                 (TAJNA, "pogresna" * 5)])
def test_cron_bez_ispravne_tajne_isti_401_i_nista_se_ne_dira(svet, monkeypatch, tajna_env, zaglavlje):
    k, baza = svet(True)
    if tajna_env is None:
        monkeypatch.delenv("AUTONOMY_CRON_SECRET", raising=False)
    else:
        monkeypatch.setenv("AUTONOMY_CRON_SECRET", tajna_env)
    pre = len(baza.dnevnik)
    r = k.post("/api/cron/autonomy", headers={} if zaglavlje is None else {"X-Autonomy-Secret": zaglavlje})
    assert (r.status_code, r.json()) == (401, {"detail": "Neovlašćen pristup."})
    assert baza.dnevnik[pre:] == [], "neovlašćen poziv ne sme ni da čita bazu"


def test_cron_sa_tajnom_bez_seme_ne_izvrsava_nista(svet, monkeypatch):
    """Tajna podešena, a migracija ne: prozor ciklusa ne može da se zauzme → 503, nijedan agent (ni planer ni
    izvršilac), nijedan model, nijedna naplata, nijedan trag „pripremljeno"."""
    k, baza = svet(True)
    monkeypatch.setenv("AUTONOMY_CRON_SECRET", TAJNA)
    import workers.background_agents as ba
    pozivi = []

    def _zabranjeno(ime):
        async def _f(*a, **kw):
            pozivi.append(ime)
            raise AssertionError(ime)
        return _f
    for m in ba._agent_modules():
        for fn in ("planiraj", "izvrsi", "run"):
            if hasattr(m, fn):
                monkeypatch.setattr(m, fn, _zabranjeno(f"{m.__name__}.{fn}"))
    r = k.post("/api/cron/autonomy", headers={"X-Autonomy-Secret": TAJNA})
    assert r.status_code == 503 and r.json()["status"] == "CLAIM_UNAVAILABLE", r.text
    assert pozivi == []
    upisi = {z["tabela"] for z in baza.upisi("usage_events") + baza.upisi("audit_immutable") + baza.upisi("autonomy_work_items")}
    assert upisi == set(), upisi


def test_dnevni_cron_registar_nepromenjen():
    """Postojeći dnevni cron (`run_background_agents`) i posle RC1 pokreće SAMO dva legacy agenta preporuka;
    autonomni agent pripreme ročišta nema `run` i ne ulazi u njega."""
    import workers.background_agents as ba
    assert set(ba._agent_registry()) == {"court_portal_watcher", "precedents_radar"}


@pytest.mark.parametrize("metod,putanja", [("GET", "/api/autonomy/work-items/{id}"),
                                           ("POST", "/api/autonomy/work-items/{id}/accept"),
                                           ("POST", "/api/autonomy/work-items/{id}/reject"),
                                           ("POST", "/api/law-brain/rad/{id}/predlozi-znanje")])
def test_radni_proizvod_bez_seme_je_isti_404(svet, metod, putanja):
    """Pre migracije nijedan radni proizvod ne može da postoji: odgovor je isti kao za nepostojeći (posle migracije),
    a ne 500/503 i ne lažno „prihvaćeno"."""
    k, _ = svet(False)
    posle = k.request(metod, putanja.format(id=NEPOSTOJECI), headers=A)
    assert posle.status_code == 404, posle.text
    k, _ = svet(True)
    pre = k.request(metod, putanja.format(id=NEPOSTOJECI), headers=A)
    assert (pre.status_code, pre.text) == (posle.status_code, posle.text)


@pytest.mark.parametrize("metod,putanja,kod", [("GET", "/api/autonomy/work-items/{id}", 500),
                                               ("POST", "/api/law-brain/rad/{id}/predlozi-znanje", 503)])
def test_druga_greska_baze_nije_prikrivena_kao_404(svet, metod, putanja, kod):
    """Samo NEPOSTOJEĆA tabela znači „nije uključeno"; ispad baze ostaje vidljiva greška (ne lažni „ne postoji")."""
    k, baza = svet(False)
    baza.greske["autonomy_work_items"] = RuntimeError("connection reset by peer")
    assert k.request(metod, putanja.format(id=NEPOSTOJECI), headers=A).status_code == kod

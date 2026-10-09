"""NS007 Task 3 — uska ulazna tačka `POST /api/cron/autonomy` + kanonski ciklus u `workers/background_agents.py`.

Ruta: tajna nije podešena / prekratka / pogrešna / nedostaje → ISTI 401 (bajt-identičan); telo se ignoriše; isti sat
dvaput → drugi poziv SKIPPED i radnik se ne poziva; zauzimanje prozora nedostupno → 503 i radnik se ne poziva; pad
radnika → 500 + ciklus FAILED (vidljivo).
Radnik (lažan agent ubačen u JEDINI registar modula): plan → upis → zauzimanje → izvršenje → rezultat; isti okidač
dvaput → jedan posao; budžet iscrpljen / nepoznat / greška baze → izvršilac se NE poziva; `NeuspehPosla` → FAILED i
nema ponavljanja; prolazna greška → ostaje RUNNING do isteka zakupa; legacy registar (dnevni cron) je nepromenjen.
"""
import asyncio
import types

import pytest

import tests.ns007_fake as f7
from services import autonomy as au

UID = "aaaaaaaa-0000-4000-8000-00000000000a"
PID = "bbbbbbbb-0000-4000-8000-00000000000b"
TAJNA = "t" * 40


def _agent(kandidati=(), izvrsi=None, ponisteni=()):
    pozivi = []

    async def planiraj(supa):
        return {"kandidati": [dict(k) for k in kandidati], "ponisteni": list(ponisteni)}

    async def _izvrsi(supa, item):
        pozivi.append(item["id"])
        if izvrsi:
            return await izvrsi(item)
        return {"title": "Priprema", "summary": "Sažetak", "content": {"x": 1}, "source_refs": [],
                "quality_state": au.DETERMINISTICKO}
    m = types.SimpleNamespace(AGENT_TYPE="hearing_prep", WORK_TYPE="HEARING_PREP", planiraj=planiraj, izvrsi=_izvrsi)
    return m, pozivi


def _kand(kljuc="roc-1:v1", cost="FREE"):
    return {"user_id": UID, "predmet_id": PID, "agent_type": "hearing_prep", "work_type": "HEARING_PREP",
            "trigger_type": "ROCISTE", "trigger_ref": "roc-1", "dedupe_key": kljuc, "reason": "Ročište sutra",
            "cost_class": cost, "budget_key": f"solo:{UID}"}


@pytest.fixture
def svet(monkeypatch):
    k, baza = f7.pripremi(monkeypatch, {"predmeti": [{"id": PID, "user_id": UID, "status": "aktivan"}]})
    monkeypatch.setenv("AUTONOMY_CRON_SECRET", TAJNA)
    import workers.background_agents as ba
    stanje = {"agenti": []}
    legacy = ba._agent_modules()
    monkeypatch.setattr(ba, "_agent_modules", lambda: legacy + stanje["agenti"])
    yield k, baza, stanje, ba
    f7.ocisti()


def _okini(k, tajna=TAJNA, **kw):
    h = {} if tajna is None else {"X-Autonomy-Secret": tajna}
    return k.post("/api/cron/autonomy", headers=h, **kw)


def test_autentifikacija_isti_401_bez_odavanja(svet, monkeypatch):
    k, baza, _, _ = svet
    odgovori = [_okini(k, None), _okini(k, "pogresna"), _okini(k, TAJNA[:-1])]
    monkeypatch.delenv("AUTONOMY_CRON_SECRET")
    odgovori.append(_okini(k, TAJNA))
    monkeypatch.setenv("AUTONOMY_CRON_SECRET", "kratka")
    odgovori.append(_okini(k, "kratka"))
    assert all(r.status_code == 401 for r in odgovori)
    assert len({r.content for r in odgovori}) == 1, "odgovor ne sme da otkrije da li je raspoređivač podešen"
    assert baza.tabele.get("autonomy_cycles", []) == [], "neovlašćen poziv ne zauzima prozor"
    assert TAJNA not in "".join(r.text for r in odgovori)
    assert k.get("/api/cron/autonomy", headers={"X-Autonomy-Secret": TAJNA}).status_code == 405


def test_jedan_ciklus_po_prozoru_i_telo_se_ignorise(svet):
    k, baza, stanje, ba = svet
    agent, pozivi = _agent([_kand()])
    stanje["agenti"] = [agent]
    r1 = _okini(k, json={"user_id": "tudji", "predmet_id": "tudji", "prozor": "auto:2000-01-01T00"})
    assert r1.status_code == 200 and r1.json()["status"] == "COMPLETED", r1.text
    s = r1.json()["sazetak"]
    assert (s["planirano"], s["zauzeto"], s["spremno"]) == (1, 1, 1)
    r2 = _okini(k)
    assert r2.status_code == 200 and r2.json() == {"ok": True, "status": "SKIPPED", "razlog": "ALREADY_CLAIMED", "prozor": r1.json()["prozor"]}
    assert len(pozivi) == 1, "drugi poziv u istom satu ne pokreće radnika"
    c = baza.tabele["autonomy_cycles"]
    assert len(c) == 1 and c[0]["status"] == "COMPLETED" and c[0]["window_key"] == r1.json()["prozor"]
    assert all(p["user_id"] == UID for p in baza.tabele["autonomy_work_items"])


def test_zauzimanje_prozora_nedostupno_503_radnik_se_ne_poziva(svet):
    k, baza, stanje, _ = svet
    agent, pozivi = _agent([_kand()])
    stanje["agenti"] = [agent]
    baza.greske["autonomy_cycles"] = RuntimeError("baza nedostupna")
    r = _okini(k)
    assert r.status_code == 503 and r.json()["status"] == "CLAIM_UNAVAILABLE"
    assert pozivi == [] and baza.tabele.get("autonomy_work_items", []) == []


def test_pad_radnika_je_vidljiv(svet, monkeypatch):
    k, baza, _, ba = svet

    async def _pada(run_id):
        raise RuntimeError("radnik pao")
    import routers.autonomy as ra
    monkeypatch.setattr(ba, "run_autonomy_cycle", _pada)
    r = _okini(k)
    assert r.status_code == 500 and r.json()["status"] == "FAILED"
    c = baza.tabele["autonomy_cycles"][0]
    assert c["status"] == "FAILED" and c["safe_error_code"] == "CYCLE_EXCEPTION" and c["finished_at"]


def test_isti_okidac_jedan_posao_i_bez_ponovnog_izvrsavanja(svet):
    _, baza, stanje, ba = svet
    agent, pozivi = _agent([_kand()])
    stanje["agenti"] = [agent]
    asyncio.run(ba.run_autonomy_cycle("r1"))
    s2 = asyncio.run(ba.run_autonomy_cycle("r2"))
    assert len(baza.tabele["autonomy_work_items"]) == 1 and len(pozivi) == 1
    assert s2["duplikata"] == 1 and s2["zauzeto"] == 0


@pytest.mark.parametrize("scenario", ["iscrpljen", "nepoznat", "greska_baze"])
def test_bez_zauzimanja_nema_izvrsioca(svet, monkeypatch, scenario):
    _, baza, stanje, ba = svet
    agent, pozivi = _agent([_kand(cost="PAID")])
    stanje["agenti"] = [agent]
    if scenario == "iscrpljen":
        monkeypatch.setenv("AUTONOMY_BUDGET_PER_ORG_DAILY", "0")
    elif scenario == "nepoznat":
        monkeypatch.setenv("AUTONOMY_BUDGET_PER_ORG_DAILY", "nije-broj")
    else:
        baza.greske["rpc:autonomy_claim_work_item"] = RuntimeError("baza nedostupna")
    s = asyncio.run(ba.run_autonomy_cycle("r1"))
    assert pozivi == [], "izvršilac (model) se ne sme pozvati bez uspešnog zauzimanja"
    kljuc = {"iscrpljen": "budzet_iscrpljen", "nepoznat": "budzet_nepoznat", "greska_baze": "zauzimanje_greska"}[scenario]
    assert s[kljuc] == 1 and s["zauzeto"] == 0
    assert baza.tabele["autonomy_work_items"][0]["status"] == "QUEUED"


def test_neuspeh_je_konacan_a_prolazna_greska_ceka_zakup(svet):
    _, baza, stanje, ba = svet

    async def _posteno(item):
        raise au.NeuspehPosla("CONTEXT_UNAVAILABLE")
    agent, pozivi = _agent([_kand()], izvrsi=_posteno)
    stanje["agenti"] = [agent]
    asyncio.run(ba.run_autonomy_cycle("r1"))
    asyncio.run(ba.run_autonomy_cycle("r2"))
    r = baza.tabele["autonomy_work_items"][0]
    assert r["status"] == "FAILED" and r["safe_error_code"] == "CONTEXT_UNAVAILABLE" and len(pozivi) == 1

    async def _prolazno(item):
        raise TimeoutError("model nije odgovorio")
    agent2, pozivi2 = _agent([_kand("roc-2:v1") | {"trigger_ref": "roc-2"}], izvrsi=_prolazno)
    stanje["agenti"] = [agent2]
    s = asyncio.run(ba.run_autonomy_cycle("r3"))
    r2 = next(x for x in baza.tabele["autonomy_work_items"] if x["dedupe_key"] == "roc-2:v1")
    assert s["prolazno"] == 1 and r2["status"] == "RUNNING" and r2["lease_owner"]
    asyncio.run(ba.run_autonomy_cycle("r4"))
    assert len(pozivi2) == 1, "važeći zakup se ne preuzima u sledećem ciklusu"


def test_ponisten_okidac_zastareva_cekajuci_posao(svet):
    _, baza, stanje, ba = svet
    agent, _ = _agent([_kand()], izvrsi=None)
    stanje["agenti"] = [agent]
    asyncio.run(au.upisi_kandidata(baza, _kand("roc-1:v0")))
    agent2, pozivi = _agent([], ponisteni=[{"user_id": UID, "predmet_id": PID, "trigger_ref": "roc-1"}])
    stanje["agenti"] = [agent2]
    s = asyncio.run(ba.run_autonomy_cycle("r1"))
    assert s["zastarelo"] == 1 and pozivi == []
    assert baza.tabele["autonomy_work_items"][0]["status"] == "SUPERSEDED"


def test_legacy_registar_dnevnog_crona_nepromenjen(svet):
    _, _, stanje, ba = svet
    agent, _ = _agent()
    stanje["agenti"] = [agent]
    assert set(ba._agent_registry()) == {"court_portal_watcher", "precedents_radar"}, "agent trajnog rada ne ulazi u dnevni cron"
    assert set(ba._work_agents()) == {"HEARING_PREP", "PRECEDENT_IMPACT"}

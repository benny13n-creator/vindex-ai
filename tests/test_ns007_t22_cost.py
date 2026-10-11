"""NS007 Task 22 — adversarijalni trošak, mereno na granici OpenAI SDK-a (svaki stvarni poziv iz bilo kog koda).

Scenario: 100 aktivnih predmeta korisnika A sa Genome-om; 2 stvarna ročišta (sutra, prekosutra) u jednom predmetu;
1 proverena nova odluka; 3 preporuke sa izmišljenim odlukama. Očekivano: TAČNO 3 poziva modela (2 pripreme + 1 analiza
uticaja) — ne 100. Zatim: otvaranje V2 (genome-v2, promene, radnje), tabla, lista, detalj (3 osvežavanja), odluka,
ponovljen ciklus, novi prozor — 0 dodatnih poziva. Beleže se dimenzije troška (bez valute: cenovnik nije kanonski).
"""
import asyncio
import json
import re
import types
from datetime import date, datetime, timedelta, timezone

import pytest

import tests.ns007_fake as f7
from tests import ns006_realni_predmet as rp
from tests import ns007_korpus as kor

DANAS = date(2026, 10, 10)


class _Odgovor:
    def __init__(self, sadrzaj):
        self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=sadrzaj))]


def _sdk_brojac(dnevnik):
    """Zamena za `openai.AsyncOpenAI`: svaki `chat.completions.create` je jedan stvarni poziv provajdera."""
    class Klijent:
        def __init__(self, *a, **kw):
            dnevnik.append({"tip": "klijent", "max_retries": kw.get("max_retries")})

            async def create(**kw2):
                poruke = kw2["messages"]
                tekst = poruke[-1]["content"]
                dnevnik.append({"tip": "poziv", "model": kw2.get("model"), "max_tokens": kw2.get("max_tokens"),
                                "prompt_znakova": sum(len(p["content"]) for p in poruke), "modul": "ročište" if "ROČIŠTE" in tekst else "praksa"})
                if "SPORNA PITANJA PREDMETA:" in tekst:
                    k = re.findall(r"\[(ffff[^\]]+)\]", tekst)[0]
                    return _Odgovor(json.dumps({"klasifikacija": "u_prilog", "uticaj": [{"tekst": "Prednost dostavnici.", "refs": [k],
                                    "izvod": "dan uručenja utvrđen u dostavnici ima prednost nad datumom navedenim u samom rešenju"}],
                                    "pitanja": [], "razmotriti_argument": {"da": False}}, ensure_ascii=False))
                ids = re.findall(r"\[([0-9a-f-]{36})\]", tekst)
                return _Odgovor(json.dumps({"pitanja": [{"tekst": "Proveriti dostavnicu.", "refs": [ids[1]]}], "beleske": []}, ensure_ascii=False))
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    return Klijent


@pytest.fixture
def svet(monkeypatch):
    t = rp.tabele(danas=DANAS)
    t["rocista"] = [dict(t["rocista"][0], id="aaaa0001-0000-4000-8000-000000000001", datum=(DANAS + timedelta(days=1)).isoformat()),
                    dict(t["rocista"][0], id="aaaa0002-0000-4000-8000-000000000002", datum=DANAS.isoformat(), vreme="12:00")]
    for i in range(98):
        t["predmeti"].append({"id": f"{i:08d}-9999-4000-8000-000000000000", "user_id": "uid-A", "naziv": f"Predmet {i}",
                              "status": "aktivan", "case_dna": {"verzija": 1, "pravna_teorija": {"sustina_spora": f"spor {i}"}}})
    sada = datetime.now(timezone.utc).isoformat()
    t["agent_recommendations"] = [
        {"id": "dddd0001-0000-4000-8000-000000000001", "user_id": "uid-A", "predmet_id": rp.PA, "agent_type": "precedents_radar",
         "status": "pending", "created_at": sada, "payload": {"odnos": "podupire", "obrazlozenje": "x",
         "odluka": {"decision_number": kor.ODLUKA, "court": "Vrhovni sud", "date": "2023-05-10"}}}] + [
        {"id": f"dddd100{i}-0000-4000-8000-000000000001", "user_id": "uid-A", "predmet_id": f"{i:08d}-9999-4000-8000-000000000000",
         "agent_type": "precedents_radar", "status": "pending", "created_at": sada, "payload": {"odnos": "osporava", "obrazlozenje": "x",
         "odluka": {"decision_number": f"Rev {9000 + i}/2025", "court": "Vrhovni sud", "date": "2025-01-01"}}} for i in range(3)]
    t.setdefault("kancelarija_clanovi", [])
    k, baza = f7.pripremi(monkeypatch, t)
    kor.postavi(monkeypatch)
    from services.agent_tasks import hearing_prep as hp, precedents_radar as pr
    import workers.background_agents as ba
    monkeypatch.setattr(hp, "_danas", lambda: DANAS)
    monkeypatch.setattr(ba, "_agent_modules", lambda: [hp, pr])
    monkeypatch.setenv("AUTONOMY_BUDGET_PER_ORG_DAILY", "20")
    monkeypatch.setenv("AUTONOMY_CRON_SECRET", "t" * 40)
    dnevnik = []
    import openai
    monkeypatch.setattr(openai, "AsyncOpenAI", _sdk_brojac(dnevnik))

    class _ZabranjenSync:
        def __init__(self, *a, **kw):
            raise AssertionError("sinhroni OpenAI klijent se ne sme koristiti u autonomnom ciklusu")
    monkeypatch.setattr(openai, "OpenAI", _ZabranjenSync)
    yield k, baza, ba, dnevnik
    f7.ocisti()


def _pozivi(d):
    return [x for x in d if x["tip"] == "poziv"]


def test_100_predmeta_3_stvarna_okidaca_tacno_3_poziva(svet):
    k, baza, ba, d = svet
    s = asyncio.run(ba.run_autonomy_cycle("r1"))
    p = _pozivi(d)
    assert len(p) == 3 and sorted(x["modul"] for x in p) == ["praksa", "ročište", "ročište"], p
    assert s["spremno"] == 3 and s["planirano"] == 3
    assert all(x["max_retries"] == 0 for x in d if x["tip"] == "klijent"), "bez skrivenih SDK ponavljanja"
    assert all(x["model"] == "gpt-4o-mini" for x in p)
    # dimenzije troška ovog ciklusa (bez valute)
    dim = {"poziva": len(p), "max_izlaznih_tokena": sum(x["max_tokens"] for x in p), "prompt_znakova": sum(x["prompt_znakova"] for x in p)}
    assert dim["max_izlaznih_tokena"] == 1200 * 2 + 1400 and dim["prompt_znakova"] < 30000, dim
    print("DIMENZIJE_TROSKA", json.dumps(dim))


def test_citanje_pregled_i_ponavljanje_ne_trose(svet):
    k, baza, ba, d = svet
    asyncio.run(ba.run_autonomy_cycle("r1"))
    pre = len(_pozivi(d))
    h = f7.zaglavlje("A")
    for put in (f"/api/predmeti/{rp.PA}/genome-v2", f"/api/predmeti/{rp.PA}/genome-v2/promene", f"/api/case-actions/predmeti/{rp.PA}",
                "/api/workspace", "/api/autonomy/work-items", f"/api/autonomy/work-items?matter_id={rp.PA}"):
        assert k.get(put, headers=h).status_code == 200
    wid = baza.tabele["autonomy_work_items"][0]["id"]
    for _ in range(3):
        assert k.get(f"/api/autonomy/work-items/{wid}", headers=h).status_code == 200
    assert k.post(f"/api/autonomy/work-items/{wid}/accept", headers=h).status_code == 200
    asyncio.run(ba.run_autonomy_cycle("r2"))                                   # isti dan, isti okidači
    import routers.autonomy as ra
    r = k.post("/api/cron/autonomy", headers={"X-Autonomy-Secret": "t" * 40})   # nov prozor kroz pravu rutu
    assert r.json()["status"] == "COMPLETED"
    assert len(_pozivi(d)) == pre, "čitanje, pregled, odluka i ponovljeni ciklusi: 0 novih poziva"

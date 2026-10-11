"""NS007 Task 5 — budžet autonomnog rada zatvoren pri grešci (nivo radnika; nivo SQL-a pod konkurencijom je u
test_ns007_t1_t2_contract_pg: 10 istovremenih, budžet 3 → tačno 3).

  • 10 plaćenih poslova iste organizacije, budžet 3 → izvršilac (model) pozvan TAČNO 3 puta, 7 ostaje QUEUED;
  • sledeći ciklus istog dana ne pokreće nijedan novi plaćen posao; drugog dana kreće nova trojka;
  • budžet je po organizaciji i zajednički za sve vrste plaćenog rada;
  • besplatan (deterministički) rad ne troši budžet i radi i kad je budžet 0;
  • baza budžeta nedostupna → 0 poziva modela;
  • upis u usage_events padne POSLE završenog rada → proizvod ostaje READY_FOR_REVIEW, ne pokreće se ponovo, a
    neuspeh se broji (ne tvrdi se da je zabeleženo).
"""
import asyncio
import types

import pytest

import tests.ns007_fake as f7
from services import autonomy as au

A, B = "aaaaaaaa-0000-4000-8000-00000000000a", "bbbbbbbb-0000-4000-8000-00000000000b"
PA, PB = "aaaaaaaa-1111-4000-8000-00000000000a", "bbbbbbbb-1111-4000-8000-00000000000b"


def _k(uid, pid, i, work_type="HEARING_PREP", cost="PAID", org=None):
    return {"user_id": uid, "predmet_id": pid, "agent_type": "hearing_prep" if work_type == "HEARING_PREP" else "precedents_radar",
            "work_type": work_type, "trigger_type": "ROCISTE" if work_type == "HEARING_PREP" else "PRECEDENT",
            "trigger_ref": f"t{i}", "dedupe_key": f"{work_type}:{i}", "reason": "razlog", "cost_class": cost,
            "budget_key": org or f"solo:{uid}"}


def _agent(work_type, kandidati, pozivi):
    async def planiraj(supa):
        return {"kandidati": list(kandidati)}

    async def izvrsi(supa, item):
        pozivi.append((work_type, item["id"]))
        return {"title": "T", "summary": "S", "content": {"x": 1}, "source_refs": [], "quality_state": au.AI_PRIPREMLJENO}
    return types.SimpleNamespace(AGENT_TYPE=work_type.lower(), WORK_TYPE=work_type, planiraj=planiraj, izvrsi=izvrsi)


@pytest.fixture
def svet(monkeypatch):
    _, baza = f7.pripremi(monkeypatch, {"predmeti": [{"id": PA, "user_id": A}, {"id": PB, "user_id": B}]})
    import workers.background_agents as ba
    stanje = {"agenti": []}
    monkeypatch.setattr(ba, "_agent_modules", lambda: stanje["agenti"])
    monkeypatch.setenv("AUTONOMY_BUDGET_PER_ORG_DAILY", "3")
    yield baza, stanje, ba, monkeypatch
    f7.ocisti()


def test_10_placenih_budzet_3_tacno_3_poziva_modela(svet):
    baza, stanje, ba, _ = svet
    pozivi = []
    stanje["agenti"] = [_agent("HEARING_PREP", [_k(A, PA, i) for i in range(10)], pozivi)]
    s = asyncio.run(ba.run_autonomy_cycle("r1"))
    assert len(pozivi) == 3 and s["spremno"] == 3 and s["budzet_iscrpljen"] == 7
    st = [r["status"] for r in baza.tabele["autonomy_work_items"]]
    assert st.count("READY_FOR_REVIEW") == 3 and st.count("QUEUED") == 7
    asyncio.run(ba.run_autonomy_cycle("r2"))
    assert len(pozivi) == 3, "isti dan: budžet je potrošen, nijedan nov plaćen posao"
    # sledeći dan: rezervacije od juče se ne računaju
    for r in baza.tabele["autonomy_work_items"]:
        if r.get("reserved_day"):
            r["reserved_day"] = "2000-01-01"
    asyncio.run(ba.run_autonomy_cycle("r3"))
    assert len(pozivi) == 6


def test_budzet_po_organizaciji_zajednicki_za_sve_vrste(svet):
    baza, stanje, ba, _ = svet
    pozivi = []
    org = "kancelarija:K1"
    stanje["agenti"] = [_agent("HEARING_PREP", [_k(A, PA, i, org=org) for i in range(2)], pozivi),
                        _agent("PRECEDENT_IMPACT", [_k(B, PB, i, "PRECEDENT_IMPACT", org=org) for i in range(2)], pozivi),
                        ]
    asyncio.run(ba.run_autonomy_cycle("r1"))
    assert len(pozivi) == 3, "dva člana iste kancelarije, dve vrste rada — jedan budžet"


def test_besplatan_rad_ne_trosi_i_radi_pri_budzetu_0(svet):
    baza, stanje, ba, mp = svet
    mp.setenv("AUTONOMY_BUDGET_PER_ORG_DAILY", "0")
    pozivi = []
    stanje["agenti"] = [_agent("CASE_CHANGE_BRIEF", [_k(A, PA, i, "CASE_CHANGE_BRIEF", cost="FREE") | {"agent_type": "case_evolution", "trigger_type": "GENOME_VERSION"} for i in range(4)], pozivi)]
    s = asyncio.run(ba.run_autonomy_cycle("r1"))
    assert len(pozivi) == 4 and s["spremno"] == 4
    assert all(r["budget_units"] == 0 for r in baza.tabele["autonomy_work_items"])
    assert not [z for z in baza.dnevnik if z["tabela"] == "usage_events"], "besplatan rad se ne knjiži kao trošak"


def test_baza_budzeta_nedostupna_nula_poziva_modela(svet):
    baza, stanje, ba, _ = svet
    pozivi = []
    stanje["agenti"] = [_agent("HEARING_PREP", [_k(A, PA, i) for i in range(5)], pozivi)]
    baza.greske["rpc:autonomy_claim_work_item"] = RuntimeError("baza nedostupna")
    s = asyncio.run(ba.run_autonomy_cycle("r1"))
    assert pozivi == [] and s["zauzimanje_greska"] == 5
    assert all(r["status"] == "QUEUED" and r["budget_units"] == 0 for r in baza.tabele["autonomy_work_items"])


def test_neuspeo_upis_upotrebe_posle_rada_ne_ponavlja_rad(svet):
    baza, stanje, ba, _ = svet
    pozivi = []
    stanje["agenti"] = [_agent("HEARING_PREP", [_k(A, PA, 0)], pozivi)]
    baza.greske["usage_events"] = RuntimeError("usage_events nedostupan")
    s = asyncio.run(ba.run_autonomy_cycle("r1"))
    assert s["spremno"] == 1 and s["upotreba_nije_zabelezena"] == 1
    r = baza.tabele["autonomy_work_items"][0]
    assert r["status"] == "READY_FOR_REVIEW" and r["budget_units"] == 1, "rezervacija ostaje izvor istine o trošku"
    del baza.greske["usage_events"]
    asyncio.run(ba.run_autonomy_cycle("r2"))
    assert len(pozivi) == 1, "gotov rad se ne pokreće ponovo zbog neuspelog računovodstva"


def test_uspesan_placen_rad_je_proknjizen_bez_sadrzaja(svet):
    baza, stanje, ba, _ = svet
    pozivi = []
    stanje["agenti"] = [_agent("HEARING_PREP", [_k(A, PA, 0)], pozivi)]
    asyncio.run(ba.run_autonomy_cycle("r1"))
    upisi = baza.tabele.get("usage_events", [])
    assert len(upisi) == 1 and upisi[0]["feature"] == "autonomy" and upisi[0]["action"] == "HEARING_PREP"
    assert set(upisi[0]["meta"]) == {"work_item_id", "run_id", "attempt"}

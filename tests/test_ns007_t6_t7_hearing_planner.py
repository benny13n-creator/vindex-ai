"""NS007 Task 6–7 — deterministički planer HEARING_PREP (0 poziva modela).

Posao nastaje SAMO za: ročište `zakazano` u prozoru (danas/sutra, podesivo), predmet istog korisnika, nije završen,
nije u brisanju, ima Genome. Ključ veže korisnika, ročište, verziju ročišta i verziju Genome-a. Promena ročišta →
nov posao, stari SUPERSEDED; otkazano/odloženo/zatvoren predmet → posao koji čeka se poništava i NE izvršava.
100 aktivnih predmeta sa 2 ročišta → tačno 2 kandidata. Greška čitanja predmeta ≠ „nema posla".
"""
import asyncio
import types
from datetime import date, timedelta

import pytest

import tests.ns007_fake as f7
from services import autonomy as au
from services.agent_tasks import hearing_prep as hp

A, B = "aaaaaaaa-0000-4000-8000-00000000000a", "bbbbbbbb-0000-4000-8000-00000000000b"
DANAS = date(2026, 10, 10)


def _pid(i):
    return f"{i:08d}-1111-4000-8000-000000000000"


def _rid(i):
    return f"{i:08d}-2222-4000-8000-000000000000"


def _predmet(i, uid=A, status="aktivan", verzija=3, **dod):
    return {"id": _pid(i), "user_id": uid, "status": status, "naziv": f"Predmet {i}",
            "case_dna": {"verzija": verzija} if verzija else {}, "brisanje_zapoceto": None, **dod}


def _roc(i, pid_i, uid=A, dani=1, status="zakazano", vreme="09:30:00", sud="Osnovni sud u Beogradu"):
    return {"id": _rid(i), "predmet_id": _pid(pid_i), "user_id": uid, "datum": (DANAS + timedelta(days=dani)).isoformat(),
            "vreme": vreme, "sud": sud, "sudnica": "12", "status": status}


@pytest.fixture
def svet(monkeypatch):
    stanje = {"tabele": None}

    def napravi(predmeti, rocista, **dod):
        t = {"predmeti": predmeti, "rocista": rocista, "case_actions": [], "kancelarija_clanovi": [], **dod}
        _, baza = f7.pripremi(monkeypatch, t)
        stanje["baza"] = baza
        return baza
    monkeypatch.setattr(hp, "_danas", lambda: DANAS)
    yield napravi, monkeypatch
    f7.ocisti()


def _plan(baza):
    return asyncio.run(hp.planiraj(baza))


def test_rociste_sutra_jedan_kandidat_sa_razlogom_i_vezom(svet):
    napravi, _ = svet
    baza = napravi([_predmet(1)], [_roc(1, 1)],
                   case_actions=[{"id": "ca-1", "predmet_id": _pid(1), "tip": "PRIPREMITI_PODNESAK", "status": "open",
                                  "dokaz": {"rociste_id": _rid(1)}}])
    p = _plan(baza)
    assert len(p["kandidati"]) == 1 and p["ponisteni"] == []
    k = p["kandidati"][0]
    assert k["trigger_ref"] == _rid(1) and k["source_version"] == 3 and k["cost_class"] == "PAID"
    assert k["dedupe_key"] == f"HEARING_PREP:{_rid(1)}:{hp.verzija_rocista(_roc(1, 1))}:g3"
    assert "sutra" in k["reason"] and "11.10.2026." in k["reason"] and "09:30" in k["reason"] and "Osnovni sud u Beogradu" in k["reason"]
    assert k["case_action_id"] == "ca-1" and k["budget_key"] == f"solo:{A}"


def test_kancelarija_je_kljuc_budzeta(svet):
    napravi, _ = svet
    baza = napravi([_predmet(1)], [_roc(1, 1)], kancelarija_clanovi=[
        {"clan_id": A, "kancelarija_id": "K1", "status": "ACTIVE"}, {"clan_id": B, "kancelarija_id": "K1", "status": "ACTIVE"}])
    assert _plan(baza)["kandidati"][0]["budget_key"] == "kancelarija:K1"


@pytest.mark.parametrize("predmet,roc,razlog", [
    (_predmet(1), _roc(1, 1, dani=2), None),      # van prozora se ni ne čita (filter u upitu)
    (_predmet(1), _roc(1, 1, dani=-1), None),
    (_predmet(1, status="zatvoren"), _roc(1, 1), "PREDMET_ZAVRSEN"),
    (_predmet(1, status="odbijen"), _roc(1, 1), "PREDMET_ZAVRSEN"),
    (_predmet(1, status="arhiviran"), _roc(1, 1), "PREDMET_ZAVRSEN"),
    (_predmet(1, brisanje_zapoceto="2026-10-09T10:00:00+00:00"), _roc(1, 1), "PREDMET_U_BRISANJU"),
    (_predmet(1, verzija=None), _roc(1, 1), "BEZ_GENOMA"),
    (_predmet(1, uid=B), _roc(1, 1, uid=A), "VLASNIK_SE_NE_POKLAPA"),
])
def test_nepodoban_nema_posla(svet, predmet, roc, razlog):
    napravi, _ = svet
    p = _plan(napravi([predmet], [roc]))
    assert p["kandidati"] == [] and p["preskoceno"] == ({razlog: 1} if razlog else {}), p["preskoceno"]


@pytest.mark.parametrize("status", ["odlozeno", "otkazano", "odrzano"])
def test_rociste_koje_nije_zakazano_nema_posla(svet, status):
    napravi, _ = svet
    assert _plan(napravi([_predmet(1)], [_roc(1, 1, status=status)]))["kandidati"] == []


def test_prozor_je_eksplicitan_i_podesiv(svet):
    napravi, mp = svet
    baza = napravi([_predmet(1)], [_roc(1, 1, dani=0), _roc(2, 1, dani=3)])
    assert [k["trigger_ref"] for k in _plan(baza)["kandidati"]] == [_rid(1)]
    assert "danas" in _plan(baza)["kandidati"][0]["reason"]
    mp.setenv("AUTONOMY_HEARING_WINDOW_DAYS", "3")
    assert len(_plan(baza)["kandidati"]) == 2
    mp.setenv("AUTONOMY_HEARING_WINDOW_DAYS", "nije-broj")
    assert len(_plan(baza)["kandidati"]) == 1


def test_100_aktivnih_predmeta_2_rocista_tacno_2_kandidata_bez_modela(svet):
    napravi, mp = svet
    pozivi = []
    import openai

    class _Zabranjeno:
        def __init__(self, *a, **k):
            pozivi.append(1)
            raise AssertionError("planer ne sme da zove model")
    mp.setattr(openai, "OpenAI", _Zabranjeno)
    mp.setattr(openai, "AsyncOpenAI", _Zabranjeno)
    baza = napravi([_predmet(i) for i in range(100)], [_roc(1, 5), _roc(2, 50, dani=0)])
    p = _plan(baza)
    assert len(p["kandidati"]) == 2 and pozivi == []


def _ciklus(baza, mp, pozivi):
    import workers.background_agents as ba

    async def izvrsi(supa, item):
        pozivi.append(item["dedupe_key"])
        return {"title": "T", "summary": "S", "content": {}, "source_refs": [], "quality_state": au.AI_PRIPREMLJENO}
    mp.setattr(hp, "izvrsi", izvrsi, raising=False)
    mp.setattr(ba, "_agent_modules", lambda: [hp])
    return asyncio.run(ba.run_autonomy_cycle("r"))


def test_promena_rocista_nov_posao_stari_zastareo(svet):
    napravi, mp = svet
    baza = napravi([_predmet(1)], [_roc(1, 1, vreme="09:30:00")])
    pozivi = []
    _ciklus(baza, mp, pozivi)
    baza.tabele["rocista"][0]["vreme"] = "13:00:00"          # sud pomerio ročište
    s = _ciklus(baza, mp, pozivi)
    st = {r["dedupe_key"]: r["status"] for r in baza.tabele["autonomy_work_items"]}
    assert len(st) == 2 and s["zastarelo"] == 1
    assert sorted(st.values()) == ["READY_FOR_REVIEW", "SUPERSEDED"]
    assert len(pozivi) == 2


def test_nova_verzija_genoma_nova_priprema(svet):
    napravi, mp = svet
    baza = napravi([_predmet(1, verzija=3)], [_roc(1, 1)])
    pozivi = []
    _ciklus(baza, mp, pozivi)
    _ciklus(baza, mp, pozivi)
    assert len(pozivi) == 1, "ista verzija → ista priprema, bez novog izvršenja"
    baza.tabele["predmeti"][0]["case_dna"]["verzija"] = 4
    _ciklus(baza, mp, pozivi)
    assert len(pozivi) == 2 and pozivi[-1].endswith(":g4")


@pytest.mark.parametrize("promena", ["otkazano", "odlozeno", "zatvoren", "obrisano"])
def test_ponisteno_rociste_posao_koji_ceka_se_ne_izvrsava(svet, promena):
    napravi, mp = svet
    baza = napravi([_predmet(1)], [_roc(1, 1)])
    p = _plan(baza)
    asyncio.run(au.upisi_kandidata(baza, p["kandidati"][0]))           # posao je u redu, još nije izvršen
    if promena == "zatvoren":
        baza.tabele["predmeti"][0]["status"] = "zatvoren"
    elif promena == "obrisano":
        baza.tabele["rocista"].clear()
    else:
        baza.tabele["rocista"][0]["status"] = promena
    pozivi = []
    s = _ciklus(baza, mp, pozivi)
    assert pozivi == [] and s["zastarelo"] >= 1
    assert baza.tabele["autonomy_work_items"][0]["status"] == "SUPERSEDED"


def test_kolona_tombstone_nedostaje_bezbedna_grana(svet):
    napravi, _ = svet
    baza = napravi([{k: v for k, v in _predmet(1).items() if k != "brisanje_zapoceto"}], [_roc(1, 1)])
    baza.nepostojece_kolone["predmeti"] = {"brisanje_zapoceto"}
    assert len(_plan(baza)["kandidati"]) == 1


def test_greska_citanja_predmeta_nije_nema_posla(svet):
    napravi, _ = svet
    baza = napravi([_predmet(1)], [_roc(1, 1)])
    baza.greske["predmeti"] = RuntimeError("baza nedostupna")
    with pytest.raises(RuntimeError):
        _plan(baza)


def test_rociste_pomereno_van_prozora_ponistava_posao_koji_ceka(svet):
    """Status ostaje `zakazano`, ali je sud pomerio ročište za 30 dana: priprema „za sutra" više ne važi."""
    napravi, mp = svet
    baza = napravi([_predmet(1)], [_roc(1, 1)])
    asyncio.run(au.upisi_kandidata(baza, _plan(baza)["kandidati"][0]))
    baza.tabele["rocista"][0]["datum"] = (DANAS + timedelta(days=30)).isoformat()
    pozivi = []
    _ciklus(baza, mp, pozivi)
    assert pozivi == [] and baza.tabele["autonomy_work_items"][0]["status"] == "SUPERSEDED"


def test_jednokratna_greska_koja_nije_kolona_ne_skida_tombstone_filter(svet):
    napravi, _ = svet
    baza = napravi([_predmet(1, brisanje_zapoceto="2026-10-09T10:00:00+00:00")], [_roc(1, 1)])
    pravi = baza.table
    stanje = {"palo": False}

    def table(ime):
        u = pravi(ime)
        if ime == "predmeti" and not stanje["palo"]:
            stari_select = u.select

            def select(kol, *a, **k):
                if "brisanje_zapoceto" in kol:
                    stanje["palo"] = True
                    raise RuntimeError('{"code": "57014", "message": "canceling statement due to statement timeout"}')
                return stari_select(kol, *a, **k)
            u.select = select
        return u
    baza.table = table
    with pytest.raises(RuntimeError):
        _plan(baza)


def test_rociste_odlozeno_pa_vraceno_priprema_se_obnavlja_bez_novog_poziva(svet):
    """Ročište greškom označeno kao odloženo (priprema → SUPERSEDED), pa vraćeno na zakazano: isti ključ (iste
    ulazne verzije) → stari proizvod se OBNAVLJA na pregled, bez novog poziva modela. Ranije: nijedna priprema."""
    napravi, mp = svet
    baza = napravi([_predmet(1)], [_roc(1, 1)])
    pozivi = []
    _ciklus(baza, mp, pozivi)
    assert baza.tabele["autonomy_work_items"][0]["status"] == "READY_FOR_REVIEW"
    baza.tabele["rocista"][0]["status"] = "odlozeno"
    _ciklus(baza, mp, pozivi)
    assert baza.tabele["autonomy_work_items"][0]["status"] == "SUPERSEDED"
    baza.tabele["rocista"][0]["status"] = "zakazano"
    s = _ciklus(baza, mp, pozivi)
    st = [r["status"] for r in baza.tabele["autonomy_work_items"]]
    assert st == ["READY_FOR_REVIEW"] and len(pozivi) == 1 and s["obnovljeno"] == 1, (st, len(pozivi))


def test_zastareo_bez_proizvoda_se_vraca_u_red(svet):
    napravi, mp = svet
    baza = napravi([_predmet(1)], [_roc(1, 1)])
    asyncio.run(au.upisi_kandidata(baza, _plan(baza)["kandidati"][0]))     # samo u redu, bez izvršenja
    baza.tabele["rocista"][0]["status"] = "odlozeno"
    _ciklus(baza, mp, [])
    assert baza.tabele["autonomy_work_items"][0]["status"] == "SUPERSEDED"
    baza.tabele["rocista"][0]["status"] = "zakazano"
    pozivi = []
    s = _ciklus(baza, mp, pozivi)
    assert baza.tabele["autonomy_work_items"][0]["status"] == "READY_FOR_REVIEW" and len(pozivi) == 1
    assert s["obnovljeno"] == 1, "obnova se broji (i beleži u reviziji), nije tiha"


def test_odbijena_priprema_se_ne_obnavlja(svet):
    """Advokat je ODBIO pripremu: isti okidač sutra ne vraća je na pregled (odluka advokata se poštuje)."""
    napravi, mp = svet
    baza = napravi([_predmet(1)], [_roc(1, 1)])
    pozivi = []
    _ciklus(baza, mp, pozivi)
    r = baza.tabele["autonomy_work_items"][0]
    r.update(status="REJECTED", resolved_at="2026-10-10T08:00:00+00:00", reviewed_by="uid-A")
    s = _ciklus(baza, mp, pozivi)
    assert r["status"] == "REJECTED" and s["obnovljeno"] == 0 and len(pozivi) == 1

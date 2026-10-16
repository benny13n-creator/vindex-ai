# -*- coding: utf-8 -*-
"""QA-01 — nepotvrđen AI datum NIJE potvrđen kritičan rok.

B1  Genome pisac više ne upisuje `kritičan` u kodu.
B2  Prošao datum nepotvrđenog predloga: „Datum je prošao — proveriti status.“,
    nije izvršen, nije prekoračen rok, nije obrisan ni prepisan.
B3  Case Action Rule 6: negativan broj dana ne daje `critical`.
B4  Legacy brojači hitnih rokova (`/api/predmeti/dashboard`, workspace,
    `/api/portfolio`, `/portfolio/dashboard`, mesečni izveštaj, Copilot plan)
    broje AI predlog samo uz ljudsku potvrdu iz lanca odluka.
B5  Izvršna kapija `sme_pokrenuti_obavezu` nije menjana — ovde se samo meri.

Sintetički podaci, bez stvarnih predmeta. Model se ne poziva.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared import rokovi as R
from shared.rok_potvrda import STANJE_ODBIJEN, STANJE_POTVRDJEN
from tests.ns005_harness import ocisti, pripremi, zaglavlje

# ── fiksni sat za čiste funkcije ────────────────────────────────────────────
DANAS = date(2026, 3, 20)


class _Danas(date):
    @classmethod
    def today(cls):
        return cls(DANAS.year, DANAS.month, DANAS.day)


def _d(dani: int) -> str:
    """Datum relativno prema STVARNOM danas (za rute koje sat uvoze lokalno)."""
    return (date.today() + timedelta(days=dani)).isoformat()


def _red(rid, uid="uid-A", pid="pred-A", dani=2, vaznost="kritičan", izvor=R.IZVOR_AI_AUTONOMOUS,
         akter="Genome (AI)", vrsta=R.VRSTA_ROK, dogadjaj=None):
    return {"id": rid, "user_id": uid, "predmet_id": pid, "dogadjaj": dogadjaj or f"Rok {rid}",
            "datum": _d(dani), "datum_iso": _d(dani), "vaznost": vaznost, "izvor": izvor,
            "akter": akter, "vrsta": vrsta}


def _baza():
    return {
        "predmeti": [{"id": "pred-A", "user_id": "uid-A", "naziv": "Predmet A", "status": "aktivan", "tip": "parnica"},
                     {"id": "pred-B", "user_id": "uid-B", "naziv": "Predmet B", "status": "aktivan", "tip": "parnica"}],
        "predmet_hronologija": [
            _red("ai-buduci", dani=2),                                       # 1
            _red("ai-prosao", dani=-10),                                     # 2
            _red("ai-potvrdjen", dani=2, dogadjaj="Rok za odgovor"),         # 3
            _red("ai-potvrdjen-prosao", dani=-5),                            # 4
            _red("ai-odbijen", dani=2),                                      # 5
            _red("dogadjaj-ai", dani=-30, vrsta=R.VRSTA_DOGADJAJ),           # 6
            _red("covek-kritican", dani=3, izvor=R.IZVOR_HUMAN_DIRECT, akter="Advokat", vrsta=None),
            _red("legacy-genome", dani=4, izvor=None, vrsta=None),           # pre migracije 127
            _red("B-tudji", uid="uid-B", pid="pred-B", dani=2, dogadjaj="TAJNI rok B"),   # 10
        ],
        "rocista": [], "predmet_dokazi": [], "predmet_dokumenti": [], "case_actions": [],
        "predmet_istorija": [], "predmet_beleske": [], "predmet_klijenti": [], "predmet_komentari": [],
        "billing_entries": [], "fakture": [],
        "audit_immutable": [
            {"seq": 1, "action": "rok_potvrdjen", "resource_type": "rok", "resource_id": "ai-potvrdjen", "user_id": "uid-A"},
            {"seq": 2, "action": "rok_potvrdjen", "resource_type": "rok", "resource_id": "ai-potvrdjen-prosao", "user_id": "uid-A"},
            {"seq": 3, "action": "rok_odbijen", "resource_type": "rok", "resource_id": "ai-odbijen", "user_id": "uid-A"},
            # Odluka korisnika B o SVOM redu ne sme ništa da znači za A.
            {"seq": 4, "action": "rok_potvrdjen", "resource_type": "rok", "resource_id": "B-tudji", "user_id": "uid-B"},
        ],
    }


@pytest.fixture
def http(monkeypatch):
    R._resetuj_sondu()
    import shared.audit_immutable as audit
    pravi = audit.log_action
    k, b = pripremi(monkeypatch, _baza())
    monkeypatch.setattr(audit, "log_action", pravi)
    # Bez mreže: workspace inače zove model (Cockpit) i pretragu prakse.
    import openai
    import shared.permissions as perm
    import shared.usage as us

    class _BezMreze:
        def __init__(self, *a, **k):
            raise RuntimeError("mreža je zabranjena u testu")

    async def _politika(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

    async def _nista(*a, **kw):
        return None
    monkeypatch.setattr(openai, "AsyncOpenAI", _BezMreze)
    monkeypatch.setattr(openai, "OpenAI", _BezMreze)
    monkeypatch.setattr(perm, "get_policy", _politika)
    monkeypatch.setattr(perm, "_check_dependencies", _nista)
    monkeypatch.setattr(us.UsageService, "consume", staticmethod(_nista))
    try:
        import app.services.retrieve as ret

        def _bez(*a, **k):
            raise RuntimeError("mreža je zabranjena u testu")
        monkeypatch.setattr(ret, "_ugradi_query", _bez)
    except Exception:
        pass
    yield k, b
    R._resetuj_sondu()
    ocisti()


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# Čiste funkcije, fiksni sat
# ═══════════════════════════════════════════════════════════════════════════

def test_B3_prioritet_kandidata_fiksni_brojevi():
    import services.event_bus  # noqa: F401  (case_evolution se uvozi preko event_bus-a)
    from services.case_evolution import _priority_by_days, _priority_rok_kandidat
    assert [_priority_rok_kandidat(d) for d in (-400, -30, -1)] == ["medium"] * 3
    assert [_priority_rok_kandidat(d) for d in (0, 3, 4, 7, 8, 30)] == [
        "critical", "critical", "high", "high", "medium", "medium"]
    # Rule 1 (ročišta) i ostala pravila nisu dirana.
    assert _priority_by_days(-10) == "critical"


@pytest.mark.parametrize("red,mapa,dostupne,ocekivano", [
    ({"id": "a", "vaznost": "kritičan", "izvor": "AI_AUTONOMOUS"}, {}, True, False),          # 1/2 nepotvrđen
    ({"id": "a", "vaznost": "kritičan", "izvor": "AI_ASSISTED"}, {}, True, False),
    ({"id": "a", "vaznost": "kritičan", "izvor": "AI_AUTONOMOUS"}, {"a": STANJE_POTVRDJEN}, True, True),   # 3
    ({"id": "a", "vaznost": "kritičan", "izvor": "AI_AUTONOMOUS"}, {"a": STANJE_POTVRDJEN}, False, False),
    ({"id": "a", "vaznost": "kritičan", "izvor": "AI_AUTONOMOUS"}, {"a": STANJE_ODBIJEN}, True, False),    # 5
    ({"id": "a", "vaznost": "kritičan", "izvor": "HUMAN_DIRECT"}, {"a": STANJE_ODBIJEN}, True, False),
    ({"id": "a", "vaznost": "kritičan", "izvor": "HUMAN_DIRECT"}, {}, True, True),           # ljudski unos ostaje
    ({"id": "a", "vaznost": "kritičan", "izvor": "HUMAN_DIRECT"}, {}, False, True),
    ({"id": "a", "vaznost": "kritičan", "izvor": None, "akter": "Genome (AI)"}, {}, True, False),   # legacy
    ({"id": "a", "vaznost": "kritičan", "izvor": None, "akter": "Pipeline (AI)"}, {}, True, False),
    ({"id": "a", "vaznost": "važan", "izvor": "HUMAN_DIRECT"}, {}, True, False),
    ({"vaznost": "kritičan", "izvor": "AI_AUTONOMOUS"}, {}, True, False),                       # bez id
    (None, {}, True, False),
])
def test_B4_je_hitan_za_prikaz_tabela(red, mapa, dostupne, ocekivano):
    assert R.je_hitan_za_prikaz(red, mapa, odluke_dostupne=dostupne) is ocekivano


def test_B4_odluke_za_hitne_pad_lanca_nije_prazno(monkeypatch):
    import shared.rok_potvrda as rp

    def _pada(*a, **k):
        raise RuntimeError("lanac nedostupan")
    monkeypatch.setattr(rp, "procitaj_lanac", _pada)
    mapa, ok = R.odluke_za_hitne([{"id": "x", "vaznost": "kritičan"}])
    assert (mapa, ok) == ({}, False)
    # Bez kritičnih redova nema ni čitanja ni pada.
    assert R.odluke_za_hitne([{"id": "x", "vaznost": "važan"}]) == ({}, True)


# ═══════════════════════════════════════════════════════════════════════════
# B1 — Genome pisac (stvarna funkcija, memorijska baza)
# ═══════════════════════════════════════════════════════════════════════════

def _genome_sync(b, rokovi):
    from routers.case_dna import _sync_rokovi_to_hronologija
    return asyncio.run(_sync_rokovi_to_hronologija(b, "pred-A", "uid-A", {"rokovi_kriticni": rokovi}))


def test_B1_genome_upisuje_vazan_i_prosli_datum_ostaje_kandidat(http):
    _, b = http
    pre = len(b.tabele["predmet_hronologija"])
    n = _genome_sync(b, [
        {"naziv": "Rok za izjašnjenje", "datum": _d(5), "opis": "iz zapisnika", "status": "aktivan"},
        {"naziv": "Isporuka robe", "datum": _d(-40), "opis": "ugovorni rok", "status": "aktivan"},
    ])
    novi = b.tabele["predmet_hronologija"][pre:]
    assert n == 2 and len(novi) == 2
    for red in novi:
        assert red["vaznost"] == "važan"                       # B1
        assert red["izvor"] == R.IZVOR_AI_AUTONOMOUS
        assert red["vrsta"] == R.VRSTA_ROK and "stanje" not in red   # kandidat, ne izvršen (B2)
        assert R.stanje_zapisa({**red, "id": "nov"}, {}) == R.STANJE_KANDIDAT
        assert not R.sme_pokrenuti_obavezu({**red, "id": "nov"}, set())   # B5
        assert not R.je_hitan_za_prikaz({**red, "id": "nov"}, {})


def test_9_isti_rok_drugim_recima_meri_duplikat(http):
    """MERENJE, ne ispravka: dedup je po tačnom tekstu (`dogadjaj`, `datum_iso`).
    Isti rok preformulisan daje DVA kandidata. Novo pravilo identiteta nije
    uvedeno (traži odobrenje osnivača)."""
    _, b = http
    pre = len(b.tabele["predmet_hronologija"])
    _genome_sync(b, [{"naziv": "Rok za žalbu", "datum": _d(9), "opis": "15 dana od prijema", "status": "aktivan"}])
    _genome_sync(b, [{"naziv": "Rok za žalbu", "datum": _d(9), "opis": "petnaest dana od dostavljanja", "status": "aktivan"}])
    _genome_sync(b, [{"naziv": "Rok za žalbu", "datum": _d(9), "opis": "15 dana od prijema", "status": "aktivan"}])
    novi = b.tabele["predmet_hronologija"][pre:]
    assert len(novi) == 2                         # isti tekst: 1; drugi tekst: +1
    assert all(r["vaznost"] == "važan" for r in novi)


# ═══════════════════════════════════════════════════════════════════════════
# B4 — legacy prikazi (STVARNI api.app)
# ═══════════════════════════════════════════════════════════════════════════

A = None


def _get(k, url, tok="A"):
    r = k.get(url, headers=zaglavlje(tok))
    assert r.status_code == 200, (url, r.status_code, r.text[:400])
    return r.json()


def test_B4_dashboard_broji_samo_potvrdjene_i_ljudske(http):
    k, _ = http
    j = _get(k, "/api/predmeti/dashboard")
    a = next(p for p in j["predmeti"] if p["id"] == "pred-A")
    # ai-potvrdjen (3) + covek-kritican; NE ai-buduci (1), ai-odbijen (5), legacy-genome
    assert a["urgentni_rokovi_count"] == 2
    assert j["statistike"]["hitni_rokovi"] == 2
    assert j["statistike"]["odluke_o_rokovima_dostupne"] is True
    assert "TAJNI" not in str(j) and all(p["id"] != "pred-B" for p in j["predmeti"])   # 10
    # Nepotvrđen predlog nije sakriven: i dalje je „sledeći rok“ predmeta.
    assert a["sledeci_rok"]["datum_iso"] == _d(2)


def test_B4_workspace_urgentni_i_hronologija(http):
    k, _ = http
    j = _get(k, "/api/predmeti/pred-A/workspace")
    urg = {h["id"] for h in j["rokovi"]["urgentni"]}
    assert urg == {"ai-potvrdjen", "covek-kritican"}
    assert j["statistike"]["urgentni_rokovi"] == 2 and j["rokovi"]["odluke_dostupne"] is True
    sve = {h["id"] for h in j["rokovi"]["hronologija"]}
    # Svi redovi A ostaju vidljivi u hronologiji — ništa obrisano, ništa sakriveno (B2/B4).
    assert {"ai-buduci", "ai-prosao", "ai-odbijen", "dogadjaj-ai", "legacy-genome"} <= sve
    assert "B-tudji" not in sve


def test_B4_portfolio_legacy_i_v2(http):
    k, _ = http
    j = _get(k, "/api/portfolio")
    hp = {x["id"]: x["urgentni_rokovi"] for x in j["hitni_predmeti"]}
    assert hp.get("pred-A") == 2
    j2 = _get(k, "/portfolio/dashboard")
    assert {r["dogadjaj"] for r in j2["hitni_rokovi"]} == {"Rok za odgovor", "Rok covek-kritican"}
    assert j2["odluke_dostupne"] is True
    # Nepotvrđen predlog ostaje u listi rokova 7 dana (vidljiv), samo nije „kritičan“.
    assert "Rok ai-buduci" in {r["dogadjaj"] for r in j2["rokovi_7_dana"]}
    assert "TAJNI" not in str(j2)


def test_2_4_mesecni_prekoraceni_ne_broji_prosli_predlog(http):
    k, _ = http
    j = _get(k, "/billing/report/mesecni")
    # 4: potvrđen prošao rok jeste prekoračen; 2: nepotvrđen prošao predlog nije;
    # 6: AI događaj (vrsta=dogadjaj) nije.
    assert j["prekoraceni_rokovi"] == 1


def test_7_pad_lanca_odluka(http):
    k, b = http
    b.greske["audit_immutable"] = Exception("lanac nedostupan")
    j = _get(k, "/api/predmeti/dashboard")
    a = next(p for p in j["predmeti"] if p["id"] == "pred-A")
    # Ljudski rok ostaje hitan; AI predlozi (i potvrđen — stanje se ne zna) se ne broje,
    # a odgovor to KAŽE umesto da tvrdi „nema hitnih rokova“.
    assert a["urgentni_rokovi_count"] == 1
    assert j["statistike"]["odluke_o_rokovima_dostupne"] is False
    w = _get(k, "/api/predmeti/pred-A/workspace")
    assert w["rokovi"]["odluke_dostupne"] is False
    assert {h["id"] for h in w["rokovi"]["urgentni"]} == {"covek-kritican"}
    p2 = _get(k, "/portfolio/dashboard")
    assert p2["odluke_dostupne"] is False
    r = k.get("/billing/report/mesecni", headers=zaglavlje("A"))
    assert r.status_code == 503 and "odluke o rokovima" in r.text


def test_7_pad_hronologije_nije_prazno(http):
    k, b = http
    b.greske["predmet_hronologija"] = Exception("hronologija nedostupna")
    assert k.get("/portfolio/dashboard", headers=zaglavlje("A")).status_code == 503
    assert k.get("/billing/report/mesecni", headers=zaglavlje("A")).status_code == 503


def test_10_tudja_potvrda_ne_vazi(http):
    k, b = http
    # Korisnik B pokušava da potvrdi A-ov nepotvrđen predlog postojećim tokom odluke.
    pre = len(b.tabele["audit_immutable"])
    r = k.post("/api/rokovi/ai-buduci/potvrdi", headers=zaglavlje("B"))
    assert r.status_code == 404, r.text
    assert len(b.tabele["audit_immutable"]) == pre
    jb = _get(k, "/api/predmeti/dashboard", tok="B")
    assert all(p["id"] == "pred-B" for p in jb["predmeti"])
    assert "Predmet A" not in str(jb)
    # B-ov red je kod B potvrđen i kritičan → hitan kod B, nikad kod A.
    assert jb["statistike"]["hitni_rokovi"] == 1
    ja = _get(k, "/api/predmeti/dashboard")
    assert ja["statistike"]["hitni_rokovi"] == 2


# ═══════════════════════════════════════════════════════════════════════════
# B2/B3 — Rule 6 kroz stvarni event bus (solo tok)
# ═══════════════════════════════════════════════════════════════════════════

from tests.test_osb002_solo_tok import _do_kraja_dogadjaja, _novi_predmet, solo  # noqa: E402,F401


def _rule6(k, b, redovi, odluke=()):
    from services.event_bus import EventType, emit_durable
    _, pid = _novi_predmet(k, b)
    for r in redovi:
        b.tabele["predmet_hronologija"].append({**r, "predmet_id": pid, "user_id": "uid-A"})
    for seq, (rid, akcija) in enumerate(odluke, start=100):
        b.tabele.setdefault("audit_immutable", []).append(
            {"seq": seq, "action": akcija, "resource_type": "rok", "resource_id": rid, "user_id": "uid-A"})
    snimak = [dict(x) for x in b.tabele["predmet_hronologija"] if x["predmet_id"] == pid]
    asyncio.run(emit_durable(EventType.MANUAL_CORRECTION_APPLIED, "uid-A", pid, {"trigger": "qa01"}))
    _do_kraja_dogadjaja(b)
    akc = {a["dokaz"]["hronologija_id"]: a for a in b.tabele["case_actions"]
           if a["predmet_id"] == pid and a["status"] == "open"
           and (a.get("dokaz") or {}).get("izvor") == "predmet_hronologija"}
    posle = [dict(x) for x in b.tabele["predmet_hronologija"] if x["predmet_id"] == pid]
    return akc, snimak, posle


def test_rule6_svih_deset_slucajeva(solo):
    R._resetuj_sondu()
    k, b = solo
    redovi = [
        _red("r-buduci-2", dani=2),                                     # 1 (blizu)
        _red("r-buduci-12", dani=12, vaznost="važan"),                  # 1 (dalje, nov Genome oblik)
        _red("r-prosao", dani=-10),                                     # 2
        _red("r-potvrdjen", dani=2),                                    # 3
        _red("r-potvrdjen-prosao", dani=-5),                            # 4
        _red("r-odbijen", dani=2),                                      # 5
        _red("r-dogadjaj", dani=-30, vrsta=R.VRSTA_DOGADJAJ),           # 6
        _red("r-isti-dan-1", dani=6, dogadjaj="Rok za žalbu"),          # 8
        _red("r-isti-dan-2", dani=6, dogadjaj="Rok za predlog dokaza"),  # 8
    ]
    akc, snimak, posle = _rule6(k, b, redovi, odluke=[
        ("r-potvrdjen", "rok_potvrdjen"), ("r-potvrdjen-prosao", "rok_potvrdjen"), ("r-odbijen", "rok_odbijen")])
    # 1: predstojeći kandidat ostaje vidljiv, prioritet po danima.
    assert akc["r-buduci-2"]["prioritet"] == "critical"
    assert akc["r-buduci-12"]["prioritet"] == "medium"
    # 2: prošao kandidat — vidljiv, NIJE critical, poštena poruka.
    assert akc["r-prosao"]["prioritet"] == "medium"
    assert "Datum je prošao — proveriti status." in akc["r-prosao"]["razlog"]
    assert "čeka vašu potvrdu" in akc["r-prosao"]["razlog"]
    # 3/4/5: odluka postoji → nije akcija pregleda (postojeće ponašanje).
    assert not {"r-potvrdjen", "r-potvrdjen-prosao", "r-odbijen"} & set(akc)
    # 6: događaj nije rok.
    assert "r-dogadjaj" not in akc
    # 8: dve obaveze istog datuma su dve akcije.
    assert {"r-isti-dan-1", "r-isti-dan-2"} <= set(akc)
    assert akc["r-isti-dan-1"]["dedupe_key"] != akc["r-isti-dan-2"]["dedupe_key"]
    # Istorijski zapisi nisu prepisani (B2): hronologija identična pre i posle.
    assert snimak == posle
    # 5: nijedan nepotvrđen ili odbijen red nije izvršiv.
    potvrdjeni = {"r-potvrdjen", "r-potvrdjen-prosao"}
    assert {r["id"] for r in R.filtriraj_izvrsive(posle, potvrdjeni)} == potvrdjeni
    R._resetuj_sondu()


def test_rule6_postojeca_critical_akcija_se_osvezava(solo):
    """Akcija otvorena PRE ispravke (prošao datum, `critical`) dobija novi prioritet pri
    sledećem usklađivanju — isti dedupe_key, bez nove akcije i bez brisanja."""
    R._resetuj_sondu()
    k, b = solo
    from services.case_evolution import _stable_key
    _, pid = _novi_predmet(k, b)
    b.tabele["predmet_hronologija"].append({**_red("r-star", dani=-3), "predmet_id": pid, "user_id": "uid-A"})
    b.tabele["case_actions"].append({
        "id": "ca-star", "predmet_id": pid, "user_id": "uid-A", "status": "open", "tip": "PLANIRATI_ROKOVE",
        "prioritet": "critical", "razlog": "Rok iz dokumenta čeka vašu potvrdu: Rok r-star (prošao pre 3 dan(a))",
        "dedupe_key": _stable_key("rok_kandidat", "r-star"), "rok": _d(-3),
        "dokaz": {"izvor": "predmet_hronologija", "hronologija_id": "r-star"}})
    from services.event_bus import EventType, emit_durable
    asyncio.run(emit_durable(EventType.MANUAL_CORRECTION_APPLIED, "uid-A", pid, {"trigger": "qa01"}))
    _do_kraja_dogadjaja(b)
    otv = [a for a in b.tabele["case_actions"] if a["predmet_id"] == pid and a["status"] == "open"
           and a.get("dedupe_key") == _stable_key("rok_kandidat", "r-star")]
    assert len(otv) == 1 and otv[0]["id"] == "ca-star"
    assert otv[0]["prioritet"] == "medium" and "proveriti status" in otv[0]["razlog"]
    R._resetuj_sondu()


# ═══════════════════════════════════════════════════════════════════════════
# B4 — Copilot plan: kontekst modelu i `kriticni_rokovi` u odgovoru
# ═══════════════════════════════════════════════════════════════════════════

def _copilot_plan(monkeypatch, b):
    import types

    import openai
    import routers.copilot as cp
    poruke = []

    class _Klijent:
        def __init__(self, *a, **k):
            pass

    async def _model(oai, **kw):
        poruke.append(kw["messages"][1]["content"])
        return types.SimpleNamespace(choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content='{"cilj": "x", "faze": []}'))])
    monkeypatch.setattr(openai, "AsyncOpenAI", _Klijent)
    monkeypatch.setattr(cp, "_pozovi_gpt4o_mini", _model)
    b.tabele["predmeti"][0]["case_dna"] = {}
    rez = asyncio.run(cp._handle_plan_predmeta("Napravi plan", "pred-A", "uid-A"))
    return rez, poruke


def test_B4_copilot_plan_ne_naziva_predlog_kriticnim(http, monkeypatch):
    _, b = http
    rez, poruke = _copilot_plan(monkeypatch, b)
    assert rez["tip"] == "PLAN" and len(poruke) == 1
    hitni_red = next(l for l in poruke[0].splitlines() if l.startswith("Hitni rokovi:"))
    assert "Rok za odgovor" in hitni_red and "Rok covek-kritican" in hitni_red
    assert "ai-buduci" not in hitni_red and "ai-odbijen" not in hitni_red
    kriticni = {r["naziv"]: r["posledica_propustanja"] for r in rez["kriticni_rokovi"]}
    assert kriticni.get("Rok ai-buduci") == ""                    # vidljiv, ali ne „Kritičan rok“
    assert kriticni.get("Rok za odgovor", "").startswith("Kritičan rok")
    assert "TAJNI" not in poruke[0]


def test_7_copilot_pad_hronologije_nije_nema(http, monkeypatch):
    _, b = http
    b.greske["predmet_hronologija"] = Exception("hronologija nedostupna")
    rez, poruke = _copilot_plan(monkeypatch, b)
    assert "Hitni rokovi: nepoznato (rokovi nisu pročitani)" in poruke[0]

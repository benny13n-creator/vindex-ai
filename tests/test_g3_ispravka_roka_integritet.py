# -*- coding: utf-8 -*-
"""G3 — ispravka AI predloga roka (POST /api/rokovi/{id}/ispravi): posle ispravke postoji TAČNO JEDNA operativna
(potvrđena) obaveza — advokatov rok — a AI predlog ostaje vidljiv u istoriji kao ODBIJEN, sa vezom na ispravku.
Stvarne rute i stvaran lanac odluka (shared/rok_potvrda + audit_immutable u bazi u memoriji)."""
from datetime import date, timedelta

from tests.test_n4_ispravka_roka import _predlog, _stanje, lanac  # noqa: F401
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401


def _d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def _kandidati(k, glava=A):
    r = k.get(f"/api/rokovi/kandidati?od={_d(-1)}&do={_d(60)}", headers=glava)
    assert r.status_code == 200, r.text
    j = r.json()
    return {x["id"]: x for x in (j.get("rokovi") or j.get("kandidati") or j.get("stavke") or [])}


def test_posle_ispravke_jedna_operativna_obaveza_a_predlog_vidljiv_kao_odbijen(lanac):
    k, b = lanac
    _predlog(b)
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    assert r.status_code == 200, r.text
    nov = r.json()["rok_id"]
    vidi = _kandidati(k)                                           # osvežen prikaz posle ispravke
    assert set(vidi) >= {nov, "rok-ai"}
    assert vidi[nov]["stanje_odluke"] == "CONFIRMED" and vidi["rok-ai"]["stanje_odluke"] == "REJECTED"
    potvrdjeni = [i for i, x in vidi.items() if x["stanje_odluke"] == "CONFIRMED"]
    assert potvrdjeni == [nov]                                     # nema protivrečnog potvrđenog stanja
    ai = next(x for x in b.tabele["predmet_hronologija"] if x["id"] == "rok-ai")
    assert ai["datum_iso"] == _d(10) and ai["izvor"] == "AI_AUTONOMOUS"     # predlog nije prepisan


def test_ispravka_opisa_i_datuma_zadrzava_izvorni_dokument(lanac):
    k, b = lanac
    _predlog(b)
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(11), "dogadjaj": "Rok za odgovor na tužbu"}, headers=A)
    assert r.status_code == 200, r.text
    nov = next(x for x in b.tabele["predmet_hronologija"] if x["id"] == r.json()["rok_id"])
    assert nov["dogadjaj"] == "Rok za odgovor na tužbu" and nov["dokument_id"] == "dok-1" and nov["izvor"] == "HUMAN_DIRECT"


def test_ponovljena_ispravka_posle_uspeha_409_bez_novog_reda(lanac):
    k, b = lanac
    _predlog(b)
    assert k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A).status_code == 200
    pre = len(b.tabele["predmet_hronologija"])
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(13)}, headers=A)
    assert r.status_code == 409 and len(b.tabele["predmet_hronologija"]) == pre


def test_odbijen_predlog_se_ne_ispravlja(lanac):
    k, b = lanac
    _predlog(b)
    assert k.post("/api/rokovi/rok-ai/odbij", json={}, headers=A).status_code == 200
    pre = len(b.tabele["predmet_hronologija"])
    assert k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A).status_code == 409
    assert len(b.tabele["predmet_hronologija"]) == pre


def test_obrisan_predlog_404_bez_upisa(lanac):
    k, b = lanac
    _predlog(b)
    b.tabele["predmet_hronologija"] = [x for x in b.tabele["predmet_hronologija"] if x["id"] != "rok-ai"]
    assert k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A).status_code == 404
    assert b.tabele["predmet_hronologija"] == []


def test_tudji_korisnik_ne_moze_da_ispravi_ni_da_sazna_postojanje(lanac):
    k, b = lanac
    _predlog(b)
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=B)
    assert r.status_code == 404 and _stanje(k, "rok-ai") == "UNCONFIRMED"
    assert len(b.tabele["predmet_hronologija"]) == 1


def test_istovremena_ispravka_istog_roka_drugi_dobija_409(lanac):
    """Brana je u procesu (`_ISPRAVKA_U_TOKU`); produkcija radi sa jednim procesom (/health: workers=1)."""
    import routers.rok_odluka as ro
    k, b = lanac
    _predlog(b)
    ro._ISPRAVKA_U_TOKU.add(("uid-A", "rok-ai"))                  # prvi zahtev je u toku
    try:
        r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    finally:
        ro._ISPRAVKA_U_TOKU.discard(("uid-A", "rok-ai"))
    assert r.status_code == 409 and len(b.tabele["predmet_hronologija"]) == 1 and _stanje(k, "rok-ai") == "UNCONFIRMED"


# ── S1 (revizija C3): predlog se ODBIJA PRE potvrde ispravke. Delimičan neuspeh u BILO KOM koraku nikad ne ostavlja
#    dve potvrđene obaveze — ni posle ručne potvrde ispravke advokatovom napomenom, ni posle druge ispravke ──

def _potvrdjeni(k, b):
    from shared.rok_potvrda import odluke
    ids = [x["id"] for x in b.tabele["predmet_hronologija"]]
    return sorted(i for i, s in odluke(ids, True).items() if s == "CONFIRMED")


def _novi(b):
    return [x["id"] for x in b.tabele["predmet_hronologija"] if x["id"] != "rok-ai"]


def test_pad_odbijanja_nista_ne_potvrdjuje_a_ponovna_ispravka_zavrsava(lanac):
    k, b = lanac
    _predlog(b)
    b.lanac_puca = "rok_odbijen"
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    b.lanac_puca = None
    assert r.status_code == 503 and _potvrdjeni(k, b) == [] and _stanje(k, "rok-ai") == "UNCONFIRMED"
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    assert r.status_code == 200, r.text
    assert _potvrdjeni(k, b) == [r.json()["rok_id"]] and _stanje(k, "rok-ai") == "REJECTED" and len(_novi(b)) == 1


def _pad_potvrde(k, b):
    _predlog(b)
    b.lanac_puca = "rok_potvrdjen"
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    b.lanac_puca = None
    assert r.status_code == 503 and _potvrdjeni(k, b) == [] and _stanje(k, "rok-ai") == "REJECTED"
    (nov,) = _novi(b)
    return nov


def test_pad_potvrde_rucna_potvrda_sopstvenom_napomenom_pa_potvrda_predloga_409(lanac):
    """Tačno sekvenca iz revizije C3 (ranije: dve potvrđene obaveze)."""
    k, b = lanac
    nov = _pad_potvrde(k, b)
    assert k.post(f"/api/rokovi/{nov}/potvrdi", json={"napomena": "proverio sam"}, headers=A).status_code == 200
    assert k.post("/api/rokovi/rok-ai/potvrdi", json={}, headers=A).status_code == 409
    assert k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(14)}, headers=A).status_code == 409
    assert _potvrdjeni(k, b) == [nov] and _novi(b) == [nov]


def test_pad_potvrde_ponovna_ispravka_dovrsava_bez_novog_reda(lanac):
    k, b = lanac
    nov = _pad_potvrde(k, b)
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(14)}, headers=A)       # drugi datum: ne potvrđuje tuđi
    assert r.status_code == 409 and _d(12) in r.json()["detail"] and _potvrdjeni(k, b) == []
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)       # isti datum: dovršava
    assert r.status_code == 200 and r.json()["rok_id"] == nov and r.json()["datum_iso"] == _d(12), r.text
    assert _potvrdjeni(k, b) == [nov] and _novi(b) == [nov]


def test_pad_odbijanja_ne_pravi_nijedan_red_pa_potvrda_korekcije_i_predloga_nije_moguca_dvaput(lanac):
    """Revizija S1-E #4: ranije je posle pada odbijanja ostajao nepovezan nepotvrđen red ispravke uz nepotvrđen predlog."""
    k, b = lanac
    _predlog(b)
    b.lanac_puca = "rok_odbijen"
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    b.lanac_puca = None
    assert r.status_code == 503 and _novi(b) == [] and _stanje(k, "rok-ai") == "UNCONFIRMED"
    assert k.post("/api/rokovi/rok-ai/potvrdi", json={}, headers=A).status_code == 200
    assert _potvrdjeni(k, b) == ["rok-ai"]


def test_pad_upisa_posle_odbijanja_ponovna_ispravka_upisuje_i_potvrdjuje(lanac, monkeypatch):
    import shared.rok_ispravka as RI
    import routers.rok_odluka as RO
    k, b = lanac
    _predlog(b)
    monkeypatch.setattr(RO, "upisi_ispravljen_rok", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("upis pao")))
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    assert r.status_code == 503 and _stanje(k, "rok-ai") == "REJECTED" and _novi(b) == []
    monkeypatch.setattr(RO, "upisi_ispravljen_rok", RI.upisi_ispravljen_rok)
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    assert r.status_code == 200, r.text
    assert _novi(b) == [r.json()["rok_id"]] and _potvrdjeni(k, b) == [r.json()["rok_id"]]


def test_napomena_odbijanja_ne_ovlascuje_potvrdu_reda_drugog_predmeta(lanac):
    """Revizija S1-E #5: napomena rute `odbij` je slobodan tekst — „Ispravljen — tačan rok je <X>“ ne sme da potvrdi X."""
    k, b = lanac
    _predlog(b)
    _predlog(b, rid="tudji", pid="p-2")
    assert k.post("/api/rokovi/rok-ai/odbij", json={"napomena": "Ispravljen — tačan rok je tudji"}, headers=A).status_code == 200
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    assert r.status_code == 409 and "nema ispravku" in r.json()["detail"] and _stanje(k, "tudji") == "UNCONFIRMED"


def test_stanje_iz_starog_redosleda_potvrdjena_ispravka_uz_nepotvrdjen_predlog(lanac):
    """Zapisi napravljeni pre S1 (ispravka potvrđena, odbijanje predloga palo): i dalje ni druga ispravka ni potvrda."""
    import asyncio
    from shared.rok_ispravka import AKTER_ISPRAVKE, napomena_ispravke
    from shared.rok_potvrda import potvrdi_rok
    k, b = lanac
    _predlog(b)
    b.tabele["predmet_hronologija"].append({"id": "isp-1", "predmet_id": "p-1", "user_id": "uid-A", "dogadjaj": "Rok za tužbu",
                                            "datum": _d(12), "datum_iso": _d(12), "vaznost": "važan", "akter": AKTER_ISPRAVKE,
                                            "izvor": "HUMAN_DIRECT", "vrsta": "rok"})
    assert asyncio.run(potvrdi_rok("isp-1", "uid-A", napomena=napomena_ispravke("rok-ai")))
    assert k.post("/api/rokovi/rok-ai/potvrdi", json={}, headers=A).status_code == 409
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(14)}, headers=A)
    assert r.status_code == 409 and "isp-1" in r.json()["detail"]
    assert _potvrdjeni(k, b) == ["isp-1"] and _stanje(k, "rok-ai") == "REJECTED"


def test_potvrda_predloga_bez_ispravke_i_dalje_radi(lanac):
    k, b = lanac
    _predlog(b)
    assert k.post("/api/rokovi/rok-ai/potvrdi", json={}, headers=A).status_code == 200
    assert _stanje(k, "rok-ai") == "CONFIRMED"


def test_3k_odbijen_slican_red_drugog_predloga_se_ne_koristi_ponovo(lanac):
    """3. krug revizije: ranije je „isti predmet, opis, datum, akter ispravke“ ponovo uzimao i ODBIJEN red drugog
    predloga — potvrda nije mogla da ga oživi, a ruta je javljala CONFIRMED (nula obaveza)."""
    from shared.rok_ispravka import AKTER_ISPRAVKE
    k, b = lanac
    _predlog(b)
    b.tabele["predmet_hronologija"].append({"id": "stari-isp", "predmet_id": "p-1", "user_id": "uid-A", "dogadjaj": "Rok za tužbu",
                                            "datum": _d(12), "datum_iso": _d(12), "vaznost": "važan", "akter": AKTER_ISPRAVKE,
                                            "izvor": "HUMAN_DIRECT", "vrsta": "rok"})
    assert k.post("/api/rokovi/stari-isp/odbij", json={}, headers=A).status_code == 200
    r = k.post("/api/rokovi/rok-ai/ispravi", json={"datum_iso": _d(12)}, headers=A)
    assert r.status_code == 200 and r.json()["rok_id"] != "stari-isp", r.text
    assert _potvrdjeni(k, b) == [r.json()["rok_id"]]

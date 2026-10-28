# -*- coding: utf-8 -*-
"""N2 — čarobnjak prijema: istovremeni zahtevi za isti predmet i identitet klijenta u nalazu provere sukoba.
Stvarne rute nad fake bazom (isti `solo` kao VCR001 T02). Browser tok: frontend-v2-ng/tests/live-n2-carobnjak-e2e.mjs."""
import asyncio

import httpx

import api
import routers.intake as INT
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401


def _klijent(k, h=A, ime="Marko", prezime="Markovic", **dodatno):
    r = k.post("/klijenti", json={"tip": "fizicko_lice", "ime": ime, "prezime": prezime, **dodatno}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["klijent"]["id"]


async def _istovremeno(telo, n=2):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://t") as c:
        return await asyncio.gather(*[c.post("/api/intake/kreiraj", json=telo, headers=A) for _ in range(n)])


def test_istovremeni_zahtevi_za_isti_naziv_otvaraju_jedan_predmet(solo):
    """Izmereno pre ispravke: dva istovremena zahteva (dva taba) → 200/200 i DVA predmeta."""
    k, b = solo
    kid = _klijent(k)
    odgovori = asyncio.run(_istovremeno({"klijent_id": kid, "naziv": "Istovremeno", "opis": "x"}, n=3))
    statusi = sorted(r.status_code for r in odgovori)
    assert statusi == [200, 409, 409], statusi
    assert len([p for p in b.tabele["predmeti"] if p["naziv"] == "Istovremeno"]) == 1
    assert INT._OTVARANJE_U_TOKU == set()                      # oznaka se oslobađa posle zahteva


def test_oznaka_ne_blokira_drugi_naziv_ni_drugog_korisnika(solo):
    k, b = solo
    kid_a, kid_b = _klijent(k), _klijent(k, h=B, ime="Bojan", prezime="Bezveze")
    INT._OTVARANJE_U_TOKU.add(("uid-A", "Zaključan naziv"))
    try:
        assert k.post("/api/intake/kreiraj", json={"klijent_id": kid_a, "naziv": "Zaključan naziv"}, headers=A).status_code == 409
        assert k.post("/api/intake/kreiraj", json={"klijent_id": kid_a, "naziv": "Drugi naziv"}, headers=A).status_code == 200
        assert k.post("/api/intake/kreiraj", json={"klijent_id": kid_b, "naziv": "Zaključan naziv"}, headers=B).status_code == 200
    finally:
        INT._OTVARANJE_U_TOKU.discard(("uid-A", "Zaključan naziv"))


def test_oznaka_se_oslobadja_i_kad_upis_padne(solo, monkeypatch):
    k, b = solo
    kid = _klijent(k)
    pravi = INT._get_supa

    class _Pada:
        def __init__(self, s):
            self._s = s

        def table(self, ime):
            t = self._s.table(ime)
            if ime == "predmeti":
                t.insert = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("baza pala"))
            return t

    monkeypatch.setattr(INT, "_get_supa", lambda: _Pada(pravi()))
    from fastapi.testclient import TestClient
    r = TestClient(api.app, raise_server_exceptions=False).post("/api/intake/kreiraj", json={"klijent_id": kid, "naziv": "Pad upisa"}, headers=A)
    assert r.status_code >= 500
    assert INT._OTVARANJE_U_TOKU == set()


def test_nalaz_provere_sukoba_nosi_identitet_klijenta(solo):
    """V2 razlikuje IZABRANOG klijenta od imenjaka po `klijent_id` nalaza; status servera se ne menja."""
    k, b = solo
    k1 = _klijent(k, email="marko.prvi@primer.test")
    r = k.post("/api/intake/kreiraj", json={"klijent_id": k1, "naziv": "Prvi predmet"}, headers=A)
    assert r.status_code == 200, r.text
    c = k.post("/api/conflict-check", json={"ime_prezime": "Marko Markovic"}, headers=A)
    assert c.status_code == 200, c.text
    d = c.json()
    nalazi = [x for x in d["konflikti"] if x["sloj"] == "klijenti"]
    assert nalazi and all(x["klijent_id"] == k1 for x in nalazi), nalazi
    assert d["status"] == "conflict"                           # server i dalje prijavljuje; V2 odlučuje po identitetu
    # B ima SVOG Marka sa predmetom: njegova provera ima nalaze, a nijedan ne nosi identitet klijenta A
    kb = _klijent(k, h=B)
    assert k.post("/api/intake/kreiraj", json={"klijent_id": kb, "naziv": "B predmet"}, headers=B).status_code == 200
    cb = k.post("/api/conflict-check", json={"ime_prezime": "Marko Markovic"}, headers=B)
    nalazi_b = [x for x in cb.json()["konflikti"] if x["sloj"] == "klijenti"]
    assert cb.status_code == 200 and nalazi_b and all(x["klijent_id"] == kb for x in nalazi_b), nalazi_b


def test_protivna_strana_iz_uloga_klijenta_nije_klijent(solo):
    """Nalaz pregleda M1: upis veze piše `uloga_klijenta`; provera je čitala staru kolonu `uloga`, pa je
    protivna strana prijavljivana kao klijent u sistemu, a V2 bi je posle N2 spustio na pregled."""
    k, b = solo
    marko = _klijent(k)
    petar = _klijent(k, ime="Petar", prezime="Peric")
    pid = k.post("/api/intake/kreiraj", json={"klijent_id": petar, "naziv": "Peric naknada"}, headers=A).json()["predmet_id"]
    assert k.post(f"/api/predmeti/{pid}/confirm-links", json={"klijent_ids": [marko], "uloga": "protivna_stranka"}, headers=A).status_code == 200
    d = k.post("/api/conflict-check", json={"ime_prezime": "Marko Markovic"}, headers=A).json()
    n = [x for x in d["konflikti"] if x["sloj"] == "klijenti" and x["klijent_id"] == marko]
    assert n and n[0]["tip_konflikta"] == "suprotna_strana" and n[0]["uloga_klijent"] is False and n[0]["sever"] == "VISOK", n
    assert d["status"] == "conflict"


def test_ime_u_nazivu_svog_predmeta_nosi_spisak_klijenata(solo):
    k, b = solo
    jelena = _klijent(k, ime="Jelena", prezime="Jelic")
    k.post("/api/intake/kreiraj", json={"klijent_id": jelena, "naziv": "Jelena Jelic protiv Osiguranja"}, headers=A)
    d = k.post("/api/conflict-check", json={"ime_prezime": "Jelena Jelic"}, headers=A).json()
    s1 = [x for x in d["konflikti"] if x["sloj"] == "predmeti"]
    assert s1 and s1[0]["klijenti_predmeta"] == [jelena], d["konflikti"]


def test_dva_klijenta_istog_imena_u_istom_predmetu_daju_dva_nalaza(solo):
    """Nalaz pregleda m2: prvi red veze je sakrivao imenjaka u istom predmetu."""
    import time
    k, b = solo
    k1 = _klijent(k, email="m1@primer.test")
    pid = k.post("/api/intake/kreiraj", json={"klijent_id": k1, "naziv": "Zajednicki predmet"}, headers=A).json()["predmet_id"]
    time.sleep(5.5)                                            # zaštita od duplog klika za isto ime klijenta
    k2 = _klijent(k, email="m2@primer.test")
    assert k.post(f"/api/predmeti/{pid}/confirm-links", json={"klijent_ids": [k2], "uloga": "stranka"}, headers=A).status_code == 200
    d = k.post("/api/conflict-check", json={"ime_prezime": "Marko Markovic"}, headers=A).json()
    ids = sorted(x["klijent_id"] for x in d["konflikti"] if x["sloj"] == "klijenti" and x["predmet_id"] == pid)
    assert ids == sorted([k1, k2]), d["konflikti"]

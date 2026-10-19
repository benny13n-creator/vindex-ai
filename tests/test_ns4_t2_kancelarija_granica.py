# -*- coding: utf-8 -*-
"""Night Sprint IV — Task 2: članstvo u kancelariji kao granica memorije — praznine koje RH001/NS008 T19 ne pokrivaju.

Pokriveno ranije (ne ponavlja se): A/B iste kancelarije, C druga kancelarija, REMOVED/SUSPENDED/INVITED za Law Brain,
delegiranje i opoziv, bajt-identični odgovori, greške bez signala postojanja (`test_ns008_t19_acl_matrix.py`,
`test_rh001_legacy_memory_acl.py`).

Ovde, kroz STVARNE legacy rute `/api/firma-memorija/*`:
  • podmetnut ID druge kancelarije u upitu/telu se ignoriše (kancelarija se izvodi na serveru);
  • suspendovan / uklonjen član i član sa zastarelom vrednošću `aktivan` (pre migracije 067) ne vide ništa;
  • solo advokat (bez kancelarije) ne dobija ničije znanje;
  • tuđ, nepostojeći i neispravan `predmet` u upisu beleške → isti 404, ništa upisano;
  • `client_memory` (profil klijenta) — bio vezan za IME, kolega je video profil tuđeg klijenta (strogi xfail do
    NS4 završnog zatvaranja). Sada vezan za identitet klijenta i vlasnika: test ispod PROLAZI; matrica u
    tests/test_ns4f_o2_profil_klijenta.py.
"""
import pytest

from tests.test_rh001_legacy_memory_acl import H, K1, KL_A, PA, svet  # noqa: F401  (fixture)

K2 = "e2e2e2e2-1919-4000-8000-000000000002"
TAJNA_K2 = "Tajna beleška kancelarije K2 o sudiji"


def _sa_k2(baza):
    baza.tabele["kancelarije"].append({"id": K2, "admin_uid": "uid-Y"})
    baza.tabele["memory_entries"].append(
        {"id": "m-k2", "kancelarija_id": K2, "user_id": "uid-Y", "entity_type": "sudija", "entity_id": "Petrović",
         "entity_name": "Sudija Petrović", "tip": "obrazac", "sadrzaj": TAJNA_K2, "vaznost": "visoka",
         "aktivan": True, "izvor": "manual", "potvrde_count": 1, "zastarela": False, "confidence": 0.9,
         "created_at": "2026-09-05T00:00:00+00:00"})


@pytest.mark.parametrize("ruta", [
    f"/api/firma-memorija/sve?kancelarija_id={K2}",
    f"/api/firma-memorija/pretrazi?kancelarija_id={K2}",
    f"/api/firma-memorija/sudija/Petrović?kancelarija_id={K2}",
    f"/api/firma-memorija/kontekst-za-ai?sudija_ime=Petrović&kancelarija_id={K2}",
])
def test_podmetnut_id_druge_kancelarije_u_upitu_se_ignorise(svet, ruta):
    napravi, _ = svet
    k, baza = napravi()
    _sa_k2(baza)
    r = k.get(ruta, headers=H("B"))
    assert r.status_code == 200 and TAJNA_K2 not in r.text


def test_podmetnut_id_druge_kancelarije_u_telu_upisa_se_ignorise(svet):
    napravi, _ = svet
    k, baza = napravi()
    _sa_k2(baza)
    r = k.post("/api/firma-memorija/dodaj", headers=H("B"),
               json={"entity_type": "sudija", "entity_id": "Jović", "tip": "napomena", "sadrzaj": "Kratka napomena.",
                     "kancelarija_id": K2})
    assert r.status_code == 200
    novi = [m for m in baza.tabele["memory_entries"] if m.get("entity_id") == "Jović"]
    assert [m["kancelarija_id"] for m in novi] == [K1]


@pytest.mark.parametrize("status", ["SUSPENDED", "REMOVED", "INVITED", "PENDING", "aktivan"])
def test_neaktivan_clan_ne_vidi_znanje_kancelarije(svet, status):
    napravi, _ = svet
    k, baza = napravi()
    for c in baza.tabele["kancelarija_clanovi"]:
        if c["user_id"] == "uid-B":
            c["status"] = status
    for ruta in ("/api/firma-memorija/sve", "/api/firma-memorija/pretrazi",
                 "/api/firma-memorija/kontekst-za-ai?sudija_ime=Petrović"):
        r = k.get(ruta, headers=H("B"))
        assert r.status_code == 200, (ruta, r.text)
        assert "Sudija traži tabelu rokova." not in r.text, (status, ruta)
    assert k.get("/api/firma-memorija/sudija/Petrović", headers=H("B")).status_code == 400


def test_solo_advokat_bez_kancelarije_ne_dobija_nicije_znanje(svet):
    napravi, _ = svet
    k, baza = napravi()
    assert k.get("/api/firma-memorija/sve", headers=H("C")).json() == {"memorije": [], "ukupno": 0}
    assert k.get("/api/firma-memorija/kontekst-za-ai?sudija_ime=Petrović", headers=H("C")).json()["kontekst"] == ""
    r = k.post("/api/firma-memorija/dodaj", headers=H("C"),
               json={"entity_type": "sudija", "entity_id": "Jović", "tip": "napomena", "sadrzaj": "Kratka napomena."})
    assert r.status_code == 400


@pytest.mark.parametrize("entity_id", [PA, "dddddddd-1919-4000-8000-000000000009", "nije-uuid"],
                         ids=["tudj", "nepostojeci", "neispravan"])
def test_beleska_uz_predmet_koji_korisnik_ne_sme_da_vidi_se_ne_upisuje(svet, entity_id):
    napravi, _ = svet
    k, baza = napravi()
    pre = len(baza.tabele["memory_entries"])
    r = k.post("/api/firma-memorija/dodaj", headers=H("B"),
               json={"entity_type": "predmet", "entity_id": entity_id, "tip": "napomena", "sadrzaj": "Pokušaj upisa."})
    assert r.status_code == 404 and "Petrović protiv" not in r.text
    assert len(baza.tabele["memory_entries"]) == pre


def test_kolega_ne_vidi_profil_tudjeg_klijenta(svet):
    napravi, _ = svet
    k, baza = napravi()
    baza.tabele["client_memory"].append({"id": "cm-1", "kancelarija_id": K1, "klijent_ime": "Marković",
                                         "klijent_id": KL_A, "prihvata_nagodbu": False,
                                         "napomene": "Klijent Marković krije imovinu."})
    r = k.get("/api/firma-memorija/klijent/Marković", headers=H("B"))
    assert r.status_code == 200
    assert "krije imovinu" not in r.text


def test_kontrola_aktivan_clan_vidi_opstu_belesku(svet):
    """Pozitivna kontrola za test iznad: bez nje bi „ništa ne vidi" prolazilo i kad niko ništa ne vidi."""
    napravi, _ = svet
    k, _ = napravi()
    for ruta in ("/api/firma-memorija/sve", "/api/firma-memorija/pretrazi",
                 "/api/firma-memorija/kontekst-za-ai?sudija_ime=Petrović"):
        assert "Sudija traži tabelu rokova." in k.get(ruta, headers=H("B")).text, ruta

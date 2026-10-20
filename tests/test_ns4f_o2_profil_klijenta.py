# -*- coding: utf-8 -*-
"""NS4 O2 — profil klijenta (`client_memory`) samo za VLASNIKA klijenta, po identitetu (ne po imenu).

Kroz STVARNE rute (`/api/firma-memorija/klijent/*`, `/kontekst-za-ai`) nad lažnom bazom. Svet: kancelarija K1
(admin X; aktivni A i B; suspendovan C, uklonjen D, pozvan E), kancelarija K2 (admin Y), solo S. A i B imaju
SVAKI svog klijenta istog imena „Marković". Pravilo: članstvo u kancelariji (ni admin uloga) NE daje pristup
profilu tuđeg klijenta; tuđ, nepostojeći i neispravan identitet daju isti odgovor (bez proročišta).
"""
import pytest

import tests.ns008_fake as f8
from tests.ns005_harness import TOKENI

K1 = "e1e1e1e1-4f4f-4000-8000-000000000001"
K2 = "e2e2e2e2-4f4f-4000-8000-000000000002"
KL_A = "c1c1c1c1-4f4f-4000-8000-0000000000a1"
KL_B = "c2c2c2c2-4f4f-4000-8000-0000000000b1"
KL_A_OBRISAN = "c3c3c3c3-4f4f-4000-8000-0000000000a2"
NEPOSTOJECI = "c9c9c9c9-4f4f-4000-8000-000000000999"
TAJNA = "Klijent krije imovinu na Kipru"
KORISNICI = {"A": "uid-A", "B": "uid-B", "X": "uid-X", "C": "uid-C", "D": "uid-D", "E": "uid-E", "Y": "uid-Y",
             "S": "uid-S"}


@pytest.fixture
def svet(monkeypatch):
    for ko, uid in KORISNICI.items():
        monkeypatch.setitem(TOKENI, f"tok-{ko}", uid)
    k, b = f8.pripremi(monkeypatch, {
        "kancelarije": [{"id": K1, "admin_uid": "uid-X"}, {"id": K2, "admin_uid": "uid-Y"}],
        "kancelarija_clanovi": [
            {"kancelarija_id": K1, "user_id": "uid-A", "status": "ACTIVE"},
            {"kancelarija_id": K1, "user_id": "uid-B", "status": "ACTIVE"},
            {"kancelarija_id": K1, "user_id": "uid-C", "status": "SUSPENDED"},
            {"kancelarija_id": K1, "user_id": "uid-D", "status": "REMOVED"},
            {"kancelarija_id": K1, "user_id": "uid-E", "status": "INVITED"},
        ],
        "klijenti": [{"id": KL_A, "user_id": "uid-A", "ime": "Marković", "deleted_at": None},
                     {"id": KL_B, "user_id": "uid-B", "ime": "Marković", "deleted_at": None},
                     {"id": KL_A_OBRISAN, "user_id": "uid-A", "ime": "Jović", "deleted_at": "2026-10-01T00:00:00+00:00"}],
        "client_memory": [], "memory_entries": [], "judge_patterns": [], "partner_profiles": [],
        "predmet_delegiranja": [], "predmeti": [],
    })
    b.jedinstveno["client_memory"] = ("kancelarija_id", "klijent_ime")        # UNIQUE iz 046
    import shared.rate as rate
    monkeypatch.setattr(rate.limiter, "enabled", False)
    yield k, b
    f8.ocisti()


def H(ko):
    return {"Authorization": f"Bearer tok-{ko}"}


def _sacuvaj(k, ko, **telo):
    return k.post("/api/firma-memorija/klijent/sacuvaj", headers=H(ko), json=telo)


def _profil_a(k, b):
    r = _sacuvaj(k, "A", klijent_id=KL_A, klijent_ime="Marković", prihvata_nagodbu=False, napomene=TAJNA,
                 kljucna_odluka="Odbio nagodbu u prvom ročištu")
    assert r.status_code == 200, r.text
    b.tabele["memory_entries"].append(
        {"id": "m-kl", "kancelarija_id": K1, "user_id": "uid-A", "entity_type": "klijent", "entity_id": KL_A,
         "entity_name": "Marković", "tip": "preferencija", "sadrzaj": "Beleška: " + TAJNA, "vaznost": "visoka",
         "aktivan": True, "created_at": "2026-10-01T00:00:00+00:00"})


# ─── pozitivne kontrole ─────────────────────────────────────────────────────────────────────────────────────

def test_vlasnik_cuva_i_cita_svoj_profil(svet):
    k, b = svet
    _profil_a(k, b)
    r = k.get(f"/api/firma-memorija/klijent/{KL_A}", headers=H("A"))
    assert r.status_code == 200 and r.json()["profil"]["napomene"] == TAJNA
    assert r.json()["profil"]["klijent_id"] == KL_A and TAJNA in r.json()["memorije"][0]["sadrzaj"]
    _sacuvaj(k, "A", klijent_id=KL_A, rizik_profil="visok", kljucna_odluka="Druga odluka")
    red = [x for x in b.tabele["client_memory"] if x["klijent_id"] == KL_A]
    assert len(red) == 1 and red[0]["rizik_profil"] == "visok" and len(red[0]["kljucne_odluke"]) == 2


def test_vlasnik_dobija_profil_u_ai_kontekstu(svet):
    k, b = svet
    _profil_a(k, b)
    r = k.get(f"/api/firma-memorija/kontekst-za-ai?klijent_id={KL_A}&klijent_ime=Marković", headers=H("A"))
    assert "NIKAD ne prihvata nagodbu" in r.json()["kontekst"] and TAJNA in r.json()["kontekst"]


# ─── čitanje: kolega, admin, druga kancelarija ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ko", ["B", "X", "Y"])
def test_tudji_profil_se_ne_cita_ni_po_id_ni_po_imenu(svet, ko):
    k, b = svet
    _profil_a(k, b)
    prazno = k.get(f"/api/firma-memorija/klijent/{NEPOSTOJECI}", headers=H(ko))
    for ref in (KL_A, "Marković", "Markovi", KL_A.upper()):
        r = k.get(f"/api/firma-memorija/klijent/{ref}", headers=H(ko))
        assert r.status_code == prazno.status_code == 200
        assert r.content == prazno.content, f"{ko}/{ref}: odgovor se razlikuje od nepostojećeg klijenta"
        assert TAJNA not in r.text


@pytest.mark.parametrize("ko", ["B", "X", "Y"])
def test_tudji_profil_ne_ulazi_u_ai_kontekst(svet, ko):
    k, b = svet
    _profil_a(k, b)
    for upit in (f"klijent_id={KL_A}&klijent_ime=Marković", "klijent_ime=Marković", f"klijent_id={KL_A}"):
        r = k.get(f"/api/firma-memorija/kontekst-za-ai?{upit}", headers=H(ko))
        assert r.status_code == 200 and TAJNA not in r.text and "nagodbu" not in r.text, (ko, upit)


def test_samo_ime_ne_daje_profil_ni_vlasniku(svet):
    """Ime nije akreditiv: bez identiteta nema profila (vlasnik koristi klijent_id)."""
    k, b = svet
    _profil_a(k, b)
    assert k.get("/api/firma-memorija/klijent/Marković", headers=H("A")).json() == {"profil": None, "memorije": []}
    assert TAJNA not in k.get("/api/firma-memorija/kontekst-za-ai?klijent_ime=Marković", headers=H("A")).text


@pytest.mark.parametrize("ko", ["C", "D", "E", "S"])
def test_suspendovan_uklonjen_pozvan_i_solo_nemaju_pristup(svet, ko):
    k, b = svet
    _profil_a(k, b)
    r = k.get(f"/api/firma-memorija/klijent/{KL_A}", headers=H(ko))
    assert r.status_code == 400 and TAJNA not in r.text
    r = _sacuvaj(k, ko, klijent_id=KL_A, napomene="upad")
    assert r.status_code == 400
    assert "upad" not in str(b.tabele["client_memory"])
    assert TAJNA not in k.get(f"/api/firma-memorija/kontekst-za-ai?klijent_id={KL_A}", headers=H(ko)).text


# ─── upis: falsifikovan identitet, ime, istoimeni klijenti ──────────────────────────────────────────────────

@pytest.mark.parametrize("ko", ["B", "X", "Y"])
def test_tudji_profil_se_ne_menja_podmetnutim_id(svet, ko):
    k, b = svet
    _profil_a(k, b)
    pre = [dict(x) for x in b.tabele["client_memory"]]
    r = _sacuvaj(k, ko, klijent_id=KL_A, klijent_ime="Marković", prihvata_nagodbu=True, napomene="prepisano")
    nepostojeci = _sacuvaj(k, ko, klijent_id=NEPOSTOJECI, napomene="x")
    assert r.status_code == nepostojeci.status_code == 404 and r.content == nepostojeci.content
    assert b.tabele["client_memory"] == pre, "tuđ profil izmenjen ili dodat red"


def test_ime_bez_identiteta_ne_upisuje(svet):
    k, b = svet
    r = _sacuvaj(k, "B", klijent_ime="Marković", napomene="x")
    assert r.status_code == 422 and b.tabele["client_memory"] == []


@pytest.mark.parametrize("ref", ["nije-uuid", "", " ", KL_A_OBRISAN])
def test_neispravan_ili_obrisan_identitet_se_odbija(svet, ref):
    k, b = svet
    r = _sacuvaj(k, "A", klijent_id=ref, klijent_ime="Jović", napomene="x")     # i ime — ono ne sme da „spase" upis
    assert r.status_code in (404, 422) and b.tabele["client_memory"] == []


def test_istoimeni_klijenti_dve_osobe_dva_profila(svet):
    k, b = svet
    assert _sacuvaj(k, "A", klijent_id=KL_A, klijent_ime="Marković", napomene="profil A").status_code == 200
    assert _sacuvaj(k, "B", klijent_id=KL_B, klijent_ime="Marković", napomene="profil B").status_code == 200
    assert len(b.tabele["client_memory"]) == 2
    assert k.get(f"/api/firma-memorija/klijent/{KL_A}", headers=H("A")).json()["profil"]["napomene"] == "profil A"
    assert k.get(f"/api/firma-memorija/klijent/{KL_B}", headers=H("B")).json()["profil"]["napomene"] == "profil B"
    assert "profil A" not in k.get(f"/api/firma-memorija/klijent/{KL_A}", headers=H("B")).text


def test_stari_red_vezan_za_ime_se_ne_sluzi_i_ne_spaja(svet):
    """Red iz vremena pre O2 (ključ = ime, `klijent_id` podmetnut bilo kim) nema dokazan identitet."""
    k, b = svet
    b.tabele["client_memory"].append({"id": "cm-star", "kancelarija_id": K1, "klijent_ime": "Marković",
                                      "klijent_id": KL_A, "napomene": "Zatrovan profil", "kljucne_odluke": []})
    assert k.get(f"/api/firma-memorija/klijent/{KL_A}", headers=H("A")).json()["profil"] is None
    _sacuvaj(k, "A", klijent_id=KL_A, napomene="nov")
    stari = next(x for x in b.tabele["client_memory"] if x["id"] == "cm-star")
    assert stari["napomene"] == "Zatrovan profil" and len(b.tabele["client_memory"]) == 2


def test_istovremeni_prvi_upis_istog_klijenta_jedan_red(svet, monkeypatch):
    """Drugi zahtev nije video red prvog (trka) → INSERT pada na UNIQUE → ažurira pobednikov red."""
    k, b = svet
    assert _sacuvaj(k, "A", klijent_id=KL_A, napomene="prvi").status_code == 200
    izvorni, prvi_select = b.table, {"bio": False}

    def trka(ime):
        u = izvorni(ime)
        if ime == "client_memory":
            iz = u.execute

            def execute():
                if u.radnja[0] == "select" and not prvi_select["bio"]:
                    prvi_select["bio"] = True
                    return type("R", (), {"data": [], "count": 0})()
                return iz()
            u.execute = execute
        return u
    monkeypatch.setattr(b, "table", trka)
    assert _sacuvaj(k, "A", klijent_id=KL_A, napomene="drugi").status_code == 200
    redovi = [x for x in b.tabele["client_memory"] if x["klijent_id"] == KL_A]
    assert len(redovi) == 1 and redovi[0]["napomene"] == "drugi"


# ─── pad provere vlasništva ─────────────────────────────────────────────────────────────────────────────────

def test_pad_acl_provere_zatvara(svet, caplog):
    k, b = svet
    _profil_a(k, b)
    b.greske["klijenti"] = Exception("db down " + TAJNA)
    r = k.get(f"/api/firma-memorija/klijent/{KL_A}", headers=H("A"))
    assert r.status_code == 503 and TAJNA not in r.text
    pre = [dict(x) for x in b.tabele["client_memory"]]
    assert _sacuvaj(k, "A", klijent_id=KL_A, napomene="x").status_code == 503
    assert b.tabele["client_memory"] == pre
    r = k.get(f"/api/firma-memorija/kontekst-za-ai?klijent_id={KL_A}", headers=H("A"))
    assert r.status_code == 200 and TAJNA not in r.text and "nagodbu" not in r.text
    assert TAJNA not in caplog.text, "sadržaj greške baze (može nositi podatke) završio u logu"

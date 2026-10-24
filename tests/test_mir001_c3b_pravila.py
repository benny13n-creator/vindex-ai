# -*- coding: utf-8 -*-
"""MIR001 C3b — regresije koje važe posle vraćanja neuspele ispravke uputstva (`589cd4f0`, GATE-03 FAIL).

Ispravka samo tekstom uputstva nije prošla slepo merenje (`docs/v2-execution/MIR001_C3B_LEDGER.md`, TASK-03), pa je
uputstvo nacrta vraćeno na `ab63f913` (STRUCTURAL RECOVERY TASK-00). Ostaje samo izmena naknadne provere (GATE-02 F4):
izuzetak važi samo za rečenicu koja JE oznaka, ne za golu tvrdnju kojoj je model dodao oznaku.
"""
import hashlib

# Sistemske poruke svih savetnika = `ab63f913` (nacrt vraćen; ostali nikad menjani u C3b)
AB63 = {
    "intake": "4d9cc68a524cbdc0fad27f98abd18c82423288885925a69b7a5d7340494397f5",
    "research": "259b0da9e5fc3485244a9bb58ae3443db021783ca65fee1e29554742812ece16",
    "drafting": "bac2d39145b7c09adb60f84cf3e63a4c2046511e030d11d13c52282f573718b2",
    "litigation": "d4604b35cdba119e2ef30cb2cd2747384b7eb00ce9c4ea380c23bcbbabdda2c0",
    "billing": "9b92e42dc61282a780ebd1580cd8b334b402e7eb73795da790e7001f38eb2fd0",
    "deadline": "50e0d20e9d3cda1481e382b6ee82879ae96092078731372abe5ead785192ba3a",
}


def test_uputstva_savetnika_su_ab63f913_bez_neuspelih_pravila_c3b():
    import routers.multi_agent as MA
    assert {a: hashlib.sha256(c["system"].encode()).hexdigest() for a, c in MA._AGENTS.items()} == AB63
    assert not any("PROCESNO STANJE — OBAVEZNA PRAVILA" in c["system"] for c in MA._AGENTS.values())


def test_provera_ne_preskace_golu_tvrdnju_uz_oznaku_modela_i_ne_oznacava_predlog_preispitivanja():
    """GATE-02 F4/F1: izuzetak provere važi samo za rečenicu koja JE oznaka. Gola tvrdnja kojoj je model sam dodao
    oznaku — u bilo kom obliku, i „DOK-n — opis“ — i dalje se označava; obrazložen predlog sudu da preispita odluku — ne."""
    import routers.multi_agent as MA
    od = [{"oznaka": "DOK-07", "tekst": "Sud prihvata predlog za dopunu vestacenja."},
          {"oznaka": "DOK-07", "tekst": "Sud nalaze tuzenom da dostavi gradjevinski dnevnik u roku od 15 dana."}]
    n = lambda t: len(MA._protivreci_odlukama(t, od))
    assert n("Dopuna veštačenja nije potrebna [PROVERITI PROCESNO STANJE: DOK-07].") == 1
    assert n("[PROVERITI PROCESNO STANJE: x] Dopuna veštačenja nije potrebna.") == 1
    assert n("Dopuna veštačenja nije potrebna jer je nalaz potpun [PROVERITI PROCESNO STANJE: DOK-08 — tuženi odustao].") == 1
    assert n("Nejasno:\n  - [PROVERITI PROCESNO STANJE: da li DOK-08 menja odluku o dopuni veštačenja koju sud nije odbio]") == 0
    assert n("Iako je sud prihvatio predlog za dopunu veštačenja (DOK-07), tužilac predlaže da sud preispita tu odluku i "
             "odustane od dopune, jer je tuženi naveo da dnevnik nije sačuvan.") == 0
    oznacen = MA._oznaci_protivrecnosti("Dopuna veštačenja nije potrebna.", MA._protivreci_odlukama("Dopuna veštačenja nije potrebna.", od))
    assert "[PROVERITI PROCESNO STANJE: DOK-07 — " in oznacen

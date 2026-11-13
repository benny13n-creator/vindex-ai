# -*- coding: utf-8 -*-
"""MIR001 C3b — regresije koje važe posle vraćanja neuspele ispravke uputstva (`589cd4f0`, GATE-03 FAIL).

Ispravka samo tekstom uputstva nije prošla slepo merenje (`docs/v2-execution/MIR001_C3B_LEDGER.md`, TASK-03), pa je
uputstvo nacrta vraćeno na `ab63f913` (STRUCTURAL RECOVERY TASK-00). Ostaje samo izmena naknadne provere (GATE-02 F4):
izuzetak važi samo za rečenicu koja JE oznaka, ne za golu tvrdnju kojoj je model dodao oznaku.
"""
import hashlib

# Osnovica sistemskih poruka svih savetnika je `ab63f913` (nacrt vraćen; ostali nikad menjani u C3b). Jedini izuzetak: intake,
# MIR002 S06 (odobrenje osnivača 2026-11-03) — samo red o čl. 371 ZOO (3 god. → 10 godina, osim kada zakon propisuje
# drugi rok; glasilo „Sl. gl. RS 29/1978“ → „Sl. list SFRJ, br. 29/78“); `tests/test_mir002_zoo371_intake.py`.
# Drugi dozvoljeni izuzetak: samo red o žalbi, čl. 367 ZPP sa izuzecima.
# Deadline: ciljana korekcija pogrešnih pravnih osnova i neuslovljenog datuma isteka (beta acceptance).
# Legal AI acceptance 08.11.2026: Drafting i Litigation imaju samo proverene pravne korekcije.
# Prethodni heševi intake: 4d9cc68a…94397f5 (ab63f913), d27da808…5ac635142 (342ae188, samo rok).
OCEKIVANI_SHA256 = {
    "intake": "2e4756220d42674e1db82c76d5399e44674543bac30d6542f06f778e66c2cf6f",
    "research": "259b0da9e5fc3485244a9bb58ae3443db021783ca65fee1e29554742812ece16",
    "drafting": "2aafe27ff7287339e9629ca8f4bf3e97ddeea5b23fe1a751f40633cc826aaf72",
    "litigation": "6090f18d9e718716b3c955688b29be651ebbc7511190332ca82673d6236cc870",
    "billing": "9b92e42dc61282a780ebd1580cd8b334b402e7eb73795da790e7001f38eb2fd0",
    "deadline": "a02053cb8e2e00d81a7a227bc52ec3a4c02c03969e742b479a50abb0f7767db2",
}


def test_uputstva_savetnika_su_zakljucana_bez_neuspelih_pravila_c3b():
    import routers.multi_agent as MA
    assert {a: hashlib.sha256(c["system"].encode()).hexdigest() for a, c in MA._AGENTS.items()} == OCEKIVANI_SHA256
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

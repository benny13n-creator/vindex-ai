# -*- coding: utf-8 -*-
"""NS4 nezavisni pregled — Zadatak 5: granice preračuna `case_patterns` (DOKAZ, ne ispravka).

`routers/learning._preracunaj_obrasce` je čitanje → računanje → upis u više zasebnih PostgREST poziva, bez
transakcije i bez zaključavanja. Dva svojstva koja NISU zagarantovana, zabeležena kao strogi xfail (prelaze u
XPASS → pad čim neko svojstvo postane tačno, pa se oznaka mora svesno skinuti):

  G1  Zastareo upis: preračun koji je pročitao `outcome_log` PRE tuđeg upisa, a piše POSLE tuđeg preračuna,
      prepisuje tačan zbir zastarelim (poslednji pisac pobeđuje). Samoisceljujuće pri sledećem upisu ishoda iste
      vrste spora — ali do tada brojevi koje čita `court_predictor` nisu tačni.
  G2  Postojeći faktori se čitaju BEZ straničenja: iznad PostgREST `max-rows` (podrazumevano 1000) deo postojećih
      redova se ne vidi → INSERT pada na `UNIQUE(user_id, tip_spora, faktor)` (037) → preračun se prekida usred
      petlje (non-fatal), faktori posle tog mesta ostaju zastareli. Duplikata nema (ograničenje u šemi).

Potpuno rešenje traži atomski preračun u bazi (SQL funkcija/RPC sa `pg_advisory_xact_lock` ili jednim
`INSERT … ON CONFLICT … DO UPDATE` iz agregata) — to je MIGRACIJA i nije urađeno (odluka osnivača, izveštaj §5).
"""
import pytest

import routers.learning as L
import tests.ns008_fake as f8

PA = "aaaaaaaa-5555-4000-8000-00000000000a"
PA2 = "aaaaaaaa-5555-4000-8000-00000000000b"


@pytest.fixture
def baza(monkeypatch):
    _, b = f8.pripremi(monkeypatch, {"outcome_log": [], "case_patterns": []})
    b.jedinstveno["case_patterns"] = ("user_id", "tip_spora", "faktor")       # UNIQUE iz 037
    yield b
    f8.ocisti()


def _ishod(b, pid, ishod, faktori):
    b.tabele["outcome_log"].append({"predmet_id": pid, "user_id": "uid-A", "ishod": ishod,
                                    "presudni_faktori": faktori, "tip_spora": "radni"})


def _zbir(b):
    return {r["faktor"]: (r["pobede"], r["porazi"], r["ukupno"]) for r in b.tabele["case_patterns"]
            if r["tip_spora"] == "radni"}


@pytest.mark.xfail(strict=True, reason="G1: preračun nije linearizovan — zastareo upis prepisuje tačan zbir")
def test_g1_zastareo_preracun_ne_prepisuje_tacan_zbir(baza, monkeypatch):
    _ishod(baza, PA, "pobeda", ["svedoci"])
    L._preracunaj_obrasce(baza, "uid-A", "radni")
    zastareo_snimak = [dict(r) for r in baza.tabele["outcome_log"]]       # zahtev 1 je pročitao samo PA
    _ishod(baza, PA2, "poraz", ["svedoci"])                                # zahtev 2: upis + pun preračun
    L._preracunaj_obrasce(baza, "uid-A", "radni")
    assert _zbir(baza) == {"svedoci": (1, 1, 2)}                            # tačno posle zahteva 2
    izvorni = baza.table

    def zastareo(ime):
        u = izvorni(ime)
        if ime == "outcome_log":
            u.execute = lambda: type("R", (), {"data": zastareo_snimak, "count": None})()
        return u
    monkeypatch.setattr(baza, "table", zastareo)
    L._preracunaj_obrasce(baza, "uid-A", "radni")                          # zahtev 1 tek sada piše
    assert _zbir(baza) == {"svedoci": (1, 1, 2)}, "poslednji (zastareo) pisac je prepisao tačan zbir"


@pytest.mark.xfail(strict=True, reason="G2: postojeći faktori bez straničenja — iznad max-rows preračun se prekida")
def test_g2_vise_postojecih_faktora_od_max_rows(baza, monkeypatch):
    cap = 5                                                                 # model PostgREST max-rows (u prod 1000)
    faktori = [f"f{i:02d}" for i in range(cap + 3)]
    for i, f in enumerate(faktori):
        baza.tabele["case_patterns"].append({"id": f"cp{i}", "user_id": "uid-A", "tip_spora": "radni", "faktor": f,
                                             "pobede": 9, "porazi": 9, "ukupno": 18})       # zastarelo
    _ishod(baza, PA, "pobeda", faktori[:])
    monkeypatch.setattr(L, "_STRANA", cap)
    izvorni = baza.table

    def sa_capom(ime):
        u = izvorni(ime)
        if ime == "case_patterns":
            iz = u.execute

            def execute():
                r = iz()
                if u.radnja[0] == "select" and isinstance(r.data, list):
                    r.data = r.data[:cap]
                return r
            u.execute = execute
        return u
    monkeypatch.setattr(baza, "table", sa_capom)
    try:
        L._preracunaj_obrasce(baza, "uid-A", "radni")
    except Exception:
        pass                                    # ruta ovo hvata kao non-fatal upozorenje (learning.py, korak 2)
    ocekivano = {f: (1, 0, 1) for f in faktori[:10]}
    assert _zbir(baza) == ocekivano, "deo faktora ostao zastareo"

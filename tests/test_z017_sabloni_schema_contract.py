# -*- coding: utf-8 -*-
"""Z017 — `POST /api/doc-templates/sacuvaj` mora stvarno da sacuva dokument.

PRE-STATE (dokazano uzivo nad produkcionom bazom, 2026-09-06):
    POST /api/doc-templates/sacuvaj  -> 500, na SVAKI poziv, za svakog
    korisnika i svaki predmet. Ekran je uredno prikazao „Dokument nije
    sacuvan", ali funkcija nikada nije radila.

  Uzrok je isti kvar kao B-U-001, B-U-002 i Z017 komentari: kod je gadjao
  kolone kojih u produkciji nema. `predmet_beleske` ima (sondirano):
      id, predmet_id, user_id, sadrzaj, created_at, updated_at
  a upis je slao `tekst` I `tip` -> PostgREST PGRST204 -> 500.

  Uz to je ispred naziva stajala ukrasna ikonica koja bi zavrsila U BAZI, a
  ne samo na ekranu -- zabranjena pravilom o ikonicama.

ZASTO JE OVO VAZNO: cuvanje je jedina tacka u kojoj generisan dokument
prestaje da bude prolazan tekst na ekranu. Dok ne radi, svaki naplativ poziv
za generisanje zavrsi kao tekst koji se izgubi pri sledecem kliku.

INVARIJANTE:
  1. Upis sme da gadja samo kolone koje postoje u produkciji.
  2. Sadrzaj nosi naziv dokumenta i njegov tekst -- oba, i bez ukrasa.
  3. Tudji predmet daje 404, ne tihi upis.
  4. META: laznjak stvarno puca na `tekst` i na `tip`.
"""
import asyncio

import pytest
from unittest.mock import patch

import routers.doc_templates as DT
from tests._schema_fake import Drift42703, napravi_supa

UID = "00000000-0000-0000-0000-00000000000a"
PID = "00000000-0000-0000-0000-0000000000p1"

# Sondirano nad produkcionom bazom 2026-09-06. Namerno izostavljeni `tekst`
# i `tip` -- ne postoje u `predmet_beleske`.
SEMA = {
    "predmet_beleske": {"id", "predmet_id", "user_id", "sadrzaj",
                        "created_at", "updated_at"},
    "predmeti": {"id", "naziv", "user_id", "status", "tip"},
}

PREDMET = {"id": PID, "user_id": UID, "naziv": "Radni spor"}


def _lazni_request():
    from starlette.requests import Request
    return Request({"type": "http", "method": "POST",
                    "path": "/api/doc-templates/sacuvaj", "headers": [],
                    "query_string": b"", "client": ("127.0.0.1", 0),
                    "server": ("testserver", 80), "scheme": "http",
                    "root_path": "", "app": None})


class _Req:
    def __init__(self, predmet_id=PID, naziv="Tužba", sadrzaj="Tekst dokumenta.",
                 sablon_id="tuzba-opstinska"):
        self.predmet_id = predmet_id
        self.naziv = naziv
        self.sadrzaj = sadrzaj
        self.sablon_id = sablon_id


def _sacuvaj(redovi, req=None):
    supa = napravi_supa(SEMA, redovi)
    with patch.object(DT, "_get_supa", return_value=supa):
        odgovor = asyncio.run(DT.sacuvaj_dokument(
            request=_lazni_request(), req=req or _Req(), user={"user_id": UID}))
    return odgovor, supa


# ── 1. Upis ne sme da gadja nepostojecu kolonu ───────────────────────────────
def test_cuvanje_ne_gadja_nepostojece_kolone():
    """Jedini razlog zasto je 500 uopste primecen."""
    odgovor, _ = _sacuvaj({"predmeti": [PREDMET],
                           "predmet_beleske": [{"id": "b1"}]})
    assert odgovor["ok"] is True


def test_upisuje_se_sadrzaj_a_ne_tekst_ni_tip():
    _, supa = _sacuvaj({"predmeti": [PREDMET], "predmet_beleske": [{"id": "b1"}]})
    kolone = [k for (t, k) in supa._dnevnik["kolone"] if t == "predmet_beleske"]
    assert "tekst" not in kolone, kolone
    assert "tip" not in kolone, kolone


# ── 2. Sadrzaj ───────────────────────────────────────────────────────────────
def test_sadrzaj_nosi_naziv_i_tekst_bez_ukrasa():
    zapisi = {}

    def _uhvati(sema, redovi=None, greske=None):
        real = napravi_supa(sema, redovi, greske)
        pravi_table = real.table.side_effect

        def _table(ime):
            upit = pravi_table(ime)
            if ime == "predmet_beleske":
                orig_insert = upit.insert

                def insert(podaci, *a, **k):
                    zapisi.update(podaci or {})
                    return orig_insert(podaci, *a, **k)
                upit.insert = insert
            return upit
        real.table.side_effect = _table
        return real

    supa = _uhvati(SEMA, {"predmeti": [PREDMET], "predmet_beleske": [{"id": "b1"}]})
    with patch.object(DT, "_get_supa", return_value=supa):
        asyncio.run(DT.sacuvaj_dokument(
            request=_lazni_request(),
            req=_Req(naziv="Tužba za naknadu", sadrzaj="Telo dokumenta."),
            user={"user_id": UID}))

    assert "sadrzaj" in zapisi, zapisi
    assert "tekst" not in zapisi and "tip" not in zapisi, zapisi
    assert "Tužba za naknadu" in zapisi["sadrzaj"]
    assert "Telo dokumenta." in zapisi["sadrzaj"]
    # Ukrasna ikonica bi zavrsila U BAZI, ne samo na ekranu.
    assert "📄" not in zapisi["sadrzaj"], zapisi["sadrzaj"]


# ── 3. Vlasnistvo ────────────────────────────────────────────────────────────
def test_tudji_predmet_daje_404_a_ne_tihi_upis():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ex:
        _sacuvaj({"predmeti": [], "predmet_beleske": []})
    assert ex.value.status_code == 404


# ── 4. META — laznjak stvarno puca ───────────────────────────────────────────
@pytest.mark.parametrize("kolona", ["tekst", "tip"])
def test_meta_laznjak_puca_na_nepostojecu_kolonu(kolona):
    """Bez ovoga ceo fajl moze biti prazan: dokaz da bi PRE-STATE pao."""
    supa = napravi_supa(SEMA, {"predmet_beleske": []})
    with pytest.raises(Drift42703):
        supa.table("predmet_beleske").select(kolona).execute()


def test_meta_laznjak_propusta_sadrzaj():
    supa = napravi_supa(SEMA, {"predmet_beleske": [{"id": "b1", "sadrzaj": "x"}]})
    r = supa.table("predmet_beleske").select("sadrzaj").execute()
    assert r.data == [{"id": "b1", "sadrzaj": "x"}]

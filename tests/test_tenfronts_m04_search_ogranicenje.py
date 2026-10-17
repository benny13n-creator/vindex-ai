# -*- coding: utf-8 -*-
"""TENFRONTS-M04 — ograničena pretraga ne sme da se predstavi kao potpuna.

`_get_user_predmet_ids` vraća najviše 500 predmeta, a hronologija/beleške/komentari pretražuju samo
prvih 200 (`in_(predmet_id, pids[:200])`). Kad korisnik ima više od 200 predmeta, deo njegovih
podataka se ne pretražuje; odgovor to mora da kaže kroz postojeći `nepotpuno` (bez neograničenih upita)."""
import asyncio
import os
import re
from unittest.mock import patch

import pytest

import routers.search as S
from tests._schema_fake import napravi_supa
from tests.test_tenfronts_m03_search_komentari import SEMA, UID_A, _lazni_request

PO_PREDMETIMA = ("hronologija", "beleske", "komentari")


def _baza(n, trazeni_poslednji=True):
    predmeti = [{"id": "p%04d" % i, "user_id": UID_A, "naziv": "Predmet %d" % i, "opis": "", "status": "aktivan"}
                for i in range(n)]
    cilj = predmeti[-1]["id"] if (n and trazeni_poslednji) else (predmeti[0]["id"] if n else "nema")
    return {
        "predmeti": predmeti,
        "predmet_hronologija": [{"id": "h1", "predmet_id": cilj, "dogadjaj": "ZASTARELOST rok", "datum_iso": "2026-11-01",
                                 "vaznost": "važan", "user_id": UID_A}],
        "predmet_beleske": [{"id": "n1", "predmet_id": cilj, "sadrzaj": "ZASTARELOST beleška", "created_at": "2026-10-01",
                             "user_id": UID_A}],
        "predmet_komentari": [{"id": "k1", "predmet_id": cilj, "user_id": UID_A, "tekst": "ZASTARELOST komentar",
                               "kreirano": "2026-10-01T00:00:00+00:00"}],
    }


def _pretrazi(n, vrste=",".join(PO_PREDMETIMA), **kw):
    supa = napravi_supa(SEMA, redovi=_baza(n, **kw))
    with patch.object(S, "_get_supa", return_value=supa):
        rez = asyncio.run(S.global_search(request=_lazni_request(), q="ZASTARELOST", vrste=vrste, limit=5,
                                          user={"user_id": UID_A}))
    return rez, supa


@pytest.mark.parametrize("n", [0, 1, 199, 200])
def test_do_200_predmeta_pretraga_je_potpuna_i_tako_se_i_kaze(n):
    rez, _ = _pretrazi(n)
    assert "nepotpuno" not in rez
    if n:
        assert all(len(rez[v]) == 1 for v in PO_PREDMETIMA)


@pytest.mark.parametrize("n", [201, 499, 500, 501])
def test_preko_200_predmeta_delimicna_pretraga_je_oznacena(n):
    rez, _ = _pretrazi(n)                       # cilj je u POSLEDNJEM predmetu — van pretraženih 200
    assert all(rez[v] == [] for v in PO_PREDMETIMA)
    assert sorted(rez.get("nepotpuno", [])) == sorted(PO_PREDMETIMA), rez


@pytest.mark.parametrize("n", [201, 501])
def test_oznaka_i_kad_je_rezultat_pronadjen_u_pretrazenom_delu(n):
    rez, _ = _pretrazi(n, trazeni_poslednji=False)
    assert all(len(rez[v]) == 1 for v in PO_PREDMETIMA)
    assert sorted(rez["nepotpuno"]) == sorted(PO_PREDMETIMA)


def test_oznaka_samo_za_trazene_vrste():
    rez, _ = _pretrazi(250, vrste="beleske,predmeti")
    assert rez["nepotpuno"] == ["beleske"]


def test_predmeti_dokumenti_nisu_pogodjeni_ogranicenjem():
    rez, _ = _pretrazi(250, vrste="predmeti,dokumenti")
    assert "nepotpuno" not in rez


def test_upiti_ostaju_ograniceni():
    _, supa = _pretrazi(501)
    # bez N+1: jedan upit za skup predmeta + (NS3-N12) jedan konstantan upit za predmete u brisanju
    # (šema ovog testa je pre migracije 114: upit za tombstone se odbija na koloni, pa je skup prazan)
    assert supa._dnevnik["tabele"].count("predmeti") == 2
    assert [k for t, k in supa._dnevnik["select"] if t == "predmeti"] == ["id"]
    import inspect
    src = inspect.getsource(S)
    assert ".limit(500)" in src and "pids[:_MAX_PREDMETA_PO_UPITU]" in src


def test_poruke_ui_ne_tvrde_da_nista_nije_pretrazeno():
    koren = os.path.join(os.path.dirname(__file__), "..")
    v2 = open(os.path.join(koren, "frontend-v2-ng", "src", "pretraga.js"), encoding="utf-8").read()
    legacy = open(os.path.join(koren, "static", "vindex.js"), encoding="utf-8").read()
    assert "nije u potpunosti pretraženo" in v2 and "nije pretraženo —" not in v2
    assert "⚠ Deo pretrage nije potpun (" in legacy and "⚠ Deo pretrage nije uspeo (" not in legacy

# -*- coding: utf-8 -*-
"""TENFRONTS-M03 — globalna pretraga obuhvata timske komentare (`predmet_komentari`, LD-006).

Granica vidljivosti je ista kao u `routers/komentari.py::get_komentari`: komentare predmeta vidi samo
vlasnik predmeta (`predmeti.user_id = uid`). Pretraga zato ide kroz `_get_user_predmet_ids` — isti
skup predmeta koji već ograničava hronologiju i beleške. Beleške (`predmet_beleske`) su drugi tip i
njihova vidljivost se ne menja. Kolone: supabase_setup.sql:553 (`tekst`, `kreirano`)."""
import asyncio
import os
import re
from unittest.mock import patch

import pytest

import routers.search as S
from tests._schema_fake import napravi_supa
from tests.test_bu002_search_schema_contract import SEMA as _SEMA_BU002, UID_A, UID_B, _lazni_request

SEMA = {**_SEMA_BU002,
        "predmet_komentari": {"id", "predmet_id", "user_id", "tekst", "kreirano", "izmenjeno"}}

P_A, P_B = "pa-1", "pb-1"
PREDMETI = [{"id": P_A, "user_id": UID_A, "naziv": "Parnica A", "opis": "", "status": "aktivan"},
            {"id": P_B, "user_id": UID_B, "naziv": "Parnica B", "opis": "", "status": "aktivan"}]
KOM_A = {"id": "k-a", "predmet_id": P_A, "user_id": UID_A, "tekst": "Proveriti VEŠTAČENJE pre ročišta",
         "kreirano": "2026-10-01T09:00:00+00:00"}
KOM_B = {"id": "k-b", "predmet_id": P_B, "user_id": UID_B, "tekst": "VEŠTAČENJE tuđe kancelarije",
         "kreirano": "2026-10-02T09:00:00+00:00"}
# anomalija podataka: red sa A-ovim user_id na B-ovom predmetu — vlasništvo predmeta odlučuje, ne autor
KOM_ANOM = {"id": "k-x", "predmet_id": P_B, "user_id": UID_A, "tekst": "VEŠTAČENJE na tuđem predmetu",
            "kreirano": "2026-10-03T09:00:00+00:00"}
BEL_B = {"id": "n-b", "predmet_id": P_B, "user_id": UID_B, "sadrzaj": "VEŠTAČENJE privatna beleška B",
         "created_at": "2026-10-01"}


def _pretrazi(q="VEŠTAČENJE", uid=UID_A, vrste=None, redovi=None, greske=None, limit=5):
    redovi = redovi if redovi is not None else {
        "predmeti": PREDMETI, "predmet_komentari": [KOM_A, KOM_B, KOM_ANOM], "predmet_beleske": [BEL_B]}
    supa = napravi_supa(SEMA, redovi=redovi, greske=greske)
    with patch.object(S, "_get_supa", return_value=supa):
        rez = asyncio.run(S.global_search(request=_lazni_request(), q=q, vrste=vrste, limit=limit,
                                          user={"user_id": uid}))
    return rez, supa


def _ids(rez, kljuc="komentari"):
    return [x["id"] for x in rez.get(kljuc) or []]


def test_sopstveni_komentar_se_nalazi_samo_kad_se_trazi_kategorija():
    rez, _ = _pretrazi(vrste="komentari")
    assert _ids(rez) == ["k-a"]
    assert rez["komentari"][0]["meta"]["predmet_id"] == P_A
    assert rez["komentari"][0]["tip"] == "komentar"
    assert "nepotpuno" not in rez and rez["ukupno"] == 1


def test_podrazumevana_pretraga_obuhvata_komentare():
    rez, _ = _pretrazi()
    assert "k-a" in _ids(rez)


def test_komentar_na_tudjem_predmetu_se_ne_nalazi_cak_ni_sa_mojim_user_id():
    rez, _ = _pretrazi(vrste="komentari")
    assert "k-b" not in _ids(rez) and "k-x" not in _ids(rez)


def test_druga_kancelarija_vidi_samo_svoje():
    rez, _ = _pretrazi(uid=UID_B, vrste="komentari")
    assert set(_ids(rez)) == {"k-b", "k-x"}            # isto kao GET /predmeti/{P_B}/komentari za vlasnika B
    assert "k-a" not in _ids(rez)


def test_privatne_beleske_nisu_prosirene():
    rez, _ = _pretrazi(vrste="komentari,beleske")
    assert _ids(rez, "beleske") == [] and "k-b" not in _ids(rez)


def test_upit_ide_samo_kroz_predmete_pozivaoca():
    _, supa = _pretrazi(vrste="komentari")
    assert ("predmeti", "user_id", UID_A) in supa._dnevnik["eq"]
    assert "predmet_komentari" in supa._dnevnik["tabele"]


def test_bez_predmeta_nema_upita_nad_komentarima():
    rez, supa = _pretrazi(vrste="komentari", redovi={"predmeti": [], "predmet_komentari": [KOM_A]})
    assert _ids(rez) == [] and "predmet_komentari" not in supa._dnevnik["tabele"]


@pytest.mark.parametrize("q", ["%VEŠ%", "VEŠTAČENJE,user_id.neq.x", "VEŠTAČENJE)", "'; drop table x; --"])
def test_poseban_unos_ne_menja_granicu(q):
    rez, _ = _pretrazi(q=q, vrste="komentari")
    assert set(_ids(rez)) <= {"k-a"}


def test_pad_izvora_je_nepotpuno_ne_prazan_uspeh():
    rez, _ = _pretrazi(vrste="komentari", greske={"predmet_komentari": TimeoutError("timeout")})
    assert rez["komentari"] == [] and rez["nepotpuno"] == ["komentari"]


def test_limit_vazi_za_komentare():
    mnogo = [{**KOM_A, "id": "k%d" % i} for i in range(12)]
    rez, _ = _pretrazi(vrste="komentari", limit=3,
                       redovi={"predmeti": PREDMETI, "predmet_komentari": mnogo})
    assert len(rez["komentari"]) == 3


def test_stari_ui_trazi_i_prikazuje_komentare():
    """Postojeća paleta (⌘K) bira kategorije iz fiksnih lista — bez njih bi API rezultat bio nevidljiv."""
    koren = os.path.join(os.path.dirname(__file__), "..")
    js = open(os.path.join(koren, "static", "vindex.js"), encoding="utf-8").read()
    html = open(os.path.join(koren, "index.html"), encoding="utf-8").read()
    assert re.search(r"var _cmdkVrste\s*=\s*'[^']*\bkomentari\b", js)
    assert re.search(r"var _CMDK_ORDER\s*=\s*\[[^\]]*'komentari'", js)
    assert re.search(r"var _CMDK_TIP_MAP\s*=\s*\{[^}]*komentari:'komentar'", js)
    assert re.search(r"komentar:\s*\{bg:", js)
    sve = re.search(r'data-vrste="([^"]+)" onclick="cmdkSetFilter\(this\)">Sve<', html).group(1)
    assert "komentari" in sve.split(",")

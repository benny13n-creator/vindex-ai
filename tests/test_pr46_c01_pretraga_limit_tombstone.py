# -*- coding: utf-8 -*-
"""PR #46 C01 — N12 filtrira predmete u brisanju POSLE `.limit(limit)` u bazi.

Kontraprimer: limit = 1, dva pogotka; prvi koji baza vrati je u brisanju, drugi je živ i pripada pozivaocu.
Baza vrati samo prvi, filter ga ukloni → odgovor kaže „nema predmeta“, bez oznake `nepotpuno`. Advokat bi
zaključio da živ predmet ne postoji. Isto za dokumente (i ostale vrste vezane za predmet).

Ugovor posle ispravke: ili je živ pogodak nađen, ili je vrsta označena u `nepotpuno` — nikad tiho „0“.
Stvarni `global_search`; baza u memoriji (`tests/_schema_fake.py`) koja primenjuje filtere pa `limit` redom upisa."""
import asyncio
from unittest.mock import patch

import pytest

import routers.search as S
from tests._schema_fake import napravi_supa
from tests.test_ns3_n12_pretraga_tombstone import SEMA, Q, UID_A, UID_B, _lazni_request

P_BRIS, P_ZIV, P_TUDJ = "p-bris", "p-ziv", "p-tudj"
BRIS = "2026-10-17T10:00:00+00:00"


def _pred(i, uid=UID_A, bris=None):
    return {"id": i, "user_id": uid, "naziv": f"{Q} predmet {i}", "opis": "", "status": "aktivan", "tip": "radno",
            "brisanje_zapoceto": bris}


def _dok(i, pid, uid=UID_A):
    return {"id": i, "predmet_id": pid, "user_id": uid, "naziv_fajla": f"{i}.pdf", "status": "indeksirano",
            "tekst_sadrzaj": f"{Q} tekst", "tip_dokaza": "", "created_at": "2026-10-01"}


def _redovi(n_bris=1):
    bris = [_pred(f"{P_BRIS}{k}", bris=BRIS) for k in range(n_bris)]
    return {
        # redosled = redosled kojim baza vraća: predmeti u brisanju PRE živog
        "predmeti": bris + [_pred(P_ZIV), _pred(P_TUDJ, uid=UID_B)],
        "predmet_dokumenti": [_dok(f"d-bris{k}", f"{P_BRIS}{k}") for k in range(n_bris)]
                             + [_dok("d-ziv", P_ZIV), _dok("d-tudj", P_TUDJ, uid=UID_B)],
        "predmet_hronologija": [{"id": f"h-bris{k}", "predmet_id": f"{P_BRIS}{k}", "dogadjaj": f"{Q} uručen",
                                 "datum_iso": "2026-10-01", "vaznost": "važan"} for k in range(n_bris)]
                               + [{"id": "h-ziv", "predmet_id": P_ZIV, "dogadjaj": f"{Q} uručen",
                                   "datum_iso": "2026-10-01", "vaznost": "važan"}],
    }


def _pretrazi(vrste, limit=1, n_bris=1, uid=UID_A):
    supa = napravi_supa(SEMA, redovi=_redovi(n_bris))
    with patch.object(S, "_get_supa", return_value=supa):
        return asyncio.run(S.global_search(request=_lazni_request(), q=Q, vrste=vrste, limit=limit,
                                           user={"user_id": uid}))


def _ids(rez, tip):
    return [x["id"] for x in rez.get(tip) or []]


@pytest.mark.parametrize("tip,ziv", [("predmeti", P_ZIV), ("dokumenti", "d-ziv"), ("hronologija", "h-ziv")])
def test_limit_1_ziv_pogodak_nije_tiho_izgubljen(tip, ziv):
    rez = _pretrazi(tip)
    nadjen = ziv in _ids(rez, tip)
    oznaceno = tip in (rez.get("nepotpuno") or [])
    assert nadjen or oznaceno, f"{tip}: živ pogodak izgubljen iza predmeta u brisanju, bez oznake nepotpuno"


@pytest.mark.parametrize("tip,ziv", [("predmeti", P_ZIV), ("hronologija", "h-ziv")])
def test_predmet_i_vrste_po_predmetu_nalaze_ziv_pogodak(tip, ziv):
    """Za predmete i vrste koje idu kroz listu predmeta isključenje je tačno (ne samo oznaka)."""
    rez = _pretrazi(tip, n_bris=3)
    assert _ids(rez, tip) == [ziv] and tip not in (rez.get("nepotpuno") or [])


@pytest.mark.parametrize("limit", [1, 2, 5, 10])
def test_nista_iz_predmeta_u_brisanju_i_limit_postovan(limit):
    rez = _pretrazi(None, limit=limit, n_bris=3)
    for tip in S._VALID_VRSTE:
        stavke = rez.get(tip) or []
        assert len(stavke) <= limit
        for x in stavke:
            pid = x["id"] if x.get("tip") == "predmet" else (x.get("meta") or {}).get("predmet_id")
            assert not str(pid).startswith(P_BRIS), f"{tip}: prikazan zapis predmeta u brisanju"
            assert pid != P_TUDJ


def test_bez_predmeta_u_brisanju_nema_lazne_oznake():
    rez = _pretrazi(None, limit=1, n_bris=0)
    assert "nepotpuno" not in rez
    assert _ids(rez, "predmeti") == [P_ZIV]


def test_tudji_predmet_u_brisanju_ne_utice_na_pozivaoca():
    rez = _pretrazi("predmeti", limit=1, uid=UID_B)
    assert _ids(rez, "predmeti") == [P_TUDJ] and "nepotpuno" not in rez

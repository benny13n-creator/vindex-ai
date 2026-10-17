# -*- coding: utf-8 -*-
"""NS3-N12 — globalna pretraga ne sme da prikaže predmet u brisanju (BETA-DEL-001) ni ništa iz njega.

Ugovor već postoji: predmet sa `brisanje_zapoceto` se „ponaša kao da ne postoji“ — `get_predmet` vraća 404
(`api.py::_je_u_brisanju`), RAG ga isključuje (`shared/rag_acl.py`), email podsetnici ga preskaču. Tombstone ostaje
dok se brisanje ne završi (i posle delimičnog neuspeha, do ponovnog pokušaja). `/api/search` to nije poštovao:
predmet, tekst dokumenata, hronologija, beleške i komentari takvog predmeta su se i dalje nalazili, a klik je
vodio na 404.

Stvarni `global_search`; baza u memoriji (`tests/_schema_fake.py`) sa kolonom `brisanje_zapoceto`."""
import asyncio
from unittest.mock import patch

import routers.search as S
from tests._schema_fake import napravi_supa
from tests.test_bu002_search_schema_contract import SEMA as _SEMA, UID_A, UID_B, _lazni_request

SEMA = {**_SEMA,
        "predmeti": set(_SEMA["predmeti"]) | {"brisanje_zapoceto"},
        "predmet_komentari": {"id", "predmet_id", "user_id", "tekst", "kreirano"}}
Q = "OTKAZ"
P_ZIV, P_BRIS, P_TUDJ = "p-ziv", "p-bris", "p-tudj"


def _redovi():
    def pred(i, uid, bris):
        return {"id": i, "user_id": uid, "naziv": f"{Q} predmet {i}", "opis": "", "status": "aktivan", "tip": "radno",
                "brisanje_zapoceto": "2026-10-17T10:00:00+00:00" if bris else None}

    def dok(i, pid, uid):
        return {"id": i, "predmet_id": pid, "user_id": uid, "naziv_fajla": f"{i}.pdf", "status": "indeksirano",
                "tekst_sadrzaj": f"Rešenje o {Q}U zaposlenog", "tip_dokaza": "sudska_odluka", "created_at": "2026-10-01"}
    return {
        "predmeti": [pred(P_ZIV, UID_A, False), pred(P_BRIS, UID_A, True), pred(P_TUDJ, UID_B, False)],
        "predmet_dokumenti": [dok("d-ziv", P_ZIV, UID_A), dok("d-bris", P_BRIS, UID_A), dok("d-tudj", P_TUDJ, UID_B)],
        "predmet_hronologija": [
            {"id": "h-ziv", "predmet_id": P_ZIV, "dogadjaj": f"{Q} uručen", "datum_iso": "2026-10-01", "vaznost": "važan"},
            {"id": "h-bris", "predmet_id": P_BRIS, "dogadjaj": f"{Q} uručen", "datum_iso": "2026-10-01", "vaznost": "važan"}],
        "predmet_beleske": [
            {"id": "b-bris", "predmet_id": P_BRIS, "sadrzaj": f"{Q} — beleška", "created_at": "2026-10-01"}],
        "predmet_komentari": [
            {"id": "k-bris", "predmet_id": P_BRIS, "user_id": UID_A, "tekst": f"{Q} komentar", "kreirano": "2026-10-01"}],
    }


def _pretrazi(uid=UID_A, sema=SEMA, greske=None, redovi=None):
    supa = napravi_supa(sema, redovi=redovi or _redovi(), greske=greske)
    with patch.object(S, "_get_supa", return_value=supa):
        return asyncio.run(S.global_search(request=_lazni_request(), q=Q, vrste=None, limit=10, user={"user_id": uid}))


def _sve_vezano_za(rez, pid):
    out = []
    for tip in ("predmeti", "dokumenti", "hronologija", "beleske", "komentari", "billing", "zadaci"):
        for x in rez.get(tip) or []:
            if (x.get("tip") == "predmet" and x.get("id") == pid) or (x.get("meta") or {}).get("predmet_id") == pid:
                out.append((tip, x["id"]))
    return out


def test_predmet_u_brisanju_i_sve_iz_njega_nestaje_iz_pretrage():
    rez = _pretrazi()
    assert _sve_vezano_za(rez, P_BRIS) == [], "pretraga prikazuje predmet u brisanju"


def test_ziv_predmet_i_dalje_nadjen_u_svim_vrstama():
    rez = _pretrazi()
    nadjeno = _sve_vezano_za(rez, P_ZIV)
    assert ("predmeti", P_ZIV) in nadjeno and ("dokumenti", "d-ziv") in nadjeno and ("hronologija", "h-ziv") in nadjeno
    assert "nepotpuno" not in rez
    assert rez["ukupno"] == sum(len(rez.get(t) or []) for t in S._VALID_VRSTE)


def test_tudji_podaci_se_i_dalje_ne_vide():
    rez = _pretrazi()
    assert _sve_vezano_za(rez, P_TUDJ) == []


def test_bez_kolone_114_pretraga_radi_kao_ranije():
    sema = {**SEMA, "predmeti": set(_SEMA["predmeti"])}
    redovi = _redovi()
    for p in redovi["predmeti"]:
        p.pop("brisanje_zapoceto")
    rez = _pretrazi(sema=sema, redovi=redovi)
    assert ("predmeti", P_BRIS) in _sve_vezano_za(rez, P_BRIS)          # bez kolone tombstone ne može postojati
    assert "nepotpuno" not in rez


def test_pad_provere_brisanja_ne_otkriva_nista_vezano_za_predmete():
    class _Pad(Exception):
        pass
    import tests._schema_fake as sf
    orig = sf._Upit.execute
    pozivi = {"n": 0}

    def _execute(self):
        if self._t == "predmeti" and any("brisanje_zapoceto" in str(k) for k in self._d["kolone"][-3:]):
            pozivi["n"] += 1
            raise _Pad("timeout")
        return orig(self)
    with patch.object(sf._Upit, "execute", _execute):
        rez = _pretrazi()
    assert pozivi["n"] >= 1
    assert _sve_vezano_za(rez, P_BRIS) == [] and _sve_vezano_za(rez, P_ZIV) == []
    assert set(rez["nepotpuno"]) >= {"predmeti", "dokumenti", "hronologija"}

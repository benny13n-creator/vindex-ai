# -*- coding: utf-8 -*-
"""NS3-N11 — legacy „Intelligence Timeline“ mora razlikovati rok koji čeka odluku advokata od potvrđenog i odbijenog.

`routers/intelligence_timeline.py` je redove `predmet_hronologija` vraćao bez identiteta, vrste i stanja odluke:
AI predlog roka koji advokat nikad nije video izgledao je isto kao rok koji je sam uneo i potvrdio, a odbijen rok
kao važeći. Kanonski obrazac već postoji (`api.py` workspace ruta, V2 `rad-predmeta.js`, NS2-A2/N03-FD8): SAMO red
izjavljen kao rok (`vrsta='rok'`, migracija 129) dobija `stanje_odluke` iz STROGO pročitanog lanca odluka; pad
čitanja = `UNKNOWN`, nikad tiho UNCONFIRMED. Oznake su iste kao u V2.

Stvarni handler; Supabase je lažna baza u memoriji; lanac odluka je zamenjen."""
import asyncio
from unittest.mock import patch

import pytest

import routers.intelligence_timeline as itl
from tests._schema_fake import napravi_supa

UID, PID = "u-1", "p-1"
R_AI, R_POTV, R_ODB, DOGADJAJ = "r-ai", "r-potv", "r-odb", "h-ev"


def _redovi(vrsta=True):
    def red(i, dog, izvor, v):
        r = {"id": i, "predmet_id": PID, "user_id": UID, "dogadjaj": dog, "akter": "x", "datum": "2026-11-02",
             "datum_iso": "2026-11-02", "vaznost": "kritičan", "izvor": izvor}
        if vrsta:
            r["vrsta"] = v
        return r
    return [red(R_AI, "Rok za odgovor na tužbu", "AI_AUTONOMOUS", "rok"),
            red(R_POTV, "Rok za žalbu", "HUMAN_DIRECT", "rok"),
            red(R_ODB, "Rok za dopunu", "AI_ASSISTED", "rok"),
            red(DOGADJAJ, "Dostavljeno rešenje", "HUMAN_DIRECT", None)]


def _pokreni(odluke=None, odluke_puca=False, vrsta=True, tudji=False):
    supa = napravi_supa({}, redovi={
        "predmeti": [{"id": PID, "user_id": "drugi" if tudji else UID, "naziv": "P", "created_at": "2026-10-01"}],
        "predmet_hronologija": _redovi(vrsta),
    })

    def _odl(ids, strogo=False):
        if odluke_puca:
            raise RuntimeError("audit lanac nedostupan")
        return {k: v for k, v in (odluke or {}).items() if k in set(ids)}
    with patch.object(itl, "_get_supa", return_value=supa), \
         patch("shared.rok_potvrda.odluke", _odl), \
         patch("shared.rokovi._sema_ima_129", return_value=vrsta):
        rez = asyncio.run(itl.intelligence_timeline(PID, user={"user_id": UID}))
    return {e["naslov"]: e for e in rez["events"] if e["tip"] == "hronologija"}, rez


ODLUKE = {R_POTV: "CONFIRMED", R_ODB: "REJECTED"}


def test_rok_koji_ceka_odluku_je_oznacen():
    ev, _ = _pokreni(ODLUKE)
    assert ev["Rok za odgovor na tužbu"]["stanje_odluke"] == "UNCONFIRMED"
    assert ev["Rok za odgovor na tužbu"]["badge"] == "rok — čeka vašu odluku"


def test_potvrdjen_i_odbijen_rok_se_razlikuju():
    ev, _ = _pokreni(ODLUKE)
    assert ev["Rok za žalbu"]["stanje_odluke"] == "CONFIRMED" and ev["Rok za žalbu"]["badge"] == "rok — potvrđen"
    assert ev["Rok za dopunu"]["stanje_odluke"] == "REJECTED" and ev["Rok za dopunu"]["badge"] == "rok — odbijen"


def test_dogadjaj_koji_nije_rok_nema_stanje_odluke():
    ev, _ = _pokreni(ODLUKE)
    assert "stanje_odluke" not in ev["Dostavljeno rešenje"] and "badge" not in ev["Dostavljeno rešenje"]


def test_pad_citanja_odluka_je_nepoznato_a_ne_ceka():
    ev, rez = _pokreni(odluke_puca=True)
    assert {ev[n]["stanje_odluke"] for n in ("Rok za odgovor na tužbu", "Rok za žalbu", "Rok za dopunu")} == {"UNKNOWN"}
    assert ev["Rok za žalbu"]["badge"] == "rok — stanje odluke trenutno nije poznato"
    assert "odluke_o_rokovima" in rez["degraded_sources"]
    assert len(ev) == 4                                     # hronologija se i dalje vraća


def test_bez_kolone_vrsta_nista_se_ne_pogadja():
    ev, rez = _pokreni(ODLUKE, vrsta=False)
    assert all("stanje_odluke" not in e for e in ev.values()) and len(ev) == 4
    assert "hronologija" not in rez["degraded_sources"]


def test_tudji_predmet_404():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _pokreni(ODLUKE, tudji=True)
    assert e.value.status_code == 404

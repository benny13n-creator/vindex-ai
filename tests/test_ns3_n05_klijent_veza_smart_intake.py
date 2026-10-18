# -*- coding: utf-8 -*-
"""NS3-N05 — Smart Intake finalize ne sme da kaže „klijent povezan“ kada veza nije upisana.

`routers/smart_intake.py::finalize_intake_job` je vraćao `klijent_dodat = bool(klijent_ime) and not
klijent_nesiguran` — bez obzira da li su upis klijenta i upis `predmet_klijenti` uspeli (oba su u `try`-u
označenom kao non-fatal). V2 (`frontend-v2-ng/src/prijem-predmeta.js`) tada prikazuje „Klijent iz dokumenta je
povezan sa predmetom.“ uz predmet bez veze. Tok „opis prvo“ (`routers/intake.py::intake_kreiraj`) taj slučaj već
tretira kao neuspeh; ovde je ugovor samo da odgovor kaže istinu (finalize ostaje non-fatal za vezu).

Stvarni handler; baza i spoljne zavisnosti iz harness-a `tests/test_n03_deadline_gates.py`."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from routers.smart_intake import FinalizeReq
from tests.test_n03_deadline_gates import _UID, _dok, _ent, _finalize, _supa

IME = "Marko Marković"


def _pokreni(ishod, veza_puca=False, klijent_bez_reda=False, resolver_puca=False):
    supa = _supa()
    zapisane_veze, novi_klijenti = [], []
    _orig = supa.table.side_effect

    def _table(ime):
        t = _orig(ime)
        if ime == "predmet_klijenti":
            def _ins(red):
                if veza_puca:
                    raise RuntimeError("predmet_klijenti insert 503")
                zapisane_veze.append(red)
                m = type("M", (), {})()
                m.execute = lambda: type("R", (), {"data": [red]})()
                return m
            t.insert.side_effect = _ins
        elif ime == "klijenti":
            def _ins_k(red):
                novi_klijenti.append(red)
                m = type("M", (), {})()
                m.execute = lambda: type("R", (), {"data": [] if klijent_bez_reda else [{"id": "kl-novi"}]})()
                return m
            t.insert.side_effect = _ins_k
        return t
    supa.table.side_effect = _table

    resolver = AsyncMock(side_effect=RuntimeError("db down")) if resolver_puca else AsyncMock(return_value=ishod)
    with patch("shared.case_assimilation.resolve_client_ownership", resolver):
        rez = asyncio.run(_finalize(supa, [_dok([_ent("plaintiff", IME, 0.95, reviewed=True)], tip="lawsuit")],
                                    body=FinalizeReq(klijent_strana="plaintiff")))
    return rez, zapisane_veze, novi_klijenti, resolver


NOVI = {"outcome": "create_new", "ime": "Marko", "prezime": "Marković", "firma": None, "tip": "fizicko_lice"}
POSTOJECI = {"outcome": "match", "klijent_id": "kl-postojeci"}


def test_novi_klijent_povezan_kad_je_veza_upisana():
    rez, veze, novi, resolver = _pokreni(NOVI)
    assert rez["klijent_dodat"] is True
    assert veze == [{"predmet_id": "pred-001", "klijent_id": "kl-novi", "uloga_klijenta": "stranka"}]
    assert novi and novi[0]["user_id"] == _UID
    assert resolver.await_args.args == (_UID, IME)                  # traži samo u klijentima pozivaoca


def test_postojeci_klijent_povezan_bez_novog_reda():
    rez, veze, novi, _ = _pokreni(POSTOJECI)
    assert rez["klijent_dodat"] is True and novi == []
    assert [v["klijent_id"] for v in veze] == ["kl-postojeci"]


@pytest.mark.parametrize("ishod", [NOVI, POSTOJECI], ids=["novi", "postojeci"])
def test_pad_upisa_veze_nije_povezan_klijent(ishod):
    rez, veze, _, _ = _pokreni(ishod, veza_puca=True)
    assert veze == []
    assert rez["klijent_dodat"] is False, "odgovor tvrdi vezu koja nije upisana"
    assert rez["predmet_id"] == "pred-001"                           # finalize i dalje non-fatal za vezu


def test_upis_klijenta_bez_reda_nije_povezan_klijent():
    rez, veze, _, _ = _pokreni(NOVI, klijent_bez_reda=True)
    assert veze == [] and rez["klijent_dodat"] is False


def test_pad_razresavanja_vlasnistva_nije_povezan_klijent():
    rez, veze, novi, _ = _pokreni(NOVI, resolver_puca=True)
    assert veze == [] and novi == [] and rez["klijent_dodat"] is False


def test_nejednoznacan_klijent_ostaje_nepovezan_i_nesiguran():
    rez, veze, novi, _ = _pokreni({"outcome": "ambiguous", "candidates": [{"id": "k1"}, {"id": "k2"}]})
    assert veze == [] and novi == []
    assert rez["klijent_dodat"] is False and rez["klijent_nesiguran"] is True
    assert rez["klijent_kandidati"] == ["k1", "k2"]


def test_coi_dogadjaj_ostaje_bezuslovan_kad_veza_padne():
    """Postojeće ponašanje (S6/Delta 002): NEW_CLIENT_LINKED se upisuje i kad veza padne — ne menja se."""
    rez, _, _, _ = _pokreni(NOVI, veza_puca=True)
    assert rez["coi_status"] == "COI_PENDING"

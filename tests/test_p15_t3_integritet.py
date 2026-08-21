# -*- coding: utf-8 -*-
"""
P1-5 §T3 — adversarijalna forenzika integriteta nad rutom `DELETE /api/predmeti/{id}`.

T2 je dokazao domensku logiku. T3 napada RUTU i pita:
  - da li audit DOKAZUJE sta se dogodilo (i kad operacija NIJE uspela)?
  - da li HTTP kod odgovara ishodu?
  - da li pad audita moze da preokrene vec izvrsenu operaciju?
  - da li ponovljeni/istovremeni DELETE moze dva puta prijaviti uspeh?

INVARIJANTA (mandat T3): ako `DELETE` prijavi SUCCESS, svaki podatak koji
politika nalaze da se ukloni mora biti uklonjen, svaki koji mora ostati mora
ostati, a audit mora dokazivati sta se dogodilo.
"""
import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import api as _api
from shared.predmet_deletion import IshodPredmeta, RezultatBrisanja

UID = "00000000-0000-0000-0000-000000000001"
PID = "p-1"
KORISNIK = {"user_id": UID, "email": "advokat@vindex.rs", "role": "advokat"}


def _pozovi(rez, audit_puca=False):
    """Vozi PRAVU rutu; domenska funkcija je zamenjena poznatim ishodom."""
    zapisi = []

    async def _audit(action, **kw):
        zapisi.append({"action": action, **kw})
        if audit_puca:
            raise RuntimeError("audit nedostupan")
        return "audit-1"

    fn = getattr(_api.predmet_obrisi, "__wrapped__", _api.predmet_obrisi)
    with patch.object(_api, "_get_supa", return_value=MagicMock()), \
         patch("shared.predmet_deletion.obrisi_predmet", return_value=rez), \
         patch("shared.audit_immutable.log_action", new=_audit):
        try:
            odgovor = asyncio.run(fn(predmet_id=PID, request=MagicMock(), user=KORISNIK))
            return odgovor, None, zapisi
        except Exception as exc:
            return None, exc, zapisi


ISHODI = [
    (IshodPredmeta.DELETED, None),
    (IshodPredmeta.ALREADY_ABSENT, 404),
    (IshodPredmeta.REFUSED, 403),
    (IshodPredmeta.BLOCKED, 409),
    # BETA-DEL-001: jedan `PARTIAL_FAILURE` razdvojen je u dva ishoda sa
    # suprotnim znacenjem za korisnika. Oba i dalje moraju upisati audit.
    (IshodPredmeta.RETRYABLE_FAILURE, 409),
    (IshodPredmeta.PERMANENT_FAILURE, 409),
]


@pytest.mark.parametrize("ishod,kod", ISHODI)
def test_audit_se_upisuje_za_SVAKI_ishod(ishod, kod):
    """I odbijeni i blokirani pokusaj su podatak od bezbednosnog znacaja."""
    odgovor, greska, zapisi = _pozovi(RezultatBrisanja(ishod, "razlog"))
    assert len(zapisi) == 1, "audit nije upisan za ishod %s" % ishod
    z = zapisi[0]
    assert z["action"] == "predmet_delete"
    assert z["resource_id"] == PID and z["user_id"] == UID
    assert z["metadata"]["ishod"] == ishod, "audit ne belezi STVARNI ishod"


@pytest.mark.parametrize("ishod,kod", ISHODI)
def test_http_kod_odgovara_ishodu(ishod, kod):
    odgovor, greska, _ = _pozovi(RezultatBrisanja(ishod, "razlog"))
    if kod is None:
        assert greska is None and odgovor["ok"] is True, ishod
    else:
        assert greska is not None and getattr(greska, "status_code", None) == kod, ishod
        assert odgovor is None


def test_samo_DELETED_daje_ok_true():
    """Nijedan drugi ishod ne sme proizvesti potvrdu brisanja."""
    for ishod, _ in ISHODI:
        odgovor, greska, _ = _pozovi(RezultatBrisanja(ishod))
        if ishod == IshodPredmeta.DELETED:
            continue
        assert odgovor is None, "ishod %s je vratio odgovor umesto greske" % ishod


def test_pad_audita_ne_preokrece_izvrsenu_operaciju():
    """Operacija je vec izvrsena; audit koji padne ne sme je pretvoriti u gresku,
    ali njegov izostanak mora biti vidljiv (logger.error u ruti)."""
    odgovor, greska, zapisi = _pozovi(
        RezultatBrisanja(IshodPredmeta.DELETED), audit_puca=True)
    assert greska is None and odgovor["ok"] is True
    assert len(zapisi) == 1


def test_ponovljeni_delete_ne_daje_dva_uspeha():
    """Prvi poziv brise, drugi mora biti 404 — nikad dva `ok:True`."""
    prvi, g1, _ = _pozovi(RezultatBrisanja(IshodPredmeta.DELETED))
    drugi, g2, _ = _pozovi(RezultatBrisanja(IshodPredmeta.ALREADY_ABSENT))
    assert prvi["ok"] is True and g1 is None
    assert drugi is None and getattr(g2, "status_code", None) == 404


def test_detalj_greske_nosi_masinski_citljiv_ishod():
    """Frontend mora moci da razlikuje sva tri neuspesna ishoda."""
    for ishod in (IshodPredmeta.BLOCKED, IshodPredmeta.RETRYABLE_FAILURE,
                  IshodPredmeta.PERMANENT_FAILURE):
        _, greska, _ = _pozovi(RezultatBrisanja(ishod, "razlog"))
        d = greska.detail
        assert isinstance(d, dict), ishod
        assert d["ishod"] == ishod
        assert d["uspeh"] is False
        assert "poruka" in d


def test_odgovor_pri_uspehu_nosi_dokaz_obima():
    """`ok:True` bez spiska ociscenog nije dokaz — mora se videti sta je uklonjeno."""
    rez = RezultatBrisanja(IshodPredmeta.DELETED)
    rez.obrisane_tabele = ["zadaci", "case_actions"]
    rez.vektori = "OBRISANI"
    odgovor, greska, _ = _pozovi(rez)
    assert greska is None
    assert odgovor["vektori"] == "OBRISANI"
    assert "zadaci" in odgovor["obrisane_tabele"]
    assert odgovor["neuspele_tabele"] == []

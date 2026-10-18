# -*- coding: utf-8 -*-
"""PR #46 C02 — delimičan uspeh onboarding-a / nedeljnog sažetka u dnevnom dispečeru.

Modul vrati `{"poslato": 3, "greske": 1}`: tri poruke su stvarno obrađene, jedna nije. N03 je ispravno učinio
neuspeh vidljivim (`status: greska`, `broj_gresaka` +1), ali je tri poslate prestao da broji u zbirnom
`stavke_obradjene` — zbir je tvrdio manje urađenog posla nego što je urađeno. Ustanovljeni obrazac je email
podsetnik u istom dispečeru (TENFRONTS-M01): validan nenegativan ceo `poslato` se broji UVEK, neuspeh odvojeno.

Stvarni `api.cron_daily` kroz TestClient, harness iz N03. Zbir se poredi sa kontrolnim pokretanjem
(`poslato 0, greske 0`) da doprinos ostalih modula harness-a ne utiče na tvrdnju."""
from unittest.mock import AsyncMock, patch

import pytest

from tests.test_ns3_n03_cron_ugnezdeni_neuspeh import (  # noqa: F401  (autouse fixture-i)
    KLJUC, MODULI, _bez_mreze, _patch_submodules, _patch_supa, _pokreni)


def _stavke(body):
    return body["heartbeat"]["stavke_obradjene"]


@pytest.mark.parametrize("modul", MODULI)
def test_delimican_uspeh_broji_poslate_i_ostaje_neuspeh(modul):
    kontrola, _ = _pokreni(modul, {"poslato": 0, "greske": 0})
    body, mock = _pokreni(modul, {"poslato": 3, "greske": 1})
    assert mock.await_count == 1                                            # bez ponavljanja
    assert body[KLJUC[modul]]["status"] == "greska"                          # neuspeh vidljiv
    assert body[KLJUC[modul]]["poslato"] == 3 and body[KLJUC[modul]]["greske"] == 1
    assert body["ok"] is False
    assert body["heartbeat"]["broj_gresaka"] == kontrola["heartbeat"]["broj_gresaka"] + 1
    assert _stavke(body) == _stavke(kontrola) + 3, "tri obrađene poruke nisu u zbirnom brojaču"


@pytest.mark.parametrize("modul", MODULI)
def test_potpun_uspeh_i_dalje_broji(modul):
    kontrola, _ = _pokreni(modul, {"poslato": 0, "greske": 0})
    body, _ = _pokreni(modul, {"poslato": 5, "greske": 0})
    assert body[KLJUC[modul]]["status"] == "ok" and _stavke(body) == _stavke(kontrola) + 5


@pytest.mark.parametrize("modul", MODULI)
@pytest.mark.parametrize("rez", [{"poslato": "3", "greske": 1}, {"poslato": True, "greske": 0},
                                 {"poslato": -2, "greske": 1}, {"greske": 1}, None, "ok"],
                         ids=["string", "bool", "negativno", "bez_poslato", "None", "tekst"])
def test_nevalidan_poslato_se_ne_broji(modul, rez):
    kontrola, _ = _pokreni(modul, {"poslato": 0, "greske": 0})
    body, _ = _pokreni(modul, rez)
    assert body[KLJUC[modul]]["status"] == "greska"
    assert _stavke(body) == _stavke(kontrola)

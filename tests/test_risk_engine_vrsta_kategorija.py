# -*- coding: utf-8 -*-
"""Risk Engine — vrsta dokumenta iz prijema/ljudske ispravke (engleska šifra iz
`shared/intake_classify.DOCUMENT_TYPES`) naspram kategorije iz `EXPECTED_DOCS`.

Ranije: dokument koji je advokat ispravno označio kao `appeal` davao je lažno
„Nedostaje podnesak stranke u spisu“ i na pragu od 3 nedostajuća podizao rizik
(Nizak/70 → Srednji/55). Mapiraju se samo šest jednoznačnih šifri; ostale se
namerno ne mapiraju (traže pravnu odluku)."""
from datetime import date, timedelta

import pytest

from services import risk_engine as RE
from services.risk_engine import calculate_procesni_rizik, identify_case_problems
from shared.constants import EXPECTED_DOCS
from shared.evidence_write import IZVORI_PROCENJENO, KOLONA_IZVOR_SNAGE

ODOBRENO = {
    "lawsuit": "podnesak", "response": "podnesak", "appeal": "podnesak",
    "judgment": "sudska_odluka", "court_decision": "sudska_odluka",
    "contract": "ugovor",
}
NEMAPIRANO = ["enforcement", "email", "invoice", "power_of_attorney", "evidence", "legal_opinion", "other",
              "nepoznata_vrsta"]
LAZNI = "Nedostaje podnesak stranke u spisu"
PISANA = "Nedostaje pisanu komunikaciju u spisu"


def _dokazi(snaga="jaka", n=3):
    return [{"snaga": snaga, KOLONA_IZVOR_SNAGE: sorted(IZVORI_PROCENJENO)[0], "kategorija": "dokaz"}
            for _ in range(n)]


def _rizik(tipovi, dokazi=None, rocista=(), tip="parnicno"):
    dok = [{"id": "d%d" % i, "tip_dokaza": t} for i, t in enumerate(tipovi)]
    r = calculate_procesni_rizik(dokazi=_dokazi() if dokazi is None else dokazi, dokumenti=dok,
                                 rocista=list(rocista), tip_predmeta=tip, expected_docs=EXPECTED_DOCS)
    return r, [p["problem"] for p in identify_case_problems(r, tip)]


def test_mapiranje_je_tacno_odobrenih_sest():
    assert RE._VRSTA_U_KATEGORIJU == ODOBRENO
    assert not set(NEMAPIRANO) & set(RE._VRSTA_U_KATEGORIJU)


@pytest.mark.parametrize("en,sr", sorted(ODOBRENO.items()))
@pytest.mark.parametrize("tip", sorted(EXPECTED_DOCS))
def test_1_sest_vrsta_daje_isti_rezultat_kao_srpska_kategorija(en, sr, tip):
    """Kriterijumi 1 i 7: ceo rezultat (nivo, skor, snaga, rokovi, problemi) jednak je srpskoj kategoriji."""
    for ostali in ([], ["sudska_odluka"], ["dopis", "ugovor"]):
        assert _rizik(ostali + [en], tip=tip) == _rizik(ostali + [sr], tip=tip)


@pytest.mark.parametrize("tipovi,nedost,nivo,health", [
    ([], ["sudska_odluka", "podnesak", "ugovor", "dopis"], "Srednji", 55),
    (["podnesak"], ["sudska_odluka", "ugovor", "dopis"], "Srednji", 55),
    (["sudska_odluka", "podnesak"], ["ugovor", "dopis"], "Nizak", 70),
    (["sudska_odluka", "podnesak", "ugovor", "dopis"], [], "Nizak", 70),
    (["medicinska_dokumentacija", "javna_isprava"], ["sudska_odluka", "podnesak", "ugovor", "dopis"], "Srednji", 55),
])
def test_2_srpske_kategorije_nepromenjene(tipovi, nedost, nivo, health):
    r, _ = _rizik(tipovi)
    assert (r["nedostajuci_dokazi"], r["nivo"], r["health_score"]) == (nedost, nivo, health)


@pytest.mark.parametrize("vrsta", NEMAPIRANO)
@pytest.mark.parametrize("tip", sorted(EXPECTED_DOCS))
def test_3_nemapirana_vrsta_ne_pokriva_nijednu_kategoriju(vrsta, tip):
    """Ponašanje kao pre ispravke: dokument nemapirane vrste ne uklanja nijedan očekivani dokument."""
    for ostali in ([], ["sudska_odluka"], ["podnesak", "ugovor"]):
        assert _rizik(ostali + [vrsta], tip=tip) == _rizik(ostali, tip=tip)


def test_4_appeal_ne_daje_lazni_nalaz_podneska():
    r, problemi = _rizik(["appeal"])
    assert "podnesak" not in r["nedostajuci_dokazi"]
    assert LAZNI not in problemi


def test_5_sinteticki_predmet_ostaje_nizak_70():
    """Prijavljen slučaj: [sudska_odluka, appeal] je bio Srednji/55 (3 nedostajuća), kontrola Nizak/70."""
    r, _ = _rizik(["sudska_odluka", "appeal"])
    assert (r["nedostajuci_count"], r["nivo"], r["health_score"]) == (2, "Nizak", 70)


def test_6_stvarno_nedostajuca_pisana_komunikacija_ostaje_vidljiva():
    """Scenario A: jedini dokument je `appeal`; lista prikazuje prva 3 nedostajuća."""
    r, problemi = _rizik(["appeal"])
    assert r["nedostajuci_dokazi"] == ["sudska_odluka", "ugovor", "dopis"]
    assert PISANA in problemi and LAZNI not in problemi


@pytest.mark.parametrize("snaga", ["jaka", "srednja", "slaba"])
def test_7_nezavisni_faktori_nepromenjeni(snaga):
    danas = date.today()
    rocista = [{"id": "r1", "datum": (danas + timedelta(days=3)).isoformat()},
               {"id": "r2", "datum": (danas - timedelta(days=2)).isoformat()},
               {"id": "r3", "datum": (danas + timedelta(days=20)).isoformat()}]
    for dokazi in (_dokazi(snaga), []):
        a, pa = _rizik(["appeal", "judgment"], dokazi=dokazi, rocista=rocista)
        s, ps = _rizik(["podnesak", "sudska_odluka"], dokazi=dokazi, rocista=rocista)
        assert (a, pa) == (s, ps)
        assert (a["kriticni_rokovi"], a["zakasneli_rokovi"], a["predstojeći_rokovi"]) == (2, 1, 2)

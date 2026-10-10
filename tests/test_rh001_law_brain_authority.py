# -*- coding: utf-8 -*-
"""RH001 — ista klasa kao NS007 Hearing Prep, u NS008 Law Brain sintezi.

Reprodukovano na 79c1071b: `proveri_sintezu` je prihvatala „Prema ustaljenoj praksi Vrhovnog suda…", „Vrhovni sud
smatra…" i „Teret dokazivanja je na tuženom" uz važeću referencu — `_ZABRANJENO` hvata samo „sudska praksa",
„zakon", „uvek", „nikad". Sinteza iskustva kancelarije je DEKLARATIVNA po ugovoru (za razliku od Hearing Prep-a),
pa se ovde primenjuje samo deljeno pravilo autoriteta (`shared/pravni_autoritet`), ne pravilo oblika.
"""
import pytest

from services.law_brain_sinteza import proveri_sintezu
from tests.test_rh001_hearing_prep_authority import ADVERSARIJALNE, DEKLARATIVNE_CINJENICE

REFS = [{"ref": "R1", "trust_class": "SOURCE_CASE_FACT", "tekst": "Raniji predmet 1: isti sud, svedoci, 2015, 3.9.2026, 12",
         "source_ref": {"table": "predmeti", "id": "p1"}}]


@pytest.mark.parametrize("tekst", ADVERSARIJALNE)
def test_sinteza_odbacuje_implicitni_autoritet(tekst):
    prihvacene, odbaceno, razlozi = proveri_sintezu({"tvrdnje": [{"tekst": tekst, "vrsta": "iskustvo", "refs": ["R1"]}]}, REFS)
    assert prihvacene == [] and odbaceno == 1, tekst
    assert razlozi in (["PRAVNI_AUTORITET_BEZ_IZVORA"], ["ZABRANJEN_SADRZAJ"], ["BROJ_BEZ_IZVORA"]), (tekst, razlozi)


def test_legitimno_iskustvo_ostaje():
    """Deklarativne tvrdnje o iskustvu bez pravnog autoriteta i dalje prolaze (sinteza nije ispražnjena)."""
    tekstovi = ["Raniji predmet pred istim sudom imao je slične dokaze.",
                "Kancelarija je u ranijem predmetu koristila svedoke."] + [
        t for t in DEKLARATIVNE_CINJENICE if "Rok" not in t]          # brojevi moraju postojati u referenci
    prihvacene, odbaceno, razlozi = proveri_sintezu(
        {"tvrdnje": [{"tekst": t, "vrsta": "iskustvo", "refs": ["R1"]} for t in tekstovi]}, REFS)
    assert "PRAVNI_AUTORITET_BEZ_IZVORA" not in razlozi
    assert {p["tekst"] for p in prihvacene} >= {tekstovi[0], tekstovi[1]}


def test_razlog_je_poseban_i_nezavisan_od_starog_filtera():
    """„Vrhovni sud smatra…" ne sadrži nijednu reč starog filtera — odbija ga SAMO novo pravilo."""
    _, _, razlozi = proveri_sintezu({"tvrdnje": [{"tekst": "Vrhovni sud smatra da je svedočenje dovoljno.",
                                                   "vrsta": "iskustvo", "refs": ["R1"]}]}, REFS)
    assert razlozi == ["PRAVNI_AUTORITET_BEZ_IZVORA"]

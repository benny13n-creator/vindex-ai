# -*- coding: utf-8 -*-
"""
Wave 9 (§6) — semantika saradnika na granici AI rezonovanja.

ŠTA JE IZMERENO

Repo IMA model saradnika: tabela `predmet_saradnici` (`routers/saradnja.py:9`),
sa endpointima za pozivanje, listanje i uklanjanje saradnika, i sa
`routers/client_portal.py:239` koji ga koristi za razrešavanje vlasnika.

Nijedna AI putanja ga NE KONSULTUJE:
  - `shared/case_context.py:161` filtrira SAMO `predmeti.user_id == uid`
  - `routers/copilot_ambient.py::_proveri_vlasnistvo_predmeta` isto tako

Posledica: saradnik na tuđem predmetu može da radi kroz `saradnja` endpointe,
ali NE MOŽE da pokrene AI analizu nad tim predmetom — dobija 404 i prazan
kontekst, isto kao potpuni stranac.

ZAŠTO OVO NIJE POPRAVLJENO OVDE, NEGO ZAKLJUČANO

Mandat (§6) izričito kaže: „Ne menjaj fail-closed ownership ponašanje bez veoma
jakog razloga." Trenutno ponašanje JESTE fail-closed — greši u bezbednom smeru.

Proširenje pristupa nije inženjerska nego poslovna odluka, i to sa naplatnom
dimenzijom: kompletna analiza košta 6 kredita, pa „sme li saradnik da je
pokrene" je neodvojivo od „čiji kredit se troši". Izmišljanje tog odgovora bi
bilo tačno ono što §26 zabranjuje.

Zato ovaj fajl ne menja ponašanje — on ga MERI i ZAKLJUČAVA. Ako neko ubuduće
proširi pristup, ovi testovi padaju i teraju ga da odluku donese svesno, uz
odgovor na pitanje o kreditima. Ako je proširenje namerno, testovi se prepisuju
uz obrazloženje — nikad ne brišu.

METOD

Isti harness kao `tests/test_wave7_ab_forensics.py`: mock-uje se SAMO Supabase
klijent, a `build_case_context` i vlasnička kapija se STVARNO izvršavaju.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_wave7_ab_forensics import (  # noqa: E402
    ALFA_DOK, ALFA_ID, ALFA_MARKER, UID_A, UID_B, _Upit,
)

# Treći identitet: registrovan saradnik na Alfinom predmetu, ne vlasnik.
UID_SARADNIK = "33333333-0000-4000-8000-000000000003"


def _baza_sa_saradnikom():
    """Alfin predmet + red u `predmet_saradnici` koji daje pristup saradniku.

    Saradnik je STVARNO upisan — ako bi ijedna AI putanja konsultovala tu
    tabelu, dobio bi pristup. Test dokazuje da je nijedna ne konsultuje.
    """
    tabele = {
        "predmeti": [
            {"id": ALFA_ID, "user_id": UID_A, "naziv": f"Spor {ALFA_MARKER}",
             "tip_postupka": "privredni", "sud": "Privredni sud", "status": "aktivan",
             "stranka": "DOO Alfa", "protivnik": "DOO Kontra-Alfa", "case_dna": None},
        ],
        "predmet_saradnici": [
            {"predmet_id": ALFA_ID, "owner_user_id": UID_A,
             "saradnik_user_id": UID_SARADNIK, "status": "prihvaceno"},
        ],
        "predmet_dokumenti": [
            {"id": "doc-a", "predmet_id": ALFA_ID, "naziv_fajla": "alfa-ugovor.pdf",
             "redni_broj": 1, "tip_dokaza": "ugovor", "status": "spreman",
             "created_at": "2026-08-01T00:00:00Z",
             "tekst_sadrzaj": f"{ALFA_DOK}: Član 7 ugovora određuje rok isporuke."},
        ],
        "predmet_dokazi": [], "rocista": [], "case_actions": [],
        "predmet_hronologija": [], "predmet_komentari": [],
    }
    supa = MagicMock()
    supa.table.side_effect = lambda ime: _Upit(tabele.get(ime, []))
    return supa


# ─── 1. KANONSKI KONTEKST ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_saradnik_ne_dobija_kanonski_kontekst():
    """Saradnik upisan u bazu ne dobija ni jedan bajt sadržaja predmeta."""
    import routers.strategija as rs

    with patch("shared.deps._get_supa", return_value=_baza_sa_saradnikom()), \
         patch("routers.strategija._get_supa", return_value=_baza_sa_saradnikom()):
        blok = await rs._kanonski_kontekst_blok(ALFA_ID, UID_SARADNIK)

    assert blok == "", (
        "saradnik je dobio kanonski kontekst tuđeg predmeta — ako je to namerna "
        "promena politike, odgovori i na pitanje čiji se krediti troše, pa prepiši "
        "ovaj test uz obrazloženje"
    )
    assert ALFA_MARKER not in blok and ALFA_DOK not in blok


@pytest.mark.asyncio
async def test_b_vlasnik_i_dalje_dobija_kontekst():
    """Pozitivna kontrola.

    Bez nje bi `test_a` prolazio i da je `build_case_context` potpuno pokvaren i
    svima vraća prazno — a to bi bio gori kvar od onog koji se meri.
    """
    import routers.strategija as rs

    with patch("shared.deps._get_supa", return_value=_baza_sa_saradnikom()), \
         patch("routers.strategija._get_supa", return_value=_baza_sa_saradnikom()):
        blok = await rs._kanonski_kontekst_blok(ALFA_ID, UID_A)

    assert blok, "vlasnik ne dobija kontekst — lanac je pokvaren, ne politika"
    assert ALFA_MARKER in blok and ALFA_DOK in blok


# ─── 2. VLASNIČKA KAPIJA ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_c_kapija_odbija_saradnika_isto_kao_stranca():
    """`_proveri_vlasnistvo_predmeta` ne pravi razliku saradnik/stranac.

    Obe grane moraju dati isti HTTP 404 — inače bi razlika u odgovoru sama po
    sebi otkrivala postojanje tuđeg predmeta.
    """
    from fastapi import HTTPException

    from routers.copilot_ambient import _proveri_vlasnistvo_predmeta

    for uid, ko in ((UID_SARADNIK, "saradnik"), (UID_B, "stranac")):
        with patch("routers.copilot_ambient._get_supa",
                   return_value=_baza_sa_saradnikom()):
            with pytest.raises(HTTPException) as exc:
                await _proveri_vlasnistvo_predmeta(ALFA_ID, uid)
        assert exc.value.status_code == 404, f"{ko} nije dobio 404"


@pytest.mark.asyncio
async def test_ng_kapija_propusta_vlasnika():
    """Negativna kontrola kapije — bez nje bi `test_c` prolazio i da kapija
    odbija SVAKOGA, uključujući vlasnika."""
    from routers.copilot_ambient import _proveri_vlasnistvo_predmeta

    with patch("routers.copilot_ambient._get_supa",
               return_value=_baza_sa_saradnikom()):
        await _proveri_vlasnistvo_predmeta(ALFA_ID, UID_A)  # ne sme da digne


# ─── 3. TABELA SARADNIKA STVARNO POSTOJI U LAŽNOJ BAZI ──────────────────────

def test_ng_lazna_baza_stvarno_sadrzi_saradnika():
    """Bez ovoga bi svi testovi iznad prolazili trivijalno.

    Ako lažna baza uopšte nema red u `predmet_saradnici`, „saradnik nema
    pristup" ne dokazuje ništa — dokazuje samo da nepostojeći saradnik nema
    pristup. Ovaj test tvrdi da red POSTOJI i da je pronalaziv istim upitom
    koji `routers/saradnja.py:208` koristi.
    """
    supa = _baza_sa_saradnikom()
    r = (supa.table("predmet_saradnici")
         .select("*")
         .eq("predmet_id", ALFA_ID)
         .eq("saradnik_user_id", UID_SARADNIK)
         .execute())
    assert r.data, "lažna baza nema saradnika — testovi iznad bi bili prazni"

# -*- coding: utf-8 -*-
"""Z017.2 -- regresija koju je Pattern A skoro uveo, a nije stigla u produkciju.

`carf_dac8_readiness_sync` je promenjena sa `-> str` na `-> dict`
{odgovor, izvori, retrieval_unavailable} (Pattern A, G2/CARF commit). Provera
poziva je pokrivala SAMO `routers/web3.py` -- `routers/source_of_funds.py`
poziva istu funkciju (`_carf_dac8_readiness`) i prosledjuje rezultat
DIREKTNO u `generisi_dossier_pdf`, koja poziva `.split("\\n")` na njemu
(dossier_pdf.py:181). Dict nema `.split` -- ovo bi bio AttributeError 500 na
SVAKOM pozivu F16.1 (Source-of-Funds Dossier) da nije uhvaceno pre commit-a.

Ovaj test cuva da izvlacenje stringa iz novog dict oblika radi za oba
slucaja (dict I stari str, za svaki slucaj da neki drugi pozivalac jos
uvek vraca golo str) i da PDF generator dobija string, ne dict.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import Request

import pytest


@pytest.mark.asyncio
async def test_carf_dict_rezultat_ne_stize_kao_dict_u_pdf_generator():
    import routers.source_of_funds as SOF

    lazan_pdf_poziv = MagicMock(return_value=b"%PDF-fake")
    zahtev = SOF.DossierRequest(opis_dokumentacije="Imam izvode sa berze i bankovne izvode za poslednjih pet godina.", carf_pitanje="", wallet_adresa="")
    user = {"user_id": "u1", "email": "a@b.rs"}
    request = MagicMock(spec=Request)

    with patch.object(SOF, "_documentation_health_score", return_value={"health_data": {}, "objasnjenje": "x", "raw": "{}"}), \
         patch.object(SOF, "_carf_dac8_readiness", return_value={"odgovor": "CARF tekst.", "izvori": [], "retrieval_unavailable": False}), \
         patch.object(SOF, "UsageService") as MockUsage, \
         patch.object(SOF, "_audit", new=AsyncMock()), \
         patch.object(SOF, "generisi_dossier_pdf", new=lazan_pdf_poziv):
        MockUsage.consume = AsyncMock(return_value=10)
        await SOF.post_source_of_funds_dossier(zahtev, request, user)

    assert lazan_pdf_poziv.called
    kontekst = lazan_pdf_poziv.call_args[0][0]
    assert isinstance(kontekst["carf_odgovor"], str), (
        "generisi_dossier_pdf je dobio %r umesto str -- .split('\\n') bi pukao" % type(kontekst["carf_odgovor"]))
    assert kontekst["carf_odgovor"] == "CARF tekst."


@pytest.mark.asyncio
async def test_carf_stari_string_oblik_i_dalje_radi():
    """Odbrambeno: ako neki buduci pozivalac i dalje vrati golo str (ne dict),
    ekstrakcija ne sme da pukne -- `isinstance(dict)` grana mora ispravno
    da padne na `else` granu."""
    import routers.source_of_funds as SOF

    lazan_pdf_poziv = MagicMock(return_value=b"%PDF-fake")
    zahtev = SOF.DossierRequest(opis_dokumentacije="Imam izvode sa berze i bankovne izvode za poslednjih pet godina.", carf_pitanje="", wallet_adresa="")
    user = {"user_id": "u1", "email": "a@b.rs"}
    request = MagicMock(spec=Request)

    with patch.object(SOF, "_documentation_health_score", return_value={"health_data": {}, "objasnjenje": "x", "raw": "{}"}), \
         patch.object(SOF, "_carf_dac8_readiness", return_value="Golo str, stari oblik."), \
         patch.object(SOF, "UsageService") as MockUsage, \
         patch.object(SOF, "_audit", new=AsyncMock()), \
         patch.object(SOF, "generisi_dossier_pdf", new=lazan_pdf_poziv):
        MockUsage.consume = AsyncMock(return_value=10)
        await SOF.post_source_of_funds_dossier(zahtev, request, user)

    kontekst = lazan_pdf_poziv.call_args[0][0]
    assert kontekst["carf_odgovor"] == "Golo str, stari oblik."

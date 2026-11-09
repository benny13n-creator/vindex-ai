"""Formalni odgovor na tužbu ne sme preneti neproverenu procesnu tvrdnju."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request


@pytest.mark.asyncio
@pytest.mark.parametrize("tekst", [
    "Tuženi podnosi odgovor u zakonskom roku od 30 dana, u skladu sa članom 298 ZPP.",
    "Tuženi je već podneo odgovor na tužbu.",
    "Rok za odgovor ističe 14.11.2026. godine.",
    "Tužba sa prilozima je dostavljena tuženom 15. oktobra 2026. godine.",
    "Рок за одговор на тужбу прописан је чланом 298. ЗПП.",
    "Tužba je uručena tuženom 15. oktobra 2026. godine.",
    "Tuženi je primio tužbu sa prilozima 15. oktobra 2026. godine.",
    "Dostava tužbe izvršena je 15. oktobra 2026. godine.",
    "Rok za odgovor na tužbu ističe sutra.",
    "Рок за одговор истиче четрнаестог новембра.",
    "Prema čl. 298. ZPP rok iznosi 30 dana.",
    "Rok za odgovor na tužbu je 30 dana. Pravni osnov je član 298 ZPP.",
    "Tuženi je predao ovaj odgovor na tužbu sudu u ponedeljak.",
    "Po članu 298. Zakona o parničnom postupku rok iznosi 30 dana.",
    "Poslednji dan za odgovor na tužbu je sutra.",
    "Odgovor na tužbu se može podneti najkasnije 14.11.2026.",
    "Dostavljanje tužbe obavljeno je 15. oktobra 2026. godine.",
    "Tuženi je zaprimio tužbu 15. oktobra 2026.",
    "Nije utvrđeno kada je tužba uručena, ali je tuženi primio tužbu 15. oktobra 2026.",
    "Odgovor na tužbu je zaveden u sudski upisnik.",
    "Tužba sa prilozima je predata tuženom 03.10.2026.",
    "Član 298 ZPP uređuje sadržaj odgovora, dok je rok po članu 298 ZPP, "
    "a član 297 ZPP propisuje rok za drugi postupak.",
    "Član 298 ZPP uređuje sadržaj odgovora, dok po toj odredbi rok iznosi 30 dana, "
    "a član 297 ZPP propisuje rok za drugi postupak.",
])
async def test_formalni_odgovor_sa_neutemeljenom_tvrdnjom_ne_vraca_uspeh(monkeypatch, tekst):
    import routers.drafting as dr

    monkeypatch.setattr("routers.copilot_ambient._proveri_vlasnistvo_predmeta", AsyncMock())
    monkeypatch.setattr(dr, "_recent_generation_exists", AsyncMock(return_value=False))
    monkeypatch.setattr("app.services.retrieve.retrieve_documents", lambda *_: ([], {}))
    monkeypatch.setattr(dr, "_pozovi_drafting_api", lambda *a, **k: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"tuzeni_ime":"TEST BETA"}'))]))
    monkeypatch.setattr(dr, "_critique_and_refine_draft", AsyncMock(return_value=(tekst, True)))
    consume, stage = AsyncMock(), AsyncMock()
    monkeypatch.setattr(dr.UsageService, "consume", consume)
    monkeypatch.setattr(dr, "_stage_draft_for_review", stage)
    req = dr.PodnesakReq(tip="odgovor_na_tuzbu", opis="Sintetički opis bez potvrde dostavljanja.", predmet_id="test-A")
    request = Request({"type": "http", "method": "POST", "path": "/api/podnesak", "headers": []})
    with pytest.raises(HTTPException) as exc:
        await dr.podnesak.__wrapped__(req, request, {"user_id": "A"})
    assert exc.value.status_code == 422
    consume.assert_not_awaited()
    stage.assert_not_called()


def test_opste_pravilo_zpp_bez_tvrdnje_o_dostavljanju_prolazi():
    from routers.drafting import _proveri_rok_odgovora_na_tuzbu
    _proveri_rok_odgovora_na_tuzbu(
        "odgovor_na_tuzbu",
        "Član 297 ZPP propisuje rok od 30 dana od dostavljanja tužbe sa prilozima. "
        "Član 298 ZPP uređuje sadržaj odgovora. Datum dostavljanja nije potvrđen.",
    )
    _proveri_rok_odgovora_na_tuzbu(
        "odgovor_na_tuzbu",
        "Rok od 30 dana računa se od uručenja tužbe sa prilozima. "
        "Član 298. ZPP uređuje sadržaj odgovora. Nije utvrđeno kada je tužba uručena.",
    )
    _proveri_rok_odgovora_na_tuzbu(
        "odgovor_na_tuzbu",
        "U spisu nema dokaza da je tužba dostavljena. "
        "Ako je tužba dostavljena sa prilozima, rok od 30 dana teče od tada.",
    )


@pytest.mark.parametrize("tekst", [
    "Član 298 ZPP uređuje sadržaj odgovora, dok je rok od 30 dana propisan članom 297 ZPP "
    "i teče od dostavljanja tužbe sa prilozima.",
    "Član 297 ZPP propisuje rok od 30 dana od dostavljanja tužbe sa prilozima, "
    "a član 298 ZPP uređuje sadržinu odgovora na tužbu.",
    "U spisu nema dokaza da je tužba sa prilozima predata tuženom. "
    "Ako je tužba sa prilozima predata tuženom, rok od 30 dana teče od tada.",
    "Nije utvrđeno da li je odgovor na tužbu zaveden u sudski upisnik.",
])
def test_formalni_odgovor_pravi_razliku_izmedju_pravila_i_cinjenica(tekst):
    from routers.drafting import _proveri_rok_odgovora_na_tuzbu
    _proveri_rok_odgovora_na_tuzbu("odgovor_na_tuzbu", tekst)

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

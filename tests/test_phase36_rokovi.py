# -*- coding: utf-8 -*-
"""
Tests for Phase 3.6 — Rokovi: zastarelost kalkulacija, relativni datum, ICS export.
Pokriva: zastarelost.py, ics_export.py, routers/zastarelost.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta


# ════════════════════════════════════════════════════════════════════════════════
# zastarelost.py — kalkulisi_zastarelost
# ════════════════════════════════════════════════════════════════════════════════

def test_kalkulisi_opsti_rok_10_godina():
    from zastarelost import kalkulisi_zastarelost
    poc = date(2020, 1, 15)
    rez = kalkulisi_zastarelost("opsti", poc)
    assert rez.datum_zastarelosti == date(2030, 1, 15)
    assert rez.rok_godina == 10
    assert "10" in rez.rok_opis


def test_kalkulisi_privreda_3_godine():
    from zastarelost import kalkulisi_zastarelost
    poc = date(2023, 6, 1)
    rez = kalkulisi_zastarelost("privreda", poc)
    assert rez.datum_zastarelosti == date(2026, 6, 1)


def test_kalkulisi_cek_6_meseci():
    from zastarelost import kalkulisi_zastarelost
    poc = date(2026, 1, 1)
    rez = kalkulisi_zastarelost("cek", poc)
    assert rez.datum_zastarelosti == date(2026, 7, 1)
    assert "meseci" in rez.rok_opis
    assert rez.rok_godina == 0


def test_kalkulisi_zalbeni_upravni_15_dana():
    from zastarelost import kalkulisi_zastarelost
    poc = date(2026, 6, 1)
    rez = kalkulisi_zastarelost("zalbeni_upravni", poc)
    assert rez.datum_zastarelosti == date(2026, 6, 16)
    assert "15" in rez.rok_opis


def test_kalkulisi_tuzba_upravni_spor_30_dana():
    from zastarelost import kalkulisi_zastarelost
    poc = date(2026, 6, 1)
    rez = kalkulisi_zastarelost("tuzba_upravni_spor", poc)
    assert rez.datum_zastarelosti == date(2026, 7, 1)


def test_kalkulisi_isteklo_flag():
    from zastarelost import kalkulisi_zastarelost
    poc = date(2010, 1, 1)
    rez = kalkulisi_zastarelost("opsti", poc)
    assert rez.isteklo is True
    assert rez.dana_preostalo < 0


def test_kalkulisi_nije_isteklo():
    from zastarelost import kalkulisi_zastarelost
    poc = date.today() - relativedelta(years=1)
    rez = kalkulisi_zastarelost("opsti", poc)
    assert rez.isteklo is False
    assert rez.dana_preostalo > 0


def test_kalkulisi_nepoznat_tip_baca_valueerror():
    from zastarelost import kalkulisi_zastarelost
    with pytest.raises(ValueError, match="Nepoznat tip"):
        kalkulisi_zastarelost("nepostojeci_tip", date.today())


def test_kalkulisi_napomena_za_menjacki():
    from zastarelost import kalkulisi_zastarelost
    rez = kalkulisi_zastarelost("menjacki", date(2024, 1, 1))
    assert rez.napomena != ""


def test_kalkulisi_bez_napomene_za_opsti():
    from zastarelost import kalkulisi_zastarelost
    rez = kalkulisi_zastarelost("opsti", date(2024, 1, 1))
    assert rez.napomena == ""


# ════════════════════════════════════════════════════════════════════════════════
# zastarelost.py — lista_tipova_zastarelosti
# ════════════════════════════════════════════════════════════════════════════════

def test_lista_tipova_nije_prazna():
    from zastarelost import lista_tipova_zastarelosti
    tipovi = lista_tipova_zastarelosti()
    assert len(tipovi) >= 10


def test_lista_tipova_ima_obavezna_polja():
    from zastarelost import lista_tipova_zastarelosti
    for t in lista_tipova_zastarelosti():
        assert "kljuc" in t
        assert "naziv" in t
        assert "osnov" in t
        assert "opis"  in t


def test_lista_tipova_sadrzi_opsti():
    from zastarelost import lista_tipova_zastarelosti
    kljucevi = [t["kljuc"] for t in lista_tipova_zastarelosti()]
    assert "opsti" in kljucevi
    assert "privreda" in kljucevi
    assert "radni_spor" in kljucevi


# ════════════════════════════════════════════════════════════════════════════════
# zastarelost.py — parsiraj_relativni_datum
# ════════════════════════════════════════════════════════════════════════════════

def test_relativni_za_30_dana():
    from zastarelost import parsiraj_relativni_datum
    ocekivano = date.today() + timedelta(days=30)
    assert parsiraj_relativni_datum("za 30 dana") == ocekivano


def test_relativni_za_1_dan():
    from zastarelost import parsiraj_relativni_datum
    ocekivano = date.today() + timedelta(days=1)
    assert parsiraj_relativni_datum("za 1 dan") == ocekivano


def test_relativni_pre_15_dana():
    from zastarelost import parsiraj_relativni_datum
    ocekivano = date.today() - timedelta(days=15)
    assert parsiraj_relativni_datum("pre 15 dana") == ocekivano


def test_relativni_za_3_nedelje():
    from zastarelost import parsiraj_relativni_datum
    ocekivano = date.today() + timedelta(weeks=3)
    assert parsiraj_relativni_datum("za 3 nedelje") == ocekivano


def test_relativni_za_1_nedelju():
    from zastarelost import parsiraj_relativni_datum
    ocekivano = date.today() + timedelta(weeks=1)
    assert parsiraj_relativni_datum("za 1 nedelju") == ocekivano


def test_relativni_za_6_meseci():
    from zastarelost import parsiraj_relativni_datum
    ocekivano = date.today() + relativedelta(months=6)
    assert parsiraj_relativni_datum("za 6 meseci") == ocekivano


def test_relativni_za_1_mesec():
    from zastarelost import parsiraj_relativni_datum
    ocekivano = date.today() + relativedelta(months=1)
    assert parsiraj_relativni_datum("za 1 mesec") == ocekivano


def test_relativni_pre_2_meseca():
    from zastarelost import parsiraj_relativni_datum
    ocekivano = date.today() - relativedelta(months=2)
    assert parsiraj_relativni_datum("pre 2 meseca") == ocekivano


def test_relativni_za_1_godinu():
    from zastarelost import parsiraj_relativni_datum
    ocekivano = date.today() + relativedelta(years=1)
    assert parsiraj_relativni_datum("za 1 godinu") == ocekivano


def test_relativni_za_5_godina():
    from zastarelost import parsiraj_relativni_datum
    ocekivano = date.today() + relativedelta(years=5)
    assert parsiraj_relativni_datum("za 5 godina") == ocekivano


def test_relativni_pre_10_godina():
    from zastarelost import parsiraj_relativni_datum
    ocekivano = date.today() - relativedelta(years=10)
    assert parsiraj_relativni_datum("pre 10 godina") == ocekivano


def test_relativni_nevalidan_izraz_baca_valueerror():
    from zastarelost import parsiraj_relativni_datum
    with pytest.raises(ValueError, match="Nepoznat relativni izraz"):
        parsiraj_relativni_datum("sutra")


def test_relativni_nevalidan_izraz_engleski():
    from zastarelost import parsiraj_relativni_datum
    with pytest.raises(ValueError):
        parsiraj_relativni_datum("in 30 days")


def test_relativni_prazno_baca_valueerror():
    from zastarelost import parsiraj_relativni_datum
    with pytest.raises(ValueError):
        parsiraj_relativni_datum("  ")


def test_relativni_sa_extra_razmakom():
    from zastarelost import parsiraj_relativni_datum
    # Strip whitespace at edges should work
    ocekivano = date.today() + timedelta(days=5)
    assert parsiraj_relativni_datum("  za 5 dana  ") == ocekivano


# ════════════════════════════════════════════════════════════════════════════════
# ics_export.py — generiši_ics_event
# ════════════════════════════════════════════════════════════════════════════════

def test_ics_event_osnovna_struktura():
    from ics_export import generiši_ics_event
    ics = generiši_ics_event("Rok zastarelosti", date(2026, 12, 31), "Opšti rok — ZOO")
    assert "BEGIN:VCALENDAR" in ics
    assert "END:VCALENDAR" in ics
    assert "BEGIN:VEVENT" in ics
    assert "END:VEVENT" in ics


def test_ics_event_summary_u_izlazu():
    from ics_export import generiši_ics_event
    ics = generiši_ics_event("Rok zastarelosti", date(2026, 12, 31))
    assert "SUMMARY:Rok zastarelosti" in ics


def test_ics_event_datum_ispravan():
    from ics_export import generiši_ics_event
    ics = generiši_ics_event("Test", date(2026, 6, 15))
    assert "DTSTART;VALUE=DATE:20260615" in ics


def test_ics_event_ima_valarm():
    from ics_export import generiši_ics_event
    ics = generiši_ics_event("Test", date(2026, 9, 1))
    assert "BEGIN:VALARM" in ics
    assert "TRIGGER:-P7D" in ics
    assert "TRIGGER:-P1D" in ics


def test_ics_event_escaping_zareza():
    from ics_export import generiši_ics_event
    ics = generiši_ics_event("Test, sa zarezom", date(2026, 7, 1))
    assert "Test\\, sa zarezom" in ics


def test_ics_event_escaping_tackazarez():
    from ics_export import generiši_ics_event
    ics = generiši_ics_event("Test; sa tačka-zarezom", date(2026, 7, 1))
    assert "Test\\; sa tačka-zarezom" in ics


def test_ics_event_crlf_separator():
    from ics_export import generiši_ics_event
    ics = generiši_ics_event("Test", date(2026, 7, 1))
    assert "\r\n" in ics


def test_ics_event_bez_opisa():
    from ics_export import generiši_ics_event
    ics = generiši_ics_event("Test", date(2026, 7, 1))
    assert "DESCRIPTION:" in ics


def test_ics_event_prodid():
    from ics_export import generiši_ics_event
    ics = generiši_ics_event("Test", date(2026, 7, 1))
    assert "PRODID:-//Vindex AI//RS" in ics


# ════════════════════════════════════════════════════════════════════════════════
# ics_export.py — generiši_ics_multi
# ════════════════════════════════════════════════════════════════════════════════

def test_ics_multi_dva_eventa():
    from ics_export import generiši_ics_multi
    eventi = [
        {"naslov": "Rok 1", "datum": date(2026, 8, 1), "opis": "prvi"},
        {"naslov": "Rok 2", "datum": date(2026, 9, 1), "opis": "drugi"},
    ]
    ics = generiši_ics_multi(eventi)
    assert ics.count("BEGIN:VEVENT") == 2
    assert ics.count("END:VEVENT")   == 2
    assert "Rok 1" in ics
    assert "Rok 2" in ics


def test_ics_multi_jedan_event():
    from ics_export import generiši_ics_multi
    ics = generiši_ics_multi([{"naslov": "Solo", "datum": date(2026, 7, 1)}])
    assert ics.count("BEGIN:VEVENT") == 1


def test_ics_multi_pet_evenata():
    from ics_export import generiši_ics_multi
    eventi = [
        {"naslov": f"Rok {i}", "datum": date(2026, i + 1, 1)} for i in range(1, 6)
    ]
    ics = generiši_ics_multi(eventi)
    assert ics.count("BEGIN:VEVENT") == 5


def test_ics_multi_bez_opisa_u_eventu():
    from ics_export import generiši_ics_multi
    ics = generiši_ics_multi([{"naslov": "Test", "datum": date(2026, 7, 1)}])
    assert "DESCRIPTION:" in ics


# ════════════════════════════════════════════════════════════════════════════════
# routers/zastarelost.py — GET /zastarelost/tipovi
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_api_tipovi_vraca_listu():
    from routers.zastarelost import get_tipovi_zastarelosti
    result = await get_tipovi_zastarelosti()
    assert "tipovi" in result
    assert len(result["tipovi"]) >= 10


@pytest.mark.anyio
async def test_api_tipovi_opsti_postoji():
    from routers.zastarelost import get_tipovi_zastarelosti
    result = await get_tipovi_zastarelosti()
    kljucevi = [t["kljuc"] for t in result["tipovi"]]
    assert "opsti" in kljucevi


# ════════════════════════════════════════════════════════════════════════════════
# routers/zastarelost.py — POST /zastarelost/kalkulisi
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_api_kalkulisi_opsti_iso_format():
    from routers.zastarelost import post_kalkulisi_zastarelost, ZastarelostRequest
    req = ZastarelostRequest(tip="opsti", datum_pocetka="2020-01-15")
    result = await post_kalkulisi_zastarelost(req)
    assert result["datum_zastarelosti"] == "15.01.2030"
    assert result["datum_zastarelosti_iso"] == "2030-01-15"
    assert result["isteklo"] is False


@pytest.mark.anyio
async def test_api_kalkulisi_dd_mm_yyyy_format():
    from routers.zastarelost import post_kalkulisi_zastarelost, ZastarelostRequest
    req = ZastarelostRequest(tip="zalbeni_upravni", datum_pocetka="01.06.2026")
    result = await post_kalkulisi_zastarelost(req)
    assert result["datum_zastarelosti"] == "16.06.2026"


@pytest.mark.anyio
async def test_api_kalkulisi_neispravan_datum_422():
    from fastapi import HTTPException
    from routers.zastarelost import post_kalkulisi_zastarelost, ZastarelostRequest
    req = ZastarelostRequest(tip="opsti", datum_pocetka="nije-datum")
    with pytest.raises(HTTPException) as exc:
        await post_kalkulisi_zastarelost(req)
    assert exc.value.status_code == 422


@pytest.mark.anyio
async def test_api_kalkulisi_nepoznat_tip_422():
    from fastapi import HTTPException
    from routers.zastarelost import post_kalkulisi_zastarelost, ZastarelostRequest
    req = ZastarelostRequest(tip="nepostojeci", datum_pocetka="2024-01-01")
    with pytest.raises(HTTPException) as exc:
        await post_kalkulisi_zastarelost(req)
    assert exc.value.status_code == 422


@pytest.mark.anyio
async def test_api_kalkulisi_dana_preostalo_tip():
    from routers.zastarelost import post_kalkulisi_zastarelost, ZastarelostRequest
    req = ZastarelostRequest(tip="privreda", datum_pocetka="2025-01-01")
    result = await post_kalkulisi_zastarelost(req)
    assert isinstance(result["dana_preostalo"], int)
    assert isinstance(result["isteklo"], bool)


# ════════════════════════════════════════════════════════════════════════════════
# routers/zastarelost.py — POST /zastarelost/relativni-datum
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_api_relativni_za_30_dana():
    from routers.zastarelost import post_relativni_datum, RelativniDatumRequest
    from datetime import date, timedelta
    req = RelativniDatumRequest(izraz="za 30 dana")
    result = await post_relativni_datum(req)
    ocekivano = (date.today() + timedelta(days=30)).isoformat()
    assert result["datum"] == ocekivano
    assert result["izraz"] == "za 30 dana"
    assert "datum_prikaz" in result


@pytest.mark.anyio
async def test_api_relativni_za_1_godinu():
    from routers.zastarelost import post_relativni_datum, RelativniDatumRequest
    from datetime import date
    req = RelativniDatumRequest(izraz="za 1 godinu")
    result = await post_relativni_datum(req)
    ocekivano = (date.today() + relativedelta(years=1)).isoformat()
    assert result["datum"] == ocekivano


@pytest.mark.anyio
async def test_api_relativni_neispravan_izraz_422():
    from fastapi import HTTPException
    from routers.zastarelost import post_relativni_datum, RelativniDatumRequest
    req = RelativniDatumRequest(izraz="sledeće nedelje")
    with pytest.raises(HTTPException) as exc:
        await post_relativni_datum(req)
    assert exc.value.status_code == 422


@pytest.mark.anyio
async def test_api_relativni_datum_prikaz_format():
    from routers.zastarelost import post_relativni_datum, RelativniDatumRequest
    req = RelativniDatumRequest(izraz="za 7 dana")
    result = await post_relativni_datum(req)
    # datum_prikaz mora biti DD.MM.YYYY
    parts = result["datum_prikaz"].split(".")
    assert len(parts) == 3
    assert len(parts[2]) == 4  # godina


# ════════════════════════════════════════════════════════════════════════════════
# routers/zastarelost.py — POST /rokovi/ics-export
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_api_ics_export_jedan_event():
    from routers.zastarelost import post_ics_export, IcsExportRequest
    req = IcsExportRequest(rokovi=[{"naslov": "Test rok", "datum_iso": "2026-12-31", "opis": "opis"}])
    resp = await post_ics_export(req)
    content = resp.body.decode("utf-8")
    assert "BEGIN:VCALENDAR" in content
    assert "Test rok" in content
    assert resp.media_type == "text/calendar"


@pytest.mark.anyio
async def test_api_ics_export_vise_rokova():
    from routers.zastarelost import post_ics_export, IcsExportRequest
    req = IcsExportRequest(rokovi=[
        {"naslov": "Rok A", "datum_iso": "2026-10-01"},
        {"naslov": "Rok B", "datum_iso": "2026-11-01"},
    ])
    resp = await post_ics_export(req)
    content = resp.body.decode("utf-8")
    assert content.count("BEGIN:VEVENT") == 2
    assert "rokovi_vindex_2" in resp.headers.get("content-disposition", "")


@pytest.mark.anyio
async def test_api_ics_export_prazna_lista_422():
    from fastapi import HTTPException
    from routers.zastarelost import post_ics_export, IcsExportRequest
    req = IcsExportRequest(rokovi=[])
    with pytest.raises(HTTPException) as exc:
        await post_ics_export(req)
    assert exc.value.status_code == 422


@pytest.mark.anyio
async def test_api_ics_export_neispravan_datum_422():
    from fastapi import HTTPException
    from routers.zastarelost import post_ics_export, IcsExportRequest
    req = IcsExportRequest(rokovi=[{"naslov": "Test", "datum_iso": "nije-datum"}])
    with pytest.raises(HTTPException) as exc:
        await post_ics_export(req)
    assert exc.value.status_code == 422


@pytest.mark.anyio
async def test_api_ics_export_bez_naslova_422():
    from fastapi import HTTPException
    from routers.zastarelost import post_ics_export, IcsExportRequest
    req = IcsExportRequest(rokovi=[{"datum_iso": "2026-12-31"}])
    with pytest.raises(HTTPException) as exc:
        await post_ics_export(req)
    assert exc.value.status_code == 422


@pytest.fixture
def anyio_backend():
    return "asyncio"

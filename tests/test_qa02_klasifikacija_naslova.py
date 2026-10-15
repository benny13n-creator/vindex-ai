# -*- coding: utf-8 -*-
"""QA-02 — heuristička klasifikacija Smart Intake-a: vrstu određuje NASLOV dokumenta, ne usputno pominjanje.

Beta QA (sintetički predmet QA-TEST-20261015): predlog tužbe, skenirani zapisnik i fotografija potvrde isporuke
dobili su tip `contract` sa fiksnih 0.85. Uzrok (`shared/intake_classify.py::classify_heuristic`): vraćala se PRVA
vrsta iz liste čija se ključna reč pojavi BILO GDE u prvih 400 znakova, a oblik „TUŽBE“ nije bio ključna reč — pa je
u „PREDLOG TUŽBE … po Ugovoru o isporuci“ pobeđivao „UGOVOR“, a u zapisniku/potvrdi koji navode broj ugovora takođe.

Fiksture su izmišljene, po obliku beta QA dokumenata (naslov u zaglavlju, stranke, poziv na ugovor u telu).
"""
import pytest

from tests.test_ns005_t14_smart_intake import ok  # noqa: F401 — `ok` je fixture

from shared.intake_classify import DOCUMENT_TYPES, classify_heuristic

PREDLOG_TUZBE_LAT = """OSNOVNI SUD U BEOGRADU
Tužilac: TEST ALFA DOO, Beograd
Tuženi: TEST BETA DOO, Novi Sad
Radi: isplate po Ugovoru o isporuci opreme br. 12/2026
PREDLOG TUŽBE
Dana 15.08.2026. tuženi je po UGOVORU bio dužan da isporuči 12 monitora."""

PREDLOG_TUZBE_ASCII = PREDLOG_TUZBE_LAT.replace("TUŽBE", "TUZBE").replace("Tužilac", "Tuzilac").replace("Tuženi", "Tuzeni")

PREDLOG_TUZBE_CIR = """ОСНОВНИ СУД У БЕОГРАДУ
Тужилац: ТЕСТ АЛФА ДОО
Тужени: ТЕСТ БЕТА ДОО
ПРЕДЛОГ ТУЖБЕ
Тужени није извршио обавезу из УГОВОРА о испоруци опреме."""

ODGOVOR_LAT = """OSNOVNI SUD U BEOGRADU
Tuženi: TEST BETA DOO
ODGOVOR NA TUŽBU
Tuženi osporava navode tužbe u celosti. Tužba se zasniva na Ugovoru o isporuci, ali je TUŽBA neosnovana."""

ODGOVOR_CIR = """ОСНОВНИ СУД У БЕОГРАДУ
ОДГОВОР НА ТУЖБУ
Тужени оспорава ТУЖБУ и наводе из УГОВОРА о испоруци."""

UGOVOR = """UGOVOR O ISPORUCI OPREME
zaključen dana 01.08.2026. između TEST ALFA DOO i TEST BETA DOO.
U slučaju spora, strane mogu podneti TUŽBA nadležnom sudu u Beogradu."""

ZAPISNIK_CIR = """ЗАПИСНИК О ПРИМОПРЕДАЈИ РОБЕ
по УГОВОРУ о испоруци бр. 12/2026
Дана 15.08.2026. предато је 9 (девет) монитора."""

ZAPISNIK_LAT = """ZAPISNIK O PRIMOPREDAJI
UGOVOR br. 12/2026 — isporuka monitora
Primopredaja izvršena 15.08.2026."""

POTVRDA = """POTVRDA O DOPUNSKOJ ISPORUCI
Na osnovu Ugovora o isporuci br. 12/2026 (UGOVOR) isporučena su 3 monitora dana 24.08.2026."""

DOSTAVNICA_PRESUDA = """DOSTAVNICA
PRESUDA P 123/2025
Uručeno dana 26.03.2025."""

NEPOZNAT = """OBAVEŠTENJE O PROMENI ADRESE
Od 01.09.2026. naša nova adresa je Bulevar 1, Beograd. Ugovor i ostali UGOVORI ostaju na snazi."""


# ── Pozitivni ─────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tekst,tip", [
    (PREDLOG_TUZBE_LAT, "lawsuit"),
    (PREDLOG_TUZBE_ASCII, "lawsuit"),
    (PREDLOG_TUZBE_CIR, "lawsuit"),
    (ODGOVOR_LAT, "response"),
    (ODGOVOR_CIR, "response"),
    (UGOVOR, "contract"),
    ("UGOVOR O ISPORUCI\nStrane su TEST ALFA DOO i TEST BETA DOO.", "contract"),
    ("T U Ž B A\nTužilac: TEST ALFA DOO", "lawsuit"),                       # razmaknut naslov
    ("ПРЕСУДА\nУ ИМЕ НАРОДА", "judgment"),
    ("РЕШЕЊЕ О ИЗВРШЕЊУ\nна основу веродостојне исправе", "enforcement"),   # duži naslov pobeđuje „РЕШЕЊЕ“
    ("PRIGOVOR NA REŠENJE\nIzjavljujem prigovor.", "appeal"),
    ("UGOVORNA KAZNA PO ČLANU 5\nTUŽBA\nTužilac: TEST ALFA DOO", "lawsuit"),   # UGOVOR ≠ UGOVORNA
    ("1. TUŽBA\nTužilac: TEST ALFA DOO", "lawsuit"),                           # redni broj ispred naslova
    ("„UGOVOR O ZAKUPU“\nzaključen 01.08.2026.", "contract"),                  # naslov pod navodnicima
])
def test_naslov_odredjuje_vrstu(tekst, tip):
    assert classify_heuristic(tekst) == (tip, 0.85)


# ── Negativni: pominjanje drugog dokumenta nije naslov ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tekst,nije", [
    (PREDLOG_TUZBE_LAT, "contract"),      # tužba koja citira ugovor
    (ODGOVOR_LAT, "lawsuit"),             # odgovor koji citira tužbu
    (UGOVOR, "lawsuit"),                  # ugovor koji pominje buduću tužbu
])
def test_citirani_dokument_ne_preuzima_vrstu(tekst, nije):
    r = classify_heuristic(tekst)
    assert r is not None and r[0] != nije, r


@pytest.mark.parametrize("tekst", [ZAPISNIK_CIR, ZAPISNIK_LAT, POTVRDA, DOSTAVNICA_PRESUDA, NEPOZNAT,
                                   "Poštovani, u prilogu vam šaljem Ugovor i TUŽBU.",
                                   "Ugovor o isporuci\nzaključen je 01.08.2026.",          # naslov nije istaknut
                                   "Zapisnik o primopredaji\nUGOVOR br 12/2026",            # stop-reč malim slovima
                                   "Potvrda o isporuci\nUGOVOR br 12/2026",
                                   "Br. 5 DOSTAVNICA\nPRESUDA P 1/2025",                    # oznaka dostavnice u redu
                                   "ZAPISNIK O PRIMOPREDAJI\nUGOVOR O ISPORUCI OPREME",      # posle stop-reči ništa
                                   "Potvrda o isporuci\nUGOVOR O ISPORUCI OPREME"])
def test_bez_prepoznatog_naslova_nema_lazno_sigurne_vrste(tekst):
    """Nijedna od 12 vrsta nije pouzdano prepoznata → heuristika ćuti (odlučuje postojeći model, sa svojom
    pouzdanošću i `other` kad nije siguran) — nikad `contract` 0.85 zbog broja ugovora u telu."""
    assert classify_heuristic(tekst) is None


@pytest.mark.parametrize("tekst,tudja", [
    # Završni gejt — nezavisni korpusi (79 + 51 slučaj). Zaglavlje koje NIJE jednoznačno (poziv na drugi akt sa „:“ ili
    # brojem, ili redovi dve različite vrste) ne sme dati samouverenu vrstu: odlučuje postojeći model.
    # Tri nova lažna pozitiva iz korpusa 79 (bilo: invoice / court_decision / invoice):
    ("ADVOKATSKA KANCELARIJA PETROVIĆ\nBulevar oslobođenja 12, Novi Sad\nRAČUN: 205-0000001234567-89\nTUŽBA\n"
     "Tužilac: TEST ALFA DOO", "invoice"),
    ("REŠENJE Iv 55/24\nŽALBA\nprotiv rešenja", "court_decision"),
    ("TUŽILAC SE POZIVA NA\nRAČUN BR 5 I UGOVOR\nTUŽBA", "invoice"),
    # Klasa A (pravilo „preskoči red“ iz e9dee23f): pravi naslov sa „:“/brojem, kasniji red druge vrste
    ("TUŽBA: radi isplate duga\nOsnovnom sudu u Beogradu\nTužilac: X\nTuženi: Y\nDokazi:\n1. UGOVOR o zajmu od 01.02.2025.\n"
     "2. Opomena", "contract"),
    ("PUNOMOĆJE br. 3/2026\nVlastodavac: Marko Marković\nza zastupanje u vezi sa:\nUGOVOR O ZAKUPU poslovnog prostora", "contract"),
    ("UGOVOR od 01.08.2026\nZakupodavac: X\nRAČUN ZAKUPODAVCA kod banke Intesa", "invoice"),
    # Klasa B (prvi red pobeđuje): memorandum, pobijani akt ili sporni ugovor iznad naslova
    ("Advokat Petar Petrović\nRAČUN ZA UPLATU: 205-123456-78\nTUŽBA\nOsnovnom sudu u Beogradu", "invoice"),
    ("Advokat Petar Petrović\nRAČUN IBAN RS35 1600 0000 0000\nTUŽBA\nOsnovnom sudu", "invoice"),
    ("Viši sud u Beogradu\nREŠENJE Posl. br. Iv 55/24\nŽALBA\nizvršnog dužnika", "court_decision"),
    ("Виши суд у Београду\nРЕШЕЊЕ Ипв(И) 12/24\nЖАЛБА\nизвршног дужника", "court_decision"),
    ("Apelacioni sud\nPRESUDA OSNOVNOG SUDA P 123/2025\nŽALBA tuženog", "judgment"),
    ("Osnov:\nUGOVOR O ZAKUPU br. 5/2024\nTUŽBA\nTužilac: X", "contract"),
])
def test_nejednoznacno_zaglavlje_ide_modelu(tekst, tudja):
    assert classify_heuristic(tekst) is None, tudja


@pytest.mark.parametrize("tekst", ["RAČUN br. 15/2026\nKupac: TEST BETA DOO", "FAKTURA br. 123\nKupac: TEST BETA DOO",
                                   "PRESUDA P 123/2025\nU IME NARODA", "УГОВОР бр. 12/2026\nо испоруци"])
def test_kljucna_rec_sa_brojem_ide_modelu(tekst):
    """Isti oblik („RAČUN BR 5“) je bio uzrok lažnog pozitiva, pa se ne pogađa ni kad je to stvarno naslov:
    pošten ishod je postojeći model, ne samouverena heuristika."""
    assert classify_heuristic(tekst) is None


def test_taksonomija_nepromenjena():
    assert DOCUMENT_TYPES == ("lawsuit", "response", "appeal", "judgment", "contract", "invoice",
                              "power_of_attorney", "evidence", "email", "court_decision", "enforcement",
                              "legal_opinion", "other")


@pytest.mark.anyio
@pytest.mark.parametrize("tekst", [ZAPISNIK_CIR, POTVRDA])
async def test_bez_naslova_ide_u_postojeci_model_sa_njegovom_pouzdanoscu(tekst, monkeypatch):
    from shared import intake_classify as ic

    async def _model(t):
        return "other", 0.4
    monkeypatch.setattr(ic, "classify_llm", _model)
    assert await ic.classify(tekst) == {"document_type": "other", "confidence": 0.4, "method": "llm"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── Kroz stvaran tok: digitalni PDF → stvaran parser → stvaran worker → `intake_documents.document_type` ─────────

@pytest.mark.parametrize("redovi,tip,metod", [
    (PREDLOG_TUZBE_ASCII.split("\n"), "lawsuit", "heuristic"),
    (["OSNOVNI SUD U BEOGRADU", "Tuzeni: TEST BETA DOO", "ODGOVOR NA TUZBU",
      "Tuzeni osporava TUZBA navode i poziva se na UGOVOR o isporuci."], "response", "heuristic"),
    (["UGOVOR O ISPORUCI OPREME", "zakljucen 01.08.2026. izmedju TEST ALFA DOO i TEST BETA DOO",
      "Za sporove je nadlezan sud u Beogradu (TUZBA se podnosi tom sudu)."], "contract", "heuristic"),
    (ZAPISNIK_LAT.replace("š", "s").split("\n"), "other", "llm"),             # model iz fixture-a: other 0.5
    (["POTVRDA O DOPUNSKOJ ISPORUCI", "Po UGOVORU br. 12/2026 isporucena su 3 monitora 24.08.2026."], "other", "llm"),
])
def test_kroz_stvaran_worker_vrsta_iz_naslova(ok, redovi, tip, metod):
    from tests.test_ns005_t14_smart_intake import _obradi, _otpremi
    from tests.test_vcr002_t02_ocr_korpus import _digitalni_pdf, _job
    k, b = ok
    jid = _job(_otpremi(k, "A", _digitalni_pdf(redovi), ime="qa02.pdf"))
    assert _obradi() is True
    [d] = [x for x in b.tabele["intake_documents"] if x.get("intake_job_id") == jid]
    assert d["document_type"] == tip, d
    assert d["classification_method"] == metod
    assert d["classification_confidence"] == (0.85 if metod == "heuristic" else 0.5)   # poreklo i pouzdanost ostaju

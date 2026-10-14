# -*- coding: utf-8 -*-
"""
N08 — Legal Reliability: analiza presude (Pipeline A, `doc_type == "presuda"`).

Put: POST /api/predmeti/{id}/upload -> api.predmet_upload_auto_analyze ->
_PRESUDA_SYSTEM_PROMPT (5 sekcija) -> legacy FE `pred_renderPresuda`.

Svaki fixture je SINTETIČKA presuda; LLM je mokovan i vraća kontrolisan izlaz,
tako da test meri ono što BACKEND radi sa izlazom modela (čuvari), ne model.
Nema mreže: OpenAI, Pinecone (retrieve), Supabase i event bus su zamenjeni.

Ugovor pouzdanosti koji se meri:
  * citat koji nije u presudi ni u dostavljenom izvoru je IZRIČITO neproveren;
  * broj sudske odluke koji nije u presudi/izvoru je IZRIČITO neproveren;
  * skraćen tekst, neprepoznata izreka/obrazloženje, OCR i prazne strane su prijavljeni;
  * pomen roka i procena izgleda kao činjenica su označeni (sistem rok ne računa);
  * tuđ predmet -> 404 pre bilo kakvog poziva modela.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# `api` pravi OpenAI klijent pri importu; test nikad ne zove mrezu.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-n08")

import io
import json
import re
import subprocess
import types
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.datastructures import Headers
from starlette.requests import Request as StarletteRequest
from fastapi import HTTPException, UploadFile

import api

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── Sintetičke presude ──────────────────────────────────────────────────────

_ZAGLAVLJE = (
    "REPUBLIKA SRBIJA\nOSNOVNI SUD U NOVOM SADU\nP1 123/2024\nDana 12.03.2024. godine\n"
    "U IME NARODA\n"
    "Osnovni sud u Novom Sadu, sudija Petar Petrović, u parnici tužioca Marka Markovića protiv "
    "tuženog Društva Primer d.o.o., radi poništaja rešenja o otkazu, doneo je dana 12.03.2024. godine\n"
    "P R E S U D U\n"
)
_IZREKA = (
    "USVAJA SE tužbeni zahtev tužioca, pa se PONIŠTAVA rešenje tuženog o otkazu ugovora o radu "
    "od 01.06.2023. godine kao nezakonito.\n"
    "OBAVEZUJE SE tuženi da tužioca vrati na rad, u skladu sa članom 191. Zakona o radu.\n"
)
_OBRAZLOZENJE = (
    "O b r a z l o ž e nj e\n"
    "Tužilac je tužbom tražio poništaj rešenja o otkazu. Sud je utvrdio da tuženi pre donošenja "
    "rešenja nije dostavio tužiocu upozorenje u smislu člana 180. Zakona o radu, pa je otkaz "
    "nezakonit. Na osnovu člana 191. Zakona o radu sud je odlučio kao u izreci.\n"
)

PRESUDA_POTPUNA = _ZAGLAVLJE + _IZREKA + _OBRAZLOZENJE
PRESUDA_BEZ_IZREKE = _ZAGLAVLJE + _OBRAZLOZENJE
PRESUDA_BEZ_OBRAZLOZENJA = _ZAGLAVLJE + _IZREKA
PRESUDA_KONFLIKT = _ZAGLAVLJE + _IZREKA + (
    "O b r a z l o ž e nj e\n"
    "Sud nalazi da je tužbeni zahtev u celosti neosnovan, jer je tuženi dokazao da je tužiocu "
    "uredno dostavio upozorenje. Otkaz je zakonit.\n"
)
PRESUDA_KONTRADIKTORNI_DATUMI = PRESUDA_POTPUNA + (
    "Presuda je doneta dana 12.03.2023. godine u Novom Sadu.\n"
)
PRESUDA_DUGACKA = PRESUDA_POTPUNA + ("Sud je dalje cenio iskaz svedoka. " * 400)

# Odgovor iz pravne baze (format `app.services.retrieve`, zaglavlje ZAKON:/ČLAN:).
_IZVOR_ZR_191 = (
    "ZAKON: Zakon o radu\nČLAN: Član 191\n\nCITABILNI TEKST: Ako sud u toku postupka utvrdi da je "
    "zaposlenom prestao radni odnos bez pravnog osnova, na zahtev zaposlenog odlučiće da se zaposleni "
    "vrati na rad, da mu se isplati naknada štete i uplate pripadajući doprinosi.\n"
)


def _llm_izlaz(propisi: str = "1. Čl. 191 Zakona o radu", osnovi: str = None, procena: str = None,
               rezime: str = None) -> str:
    return (
        "1. REZIME PRESUDE\n"
        + (rezime or "Sud je usvojio tužbeni zahtev i poništio rešenje o otkazu jer tuženi nije dostavio upozorenje.")
        + "\n\n2. KLJUČNI ARGUMENTI SUDA\n1. Tuženi nije dostavio upozorenje pre otkaza.\n\n"
        "3. PRIMENJENI PROPISI\n" + propisi + "\n\n"
        "4. POTENCIJALNI ŽALBENI OSNOVI\n"
        + (osnovi or "1. Pogrešno utvrđeno činjenično stanje — sud nije cenio dokaz o dostavljanju upozorenja.")
        + "\n\n5. PROCENA IZGLEDA ŽALBE\n"
        + (procena or "NIZAK\nObrazloženje presude je dosledno i oslanja se na izvedene dokaze.")
        + "\n\nOva analiza je generisana uz pomoć AI i mora biti proverena od strane ovlašćenog advokata."
    )


# ── Harness ─────────────────────────────────────────────────────────────────

def _fake_user(uid: str = "user-n08-0001"):
    return types.SimpleNamespace(id=uid, email="advokat@primer.test")


def _fake_request():
    scope = {"type": "http", "method": "POST", "headers": [], "query_string": b"",
             "path": "/api/predmeti/pred-1/upload", "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


def _upload(name: str = "presuda.pdf") -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(b"%PDF-synthetic"),
                      headers=Headers({"content-type": "application/pdf"}))


async def _perm(user=None):
    return user


def _chain(data):
    c = MagicMock()
    for m in ["select", "eq", "insert", "execute", "single", "order", "limit", "is_", "gte", "or_"]:
        setattr(c, m, MagicMock(return_value=c))
    r = MagicMock(); r.data = data
    c.execute = MagicMock(return_value=r)
    return c


def _supa(istorija: list, vlasnik: bool = True):
    def _table(name):
        if name == "predmeti":
            c = MagicMock()
            for m in ("select", "eq", "single"):
                setattr(c, m, MagicMock(return_value=c))
            r = MagicMock(); r.data = {"id": "pred-1", "naziv": "Marković protiv Primer", "tip": "radno"} if vlasnik else None
            c.execute = MagicMock(return_value=r)
            return c
        if name == "predmet_dokumenti":
            c = _chain([])
            def _ins(payload):
                ic = MagicMock(); r = MagicMock(); r.data = [dict(payload, id="dok-1")]
                ic.execute = MagicMock(return_value=r)
                return ic
            c.insert = MagicMock(side_effect=_ins)
            return c
        if name == "predmet_istorija":
            c = _chain([])
            def _ins(payload):
                istorija.append(payload)
                return _chain([payload])
            c.insert = MagicMock(side_effect=_ins)
            return c
        return _chain([])
    s = MagicMock(); s.table = MagicMock(side_effect=_table)
    return s


def _oai(procena_izlaz: str, pozivi: list):
    def _create(*a, **kw):
        sistem = kw["messages"][0]["content"]
        pozivi.append(kw)
        r = MagicMock()
        if sistem.startswith("Ti si stručni pravni analitičar specijalizovan za srpsko pravo i analizu sudskih presuda"):
            sadrzaj = procena_izlaz
        elif "JSON array" in sistem:
            sadrzaj = "[]"
        else:
            sadrzaj = "{}"
        r.choices = [MagicMock(message=MagicMock(content=sadrzaj))]
        return r
    client = MagicMock(); client.chat.completions.create = MagicMock(side_effect=_create)
    return MagicMock(return_value=client)


async def _pokreni(tekst: str, izlaz: str, *, izvori=None, ocr=False, strane=None, ocr_conf=None,
                   vlasnik=True):
    istorija, pozivi = [], []
    with patch("api._require_auth", return_value=_fake_user()), \
         patch("api._get_supa", return_value=_supa(istorija, vlasnik)), \
         patch("api.PermissionService.require", return_value=_perm), \
         patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)), \
         patch("uploaded_doc.extractor.extract", return_value=(tekst, False, ocr, strane, ocr_conf)), \
         patch("uploaded_doc.chunker.chunk_document", return_value=types.SimpleNamespace(total_chunks=1)), \
         patch("uploaded_doc.ingest.ingest_session", return_value=1), \
         patch("routers.smart_intake._encrypt", return_value=b"ENC"), \
         patch("shared.rag_acl.dozvoljeni_predmeti", return_value=["pred-1"]), \
         patch("app.services.retrieve.retrieve_documents", return_value=(list(izvori or []), {})), \
         patch("services.event_bus.emit_durable", new=AsyncMock()), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()), \
         patch("openai.OpenAI", new=_oai(izlaz, pozivi)), \
         patch("api.UsageService.consume", new=AsyncMock()), \
         patch("api.UsageService.refund", new=AsyncMock()):
        rez = await api.predmet_upload_auto_analyze(
            "pred-1", _fake_request(), _upload(), authorization="Bearer test",
        )
    return rez, istorija, pozivi


def _citat(provera, clan):
    return [c for c in provera["citati"]["stavke"] if c["clan"] == clan]


# ── Prompt / šema ───────────────────────────────────────────────────────────

def test_prompt_trazi_pet_sekcija_i_zabranjuje_rok_i_procenat():
    p = api._PRESUDA_SYSTEM_PROMPT
    for k in ("1. REZIME PRESUDE", "2. KLJUČNI ARGUMENTI SUDA", "3. PRIMENJENI PROPISI",
              "4. POTENCIJALNI ŽALBENI OSNOVI", "5. PROCENA IZGLEDA ŽALBE"):
        assert k in p
    assert "NIKADA ne izmišljaj broj člana" in p
    # N08: rok i procenat nisu stvar modela
    assert "Ne izračunavaj i ne navodi rok za žalbu" in p
    assert "Ne navodi procenat" in p
    assert "Ako u tekstu nema izreke ili obrazloženja" in p


# ── Adversarijalni fixture-i kroz pravi kod sa mokovanim modelom ────────────

@pytest.mark.anyio
async def test_f0_potpuna_presuda_citat_potvrdjen_u_izvoru_i_presudi():
    rez, istorija, _ = await _pokreni(PRESUDA_POTPUNA, _llm_izlaz(), izvori=[_IZVOR_ZR_191])
    assert rez["doc_type"] == "presuda"
    pv = rez["provera_presude"]
    assert pv["delovi"] == {"izreka_prepoznata": True, "obrazlozenje_prepoznato": True}
    assert pv["obuhvat"]["skraceno"] is False
    [c191] = _citat(pv, "191")
    assert c191["status"] == "POTVRDJEN_U_IZVORU" and c191["u_presudi"] is True
    assert pv["citati"]["status"] == "PROVERENI"
    assert pv["upozorenja"] == []


@pytest.mark.anyio
async def test_f1_nedostaje_izreka_prijavljeno():
    rez, _, _ = await _pokreni(PRESUDA_BEZ_IZREKE, _llm_izlaz(), izvori=[_IZVOR_ZR_191])
    pv = rez["provera_presude"]
    assert pv["delovi"]["izreka_prepoznata"] is False
    assert any("izreka" in u for u in pv["upozorenja"])


@pytest.mark.anyio
async def test_f2_nedostaje_obrazlozenje_prijavljeno():
    rez, _, _ = await _pokreni(PRESUDA_BEZ_OBRAZLOZENJA, _llm_izlaz(), izvori=[_IZVOR_ZR_191])
    pv = rez["provera_presude"]
    assert pv["delovi"]["obrazlozenje_prepoznato"] is False
    assert pv["delovi"]["izreka_prepoznata"] is True
    assert any("obrazloženje" in u for u in pv["upozorenja"])


@pytest.mark.anyio
async def test_f3_konflikt_izreke_i_obrazlozenja_nije_detektovan_deterministicki():
    """Dokumentovan jaz: sistem NE poredi smisao izreke i obrazloženja — oba dela su prisutna."""
    rez, _, _ = await _pokreni(PRESUDA_KONFLIKT, _llm_izlaz(), izvori=[_IZVOR_ZR_191])
    pv = rez["provera_presude"]
    assert pv["delovi"] == {"izreka_prepoznata": True, "obrazlozenje_prepoznato": True}
    assert not any("protivre" in u for u in pv["upozorenja"])


@pytest.mark.anyio
async def test_f4_skenirana_presuda_sa_praznim_stranama_prijavljena():
    strane = [PRESUDA_POTPUNA, "   ", "\n"]
    rez, _, _ = await _pokreni(PRESUDA_POTPUNA, _llm_izlaz(), izvori=[_IZVOR_ZR_191],
                               ocr=True, strane=strane, ocr_conf=0.41)
    pv = rez["provera_presude"]
    assert pv["ocr"] == {"koriscen": True, "pouzdanost": 0.41, "strane_bez_teksta": [2, 3]}
    assert any("OCR" in u for u in pv["upozorenja"])
    assert any("2, 3" in u for u in pv["upozorenja"])


@pytest.mark.anyio
async def test_f5_nepostojeci_clan_izricito_neproveren():
    izlaz = _llm_izlaz(propisi="1. Čl. 191 Zakona o radu\n2. Čl. 999 Zakona o parničnom postupku")
    rez, istorija, _ = await _pokreni(PRESUDA_POTPUNA, izlaz, izvori=[_IZVOR_ZR_191])
    pv = rez["provera_presude"]
    [c999] = _citat(pv, "999")
    assert c999["status"] == "NEPROVEREN" and c999["u_presudi"] is False
    assert pv["citati"]["status"] == "NEPROVERENI"
    assert any("999" in u for u in pv["upozorenja"])
    # trag ostaje i u sačuvanoj istoriji (ponovno otvaranje ne briše oznaku)
    auto = [r for r in istorija if r["pitanje"].startswith("[Auto-analiza]")]
    assert auto and "999" in auto[0]["odgovor"].split("PROVERA SISTEMA")[1]


@pytest.mark.anyio
async def test_f5b_clan_naveden_u_presudi_ali_bez_izvora_nije_potvrdjen():
    rez, _, _ = await _pokreni(PRESUDA_POTPUNA, _llm_izlaz(propisi="1. Čl. 180 Zakona o radu"), izvori=[])
    [c180] = _citat(rez["provera_presude"], "180")
    assert c180["status"] == "NAVEDEN_U_PRESUDI" and c180["u_presudi"] is True


@pytest.mark.anyio
async def test_f6_zalbeni_osnov_bez_osnova_u_presudi_neproveren_citat():
    izlaz = _llm_izlaz(osnovi="1. Bitna povreda iz člana 374. stav 2. tačka 12. ZPP — presuda nema razloga.")
    rez, _, _ = await _pokreni(PRESUDA_POTPUNA, izlaz, izvori=[_IZVOR_ZR_191])
    [c374] = _citat(rez["provera_presude"], "374")
    assert c374["status"] == "NEPROVEREN"


@pytest.mark.anyio
async def test_f7_kontradiktorni_datumi_nisu_detektovani():
    """Dokumentovan jaz: dva različita datuma donošenja se ne porede."""
    rez, _, _ = await _pokreni(PRESUDA_KONTRADIKTORNI_DATUMI, _llm_izlaz(), izvori=[_IZVOR_ZR_191])
    assert not any("datum" in u.lower() for u in rez["provera_presude"]["upozorenja"])


@pytest.mark.anyio
async def test_f8_nepostojeca_odluka_izricito_neproverena():
    izlaz = _llm_izlaz(osnovi="1. Pogrešna primena materijalnog prava — protivno stavu VKS u odluci Rev 9999/2023.")
    rez, _, _ = await _pokreni(PRESUDA_POTPUNA, izlaz, izvori=[_IZVOR_ZR_191])
    odl = rez["provera_presude"]["odluke"]
    assert {"oznaka": "Rev 9999/2023", "u_presudi": False, "u_izvoru": False, "status": "NEPROVERENA"} in odl
    assert any("Rev 9999/2023" in u for u in rez["provera_presude"]["upozorenja"])


@pytest.mark.anyio
async def test_f8b_broj_same_presude_je_naveden_u_presudi():
    izlaz = _llm_izlaz(rezime="Presudom P1 123/2024 sud je usvojio tužbeni zahtev.")
    rez, _, _ = await _pokreni(PRESUDA_POTPUNA, izlaz, izvori=[_IZVOR_ZR_191])
    [o] = [o for o in rez["provera_presude"]["odluke"] if o["oznaka"].startswith("P1")]
    assert o["status"] == "NAVEDENA_U_PRESUDI"


@pytest.mark.anyio
async def test_f9_izmisljen_rok_i_procenat_oznaceni():
    izlaz = _llm_izlaz(procena="VISOK\nŽalba će sigurno uspeti (85%). Rok za žalbu ističe 27.03.2024.")
    rez, _, _ = await _pokreni(PRESUDA_POTPUNA, izlaz, izvori=[_IZVOR_ZR_191])
    pv = rez["provera_presude"]
    assert pv["rok_pomenut"] is True
    assert pv["procena_kao_cinjenica"] is True
    assert any("rok" in u.lower() for u in pv["upozorenja"])


@pytest.mark.anyio
async def test_f10_skracen_tekst_prijavljen():
    rez, _, pozivi = await _pokreni(PRESUDA_DUGACKA, _llm_izlaz(), izvori=[_IZVOR_ZR_191])
    ob = rez["provera_presude"]["obuhvat"]
    assert ob["skraceno"] is True and ob["analizirano_znakova"] == 8000
    assert ob["ukupno_znakova"] == len(PRESUDA_DUGACKA)
    assert any("8000" in u or "8.000" in u for u in rez["provera_presude"]["upozorenja"])


@pytest.mark.anyio
async def test_f11_tudji_predmet_404_bez_poziva_modela():
    with pytest.raises(HTTPException) as e:
        await _pokreni(PRESUDA_POTPUNA, _llm_izlaz(), vlasnik=False)
    assert e.value.status_code == 404


@pytest.mark.anyio
async def test_ne_presuda_nema_provere_presude():
    rez, _, _ = await _pokreni("Ugovor o zakupu zaključen između strana ugovornica.", "Procena.")
    assert rez["doc_type"] != "presuda"
    assert rez["provera_presude"] is None


def test_negativna_kontrola_bez_laznih_upozorenja():
    """'Sud ističe da…' nije rok; 'ne garantuje' nije predviđanje; zakonski glasnik nije odluka."""
    izlaz = _llm_izlaz(
        rezime="Sud ističe da tuženi nije dostavio upozorenje (Sl. glasnik RS, br. 24/2005, 61/2005).",
        procena="SREDNJI\nAnaliza ne garantuje ishod; obrazloženje ima slabosti.",
    )
    pv = api._provera_analize_presude(izlaz, PRESUDA_POTPUNA, [_IZVOR_ZR_191], 8000)
    assert pv["rok_pomenut"] is False
    assert pv["procena_kao_cinjenica"] is False
    assert pv["odluke"] == []
    assert pv["upozorenja"] == []


def test_cirilicna_presuda_i_citat():
    presuda = "ОСНОВНИ СУД\nП 5/2024\nУСВАЈА СЕ тужбени захтев на основу члана 191. Закона о раду.\nО б р а з л о ж е њ е\nСуд је утврдио…"
    pv = api._provera_analize_presude(_llm_izlaz(), presuda, [_IZVOR_ZR_191], 8000)
    assert pv["delovi"] == {"izreka_prepoznata": True, "obrazlozenje_prepoznato": True}
    [c] = _citat(pv, "191")
    assert c["u_presudi"] is True and c["status"] == "POTVRDJEN_U_IZVORU"


def test_provera_pad_cuvara_je_nepoznato_nikad_provereno():
    with patch("main._klasifikuj_citate", side_effect=RuntimeError("x")):
        pv = api._provera_analize_presude(_llm_izlaz(), PRESUDA_POTPUNA, [_IZVOR_ZR_191], 8000)
    assert pv["citati"]["status"] == "NEPOZNATO"
    assert any("nije izvršena" in u for u in pv["upozorenja"])


# ── Prikaz (legacy FE) ──────────────────────────────────────────────────────

def _render(tekst: str, provera) -> str:
    js = (REPO_ROOT / "static" / "vindex.js").read_text(encoding="utf-8-sig")
    m = re.search(r"function pred_renderPresuda\(tekst, provera\) \{.*?\n\}\r?\n", js, re.S)
    assert m, "pred_renderPresuda(tekst, provera) nije pronađen"
    pm = re.search(r"function pred_renderPresudaProvera\(provera\) \{.*?\n\}\r?\n", js, re.S)
    assert pm, "pred_renderPresudaProvera(provera) nije pronađen"
    skript = (
        "function escHtml(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;');}\n"
        + pm.group(0) + m.group(0)
        + "\nprocess.stdout.write(pred_renderPresuda(" + json.dumps(tekst) + "," + json.dumps(provera) + "));\n"
    )
    r = subprocess.run(["node", "-e", skript], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_prikaz_razlikuje_ai_analizu_i_oznacava_neproverene():
    pv = api._provera_analize_presude(
        _llm_izlaz(propisi="1. Čl. 191 Zakona o radu\n2. Čl. 999 Zakona o parničnom postupku"),
        PRESUDA_BEZ_IZREKE, [_IZVOR_ZR_191], 8000,
    )
    html = _render(_llm_izlaz(propisi="1. Čl. 999 Zakona o parničnom postupku"), pv)
    assert "AI analiza" in html and "nije tekst presude" in html
    assert "NEPROVEREN" in html and "999" in html
    assert "izreka" in html
    assert "AI procena" in html            # bedž izgleda žalbe nije činjenica
    assert "predlog za proveru advokata" in html


def test_prikaz_bez_provere_ne_tvrdi_proverenost():
    html = _render(_llm_izlaz(), None)
    assert "AI analiza" in html
    assert "nije izvršena" in html


# ── Nezavisna recenzija (2026-10-14): "pravna baza" = samo zvanični korpus ──

# Advokatov sopstveni pasus (format `doc_formatter.format_doc_passage`) — NIJE pravna baza.
_IZVOR_ADVOKATOV_NACRT = (
    "KORISNIKOV DOKUMENT — OVAJ PREDMET [nacrt_zalbe.docx, chunk 0]\n\n"
    "Nacrt žalbe: prema stavu Vrhovnog suda Rev 9999/2023, primenjuje se član 999 Zakona o "
    "parničnom postupku."
)
# Ručno pisane ZR napomene koje upload ubacuje za radne sporove — NISU pasus iz korpusa.
_ZR_NAPOMENE = "ZR Član 176: Poslodavac može otkazati ugovor o radu bez otkaznog roka zaposlenom..."
_IZVOR_PRAKSA_REV = (
    "SUDSKA PRAKSA [Vrhovni sud, Rev 1234/2020, 01.02.2021]\nOblast: radno pravo\n\n"
    "Zaposleni kome je nezakonito prestao radni odnos ima pravo na vraćanje na rad."
)


def test_r1_advokatov_dokument_nije_pravna_baza():
    """Izmišljen član i odluka iz advokatovog nacrta ne smeju postati '✓ u izvoru iz pravne baze'."""
    izlaz = _llm_izlaz(
        propisi="1. Čl. 999 Zakona o parničnom postupku",
        osnovi="1. Prema odluci Rev 9999/2023 sud je pogrešio.",
    )
    pv = api._provera_analize_presude(izlaz, PRESUDA_POTPUNA, [_IZVOR_ADVOKATOV_NACRT], 8000)
    [c999] = _citat(pv, "999")
    assert c999["u_izvoru"] is False and c999["status"] == "NEPROVEREN"
    assert pv["citati"]["status"] == "NEPROVERENI"
    [rev] = [o for o in pv["odluke"] if "9999" in o["oznaka"]]
    assert rev["u_izvoru"] is False and rev["status"] == "NEPROVERENA"


def test_r1b_odluka_iz_sudske_prakse_jeste_u_izvoru():
    """Pozitivna kontrola: broj odluke iz SUDSKA PRAKSA pasusa ostaje 'u izvoru'."""
    izlaz = _llm_izlaz(osnovi="1. Vrhovni sud je u odluci Rev 1234/2020 zauzeo isti stav.")
    pv = api._provera_analize_presude(izlaz, PRESUDA_POTPUNA, [_IZVOR_PRAKSA_REV], 8000)
    [rev] = [o for o in pv["odluke"] if "1234" in o["oznaka"]]
    assert rev["status"] == "U_IZVORU"


def test_r1c_uputstvo_hijerarhije_i_zr_napomene_nisu_izvor():
    from app.services.doc_formatter import ORIGIN_HIERARCHY_INSTRUCTIONS
    izlaz = _llm_izlaz(propisi="1. Čl. 176 Zakona o radu")
    pv = api._provera_analize_presude(
        izlaz, PRESUDA_POTPUNA, [ORIGIN_HIERARCHY_INSTRUCTIONS, _ZR_NAPOMENE], 8000)
    [c176] = _citat(pv, "176")
    assert c176["u_izvoru"] is False and c176["status"] == "NEPROVEREN"


def test_r2_broj_clana_bez_zakona_nije_potvrda():
    """ARTICLE_PRESENT (broj se negde pojavljuje) se ne prikazuje kao 'potvrđen'."""
    izlaz = _llm_izlaz(propisi="1. član 176")
    pv = api._provera_analize_presude(izlaz, PRESUDA_POTPUNA, [_IZVOR_ZR_191, _ZR_NAPOMENE], 8000)
    [c176] = _citat(pv, "176")
    assert c176["u_izvoru"] is False and c176["status"] == "NEPROVEREN"
    # ni kad je broj u pasusu iz korpusa, ali bez naziva zakona u analizi
    pv2 = api._provera_analize_presude(_llm_izlaz(propisi="1. član 191"), _ZAGLAVLJE + _OBRAZLOZENJE[:60],
                                       [_IZVOR_ZR_191], 8000)
    [c191] = _citat(pv2, "191")
    assert c191["status"] != "POTVRDJEN_U_IZVORU"


def test_r3_naveden_u_presudi_vezan_za_zakon():
    """'čl. 200 ZOO' u analizi nije 'naveden u presudi' kad presuda navodi čl. 200 ZPP."""
    presuda = PRESUDA_POTPUNA + "Odluka o troškovima doneta je na osnovu člana 200 Zakona o parničnom postupku.\n"
    pv = api._provera_analize_presude(_llm_izlaz(propisi="1. čl. 200 ZOO"), presuda, [], 8000)
    [c200] = _citat(pv, "200")
    assert c200["u_presudi"] is False and c200["status"] == "NEPROVEREN"
    assert pv["citati"]["status"] == "NEPROVERENI"
    # pozitivna kontrola: isti zakon -> naveden u presudi
    pv2 = api._provera_analize_presude(_llm_izlaz(propisi="1. čl. 200 ZPP"), presuda, [], 8000)
    [d200] = _citat(pv2, "200")
    assert d200["u_presudi"] is True and d200["status"] == "NAVEDEN_U_PRESUDI"


def test_r4_nan_ocr_pouzdanost_ne_ruši():
    pv = api._provera_analize_presude(_llm_izlaz(), PRESUDA_POTPUNA, [_IZVOR_ZR_191], 8000,
                                      ocr_koriscen=True, ocr_pouzdanost=float("nan"))
    assert any("OCR" in u for u in pv["upozorenja"])


@pytest.mark.anyio
async def test_r4b_pad_provere_posle_cuvanja_nije_500():
    """Dokument je već sačuvan — pad provere vraća NEPOZNATO, ne 500 i ne 'provereno'."""
    with patch("api._provera_analize_presude", side_effect=RuntimeError("n08-test")):
        rez, istorija, _ = await _pokreni(PRESUDA_POTPUNA, _llm_izlaz(), izvori=[_IZVOR_ZR_191])
    pv = rez["provera_presude"]
    assert pv["citati"]["status"] == "NEPOZNATO" and pv["citati"]["stavke"] == []
    assert any("nije izvršena" in u for u in pv["upozorenja"])
    auto = [r for r in istorija if r["pitanje"].startswith("[Auto-analiza]")]
    assert auto and "nije izvršena" in auto[0]["odgovor"].split("PROVERA SISTEMA")[1]


def test_r5_istorija_bez_upozorenja_i_dalje_nosi_trag_provere():
    pv = api._provera_analize_presude(_llm_izlaz(), PRESUDA_POTPUNA, [_IZVOR_ZR_191], 8000)
    trag = api._provera_presude_tekst(pv)
    assert "PROVERA SISTEMA" in trag
    assert api._provera_presude_tekst(None) == ""


def test_r5b_ponovno_otvaranje_iz_istorije_prikazuje_sacuvanu_proveru():
    """Istorija prosleđuje samo tekst; upozorenja ne smeju završiti u sekciji 5 (AI procena)."""
    pv = api._provera_analize_presude(
        _llm_izlaz(propisi="1. Čl. 999 Zakona o parničnom postupku"), PRESUDA_POTPUNA, [_IZVOR_ZR_191], 8000)
    sacuvano = _llm_izlaz(propisi="1. Čl. 999 Zakona o parničnom postupku") + api._provera_presude_tekst(pv)
    html = _render(sacuvano, None)
    assert "Provera sistema nije izvršena" not in html
    assert "Provera sistema (nije deo AI analize)" in html
    i_box = html.index("Provera sistema (nije deo AI analize)")
    i_sek5 = html.index("Procena izgleda žalbe")
    assert i_box < i_sek5 and "999" in html[i_box:i_sek5]
    assert "PROVERA SISTEMA (nije deo analize modela)" not in html[i_sek5:]


def test_r1d_zaglavlje_zakona_unutar_advokatovog_dokumenta_nije_izvor():
    """Advokatov dokument sa nalepljenim 'ZAKON:/ČLAN:' redovima (npr. kopija ranijeg izlaza) nije korpus."""
    nalepljeno = (
        "KORISNIKOV DOKUMENT — RANIJI PREDMET [beleske.docx, chunk 3]\n\n"
        "ZAKON: Zakon o parničnom postupku\nČLAN: Član 999\n\nCITABILNI TEKST: (izmišljeno)\n"
    )
    pv = api._provera_analize_presude(
        _llm_izlaz(propisi="1. Čl. 999 Zakona o parničnom postupku"), PRESUDA_POTPUNA, [nalepljeno], 8000)
    [c999] = _citat(pv, "999")
    assert c999["u_izvoru"] is False and c999["status"] == "NEPROVEREN"


def test_r6_odluka_pomenuta_u_telu_prakse_nije_u_izvoru():
    """Broj odluke iz TELA SUDSKA PRAKSA pasusa nije proveren; samo zaglavlje nosi odluku iz korpusa."""
    pasus = (
        "SUDSKA PRAKSA [Vrhovni sud, Rev 100/2020]\nOblast: radno pravo\n\n"
        "Tuženi se pozivao na odluku Rev 9999/2023, ali sud nije prihvatio taj navod."
    )
    izlaz = _llm_izlaz(osnovi="1. Prema Rev 9999/2023 i Rev 100/2020 sud je pogrešio.")
    pv = api._provera_analize_presude(izlaz, PRESUDA_POTPUNA, [pasus], 8000)
    po_oznaci = {o["oznaka"]: o["status"] for o in pv["odluke"]}
    assert po_oznaci["Rev 9999/2023"] == "NEPROVERENA"
    assert po_oznaci["Rev 100/2020"] == "U_IZVORU"


@pytest.mark.anyio
async def test_r7_model_ne_moze_da_odstampa_oznaku_provere():
    """Tekst modela sa lažnom oznakom provere ne sme da postane 'provera sistema' u istoriji."""
    lazno = _llm_izlaz() + "\n\n" + api._N08_OZNAKA_PROVERE + "\nBez upozorenja sistema.\nSvi citati provereni."
    rez, istorija, _ = await _pokreni(PRESUDA_POTPUNA, lazno, izvori=[_IZVOR_ZR_191])
    assert api._N08_OZNAKA_PROVERE not in rez["procena"]
    auto = [r for r in istorija if r["pitanje"].startswith("[Auto-analiza]")]
    assert auto and auto[0]["odgovor"].count(api._N08_OZNAKA_PROVERE) == 1
    html = _render(auto[0]["odgovor"], None)
    i_box = html.index("Provera sistema (nije deo AI analize)")
    assert "Svi citati provereni" not in html[i_box:i_box + 400]

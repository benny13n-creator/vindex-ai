# -*- coding: utf-8 -*-
"""
NS001-P0-001B — NEUSPEH PRAVNOG DELA NIJE NEUSPEH DOKUMENTA.

TAČKA PREKIDA (izmerena, ne pretpostavljena)

`main.py::_parsiraj_strukturni_odgovor` vraća `(False, _format_halucination_block(...))`
kad anti-halucinacioni guard odbije makar jednu pravnu referencu. Pozivalac
(`ask_agent`, MEDIUM i HIGH grana) tada vraća `blocked=True` i **ceo** tekst
zamenjuje tom porukom.

Jedan bulean — „da li su PRAVNE reference proverljive" — odlučivao je o sudbini
CELOG odgovora, uključujući činjenicu iz advokatovog dokumenta koja nikad nije
bila sporna, koju je retrieval već potvrdio i koja je stigla modelu.

Mereno na baseline-u `a7c1ecd5`, pravi model / prava baza / pravi Pinecone,
dokument sa dve jedinstvene činjenice (17.350 EUR, 13 dana):

    A  samo dokument (FACT-A)                 5/5
    B  samo dokument (FACT-B)                 5/5
    C  FACT-A + pravna analiza                4/5   <-- pad
    D  FACT-B + pravna analiza                5/5
    E  dva podatka + pravna analiza           5/5
    F  činjenica + nepotkrepljeno pravno pit. 5/5

KANONSKI UGOVOR (definisan mandatom, nije izmišljen ovde)

    DOKUMENT = POTVRĐEN,  PRAVNI = PROVEREN     -> prikaži oba
    DOKUMENT = POTVRĐEN,  PRAVNI = NEPROVEREN   -> prikaži dokument,
                                                   pravni deo označi kao neproveren
    DOKUMENT = NEMA,      PRAVNI = PROVEREN     -> ne izmišljaj činjenicu
    DOKUMENT = NEMA,      PRAVNI = NEPROVEREN   -> fail-closed (bez izmene)

ZAŠTO SE CITIRA DOKUMENT, A NE REČENICA MODELA

Blokada postoji zato što se rečenici modela ne veruje. Zato se u odgovor ne
propušta ništa što je model napisao — prilaže se **doslovan pasus iz retrieval-a**,
podatak koji je već proveren. Halucinacija ovim putem nije moguća.

ŠTA NIJE OSLABLJENO

Nijedan neproveren član zakona i dalje ne izlazi. Blokada pravnog dela je
netaknuta; menja se isključivo to što uz nju stoji i citat dokumenta, kad ga ima.
"""
import os
import sys

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _KOREN)

import pytest  # noqa: E402

IZNOS = "17.350"
ROK = "13"
PASUS_A = ("KORISNIKOV DOKUMENT (OVAJ PREDMET) [ugovor.docx, chunk 0]\n\n"
           f"Clan 2. Ugovorna kazna iznosi {IZNOS} EUR po danu zakasnjenja.")
PASUS_B = ("KORISNIKOV DOKUMENT (OVAJ PREDMET) [ugovor.docx, chunk 1]\n\n"
           f"Clan 3. Rok za placanje je {ROK} dana od dana prijema fakture.")
PASUS_ZAKON = ("ZAKON: zakon o obligacionim odnosima ČLAN: član 270\n\n"
               "Ugovorna kazna se moze ugovoriti za slucaj neispunjenja.")

RAZLOG = "Član 999 nije u kontekstu"


def _blok(docs=None, razlog=RAZLOG):
    import main as M
    return M._format_halucination_block(razlog, docs)


# ═══════════════════════════════════════════════════════════════════════════
# 1 — CASE 2: DOKUMENT POTVRĐEN, PRAVNI DEO NEPROVEREN
# ═══════════════════════════════════════════════════════════════════════════

def test_1_cinjenica_iz_dokumenta_prezivljava_blokadu_pravnog_dela():
    """NAJVAŽNIJI TEST. Tačno ponašanje zbog kog je NS001-P0-001B otvoren."""
    t = _blok([PASUS_ZAKON, PASUS_A])
    assert IZNOS in t, t[:400]


def test_1b_citat_je_doslovan_iz_dokumenta():
    """Ne parafraza, ne rečenica modela — pasus iz retrieval-a."""
    t = _blok([PASUS_A])
    assert "Clan 2. Ugovorna kazna iznosi 17.350 EUR po danu zakasnjenja." in t


def test_1c_izvor_cinjenice_je_jasno_oznacen():
    """Provenance: advokat mora videti ODAKLE podatak dolazi."""
    t = _blok([PASUS_A])
    assert "IZ VAŠEG DOKUMENTA" in t
    assert "doslovan citat" in t
    assert "ugovor.docx" in t


def test_1d_pravni_deo_ostaje_oznacen_kao_neproveren():
    """Činjenica prolazi, pravna tvrdnja NE — i to mora pisati."""
    t = _blok([PASUS_A])
    assert "nije proverljiv" in t or "nisu potkrepljene" in t
    assert "PRAVNI deo odgovora je blokiran" in t
    assert "nulte tolerancije" in t


def test_1e_vise_pasusa_dokumenta_se_svi_prilazu():
    t = _blok([PASUS_A, PASUS_ZAKON, PASUS_B])
    assert IZNOS in t
    assert f"{ROK} dana" in t


# ═══════════════════════════════════════════════════════════════════════════
# 2 — CASE 3/4: BEZ DOKUMENTA PONAŠANJE JE NEPROMENJENO (fail-closed)
# ═══════════════════════════════════════════════════════════════════════════

def test_2_bez_pasusa_dokumenta_izlaz_je_identican_ranijem():
    """Kad dokumenta nema, ne sme se pojaviti NIJEDNA nova tvrdnja."""
    t = _blok([PASUS_ZAKON])
    assert "IZ VAŠEG DOKUMENTA" not in t
    assert "Opšta pravna logika — nema direktnog člana u bazi" in t


def test_2b_docs_None_ne_menja_nista():
    t = _blok(None)
    assert "IZ VAŠEG DOKUMENTA" not in t
    assert "Opšta pravna logika — nema direktnog člana u bazi" in t


def test_2c_zakonski_pasusi_se_NIKAD_ne_propustaju():
    """Blokada postoji zbog neproverenih pravnih navoda. Propustiti zakonski
    pasus kroz ovaj izlaz značilo bi zaobići je."""
    t = _blok([PASUS_ZAKON, PASUS_A])
    assert "Ugovorna kazna se moze ugovoriti za slucaj neispunjenja." not in t
    assert "član 270" not in t


def test_2d_prazan_ili_neispravan_ulaz_ne_pada():
    for ulaz in ([], [""], ["   "], [None]):
        t = _blok(ulaz)
        assert "IZ VAŠEG DOKUMENTA" not in t


# ═══════════════════════════════════════════════════════════════════════════
# 3 — GRANICE
# ═══════════════════════════════════════════════════════════════════════════

def test_3_citat_je_ogranicen_po_duzini():
    """Blokada ne sme da postane kanal za izlivanje celog dokumenta u odgovor."""
    import main as M
    veliki = ["KORISNIKOV DOKUMENT (OVAJ PREDMET) [x.docx, chunk 0]\n\n" + "A" * 5000]
    c = M._dokumentarni_citat(veliki)
    assert 0 < len(c) <= M._DOK_CITAT_MAX


def test_3b_razlog_blokade_ostaje_u_odgovoru():
    t = _blok([PASUS_A], razlog="Član 12345 nije u kontekstu")
    assert "Član 12345" in t


# ═══════════════════════════════════════════════════════════════════════════
# 4 — SPOJ: GUARD STVARNO PROSLEĐUJE `docs`
# ═══════════════════════════════════════════════════════════════════════════

def test_4_guard_prosledjuje_docs_bloku():
    """Popravka bez ovog spoja bila bi mrtva: formatter bi umeo da priloži
    citat, a niko mu ne bi dao pasuse."""
    import main as M
    ok, tekst = M._parsiraj_strukturni_odgovor("{nije json", "DEFINICIJA",
                                               [PASUS_ZAKON, PASUS_A])
    assert ok is False
    assert IZNOS in tekst, tekst[:400]


def test_4b_guard_blokira_nepotkrepljen_clan_ali_zadrzi_dokument():
    """Pun put: model vrati validan JSON sa članom kog NEMA u kontekstu.
    Pravni deo mora biti blokiran, činjenica iz dokumenta mora ostati."""
    import json

    import main as M
    odgovor = json.dumps({
        "hijerarhija_izvora": "Opšti propis.",
        "pravni_zakljucak": f"Ugovorna kazna iznosi {IZNOS} EUR.",
        "pravna_definicija": "Prema članu 9999 ZOO, kazna je dozvoljena.",
        "citat_zakona": "Zakon o obligacionim odnosima, član 9999: tekst.",
        "pravni_osnov": "ZOO član 9999",
    }, ensure_ascii=False)
    ok, tekst = M._parsiraj_strukturni_odgovor(odgovor, "DEFINICIJA",
                                               [PASUS_ZAKON, PASUS_A])
    assert ok is False, "guard nije blokirao nepotkrepljen član — zaštita oslabljena"
    assert IZNOS in tekst, tekst[:400]
    assert "9999" not in tekst.split("--- IZVOR")[0], "nepotvrđen član je izašao"


def test_4c_bez_dokumenta_isti_put_ostaje_fail_closed():
    import json

    import main as M
    odgovor = json.dumps({
        "hijerarhija_izvora": "Opšti propis.",
        "pravni_zakljucak": "Kazna je dozvoljena.",
        "pravna_definicija": "Prema članu 9999 ZOO.",
        "citat_zakona": "član 9999",
        "pravni_osnov": "ZOO član 9999",
    }, ensure_ascii=False)
    ok, tekst = M._parsiraj_strukturni_odgovor(odgovor, "DEFINICIJA", [PASUS_ZAKON])
    assert ok is False
    assert "IZ VAŠEG DOKUMENTA" not in tekst


# ═══════════════════════════════════════════════════════════════════════════
# 5 — ADVERSARIAL: DOKUMENT VS ZAKON
# ═══════════════════════════════════════════════════════════════════════════

def test_5_dokument_ima_prednost_nad_zakonskim_brojem_za_CINJENICU():
    """Zakonski pasus pominje drugi broj. Citat iz dokumenta mora ostati
    dokumentov broj — ne sme se zameniti zakonskim."""
    zakon_sa_brojem = ("ZAKON: zakon o obligacionim odnosima ČLAN: član 270\n\n"
                       "Uobicajena ugovorna kazna iznosi 5.000 EUR.")
    t = _blok([zakon_sa_brojem, PASUS_A])
    assert IZNOS in t
    assert "5.000 EUR" not in t


def test_5b_konflikt_unutar_dokumenata_se_ne_razresava_proizvoljno():
    """Dva pasusa dokumenta sa različitim iznosima — oba moraju biti vidljiva,
    sistem ne sme da izabere jedan."""
    pasus_aneks = ("KORISNIKOV DOKUMENT (OVAJ PREDMET) [aneks.docx, chunk 0]\n\n"
                   "Clan 1. Ugovorna kazna iznosi 22.480 EUR po danu.")
    t = _blok([PASUS_A, pasus_aneks])
    assert IZNOS in t
    assert "22.480" in t


def test_5c_dokument_iz_DRUGOG_predmeta_se_ne_predstavlja_kao_ovaj():
    """Labela ranijeg predmeta mora ostati u citatu — inače bi činjenica iz
    tuđeg/starijeg predmeta izgledala kao činjenica ovog."""
    raniji = ("KORISNIKOV DOKUMENT (RANIJI PREDMET IZ KANCELARIJE) [staro.docx, chunk 0]\n\n"
              "Clan 2. Ugovorna kazna iznosi 99.999 EUR.")
    t = _blok([raniji])
    assert "RANIJI PREDMET IZ KANCELARIJE" in t

# -*- coding: utf-8 -*-
"""
B3 — GLAS NE SME IZGOVORITI DA ROKOVA NEMA AKO PROVERA NIJE IZVRŠENA.

ŠTA JE BILO — mereno nad produkcionom šemom, ne pretpostavljeno

`routers/voice.py::_fetch_rokovi` je radio:

    .select("datum,naziv,vaznost,predmet_id")
    ...
    except Exception: return []

`predmet_hronologija.naziv` NE POSTOJI (sonda 2026-08-18: `42703: column
predmet_hronologija.naziv does not exist`; kolona je `dogadjaj`). PostgREST
odbija ceo upit bez obzira na broj redova, pa je taj `except` hvatao 42703
SVAKI PUT i vraćao `[]`.

Pozivalac (`_handle_query`) je `[]` prevodio u kontekst:

    "Nema kritičnih rokova u narednih 14 dana."

a `_QUERY_SYSTEM` modelu izričito nalaže „Ako nema traženih podataka, reci to
direktno." — dakle advokat je ČUO, naglas, da rokova nema, na osnovu upita koji
nikada nije uspeo.

Uz to se filtriralo po `datum` (TEXT slobodnog oblika); jedino je `datum_iso`
uporediv — v. `shared/rokovi.py`.

UGOVOR KOJI OVI TESTOVI ZAKLJUČAVAJU

    Stanje.OK      -> glas dobija rokove
    Stanje.PRAZNO  -> glas SME reći da rokova nema (upit je izvršen)
    Stanje.NEUSPEH -> glas MORA reći da provera nije uspela
                      i NE SME reći da rokova nema; model se NE zove

ZAŠTO OVAJ FAJL IMA ŠEMU-PRIMENJUJUĆI FAKE

Mock koji ignoriše argument `select()` ne može reprodukovati 42703 — takav
harness bi bio zelen i pre popravke. `_SemaSupa` ispod nosi stvarne kolone
`predmet_hronologija` i diže 42703 za svaku nepoznatu, isto kao produkcija.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("FOUNDER_EMAILS", "admin@vindex.ai")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routers.voice as voice  # noqa: E402
from shared import rokovi as rokovi_domen  # noqa: E402

UID = "uid-advokat"
DANAS = date.today()
SUTRA = (DANAS + timedelta(days=1)).isoformat()

# Stvarne kolone `predmet_hronologija` (PostgREST OpenAPI koren, 2026-08-18).
# `naziv` NAMERNO nije u skupu — to je cela poenta.
SEMA_HRONOLOGIJA = {
    "id", "predmet_id", "user_id", "dokument_naziv", "datum", "datum_iso",
    "dogadjaj", "akter", "vaznost", "created_at",
}

RED_ROKA = {
    "id": "h1", "predmet_id": "p1", "dogadjaj": "Žalba na presudu",
    "datum_iso": SUTRA, "vaznost": "kritičan", "akter": "Advokat",
}


class SemaGreska(RuntimeError):
    """42703 — isto što PostgREST vrati za nepostojeću kolonu."""


class _SemaSupa:
    """Lažni Supabase koji STVARNO primenjuje skup kolona."""

    def __init__(self, redovi=None, puca=False):
        self.redovi = redovi if redovi is not None else [RED_ROKA]
        self.puca = puca
        self.trazeno: list[tuple] = []   # (tabela, kolone)

    def table(self, ime):
        spolja = self

        class _Q:
            def select(self, kolone="*", *a, **k):
                spolja.trazeno.append((ime, kolone))
                if spolja.puca:
                    raise RuntimeError("simuliran ispad baze")
                if ime == "predmet_hronologija" and kolone != "*":
                    for c in [x.strip() for x in kolone.split(",")]:
                        if c and c not in SEMA_HRONOLOGIJA:
                            raise SemaGreska(
                                f"42703: column {ime}.{c} does not exist")
                return self

            def eq(self, *a, **k):    return self
            def gte(self, *a, **k):   return self
            def lte(self, *a, **k):   return self
            def order(self, *a, **k): return self
            def limit(self, *a, **k): return self

            def execute(self):
                return MagicMock(data=list(spolja.redovi))

        return _Q()


def _pozovi(supa, pitanje="Koji su mi rokovi ove nedelje?", odgovor_modela="OK."):
    """Vozi PRAVI `_handle_query`. Model je zamenjen, ali se broji da li je zvan."""
    poziva = {"n": 0}

    def _lazni_model(client, **kw):
        poziva["n"] += 1
        return MagicMock(choices=[MagicMock(message=MagicMock(content=odgovor_modela))])

    with patch.object(voice, "_pozovi_voice_chat_api", side_effect=_lazni_model), \
         patch("openai.OpenAI", return_value=MagicMock()):
        rez = asyncio.run(voice._handle_query(pitanje, UID, supa))
    return rez, poziva["n"]


# ═══════════════════════════════════════════════════════════════════════════════
# A. PRE-BUG REPRODUCTION — tačan kvar iz mandata
# ═══════════════════════════════════════════════════════════════════════════════

def test_A_stari_select_bi_pao_na_42703():
    """Dokaz da je kvar bio ACTIVE, ne teorijski: stari `select` obara upit."""
    supa = _SemaSupa()
    with pytest.raises(SemaGreska) as e:
        supa.table("predmet_hronologija").select("datum,naziv,vaznost,predmet_id")
    assert "naziv" in str(e.value)


def test_A2_kanonski_select_prolazi_kroz_semu():
    supa = _SemaSupa()
    supa.table("predmet_hronologija").select(rokovi_domen._KOLONE)  # ne diže


def test_A3_pao_upit_vise_ne_daje_tvrdnju_da_rokova_nema():
    """PRE: `[]` -> „Nema kritičnih rokova". POSLE: eksplicitan neuspeh."""
    supa = _SemaSupa(puca=True)
    rez, pozvan_model = _pozovi(supa)

    assert rez["rokovi_provereni"] is False
    assert "nije uspela" in rez["odgovor"]
    assert "nema" not in rez["odgovor"].lower().replace("rokova nema.", "")


# ═══════════════════════════════════════════════════════════════════════════════
# B. HAPPY PATH
# ═══════════════════════════════════════════════════════════════════════════════

def test_B_rokovi_postoje_i_stizu_do_modela():
    supa = _SemaSupa(redovi=[RED_ROKA])
    zabelezen = {}

    def _lazni_model(client, **kw):
        zabelezen["messages"] = kw.get("messages")
        return MagicMock(choices=[MagicMock(message=MagicMock(content="Imate jedan rok."))])

    with patch.object(voice, "_pozovi_voice_chat_api", side_effect=_lazni_model), \
         patch("openai.OpenAI", return_value=MagicMock()):
        rez = asyncio.run(voice._handle_query("Koji su mi rokovi?", UID, supa))

    kontekst = zabelezen["messages"][1]["content"]
    assert "Rokovi koji ističu" in kontekst
    assert "Žalba na presudu" in kontekst, "naslov roka nije stigao modelu"
    assert rez["odgovor"] == "Imate jedan rok."
    assert "rokovi_provereni" not in rez, "uspešan tok ne menja postojeći oblik odgovora"


# ═══════════════════════════════════════════════════════════════════════════════
# C+E. FAILURE / EXCEPTION PATH — neuspeh ostaje vidljiv, model se NE zove
# ═══════════════════════════════════════════════════════════════════════════════

def test_C_ispad_baze_daje_eksplicitan_neuspeh():
    supa = _SemaSupa(puca=True)
    rez, pozvan_model = _pozovi(supa)

    assert rez["type"] == "query"
    assert rez["odgovor"] == voice._ROKOVI_NEUSPEH_ODGOVOR
    assert rez["rokovi_provereni"] is False


def test_E_na_neuspehu_se_model_NE_zove():
    """Bezbednosno svojstvo ne sme zavisiti od poslušnosti modela.

    Usput: nema naplativog poziva na putanji greške.
    """
    supa = _SemaSupa(puca=True)
    _rez, pozvan_model = _pozovi(supa)
    assert pozvan_model == 0, "model je pozvan uprkos palom upitu o rokovima"


def test_E2_uspeh_i_dalje_zove_model():
    """Kontrola: da `test_E` ne prolazi zato što model nikad nije zvan."""
    supa = _SemaSupa(redovi=[RED_ROKA])
    _rez, pozvan_model = _pozovi(supa)
    assert pozvan_model == 1


# ═══════════════════════════════════════════════════════════════════════════════
# D. PRAZNO ≠ NEUSPEH
# ═══════════════════════════════════════════════════════════════════════════════

def test_D_legitimno_prazno_sme_reci_da_rokova_nema():
    supa = _SemaSupa(redovi=[])
    zabelezen = {}

    def _lazni_model(client, **kw):
        zabelezen["messages"] = kw.get("messages")
        return MagicMock(choices=[MagicMock(message=MagicMock(content="Nemate rokova."))])

    with patch.object(voice, "_pozovi_voice_chat_api", side_effect=_lazni_model), \
         patch("openai.OpenAI", return_value=MagicMock()):
        rez = asyncio.run(voice._handle_query("Koji su mi rokovi?", UID, supa))

    kontekst = zabelezen["messages"][1]["content"]
    assert "Nema kritičnih rokova u narednih 14 dana." in kontekst
    assert "rokovi_provereni" not in rez


def test_D2_prazno_i_neuspeh_daju_RAZLICIT_ishod():
    """Jezgro B3: dve situacije koje su ranije bile bit-identične."""
    prazno, _ = _pozovi(_SemaSupa(redovi=[]), odgovor_modela="Nemate rokova.")
    neuspeh, _ = _pozovi(_SemaSupa(puca=True))

    assert prazno["odgovor"] != neuspeh["odgovor"]
    assert "rokovi_provereni" not in prazno
    assert neuspeh["rokovi_provereni"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# F. CONTRACT TEST — DB ugovor
# ═══════════════════════════════════════════════════════════════════════════════

def test_F_voice_ne_gadja_nepostojecu_kolonu():
    supa = _SemaSupa(redovi=[RED_ROKA])
    _pozovi(supa)

    hron = [k for t, k in supa.trazeno if t == "predmet_hronologija"]
    assert hron, "domen rokova nije ni dodirnut — test ne bi merio ništa"
    for kolone in hron:
        for c in [x.strip() for x in kolone.split(",")]:
            assert c in SEMA_HRONOLOGIJA, f"select imenuje `{c}` koje u šemi ne postoji"


def test_F2_voice_koristi_kanonski_citac_a_ne_sopstveni_upit():
    """`shared/rokovi.py` je jedini vlasnik čitanja rokova — bez drugog parsera."""
    izvor = open(os.path.join(os.path.dirname(__file__), "..", "routers", "voice.py"),
                 encoding="utf-8").read()
    i = izvor.index("async def _fetch_rokovi")
    telo = izvor[i:i + 900]
    assert "rokovi_za_korisnika" in telo, "ne koristi se kanonski čitalac"
    assert "predmet_hronologija" not in telo, "voice ponovo sam gradi upit nad tabelom"


def test_F3_filtrira_se_po_datum_iso_a_ne_po_TEXT_datumu():
    """`datum` je TEXT slobodnog oblika; jedino je `datum_iso` uporediv."""
    assert "datum_iso" in rokovi_domen._KOLONE
    izvor = open(os.path.join(os.path.dirname(__file__), "..", "shared", "rokovi.py"),
                 encoding="utf-8").read()
    assert '.gte("datum_iso"' in izvor and '.lte("datum_iso"' in izvor


# ═══════════════════════════════════════════════════════════════════════════════
# H. NEGATIVNA INVARIJANTA
# ═══════════════════════════════════════════════════════════════════════════════

_ZABRANJENE_FRAZE = [
    "nema kritičnih rokova",
    "nemate rokova",
    "nema rokova",
]


@pytest.mark.parametrize("supa_kw", [
    {"puca": True},
])
@pytest.mark.parametrize("pitanje", [
    "Koji su mi rokovi?",
    "Da li mi ističe neki rok?",
    "Imam li rok ove nedelje?",
    "Koji su rokovi i ročišta danas?",
])
def test_H_query_failed_NIKAD_ne_tvrdi_odsustvo_rokova(supa_kw, pitanje):
    """QUERY_FAILED ⇒ NOT „NEMA ROKOVA" — na svakoj formulaciji pitanja."""
    supa = _SemaSupa(**supa_kw)
    rez, pozvan_model = _pozovi(supa, pitanje=pitanje,
                                odgovor_modela="Nemate rokova ove nedelje.")

    tekst = rez["odgovor"].lower()
    for fraza in _ZABRANJENE_FRAZE:
        assert fraza not in tekst, (
            f"ZABRANJENO STANJE: pao upit, a glas kaže `{fraza}` -> {rez['odgovor']!r}")
    assert pozvan_model == 0
    assert rez["rokovi_provereni"] is False


def test_H2_neuspeh_ne_moze_da_se_predstavi_kao_uspeh():
    """Ne sme postojati odgovor koji tvrdi proverenost a provera je pala."""
    rez, _ = _pozovi(_SemaSupa(puca=True))
    assert rez.get("rokovi_provereni") is not True
    assert "nije uspela" in rez["odgovor"]


# ═══════════════════════════════════════════════════════════════════════════════
# G. REGRESIJA — ostalo ponašanje `_handle_query` je nepromenjeno
# ═══════════════════════════════════════════════════════════════════════════════

def test_G_pitanje_bez_rokova_ne_dodiruje_domen_rokova():
    supa = _SemaSupa(puca=True)     # pao bi da se uopšte pozove
    rez, pozvan_model = _pozovi(supa, pitanje="Koliko imam predmeta?",
                                odgovor_modela="Imate dva predmeta.")

    assert rez["odgovor"] == "Imate dva predmeta."
    assert "rokovi_provereni" not in rez
    assert pozvan_model == 1


def test_G2_oblik_odgovora_je_nepromenjen():
    rez, _ = _pozovi(_SemaSupa(redovi=[RED_ROKA]))
    for k in ("type", "actions", "odgovor", "action", "params", "followup"):
        assert k in rez, f"nedostaje postojeće polje `{k}`"
    assert rez["type"] == "query"

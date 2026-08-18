# -*- coding: utf-8 -*-
"""
N1 (OOS-B3-1) — GLAS NE SME REĆI „0 PREDMETA" IZ UPITA KOJI JE PAO.

ŠTA JE BILO — mereno nad produkcionom šemom, ne pretpostavljeno

`routers/voice.py::_fetch_predmeti_summary` je slao:

    .select("id,naziv,tuzilac,tuzeni,oblast,status,created_at")

Sonda kolonu po kolonu (2026-08-18): **šest od sedam prolazi**, a `oblast`
vraća `42703: column predmeti.oblast does not exist`.

`oblast` NIJE preimenovana — ni `oblast_prava`, ni `kategorija`, ni
`pravna_oblast`, ni `oblast_spora`, ni `domen` ne postoje. U celom
repozitorijumu nema nijedne SQL naredbe koja je kreira; `CREATE TABLE predmeti`
(`supabase_setup.sql:300`) ima samo id/user_id/naziv/opis/tip/status/
created_at/updated_at. Kolona je uvedena u KODU (`d727fbd8`) protiv šeme koja
je nikad nije imala.

LANAC KVARA (reprodukovan determinističkim harnessom):

    select sa `oblast` -> PostgREST 42703 -> except -> {ukupno:0, aktivnih:0}
    -> kontekst „Predmeti: ukupno 0, aktivnih 0."
    -> `_QUERY_SYSTEM`: „Ako nema traženih podataka, reci to direktno."
    -> advokat sa 19 predmeta ČUJE da nema nijedan

Kontrola iz istog harnessa: sa identičnim kodom i identičnim redovima, ali bez
`oblast` u select-u, funkcija vraća `3 ukupno, 2 aktivna` — dakle kvar je
ISKLJUČIVO ta kolona.

ZAŠTO POSTOJEĆI TESTOVI NISU UHVATILI KVAR

  1. **Nijedan** test ne dodiruje `_fetch_predmeti_summary`.
  2. Jedini fajl koji vozi `_handle_query` je `test_b3_voice_rokovi.py`, a
     njegov `test_G` postavlja pitanje „Koliko imam predmeta?" — dakle VOZI
     ovu pokvarenu granu — ali tvrdi samo `rez["odgovor"] == "<mokovan tekst>"`
     i `pozvan_model == 1`. Nikad ne gleda KONTEKST koji je model dobio, pa je
     `ukupno: 0` bio nevidljiv.
  3. `_SemaSupa` u tom fajlu primenjuje šemu samo za `predmet_hronologija`
     (`if ime == "predmet_hronologija"`), pa `predmeti` select prolazi
     neproveren i 42703 se ne može reprodukovati.

UGOVOR KOJI OVI TESTOVI ZAKLJUČAVAJU

    upit OK + redovi   -> stvaran broj
    upit OK + 0 redova -> „0 predmeta" je DOZVOLJENO
    upit PAO           -> nikad „0 predmeta"; deterministički neuspeh, bez modela
"""
from __future__ import annotations

import asyncio
import os
import sys
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

UID = "uid-advokat"

# Stvarne kolone `predmeti` (PostgREST OpenAPI koren, 2026-08-18).
# `oblast` NAMERNO nije u skupu — to je cela poenta.
SEMA_PREDMETI = {
    "id", "user_id", "naziv", "opis", "tip", "status", "created_at",
    "updated_at", "tuzilac", "tuzeni", "rizik", "vrednost_spora",
    "kanban_faza", "case_dna", "broj_predmeta",
}

REDOVI = [
    {"id": "p1", "naziv": "Tužba Petrović", "status": "aktivan"},
    {"id": "p2", "naziv": "Spor Nikolić",   "status": "aktivan"},
    {"id": "p3", "naziv": "Stari predmet",  "status": "zatvoren"},
]


class SemaGreska(RuntimeError):
    """42703 — isto što PostgREST vrati za nepostojeću kolonu."""


class _SemaSupa:
    """Lažni Supabase koji STVARNO primenjuje skup kolona nad `predmeti`."""

    def __init__(self, redovi=None, puca=False, neispravan=False):
        self.redovi = REDOVI if redovi is None else redovi
        self.puca = puca
        self.neispravan = neispravan
        self.trazeno: list[tuple] = []

    def table(self, ime):
        spolja = self

        class _Q:
            def select(self, kolone="*", *a, **k):
                spolja.trazeno.append((ime, kolone))
                if spolja.puca:
                    raise RuntimeError("simuliran ispad baze")
                if ime == "predmeti" and kolone != "*":
                    for c in [x.strip() for x in kolone.split(",")]:
                        if c and c not in SEMA_PREDMETI:
                            raise SemaGreska(
                                f"42703: column {ime}.{c} does not exist")
                return self

            def eq(self, *a, **k):    return self
            def gte(self, *a, **k):   return self
            def lte(self, *a, **k):   return self
            def order(self, *a, **k): return self
            def limit(self, *a, **k): return self

            def execute(self):
                if spolja.neispravan:
                    return MagicMock(data=None)     # malformed / bez `data`
                return MagicMock(data=list(spolja.redovi))

        return _Q()


def _summary(**kw):
    return asyncio.run(voice._fetch_predmeti_summary(UID, _SemaSupa(**kw)))


def _pitaj(supa, pitanje="Koliko imam predmeta?", odgovor="Imate dva predmeta."):
    """Vozi PRAVI `_handle_query`; broji pozive modela i hvata kontekst."""
    stanje = {"n": 0, "kontekst": ""}

    def _model(client, **kw):
        stanje["n"] += 1
        stanje["kontekst"] = (kw.get("messages") or [{}, {}])[1].get("content", "")
        return MagicMock(choices=[MagicMock(message=MagicMock(content=odgovor))])

    with patch.object(voice, "_pozovi_voice_chat_api", side_effect=_model), \
         patch("openai.OpenAI", return_value=MagicMock()):
        rez = asyncio.run(voice._handle_query(pitanje, UID, supa))
    return rez, stanje


# ═══════════════════════════════════════════════════════════════════════════
# PRE-STATE REPRODUKCIJA
# ═══════════════════════════════════════════════════════════════════════════

def test_pre_stara_kolona_obara_upit():
    """Dokaz da je kvar bio ACTIVE: `oblast` obara ceo select."""
    supa = _SemaSupa()
    with pytest.raises(SemaGreska) as e:
        supa.table("predmeti").select("id,naziv,tuzilac,tuzeni,oblast,status,created_at")
    assert "oblast" in str(e.value)


def test_pre_kod_vise_ne_trazi_nepostojecu_kolonu():
    """Regresiona brava nad izvorom: `oblast` se ne sme vratiti u select."""
    import re
    src = open(os.path.join(os.path.dirname(__file__), "..", "routers", "voice.py"),
               encoding="utf-8").read()
    for m in re.finditer(r'\.table\("predmeti"\)\s*\n?\s*\.select\("([^"]+)"', src):
        for c in [x.strip() for x in m.group(1).split(",")]:
            assert c in SEMA_PREDMETI, f"voice.py traži `predmeti.{c}` koje ne postoji"


# ═══════════════════════════════════════════════════════════════════════════
# N1.4 TEST MATRIX — A/B/C/D/E
# ═══════════════════════════════════════════════════════════════════════════

def test_A_upit_OK_sa_redovima_daje_stvaran_broj():
    s = _summary()
    assert s["uspeh"] is True
    assert s["ukupno"] == 3
    assert s["aktivnih"] == 2
    assert len(s["predmeti"]) == 3


def test_B_upit_OK_bez_redova_sme_biti_nula():
    s = _summary(redovi=[])
    assert s["uspeh"] is True
    assert s["ukupno"] == 0 and s["aktivnih"] == 0


def test_C_upit_PAO_nije_nula():
    s = _summary(puca=True)
    assert s["uspeh"] is False, "pad upita je predstavljen kao uspeh"


def test_D_izuzetak_nije_nula():
    """Isti ugovor, drugi okidač: bilo koji izuzetak."""
    s = _summary(puca=True)
    assert s["uspeh"] is False
    assert s["predmeti"] == []


def test_E_malformed_odgovor_je_fail_safe():
    """`data=None` ne sme srušiti rutu niti postati lažna nula."""
    s = _summary(neispravan=True)
    assert s["uspeh"] is True          # upit JESTE izvršen
    assert s["ukupno"] == 0            # `data or []` — legitimno prazno


def test_B_i_C_daju_RAZLICIT_ishod():
    """Jezgro N1: dva stanja koja su ranije bila bajt-identična."""
    prazno = _summary(redovi=[])
    palo = _summary(puca=True)
    assert prazno["ukupno"] == palo["ukupno"] == 0
    assert prazno["uspeh"] != palo["uspeh"]


# ═══════════════════════════════════════════════════════════════════════════
# GLAS — ono što advokat ČUJE
# ═══════════════════════════════════════════════════════════════════════════

def test_glas_upit_OK_model_dobija_TACAN_broj():
    """Ovo je asercija koja je nedostajala postojećem `test_G`."""
    rez, st = _pitaj(_SemaSupa())
    assert st["n"] == 1
    assert "Predmeti: ukupno 3, aktivnih 2." in st["kontekst"], st["kontekst"]
    assert "Tužba Petrović" in st["kontekst"]
    assert "predmeti_provereni" not in rez


def test_glas_upit_PAO_ne_kaze_nula_i_ne_zove_model():
    rez, st = _pitaj(_SemaSupa(puca=True))
    assert st["n"] == 0, "model je pozvan iako provera predmeta nije izvršena"
    assert rez["predmeti_provereni"] is False
    assert rez["odgovor"] == voice._PREDMETI_NEUSPEH_ODGOVOR
    assert "nije uspela" in rez["odgovor"]


_ZABRANJENO = ["ukupno 0", "aktivnih 0", "nemate predmeta", "0 predmeta"]


@pytest.mark.parametrize("pitanje", [
    "Koliko imam predmeta?",
    "Koliko aktivnih predmeta imam?",
    "Da li imam neki slučaj u toku?",
    "Koliko predmeta i rokova imam danas?",
])
def test_glas_pao_upit_NIKAD_ne_tvrdi_odsustvo_predmeta(pitanje):
    """QUERY_FAILED ⇒ NOT „0 predmeta" — na svakoj formulaciji."""
    rez, st = _pitaj(_SemaSupa(puca=True), pitanje=pitanje,
                     odgovor="Nemate nijedan predmet.")
    tekst = rez["odgovor"].lower()
    for fraza in _ZABRANJENO:
        assert fraza not in tekst, f"pao upit, a glas kaže `{fraza}`: {rez['odgovor']!r}"
    assert st["n"] == 0


def test_glas_prazna_baza_SME_da_kaze_da_nema_predmeta():
    """Legitimno prazno mora ostati dozvoljeno — inače je popravka pregruba."""
    rez, st = _pitaj(_SemaSupa(redovi=[]), odgovor="Nemate nijedan predmet.")
    assert st["n"] == 1
    assert "Predmeti: ukupno 0, aktivnih 0." in st["kontekst"]
    assert rez["odgovor"] == "Nemate nijedan predmet."
    assert "predmeti_provereni" not in rez


# ═══════════════════════════════════════════════════════════════════════════
# REGRESIJA — B3 i ostalo ponašanje `_handle_query`
# ═══════════════════════════════════════════════════════════════════════════

def test_regresija_pitanje_bez_predmeta_ne_dodiruje_domen_predmeta():
    """Namera testa je nepromenjena: pitanje koje ne pominje predmete NE SME
    dodirnuti domen predmeta.

    Očekivani odgovor je izmenjen jer je N5-A-003 zatvorio susedni kvar u
    istoj funkciji: `_SemaSupa(puca=True)` obara i upit nad `rocista`, a
    pitanje „Kada je ročište?" tu granu aktivira. Ranije je taj pad bio
    progutan u `[]` i model je svejedno odgovarao — upravo lažni uspeh koji
    je M3 uklonio. Domen predmeta se i dalje ne dodiruje, što je ono što
    ovaj test meri.
    """
    supa = _SemaSupa(puca=True)   # pao bi da se pozove
    rez, st = _pitaj(supa, pitanje="Kada je ročište?", odgovor="Sutra u 10h.")
    assert rez["odgovor"] != "Sutra u 10h.", "model je odgovorio iz palog upita"
    assert "ročišta nije uspela" in rez["odgovor"]
    assert rez["rocista_provereni"] is False
    assert "predmeti_provereni" not in rez
    assert not any(t == "predmeti" for t, _ in supa.trazeno)


def test_regresija_oblik_odgovora_nepromenjen():
    rez, _ = _pitaj(_SemaSupa())
    for k in ("type", "actions", "odgovor", "action", "params", "followup"):
        assert k in rez, f"nedostaje postojeće polje `{k}`"
    assert rez["type"] == "query"


def test_regresija_B3_rokovi_ugovor_netaknut():
    """N1 ne sme oslabiti B3: rokovi i dalje imaju sopstvenu failure semantiku."""
    assert hasattr(voice, "_ROKOVI_NEUSPEH_ODGOVOR")
    assert "rokova" in voice._ROKOVI_NEUSPEH_ODGOVOR.lower()

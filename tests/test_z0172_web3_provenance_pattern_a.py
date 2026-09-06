# -*- coding: utf-8 -*-
"""Z017.2 §5/§6/§7/§8 -- PATTERN A provenance contract, web3_pretraga_sync.

STA OVAJ TEST CUVA, A STO SE IZ KODA NE VIDI:

  Pre ove izmene `web3_pretraga_sync` je vracala `str`. Preuzeti odlomci
  (koji propis, ocena relevantnosti, da li je Pinecone uopste odgovorio)
  postojali su LOKALNO u funkciji (`svi_matches`) i bili su BACENI cim su
  ušli u GPT prompt kao tekst -- isti "polje se gubi na granici" defekt koji
  je B4-M1 zatvorio za /api/pitanje (`izvori_neuspeh`), ovde nikad nije bio
  ni otvoren kao pitanje jer G1--G5 nikad nisu koristili
  `api.py::normalizuj_rezultat()`.

  CENTRALNI INVARIJANT (isti kao B-U-003): FAILURE != EMPTY RESULT.
    - Pinecone/embedding IZUZETAK -> retrieval_unavailable=True, izvori=[]
    - Pinecone ODGOVORIO, 0 pogodaka iznad praga -> retrieval_unavailable=False, izvori=[]
  Ova dva stanja NIKAD ne smeju izgledati isto -- jedno je "nismo proverili",
  drugo je "proverili smo, nema odgovarajuce odredbe".

  `_build_izvori_web3` koristi SAMO polja koja retrieval stvarno vraca za
  ovaj namespace (`izvor`, `tekst`, `score`) -- NE `_build_izvori` iz
  `app.services.retrieve` (ta funkcija ocekuje `law`/`article` metadata koja
  web3_zdi_mca namespace nema; slepo reuse bi tiho vratio [] za SVAKI
  pogodak zato sto kljucevi ne postoje -- lazna "nema izvora").
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import web3_compliance as W


def _match(i, score, izvor, tekst):
    return SimpleNamespace(id=i, score=score, metadata={"izvor": izvor, "tekst": tekst})


class _IndexSaRezultatima:
    def query(self, *a, **k):
        return SimpleNamespace(matches=[
            _match("w1", 0.81, "ZDI", "Član 5\nDigitalna imovina se izdaje uz belu knjigu (whitepaper)."),
            _match("w2", 0.62, "MiCA", "Article 4\nCASP authorisation is required prior to offering services."),
        ])


class _IndexPrazan:
    """Pinecone RADI, ali nema nijedan pogodak iznad praga relevantnosti."""
    def query(self, *a, **k):
        return SimpleNamespace(matches=[
            _match("w3", 0.12, "ZDI", "nepovezan odlomak ispod praga 0.50"),
        ])


class _IndexPada:
    def query(self, *a, **k):
        raise RuntimeError("pinecone: connection reset")


def _lazni_gpt_odgovor(text="Analiza na osnovu dostupnih odredbi."):
    class _Msg:
        content = text
    class _Choice:
        message = _Msg()
    class _Resp:
        choices = [_Choice()]
    return _Resp()


def _pozovi(index):
    with patch("app.services.retrieve._get_index", return_value=index), \
         patch("app.services.retrieve._ugradi_query", return_value=[0.0] * 8), \
         patch.object(W, "_pozovi_web3_api", return_value=_lazni_gpt_odgovor()), \
         patch.object(W, "_verifikuj_citat_clanova", side_effect=lambda odgovor, chunks: odgovor):
        return W.web3_pretraga_sync("Da li je potrebna dozvola za izdavanje tokena?", "fake-key")


def test_pretraga_uspesna_vraca_strukturirane_izvore():
    r = _pozovi(_IndexSaRezultatima())
    assert isinstance(r, dict)
    assert r["retrieval_unavailable"] is False
    assert len(r["izvori"]) == 2
    assert {x["izvor"] for x in r["izvori"]} == {"ZDI", "MiCA"}
    for x in r["izvori"]:
        assert 0.0 <= x["score"] <= 1.0
        assert x["odlomak"]  # stvaran preuzet tekst, ne izmisljen


def test_prazan_pogodak_ispod_praga_nije_isto_sto_i_pad_pretrage():
    r = _pozovi(_IndexPrazan())
    assert r["izvori"] == []
    assert r["retrieval_unavailable"] is False  # PROVERENO, nema odgovarajuce odredbe


def test_pad_pretrage_je_retrieval_unavailable_ne_prazan_rezultat():
    r = _pozovi(_IndexPada())
    assert r["izvori"] == []
    assert r["retrieval_unavailable"] is True  # NIJE PROVERENO -- razlicito od gornjeg testa
    assert r["odgovor"]  # GPT i dalje odgovara (na kanonskom pregledu), ali bez tvrdnje o izvoru


def test_odgovor_ostaje_string_bez_obzira_na_novu_dict_omotnicu():
    r = _pozovi(_IndexSaRezultatima())
    assert isinstance(r["odgovor"], str) and r["odgovor"]


# ═══════════════════════════════════════════════════════════════════════════
# G2 -- compliance_check_sync (isti obrazac, drugi endpoint, ista provera)
# ═══════════════════════════════════════════════════════════════════════════

def _pozovi_compliance(index):
    with patch("app.services.retrieve._get_index", return_value=index), \
         patch("app.services.retrieve._ugradi_query", return_value=[0.0] * 8), \
         patch.object(W, "_pozovi_web3_api", return_value=_lazni_gpt_odgovor()), \
         patch.object(W, "_verifikuj_citat_clanova", side_effect=lambda odgovor, chunks: odgovor):
        return W.compliance_check_sync("Poslovni model: platforma za razmenu tokena.", "fake-key")


def test_compliance_check_vraca_strukturirane_izvore():
    r = _pozovi_compliance(_IndexSaRezultatima())
    assert isinstance(r, dict)
    assert r["retrieval_unavailable"] is False
    assert len(r["izvori"]) == 2


def test_compliance_check_pad_pretrage_je_retrieval_unavailable():
    r = _pozovi_compliance(_IndexPada())
    assert r["izvori"] == [] and r["retrieval_unavailable"] is True


# ═══════════════════════════════════════════════════════════════════════════
# CARF/DAC8 -- carf_dac8_readiness_sync (drugi namespace, drugo metadata polje)
# ═══════════════════════════════════════════════════════════════════════════

def _match_carf(i, score, propis, naslov, tekst):
    return SimpleNamespace(id=i, score=score, metadata={"propis": propis, "naslov": naslov, "tekst": tekst})


class _IndexCarfSaRezultatima:
    def query(self, *a, **k):
        return SimpleNamespace(matches=[
            _match_carf("c1", 0.81, "CARF", "Section 3", "Reporting Crypto-Asset Service Providers must..."),
        ])


def _pozovi_carf(index):
    with patch("app.services.retrieve._get_index", return_value=index), \
         patch("app.services.retrieve._ugradi_query", return_value=[0.0] * 8), \
         patch.object(W, "_pozovi_web3_api", return_value=_lazni_gpt_odgovor()), \
         patch.object(W, "_verifikuj_citat_carf_dac8", side_effect=lambda odgovor, chunks: odgovor):
        return W.carf_dac8_readiness_sync("Da li smo RCASP po CARF-u?", "fake-key")


def test_carf_dac8_koristi_propis_polje_ne_izvor():
    """Slepo citanje `izvor` (web3_zdi_mca polje) na carf_dac8 matches-ima bi
    vratilo default "ZDI/MiCA" -- pogresan izvor za CARF/DAC8 nalaz. Ovaj test
    cuva da _build_izvori_web3 poziv u carf_dac8_readiness_sync koristi
    izvor_polje="propis", ne podrazumevano "izvor"."""
    r = _pozovi_carf(_IndexCarfSaRezultatima())
    assert len(r["izvori"]) == 1
    assert r["izvori"][0]["izvor"] == "CARF — Section 3"
    assert "ZDI" not in r["izvori"][0]["izvor"]


def test_carf_dac8_pad_pretrage_je_retrieval_unavailable():
    r = _pozovi_carf(_IndexPada())
    assert r["izvori"] == [] and r["retrieval_unavailable"] is True

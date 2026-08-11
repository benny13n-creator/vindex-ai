# -*- coding: utf-8 -*-
"""
Governance Wave 2 — Cohere: latentan put, ne živ provajder.

ISPRAVKA RANIJEG NALAZA

Prethodni sprint je prijavio: „`cohere` je živ produkcijski provajder sa 4
pozivaoca, potpuno van OpenAI patch-a" — i na osnovu toga oborio tvrdnju da
monkey-patch daje strukturnu pokrivenost.

Merenje pokazuje da je taj nalaz TAČAN o postojanju koda, a NETAČAN o
produkciji. Put je dvostruko zatvoren:

  1. `cohere` paket NIJE u `requirements.txt` (deklarisani su samo
     `openai==2.29.0`, `langchain-openai`, `langchain`, `httpx`, `websockets`).
     Produkcioni image se gradi iz tog fajla (`Dockerfile:14`), pa
     `import cohere` pada i `_COHERE_AVAILABLE` je False
     (`app/services/retrieve.py:33-37`).

  2. `COHERE_API_KEY` nije postavljen; `.env.example:18` ga izričito označava
     kao „opciono — za Re-Ranking, Sprint 3".

Bilo koji uslov sam po sebi vraća `None` iz `_get_cohere()`
(`app/services/retrieve.py:511-516`), pa `_cohere_rerank` na `:1254-1256` pada
na `_gpt_rerank` — OpenAI poziv kroz patch-ovan SDK, dakle POKRIVEN.

Na ovoj razvojnoj mašini `cohere` JESTE instaliran (6.1.0), što objašnjava
zašto je raniji pregled zaključio da je živ. Instaliran paket na razvojnoj
mašini nije produkcijska zavisnost.

ZAŠTO OVAJ TEST POSTOJI

Ne da bi proglasio problem rešenim — nego zato što je put LATENTAN. Dovoljno je
da neko doda `cohere` u `requirements.txt` i postavi ključ, i putanja tiho
postaje živa, van svakog guard-a, sa pasusima iz korisnikovih dokumenata koji
odlaze trećem provajderu. Ovaj test tu tišinu uklanja: ili provajder nije
dostupan, ili mora biti upravljan.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REQ = os.path.join(_KOREN, "requirements.txt")


def _requirements() -> str:
    return open(_REQ, encoding="utf-8").read().lower()


# ─── 1. PRODUKCIJSKA ZAVISNOST ──────────────────────────────────────────────

def test_a_cohere_nije_produkcijska_zavisnost():
    """Ako `cohere` ikad uđe u `requirements.txt`, ovaj test pada NAMERNO.

    To nije zabrana upotrebe Cohere-a. To je zahtev da se, pre nego što postane
    produkcijska zavisnost, njegova governance putanja reši — jer ga OpenAI
    monkey-patch (`shared/ai_client.py`) fizički ne vidi.

    Šta uraditi kad padne: ili ukloni zavisnost, ili provuci `_cohere_rerank`
    kroz forensics/guard i tek onda prepiši ovaj test uz obrazloženje.
    """
    req = _requirements()
    assert "cohere" not in req, (
        "`cohere` je dodat u requirements.txt — putanja `app/services/retrieve.py:1249` "
        "(_cohere_rerank) time postaje ŽIVA u produkciji, a OpenAI SDK patch je "
        "ne pokriva: ni prompt guard, ni ai_forensics, ni provenance. Kroz nju "
        "prolaze pasusi iz korisnikovih dokumenata i sudske prakse. Reši "
        "governance pre nego što uključiš zavisnost."
    )


def test_b_kljuc_je_opcion_i_put_je_dvostruko_zatvoren():
    """Dva nezavisna uslova, svaki dovoljan da zatvori put.

    Dokumentuje se DA su oba prisutna — jedan bi bio dovoljan, ali dva znače da
    slučajno vraćanje jednog ne otvara putanju.
    """
    import app.services.retrieve as r

    izvor = open(r.__file__, encoding="utf-8").read()
    assert "_COHERE_AVAILABLE" in izvor, "uslov dostupnosti paketa je uklonjen"
    assert 'os.getenv("COHERE_API_KEY")' in izvor, "uslov postojanja ključa je uklonjen"

    # Fallback mora ostati — bez njega bi zatvoren put značio pad, ne degradaciju.
    assert "_gpt_rerank" in izvor, (
        "fallback na _gpt_rerank je uklonjen — bez njega zatvoren Cohere put "
        "obara reranking umesto da ga degradira na patch-ovan OpenAI poziv"
    )


# ─── 2. PONAŠANJE, NE SAMO IZVOR ────────────────────────────────────────────

def test_c_bez_kljuca_klijent_je_None(monkeypatch):
    """Merenje, ne čitanje: `_get_cohere()` mora vratiti None bez ključa."""
    import app.services.retrieve as r

    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    monkeypatch.setattr(r, "_COHERE_CLIENT", None, raising=False)
    assert r._get_cohere() is None


def test_d_rerank_pada_na_gpt_kad_cohere_nije_dostupan(monkeypatch):
    """Ključni dokaz: bez Cohere-a poziv ODLAZI na patch-ovan OpenAI put.

    Ovo je razlika između „Cohere nije pozvan" i „umesto njega je pozvan
    upravljan provajder". Prva tvrdnja ne kaže ništa o pokrivenosti; druga kaže.
    """
    import app.services.retrieve as r

    pozvano = {}

    def _lazni_gpt_rerank(query, matches, k=3):
        pozvano["gpt"] = True
        return matches[:k]

    monkeypatch.setattr(r, "_get_cohere", lambda: None)
    monkeypatch.setattr(r, "_gpt_rerank", _lazni_gpt_rerank)

    class _M:
        metadata = {"text": "pasus iz dokumenta"}
        score = 0.9

    rez = r._cohere_rerank("upit", [_M(), _M()], k=1)
    assert pozvano.get("gpt") is True, (
        "bez Cohere-a se NE poziva _gpt_rerank — put ne degradira na upravljan "
        "provajder nego tiho vraća nešto drugo"
    )
    assert len(rez) == 1


# ─── 3. NEGATIVNA KONTROLA ──────────────────────────────────────────────────

def test_ng_test_bi_uhvatio_ziv_cohere(monkeypatch):
    """Dokaz da `test_a` meri nešto.

    Simulira se `requirements.txt` sa Cohere-om i proverava da bi tvrdnja pala.
    Bez ovoga bi `test_a` prolazio i da uvek gleda prazan string.
    """
    lazni = "openai==2.29.0\ncohere==5.11.0\nhttpx>=0.27.0\n"
    assert "cohere" in lazni.lower(), "kontrola je besmislena ako uzorak nema cohere"

    stvarni = _requirements()
    assert stvarni.strip(), "requirements.txt je prazan — test bi prolazio vakuumski"
    assert "openai" in stvarni, "requirements.txt se ne čita ispravno"


def test_ng_cohere_poziv_stvarno_postoji_u_kodu():
    """Put je latentan, ne nepostojeći.

    Ako neko obriše `_cohere_rerank`, gornji testovi postaju besmisleni a i
    dalje bi prolazili. Ovo drži tvrdnju vezanu za stvarni kod.
    """
    import app.services.retrieve as r
    izvor = open(r.__file__, encoding="utf-8").read()
    assert "def _cohere_rerank" in izvor
    assert "co.rerank(" in izvor, (
        "Cohere poziv više ne postoji — ako je put uklonjen namerno, obriši i "
        "ovaj fajl umesto da testovi štite nepostojeći rizik"
    )

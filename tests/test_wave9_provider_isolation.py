# -*- coding: utf-8 -*-
"""
Wave 9 / D1 — Cohere: latentan put je sada EKSPLICITNO izolovan.

IZMERENO STANJE PRE IZMENE (potvrđeno, ne prepisano iz ranijeg izveštaja)

  * `cohere` NIJE u `requirements.txt` — produkcioni image se gradi iz njega,
    pa `import cohere` tamo pada i `_COHERE_AVAILABLE` je False.
  * `COHERE_API_KEY` nije postavljen ni lokalno ni na produkciji.
  * Na ovoj razvojnoj mašini `cohere` JESTE instaliran (6.1.0) — zato je raniji
    pregled zaključio da je Cohere „živ provajder".

Oba uslova su bila DOVOLJNA da zatvore put, ali nijedan nije bio NAMERAN. Bilo
je dovoljno da neko doda paket u lanac zavisnosti ili ostavi ključ u `.env`-u
i putanja bi tiho oživela — sa korisnikovim upitom i isečcima dokumenata koji
odlaze provajderu koji kanonski chokepoint (`shared/ai_client.py::
_patch_prompt_guard`, monkey-patch na KLASAMA OpenAI SDK-a) fizički ne vidi.

ŠTA JE PROMENJENO

Grana NIJE obrisana — `_gpt_rerank` fallback zavisi od iste strukture, a četiri
pozivna mesta zovu `_cohere_rerank` po imenu; brisanje bi bio veći refaktor od
koristi i uklonilo bi reranking, ne rizik. Umesto toga uveden je jedan imenovan
uslov aktivacije `_cohere_dozvoljen()` koji traži SVA TRI uslova istovremeno:
paket + ključ + eksplicitan `VINDEX_COHERE_RERANK` opt-in.

ŠTA OVI TESTOVI MERE

Ponašanje u runtime-u, ne prisustvo stringova u izvoru. Svaki test koji tvrdi
„Cohere se ne zove" to dokazuje kroz `assert_not_called` na `_get_cohere`, uz
`_COHERE_AVAILABLE=True` — dakle paket se NAMERNO pravi dostupnim, da bi bilo
jasno da blokira opt-in, a ne slučajna odsutnost paketa na ovoj mašini.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.services.retrieve as r  # noqa: E402

_OPT_IN = "VINDEX_COHERE_RERANK"


class _Match:
    """Minimalni Pinecone match — samo ono što reranker stvarno čita."""

    def __init__(self, ident: str, tekst: str):
        self.id = ident
        self.metadata = {"text": tekst, "law": "ZOO", "article": ident}
        self.score = 0.5


def _matchevi() -> list:
    return [_Match("A", "prvi pasus"), _Match("B", "drugi pasus"), _Match("C", "treci pasus")]


class _GptOdgovor:
    """Odgovor gpt-4o-mini rerankera koji traži redosled 3,1,2."""

    class _Msg:
        content = "[3,1,2]"

    class _Choice:
        message = None

    def __init__(self):
        c = self._Choice()
        c.message = self._Msg()
        self.choices = [c]


@pytest.fixture(autouse=True)
def cisto_okruzenje(monkeypatch):
    """Svaki test kreće iz poznatog stanja.

    `_COHERE_CLIENT` je modul-globalni singleton — bez resetovanja bi klijent
    napravljen u pozitivnoj kontroli procurio u naredni test i lažno ga obojio.
    """
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    monkeypatch.delenv(_OPT_IN, raising=False)
    monkeypatch.setattr(r, "_COHERE_CLIENT", None, raising=False)
    yield
    r._COHERE_CLIENT = None


def _lazni_cohere_klijent(rezultat_indeksi=(2, 0)):
    klijent = MagicMock()
    rez = MagicMock()
    rez.results = [MagicMock(index=i) for i in rezultat_indeksi]
    klijent.rerank.return_value = rez
    return klijent


# ═══════════════════════════════════════════════════════════════════════════
# 1. IZMERENO STANJE — dokaz, ne tvrdnja
# ═══════════════════════════════════════════════════════════════════════════

def test_a_izmereno_paket_nije_produkcijska_zavisnost():
    """`cohere` nije u `requirements.txt` → na produkciji paket ne postoji.

    Ovo NIJE zabrana upotrebe. Ako neko sutra doda zavisnost, `_cohere_dozvoljen`
    i dalje traži opt-in, pa put ostaje zatvoren — ali ovaj test tada pada i
    prisiljava na svesnu odluku umesto tihe promene površine.
    """
    koren = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    req = open(os.path.join(koren, "requirements.txt"), encoding="utf-8").read().lower()
    assert "openai" in req, "requirements.txt se ne čita ispravno — test bi prolazio vakuumski"
    assert "cohere" not in req


def test_b_izmereno_podrazumevano_stanje_je_iskljuceno():
    """Runtime provera, ne čitanje izvora: bez env-a uslov je False.

    Namerno se NE dira `_COHERE_AVAILABLE` — meri se stvarno stanje ove mašine
    (gde je paket instaliran) i dokazuje da instalacija sama po sebi ne pali
    putanju.
    """
    assert r._cohere_dozvoljen() is False


# ═══════════════════════════════════════════════════════════════════════════
# 2. IZOLACIJA — Cohere se NE zove
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "env, opis",
    [
        ({}, "podrazumevano stanje, bez ijedne env promenljive"),
        ({"COHERE_API_KEY": "co-tajni-kljuc"}, "samo ključ, bez opt-in-a"),
        ({_OPT_IN: "1"}, "samo opt-in, bez ključa"),
        ({"COHERE_API_KEY": "co-tajni-kljuc", _OPT_IN: "0"}, "ključ + izričito ugašen opt-in"),
    ],
)
def test_c_bez_punog_opt_ina_cohere_se_ne_dodiruje(monkeypatch, env, opis):
    """Srž D1.

    `_COHERE_AVAILABLE` se postavlja na True da bi bilo isključeno objašnjenje
    „nije pozvan jer paket ne postoji". Ono što blokira je isključivo uslov
    aktivacije.

    Dodatno se tvrdi da GPT fallback nije samo pozvan nego i da je STVARNO
    rerangirao — `_gpt_rerank` se ne mock-uje, mock-uje se OpenAI poziv ispod
    njega, pa se meri izlazni redosled. Bez toga bi „fallback radi" značilo
    samo „nešto se vratilo".
    """
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(r, "_COHERE_AVAILABLE", True)

    get_cohere = MagicMock(name="_get_cohere")
    monkeypatch.setattr(r, "_get_cohere", get_cohere)
    monkeypatch.setattr(r, "_pozovi_chat_api", MagicMock(return_value=_GptOdgovor()))

    rez = r._cohere_rerank("koliko iznosi zatezna kamata", _matchevi(), k=3)

    get_cohere.assert_not_called()
    assert [m.id for m in rez] == ["C", "A", "B"], (
        f"GPT fallback nije rerangirao ({opis}) — izolacija je degradirala kvalitet "
        f"pretrage umesto da ga sačuva"
    )


def test_d_get_cohere_je_takodje_zatvoren(monkeypatch):
    """Odbrana u dubinu.

    `_cohere_rerank` proverava uslov pre `_get_cohere`, ali `_get_cohere` je
    javna funkcija modula koju sutra može pozvati neko drugi. I ona mora da
    vrati None dok opt-in nije uključen, inače bi izolacija važila za tačno
    jedno pozivno mesto.
    """
    monkeypatch.setattr(r, "_COHERE_AVAILABLE", True)
    monkeypatch.setenv("COHERE_API_KEY", "co-tajni-kljuc")
    assert r._get_cohere() is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. POZITIVNA KONTROLA — sa punim opt-in-om se Cohere ZOVE
# ═══════════════════════════════════════════════════════════════════════════

def test_e_pun_opt_in_aktivira_cohere(monkeypatch):
    """Bez ovoga bi svi testovi iznad prolazili i da je grana mrtav kod.

    Dokazuje da uslov razlikuje dva stanja, a ne da bezuslovno blokira.
    """
    monkeypatch.setattr(r, "_COHERE_AVAILABLE", True)
    monkeypatch.setenv("COHERE_API_KEY", "co-tajni-kljuc")
    monkeypatch.setenv(_OPT_IN, "1")

    klijent = _lazni_cohere_klijent(rezultat_indeksi=(2, 0))
    monkeypatch.setattr(r, "_get_cohere", MagicMock(return_value=klijent))
    gpt = MagicMock(side_effect=AssertionError("GPT fallback ne sme da se zove"))
    monkeypatch.setattr(r, "_gpt_rerank", gpt)
    monkeypatch.setattr(r, "_uknjizi_cohere_provenance", MagicMock())

    assert r._cohere_dozvoljen() is True
    rez = r._cohere_rerank("upit", _matchevi(), k=2)

    klijent.rerank.assert_called_once()
    assert [m.id for m in rez] == ["C", "A"]


def test_f_cohere_izuzetak_pada_na_gpt_i_korisnik_dobija_rezultat(monkeypatch):
    """Kad je Cohere UKLJUČEN pa pukne, pretraga ne sme da padne.

    Ovo je jedini scenario u kojem korisnik zavisi od fallback-a dok je Cohere
    aktiviran — i jedini u kojem su podaci već otišli napolje pre greške.
    """
    monkeypatch.setattr(r, "_COHERE_AVAILABLE", True)
    monkeypatch.setenv("COHERE_API_KEY", "co-tajni-kljuc")
    monkeypatch.setenv(_OPT_IN, "true")

    klijent = MagicMock()
    klijent.rerank.side_effect = RuntimeError("cohere 503")
    monkeypatch.setattr(r, "_get_cohere", MagicMock(return_value=klijent))
    monkeypatch.setattr(r, "_pozovi_chat_api", MagicMock(return_value=_GptOdgovor()))
    prov = MagicMock()
    monkeypatch.setattr(r, "_uknjizi_cohere_provenance", prov)

    rez = r._cohere_rerank("upit", _matchevi(), k=3)

    assert [m.id for m in rez] == ["C", "A", "B"], "fallback nije rerangirao posle Cohere greške"
    assert prov.call_args.kwargs.get("status") == "error", (
        "neuspeo Cohere poziv nije uknjižen — podaci su otišli napolje bez traga"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. PROVENANCE — trag da su podaci otišli, bez sadržaja
# ═══════════════════════════════════════════════════════════════════════════

def test_g_aktivan_cohere_pise_provenance_red_bez_sadrzaja(monkeypatch):
    """Kad je grana uključena, mora postojati trag — i ne sme sadržati sadržaj.

    Trag ide kroz POSTOJEĆU javnu funkciju `log_provenance_from_wrapper`, istu
    koju kanonski wrapper koristi za OpenAI pozive, pa Cohere red završava u
    istoj `ai_forensics` tabeli sa istim `correlation_id`-jem.
    """
    monkeypatch.setattr(r, "_COHERE_AVAILABLE", True)
    monkeypatch.setenv("COHERE_API_KEY", "co-tajni-kljuc")
    monkeypatch.setenv(_OPT_IN, "1")
    monkeypatch.setattr(r, "_get_cohere", MagicMock(return_value=_lazni_cohere_klijent((0,))))

    upit = "poverljiv upit o klijentu Petrovic"
    zabelezen = AsyncMock()
    with patch("security.ai_forensics.log_provenance_from_wrapper", new=zabelezen):
        r._cohere_rerank(upit, _matchevi(), k=1)

    zabelezen.assert_awaited_once()
    kw = zabelezen.await_args.kwargs
    assert kw["model_provider"] == "cohere"
    assert kw["model_name"] == r._COHERE_RERANK_MODEL
    assert kw["correlation_id"], "provenance red bez correlation_id-ja se ne može spojiti sa auditom"

    spojeno = " ".join(str(v) for v in kw.values())
    assert upit not in spojeno, "SADRŽAJ UPITA je procureo u provenance red"
    for m in _matchevi():
        assert m.metadata["text"] not in spojeno, "SADRŽAJ DOKUMENTA je procureo u provenance red"


def test_h_provenance_ne_obara_pretragu(monkeypatch):
    """Knjiženje je fail-soft. Pad audita ne sme da obori korisnikovu pretragu."""
    monkeypatch.setattr(r, "_COHERE_AVAILABLE", True)
    monkeypatch.setenv("COHERE_API_KEY", "co-tajni-kljuc")
    monkeypatch.setenv(_OPT_IN, "1")
    monkeypatch.setattr(r, "_get_cohere", MagicMock(return_value=_lazni_cohere_klijent((1,))))

    with patch("security.ai_forensics.log_provenance_from_wrapper",
               new=AsyncMock(side_effect=RuntimeError("supabase down"))):
        rez = r._cohere_rerank("upit", _matchevi(), k=1)

    assert [m.id for m in rez] == ["B"]

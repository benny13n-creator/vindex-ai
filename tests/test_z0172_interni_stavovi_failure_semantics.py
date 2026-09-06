# -*- coding: utf-8 -*-
"""Z017.2 -- D9 interni_stavovi -- FAILURE != EMPTY (isti invarijant kao B-U-003).

PRE-STATE (dokazano citanjem koda, ne pretpostavljeno): `search_stavovi`
je imalo `except Exception: return []` -- pretraga koja NIJE izvrsena
(Pinecone/embedding pad) je bila BAJT-IDENTICNA uspesnoj pretrazi sa nula
pogodaka. routers/interni.py je taj `[]` direktno prosledjivao kao
`{"rezultati": [], "ukupno": 0}` -- korisnik bi video "nema internih
stavova za ovaj upit" kad je STVARNO stanje bilo "pretraga nije ni
izvrsena". D9 nikad nije imalo V2 povrsinu, pa ovaj kvar nikad nije
stigao do frontenda -- zatvoreno OVDE, pre nego sto se doda.

CENTRALNI INVARIJANT (isti kao B-U-003): FAILURE != EMPTY RESULT.
"""
from unittest.mock import MagicMock, patch

import pytest

import interni_stavovi as IS
import routers.interni as R


class _IndexPrazan:
    """Pinecone RADI, ali nema pogodak iznad praga 0.5."""
    def query(self, *a, **k):
        m = MagicMock()
        m.matches = []
        return m


class _IndexPada:
    def query(self, *a, **k):
        raise RuntimeError("pinecone: connection reset")


def _lazan_embed_client():
    m = MagicMock()
    m.embed_query.return_value = [0.0] * 8
    return m


def test_prazan_pogodak_nije_isto_sto_i_pad_pretrage():
    with patch.object(IS, "_get_pinecone_index", return_value=_IndexPrazan()), \
         patch.object(IS, "_get_embeddings_client", return_value=_lazan_embed_client()):
        r = IS.search_stavovi("uid-1", "neko pitanje")
    assert r == []  # PROVERENO, nema pogotka -- ovo je ispravno


def test_pad_pretrage_baca_ne_vraca_tiho_prazno():
    with patch.object(IS, "_get_pinecone_index", return_value=_IndexPada()), \
         patch.object(IS, "_get_embeddings_client", return_value=_lazan_embed_client()):
        with pytest.raises(RuntimeError):
            IS.search_stavovi("uid-1", "neko pitanje")


@pytest.mark.anyio
async def test_router_razlikuje_prazno_od_pada():
    from fastapi import Request as StarletteRequestType

    async def _fake_consume(*a, **k):
        return 10

    req = MagicMock(spec=StarletteRequestType)
    user = {"user_id": "uid-1", "email": "a@b.rs"}
    body = R.InterniPretraga(upit="neko pitanje")

    # Prazan pogodak
    with patch.object(R, "_search_stavovi", return_value=[]), \
         patch.object(R.UsageService, "consume", new=_fake_consume):
        prazno = await R.post_pretraga_stavova(body, req, user)
    assert prazno["ukupno"] == 0 and prazno["pretraga_neuspesna"] is False

    # Pad pretrage
    def _pada(*a, **k):
        raise RuntimeError("down")
    with patch.object(R, "_search_stavovi", side_effect=_pada), \
         patch.object(R.UsageService, "consume", new=_fake_consume):
        palo = await R.post_pretraga_stavova(body, req, user)
    assert palo["ukupno"] == 0 and palo["pretraga_neuspesna"] is True
    # Dva razlicita stanja, ISTI "ukupno": 0 -- razlikuju se SAMO kroz
    # pretraga_neuspesna, sto je tacno polje koje mora postojati.


@pytest.fixture
def anyio_backend():
    return "asyncio"

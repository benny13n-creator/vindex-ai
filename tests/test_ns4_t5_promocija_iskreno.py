# -*- coding: utf-8 -*-
"""Night Sprint IV — Task 5: odobrenje nacrta ne sme da tvrdi ni pogrešan razlog ni uspeh koji se nije desio.

Zatečeno (`routers/drafting.py`):
  1. `staging_approve` za SVAKI neuspeh promocije (Pinecone pao, prazan nacrt) vraća „confidence_score je ispod
     praga“ — i kad je ocena 0.95. Advokat dobija pogrešan razlog i ne zna da je upis pao.
  2. `_promote_staged_draft_to_pinecone` vraća True i kad je `ingest_session` upisao MANJE delova od očekivanog
     (red u `predmet_dokumenti` dobija `sacuvano`, ali ruta kaže „dodat u bazu znanja“ i `pinecone_indexed=True`).

Bez mreže: Pinecone/ingest je zamenjen, baza je stateful lažni red iz `test_beta_gate_staging_approve_race`.
"""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from routers import drafting
from tests.test_beta_gate_staging_approve_race import _StagingMemoryTable, _req


def _red(conf=0.95, sid="st-n4"):
    return {"id": sid, "user_id": "u1", "predmet_id": "p1", "tip": "podnesak", "naziv": "Nacrt",
            "tekst": "Sadržaj odobrenog nacrta.", "confidence_score": conf, "status": "pending",
            "pinecone_indexed": False}


def _odobri(red, promocija):
    supa = MagicMock()
    supa.table.return_value = _StagingMemoryTable(red)
    pozivi = {"n": 0}

    async def _promo(_supa, _row):
        pozivi["n"] += 1
        return await promocija()
    with patch.object(drafting, "_get_supa", return_value=supa), \
         patch.object(drafting, "_promote_staged_draft_to_pinecone", new=_promo):
        rez = asyncio.run(drafting.staging_approve(red["id"], _req(), {"user_id": "u1"}))
    return rez, pozivi["n"]


async def _pada():
    raise RuntimeError("pinecone 503")


async def _vraca_false():
    return False


async def _uspeh():
    return True


@pytest.mark.parametrize("promocija", [_pada, _vraca_false], ids=["izuzetak", "false"])
def test_neuspeh_promocije_nije_prijavljen_kao_nizak_kvalitet(promocija):
    red = _red(conf=0.95)
    rez, n = _odobri(red, promocija)
    assert n == 1 and rez["indexed"] is False and red["pinecone_indexed"] is False
    assert rez.get("razlog") == "INDEKSIRANJE_NIJE_USPELO"
    assert "ispod praga" not in rez["poruka"] and "confidence" not in rez["poruka"], rez["poruka"]


def test_ispod_praga_navodi_prag_i_ne_promovise():
    red = _red(conf=0.40)
    rez, n = _odobri(red, _uspeh)
    assert n == 0 and rez["indexed"] is False and rez.get("razlog") == "ISPOD_PRAGA"
    assert "0.85" in rez["poruka"]


def test_uspeh_bez_razloga_neuspeha():
    red = _red()
    rez, n = _odobri(red, _uspeh)
    assert n == 1 and rez["indexed"] is True and red["pinecone_indexed"] is True
    assert rez.get("razlog") in (None, "INDEKSIRANO")


def test_ponovljeno_odobrenje_posle_neuspeha_ne_promovise_ponovo():
    """Nema tihog dupliranja vektora: drugi poziv ne promoviše. (Oporavak NIJE moguć kroz ovu rutu — blocker.)"""
    red = _red()
    _odobri(red, _pada)
    rez, n = _odobri(red, _uspeh)
    assert n == 0 and red["status"] == "approved" and red["pinecone_indexed"] is False
    assert rez["indexed"] is False


def _promovisi_sa_upisano(upisano):
    supa = MagicMock()
    dokumenti = []

    def _table(name):
        m = MagicMock()
        if name == "predmet_dokumenti":
            m.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = \
                MagicMock(data=[])

            def _insert(row):
                dokumenti.append(row)
                ex = MagicMock()
                ex.execute.return_value = MagicMock(data=[row])
                return ex
            m.insert.side_effect = _insert
        return m
    supa.table.side_effect = _table
    row = {"id": "stg-1", "user_id": "u1", "kancelarija_id": "kanc-1", "predmet_id": "pred-1",
           "tip": "tuzba", "naziv": "Tužba", "tekst": "Puni tekst odobrenog nacrta. " * 40, "confidence_score": 0.9}
    with patch("uploaded_doc.ingest.ingest_session", side_effect=lambda manifest, *a, **k: upisano(manifest)):
        rez = asyncio.run(drafting._promote_staged_draft_to_pinecone(supa, row))
    return rez, dokumenti


def test_nepotpun_upis_nije_uspeh_promocije():
    rez, dok = _promovisi_sa_upisano(lambda m: m.total_chunks - 1 if m.total_chunks > 1 else 0)
    assert rez is False, "nepotpun upis u indeks prijavljen kao uspešna promocija"
    assert dok and dok[0]["status"] == "sacuvano"


def test_potpun_upis_je_uspeh():
    rez, dok = _promovisi_sa_upisano(lambda m: m.total_chunks)
    assert rez is True and dok[0]["status"] == "indeksirano"

# -*- coding: utf-8 -*-
"""
Regression tests — Faza 1: Popravka Kritičnih Bugova i Async Blokada (2026-07-24).

1. routers/drafting.py + api.py admin dijagnostika: retrieve_documents() vraća
   tuple[list[str], dict], ne samu listu — nepravilno raspakivanje je pravilo da
   "kontekst" za /api/podnesak UVEK bude prazan string.
2. app/services/retrieve.py::_semanticka_pretraga — _ugradi_query (OpenAI
   embeddings poziv) je ranije stajao izvan try bloka; prolazna greška je bila
   neuhvaćen izuzetak umesto da vrati praznu listu kao ostatak funkcije.
"""
import sys
import os
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@contextmanager
def _stub_retrieve_llm():
    """Stub the OpenAI chat client used throughout retrieve.py.

    retrieve_documents() unconditionally fires several gpt-4o-mini calls that
    have nothing to do with Pinecone: _dekomponuj_query / decompose_query and
    _generiši_hyde (both in a ThreadPoolExecutor), _prosiri_query_gpt_wrapper,
    _gpt_rerank when Cohere is unavailable, and _oceni_relevantnost in the
    CRAG loop. All build their client through retrieve._get_client(), which
    the tuple-contract test below never patched -- so mocking
    _get_index/_get_embeddings/_get_cohere still left real, billed requests
    going out.

    The stub returns an empty completion, which drives each call site down
    its own documented empty/neutral branch. The test asserts the SHAPE of
    the return value, which is unaffected either way.
    """
    fake_message = MagicMock()
    fake_message.content = ""
    fake_choice = MagicMock()
    fake_choice.message = fake_message
    fake_resp = MagicMock()
    fake_resp.choices = [fake_choice]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_resp
    with patch("app.services.retrieve._get_client", return_value=fake_client):
        yield


# ─── Bug #1: RAG kontekst tuple-unpacking (routers/drafting.py) ───────────────

def test_retrieve_documents_vraca_tuple_docs_i_meta():
    """retrieve_documents() mora vratiti (list[str], dict), ne samo listu —
    dokumentuje ugovor koji /api/podnesak zavisi od."""
    from app.services.retrieve import retrieve_documents

    mock_index = MagicMock()
    mock_index.query.return_value = MagicMock(matches=[])
    mock_embeddings = MagicMock()
    mock_embeddings.embed_query.return_value = [0.0] * 3072
    mock_cohere = MagicMock()
    mock_cohere.rerank.side_effect = Exception("no cohere")

    with _stub_retrieve_llm(), \
         patch("app.services.retrieve._get_index", return_value=mock_index), \
         patch("app.services.retrieve._get_embeddings", return_value=mock_embeddings), \
         patch("app.services.retrieve._get_cohere", return_value=mock_cohere):
        result = retrieve_documents("Uslovi raskida ugovora o radu")

    assert isinstance(result, tuple) and len(result) == 2
    docs, meta = result
    assert isinstance(docs, list)
    assert isinstance(meta, dict)
    # Regression guard: pre fix-a je "\n\n".join(docs[:4]) pucao jer je "docs"
    # bio ceo (list, dict) tuple, ne lista stringova.
    kontekst = "\n\n".join(docs[:4]) if docs else ""
    assert isinstance(kontekst, str)


# ─── Bug #2: unguarded OpenAI embeddings poziv (_semanticka_pretraga) ─────────

def test_semanticka_pretraga_hvata_gresku_embeddinga():
    """Prolazna greška OpenAI embeddings API-ja (rate limit, mrežni blip) mora
    biti uhvaćena i vratiti praznu listu, ne propagirati neuhvaćen izuzetak."""
    from app.services.retrieve import _semanticka_pretraga

    mock_index = MagicMock()

    with patch("app.services.retrieve._get_index", return_value=mock_index), \
         patch("app.services.retrieve._ugradi_query", side_effect=Exception("OpenAI rate limit")):
        rezultat = _semanticka_pretraga("test upit", k=5)

    assert rezultat == []
    mock_index.query.assert_not_called()


def test_semanticka_pretraga_normalan_tok_i_dalje_radi():
    """Regression guard: premeštanje _ugradi_query u try blok ne sme pokvariti
    normalan (uspešan) tok pretrage."""
    from app.services.retrieve import _semanticka_pretraga

    mock_index = MagicMock()
    mock_match = MagicMock()
    mock_index.query.return_value = MagicMock(matches=[mock_match])

    with patch("app.services.retrieve._get_index", return_value=mock_index), \
         patch("app.services.retrieve._ugradi_query", return_value=[0.1] * 3072):
        rezultat = _semanticka_pretraga("test upit", k=5)

    assert rezultat == [mock_match]

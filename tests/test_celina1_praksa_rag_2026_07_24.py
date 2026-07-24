# -*- coding: utf-8 -*-
"""
Regression tests — Celina 1: Analiza i Optimizacija Modula Sudske Prakse
i RAG Baze (2026-07-24).

1. app/services/retrieve.py — 3 unguarded _ugradi_query pozivi
   (retrieve_documents, retrieve_sudska_praksa, retrieve_grupisano)
   sada fail-soft; retrieve_sudska_praksa dobija Cohere/GPT re-rank
   umesto čistog cosine-similarity poretka.
2. routers/praksa.py::_fetch_decision_chunks — budžetiranje po sekciji
   (HEADER/IZREKA/OBRAZLOŽENJE) umesto flat [:4500] koji je davao
   OBRAZLOŽENJU (pravno najvrednija sekcija) najmanji prioritet.
3. routers/praksa.py + routers/oblasti.py — @llm_retry dodat na svih
   5 direktnih OpenAI poziva (ranije bez retry-ja, za razliku od
   main.py/drafting koji su ga dobili u Fazi 2).
"""
import sys
import os
import json
from unittest.mock import MagicMock, AsyncMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("FOUNDER_TOKEN", "test-admin-token-12345")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── 1a. retrieve_documents fail-soft embed guard ─────────────────────────

def test_retrieve_documents_embed_failure_vraca_low_confidence():
    from app.services.retrieve import retrieve_documents

    with patch("app.services.retrieve._ugradi_query", side_effect=Exception("rate limit")):
        docs, meta = retrieve_documents("test upit")

    assert docs == []
    assert meta["confidence"] == "LOW"
    assert meta["doc_passages"] == []
    assert meta["praksa_matches"] == []
    assert "izvori" in meta and "confidence_detail" in meta  # pun oblik, ne delimičan


# ─── 1b. retrieve_sudska_praksa fail-soft + re-rank ───────────────────────

def test_retrieve_sudska_praksa_embed_failure_vraca_praznu_listu():
    from app.services.retrieve import retrieve_sudska_praksa

    with patch("app.services.retrieve._ugradi_query", side_effect=Exception("rate limit")):
        result = retrieve_sudska_praksa("test")

    assert result == []


def test_retrieve_sudska_praksa_poziva_cohere_rerank():
    """Ključni regresioni test: pre ove izmene, praksa retrieval je vraćao
    isključivo cosine-similarity poredak bez ikakvog re-rank prolaza."""
    from app.services.retrieve import retrieve_sudska_praksa

    mock_index = MagicMock()
    mock_match = MagicMock()
    mock_index.query.return_value = MagicMock(matches=[mock_match])

    with patch("app.services.retrieve._get_index", return_value=mock_index), \
         patch("app.services.retrieve._ugradi_query", return_value=[0.1] * 3072), \
         patch("app.services.retrieve._cohere_rerank", return_value=["reranked"]) as mock_rerank:
        result = retrieve_sudska_praksa("test query", top_k=10)

    assert result == ["reranked"]
    mock_rerank.assert_called_once()
    args, kwargs = mock_rerank.call_args
    assert args[0] == "test query"
    assert kwargs.get("k") == 10


def test_retrieve_sudska_praksa_fetch_uje_siri_kandidatski_skup():
    """top_k=5 mora i dalje fetch-ovati bar 20 sirovih kandidata pre
    re-rank-a (širi net za bolji izbor), ne samo 5."""
    from app.services.retrieve import retrieve_sudska_praksa

    mock_index = MagicMock()
    mock_index.query.return_value = MagicMock(matches=[])

    with patch("app.services.retrieve._get_index", return_value=mock_index), \
         patch("app.services.retrieve._ugradi_query", return_value=[0.1] * 3072):
        retrieve_sudska_praksa("test", top_k=5)

    call_kwargs = mock_index.query.call_args.kwargs
    assert call_kwargs["top_k"] >= 20


# ─── 1c. retrieve_grupisano fail-soft embed guard ─────────────────────────

def test_retrieve_grupisano_embed_failure_vraca_praznu_strukturu():
    from app.services.retrieve import retrieve_grupisano

    with patch("app.services.retrieve._ugradi_query", side_effect=Exception("rate limit")):
        result = retrieve_grupisano("test upit")

    assert result["total"] == 0
    assert result["query"] == "test upit"
    assert result["grupe"] == {"tuzilac": [], "tuzeni": [], "mesovito": [], "nepoznato": []}
    assert result["statistika"]["pct_tuzilac"] == 0


# ─── 2. _fetch_decision_chunks — budžetiranje po sekciji ──────────────────

def _fake_match(section, text, idx, dn="P 1/2025"):
    m = MagicMock()
    m.metadata = {
        "decision_number": dn, "decision_date": "2025-01-01",
        "court": "Osnovni sud", "matter": "Gradjanska",
        "section": section, "text": text, "chunk_index": idx,
    }
    return m


def test_fetch_decision_chunks_ne_gasi_obrazlozenje_kod_duge_presude():
    """Ključni regresioni test: stari flat [:4500] cutoff (posle
    HEADER+IZREKA+OBRAZLOŽENJE spajanja) je davao prve dve sekcije
    prioritet SAMO zato što idu prve -- za dugu presudu, OBRAZLOŽENJE
    (pravno najvrednija sekcija za poređenje) je bilo skoro u potpunosti
    odsečeno. Sada mora preživeti značajan deo."""
    from routers.praksa import _fetch_decision_chunks

    header_text = "H" * 100
    izreka_text = "I" * 200
    obraz_text = "O" * 10000

    matches = [
        _fake_match("HEADER", header_text, 0),
        _fake_match("IZREKA", izreka_text, 1),
        _fake_match("OBRAZLOŽENJE", obraz_text, 2),
    ]
    mock_index = MagicMock()
    mock_index.query.return_value = MagicMock(matches=matches)

    with patch("app.services.retrieve._get_index", return_value=mock_index):
        meta, full_text = _fetch_decision_chunks("P 1/2025")

    assert "H" * 50 in full_text
    assert "I" * 50 in full_text
    obraz_chars = full_text.count("O")
    assert obraz_chars > 4000, (
        f"OBRAZLOŽENJE mora dobiti većinu budžeta, dobio je samo {obraz_chars} znakova"
    )


def test_fetch_decision_chunks_kratka_presuda_neizmenjena():
    from routers.praksa import _fetch_decision_chunks

    matches = [
        _fake_match("HEADER", "Kratko zaglavlje.", 0),
        _fake_match("IZREKA", "Kratka izreka.", 1),
        _fake_match("OBRAZLOŽENJE", "Kratko obrazloženje.", 2),
    ]
    mock_index = MagicMock()
    mock_index.query.return_value = MagicMock(matches=matches)

    with patch("app.services.retrieve._get_index", return_value=mock_index):
        meta, full_text = _fetch_decision_chunks("P 1/2025")

    assert "Kratko zaglavlje." in full_text
    assert "Kratka izreka." in full_text
    assert "Kratko obrazloženje." in full_text


def test_fetch_decision_chunks_ne_pronadjena_odluka_baca_value_error():
    from routers.praksa import _fetch_decision_chunks
    import pytest

    mock_index = MagicMock()
    mock_index.query.return_value = MagicMock(matches=[])

    with patch("app.services.retrieve._get_index", return_value=mock_index):
        with pytest.raises(ValueError):
            _fetch_decision_chunks("NEPOSTOJECA/2025")


# ─── 3. @llm_retry primenjen na direktne OpenAI pozive ────────────────────

def _fake_chat_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    return resp


def test_oblasti_gpt_call_retry_na_rate_limit():
    from routers.oblasti import _gpt_call
    from openai import RateLimitError

    calls = {"n": 0}

    def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RateLimitError("rate limited", response=MagicMock(status_code=429, headers={}), body=None)
        return _fake_chat_response("odgovor")

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = _side_effect
        out = _gpt_call("system", "user", 500)

    assert out == "odgovor"
    assert calls["n"] == 3


def test_oblasti_gpt_call_ne_ponavlja_bad_request():
    from routers.oblasti import _gpt_call
    from openai import BadRequestError
    import pytest

    calls = {"n": 0}

    def _side_effect(*a, **kw):
        calls["n"] += 1
        raise BadRequestError("bad", response=MagicMock(status_code=400, headers={}), body=None)

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = _side_effect
        with pytest.raises(BadRequestError):
            _gpt_call("system", "user", 500)

    assert calls["n"] == 1


def test_praksa_ratio_api_retry_na_rate_limit():
    from routers.praksa import _pozovi_ratio_api
    from openai import RateLimitError

    calls = {"n": 0}

    def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RateLimitError("rate limited", response=MagicMock(status_code=429, headers={}), body=None)
        return _fake_chat_response("Sud je zauzeo stav...")

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = _side_effect
        out = _pozovi_ratio_api("neki tekst presude")

    assert out == "Sud je zauzeo stav..."
    assert calls["n"] == 2


def test_praksa_uporedi_api_retry_na_rate_limit():
    from routers.praksa import _pozovi_uporedi_api
    from openai import RateLimitError

    calls = {"n": 0}

    def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RateLimitError("rate limited", response=MagicMock(status_code=429, headers={}), body=None)
        return _fake_chat_response("uporedna analiza")

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = _side_effect
        out = _pozovi_uporedi_api("uporedi ove dve odluke")

    assert out == "uporedna analiza"
    assert calls["n"] == 2


def test_praksa_slicni_api_retry_na_rate_limit():
    from routers.praksa import _pozovi_slicni_api
    from openai import RateLimitError

    calls = {"n": 0}

    def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RateLimitError("rate limited", response=MagicMock(status_code=429, headers={}), body=None)
        return _fake_chat_response('{"slicni": []}')

    with patch("openai.OpenAI") as MockOAI:
        MockOAI.return_value.chat.completions.create.side_effect = _side_effect
        out = _pozovi_slicni_api("cinjenice", None, "decisions")

    assert out == '{"slicni": []}'
    assert calls["n"] == 2


def test_praksa_argument_map_api_retry_na_rate_limit():
    import asyncio
    from routers.praksa import _pozovi_argument_map_api
    from openai import RateLimitError

    calls = {"n": 0}

    async def _side_effect(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RateLimitError("rate limited", response=MagicMock(status_code=429, headers={}), body=None)
        return _fake_chat_response('{"za_mene": []}')

    fake_oai = MagicMock()
    fake_oai.chat.completions.create = _side_effect

    out = asyncio.run(_pozovi_argument_map_api(fake_oai, "argument", "decisions"))

    assert out == '{"za_mene": []}'
    assert calls["n"] == 2


# ─── 4. Sentry capture dodat na prethodno tihe/log-only except blokove ────

def test_extract_ratio_sync_zove_sentry_na_gresku():
    from routers import praksa as praksa_mod

    with patch.object(praksa_mod, "_get_ratio_from_cache", return_value=None), \
         patch.object(praksa_mod, "_pozovi_ratio_api", side_effect=Exception("boom")), \
         patch.object(praksa_mod, "_sentry_capture") as mock_capture:
        out = praksa_mod._extract_ratio_sync("P 1/2025", "dovoljno dugačak tekst da prođe proveru dužine od 60 znakova")

    assert out == ""
    mock_capture.assert_called_once()

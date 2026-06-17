# -*- coding: utf-8 -*-
"""Tests for GPT-4o-mini reranker (_gpt_rerank) in retrieve.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from unittest.mock import MagicMock, patch


def _make_match(id_: str, law: str, article: str, text: str, score: float = 0.7):
    m = MagicMock()
    m.id = id_
    m.score = score
    m.metadata = {"law": law, "article": article, "text": text, "parent_text": ""}
    return m


def _gpt_response(indices: list) -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.content = json.dumps(indices)
    return resp


_MATCHES = [
    _make_match("m1", "zakon o radu", "Član 179", "Otkaz ugovora o radu...", score=0.72),
    _make_match("m2", "zakon o radu", "Član 189", "Otkazni rok iznosi...",  score=0.68),
    _make_match("m3", "KZ",           "Član 208", "Krivično delo prevare...", score=0.65),
]


# ─── _gpt_rerank direktni testovi ────────────────────────────────────────────

def test_gpt_rerank_basic():
    """GPT vraća [2,1,3] → matches reordered: m2, m1, m3."""
    from app.services.retrieve import _gpt_rerank

    with patch("app.services.retrieve._get_client") as mk:
        mk.return_value.chat.completions.create.return_value = _gpt_response([2, 1, 3])
        result = _gpt_rerank("otkaz ugovora o radu", _MATCHES, k=3)

    assert len(result) == 3
    assert result[0].id == "m2"
    assert result[1].id == "m1"
    assert result[2].id == "m3"


def test_gpt_rerank_k_limit():
    """k=2 → samo 2 rezultata vraća."""
    from app.services.retrieve import _gpt_rerank

    with patch("app.services.retrieve._get_client") as mk:
        mk.return_value.chat.completions.create.return_value = _gpt_response([3, 1])
        result = _gpt_rerank("prevara KZ", _MATCHES, k=2)

    assert len(result) == 2
    assert result[0].id == "m3"
    assert result[1].id == "m1"


def test_gpt_rerank_empty_matches():
    """Prazna lista → vraća praznu listu bez GPT poziva."""
    from app.services.retrieve import _gpt_rerank

    with patch("app.services.retrieve._get_client") as mk:
        result = _gpt_rerank("otkaz", [], k=3)

    mk.return_value.chat.completions.create.assert_not_called()
    assert result == []


def test_gpt_rerank_gpt_error_fallback():
    """Ako GPT baci grešku → vraća prvih k matches (interni skor)."""
    from app.services.retrieve import _gpt_rerank

    with patch("app.services.retrieve._get_client") as mk:
        mk.return_value.chat.completions.create.side_effect = Exception("timeout")
        result = _gpt_rerank("otkaz", _MATCHES, k=2)

    assert len(result) == 2
    assert result[0].id == "m1"
    assert result[1].id == "m2"


def test_gpt_rerank_invalid_json_fallback():
    """Ako GPT vrati nevažeći JSON → fallback na matches[:k]."""
    from app.services.retrieve import _gpt_rerank

    bad_resp = MagicMock()
    bad_resp.choices[0].message.content = "nije JSON"

    with patch("app.services.retrieve._get_client") as mk:
        mk.return_value.chat.completions.create.return_value = bad_resp
        result = _gpt_rerank("otkaz", _MATCHES, k=2)

    assert len(result) == 2
    assert result[0].id == "m1"


def test_gpt_rerank_out_of_range_idx():
    """GPT vrati indeks 99 (van opsega) → preskočen, ne puca."""
    from app.services.retrieve import _gpt_rerank

    with patch("app.services.retrieve._get_client") as mk:
        mk.return_value.chat.completions.create.return_value = _gpt_response([99, 1])
        result = _gpt_rerank("otkaz", _MATCHES, k=2)

    # idx 99 je van opsega, idx 1 → m1; ostalo fallback
    valid_ids = {r.id for r in result}
    assert "m1" in valid_ids


def test_gpt_rerank_dedup():
    """GPT vrati isti indeks dva puta → deduplikovan."""
    from app.services.retrieve import _gpt_rerank

    with patch("app.services.retrieve._get_client") as mk:
        mk.return_value.chat.completions.create.return_value = _gpt_response([1, 1, 2])
        result = _gpt_rerank("otkaz", _MATCHES, k=3)

    ids = [r.id for r in result]
    assert ids.count("m1") == 1


def test_gpt_rerank_code_block_stripped():
    """GPT obomota JSON u ```json blok → parser ga odbaci i parsira."""
    from app.services.retrieve import _gpt_rerank

    wrapped = MagicMock()
    wrapped.choices[0].message.content = "```json\n[2,1]\n```"

    with patch("app.services.retrieve._get_client") as mk:
        mk.return_value.chat.completions.create.return_value = wrapped
        result = _gpt_rerank("otkaz", _MATCHES, k=2)

    assert result[0].id == "m2"
    assert result[1].id == "m1"


def test_gpt_rerank_parent_text_used_for_snippet():
    """_gpt_rerank koristi parent_text kad postoji za snippet koji šalje GPT-u."""
    from app.services.retrieve import _gpt_rerank

    m = _make_match("px", "zakon o radu", "Član 1", "kratko", score=0.8)
    m.metadata["parent_text"] = "Dugi parent tekst koji objasnjava clan zakona o radu"

    captured_prompt = []

    def _fake_create(**kwargs):
        captured_prompt.append(kwargs["messages"][-1]["content"])
        return _gpt_response([1])

    with patch("app.services.retrieve._get_client") as mk:
        mk.return_value.chat.completions.create.side_effect = _fake_create
        _gpt_rerank("otkaz", [m], k=1)

    assert "Dugi parent tekst" in captured_prompt[0]


# ─── _cohere_rerank fallback integracija ─────────────────────────────────────

def test_cohere_rerank_falls_back_to_gpt_when_no_cohere():
    """_cohere_rerank poziva _gpt_rerank kad COHERE_API_KEY nije postavljen."""
    from app.services.retrieve import _cohere_rerank

    with patch("app.services.retrieve._get_cohere", return_value=None), \
         patch("app.services.retrieve._gpt_rerank", return_value=[_MATCHES[1]]) as mock_gpt:
        result = _cohere_rerank("otkaz", _MATCHES, k=1)

    mock_gpt.assert_called_once_with("otkaz", _MATCHES, 1)
    assert result[0].id == "m2"


def test_cohere_rerank_falls_back_to_gpt_on_exception():
    """_cohere_rerank poziva _gpt_rerank kad Cohere baci grešku."""
    from app.services.retrieve import _cohere_rerank

    co_mock = MagicMock()
    co_mock.rerank.side_effect = Exception("Cohere API down")

    with patch("app.services.retrieve._get_cohere", return_value=co_mock), \
         patch("app.services.retrieve._gpt_rerank", return_value=[_MATCHES[0]]) as mock_gpt:
        result = _cohere_rerank("prevara", _MATCHES, k=1)

    mock_gpt.assert_called_once()
    assert result[0].id == "m1"


def test_cohere_rerank_uses_cohere_when_available():
    """_cohere_rerank koristi Cohere kad je dostupan (GPT se ne poziva)."""
    from app.services.retrieve import _cohere_rerank

    rerank_res = MagicMock()
    rerank_res.results = [MagicMock(index=2), MagicMock(index=0)]

    co_mock = MagicMock()
    co_mock.rerank.return_value = rerank_res

    with patch("app.services.retrieve._get_cohere", return_value=co_mock), \
         patch("app.services.retrieve._gpt_rerank") as mock_gpt:
        result = _cohere_rerank("otkaz", _MATCHES, k=2)

    mock_gpt.assert_not_called()
    assert result[0].id == "m3"
    assert result[1].id == "m1"

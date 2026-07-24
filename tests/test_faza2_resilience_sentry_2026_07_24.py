# -*- coding: utf-8 -*-
"""
Regression tests — Faza 2: Otpornost (Resilience) i Sentry Monitoring (2026-07-24).

1. shared/llm_retry.py::llm_retry — exponential backoff retry na prolaznim
   OpenAI greškama (429/5xx/timeout/connection), NEMA retry na 400/401.
2. shared/sentry.py::capture_exception — bezbedan no-op kad sentry-sdk nije
   instaliran (lokalni dev/test) ili nije inicijalizovan (bez SENTRY_DSN);
   nikad ne sme da baci izuzetak nazad pozivaocu.
"""
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── llm_retry ─────────────────────────────────────────────────────────────

def test_llm_retry_retries_rate_limit_do_uspeha():
    from shared.llm_retry import llm_retry
    from openai import RateLimitError

    calls = {"n": 0}

    @llm_retry
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RateLimitError(
                "rate limited", response=MagicMock(status_code=429, headers={}), body=None
            )
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_llm_retry_ne_ponavlja_bad_request():
    from shared.llm_retry import llm_retry
    from openai import BadRequestError

    calls = {"n": 0}

    @llm_retry
    def uvek_bad_request():
        calls["n"] += 1
        raise BadRequestError(
            "bad request", response=MagicMock(status_code=400, headers={}), body=None
        )

    import pytest
    with pytest.raises(BadRequestError):
        uvek_bad_request()
    assert calls["n"] == 1


def test_llm_retry_ne_ponavlja_authentication_error():
    from shared.llm_retry import llm_retry
    from openai import AuthenticationError

    calls = {"n": 0}

    @llm_retry
    def uvek_401():
        calls["n"] += 1
        raise AuthenticationError(
            "unauthorized", response=MagicMock(status_code=401, headers={}), body=None
        )

    import pytest
    with pytest.raises(AuthenticationError):
        uvek_401()
    assert calls["n"] == 1


def test_llm_retry_odaje_gresku_posle_max_pokusaja():
    from shared.llm_retry import llm_retry
    from openai import InternalServerError

    calls = {"n": 0}

    @llm_retry
    def uvek_500():
        calls["n"] += 1
        raise InternalServerError(
            "server error", response=MagicMock(status_code=500, headers={}), body=None
        )

    import pytest
    with pytest.raises(InternalServerError):
        uvek_500()
    assert calls["n"] == 3  # max 3 pokušaja, zatim se greška propagira


def test_llm_retry_radi_i_na_async_funkcijama():
    import asyncio
    from shared.llm_retry import llm_retry
    from openai import RateLimitError

    calls = {"n": 0}

    @llm_retry
    async def flaky_async():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RateLimitError(
                "rate limited", response=MagicMock(status_code=429, headers={}), body=None
            )
        return "ok-async"

    assert asyncio.run(flaky_async()) == "ok-async"
    assert calls["n"] == 2


# ─── sentry capture helper ───────────────────────────────────────────────────

def test_sentry_capture_ne_baca_kad_sdk_nije_instaliran():
    """U ovom test okruženju sentry-sdk NIJE instaliran -- ovo je namerno,
    dokumentuje da capture_exception mora ostati bezbedan no-op i ovde."""
    from shared.sentry import capture_exception

    try:
        raise ValueError("test greška")
    except Exception as exc:
        capture_exception(exc)  # ne sme da baci


def test_sentry_capture_prosledjuje_kad_je_sdk_dostupan():
    import shared.sentry as sentry_module

    fake_sentry_sdk = MagicMock()
    fake_module = MagicMock()
    fake_module.capture_exception = fake_sentry_sdk.capture_exception

    with patch.dict(sys.modules, {"sentry_sdk": fake_module}):
        exc = ValueError("test greška")
        sentry_module.capture_exception(exc)

    fake_sentry_sdk.capture_exception.assert_called_once_with(exc)


def test_semanticka_pretraga_zove_sentry_capture_na_gresku():
    """Regression guard: _semanticka_pretraga (app/services/retrieve.py) mora
    da pozove capture_exception iz shared.sentry kad OpenAI embeddings pukne."""
    from app.services.retrieve import _semanticka_pretraga

    mock_index = MagicMock()

    with patch("app.services.retrieve._get_index", return_value=mock_index), \
         patch("app.services.retrieve._ugradi_query", side_effect=Exception("boom")), \
         patch("app.services.retrieve._sentry_capture") as mock_capture:
        rezultat = _semanticka_pretraga("test upit", k=5)

    assert rezultat == []
    mock_capture.assert_called_once()

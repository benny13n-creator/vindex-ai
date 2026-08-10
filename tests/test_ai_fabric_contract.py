# -*- coding: utf-8 -*-
"""
LEVEL A + LEVEL B — offline i mock testovi za shared/ai_fabric.py.

NIJEDAN TEST NE PRAVI EKSTERNI AI POZIV.
Level C (realni smoke) je zaseban fajl i opt-in preko RUN_PROVIDER_SMOKE_TESTS.

Šta se ovde dokazuje:
  - kanonski kontekst ide kroz fabric BEZ gubitka provenance-a (test 3)
  - nijedan SDK tip ne izlazi iz adaptera (test 8, 9, 10)
  - capability guard odbija umesto da tiho degradira (test 5)
  - rutiranje je determinističko, fallback samo kad je eksplicitno dozvoljen (6, 7)
  - model ID se NE pogađa kad nije konfigurisan (test 4)
  - greške se normalizuju, sirov SDK izuzetak ne curi u domen (test 11)
  - health check ne pravi naplativ poziv (test 12)
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.ai_fabric import (  # noqa: E402
    AIGateway, AIRequest, AIResponse, AIError, AIInvalidRequestError,
    AIRateLimitError, AITimeoutError, AIUnavailableError,
    AIUnsupportedCapabilityError, AnthropicProvider, Capability, GeminiProvider,
    OpenAIProvider, ProviderRegistry, TaskPolicy, _BaseAdapter, _normalize,
)


# ─── LEVEL A — ugovor, bez ijednog SDK-a ─────────────────────────────────────

def test_1_request_declares_required_capabilities():
    r = AIRequest(task="drafting", prompt="x")
    assert r.required_capabilities() == {Capability.TEXT_GENERATION}
    r2 = AIRequest(task="drafting", prompt="x", schema={"type": "object"})
    assert Capability.STRUCTURED_OUTPUT in r2.required_capabilities()


def test_2_response_total_tokens_is_none_when_unknown():
    assert AIResponse("p", "m", "t").total_tokens is None
    assert AIResponse("p", "m", "t", input_tokens=3, output_tokens=4).total_tokens == 7


def test_3_canonical_context_keeps_provenance():
    """case_context.context_field pakuje {value, source, owner, refresh}.

    Fabric NE sme da odbaci `source` -- to je razlika između činjenice i
    izvedenog zaključka, i jedini razlog zašto kontekst uopšte nosi provenance.
    """
    ctx = {"tuzilac": {"value": "Petar P.", "source": "tuzba.pdf",
                       "owner": "intake", "refresh": "on_document"}}
    out = _BaseAdapter.render_context(ctx)
    assert "Petar P." in out
    assert "tuzba.pdf" in out, "provenance izvora mora preživeti serijalizaciju"


def test_4_model_id_is_never_guessed():
    """Bez ANTHROPIC_MODEL/GEMINI_MODEL adapter odbija umesto da pogodi ID."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}, clear=False):
        os.environ.pop("ANTHROPIC_MODEL", None)
        with pytest.raises(AIInvalidRequestError):
            AnthropicProvider().generate(AIRequest(task="t", prompt="p"))
    with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}, clear=False):
        os.environ.pop("GEMINI_MODEL", None)
        with pytest.raises(AIInvalidRequestError):
            GeminiProvider().generate(AIRequest(task="t", prompt="p"))


def test_5_unsupported_capability_raises_not_silently_degrades():
    class _NoStructured(_BaseAdapter):
        name = "x"
        _caps = {Capability.TEXT_GENERATION}
    with pytest.raises(AIUnsupportedCapabilityError):
        _NoStructured()._require_caps(AIRequest(task="t", prompt="p", schema={"a": 1}))


def test_6_routing_is_deterministic_and_honours_explicit_override():
    reg = ProviderRegistry()
    a = reg.resolve(AIRequest(task="drafting", prompt="p", provider="gemini"))
    assert a.name == "gemini", "eksplicitan override ima prioritet nad politikom"


def test_7_fallback_only_when_policy_allows_it():
    """Podrazumevano NEMA fallback-a: tiha promena provajdera je tiha promena
    kvaliteta pravnog rezultata."""
    cfg = MagicMock(); cfg.is_configured.return_value = False
    cfg.name = "openai"; cfg._caps = {Capability.TEXT_GENERATION}
    ok = MagicMock(); ok.is_configured.return_value = True
    ok.name = "anthropic"; ok._caps = {Capability.TEXT_GENERATION}

    strict = ProviderRegistry([cfg, ok], {"t": TaskPolicy("openai")})
    with pytest.raises(AIUnavailableError):
        strict.resolve(AIRequest(task="t", prompt="p"))

    lenient = ProviderRegistry([cfg, ok], {"t": TaskPolicy("openai", allowed_fallbacks=("anthropic",))})
    assert lenient.resolve(AIRequest(task="t", prompt="p")).name == "anthropic"


# ─── LEVEL B — mock SDK, dokaz mapiranja ─────────────────────────────────────

def test_8_openai_adapter_returns_canonical_response_not_sdk_object():
    fake = MagicMock()
    fake.choices = [MagicMock(message=MagicMock(content="odgovor"), finish_reason="stop")]
    fake.usage = MagicMock(prompt_tokens=11, completion_tokens=22)
    fake.model = "gpt-4o-mini"; fake.id = "req-1"
    client = MagicMock(); client.chat.completions.create.return_value = fake

    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}, clear=False), \
         patch("openai.OpenAI", return_value=client):
        out = OpenAIProvider().generate(AIRequest(task="drafting", prompt="p", correlation_id="c1"))

    assert isinstance(out, AIResponse)
    assert (out.provider, out.text, out.input_tokens, out.output_tokens) == ("openai", "odgovor", 11, 22)
    assert out.provider_request_id == "req-1" and out.correlation_id == "c1"
    assert "MagicMock" not in repr(out.raw_meta), "sirov SDK objekat ne sme u kanonski odgovor"


def test_9_anthropic_adapter_maps_system_to_top_level():
    blok = MagicMock(); blok.type = "text"; blok.text = "claude kaže"
    fake = MagicMock(); fake.content = [blok]; fake.usage = MagicMock(input_tokens=5, output_tokens=6)
    fake.model = "m"; fake.id = "a-1"; fake.stop_reason = "end_turn"
    client = MagicMock(); client.messages.create.return_value = fake

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k", "ANTHROPIC_MODEL": "m"}, clear=False), \
         patch("anthropic.Anthropic", return_value=client):
        out = AnthropicProvider().generate(AIRequest(task="t", prompt="p", system="SYS"))

    kw = client.messages.create.call_args.kwargs
    assert kw["system"] == "SYS", "Anthropic system je top-level, ne poruka"
    assert all(m["role"] != "system" for m in kw["messages"])
    assert (out.provider, out.text, out.input_tokens) == ("anthropic", "claude kaže", 5)


def test_10_gemini_adapter_maps_system_to_constructor():
    fake = MagicMock(); fake.text = "gemini kaže"
    fake.usage_metadata = MagicMock(prompt_token_count=7, candidates_token_count=8)
    fake.candidates = [MagicMock(finish_reason="STOP")]
    gm = MagicMock(); gm.generate_content.return_value = fake

    with patch.dict(os.environ, {"GEMINI_API_KEY": "k", "GEMINI_MODEL": "g"}, clear=False), \
         patch("google.generativeai.configure"), \
         patch("google.generativeai.GenerativeModel", return_value=gm) as ctor:
        out = GeminiProvider().generate(AIRequest(task="t", prompt="p", system="SYS"))

    assert ctor.call_args.kwargs["system_instruction"] == "SYS"
    assert (out.provider, out.text, out.output_tokens) == ("gemini", "gemini kaže", 8)


def test_11_sdk_exceptions_are_normalized_never_leak():
    class RateLimitError(Exception): pass
    class APITimeoutError(Exception): pass
    class APIConnectionError(Exception): pass
    assert isinstance(_normalize(RateLimitError("x"), "openai", "m"), AIRateLimitError)
    assert isinstance(_normalize(APITimeoutError("x"), "openai", "m"), AITimeoutError)
    assert isinstance(_normalize(APIConnectionError("x"), "openai", "m"), AIUnavailableError)
    assert _normalize(RateLimitError("x"), "openai", "m").retryable is True


def test_12_health_check_makes_no_billable_call():
    with patch("openai.OpenAI") as ctor:
        h = ProviderRegistry().health("openai")
    ctor.assert_not_called(), "health sme da gleda samo konfiguraciju"
    assert set(h) == {"provider", "configured", "default_model", "capabilities"}


def test_13_gateway_reuses_existing_correlation_infrastructure():
    """Bez druge korelacione šeme -- koristi shared.ai_provenance."""
    gw = AIGateway()
    with patch("shared.ai_provenance.current_correlation_id", return_value="corr-9"):
        req = gw._correlate(AIRequest(task="t", prompt="p"))
    assert req.correlation_id == "corr-9"


def test_14_gateway_emits_telemetry_on_failure_and_reraises():
    class _Boom(MagicMock):
        name = "openai"
    bad = MagicMock(); bad.name = "openai"; bad.is_configured.return_value = True
    bad._caps = {Capability.TEXT_GENERATION}
    bad.generate.side_effect = AITimeoutError("timeout", "openai", "m")
    gw = AIGateway(ProviderRegistry([bad], {"t": TaskPolicy("openai")}))
    with pytest.raises(AITimeoutError):
        gw.generate(AIRequest(task="t", prompt="p"))


def test_15_openai_default_model_matches_repository_reality():
    """gpt-4o-mini je model koji repo stvarno koristi na 59 mesta -- nije pogodak."""
    os.environ.pop("OPENAI_MODEL", None)
    assert OpenAIProvider().default_model() == "gpt-4o-mini"


def test_16_all_three_providers_registered_with_capabilities():
    reg = ProviderRegistry()
    assert reg.names() == ["anthropic", "gemini", "openai"]
    for n in reg.names():
        assert Capability.TEXT_GENERATION.value in reg.health(n)["capabilities"]

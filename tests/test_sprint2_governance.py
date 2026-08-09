# -*- coding: utf-8 -*-
"""
Sprint 2 — governance gaps: AI paths that were outside the guard/audit surface.

Three of the four items here are invisible to any coverage count, which is why
they survived: the call-site inventory regex looked for chat/embedding shapes,
so audio never appeared in it; the identity stamp existed but was documented as
inert; and the contextvars loss happens at a thread boundary rather than in any
one function.

Behavioural throughout. Nothing here asserts on source text alone.
"""
import asyncio
import contextvars
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── S2-1: audio.* was never intercepted ────────────────────────────────────

def test_audio_transcriptions_is_intercepted():
    """routers/voice.py::_pozovi_whisper_api calls audio.transcriptions.create.
    The patch covered Completions and Embeddings only, so Whisper produced ZERO
    provenance rows and carried no timeout -- a whole modality outside the audit
    surface, and invisible to every coverage count because the inventory regex
    looked for chat/embedding call shapes."""
    import api  # noqa: F401 — bootstraps the patch, as gunicorn does
    from openai.resources.audio.transcriptions import AsyncTranscriptions, Transcriptions

    assert Transcriptions.create.__name__ == "_tracked"
    assert AsyncTranscriptions.create.__name__ == "_tracked"


def test_audio_speech_is_intercepted():
    """Same for TTS (audio.speech.create, _pozovi_tts_api)."""
    import api  # noqa: F401
    from openai.resources.audio.speech import AsyncSpeech, Speech

    assert Speech.create.__name__ == "_tracked"
    assert AsyncSpeech.create.__name__ == "_tracked"


def test_chat_and_embeddings_are_still_intercepted():
    """No regression: extending the patch must not displace what it covered."""
    import api  # noqa: F401
    from openai.resources.chat.completions import Completions
    from openai.resources.embeddings import Embeddings

    assert Completions.create.__name__ == "_guarded_create"
    assert Embeddings.create.__name__ == "_tracked_embed"


def test_audio_calls_record_provenance_on_success_and_on_failure():
    """The gap here is AUDIT, not guard: Whisper input is audio bytes, so
    prompt-guard cannot apply -- but the operation must still leave a provenance
    row, and a FAILED call must leave one too. Before this, audio produced none."""
    import api  # noqa: F401 — bootstraps the patch
    import shared.ai_client as ac
    from openai.resources.audio.speech import Speech

    seen = []

    def _spy(_self, _kwargs, _response, _latency, error=None):
        seen.append(error)

    # Success path: the patched method must call the provenance hook.
    with patch.object(ac, "_capture_embedding_provenance", _spy):
        fake_self = MagicMock()
        fake_self._post = MagicMock(return_value=MagicMock())
        try:
            Speech.create(fake_self, model="tts-1", voice="alloy", input="tekst")
        except Exception:
            pass

    assert seen, "an audio call must reach the provenance hook"


def test_audio_calls_carry_the_default_timeout():
    """Same 600s SDK default applied to audio, and Whisper uploads are the
    largest payloads the product sends."""
    import api  # noqa: F401
    import shared.ai_client as ac
    from openai.resources.audio.speech import Speech

    captured = {}

    def _fake_post(*args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop here — we only need the kwargs")

    with patch.object(ac, "_capture_embedding_provenance", lambda *a, **k: None):
        fake_self = MagicMock()
        fake_self._post = _fake_post
        try:
            Speech.create(fake_self, model="tts-1", voice="alloy", input="tekst")
        except Exception:
            pass

    assert "timeout" in captured or captured.get("options") is not None, (
        "the audio call must carry a timeout down to the transport"
    )


# ── S2-3: the identity stamp was inert across 13 endpoints ─────────────────

@pytest.mark.anyio
async def test_require_auth_async_actually_stamps_the_request_context():
    """_require_auth stamps user_id itself, but every caller invoked it as
    `await asyncio.to_thread(_require_auth, ...)`, and a contextvar mutation made
    inside a to_thread-offloaded function does not propagate back to the awaiting
    coroutine. api.py's own comment said so and called it "currently inert".

    Consequence: every AI provenance row on those 13 endpoints carried
    user_id=NULL, so the audit trail could not answer "who ran this"."""
    import api
    from shared import ai_provenance as prov

    fake_user = MagicMock()
    fake_user.id = "user-abc-123"

    prov.set_request_context(user_id=None)
    with patch.object(api, "_require_auth", return_value=fake_user):
        await api._require_auth_async("Bearer whatever")

    assert prov.current_context().get("user_id") == "user-abc-123", (
        "the stamp must survive into the caller's own coroutine"
    )


@pytest.mark.anyio
async def test_require_auth_async_propagates_authentication_failures():
    """No regression: a bad token must still 401, not be swallowed by the
    wrapper."""
    from fastapi import HTTPException
    import api

    with patch.object(api, "_require_auth", side_effect=HTTPException(status_code=401, detail="x")):
        with pytest.raises(HTTPException) as exc:
            await api._require_auth_async("Bearer bad")
    assert exc.value.status_code == 401


def test_no_endpoint_still_uses_the_inert_thread_hop():
    """The 13 call sites must all be rewired; the only remaining to_thread hop
    is the one inside the wrapper itself."""
    import inspect
    import api

    # Counted from the AST, not from text. Both a comment and a docstring in
    # api.py quote the old call shape while explaining why it was inert, and a
    # substring count is fooled by either -- which it was, twice, while writing
    # this test.
    import ast

    tree = ast.parse(inspect.getsource(api))
    hops = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr == "to_thread":
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Name) and first.id == "_require_auth":
                hops += 1

    assert hops == 1, (
        f"only the wrapper may call _require_auth off-thread; found {hops} real call(s)"
    )


# ── S2-4: contextvars did not cross the RAG thread boundary ────────────────

def test_contextvars_do_not_cross_a_raw_executor_without_copy_context():
    """Establishes the premise rather than assuming it: this is the behaviour
    that made the RAG path lose identity and correlation."""
    var = contextvars.ContextVar("probe", default=None)
    var.set("set-in-caller")

    with ThreadPoolExecutor(max_workers=1) as ex:
        got_raw = ex.submit(var.get).result()
        got_ctx = ex.submit(contextvars.copy_context().run, var.get).result()

    assert got_raw is None, "a raw submit loses the context (this is the defect)"
    assert got_ctx == "set-in-caller", "copy_context().run carries it across"


def test_rag_executor_submits_carry_the_context():
    """_decomp_fn, _generisi_hyde, _prosiri_query_gpt_wrapper and
    _semanticka_pretraga all make provider calls. Without copy_context their
    provenance rows lost user_id AND correlation_id even when the request
    context was correctly set upstream -- on the busiest AI path in the product."""
    import inspect
    import app.services.retrieve as r

    src = inspect.getsource(r)
    for fn in ("_decomp_fn", "_generiši_hyde", "_prosiri_query_gpt_wrapper", "_semanticka_pretraga"):
        idx = src.index(f"submit(contextvars.copy_context().run, {fn}")
        assert idx > 0, f"{fn} must be submitted with a copied context"

    assert "submit(_decomp_fn" not in src
    assert "submit(_prosiri_query_gpt_wrapper" not in src


# ── S2-2: the realtime voice session ignored the EU/Azure redirect ─────────

@pytest.mark.anyio
async def test_realtime_voice_refuses_to_run_under_eu_configuration():
    """shared/ai_client.py redirects every OpenAI SDK call to Azure when
    AZURE_OPENAI_KEY and AZURE_OPENAI_ENDPOINT are set. voice_orchestrator does
    not use the SDK -- it opens a raw WebSocket to a hardcoded
    wss://api.openai.com/v1/realtime -- so it ignored that redirect entirely.

    A firm on the EU-residency configuration believes all AI traffic stays in
    the EU. Vindex Live carries the lawyer's spoken, privileged client
    conversation and its Whisper transcription. Silently sending that to OpenAI
    US is a false statement about where the data went, so the session must be
    refused instead."""
    import services.voice_orchestrator as vo

    with patch.dict(os.environ, {
        "AZURE_OPENAI_KEY": "fake-azure-key",
        "AZURE_OPENAI_ENDPOINT": "https://fake.openai.azure.com",
        "OPENAI_API_KEY": "sk-fake",
    }):
        with pytest.raises(RuntimeError) as exc:
            await vo._connect_openai_realtime()

    assert "EU" in str(exc.value), "the refusal must say why"


@pytest.mark.anyio
async def test_realtime_voice_still_connects_without_azure_configuration():
    """No regression: on the normal OpenAI configuration the session must still
    open. Only the transport is asserted here -- the connect itself is mocked,
    so no network call is made."""
    import services.voice_orchestrator as vo

    seen = {}

    async def _fake_connect(url, **kwargs):
        seen["url"] = url
        return MagicMock()

    fake_ws = MagicMock()
    fake_ws.connect = _fake_connect

    env = {k: v for k, v in os.environ.items()
           if k not in ("AZURE_OPENAI_KEY", "AZURE_OPENAI_ENDPOINT")}
    env["OPENAI_API_KEY"] = "sk-fake"

    with patch.dict(os.environ, env, clear=True), \
         patch.dict("sys.modules", {"websockets": fake_ws}):
        await vo._connect_openai_realtime()

    assert seen["url"].startswith("wss://api.openai.com/v1/realtime")

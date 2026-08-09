# -*- coding: utf-8 -*-
"""
AI Client factory — transparentno bira OpenAI ili Azure OpenAI, i (SEC-003)
centralno primenjuje Prompt Guard na SVAKI GPT poziv u aplikaciji.

Ako su AZURE_OPENAI_KEY i AZURE_OPENAI_ENDPOINT postavljeni u .env,
svi OpenAI pozivi idu na Azure (podaci ostaju u EU).
Ako nisu, koristi standardni OpenAI API.

Pozovi _patch_openai_module() i _patch_prompt_guard() na startu pre bilo kog
router importa. Azure deployment imena moraju da se poklapaju sa model imenima:
  - "gpt-4o"      → Azure deployment "gpt-4o"
  - "gpt-4o-mini" → Azure deployment "gpt-4o-mini"

SEC-003 — centralni guard:
  Umesto da se svako od ~130 pozivnih mesta (api.py + ~50 routers/services
  fajlova) samo seti da pozove security/prompt_guard.py, _patch_prompt_guard()
  presreće OpenAI SDK-ovu Completions.create/AsyncCompletions.create metodu
  direktno na klasi — TAČNO onu metodu koju svaki poziv u aplikaciji na kraju
  zove, bez obzira gde je klijent konstruisan. Ovo je ista tehnika koju
  _patch_openai_module() već koristi za Azure redirect (patch na klasu, ne
  na instancu), primenjena na bezbednosni sloj. Rezultat: nijedno pozivno
  mesto ne mora da se menja da bi bilo zaštićeno — zaštita je strukturna,
  ne zavisi od toga da li je autor te rute setio da doda proveru.
"""
import inspect
import logging
import os

logger = logging.getLogger("vindex.ai_client")

_patched = False
_guard_patched = False


def _patch_openai_module() -> None:
    """
    Monkey-patchuje openai.OpenAI i openai.AsyncOpenAI da koriste Azure
    ako su Azure env var-ovi postavljeni. Mora se pozvati pre svih router importa.
    """
    global _patched
    if _patched:
        return

    azure_key      = os.getenv("AZURE_OPENAI_KEY", "").strip()
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()

    if not (azure_key and azure_endpoint):
        logger.info("[AI] Koristi standardni OpenAI API")
        _patched = True
        return

    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    endpoint    = azure_endpoint.rstrip("/")

    try:
        import openai
        from openai import AzureOpenAI as _AzSync, AsyncAzureOpenAI as _AzAsync

        class _PatchedSync(_AzSync):
            def __init__(self, api_key=None, **kwargs):
                super().__init__(
                    api_key=azure_key,
                    azure_endpoint=endpoint,
                    api_version=api_version,
                )

        class _PatchedAsync(_AzAsync):
            def __init__(self, api_key=None, **kwargs):
                super().__init__(
                    api_key=azure_key,
                    azure_endpoint=endpoint,
                    api_version=api_version,
                )

        openai.OpenAI      = _PatchedSync
        openai.AsyncOpenAI = _PatchedAsync

        logger.info("[AI] Azure OpenAI aktivan — endpoint: %s  version: %s", endpoint, api_version)

    except Exception as exc:
        logger.error("[AI] Patch neuspešan, koristim standardni OpenAI: %s", exc)

    _patched = True


def _extract_user_text(messages) -> str:
    """
    Spaja tekst svih 'user'-role poruka iz messages liste — ovo je jedini
    deo poziva koji guard analizira (isti ugovor kao wrap_for_ai(): nepoverljiv
    sadržaj živi u 'user' porukama, 'system' poruke su poverljive instrukcije
    koje autor rute kontroliše, ne korisnik/dokument).

    Podržava i string i multimodalni (lista content-parts) format poruke.
    """
    if not messages:
        return ""
    parts: list[str] = []
    for m in messages:
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
        if role != "user":
            continue
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", "") or "")
    return "\n".join(p for p in parts if p)


def _caller_hint(depth: int = 2) -> str:
    # Dijagnostika: koji fajl/funkcija je pozvao create() — korisno u
    # logovima kad se poziv blokira, s obzirom da patch ne zna koja je
    # ruta u pitanju (to je upravo poenta — ne zavisi od pozivnog mesta).
    # Mission Atlas (2026-08-03): isti mehanizam sada služi i kao automatski
    # 'module_name'/'operation_name' za AI Provenance kad pozivno mesto nije
    # eksplicitno postavilo shared/ai_provenance.py's case_context().
    try:
        frame = inspect.stack()[depth]
        return f"{frame.filename.split(os.sep)[-1]}:{frame.function}:{frame.lineno}"
    except Exception:
        return "unknown"


def _client_provider_name(self) -> str:
    """'azure' ako je resurs vezan za AzureOpenAI/AsyncAzureOpenAI klijenta,
    inace 'openai' — cita se preko resursa._client, standardni openai SDK
    atribut (Completions/Embeddings instanca uvek drzi referencu na svog
    roditeljskog klijenta)."""
    try:
        client = getattr(self, "_client", None)
        if client is not None and "Azure" in type(client).__name__:
            return "azure"
    except Exception:
        pass
    return "openai"


# Mission Atlas (2026-08-03): _orig_create/_orig_acreate/_orig_embed/
# _orig_aembed su namerno modulskog nivoa (ne closure lokali unutar
# _patch_prompt_guard) da bi testovi mogli da ih monkeypatch-uju direktno
# (unittest.mock.patch("shared.ai_client._orig_create", ...)) i simuliraju
# uspesan odgovor bez pravog mrežnog poziva — bez ovoga, provenance-capture
# logika (koja treba PRAVI response objekat da izvuce model/tokene/sadržaj)
# ne bi bila testabilna bez stvarnog OpenAI pristupa.
_orig_create = None
_orig_acreate = None
_orig_embed = None
_orig_aembed = None


def _capture_chat_provenance(self, kwargs: dict, response, latency_ms: int, error: Exception | None = None) -> None:
    """Gradi i (fire-and-forget, fail-soft) upisuje provenance zapis za JEDAN
    chat.completions.create poziv. Nikad ne baca — greška ovde ne sme
    da utiče na AI poziv koji je vec zavrsen (uspesno ili neuspesno)."""
    try:
        import asyncio
        from shared import ai_provenance as _prov
        from security.ai_forensics import log_provenance_from_wrapper

        ctx = _prov.current_context()
        messages = kwargs.get("messages") or []
        system_text = "\n".join(
            (m.get("content") if isinstance(m, dict) else getattr(m, "content", "")) or ""
            for m in messages
            if (m.get("role") if isinstance(m, dict) else getattr(m, "role", None)) == "system"
        )
        user_text = _extract_user_text(messages)

        output_text = None
        token_in = token_out = None
        model_reported = kwargs.get("model")
        if response is not None:
            try:
                output_text = (response.choices[0].message.content or "") if response.choices else ""
            except Exception:
                output_text = None
            usage = getattr(response, "usage", None)
            if usage is not None:
                token_in = getattr(usage, "prompt_tokens", None)
                token_out = getattr(usage, "completion_tokens", None)
            model_reported = getattr(response, "model", None) or model_reported

        record_kwargs = dict(
            module_name=ctx.get("module_name") or _caller_hint(depth=3),
            operation_name=ctx.get("operation_name"),
            model_provider=_client_provider_name(self),
            model_name=model_reported or "unknown",
            system_prompt_hash=_prov.sha256_text(system_text),
            user_prompt_hash=_prov.sha256_text(user_text),
            token_usage_input=token_in,
            token_usage_output=token_out,
            latency_ms=latency_ms,
            output_hash=_prov.sha256_text(output_text) if output_text else None,
            correlation_id=ctx.get("correlation_id") or _prov.new_correlation_id(),
            parent_event_id=ctx.get("parent_event_id"),
            user_id=ctx.get("user_id"),
            tenant_id=ctx.get("tenant_id"),
            predmet_id=ctx.get("predmet_id"),
            document_id=ctx.get("document_id"),
            knowledge_sources=ctx.get("knowledge_sources"),
            retrieved_context_ids=ctx.get("retrieved_context_ids"),
            retrieval_query=ctx.get("retrieval_query"),
            status="error" if error else "success",
            error_message=str(error)[:500] if error else None,
        )

        coro = log_provenance_from_wrapper(**record_kwargs)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            asyncio.run(coro)
    except Exception as exc:
        logger.debug("[AI_PROVENANCE] capture greška (nije kritično): %s", exc)


def _capture_embedding_provenance(self, kwargs: dict, response, latency_ms: int, error: Exception | None = None) -> None:
    """Isto kao _capture_chat_provenance, za Embeddings.create — nema
    system/user razdvajanje ni izlazni tekst (vektor nije 'odgovor' u istom
    smislu), pa se hashuje ulazni tekst i broje tokeni ako su dostupni."""
    try:
        import asyncio
        from shared import ai_provenance as _prov
        from security.ai_forensics import log_provenance_from_wrapper

        ctx = _prov.current_context()
        input_val = kwargs.get("input")
        input_text = input_val if isinstance(input_val, str) else "\n".join(str(x) for x in (input_val or []))

        token_in = None
        model_reported = kwargs.get("model")
        if response is not None:
            usage = getattr(response, "usage", None)
            if usage is not None:
                token_in = getattr(usage, "prompt_tokens", None)
            model_reported = getattr(response, "model", None) or model_reported

        coro = log_provenance_from_wrapper(
            module_name=ctx.get("module_name") or _caller_hint(depth=3),
            operation_name=ctx.get("operation_name") or "embedding",
            model_provider=_client_provider_name(self),
            model_name=model_reported or "unknown",
            user_prompt_hash=_prov.sha256_text(input_text),
            token_usage_input=token_in,
            latency_ms=latency_ms,
            correlation_id=ctx.get("correlation_id") or _prov.new_correlation_id(),
            parent_event_id=ctx.get("parent_event_id"),
            user_id=ctx.get("user_id"),
            tenant_id=ctx.get("tenant_id"),
            predmet_id=ctx.get("predmet_id"),
            document_id=ctx.get("document_id"),
            retrieval_query=ctx.get("retrieval_query"),
            status="error" if error else "success",
            error_message=str(error)[:500] if error else None,
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            asyncio.run(coro)
    except Exception as exc:
        logger.debug("[AI_PROVENANCE] embedding capture greška (nije kritično): %s", exc)


# ── S1-2 (2026-08-09): default per-request timeout ─────────────────────────
# 111 OpenAI/AsyncOpenAI constructions exist in application code and NOT ONE
# sets `timeout=` (verified by grep). The installed SDK's default is
# Timeout(connect=5, read=600) with max_retries=2 -- so one logical call could
# occupy up to 3 x 600s of wall time before @llm_retry even began its own 3
# attempts.
#
# That matters more here than it would elsewhere: production runs ONE uvicorn
# process (measured -- 24/24 parallel /health requests, same pid, workers:1),
# and the sync GPT calls are dispatched through asyncio.to_thread into the
# default executor, which is the SAME pool the ~1,500 Supabase call sites use.
# A degraded provider could therefore hold every worker thread and stop the app
# from serving anything at all.
#
# Applied HERE rather than at the 111 construction sites: every call already
# funnels through this patch, so one edit covers all of them and cannot be
# missed by a new call site added later.
#
# Overridable per call -- an explicit timeout= in kwargs always wins, so a
# deliberately long-running call can still opt out.
_DEFAULT_LLM_TIMEOUT_S = float(os.getenv("VINDEX_LLM_TIMEOUT_S", "60"))


def _with_timeout(kwargs: dict) -> dict:
    if "timeout" not in kwargs or kwargs.get("timeout") is None:
        kwargs["timeout"] = _DEFAULT_LLM_TIMEOUT_S
    return kwargs


def _patch_prompt_guard() -> None:
    """
    SEC-003 — presreće Completions.create/AsyncCompletions.create na nivou
    KLASE (ne instance), pre bilo kog OpenAI/AsyncOpenAI konstruktora u
    aplikaciji. Svaki od ~130 pozivnih mesta u api.py/routers//services/
    prolazi kroz ovu proveru, bez obzira da li je to pozivno mesto ikad
    čulo za security/prompt_guard.py.

    Ako je 'user'-role sadržaj poziva iznad BLOCK_THRESHOLD (security/
    prompt_guard.py::analyze), poziv OpenAI-u se NIKAD ne izvršava —
    PromptInjectionBlocked se podiže pre _orig_create/_orig_acreate.

    Mission Atlas (2026-08-03): isti presretnuti sloj sada dodatno beleži AI
    Provenance (shared/ai_provenance.py + security/ai_forensics.py) na SVAKI
    poziv koji stigne do OpenAI-a — isti "jedan ulaz, jedna implementacija"
    princip kao SEC-003, primenjen na sledljivost umesto bezbednosti. Ovo je
    NAMERNO isti patch point, ne paralelan mehanizam.
    """
    global _guard_patched, _orig_create, _orig_acreate, _orig_embed, _orig_aembed
    if _guard_patched:
        return

    try:
        from openai.resources.chat.completions.completions import (
            AsyncCompletions,
            Completions,
        )
    except Exception as exc:
        logger.error("[AI_GUARD] Nisam mogao da uvezem OpenAI Completions klase, guard NIJE aktivan: %s", exc)
        _guard_patched = True
        return

    from security.prompt_guard import PromptInjectionBlocked
    from security.prompt_guard import analyze as _analyze

    _orig_create = Completions.create
    _orig_acreate = AsyncCompletions.create

    def _guarded_create(self, *args, **kwargs):
        text = _extract_user_text(kwargs.get("messages"))
        if text:
            result = _analyze(text)
            if result.blocked:
                logger.warning(
                    "[AI_GUARD] BLOCKED (sync) caller=%s score=%.2f flags=%d",
                    _caller_hint(), result.risk_score, len(result.flags),
                )
                raise PromptInjectionBlocked(result.risk_score, result.flags)
        import time
        _t0 = time.monotonic()
        try:
            response = _orig_create(self, *args, **_with_timeout(kwargs))
        except Exception as exc:
            _capture_chat_provenance(self, kwargs, None, int((time.monotonic() - _t0) * 1000), error=exc)
            raise
        _capture_chat_provenance(self, kwargs, response, int((time.monotonic() - _t0) * 1000))
        return response

    async def _guarded_acreate(self, *args, **kwargs):
        text = _extract_user_text(kwargs.get("messages"))
        if text:
            import asyncio
            result = await asyncio.to_thread(_analyze, text)
            if result.blocked:
                logger.warning(
                    "[AI_GUARD] BLOCKED (async) caller=%s score=%.2f flags=%d",
                    _caller_hint(), result.risk_score, len(result.flags),
                )
                raise PromptInjectionBlocked(result.risk_score, result.flags)
        import time
        _t0 = time.monotonic()
        try:
            response = await _orig_acreate(self, *args, **_with_timeout(kwargs))
        except Exception as exc:
            _capture_chat_provenance(self, kwargs, None, int((time.monotonic() - _t0) * 1000), error=exc)
            raise
        _capture_chat_provenance(self, kwargs, response, int((time.monotonic() - _t0) * 1000))
        return response

    Completions.create = _guarded_create
    AsyncCompletions.create = _guarded_acreate

    try:
        from openai.resources.embeddings import AsyncEmbeddings, Embeddings

        _orig_embed = Embeddings.create
        _orig_aembed = AsyncEmbeddings.create

        def _tracked_embed(self, *args, **kwargs):
            import time
            _t0 = time.monotonic()
            try:
                response = _orig_embed(self, *args, **kwargs)
            except Exception as exc:
                _capture_embedding_provenance(self, kwargs, None, int((time.monotonic() - _t0) * 1000), error=exc)
                raise
            _capture_embedding_provenance(self, kwargs, response, int((time.monotonic() - _t0) * 1000))
            return response

        async def _tracked_aembed(self, *args, **kwargs):
            import time
            _t0 = time.monotonic()
            try:
                response = await _orig_aembed(self, *args, **kwargs)
            except Exception as exc:
                _capture_embedding_provenance(self, kwargs, None, int((time.monotonic() - _t0) * 1000), error=exc)
                raise
            _capture_embedding_provenance(self, kwargs, response, int((time.monotonic() - _t0) * 1000))
            return response

        Embeddings.create = _tracked_embed
        AsyncEmbeddings.create = _tracked_aembed
    except Exception as exc:
        logger.warning("[AI_PROVENANCE] Embeddings provenance patch neuspešan (nije kritično): %s", exc)

    _guard_patched = True
    logger.info(
        "[AI_GUARD] Prompt Guard presreo Completions.create/AsyncCompletions.create "
        "— svi GPT pozivi u aplikaciji sada strukturno zaštićeni (SEC-003) i "
        "beleže AI Provenance (Mission Atlas)"
    )

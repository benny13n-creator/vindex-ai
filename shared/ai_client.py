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
    """
    global _guard_patched
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

    def _caller_hint() -> str:
        # Dijagnostika: koji fajl/funkcija je pozvao create() — korisno u
        # logovima kad se poziv blokira, s obzirom da patch ne zna koja je
        # ruta u pitanju (to je upravo poenta — ne zavisi od pozivnog mesta).
        try:
            frame = inspect.stack()[2]
            return f"{frame.filename.split(os.sep)[-1]}:{frame.function}:{frame.lineno}"
        except Exception:
            return "unknown"

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
        return _orig_create(self, *args, **kwargs)

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
        return await _orig_acreate(self, *args, **kwargs)

    Completions.create = _guarded_create
    AsyncCompletions.create = _guarded_acreate
    _guard_patched = True
    logger.info(
        "[AI_GUARD] Prompt Guard presreo Completions.create/AsyncCompletions.create "
        "— svi GPT pozivi u aplikaciji sada strukturno zaštićeni (SEC-003)"
    )

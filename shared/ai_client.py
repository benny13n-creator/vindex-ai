# -*- coding: utf-8 -*-
"""
AI Client factory — transparentno bira OpenAI ili Azure OpenAI.

Ako su AZURE_OPENAI_KEY i AZURE_OPENAI_ENDPOINT postavljeni u .env,
svi OpenAI pozivi idu na Azure (podaci ostaju u EU).
Ako nisu, koristi standardni OpenAI API.

Pozovi _patch_openai_module() na startu pre bilo kog router importa.
Azure deployment imena moraju da se poklapaju sa model imenima:
  - "gpt-4o"      → Azure deployment "gpt-4o"
  - "gpt-4o-mini" → Azure deployment "gpt-4o-mini"
"""
import logging
import os

logger = logging.getLogger("vindex.ai_client")

_patched = False


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

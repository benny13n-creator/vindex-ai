# -*- coding: utf-8 -*-
"""
Vindex AI — security/ai_forensics.py

AI Forensics — beleži svaki AI poziv sa svim relevantnim metapodacima.

Svrha: Potpuna rekonstrukcija svakog AI odgovora čak i godinama kasnije.
Odgovara na: Ko je zatražio analizu? Koji dokumenti su korišćeni?
             Koja verzija modela je odgovorila? Kakav je bio prompt?

Tabela: ai_forensics (videti SQL migraciju)
Čitanje: SELECT * FROM ai_forensics WHERE user_id='...' ORDER BY started_at DESC
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger("vindex.security.forensics")

# ─── ForensicsRecord ─────────────────────────────────────────────────────────

class ForensicsRecord:
    """
    Kontekst manager za praćenje jednog AI poziva.

    Upotreba:
        async with ForensicsRecord(user_id, endpoint) as rec:
            rec.set_prompt(system_prompt, user_input)
            rec.set_documents(docs)
            result = await ai_call(...)
            rec.set_response(result)
    """

    def __init__(self, user_id: str, endpoint: str, model: str = "gpt-4o"):
        self.user_id    = user_id
        self.endpoint   = endpoint
        self.model      = model
        self._start     = time.monotonic()
        self._data: dict[str, Any] = {
            "user_id":        user_id,
            "endpoint":       endpoint,
            "model":          model,
            "started_at":     _utcnow(),
            "prompt_hash":    None,
            "documents_count": 0,
            "document_hashes": [],
            "injection_risk_score": 0.0,
            "injection_flags": [],
            "finished_at":    None,
            "latency_ms":     None,
            "response_hash":  None,
            "tokens_prompt":  None,
            "tokens_completion": None,
            "prompt_version": os.getenv("PROMPT_VERSION", "1.0"),
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._data["finished_at"] = _utcnow()
        self._data["latency_ms"]  = int((time.monotonic() - self._start) * 1000)
        asyncio.create_task(_persist(self._data.copy()))
        return False   # ne guta izuzetke

    def set_prompt(
        self,
        system_prompt: str,
        user_input: str,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> None:
        combined = f"{system_prompt}\n\n{user_input}"
        self._data["prompt_hash"]  = _sha256(combined)
        self._data["temperature"]  = temperature
        self._data["max_tokens"]   = max_tokens
        self._data["input_chars"]  = len(user_input)

    def set_documents(self, documents: list[str]) -> None:
        self._data["documents_count"] = len(documents)
        self._data["document_hashes"] = [_sha256(d)[:16] for d in documents[:20]]

    def set_injection_analysis(self, risk_score: float, flags: list[str]) -> None:
        self._data["injection_risk_score"] = round(risk_score, 4)
        self._data["injection_flags"]      = flags[:10]  # max 10 flagova

    def set_response(self, response_text: str, usage: Optional[dict] = None) -> None:
        self._data["response_hash"] = _sha256(response_text)
        if usage:
            self._data["tokens_prompt"]     = usage.get("prompt_tokens")
            self._data["tokens_completion"] = usage.get("completion_tokens")


# ─── Async persistence ────────────────────────────────────────────────────────

async def _persist(data: dict) -> None:
    """Upisuje forensics zapis u Supabase. Fire-and-forget, nikad ne blokira."""
    try:
        from api import _get_supa  # import ovde da se izbegne cirkularna zavisnost
        supa = _get_supa()
        # JSONB polja moraju biti json-serializable
        safe_data = {
            k: (json.dumps(v) if isinstance(v, list) else v)
            for k, v in data.items()
        }
        await asyncio.to_thread(
            lambda: supa.table("ai_forensics").insert(safe_data).execute()
        )
    except Exception as e:
        logger.debug("[FORENSICS] persist greška (nije kritično): %s", e)


# ─── Brza verzija (sync, fire-and-forget) ────────────────────────────────────

def log_ai_call_sync(
    user_id: str,
    endpoint: str,
    model: str,
    prompt_hash: str,
    documents_count: int,
    latency_ms: int,
    response_hash: str,
    injection_risk: float = 0.0,
    tokens_prompt: Optional[int] = None,
    tokens_completion: Optional[int] = None,
) -> None:
    """
    Sinhrona verzija za slučajeve kada nije dostupan async kontekst.
    Pokreće persist u background thread-u.
    """
    import threading
    data = {
        "user_id":        user_id,
        "endpoint":       endpoint,
        "model":          model,
        "prompt_hash":    prompt_hash,
        "documents_count": documents_count,
        "document_hashes": [],
        "injection_risk_score": injection_risk,
        "injection_flags": [],
        "started_at":     _utcnow(),
        "finished_at":    _utcnow(),
        "latency_ms":     latency_ms,
        "response_hash":  response_hash,
        "tokens_prompt":  tokens_prompt,
        "tokens_completion": tokens_completion,
        "prompt_version": os.getenv("PROMPT_VERSION", "1.0"),
    }
    threading.Thread(target=_persist_sync, args=(data,), daemon=True).start()


def _persist_sync(data: dict) -> None:
    try:
        from api import _get_supa
        supa = _get_supa()
        safe = {k: (json.dumps(v) if isinstance(v, list) else v) for k, v in data.items()}
        supa.table("ai_forensics").insert(safe).execute()
    except Exception as e:
        logger.debug("[FORENSICS] sync persist greška: %s", e)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

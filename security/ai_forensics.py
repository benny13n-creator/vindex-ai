# -*- coding: utf-8 -*-
"""
Vindex AI — security/ai_forensics.py

AI Forensics — beleži svaki AI poziv sa svim relevantnim metapodacima.

Svrha: integritet-verifikacija svakog AI poziva čak i godinama kasnije --
NIJE rekonstrukcija sadržaja (vidi niže). Odgovara na: Ko je zatražio
analizu? Koji dokumenti su korišćeni? Koja verzija modela je odgovorila?

VAŽNO (ispravljeno Program Tau, Master Sprint 001, 2026-08-06 -- Agent 4
Security Review je pronašao da je prethodna formulacija ovog docstring-a
("potpuna rekonstrukcija") netačna): ova tabela čuva SAMO SHA-256 heševe
prompta/odgovora (`system_prompt_hash`, `user_prompt_hash`, `output_hash`),
nikad sirov tekst. To znači da se može DOKAZATI da je poziv datog sadržaja
zaista izvršen (re-hash + poređenje), ali se sirov prompt/odgovor NE MOŽE
rekonstruisati unazad iz heša -- ako je ikad potrebna stvarna rekonstrukcija
teksta (npr. spor sa klijentom, upit advokatske komore), ovaj mehanizam to
ne pruža. Namerna dizajn odluka (bez druge kopije osetljivog sadržaja
predmeta u forenzičkoj tabeli), ne propust -- ali docstring ranije nije to
jasno govorio.

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


# ─── Mission Atlas (2026-08-03) — canonical-wrapper provenance sink ──────────
# ForensicsRecord/log_ai_call_sync above were designed for explicit, per-call-
# site instrumentation and were never actually wired into any of the ~130 AI
# call sites (confirmed: zero imports of this module anywhere else in the
# repo before this mission) — the table and hashing design were correct, they
# were simply never connected. log_provenance_from_wrapper is the sink the
# canonical wrapper (shared/ai_client.py's already-patched Completions.create/
# AsyncCompletions.create/Embeddings.create) calls automatically on every AI
# call, structurally, the same way SEC-003's prompt guard already does — no
# per-call-site wiring required for the fields a wrapper CAN see (model,
# tokens, latency, hashes). Case/user context (fields a global SDK-level
# patch cannot see on its own) comes from shared/ai_provenance.py's context
# vars, read here as `ctx`.
#
# Column set here is a superset of the original 043 migration's ai_forensics
# table — see migrations/<pending>_ai_provenance_extension.sql (drafted, NOT
# applied; founder runs migrations himself per this project's standing rule).
# Extra columns are additive (ADD COLUMN IF NOT EXISTS), so this function is
# safe to call before that migration runs too: unknown-column inserts would
# fail loudly against a real Postgres schema, so _persist_provenance only
# includes a column if the caller actually supplied a value for it, keeping
# pre-migration environments from erroring on every AI call.

async def log_provenance_from_wrapper(
    *,
    module_name: str,
    operation_name: Optional[str] = None,
    model_provider: str,
    model_name: str,
    model_version: Optional[str] = None,
    system_prompt_hash: Optional[str] = None,
    user_prompt_hash: Optional[str] = None,
    prompt_version: Optional[str] = None,
    token_usage_input: Optional[int] = None,
    token_usage_output: Optional[int] = None,
    latency_ms: Optional[int] = None,
    output_hash: Optional[str] = None,
    confidence_score: Optional[float] = None,
    hallucination_check_result: Optional[str] = None,
    correlation_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    predmet_id: Optional[str] = None,
    document_id: Optional[str] = None,
    knowledge_sources: Optional[list] = None,
    retrieved_context_ids: Optional[list] = None,
    retrieval_query: Optional[str] = None,
    audit_reference: Optional[str] = None,
    status: str = "success",
    error_message: Optional[str] = None,
) -> None:
    """Fail-soft, fire-and-forget insert — a provenance-logging bug must
    never break a real AI call, same contract as every other function here.

    Mission Ledger (2026-08-03): audit_reference defaults to correlation_id
    itself when the caller doesn't supply a more specific value — the shared
    correlation_id IS the join key to the matching audit_immutable row (now
    that shared/audit_immutable.py::log_action also stores it), so this
    column documents that fact for a reader who doesn't already know to
    look for correlation_id specifically, rather than pointing at a
    would-be audit_immutable.id that may not exist yet at write time (audit
    rows for the same logical action are often written slightly after this
    one, from router code that runs after the AI call returns).

    correlation_id itself also auto-fills from shared/ai_provenance.py's
    current context if the caller doesn't supply one — shared/ai_client.py's
    wrapper already does this before calling here, but defaulting it here
    too means any OTHER future caller of this function gets the same
    continuity guarantee for free, not just the canonical wrapper."""
    if correlation_id is None:
        try:
            from shared.ai_provenance import current_correlation_id
            correlation_id = current_correlation_id()
        except Exception:
            correlation_id = None
    if audit_reference is None and correlation_id:
        audit_reference = correlation_id
    record = {
        "user_id":                    user_id,
        "endpoint":                   module_name,          # legacy column, kept populated for BEFORE-migration compatibility
        "model":                      model_name,            # legacy column, same reason
        "prompt_hash":                user_prompt_hash,       # legacy column, closest equivalent
        "started_at":                 _utcnow(),
        "latency_ms":                 latency_ms,
        "response_hash":              output_hash,
        "tokens_prompt":               token_usage_input,
        "tokens_completion":           token_usage_output,
        "prompt_version":              prompt_version or "1.0",
        "module_name":                module_name,
        "operation_name":              operation_name,
        "model_provider":              model_provider,
        "model_version":               model_version,
        "system_prompt_hash":           system_prompt_hash,
        "user_prompt_hash":             user_prompt_hash,
        "confidence_score":            confidence_score,
        "hallucination_check_result":  hallucination_check_result,
        "correlation_id":              correlation_id,
        "parent_event_id":             parent_event_id,
        "tenant_id":                   tenant_id,
        "predmet_id":                  predmet_id,
        "document_id":                 document_id,
        "knowledge_sources":           knowledge_sources or [],
        "retrieved_context_ids":       retrieved_context_ids or [],
        "retrieval_query":             retrieval_query,
        "audit_reference":             audit_reference,
        "status":                     status,
        "error_message":               error_message,
    }
    # Legacy-only subset — columns that already exist in the 043 migration,
    # so this still writes REAL rows before the founder runs the extension
    # migration (same "try wide, fall back to narrow" idiom already used
    # elsewhere in this repo for schema-pending columns, e.g.
    # api.py's predmet_dokumenti tekst_sadrzaj insert).
    _legacy_keys = {
        "user_id", "endpoint", "model", "prompt_hash", "started_at",
        "latency_ms", "response_hash", "tokens_prompt", "tokens_completion",
        "prompt_version",
    }
    legacy_record = {k: v for k, v in record.items() if k in _legacy_keys}

    try:
        from api import _get_supa
        from shared.audit_immutable import _is_missing_column_error
        supa = _get_supa()
        safe = {k: (json.dumps(v) if isinstance(v, list) else v) for k, v in record.items() if v is not None}
        try:
            await asyncio.to_thread(lambda: supa.table("ai_forensics").insert(safe).execute())
        except Exception as _wide_exc:
            # Project Phoenix (2026-08-03), Finding P-1: NARROW fallback --
            # only retry without the extended-schema columns when the error
            # actually looks like "column doesn't exist yet" (pre-migration
            # 089), not for a genuinely unrelated failure (e.g. connection
            # reset), which would just waste a second doomed attempt.
            if not _is_missing_column_error(_wide_exc):
                raise
            safe_legacy = {k: v for k, v in safe.items() if k in legacy_record}
            await asyncio.to_thread(lambda: supa.table("ai_forensics").insert(safe_legacy).execute())
    except Exception as e:
        logger.debug("[FORENSICS] provenance persist greška (nije kritično): %s", e)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

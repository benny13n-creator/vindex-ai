# -*- coding: utf-8 -*-
"""
Vindex AI — shared/ai_provenance.py

Mission Atlas (2026-08-03) — request/case-scoped context propagation for AI
provenance capture. Does NOT persist anything itself (see
security/ai_forensics.py::log_provenance_from_wrapper for that) — this module
only answers "what context is the current AI call happening in," so the
canonical wrapper (shared/ai_client.py) can attach user/tenant/case/document
identity to a call it intercepts structurally, without every one of the ~130
call sites needing to pass that context explicitly through kwargs.

Two layers, set at two different points in a request's lifecycle:

1. Request context (user_id, tenant_id) — set ONCE per request, at the
   existing auth choke points (shared/deps.py::get_current_user,
   api.py::_require_auth). Every authenticated endpoint already calls one of
   these two functions — this is a "connect, don't build" hook, not a new
   auth mechanism. Uses `.set()` with no restore: each FastAPI request runs
   in its own asyncio Task, and contextvars are Task-isolated, so there is no
   cross-request leakage risk from skipping the token/reset dance here.

2. Case context (predmet_id, document_id, module_name, operation_name,
   knowledge_sources, retrieval_query, correlation_id, parent_event_id) — set
   temporarily around a specific AI operation via `case_context(...)`, a real
   context manager that restores the previous value on exit (a single
   request can make multiple AI calls in different case contexts, e.g.
   Cockpit's several distinct analyses).
"""
from __future__ import annotations

import contextvars
import hashlib
import uuid
from contextlib import contextmanager
from typing import Any, Iterator, Optional

_request_ctx: contextvars.ContextVar[dict] = contextvars.ContextVar("ai_request_ctx", default={})
_case_ctx: contextvars.ContextVar[dict] = contextvars.ContextVar("ai_case_ctx", default={})


def set_request_context(user_id: Optional[str] = None, tenant_id: Optional[str] = None) -> None:
    """Called once per request from the two auth choke points. No restore —
    see module docstring for why that's safe here."""
    _request_ctx.set({"user_id": user_id, "tenant_id": tenant_id})


@contextmanager
def case_context(
    predmet_id: Optional[str] = None,
    document_id: Optional[str] = None,
    module_name: Optional[str] = None,
    operation_name: Optional[str] = None,
    knowledge_sources: Optional[list] = None,
    retrieved_context_ids: Optional[list] = None,
    retrieval_query: Optional[str] = None,
    parent_event_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Iterator[str]:
    """Wrap a specific AI operation to attach case-level provenance context.
    Yields the correlation_id in use (generated fresh if not supplied), so
    the caller can also stamp it onto a durable event/audit row for
    cross-referencing (Phase 3 Source Traceability)."""
    cid = correlation_id or new_correlation_id()
    previous = _case_ctx.get()
    merged = {
        **previous,
        "predmet_id": predmet_id,
        "document_id": document_id,
        "module_name": module_name,
        "operation_name": operation_name,
        "knowledge_sources": knowledge_sources or [],
        "retrieved_context_ids": retrieved_context_ids or [],
        "retrieval_query": retrieval_query,
        "parent_event_id": parent_event_id,
        "correlation_id": cid,
    }
    token = _case_ctx.set(merged)
    try:
        yield cid
    finally:
        _case_ctx.reset(token)


def current_context() -> dict[str, Any]:
    """Merged view the canonical wrapper reads from — request context first,
    case context overlays it (case context is the more specific scope)."""
    return {**_request_ctx.get(), **_case_ctx.get()}


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def sha256_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

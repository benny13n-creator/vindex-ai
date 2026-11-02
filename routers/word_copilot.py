"""Word Add-in selected-text analysis endpoint.

Only the explicit Word selection is accepted. Optional matter context is authorized
server-side through the canonical Vindex matter ACL.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from routers.word_auth import (
    WordSession,
    _word_server_client_key,
    require_word_session,
)
from shared.deps import _get_supa
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService

logger = logging.getLogger("vindex.word_copilot")
router = APIRouter(prefix="/api/word", tags=["word-copilot"])

_MAX_SELECTED_TEXT_CHARS = 4000


class WordAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    text: str = Field(min_length=1, max_length=_MAX_SELECTED_TEXT_CHARS)
    predmet_id: UUID | None = None


class WordRewriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    text: str = Field(min_length=1, max_length=_MAX_SELECTED_TEXT_CHARS)


async def require_word_analysis_user(
    request: Request,
    session: WordSession = Depends(require_word_session),
) -> dict[str, Any]:
    """Resolve server-controlled identity and apply the existing feature policy."""
    def _load_user():
        return _get_supa().auth.admin.get_user_by_id(session.user_id)

    try:
        response = await asyncio.wait_for(asyncio.to_thread(_load_user), timeout=4)
    except Exception:
        logger.warning("[WORD_ANALYSIS] identity_lookup_unavailable")
        raise HTTPException(status_code=503, detail="Prijava trenutno nije dostupna.")

    auth_user = getattr(response, "user", None) if response is not None else None
    if getattr(auth_user, "id", None) != session.user_id:
        raise HTTPException(status_code=401, detail="Word sesija nije važeća.")

    email = getattr(auth_user, "email", None)
    user = {"user_id": session.user_id, "email": email if isinstance(email, str) else ""}

    try:
        from shared.ai_provenance import current_correlation_id, set_request_context

        set_request_context(
            user_id=session.user_id,
            correlation_id=current_correlation_id(),
        )
        authorized = await PermissionService.require("copilot_ambient")(user)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[WORD_ANALYSIS] feature_authorization_unavailable error=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Analiza teksta trenutno nije dostupna.")

    if not isinstance(authorized, dict) or authorized.get("user_id") != session.user_id:
        raise HTTPException(status_code=401, detail="Word sesija nije važeća.")
    return authorized


def _load_word_matter_rows(user_id: str) -> list[dict[str, Any]]:
    """List minimal matter labels from the same ACL used by get_predmet and RAG."""
    from shared.rag_acl import dozvoljeni_predmeti

    supa = _get_supa()
    allowed = dozvoljeni_predmeti(supa, user_id)
    if not allowed:
        return []
    allowed_ids = {str(item) for item in allowed}
    result = (
        supa.table("predmeti")
        .select("id,naziv,tip,status")
        .in_("id", list(allowed_ids))
        .order("naziv")
        .execute()
    )
    return [
        {
            "id": str(row["id"]),
            "naziv": str(row.get("naziv") or "Predmet"),
            "tip": row.get("tip") if isinstance(row.get("tip"), str) else None,
            "status": row.get("status") if isinstance(row.get("status"), str) else None,
        }
        for row in (result.data or [])
        if row.get("id") and str(row["id"]) in allowed_ids
    ]


async def _require_word_matter_access(user_id: str, predmet_id: UUID) -> str:
    """Require an owner or active canonical delegate grant; IDs never grant rights."""
    def _load_allowed_ids():
        from shared.rag_acl import dozvoljeni_predmeti

        return dozvoljeni_predmeti(_get_supa(), user_id)

    try:
        allowed = await asyncio.wait_for(asyncio.to_thread(_load_allowed_ids), timeout=5)
    except Exception as exc:
        logger.warning("[WORD_ANALYSIS] matter_authorization_unavailable error=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Predmet nije mogao biti proveren.")

    if not isinstance(allowed, (list, tuple, set)):
        logger.warning("[WORD_ANALYSIS] matter_authorization_invalid_result")
        raise HTTPException(status_code=503, detail="Predmet nije mogao biti proveren.")

    requested = str(predmet_id)
    if requested not in {str(item) for item in allowed}:
        raise HTTPException(status_code=404, detail="Predmet nije dostupan.")
    return requested


@router.get("/matters")
@limiter.limit("30/minute", key_func=_word_server_client_key)
async def list_word_matters(
    request: Request,
    user: dict = Depends(require_word_analysis_user),
):
    try:
        rows = await asyncio.wait_for(
            asyncio.to_thread(_load_word_matter_rows, user["user_id"]),
            timeout=5,
        )
    except Exception as exc:
        logger.warning("[WORD_ANALYSIS] matter_list_unavailable error=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Predmeti trenutno nisu dostupni.")
    return {"predmeti": rows}

def _require_word_ai_budget_operation(request: Request, user_id: str) -> None:
    """Require PR #66's provider gate and per-request operation before retrieval."""
    try:
        from shared import ai_budget
    except Exception:
        raise HTTPException(status_code=503, detail="AI analiza je privremeno nedostupna.")

    required = ("rezim", "tekuca_operacija", "pre_poziva", "apre_poziva", "posle_poziva")
    if any(not callable(getattr(ai_budget, name, None)) for name in required):
        raise HTTPException(status_code=503, detail="AI analiza je privremeno nedostupna.")

    try:
        budget_mode = ai_budget.rezim()
    except Exception:
        budget_mode = None
    if budget_mode != "enforce":
        raise HTTPException(status_code=503, detail="AI analiza je privremeno nedostupna.")

    budget_middleware_present = any(
        getattr(getattr(item, "cls", None), "__module__", "") == "shared.ai_budget"
        and getattr(getattr(item, "cls", None), "__name__", "") == "AIBudzetMiddleware"
        for item in getattr(request.app, "user_middleware", ())
    )
    if not budget_middleware_present:
        raise HTTPException(status_code=503, detail="AI analiza je privremeno nedostupna.")

    try:
        operation = ai_budget.tekuca_operacija()
        if (
            operation is None
            or getattr(operation, "user_id", None) != user_id
            or getattr(operation, "feature", None) != "copilot_ambient"
            or getattr(operation, "zatvorena", True)
        ):
            raise HTTPException(status_code=503, detail="AI analiza je privremeno nedostupna.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="AI analiza je privremeno nedostupna.")

@router.post("/analyze")
@limiter.limit("30/minute", key_func=_word_server_client_key)
async def analyze_word_selection(
    req: WordAnalyzeRequest,
    request: Request,
    user: dict = Depends(require_word_analysis_user),
):
    selected_text = req.text
    if not selected_text.strip():
        raise HTTPException(status_code=422, detail="Izaberite tekst za analizu.")

    user_id = user["user_id"]
    predmet_id = None
    if req.predmet_id is not None:
        predmet_id = await _require_word_matter_access(user_id, req.predmet_id)
    _require_word_ai_budget_operation(request, user_id)

    try:
        from services.ambient_analyzer import (
            SelectedMatterRetrievalUnavailable,
            SelectedTextProviderUnavailable,
            analyze_selected_text,
        )

        if predmet_id:
            from shared.ai_provenance import case_context

            with case_context(
                predmet_id=predmet_id,
                module_name="word_addin",
                operation_name="selected_text_analysis",
                knowledge_sources=["statutes", "case_law", "matter_documents"],
            ):
                result = await analyze_selected_text(
                    selected_text, user_id=user_id, predmet_id=predmet_id
                )
        else:
            result = await analyze_selected_text(selected_text, user_id=user_id)
    except HTTPException:
        raise
    except Exception as exc:
        try:
            from shared.ai_budget import AIBudzetOdbijen
        except ImportError:
            AIBudzetOdbijen = ()  # type: ignore[assignment]
        if isinstance(exc, AIBudzetOdbijen):
            raise HTTPException(status_code=exc.status, detail=exc.detalj)
        if isinstance(exc, SelectedMatterRetrievalUnavailable):
            raise HTTPException(status_code=503, detail="Izabrani predmet trenutno nije dostupan za analizu.")
        if isinstance(exc, SelectedTextProviderUnavailable):
            raise HTTPException(
                status_code=503,
                detail="Vindex nije uspeo da završi analizu. Pokušajte ponovo.",
            )
        logger.warning("[WORD_ANALYSIS] analysis_failed error=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Analiza teksta trenutno nije dostupna.")

    try:
        await UsageService.consume(user_id, user.get("email", ""), "copilot_ambient")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[WORD_ANALYSIS] usage_settlement_unavailable error=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Analiza nije mogla biti potvrđena.")

    return result


@router.post("/rewrite")
@limiter.limit("30/minute", key_func=_word_server_client_key)
async def propose_word_rewrite(
    req: WordRewriteRequest,
    request: Request,
    user: dict = Depends(require_word_analysis_user),
):
    """Generate a review-only text proposal; this endpoint never writes a document or matter."""
    selected_text = req.text
    if not selected_text.strip():
        raise HTTPException(status_code=422, detail="Izaberite tekst za preformulisanje.")

    user_id = user["user_id"]
    _require_word_ai_budget_operation(request, user_id)
    try:
        from services.ambient_analyzer import (
            SelectedTextProviderUnavailable,
            generate_word_rewrite_proposal,
        )

        proposal = await generate_word_rewrite_proposal(selected_text, user_id=user_id)
    except HTTPException:
        raise
    except Exception as exc:
        try:
            from shared.ai_budget import AIBudzetOdbijen
        except ImportError:
            AIBudzetOdbijen = ()  # type: ignore[assignment]
        if isinstance(exc, AIBudzetOdbijen):
            raise HTTPException(status_code=exc.status, detail=exc.detalj)
        if isinstance(exc, SelectedTextProviderUnavailable):
            raise HTTPException(
                status_code=503,
                detail="Vindex nije uspeo da pripremi predlog. Pokušajte ponovo.",
            )
        logger.warning("[WORD_REWRITE] proposal_failed error=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Predlog trenutno nije dostupan.")

    try:
        await UsageService.consume(user_id, user.get("email", ""), "copilot_ambient")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[WORD_REWRITE] usage_settlement_unavailable error=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Predlog nije mogao biti potvrđen.")

    return {
        "original_text": selected_text,
        "proposal_text": proposal,
        "ai_generated": True,
        "document_changed": False,
    }

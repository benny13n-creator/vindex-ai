import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from shared.deps import _get_supa, get_current_user

router = APIRouter(prefix="/api/plan", tags=["plan"])

# Dok Stripe nije live, enforce blokira samo ako je ENFORCE_LIMITS=True.
# Tracking se uvek radi. Ovo sprečava da korisnici budu blokirani pre nego
# što mogu da plate — dupli billing bug + UX problem.
import os as _os
_ENFORCE_LIMITS = _os.getenv("ENFORCE_LIMITS", "false").lower() == "true"

PLAN_LIMITS = {
    "free":       {"ai_queries": 15,   "doc_analyses": 2,    "strategies": 0},
    "advokat":    {"ai_queries": 100,  "doc_analyses": 10,   "strategies": 2},
    "pro":        {"ai_queries": 300,  "doc_analyses": None, "strategies": 5},
    "firma":      {"ai_queries": 200,  "doc_analyses": 20,   "strategies": 10},
    "enterprise": {"ai_queries": None, "doc_analyses": None, "strategies": None},
}

OVERAGE_PRICE = {
    "ai_queries":   0.15,
    "doc_analyses": 0.50,
    "strategies":   1.50,
}


def _year_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def _get_plan(user_id: str) -> dict:
    sb = _get_supa()
    res = await asyncio.to_thread(
        lambda: sb.table("korisnik_plan").select("*").eq("user_id", user_id).maybe_single().execute()
    )
    if res.data:
        return res.data
    return {"plan_type": "free", "seats": 1, "billing_cycle": "monthly"}


async def _get_usage(user_id: str, year_month: str) -> dict:
    sb = _get_supa()
    res = await asyncio.to_thread(
        lambda: sb.table("korisnik_usage")
            .select("*")
            .eq("user_id", user_id)
            .eq("year_month", year_month)
            .maybe_single()
            .execute()
    )
    if res.data:
        return res.data
    return {
        "ai_queries": 0, "doc_analyses": 0, "strategies": 0,
        "overage_queries": 0, "overage_docs": 0, "overage_strategies": 0,
    }


@router.get("/status")
async def plan_status(user=Depends(get_current_user)):
    user_id = user["user_id"]  # BUG FIX: bio user["id"]
    ym = _year_month()
    plan = await _get_plan(user_id)
    usage = await _get_usage(user_id, ym)
    pt = plan["plan_type"]
    limits = PLAN_LIMITS.get(pt, PLAN_LIMITS["free"])

    return {
        "plan": pt,
        "seats": plan.get("seats", 1),
        "billing_cycle": plan.get("billing_cycle", "monthly"),
        "year_month": ym,
        "enforce_active": _ENFORCE_LIMITS,
        "usage": {
            "ai_queries":   {"used": usage["ai_queries"],   "limit": limits["ai_queries"]},
            "doc_analyses": {"used": usage["doc_analyses"], "limit": limits["doc_analyses"]},
            "strategies":   {"used": usage["strategies"],   "limit": limits["strategies"]},
        },
        "overage": {
            "queries":    usage["overage_queries"],
            "docs":       usage["overage_docs"],
            "strategies": usage["overage_strategies"],
        },
        "overage_price_eur": OVERAGE_PRICE,
    }


async def enforce_and_increment(user_id: str, resource: str):
    """
    Prati AI upotrebu i (kada je ENFORCE_LIMITS=true) blokira na limitu.

    ENFORCE_LIMITS=false (default dok Stripe nije live):
      - Tracking uvek radi (za analytics)
      - Blokiranje ne radi (korisnici nisu zarobljeni bez plaćanja)
      - Stari kredit sistem ostaje jedini gatekeeper

    ENFORCE_LIMITS=true (posle Stripe integracije):
      - Blokira free/advokat/pro na limitu
      - Firma beleži overage umesto blokiranja
    """
    try:
        await _enforce_and_increment_inner(user_id, resource)
    except HTTPException:
        raise  # limit exceeded — namerno, ne swallowati
    except Exception as exc:
        # DB tabele (korisnik_plan/korisnik_usage) možda nisu kreirane — ne blokira funkcionalnost
        import logging as _lg
        _lg.getLogger("vindex.plans").warning(
            "[ENFORCE] DB tracking greška (non-fatal) uid=%.8s: %s", user_id, exc
        )


async def _enforce_and_increment_inner(user_id: str, resource: str):
    """Unutrašnja implementacija — baca izuzetak ako DB nije dostupna."""
    ym = _year_month()
    plan = await _get_plan(user_id)
    usage = await _get_usage(user_id, ym)
    pt = plan["plan_type"]
    limits = PLAN_LIMITS.get(pt, PLAN_LIMITS["free"])

    field_map = {
        "ai_queries":   ("ai_queries",   "overage_queries"),
        "doc_analyses": ("doc_analyses", "overage_docs"),
        "strategies":   ("strategies",   "overage_strategies"),
    }
    if resource not in field_map:
        return

    usage_field, overage_field = field_map[resource]
    used = usage[usage_field]
    limit = limits[resource]

    sb = _get_supa()

    if limit is None:
        # Neograničeno (pro doc_analyses) — samo inkrementiraj
        await asyncio.to_thread(
            lambda: sb.table("korisnik_usage").upsert(
                {"user_id": user_id, "year_month": ym, usage_field: used + 1},
                on_conflict="user_id,year_month",
            ).execute()
        )
        return

    if used < limit or not _ENFORCE_LIMITS:
        # Unutar limita, ili enforce nije aktivan — tracking
        await asyncio.to_thread(
            lambda: sb.table("korisnik_usage").upsert(
                {"user_id": user_id, "year_month": ym, usage_field: used + 1},
                on_conflict="user_id,year_month",
            ).execute()
        )
    elif pt == "firma":
        # Firma plan: overage naplata umesto blokiranja
        cur_overage = usage[overage_field]
        await asyncio.to_thread(
            lambda: sb.table("korisnik_usage").upsert(
                {"user_id": user_id, "year_month": ym, overage_field: cur_overage + 1},
                on_conflict="user_id,year_month",
            ).execute()
        )
    else:
        price = OVERAGE_PRICE[resource]
        raise HTTPException(
            status_code=402,
            detail={
                "error": "limit_exceeded",
                "resource": resource,
                "used": used,
                "limit": limit,
                "upgrade_hint": f"Nadogradite plan (€{price}/jedinica za Firma overage).",
            },
        )

import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from shared.deps import _get_supa, get_current_user

router = APIRouter(prefix="/api/plan", tags=["plan"])

import os as _os
_ENFORCE_LIMITS = _os.getenv("ENFORCE_LIMITS", "false").lower() == "true"

# ── Cene (EUR) ────────────────────────────────────────────────────────────────
PLAN_PRICES = {
    "free":       {"monthly": 0,    "annual": 0},
    "starter":    {"monthly": 29,   "annual": 23.20},   # 20% popust
    "pro":        {"monthly": 79,   "annual": 63.20},
    "enterprise": {"monthly": 130,  "annual": 104.00},
}

# ── Mesečni limiti (None = neograničeno) ──────────────────────────────────────
PLAN_LIMITS = {
    "free": {
        "ai_queries":       5,
        "doc_analyses":     1,
        "nacrti":           0,
        "court_predictor":  0,
        "battle_reports":   0,
        "hearing_prep":     0,
        "commander":        0,
        "simulator":        0,
        "digital_twin":     0,
        "evidence_graph":   0,
        "memory_unosi":     0,
        "predmeti_max":     3,
        "klijenti_max":     5,
        "seats":            1,
        # Feature flags
        "morning_briefing": False,
        "whatsapp_viber":   False,
        "google_calendar":  False,
        "webhooks":         False,
        "enterprise_tim":   False,
        "vindex_memory":    False,
        "regional":         False,
    },
    "starter": {
        "ai_queries":       100,
        "doc_analyses":     20,
        "nacrti":           15,
        "court_predictor":  5,
        "battle_reports":   2,
        "hearing_prep":     5,
        "commander":        10,
        "simulator":        3,
        "digital_twin":     2,
        "evidence_graph":   2,
        "memory_unosi":     100,
        "predmeti_max":     50,
        "klijenti_max":     None,
        "seats":            1,
        "morning_briefing": True,
        "whatsapp_viber":   False,
        "google_calendar":  False,
        "webhooks":         False,
        "enterprise_tim":   False,
        "vindex_memory":    True,
        "regional":         True,
    },
    "pro": {
        "ai_queries":       500,
        "doc_analyses":     75,
        "nacrti":           60,
        "court_predictor":  20,
        "battle_reports":   8,
        "hearing_prep":     None,
        "commander":        None,
        "simulator":        None,
        "digital_twin":     10,
        "evidence_graph":   10,
        "memory_unosi":     1000,
        "predmeti_max":     None,
        "klijenti_max":     None,
        "seats":            2,
        "morning_briefing": True,
        "whatsapp_viber":   True,
        "google_calendar":  True,
        "webhooks":         False,
        "enterprise_tim":   False,
        "vindex_memory":    True,
        "regional":         True,
    },
    "enterprise": {
        "ai_queries":       None,
        "doc_analyses":     None,
        "nacrti":           None,
        "court_predictor":  None,
        "battle_reports":   None,
        "hearing_prep":     None,
        "commander":        None,
        "simulator":        None,
        "digital_twin":     None,
        "evidence_graph":   None,
        "memory_unosi":     None,
        "predmeti_max":     None,
        "klijenti_max":     None,
        "seats":            5,
        "morning_briefing": True,
        "whatsapp_viber":   True,
        "google_calendar":  True,
        "webhooks":         True,
        "enterprise_tim":   True,
        "vindex_memory":    True,
        "regional":         True,
    },
    # Backward compatibility — stari nazivi planova
    "advokat":    None,  # -> starter
    "firma":      None,  # -> enterprise
}

# Backward compat alias-i
_PLAN_ALIAS = {"advokat": "starter", "firma": "enterprise"}


def _year_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _resolve_plan(plan_type: str) -> str:
    """Resolvuje stare nazive planova u nove."""
    return _PLAN_ALIAS.get(plan_type, plan_type)


def _get_limits(plan_type: str) -> dict:
    resolved = _resolve_plan(plan_type)
    limits = PLAN_LIMITS.get(resolved)
    if limits is None:
        return PLAN_LIMITS["free"]
    return limits


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
    defaults = {
        "ai_queries": 0, "doc_analyses": 0, "nacrti": 0,
        "court_predictor": 0, "battle_reports": 0, "hearing_prep": 0,
        "commander": 0, "simulator": 0, "digital_twin": 0, "evidence_graph": 0,
        # backward compat
        "strategies": 0,
        "overage_queries": 0, "overage_docs": 0, "overage_strategies": 0,
    }
    if res.data:
        return {**defaults, **res.data}
    return defaults


@router.get("/status")
async def plan_status(user=Depends(get_current_user)):
    user_id = user["user_id"]
    ym = _year_month()
    plan = await _get_plan(user_id)
    usage = await _get_usage(user_id, ym)
    pt = _resolve_plan(plan["plan_type"])
    limits = _get_limits(pt)
    prices = PLAN_PRICES.get(pt, PLAN_PRICES["free"])

    def _usage_item(resource):
        used = usage.get(resource, 0)
        limit = limits.get(resource)
        pct = None if limit is None else round(used / limit * 100) if limit > 0 else 100
        return {"used": used, "limit": limit, "pct": pct}

    return {
        "plan":           pt,
        "plan_display":   _plan_display_name(pt),
        "seats":          plan.get("seats", 1),
        "billing_cycle":  plan.get("billing_cycle", "monthly"),
        "year_month":     ym,
        "enforce_active": _ENFORCE_LIMITS,
        "prices":         prices,
        "features": {
            "morning_briefing": limits.get("morning_briefing", False),
            "whatsapp_viber":   limits.get("whatsapp_viber", False),
            "google_calendar":  limits.get("google_calendar", False),
            "webhooks":         limits.get("webhooks", False),
            "enterprise_tim":   limits.get("enterprise_tim", False),
            "vindex_memory":    limits.get("vindex_memory", False),
            "regional":         limits.get("regional", False),
        },
        "usage": {
            "ai_queries":      _usage_item("ai_queries"),
            "doc_analyses":    _usage_item("doc_analyses"),
            "nacrti":          _usage_item("nacrti"),
            "court_predictor": _usage_item("court_predictor"),
            "battle_reports":  _usage_item("battle_reports"),
            "hearing_prep":    _usage_item("hearing_prep"),
            "commander":       _usage_item("commander"),
            "simulator":       _usage_item("simulator"),
            "digital_twin":    _usage_item("digital_twin"),
            "evidence_graph":  _usage_item("evidence_graph"),
        },
        "limits": {
            "predmeti_max":  limits.get("predmeti_max"),
            "klijenti_max":  limits.get("klijenti_max"),
            "memory_unosi":  limits.get("memory_unosi"),
            "seats":         limits.get("seats", 1),
        },
    }


@router.get("/info")
async def plan_info():
    """Javni endpoint — info o svim planovima i cenama."""
    return {
        "planovi": [
            {
                "id": "free",
                "naziv": "Besplatno",
                "cena_mesecno": 0,
                "cena_godisnje": 0,
                "opis": "Za upoznavanje platforme",
            },
            {
                "id": "starter",
                "naziv": "Starter",
                "cena_mesecno": 29,
                "cena_godisnje_mesecno": 23.20,
                "cena_godisnje_ukupno": 278.40,
                "popust_godisnje_pct": 20,
                "opis": "Za solo advokata",
            },
            {
                "id": "pro",
                "naziv": "Pro",
                "cena_mesecno": 79,
                "cena_godisnje_mesecno": 63.20,
                "cena_godisnje_ukupno": 758.40,
                "popust_godisnje_pct": 20,
                "opis": "Za aktivnu kancelariju",
                "preporucen": True,
            },
            {
                "id": "enterprise",
                "naziv": "Enterprise",
                "cena_mesecno": 130,
                "cena_godisnje_mesecno": 104.00,
                "cena_godisnje_ukupno": 1248.00,
                "popust_godisnje_pct": 20,
                "opis": "Za tim advokata, neograničeno",
            },
        ]
    }


def _plan_display_name(pt: str) -> str:
    names = {
        "free": "Besplatno",
        "starter": "Starter",
        "pro": "Pro",
        "enterprise": "Enterprise",
    }
    return names.get(pt, pt.capitalize())


# Faza 72 čišćenje: enforce_and_increment/_enforce_and_increment_inner/
# check_feature_access su obrisane — nula pozivalaca bilo gde u kodu (potvrđeno
# grep-om pre brisanja). PermissionService/UsageService (migracije 063-066) su
# preuzeli SVU gejt/kredit logiku; ova tri su bila mrtav kod od Faze 70's
# wiring talasa (svi pozivi enforce_and_increment su uklonjeni iz pozivalaca
# tada, ali same funkcije nisu obrisane iz ovog fajla do sada).

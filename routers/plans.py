import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from shared.deps import _get_supa, _ensure_profile, get_current_user
from shared.feature_registry import get_all_policies
from shared.permissions import effective_tier
from shared.usage import UsageService

router = APIRouter(prefix="/api/plan", tags=["plan"])

# ── Cene (EUR) — javni /info endpoint, statična marketing lista, ne čita bazu.
# NAMERNO nedirano u Fazi 72.5 (potpuno uklanjanje korisnik_plan/korisnik_usage
# zavisnosti) — ova lista i dalje koristi stare nazive tarifa (free/starter/
# pro/enterprise), koje treba uskladiti sa profiles.subscription_type
# (basic/professional/enterprise) kad se radi Faza 73 (tier restructuring,
# pricing modal, javna prezentacija) — ne pre toga, eksplicitna founder-ova
# odluka da se te dve stvari ne mešaju u istoj promeni.
PLAN_PRICES = {
    "free":       {"monthly": 0,    "annual": 0},
    "starter":    {"monthly": 29,   "annual": 23.20},   # 20% popust
    "pro":        {"monthly": 79,   "annual": 63.20},
    "enterprise": {"monthly": 130,  "annual": 104.00},
}


def _year_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def _monthly_usage_by_feature(user_id: str) -> dict[str, dict]:
    """Agregira feature_usage (dnevni redovi, migracija 064) na mesečni nivo po
    feature_key — feature_usage.mesec je već upisan po redu upravo da ovo bude
    jedan .eq() upit umesto range-upita po datumu."""
    sb = _get_supa()
    ym = _year_month()

    def _fetch():
        return (
            sb.table("feature_usage")
            .select("feature_key, broj_koriscenja, krediti_potroseni")
            .eq("user_id", user_id)
            .eq("mesec", ym)
            .execute()
        )

    rows = (await asyncio.to_thread(_fetch)).data or []
    agg: dict[str, dict] = {}
    for r in rows:
        fk = r.get("feature_key")
        if not fk:
            continue
        bucket = agg.setdefault(fk, {"broj_koriscenja": 0, "krediti_potroseni": 0.0})
        bucket["broj_koriscenja"] += r.get("broj_koriscenja") or 0
        bucket["krediti_potroseni"] += float(r.get("krediti_potroseni") or 0)
    return agg


@router.get("/status")
async def plan_status(user=Depends(get_current_user)):
    """
    Stvarno stanje naloga — ISKLJUČIVO iz entitlement sistema (migracije
    063-066): profiles.subscription_type/addons/subscription_expires_at,
    feature_registry, feature_usage. Nikakvo čitanje iz korisnik_plan/
    korisnik_usage (obrisan sistem, Faza 72.5) — to je bila potpuno odvojena,
    nikad ažurirana tabela otkad je UsageService preuzeo kredit-tracking.
    """
    user_id = user["user_id"]
    email = user.get("email", "")

    profil = await asyncio.to_thread(_ensure_profile, user_id, email)
    pt = effective_tier(profil)
    ym = _year_month()

    credits_remaining, usage_agg, policies = await asyncio.gather(
        UsageService.balance(user_id, email),
        _monthly_usage_by_feature(user_id),
        get_all_policies(),
    )
    policy_by_key = {p["feature_key"]: p for p in policies}

    usage_this_month = []
    for fk, agg in sorted(usage_agg.items(), key=lambda kv: -kv[1]["krediti_potroseni"]):
        pol = policy_by_key.get(fk, {})
        usage_this_month.append({
            "feature_key":       fk,
            "naziv":             pol.get("naziv", fk),
            "broj_koriscenja":   agg["broj_koriscenja"],
            "krediti_potroseni": agg["krediti_potroseni"],
            "dnevni_limit":      pol.get("dnevni_limit"),
            "mesecni_limit":     pol.get("mesecni_limit"),
        })

    return {
        "plan":                     pt,
        "plan_display":             _plan_display_name(pt),
        "addons":                   profil.get("addons") or [],
        "subscription_expires_at":  profil.get("subscription_expires_at"),
        "subscription_seats_extra": profil.get("subscription_seats_extra", 0),
        "credits_remaining":        credits_remaining,
        "year_month":               ym,
        "usage_this_month":         usage_this_month,
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
        "basic": "Basic",
        "professional": "Professional",
        "enterprise": "Enterprise",
    }
    return names.get(pt, pt.capitalize())


# Faza 72 čišćenje: enforce_and_increment/_enforce_and_increment_inner/
# check_feature_access su obrisane — nula pozivalaca bilo gde u kodu (potvrđeno
# grep-om pre brisanja). PermissionService/UsageService (migracije 063-066) su
# preuzeli SVU gejt/kredit logiku; ova tri su bila mrtav kod od Faze 70's
# wiring talasa (svi pozivi enforce_and_increment su uklonjeni iz pozivalaca
# tada, ali same funkcije nisu obrisane iz ovog fajla do sada).

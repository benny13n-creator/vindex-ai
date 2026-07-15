import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from shared.business_groups import get_all_groups
from shared.deps import _get_supa, _ensure_profile, get_current_user
from shared.feature_registry import get_all_policies
from shared.permissions import effective_tier
from shared.tier_config import get_all_tiers, get_tier
from shared.usage import UsageService

router = APIRouter(prefix="/api/plan", tags=["plan"])


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

    credits_remaining, usage_agg, policies, tier_row = await asyncio.gather(
        UsageService.balance(user_id, email),
        _monthly_usage_by_feature(user_id),
        get_all_policies(),
        get_tier(pt),
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
        "plan_display":             tier_row.get("display_name", pt.capitalize()),
        "addons":                   profil.get("addons") or [],
        "subscription_expires_at":  profil.get("subscription_expires_at"),
        "subscription_seats_extra": profil.get("subscription_seats_extra", 0),
        "credits_remaining":        credits_remaining,
        "year_month":               ym,
        "usage_this_month":         usage_this_month,
    }


@router.get("/info")
async def plan_info():
    """Javni endpoint — info o svim tarifama i cenama. Isključivo iz tier_config
    (migracija 068) — nema statične/hardkodovane cene ovde, promena preko
    Admin Console-a je odmah vidljiva i na ovom javnom endpoint-u."""
    tiers = await get_all_tiers()
    return {
        "planovi": [
            {
                "id":                    t["tier_key"],
                "naziv":                 t.get("display_name", t["tier_key"].capitalize()),
                "cena_mesecno":          t.get("monthly_price_eur", 0),
                "cena_godisnje_mesecno": round(t["yearly_price_eur"] / 12, 2) if t.get("yearly_price_eur") else None,
                "cena_godisnje_ukupno":  t.get("yearly_price_eur"),
                "ukljucena_mesta":       t.get("included_seats", 1),
                "cena_dodatnog_mesta":   t.get("extra_seat_price_eur"),
                "opis":                  t.get("description"),
            }
            for t in tiers
            if t.get("is_active", True)
        ]
    }


@router.get("/pricing-matrix")
async def pricing_matrix():
    """Javni endpoint — Pricing Modal Nivo 1/Nivo 2 struktura. IZVEDENA u
    trenutku upita spajanjem feature_registry + business_groups (migracija
    071) — nikad zaseban 'pricing_matrix' red, jer bi to bio drugi izvor
    istine. Dodavanje nove funkcije = jedan INSERT u feature_registry sa
    postavljenim business_group_id, ovaj endpoint je automatski prikazuje,
    bez izmene koda.

    Samo feature_type IN (SUBSCRIPTION, ADDON), status=ACTIVE, visible=visible
    i sa dodeljenom business_group_id ulaze u matricu — FOUNDATION (uvek
    dostupno, nije razlog za kupovinu) i COMING_SOON (nije izgrađeno, nikad
    se ne reklamira) su namerno isključeni."""
    groups, policies = await asyncio.gather(get_all_groups(), get_all_policies())
    groups_by_id = {g["id"]: g for g in groups}

    by_group: dict[str, list[dict]] = {g["key"]: [] for g in groups if g.get("visible", True)}
    for p in policies:
        if p.get("feature_type") not in ("SUBSCRIPTION", "ADDON"):
            continue
        if p.get("status") != "ACTIVE" or p.get("visible") != "visible":
            continue
        group = groups_by_id.get(p.get("business_group_id"))
        if not group or group["key"] not in by_group:
            continue
        by_group[group["key"]].append({
            "feature_key":  p["feature_key"],
            "naziv":        p.get("naziv", p["feature_key"]),
            "opis":         p.get("opis"),
            "minimum_plan": p.get("minimum_plan"),
            "addon":        p.get("addon"),
            "krediti":      p.get("krediti"),
        })

    grupe = []
    for g in sorted((g for g in groups if g.get("visible", True)), key=lambda g: g.get("display_order", 0)):
        funkcije = sorted(by_group.get(g["key"], []), key=lambda f: f["naziv"])
        grupe.append({
            "key":            g["key"],
            "naziv":          g.get("display_name", g["key"]),
            "opis":           g.get("description"),
            "broj_funkcija":  len(funkcije),
            "funkcije":       funkcije,
        })

    return {"grupe": grupe}


# Faza 72 čišćenje: enforce_and_increment/_enforce_and_increment_inner/
# check_feature_access su obrisane — nula pozivalaca bilo gde u kodu (potvrđeno
# grep-om pre brisanja). PermissionService/UsageService (migracije 063-066) su
# preuzeli SVU gejt/kredit logiku; ova tri su bila mrtav kod od Faze 70's
# wiring talasa (svi pozivi enforce_and_increment su uklonjeni iz pozivalaca
# tada, ali same funkcije nisu obrisane iz ovog fajla do sada).

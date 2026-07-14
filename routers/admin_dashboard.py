# -*- coding: utf-8 -*-
"""
Vindex AI — routers/admin_dashboard.py

Admin Operations Dashboard (founder-only): Notification Center, Beta Users,
Security overview. System Health / APR Health / Portal Health / Platform
Analytics žive u routers/proof.py, routers/apr.py, routers/portal_monitoring.py,
i routers/analytics.py — ovaj router pokriva samo delove koji nisu imali
prirodni dom.

Endpoints (svi founder-only):
  GET  /api/admin/notification-log            — lista Viber/SMS/WhatsApp slanja
  POST /api/admin/notification-log/{id}/retry — ponovo pošalji neuspelo slanje
  GET  /api/admin/beta-users                  — spisak beta korisnika
  POST /api/admin/beta-users                  — dodaj beta korisnika (invite)
  GET  /api/admin/security-overview           — vidljivost postojećih bezbednosnih slojeva
  GET  /api/admin/pinecone-capacity            — vektora/procenjena veličina po namespace-u + nedeljni trend
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user, _is_founder
from shared.rate import limiter

logger = logging.getLogger("vindex.admin_dashboard")
router = APIRouter(prefix="/api/admin", tags=["admin-dashboard"])


def _require_founder(user: dict) -> None:
    if not _is_founder(user.get("email", "")):
        raise HTTPException(status_code=403, detail="Restricted.")


# ─── Notification Center ───────────────────────────────────────────────────────

@router.get("/notification-log")
@limiter.limit("30/minute")
async def notification_log_list(
    request: Request,
    user: dict = Depends(get_current_user),
    channel: Optional[str] = None,
    delivery_status: Optional[str] = None,
    user_id: Optional[str] = None,
    predmet_id: Optional[str] = None,
    limit: int = 50,
):
    """Lista poslednjih Viber/SMS/WhatsApp slanja, sa filterima."""
    _require_founder(user)
    supa = _get_supa()
    limit = min(max(limit, 1), 200)

    try:
        q = supa.table("notification_log").select("*").order("sent_at", desc=True).limit(limit)
        if channel:
            q = q.eq("channel", channel)
        if delivery_status:
            q = q.eq("delivery_status", delivery_status)
        if user_id:
            q = q.eq("user_id", user_id)
        if predmet_id:
            q = q.eq("ref_id", predmet_id)  # ref_id trenutno duplira ulogu predmet_id-a
        r = await asyncio.to_thread(q.execute)
        rows = r.data or []
    except Exception as e:
        logger.error("[ADMIN] notification-log greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri čitanju notification_log.")

    return {"notifikacije": rows, "ukupno": len(rows)}


@router.post("/notification-log/{notif_id}/retry")
@limiter.limit("15/minute")
async def notification_log_retry(
    notif_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Ponovo šalje notifikaciju koja je ranije neuspela (delivery_status='failed')."""
    _require_founder(user)
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("notification_log").select("*").eq("id", notif_id).maybe_single().execute()
        )
        row = r.data
    except Exception:
        row = None

    if not row:
        raise HTTPException(status_code=404, detail="Notifikacija nije pronađena.")
    if row.get("delivery_status") not in ("failed", "deferred_quiet_hours"):
        raise HTTPException(status_code=400, detail="Samo neuspele ili odložene notifikacije mogu da se ponove.")
    if not row.get("message_text"):
        raise HTTPException(status_code=422, detail="Originalni tekst poruke nije sačuvan — retry nije moguć za starije zapise.")

    channel = row.get("channel")
    target_uid = row.get("user_id")
    ok = False
    error_message = None

    try:
        if channel == "viber":
            vr = await asyncio.to_thread(
                lambda: supa.table("korisnik_viber_profil")
                    .select("viber_user_id").eq("user_id", target_uid).eq("aktivan", True).maybe_single().execute()
            )
            if vr.data and vr.data.get("viber_user_id"):
                from routers.viber import _viber_send
                ok = await _viber_send(vr.data["viber_user_id"], row["message_text"])
            else:
                error_message = "Viber nalog više nije povezan."
        elif channel in ("sms", "whatsapp"):
            sr = await asyncio.to_thread(
                lambda: supa.table("korisnik_sms_profil")
                    .select("telefon,whatsapp").eq("user_id", target_uid).eq("aktivan", True).maybe_single().execute()
            )
            if sr.data and sr.data.get("telefon"):
                from routers.sms import _send_sms
                to = f"whatsapp:{sr.data['telefon']}" if channel == "whatsapp" else sr.data["telefon"]
                ok = await asyncio.to_thread(_send_sms, to, row["message_text"][:160])
            else:
                error_message = "Broj telefona više nije registrovan."
        else:
            raise HTTPException(status_code=400, detail=f"Nepoznat kanal: {channel}")
    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e)[:150]

    new_status = "sent" if ok else "failed"
    try:
        await asyncio.to_thread(
            lambda: supa.table("notification_log").insert({
                "user_id":         target_uid,
                "channel":         channel,
                "tip":             row.get("tip", "retry"),
                "ref_id":          row.get("ref_id"),
                "delivery_status": new_status,
                "error_message":   error_message,
                "message_text":    row.get("message_text"),
            }).execute()
        )
    except Exception:
        pass

    return {"ok": ok, "delivery_status": new_status, "error_message": error_message}


# ─── Beta Users ─────────────────────────────────────────────────────────────

class BetaUserReq(BaseModel):
    email: str = Field(..., min_length=3, max_length=200)
    naziv_firme: Optional[str] = Field(default=None, max_length=200)
    napomena: Optional[str] = Field(default=None, max_length=500)


@router.get("/beta-users")
@limiter.limit("30/minute")
async def beta_users_list(request: Request, user: dict = Depends(get_current_user)):
    """Spisak beta korisnika i njihov status."""
    _require_founder(user)
    supa = _get_supa()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("beta_users").select("*").order("invited_at", desc=True).execute()
        )
        rows = r.data or []
    except Exception as e:
        logger.error("[ADMIN] beta-users greška: %s", e)
        rows = []
    return {"beta_korisnici": rows, "ukupno": len(rows)}


@router.post("/beta-users")
@limiter.limit("20/minute")
async def beta_users_add(
    body: BetaUserReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Dodaje email na spisak beta korisnika (status='invited')."""
    _require_founder(user)
    supa = _get_supa()
    try:
        await asyncio.to_thread(
            lambda: supa.table("beta_users").upsert({
                "email":       body.email.strip().lower(),
                "naziv_firme": body.naziv_firme,
                "napomena":    body.napomena,
            }, on_conflict="email").execute()
        )
    except Exception as e:
        logger.error("[ADMIN] beta-users insert greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri dodavanju beta korisnika.")
    return {"ok": True}


# ─── Security overview (samo vidljivost postojećih slojeva, bez nove logike) ──

@router.get("/security-overview")
@limiter.limit("20/minute")
async def security_overview(request: Request, user: dict = Depends(get_current_user)):
    """Read-only pregled statusa postojećih bezbednosnih slojeva (Wave 1/2)."""
    _require_founder(user)
    supa = _get_supa()
    od_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    async def _count(table: str, **filters) -> Optional[int]:
        try:
            q = supa.table(table).select("id", count="exact").limit(1)
            for k, v in filters.items():
                if k.endswith("_gte"):
                    q = q.gte(k[:-4], v)
                else:
                    q = q.eq(k, v)
            r = await asyncio.to_thread(q.execute)
            return r.count if r.count is not None else len(r.data or [])
        except Exception:
            return None

    last_anchor = None
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("chain_anchors")
                .select("anchored_at")
                .eq("id", "cron_daily_heartbeat")
                .maybe_single()
                .execute()
        )
        last_anchor = r.data.get("anchored_at") if r.data else None
    except Exception:
        pass

    return {
        "last_chain_anchor_at":       last_anchor,
        "security_events_24h":        await _count("security_events", created_at_gte=od_24h),
        "ai_forensics_24h":           await _count("ai_forensics", started_at_gte=od_24h),
        "napomena": "Read-only pregled postojećih bezbednosnih slojeva (Wave 1/2). Nema nove bezbednosne logike u ovom sprintu.",
    }


# ─── Pinecone Capacity Monitoring ───────────────────────────────────────────
# Broj vektora i procenjena veličina po namespace-u + nedeljni trend rasta.
# Snapshot se upisuje pri svakoj poseti (najviše jednom dnevno po namespace-u
# preko UNIQUE(snapshot_date, namespace) + upsert) — nema potrebe za posebnim
# cron job-om da bi se prikupljala istorija.

def _pinecone_index():
    from pinecone import Pinecone
    api_key = os.getenv("PINECONE_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="PINECONE_API_KEY nije konfigurisan.")
    pc = Pinecone(api_key=api_key)
    host = os.getenv("PINECONE_HOST", "").strip()
    if host:
        return pc.Index(host=host)
    return pc.Index(os.getenv("PINECONE_INDEX_NAME", "vindex-ai").strip())


@router.get("/pinecone-capacity")
@limiter.limit("20/minute")
async def pinecone_capacity(request: Request, user: dict = Depends(get_current_user)):
    """Broj vektora + procenjena veličina po namespace-u, plus nedeljni trend rasta
    (iz istorijskih snapshot-ova). Upisuje današnji snapshot ako još ne postoji."""
    _require_founder(user)

    try:
        idx = await asyncio.to_thread(_pinecone_index)
        stats = await asyncio.to_thread(idx.describe_index_stats)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[ADMIN] pinecone-capacity greška: %s", e)
        raise HTTPException(status_code=502, detail="Greška pri čitanju Pinecone statistike.")

    dimenzija = stats.get("dimension") or 3072
    bytes_po_vektoru = dimenzija * 4  # float32 — ne uključuje metapodatke (procena je donja granica)

    namespaces = []
    for naziv, info in (stats.get("namespaces") or {}).items():
        broj = info.get("vector_count", 0)
        namespaces.append({
            "namespace": naziv,
            "vector_count": broj,
            "estimated_bytes": broj * bytes_po_vektoru,
        })
    namespaces.sort(key=lambda n: -n["vector_count"])

    supa = _get_supa()
    danas = datetime.now(timezone.utc).date().isoformat()

    def _snapshot():
        rows = [{
            "snapshot_date": danas,
            "namespace": n["namespace"],
            "vector_count": n["vector_count"],
            "estimated_bytes": n["estimated_bytes"],
        } for n in namespaces]
        if rows:
            supa.table("pinecone_capacity_snapshots").upsert(
                rows, on_conflict="snapshot_date,namespace"
            ).execute()

    try:
        await asyncio.to_thread(_snapshot)
    except Exception as e:
        logger.warning("[ADMIN] pinecone-capacity snapshot upis neuspešan (nastavljam): %s", e)

    trend = {}
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).date().isoformat()
        r = await asyncio.to_thread(
            lambda: supa.table("pinecone_capacity_snapshots")
                .select("snapshot_date,namespace,vector_count,estimated_bytes")
                .gte("snapshot_date", cutoff)
                .order("snapshot_date", desc=False)
                .execute()
        )
        for row in (r.data or []):
            trend.setdefault(row["namespace"], []).append({
                "datum": row["snapshot_date"],
                "vector_count": row["vector_count"],
                "estimated_bytes": row["estimated_bytes"],
            })
    except Exception as e:
        logger.warning("[ADMIN] pinecone-capacity trend čitanje neuspešno: %s", e)

    return {
        "total_vector_count": stats.get("total_vector_count", 0),
        "dimension": dimenzija,
        "namespaces": namespaces,
        "trend_po_namespace": trend,
        "napomena": (
            "Procenjena veličina je DONJA granica (samo sirovi vektori, float32) — "
            "stvarna potrošnja prostora je veća zbog metapodataka. Koristi za trend, ne za tačan limit."
        ),
    }


# ─── Admin Feature Console ──────────────────────────────────────────────────
# Jedini način da se promeni tarifa/addon/cena/limit funkcije — NIKAD izmena
# koda. Svaka izmena odmah invalidira feature_registry keš (shared/
# feature_registry.py) tako da je vidljiva na sledećem pozivu, bez restarta.

class FeatureRegistryUpdate(BaseModel):
    naziv: Optional[str] = None
    kategorija: Optional[str] = None
    minimum_plan: Optional[str] = Field(default=None, description="basic/professional/enterprise ili null za addon-only")
    addon: Optional[str] = None
    krediti: Optional[float] = None
    krediti_po_minutu: Optional[float] = None
    credit_multiplier: Optional[float] = Field(default=None, description="Faktor množenja bazne cene za skuplje varijante iste funkcije (npr. 6 za kompletnu analizu). 1 = bez množenja.")
    dnevni_limit: Optional[int] = None
    mesecni_limit: Optional[int] = None
    cooldown_seconds: Optional[int] = None
    priority: Optional[str] = Field(default=None, description="HIGH/MEDIUM/LOW")
    estimated_cost_usd: Optional[float] = None
    version: Optional[str] = None
    status: Optional[str] = Field(default=None, description="ACTIVE/BETA/DEPRECATED/INTERNAL/COMING_SOON")
    visible: Optional[str] = Field(default=None, description="visible/hidden/internal/enterprise_only")
    feature_type: Optional[str] = Field(default=None, description="FOUNDATION/SUBSCRIPTION/ADDON/INTERNAL — određuje da li se funkcija uopšte pojavljuje u Pricing tabeli i gde")
    chargeable: Optional[bool] = None
    ai_model: Optional[str] = None
    aktivno: Optional[bool] = None
    opis: Optional[str] = None
    # Eksplicitni "obriši ovo ograničenje" flag-ovi — Pydantic ne razlikuje
    # "polje nije poslato" od "polje je namerno None" bez ovoga.
    ukloni_dnevni_limit: bool = False
    ukloni_mesecni_limit: bool = False
    ukloni_cooldown: bool = False
    ukloni_addon: bool = False
    ukloni_minimum_plan: bool = False


_VALID_STATUS = ("ACTIVE", "BETA", "DEPRECATED", "INTERNAL", "COMING_SOON")
_VALID_VISIBLE = ("visible", "hidden", "internal", "enterprise_only")
_VALID_PRIORITY = ("HIGH", "MEDIUM", "LOW")
_VALID_FEATURE_TYPE = ("FOUNDATION", "SUBSCRIPTION", "ADDON", "INTERNAL")


async def _write_audit(feature_key: str, changed_by: str, old_values: dict, new_values: dict) -> None:
    try:
        await asyncio.to_thread(
            lambda: _get_supa().table("feature_registry_audit").insert({
                "feature_key": feature_key,
                "changed_by": changed_by,
                "old_values": old_values,
                "new_values": new_values,
            }).execute()
        )
    except Exception as exc:
        # Migracija 065 možda nije pokrenuta na ovom okruženju — ne blokiraj izmenu zbog toga.
        logger.warning("[ADMIN] feature_registry_audit upis neuspešan (non-fatal): %s", exc)


@router.get("/feature-registry")
@limiter.limit("60/minute")
async def feature_registry_list(request: Request, user: dict = Depends(get_current_user)):
    """Sva 69 funkcija sa trenutnom politikom — Admin Feature Console tabela."""
    _require_founder(user)
    from shared.feature_registry import get_all_policies
    policies = await get_all_policies()
    policies.sort(key=lambda p: (p.get("kategorija") or "", p.get("feature_key") or ""))
    return {"features": policies, "ukupno": len(policies)}


@router.get("/feature-registry/{feature_key}/audit")
@limiter.limit("60/minute")
async def feature_registry_audit_history(feature_key: str, request: Request, user: dict = Depends(get_current_user), limit: int = 50):
    """Istorija izmena jedne funkcije — trajno, nikad se ne briše."""
    _require_founder(user)
    limit = min(max(limit, 1), 200)
    try:
        res = await asyncio.to_thread(
            lambda: _get_supa().table("feature_registry_audit")
                .select("*")
                .eq("feature_key", feature_key)
                .order("changed_at", desc=True)
                .limit(limit)
                .execute()
        )
        return {"feature_key": feature_key, "istorija": res.data or []}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Greška: {exc!r}")


@router.patch("/feature-registry/{feature_key}")
@limiter.limit("30/minute")
async def feature_registry_update(
    feature_key: str,
    payload: FeatureRegistryUpdate,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Menja politiku jedne funkcije. Odmah invalidira keš — promena je
    aktivna na sledećem pozivu bilo kog korisnika, bez deploy-a/restarta.
    Svaka izmena ostaje trajno u feature_registry_audit."""
    _require_founder(user)
    from shared.feature_registry import invalidate

    updates: dict = {}
    for field in ("naziv", "kategorija", "minimum_plan", "addon", "krediti",
                  "krediti_po_minutu", "credit_multiplier", "dnevni_limit", "mesecni_limit",
                  "cooldown_seconds", "priority", "estimated_cost_usd",
                  "version", "status", "visible", "feature_type", "chargeable",
                  "ai_model", "aktivno", "opis"):
        val = getattr(payload, field)
        if val is not None:
            updates[field] = val
    if payload.ukloni_dnevni_limit:
        updates["dnevni_limit"] = None
    if payload.ukloni_mesecni_limit:
        updates["mesecni_limit"] = None
    if payload.ukloni_cooldown:
        updates["cooldown_seconds"] = None
    if payload.ukloni_addon:
        updates["addon"] = None
    if payload.ukloni_minimum_plan:
        updates["minimum_plan"] = None

    if not updates:
        raise HTTPException(status_code=400, detail="Nema izmena u zahtevu.")
    if "minimum_plan" in updates and updates["minimum_plan"] is not None and updates["minimum_plan"] not in ("basic", "professional", "enterprise"):
        raise HTTPException(status_code=400, detail="minimum_plan mora biti basic/professional/enterprise ili null.")
    if "priority" in updates and updates["priority"] not in _VALID_PRIORITY:
        raise HTTPException(status_code=400, detail=f"priority mora biti jedno od: {_VALID_PRIORITY}.")
    if "status" in updates and updates["status"] not in _VALID_STATUS:
        raise HTTPException(status_code=400, detail=f"status mora biti jedno od: {_VALID_STATUS}.")
    if "visible" in updates and updates["visible"] not in _VALID_VISIBLE:
        raise HTTPException(status_code=400, detail=f"visible mora biti jedno od: {_VALID_VISIBLE}.")
    if "feature_type" in updates and updates["feature_type"] not in _VALID_FEATURE_TYPE:
        raise HTTPException(status_code=400, detail=f"feature_type mora biti jedno od: {_VALID_FEATURE_TYPE}.")

    try:
        old_res = await asyncio.to_thread(
            lambda: _get_supa().table("feature_registry").select("*").eq("feature_key", feature_key).maybe_single().execute()
        )
        if not old_res.data:
            raise HTTPException(status_code=404, detail=f"Feature '{feature_key}' nije pronađen u Registry-ju.")
        old_values = {k: old_res.data.get(k) for k in updates}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Greška pri čitanju stare vrednosti: {exc!r}")

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    updates["updated_by"] = user.get("email", "")

    try:
        res = await asyncio.to_thread(
            lambda: _get_supa().table("feature_registry")
                .update(updates)
                .eq("feature_key", feature_key)
                .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail=f"Feature '{feature_key}' nije pronađen u Registry-ju.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[ADMIN] feature-registry update greška za %s", feature_key)
        raise HTTPException(status_code=500, detail=f"Greška pri izmeni: {exc!r}")

    invalidate()
    await _write_audit(feature_key, user.get("email", ""), old_values, {k: v for k, v in updates.items() if k not in ("updated_at", "updated_by")})
    logger.info("[ADMIN] feature_registry['%s'] izmenjen od %s: %s", feature_key, user.get("email"), updates)
    return {"feature_key": feature_key, "azurirano": updates}


@router.post("/feature-registry/{feature_key}/toggle")
@limiter.limit("30/minute")
async def feature_registry_toggle(feature_key: str, request: Request, user: dict = Depends(get_current_user)):
    """Brzi kill-switch — uključi/isključi funkciju za SVE korisnike (uključujući foundera)."""
    _require_founder(user)
    from shared.feature_registry import get_policy, invalidate

    try:
        current = await get_policy(feature_key)
    except RuntimeError:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_key}' nije pronađen u Registry-ju.")

    novo_stanje = not current.get("aktivno", True)
    await asyncio.to_thread(
        lambda: _get_supa().table("feature_registry")
            .update({"aktivno": novo_stanje, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user.get("email", "")})
            .eq("feature_key", feature_key)
            .execute()
    )
    invalidate()
    await _write_audit(feature_key, user.get("email", ""), {"aktivno": current.get("aktivno", True)}, {"aktivno": novo_stanje})
    logger.warning("[ADMIN] feature_registry['%s'] aktivno=%s (od %s)", feature_key, novo_stanje, user.get("email"))
    return {"feature_key": feature_key, "aktivno": novo_stanje}


# ─── Admin Tier Config Console ───────────────────────────────────────────────
# Jedini način da se promeni cena/uključena mesta tarife — NIKAD izmena koda.
# Isti obrazac kao Admin Feature Console iznad (migracija 068).

class TierConfigUpdate(BaseModel):
    display_name: Optional[str] = None
    monthly_price_eur: Optional[float] = None
    yearly_price_eur: Optional[float] = None
    included_seats: Optional[int] = None
    extra_seat_price_eur: Optional[float] = None
    max_devices: Optional[int] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    ukloni_yearly_price: bool = False
    ukloni_extra_seat_price: bool = False
    ukloni_max_devices: bool = False


async def _write_tier_audit(tier_key: str, changed_by: str, old_values: dict, new_values: dict) -> None:
    try:
        await asyncio.to_thread(
            lambda: _get_supa().table("tier_config_audit").insert({
                "tier_key": tier_key,
                "changed_by": changed_by,
                "old_values": old_values,
                "new_values": new_values,
            }).execute()
        )
    except Exception as exc:
        logger.warning("[ADMIN] tier_config_audit upis neuspešan (non-fatal): %s", exc)


@router.get("/tier-config")
@limiter.limit("60/minute")
async def tier_config_list(request: Request, user: dict = Depends(get_current_user)):
    """Sve 3 tarife sa trenutnom cenom — Admin Tier Config tabela."""
    _require_founder(user)
    from shared.tier_config import get_all_tiers
    tiers = await get_all_tiers()
    return {"tiers": tiers, "ukupno": len(tiers)}


@router.get("/tier-config/{tier_key}/audit")
@limiter.limit("30/minute")
async def tier_config_audit_log(tier_key: str, request: Request, user: dict = Depends(get_current_user)):
    _require_founder(user)
    res = await asyncio.to_thread(
        lambda: _get_supa().table("tier_config_audit")
            .select("*")
            .eq("tier_key", tier_key)
            .order("changed_at", desc=True)
            .limit(50)
            .execute()
    )
    return {"tier_key": tier_key, "istorija": res.data or []}


@router.patch("/tier-config/{tier_key}")
@limiter.limit("30/minute")
async def tier_config_update(
    tier_key: str,
    payload: TierConfigUpdate,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Menja cenu/mesta jedne tarife. Odmah invalidira keš — promena je aktivna
    na sledećem pozivu bilo kog korisnika (Pricing modal, Settings, Product
    Intelligence, SeatService), bez deploy-a/restarta. Svaka izmena ostaje
    trajno u tier_config_audit."""
    _require_founder(user)
    from shared.tier_config import invalidate

    updates: dict = {}
    for field in ("display_name", "monthly_price_eur", "yearly_price_eur", "included_seats",
                  "extra_seat_price_eur", "max_devices", "description", "sort_order", "is_active"):
        val = getattr(payload, field)
        if val is not None:
            updates[field] = val
    if payload.ukloni_yearly_price:
        updates["yearly_price_eur"] = None
    if payload.ukloni_extra_seat_price:
        updates["extra_seat_price_eur"] = None
    if payload.ukloni_max_devices:
        updates["max_devices"] = None

    if not updates:
        raise HTTPException(status_code=400, detail="Nema izmena u zahtevu.")

    try:
        old_res = await asyncio.to_thread(
            lambda: _get_supa().table("tier_config").select("*").eq("tier_key", tier_key).maybe_single().execute()
        )
        if not old_res.data:
            raise HTTPException(status_code=404, detail=f"Tarifa '{tier_key}' nije pronađena u tier_config.")
        old_values = {k: old_res.data.get(k) for k in updates}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Greška pri čitanju stare vrednosti: {exc!r}")

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    updates["updated_by"] = user.get("email", "")

    try:
        res = await asyncio.to_thread(
            lambda: _get_supa().table("tier_config")
                .update(updates)
                .eq("tier_key", tier_key)
                .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail=f"Tarifa '{tier_key}' nije pronađena u tier_config.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[ADMIN] tier_config update greška za %s", tier_key)
        raise HTTPException(status_code=500, detail=f"Greška pri izmeni: {exc!r}")

    invalidate()
    await _write_tier_audit(tier_key, user.get("email", ""), old_values, {k: v for k, v in updates.items() if k not in ("updated_at", "updated_by")})
    logger.info("[ADMIN] tier_config['%s'] izmenjen od %s: %s", tier_key, user.get("email"), updates)
    return {"tier_key": tier_key, "azurirano": updates}

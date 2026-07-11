# -*- coding: utf-8 -*-
"""
Vindex AI — Usage Analytics

POST /analytics/track  — log usage event (fire-and-forget, bez credit deduction)
GET  /analytics/usage  — aggregirani pregled za poslednje N dana
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user, _is_founder
from shared.rate import limiter

logger = logging.getLogger("vindex.analytics")
router = APIRouter(tags=["analytics"])


class TrackReq(BaseModel):
    feature: str = Field(..., max_length=50)
    action: str = Field(..., max_length=50)
    predmet_id: Optional[str] = None
    metadata: Optional[dict] = None


async def _track_event(
    user_id: str,
    feature: str,
    action: str,
    predmet_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Fire-and-forget — pozivati via asyncio.create_task()."""
    try:
        supa = _get_supa()
        row: dict = {
            "user_id": user_id,
            "feature": feature[:50],
            "action":  action[:50],
        }
        if predmet_id:
            row["predmet_id"] = predmet_id
        if metadata:
            import json
            row["metadata"] = json.dumps(metadata, ensure_ascii=False)[:500]
        await asyncio.to_thread(
            lambda: supa.table("usage_events").insert(row).execute()
        )
    except Exception as e:
        logger.debug("[ANALYTICS] track greška: %s", e)


@router.post("/analytics/track")
@limiter.limit("120/minute")
async def track_usage(
    req: TrackReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Log usage event — bez credit deduction."""
    asyncio.create_task(
        _track_event(
            user["user_id"],
            req.feature,
            req.action,
            req.predmet_id,
            req.metadata,
        )
    )
    return {"ok": True}


@router.get("/analytics/usage")
@limiter.limit("30/minute")
async def get_usage(
    request: Request,
    user: dict = Depends(get_current_user),
    dana: int = 30,
):
    """Aggregirani usage stats za poslednje N dana (1–90)."""
    uid  = user["user_id"]
    dana = min(max(dana, 1), 90)
    since = (datetime.now(timezone.utc) - timedelta(days=dana)).isoformat()
    supa  = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("usage_events")
                .select("feature, action, predmet_id, created_at")
                .eq("user_id", uid)
                .gte("created_at", since)
                .order("created_at", desc=True)
                .limit(2000)
                .execute()
        )
        events = r.data or []
    except Exception as e:
        logger.error("[ANALYTICS] query greška: %s", e)
        events = []

    feature_counts: dict[str, int] = {}
    action_counts:  dict[str, int] = {}
    predmet_counts: dict[str, int] = {}
    day_counts:     dict[str, int] = {}

    for ev in events:
        f  = ev.get("feature") or ""
        a  = ev.get("action")  or ""
        p  = ev.get("predmet_id") or ""
        ts = (ev.get("created_at") or "")[:10]

        feature_counts[f] = feature_counts.get(f, 0) + 1
        action_counts[a]  = action_counts.get(a, 0) + 1
        if p:
            predmet_counts[p] = predmet_counts.get(p, 0) + 1
        if ts:
            day_counts[ts] = day_counts.get(ts, 0) + 1

    top_features  = sorted(feature_counts.items(), key=lambda x: -x[1])[:10]
    top_actions   = sorted(action_counts.items(),  key=lambda x: -x[1])[:10]
    top_pred_raw  = sorted(predmet_counts.items(), key=lambda x: -x[1])[:5]
    aktivnost     = sorted(day_counts.items())[-30:]

    # Enrich top predmeti with names
    top_predmeti = []
    for pid, cnt in top_pred_raw:
        try:
            pr = await asyncio.to_thread(
                lambda _p=pid: supa.table("predmeti")
                    .select("naziv")
                    .eq("id", _p)
                    .eq("user_id", uid)
                    .single()
                    .execute()
            )
            naziv = pr.data.get("naziv", pid) if pr.data else pid
        except Exception:
            naziv = pid
        top_predmeti.append({"predmet_id": pid, "naziv": naziv, "pristupa": cnt})

    return {
        "period_dana":       dana,
        "ukupno_dogadjaja":  len(events),
        "top_funkcije":      [{"feature": f, "count": c} for f, c in top_features],
        "top_akcije":        [{"action": a, "count": c} for a, c in top_actions],
        "top_predmeti":      top_predmeti,
        "aktivnost_po_danu": [{"datum": d, "count": c} for d, c in aktivnost],
    }


# ─── Opposing counsel tracker ─────────────────────────────────────────────────

_OPPOSING_ROLES = ("advokat_protivne", "protivna_strana", "protivna_stranka", "tuzeni")
_ISHOD_SCORE = {
    "pobeda":     1,
    "poraz":     -1,
    "nagodba":    0,
    "odustajanje": 0,
    "odbacena":   0,
    "ostalo":     0,
}


def _parse_ishod(dogadjaj: str) -> Optional[str]:
    """Iz hronologija teksta 'Predmet zatvoren — Ishod: X' izvlači ishod."""
    if not dogadjaj:
        return None
    low = dogadjaj.lower()
    for k in _ISHOD_SCORE:
        if k in low:
            return k
    return "ostalo"


@router.get("/analytics/opposing-counsel")
@limiter.limit("20/minute")
async def opposing_counsel_tracker(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Analitika suprotnih strana / protivnih advokata.
    Za svakog protivnika: ukupno predmeta, aktivni, zatvoreni, ishodi, tipovi predmeta.
    Sortiran po ukupnom broju predmeta (silazno).
    """
    uid  = user["user_id"]
    supa = _get_supa()

    # 1. Svi predmeti korisnika
    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id,naziv,tip,status")
            .eq("user_id", uid)
            .limit(500)
            .execute()
    )
    predmeti_all = pred_r.data or []
    if not predmeti_all:
        return {"suprotne_strane": [], "ukupno_predmeta": 0}

    pred_map = {p["id"]: p for p in predmeti_all}
    pred_ids = list(pred_map.keys())
    closed_ids = [p["id"] for p in predmeti_all if p.get("status") in ("zatvoren", "arhiviran")]

    # 2. predmet_klijenti sa ulogama protivne strane
    async def _empty():
        return type("R", (), {"data": []})()

    pk_r, hron_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmet_klijenti")
                .select("predmet_id,klijent_id,uloga_klijenta")
                .in_("predmet_id", pred_ids)
                .in_("uloga_klijenta", list(_OPPOSING_ROLES))
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_hronologija")
                .select("predmet_id,dogadjaj")
                .in_("predmet_id", closed_ids)
                .like("dogadjaj", "Predmet zatvoren%")
                .execute()
        ) if closed_ids else _empty(),
    )

    pk_rows  = pk_r.data or []
    hron_rows = hron_r.data or []

    # ishod lookup: predmet_id → ishod string
    ishod_map: dict[str, str] = {}
    for h in hron_rows:
        pid = h.get("predmet_id")
        if pid and pid not in ishod_map:
            ishod_map[pid] = _parse_ishod(h.get("dogadjaj", "")) or "ostalo"

    if not pk_rows:
        return {"suprotne_strane": [], "ukupno_predmeta": len(predmeti_all)}

    # 3. Učitaj klijente jednom batch-om
    kl_ids = list({r["klijent_id"] for r in pk_rows if r.get("klijent_id")})
    kl_r = await asyncio.to_thread(
        lambda: supa.table("klijenti")
            .select("id,ime,prezime,firma")
            .in_("id", kl_ids)
            .execute()
    )
    kl_map = {k["id"]: k for k in (kl_r.data or [])}

    # 4. Agregacija po klijentu
    agg: dict[str, dict] = {}
    for row in pk_rows:
        kid = row.get("klijent_id")
        pid = row.get("predmet_id")
        if not kid or not pid:
            continue

        kl = kl_map.get(kid, {})
        ime = (
            ((kl.get("ime") or "") + " " + (kl.get("prezime") or "")).strip()
            or kl.get("firma") or kid[:8]
        )
        firma = kl.get("firma") or ""

        if kid not in agg:
            agg[kid] = {
                "klijent_id":   kid,
                "ime":          ime,
                "firma":        firma,
                "uloge":        set(),
                "predmeti_ids": set(),
                "tipovi":       {},
                "ishodi":       {"pobeda": 0, "poraz": 0, "nagodba": 0, "ostalo": 0},
                "aktivni":      0,
                "zatvoreni":    0,
            }

        entry = agg[kid]
        entry["uloge"].add(row.get("uloga_klijenta", ""))
        if pid in entry["predmeti_ids"]:
            continue
        entry["predmeti_ids"].add(pid)

        pred = pred_map.get(pid, {})
        tip  = pred.get("tip") or "ostalo"
        entry["tipovi"][tip] = entry["tipovi"].get(tip, 0) + 1

        if pred.get("status") in ("zatvoren", "arhiviran"):
            entry["zatvoreni"] += 1
            ishod = ishod_map.get(pid, "ostalo")
            entry["ishodi"][ishod] = entry["ishodi"].get(ishod, 0) + 1
        else:
            entry["aktivni"] += 1

    # 5. Pripremi output
    result = []
    for kid, e in agg.items():
        ukupno = len(e["predmeti_ids"])
        ishodi = e["ishodi"]
        score  = ishodi.get("pobeda", 0) - ishodi.get("poraz", 0)
        top_tip = max(e["tipovi"], key=e["tipovi"].get) if e["tipovi"] else None
        result.append({
            "klijent_id":     kid,
            "ime":            e["ime"],
            "firma":          e["firma"],
            "uloge":          sorted(e["uloge"]),
            "ukupno_predmeta": ukupno,
            "aktivni":        e["aktivni"],
            "zatvoreni":      e["zatvoreni"],
            "ishodi": {
                "pobeda":     ishodi.get("pobeda", 0),
                "poraz":      ishodi.get("poraz", 0),
                "nagodba":    ishodi.get("nagodba", 0),
                "ostalo":     ishodi.get("ostalo", 0),
            },
            "score":          score,
            "dominantni_tip": top_tip,
        })

    result.sort(key=lambda x: -x["ukupno_predmeta"])

    return {
        "suprotne_strane":  result,
        "ukupno_predmeta":  len(predmeti_all),
        "ukupno_protivnika": len(result),
    }


# ─── Platform Analytics Dashboard (founder-only, svi korisnici) ──────────────

@router.get("/api/admin/analytics/platform")
@limiter.limit("15/minute")
async def platform_analytics(
    request: Request,
    user: dict = Depends(get_current_user),
    dana: int = 30,
):
    """
    Founder-only agregatna analitika preko SVIH korisnika (za razliku od
    /analytics/usage koji je per-user). Koristi iste usage_events kao i
    postojeci piTrack/_track_event pipeline — bez nove instrumentacije.
    """
    if not _is_founder(user.get("email", "")):
        raise HTTPException(status_code=403, detail="Restricted.")

    dana = min(max(dana, 1), 90)
    supa = _get_supa()
    now  = datetime.now(timezone.utc)
    since = (now - timedelta(days=dana)).isoformat()
    since_1d = (now - timedelta(days=1)).isoformat()
    since_7d = (now - timedelta(days=7)).isoformat()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("usage_events")
                .select("user_id,feature,action,metadata,created_at")
                .gte("created_at", since)
                .limit(5000)
                .execute()
        )
        events = r.data or []
    except Exception as e:
        logger.error("[ANALYTICS] platform query greška: %s", e)
        events = []

    def _count(feature: str, action: str) -> int:
        return sum(1 for e in events if e.get("feature") == feature and e.get("action") == action)

    def _distinct_users(feature: Optional[str] = None, action: Optional[str] = None, since_iso: Optional[str] = None) -> set:
        out = set()
        for e in events:
            if feature and e.get("feature") != feature:
                continue
            if action and e.get("action") != action:
                continue
            if since_iso and (e.get("created_at") or "") < since_iso:
                continue
            if e.get("user_id"):
                out.add(e["user_id"])
        return out

    wizard_started   = _count("wizard", "started")
    wizard_completed = _count("wizard", "completed")
    ai_started        = _count("ai_analysis", "started")
    ai_completed      = _count("ai_analysis", "completed")
    draft_accepted    = _count("ai_outcome", "accepted")
    draft_edited      = _count("ai_outcome", "edited")
    draft_rejected    = _count("ai_outcome", "rejected")
    draft_total       = draft_accepted + draft_edited + draft_rejected

    # Portal monitoring adoption
    portal_users = _distinct_users("portal", "tracking_enabled")
    active_users = _distinct_users()

    # APR lookup usage (odvojena tabela — ne usage_events)
    apr_uspesno = apr_total = 0
    try:
        apr_r = await asyncio.to_thread(
            lambda: supa.table("apr_lookup_log").select("success").gte("created_at", since).execute()
        )
        apr_rows = apr_r.data or []
        apr_total = len(apr_rows)
        apr_uspesno = sum(1 for x in apr_rows if x.get("success"))
    except Exception:
        pass

    # DAU/WAU
    dau = len(_distinct_users(since_iso=since_1d))
    wau = len(_distinct_users(since_iso=since_7d))

    # Avg sesija po korisniku (aktivne_sesije: distinct device_id po user_id)
    avg_sessions = None
    try:
        sess_r = await asyncio.to_thread(
            lambda: supa.table("aktivne_sesije").select("user_id,device_id").execute()
        )
        sess_rows = sess_r.data or []
        by_user: dict[str, set] = {}
        for s in sess_rows:
            uid = s.get("user_id")
            if uid:
                by_user.setdefault(uid, set()).add(s.get("device_id"))
        if by_user:
            avg_sessions = round(sum(len(v) for v in by_user.values()) / len(by_user), 2)
    except Exception:
        pass

    # Najkorišćeniji/najmanje korišćeni tabovi (nav/tab_switch, metadata={"tab": t})
    tab_counts: dict[str, int] = {}
    for e in events:
        if e.get("feature") == "nav" and e.get("action") == "tab_switch":
            try:
                meta = json.loads(e.get("metadata") or "{}")
                t = meta.get("tab")
                if t:
                    tab_counts[t] = tab_counts.get(t, 0) + 1
            except Exception:
                pass
    tab_sorted = sorted(tab_counts.items(), key=lambda x: -x[1])

    return {
        "period_dana": dana,
        "wizard": {
            "started": wizard_started, "completed": wizard_completed,
            "completion_rate_pct": round(wizard_completed / wizard_started * 100, 1) if wizard_started else None,
        },
        "ai_analysis": {"started": ai_started, "completed": ai_completed},
        "apr_lookup": {
            "ukupno": apr_total, "uspesno": apr_uspesno,
            "stopa_uspeha_pct": round(apr_uspesno / apr_total * 100, 1) if apr_total else None,
        },
        "portal_monitoring_adoption": {
            "korisnika_ukljucilo": len(portal_users),
            "aktivnih_korisnika": len(active_users),
            "stopa_pct": round(len(portal_users) / len(active_users) * 100, 1) if active_users else None,
        },
        "draft_outcomes": {
            "accepted": draft_accepted, "edited": draft_edited, "rejected": draft_rejected,
            "accepted_rate_pct": round(draft_accepted / draft_total * 100, 1) if draft_total else None,
        },
        "dau": dau,
        "wau": wau,
        "avg_sessions_per_user": avg_sessions,
        "top_tabovi": [{"tab": t, "count": c} for t, c in tab_sorted[:8]],
        "najmanje_koriscenih_tabova": [{"tab": t, "count": c} for t, c in tab_sorted[-5:]] if len(tab_sorted) > 3 else [],
    }

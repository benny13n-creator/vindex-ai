# -*- coding: utf-8 -*-
"""
Vindex AI — Product Intelligence Layer
Faza: Intelligence (Admin only — founder guard)

GET /admin/pi/overview    — DAU/WAU/MAU, sessions, trends
GET /admin/pi/features    — usage per feature + credit estimates
GET /admin/pi/retention   — cohort retention matrix + D7/D30
GET /admin/pi/funnels     — funnel conversion analytics
GET /admin/pi/timeline    — 90-day daily chart data
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from shared.deps import (
    FOUNDER_EMAILS,
    _get_supa,
    get_current_user,
)
from shared.rate import limiter

logger = logging.getLogger("vindex.pi")
router = APIRouter(tags=["product_intelligence"])

# Credit cost per feature (known from codebase)
_CREDIT_COST: dict[str, int] = {
    "pravno_istrazivanje": 1,
    "analiza_rizika":      1,
    "zastarelost":         1,
    "sudska_praksa":       1,
    "dokument":            1,
    "predmeti":            0,
    "copilot":             1,
    "strategija":          1,
    "drafting":            2,
    "web3":                2,
    "hearing_cc":          3,
    "intake":              2,
    "dashboard":           0,
    "nav":                 0,
    "auth":                0,
    "session":             0,
    "klijenti":            0,
    "kalendar":            0,
    "inbox":               0,
    "billing":             0,
    "notifikacije":        0,
}

# Predefined conversion funnels
_FUNNELS: list[dict] = [
    {
        "naziv": "Onboarding korisnika",
        "koraci": [
            {"feature": "auth",                "action": "login",   "label": "Prijava"},
            {"feature": "dashboard",           "action": "view",    "label": "Otvorio Centar"},
            {"feature": "pravno_istrazivanje", "action": "query",   "label": "Prvo pitanje"},
            {"feature": "predmeti",            "action": "create",  "label": "Kreirao predmet"},
            {"feature": "analiza_rizika",      "action": "run",     "label": "Prva analiza"},
        ],
    },
    {
        "naziv": "Analiza predmeta",
        "koraci": [
            {"feature": "predmeti",        "action": "open",    "label": "Otvorio predmet"},
            {"feature": "dokument",        "action": "upload",  "label": "Upload dokumenta"},
            {"feature": "analiza_rizika",  "action": "run",     "label": "Analiza rizika"},
            {"feature": "strategija",      "action": "run",     "label": "Strategija"},
        ],
    },
    {
        "naziv": "Priprema ročišta",
        "koraci": [
            {"feature": "predmeti",   "action": "open",     "label": "Otvorio predmet"},
            {"feature": "kalendar",   "action": "view",     "label": "Pogledao kalendar"},
            {"feature": "hearing_cc", "action": "generate", "label": "Generisao brifing"},
            {"feature": "hearing_cc", "action": "followup", "label": "Follow-up ročišta"},
        ],
    },
    {
        "naziv": "Copilot sesija",
        "koraci": [
            {"feature": "predmeti", "action": "open",   "label": "Otvorio predmet"},
            {"feature": "copilot",  "action": "query",  "label": "Pitanje copilotu"},
            {"feature": "copilot",  "action": "query",  "label": "Nastavak konverzacije"},
            {"feature": "copilot",  "action": "export", "label": "Eksport beleške"},
        ],
    },
]


# ─── Admin guard ──────────────────────────────────────────────────────────────

async def _require_admin(user: dict = Depends(get_current_user)) -> dict:
    if (user.get("email") or "").lower() not in FOUNDER_EMAILS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Pristup zabranjen — samo za administratore.")
    return user


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe(r) -> list:
    if isinstance(r, Exception):
        return []
    return r.data or []


def _compute_sessions(events: list[dict]) -> tuple[int, float, list[float]]:
    """
    Group events per user into 30-minute sessions.
    Returns (session_count, avg_duration_minutes, durations_list).
    """
    by_user: dict[str, list[datetime]] = defaultdict(list)
    for ev in events:
        uid = ev.get("user_id", "")
        ts_raw = ev.get("created_at", "")
        if not (uid and ts_raw):
            continue
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except Exception:
            continue
        by_user[uid].append(ts)

    durations: list[float] = []
    for uid, timestamps in by_user.items():
        timestamps.sort()
        s_start = timestamps[0]
        s_last  = timestamps[0]
        for ts in timestamps[1:]:
            gap_sec = (ts - s_last).total_seconds()
            if gap_sec > 1800:  # 30 min
                dur = (s_last - s_start).total_seconds() / 60
                durations.append(dur)
                s_start = ts
            s_last = ts
        dur = (s_last - s_start).total_seconds() / 60
        durations.append(dur)

    total = len(durations)
    avg   = round(sum(durations) / total, 1) if total else 0.0
    return total, avg, durations


def _cohort_retention(events: list[dict]) -> dict:
    """
    Weekly cohort retention matrix.
    Returns {cohorts: [{week, users, W0..W4}], d7_rate, d30_rate}.
    """
    if not events:
        return {"cohorts": [], "d7_rate": 0.0, "d30_rate": 0.0}

    # Find first-activity week per user
    first_week: dict[str, date] = {}
    user_weeks: dict[str, set[date]] = defaultdict(set)

    for ev in events:
        uid    = ev.get("user_id", "")
        ts_raw = (ev.get("created_at") or "")[:10]
        if not (uid and ts_raw):
            continue
        try:
            d = date.fromisoformat(ts_raw)
        except Exception:
            continue
        # Normalize to Monday of that week
        monday = d - timedelta(days=d.weekday())
        if uid not in first_week or monday < first_week[uid]:
            first_week[uid] = monday
        user_weeks[uid].add(monday)

    today = date.today()
    today_monday = today - timedelta(days=today.weekday())

    # Build cohort data for last 8 weeks
    cohorts_out: list[dict] = []
    for weeks_ago in range(7, -1, -1):
        cohort_monday = today_monday - timedelta(weeks=weeks_ago)
        cohort_label  = cohort_monday.isoformat()
        cohort_users  = [uid for uid, fw in first_week.items() if fw == cohort_monday]
        n_users       = len(cohort_users)
        if n_users == 0:
            continue
        week_ret: dict[str, Optional[float]] = {}
        for w in range(1, 5):
            target = cohort_monday + timedelta(weeks=w)
            if target > today_monday:
                week_ret[f"W{w}"] = None  # Future
            else:
                active = sum(1 for uid in cohort_users if target in user_weeks[uid])
                week_ret[f"W{w}"] = round(active / n_users * 100, 1)
        cohorts_out.append({
            "week":   cohort_label,
            "users":  n_users,
            **week_ret,
        })

    # D7 and D30 retention
    cutoff_d7  = today - timedelta(days=7)
    cutoff_d30 = today - timedelta(days=30)
    cutoff_d7m  = cutoff_d7  - timedelta(days=7)
    cutoff_d30m = cutoff_d30 - timedelta(days=30)

    d7_cohort  = [uid for uid, fw in first_week.items()
                  if cutoff_d7m <= fw <= cutoff_d7]
    d30_cohort = [uid for uid, fw in first_week.items()
                  if cutoff_d30m <= fw <= cutoff_d30]

    def _recently_active(uid: str, since: date) -> bool:
        return any(w >= since - timedelta(days=since.weekday())
                   for w in user_weeks[uid])

    d7_rate  = (round(sum(1 for u in d7_cohort  if _recently_active(u, cutoff_d7)) / len(d7_cohort)  * 100, 1)
                if d7_cohort  else None)
    d30_rate = (round(sum(1 for u in d30_cohort if _recently_active(u, cutoff_d30)) / len(d30_cohort) * 100, 1)
                if d30_cohort else None)

    return {
        "cohorts":  cohorts_out,
        "d7_rate":  d7_rate,
        "d30_rate": d30_rate,
    }


def _funnel_conversion(events: list[dict], funnel: dict) -> dict:
    """Compute conversion for a single funnel across all users."""
    koraci = funnel["koraci"]
    if not koraci:
        return {"naziv": funnel["naziv"], "koraci": [], "ukupna_konverzija": None}

    # For each user track which steps they've completed
    completed: dict[str, int] = defaultdict(int)

    # Build user event sets: {uid: {(feature, action), ...}}
    user_pairs: dict[str, set] = defaultdict(set)
    for ev in events:
        uid = ev.get("user_id", "")
        f   = ev.get("feature", "")
        a   = ev.get("action", "")
        if uid and f:
            user_pairs[uid].add((f, a))

    # Users reaching each step
    all_users = len(user_pairs)
    step_counts: list[int] = []
    for i, korak in enumerate(koraci):
        pair = (korak["feature"], korak["action"])
        n = sum(1 for u, pairs in user_pairs.items() if pair in pairs)
        step_counts.append(n)

    result_koraci = []
    for i, korak in enumerate(koraci):
        n        = step_counts[i]
        prev     = step_counts[i - 1] if i > 0 else all_users
        step_cvr = round(n / prev * 100, 1) if prev > 0 else 0.0
        result_koraci.append({
            "label":       korak["label"],
            "feature":     korak["feature"],
            "action":      korak["action"],
            "korisnici":   n,
            "konverzija":  step_cvr,
        })

    overall = round(step_counts[-1] / all_users * 100, 1) if all_users and step_counts else 0.0
    return {
        "naziv":               funnel["naziv"],
        "ukupna_konverzija":   overall,
        "ukupno_korisnika":    all_users,
        "koraci":              result_koraci,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/pi/overview")
@limiter.limit("30/minute")
async def pi_overview(
    request: Request,
    user: dict = Depends(_require_admin),
):
    """DAU / WAU / MAU + session metrics + period trends."""
    supa  = _get_supa()
    today = date.today()

    since_90d  = (today - timedelta(days=90)).isoformat() + "T00:00:00+00:00"
    since_180d = (today - timedelta(days=180)).isoformat() + "T00:00:00+00:00"
    today_iso  = today.isoformat()
    since_7d   = (today - timedelta(days=7)).isoformat()
    since_30d  = (today - timedelta(days=30)).isoformat()

    (ev_90_r, ev_180_r) = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("usage_events")
            .select("user_id,feature,action,created_at")
            .gte("created_at", since_90d)
            .order("created_at")
            .limit(100000)
            .execute()),
        asyncio.to_thread(lambda: supa.table("usage_events")
            .select("user_id,created_at")
            .gte("created_at", since_180d)
            .lt("created_at", since_90d)
            .limit(50000)
            .execute()),
        return_exceptions=True,
    )

    ev90  = _safe(ev_90_r)
    ev180 = _safe(ev_180_r)

    def _users_since(evs: list, since: str) -> set[str]:
        return {e["user_id"] for e in evs
                if (e.get("created_at") or "")[:10] >= since
                and e.get("user_id")}

    dau = len(_users_since(ev90, today_iso))
    wau = len(_users_since(ev90, since_7d))
    mau = len(_users_since(ev90, since_30d))

    # Previous period
    prev_30_start = (today - timedelta(days=60)).isoformat()
    prev_30_end   = since_30d
    prev_mau = len({e["user_id"] for e in ev180
                    if prev_30_start <= (e.get("created_at") or "")[:10] < prev_30_end
                    and e.get("user_id")})

    def _trend(current: int, prev: int) -> str:
        if prev == 0:
            return "+100%" if current > 0 else "0%"
        pct = round((current - prev) / prev * 100)
        return f"+{pct}%" if pct >= 0 else f"{pct}%"

    # Sessions
    total_sessions, avg_min, _ = _compute_sessions(ev90)

    # Events per day (last 30)
    day_counts: dict[str, int] = defaultdict(int)
    day_users:  dict[str, set] = defaultdict(set)
    for ev in ev90:
        d = (ev.get("created_at") or "")[:10]
        if d >= since_30d:
            day_counts[d] += 1
            if ev.get("user_id"):
                day_users[d].add(ev["user_id"])

    # Total unique users
    all_users_90d = {e["user_id"] for e in ev90 if e.get("user_id")}

    return {
        "dau":                    dau,
        "wau":                    wau,
        "mau":                    mau,
        "mau_trend":              _trend(mau, prev_mau),
        "total_korisnika_90d":    len(all_users_90d),
        "total_events_30d":       sum(1 for e in ev90 if (e.get("created_at") or "")[:10] >= since_30d),
        "total_sessions_90d":     total_sessions,
        "avg_session_minutes":    avg_min,
        "events_per_day_30d":     [
            {"datum": d, "events": day_counts.get(d, 0), "korisnici": len(day_users.get(d, set()))}
            for d in sorted(set(
                [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
            ))
        ],
    }


@router.get("/admin/pi/features")
@limiter.limit("30/minute")
async def pi_features(
    request: Request,
    user: dict = Depends(_require_admin),
    dana: int = 30,
):
    """Top + least used features, credit spend estimates, action breakdown."""
    dana  = min(max(dana, 7), 90)
    supa  = _get_supa()
    since = (date.today() - timedelta(days=dana)).isoformat() + "T00:00:00+00:00"

    r = await asyncio.to_thread(lambda: supa.table("usage_events")
        .select("user_id,feature,action,created_at")
        .gte("created_at", since)
        .limit(50000)
        .execute())

    events = _safe(r)
    total  = len(events)

    feature_counts:  dict[str, int]      = defaultdict(int)
    feature_users:   dict[str, set]      = defaultdict(set)
    action_by_feat:  dict[str, dict]     = defaultdict(lambda: defaultdict(int))

    for ev in events:
        f = ev.get("feature") or "unknown"
        a = ev.get("action")  or "unknown"
        u = ev.get("user_id") or ""
        feature_counts[f] += 1
        feature_users[f].add(u)
        action_by_feat[f][a] += 1

    all_features = sorted(feature_counts.keys())
    feature_data = []
    for f in sorted(feature_counts, key=lambda x: -feature_counts[x]):
        cnt   = feature_counts[f]
        cost  = _CREDIT_COST.get(f, 1)
        feature_data.append({
            "feature":         f,
            "events":          cnt,
            "unique_users":    len(feature_users[f]),
            "pct_of_total":    round(cnt / total * 100, 1) if total else 0.0,
            "credit_cost":     cost,
            "credits_spent":   cnt * cost,
            "top_actions":     sorted(action_by_feat[f].items(), key=lambda x: -x[1])[:5],
        })

    return {
        "period_dana":         dana,
        "ukupno_events":       total,
        "ukupno_features":     len(feature_counts),
        "top_features":        feature_data[:10],
        "least_used":          list(reversed(feature_data))[:5],
        "all_features":        feature_data,
        "total_credits_spent": sum(fd["credits_spent"] for fd in feature_data),
    }


@router.get("/admin/pi/retention")
@limiter.limit("20/minute")
async def pi_retention(
    request: Request,
    user: dict = Depends(_require_admin),
):
    """Weekly cohort retention matrix + D7/D30 rates."""
    supa  = _get_supa()
    since = (date.today() - timedelta(days=120)).isoformat() + "T00:00:00+00:00"

    r = await asyncio.to_thread(lambda: supa.table("usage_events")
        .select("user_id,created_at")
        .gte("created_at", since)
        .order("created_at")
        .limit(100000)
        .execute())

    events = _safe(r)
    data   = _cohort_retention(events)

    return {
        **data,
        "opis": "Procenat korisnika iz početne kohort nedelje koji su ostali aktivni u W1-W4",
    }


@router.get("/admin/pi/funnels")
@limiter.limit("20/minute")
async def pi_funnels(
    request: Request,
    user: dict = Depends(_require_admin),
    dana: int = 30,
):
    """Funnel conversion analytics for predefined user journeys."""
    dana  = min(max(dana, 7), 90)
    supa  = _get_supa()
    since = (date.today() - timedelta(days=dana)).isoformat() + "T00:00:00+00:00"

    r = await asyncio.to_thread(lambda: supa.table("usage_events")
        .select("user_id,feature,action,created_at")
        .gte("created_at", since)
        .limit(50000)
        .execute())

    events  = _safe(r)
    results = [_funnel_conversion(events, f) for f in _FUNNELS]

    return {
        "period_dana": dana,
        "funnels":     results,
    }


@router.get("/admin/pi/timeline")
@limiter.limit("30/minute")
async def pi_timeline(
    request: Request,
    user: dict = Depends(_require_admin),
    dana: int = 90,
):
    """Daily active users + event counts for trend charts."""
    dana  = min(max(dana, 7), 180)
    supa  = _get_supa()
    since = (date.today() - timedelta(days=dana)).isoformat() + "T00:00:00+00:00"

    r = await asyncio.to_thread(lambda: supa.table("usage_events")
        .select("user_id,feature,created_at")
        .gte("created_at", since)
        .order("created_at")
        .limit(200000)
        .execute())

    events = _safe(r)
    today  = date.today()

    day_stats: dict[str, dict] = {}
    for ev in events:
        d = (ev.get("created_at") or "")[:10]
        if not d:
            continue
        if d not in day_stats:
            day_stats[d] = {"events": 0, "users": set(), "features": defaultdict(int)}
        day_stats[d]["events"] += 1
        if ev.get("user_id"):
            day_stats[d]["users"].add(ev["user_id"])
        f = ev.get("feature") or "unknown"
        day_stats[d]["features"][f] += 1

    timeline = []
    for i in range(dana - 1, -1, -1):
        d   = (today - timedelta(days=i)).isoformat()
        st  = day_stats.get(d, {})
        timeline.append({
            "datum":     d,
            "dau":       len(st.get("users", set())),
            "events":    st.get("events", 0),
            "top_feature": max(st.get("features", {}).items(), key=lambda x: x[1])[0]
                           if st.get("features") else None,
        })

    return {
        "period_dana": dana,
        "timeline":    timeline,
        "peak_dau":    max((t["dau"] for t in timeline), default=0),
        "peak_datum":  max(timeline, key=lambda t: t["dau"], default={}).get("datum"),
    }


@router.get("/admin/pi/plans")
@limiter.limit("30/minute")
async def pi_plans(
    request: Request,
    user: dict = Depends(_require_admin),
):
    """Plan distribucija, MRR procena, AI usage ovog meseca, onboarding email stats."""
    from datetime import datetime, timezone
    supa  = _get_supa()
    now   = datetime.now(timezone.utc)
    ym    = now.strftime("%Y-%m")

    _PLAN_PRICE_EUR = {"free": 0, "advokat": 19, "pro": 39, "firma": 59}

    plans_r, usage_r, profiles_r, onboard_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("korisnik_plan").select("plan_type, seats, billing_cycle").execute()),
        asyncio.to_thread(lambda: supa.table("korisnik_usage").select("ai_queries, doc_analyses, strategies").eq("year_month", ym).execute()),
        asyncio.to_thread(lambda: supa.table("profiles").select("id, registered_at, created_at").execute()),
        asyncio.to_thread(lambda: supa.table("onboarding_email_log").select("tip").execute()),
        return_exceptions=True,
    )

    plans    = _safe(plans_r)
    usages   = _safe(usage_r)
    profiles = _safe(profiles_r)
    onboard  = _safe(onboard_r)

    # Plan distribution
    dist: dict[str, int] = {"free": 0, "advokat": 0, "pro": 0, "firma": 0}
    mrr_eur = 0.0
    for p in plans:
        pt    = p.get("plan_type", "free")
        seats = p.get("seats", 1) or 1
        mult  = 0.8 if p.get("billing_cycle") == "yearly" else 1.0
        dist[pt] = dist.get(pt, 0) + 1
        mrr_eur += _PLAN_PRICE_EUR.get(pt, 0) * seats * mult

    # Free users = profiles not in korisnik_plan
    plan_uids = set()
    if not isinstance(plans_r, Exception):
        plan_uids = {p.get("user_id", "") for p in (plans_r.data or []) if p.get("user_id")}
    total_profiles = len(profiles)
    dist["free"] = max(0, total_profiles - sum(dist[k] for k in ["advokat", "pro", "firma"]))

    # Monthly AI usage totals
    total_queries    = sum(u.get("ai_queries", 0) or 0 for u in usages)
    total_docs       = sum(u.get("doc_analyses", 0) or 0 for u in usages)
    total_strategies = sum(u.get("strategies", 0) or 0 for u in usages)

    # Onboarding email stats
    ob_counts: dict[str, int] = {"welcome": 0, "day1": 0, "day3": 0}
    for ob in onboard:
        tip = ob.get("tip", "")
        if tip in ob_counts:
            ob_counts[tip] += 1

    # Conversion: % of registered who got past welcome (rough)
    reg_total = total_profiles
    ob_pct = {
        "welcome_rate": round(ob_counts["welcome"] / reg_total * 100, 1) if reg_total else 0,
        "day1_rate":    round(ob_counts["day1"]    / reg_total * 100, 1) if reg_total else 0,
        "day3_rate":    round(ob_counts["day3"]    / reg_total * 100, 1) if reg_total else 0,
    }

    return {
        "plan_distribucija":  dist,
        "ukupno_korisnika":   reg_total,
        "placajuci":          dist["advokat"] + dist["pro"] + dist["firma"],
        "mrr_eur":            round(mrr_eur, 2),
        "arr_eur":            round(mrr_eur * 12, 2),
        "ai_usage_ovaj_mesec": {
            "ai_queries":   total_queries,
            "doc_analyses": total_docs,
            "strategies":   total_strategies,
        },
        "onboarding_emails":  ob_counts,
        "onboarding_rates":   ob_pct,
    }

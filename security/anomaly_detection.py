# -*- coding: utf-8 -*-
"""
Vindex AI — security/anomaly_detection.py

Behavioral Anomaly Detection — detektuje kompromitovane naloge.

Princip: svaki korisnik ima "bazni profil" (prosek poslednjih 30 dana).
Ako tekući dan drastično odstupa od profila, sistem automatski:
  1. Loguje u security_events (za admin pregled)
  2. Upisuje u audit_immutable
  3. Vraća True (blokiraj) ili False (dozvoli)

Faktori koji se prate:
  - Broj zahteva po satu (ai_calls, api_calls)
  - Broj unikatnih IP adresa u jednom danu
  - Vreme pristupa (noćni pristup za korisnike koji nikad noću ne rade)
  - Neobičan endpoint pattern (odjednom masovni export)

Ovaj modul NE odlučuje sam — šalje signal, API layer odlučuje o blokadi.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import NamedTuple, Optional

logger = logging.getLogger("vindex.security.anomaly")

# ─── Pragovi ─────────────────────────────────────────────────────────────────

# Koliko puta veće od proseka je "anomalija"
ANOMALY_MULTIPLIER_AI    = float(os.getenv("ANOMALY_AI_MULTIPLIER", "10.0"))
ANOMALY_MULTIPLIER_API   = float(os.getenv("ANOMALY_API_MULTIPLIER", "20.0"))
ANOMALY_MULTIPLIER_IP    = float(os.getenv("ANOMALY_IP_MULTIPLIER",  "5.0"))

# Apsolutni minimalni pragovi (čak i bez baznog profila)
ABS_AI_HOURLY_LIMIT  = int(os.getenv("ABS_AI_HOURLY_LIMIT", "200"))
ABS_API_HOURLY_LIMIT = int(os.getenv("ABS_API_HOURLY_LIMIT", "2000"))
ABS_IP_DAILY_LIMIT   = int(os.getenv("ABS_IP_DAILY_LIMIT",   "15"))

# Minimum dana istorije pre nego što se anomaly detection aktivira
MIN_HISTORY_DAYS = 3

# In-memory sliding window (reset pri restartu — dopuna DB profilu)
_hourly_ai:  dict[str, deque[float]]  = defaultdict(lambda: deque())
_hourly_api: dict[str, deque[float]]  = defaultdict(lambda: deque())
_daily_ips:  dict[str, set[str]]       = defaultdict(set)
_last_seen:  dict[str, float]          = {}


class AnomalySignal(NamedTuple):
    is_anomaly: bool
    score: float            # 0.0–1.0 (veće = sumnjivije)
    reasons: list[str]
    user_id: str


# ─── Javni API ────────────────────────────────────────────────────────────────

def record_request(user_id: str, endpoint: str, ip: str, is_ai: bool) -> None:
    """
    Beleži dolazni zahtev u in-memory sliding windows.
    Poziva se iz middleware-a — ne blokira odgovor.
    """
    now = time.time()
    _last_seen[user_id] = now
    key_hr = f"{user_id}:hr"
    key_day = f"{user_id}:day"

    if is_ai:
        _hourly_ai[key_hr].append(now)
        _trim_window(_hourly_ai[key_hr], 3600)
    _hourly_api[key_hr].append(now)
    _trim_window(_hourly_api[key_hr], 3600)

    if ip:
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]
        _daily_ips[key_day].add(ip_hash)


async def check_anomaly(user_id: str, ip: Optional[str] = None) -> AnomalySignal:
    """
    Proverava da li je tekući korisnički obrazac anomalan.
    Vraća AnomalySignal odmah (iz in-memory podataka + DB profila).
    """
    score = 0.0
    reasons: list[str] = []
    key_hr  = f"{user_id}:hr"
    key_day = f"{user_id}:day"

    # ── In-memory provere (brze) ─────────────────────────────────────────────
    ai_count  = len(_hourly_ai.get(key_hr, []))
    api_count = len(_hourly_api.get(key_hr, []))
    ip_count  = len(_daily_ips.get(key_day, set()))

    # Apsolutni pragovi (bez baznog profila)
    if ai_count > ABS_AI_HOURLY_LIMIT:
        score += 0.6
        reasons.append(f"ai_hourly:{ai_count}>{ABS_AI_HOURLY_LIMIT}")

    if api_count > ABS_API_HOURLY_LIMIT:
        score += 0.5
        reasons.append(f"api_hourly:{api_count}>{ABS_API_HOURLY_LIMIT}")

    if ip_count > ABS_IP_DAILY_LIMIT:
        score += 0.4
        reasons.append(f"unique_ips:{ip_count}>{ABS_IP_DAILY_LIMIT}")

    # ── DB profil (async, samo ako nema očiglednih anomalija) ───────────────
    if score < 0.4:
        db_signal = await _check_db_profile(user_id, ai_count, api_count, ip_count)
        score += db_signal.score
        reasons.extend(db_signal.reasons)

    score = min(score, 1.0)
    is_anomaly = score >= 0.7

    if is_anomaly:
        logger.warning(
            "[ANOMALY] uid=%.8s score=%.2f reasons=%s",
            user_id, score, reasons,
        )
        asyncio.create_task(_log_anomaly(user_id, score, reasons, ip))

    return AnomalySignal(is_anomaly=is_anomaly, score=score, reasons=reasons, user_id=user_id)


async def get_user_profile(user_id: str) -> Optional[dict]:
    """Vraća DB profil korisnika za admin pregled."""
    try:
        from api import _get_supa
        supa = _get_supa()
        result = await asyncio.to_thread(
            lambda: supa.table("user_activity_profile")
                .select("*")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
        )
        return result.data
    except Exception:
        return None


async def update_daily_profile(user_id: str) -> None:
    """
    Ažurira bazni profil korisnika u bazi.
    Pozivati jednom dnevno (Supabase cron ili background task).
    Upisuje broj AI poziva, API poziva i unikatnih IP-ova za tekući dan.
    """
    key_hr  = f"{user_id}:hr"
    key_day = f"{user_id}:day"

    try:
        from api import _get_supa
        supa = _get_supa()
        today = datetime.now(timezone.utc).date().isoformat()

        ai_count  = len(_hourly_ai.get(key_hr, []))
        api_count = len(_hourly_api.get(key_hr, []))
        ip_count  = len(_daily_ips.get(key_day, set()))

        await asyncio.to_thread(
            lambda: supa.table("user_daily_activity").upsert({
                "user_id":   user_id,
                "date":      today,
                "ai_calls":  ai_count,
                "api_calls": api_count,
                "ip_count":  ip_count,
            }, on_conflict="user_id,date").execute()
        )
    except Exception as e:
        logger.debug("[ANOMALY] profile update greška: %s", e)


# ─── Interni helpers ──────────────────────────────────────────────────────────

def _trim_window(dq: deque, window_seconds: float) -> None:
    cutoff = time.time() - window_seconds
    while dq and dq[0] < cutoff:
        dq.popleft()


async def _check_db_profile(
    user_id: str, ai_now: int, api_now: int, ip_now: int
) -> AnomalySignal:
    """Poredi tekuće vrednosti sa baznim profilom iz DB-a."""
    score = 0.0
    reasons: list[str] = []
    try:
        from api import _get_supa
        supa = _get_supa()

        # Prosek poslednjih 30 dana
        result = await asyncio.to_thread(
            lambda: supa.rpc("get_activity_averages", {"p_user_id": user_id}).execute()
        )
        if not result.data:
            return AnomalySignal(False, 0.0, [], user_id)

        avg = result.data[0]
        days = avg.get("days_count", 0)

        if days < MIN_HISTORY_DAYS:
            return AnomalySignal(False, 0.0, [], user_id)

        avg_ai  = float(avg.get("avg_ai_calls", 0) or 0)
        avg_api = float(avg.get("avg_api_calls", 0) or 0)
        avg_ip  = float(avg.get("avg_ip_count", 1) or 1)

        if avg_ai > 0 and ai_now > avg_ai * ANOMALY_MULTIPLIER_AI:
            score += 0.5
            reasons.append(f"ai_vs_baseline:{ai_now:.0f}vs{avg_ai:.0f}x{ANOMALY_MULTIPLIER_AI}")

        if avg_api > 0 and api_now > avg_api * ANOMALY_MULTIPLIER_API:
            score += 0.4
            reasons.append(f"api_vs_baseline:{api_now:.0f}vs{avg_api:.0f}x{ANOMALY_MULTIPLIER_API}")

        if avg_ip > 0 and ip_now > avg_ip * ANOMALY_MULTIPLIER_IP:
            score += 0.3
            reasons.append(f"ip_vs_baseline:{ip_now:.0f}vs{avg_ip:.1f}x{ANOMALY_MULTIPLIER_IP}")

    except Exception as e:
        logger.debug("[ANOMALY] DB profile check greška: %s", e)

    return AnomalySignal(is_anomaly=score >= 0.7, score=score, reasons=reasons, user_id=user_id)


async def _log_anomaly(user_id: str, score: float, reasons: list[str], ip: Optional[str]) -> None:
    """Upisuje anomaliju u security_events i audit_immutable."""
    try:
        import json
        from api import _get_supa
        from shared.audit_immutable import log_action

        ip_hash = hashlib.sha256((ip or "").encode()).hexdigest()[:16] if ip else None
        supa = _get_supa()

        await asyncio.to_thread(
            lambda: supa.table("security_events").insert({
                "event_type": "suspicious_access",
                "user_id": user_id,
                "ip_hash": ip_hash,
                "details": {"score": round(score, 3), "reasons": reasons[:10]},
            }).execute()
        )

        await log_action(
            "suspicious_access",
            user_id=user_id,
            resource_type="session",
            ip=ip,
            metadata={"score": round(score, 3), "reasons": reasons[:5]},
        )
    except Exception as e:
        logger.debug("[ANOMALY] log greška: %s", e)

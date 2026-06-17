# -*- coding: utf-8 -*-
"""
Vindex AI — shared/deps.py

Sve deljene zavisnosti: Supabase konekcija, JWT autentifikacija, kredit sistem,
FastAPI dependency funkcije (get_current_user, require_credits, require_pro),
i audit log helperi.

Importuje se od api.py i svih router modula. NE importuje ništa iz api.py
da ne bi nastala cirkularna zavisnost.
"""
from __future__ import annotations

import asyncio
import hashlib as _hashlib
import logging
import os
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt as jose_jwt, JWTError
from supabase import create_client, Client as SupabaseClient

logger = logging.getLogger("vindex.api")

# ─── Supabase ────────────────────────────────────────────────────────────────
SUPABASE_URL         = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
SUPABASE_JWT_SECRET  = os.getenv("SUPABASE_JWT_SECRET", "").strip()

# Founder emailovi — neograničen pristup, krediti se ne oduzimaju
_founder_emails_raw = os.getenv("FOUNDER_EMAILS", "")
if not _founder_emails_raw.strip():
    raise RuntimeError(
        "FOUNDER_EMAILS env var must be set — add comma-separated founder emails to .env"
    )
FOUNDER_EMAILS: set[str] = {
    e.strip().lower()
    for e in _founder_emails_raw.split(",")
    if e.strip()
}

# PRO korisnici — pristup modulu za podneske i budućim PRO funkcijama
PRO_EMAILS: set[str] = FOUNDER_EMAILS | {
    e.strip().lower()
    for e in os.getenv("PRO_EMAILS", "").split(",")
    if e.strip()
}

BESPLATNI_KREDITI     = 15
BASIC_MESECNI_KREDITI = 200
PRO_MESECNI_KREDITI   = 600

# In-memory mesečna upotreba: {user_id: {"month": "YYYY-MM", "count": N}}
_mesecna_upotreba: dict[str, dict] = {}


def _is_founder(email: str) -> bool:
    return (email or "").lower() in FOUNDER_EMAILS


def _is_pro(email: str, is_pro_db: bool = False) -> bool:
    """PRO status: founder, PRO_EMAILS lista, ili is_pro=true u Supabase profiles."""
    return is_pro_db or (email or "").lower() in PRO_EMAILS


# ─── Supabase klijent ────────────────────────────────────────────────────────
_supa: Optional[SupabaseClient] = None


def _get_supa() -> SupabaseClient:
    global _supa
    if _supa is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise RuntimeError(
                "SUPABASE_URL i SUPABASE_SERVICE_KEY moraju biti postavljeni u .env fajlu."
            )
        logger.info("Supabase init: URL=%r", SUPABASE_URL)
        _supa = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _supa


# ─── Provera jednokratnih email adresa ───────────────────────────────────────
DISPOSABLE_DOMAINS = {
    "mailinator.com", "tempmail.com", "guerrillamail.com", "throwaway.email",
    "10minutemail.com", "yopmail.com", "sharklasers.com", "grr.la",
    "guerrillamail.info", "guerrillamail.biz", "guerrillamail.de",
    "guerrillamail.net", "guerrillamail.org", "spam4.me", "trashmail.com",
    "trashmail.me", "trashmail.net", "trashmail.org", "dispostable.com",
    "mailnull.com", "maildrop.cc", "spamgourmet.com", "fakeinbox.com",
    "mailnesia.com", "spaml.com", "getairmail.com", "fakemailgenerator.com",
    "mailbucket.org", "filzmail.com", "gishpuppy.com", "inoutmail.de",
    "noemail.com", "throwam.com", "temp-mail.org", "tempr.email",
    "discard.email", "burnermail.io", "tempinbox.com", "emailondeck.com",
    "nada.email", "spamex.com", "mailtemp.info", "tmpmail.org",
    "mytemp.email", "tempmailo.com", "spoofmail.de", "mailnew.com",
}


def _is_disposable_email(email: str) -> bool:
    domain = email.split("@")[-1].lower() if "@" in email else ""
    return domain in DISPOSABLE_DOMAINS


# ─── JWT autentifikacija ──────────────────────────────────────────────────────
security = HTTPBearer(auto_error=False)


_JWKS_CACHE: dict = {"keys": None, "fetched_at": 0.0}
_JWKS_TTL_S = 3600  # 1h cache

_JWKS_HARDCODED = {
    "alg": "ES256", "crv": "P-256", "kty": "EC", "use": "sig",
    "kid": "34474d56-eee6-41ed-a78d-4490889d6111",
    "x": "StfqNCxcMFEJ--teLZgJtrF-wyQOyFZPwAakAvRf_Pg",
    "y": "oZmdFqo0HMJD5iLXvjmQ8Golb61P-X71m5bO9zDf8gc",
}


def _get_jwks_key(alg: str) -> Optional[dict]:
    """Fetch JWKS from Supabase with 1h cache. Falls back to hardcoded key."""
    import time as _time
    now = _time.monotonic()
    if _JWKS_CACHE["keys"] is None or (now - _JWKS_CACHE["fetched_at"]) > _JWKS_TTL_S:
        try:
            import urllib.request as _ur, json as _jj
            url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
            with _ur.urlopen(url, timeout=3) as r:
                data = _jj.loads(r.read())
            _JWKS_CACHE["keys"] = data.get("keys", [])
            _JWKS_CACHE["fetched_at"] = now
            logger.info("[JWKS] Refreshed %d keys from Supabase", len(_JWKS_CACHE["keys"]))
        except Exception as e:
            logger.warning("[JWKS] Fetch failed, using hardcoded key: %s", e)
            if _JWKS_CACHE["keys"] is None:
                _JWKS_CACHE["keys"] = [_JWKS_HARDCODED]

    keys = _JWKS_CACHE.get("keys") or [_JWKS_HARDCODED]
    # Prefer key matching alg, fallback to first key
    for k in keys:
        if k.get("alg", "") == alg or k.get("kty", "") in ("EC", "RSA"):
            return k
    return keys[0] if keys else _JWKS_HARDCODED


def _jwt_alg(token: str) -> str:
    """Čita 'alg' iz JWT headera bez verifikacije."""
    try:
        import base64 as _b64, json as _jh
        part = token.split(".")[0]
        part += "=" * (4 - len(part) % 4)
        return _jh.loads(_b64.b64decode(part)).get("alg", "HS256")
    except Exception:
        return "HS256"


def _verify_token(token: str) -> Optional[dict]:
    """
    Verifikuje Supabase token:
    1. Supabase Python SDK (get_user) — najrobusnije
    2. Lokalni JWT decode (HS256 ili RS256 via JWKS)
    """
    if not token:
        return None

    # Korak 1: Supabase Python SDK
    try:
        supa = _get_supa()
        resp = supa.auth.get_user(token)
        logger.info("SDK get_user resp: %s", resp)
        if resp and resp.user and resp.user.id:
            return {
                "sub":   resp.user.id,
                "email": resp.user.email or "",
            }
        logger.warning("SDK get_user: resp.user prazan — %s", resp)
    except Exception as e:
        logger.warning("Supabase SDK get_user neuspešno: %s", e)

    alg = _jwt_alg(token)
    logger.info("JWT algoritam: %s", alg)

    # Korak 2a: HS256 sa JWT_SECRET
    if alg == "HS256" and SUPABASE_JWT_SECRET:
        try:
            payload = jose_jwt.decode(
                token, SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
            if payload.get("sub"):
                return payload
        except JWTError as e:
            logger.warning("HS256 decode greška: %s", e)

    # Korak 2b: ES256/RS256 — dinamičan JWKS fetch sa 1h cache, fallback na hardkod
    if alg in ("RS256", "ES256"):
        from jose import jwk as jose_jwk
        jwk_to_try = _get_jwks_key(alg)
        if jwk_to_try:
            try:
                pub = jose_jwk.construct(jwk_to_try)
                payload = jose_jwt.decode(
                    token, pub,
                    algorithms=[alg],
                    options={"verify_aud": False},
                )
                if payload.get("sub"):
                    return payload
                logger.warning("JWKS decode OK ali nema sub")
            except JWTError as e:
                logger.warning("JWKS decode greška: %s", e)

    logger.warning("_verify_token: svi koraci neuspešni — vraćam None")
    return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """FastAPI dependency — verifikuje token i vraća korisničke podatke."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Prijava je obavezna za korišćenje Vindex AI.",
        )
    payload = await asyncio.to_thread(_verify_token, credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vaša sesija je istekla. Prijavite se ponovo.",
        )
    email = (
        payload.get("email")
        or payload.get("user_metadata", {}).get("email")
        or payload.get("email_claim")
        or ""
    )
    logger.info("get_current_user: sub=%s email=%s", payload.get("sub", "?")[:8], email)
    return {"user_id": payload.get("sub"), "email": email}


# ─── Kredit sistem ────────────────────────────────────────────────────────────
def _get_current_month() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m")


def _get_monthly_usage(user_id: str) -> int:
    entry = _mesecna_upotreba.get(user_id, {})
    if entry.get("month") != _get_current_month():
        return 0
    return entry.get("count", 0)


def _increment_monthly_usage(user_id: str) -> None:
    month = _get_current_month()
    entry = _mesecna_upotreba.get(user_id, {})
    if entry.get("month") != month:
        _mesecna_upotreba[user_id] = {"month": month, "count": 1}
    else:
        _mesecna_upotreba[user_id] = {"month": month, "count": entry.get("count", 0) + 1}


def _ensure_profile(user_id: str, email: str = "") -> dict:
    """
    Čita kredite iz user_credits i PRO status iz profiles.
    Auto-heal: kreira user_credits red sa 15 kredita ako ne postoji.
    Vraća dict: { credits_remaining, is_pro }
    """
    supa = _get_supa()

    # ── Korak 1: credits iz user_credits ──────────────────────────────────────
    credits_remaining: int = 0
    try:
        credits_res = (
            supa.table("user_credits")
            .select("credits_remaining")
            .eq("user_id", user_id)
            .execute()
        )
        credits_rows = credits_res.data or []
        if credits_rows:
            credits_remaining = credits_rows[0].get("credits_remaining", 0)
            logger.debug("[CREDITS] uid=%.8s credits=%d", user_id, credits_remaining)
        else:
            logger.warning(
                "[CREDITS] user_credits red ne postoji za uid=%.8s — auto-heal: upisujem 15",
                user_id,
            )
            supa.table("user_credits").insert(
                {"user_id": user_id, "credits_remaining": BESPLATNI_KREDITI}
            ).execute()
            credits_remaining = BESPLATNI_KREDITI
    except Exception as exc:
        logger.error(
            "[CREDITS] GREŠKA pri čitanju user_credits za uid=%.8s — %s: %r\n"
            "  >>> Proverite da li je supabase_setup.sql pokrenut u Supabase Dashboard! <<<",
            user_id, type(exc).__name__, str(exc)[:300],
        )

    # ── Korak 2: is_pro iz profiles ───────────────────────────────────────────
    is_pro_db = False
    try:
        profile_res = (
            supa.table("profiles")
            .select("is_pro")
            .eq("id", user_id)
            .execute()
        )
        is_pro_db = bool((profile_res.data or [{}])[0].get("is_pro", False))
    except Exception as exc:
        logger.warning(
            "[PROFILE] GREŠKA pri čitanju profiles za uid=%.8s — %s: %r",
            user_id, type(exc).__name__, str(exc)[:200],
        )

    return {"credits_remaining": credits_remaining, "is_pro": _is_pro(email, is_pro_db)}


def _get_credits(user_id: str) -> int:
    """Čita broj preostalih kredita iz baze."""
    return _ensure_profile(user_id).get("credits_remaining", 0)


def _deduct_credit(user_id: str, email: str = "") -> int:
    """Atomično oduzima jedan kredit. Founder nikad ne gubi kredit."""
    if _is_founder(email):
        return 9999
    try:
        result = _get_supa().rpc("deduct_credit", {"p_user_id": user_id}).execute()
        _increment_monthly_usage(user_id)
        return result.data if result.data is not None else -1
    except Exception:
        logger.exception("Greška pri oduzimanju kredita za korisnika %s", user_id)
        return -1


def _sb_get_credits(user_id: str) -> int:
    """Read credits_remaining from Supabase. Returns 0 if row missing."""
    try:
        res = (
            _get_supa()
            .table("user_credits")
            .select("credits_remaining")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        return res.data["credits_remaining"] if res.data else 0
    except Exception as e:
        logger.error("[CREDITS] _sb_get_credits error for uid=%.8s: %s", user_id, e)
        return 0


def _sb_deduct_credit(user_id: str) -> int:
    """Atomically deduct 1 credit via RPC. Returns new balance. Founder guard not here — use _deduct_credit for endpoint calls."""
    try:
        result = _get_supa().rpc("deduct_credit", {"p_user_id": user_id}).execute()
        _increment_monthly_usage(user_id)
        return result.data if result.data is not None else 0
    except Exception as e:
        logger.error("[CREDITS] _sb_deduct_credit error for uid=%.8s: %s", user_id, e)
        return 0


def _sb_ensure_credits_row(user_id: str, initial: int = 15) -> None:
    """Create user_credits row if it doesn't exist (ignore_duplicates=True → never resets existing balance)."""
    try:
        _get_supa().table("user_credits").upsert(
            {"user_id": user_id, "credits_remaining": initial},
            on_conflict="user_id",
            ignore_duplicates=True,
        ).execute()
    except Exception as e:
        logger.error("[CREDITS] _sb_ensure_credits_row error for uid=%.8s: %s", user_id, e)


def _deduct_n_credits(user_id: str, email: str, n: int) -> int:
    """Atomically deduct n credits. Founder guard applied."""
    if _is_founder(email):
        return 9999
    try:
        result = _get_supa().rpc("deduct_n_credits", {"p_user_id": user_id, "p_n": n}).execute()
        _increment_monthly_usage(user_id)
        return result.data if result.data is not None else 0
    except Exception:
        logger.exception("[F12] Greška pri oduzimanju %d kredita za uid=%s", n, user_id)
        return 0


def _refund_one_credit(user_id: str) -> None:
    """Refund 1 credit (e.g. cache hit pre-deducted). Best-effort — never raises."""
    try:
        _get_supa().rpc("refund_one_credit", {"p_user_id": user_id}).execute()
    except Exception:
        # Fallback: raw increment if RPC not found
        try:
            supa = _get_supa()
            cur = supa.table("user_credits").select("credits_remaining").eq("user_id", user_id).single().execute()
            if cur.data:
                supa.table("user_credits").update({
                    "credits_remaining": cur.data["credits_remaining"] + 1
                }).eq("user_id", user_id).execute()
        except Exception as e2:
            logger.warning("[CREDITS] _refund_one_credit fallback failed uid=%.8s: %s", user_id, e2)


async def require_credits(user: dict = Depends(get_current_user)) -> dict:
    """Dependency koji atomično proverava I oduzima 1 kredit. Founder uvek prolazi."""
    email = user.get("email", "")
    logger.info("require_credits: email=%s is_founder=%s", email, _is_founder(email))
    if _is_founder(email):
        user["credits_remaining"] = 9999
        user["credit_pre_deducted"] = False
        return user

    # Mesečni limit (PRO: 600, Basic/Free: 200 — Free korisnici su stopiran ranije, na 15)
    is_pro_user = _is_pro(email)
    monthly_limit = PRO_MESECNI_KREDITI if is_pro_user else BASIC_MESECNI_KREDITI
    monthly_used  = _get_monthly_usage(user["user_id"])
    if monthly_used >= monthly_limit:
        if is_pro_user:
            msg = (f"Iskoristili ste {PRO_MESECNI_KREDITI} mesečnih pitanja. "
                   "Kontaktirajte nas za Firm plan.")
        else:
            msg = (f"Iskoristili ste {BASIC_MESECNI_KREDITI} mesečnih pitanja. "
                   "Pređite na PRO za 600 pitanja mesečno.")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={"code": "MONTHLY_LIMIT", "message": msg, "credits_remaining": 0},
        )

    # Atomično pre-deductuj 1 kredit — eliminiše race condition na concurrent zahteve.
    # deduct_credit RPC je atomic na DB nivou: second concurrent request dobija -1.
    preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], email)
    if preostalo < 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "NO_CREDITS",
                "message": (
                    "Iskoristili ste besplatne upite. "
                    "Pređite na Basic paket (19€) za neograničen pristup."
                ),
                "credits_remaining": 0,
            },
        )
    user["credits_remaining"] = preostalo
    user["credit_pre_deducted"] = True
    return user


async def require_pro(user: dict = Depends(get_current_user)) -> dict:
    """Dependency — blokira pristup ako korisnik nije PRO."""
    profil = await asyncio.to_thread(_ensure_profile, user["user_id"], user.get("email", ""))
    if not profil["is_pro"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ova funkcija zahteva PRO pretplatu. Nadogradite nalog na VindexAI PRO.",
        )
    user["is_pro"] = True
    return user


# ─── Audit log ────────────────────────────────────────────────────────────────

def _q_hash(tekst: str) -> str:
    """SHA-256 (16 hex) od pitanja — za log bez curenja sadržaja."""
    return _hashlib.sha256((tekst or "").encode()).hexdigest()[:16]


async def _audit(user_id: str, akcija: str, q_hash: str) -> None:
    """
    Beleži pristup bez čuvanja sadržaja: ko + kada + šta (hash).
    ZZPL čl. 5(1)(f) — integritet i poverljivost.
    Fire-and-forget — greška u audit-u ne blokira odgovor.
    """
    try:
        await asyncio.to_thread(
            lambda: _get_supa().table("audit_log").insert({
                "user_id": user_id,
                "akcija": akcija,
                "q_hash": q_hash,
            }).execute()
        )
    except Exception:
        logger.warning("Audit log neuspešan — ne blokira odgovor")

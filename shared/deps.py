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
import threading
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt as jose_jwt, JWTError
from supabase import create_client, Client as SupabaseClient

# NS001/FAZA 1 — `maybe_single()` u postgrest 2.28.3 vraća `None` na 0 redova,
# a 201 mesta u ovom kodu odmah čita `.data`, pa umesto 404 daju HTTP 500.
# Ugovor se vraća na jednom mestu, ovde, jer je `shared/deps.py` kanonski ulaz u
# bazu i uvozi ga svaki produkcijski put. Detalji i merenja: shared/postgrest_compat.py
from shared.postgrest_compat import primeni as _primeni_pgrst_compat

_primeni_pgrst_compat()

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
# BLACKSWAN-HIGH-001 (Operation Black Swan, Mission 001, Scenario 1): the check-then-set
# below is atomic only when every caller runs on the main asyncio event loop thread. 42+
# call sites invoke _get_supa() from INSIDE an asyncio.to_thread(...) lambda, which runs
# on a real OS thread from the default ThreadPoolExecutor -- there the check-then-set is
# NOT atomic. Reproduced: a cold worker + 50 real concurrent threads produced 50 separate
# create_client() calls / 50 distinct client objects instead of 1, under exactly the "many
# lawyers hit a just-started worker" scenario this mission names. A plain threading.Lock
# is correct and cheap here -- this function is called on both asyncio-loop and worker-
# thread call sites, so an asyncio.Lock would not protect the thread-pool callers at all.
_supa_lock = threading.Lock()


def _get_supa() -> SupabaseClient:
    global _supa
    if _supa is None:
        with _supa_lock:
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


def verify_token_local(token: str) -> Optional[dict]:
    """
    Lokalna, kriptografski verifikovana JWT provera — BEZ Supabase SDK network
    poziva (nasuprot `_verify_token`, koja prvo pokušava `supa.auth.get_user`).

    SEC-005 (2026-07-24): izdvojeno iz `_verify_token`-a da bi moglo da se
    pozove iz `api.py`'s `user_rate_limit_middleware`-a za per-user rate
    limit bucketing, bez udvostručavanja mrežnog poziva ka Supabase-u na
    SVAKI /api/* zahtev (JWKS fetch je keširan 1h u `_get_jwks_key`, pa ni
    RS256/ES256 grana ne udara mrežu po zahtevu u praksi).

    Signature verifikacija (HS256 sa JWT_SECRET, ili RS256/ES256 preko JWKS)
    znači da ovo NIJE naivan, nepotvrđen decode — token sa falsifikovanim
    `sub` claim-om ovde ne prolazi, isto kao ni u `_verify_token`-u. Razlika
    je samo u tome što ovde nema Supabase-ovog live revocation/session
    check-a — dovoljno za rate-limit bucketing (koje korisničke pozive
    grupisati), NE dovoljno za autorizaciju (to i dalje radi isključivo
    `get_current_user` niže u lancu, na nivou svake zaštićene rute).
    """
    if not token:
        return None

    alg = _jwt_alg(token)

    # HS256 sa JWT_SECRET
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
            logger.debug("verify_token_local: HS256 decode greška: %s", e)

    # ES256/RS256 — dinamičan JWKS fetch sa 1h cache, fallback na hardkod
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
                logger.debug("verify_token_local: JWKS decode OK ali nema sub")
            except JWTError as e:
                logger.debug("verify_token_local: JWKS decode greška: %s", e)

    return None


def _verify_token(token: str) -> Optional[dict]:
    """
    Verifikuje Supabase token:
    1. Supabase Python SDK (get_user) — najrobusnije
    2. Lokalni JWT decode (HS256 ili RS256 via JWKS) — `verify_token_local`
    """
    if not token:
        return None

    # Korak 1: Supabase Python SDK
    try:
        supa = _get_supa()
        resp = supa.auth.get_user(token)
        if resp and resp.user and resp.user.id:
            return {
                "sub":   resp.user.id,
                "email": resp.user.email or "",
            }
        logger.warning("SDK get_user: resp.user prazan — %s", resp)
    except Exception as e:
        logger.warning("Supabase SDK get_user neuspešno: %s", e)

    # Korak 2: lokalni decode (HS256 ili JWKS)
    payload = verify_token_local(token)
    if payload:
        return payload

    logger.warning("_verify_token: svi koraci neuspešni — vraćam None")
    return None


def email_iz_tokena(payload: Optional[dict]) -> str:
    """B-U-007 — JEDINA dozvoljena granica poverenja za identitet iz tokena.

    Email izveden ovom funkcijom odlučuje o osnivačkim i admin privilegijama
    (`FOUNDER_EMAILS`, `PRO_EMAILS`, `_require_admin`, `_require_founder`,
    `_is_founder`, `klijenti/permissions.py::_role_from_db`). Zato sme da
    dolazi ISKLJUČIVO iz server-kontrolisanog izvora.

    ŠTA JE POUZDANO — `payload["email"]`:
      • na SDK putanji (`supa.auth.get_user`) `_verify_token` ga sintetiše iz
        `resp.user.email`, tj. iz kolone `auth.users.email`;
      • na lokalnoj putanji (`verify_token_local`) to je top-level claim koji
        Supabase upisuje iz iste kolone i kriptografski potpisuje.
      Korisnik tu vrednost ne može da promeni bez verifikovanog email-change
      toka — dakle menja je server, ne klijent.

    ŠTA NIJE POUZDANO I ZATO VIŠE NE ULAZI U ODLUKU:
      • `user_metadata.email` — piše ga sam korisnik pozivom
        `supabase.auth.updateUser({data: {...}})`. Izmereno nad sintetičkim
        nalogom 2026-08-22: običan korisnik je upisao osnivački email i ta
        vrednost se pojavila u POTPISANOM tokenu. Potpis dokazuje da token
        nije falsifikovan — NE dokazuje da je sadržaj polja istinit.
      • `email_claim` — nestandardan ključ koji nijedno mesto u repou ne
        upisuje; kao fallback bi bio samo još jedan otvoren ulaz.

    FAIL-CLOSED: kad pouzdanog email-a nema, vraća se `""`. Prazan string nije
    ni u `FOUNDER_EMAILS` ni u `PRO_EMAILS` (prazne vrednosti se filtriraju pri
    učitavanju), pa je ishod DENY — nikad „best effort" privilegija.
    """
    if not isinstance(payload, dict):
        return ""
    email = payload.get("email")
    if not isinstance(email, str):
        return ""
    return email.strip()


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if not request or not request.client:
        return None
    return request.client.host


async def _log_login_failed(reason: str, request: Optional[Request], token_prefix: str = "") -> None:
    """CELINA 5 (2026-07-24): telemetrija za neuspele logine — 'login_failed' je
    bio definisan u AUDITABLE_ACTIONS (shared/audit_immutable.py) od ranije, ali
    nijedno mesto u kodu ga nikad nije pozivalo. Fire-and-forget, nikad ne sme
    da uspori ili blokira 401 odgovor."""
    try:
        from shared.audit_immutable import log_action
        ip = _client_ip(request)
        await log_action(
            "login_failed",
            resource_type="session",
            ip=ip,
            metadata={"reason": reason, "token_prefix": token_prefix},
        )
    except Exception as e:
        logger.debug("[AUTH] login_failed audit greška (nije kritično): %s", e)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """FastAPI dependency — verifikuje token i vraća korisničke podatke."""
    if not credentials:
        asyncio.create_task(_log_login_failed("no_credentials", request))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Prijava je obavezna za korišćenje Vindex AI.",
        )
    payload = await asyncio.to_thread(_verify_token, credentials.credentials)
    if not payload:
        asyncio.create_task(
            _log_login_failed("invalid_or_expired_token", request, credentials.credentials[:12])
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vaša sesija je istekla. Prijavite se ponovo.",
        )
    # B-U-007: identitet koji odlucuje o privilegiji dolazi SAMO iz
    # server-kontrolisanog claim-a. v. shared/deps.py::email_iz_tokena
    email = email_iz_tokena(payload)
    logger.debug("get_current_user: sub=%s email=%s", payload.get("sub", "?")[:8], email)
    # Mission Atlas (2026-08-03) — AI Provenance request context. Every
    # Depends(get_current_user)-protected endpoint already resolves the user
    # here; stamping it into shared/ai_provenance.py's request-scoped
    # contextvar lets the canonical AI wrapper (shared/ai_client.py) attach
    # "who triggered this AI call" without any of the ~130 AI call sites
    # needing to pass user_id through explicitly.
    try:
        from shared.ai_provenance import set_request_context, current_correlation_id
        # Program Alpha (2026-08-04): reuse the correlation_id
        # api.py::correlation_id_middleware already set for this request
        # (it runs earlier, before this dependency resolves) instead of
        # overwriting it with a freshly-minted one -- set_request_context()
        # replaces the whole context dict, so omitting this would silently
        # orphan the id already returned to the client in the
        # X-Correlation-ID response header.
        set_request_context(user_id=payload.get("sub"), correlation_id=current_correlation_id())
    except Exception:
        pass
    return {"user_id": payload.get("sub"), "email": email}


# ─── Kredit sistem ────────────────────────────────────────────────────────────
def _get_current_month() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m")


def _get_monthly_usage(user_id: str) -> int:
    month = _get_current_month()
    try:
        row = _get_supa().table("user_credits") \
            .select("mesecno_korisceno, mesec") \
            .eq("user_id", user_id) \
            .maybe_single() \
            .execute()
        if row.data and row.data.get("mesec") == month:
            return row.data.get("mesecno_korisceno", 0)
    except Exception:
        entry = _mesecna_upotreba.get(user_id, {})
        if entry.get("month") == month:
            return entry.get("count", 0)
    return 0


def _increment_monthly_usage(user_id: str) -> None:
    month = _get_current_month()
    try:
        # P1-C (2026-08-08): this was a SELECT-then-UPDATE. Two charges landing
        # together both read the same mesecno_korisceno and both wrote read+1,
        # so one of them vanished -- a lost update on a quota counter, executing
        # on every AI request in the product (this runs inside _deduct_n_credits,
        # which is underneath every UsageService.consume call).
        #
        # migrations/108_atomic_usage_counters.sql shipped increment_monthly_usage
        # precisely to close this, but the Python caller was never switched over,
        # so the fix sat unused in the database. It does the whole read-add-write
        # in one statement, including the month rollover.
        res = _get_supa().rpc("increment_monthly_usage", {
            "p_user_id": user_id,
            "p_mesec":   month,
        }).execute()
        # The RPC returns -1 when the user has no user_credits row. That is the
        # same condition the old code's `if row.data:` handled by falling
        # through to the in-memory counter, so keep falling through -- treating
        # -1 as success would silently stop counting those users entirely.
        if isinstance(res.data, int) and res.data >= 0:
            return
    except Exception as e:
        logger.warning("[CREDITS] _increment_monthly_usage RPC failed: %s", e)
    # Fallback na in-memory ako DB padne
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
    # Jedan retry na prolaznu grešku baze — bez njega, jedan mrežni hiccup
    # izgleda korisniku identično kao "potrošeni krediti" (lažan paywall).
    credits_remaining: int = 0
    _read_ok = False
    for _attempt in (1, 2):
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
            _read_ok = True
            break
        except Exception as exc:
            if _attempt == 1:
                logger.warning(
                    "[CREDITS] uid=%.8s pokušaj 1/2 neuspešan (%s) — ponavljam odmah",
                    user_id, type(exc).__name__,
                )
                continue
            logger.error(
                "[CREDITS] GREŠKA pri čitanju user_credits za uid=%.8s — %s: %r\n"
                "  >>> Proverite da li je supabase_setup.sql pokrenut u Supabase Dashboard! <<<",
                user_id, type(exc).__name__, str(exc)[:300],
            )
    if not _read_ok:
        raise HTTPException(
            status_code=503,
            detail="Trenutno ne možemo proveriti vaše kredite. Pokušajte ponovo za par sekundi.",
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

    # ── Korak 3: digitalna_imovina_aktivirano — odvojen, izolovan poziv (ne sme
    # da obori is_pro čitanje ako migracija 060 još nije pokrenuta na serveru) ─
    digitalna_imovina_aktivirano = False
    try:
        dim_res = (
            supa.table("profiles")
            .select("digitalna_imovina_aktivirano")
            .eq("id", user_id)
            .execute()
        )
        digitalna_imovina_aktivirano = bool((dim_res.data or [{}])[0].get("digitalna_imovina_aktivirano", False))
    except Exception as exc:
        logger.debug(
            "[PROFILE] digitalna_imovina_aktivirano nije dostupno za uid=%.8s (migracija 060?) — %s",
            user_id, type(exc).__name__,
        )

    # ── Korak 4: digitalna_imovina_standalone — isto izolovano (migracija 062) ──
    digitalna_imovina_standalone = False
    try:
        dim_sa_res = (
            supa.table("profiles")
            .select("digitalna_imovina_standalone")
            .eq("id", user_id)
            .execute()
        )
        digitalna_imovina_standalone = bool((dim_sa_res.data or [{}])[0].get("digitalna_imovina_standalone", False))
    except Exception as exc:
        logger.debug(
            "[PROFILE] digitalna_imovina_standalone nije dostupno za uid=%.8s (migracija 062?) — %s",
            user_id, type(exc).__name__,
        )

    # ── Korak 5: entitlement sistem — subscription_type/addons/expires_at/seats
    # (migracija 063) — izolovano, isti bezbedan pattern kao gornji koraci ──────
    subscription_type = "basic"
    addons: list = []
    subscription_expires_at = None
    subscription_seats_extra = 0
    try:
        sub_res = (
            supa.table("profiles")
            .select("subscription_type, addons, subscription_expires_at, subscription_seats_extra")
            .eq("id", user_id)
            .execute()
        )
        row = (sub_res.data or [{}])[0]
        subscription_type = row.get("subscription_type") or "basic"
        addons = row.get("addons") or []
        subscription_expires_at = row.get("subscription_expires_at")
        subscription_seats_extra = row.get("subscription_seats_extra") or 0
    except Exception as exc:
        logger.debug(
            "[PROFILE] entitlement kolone nisu dostupne za uid=%.8s (migracija 063?) — %s",
            user_id, type(exc).__name__,
        )

    return {
        "credits_remaining": credits_remaining,
        "is_pro": _is_pro(email, is_pro_db),
        "digitalna_imovina_aktivirano": digitalna_imovina_aktivirano,
        "digitalna_imovina_standalone": digitalna_imovina_standalone,
        "subscription_type": subscription_type,
        "addons": addons,
        "subscription_expires_at": subscription_expires_at,
        "subscription_seats_extra": subscription_seats_extra,
    }


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
    """Atomically deduct n credits. Founder guard applied.

    Returns -1 when the deduction did NOT happen (insufficient balance per
    the RPC's own WHERE guard, or the RPC call itself failed) — callers
    MUST treat any negative return as "not charged", never as a valid
    balance. Monthly usage is only incremented when the deduction actually
    succeeded, so a rejected/failed deduction doesn't count against limits.
    """
    if _is_founder(email):
        return 9999
    try:
        result = _get_supa().rpc("deduct_n_credits", {"p_user_id": user_id, "p_n": n}).execute()
        new_balance = result.data if result.data is not None else -1
        if new_balance is not None and new_balance >= 0:
            _increment_monthly_usage(user_id)
        return new_balance
    except Exception:
        # CREDIT-LOSTREPLY-003 (MEDIUM, adversarial review 2026-08-08): this
        # cannot distinguish "the charge never executed" from "the charge
        # COMMITTED but the reply was lost" (connection reset, PostgREST
        # timeout). It must pick one, and failing CLOSED is correct -- the
        # alternative would deliver paid work on an unknown billing state.
        # But the second case silently bills the user for nothing, so it is
        # logged on its own marker for manual reconciliation rather than
        # folded into generic error noise. Closing this properly needs an
        # idempotency key on the charge, which the product deliberately does
        # not have (see test_retry_charges_twice_by_design_and_stays_consistent).
        logger.exception(
            "[CREDIT_RECONCILE] deduct_n_credits RPC raised for uid=%s n=%d -- treating as NOT "
            "charged and failing closed; if the transaction actually committed the user was "
            "billed without delivery and needs manual reconciliation", user_id, n,
        )
        return -1


def _refund_n_credits(user_id: str, n: int) -> int:
    """Atomically refund n credits (compensating transaction after a charged
    operation failed downstream). Best-effort — never raises.

    Returns the new balance, or -1 if nothing was refunded.

    Migration 107 defines refund_n_credits as a single-statement increment, so
    concurrent refunds — and a refund racing a deduction — cannot lose an
    update.
    """
    if n <= 0:
        return -1
    try:
        result = _get_supa().rpc("refund_n_credits", {"p_user_id": user_id, "p_n": int(n)}).execute()
        return result.data if result.data is not None else -1
    except Exception as exc:
        # Beta Gate Blocker Closure (2026-08-08): this used to fall back to a
        # read-modify-write (SELECT credits_remaining -> UPDATE value+1), which
        # is a lost-update race. Worse than losing a refund: a refund that read
        # the balance BEFORE a concurrent charge would write that stale value
        # back and erase the charge entirely -- free AI usage through the
        # refund door. A failed refund under-credits the user (bounded, and
        # loudly logged); a racy refund can silently corrupt the balance. The
        # fallback is therefore deliberately gone, not replaced.
        logger.error(
            "[CREDITS] refund_n_credits RPC failed uid=%.8s n=%d -- credits NOT refunded "
            "(migration 107 applied?): %s", user_id, n, exc,
        )
        return -1


def _refund_one_credit(user_id: str) -> None:
    """Refund 1 credit (e.g. cache hit pre-deducted). Best-effort — never raises."""
    _refund_n_credits(user_id, 1)


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
                   "Kontaktirajte nas za Kancelarija plan.")
        else:
            msg = (f"Iskoristili ste {BASIC_MESECNI_KREDITI} mesečnih pitanja. "
                   f"Pređite na PRO za {PRO_MESECNI_KREDITI} pitanja mesečno.")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={"code": "MONTHLY_LIMIT", "message": msg, "credits_remaining": 0},
        )

    # Atomično pre-deductuj 1 kredit — eliminiše race condition na concurrent zahteve.
    #
    # CREDIT-CONSUME-001 (CRITICAL, adversarial review 2026-08-08): the
    # comment here used to claim "deduct_credit RPC je atomic na DB nivou:
    # second concurrent request dobija -1". The UPDATE is atomic, but the
    # claim about -1 is FALSE for the deployed body: production's
    # deduct_credit ends its NOT-FOUND branch with
    # `RETURN COALESCE(new_credits, 0)` (supabase_setup.sql:139), so it
    # returns the current balance and never a negative -- making the
    # `preostalo < 0` check below unreachable, exactly as in
    # UsageService.consume. This dependency currently has ZERO
    # `Depends(require_credits)` call sites (verified by grep), so it was
    # never live, but it is left correct rather than left as a trap for
    # whoever re-adopts it. Routed through the one primitive whose contract
    # is defined and tested (migration 107): >=0 charged, -1 not charged.
    preostalo = await asyncio.to_thread(_deduct_n_credits, user["user_id"], email, 1)
    if preostalo < 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "NO_CREDITS",
                "message": (
                    "Iskoristili ste besplatne upite. "
                    "Pređite na PRO paket za mnogo više upita mesečno."
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

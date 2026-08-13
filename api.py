# -*- coding: utf-8 -*-
"""
Vindex AI — FastAPI server sa Supabase autentifikacijom i kreditnim sistemom
"""

import logging
import os
import asyncio
import threading
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Request, Depends, HTTPException, status, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

BASE_DIR = Path(__file__).parent
load_dotenv()

# ─── Azure OpenAI patch (mora pre svih router importa) ───────────────────────
from shared.ai_client import _patch_openai_module, _patch_prompt_guard
_patch_openai_module()
_patch_prompt_guard()  # SEC-003 — centralni Prompt Guard na SVIM GPT pozivima

# ─── Sentry error tracking ────────────────────────────────────────────────────
def _setup_sentry() -> None:
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        sentry_sdk.init(
            dsn=dsn,
            integrations=[
                StarletteIntegration(transaction_style="endpoint"),
                FastApiIntegration(),
            ],
            traces_sample_rate=0.05,
            environment=os.getenv("ENVIRONMENT", "production"),
            send_default_pii=False,
            attach_stacktrace=True,
        )
    except Exception as _se:
        print(f"[WARN] Sentry init failed: {_se}")

_setup_sentry()

# ─── Prometheus metrics ───────────────────────────────────────────────────────
def _setup_prometheus(application) -> None:
    try:
        from starlette_exporter import PrometheusMiddleware, handle_metrics
        from starlette.requests import Request as _SR
        from starlette.responses import Response as _SResp
        application.add_middleware(PrometheusMiddleware, app_name="vindex_ai", prefix="vindex")

        async def _metrics_gated(scope, receive, send):
            req = _SR(scope, receive)
            key = req.headers.get("x-admin-key", "")
            admin_key = os.getenv("ADMIN_DEBUG_KEY", "")
            if not admin_key or key != admin_key:
                resp = _SResp(status_code=404)
                await resp(scope, receive, send)
                return
            await handle_metrics(scope, receive, send)

        application.add_route("/metrics", _metrics_gated)
    except ImportError:
        pass  # Not installed in dev — no-op

# ─── Fail-fast: validacija encryption key PRE nego server podigne ikoji endpoint
from security.crypto import validate_field_encryption_key as _validate_enc_key
from security.html_sanitize import sanitize_user_input
_validate_enc_key()

import time as _time
from collections import deque as _deque
from datetime import date, datetime, timedelta, timezone

# ─── Performance ring buffers (in-memory, reset on restart) ──────────────────
_PERF: dict[str, _deque] = {
    "copilot":     _deque(maxlen=500),
    "upload":      _deque(maxlen=500),
    "predmet_new": _deque(maxlen=500),
    "ccc":         _deque(maxlen=500),
}
_ERR_LOG: list[float] = []  # timestamps 5xx grešaka

from main import ask_agent, ask_nacrt, ask_analiza, ask_analiza_v2, _skini_pii, klasifikuj_pitanje
from drafting.router import generate_draft as _drafting_generate
from drafting.templates import get_types_list as _drafting_get_types
from templates.podnesci import (
    TIPOVI as PODNESAK_TIPOVI,
    EKSTRAKCIONI_PROMPTOVI,
    OBOGACIVANJE_PROMPTOVI,
    popuni_sablon,
)
from knowledge.vks_standards import preporuci_iznose as vks_preporuci
from klijenti.router import router as klijenti_router

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("vindex.api")

# ─── Supabase ────────────────────────────────────────────────────────────────
from jose import jwt as jose_jwt, JWTError
from supabase import create_client, Client as SupabaseClient

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
# Founders su automatski PRO. Dodaj testere i plaćene korisnike ovde (env var) ili setuj is_pro=true u Supabase.
PRO_EMAILS: set[str] = FOUNDER_EMAILS | {
    e.strip().lower()
    for e in os.getenv("PRO_EMAILS", "").split(",")
    if e.strip()
}


def _is_founder(email: str) -> bool:
    return (email or "").lower() in FOUNDER_EMAILS


def _is_pro(email: str, is_pro_db: bool = False) -> bool:
    """PRO status: founder, PRO_EMAILS lista, ili is_pro=true u Supabase profiles."""
    return is_pro_db or (email or "").lower() in PRO_EMAILS

_supa: Optional[SupabaseClient] = None
# BLACKSWAN-HIGH-001 fix -- same thread-unsafe lazy-singleton bug as shared/deps.py's own
# _get_supa() (this module keeps a SEPARATE singleton, a pre-existing duplication not
# consolidated here). See that module's comment for the full reproduction.
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

    # Korak 2b: ES256 sa hardkodovanim javnim ključem (brzo, bez mreže)
    if alg in ("RS256", "ES256"):
        from jose import jwk as jose_jwk
        _SUPABASE_JWK = {
            "alg": "ES256", "crv": "P-256", "kty": "EC", "use": "sig",
            "kid": "34474d56-eee6-41ed-a78d-4490889d6111",
            "x": "StfqNCxcMFEJ--teLZgJtrF-wyQOyFZPwAakAvRf_Pg",
            "y": "oZmdFqo0HMJD5iLXvjmQ8Golb61P-X71m5bO9zDf8gc",
        }
        try:
            pub = jose_jwk.construct(_SUPABASE_JWK)
            payload = jose_jwt.decode(
                token, pub,
                algorithms=[alg],
                options={"verify_aud": False},
            )
            if payload.get("sub"):
                return payload
            logger.warning("ES256 hardkod: decode OK ali nema sub")
        except JWTError as e:
            logger.warning("ES256 hardkod greška (%s) — pokušavam živi JWKS fallback", e)
            # Hardkodovani ključ je snapshot — ako ga Supabase ikad rotira, ovaj
            # put se sam oporavlja umesto da ODJAVI SVE korisnike odjednom.
            payload = _verify_via_live_jwks(token, alg)
            if payload:
                return payload

    logger.warning("_verify_token: svi koraci neuspešni — vraćam None")
    return None


_jwks_cache: dict = {"keys": None, "fetched_at": 0.0}
_JWKS_CACHE_TTL = 3600  # 1h — dovoljno retko da ne opterecuje Supabase, dovoljno cesto da se sam-izleci


def _verify_via_live_jwks(token: str, alg: str) -> Optional[dict]:
    """
    Fallback za slucaj da je hardkodovani _SUPABASE_JWK zastareo (Supabase
    rotirao potpisni kljuc). Preuzima /.well-known/jwks.json uzivo, kesira
    ga _JWKS_CACHE_TTL sekundi da ne udara Supabase na svaki zahtev, i
    pokusava da verifikuje token protiv SVIH kljuceva u odgovoru.
    """
    import time
    from jose import jwk as jose_jwk

    if not SUPABASE_URL:
        return None

    now = time.time()
    keys = _jwks_cache["keys"]
    if keys is None or (now - _jwks_cache["fetched_at"]) > _JWKS_CACHE_TTL:
        try:
            import requests
            resp = requests.get(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json", timeout=5)
            resp.raise_for_status()
            keys = resp.json().get("keys", [])
            _jwks_cache["keys"] = keys
            _jwks_cache["fetched_at"] = now
            logger.info("[JWKS] Živi ključevi preuzeti (%d) — keširano %ds", len(keys), _JWKS_CACHE_TTL)
        except Exception as exc:
            logger.error("[JWKS] Preuzimanje uživo neuspešno: %s", exc)
            return None

    for jwk_dict in (keys or []):
        try:
            pub = jose_jwk.construct(jwk_dict)
            payload = jose_jwt.decode(
                token, pub,
                algorithms=[jwk_dict.get("alg", alg)],
                options={"verify_aud": False},
            )
            if payload.get("sub"):
                logger.info("[JWKS] Token verifikovan preko živog ključa kid=%s", jwk_dict.get("kid", "?"))
                return payload
        except JWTError:
            continue
        except Exception as exc:
            logger.warning("[JWKS] Greška pri pokušaju sa kid=%s: %s", jwk_dict.get("kid", "?"), exc)
            continue
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
BESPLATNI_KREDITI = 15
BASIC_MESECNI_KREDITI = 200
PRO_MESECNI_KREDITI   = 600

# _mesecna_upotreba, _get_monthly_usage i _increment_monthly_usage su u shared/deps.py
# — uvozimo ih odatle da bi svi workeri koristili isti objekat unutar procesa.


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
                # Row missing — auto-heal (trigger bi trebalo da ga kreira, ovo je safety net)
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
        # Oba pokušaja neuspešna — prava infrastrukturna greška, ne "korisnik
        # nema kredita". Ne gutamo je u lažnu nulu; neka poziv endpointa
        # eksplicitno padne umesto da tiho prikaže pogrešan paywall.
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


# ─── Supabase credit helpers (clean single-purpose API) ──────────────────────

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


# require_credits is the canonical shared version \u2014 same object as shared.deps.require_credits
# so a single dependency_overrides entry covers all routes (api.py + all router modules).
from shared.deps import require_credits, _refund_one_credit, _increment_monthly_usage, _get_monthly_usage, verify_token_local
from shared.attention_priority import VAZNOST_TO_CANONICAL as _VAZNOST_TO_CANONICAL, CANONICAL_ORDER as _CANONICAL_ORDER
from shared.cost import begin_cost_tracking, log_cost_to_db
from shared.llm_retry import llm_retry
from shared.permissions import PermissionService
from shared.sentry import capture_exception as _sentry_capture


@llm_retry
def _pozovi_openai_sync_api(client, **kwargs):
    """CELINA 4 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške. Zajednički helper
    za preostale direktne sync OpenAI pozive u api.py (pozivalac je odgovoran
    za asyncio.to_thread ako se poziva iz async def)."""
    return client.chat.completions.create(**kwargs)


@llm_retry
async def _pozovi_openai_async_api(client, **kwargs):
    """CELINA 4 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške. Zajednički helper
    za preostale direktne AsyncOpenAI pozive u api.py."""
    return await client.chat.completions.create(**kwargs)
from shared.usage import UsageService


# ─── App ──────────────────────────────────────────────────────────────────────
logger.info("=== STARTUP ENV CHECK ===")
logger.info("=== CODE VERSION: legal-analysis-redesign-v2 ===")
logger.info("SUPABASE_URL    : %s...%s", SUPABASE_URL[:20] if SUPABASE_URL else "N/A", SUPABASE_URL[-8:] if SUPABASE_URL and len(SUPABASE_URL) > 28 else "")
logger.info("SERVICE_KEY set : %s", bool(SUPABASE_SERVICE_KEY))
logger.info("JWT_SECRET set  : %s", bool(SUPABASE_JWT_SECRET))
logger.info("FOUNDER_EMAILS  : %s", FOUNDER_EMAILS)
logger.info("PINECONE_API_KEY set : %s", bool(os.getenv("PINECONE_API_KEY", "")))
logger.info("PINECONE_HOST       : %r", os.getenv("PINECONE_HOST", ""))
logger.info("OPENAI_API_KEY set   : %s", bool(os.getenv("OPENAI_API_KEY", "")))

# SEC-005 (2026-07-23): Redis-backed rate limiting is now fail-open, closing
# the gap that previously forced this to be permanently in-memory — see
# shared/rate.py's module docstring for the full incident history and why
# swallow_errors + in_memory_fallback_enabled are both required, not just one.
#
# SEC-005 (2026-07-24): key_func changed from slowapi's own get_remote_address
# (reads only request.client.host) to shared.rate._get_real_ip (reads
# X-Forwarded-For). This app runs behind Render's edge proxy via
# gunicorn+UvicornWorker with no forwarded_allow_ips/ProxyHeadersMiddleware
# configured, so request.client.host is the proxy's address, not the real
# client's — get_remote_address was very likely bucketing all traffic behind
# the same proxy under one shared identity instead of limiting per client.
#
# Wave 10 (2026-08-11): api.py je do sada gradio SOPSTVENU Limiter instancu
# (`limiter = build_limiter(...)`), dok su svi ruteri radili
# `from shared.rate import limiter` i dekorisali rute onom iz shared.rate.
# Rezultat su bile DVE žive instance sa dva odvojena skupa brojača: jedna
# koju dekoratori stvarno koriste, druga u `app.state.limiter` koju koristi
# SlowAPIMiddleware za podrazumevani `60/hour`. Sada se koristi jedna
# kanonska instanca iz `shared.rate` — jedan lifecycle, jedan storage,
# jedan reset. `key_func` je i dalje `_get_real_ip` (gradi ga
# `shared.rate.build_limiter`), pa se semantika limitiranja ne menja.
from shared.rate import _REDIS_URL, limiter
logger.info("Rate limiter: %s (REDIS_URL=%s)", "Redis fail-open" if _REDIS_URL else "in-memory", bool(_REDIS_URL))
app = FastAPI(title="Vindex AI", docs_url=None, redoc_url=None)
app.state.limiter = limiter


def _json_rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"greska": "Previše zahteva. Sačekajte nekoliko sekundi i pokušajte ponovo."},
    )


app.add_exception_handler(RateLimitExceeded, _json_rate_limit_handler)
# Program Lambda, Master Sprint 001 (SEC-011): SlowAPIMiddleware was never
# registered, meaning shared/rate.py's own `default_limits=["60/hour"]`
# floor was very likely non-enforcing for any route without an explicit
# @limiter.limit() decorator (SEC-010 found ~172 such routes). This is the
# one-line fix the register itself already named as "trivial, P0."
app.add_middleware(SlowAPIMiddleware)
_setup_prometheus(app)

# Klijenti CRM router (P1–P8, sve faze)
app.include_router(klijenti_router)

# Extracted routers (Oblast 8 refactor)
from routers.zastarelost import router as zastarelost_router
from routers.strategija  import router as strategija_router
from routers.web3        import router as web3_router
from routers.csv_import  import router as csv_import_router
from routers.ofac_screening import router as ofac_router
from routers.wallet_provenance import router as wallet_provenance_router
from routers.source_of_funds import router as source_of_funds_router
from routers.interni     import router as interni_router
from routers.push        import router as push_router
from routers.export      import router as export_router
from routers.drafting    import router as drafting_router
from routers.dokument    import router as dokument_router
from routers.komentari   import router as komentari_router
from routers.praksa      import router as praksa_router
from routers.copilot       import router as copilot_router
from routers.analytics     import router as analytics_router
from routers.portfolio     import router as portfolio_router
from routers.notifications import router as notifications_router
from routers.intake        import router as intake_router
from routers.smart_intake  import router as smart_intake_router
from routers.import_klijenti import router as import_klijenti_router
from routers.billing       import router as billing_router
from routers.tarife        import router as tarife_router
from routers.rocista       import router as rocista_router
from routers.kalendar      import router as kalendar_router
from routers.hearing_cc           import router as hearing_cc_router
from routers.dashboard            import router as dashboard_router
from routers.inbox                import router as inbox_router
from routers.product_intelligence import router as pi_router
from routers.case_pipeline        import router as case_pipeline_router
from routers.predmeti_close       import router as predmeti_close_router
from routers.rokovi_lanac         import router as rokovi_lanac_router
from routers.ugovor_zastupanja    import router as ugovor_zastupanja_router
from routers.sef                  import router as sef_router
from routers.cross_doc            import router as cross_doc_router
from routers.client_portal        import router as client_portal_router
from routers.saradnja             import router as saradnja_router
from routers.oblasti              import router as oblasti_router
from routers.batch_ingest         import router as batch_ingest_router
from routers.integracije          import router as integracije_router
from routers.recurring            import router as recurring_router
from routers.search               import router as search_router
from routers.billing_reports      import router as billing_reports_router
from routers.sms                  import router as sms_router
from routers.viber                import router as viber_router
from routers.whatsapp_notif       import router as whatsapp_notif_router
from routers.evidence             import router as evidence_router
from routers.evidence_graph       import router as evidence_graph_router
from routers.voice                import router as voice_router
from routers.voice_realtime       import router as voice_realtime_router
from routers.agent_notifications  import router as agent_notifications_router
from routers.copilot_ambient      import router as copilot_ambient_router
from routers.precedenti           import router as precedenti_router
from routers.knowledge_graph      import router as knowledge_graph_router
from routers.ccc                  import router as ccc_router
from routers.conflict_check       import router as conflict_check_router
from routers.matter_intel         import router as matter_intel_router
from routers.outcome_intel        import router as outcome_intel_router
from routers.multi_agent          import router as multi_agent_router
from routers.jobs                 import router as jobs_router
from routers.waitlist             import router as waitlist_router
from routers.kancelarija          import router as kancelarija_router
from routers.law_upload           import router as law_upload_router
from routers.email_notif          import router as email_notif_router, send_welcome_email
from routers.doc_templates        import router as doc_templates_router
from routers.plans                import router as plans_router
from routers.knowledge_base       import router as knowledge_base_router
from routers.gdpr                 import router as gdpr_router
from routers.support              import router as support_router
from routers.court_predictor      import router as court_predictor_router
from routers.onboarding           import router as onboarding_router
from routers.integrations         import router as new_integrations_router
from routers.enterprise           import router as enterprise_router
from routers.morning_briefing     import router as morning_briefing_router
from routers.case_commander       import router as case_commander_router
from routers.region               import router as region_router
from routers.auto_discovery       import router as auto_discovery_router
from routers.strategy_simulator   import router as strategy_simulator_router
from routers.digital_twin         import router as digital_twin_router
from routers.learning             import router as learning_router
from routers.style_checker        import router as style_checker_router
from routers.knowledge_transfer   import router as knowledge_transfer_router
from routers.client_twin          import router as client_twin_router
from routers.confidence_audit     import router as confidence_audit_router
from routers.knowledge_hygiene    import router as knowledge_hygiene_router
from routers.case_intelligence    import router as case_intelligence_router
from routers.case_actions         import router as case_actions_router
from routers.workspace            import router as workspace_router
from routers.decision_replay      import router as decision_replay_router
from routers.case_dna             import router as case_dna_router
from routers.health_index         import router as health_index_router
from routers.intelligence_timeline import router as intel_timeline_router
from routers.legal_reasoning       import router as legal_reasoning_router
from routers.tos                   import router as tos_router
from routers.data_export           import router as data_export_router
from routers.status_page           import router as status_page_router

app.include_router(zastarelost_router)
app.include_router(strategija_router)
app.include_router(web3_router)
app.include_router(csv_import_router)
app.include_router(ofac_router)
app.include_router(wallet_provenance_router)
app.include_router(source_of_funds_router)
app.include_router(interni_router)
app.include_router(push_router)
app.include_router(export_router)
app.include_router(drafting_router)
app.include_router(dokument_router)
app.include_router(komentari_router)
app.include_router(praksa_router)
app.include_router(copilot_router)
app.include_router(analytics_router)
app.include_router(portfolio_router)
app.include_router(notifications_router)
app.include_router(intake_router)
app.include_router(smart_intake_router)
app.include_router(import_klijenti_router)
app.include_router(billing_router)
app.include_router(tarife_router)
app.include_router(rocista_router)
app.include_router(kalendar_router)
app.include_router(hearing_cc_router)
app.include_router(dashboard_router)
app.include_router(inbox_router)
app.include_router(pi_router)
app.include_router(case_pipeline_router)
app.include_router(predmeti_close_router)
app.include_router(rokovi_lanac_router)
app.include_router(ugovor_zastupanja_router)
app.include_router(sef_router)
app.include_router(cross_doc_router)
app.include_router(client_portal_router)
app.include_router(saradnja_router)
app.include_router(oblasti_router)
app.include_router(batch_ingest_router)
app.include_router(integracije_router)
app.include_router(recurring_router)
app.include_router(search_router)
app.include_router(billing_reports_router)
app.include_router(sms_router)
app.include_router(viber_router)
app.include_router(whatsapp_notif_router)
app.include_router(evidence_router)
app.include_router(evidence_graph_router)
app.include_router(voice_router)
app.include_router(voice_realtime_router)
app.include_router(agent_notifications_router)
app.include_router(copilot_ambient_router)
app.include_router(precedenti_router)
app.include_router(knowledge_graph_router)
app.include_router(ccc_router)
app.include_router(conflict_check_router)
app.include_router(matter_intel_router)
app.include_router(outcome_intel_router)
app.include_router(multi_agent_router)
app.include_router(jobs_router)
app.include_router(waitlist_router)
app.include_router(kancelarija_router)
app.include_router(law_upload_router)
app.include_router(email_notif_router)
app.include_router(doc_templates_router)
app.include_router(plans_router)
app.include_router(knowledge_base_router)
app.include_router(gdpr_router)
app.include_router(support_router)
app.include_router(court_predictor_router)
app.include_router(onboarding_router)
app.include_router(new_integrations_router)
app.include_router(enterprise_router)
app.include_router(morning_briefing_router)
app.include_router(case_commander_router)
app.include_router(region_router)
app.include_router(strategy_simulator_router)
app.include_router(digital_twin_router)
app.include_router(auto_discovery_router)
app.include_router(learning_router)
app.include_router(style_checker_router)
app.include_router(knowledge_transfer_router)
app.include_router(client_twin_router)
app.include_router(confidence_audit_router)
app.include_router(knowledge_hygiene_router)
app.include_router(case_intelligence_router)
app.include_router(case_actions_router)
app.include_router(workspace_router)
app.include_router(decision_replay_router)
app.include_router(case_dna_router)
app.include_router(health_index_router)
app.include_router(intel_timeline_router)
app.include_router(legal_reasoning_router)
app.include_router(tos_router)
app.include_router(data_export_router)
app.include_router(status_page_router)
from routers.sesije import router as sesije_router
app.include_router(sesije_router)

from routers.apr import router as apr_router
app.include_router(apr_router)

from routers.portal_monitoring import router as portal_monitoring_router
app.include_router(portal_monitoring_router)

from routers.cio import router as cio_router
app.include_router(cio_router)

from routers.corrections      import router as corrections_router
from routers.zakon_monitoring import router as zakon_monitoring_router
from routers.profitabilnost   import router as profitabilnost_router
from routers.zadaci           import router as zadaci_router
from routers.benchmarking     import router as benchmarking_router
from routers.firm_memory      import router as firm_memory_router
from routers.proof            import router as proof_router
from routers.memory_graph     import router as memory_graph_router
from routers.workflow         import router as workflow_router
from routers.admin_dashboard  import router as admin_dashboard_router
app.include_router(corrections_router)
app.include_router(zakon_monitoring_router)
app.include_router(profitabilnost_router)
app.include_router(zadaci_router)
app.include_router(benchmarking_router)
app.include_router(firm_memory_router)
app.include_router(proof_router)
app.include_router(memory_graph_router)
app.include_router(workflow_router)
app.include_router(admin_dashboard_router)

# F6 — Serviranje static fajlova (PWA manifest, sw.js, ikone)
from fastapi.staticfiles import StaticFiles as _StaticFiles
if os.path.exists(BASE_DIR / "static"):
    app.mount("/static", _StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# MS Word Add-in (taskpane.html, adapter.js, manifest.xml) — servirano sa
# ISTOG FastAPI app-a kao /api/copilot/ambient/analyze namerno: taskpane.html
# poziva window.location.origin kao apiBase (v. taskpane.html's init()),
# tako da je fetch() ka API-ju SAME-ORIGIN i lokalno (https://localhost:8000)
# i u produkciji (https://vindex.rs) -- nema potrebe za CORS podešavanjem
# za ovaj tok. Word zahteva HTTPS za sideload-ovane add-in-e (v.
# scripts/run_word_addin_dev.py za lokalni HTTPS dev server).
if os.path.exists(BASE_DIR / "integrations" / "word_addin"):
    app.mount(
        "/word_addin",
        _StaticFiles(directory=str(BASE_DIR / "integrations" / "word_addin")),
        name="word_addin",
    )


@app.on_event("startup")
async def _warm_connections():
    """Pre-inicijalizuje Pinecone i OpenAI klijente da se izbegne cold-start kašnjenje."""
    def _warm():
        try:
            from app.services.retrieve import _get_index, _get_embeddings, _get_client
            _get_index()
            _get_embeddings()
            _get_client()
            logger.info("Startup warming: Pinecone + OpenAI klijenti inicijalizovani.")
        except Exception as exc:
            logger.warning("Startup warming neuspešan (nije fatalno): %s", exc)
    await asyncio.to_thread(_warm)


@app.on_event("startup")
async def _start_smart_intake_background_loops():
    """Smart Intake Engine, Faza 0 (docs/adr/ADR-0001/ADR-0002) — pokreće
    IntakeWorker (claim/process/complete/fail/reap petlju) i durable event
    bus dispatch loop. Oba dele event loop sa HTTP serverom — nema zaseban
    proces u Fazi 0 (ADR-0002)."""
    try:
        from shared.intake_worker import start_worker
        from services.event_bus import start_dispatch_loop
        start_worker()
        start_dispatch_loop()
    except Exception as exc:
        logger.error("[STARTUP] Smart Intake pozadinske petlje nisu pokrenute (nije fatalno za ostatak app-a): %s", exc)


@app.on_event("shutdown")
async def _stop_smart_intake_background_loops():
    """Graceful shutdown — signalizira obema petljama da stanu POSLE
    trenutnog tick-a, nikad usred obrade jednog posla/dispatch batch-a."""
    try:
        from shared.intake_worker import stop_worker
        from services.event_bus import stop_dispatch_loop
        await stop_worker()
        await stop_dispatch_loop()
    except Exception as exc:
        logger.warning("[SHUTDOWN] Smart Intake pozadinske petlje nisu čisto zaustavljene: %s", exc)

    # S1-1 (2026-08-09): this handler drained exactly two long-lived loops. The
    # other 135 asyncio.create_task(...) calls in the codebase were killed with
    # no grace on every SIGTERM -- on Render, every redeploy -- and nothing
    # reconciled them, because the existing reapers look for a missing durable
    # EVENT ROW, not for a task that died. Tasks registered through
    # shared/bg.py::spawn now get a bounded chance to finish.
    try:
        from shared.bg import drain as _drain_bg
        _left = await _drain_bg(timeout=10.0)
        if _left:
            logger.warning("[SHUTDOWN] %d pozadinskih taskova prekinuto pri gašenju.", _left)
    except Exception as exc:
        logger.warning("[SHUTDOWN] drenaža pozadinskih taskova nije uspela: %s", exc)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Hvatanje svih neočekivanih izuzetaka — vraća JSON umesto HTML stranice greške."""
    from starlette.exceptions import HTTPException as _HTTPExc
    if isinstance(exc, _HTTPExc):
        raise exc
    # SEC-003 — centralni Prompt Guard je blokirao poziv PRE slanja OpenAI-u.
    # Ovo je fallback za pozivna mesta koja ne hvataju izuzetak eksplicitno
    # (rute koje eksplicitno hvataju Exception oko GPT poziva i dalje dobijaju
    # tačan isti bezbednosni ishod — poziv OpenAI-u se nikad nije desio — samo
    # sa svojim, ne ovim, formatom odgovora).
    from security.prompt_guard import PromptInjectionBlocked as _PIBlocked
    if isinstance(exc, _PIBlocked):
        logger.warning(
            "[AI_GUARD] Neuhvaćen PromptInjectionBlocked [path=%s] score=%.2f flags=%d",
            request.url.path, exc.risk_score, len(exc.flags),
        )
        try:
            from shared.audit_immutable import log_action as _imm_log
            from shared.bg import spawn as _spawn_bg
            _spawn_bg(_imm_log(
                "injection_attempt_blocked",
                user_id="unknown",  # SDK-nivo patch nema pristup autentifikovanom user_id-ju
                resource_type=request.url.path,
                ip=request.client.host if request.client else None,
                metadata={"score": exc.risk_score, "flags": exc.flags[:5]},
            ))
        except Exception:
            pass
        _msg = "Zahtev sadrži neodgovarajući sadržaj i nije obrađen."
        return JSONResponse(
            status_code=400,
            content={"greska": _msg, "error": _msg, "status": "error"},
        )
    # Redis quota/connection error — posebna poruka, ne 500
    try:
        from redis.exceptions import RedisError as _RedisError
        if isinstance(exc, _RedisError):
            logger.error("Redis greška [path=%s] %s: %s", request.url.path, type(exc).__name__, exc)
            _msg = "Usluga privremeno nedostupna. Pokušajte ponovo za nekoliko sekundi."
            return JSONResponse(
                status_code=503,
                content={"greska": _msg, "error": _msg, "status": "error"},
            )
    except ImportError:
        pass
    logger.exception("Neočekivana greška [path=%s] tip=%s: %s", request.url.path, type(exc).__name__, exc)
    _msg = "Interna greška servera. Pokušajte ponovo."
    return JSONResponse(
        status_code=500,
        content={"greska": _msg, "error": _msg, "status": "error"},
    )

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "https://vindex.rs").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)

from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

from shared.audit import AuditMiddleware
app.add_middleware(AuditMiddleware)

# ─── User-level rate limiting (in-memory sliding window) ─────────────────────
# Dopuna IP-based slowapi limitera: prati pozive po user_id
# Limiti su namerno blaži od IP limita — korisnik može biti iza NAT-a

import collections as _collections
from security.anomaly_detection import record_request as _anomaly_record, check_anomaly as _anomaly_check

_USER_RATE: dict[str, _deque] = {}
_USER_RATE_LOCK = asyncio.Lock()

_USER_AI_LIMIT    = int(os.getenv("USER_AI_LIMIT_PER_HOUR", "60"))    # AI endpointi
_USER_API_LIMIT   = int(os.getenv("USER_API_LIMIT_PER_HOUR", "600"))   # svi API endpointi

# SEC-005 (2026-07-24): lista je bila zastarela otkad je pisana — 3 od
# originalnih 6 unosa ("/api/kompletna", "/api/copilot", "/api/drafting") ne
# odgovaraju nijednoj stvarno montiranoj ruti (copilot je montiran BEZ
# "/api" prefiksa, kao "/copilot/chat"). Osveženo da odgovara stvarnim
# AI-pozivajućim ruterima danas — svaki prefiks ovde odgovara ruteru čiji
# je kod potvrđeno (grep na openai/chat.completions/gpt-/ai_client) da
# stvarno zove OpenAI. `enterprise.py` namerno NIJE ovde — ne zove AI
# uopšte, njegova zaštita je čisto per-route IP limiter (Faza 3), ne ovaj
# per-user "AI budžet" sat.
_AI_ENDPOINTS = {
    "/api/pitanje", "/api/analiza", "/api/nacrt", "/api/sazmi", "/api/podnesak",  # api.py + routers/drafting.py
    "/copilot/chat",                                                             # routers/copilot.py (bez /api prefiksa)
    "/api/style",                                                                # routers/style_checker.py
    "/api/knowledge",                                                            # routers/knowledge_transfer.py
    "/api/matter-intel",                                                         # routers/matter_intel.py
    "/replay",                                                                    # routers/decision_replay.py (prefiks deli /api/predmeti sa CRUD rutama, zato uzak substring)
    "/api/client-twin",                                                          # routers/client_twin.py
    "/api/cio",                                                                  # routers/cio.py
    "/api/outcome-intel",                                                        # routers/outcome_intel.py
    "/api/precedenti",                                                           # routers/precedenti.py
    "/api/intelligence",                                                        # routers/case_intelligence.py
    "/api/evidence",                                                             # routers/evidence.py
}


async def _check_user_rate_limit(user_id: str, path: str) -> bool:
    """
    Proverava korisnički sliding-window rate limit.
    Vraća True ako je zahtev dozvoljen, False ako je prekoračen.
    """
    if not user_id:
        return True
    now = _time.time()
    window = 3600.0  # 1 sat

    is_ai = any(ep in path for ep in _AI_ENDPOINTS)
    limit = _USER_AI_LIMIT if is_ai else _USER_API_LIMIT
    key = f"{user_id}:{'ai' if is_ai else 'api'}"

    async with _USER_RATE_LOCK:
        dq = _USER_RATE.setdefault(key, _deque())
        # Očisti zastarele unose
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
    return True


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Program Alpha (2026-08-04): previously minted/stored the correlation_id
    in its own, fully independent ContextVar (`_correlation_id_var`), with
    zero readers anywhere else in the codebase — the ONE piece of correlation
    infrastructure actually visible to a client (this header) was completely
    disconnected from shared/ai_provenance.py's own request context, which 4
    prior missions (Ledger, Migration, Phoenix, Keystone) spent real effort
    wiring end-to-end into audit_immutable/ai_forensics/events. A lawyer or
    support engineer taking this header's value and searching for it in any
    of those tables would never find a match. Now sets the SAME canonical
    context this whole codebase already uses, at the earliest point in the
    request lifecycle (middleware runs before route dependencies/auth) --
    shared/deps.py::get_current_user (the async, non-thread-offloaded auth
    path used by the large majority of endpoints) reuses this same id via
    current_correlation_id() rather than minting a second one."""
    from shared.ai_provenance import set_request_context
    # set_request_context() already implements "use the provided id, or mint
    # a fresh one" internally (shared/ai_provenance.py::set_request_context)
    # and returns whichever one is now in effect -- no separate minting logic
    # needed here.
    cid = set_request_context(correlation_id=request.headers.get("X-Correlation-ID"))
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    return response


@app.middleware("http")
async def user_rate_limit_middleware(request: Request, call_next):
    """
    User-level sliding window rate limiter.
    Dopunjuje IP-based slowapi — štiti od botnet-a koji rotira IP adrese.
    Aktivira se samo na /api/ rutama da ne usporava static fajlove.

    SEC-005 (2026-07-24): ranije je ovaj middleware čitao
    `request.state.user_id`, koji NIJE NIGDE u kodu bio postavljen —
    `get_current_user` (FastAPI `Depends`) identitet vraća direktno ruti kao
    povratnu vrednost, nikad ga ne piše u `request.state`, i čak i da piše,
    to bi se desilo unutar `call_next(request)` — POSLE ove provere, prekasno
    da utiče na tekući zahtev. Zbog toga je `uid` uvek bio `None` i ceo ovaj
    blok (rate limit + anomaly detection) se nikad nije izvršio.
    Ispravka: middleware sam izvlači i verifikuje token, PRE `call_next`-a,
    lokalnom (bez Supabase SDK network poziva) proverom potpisa
    `verify_token_local` — dovoljno da bude otporno na falsifikovan `sub`
    claim, a ne dodaje drugi mrežni poziv na svaki zahtev (taj se već plaća
    jednom, u `get_current_user`, za zaštićene rute). Rezultat se upisuje u
    `request.state.user_id` i za dalju upotrebu nizvodno (npr. logovanje).
    """
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)

    uid = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):].strip()
        try:
            payload = verify_token_local(token)
            uid = payload.get("sub") if payload else None
        except Exception as e:
            logger.debug("[RATE] verify_token_local neuspešno: %s", e)
    request.state.user_id = uid

    client_ip = request.client.host if request.client else None
    is_ai = any(ep in path for ep in _AI_ENDPOINTS)

    if uid:
        # Beleži zahtev u anomaly sliding windows (ne-blokira)
        _anomaly_record(uid, path, client_ip or "", is_ai)

        # Rate limit provera
        if not await _check_user_rate_limit(uid, path):
            from shared.audit_immutable import log_action
            asyncio.create_task(log_action(
                "rate_limit_exceeded",
                user_id=uid,
                resource_type="api",
                resource_id=path[:100],
                ip=client_ip,
            ))
            return JSONResponse(
                status_code=429,
                content={"greska": "Previše zahteva. Sačekajte nekoliko minuta i pokušajte ponovo."},
            )

        # Anomaly detection — samo za AI endpointe (sporije, nije potrebno za svaki zahtev)
        if is_ai:
            signal = await _anomaly_check(uid, client_ip)
            if signal.is_anomaly:
                logger.warning(
                    "[ANOMALY] uid=%.8s score=%.2f blocked reasons=%s",
                    uid, signal.score, signal.reasons,
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "greska": "Neobičan obrazac aktivnosti. Kontaktirajte podršku ako mislite da je ovo greška.",
                        "code": "anomaly_detected",
                    },
                )

    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Dodaje security, cache i permissions headere na svaki odgovor."""
    response = await call_next(request)

    # Dugoročni cache za verzionisane static fajlove (JS/CSS) — bezbedan jer
    # index.html koji ih uključuje ima no-cache pa odmah vidi novi ?v= param.
    path = request.url.path
    if path.startswith("/static/") and (path.endswith(".js") or path.endswith(".css")):
        response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
    elif path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=86400"

    response.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=(), payment=()"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdnjs.cloudflare.com unpkg.com; "
        "style-src 'self' 'unsafe-inline' cdnjs.cloudflare.com fonts.googleapis.com; "
        "font-src 'self' cdnjs.cloudflare.com fonts.gstatic.com data:; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' https://*.supabase.co wss://*.supabase.co https://api.openai.com "
        "https://api.emailjs.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com "
        "https://unpkg.com https://fonts.googleapis.com https://fonts.gstatic.com; "
        "worker-src 'self' blob:; "
        "frame-ancestors 'none'; "
        "report-uri /api/security/csp-report"
    )
    return response


@app.middleware("http")
async def _perf_tracking(request: Request, call_next):
    """Beleži vreme odgovora za 4 ključna endpointa u ring bufferima."""
    t0  = _time.perf_counter()
    resp = await call_next(request)
    ms   = int((_time.perf_counter() - t0) * 1000)
    path = request.url.path
    m    = request.method

    if "/copilot" in path:
        _PERF["copilot"].append(ms)
    elif "/dokument" in path and m in ("POST", "PUT"):
        _PERF["upload"].append(ms)
    elif path.rstrip("/").endswith("/predmeti") and m == "POST":
        _PERF["predmet_new"].append(ms)
    elif "/ccc" in path:
        _PERF["ccc"].append(ms)

    if resp.status_code >= 500:
        _ERR_LOG.append(_time.time())
        if len(_ERR_LOG) > 5000:
            del _ERR_LOG[:1000]

    return resp


# ─── Modeli zahteva ───────────────────────────────────────────────────────────

class HistoryItem(BaseModel):
    q: str = Field("", max_length=500)
    a: str = Field("", max_length=1000)


class PitanjeReq(BaseModel):
    pitanje:    str = Field(..., min_length=3, max_length=2000)
    history:    List[HistoryItem] = Field(default_factory=list, max_length=3)
    predmet_id: Optional[str] = Field(None, max_length=64)
    session_id: Optional[str] = Field(None, max_length=64)  # F1.5: konverzaciona memorija

    @field_validator("pitanje")
    @classmethod
    def ocisti(cls, v: str) -> str:
        return sanitize_user_input(v.strip()) or ""




class EmailCheckReq(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)


# ─── Async queue za AI pozive (sprečava OpenAI rate-limit pucanje) ───────────
# Max concurrent OpenAI calls. Threshold: 8 = safe za GPT-4o tier-1 limits.
# Zahtev koji čeka > 30s dobija 503 — bolje odmah nego viseti.

_AI_CONCURRENCY = int(os.getenv("AI_MAX_CONCURRENCY", "8"))
_AI_SEMAPHORE: asyncio.Semaphore | None = None
_AI_QUEUE_TIMEOUT = 30.0  # sekundi


def _get_ai_semaphore() -> asyncio.Semaphore:
    global _AI_SEMAPHORE
    if _AI_SEMAPHORE is None:
        _AI_SEMAPHORE = asyncio.Semaphore(_AI_CONCURRENCY)
    return _AI_SEMAPHORE


async def pokreni(fn, *args):
    sem = _get_ai_semaphore()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=_AI_QUEUE_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("[QUEUE] AI semaphore timeout — %d concurrent slots zauzeto", _AI_CONCURRENCY)
        raise HTTPException(
            status_code=503,
            detail="Server je trenutno preopterećen. Pokušajte ponovo za nekoliko sekundi.",
        )
    try:
        return await asyncio.to_thread(fn, *args)
    finally:
        sem.release()


async def _get_firma_namespace(uid: str) -> Optional[str]:
    """
    Vraća Pinecone namespace za kancelariju korisnika.
    Proverava: admin → kancelarije.pinecone_namespace
               član  → kancelarija_clanovi → kancelarije.pinecone_namespace
    Vraća None ako korisnik nije u firmi ili firma nema namespace.
    """
    try:
        supa = _get_supa()
        # Admin?
        adm = await asyncio.to_thread(
            lambda: supa.table("kancelarije")
                .select("pinecone_namespace")
                .eq("admin_uid", uid)
                .maybe_single()
                .execute()
        )
        if adm.data and adm.data.get("pinecone_namespace"):
            return adm.data["pinecone_namespace"]

        # Član?
        clan = await asyncio.to_thread(
            lambda: supa.table("kancelarija_clanovi")
                .select("kancelarija_id")
                .eq("user_id", uid)
                .eq("status", "ACTIVE")
                .maybe_single()
                .execute()
        )
        if clan.data and clan.data.get("kancelarija_id"):
            kId = clan.data["kancelarija_id"]
            kanc = await asyncio.to_thread(
                lambda: supa.table("kancelarije")
                    .select("pinecone_namespace")
                    .eq("id", kId)
                    .maybe_single()
                    .execute()
            )
            if kanc.data and kanc.data.get("pinecone_namespace"):
                return kanc.data["pinecone_namespace"]
    except Exception as _e:
        logger.debug("[FIRMA_NS] Greška pri dohvatanju namespace-a: %s", _e)
    return None


def _mem_relevance_score(memory: dict, kljucne_reci: list[str]) -> float:
    """
    Skoruje relevantnost memorije u odnosu na pitanje.
    Kombinuje confidence (0-1) i broj podudaranja sa ključnim rečima pitanja.
    """
    conf = float(memory.get("confidence") or 1.0)
    if not kljucne_reci:
        return conf
    tekst = ((memory.get("entity_name") or "") + " " + (memory.get("sadrzaj") or "")).lower()
    pogodci = sum(1 for r in kljucne_reci if r in tekst)
    # Keyword hit povećava score; max 2× confidence
    relevance = conf + min(pogodci * 0.15, conf)
    return relevance


async def _fetch_firm_memory_context(uid: str, pitanje: Optional[str] = None) -> Optional[str]:
    """
    Dohvata institucionalnu memoriju kancelarije i partner profil za dati uid.
    Ako je prosleđeno pitanje, vraća top-5 RELEVANTNIH memorija (ne samo top-confidence).
    Nikad ne blokira — sve greške se gutaju.
    """
    try:
        supa = _get_supa()
        kanc_id: Optional[str] = None

        adm = await asyncio.to_thread(
            lambda: supa.table("kancelarije")
                .select("id")
                .eq("admin_uid", uid)
                .maybe_single()
                .execute()
        )
        if adm.data:
            kanc_id = adm.data.get("id")

        if not kanc_id:
            clan = await asyncio.to_thread(
                lambda: supa.table("kancelarija_clanovi")
                    .select("kancelarija_id")
                    .eq("user_id", uid)
                    .eq("status", "ACTIVE")
                    .maybe_single()
                    .execute()
            )
            if clan.data:
                kanc_id = clan.data.get("kancelarija_id")

        if not kanc_id:
            return None

        mem_r, prof_r = await asyncio.gather(
            asyncio.to_thread(
                # Dohvatamo više (20) pa filtriramo/sortiramo lokalno po relevantnosti
                lambda: supa.table("memory_entries")
                    .select("sadrzaj,entity_name,entity_type,confidence,vaznost")
                    .eq("kancelarija_id", kanc_id)
                    .eq("aktivan", True)
                    .eq("zastarela", False)
                    .gte("confidence", 0.5)
                    .order("confidence", desc=True)
                    .limit(20)
                    .execute()
            ),
            asyncio.to_thread(
                lambda: supa.table("partner_profiles")
                    .select("preferira_krace,preferira_bullet,preferira_formalan,odbijene_strategije")
                    .eq("kancelarija_id", kanc_id)
                    .eq("partner_uid", uid)
                    .maybe_single()
                    .execute()
            ),
        )

        all_memories = mem_r.data or []
        profil = prof_r.data

        # Relevantni retrieval: ključne reči iz pitanja → rankiraj memorije
        kljucne_reci: list[str] = []
        if pitanje:
            import re as _re
            stop = {"i", "u", "da", "se", "je", "na", "za", "ne", "li", "ili", "ako", "ali", "što",
                    "koji", "koje", "koja", "su", "sa", "od", "do", "po", "iz", "kao", "sve", "ima"}
            kljucne_reci = [w.lower() for w in _re.findall(r'\b\w{3,}\b', pitanje) if w.lower() not in stop]

        # Sortiraj po relevantnosti + uzmi top 5
        memories = sorted(
            all_memories,
            key=lambda m: _mem_relevance_score(m, kljucne_reci),
            reverse=True
        )[:5]

        if not memories and not profil:
            return None

        lines = ["INSTITUCIONALNA MEMORIJA KANCELARIJE (top 5 relevantnih):"]
        for m in memories:
            naziv = m.get("entity_name", "")
            sadrzaj = m.get("sadrzaj", "")
            conf = float(m.get("confidence") or 1.0)
            pouzdanost = "visoka" if conf >= 0.8 else ("srednja" if conf >= 0.6 else "niska")
            prefix = f"[{naziv}] " if naziv else ""
            lines.append(f"- {prefix}{sadrzaj} [pouzdanost: {pouzdanost}]")

        if profil:
            stil_delovi = []
            if profil.get("preferira_krace"):
                stil_delovi.append("kraći podnesci")
            if profil.get("preferira_bullet"):
                stil_delovi.append("bullet liste")
            else:
                stil_delovi.append("bez bullet lista")
            if profil.get("preferira_formalan"):
                stil_delovi.append("formalan ton")
            if stil_delovi:
                lines.append(f"- Stil partnera: {', '.join(stil_delovi)}")
            odbijene = profil.get("odbijene_strategije") or []
            for s in (odbijene[:2] if isinstance(odbijene, list) else []):
                lines.append(f"- NIKAD NE PREDLAGATI: {s}")

        return "\n".join(lines)
    except Exception as _me:
        logger.debug("[FIRM_MEM] Greška pri dohvatanju memorije: %s", _me)
        return None


def _poseduje_predmet(user_id: str, predmet_id: str) -> bool:
    """Da li `predmet_id` pripada baš ovom korisniku.

    CONF-010 (BETA-DATA-CONFIDENTIALITY-002). `/api/pitanje` (`:3378`) i
    `/api/procena` (`:4895`) su upisivali u `predmet_istorija` sa `predmet_id`
    koji stiže iz tela zahteva, bez ijedne provere. Napadač je time ubacivao
    sopstveno pitanje i pun GPT-4o odgovor u TUĐI pravni spis, gde ih žrtva
    zatim vidi kao svoju AI istoriju (`:4154` ih razliva kroz `get_predmet`).

    Asimetrija koja objašnjava kako je promaklo: oba endpointa čitanje konteksta
    VEĆ ispravno filtriraju po `user_id` (`:3339`, `:4774`). Izolacija je
    promišljena na strani čitanja i zaboravljena na strani upisa — isti obrazac
    u devet drugih ruta.

    Fail-closed: greška u proveri znači NE upisuj.
    """
    if not (user_id and predmet_id):
        return False
    try:
        r = (_get_supa().table("predmeti").select("id")
             .eq("id", predmet_id).eq("user_id", user_id).limit(1).execute())
        return bool(r.data)
    except Exception as e:
        logger.warning("[SEC] provera vlasništva predmeta pala, upis se odbija: %s", e)
        return False


def _treba_refundirati(rezultat: dict) -> bool:
    """Da li korisniku treba vratiti kredit za ovaj rezultat.

    BETA-HARDENING-001 / FS-003. Uslov je do sada glasio
    `from_cache or blocked or status == "error"` i bio je DOSLOVNO isti na obe
    putanje (`/api/pitanje` i `/api/pitanje/stream`). Nijedna od njih nije
    pokrivala slucaj `status == "success"` sa PRAZNIM tekstom: korisnik dobije
    prazan ekran, protokol se uredno zavrsi, a kredit ostane naplacen.

    Prazan odgovor nije isporucen odgovor. Predikat je izdvojen ovde da obe
    putanje dele JEDAN uslov -- ovo nije nov tok, nego uklanjanje duplikata
    uslova koji je vec postojao dva puta.
    """
    if not isinstance(rezultat, dict):
        return True
    if rezultat.get("from_cache", False) or rezultat.get("blocked", False):
        return True
    if rezultat.get("status") == "error":
        return True
    if rezultat.get("status") == "success":
        # SE-006 (protivnički pregled): `data` nije uvek `str` — `ask_analiza_v2`
        # vraća `dict`. `(… or "").strip()` bi bacio `AttributeError` i pretvorio
        # kanonski predikat u NOV izvor padova. Prazno je samo ono što nema
        # sadržaja; svaka ne-prazna struktura je isporučen odgovor.
        _data = rezultat.get("data")
        if _data is None:
            return True
        if isinstance(_data, str):
            if not _data.strip():
                return True
        elif not _data:
            return True
    return False


def normalizuj_rezultat(rezultat: dict, credits_remaining: Optional[int] = None) -> dict:
    """Pretvara interni rezultat agenta u API odgovor."""
    resp: dict = {}
    if not isinstance(rezultat, dict):
        resp["odgovor"] = str(rezultat)
    elif rezultat.get("status") == "success":
        resp["odgovor"] = rezultat.get("data") or "Sistem nije vratio odgovor. Pokušajte ponovo."
    else:
        resp["odgovor"] = rezultat.get(
            "message",
            "Došlo je do greške prilikom obrade zahteva. Pokušajte ponovo.",
        )
    if credits_remaining is not None:
        resp["credits_remaining"] = credits_remaining
    # RAG confidence signal — šalje se klijentu radi prikaza
    if isinstance(rezultat, dict):
        if rezultat.get("confidence"):
            resp["confidence"] = rezultat["confidence"]
        if rezultat.get("confidence_detail"):
            resp["confidence_detail"] = rezultat["confidence_detail"]
        if rezultat.get("izvori"):
            resp["izvori"] = rezultat["izvori"]
        if rezultat.get("top_score") is not None:
            resp["top_score"] = round(float(rezultat["top_score"]), 3)
        if rezultat.get("top_law"):
            resp["top_law"] = rezultat["top_law"]
        if rezultat.get("top_article"):
            resp["top_article"] = rezultat["top_article"]
    return resp


def greska_odgovor(status_code: int, poruka: str) -> JSONResponse:
    logger.warning("API greška %d: %s", status_code, poruka)
    return JSONResponse(status_code=status_code, content={"greska": poruka})


# ─── Cache busting ────────────────────────────────────────────────────────────
import re as _re

def _get_git_hash() -> str:
    """Vrednost za `?v=` u index.html — sada iz jedinog vlasnika identiteta.

    P0-A: ranija implementacija je zvala `git rev-parse --short HEAD` kroz
    subprocess, a na grešci vraćala `str(int(time.time()))[-6:]`. Dva problema:

      1. `python:3.11-slim` NEMA `git` binarni fajl, pa je u produkciji ta
         grana uvek padala na fallback. Mehanizam nikad nije radio tamo gde je
         bio potreban.
      2. Fallback je vraćao šestocifren broj koji IZGLEDA kao skraćen hash.
         Vrednost koja se lažno predstavlja kao identitet je gora od izostanka
         identiteta -- neko bi se na nju pozvao kao na dokaz koji build je živ.

    `shared/build_info.py` razrešava SHA iz platformskih promenljivih ili iz
    `.git` direktorijuma, bez subprocess-a i bez `git` binarnog fajla. Kada
    identitet nije dokazan, prefiks `nover-` čini to očiglednim na prvi pogled.
    """
    from shared.build_info import get_build_info
    short = get_build_info().get("commit_short")
    if short:
        return short
    import time
    return "nover-" + str(int(time.time()))[-6:]

_GIT_HASH: str = _get_git_hash()
_INDEX_HTML_BYTES: bytes = b""

def _load_index_html() -> bytes:
    global _INDEX_HTML_BYTES
    path = BASE_DIR / "index.html"
    if not path.exists():
        return b""
    content = path.read_text(encoding="utf-8")
    content = _re.sub(r'\?v=\w+', f"?v={_GIT_HASH}", content)
    _INDEX_HTML_BYTES = content.encode("utf-8")
    return _INDEX_HTML_BYTES

_load_index_html()
logger.info("Cache busting: ?v=%s", _GIT_HASH)


# ─── Rute ─────────────────────────────────────────────────────────────────────

# ─── Javni sajt (site/) ───────────────────────────────────────────────────────
# Svaka stranica je zasebna ruta -> zaseban HTML fajl -> FileResponse sa
# eksplicitnim Cache-Control. Namerno se NE montira `site/` preko StaticFiles:
# `static/` je vec ceo montiran, pa je npr. `static/security.html` javan na dve
# putanje sa razlicitim kesiranjem -- taj obrazac se ovde ne ponavlja.
#
# max-age=300 (a ne 3600): HTML nema hash u imenu ni build korak, pa je HTTP kes
# jedina poluga za brzu ispravku teksta. Sat vremena bi znacio sat vremena bez
# ikakvog nacina da se ispravka ubrza.

@app.get("/", include_in_schema=False)
@app.head("/", include_in_schema=False)
def root():
    path = BASE_DIR / "site" / "index.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": "public, max-age=300"})
    return {"status": "ok", "servis": "Vindex AI"}


@app.get("/kako-radi", include_in_schema=False)
def site_kako_radi():
    path = BASE_DIR / "site" / "kako-radi.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": "public, max-age=300"})
    return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})


@app.get("/sposobnosti", include_in_schema=False)
def site_sposobnosti():
    path = BASE_DIR / "site" / "sposobnosti.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": "public, max-age=300"})
    return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})


@app.get("/za-advokate", include_in_schema=False)
def site_za_advokate():
    path = BASE_DIR / "site" / "za-advokate.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": "public, max-age=300"})
    return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})


@app.get("/web3", include_in_schema=False)
def site_web3():
    """Digitalna imovina i usklađenost.

    Ruta je `/web3` jer je to termin po kome je posetilac traži, ali je vidljivi
    naziv modula „Digitalna imovina" — tako ga zove i sam kod (`migrations/060`).
    Obim je usklađenost i provera porekla digitalne imovine; nikad trgovanje.
    """
    path = BASE_DIR / "site" / "web3.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": "public, max-age=300"})
    return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})


@app.get("/bezbednost", include_in_schema=False)
def site_bezbednost():
    path = BASE_DIR / "site" / "bezbednost.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": "public, max-age=300"})
    return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})


@app.get("/vizija", include_in_schema=False)
def site_vizija():
    path = BASE_DIR / "site" / "vizija.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": "public, max-age=300"})
    return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})


@app.get("/tehnologija", include_in_schema=False)
def site_tehnologija():
    path = BASE_DIR / "site" / "tehnologija.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": "public, max-age=300"})
    return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})


@app.get("/beta", include_in_schema=False)
def site_beta():
    path = BASE_DIR / "site" / "beta.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": "public, max-age=300"})
    return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})


@app.get("/kontakt", include_in_schema=False)
def site_kontakt():
    path = BASE_DIR / "site" / "kontakt.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": "public, max-age=300"})
    return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})


@app.get("/privacy")
def privacy_policy():
    path = BASE_DIR / "privacy.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})
    return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})

@app.get("/status")
def status_page():
    path = BASE_DIR / "static" / "status.html"
    return FileResponse(path, headers={"Cache-Control": "no-cache"})

@app.get("/security")
def security_whitepaper():
    path = BASE_DIR / "static" / "security.html"
    return FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})

@app.get("/dpa")
def dpa_page():
    path = BASE_DIR / "static" / "dpa.html"
    return FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})

@app.get("/ai-disclosure")
def ai_disclosure_page():
    path = BASE_DIR / "static" / "ai-disclosure.html"
    return FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})

@app.get("/bezbednosni-list")
def bezbednosni_list_page():
    path = BASE_DIR / "static" / "bezbednosni-list.html"
    return FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})


@app.get("/terms")
def terms_of_service():
    path = BASE_DIR / "terms.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})
    return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})


# Ruta /pricing je uklonjena zajedno sa pricing.html: nijedan od reklamiranih
# planova nije bio kupljiv (STRIPE_URL je prazan), krediti se ne obnavljaju, a
# deo prodavanih funkcija je gejtovan stroze nego sto je stranica tvrdila.
# Cene se saopstavaju kroz /kontakt dok naplata ne postoji.


@app.get("/health")
@app.head("/health")
def health():
    import os as _os
    from shared.build_info import APP_NAME as _APP, get_build_info as _bi
    _b = _bi()
    return {
        "status": "ok",
        # P0-A: `app` i `commit` su ovde da bi odgovor sam sebe identifikovao.
        # Bez njih je HTTP 200 sa /health neupotrebljiv kao dokaz da se vrti
        # Vindex -- tacno ta greska je proizvela lazan nalaz u TASK-3D.
        "app": _APP,
        "commit": _b["commit_short"],
        "pid": _os.getpid(),
        "redis": bool(_REDIS_URL),
        "workers": int(_os.getenv("WEB_CONCURRENCY", 1)),
        # GT-001 (BETA-HARDENING-002): stanje provenance ŠEME, ne stanje zakrpe.
        # Ranije se ovde izlagalo samo da li je AI zakrpa aktivna — a tiho
        # osiromašenje forenzičkog traga (migracija 089 nije primenjena) nije
        # imalo NIJEDAN spoljni signal. Sada ga ima, i `None` se ne prikazuje
        # kao „u redu" nego kao „još nije izmereno".
        "provenance": _provenance_stanje(),
    }


def _provenance_stanje() -> dict:
    """Fail-soft omotač — health nikad ne sme da padne zbog dijagnostike."""
    try:
        from security.ai_forensics import provenance_stanje_seme
        return provenance_stanje_seme()
    except Exception:                  # pragma: no cover — dijagnostika
        # P6b (protivnicki pregled): OVDE JE STAJALO `str(_exc)[:120]`.
        # `/health` je JAVAN i neautentikovan; izmereno je da tako izlazi
        # `postgres://korisnik:LOZINKA@host/baza` iz teksta izuzetka.
        # To je bila NOVA bezbednosna povrsina koju je uveo ovaj sprint.
        # Spolja se sme videti samo DA dijagnostika nije dostupna.
        logger.warning("[HEALTH] stanje provenance seme nije dostupno", exc_info=True)
        return {"dostupno": False}


@app.get("/api/version")
@app.head("/api/version")
def api_version():
    """Identitet build-a koji opslužuje ovaj zahtev (P0-A / BTM-P0-04).

    Javno, namerno. Repozitorijum je javan, pa commit SHA ne otkriva ništa što
    već nije dostupno, a bez javnog pristupa ovaj endpoint ne bi mogao da
    posluži svrsi: da se sa strane, bez pristupa serveru, dokaže KOJI build
    opslužuje korisnika.

    Ne izlaže putanje, `pid`, broj worker-a niti bilo šta o infrastrukturi --
    to ostaje na `/health` i `/metrics`.

    `identity_proven: false` znači da SHA nije razrešen ni iz jedne
    platformske promenljive ni iz `.git`. Tada se odgovor NE sme koristiti kao
    dokaz da je bilo koja popravka deployovana.
    """
    from shared.build_info import build_identity_proven as _proven, get_build_info as _bi
    b = _bi()

    # Governance Wave 4: da li su AI kontrole STVARNO žive u ovom procesu.
    #
    # Do sada se to nije moglo utvrditi spolja. `_guard_patched` se postavljao
    # na True i kada patch nije uspeo, pa je proces bez ijednog prompt guard-a i
    # bez Response Firewall-a izgledao identično ispravnom. Ovo je najmanja
    # tačka izlaganja koja postoji — `/api/version` već postoji zbog P0-A i već
    # je namenjen tvrdnjama o identitetu ovog build-a.
    #
    # Ne izlaže ništa osetljivo: dve zastavice i ime klase greške.
    #
    # Governance Wave 9 (§8): status sada nosi i `ai_blocked` — razliku između
    # „kontrole ne rade, a AI i dalje radi neupravljano" (neprihvatljivo) i
    # „kontrole ne rade, pa je AI granica zatvorena" (fail-closed). Bez tog
    # polja se ta dva stanja spolja ne razlikuju, a samo jedno je bezbedno.
    try:
        from shared.ai_client import governance_status as _gs
        gov = _gs()
    except Exception:
        # `ai_blocked: None` = nepoznato. Namerno NIJE False: tvrdnja „AI nije
        # blokiran" bez izvora bila bi izmišljena.
        gov = {
            "attempted": None, "active": None, "ai_blocked": None,
            "ai_block_method": None, "ai_block_reason": None,
            "failure_reason": "status nedostupan",
        }

    return {
        "app": b["app"],
        "governance": gov,
        "commit": b["commit"],
        "commit_short": b["commit_short"],
        "commit_source": b["commit_source"],
        "identity_proven": _proven(),
        "branch": b["branch"],
        "built_at": b["built_at"],
        "started_at": b["started_at"],
        "environment": b["environment"],
        "environment_declared": b["environment_declared"],
        "python": b["python"],
        "sw_cache": b["sw_cache"],
    }


@app.post("/api/cron/daily")
async def cron_daily(request: Request):
    """
    Unified daily cron — jedan poziv, sve pozadinske operacije.
    Zaštićen X-Cron-Secret headerom.
    Render.com cron: POST /api/cron/daily svaki dan u 07:00 UTC

    Guarantees:
      - Idempotent: drugi poziv unutar 60 min vraća skip bez ponovnog izvršavanja
      - Isolated: svaki modul u try/except; greška jednog ne obarajre ostatak
      - Auditable: svaki run dobija Run ID + per-modul counts + duration
    """
    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz

    cron_secret = os.getenv("BRIEFING_CRON_SECRET", "")
    x_secret = request.headers.get("X-Cron-Secret", "")
    # Fail CLOSED (Production Readiness Report 2026-07-25, stavka #1): ako
    # BRIEFING_CRON_SECRET nije podešen na serveru, endpoint MORA ostati
    # zaključan -- prethodna verzija (`if cron_secret and ...`) je tiho
    # preskakala proveru kad je env var nedostajala, ostavljajući ovaj
    # dispečer (retention cleanup, background agenti, svi dnevni moduli)
    # pozivan bez ikakve autentifikacije od bilo koga ko zna URL.
    if not cron_secret or x_secret != cron_secret:
        raise HTTPException(status_code=401, detail="Neovlašćen pristup.")

    run_id = _uuid.uuid4().hex[:8]
    _now = _dt.now(_tz.utc)
    _run_date = _now.strftime("%Y%m%d")

    # ── Idempotency guard: preskoči ako je već pokrenuto u poslednjih 60 min ──
    try:
        _last_r = await asyncio.to_thread(
            lambda: _get_supa().table("chain_anchors")
                .select("anchored_at")
                .eq("id", "cron_daily_heartbeat")
                .maybe_single()
                .execute()
        )
        if _last_r.data and _last_r.data.get("anchored_at"):
            _last_ts = _dt.fromisoformat(_last_r.data["anchored_at"].replace("Z", "+00:00"))
            _sati_od = (_dt.now(_tz.utc) - _last_ts).total_seconds() / 3600
            if _sati_od < 1:
                logger.info("[CRON_DAILY] run_id=%s SKIPPED ran %.1f min ago", run_id, _sati_od * 60)
                return {"ok": True, "skipped": True, "run_id": run_id,
                        "razlog": f"Već pokrenuto pre {round(_sati_od * 60, 1)} min"}
            if _sati_od > 36:
                logger.critical(
                    "[CRON_DAILY] STALE ALERT run_id=%s poslednji run pre %.1fh! "
                    "Proveriti cron-job.org i Render.com logs.", run_id, _sati_od
                )
    except Exception:
        pass

    # ── cron_runs: zabeleži početak izvršavanja (operativna istorija) ────────
    try:
        await asyncio.to_thread(
            lambda: _get_supa().table("cron_runs").insert({
                "run_id": run_id, "started_at": _now.isoformat(), "status": "running",
            }).execute()
        )
    except Exception:
        pass

    rezultati: dict = {"run_id": run_id}
    _t_start = _time.monotonic()
    _broj_grešaka = 0
    _stavke_obradjene = 0

    # ── Modul 1: Workflow eskalacije ─────────────────────────────────────────
    _t_wf = _time.monotonic()
    try:
        from routers.workflow import _check_escalations
        _wf = await asyncio.wait_for(_check_escalations(), timeout=60)
        _wf_esc = int(_wf.get("eskaliranih", 0) or 0) if isinstance(_wf, dict) else 0
        _wf_chk = int(_wf.get("proverenih", 0) or 0) if isinstance(_wf, dict) else 0
        _stavke_obradjene += _wf_esc
        rezultati["workflow"] = {
            "proverenih": _wf_chk,
            "eskaliranih": _wf_esc,
            "duration_ms": round((_time.monotonic() - _t_wf) * 1000),
            "status": "ok",
        }
    except asyncio.TimeoutError:
        rezultati["workflow"] = {"status": "timeout", "greska": "Prekoraceno 60s",
                                  "duration_ms": round((_time.monotonic() - _t_wf) * 1000)}
        _broj_grešaka += 1
    except Exception as _ce:
        rezultati["workflow"] = {"status": "greska", "greska": str(_ce)[:120],
                                  "duration_ms": round((_time.monotonic() - _t_wf) * 1000)}
        _broj_grešaka += 1

    # ── Modul 2: Zakon monitoring (samo ponedeljkom) ─────────────────────────
    if _dt.now(_tz.utc).weekday() == 0:
        _t_zm = _time.monotonic()
        try:
            from routers.zakon_monitoring import _skeniraj_sl_glasnik
            _zm = await asyncio.wait_for(_skeniraj_sl_glasnik(_get_supa(), dana_unazad=7), timeout=180)
            _zm_pron = int(_zm.get("pronadjeno", 0) or 0) if isinstance(_zm, dict) else 0
            _zm_prom = int(_zm.get("promena", 0) or 0) if isinstance(_zm, dict) else 0
            _stavke_obradjene += _zm_pron
            rezultati["zakon_monitoring"] = {
                "proverenih": _zm_pron,
                "promena": _zm_prom,
                "duration_ms": round((_time.monotonic() - _t_zm) * 1000),
                "status": "ok",
            }
        except asyncio.TimeoutError:
            rezultati["zakon_monitoring"] = {"status": "timeout", "greska": "Prekoraceno 180s",
                                              "duration_ms": round((_time.monotonic() - _t_zm) * 1000)}
            _broj_grešaka += 1
        except Exception as _ze:
            rezultati["zakon_monitoring"] = {"status": "greska", "greska": str(_ze)[:120],
                                              "duration_ms": round((_time.monotonic() - _t_zm) * 1000)}
            _broj_grešaka += 1
    else:
        rezultati["zakon_monitoring"] = {"status": "preskoceno", "razlog": "nije ponedeljak"}

    # ── Modul 3: Memory cleanup — čisti zastarele unose (confidence < 0.1) ──
    _t_mc = _time.monotonic()
    try:
        async def _cleanup():
            r1 = await asyncio.to_thread(
                lambda: _get_supa().table("memory_entries").delete().lt("confidence", 0.1).execute()
            )
            r2 = await asyncio.to_thread(
                lambda: _get_supa().table("memory_entries").delete().eq("zastarela", True).execute()
            )
            return len(r1.data or []) + len(r2.data or [])
        _obrisano = await asyncio.wait_for(_cleanup(), timeout=30)
        rezultati["memory_cleanup"] = {
            "obrisano": _obrisano,
            "duration_ms": round((_time.monotonic() - _t_mc) * 1000),
            "status": "ok",
        }
    except asyncio.TimeoutError:
        rezultati["memory_cleanup"] = {"status": "timeout", "greska": "Prekoraceno 30s",
                                        "duration_ms": round((_time.monotonic() - _t_mc) * 1000)}
        _broj_grešaka += 1
    except Exception as _mce:
        rezultati["memory_cleanup"] = {"status": "greska", "greska": str(_mce)[:120],
                                        "duration_ms": round((_time.monotonic() - _t_mc) * 1000)}
        _broj_grešaka += 1

    # ── Modul 4: Portal.sud.rs monitoring ────────────────────────────────────
    _t_pm = _time.monotonic()
    try:
        from routers.portal_monitoring import cron_proveri as _pm_cron
        class _FakeReq:
            headers = {}
            client = None
        _pm_r = await asyncio.wait_for(
            _pm_cron(_FakeReq(), x_cron_secret=cron_secret, user={"user_id": "cron", "email": ""}, run_id=run_id),
            timeout=120,
        )
        _pm_prov = int(_pm_r.get("provereno", 0)) if isinstance(_pm_r, dict) else 0
        _pm_prom = int(_pm_r.get("promena", 0)) if isinstance(_pm_r, dict) else 0
        _stavke_obradjene += _pm_prom
        rezultati["portal_monitoring"] = {
            "provereno": _pm_prov,
            "promena": _pm_prom,
            "duration_ms": round((_time.monotonic() - _t_pm) * 1000),
            "status": "ok",
        }
    except asyncio.TimeoutError:
        rezultati["portal_monitoring"] = {"status": "timeout", "greska": "Prekoraceno 120s",
                                           "duration_ms": round((_time.monotonic() - _t_pm) * 1000)}
        _broj_grešaka += 1
    except Exception as _pme:
        rezultati["portal_monitoring"] = {"status": "greska", "greska": str(_pme)[:120],
                                           "duration_ms": round((_time.monotonic() - _t_pm) * 1000)}
        _broj_grešaka += 1

    # ── Modul 5: Workflow eskalacije ─────────────────────────────────────────
    _t_wf = _time.monotonic()
    try:
        from routers.workflow import _check_escalations as _wf_cron
        _wf_r = await asyncio.wait_for(_wf_cron(), timeout=60)
        _wf_poslato = int(_wf_r.get("eskalacionih_alertova", 0)) if isinstance(_wf_r, dict) else 0
        _stavke_obradjene += _wf_poslato
        rezultati["workflow_eskalacije"] = {
            "eskalacionih_alertova": _wf_poslato,
            "duration_ms": round((_time.monotonic() - _t_wf) * 1000),
            "status": "ok",
        }
    except asyncio.TimeoutError:
        rezultati["workflow_eskalacije"] = {"status": "timeout", "greska": "Prekoraceno 60s",
                                             "duration_ms": round((_time.monotonic() - _t_wf) * 1000)}
        _broj_grešaka += 1
    except Exception as _wfe:
        rezultati["workflow_eskalacije"] = {"status": "greska", "greska": str(_wfe)[:120],
                                             "duration_ms": round((_time.monotonic() - _t_wf) * 1000)}
        _broj_grešaka += 1

    # ── Modul 6/7/8: Email podsetnici / onboarding / nedeljni sažetak ───────
    # SEC-002 (2026-07-24): ova 3 modula su ranije živela u
    # routers/email_notif.py's SOPSTVENOM /api/cron/daily -- koji je bio
    # registrovan PRE ovog handlera (app.include_router na liniji 699) i
    # zato tiho "pobeđivao" u Starlette-ovom prvi-match rutiranju, što je
    # značilo da OVAJ, bogatiji dispečer nikad nije stvarno izvršen. Taj
    # duplirani endpoint je uklonjen; posalji_podsetnike/onboarding_cron/
    # posalji_nedeljni_sazetak (i dalje dostupne kao svoje pojedinačne rute
    # za ručno okidanje) sada se pozivaju odavde direktno. Nijedna od te 3
    # funkcije ne koristi `request`/`user` u svom telu (potvrđeno čitanjem
    # izvora pre ove izmene) -- prosleđujemo isti `request` koji ovaj
    # handler već ima, i placeholder `user` istog oblika koji
    # _require_cron_or_founder sam vraća za X-Cron-Key granu.
    _cron_user = {"user_id": "cron-scheduler", "email": next(iter(FOUNDER_EMAILS), "")}

    _t_em = _time.monotonic()
    try:
        from routers.email_notif import posalji_podsetnike as _email_podsetnici_cron
        _em_r = await asyncio.wait_for(_email_podsetnici_cron(request, _cron_user), timeout=60)
        _stavke_obradjene += int((_em_r or {}).get("poslato", 0))
        rezultati["email_podsetnici"] = {**(_em_r or {}), "status": "ok",
                                          "duration_ms": round((_time.monotonic() - _t_em) * 1000)}
    except asyncio.TimeoutError:
        rezultati["email_podsetnici"] = {"status": "timeout", "greska": "Prekoraceno 60s",
                                          "duration_ms": round((_time.monotonic() - _t_em) * 1000)}
        _broj_grešaka += 1
    except Exception as _eme:
        rezultati["email_podsetnici"] = {"status": "greska", "greska": str(_eme)[:120],
                                          "duration_ms": round((_time.monotonic() - _t_em) * 1000)}
        _broj_grešaka += 1

    _t_ob = _time.monotonic()
    try:
        from routers.email_notif import onboarding_cron as _onboarding_cron_fn
        _ob_r = await asyncio.wait_for(_onboarding_cron_fn(request, _cron_user), timeout=60)
        _stavke_obradjene += int((_ob_r or {}).get("poslato", 0))
        rezultati["onboarding"] = {**(_ob_r or {}), "status": "ok",
                                   "duration_ms": round((_time.monotonic() - _t_ob) * 1000)}
    except asyncio.TimeoutError:
        rezultati["onboarding"] = {"status": "timeout", "greska": "Prekoraceno 60s",
                                    "duration_ms": round((_time.monotonic() - _t_ob) * 1000)}
        _broj_grešaka += 1
    except Exception as _obe:
        rezultati["onboarding"] = {"status": "greska", "greska": str(_obe)[:120],
                                    "duration_ms": round((_time.monotonic() - _t_ob) * 1000)}
        _broj_grešaka += 1

    if _dt.now(_tz.utc).weekday() == 0:  # ponedeljak
        _t_ns = _time.monotonic()
        try:
            from routers.email_notif import posalji_nedeljni_sazetak as _nedeljni_sazetak_cron
            _ns_r = await asyncio.wait_for(_nedeljni_sazetak_cron(request, _cron_user), timeout=60)
            _stavke_obradjene += int((_ns_r or {}).get("poslato", 0))
            rezultati["nedeljni_sazetak"] = {**(_ns_r or {}), "status": "ok",
                                              "duration_ms": round((_time.monotonic() - _t_ns) * 1000)}
        except asyncio.TimeoutError:
            rezultati["nedeljni_sazetak"] = {"status": "timeout", "greska": "Prekoraceno 60s",
                                              "duration_ms": round((_time.monotonic() - _t_ns) * 1000)}
            _broj_grešaka += 1
        except Exception as _nse:
            rezultati["nedeljni_sazetak"] = {"status": "greska", "greska": str(_nse)[:120],
                                              "duration_ms": round((_time.monotonic() - _t_ns) * 1000)}
            _broj_grešaka += 1
    else:
        rezultati["nedeljni_sazetak"] = {"status": "preskoceno", "razlog": "nije ponedeljak"}

    # ── Modul 9: SEC-002 Data Retention cleanup ──────────────────────────────
    _t_rt = _time.monotonic()
    try:
        from services.retention_service import execute_retention_cleanup
        _rt_r = await asyncio.wait_for(execute_retention_cleanup(), timeout=60)
        _rt_summary = (_rt_r or {}).get("_summary", {})
        _stavke_obradjene += int(_rt_summary.get("ukupno_obrisano", 0))
        _broj_grešaka += int(_rt_summary.get("greske", 0))
        rezultati["retention_cleanup"] = {
            "status": "ok" if not _rt_summary.get("greske") else "delimicno",
            "obrisano": _rt_summary.get("ukupno_obrisano", 0),
            "detalji": {k: v for k, v in (_rt_r or {}).items() if k != "_summary"},
            "duration_ms": round((_time.monotonic() - _t_rt) * 1000),
        }
    except asyncio.TimeoutError:
        rezultati["retention_cleanup"] = {"status": "timeout", "greska": "Prekoraceno 60s",
                                           "duration_ms": round((_time.monotonic() - _t_rt) * 1000)}
        _broj_grešaka += 1
    except Exception as _rte:
        rezultati["retention_cleanup"] = {"status": "greska", "greska": str(_rte)[:120],
                                           "duration_ms": round((_time.monotonic() - _t_rt) * 1000)}
        _broj_grešaka += 1

    # ── Modul 9a: BLACKSWAN-HIGH-008 — reap missing pipeline events ──────────
    _t_mpe = _time.monotonic()
    try:
        from services.event_bus import reap_missing_pipeline_events
        _mpe_r = await asyncio.wait_for(reap_missing_pipeline_events(), timeout=60)
        _stavke_obradjene += int((_mpe_r or {}).get("backfilled", 0))
        rezultati["reap_missing_pipeline_events"] = {
            "status": "ok",
            "checked": (_mpe_r or {}).get("checked", 0),
            "backfilled": (_mpe_r or {}).get("backfilled", 0),
            "duration_ms": round((_time.monotonic() - _t_mpe) * 1000),
        }
    except asyncio.TimeoutError:
        rezultati["reap_missing_pipeline_events"] = {"status": "timeout", "greska": "Prekoraceno 60s",
                                                       "duration_ms": round((_time.monotonic() - _t_mpe) * 1000)}
        _broj_grešaka += 1
    except Exception as _mpee:
        rezultati["reap_missing_pipeline_events"] = {"status": "greska", "greska": str(_mpee)[:120],
                                                       "duration_ms": round((_time.monotonic() - _t_mpe) * 1000)}
        _broj_grešaka += 1

    # ── Modul 9a2: Phoenix Closure (LIVINGSYS-DEBT-042 sub-item) — reap missing
    # ROCISTE_ZAKAZANO events, same shape as reap_missing_pipeline_events above ──
    _t_mre = _time.monotonic()
    try:
        from services.event_bus import reap_missing_rociste_events
        _mre_r = await asyncio.wait_for(reap_missing_rociste_events(), timeout=60)
        _stavke_obradjene += int((_mre_r or {}).get("backfilled", 0))
        rezultati["reap_missing_rociste_events"] = {
            "status": "ok",
            "checked": (_mre_r or {}).get("checked", 0),
            "backfilled": (_mre_r or {}).get("backfilled", 0),
            "duration_ms": round((_time.monotonic() - _t_mre) * 1000),
        }
    except asyncio.TimeoutError:
        rezultati["reap_missing_rociste_events"] = {"status": "timeout", "greska": "Prekoraceno 60s",
                                                      "duration_ms": round((_time.monotonic() - _t_mre) * 1000)}
        _broj_grešaka += 1
    except Exception as _mree:
        rezultati["reap_missing_rociste_events"] = {"status": "greska", "greska": str(_mree)[:120],
                                                      "duration_ms": round((_time.monotonic() - _t_mre) * 1000)}
        _broj_grešaka += 1

    # ── Modul 9b: BLACKSWAN-CRIT-001 — reap orphan draft fakture ─────────────
    _t_bf = _time.monotonic()
    try:
        from routers.billing import reap_orphan_fakture
        _bf_r = await asyncio.wait_for(reap_orphan_fakture(), timeout=60)
        _stavke_obradjene += int((_bf_r or {}).get("reaped", 0))
        rezultati["reap_orphan_fakture"] = {
            "status": "ok",
            "checked": (_bf_r or {}).get("checked", 0),
            "reaped": (_bf_r or {}).get("reaped", 0),
            "duration_ms": round((_time.monotonic() - _t_bf) * 1000),
        }
    except asyncio.TimeoutError:
        rezultati["reap_orphan_fakture"] = {"status": "timeout", "greska": "Prekoraceno 60s",
                                             "duration_ms": round((_time.monotonic() - _t_bf) * 1000)}
        _broj_grešaka += 1
    except Exception as _bfe:
        rezultati["reap_orphan_fakture"] = {"status": "greska", "greska": str(_bfe)[:120],
                                             "duration_ms": round((_time.monotonic() - _t_bf) * 1000)}
        _broj_grešaka += 1

    # ── Modul 10: KORAK B — Autonomni Background Action Agenti (2026-07-24) ─
    _t_ba = _time.monotonic()
    try:
        from workers.background_agents import run_background_agents
        _ba_r = await asyncio.wait_for(run_background_agents(run_id), timeout=600)
        _ba_preporuke = sum(
            int(v.get("preporuke_kreirane", 0)) for v in (_ba_r or {}).get("po_agentu", {}).values()
        )
        _stavke_obradjene += _ba_preporuke
        _broj_grešaka += int((_ba_r or {}).get("greske", 0))
        rezultati["background_agents"] = {
            **(_ba_r or {}), "status": "ok",
            "duration_ms": round((_time.monotonic() - _t_ba) * 1000),
        }
    except asyncio.TimeoutError:
        rezultati["background_agents"] = {"status": "timeout", "greska": "Prekoraceno 600s",
                                           "duration_ms": round((_time.monotonic() - _t_ba) * 1000)}
        _broj_grešaka += 1
    except Exception as _bae:
        rezultati["background_agents"] = {"status": "greska", "greska": str(_bae)[:120],
                                           "duration_ms": round((_time.monotonic() - _t_ba) * 1000)}
        _broj_grešaka += 1

    # ── Heartbeat (uvek se izvršava, bez obzira na greške iznad) ────────────
    _ts = _dt.now(_tz.utc).isoformat()
    _duration_ms = round((_time.monotonic() - _t_start) * 1000)
    try:
        import hashlib as _hl, json as _json
        _audit = {
            "run_id": run_id,
            "ts": _ts,
            "duration_ms": _duration_ms,
            "stavke": _stavke_obradjene,
            "greske": _broj_grešaka,
            "moduli": {k: v.get("status", "?") for k, v in rezultati.items() if isinstance(v, dict) and k != "run_id"},
        }
        _hash = _hl.sha256(_json.dumps(_audit, default=str).encode()).hexdigest()[:32]
        _supa_hb = _get_supa()
        await asyncio.to_thread(
            lambda: _supa_hb.table("chain_anchors").upsert({
                "id":           "cron_daily_heartbeat",
                "hash_256":     _hash,
                "record_count": _stavke_obradjene,
                "anchored_at":  _ts,
            }).execute()
        )
        await asyncio.to_thread(
            lambda: _supa_hb.table("chain_anchors").upsert({
                "id":           f"cron_run_{_run_date}",
                "hash_256":     _json.dumps(_audit, default=str)[:500],
                "record_count": _stavke_obradjene,
                "anchored_at":  _ts,
            }).execute()
        )
        rezultati["heartbeat"] = {
            "ok": _broj_grešaka == 0,
            "run_id": run_id,
            "duration_ms": _duration_ms,
            "stavke_obradjene": _stavke_obradjene,
            "broj_gresaka": _broj_grešaka,
            "status": "ok",
        }
    except Exception as _he:
        rezultati["heartbeat"] = {"ok": False, "status": "greska", "greska": str(_he)[:100]}

    # ── cron_runs: upiši ishod (nezavisno od heartbeat bloka iznad) ──────────
    try:
        _cr_status = "ok" if _broj_grešaka == 0 else "partial"
        await asyncio.to_thread(
            lambda: _get_supa().table("cron_runs").upsert({
                "run_id":          run_id,
                "started_at":      _now.isoformat(),
                "finished_at":     _dt.now(_tz.utc).isoformat(),
                "duration_ms":     _duration_ms,
                "status":          _cr_status,
                "processed_items": _stavke_obradjene,
                "errors_count":    _broj_grešaka,
                "moduli":          {k: v.get("status", "?") for k, v in rezultati.items() if isinstance(v, dict) and k != "run_id"},
            }).execute()
        )
    except Exception as _cre:
        logger.warning("[CRON_DAILY] cron_runs upis greška: %s", _cre)

    logger.info(
        "[CRON_DAILY] run_id=%s | %s | %dms | %d stavki | %d grešaka | moduli: %s",
        run_id, _ts, _duration_ms, _stavke_obradjene, _broj_grešaka,
        {k: v.get("status", "?") for k, v in rezultati.items() if isinstance(v, dict)},
    )
    return {"ok": _broj_grešaka == 0, "run_id": run_id, "timestamp": _ts, **rezultati}


@app.get("/api/admin/kpi")
@limiter.limit("10/minute")
async def admin_kpi(request: Request, user: dict = Depends(get_current_user)):
    """
    Founder-only endpoint: vraća 7 KPI metrika u realnom vremenu.
    Metrike se akumuliraju od poslednjeg restarta servera.
    """
    if not _is_founder(user.get("email", "")):
        raise HTTPException(status_code=403, detail="Restricted.")

    def _stats(dq: _deque) -> dict:
        if not dq:
            return {"avg_ms": None, "p95_ms": None, "n": 0, "ok": None}
        s = sorted(dq)
        avg = int(sum(s) / len(s))
        p95 = s[min(int(len(s) * 0.95), len(s) - 1)]
        return {"avg_ms": avg, "p95_ms": p95, "n": len(s), "ok": None}

    def _annotate(stats: dict, cilj_ms: int) -> dict:
        avg = stats.get("avg_ms")
        stats["cilj_ms"] = cilj_ms
        if avg is not None:
            stats["ok"] = avg <= cilj_ms
        return stats

    week_ago  = _time.time() - 7 * 86400
    greske_7d = sum(1 for ts in _ERR_LOG if ts > week_ago)

    supa     = _get_supa()
    week_iso = (datetime.utcnow() - timedelta(days=7)).isoformat()
    au_r = await asyncio.to_thread(
        lambda: supa.table("usage_events")
                     .select("user_id")
                     .gte("created_at", week_iso)
                     .execute()
    )
    aktivni_7d = len(set(r["user_id"] for r in (au_r.data or []) if r.get("user_id")))

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "uptime":    "prati https://dashboard.render.com",
        "copilot":         _annotate(_stats(_PERF["copilot"]),     10_000),
        "upload_dokumenta": _annotate(_stats(_PERF["upload"]),      5_000),
        "kreiranje_predmeta": _annotate(_stats(_PERF["predmet_new"]), 2_000),
        "ccc_load":        _annotate(_stats(_PERF["ccc"]),          2_000),
        "greske_7d":       {"vrednost": greske_7d, "cilj": 1, "ok": greske_7d <= 1},
        "aktivni_korisnici_7d": {"vrednost": aktivni_7d},
        "napomena": "Timing metrike se resetuju pri restartu. Prikupljaju se automatski od prvog zahteva.",
    }


# ─── CSP Violation Report Endpoint ───────────────────────────────────────────

@app.post("/api/security/csp-report")
async def csp_violation_report(request: Request):
    """
    Prima Content Security Policy violation reportove iz browsera.
    Loguje u security_events tabelu i Python logger.
    Ne zahteva autentifikaciju — browser šalje automatski.
    """
    try:
        body = await request.json()
        report = body.get("csp-report", body)

        blocked_uri   = report.get("blocked-uri", "")
        violated_dir  = report.get("violated-directive", "")
        document_uri  = report.get("document-uri", "")
        source_file   = report.get("source-file", "")

        logger.warning(
            "[CSP] violation: directive=%s blocked=%s source=%s",
            violated_dir, blocked_uri[:100], source_file[:100],
        )

        # Upiši u security_events (fire-and-forget)
        import hashlib as _hl
        ip = request.client.host if request.client else None
        ip_hash = _hl.sha256((ip or "").encode()).hexdigest()[:16] if ip else None

        await asyncio.to_thread(
            lambda: _get_supa().table("security_events").insert({
                "event_type": "csp_violation",
                "ip_hash": ip_hash,
                "details": {
                    "blocked_uri":   blocked_uri[:200],
                    "violated_dir":  violated_dir[:100],
                    "document_uri":  document_uri[:200],
                    "source_file":   source_file[:200],
                },
            }).execute()
        )
    except Exception as e:
        logger.debug("[CSP] report parse greška: %s", e)
    return JSONResponse(status_code=204, content=None)


@app.get("/api/admin/security/audit-verify")
@limiter.limit("2/minute")
async def admin_audit_verify(request: Request, user: dict = Depends(get_current_user)):
    """
    Founder-only: verifikuje integritet hash-chain audit loga.
    Skenira poslednjih 1000 zapisa i proveri da li je lanac nepolupan.
    """
    if not _is_founder(user.get("email", "")):
        raise HTTPException(status_code=403, detail="Restricted.")
    from shared.audit_immutable import verify_chain_integrity
    result = await verify_chain_integrity(limit=1000)
    return {
        "timestamp": datetime.utcnow().isoformat(),
        **result,
    }


@app.get("/api/admin/security/agents")
async def admin_agent_permissions(
    x_admin_key: str = Header(default=""),
    user: dict = Depends(get_current_user),
):
    """Founder-only: pregled dozvola svih AI agenata."""
    if not _is_founder(user.get("email", "")):
        raise HTTPException(status_code=403, detail="Restricted.")
    from security.agent_isolation import get_agent_permissions_summary
    return {"agents": get_agent_permissions_summary()}


@app.post("/api/admin/security/anchor-today")
@limiter.limit("4/hour")
async def admin_anchor_today(request: Request, user: dict = Depends(get_current_user)):
    """Founder-only: sidri dnevni root hash audit lanca na nezavisnoj lokaciji."""
    if not _is_founder(user.get("email", "")):
        raise HTTPException(status_code=403, detail="Restricted.")
    from security.chain_anchor import anchor_today
    result = await anchor_today()
    return {"timestamp": datetime.utcnow().isoformat(), **result}


@app.get("/api/admin/security/anchor-verify/{target_date}")
@limiter.limit("10/minute")
async def admin_anchor_verify(
    target_date: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Founder-only: verifikuje integritet audit lanca za dati datum (YYYY-MM-DD)."""
    if not _is_founder(user.get("email", "")):
        raise HTTPException(status_code=403, detail="Restricted.")
    import re
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", target_date):
        raise HTTPException(status_code=400, detail="Format datuma mora biti YYYY-MM-DD.")
    from security.chain_anchor import verify_anchor
    result = await verify_anchor(target_date)
    return {"timestamp": datetime.utcnow().isoformat(), **result}


@app.get("/test-pinecone")
async def test_pinecone(x_admin_key: str = Header(default="")):
    admin_key = os.getenv("ADMIN_DEBUG_KEY", "")
    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=404, detail="Not found")
    def _run():
        try:
            from pinecone import Pinecone
            from langchain_openai import OpenAIEmbeddings
            from app.services.retrieve import EMBEDDING_MODEL
            pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
            index = pc.Index("vindex-ai")
            stats = index.describe_index_stats()
            emb = OpenAIEmbeddings(model=EMBEDDING_MODEL)
            vektor = emb.embed_query("ugovor o radu otkaz")
            test_results = index.query(
                vector=vektor,
                top_k=3,
                include_metadata=True
            )
            return {
                "total_vectors": stats.total_vector_count,
                "vector_dim": len(vektor),
                "test_query_matches": len(test_results.matches),
                "first_match_metadata": test_results.matches[0].metadata
                    if test_results.matches else "NEMA REZULTATA"
            }
        except Exception as e:
            return {"error": type(e).__name__, "message": str(e)}
    return await asyncio.to_thread(_run)


@app.get("/test-zdi")
async def test_zdi_indeksiranost(x_admin_key: str = Header(default="")):
    """
    Proverava da li su ključni članovi ZDI (2, 74, 75, 78) indeksirani u Pinecone.
    Vraća status svakog člana: pronađen/nije pronađen.
    """
    admin_key = os.getenv("ADMIN_DEBUG_KEY", "")
    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=404, detail="Not found")
    def _run():
        try:
            from app.services.retrieve import proveri_zdi_indeksiranost
            rezultat = proveri_zdi_indeksiranost()
            svi_ok = all(rezultat.values())
            return {
                "status": "ok" if svi_ok else "upozorenje",
                "poruka": "Svi ključni ZDI članovi su indeksirani." if svi_ok
                          else "Neki ZDI članovi NISU pronađeni u Pinecone indeksu — reindeksiranje preporučeno.",
                "clanovi": rezultat,
            }
        except Exception as e:
            return {"status": "error", "error": type(e).__name__, "message": str(e)}
    return await asyncio.to_thread(_run)


@app.get("/api/diagnose")
async def diagnose(x_admin_key: str = Header(default="")):
    """Testira konekciju sa Pinecone i OpenAI — sve u thread-u da ne blokira event loop."""
    admin_key = os.getenv("ADMIN_DEBUG_KEY", "")
    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=404, detail="Not found")

    def _run_checks():
        result = {}
        try:
            from openai import OpenAI as _OAI
            c = _OAI(api_key=os.getenv("OPENAI_API_KEY"))
            c.models.list()
            result["openai"] = "OK"
        except Exception as e:
            result["openai"] = f"GREŠKA: {type(e).__name__}: {str(e)[:200]}"

        try:
            from pinecone import Pinecone as _PC
            pc = _PC(api_key=os.getenv("PINECONE_API_KEY"))
            idx = pc.Index("vindex-ai")
            stats = idx.describe_index_stats()
            result["pinecone"] = f"OK — {stats.total_vector_count} vektora"
        except Exception as e:
            result["pinecone"] = f"GREŠKA: {type(e).__name__}: {str(e)[:200]}"

        try:
            from langchain_openai import OpenAIEmbeddings
            from app.services.retrieve import EMBEDDING_MODEL
            emb = OpenAIEmbeddings(model=EMBEDDING_MODEL)
            vec = emb.embed_query("test")
            result["embeddings"] = f"OK — dim={len(vec)}"
        except Exception as e:
            result["embeddings"] = f"GREŠKA: {type(e).__name__}: {str(e)[:200]}"

        return result

    return await asyncio.to_thread(_run_checks)


# Javne stranice koje ulaze u sitemap. Redosled je i redosled u XML-u.
# Prvi element para je putanja, drugi je prioritet.
_SITEMAP_PUTANJE: list[tuple[str, str]] = [
    ("/", "1.0"),
    ("/kako-radi", "0.9"),
    ("/sposobnosti", "0.9"),
    ("/za-advokate", "0.9"),
    ("/web3", "0.9"),
    ("/bezbednost", "0.8"),
    ("/vizija", "0.7"),
    ("/tehnologija", "0.7"),
    ("/beta", "0.8"),
    ("/kontakt", "0.6"),
    # Postojece pravne stranice -- vec javne, servirane iz ruta iznad.
    ("/privacy", "0.4"),
    ("/terms", "0.4"),
    ("/security", "0.4"),
    ("/dpa", "0.3"),
    ("/ai-disclosure", "0.3"),
    ("/bezbednosni-list", "0.3"),
]


def _sajt_osnovni_url(request: Request) -> str:
    """Osnovni URL bez zavrsne kose crte, izveden iz zahteva.

    Domen se namerno NE hardkoduje: isti kod tada radi i na vindex.rs i na
    staging domenu, bez izmene konfiguracije kad se domen promeni.
    """
    return str(request.base_url).rstrip("/")


@app.get("/robots.txt")
def robots(request: Request):
    osnovni = _sajt_osnovni_url(request)
    return PlainTextResponse(
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        f"\nSitemap: {osnovni}/sitemap.xml\n",
        media_type="text/plain",
    )


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap(request: Request):
    osnovni = _sajt_osnovni_url(request)
    stavke = "".join(
        f"  <url><loc>{osnovni}{putanja}</loc>"
        f"<changefreq>weekly</changefreq>"
        f"<priority>{prioritet}</priority></url>\n"
        for putanja, prioritet in _SITEMAP_PUTANJE
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{stavke}"
        "</urlset>\n"
    )
    return PlainTextResponse(
        xml,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


def _serve_index_html():
    from fastapi.responses import Response
    html = _INDEX_HTML_BYTES or _load_index_html()
    if not html:
        return greska_odgovor(404, "Frontend nije pronađen.")
    return Response(
        content=html,
        media_type="text/html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Build": _GIT_HASH,
        },
    )


@app.get("/app")
def serve_html():
    return _serve_index_html()


@app.get("/portal", include_in_schema=False)
def serve_portal():
    """Klijentski portal — stranica za klijente, pristup putem tokena."""
    path = BASE_DIR / "client_portal.html"
    if path.exists():
        return FileResponse(str(path), headers={"Cache-Control": "no-cache"})
    return _serve_index_html()


@app.get("/api/portal/predmet")
@limiter.limit("20/minute")
async def portal_predmet_data(request: Request, token: str):
    """
    Vraća podatke o predmetu za klijentski portal.
    Zaštićen vremenskim tokenom iz privremeni_pristup tabele (secrets.token_urlsafe(32),
    generisan u routers/saradnja.py — kriptografski jak, 256-bit entropija).
    Nije potrebna autentifikacija — pristup je kontrolisan tokenom. Rate limit je
    dodatna odbrana u dubini (defense-in-depth), ne osnovna zaštita.
    """
    from datetime import datetime, timezone

    if not token or len(token) < 10:
        raise HTTPException(status_code=400, detail="Neispravan token.")

    supa = _get_supa()

    tok_r = await asyncio.to_thread(
        lambda: supa.table("privremeni_pristup")
            .select("*")
            .eq("token", token)
            .eq("iskoriscen", False)
            .maybe_single()
            .execute()
    )

    if not tok_r.data:
        raise HTTPException(status_code=404, detail="Token nije pronađen ili je iskorišćen.")

    tok = tok_r.data
    istice = tok.get("istice_u")
    if istice:
        istice_dt = datetime.fromisoformat(istice.replace("Z", "+00:00"))
        if istice_dt < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Link je istekao. Kontaktirajte advokata za novi link.")

    predmet_id      = tok.get("predmet_id")
    vlasnik_user_id = tok.get("vlasnik_user_id")

    pred_r, rok_r, advokat_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmeti").select("*").eq("id", predmet_id).maybe_single().execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("rokovi")
                .select("naziv, datum, tip")
                .eq("predmet_id", predmet_id)
                .gte("datum", datetime.now(timezone.utc).date().isoformat())
                .order("datum")
                .limit(10)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("profiles")
                .select("email")
                .eq("id", vlasnik_user_id)
                .maybe_single()
                .execute()
        ),
    )

    predmet = pred_r.data  or {}
    rokovi  = rok_r.data   or []
    advokat = advokat_r.data or {}

    ai_status = "Predmet je aktivan. Advokat aktivno radi na slučaju."
    try:
        from openai import OpenAI as _OAI
        _oai = _OAI(api_key=os.environ["OPENAI_API_KEY"])
        naziv  = predmet.get("naziv", "Predmet")
        status = predmet.get("status", "aktivan")
        ai_r   = await asyncio.to_thread(
            _pozovi_openai_sync_api,
            _oai,
            model="gpt-4o-mini",
            messages=[{"role": "user", "content":
                f"Napiši kratku, profesionalnu poruku za klijenta o statusu predmeta '{naziv}' "
                f"(status: {status}). Jedna do dve rečenice. Bez pravnih saveta. Ekavica. Ne pominjaj AI."}],
            max_tokens=100,
            temperature=0.4,
        )
        ai_status = ai_r.choices[0].message.content.strip()
    except Exception as _ai_status_exc:
        _sentry_capture(_ai_status_exc)

    return {
        "naziv":         predmet.get("naziv", "Predmet"),
        "status":        predmet.get("status", "aktivan"),
        "stranka":       predmet.get("stranka"),
        "datum_otvoren": predmet.get("created_at"),
        "ai_status":     ai_status,
        "rokovi":        rokovi,
        "dokumenti":     [],
        "advokat_ime":   advokat.get("ime", "Advokat"),
        "advokat_email": advokat.get("email"),
    }


@app.get("/sw.js", include_in_schema=False)
def serve_sw():
    """Service Worker mora biti na root scope-u da bi mogao da interceptuje /app i /api/*."""
    from fastapi.responses import FileResponse as _FR
    sw_path = BASE_DIR / "static" / "sw.js"
    return _FR(str(sw_path), media_type="application/javascript", headers={
        "Service-Worker-Allowed": "/",
        "Cache-Control": "no-cache, no-store, must-revalidate",
    })


@app.get("/manifest.json", include_in_schema=False)
def serve_manifest():
    from fastapi.responses import FileResponse as _FR
    return _FR(str(BASE_DIR / "static" / "manifest.json"), media_type="application/manifest+json")


@app.get("/offline", include_in_schema=False)
def serve_offline():
    return _serve_index_html()


# ─── Auth endpointi ───────────────────────────────────────────────────────────


class RegisterReq(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def ocisti_email(cls, v: str) -> str:
        return v.strip().lower()


@app.post("/api/register")
@limiter.limit("5/minute")
async def register(req: RegisterReq, request: Request):
    """
    Registracija novog korisnika koristeći Supabase Admin API (service key).
    Kreira korisnika sa email_confirm=True — zaobilaži email potvrdu.
    Vraća user_id i access_token ako je registracija uspešna.
    """
    if _is_disposable_email(req.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Privremene email adrese nisu dozvoljene.",
        )

    def _do_register():
        supa = _get_supa()
        try:
            # Admin create — ne šalje confirmation email, auto-confirms
            result = supa.auth.admin.create_user({
                "email": req.email,
                "password": req.password,
                "email_confirm": True,
            })
            if not result or not result.user:
                raise ValueError("Supabase admin.create_user nije vratio korisnika.")
            user_id = result.user.id
            logger.info("Registracija uspešna: uid=%.8s email=%s", user_id, req.email)

            # Kreira user_credits red sa 15 kredita (trigger to radi automatski,
            # ali _sb_ensure_credits_row je safety net).
            # ignore_duplicates=True — nikad ne resetuje existeći balans.
            _sb_ensure_credits_row(user_id, BESPLATNI_KREDITI)
            # Kreira profil (email + is_pro=false) — bez credits_remaining
            try:
                supa.table("profiles").upsert(
                    {"id": user_id, "email": req.email},
                    on_conflict="id",
                ).execute()
            except Exception as prof_err:
                logger.warning("Profil nije kreiran odmah: %s", prof_err)

            # Prijavi korisnika da dobije token
            login_result = supa.auth.sign_in_with_password({
                "email": req.email,
                "password": req.password,
            })
            session = getattr(login_result, "session", None)
            access_token = session.access_token if session else None
            return {
                "status": "ok",
                "user_id": user_id,
                "access_token": access_token,
                "credits_remaining": BESPLATNI_KREDITI,
            }

        except Exception as exc:
            err_str = str(exc)
            logger.warning("Registracija neuspešna: email=%s greška=%s", req.email, err_str)
            if "already registered" in err_str.lower() or "already been registered" in err_str.lower():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email adresa je već registrovana. Prijavite se.",
                )
            if "password" in err_str.lower() and "weak" in err_str.lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Lozinka je preslaba. Koristite najmanje 8 karaktera.",
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Registracija nije uspela. Pokušajte ponovo ili kontaktirajte podršku.",
            )

    try:
        result = await asyncio.to_thread(_do_register)
        # S1-1: both were unreferenced fire-and-forget. A redeploy in the seconds
        # after signup left the user permanently with no plan, no trial_kraj and
        # onboarding_done unset, with nothing to reconcile it.
        from shared.bg import spawn as _spawn_bg
        _spawn_bg(asyncio.to_thread(send_welcome_email, result["user_id"], req.email),
                  name="register:welcome_email")
        _spawn_bg(_setup_trial(_get_supa(), result["user_id"]), name="register:setup_trial")
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Neočekivana greška u /api/register")
        raise HTTPException(status_code=500, detail="Greška servera. Pokušajte ponovo.")


async def _setup_trial(supa, user_id: str) -> None:
    """Postavi 30-dnevni trial za novog korisnika."""
    from datetime import datetime, timezone, timedelta
    trial_kraj = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    try:
        await asyncio.to_thread(
            lambda: supa.table("profiles").update({
                "plan":            "trial",
                "trial_kraj":      trial_kraj,
                "onboarding_done": False,
            }).eq("id", user_id).execute()
        )
    except Exception as e:
        logger.warning("Trial setup greška: %s", e)


@app.post("/api/auth/onboarding/complete")
async def onboarding_complete(
    payload: dict,
    user: dict = Depends(get_current_user),
):
    """Označi onboarding kao završen i sačuvaj početne podatke firme."""
    uid = user["user_id"]
    supa = _get_supa()
    update_data: dict = {"onboarding_done": True}
    if payload.get("naziv_firme"):
        update_data["naziv_firme"] = str(payload["naziv_firme"])[:100]
    if payload.get("specijalizacija"):
        update_data["specijalizacija"] = str(payload["specijalizacija"])[:100]
    try:
        await asyncio.to_thread(
            lambda: supa.table("profiles").update(update_data).eq("id", uid).execute()
        )
    except Exception as e:
        logger.warning("Onboarding complete greška: %s", e)
    return {"ok": True, "message": "Dobrodošli u Vindex AI!"}


@app.get("/api/auth/trial/status")
async def trial_status(user: dict = Depends(get_current_user)):
    """Vraća status triala i onboarding flag."""
    from datetime import datetime, timezone
    uid = user["user_id"]
    supa = _get_supa()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("profiles").select("plan, trial_kraj, onboarding_done").eq("id", uid).maybe_single().execute()
        )
        if r and r.data:
            plan = r.data.get("plan", "trial")
            trial_kraj_str = r.data.get("trial_kraj")
            dani_ostalo = None
            if trial_kraj_str and plan == "trial":
                try:
                    trial_kraj_dt = datetime.fromisoformat(trial_kraj_str.replace("Z", "+00:00"))
                    dani_ostalo = max(0, (trial_kraj_dt - datetime.now(timezone.utc)).days)
                except Exception:
                    dani_ostalo = 30
            return {
                "plan":           plan,
                "trial_aktivan":  plan == "trial" and (dani_ostalo is None or dani_ostalo > 0),
                "dani_ostalo":    dani_ostalo,
                "onboarding_done": r.data.get("onboarding_done", True),
            }
    except Exception as e:
        logger.debug("Trial status greška: %s", e)
    return {"plan": "trial", "trial_aktivan": True, "dani_ostalo": 30, "onboarding_done": True}


@app.post("/api/logout")
async def logout(user: dict = Depends(get_current_user), request: Request = None):
    """Invaliduje sve aktivne sesije korisnika na Supabase nivou.
    Čak i ako klijent drži JWT token, Supabase get_user() poziv će ga odbiti.
    """
    uid = user["user_id"]
    try:
        supa = _get_supa()
        await asyncio.to_thread(lambda: supa.auth.admin.sign_out(uid))
        logger.info("[LOGOUT] sve sesije invalidovane uid=%.8s", uid)
    except Exception as e:
        logger.warning("[LOGOUT] sign_out partial fail uid=%.8s: %s", uid, e)

    from shared.audit_immutable import log_action as _imm_log
    ip = request.client.host if request and request.client else None
    asyncio.create_task(_imm_log("logout", user_id=uid, ip=ip))

    return {"ok": True, "poruka": "Odjavili ste se sa svih uređaja."}


@app.get("/api/me")
async def me(user: dict = Depends(get_current_user)):
    """Vraća podatke o prijavljenom korisniku, kredite i PRO status."""
    try:
        email = user.get("email", "")
        profil = await asyncio.to_thread(_ensure_profile, user["user_id"], email)
        founder = _is_founder(email)
        # Founder uvek vidi 9999 — frontend nikad ne prikazuje paywall
        credits = 9999 if founder else profil["credits_remaining"]
        return {
            "user_id":           user["user_id"],
            "email":             email,
            "credits_remaining": credits,
            "credits_total":     9999 if founder else BESPLATNI_KREDITI,
            "is_pro":            profil["is_pro"],
            "is_founder":        founder,
            "digitalna_imovina_aktivirano": profil.get("digitalna_imovina_aktivirano", False),
            "digitalna_imovina_standalone": profil.get("digitalna_imovina_standalone", False),
        }
    except Exception as exc:
        logger.exception("Greška u /api/me za korisnika %s", user.get("user_id"))
        raise HTTPException(status_code=500, detail=f"Greška profila: {exc!r}")


@app.get("/api/credits-debug")
async def credits_debug(user: dict = Depends(get_current_user)):
    """
    Dijagnoza kredit sistema za prijavljenog korisnika.
    Proverava da li tabela, red i RPC funkcija postoje i rade ispravno.
    """
    user_id = user["user_id"]
    email   = user.get("email", "")
    supa    = _get_supa()
    out: dict = {"user_id": user_id, "email": email}

    # 1. Da li tabela user_credits postoji?
    try:
        r = supa.table("user_credits").select("id").limit(0).execute()
        out["table_user_credits"] = "OK — tabela postoji"
    except Exception as exc:
        out["table_user_credits"] = f"GREŠKA: {type(exc).__name__}: {str(exc)[:300]}"

    # 2. Da li ovaj korisnik ima red u user_credits?
    try:
        r = supa.table("user_credits").select("*").eq("user_id", user_id).execute()
        out["user_credits_row"] = r.data if r.data else "NEMA REDA — trigger nije kreirao red ili SQL nije pokrenut"
    except Exception as exc:
        out["user_credits_row"] = f"GREŠKA: {type(exc).__name__}: {str(exc)[:300]}"

    # 3. Da li profiles tabela postoji i ima red za ovog korisnika?
    try:
        r = supa.table("profiles").select("*").eq("id", user_id).execute()
        out["profiles_row"] = r.data if r.data else "NEMA REDA"
    except Exception as exc:
        out["profiles_row"] = f"GREŠKA: {type(exc).__name__}: {str(exc)[:300]}"

    # 4. Rezultat _ensure_profile (šta backend vidi za ovog korisnika)
    try:
        profil = await asyncio.to_thread(_ensure_profile, user_id, email)
        out["_ensure_profile"] = profil
    except Exception as exc:
        out["_ensure_profile"] = f"GREŠKA: {type(exc).__name__}: {str(exc)[:300]}"

    # 5. Provera kredit-RPC-a — STVARNO NEDESTRUKTIVNO.
    #
    # Beta Gate Credit System Closure (2026-08-08) — CRITICAL, reachable by
    # ANY authenticated user with no rate limit:
    #
    # This step used to call deduct_credit (a REAL -1 deduction, despite the
    # old comment claiming "dry-run: oduzima 0") and then "restore" the
    # balance with a blind ABSOLUTE write of a value read back in step 4:
    #     update({"credits_remaining": profil["credits_remaining"]})
    # That is a lost update by construction. Any charge committed between
    # step 4's read and this write was silently ERASED, so calling this
    # endpoint in a loop while running expensive AI operations restored the
    # pre-charge balance again and again -- unlimited free AI usage without
    # touching authentication. The same write also destroyed credits: if
    # step 4 raised, `profil` was unbound, the write raised NameError inside
    # a bare `except: pass`, and the user silently lost a credit per call.
    #
    # Migration 107 makes a genuinely non-destructive probe possible:
    # deduct_n_credits(uid, 0) hits the function's own `p_n <= 0` guard,
    # returns -1 and mutates NOTHING. Liveness is proven without touching a
    # single credit -- and, as a bonus, the return value distinguishes the
    # guarded body from the pre-107 one, so this endpoint now doubles as the
    # application-visible contract-drift detector whose absence let a
    # vulnerable function body sit in production while CI stayed green.
    try:
        r = supa.rpc("deduct_n_credits", {"p_user_id": user_id, "p_n": 0}).execute()
        if r.data == -1:
            out["credit_rpc"] = (
                "OK — deduct_n_credits postoji i ispravno odbija p_n=0 "
                "(ništa nije naplaćeno; migracija 107 je primenjena)"
            )
        else:
            out["credit_rpc"] = (
                f"KRITIČNO: deduct_n_credits(p_n=0) vratio {r.data!r}, očekivano -1 — "
                "migracija 107 NIJE primenjena, stara nezaštićena verzija je živa "
                "(trka za kredite je otvorena)"
            )
    except Exception as exc:
        out["credit_rpc"] = f"GREŠKA: {type(exc).__name__}: {str(exc)[:300]}"

    # 6. Dijagnoza
    diag = []
    if "GREŠKA" in str(out.get("table_user_credits", "")):
        diag.append("KRITIČNO: user_credits tabela ne postoji — pokrenite supabase_setup.sql u Supabase Dashboard")
    elif "NEMA REDA" in str(out.get("user_credits_row", "")):
        diag.append("UPOZORENJE: user_credits tabela postoji ali korisnik nema red — trigger nije radio ili SQL nije pokrenut")
    if "GREŠKA" in str(out.get("credit_rpc", "")):
        diag.append("KRITIČNO: deduct_n_credits RPC ne postoji — pokrenite supabase_setup.sql + migracije")
    elif "KRITIČNO" in str(out.get("credit_rpc", "")):
        diag.append(
            "KRITIČNO: migracija 107 nije primenjena — trka za kredite je otvorena u produkciji "
            "(pokrenite migrations/107_beta_gate_credit_race_closure.sql)"
        )
    if not diag:
        diag.append("Sve izgleda ispravno.")
    out["dijagnoza"] = diag

    return out


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


@app.get("/api/debug")
async def debug_env(x_admin_key: str = Header(default="")):
    """Dijagnostički endpoint — zaštićen admin ključem."""
    admin_key = os.getenv("ADMIN_DEBUG_KEY", "")
    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        import supabase as _supa_mod
        supa_version = getattr(_supa_mod, "__version__", "nepoznato")
    except ImportError:
        supa_version = "nije instalirano"
    conn_status = "nije testirano"
    try:
        supa = _get_supa()
        result = supa.table("profiles").select("id").limit(1).execute()
        conn_status = f"OK — {len(result.data)} redova"
    except Exception as e:
        conn_status = f"GREŠKA: {e!r}"
    return {
        "version": "2025-04-17-v4",
        "supabase_py_version": supa_version,
        "db_connection": conn_status,
    }


@app.get("/api/test-pitanje")
async def test_pitanje(q: str, x_admin_key: str = Header(default="")):
    """Dijagnostika pipeline-a — zaštićena admin ključem."""
    admin_key = os.getenv("ADMIN_DEBUG_KEY", "")
    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=404, detail="Not found")
    from app.services.retrieve import retrieve_documents
    from main import _filtriraj_kontekst
    # BUG FIX (2026-07-24): retrieve_documents vraća (docs, retrieval_meta),
    # ne samu listu -- ovaj admin dijagnostički endpoint je bio pogođen istom
    # greškom kao routers/drafting.py's /api/podnesak.
    docs, _retrieval_meta = retrieve_documents(q, k=10)
    filtrirani = _filtriraj_kontekst(docs)
    return {
        "pitanje": q,
        "pinecone_docs_count": len(docs),
        "filtrirani_count": len(filtrirani),
        "clanovi": [d[:120] for d in filtrirani],
    }


@app.get("/api/rag-test")
async def rag_test(q: str = "zakon o privrednim drustvima registracija", x_admin_key: str = Header(default="")):
    """
    Kompletan RAG dijagnostički endpoint.
    GET /api/rag-test?q=vaše+pitanje
    Header: X-Admin-Key: <ADMIN_DEBUG_KEY>

    Vraća:
    - env var status (API ključevi postavljeni ili ne)
    - Pinecone index stats (broj vektora)
    - retrieve_documents rezultati (svaki doc prikazan)
    - Šta bi ušlo u GPT prompt
    """
    admin_key = os.getenv("ADMIN_DEBUG_KEY", "")
    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=404, detail="Not found")

    def _run():
        out: dict = {
            "query": q,
            "env": {
                "PINECONE_API_KEY": bool(os.getenv("PINECONE_API_KEY")),
                "PINECONE_HOST":    os.getenv("PINECONE_HOST", "NIJE POSTAVLJEN"),
                "PINECONE_INDEX_NAME": os.getenv("PINECONE_INDEX_NAME", "vindex-ai (default)"),
                "OPENAI_API_KEY":   bool(os.getenv("OPENAI_API_KEY")),
            },
        }

        # 1. Pinecone index stats
        try:
            from app.services.retrieve import _get_index
            idx = _get_index()
            stats = idx.describe_index_stats()
            out["pinecone_stats"] = {
                "total_vectors":     stats.total_vector_count,
                "dimension":         stats.dimension,
                "namespaces":        str(stats.namespaces)[:300],
            }
        except Exception as exc:
            out["pinecone_stats"] = f"GREŠKA: {type(exc).__name__}: {str(exc)[:300]}"

        # 2. retrieve_documents
        try:
            from app.services.retrieve import retrieve_documents
            import time as _t
            t0 = _t.perf_counter()
            # BUG FIX (2026-07-24): ista greška kao gore -- retrieve_documents
            # vraća (docs, retrieval_meta) tuple.
            docs, retrieval_meta = retrieve_documents(q, k=6)
            elapsed = _t.perf_counter() - t0
            out["retrieve"] = {
                "elapsed_sec": round(elapsed, 2),
                "docs_count":  len(docs),
                "docs": [{"index": i, "length": len(d), "preview": d[:400]} for i, d in enumerate(docs)],
                "retrieval_meta": {k: v for k, v in retrieval_meta.items() if k not in ("doc_passages", "praksa_matches")},
            }
        except Exception as exc:
            out["retrieve"] = f"GREŠKA: {type(exc).__name__}: {str(exc)[:400]}"

        # 3. Šta bi ušlo u GPT prompt (filtrirani kontekst)
        try:
            from main import _filtriraj_kontekst
            filtrirani = _filtriraj_kontekst(docs if isinstance(docs, list) else [])
            kontekst = "\n\n---\n\n".join(filtrirani)
            out["kontekst_za_gpt"] = {
                "filtrirani_count": len(filtrirani),
                "ukupno_chars":     len(kontekst),
                "preview_500":      kontekst[:500],
            }
        except Exception as exc:
            out["kontekst_za_gpt"] = f"GREŠKA: {type(exc).__name__}: {str(exc)[:200]}"

        # 4. Dijagnoza
        diag = []
        if not out["env"]["PINECONE_API_KEY"]:
            diag.append("KRITIČNO: PINECONE_API_KEY nije postavljen na Render!")
        if not out["env"]["OPENAI_API_KEY"]:
            diag.append("KRITIČNO: OPENAI_API_KEY nije postavljen na Render!")
        if out["env"]["PINECONE_HOST"] == "NIJE POSTAVLJEN":
            diag.append("UPOZORENJE: PINECONE_HOST nije postavljen — konekcija ide putem API round-trip (sporije).")
        ps = out.get("pinecone_stats", {})
        if isinstance(ps, dict) and ps.get("total_vectors", 0) == 0:
            diag.append("KRITIČNO: Pinecone index je prazan — pokrenite ingest_kz_zpdg.py!")
        rt = out.get("retrieve", {})
        if isinstance(rt, dict) and rt.get("docs_count", 0) == 0:
            diag.append("KRITIČNO: retrieve_documents vratio 0 docs — Pinecone ne vraća rezultate.")
        if not diag:
            diag.append("Sve izgleda ispravno.")
        out["dijagnoza"] = diag

        return out

    return await asyncio.to_thread(_run)


@app.post("/api/check-email")
async def check_email(req: EmailCheckReq):
    """Proverava da li je email adresa jednokratna (disposable)."""
    if _is_disposable_email(req.email):
        return {"valid": False, "razlog": "Privremene email adrese nisu dozvoljene."}
    return {"valid": True}


# ─── AI endpointi (zahtevaju autentifikaciju i kredite) ───────────────────────

import hashlib as _hashlib

def _q_hash(tekst: str) -> str:
    """SHA-256 (16 hex) od pitanja — za log bez curenja sadržaja."""
    return _hashlib.sha256((tekst or "").encode()).hexdigest()[:16]


async def _audit(user_id: str, akcija: str, q_hash: str) -> None:
    """
    Beleži pristup bez čuvanja sadržaja: ko + kada + šta (hash).
    ZZPL čl. 5(1)(f) — integritet i poverljivost.
    Fire-and-forget — greška u audit-u ne blokira odgovor.
    Supabase tabela: audit_log(id uuid, user_id uuid, akcija text, q_hash text, ts timestamptz)
    SQL migracija: CREATE TABLE audit_log (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id UUID NOT NULL, akcija VARCHAR(50), q_hash VARCHAR(16), ts TIMESTAMPTZ DEFAULT NOW());
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


@app.post("/api/bot/ask")
@limiter.limit("120/minute")
async def bot_ask(req: PitanjeReq, request: Request, x_api_key: str = Header(default="")):
    """
    Internal endpoint for the Vindex Telegram bot.
    Authenticated via X-Api-Key header (BOT_API_KEY env var).
    Bypasses Supabase auth — the bot manages its own subscription logic.
    """
    bot_key = os.getenv("BOT_API_KEY", "").strip()
    if not bot_key or x_api_key != bot_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    qh = _q_hash(req.pitanje)
    logger.info("Bot pitanje [q=%s]", qh)
    try:
        rezultat = await pokreni(ask_agent, req.pitanje, None)
        return normalizuj_rezultat(rezultat)
    except Exception:
        logger.exception("Greška u /api/bot/ask [q=%s]", qh)
        return greska_odgovor(500, "Greška servera.")


# ─── F1.5: Konverzaciona memorija (ai_sessions, TTL=2h) ─────────────────────
_SESSION_TTL_HOURS = 2


async def _session_dohvati(supa, session_id: str, user_id: str) -> list[dict]:
    """Vraća poslednjih 5 razmena (10 poruka) iz tekuće sesije."""
    from datetime import datetime, timezone, timedelta
    if not session_id:
        return []
    try:
        ttl_from = (datetime.now(timezone.utc) - timedelta(hours=_SESSION_TTL_HOURS)).isoformat()
        result = await asyncio.to_thread(
            lambda: supa.table("ai_sessions")
                .select("uloga, sadrzaj")
                .eq("session_id", session_id)
                .eq("user_id", user_id)
                .gte("created_at", ttl_from)
                .order("created_at", desc=False)
                .limit(10)
                .execute()
        )
        return result.data or []
    except Exception as _se:
        logger.debug("[SESSION] dohvati greška: %s", _se)
        return []


async def _session_sacuvaj(supa, session_id: str, user_id: str, uloga: str, sadrzaj: str) -> None:
    """Čuva jednu poruku u ai_sessions. Fire-and-forget."""
    if not session_id or not sadrzaj:
        return
    try:
        await asyncio.to_thread(
            lambda: supa.table("ai_sessions").insert({
                "session_id": session_id,
                "user_id":    user_id,
                "uloga":      uloga,
                "sadrzaj":    sadrzaj[:4000],
            }).execute()
        )
    except Exception as _se:
        logger.debug("[SESSION] sacuvaj greška (tabela možda ne postoji): %s", _se)


@app.post("/api/pitanje")
@limiter.limit("30/minute")
async def pitanje(req: PitanjeReq, request: Request, user: dict = Depends(PermissionService.require("ai_pravna_pitanja"))):
    """Pravno istraživanje — pretražuje bazu zakona."""
    # BLACKSWAN-HIGH-004 fix (Operation Black Swan, Mission 001, Scenario 3): pokreni()'s
    # AI-concurrency semaphore raises HTTPException(503) on a 30s queue-wait timeout (many
    # requests piling up during slow OpenAI) -- the bare `except Exception:` below used to
    # catch that too and downgrade it to a generic 500, but the refund check only ever ran
    # on a NORMAL return from the try block, never in the except path. Credit stayed
    # deducted with nothing to show for it. Reproduced (real semaphore, real pokreni()):
    # consume_calls=2, refund_calls=0 across 2 concurrent calls where 1 hit the queue
    # timeout. Tracked explicitly so the except block can refund exactly when consume()
    # actually succeeded but nothing downstream did.
    _credit_consumed = False
    try:
        qh = _q_hash(req.pitanje)
        logger.info("Pitanje [uid=%.8s] [q=%s]", user["user_id"], qh)
        asyncio.create_task(_audit(user["user_id"], "pitanje", qh))

        # Atomično oduzmi kredit PRE agent poziva (isti timing kao stari require_credits
        # pre-deduction) — refunduje se ispod ako je odgovor iz keša ili blokiran.
        preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "ai_pravna_pitanja")
        _credit_consumed = True

        # ── Prompt injection detekcija ────────────────────────────────────────
        from security.prompt_guard import analyze as _guard_analyze
        from security.prompt_guard import truncate_safe as _guard_truncate
        from shared.audit_immutable import log_action as _imm_log

        _guard_result = await asyncio.to_thread(_guard_analyze, req.pitanje)
        if _guard_result.blocked:
            logger.warning(
                "[GUARD] BLOCKED pitanje uid=%.8s score=%.2f",
                user["user_id"], _guard_result.risk_score,
            )
            asyncio.create_task(_imm_log(
                "injection_attempt_blocked",
                user_id=user["user_id"],
                resource_type="pitanje",
                ip=request.client.host if request.client else None,
                metadata={"score": _guard_result.risk_score, "flags": _guard_result.flags[:5]},
            ))
            # SOA-006 (second-order audit, 2026-08-08): this is a NORMAL return,
            # so neither `except` handler below runs, and it sits ABOVE the
            # cache-hit/blocked refund check -- the credit consumed a few lines
            # earlier was simply kept. Zero AI work happened. A lawyer whose
            # case description trips a prompt-guard false positive paid for
            # every attempt. (The comment at the consume() call promises a
            # refund when "blokiran", but that refers to rezultat["blocked"]
            # from the agent, a different flag entirely.)
            await UsageService.refund(user["user_id"], user.get("email", ""), "ai_pravna_pitanja")
            _credit_consumed = False
            return greska_odgovor(400, "Zahtev sadrži neodgovarajući sadržaj i nije obrađen.")

        # Ograniči veličinu pre slanja AI-u
        req_pitanje_safe = _guard_truncate(req.pitanje)

        predmet_id = (req.predmet_id or "").strip() or None
        session_id = (req.session_id or "").strip() or None

        # F1.5: ako frontend nije poslao history, dohvati iz ai_sessions (2h TTL)
        history = [{"q": h.q, "a": h.a} for h in req.history] if req.history else None
        if not history and session_id:
            supa = _get_supa()
            sesija_redovi = await _session_dohvati(supa, session_id, user["user_id"])
            if sesija_redovi:
                # Konvertuj poruke u format koji ask_agent razume
                _hist: list[dict] = []
                for i in range(0, len(sesija_redovi) - 1, 2):
                    u_row = sesija_redovi[i]
                    a_row = sesija_redovi[i + 1] if i + 1 < len(sesija_redovi) else None
                    if u_row.get("uloga") == "user" and a_row and a_row.get("uloga") == "assistant":
                        _hist.append({"q": u_row["sadrzaj"], "a": a_row["sadrzaj"]})
                history = _hist[-3:] if _hist else None  # max 3 razmene kao i req.history

        # F5.4: inject predmet context when predmet_id is provided
        pitanje_za_agenta = req.pitanje
        if predmet_id:
            try:
                supa = _get_supa()
                beleske_res  = supa.table("predmet_beleske").select("sadrzaj").eq("predmet_id", predmet_id).eq("user_id", user["user_id"]).order("created_at", desc=True).limit(5).execute()
                istorija_res = supa.table("predmet_istorija").select("pitanje, odgovor").eq("predmet_id", predmet_id).eq("user_id", user["user_id"]).order("created_at", desc=True).limit(10).execute()
                beleske_tekst  = "\n".join(b["sadrzaj"] for b in (beleske_res.data or []) if b.get("sadrzaj"))
                istorija_tekst = "\n".join(
                    f"P: {r['pitanje']}\nO: {r['odgovor'][:300]}"
                    for r in (istorija_res.data or []) if r.get("pitanje")
                )
                if beleske_tekst or istorija_tekst:
                    delovi = []
                    if beleske_tekst:
                        delovi.append(f"Beleške:\n{beleske_tekst}")
                    if istorija_tekst:
                        delovi.append(f"Istorija razgovora:\n{istorija_tekst}")
                    extra_context = "KONTEKST PREDMETA:\n" + "\n\n".join(delovi)
                    pitanje_za_agenta = f"{extra_context}\n\nPITANJE: {req.pitanje}"
                    logger.info("[F5] predmet_id=%s context injected (%d beleški, %d istorija)", predmet_id, len(beleske_res.data or []), len(istorija_res.data or []))
            except Exception:
                logger.warning("[F5] predmet context load failed for predmet_id=%s — proceeding without", predmet_id)

        tip = await asyncio.to_thread(klasifikuj_pitanje, _skini_pii(req.pitanje))
        begin_cost_tracking()
        _firma_ns = await _get_firma_namespace(user["user_id"])
        _extra_ns = [_firma_ns] if _firma_ns else None
        _mem_ctx = await _fetch_firm_memory_context(user["user_id"], pitanje=req.pitanje)
        rezultat = await pokreni(ask_agent, pitanje_za_agenta, history, _extra_ns, _mem_ctx)
        asyncio.create_task(log_cost_to_db(user["user_id"], "pitanje"))
        # UsageService.consume() already pre-deducted the credit above (same timing as the
        # old require_credits pre-deduction) — refund on cache-hit/blocked/genuine LLM
        # failure (LAMBDA008-REL-001: ask_agent returns {"status":"error",...} rather than
        # raising on exhausted-retry OpenAI failure, so this must be checked explicitly —
        # otherwise a sustained outage burns a real credit on every failed request).
        if _treba_refundirati(rezultat):
            await UsageService.refund(user["user_id"], user.get("email", ""), "ai_pravna_pitanja")
            preostalo = preostalo + 1
        _credit_consumed = False  # accounted for above; the except block must not double-refund

        # F5.4: persist Q&A turn to predmet_istorija
        # CONF-010: kapija pre upisa, v. `_poseduje_predmet`. Namerno NE diže
        # 404 — odgovor je već proizveden i naplaćen, a strana čitanja ionako
        # nije vratila nikakav kontekst tuđeg predmeta. Odbija se samo upis,
        # jer je on jedina radnja koja ostavlja trag kod žrtve.
        _sme_istoriju = bool(predmet_id) and await asyncio.to_thread(
            _poseduje_predmet, user["user_id"], predmet_id
        )
        if predmet_id and not _sme_istoriju:
            logger.warning(
                "[SEC] CONF-010: odbijen upis u predmet_istorija — predmet %s nije korisnikov",
                predmet_id,
            )
        if _sme_istoriju and rezultat.get("status") == "success" and not rezultat.get("blocked"):
            try:
                _get_supa().table("predmet_istorija").insert({
                    "predmet_id": predmet_id,
                    "user_id":    user["user_id"],
                    "pitanje":    req.pitanje[:500],
                    "odgovor":    (rezultat.get("data") or "")[:3000],
                    "confidence": rezultat.get("confidence", ""),
                }).execute()
            except Exception:
                logger.warning("[F5] predmet_istorija save failed for predmet_id=%s", predmet_id)

        # F1.5: persist Q&A turn to ai_sessions (fire-and-forget)
        if session_id and rezultat.get("status") == "success" and not rezultat.get("blocked", False):
            ai_odgovor = (rezultat.get("data") or "").strip()
            if ai_odgovor:
                _supa = _get_supa()
                asyncio.create_task(_session_sacuvaj(_supa, session_id, user["user_id"], "user", req.pitanje))
                asyncio.create_task(_session_sacuvaj(_supa, session_id, user["user_id"], "assistant", ai_odgovor))

        resp = normalizuj_rezultat(rezultat, credits_remaining=max(preostalo, 0))
        if not resp.get("odgovor"):
            logger.error("[PITANJE] normalizuj_rezultat vratio prazan odgovor — rezultat=%s", rezultat)
            resp["odgovor"] = "Sistem nije mogao da formuliše odgovor. Pokušajte ponovo."
        return resp
    except HTTPException:
        # BLACKSWAN-HIGH-004: pokreni()'s own 503 (AI queue-timeout) is an intentional,
        # already-logged signal, not an unexpected server error -- let it propagate with
        # its real status code instead of being downgraded to a generic 500 below. The
        # credit-refund handling is identical either way (see the bare except).
        if _credit_consumed:
            await UsageService.refund(user["user_id"], user.get("email", ""), "ai_pravna_pitanja")
        raise
    except Exception:
        _qh_safe = locals().get("qh", "?")
        logger.exception("Greška u /api/pitanje [q=%s]", _qh_safe)
        if _credit_consumed:
            await UsageService.refund(user["user_id"], user.get("email", ""), "ai_pravna_pitanja")
        return greska_odgovor(
            500,
            "Došlo je do greške na serveru. Pokušajte ponovo za nekoliko sekundi.",
        )


@app.post("/api/pitanje/stream")
@limiter.limit("10/minute")
async def pitanje_stream(req: PitanjeReq, request: Request, user: dict = Depends(PermissionService.require("ai_pravna_pitanja"))):
    """
    SSE streaming verzija /api/pitanje.

    NAPOMENA (CELINA 3, 2026-07-24): Ovo NIJE token-level streaming direktno iz
    OpenAI-a. ask_agent() se izvršava do kraja (retrieval + guard/halucinacija
    provera + LLM poziv) PRE nego što se ijedan bajt pošalje klijentu — tek
    kompletan, guard-verifikovan odgovor se veštački deli na 80-karakterne
    delove za SSE isporuku. Ovo je namerna odluka (v. komentar "Guard-complete
    pipeline" u _event_generator ispod), ne bug: anti-halucinacijski/topic-drift
    guard mora da vidi ceo odgovor pre nego što bilo šta stigne do korisnika,
    što pravi token-streaming direktno iz OpenAI-a ne bi dozvoljavao.

    SSE format:
      data: <tekst chunk>\n\n
      data: [DONE]\n\n     — signal kraju
      data: [CREDITS:N]\n\n — preostali krediti
    """
    import json as _json
    import re as _re
    from main import (
        _skini_pii, _hash_za_log, klasifikuj_pitanje,
        SYSTEM_PROMPT_COMPLIANCE, SYSTEM_PROMPT_PORESKI,
        SYSTEM_PROMPT_PARNICA, SYSTEM_PROMPT_DEFINICIJA,
        _filtriraj_kontekst, retrieve_documents,
        _format_low_response, _format_medium_response,
        DISCLAIMER,
    )

    qh = _q_hash(req.pitanje)
    logger.info("PitanjeStream [uid=%.8s] [q=%s]", user["user_id"], qh)

    # ── Prompt injection detekcija ────────────────────────────────────────────
    # Governance Wave 2. Sestrinski `/api/pitanje` radi ovu proveru na :3045-3064;
    # streaming blizanac je nije imao i oslanjao se isključivo na SDK monkey-patch
    # (`shared/ai_client.py`) koji opali tek na samom GPT pozivu. Dve merene
    # posledice tog oslanjanja:
    #
    #   1. Napadački prompt bi PRE blokade bio embedovan i poslat Pinecone-u
    #      (`app/services/retrieve.py:610`) — `_tracked_embed` radi provenance,
    #      ali NE poziva `analyze()`. Sadržaj bi dakle već napustio sistem.
    #   2. Blokada sa nivoa SDK patch-a nema pristup autentifikovanom identitetu,
    #      pa fallback na `api.py:893-905` upisuje `user_id="unknown"`. Pokušaj
    #      injekcije ostajao je bez traga koji se može pripisati korisniku.
    #
    # Provera stoji PRE svakog dovlačenja i pre naplate, pa blokiran pokušaj ne
    # troši ni kredit ni embedding poziv.
    from security.prompt_guard import analyze as _guard_analyze_s
    from shared.audit_immutable import log_action as _imm_log_s

    _guard_s = await asyncio.to_thread(_guard_analyze_s, req.pitanje)
    if _guard_s.blocked:
        logger.warning(
            "[GUARD] BLOCKED pitanje/stream uid=%.8s score=%.2f",
            user["user_id"], _guard_s.risk_score,
        )
        asyncio.create_task(_imm_log_s(
            "injection_attempt_blocked",
            user_id=user["user_id"],
            resource_type="pitanje_stream",
            ip=request.client.host if request.client else None,
            metadata={"score": _guard_s.risk_score, "flags": _guard_s.flags[:5]},
        ))
        # 400 pre otvaranja SSE toka, ne greška unutar njega: klijent proverava
        # `res.ok` pre nego što počne da čita, pa poruka stiže kao poruka a ne
        # kao komad odgovora koji izgleda kao pravni sadržaj.
        return JSONResponse(
            status_code=400,
            content={"greska": "Zahtev je odbijen iz bezbednosnih razloga."},
        )
    asyncio.create_task(_audit(user["user_id"], "pitanje_stream", qh))
    _stream_firma_ns = await _get_firma_namespace(user["user_id"])
    _stream_extra_ns = [_stream_firma_ns] if _stream_firma_ns else None

    # Atomično oduzmi kredit PRE agent poziva (isti timing kao stari require_credits
    # pre-deduction) — refunduje se ispod ako je odgovor iz keša ili blokiran.
    _stream_preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "ai_pravna_pitanja")

    async def _event_generator():
        # Commit 4/T1: Guard-complete pipeline — all Commits (1+2+3) run inside ask_agent
        # before the first byte is sent to the client. Old direct-LLM path removed.
        #
        # SOA-012 (second-order audit, 2026-08-08): the credit is consumed
        # ABOVE this generator, but every refund path lived inside
        # `except Exception`. When the client disconnects mid-stream Starlette
        # closes the generator, which raises GeneratorExit / CancelledError --
        # both BaseException, NOT Exception -- so no refund ran at all.
        # Closing the browser tab on a slow answer silently cost a credit.
        # `_refunded` makes the refund idempotent across the three paths
        # (success-path condition, Exception, BaseException) so adding the
        # BaseException handler cannot double-refund.
        _refunded = False
        # B1/B2 (protivnicki pregled): `_refund_dugovan` je ODVOJEN od
        # `_delivered`. Zastita `not _delivered`, dodata zbog SE-007, gusila je
        # i LEGITIMAN ponovni pokusaj refundacije: kod kes-pogotka ili
        # `status="error"` prvi `refund()` moze da padne, `_refunded` ostane
        # `False`, a `except Exception` je onda odbijao da pokusa ponovo jer je
        # odgovor vec isporucen. Korisnik ostane naplacen za kesiran ili
        # neuspeo odgovor -- regresija u odnosu na `6fb4a99f`.
        #
        # Razlika je sustinska:
        #   `_delivered`      = da li je korisnik dobio tekst
        #   `_refund_dugovan` = da li mu po ugovoru SLEDUJE povracaj
        # Prekid veze gleda prvo; neuspeo upis povracaja gleda drugo.
        _refund_dugovan = False
        # NIGHT-005: set once the answer bytes have left the server. See the
        # disconnect handler at the bottom of this generator.
        _delivered = False
        try:
            history_obj = [{"q": h.q, "a": h.a} for h in req.history] if req.history else None

            _stream_mem_ctx = await _fetch_firm_memory_context(user["user_id"], pitanje=req.pitanje)
            rezultat = await pokreni(ask_agent, req.pitanje, history_obj, _stream_extra_ns, _stream_mem_ctx)

            if rezultat.get("status") == "success":
                data_text = rezultat.get("data", "")
            else:
                data_text = rezultat.get(
                    "message", "Došlo je do greške. Pokušajte ponovo."
                )

            # Stream the guard-verified response in 80-char chunks
            _CHUNK = 80
            _delovi = [data_text[i:i + _CHUNK] for i in range(0, len(data_text), _CHUNK)]
            for chunk in _delovi:
                # BETA-HARDENING-001 / FS-001 — REGRESIJA NIGHT-005.
                #
                # `_delivered = True` je stajalo POSLE petlje. Generator se posle
                # `yield` SUSPENDUJE i nastavlja tek kad potrošač zatraži sledeću
                # stavku. Klijent koji primi poslednji komad i prestane da čita
                # nikad ne dopusti da se ta linija izvrši -- pa `except BaseException`
                # zatekne `_delivered = False` i REFUNDIRA kredit.
                #
                # Ishod: pun odgovor isporučen, kredit vraćen, neto cena 0.
                # Izmereno: 363/363 znaka primljeno, bajt-identično, saldo 10 → 10.
                # Ponovljivo do granice od 10/min; `refund` nema gornju granicu.
                #
                # NIGHT-005 je opisao TAČNO ovaj kvar i tvrdio da ga zatvara.
                # Njegov test (`test_beta_gate_credit_second_order.py:114`) proverava
                # `assert "_delivered = True" in src` -- PRISUSTVO NISKE, ne mesto
                # izvršavanja. Zato je 70 testova bilo zeleno dok je rupa stajala.
                #
                # SE-001 (protivnički pregled): PRVA verzija ove popravke podizala
                # je zastavicu pred POSLEDNJIM komadom i time samo POMERILA
                # granicu zloupotrebe za 80 znakova. Prekid na pretposlednjem
                # komadu i dalje je vraćao kredit — izmereno: odgovor od 4.000
                # znakova, primljeno 3.920 (98%), `refund = 1`.
                #
                # Gore od toga: `DISCLAIMER` (265 znakova, `main.py:2336`) visi na
                # kraju SVAKOG odgovora, pa je poslednji komad uvek rep pravne
                # napomene. Napadač ga žrtvuje i **ne gubi nijedan znak pravnog
                # sadržaja**. Cena zaobilaženja bila je nula.
                #
                # Kanonska semantika je zato „isporučeno = 0 komada":
                #   0 komada   → korisnik nije dobio ništa → refund (SOA-012)
                #   ≥ 1 komad  → odgovor je počeo da izlazi → bez refunda
                _delivered = True
                yield f"data: {chunk.replace(chr(10), chr(92) + 'n')}\n\n"

            # Prazan odgovor nema nijedan komad, pa gornja grana nikad ne opali.
            # To je ISPRAVNO: prazan ekran nije isporuka, i `_treba_refundirati`
            # ispod vraća kredit (FS-003).
            # SE-005 (protivnički pregled): odgovor od samih belina PROIZVODI
            # komade, pa `not _delovi` ne opali — korisnik dobija prazan ekran i
            # uredan `[DONE]`. Za korisnika je to isto što i prazan odgovor.
            if not _delovi or not data_text.strip():
                logger.error(
                    "[PITANJE_STREAM] prazan odgovor — korisnik ne dobija tekst [q=%s]", qh
                )
                yield "data: Sistem nije vratio odgovor. Pokušajte ponovo.\n\n"

            # UsageService.consume() already pre-deducted the credit above (same timing as
            # the old require_credits pre-deduction) — refund on cache-hit/blocked/genuine
            # LLM failure (LAMBDA008-REL-001, see /api/pitanje's identical fix above).
            preostalo = _stream_preostalo
            if _treba_refundirati(rezultat):
                _refund_dugovan = True
                await UsageService.refund(user["user_id"], user.get("email", ""), "ai_pravna_pitanja")
                _refunded = True
                # SOA-016: the displayed balance used to be hardcoded `+ 1`,
                # which is wrong for any feature priced above 1 credit. Read
                # the real post-refund balance instead of guessing.
                preostalo = await UsageService.balance(user["user_id"], user.get("email", ""))

            yield "data: [DONE]\n\n"
            yield f"data: [CREDITS:{max(preostalo, 0)}]\n\n"

        except Exception as _stream_exc:
            _sentry_capture(_stream_exc)
            logger.exception("Greška u /api/pitanje/stream [q=%s]", qh)
            # BLACKSWAN-HIGH-004 fix (stream variant): the credit above is consumed
            # unconditionally before this generator even starts -- an exception here
            # (including pokreni()'s own 503 queue-timeout, Scenario 3) used to skip the
            # refund entirely, since the refund-check logic only runs on the success path
            # a few lines above. Same fix as the non-streaming /api/pitanje.
            # SE-007 (protivnički pregled): zaštita `not _delivered` postojala je
            # SAMO u `except BaseException` grani ispod. Izuzetak koji nastane
            # POSLE isporuke odgovora (npr. pad pri čitanju salda) prolazio je
            # ovuda i refundirao pun, već isporučen odgovor — izmereno: 437
            # znakova isporučeno, `refund = 1`, uz dva `[DONE]`.
            if not _refunded and (_refund_dugovan or not _delivered):
                try:
                    await UsageService.refund(user["user_id"], user.get("email", ""), "ai_pravna_pitanja")
                    _refunded = True
                except Exception:
                    logger.warning("[PITANJE_STREAM] refund nakon greške nije uspeo [q=%s]", qh)
            elif _delivered:
                logger.info(
                    "[PITANJE_STREAM] greška NAKON isporuke odgovora — bez refunda [q=%s]", qh
                )
            yield "data: Došlo je do greške. Pokušajte ponovo.\n\n"
            yield "data: [DONE]\n\n"

        except BaseException:
            # SOA-012: client disconnect / task cancellation arrives as
            # GeneratorExit or CancelledError, which are BaseException and so
            # slip past the handler above. Refund here, then re-raise so
            # cancellation semantics are preserved exactly (this handler must
            # never swallow). Awaiting during aclose() is permitted -- what is
            # forbidden is yielding, and nothing is yielded below.
            # NIGHT-005 (2026-08-09): `and not _delivered`. On the SUCCESS path
            # _refunded was still False when this handler ran, so a client that
            # read the entire answer and then dropped the connection before
            # [DONE] received the full gpt-4o answer AND got its credit back.
            # Repeatable at the 10/min limit, and refund_n_credits has no cap and
            # no link to a charge, so the balance simply climbs back each time.
            # It also fired unintentionally whenever a flaky mobile connection
            # dropped on the last chunk. Only refund a disconnect that actually
            # cost the user something.
            if not _refunded and not _delivered:
                try:
                    await UsageService.refund(user["user_id"], user.get("email", ""), "ai_pravna_pitanja")
                    _refunded = True
                except Exception:
                    logger.warning("[PITANJE_STREAM] refund nakon prekida veze nije uspeo [q=%s]", qh)
            elif _delivered:
                logger.info("[PITANJE_STREAM] veza prekinuta NAKON isporuke odgovora — bez refunda [q=%s]", qh)
            raise

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Global Search ─────────────────────────────────────────────────────────────
# Project Sentinel (2026-08-03): ovaj fajl je ranije imao SOPSTVENU
# @app.get("/api/search") definiciju ovde — drugu, nezavisno napisanu
# implementaciju istog (path, method) para koji routers/search.py već
# registruje. Starlette matchuje rute po redosledu registracije i staje na
# prvi pogodak; routers/search.py se uključuje (app.include_router) PRE nego
# što se ovaj modul do kraja učita, pa je ova verzija bila 100% mrtav kod —
# nijedan HTTP zahtev je nikad nije mogao dostići, tiho, bez greške, bez
# test failure-a. Ovo je DRUGI potvrđen slučaj iste klase greške u ovom
# engagement-u (prvi: SEC-002, /api/cron/daily dispečer kolizija) — obrisano
# u potpunosti umesto ostavljeno kao "možda nekad korisno". routers/search.py
# je funkcionalno širi (dokumenti/billing/zadaci/hronologija/beleske) osim
# što ne pretražuje predmet_komentari — ta jedna kategorija nikad nije bila
# stvarno dostupna korisniku (ova ruta ju je jedina nudila, i bila je mrtva),
# pa dodavanje komentar-pretrage u routers/search.py je moguće buduće
# poboljšanje, ne bug fix — van obima ove misije (nema novih funkcija).


# ── F5: CASE MANAGEMENT ───────────────────────────────────────────────────────


def _require_auth(authorization: Optional[str]) -> object:
    """
    Extract user from Bearer token. Full 3-step verification: SDK → HS256 → ES256.

    BUG FIX (2026-07-24): svih 11 poziva ove funkcije su ranije bili sinhroni
    unutar async def ruta -- _verify_token unutra može da udari Supabase SDK
    (mrežni poziv) ili živi JWKS fetch (requests.get), oboje blokirajuće.
    Pozivaoci sada koriste await _require_auth_async(authorization).
    HTTPException podignut unutar thread-a se korektno propagira nazad kroz
    await (standardno asyncio ponašanje, isti obrazac kao shared/deps.py).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization[len("Bearer "):]
    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    class _AuthUser:
        id: str = payload.get("sub", "")
        email: str = (
            payload.get("email")
            or payload.get("user_metadata", {}).get("email")
            or ""
        )

    # Mission Atlas (2026-08-03) — same AI Provenance request-context stamp
    # as shared/deps.py::get_current_user, for api.py's own manual-auth style.
    # Program Alpha (2026-08-04) — reuse the middleware's correlation_id, same
    # reasoning as shared/deps.py::get_current_user. KNOWN LIMITATION, found
    # during this same mission, not fixed here (see ARCHITECTURAL_DEBT_REGISTER.md):
    # every caller of this function invokes it via
    # `await _require_auth_async(authorization)` -- a contextvar
    # mutation made *inside* a to_thread-offloaded function does not
    # propagate back to the awaiting coroutine (confirmed empirically), so
    # this call is currently inert from the calling endpoint's own context,
    # unlike shared/deps.py::get_current_user (a genuine async dependency,
    # resolved directly in the request's own coroutine, no thread hop).
    # Left in place (harmless, and correctly reuses the id if the isolation
    # issue is ever fixed by making this function async) rather than removed.
    try:
        from shared.ai_provenance import set_request_context, current_correlation_id
        set_request_context(user_id=payload.get("sub"), correlation_id=current_correlation_id())
    except Exception:
        pass

    return _AuthUser()



async def _require_auth_async(authorization: Optional[str]) -> object:
    """Async wrapper around _require_auth that ACTUALLY stamps the request context.

    S2-3 (2026-08-09). _require_auth stamps user_id/correlation_id itself, but
    every caller invokes it as `await asyncio.to_thread(_require_auth, ...)`, and
    a contextvar mutation made inside a to_thread-offloaded function does not
    propagate back to the awaiting coroutine. The comment inside _require_auth
    documented this and called the stamp "currently inert" -- correctly, and it
    stayed inert across 13 endpoints.

    Consequence: every AI provenance row written on those 13 endpoints carried
    user_id=NULL, so the AI audit trail could not answer "who ran this" for any
    of them.

    The blocking work (Supabase SDK call, JWKS fetch) still happens off-thread;
    only the contextvar write moves into the caller's own coroutine, which is
    where it has to be to survive.
    """
    user = await asyncio.to_thread(_require_auth, authorization)
    try:
        from shared.ai_provenance import set_request_context, current_correlation_id
        set_request_context(user_id=getattr(user, "id", None) or None,
                            correlation_id=current_correlation_id())
    except Exception:
        pass
    return user


@app.post("/api/predmeti")
@limiter.limit("30/minute")
async def kreiraj_predmet(request: Request, authorization: str = Header(None)):
    user = await _require_auth_async(authorization)
    body = await request.json()
    naziv = sanitize_user_input((body.get("naziv") or "").strip()) or ""
    if not naziv:
        raise HTTPException(status_code=400, detail="naziv je obavezan")

    # Program Lambda, Certification 004 (2026-08-06): Chaos Engineer +
    # Database Reliability forks both independently found (Adversarial
    # Certification-confirmed) this endpoint had zero protection against a
    # double-click/duplicate submit -- same finding, same fix shape as
    # routers/intake.py::intake_kreiraj (see that file's own comment for
    # the full reasoning on why a 5s window, and why this is a check-then-
    # insert mitigation, not a full atomic guarantee).
    _cutoff_iso = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    _dup_check = await asyncio.to_thread(
        lambda: _get_supa().table("predmeti")
            .select("id, created_at")
            .eq("user_id", user.id).eq("naziv", naziv)
            .gte("created_at", _cutoff_iso)
            .limit(1).execute()
    )
    if _dup_check.data:
        logger.warning(
            "[API] dupliran zahtev odbijen — uid=%.8s naziv=%r već kreiran (predmet=%s)",
            user.id, naziv, _dup_check.data[0]["id"],
        )
        raise HTTPException(
            status_code=409,
            detail="Predmet sa ovim nazivom je upravo kreiran. Ako ovo nije duplikat, sačekajte par sekundi i pokušajte ponovo.",
        )

    row = _get_supa().table("predmeti").insert({
        "user_id": user.id,
        "naziv":   naziv,
        "opis":    sanitize_user_input(body.get("opis", "")),
        "tip":     body.get("tip", "opsti"),
        "status":  "aktivan",
    }).execute()
    novi_predmet = row.data[0]

    # D3 (VINDEX_2_1_ARCHITECTURE_ROADMAP.md) — emituje PredmetKreiran za standardni
    # "+ Novi predmet" tok. Aktivira postojeći case_pipeline (services/case_pipeline.py)
    # kroz vec registrovan on_predmet_kreiran handler (services/event_bus.py) — nema
    # novog agenta niti nove event arhitekture, samo povezuje vec izgradjen lanac.
    #
    # Project Sentinel (2026-08-03): ranije je ovo bio čist in-process emit()
    # (fire-and-forget asyncio.create_task, bez ikakvog durable outbox reda) —
    # restart/pad procesa između commit-a predmeta iznad i završetka
    # run_case_pipeline je tiho i trajno gubio ceo Case Pipeline (rokovi,
    # mini-strategija, HCC briefing, risk snapshot) bez ijednog traga da je
    # ikad trebalo da se pokrene (Sentinel Phase 2 event_bus_hardening
    # investigation, Finding 1). Sada se, isto kao GENOME_UPDATED
    # (routers/case_dna.py::_emit_genome_event), upisuje ISKLJUČIVO u durable
    # outbox ('events' tabela) — dispatch_pending_events() poller pokreće vec
    # registrovan on_predmet_kreiran handler, i preživljava restart. Bezbedno
    # potvrđeno: run_case_pipeline je idempotentan po koraku (marker-based
    # dedup, npr. _step_ekstrakcija_rokova), pa čak i redak dupli dispatch ne
    # pravi duplirane redove.
    # Mission Ledger (2026-08-03): correlation_id se sada upisuje i kao
    # dedikovana kolona (migracija 090, drafted, not yet applied) — isti id
    # koji shared/ai_provenance.py's set_request_context već postavio za ovaj
    # HTTP zahtev (isti kao onaj koji AI wrapper/log_action koriste), tako da
    # ceo lanac za "+ Novi predmet" deli JEDAN id od HTTP zahteva naovamo.
    try:
        from services.event_bus import EventType
        from shared.ai_provenance import current_correlation_id
        _cid = current_correlation_id()
        _evt_row = {
            "event_type": EventType.PREDMET_KREIRAN.value,
            "user_id":    user.id,
            "predmet_id": novi_predmet["id"],
            "payload":    {"naziv": naziv, "tip": body.get("tip", "opsti"), "correlation_id": _cid},
        }
        # Project Phoenix (2026-08-03), Finding P-1: NARROW fallback
        # (_is_missing_column_error), ne bare except -- v. shared/
        # audit_immutable.py's ista logika za obrazloženje.
        from shared.audit_immutable import _is_missing_column_error
        # BLACKSWAN-HIGH-008 fix (Operation Black Swan, Mission 001, Scenario 5): a
        # connection blip landing on THIS insert (after the predmet row above already
        # committed and HTTP 200 already promised) used to be a single attempt, logged
        # and silently dropped -- since dispatch_pending_events() is the ONLY trigger for
        # the entire Case Pipeline (rokovi/mini-strategija/HCC briefing/risk snapshot),
        # that case then NEVER got a pipeline run, forever, with nothing in the codebase
        # scanning for a predmet with no matching PREDMET_KREIRAN event. A short retry
        # closes the common transient-blip case (a blip lasting a few seconds, this
        # mission's own named Scenario 5 shape) without a larger redesign; a genuinely
        # sustained outage still needs the reconciliation sweep below.
        _evt_insert_ok = False
        _evt_last_exc: Exception | None = None
        for _evt_attempt in range(3):
            try:
                await asyncio.to_thread(
                    lambda: _get_supa().table("events").insert({**_evt_row, "correlation_id": _cid}).execute()
                )
                _evt_insert_ok = True
                break
            except Exception as _wide_exc:
                if not _is_missing_column_error(_wide_exc):
                    _evt_last_exc = _wide_exc
                    if _evt_attempt < 2:
                        await asyncio.sleep(0.5 * (_evt_attempt + 1))
                    continue
                await asyncio.to_thread(lambda: _get_supa().table("events").insert(_evt_row).execute())
                _evt_insert_ok = True
                break
        if not _evt_insert_ok:
            raise _evt_last_exc or RuntimeError("events insert failed, unknown reason")
    except Exception as _pe:
        logger.error(
            "[PIPELINE] PredmetKreiran durable event upis TRAJNO neuspeo posle retry-a — predmet=%s ostaje bez Case Pipeline dok reap_missing_pipeline_events ne popravi: %s",
            novi_predmet["id"], _pe,
        )

    # D22 v1 (VINDEX_OPERATIONAL_GAP_REGISTER.md G-003) — minimalni audit trag:
    # ko je kreirao predmet, kada, preko kog API poziva. 'predmet_create' je vec
    # u AUDITABLE_ACTIONS (shared/audit_immutable.py) od ranije, nikad pozvano —
    # samo povezuje postojecu infrastrukturu, ne gradi novu.
    try:
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            "predmet_create",
            user_id=user.id,
            resource_type="predmet",
            resource_id=novi_predmet["id"],
            ip=request.client.host if request.client else None,
            metadata={"naziv": naziv, "tip": body.get("tip", "opsti"), "source": "api"},
        ))
    except Exception as _ae:
        logger.warning("[AUDIT] predmet_create log greška: %s", _ae)

    return {"predmet": novi_predmet}


@app.get("/api/predmeti")
@limiter.limit("60/minute")
async def lista_predmeta(
    request: Request,
    authorization: str = Header(None),
    limit: int = 200,
    offset: int = 0,
):
    """
    FIX (nightly repair, 2026-07-24), Faza 3 item 8: ranije je ovaj upit
    (a) bio sinhron poziv unutar async def bez asyncio.to_thread -- ista
    klasa bloka event loop-a kao Faza 1 item 2 (routers/multi_agent.py),
    zatečena ovde dok se dodavala paginacija -- i (b) povlačio SVE
    predmete korisnika bez ograničenja. limit/offset su opcioni sa
    velikodušnim podrazumevanim vrednostima (200) koje ne menjaju ponašanje
    za veliku većinu korisnika (mala/solo advokatska praksa) -- štiti samo
    protiv neograničenog rasta kod firmi sa dugom istorijom predmeta.
    select("*") je namerno NEIZMENJEN u ovom prolazu -- suženje kolona bi
    zahtevalo poznavanje TAČNO kojih polja se frontend oslanja, što nije
    potvrđeno u ovoj sesiji; menjanje toga bez te potvrde rizikuje da tiho
    pokvari UI koji čita polje koje bismo izostavili.
    """
    user = await _require_auth_async(authorization)
    limit = min(max(limit, 1), 500)
    offset = max(offset, 0)
    rows = await asyncio.to_thread(
        lambda: _get_supa().table("predmeti")
            .select("*", count="exact")
            .eq("user_id", user.id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
    )
    return {"predmeti": rows.data, "ukupno": rows.count}


@app.get("/api/predmeti/dashboard")
@limiter.limit("30/minute")
async def predmeti_dashboard(request: Request, user: dict = Depends(get_current_user)):
    """
    Prioritizacioni dashboard — svi predmeti sa rizik + rok indikatorima.
    Vraća: po_prioritetu, po_riziku, po_rokovima, statistike.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    preds_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id,naziv,tip,status,created_at")
            .eq("user_id", uid)
            .order("created_at", desc=True)
            .execute()
    )
    predmeti = preds_r.data or []
    if not predmeti:
        return {"predmeti": [], "po_prioritetu": [], "po_riziku": [], "po_rokovima": [], "statistike": {"ukupno": 0}}

    pred_ids = [p["id"] for p in predmeti]

    from datetime import date as _date, datetime as _dt
    today_iso = _date.today().isoformat()

    from shared.attention_priority import canonical_sort_key, CANONICAL_ORDER

    hron_r, dokazi_r, dokumenti_r, rocista_r, actions_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmet_hronologija")
                .select("predmet_id,datum_iso,dogadjaj,vaznost")
                .in_("predmet_id", pred_ids)
                .gte("datum_iso", today_iso)
                .order("datum_iso")
                .execute()
        ),
        # Operation One Truth (2026-08-07): this endpoint used to read a CACHED risk
        # snapshot (`predmet_istorija` rows tagged "[Rizik] {date}"), written once at
        # case creation and only lazily refreshed if/when a lawyer happened to open
        # that specific case's Workspace that day -- nothing in the platform's event
        # system ever re-wrote it on the events that actually change the answer
        # (new evidence, a newly-scheduled hearing). Red Team's own forensic pass
        # constructed a full reproduction of this Dashboard showing a stale "low risk"
        # badge for a case a hearing had since made urgent. Fixed by bulk-fetching the
        # same 3 tables calculate_procesni_rizik needs and computing it LIVE per case
        # below -- the same canonical engine every other risk surface already uses,
        # with no cache to go stale.
        # Operation Singular Intelligence, Mission 002: .is_("deleted_at","null") added -- Team 7's
        # Database Evidence Chains audit found this was 1 of 3 remaining calculate_procesni_rizik
        # callers (of 15+ total) still missing the soft-delete filter every other caller has had
        # since earlier missions' fixes -- a soft-deleted evidence row still inflated/deflated this
        # dashboard's own risk sort relative to Workspace/CCC/Matter Intel for the same case.
        asyncio.to_thread(
            lambda: supa.table("predmet_dokazi")
                .select("predmet_id,snaga,kategorija")
                .in_("predmet_id", pred_ids)
                .is_("deleted_at", "null")
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti")
                .select("predmet_id,tip_dokaza")
                .in_("predmet_id", pred_ids)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("rocista")
                .select("predmet_id,datum")
                .in_("predmet_id", pred_ids)
                .execute()
        ),
        # LAMBDA008-ARCH-002 fix: this endpoint used to compute its own hand-rolled
        # priority formula (_RISK_SCORE weights + urgentni*3 + days-to-next), a 4th
        # independent priority algorithm bypassing the platform's canonical Attention
        # Engine (shared/attention_priority.py, case_actions.prioritet — Core
        # Consolidation §1.2). Now delegates: po_prioritetu sorts by each case's most
        # urgent OPEN case_actions row, translated through canonical_sort_key, exactly
        # like Workspace does.
        asyncio.to_thread(
            lambda: supa.table("case_actions")
                .select("predmet_id,prioritet")
                .in_("predmet_id", pred_ids)
                .eq("status", "open")
                .execute()
        ),
    )

    hron_map: dict = {}
    for h in (hron_r.data or []):
        hron_map.setdefault(h["predmet_id"], []).append(h)

    dokazi_map: dict = {}
    for d in (dokazi_r.data or []):
        dokazi_map.setdefault(d["predmet_id"], []).append(d)
    dokumenti_map: dict = {}
    for d in (dokumenti_r.data or []):
        dokumenti_map.setdefault(d["predmet_id"], []).append(d)
    rocista_map: dict = {}
    for r in (rocista_r.data or []):
        rocista_map.setdefault(r["predmet_id"], []).append(r)

    from services.risk_engine import calculate_procesni_rizik as _calc_rizik_dash
    from shared.constants import EXPECTED_DOCS as _EXPECTED_DOCS_DASH
    risk_map: dict = {}
    for p in predmeti:
        pid = p["id"]
        risk_map[pid] = _calc_rizik_dash(
            dokazi=dokazi_map.get(pid, []), dokumenti=dokumenti_map.get(pid, []),
            rocista=rocista_map.get(pid, []), tip_predmeta=p.get("tip", "ostalo"),
            expected_docs=_EXPECTED_DOCS_DASH,
        )

    # Most urgent OPEN action per case, as a canonical sort key (0=critical .. 4=informational).
    # A case with no open actions sorts after every case that has one.
    _NO_ACTION_KEY = len(CANONICAL_ORDER)
    action_prio_map: dict = {}
    for a in (actions_r.data or []):
        pid = a["predmet_id"]
        key = canonical_sort_key(a.get("prioritet", ""))
        if pid not in action_prio_map or key < action_prio_map[pid]:
            action_prio_map[pid] = key

    _RISK_SCORE = {"visok": 4, "srednji": 2, "nizak": 1}
    enriched = []
    for p in predmeti:
        pid       = p["id"]
        hron      = hron_map.get(pid, [])
        urgentni  = [h for h in hron if h.get("vaznost") == "kritičan"]
        sledeci   = hron[0] if hron else None
        rizik     = risk_map.get(pid, {})
        nivo      = rizik.get("nivo", "")

        days_to_next = 999
        if sledeci and sledeci.get("datum_iso"):
            try:
                days_to_next = (_dt.strptime(sledeci["datum_iso"], "%Y-%m-%d").date() - _date.today()).days
            except Exception:
                pass

        enriched.append({
            **p,
            "urgentni_rokovi_count": len(urgentni),
            "sledeci_rok":           sledeci,
            "rizik_nivo":            nivo,
            "action_priority_key":   action_prio_map.get(pid, _NO_ACTION_KEY),
            "_days_to_next":         days_to_next,
        })

    # Primary: canonical action priority (lower = more urgent). Ties broken by the
    # existing deadline-proximity signal, which is not itself a competing priority
    # source — just a tiebreaker among cases at the same canonical urgency.
    po_prioritetu = sorted(
        enriched,
        key=lambda x: (x["action_priority_key"], -max(0, 30 - x["_days_to_next"])),
    )
    for e in enriched:
        e.pop("_days_to_next", None)
    po_riziku     = sorted(
        [e for e in enriched if e["rizik_nivo"] in ("visok","srednji","nizak")],
        key=lambda x: _RISK_SCORE.get(x["rizik_nivo"], 0),
        reverse=True,
    )
    po_rokovima   = sorted(
        [e for e in enriched if e["sledeci_rok"]],
        key=lambda x: x["sledeci_rok"].get("datum_iso","9999"),
    )

    return {
        "predmeti":        enriched,
        "po_prioritetu":   po_prioritetu[:15],
        "po_riziku":       po_riziku[:15],
        "po_rokovima":     po_rokovima[:15],
        "statistike": {
            "ukupno":              len(predmeti),
            "visok_rizik":         sum(1 for e in enriched if e["rizik_nivo"] == "visok"),
            "hitni_rokovi":        sum(e["urgentni_rokovi_count"] for e in enriched),
            "bez_rizik_procene":   sum(1 for e in enriched if not e["rizik_nivo"]),
        },
    }


@app.get("/api/predmeti/{predmet_id}")
@limiter.limit("60/minute")
async def get_predmet(predmet_id: str, request: Request, authorization: str = Header(None)):
    user = await _require_auth_async(authorization)
    supa = _get_supa()
    row = supa.table("predmeti").select("*").eq("id", predmet_id).eq("user_id", user.id).maybe_single().execute()
    if not row.data:
        # FIX (nightly repair, 2026-07-24): predmet_delegiranja (routers/
        # enterprise.py::delegiraj_predmet) je ranije upisivao zapis o
        # delegiranju koji NIŠTA drugo u kodu nikad nije čitalo za pristup
        # -- kolega kome je predmet "delegiran" i dalje nije mogao ni da
        # ga VIDI. Ovo dodaje stvarnu proveru pristupa za READ putanju
        # (uvid) preko aktivne delegacije -- write akcije (izmena, beleške
        # itd.) i dalje ostaju gejtovane isključivo na originalnog vlasnika,
        # namerno, dok se ne donese šira odluka o granicama delegiranog
        # pristupa.
        deleg = supa.table("predmet_delegiranja") \
            .select("id") \
            .eq("predmet_id", predmet_id) \
            .eq("na_user_id", user.id) \
            .eq("status", "aktivno") \
            .maybe_single().execute()
        if deleg.data:
            row = supa.table("predmeti").select("*").eq("id", predmet_id).maybe_single().execute()

    if not row.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")

    beleske, istorija, dokumenti, hronologija, komentari, predmet_klijenti = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_beleske").select("*").eq("predmet_id", predmet_id).order("created_at", desc=True).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija").select("*").eq("predmet_id", predmet_id).order("created_at", desc=True).limit(20).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select("*").eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija").select("*").eq("predmet_id", predmet_id).order("datum_iso", desc=False).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_komentari").select("*").eq("predmet_id", predmet_id).order("kreirano", desc=True).limit(50).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_klijenti").select("klijent_id, uloga_klijenta, napomena, kreirano").eq("predmet_id", predmet_id).execute()),
    )

    # Fetch basic client info for linked klijenti
    # Lambda Certification 002 (2026-08-06) -- ranije nije postojala
    # user_id provera ovde (API Penetration sweep, potvrdjeno: konfirmovan
    # cross-tenant PII leak ako se tudj klijent_id ubaci u predmet_klijenti,
    # vidi predmet_confirm_links). Skopirano na row.data["user_id"] (stvarni
    # vlasnik predmeta), NE na user.id posmatraca, jer delegirani pristup
    # iznad namerno dozvoljava kolegi da vidi predmet vlasnika -- klijenti
    # moraju ostati skopirani na PRAVOG vlasnika u oba slucaja.
    klijenti_linked = []
    if predmet_klijenti.data:
        klijent_ids = [r["klijent_id"] for r in predmet_klijenti.data]
        predmet_owner_uid = row.data.get("user_id")
        try:
            kl_rows = await asyncio.to_thread(
                lambda: supa.table("klijenti")
                    .select("id, ime, prezime, firma, tip, status")
                    .eq("user_id", predmet_owner_uid)
                    .in_("id", klijent_ids)
                    .is_("deleted_at", "null")
                    .execute()
            )
            kl_map = {r["id"]: r for r in (kl_rows.data or [])}
            for pk in predmet_klijenti.data:
                kl = kl_map.get(pk["klijent_id"])
                if kl:
                    klijenti_linked.append({
                        **kl,
                        "uloga": pk.get("uloga_klijenta", "stranka"),
                        "napomena": pk.get("napomena", ""),
                    })
        except Exception as e:
            logger.warning("[PREDMETI] klijenti linked greška: %s", e)

    return {
        "predmet":         row.data,
        "beleske":         beleske.data,
        "istorija":        istorija.data,
        "dokumenti":       dokumenti.data,
        "hronologija":     hronologija.data,
        "komentari":       komentari.data,
        "klijenti_linked": klijenti_linked,
    }


@app.patch("/api/predmeti/{predmet_id}")
@limiter.limit("30/minute")
async def update_predmet(predmet_id: str, request: Request, authorization: str = Header(None)):
    user = await _require_auth_async(authorization)
    body = await request.json()
    allowed = {k: v for k, v in body.items() if k in {
        "naziv", "opis", "tip", "status",
        "tuzilac", "tuzeni", "oblast", "rizik", "vrednost_spora",
    }}
    if not allowed:
        raise HTTPException(status_code=400, detail="Nema validnih polja za update")
    # XSS sweep (2026-07-24): naziv/opis/tuzilac/tuzeni/oblast su slobodan
    # tekst -- stripuj HTML markup pre upisa (tip/status/rizik/vrednost_spora
    # su kontrolisane/numeričke vrednosti, ne diramo ih).
    for _fld in ("naziv", "opis", "tuzilac", "tuzeni", "oblast"):
        if _fld in allowed:
            allowed[_fld] = sanitize_user_input(allowed[_fld])

    # Program Lambda, Certification 004 (2026-08-06): Chaos Engineer fork
    # found (Adversarial Certification-confirmed) this was a blind
    # last-write-wins update with no version/updated_at precondition -- a
    # stale write from one browser tab (editing a case already changed by
    # another tab, or by a background process) silently clobbers newer
    # data with no conflict ever surfaced to either side. `predmeti` has a
    # real, trigger-refreshed `updated_at` column (supabase_setup.sql's own
    # `update_predmeti_updated_at` trigger -- genuinely bumped on every
    # UPDATE, not just a DEFAULT that only applies on INSERT), so an
    # optional client-supplied `if_updated_at` can be used as an
    # optimistic-concurrency token with no new migration needed. Opt-in and
    # backward-compatible: a caller not yet sending it gets the exact prior
    # behavior (unconditional update), so no existing frontend breaks.
    if_updated_at = body.get("if_updated_at")
    supa = _get_supa()
    q = supa.table("predmeti").update(allowed).eq("id", predmet_id).eq("user_id", user.id)
    if if_updated_at:
        q = q.eq("updated_at", if_updated_at)
    result = q.execute()
    # F-V41-001 (2026-08-10): guard je bio uslovljen OPCIONIM `if_updated_at`
    # tokenom, pa je pozivalac koji ga ne šalje -- a to je svaki stariji klijent
    # -- dobijao {"ok": True} i za predmet koji ne postoji ili nije njegov.
    # Success odgovor bez ijednog izmenjenog reda. Ugovor za "nije pronađen"
    # već je definisan ispod, samo je bio nedostižan bez tokena; uslov se sada
    # veže za stvarni ishod mutacije, ne za prisustvo opcionog polja.
    if not result.data:
        # Phase 6 adversarial re-attack (same sprint) found this originally
        # conflated 2 distinct causes of "0 rows updated": a genuine stale
        # write (if_updated_at precondition didn't match) vs. predmet_id
        # simply not existing/not owned by this caller -- the latter got
        # the misleading "someone else changed it" message instead of
        # "not found". A cheap follow-up existence check (ignoring
        # if_updated_at) distinguishes them; ownership scoping is
        # unaffected either way, this only changes which error message
        # a caller sees.
        exists = await asyncio.to_thread(
            lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", user.id).maybe_single().execute()
        )
        if not exists.data:
            raise HTTPException(status_code=404, detail="Predmet nije pronađen")
        raise HTTPException(
            status_code=409,
            detail="Predmet je izmenjen u međuvremenu. Osvežite stranicu i pokušajte ponovo.",
        )
    # Program Phoenix, Mission 002: the new updated_at is returned so a caller now sending
    # if_updated_at (see LIVINGSYS-DEBT-007 fix, static/vindex.js::_predInlineEdit) can update
    # its own cached value for the NEXT edit -- without this, a 2nd field edited moments after
    # the 1st would spuriously 409 against an already-stale cached precondition.
    _new_updated_at = (result.data[0].get("updated_at") if result.data else None)

    # V41-B: kanonski audit tek POSLE `if not result.data` guarda -- pre njega
    # uspeh mutacije nije bio dokaziv (F-V41-001), zato su guard i audit
    # razdvojeni sprintovi. Middleware u shared/audit.py već upisuje ovaj PATCH
    # u `audit_log`, ali kao string "PATCH:<uuid>" bez resource_type i bez hash
    # lanca; kanonski zapis se DODAJE uz njega, ne zamenjuje ga (isti OPTION A
    # obrazac kao saradnik_uklonjen).
    #
    # metadata nosi SAMO IMENA izmenjenih polja, nikad vrednosti: `audit_immutable`
    # je append-only sa BEFORE UPDATE OR DELETE trigerom, pa bi upis sadržaja
    # predmeta (naziv/opis/tuzilac/tuzeni) trajno duplirao lične podatke u
    # ledger iz kog se ne mogu obrisati.
    from shared.audit_immutable import log_action
    await log_action("predmet_update", user_id=user.id,
                     resource_type="predmet", resource_id=predmet_id,
                     ip=request.client.host if request.client else None,
                     metadata={"polja": sorted(allowed.keys())})

    return {"ok": True, "updated_at": _new_updated_at}


@app.patch("/api/predmeti/{predmet_id}/kanban-faza")
@limiter.limit("30/minute")
async def update_kanban_faza(predmet_id: str, request: Request, authorization: str = Header(None)):
    """Kanban Case Pipeline — premesti predmet u drugu fazu."""
    user = await _require_auth_async(authorization)
    body = await request.json()
    faza = (body.get("kanban_faza") or "").strip()
    _VALID = {"inicijalna_procena", "priprema", "aktivan_postupak", "ceka_odluku", "zavrsen"}
    if faza not in _VALID:
        raise HTTPException(status_code=400, detail="Nevalidna faza")
    supa = _get_supa()
    # BLACKSWAN-HIGH-002 fix (Operation Black Swan, Mission 001, Scenario 7): was a bare
    # unconditional update -- two concurrent drags of the same card (2 tabs, or 2
    # lawyers) both returned "ok: True" while only one write actually survived, a
    # classic lost update with zero conflict signal to either caller. Reproduced: caller
    # A's own response claimed success for its target phase while the DB silently held
    # caller B's phase instead. `if_faza` is optional (old frontend callers keep working
    # unconditionally, same opt-in shape as update_predmet's own if_updated_at) but the
    # frontend below IS updated to send it, so this closes the gap for real, not just in
    # infrastructure nobody calls (the pre-existing if_updated_at protection on
    # update_predmet has zero live frontend callers per this mission's own finding).
    if_faza = (body.get("if_faza") or "").strip()
    q = supa.table("predmeti").update({"kanban_faza": faza}).eq("id", predmet_id).eq("user_id", user.id)
    if if_faza:
        q = q.eq("kanban_faza", if_faza)
    result = q.execute()
    if not (result.data):
        if if_faza:
            exists = await asyncio.to_thread(
                lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", user.id).maybe_single().execute()
            )
            if not exists.data:
                raise HTTPException(status_code=404, detail="Predmet nije pronađen")
            raise HTTPException(
                status_code=409,
                detail="Faza je izmenjena u međuvremenu. Osvežite stranicu i pokušajte ponovo.",
            )
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")
    return {"ok": True, "kanban_faza": faza}


@app.post("/api/predmeti/{predmet_id}/beleske")
@limiter.limit("30/minute")
async def dodaj_belesku(predmet_id: str, request: Request, authorization: str = Header(None)):
    user = await _require_auth_async(authorization)
    # SEC-001 fix (2026-07-23): predmet_id came from the URL and was never
    # verified to belong to the caller before this insert — any authenticated
    # user could write a note into another user's case file. Same ownership
    # check already used by the sibling GET for this exact resource
    # (get_predmet, api.py:3161) and by update_predmet (api.py:3220).
    pred = _get_supa().table("predmeti").select("id").eq("id", predmet_id).eq("user_id", user.id).single().execute()
    if not pred.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")
    body = await request.json()
    sadrzaj = sanitize_user_input((body.get("sadrzaj") or "").strip()) or ""
    if not sadrzaj:
        raise HTTPException(status_code=400, detail="sadrzaj je obavezan")
    row = _get_supa().table("predmet_beleske").insert({
        "predmet_id": predmet_id,
        "user_id":    user.id,
        "sadrzaj":    sadrzaj,
    }).execute()
    return {"beleska": row.data[0]}


@app.delete("/api/predmeti/{predmet_id}/beleske/{beleska_id}")
@limiter.limit("30/minute")
async def obrisi_belesku(predmet_id: str, beleska_id: str, request: Request, authorization: str = Header(None)):
    user = await _require_auth_async(authorization)
    _get_supa().table("predmet_beleske").delete().eq("id", beleska_id).eq("user_id", user.id).execute()
    return {"ok": True}


@app.post("/api/predmeti/{predmet_id}/istorija")
@limiter.limit("30/minute")
async def sacuvaj_istoriju(predmet_id: str, request: Request, authorization: str = Header(None)):
    user = await _require_auth_async(authorization)
    # SEC-001 fix (2026-07-23): same gap as dodaj_belesku above — predmet_id
    # from the URL was never verified against the caller before this insert.
    pred = _get_supa().table("predmeti").select("id").eq("id", predmet_id).eq("user_id", user.id).single().execute()
    if not pred.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")
    body = await request.json()
    _get_supa().table("predmet_istorija").insert({
        "predmet_id": predmet_id,
        "user_id":    user.id,
        "pitanje":    body.get("pitanje", ""),
        "odgovor":    body.get("odgovor", ""),
        "confidence": body.get("confidence", ""),
    }).execute()
    return {"ok": True}


# ── Phase 2.1: Document type detection ───────────────────────────────────────

_PRESUDA_MARKERS = [
    "u ime naroda", "izreka", "obrazloženje", "obrazlozenje",
    "prvostepenom presudom", "prvostepene presude",
    "apelacioni sud", "vrhovni kasacioni", "viši sud", "osnovni sud",
    "tužbeni zahtev", "tuzbeni zahtev",
    "žalba je", "žalba tužioca", "žalba tuženog",
    "obavezuje se tuženi", "odbija se tužbeni", "odbija se žalba",
    "revizija tužioca", "revizija tuženog",
    "gž ", "rev ", "pž ", "kž ",
]

_UGOVOR_MARKERS = [
    "ugovor o ", "zaključen između", "zakljucen izmedju",
    "strane ugovornice", "ugovorne strane",
    "ugovarač", "ugovarac",
    "kupoprodajni ugovor", "ugovor o zakupu",
    "ugovor o radu", "ugovor o delu",
    "potpisnici ovog ugovora",
]


def _detect_doc_type(text: str) -> str:
    """Keyword heuristic on first 3000 chars. Returns 'presuda' | 'ugovor' | 'opsti'."""
    sample = text[:3000].lower()
    p = sum(1 for m in _PRESUDA_MARKERS if m in sample)
    u = sum(1 for m in _UGOVOR_MARKERS if m in sample)
    if p >= 2 or (p >= 1 and u == 0):
        return "presuda"
    if u >= 2 or (u >= 1 and p == 0):
        return "ugovor"
    return "opsti"


_PRESUDA_SYSTEM_PROMPT = """Ti si stručni pravni analitičar specijalizovan za srpsko pravo i analizu sudskih presuda.

Analiziraš presudu i generišeš strukturisani izveštaj koji advokat može direktno koristiti pri pisanju žalbe.

OBAVEZNI FORMAT — tačno ovih 5 sekcija:

1. REZIME PRESUDE
Sažetak šta je sud odlučio, koje zahteve usvojio a koje odbio, i na osnovu čega. Tačno 5-7 rečenica.

2. KLJUČNI ARGUMENTI SUDA
Najvažniji razlozi koje je sud naveo za svoju odluku. Numerisana lista, max 4 stavke.

3. PRIMENJENI PROPISI
Tačna lista zakona i članova koje je sud citirao ili primenio. Format: "Čl. X naziv_zakona". Max 10 stavki.

4. POTENCIJALNI ŽALBENI OSNOVI
Konkretni pravni osnovi za žalbu (pogrešna primena materijalnog prava, bitna povreda odredaba ZPP, pogrešno utvrđeno činjenično stanje). Za svaki osnov kratko objašnjenje. Numerisana lista, max 4 stavke.

5. PROCENA IZGLEDA ŽALBE
Na prvom redu napiši TAČNO JEDNO od: NIZAK / SREDNJI / VISOK
Zatim obrazloženje u 2-3 rečenice zašto si dao tu ocenu.

PRAVILA:
- Nikada ne garantuj ishod žalbe.
- Budi objektivan — navedi i jake strane presude.
- Koristi srpsku ekavicu i pravni registar.
- Svaka sekcija max 6 redova.
- Na kraju dodaj: "Ova analiza je generisana uz pomoć AI i mora biti proverena od strane ovlašćenog advokata."
"""


# ── Shared citation guard — appended to both procena + presuda prompts ────────
_CITATION_GUARD = (
    "\n\n🔒 PRAVILO ZA PRAVNI OSNOV — OBAVEZNO:\n"
    "- Brojeve članova (npr. 'Čl. 184. ZR') citiraj ISKLJUČIVO iz bloka 'DOSTUPNI ZAKONI' "
    "koji se nalazi na početku upita korisnika.\n"
    "- Ako relevantan član NIJE u bloku, napiši naziv pravnog instituta "
    "(npr. 'obaveza obrazloženja otkaza od strane poslodavca') BEZ broja člana.\n"
    "- NIKADA ne izmišljaj broj člana iz opšteg znanja.\n"
    "- Za presudu u sekciji 'PRIMENJENI PROPISI': navodi SAMO članove koje sud "
    "eksplicitno citira u tekstu presude ili koji se nalaze u bloku 'DOSTUPNI ZAKONI'.\n"
)

_PRESUDA_SYSTEM_PROMPT = _PRESUDA_SYSTEM_PROMPT + _CITATION_GUARD


# ── F5.3: PRAVNA PROCENA ──────────────────────────────────────────────────────

_PROCENA_SYSTEM_PROMPT = """Ti si stručni pravni analitičar za srpsko pravo.
Na osnovu opisanih činjenica pruži strukturiranu pravnu procenu.

OBAVEZNI FORMAT — tačno ovih 17 sekcija:

1. PRAVNI OSNOV
Navedi SVE primenjive zakonske odredbe na opisanu situaciju — bez obzira na to koju stranu štite.
Citiraj ISKLJUČIVO iz bloka DOSTUPNI ZAKONI koji se nalazi na početku korisničkog upita.
Primer za otkaz ugovora o radu: čl. 175, 176, 184, 191 ZR — svi zajedno u jednoj sekciji.
NE raspoređuj članove po sekcijama "za tužioca" ili "za tuženog" — svi idu ovde.

2. ARGUMENTI ZA TUŽIOCA
Najjači FAKTIČKI i pravni argumenti u korist tužioca/oštećenog (max 3 boda).
Fokus na činjenice i procesne prednosti — ne ponavljaj članove iz sekcije 1.

3. SLABOSTI U POZICIJI TUŽIOCA
Slabe tačke u poziciji tužioca koje tuženi može iskoristiti (max 3 boda).
Fokus na procesne rupe, nedostajuće dokaze i teško dokazive tvrdnje.

4. POTENCIJALNI ARGUMENTI TUŽENOG
Najjači FAKTIČKI kontraargumenti u korist tuženog/poslodavca (max 3 boda).
Fokus na činjenične nedostatke i procesne rizike — ne navoditi zakonske članove ovde.

5. STRATEGIJA ZA TUŽIOCA
Obavezno tačno ovim redom, svaka stavka na posebnoj liniji:
Najjači napad: [1 rečenica — centralna procesna strategija tužioca]
Zašto: [obrazloženje u 1 rečenici]
Dokaz koji odlučuje spor: [konkretan dokaz ili činjenica]
Snaga argumenta: VISOKA / SREDNJA / NISKA

6. STRATEGIJA ZA TUŽENOG
Obavezno tačno ovim redom, svaka stavka na posebnoj liniji:
Najjača odbrana: [1 rečenica — centralna procesna strategija tuženog]
Zašto: [obrazloženje u 1 rečenici]
Dokaz koji odlučuje spor: [konkretan dokaz ili činjenica]
Snaga argumenta: VISOKA / SREDNJA / NISKA
Napomena za radne sporove: tuženi bi mogao pokušati da istakne postojanje opravdanih razloga, ali sud će ceniti i zakonitost sprovedene procedure.

7. PREDVIĐENI ARGUMENTI TUŽENOG
Najopasnije tvrdnje tuženog koje tužilac mora da predvidi — obavezno u ovom formatu (max 3 argumenta):
- Argument 1: [konkretna tvrdnja tuženog]
  Procena opasnosti: VISOKA / SREDNJA / NISKA — [obrazloženje zašto]
- Argument 2: [konkretna tvrdnja]
  Procena opasnosti: VISOKA / SREDNJA / NISKA — [obrazloženje]
- Argument 3: [konkretna tvrdnja]
  Procena opasnosti: VISOKA / SREDNJA / NISKA — [obrazloženje]

8. FAKTORI KOJI UTIČU NA ISHOD
Navedi minimum 4 faktora koji utiču na ishod spora, sortirano od najvećeg ka najmanjem uticaju.
Obavezno tačno u ovom formatu (svaki faktor na posebnoj liniji):
Faktor: [naziv faktora] | Uticaj: VEOMA VISOK / VISOK / SREDNJI / NIZAK | Status: Potvrđeno / Nepotvrđeno / Nepoznato | Izvor: Izjava korisnika / Dostavljen dokument / Dokument nije dostavljen / Pretpostavka
(ponovi za svaki faktor, min 4)

9. SPORNE TAČKE
Ključne činjenične ili pravne tačke oko kojih se stranke mogu sporiti (max 3 boda).

10. NEDOSTAJUĆE ČINJENICE
Pitanja čiji odgovor nije poznat a direktno utiče na analizu — navedi minimum 3:
- [pitanje 1 — konkretna nepoznata činjenica]
- [pitanje 2 — konkretna nepoznata činjenica]
- [pitanje 3 — konkretna nepoznata činjenica]

11. CRVENE ZASTAVICE
🚨 Automatski identifikovani kritični problemi — samo stvarni, konkretni rizici (min 2, max 5):
- 🚨 [kritični problem 1 — konkretan, vezan za ovaj predmet]
- 🚨 [kritični problem 2 — konkretan, vezan za ovaj predmet]
Ne piši generičke zastavice — svaka mora biti specifična za opisane činjenice.

12. POTREBNI DOKAZI
Grupiši dokaze u tačno 3 nivoa — svaki nivo na posebnoj liniji:
🔴 Kritični: (dokazi bez kojih predmet pada — nabrojati)
🟡 Važni: (dokazi koji jačaju poziciju — nabrojati)
🟢 Korisni: (podržavajući dokazi — nabrojati)

13. KOMPLETIRANOST PREDMETA
OBAVEZNO: prva linija mora biti tačno u ovom formatu (bez izmena):
KOMPLETIRANOST: XX%
Zatim OBAVEZNO na sledećoj liniji:
Nedostaje: [konkretan spisak dokumenata koji fale]
Primer ispravnog outputa:
KOMPLETIRANOST: 35%
Nedostaje: rešenje o otkazu, pisano upozorenje zaposlenom, ugovor o radu

14. PROCENA RIZIKA
OBAVEZNO: popuni SVE podsekcije — ne ostavljaj prazne linije.
Faktori koji POVEĆAVAJU rizik:
- [faktor 1]
- [faktor 2]
Faktori koji SMANJUJU rizik:
- [faktor 1]
- [faktor 2]
Rizik za tužioca: NIZAK / SREDNJI / VISOK — [obrazloženje u 1 rečenici]
Rizik za tuženog: NIZAK / SREDNJI / VISOK — [obrazloženje u 1 rečenici]
OBAVEZNO: reči NIZAK, SREDNJI ili VISOK moraju biti prisutne u obe linije.

15. RELEVANTNA PRAKSA
Samo ako su odlomci sudske prakse dostavljeni pod "RELEVANTNA SUDSKA PRAKSA".
Za svaku presudu obavezno ovim redom:
• [Sud, broj odluke, godina]
  Pravni stav: "[citat ključnog stava u navodnicima — 1-2 rečenice]"
  Sličnost sa predmetom: XX%
  Zašto je relevantna: [1 rečenica]
  Poklapanja: [lista ključnih poklapanja sa predmetom]
  Razlike: [lista ključnih razlika u odnosu na predmet]
  Ako sud usvoji isti pravni stav → [konkretna posledica za tužioca ili tuženog u ovom predmetu]
  Podržava: Tužioca / Tuženog / Neutralno
Navedi max 3 presude.

17. PITANJA ZA KLIJENTA
Konkretna pitanja koja advokat treba da postavi klijentu — navedi minimum 4:
→ [pitanje 1 — konkretno, vezano za ovaj predmet]
→ [pitanje 2]
→ [pitanje 3]
→ [pitanje 4]

18. POUZDANOST PROCENE
OBAVEZNO: prva linija mora biti tačno u ovom formatu:
POUZDANOST: XX%
OBAVEZNO: vrednost XX nikad ne sme biti veća od 95.
Razlozi:
- [razlog koji smanjuje pouzdanost] (npr. -25%)
- [razlog koji smanjuje pouzdanost] (npr. -10%)
- [razlog koji povećava pouzdanost] (npr. +10%)
- [razlog koji povećava pouzdanost] (npr. +15%)
Zatim:
Nedostaju: [lista dokumenata]
Upload ovih dokumenata može značajno promeniti zaključak.

PRAVILA:
- Nikada ne garantuj ishod postupka.
- Koristi srpsku ekavicu i pravni registar.
- Budi koncizan ali konkretan — bez generičkih fraza.
- POUZDANOST i sve procenjene vrednosti: maksimum je 95% — nikad više.
- ZABRANJENE FORMULACIJE (ne koristi ih nikad):
  × "Sud će smatrati..."
  × "Sud može smatrati..."
  × "Tužilac gubi argument..."
  × "Ovo neutrališe..."
  × "može neutralisati proceduralne propuste"
  × "Tužilac gubi osnovni argument"
- DOZVOLJENE ZAMENE:
  ✓ "Jača poziciju..."
  ✓ "Slabi poziciju..."
  ✓ "Može biti relevantno..."
  ✓ "Zahteva dodatnu proveru..."
  ✓ "može značajno ojačati poziciju tuženog, ali će sud ceniti i zakonitost sprovedene procedure"
  ✓ "Tužilac ostaje bez jednog od ključnih argumenata, ali spor i dalje zavisi od drugih činjenica i dokaza"
- Na kraju sekcije 18 dodaj: "Ova procena je generisana uz pomoć AI i mora biti proverena od strane ovlašćenog advokata."
"""

_PROCENA_SYSTEM_PROMPT = _PROCENA_SYSTEM_PROMPT + _CITATION_GUARD

# ── Phase 3.4: V2 addendum — sekcije 19-21 (appended to existing 18-section prompt) ──
_PROCENA_V2_ADDENDUM = """

DODATNE OBAVEZNE SEKCIJE (dodaj na kraju, iza sekcije 18):

19. ŽALBENI OSNOVI
Samo ako postoje uslovi za žalbu, prigovor ili pravno sredstvo u ovom predmetu.
Navedi konkretne zakonske osnove za žalbu (max 3), u obliku:
- Osnov 1: [naziv pravnog osnova] — [zakonska odredba ako je primenljiva]
  Jačina: JAKA / SREDNJA / SLABA — [obrazloženje u 1 rečenici]
- Osnov 2: ...
Ako žalbeni postupak još nije aktuelan, napiši: "Žalbeni postupak još nije aktivan — predmet je u pripremnoj fazi."

20. SLEDEĆI KORACI
Konkretnih 3-5 koraka koje stranka mora preduzeti — sortiranih po hitnosti:
1. [korak 1 — konkretan, sa rokom ako postoji]
2. [korak 2]
3. [korak 3]
4. [opcionalni korak 4]
5. [opcionalni korak 5]
Svaki korak mora biti specifičan za ovaj predmet, ne generički.

21. PROCENA USPEHA
OBAVEZNO: prva linija mora biti tačno u ovom formatu (bez izmena):
PROCENA USPEHA: XX%
gde XX je procenjena verovatnoća uspeha tužioca u rasponu 5-90.
OBAVEZNO vrednost mora biti između 5 i 90 — nikad 0 ili 100.
Zatim:
Obrazloženje: [2-3 rečenice koje objašnjavaju procenu]
Faktori koji povećavaju šanse:
- [faktor 1]
- [faktor 2]
Faktori koji smanjuju šanse:
- [faktor 1]
- [faktor 2]
"""


def _fetch_relevantne_presude_sync(tekst: str, top_k: int = 5) -> list:
    """Phase 3.4 — Fetch top relevant court decisions from Pinecone for Section 22.
    Queries sudska_praksa and upravna_praksa, deduplicates by decision_number."""
    from app.services.retrieve import _get_index, _ugradi_query, _pretraga_ns
    try:
        vec = _ugradi_query(tekst[:500])
    except Exception as _e:
        logger.warning("[P3.4] Embedding greška: %s", _e)
        return []
    index = _get_index()
    seen_dn: set = set()
    results: list = []
    for ns in ("sudska_praksa", "upravna_praksa"):
        try:
            matches = _pretraga_ns(vec, ns, k=top_k)
            for m in matches:
                md = m.metadata or {}
                dn = md.get("decision_number") or md.get("decision_id_fallback") or ""
                if not dn or dn in seen_dn:
                    continue
                seen_dn.add(dn)
                results.append({
                    "broj":   dn,
                    "datum":  md.get("decision_date", ""),
                    "sud":    md.get("court", ""),
                    "oblast": md.get("matter", ""),
                    "pravni_stav_preview": (md.get("text") or "")[:250],
                    "score":  round(float(m.score), 3),
                })
        except Exception as _ne:
            logger.debug("[P3.4] ns=%s fetch greška: %s", ns, _ne)
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def _format_sekcija22(presude: list) -> str:
    """Phase 3.4 — Format Pinecone results as Section 22 text."""
    if not presude:
        return ""
    parts = []
    for p in presude:
        broj   = p.get("broj") or "?"
        sud    = p.get("sud") or ""
        datum  = p.get("datum") or ""
        oblast = p.get("oblast") or ""
        score  = p.get("score", 0)
        tekst  = (p.get("pravni_stav_preview") or "").strip()
        sim_pct = min(99, int(float(score) * 100))
        header = f"• [{broj}]"
        if sud:
            header += f" ({sud})"
        if datum:
            header += f" — {datum}"
        lines = [header]
        if oblast:
            lines.append(f"  Oblast: {oblast}")
        lines.append(f"  Sličnost sa predmetom: {sim_pct}%")
        if tekst:
            preview = tekst[:220] + ("..." if len(tekst) > 220 else "")
            lines.append(f'  Pravni stav: "{preview}"')
        parts.append("\n".join(lines))
    return "\n\n22. RELEVANTNA SUDSKA PRAKSA\n" + "\n\n".join(parts) + "\n"


# ── Phase 2.2: Hronologija dokaza — extracts all dated events from a document ──
_HRONOLOGIJA_SYSTEM_PROMPT = """Ti si pravni asistent koji analizira pravne dokumente i izvlači sve datume i događaje.

ZADATAK: Iz teksta dokumenta izvuci SVE datume i događaje koji su pravno relevantni.

Vrati ISKLJUČIVO JSON array bez ikakvog teksta pre ili posle. Format svakog unosa:
{
  "datum": "DD.MM.YYYY",
  "datum_iso": "YYYY-MM-DD",
  "dogadjaj": "Kratak opis šta se desilo (max 150 znakova)",
  "akter": "Ko je preduzeo radnju (osoba, firma, sud...)",
  "vaznost": "kritičan"
}

PRAVILA:
- vaznost mora biti tačno jedna od: "kritičan", "važan", "informativan"
  * "kritičan" = ključni pravni datumi (otkaz, tužba, presuda, rok, ugovor potpisan/raskinut)
  * "važan" = važni ali ne odlučujući (upozorenje, obaveštenje, zahtev, odgovor)
  * "informativan" = kontekst i pozadina (zaposlenje, transfer, pismo, napomena)
- datum: DD.MM.YYYY format. Ako je mesec/godina bez dana — koristi "01" za dan.
- datum_iso: ISO 8601 format YYYY-MM-DD. Ako datum nije poznat, stavi null.
- akter: ime ili opis aktera (npr. "Poslodavac", "Zaposleni Marko Marković", "Osnovni sud Beograd")
- dogadjaj: konkretan opis, ne prazna fraza. Max 150 znakova.
- Ako relativni datum ("prošle godine", "pre 6 meseci") — proceni apsolutni datum na osnovu konteksta dokumenta i napiši u napomeni.
- Ako nema ni jednog datuma, vrati prazan array: []
- Vrati SAMO JSON array, apsolutno ništa pre ili posle."""


@app.post("/api/procena")
@limiter.limit("5/minute")
async def pravna_procena(request: Request, authorization: str = Header(None)):
    """F5.3 — Structured legal case assessment via GPT-4o."""
    from openai import OpenAI as _OAI
    user = await _require_auth_async(authorization)
    # _require_auth returns a plain object (not a dict) — PermissionService.require()
    # expects a dict it can read/mutate, so build one and invoke the dependency callable
    # manually (Depends() default is only resolved by FastAPI's DI, calling it directly
    # with an explicit `user=` kwarg just runs the function body against that dict).
    _entitlement_user = {"user_id": user.id, "email": user.email}
    await PermissionService.require("procena")(user=_entitlement_user)
    body = await request.json()
    cinjenice = (body.get("cinjenice") or "").strip()
    if not cinjenice:
        raise HTTPException(status_code=400, detail="cinjenice su obavezne")

    predmet_id = (body.get("predmet_id") or "").strip() or None

    # Fetch existing notes for additional context if predmet_id supplied
    kontekst_beleske = ""
    if predmet_id:
        try:
            beleske_res = _get_supa().table("predmet_beleske").select("sadrzaj").eq("predmet_id", predmet_id).eq("user_id", user.id).order("created_at", desc=True).limit(5).execute()
            if beleske_res.data:
                sadrzaji = [b["sadrzaj"] for b in beleske_res.data if b.get("sadrzaj")]
                if sadrzaji:
                    kontekst_beleske = "\n\nBELEŠKE IZ PREDMETA (dodatni kontekst):\n" + "\n---\n".join(sadrzaji)
        except Exception:
            logger.warning("[PROCENA] Nije uspelo učitavanje beleški za predmet_id=%s", predmet_id)

    # Inject ZR law hints if labor dispute keywords detected
    _proc_law_ctx = ""
    _PROC_LABOR_KW = ["otkaz", "radni spor", "radno pravo", "radni odnos",
                      "zaposleni", "poslodavac", "radu", "zr"]
    _PROC_ZR_HINTS = (
        "ZR Član 175: Poslodavac može otkazati ugovor o radu zaposlenom ako postoji opravdan razlog "
        "koji se odnosi na radnu sposobnost i ponašanje zaposlenog (otkaz iz subjektivnih razloga) ili "
        "usled ekonomskih, organizacionih ili tehnoloških promena (otkaz iz objektivnih razloga).\n\n"
        "ZR Član 176: Poslodavac može otkazati ugovor o radu bez otkaznog roka zaposlenom koji svojom "
        "krivicom učini povredu radne obaveze ili ne poštuje radnu disciplinu.\n\n"
        "ZR Član 184: Rešenje o otkazu mora biti u pisanoj formi sa obrazloženjem i poukom o pravnom leku. "
        "Zaposleni mora biti obavešten i dobiti 8 dana za izjašnjenje.\n\n"
        "ZR Član 191: Ako sud utvrdi nezakonit otkaz, zaposleni ima pravo na vraćanje na rad i naknadu "
        "izgubljene zarade, ili novčanu naknadu umesto vraćanja na rad."
    )
    if any(t in cinjenice.lower() for t in _PROC_LABOR_KW):
        _proc_law_ctx = (
            "DOSTUPNI ZAKONI (citiraj ISKLJUČIVO ove članove — ne citiraj iz opšteg znanja):\n\n"
            + _PROC_ZR_HINTS + "\n\n---\n\n"
        )
        logger.info("[PROCENA] ZR law hints injected")

    # Fetch case law directly from sudska_praksa namespace (returns real Pinecone objects)
    _praksa_context = ""
    try:
        from app.services.retrieve import _pretraga_praksa, _ugradi_query, _formatiraj_praksa_match
        _p_vec = await asyncio.wait_for(
            asyncio.to_thread(_ugradi_query, cinjenice[:500]),
            timeout=8.0,
        )
        _p_matches = await asyncio.wait_for(
            asyncio.to_thread(_pretraga_praksa, _p_vec, 3),
            timeout=5.0,
        )
        # Fallback: if primary query returns nothing, retry with a broad legal query
        if not _p_matches:
            logger.info("[PROCENA] Praksa: 0 primarnih — pokušavam fallback upit")
            _fallback_query = "presuda sud zakon radni spor otkaz"
            try:
                _fb_vec = await asyncio.wait_for(
                    asyncio.to_thread(_ugradi_query, _fallback_query),
                    timeout=8.0,
                )
                _p_matches = await asyncio.wait_for(
                    asyncio.to_thread(_pretraga_praksa, _fb_vec, 3),
                    timeout=5.0,
                )
                if _p_matches:
                    logger.info("[PROCENA] Praksa fallback: %d matches", len(_p_matches))
            except Exception as _fb_err:
                logger.warning("[PROCENA] Praksa fallback greška: %s", _fb_err)
        if _p_matches:
            _p_parts = [_formatiraj_praksa_match(m) for m in _p_matches]
            _p_parts = [p for p in _p_parts if p and len(p.strip()) > 30]
            if _p_parts:
                _praksa_context = (
                    "\n\nRELEVANTNA SUDSKA PRAKSA (koristi ove odlomke za sekciju 15 — RELEVANTNA PRAKSA):\n\n"
                    + "\n\n---\n\n".join(_p_parts)
                )
                logger.info("[PROCENA] Praksa: %d matches injected iz sudska_praksa", len(_p_parts))
        else:
            logger.info("[PROCENA] Praksa: 0 matches iz sudska_praksa namespace (i fallback)")
    except asyncio.TimeoutError as _pe:
        logger.warning("[PROCENA] Praksa timeout: %s", _pe)
    except Exception as _pe:
        logger.warning("[PROCENA] Praksa greška: %s", _pe, exc_info=True)

    user_content = (
        _proc_law_ctx
        + f"ČINJENICE SLUČAJA:\n{cinjenice}{kontekst_beleske}{_praksa_context}"
    )

    try:
        client = _OAI(api_key=os.getenv("OPENAI_API_KEY"))
        # BUG FIX (2026-07-24, CELINA 4): sinhroni SDK poziv unutar async def
        # blokirao je ceo event loop (90s timeout, do 4500 tokena) -- sada
        # ide preko asyncio.to_thread, isti obrazac kao ostatak fajla.
        resp = await asyncio.to_thread(
            _pozovi_openai_sync_api,
            client,
            model="gpt-4o",
            temperature=0,
            max_tokens=4500,
            timeout=90.0,
            messages=[
                {"role": "system", "content": _PROCENA_SYSTEM_PROMPT + _PROCENA_V2_ADDENDUM},
                {"role": "user",   "content": user_content},
            ],
        )
        procena_tekst = (resp.choices[0].message.content or "").strip()
    except Exception as _procena_exc:
        _sentry_capture(_procena_exc)
        logger.exception("[PROCENA] GPT-4o greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju procene. Pokušajte ponovo.")

    await UsageService.consume(_entitlement_user["user_id"], _entitlement_user["email"], "procena")

    # Phase 3.4 — Append Section 22: Pinecone-retrieved relevant court decisions
    if procena_tekst:
        try:
            _rel22 = await asyncio.wait_for(
                asyncio.to_thread(_fetch_relevantne_presude_sync, cinjenice[:500]),
                timeout=7.0,
            )
            if _rel22:
                procena_tekst += _format_sekcija22(_rel22)
                logger.info("[P3.4] /procena Sekcija 22: %d presuda", len(_rel22))
        except (asyncio.TimeoutError, Exception) as _s22e:
            logger.warning("[P3.4] /procena Sekcija 22 greška: %s", _s22e)

    # Persist to predmet_istorija if linked to a case
    # CONF-010: ista kapija kao na `/api/pitanje`. Ovde je nosivost veća —
    # payload je pun GPT-4o pravni nalaz, ne samo pitanje.
    if predmet_id and procena_tekst and not await asyncio.to_thread(
        _poseduje_predmet, user.id, predmet_id
    ):
        logger.warning(
            "[SEC] CONF-010: odbijen upis procene u predmet_istorija — predmet %s nije korisnikov",
            predmet_id,
        )
        procena_tekst_smem_upisati = False
    else:
        procena_tekst_smem_upisati = True

    if predmet_id and procena_tekst and procena_tekst_smem_upisati:
        try:
            _get_supa().table("predmet_istorija").insert({
                "predmet_id": predmet_id,
                "user_id":    user.id,
                "pitanje":    cinjenice[:500],
                "odgovor":    procena_tekst,
                "confidence": "MEDIUM",
            }).execute()
        except Exception:
            logger.warning("[PROCENA] Nije uspelo čuvanje u istoriju za predmet_id=%s", predmet_id)

    return {"procena": procena_tekst, "predmet_id": predmet_id}


# ── Phase 1.1: Auto-trigger — upload document to predmet + auto-analyze ───────

_ALLOWED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/octet-stream",  # some browsers send this for .docx
    # Operation Lawyer Day (2026-08-03): image OCR (uploaded_doc/extractor.py::
    # extract_image, Night Shift M-001, 2026-08-02) was wired into Smart
    # Intake's own upload validation but never into THIS endpoint -- the one
    # a lawyer can actually reach today (Smart Intake has no frontend entry
    # point, see decisions/2026-08-03_ZTC-FRONTEND_smart_intake_wiring_BLOCKER_REPORT.md).
    # M-001's own "photo upload now works end to end" claim was therefore only
    # true for an unreachable path -- a lawyer with phone photos of a document
    # could not upload them anywhere in the app. extract_image()'s own
    # docstring already anticipated this exact caller ("api.py's auto-analyze
    # upload") needing zero special-casing -- this closes that gap.
    "image/jpeg",
    "image/png",
}
_ALLOWED_SUFFIXES = {".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


# Program Phoenix, Mission 012 (LIVINGSYS-DEBT-021): GPT chronology extraction
# feeds directly into the urgent-deadline notification system with no human-
# review gate -- a single malformed datum_iso used to drop the entire
# extraction batch silently (one bulk .insert(rows) call, rejected atomically
# by Postgres on the first bad value). These 2 helpers close that gap:
# per-field validation before insert, and per-row (not bulk) persistence so
# one bad row can never take its siblings down with it. Extracted as module-
# level functions (not inlined in predmet_upload_auto_analyze below) so they
# are independently unit-testable without mocking the whole upload endpoint.
def _validate_hronologija_datum_iso(datum_iso, predmet_id: str) -> Optional[str]:
    """Returns a well-formed ISO date string, or None if datum_iso is absent,
    a known placeholder, or syntactically present but semantically invalid
    (e.g. GPT hallucinating "2026-13-45") -- never raises, never fabricates a
    replacement date."""
    if not datum_iso:
        return None
    if len(str(datum_iso)) < 4 or str(datum_iso).lower() in ("null", "none", ""):
        return None
    try:
        date.fromisoformat(str(datum_iso)[:10])
    except (ValueError, TypeError):
        logger.warning(
            "[P2.2] Hronologija: nevalidan datum_iso=%r odbačen (dogadjaj sačuvan bez datuma) predmet=%s",
            datum_iso, predmet_id,
        )
        return None
    return datum_iso


def _insert_hronologija_rows(rows: list, predmet_id: str) -> int:
    """Persists each predmet_hronologija row independently -- a single row's
    DB-level failure is logged and skipped, never dropping its siblings.
    Returns the count of rows actually persisted."""
    hron_count = 0
    for _hrow in rows:
        try:
            _get_supa().table("predmet_hronologija").insert(_hrow).execute()
            hron_count += 1
        except Exception as _row_e:
            logger.warning(
                "[P2.2] Hronologija: red odbačen (dogadjaj=%r) predmet=%s: %s",
                _hrow.get("dogadjaj", "")[:80], predmet_id, _row_e,
            )
    return hron_count


@app.post("/api/predmeti/{predmet_id}/upload")
@limiter.limit("10/minute")
async def predmet_upload_auto_analyze(
    predmet_id: str,
    request: Request,
    file: UploadFile = File(...),
    authorization: str = Header(None),
):
    """Phase 1.1 — Upload doc to a predmet and auto-trigger AI analysis.
    Returns {session_id, filename, procena} — procena runs automatically."""
    import hashlib
    import tempfile
    from pathlib import Path as _Path
    from openai import OpenAI as _OAI

    from uploaded_doc.chunker import chunk_document
    from uploaded_doc.cleanup import cleanup_expired
    from uploaded_doc.extractor import DocumentSafetyLimitExceeded, extract
    from uploaded_doc.ingest import ingest_session
    from uploaded_doc.session import generate_session_id, expires_at_iso

    user = await _require_auth_async(authorization)
    # _require_auth returns a plain object (not a dict) — PermissionService.require()
    # expects a dict it can read/mutate, so build one and invoke the dependency callable
    # manually (Depends() default is only resolved by FastAPI's DI, calling it directly
    # with an explicit `user=` kwarg just runs the function body against that dict).
    _entitlement_user = {"user_id": user.id, "email": user.email}
    await PermissionService.require("predmet_upload_ai")(user=_entitlement_user)

    # Validate ownership
    pred_row = _get_supa().table("predmeti").select("id,naziv,tip").eq("id", predmet_id).eq("user_id", user.id).single().execute()
    if not pred_row.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")
    predmet_naziv = pred_row.data.get("naziv", "")
    predmet_tip   = pred_row.data.get("tip", "opsti")

    # Institutional Learning & RAG Audit (2026-07-26) #1: vlasnik-znanja
    # namespace (kancelarija_{id} ako korisnik pripada kancelariji, inače
    # user_{user.id}) -- zamenjuje raniju pred_{session_id} šemu koja je
    # svaki dokument slala u sopstveni izolovani, neagregabilni namespace.
    from shared.kancelarija_utils import get_kancelarija_id as _get_kid, rag_owner_namespace as _rag_ns
    _kancelarija_id = await _get_kid(_get_supa(), user.id)
    _owner_ns = _rag_ns(user.id, _kancelarija_id)

    # File guards
    suffix = _Path(file.filename or "").suffix.lower()
    if file.content_type not in _ALLOWED_MIMES or suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Podržani formati: PDF, DOCX")
    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Fajl je preko 10MB")

    # Program Intake Sprint 001 (2026-08-04) -- ovaj endpoint je ranije NIKAD
    # nije čuvao originalni fajl bilo gde: tempfile se briše u finally bloku
    # ispod, a storage_path upisan niže (_row) je bio string labela koja ne
    # pokazuje ni na jedan stvaran objekat u Supabase Storage-u -- jedini
    # trag koji preživi je isečen tekst_sadrzaj i Pinecone vektori. Za
    # advokatski sistem evidencije, gubitak originalnog dokumenta (skenirana
    # slika, potpisan PDF) je neprihvatljiv gubitak, ne kozmetički propust.
    # Isti šifrovani-pre-upload obrazac kao Smart Intake (routers/
    # smart_intake.py::_encrypt, koji sam prati klijenti/router.py Trezor) --
    # reuse-ovan, ne ponovo izmišljen. Best-effort: ako storage upis padne,
    # ostatak toka (OCR/Pinecone/DB) NIJE blokiran (bila bi regresija u
    # dostupnosti za funkciju koja ranije nije ni postojala) -- storage_path
    # ostaje na staroj labeli, jasno signalizirajuci da original NIJE sačuvan,
    # umesto da tiho tvrdi suprotno.
    _original_storage_path = None
    try:
        import uuid as _uuid
        from routers.smart_intake import _encrypt as _si_encrypt, _STORAGE_BUCKET as _si_bucket
        _storage_key = f"{user.id}/{predmet_id}/{_uuid.uuid4().hex}{suffix}"
        _encrypted = await asyncio.to_thread(_si_encrypt, raw)
        await asyncio.to_thread(
            lambda: _get_supa().storage.from_(_si_bucket).upload(
                path=_storage_key, file=_encrypted,
                file_options={"content-type": "application/octet-stream", "upsert": "false"},
            )
        )
        _original_storage_path = _storage_key
    except Exception as _se:
        logger.warning("[P1.1] Original fajl storage upis neuspesan (nastavljam bez cuvanja originala): %s", _se)

    # Program Intake Sprint 002 (2026-08-05) -- ceo ostatak obrade (OCR ->
    # Pinecone -> DB) je uvijen u ovaj try/except da bi orphan-blob nalaz
    # (Sprint 002 Fork A §A2, "sirа od INTAKE-002, bez ikakve infrastrukture
    # za pracenje") bio zatvoren KOMPENZUJUCIM brisanjem, ne samo dokumentovan.
    # Ako je storage upis originala (iznad) uspeo, ali BILO KOJI od 5 raise
    # mesta ispod pukne (safety limit, necitljiv sken, prazan tekst, Pinecone
    # neuspeh, Sentinel hard-fail), enkriptovan blob bi ranije ostao trajno
    # sirotce u intake-dokumenti bucket-u -- niko i nista ga vise ne
    # referencira. Brisanje ovde je best-effort (ako i ono padne, samo se
    # loguje, originalna HTTPException i dalje ide ka klijentu nepromenjena)
    # i NE menja nijedan postojeci odgovor klijentu -- isti izuzetak se
    # ponovo baca posle cišcenja (`raise` bez argumenata čuva originalni tip
    # i poruku).
    try:
        # Extract text
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(raw)
                tmp_path = _Path(tmp.name)
            try:
                text, is_scanned, ocr_used, _pages, _ocr_conf = await asyncio.to_thread(extract, tmp_path)
            except DocumentSafetyLimitExceeded as _dsle:
                logger.warning(
                    "[SEC-007] Upload odbijen (safety limit) predmet=%s filename=%r razlog=%s",
                    predmet_id, file.filename, _dsle.reason,
                )
                raise HTTPException(
                    status_code=413,
                    detail="Fajl je odbijen — sadržaj posle raspakivanja prelazi bezbednosni limit.",
                )
            if is_scanned:
                raise HTTPException(
                    status_code=422,
                    detail="Tekst nije čitljiv ni optičkim prepoznavanjem (OCR). Probajte jasniju fotografiju/sken, digitalni PDF ili DOCX."
                )
        finally:
            if tmp_path and tmp_path.exists():
                try: tmp_path.unlink()
                except Exception: pass

        if not text or not text.strip():
            raise HTTPException(status_code=422, detail="Dokument je prazan ili nečitljiv.")

        if ocr_used:
            logger.info("[OCR] Dokument %r procitat OCR-om (predmet=%s)", file.filename, predmet_id)

        # Phase 2.1 — detect document type for routing to specialized prompt
        doc_type = _detect_doc_type(text)
        logger.info("[P2.1] doc_type=%r for predmet=%s, filename=%s", doc_type, predmet_id, file.filename)

        # Chunk + ingest to Pinecone
        _content_sha256 = hashlib.sha256(raw).hexdigest()
        source_meta = {
            "source_filename": file.filename,
            "source_format": suffix.lstrip("."),
            "source_sha256": _content_sha256,
            "is_scanned": ocr_used,
            "session_id": "__local__",
        }

        # Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-020): Pipeline A had zero
        # duplicate-content detection, unlike Smart Intake's own content_sha256
        # dedup (routers/smart_intake.py, migration 095's predmet_dokumenti
        # column, already applied). Non-blocking, informational only -- the
        # register's "silently skip vs surface a warning" product decision is
        # correctly NOT invented here; this doesn't change upload behavior at
        # all, it only tells the caller "you've uploaded this exact content
        # before" so a human can decide. Fail-soft: a lookup failure never
        # blocks the upload.
        _mozda_duplikat = False
        try:
            _dup_check = await asyncio.to_thread(
                lambda: _get_supa().table("predmet_dokumenti")
                    .select("id").eq("user_id", user.id).eq("content_sha256", _content_sha256)
                    .limit(1).execute()
            )
            _mozda_duplikat = bool(_dup_check.data)
        except Exception as _dup_exc:
            logger.warning("[P1.1] duplicate-content provera neuspešna (nastavljam): %s", _dup_exc)
        manifest = await asyncio.to_thread(chunk_document, text, source_meta)
        if manifest.total_chunks == 0:
            raise HTTPException(status_code=422, detail="Dokument je prazan.")

        session_id = generate_session_id()
        # Predmet dokumenti su trajni -- koriste _owner_ns (kancelarija_{id}/
        # user_{id}), ne 'pred_' + nasumičan session_id (v. napomena iznad).
        # cleanup_expired i dalje briše samo 'tmp_*' namespace-ove, pa ovaj
        # trajni namespace nikad neće biti obrisan njime.
        _pinecone_ok = True
        try:
            from shared.vector_origin import ORIGIN_CLIENT_DOC, now_iso as _now_iso
            count = await asyncio.to_thread(
                ingest_session, manifest, session_id,
                namespace_override=_owner_ns,
                extra_metadata={
                    "predmet_id": predmet_id,
                    "kancelarija_id": _kancelarija_id or "",
                    "type": "case_doc",
                    # Institutional Memory V2 (2026-07-26) STUB 2/3 -- v.
                    # shared/vector_origin.py za origin/decay semantiku.
                    "origin": ORIGIN_CLIENT_DOC,
                    "parent_id": "",
                    "origin_chain": [ORIGIN_CLIENT_DOC],
                    "created_at": _now_iso(),
                    "golden_template": False,
                },
            )
            # BETA-DATA-CONFIDENTIALITY-004 / FS-001 — USPEH SE DOKAZUJE, NE
            # PRETPOSTAVLJA. Do sada je `_pinecone_ok` ostajao True samo zato
            # što izuzetak nije podignut, a `count` se nije proveravao nijednom.
            # `ingest_session` vraca broj STVARNO upisanih vektora; ako je manji
            # od broja chunk-ova, dokument je u Pinecone-u nepotpun i ne sme da
            # se predstavi kao pretraziv.
            from uploaded_doc.ingest import ingest_je_potpun as _potpun
            if not _potpun(count, manifest.total_chunks):
                logger.error(
                    "[INGEST] nepotpun ingest predmet=%s: upisano %s od %s chunk-ova",
                    predmet_id, count, manifest.total_chunks,
                )
                _pinecone_ok = False
        except Exception as _pe:
            _pe_str = str(_pe)
            # Klasifikator je bio `"storage" in _pe_str.lower()` -- presiroko:
            # svaka greska cija poruka sadrzi "storage" (ukljucujuci greske
            # Supabase Storage-a i poruke koje pominju `storage_path`) tiho je
            # postajala "kvota" i dokument je zavrsavao kao 'sacuvano' umesto
            # da podigne 500. Suzeno na stvarne Pinecone kvota poruke.
            from uploaded_doc.ingest import je_kvota_greska as _je_kvota
            if _je_kvota(_pe):
                logger.warning("[P1.1] Pinecone storage pun — dokument se cuva bez RAG indeksiranja: %s", _pe_str[:120])
                _pinecone_ok = False
                count = 0
            else:
                raise HTTPException(status_code=500, detail=f"Greška pri obradi dokumenta: {_pe_str}")

        # Record in predmet_dokumenti — tekst_sadrzaj se cuva za trajni preview
        _dok_id = None
        _tekst_preview = text[:100_000] if text else ""
        try:
            # Izracunaj sledeci redni_broj za DOK-01, DOK-02...
            try:
                _rn_res = _get_supa().table("predmet_dokumenti") \
                    .select("redni_broj") \
                    .eq("predmet_id", predmet_id) \
                    .order("redni_broj", desc=True) \
                    .limit(1).execute()
                _max_rn = (_rn_res.data or [{}])[0].get("redni_broj") or 0
                _next_rn = int(_max_rn) + 1
            except Exception:
                _next_rn = 1

            _row = {
                "predmet_id":          predmet_id,
                "user_id":             user.id,
                "naziv_fajla":         file.filename or "dokument",
                # Program Intake Sprint 001: stvaran, dereferencibilan put u
                # intake-dokumenti bucket-u kad je upis originala uspeo (iznad);
                # inace stara "session/{id}" labela koja NIKAD nije pokazivala na
                # stvaran objekat -- zadrzana kao fallback vrednost, ne kao
                # tvrdnja da je original sacuvan (honestly reflects the gap,
                # doesn't paper over it with a value that looks the same either way).
                "storage_path":        _original_storage_path or f"session/{session_id}",
                # Deljeni namespace (v. napomena iznad) -- vise dokumenata istog
                # vlasnika deli isti namespace, razlikuju se preko predmet_id
                # metadata filtera, ne preko odvojenih namespace-ova.
                "pinecone_namespace":  _owner_ns,
                "status":              "indeksirano" if _pinecone_ok else "sacuvano",
                "velicina_kb":         max(1, len(raw) // 1024),
                "redni_broj":          _next_rn,
                # Phoenix Closure (LIVINGSYS-DEBT-020): reuses the existing
                # content_sha256 column (migration 095, already applied --
                # Smart Intake already writes/reads it) so a FUTURE upload can
                # find THIS one as a duplicate match.
                "content_sha256":      _content_sha256,
            }
            # Sačuvaj tekst ako kolona postoji (migration: ALTER TABLE predmet_dokumenti ADD COLUMN tekst_sadrzaj TEXT)
            try:
                _ins = _get_supa().table("predmet_dokumenti").insert({**_row, "tekst_sadrzaj": _tekst_preview}).execute()
            except Exception:
                try:
                    _ins = _get_supa().table("predmet_dokumenti").insert(_row).execute()
                except Exception:
                    # content_sha256 (migration 095) somehow unavailable in this
                    # environment -- fall back to the pre-020 row shape rather
                    # than losing the document entirely over an optional column.
                    _row_no_hash = {k: v for k, v in _row.items() if k != "content_sha256"}
                    _ins = _get_supa().table("predmet_dokumenti").insert(_row_no_hash).execute()
            _dok_id = (_ins.data or [{}])[0].get("id")
        except Exception:
            logger.warning("[P1.1] predmet_dokumenti insert failed for predmet=%s", predmet_id)

        # Project Sentinel (2026-08-03): ako predmet_dokumenti insert nije uspeo
        # (npr. Supabase greška odmah posle uspešnog Pinecone ingest-a iznad),
        # dokument ne postoji u sistemu iz perspektive predmeta — nastavak na AI
        # procenu/hronologiju/metapodatke bi proizveo kompletan HTTP 200 "uspeh"
        # (auto_analyzed=true, procena_tekst, predmet_istorija unos) za dokument
        # koji se nikad ne pojavljuje u case-ovoj sopstvenoj listi dokumenata —
        # potvrđena lažna potvrda uspeha (Sentinel Phase 3, failure_recovery
        # investigation §8). Pinecone vektor ostaje (isti orphan-vektor nalaz
        # kao Sprint 002 Fork A §A3 — deferred, INTAKE-001-shape, vidi
        # ARCHITECTURAL_DEBT_REGISTER.md), ali korisnik više ne dobija lažan
        # signal uspeha niti AI analizu duha-dokumenta.
        if not _dok_id:
            raise HTTPException(
                status_code=500,
                detail="Dokument je otpremljen, ali nije uspešno sačuvan u sistemu — analiza nije pokrenuta. Pokušajte ponovo.",
            )
    except Exception:
        if _original_storage_path:
            try:
                from routers.smart_intake import _STORAGE_BUCKET as _si_bucket_cleanup
                await asyncio.to_thread(
                    lambda: _get_supa().storage.from_(_si_bucket_cleanup).remove([_original_storage_path])
                )
                logger.info(
                    "[P1.1] Orphan cleanup: obrisan originalni fajl iz storage-a posle neuspesne obrade (predmet=%s, key=%s)",
                    predmet_id, _original_storage_path,
                )
            except Exception as _ce:
                logger.warning(
                    "[P1.1] Orphan cleanup neuspesan (blob moze ostati sirotce) predmet=%s, key=%s: %s",
                    predmet_id, _original_storage_path, _ce,
                )
        raise

    # D22 v1 (VINDEX_OPERATIONAL_GAP_REGISTER.md G-003) — isti obrazac kao
    # predmet_create iznad. 'dokument_upload' je vec u AUDITABLE_ACTIONS.
    if _dok_id:
        try:
            from shared.audit_immutable import log_action
            asyncio.create_task(log_action(
                "dokument_upload",
                user_id=user.id,
                resource_type="dokument",
                resource_id=_dok_id,
                ip=request.client.host if request.client else None,
                metadata={"predmet_id": predmet_id, "naziv_fajla": file.filename or "dokument"},
            ))
        except Exception as _ae:
            logger.warning("[AUDIT] dokument_upload log greška: %s", _ae)

    # ── NEW_EVIDENCE_REGISTERED / DOCUMENT_ACCEPTED — Program Delta, Sprint
    # 003 (2026-08-05) — Canonical Event Migration II. This USED TO be two
    # direct, in-process background tasks: `asyncio.create_task(asyncio.
    # to_thread(klasifikuj_i_sacuvaj, ...))` and `asyncio.create_task(
    # _genome_bg())` (the latter with a crude `asyncio.sleep(3)` heuristic,
    # hoping classification finished writing tip_dokaza before Genome read
    # it) — Pipeline A deciding for itself "what happens after a document is
    # uploaded", the exact scattered-decision pattern Program Delta exists
    # to eliminate, and the SAME pattern Sprints 001-002 already migrated
    # for Pipeline C (Smart Intake). Replaced with two durable outbox
    # emissions (services/event_bus.py::emit_durable, the SAME helper
    # Pipeline C uses) — the Canonical Consequence Engine (services/
    # case_evolution.py::handle_case_changed) now owns deciding and
    # executing what follows, reusing its EXISTING NEW_EVIDENCE_REGISTERED/
    # DOCUMENT_ACCEPTED consequence definitions UNCHANGED (no new Genome/
    # Timeline/Evidence capability — Pipeline A's document-accept event now
    # gets the exact same canonical treatment Pipeline C's already gets,
    # including a Timeline entry Pipeline A never produced before — that is
    # the intended effect of convergence, not scope creep). Emitted in this
    # order (evidence first, genome second) so a single-worker/low-
    # concurrency dispatch processes classification before the genome
    # refresh reads tip_dokaza — an eventual-consistency ordering, not a
    # hard guarantee, honestly no stronger than the sleep(3) heuristic it
    # replaces (see Reliability Verification Report II).
    if _dok_id:
        try:
            from services.event_bus import EventType, emit_durable
            await emit_durable(
                EventType.NEW_EVIDENCE_REGISTERED,
                user.id,
                predmet_id,
                {"dokument_id": _dok_id, "naziv": file.filename or "dokument", "trigger": "pipeline_a_upload"},
            )
        except Exception as _ce:
            logger.warning("[SMART_EVOLUTION] NEW_EVIDENCE_REGISTERED durable event upis greška (non-fatal) dok=%s: %s", _dok_id, _ce)

    if _dok_id and predmet_id:
        try:
            from services.event_bus import EventType, emit_durable
            await emit_durable(
                EventType.DOCUMENT_ACCEPTED,
                user.id,
                predmet_id,
                {"dokumenti": [file.filename or "dokument"], "trigger": "pipeline_a_upload"},
            )
        except Exception as _ge:
            logger.warning("[SMART_EVOLUTION] DOCUMENT_ACCEPTED durable event upis greška (non-fatal) predmet=%s: %s", predmet_id, _ge)

    # ── AUTO ANALYSIS ──────────────────────────────────────────────────────────
    # Phase 2.1: choose prompt and text limit based on detected doc type
    if doc_type == "presuda":
        system_prompt  = _PRESUDA_SYSTEM_PROMPT
        text_limit     = 8000
        text_label     = "TEKST PRESUDE"
        truncate_label = "\n[...presuda se nastavlja, prikazan je izvod...]"
        max_tok        = 1200
    else:
        system_prompt  = _PROCENA_SYSTEM_PROMPT + _PROCENA_V2_ADDENDUM
        text_limit     = 3000
        text_label     = "Sadržaj uploadovanog dokumenta"
        truncate_label = "\n[...dokument nastavlja...]"
        max_tok        = 4000

    # ── Phase 2.1 RAG + Law Hints ─────────────────────────────────────────────
    _rag_query = f"{predmet_naziv} {predmet_tip} " + " ".join(text[:400].split())
    _rag_query = _rag_query[:500]
    _law_chunks: list[str] = []

    # Step 1: Hardcoded law hints — zero Pinecone calls, zero latency.
    # Injected directly when keywords indicate a labor dispute.
    _LABOR_KW = ["otkaz", "radni spor", "radno pravo", "radni odnos",
                 "zaposleni", "poslodavac", "radu", "zr"]
    _ZR_HINTS = (
        "ZR Član 175: Poslodavac može otkazati ugovor o radu zaposlenom ako postoji opravdan razlog "
        "koji se odnosi na radnu sposobnost i ponašanje zaposlenog (otkaz iz subjektivnih razloga) ili "
        "usled ekonomskih, organizacionih ili tehnoloških promena (otkaz iz objektivnih razloga).\n\n"
        "ZR Član 176: Poslodavac može otkazati ugovor o radu bez otkaznog roka zaposlenom koji svojom "
        "krivicom učini povredu radne obaveze ili ne poštuje radnu disciplinu, u skladu sa zakonom ili "
        "opštim aktom.\n\n"
        "ZR Član 184: Rešenje o otkazu ugovora o radu mora biti u pisanoj formi i mora da sadrži "
        "obrazloženje i pouku o pravnom leku. Poslodavac je dužan da pre donošenja rešenja o otkazu "
        "zaposlenom dostavi obaveštenje o razlozima za otkaz i ostavi mu rok od najmanje 8 dana da se "
        "izjasni o navodima iz obaveštenja.\n\n"
        "ZR Član 191: Ako sud utvrdi da je zaposlenom nezakonito prestao radni odnos, zaposleni ima "
        "pravo na vraćanje na rad i isplatu izgubljene zarade sa zakonskom kamatom, ili umesto vraćanja "
        "na rad, na novčanu naknadu u iznosu koji određuje sud u zavisnosti od vremena provedenog na radu "
        "i godina staža."
    )
    if any(t in _rag_query.lower() for t in _LABOR_KW):
        _law_chunks.append(_ZR_HINTS)
        logger.info("[P2.1] ZR law hints injected (hardcoded, no Pinecone)")

    # Step 2: RAG retrieval for case law context (4s timeout, k=3)
    _rag_meta: dict = {}
    try:
        from app.services.retrieve import retrieve_documents as _retrieve
        # F-01: skup predmeta koje pozivalac stvarno sme da vidi, izracunat
        # kanonski (v. shared/rag_acl.py). Bez njega retrieval ne sme da
        # dodirne namespace vlasnika.
        from shared.rag_acl import dozvoljeni_predmeti as _acl_predmeti
        _dozvoljeni_pred = await asyncio.to_thread(_acl_predmeti, _get_supa(), user.id)
        # Institutional Learning & RAG Audit (2026-07-26) #2: kancelarija_namespace
        # + current_predmet_id daju ovoj auto-analizi pristup ranijim predmetima
        # istog vlasnika (kancelarije ili solo korisnika), sa prioritetom na
        # TRENUTNI predmet -- v. app/services/retrieve.py.
        _rag_docs, _rag_meta = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: _retrieve(
                    _rag_query, 3,
                    kancelarija_namespace=_owner_ns,
                    current_predmet_id=predmet_id,
                    dozvoljeni_predmeti=_dozvoljeni_pred,
                )
            ),
            timeout=4.0,
        )
        if _rag_docs:
            _seen = {_ZR_HINTS}
            for _d in _rag_docs[:3]:
                if _d not in _seen:
                    _law_chunks.append(_d)
                    _seen.add(_d)
            logger.info("[P2.1] RAG: %d chunks, top_law=%s, query='%.60s'",
                        len(_rag_docs), _rag_meta.get("top_law", "?"), _rag_query)
    except asyncio.TimeoutError:
        logger.warning("[P2.1] RAG timeout (>4s) — nastavljamo bez RAG")
    except Exception:
        logger.warning("[P2.1] RAG greška — nastavljamo bez RAG")

    law_context = ""
    if _law_chunks:
        law_context = (
            "DOSTUPNI ZAKONI (citiraj ISKLJUČIVO ove članove — ne citiraj iz opšteg znanja):\n\n"
            + "\n\n---\n\n".join(_law_chunks[:6])
            + "\n\n---\n\n"
        )

    # Inject top 3 praksa matches for section 11 (RELEVANTNA PRAKSA) — direct namespace query
    _praksa_upload_ctx = ""
    if doc_type != "presuda":
        try:
            from app.services.retrieve import _pretraga_praksa, _ugradi_query, _formatiraj_praksa_match
            _up_vec = await asyncio.wait_for(
                asyncio.to_thread(_ugradi_query, _rag_query[:400]),
                timeout=6.0,
            )
            _up_pm = await asyncio.wait_for(
                asyncio.to_thread(_pretraga_praksa, _up_vec, 3),
                timeout=4.0,
            )
            if _up_pm:
                _up_parts = [_formatiraj_praksa_match(m) for m in _up_pm]
                _up_parts = [p for p in _up_parts if p and len(p.strip()) > 30]
                if _up_parts:
                    _praksa_upload_ctx = (
                        "\n\nRELEVANTNA SUDSKA PRAKSA (koristi ove odlomke za sekciju 11 — RELEVANTNA PRAKSA):\n\n"
                        + "\n\n---\n\n".join(_up_parts)
                    )
                    logger.info("[P2.1] Praksa: %d matches injected", len(_up_parts))
        except asyncio.TimeoutError:
            logger.warning("[P2.1] Praksa fetch timeout")
        except Exception as _upe:
            logger.warning("[P2.1] Praksa fetch greška: %s", _upe)

    cinjenice_text = (
        law_context
        + f"Predmet: {predmet_naziv} (oblast: {predmet_tip})\n\n"
        + f"{text_label}:\n"
        + text[:text_limit]
        + (truncate_label if len(text) > text_limit else "")
        + _praksa_upload_ctx
    )

    # Fetch existing notes for additional context (skip for presuda — full text is more useful)
    if doc_type != "presuda":
        try:
            beleske_res = _get_supa().table("predmet_beleske").select("sadrzaj").eq("predmet_id", predmet_id).eq("user_id", user.id).order("created_at", desc=True).limit(3).execute()
            if beleske_res.data:
                b_tekst = "\n---\n".join(b["sadrzaj"] for b in beleske_res.data if b.get("sadrzaj"))
                if b_tekst:
                    cinjenice_text += f"\n\nBELEŠKE IZ PREDMETA:\n{b_tekst}"
        except Exception:
            pass

    # ── Run procena + hronologija GPT-4o calls IN PARALLEL ───────────────────────
    import json as _json, re as _re_hron
    _oai_client = _OAI(api_key=os.getenv("OPENAI_API_KEY"))
    _hron_user  = f"Dokument: {file.filename or 'dokument'}\n\n{text[:6000]}"

    @llm_retry
    def _call_procena():
        return _oai_client.chat.completions.create(
            model="gpt-4o", temperature=0, max_tokens=max_tok, timeout=60.0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": cinjenice_text},
            ],
        )

    @llm_retry
    def _call_hronologija():
        return _oai_client.chat.completions.create(
            model="gpt-4o", temperature=0, max_tokens=1500, timeout=35.0,
            messages=[
                {"role": "system", "content": _HRONOLOGIJA_SYSTEM_PROMPT},
                {"role": "user",   "content": _hron_user},
            ],
        )

    _META_SYSTEM = (
        "Ti si AI sistem za ekstrakciju pravnih metapodataka iz srpskih pravnih dokumenata. "
        "Odgovori ISKLJUČIVO u JSON formatu bez teksta van JSON-a. "
        'Struktura: {"tip_dokumenta": str, "stranke": [str], "datum_dokumenta": str, '
        '"iznosi": [{"opis": str, "iznos": str}], "predlog_predmeta": str}\n'
        "tip_dokumenta: tuzba|ugovor|zalba|presuda|resenje|izjava|punomoćje|ostalo\n"
        "stranke: lista punih imena (max 5)\n"
        "datum_dokumenta: ISO format YYYY-MM-DD ili prazan string\n"
        "iznosi: novčani iznosi sa opisom (max 5)\n"
        "predlog_predmeta: kratki naziv za predmet (max 80 znakova)"
    )

    @llm_retry
    def _call_metapodaci():
        return _oai_client.chat.completions.create(
            model="gpt-4o-mini", temperature=0, max_tokens=600, timeout=25.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _META_SYSTEM},
                {"role": "user",   "content": f"Dokument: {file.filename or 'dokument'}\n\n{text[:4000]}"},
            ],
        )

    # Mission Migration (2026-08-03) -- Canonical AI Infrastructure Adoption:
    # wraps the 3 parallel GPT calls in explicit case_context() so their
    # ai_forensics rows carry predmet_id/document_id (previously only the
    # request-level correlation_id was inherited automatically, per Mission
    # Ledger's default). asyncio.to_thread() copies the current contextvars
    # context into its executor thread, so this contextvar is visible inside
    # each of the 3 synchronous _call_*() functions above.
    from shared.ai_provenance import case_context as _ai_case_ctx
    with _ai_case_ctx(
        predmet_id=predmet_id, document_id=_dok_id, module_name="api_upload",
        operation_name="procena_hronologija_metapodaci",
    ):
        _pr, _hr, _meta = await asyncio.gather(
            asyncio.to_thread(_call_procena),
            asyncio.to_thread(_call_hronologija),
            asyncio.to_thread(_call_metapodaci),
            return_exceptions=True,
        )

    # Jedan consume() poziv za celokupnu upload-triggered AI analizu (3 paralelna
    # potpoziva iznad broje se kao JEDNA upotreba ove funkcije, ne tri).
    await UsageService.consume(_entitlement_user["user_id"], _entitlement_user["email"], "predmet_upload_ai")

    # Final Beta Gate F6 (HIGH): if ALL 3 GPT calls failed (e.g. a sustained
    # OpenAI outage), this endpoint still returns HTTP 200 with
    # auto_analyzed: false and zero AI value produced -- but the credit above
    # was already charged. Refund it, mirroring the established
    # consume-then-refund-on-failure pattern /api/pitanje already uses
    # (UsageService.refund calls a few hundred lines up). A partial failure
    # (1 or 2 of 3 calls succeeded) still produced real value and is NOT
    # refunded, matching that same feature's existing partial-success billing.
    if isinstance(_pr, Exception) and isinstance(_hr, Exception) and isinstance(_meta, Exception):
        await UsageService.refund(_entitlement_user["user_id"], _entitlement_user["email"], "predmet_upload_ai")
        logger.warning(
            "[P1.1] Sva 3 AI poziva neuspešna za predmet=%s — kredit refundovan (procena=%s, hronologija=%s, metapodaci=%s)",
            predmet_id, _pr, _hr, _meta,
        )

    # ── Process procena ───────────────────────────────────────────────────────
    procena_tekst = ""
    if not isinstance(_pr, Exception):
        procena_tekst = (_pr.choices[0].message.content or "").strip()
        logger.info("[P1.1] Auto-procena uspešna za predmet=%s, chars=%d", predmet_id, len(procena_tekst))
    else:
        logger.warning("[P1.1] Auto-procena greška za predmet=%s: %s", predmet_id, _pr)

    # Phase 3.4 — Append Section 22: Pinecone-retrieved relevant court decisions
    if procena_tekst and doc_type != "presuda":
        try:
            _rel_presude = await asyncio.wait_for(
                asyncio.to_thread(_fetch_relevantne_presude_sync, cinjenice_text[:500]),
                timeout=7.0,
            )
            if _rel_presude:
                procena_tekst += _format_sekcija22(_rel_presude)
                logger.info("[P3.4] upload Sekcija 22: %d presuda dodato za predmet=%s", len(_rel_presude), predmet_id)
        except asyncio.TimeoutError:
            logger.warning("[P3.4] upload Sekcija 22 timeout — preskačem")
        except Exception as _s22e:
            logger.warning("[P3.4] upload Sekcija 22 greška: %s", _s22e)

    if procena_tekst:
        try:
            _get_supa().table("predmet_istorija").insert({
                "predmet_id": predmet_id,
                "user_id":    user.id,
                "pitanje":    f"[Auto-analiza] {file.filename or 'dokument'}",
                "odgovor":    procena_tekst,
                "confidence": "MEDIUM",
            }).execute()
        except Exception:
            logger.warning("[P1.1] predmet_istorija insert failed for predmet=%s", predmet_id)

    # ── Process hronologija ───────────────────────────────────────────────────
    hron_count = 0
    if not isinstance(_hr, Exception):
        try:
            hron_raw = (_hr.choices[0].message.content or "").strip()
            # Strip markdown fences
            if "```" in hron_raw:
                hron_raw = "\n".join(
                    line for line in hron_raw.splitlines()
                    if not line.strip().startswith("```")
                )
            # Extract JSON array even if GPT-4o added surrounding text
            _m = _re_hron.search(r'\[[\s\S]*\]', hron_raw)
            if _m:
                hron_raw = _m.group(0)
            hron_data = _json.loads(hron_raw)
            if isinstance(hron_data, list) and hron_data:
                _VALID_VAZNOST = {"kritičan", "važan", "informativan"}
                rows = []
                for ev in hron_data[:50]:
                    if not isinstance(ev, dict) or not ev.get("dogadjaj"):
                        continue
                    datum_iso = _validate_hronologija_datum_iso(ev.get("datum_iso"), predmet_id)
                    vaznost = ev.get("vaznost", "informativan")
                    if vaznost not in _VALID_VAZNOST:
                        vaznost = "informativan"
                    rows.append({
                        "predmet_id":     predmet_id,
                        "user_id":        user.id,
                        "dokument_naziv": file.filename or "dokument",
                        "datum":          str(ev.get("datum") or "")[:30],
                        "datum_iso":      datum_iso,
                        "dogadjaj":       str(ev.get("dogadjaj", ""))[:500],
                        "akter":          str(ev.get("akter") or "")[:200],
                        "vaznost":        vaznost,
                    })
                if rows:
                    # Program Phoenix, Mission 012 (LIVINGSYS-DEBT-021): per-row
                    # insert (was one bulk .insert(rows)) so a single row's
                    # DB-level failure (any other unforeseen malformed field)
                    # can't silently drop every sibling event in the same
                    # batch -- each event is now independently persisted.
                    hron_count = _insert_hronologija_rows(rows, predmet_id)
                    logger.info("[P2.2] Hronologija: %d/%d događaja sačuvano za predmet=%s", hron_count, len(rows), predmet_id)
        except Exception as _he:
            logger.warning("[P2.2] Hronologija greška: %s | raw[:150]=%r", _he, hron_raw[:150] if 'hron_raw' in dir() else "")
    else:
        logger.warning("[P2.2] Hronologija GPT greška za predmet=%s: %s", predmet_id, _hr)

    # ── Process metapodaci ────────────────────────────────────────────────────
    import json as _json_meta
    metapodaci = {}
    if not isinstance(_meta, Exception):
        try:
            metapodaci = _json_meta.loads(_meta.choices[0].message.content or "{}")
            if metapodaci:
                _get_supa().table("predmet_istorija").insert({
                    "predmet_id": predmet_id,
                    "user_id":    user.id,
                    "pitanje":    f"[Metapodaci] {file.filename or 'dokument'}",
                    "odgovor":    _json_meta.dumps(metapodaci, ensure_ascii=False),
                    "confidence": "HIGH",
                }).execute()
        except Exception as _me:
            logger.warning("[P3-META] metapodaci parse/insert greška: %s", _me)
    else:
        logger.warning("[P3-META] metapodaci GPT greška za predmet=%s: %s", predmet_id, _meta)

    # ── Auto-linking suggestions ─────────────────────────────────────────────
    predlozi_povezivanja = []
    if metapodaci.get("stranke"):
        for _stranka_ime in (metapodaci["stranke"] or [])[:4]:
            if not _stranka_ime or len(_stranka_ime.strip()) < 3:
                continue
            try:
                _parts = _stranka_ime.strip().split()
                _filter = (
                    f"firma.ilike.%{_stranka_ime}%,ime.ilike.%{_parts[0]}%"
                    if len(_parts) >= 2
                    else f"firma.ilike.%{_stranka_ime}%,ime.ilike.%{_stranka_ime}%"
                )
                _kl_res = await asyncio.to_thread(
                    lambda f=_filter: _get_supa().table("klijenti")
                        .select("id,ime,prezime,firma,tip")
                        .eq("user_id", user.id)
                        .is_("deleted_at", "null")
                        .or_(f)
                        .limit(2)
                        .execute()
                )
                for _kl in (_kl_res.data or []):
                    _naziv = f"{_kl.get('ime','')} {_kl.get('prezime','')}".strip() or _kl.get("firma", "")
                    _conf = 95 if _stranka_ime.lower() in _naziv.lower() or _naziv.lower() in _stranka_ime.lower() else 74
                    predlozi_povezivanja.append({
                        "tip":        "klijent",
                        "id":         _kl["id"],
                        "naziv":      _naziv,
                        "razlog":     f"Stranka '{_stranka_ime}' pronađena u dokumentu",
                        "pouzdanost": _conf,
                    })
            except Exception as _ale:
                logger.warning("[AUTO-LINK] klijent search greška: %s", _ale)
    # Deduplicate by id, keep highest confidence
    _seen_al: dict = {}
    for _p in predlozi_povezivanja:
        _pid = _p["id"]
        if _pid not in _seen_al or _p["pouzdanost"] > _seen_al[_pid]["pouzdanost"]:
            _seen_al[_pid] = _p
    predlozi_povezivanja = sorted(_seen_al.values(), key=lambda x: -x["pouzdanost"])

    asyncio.create_task(asyncio.to_thread(cleanup_expired))

    # Mission Migration (2026-08-03) -- Canonical AI Infrastructure Adoption:
    # dedicated audit entry for "AI analyzed this document," distinct from
    # the raw "dokument_upload" audit above (that one records the upload
    # act; this records the AI decision act) -- correlation_id auto-inherits
    # from the request context.
    if procena_tekst:
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            action="dokument_ai_analiza_complete", user_id=user.id,
            resource_type="predmet_dokumenti", resource_id=_dok_id,
        ))

    return {
        "session_id":          session_id,
        "filename":            file.filename,
        "chunk_count":         count,
        "predmet_id":          predmet_id,
        "doc_type":            doc_type,
        "procena":             procena_tekst,
        "auto_analyzed":       bool(procena_tekst),
        "hronologija_count":   hron_count,
        "metadata":            metapodaci,
        "predlozi_povezivanja": predlozi_povezivanja,
        # Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-020): informational only,
        # does not block or alter the upload -- see the content_sha256 check above.
        "mozda_duplikat":      _mozda_duplikat,
        # Final Beta Gate F7 (MEDIUM): storage upload of the ORIGINAL file
        # (see the try/except a few hundred lines up) is best-effort and was
        # never disclosed to the caller -- a lawyer whose signed original
        # failed to persist saw an identical success screen to one whose
        # original was safely stored. False when the storage write failed,
        # even though the rest of the upload (OCR/Pinecone/DB) still
        # succeeded by design.
        "original_preserved":  bool(_original_storage_path),
    }


# ── Phase 2.2: GET hronologija for a predmet ─────────────────────────────────

@app.get("/api/predmeti/{predmet_id}/hronologija")
@limiter.limit("30/minute")
async def predmet_hronologija_get(
    predmet_id: str,
    request: Request,
    authorization: str = Header(None),
):
    """Phase 2.2 — Return sorted chronology events for a predmet."""
    user = await _require_auth_async(authorization)
    pred_row = _get_supa().table("predmeti").select("id").eq("id", predmet_id).eq("user_id", user.id).single().execute()
    if not pred_row.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")

    try:
        res = (
            _get_supa()
            .table("predmet_hronologija")
            .select("id,datum,datum_iso,dogadjaj,akter,vaznost,dokument_naziv,created_at")
            .eq("predmet_id", predmet_id)
            .eq("user_id", user.id)
            .order("datum_iso", desc=False)
            .order("created_at", desc=False)
            .limit(100)
            .execute()
        )
        items = res.data or []
        # Items with null datum_iso go to end — separate and append
        with_date    = [i for i in items if i.get("datum_iso")]
        without_date = [i for i in items if not i.get("datum_iso")]
        return {"hronologija": with_date + without_date}
    except Exception:
        logger.exception("[P2.2] hronologija_get greška za predmet=%s", predmet_id)
        raise HTTPException(status_code=500, detail="Greška pri učitavanju hronologije")


# ── AI Preporuka za predmet ───────────────────────────────────────────────────

@app.get("/api/predmeti/{predmet_id}/ai-preporuka")
@limiter.limit("10/minute")
async def predmet_ai_preporuka(
    predmet_id: str,
    request: Request,
    user: dict = Depends(PermissionService.require("predmet_ai_preporuka")),
):
    """
    Analizira stanje predmeta i vraća AI preporuku:
    - Sledeći korak
    - Dokumenta koja nedostaju
    - Ključni rokovi
    - Presude koje podržavaju poziciju
    """
    supa = _get_supa()
    pred = supa.table("predmeti").select("naziv, opis, tip, status").eq("id", predmet_id).eq("user_id", user["user_id"]).single().execute()
    if not pred.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")

    p = pred.data
    docs_r    = supa.table("predmet_dokumenti").select("naziv_fajla").eq("predmet_id", predmet_id).execute()
    beleske_r = supa.table("predmet_beleske").select("sadrzaj").eq("predmet_id", predmet_id).limit(5).order("created_at", desc=True).execute()
    hron_r    = supa.table("predmet_hronologija").select("datum, dogadjaj, vaznost").eq("predmet_id", predmet_id).order("datum_iso", desc=False).limit(10).execute()

    docs_list    = [d.get("naziv_fajla", "") for d in (docs_r.data or [])]
    beleske_list = [b.get("sadrzaj", "")[:200] for b in (beleske_r.data or [])]
    hron_list    = [f"{h.get('datum','')} — {h.get('dogadjaj','')}" for h in (hron_r.data or [])]

    from openai import AsyncOpenAI as _AOI
    oai = _AOI(api_key=os.getenv("OPENAI_API_KEY", ""))

    system_p = (
        "Ti si pravni asistent za srpsko pravo. Na osnovu podataka o predmetu "
        "napravi kratku preporuku u JSON formatu bez ikakvog teksta van JSON-a:\n"
        "{\n"
        '  "sledeci_korak": str,\n'
        '  "dokumenta_koja_nedostaju": [str],\n'
        '  "kljucni_rokovi": [{"naziv": str, "rok": str, "zakon": str}],\n'
        '  "preporucene_presude": [str],\n'
        '  "rizici": [str]\n'
        "}\n"
        "Budi konkretan i kratak. Max 3 stavke po listi."
    )

    context = (
        f"Naziv predmeta: {p.get('naziv','')}\n"
        f"Opis: {p.get('opis','')}\n"
        f"Tip: {p.get('tip','')}\n"
        f"Status: {p.get('status','')}\n"
        f"Dokumenta u sistemu: {', '.join(docs_list) or 'nema'}\n"
        f"Poslednje beleške: {'; '.join(beleske_list) or 'nema'}\n"
        f"Hronologija: {'; '.join(hron_list) or 'nema'}"
    )

    try:
        resp = await _pozovi_openai_async_api(
            oai,
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_p},
                {"role": "user",   "content": context},
            ],
            temperature=0.15,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        import json as _json
        preporuka = _json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        _sentry_capture(e)
        logger.error("[AI-PREPORUKA] greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri generisanju preporuke.")

    await UsageService.consume(user["user_id"], user.get("email", ""), "predmet_ai_preporuka")
    return {"predmet_id": predmet_id, "preporuka": preporuka}


# ── Dokument preview — rekonstruiše tekst iz Pinecone ────────────────────────

@app.get("/api/predmeti/{predmet_id}/dokumenti/{dok_id}/preview")
@limiter.limit("20/minute")
async def predmet_dokument_preview(
    predmet_id: str,
    dok_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Vraća tekst dokumenta. Čita iz Supabase (trajno), ili kao fallback iz Pinecone."""
    uid = user["user_id"]
    supa = _get_supa()

    row = await asyncio.to_thread(
        lambda: supa.table("predmet_dokumenti")
            .select("id,naziv_fajla,pinecone_namespace,velicina_kb,status,created_at,tekst_sadrzaj")
            .eq("id", dok_id)
            .eq("predmet_id", predmet_id)
            .eq("user_id", uid)
            .single()
            .execute()
    )
    if not row.data:
        raise HTTPException(status_code=404, detail="Dokument nije pronađen")

    d = row.data

    # Program Intake Sprint 001 (2026-08-04) -- 'dokument_view' je vec u
    # AUDITABLE_ACTIONS (shared/audit_immutable.py) i vec ima UI labelu
    # (routers/intelligence_timeline.py) -- samo je ovo pozivno mesto
    # nedostajalo (Fork 3 finding #3: plumbing postoji na oba kraja, samo
    # poziv fali). Isti fire-and-forget/best-effort obrazac kao
    # 'dokument_upload' iznad -- greška u audit upisu ne sme oboriti pregled.
    try:
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            "dokument_view",
            user_id=uid,
            resource_type="dokument",
            resource_id=dok_id,
            ip=request.client.host if request.client else None,
            metadata={"predmet_id": predmet_id, "naziv_fajla": d.get("naziv_fajla", "")},
        ))
    except Exception as _ae:
        logger.warning("[AUDIT] dokument_view log greška: %s", _ae)

    # 1. Primaran izvor: tekst_sadrzaj u Supabase (trajno, ne ističe)
    tekst = (d.get("tekst_sadrzaj") or "").strip()

    # 2. Fallback: rekonstrukcija iz Pinecone (za stare dokumente bez tekst_sadrzaj)
    if not tekst:
        ns = d.get("pinecone_namespace") or ""
        if ns:
            ns_prefix = "pred_" if ns.startswith("pred_") else "tmp_"
            session_id = ns.removeprefix("tmp_").removeprefix("pred_")
            from routers.dokument import _fetch_session_tekst
            tekst = await asyncio.to_thread(_fetch_session_tekst, session_id, ns_prefix)

    return {
        "naziv_fajla": d.get("naziv_fajla", ""),
        "velicina_kb": d.get("velicina_kb", 0),
        "status": d.get("status", ""),
        "created_at": d.get("created_at", ""),
        "tekst": tekst or "",
        "dostupan": bool(tekst),
    }


# ── P1 — Case Workspace ───────────────────────────────────────────────────────

@app.get("/api/predmeti/{predmet_id}/workspace")
@limiter.limit("20/minute")
async def predmet_workspace(
    predmet_id: str,
    request: Request,
    user: dict = Depends(PermissionService.require("predmet_workspace_ai")),
):
    """
    Jedinstveni Case Workspace — sve što je potrebno za predmet u jednom pozivu.
    Vraća: predmet, stranke, protivna strana, dokumenti, rokovi (urgentni),
    komentari, beleske, komunikacija, historija, sudska praksa preview, statistike.
    """
    uid = user["user_id"]
    supa = _get_supa()

    # Step 1: Verify ownership
    pred = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("*").eq("id", predmet_id).eq("user_id", uid).single().execute()
    )
    if not pred.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")

    # Step 2: Parallel fetch of all related data
    (beleske_r, istorija_r, dokumenti_r, hronologija_r, komentari_r, pk_r, rocista_ws_r, dokazi_ws_r, case_actions_ws_r) = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_beleske").select("*").eq("predmet_id", predmet_id).order("created_at", desc=True).limit(50).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija").select("pitanje,odgovor,confidence,created_at").eq("predmet_id", predmet_id).order("created_at", desc=True).limit(30).execute()),
        # Operation Single Brain (2026-08-07): tip_dokaza added -- this select fed directly
        # into calculate_procesni_rizik below (_deterministic_risk) without it, so the
        # Cockpit's own "Otkriveni problemi" card could tell a lawyer a document type was
        # missing even when it was fully uploaded (missing-evidence detection reads exactly
        # this column). Execution-tested by this mission's Team 6 against routers/ccc.py's
        # correct query for identical case data, confirming a real divergence this closes.
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select("id,naziv_fajla,status,velicina_kb,created_at,pinecone_namespace,redni_broj,tip_dokaza").eq("predmet_id", predmet_id).order("redni_broj").execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija").select("*").eq("predmet_id", predmet_id).order("datum_iso", desc=False).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_komentari").select("*").eq("predmet_id", predmet_id).order("kreirano", desc=True).limit(50).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_klijenti").select("klijent_id,uloga_klijenta,napomena").eq("predmet_id", predmet_id).execute()),
        # 'datum' dodat (G-027) — potreban calculate_procesni_rizik za predstojeci/kriticni racun,
        # ranije se ovde selektovalo samo 'id' jer je CRS koristio samo broj rocista.
        asyncio.to_thread(lambda: supa.table("rocista").select("id,datum").eq("predmet_id", predmet_id).eq("user_id", uid).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokazi").select("snaga,kategorija,pravni_element").eq("predmet_id", predmet_id).is_("deleted_at", "null").execute()),
        # Operation Single Brain, Mission 002: feeds compute_case_readiness() below so the
        # Case Ready Score checklist can be capped by the canonical readiness engine --
        # see docs/singlebrain/READINESS_AUTHORITY_SPEC.md.
        asyncio.to_thread(lambda: supa.table("case_actions").select("prioritet,tip,status,razlog,dedupe_key").eq("predmet_id", predmet_id).eq("status", "open").execute()),
    )

    # Step 3: Resolve linked klijenti
    stranke, protivna_strana, svedoci, ostali_ucesnici = [], [], [], []
    komunikacija = []
    if pk_r.data:
        klijent_ids = [r["klijent_id"] for r in pk_r.data]
        kl_rows = await asyncio.to_thread(
            lambda: supa.table("klijenti")
                .select("id,ime,prezime,firma,tip,status,email,telefon")
                .in_("id", klijent_ids)
                .is_("deleted_at", "null")
                .execute()
        )
        kl_map = {r["id"]: r for r in (kl_rows.data or [])}
        for pk in pk_r.data:
            kl = kl_map.get(pk["klijent_id"])
            if not kl:
                continue
            entry = {**kl, "uloga": pk.get("uloga_klijenta", "stranka"), "napomena": pk.get("napomena", "")}
            uloga = pk.get("uloga_klijenta", "stranka")
            if uloga == "stranka":
                stranke.append(entry)
            elif uloga == "protivna_stranka":
                protivna_strana.append(entry)
            elif uloga == "svedok":
                svedoci.append(entry)
            else:
                ostali_ucesnici.append(entry)

        # Step 4: Komunikacija linked through all klijent_ids
        try:
            kom_r = await asyncio.to_thread(
                lambda: supa.table("klijent_komunikacija")
                    .select("id,tip,datum_vreme,kratak_opis,klijent_id")
                    .in_("klijent_id", klijent_ids)
                    .order("datum_vreme", desc=True)
                    .limit(30)
                    .execute()
            )
            komunikacija = kom_r.data or []
        except Exception as e:
            logger.warning("[WORKSPACE] komunikacija greška: %s", e)

    # Step 5: Urgentni rokovi (kritičan + datum u budućnosti)
    from datetime import date
    today_iso = date.today().isoformat()
    urgentni_rokovi = [
        h for h in (hronologija_r.data or [])
        if h.get("vaznost") == "kritičan" and (h.get("datum_iso") or "") >= today_iso
    ]

    # Step 5b: Procesni rizik — G-027/AR-01 jedini deterministicki izvor istine.
    # Racunat OVDE (ne u GPT promptu) jer Cockpit vise ne sme da odredjuje nivo
    # rizika sam — samo ga prikazuje i (preko GPT-a) objasnjava zasto.
    from services.risk_engine import calculate_procesni_rizik as _calc_rizik
    from shared.constants import EXPECTED_DOCS as _EXPECTED_DOCS_WS

    _deterministic_risk = _calc_rizik(
        dokazi=(dokazi_ws_r.data if not isinstance(dokazi_ws_r, Exception) else []) or [],
        dokumenti=dokumenti_r.data or [],
        rocista=rocista_ws_r.data or [],
        tip_predmeta=pred.data.get("tip") or "ostalo",
        expected_docs=_EXPECTED_DOCS_WS,
    )

    # Otkriveni problemi — Core Consolidation Sec 1.2 (2026-07-22): jedini
    # algoritam za "sledecu akciju" u celoj platformi (services.risk_engine.
    # identify_case_problems). Cockpit vise ne pusta GPT da SAM smisli
    # sledecu akciju/prioritet — GPT ostaje samo za ai_sazetak (slobodan
    # opis) i rizik_objasnjenje (zasto je rizik takav), obe cisto
    # objasnjavajuce, ne odlucujuce (AR-01).
    from services.risk_engine import identify_case_problems as _identify_problems
    _otkriveni_problemi = _identify_problems(_deterministic_risk, pred.data.get("tip") or "ostalo")

    # Step 6: Parallel — praksa preview + cockpit AI
    import os as _os_ws, json as _json_ws
    from openai import AsyncOpenAI as _OAI_ws

    _COCKPIT_SYSTEM = (
        "Ti si pravni asistent. Procesni rizik predmeta je VEC IZRACUNAT "
        "determinstickim sistemom i dat ti je u kontekstu — NE odredjuj ga sam, "
        "samo objasni ZASTO je takav (faktori_plus/faktori_minus). "
        "Otkriveni problemi predmeta su TAKODJE vec determinsticki izracunati — "
        "ne predlazi sledecu akciju, to nije tvoj posao. "
        "Vrati ISKLJUČIVO JSON bez teksta van JSON-a:\n"
        '{"ai_sazetak": str (maks 100 reči, konkretan opis stanja predmeta),\n'
        ' "rizik_objasnjenje": {"faktori_plus": [str], "faktori_minus": [str]}}\n'
        "Ne koristi opšte fraze. Budi konkretan."
    )

    async def _fetch_cockpit_ai():
        try:
            oai = _OAI_ws(api_key=_os_ws.getenv("OPENAI_API_KEY", ""))
            p = pred.data
            _stranke_str = ", ".join(
                (s.get("ime","") + " " + s.get("prezime","")).strip() or s.get("firma","")
                for s in stranke[:3]
            )
            _protivna_str = ", ".join(
                (s.get("ime","") + " " + s.get("prezime","")).strip() or s.get("firma","")
                for s in protivna_strana[:3]
            )
            ctx = (
                f"Predmet: {p.get('naziv','')} | Tip: {p.get('tip','')} | Status: {p.get('status','')}\n"
                f"Opis: {(p.get('opis') or '')[:400]}\n"
                f"Stranke: {_stranke_str or 'nema'}\n"
                f"Protivna strana: {_protivna_str or 'nema'}\n"
                f"Dokumenti: {', '.join(d.get('naziv_fajla','') for d in (dokumenti_r.data or [])[:5]) or 'nema'}\n"
                f"Poslednje beleske: {' | '.join((b.get('sadrzaj') or '')[:80] for b in (beleske_r.data or [])[:3]) or 'nema'}\n"
                f"Rokovi: {' | '.join((h.get('dogadjaj','') or '')[:80] + ' (' + (h.get('datum_iso','') or '') + ')' for h in (hronologija_r.data or [])[:5]) or 'nema'}\n"
                f"Procesni rizik (vec izracunat, ne menjaj): {_deterministic_risk['nivo']} "
                f"— snaga dokaza: {_deterministic_risk['snaga_dokaza']}, "
                f"nedostajucih dokaza: {_deterministic_risk['nedostajuci_count']}, "
                f"kriticnih rokova (≤7 dana): {_deterministic_risk['kriticni_rokovi']}"
            )
            resp = await _pozovi_openai_async_api(
                oai,
                model="gpt-4o-mini", temperature=0.1, max_tokens=700,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _COCKPIT_SYSTEM},
                    {"role": "user",   "content": ctx},
                ],
            )
            return _json_ws.loads(resp.choices[0].message.content or "{}")
        except Exception as _ce:
            _sentry_capture(_ce)
            logger.warning("[WORKSPACE-COCKPIT] AI greška: %s", _ce)
            return {}

    async def _fetch_praksa_preview():
        _results = []
        try:
            from app.services.retrieve import _pretraga_praksa, _ugradi_query
            p = pred.data
            _q = f"{p.get('naziv','')} {p.get('opis','')} {p.get('tip','')}".strip()[:400]
            if _q:
                _vec = await asyncio.wait_for(asyncio.to_thread(_ugradi_query, _q), timeout=5.0)
                _matches = await asyncio.wait_for(asyncio.to_thread(_pretraga_praksa, _vec, 3), timeout=4.0)
                for m in (_matches or [])[:3]:
                    meta = getattr(m, "metadata", None) or {}
                    _results.append({
                        "decision_number": meta.get("decision_number", ""),
                        "court":           meta.get("court", ""),
                        "decision_date":   meta.get("decision_date", ""),
                        "izreka_preview":  meta.get("izreka_preview", "")[:200],
                        "score":           round(getattr(m, "score", 0), 4),
                    })
        except Exception as _pe:
            logger.warning("[WORKSPACE] praksa preview greška: %s", _pe)
        return _results

    cockpit_raw, praksa_preview = await asyncio.gather(
        _fetch_cockpit_ai(),
        _fetch_praksa_preview(),
        return_exceptions=True,
    )
    if isinstance(cockpit_raw, Exception):
        cockpit_raw = {}
    if isinstance(praksa_preview, Exception):
        praksa_preview = []

    await UsageService.consume(user["user_id"], user.get("email", ""), "predmet_workspace_ai")

    # Step 6b: Risk history — compare today vs previous snapshot.
    # G-027: izvor nivoa je SAD _deterministic_risk (jedini izvor istine), ne
    # vise cockpit_raw — GPT vise ne odredjuje nivo, samo faktori_plus/minus.
    import json as _json_risk
    _rizik_objasnjenje = cockpit_raw.get("rizik_objasnjenje", {}) if isinstance(cockpit_raw, dict) else {}
    _rizik_nivo = _deterministic_risk["nivo"].lower()
    _rizik_promena = None
    _today_tag = f"[Rizik] {today_iso}"
    try:
        _prev_risk_r = await asyncio.to_thread(
            lambda: supa.table("predmet_istorija")
                .select("odgovor,created_at,pitanje")
                .eq("predmet_id", predmet_id)
                .eq("user_id", uid)
                .like("pitanje", "[Rizik]%")
                .order("created_at", desc=True)
                .limit(3)
                .execute()
        )
        _prev_records = _prev_risk_r.data or []
        _today_saved  = any(r.get("pitanje","") == _today_tag for r in _prev_records)
        _prev_other   = next((r for r in _prev_records if r.get("pitanje","") != _today_tag), None)
        if _prev_other:
            try:
                _prev_data = _json_risk.loads(_prev_other.get("odgovor","{}"))
                _prev_nivo = _prev_data.get("nivo","")
                if _prev_nivo and _prev_nivo != _rizik_nivo:
                    _rizik_promena = {
                        "prethodni":     _prev_nivo,
                        "trenutni":      _rizik_nivo,
                        "datum_promene": _prev_other.get("created_at",""),
                    }
            except Exception:
                pass
        if not _today_saved:
            asyncio.create_task(asyncio.to_thread(
                lambda: supa.table("predmet_istorija").insert({
                    "predmet_id": predmet_id,
                    "user_id":    uid,
                    "pitanje":    _today_tag,
                    "odgovor":    _json_risk.dumps({
                        "nivo":          _rizik_nivo,
                        "faktori_plus":  _rizik_objasnjenje.get("faktori_plus", []),
                        "faktori_minus": _rizik_objasnjenje.get("faktori_minus", []),
                    }, ensure_ascii=False),
                    "confidence": "MEDIUM",
                }).execute()
            ))
    except Exception as _re:
        logger.warning("[WORKSPACE-RISK-HISTORY] greška: %s", _re)

    # Step 7: Rokovi po hitnosti
    # Program Omega Sprint 006 (2026-08-06): derived from the canonical
    # model (shared/attention_priority.py::VAZNOST_TO_CANONICAL) instead of
    # an independently-maintained {word: number} dict — same values as
    # before (kritičan=0...ostalo=3), now provably a translation, not a
    # 5th parallel copy. See docs/omega/CANONICAL_ATTENTION_MODEL.md.
    _vaznost_order = {word: _CANONICAL_ORDER[canon] for word, canon in _VAZNOST_TO_CANONICAL.items()}
    rokovi_po_hitnosti = sorted(
        hronologija_r.data or [],
        key=lambda h: (
            _vaznost_order.get(h.get("vaznost", "ostalo"), 3),
            h.get("datum_iso") or "9999-12-31",
        ),
    )

    # Step 8: Poslednja aktivnost (merge across beleske/komentari/komunikacija/istorija)
    _sve_aktivnosti = []
    for b in (beleske_r.data or [])[:1]:
        _sve_aktivnosti.append({"tip": "beleska", "datum": b.get("created_at",""), "opis": (b.get("sadrzaj") or "")[:120]})
    for k in (komentari_r.data or [])[:1]:
        _sve_aktivnosti.append({"tip": "komentar", "datum": k.get("created_at",""), "opis": (k.get("tekst") or "")[:120]})
    for km in komunikacija[:1]:
        _sve_aktivnosti.append({"tip": "komunikacija", "datum": km.get("datum_vreme",""), "opis": (km.get("kratak_opis") or "")[:120]})
    for it in (istorija_r.data or [])[:1]:
        _sve_aktivnosti.append({"tip": "analiza", "datum": it.get("created_at",""), "opis": (it.get("pitanje") or "")[:120]})
    _sve_aktivnosti = [a for a in _sve_aktivnosti if a.get("datum")]
    _sve_aktivnosti.sort(key=lambda a: a["datum"], reverse=True)
    poslednja_aktivnost = _sve_aktivnosti[0] if _sve_aktivnosti else None

    # Step 9: Statistike
    from datetime import datetime
    created_at = pred.data.get("created_at", "")
    try:
        dana_od_otvaranja = (datetime.now() - datetime.fromisoformat(created_at.replace("Z", "+00:00").replace("+00:00", ""))).days
    except Exception:
        dana_od_otvaranja = 0

    # Case Ready Score — computed from loaded data
    _ws_rocista = (rocista_ws_r.data or []) if not isinstance(rocista_ws_r, Exception) else []
    _ws_klijenti = (pk_r.data or []) if not isinstance(pk_r, Exception) else []
    _ws_ist_full = (istorija_r.data or []) if not isinstance(istorija_r, Exception) else []
    try:
        from services.case_pipeline import calculate_case_ready_score as _calc_crs
        from shared.case_readiness import compute_case_readiness as _compute_readiness_ws
        _ws_readiness = _compute_readiness_ws(
            (case_actions_ws_r.data or []) if not isinstance(case_actions_ws_r, Exception) else []
        )
        _crs, _checklist = _calc_crs(
            dokumenti=dokumenti_r.data or [],
            klijenti=_ws_klijenti,
            rokovi=hronologija_r.data or [],
            istorija=_ws_ist_full,
            rocista=_ws_rocista,
            readiness=_ws_readiness,
        )
    except Exception:
        _crs, _checklist = 0, []
        _ws_readiness = None

    return {
        "predmet":            pred.data,
        "stranke":            stranke,
        "protivna_strana":    protivna_strana,
        "svedoci":            svedoci,
        "ostali_ucesnici":    ostali_ucesnici,
        "dokumenti":          dokumenti_r.data or [],
        "rokovi": {
            "urgentni":       urgentni_rokovi,
            "po_hitnosti":    rokovi_po_hitnosti,
            "hronologija":    hronologija_r.data or [],
        },
        "komentari":          komentari_r.data or [],
        "beleske":            beleske_r.data or [],
        "komunikacija":       komunikacija,
        "istorija":           istorija_r.data or [],
        "sudska_praksa_preview": praksa_preview,
        "cockpit": {
            "ai_sazetak":          cockpit_raw.get("ai_sazetak", ""),
            # Core Consolidation Sec 1.2 (2026-07-22): "sledeca_akcija" GPT
            # polje uklonjeno — bilo je jedina preostala AR-01 povreda u
            # Cockpit-u (prioritet je bio potpuno GPT-odlucen, ranije G-029).
            # otkriveni_problemi je sada JEDINI izvor za ovu povrsinu, isti
            # algoritam kao Matter Intel i Case Ready Score.
            "otkriveni_problemi":  _otkriveni_problemi,
            # G-027/AR-01: nivo dolazi ISKLJUČIVO iz _deterministic_risk (isti
            # izvor kao Matter Intelligence Bar) — GPT samo popunjava
            # faktori_plus/minus (objašnjenje), nikad sam ne bira nivo.
            "procena_rizika": {
                "nivo":          _deterministic_risk["nivo"].lower(),
                "faktori_plus":  _rizik_objasnjenje.get("faktori_plus", []),
                "faktori_minus": _rizik_objasnjenje.get("faktori_minus", []),
            },
            "poslednja_aktivnost": poslednja_aktivnost,
            "rizik_promena":       _rizik_promena,
        },
        "case_ready_score":   _crs,
        "checklist":          _checklist,
        # Operation Single Brain, Mission 002: the CANONICAL_OWNER's own verdict, alongside
        # the checklist score it may have capped -- see docs/singlebrain/READINESS_AUTHORITY_SPEC.md.
        "readiness_status":   (_ws_readiness or {}).get("status"),
        "statistike": {
            "dokumenti_count":    len(dokumenti_r.data or []),
            "beleske_count":      len(beleske_r.data or []),
            "komentari_count":    len(komentari_r.data or []),
            "dana_od_otvaranja":  dana_od_otvaranja,
            "urgentni_rokovi":    len(urgentni_rokovi),
        },
    }


# ── P3/P4 — One-click document link confirmation ─────────────────────────────

class ConfirmLinksReq(BaseModel):
    klijent_ids: list = Field(default=[])
    uloga:       str  = Field(default="stranka", max_length=40)
    dodaj_rok:   Optional[dict] = Field(default=None)


@app.post("/api/predmeti/{predmet_id}/confirm-links")
@limiter.limit("20/minute")
async def predmet_confirm_links(
    predmet_id: str,
    req: ConfirmLinksReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Jednim klikom potvrdi AI predloge — poveži klijente i/ili dodaj rok.
    Poziva se iz frontend confirm-card-a posle upload-a dokumenta.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    pred = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", uid).single().execute()
    )
    if not pred.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")

    linked  = []
    rok_dodat = False

    # Lambda Certification 002 (2026-08-06) -- ranije se klijent_ids iz
    # tela zahteva vezivalo za predmet bez provere da li ti klijenti uopste
    # pripadaju pozivaocu (API Penetration sweep, potvrdjeno: dvokorak
    # cross-tenant PII leak preko get_predmet-a). Vlasnistvo nad SVAKIM
    # id-jem se sada proverava pre vezivanja, isti obrazac kao svuda
    # drugde u ovom fajlu (.eq("user_id", uid)).
    own_kl = await asyncio.to_thread(
        lambda: supa.table("klijenti")
            .select("id")
            .eq("user_id", uid)
            .in_("id", (req.klijent_ids or [])[:5])
            .execute()
    )
    own_kl_ids = {r["id"] for r in (own_kl.data or [])}

    for kl_id in (req.klijent_ids or [])[:5]:
        if kl_id not in own_kl_ids:
            logger.warning("[CONFIRM-LINKS] odbijen tudj klijent_id=%s od uid=%s", kl_id, uid)
            continue
        try:
            existing = await asyncio.to_thread(
                lambda _kid=kl_id: supa.table("predmet_klijenti")
                    .select("predmet_id")
                    .eq("predmet_id", predmet_id)
                    .eq("klijent_id", _kid)
                    .execute()
            )
            if not (existing.data):
                await asyncio.to_thread(
                    lambda _kid=kl_id: supa.table("predmet_klijenti").insert({
                        "predmet_id":     predmet_id,
                        "klijent_id":     _kid,
                        "uloga_klijenta": req.uloga,
                    }).execute()
                )
            linked.append(kl_id)
        except Exception as e:
            logger.warning("[CONFIRM-LINKS] klijent link greška: %s", e)

    if req.dodaj_rok:
        try:
            rok = req.dodaj_rok
            await asyncio.to_thread(
                lambda: supa.table("predmet_hronologija").insert({
                    "predmet_id": predmet_id,
                    "user_id":    uid,
                    "dogadjaj":   (rok.get("naziv") or "Rok")[:200],
                    "datum":      rok.get("datum_iso",""),
                    "datum_iso":  rok.get("datum_iso",""),
                    "vaznost":    rok.get("vaznost","bitan"),
                    "akter":      "Auto-detect (AI)",
                }).execute()
            )
            rok_dodat = True
        except Exception as e:
            logger.warning("[CONFIRM-LINKS] rok insert greška: %s", e)

    asyncio.create_task(_audit(uid, "confirm_links", predmet_id))
    return {"predmet_id": predmet_id, "linked_klijenti": linked, "rok_dodat": rok_dodat, "success": True}


# ── Portfolio Intelligence ─────────────────────────────────────────────────────

@app.get("/api/portfolio")
@limiter.limit("30/minute")
async def portfolio_intelligence(request: Request, user: dict = Depends(get_current_user)):
    """
    Partner morning view — KPI pregled cele kancelarije.
    Vraća: kpi (aktivni, visok_rizik, rokovi_7_dana, neaktivni_30_dana),
    hitni_predmeti, rokovi_ove_nedelje, neaktivni, po_tipu.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    from datetime import date as _dtpf, timedelta as _tdpf
    today_pf  = _dtpf.today()
    today_iso = today_pf.isoformat()
    next7_iso = (today_pf + _tdpf(days=7)).isoformat()
    next14    = (today_pf + _tdpf(days=14)).isoformat()
    past30    = (today_pf - _tdpf(days=30)).isoformat()

    preds_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id,naziv,tip,status,created_at")
            .eq("user_id", uid)
            .execute()
    )
    predmeti = preds_r.data or []
    if not predmeti:
        return {
            "kpi": {"aktivni":0,"zatvoreni":0,"visok_rizik":0,"rokovi_7_dana":0,"neaktivni_30_dana":0,"bez_klijenta":0},
            "rokovi_ove_nedelje": [], "hitni_predmeti": [], "neaktivni": [], "po_tipu": {},
        }

    aktv_ids = [p["id"] for p in predmeti if p.get("status") != "zatvoren"]
    if not aktv_ids:
        aktv_ids = [p["id"] for p in predmeti]

    hron_r, risk_r, aktivnost_r, pk_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("predmet_id,dogadjaj,datum_iso,vaznost")
            .in_("predmet_id", aktv_ids)
            .gte("datum_iso", today_iso)
            .lte("datum_iso", next14)
            .order("datum_iso")
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("predmet_id,odgovor,created_at")
            .in_("predmet_id", aktv_ids)
            .like("pitanje", "[Rizik]%")
            .order("created_at", desc=True)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("predmet_id,created_at")
            .in_("predmet_id", aktv_ids)
            .not_.like("pitanje", "[Rizik]%")
            .order("created_at", desc=True)
            .limit(max(len(aktv_ids) * 3, 60))
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_klijenti")
            .select("predmet_id")
            .in_("predmet_id", aktv_ids)
            .execute()),
        return_exceptions=True,
    )

    import json as _jpf
    risk_map_pf: dict = {}
    for r in (risk_r.data if not isinstance(risk_r, Exception) else []):
        pid = r["predmet_id"]
        if pid not in risk_map_pf:
            try:
                risk_map_pf[pid] = _jpf.loads(r.get("odgovor","{}"))
            except Exception:
                pass

    akt_map: dict = {}
    for a in (aktivnost_r.data if not isinstance(aktivnost_r, Exception) else []):
        pid = a["predmet_id"]
        if pid not in akt_map:
            akt_map[pid] = (a.get("created_at","") or "")

    has_klijent = set(
        r["predmet_id"] for r in (pk_r.data if not isinstance(pk_r, Exception) else [])
    )

    hron_all = hron_r.data if not isinstance(hron_r, Exception) else []
    hron_map_pf: dict = {}
    for h in hron_all:
        hron_map_pf.setdefault(h["predmet_id"], []).append(h)

    aktivni   = [p for p in predmeti if p.get("status") != "zatvoren"]
    visok_ids = [pid for pid, rz in risk_map_pf.items() if rz.get("nivo") == "visok"]
    rokovi_7  = [h for h in hron_all if (h.get("datum_iso","") or "") <= next7_iso]

    neaktivni_list = []
    for p in aktivni:
        last = akt_map.get(p["id"],"")
        if not last or last[:10] < past30:
            neaktivni_list.append({
                "id": p["id"], "naziv": p["naziv"],
                "poslednja_aktivnost": last[:10] if last else None,
            })

    _RSCORE = {"visok":4,"srednji":2,"nizak":1}
    hitni = []
    for p in aktivni:
        pid  = p["id"]
        nivo = risk_map_pf.get(pid,{}).get("nivo","")
        urg  = sum(1 for h in hron_map_pf.get(pid,[]) if h.get("vaznost")=="kritičan")
        if nivo=="visok" or urg>0:
            hitni.append({
                "id": pid, "naziv": p["naziv"], "tip": p.get("tip",""),
                "rizik_nivo": nivo, "urgentni_rokovi": urg,
                "sledeci_rok": hron_map_pf.get(pid,[])[0] if hron_map_pf.get(pid) else None,
            })
    hitni.sort(key=lambda x: (_RSCORE.get(x["rizik_nivo"],0)*-1, x["urgentni_rokovi"]*-1))

    po_tipu: dict = {}
    for p in predmeti:
        t = (p.get("tip") or "ostalo")
        po_tipu[t] = po_tipu.get(t,0) + 1

    return {
        "kpi": {
            "aktivni":            len(aktivni),
            "zatvoreni":          len(predmeti) - len(aktivni),
            "visok_rizik":        len(visok_ids),
            "rokovi_7_dana":      len(rokovi_7),
            "neaktivni_30_dana":  len(neaktivni_list),
            "bez_klijenta":       len(aktv_ids) - len([i for i in aktv_ids if i in has_klijent]),
        },
        "rokovi_ove_nedelje": rokovi_7[:10],
        "hitni_predmeti":     hitni[:5],
        "neaktivni":          neaktivni_list[:5],
        "po_tipu":            po_tipu,
    }


# ── Notification Engine ────────────────────────────────────────────────────────
# Program Omega, Final Sprint 006 (2026-08-06) — Canonical Attention Engine:
# `GET /api/notifications` (a 4th independent, fully-computed alert system —
# "bez novog DB table-a", its own priority vocabulary "visoka"/"srednja"/
# "niska", its own inline sort dict, its own risk-change detector duplicating
# routers/dashboard.py's own trend logic) removed here — confirmed via a
# repo-wide grep of static/vindex.js to have ZERO frontend callers (the
# frontend's own `notif_load()` calls `GET /notifications`, a completely
# different, DB-backed, live route — routers/notifications.py). Retiring a
# fully dead, self-contained, side-effect-free endpoint is the safest
# possible elimination this sprint's own Phase 4 asks for: nothing currently
# depends on it. See docs/omega/ALERT_CONSOLIDATION_REPORT.md.

# ── Usage Analytics ────────────────────────────────────────────────────────────

@app.get("/api/usage/stats")
@limiter.limit("10/minute")
async def usage_stats(request: Request, user: dict = Depends(get_current_user)):
    """Produkt inteligencija — top funkcije, dnevna aktivnost, copilot usage."""
    uid  = user["user_id"]
    supa = _get_supa()

    from datetime import date as _dus, timedelta as _tus
    past30_us = (_dus.today() - _tus(days=30)).isoformat()

    audit_r, predmeti_r, pitanja_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("audit_log")
            .select("akcija,ts")
            .eq("user_id", uid)
            .gte("ts", past30_us+"T00:00:00")
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("tip,status")
            .eq("user_id", uid)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("pitanje,created_at")
            .eq("user_id", uid)
            .not_.like("pitanje","[Rizik]%")
            .gte("created_at", past30_us+"T00:00:00")
            .order("created_at", desc=True)
            .limit(200)
            .execute()),
        return_exceptions=True,
    )

    action_counts: dict = {}
    daily_act: dict = {}
    for a in (audit_r.data if not isinstance(audit_r, Exception) else []):
        ak  = a.get("akcija","ostalo")
        action_counts[ak] = action_counts.get(ak,0) + 1
        day = (a.get("ts") or "")[:10]
        if day:
            daily_act[day] = daily_act.get(day,0) + 1

    po_statusu: dict = {}
    for p in (predmeti_r.data if not isinstance(predmeti_r, Exception) else []):
        s = p.get("status","aktivan")
        po_statusu[s] = po_statusu.get(s,0) + 1

    pitanja_all = pitanja_r.data if not isinstance(pitanja_r, Exception) else []
    top_actions = sorted(action_counts.items(), key=lambda x: x[1], reverse=True)[:8]

    return {
        "top_funkcije":         [{"akcija":a,"count":c} for a,c in top_actions],
        "daily_activity":       dict(sorted(daily_act.items())[-14:]),
        "predmeti_po_statusu":  po_statusu,
        "copilot_aktivnost_30d": len(pitanja_all),
        "total_akcija_30d":     len(audit_r.data if not isinstance(audit_r, Exception) else []),
    }



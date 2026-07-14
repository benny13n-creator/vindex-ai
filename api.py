# -*- coding: utf-8 -*-
"""
Vindex AI — FastAPI server sa Supabase autentifikacijom i kreditnim sistemom
"""

import logging
import os
import asyncio
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Request, Depends, HTTPException, status, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

BASE_DIR = Path(__file__).parent
load_dotenv()

# ─── Azure OpenAI patch (mora pre svih router importa) ───────────────────────
from shared.ai_client import _patch_openai_module
_patch_openai_module()

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
_validate_enc_key()

import time as _time
from collections import deque as _deque
from datetime import datetime, timedelta

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
from app.services import audit_log as _al
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
from shared.deps import require_credits, _refund_one_credit, _increment_monthly_usage, _get_monthly_usage
from shared.cost import begin_cost_tracking, log_cost_to_db
from shared.permissions import PermissionService
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

# REDIS_URL ostaje samo za info (health check) — rate limiter UVEK in-memory.
# Razlog: Upstash free tier (256MB) može prekoračiti kvotu; redis.ResponseError
# iz slowapi dekoratora ruši sve rute pre nego što se endpoint body izvrši,
# zaobilazeći sve try/except blokove unutar endpointa.
_REDIS_URL = os.getenv("REDIS_URL", "").strip()
logger.info("Rate limiter: in-memory (single-worker; REDIS_URL=%s)", bool(_REDIS_URL))
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60/hour"],
)
app = FastAPI(title="Vindex AI", docs_url=None, redoc_url=None)
app.state.limiter = limiter


def _json_rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"greska": "Previše zahteva. Sačekajte nekoliko sekundi i pokušajte ponovo."},
    )


app.add_exception_handler(RateLimitExceeded, _json_rate_limit_handler)
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
from routers.vindex_memory        import router as vindex_memory_router
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
from routers.decision_replay      import router as decision_replay_router
from routers.case_dna             import router as case_dna_router
from routers.health_index         import router as health_index_router
from routers.intelligence_timeline import router as intel_timeline_router
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
app.include_router(vindex_memory_router)
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
app.include_router(decision_replay_router)
app.include_router(case_dna_router)
app.include_router(health_index_router)
app.include_router(intel_timeline_router)
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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Hvatanje svih neočekivanih izuzetaka — vraća JSON umesto HTML stranice greške."""
    from starlette.exceptions import HTTPException as _HTTPExc
    if isinstance(exc, _HTTPExc):
        raise exc
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

_AI_ENDPOINTS = {"/api/pitanje", "/api/analiza", "/api/kompletna", "/api/copilot",
                 "/api/nacrt", "/api/drafting"}


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


import uuid as _uuid
import contextvars as _cv
_correlation_id_var: _cv.ContextVar[str] = _cv.ContextVar("correlation_id", default="")


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    cid = request.headers.get("X-Correlation-ID") or str(_uuid.uuid4())
    _correlation_id_var.set(cid)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    return response


@app.middleware("http")
async def user_rate_limit_middleware(request: Request, call_next):
    """
    User-level sliding window rate limiter.
    Dopunjuje IP-based slowapi — štiti od botnet-a koji rotira IP adrese.
    Aktivira se samo na /api/ rutama da ne usporava static fajlove.
    """
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)

    uid = getattr(request.state, "user_id", None)
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
        return v.strip()




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
                .eq("status", "aktivan")
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
                    .eq("status", "aktivan")
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
import subprocess as _subprocess

def _get_git_hash() -> str:
    try:
        return _subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(BASE_DIR), stderr=_subprocess.DEVNULL, timeout=3
        ).decode().strip()
    except Exception:
        import time
        return str(int(time.time()))[-6:]

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

@app.get("/")
@app.head("/")
def root():
    path = BASE_DIR / "landing.html"
    if path.exists():
        return FileResponse(path)
    return {"status": "ok", "servis": "Vindex AI"}


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


@app.get("/terms")
def terms_of_service():
    path = BASE_DIR / "terms.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})
    return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})


@app.get("/pricing", include_in_schema=False)
def pricing_page():
    path = BASE_DIR / "pricing.html"
    if path.exists():
        return FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})
    return JSONResponse(status_code=404, content={"error": "Stranica nije pronađena."})


@app.get("/health")
@app.head("/health")
def health():
    import os as _os
    return {
        "status": "ok",
        "pid": _os.getpid(),
        "redis": bool(_REDIS_URL),
        "workers": int(_os.getenv("WEB_CONCURRENCY", 1)),
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
    if cron_secret and x_secret != cron_secret:
        raise HTTPException(status_code=403, detail="Neovlašćen pristup.")

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
            pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
            index = pc.Index("vindex-ai")
            stats = index.describe_index_stats()
            emb = OpenAIEmbeddings(model="text-embedding-3-large")
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
            emb = OpenAIEmbeddings(model="text-embedding-3-large")
            vec = emb.embed_query("test")
            result["embeddings"] = f"OK — dim={len(vec)}"
        except Exception as e:
            result["embeddings"] = f"GREŠKA: {type(e).__name__}: {str(e)[:200]}"

        return result

    return await asyncio.to_thread(_run_checks)


@app.get("/robots.txt")
def robots():
    return PlainTextResponse(
        "User-agent: *\nAllow: /\nDisallow: /api/\n",
        media_type="text/plain",
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
            lambda: _oai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content":
                    f"Napiši kratku, profesionalnu poruku za klijenta o statusu predmeta '{naziv}' "
                    f"(status: {status}). Jedna do dve rečenice. Bez pravnih saveta. Ekavica. Ne pominjaj AI."}],
                max_tokens=100,
                temperature=0.4,
            )
        )
        ai_status = ai_r.choices[0].message.content.strip()
    except Exception:
        pass

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
        asyncio.create_task(asyncio.to_thread(send_welcome_email, result["user_id"], req.email))
        asyncio.create_task(_setup_trial(_get_supa(), result["user_id"]))
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

    # 5. Test deduct_credit RPC (dry-run: oduzima 0 — proverava samo da li RPC postoji)
    try:
        r = supa.rpc("deduct_credit", {"p_user_id": user_id}).execute()
        out["deduct_credit_rpc"] = f"OK — vrati: {r.data}"
        # Odmah vrati oduzeti kredit da test bude nedestruktivan
        try:
            supa.table("user_credits").update(
                {"credits_remaining": profil.get("credits_remaining", 0) if isinstance(profil, dict) else 0}
            ).eq("user_id", user_id).execute()
            out["deduct_credit_rpc"] += " (kredit vraćen — test je bio nedestruktivan)"
        except Exception:
            pass
    except Exception as exc:
        out["deduct_credit_rpc"] = f"GREŠKA: {type(exc).__name__}: {str(exc)[:300]}"

    # 6. Dijagnoza
    diag = []
    if "GREŠKA" in str(out.get("table_user_credits", "")):
        diag.append("KRITIČNO: user_credits tabela ne postoji — pokrenite supabase_setup.sql u Supabase Dashboard")
    elif "NEMA REDA" in str(out.get("user_credits_row", "")):
        diag.append("UPOZORENJE: user_credits tabela postoji ali korisnik nema red — trigger nije radio ili SQL nije pokrenut")
    if "GREŠKA" in str(out.get("deduct_credit_rpc", "")):
        diag.append("KRITIČNO: deduct_credit RPC ne postoji — pokrenite supabase_setup.sql")
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
    docs = retrieve_documents(q, k=10)
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
            docs = retrieve_documents(q, k=6)
            elapsed = _t.perf_counter() - t0
            out["retrieve"] = {
                "elapsed_sec": round(elapsed, 2),
                "docs_count":  len(docs),
                "docs": [{"index": i, "length": len(d), "preview": d[:400]} for i, d in enumerate(docs)],
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
        t0 = _time.monotonic()
        rezultat = await pokreni(ask_agent, req.pitanje, None)
        latency_ms = int((_time.monotonic() - t0) * 1000)
        _al.log_response(
            endpoint="/api/bot/ask",
            query_hash=qh,
            tip=None,
            confidence=rezultat.get("confidence"),
            top_score=rezultat.get("top_score"),
            top_article=rezultat.get("top_article"),
            top_law=rezultat.get("top_law"),
            response_text=rezultat.get("data", ""),
            latency_ms=latency_ms,
        )
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
    try:
        qh = _q_hash(req.pitanje)
        logger.info("Pitanje [uid=%.8s] [q=%s]", user["user_id"], qh)
        asyncio.create_task(_audit(user["user_id"], "pitanje", qh))

        # Atomično oduzmi kredit PRE agent poziva (isti timing kao stari require_credits
        # pre-deduction) — refunduje se ispod ako je odgovor iz keša ili blokiran.
        preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "ai_pravna_pitanja")

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
        t0 = _time.monotonic()
        _firma_ns = await _get_firma_namespace(user["user_id"])
        _extra_ns = [_firma_ns] if _firma_ns else None
        _mem_ctx = await _fetch_firm_memory_context(user["user_id"], pitanje=req.pitanje)
        rezultat = await pokreni(ask_agent, pitanje_za_agenta, history, _extra_ns, _mem_ctx)
        latency_ms = int((_time.monotonic() - t0) * 1000)
        asyncio.create_task(log_cost_to_db(user["user_id"], "pitanje"))
        _al.log_response(
            endpoint="/api/pitanje",
            query_hash=qh,
            tip=tip,
            confidence=rezultat.get("confidence"),
            top_score=rezultat.get("top_score"),
            top_article=rezultat.get("top_article"),
            top_law=rezultat.get("top_law"),
            response_text=rezultat.get("data", ""),
            latency_ms=latency_ms,
        )
        # UsageService.consume() already pre-deducted the credit above (same timing as the
        # old require_credits pre-deduction) — refund on cache-hit/blocked, exactly as before.
        if rezultat.get("from_cache", False) or rezultat.get("blocked", False):
            await UsageService.refund(user["user_id"], user.get("email", ""), "ai_pravna_pitanja")
            preostalo = preostalo + 1

        # F5.4: persist Q&A turn to predmet_istorija
        if predmet_id and rezultat.get("status") == "success" and not rezultat.get("blocked"):
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
    except Exception:
        _qh_safe = locals().get("qh", "?")
        logger.exception("Greška u /api/pitanje [q=%s]", _qh_safe)
        return greska_odgovor(
            500,
            "Došlo je do greške na serveru. Pokušajte ponovo za nekoliko sekundi.",
        )


@app.post("/api/pitanje/stream")
@limiter.limit("10/minute")
async def pitanje_stream(req: PitanjeReq, request: Request, user: dict = Depends(PermissionService.require("ai_pravna_pitanja"))):
    """
    SSE streaming verzija /api/pitanje.
    Retrieval se izvršava normalno, zatim se GPT-4o odgovor stream-uje
    chunk po chunk — korisnik vidi izlaz odmah, bez čekanja na kompletan odgovor.

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
    from openai import OpenAI as _OAI

    qh = _q_hash(req.pitanje)
    logger.info("PitanjeStream [uid=%.8s] [q=%s]", user["user_id"], qh)
    asyncio.create_task(_audit(user["user_id"], "pitanje_stream", qh))
    _stream_firma_ns = await _get_firma_namespace(user["user_id"])
    _stream_extra_ns = [_stream_firma_ns] if _stream_firma_ns else None

    # Atomično oduzmi kredit PRE agent poziva (isti timing kao stari require_credits
    # pre-deduction) — refunduje se ispod ako je odgovor iz keša ili blokiran.
    _stream_preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "ai_pravna_pitanja")

    async def _event_generator():
        # Commit 4/T1: Guard-complete pipeline — all Commits (1+2+3) run inside ask_agent
        # before the first byte is sent to the client. Old direct-LLM path removed.
        t0 = _time.monotonic()
        try:
            history_obj = [{"q": h.q, "a": h.a} for h in req.history] if req.history else None

            _stream_mem_ctx = await _fetch_firm_memory_context(user["user_id"], pitanje=req.pitanje)
            rezultat = await pokreni(ask_agent, req.pitanje, history_obj, _stream_extra_ns, _stream_mem_ctx)
            latency_ms = int((_time.monotonic() - t0) * 1000)

            if rezultat.get("status") == "success":
                data_text = rezultat.get("data", "")
            else:
                data_text = rezultat.get(
                    "message", "Došlo je do greške. Pokušajte ponovo."
                )

            tip = await asyncio.to_thread(klasifikuj_pitanje, _skini_pii(req.pitanje))
            _al.log_response(
                endpoint="/api/pitanje/stream",
                query_hash=qh,
                tip=tip,
                confidence=rezultat.get("confidence"),
                top_score=rezultat.get("top_score"),
                top_article=rezultat.get("top_article"),
                top_law=rezultat.get("top_law"),
                response_text=data_text,
                latency_ms=latency_ms,
            )

            # Stream the guard-verified response in 80-char chunks
            _CHUNK = 80
            for i in range(0, len(data_text), _CHUNK):
                chunk = data_text[i:i + _CHUNK]
                yield f"data: {chunk.replace(chr(10), chr(92) + 'n')}\n\n"

            # UsageService.consume() already pre-deducted the credit above (same timing as
            # the old require_credits pre-deduction) — refund on cache-hit/blocked, exactly
            # as before.
            preostalo = _stream_preostalo
            if rezultat.get("from_cache", False) or rezultat.get("blocked", False):
                await UsageService.refund(user["user_id"], user.get("email", ""), "ai_pravna_pitanja")
                preostalo = preostalo + 1

            yield "data: [DONE]\n\n"
            yield f"data: [CREDITS:{max(preostalo, 0)}]\n\n"

        except Exception:
            logger.exception("Greška u /api/pitanje/stream [q=%s]", qh)
            yield "data: Došlo je do greške. Pokušajte ponovo.\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Global Search ─────────────────────────────────────────────────────────────


@app.get("/api/search")
@limiter.limit("30/minute")
async def global_search(
    request: Request,
    q: str = "",
    limit: int = 10,
    user: dict = Depends(get_current_user),
):
    """
    Pretražuje klijente, predmete, beleške i komentare jednim upitom.
    Vraća rangirane rezultate po tipu entiteta.
    """
    q = (q or "").strip()
    if not q or len(q) < 2:
        raise HTTPException(status_code=400, detail="Upit mora imati najmanje 2 karaktera.")
    limit = min(max(limit, 1), 50)
    uid = user["user_id"]
    supa = _get_supa()
    results = []

    # Sanitize q for PostgREST .or_() interpolation — comma/dot break filter syntax
    import re as _re
    q_safe = _re.sub(r'[,.()\[\]{}\\\'"%]', ' ', q).strip()
    if not q_safe:
        q_safe = "zzz_no_match"  # prevent empty pattern returning all rows

    # ── Klijenti ──────────────────────────────────────────────────────────────
    try:
        rows = (
            supa.table("klijenti")
            .select("id, ime, prezime, firma, email, tip, status")
            .eq("user_id", uid)
            .is_("deleted_at", "null")
            .or_(
                f"ime.ilike.%{q_safe}%,"
                f"prezime.ilike.%{q_safe}%,"
                f"firma.ilike.%{q_safe}%,"
                f"email.ilike.%{q_safe}%"
            )
            .limit(limit)
            .execute()
        )
        for r in (rows.data or []):
            naziv = (
                f"{r.get('ime','')} {r.get('prezime','')}".strip()
                or r.get("firma", "")
            )
            results.append({
                "tip": "klijent",
                "id": r["id"],
                "naziv": naziv,
                "meta": r.get("status", ""),
                "url": f"/klijenti/{r['id']}",
            })
    except Exception as e:
        logger.warning("[SEARCH] klijenti greška: %s", e)

    # ── Predmeti ──────────────────────────────────────────────────────────────
    try:
        rows = (
            supa.table("predmeti")
            .select("id, naziv, opis, tip, status")
            .eq("user_id", uid)
            .or_(f"naziv.ilike.%{q_safe}%,opis.ilike.%{q_safe}%")
            .limit(limit)
            .execute()
        )
        for r in (rows.data or []):
            results.append({
                "tip": "predmet",
                "id": r["id"],
                "naziv": r.get("naziv", ""),
                "meta": r.get("status", ""),
                "url": f"/predmeti/{r['id']}",
            })
    except Exception as e:
        logger.warning("[SEARCH] predmeti greška: %s", e)

    # ── Beleške ───────────────────────────────────────────────────────────────
    try:
        rows = (
            supa.table("predmet_beleske")
            .select("id, sadrzaj, predmet_id, created_at")
            .eq("user_id", uid)
            .ilike("sadrzaj", f"%{q_safe}%")
            .limit(limit)
            .execute()
        )
        for r in (rows.data or []):
            snippet = (r.get("sadrzaj") or "")[:120]
            results.append({
                "tip": "beleska",
                "id": r["id"],
                "naziv": snippet,
                "meta": r.get("predmet_id", ""),
                "url": f"/predmeti/{r.get('predmet_id', '')}",
            })
    except Exception as e:
        logger.warning("[SEARCH] beleske greška: %s", e)

    # ── Komentari ─────────────────────────────────────────────────────────────
    try:
        rows = (
            supa.table("predmet_komentari")
            .select("id, tekst, predmet_id, created_at")
            .eq("user_id", uid)
            .ilike("tekst", f"%{q_safe}%")
            .limit(limit)
            .execute()
        )
        for r in (rows.data or []):
            snippet = (r.get("tekst") or "")[:120]
            results.append({
                "tip": "komentar",
                "id": r["id"],
                "naziv": snippet,
                "meta": r.get("predmet_id", ""),
                "url": f"/predmeti/{r.get('predmet_id', '')}",
            })
    except Exception as e:
        logger.warning("[SEARCH] komentari greška: %s", e)

    return {
        "q": q,
        "ukupno": len(results),
        "rezultati": results[:limit],
    }


# ── F5: CASE MANAGEMENT ───────────────────────────────────────────────────────


def _require_auth(authorization: Optional[str]) -> object:
    """Extract user from Bearer token. Full 3-step verification: SDK → HS256 → ES256."""
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

    return _AuthUser()


@app.post("/api/predmeti")
@limiter.limit("30/minute")
async def kreiraj_predmet(request: Request, authorization: str = Header(None)):
    user = _require_auth(authorization)
    body = await request.json()
    naziv = (body.get("naziv") or "").strip()
    if not naziv:
        raise HTTPException(status_code=400, detail="naziv je obavezan")
    row = _get_supa().table("predmeti").insert({
        "user_id": user.id,
        "naziv":   naziv,
        "opis":    body.get("opis", ""),
        "tip":     body.get("tip", "opsti"),
        "status":  "aktivan",
    }).execute()
    return {"predmet": row.data[0]}


@app.get("/api/predmeti")
@limiter.limit("60/minute")
async def lista_predmeta(request: Request, authorization: str = Header(None)):
    user = _require_auth(authorization)
    rows = _get_supa().table("predmeti").select("*").eq("user_id", user.id).order("created_at", desc=True).execute()
    return {"predmeti": rows.data}


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

    hron_r, risk_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmet_hronologija")
                .select("predmet_id,datum_iso,dogadjaj,vaznost")
                .in_("predmet_id", pred_ids)
                .gte("datum_iso", today_iso)
                .order("datum_iso")
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_istorija")
                .select("predmet_id,odgovor,created_at")
                .in_("predmet_id", pred_ids)
                .like("pitanje", "[Rizik]%")
                .order("created_at", desc=True)
                .execute()
        ),
    )

    import json as _jd
    hron_map: dict = {}
    for h in (hron_r.data or []):
        hron_map.setdefault(h["predmet_id"], []).append(h)

    risk_map: dict = {}
    for r in (risk_r.data or []):
        pid = r["predmet_id"]
        if pid not in risk_map:
            try:
                risk_map[pid] = _jd.loads(r.get("odgovor", "{}"))
            except Exception:
                pass

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

        score = (
            len(urgentni) * 3
            + _RISK_SCORE.get(nivo, 0) * 2
            + max(0, 30 - days_to_next)
        )
        enriched.append({
            **p,
            "urgentni_rokovi_count": len(urgentni),
            "sledeci_rok":           sledeci,
            "rizik_nivo":            nivo,
            "priority_score":        score,
        })

    po_prioritetu = sorted(enriched, key=lambda x: x["priority_score"], reverse=True)
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
    user = _require_auth(authorization)
    supa = _get_supa()
    row = supa.table("predmeti").select("*").eq("id", predmet_id).eq("user_id", user.id).single().execute()
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
    klijenti_linked = []
    if predmet_klijenti.data:
        klijent_ids = [r["klijent_id"] for r in predmet_klijenti.data]
        try:
            kl_rows = await asyncio.to_thread(
                lambda: supa.table("klijenti")
                    .select("id, ime, prezime, firma, tip, status")
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
    user = _require_auth(authorization)
    body = await request.json()
    allowed = {k: v for k, v in body.items() if k in {
        "naziv", "opis", "tip", "status",
        "tuzilac", "tuzeni", "oblast", "rizik", "vrednost_spora",
    }}
    if not allowed:
        raise HTTPException(status_code=400, detail="Nema validnih polja za update")
    _get_supa().table("predmeti").update(allowed).eq("id", predmet_id).eq("user_id", user.id).execute()
    return {"ok": True}


@app.patch("/api/predmeti/{predmet_id}/kanban-faza")
@limiter.limit("30/minute")
async def update_kanban_faza(predmet_id: str, request: Request, authorization: str = Header(None)):
    """Kanban Case Pipeline — premesti predmet u drugu fazu."""
    user = _require_auth(authorization)
    body = await request.json()
    faza = (body.get("kanban_faza") or "").strip()
    _VALID = {"inicijalna_procena", "priprema", "aktivan_postupak", "ceka_odluku", "zavrsen"}
    if faza not in _VALID:
        raise HTTPException(status_code=400, detail="Nevalidna faza")
    result = _get_supa().table("predmeti").update({"kanban_faza": faza}).eq("id", predmet_id).eq("user_id", user.id).execute()
    if not (result.data):
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")
    return {"ok": True, "kanban_faza": faza}


@app.post("/api/predmeti/{predmet_id}/beleske")
@limiter.limit("30/minute")
async def dodaj_belesku(predmet_id: str, request: Request, authorization: str = Header(None)):
    user = _require_auth(authorization)
    body = await request.json()
    sadrzaj = (body.get("sadrzaj") or "").strip()
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
    user = _require_auth(authorization)
    _get_supa().table("predmet_beleske").delete().eq("id", beleska_id).eq("user_id", user.id).execute()
    return {"ok": True}


@app.post("/api/predmeti/{predmet_id}/istorija")
@limiter.limit("30/minute")
async def sacuvaj_istoriju(predmet_id: str, request: Request, authorization: str = Header(None)):
    user = _require_auth(authorization)
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
    user = _require_auth(authorization)
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
        resp = client.chat.completions.create(
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
    except Exception:
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
    if predmet_id and procena_tekst:
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
}
_ALLOWED_SUFFIXES = {".pdf", ".docx", ".doc"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

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
    from uploaded_doc.extractor import extract
    from uploaded_doc.ingest import ingest_session
    from uploaded_doc.session import generate_session_id, expires_at_iso

    user = _require_auth(authorization)
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

    # File guards
    suffix = _Path(file.filename or "").suffix.lower()
    if file.content_type not in _ALLOWED_MIMES or suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Podržani formati: PDF, DOCX")
    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Fajl je preko 10MB")

    # Extract text
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw)
            tmp_path = _Path(tmp.name)
        text, is_scanned, ocr_used = await asyncio.to_thread(extract, tmp_path)
        if is_scanned:
            raise HTTPException(
                status_code=422,
                detail="Skenirani PDF — tekst nije čitljiv ni optičkim prepoznavanjem (OCR). Probajte digitalni PDF ili DOCX."
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
    source_meta = {
        "source_filename": file.filename,
        "source_format": suffix.lstrip("."),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "is_scanned": ocr_used,
        "session_id": "__local__",
    }
    manifest = await asyncio.to_thread(chunk_document, text, source_meta)
    if manifest.total_chunks == 0:
        raise HTTPException(status_code=422, detail="Dokument je prazan.")

    session_id = generate_session_id()
    # Predmet dokumenti su trajni — koristimo 'pred_' prefix da cleanup_expired
    # (koji brise samo 'tmp_*') nikad ne obrise ove vektore iz Pinecone-a.
    _pinecone_ok = True
    try:
        count = await asyncio.to_thread(
            ingest_session, manifest, session_id,
            namespace_prefix="pred_"
        )
    except Exception as _pe:
        _pe_str = str(_pe)
        if "429" in _pe_str or "storage" in _pe_str.lower() or "Too Many" in _pe_str:
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
            "storage_path":        f"session/{session_id}",
            "pinecone_namespace":  f"pred_{session_id}",
            "status":              "indeksirano" if _pinecone_ok else "sacuvano",
            "velicina_kb":         max(1, len(raw) // 1024),
            "redni_broj":          _next_rn,
        }
        # Sačuvaj tekst ako kolona postoji (migration: ALTER TABLE predmet_dokumenti ADD COLUMN tekst_sadrzaj TEXT)
        try:
            _ins = _get_supa().table("predmet_dokumenti").insert({**_row, "tekst_sadrzaj": _tekst_preview}).execute()
        except Exception:
            _ins = _get_supa().table("predmet_dokumenti").insert(_row).execute()
        _dok_id = (_ins.data or [{}])[0].get("id")
    except Exception:
        logger.warning("[P1.1] predmet_dokumenti insert failed for predmet=%s", predmet_id)

    # Auto-classify document in background (Evidence Vault)
    if _dok_id:
        try:
            from routers.evidence import klasifikuj_i_sacuvaj
            asyncio.create_task(asyncio.to_thread(
                klasifikuj_i_sacuvaj, predmet_id, _dok_id,
                file.filename or "dokument", text[:2000], user.id
            ))
        except Exception as _ce:
            logger.warning("[EVIDENCE] Auto-classify task greška: %s", _ce)

    # Auto-refresh Case Genome u pozadini posle svakog novog dokumenta
    if _dok_id and predmet_id:
        async def _genome_bg():
            await asyncio.sleep(3)  # sacekaj da klasifikacija upisice tip_dokaza
            try:
                from routers.case_dna import _run_genome_background
                _stari_g = _get_supa().table("predmeti").select("case_dna") \
                    .eq("id", predmet_id).eq("user_id", str(user.id)).execute()
                _sg = ((_stari_g.data or [{}])[0].get("case_dna") or {})
                _sp = _sg.get("snaga_predmeta_procent") if isinstance(_sg, dict) else None
                await _run_genome_background(predmet_id, str(user.id), _sp)
            except Exception as _ge:
                logger.warning("[GENOME] Auto-refresh bg greška: %s", _ge)
        asyncio.create_task(_genome_bg())

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
        _rag_docs, _rag_meta = await asyncio.wait_for(
            asyncio.to_thread(_retrieve, _rag_query, 3),
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

    def _call_procena():
        return _oai_client.chat.completions.create(
            model="gpt-4o", temperature=0, max_tokens=max_tok, timeout=60.0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": cinjenice_text},
            ],
        )

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

    def _call_metapodaci():
        return _oai_client.chat.completions.create(
            model="gpt-4o-mini", temperature=0, max_tokens=600, timeout=25.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _META_SYSTEM},
                {"role": "user",   "content": f"Dokument: {file.filename or 'dokument'}\n\n{text[:4000]}"},
            ],
        )

    _pr, _hr, _meta = await asyncio.gather(
        asyncio.to_thread(_call_procena),
        asyncio.to_thread(_call_hronologija),
        asyncio.to_thread(_call_metapodaci),
        return_exceptions=True,
    )

    # Jedan consume() poziv za celokupnu upload-triggered AI analizu (3 paralelna
    # potpoziva iznad broje se kao JEDNA upotreba ove funkcije, ne tri).
    await UsageService.consume(_entitlement_user["user_id"], _entitlement_user["email"], "predmet_upload_ai")

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
                    datum_iso = ev.get("datum_iso") or None
                    if datum_iso and (len(str(datum_iso)) < 4 or str(datum_iso).lower() in ("null", "none", "")):
                        datum_iso = None
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
                    _get_supa().table("predmet_hronologija").insert(rows).execute()
                    hron_count = len(rows)
                    logger.info("[P2.2] Hronologija: %d događaja sačuvano za predmet=%s", hron_count, predmet_id)
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
    user = _require_auth(authorization)
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
        resp = await oai.chat.completions.create(
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
    (beleske_r, istorija_r, dokumenti_r, hronologija_r, komentari_r, pk_r, rocista_ws_r) = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_beleske").select("*").eq("predmet_id", predmet_id).order("created_at", desc=True).limit(50).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija").select("pitanje,odgovor,confidence,created_at").eq("predmet_id", predmet_id).order("created_at", desc=True).limit(30).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select("id,naziv_fajla,status,velicina_kb,created_at,pinecone_namespace,redni_broj").eq("predmet_id", predmet_id).order("redni_broj").execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija").select("*").eq("predmet_id", predmet_id).order("datum_iso", desc=False).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_komentari").select("*").eq("predmet_id", predmet_id).order("kreirano", desc=True).limit(50).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_klijenti").select("klijent_id,uloga_klijenta,napomena").eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("rocista").select("id").eq("predmet_id", predmet_id).eq("user_id", uid).execute()),
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

    # Step 6: Parallel — praksa preview + cockpit AI
    import os as _os_ws, json as _json_ws
    from openai import AsyncOpenAI as _OAI_ws

    _COCKPIT_SYSTEM = (
        "Ti si pravni asistent. Na osnovu podataka predmeta vrati ISKLJUČIVO JSON bez teksta van JSON-a:\n"
        '{"ai_sazetak": str (maks 100 reči, konkretan opis stanja predmeta),\n'
        ' "sledeca_akcija": {"opis": str, "rok": str, "prioritet": "hitan|normalan|odlozen"},\n'
        ' "procena_rizika": {"nivo": "visok|srednji|nizak", "faktori_plus": [str], "faktori_minus": [str]}}\n'
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
                f"Rokovi: {' | '.join((h.get('dogadjaj','') or '')[:80] + ' (' + (h.get('datum_iso','') or '') + ')' for h in (hronologija_r.data or [])[:5]) or 'nema'}"
            )
            resp = await oai.chat.completions.create(
                model="gpt-4o-mini", temperature=0.1, max_tokens=700,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _COCKPIT_SYSTEM},
                    {"role": "user",   "content": ctx},
                ],
            )
            return _json_ws.loads(resp.choices[0].message.content or "{}")
        except Exception as _ce:
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

    # Step 6b: Risk history — compare today vs previous snapshot
    import json as _json_risk
    _rizik_info = cockpit_raw.get("procena_rizika", {}) if isinstance(cockpit_raw, dict) else {}
    _rizik_nivo = _rizik_info.get("nivo", "")
    if _rizik_nivo:
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
                        cockpit_raw.setdefault("procena_rizika", {})["promena"] = {
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
                            "faktori_plus":  _rizik_info.get("faktori_plus", []),
                            "faktori_minus": _rizik_info.get("faktori_minus", []),
                        }, ensure_ascii=False),
                        "confidence": "MEDIUM",
                    }).execute()
                ))
        except Exception as _re:
            logger.warning("[WORKSPACE-RISK-HISTORY] greška: %s", _re)

    # Step 7: Rokovi po hitnosti
    _VAZNOST_ORDER = {"kritičan": 0, "bitan": 1, "normalan": 2, "ostalo": 3}
    rokovi_po_hitnosti = sorted(
        hronologija_r.data or [],
        key=lambda h: (
            _VAZNOST_ORDER.get(h.get("vaznost", "ostalo"), 3),
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
        _crs, _checklist = _calc_crs(
            dokumenti=dokumenti_r.data or [],
            klijenti=_ws_klijenti,
            rokovi=hronologija_r.data or [],
            istorija=_ws_ist_full,
            rocista=_ws_rocista,
        )
    except Exception:
        _crs, _checklist = 0, []

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
            "sledeca_akcija":      cockpit_raw.get("sledeca_akcija", {}),
            "procena_rizika":      cockpit_raw.get("procena_rizika", {}),
            "poslednja_aktivnost": poslednja_aktivnost,
            "rizik_promena":       cockpit_raw.get("procena_rizika", {}).get("promena"),
        },
        "case_ready_score":   _crs,
        "checklist":          _checklist,
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

    for kl_id in (req.klijent_ids or [])[:5]:
        try:
            existing = await asyncio.to_thread(
                lambda _kid=kl_id: supa.table("predmet_klijenti")
                    .select("id")
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
                        "user_id":        uid,
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

@app.get("/api/notifications")
@limiter.limit("30/minute")
async def get_notifications(request: Request, user: dict = Depends(get_current_user)):
    """
    Computed notifications — bez novog DB table-a.
    Tipovi: rok_blizu (7 dana), rizik_promena, predmet_bez_klijenta.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    from datetime import date as _dtn, timedelta as _tdn, datetime as _dtn2
    today_n  = _dtn.today().isoformat()
    next7_n  = (_dtn.today() + _tdn(days=7)).isoformat()

    preds_r, hron_n, risk_n, pk_n = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id,naziv,status")
            .eq("user_id", uid)
            .neq("status","zatvoren")
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("predmet_id,dogadjaj,datum_iso,vaznost")
            .eq("user_id", uid)
            .gte("datum_iso", today_n)
            .lte("datum_iso", next7_n)
            .in_("vaznost", ["kritičan","bitan"])
            .order("datum_iso")
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("predmet_id,odgovor,created_at")
            .eq("user_id", uid)
            .like("pitanje","[Rizik]%")
            .order("created_at", desc=True)
            .limit(120)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_klijenti")
            .select("predmet_id")
            .execute()),
        return_exceptions=True,
    )

    pred_map  = {p["id"]: p["naziv"] for p in (preds_r.data or [])}
    has_kl    = set(r["predmet_id"] for r in (pk_n.data if not isinstance(pk_n, Exception) else []))
    notifs    = []

    # Type 1: upcoming rokovi
    for h in (hron_n.data if not isinstance(hron_n, Exception) else []):
        pid   = h.get("predmet_id","")
        naziv = pred_map.get(pid,"")
        if not naziv:
            continue
        days = None
        try:
            days = (_dtn2.strptime(h["datum_iso"],"%Y-%m-%d").date() - _dtn.today()).days
        except Exception:
            pass
        prio = "visoka" if (days is not None and days<=3) or h.get("vaznost")=="kritičan" else "srednja"
        notifs.append({
            "id":             f"rok_{pid}_{h['datum_iso']}",
            "tip":            "rok_blizu",
            "prioritet":      prio,
            "poruka":         f"{h.get('dogadjaj','Rok')}" + (f" — za {days} dana" if days is not None else ""),
            "predmet_id":     pid,
            "predmet_naziv":  naziv,
            "datum":          h.get("datum_iso",""),
        })

    # Type 2: risk changes
    import json as _jnn
    risk_by_pred: dict = {}
    for r in (risk_n.data if not isinstance(risk_n, Exception) else []):
        pid = r.get("predmet_id","")
        if pid in pred_map:
            risk_by_pred.setdefault(pid,[]).append(r)
    for pid, recs in risk_by_pred.items():
        if len(recs) < 2:
            continue
        try:
            lat = _jnn.loads(recs[0].get("odgovor","{}"))
            prv = _jnn.loads(recs[1].get("odgovor","{}"))
            if lat.get("nivo") and prv.get("nivo") and lat["nivo"] != prv["nivo"]:
                arr = "↑" if lat["nivo"]=="visok" else ("↓" if lat["nivo"]=="nizak" else "→")
                notifs.append({
                    "id":            f"rizik_{pid}",
                    "tip":           "rizik_promena",
                    "prioritet":     "visoka" if lat["nivo"]=="visok" else "srednja",
                    "poruka":        f"Rizik {arr} {prv['nivo']} → {lat['nivo']}",
                    "predmet_id":    pid,
                    "predmet_naziv": pred_map[pid],
                    "datum":         (recs[0].get("created_at","") or "")[:10],
                })
        except Exception:
            pass

    # Type 3: predmeti bez klijenta
    for pid, naziv in pred_map.items():
        if pid not in has_kl:
            notifs.append({
                "id":            f"bez_kl_{pid}",
                "tip":           "bez_klijenta",
                "prioritet":     "niska",
                "poruka":        "Predmet bez vezanog klijenta",
                "predmet_id":    pid,
                "predmet_naziv": naziv,
                "datum":         "",
            })

    notifs.sort(key=lambda n: ({"visoka":0,"srednja":1,"niska":2}.get(n["prioritet"],3), n.get("datum","")))
    return {"notifications": notifs[:25], "ukupno": len(notifs)}


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



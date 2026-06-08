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
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

BASE_DIR = Path(__file__).parent
load_dotenv()

import time as _time
from main import ask_agent, ask_nacrt, ask_analiza, _skini_pii, klasifikuj_pitanje
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

    # Korak 2b: ES256 sa hardkodovanim javnim ključem (JWKS offline)
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
            logger.warning("ES256 hardkod greška: %s", e)

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
BESPLATNI_KREDITI = 15
BASIC_MESECNI_KREDITI = 200
PRO_MESECNI_KREDITI   = 600

# In-memory mesečna upotreba: {user_id: {"month": "YYYY-MM", "count": N}}
# Resetuje se pri restartovanju servera (prihvatljivo za single-instance deployment)
_mesecna_upotreba: dict[str, dict] = {}


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
            # Row missing — auto-heal (trigger bi trebalo da ga kreira, ovo je safety net)
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


async def require_credits(user: dict = Depends(get_current_user)) -> dict:
    """Dependency koji proverava da korisnik ima kredite. Founder uvek prolazi."""
    email = user.get("email", "")
    logger.info("require_credits: email=%s is_founder=%s", email, _is_founder(email))
    if _is_founder(email):
        user["credits_remaining"] = 9999
        return user

    # Mese\u010dni limit (PRO: 600, Basic/Free: 200 \u2014 Free korisnici su stopiran ranije, na 15)
    is_pro_user = _is_pro(email)
    monthly_limit = PRO_MESECNI_KREDITI if is_pro_user else BASIC_MESECNI_KREDITI
    monthly_used  = _get_monthly_usage(user["user_id"])
    if monthly_used >= monthly_limit:
        if is_pro_user:
            msg = (f"Iskoristili ste {PRO_MESECNI_KREDITI} mese\u010dnih pitanja. "
                   "Kontaktirajte nas za Firm plan.")
        else:
            msg = (f"Iskoristili ste {BASIC_MESECNI_KREDITI} mese\u010dnih pitanja. "
                   "Pre\u0111ite na PRO za 600 pitanja mese\u010dno.")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={"code": "MONTHLY_LIMIT", "message": msg, "credits_remaining": 0},
        )

    credits = await asyncio.to_thread(_get_credits, user["user_id"])
    if credits <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "NO_CREDITS",
                "message": (
                    "Iskoristili ste besplatne upite. "
                    "Pre\u0111ite na Basic paket (19\u20ac) za neograni\u010den pristup."
                ),
                "credits_remaining": 0,
            },
        )
    user["credits_remaining"] = credits
    return user


# ─── App ──────────────────────────────────────────────────────────────────────
logger.info("=== STARTUP ENV CHECK ===")
logger.info("SUPABASE_URL    : %r", SUPABASE_URL)
logger.info("SERVICE_KEY set : %s", bool(SUPABASE_SERVICE_KEY))
logger.info("JWT_SECRET set  : %s", bool(SUPABASE_JWT_SECRET))
logger.info("FOUNDER_EMAILS  : %s", FOUNDER_EMAILS)
logger.info("PINECONE_API_KEY set : %s", bool(os.getenv("PINECONE_API_KEY", "")))
logger.info("PINECONE_HOST       : %r", os.getenv("PINECONE_HOST", ""))
logger.info("OPENAI_API_KEY set   : %s", bool(os.getenv("OPENAI_API_KEY", "")))

limiter = Limiter(key_func=get_remote_address, default_limits=["60/hour"])
app = FastAPI(title="Vindex AI", docs_url=None, redoc_url=None)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


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
    logger.exception("Neočekivana greška [path=%s]: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "type": type(exc).__name__,
            "status": "error",
        },
    )

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "https://vindex-ai.onrender.com").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Dodaje security i permissions headere na svaki odgovor."""
    response = await call_next(request)
    # Dozvoljava Web Speech API (mikrofon) na self i Render domenu
    response.headers["Permissions-Policy"] = (
        "microphone=(self \"https://vindex-ai.onrender.com\")"
    )
    # Feature-Policy za starije Chrome verzije
    response.headers["Feature-Policy"] = "microphone 'self'"
    # Sprečava clickjacking
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# ─── Modeli zahteva ───────────────────────────────────────────────────────────

class HistoryItem(BaseModel):
    q: str = Field("", max_length=500)
    a: str = Field("", max_length=1000)


class PitanjeReq(BaseModel):
    pitanje:    str = Field(..., min_length=3, max_length=2000)
    history:    List[HistoryItem] = Field(default_factory=list, max_length=3)
    predmet_id: Optional[str] = Field(None, max_length=64)

    @field_validator("pitanje")
    @classmethod
    def ocisti(cls, v: str) -> str:
        return v.strip()


class NacrtReq(BaseModel):
    vrsta: str = Field(..., min_length=2, max_length=200)
    opis: str = Field(..., min_length=10, max_length=5000)

    @field_validator("vrsta", "opis")
    @classmethod
    def ocisti(cls, v: str) -> str:
        return v.strip()


class AnalizaReq(BaseModel):
    tekst: str = Field(..., min_length=10, max_length=50000)  # raised: real contracts 8k-25k chars
    pitanje: str = Field("", max_length=1000)

    @field_validator("tekst", "pitanje")
    @classmethod
    def ocisti(cls, v: str) -> str:
        return v.strip()


class EmailCheckReq(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)


class FeedbackReq(BaseModel):
    pitanje: str = Field("", max_length=2000)
    odgovor: str = Field("", max_length=5000)
    tip: str = Field("greska", max_length=50)


class PodnesakReq(BaseModel):
    tip: str = Field(..., max_length=50)
    opis: str = Field(..., min_length=20, max_length=5000)

    @field_validator("tip")
    @classmethod
    def validiraj_tip(cls, v: str) -> str:
        dozvoljeni = {"tuzba_naknada_stete", "zalba_parnicna", "predlog_izvrsenje"}
        if v not in dozvoljeni:
            raise ValueError(f"Tip podneska mora biti jedan od: {dozvoljeni}")
        return v

    @field_validator("opis")
    @classmethod
    def ocisti_opis(cls, v: str) -> str:
        return v.strip()


class SazmiReq(BaseModel):
    odgovor: str = Field(..., max_length=6000)


# ─── Helperi ──────────────────────────────────────────────────────────────────

async def pokreni(fn, *args):
    """Pokreće sinhronu funkciju u thread poolu."""
    return await asyncio.to_thread(fn, *args)


def normalizuj_rezultat(rezultat: dict, credits_remaining: Optional[int] = None) -> dict:
    resp: dict = {}
    if not isinstance(rezultat, dict):
        resp["odgovor"] = str(rezultat)
    elif rezultat.get("status") == "success":
        resp["odgovor"] = rezultat.get("data", "")
    else:
        resp["odgovor"] = rezultat.get(
            "message",
            "Došlo je do greške prilikom obrade zahteva. Pokušajte ponovo.",
        )
    if credits_remaining is not None:
        resp["credits_remaining"] = credits_remaining
    return resp


def greska_odgovor(status_code: int, poruka: str) -> JSONResponse:
    logger.warning("API greška %d: %s", status_code, poruka)
    return JSONResponse(status_code=status_code, content={"greska": poruka})


# ─── Rute ─────────────────────────────────────────────────────────────────────

@app.get("/")
@app.head("/")
def root():
    path = BASE_DIR / "landing.html"
    if path.exists():
        return FileResponse(path)
    return {"status": "ok", "servis": "Vindex AI"}


@app.get("/health")
@app.head("/health")
def health():
    return {"status": "ok"}


@app.get("/test-pinecone")
async def test_pinecone():
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
async def test_zdi_indeksiranost():
    """
    Proverava da li su ključni članovi ZDI (2, 74, 75, 78) indeksirani u Pinecone.
    Vraća status svakog člana: pronađen/nije pronađen.
    """
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
async def diagnose():
    """Testira konekciju sa Pinecone i OpenAI — sve u thread-u da ne blokira event loop."""

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


@app.get("/app")
def serve_html():
    path = BASE_DIR / "index.html"
    if not path.exists():
        return greska_odgovor(404, "Frontend nije pronađen.")
    return FileResponse(path)


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
                detail=f"Registracija nije uspela: {err_str[:200]}",
            )

    try:
        return await asyncio.to_thread(_do_register)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Neočekivana greška u /api/register")
        raise HTTPException(status_code=500, detail="Greška servera. Pokušajte ponovo.")


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


@app.post("/api/pitanje")
@limiter.limit("10/minute")
async def pitanje(req: PitanjeReq, request: Request, user: dict = Depends(require_credits)):
    """Pravno istraživanje — pretražuje bazu zakona."""
    qh = _q_hash(req.pitanje)
    logger.info("Pitanje [uid=%.8s] [q=%s]", user["user_id"], qh)
    asyncio.create_task(_audit(user["user_id"], "pitanje", qh))
    predmet_id = (req.predmet_id or "").strip() or None
    try:
        history = [{"q": h.q, "a": h.a} for h in req.history] if req.history else None

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
        t0 = _time.monotonic()
        rezultat = await pokreni(ask_agent, pitanje_za_agenta, history)
        latency_ms = int((_time.monotonic() - t0) * 1000)
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
        should_deduct = (
            rezultat.get("status") == "success"
            and not rezultat.get("blocked", False)
            and not rezultat.get("from_cache", False)
        )
        if should_deduct:
            preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        else:
            preostalo = await asyncio.to_thread(_get_credits, user["user_id"])

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

        return normalizuj_rezultat(rezultat, credits_remaining=max(preostalo, 0))
    except Exception:
        logger.exception("Greška u /api/pitanje [q=%s]", qh)
        return greska_odgovor(
            500,
            "Došlo je do greške na serveru. Pokušajte ponovo za nekoliko sekundi.",
        )


@app.post("/api/pitanje/stream")
@limiter.limit("10/minute")
async def pitanje_stream(req: PitanjeReq, request: Request, user: dict = Depends(require_credits)):
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

    async def _event_generator():
        # Commit 4/T1: Guard-complete pipeline — all Commits (1+2+3) run inside ask_agent
        # before the first byte is sent to the client. Old direct-LLM path removed.
        t0 = _time.monotonic()
        try:
            history_obj = [{"q": h.q, "a": h.a} for h in req.history] if req.history else None

            rezultat = await pokreni(ask_agent, req.pitanje, history_obj)
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

            # Conditional deduction — same logic as /api/pitanje
            _should_deduct = (
                rezultat.get("status") == "success"
                and not rezultat.get("blocked", False)
                and not rezultat.get("from_cache", False)
            )
            if _should_deduct:
                preostalo = await asyncio.to_thread(
                    _deduct_credit, user["user_id"], user.get("email", "")
                )
            else:
                preostalo = await asyncio.to_thread(_get_credits, user["user_id"])

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


@app.get("/api/nacrt/types")
async def nacrt_types():
    """Vraća listu dostupnih tipova nacrta (bez autentifikacije)."""
    return {"tipovi": _drafting_get_types()}


# ─── /api/playbook ────────────────────────────────────────────────────────────

_MAX_PLAYBOOK_BYTES = 2 * 1024 * 1024  # 2 MB


@app.post("/api/playbook/upload")
@limiter.limit("10/minute")
async def playbook_upload(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(require_pro),
):
    """P4.4 — Upload firm playbook (TXT or DOCX). Ne troši kredit."""
    from pathlib import Path as _Path
    import tempfile
    from uploaded_doc.extractor import extract_docx, extract_txt

    suffix = _Path(file.filename or "").suffix.lower()
    if suffix not in {".txt", ".docx"}:
        raise HTTPException(status_code=415, detail="Podržani formati: TXT, DOCX")

    raw = await file.read()
    if len(raw) > _MAX_PLAYBOOK_BYTES:
        raise HTTPException(status_code=413, detail="Fajl je preko 2MB")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw)
            tmp_path = _Path(tmp.name)

        if suffix == ".docx":
            tekst, _ = await asyncio.to_thread(extract_docx, tmp_path)
        else:
            tekst, _ = await asyncio.to_thread(extract_txt, tmp_path)

        if not tekst or not tekst.strip():
            raise HTTPException(status_code=422, detail="Fajl je prazan ili nečitljiv")

        from drafting.playbook import ingest_playbook
        count = await asyncio.to_thread(ingest_playbook, user["user_id"], file.filename or "", tekst)
        return {"filename": file.filename, "chunks_ingested": count}
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


@app.delete("/api/playbook")
@limiter.limit("10/minute")
async def playbook_delete(request: Request, user: dict = Depends(require_pro)):
    """P4.4 — Briše ceo playbook korisnika iz Pinecone."""
    from drafting.playbook import delete_playbook
    deleted = await asyncio.to_thread(delete_playbook, user["user_id"])
    return {"deleted_chunks": deleted}


@app.get("/api/playbook/status")
@limiter.limit("30/minute")
async def playbook_status(request: Request, user: dict = Depends(require_pro)):
    """P4.4 — Vraća status playbook-a: da li postoji i koliko chunks ima."""
    def _check():
        try:
            from uploaded_doc.ingest import _get_pinecone_index
            index = _get_pinecone_index()
            ns = f"playbook_{user['user_id']}"
            stats = index.describe_index_stats()
            ns_data = stats.namespaces.get(ns) if hasattr(stats, "namespaces") else None
            count = (ns_data.vector_count if hasattr(ns_data, "vector_count") else 0) if ns_data else 0
            return {"has_playbook": count > 0, "chunk_count": count}
        except Exception:
            return {"has_playbook": False, "chunk_count": 0}
    return await asyncio.to_thread(_check)


@app.post("/api/nacrt")
@limiter.limit("10/minute")
async def nacrt(req: NacrtReq, request: Request, user: dict = Depends(require_pro)):
    """Generisanje nacrta pravnog dokumenta (strukturirani šablon)."""
    logger.info("Nacrt [uid=%.8s] vrsta=%s", user["user_id"], req.vrsta)
    asyncio.create_task(_audit(user["user_id"], f"nacrt:{req.vrsta}", ""))
    try:
        qh_nacrt = _q_hash(_skini_pii(req.opis))
        t0 = _time.monotonic()
        rezultat = await pokreni(_drafting_generate, req.vrsta, _skini_pii(req.opis), user["user_id"])
        latency_ms = int((_time.monotonic() - t0) * 1000)
        _al.log_response(
            endpoint="/api/nacrt",
            query_hash=qh_nacrt,
            tip=req.vrsta[:20],
            response_text=rezultat.get("data", ""),
            latency_ms=latency_ms,
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return normalizuj_rezultat(rezultat, credits_remaining=max(preostalo, 0))
    except Exception:
        logger.exception("Greška u /api/nacrt")
        return greska_odgovor(
            500,
            "Došlo je do greške na serveru. Pokušajte ponovo za nekoliko sekundi.",
        )


@app.post("/api/analiza")
@limiter.limit("10/minute")
async def analiza(req: AnalizaReq, request: Request, user: dict = Depends(require_credits)):
    """Analiza pravnog dokumenta."""
    qh = _q_hash(req.pitanje)
    logger.info("Analiza [uid=%.8s] [q=%s]", user["user_id"], qh)
    asyncio.create_task(_audit(user["user_id"], "analiza", qh))
    try:
        qh_analiza = _q_hash(_skini_pii(req.pitanje or req.tekst[:200]))
        t0 = _time.monotonic()
        rezultat = await pokreni(ask_analiza, req.tekst, req.pitanje)
        latency_ms = int((_time.monotonic() - t0) * 1000)
        _al.log_response(
            endpoint="/api/analiza",
            query_hash=qh_analiza,
            response_text=rezultat.get("data", ""),
            latency_ms=latency_ms,
        )
        # Don't deduct when analysis was blocked by the hallucination guard
        is_blocked = (rezultat.get("data") or "").startswith("[!] ANALIZA BLOKIRANA")
        should_deduct = rezultat.get("status") == "success" and not is_blocked
        if should_deduct:
            preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        else:
            preostalo = await asyncio.to_thread(_get_credits, user["user_id"])
        return normalizuj_rezultat(rezultat, credits_remaining=max(preostalo, 0))
    except Exception:
        logger.exception("Neočekivana greška u /api/analiza")
        return greska_odgovor(
            500,
            "Došlo je do greške na serveru. Pokušajte ponovo za nekoliko sekundi.",
        )


# ─── Feedback endpoint ────────────────────────────────────────────────────────

@app.post("/api/sazmi")
@limiter.limit("10/minute")
async def sazmi(req: SazmiReq, request: Request, user: dict = Depends(require_credits)):
    """Generiše verziju odgovora na 'ljudskom' jeziku za klijenta (Viber/Mejl)."""
    from openai import OpenAI as _OAI
    try:
        klijent_prompt = (
            "Advokat ti šalje pravni odgovor koji treba da prepišeš za klijenta — laika koji ne zna pravo.\n"
            "PRAVILA TONA: Profesionalan, smiren, poverljiv. BEZ: latinštine, paragrafa, citata, 'čl.', 'Sl. glasnik', 'lex specialis'.\n"
            "STRUKTURA (4–6 rečenica):\n"
            "  1. Šta znači situacija za klijenta u jednoj jasnoj rečenici.\n"
            "  2. Šta je klijentov ključni dokaz ili korak — konkretan, bez teorije.\n"
            "  3. Koji je rizik ako ne preduzme ništa (rok, zastarelost, gubitak prava).\n"
            "  4. Šta je sledeći korak koji klijent treba da uradi — imperativ, ne upit.\n"
            "  5. Kratka napomena: 'Pre preduzimanja koraka, konsultujte svog advokata za konačno mišljenje.'\n"
            "Počni direktno prvom rečenicom. Bez uvoda, bez 'Evo sažetka', bez zaglavlja."
        )
        from main import _skini_pii as _pii
        client = _OAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=300,
            messages=[
                {"role": "system", "content": klijent_prompt},
                {"role": "user", "content": _pii(req.odgovor[:4000])},
            ],
        )
        tekst = resp.choices[0].message.content.strip()
        await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"status": "ok", "sazetak": tekst}
    except Exception:
        logger.exception("Greška u /api/sazmi")
        return greska_odgovor(500, "Greška pri generisanju sažetka.")



@app.post("/api/feedback")
async def feedback(req: FeedbackReq, user: dict = Depends(get_current_user)):
    """
    Korisnik prijavljuje netačan ili nepotpun odgovor.
    NO-STORAGE POLICY (Basic API tier): čuvamo samo hash pitanja i tip — bez sadržaja.
    ZZPL čl. 5(1)(c) — minimizacija podataka.
    """
    try:
        qh = _q_hash(req.pitanje)
        await asyncio.to_thread(
            lambda: _get_supa().table("feedback").insert({
                "user_id": user["user_id"],
                "q_hash":  qh,
                "tip":     req.tip,
                # pitanje i odgovor se NE čuvaju — samo hash za deduplication
            }).execute()
        )
        logger.info("Feedback [uid=%.8s] tip=%s [q=%s]", user["user_id"], req.tip, qh)
        return {"status": "ok"}
    except Exception:
        logger.exception("Greška u /api/feedback")
        return {"status": "ok"}


# ─── PRO: Modul podnesaka ─────────────────────────────────────────────────────

@app.post("/api/podnesak")
@limiter.limit("5/minute")
async def podnesak(req: PodnesakReq, request: Request, user: dict = Depends(require_pro)):
    """
    Generiše nacrt sudskog podneska u dva koraka:
    1. Ekstrakcija entiteta iz slobodnog opisa (GPT-4o-mini, brzo)
    2. RAG + popunjavanje šablona (GPT-4o, precizno)
    """
    from openai import OpenAI as _OAI
    import json

    log_id = _q_hash(req.opis)
    logger.info("Podnesak [uid=%.8s] tip=%s [q=%s]", user["user_id"], req.tip, log_id)

    oai = _OAI(api_key=os.getenv("OPENAI_API_KEY"))
    opis_api = _skini_pii(req.opis)  # PII filter pre slanja na OpenAI

    # ── KORAK 1: Ekstrakcija entiteta (GPT-4o-mini, ~1s) ──────────────────────
    ekstr_prompt = EKSTRAKCIONI_PROMPTOVI[req.tip]

    def _parse_json_safe(raw: str) -> dict:
        """Pokušava da parsira JSON; ako ne uspe, traži prvi {...} blok."""
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            import re as _re
            m = _re.search(r'\{[\s\S]+\}', raw)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    pass
        return {}

    try:
        ekstr_resp = await asyncio.to_thread(
            lambda: oai.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                max_tokens=900,
                messages=[
                    {"role": "system", "content": ekstr_prompt},
                    {"role": "user",   "content": f"OPIS SLUČAJA:\n{opis_api}"},
                ],
            )
        )
        raw_json = (ekstr_resp.choices[0].message.content or "").strip()
        entiteti: dict = _parse_json_safe(raw_json)
        if not entiteti:
            logger.warning("Ekstrakcija vratila prazan JSON [q=%s] — retry sa gpt-4o", log_id)
            ekstr_resp2 = await asyncio.to_thread(
                lambda: oai.chat.completions.create(
                    model="gpt-4o",
                    temperature=0,
                    max_tokens=900,
                    messages=[
                        {"role": "system", "content": ekstr_prompt},
                        {"role": "user",   "content": f"OPIS SLUČAJA:\n{opis_api}\n\nVrati ISKLJUČIVO validan JSON objekat, bez ikakvog drugog teksta."},
                    ],
                )
            )
            entiteti = _parse_json_safe(ekstr_resp2.choices[0].message.content or "")
    except Exception as exc:
        logger.warning("Ekstrakcija entiteta neuspešna [q=%s]: %s", log_id, exc)
        entiteti = {}

    # ── KORAK 2: RAG — dohvati relevantne odredbe zakona ──────────────────────
    rag_upit = f"{PODNESAK_TIPOVI[req.tip]}: {opis_api[:400]}"
    try:
        from app.services.retrieve import retrieve_documents
        docs = await asyncio.to_thread(retrieve_documents, rag_upit, 5)
        kontekst = "\n\n".join(docs[:4]) if docs else ""
    except Exception as exc:
        logger.warning("RAG neuspešan za podnesak [q=%s]: %s", log_id, exc)
        kontekst = ""

    # ── KORAK 2b: VKS orijentacioni kriterijumi (samo za tužbu naknade štete) ─
    vks_analiza = ""
    vks_kontekst_blok = ""
    if req.tip == "tuzba_naknada_stete":
        try:
            vks = vks_preporuci(entiteti)
            vks_kontekst_blok = f"\n\nVKS ORIJENTACIONI KRITERIJUMI:\n{vks['kontekst_tekst']}"
            vks_analiza = vks["analiza_tekst"]
        except Exception as exc:
            logger.warning("VKS preporuka neuspešna [q=%s]: %s", log_id, exc)

    # ── KORAK 3: Obogaćivanje šablona (GPT-4o) ────────────────────────────────
    obog_prompt = OBOGACIVANJE_PROMPTOVI[req.tip]
    obog_user = (
        f"EKSTRAKTOVANI PODACI (JSON):\n{json.dumps(entiteti, ensure_ascii=False)}"
        f"{vks_kontekst_blok}\n\n"
        f"ZAKONSKI KONTEKST (RAG):\n{kontekst or 'Nije pronađen relevantan kontekst.'}"
    )
    try:
        obog_resp = await asyncio.to_thread(
            lambda: oai.chat.completions.create(
                model="gpt-4o",
                temperature=0,
                max_tokens=2500,
                messages=[
                    {"role": "system", "content": obog_prompt},
                    {"role": "user",   "content": obog_user},
                ],
            )
        )
        raw_obog = (obog_resp.choices[0].message.content or "").strip()
        raw_obog = raw_obog.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        obogacivanje: dict = json.loads(raw_obog)
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Obogaćivanje neuspešno [q=%s]: %s", log_id, exc)
        obogacivanje = {}

    # ── KORAK 4: Popuni šablon ────────────────────────────────────────────────
    nacrt = popuni_sablon(req.tip, entiteti, obogacivanje, vks_analiza=vks_analiza)

    # Oduzmi kredit
    await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))

    return {
        "status":  "success",
        "odgovor": nacrt,
        "tip":     req.tip,
        "naziv":   PODNESAK_TIPOVI[req.tip],
    }


# ─── Document Upload (Phase 2.2) ─────────────────────────────────────────────

_ALLOWED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_ALLOWED_SUFFIXES = {".pdf", ".docx"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@app.post("/api/dokument/upload")
@limiter.limit("20/minute")
async def dokument_upload(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(require_credits),
):
    """Upload a legal document (PDF or DOCX), chunk it, and ingest into a
    temporary Pinecone namespace. Returns session_id for Phase 2.3 retrieval."""
    import hashlib
    import tempfile
    from pathlib import Path as _Path

    from uploaded_doc.api_models import UploadResponse
    from uploaded_doc.chunker import chunk_document
    from uploaded_doc.cleanup import cleanup_expired
    from uploaded_doc.extractor import extract
    from uploaded_doc.ingest import ingest_session
    from uploaded_doc.session import generate_session_id, expires_at_iso, ttl_seconds_remaining

    # Content-Length guard (header-based, fast path)
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    # MIME and suffix validation
    suffix = _Path(file.filename or "").suffix.lower()
    if file.content_type not in _ALLOWED_MIMES or suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Unsupported format")

    raw = await file.read()

    # Size guard after read (covers missing Content-Length)
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    # Write to temp file for extractor
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw)
            tmp_path = _Path(tmp.name)

        text, is_scanned = await asyncio.to_thread(extract, tmp_path)

        if is_scanned:
            raise HTTPException(status_code=422, detail="Skenirani ili nečitljiv PDF. Dokument ne sadrži čitljiv tekst — pošaljite digitalni PDF.")

        source_meta = {
            "source_filename": file.filename,
            "source_format": suffix.lstrip("."),
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "is_scanned": is_scanned,
            "session_id": "__local__",
        }
        manifest = await asyncio.to_thread(chunk_document, text, source_meta)

        if manifest.total_chunks == 0:
            raise HTTPException(status_code=422, detail="Empty document")

        session_id = generate_session_id()
        ttl_hours = 24
        try:
            count = await asyncio.to_thread(ingest_session, manifest, session_id, ttl_hours)
        except Exception as e:
            logger.error("[UPLOAD] ingest_session greška: %s", str(e), exc_info=True)
            raise HTTPException(status_code=500, detail=f"Greška pri obradi dokumenta: {str(e)}")

        exp_iso = expires_at_iso(ttl_hours)

        # Fire-and-forget cleanup (non-blocking)
        async def _background_cleanup():
            try:
                result = await asyncio.to_thread(cleanup_expired)
                logger.info("[UPLOAD] Background cleanup: %s", result)
            except Exception as _ce:
                logger.warning("[UPLOAD] Background cleanup failed: %s", _ce)

        asyncio.create_task(_background_cleanup())

        await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return UploadResponse(
            session_id=session_id,
            chunk_count=count,
            chunk_mode_used=manifest.chunk_mode_used,
            article_labels_detected=manifest.article_labels_detected,
            expires_at=exp_iso,
            ttl_seconds=ttl_seconds_remaining(exp_iso),
        )

    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


@app.post("/api/dokument/cleanup")
async def dokument_cleanup(
    x_admin_token: str = Header(default=""),
):
    """Admin endpoint: delete expired tmp_* Pinecone namespaces.
    Requires X-Admin-Token matching FOUNDER_TOKEN env var."""
    from uploaded_doc.api_models import CleanupResponse
    from uploaded_doc.cleanup import cleanup_expired

    founder_token = os.getenv("FOUNDER_TOKEN", "").strip()
    if not founder_token:
        raise HTTPException(status_code=503, detail="Cleanup endpoint not configured")
    if x_admin_token != founder_token:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = await asyncio.to_thread(cleanup_expired, False)
    return CleanupResponse(
        namespaces_deleted=result["namespaces_deleted"],
        chunks_deleted=result["chunks_deleted"],
        namespaces_inspected=result["namespaces_inspected"],
    )


class PitanjeDocRequest(BaseModel):
    session_id: str
    pitanje: str
    history: Optional[List[dict]] = None


_MAX_DOC_PITANJE_LEN = 2000


@app.post("/api/dokument/pitanje")
async def dokument_pitanje(body: PitanjeDocRequest, user: dict = Depends(require_credits)):
    """Ask a question about an uploaded document session."""
    from uploaded_doc.session import validate_session

    if not body.pitanje or not body.pitanje.strip():
        raise HTTPException(status_code=422, detail="Pitanje ne može biti prazno")
    if len(body.pitanje) > _MAX_DOC_PITANJE_LEN:
        raise HTTPException(status_code=422, detail="Pitanje je predugačko")
    if not body.session_id or not body.session_id.strip():
        raise HTTPException(status_code=422, detail="session_id je obavezan")

    session_valid = await asyncio.to_thread(validate_session, body.session_id)
    if not session_valid:
        raise HTTPException(status_code=404, detail="Sesija nije pronađena ili je istekla")

    rezultat = await asyncio.to_thread(
        ask_agent,
        body.pitanje,
        body.history,
        [f"tmp_{body.session_id}"],
    )
    await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
    return rezultat


# ─── /api/dokument/rokovi ────────────────────────────────────────────────────


def _fetch_session_tekst(session_id: str) -> str:
    """Reconstruct document text from Pinecone tmp_<session_id> chunk metadata."""
    try:
        from uploaded_doc.ingest import _get_pinecone_index
        index = _get_pinecone_index()
        namespace = f"tmp_{session_id}"
        result = index.query(
            vector=[0.0] * 3072,
            top_k=1000,
            namespace=namespace,
            include_metadata=True,
        )
        matches = result.matches if hasattr(result, "matches") else result.get("matches", [])
        if not matches:
            return ""
        matches_sorted = sorted(
            matches,
            key=lambda m: int((m.metadata or {}).get("chunk_index", 0))
        )
        texts = [(m.metadata or {}).get("text", "") for m in matches_sorted]
        return "\n\n".join(t for t in texts if t.strip())
    except Exception:
        logger.exception("[ROKOVI] Greška pri čitanju chunks iz Pinecone za session=%s", session_id)
        return ""


class RokoviRequest(BaseModel):
    session_id: str = ""
    tekst: str = Field("", max_length=50000)


@app.post("/api/dokument/rokovi")
@limiter.limit("20/minute")
async def dokument_rokovi(body: RokoviRequest, request: Request, user: dict = Depends(require_credits)):
    """P3.2 — Ekstrakcija rokova iz Pinecone chunks. Ne troši kredit."""
    from uploaded_doc.deadline_parser import ekstrahuj_rokove

    tekst = (body.tekst or "").strip()

    if not tekst and body.session_id:
        from uploaded_doc.session import validate_session
        session_ok = await asyncio.to_thread(validate_session, body.session_id)
        if not session_ok:
            raise HTTPException(status_code=404, detail="Sesija nije pronađena ili je istekla")
        tekst = await asyncio.to_thread(_fetch_session_tekst, body.session_id)

    if not tekst:
        return {"rokovi": [], "ukupno": 0}

    rokovi = await asyncio.to_thread(ekstrahuj_rokove, tekst)
    return {"rokovi": rokovi, "ukupno": len(rokovi)}


# ─── /api/praksa/search ───────────────────────────────────────────────────────

_VALID_MATTERS     = frozenset({"Građanska", "Zaštita prava", "Upravna", "Krivična"})
_VALID_COURTS      = frozenset({"Vrhovni sud", "Vrhovni kasacioni sud"})
_PRAKSA_NS_SEARCH  = "sudska_praksa"


class PraksaSearchReq(BaseModel):
    query:     Optional[str] = None
    matter:    Optional[str] = None
    court:     Optional[str] = None
    year_from: Optional[int] = None
    year_to:   Optional[int] = None
    limit:     int = Field(default=10, ge=1, le=50)
    offset:    int = Field(default=0, ge=0)

    @field_validator("query")
    @classmethod
    def ocisti_query(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return v


def _praksa_search_sync(
    query:     Optional[str],
    matter:    Optional[str],
    court:     Optional[str],
    year_from: Optional[int],
    year_to:   Optional[int],
    limit:     int,
    offset:    int,
) -> dict:
    import re as _re
    from app.services.retrieve import _get_index, _ugradi_query

    # Build Pinecone metadata filter
    filters: dict = {}
    if matter:
        filters["matter"] = {"$eq": matter}
    if court:
        filters["court"] = {"$eq": court}
    filter_dict: Optional[dict] = filters if filters else None

    # Embedding: real vector for semantic search, uniform unit vector for browse.
    # Zero-vector is invalid for cosine metric (undefined similarity); a uniform
    # unit vector is the least-biased valid direction for browse/filter-only mode.
    has_query = bool(query and query.strip())
    if has_query:
        vector = _ugradi_query(query)
    else:
        import math as _math
        _dim = 3072
        vector = [1.0 / _math.sqrt(_dim)] * _dim

    # top_k tuned: semantic=300 sufficient for ranking, browse=1500 covers full namespace (~1479 chunks)
    top_k = 300 if has_query else 1500

    # Pinecone query — sudska_praksa namespace
    index = _get_index()
    res = index.query(
        vector=vector,
        top_k=top_k,
        filter=filter_dict,
        namespace=_PRAKSA_NS_SEARCH,
        include_metadata=True,
    )

    # Group chunks by decision_number
    groups: dict[str, dict] = {}
    for m in res.matches:
        meta = m.metadata or {}
        dn = (meta.get("decision_number") or "").strip() or m.id
        if dn not in groups:
            groups[dn] = {
                "decision_number": dn,
                "decision_date":   meta.get("decision_date", ""),
                "court":           meta.get("court", ""),
                "matter":          meta.get("matter", ""),
                "chunks":          [],
                "max_score":       m.score,
            }
        groups[dn]["chunks"].append({
            "section":     meta.get("section", ""),
            "text":        meta.get("text", "") or meta.get("parent_text", ""),
            "chunk_index": meta.get("chunk_index") or 0,
            "score":       m.score,
        })
        if m.score > groups[dn]["max_score"]:
            groups[dn]["max_score"] = m.score

    # Assemble per-decision objects from sorted chunks
    decisions_raw: list[dict] = []
    for g in groups.values():
        chunks = sorted(g["chunks"], key=lambda c: c["chunk_index"])
        izreka_full   = " ".join(c["text"] for c in chunks if c["section"] == "IZREKA").strip()
        obrazloz_full = " ".join(c["text"] for c in chunks if c["section"] == "OBRAZLOŽENJE").strip()
        decisions_raw.append({
            "decision_number":   g["decision_number"],
            "decision_date":     g["decision_date"],
            "court":             g["court"],
            "matter":            g["matter"],
            "izreka_preview":    izreka_full[:200],
            "izreka_full":       izreka_full,
            "obrazlozenje_full": obrazloz_full,
            "score":             round(g["max_score"], 6),
        })

    # Year filter (in-memory, after grouping)
    if year_from is not None or year_to is not None:
        filtered: list[dict] = []
        for d in decisions_raw:
            yr_m = _re.match(r"(\d{4})", d["decision_date"] or "")
            if not yr_m:
                continue
            yr = int(yr_m.group(1))
            if year_from is not None and yr < year_from:
                continue
            if year_to is not None and yr > year_to:
                continue
            filtered.append(d)
        decisions_raw = filtered

    # Sort: by relevance score when semantic query present, else by date desc
    if has_query:
        decisions_raw.sort(key=lambda d: d["score"], reverse=True)
    else:
        decisions_raw.sort(key=lambda d: d["decision_date"] or "", reverse=True)

    total = len(decisions_raw)
    return {
        "total":     total,
        "page":      offset // limit + 1,
        "limit":     limit,
        "decisions": decisions_raw[offset: offset + limit],
    }


@app.post("/api/praksa/search")
@limiter.limit("30/minute")
async def praksa_search(req: PraksaSearchReq, request: Request):
    """Faceted case-law search over sudska_praksa Pinecone namespace."""
    if req.matter and req.matter not in _VALID_MATTERS:
        return JSONResponse(
            status_code=400,
            content={"error": "Nevalidan matter filter",
                     "detail": f"Dozvoljena vrednost: {sorted(_VALID_MATTERS)}"},
        )
    if req.court and req.court not in _VALID_COURTS:
        return JSONResponse(
            status_code=400,
            content={"error": "Nevalidan court filter",
                     "detail": f"Dozvoljena vrednost: {sorted(_VALID_COURTS)}"},
        )
    if (req.year_from is not None and req.year_to is not None
            and req.year_from > req.year_to):
        return JSONResponse(
            status_code=400,
            content={"error": "Nevalidan opseg godina",
                     "detail": "year_from mora biti ≤ year_to"},
        )
    try:
        result = await asyncio.to_thread(
            _praksa_search_sync,
            req.query, req.matter, req.court,
            req.year_from, req.year_to,
            req.limit, req.offset,
        )
        return result
    except Exception as exc:
        logger.exception("Greška u /api/praksa/search")
        return JSONResponse(
            status_code=500,
            content={"error": "Greška Pinecone servisa", "detail": str(exc)[:200]},
        )
    
# ── F5: CASE MANAGEMENT ───────────────────────────────────────────────────────


def _require_auth(authorization: Optional[str]) -> object:
    """Extract user from Bearer token. Raises 401 if missing or invalid."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization[len("Bearer "):]
    try:
        user_resp = _get_supa().auth.get_user(token)
        user = getattr(user_resp, "user", None)
        if not user:
            raise ValueError("no user")
        return user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


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


@app.get("/api/predmeti/{predmet_id}")
@limiter.limit("60/minute")
async def get_predmet(predmet_id: str, request: Request, authorization: str = Header(None)):
    user = _require_auth(authorization)
    supa = _get_supa()
    row = supa.table("predmeti").select("*").eq("id", predmet_id).eq("user_id", user.id).single().execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")
    beleske   = supa.table("predmet_beleske").select("*").eq("predmet_id", predmet_id).order("created_at", desc=True).execute()
    istorija  = supa.table("predmet_istorija").select("*").eq("predmet_id", predmet_id).order("created_at", desc=True).limit(20).execute()
    dokumenti = supa.table("predmet_dokumenti").select("*").eq("predmet_id", predmet_id).execute()
    return {
        "predmet":   row.data,
        "beleske":   beleske.data,
        "istorija":  istorija.data,
        "dokumenti": dokumenti.data,
    }


@app.patch("/api/predmeti/{predmet_id}")
@limiter.limit("30/minute")
async def update_predmet(predmet_id: str, request: Request, authorization: str = Header(None)):
    user = _require_auth(authorization)
    body = await request.json()
    allowed = {k: v for k, v in body.items() if k in {"naziv", "opis", "tip", "status"}}
    if not allowed:
        raise HTTPException(status_code=400, detail="Nema validnih polja za update")
    _get_supa().table("predmeti").update(allowed).eq("id", predmet_id).eq("user_id", user.id).execute()
    return {"ok": True}


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

OBAVEZNI FORMAT — tačno ovih 13 sekcija:

1. PRAVNI OSNOV
Navedi SVE primenjive zakonske odredbe na opisanu situaciju — bez obzira na to koju stranu štite.
Citiraj ISKLJUČIVO iz bloka DOSTUPNI ZAKONI koji se nalazi na početku korisničkog upita.
Primer za otkaz ugovora o radu: čl. 175, 176, 184, 191 ZR — svi zajedno u jednoj sekciji.
NE raspoređuj članove po sekcijama "za tužioca" ili "za tuženog" — svi idu ovde.

2. ARGUMENTI ZA TUŽIOCA
Najjači FAKTIČKI i pravni argumenti u korist tužioca/oštećenog (max 3 boda).
Fokus na činjenice i procesne prednosti — ne ponavljaj članove iz sekcije 1.

3. ARGUMENTI ZA TUŽENOG
Najjači FAKTIČKI kontraargumenti u korist tuženog/poslodavca (max 3 boda).
Fokus na činjenične nedostatke i procesne rizike — ne navoditi zakonske članove ovde.

4. STRATEGIJA ZA TUŽIOCA
Obavezno tačno ovim redom, svaka stavka na posebnoj liniji:
Najjači napad: [1 rečenica — centralna procesna strategija tužioca]
Zašto: [obrazloženje u 1 rečenici]
Dokaz koji odlučuje spor: [konkretan dokaz ili činjenica]
Snaga argumenta: VISOKA / SREDNJA / NISKA

5. STRATEGIJA ZA TUŽENOG
Obavezno tačno ovim redom, svaka stavka na posebnoj liniji:
Najjača odbrana: [1 rečenica — centralna procesna strategija tuženog]
Zašto: [obrazloženje u 1 rečenici]
Dokaz koji odlučuje spor: [konkretan dokaz ili činjenica]
Snaga argumenta: VISOKA / SREDNJA / NISKA
Napomena za radne sporove: tuženi bi mogao pokušati da istakne postojanje opravdanih razloga, ali sud će ceniti i zakonitost sprovedene procedure.

6. PREDVIĐENI ARGUMENTI TUŽENOG
Najopasnije tvrdnje tuženog koje tužilac mora da predvidi — obavezno u ovom formatu (max 3 argumenta):
- Argument 1: [konkretna tvrdnja tuženog]
  Procena opasnosti: VISOKA / SREDNJA / NISKA — [obrazloženje zašto]
- Argument 2: [konkretna tvrdnja]
  Procena opasnosti: VISOKA / SREDNJA / NISKA — [obrazloženje]
- Argument 3: [konkretna tvrdnja]
  Procena opasnosti: VISOKA / SREDNJA / NISKA — [obrazloženje]

7. KLJUČNA ČINJENICA
Šta odlučuje spor — navedi 2-3 ključne činjenice u formatu:
Ključna činjenica 1: [konkretna tvrdnja]
Ako DA → [konkretna posledica za tužioca]
Ako NE → [konkretna posledica za tuženog]
(ponovi za svaku ključnu činjenicu)

8. SPORNE TAČKE
Ključne činjenične ili pravne tačke oko kojih se stranke mogu sporiti (max 3 boda).

9. POTREBNI DOKAZI
Grupiši dokaze u tačno 3 nivoa — svaki nivo na posebnoj liniji:
🔴 Kritični: (dokazi bez kojih predmet pada — nabrojati)
🟡 Važni: (dokazi koji jačaju poziciju — nabrojati)
🟢 Korisni: (podržavajući dokazi — nabrojati)

10. KOMPLETIRANOST PREDMETA
OBAVEZNO: prva linija mora biti tačno u ovom formatu (bez izmena):
KOMPLETIRANOST: XX%
Zatim na sledećoj liniji:
Nedostaje: [konkretan spisak dokumenata koji fale]
Primer ispravnog outputa:
KOMPLETIRANOST: 35%
Nedostaje: rešenje o otkazu, pisano upozorenje zaposlenom, ugovor o radu

11. PROCENA RIZIKA
OBAVEZNO: popuni SVE tri podsekcije — ne ostavljaj prazne linije.
Faktori koji POVEĆAVAJU rizik:
- [faktor 1]
- [faktor 2]
Faktori koji SMANJUJU rizik:
- [faktor 1]
- [faktor 2]
Ukupna procena: NIZAK / SREDNJI / VISOK — [obrazloženje u 1 rečenici]
OBAVEZNO: reč NIZAK, SREDNJI ili VISOK mora biti prisutna u ovoj sekciji.

12. RELEVANTNA PRAKSA
Samo ako su odlomci sudske prakse dostavljeni pod "RELEVANTNA SUDSKA PRAKSA".
Za svaku presudu obavezno ovim redom:
• [Sud, broj odluke, godina]
  Pravni stav: "[citat ključnog stava u navodnicima — 1-2 rečenice]"
  Sličnost sa predmetom: XX%
  Zašto je relevantna: [1 rečenica]
  Poklapanja: [lista ključnih poklapanja sa predmetom]
  Razlike: [lista ključnih razlika u odnosu na predmet]
Navedi max 3 presude.

13. POUZDANOST PROCENE
OBAVEZNO: prva linija mora biti tačno u ovom formatu:
POUZDANOST: XX%
Zatim:
Nedostaju: [lista dokumenata]
Upload ovih dokumenata može značajno promeniti zaključak.

PRAVILA:
- Nikada ne garantuj ishod postupka.
- Koristi srpsku ekavicu i pravni registar.
- Budi koncizan ali konkretan — bez generičkih fraza.
- Na kraju sekcije 13 dodaj: "Ova procena je generisana uz pomoć AI i mora biti proverena od strane ovlašćenog advokata."
"""

_PROCENA_SYSTEM_PROMPT = _PROCENA_SYSTEM_PROMPT + _CITATION_GUARD


@app.post("/api/procena")
@limiter.limit("5/minute")
async def pravna_procena(request: Request, authorization: str = Header(None)):
    """F5.3 — Structured legal case assessment via GPT-4o."""
    from openai import OpenAI as _OAI
    user = _require_auth(authorization)
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
        if _p_matches:
            _p_parts = [_formatiraj_praksa_match(m) for m in _p_matches]
            _p_parts = [p for p in _p_parts if p and len(p.strip()) > 30]
            if _p_parts:
                _praksa_context = (
                    "\n\nRELEVANTNA SUDSKA PRAKSA (koristi ove odlomke za sekciju 11 — RELEVANTNA PRAKSA):\n\n"
                    + "\n\n---\n\n".join(_p_parts)
                )
                logger.info("[PROCENA] Praksa: %d matches injected iz sudska_praksa", len(_p_parts))
        else:
            logger.info("[PROCENA] Praksa: 0 matches iz sudska_praksa namespace (vektori: 12604)")
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
            max_tokens=3500,
            timeout=60.0,
            messages=[
                {"role": "system", "content": _PROCENA_SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ],
        )
        procena_tekst = (resp.choices[0].message.content or "").strip()
    except Exception:
        logger.exception("[PROCENA] GPT-4o greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju procene. Pokušajte ponovo.")

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
        text, is_scanned = await asyncio.to_thread(extract, tmp_path)
        if is_scanned:
            raise HTTPException(status_code=422, detail="Skenirani PDF — pošaljite digitalni PDF.")
    finally:
        if tmp_path and tmp_path.exists():
            try: tmp_path.unlink()
            except Exception: pass

    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="Dokument je prazan ili nečitljiv.")

    # Phase 2.1 — detect document type for routing to specialized prompt
    doc_type = _detect_doc_type(text)
    logger.info("[P2.1] doc_type=%r for predmet=%s, filename=%s", doc_type, predmet_id, file.filename)

    # Chunk + ingest to Pinecone
    source_meta = {
        "source_filename": file.filename,
        "source_format": suffix.lstrip("."),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "is_scanned": False,
        "session_id": "__local__",
    }
    manifest = await asyncio.to_thread(chunk_document, text, source_meta)
    if manifest.total_chunks == 0:
        raise HTTPException(status_code=422, detail="Dokument je prazan.")

    session_id = generate_session_id()
    ttl_hours  = 24 * 7  # 7 dana za predmet dokumente
    count = await asyncio.to_thread(ingest_session, manifest, session_id, ttl_hours)

    # Record in predmet_dokumenti
    try:
        _get_supa().table("predmet_dokumenti").insert({
            "predmet_id":          predmet_id,
            "user_id":             user.id,
            "naziv_fajla":         file.filename or "dokument",
            "storage_path":        f"session/{session_id}",
            "pinecone_namespace":  f"tmp_{session_id}",
            "status":              "indeksirano",
            "velicina_kb":         max(1, len(raw) // 1024),
        }).execute()
    except Exception:
        logger.warning("[P1.1] predmet_dokumenti insert failed for predmet=%s", predmet_id)

    # ── AUTO ANALYSIS ──────────────────────────────────────────────────────────
    # Phase 2.1: choose prompt and text limit based on detected doc type
    if doc_type == "presuda":
        system_prompt  = _PRESUDA_SYSTEM_PROMPT
        text_limit     = 8000
        text_label     = "TEKST PRESUDE"
        truncate_label = "\n[...presuda se nastavlja, prikazan je izvod...]"
        max_tok        = 1200
    else:
        system_prompt  = _PROCENA_SYSTEM_PROMPT
        text_limit     = 3000
        text_label     = "Sadržaj uploadovanog dokumenta"
        truncate_label = "\n[...dokument nastavlja...]"
        max_tok        = 2800

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

    procena_tekst = ""
    try:
        client = _OAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            max_tokens=max_tok,
            timeout=60.0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": cinjenice_text},
            ],
        )
        procena_tekst = (resp.choices[0].message.content or "").strip()
        logger.info("[P1.1] Auto-procena uspešna za predmet=%s, chars=%d", predmet_id, len(procena_tekst))
    except Exception:
        logger.exception("[P1.1] Auto-procena greška za predmet=%s", predmet_id)
        # Don't fail — return successful upload even if analysis fails
        procena_tekst = ""

    # Persist analysis to predmet_istorija
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

    asyncio.create_task(asyncio.to_thread(cleanup_expired))

    return {
        "session_id":    session_id,
        "filename":      file.filename,
        "chunk_count":   count,
        "predmet_id":    predmet_id,
        "doc_type":      doc_type,
        "procena":       procena_tekst,
        "auto_analyzed": bool(procena_tekst),
    }
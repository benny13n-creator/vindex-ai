# -*- coding: utf-8 -*-
"""
Vindex AI — FastAPI server sa Supabase autentifikacijom i kreditnim sistemom
"""

import logging
import os
import asyncio
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Request, Depends, HTTPException, status, Header
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
        return result.data if result.data is not None else -1
    except Exception:
        logger.exception("Greška pri oduzimanju kredita za korisnika %s", user_id)
        return -1


async def require_credits(user: dict = Depends(get_current_user)) -> dict:
    """Dependency koji proverava da korisnik ima kredite. Founder uvek prolazi."""
    email = user.get("email", "")
    logger.info("require_credits: email=%s is_founder=%s", email, _is_founder(email))
    if _is_founder(email):
        user["credits_remaining"] = 9999
        return user
    credits = await asyncio.to_thread(_get_credits, user["user_id"])
    if credits <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "NO_CREDITS",
                "message": (
                    "Iskoristili ste besplatne upite. "
                    "Pre\u0111ite na Basic paket (49\u20ac) za neograni\u010den pristup."
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
    pitanje: str = Field(..., min_length=3, max_length=2000)
    history: List[HistoryItem] = Field(default_factory=list, max_length=3)

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
    tekst: str = Field(..., min_length=10, max_length=10000)
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
    path = BASE_DIR / "index.html"
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
async def register(req: RegisterReq):
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
            # ali upsert je safety net u slučaju da trigger kasni)
            try:
                supa.table("user_credits").upsert(
                    {"user_id": user_id, "credits_remaining": BESPLATNI_KREDITI},
                    on_conflict="user_id",
                ).execute()
            except Exception as cred_err:
                logger.error(
                    "[REGISTER] user_credits upsert NEUSPEŠAN za uid=%.8s — %s: %r\n"
                    "  >>> Proverite da li je supabase_setup.sql pokrenut u Supabase Dashboard! <<<",
                    user_id, type(cred_err).__name__, str(cred_err)[:300],
                )
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
        rezultat = await pokreni(ask_agent, req.pitanje, None)
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
    try:
        history = [{"q": h.q, "a": h.a} for h in req.history] if req.history else None
        tip = await asyncio.to_thread(klasifikuj_pitanje, _skini_pii(req.pitanje))
        t0 = _time.monotonic()
        rezultat = await pokreni(ask_agent, req.pitanje, history)
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
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
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
    )
    from openai import OpenAI as _OAI

    qh = _q_hash(req.pitanje)
    logger.info("PitanjeStream [uid=%.8s] [q=%s]", user["user_id"], qh)
    asyncio.create_task(_audit(user["user_id"], "pitanje_stream", qh))

    async def _event_generator():
        t0 = _time.monotonic()
        try:
            pitanje_api = _skini_pii(req.pitanje)
            history = [{"q": h.q, "a": h.a} for h in req.history] if req.history else None

            # STEP 1: Retrieve — unpack tuple (v3.0 returns docs + metadata)
            docs, retrieval_meta = await asyncio.to_thread(retrieve_documents, pitanje_api, 10)
            confidence  = retrieval_meta["confidence"]
            top_score   = retrieval_meta["top_score"]
            top_article = retrieval_meta["top_article"]
            top_law     = retrieval_meta["top_law"]
            top_text    = retrieval_meta["top_text"]
            logger.info(
                "[STREAM] confidence=%s score=%.4f article=%s law=%s [q=%s]",
                confidence, top_score, top_article, top_law, qh,
            )
            stream_tip = await asyncio.to_thread(klasifikuj_pitanje, pitanje_api)

            # STEP 2: LOW — stream static refusal, no GPT call
            if confidence == "LOW":
                tekst = _format_low_response(top_score)
                yield f"data: {tekst.replace(chr(10), chr(92) + 'n')}\n\n"
                preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
                yield "data: [DONE]\n\n"
                yield f"data: [CREDITS:{max(preostalo, 0)}]\n\n"
                _al.log_response(
                    endpoint="/api/pitanje/stream", query_hash=qh, tip=stream_tip,
                    confidence="LOW", top_score=top_score, top_article=top_article,
                    top_law=top_law, response_text=tekst,
                    latency_ms=int((_time.monotonic() - t0) * 1000),
                )
                return

            # STEP 3: MEDIUM — stream raw article text, no GPT call
            if confidence == "MEDIUM":
                tekst = _format_medium_response(top_article, top_law, top_text, top_score)
                yield f"data: {tekst.replace(chr(10), chr(92) + 'n')}\n\n"
                preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
                yield "data: [DONE]\n\n"
                yield f"data: [CREDITS:{max(preostalo, 0)}]\n\n"
                _al.log_response(
                    endpoint="/api/pitanje/stream", query_hash=qh, tip=stream_tip,
                    confidence="MEDIUM", top_score=top_score, top_article=top_article,
                    top_law=top_law, response_text=tekst,
                    latency_ms=int((_time.monotonic() - t0) * 1000),
                )
                return

            # STEP 4: HIGH — keep existing topic-specific prompt logic
            filtrirani = _filtriraj_kontekst(docs)
            if not filtrirani:
                yield "data: Nije pronađen relevantan zakonski tekst za vaše pitanje.\n\n"
                yield "data: [DONE]\n\n"
                return

            tip = stream_tip
            prompt_map = {
                "COMPLIANCE": (SYSTEM_PROMPT_COMPLIANCE, "gpt-4o", 1000),
                "PORESKI":    (SYSTEM_PROMPT_PORESKI,    "gpt-4o", 800),
                "PARNICA":    (SYSTEM_PROMPT_PARNICA,    "gpt-4o", 1000),
                "DEFINICIJA": (SYSTEM_PROMPT_DEFINICIJA, "gpt-4o-mini", 600),
            }
            system_prompt, model, max_tokens = prompt_map.get(tip, prompt_map["DEFINICIJA"])

            kontekst = "\n\n---\n\n".join(filtrirani)
            history_blok = ""
            if history:
                stavke = [
                    f"[{i}] Korisnik: {_skini_pii((h.get('q') or '')[:200])}\n"
                    f"    Vindex AI: {(h.get('a') or '')[:400]}..."
                    for i, h in enumerate(history[-3:], 1)
                ]
                history_blok = "ISTORIJA RAZGOVORA (kontekst):\n" + "\n".join(stavke) + "\n\n"

            user_content = (
                f"{history_blok}"
                f"PITANJE: {pitanje_api}\n\n"
                f"KONTEKST IZ BAZE ZAKONA:\n{kontekst}"
            )

            # Stream GPT odgovor — existing structure preserved
            oai = _OAI(api_key=os.getenv("OPENAI_API_KEY"))

            def _stream_sync():
                return oai.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_content},
                    ],
                    temperature=0,
                    max_tokens=max_tokens,
                    stream=True,
                    timeout=30.0,
                )

            stream = await asyncio.to_thread(_stream_sync)

            def _iter_chunks(s):
                for chunk in s:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        yield delta

            full_response_parts: list[str] = []  # buffer for anti-hallucination gate

            for chunk_text in await asyncio.to_thread(lambda: list(_iter_chunks(stream))):
                full_response_parts.append(chunk_text)  # accumulate for gate check
                escaped = chunk_text.replace("\n", "\\n")
                yield f"data: {escaped}\n\n"

            # STEP 5: Anti-hallucination gate — article number presence check
            full_response = "".join(full_response_parts)
            art_num_m = _re.search(r"\d+", top_article or "")
            gate_passes = (not art_num_m) or (art_num_m.group() in full_response)

            if not gate_passes:
                logger.warning(
                    "[STREAM] Anti-hallucination FAIL — %s not cited [q=%s]", top_article, qh,
                )
                notice = (
                    f"\n\n---\n⚠ Citat nije verifikovan u odgovoru. "
                    f"Proverite izvor: {top_law}, {top_article}"
                )
                yield f"data: {notice.replace(chr(10), chr(92) + 'n')}\n\n"

            # Oduzmi kredit i pošalji broj
            preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
            yield "data: [DONE]\n\n"
            yield f"data: [CREDITS:{max(preostalo, 0)}]\n\n"
            _al.log_response(
                endpoint="/api/pitanje/stream", query_hash=qh, tip=stream_tip,
                confidence="HIGH", top_score=top_score, top_article=top_article,
                top_law=top_law, response_text=full_response,
                latency_ms=int((_time.monotonic() - t0) * 1000),
            )

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


@app.post("/api/nacrt")
@limiter.limit("10/minute")
async def nacrt(req: NacrtReq, request: Request, user: dict = Depends(require_credits)):
    """Generisanje nacrta pravnog dokumenta."""
    logger.info("Nacrt [uid=%.8s] vrsta=%s", user["user_id"], req.vrsta)
    asyncio.create_task(_audit(user["user_id"], f"nacrt:{req.vrsta}", ""))
    try:
        qh_nacrt = _q_hash(_skini_pii(req.opis))
        t0 = _time.monotonic()
        rezultat = await pokreni(ask_nacrt, req.vrsta, req.opis)
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
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
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
async def sazmi(req: SazmiReq, request: Request, user: dict = Depends(get_current_user)):
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

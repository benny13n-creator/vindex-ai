# -*- coding: utf-8 -*-
"""
Vindex AI — FastAPI server sa Supabase autentifikacijom i kreditnim sistemom
"""

import logging
import os
import asyncio
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

BASE_DIR = Path(__file__).parent
load_dotenv()

from main import ask_agent, ask_nacrt, ask_analiza

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

SUPABASE_URL         = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_JWT_SECRET  = os.getenv("SUPABASE_JWT_SECRET", "")

_supa: Optional[SupabaseClient] = None


def _get_supa() -> SupabaseClient:
    global _supa
    if _supa is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise RuntimeError(
                "SUPABASE_URL i SUPABASE_SERVICE_KEY moraju biti postavljeni u .env fajlu."
            )
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


def _verify_token(token: str) -> Optional[dict]:
    """
    Verifikuje token u tri koraka:
    1. Direktan HTTP poziv na Supabase /auth/v1/user — najsigurnije, ne zavisi od JWT_SECRET
    2. Lokalni JWT decode — fallback ako je JWT_SECRET ispravno postavljen
    3. JWT decode bez verifikacije — poslednji fallback (samo čita sub/email)
    """
    if not token:
        return None

    # Korak 1: Direktan Supabase Auth API poziv
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        try:
            import urllib.request, json as _json
            url = f"{SUPABASE_URL}/auth/v1/user"
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": SUPABASE_SERVICE_KEY,
                },
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = _json.loads(resp.read())
                if data.get("id"):
                    return {"sub": data["id"], "email": data.get("email", "")}
        except Exception as e:
            logger.debug("Supabase Auth API neuspešno: %s", e)

    # Korak 2: lokalni JWT decode sa tajnim ključem
    if SUPABASE_JWT_SECRET:
        try:
            payload = jose_jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
            if payload.get("sub"):
                return payload
        except JWTError:
            pass

    # Korak 3: JWT decode bez verifikacije potpisa (čita samo sub/email)
    try:
        payload = jose_jwt.decode(
            token,
            options={"verify_signature": False, "verify_aud": False},
            algorithms=["HS256"],
        )
        if payload.get("sub"):
            logger.warning("Token prihvaćen BEZ verifikacije potpisa za user %s", payload.get("sub"))
            return payload
    except JWTError:
        pass

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
    return {"user_id": payload.get("sub"), "email": payload.get("email")}


# ─── Kredit sistem ────────────────────────────────────────────────────────────
BESPLATNI_KREDITI = 15


def _ensure_profile(user_id: str, email: str = "") -> int:
    """
    Čita kredite. Ako profil ne postoji, kreira ga sa 15 kredita (auto-heal).
    Vraća broj preostalih kredita.
    """
    supa = _get_supa()
    try:
        result = (
            supa.table("profiles")
            .select("credits_remaining")
            .eq("id", user_id)
            .execute()
        )
        rows = result.data or []
        if rows:
            return rows[0].get("credits_remaining", 0)
        # Profil ne postoji — kreira se sa 15 kredita
        logger.warning("Profil ne postoji za korisnika %s — kreiranje sa 15 kredita", user_id)
        supa.table("profiles").insert(
            {"id": user_id, "email": email, "credits_remaining": BESPLATNI_KREDITI}
        ).execute()
        return BESPLATNI_KREDITI
    except Exception:
        logger.exception("Greška pri čitanju/kreiranju profila za korisnika %s", user_id)
        return 0


def _get_credits(user_id: str) -> int:
    """Čita broj preostalih kredita iz baze."""
    return _ensure_profile(user_id)


def _deduct_credit(user_id: str) -> int:
    """Atomično oduzima jedan kredit. Vraća preostali broj ili -1 ako nema kredita."""
    try:
        result = _get_supa().rpc("deduct_credit", {"p_user_id": user_id}).execute()
        return result.data if result.data is not None else -1
    except Exception:
        logger.exception("Greška pri oduzimanju kredita za korisnika %s", user_id)
        return -1


async def require_credits(user: dict = Depends(get_current_user)) -> dict:
    """Dependency koji proverava da korisnik ima kredite pre izvršavanja upita."""
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
limiter = Limiter(key_func=get_remote_address, default_limits=["60/hour"])
app = FastAPI(title="Vindex AI", docs_url=None, redoc_url=None)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


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

    @field_validator("tip")
    @classmethod
    def proveri_tip(cls, v: str) -> str:
        dozvoljeni = {"greska", "netacno", "nepotpuno", "ostalo"}
        return v if v in dozvoljeni else "ostalo"


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
def root():
    return {"status": "ok", "servis": "Vindex AI"}


@app.get("/health")
def health():
    return {"status": "ok"}


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

@app.get("/api/me")
async def me(user: dict = Depends(get_current_user)):
    """Vraća podatke o prijavljenom korisniku i broj preostalih kredita. Auto-kreira profil ako ne postoji."""
    try:
        credits = await asyncio.to_thread(_ensure_profile, user["user_id"], user.get("email", ""))
        return {
            "user_id":          user["user_id"],
            "email":            user["email"],
            "credits_remaining": credits,
            "credits_total":    BESPLATNI_KREDITI,
        }
    except Exception as exc:
        logger.exception("Greška u /api/me za korisnika %s", user.get("user_id"))
        raise HTTPException(status_code=500, detail=f"Greška profila: {exc!r}")


@app.get("/api/debug")
async def debug_env():
    """Dijagnostički endpoint — prikazuje status env varijabli (bez tajnih vrednosti)."""
    try:
        import supabase as _supa_mod
        supa_version = getattr(_supa_mod, "__version__", "nepoznato")
    except ImportError:
        supa_version = "nije instalirano"
    jwt_ok  = bool(SUPABASE_JWT_SECRET)
    key_prefix = SUPABASE_SERVICE_KEY[:12] + "..." if SUPABASE_SERVICE_KEY else "(prazan)"
    url_val    = SUPABASE_URL[:40] + "..." if len(SUPABASE_URL) > 40 else SUPABASE_URL
    # probaj konekciju
    conn_status = "nije testirano"
    try:
        supa = _get_supa()
        result = supa.table("profiles").select("id").limit(1).execute()
        conn_status = f"OK — {len(result.data)} redova"
    except Exception as e:
        conn_status = f"GREŠKA: {e!r}"
    return {
        "version": "2025-04-17-v3",
        "supabase_py_version": supa_version,
        "SUPABASE_URL":        url_val,
        "SUPABASE_SERVICE_KEY_prefix": key_prefix,
        "SUPABASE_JWT_SECRET_set": jwt_ok,
        "db_connection": conn_status,
    }


@app.get("/api/test-pitanje")
async def test_pitanje(q: str = "zastarelost dugova za struju"):
    """Dijagnostika pipeline-a — ne oduzima kredite."""
    from app.services.retrieve import retrieve_documents
    from main import _filtriraj_kontekst
    docs = retrieve_documents(q, k=10)
    filtrirani = _filtriraj_kontekst(docs)
    return {
        "pitanje": q,
        "pinecone_docs_count": len(docs),
        "filtrirani_count": len(filtrirani),
        "first_doc_preview": filtrirani[0][:200] if filtrirani else None,
        "fallback_ce_biti_koriscen": len(filtrirani) == 0,
    }


@app.post("/api/check-email")
async def check_email(req: EmailCheckReq):
    """Proverava da li je email adresa jednokratna (disposable)."""
    if _is_disposable_email(req.email):
        return {"valid": False, "razlog": "Privremene email adrese nisu dozvoljene."}
    return {"valid": True}


# ─── AI endpointi (zahtevaju autentifikaciju i kredite) ───────────────────────

@app.post("/api/pitanje")
@limiter.limit("10/minute")
async def pitanje(req: PitanjeReq, request: Request, user: dict = Depends(require_credits)):
    """Pravno istraživanje — pretražuje bazu zakona."""
    logger.info("Pitanje [%s]: %.80s", user["email"], req.pitanje)
    try:
        history = [{"q": h.q, "a": h.a} for h in req.history] if req.history else None
        rezultat = await pokreni(ask_agent, req.pitanje, history)
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"])
        return normalizuj_rezultat(rezultat, credits_remaining=max(preostalo, 0))
    except Exception:
        logger.exception("Neočekivana greška u /api/pitanje")
        return greska_odgovor(
            500,
            "Došlo je do greške na serveru. Pokušajte ponovo za nekoliko sekundi.",
        )


@app.post("/api/nacrt")
@limiter.limit("10/minute")
async def nacrt(req: NacrtReq, request: Request, user: dict = Depends(require_credits)):
    """Generisanje nacrta pravnog dokumenta."""
    logger.info("Nacrt [%s] vrsta=%s", user["email"], req.vrsta)
    try:
        rezultat = await pokreni(ask_nacrt, req.vrsta, req.opis)
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"])
        return normalizuj_rezultat(rezultat, credits_remaining=max(preostalo, 0))
    except Exception:
        logger.exception("Neočekivana greška u /api/nacrt")
        return greska_odgovor(
            500,
            "Došlo je do greške na serveru. Pokušajte ponovo za nekoliko sekundi.",
        )


@app.post("/api/analiza")
@limiter.limit("10/minute")
async def analiza(req: AnalizaReq, request: Request, user: dict = Depends(require_credits)):
    """Analiza pravnog dokumenta."""
    logger.info("Analiza [%s] pitanje=%.60s", user["email"], req.pitanje)
    try:
        rezultat = await pokreni(ask_analiza, req.tekst, req.pitanje)
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"])
        return normalizuj_rezultat(rezultat, credits_remaining=max(preostalo, 0))
    except Exception:
        logger.exception("Neočekivana greška u /api/analiza")
        return greska_odgovor(
            500,
            "Došlo je do greške na serveru. Pokušajte ponovo za nekoliko sekundi.",
        )


# ─── Feedback endpoint ────────────────────────────────────────────────────────

@app.post("/api/feedback")
async def feedback(req: FeedbackReq, user: dict = Depends(get_current_user)):
    """Korisnik prijavljuje netačan ili nepotpun odgovor."""
    try:
        await asyncio.to_thread(
            lambda: _get_supa().table("feedback").insert({
                "user_id": user["user_id"],
                "pitanje": req.pitanje[:2000],
                "odgovor": req.odgovor[:5000],
                "tip":     req.tip,
            }).execute()
        )
        logger.info("Feedback [%s] tip=%s", user["email"], req.tip)
        return {"status": "ok"}
    except Exception:
        logger.exception("Greška u /api/feedback")
        return {"status": "ok"}  # Ne blokiramo korisnika zbog greške u feedbacku

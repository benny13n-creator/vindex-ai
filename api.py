# -*- coding: utf-8 -*-
"""
Vindex AI — FastAPI server
"""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import asyncio
import os

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
    allow_headers=["Content-Type"],
)

# ─── Modeli zahtjeva ──────────────────────────────────────────────────────────

class PitanjeReq(BaseModel):
    pitanje: str = Field(..., min_length=3, max_length=2000)

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


# ─── Helperi ──────────────────────────────────────────────────────────────────

async def pokreni(fn, *args):
    """Pokreće sinhronu funkciju u thread poolu."""
    return await asyncio.to_thread(fn, *args)


def normalizuj_rezultat(rezultat: dict) -> dict:
    if not isinstance(rezultat, dict):
        return {"odgovor": str(rezultat)}
    if rezultat.get("status") == "success":
        return {"odgovor": rezultat.get("data", "")}
    return {"odgovor": rezultat.get("message", "Greška u obradi zahtjeva.")}


def greska_odgovor(status: int, poruka: str) -> JSONResponse:
    logger.warning("API greška %d: %s", status, poruka)
    return JSONResponse(status_code=status, content={"greska": poruka})


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


# ─── API Endpointi ────────────────────────────────────────────────────────────

@app.post("/api/pitanje")
@limiter.limit("10/minute")
async def pitanje(req: PitanjeReq, request: Request):
    """Pravno istraživanje — pretražuje bazu zakona."""
    logger.info("Pitanje: %.80s", req.pitanje)
    try:
        rezultat = await pokreni(ask_agent, req.pitanje)
        return normalizuj_rezultat(rezultat)
    except Exception:
        logger.exception("Neočekivana greška u /api/pitanje")
        return greska_odgovor(500, "Privremena greška servera. Pokušajte ponovo.")


@app.post("/api/nacrt")
@limiter.limit("10/minute")
async def nacrt(req: NacrtReq, request: Request):
    """Generisanje nacrta pravnog dokumenta."""
    logger.info("Nacrt vrsta=%s", req.vrsta)
    try:
        rezultat = await pokreni(ask_nacrt, req.vrsta, req.opis)
        return normalizuj_rezultat(rezultat)
    except Exception:
        logger.exception("Neočekivana greška u /api/nacrt")
        return greska_odgovor(500, "Privremena greška servera. Pokušajte ponovo.")


@app.post("/api/analiza")
@limiter.limit("10/minute")
async def analiza(req: AnalizaReq, request: Request):
    """Analiza pravnog dokumenta."""
    logger.info("Analiza pitanje=%.60s", req.pitanje)
    try:
        rezultat = await pokreni(ask_analiza, req.tekst, req.pitanje)
        return normalizuj_rezultat(rezultat)
    except Exception:
        logger.exception("Neočekivana greška u /api/analiza")
        return greska_odgovor(500, "Privremena greška servera. Pokušajte ponovo.")

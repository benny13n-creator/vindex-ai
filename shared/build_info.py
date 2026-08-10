# -*- coding: utf-8 -*-
"""
Vindex AI — shared/build_info.py

IDENTITET BUILD-A (P0-A, BTM-P0-04)

ZASTO OVAJ MODUL POSTOJI
Do sada nijedan endpoint nije izlagao verziju aplikacije ni git SHA. Posledica
nije bila kozmeticka:

  1. Tokom TASK-3D verifikacije, `localhost:8000` je vracao HTTP 200 i bio
     protumacen kao Vindex. Vrtela se potpuno druga aplikacija ("Focus IP Core
     Engine", 53 rute, nula Vindex ruta). Prijavljen je lazan nalaz o
     nedostupnosti PRO rute. Nijedan odgovor sa servera to nije mogao da
     opovrgne, jer nijedan nije nosio ime aplikacije.

  2. Migracija 107 je primenjena u bazi, ali tri CRITICAL/HIGH ispravke
     kreditne trke su u PYTHON kodu (`0561e6c`, `4e6e4f1`). Ako produkcija
     vrti stariji build, putanja od 1 kredita ostaje eksploatabilna UPRKOS
     primenjenoj migraciji. Bez SHA-a to se ne moze ni potvrditi ni opovrgnuti.

Zato ovo nije "verzija u UI-ju". Ovo je chain-of-custody: dokaz da je odredjeni
commit zaista onaj koji opsluzuje korisnika.

PROJEKTNO PRAVILO KOJE OVAJ MODUL POSTUJE
`commit_source` se UVEK vraca uz `commit`. Vrednost bez porekla je tvrdnja, ne
dokaz -- ista disciplina koju `shared/case_context.py` primenjuje na podatke
predmeta. Ako je `commit_source == "unknown"`, `commit` je `None`, nikad
pogodjena vrednost.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

APP_NAME = "vindex-ai"

_BASE_DIR = Path(__file__).resolve().parent.parent

# Trenutak importa modula. NIJE vreme build-a -- vidi `built_at`.
_STARTED_AT = datetime.now(timezone.utc)

# Redosled je namerno ovakav: eksplicitno pre platformskog, platformsko pre
# citanja .git direktorijuma. Prva neprazna vrednost pobedjuje.
#
# RENDER_GIT_COMMIT i RAILWAY_GIT_COMMIT_SHA obe platforme postavljaju SAME,
# bez ikakve konfiguracije u dashboard-u. Zato P0-A ne zavisi ni od koga.
_SHA_ENV_KEYS: Tuple[str, ...] = (
    "GIT_SHA",                  # nas sopstveni, injektovan kroz Dockerfile ARG
    "RENDER_GIT_COMMIT",        # Render.com, automatski
    "RAILWAY_GIT_COMMIT_SHA",   # Railway, automatski
    "SOURCE_VERSION",           # Heroku-kompatibilne platforme
    "VERCEL_GIT_COMMIT_SHA",
)

_BRANCH_ENV_KEYS: Tuple[str, ...] = (
    "GIT_BRANCH",
    "RENDER_GIT_BRANCH",
    "RAILWAY_GIT_BRANCH",
    "VERCEL_GIT_COMMIT_REF",
)

_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


def _clean_sha(raw: Optional[str]) -> Optional[str]:
    """Prihvata samo ono sto stvarno lici na git SHA.

    Prazan string, `None`, ili smece iz pogresno postavljene promenljive ne sme
    da prodje kao identitet build-a -- radije `unknown` nego lazan dokaz.
    """
    if not raw:
        return None
    s = raw.strip().lower()
    return s if _SHA_RE.match(s) else None


def _sha_from_env() -> Tuple[Optional[str], Optional[str]]:
    for key in _SHA_ENV_KEYS:
        sha = _clean_sha(os.getenv(key))
        if sha:
            return sha, key
    return None, None


def _sha_from_git_dir() -> Tuple[Optional[str], Optional[str]]:
    """Cita .git direktorijum bez pokretanja `git` binarnog fajla.

    U produkcionom image-u ovo radi samo zato sto Dockerfile nema .dockerignore
    pa `COPY . .` povlaci i `.git`. Ako se to ikad promeni, ova grana tiho
    prestaje da vraca vrednost -- a `commit_source` ce to odmah pokazati.
    """
    git_dir = _BASE_DIR / ".git"
    if not git_dir.is_dir():
        return None, None
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None, None

    # Detached HEAD: fajl sadrzi sam SHA.
    direct = _clean_sha(head)
    if direct:
        return direct, "git-dir"

    if not head.startswith("ref:"):
        return None, None
    ref = head.split(":", 1)[1].strip()

    try:
        sha = _clean_sha((git_dir / ref).read_text(encoding="utf-8").strip())
        if sha:
            return sha, "git-dir"
    except OSError:
        pass

    # Ref moze biti spakovan u packed-refs umesto zasebnog fajla.
    try:
        for line in (git_dir / "packed-refs").read_text(encoding="utf-8").splitlines():
            if line.startswith(("#", "^")):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[1].strip() == ref:
                sha = _clean_sha(parts[0])
                if sha:
                    return sha, "git-dir-packed"
    except OSError:
        pass

    return None, None


def _branch() -> Optional[str]:
    for key in _BRANCH_ENV_KEYS:
        val = (os.getenv(key) or "").strip()
        if val:
            return val
    try:
        head = (_BASE_DIR / ".git" / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: refs/heads/"):
            return head.split("refs/heads/", 1)[1].strip() or None
    except OSError:
        pass
    return None


def _built_at() -> Optional[str]:
    """Vreme build-a -- SAMO ako je eksplicitno injektovano.

    Namerno se NE pogadja iz mtime-a fajlova: to bi merilo kada je kod kopiran,
    ne kada je napravljen, a lazan timestamp je gori od nikakvog.
    """
    raw = (os.getenv("BUILD_TIMESTAMP") or "").strip()
    return raw or None


def _sw_cache_name() -> Optional[str]:
    """CACHE_NAME iz static/sw.js -- de-facto marker frontend build-a.

    Backend i frontend se deploy-uju zajedno, ali se keshiraju odvojeno. Ako
    `commit` napreduje a `sw_cache` stoji, korisnik vrti stari frontend nad
    novim backend-om. To je jedini nacin da se taj razlaz uopste primeti.
    """
    try:
        txt = (_BASE_DIR / "static" / "sw.js").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    m = re.search(r"CACHE_NAME\s*=\s*['\"]([^'\"]+)['\"]", txt)
    return m.group(1) if m else None


def _resolve() -> dict:
    sha, source = _sha_from_env()
    if not sha:
        sha, source = _sha_from_git_dir()

    env_raw = os.getenv("ENVIRONMENT")

    return {
        "app": APP_NAME,
        "commit": sha,
        "commit_short": sha[:7] if sha else None,
        # Kako je SHA dobijen. `unknown` znaci da identitet build-a NIJE dokazan
        # -- ne da je nesto poslo po zlu, nego da tvrdnja nema pokrice.
        "commit_source": source or "unknown",
        "branch": _branch(),
        "built_at": _built_at(),
        "started_at": _STARTED_AT.isoformat(),
        # `environment` je ono sto aplikacija stvarno koristi; `environment_declared`
        # kaze da li je iko to zaista postavio ili je palo na podrazumevano.
        # Razlika je bitna: bez nje "production" izgleda isto kad je namerno
        # podeseno i kad nije podeseno uopste.
        "environment": (env_raw or "production").strip(),
        "environment_declared": bool(env_raw and env_raw.strip()),
        "python": sys.version.split()[0],
        "sw_cache": _sw_cache_name(),
    }


# Razresava se jednom, pri importu. Identitet build-a se ne menja u toku zivota
# procesa, a endpoint ne sme da dira disk na svaki zahtev.
_BUILD_INFO = _resolve()


def get_build_info() -> dict:
    """Identitet ovog build-a. Kopija -- pozivalac ne sme da menja kes."""
    return dict(_BUILD_INFO)


def build_identity_proven() -> bool:
    """Da li je identitet build-a DOKAZAN, a ne samo prijavljen."""
    return _BUILD_INFO["commit_source"] != "unknown" and bool(_BUILD_INFO["commit"])


def refresh() -> dict:
    """Ponovo razresava. Postoji zbog testova; produkcija ne treba da je zove."""
    global _BUILD_INFO
    _BUILD_INFO = _resolve()
    return get_build_info()

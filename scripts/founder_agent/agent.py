#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — scripts/founder_agent/agent.py

Founder Autopilot Agent (2026-07-24)

Izolovan interni alat: čita Git napredak (poslednja 24h, ili poslednjih N
commit-a ako u 24h nema ničega), primenjuje persona.json (identitet, ton,
zabranjene fraze, fokus oblasti), i preko OpenAI-ja piše nacrt objave
(LinkedIn stil, srpski jezik) koja zvuči kao osnivač, ne kao generički AI
marketing tekst.

NIKAD ne objavljuje ništa automatski — samo piše u
scripts/founder_agent/drafts/latest_post.md i ispisuje na konzoli. Founder
ručno pregleda i deli (isti Human-in-the-Loop princip kao svaki drugi
agent u ovom repozitorijumu — v. workers/background_agents.py,
routers/agent_notifications.py).

Pokretanje:
  python scripts/founder_agent/agent.py
  python scripts/founder_agent/agent.py --since-hours 48
  python scripts/founder_agent/agent.py --fallback-n 20
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from shared.llm_retry import llm_retry  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("vindex.founder_agent")

_HERE = Path(__file__).resolve().parent
_PERSONA_PATH = _HERE / "persona.json"
_DRAFTS_DIR = _HERE / "drafts"
_LATEST_DRAFT_PATH = _DRAFTS_DIR / "latest_post.md"

_DEFAULT_SINCE_HOURS = 24
_DEFAULT_FALLBACK_N = 15


# ─── Persona ────────────────────────────────────────────────────────────────

def load_persona(path: Optional[Path] = None) -> dict:
    persona_path = path or _PERSONA_PATH
    with open(persona_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ─── Git log ────────────────────────────────────────────────────────────────

def get_git_log(since_hours: int = _DEFAULT_SINCE_HOURS, fallback_n: int = _DEFAULT_FALLBACK_N) -> str:
    """Vraća git log (hash + datum + poruka) za poslednjih `since_hours`
    sati. Ako je prazan (npr. vikend, nema commit-a danas), pada nazad na
    poslednjih `fallback_n` commit-a bez vremenskog ograničenja -- agent
    uvek ima nešto o čemu da piše umesto da tiho ne uradi ništa."""
    log_format = "%h | %ad | %s"

    recent = _run_git_log(["--since", f"{since_hours} hours ago", f"--pretty=format:{log_format}", "--date=short"])
    if recent.strip():
        return recent

    logger.info("[FOUNDER_AGENT] Nema commit-a u poslednjih %dh — pada nazad na poslednjih %d commit-a.", since_hours, fallback_n)
    return _run_git_log([f"-{fallback_n}", f"--pretty=format:{log_format}", "--date=short"])


def _run_git_log(extra_args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "log", *extra_args],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            logger.warning("[FOUNDER_AGENT] git log greška: %s", result.stderr.strip()[:300])
            return ""
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("[FOUNDER_AGENT] git log nije mogao da se izvrši: %s", e)
        return ""


# ─── Zabranjene fraze — primena persona.json pravila ───────────────────────

def find_banned_phrase(tekst: str, banned_words: list[str]) -> Optional[str]:
    """Vraća prvu pronađenu zabranjenu frazu (case-insensitive substring),
    ili None ako tekst ne krši nijedno pravilo."""
    lower = (tekst or "").lower()
    for fraza in banned_words:
        if fraza.lower() in lower:
            return fraza
    return None


def strip_banned_phrases(tekst: str, banned_words: list[str]) -> str:
    """Sigurnosna mreža: čak i posle LLM instrukcije + jednog pokušaja
    regenerisanja, model MOŽE da ignoriše negativnu instrukciju (poznato
    ponašanje LLM-ova). Ovo garantuje da zabranjena fraza NIKAD ne završi
    u fajlu koji se snima na disk, bez obzira šta model vrati."""
    ocisceno = tekst
    for fraza in banned_words:
        ocisceno = re.sub(re.escape(fraza), "", ocisceno, flags=re.IGNORECASE)
    return ocisceno


# ─── LLM generisanje ────────────────────────────────────────────────────────

_MODEL = os.getenv("FOUNDER_AGENT_MODEL", "gpt-4o-mini")


def _build_system_prompt(persona: dict) -> str:
    ton = ", ".join(persona.get("tone_style", []))
    fokus = "\n".join(f"  - {f}" for f in persona.get("key_focus_areas", []))
    zabranjeno = "\n".join(f'  - "{f}"' for f in persona.get("banned_words", []))
    struktura = persona.get("post_structure", {})

    return f"""Ti si {persona.get('identity', 'osnivač tehnološke kompanije')}.

TON I STIL: {ton}

FOKUS OBLASTI (koristi konkretne dokaze iz git loga, ne uopštene tvrdnje):
{fokus}

STRUKTURA OBJAVE (piši na srpskom jeziku):
1. HOOK: {struktura.get('hook', '')}
2. INŽENJERSKA PRIČA: {struktura.get('inzenjerska_prica', '')}
3. ZAKLJUČAK I POTPIS: {struktura.get('zakljucak_i_potpis', '')}

STROGO ZABRANJENE FRAZE — NIKAD ih ne koristi, ni u kom obliku, ni na srpskom ni na engleskom:
{zabranjeno}

Na samom kraju objave, u novom redu, dodaj TAČNO ovaj potpis (bez izmena):
"{persona.get('signature', '')}"

Vrati SAMO tekst objave, bez markdown naslova, bez uvoda tipa "Evo objave:"."""


@llm_retry
def _pozovi_llm_api(system_prompt: str, git_log: str) -> str:
    from openai import OpenAI
    client = OpenAI()
    r = client.chat.completions.create(
        model=_MODEL,
        temperature=0.6,
        max_tokens=700,
        timeout=30.0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"GIT LOG (izvor za objavu):\n{git_log}"},
        ],
    )
    return (r.choices[0].message.content or "").strip()


def generate_post(git_log: str, persona: dict) -> str:
    """Generiše objavu, sa jednim pokušajem regenerisanja ako model prekrši
    banned_words pravilo, i konačnom sigurnosnom mrežom (strip_banned_phrases)
    koja garantuje da se zabranjena fraza NIKAD ne pojavi u vraćenom tekstu."""
    system_prompt = _build_system_prompt(persona)
    banned = persona.get("banned_words", [])

    tekst = _pozovi_llm_api(system_prompt, git_log)
    prekrsaj = find_banned_phrase(tekst, banned)

    if prekrsaj:
        logger.warning("[FOUNDER_AGENT] Model je upotrebio zabranjenu frazu '%s' — pokušavam ponovo.", prekrsaj)
        pojacan_prompt = system_prompt + f'\n\nVAŽNO: prethodni pokušaj je sadržao zabranjenu frazu "{prekrsaj}". NE SME se ponoviti.'
        tekst = _pozovi_llm_api(pojacan_prompt, git_log)

    return strip_banned_phrases(tekst, banned)


# ─── Snimanje nacrta ────────────────────────────────────────────────────────

def write_draft(tekst: str, out_path: Optional[Path] = None) -> Path:
    path = out_path or _LATEST_DRAFT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tekst.strip() + "\n", encoding="utf-8")
    return path


# ─── main ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Vindex AI Founder Autopilot Agent")
    parser.add_argument("--since-hours", type=int, default=_DEFAULT_SINCE_HOURS)
    parser.add_argument("--fallback-n", type=int, default=_DEFAULT_FALLBACK_N)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    persona = load_persona()
    git_log = get_git_log(args.since_hours, args.fallback_n)

    if not git_log.strip():
        print("Nema Git istorije za analizu (prazan repozitorijum ili git nije dostupan).")
        sys.exit(1)

    print("=" * 72)
    print("Vindex AI — Founder Autopilot Agent")
    print("=" * 72)

    tekst = generate_post(git_log, persona)
    out_path = Path(args.out) if args.out else None
    saved_path = write_draft(tekst, out_path)

    print(tekst)
    print("=" * 72)
    print(f"Nacrt sačuvan: {saved_path.resolve()}")


if __name__ == "__main__":
    main()

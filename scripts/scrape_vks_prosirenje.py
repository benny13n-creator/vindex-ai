#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — VKS proširenje scraper v2 (FIXED)
Preuzima sve kategorije sa vrh.sud.rs:
  sc = Vrhovni kasacioni sud
  ac = Apelacioni sudovi
  cc = Privredni apelacioni sud
  uc = Upravni sud

BUG FIX v2: koristimo li.search-result + h3>a + div.result-summary
             i POST sa op=Pretraga, level=1 (kao Phase 1)
             i page numbering od 0 (ne od 1)

Target: 5000 odluka po kombinaciji = 100k+ ukupno

Pokretanje:
    python scripts/scrape_vks_prosirenje.py --dry-run
    python scripts/scrape_vks_prosirenje.py
    python scripts/scrape_vks_prosirenje.py --reset   # brise checkpoint i pocinje ispocetka
"""

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx
from bs4 import BeautifulSoup

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("vks_prosirenje")

# ── Konfiguracija ──────────────────────────────────────────────────────────────
BASE        = "https://www.vrh.sud.rs"
SEARCH_URL  = f"{BASE}/sr-lat/solr-search-page/results"
CRAWL_DELAY = 2.5    # ubrzano za masovni ingest (originalno 10.5)
PAGE_SIZE   = 50
TARGET      = 5000   # po kombinaciji (court_type + matter)
MAX_PAGES   = 120    # 5000 / 50 = 100 stranica; 120 je headroom

OUT_DIR     = _ROOT / "data" / "vks_prosirenje" / "odluke"
CKPT_FILE   = _ROOT / "data" / "vks_prosirenje" / "checkpoint.json"
LOG_FILE    = _ROOT / "data" / "vks_prosirenje" / "scraper.log"

HEADERS = {
    "User-Agent": "Vindex AI Legal Research (vindex-ai.onrender.com; contact: info@vindexai.rs)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sr,en;q=0.9",
    "Referer": "https://www.vrh.sud.rs/sr-lat/sudska-praksa",
}

# Sve kombinacije court_type + matter
TARGETS = [
    # VKS (sc) — sve materije
    {"court_type": "sc", "matter": "33", "label": "VKS/Krivicna"},
    {"court_type": "sc", "matter": "19", "label": "VKS/Gradjanska"},
    {"court_type": "sc", "matter": "9",  "label": "VKS/Upravna"},
    {"court_type": "sc", "matter": "8",  "label": "VKS/ZastitaPrava"},
    {"court_type": "sc", "matter": "20", "label": "VKS/Radno"},
    {"court_type": "sc", "matter": "21", "label": "VKS/Porodicno"},
    {"court_type": "sc", "matter": "22", "label": "VKS/Nasledno"},
    {"court_type": "sc", "matter": "23", "label": "VKS/StvarnoProvo"},
    {"court_type": "sc", "matter": "24", "label": "VKS/Obligaciono"},
    {"court_type": "sc", "matter": "25", "label": "VKS/Privredno"},
    {"court_type": "sc", "matter": "26", "label": "VKS/Stecajno"},
    {"court_type": "sc", "matter": "27", "label": "VKS/Izvrsno"},
    {"court_type": "sc", "matter": "28", "label": "VKS/Vanparnicno"},
    {"court_type": "sc", "matter": "29", "label": "VKS/UpravniSpor"},
    {"court_type": "sc", "matter": "30", "label": "VKS/Ustavno"},
    {"court_type": "sc", "matter": "1",  "label": "VKS/KrivicnoProc"},
    {"court_type": "sc", "matter": "2",  "label": "VKS/Prekrsajno"},
    # Apelacioni sudovi (ac)
    {"court_type": "ac", "matter": "19", "label": "AS/Gradjanska"},
    {"court_type": "ac", "matter": "33", "label": "AS/Krivicna"},
    {"court_type": "ac", "matter": "20", "label": "AS/Radno"},
    {"court_type": "ac", "matter": "21", "label": "AS/Porodicno"},
    {"court_type": "ac", "matter": "22", "label": "AS/Nasledno"},
    {"court_type": "ac", "matter": "25", "label": "AS/Privredno"},
    {"court_type": "ac", "matter": "8",  "label": "AS/ZastitaPrava"},
    {"court_type": "ac", "matter": "9",  "label": "AS/Upravna"},
    {"court_type": "ac", "matter": "27", "label": "AS/Izvrsno"},
    {"court_type": "ac", "matter": "28", "label": "AS/Vanparnicno"},
    # Privredni apelacioni sud (cc)
    {"court_type": "cc", "matter": "25", "label": "PAP/Privredno"},
    {"court_type": "cc", "matter": "26", "label": "PAP/Stecajno"},
    {"court_type": "cc", "matter": "27", "label": "PAP/Izvrsno"},
    {"court_type": "cc", "matter": "19", "label": "PAP/Gradjanska"},
    # Upravni sud (uc)
    {"court_type": "uc", "matter": "9",  "label": "US/Upravno"},
    {"court_type": "uc", "matter": "29", "label": "US/UpravniSpor"},
    {"court_type": "uc", "matter": "19", "label": "US/Gradjanska"},
]


def _iso():
    return datetime.now(timezone.utc).isoformat()


def _load_ckpt():
    if CKPT_FILE.exists():
        return json.loads(CKPT_FILE.read_text(encoding="utf-8"))
    return {"preuzeto": 0, "greske": 0, "preuzeti_ids": [], "gotove_kombinacije": [], "timestamp": _iso()}


def _save_ckpt(ck):
    CKPT_FILE.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_id(text: str, url: str) -> str:
    if text:
        safe = re.sub(r"[^A-Za-z0-9_]", "_", text)
        safe = re.sub(r"_+", "_", safe).strip("_")
        return safe[:80]
    return "id_" + hashlib.md5(url.encode()).hexdigest()[:12]


_last_req = [0.0]


def _rate_limit():
    elapsed = time.time() - _last_req[0]
    if elapsed < CRAWL_DELAY:
        time.sleep(CRAWL_DELAY - elapsed)
    _last_req[0] = time.time()


def _fetch_search(client: httpx.Client, court_type: str, matter: str, page: int):
    """POST na search URL — isti pattern kao Phase 1 koji je radio."""
    _rate_limit()
    # Phase 1 pattern: POST sa op=Pretraga, level=1 + query params
    params = (
        f"court_type={court_type}&matter={matter}"
        f"&sorting=by_date_down&results={PAGE_SIZE}&page={page}"
    )
    url = f"{SEARCH_URL}?{params}"
    for attempt in range(3):
        try:
            r = client.post(url, data={"op": "Pretraga", "level": "1"}, timeout=30)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
            if r.status_code == 429:
                log.warning("429 — cekam 60s")
                time.sleep(60)
            elif r.status_code == 403:
                log.error("403 BLOCKED — stop")
                return None
        except Exception as e:
            log.warning("Greska (pokusaj %d): %s", attempt + 1, e)
            time.sleep(8 * (attempt + 1))
    return None


def _fetch_text(client: httpx.Client, url: str) -> str:
    """Preuzima tekst odluke sa stranice."""
    _rate_limit()
    for attempt in range(3):
        try:
            r = client.get(url, timeout=30)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "lxml")
                # Probaj vise selektora za sadrzaj
                for sel in [
                    "div.field--name-body",
                    "div.field-item",
                    "article .content",
                    "div.tekst-odluke",
                    "div#content",
                    "main article",
                    "article",
                ]:
                    el = soup.select_one(sel)
                    if el:
                        return el.get_text(separator="\n", strip=True)
                # Fallback: body
                return soup.body.get_text(separator="\n", strip=True) if soup.body else ""
        except Exception as e:
            log.warning("Fetch greska (pokusaj %d): %s", attempt + 1, e)
            time.sleep(8 * (attempt + 1))
    return ""


def _parse_results(soup: BeautifulSoup) -> list[dict]:
    """Parsira rezultate — Phase 1 CSS selektori koji su radili."""
    stubs = []

    # Primarni selektor (potvrdjen u Phase 1)
    items = soup.select("li.search-result")

    # Fallback selektori ako se sajt promenio
    if not items:
        items = soup.select("div.views-row")
    if not items:
        items = soup.select("article.node")
    if not items:
        items = soup.select("div.search-result")

    for li in items:
        # Link
        h3 = li.find("h3")
        a = h3.find("a") if h3 else li.find("a", href=True)
        if not a:
            continue

        href = a.get("href", "")
        if not href:
            continue
        url = href if href.startswith("http") else BASE + href
        naslov = a.get_text(strip=True)

        # Summary div
        summary_div = li.find("div", class_="result-summary") or li.find("p")
        summary = summary_div.get_text(strip=True) if summary_div else ""

        # Datum
        datum_m = re.search(r"Datum:\s*(\d{2}\.\d{2}\.\d{4})", summary)
        datum = ""
        if datum_m:
            p = datum_m.group(1).split(".")
            datum = f"{p[2]}-{p[1]}-{p[0]}"

        # Broj predmeta / upisnik
        reg_m = re.search(r"Upisnici?:\s*([^/\n]+)", summary)
        upisnik = reg_m.group(1).strip() if reg_m else ""

        stubs.append({
            "url": url,
            "naslov": naslov,
            "datum": datum,
            "upisnik": upisnik,
            "summary": summary[:300],
        })

    return stubs


def _scrape_combination(client: httpx.Client, target: dict, preuzeti_ids: set) -> list[dict]:
    court_type = target["court_type"]
    matter     = target["matter"]
    label      = target["label"]
    new_decisions = []
    ukupno_stranica_praznih = 0

    log.info("══ %s (court=%s, matter=%s) ══", label, court_type, matter)

    for page in range(0, MAX_PAGES):  # FIXED: od 0, ne od 1
        soup = _fetch_search(client, court_type, matter, page)
        if not soup:
            log.warning("  Nema odgovora za str. %d", page)
            break

        stubs = _parse_results(soup)

        if not stubs:
            ukupno_stranica_praznih += 1
            if ukupno_stranica_praznih >= 2:
                log.info("  Kraj rezultata na str. %d", page)
                break
            continue
        else:
            ukupno_stranica_praznih = 0

        log.info("  Str. %d: %d rezultata", page, len(stubs))

        for stub in stubs:
            decision_id = _safe_id(stub["naslov"], stub["url"])
            if decision_id in preuzeti_ids:
                continue

            tekst = _fetch_text(client, stub["url"])
            if not tekst or len(tekst) < 80:
                log.debug("  SKIP (prekratak tekst): %s", stub["url"])
                continue

            rec = {
                "id": decision_id,
                "izvor": "vrh_sud_prosirenje",
                "sud": label.split("/")[0],
                "materija": label.split("/")[-1] if "/" in label else label,
                "court_type": court_type,
                "matter_id": matter,
                "url": stub["url"],
                "naslov": stub["naslov"],
                "datum": stub["datum"],
                "upisnik": stub["upisnik"],
                "tekst": tekst,
                "scraped_at": _iso(),
            }
            new_decisions.append(rec)
            preuzeti_ids.add(decision_id)

            if len(new_decisions) >= TARGET:
                log.info("  Target %d dostignut za %s", TARGET, label)
                return new_decisions

    log.info("  ✓ %s: %d novih odluka", label, len(new_decisions))
    return new_decisions


def run(dry_run: bool = False, reset: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    Path(_ROOT / "data" / "vks_prosirenje").mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8", mode="a")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s | %(message)s"))
    log.addHandler(fh)

    if reset:
        log.info("RESET — brišem checkpoint")
        if CKPT_FILE.exists():
            CKPT_FILE.unlink()

    ck = _load_ckpt()
    preuzeti_ids = set(ck.get("preuzeti_ids", []))
    gotove = set(ck.get("gotove_kombinacije", []))
    preuzeto = ck.get("preuzeto", 0)
    greske   = ck.get("greske", 0)

    log.info("═══ VKS PROŠIRENJE v2 — %d kombinacija, target %d po komb. ═══", len(TARGETS), TARGET)
    log.info("  Vec preuzeto: %d | Vec gotovih kombinacija: %d", preuzeto, len(gotove))

    if dry_run:
        print(f"Kombinacija: {len(TARGETS)}")
        print(f"Target po kombinaciji: {TARGET}")
        print(f"Max procena: {len(TARGETS) * TARGET:,} odluka")
        print(f"Vec gotovih kombinacija: {len(gotove)}/{len(TARGETS)}")
        return

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for target in TARGETS:
            key = f"{target['court_type']}_{target['matter']}"
            if key in gotove:
                log.info("  SKIP (vec gotovo): %s", target["label"])
                continue

            try:
                new = _scrape_combination(client, target, preuzeti_ids)
            except Exception as e:
                log.error("Greska za %s: %s", target["label"], e)
                greske += 1
                gotove.add(key)
                ck.update({"greske": greske, "gotove_kombinacije": list(gotove), "timestamp": _iso()})
                _save_ckpt(ck)
                continue

            # Sacuvaj odluke
            for rec in new:
                fpath = OUT_DIR / f"{rec['id']}.json"
                if not fpath.exists():
                    fpath.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
                    preuzeto += 1

            gotove.add(key)
            ck.update({
                "preuzeto": preuzeto,
                "greske": greske,
                "preuzeti_ids": list(preuzeti_ids),
                "gotove_kombinacije": list(gotove),
                "timestamp": _iso(),
            })
            _save_ckpt(ck)
            log.info("  [Checkpoint] Ukupno: %d odluka | Gotovih kombinacija: %d/%d",
                     preuzeto, len(gotove), len(TARGETS))

    log.info("═══ ZAVRŠENO: %d odluka u %s ═══", preuzeto, OUT_DIR)
    print(f"\n{'='*60}")
    print(f"VKS PROŠIRENJE ZAVRŠENO: {preuzeto:,} odluka")
    print(f"Greške: {greske}")
    print(f"Lokacija: {OUT_DIR}")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VKS proširenje scraper v2")
    parser.add_argument("--dry-run", action="store_true", help="Samo procena, bez preuzimanja")
    parser.add_argument("--reset", action="store_true", help="Brisi checkpoint i pocni ispocetka")
    args = parser.parse_args()
    run(dry_run=args.dry_run, reset=args.reset)

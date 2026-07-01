#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — ECHR / HUDOC scraper za predmete Srbije
Preuzima sve odluke Evropskog suda za ljudska prava u kojima je Srbija tužena strana.

Pokretanje:
    python scripts/scrape_echr.py --dry-run    # samo broji
    python scripts/scrape_echr.py              # preuzima sve

Output: data/echr/odluke/{itemid}.json
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("echr_scraper")

# ── Konfiguracija ──────────────────────────────────────────────────────────────
HUDOC_SEARCH = "https://hudoc.echr.coe.int/app/query/results"
HUDOC_TEXT   = "https://hudoc.echr.coe.int/app/conversion/docx/html/body"
RATE_S       = 1.0
PAGE_SIZE    = 500

OUT_DIR      = _ROOT / "data" / "echr" / "odluke"
CKPT_FILE    = _ROOT / "data" / "echr" / "checkpoint.json"
LOG_FILE     = _ROOT / "data" / "echr" / "scraper.log"

HEADERS = {
    "User-Agent": "Vindex AI Legal Research (vindex-ai.onrender.com; contact: info@vindexai.rs)",
    "Accept": "application/json",
    "Accept-Language": "sr,en;q=0.9",
}

SELECT_FIELDS = ",".join([
    "itemid", "appno", "docname", "typedescription",
    "languageisocode", "judgementdate", "decisiondate",
    "conclusion", "respondent", "importance", "article",
    "violation", "nonviolation", "extractedappno",
    "originatingbody", "scl",
])


def _iso():
    return datetime.now(timezone.utc).isoformat()


def _load_ckpt():
    if CKPT_FILE.exists():
        return json.loads(CKPT_FILE.read_text(encoding="utf-8"))
    return {"preuzeto": 0, "greske": 0, "preuzeti_ids": [], "timestamp": _iso()}


def _save_ckpt(ck):
    CKPT_FILE.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_downloaded(itemid: str) -> bool:
    return (OUT_DIR / f"{itemid}.json").exists()


def _fetch_all_ids(client: httpx.Client) -> list[dict]:
    """Preuzima sve metapodatke za predmete Srbije sa HUDOC-a."""
    all_results = []
    start = 0

    while True:
        params = {
            "select": SELECT_FIELDS,
            "sort": "judgementdate Desc",
            "query": 'respondent:"SRB"',
            "start": start,
            "length": PAGE_SIZE,
        }
        try:
            r = client.get(HUDOC_SEARCH, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.error("Greška pri preuzimanju stranice start=%d: %s", start, e)
            time.sleep(5)
            continue

        results = data.get("results", [])
        total = data.get("resultcount", 0)

        if not results:
            break

        for item in results:
            all_results.append(item.get("columns", {}))

        log.info("Preuzeto metapodataka: %d / %d", len(all_results), total)

        if len(all_results) >= total:
            break

        start += PAGE_SIZE
        time.sleep(RATE_S)

    return all_results


def _fetch_full_text(client: httpx.Client, itemid: str) -> str:
    """Pokušava da preuzme pun tekst odluke."""
    url = f"{HUDOC_TEXT}?library=ECHR&id={itemid}"
    try:
        r = client.get(url, timeout=30)
        if r.status_code == 200 and len(r.text) > 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "lxml")
            # Ukloni tagove, vrati čist tekst
            return soup.get_text(separator="\n", strip=True)
    except Exception as e:
        log.debug("Tekst nije dostupan za %s: %s", itemid, e)
    return ""


def _build_record(meta: dict, tekst: str) -> dict:
    """Gradi JSON zapis za jednu ECHR odluku."""
    datum = meta.get("judgementdate") or meta.get("decisiondate") or ""
    if datum and "T" in datum:
        datum = datum.split("T")[0]

    return {
        "id": meta.get("itemid", ""),
        "izvor": "echr",
        "sud": "Evropski sud za ljudska prava",
        "drzava": "Srbija (tužena strana)",
        "broj_predmeta": meta.get("appno", ""),
        "naziv": meta.get("docname", ""),
        "tip_odluke": meta.get("typedescription", ""),
        "datum": datum,
        "jezik": meta.get("languageisocode", "ENG"),
        "vaznost": meta.get("importance", ""),
        "clanovi": meta.get("article", ""),
        "povreda": meta.get("violation", ""),
        "bez_povrede": meta.get("nonviolation", ""),
        "zakljucak": meta.get("conclusion", ""),
        "telo": meta.get("originatingbody", ""),
        "tekst": tekst,
        "url": f"https://hudoc.echr.coe.int/eng#{{'itemid':['{meta.get('itemid', '')}']}}",
        "scraped_at": _iso(),
    }


def run(dry_run: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Dodaj file handler za log
    fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s | %(message)s"))
    log.addHandler(fh)

    ck = _load_ckpt()
    preuzeti_set = set(ck.get("preuzeti_ids", []))

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        log.info("═══ ECHR SCRAPER — preuzimam listu predmeta Srbije ═══")
        svi = _fetch_all_ids(client)
        log.info("Ukupno pronađeno na HUDOC-u: %d predmeta", len(svi))

        if dry_run:
            vec_preuzeto = sum(1 for m in svi if _is_downloaded(m.get("itemid", "")))
            print(f"\nDRY RUN REZULTAT:")
            print(f"  Ukupno na HUDOC-u: {len(svi)}")
            print(f"  Već preuzeto: {vec_preuzeto}")
            print(f"  Za preuzimanje: {len(svi) - vec_preuzeto}")
            return

        todo = [m for m in svi if m.get("itemid") and m["itemid"] not in preuzeti_set]
        log.info("Za preuzimanje: %d / %d", len(todo), len(svi))

        preuzeto = ck.get("preuzeto", 0)
        greske = ck.get("greske", 0)

        for i, meta in enumerate(todo):
            itemid = meta.get("itemid", "")
            if not itemid:
                continue

            if _is_downloaded(itemid):
                preuzeti_set.add(itemid)
                continue

            tekst = _fetch_full_text(client, itemid)
            rec = _build_record(meta, tekst)

            # Čuvamo i ako nema teksta (metapodaci su vredni)
            path = OUT_DIR / f"{itemid}.json"
            path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            preuzeto += 1
            preuzeti_set.add(itemid)

            if (i + 1) % 50 == 0:
                log.info("Napredak: %d / %d preuzeto", preuzeto, len(svi))
                ck.update({
                    "preuzeto": preuzeto,
                    "greske": greske,
                    "preuzeti_ids": list(preuzeti_set),
                    "timestamp": _iso(),
                    "ukupno": len(svi),
                })
                _save_ckpt(ck)

            time.sleep(RATE_S)

    ck.update({
        "preuzeto": preuzeto,
        "greske": greske,
        "preuzeti_ids": list(preuzeti_set),
        "timestamp": _iso(),
        "ukupno": len(svi),
    })
    _save_ckpt(ck)
    log.info("═══ ECHR SCRAPER ZAVRŠEN: %d odluka preuzeto ═══", preuzeto)
    print(f"\nECHR ZAVRŠEN: {preuzeto} odluka u data/echr/odluke/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)

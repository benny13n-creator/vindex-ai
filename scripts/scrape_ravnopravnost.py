#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — Poverenik za zaštitu ravnopravnosti scraper
Preuzima mišljenja i preporuke sa ravnopravnost.gov.rs (~1,400 dokumenata, HTML).

Pokretanje:
    python scripts/scrape_ravnopravnost.py --dry-run
    python scripts/scrape_ravnopravnost.py

Output: data/ravnopravnost/odluke/{id}.json
"""

import argparse, json, logging, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx
from bs4 import BeautifulSoup

_ROOT = Path(__file__).parent.parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("ravnopravnost_scraper")

BASE      = "https://ravnopravnost.gov.rs"
LIST_URL  = "https://ravnopravnost.gov.rs/misljenja-i-preporuke/page/{page}/"
TOTAL_PGS = 145   # malo više od 141 — bot detektuje kraj automatski
RATE_S    = 1.2

OUT_DIR  = _ROOT / "data" / "ravnopravnost" / "odluke"
CKPT     = _ROOT / "data" / "ravnopravnost" / "checkpoint.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VindexBot/1.0; legal research; contact: info@vindexai.rs)",
    "Accept": "text/html,*/*",
    "Accept-Language": "sr-RS,sr;q=0.9",
}

def _iso(): return datetime.now(timezone.utc).isoformat()
def _load_ckpt():
    if CKPT.exists(): return json.loads(CKPT.read_text(encoding="utf-8"))
    return {"preuzeto": 0, "greske": 0, "preuzeti_urls": [], "poslednja_strana": 0, "timestamp": _iso()}
def _save_ckpt(ck): CKPT.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")

def _slug(url: str) -> str:
    path = url.rstrip("/").split("/")[-1]
    return re.sub(r"[^\w]", "_", path)[:80] or "doc"

def _get(client, url):
    for attempt in range(3):
        try:
            r = client.get(url, timeout=30)
            if r.status_code == 200: return r
            if r.status_code == 404: return None
            time.sleep(5 * (attempt + 1))
        except Exception as e:
            log.warning("Greška (pokušaj %d): %s", attempt + 1, e)
            time.sleep(5 * (attempt + 1))
    return None

def _scrape_listing(client, page: int) -> list[dict]:
    r = _get(client, LIST_URL.format(page=page))
    if not r: return []

    soup = BeautifulSoup(r.text, "lxml")
    items = []

    # Svaka stavka ima "Opširnije" link koji vodi na punu stranicu mišljenja.
    # URL pattern: /\d+-\d+-naslov-misljenja/
    MISLJENJE_RE = re.compile(r"ravnopravnost\.gov\.rs/\d+[-–]\d+[-–]")

    for a in soup.find_all("a", href=MISLJENJE_RE):
        href = a["href"]
        if not href.startswith("http"): href = BASE + href

        naslov_tekst = a.get_text(strip=True)

        # Naslov je u <h5> ili <h2> u istom roditeljskom divu
        parent = a.find_parent(["div", "article", "section", "li"])
        naslov = naslov_tekst
        datum  = ""

        if parent:
            h = parent.find(["h2", "h3", "h4", "h5"])
            if h:
                hn = h.get_text(strip=True)
                if len(hn) > len(naslov): naslov = hn

            # Datum
            ptxt = parent.get_text(" ", strip=True)
            dm = re.search(r"(\d{1,2})\.\s*(\w+)\s*(\d{4})", ptxt)
            if not dm:
                dm = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", ptxt)
                if dm: datum = f"{dm.group(3)}-{dm.group(2).zfill(2)}-{dm.group(1).zfill(2)}"

        if not naslov or len(naslov) < 8: naslov = href.split("/")[-2].replace("-", " ")

        items.append({"url": href, "naslov": naslov[:400], "datum": datum})

    # Deduplikacija
    seen = set()
    unique = []
    for it in items:
        if it["url"] not in seen:
            seen.add(it["url"])
            unique.append(it)
    return unique

def _scrape_article(client, url: str) -> str:
    r = _get(client, url)
    if not r: return ""

    soup = BeautifulSoup(r.text, "lxml")
    # Traži głównu content oblast
    for sel in ["article", ".entry-content", ".post-content", "main", ".content"]:
        el = soup.select_one(sel)
        if el:
            # Ukloni navigaciju i bočni panel
            for tag in el.select("nav, .sidebar, .widget, script, style, header, footer"):
                tag.decompose()
            tekst = el.get_text(separator="\n", strip=True)
            if len(tekst) > 200: return tekst

    # Fallback — body
    body = soup.find("body")
    return body.get_text(separator="\n", strip=True)[:50000] if body else ""

def run(dry_run=False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (_ROOT / "data" / "ravnopravnost").mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(str(_ROOT / "data" / "ravnopravnost" / "scraper.log"), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s | %(message)s"))
    log.addHandler(fh)

    ck = _load_ckpt()
    preuzeti = set(ck.get("preuzeti_urls", []))
    preuzeto = ck.get("preuzeto", 0)
    greske   = ck.get("greske", 0)
    start_pg = ck.get("poslednja_strana", 0) + 1

    log.info("═══ RAVNOPRAVNOST SCRAPER — od stranice %d ═══", start_pg)

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        empty_pages = 0
        for page in range(start_pg, TOTAL_PGS + 1):
            log.info("Stranica %d/%d...", page, TOTAL_PGS)
            items = _scrape_listing(client, page)

            if not items:
                empty_pages += 1
                if empty_pages >= 3:
                    log.info("Kraj listinga.")
                    break
                time.sleep(RATE_S)
                continue

            empty_pages = 0
            log.info("  Pronađeno %d mišljenja", len(items))

            if dry_run:
                for it in items[:3]: print(f"  {it['naslov'][:70]}")
                if page >= 2:
                    print(f"\nDRY RUN: ~{len(items)*141} mišljenja procenjeno (141 stranica)")
                    return
                time.sleep(RATE_S)
                continue

            for item in items:
                if item["url"] in preuzeti: continue

                out_id  = _slug(item["url"])
                out_path = OUT_DIR / f"ravnopravnost_{out_id}.json"
                if out_path.exists():
                    preuzeti.add(item["url"])
                    continue

                tekst = _scrape_article(client, item["url"])
                time.sleep(RATE_S * 0.8)

                if len(tekst) < 100:
                    log.warning("  Prazan sadržaj: %s", item["url"][:60])
                    greske += 1
                    preuzeti.add(item["url"])
                    continue

                rec = {
                    "id": f"ravnopravnost_{out_id}",
                    "izvor": "poverenik_ravnopravnost",
                    "institucija": "Poverenik za zaštitu ravnopravnosti",
                    "naslov": item["naslov"][:500],
                    "datum": item["datum"],
                    "url": item["url"],
                    "tekst": tekst[:80000],
                    "scraped_at": _iso(),
                }
                out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
                preuzeti.add(item["url"])
                preuzeto += 1

            ck.update({
                "preuzeto": preuzeto, "greske": greske,
                "preuzeti_urls": list(preuzeti),
                "poslednja_strana": page, "timestamp": _iso(),
            })
            _save_ckpt(ck)
            log.info("  Ukupno: %d | Ova str: %d", preuzeto, len(items))
            time.sleep(RATE_S)

    ck.update({"preuzeto": preuzeto, "greske": greske, "preuzeti_urls": list(preuzeti), "timestamp": _iso()})
    _save_ckpt(ck)
    log.info("═══ RAVNOPRAVNOST ZAVRŠEN: %d mišljenja ═══", preuzeto)
    print(f"\nRAVNOPRAVNOST: {preuzeto} mišljenja u {OUT_DIR}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)

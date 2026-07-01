#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — Ministarstvo finansija scraper
Preuzima mesečne biltene stručnih mišljenja (PDF) sa mfin.gov.rs.
~23 stranice listinga × ~10 biltena = ~230 biltena PDF-ova.

Pokretanje:
    python scripts/scrape_mfin.py --dry-run
    python scripts/scrape_mfin.py

Output: data/mfin/odluke/{id}.json
"""

import argparse, json, logging, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx
import pypdf
from bs4 import BeautifulSoup

_ROOT = Path(__file__).parent.parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("mfin_scraper")

BASE       = "https://www.mfin.gov.rs"
LIST_BASE  = "https://www.mfin.gov.rs/aktivnosti/strucna-miljenja"
RATE_S     = 1.5

OUT_DIR  = _ROOT / "data" / "mfin" / "odluke"
PDF_DIR  = _ROOT / "data" / "mfin" / "pdf"
CKPT     = _ROOT / "data" / "mfin" / "checkpoint.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VindexBot/1.0; legal research; contact: info@vindexai.rs)",
    "Accept": "text/html,*/*",
    "Accept-Language": "sr-RS,sr;q=0.9",
}

def _iso(): return datetime.now(timezone.utc).isoformat()
def _load_ckpt():
    if CKPT.exists(): return json.loads(CKPT.read_text(encoding="utf-8"))
    return {"preuzeto": 0, "greske": 0, "preuzeti_ids": [], "timestamp": _iso()}
def _save_ckpt(ck): CKPT.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")

def _slug(url: str) -> str:
    path = url.rstrip("/").split("/")[-1]
    return re.sub(r"[^\w]", "_", path)[:80] or "doc"

def _get(client, url):
    for attempt in range(3):
        try:
            r = client.get(url, timeout=40)
            if r.status_code == 200: return r
            if r.status_code in (404, 410): return None
            time.sleep(6 * (attempt + 1))
        except Exception as e:
            log.warning("Greška (pokušaj %d): %s", attempt + 1, e)
            time.sleep(6 * (attempt + 1))
    return None

def _get_bilten_links(client) -> list[dict]:
    """Prikuplja sve bilten stranice sa svih 23 stranica listinga."""
    links = []
    seen  = set()

    for page in range(1, 30):
        url = LIST_BASE if page == 1 else f"{LIST_BASE}/{page}"
        log.info("Listing stranica %d: %s", page, url)
        r = _get(client, url)
        if not r: break

        soup = BeautifulSoup(r.text, "lxml")

        # Bilten linkovi — vode na /aktivnosti/bilten-... stranice
        found = 0
        for a in soup.find_all("a", href=lambda h: h and "/aktivnosti/bilten" in h):
            href = a["href"]
            if not href.startswith("http"): href = BASE + href
            if href in seen: continue
            seen.add(href)
            naslov = a.get_text(strip=True)
            if not naslov: naslov = href.split("/")[-1].replace("-", " ")
            links.append({"url": href, "naslov": naslov[:400]})
            found += 1

        log.info("  Pronađeno %d bilten linkova (ukupno: %d)", found, len(links))

        # Proveri da li ima sledeće stranice
        next_lnk = soup.find("a", string=re.compile(r"»|Sledeća|Next", re.I))
        if not next_lnk and found == 0: break

        time.sleep(RATE_S * 0.5)

    return links

def _get_pdf_from_bilten(client, url: str) -> tuple[str, str]:
    """Sa bilten stranice izvlači PDF URL i datum."""
    r = _get(client, url)
    if not r: return "", ""

    soup = BeautifulSoup(r.text, "lxml")

    # PDF link
    pdf_url = ""
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" in href.lower() and "mfin.gov.rs" in href:
            if not href.startswith("http"): href = BASE + href
            pdf_url = href
            break

    # Datum
    datum = ""
    for el in soup.find_all(["time", "span", "p", "div"]):
        txt = el.get_text(strip=True)
        dm = re.search(r"(\d{1,2})\.\s+(\w+)\s+(\d{4})\.", txt)
        if dm:
            datum = f"{dm.group(3)}"
            break
        dm2 = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", txt)
        if dm2:
            datum = f"{dm2.group(3)}-{dm2.group(2).zfill(2)}-{dm2.group(1).zfill(2)}"
            break

    return pdf_url, datum

def _extract_pdf_text(pdf_path: Path) -> str:
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        parts = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip(): parts.append(t)
        return "\n\n".join(parts)
    except Exception as e:
        log.error("PDF greška (%s): %s", pdf_path.name, e)
        return ""

def run(dry_run=False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    (_ROOT / "data" / "mfin").mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(str(_ROOT / "data" / "mfin" / "scraper.log"), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s | %(message)s"))
    log.addHandler(fh)

    ck = _load_ckpt()
    preuzeti = set(ck.get("preuzeti_ids", []))
    preuzeto = ck.get("preuzeto", 0)
    greske   = ck.get("greske", 0)

    log.info("═══ MFIN SCRAPER — pokretanje ═══")

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        bilten_links = _get_bilten_links(client)
        log.info("Ukupno pronađeno bilten stranica: %d", len(bilten_links))

        if dry_run:
            print(f"\nDRY RUN: {len(bilten_links)} biltena pronađeno")
            for b in bilten_links[:5]: print(f"  {b['naslov'][:70]}")
            return

        for bilten in bilten_links:
            bid = _slug(bilten["url"])
            if bid in preuzeti: continue

            out_path = OUT_DIR / f"mfin_{bid}.json"
            if out_path.exists():
                preuzeti.add(bid)
                continue

            log.info("Bilten: %s", bilten["naslov"][:60])
            pdf_url, datum = _get_pdf_from_bilten(client, bilten["url"])
            time.sleep(RATE_S * 0.5)

            if not pdf_url:
                log.warning("  Nema PDF-a za: %s", bilten["url"][:60])
                greske += 1
                preuzeti.add(bid)
                continue

            # Preuzmi PDF
            pdf_path = PDF_DIR / f"{bid}.pdf"
            if not pdf_path.exists():
                r_pdf = _get(client, pdf_url)
                if r_pdf and (b"%PDF" in r_pdf.content[:10] or len(r_pdf.content) > 10000):
                    pdf_path.write_bytes(r_pdf.content)
                    log.info("  PDF preuzet: %d KB", len(r_pdf.content)//1024)
                else:
                    log.warning("  PDF nije preuzet: %s", pdf_url[:60])
                    greske += 1
                    preuzeti.add(bid)
                    continue
                time.sleep(RATE_S)

            tekst = _extract_pdf_text(pdf_path)
            log.info("  Tekst: %d karaktera", len(tekst))

            rec = {
                "id": f"mfin_{bid}",
                "izvor": "mfin_bilten",
                "institucija": "Ministarstvo finansija RS",
                "tip": "Bilten stručnih mišljenja",
                "naslov": bilten["naslov"],
                "datum": datum,
                "url": bilten["url"],
                "pdf_url": pdf_url,
                "tekst": tekst[:200000],
                "scraped_at": _iso(),
            }
            out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            preuzeti.add(bid)
            preuzeto += 1

            ck.update({"preuzeto": preuzeto, "greske": greske, "preuzeti_ids": list(preuzeti), "timestamp": _iso()})
            _save_ckpt(ck)
            time.sleep(RATE_S)

    ck.update({"preuzeto": preuzeto, "greske": greske, "preuzeti_ids": list(preuzeti), "timestamp": _iso()})
    _save_ckpt(ck)
    log.info("═══ MFIN ZAVRŠEN: %d biltena ═══", preuzeto)
    print(f"\nMFIN: {preuzeto} biltena u {OUT_DIR}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)

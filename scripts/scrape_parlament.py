#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — Narodna skupština Srbije scraper
Preuzima donete zakone i predloge zakona sa parlament.gov.rs.
~3,000+ zakona dostupno besplatno u PDF/DOC formatu.

Pokretanje:
    python scripts/scrape_parlament.py --dry-run
    python scripts/scrape_parlament.py

Output: data/parlament/odluke/{id}.json
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
log = logging.getLogger("parlament_scraper")

BASE   = "https://www.parlament.gov.rs"
RATE_S = 1.3

# Kategorije zakona po sazivu (od 2001 do danas)
# Skupština ima ~3,000+ zakona
SAZIVI = [
    {"url": "/akti/doneti-zakoni/doneti-zakoni.1033.html", "opis": "Tekući saziv"},
    # Dodatne stranice paginacije se generišu dinamički
]

OUT_DIR = _ROOT / "data" / "parlament" / "odluke"
PDF_DIR = _ROOT / "data" / "parlament" / "pdf"
CKPT    = _ROOT / "data" / "parlament" / "checkpoint.json"

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
    path = url.rstrip("/").split("/")[-1].replace(".html", "").replace(".pdf", "")
    return re.sub(r"[^\w]", "_", path)[:80] or "zakon"

def _get(client, url):
    for attempt in range(3):
        try:
            r = client.get(url, timeout=30)
            if r.status_code == 200: return r
            if r.status_code in (404, 410): return None
            time.sleep(5 * (attempt + 1))
        except Exception as e:
            log.warning("Greška (pokušaj %d): %s", attempt + 1, e)
            time.sleep(5 * (attempt + 1))
    return None

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

def _get_zakon_links(client) -> list[dict]:
    """Sakuplja sve zakone sa svih stranica Skupštine."""
    all_links = []
    seen = set()

    # Skupština paginira sa ?start=N (Joomla)
    base_url = BASE + "/akti/doneti-zakoni/doneti-zakoni.1033.html"
    offset = 0

    while True:
        url = base_url if offset == 0 else f"{base_url}?start={offset}"
        log.info("  Skupštinska lista offset=%d", offset)

        r = _get(client, url)
        if not r: break

        soup = BeautifulSoup(r.text, "lxml")
        found = 0

        # Tabela zakona
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2: continue

            # Naslov zakona
            naslov_td = tds[0]
            naslov_a = naslov_td.find("a", href=True)
            if not naslov_a: continue

            naslov = naslov_a.get_text(strip=True)
            zakon_href = naslov_a["href"]
            if not zakon_href.startswith("http"):
                zakon_href = BASE + zakon_href

            if zakon_href in seen: continue
            seen.add(zakon_href)

            # Datum iz tabele
            datum = ""
            for td in tds:
                dm = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", td.get_text())
                if dm:
                    datum = f"{dm.group(3)}-{dm.group(2).zfill(2)}-{dm.group(1).zfill(2)}"
                    break

            # PDF link
            pdf_url = ""
            for a in tr.find_all("a", href=lambda h: h and ".pdf" in h.lower()):
                pdf_url = a["href"]
                if not pdf_url.startswith("http"): pdf_url = BASE + pdf_url
                break

            all_links.append({
                "url": zakon_href,
                "naslov": naslov[:400],
                "datum": datum,
                "pdf_url": pdf_url,
            })
            found += 1

        log.info("    Pronađeno %d zakona (ukupno: %d)", found, len(all_links))

        if found == 0: break

        # Sledeća stranica
        next_link = soup.find("a", string=re.compile(r"»|Sledeća|Next", re.I))
        if not next_link:
            # Probaj paginacione linkove
            pager = soup.find(class_=re.compile(r"pager|pagination", re.I))
            if pager:
                current = pager.find("strong") or pager.find("span", class_="active")
                if current:
                    nxt = current.find_next_sibling("a")
                    if nxt:
                        href = nxt["href"]
                        m = re.search(r"start=(\d+)", href)
                        if m:
                            offset = int(m.group(1))
                            time.sleep(RATE_S * 0.5)
                            continue
            break

        href = next_link["href"]
        m = re.search(r"start=(\d+)", href)
        if m:
            offset = int(m.group(1))
        else:
            break

        time.sleep(RATE_S * 0.5)

    return all_links

def run(dry_run=False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    (_ROOT / "data" / "parlament").mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(str(_ROOT / "data" / "parlament" / "scraper.log"), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s | %(message)s"))
    log.addHandler(fh)

    ck = _load_ckpt()
    preuzeti = set(ck.get("preuzeti_ids", []))
    preuzeto = ck.get("preuzeto", 0)
    greske   = ck.get("greske", 0)

    log.info("═══ PARLAMENT SCRAPER — pokretanje ═══")

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        log.info("Prikupljam listu zakona...")
        zakoni = _get_zakon_links(client)
        log.info("Ukupno pronađeno zakona: %d", len(zakoni))

        if dry_run:
            print(f"\nDRY RUN: {len(zakoni)} zakona pronađeno")
            for z in zakoni[:5]:
                print(f"  {z['naslov'][:70]} ({z['datum']})")
            return

        for zakon in zakoni:
            zid = _slug(zakon["url"])
            if zid in preuzeti: continue

            out_path = OUT_DIR / f"parlament_{zid}.json"
            if out_path.exists():
                preuzeti.add(zid)
                continue

            # Preuzmi PDF ako postoji
            tekst = ""
            if zakon.get("pdf_url"):
                pdf_path = PDF_DIR / f"{zid}.pdf"
                if not pdf_path.exists():
                    r_pdf = _get(client, zakon["pdf_url"])
                    if r_pdf and b"%PDF" in r_pdf.content[:10]:
                        pdf_path.write_bytes(r_pdf.content)
                        log.info("  PDF: %s (%d KB)", zid[:40], len(r_pdf.content)//1024)
                    time.sleep(RATE_S * 0.5)

                if pdf_path.exists():
                    tekst = _extract_pdf_text(pdf_path)

            # Ako nema PDF-a, scrape-uj HTML stranicu zakona
            if not tekst and zakon.get("url"):
                r_page = _get(client, zakon["url"])
                if r_page:
                    soup = BeautifulSoup(r_page.text, "lxml")
                    content = soup.find(class_=re.compile(r"content|item", re.I)) or soup.find("main")
                    if content:
                        tekst = content.get_text(separator="\n", strip=True)[:80000]
                time.sleep(RATE_S * 0.5)

            if not tekst:
                # Sačuvaj bar metapodatke
                tekst = f"Zakon: {zakon['naslov']}"

            rec = {
                "id": f"parlament_{zid}",
                "izvor": "parlament",
                "institucija": "Narodna skupština Republike Srbije",
                "tip": "Zakon",
                "naslov": zakon["naslov"],
                "datum": zakon["datum"],
                "url": zakon["url"],
                "pdf_url": zakon.get("pdf_url", ""),
                "tekst": tekst[:150000],
                "scraped_at": _iso(),
            }
            out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            preuzeti.add(zid)
            preuzeto += 1
            log.info("  ✓ %s", zakon["naslov"][:50])

            ck.update({"preuzeto": preuzeto, "greske": greske, "preuzeti_ids": list(preuzeti), "timestamp": _iso()})
            _save_ckpt(ck)
            time.sleep(RATE_S)

    ck.update({"preuzeto": preuzeto, "greske": greske, "preuzeti_ids": list(preuzeti), "timestamp": _iso()})
    _save_ckpt(ck)
    log.info("═══ PARLAMENT ZAVRŠEN: %d zakona ═══", preuzeto)
    print(f"\nPARLAMENT: {preuzeto} zakona u {OUT_DIR}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)

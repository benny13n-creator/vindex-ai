#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — Ustavni sud Srbije scraper (PDF Bilteni)
Preuzima biltene Ustavnog suda (2012-2024) i parsuje odluke iz PDF-ova.

Pokretanje:
    python scripts/scrape_ustavni.py --dry-run
    python scripts/scrape_ustavni.py

Output: data/ustavni/odluke/{id}.json
"""

import argparse
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
import pypdf

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ustavni_scraper")

# ── Konfiguracija ──────────────────────────────────────────────────────────────
BASE     = "https://ustavni.sud.rs"
RATE_S   = 2.0

OUT_DIR  = _ROOT / "data" / "ustavni" / "odluke"
PDF_DIR  = _ROOT / "data" / "ustavni" / "pdf"
CKPT     = _ROOT / "data" / "ustavni" / "checkpoint.json"
LOG_FILE = _ROOT / "data" / "ustavni" / "scraper.log"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VindexBot/1.0; research; contact: info@vindexai.rs)",
    "Accept": "text/html,application/pdf,*/*",
    "Accept-Language": "sr-RS,sr;q=0.9",
}

# Svi bilteni — od najstarijeg ka najnovijem
BILTENI = [
    {"url": "/upload/document/bilten_1-2012-2016.pdf", "period": "2012-2016 (1)"},
    {"url": "/upload/document/bilten_2-2012-2016.pdf", "period": "2012-2016 (2)"},
    {"url": "/upload/document/bilten_2017.pdf",         "period": "2017"},
    {"url": "/upload/document/bilten_2018.pdf",         "period": "2018"},
    {"url": "/upload/document/bilten_2019.pdf",         "period": "2019"},
    {"url": "/upload/document/bilten_2020.pdf",         "period": "2020"},
    {"url": "/upload/document/bilten_2021.pdf",         "period": "2021"},
    {"url": "/upload/document/bilten_2022.pdf",         "period": "2022"},
    {"url": "/upload/document/bilten_us_2023.pdf",      "period": "2023"},
    {"url": "/upload/document/bilten_ustavnog_suda_2024.pdf", "period": "2024"},
]

# Stariji bilteni — probamo i ove
BILTENI_STARIJI = [
    {"url": "/upload/document/bilten_2008-2011.pdf",    "period": "2008-2011"},
    {"url": "/upload/document/bilten_2009-2011.pdf",    "period": "2009-2011"},
    {"url": "/upload/document/bilten_2010.pdf",         "period": "2010"},
    {"url": "/upload/document/bilten_2011.pdf",         "period": "2011"},
    {"url": "/upload/document/bilten_ustavnog_suda_2009.pdf", "period": "2009"},
    {"url": "/upload/document/bilten_ustavnog_suda_2008.pdf", "period": "2008"},
    {"url": "/upload/document/bilten_us_2025.pdf",      "period": "2025"},
    {"url": "/upload/document/bilten_ustavnog_suda_2025.pdf", "period": "2025"},
]


def _iso():
    return datetime.now(timezone.utc).isoformat()


def _load_ckpt():
    if CKPT.exists():
        return json.loads(CKPT.read_text(encoding="utf-8"))
    return {"preuzeto": 0, "bilteni_gotovi": [], "timestamp": _iso()}


def _save_ckpt(ck):
    CKPT.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")


def _download_pdf(client: httpx.Client, url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 1000:
        log.info("PDF već postoji: %s", dest.name)
        return True
    try:
        r = client.get(url, timeout=120)
        if r.status_code == 200 and b"%PDF" in r.content[:10]:
            dest.write_bytes(r.content)
            log.info("Preuzet PDF: %s (%d KB)", dest.name, len(r.content) // 1024)
            return True
        log.warning("PDF nije dostupan: %s (HTTP %d)", url, r.status_code)
        return False
    except Exception as e:
        log.error("Greška pri preuzimanju %s: %s", url, e)
        return False


def _extract_pdf_text(pdf_path: Path) -> str:
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        pages = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                pages.append(t)
        return "\n\n".join(pages)
    except Exception as e:
        log.error("PDF parse greška (%s): %s", pdf_path.name, e)
        return ""


def _split_into_decisions(text: str, period: str) -> list[dict]:
    """
    Pokušava da podeli PDF tekst na individualne odluke.
    Ustavni sud bilteni imaju strukturu:
      - Broj predmeta: IUz-xxx/YYYY, Už-xxx/YYYY, IUo-xxx/YYYY
      - Datum
      - Izreka
      - Obrazloženje
    """
    decisions = []

    # Pattern za broj predmeta Ustavnog suda
    PATTERN = re.compile(
        r"(IU[zopal]-\s*\d+/\d{4}|Už-\s*\d+/\d{4}|IUp-\s*\d+/\d{4}|"
        r"U[žz]\s*-?\s*\d+/\d{4}|Ibz\s*-?\s*\d+/\d{4}|"
        r"IUl\s*-?\s*\d+/\d{4}|IUa\s*-?\s*\d+/\d{4})",
        re.IGNORECASE
    )

    matches = list(PATTERN.finditer(text))

    if not matches:
        # Ako nema jasnih granica, uzmi ceo tekst kao jednu stavku
        if len(text.strip()) > 200:
            decisions.append({
                "id": f"ustavni_{period.replace(' ', '_').replace('/', '_')}_full",
                "izvor": "ustavni_sud_bilten",
                "sud": "Ustavni sud Srbije",
                "period": period,
                "broj_predmeta": "",
                "tip_odluke": "",
                "datum": "",
                "tekst": text[:20000],
                "scraped_at": _iso(),
            })
        return decisions

    log.info("  Pronađeno %d odluka u periodu %s", len(matches), period)

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()

        if len(chunk) < 100:
            continue

        broj = match.group(0).strip()
        broj = re.sub(r"\s+", " ", broj)

        # Datum u tekstu
        datum = ""
        dm = re.search(r"(\d{1,2})[.\s]+(\d{1,2})[.\s]+(\d{4})", chunk)
        if dm:
            datum = f"{dm.group(3)}-{dm.group(2).zfill(2)}-{dm.group(1).zfill(2)}"

        # Tip odluke
        tip = ""
        tm = re.search(r"(Одлука|Решење|Закључак|Odluka|Rešenje|Zaključak)", chunk[:200])
        if tm:
            tip = tm.group(1)

        safe_id = re.sub(r"[^\w]", "_", broj)[:60]
        decisions.append({
            "id": f"ustavni_{safe_id}",
            "izvor": "ustavni_sud_bilten",
            "sud": "Ustavni sud Srbije",
            "period": period,
            "broj_predmeta": broj,
            "tip_odluke": tip,
            "datum": datum,
            "tekst": chunk[:15000],
            "scraped_at": _iso(),
        })

    return decisions


def run(dry_run: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s | %(message)s"))
    log.addHandler(fh)

    ck = _load_ckpt()
    gotovi = set(ck.get("bilteni_gotovi", []))
    preuzeto = ck.get("preuzeto", 0)

    svi_bilteni = BILTENI + BILTENI_STARIJI

    log.info("═══ USTAVNI SUD SCRAPER — %d biltena ═══", len(svi_bilteni))

    if dry_run:
        print(f"Planiranih biltena: {len(svi_bilteni)}")
        print(f"Procena: 50-200 odluka po biltenu = ~{len(svi_bilteni) * 100} odluka")
        return

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for bilten in svi_bilteni:
            key = bilten["url"]
            if key in gotovi:
                log.info("Preskačem (gotov): %s", bilten["period"])
                continue

            full_url = BASE + bilten["url"]
            pdf_name = Path(bilten["url"]).name
            pdf_path = PDF_DIR / pdf_name

            log.info("═ Bilten: %s ═", bilten["period"])

            # Preuzmi PDF
            ok = _download_pdf(client, full_url, pdf_path)
            if not ok:
                log.warning("Bilten nije dostupan: %s", bilten["period"])
                gotovi.add(key)
                continue

            time.sleep(RATE_S)

            # Parsuj PDF
            log.info("  Parsujem PDF: %s", pdf_name)
            text = _extract_pdf_text(pdf_path)
            if not text or len(text) < 500:
                log.warning("  Prazan PDF: %s", pdf_name)
                gotovi.add(key)
                continue

            log.info("  Izvučeno %d karaktera iz PDF-a", len(text))

            # Podeli na odluke
            odluke = _split_into_decisions(text, bilten["period"])
            log.info("  Pronađeno %d odluka", len(odluke))

            # Sačuvaj svaku odluku
            for odluka in odluke:
                path = OUT_DIR / f"{odluka['id']}.json"
                if not path.exists():
                    path.write_text(
                        json.dumps(odluka, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                    preuzeto += 1

            gotovi.add(key)
            ck.update({
                "preuzeto": preuzeto,
                "bilteni_gotovi": list(gotovi),
                "timestamp": _iso(),
            })
            _save_ckpt(ck)
            log.info("  ✓ Sačuvano %d odluka (ukupno: %d)", len(odluke), preuzeto)
            time.sleep(RATE_S)

    ck.update({"preuzeto": preuzeto, "bilteni_gotovi": list(gotovi), "timestamp": _iso()})
    _save_ckpt(ck)
    log.info("═══ USTAVNI SUD ZAVRŠEN: %d odluka iz %d biltena ═══", preuzeto, len(gotovi))
    print(f"\nUSTAVNI SUD ZAVRŠEN: {preuzeto} odluka u data/ustavni/odluke/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)

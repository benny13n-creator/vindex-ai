# -*- coding: utf-8 -*-
"""
VINDEX Faza 2B — T1: Download all bilten PDFs
AS Beograd (14), AS Niš (11, excl. 2023-24), VKS (7)
10s delay between downloads. Skip + log failures.
"""
import sys, time, hashlib
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
DELAY = 10
MIN_SIZE = 20_000    # 20 KB
MAX_SIZE = 50_000_000  # 50 MB

BASE = Path(__file__).parent.parent

BILTENI = [
    # ── AS Beograd (14) ─────────────────────────────────────────────────────
    ("as_bg", "bilten_bg_01_2010.pdf",
     "https://bg.ap.sud.rs/files/Bilten%202010_1.pdf",
     "AS Beograd Bilten 1 (2010)"),
    ("as_bg", "bilten_bg_02_2011.pdf",
     "https://bg.ap.sud.rs/files/bilten%202.pdf",
     "AS Beograd Bilten 2 (2011)"),
    ("as_bg", "bilten_bg_03_2011.pdf",
     "https://bg.ap.sud.rs/files/bilten%203.pdf",
     "AS Beograd Bilten 3 (2011)"),
    ("as_bg", "bilten_bg_04_2012.pdf",
     "https://bg.ap.sud.rs/files/Bilten-4%202012.pdf",
     "AS Beograd Bilten 4 (2012)"),
    ("as_bg", "bilten_bg_05_2013.pdf",
     "https://bg.ap.sud.rs/files/Bilten_5_2013.pdf",
     "AS Beograd Bilten 5 (2013)"),
    ("as_bg", "bilten_bg_06_2014.pdf",
     "https://bg.ap.sud.rs/files/Bilten%20broj%206%20u%20elektronskoj%20formimin.pdf",
     "AS Beograd Bilten 6 (2014)"),
    ("as_bg", "bilten_bg_07_2015.pdf",
     "https://bg.ap.sud.rs/files/Bilten%20broj%207%20u%20elektronskoj%20formi.pdf",
     "AS Beograd Bilten 7 (2015)"),
    ("as_bg", "bilten_bg_08_2016.pdf",
     "https://bg.ap.sud.rs/files/Bilten%20broj%208%20u%20elektronskoj%20formi.pdf",
     "AS Beograd Bilten 8 (2016)"),
    ("as_bg", "bilten_bg_09_2017.pdf",
     "https://bg.ap.sud.rs/files/Bilten_Apelacije_BGD_9_2019min.pdf",
     "AS Beograd Bilten 9 (2017)"),
    ("as_bg", "bilten_bg_10_2018.pdf",
     "https://bg.ap.sud.rs/files/Bilten10.pdf",
     "AS Beograd Bilten 10 (2018)"),
    ("as_bg", "bilten_bg_11_2020.pdf",
     "https://bg.ap.sud.rs/files/Bilten11.pdf",
     "AS Beograd Bilten 11 (2020)"),
    ("as_bg", "bilten_bg_12_2022.pdf",
     "https://bg.ap.sud.rs/files/Bilten-Apelacije-BG-br-12.pdf",
     "AS Beograd Bilten 12 (2022)"),
    ("as_bg", "bilten_bg_13_2023.pdf",
     "https://bg.ap.sud.rs/files/BiltenApelBG13-2023.pdf",
     "AS Beograd Bilten 13 (2023)"),
    ("as_bg", "bilten_bg_14_2024.pdf",
     "https://bg.ap.sud.rs/files/Bilten%20Apel%20BG%2014-2024%20-%20provera%202-.pdf",
     "AS Beograd Bilten 14 (2024)"),

    # ── AS Niš (11, excl. 2023-24 already done) ─────────────────────────────
    ("as_nis", "bilten_nis_2022.pdf",
     "http://www.ni.ap.sud.rs/resources/files/Bilten%202022%20Nis.pdf",
     "AS Nis Bilten 2022"),
    ("as_nis", "bilten_nis_2021.pdf",
     "http://www.ni.ap.sud.rs/resources/files/Bilten%202021%20Nis.pdf",
     "AS Nis Bilten 2021"),
    ("as_nis", "bilten_nis_2020.pdf",
     "http://www.ni.ap.sud.rs/resources/files/Bilten%202020%20Nis.pdf",
     "AS Nis Bilten 2020"),
    ("as_nis", "bilten_nis_2019.pdf",
     "http://www.ni.ap.sud.rs/resources/files/Bilten%202019%20Nis.pdf",
     "AS Nis Bilten 2019"),
    ("as_nis", "bilten_nis_2018.pdf",
     "http://www.ni.ap.sud.rs/resources/files/Bilten%202018%20Nis.pdf",
     "AS Nis Bilten 2018"),
    ("as_nis", "bilten_nis_2017.pdf",
     "http://www.ni.ap.sud.rs/resources/files/Bilten%202017%20Nis.pdf",
     "AS Nis Bilten 2017"),
    ("as_nis", "bilten_nis_2014.pdf",
     "http://www.ni.ap.sud.rs/resources/files/Bilten%202014%20Nis.pdf",
     "AS Nis Bilten 2014"),
    ("as_nis", "bilten_nis_2013.pdf",
     "http://www.ni.ap.sud.rs/resources/files/Bilten%202013%20Nis.pdf",
     "AS Nis Bilten 2013"),
    ("as_nis", "bilten_nis_2012.pdf",
     "http://www.ni.ap.sud.rs/resources/files/Bilten%202012%20Nis.pdf",
     "AS Nis Bilten 2012"),
    ("as_nis", "bilten_nis_2011.pdf",
     "http://www.ni.ap.sud.rs/resources/files/Bilten%202011%20Nis.pdf",
     "AS Nis Bilten 2011"),
    ("as_nis", "bilten_nis_2010.pdf",
     "http://www.ni.ap.sud.rs/resources/files/Bilten%202010%20Nis.pdf",
     "AS Nis Bilten 2010"),

    # ── VKS 2023-3 through 2025-3 (7) ───────────────────────────────────────
    ("vks", "bilten_vks_2023_3.pdf",
     "https://www.vrh.sud.rs/sites/default/files/attachments/Bilten%20VS%203-2023.pdf",
     "VKS Bilten 2023-3"),
    ("vks", "bilten_vks_2024_1.pdf",
     "https://www.vrh.sud.rs/sites/default/files/attachments/Bilten%201-2024.pdf",
     "VKS Bilten 2024-1"),
    ("vks", "bilten_vks_2024_2.pdf",
     "https://www.vrh.sud.rs/sites/default/files/attachments/Bilten%202-2024.pdf",
     "VKS Bilten 2024-2"),
    ("vks", "bilten_vks_2024_3.pdf",
     "https://www.vrh.sud.rs/sites/default/files/attachments/Bilten%203-2024.pdf",
     "VKS Bilten 2024-3"),
    ("vks", "bilten_vks_2025_1.pdf",
     "https://www.vrh.sud.rs/sites/default/files/files/Bilteni/VrhovniSud/Bilten-VS-2025-1.pdf",
     "VS Bilten 2025-1"),
    ("vks", "bilten_vks_2025_2.pdf",
     "https://www.vrh.sud.rs/sites/default/files/files/Bilteni/VrhovniSud/Bilten-VS-2025-2.pdf",
     "VS Bilten 2025-2"),
    ("vks", "bilten_vks_2025_3.pdf",
     "https://www.vrh.sud.rs/sites/default/files/files/Bilteni/VrhovniSud/Bilten-VS-2025-3.pdf",
     "VS Bilten 2025-3"),
]


def is_valid_pdf(data: bytes) -> bool:
    return data[:4] == b'%PDF'


def download_all():
    results = {"ok": [], "skip": [], "already": []}
    total = len(BILTENI)

    for i, (subdir, filename, url, label) in enumerate(BILTENI):
        out_path = BASE / "data/sudska_praksa/raw_bilteni" / subdir / filename
        print(f"\n[{i+1:02d}/{total}] {label}")
        print(f"  URL: {url}")
        print(f"  OUT: {out_path}")

        if out_path.exists():
            kb = out_path.stat().st_size / 1024
            if kb > MIN_SIZE / 1024:
                print(f"  SKIP (already exists, {kb:.0f} KB)")
                results["already"].append((label, filename, kb))
                continue

        # Polite delay
        if i > 0:
            print(f"  Waiting {DELAY}s...", flush=True)
            time.sleep(DELAY)

        try:
            with httpx.Client(headers={"User-Agent": UA, "Accept": "application/pdf,*/*"},
                              timeout=60, follow_redirects=True) as client:
                r = client.get(url)

            print(f"  HTTP {r.status_code} | {len(r.content):,} bytes | "
                  f"Content-Type: {r.headers.get('content-type','?')[:40]}")

            if r.status_code != 200:
                print(f"  [SKIP] Bad status {r.status_code}")
                results["skip"].append((label, filename, f"HTTP {r.status_code}"))
                continue

            if len(r.content) < MIN_SIZE:
                print(f"  [SKIP] Too small ({len(r.content)} bytes < {MIN_SIZE})")
                results["skip"].append((label, filename, f"too small: {len(r.content)}B"))
                continue

            if len(r.content) > MAX_SIZE:
                print(f"  [SKIP] Too large ({len(r.content):,} bytes)")
                results["skip"].append((label, filename, f"too large"))
                continue

            if not is_valid_pdf(r.content):
                print(f"  [SKIP] Not a valid PDF (magic bytes: {r.content[:8]!r})")
                results["skip"].append((label, filename, "not a PDF"))
                continue

            out_path.write_bytes(r.content)
            kb = len(r.content) / 1024
            print(f"  [OK] Saved {kb:.0f} KB")
            results["ok"].append((label, filename, kb))

        except Exception as exc:
            print(f"  [SKIP] Exception: {exc}")
            results["skip"].append((label, filename, str(exc)[:80]))

    # Summary
    print(f"\n{'='*60}")
    print(f"DOWNLOAD SUMMARY")
    print(f"{'='*60}")
    print(f"  OK       : {len(results['ok'])}")
    print(f"  Already  : {len(results['already'])}")
    print(f"  Skipped  : {len(results['skip'])}")
    print(f"  Total    : {len(results['ok']) + len(results['already'])}/{total} available")

    if results["skip"]:
        print(f"\n  Failed downloads:")
        for label, fn, reason in results["skip"]:
            print(f"    {label}: {reason}")

    return results


if __name__ == "__main__":
    download_all()

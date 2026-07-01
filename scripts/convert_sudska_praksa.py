#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — Konvertor stare sudska_praksa kolekcije u standardni format.

Stara kolekcija (raw/ i raw_bilteni/) koristi drugacije field nazive:
  - raw_text -> tekst
  - decision_id -> id
  - court -> sud

Output: data/sudska_praksa_converted/odluke/{id}.json
Format: isti kao ECHR/KZK (spreman za ingest_sudskapraksa.py)

Pokretanje:
    python scripts/convert_sudska_praksa.py
"""

import json
import sys
import re
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
RAW_DIR    = ROOT / "data" / "sudska_praksa" / "raw"
BILTENI_DIR = ROOT / "data" / "sudska_praksa" / "raw_bilteni"
OUT_DIR    = ROOT / "data" / "sudska_praksa_converted" / "odluke"

MIN_TEKST = 80
_iso = lambda: datetime.now(timezone.utc).isoformat()


def _safe_id(raw_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", str(raw_id))
    safe = re.sub(r"_+", "_", safe).strip("_")
    return f"sp_old_{safe[:80]}"


def convert_raw(rec: dict) -> dict | None:
    """Konvertuj raw format u standardni."""
    tekst = (rec.get("raw_text") or rec.get("tekst") or "").strip()
    if len(tekst) < MIN_TEKST:
        return None
    raw_id = rec.get("decision_id") or rec.get("id") or ""
    return {
        "id":        _safe_id(raw_id),
        "izvor":     "vrh_sud_bilten",
        "sud":       rec.get("court") or rec.get("sud") or "Vrhovni sud Srbije",
        "materija":  rec.get("matter") or rec.get("materija") or "",
        "broj":      rec.get("decision_number") or rec.get("broj") or raw_id,
        "datum":     rec.get("decision_date") or rec.get("datum") or "",
        "naslov":    rec.get("heading") or rec.get("naslov") or raw_id,
        "tekst":     tekst,
        "url":       rec.get("source_url") or rec.get("url") or "",
        "izvor_tip": "bilten",
        "scraped_at": rec.get("scraped_at") or _iso(),
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    converted = 0
    skipped_short = 0
    skipped_exists = 0
    errors = 0

    # 1. RAW kategorije (gradjanska, krivicna, upravna, zastitaprava)
    raw_categories = [d for d in RAW_DIR.iterdir() if d.is_dir() and not d.name.startswith("_")]
    print(f"RAW kategorije: {[d.name for d in raw_categories]}")

    for cat_dir in raw_categories:
        for fpath in sorted(cat_dir.glob("*.json")):
            try:
                rec = json.loads(fpath.read_text(encoding="utf-8"))
                out = convert_raw(rec)
                if out is None:
                    skipped_short += 1
                    continue
                out_path = OUT_DIR / f"{out['id']}.json"
                if out_path.exists():
                    skipped_exists += 1
                    continue
                out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
                converted += 1
            except Exception as e:
                errors += 1

    # 2. BILTENI (raw_bilteni/**/*.json)
    for fpath in sorted(BILTENI_DIR.rglob("*.json")):
        try:
            rec = json.loads(fpath.read_text(encoding="utf-8"))
            out = convert_raw(rec)
            if out is None:
                skipped_short += 1
                continue
            # Dodaj bilten source info
            out["izvor_tip"] = "bilten"
            out["bilten_source"] = str(rec.get("bilten_source") or fpath.parent.name)
            out_path = OUT_DIR / f"{out['id']}.json"
            if out_path.exists():
                skipped_exists += 1
                continue
            out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            converted += 1
        except Exception as e:
            errors += 1

    total = len(list(OUT_DIR.glob("*.json")))
    print(f"\n=== KONVERZIJA ZAVRSENA ===")
    print(f"Konvertovano:     {converted}")
    print(f"Vec postoji:      {skipped_exists}")
    print(f"Prekratko (<{MIN_TEKST}):  {skipped_short}")
    print(f"Greske:           {errors}")
    print(f"Ukupno u out_dir: {total}")
    print(f"Lokacija: {OUT_DIR}")


if __name__ == "__main__":
    main()

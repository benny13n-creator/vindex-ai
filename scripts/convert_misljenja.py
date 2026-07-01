#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, json, re
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
src = ROOT / "data" / "misljenja" / "raw"
out_dir = ROOT / "data" / "misljenja_converted" / "odluke"
out_dir.mkdir(parents=True, exist_ok=True)

conv = 0
skip = 0
for f in src.glob("*.json"):
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        tekst = (d.get("tekst") or "").strip()
        if len(tekst) < 80:
            skip += 1
            continue
        safe_id = re.sub(r"[^A-Za-z0-9_\-]", "_", d.get("broj", "") or f.stem)[:80]
        rec = {
            "id": f"misljenje_{safe_id}",
            "izvor": "misljenje_ministarstvo",
            "sud": d.get("ministarstvo", "Ministarstvo"),
            "materija": d.get("oblast", ""),
            "naslov": d.get("naziv", ""),
            "datum": d.get("datum", ""),
            "tekst": tekst,
        }
        out_path = out_dir / f"{rec['id']}.json"
        out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        conv += 1
    except Exception as e:
        print("ERR:", e)

print(f"Konvertovano: {conv}, preskoceno: {skip}")
print(f"Lokacija: {out_dir}")

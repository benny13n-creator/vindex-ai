#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Konvertuje izvore prikupljene fork agentom u standardni Vindex format (id + tekst).
"""
import json, re, sys
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT    = Path(__file__).parent.parent
MIN_TXT = 150


def _iso():
    return datetime.now(timezone.utc).isoformat()


def safe_id(raw: str, prefix: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_\-]", "_", str(raw))[:60]
    return f"{prefix}_{s}"


def convert_sudskapraksa_sud():
    """sudskapraksa_sud/odluke -> sudskapraksa_sud_converted/odluke"""
    src = ROOT / "data" / "sudskapraksa_sud" / "odluke"
    out = ROOT / "data" / "sudskapraksa_sud_converted" / "odluke"
    out.mkdir(parents=True, exist_ok=True)

    conv = skip = err = 0
    for f in src.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            tekst = (d.get("tekst") or "").strip()
            if len(tekst) < MIN_TXT or tekst.startswith("[SKENIRAN"):
                skip += 1; continue

            raw_id = d.get("node_id") or d.get("broj_predmeta") or f.stem
            rec = {
                "id":       safe_id(raw_id, "sp_sud"),
                "izvor":    d.get("izvor", "sudskapraksa_sud"),
                "sud":      d.get("sud", "Vrhovni kasacioni sud"),
                "naslov":   d.get("naslov", ""),
                "datum":    d.get("datum", "")[:10] if d.get("datum") else "",
                "materija": d.get("oblast_prava", ""),
                "broj":     d.get("broj_predmeta", ""),
                "tekst":    tekst,
                "url":      d.get("url", ""),
                "scraped_at": _iso(),
            }
            (out / f"{rec['id']}.json").write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            conv += 1
        except Exception as e:
            err += 1
    print(f"sudskapraksa_sud: {conv} konv, {skip} preskoceno, {err} gresaka -> {out}")
    return conv


def convert_ombudsman_apv():
    """ombudsman_apv/misljenja -> ombudsman_apv_converted/odluke"""
    src = ROOT / "data" / "ombudsman_apv" / "misljenja"
    out = ROOT / "data" / "ombudsman_apv_converted" / "odluke"
    out.mkdir(parents=True, exist_ok=True)

    conv = skip = err = 0
    for i, f in enumerate(src.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            tekst = (d.get("tekst") or "").strip()
            if len(tekst) < MIN_TXT:
                skip += 1; continue

            rec = {
                "id":       safe_id(f.stem, "apv"),
                "izvor":    "ombudsman_apv",
                "sud":      "Pokrajinski zaštitnik gradjana — ombudsman APV",
                "naslov":   d.get("naslov", "")[:200],
                "tekst":    tekst,
                "url":      d.get("url", ""),
                "scraped_at": _iso(),
            }
            (out / f"{rec['id']}.json").write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            conv += 1
        except Exception as e:
            err += 1
    print(f"ombudsman_apv: {conv} konv, {skip} preskoceno, {err} gresaka -> {out}")
    return conv


def convert_apelacioni_bilteni():
    """apelacioni_bilteni/fajlovi -> apelacioni_bilteni_converted/odluke"""
    src = ROOT / "data" / "apelacioni_bilteni" / "fajlovi"
    out = ROOT / "data" / "apelacioni_bilteni_converted" / "odluke"
    out.mkdir(parents=True, exist_ok=True)

    conv = skip = err = 0
    for f in src.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            tekst = (d.get("tekst") or "").strip()
            if len(tekst) < MIN_TXT:
                skip += 1; continue

            rec = {
                "id":       safe_id(f.stem, "ap_bilten"),
                "izvor":    "apelacioni_bilteni",
                "sud":      d.get("sud", "Apelacioni sud"),
                "naslov":   d.get("naslov", ""),
                "tekst":    tekst,
                "url":      d.get("url", ""),
                "scraped_at": _iso(),
            }
            (out / f"{rec['id']}.json").write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            conv += 1
        except Exception as e:
            err += 1
    print(f"apelacioni_bilteni: {conv} konv, {skip} preskoceno, {err} gresaka -> {out}")
    return conv


if __name__ == "__main__":
    print("=== KONVERZIJA FORK IZVORA ===")
    total = 0
    total += convert_sudskapraksa_sud()
    total += convert_ombudsman_apv()
    total += convert_apelacioni_bilteni()
    print(f"\nUkupno konvertovano: {total}")

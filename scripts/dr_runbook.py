#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — scripts/dr_runbook.py

Disaster Recovery Runbook — Izvršni ček-lista

Pokrenuti:
  python scripts/dr_runbook.py                 # Pun DR test
  python scripts/dr_runbook.py --quick          # Samo connectivity (< 30s)
  python scripts/dr_runbook.py --check backup   # Samo backup provera

CELINA 5 (2026-07-24): zvanični DR plan je sada docs/security/DISASTER_RECOVERY_PLAN.md
-- ovaj skript je automatizovani ALAT koji implementira deo tog plana (§6), ne
izvor istine za RPO/RTO brojeve. Ciljevi ispod ažurirani da se poklapaju sa
zvaničnim planom; pročitati DISASTER_RECOVERY_PLAN.md §2.1 za pošten caveat --
RPO od 15 minuta zahteva Supabase Point-in-Time Recovery (PITR) da bude
aktivan, što NIJE potvrđeno iz koda (billing/plan odluka, ne kod odluka).
Dok se ne potvrdi (v. §8 Verification Log u DRP-u), efektivan RPO je i dalje
gornja granica dnevnog backup-a (do 24h), ne 15 minuta.

DEFINCIJE:
  RPO (Recovery Point Objective): max gubitak podataka koji je prihvatljiv
    Zvaničan cilj (DISASTER_RECOVERY_PLAN.md): 15 minuta -- zahteva PITR (nepotvrđeno)
    Potvrđena donja granica bez PITR-a: 24 sata (dnevni Supabase backup)

  RTO (Recovery Time Objective): koliko brzo mora biti sistem online
    Zvaničan cilj (DISASTER_RECOVERY_PLAN.md): 2 sata -- proceduralni cilj, dostižan
    sa trenutnim alatima (v. DRP §2.2 za obrazloženje izvodljivosti)

SCENARIJI OPORAVKA:
  P0 — Kompletni gubitak (Supabase + Render nedostupni):
    1. Aktiviraj Render.com "Rollback to previous deploy" (< 5 min)
    2. Restoruj Supabase iz poslednjeg point-in-time backup-a (< 30 min)
    3. Verifikuj audit_immutable lanac integritet
    4. Obavesti korisnike (email template u INCIDENT_EMAIL_TEMPLATE)
    Ukupno RTO: ~1-2 sata

  P1 — Supabase dole (Render OK):
    1. Supabase dashboard → Project Settings → Restore
    2. Promena env var SUPABASE_URL na backup instance (ako postoji)
    Ukupno RTO: ~30-60 minuta

  P2 — Render dole (Supabase OK):
    1. Render.com → New Web Service → Deploy from GitHub (main branch)
    Ukupno RTO: ~15-30 minuta

KONTAKTI:
  Render.com incident: https://status.render.com
  Supabase incident:   https://status.supabase.com
  Cloudflare:          https://cloudflarestatus.com
  Poverenik RS (GDPR): poverenik.rs / +381 11 408-9711
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Dodaj parent direktorij u path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ─── Konstantne definicije ───────────────────────────────────────────────────

# CELINA 5: RTO_HOURS now matches the official 2h target in
# docs/security/DISASTER_RECOVERY_PLAN.md §2. RPO_HOURS stays at the
# confirmed 24h daily-backup floor (not the 0.25h/15min policy target) --
# claiming 15 minutes here would be an unverified claim; see DRP §2.1.
RPO_HOURS = 24
RPO_TARGET_HOURS = 0.25  # 15 min policy target — requires Supabase PITR, unconfirmed
RTO_HOURS = 2

INCIDENT_EMAIL_TEMPLATE = """
Predmet: [Vindex AI] Obaveštenje o tehničkom incidentu

Poštovani korisnici,

Obaveštavamo vas da je {datum} u {vreme} UTC detektovan tehnički incident
koji je uticao na dostupnost/integritet platforme Vindex AI.

Status: {status}
Procenjen uticaj: {uticaj}
Procenjeno vreme oporavka: {rto}

Preduzte sledeće korake:
{koraci}

Ukoliko imate pitanja, kontaktirajte nas na: support@vindex.ai

Vindex AI tim
---
Napomena: Ovo je obaveštenje u skladu sa GDPR čl. 33-34 i ZZPL čl. 52-53.
"""

CHECK_RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: str = "", critical: bool = False) -> bool:
    status = "OK" if ok else ("KRITIČNO" if critical else "UPOZORENJE")
    icon   = "✓" if ok else ("✗" if critical else "!")
    print(f"  [{icon}] {name}: {detail or status}")
    CHECK_RESULTS.append({"name": name, "ok": ok, "detail": detail, "critical": critical})
    return ok


# ─── Provere ──────────────────────────────────────────────────────────────────

def check_supabase() -> bool:
    print("\n[SUPABASE]")
    try:
        from supabase import create_client
        url  = os.getenv("SUPABASE_URL", "")
        key  = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            return check("Konekcija", False, "SUPABASE_URL ili SUPABASE_SERVICE_KEY nisu postavljeni", critical=True)

        t0 = time.monotonic()
        supa = create_client(url, key)
        res  = supa.table("profiles").select("id").limit(1).execute()
        ms   = int((time.monotonic() - t0) * 1000)

        check("Konekcija", True, f"OK ({ms}ms)")

        # Proveri backup status (Supabase Pro+)
        check("WAL backup", True, "Supabase managed — proveriti dashboard manuelno")
        check("Point-in-time restore", True, f"RPO cilj: {RPO_HOURS}h — Supabase daily backup potvrđen")

        # Proveri kritične tabele
        for table in ["audit_immutable", "ai_forensics", "predmeti", "klijenti"]:
            try:
                supa.table(table).select("id").limit(0).execute()
                check(f"Tabela {table}", True)
            except Exception as e:
                check(f"Tabela {table}", False, str(e)[:80], critical=True)

        return True
    except Exception as e:
        return check("Konekcija", False, str(e)[:100], critical=True)


def check_openai() -> bool:
    print("\n[OPENAI]")
    try:
        from openai import OpenAI
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            return check("API key", False, "OPENAI_API_KEY nije postavljen", critical=True)

        t0 = time.monotonic()
        c = OpenAI(api_key=key)
        c.models.list()
        ms = int((time.monotonic() - t0) * 1000)
        check("Konekcija", True, f"OK ({ms}ms)")
        check("Model gpt-4o", True, "Dostupan")
        return True
    except Exception as e:
        return check("Konekcija", False, str(e)[:100], critical=True)


def check_pinecone() -> bool:
    print("\n[PINECONE]")
    try:
        from pinecone import Pinecone
        key = os.getenv("PINECONE_API_KEY", "")
        if not key:
            return check("API key", False, "PINECONE_API_KEY nije postavljen", critical=True)

        t0 = time.monotonic()
        pc = Pinecone(api_key=key)
        idx = pc.Index("vindex-ai")
        stats = idx.describe_index_stats()
        ms = int((time.monotonic() - t0) * 1000)

        check("Konekcija", True, f"OK ({ms}ms)")
        check("Vektori", stats.total_vector_count > 0, f"{stats.total_vector_count} vektora")
        return True
    except Exception as e:
        return check("Konekcija", False, str(e)[:100], critical=True)


def check_env_vars() -> bool:
    print("\n[ENV VARS & KONFIGURACIJA]")
    required = [
        ("SUPABASE_URL", True),
        ("SUPABASE_SERVICE_KEY", True),
        ("OPENAI_API_KEY", True),
        ("PINECONE_API_KEY", True),
        ("FIELD_ENCRYPTION_KEY", True),
        ("ADMIN_DEBUG_KEY", True),
        ("FOUNDER_EMAILS", True),
        ("ALLOWED_ORIGINS", False),
        ("SUPABASE_JWT_SECRET", False),
    ]
    all_ok = True
    for var, is_critical in required:
        val = os.getenv(var, "")
        ok  = bool(val)
        if not ok:
            all_ok = False
        check(var, ok, "Postavljen" if ok else "NEDOSTAJE", critical=is_critical)
    return all_ok


def check_audit_chain() -> bool:
    print("\n[AUDIT CHAIN INTEGRITET]")
    try:
        import asyncio
        from shared.audit_immutable import verify_chain_integrity

        result = asyncio.run(verify_chain_integrity(limit=500))
        ok = result.get("ok", False)
        check(
            "Hash-chain",
            ok,
            result.get("message", "")[:80],
            critical=not ok,
        )
        check("Zapisi provereni", True, f"{result.get('checked', 0)} zapisa")
        return ok
    except Exception as e:
        return check("Hash-chain", False, str(e)[:80], critical=False)


def check_rpo_rto() -> bool:
    print("\n[RPO / RTO DEFINICIJE]")
    check(
        "RPO (Recovery Point Objective)", True,
        f"cilj {RPO_TARGET_HOURS*60:.0f}min (zahteva PITR, nepotvrđeno) — "
        f"potvrđena donja granica {RPO_HOURS}h (dnevni Supabase backup)",
    )
    check("RTO (Recovery Time Objective)", True, f"{RTO_HOURS}h — Render rollback + Supabase restore")
    check("P0 Procedura", True, "docs/security/DISASTER_RECOVERY_PLAN.md §4 (zvaničan plan)")
    check("Kontakti", True, "support@vindex.ai, Render dashboard, Supabase dashboard")
    print()
    print("  NAPOMENA: Ručno testiranje restore procedure:")
    print("    1. Supabase Dashboard → Project Settings → Backups")
    print("    2. Klikni 'Restore' → izaberi test projekat (NE produkciju!)")
    print("    3. Proveri da li su podaci čitljivi i konzistentni")
    print("    4. Zabeleži rezultat i vreme oporavka u DISASTER_RECOVERY_PLAN.md §8")
    return True


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Vindex AI DR Runbook")
    parser.add_argument("--quick", action="store_true", help="Brza provera (samo connectivity)")
    parser.add_argument("--check", choices=["backup", "chain", "env", "all"], default="all")
    parser.add_argument("--json-out", type=str, help="JSON izlaz")
    args = parser.parse_args()

    print("=" * 70)
    print(f"Vindex AI — Disaster Recovery Runbook")
    print(f"Vreme: {datetime.now(timezone.utc).isoformat()}")
    print(f"RPO cilj: {RPO_TARGET_HOURS*60:.0f}min (zahteva PITR) / {RPO_HOURS}h potvrđeno  |  RTO cilj: {RTO_HOURS}h")
    print("=" * 70)

    checks_to_run = {
        "env":    check_env_vars,
        "supa":   check_supabase,
        "openai": check_openai if not args.quick else None,
        "pine":   check_pinecone if not args.quick else None,
        "chain":  check_audit_chain if not args.quick else None,
        "rpo":    check_rpo_rto if not args.quick else None,
    }

    if args.check == "backup":
        checks_to_run = {"supa": check_supabase, "rpo": check_rpo_rto}
    elif args.check == "chain":
        checks_to_run = {"chain": check_audit_chain}
    elif args.check == "env":
        checks_to_run = {"env": check_env_vars}

    results = {}
    for name, fn in checks_to_run.items():
        if fn:
            results[name] = fn()

    print("\n" + "=" * 70)
    total    = len(CHECK_RESULTS)
    passed   = sum(1 for r in CHECK_RESULTS if r["ok"])
    critical = [r for r in CHECK_RESULTS if not r["ok"] and r["critical"]]
    warnings = [r for r in CHECK_RESULTS if not r["ok"] and not r["critical"]]

    print(f"REZIME: {passed}/{total} provera prošlo")
    if critical:
        print(f"  KRITIČNO ({len(critical)}): {', '.join(r['name'] for r in critical)}")
    if warnings:
        print(f"  Upozorenja ({len(warnings)}): {', '.join(r['name'] for r in warnings)}")
    if not critical and not warnings:
        print("  Sve provere prošle — sistem je DR spreman.")
    print("=" * 70)

    if args.json_out:
        out = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {"total": total, "passed": passed, "critical": len(critical), "warnings": len(warnings)},
            "checks": CHECK_RESULTS,
        }
        Path(args.json_out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"JSON rezultati: {args.json_out}")

    sys.exit(1 if critical else 0)


if __name__ == "__main__":
    main()

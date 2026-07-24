#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — scripts/verify_backup_restore.py

Backup Restore Verification Drill (Celina 5, 2026-07-24)

Implements §6 of docs/security/DISASTER_RECOVERY_PLAN.md — the "structural
soundness" check that plain connectivity (scripts/dr_runbook.py) does not
cover on its own. Produces a timestamped, HMAC-signed JSON report
(backup_restore_verification.json) suitable for the DRP §8 evidence log.

WHAT THIS SCRIPT DOES NOT DO — read before relying on it:
  It does NOT trigger an actual Supabase point-in-time restore. There is no
  safe way to script a real destructive restore against a live project
  without real risk of restoring the WRONG target (production vs. test) --
  that action stays a deliberate, human-confirmed step in the Supabase
  Dashboard (DRP §4.2), on purpose. What this script DOES verify, read-only,
  against whatever database it is pointed at:
    1. Every table a restore must bring back actually exists and is queryable.
    2. Row counts are sane (not zero for tables that should never be empty
       in a live system with any real usage).
    3. The audit_immutable hash-chain is internally consistent (the same
       check used for tamper detection doubles as a restore-integrity check
       -- a truncated/corrupted restore breaks the chain the same way
       tampering would, see DRP §4.3 for why a break AT the restore boundary
       is expected and a break elsewhere is not).
    4. A representative cross-table query (join) succeeds, as a basic
       referential-sanity smoke test.
    5. Query latency is captured, as an input to RTO planning (DRP §2.2).

  Run this against a REAL restored database (a Supabase "restore to new
  project" target, or a staging copy) to actually verify a restore drill.
  Run it against production on a schedule (DRP §6: monthly) as a standing
  structural-health check -- in that mode it is not verifying "did the
  restore work" (nothing was restored) but "if we had to restore right now,
  would we recognize a corrupt/incomplete result" by having a known-good
  baseline of what "healthy" looks like.

Usage:
  python scripts/verify_backup_restore.py                 # full drill, writes JSON report
  python scripts/verify_backup_restore.py --quick          # connectivity + chain only
  python scripts/verify_backup_restore.py --out custom.json
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ─── Konfiguracija ────────────────────────────────────────────────────────────

DEFAULT_OUT = "backup_restore_verification.json"

# Kriticne tabele koje MORAJU postojati i biti upitljive posle svakog restore-a.
# NAPOMENA: "min_expected_rows=0" znaci "sme biti prazna" (npr. novoj instalaciji) --
# ne testira se protiv fiksnog broja jer se broj redova legitimno menja svakog dana.
CRITICAL_TABLES: list[tuple[str, bool]] = [
    # (naziv, sme_biti_prazna)
    ("profiles",          False),
    ("predmeti",          True),
    ("klijenti",          True),
    ("audit_immutable",   True),
    ("billing_entries",   True),
    ("predmet_dokumenti", True),
    ("security_events",   True),
    ("ai_forensics",      True),
]

CHECK_RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: str = "", critical: bool = False) -> bool:
    status = "OK" if ok else ("KRITICNO" if critical else "UPOZORENJE")
    icon = "[OK]" if ok else ("[X]" if critical else "[!]")
    print(f"  {icon} {name}: {detail or status}")
    CHECK_RESULTS.append({
        "name": name, "ok": ok, "detail": detail, "critical": critical,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })
    return ok


# ─── Provere ──────────────────────────────────────────────────────────────────

def check_connectivity(supa) -> dict:
    print("\n[1/5] KONEKTIVNOST")
    t0 = time.monotonic()
    try:
        supa.table("profiles").select("id").limit(1).execute()
        ms = int((time.monotonic() - t0) * 1000)
        check("Supabase konekcija", True, f"OK ({ms}ms)")
        return {"ok": True, "latency_ms": ms}
    except Exception as e:
        check("Supabase konekcija", False, str(e)[:150], critical=True)
        return {"ok": False, "latency_ms": None, "error": str(e)[:200]}


def check_critical_tables(supa) -> dict:
    print("\n[2/5] KRITICNE TABELE — postojanje + row count sanity")
    results: dict[str, dict] = {}
    for table, allow_empty in CRITICAL_TABLES:
        try:
            r = supa.table(table).select("id", count="exact").limit(1).execute()
            count = r.count if r.count is not None else len(r.data or [])
            ok = allow_empty or count > 0
            check(
                f"Tabela {table}", ok,
                f"{count} redova" + ("" if ok else " — OCEKIVANO NEPRAZNA"),
                critical=not allow_empty and not ok,
            )
            results[table] = {"exists": True, "row_count": count, "ok": ok}
        except Exception as e:
            check(f"Tabela {table}", False, str(e)[:120], critical=True)
            results[table] = {"exists": False, "row_count": None, "ok": False, "error": str(e)[:200]}
    return results


def check_audit_chain() -> dict:
    print("\n[3/5] AUDIT CHAIN INTEGRITET (audit_immutable hash-lanac)")
    try:
        import asyncio
        from shared.audit_immutable import verify_chain_integrity

        result = asyncio.run(verify_chain_integrity(limit=1000))
        ok = result.get("ok", False)
        check(
            "Hash-chain integritet", ok,
            result.get("message", "")[:120],
            critical=not ok,
        )
        check("Zapisi provereni", True, f"{result.get('checked', 0)} zapisa")
        return result
    except Exception as e:
        check("Hash-chain integritet", False, str(e)[:150], critical=False)
        return {"ok": False, "checked": 0, "broken_at_seq": None, "message": str(e)[:200]}


def check_referential_sanity(supa) -> dict:
    print("\n[4/5] REFERENCIJALNI SMOKE TEST (cross-table upit)")
    try:
        t0 = time.monotonic()
        r = (
            supa.table("predmeti")
            .select("id, naziv, predmet_klijenti(klijent_id)")
            .limit(5)
            .execute()
        )
        ms = int((time.monotonic() - t0) * 1000)
        ok = True  # ne pada = upit strukturno validan (join postoji), prazan rezultat je i dalje OK
        check("Join predmeti <-> predmet_klijenti", ok, f"OK ({ms}ms, {len(r.data or [])} redova)")
        return {"ok": ok, "latency_ms": ms, "rows_returned": len(r.data or [])}
    except Exception as e:
        check("Join predmeti <-> predmet_klijenti", False, str(e)[:150], critical=False)
        return {"ok": False, "latency_ms": None, "error": str(e)[:200]}


def check_rto_latency_budget(connectivity: dict, referential: dict) -> dict:
    print("\n[5/5] RTO LATENCY BUDGET (informativno — v. DRP §2.2)")
    conn_ms = connectivity.get("latency_ms") or 0
    ref_ms = referential.get("latency_ms") or 0
    total_ms = conn_ms + ref_ms
    # Ne kriticno po definiciji — ovo je informativni signal za RTO planiranje,
    # ne pass/fail provera (jedan spor upit ne znaci da je restore neuspesan).
    check(
        "Ukupna latencija provera", True,
        f"{total_ms}ms (konekcija {conn_ms}ms + join {ref_ms}ms) — "
        f"zanemarljivo u odnosu na RTO cilj od 2h",
    )
    return {"total_ms": total_ms, "connectivity_ms": conn_ms, "referential_ms": ref_ms}


# ─── Potpisivanje izveštaja ───────────────────────────────────────────────────

def _sign_report(payload: dict) -> str:
    """
    HMAC-SHA256 potpis nad kanonskim JSON sadržajem izveštaja.

    Koristi FIELD_ENCRYPTION_KEY ako postoji (već postojeći produkcioni
    secret za ovu svrhu — v. security/crypto.py), inače pada nazad na
    deterministički lokalni kljuc SAMO za dev/test (jasno obeleženo u
    izveštaju kao "unsigned_dev_key" da se nikad ne pomeša sa stvarnim
    potpisom). Potpis dokazuje da report nije izmenjen POSLE generisanja --
    ne dokazuje ništa o samoj bazi, to rade provere iznad.
    """
    key = os.getenv("FIELD_ENCRYPTION_KEY", "").strip()
    key_source = "FIELD_ENCRYPTION_KEY"
    if not key:
        key = "dev-only-unsigned-fallback-key-do-not-trust"
        key_source = "unsigned_dev_key"

    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    signature = hmac.new(key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return signature, key_source


def verify_report_signature(report_path: str) -> bool:
    """Verifikuje potpis postojeceg izveštaja — za buduću proveru da izveštaj nije izmenjen."""
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    signature = report.pop("signature", None)
    key_source = report.pop("signature_key_source", None)
    expected, _ = _sign_report(report)
    return signature == expected


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Vindex AI Backup Restore Verification Drill")
    parser.add_argument("--quick", action="store_true", help="Samo konektivnost + chain (bez tabela/join)")
    parser.add_argument("--out", type=str, default=DEFAULT_OUT, help="Putanja JSON izveštaja")
    parser.add_argument("--verify-signature", type=str, default=None,
                         help="Umesto pokretanja drill-a, verifikuj potpis postojeceg izveštaja")
    args = parser.parse_args()

    if args.verify_signature:
        ok = verify_report_signature(args.verify_signature)
        print(f"Potpis {'VALIDAN' if ok else 'NEVALIDAN — izveštaj je izmenjen posle generisanja'}: {args.verify_signature}")
        sys.exit(0 if ok else 1)

    print("=" * 72)
    print("Vindex AI — Backup Restore Verification Drill")
    print(f"Vreme: {datetime.now(timezone.utc).isoformat()}")
    print("Implementira DISASTER_RECOVERY_PLAN.md §6 — struktura, ne destruktivan restore.")
    print("=" * 72)

    try:
        from supabase import create_client
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
        if not url or not key:
            print("\nKRITICNO: SUPABASE_URL ili SUPABASE_SERVICE_KEY nisu postavljeni.")
            sys.exit(1)
        supa = create_client(url, key)
    except Exception as e:
        print(f"\nKRITICNO: ne mogu da se povežem na Supabase: {e}")
        sys.exit(1)

    connectivity = check_connectivity(supa)
    chain = check_audit_chain()

    tables = {}
    referential = {"ok": None, "latency_ms": None}
    rto_budget = {}
    if not args.quick:
        tables = check_critical_tables(supa)
        referential = check_referential_sanity(supa)
        rto_budget = check_rto_latency_budget(connectivity, referential)

    total = len(CHECK_RESULTS)
    passed = sum(1 for r in CHECK_RESULTS if r["ok"])
    critical_failures = [r for r in CHECK_RESULTS if not r["ok"] and r["critical"]]
    warnings = [r for r in CHECK_RESULTS if not r["ok"] and not r["critical"]]

    print("\n" + "=" * 72)
    print(f"REZIME: {passed}/{total} provera prošlo")
    if critical_failures:
        print(f"  KRITICNO ({len(critical_failures)}): {', '.join(r['name'] for r in critical_failures)}")
    if warnings:
        print(f"  Upozorenja ({len(warnings)}): {', '.join(r['name'] for r in warnings)}")
    if not critical_failures and not warnings:
        print("  Sve provere prošle — restore bi bio strukturno zdrav.")
    print("=" * 72)

    overall_ok = len(critical_failures) == 0

    report_body = {
        "report_type": "backup_restore_verification",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "quick" if args.quick else "full",
        "overall_ok": overall_ok,
        "summary": {
            "total_checks": total,
            "passed": passed,
            "critical_failures": len(critical_failures),
            "warnings": len(warnings),
        },
        "connectivity": connectivity,
        "audit_chain": chain,
        "critical_tables": tables,
        "referential_sanity": referential,
        "rto_latency_budget": rto_budget,
        "checks": CHECK_RESULTS,
        "drp_reference": "docs/security/DISASTER_RECOVERY_PLAN.md §6",
        "signature_algorithm": "HMAC-SHA256",
    }

    # signature_algorithm mora biti u payload-u PRE potpisivanja -- polje
    # dodato POSLE _sign_report() bi bilo deo sačuvanog JSON-a ali ne i
    # dela hash-a, pa bi verify_report_signature() uvek prijavljivao
    # nevalidan potpis čak i na netaknutom izveštaju (nadjeno smoke-testom).
    signature, key_source = _sign_report(report_body)
    report_body["signature"] = signature
    report_body["signature_key_source"] = key_source

    out_path = Path(args.out)
    out_path.write_text(json.dumps(report_body, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nIzveštaj sačuvan: {out_path.resolve()}")
    print(f"Potpis: {signature[:24]}... (izvor ključa: {key_source})")
    if key_source == "unsigned_dev_key":
        print("UPOZORENJE: FIELD_ENCRYPTION_KEY nije postavljen — potpis NIJE kriptografski pouzdan (dev fallback).")

    sys.exit(0 if overall_ok else 1)


if __name__ == "__main__":
    main()

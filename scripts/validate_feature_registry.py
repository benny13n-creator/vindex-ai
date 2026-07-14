# -*- coding: utf-8 -*-
"""
Vindex AI — Feature Registry Validator (Faza 70.7)

Proverava kompletnost i konzistentnost svakog reda u živoj feature_registry
tabeli — namenjeno da se pokreće pri svakom deploy-u, pre nego što Admin
Feature Console izmene (ili buduće migracije) tiho unesu polupopunjen red.

Napomena o obimu: proverava se protiv STVARNE šeme tabele (migracije 064/065),
ne protiv Faze 70's v3 backlog predloga (display_name, icon, tags, sort_order —
ta polja NE postoje u bazi, namerno odloženo, vidi #83 BACKLOG). "naziv" kolona
već služi kao display_name. Kad se v3 polja jednog dana dodaju, ovaj validator
se proširuje — ne pre toga, jer bi inače prijavljivao 100% "missing" za polja
koja svesno još ne postoje.

Pravila i ozbiljnost:
  FATAL   — feature_key prazan/duplikat; naziv prazan; minimum_plan I addon
            oba NULL (funkcija je trajno nedostupna — niko je ne može otključati)
  WARNING — krediti > 0 a ai_model prazan (naplaćuje se, a ne zna se koji model);
            ai_model postavljen a estimated_cost_usd prazan (nema procene troška
            za profitabilnost); kategorija == 'ostalo' (nekategorisano)
  INFO    — opis prazan (nedostaje dokumentacija za Admin Console)

Upotreba:
    python scripts/validate_feature_registry.py

Exit kod: 1 ako postoji bar jedan FATAL nalaz, inače 0.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(dotenv_path=ROOT / ".env")

VALID_PLANS = {"basic", "professional", "enterprise"}
VALID_STATUS = {"ACTIVE", "BETA", "DEPRECATED", "INTERNAL", "COMING_SOON"}
VALID_VISIBLE = {"visible", "hidden", "internal", "enterprise_only"}
VALID_PRIORITY = {"HIGH", "MEDIUM", "LOW"}
VALID_FEATURE_TYPE = {"FOUNDATION", "SUBSCRIPTION", "ADDON", "INTERNAL"}


def _validate_row(row: dict) -> list[tuple[str, str]]:
    """Returns list of (severity, message) for one feature_registry row."""
    findings: list[tuple[str, str]] = []
    key = row.get("feature_key") or "<prazan feature_key>"

    if not row.get("feature_key"):
        findings.append(("FATAL", "feature_key je prazan"))
    if not row.get("naziv"):
        findings.append(("FATAL", f"[{key}] naziv je prazan"))

    minimum_plan = row.get("minimum_plan")
    addon = row.get("addon")
    if minimum_plan is None and addon is None:
        findings.append((
            "FATAL",
            f"[{key}] minimum_plan I addon su oba NULL — funkcija je trajno "
            f"nedostupna, niko je ne može otključati ni jednom tarifom ni dodatkom",
        ))
    if minimum_plan is not None and minimum_plan not in VALID_PLANS:
        findings.append(("FATAL", f"[{key}] minimum_plan='{minimum_plan}' nije validna tarifa {VALID_PLANS}"))

    krediti = row.get("krediti")
    if krediti is not None and krediti < 0:
        findings.append(("FATAL", f"[{key}] krediti={krediti} je negativan"))

    ai_model = row.get("ai_model")
    if krediti and krediti > 0 and not ai_model:
        findings.append(("WARNING", f"[{key}] krediti={krediti} > 0 ali ai_model nije postavljen"))
    if ai_model and row.get("estimated_cost_usd") is None:
        findings.append(("WARNING", f"[{key}] ai_model='{ai_model}' postavljen ali estimated_cost_usd nedostaje — nema osnove za gross profit po funkciji"))

    kategorija = row.get("kategorija")
    if not kategorija or kategorija == "ostalo":
        findings.append(("WARNING", f"[{key}] kategorija je '{kategorija}' — nekategorisano"))

    status = row.get("status")
    if status and status not in VALID_STATUS:
        findings.append(("FATAL", f"[{key}] status='{status}' nije validan {VALID_STATUS}"))

    visible = row.get("visible")
    if visible and visible not in VALID_VISIBLE:
        findings.append(("FATAL", f"[{key}] visible='{visible}' nije validan {VALID_VISIBLE}"))

    priority = row.get("priority")
    if priority and priority not in VALID_PRIORITY:
        findings.append(("FATAL", f"[{key}] priority='{priority}' nije validan {VALID_PRIORITY}"))

    if not row.get("opis"):
        findings.append(("INFO", f"[{key}] opis je prazan (dokumentacija za Admin Console)"))

    feature_type = row.get("feature_type")
    if feature_type and feature_type not in VALID_FEATURE_TYPE:
        findings.append(("FATAL", f"[{key}] feature_type='{feature_type}' nije validan {VALID_FEATURE_TYPE}"))
    if feature_type == "FOUNDATION" and krediti:
        findings.append(("WARNING", f"[{key}] feature_type=FOUNDATION ali krediti={krediti} > 0 — osnovna funkcionalnost ne bi trebalo da troši kredite"))
    if feature_type == "ADDON" and addon is None:
        findings.append(("WARNING", f"[{key}] feature_type=ADDON ali addon polje je NULL — nejasno koji dodatak otključava ovo"))

    chargeable = row.get("chargeable")
    if chargeable is False and krediti:
        findings.append(("FATAL", f"[{key}] chargeable=false ali krediti={krediti} > 0 — kontradiktorno, Registry tvrdi i da se naplaćuje i da se ne naplaćuje"))

    return findings


async def _fetch_policies() -> list[dict]:
    from shared.feature_registry import get_all_policies
    return await get_all_policies()


def main() -> int:
    try:
        policies = asyncio.run(_fetch_policies())
    except Exception as exc:
        print(f"[ERROR] Ne mogu da učitam feature_registry iz baze: {exc}", file=sys.stderr)
        return 2

    if not policies:
        print("[ERROR] feature_registry tabela je prazna ili nedostupna.", file=sys.stderr)
        return 2

    seen_keys: dict[str, int] = {}
    all_findings: list[tuple[str, str]] = []

    for row in policies:
        key = row.get("feature_key") or ""
        seen_keys[key] = seen_keys.get(key, 0) + 1
        all_findings.extend(_validate_row(row))

    for key, count in seen_keys.items():
        if count > 1:
            all_findings.append(("FATAL", f"[{key}] duplikat — pojavljuje se {count} puta u registru"))

    by_severity: dict[str, list[str]] = {"FATAL": [], "WARNING": [], "INFO": []}
    for severity, msg in all_findings:
        by_severity[severity].append(msg)

    print("=" * 78)
    print("FEATURE REGISTRY VALIDATOR")
    print("=" * 78)
    print(f"  Redova u registru:  {len(policies)}")
    print(f"  FATAL:              {len(by_severity['FATAL'])}")
    print(f"  WARNING:            {len(by_severity['WARNING'])}")
    print(f"  INFO:               {len(by_severity['INFO'])}")
    print()

    for severity in ("FATAL", "WARNING", "INFO"):
        if not by_severity[severity]:
            continue
        print("─" * 78)
        print(f"{severity}:")
        print("─" * 78)
        for msg in by_severity[severity]:
            print(f"  {msg}")
        print()

    if by_severity["FATAL"]:
        print(f"[FAIL] {len(by_severity['FATAL'])} FATAL nalaz(a). Ne sme u produkciju bez provere.")
        return 1

    print("[OK] Nema FATAL nalaza u feature_registry.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

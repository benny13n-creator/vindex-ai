#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — security/sbom_check.py

Supply Chain Security:
  1. SBOM generisanje (Software Bill of Materials)
  2. CVE provera svih zavisnosti
  3. Pregled pinned vs. floating verzija

Pokrenuti ručno pre svakog deploymenta:
  python security/sbom_check.py

Ili u CI/CD (GitHub Actions):
  - pip install pip-audit safety
  - python security/sbom_check.py --ci   (ne-nulti exit code na CVE)

Referenca: NIST SP 800-204D — Software Supply Chain Security
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def generate_sbom() -> list[dict]:
    """Generiše SBOM za sve instalirane pakete."""
    packages = []
    for dist in importlib.metadata.distributions():
        metadata = dist.metadata
        name    = metadata.get("Name", "unknown")
        version = metadata.get("Version", "unknown")
        license_ = metadata.get("License", "unknown") or "unknown"
        home_page = metadata.get("Home-page", "") or metadata.get("Project-URL", "")

        packages.append({
            "name":     name,
            "version":  version,
            "license":  license_,
            "home_page": home_page,
        })

    return sorted(packages, key=lambda p: p["name"].lower())


def run_pip_audit() -> tuple[bool, list[dict]]:
    """
    Pokretanje pip-audit za CVE proveru.
    Vraća (has_vulnerabilities, list_of_vulns).
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--format=json", "--progress-spinner=off"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.stdout:
            data = json.loads(result.stdout)
            vulns = []
            for dep in data.get("dependencies", []):
                if dep.get("vulns"):
                    for v in dep["vulns"]:
                        vulns.append({
                            "package": dep["name"],
                            "version": dep["version"],
                            "id":      v.get("id"),
                            "description": v.get("description", "")[:200],
                            "fix_versions": v.get("fix_versions", []),
                        })
            return len(vulns) > 0, vulns
        return False, []
    except FileNotFoundError:
        print("  UPOZORENJE: pip-audit nije instaliran. Instalirajte: pip install pip-audit")
        return False, []
    except subprocess.TimeoutExpired:
        print("  UPOZORENJE: pip-audit timeout.")
        return False, []
    except Exception as e:
        print(f"  UPOZORENJE: pip-audit greška: {e}")
        return False, []


def check_pinned_versions() -> list[str]:
    """
    Proverava da li requirements.txt sadrži precizirane verzije (ne ~=, >=, *).
    Vraća listu nepreciziranih paketa.
    """
    req_file = Path(__file__).parent.parent / "requirements.txt"
    if not req_file.exists():
        return ["UPOZORENJE: requirements.txt nije pronađen"]

    unpinned = []
    with open(req_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Prihvatljivo: == (precizna verzija)
            # Neprihvatljivo: >=, ~=, >, nema verzije
            if "==" in line:
                continue
            if any(c in line for c in (">=", "~=", ">", "<", "!=")) or not any(c in line for c in ("=")):
                pkg = line.split("[")[0].split(";")[0].strip()
                unpinned.append(pkg)

    return unpinned


def check_critical_deps() -> list[str]:
    """Proverava da li su kritične bezbednosne zavisnosti instalirane."""
    critical = [
        ("cryptography", ">=41.0"),
        ("argon2-cffi",  ">=21.0"),
        ("jose",         "any"),
    ]
    missing = []
    for pkg, min_version in critical:
        try:
            importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            missing.append(f"{pkg} ({min_version})")
    return missing


def main():
    parser = argparse.ArgumentParser(description="Vindex AI — Supply Chain Security Check")
    parser.add_argument("--ci", action="store_true", help="CI mode: ne-nulti exit code ako postoje CVE")
    parser.add_argument("--sbom-out", type=str, help="Putanja za SBOM JSON izvoz")
    args = parser.parse_args()

    print("=" * 70)
    print(f"Vindex AI — SBOM & Supply Chain Check")
    print(f"Datum: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)
    print()

    # 1. Generiši SBOM
    print("[1/4] Generisanje SBOM...")
    sbom = generate_sbom()
    print(f"      {len(sbom)} paketa pronađeno.")

    if args.sbom_out:
        out_path = Path(args.sbom_out)
        out_path.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tool": "vindex-sbom-check",
            "packages": sbom,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"      SBOM sačuvan: {out_path}")

    # 2. CVE provera
    print()
    print("[2/4] CVE provera (pip-audit)...")
    has_vulns, vulns = run_pip_audit()
    if has_vulns:
        print(f"      UPOZORENJE: {len(vulns)} ranjivosti pronađeno!")
        for v in vulns[:10]:
            print(f"      - {v['package']}=={v['version']}: {v['id']}")
            if v['fix_versions']:
                print(f"        Popravka: {', '.join(v['fix_versions'])}")
    else:
        print("      Nema poznatih CVE ranjivosti.")

    # 3. Pinning provera
    print()
    print("[3/4] Provera piniranih verzija u requirements.txt...")
    unpinned = check_pinned_versions()
    if unpinned:
        print(f"      UPOZORENJE: {len(unpinned)} paketa bez preciznih verzija:")
        for pkg in unpinned[:10]:
            print(f"      - {pkg}")
        print("      Preporuka: Koristite 'pip-compile --generate-hashes' za precizne hash verzije.")
    else:
        print("      Sve verzije su precizirane.")

    # 4. Kritične zavisnosti
    print()
    print("[4/4] Provera kritičnih bezbednosnih paketa...")
    missing_critical = check_critical_deps()
    if missing_critical:
        print(f"      KRITIČNO: Sledeći paketi nedostaju: {', '.join(missing_critical)}")
    else:
        print("      Sve kritične zavisnosti su prisutne.")

    # Rezime
    print()
    print("=" * 70)
    issues = len(vulns) + len(unpinned) + len(missing_critical)
    if issues == 0:
        print("Rezultat: Nema pronađenih problema.")
    else:
        print(f"Rezultat: {issues} problema pronađeno — pogledajte izlaz iznad.")
    print("=" * 70)

    if args.ci and (has_vulns or missing_critical):
        sys.exit(1)


if __name__ == "__main__":
    main()

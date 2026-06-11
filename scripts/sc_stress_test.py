# -*- coding: utf-8 -*-
"""
Faza 0 — Smart Contract Analyzer: stress test za determinizam.
8 ugovora x 3 run-a = 24 poziva.

Pokretanje:
    python scripts/sc_stress_test.py

Output:
    scripts/sc_stress_test_results.json
    scripts/sc_stress_test_report.md
"""
import sys, os, json, time, itertools
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(dotenv_path=ROOT / ".env")
os.environ["VINDEX_CACHE_BYPASS"] = "1"

import api as _api
from fastapi.testclient import TestClient

# ── Auth bypass — founder identity, no credit deduction ───────────────────────
MOCK_USER = {
    "user_id": "00000000-0000-0000-0000-000000000001",
    "email":   "benny13.n@gmail.com",
    "is_pro":  True,
}
_api.app.dependency_overrides[_api.require_pro] = lambda: MOCK_USER

# ── Rate limiter bypass — reset storage before each call ──────────────────────
def _reset_limiter():
    try:
        _api.limiter.reset()
    except Exception:
        pass

client = TestClient(_api.app, raise_server_exceptions=False)

# ── Constants for determinism checks ──────────────────────────────────────────
PLACEHOLDER_TEXT = _api._DEFAULT_OFFCHAIN_PLACEHOLDER["zavisnost"]
AML_TEXT         = _api._AML_KYC_NAPOMENA.strip()


def run_analysis(source: str) -> dict:
    _reset_limiter()
    resp = client.post(
        "/web3/analiziraj-ugovor",
        json={"solidity_source": source},
    )
    if resp.status_code == 429:
        # Fallback: wait for rate limit window to reset
        time.sleep(62)
        _reset_limiter()
        resp = client.post("/web3/analiziraj-ugovor", json={"solidity_source": source})
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def extract_metrics(data: dict) -> dict:
    ar            = data.get("analysis_result", {})
    pravni_rizici = ar.get("pravni_rizici", [])
    offchain      = ar.get("offchain_zavisnosti", [])
    anon          = ar.get("pravni_indikatori", {}).get("anonimnost_ucesnika", {})
    reg_rel       = ar.get("regulatorna_relevantnost", [])

    zdi_clanovi, mica_clanovi = [], []
    for r in reg_rel:
        propis = r.get("propis", "").lower()
        if any(k in propis for k in ("digital", "zdi", "digitalna imovina", "digitalnoj imovini")):
            zdi_clanovi = r.get("relevantni_clanovi", [])
        if any(k in propis for k in ("mica", "markets in crypto", "crypto-assets")):
            mica_clanovi = r.get("relevantni_clanovi", [])

    offchain_ok = bool(offchain) and offchain[0].get("zavisnost", "").strip() == PLACEHOLDER_TEXT.strip()

    return {
        "broj_pravnih_rizika":      len(pravni_rizici),
        "naslovi_rizika":           [r.get("rizik", "")[:65] for r in pravni_rizici],
        "offchain_ima_placeholder": offchain_ok,
        "anon_ima_aml_napomenu":    AML_TEXT in anon.get("obrazlozenje", ""),
        "anon_indikator":           anon.get("indikator", "?"),
        "confidence_tier":          ar.get("confidence_tier", "?"),
        "is_proxy_detected":        data.get("is_proxy_detected", False),
        "zdi_clanovi":              zdi_clanovi,
        "mica_clanovi":             mica_clanovi,
    }


# ── Load contracts ─────────────────────────────────────────────────────────────
CONTRACTS_DIR = ROOT / "test_contracts"
contracts     = sorted(CONTRACTS_DIR.glob("*.sol"))
RUNS          = 3

if not contracts:
    print("ERROR: Nema .sol fajlova u test_contracts/")
    sys.exit(1)

print(f"\n{'='*65}")
print(f"Faza 0 — Smart Contract Analyzer Stress Test")
print(f"Ugovori: {len(contracts)}  |  Runs: {RUNS}  |  Ukupno poziva: {len(contracts)*RUNS}")
print(f"Datum: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"{'='*65}\n")

all_results = []

for ci, contract_path in enumerate(contracts):
    name   = contract_path.stem
    source = contract_path.read_text(encoding="utf-8")

    print(f"\n[{ci+1}/{len(contracts)}] {name}")
    print("-" * 50)

    contract_entry = {"contract": name, "runs": []}

    for run_n in range(1, RUNS + 1):
        t0    = time.time()
        error = None
        metrics = {}

        try:
            data    = run_analysis(source)
            metrics = extract_metrics(data)
        except Exception as e:
            error = str(e)[:300]
            print(f"  Run {run_n}: GRESKA — {error}")

        elapsed = round(time.time() - t0, 1)
        run_entry = {"run": run_n, "elapsed_s": elapsed, "error": error, **metrics}
        contract_entry["runs"].append(run_entry)

        if not error:
            print(
                f"  Run {run_n}: rizika={metrics['broj_pravnih_rizika']:2d}  "
                f"offchain={'DA' if metrics['offchain_ima_placeholder'] else 'NE'}  "
                f"aml={'DA' if metrics['anon_ima_aml_napomenu'] else 'NE'}  "
                f"tier={metrics['confidence_tier']}  "
                f"ZDI={metrics['zdi_clanovi']}  ({elapsed}s)"
            )

        if run_n < RUNS:
            time.sleep(2)

    all_results.append(contract_entry)

    if ci < len(contracts) - 1:
        time.sleep(3)

# ── Save raw JSON ──────────────────────────────────────────────────────────────
out_json = ROOT / "scripts" / "sc_stress_test_results.json"
with open(out_json, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)
print(f"\n[OK] JSON saved: {out_json}")


# ── Generate Markdown report ───────────────────────────────────────────────────
def bc(v): return "DA" if v else "NE"

lines = []
lines.append("# Smart Contract Analyzer — Stress Test Report (Faza 0)")
lines.append(f"\n**Datum**: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ")
lines.append(f"**Ugovori**: {len(contracts)}  |  **Runs/ugovor**: {RUNS}  |  "
             f"**Ukupno poziva**: {len(contracts)*RUNS}  ")
lines.append("**Model**: gpt-4o, temperature=0.2  ")
lines.append("**Post-processing**: offchain placeholder, AML napomena, lock-without-exit fallback")

lines.append("\n---\n")
lines.append("## Sazet pregled stabilnosti\n")
lines.append("| Ugovor | Rizici identican br. (3/3)? | ZDI identicni (3/3)? | Offchain OK (3/3)? | AML OK (3/3)? |")
lines.append("|--------|------------------------------|----------------------|--------------------|--------------|")

stability_rizici = []
stability_zdi    = []
offchain_pass    = []
aml_pass         = []

for entry in all_results:
    name = entry["contract"]
    runs = [r for r in entry["runs"] if not r.get("error")]

    if len(runs) < 2:
        lines.append(f"| {name} | N/A | N/A | N/A | N/A |")
        continue

    counts   = [r["broj_pravnih_rizika"] for r in runs]
    zdi_sets = [tuple(sorted(r.get("zdi_clanovi", []))) for r in runs]
    oc_ok    = [r.get("offchain_ima_placeholder", False) for r in runs]
    aml_ok   = [r.get("anon_ima_aml_napomenu", False) for r in runs]

    rizici_stable = len(set(counts))    == 1
    zdi_stable    = len(set(zdi_sets))  == 1
    oc_all        = all(oc_ok)
    aml_all       = all(aml_ok)

    stability_rizici.append(rizici_stable)
    stability_zdi.append(zdi_stable)
    offchain_pass.extend(oc_ok)
    aml_pass.extend(aml_ok)

    rzl = ("DA" if rizici_stable else f"NE ({counts})")
    zdl = ("DA" if zdi_stable    else "NE (variira)")
    lines.append(f"| {name} | {rzl} | {zdl} | {bc(oc_all)} | {bc(aml_all)} |")

n = len(stability_rizici)
pct_r  = round(100 * sum(stability_rizici) / n)  if n else 0
pct_z  = round(100 * sum(stability_zdi) / n)     if n else 0
pct_oc = round(100 * sum(offchain_pass) / len(offchain_pass)) if offchain_pass else 0
pct_am = round(100 * sum(aml_pass) / len(aml_pass))           if aml_pass      else 0

lines.append(f"\n**Stabilnost broja rizika**: {sum(stability_rizici)}/{n} ugovora ({pct_r}%)  ")
lines.append(f"**Stabilnost ZDI clanova**: {sum(stability_zdi)}/{n} ugovora ({pct_z}%)  ")
lines.append(f"**Determinizam offchain** (post-processing): {sum(offchain_pass)}/{len(offchain_pass)} poziva ({pct_oc}%)  ")
lines.append(f"**Determinizam AML napomena** (post-processing): {sum(aml_pass)}/{len(aml_pass)} poziva ({pct_am}%)  ")

lines.append("\n---\n")
lines.append("## Detalji po ugovoru\n")

for entry in all_results:
    name = entry["contract"]
    runs = entry["runs"]
    lines.append(f"### {name}\n")
    lines.append("| Run | Rizika | Offchain OK | AML OK | Anon ind. | Confidence | Proxy | ZDI | MiCA | Vreme |")
    lines.append("|-----|--------|-------------|--------|-----------|------------|-------|-----|------|-------|")

    for r in runs:
        if r.get("error"):
            lines.append(f"| {r['run']} | GRESKA | - | - | - | - | - | - | - | {r['elapsed_s']}s |")
            continue
        oc   = bc(r.get("offchain_ima_placeholder", False))
        aml  = bc(r.get("anon_ima_aml_napomenu", False))
        prx  = "DA" if r.get("is_proxy_detected") else "NE"
        zdi  = ", ".join(r.get("zdi_clanovi", [])) or "-"
        mica = ", ".join(r.get("mica_clanovi", [])) or "-"
        lines.append(
            f"| {r['run']} | {r.get('broj_pravnih_rizika','?')} | {oc} | {aml} | "
            f"{r.get('anon_indikator','?')} | {r.get('confidence_tier','?')} | {prx} | "
            f"{zdi} | {mica} | {r['elapsed_s']}s |"
        )

    for r in runs:
        if r.get("error"):
            continue
        rizici = r.get("naslovi_rizika", [])
        if rizici:
            lines.append(f"\n**Run {r['run']} rizici:**")
            for rz in rizici:
                lines.append(f"- {rz}")
    lines.append("")

out_md = ROOT / "scripts" / "sc_stress_test_report.md"
with open(out_md, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"[OK] Report saved: {out_md}")

print(f"\n{'='*65}")
print("STRESS TEST SAZETAK")
print(f"{'='*65}")
print(f"  Stabilnost broja rizika : {sum(stability_rizici)}/{n} ({pct_r}%)")
print(f"  Stabilnost ZDI clanova  : {sum(stability_zdi)}/{n} ({pct_z}%)")
print(f"  Offchain placeholder    : {sum(offchain_pass)}/{len(offchain_pass)} ({pct_oc}%)")
print(f"  AML napomena            : {sum(aml_pass)}/{len(aml_pass)} ({pct_am}%)")
print(f"{'='*65}")

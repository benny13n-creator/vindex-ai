# -*- coding: utf-8 -*-
"""
Faza 0 — Smart Contract Analyzer: stress test za determinizam.
8 ugovora x 3 run-a = 24 poziva (direktno, bez HTTP, zaobilazi rate limiter).

Pokretanje:
    python scripts/sc_stress_test.py

Output:
    scripts/sc_stress_test_results.json
    scripts/sc_stress_test_report.md
"""
import sys, os, json, time, asyncio
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(dotenv_path=ROOT / ".env")

os.environ["VINDEX_CACHE_BYPASS"] = "1"

# Import api module (loads FastAPI app, all helpers, constants)
import api as _api

# ── Auth bypass — founder identity, no credit deduction ───────────────────────
MOCK_USER = {
    "user_id": "00000000-0000-0000-0000-000000000001",
    "email":   "benny13.n@gmail.com",
    "is_pro":  True,
}

# ── Constants for determinism checks ──────────────────────────────────────────
PLACEHOLDER_TEXT = _api._DEFAULT_OFFCHAIN_PLACEHOLDER["zavisnost"]
AML_TEXT         = _api._AML_KYC_NAPOMENA.strip()


async def _run_single(source: str) -> dict:
    """Call post_analiziraj_ugovor directly — bypasses HTTP + rate limiter."""
    mock_req = MagicMock()
    mock_req.client.host = "127.0.0.1"
    mock_req.headers     = {}

    return await _api.post_analiziraj_ugovor(
        req=_api.SmartContractReq(solidity_source=source),
        request=mock_req,
        user=MOCK_USER,
    )


def run_analysis(source: str) -> dict:
    return asyncio.run(_run_single(source))


def extract_metrics(data: dict) -> dict:
    ar  = data.get("analysis_result", {})
    pravni_rizici  = ar.get("pravni_rizici", [])
    offchain       = ar.get("offchain_zavisnosti", [])
    anon           = ar.get("pravni_indikatori", {}).get("anonimnost_ucesnika", {})
    reg_rel        = ar.get("regulatorna_relevantnost", [])

    zdi_clanovi, mica_clanovi = [], []
    for r in reg_rel:
        propis = r.get("propis", "").lower()
        if any(k in propis for k in ("digital", "zdi", "digitalna imovina", "digitalnoj imovini")):
            zdi_clanovi = r.get("relevantni_clanovi", [])
        if any(k in propis for k in ("mica", "markets in crypto", "crypto-assets")):
            mica_clanovi = r.get("relevantni_clanovi", [])

    offchain_ok = (
        bool(offchain) and
        offchain[0].get("zavisnost", "").strip() == PLACEHOLDER_TEXT.strip()
    )

    return {
        "broj_pravnih_rizika":  len(pravni_rizici),
        "naslovi_rizika":       [r.get("rizik", "")[:65] for r in pravni_rizici],
        "offchain_ima_placeholder": offchain_ok,
        "anon_ima_aml_napomenu":    AML_TEXT in anon.get("obrazlozenje", ""),
        "anon_indikator":       anon.get("indikator", "?"),
        "confidence_tier":      ar.get("confidence_tier", "?"),
        "is_proxy_detected":    data.get("is_proxy_detected", False),
        "zdi_clanovi":          zdi_clanovi,
        "mica_clanovi":         mica_clanovi,
    }


# ── Load contracts ─────────────────────────────────────────────────────────────
CONTRACTS_DIR = ROOT / "test_contracts"
contracts = sorted(CONTRACTS_DIR.glob("*.sol"))

if not contracts:
    print("ERROR: Nema .sol fajlova u test_contracts/")
    sys.exit(1)

RUNS = 3
DELAY_BETWEEN_RUNS = 2   # sekunde između run-ova istog ugovora
DELAY_BETWEEN_CONTRACTS = 3  # sekunde između ugovora

print(f"\n{'='*65}")
print(f"Faza 0 — Smart Contract Analyzer Stress Test")
print(f"Ugovori: {len(contracts)}  |  Run-ovi: {RUNS}  |  Ukupno poziva: {len(contracts)*RUNS}")
print(f"Datum: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"{'='*65}\n")

all_results = []

for ci, contract_path in enumerate(contracts):
    name   = contract_path.stem
    source = contract_path.read_text(encoding="utf-8")
    word_count = len(source.split())

    print(f"\n[{ci+1}/{len(contracts)}] {name}  ({word_count} reči)")
    print("-" * 50)

    contract_entry = {"contract": name, "runs": []}

    for run_n in range(1, RUNS + 1):
        t0 = time.time()
        error = None
        metrics = {}

        try:
            data = run_analysis(source)
            metrics = extract_metrics(data)
        except Exception as e:
            error = str(e)[:200]
            print(f"  Run {run_n}: GREŠKA — {error}")

        elapsed = round(time.time() - t0, 1)

        run_entry = {"run": run_n, "elapsed_s": elapsed, "error": error, **metrics}
        contract_entry["runs"].append(run_entry)

        if not error:
            print(
                f"  Run {run_n}: rizika={metrics['broj_pravnih_rizika']:2d}  "
                f"offchain={'DA' if metrics['offchain_ima_placeholder'] else 'NE':3s}  "
                f"aml={'DA' if metrics['anon_ima_aml_napomenu'] else 'NE':3s}  "
                f"tier={metrics['confidence_tier']:8s}  "
                f"ZDI={metrics['zdi_clanovi']}  ({elapsed}s)"
            )

        if run_n < RUNS:
            time.sleep(DELAY_BETWEEN_RUNS)

    all_results.append(contract_entry)

    if ci < len(contracts) - 1:
        time.sleep(DELAY_BETWEEN_CONTRACTS)

# ── Save raw JSON ──────────────────────────────────────────────────────────────
out_json = ROOT / "scripts" / "sc_stress_test_results.json"
with open(out_json, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)
print(f"\n✓ JSON saved: {out_json}")


# ── Generate Markdown report ───────────────────────────────────────────────────
def bool_cell(v: bool) -> str:
    return "✅" if v else "❌"


lines = []
lines.append("# Smart Contract Analyzer — Stress Test Report (Faza 0)")
lines.append(f"\n**Datum**: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ")
lines.append(f"**Ugovori**: {len(contracts)}  |  **Runs/ugovor**: {RUNS}  |  **Ukupno poziva**: {len(contracts)*RUNS}  ")
lines.append(f"**Model**: gpt-4o, temperature=0.2  ")
lines.append(f"**Post-processing**: aktivan (offchain placeholder, AML napomena, lock-without-exit fallback)")

lines.append("\n---\n")
lines.append("## Sažetak stabilnosti\n")
lines.append("| Ugovor | Rizici identični (3/3)? | ZDI identični (3/3)? | Offchain OK (3/3)? | AML OK (3/3)? |")
lines.append("|--------|------------------------|----------------------|-------------------|--------------|")

stability_rizici = []
stability_zdi    = []
offchain_pass    = []
aml_pass         = []

for entry in all_results:
    name  = entry["contract"]
    runs  = [r for r in entry["runs"] if not r.get("error")]

    if len(runs) < 2:
        row = f"| {name} | N/A | N/A | N/A | N/A |"
        lines.append(row)
        continue

    counts   = [r["broj_pravnih_rizika"] for r in runs]
    zdi_sets = [tuple(sorted(r.get("zdi_clanovi", []))) for r in runs]
    oc_ok    = [r.get("offchain_ima_placeholder", False) for r in runs]
    aml_ok   = [r.get("anon_ima_aml_napomenu", False) for r in runs]

    rizici_stable = len(set(counts))   == 1
    zdi_stable    = len(set(zdi_sets)) == 1
    oc_all        = all(oc_ok)
    aml_all       = all(aml_ok)

    stability_rizici.append(rizici_stable)
    stability_zdi.append(zdi_stable)
    offchain_pass.extend(oc_ok)
    aml_pass.extend(aml_ok)

    rizici_label = ("✅ DA" if rizici_stable else f"❌ NE ({counts})")
    zdi_label    = ("✅ DA" if zdi_stable    else f"❌ NE (variira)")
    oc_label     = bool_cell(oc_all)
    aml_label    = bool_cell(aml_all)

    lines.append(f"| {name} | {rizici_label} | {zdi_label} | {oc_label} | {aml_label} |")

# Aggregate stats
n = len(stability_rizici)
pct_rizici  = round(100 * sum(stability_rizici) / n) if n else 0
pct_zdi     = round(100 * sum(stability_zdi) / n)    if n else 0
pct_offchain = round(100 * sum(offchain_pass) / len(offchain_pass)) if offchain_pass else 0
pct_aml      = round(100 * sum(aml_pass) / len(aml_pass))           if aml_pass      else 0

lines.append(f"\n**Stabilnost broja rizika**: {sum(stability_rizici)}/{n} ugovora konzistentni ({pct_rizici}%)  ")
lines.append(f"**Stabilnost ZDI članova**: {sum(stability_zdi)}/{n} ugovora konzistentni ({pct_zdi}%)  ")
lines.append(f"**Determinizam offchain** (post-processing): {sum(offchain_pass)}/{len(offchain_pass)} poziva OK ({pct_offchain}%)  ")
lines.append(f"**Determinizam AML napomena** (post-processing): {sum(aml_pass)}/{len(aml_pass)} poziva OK ({pct_aml}%)  ")

lines.append("\n---\n")
lines.append("## Detalji po ugovoru\n")

for entry in all_results:
    name = entry["contract"]
    runs = entry["runs"]
    lines.append(f"### {name}\n")
    lines.append("| Run | Rizika | Offchain OK | AML OK | Anon indikator | Confidence | Proxy | ZDI | MiCA | Vreme |")
    lines.append("|-----|--------|-------------|--------|----------------|------------|-------|-----|------|-------|")

    for r in runs:
        if r.get("error"):
            lines.append(f"| {r['run']} | GREŠKA | — | — | — | — | — | — | — | {r['elapsed_s']}s |")
            continue
        oc   = bool_cell(r.get("offchain_ima_placeholder", False))
        aml  = bool_cell(r.get("anon_ima_aml_napomenu", False))
        prx  = "DA" if r.get("is_proxy_detected") else "NE"
        zdi  = ", ".join(r.get("zdi_clanovi", [])) or "—"
        mica = ", ".join(r.get("mica_clanovi", [])) or "—"
        lines.append(
            f"| {r['run']} | {r.get('broj_pravnih_rizika','?')} | {oc} | {aml} | "
            f"{r.get('anon_indikator','?')} | {r.get('confidence_tier','?')} | {prx} | "
            f"{zdi} | {mica} | {r['elapsed_s']}s |"
        )

    # Naslovi rizika po runu
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
print(f"✓ Report saved: {out_md}")

# ── Console summary ────────────────────────────────────────────────────────────
print(f"\n{'='*65}")
print("STRESS TEST SAŽETAK")
print(f"{'='*65}")
print(f"  Stabilnost broja rizika : {sum(stability_rizici)}/{n} ({pct_rizici}%)")
print(f"  Stabilnost ZDI članova  : {sum(stability_zdi)}/{n} ({pct_zdi}%)")
print(f"  Offchain placeholder    : {sum(offchain_pass)}/{len(offchain_pass)} ({pct_offchain}%)")
print(f"  AML napomena            : {sum(aml_pass)}/{len(aml_pass)} ({pct_aml}%)")
print(f"{'='*65}")

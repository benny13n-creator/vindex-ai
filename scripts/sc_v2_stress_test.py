# -*- coding: utf-8 -*-
"""
V2 Schema Stress Test — determinizam novih polja.
3 ugovora x 3 run-a = 9 poziva ukupno.

Testira stabilnost:
  - Garantovana polja (post-processing): broj_pravnih_rizika minimum, offchain, AML napomena
  - GPT-generisana polja: nivo_relevantnosti, klasifikacija_tokena, aml_kyc.nivo_rizika,
    centralizacija.nivo, administrativna_ovlascenja.nivo

Pokretanje:
    python scripts/sc_v2_stress_test.py

Output:
    scripts/sc_v2_stress_test_results.json
    scripts/sc_v2_stress_test_report.md
"""
import sys, os, json, time
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

# ── Auth + rate limiter bypass ─────────────────────────────────────────────────
MOCK_USER = {
    "user_id": "00000000-0000-0000-0000-000000000001",
    "email":   "benny13.n@gmail.com",
    "is_pro":  True,
}
_api.app.dependency_overrides[_api.require_pro] = lambda: MOCK_USER

def _reset_limiter():
    try:
        _api.limiter.reset()
    except Exception:
        pass

client = TestClient(_api.app, raise_server_exceptions=False)

PLACEHOLDER_TEXT = _api._DEFAULT_OFFCHAIN_PLACEHOLDER["zavisnost"]
AML_TEXT         = _api._AML_KYC_NAPOMENA.strip()

# ── Target contracts ───────────────────────────────────────────────────────────
CONTRACTS_DIR = ROOT / "test_contracts"
TARGET_CONTRACTS = ["simple_staking.sol", "simple_token.sol", "pause_token.sol"]


def run_analysis(source: str) -> dict:
    _reset_limiter()
    resp = client.post("/web3/analiziraj-ugovor", json={"solidity_source": source})
    if resp.status_code == 429:
        time.sleep(62)
        _reset_limiter()
        resp = client.post("/web3/analiziraj-ugovor", json={"solidity_source": source})
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def extract_metrics(data: dict, source: str) -> dict:
    ar = data.get("analysis_result", {})

    # Guaranteed by post-processing
    pravni_rizici = ar.get("pravni_rizici", []) or []
    offchain      = ar.get("offchain_zavisnosti", []) or []
    anon          = (ar.get("pravni_indikatori") or {}).get("anonimnost_ucesnika", {}) or {}
    offchain_ok   = bool(offchain) and offchain[0].get("zavisnost", "").strip() == PLACEHOLDER_TEXT.strip()
    aml_ok        = AML_TEXT in anon.get("obrazlozenje", "")

    # Regulatorna relevantnost
    reg_rel = ar.get("regulatorna_relevantnost", []) or []
    reg_summary = []
    for r in reg_rel:
        clanovi = r.get("relevantni_clanovi", []) or []
        reg_summary.append({
            "propis_kratko": r.get("propis", "")[:50],
            "nivo_relevantnosti": r.get("nivo_relevantnosti", "?"),
            "broj_clanova": len(clanovi),
        })

    # v2 nova polja
    klasif     = ar.get("klasifikacija_tokena", []) or []
    aml_kyc    = ar.get("aml_kyc", {}) or {}
    cent       = ar.get("centralizacija", {}) or {}
    adm        = ar.get("administrativna_ovlascenja", {}) or {}
    sazetak    = ar.get("pravni_sazetak", []) or []

    # Heuristics (computed from source, not in API response)
    is_lock  = _api._sc_detect_lock_without_exit(source)
    is_mint  = _api._sc_detect_unrestricted_mint(source)
    is_proxy = data.get("is_proxy_detected", False)

    return {
        # Guaranteed fields
        "broj_pravnih_rizika":      len(pravni_rizici),
        "naslovi_rizika":           [r.get("rizik", "")[:65] for r in pravni_rizici],
        "offchain_ima_placeholder": offchain_ok,
        "anon_ima_aml_napomenu":    aml_ok,
        "confidence_tier":          ar.get("confidence_tier", "?"),

        # v2 GPT-generated fields
        "reg_summary":              reg_summary,
        "klasif_tokena":            [{"kategorija": k.get("kategorija","?"), "status": k.get("status","?")} for k in klasif],
        "aml_nivo_rizika":          aml_kyc.get("nivo_rizika", "?"),
        "aml_obrazlozenje_80":      aml_kyc.get("obrazlozenje", "")[:80],
        "cent_nivo":                cent.get("nivo", "?"),
        "cent_obrazlozenje_80":     cent.get("obrazlozenje", "")[:80],
        "adm_nivo":                 adm.get("nivo", "?"),
        "adm_br_funkcija":          len(adm.get("privilegovane_funkcije", []) or []),
        "adm_br_uloga":             len(adm.get("privilegovane_uloge", []) or []),
        "br_sazetak_stavki":        len(sazetak),

        # Heuristics (deterministic, code-derived)
        "is_lock_without_exit":     is_lock,
        "is_unrestricted_mint":     is_mint,
        "is_proxy_detected":        is_proxy,
    }


# ── Main loop ──────────────────────────────────────────────────────────────────
print(f"\n{'='*68}")
print(f"V2 Schema Stress Test — determinizam novih polja")
print(f"Ugovori: {len(TARGET_CONTRACTS)}  |  Runs: 3  |  Ukupno poziva: 9")
print(f"Datum: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"{'='*68}\n")

all_results = []

for ci, fname in enumerate(TARGET_CONTRACTS):
    fpath = CONTRACTS_DIR / fname
    if not fpath.exists():
        print(f"[SKIP] {fname} ne postoji u test_contracts/")
        continue

    source = fpath.read_text(encoding="utf-8")
    name   = fpath.stem

    # Pre-compute heuristics (deterministic)
    is_lock  = _api._sc_detect_lock_without_exit(source)
    is_mint  = _api._sc_detect_unrestricted_mint(source)
    min_rizika = (1 if is_lock else 0) + (1 if is_mint else 0)

    print(f"\n[{ci+1}/{len(TARGET_CONTRACTS)}] {name}")
    print(f"  Heuristike: lock={is_lock}, mint={is_mint}, min_garantovanih_rizika={min_rizika}")
    print("-" * 55)

    contract_entry = {
        "contract": name,
        "min_garantovanih_rizika": min_rizika,
        "is_lock_heuristic": is_lock,
        "is_mint_heuristic": is_mint,
        "runs": [],
    }

    for run_n in range(1, 4):
        t0 = time.time()
        error = None
        metrics = {}

        try:
            data    = run_analysis(source)
            metrics = extract_metrics(data, source)
        except Exception as e:
            error = str(e)[:300]
            print(f"  Run {run_n}: GRESKA — {error}")

        elapsed = round(time.time() - t0, 1)
        run_entry = {"run": run_n, "elapsed_s": elapsed, "error": error, **metrics}
        contract_entry["runs"].append(run_entry)

        if not error:
            aml_nivo = metrics.get("aml_nivo_rizika", "?")
            cent_nivo = metrics.get("cent_nivo", "?")
            adm_nivo = metrics.get("adm_nivo", "?")
            klasif_str = ", ".join(f"{k['kategorija']}={k['status']}" for k in metrics.get("klasif_tokena", []))
            reg_str = " | ".join(
                f"{r['propis_kratko'][:25]}:{r['nivo_relevantnosti']}({r['broj_clanova']}cl)"
                for r in metrics.get("reg_summary", [])
            )
            ok_post = (
                metrics["broj_pravnih_rizika"] >= min_rizika
                and metrics["offchain_ima_placeholder"]
                and metrics["anon_ima_aml_napomenu"]
            )
            print(
                f"  Run {run_n}: rizika={metrics['broj_pravnih_rizika']:2d}(min={min_rizika})  "
                f"post={'OK' if ok_post else 'FAIL'}  "
                f"aml={aml_nivo}  cent={cent_nivo}  adm={adm_nivo}  "
                f"tier={metrics['confidence_tier']}  ({elapsed}s)"
            )
            if klasif_str:
                print(f"           klasif: {klasif_str}")
            if reg_str:
                print(f"           reg:    {reg_str[:120]}")

        if run_n < 3:
            time.sleep(2)

    all_results.append(contract_entry)
    if ci < len(TARGET_CONTRACTS) - 1:
        time.sleep(3)


# ── Save raw JSON ──────────────────────────────────────────────────────────────
out_json = ROOT / "scripts" / "sc_v2_stress_test_results.json"
with open(out_json, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)
print(f"\n[OK] JSON saved: {out_json}")


# ── Generate Markdown report ───────────────────────────────────────────────────
def stable(vals):
    clean = [v for v in vals if v is not None]
    return len(set(str(v) for v in clean)) == 1 if len(clean) >= 2 else None

def fmt_stable(vals):
    s = stable(vals)
    if s is None:
        return "?"
    return "✅ DA" if s else "❌ NE"

def fmt_vals(vals):
    return " / ".join(str(v) for v in vals)

lines = []
lines.append("# Smart Contract Analyzer — V2 Schema Stress Test Report")
lines.append(f"\n**Datum**: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ")
lines.append("**Ugovori**: 3 (simple_staking, simple_token, pause_token)  ")
lines.append("**Runs/ugovor**: 3  |  **Ukupno poziva**: 9  ")
lines.append("**Model**: gpt-4o, temperature=0.2  ")
lines.append("")

# ── Post-processing integrity check ───────────────────────────────────────────
lines.append("---")
lines.append("")
lines.append("## ⚡ Post-processing garantovana polja (REGRESIJA ako nestabilno)")
lines.append("")
lines.append("| Ugovor | Min garantovanih rizika | Br. rizika R1/R2/R3 | >= min? (KRITIČNO) | Identičan br.? | Offchain OK? | AML napomena? |")
lines.append("|--------|------------------------|---------------------|---------------------|----------------|--------------|---------------|")

for entry in all_results:
    name = entry["contract"]
    runs = [r for r in entry["runs"] if not r.get("error")]
    min_g = entry["min_garantovanih_rizika"]

    rizici_vals  = [r["broj_pravnih_rizika"] for r in runs]
    offchain_all = all(r.get("offchain_ima_placeholder", False) for r in runs)
    aml_all      = all(r.get("anon_ima_aml_napomenu", False) for r in runs)

    # KRITIČNO: svi runovi moraju imati >= min_g (ovo je post-processing garancija)
    min_ok       = all(v >= min_g for v in rizici_vals)
    # GPT varijabilnost: da li je ukupan broj identičan? (NE = GPT šum, ne regresija)
    count_stable = len(set(rizici_vals)) == 1

    lines.append(
        f"| {name} | {min_g} | {fmt_vals(rizici_vals)} | "
        f"{'✅ DA' if min_ok else '🚨 NE — REGRESIJA'} | "
        f"{'✅ DA' if count_stable else '⚠️ NE (GPT šum)'} | "
        f"{'✅' if offchain_all else '❌'} | "
        f"{'✅' if aml_all else '❌'} |"
    )

lines.append("")

# ── GPT-generated fields per contract ─────────────────────────────────────────
lines.append("---")
lines.append("")
lines.append("## 📊 GPT-generisana polja po ugovoru")
lines.append("")

grand_stable = 0
grand_total  = 0

for entry in all_results:
    name = entry["contract"]
    runs = [r for r in entry["runs"] if not r.get("error")]
    if not runs:
        lines.append(f"### {name} — sve run-ove greška, nema podataka\n")
        continue

    lines.append(f"### {name}")
    lines.append("")
    lines.append(f"Heuristike: `lock={entry['is_lock_heuristic']}` | `mint={entry['is_mint_heuristic']}`  ")
    lines.append("")
    lines.append("| Polje | Run 1 | Run 2 | Run 3 | Stabilno? |")
    lines.append("|-------|-------|-------|-------|-----------|")

    def row(label, key, transform=None):
        vals = []
        for r in runs:
            v = r.get(key, "?")
            if transform:
                v = transform(v)
            vals.append(v)
        # Pad to 3 if fewer runs succeeded
        while len(vals) < 3:
            vals.append("—")
        s = fmt_stable(vals)
        return f"| {label} | {vals[0]} | {vals[1]} | {vals[2]} | {s} |"

    def row_list(label, key, subkey):
        """Extract a value from a list field by subkey across runs."""
        vals = []
        for r in runs:
            items = r.get(key, []) or []
            v = ", ".join(str(i.get(subkey,"?")) for i in items) if items else "—"
            vals.append(v[:60])
        while len(vals) < 3:
            vals.append("—")
        s = fmt_stable(vals)
        return f"| {label} | {vals[0]} | {vals[1]} | {vals[2]} | {s} |"

    def row_reg(label, subkey):
        """Extract from reg_summary list."""
        vals = []
        for r in runs:
            regs = r.get("reg_summary", []) or []
            v = " | ".join(str(rg.get(subkey,"?")) for rg in regs) if regs else "—"
            vals.append(v[:70])
        while len(vals) < 3:
            vals.append("—")
        s = fmt_stable(vals)
        return f"| {label} | {vals[0]} | {vals[1]} | {vals[2]} | {s} |"

    lines.append(row("confidence_tier", "confidence_tier"))
    lines.append(row("centralizacija.nivo", "cent_nivo"))
    lines.append(row("adm_ovl.nivo", "adm_nivo"))
    lines.append(row("adm_ovl.br_funkcija", "adm_br_funkcija"))
    lines.append(row("adm_ovl.br_uloga", "adm_br_uloga"))
    lines.append(row("aml_kyc.nivo_rizika", "aml_nivo_rizika"))
    lines.append(row_list("klasif_tokena.kategorija", "klasif_tokena", "kategorija"))
    lines.append(row_list("klasif_tokena.status", "klasif_tokena", "status"))
    lines.append(row_reg("reg.nivo_relevantnosti", "nivo_relevantnosti"))
    lines.append(row_reg("reg.broj_clanova", "broj_clanova"))
    lines.append(row("br_pravni_sazetak", "br_sazetak_stavki"))

    # Count stable fields for this contract
    check_keys = [
        ("confidence_tier", lambda r: r.get("confidence_tier","?")),
        ("cent_nivo",        lambda r: r.get("cent_nivo","?")),
        ("adm_nivo",         lambda r: r.get("adm_nivo","?")),
        ("aml_nivo_rizika",  lambda r: r.get("aml_nivo_rizika","?")),
        ("klasif_status",    lambda r: str([k.get("status") for k in (r.get("klasif_tokena") or [])])),
        ("reg_nivo",         lambda r: str([rg.get("nivo_relevantnosti") for rg in (r.get("reg_summary") or [])])),
    ]
    local_s = 0
    for _, fn in check_keys:
        vals = [fn(r) for r in runs]
        if stable(vals):
            local_s += 1
    grand_stable += local_s
    grand_total  += len(check_keys)

    lines.append("")
    lines.append(f"**Stabilnih GPT polja: {local_s}/{len(check_keys)}**")
    lines.append("")

    # Rizici titles per run
    for i, r in enumerate(runs, 1):
        rizici = r.get("naslovi_rizika", [])
        if rizici:
            lines.append(f"**Run {i} rizici ({r['broj_pravnih_rizika']}):**")
            for rz in rizici:
                lines.append(f"- {rz}")
    lines.append("")


# ── Grand summary ──────────────────────────────────────────────────────────────
lines.append("---")
lines.append("")
lines.append("## Ukupni sažetak")
lines.append("")

# Post-processing integrity
post_ok_list = []
for entry in all_results:
    runs = [r for r in entry["runs"] if not r.get("error")]
    min_g = entry["min_garantovanih_rizika"]
    rizici_vals = [r["broj_pravnih_rizika"] for r in runs]
    offchain_all = all(r.get("offchain_ima_placeholder", False) for r in runs)
    aml_all = all(r.get("anon_ima_aml_napomenu", False) for r in runs)
    # Regresija = min_g nije ispunjen ILI offchain/AML nisu OK
    # Varijabilnost broja rizika (> min_g) je GPT šum, ne regresija
    min_ok = all(v >= min_g for v in rizici_vals)
    post_ok_list.append(min_ok and offchain_all and aml_all)

post_ok_n = sum(post_ok_list)
post_total = len(post_ok_list)
gpt_pct = round(100 * grand_stable / grand_total) if grand_total else 0

lines.append(f"- **Post-processing integritet**: {post_ok_n}/{post_total} ugovora bez regresije")
lines.append(f"- **GPT polja stabilna 3/3**: {grand_stable}/{grand_total} ({gpt_pct}%)")
lines.append("")

if post_ok_n < post_total:
    lines.append("🚨 **REGRESIJA DETEKTOVANA** — post-processing garantovana polja nisu stabilna!")
else:
    lines.append("✅ **Post-processing garantovana polja: 100% stabilna** (nema regresije)")

lines.append("")
lines.append(f"> GPT-generisana polja pri temperature=0.2: {gpt_pct}% stabilna 3/3 runs.  ")
lines.append("> Nestabilnost GPT polja je očekivana — nisu garantovana post-processing-om.")

# ── Write report ───────────────────────────────────────────────────────────────
out_md = ROOT / "scripts" / "sc_v2_stress_test_report.md"
with open(out_md, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"[OK] Report saved: {out_md}")

print(f"\n{'='*68}")
print("V2 STRESS TEST SAZETAK")
print(f"{'='*68}")
print(f"  Post-processing integritet : {post_ok_n}/{post_total} ugovora OK")
print(f"  GPT polja stabilna 3/3     : {grand_stable}/{grand_total} ({gpt_pct}%)")
print(f"{'='*68}")

# -*- coding: utf-8 -*-
"""
evaluation/phase_0_5/run.py — generates blinded Genome-vs-LRE comparisons
for Reality Calibration (docs/architecture/LEGAL_REASONING_ARCHITECTURE.md
Phase 0.5).

Does NOT change any application code or data. Reads Case Genome
(predmeti.case_dna) and runs services.legal_reasoning_engine.
generate_reasoning_graph() for each predmet_id listed in a dataset
manifest (evaluation/phase_0_5/datasets/*.json — curated by the founder,
never auto-selected, per explicit instruction 2026-07-23: "Ne sme biti
automatski odabran").

For each case, writes TWO separate files:
  outputs/blinded/{predmet_id}.json  — what the lawyer sees: profile,
                                        Analysis A, Analysis B, empty
                                        score sheet. NO source labels.
  outputs/keys/{predmet_id}.json     — the real A/B -> genome/lre mapping.
                                        Never shown to the lawyer before
                                        scoring (compare.py reveals it
                                        after).

Usage:
    python evaluation/phase_0_5/run.py evaluation/phase_0_5/datasets/<manifest>.json
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.phase_0_5.metrics import assign_blind_labels, empty_score_sheet  # noqa: E402

OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"
BLINDED_DIR = OUTPUTS_DIR / "blinded"
KEYS_DIR = OUTPUTS_DIR / "keys"


def _genome_analysis_text(genome: dict) -> dict:
    """Extract Genome's EXISTING reasoning-shaped fields, unchanged --
    this is exactly what Phase 0.5 is measuring against, not a
    reformatted/improved version of it."""
    return {
        "argumenti_za": genome.get("argumenti_za") or [],
        "argumenti_protiv": genome.get("argumenti_protiv") or [],
        "kontradikcije": genome.get("kontradikcije") or [],
        "najslabija_tacka": genome.get("najslabija_tacka") or {},
        "zakljucak": genome.get("zakljucak") or "",
    }


def _lre_analysis_text(nodes: list[dict], edges: list[dict], confidence_rows: list[dict]) -> dict:
    """Reconstruct a comparable structure from the Reasoning Graph -- claims
    with their supporting facts/norms and confidence, contradictions are
    not a first-class LRE concept yet (Phase 0 scope), so this only
    covers what LRE actually produces today. Asymmetry between the two
    analyses' shape is itself informative for the lawyer, not hidden."""
    nodes_by_id = {n["id"]: n for n in nodes}
    conf_by_claim = {c["node_id"]: c for c in confidence_rows}

    supports = {}
    satisfies = {}
    creates = {}
    for e in edges:
        if e["edge_type"] == "supports":
            supports.setdefault(e["to_node_id"], []).append(e["from_node_id"])
        elif e["edge_type"] == "satisfies":
            satisfies.setdefault(e["to_node_id"], []).append(e["from_node_id"])
        elif e["edge_type"] == "creates":
            creates.setdefault(e["to_node_id"], []).append(e["from_node_id"])

    claims = []
    for n in nodes:
        if n["node_type"] != "Claim":
            continue
        claim_id = n["id"]
        norm_ids = creates.get(claim_id, [])
        le_ids = set()
        for norm_id in norm_ids:
            le_ids.update(satisfies.get(norm_id, []))
        fact_labels = []
        for le_id in le_ids:
            for fact_id in supports.get(le_id, []):
                if fact_id in nodes_by_id:
                    fact_labels.append(nodes_by_id[fact_id]["label"])
        norm_labels = [nodes_by_id[nid]["label"] for nid in norm_ids if nid in nodes_by_id]
        conf = conf_by_claim.get(claim_id, {})
        claims.append({
            "claim": n["label"],
            "based_on_facts": fact_labels,
            "based_on_norms": norm_labels,
            "confidence_total": conf.get("confidence_total"),
        })
    return {"claims": claims}


async def _run_one(predmet_id: str, profile: str, founder_user_id: str, supa) -> dict:
    from services.legal_reasoning_engine import generate_reasoning_graph

    pred_r = supa.table("predmeti").select("id,naziv,case_dna").eq("id", predmet_id).eq(
        "user_id", founder_user_id).maybe_single().execute()
    predmet = pred_r.data or {}
    genome = predmet.get("case_dna") or {}
    if not genome or genome.get("greska"):
        return {"predmet_id": predmet_id, "profile": profile, "skipped": "Nema Genome-a za ovaj predmet"}

    genome_analysis = _genome_analysis_text(genome)

    lre_result = await generate_reasoning_graph(predmet_id, founder_user_id)
    if lre_result.get("greska") and "graph_id" not in lre_result:
        return {"predmet_id": predmet_id, "profile": profile, "skipped": f"LRE greška: {lre_result['greska']}"}

    graph_id = lre_result["graph_id"]
    nodes = (supa.table("reasoning_nodes").select("id,node_type,label").eq("graph_id", graph_id).execute().data or [])
    edges = (supa.table("reasoning_edges").select("edge_type,from_node_id,to_node_id").eq("graph_id", graph_id).execute().data or [])
    confidence_rows = (supa.table("reasoning_confidence").select(
        "node_id,confidence_total").eq("predmet_id", predmet_id).execute().data or [])
    lre_analysis = _lre_analysis_text(nodes, edges, confidence_rows)

    assignment = assign_blind_labels(predmet_id)
    content_by_source = {"genome": genome_analysis, "lre": lre_analysis}
    blinded = {
        "predmet_id": predmet_id,
        "profile": profile,
        "naziv_maskiran": True,  # naziv predmeta se namerno NE upisuje ovde
        "Analysis A": content_by_source[assignment.label_to_source["A"]],
        "Analysis B": content_by_source[assignment.label_to_source["B"]],
        "score_sheet": empty_score_sheet(predmet_id),
    }

    BLINDED_DIR.mkdir(parents=True, exist_ok=True)
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    (BLINDED_DIR / f"{predmet_id}.json").write_text(
        json.dumps(blinded, ensure_ascii=False, indent=2), encoding="utf-8")
    (KEYS_DIR / f"{predmet_id}.json").write_text(
        json.dumps(assignment.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    return {"predmet_id": predmet_id, "profile": profile, "ok": True, "lre_verzija": lre_result.get("verzija")}


async def main(manifest_path: str):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from supabase import create_client

    founder_user_id = os.environ["EVAL_FOUNDER_USER_ID"]  # explicit, not hardcoded -- set per environment
    supa = create_client(
        os.environ["SUPABASE_URL"],
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_SERVICE_KEY"],
    )

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    cases = manifest.get("predmeti") or []
    if not cases:
        print("Prazan manifest -- nista za pokretanje. Popuni evaluation/phase_0_5/datasets/ pre pokretanja.")
        return

    results = []
    for c in cases:
        r = await _run_one(c["predmet_id"], c.get("profile", "nepoznat"), founder_user_id, supa)
        print(json.dumps(r, ensure_ascii=False))
        results.append(r)

    ok = sum(1 for r in results if r.get("ok"))
    print(f"\n{ok}/{len(results)} predmeta uspesno obradjeno. Blindirani izlazi: {BLINDED_DIR}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))

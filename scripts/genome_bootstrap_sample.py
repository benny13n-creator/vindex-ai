# -*- coding: utf-8 -*-
"""
Vindex AI — Case Genome Verification Layer bootstrap sampler (Faza 1.3 Rule C).

Povlaci N reprezentativnih Genome izlaza iz zive produkcije (raspon snaga_
predmeta_procent i broja dokumenata), pokrece shared/genome_validator.py
NEIZMENJEN nad svakim, i pise anonimizovan radni fajl za rucni pregled u
scratchpad direktorijum (NE u repo — sadrzi stvaran sadrzaj klijentskih
predmeta, ne sme se komitovati).

Real predmet_id <-> anonimizovana oznaka (CASE-01..) mapa se pise u
poseban lokalni fajl, takodje van repo-a.

Pokreni: python scripts/genome_bootstrap_sample.py <broj_uzoraka> <izlazni_dir>
Zahteva .env sa SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (ili _SERVICE_KEY).
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


def main(n: int, out_dir: str) -> int:
    _load_env()
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_SERVICE_KEY"]
    supa = create_client(url, key)

    sys.path.insert(0, str(ROOT))
    from shared.genome_validator import verify_genome

    res = supa.table("predmeti").select("id,naziv,case_dna").order("id", desc=True).limit(500).execute()
    rows = res.data or []

    candidates = []
    for r in rows:
        g = r.get("case_dna")
        if not isinstance(g, dict) or not g or g.get("greska"):
            continue
        if not g.get("verzija"):
            continue
        candidates.append(r)

    # Diverzitet: sortiraj po snaga_predmeta_procent, uzmi ravnomerno raspodeljene uzorke
    candidates.sort(key=lambda r: (r["case_dna"].get("snaga_predmeta_procent") or 0))
    total = len(candidates)
    if total == 0:
        print("Nema validnih Genome izlaza u poslednjih 500 predmeta.")
        return 1

    step = max(1, total // n)
    picked = candidates[::step][:n]

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    mapping = {}
    sample_records = []

    for i, r in enumerate(picked, start=1):
        label = f"CASE-{i:02d}"
        predmet_id = r["id"]
        mapping[label] = predmet_id

        dok_res = (
            supa.table("predmet_dokumenti")
            .select("naziv_fajla,redni_broj,tekst_sadrzaj,tip_dokaza")
            .eq("predmet_id", predmet_id)
            .order("redni_broj")
            .execute()
        )
        docs = dok_res.data or []
        docs_for_validator = [
            {"naziv_fajla": d.get("naziv_fajla"), "redni_broj": d.get("redni_broj")}
            for d in docs
        ]
        validator_result = verify_genome(r["case_dna"], docs_for_validator)

        sample_records.append({
            "label": label,
            "genome": r["case_dna"],
            "documents": [
                {
                    "naziv_fajla": d.get("naziv_fajla"),
                    "redni_broj": d.get("redni_broj"),
                    "tip_dokaza": d.get("tip_dokaza"),
                    "tekst_sadrzaj_excerpt": (d.get("tekst_sadrzaj") or "")[:6000],
                }
                for d in docs
            ],
            "validator_result": validator_result,
            "doc_count": len(docs),
        })

    (out_path / "genome_bootstrap_sample.json").write_text(
        json.dumps(sample_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_path / "genome_bootstrap_mapping_LOCAL_ONLY.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Kandidata sa validnim Genome: {total}")
    print(f"Odabrano (ravnomerno po snazi predmeta): {len(picked)}")
    print(f"Upisano: {out_path / 'genome_bootstrap_sample.json'}")
    return 0


if __name__ == "__main__":
    n_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    out_arg = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "_bootstrap_scratch")
    raise SystemExit(main(n_arg, out_arg))

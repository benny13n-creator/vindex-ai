# -*- coding: utf-8 -*-
"""
G-034 empirijska validacija (2026-07-22) — NE implementacija, NE odluka.

Cilj: proveriti da li Case Genome-ovi rizik-signali (snaga_predmeta_procent,
najslabija_tacka.kriticnost) i services/risk_engine.py::calculate_procesni_rizik
("procesni rizik", jedini deterministicki izvor posle G-027 fix-a) zaista
predstavljaju isti poslovni koncept za iste predmete, ili mere razlicite
stvari koje slucajno dele temu "rizik". Isti obrazac kao
scripts/g027_risk_validation.py (2026-07-20) — poziva STVARNE endpoint-e
in-process preko ASGI transporta, auth fake-ovan preko
app.dependency_overrides, nula promene aplikativnog koda.

NAMERNO ne racuna jedinstven "spojen" skor niti pokusava da normalizuje oba
signala na istu skalu unapred -- to bi ubacilo pristrasnost u samu analizu.
Umesto toga: sirovi podaci se prikazuju jedan pored drugog (isto kao G-027),
grupisu se predmeti po risk_engine kategoriji (Nizak/Srednji/Visok) i
racuna se prosecan Genome signal PO GRUPI. Ako Genome i risk_engine mere
isti koncept, ocekuje se monotona veza (Visok grupa -> niza prosecna snaga,
visa prosecna kriticnost). Ako nema monotone veze (ili je flat, isti obrazac
kao G-027 nalaz "Cockpit 16/16 isti odgovor"), to je dokaz da mere razlicite
stvari -- ODLUKA (spoji/razlikuj/ne diraj) dolazi POSLE ovog izvestaja, ne
pre, i ne u ovom skriptu.

Pise samo u vindex_scraper_output/g034_validation.json (van repo-a).
Ne menja nijedan red aplikativnog koda.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FOUNDER_USER_ID = "384a7149-938b-4b83-99e0-8d7524e0581a"
FOUNDER_EMAIL = "benny13.n@gmail.com"


async def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    import httpx
    import api as api_module
    from shared.deps import get_current_user
    from supabase import create_client

    supa = create_client(
        os.environ["SUPABASE_URL"],
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_SERVICE_KEY"],
    )

    predmeti = (
        supa.table("predmeti")
        .select("id,naziv,status,case_dna")
        .eq("user_id", FOUNDER_USER_ID)
        .order("created_at")
        .execute()
    ).data or []

    async def _fake_user():
        return {"user_id": FOUNDER_USER_ID, "email": FOUNDER_EMAIL}

    api_module.app.dependency_overrides[get_current_user] = _fake_user

    results = []
    try:
        transport = httpx.ASGITransport(app=api_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://g034harness") as client:
            headers = {"Authorization": "Bearer harness-token"}

            for p in predmeti:
                pid = p["id"]
                row: dict = {"predmet_id": pid, "naziv": p["naziv"]}

                genome = p.get("case_dna") or {}
                if isinstance(genome, dict) and genome and not genome.get("greska"):
                    row["genome_snaga_predmeta_procent"] = genome.get("snaga_predmeta_procent")
                    row["genome_kompletnost"] = genome.get("genome_kompletnost")
                    _nt = genome.get("najslabija_tacka") or {}
                    row["genome_najslabija_tacka_kriticnost"] = _nt.get("kriticnost")
                    row["genome_verzija"] = genome.get("verzija")
                else:
                    row["genome_snaga_predmeta_procent"] = None
                    row["genome_najslabija_tacka_kriticnost"] = None
                    row["genome_note"] = "nema Genome-a ili sadrzi gresku -- nije uporedivo"

                mi_resp = await client.get(f"/api/matter-intel/predmeti/{pid}", headers=headers)
                if mi_resp.status_code == 200:
                    mi = mi_resp.json()
                    row["risk_engine_nivo"] = mi.get("procesni_rizik")
                    row["risk_engine_health_score"] = mi.get("health_score")
                    row["risk_engine_snaga_dokaza"] = mi.get("snaga_dokaza")
                    row["risk_engine_nedostajuci_count"] = mi.get("nedostajuci_count")
                else:
                    row["risk_engine_error"] = f"{mi_resp.status_code}: {mi_resp.text[:200]}"

                results.append(row)
                print(f"  {pid[:8]} risk_engine={row.get('risk_engine_nivo')!s:8} "
                      f"genome_snaga={row.get('genome_snaga_predmeta_procent')!s:4} "
                      f"genome_kriticnost={row.get('genome_najslabija_tacka_kriticnost')!s:4}")
    finally:
        api_module.app.dependency_overrides.pop(get_current_user, None)

    # ── Grupisanje po risk_engine kategoriji — proseci Genome signala ─────────
    comparable = [r for r in results if r.get("genome_snaga_predmeta_procent") is not None
                  and r.get("risk_engine_nivo")]
    print(f"\n{len(comparable)}/{len(results)} predmeta uporedivo (imaju i Genome i risk_engine izlaz).")

    groups: dict = {}
    for r in comparable:
        nivo = r["risk_engine_nivo"]
        groups.setdefault(nivo, {"snaga": [], "kriticnost": []})
        groups[nivo]["snaga"].append(r["genome_snaga_predmeta_procent"])
        krit = r.get("genome_najslabija_tacka_kriticnost")
        if krit is not None:
            groups[nivo]["kriticnost"].append(krit)

    print("\n=== Prosecan Genome signal PO risk_engine kategoriji ===")
    print("(Ako isti koncept: Visok treba nizu snagu/visu kriticnost od Nizak. Ako flat/nemonotono: razliciti koncepti.)")
    summary = {}
    for nivo in ("Nizak", "Srednji", "Visok"):
        g = groups.get(nivo)
        if not g or not g["snaga"]:
            print(f"  {nivo:8} — nema uporedivih predmeta")
            continue
        avg_snaga = sum(g["snaga"]) / len(g["snaga"])
        avg_krit = sum(g["kriticnost"]) / len(g["kriticnost"]) if g["kriticnost"] else None
        summary[nivo] = {"n": len(g["snaga"]), "avg_genome_snaga": round(avg_snaga, 1),
                          "avg_genome_kriticnost": round(avg_krit, 1) if avg_krit is not None else None}
        print(f"  {nivo:8} (n={len(g['snaga'])})  prosek_snaga={avg_snaga:.1f}%  "
              f"prosek_kriticnost={avg_krit if avg_krit is not None else 'N/A'}")

    out_dir = ROOT / "vindex_scraper_output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "g034_validation.json"
    out_path.write_text(json.dumps({"po_predmetu": results, "grupisano": summary},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSacuvano: {out_path} ({len(results)} predmeta)")
    print("\nOVO JE ANALIZA, NE ODLUKA. Sledeci korak (posle founderovog pregleda "
          "rezultata): odluciti da li G-034 postaje implementacioni zadatak "
          "(D29) ili se zatvara kao 'razliciti koncepti, ne diraj'.")


if __name__ == "__main__":
    asyncio.run(main())

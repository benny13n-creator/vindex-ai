# -*- coding: utf-8 -*-
"""
G-027 empirijska validacija (2026-07-20) — NE implementacija.

Cilj: proveriti da li Matter Intelligence ("Procesni rizik") i Cockpit
("Procena rizika") zaista predstavljaju isti poslovni koncept za iste
predmete, ili se radi o dve razlicite metrike koje slucajno dele naziv
"rizik". Case Ready Score se meri uporedo kao kontrolna kolona (vec
utvrdjeno da meri kompletnost, ne rizik — proverava se da li se to
potvrdjuje na stvarnim podacima).

Poziva STVARNE endpoint-e (GET /api/matter-intel/predmeti/{id} i
GET /api/predmeti/{id}/workspace) in-process preko ASGI transporta —
ista logika kao scripts/genome_case_dna_evaluate.py — sa jednom
razlikom: auth se ovde fake-uje preko app.dependency_overrides na
shared.deps.get_current_user (obe rute zavise od nje, direktno ili
kroz PermissionService.require), ne preko patch-ovanja api._require_auth
(ta funkcija se koristi samo na POST create/upload rutama, ne ovde).

Ne menja nijedan red aplikativnog koda. Pise samo u
vindex_scraper_output/g027_validation.json (van repo-a).
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
        .select("id,naziv,status")
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
        async with httpx.AsyncClient(transport=transport, base_url="http://g027harness") as client:
            headers = {"Authorization": "Bearer harness-token"}

            for p in predmeti:
                pid = p["id"]
                row = {"predmet_id": pid, "naziv": p["naziv"]}

                mi_resp = await client.get(f"/api/matter-intel/predmeti/{pid}", headers=headers)
                if mi_resp.status_code == 200:
                    mi = mi_resp.json()
                    row["matter_risk_label"] = mi.get("procesni_rizik")
                    row["matter_health_score"] = mi.get("health_score")
                    row["matter_snaga_dokaza"] = mi.get("snaga_dokaza")
                    row["matter_nedostajuci_count"] = mi.get("nedostajuci_count")
                else:
                    row["matter_error"] = f"{mi_resp.status_code}: {mi_resp.text[:200]}"

                ws_resp = await client.get(f"/api/predmeti/{pid}/workspace", headers=headers)
                if ws_resp.status_code == 200:
                    ws = ws_resp.json()
                    cockpit = ws.get("cockpit") or {}
                    procena = cockpit.get("procena_rizika") or {}
                    row["cockpit_risk_label"] = procena.get("nivo")
                    row["cockpit_faktori_plus"] = procena.get("faktori_plus")
                    row["cockpit_faktori_minus"] = procena.get("faktori_minus")
                    row["cockpit_sazetak"] = cockpit.get("ai_sazetak")
                    row["case_ready_score"] = ws.get("case_ready_score")
                    row["checklist_done"] = sum(1 for c in (ws.get("checklist") or []) if c.get("done") or c.get("ok"))
                    row["checklist_total"] = len(ws.get("checklist") or [])
                else:
                    row["workspace_error"] = f"{ws_resp.status_code}: {ws_resp.text[:200]}"

                results.append(row)
                print(f"  {pid[:8]} matter={row.get('matter_risk_label')!s:8} "
                      f"cockpit={row.get('cockpit_risk_label')!s:8} "
                      f"crs={row.get('case_ready_score')!s:4} "
                      f"health={row.get('matter_health_score')!s:4}")
    finally:
        api_module.app.dependency_overrides.pop(get_current_user, None)

    out_dir = ROOT / "vindex_scraper_output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "g027_validation.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSacuvano: {out_path} ({len(results)} predmeta)")


if __name__ == "__main__":
    asyncio.run(main())

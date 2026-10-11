"""NS007 Task 24 — lokalna proba postavljanja: PRAVI uvicorn sa PRAVIM `api.app` nad lažnom bazom (isti proces).

Pokretanje: python tests/ns007_uvicorn_proba.py <port> [--spor] [--pad]
  --spor  ciklus traje 6 s (za proveru isteka vremena u okidaču)
  --pad   ciklus baca izuzetak (ruta vraća 500)
Tajna: AUTONOMY_CRON_SECRET iz okruženja. Ništa ne izlazi na mrežu (model i korpus zamenjeni).
"""
import asyncio
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _k, _v in (("OPENAI_API_KEY", "sk-fake-ns007"), ("PINECONE_API_KEY", "fake"), ("PINECONE_HOST", "https://fake.pinecone.io"),
               ("FOUNDER_EMAILS", "ci@example.com"), ("SUPABASE_URL", "https://fake.supabase.co"), ("SUPABASE_SERVICE_KEY", "x"),
               ("SUPABASE_ANON_KEY", "x"), ("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok"),
               ("FIELD_ENCRYPTION_KEY", "a" * 64)):
    os.environ.setdefault(_k, _v)

import logging  # noqa: E402
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402
import uvicorn  # noqa: E402

import tests.ns007_fake as f7  # noqa: E402
from tests import ns006_realni_predmet as rp  # noqa: E402
from tests import ns007_demo  # noqa: E402


def main():
    port = int(sys.argv[1])
    mp = pytest.MonkeyPatch()
    t = rp.tabele()
    t["rocista"][0]["datum"] = (date.today() + timedelta(days=1)).isoformat()
    t["agent_recommendations"] = []
    t.setdefault("kancelarija_clanovi", [])
    f7.pripremi(mp, t)
    from services.agent_tasks import hearing_prep as hp, precedents_radar as pr
    import openai
    import workers.background_agents as ba
    mp.setattr(ba, "_agent_modules", lambda: [hp, pr])
    mp.setattr(openai, "AsyncOpenAI", ns007_demo._provajder([]))
    os.environ.setdefault("AUTONOMY_BUDGET_PER_ORG_DAILY", "20")
    if "--spor" in sys.argv or "--pad" in sys.argv:
        pravi = ba.run_autonomy_cycle

        async def izmenjen(run_id):
            if "--pad" in sys.argv:
                raise RuntimeError("ciklus pao (proba)")
            await asyncio.sleep(6)
            return await pravi(run_id)
        mp.setattr(ba, "run_autonomy_cycle", izmenjen)
    import api
    print("SPREMAN", flush=True)
    uvicorn.run(api.app, host="127.0.0.1", port=port, log_level="error")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""NS005 Gate A2 — JEDAN zahtev iz ZASEBNOG OS procesa (nije pytest test).

Pokretanje (iz testa): python tests/ns005_a2_proces.py <pg|mem> <dsn> <kljuc> <kasnjenje_s> <izlaz.json>

Svaki proces ima SVOJ `api.app`, svoju memoriju i svoju lažnu poslovnu bazu; jedino deljeno
je skladište ključeva (`pg` = stvaran PostgreSQL iz migracije 134; `mem` = memorija procesa,
negativna kontrola). Ruta je stvarna `/api/pitanje`; model (`api.pokreni`) i kredit
(`UsageService.consume`) su brojači — upisuje se koliko puta je ruta ZAISTA izvršena u ovom procesu.
"""
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)
import tests.conftest  # noqa: E402,F401  (isto okruženje kao pytest: lažni ključevi, bez .env tajni)

import pytest  # noqa: E402

from tests.ns005_harness import pripremi, zaglavlje  # noqa: E402
from tests.ns005_pg_skladiste import MemorijaSkladiste, PgSkladiste  # noqa: E402


def main():
    vrsta, dsn, kljuc, kasnjenje, izlaz = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), sys.argv[5]
    mp = pytest.MonkeyPatch()
    k, b = pripremi(mp, {"predmeti": [{"id": "pred-A-1", "user_id": "uid-A", "naziv": "P", "status": "aktivan"}], "predmet_istorija": []})
    import api
    import shared.idempotency as idem
    import shared.permissions as perm
    import shared.usage as us
    brojaci = {"model": 0, "kredit": 0}

    async def _politika(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

    async def _nista(*a, **kw):
        return None

    async def _kredit(*a, **kw):
        brojaci["kredit"] += 1
        return 10

    async def _pokreni(fn, *a, **kw):
        brojaci["model"] += 1
        time.sleep(kasnjenje)
        return {"status": "success", "data": "--- PRAVNI ZAKLJUČAK\nOdgovor.", "confidence": "HIGH", "top_score": 0.8,
                "confidence_detail": {"nivo": "HIGH"}, "izvori": [{"zakon": "zakon o obligacionim odnosima", "clan": "Član 200"}]}

    mp.setattr(perm, "get_policy", _politika)
    mp.setattr(perm, "_check_dependencies", _nista)
    mp.setattr(us.UsageService, "consume", staticmethod(_kredit))
    mp.setattr(us.UsageService, "refund", staticmethod(_nista))
    mp.setattr(api, "_fetch_firm_memory_context", _nista, raising=False)
    mp.setattr(api, "_get_firma_namespace", _nista, raising=False)
    mp.setattr(api, "klasifikuj_pitanje", lambda *a, **kw: "opste", raising=False)
    mp.setattr(api, "pokreni", _pokreni)
    idem.postavi_skladiste((lambda: PgSkladiste(dsn)) if vrsta == "pg" else MemorijaSkladiste)
    r = k.post("/api/pitanje", json={"pitanje": "Koji je rok zastarelosti?"}, headers={**zaglavlje("A"), "Idempotency-Key": kljuc})
    with open(izlaz, "w", encoding="utf-8") as f:
        json.dump({"status": r.status_code, "replay": r.headers.get("idempotent-replayed"), "kod": (r.json() or {}).get("kod") if r.headers.get("content-type", "").startswith("application/json") else None,
                   **brojaci}, f)
    mp.undo()


if __name__ == "__main__":
    main()

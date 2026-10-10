"""NS006 — izvozi STVARNE odgovore backend ruta za realističan predmet (tests/ns006_realni_predmet.py),
da UI testovi (frontend-v2-ng/tests/live-analiza.mjs) proveravaju ugovor koji backend zaista vraća,
a ne ručno napisan JSON.

Pokretanje: `python tests/ns006_ui_fixture.py` → JSON na stdout (jedan red, prefiks `@@`).
Akcije predmeta pravi STVARNI reconcile (`_consequence_refresh_case_actions`) sa događajem E-V4;
ugovor, promene, akcije i tabla dolaze iz STVARNIH ruta kroz TestClient nad lažnom bazom.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _k, _v in (("OPENAI_API_KEY", "sk-fake-ns006"), ("PINECONE_API_KEY", "fake"), ("PINECONE_HOST", "https://fake.pinecone.io"),
               ("FOUNDER_EMAILS", "ci@example.com"), ("SUPABASE_URL", "https://fake.supabase.co"), ("SUPABASE_SERVICE_KEY", "x"),
               ("SUPABASE_ANON_KEY", "x"), ("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok"),
               ("FIELD_ENCRYPTION_KEY", "a" * 64)):
    os.environ.setdefault(_k, _v)

import logging  # noqa: E402
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402

from tests import ns006_realni_predmet as rp  # noqa: E402
from tests.ns006_fake import pripremi, ocisti, zaglavlje  # noqa: E402


def main(pad: str | None = None) -> dict:
    mp = pytest.MonkeyPatch()
    try:
        k, baza = pripremi(mp, rp.tabele())
        from services.case_evolution import _consequence_refresh_case_actions
        from services.event_bus import Event, EventType
        asyncio.run(_consequence_refresh_case_actions(Event(
            type=EventType.DOCUMENT_ACCEPTED, user_id="uid-A", predmet_id=rp.PA, payload={}, event_id=rp.DOGADJAJ_V4)))
        if pad:   # izvor koji „pada" POSLE reconcile-a: čitanje mora reći DEGRADED, ne prazno
            baza.greske[pad] = RuntimeError("izvor nedostupan (fixture)")
        out = {"PA": rp.PA, "PB": rp.PB, "D1": rp.D1, "D2": rp.D2, "D3": rp.D3, "odgovori": {}}
        for kor, pid in (("A", rp.PA), ("B", rp.PB), ("B", rp.PA)):
            for ruta in ("/api/predmeti/{p}/genome-v2", "/api/predmeti/{p}/genome-v2/promene", "/api/case-actions/predmeti/{p}"):
                r = k.get(ruta.format(p=pid), headers=zaglavlje(kor))
                telo = r.json()
                if isinstance(telo, dict):
                    telo.pop("procitano", None)
                out["odgovori"][f"{kor}|{ruta.format(p=pid)}"] = {"status": r.status_code, "telo": telo}
        for kor in ("A", "B"):
            r = k.get("/api/workspace", headers=zaglavlje(kor))
            out["odgovori"][f"{kor}|/api/workspace"] = {"status": r.status_code, "telo": r.json()}
        pisanja = [z for z in baza.dnevnik if z["radnja"] in ("insert", "update", "upsert", "delete") and z["tabela"] != "case_actions"]
        out["pisanja_van_reconcile"] = len(pisanja)
        return out
    finally:
        ocisti()
        mp.undo()


if __name__ == "__main__":
    _pad = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--pad=")), None)
    print("@@" + json.dumps(main(_pad), ensure_ascii=False))

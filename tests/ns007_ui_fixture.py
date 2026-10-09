"""NS007 — STVARNI odgovori backend-a posle STVARNOG autonomnog ciklusa, za V2 UI testove (frontend-v2-ng/tests/live-pripremljeno.mjs).

Realističan predmet (tests/ns006_realni_predmet.py), ročište sutra + proverena preporuka Precedents Radar-a; ciklus
`run_autonomy_cycle` nad lažnom bazom, modeli zamenjeni (čitaju pravi prompt), korpus odluka = lažan Pinecone indeks.
Izvoz: tabla A/B, liste rada, detalji, tuđ detalj (404), promene/case-actions za Pregled, pa odgovori prihvatanja i
odbijanja (posle izvoza čitanja). Pokretanje: `python tests/ns007_ui_fixture.py` → jedan red `@@{json}`.
"""
import asyncio
import json
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _k, _v in (("OPENAI_API_KEY", "sk-fake-ns007"), ("PINECONE_API_KEY", "fake"), ("PINECONE_HOST", "https://fake.pinecone.io"),
               ("FOUNDER_EMAILS", "ci@example.com"), ("SUPABASE_URL", "https://fake.supabase.co"), ("SUPABASE_SERVICE_KEY", "x"),
               ("SUPABASE_ANON_KEY", "x"), ("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok"),
               ("FIELD_ENCRYPTION_KEY", "a" * 64)):
    os.environ.setdefault(_k, _v)
os.environ["AUTONOMY_BUDGET_PER_ORG_DAILY"] = "10"

import logging  # noqa: E402
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402

import tests.ns007_fake as f7  # noqa: E402
from tests import ns006_realni_predmet as rp  # noqa: E402
from tests import ns007_korpus as kor  # noqa: E402


def _model_rocista(prompt, pid):
    ids = re.findall(r"\[([0-9a-f-]{36}|ai:[0-9a-f]+)\]", prompt)
    kontr = next(i for i in ids if i.startswith("ffff"))
    return json.dumps({"pitanja": [{"tekst": "Proveriti koji je datum uručenja tačan pre ročišta.", "refs": [kontr]}],
                       "beleske": [{"tekst": "Pripremiti dostavnicu kao dokaz o datumu uručenja.", "refs": [ids[1]]}]}, ensure_ascii=False)


def _model_uticaja(prompt, pid):
    k = re.findall(r"\[(ffff[^\]]+)\]", prompt)[0]
    return json.dumps({"klasifikacija": "u_prilog",
                       "uticaj": [{"tekst": "Odluka daje prednost datumu iz dostavnice — podupire tvrdnju o kasnijem uručenju.",
                                   "refs": [k], "izvod": "dan uručenja utvrđen u dostavnici ima prednost nad datumom navedenim u samom rešenju"}],
                       "pitanja": [{"tekst": "Da li je dostavnica potpisana lično od klijenta?", "refs": [k]}],
                       "razmotriti_argument": {"da": True, "razlog": "Argument o roku za tužbu vezati za datum iz dostavnice."}},
                      ensure_ascii=False)


def main() -> dict:
    mp = pytest.MonkeyPatch()
    try:
        danas = date.today()
        t = rp.tabele(danas=danas)
        t["rocista"][0].update(datum=(danas + timedelta(days=1)).isoformat(), sudnica="12")
        t["agent_recommendations"] = [{
            "id": "dddd0001-0000-4000-8000-000000000001", "user_id": "uid-A", "predmet_id": rp.PA, "agent_type": "precedents_radar",
            "status": "pending", "naslov": "Nova praksa", "dedup_key": f"precedent:{rp.PA}:{kor.ODLUKA}",
            "created_at": "2099-01-01T00:00:00+00:00",
            "payload": {"odnos": "podupire", "obrazlozenje": "Odluka o dostavi rešenja.",
                        "odluka": {"decision_number": kor.ODLUKA, "court": "Vrhovni sud", "date": "2023-05-10", "matter": "radno"}}}]
        t.setdefault("kancelarija_clanovi", [])
        k, baza = f7.pripremi(mp, t)
        kor.postavi(mp)
        from services.agent_tasks import hearing_prep as hp, precedents_radar as pr
        import workers.background_agents as ba

        async def m1(p, pid):
            return _model_rocista(p, pid)

        async def m2(p, pid):
            return _model_uticaja(p, pid)
        mp.setattr(hp, "_pozovi_model", m1)
        mp.setattr(pr, "_pozovi_model_uticaj", m2)
        mp.setattr(ba, "_agent_modules", lambda: [hp, pr])
        sazetak = asyncio.run(ba.run_autonomy_cycle("ui-fixture"))
        radovi = {r["work_type"]: r["id"] for r in baza.tabele["autonomy_work_items"]}

        out = {"PA": rp.PA, "PB": rp.PB, "radovi": radovi, "sazetak": sazetak, "odgovori": {}}

        def uzmi(kor_, put, metod="GET", telo=None):
            h = f7.zaglavlje(kor_)
            r = k.get(put, headers=h) if metod == "GET" else k.post(put, headers=h, json=telo)
            tel = r.json()
            if isinstance(tel, dict):
                tel.pop("procitano", None)
                tel.pop("generisano", None)
            out["odgovori"][f"{kor_}|{metod}|{put}"] = {"status": r.status_code, "telo": tel}

        for ko in ("A", "B"):
            uzmi(ko, "/api/workspace")
            uzmi(ko, "/api/autonomy/work-items")
        uzmi("A", f"/api/autonomy/work-items?matter_id={rp.PA}")
        uzmi("B", f"/api/autonomy/work-items?matter_id={rp.PB}")
        for wid in radovi.values():
            uzmi("A", f"/api/autonomy/work-items/{wid}")
            uzmi("B", f"/api/autonomy/work-items/{wid}")
        for ko, pid in (("A", rp.PA), ("B", rp.PB)):
            uzmi(ko, f"/api/predmeti/{pid}/genome-v2/promene")
            uzmi(ko, f"/api/case-actions/predmeti/{pid}")
        pre = len(baza.dnevnik)
        uzmi("A", f"/api/autonomy/work-items/{radovi['HEARING_PREP']}/accept", "POST")
        uzmi("A", f"/api/autonomy/work-items/{radovi['PRECEDENT_IMPACT']}/reject", "POST", {"razlog": "Nije relevantno."})
        spoljni = [z for z in baza.dnevnik[pre:] if z["radnja"] in ("insert", "update", "upsert", "delete")
                   and z["tabela"] not in ("autonomy_work_items", "v2_mutation_idempotency", "audit_immutable")]
        out["upisi_van_pregleda"] = len(spoljni)
        return out
    finally:
        f7.ocisti()
        mp.undo()


if __name__ == "__main__":
    print("@@" + json.dumps(main(), ensure_ascii=False, default=str))

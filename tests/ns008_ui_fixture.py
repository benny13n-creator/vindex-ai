"""NS008 — STVARNI odgovori Law Brain ruta za V2 UI testove (frontend-v2-ng/tests/live-law-brain.mjs).

Ista lažna baza i isti podaci kao tests/test_ns008_t11_api.py (A i B u istoj kancelariji; A ima zatvoren sličan
predmet sa ljudskim ishodom, overen rad, potvrđenu i predloženu lekciju; kancelarija ima belešku o sudiji).
Odgovori su ono što STVARNE rute vrate kroz TestClient — ne ručno pisan JSON. Model sinteze je zamenjen
funkcijom koja čita pravi prompt (reference) i vraća i ispravne i neispravne tvrdnje.
Pokretanje: `python tests/ns008_ui_fixture.py` → jedan red `@@{json}`.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _k, _v in (("OPENAI_API_KEY", "sk-fake-ns008"), ("PINECONE_API_KEY", "fake"), ("PINECONE_HOST", "https://fake.pinecone.io"),
               ("FOUNDER_EMAILS", "ci@example.com"), ("SUPABASE_URL", "https://fake.supabase.co"), ("SUPABASE_SERVICE_KEY", "x"),
               ("SUPABASE_ANON_KEY", "x"), ("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok"),
               ("FIELD_ENCRYPTION_KEY", "a" * 64)):
    os.environ.setdefault(_k, _v)

import logging  # noqa: E402
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402

import tests.ns008_fake as f8  # noqa: E402
from tests.test_ns008_t11_api import PA_CUR, PA_OLD, PB_CUR, _tabele  # noqa: E402

W_ACC = "eeee0001-1515-4000-8000-000000000001"
W_READY = "eeee0002-1515-4000-8000-000000000002"


def _model(prompt, pid):
    refs = dict(re.findall(r"^(R\d+) (\[[A-Z_]+\].*)$", prompt, re.M))
    ishod = next(r for r, t in refs.items() if "HUMAN_CONFIRMED_OUTCOME" in t)
    slican = next(r for r, t in refs.items() if "Raniji predmet 1" in t)
    rad = next(r for r, t in refs.items() if "Overen rad" in t)
    return json.dumps({"tvrdnje": [
        {"tekst": "Raniji predmet kancelarije je iste vrste i vođen je pred istim sudom.", "vrsta": "iskustvo", "refs": [slican]},
        {"tekst": "U tom predmetu ishod je bio nagodba, prema unosu advokata.", "vrsta": "ishod", "refs": [ishod]},
        {"tekst": "Overena tužba iz tog predmeta može poslužiti kao polazna osnova.", "vrsta": "overen_rad", "refs": [rad]},
        {"tekst": "Šansa za uspeh je 80%.", "vrsta": "iskustvo", "refs": [slican]},
        {"tekst": "Izmišljen predmet.", "vrsta": "ishod", "refs": ["R99"]},
    ]}, ensure_ascii=False)


def main() -> dict:
    mp = pytest.MonkeyPatch()
    try:
        t = _tabele()
        t["autonomy_work_items"] = [
            {"id": W_ACC, "user_id": "uid-A", "predmet_id": PA_CUR, "work_type": "HEARING_PREP", "status": "ACCEPTED",
             "title": "Priprema za ročište", "summary": "Šta proveriti.", "dedupe_key": "k1", "reason": "Ročište sutra",
             "ready_at": "2026-10-10T03:00:00+00:00", "quality_state": "AI_PREPARED_FOR_REVIEW",
             "content_json": {"rociste": {"datum": "2026-10-11"}, "pitanja": [{"tekst": "Proveriti datum uručenja.", "refs": ["x"]}]}},
            {"id": W_READY, "user_id": "uid-A", "predmet_id": PA_CUR, "work_type": "HEARING_PREP", "status": "READY_FOR_REVIEW",
             "title": "Druga priprema", "summary": "x", "dedupe_key": "k2", "reason": "r", "ready_at": "2026-10-10T03:00:00+00:00",
             "quality_state": "AI_PREPARED_FOR_REVIEW", "content_json": {"rociste": {"datum": "2026-10-11"}}}]
        k, baza = f8.pripremi(mp, t)
        import services.quality_gate as qg

        async def _kvalitet(tekst, tip=""):
            return {"confidence_score": 0.9, "detail": {}}
        mp.setattr(qg, "evaluate_draft_quality", _kvalitet)
        import shared.permissions as perm
        import shared.usage as us
        import services.law_brain_sinteza as S

        async def _politika(feature):
            return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

        async def _nista(*a, **kw):
            return None
        krediti = []

        async def _naplati(*a, **kw):
            krediti.append(a[2] if len(a) > 2 else None)
        pozivi = []

        async def _m(prompt, pid):
            pozivi.append(pid)
            return _model(prompt, pid)
        mp.setattr(perm, "get_policy", _politika)
        mp.setattr(perm, "_check_dependencies", _nista)
        mp.setattr(us.UsageService, "consume", staticmethod(_naplati))
        mp.setattr(S, "_pozovi_model_sinteze", _m)

        out = {"PA_CUR": PA_CUR, "PA_OLD": PA_OLD, "PB_CUR": PB_CUR, "W_ACC": W_ACC, "W_READY": W_READY, "odgovori": {}}

        def uzmi(ko, put, metod="GET", kljuc=None, oznaka=""):
            h = f8.zaglavlje(ko)
            r = k.get(put, headers=h) if metod == "GET" else k.post(put, headers=h)
            out["odgovori"][f"{ko}|{metod}|{put}{oznaka}"] = {"status": r.status_code, "telo": r.json()}

        for ko in ("A", "B"):
            uzmi(ko, "/api/law-brain/znanje")
        uzmi("A", f"/api/law-brain/predmeti/{PA_CUR}")
        uzmi("B", f"/api/law-brain/predmeti/{PB_CUR}")
        uzmi("B", f"/api/law-brain/predmeti/{PA_CUR}")
        pre_modela = len(pozivi)
        uzmi("A", f"/api/law-brain/predmeti/{PA_CUR}/sinteza", "POST")
        uzmi("B", f"/api/law-brain/predmeti/{PB_CUR}/sinteza", "POST")
        out["model_pozvan_pri_citanju"] = pre_modela
        out["model_pozvan_ukupno"] = len(pozivi)
        out["krediti"] = krediti
        for wid in (W_ACC, W_READY):
            uzmi("A", f"/api/autonomy/work-items/{wid}")
        uzmi("A", f"/api/law-brain/rad/{W_ACC}/predlozi-znanje", "POST")
        uzmi("A", f"/api/law-brain/rad/{W_ACC}/predlozi-znanje", "POST", oznaka="#ponovo")
        out["staging_posle_predloga"] = [{k_: r.get(k_) for k_ in ("status", "is_lawyer_approved", "pinecone_indexed", "tip")}
                                         for r in baza.tabele.get("staging_memory", []) if r.get("tip") == "pripremljen_rad"]
        baza.greske["memory_entries"] = Exception("down")
        uzmi("A", "/api/law-brain/znanje", oznaka="#degradirano")
        uzmi("A", f"/api/law-brain/predmeti/{PA_CUR}", oznaka="#degradirano")
        return out
    finally:
        f8.ocisti()
        mp.undo()


if __name__ == "__main__":
    print("@@" + json.dumps(main(), ensure_ascii=False, default=str))

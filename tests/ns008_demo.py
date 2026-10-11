"""NS008 jutarnji demo — „Kancelarija pamti" (Law Brain samostalno; Task 18 je namerno preskočen).

Isti scenario kao tests/test_ns008_t23_firm_remembers.py: istorija nastaje STVARNIM rutama, zatim se izvoze
STVARNI odgovori Law Brain ruta za V2 ekrane: Znanje, Analiza tekućeg predmeta, izričita sinteza i stanje posle
opoziva overene tužbe i lekcije. Model sinteze je zamena koja čita pravi prompt. Bez ikakvog spoljnog efekta.
Pokretanje: `python tests/ns008_demo.py --json` → jedan red `@@{json}` (bez --json: čitljiv sažetak).
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
from tests import ns008_scenario as sc  # noqa: E402


def _model(prompt, pid):
    r = dict(re.findall(r"^(R\d+) (\[[A-Z_]+\].*)$", prompt, re.M))
    pick = lambda frag: next((x for x, t in r.items() if frag in t), None)  # noqa: E731
    tv = []
    if pick("Raniji predmet 1"):
        tv.append({"tekst": "Kancelarija je vodila sličan spor o otkazu zbog povrede radne discipline pred istim sudom.",
                   "vrsta": "iskustvo", "refs": [pick("Raniji predmet 1")]})
    if pick("HUMAN_CONFIRMED_OUTCOME"):
        tv.append({"tekst": "U tom sporu advokat je zabeležio ishod pobeda; presudni su bili svedoci i pisana komunikacija.",
                   "vrsta": "ishod", "refs": [pick("HUMAN_CONFIRMED_OUTCOME")]})
    if pick("Overen rad"):
        tv.append({"tekst": "Overena tužba za poništaj rešenja o otkazu može poslužiti kao polazna osnova.",
                   "vrsta": "overen_rad", "refs": [pick("Overen rad")]})
    if pick("Potvrđena lekcija"):
        tv.append({"tekst": "Potvrđena praksa kancelarije: odmah pribaviti dostavnicu rešenja i svedoke vremena uručenja.",
                   "vrsta": "overen_rad", "refs": [pick("Potvrđena lekcija")]})
    tv.append({"tekst": "Šansa za uspeh je 80%.", "vrsta": "iskustvo", "refs": [pick("Raniji predmet 1") or "R1"]})
    return json.dumps({"tvrdnje": tv}, ensure_ascii=False)


def main() -> dict:
    mp = pytest.MonkeyPatch()
    try:
        k, b = f8.pripremi(mp, sc.tabele())
        import routers.drafting as drafting
        import shared.permissions as perm
        import shared.usage as us
        import services.law_brain_sinteza as S
        krediti, modeli = [], []

        async def _promote(supa, row):
            return True

        async def _pol(feature):
            return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

        async def _nista(*a, **kw):
            return None

        async def _kredit(*a, **kw):
            krediti.append(a[2] if len(a) > 2 else None)

        async def _m(prompt, pid):
            modeli.append(pid)
            return _model(prompt, pid)
        mp.setattr(drafting, "_promote_staged_draft_to_pinecone", _promote)
        mp.setattr(perm, "get_policy", _pol)
        mp.setattr(perm, "_check_dependencies", _nista)
        mp.setattr(us.UsageService, "consume", staticmethod(_kredit))
        mp.setattr(S, "_pozovi_model_sinteze", _m)
        istorija = {n: r.status_code for n, r in sc.pripremi_istoriju(k, f8.zaglavlje).items()}

        out = {"CUR": sc.CUR, "OLD1": sc.OLD1, "OLD2": sc.OLD2, "istorija": istorija, "odgovori": {}}

        def uzmi(put, metod="GET", oznaka=""):
            h = f8.zaglavlje("A")
            r = k.get(put, headers=h) if metod == "GET" else (k.post(put, headers=h) if metod == "POST" else None)
            out["odgovori"][f"A|{metod}|{put}{oznaka}"] = {"status": r.status_code, "telo": r.json()}

        uzmi("/api/law-brain/znanje")
        uzmi(f"/api/law-brain/predmeti/{sc.CUR}")
        out["model_pre_klika"] = len(modeli)
        uzmi(f"/api/law-brain/predmeti/{sc.CUR}/sinteza", "POST")
        k.post(f"/api/staging/{sc.S_TUZBA}/reject", headers=f8.zaglavlje("A"))
        k.patch(f"/api/learning/lessons/{sc.L_POTVRDJENA}/potvrdi", headers=f8.zaglavlje("A"), json={"akcija": "odbaci"})
        uzmi(f"/api/law-brain/predmeti/{sc.CUR}", oznaka="#posle-opoziva")
        uzmi(f"/api/law-brain/predmeti/{sc.CUR}/sinteza", "POST", oznaka="#posle-opoziva")
        out["model_ukupno"], out["krediti"] = len(modeli), krediti
        return out
    finally:
        f8.ocisti()
        mp.undo()


if __name__ == "__main__":
    rez = main()
    if "--json" in sys.argv:
        print("@@" + json.dumps(rez, ensure_ascii=False, default=str))
    else:
        c = rez["odgovori"][f"A|GET|/api/law-brain/predmeti/{rez['CUR']}"]["telo"]
        print("Slični:", [s["naziv"] + " — " + s["zasto"] for s in c["similar_cases"]["stavke"]])
        print("Overeni radovi:", [a["title"] for a in c["verified_artifacts"]["stavke"]])
        print("Potvrđene lekcije:", [x["excerpt"] for x in c["confirmed_lessons"]["stavke"]])
        print("Ishodi:", c["descriptive_outcomes"]["recenice"])
        print("Model pre klika:", rez["model_pre_klika"], "| ukupno:", rez["model_ukupno"], "| krediti:", rez["krediti"])

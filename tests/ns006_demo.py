"""NS006 — jutarnji demo za foundera (< 5 minuta): „Vindex je razumeo promenu predmeta pre nego što smo pitali."

Pokretanje:  python tests/ns006_demo.py           → priča korak po korak (samo test podaci, lažna baza, 0 mrežnih poziva)
             python tests/ns006_demo.py --json    → isto, plus STVARNI odgovori ruta posle promene (za snimke ekrana:
                                                    frontend-v2-ng/tests/ns006-demo.mjs → shots/ns006-demo/)

Predmet: Marko Petrović protiv „Gradnja Invest" DOO (izmišljen radni spor). Prvo stiže rešenje o otkazu i advokat ručno
dodaje tvrdnju. Zatim stiže DOSTAVNICA, koja kaže da je rešenje uručeno 25.03 — a rešenje kaže 17.03.
NIKO ne klikće „osveži analizu": prijem dokumenta ostavlja isti trajni događaj kao `api.py` upload, a kanonski
dispečer (isti koji DispatchLoop zove na 3 s) sam pokreće analizu, V2 protivrečnost i radnje.
Zamenjeni su SAMO modeli (klasifikacija iz stvarnog teksta, Genome iz stvarnog prompta) — da demo bude ponovljiv.
"""
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
from tests.test_ns006_t14_realni_predmet import _tabele, _klasifikuj, _genome_model, _prijem  # noqa: E402

PA = rp.PA
SPREMNOST = {"READY": "spremno", "PARTIALLY_READY": "delimično spremno", "BLOCKED": "blokirano (otvorene radnje visokog prioriteta)",
             "CRITICAL_GAP": "kritičan nedostatak (otvorena kritična radnja)", "UNKNOWN": "nepoznato"}
JSON = "--json" in sys.argv
_izlaz = sys.stderr if JSON else sys.stdout


def reci(t=""):
    print(t, file=_izlaz)


def stanje(k):
    ziv = k.get(f"/api/predmeti/{PA}/genome-v2", headers=zaglavlje("A")).json()
    akc = k.get(f"/api/case-actions/predmeti/{PA}", headers=zaglavlje("A")).json()
    dims = {d["kljuc"]: d for d in ziv["spremnost"]["dimenzije"]}
    return {"verzija": ziv["metapodaci"]["genome_verzija"],
            "tvrdnje": {t["id"]: t for t in ziv["dokazi"]["tvrdnje"]},
            "kontr": ziv["kontradikcije"]["aktivne"],
            "spremnost": dims["operativna_spremnost"]["vrednost"],
            "kontr_dim": dims["kontradikcije"]["vrednost"],
            "akcije": {a["id"]: a for a in akc["akcije"]}}


def main():
    mp = pytest.MonkeyPatch()
    pozivi_modela = []
    try:
        k, baza = pripremi(mp, _tabele())
        import routers.case_dna as cd
        import routers.evidence as ev
        mp.setattr(cd, "_pozovi_genome_api", _genome_model(pozivi_modela))
        mp.setattr(ev, "_klasifikuj_dokument", _klasifikuj)

        reci("VINDEX NS006 — DEMO: ŽIVI PREDMET")
        reci("Predmet: Marko Petrović protiv „Gradnja Invest“ DOO (test podaci)\n")

        # 1–2. predmet pre promene
        _prijem(baza, rp.D1, "Rešenje o otkazu.pdf", 1, rp.TEKST_D1)
        k.post(f"/api/evidence/predmeti/{PA}/dokaz", json={"tvrdnja": "Klijent tvrdi da rešenje o otkazu nije primio lično.",
                                                         "pravni_element": "uručenje"}, headers=zaglavlje("A"))
        from tests.ns006_fake import dispecuj
        dispecuj()
        pre = stanje(k)
        reci(f"1. PRE PROMENE  — u spisu: Rešenje o otkazu; advokat je ručno dodao jednu tvrdnju.")
        reci(f"2. ANALIZA v{pre['verzija']} — tvrdnji: {len(pre['tvrdnje'])}, protivrečnosti: {len(pre['kontr'])}, "
             f"otvorenih radnji: {len(pre['akcije'])}, operativna spremnost: {SPREMNOST[pre['spremnost']]}")

        # 3–5. materijalna promena, BEZ ručnog osvežavanja
        reci("\n3. STIŽE NOV DOKUMENT: Dostavnica.pdf (ista putanja kao upload u aplikaciji)")
        reci("4. Niko ne klikće „osveži analizu“.")
        modela_pre = len(pozivi_modela)
        _prijem(baza, rp.D2, "Dostavnica.pdf", 2, rp.TEKST_D2)
        dogadjaji = [e for e in baza.tabele["events"] if e["event_type"] == "DocumentAccepted"]
        reci(f"5. Kanonski tok je sam obradio događaj {dogadjaji[-1]['id'][:8]}… "
             f"(posledice: {', '.join(sorted({c['consequence_name'] for c in baza.tabele['case_evolution_consequences'] if c['event_id'] == dogadjaji[-1]['id']}))})")

        posle = stanje(k)
        pr = k.get(f"/api/predmeti/{PA}/genome-v2/promene", headers=zaglavlje("A")).json()
        reci(f"\n6. ANALIZA v{pre['verzija']} → v{posle['verzija']}  (model pozvan {len(pozivi_modela) - modela_pre}× za ovaj dokument, ni jednom pri čitanju)")
        reci("7. ŠTA SE PROMENILO:")
        for p in pr["promene"]:
            reci(f"     {p['oznaka']} {p['opis']}")
        nove = [t for i, t in posle["tvrdnje"].items() if i not in pre["tvrdnje"]]
        reci(f"8. DOKAZI: {len(pre['tvrdnje'])} → {len(posle['tvrdnje'])} tvrdnji; nove iz dostavnice:")
        for t in nove:
            lok = t.get("lokacija") or {}
            reci(f"     „{t['vrednost']}“ — {t['poreklo']}, približno str. {lok.get('strana_procena', '?')}")
        for x in posle["kontr"]:
            reci(f"9. PROTIVREČNOST: {x['sporna_tacka']} ({x['tezina']})")
            for u in x["ucesnici"]:
                reci(f"     • „{u['tvrdnja']}“")
        kd = posle["kontr_dim"]
        reci(f"10. SPREMNOST: {SPREMNOST[pre['spremnost']]} → {SPREMNOST[posle['spremnost']]}")
        reci(f"     protivrečnosti: {kd['aktivnih']} aktivna, {kd['kriticnih']} kritična (pravilo nad radnjama, ne procena ishoda)")
        reci("11. RADNJE (svaka nosi događaj koji ju je proizvela):")
        for a in posle["akcije"].values():
            novo = "NOVO " if a["id"] not in pre["akcije"] else "      "
            reci(f"     {novo}[{a['prioritet']}] {a['tip']} — {a['razlog']}")
        reci("\n12–15. V2 ekrani (Analiza, Pregled, Danas): node frontend-v2-ng/tests/ns006-demo.mjs → shots/ns006-demo/")
        reci("\nZAKLJUČAK: dokument je promenio predmet; Vindex je sam ažurirao analizu, dokaze, protivrečnost,")
        reci("spremnost i radnje — pre nego što je iko pitao. Nijedan broj nije verovatnoća ishoda.")

        if JSON:
            out = {"PA": PA, "PB": rp.PB, "D1": rp.D1, "D2": rp.D2, "D3": rp.D3, "odgovori": {}}
            for kor, pid in (("A", PA), ("B", rp.PB), ("B", PA)):
                for ruta in ("/api/predmeti/{p}/genome-v2", "/api/predmeti/{p}/genome-v2/promene", "/api/case-actions/predmeti/{p}"):
                    r = k.get(ruta.format(p=pid), headers=zaglavlje(kor))
                    out["odgovori"][f"{kor}|{ruta.format(p=pid)}"] = {"status": r.status_code, "telo": r.json()}
            for kor in ("A", "B"):
                r = k.get("/api/workspace", headers=zaglavlje(kor))
                out["odgovori"][f"{kor}|/api/workspace"] = {"status": r.status_code, "telo": r.json()}
            print("@@" + json.dumps(out, ensure_ascii=False))
    finally:
        ocisti()
        mp.undo()


if __name__ == "__main__":
    main()

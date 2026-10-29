"""CG001 — STVARNI odgovori backend ruta za zatečeno produkciono stanje incidenta „Evidencija uplate“
(V2 {A,B} sačuvano, Genome v1 → v2 sa {A,C,D}), za frontend-v2-ng/tests/live-cg001-kontinuitet.mjs.

Pokretanje: `python tests/cg001_ui_fixture.py` → JSON na stdout (jedan red, prefiks `@@`). Refresh ide istim putem kao u
produkciji (DOCUMENT_ACCEPTED → genome_refresh → refresh_case_actions); odgovori dolaze iz STVARNIH ruta (TestClient).
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _k, _v in (("OPENAI_API_KEY", "sk-fake-cg001"), ("PINECONE_API_KEY", "fake"), ("PINECONE_HOST", "https://fake.pinecone.io"),
               ("FOUNDER_EMAILS", "ci@example.com"), ("SUPABASE_URL", "https://fake.supabase.co"), ("SUPABASE_SERVICE_KEY", "x"),
               ("SUPABASE_ANON_KEY", "x"), ("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok"),
               ("FIELD_ENCRYPTION_KEY", "a" * 64)):
    os.environ.setdefault(_k, _v)

import logging  # noqa: E402
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402

from tests.ns006_fake import dispecuj, ocisti, pripremi, zaglavlje  # noqa: E402
from tests import test_cg001_lanac as L  # noqa: E402
from tests.test_cg001_incident_uplata import A, B, D1, D2, KONTR, P, dokazi_v2  # noqa: E402


def main() -> dict:
    mp = pytest.MonkeyPatch()
    try:
        g1 = {"verzija": 1, "_analiza_osnov": {"cinjenica": 7, "dokumenata": 2}, "kontradikcije": [{
            "opis": "TEST 01 navodi uplatu od 40.000 RSD, dok TEST 02 prikazuje 30.000 RSD.", "tezina": "manja",
            "claim_ids": sorted([A, B]), "claim_refs": ["CLAIM-004", "CLAIM-002"], "lokacija_1": "DOK-01", "lokacija_2": "DOK-02",
            "issue_label": L.LABEL, "dokument_id_1": D1, "dokument_id_2": D2, "relation_type": "cinjenica_cinjenica"}]}
        k, baza = pripremi(mp, L._tabele(dokazi_v2(), v2_ab=True, case_dna=g1))
        import routers.case_dna as cd
        pozivi = []
        mp.setattr(cd, "_pozovi_genome_api", L._model(pozivi))
        from services.v2_projection import u_akcije, ucitaj_v2_kontradikcije
        baza.tabele["case_actions"] = [{**a, "id": "akc-1", "predmet_id": P, "status": "open", "kreirao": "system",
                                        "updated_at": "2026-10-28T21:58:47Z", "created_at": "2026-10-28T21:58:26Z"}
                                       for a in u_akcije(asyncio.run(ucitaj_v2_kontradikcije(baza, P)))]
        L._refresh(cd, baza, pozivi)
        n_poziva = len(pozivi)
        out = {"P": P, "D1": D1, "D2": D2, "KONTR": KONTR, "odgovori": {}}
        for kor in ("A", "B"):
            for ruta in ("/api/predmeti/{p}/genome-v2", "/api/predmeti/{p}/genome-v2/promene", "/api/case-actions/predmeti/{p}"):
                r = k.get(ruta.format(p=P), headers=zaglavlje(kor))
                telo = r.json()
                if isinstance(telo, dict):
                    telo.pop("procitano", None)
                out["odgovori"][f"{kor}|{ruta.format(p=P)}"] = {"status": r.status_code, "telo": telo}
        out["model_pozvan_pri_citanju"] = len(pozivi) - n_poziva
    finally:
        ocisti()
        mp.undo()
    out["bez_dogadjaja"] = bez_dogadjaja()
    return out


def bez_dogadjaja() -> dict:
    """CG001 Task 1 — odmah posle deploy-a: `case_dna` je već v2 {A,C,D}, radnja upisana STARIM kodom, nijedan
    događaj ni reconcile. Odgovori svih primarnih površina, i dokaz da čitanje ništa nije upisalo."""
    import copy
    mp = pytest.MonkeyPatch()
    try:
        import routers.case_dna as cd
        pozivi = []

        def otvori(tabele):
            k, baza = pripremi(mp, tabele)
            mp.setattr(cd, "_pozovi_genome_api", L._model(pozivi))
            return k, baza, cd
        k, baza = L._zateceno(otvori, L._g(2, [L.A, L.C, L.D], "kriticna"))
        pre = copy.deepcopy({t: r for t, r in baza.tabele.items() if r})
        out = {"upisan_razlog": baza.tabele["case_actions"][0]["razlog"], "odgovori": {}}
        for kor in ("A", "B"):
            for ruta in ("/api/predmeti/{p}/genome-v2", "/api/predmeti/{p}/genome-v2/promene", "/api/case-actions/predmeti/{p}",
                         "/api/case-actions/worklist", "/api/workspace"):
                r = k.get(ruta.format(p=P), headers=zaglavlje(kor))
                telo = r.json()
                if isinstance(telo, dict):
                    telo.pop("procitano", None)
                out["odgovori"][f"{kor}|{ruta.format(p=P)}"] = {"status": r.status_code, "telo": telo}
        out["citanje_upisalo"] = {t: r for t, r in baza.tabele.items() if r} != pre
        out["model_pozvan"] = len(pozivi)
        return out
    finally:
        ocisti()
        mp.undo()


if __name__ == "__main__":
    print("@@" + json.dumps(main(), ensure_ascii=False))

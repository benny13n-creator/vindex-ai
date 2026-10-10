# -*- coding: utf-8 -*-
"""NS008 Task 22 — razmera: 1 / 100 / 1000 stavki institucionalnog znanja.

Meri se BROJ UPITA (dnevnik lažne baze) i vreme za: osnovni kontekst predmeta, sličnost, overene radove i stranu
Znanje. Broj upita mora da raste sa ceil(N / 200) (deo `in_`), nikad sa N. Rezultati su ograničeni. Nijedan poziv
modela ni Pinecone-a pri čitanju. Supabase-ovo sečenje odgovora (1000 redova) se emulira i dokazuje da se čita sve.
"""
import time
from types import SimpleNamespace

import pytest

import tests.ns008_fake as f8
from services import law_brain as lb

K1 = "e1e1e1e1-2222-4000-8000-000000000001"
CUR = "aaaaaaaa-2222-4000-8000-ffffffffffff"
MERENJA = {}


def _id(i):
    return f"aaaaaaaa-2222-4000-8000-{i:012d}"


def _svet(n):
    predmeti = [{"id": CUR, "user_id": "uid-A", "naziv": "Tekući", "tip": "radni", "oblast": "radno", "status": "aktivan",
                 "case_dna": {"verzija": 1}, "updated_at": "2026-10-01"}]
    t = {"predmeti": predmeti, "rocista": [], "predmet_dokazi": [], "outcome_log": [], "staging_memory": [],
         "predmet_issues": [], "predmet_contradictions": [], "predmet_delegiranja": [], "lessons_learned": [],
         "memory_entries": [], "memory_graph_edges": [], "klijenti": [],
         "kancelarije": [{"id": K1, "admin_uid": "uid-X"}],
         "kancelarija_clanovi": [{"kancelarija_id": K1, "user_id": "uid-A", "status": "ACTIVE"}]}
    t["rocista"].append({"predmet_id": CUR, "user_id": "uid-A", "sud": "OS Beograd"})
    t["predmet_dokazi"].append({"predmet_id": CUR, "user_id": "uid-A", "kategorija": "svedok"})
    for i in range(n):
        pid = _id(i)
        predmeti.append({"id": pid, "user_id": "uid-A", "naziv": f"Raniji {i}", "tip": "radni", "oblast": "radno",
                         "status": "zatvoren", "case_dna": {"verzija": 1}, "updated_at": f"2026-01-{1 + i % 28:02d}"})
        t["rocista"].append({"predmet_id": pid, "user_id": "uid-A", "sud": "OS Beograd"})
        t["predmet_dokazi"].append({"predmet_id": pid, "user_id": "uid-A", "kategorija": "svedok"})
        t["outcome_log"].append({"id": f"o{i}", "predmet_id": pid, "user_id": "uid-A", "ishod": ("pobeda", "poraz", "nagodba")[i % 3]})
        t["staging_memory"].append({"id": f"s{i}", "user_id": "uid-A", "predmet_id": pid, "tip": "tuzba", "naziv": f"Rad {i}",
                                    "tekst": "t", "status": "approved", "is_lawyer_approved": True,
                                    "approved_at": "2026-02-01T00:00:00+00:00", "pinecone_indexed": True})
        t["lessons_learned"].append({"id": f"l{i}", "user_id": "uid-A", "tip_spora": "radni", "lecija": f"Lekcija {i}",
                                     "status_lekcije": "usvojena_praksa", "potvrdio": "uid-A",
                                     "potvrdjeno_at": "2026-02-01", "zastarela": False})
        t["memory_entries"].append({"id": f"m{i}", "kancelarija_id": K1, "user_id": "uid-A", "entity_type": "sudija",
                                    "entity_id": f"S{i}", "sadrzaj": f"Beleška {i}", "aktivan": True, "izvor": "manual"})
    return t


@pytest.fixture
def merenje(monkeypatch):
    def _meri(n):
        k, b = f8.pripremi(monkeypatch, _svet(n))
        import openai
        from app.services import retrieve as rt
        monkeypatch.setattr(openai, "OpenAI", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("model pri čitanju")))
        monkeypatch.setattr(rt, "_pretraga_ns", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Pinecone pri čitanju")))
        out = {}
        for ime, fn in (("kontekst", lambda: lb.kontekst_predmeta(b, "uid-A", CUR, today=__import__("datetime").date(2026, 10, 10))),
                        ("slicnost", lambda: lb.slicni_predmeti(b, "uid-A", CUR)),
                        ("radovi", lambda: lb.ucitaj_artefakte(b, [p for p in b.tabele["predmeti"] if p["status"] == "zatvoren"])),
                        ("znanje", lambda: lb.pregled_znanja(b, "uid-A", today=__import__("datetime").date(2026, 10, 10)))):
            b.dnevnik.clear()
            t0 = time.perf_counter()
            rez = fn()
            out[ime] = {"upita": len(b.dnevnik), "ms": round((time.perf_counter() - t0) * 1000, 1), "rez": rez,
                        "radnje": {d["radnja"] for d in b.dnevnik}}
        f8.ocisti()
        return out
    yield _meri


@pytest.mark.parametrize("n", [1, 100, 1000])
def test_upiti_rastu_po_delovima_ne_po_predmetu(merenje, n):
    m = merenje(n)
    MERENJA[n] = {k: (v["upita"], v["ms"]) for k, v in m.items()}
    delova = max(1, -(-(n + 1) // 200))
    for ime, v in m.items():
        assert v["radnje"] == {"select"}, (ime, v["radnje"])
        assert v["upita"] <= 12 * delova + 8, (ime, n, v["upita"])
    k = m["kontekst"]["rez"]
    assert len(k["similar_cases"]["stavke"]) <= 50 and len(k["relevant_human_memory"]["stavke"]) <= 15
    assert len(k["verified_artifacts"]["stavke"]) <= 51
    z = m["znanje"]["rez"]
    assert len(z["verifikovani_radovi"]["stavke"]) <= lb.MAX_PRIKAZ and z["verifikovani_radovi"]["ukupno"] == n
    assert len(z["potvrdjene_lekcije"]["stavke"]) <= 500 and len(z["memorija_kancelarije"]["stavke"]) <= 500
    assert k["descriptive_outcomes"]["relevantnih"] == len(k["similar_cases"]["stavke"]) <= 50


def test_rast_upita_je_sublinearan():
    if not {1, 100, 1000} <= set(MERENJA):
        pytest.skip("zavisi od parametrizovanog merenja")
    for n, v in sorted(MERENJA.items()):
        print(f"MERENJE N={n} " + " ".join(f"{ime}={u}upita/{ms}ms" for ime, (u, ms) in v.items()))
    for ime in ("kontekst", "slicnost", "znanje"):
        assert MERENJA[1000][ime][0] < 10 * MERENJA[1][ime][0], (ime, MERENJA)


class _SupabaseSaSecenjem:
    """Kao PostgREST sa `max-rows = 1000`: odgovor bez `range` (ili sa većim opsegom) se seče na 1000."""

    def __init__(self, redovi):
        self.redovi, self.upita = redovi, 0

    def table(self, _t):
        q = SimpleNamespace(opseg=None, ids=None)
        o = self

        class _Q:
            def select(self, *a):
                return self

            def in_(self, k, v):
                q.ids = set(v)
                return self

            def range(self, a, b):
                q.opseg = (a, b)
                return self

            def execute(self):
                o.upita += 1
                sve = [r for r in o.redovi if r["predmet_id"] in q.ids]
                a, b = q.opseg or (0, 10 ** 9)
                return SimpleNamespace(data=sve[a:min(b + 1, a + 1000)])
        return _Q()


def test_secenje_na_1000_redova_ne_lazira_brojeve():
    redovi = [{"predmet_id": "p1", "user_id": "u", "kategorija": "svedok", "i": i} for i in range(2500)]
    s = _SupabaseSaSecenjem(redovi)
    assert len(lb._in_upit(s, "predmet_dokazi", "*", "predmet_id", ["p1"])) == 2500
    assert s.upita == 3

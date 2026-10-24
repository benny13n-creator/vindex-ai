# -*- coding: utf-8 -*-
"""MIR001 TASK-10 — JEDAN neprekinuti sintetički scenario (isti proces, ista baza, isti korisnik, isti predmet):

nov predmet → 7 dokumenata → OCR → činjenice → vremenski sled → protivrečnosti → pravno pitanje (savetnik) →
strategija → nacrt → pregled/izmena/odobrenje/DOCX → nova informacija (DOK-08) → sledeća radnja → autonomna priprema.

Stvarno: sve rute, worker, Tesseract, dispečer, Genome osvežavanje i V2 projekcija, Case Actions, staging, DOCX,
ciklus autonomije. Zamenjeni: modeli (klasifikacija, Genome — TASK-03/07; savetnik — snimač; ocena kvaliteta nacrta).
Sadržaj STVARNOG modela za pitanje/strategiju/nacrt je meren u TASK-04/05/06 (docs/v2-execution/MIR001_T0*_STVARNI_MODEL.json).
Svaki segment upisuje svoj ishod u `SEGMENTI` (redosled = redosled toka); padne li segment, test pada na njemu.
"""
import asyncio
import io
import types

import pytest

from tests import mir001_golden_case as gc
from tests.test_mir001_t07_dogadjaj_posledica import ROK, _dodaj, spis, treba_ocr  # noqa: F401
from tests.test_mir001_t08_proaktivnost import auto  # noqa: F401
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401
from tests.nacrt_json_zamena import kao_json

SEGMENTI = []


@treba_ocr
def test_ceo_tok_miroslavljevog_predmeta(auto, monkeypatch):
    k, b, pid, doks = auto
    import routers.multi_agent as MA
    import services.quality_gate as QG
    import shared.usage as US

    def seg(ime, uslov, detalj=""):
        SEGMENTI.append((ime, bool(uslov), detalj))
        assert uslov, (ime, detalj)

    # 1–2. nov predmet, 7 dokumenata, OCR skena (fixture: STVARAN put prijema kroz V2 rute)
    moji = [d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid]
    seg("01 nov predmet + 7 dokumenata", len(moji) == 7 and {d["user_id"] for d in moji} == {"uid-A"})
    sken = next(d for d in moji if d["naziv_fajla"] == gc.po_oznaci("DOK-05")["ime"])
    seg("02 OCR skena (stvaran Tesseract)", gc.NAVODI["N-09"]["tekst"] in " ".join((sken.get("tekst_sadrzaj") or "").split()))

    # 3. činjenice sa izvorom; 4. vremenski sled; 5. protivrečnosti
    zive = [t for t in b.tabele["predmet_dokazi"] if t["predmet_id"] == pid and not t.get("deleted_at")]
    seg("03 navodi sa izvorom", all(any(n["tekst"] in t["tvrdnja"] and t["dokument_id"] == doks[n["dok"]] for t in zive)
                                    for n in gc.NAVODI.values()))
    g = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A).json()
    st = sorted([s for s in g["hronologija"]["stavke"] if s.get("datum")], key=lambda s: s["datum"])
    seg("04 vremenski sled sa izvorom", [(s["datum"], s["lokacija"]["dokument_id"]) for s in st]
        == [(iso, doks[oz]) for iso, _, oz in gc.HRONOLOGIJA])
    seg("05 protivrečnosti stranaka aktivne", {x["sporna_tacka"] for x in g["kontradikcije"]["aktivne"]}
        == {x["pitanje"] for x in gc.PROTIVRECNOSTI})

    # savetnik: snimač poruke (sadržaj stvarnog modela meren u TASK-04/05/06)
    snim = []

    def _model(client, system, user_msg):
        snim.append({"system": MA._sa_granicom(system), "user": user_msg})
        txt = ("PRIVREDNOM SUDU U PRIMERGRADU\nBroj predmeta: P 9901/2026\nVestak u nalazu navodi uzrok (DOK-05).\n"
               "⚠️ Ovaj nacrt generisala je AI i mora ga pregledati i potpisati ovlašćeni advokat pre podnošenja sudu.")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=txt))])

    async def _politika(f):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free", "krediti": 1}

    async def _stanje(u, e):
        return 100

    async def _kvalitet(t, tip):
        return {"confidence_score": 0.5, "detail": {}}
    monkeypatch.setattr(MA, "_pozovi_agent_api", _model)
    monkeypatch.setattr(MA, "_pozovi_nacrt_api", kao_json(_model))     # C3b: nacrt iz spisa = JSON
    monkeypatch.setattr(US, "get_policy", _politika)
    monkeypatch.setattr(US.UsageService, "balance", staticmethod(_stanje))
    monkeypatch.setattr(QG, "evaluate_draft_quality", _kvalitet)
    import app.services.retrieve as R
    monkeypatch.setattr(R, "retrieve_documents", lambda *a, **kw: ([], {}))
    odlozeni = []

    class _Asyncio:
        def __getattr__(self, ime):
            return getattr(asyncio, ime)

        def create_task(self, coro):
            odlozeni.append(coro)
    monkeypatch.setattr(MA, "asyncio", _Asyncio())
    b.podrazumevano.setdefault("staging_memory", {}).update({"status": "pending", "is_lawyer_approved": False,
                                                            "pinecone_indexed": False, "quality_detail": {}, "naziv": ""})

    # 6. pravno pitanje (savetnik nad celim spisom + sporne tačke)
    r = k.post("/api/agents/run", json={"agent": "research", "task": "Koliki je garantni rok po ugovoru stranaka?",
                                        "predmet_id": pid}, headers=A)
    iz = r.json()["izvori_predmeta"]
    seg("06 pravno pitanje nad celim spisom", r.status_code == 200 and iz["svi_dokumenti_u_celini"] is True
        and gc.NAVODI["N-02"]["tekst"] in snim[-1]["user"] and "SPORNE TAČKE PREDMETA" in snim[-1]["user"])

    # 7. strategija (litigation) — pravila rada sa spisom i današnji datum u poruci
    r = k.post("/api/agents/run", json={"agent": "litigation", "task": "Pripremi radnu strategiju za tuzioca.",
                                        "predmet_id": pid}, headers=A)
    seg("07 strategija iz spisa", r.status_code == 200 and "## 0. PROCESNO STANJE" in snim[-1]["system"]
        and "Današnji datum:" in snim[-1]["user"] and "Snaga predmeta" not in snim[-1]["user"])

    # 8. nacrt → pregled → izmena → odobrenje → DOCX
    r = k.post("/api/agents/run", json={"agent": "drafting", "task": "Sastavi izjasnjenje tuzioca na nalaz vestaka (DOK-05).",
                                        "predmet_id": pid}, headers=A)
    while odlozeni:
        asyncio.run(odlozeni.pop(0))
    [nac] = [s for s in b.tabele["staging_memory"] if s.get("predmet_id") == pid]
    prvobitan = str(nac["tekst"])                                      # pre izmene (red je isti objekat kao u bazi)
    # C3b FINAL CLOSURE: AI radni predlog → usvojene stavke + izmena advokata → odobren dokument za sud → DOCX
    from tests import c3b_usvajanje_pomoc as U
    stv = U.predlog(k, A, nac["id"])["predlog"]["stavke"]
    dok, d = U.ceo_tok(k, A, nac["id"], [x["id"] for x in stv if "⚠" not in x["tekst"]][:3],
                       izmeni=lambda t: U.bez_oznaka(t) + "\n\nIzmenio advokat.")
    sadrzaj = "\n".join(U.docx_pasusi(d.content)) if d.status_code == 200 else ""
    nepromenjen = next(s for s in b.tabele["staging_memory"] if s["id"] == nac["id"])["tekst"] == prvobitan
    seg("08 nacrt → AI predlog → usvajanje → izmena → odobrenje → DOCX", "PROVERA PRE UPOTREBE" in prvobitan
        and d.status_code == 200 and "Izmenio advokat." in sadrzaj and nepromenjen and dok["tekst"].endswith("Izmenio advokat."),
        str({"napomena": "PROVERA PRE UPOTREBE" in prvobitan, "docx": d.status_code, "predlog_nepromenjen": nepromenjen}))

    # 9. nova informacija → 10. sledeća radnja
    d8 = _dodaj(k, b, pid, gc.KASNIJI)
    akc = [a for a in b.tabele["case_actions"] if a["predmet_id"] == pid and a["status"] == "open"
           and a["tip"] == "PLANIRATI_ROKOVE" and (a.get("dokaz") or {}).get("dokument_id") == d8]
    seg("09 nova informacija u modelu predmeta", any(h.get("datum_iso") == ROK and h.get("dokument_id") == d8
                                                     for h in b.tabele["predmet_hronologija"]))
    seg("10 sledeća radnja sa razlogom i izvorom", len(akc) == 1 and "čeka vašu potvrdu" in akc[0]["razlog"])

    # 11. autonomna priprema (bez zahteva), izolovano
    from workers.background_agents import run_autonomy_cycle
    asyncio.run(run_autonomy_cycle("mir001-t10"))
    pre = [w for w in b.tabele["autonomy_work_items"] if w["predmet_id"] == pid and w["work_type"] == "CASE_CHANGE_BRIEF"
           and w["status"] == "READY_FOR_REVIEW"]
    seg("11 autonomna priprema pregleda promene", len(pre) == 1 and any(ROK in str(p.get("novo")) for p in pre[0]["content_json"]["promene"]))

    # izolacija kroz ceo tok
    seg("12 korisnik B ne vidi ništa od predmeta A",
        all(k.get(u, headers=B).status_code in (403, 404) for u in
            (f"/api/predmeti/{pid}", f"/api/predmeti/{pid}/genome-v2", f"/api/autonomy/work-items/{pre[0]['id']}",
             f"/api/staging/{nac['id']}")))
    print("\nSEGMENTI:", ascii([(i, ok) for i, ok, _ in SEGMENTI]))

"""NS006 Task 14 — realističan predmet od prijema dokumenta do akcije i V2 čitanja.

Izmišljen radni spor (Marko Petrović protiv „Gradnja Invest" DOO), tok kroz STVARNI kod:

  1. Prijem rešenja o otkazu  — isti trajni događaji kao `api.py` upload: NewEvidenceRegistered pa DocumentAccepted
       → evidence_classification (`klasifikuj_i_sacuvaj`: tvrdnje modela, LOCIRANE u tekstu, `ai_klasifikacija`)
       → genome_refresh v1 → reconcile akcija
  2. Advokat ručno dodaje tvrdnju (ruta)            → HUMAN_CONFIRMED, NewEvidenceRegistered → reconcile
  3. Prijem dostavnice                               → nova tvrdnja „uručena 25.03" protivreči „uručeno 17.03"
       → genome_refresh v2 → V2 kontradikcija (paketni RPC) → RAZRESITI_KONTRADIKCIJU
  4. Zakazano ročište (ruta)                         → genome v3, PRIPREMITI_PODNESAK
  5. V2 čitanje (genome-v2, promene, case-actions, workspace) — bez ijednog poziva modela.

Zamenjeni su SAMO modeli: klasifikacija (iz STVARNOG teksta izdvaja rečenice sa datumom) i Genome (čita
STVARNI prompt i bira CLAIM oznake iz kataloga). Nijedan mrežni poziv.
"""
import asyncio
import copy
import json
import re
from datetime import date, timedelta

import pytest

from tests import ns006_realni_predmet as rp
from tests.ns006_fake import pripremi, ocisti, dispecuj, zaglavlje

PA = rp.PA
DATUM_ROCISTA = (date.today() + timedelta(days=12)).isoformat()


def _tabele():
    t = rp.tabele()
    t["predmeti"][0].update({"case_dna": {}, "observation_version": 0})
    t["predmeti"][1]["observation_version"] = 0
    for k in ("predmet_dokumenti", "predmet_dokazi", "rocista", "predmet_genome_history", "predmet_issues",
              "predmet_contradictions", "predmet_contradiction_claims"):
        t[k] = []
    for k in ("predmet_hronologija", "proactive_alerts", "notifications", "audit_immutable"):
        t.setdefault(k, [])
    return t


def _klasifikuj(naziv, tekst):
    telo = " ".join(l for l in tekst.splitlines() if l.strip() and not l.isupper())   # bez zaglavlja dokumenta
    recenice = [s.strip().rstrip(".") + "." for s in re.split(r"\.\s+(?=[A-ZČĆŠŽĐ])", telo) if re.search(r"\d{2}\.\d{2}\.\d{4}", s)]
    return {"tip_dokaza": "dopis", "pravni_elementi": ["uručenje"] * len(recenice), "ai_tags": {}, "kljucne_cinjenice": recenice}


def _genome_model(pozivi):
    async def _pozovi(client, combined, n):
        pozivi.append(combined)
        oznake = dict(re.findall(r"(CLAIM-\d{3}): ([^\n]+)", combined))
        a = next((k for k, v in oznake.items() if "uručeno zaposlenom 17.03.2025" in v), None)
        b = next((k for k, v in oznake.items() if "25.03.2025" in v), None)
        g = copy.deepcopy(rp._genome(0, False, 0, 0))
        for polje in ("verzija", "_analiza_osnov", "_genome_docs_count", "_genome_docs_preskoceno", "_dokumenti_bez_teksta", "_verifikacija"):
            g.pop(polje, None)
        if a and b:
            g["kontradikcije"] = [{"issue_label": "datum uručenja rešenja o otkazu", "claim_refs": [a, b],
                                   "relation_type": "cinjenica_cinjenica", "opis": "17.03.2025 naspram 25.03.2025.",
                                   "tezina": "kriticna", "lokacija_1": "DOK-01", "lokacija_2": "DOK-02"}]
        g["snaga_faktori"] = [{"faktor": "Pisani dokazi", "uticaj": "+5", "opis": "x"}]
        return json.dumps(g, ensure_ascii=False)
    return _pozovi


def _prijem(baza, dok_id, naziv, rb, tekst):
    """Isto što ostavlja `api.py` upload: red dokumenta + NewEvidenceRegistered, pa DocumentAccepted."""
    baza.tabele["predmet_dokumenti"].append({"id": dok_id, "predmet_id": PA, "user_id": "uid-A", "naziv_fajla": naziv,
                                             "redni_broj": rb, "status": "obradjen", "tekst_sadrzaj": tekst})
    from services.event_bus import EventType, emit_durable
    asyncio.run(emit_durable(EventType.NEW_EVIDENCE_REGISTERED, "uid-A", PA, {"dokument_id": dok_id, "naziv": naziv, "trigger": "pipeline_a_upload"}))
    asyncio.run(emit_durable(EventType.DOCUMENT_ACCEPTED, "uid-A", PA, {"dokumenti": [naziv], "trigger": "pipeline_a_upload"}))
    rez = dispecuj(2)
    assert all(r["greske"] == 0 for r in rez), rez


@pytest.fixture
def svet(monkeypatch):
    k, baza = pripremi(monkeypatch, _tabele())
    import routers.case_dna as cd
    import routers.evidence as ev
    pozivi = []
    monkeypatch.setattr(cd, "_pozovi_genome_api", _genome_model(pozivi))
    monkeypatch.setattr(ev, "_klasifikuj_dokument", _klasifikuj)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-bez-mreze")
    yield k, baza, pozivi
    ocisti()


def test_realan_predmet_od_dokumenta_do_akcije(svet):
    k, baza, pozivi = svet

    # 1. rešenje o otkazu
    _prijem(baza, rp.D1, "Rešenje o otkazu.pdf", 1, rp.TEKST_D1)
    assert baza.tabele["predmeti"][0]["case_dna"]["verzija"] == 1
    dz = {d["tvrdnja"]: d for d in baza.tabele["predmet_dokazi"]}
    t1 = next(d for t, d in dz.items() if "17.03.2025" in t)
    assert t1["izvor_tvrdnje"] == "ai_klasifikacija" and t1["nacin_pronalaska"] == "egzaktan" and t1["dokument_id"] == rp.D1

    # 2. advokat ručno dodaje tvrdnju
    r = k.post(f"/api/evidence/predmeti/{PA}/dokaz", json={"tvrdnja": "Klijent tvrdi da rešenje o otkazu nije primio lično.",
                                                         "pravni_element": "uručenje"}, headers=zaglavlje("A"))
    assert r.status_code == 200 and r.json()["dogadjaj"] == "ZAKAZAN"
    dispecuj()

    # 3. dostavnica — nova činjenica protivreči rešenju
    _prijem(baza, rp.D2, "Dostavnica.pdf", 2, rp.TEKST_D2)
    g = baza.tabele["predmeti"][0]["case_dna"]
    assert g["verzija"] == 2 and len(g["kontradikcije"]) == 1
    kontr = [x for x in baza.tabele["predmet_contradictions"] if x["state"] == "OPEN"]
    assert len(kontr) == 1

    # 4. ročište
    r = k.post("/api/rocista", json={"predmet_id": PA, "sud": "Osnovni sud u Beogradu", "datum": DATUM_ROCISTA, "vreme": "09:30"},
               headers=zaglavlje("A"))
    assert r.status_code == 200
    rez = dispecuj()
    assert rez[0]["greske"] == 0 and baza.tabele["predmeti"][0]["case_dna"]["verzija"] == 3
    analiza_poziva = len(pozivi)

    # 5. V2 čitanje — ništa ne poziva model
    ziv = k.get(f"/api/predmeti/{PA}/genome-v2", headers=zaglavlje("A")).json()
    pr = k.get(f"/api/predmeti/{PA}/genome-v2/promene", headers=zaglavlje("A")).json()
    akc = k.get(f"/api/case-actions/predmeti/{PA}", headers=zaglavlje("A")).json()
    ws = k.get("/api/workspace", headers=zaglavlje("A")).json()
    assert len(pozivi) == analiza_poziva, "čitanje ne sme pozvati model"

    # poreklo
    po = ziv["dokazi"]["sazetak"]["po_poreklu"]
    assert po["SOURCE_FACT"] >= 2 and po["HUMAN_CONFIRMED"] == 1, po
    covek = next(t for t in ziv["dokazi"]["tvrdnje"] if "nije primio" in t["vrednost"])
    assert covek["poreklo"] == "HUMAN_CONFIRMED" and covek["potpora"] == "BEZ_POTPORE"
    # kontradikcija sa izvorima
    a = ziv["kontradikcije"]["aktivne"]
    assert len(a) == 1 and a[0]["sporna_tacka"] == "datum uručenja rešenja o otkazu"
    assert sorted(u["dokument_id"] for u in a[0]["ucesnici"]) == sorted([rp.D1, rp.D2])
    assert all(u["lokacija"] and u["lokacija"]["strana_procena"] for u in a[0]["ucesnici"])
    # nijedan izmišljen id: sve reference postoje
    dok_ids = {d["id"] for d in baza.tabele["predmet_dokumenti"]}
    tvrd_ids = {d["id"] for d in baza.tabele["predmet_dokazi"]}
    for t in ziv["dokazi"]["tvrdnje"]:
        assert t["id"] in tvrd_ids and (t["dokument_id"] is None or t["dokument_id"] in dok_ids)
    for u in a[0]["ucesnici"]:
        assert u["tvrdnja_id"] in tvrd_ids
    # spremnost i akcije
    dims = {d["kljuc"]: d for d in ziv["spremnost"]["dimenzije"]}
    assert dims["operativna_spremnost"]["vrednost"] == "CRITICAL_GAP"
    tipovi = sorted(x["tip"] for x in akc["akcije"])
    assert "RAZRESITI_KONTRADIKCIJU" in tipovi and "PRIPREMITI_PODNESAK" in tipovi
    assert any(x["predmet_id"] == PA for x in ws["kriticno"]) and ws["provera_potpuna"] is True
    # promene v2 → v3 (ročište ne menja strukturu analize; razlika je poštena)
    assert (pr["trenutna_verzija"], pr["prethodna_verzija"]) == (3, 2) and pr["stanje"] == "OK"
    # nijedan broj modela kao verovatnoća ishoda
    tekst = json.dumps(ziv, ensure_ascii=False).lower()
    for zabranjeno in ("verovatnoća uspeha", "šansa", "probability", "predviđanje presude"):
        assert zabranjeno not in tekst
    assert all("NIJE verovatnoća ishoda" in m["napomena"] for m in ziv["metrike"])


def test_klijent_b_ne_vidi_nista_od_realnog_predmeta(svet):
    k, baza, _ = svet
    _prijem(baza, rp.D1, "Rešenje o otkazu.pdf", 1, rp.TEKST_D1)
    for ruta in (f"/api/predmeti/{PA}/genome-v2", f"/api/predmeti/{PA}/genome-v2/promene", f"/api/case-actions/predmeti/{PA}"):
        r = k.get(ruta, headers=zaglavlje("B"))
        assert r.status_code == 404 and "Petrović" not in r.text and "uručeno" not in r.text
    assert k.get("/api/workspace", headers=zaglavlje("B")).json()["ukupno_aktivnih"] == 0

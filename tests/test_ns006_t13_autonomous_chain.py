"""NS006 Task 13 — „Promenio sam predmet, a Vindex je ažurirao razumevanje i sledeće korake bez mog zahteva."

Lanac kroz STVARNE komponente; ručni refresh Genome-a se NE poziva nigde:

  POST /api/rocista (advokat zakazuje ročište)
    → `emit_durable(rociste_zakazano)` (trajni red u `events`)
    → `dispatch_pending_events` (isti poller kao DispatchLoop)
    → `handle_case_changed` → genome_refresh → `_do_genome_refresh` → `_extract_genome`
        (model zamenjen DETERMINISTIČKOM funkcijom koja čita STVARNI prompt i bira CLAIM oznake iz
         stvarnog kataloga — nijedan mrežni poziv)
    → `upisi_v2_opazanje` → `v2_persist_observation_package` (SQL 124/125 emuliran u tests/ns006_fake.py)
    → Genome v3 → v4 (istorija v3, okidač `case_evolution:<event_id>`)
    → refresh_case_actions (RAZRESITI_KONTRADIKCIJU za novu V2 kontradikciju + PRIPREMITI_PODNESAK za ročište)
    → GET genome-v2 / genome-v2/promene / case-actions vide novo stanje.

Trag: event_id → `case_evolution_consequences` → `predmet_genome_history.trigger_event` → `case_actions.event_id`.
"""
import asyncio
import copy
import json
import re
from datetime import date, timedelta

import pytest

from tests import ns006_realni_predmet as rp
from tests.ns006_fake import pripremi, ocisti, dispecuj, zaglavlje

ROCISTE_DATUM = (date.today() + timedelta(days=9)).isoformat()


def _pocetne_tabele():
    t = rp.tabele()
    p = t["predmeti"][0]
    v3 = copy.deepcopy(t["predmet_genome_history"][0]["genome_data"])     # v3: bez kontradikcije
    p["case_dna"] = v3
    p["observation_version"] = 0
    t["predmeti"][1]["observation_version"] = 0
    v2 = dict(copy.deepcopy(v3), verzija=2)
    t["predmet_genome_history"] = [{"id": "h2", "predmet_id": rp.PA, "user_id": "uid-A", "verzija": 2, "genome_data": v2,
                                    "trigger_event": "manual_refresh", "created_at": "2026-10-01T08:00:00+00:00"}]
    t["predmet_issues"], t["predmet_contradictions"], t["predmet_contradiction_claims"] = [], [], []
    t["rocista"] = []
    for k in ("predmet_hronologija", "proactive_alerts", "notifications", "audit_immutable", "case_intelligence_summaries"):
        t.setdefault(k, [])
    return t


def _model_iz_prompta(pozivi):
    """Deterministička zamena za model: čita PRAVI prompt (tekst dokumenata + EVIDENCE VAULT sa
    CLAIM oznakama) i prijavljuje kontradikciju između tvrdnje „uručeno 17.03" i „uručena 25.03"
    koristeći ISKLJUČIVO oznake koje je prompt ponudio."""
    async def _pozovi(client, combined, n):
        pozivi.append(combined)
        oznake = dict(re.findall(r"(CLAIM-\d{3}): ([^\n]+)", combined))
        a = next(k for k, v in oznake.items() if "17.03.2025" in v)
        b = next(k for k, v in oznake.items() if "25.03.2025" in v)
        g = copy.deepcopy(rp._genome(0, True, 3, 5))
        for polje in ("verzija", "_analiza_osnov", "_genome_docs_count", "_genome_docs_preskoceno", "_dokumenti_bez_teksta", "_verifikacija"):
            g.pop(polje, None)
        g["kontradikcije"] = [{"issue_label": "datum uručenja rešenja o otkazu", "claim_refs": [a, b],
                               "relation_type": "cinjenica_cinjenica", "opis": "Rešenje: 17.03.2025; dostavnica: 25.03.2025.",
                               "tezina": "kriticna", "lokacija_1": "DOK-01", "lokacija_2": "DOK-02"}]
        g["snaga_faktori"] = [{"faktor": "Pisani dokazi", "uticaj": "+10", "opis": "x"}]
        return json.dumps(g, ensure_ascii=False)
    return _pozovi


@pytest.fixture
def lanac(monkeypatch):
    k, baza = pripremi(monkeypatch, _pocetne_tabele())
    import routers.case_dna as cd
    pozivi = []
    monkeypatch.setattr(cd, "_pozovi_genome_api", _model_iz_prompta(pozivi))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-bez-mreze")
    yield k, baza, pozivi
    ocisti()


def test_promena_predmeta_bez_rucnog_refresha(lanac):
    k, baza, pozivi = lanac
    pre = {"verzija": baza.tabele["predmeti"][0]["case_dna"]["verzija"],
           "akcije": len(baza.tabele["case_actions"]), "kontr": len(baza.tabele["predmet_contradictions"])}
    assert pre == {"verzija": 3, "akcije": 0, "kontr": 0}

    # 1. advokat zakazuje ročište — OBIČNA podržana putanja
    r = k.post("/api/rocista", json={"predmet_id": rp.PA, "sud": "Osnovni sud u Beogradu", "datum": ROCISTE_DATUM, "vreme": "10:00"},
               headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    dog = [e for e in baza.tabele["events"] if e["event_type"] == "rociste_zakazano"]
    assert len(dog) == 1
    event_id = dog[0]["id"]
    assert not pozivi, "do dispečera se ništa ne analizira"

    # 2. kanonski dispečer (isti koji DispatchLoop zove svakih 3 s); niko ne zove refresh
    rez = dispecuj()[0]
    assert rez["greske"] == 0, rez
    assert len(pozivi) == 1, "tačno jedna analiza po događaju"
    posledice = {c["consequence_name"]: c["status"] for c in baza.tabele["case_evolution_consequences"] if c["event_id"] == event_id}
    assert posledice == {"genome_refresh": "completed", "refresh_case_actions": "completed", "project_notifications": "completed"}, posledice

    # 3. Genome v3 → v4, istorija vezana za događaj
    g = baza.tabele["predmeti"][0]["case_dna"]
    assert g["verzija"] == 4
    h3 = next(h for h in baza.tabele["predmet_genome_history"] if h["verzija"] == 3)
    assert h3["trigger_event"] == "case_evolution:" + event_id
    assert g["kontradikcije"][0]["claim_ids"] == sorted([rp.T1, rp.T2]), "trajni identitet tvrdnji upisan"

    # 4. V2 kontradikcija perzistirana kroz paketni RPC
    k1 = [x for x in baza.tabele["predmet_contradictions"] if x["state"] == "OPEN"]
    assert len(k1) == 1 and baza.tabele["predmeti"][0]["observation_version"] == 1
    clanovi = sorted(c["dokaz_id"] for c in baza.tabele["predmet_contradiction_claims"] if c["contradiction_id"] == k1[0]["id"])
    assert clanovi == sorted([rp.T1, rp.T2])

    # 5. Case Actions usklađene sa novim stanjem, vezane za ISTI događaj
    otvorene = {a["dedupe_key"]: a for a in baza.tabele["case_actions"] if a["status"] == "open"}
    assert "v2:contradiction:" + k1[0]["id"] in otvorene
    roc = next(a for a in otvorene.values() if a["tip"] == "PRIPREMITI_PODNESAK")
    assert roc["rok"] == ROCISTE_DATUM and "za 9 dan" in roc["razlog"]
    assert all(a["event_id"] == event_id for a in otvorene.values()), "trag: svaka akcija nosi događaj koji ju je proizveo"

    # 6. svež V2 prikaz vidi novo stanje — bez ijednog novog poziva modela
    promene = k.get(f"/api/predmeti/{rp.PA}/genome-v2/promene", headers=zaglavlje("A")).json()
    assert (promene["trenutna_verzija"], promene["prethodna_verzija"], promene["dogadjaj_id"]) == (4, 3, event_id)
    assert any(p["vrsta"] == "kontradikcija_dodata" for p in promene["promene"])
    assert {a["id"] for a in promene["akcije_dogadjaja"]} == {a["id"] for a in otvorene.values()}
    ziv = k.get(f"/api/predmeti/{rp.PA}/genome-v2", headers=zaglavlje("A")).json()
    assert ziv["metapodaci"]["genome_verzija"] == 4 and ziv["kontradikcije"]["izvor"] == "v2"
    assert ziv["kontradikcije"]["aktivne"][0]["sporna_tacka"] == "datum uručenja rešenja o otkazu"
    akcije = k.get(f"/api/case-actions/predmeti/{rp.PA}", headers=zaglavlje("A")).json()
    assert akcije["broj_akcija"] == len(otvorene)
    assert len(pozivi) == 1, "čitanje ne poziva model"


def test_ponovljen_dispecer_ne_ponavlja_skupu_analizu(lanac):
    k, baza, pozivi = lanac
    k.post("/api/rocista", json={"predmet_id": rp.PA, "sud": "Osnovni sud u Beogradu", "datum": ROCISTE_DATUM}, headers=zaglavlje("A"))
    dispecuj(3)
    assert len(pozivi) == 1 and baza.tabele["predmeti"][0]["case_dna"]["verzija"] == 4
    # isti događaj ponovo stavljen u red (npr. ručni replay) → posledice su `completed`, analiza se ne ponavlja
    ev = baza.tabele["events"][0]
    ev["dispatched_at"], ev["claimed_at"] = None, None
    dispecuj()
    assert len(pozivi) == 1 and baza.tabele["predmeti"][0]["case_dna"]["verzija"] == 4


def test_tudji_korisnik_ne_pokrece_obradu_tudjeg_predmeta(lanac):
    k, baza, pozivi = lanac
    r = k.post("/api/rocista", json={"predmet_id": rp.PA, "sud": "Sud", "datum": ROCISTE_DATUM}, headers=zaglavlje("B"))
    assert r.status_code == 404
    dispecuj()
    assert baza.tabele["events"] == [] and pozivi == [] and baza.tabele["predmeti"][0]["case_dna"]["verzija"] == 3

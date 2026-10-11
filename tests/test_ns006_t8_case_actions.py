"""NS006 Task 8 — integritet motora akcija (services/case_evolution.py → case_actions).

Matrica stanje → očekivana akcija (postojeća semantika, bez novih kategorija), kroz STVARNI
reconcile (`_consequence_refresh_case_actions` / `_compute_target_actions`) nad lažnom bazom sa
delimičnim UNIQUE indeksom iz migracije 099 (tests/ns006_fake.py):

  bez tvrdnji                       → PRIBAVITI_DOKAZ „nema dokaza" (critical)
  nov dokaz                         → ta akcija se ZATVARA (Task 2)
  zakazano ročište ≤30 dana          → PRIPREMITI_PODNESAK, rok = datum, prioritet po danima
  pomereno ročište                   → ISTA akcija (ključ = id ročišta) AŽURIRANA, ne zatvorena+otvorena
  otvorena V2 kontradikcija          → RAZRESITI_KONTRADIKCIJU (ključ v2:contradiction:<id>)
  kontradikcija se više ne opaža     → akcija se ZATVARA
  zatvoren predmet                   → sve otvorene se zatvaraju; Workspace ga ne prikazuje

Plus: isti događaj dvaput i paralelno → jedna logička akcija; isto stanje posle „restarta" → isti skup;
svaka akcija ima razlog i izvor; bez roka → `rok: null`.

KVAR (pronađen u Task 0, PROVEN ovde): pad čitanja izvora se tretirao kao prazan izvor — pad čitanja
ročišta je ZATVARAO otvorenu akciju za ročište, a pad čitanja tvrdnji OTVARAO lažnu „nema dokaza".
"""
import asyncio
from datetime import date, timedelta

import pytest

from tests.ns006_fake import pripremi, ocisti, zaglavlje

PA = "11111111-1111-4111-8111-11111111111a"
DANAS = date.today()


def _tabele(**k):
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Petrović protiv ABC", "tip": "radno",
                      "status": k.get("status", "aktivan"), "case_dna": k.get("case_dna", {})}],
        "predmet_dokazi": k.get("dokazi", []),
        "predmet_dokumenti": k.get("dokumenti", []),
        "rocista": k.get("rocista", []),
        "case_actions": [], "events": [], "case_evolution_consequences": [],
        "predmet_issues": k.get("issues", []), "predmet_contradictions": k.get("kontradikcije", []),
        "predmet_contradiction_claims": k.get("clanovi", []),
        "zadaci": [], "intake_jobs": [],
    }


@pytest.fixture
def okr(monkeypatch):
    stanje = {}

    def _pripremi(**k):
        stanje["k"], stanje["baza"] = pripremi(monkeypatch, _tabele(**k))
        return stanje["k"], stanje["baza"]
    yield _pripremi
    ocisti()


def _reconcile(event_id="dog-1"):
    from services.case_evolution import _consequence_refresh_case_actions
    from services.event_bus import Event, EventType
    return asyncio.run(_consequence_refresh_case_actions(Event(
        type=EventType.SOURCE_INVALIDATED, user_id="uid-A", predmet_id=PA, payload={}, event_id=event_id)))


def _otvorene(baza):
    return {a["dedupe_key"]: a for a in baza.tabele["case_actions"] if a["status"] == "open"}


def _roc(id_, dana, status="zakazano"):
    return {"id": id_, "predmet_id": PA, "user_id": "uid-A", "sud": "Osnovni sud u Beogradu",
            "datum": (DANAS + timedelta(days=dana)).isoformat(), "status": status}


def _kljuc_rocista(id_):
    from services.case_evolution import _stable_key
    return _stable_key("rociste", id_)


# ── matrica ──────────────────────────────────────────────────────────────────

def test_rociste_akcija_i_pomeranje_azurira_istu(okr):
    _, baza = okr(rocista=[_roc("r1", 5)])
    _reconcile("d1")
    a = _otvorene(baza)[_kljuc_rocista("r1")]
    assert a["tip"] == "PRIPREMITI_PODNESAK" and a["prioritet"] == "high" and a["rok"] == (DANAS + timedelta(days=5)).isoformat()
    assert "za 5 dan" in a["razlog"] and a["dokaz"]["rociste_id"] == "r1"
    prvi_id = a["id"]
    baza.tabele["rocista"][0]["datum"] = (DANAS + timedelta(days=2)).isoformat()
    _reconcile("d2")
    b = _otvorene(baza)[_kljuc_rocista("r1")]
    assert b["id"] == prvi_id, "pomereno ročište AŽURIRA istu akciju"
    assert b["prioritet"] == "critical" and b["rok"] == (DANAS + timedelta(days=2)).isoformat() and b["event_id"] == "d2"
    assert sum(1 for x in baza.tabele["case_actions"] if x["dedupe_key"] == _kljuc_rocista("r1")) == 1


def test_otkazano_rociste_zatvara_akciju(okr):
    _, baza = okr(rocista=[_roc("r1", 5)])
    _reconcile("d1")
    baza.tabele["rocista"][0]["status"] = "otkazano"
    _reconcile("d2")
    assert _kljuc_rocista("r1") not in _otvorene(baza)


def test_v2_kontradikcija_otvara_i_zatvara(okr):
    _, baza = okr(dokazi=[{"id": "c1", "predmet_id": PA, "user_id": "uid-A", "tvrdnja": "a", "deleted_at": None},
                          {"id": "c2", "predmet_id": PA, "user_id": "uid-A", "tvrdnja": "b", "deleted_at": None}],
                  issues=[{"id": "i1", "predmet_id": PA, "user_id": "uid-A", "label": "datum uručenja", "status": "DISCOVERED"}],
                  kontradikcije=[{"id": "k1", "issue_id": "i1", "relation_type": "cinjenica_cinjenica", "state": "OPEN", "tezina": "kriticna"}],
                  clanovi=[{"contradiction_id": "k1", "dokaz_id": "c1", "removed_at": None},
                           {"contradiction_id": "k1", "dokaz_id": "c2", "removed_at": None}])
    _reconcile("d1")
    a = _otvorene(baza)["v2:contradiction:k1"]
    assert a["tip"] == "RAZRESITI_KONTRADIKCIJU" and a["prioritet"] == "critical" and a["razlog"] == "datum uručenja"
    assert sorted(a["dokaz"]["claim_ids"]) == ["c1", "c2"] and a["rok"] is None
    baza.tabele["predmet_contradictions"][0]["state"] = "NOT_OBSERVED"
    _reconcile("d2")
    assert "v2:contradiction:k1" not in _otvorene(baza)


def test_zatvoren_predmet_zatvara_sve_i_nestaje_iz_workspace(okr):
    k, baza = okr(rocista=[_roc("r1", 5)])
    _reconcile("d1")
    assert _otvorene(baza)
    w = k.get("/api/workspace", headers=zaglavlje("A")).json()
    assert w["ukupno_aktivnih"] >= 1
    baza.tabele["predmeti"][0]["status"] = "zatvoren"
    _reconcile("d2")
    assert _otvorene(baza) == {}
    w2 = k.get("/api/workspace", headers=zaglavlje("A")).json()
    assert w2["ukupno_aktivnih"] == 0 and w2["provera_potpuna"] is True


def test_propusteno_rociste_ostaje_kriticno(okr):
    """BLACKSWAN-CRIT-002: prošao datum ≠ „rešeno" — akcija ostaje dok se status ročišta ne promeni."""
    _, baza = okr(rocista=[_roc("r9", -2)])
    _reconcile("d1")
    a = _otvorene(baza)[_kljuc_rocista("r9")]
    assert a["prioritet"] == "critical" and "PROPUŠTENO" in a["razlog"]


def test_terminalan_predmet_bez_reconcile_nije_u_workspace(okr):
    """Legacy `PATCH /api/predmeti/{id}` sme da postavi terminalan status BEZ događaja (Task 2, dug);
    tada akcije ostaju `open`, a Workspace ih i dalje NE SME prikazati."""
    k, baza = okr(rocista=[_roc("r1", 5)])
    _reconcile("d1")
    baza.tabele["predmeti"][0]["status"] = "arhiviran"     # bez reconcile-a
    assert _otvorene(baza), "akcije su i dalje otvorene u bazi"
    w = k.get("/api/workspace", headers=zaglavlje("A")).json()
    assert w["ukupno_aktivnih"] == 0


def test_svaka_akcija_ima_razlog_i_izvor_bez_izmisljenog_roka(okr):
    _, baza = okr(rocista=[_roc("r1", 5)])
    _reconcile("d1")
    for a in baza.tabele["case_actions"]:
        assert a["razlog"] and a["dokaz"], a
        if a["tip"] != "PRIPREMITI_PODNESAK":
            assert a["rok"] is None, a


# ── idempotencija / konkurentnost / restart ──────────────────────────────────

def test_isti_dogadjaj_dvaput_i_paralelno_jedna_akcija(okr):
    _, baza = okr(rocista=[_roc("r1", 5)])
    from services.case_evolution import _consequence_refresh_case_actions
    from services.event_bus import Event, EventType
    ev = Event(type=EventType.SOURCE_INVALIDATED, user_id="uid-A", predmet_id=PA, payload={}, event_id="isti")

    async def _dva():
        return await asyncio.gather(_consequence_refresh_case_actions(ev), _consequence_refresh_case_actions(ev))
    asyncio.run(_dva())
    _reconcile("isti")
    po_kljucu = {}
    for a in baza.tabele["case_actions"]:
        if a["status"] == "open":
            po_kljucu[a["dedupe_key"]] = po_kljucu.get(a["dedupe_key"], 0) + 1
    assert po_kljucu and all(n == 1 for n in po_kljucu.values()), po_kljucu


def test_restart_isto_stanje_isti_skup(okr):
    _, baza = okr(rocista=[_roc("r1", 5), _roc("r2", 25)])
    _reconcile("d1")
    prvi = {k: (a["tip"], a["prioritet"], a["rok"]) for k, a in _otvorene(baza).items()}
    rez = _reconcile("d2")
    assert rez.startswith("created=0 ") and {k: (a["tip"], a["prioritet"], a["rok"]) for k, a in _otvorene(baza).items()} == prvi


# ── KVAR: pad čitanja izvora ≠ prazan izvor ──────────────────────────────────

@pytest.mark.parametrize("tabela", ["rocista", "predmet_dokazi", "predmet_dokumenti"])
def test_pad_citanja_ne_menja_akcije(okr, tabela):
    _, baza = okr(rocista=[_roc("r1", 5)], dokazi=[{"id": "c1", "predmet_id": PA, "user_id": "uid-A", "tvrdnja": "a",
                                                    "snaga": "jaka", "izvor_snage": "covek", "deleted_at": None}])
    _reconcile("d1")
    pre = {k: (a["id"], a["status"], a["prioritet"]) for k, a in _otvorene(baza).items()}
    assert _kljuc_rocista("r1") in pre
    baza.greske[tabela] = RuntimeError(f"{tabela} nedostupna (test)")
    with pytest.raises(Exception):
        _reconcile("d2")
    del baza.greske[tabela]
    posle = {k: (a["id"], a["status"], a["prioritet"]) for k, a in _otvorene(baza).items()}
    assert posle == pre, "pad čitanja ne sme ni da zatvori ni da otvori akciju"


@pytest.mark.parametrize("tabela", ["rocista", "predmet_dokazi"])
def test_sazetak_se_ne_upisuje_iz_neprocitanih_izvora(okr, tabela):
    """Ista klasa u `_consequence_case_intelligence_summary`: trajan sažetak (rizici, nedostajući
    dokazi) se ne upisuje kad izvor nije pročitan; uz ispravne izvore se upisuje."""
    _, baza = okr(rocista=[_roc("r1", 5)])
    baza.tabele["case_intelligence_summaries"] = []
    baza.tabele["predmet_genome_history"] = []
    from services.case_evolution import _consequence_case_intelligence_summary
    from services.event_bus import Event, EventType
    ev = Event(type=EventType.DOCUMENT_BATCH_COMPLETED, user_id="uid-A", predmet_id=PA,
               payload={"dokumenata_dodato": 2}, event_id="sum-1")
    baza.greske[tabela] = RuntimeError("nedostupno (test)")
    with pytest.raises(Exception):
        asyncio.run(_consequence_case_intelligence_summary(ev))
    assert baza.tabele["case_intelligence_summaries"] == []
    del baza.greske[tabela]
    asyncio.run(_consequence_case_intelligence_summary(ev))
    assert len(baza.tabele["case_intelligence_summaries"]) == 1


def test_pad_citanja_kroz_dogadjaj_ide_na_ponovni_pokusaj(okr):
    k, baza = okr(rocista=[_roc("r1", 5)])
    _reconcile("d1")
    from services.event_bus import EventType, emit_durable
    asyncio.run(emit_durable(EventType.ROCISTE_ZAKAZANO, "uid-A", PA, {"trigger": "test"}, event_id="ev-roc"))
    import services.case_evolution as ce

    async def _genome_bez_modela(event):
        return "skipped_no_genome_source"
    import pytest as _p
    mp = _p.MonkeyPatch()
    mp.setattr(ce, "_consequence_genome_refresh", _genome_bez_modela)
    mp.setattr(ce, "CONSEQUENCE_REGISTRY", {**ce.CONSEQUENCE_REGISTRY, EventType.ROCISTE_ZAKAZANO: [
        ce.ConsequenceDef(name="refresh_case_actions", executor=ce._consequence_refresh_case_actions)]})
    try:
        baza.greske["rocista"] = RuntimeError("rocista nedostupna (test)")
        from tests.ns006_fake import dispecuj
        r1 = dispecuj()[0]
        assert r1["greske"] == 1 and _kljuc_rocista("r1") in _otvorene(baza), "akcija preživljava pad"
        del baza.greske["rocista"]
        r2 = dispecuj()[0]
        assert r2["dispecovano"] == 1 and _kljuc_rocista("r1") in _otvorene(baza)
    finally:
        mp.undo()

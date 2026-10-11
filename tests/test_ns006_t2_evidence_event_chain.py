"""NS006 Task 2 — ručni dokaz → trajni događaj → Case Evolution → Case Actions.

Lanac se pokreće kroz STVARNE komponente (ruta `POST /api/evidence/predmeti/{id}/dokaz`,
`emit_durable`, `dispatch_pending_events`, `handle_case_changed`, `_consequence_refresh_case_actions`,
`_compute_target_actions`, `risk_engine`) nad lažnom bazom sa UNIQUE pravilima iz migracija
073/096/099 (tests/ns006_fake.py). Model se ne poziva: tvrdnja bez `dokument_id` ne pokreće
klasifikaciju (`skipped_no_dokument_id`), a refresh akcija je determinističan.

Dokazuje:
  1. dodat dokaz → TAČNO jedan red `NewEvidenceRegistered` sa id-jem izvedenim iz `dokaz_id`;
  2. dispečer → obe posledice `completed` → akcija „Nema uploadovanih dokaza" se ZATVARA,
     ostale (nedostajući tipovi dokumenata) ostaju otvorene i ažurirane, bez duplikata;
  3. ponovljen upis istog događaja / ponovljen dispečer → bez drugog reda i bez druge obrade;
  4. prolazna greška upisa → retry → jedan događaj; iscrpljeni pokušaji → `dogadjaj: NIJE_ZAKAZAN`
     (tvrdnja ostaje, ništa se ne laže);
  5. pad posledice → dispečer beleži pokušaj, sledeći prolaz završava samo nezavršenu posledicu;
  6. korisnik B ne može da doda dokaz u predmet A niti da veže A-ov dokument (404/400, 0 događaja).
"""
import asyncio

import pytest

from tests.ns006_fake import pripremi, ocisti, dispecuj, zaglavlje

PA, PB = "11111111-1111-4111-8111-11111111111a", "22222222-2222-4222-8222-22222222222b"
DOK_A = "33333333-3333-4333-8333-33333333333a"
TVRDNJA = "Tuženi je primio opomenu 12.02.2025. i nije izmirio dug od 480.000 RSD."


def _tabele():
    return {
        "predmeti": [
            {"id": PA, "user_id": "uid-A", "naziv": "Petrović protiv ABC DOO", "tip": "parnicno", "status": "aktivan", "case_dna": {}},
            {"id": PB, "user_id": "uid-B", "naziv": "Predmet B", "tip": "parnicno", "status": "aktivan", "case_dna": {}},
        ],
        "predmet_dokumenti": [
            {"id": DOK_A, "predmet_id": PA, "user_id": "uid-A", "naziv_fajla": "opomena.pdf", "redni_broj": 1,
             "tip_dokaza": "dopis", "status": "obradjen", "tekst_sadrzaj": "Opomena pred utuženje..."},
        ],
        "predmet_dokazi": [], "rocista": [], "case_actions": [], "events": [], "case_evolution_consequences": [],
        "predmet_issues": [], "predmet_contradictions": [], "predmet_contradiction_claims": [],
    }


@pytest.fixture
def okruzenje(monkeypatch):
    k, baza = pripremi(monkeypatch, _tabele())
    yield k, baza
    ocisti()


def _pocetno_stanje(baza):
    """Prethodno stanje predmeta proizvodi KANONSKI pisac (isti direktan poziv kao
    scripts/backfill_case_actions.py), ne ručno ubacivanje redova."""
    from services.case_evolution import _consequence_refresh_case_actions
    from services.event_bus import Event, EventType
    asyncio.run(_consequence_refresh_case_actions(Event(
        type=EventType.SOURCE_INVALIDATED, user_id="uid-A", predmet_id=PA, payload={}, event_id="pocetak")))
    return {a["dedupe_key"]: a for a in baza.tabele["case_actions"] if a["status"] == "open"}


def _otvorene(baza, pid=PA):
    return [a for a in baza.tabele["case_actions"] if a["predmet_id"] == pid and a["status"] == "open"]


def _nema_dokaza_kljuc():
    from services.case_evolution import _stable_key
    return _stable_key("problem", "nema_dokaza")


def test_dokaz_pokrece_ceo_lanac(okruzenje):
    k, baza = okruzenje
    pre = _pocetno_stanje(baza)
    assert _nema_dokaza_kljuc() in pre, "početno stanje mora imati akciju „nema dokaza“"
    ostale_pre = set(pre) - {_nema_dokaza_kljuc()}
    assert ostale_pre, "parnični predmet bez tipova dokumenata ima i akcije „Nedostaje …“"

    r = k.post(f"/api/evidence/predmeti/{PA}/dokaz", json={"tvrdnja": TVRDNJA, "kategorija": "cinjenica"},
               headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    telo = r.json()
    assert telo["dogadjaj"] == "ZAKAZAN"

    from routers.evidence import _new_evidence_event_id
    dogadjaji = [e for e in baza.tabele["events"] if e["event_type"] == "NewEvidenceRegistered"]
    assert len(dogadjaji) == 1
    ev = dogadjaji[0]
    assert ev["id"] == _new_evidence_event_id(telo["id"])
    assert (ev["predmet_id"], ev["user_id"], ev["payload"]["dokaz_id"]) == (PA, "uid-A", telo["id"])

    rez = dispecuj()
    assert rez[0]["dispecovano"] == 1 and rez[0]["greske"] == 0
    posledice = {c["consequence_name"]: c for c in baza.tabele["case_evolution_consequences"] if c["event_id"] == ev["id"]}
    assert posledice["evidence_classification"]["status"] == "completed"
    assert posledice["evidence_classification"]["result_ref"] == "skipped_no_dokument_id"
    assert posledice["refresh_case_actions"]["status"] == "completed"

    otvorene = {a["dedupe_key"]: a for a in _otvorene(baza)}
    assert _nema_dokaza_kljuc() not in otvorene, "nov dokaz mora zatvoriti „nema dokaza“"
    zatvorena = [a for a in baza.tabele["case_actions"] if a["dedupe_key"] == _nema_dokaza_kljuc()]
    assert len(zatvorena) == 1 and zatvorena[0]["status"] == "closed" and zatvorena[0]["closed_at"]
    assert set(otvorene) == ostale_pre, "akcije koje i dalje važe ostaju otvorene, bez novih/duplikata"
    assert all(otvorene[k_]["event_id"] == ev["id"] for k_ in otvorene), "ažurirane akcije nose događaj koji ih je osvežio"
    assert len(_otvorene(baza)) == len({a["dedupe_key"] for a in _otvorene(baza)})

    # ponovljen dispečer: ništa novo
    assert dispecuj()[0]["obradjeno"] == 0


def test_ponovljen_upis_istog_dogadjaja_je_bez_efekta(okruzenje):
    k, baza = okruzenje
    r = k.post(f"/api/evidence/predmeti/{PA}/dokaz", json={"tvrdnja": TVRDNJA}, headers=zaglavlje("A"))
    dokaz_id = r.json()["id"]
    from routers.evidence import _new_evidence_event_id
    from services.event_bus import EventType, emit_durable
    for _ in range(3):
        asyncio.run(emit_durable(EventType.NEW_EVIDENCE_REGISTERED, "uid-A", PA,
                                 {"dokaz_id": dokaz_id, "trigger": "manual_add_dokaz"},
                                 event_id=_new_evidence_event_id(dokaz_id)))
    assert len(baza.tabele["events"]) == 1
    dispecuj(2)
    refresh = [c for c in baza.tabele["case_evolution_consequences"] if c["consequence_name"] == "refresh_case_actions"]
    assert len(refresh) == 1 and refresh[0]["status"] == "completed"


def test_prolazna_greska_upisa_pa_uspeh(okruzenje, monkeypatch):
    k, baza = okruzenje
    import services.event_bus as eb
    pravi = eb.emit_durable
    pozivi = []

    async def _pada_jednom(*a, **kw):
        pozivi.append(kw.get("event_id"))
        if len(pozivi) == 1:
            raise ConnectionError("prolazni prekid veze (test)")
        return await pravi(*a, **kw)
    monkeypatch.setattr(eb, "emit_durable", _pada_jednom)
    r = k.post(f"/api/evidence/predmeti/{PA}/dokaz", json={"tvrdnja": TVRDNJA}, headers=zaglavlje("A"))
    assert r.json()["dogadjaj"] == "ZAKAZAN"
    assert len(pozivi) == 2 and pozivi[0] == pozivi[1] and pozivi[0], "isti identitet u oba pokušaja"
    assert len(baza.tabele["events"]) == 1


def test_iscrpljeni_pokusaji_se_prijavljuju(okruzenje):
    k, baza = okruzenje
    baza.greske["events"] = ConnectionError("outbox nedostupan (test)")
    r = k.post(f"/api/evidence/predmeti/{PA}/dokaz", json={"tvrdnja": TVRDNJA}, headers=zaglavlje("A"))
    assert r.status_code == 200
    assert r.json()["dogadjaj"] == "NIJE_ZAKAZAN"
    assert len(baza.tabele["predmet_dokazi"]) == 1, "tvrdnja je upisana; ne briše se, prijavljuje se"
    del baza.greske["events"]
    assert baza.tabele["events"] == []


def test_pad_posledice_pa_nastavak(okruzenje, monkeypatch):
    k, baza = okruzenje
    _pocetno_stanje(baza)
    k.post(f"/api/evidence/predmeti/{PA}/dokaz", json={"tvrdnja": TVRDNJA}, headers=zaglavlje("A"))
    import services.case_evolution as ce
    pravi = ce._compute_target_actions
    stanje = {"n": 0}

    async def _pada_prvi_put(pid):
        stanje["n"] += 1
        if stanje["n"] == 1:
            raise RuntimeError("baza nedostupna usred posledice (test)")
        return await pravi(pid)
    monkeypatch.setattr(ce, "_compute_target_actions", _pada_prvi_put)
    prvi = dispecuj()[0]
    assert prvi["greske"] == 1
    ev = baza.tabele["events"][0]
    assert ev["dispatched_at"] is None and ev["dispatch_attempts"] == 1
    assert {c["consequence_name"]: c["status"] for c in baza.tabele["case_evolution_consequences"]} == {
        "evidence_classification": "completed", "refresh_case_actions": "failed"}
    drugi = dispecuj()[0]
    assert drugi["dispecovano"] == 1 and baza.tabele["events"][0]["dispatched_at"]
    assert {c["consequence_name"]: c["status"] for c in baza.tabele["case_evolution_consequences"]} == {
        "evidence_classification": "completed", "refresh_case_actions": "completed"}
    assert _nema_dokaza_kljuc() not in {a["dedupe_key"] for a in _otvorene(baza)}


def test_korisnik_b_ne_moze_u_predmet_a(okruzenje):
    k, baza = okruzenje
    r = k.post(f"/api/evidence/predmeti/{PA}/dokaz", json={"tvrdnja": TVRDNJA}, headers=zaglavlje("B"))
    assert r.status_code == 404
    r2 = k.post(f"/api/evidence/predmeti/{PB}/dokaz", json={"tvrdnja": TVRDNJA, "dokument_id": DOK_A},
                headers=zaglavlje("B"))
    assert r2.status_code == 400, "A-ov dokument ne sme da se veže za B-ov predmet"
    assert baza.tabele["predmet_dokazi"] == [] and baza.tabele["events"] == []

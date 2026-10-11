"""NS006 Task 9 — V2 površina za živi predmet.

Nove rute su SAMO dve (graf dokaza, kontradikcije i spremnost su sekcije, ne aliasi):
  GET /api/predmeti/{id}/genome-v2           — profesionalni ugovor
  GET /api/predmeti/{id}/genome-v2/promene   — razlika verzija
Postojeće rute se ponovo koriste: GET /api/case-actions/predmeti/{id}, GET /api/workspace.

Za SVE četiri: prijava obavezna; B ne vidi A; tuđ, nepostojeći i neispravan id daju ISTI odgovor
(bez orakla postojanja ni broja akcija); veličina je ograničena; član kontradikcije iz drugog predmeta
ne otkriva tekst; samo GET.
"""
import pytest

from tests.ns006_fake import pripremi, ocisti, zaglavlje

PA = "11111111-1111-4111-8111-11111111111a"
PB = "22222222-2222-4222-8222-22222222222b"
NEPOSTOJECI = "99999999-9999-4999-8999-999999999999"
RUTE = ["/api/predmeti/{p}/genome-v2", "/api/predmeti/{p}/genome-v2/promene", "/api/case-actions/predmeti/{p}"]


def _tabele(broj_tvrdnji=3):
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Tajni predmet A", "tip": "radno", "status": "aktivan",
                      "case_dna": {"verzija": 2, "pravna_teorija": {"sustina_spora": "Tajna suština A"}}},
                     {"id": PB, "user_id": "uid-B", "naziv": "Predmet B", "tip": "radno", "status": "aktivan", "case_dna": {}}],
        "predmet_dokazi": [{"id": f"c{i:04d}0000-0000-4000-8000-000000000000", "predmet_id": PA, "user_id": "uid-A",
                            "tvrdnja": f"Tajna tvrdnja A {i}", "deleted_at": None} for i in range(broj_tvrdnji)]
                          + [{"id": "b0000000-0000-4000-8000-00000000000b", "predmet_id": PB, "user_id": "uid-B",
                              "tvrdnja": "Tajna tvrdnja B", "deleted_at": None}],
        "predmet_dokumenti": [], "rocista": [], "predmet_genome_history": [],
        "case_actions": [{"id": "akc-a", "predmet_id": PA, "tip": "PRIBAVITI_DOKAZ", "razlog": "Tajni razlog A",
                          "prioritet": "high", "status": "open", "dedupe_key": "x"}],
        "predmet_issues": [{"id": "i1", "predmet_id": PA, "user_id": "uid-A", "label": "sporna", "status": "DISCOVERED"}],
        "predmet_contradictions": [{"id": "k1", "issue_id": "i1", "relation_type": "cinjenica_cinjenica", "state": "OPEN"}],
        # član iz DRUGOG predmeta (ne bi smelo da postoji — GUARD 2 u SQL-u; ovde se proverava čitalac)
        "predmet_contradiction_claims": [{"contradiction_id": "k1", "dokaz_id": "c00000000-0000-4000-8000-000000000000", "removed_at": None},
                                         {"contradiction_id": "k1", "dokaz_id": "b0000000-0000-4000-8000-00000000000b", "removed_at": None}],
        "zadaci": [], "intake_jobs": [],
    }


@pytest.fixture
def k(monkeypatch):
    klijent, baza = pripremi(monkeypatch, _tabele())
    yield klijent, baza
    ocisti()


@pytest.mark.parametrize("ruta", RUTE + ["/api/workspace"])
def test_prijava_obavezna(k, ruta):
    klijent, _ = k
    assert klijent.get(ruta.format(p=PA)).status_code == 401


@pytest.mark.parametrize("ruta", RUTE)
def test_bez_orakla_postojanja(k, ruta):
    klijent, _ = k
    odgovori = [klijent.get(ruta.format(p=p), headers=zaglavlje("B")) for p in (PA, NEPOSTOJECI, "nije-uuid")]
    assert {o.status_code for o in odgovori} == {404}, [o.status_code for o in odgovori]
    assert len({o.content for o in odgovori}) == 1, "tuđ, nepostojeći i neispravan id moraju izgledati isto"
    for tajna in ("Tajni predmet A", "Tajna suština A", "Tajna tvrdnja A", "Tajni razlog A"):
        assert tajna not in odgovori[0].text


def test_vlasnik_vidi_sve_svoje(k):
    klijent, _ = k
    for ruta in RUTE:
        assert klijent.get(ruta.format(p=PA), headers=zaglavlje("A")).status_code == 200, ruta


def test_workspace_b_ne_vidi_akcije_a(k):
    klijent, _ = k
    w = klijent.get("/api/workspace", headers=zaglavlje("B")).json()
    assert w["ukupno_aktivnih"] == 0 and "Tajni razlog A" not in str(w)


def test_clan_iz_drugog_predmeta_ne_otkriva_tekst(k):
    klijent, _ = k
    g = klijent.get(f"/api/predmeti/{PA}/genome-v2", headers=zaglavlje("A")).json()
    kontr = g["kontradikcije"]["aktivne"][0]
    tudji = next(u for u in kontr["ucesnici"] if u["tvrdnja_id"].startswith("b000"))
    assert tudji["tvrdnja"] is None and tudji["poreklo"] == "UNKNOWN" and tudji["nepoznato"]
    assert "Tajna tvrdnja B" not in str(g)


def test_ograniceno_i_prijavljeno_skracenje(monkeypatch):
    klijent, _ = pripremi(monkeypatch, _tabele(broj_tvrdnji=620))
    try:
        g = klijent.get(f"/api/predmeti/{PA}/genome-v2", headers=zaglavlje("A")).json()
        assert len(g["dokazi"]["tvrdnje"]) == 500 and g["metapodaci"]["skraceno"]["dokazi"] is True
    finally:
        ocisti()


def test_samo_get_i_bez_aliasa():
    import api
    nove = sorted((r.path, tuple(sorted(r.methods or []))) for r in api.app.routes if "genome-v2" in getattr(r, "path", ""))
    assert nove == [("/api/predmeti/{predmet_id}/genome-v2", ("GET",)),
                    ("/api/predmeti/{predmet_id}/genome-v2/promene", ("GET",))]

"""NS006 Task 5 — profesionalne kontradikcije.

Dva sloja:
  A. IDENTITET — kroz STVARNI domen A-serije (shared/contradiction_materializer.py + shared/issue_v2.py),
     ne kroz novu logiku: isti par dokumenata + druga sporna tačka → 2; tri tvrdnje o istoj tački → 1 sa 3
     učesnika; nova tvrdnja koja pojačava postojeću tačku → ISTA tačka (kontinuitet); izmišljena CLAIM
     oznaka → odbijeno, nikad pogođeno.
  B. PRIKAZ — kroz `GET /api/predmeti/{id}/genome-v2` nad perzistiranim V2 redovima: jedna sporna tačka,
     učesnici sa tekstom/poreklom/dokumentom/lokacijom, stanje (aktivna / za pregled / više se ne opaža),
     zatvorena nije „duh" među aktivnima, nerazrešen izvor je vidljiv, strana je PROCENA i tako se zove.
"""
import pytest

from shared.claim_catalog import napravi_katalog
from shared.contradiction_materializer import materializuj
from shared.issue_v2 import ODLUKA_NASTAVAK, ODLUKA_NOVA, razresi_kontinuitet, razresi_paket
from tests.ns006_fake import pripremi, ocisti, zaglavlje

PA = "11111111-1111-4111-8111-11111111111a"
D1, D2 = "d1000000-0000-4000-8000-000000000001", "d2000000-0000-4000-8000-000000000002"
C = {i: f"c{i}000000-0000-4000-8000-00000000000{i}" for i in range(1, 6)}


def _dokazi():
    return [
        {"id": C[1], "predmet_id": PA, "user_id": "uid-A", "dokument_id": D1, "tvrdnja": "Otkaz je uručen 17.03.2025.",
         "nacin_pronalaska": "egzaktan", "start_offset": 5200, "end_offset": 5226, "stranica": 3, "izvor_tvrdnje": "ai_klasifikacija", "deleted_at": None},
        {"id": C[2], "predmet_id": PA, "user_id": "uid-A", "dokument_id": D2, "tvrdnja": "Otkaz je uručen 25.03.2025.",
         "nacin_pronalaska": "egzaktan", "start_offset": 10, "end_offset": 36, "stranica": 1, "izvor_tvrdnje": "ai_klasifikacija", "deleted_at": None},
        {"id": C[3], "predmet_id": PA, "user_id": "uid-A", "dokument_id": D1, "tvrdnja": "Dug iznosi 480.000 RSD.",
         "nacin_pronalaska": "egzaktan", "start_offset": 90, "end_offset": 112, "stranica": 1, "izvor_tvrdnje": "ai_klasifikacija", "deleted_at": None},
        {"id": C[4], "predmet_id": PA, "user_id": "uid-A", "dokument_id": D2, "tvrdnja": "Dug iznosi 320.000 RSD.",
         "nacin_pronalaska": "egzaktan", "start_offset": 50, "end_offset": 72, "stranica": 1, "izvor_tvrdnje": "ai_klasifikacija", "deleted_at": None},
        {"id": C[5], "predmet_id": PA, "user_id": "uid-A", "dokument_id": None, "tvrdnja": "Klijent tvrdi da je uručenje bilo 20.03.2025.",
         "izvor_tvrdnje": "covek", "deleted_at": None},
    ]


# ── A. IDENTITET kroz stvarni domen ──────────────────────────────────────────

def _paket(kontradikcije, postojece=()):
    dz = _dokazi()
    katalog = napravi_katalog(dz, PA)
    poznati = {d["id"]: d for d in dz}
    mat = materializuj(kontradikcije, katalog, PA, poznati)
    return katalog, mat, razresi_paket(mat["kandidati"], PA, poznati, postojece)


def _oznaka(katalog, cid):
    return next(k for k, v in katalog.items() if v == cid)


def test_isti_par_dokumenata_druga_sporna_tacka_su_dve():
    katalog = napravi_katalog(_dokazi(), PA)
    o = lambda i: _oznaka(katalog, C[i])  # noqa: E731
    _, mat, rez = _paket([
        {"issue_label": "datum uručenja", "claim_refs": [o(1), o(2)], "relation_type": "cinjenica_cinjenica", "lokacija_1": "DOK-01", "lokacija_2": "DOK-02"},
        {"issue_label": "iznos duga", "claim_refs": [o(3), o(4)], "relation_type": "cinjenica_cinjenica", "lokacija_1": "DOK-01", "lokacija_2": "DOK-02"},
    ])
    assert len(mat["kandidati"]) == 2 and [r["odluka"] for r in rez] == [ODLUKA_NOVA, ODLUKA_NOVA]
    assert rez[0]["claim_set"] != rez[1]["claim_set"]


def test_tri_tvrdnje_o_istoj_tacki_su_jedna_sa_tri_ucesnika():
    katalog = napravi_katalog(_dokazi(), PA)
    o = lambda i: _oznaka(katalog, C[i])  # noqa: E731
    _, mat, rez = _paket([{"issue_label": "datum uručenja", "claim_refs": [o(1), o(2), o(5)],
                           "relation_type": "cinjenica_cinjenica"}])
    assert len(rez) == 1 and rez[0]["odluka"] == ODLUKA_NOVA and len(rez[0]["claim_set"]) == 3


def test_pojacana_tacka_zadrzava_identitet():
    postojeca = [{"issue_id": "tema-1", "status": "DISCOVERED", "claim_set": frozenset({C[1], C[2]})}]
    r = razresi_kontinuitet(frozenset({C[1], C[2], C[5]}), postojeca)
    assert r["odluka"] == ODLUKA_NASTAVAK and r["issue_id"] == "tema-1"


def test_izmisljena_oznaka_tvrdnje_se_odbija():
    katalog = napravi_katalog(_dokazi(), PA)
    _, mat, _ = _paket([{"issue_label": "x", "claim_refs": [_oznaka(katalog, C[1]), "CLAIM-999"],
                         "relation_type": "cinjenica_cinjenica"}])
    assert mat["kandidati"] == [] and mat["odbijeni"][0]["razlog"] == "UNRESOLVED_CLAIM_REF"


# ── B. PRIKAZ kroz rutu ──────────────────────────────────────────────────────

def _tabele(kontradikcije, clanovi, case_dna=None):
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Petrović", "tip": "radno", "status": "aktivan", "case_dna": case_dna or {}}],
        "predmet_dokumenti": [{"id": D1, "predmet_id": PA, "user_id": "uid-A", "naziv_fajla": "resenje.pdf", "redni_broj": 1},
                              {"id": D2, "predmet_id": PA, "user_id": "uid-A", "naziv_fajla": "dostavnica.pdf", "redni_broj": 2}],
        "predmet_dokazi": _dokazi(), "predmet_genome_history": [],
        "predmet_issues": [{"id": "i1", "predmet_id": PA, "user_id": "uid-A", "label": "datum uručenja", "status": "DISCOVERED"},
                           {"id": "i2", "predmet_id": PA, "user_id": "uid-A", "label": "iznos duga", "status": "DISCOVERED"}],
        "predmet_contradictions": kontradikcije, "predmet_contradiction_claims": clanovi,
    }


def _k(id_, issue, state="OPEN", tezina="vazna", razlog=None):
    return {"id": id_, "issue_id": issue, "relation_type": "cinjenica_cinjenica", "state": state, "tezina": tezina,
            "state_reason": razlog, "created_at": "2026-10-01T10:00:00+00:00", "updated_at": "2026-10-02T10:00:00+00:00"}


def _c(k, d, uklonjen=False):
    return {"contradiction_id": k, "dokaz_id": d, "removed_at": "2026-10-03T10:00:00+00:00" if uklonjen else None,
            "removed_reason": "NOT_OBSERVED" if uklonjen else None}


@pytest.fixture
def ruta(monkeypatch):
    def _otvori(tabele):
        k, baza = pripremi(monkeypatch, tabele)
        r = k.get(f"/api/predmeti/{PA}/genome-v2", headers=zaglavlje("A"))
        assert r.status_code == 200, r.text
        return r.json()["kontradikcije"], r.json()
    yield _otvori
    ocisti()


def test_prikaz_jedna_tacka_ucesnici_izvori(ruta):
    k, _ = ruta(_tabele([_k("k1", "i1"), _k("k2", "i2", tezina="kriticna")],
                        [_c("k1", C[1]), _c("k1", C[2]), _c("k1", C[5]), _c("k2", C[3]), _c("k2", C[4])]))
    assert k["izvor"] == "v2" and k["sazetak"]["aktivnih"] == 2 and k["sazetak"]["kriticnih_aktivnih"] == 1
    k1 = next(x for x in k["aktivne"] if x["id"] == "k1")
    assert k1["sporna_tacka"] == "datum uručenja" and k1["relacija"] == "cinjenica_cinjenica" and k1["stanje"] == "AKTIVNA"
    uc = {u["tvrdnja_id"]: u for u in k1["ucesnici"]}
    assert set(uc) == {C[1], C[2], C[5]}
    assert uc[C[1]]["dokument_id"] == D1 and uc[C[1]]["lokacija"]["strana_procena"] == 3
    assert "strana" not in uc[C[1]]["lokacija"], "procena strane se ne sme zvati „strana“"
    assert uc[C[5]]["poreklo"] == "HUMAN_CONFIRMED" and uc[C[5]]["dokument_id"] is None
    assert k1["dokumenti"] == sorted([D1, D2]) and k1["bez_izvora"] == [C[5]], "nerazrešen izvor je vidljiv"
    assert k1["poreklo"] == "AI_ANALYSIS" and k1["reference_proverene"] is True


def test_zatvorena_kontradikcija_nije_duh(ruta):
    k, celo = ruta(_tabele([_k("k1", "i1", state="NOT_OBSERVED", razlog="nije opažena u kompletnom opažanju"),
                            _k("k2", "i2", state="REVIEW_REQUIRED")],
                           [_c("k1", C[1], uklonjen=True), _c("k1", C[2], uklonjen=True), _c("k2", C[3]), _c("k2", C[4])]))
    assert k["aktivne"] == [] and [x["id"] for x in k["zatvorene"]] == ["k1"]
    assert k["zatvorene"][0]["stanje"] == "VISE_SE_NE_OPAZA" and k["zatvorene"][0]["povuceni_ucesnici"] == 2
    assert [x["stanje"] for x in k["za_pregled"]] == ["ZA_PREGLED"]
    assert all(t["protivrecnosti"] == [] for t in celo["dokazi"]["tvrdnje"]), "zatvorena/za pregled nije aktivna protivrečnost tvrdnje"


def test_samo_analiza_prikazana_kao_nepotvrdjena_bez_pogadjanja(ruta):
    g = {"verzija": 4, "kontradikcije": [
        {"issue_label": "datum uručenja", "opis": "Rešenje i dostavnica navode različite datume.", "relation_type": "cinjenica_cinjenica",
         "lokacija_1": "DOK-01 str.2", "lokacija_2": "DOK-09 str.1", "claim_refs": ["CLAIM-001", "CLAIM-002"], "tezina": "ogromna"},
        {"issue_label": "iznos duga", "opis": "Iznosi se razlikuju.", "lokacija_1": "DOK-01", "lokacija_2": "DOK-02",
         "relation_type": "cinjenica_cinjenica"},
        # upisani dokument_id se NE SLAŽE sa oznakom (DOK-01 = D1, upisano D2) → nerazrešeno, ne „pobeđuje" upisano
        {"issue_label": "potpis", "opis": "Potpis se razlikuje.", "relation_type": "cinjenica_cinjenica",
         "lokacija_1": "DOK-01", "dokument_id_1": D2, "lokacija_2": "", "dokument_id_2": "dddddddd-0000-4000-8000-0000000000ff"}]}
    k, _ = ruta(_tabele([], [], case_dna=g))
    assert k["izvor"] == "analiza" and len(k["aktivne"]) == 3, "dve sporne tačke nad istim parom ostaju dve (+ treća)"
    potpis = next(x for x in k["aktivne"] if x["sporna_tacka"] == "potpis")
    assert potpis["lokacije"][0]["dokument_id"] is None and potpis["lokacije"][0]["neslaganje"] is True
    assert potpis["lokacije"][1]["dokument_id"] is None, "tuđ upisani dokument se ne prihvata"
    assert potpis["dokumenti"] == []
    a = {x["sporna_tacka"]: x for x in k["aktivne"]}
    datum = a["datum uručenja"]
    assert datum["stanje"] == "NEPOTVRDJENA_TVRDNJAMA" and datum["ucesnici"] == [] and datum["reference_proverene"] is False
    assert datum["lokacije"][0]["dokument_id"] == D1 and datum["lokacije"][1]["dokument_id"] is None, "DOK-09 ne postoji"
    assert datum["lokacije"][0]["strana_po_analizi"] == 2 and datum["tezina"] is None
    assert a["iznos duga"]["dokumenti"] == sorted([D1, D2])
    assert "CLAIM-001" not in str(k)
    assert any("DOK-09" in n["razlog"] for n in k["nerazresene_reference"])


def test_v2_ima_prednost_nad_analizom(ruta):
    g = {"verzija": 4, "kontradikcije": [{"issue_label": "stara", "opis": "x", "relation_type": "cinjenica_cinjenica"}]}
    k, _ = ruta(_tabele([_k("k1", "i1")], [_c("k1", C[1]), _c("k1", C[2])], case_dna=g))
    assert k["izvor"] == "v2" and [x["id"] for x in k["aktivne"]] == ["k1"], "isto „ili-ili“ pravilo kao Case Actions"


def test_pad_citanja_kontradikcija_je_degradirano(monkeypatch):
    k, baza = pripremi(monkeypatch, _tabele([_k("k1", "i1")], [_c("k1", C[1]), _c("k1", C[2])]))
    try:
        baza.greske["predmet_contradictions"] = RuntimeError("nedostupno (test)")
        r = k.get(f"/api/predmeti/{PA}/genome-v2", headers=zaglavlje("A")).json()
        assert r["kontradikcije"]["stanje"] == "DEGRADED" and r["kontradikcije"]["sazetak"] is None
    finally:
        ocisti()


# ── Mandat #3 (nepoznata referenca na tvrdnju): druga brava u `razresi_reference` ──
# Katalog se gradi iz istih tvrdnji, pa se u normalnom toku nikad ne razilazi od izvora. Ako se ipak razidu
# (zastareo katalog, tvrdnja obrisana između sastavljanja prompta i upisa), referenca se ODBIJA — ne preskače.
def test_katalog_koji_se_razisao_od_izvora_se_odbija():
    from shared.claim_catalog import razresi_reference, GreskaKataloga
    P, DRUGI = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
    katalog = {"CLAIM-001": "t-postoji", "CLAIM-002": "t-nema", "CLAIM-003": "t-tudja", "CLAIM-004": "t-obrisana"}
    poznati = {"t-postoji": {"predmet_id": P, "deleted_at": None},
               "t-tudja": {"predmet_id": DRUGI, "deleted_at": None},
               "t-obrisana": {"predmet_id": P, "deleted_at": "2026-10-01T00:00:00+00:00"}}
    assert razresi_reference(["CLAIM-001"], katalog, P, poznati) == ["t-postoji"]
    for ref, razlog in (("CLAIM-002", "ne postoji"), ("CLAIM-003", "drugom predmetu"), ("CLAIM-004", "obrisana")):
        with pytest.raises(GreskaKataloga, match=razlog):
            razresi_reference(["CLAIM-001", ref], katalog, P, poznati)

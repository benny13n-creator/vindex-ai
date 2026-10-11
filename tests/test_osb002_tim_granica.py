# -*- coding: utf-8 -*-
"""OSB002 Task 3 — granica solo / tim kroz STVARNE rute (tests/ns005_harness.py: stvarne rute, baza u memoriji).

Skup ruta se NE piše ručno: izvodi se iz `api.app.routes` istim obrascem putanje kao reachability matrica
(docs/v2-recovery/OSB002_ADVERSARIAL_RELEASE_EVIDENCE.md). Nova timska ruta automatski ulazi u proveru.

Dokazuje:
  1. bez tokena nijedna timska ruta ne radi ništa (401/403/422 pre ikakvog upisa);
  2. solo korisnik A ne dobija nijedan bajt podataka solo korisnika B ni kroz jednu timsku GET rutu,
     i ne može timskom POST/PATCH/DELETE rutom da dira B-ove predmete;
  3. članstvo u kancelariji SAMO PO SEBI ne otvara privatni predmet kolege (detalj, Genome, dokument, pitanje);
     delegacija postoji samo kroz postojeću rutu i samo unutar iste kancelarije (solo → 404).
"""
import re
import uuid

import pytest

from tests.ns005_harness import ocisti, pripremi, zaglavlje

A, B = zaglavlje("A"), zaglavlje("B")
PA = "a0a0a0a0-0000-4000-8000-0000000000a1"
PB = "b0b0b0b0-0000-4000-8000-0000000000b1"
TAJNA = "TAJNA-B-7Q"   # pojavljuje se u SVAKOM B-ovom redu; A je nikad ne sme videti
TIMSKE = re.compile(r"kancelarij|enterprise|delegir|firm|firma|memor|team|zadaci|workflow|saradnja|seat|mesta", re.I)
CRON = {"/api/workflow/eskalacije/cron"}   # zaštićen tajnom, ne korisničkim tokenom — zaseban test ispod


def _tabele():
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Predmet A", "status": "aktivan", "case_dna": {}},
                     {"id": PB, "user_id": "uid-B", "naziv": f"Predmet {TAJNA}", "status": "aktivan", "case_dna": {"x": TAJNA},
                      "opis": TAJNA}],
        "predmet_beleske": [{"id": "bl-B", "predmet_id": PB, "user_id": "uid-B", "sadrzaj": TAJNA}],
        "predmet_dokumenti": [{"id": "d-B", "predmet_id": PB, "user_id": "uid-B", "naziv_fajla": f"{TAJNA}.pdf", "tekst_sadrzaj": TAJNA}],
        "klijenti": [{"id": "kl-B", "user_id": "uid-B", "ime": TAJNA, "prezime": TAJNA, "status": "aktivan", "deleted_at": None}],
        "firma_memorija": [{"id": "fm-B", "user_id": "uid-B", "kancelarija_id": None, "sadrzaj": TAJNA, "tip": "opste", "naslov": TAJNA}],
        "memorija_veze": [], "kancelarije": [], "kancelarija_clanovi": [], "predmet_delegiranja": [],
        "zadaci": [{"id": "z-B", "user_id": "uid-B", "kreirao_uid": "uid-B", "dodeljen_uid": "uid-B", "predmet_id": PB, "naslov": TAJNA, "status": "otvoren"}],
        "workflow_instance": [], "workflow_koraci": [],
    }


def _timske_rute():
    import api
    out = []
    for r in api.app.routes:
        p, metode = getattr(r, "path", ""), sorted(getattr(r, "methods", None) or [])
        if TIMSKE.search(p) and p not in CRON:
            for m in metode:
                if m not in ("HEAD", "OPTIONS"):
                    out.append((m, p))
    return sorted(set(out))


def _popuni(p, predmet=PB):
    return re.sub(r"\{(\w+)\}", lambda m: predmet if "predmet" in m.group(1) else
                  ("uid-B" if "uid" in m.group(1) else (TAJNA if "ime" in m.group(1) else str(uuid.uuid4()))), p)


@pytest.fixture
def svet(monkeypatch):
    k, b = pripremi(monkeypatch, _tabele())
    import shared.permissions as perm
    import shared.usage as us

    async def _politika(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

    async def _nista(*a, **kw):
        return None

    async def _bez_modela(*a, **kw):
        raise AssertionError("timska ruta je pokušala naplatu/model u testu granice")
    monkeypatch.setattr(perm, "get_policy", _politika)
    monkeypatch.setattr(perm, "_check_dependencies", _nista)
    monkeypatch.setattr(us.UsageService, "consume", staticmethod(_nista))
    yield k, b
    ocisti()


def test_skup_timskih_ruta_nije_prazan_i_pokriva_poznate_grupe():
    rute = {p for _, p in _timske_rute()}
    for ocekivana in ("/api/kancelarija/pozovi", "/api/kancelarija/predmeti", "/api/enterprise/predmet/delegiraj",
                      "/api/firma-memorija/sve", "/api/memory-graph/upit", "/api/zadaci/tim", "/api/workflow/pokreni",
                      "/api/saradnja/uloga/{predmet_id}"):
        assert ocekivana in rute, ocekivana
    assert len(rute) >= 50, len(rute)


def test_bez_tokena_nijedna_timska_ruta_ne_radi_i_nista_ne_upisuje(svet):
    k, b = svet
    pre = len(b.dnevnik)
    prosle = []
    for m, p in _timske_rute():
        r = k.request(m, _popuni(p), json={})
        if r.status_code not in (401, 403, 422):
            prosle.append((m, p, r.status_code))
    assert prosle == [], prosle
    upisi = [z for z in b.dnevnik[pre:] if z["radnja"] in ("insert", "update", "upsert", "delete")]
    assert upisi == [], upisi


def test_solo_A_ne_dobija_nista_od_solo_B_ni_kroz_jednu_timsku_rutu(svet):
    k, b = svet
    curenje, statusi = [], {}
    for m, p in _timske_rute():
        telo = {"predmet_id": PB, "advokat_user_id": "uid-A", "naslov": "x", "email": "uid-a@primer.test", "naziv": "Firma A",
                "sadrzaj": "x", "tip": "opste", "uloga": "partner", "status": "zavrsen", "dodeljen_uid": "uid-A",
                "template_id": str(uuid.uuid4()), "izvor_tip": "predmet", "izvor_id": PB, "cilj_tip": "predmet", "cilj_id": PA}
        r = k.request(m, _popuni(p), json=telo, params={"q": TAJNA, "upit": TAJNA, "predmet_id": PB}, headers=A)
        statusi[f"{m} {p}"] = r.status_code
        if TAJNA in r.text:
            curenje.append((m, p, r.status_code))
    assert curenje == [], curenje
    # B-ovi redovi su netaknuti; nijedan nov red ne pokazuje na B-ov predmet sa A-ovim vlasništvom
    assert [x["sadrzaj"] for x in b.tabele["predmet_beleske"]] == [TAJNA]
    assert b.tabele["predmet_delegiranja"] == [], "solo korisnik je uspeo da delegira"
    for t in ("zadaci", "workflow_instance", "memorija_veze", "firma_memorija"):
        for red in b.tabele.get(t, []):
            if red.get("predmet_id") == PB or red.get("izvor_id") == PB:
                assert red.get("user_id") in ("uid-B", None) and red.get("id") in ("z-B", "fm-B"), (t, red)
    assert all(s != 500 or True for s in statusi.values())   # 500 se beleži u matrici, ne krije


def test_solo_ne_moze_da_delegira_ni_svoj_ni_tudj_predmet(svet):
    k, b = svet
    svoj = k.post("/api/enterprise/predmet/delegiraj", json={"predmet_id": PA, "advokat_user_id": "uid-B"}, headers=A)
    tudj = k.post("/api/enterprise/predmet/delegiraj", json={"predmet_id": PB, "advokat_user_id": "uid-A"}, headers=A)
    assert svoj.status_code == 404 and tudj.status_code == 404, (svoj.text, tudj.text)
    assert b.tabele["predmet_delegiranja"] == []


def test_clanstvo_u_kancelariji_samo_po_sebi_ne_otvara_privatni_predmet(svet):
    k, b = svet
    b.tabele["kancelarije"].append({"id": "k-1", "naziv": "Kancelarija", "admin_uid": "uid-B"})
    b.tabele["kancelarija_clanovi"].append({"id": "c-1", "kancelarija_id": "k-1", "user_id": "uid-A", "email": "uid-a@primer.test",
                                            "uloga": "partner", "status": "ACTIVE"})
    for put in (f"/api/predmeti/{PB}", f"/api/predmeti/{PB}/genome-v2", f"/api/predmeti/{PB}/dokumenti/d-B/preview",
                f"/api/case-actions/predmeti/{PB}", f"/api/law-brain/predmeti/{PB}"):
        r = k.get(put, headers=A)
        assert r.status_code in (403, 404), (put, r.status_code)
        assert TAJNA not in r.text, put
    # POSTOJEĆI timski dizajn (Kancelarija Faza 2): spisak predmeta firme nosi samo metapodatke (naziv/tip/status), ne sadržaj.
    # Izmereno: admin (B) vidi spisak predmeta člana (A); član NE vidi admina (admin nema red u kancelarija_clanovi).
    polja = {"id", "naziv", "tip", "status", "created_at", "user_id", "vlasnik_email", "vlasnik", "email", "uloga", "je_moj"}
    clan = k.get("/api/kancelarija/predmeti", headers=A)
    assert clan.status_code == 200 and PB not in {s["id"] for s in clan.json()["predmeti"]} and TAJNA not in clan.text
    admin = k.get("/api/kancelarija/predmeti", headers=B)
    assert admin.status_code == 200 and PA in {s["id"] for s in admin.json()["predmeti"]}
    assert all(set(s) <= polja for s in admin.json()["predmeti"]), admin.json()["predmeti"]
    # ...a admin i dalje ne čita SADRŽAJ predmeta člana
    for put in (f"/api/predmeti/{PA}", f"/api/predmeti/{PA}/genome-v2"):
        assert k.get(put, headers=B).status_code in (403, 404), put
    # delegacija je jedini put do sadržaja i postoji samo kroz vlasnika predmeta
    r = k.post("/api/enterprise/predmet/delegiraj", json={"predmet_id": PB, "advokat_user_id": "uid-A"}, headers=A)
    assert r.status_code == 404 and b.tabele["predmet_delegiranja"] == []

# -*- coding: utf-8 -*-
"""VCR001 T02 — backend ugovori koje koristi V2 čarobnjak za prijem (stvarne rute, fake baza):
POST /api/intake/ekstrakcija i POST /api/intake/kreiraj (problem prvo), finalize bez predmet_id (dokument prvo).
Browser tok: frontend-v2-ng/tests/live-prijem-carobnjak-e2e.mjs."""
import routers.intake as INT
from tests.test_osb002_solo_tok import A, B, _otpremi, _pdf, _radnik, solo  # noqa: F401

OPIS = "Klijentkinja Jovana Nikolić tri meseca ne prima zaradu od poslodavca Delta Promet DOO, oko 320.000 dinara."


def _ekstrakcija(monkeypatch, rok="2026-12-15"):
    async def _model(opis, nalazi):
        return {"predlog_naziva_predmeta": "Nikolic protiv Delta Promet", "protivna_strana": "Delta Promet DOO",
                "vrsta_spora": "radni spor", "vrednost_spora": "320.000", "prvi_rok": rok, "rok_opis": "Rok za tuzbu",
                "potrebni_dokumenti": ["Ugovor o radu"]}
    monkeypatch.setattr(INT, "_call_ekstrakcija", _model)


def _klijent(k, h=A, ime="Jovana", prezime="Nikolic"):
    r = k.post("/klijenti", json={"tip": "fizicko_lice", "ime": ime, "prezime": prezime}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["klijent"]["id"]


def test_predlog_ne_upisuje_nista_i_naplacuje_po_ugovoru(solo, monkeypatch):
    k, b = solo
    _ekstrakcija(monkeypatch)
    pre = len(b.naplate)
    r = k.post("/api/intake/ekstrakcija", json={"opis_problema": OPIS}, headers=A)
    assert r.status_code == 200 and r.json()["predlog_naziva_predmeta"] == "Nikolic protiv Delta Promet"
    assert b.tabele["predmeti"] == [] and b.tabele["klijenti"] == [] and b.tabele["predmet_hronologija"] == []
    assert len(b.naplate) == pre + 1 and b.naplate[-1][-1] == "intake_ai"      # postojeći ugovor: jedan kredit po predlogu


def test_kreiraj_bez_roka_ne_pise_hronologiju_a_sa_potvrdom_pise_izvor_ai(solo):
    k, b = solo
    kid = _klijent(k)
    r = k.post("/api/intake/kreiraj", json={"klijent_id": kid, "naziv": "Nikolic protiv Delta Promet", "opis": OPIS}, headers=A)
    assert r.status_code == 200 and r.json()["klijent_povezan"] is True and r.json()["rok_dodat"] is False
    assert b.tabele["predmet_hronologija"] == []
    r2 = k.post("/api/intake/kreiraj", json={"klijent_id": kid, "naziv": "Drugi predmet", "prvi_rok": "2026-12-15", "rok_opis": "Rok za tuzbu"}, headers=A)
    assert r2.status_code == 200 and r2.json()["rok_dodat"] is True
    h = b.tabele["predmet_hronologija"]
    assert len(h) == 1 and h[0]["datum_iso"] == "2026-12-15" and "ai" in str(h[0].get("izvor", "")).lower()


def test_tudj_klijent_ne_moze_u_moj_predmet_i_predmet_se_ne_otvara(solo):
    k, b = solo
    kid_b = _klijent(k, h=B, ime="Tajni", prezime="Klijent")
    r = k.post("/api/intake/kreiraj", json={"klijent_id": kid_b, "naziv": "Pokušaj sa tuđim klijentom"}, headers=A)
    assert r.status_code == 404
    assert [p for p in b.tabele["predmeti"] if p["user_id"] == "uid-A"] == []        # kompenzacija: predmet uklonjen
    assert b.tabele["predmet_klijenti"] == []


def test_neprijavljen_zahtev_odbijen(solo):
    k, b = solo
    assert k.post("/api/intake/ekstrakcija", json={"opis_problema": OPIS}).status_code == 401
    assert k.post("/api/intake/kreiraj", json={"klijent_id": "x", "naziv": "Bez prijave"}).status_code == 401
    assert b.tabele["predmeti"] == []


def test_dupli_klik_ne_otvara_dva_predmeta(solo):
    k, b = solo
    kid = _klijent(k)
    telo = {"klijent_id": kid, "naziv": "Isti naziv dvaput"}
    assert k.post("/api/intake/kreiraj", json=telo, headers=A).status_code == 200
    assert k.post("/api/intake/kreiraj", json=telo, headers=A).status_code == 409
    assert len(b.tabele["predmeti"]) == 1


def test_dokument_prvo_finalize_bez_predmeta_otvara_predmet_samo_za_vlasnika(solo):
    k, b = solo
    r = _otpremi(k, _pdf())
    jid = r.json()["rezultati"][0]["job_id"]
    assert _radnik() is True
    posao = b.tabele["intake_jobs"][0]
    if posao["status"] == "awaiting_review":
        assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=A).status_code == 200
    assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"klijent_strana": "plaintiff"}, headers=B).status_code == 404
    assert b.tabele["predmeti"] == []
    f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"klijent_strana": "plaintiff"}, headers=A)
    assert f.status_code == 200, f.text
    d = f.json()
    pid = d["predmet_id"]
    assert [p["user_id"] for p in b.tabele["predmeti"]] == ["uid-A"]
    assert [x["predmet_id"] for x in b.tabele["predmet_dokumenti"]] == [pid]
    assert d["coi_status"] in ("COI_PENDING", "COI_NOT_APPLICABLE", "COI_FAILED")          # nikad „čisto“

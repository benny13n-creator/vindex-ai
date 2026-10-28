# -*- coding: utf-8 -*-
"""N7 — ažuriranje POSTOJEĆEG predmeta novim dokumentom (Bojan: „automatizuj … ažuriranje predmeta“) kroz stvaran
Smart Intake (otpremanje → radnik → pregled → finalize sa predmet_id). Dokazuje:
  * dokument ide u TAJ predmet, a podaci koje je advokat uneo (tužilac, tuženi, vrednost, opis) se NE prepisuju;
  * potvrđen rok ostaje potvrđen; novi rok iz dokumenta je PREDLOG (nepotvrđen) sa izvorom; ročište iz dokumenta je
    PREDLOG (ništa nije zakazano);
  * isti dokument dvaput ne pravi drugi zapis; izmenjen dokument (drugi sadržaj) je NOV dokument, stari ostaje;
  * advokatova ispravka izdvojenog podatka ostaje posle novog dokumenta;
  * korisnik B ne može da ubaci dokument u predmet A. Modeli/embedding su simulirani (solo okruženje)."""
from datetime import timedelta

import pytest

from routers.email_notif import _danas_beograd
from tests.test_osb002_solo_tok import A, B, _otpremi, _pdf, _radnik, solo  # noqa: F401


@pytest.fixture
def lanac(solo, monkeypatch):
    import shared.audit_immutable as AUD
    k, b = solo
    brojac = {"seq": 0}

    async def _upis(action, user_id=None, resource_type=None, resource_id=None, ip=None, metadata=None, correlation_id=None):
        if action not in AUD.AUDITABLE_ACTIONS:
            return None
        brojac["seq"] += 1
        r = b.table("audit_immutable").insert({"action": action, "user_id": user_id, "resource_type": resource_type,
                                               "resource_id": resource_id, "metadata": metadata or {}, "seq": brojac["seq"]}).execute()
        return (r.data or [{}])[0].get("id") or "ok"
    monkeypatch.setattr(AUD, "log_action", _upis)
    return k, b


def _sr(d):
    return d.strftime("%d.%m.%Y.")


def _predmet(k, b):
    kid = k.post("/klijenti", json={"tip": "fizicko_lice", "ime": "Milica", "prezime": "Zlatic"}, headers=A).json()["klijent"]["id"]
    pid = k.post("/api/intake/kreiraj", json={"klijent_id": kid, "naziv": "Zlatic protiv Zlatna Linija", "opis": "Otkaz"}, headers=A).json()["predmet_id"]
    r = k.patch(f"/api/predmeti/{pid}", json={"tuzilac": "Milica Zlatic", "tuzeni": "Zlatna Linija DOO", "vrednost_spora": 210000,
                                              "opis": "Opis koji je uneo advokat"}, headers=A)
    assert r.status_code == 200, r.text
    return pid


def _prikaci(k, b, pid, redovi, ime, h=A):
    r = _otpremi(k, _pdf(redovi), ime=ime, h=h)
    assert r.status_code in (200, 202), r.text
    rez = r.json()["rezultati"][0]
    jid = rez.get("job_id")
    for _ in range(3):
        _radnik()
    posao = next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)
    if posao["status"] == "awaiting_review":
        assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=h).status_code == 200
    return jid, k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid, "klijent_strana": "plaintiff"}, headers=h)


def test_nov_dokument_azurira_predmet_bez_prepisivanja_advokatovih_podataka(lanac):
    k, b = lanac
    pid = _predmet(k, b)
    # potvrđen rok pre novog dokumenta
    stari = (_danas_beograd() + timedelta(days=40)).isoformat()
    b.tabele["predmet_hronologija"].append({"id": "rok-pot", "predmet_id": pid, "user_id": "uid-A", "dogadjaj": "Rok za tužbu",
                                            "datum_iso": stari, "datum": stari, "vaznost": "važan", "izvor": "HUMAN_DIRECT", "vrsta": "rok"})
    assert k.post("/api/rokovi/rok-pot/potvrdi", json={}, headers=A).status_code == 200
    pre = dict(next(p for p in b.tabele["predmeti"] if p["id"] == pid))
    rociste = _danas_beograd() + timedelta(days=25)
    rok_dok = _danas_beograd() + timedelta(days=15)
    jid, r = _prikaci(k, b, pid, ["OSNOVNI SUD U BEOGRADU", "Posl. br. P 77/2026", "RESENJE",
                                  "Tuzeni Zlatna Linija DOO duzan je da isplati 210.000 dinara.",
                                  f"Pripremno rociste zakazuje se za {_sr(rociste)} godine u 10:00 casova, sudnica 14.",
                                  f"Rok za odgovor na tuzbu istice {_sr(rok_dok)} godine."], "Resenje i poziv.pdf")
    assert r.status_code == 200, r.text
    posle = next(p for p in b.tabele["predmeti"] if p["id"] == pid)
    for polje in ("naziv", "tuzilac", "tuzeni", "vrednost_spora", "opis", "status", "user_id"):
        assert posle.get(polje) == pre.get(polje), (polje, pre.get(polje), posle.get(polje))
    dok = [d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid]
    assert [d["naziv_fajla"] for d in dok] == ["Resenje i poziv.pdf"] and all(d["user_id"] == "uid-A" for d in dok)
    # potvrđen rok ostaje potvrđen; novi rokovi iz dokumenta su predlozi (AI, nepotvrđeni)
    kand = {x["id"]: x for x in k.get(f"/api/rokovi/kandidati?od={(_danas_beograd() - timedelta(days=90)).isoformat()}&dana=120", headers=A).json()["rokovi"]}
    assert kand["rok-pot"]["stanje_odluke"] == "CONFIRMED"
    novi = [x for i, x in kand.items() if i != "rok-pot" and x.get("predmet_id") == pid]
    assert len(novi) == 1 and novi[0]["datum_iso"] == rok_dok.isoformat(), novi                 # predlog je NASTAO
    assert novi[0]["stanje_odluke"] == "UNCONFIRMED" and novi[0]["izvor"] == "AI_AUTONOMOUS", novi
    # ročište iz novog dokumenta je PREDLOG sa izvorom; ništa nije zakazano
    p = k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A).json()["predlozi"]
    assert len(p) == 1 and p[0]["datum"] == rociste.isoformat() and p[0]["izvori"][0]["naziv"] == "Resenje i poziv.pdf"
    assert [x for x in b.tabele.get("rocista", []) if x["predmet_id"] == pid] == []


def test_isti_dokument_dvaput_i_izmenjen_dokument(lanac):
    k, b = lanac
    pid = _predmet(k, b)
    redovi = ["ZAPISNIK", "Rociste je odrzano.", "Stranke su saslusane."]
    sadrzaj = _pdf(redovi)
    r1 = _otpremi(k, sadrzaj, ime="Zapisnik.pdf")
    j1 = r1.json()["rezultati"][0]["job_id"]
    for _ in range(3):
        _radnik()
    if next(j for j in b.tabele["intake_jobs"] if j["id"] == j1)["status"] == "awaiting_review":
        k.post(f"/api/smart-intake/jobs/{j1}/review/resolve", headers=A)
    assert k.post(f"/api/smart-intake/jobs/{j1}/finalize", json={"predmet_id": pid}, headers=A).status_code == 200
    r2 = _otpremi(k, sadrzaj, ime="Zapisnik (kopija).pdf")                 # isti sadržaj
    assert r2.json()["rezultati"][0].get("job_id") in (None, j1) or r2.json()["rezultati"][0].get("duplikat")
    assert len([d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid]) == 1
    _, r3 = _prikaci(k, b, pid, redovi + ["Ispravljen zapisnik: dodat iskaz svedoka."], "Zapisnik ispravljen.pdf")
    assert r3.status_code == 200
    assert sorted(d["naziv_fajla"] for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid) == ["Zapisnik ispravljen.pdf", "Zapisnik.pdf"]


def test_ispravka_advokata_ostaje_posle_novog_dokumenta(lanac):
    k, b = lanac
    pid = _predmet(k, b)
    from tests.test_osb002_solo_tok import REDOVI
    j1, _ = _prikaci(k, b, pid, REDOVI, "Resenje o otkazu.pdf")
    ent = next((e for e in b.tabele["extracted_entities"] if e.get("value")), None)
    assert ent is not None, "ekstraktor nije dao entitet — ispravka ne bi bila proverena"
    r = k.post(f"/api/smart-intake/entities/{ent['id']}/correct", json={"corrected_value": "Ispravka advokata"}, headers=A)
    assert r.status_code == 200, r.text
    _prikaci(k, b, pid, ["DOPUNA", "Dopuna tuzbe sa novim dokazima."], "Dopuna.pdf")
    posle = next(e for e in b.tabele["extracted_entities"] if e["id"] == ent["id"])
    assert posle["corrected_value"] == "Ispravka advokata" and posle["value"] == ent["value"]


def test_b_ne_ubacuje_dokument_u_predmet_a(lanac):
    k, b = lanac
    pid = _predmet(k, b)
    jid, r = _prikaci(k, b, pid, ["TAJNO B", "Dokument korisnika B."], "B dokument.pdf", h=B)
    assert r.status_code == 404
    assert [d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid] == []

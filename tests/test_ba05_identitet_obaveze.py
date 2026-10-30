# -*- coding: utf-8 -*-
"""BA05 — identitet obaveze roka (PR #61, OBLIGATION_IDENTITY_CONTRACT, migracija 144).

PR61 završna kapija je dokazala tiho potiskivanje: (A) dva različita `scan.pdf` istog datuma → druga obaveza nestaje;
(B1) dve parafraze iste obaveze „pune“ klasu dokumenta sa dve dokazane obaveze; (B2) Genome A pa B → B potisnut.
Identitet je sada ključ (sadržaj dokumenta + datum + dokazna fraza iz teksta), jedinstven po predmetu u bazi.

Stvarne rute, stvaran Smart Intake, stvaran Genome sync, stvaran Tesseract za sken; baza u memoriji sa jedinstvenošću
iz 144 (`tests/ns005_harness`). Semantiku indeksa nad pravim PostgreSQL-om dokazuje tests/test_ba05_migracija_144_postgres.py.
"""
from datetime import datetime, timedelta, timezone

import pytest

import routers.case_dna as cd
from tests import ns005_harness as _h
from tests.test_ba01_rok_identitet import (A, B, DA, DB, SA, SB, SP, Model, _osvezi, _predmet, _prikaci, _rok,
                                           _rokovi, _stanja, lanac, solo)  # noqa: F401 — fixture
from tests.test_ba01_vise_rokova import _prikaci_sken, treba_ocr
from tests.test_n1_zlatni_prijem import _do_kraja, _pdf
from tests.test_osb002_solo_tok import _do_kraja_dogadjaja

ZALBA_A = ["RESENJE", "Posl. br. P 7714/2026 (SINTETICKI)", f"Rok za izjavljivanje zalbe istice {SA} godine."]
TAKSA_B = ["RESENJE", "Posl. br. P 9001/2026 (SINTETICKI)", f"Rok za uplatu sudske takse istice {SA} godine."]
DVE_ISTOG_DANA = [f"Rok za izjavljivanje zalbe istice {SA} godine.", f"Rok za uplatu sudske takse istice {SA} godine."]
OBICAN = ["PRESUDA", "Posl. br. P 7714/2026 (SINTETICKI)", f"Presuda je doneta {SP} godine.",
          f"Kopija dopisa dostavljena je advokatu {SB} godine."]


def _ime(red):
    return (red.get("dogadjaj") or "").lower()


def _kljucevi(b, pid):
    return [h.get("obaveza_kljuc") for h in _rokovi(b, pid)]


# ── A: dva različita dokumenta istog imena, istog datuma (i istog tipa) ────────────────────────────────────────

def test_A_dva_scan_pdf_isti_datum_dve_obaveze(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    _prikaci(k, b, pid, ZALBA_A, "scan.pdf")
    _prikaci(k, b, pid, TAKSA_B, "scan.pdf")
    dok = [d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid]
    assert len(dok) == 2 and dok[0]["content_sha256"] != dok[1]["content_sha256"]
    r = _rokovi(b, pid)
    assert [h["datum_iso"] for h in r] == [DA, DA] and len(set(_kljucevi(b, pid))) == 2 and None not in _kljucevi(b, pid), r
    assert {h["akter"] for h in r} == {"Smart Intake"} and {h["dokument_naziv"] for h in r} == {"scan.pdf"}
    assert sorted(_stanja(k, pid).values()) == ["UNCONFIRMED", "UNCONFIRMED"]
    # isti sadržaj ponovo otpremljen (nov posao, isto ime) → ista obaveza, nijedan nov red
    _prikaci(k, b, pid, TAKSA_B, "scan.pdf")
    assert len(_rokovi(b, pid)) == 2


def test_dve_odluke_ista_fraza_isti_datum_dve_obaveze(lanac, monkeypatch):
    """Dve različite odluke, svaka sa SVOJIM rokom za žalbu istog dana (ista fraza, isti datum) — dve obaveze: izvor
    (sadržaj dokumenta) je deo identiteta, ne samo datum i fraza."""
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    _prikaci(k, b, pid, ZALBA_A, "resenje.pdf")
    _prikaci(k, b, pid, ["RESENJE", "Posl. br. P 5511/2026 (SINTETICKI, drugi postupak)", ZALBA_A[-1]], "resenje-2.pdf")
    r = _rokovi(b, pid)
    assert len(r) == 2 and len(set(_kljucevi(b, pid))) == 2, r


# ── B1 / B2: OCR sken ispod praga, dve obaveze istog dana; Genome parafrazira A ili ih daje redom ─────────────

@treba_ocr
def test_B1_parafraze_A_ne_maskiraju_B(lanac, monkeypatch):
    k, b = lanac
    model = Model([])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    _prikaci_sken(k, b, pid, DVE_ISTOG_DANA, "sken.pdf")
    assert _rokovi(b, pid) == []                                                # OCR ispod praga: SI ne upisuje
    model.izlaz = [_rok("Rok za zalbu", DA, "Izjavljivanje zalbe protiv resenja"),
                   _rok("Zalbeni rok", DA, "Pravo na zalbu prestaje istekom roka")]
    _osvezi(pid)
    r = _rokovi(b, pid)
    assert len(r) == 2 and len(set(_kljucevi(b, pid))) == 2, [h["dogadjaj"] for h in r]
    assert len([h for h in r if "zalb" in _ime(h)]) == 1 and len([h for h in r if "taks" in _ime(h)]) == 1
    # model se ne može vezati za tačno jednu od dve obaveze → naslov je citat iz izvora, ne parafraza modela
    # (citat je stvaran OCR tekst, sa greškama prepoznavanja — npr. „izjavijivanje“)
    assert all(h["dogadjaj"].startswith("Rok iz dokumenta: Rok ") and "Pravo na zalbu" not in h["dogadjaj"] for h in r)
    assert {h["akter"] for h in r} == {"Genome (AI)"} and {h["izvor"] for h in r} == {"AI_AUTONOMOUS"}
    assert len({h["dokument_id"] for h in r}) == 1 and None not in {h["dokument_id"] for h in r}
    model.izlaz = [_rok("Žalba", DA, "x"), _rok("Žalbeni rok", DA, "y"), _rok("Treća tvrdnja", DA, "z")]
    _osvezi(pid)
    assert len(_rokovi(b, pid)) == 2


@treba_ocr
def test_B2_A_pa_B_u_sledecem_osvezavanju_i_odluke_ostaju(lanac, monkeypatch):
    k, b = lanac
    model = Model([])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    _prikaci_sken(k, b, pid, DVE_ISTOG_DANA, "sken.pdf")
    model.izlaz = [_rok("Rok za zalbu", DA, "Izjavljivanje zalbe")]
    _osvezi(pid)
    model.izlaz = [_rok("Rok za uplatu sudske takse", DA, "Uplata takse")]
    _osvezi(pid)
    r = _rokovi(b, pid)
    assert len(r) == 2 and any("taks" in _ime(h) for h in r) and any("zalb" in _ime(h) for h in r), [h["dogadjaj"] for h in r]
    za = next(h for h in r if "zalb" in _ime(h))
    ta = next(h for h in r if "taks" in _ime(h))
    assert k.post(f"/api/rokovi/{za['id']}/potvrdi", json={}, headers=A).status_code == 200
    assert k.post(f"/api/rokovi/{ta['id']}/odbij", json={"napomena": "nije obaveza klijenta"}, headers=A).status_code == 200
    for izlaz in ([_rok("Žalbeni rok", DA, "a")], [_rok("Taksa", DA, "b")], []):
        model.izlaz = izlaz
        _osvezi(pid)
    assert sorted(h["id"] for h in _rokovi(b, pid)) == sorted([za["id"], ta["id"]])
    assert _stanja(k, pid) == {za["id"]: "CONFIRMED", ta["id"]: "REJECTED"}       # odluke na istim id, nijedna preneta


# ── C: datum koji tekst ne navodi kao rok ──────────────────────────────────────────────────────────────────────

def test_C_nedokazan_datum_jedan_nepotvrden_predlog_ai(lanac, monkeypatch):
    k, b = lanac
    model = Model([])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    _prikaci(k, b, pid, OBICAN, "presuda.pdf")
    assert _rokovi(b, pid) == []                                                # običan datum nije rok
    model.izlaz = [_rok("Rok za izvrsenje", DB, "tvrdnja modela")]
    _osvezi(pid)
    model.izlaz = [_rok("Izvrsenje presude", DB, "druga formulacija")]
    _osvezi(pid)
    [h] = _rokovi(b, pid)                                                       # parafraza ne pravi drugi red
    assert h["akter"] == "Genome (AI)" and h["izvor"] == "AI_AUTONOMOUS" and h["obaveza_kljuc"]
    assert _stanja(k, pid) == {h["id"]: "UNCONFIRMED"}


# ── pad ekstrakcije teksta pri prikačivanju: rok iz entiteta se ne gubi ────────────────────────────────────────

def test_pad_ekstrakcije_teksta_rok_ostaje(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    import uploaded_doc.extractor as ex

    def _pad(*a, **kw):
        raise RuntimeError("OCR nije uspeo (sintetički)")
    pid = _predmet(k)
    r = k.post("/api/smart-intake/documents", files=[("files", ("scan.pdf", _pdf(ZALBA_A), "application/pdf"))], headers=A)
    jid = r.json()["rezultati"][0]["job_id"]
    _do_kraja()
    if k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()["job"]["status"] == "awaiting_review":
        k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", json={}, headers=A)
        _do_kraja()
    monkeypatch.setattr(ex, "extract", _pad)
    k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    [h] = _rokovi(b, pid)
    assert h["datum_iso"] == DA and h["obaveza_kljuc"] and h["akter"] == "Smart Intake"


# ── izvor uklonjen posle potvrde, isti sadržaj ponovo otpremljen ───────────────────────────────────────────────

def test_uklonjen_pa_ponovo_otpremljen_isti_dokument_odluka_ostaje(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    _prikaci(k, b, pid, ZALBA_A, "scan.pdf")
    [h] = _rokovi(b, pid)
    assert k.post(f"/api/rokovi/{h['id']}/potvrdi", json={}, headers=A).status_code == 200
    b.tabele["predmet_dokumenti"] = [d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] != pid]   # brisanje
    _prikaci(k, b, pid, ZALBA_A, "scan-novo-ime.pdf")
    assert [x["id"] for x in _rokovi(b, pid)] == [h["id"]] and _stanja(k, pid) == {h["id"]: "CONFIRMED"}


# ── prekid procesa usred upisa rokova → nastavak prikačivanja upisuje rok tačno jednom ──────────────────────────

class _Ubijen(BaseException):
    """Proces ubijen (OOM, redeploy): ne hvata ga `except Exception`."""


def test_prekid_pri_upisu_roka_nastavak_upisuje_jednom(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    r = k.post("/api/smart-intake/documents", files=[("files", ("dve.pdf", _pdf(["RESENJE"] + DVE_ISTOG_DANA), "application/pdf"))], headers=A)
    jid = r.json()["rezultati"][0]["job_id"]
    _do_kraja()
    if k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()["job"]["status"] == "awaiting_review":
        k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", json={}, headers=A)
        _do_kraja()
    orig = _h._Upit.execute
    stanje = {"upisa": 0}

    def execute(self):
        if self.t == "predmet_hronologija" and self.radnja[0] == "insert":
            stanje["upisa"] += 1
            if stanje["upisa"] == 2:                       # prvi rok upisan, proces ubijen pre drugog
                raise _Ubijen()
        return orig(self)
    monkeypatch.setattr(_h._Upit, "execute", execute)
    try:
        prvi = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
        assert prvi.status_code >= 500, prvi.text                           # klijent bez podizanja izuzetka servera
    except _Ubijen:
        pass
    monkeypatch.setattr(_h._Upit, "execute", orig)
    assert stanje["upisa"] == 2
    assert len(_rokovi(b, pid)) == 1
    posao = next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)
    posao["finalizing_at"] = (datetime.now(timezone.utc) - timedelta(seconds=121)).isoformat()
    f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    assert f.status_code == 200, f.text
    _do_kraja_dogadjaja(b)
    r = _rokovi(b, pid)
    assert len(r) == 2 and len(set(_kljucevi(b, pid))) == 2, r                 # druga obaveza više ne nestaje
    assert len([d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid]) == 1


# ── zatečeni redovi (pre 144, bez ključa) ─────────────────────────────────────────────────────────────────────

def _zatecen(b, pid, datum, **polja):
    b.tabele["predmet_hronologija"].append({"id": f"zatecen-{len(b.tabele['predmet_hronologija'])}", "predmet_id": pid,
                                            "user_id": "uid-A", "datum_iso": datum, "datum": datum, "vrsta": "rok",
                                            "izvor": "AI_AUTONOMOUS", **polja})


def test_zatecen_red_jedne_obaveze_pokriva_bez_novog_kandidata(lanac, monkeypatch):
    k, b = lanac
    model = Model([])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    _zatecen(b, pid, DA, dogadjaj="Rok iz dokumenta (sudska odluka)", akter="Smart Intake", dokument_naziv="scan.pdf")
    _prikaci(k, b, pid, ZALBA_A, "scan.pdf")                                     # isti dokument, ime jednoznačno
    assert len(_rokovi(b, pid)) == 1
    did = next(d["id"] for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid)
    model.izlaz = [_rok("Žalbeni rok", DA, "x")]
    _osvezi(pid)
    assert len(_rokovi(b, pid)) == 1 and did


def test_zatecen_red_ne_pokriva_drugi_dokument_istog_imena(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    pid = _predmet(k)
    _prikaci(k, b, pid, ZALBA_A, "scan.pdf")
    for h in _rokovi(b, pid):                                                    # kao da je upisan pre 144
        h["obaveza_kljuc"] = None
    _prikaci(k, b, pid, TAKSA_B, "scan.pdf")
    assert len(_rokovi(b, pid)) == 2


@treba_ocr
def test_zatecen_red_kod_dve_obaveze_istog_dana_ne_maskira_drugu(lanac, monkeypatch):
    k, b = lanac
    model = Model([])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    _prikaci_sken(k, b, pid, DVE_ISTOG_DANA, "sken.pdf")
    did = next(d["id"] for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid)
    _zatecen(b, pid, DA, dogadjaj="Rok za zalbu: stari predlog", akter="Genome (AI)", dokument_id=did, dokument_naziv="sken.pdf")
    model.izlaz = [_rok("Rok za zalbu", DA, "x")]
    _osvezi(pid)
    r = _rokovi(b, pid)
    # zatečen red ne zna koju od dve obaveze predstavlja → obe dokazane obaveze dobijaju kandidat (moguć duplikat
    # zatečenog reda, nikad gubitak); zatečen red se ne menja
    assert any("taks" in _ime(h) for h in r) and next(h for h in r if h["id"].startswith("zatecen")).get("obaveza_kljuc") is None
    assert len(r) == 3


# ── kod pre migracije 144: bez identiteta, ali bez potiskivanja ────────────────────────────────────────────────

def test_bez_migracije_144_nema_potiskivanja(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([]))
    orig = _h._Upit.execute

    def execute(self):
        if self.t == "predmet_hronologija" and "obaveza_kljuc" in str(self.kol) + str(self.radnja[1]):
            raise Exception('{"code": "42703", "message": "column predmet_hronologija.obaveza_kljuc does not exist"}')
        return orig(self)
    monkeypatch.setattr(_h._Upit, "execute", execute)
    pid = _predmet(k)
    _prikaci(k, b, pid, ZALBA_A, "scan.pdf")
    _prikaci(k, b, pid, TAKSA_B, "scan.pdf")
    r = _rokovi(b, pid)
    assert len(r) == 2 and all(not h.get("obaveza_kljuc") for h in r), r

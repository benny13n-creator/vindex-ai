# -*- coding: utf-8 -*-
"""N6 — izveštaji (Bojan: „da može da izvuče izveštaje“): postojeći izveštaji moraju TAČNO da predstavljaju podatke.
  * PDF predmeta: srpska slova (Helvetica ih je gubila), ročišta sa stanjem, oznaka odluke SAMO na rokovima;
  * mesečni izveštaj: „fakturisano“ = izdato (ne nacrt/stornirano), ročišta bez otkazanih/odloženih, „narednih 14 dana“
    su rokovi sa stanjem odluke (AI predlog nije obaveza), prekoračeni broje i potvrđen „važan“ rok;
  * CSV evidencije naplate nosi status fakture. Stvarne rute nad bazom u memoriji (tests/ns005_harness)."""
import csv
import io
from datetime import date, timedelta

import pytest

from tests.ns005_harness import pripremi, ocisti, zaglavlje

PA, PB = "pred-A-1", "pred-B-1"
DANAS = date.today()


def _d(n):
    return (DANAS + timedelta(days=n)).isoformat()


def _baza():
    rok = lambda rid, n, dog, vrsta="rok", vaz="važan", izvor="AI_AUTONOMOUS": {"id": rid, "user_id": "uid-A", "predmet_id": PA, "dogadjaj": dog,
        "datum": _d(n), "datum_iso": _d(n), "vaznost": vaz, "akter": "Sistem", "izvor": izvor, "vrsta": vrsta}
    prvi = DANAS.replace(day=1)
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Zlatić protiv Đorđević", "status": "aktivan", "tip": "parnica", "opis": "Naknada štete"},
                     {"id": PB, "user_id": "uid-B", "naziv": "TAJNI B", "status": "aktivan"}],
        "predmet_dokumenti": [], "predmet_beleske": [],
        "predmet_hronologija": [rok("h-dog", -3, "Podneta tužba", vrsta="dogadjaj", vaz="informativan"),
                                rok("h-dog2", 4, "Sastanak sa klijentom", vrsta="dogadjaj", vaz="informativan"),
                                rok("h-ai", 5, "Rok za odgovor (AI)"), rok("h-pot", 6, "Rok za žalbu (potvrđen)"),
                                rok("h-odb", 7, "Rok odbijen"), rok("h-prosao", -2, "Prošao potvrđen rok"),
                                {"id": "h-b", "user_id": "uid-B", "predmet_id": PB, "dogadjaj": "TAJNI rok B", "datum_iso": _d(5), "vaznost": "važan", "vrsta": "rok"}],
        "rocista": [{"id": f"r-{s}", "user_id": "uid-A", "predmet_id": PA, "sud": f"Sud {s}", "sudnica": "14", "datum": prvi.isoformat(),
                     "vreme": "10:00:00", "status": s} for s in ("zakazano", "odrzano", "odlozeno", "otkazano")]
                   + [{"id": "r-b", "user_id": "uid-B", "predmet_id": PB, "sud": "TAJNI sud", "datum": prvi.isoformat(), "status": "zakazano"}],
        "fakture": [{"id": f"f-{s}", "user_id": "uid-A", "predmet_id": PA, "broj_fakture": f"2026/{s}", "status": s, "iznos_sa_pdv": 1000.0,
                     "datum_fakture": prvi.isoformat(), "klijent_naziv": "K"} for s in ("nacrt", "izdata", "placena", "stornirana")],
        "billing_entries": [{"id": "e-1", "user_id": "uid-A", "predmet_id": PA, "opis": "Rad", "iznos_rsd": 1000.0, "obracunato": True,
                             "faktura_id": "f-placena", "datum": prvi.isoformat()}],
        "audit_immutable": [{"action": "rok_potvrdjen", "resource_type": "rok", "resource_id": "h-pot", "seq": 1},
                            {"action": "rok_odbijen", "resource_type": "rok", "resource_id": "h-odb", "seq": 2},
                            {"action": "rok_potvrdjen", "resource_type": "rok", "resource_id": "h-prosao", "seq": 3}],
    }


@pytest.fixture
def ok(monkeypatch):
    k, b = pripremi(monkeypatch, _baza())
    import shared.rokovi as RD
    monkeypatch.setattr(RD, "_sema_ima_129", lambda supa=None: True)
    yield k, b
    ocisti()


def _pdf_tekst(sadrzaj: bytes) -> str:
    import pymupdf
    return "\n".join(s.get_text() for s in pymupdf.open(stream=sadrzaj, filetype="pdf"))


def test_pdf_srpska_slova_rocista_i_oznake_samo_na_rokovima(ok):
    k, b = ok
    r = k.get(f"/api/predmeti/{PA}/pdf-export", headers=zaglavlje("A"))
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    t = _pdf_tekst(r.content)
    assert "Zlatić protiv Đorđević" in t and "Događaj" in t                      # Helvetica: „ZlatiI protiv IorIeviI“
    for st in ("zakazano", "održano", "odloženo", "otkazano"):
        assert st in t, st
    assert "[NEPOTVRĐENO] Rok za odgovor (AI)" in t and "[ODBIJENO] Rok odbijen" in t
    assert "[NEPOTVRĐENO] Podneta tužba" not in t and "Podneta tužba" in t      # događaj nije odluka
    assert "[NEPOTVRĐENO] Rok za žalbu" not in t and "Rok za žalbu (potvrđen)" in t
    assert "TAJNI" not in t
    assert k.get(f"/api/predmeti/{PA}/pdf-export", headers=zaglavlje("B")).status_code == 404


def test_pdf_tekst_sa_znakom_manje_ne_obara_izvestaj(ok):
    k, b = ok
    b.tabele["predmet_beleske"].append({"id": "bel", "user_id": "uid-A", "predmet_id": PA, "sadrzaj": "klauzula <tačka 3> i <font name=Bad>x</font>", "created_at": "2026-10-01"})
    r = k.get(f"/api/predmeti/{PA}/pdf-export", headers=zaglavlje("A"))
    assert r.status_code == 200 and "klauzula <tačka 3> i <font name=Bad>x</font>" in _pdf_tekst(r.content)


def test_mesecni_izvestaj_tacnost(ok):
    k, b = ok
    r = k.get("/billing/report/mesecni", params={"mesec": DANAS.strftime("%Y-%m")}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["fakturisano_rsd"] == 2000.0 and d["naplaceno_rsd"] == 1000.0 and d["neplaceno_rsd"] == 1000.0, d   # izdata + plaćena
    assert d["rocista_mesec"] == 2 and {x["status"] for x in d["rocista"]} == {"zakazano", "odrzano"}
    sled = {x["id"]: x["stanje_odluke"] for x in d["sledecih_14_dana"]}
    assert sled == {"h-ai": "UNCONFIRMED", "h-pot": "CONFIRMED"}, sled                  # bez događaja, bez odbijenog, bez B
    # Postojeće pravilo (shared/rokovi.je_hitan_za_prikaz): prekoračen = samo `kritičan`; potvrđen „važan“ rok koji je prošao
    # se NE broji — da li treba, odluka je osnivača (N6), ne menja se ovde.
    assert d["prekoraceni_rokovi"] == 0


def test_csv_evidencija_nosi_status_fakture(ok):
    k, b = ok
    r = k.get("/billing/report/csv", params={"od": DANAS.replace(day=1).isoformat()}, headers=zaglavlje("A"))
    assert r.status_code == 200
    redovi = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    assert redovi[0][-2:] == ["Broj fakture", "Status fakture"] and redovi[0][:10][-1] == "Faktura ID"
    assert redovi[1][-2:] == ["2026/placena", "plaćena"]


def test_pdf_cirilica_ostaje_ili_je_preslovljena_uz_napomenu(ok, monkeypatch):
    """Nalaz pregleda N6: Vera nema ćirilicu, pa je „Ђорђевић“ tiho nestajao. Sa DejaVu/Arial ostaje ćirilica;
    bez takvog fonta tekst se preslovljava na latinicu i PDF to kaže."""
    import predmet_pdf as PP
    k, b = ok
    b.tabele["predmeti"][0]["naziv"] = "Петровић против Ђорђевића"
    b.tabele["predmeti"][0]["tip"] = "parnični <i>"                    # neispravan tag u slobodnom polju
    t = _pdf_tekst(k.get(f"/api/predmeti/{PA}/pdf-export", headers=zaglavlje("A")).content)
    if PP._CIRILICA:
        assert "Петровић против Ђорђевића" in t
    monkeypatch.setattr(PP, "_CIRILICA", False)
    r = k.get(f"/api/predmeti/{PA}/pdf-export", headers=zaglavlje("A"))
    assert r.status_code == 200
    t2 = _pdf_tekst(r.content)
    assert "Petrović protiv Đorđevića" in t2 and "preslovljen na latinicu" in t2 and "PARNIČNI <I>" in t2


def test_izvrsen_rok_nije_u_narednih_14_dana(ok):
    k, b = ok
    next(h for h in b.tabele["predmet_hronologija"] if h["id"] == "h-ai")["stanje"] = "izvrsen"
    d = k.get("/billing/report/mesecni", params={"mesec": DANAS.strftime("%Y-%m")}, headers=zaglavlje("A")).json()
    assert "h-ai" not in {x["id"] for x in d["sledecih_14_dana"]}

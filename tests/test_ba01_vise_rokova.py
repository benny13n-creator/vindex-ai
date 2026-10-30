# -*- coding: utf-8 -*-
"""Operation Bojan BA-01 — više nezavisnih rokova iz jednog dokumenta (Task 6, BA-05/BA-06).

`extract_deadline` bira jedan rok; drugi dokazani rok istog dokumenta se bez Genome-a gubio. Sada Smart Intake predlaže
svaku dokazanu obavezu (datum + dokazna fraza iz izvora) kao zaseban, NEPOTVRĐEN kandidat. Običan datum nikad.
Datumi su relativni prema `_danas_beograd()` (sintetički, označeni). Genome je zamenjen praznim ili skriptovanim izlazom.
"""
import asyncio
import re
from datetime import timedelta

import pytest

import routers.case_dna as cd
import shared.intake_extract as ex
from routers.email_notif import _danas_beograd
from tests.test_ba01_rok_identitet import Model, _osvezi, _po_datumu, _predmet, _prikaci, _rok, _rokovi, _stanja
from tests.test_n1_zlatni_prijem import _OCR, _sken_pdf
from tests.test_n7_azuriranje_predmeta import _sr, lanac  # noqa: F401 — fixture
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401 — fixture

treba_ocr = pytest.mark.skipif(_OCR is None, reason="Tesseract nije dostupan — sken traži stvaran OCR")
DANAS = _danas_beograd()
A_ROK, B_ROK, C_OBICAN = DANAS + timedelta(days=6), DANAS + timedelta(days=21), DANAS - timedelta(days=8)
ZAGLAVLJE = ["OSNOVNI SUD U BEOGRADU", "Posl. br. P 7714/2026 (SINTETICKI)", "Tuzilac: Petar Goldenovic iz Beograda",
             "Tuzeni: Golden Gradnja DOO Beograd", "PRESUDA", f"Presuda je doneta {_sr(C_OBICAN)} godine."]
DVA_ROKA = ZAGLAVLJE + ["Obavezuje se tuzeni da tuziocu isplati 350.000,00 dinara.",
                        f"Rok za izjavljivanje zalbe istice {_sr(A_ROK)} godine.",
                        f"Rok za dobrovoljno ispunjenje istice {_sr(B_ROK)} godine.",
                        f"U Beogradu, dana {_sr(C_OBICAN + timedelta(days=1))}"]
ISTI_DAN = ZAGLAVLJE + [f"Rok za izjavljivanje zalbe istice {_sr(A_ROK)} godine.",
                        f"Rok za uplatu sudske takse istice {_sr(A_ROK)} godine."]
PONOVLJENO = ZAGLAVLJE + [f"Rok za izjavljivanje zalbe istice {_sr(A_ROK)} godine.", "Obrazlozenje presude.",
                          f"POUKA O PRAVNOM LEKU: Rok za izjavljivanje zalbe istice {_sr(A_ROK)} godine."]


def _rokovi_entiteti(tekst):
    async def _bez_llm(_t):
        return {}
    stari = ex.extract_free_text_entities
    ex.extract_free_text_entities = _bez_llm
    try:
        return [e for e in asyncio.run(ex.extract_all_entities(tekst)) if e["entity_type"] == "deadline"]
    finally:
        ex.extract_free_text_entities = stari


def _iso(d):
    return d.isoformat()


# ── ekstrakcija ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_entiteti_dva_roka_bez_obicnog_datuma():
    e = _rokovi_entiteti("\n".join(DVA_ROKA))
    assert [x["value"] for x in e] == [_sr(A_ROK)[:-1], _sr(B_ROK)[:-1]] and all(x["confidence"] >= 0.9 for x in e), e


def test_entiteti_isti_dan_dve_obaveze_i_ista_obaveza_dvaput():
    assert [x["value"] for x in _rokovi_entiteti("\n".join(ISTI_DAN))] == [_sr(A_ROK)[:-1]] * 2
    assert [x["value"] for x in _rokovi_entiteti("\n".join(PONOVLJENO))] == [_sr(A_ROK)[:-1]]


def test_kratak_dokument_bez_zaglavlja_dve_obaveze_istog_dana():
    """Task 1: dedup parsera po isečku konteksta (`vrednost + kontekst[:50]`) u kratkom tekstu je drugi rok istog
    datuma tiho brisao — oba isečka počinju od 0."""
    tekst = f"Rok za zalbu istice {_sr(A_ROK)} godine.\nRok za uplatu takse istice {_sr(A_ROK)} godine."
    assert [x["value"] for x in _rokovi_entiteti(tekst)] == [_sr(A_ROK)[:-1]] * 2


@pytest.mark.parametrize("tekst", [
    "Protiv ove presude dozvoljena je zalba u roku od 15 dana od dana prijema.",   # relativan, bez početka
    "Rok za zalbu istice O5.11.2O26. godine.",                                      # OCR: slovo O umesto nule
    "Presuda je doneta 20.10.2026.\nU Beogradu, dana 21.10.2026.",                  # samo obični datumi
])
def test_bez_izmisljenog_konkretnog_roka(tekst):
    e = _rokovi_entiteti(tekst)
    assert len(e) == 1 and not (e[0]["value"] and re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", e[0]["value"])), e


def test_jedan_rok_isti_kao_ranije():
    tekst = f"Rok za zalbu istice {_sr(A_ROK)} godine."
    assert [(x["value"], x["confidence"]) for x in _rokovi_entiteti(tekst)] == [ex.extract_deadline(tekst)]


# ── tok: kandidati, potvrda, odbijanje, ponovna obrada ───────────────────────────────────────────────────────────

def test_dva_kandidata_potvrda_a_odbijanje_b(lanac, monkeypatch):
    k, b = lanac
    model = Model([])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    _prikaci(k, b, pid, DVA_ROKA, "01 Presuda digitalna.pdf")
    r = sorted(_rokovi(b, pid), key=lambda h: h["datum_iso"])
    assert [(h["datum_iso"], h["dokument_naziv"], h["akter"]) for h in r] == [
        (_iso(A_ROK), "01 Presuda digitalna.pdf", "Smart Intake"), (_iso(B_ROK), "01 Presuda digitalna.pdf", "Smart Intake")], r
    st = _stanja(k, pid)
    assert st == {r[0]["id"]: "UNCONFIRMED", r[1]["id"]: "UNCONFIRMED"}
    assert k.post(f"/api/rokovi/{r[0]['id']}/potvrdi", json={}, headers=A).status_code == 200
    assert _stanja(k, pid) == {r[0]["id"]: "CONFIRMED", r[1]["id"]: "UNCONFIRMED"}
    assert k.post(f"/api/rokovi/{r[1]['id']}/odbij", json={}, headers=A).status_code == 200
    # Genome sada vidi obe obaveze (preformulisano) + ista obrada dokumenta ponovo
    model.izlaz = [_rok("Žalbeni rok", _iso(A_ROK), "x"), _rok("Ispunjenje", _iso(B_ROK), "y")]
    _osvezi(pid)
    _prikaci(k, b, pid, DVA_ROKA, "01 Presuda digitalna.pdf")
    assert _stanja(k, pid) == {r[0]["id"]: "CONFIRMED", r[1]["id"]: "REJECTED"}
    assert _po_datumu(b, pid) == {_iso(A_ROK): 1, _iso(B_ROK): 1}
    assert k.get(f"/api/rokovi/kandidati?predmet_id={pid}", headers=B).json()["rokovi"] == []


def test_isti_dan_dve_obaveze_dva_kandidata_razlicite_oznake(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([_rok("Žalba", _iso(A_ROK), "x"), _rok("Taksa", _iso(A_ROK), "y")]))
    pid = _predmet(k)
    _prikaci(k, b, pid, ISTI_DAN, "02 Resenje.pdf")
    r = _rokovi(b, pid)
    assert len(r) == 2 and len({h["dogadjaj"] for h in r}) == 2 and {h["akter"] for h in r} == {"Smart Intake"}, r
    potvrdjen = r[0]["id"]
    assert k.post(f"/api/rokovi/{potvrdjen}/potvrdi", json={}, headers=A).status_code == 200
    st = _stanja(k, pid)
    assert st[potvrdjen] == "CONFIRMED" and st[r[1]["id"]] == "UNCONFIRMED"     # druga obaveza ne nasleđuje odluku


def test_ista_obaveza_dvaput_u_dokumentu_jedan_kandidat(lanac, monkeypatch):
    k, b = lanac
    monkeypatch.setattr(cd, "_pozovi_genome_api", Model([_rok("Žalba", _iso(A_ROK), "x")]))
    pid = _predmet(k)
    _prikaci(k, b, pid, PONOVLJENO, "03 Presuda sa poukom.pdf")
    assert _po_datumu(b, pid) == {_iso(A_ROK): 1}


@treba_ocr
def test_sken_stvaran_ocr_rokovi_ostaju_nesigurni_a_genome_ogranicen_ocr_tekstom(lanac, monkeypatch):
    """OCR rok je ispod praga (OCR_PLAFON) i bez ispravke advokata NE postaje Smart Intake kandidat — nesigurno ostaje
    nesigurno (BA-03). Genome kandidat iz istog skena je ograničen brojem obaveza koje OCR tekst stvarno dokazuje."""
    k, b = lanac
    model = Model([])
    monkeypatch.setattr(cd, "_pozovi_genome_api", model)
    pid = _predmet(k)
    jid = _prikaci_sken(k, b, pid, DVA_ROKA[-3:-1], "04 Presuda skenirana.pdf")
    dok = next(d for d in b.tabele["intake_documents"] if d["intake_job_id"] == jid)
    ent = [e for e in b.tabele["extracted_entities"] if e["document_id"] == dok["id"] and e["entity_type"] == "deadline"]
    assert dok["ocr_used"] is True
    assert sorted(e["value"] for e in ent) == sorted([_sr(A_ROK)[:-1], _sr(B_ROK)[:-1]]) and all(e["confidence"] < 0.9 for e in ent), ent
    assert _rokovi(b, pid) == []
    model.izlaz = [_rok("Žalba", _iso(A_ROK), "x", "DOK-01"), _rok("Ispunjenje", _iso(B_ROK), "y", "DOK-01"),
                   _rok("Izmišljen", _iso(B_ROK), "z", "DOK-01")]
    _osvezi(pid)
    assert _po_datumu(b, pid) == {_iso(A_ROK): 1, _iso(B_ROK): 1}


def _prikaci_sken(k, b, pid, redovi, ime):
    from tests.test_n1_zlatni_prijem import _do_kraja
    from tests.test_osb002_solo_tok import _do_kraja_dogadjaja
    r = k.post("/api/smart-intake/documents", files=[("files", (ime, _sken_pdf(redovi), "application/pdf"))], headers=A)
    jid = r.json()["rezultati"][0]["job_id"]
    _do_kraja()
    # OCR entiteti su ispod praga (OCR_PLAFON) → pregled; advokat ga razrešava (postojeći tok, ne zaobilazi se)
    assert k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()["job"]["status"] == "awaiting_review"
    assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", json={}, headers=A).status_code == 200
    _do_kraja()
    assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A).status_code == 200
    _do_kraja_dogadjaja(b)
    return jid

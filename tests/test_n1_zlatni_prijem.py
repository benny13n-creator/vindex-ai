# -*- coding: utf-8 -*-
"""N1 GOLDEN INTAKE CASE (backend) — jedan advokat, jedan klijent, opis spora, četiri dokumenta, JEDAN predmet.

Kroz STVARNE rute (klijent → provera sukoba → POST /api/intake/kreiraj → Smart Intake otpremanje → STVARAN intake worker
i ekstraktor → ispravka → pregled → prikačivanje), nad bazom u memoriji koja upisuje (tests/test_osb002_solo_tok.py).
Simulirani su samo modeli (klasifikacija kad heuristika ne odluči, stranke iz slobodnog teksta) i embedding/Pinecone.

OCR NIJE simuliran. Sa Tesseract-om (CI: produkciona Docker slika i production-runtime posao, VINDEX_REQUIRE_OCR=1)
skenirani PDF i fotografija moraju biti STVARNO pročitani i prikačeni (4/4). Bez Tesseract-a (lokalni Windows) isti
dokumenti moraju vidljivo ostati neprikačeni (`prazan_tekst`), bez izmišljenog teksta i bez `ocr_used=True` (2/4).
Browser strana istog toka: frontend-v2-ng/tests/live-zlatni-prijem-e2e.mjs.
"""
import io
import os

import pytest

from tests.test_osb002_solo_tok import A, B, _radnik, solo  # noqa: F401 — `solo` je fixture

try:
    import pytesseract
    _OCR = str(pytesseract.get_tesseract_version())
except Exception as _e:   # noqa: BLE001
    _OCR = None
    if os.getenv("VINDEX_REQUIRE_OCR") == "1":
        raise RuntimeError(f"VINDEX_REQUIRE_OCR=1, ali Tesseract nije dostupan ({type(_e).__name__})")

MARKER = "ZLATNI-7731"
OPIS = ("Klijentkinja Milica Zlatic dobila je resenje o otkazu od Zlatna Linija DOO. Cilj: ponistaj resenja o otkazu, "
        "vracanje na rad i isplata zarade. Oznaka " + MARKER + ".")
SKEN = ["RESENJE O OTKAZU UGOVORA O RADU", "Zaposlena: Milica Zlatic iz Beograda", "Poslodavac: Zlatna Linija DOO Beograd",
        "Resenje je uruceno zaposlenoj 03.02.2026. godine."]
FOTO = ["DOSTAVNICA", "Primalac: Milica Zlatic iz Beograda", "Posiljalac: Zlatna Linija DOO Beograd",
        "Uruceno dana 05.02.2026. godine."]


def _pdf(redovi):
    from reportlab.pdfgen import canvas
    b = io.BytesIO()
    c = canvas.Canvas(b)
    for i, r in enumerate(redovi):
        c.drawString(60, 780 - i * 24, r)
    c.showPage()
    c.save()
    return b.getvalue()


def _raster_png(redovi):
    """Strana kao slika (fotografija/sken): tekst postoji SAMO kao pikseli."""
    import fitz
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    tw = fitz.TextWriter(s.rect)
    for i, r in enumerate(redovi):
        tw.append((50, 80 + i * 34), r, font=fitz.Font("helv"), fontsize=20)
    tw.write_text(s)
    png = s.get_pixmap(dpi=200).tobytes("png")
    doc.close()
    return png


def _sken_pdf(redovi):
    import fitz
    sken = fitz.open()
    s = sken.new_page(width=595, height=842)
    s.insert_image(s.rect, stream=_raster_png(redovi))
    b = io.BytesIO()
    sken.save(b)
    sken.close()
    return b.getvalue()


def _docx(redovi):
    import docx
    d = docx.Document()
    for r in redovi:
        d.add_paragraph(r)
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


DOKUMENTI = {
    "01 Tuzba digitalna.pdf": (lambda: _pdf(["OSNOVNI SUD U BEOGRADU", "Broj predmeta: P 5521/2026", "Tuzilac: Milica Zlatic iz Beograda",
                                             "Tuzeni: Zlatna Linija DOO Beograd",
                                             "Tuzba radi ponistaja resenja o otkazu i isplate zarade od 210.000,00 dinara."]), "application/pdf"),
    "02 Resenje skenirano.pdf": (lambda: _sken_pdf(SKEN), "application/pdf"),
    "03 Dostavnica fotografija.png": (lambda: _raster_png(FOTO), "image/png"),
    "04 Ugovor o radu.docx": (lambda: _docx(["UGOVOR O RADU", "Poslodavac: Zlatna Linija DOO Beograd", "Zaposlena: Milica Zlatic",
                                             "Zarada: 70.000,00 dinara mesecno."]),
                              "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
}
SLIKOVNI = ("02 Resenje skenirano.pdf", "03 Dostavnica fotografija.png")
_BAJTOVI: dict = {}


def _sadrzaj(ime):
    """Isti bajtovi pri svakom pozivu (reportlab u PDF upisuje vreme — ponovljeno otpremanje mora biti ISTI sadržaj)."""
    if ime not in _BAJTOVI:
        _BAJTOVI[ime] = DOKUMENTI[ime][0]()
    return _BAJTOVI[ime]


def _do_kraja():
    for _ in range(10):
        if not _radnik():
            return


def _zlatni_tok(k, b):
    r = k.post("/klijenti", json={"tip": "fizicko_lice", "ime": "Milica", "prezime": "Zlatic"}, headers=A)
    assert r.status_code == 200, r.text
    kid = r.json()["klijent"]["id"]
    coi = k.post("/api/conflict-check", json={"ime_prezime": "Milica Zlatic"}, headers=A)
    assert coi.status_code == 200 and isinstance(coi.json().get("status"), str), coi.text
    r = k.post("/api/intake/kreiraj", json={"klijent_id": kid, "naziv": "Zlatic protiv Zlatna Linija — otkaz", "opis": OPIS}, headers=A)
    assert r.status_code == 200 and r.json()["klijent_povezan"] is True, r.text
    pid = r.json()["predmet_id"]

    fajlovi = [("files", (ime, _sadrzaj(ime), tip)) for ime, (_fn, tip) in DOKUMENTI.items()]
    r = k.post("/api/smart-intake/documents", files=fajlovi, headers=A)
    assert r.status_code == 202, r.text
    poslovi = {x["filename"]: x["job_id"] for x in r.json()["rezultati"] if x["ok"]}
    assert set(poslovi) == set(DOKUMENTI), r.json()
    _do_kraja()

    ispravka, finalizacije = None, {}
    for ime, jid in poslovi.items():
        g = k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()
        if ime.startswith("01") and ispravka is None:
            ent = next(e for e in g["entiteti"] if e["entity_type"] == "defendant")
            ispravka = {"entity_id": ent["entity_id"], "original": ent["value"], "posao": jid,
                        "vrednost": "Zlatna Linija DOO Beograd (ispravljeno)"}
            rr = k.post(f"/api/smart-intake/entities/{ent['entity_id']}/correct", json={"corrected_value": ispravka["vrednost"]}, headers=A)
            assert rr.status_code == 200, rr.text
        if g["job"]["status"] == "awaiting_review":
            assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", json={}, headers=A).status_code == 200
            _do_kraja()
        f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
        assert f.status_code == 200, (ime, f.text)
        finalizacije[ime] = f.json()
    return kid, pid, poslovi, ispravka, finalizacije


def test_zlatni_prijem_jedan_predmet_klijent_opis_dokumenti(solo):
    k, b = solo
    kid, pid, poslovi, ispravka, fin = _zlatni_tok(k, b)
    t = b.tabele

    predmeti_a = [p for p in t["predmeti"] if p["user_id"] == "uid-A"]
    assert [p["id"] for p in predmeti_a] == [pid], "tačno jedan predmet"
    assert MARKER in predmeti_a[0]["opis"] and "Cilj:" in predmeti_a[0]["opis"], "opis spora i cilj sačuvani"
    assert [(v["predmet_id"], v["klijent_id"]) for v in t["predmet_klijenti"]] == [(pid, kid)], "klijent povezan sa predmetom"

    dok = [d for d in t["predmet_dokumenti"] if d["predmet_id"] == pid]
    po_poslu = {d["source_intake_job_id"]: d for d in dok}
    assert all(d["user_id"] == "uid-A" for d in dok) and len(po_poslu) == len(dok), "poreklo: jedan dokument po poslu, vlasnik A"
    for ime in ("01 Tuzba digitalna.pdf", "04 Ugovor o radu.docx"):
        assert fin[ime]["ok"] is True and (po_poslu[poslovi[ime]].get("tekst_sadrzaj") or "").strip(), ime
    ocr_doc = {d["intake_job_id"]: d for d in t["intake_documents"]}
    if _OCR:
        assert len(dok) == 4, [d["naziv_fajla"] for d in dok]
        assert "OTKAZU" in po_poslu[poslovi[SLIKOVNI[0]]]["tekst_sadrzaj"].upper()
        assert "DOSTAVNICA" in po_poslu[poslovi[SLIKOVNI[1]]]["tekst_sadrzaj"].upper()
        assert all(ocr_doc[poslovi[ime]]["ocr_used"] is True for ime in SLIKOVNI), "stvaran OCR je pročitao sken i fotografiju"
    else:
        assert len(dok) == 2, [d["naziv_fajla"] for d in dok]
        for ime in SLIKOVNI:
            assert fin[ime]["ok"] is False and [x["razlog"] for x in fin[ime]["dokumenti"]] == ["prazan_tekst"], fin[ime]
            assert poslovi[ime] not in po_poslu, "nepročitan dokument nije prikačen sa izmišljenim tekstom"
            assert ocr_doc[poslovi[ime]]["ocr_used"] is False, "bez OCR-a nema ocr_used=True"

    ent = next(e for e in t["extracted_entities"] if e["id"] == ispravka["entity_id"])
    doc_posla = {d["id"]: d["intake_job_id"] for d in t["intake_documents"]}
    assert ent["corrected_value"] == ispravka["vrednost"] and ent["value"] == ispravka["original"], "original se ne briše"
    assert doc_posla[ent["document_id"]] == ispravka["posao"] == poslovi["01 Tuzba digitalna.pdf"], "ispravka pripada tačnom dokumentu"
    assert not [h for h in t["predmet_hronologija"] if str(h.get("stanje") or "").upper() in ("CONFIRMED", "POTVRDJEN")], \
        "nijedan rok nije potvrđen bez advokata"

    # ponovljeno otpremanje i prikačivanje istog sadržaja: isti posao, bez novog dokumenta i bez novog predmeta
    pre = (len(t["intake_jobs"]), len(t["predmet_dokumenti"]))
    ime, (fn, tip) = next(iter(DOKUMENTI.items()))
    r = k.post("/api/smart-intake/documents", files=[("files", (ime, _sadrzaj(ime), tip))], headers=A).json()["rezultati"][0]
    assert r["already_submitted"] is True and r["job_id"] == poslovi[ime]
    f = k.post(f"/api/smart-intake/jobs/{poslovi[ime]}/finalize", json={"predmet_id": pid}, headers=A)
    assert f.status_code == 200 and f.json()["predmet_id"] == pid
    assert (len(t["intake_jobs"]), len(t["predmet_dokumenti"])) == pre
    assert [p["id"] for p in t["predmeti"] if p["user_id"] == "uid-A"] == [pid]

    # korisnik B: ništa od A nije dostupno ni promenljivo
    jid = poslovi["01 Tuzba digitalna.pdf"]
    assert k.get(f"/api/predmeti/{pid}", headers=B).status_code == 404
    assert k.get(f"/api/smart-intake/jobs/{jid}", headers=B).status_code == 404
    assert k.post(f"/api/smart-intake/entities/{ispravka['entity_id']}/correct", json={"corrected_value": "B"}, headers=B).status_code == 404
    assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=B).status_code == 404
    assert k.post("/api/intake/kreiraj", json={"klijent_id": kid, "naziv": "B uzima klijenta A"}, headers=B).status_code == 404
    assert ent["corrected_value"] == ispravka["vrednost"]
    assert not [p for p in t["predmeti"] if p["user_id"] == "uid-B"] and len(t["predmet_klijenti"]) == 1


@pytest.mark.parametrize("ime,sadrzaj,poruka", [
    ("ugovor.docx", b"Ovo nije DOCX nego obican tekst.", "nije Word (DOCX)"),
    ("tuzba.pdf", b"Ovo nije PDF nego obican tekst.", "nije PDF"),
    ("presuda.pdf", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "nije PDF"),
])
def test_sadrzaj_mora_odgovarati_ekstenziji_pri_otpremanju(solo, ime, sadrzaj, poruka):
    k, b = solo
    r = k.post("/api/smart-intake/documents", files=[("files", (ime, sadrzaj, "application/octet-stream"))], headers=A)
    assert r.status_code == 202
    x = r.json()["rezultati"][0]
    assert x["ok"] is False and poruka in x["greska"] and "job_id" not in x
    assert b.tabele["intake_jobs"] == [], "ništa nije sačuvano ni zakazano"


def test_ispravan_pdf_i_docx_i_dalje_prolaze_i_pdf_sa_uvodnim_bajtovima(solo):
    k, b = solo
    pdf = _pdf(["UGOVOR", "Strana: Test"])
    fajlovi = [("files", ("a.pdf", pdf, "application/pdf")), ("files", ("b.pdf", b"\r\n" + pdf, "application/pdf")),
               ("files", ("c.docx", _docx(["UGOVOR"]), "application/octet-stream"))]
    r = k.post("/api/smart-intake/documents", files=fajlovi, headers=A).json()["rezultati"]
    assert [x["ok"] for x in r] == [True, True, True], r


def test_neprocitan_sken_nije_prijavljen_kao_procitan_ocr_om(solo, monkeypatch):
    """Važi i uz Tesseract: OCR koji ne pročita ništa (simuliran SAMO ovde, na granici `_ocr_image`) ne sme dati
    `ocr_koriscen=True` — V2 bi posle pregleda prikazao „tekst pročitan OCR-om“ za dokument koji nije pročitan."""
    import uploaded_doc.extractor as ex
    monkeypatch.setattr(ex, "_ocr_image", lambda img, lang: ("", None))
    k, b = solo
    r = k.post("/api/smart-intake/documents", files=[("files", ("sken.pdf", _sken_pdf(SKEN), "application/pdf"))], headers=A)
    jid = r.json()["rezultati"][0]["job_id"]
    _do_kraja()
    g = k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()
    assert g["job"]["status"] == "awaiting_review" and g["potrebna_provera"]["razlog"] == "ocr_failed"
    assert g["dokument"]["ocr_koriscen"] is False
    assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", json={}, headers=A).status_code == 200
    assert k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()["dokument"]["ocr_koriscen"] is False

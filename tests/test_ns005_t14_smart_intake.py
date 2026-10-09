# -*- coding: utf-8 -*-
"""NS005 Task 14 — Smart Intake kroz STVARNE rute (routers/smart_intake.py), STVARAN worker
(shared/intake_worker.IntakeWorker._tick) i STVARAN OCR (Tesseract).

Zamenjeno je samo ono što je spoljno i plaćeno, a nije predmet provere: pozivi modela
(klasifikacija kad heuristika ne odluči, slobodan tekst stranaka) i embedding/Pinecone upis
(`uploaded_doc.ingest.ingest_session` — beleži se namespace). Regex polja (broj predmeta, iznos,
sud, rok) izvlače se iz PRAVOG OCR teksta. Intake red je verna emulacija SQL-a migracija 073/095
(tests/ns005_intake_fake.py) nad lažnim Supabase-om; skladište je lažna Supabase Storage kofa.

Bez Tesseract-a test se preskače; sa VINDEX_REQUIRE_OCR=1 nedostatak je pad.
"""
import asyncio
import json
import os
import re
import uuid

import pytest

from tests.ns005_harness import pripremi, ocisti, zaglavlje, SPOLJNI_POKUSAJI
from tests import ns005_intake_fake

try:
    import fitz  # noqa: F401
    import pytesseract
    _OCR = str(pytesseract.get_tesseract_version())
except Exception as _e:
    _OCR = None
    if os.getenv("VINDEX_REQUIRE_OCR") == "1":
        raise RuntimeError(f"VINDEX_REQUIRE_OCR=1, ali Tesseract nije dostupan ({type(_e).__name__})")
pytestmark = pytest.mark.skipif(_OCR is None, reason="Tesseract nije dostupan — Smart Intake E2E sa pravim OCR-om preskočen")

PA, PB = "pred-A-1", "pred-B-1"
REDOVI = [
    "OSNOVNI SUD U BEOGRADU",
    "Broj predmeta: P 1234/2026",
    "Tužilac: Marko Petrović iz Beograda",
    "Tuženi: Jovan Jovanović iz Novog Sada",
    "Predmet: naknada štete u iznosu od 250.000,00 dinara",
    "Ročište je zakazano za 15. novembar 2026. godine.",
]
KOFA = "intake-dokumenti"


def _skeniran_pdf(redovi=REDOVI):
    """Skenirana strana bez tekstualnog sloja (rasterizovan tekst, URW Helvetica sa č/ć/š/ž)."""
    import io
    import fitz
    doc = fitz.open()
    strana = doc.new_page(width=595, height=842)
    tw = fitz.TextWriter(strana.rect)
    for i, red in enumerate(redovi):
        tw.append((50, 80 + i * 34), red, font=fitz.Font("helv"), fontsize=20)
    tw.write_text(strana)
    pix = strana.get_pixmap(dpi=200)
    doc.close()
    sken = fitz.open()
    s2 = sken.new_page(width=595, height=842)
    s2.insert_image(s2.rect, stream=pix.tobytes("png"))
    b = io.BytesIO()
    sken.save(b)
    sken.close()
    return b.getvalue()


def _baza():
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Petrović protiv Jovanovića", "status": "aktivan",
                      "broj_predmeta": "P 9999/2025", "sud": "Viši sud u Nišu"},
                     {"id": PB, "user_id": "uid-B", "naziv": "Predmet B", "status": "aktivan"}],
        "intake_jobs": [], "intake_documents": [], "extracted_entities": [], "intake_review_queue": [],
        "intake_segments": [], "intake_audit_log": [], "events": [], "predmet_dokumenti": [], "predmet_hronologija": [],
        "klijenti": [], "predmet_klijenti": [], "v2_mutation_idempotency": [],
    }


@pytest.fixture
def ok(monkeypatch):
    k, b = pripremi(monkeypatch, _baza())
    ns005_intake_fake.ukljuci(b)
    import shared.intake_classify as kl
    import shared.intake_extract as ex
    import uploaded_doc.ingest as ing
    b.vektori = []

    async def _klasifikuj_model(tekst):
        return "other", 0.5

    async def _slobodan_tekst(tekst):
        return {"plaintiff": ("Marko Petrović", 0.6), "defendant": ("Jovan Jovanović", 0.6)}

    def _ingest(manifest, session_id, namespace_override=None, **kw):
        b.vektori.append({"namespace": namespace_override, "predmet_id": (kw.get("extra_metadata") or {}).get("predmet_id")})
        return manifest.total_chunks
    monkeypatch.setattr(kl, "classify_llm", _klasifikuj_model)
    monkeypatch.setattr(ex, "extract_free_text_entities", _slobodan_tekst)
    monkeypatch.setattr(ing, "ingest_session", _ingest)
    yield k, b
    ocisti()


def _otpremi(k, tok, sadrzaj, ime="sken tuzbe.pdf", tip="application/pdf", kljuc=None):
    h = zaglavlje(tok)
    if kljuc:
        h["Idempotency-Key"] = kljuc
    return k.post("/api/smart-intake/documents", files=[("files", (ime, sadrzaj, tip))], headers=h)


def _obradi():
    from shared.intake_worker import IntakeWorker
    return asyncio.run(IntakeWorker(worker_id="test")._tick())


def _do_pregleda(k, b):
    r = _otpremi(k, "A", _skeniran_pdf())
    assert r.status_code == 202, r.text
    jid = r.json()["rezultati"][0]["job_id"]
    assert _obradi() is True
    return jid


def test_skeniran_pdf_kroz_pravi_ocr_do_pregleda(ok):
    k, b = ok
    sirovo = _skeniran_pdf()
    r = _otpremi(k, "A", sirovo)
    assert r.status_code == 202 and r.json()["rezultati"][0]["ok"] is True
    jid = r.json()["rezultati"][0]["job_id"]
    posao = b.tabele["intake_jobs"][0]
    assert posao["status"] == "received" and posao["uploaded_by"] == "uid-A"
    # Ključ skladišta: neproziran, bez imena fajla; sadržaj šifrovan.
    assert re.fullmatch(r"uid-A/[0-9a-f]{32}", posao["storage_path"]) and "sken" not in posao["storage_path"]
    blob = b.storage.sadrzaj[(KOFA, posao["storage_path"])]
    assert blob != sirovo and b"%PDF" not in blob
    assert _obradi() is True
    assert posao["status"] == "awaiting_review"
    g = k.get(f"/api/smart-intake/jobs/{jid}", headers=zaglavlje("A"))
    assert g.status_code == 200, g.text
    d = g.json()
    assert d["dokument"]["ocr_koriscen"] is True
    broj = [e for e in d["entiteti"] if e["entity_type"] == "case_number"][0]
    assert broj["value"] == "P 1234/2026" and broj["confidence"] >= 0.9 and broj["needs_review"] is False   # iz PRAVOG OCR teksta
    assert d["potrebna_provera"] and "document_type" in d["potrebna_provera"]["polja"]


def test_B_nikad_ne_vidi_niti_menja_posao_A(ok):
    k, b = ok
    jid = _do_pregleda(k, b)
    a_ent = k.get(f"/api/smart-intake/jobs/{jid}", headers=zaglavlje("A")).json()["entiteti"][0]["entity_id"]
    odgovori = [
        k.get(f"/api/smart-intake/jobs/{jid}", headers=zaglavlje("B")),
        k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=zaglavlje("B")),
        k.post(f"/api/smart-intake/jobs/{jid}/review/reject", headers=zaglavlje("B")),
        k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": PB}, headers=zaglavlje("B")),
        k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": PA}, headers=zaglavlje("B")),
    ]
    for r in odgovori:
        assert r.status_code == 404, r.text
        assert "sken" not in r.text and "uid-A" not in r.text and "P 1234" not in r.text
    tudj = k.post(f"/api/smart-intake/entities/{a_ent}/correct", json={"corrected_value": "UPAD"}, headers=zaglavlje("B"))
    nepostojeci = k.post(f"/api/smart-intake/entities/{uuid.uuid4()}/correct", json={"corrected_value": "x"}, headers=zaglavlje("B"))
    assert tudj.status_code == nepostojeci.status_code == 404 and tudj.json() == nepostojeci.json()   # bez proročišta postojanja
    assert all(e.get("corrected_value") is None for e in b.tabele["extracted_entities"])
    assert b.tabele["intake_jobs"][0]["status"] == "awaiting_review" and b.tabele["predmet_dokumenti"] == []


def test_dedupe_je_vezan_za_korisnika_bez_procurivanja(ok):
    k, b = ok
    sadrzaj = _skeniran_pdf()
    r1, r2 = _otpremi(k, "A", sadrzaj), _otpremi(k, "A", sadrzaj, ime="drugo ime.pdf")
    j1, j2 = r1.json()["rezultati"][0], r2.json()["rezultati"][0]
    assert j2["job_id"] == j1["job_id"] and j2.get("already_submitted") is True
    rb = _otpremi(k, "B", sadrzaj).json()["rezultati"][0]
    assert rb["ok"] is True and rb["job_id"] != j1["job_id"] and "already_submitted" not in rb   # B ne saznaje ništa o A
    assert len(b.tabele["intake_jobs"]) == 2 and len(b.storage.sadrzaj) == 2
    assert sorted(j["uploaded_by"] for j in b.tabele["intake_jobs"]) == ["uid-A", "uid-B"]


def test_pregled_ispravka_potvrda_i_prikacivanje_ne_prepisuje_predmet(ok):
    k, b = ok
    jid = _do_pregleda(k, b)
    assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": PA}, headers=zaglavlje("A")).status_code == 409   # pregled pre svega
    assert b.tabele["predmet_dokumenti"] == []
    ent = {e["entity_type"]: e for e in k.get(f"/api/smart-intake/jobs/{jid}", headers=zaglavlje("A")).json()["entiteti"]}
    r = k.post(f"/api/smart-intake/entities/{ent['plaintiff']['entity_id']}/correct", json={"corrected_value": "Marko Petrović Ispravljeno"}, headers=zaglavlje("A"))
    assert r.status_code == 200 and r.json()["corrected_value"] == "Marko Petrović Ispravljeno"
    orig = [e for e in b.tabele["extracted_entities"] if e["entity_type"] == "plaintiff"][0]
    assert orig["value"] == "Marko Petrović"   # original se NE briše; ispravka je dodatak
    assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=zaglavlje("A")).json()["job_status_advanced"] is True
    pre = json.dumps(b.tabele["predmeti"], sort_keys=True)
    f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": PA}, headers=zaglavlje("A"))
    assert f.status_code == 200, f.text
    d = f.json()
    assert d["predmet_id"] == PA and d["dokumenata_povezano"] == 1 and d["klijent_dodat"] is False and d["coi_status"] == "COI_NOT_APPLICABLE"
    assert json.dumps(b.tabele["predmeti"], sort_keys=True) == pre   # izvučen „P 1234/2026“ NIJE prepisao potvrđen broj predmeta
    assert [(x["predmet_id"], x["user_id"], x["naziv_fajla"]) for x in b.tabele["predmet_dokumenti"]] == [(PA, "uid-A", "sken tuzbe.pdf")]
    assert b.tabele["klijenti"] == [] and not [h for h in b.tabele["predmet_hronologija"] if h.get("vrsta") == "rok"]
    assert b.vektori == [{"namespace": "user_uid-A", "predmet_id": PA}]


def test_odbijanje_pregleda_zatvara_put_ka_predmetu(ok):
    k, b = ok
    jid = _do_pregleda(k, b)
    r = k.post(f"/api/smart-intake/jobs/{jid}/review/reject", headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": PA}, headers=zaglavlje("A"))
    assert f.status_code in (409, 422) and b.tabele["predmet_dokumenti"] == []


def test_necitljiv_sken_ide_na_pregled_bez_lazne_ekstrakcije(ok):
    k, b = ok
    r = _otpremi(k, "A", _skeniran_pdf(["   "]))
    jid = r.json()["rezultati"][0]["job_id"]
    assert _obradi() is True
    d = k.get(f"/api/smart-intake/jobs/{jid}", headers=zaglavlje("A")).json()
    assert d["job"]["status"] == "awaiting_review" and d["potrebna_provera"]["razlog"] == "ocr_failed"
    assert d["entiteti"] == [] and d["dokument"]["tip"] == "other" and d["dokument"]["tip_pouzdanost"] == 0.0


def test_nepodrzan_format_odbijen_odmah_bez_posla(ok):
    k, b = ok
    r = _otpremi(k, "A", b"MZ\x90\x00", ime="program.exe", tip="application/octet-stream")
    assert r.status_code == 202 and r.json()["rezultati"][0]["ok"] is False and "Nepodržan format" in r.json()["rezultati"][0]["greska"]
    assert b.tabele["intake_jobs"] == [] and b.storage.sadrzaj == {}


def test_V2_idempotencija_prikacivanja_i_ponovljeno_otpremanje(ok):
    k, b = ok
    jid = _do_pregleda(k, b)
    assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers={**zaglavlje("A"), "Idempotency-Key": str(uuid.uuid4())}).status_code == 200
    kljuc = str(uuid.uuid4())
    h = {**zaglavlje("A"), "Idempotency-Key": kljuc}
    f1 = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": PA}, headers=h)
    f2 = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": PA}, headers=h)
    assert f1.status_code == f2.status_code == 200 and f2.json() == f1.json() and f2.headers.get("idempotent-replayed") == "true"
    assert len(b.tabele["predmet_dokumenti"]) == 1 and len(b.vektori) == 1
    zapisi = {(z["path"], z["state"]) for z in b.tabele["v2_mutation_idempotency"]}
    assert (f"/api/smart-intake/jobs/{jid}/finalize", "COMPLETED") in zapisi
    # Otpremanje sa V2 ključem: generička zaštita ga NE baferuje (multipart); štiti ga dedupe na nivou posla.
    sadrzaj, kup = _skeniran_pdf(["DRUGI DOKUMENT", "Broj predmeta: P 77/2026", "Tužilac: Ana Anić"] * 2), str(uuid.uuid4())
    u1, u2 = _otpremi(k, "A", sadrzaj, kljuc=kup), _otpremi(k, "A", sadrzaj, kljuc=kup)
    assert u2.json()["rezultati"][0]["job_id"] == u1.json()["rezultati"][0]["job_id"] and u2.json()["rezultati"][0].get("already_submitted") is True
    assert not [z for z in b.tabele["v2_mutation_idempotency"] if z["path"] == "/api/smart-intake/documents"]
    assert len([j for j in b.tabele["intake_jobs"] if j["uploaded_by"] == "uid-A"]) == 2


def test_nema_spoljne_mreze():
    assert SPOLJNI_POKUSAJI == []

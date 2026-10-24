# -*- coding: utf-8 -*-
"""MIR001 TASK-02 (MIR-01) — ceo Golden Case spis (7 procesnih dokumenata) kroz STVARAN V2 put prijema.

Put (kao frontend-v2-ng/src/nov-predmet.js + prijem-predmeta.js): POST /api/predmeti → POST /api/smart-intake/documents
(svih 7 fajlova u JEDNOM zahtevu, `files` × 7, bez Idempotency-Key — kao V2) → STVARAN intake worker
(pypdf; za sken STVARAN Tesseract kroz `uploaded_doc.extractor`) → pregled → POST /jobs/{id}/finalize → GET /api/predmeti/{id}.

Stvarno: rute, vlasništvo, worker, ekstrakcija, OCR, upisi u bazu u memoriji (tests/ns006_fake.py). Simulirano: prijava,
modeli klasifikacije, embedding/Pinecone (tests/test_osb002_solo_tok.py::postavi_solo).
Bez Tesseract-a se OCR test preskače; uz VINDEX_REQUIRE_OCR=1 nedostatak je pad.
"""
import os

import pytest

from tests import mir001_golden_case as gc
from tests.test_osb002_solo_tok import A, B, _do_kraja_dogadjaja, _radnik, solo  # noqa: F401

try:
    import pytesseract
    _OCR = str(pytesseract.get_tesseract_version())
except Exception:
    _OCR = None
if os.environ.get("VINDEX_REQUIRE_OCR") == "1" and _OCR is None:
    raise RuntimeError("VINDEX_REQUIRE_OCR=1, a Tesseract nije dostupan")
treba_ocr = pytest.mark.skipif(_OCR is None, reason="Tesseract nije dostupan — prijem skena se ne može dokazati")


def _norm(t):
    return " ".join((t or "").split())


def _otpremi_sve(k, dokumenti, h=A):
    files = [("files", (d["ime"], gc.bajtovi(d), "application/pdf")) for d in dokumenti]
    r = k.post("/api/smart-intake/documents", files=files, headers=h)
    assert r.status_code == 202, r.text
    return r.json()["rezultati"]


def _obradi_sve():
    n = 0
    while _radnik():
        n += 1
        assert n < 50
    return n


def _prikaci(k, jid, pid, h=A):
    j = k.get(f"/api/smart-intake/jobs/{jid}", headers=h)
    assert j.status_code == 200, j.text
    if j.json()["job"]["status"] == "awaiting_review":
        assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=h).status_code == 200
    return k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=h)


OSTECEN = bytes([0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x34, 0x0A, 0x00, 0x01]) + b" nije pdf"  # %PDF-1.4, pa smece


def _novi_predmet(k, naziv=f"Alfa Fiktiv protiv Beta Primer Gradnja ({gc.BROJ}, SINTETICKI)", h=A):
    p = k.post("/api/predmeti", json={"naziv": naziv, "tip": "Privredni spor", "opis": "Naknada stete — krov hale"}, headers=h)
    assert p.status_code == 200, p.text
    return p.json()["predmet"]["id"]


def _dok_predmeta(b, pid):
    return [d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid]


def primi_spis(k, b, dokumenti=None):
    """Ceo spis primljen i prikačen jednom novom predmetu A (V2 put). Vraća (pid, {oznaka: red predmet_dokumenti},
    {oznaka: job_id}). Deli ga TASK-03 i dalje."""
    dokumenti = dokumenti or gc.DOKUMENTI
    pid = _novi_predmet(k)
    rez = _otpremi_sve(k, dokumenti)
    assert [x["ok"] for x in rez] == [True] * len(dokumenti), rez
    poslovi = {d["oznaka"]: x["job_id"] for d, x in zip(dokumenti, rez)}
    assert len(set(poslovi.values())) == len(dokumenti)
    _obradi_sve()
    for oz, jid in poslovi.items():
        f = _prikaci(k, jid, pid)
        assert f.status_code == 200, (oz, f.text)
        assert f.json()["predmet_id"] == pid and f.json()["dokumenata_povezano"] == 1, (oz, f.json())
    _do_kraja_dogadjaja(b, najvise=40)
    doks = {d["oznaka"]: next(x for x in _dok_predmeta(b, pid) if x["naziv_fajla"] == d["ime"]) for d in dokumenti}
    return pid, doks, poslovi


@pytest.fixture
def spis(solo):
    """Ceo spis primljen i prikačen jednom predmetu A. Vraća (k, b, pid, {oznaka: red predmet_dokumenti}, {oznaka: job_id})."""
    k, b = solo
    pid, doks, poslovi = primi_spis(k, b)
    return k, b, pid, doks, poslovi


# ── 1. Svih sedam pripada jednom ispravnom predmetu; nijedan nije izgubljen ─────────────────────────────────────────
@treba_ocr
def test_svih_sedam_u_jednom_predmetu_nijedan_izgubljen(spis):
    k, b, pid, doks, poslovi = spis
    assert len(_dok_predmeta(b, pid)) == 7 == len(b.tabele["predmet_dokumenti"])
    assert len({d["id"] for d in doks.values()}) == 7
    assert {d["user_id"] for d in doks.values()} == {"uid-A"}
    assert len([p for p in b.tabele["predmeti"] if p["user_id"] == "uid-A"]) == 1     # prijem nije napravio drugi predmet
    # V2 kartica Dokumenti čita detalj predmeta
    d = k.get(f"/api/predmeti/{pid}", headers=A)
    assert d.status_code == 200
    assert sorted(x["naziv_fajla"] for x in d.json()["dokumenti"]) == sorted(x["ime"] for x in gc.DOKUMENTI)
    # svaki posao je završen i prikačen ovom predmetu (izvedeno stanje koje V2 prikazuje)
    for oz, jid in poslovi.items():
        j = k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()["job"]
        assert j["status"] == "completed" and j["predmet_id"] == pid, (oz, j["status"])
        assert j["prikacivanje"] == "PRIKACENO", (oz, j.get("prikacivanje"))


# ── 2. Tekst: digitalni tačno, sken kroz stvaran OCR ────────────────────────────────────────────────────────────────
@treba_ocr
def test_izvuceni_tekst_odgovara_ocekivanom_sadrzaju(spis):
    k, b, pid, doks, poslovi = spis
    for d in gc.DOKUMENTI:
        tekst = _norm(doks[d["oznaka"]].get("tekst_sadrzaj"))
        if d["skeniran"]:
            tacnih = sum(1 for r in d["redovi"] if _norm(r) in tekst)
            assert tacnih >= len(d["redovi"]) - 1, (d["oznaka"], tacnih, tekst[:300])
        else:
            for r in d["redovi"]:
                assert _norm(r) in tekst, (d["oznaka"], r)
    for nid, n in gc.NAVODI.items():
        assert n["tekst"] in _norm(doks[n["dok"]].get("tekst_sadrzaj")), nid
    # sken je stvarno čitan OCR-om, i V2 to vidi (dokument.ocr_koriscen → „tekst pročitan OCR-om“)
    sken = next(d for d in gc.DOKUMENTI if d["skeniran"])
    j = k.get(f"/api/smart-intake/jobs/{poslovi[sken['oznaka']]}", headers=A).json()
    assert j["dokument"]["ocr_koriscen"] is True
    assert all(k.get(f"/api/smart-intake/jobs/{poslovi[d['oznaka']]}", headers=A).json()["dokument"]["ocr_koriscen"] is False
               for d in gc.DOKUMENTI if not d["skeniran"])


# ── 3. Ponavljanje bez duplikata ────────────────────────────────────────────────────────────────────────────────────
@treba_ocr
def test_ponovljeno_otpremanje_i_prikacivanje_ne_pravi_duplikate(spis):
    k, b, pid, doks, poslovi = spis
    pre = {t: len(b.tabele[t]) for t in ("predmet_dokumenti", "intake_jobs", "predmet_dokazi")}
    # dvostruki klik „Otpremi“ sa istim fajlovima (V2 ne šalje ključ; ključ je vlasnik + sha256 sadržaja)
    rez = _otpremi_sve(k, gc.DOKUMENTI)
    assert [x["job_id"] for x in rez] == [poslovi[d["oznaka"]] for d in gc.DOKUMENTI]
    _obradi_sve()
    # ponovljeno prikačivanje istog posla istom predmetu
    for jid in poslovi.values():
        f = _prikaci(k, jid, pid)
        assert f.status_code == 200 and f.json()["predmet_id"] == pid, f.text
    _do_kraja_dogadjaja(b, najvise=20)
    assert {t: len(b.tabele[t]) for t in pre} == pre
    assert len(_dok_predmeta(b, pid)) == 7


# ── 4. Neuspela obrada nikad ne prikazuje lažan uspeh ───────────────────────────────────────────────────────────────
@treba_ocr
def test_osteceni_fajl_u_istom_prijemu_nije_lazni_uspeh(spis):
    k, b, pid, doks, poslovi = spis
    r = k.post("/api/smart-intake/documents", files=[("files", ("09 Ostecen podnesak.pdf", OSTECEN, "application/pdf"))],
               headers=A)
    assert r.status_code == 202, r.text
    x = r.json()["rezultati"][0]
    assert x["ok"] is True                          # prihvaćen na ulazu, pada u obradi (stvaran pypdf)
    _obradi_sve()
    j = k.get(f"/api/smart-intake/jobs/{x['job_id']}", headers=A).json()["job"]
    assert j["status"] == "failed" and j["prikacivanje"] == "NIJE_PRIKACENO", (j["status"], j.get("prikacivanje"))
    assert "nije ispravan PDF" in (j.get("last_error") or "")        # razlog koji V2 prikazuje
    f = k.post(f"/api/smart-intake/jobs/{x['job_id']}/finalize", json={"predmet_id": pid}, headers=A)
    assert f.status_code == 409, f.text                               # nikad „prikačeno“
    assert [d["naziv_fajla"] for d in _dok_predmeta(b, pid) if d["naziv_fajla"].startswith("09")] == []
    assert len(_dok_predmeta(b, pid)) == 7                            # ostatak spisa netaknut
    # ISTI bajtovi ponovo (dvostruki klik): vraća se isti, i dalje neuspeli posao — ne nastaje „uspešna“ kopija
    r2 = k.post("/api/smart-intake/documents", files=[("files", ("09 Ostecen podnesak.pdf", OSTECEN, "application/pdf"))], headers=A)
    assert r2.status_code == 202, r2.text
    x2 = r2.json()["rezultati"][0]
    assert x2["job_id"] == x["job_id"], x2
    _obradi_sve()
    assert k.get(f"/api/smart-intake/jobs/{x['job_id']}", headers=A).json()["job"]["status"] == "failed"
    assert len(_dok_predmeta(b, pid)) == 7


# ── 5. Korisnik B ne vidi i ne dira spis korisnika A ────────────────────────────────────────────────────────────────
@treba_ocr
def test_korisnik_b_nema_pristup_predmetu_dokumentima_ni_poslovima_a(spis):
    k, b, pid, doks, poslovi = spis
    pid_b = _novi_predmet(k, gc.B_PREDMET["naziv"], h=B)
    [xb] = _otpremi_sve(k, [{**gc.B_DOKUMENT, "oznaka": "B"}], h=B)
    _obradi_sve()
    assert k.get(f"/api/predmeti/{pid}", headers=B).status_code in (403, 404)
    assert pid not in [p["id"] for p in (k.get("/api/predmeti", headers=B).json().get("predmeti") or [])]
    for d in doks.values():
        assert k.get(f"/api/predmeti/{pid}/dokumenti/{d['id']}/preview", headers=B).status_code in (403, 404)
    for jid in poslovi.values():
        assert k.get(f"/api/smart-intake/jobs/{jid}", headers=B).status_code in (403, 404)
        assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid_b}, headers=B).status_code in (403, 404)
    # B ne može da ubaci svoj dokument u predmet A
    f = _prikaci(k, xb["job_id"], pid, h=B) if k.get(f"/api/smart-intake/jobs/{xb['job_id']}", headers=B).status_code == 200 else None
    assert f is not None and f.status_code in (403, 404), (f.status_code, f.text) if f is not None else None
    assert len(_dok_predmeta(b, pid)) == 7
    assert gc.B_MARKER not in " ".join((d.get("tekst_sadrzaj") or "") for d in _dok_predmeta(b, pid))
    # i obrnuto: A ne vidi B
    assert k.get(f"/api/predmeti/{pid_b}", headers=A).status_code in (403, 404)

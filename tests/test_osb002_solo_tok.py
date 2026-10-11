# -*- coding: utf-8 -*-
"""OSB002 Task 1 — JEDAN neprekinut solo tok advokata kroz STVARNE rute (isti identitet, isti predmet).

Tok (redosled koji V2 koristi; frontend-v2-ng/src/*.js): klijent → predmet → veza klijent–predmet →
Smart Intake otpremanje digitalnog PDF-a → STVARAN intake worker → pregled → prikačivanje predmetu →
trajni događaji (STVARAN dispečer) → dokazi i Genome → V2 čitanja (genome-v2, case-actions, workspace) →
pravno pitanje → Law Brain → nacrt na overu. Svaki korak čita ono što je prethodni STVARNO upisao.

Šta je stvarno: api.py i ruteri, provere vlasništva, FastAPI HTTP (TestClient), intake worker, pypdf
ekstrakcija teksta, Case Evolution dispečer, V2 projekcije. Upisi su STVARNI nad bazom u memoriji
(tests/ns006_fake.py — jedinstvenost i DEFAULT-i prepisani iz migracija; intake RPC-ovi iz 073/095).
Šta je SIMULIRANO (spoljni provajderi): prijava (Supabase Auth → deterministički token), modeli
(klasifikacija, Genome, odgovor na pitanje, nacrt), embedding/Pinecone upis, pretraga korpusa. OCR NIJE
u ovom toku: PDF ima tekstualni sloj (skenirani PDF pokriva test_ns005_t14_smart_intake sa Tesseract-om).
"""
import asyncio
import copy
import io
import json
import re
import types
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from tests import ns005_intake_fake
from tests import ns006_realni_predmet as rp
from tests.ns005_harness import SPOLJNI_POKUSAJI
from tests.ns006_fake import dispecuj, ocisti, pripremi, zaglavlje

A, B = zaglavlje("A"), zaglavlje("B")
REDOVI = [
    "OSNOVNI SUD U BEOGRADU",
    "Broj predmeta: P 4321/2026",
    "Tuzilac: Marko Petrovic iz Beograda",
    "Tuzeni: Gradnja Invest DOO Beograd",
    "Resenje o otkazu je uruceno zaposlenom 17.03.2025. godine.",
    "Predmet: ponistaj resenja o otkazu i isplata zarade od 480.000,00 dinara.",
]
TABELE = ("predmeti", "klijenti", "predmet_klijenti", "intake_jobs", "intake_documents", "extracted_entities",
          "intake_review_queue", "intake_segments", "intake_audit_log", "events", "predmet_dokumenti",
          "predmet_hronologija", "predmet_dokazi", "predmet_genome_history", "predmet_issues", "predmet_contradictions",
          "predmet_contradiction_claims", "case_actions", "case_evolution_consequences", "v2_mutation_idempotency",
          "rocista", "proactive_alerts", "notifications", "audit_immutable", "predmet_beleske", "predmet_istorija",
          "staging_memory")


def _pdf(redovi=REDOVI):
    """Digitalni PDF sa tekstualnim slojem (reportlab je u requirements.txt)."""
    from reportlab.pdfgen import canvas
    b = io.BytesIO()
    c = canvas.Canvas(b)
    for i, red in enumerate(redovi):
        c.drawString(60, 780 - i * 24, red)
    c.showPage()
    c.save()
    return b.getvalue()


def _klasifikuj(naziv, tekst):
    """Model klasifikacije (zamena): iz STVARNOG izvučenog teksta uzima rečenice sa datumom."""
    recenice = [l.strip() for l in tekst.splitlines() if re.search(r"\d{2}\.\d{2}\.\d{4}", l)]
    return {"tip_dokaza": "dopis", "pravni_elementi": ["uručenje"] * len(recenice), "ai_tags": {}, "kljucne_cinjenice": recenice}


def _genome(pozivi):
    async def _pozovi(client, combined, n):
        pozivi.append(combined)
        g = copy.deepcopy(rp._genome(0, False, 0, 0))
        for polje in ("verzija", "_analiza_osnov", "_genome_docs_count", "_genome_docs_preskoceno", "_dokumenti_bez_teksta", "_verifikacija"):
            g.pop(polje, None)
        g["rokovi_kriticni"] = []
        return json.dumps(g, ensure_ascii=False)
    return _pozovi


@pytest.fixture
def solo(monkeypatch):
    k, b = pripremi(monkeypatch, {t: [] for t in TABELE})
    ns005_intake_fake.ukljuci(b)
    # `predmeti.case_dna` nema definiciju u migracijama; produkcija (read-only brojanje 2026-10-11): 0 od 148 redova
    # je NULL, 125 je '{}' — nov red dobija '{}'. Bez ovoga lažna baza vraća NULL, čega u produkciji nema.
    b.podrazumevano.setdefault("predmeti", {}).update({"case_dna": {}, "observation_version": 0})   # 124: NOT NULL DEFAULT 0
    import routers.case_dna as cd
    import routers.evidence as ev
    import shared.intake_classify as kl
    import shared.intake_extract as ex
    import shared.permissions as perm
    import shared.usage as us
    import uploaded_doc.ingest as ing

    b.vektori, b.naplate, b.genome_pozivi = [], [], []

    async def _politika(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

    async def _nista(*a, **kw):
        return None

    async def _naplati(*a, **kw):
        b.naplate.append(a)
        return 10

    async def _klas_model(tekst):
        return "other", 0.5

    async def _stranke(tekst):
        return {"plaintiff": ("Marko Petrovic", 0.6), "defendant": ("Gradnja Invest DOO Beograd", 0.6)}

    def _ingest(manifest, session_id, namespace_override=None, **kw):
        b.vektori.append({"namespace": namespace_override, "predmet_id": (kw.get("extra_metadata") or {}).get("predmet_id")})
        return manifest.total_chunks

    monkeypatch.setattr(perm, "get_policy", _politika)
    monkeypatch.setattr(perm, "_check_dependencies", _nista)
    monkeypatch.setattr(us.UsageService, "consume", staticmethod(_naplati))
    monkeypatch.setattr(us.UsageService, "refund", staticmethod(_nista))
    monkeypatch.setattr(kl, "classify_llm", _klas_model)
    monkeypatch.setattr(ex, "extract_free_text_entities", _stranke)
    monkeypatch.setattr(ing, "ingest_session", _ingest)
    monkeypatch.setattr(ev, "_klasifikuj_dokument", _klasifikuj)
    monkeypatch.setattr(cd, "_pozovi_genome_api", _genome(b.genome_pozivi))
    import services.case_pipeline as cp
    b.pipeline_pozivi = []

    async def _pipeline_model(oai, **kw):
        b.pipeline_pozivi.append(kw.get("model"))
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="{}"))],
                                     usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))
    monkeypatch.setattr(cp, "_pozovi_pipeline_api", _pipeline_model)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-bez-mreze")
    yield k, b
    ocisti()


def _radnik():
    from shared.intake_worker import IntakeWorker
    return asyncio.run(IntakeWorker(worker_id="osb002")._tick())


def _otpremi(k, sadrzaj, ime="Resenje o otkazu.pdf", h=A, kljuc=None):
    h = dict(h)
    if kljuc:
        h["Idempotency-Key"] = kljuc
    return k.post("/api/smart-intake/documents", files=[("files", (ime, sadrzaj, "application/pdf"))], headers=h)


def _do_kraja_dogadjaja(b, najvise=6):
    for _ in range(najvise):
        rez = dispecuj()
        assert rez[0]["greske"] == 0, (rez, [(e["event_type"], e.get("last_error")) for e in b.tabele["events"] if e.get("last_error")])
        if all(e.get("dispatched_at") for e in b.tabele["events"]):
            return
    raise AssertionError("događaji nisu ispražnjeni")


def _novi_predmet(k, b):
    kl = k.post("/klijenti", json={"ime": "Marko", "prezime": "Petrovic"}, headers=A)
    assert kl.status_code == 200, kl.text
    kid = kl.json()["klijent"]["id"]
    p = k.post("/api/predmeti", json={"naziv": "Petrovic protiv Gradnja Invest", "tip": "Radni spor", "opis": "Nezakonit otkaz"}, headers=A)
    assert p.status_code == 200, p.text
    pid = p.json()["predmet"]["id"]
    v = k.post(f"/api/predmeti/{pid}/confirm-links", json={"klijent_ids": [kid], "uloga": "tuzilac"}, headers=A)
    assert v.status_code == 200 and v.json()["linked_klijenti"] == [kid], v.text
    return kid, pid


def _prijem_dokumenta(k, b, pid, sadrzaj=None, ime="Resenje o otkazu.pdf"):
    r = _otpremi(k, sadrzaj or _pdf(), ime=ime)
    assert r.status_code == 202 and r.json()["rezultati"][0]["ok"] is True, r.text
    jid = r.json()["rezultati"][0]["job_id"]
    assert _radnik() is True
    posao = next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)
    if posao["status"] == "awaiting_review":
        rr = k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=A)
        assert rr.status_code == 200, rr.text
    f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    assert f.status_code == 200, f.text
    return jid, f.json()


def test_jedan_neprekinut_solo_tok(solo):
    k, b = solo
    kid, pid = _novi_predmet(k, b)
    red = next(p for p in b.tabele["predmeti"] if p["id"] == pid)
    assert red["user_id"] == "uid-A" and red["status"] == "aktivan"

    # Prijem dokumenta (stvaran worker + pypdf; bez OCR-a)
    jid, fin = _prijem_dokumenta(k, b, pid)
    assert fin["predmet_id"] == pid and fin["dokumenata_povezano"] == 1, fin
    posao = next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)
    assert posao["uploaded_by"] == "uid-A" and posao["status"] == "completed", posao["status"]
    doks = [d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid]
    assert len(doks) == 1 and doks[0]["user_id"] == "uid-A"
    assert "P 4321/2026" in (doks[0].get("tekst_sadrzaj") or ""), "izvučen tekst nije sačuvan uz dokument"
    assert b.vektori == [{"namespace": "user_uid-A", "predmet_id": pid}]

    # Detalj predmeta i pregled teksta — ono što V2 kartica Dokumenti prikazuje
    d = k.get(f"/api/predmeti/{pid}", headers=A)
    assert d.status_code == 200, d.text
    dj = d.json()
    assert [x["id"] for x in dj.get("dokumenti", [])] == [doks[0]["id"]]
    assert [x["id"] for x in dj["klijenti_linked"]] == [kid]
    pv = k.get(f"/api/predmeti/{pid}/dokumenti/{doks[0]['id']}/preview", headers=A)
    assert pv.status_code == 200 and "P 4321/2026" in pv.text, pv.text[:300]

    # Trajni događaji → dokazi i Genome (stvaran dispečer)
    _do_kraja_dogadjaja(b)
    dokazi = [x for x in b.tabele["predmet_dokazi"] if x["predmet_id"] == pid]
    assert dokazi and all(x["dokument_id"] == doks[0]["id"] for x in dokazi)
    assert any("17.03.2025" in x["tvrdnja"] for x in dokazi)
    red = next(p for p in b.tabele["predmeti"] if p["id"] == pid)
    assert (red.get("case_dna") or {}).get("verzija") == 1, red.get("case_dna")

    # V2 čitanja — bez poziva modela
    n = len(b.genome_pozivi)
    ziv = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A)
    akc = k.get(f"/api/case-actions/predmeti/{pid}", headers=A)
    ws = k.get("/api/workspace", headers=A)
    lb = k.get(f"/api/law-brain/predmeti/{pid}", headers=A)
    for r in (ziv, akc, ws, lb):
        assert r.status_code == 200, (r.request.url, r.text[:300])
    assert len(b.genome_pozivi) == n, "čitanje je pozvalo model"
    zj = ziv.json()
    tvrd_ids = {x["id"] for x in dokazi}
    assert zj["dokazi"]["tvrdnje"] and all(t["id"] in tvrd_ids for t in zj["dokazi"]["tvrdnje"])
    assert pid in ws.text
    assert ws.json().get("vindex_je_pripremio_stanje") in ("NIJE_UKLJUCENO", "PRAZNO", "OK"), ws.json().get("vindex_je_pripremio_stanje")

    # B ne vidi ništa od toga
    for put in (f"/api/predmeti/{pid}", f"/api/predmeti/{pid}/genome-v2", f"/api/case-actions/predmeti/{pid}",
                f"/api/law-brain/predmeti/{pid}", f"/api/smart-intake/jobs/{jid}",
                f"/api/predmeti/{pid}/dokumenti/{doks[0]['id']}/preview"):
        r = k.get(put, headers=B)
        assert r.status_code == 404, (put, r.status_code)
        assert "P 4321" not in r.text and "Petrovic" not in r.text
    assert "Petrovic" not in k.get("/api/workspace", headers=B).text
    assert SPOLJNI_POKUSAJI == [] or not any("openai" in h or "pinecone" in h for h in SPOLJNI_POKUSAJI)

    # Beleška, pravno pitanje u kontekstu predmeta (model zamenjen: hvata upit), nacrt na overu
    bl = k.post(f"/api/predmeti/{pid}/beleske", json={"sadrzaj": "SOLO-BELESKA svedok Jovan potvrđuje kasnu dostavu"}, headers=A)
    assert bl.status_code == 200, bl.text
    import api
    upiti = []

    async def _pokreni(fn, pitanje_za_agenta, *a, **kw):
        upiti.append(pitanje_za_agenta)
        return {"status": "success", "data": "--- PRAVNI ZAKLJUČAK\nOdgovor.", "confidence": "HIGH", "top_score": 0.8,
                "confidence_detail": {"nivo": "HIGH"}, "izvori": [{"zakon": "zakon o radu", "clan": "Član 185"}]}
    with patch.object(api, "pokreni", _pokreni):
        q = k.post("/api/pitanje", json={"pitanje": "Da li je otkaz zakonito uručen?", "predmet_id": pid}, headers=A)
        qb = k.post("/api/pitanje", json={"pitanje": "Da li je otkaz zakonito uručen?", "predmet_id": pid}, headers=B)
    assert q.status_code == 200 and q.json()["kontekst_predmeta"] is True, q.text
    assert "SOLO-BELESKA" in upiti[0]
    assert q.json()["izvori"] == [{"zakon": "zakon o radu", "clan": "Član 185"}]
    assert qb.status_code == 200 and qb.json()["kontekst_predmeta"] is False and "SOLO-BELESKA" not in upiti[1]

    import routers.drafting as D
    import services.quality_gate as QG

    def _model(oai, **kw):
        if kw.get("max_tokens") == 900:
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(
                content=json.dumps({"tuzilac": "Marko Petrovic", "tuzeni": "Gradnja Invest DOO"})))])
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps({"pravni_osnov": "čl. 185 ZR"})))])

    async def _kriticar(oai, nacrt, kontekst, tip):
        return {"ima_izmisljenih_navoda": False}

    async def _kvalitet(t, tip):
        return {"confidence_score": 0.5, "detail": {}}
    import app.services.retrieve as R
    with patch.object(D, "_pozovi_drafting_api", _model), patch.object(D, "_pozovi_kriticara", _kriticar), \
            patch.object(QG, "evaluate_draft_quality", _kvalitet), \
            patch.object(R, "retrieve_documents", lambda *a, **kw: (["Zakon o radu, Član 185: Rešenje o otkazu se dostavlja..."], {})):
        n = k.post("/api/podnesak", json={"tip": "tuzba_naknada_stete", "opis": "Tužba radi poništaja rešenja o otkazu.", "predmet_id": pid}, headers=A)
        nb = k.post("/api/podnesak", json={"tip": "tuzba_naknada_stete", "opis": "Tužba radi poništaja rešenja o otkazu.", "predmet_id": pid}, headers=B)
    assert n.status_code == 200, n.text
    nj = n.json()
    assert nj["ai_generated"] is True and "mora biti pregledan od strane ovlašćenog advokata" in nj["odgovor"]
    assert nb.status_code == 404
    # Ništa od A nije prešlo na B; svi upisi ovog toka nose vlasnika A
    for t in ("predmeti", "klijenti", "predmet_dokumenti", "predmet_dokazi", "predmet_beleske", "intake_jobs"):
        for r in b.tabele[t]:
            assert (r.get("user_id") or r.get("uploaded_by")) == "uid-A", (t, r.get("user_id"))


# ── Adversarijalni slučajevi nad ISTIM tokom (isti korisnik, stvarne rute) ───────────────────────────────────

def test_ponovljeno_slanje_istog_dokumenta_i_dupla_finalizacija(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    sadrzaj = _pdf()
    r1, r2 = _otpremi(k, sadrzaj), _otpremi(k, sadrzaj, ime="drugo ime.pdf")
    j1, j2 = r1.json()["rezultati"][0], r2.json()["rezultati"][0]
    assert j2["job_id"] == j1["job_id"] and j2.get("already_submitted") is True
    assert len(b.tabele["intake_jobs"]) == 1
    assert _radnik() is True
    jid = j1["job_id"]
    if b.tabele["intake_jobs"][0]["status"] == "awaiting_review":
        assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=A).status_code == 200
    f1 = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    f2 = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    assert f1.status_code == 200, f1.text
    assert f2.status_code in (200, 409), f2.text
    assert len([d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid]) == 1, "dupla finalizacija je napravila drugi dokument"
    _do_kraja_dogadjaja(b)
    n_dokaza = len(b.tabele["predmet_dokazi"])
    # ponovna isporuka događaja (retry) ne duplira tvrdnje
    for e in b.tabele["events"]:
        if e["event_type"] == "NewEvidenceRegistered":
            e["dispatched_at"] = None
            e["claimed_at"] = None
    b.tabele["case_evolution_consequences"] = [c for c in b.tabele["case_evolution_consequences"] if c["consequence_name"] != "evidence_classification"]
    _do_kraja_dogadjaja(b)
    assert len(b.tabele["predmet_dokazi"]) == n_dokaza, "ponovljen događaj je duplirao tvrdnje"


def test_dupli_predmet_u_5_sekundi_je_409(solo):
    k, b = solo
    telo = {"naziv": "Isti naziv predmeta", "tip": "Radni spor"}
    r1, r2 = k.post("/api/predmeti", json=telo, headers=A), k.post("/api/predmeti", json=telo, headers=A)
    assert r1.status_code == 200 and r2.status_code == 409
    assert len([p for p in b.tabele["predmeti"] if p["naziv"] == "Isti naziv predmeta"]) == 1


def test_prekinuta_obrada_nije_zavrsena_i_ne_moze_da_se_prikaci(solo, monkeypatch):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    jid = _otpremi(k, _pdf()).json()["rezultati"][0]["job_id"]
    from shared.intake_worker import IntakeWorker

    def _pad(self, path):
        raise RuntimeError("worker prekinut usred ekstrakcije")
    monkeypatch.setattr(IntakeWorker, "_extract_text", _pad)
    assert _radnik() is True
    posao = b.tabele["intake_jobs"][0]
    assert posao["status"] not in ("completed", "awaiting_review"), posao["status"]
    f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
    assert f.status_code >= 400 and b.tabele["predmet_dokumenti"] == []
    g = k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()
    assert g["job"]["status"] == posao["status"] and g["job"]["last_error"]
    # ponovni pokušaj posle prekida završava normalno
    monkeypatch.undo()
    posao["next_retry_at"] = None
    posao["status"] = "received" if posao["status"] == "failed_retryable" else posao["status"]


def test_dokument_bez_teksta_ide_na_pregled_ne_lazno_zavrsen(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    from reportlab.pdfgen import canvas
    bb = io.BytesIO()
    c = canvas.Canvas(bb)
    c.rect(100, 100, 200, 200)          # samo crtež, bez ijednog znaka teksta
    c.showPage()
    c.save()
    jid = _otpremi(k, bb.getvalue(), ime="prazan sken.pdf").json()["rezultati"][0]["job_id"]
    assert _radnik() is True
    posao = b.tabele["intake_jobs"][0]
    assert posao["status"] != "completed", "dokument bez teksta je označen kao završen"
    assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A).status_code == 409
    assert b.tabele["predmet_dokumenti"] == []
    d = k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()
    assert d["potrebna_provera"], d


def test_dokument_ne_moze_u_tudj_predmet_ni_tudj_posao(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    pb = k.post("/api/predmeti", json={"naziv": "Tajni predmet B"}, headers=B).json()["predmet"]["id"]
    jid = _otpremi(k, _pdf()).json()["rezultati"][0]["job_id"]
    assert _radnik() is True
    if b.tabele["intake_jobs"][0]["status"] == "awaiting_review":
        assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=A).status_code == 200
    u_tudj = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pb}, headers=A)
    tudj_posao = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pb}, headers=B)
    assert u_tudj.status_code == 404 and tudj_posao.status_code == 404
    assert b.tabele["predmet_dokumenti"] == []
    # BETA-DEF-003 (zabeleženo, nije ispravljeno): 404 za tuđ/nepostojeći predmet se diže POSLE zauzimanja finalizacije
    # i ne oslobađa ga (susedne grane greške ga oslobađaju) — posao je zaključan do isteka 120 s, pa se sam oslobađa.
    assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A).status_code == 409
    from datetime import datetime, timedelta, timezone
    b.tabele["intake_jobs"][0]["finalizing_at"] = (datetime.now(timezone.utc) - timedelta(seconds=121)).isoformat()
    assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A).status_code == 200
    assert [d["predmet_id"] for d in b.tabele["predmet_dokumenti"]] == [pid]


def test_genome_prati_novi_dokument_ne_ostaje_ustajao(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    _prijem_dokumenta(k, b, pid)
    _do_kraja_dogadjaja(b)
    v1 = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A).json()
    _prijem_dokumenta(k, b, pid, sadrzaj=_pdf(["POSTA SRBIJE - DOSTAVNICA", "Broj posiljke: RR 123456789 RS",
                                                             "Primalac: Marko Petrovic, Beograd, ulica Nemanjina 4",
                                                             "Posiljka je urucena primaocu dana 25.03.2025. godine.",
                                                             "Posiljalac: Gradnja Invest DOO Beograd, pravna sluzba",
                                                             "Potpis primaoca i dostavljaca nalaze se na poledjini."]),
                      ime="Dostavnica.pdf")
    _do_kraja_dogadjaja(b)
    red = next(p for p in b.tabele["predmeti"] if p["id"] == pid)
    assert red["case_dna"]["verzija"] == 2
    v2 = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A).json()
    assert len(v2["dokazi"]["tvrdnje"]) > len(v1["dokazi"]["tvrdnje"])
    assert any("25.03.2025" in t["vrednost"] for t in v2["dokazi"]["tvrdnje"])


def test_pad_genome_modela_ne_pravi_lazno_stanje(solo, monkeypatch):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    import routers.case_dna as cd

    async def _pad(*a, **kw):
        raise RuntimeError("model nedostupan")
    monkeypatch.setattr(cd, "_pozovi_genome_api", _pad)
    _prijem_dokumenta(k, b, pid)
    for _ in range(3):
        dispecuj()
    red = next(p for p in b.tabele["predmeti"] if p["id"] == pid)
    assert not (red.get("case_dna") or {}).get("verzija"), "Genome verzija upisana iako model nije odgovorio"
    neuspeh = [e for e in b.tabele["events"] if e["event_type"] == "DocumentAccepted"]
    assert neuspeh and all(not e.get("dispatched_at") or e.get("last_error") for e in neuspeh)
    akcije = [a for a in b.tabele["case_actions"] if a.get("predmet_id") == pid and a.get("status") == "open"]
    dok_ids = {d["id"] for d in b.tabele["predmet_dokumenti"]}
    for a in akcije:
        assert set(a.get("izvor_dokumenti") or []) <= dok_ids, a
    g = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A)
    assert g.status_code == 200
    assert g.json().get("trenutna_verzija") in (None, 0) or not g.json().get("genome"), g.json().get("trenutna_verzija")


def test_tvrdnja_modela_nije_predstavljena_kao_proverena(solo):
    k, b = solo
    _, pid = _novi_predmet(k, b)
    _prijem_dokumenta(k, b, pid)
    _do_kraja_dogadjaja(b)
    ziv = k.get(f"/api/predmeti/{pid}/genome-v2", headers=A).json()
    for t in ziv["dokazi"]["tvrdnje"]:
        assert t["poreklo"] != "HUMAN_CONFIRMED", t        # model nikad ne postaje „potvrdio advokat"
        if t["poreklo"] == "SOURCE_FACT":
            assert t["dokument_id"], t                    # „činjenica iz izvora" uvek pokazuje na dokument

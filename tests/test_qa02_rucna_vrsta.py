# -*- coding: utf-8 -*-
"""QA-02 — advokat ispravlja vrstu JEDNOG dokumenta, a ispravka ostaje autoritativna.

STVARNO: rute `routers/smart_intake.py` i `routers/evidence.py` kroz FastAPI TestClient, intake worker
(`IntakeWorker._tick`, heuristika klasifikacije), prikačivanje (finalize), posledica AI klasifikacije dokaza
(`services/case_evolution._consequence_evidence_classify` → `routers/evidence.klasifikuj_i_sacuvaj`) i
zajednički upis tvrdnji. ZAMENJENO: Supabase (tests/ns005_harness — filtri i upisi se stvarno primenjuju,
`kolona->>ključ` kao Postgres), odgovor modela (deterministički, bez mreže), Pinecone, upis audit zapisa
(beleži se, može se oboriti). Sintetički tekstovi.
"""
import asyncio

import pytest

from tests import ns005_intake_fake
from tests.ns005_harness import ocisti, pripremi, zaglavlje

NL = chr(10)
PA, PB = "pred-A-1", "pred-B-1"
TUZBA = NL.join(["TUŽBA", "Osnovnom sudu u Beogradu", "Tužilac: Marko Petrović iz Beograda",
                 "Tuženi: Jovan Jovanović iz Novog Sada", "radi naknade štete zbog neispunjenja ugovora."])
TUZBA_2 = NL.join(["TUŽBA", "Višem sudu u Nišu", "Tužilac: Ana Anić", "Tuženi: Petar Perić",
                   "radi utvrđenja prava svojine na stanu."])
OZNAKA = "_vrsta_advokat"


def _baza():
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Petrović protiv Jovanovića", "status": "aktivan"},
                     {"id": PB, "user_id": "uid-B", "naziv": "Predmet B", "status": "aktivan"}],
        "intake_jobs": [], "intake_documents": [], "extracted_entities": [], "intake_review_queue": [],
        "intake_job_segments": [], "intake_processing_outcomes": [], "intake_audit_log": [], "events": [],
        "predmet_dokumenti": [], "predmet_dokazi": [], "predmet_hronologija": [], "klijenti": [],
        "predmet_klijenti": [], "v2_mutation_idempotency": [],
    }


@pytest.fixture
def ok(monkeypatch):
    k, b = pripremi(monkeypatch, _baza())
    ns005_intake_fake.ukljuci(b)
    import routers.evidence as ev
    import shared.audit_immutable as audit
    import shared.intake_classify as kl
    import shared.intake_extract as ex
    import uploaded_doc.ingest as ing

    async def _model_vrste(tekst):
        return "other", 0.5

    async def _slobodan_tekst(tekst):
        return {}

    def _ingest(manifest, session_id, namespace_override=None, **kw):
        return manifest.total_chunks
    monkeypatch.setattr(kl, "classify_llm", _model_vrste)
    monkeypatch.setattr(ex, "extract_free_text_entities", _slobodan_tekst)
    monkeypatch.setattr(ing, "ingest_session", _ingest)

    # AI klasifikacija dokaza (routers/evidence.py): deterministički odgovor umesto modela.
    b.ai_vrsta = "podnesak"
    monkeypatch.setattr(ev, "_klasifikuj_dokument", lambda naziv, tekst: {
        "tip_dokaza": b.ai_vrsta, "pravni_elementi": ["naknada štete"],
        "ai_tags": {"_klasifikacija_pouzdanost": "visoka"},
        "kljucne_cinjenice": ["Tužilac traži naknadu štete zbog neispunjenja ugovora."]})

    b.audit = []
    b.audit_pada = False

    async def _audit(action, user_id=None, resource_type=None, resource_id=None, ip=None, metadata=None, **kw):
        if b.audit_pada == "baca":
            raise RuntimeError("audit_immutable: connection reset")
        if b.audit_pada:
            return None
        b.audit.append({"action": action, "user_id": user_id, "resource_type": resource_type,
                        "resource_id": resource_id, "metadata": dict(metadata or {})})
        return "audit-%d" % len(_aud(b))
    monkeypatch.setattr(audit, "log_action", _audit)
    yield k, b
    ocisti()


def _otpremi(k, korisnik, tekst, ime="dokument.txt"):
    r = k.post("/api/smart-intake/documents", files=[("files", (ime, tekst.encode("utf-8"), "text/plain"))],
               headers=zaglavlje(korisnik))
    assert r.status_code == 202, r.text
    x = r.json()["rezultati"][0]
    assert x["ok"] is True, x
    return x["job_id"]


def _obradi():
    from shared.intake_worker import IntakeWorker
    return asyncio.run(IntakeWorker(worker_id="test")._tick())


def _posao(k, jid, korisnik="A"):
    r = k.get(f"/api/smart-intake/jobs/{jid}", headers=zaglavlje(korisnik))
    assert r.status_code == 200, r.text
    return r.json()


def _spreman(k, korisnik="A", tekst=TUZBA, ime="dokument.txt"):
    jid = _otpremi(k, korisnik, tekst, ime)
    assert _obradi() is True
    return jid


def _ispravi(k, doc_id, vrsta, prethodna, korisnik="A"):
    return k.post(f"/api/smart-intake/documents/{doc_id}/vrsta", json={"vrsta": vrsta, "prethodna": prethodna},
                  headers=zaglavlje(korisnik))


def _ispravi_u_predmetu(k, dok_id, vrsta, prethodna, predmet=PA, korisnik="A"):
    return k.post(f"/api/evidence/predmeti/{predmet}/dokumenti/{dok_id}/vrsta",
                  json={"vrsta": vrsta, "prethodna": prethodna}, headers=zaglavlje(korisnik))


def _prikaci(k, jid, predmet=PA, korisnik="A"):
    if _posao(k, jid, korisnik)["job"]["status"] == "awaiting_review":
        assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=zaglavlje(korisnik)).status_code == 200
    r = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": predmet}, headers=zaglavlje(korisnik))
    assert r.status_code == 200, r.text
    return r.json()


def _ai_klasifikacija(b, dok_id, predmet=PA, korisnik="uid-A"):
    """Stvarna posledica NEW_EVIDENCE_REGISTERED (ono što event bus izvršava posle prikačivanja)."""
    from services.case_evolution import _consequence_evidence_classify
    from services.event_bus import Event, EventType
    return asyncio.run(_consequence_evidence_classify(Event(
        type=EventType.NEW_EVIDENCE_REGISTERED, user_id=korisnik, predmet_id=predmet,
        payload={"dokument_id": dok_id, "naziv": "dokument.txt"})))


def _intake_dok(b, jid):
    return [d for d in b.tabele["intake_documents"] if d["intake_job_id"] == jid]


def _dok_predmeta(b, jid):
    [d] = [d for d in b.tabele["predmet_dokumenti"] if d.get("source_intake_job_id") == jid]
    return d


def _tagovi(d):
    from shared.evidence_graph import _ai_tags
    return _ai_tags(d.get("ai_tags"))


def _aud(b):
    return [a for a in b.audit if a["action"] == "dokument_vrsta_ispravljena"]


def _job_red(b, jid):
    return next(j for j in b.tabele["intake_jobs"] if j["id"] == jid)


# ── 1: pogrešno prepoznata tužba → advokat bira žalbu → prikaz i perzistencija ─────────────────────────

def test_1_tuzba_u_zalbu_pre_prikacivanja_prikaz_baza_audit(ok):
    k, b = ok
    jid = _spreman(k)
    x = _posao(k, jid)
    assert x["job"]["status"] == "awaiting_review"
    assert (x["dokument"]["tip"], x["dokument"]["tip_odredio_advokat"]) == ("lawsuit", False)
    assert "appeal" in x["dozvoljene_vrste"]
    doc_id = x["dokument"]["document_id"]

    r = _ispravi(k, doc_id, "appeal", "lawsuit")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "document_id": doc_id, "vrsta": "appeal", "prethodna": "lawsuit", "promenjeno": True}

    x = _posao(k, jid)                                        # osvežen prikaz čita bazu, ne odgovor ispravke
    assert (x["dokument"]["tip"], x["dokument"]["tip_odredio_advokat"]) == ("appeal", True)
    assert [d["tip"] for d in x["dokumenti"]] == ["appeal"]
    [dok] = _intake_dok(b, jid)
    assert dok["document_type"] == "appeal" and dok["classification_method"] == "heuristic"   # poreklo AI vrednosti se ne briše
    [isp] = [o for o in b.tabele["intake_processing_outcomes"] if o.get("user_corrected")]
    assert (isp["document_type"], isp["fields_corrected"], isp["segment_id"]) == ("appeal", ["document_type"], None)
    assert _aud(b) == [{"action": "dokument_vrsta_ispravljena", "user_id": "uid-A", "resource_type": "intake_documents",
                        "resource_id": doc_id, "metadata": {"staro": "lawsuit", "novo": "appeal", "intake_job_id": jid,
                                                            "faza": "pre_prikacivanja"}}]
    assert _job_red(b, jid)["finalizing_at"] is None          # zauzeće ispravke je oslobođeno


def test_1b_akcija_je_u_dozvoli_audita():
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "dokument_vrsta_ispravljena" in AUDITABLE_ACTIONS   # inače log_action tiho vraća None


# ── 2: ispravka pre prikačivanja opstaje kroz prikačivanje i AI klasifikaciju dokaza ───────────────────

def test_2_ispravka_opstaje_kroz_prikacivanje_i_ai_klasifikaciju(ok):
    k, b = ok
    jid = _spreman(k)
    doc_id = _posao(k, jid)["dokument"]["document_id"]
    assert _ispravi(k, doc_id, "appeal", "lawsuit").status_code == 200
    _prikaci(k, jid)

    red = _dok_predmeta(b, jid)
    assert red["tip_dokaza"] == "appeal"
    assert _tagovi(red)[OZNAKA] == {"tip": "appeal", "akter": "uid-A", "izvor": "prijem", "intake_document_id": doc_id}

    assert _ai_klasifikacija(b, red["id"]) == red["id"]       # AI kaže „podnesak“
    red = _dok_predmeta(b, jid)
    assert red["tip_dokaza"] == "appeal"                      # ljudska odluka ostaje
    assert _tagovi(red).get(OZNAKA, {}).get("tip") == "appeal"
    assert red["klasifikovan_at"] and red["pravni_elementi"] == ["naknada štete"]   # ostatak klasifikacije radi
    assert [t["dokument_id"] for t in b.tabele["predmet_dokazi"]] == [red["id"]]

    ev = k.get(f"/api/evidence/predmeti/{PA}", headers=zaglavlje("A")).json()
    assert [d["tip_dokaza"] for d in ev["dokumenti"]] == ["appeal"]
    from shared.evidence_graph import klasifikacija_dokumenta
    assert klasifikacija_dokumenta(red) == {"stanje": "USPESNA", "tip": "appeal", "odredio": "advokat"}


def test_2_kontrola_bez_ispravke_AI_i_dalje_odredjuje_vrstu(ok):
    """Čuvar ne gasi AI klasifikaciju: dokument bez ljudske odluke dobija AI vrstu kao i ranije."""
    k, b = ok
    jid = _spreman(k)
    _prikaci(k, jid)
    red = _dok_predmeta(b, jid)
    assert red["tip_dokaza"] == "lawsuit" and OZNAKA not in _tagovi(red)
    _ai_klasifikacija(b, red["id"])
    assert _dok_predmeta(b, jid)["tip_dokaza"] == "podnesak"


# ── 3/4: već prikačen dokument se ispravlja u predmetu; ponovna AI klasifikacija ga ne poništava ───────

def test_3_4_ispravka_u_predmetu_i_ponovna_AI_klasifikacija(ok):
    k, b = ok
    jid = _spreman(k)
    _prikaci(k, jid)
    red = _dok_predmeta(b, jid)
    _ai_klasifikacija(b, red["id"])
    assert _dok_predmeta(b, jid)["tip_dokaza"] == "podnesak"

    doc_id = _intake_dok(b, jid)[0]["id"]
    r = _ispravi(k, doc_id, "appeal", "lawsuit")              # prijem posle prikačivanja ne menja ništa
    assert r.status_code == 409 and "u predmetu" in r.json()["detail"]

    r = _ispravi_u_predmetu(k, red["id"], "appeal", "podnesak")
    assert r.status_code == 200, r.text
    assert r.json()["promenjeno"] is True
    red = _dok_predmeta(b, jid)
    assert red["tip_dokaza"] == "appeal"
    oz = _tagovi(red)[OZNAKA]
    assert (oz["tip"], oz["prethodna"], oz["akter"], oz["izvor"]) == ("appeal", "podnesak", "uid-A", "predmet")
    assert _tagovi(red)["_klasifikacija_pouzdanost"] == "visoka"          # postojeći AI tagovi ostaju
    assert _aud(b)[-1] == {"action": "dokument_vrsta_ispravljena", "user_id": "uid-A", "resource_type": "predmet_dokumenti",
                           "resource_id": red["id"], "metadata": {"staro": "podnesak", "novo": "appeal",
                                                                  "predmet_id": PA, "faza": "u_predmetu"}}

    # 4: ponovna AI klasifikacija (isti poziv koji izvršava „Reklasifikuj“) ne poništava ljudsku odluku
    from routers.evidence import klasifikuj_i_sacuvaj
    b.ai_vrsta = "sudska_odluka"
    rez = klasifikuj_i_sacuvaj(PA, red["id"], "dokument.txt", TUZBA, "uid-A")
    assert rez.get("_vrsta_zadrzana") is True
    red = _dok_predmeta(b, jid)
    assert red["tip_dokaza"] == "appeal" and _tagovi(red)[OZNAKA]["tip"] == "appeal"
    ev = k.get(f"/api/evidence/predmeti/{PA}", headers=zaglavlje("A")).json()
    assert [d["tip_dokaza"] for d in ev["dokumenti"]] == ["appeal"]


@pytest.mark.parametrize("ai_tags_kao_string", [False, True])
def test_4_AI_ne_prepisuje_red_sa_oznakom_advokata_bez_rute(ok, ai_tags_kao_string):
    """Bez nove rute: red u predmetu već nosi ljudsku vrstu + oznaku; posledica AI klasifikacije je ne menja.
    Kontrola: isti red BEZ oznake (ili sa starim `ai_tags` kao JSON string) AI i dalje klasifikuje."""
    import json
    k, b = ok
    jid = _spreman(k)
    _prikaci(k, jid)
    red = _dok_predmeta(b, jid)
    oznaka = {OZNAKA: {"tip": "appeal", "akter": "uid-A", "izvor": "predmet"}}
    for r in b.tabele["predmet_dokumenti"]:
        if r["id"] == red["id"]:
            r.update({"tip_dokaza": "appeal", "ai_tags": oznaka})
    _ai_klasifikacija(b, red["id"])
    assert _dok_predmeta(b, jid)["tip_dokaza"] == "appeal"
    assert _dok_predmeta(b, jid)["klasifikovan_at"]                     # tvrdnje i završetak klasifikacije ipak rade

    jid2 = _spreman(k, tekst=TUZBA_2)
    _prikaci(k, jid2)
    red2 = _dok_predmeta(b, jid2)
    if ai_tags_kao_string:
        for r in b.tabele["predmet_dokumenti"]:
            if r["id"] == red2["id"]:
                r["ai_tags"] = json.dumps({"_klasifikacija_pouzdanost": "niska"})
    _ai_klasifikacija(b, red2["id"])
    assert _dok_predmeta(b, jid2)["tip_dokaza"] == "podnesak"


def test_4_uslov_odbijen_od_baze_rezervni_put_i_dalje_cuva_odluku(ok, monkeypatch):
    """Ako PostgREST odbije `ai_tags->>…` uslov, klasifikacija čita oznaku pre upisa — ljudska vrsta ostaje."""
    k, b = ok
    from tests import ns005_harness as h
    jid = _spreman(k)
    doc_id = _posao(k, jid)["dokument"]["document_id"]
    assert _ispravi(k, doc_id, "appeal", "lawsuit").status_code == 200
    _prikaci(k, jid)
    orig = h._Upit.execute

    def execute(self):
        if any(kl and "->>" in kl for _, kl, _v in self.filt):
            raise Exception('{"code": "PGRST100", "message": "failed to parse filter"}')
        return orig(self)
    monkeypatch.setattr(h._Upit, "execute", execute)
    red = _dok_predmeta(b, jid)
    _ai_klasifikacija(b, red["id"])
    assert _dok_predmeta(b, jid)["tip_dokaza"] == "appeal"
    # i bez oznake rezervni put upisuje AI vrstu (ne gasi klasifikaciju)
    jid2 = _spreman(k, tekst=TUZBA_2)
    _prikaci(k, jid2)
    _ai_klasifikacija(b, _dok_predmeta(b, jid2)["id"])
    assert _dok_predmeta(b, jid2)["tip_dokaza"] == "podnesak"


# ── 5: dva korisnika ne mogu ispravljati dokumente jedan drugog ───────────────────────────────────────

def test_5_tudji_korisnik_ne_menja_ni_pre_ni_posle_prikacivanja(ok):
    k, b = ok
    jid = _spreman(k)
    doc_id = _posao(k, jid)["dokument"]["document_id"]
    r = _ispravi(k, doc_id, "appeal", "lawsuit", korisnik="B")
    assert r.status_code == 404
    assert _intake_dok(b, jid)[0]["document_type"] == "lawsuit"
    _prikaci(k, jid)
    red = _dok_predmeta(b, jid)
    for predmet in (PA, PB):
        r = _ispravi_u_predmetu(k, red["id"], "appeal", "lawsuit", predmet=predmet, korisnik="B")
        assert r.status_code == 404, (predmet, r.text)
    assert _dok_predmeta(b, jid)["tip_dokaza"] == "lawsuit" and OZNAKA not in _tagovi(_dok_predmeta(b, jid))
    assert _aud(b) == [] and not [o for o in b.tabele["intake_processing_outcomes"] if o.get("user_corrected")]
    assert k.post(f"/api/smart-intake/documents/{doc_id}/vrsta", json={"vrsta": "appeal", "prethodna": "lawsuit"}).status_code == 401


# ── 6: dva dokumenta istog naziva ostaju nezavisna ────────────────────────────────────────────────────

def test_6_isti_naziv_fajla_nezavisni_dokumenti(ok):
    k, b = ok
    j1 = _spreman(k, tekst=TUZBA, ime="tuzba.txt")
    j2 = _spreman(k, tekst=TUZBA_2, ime="tuzba.txt")
    d1 = _posao(k, j1)["dokument"]["document_id"]
    assert _ispravi(k, d1, "appeal", "lawsuit").status_code == 200
    assert _intake_dok(b, j1)[0]["document_type"] == "appeal"
    assert _intake_dok(b, j2)[0]["document_type"] == "lawsuit"
    assert _posao(k, j2)["dokument"]["tip_odredio_advokat"] is False
    _prikaci(k, j1)
    _prikaci(k, j2)
    r1, r2 = _dok_predmeta(b, j1), _dok_predmeta(b, j2)
    assert r1["naziv_fajla"] == r2["naziv_fajla"] == "tuzba.txt"
    assert (r1["tip_dokaza"], OZNAKA in _tagovi(r1)) == ("appeal", True)
    assert (r2["tip_dokaza"], OZNAKA in _tagovi(r2)) == ("lawsuit", False)
    assert _ispravi_u_predmetu(k, r2["id"], "judgment", "lawsuit").status_code == 200
    assert (_dok_predmeta(b, j1)["tip_dokaza"], _dok_predmeta(b, j2)["tip_dokaza"]) == ("appeal", "judgment")


# ── 7: segmentiran upload menja isključivo odabrani dokument ──────────────────────────────────────────

def _segmentiran_pdf():
    import io
    import fitz
    strane = [
        ["TUŽBA", "Osnovnom sudu u Beogradu", "Tužilac: Marko Petrović", "Strana 1 od 2"],
        ["Nastavak obrazloženja tužbe i dokazni predlozi tužioca.", "Strana 2 od 2"],
        ["PUNOMOĆJE", "Ovlašćujem advokata da me zastupa u parnici.", "Strana 1 od 1"],
    ]
    d = fitz.open()
    for redovi in strane:
        s = d.new_page(width=595, height=842)
        tw = fitz.TextWriter(s.rect)
        for i, red in enumerate(redovi):
            tw.append((50, 80 + i * 30), red, font=fitz.Font("helv"), fontsize=14)
        tw.write_text(s)
    buf = io.BytesIO()
    d.save(buf)
    d.close()
    return buf.getvalue()


def test_7_segmentiran_upload_menja_samo_izabrani_deo(ok):
    pytest.importorskip("fitz")
    k, b = ok
    r = k.post("/api/smart-intake/documents", files=[("files", ("paket.pdf", _segmentiran_pdf(), "application/pdf"))],
               headers=zaglavlje("A"))
    jid = r.json()["rezultati"][0]["job_id"]
    assert _obradi() is True
    x = _posao(k, jid)
    assert [d["tip"] for d in x["dokumenti"]] == ["lawsuit", "power_of_attorney"], x["dokumenti"]
    d1, d2 = (d["document_id"] for d in x["dokumenti"])

    assert _ispravi(k, d2, "contract", "power_of_attorney").status_code == 200
    x = _posao(k, jid)
    assert [(d["tip"], d["tip_odredio_advokat"]) for d in x["dokumenti"]] == [("lawsuit", False), ("contract", True)]
    seg2 = next(s for s in b.tabele["intake_job_segments"] if s["document_id"] == d2)
    [isp] = [o for o in b.tabele["intake_processing_outcomes"] if o.get("user_corrected")]
    assert isp["segment_id"] == seg2["id"]

    _prikaci(k, jid)
    redovi = {r["source_intake_job_segment_id"]: r for r in b.tabele["predmet_dokumenti"] if r.get("source_intake_job_id") == jid}
    assert len(redovi) == 2
    seg1 = next(s for s in b.tabele["intake_job_segments"] if s["document_id"] == d1)
    assert (redovi[seg1["id"]]["tip_dokaza"], OZNAKA in _tagovi(redovi[seg1["id"]])) == ("lawsuit", False)
    assert (redovi[seg2["id"]]["tip_dokaza"], OZNAKA in _tagovi(redovi[seg2["id"]])) == ("contract", True)


def test_7b_ispravka_bez_pouzdane_veze_sa_delom_se_odbija(ok):
    """Posao ima segmente, a dokument nema svoj segment: veza nije pouzdana → 409, bez upisa (nikad po nazivu)."""
    k, b = ok
    jid = _spreman(k)
    doc_id = _posao(k, jid)["dokument"]["document_id"]
    b.tabele["intake_job_segments"].append({"id": "seg-tudji", "intake_job_id": jid, "document_id": "neki-drugi",
                                            "segment_index": 0})
    r = _ispravi(k, doc_id, "appeal", "lawsuit")
    assert r.status_code == 409 and "pouzdano povezati" in r.json()["detail"]
    assert _intake_dok(b, jid)[0]["document_type"] == "lawsuit" and _aud(b) == []


# ── 8: dvostruki klik i konkurentni zahtevi ne prave kontradiktorno stanje ─────────────────────────────

def test_8_dvostruki_klik_jedan_zapis(ok):
    k, b = ok
    jid = _spreman(k)
    doc_id = _posao(k, jid)["dokument"]["document_id"]
    assert _ispravi(k, doc_id, "appeal", "lawsuit").json()["promenjeno"] is True
    r = _ispravi(k, doc_id, "appeal", "lawsuit")
    assert r.status_code == 200 and r.json()["promenjeno"] is False
    assert len(_aud(b)) == 1 and len([o for o in b.tabele["intake_processing_outcomes"] if o.get("user_corrected")]) == 1


def test_8_zastareo_prikaz_ne_gazi_noviju_ispravku(ok):
    k, b = ok
    jid = _spreman(k)
    doc_id = _posao(k, jid)["dokument"]["document_id"]
    assert _ispravi(k, doc_id, "appeal", "lawsuit").status_code == 200           # prozor 1
    r = _ispravi(k, doc_id, "judgment", "lawsuit")                                # prozor 2 još vidi „tužba“
    assert r.status_code == 409 and "u međuvremenu" in r.json()["detail"]
    assert _intake_dok(b, jid)[0]["document_type"] == "appeal" and len(_aud(b)) == 1
    _prikaci(k, jid)
    red = _dok_predmeta(b, jid)
    assert _ispravi_u_predmetu(k, red["id"], "judgment", "appeal").status_code == 200
    r = _ispravi_u_predmetu(k, red["id"], "contract", "appeal")                   # zastareo prikaz u predmetu
    assert r.status_code == 409
    assert _dok_predmeta(b, jid)["tip_dokaza"] == "judgment" and _tagovi(_dok_predmeta(b, jid))[OZNAKA]["tip"] == "judgment"


def test_8_prikacivanje_ne_cita_vrstu_dok_se_ispravka_upisuje(ok, monkeypatch):
    """Ispravka drži zauzeće finalizacije: prikačivanje u tom trenutku ne dobija zauzeće (409, bez upisa)."""
    k, b = ok
    from shared import intake_documents, intake_queue
    jid = _spreman(k)
    doc_id = _posao(k, jid)["dokument"]["document_id"]
    tokom = {}
    orig = intake_documents.write_processing_outcome

    async def _usred(*a, **kw):
        tokom["zauzece_finalizacije"] = await intake_queue.claim_finalize(jid)
        return await orig(*a, **kw)
    monkeypatch.setattr(intake_documents, "write_processing_outcome", _usred)
    assert _ispravi(k, doc_id, "appeal", "lawsuit").status_code == 200
    assert tokom["zauzece_finalizacije"] is None
    monkeypatch.setattr(intake_documents, "write_processing_outcome", orig)
    _job_red(b, jid)["finalizing_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    r = _ispravi(k, doc_id, "judgment", "appeal")                                 # prikačivanje u toku
    assert r.status_code == 409 and "u toku" in r.json()["detail"]
    assert _intake_dok(b, jid)[0]["document_type"] == "appeal"


def test_8_AI_upis_izmedju_citanja_i_upisa_advokata_daje_409_ne_mesavinu(ok, monkeypatch):
    k, b = ok
    from tests import ns005_harness as h
    jid = _spreman(k)
    _prikaci(k, jid)
    red = _dok_predmeta(b, jid)
    orig = h._Upit.execute

    def execute(self):
        if (self.t == "predmet_dokumenti" and self.radnja[0] == "update"
                and OZNAKA in ((self.radnja[1] or {}).get("ai_tags") or {})):
            for r in b.tabele["predmet_dokumenti"]:
                if r["id"] == red["id"]:
                    r.update({"tip_dokaza": "sudska_odluka", "ai_tags": '{"_klasifikacija_pouzdanost": "niska"}'})
        return orig(self)
    monkeypatch.setattr(h._Upit, "execute", execute)
    r = _ispravi_u_predmetu(k, red["id"], "appeal", "lawsuit")
    assert r.status_code == 409
    red = _dok_predmeta(b, jid)
    assert red["tip_dokaza"] == "sudska_odluka" and OZNAKA not in _tagovi(red) and _aud(b) == []


# ── 9: nedozvoljena vrsta se odbija ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("vrsta", ["zalba", "podnesak", "", "LAWSUIT", "appeal; drop"])
def test_9_nedozvoljena_vrsta(ok, vrsta):
    k, b = ok
    jid = _spreman(k)
    doc_id = _posao(k, jid)["dokument"]["document_id"]
    assert _ispravi(k, doc_id, vrsta, "lawsuit").status_code == 422
    _prikaci(k, jid)
    red = _dok_predmeta(b, jid)
    assert _ispravi_u_predmetu(k, red["id"], vrsta, "lawsuit").status_code == 422
    assert _intake_dok(b, jid)[0]["document_type"] == "lawsuit" and red["tip_dokaza"] == "lawsuit" and _aud(b) == []


# ── 10: neuspešan upis ili audit nikad nije „uspešna ispravka“ ─────────────────────────────────────────

def test_10_audit_pada_pre_prikacivanja_vraca_vrstu(ok):
    k, b = ok
    jid = _spreman(k)
    doc_id = _posao(k, jid)["dokument"]["document_id"]
    b.audit_pada = True
    r = _ispravi(k, doc_id, "appeal", "lawsuit")
    assert r.status_code == 503 and "nije sačuvana" in r.json()["detail"]
    x = _posao(k, jid)
    assert (x["dokument"]["tip"], x["dokument"]["tip_odredio_advokat"]) == ("lawsuit", False)
    assert _job_red(b, jid)["finalizing_at"] is None
    b.audit_pada = False
    _prikaci(k, jid)                                          # preostali red ispravke ne proglašava AI vrstu ljudskom
    assert OZNAKA not in _tagovi(_dok_predmeta(b, jid))


def test_10_zapis_odluke_pada_vraca_vrstu(ok):
    k, b = ok
    jid = _spreman(k)
    doc_id = _posao(k, jid)["dokument"]["document_id"]
    b.greske["intake_processing_outcomes"] = Exception("connection reset")
    r = _ispravi(k, doc_id, "appeal", "lawsuit")
    del b.greske["intake_processing_outcomes"]
    assert r.status_code == 503
    assert _intake_dok(b, jid)[0]["document_type"] == "lawsuit" and _aud(b) == []


def test_10_vracanje_ne_uspe_ishod_nepoznat_nikad_uspeh(ok, monkeypatch):
    k, b = ok
    from shared import intake_documents
    jid = _spreman(k)
    doc_id = _posao(k, jid)["dokument"]["document_id"]
    b.audit_pada = True
    orig = intake_documents.ispravi_vrstu

    async def _samo_prvi(document_id, nova, prethodna):
        if nova == "lawsuit":
            raise Exception("connection reset")
        return await orig(document_id, nova, prethodna)
    monkeypatch.setattr(intake_documents, "ispravi_vrstu", _samo_prvi)
    r = _ispravi(k, doc_id, "appeal", "lawsuit")
    assert r.status_code == 503 and "nije poznat" in r.json()["detail"]
    assert _job_red(b, jid)["finalizing_at"] is None


def test_10_upis_vrste_pada_nije_uspeh_i_zauzece_oslobodjeno(ok):
    k, b = ok
    jid = _spreman(k)
    doc_id = _posao(k, jid)["dokument"]["document_id"]
    from tests import ns005_harness as h
    orig = h._Upit.execute

    def execute(self):
        if self.t == "intake_documents" and self.radnja[0] == "update":
            raise Exception("connection reset")
        return orig(self)
    h_patch = pytest.MonkeyPatch()
    h_patch.setattr(h._Upit, "execute", execute)
    try:
        r = _ispravi(k, doc_id, "appeal", "lawsuit")
    finally:
        h_patch.undo()
    assert r.status_code >= 500
    assert _intake_dok(b, jid)[0]["document_type"] == "lawsuit" and _aud(b) == []
    assert _job_red(b, jid)["finalizing_at"] is None


def test_10_audit_pada_u_predmetu_vraca_vrstu_i_tagove(ok):
    k, b = ok
    jid = _spreman(k)
    _prikaci(k, jid)
    red = _dok_predmeta(b, jid)
    _ai_klasifikacija(b, red["id"])
    pre = dict(_dok_predmeta(b, jid))
    b.audit_pada = True
    r = _ispravi_u_predmetu(k, red["id"], "appeal", "podnesak")
    assert r.status_code == 503 and "nije sačuvana" in r.json()["detail"]
    posle = _dok_predmeta(b, jid)
    assert (posle["tip_dokaza"], posle["ai_tags"]) == (pre["tip_dokaza"], pre["ai_tags"]) == ("podnesak", pre["ai_tags"])
    assert OZNAKA not in _tagovi(posle)


def test_10_prikacivanje_ne_ide_dalje_kad_vrste_advokata_nisu_procitane(ok):
    k, b = ok
    jid = _spreman(k)
    assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", headers=zaglavlje("A")).status_code == 200
    b.greske["intake_processing_outcomes"] = Exception("connection reset")
    r = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": PA}, headers=zaglavlje("A"))
    del b.greske["intake_processing_outcomes"]
    assert r.status_code == 503
    assert [d for d in b.tabele["predmet_dokumenti"] if d.get("source_intake_job_id") == jid] == []
    assert _job_red(b, jid)["finalizing_at"] is None


def test_10_prikaz_posla_ne_pada_kad_vrste_advokata_nisu_procitane(ok):
    k, b = ok
    jid = _spreman(k)
    b.greske["intake_processing_outcomes"] = Exception("connection reset")
    x = _posao(k, jid)
    del b.greske["intake_processing_outcomes"]
    assert x["dokument"]["tip"] == "lawsuit" and x["dokument"]["tip_odredio_advokat"] is None   # nepoznato, ne „ne“


@pytest.mark.parametrize("gde", ["prijem", "predmet"])
def test_10_audit_baca_izuzetak_nije_uspeh_i_vrsta_vracena(ok, gde):
    """Pad audita kao izuzetak (ne samo `None`): isti ishod — 503 sa vraćenom vrstom, nikad 200 ni promena bez zapisa."""
    k, b = ok
    jid = _spreman(k)
    if gde == "prijem":
        doc_id = _posao(k, jid)["dokument"]["document_id"]
        b.audit_pada = "baca"
        r = _ispravi(k, doc_id, "appeal", "lawsuit")
        assert r.status_code == 503 and "nije sačuvana" in r.json()["detail"]
        assert _intake_dok(b, jid)[0]["document_type"] == "lawsuit"
    else:
        _prikaci(k, jid)
        red = _dok_predmeta(b, jid)
        b.audit_pada = "baca"
        r = _ispravi_u_predmetu(k, red["id"], "appeal", "lawsuit")
        assert r.status_code == 503 and "nije sačuvana" in r.json()["detail"]
        assert _dok_predmeta(b, jid)["tip_dokaza"] == "lawsuit" and OZNAKA not in _tagovi(_dok_predmeta(b, jid))


def test_11_v2_lista_vrsta_je_dozvoljena_taksonomija():
    import json
    import os
    import re
    from shared.intake_classify import DOCUMENT_TYPES
    put = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend-v2-ng", "src", "app.js")
    izvor = open(put, encoding="utf-8").read()
    m = re.search(r"var VRSTE_IZBOR = (\[[^;]*\]);", izvor)
    assert m and json.loads(m.group(1)) == list(DOCUMENT_TYPES)

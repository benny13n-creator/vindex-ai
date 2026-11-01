# -*- coding: utf-8 -*-
"""S10 — kompletan lokalni end-to-end: JEDAN sintetički predmet kroz sve Bojanove zahteve, stvarnim rutama nad
izolovanom bazom u memoriji (solo okruženje), stvarnim intake radnikom, STVARNIM OCR-om (Tesseract) i stvarnim SMTP
transportom prema lokalnom serveru na 127.0.0.1 (nijedna poruka ne napušta računar).

Zamenjeni su samo modeli: klasifikacija dokaza (tvrdnje = redovi teksta) i Genome (vraća protivrečnosti iz specifikacije
nad STVARNIM oznakama tvrdnji iz prompta). Sve odluke donosi „advokat“ kroz iste rute kao V2.

Tok: klijent → provera sukoba → opis i cilj → predmet → 4 formata (digitalni PDF, sken PDF, PNG, DOCX) uz OCR →
pregled i ispravka → prikačivanje → tvrdnje sa izvorima (B5) → lažna i stvarna protivrečnost (B7) → hronologija → rokovi
i odluke → ročište iz dokumenta i zakazivanje → Case Actions → naplata i faktura → PDF/CSV → nadležnost i čl. 55a →
podsetnik kroz lokalni SMTP → ponovni pokušaji i konkurentnost → korisnik B nad svim ključnim resursima.

Transakcione trke nad PRAVOM bazom NISU ovde (baza u memoriji nije dokaz atomarnosti) — dokazuju ih PostgreSQL testovi
navedeni u ledgeru (`test_ocr001_trka_postgres`, `test_ba05_migracija_144_postgres`, `test_ba04_…_postgres`,
`test_s02_odluka_postgres`, `test_rc_billing_gate`)."""
import asyncio
import copy
import email
import html as _html
import json
import re
import threading
from datetime import timedelta
from unittest.mock import patch

import pytest

from routers.email_notif import _danas_beograd
from tests import ns006_realni_predmet as rp
from tests import test_b10_reminder_claim as b10
from tests.test_n1_zlatni_prijem import _OCR, _docx, _pdf, _raster_png, _sken_pdf
from tests.test_n7_azuriranje_predmeta import _sr, lanac  # noqa: F401 — `lanac` je fixture (audit lanac sa `seq`)
from tests.test_osb002_solo_tok import A, B, _do_kraja_dogadjaja, _radnik, solo  # noqa: F401
from tests.test_s2_smtp_transport_lokalno import LokalniSmtp, _sertifikat

pytestmark = pytest.mark.skipif(_OCR is None, reason="S10 traži stvaran OCR (Tesseract); CI produkcione slike: VINDEX_REQUIRE_OCR=1")

SUTRA = _danas_beograd() + timedelta(days=1)
ZA_5 = _danas_beograd() + timedelta(days=5)
ZA_10 = _danas_beograd() + timedelta(days=10)
OPIS = ("Klijent Stefan Primerovic dobio je resenje o otkazu od Beta Primer DOO. Cilj: ponistaj resenja o otkazu i "
        "isplata zarade. Oznaka S10-BOJAN.")
DOKUMENTI = {
    "01 Resenje digitalno.pdf": ("pdf", ["OSNOVNI SUD U NOVOM SADU", "Posl. br. P 7101/2026", "RESENJE",
                                         f"Pripremno rociste zakazuje se za {_sr(SUTRA)} godine u 09:30 casova, sudnica 7.",
                                         f"Rok za odgovor na tuzbu istice {_sr(SUTRA)} godine.",
                                         f"Rok za uplatu sudske takse istice {_sr(SUTRA)} godine.",
                                         "Resenje o otkazu je uruceno tuziocu 17.03.2025. godine."]),
    "02 Nalog.docx": ("docx", ["NALOG ZA UPLATU", "Posl. br. P 7101/2026",
                               f"Rok za uplatu dodatne sudske takse istice {_sr(ZA_5)} godine.",
                               "Posiljka je urucena primaocu 25.03.2025. godine."]),
    "03 Dostavnica skenirana.pdf": ("sken", ["DOSTAVNICA", "Primalac: Stefan Primerovic", "Uruceno dana 05.02.2026. godine.",
                                             f"Rok za zalbu istice {_sr(ZA_10)} godine."]),
    "04 Povratnica fotografija.png": ("png", ["POVRATNICA", "Primalac: Beta Primer DOO", "Uruceno dana 06.02.2026. godine."]),
}
_TIP = {"pdf": "application/pdf", "sken": "application/pdf", "png": "image/png",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
_BAJTOVI: dict = {}
TAKSE = ("Razlika u rokovima za uplatu takse", "Rok za uplatu sudske takse", "Rok za uplatu dodatne sudske takse")
URUCENJE = ("Datum urucenja resenja", "uruceno tuziocu 17.03", "urucena primaocu 25.03")


def _sadrzaj(ime):
    if ime not in _BAJTOVI:
        vrsta, redovi = DOKUMENTI[ime]
        _BAJTOVI[ime] = {"pdf": _pdf, "docx": _docx, "sken": _sken_pdf, "png": _raster_png}[vrsta](redovi)
    return _BAJTOVI[ime]


def _klasifikuj(naziv, tekst):
    redovi = [l.strip() for l in tekst.splitlines() if l.strip() and not l.strip().isupper() and not l.startswith("Posl. br.")]
    return {"tip_dokaza": "dopis", "pravni_elementi": [], "ai_tags": {}, "kljucne_cinjenice": redovi}


def _genome_model(stanje):
    async def _pozovi(client, combined, n):
        if stanje.get("nepotpun"):
            return '{"tip_predmeta": "radni_spor", "kontradikcije": ['            # model vrati prekinut odgovor
        claim = dict(re.findall(r"(CLAIM-\d+): ([^\n]+)", combined))
        g = copy.deepcopy(rp._genome(0, False, 0, 0))
        for polje in ("verzija", "_analiza_osnov", "_genome_docs_count", "_genome_docs_preskoceno", "_dokumenti_bez_teksta", "_verifikacija"):
            g.pop(polje, None)
        g["datumi_kljucni"], g["rokovi_kriticni"], g["kontradikcije"] = [], [], []
        for labela, a, b in (TAKSE, URUCENJE):
            ca = [c for c, t in claim.items() if a in t and "dodatne" not in t]
            cb = [c for c, t in claim.items() if b in t]
            if ca and cb:
                g["kontradikcije"].append({"issue_label": labela, "claim_refs": [ca[0], cb[0]], "relation_type": "cinjenica_cinjenica",
                                           "opis": f"{a} / {b}", "tezina": "vazna"})
        return json.dumps(g, ensure_ascii=False)
    return _pozovi


@pytest.fixture
def svet(lanac, monkeypatch):
    k, b = lanac
    import routers.case_dna as cd
    import routers.evidence as ev
    stanje = {}
    monkeypatch.setattr(ev, "_klasifikuj_dokument", _klasifikuj)
    monkeypatch.setattr(cd, "_pozovi_genome_api", _genome_model(stanje))
    for t in ("billing_entries", "fakture", "timer_sessions", "tarifne_stavke_custom", "email_notif_log"):
        b.tabele.setdefault(t, [])
    return k, b, stanje


def _kon(k, pid, h=A):
    g = k.get(f"/api/predmeti/{pid}/genome-v2", headers=h)
    assert g.status_code == 200, g.text
    return g.json()["kontradikcije"]


def _odluka(k, pid, labela, radnja, h=A):
    kon = _kon(k, pid)
    x = next(x for x in kon["aktivne"] + kon["za_pregled"] + kon["zatvorene"] if x["sporna_tacka"] == labela)
    o = x["odluka"]
    return k.post(f"/api/predmeti/{pid}/sporne-tacke/{o['issue_id']}/{radnja}",
                  json={"ocekivano": {"status": o["status"], "odluka_at": o["odluka_at"], "sadrzaj": o["sadrzaj"]}}, headers=h)


def _akcije(b, pid):
    return sorted(a.get("razlog") for a in b.tabele["case_actions"]
                  if a["predmet_id"] == pid and a.get("tip") == "RAZRESITI_KONTRADIKCIJU" and a.get("status") == "open")


def _rokovi(b, pid):
    return {h["dogadjaj"]: h for h in b.tabele["predmet_hronologija"] if h["predmet_id"] == pid and h.get("vrsta") == "rok"}


def _podsetnik(b, server):
    import routers.email_notif as en
    from shared.rate import limiter
    limiter.reset()
    with patch.object(en, "_get_supa", return_value=b), patch.object(en, "_SMTP_HOST", "127.0.0.1"), \
         patch.object(en, "_SMTP_PORT", server.port), patch.object(en, "_SMTP_USER", "test-korisnik"), \
         patch.object(en, "_SMTP_PASS", "test-lozinka"), patch.object(en, "_FROM_ADDR", "podsetnik@example.invalid"):
        return asyncio.run(en.posalji_podsetnike(b10._request(), user={"user_id": "cron", "email": ""}))


def _html_poruke(primljeno):
    p = email.message_from_bytes(primljeno["telo"])
    return _html.unescape(next(d for d in p.walk() if d.get_content_type() == "text/html").get_payload(decode=True).decode()).lower()


def test_s10_jedan_predmet_kroz_ceo_bojanov_tok(svet, tmp_path):
    k, b, stanje = svet

    # 1–4: klijent, provera sukoba, opis i cilj, jedan predmet
    kid = k.post("/klijenti", json={"tip": "fizicko_lice", "ime": "Stefan", "prezime": "Primerovic"}, headers=A).json()["klijent"]["id"]
    coi = k.post("/api/conflict-check", json={"ime_prezime": "Beta Primer DOO"}, headers=A)
    assert coi.status_code == 200 and [x for x in coi.json()["konflikti"] if x.get("sloj") == "predmeti"] == []
    r = k.post("/api/intake/kreiraj", json={"klijent_id": kid, "naziv": "Primerovic protiv Beta Primer", "opis": OPIS}, headers=A)
    assert r.status_code == 200 and r.json()["klijent_povezan"] is True, r.text
    pid = r.json()["predmet_id"]
    predmet = next(p for p in b.tabele["predmeti"] if p["id"] == pid)
    assert "Cilj:" in predmet["opis"] and "S10-BOJAN" in predmet["opis"]
    assert [(v["predmet_id"], v["klijent_id"]) for v in b.tabele["predmet_klijenti"]] == [(pid, kid)]

    # 5–8: četiri formata, stvaran OCR, pregled i ispravka, prikačivanje istom predmetu
    fajlovi = [("files", (ime, _sadrzaj(ime), _TIP[v])) for ime, (v, _) in DOKUMENTI.items()]
    r = k.post("/api/smart-intake/documents", files=fajlovi, headers=A)
    assert r.status_code == 202, r.text
    poslovi = {x["filename"]: x["job_id"] for x in r.json()["rezultati"] if x["ok"]}
    assert set(poslovi) == set(DOKUMENTI)
    for _ in range(10):
        if not _radnik():
            break
    ispravka = None
    for ime, jid in poslovi.items():
        g = k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()
        if ime.startswith("01") and ispravka is None:
            ent = next((e for e in g["entiteti"] if e["entity_type"] in ("case_number", "court")), None)
            assert ent, g["entiteti"]                                                 # pregled + ispravka su OBAVEZAN korak toka
            ispravka = (ent["entity_id"], "P 7101/2026 (provereno)")
            assert k.post(f"/api/smart-intake/entities/{ent['entity_id']}/correct", json={"corrected_value": ispravka[1]},
                          headers=A).status_code == 200
        if g["job"]["status"] == "awaiting_review":
            assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", json={}, headers=A).status_code == 200
        f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
        assert f.status_code == 200 and f.json()["ok"] is True, (ime, f.text)
    dok = {d["naziv_fajla"]: d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid}
    assert set(dok) == set(DOKUMENTI), sorted(dok)                                   # svi validni → ISTI predmet
    assert all((d.get("tekst_sadrzaj") or "").strip() for d in dok.values())         # OCR je stvarno pročitao sken i foto
    ocr = {d["intake_job_id"]: d for d in b.tabele["intake_documents"]}
    assert ocr[poslovi["03 Dostavnica skenirana.pdf"]]["ocr_used"] is True and ocr[poslovi["04 Povratnica fotografija.png"]]["ocr_used"] is True
    assert ocr[poslovi["01 Resenje digitalno.pdf"]]["ocr_used"] is False
    assert len([p for p in b.tabele["predmeti"] if p["user_id"] == "uid-A"]) == 1
    isp = next(e for e in b.tabele["extracted_entities"] if e["id"] == ispravka[0])
    assert isp.get("corrected_value") == ispravka[1] and isp.get("value") != ispravka[1]   # ispravka sačuvana, original ostaje
    _do_kraja_dogadjaja(b, najvise=12)

    # 7. B5: tvrdnje iz dokumenata imaju stvaran izvor (dokument) i nisu „utvrđene“ niti advokatom potvrđene
    tvrdnje = [d for d in b.tabele["predmet_dokazi"] if d["predmet_id"] == pid]
    assert tvrdnje and all(d.get("dokument_id") in {x["id"] for x in dok.values()} for d in tvrdnje)
    uruc = [d for d in tvrdnje if "uruceno tuziocu 17.03" in (d.get("tvrdnja") or "")]
    assert uruc and uruc[0]["dokument_id"] == dok["01 Resenje digitalno.pdf"]["id"]

    # 8. B7: lažna (dve različite takse) i stvarna (dva datuma uručenja) — obe KANDIDATI, bez akcije
    kon = _kon(k, pid)
    assert kon["aktivne"] == [] and {x["sporna_tacka"] for x in kon["za_pregled"]} == {TAKSE[0], URUCENJE[0]}
    assert _akcije(b, pid) == []
    assert _odluka(k, pid, TAKSE[0], "odbij").status_code == 200
    assert _odluka(k, pid, URUCENJE[0], "potvrdi").status_code == 200
    _do_kraja_dogadjaja(b, najvise=10)
    kon = _kon(k, pid)
    assert [x["sporna_tacka"] for x in kon["aktivne"]] == [URUCENJE[0]]
    assert {x["sporna_tacka"]: x["stanje"] for x in kon["zatvorene"]}.get(TAKSE[0]) == "ODBIJENA"
    assert _akcije(b, pid) == [URUCENJE[0]]                                            # 12. Case Actions samo za potvrđenu

    # 9. hronologija: rokovi sa izvorom (dokument), nijedan potvrđen bez advokata
    rok = _rokovi(b, pid)
    # Advokat bira ŠTA potvrđuje po nazivu kandidata (Danas, kalendar, email): svaki rok mora nositi SVOJU rečenicu iz
    # dokumenta, a rok pročitan OCR-om oznaku „OCR, proveriti“ (S05). Dva roka istog dana se ne smeju razlikovati samo
    # rednim brojem.
    assert len(rok) == 4, sorted(rok)
    odgovor = next((h for d, h in rok.items() if "odgovor na tuzbu istice" in d.lower()), None)
    taksa = next((h for d, h in rok.items() if "uplatu sudske takse istice" in d.lower()), None)
    dodatna = next((h for d, h in rok.items() if "dodatne sudske takse istice" in d.lower()), None)
    zalba = next((h for d, h in rok.items() if "zalbu istice" in d.lower()), None)
    assert odgovor and taksa and dodatna and zalba, sorted(rok)
    assert "(OCR, proveriti)" in zalba["dogadjaj"] and "OCR" not in odgovor["dogadjaj"], (zalba["dogadjaj"], odgovor["dogadjaj"])
    assert odgovor["datum_iso"] == taksa["datum_iso"] == SUTRA.isoformat()            # INV-07: dve obaveze istog dana
    assert {h["dokument_id"] for h in (odgovor, taksa)} == {dok["01 Resenje digitalno.pdf"]["id"]}
    from shared.rok_potvrda import potvrdjeni_ids
    assert potvrdjeni_ids([odgovor["id"], taksa["id"], dodatna["id"]]) == set()

    # 10. odluke o rokovima: potvrdi jedan, odbij drugi istog dana, treći ostaje nepotvrđen
    assert k.post(f"/api/rokovi/{odgovor['id']}/potvrdi", json={}, headers=A).status_code == 200
    assert k.post(f"/api/rokovi/{taksa['id']}/odbij", json={}, headers=A).status_code == 200
    assert potvrdjeni_ids([odgovor["id"], taksa["id"], dodatna["id"]]) == {odgovor["id"]}
    # advokat ispravlja OCR-om pročitan datum žalbe: nova obaveza je potvrđena, pogrešan datum se ne citira
    tacan_zalba = ZA_10 + timedelta(days=2)
    assert k.post(f"/api/rokovi/{zalba['id']}/ispravi", json={"datum_iso": tacan_zalba.isoformat()}, headers=A).status_code == 200
    ispr = [h for h in b.tabele["predmet_hronologija"] if h["predmet_id"] == pid and h.get("akter") == "Advokat (ispravka predloga)"]
    assert len(ispr) == 1 and ispr[0]["datum_iso"] == tacan_zalba.isoformat() and potvrdjeni_ids([ispr[0]["id"], zalba["id"]]) == {ispr[0]["id"]}
    assert "Rok za zalbu istice … godine." in ispr[0]["dogadjaj"] and _sr(ZA_10) not in ispr[0]["dogadjaj"]
    assert ispr[0]["dogadjaj"].endswith(f"datum ispravio advokat: {tacan_zalba.strftime('%d.%m.%Y.')}"), ispr[0]["dogadjaj"]

    # 11. ročište: predlog iz dokumenta → advokat zakazuje (dupli klik = jedno)
    pr = k.get(f"/api/rocista/predlozi?predmet_id={pid}", headers=A).json()["predlozi"]
    assert [(x["datum"], x["vreme"]) for x in pr] == [(SUTRA.isoformat(), "09:30")]
    assert [x for x in b.tabele.get("rocista", []) if x["predmet_id"] == pid] == []
    telo = {"predmet_id": pid, "sud": pr[0]["sud"], "datum": pr[0]["datum"], "vreme": pr[0]["vreme"], "sudnica": pr[0].get("sudnica")}
    assert k.post("/api/rocista", json=telo, headers=A).status_code == 200
    k.post("/api/rocista", json=telo, headers=A)
    roc = [x for x in b.tabele["rocista"] if x["predmet_id"] == pid]
    assert len(roc) == 1

    # 13. naplata: rad, faktura izdata → plaćena, zastareo prikaz 409
    eid = k.post("/billing/entries", json={"predmet_id": pid, "opis": "Priprema odgovora na tuzbu", "iznos_rsd": 1234.56},
                 headers=A).json()["entry"]["id"]
    f = k.post("/billing/faktura", json={"predmet_id": pid, "entry_ids": [eid], "klijent_naziv": "Stefan Primerovic", "pdv_stopa": 20},
               headers=A).json()["faktura"]
    next(x for x in b.tabele["fakture"] if x["id"] == f["id"]).setdefault("datum_fakture", _danas_beograd().isoformat())
    put = f"/billing/faktura/{f['id']}/status"
    assert k.patch(put, json={"status": "izdata", "iz_statusa": "nacrt"}, headers=A).status_code == 200
    assert k.patch(put, json={"status": "placena", "iz_statusa": "izdata"}, headers=A).status_code == 200
    assert k.patch(put, json={"status": "placena", "iz_statusa": "izdata"}, headers=A).status_code == 409

    # 14. PDF i CSV — čitanjem stvarno generisanih fajlova
    pdf = k.get(f"/api/predmeti/{pid}/pdf-export", headers=A)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    import pymupdf
    t = "\n".join(s.get_text() for s in pymupdf.open(stream=pdf.content, filetype="pdf"))
    t1 = " ".join(t.split())
    assert "Primerovic protiv Beta Primer" in t1
    assert re.search(r"\[ODBIJENO\] [^\[]*uplatu sudske takse", t1), t1[:2000]
    assert re.search(r"\[NEPOTVRĐENO\] [^\[]*dodatne sudske takse", t1), t1[:2000]
    assert not re.search(r"\[(NEPOTVRĐENO|ODBIJENO)\] [^\[]*odgovor na tuzbu", t1)        # potvrđen rok bez oznake
    csv = k.get("/billing/report/csv", params={"od": f"{SUTRA.year}-01-01", "do": f"{SUTRA.year}-12-31"}, headers=A)
    redovi = [r.split(";") for r in csv.content.decode("utf-8-sig").strip().splitlines()]
    stavka = next(r for r in redovi if "Priprema odgovora na tuzbu" in r)
    assert stavka[7] == "1234.56" and stavka[-1] == "plaćena"

    # 15. nadležnost i čl. 55a — deterministički slojevi (model se ne poziva)
    import main as M
    assert "ZPP čl. 42" in M._napomene_nadleznosti("Tužimo dva tužena solidarno, jedan iz Sombora, drugi iz Leskovca. Kom sudu podnosimo tužbu?", "")
    v = M._dodaj_proracun_povrata(
        "Okrivljeni je ranije dva puta osuđen na zatvor od po dve godine za krađe učinjene sa umišljajem, otpušten je pre tri godine, "
        "a sada je sa umišljajem izvršio krađu za koju je propisan zatvor od jedne do osam godina. Ranija dela su istovrsna sa novim.",
        {"status": "success", "data": "--- PRAVNI ZAKLJUČAK\nx"})
    assert v["proracun_povrata"] == "DA" and "više od 4 godine i 6 meseci, najviše 8 godina" in v["data"]

    # 16. podsetnik kroz STVARAN SMTP transport (STARTTLS, AUTH) prema lokalnom serveru — samo potvrđen rok i zakazano ročište
    b.tabele.setdefault("korisnik_email_notif", []).append({"user_id": "uid-A", "aktivan": True, "dan_1": True, "dan_3": False, "dan_7": False})
    b.tabele.setdefault("profiles", []).append({"id": "uid-A", "email": "advokat-a@example.invalid"})
    smtp = LokalniSmtp(*_sertifikat(tmp_path))
    try:
        rez1 = _podsetnik(b, smtp)
        # posle prvog dnevnog pokretanja ročište je pomereno (sud je odložio) → drugo pokretanje istog dana ne šalje ništa
        # ni za stari ni za novi datum (novi nije sutra); promena ostaje u istoriji (S04)
        assert k.patch(f"/api/rocista/{roc[0]['id']}", json={"datum": ZA_5.isoformat()}, headers=A).status_code == 200
        rez2 = _podsetnik(b, smtp)                                                     # duplo pokretanje istog dana
    finally:
        smtp.zatvori()
    assert rez1["poslato"] == 1 and rez1["greske"] == 0 and rez2["poslato"] == 0, (rez1, rez2)
    assert [(x["metadata"]["prethodno"]["datum"], x["metadata"]["novo"]["datum"]) for x in b.tabele["audit_immutable"]
            if x["action"] == "rociste_izmena"] == [(SUTRA.isoformat(), ZA_5.isoformat())]
    assert len(smtp.primljeno) == 1 and smtp.primljeno[0]["za"] == ["advokat-a@example.invalid"]
    poruka = _html_poruke(smtp.primljeno[0])
    assert "odgovor na tuzbu" in poruka and "09:30" in poruka and "sudnica 7" in poruka
    assert "uplatu sudske takse" not in poruka and "dodatne" not in poruka           # odbijen i nepotvrđen rok — nikad

    # 17. retry / reload: ponovljena finalizacija i ponovno osvežavanje ne dupliraju ništa
    pre = (len(b.tabele["predmet_dokumenti"]), len(b.tabele["predmet_dokazi"]), _akcije(b, pid), len(b.tabele["rocista"]))
    for jid in poslovi.values():
        f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A)
        assert f.status_code in (200, 409), f.text
    assert k.post(f"/api/predmeti/{pid}/case-dna/refresh", headers=A).status_code in (200, 202)
    _do_kraja_dogadjaja(b, najvise=10)
    assert (len(b.tabele["predmet_dokumenti"]), len(b.tabele["predmet_dokazi"]), _akcije(b, pid), len(b.tabele["rocista"])) == pre
    kon = _kon(k, pid)
    assert [x["sporna_tacka"] for x in kon["aktivne"]] == [URUCENJE[0]] and TAKSE[0] not in {x["sporna_tacka"] for x in kon["za_pregled"]}
    assert potvrdjeni_ids([odgovor["id"], taksa["id"], dodatna["id"]]) == {odgovor["id"]}

    # 18. korisnik B: nijedan ključni resurs A nije čitljiv ni promenljiv
    jid1 = poslovi["01 Resenje digitalno.pdf"]
    d1 = dok["01 Resenje digitalno.pdf"]["id"]
    kon_a = _kon(k, pid)
    iid = kon_a["aktivne"][0]["odluka"]["issue_id"]
    stanje_a = (copy.deepcopy(b.tabele["predmet_issues"]), len(b.tabele["audit_immutable"]), copy.deepcopy(b.tabele["rocista"]),
                copy.deepcopy(b.tabele["fakture"]))
    zahtevi_b = {
        "predmet": k.get(f"/api/predmeti/{pid}", headers=B).status_code,
        "genome": k.get(f"/api/predmeti/{pid}/genome-v2", headers=B).status_code,
        "dokument": k.get(f"/api/predmeti/{pid}/dokumenti/{d1}/preview", headers=B).status_code,
        "posao": k.get(f"/api/smart-intake/jobs/{jid1}", headers=B).status_code,
        "prikaci": k.post(f"/api/smart-intake/jobs/{jid1}/finalize", json={"predmet_id": pid}, headers=B).status_code,
        "sporna_tacka": k.post(f"/api/predmeti/{pid}/sporne-tacke/{iid}/odbij",
                               json={"ocekivano": {"status": "CONFIRMED", "odluka_at": "x", "sadrzaj": "x"}}, headers=B).status_code,
        "rok": k.post(f"/api/rokovi/{dodatna['id']}/potvrdi", json={}, headers=B).status_code,
        "rociste": k.patch(f"/api/rocista/{roc[0]['id']}", json={"status": "otkazano"}, headers=B).status_code,
        "faktura": k.patch(put, json={"status": "izdata", "iz_statusa": "placena"}, headers=B).status_code,
        "pdf": k.get(f"/api/predmeti/{pid}/pdf-export", headers=B).status_code,
        "osvezavanje": k.post(f"/api/predmeti/{pid}/case-dna/refresh", headers=B).status_code,
    }
    assert all(s in (403, 404) for s in zahtevi_b.values()), zahtevi_b
    assert potvrdjeni_ids([dodatna["id"]]) == set()
    assert (b.tabele["predmet_issues"], len(b.tabele["audit_immutable"]), b.tabele["rocista"], b.tabele["fakture"]) == stanje_a
    csv_b = k.get("/billing/report/csv", params={"od": f"{SUTRA.year}-01-01", "do": f"{SUTRA.year}-12-31"}, headers=B)
    assert "Priprema odgovora na tuzbu" not in csv_b.content.decode("utf-8-sig")


def test_s10_ekstremno_dva_istovremena_finalize_i_dva_istoimena_fajla(svet):
    """Dva istovremena prikačivanja istog posla → tačno jedan dokument (zauzeće finalize-a; PostgreSQL trku dokazuje
    `test_ocr001_trka_postgres`). Dva RAZLIČITA fajla istog imena → dva dokumenta (ime nije identitet, INV-02)."""
    k, b, _ = svet
    kid = k.post("/klijenti", json={"tip": "fizicko_lice", "ime": "Ana", "prezime": "Ekstremovic"}, headers=A).json()["klijent"]["id"]
    pid = k.post("/api/intake/kreiraj", json={"klijent_id": kid, "naziv": "S10 ekstremno", "opis": "Cilj: test."}, headers=A).json()["predmet_id"]
    prvi = _pdf(["DOPIS", "Prvi dopis tuzenom o dugu od 10.000,00 dinara.", "Datum: 01.02.2026."])
    drugi = _pdf(["DOPIS", "Drugi dopis tuzenom o kamati na dug.", "Datum: 02.02.2026."])
    r = k.post("/api/smart-intake/documents", files=[("files", ("scan.pdf", prvi, "application/pdf")),
                                                     ("files", ("scan.pdf", drugi, "application/pdf"))], headers=A)
    jobs = [x["job_id"] for x in r.json()["rezultati"] if x["ok"]]
    assert len(jobs) == 2 and jobs[0] != jobs[1]
    for _ in range(6):
        if not _radnik():
            break
    for jid in jobs:
        if k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()["job"]["status"] == "awaiting_review":
            assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", json={}, headers=A).status_code == 200
    ishodi = []
    niti = [threading.Thread(target=lambda: ishodi.append(k.post(f"/api/smart-intake/jobs/{jobs[0]}/finalize",
                                                               json={"predmet_id": pid}, headers=A).status_code)) for _ in range(2)]
    for n in niti:
        n.start()
    for n in niti:
        n.join()
    assert k.post(f"/api/smart-intake/jobs/{jobs[1]}/finalize", json={"predmet_id": pid}, headers=A).status_code == 200
    dok = [d for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid]
    assert 200 in ishodi and set(ishodi) <= {200, 409} and len(dok) == 2, (ishodi, [d["naziv_fajla"] for d in dok])
    assert {d["source_intake_job_id"] for d in dok} == set(jobs)


def test_s10_ekstremno_nepotpun_odgovor_modela_i_necitljiv_sken(svet):
    """Model vrati prekinut JSON → postojeća analiza, tvrdnje i odluke ostaju, a pad nije prikazan kao uspeh.
    Sken koji OCR ne može da pročita → nije prikačen kao pročitan (INV-03)."""
    k, b, stanje = svet
    kid = k.post("/klijenti", json={"tip": "fizicko_lice", "ime": "Ivan", "prezime": "Nepotpunic"}, headers=A).json()["klijent"]["id"]
    pid = k.post("/api/intake/kreiraj", json={"klijent_id": kid, "naziv": "S10 nepotpun", "opis": "Cilj: test."}, headers=A).json()["predmet_id"]
    for ime in ("01 Resenje digitalno.pdf", "02 Nalog.docx"):
        r = k.post("/api/smart-intake/documents", files=[("files", (ime, _sadrzaj(ime), _TIP[DOKUMENTI[ime][0]]))], headers=A)
        jid = r.json()["rezultati"][0]["job_id"]
        for _ in range(6):
            if not _radnik():
                break
        if k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()["job"]["status"] == "awaiting_review":
            k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", json={}, headers=A)
        assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A).json()["ok"] is True
    _do_kraja_dogadjaja(b, najvise=12)
    assert _odluka(k, pid, URUCENJE[0], "potvrdi").status_code == 200
    _do_kraja_dogadjaja(b, najvise=10)
    pre = (copy.deepcopy([d for d in b.tabele["predmet_dokazi"] if d["predmet_id"] == pid]), _akcije(b, pid),
           {i["label"]: i["status"] for i in b.tabele["predmet_issues"] if i["predmet_id"] == pid},
           copy.deepcopy(next(x for x in b.tabele["predmeti"] if x["id"] == pid).get("case_dna")))
    stanje["nepotpun"] = True
    r = k.post(f"/api/predmeti/{pid}/case-dna/refresh", headers=A)
    assert r.status_code == 200 and r.json().get("case_dna_persisted") is False, r.text          # pad je rečen, ne prećutan
    stanje["nepotpun"] = False
    posle = ([d for d in b.tabele["predmet_dokazi"] if d["predmet_id"] == pid], _akcije(b, pid),
             {i["label"]: i["status"] for i in b.tabele["predmet_issues"] if i["predmet_id"] == pid},
             copy.deepcopy(next(x for x in b.tabele["predmeti"] if x["id"] == pid).get("case_dna")))
    assert pre[3] and posle == pre                                                               # ništa izgubljeno, ništa prepisano

    from PIL import Image, ImageDraw
    import io
    im = Image.new("RGB", (1200, 700), "white")
    ImageDraw.Draw(im).text((60, 60), "Uruceno dana 05.02.2026.", fill="black")       # sitan bitmap font — OCR ga ne čita pouzdano
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    r = k.post("/api/smart-intake/documents", files=[("files", ("sitna.png", buf.getvalue(), "image/png"))], headers=A)
    jid = r.json()["rezultati"][0]["job_id"]
    for _ in range(6):
        if not _radnik():
            break
    if k.get(f"/api/smart-intake/jobs/{jid}", headers=A).json()["job"]["status"] == "awaiting_review":
        k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", json={}, headers=A)
    f = k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid}, headers=A).json()
    assert f["ok"] is False and [x["razlog"] for x in f["dokumenti"]] == ["prazan_tekst"], f
    assert "sitna.png" not in {d["naziv_fajla"] for d in b.tabele["predmet_dokumenti"] if d["predmet_id"] == pid}

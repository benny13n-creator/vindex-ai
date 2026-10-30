# -*- coding: utf-8 -*-
"""Operation Bojan BA-01 — Task 9, zlatni slučaj BA-01…BA-08 na konačnom kodu (Run D: deterministički).

Jedan klijent, jedan predmet, četiri vrste dokumenata (digitalni PDF, skenirani PDF, fotografija PNG, DOCX) i dopuna.
STVARNI: rute, Smart Intake worker i ekstrakcija, OCR (Tesseract), Genome sync, lanac odluka, dispečer podsetnika i
`_smtp_send` prema lokalnom SMTP serveru. ZAMENJENI: izlaz Genome modela (skriptovan, preformulisan između osvežavanja),
stranke iz slobodnog teksta (fixture), embedding. Datumi su relativni prema `_danas_beograd()` i sintetički.
Run M (stvaran model) i browser dokaz: BA01-SPRINT-EVIDENCE/TEST_RESULTS.md.
"""
import copy
import json
import os
import re
from datetime import timedelta

import pytest

import routers.case_dna as cd
import tests.test_osb002_solo_tok as osb
from routers.email_notif import _danas_beograd
from shared.rok_potvrda import potvrdjeni_ids
from tests.test_ba01_obaveze_podsetnici import _poruke, _posalji, _profil, smtp  # noqa: F401 — fixture
from tests.test_ba01_rok_identitet import _osvezi, _rokovi, _stanja
from tests.test_n1_zlatni_prijem import _OCR, _do_kraja, _docx, _pdf, _raster_png, _sken_pdf
from tests.test_n7_azuriranje_predmeta import _sr, lanac  # noqa: F401 — fixture
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401 — fixture
from tests.test_osb002_solo_tok import _do_kraja_dogadjaja

if os.environ.get("VINDEX_REQUIRE_OCR") == "1" and _OCR is None:
    raise RuntimeError("VINDEX_REQUIRE_OCR=1, a Tesseract nije dostupan")
treba_ocr = pytest.mark.skipif(_OCR is None, reason="Tesseract nije dostupan — zlatni slučaj traži stvaran OCR")

D = _danas_beograd()
DONETA, OBICAN, URUCENA_TUZ, URUCENO = (D - timedelta(days=n) for n in (10, 9, 7, 6))
ROK_A, ROK_B, ROK_C = D + timedelta(days=1), D + timedelta(days=21), D + timedelta(days=25)
PUNOMOCJE = D - timedelta(days=15)

DOK = {
    "01 Presuda digitalna.pdf": (lambda: _pdf([
        "OSNOVNI SUD U BEOGRADU", "Posl. br. P 7714/2026 (SINTETICKI)", "Tuzilac: Petar Goldenovic iz Beograda",
        "Tuzeni: Golden Gradnja DOO Beograd", "PRESUDA", f"Presuda je doneta {_sr(DONETA)} godine.",
        "Obavezuje se tuzeni da tuziocu isplati 350.000,00 dinara.",
        f"Rok za izjavljivanje zalbe istice {_sr(ROK_A)} godine.",
        f"Rok za dobrovoljno ispunjenje istice {_sr(ROK_B)} godine.",
        f"U Beogradu, dana {_sr(OBICAN)}"]), "application/pdf"),
    "02 Dostava skenirana.pdf": (lambda: _sken_pdf(["POTVRDA O DOSTAVI", "Posl. br. P 7714/2026",
                                                    f"Presuda je urucena tuzenom {_sr(URUCENA_TUZ)} godine."]), "application/pdf"),
    "03 Dostavnica fotografija.png": (lambda: _raster_png(["DOSTAVNICA", "Primalac: Petar Goldenovic",
                                                           "Posiljka: presuda P 7714/2026", f"Uruceno dana {_sr(URUCENO)} godine."]), "image/png"),
    "04 Punomocje.docx": (lambda: _docx(["PUNOMOCJE", "Petar Goldenovic ovlascuje advokata za zastupanje",
                                         "u predmetu P 7714/2026.", f"U Beogradu, {_sr(PUNOMOCJE)}"]),
                          "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
}
DOPUNA = ["OBAVESTENJE SUDA", "Posl. br. P 7714/2026",
          f"Rok za odgovor na zalbu istice {_sr(ROK_C)} godine.",
          f"Rok za uplatu sudske takse istice {_sr(ROK_C)} godine."]
SKENOVI = ("02 Dostava skenirana.pdf", "03 Dostavnica fotografija.png")
_B: dict = {}


def _bajt(ime):
    if ime not in _B:
        _B[ime] = DOK[ime][0]()
    return _B[ime]


def _iso(d):
    return d.isoformat()


def _rok(naziv, d, opis, lok):
    return {"naziv": naziv, "datum": _iso(d), "opis": opis, "status": "aktivan", "lokacija": lok}


class _Genome:
    """Skriptovan model: isti rokovi i događaji, druga formulacija pri svakom osvežavanju."""
    def __init__(self):
        self.pozivi, self.dopuna = 0, False

    async def __call__(self, client, combined, n):
        self.pozivi += 1
        i = self.pozivi
        g = copy.deepcopy(osb.rp._genome(0, False, 0, 0))
        for polje in ("verzija", "_analiza_osnov", "_genome_docs_count", "_genome_docs_preskoceno", "_dokumenti_bez_teksta", "_verifikacija"):
            g.pop(polje, None)
        g["rokovi_kriticni"] = [_rok(["Rok za izjavljivanje zalbe", "Žalbeni rok", "Rok za žalbu"][i % 3], ROK_A, f"formulacija {i}", "DOK-01"),
                                _rok(["Dobrovoljno ispunjenje", "Rok za ispunjenje", "Ispunjenje obaveze"][i % 3], ROK_B, f"opis {i}", "DOK-01")]
        g["datumi_kljucni"] = [{"opis": "Presuda doneta", "datum": _iso(DONETA), "znacaj": "kriticno", "lokacija": "DOK-01"},
                               {"opis": "Presuda uručena tuženom", "datum": _iso(URUCENA_TUZ), "znacaj": "bitno", "lokacija": "DOK-02"},
                               {"opis": "Presuda uručena tužiocu", "datum": _iso(URUCENO), "znacaj": "bitno", "lokacija": "DOK-03"}]
        if self.dopuna:
            g["rokovi_kriticni"] += [_rok("Odgovor na žalbu", ROK_C, f"v{i}", "DOK-05"), _rok("Sudska taksa", ROK_C, f"t{i}", "DOK-05")]
        return json.dumps(g, ensure_ascii=False)


def _finalizuj(k, poslovi, pid, h=A):
    for jid in poslovi.values():
        if k.get(f"/api/smart-intake/jobs/{jid}", headers=h).json()["job"]["status"] == "awaiting_review":
            assert k.post(f"/api/smart-intake/jobs/{jid}/review/resolve", json={}, headers=h).status_code == 200
            _do_kraja()
        assert k.post(f"/api/smart-intake/jobs/{jid}/finalize", json={"predmet_id": pid, "klijent_strana": "plaintiff"},
                      headers=h).status_code == 200


@treba_ocr
def test_zlatni_slucaj_ba01_ba08(lanac, monkeypatch, smtp):
    k, b = lanac
    t = b.tabele
    genome = _Genome()
    monkeypatch.setattr(cd, "_pozovi_genome_api", genome)
    import shared.intake_extract as ex

    async def _bez_modela(_tekst):
        # Isti oblik kao `extract_free_text_entities` kad model nije dostupan (fallback: svih 5 tipova, bez vrednosti).
        # Fixture `_stranke` vraća samo stranke — taj oblik bi sakrio regex sud. Stranke iz stvarnog modela: Run M.
        return {tip: (None, 0.0) for tip in ("judge", "plaintiff", "defendant", "court", "law_cited")}
    monkeypatch.setattr(ex, "extract_free_text_entities", _bez_modela)
    _profil(b, "uid-A", "advokat-a@example.invalid")

    # ── BA-01: jedan klijent, jedan predmet, opis i cilj ─────────────────────────────────────────────────────────
    kid = k.post("/klijenti", json={"tip": "fizicko_lice", "ime": "Petar", "prezime": "Goldenovic"}, headers=A).json()["klijent"]["id"]
    opis = "Goldenovic protiv Golden Gradnja (SINTETICKI). Cilj: naplata po presudi."
    r = k.post("/api/intake/kreiraj", json={"klijent_id": kid, "naziv": "Goldenovic protiv Golden Gradnja", "opis": opis}, headers=A)
    pid = r.json()["predmet_id"]

    # ── BA-02: četiri vrste dokumenata, jedan zahtev; stvaran OCR ────────────────────────────────────────────────
    r = k.post("/api/smart-intake/documents", files=[("files", (i, _bajt(i), DOK[i][1])) for i in DOK], headers=A)
    poslovi = {x["filename"]: x["job_id"] for x in r.json()["rezultati"] if x["ok"]}
    assert set(poslovi) == set(DOK)
    _do_kraja()
    # ── BA-08 (ispravka pre prikačivanja): advokat ispravlja iznos; original ostaje ─────────────────────────────
    idok = {d["intake_job_id"]: d for d in t["intake_documents"]}
    ent01 = [e for e in t["extracted_entities"] if e["document_id"] == idok[poslovi["01 Presuda digitalna.pdf"]]["id"]]
    iznos = next(e for e in ent01 if e["entity_type"] == "amount")
    assert k.post(f"/api/smart-intake/entities/{iznos['id']}/correct", json={"corrected_value": "350.000,00 dinara (glavnica)"},
                  headers=A).status_code == 200
    _finalizuj(k, poslovi, pid)
    _do_kraja_dogadjaja(b)

    assert [p["id"] for p in t["predmeti"] if p["user_id"] == "uid-A"] == [pid]                               # BA-01
    assert opis in next(p for p in t["predmeti"] if p["id"] == pid)["opis"]
    assert [(v["predmet_id"], v["klijent_id"]) for v in t["predmet_klijenti"]] == [(pid, kid)]
    dok = {d["naziv_fajla"]: d for d in t["predmet_dokumenti"] if d["predmet_id"] == pid}
    assert set(dok) == set(DOK)                                                                                  # BA-02
    for ime in DOK:
        assert idok[poslovi[ime]]["ocr_used"] is (ime in SKENOVI), ime
    assert "DOSTAVI" in dok["02 Dostava skenirana.pdf"]["tekst_sadrzaj"].upper()
    assert "DOSTAVNICA" in dok["03 Dostavnica fotografija.png"]["tekst_sadrzaj"].upper()
    assert _sr(URUCENA_TUZ)[:-1] in dok["02 Dostava skenirana.pdf"]["tekst_sadrzaj"]

    # ── BA-03: broj, sud, iznos, rokovi tačni i vezani za izvor; ništa izmišljeno ──────────────────────────────
    v01 = {}
    for e in ent01:
        v01.setdefault(e["entity_type"], []).append(e)
    assert [e["value"] for e in v01["case_number"]] == ["P 7714/2026"]
    assert [e["value"] for e in v01["court"]] == ["OSNOVNI SUD U BEOGRADU"]                     # ne „… Posl“
    assert iznos["value"] == "350.000,00 dinara" and next(e for e in t["extracted_entities"] if e["id"] == iznos["id"])["corrected_value"] \
        == "350.000,00 dinara (glavnica)"
    assert sorted(e["value"] for e in v01["deadline"]) == sorted([_sr(ROK_A)[:-1], _sr(ROK_B)[:-1]])
    tekst01 = dok["01 Presuda digitalna.pdf"]["tekst_sadrzaj"]
    for e in ent01:
        if e["extraction_method"] == "regex" and e["value"]:
            assert e["value"].split(" ")[0] in tekst01, e                                       # regex vrednost postoji u izvoru
    assert not [e for e in ent01 if e["entity_type"] in ("plaintiff", "defendant", "judge") and e["value"]]  # bez modela: nema izmišljenih

    # ── BA-04: procesni događaji u hronologiji predmeta, sa izvorom ──────────────────────────────────────────────
    det = k.get(f"/api/predmeti/{pid}", headers=A).json()
    pd = det["procesni_dogadjaji"]["stavke"]
    po_id = {d["id"]: n for n, d in dok.items()}
    assert [(x["datum"], po_id.get(x["lokacija"]["dokument_id"]), x["datum_u_izvoru"]) for x in pd] == [
        (_iso(DONETA), "01 Presuda digitalna.pdf", True), (_iso(URUCENA_TUZ), "02 Dostava skenirana.pdf", True),
        (_iso(URUCENO), "03 Dostavnica fotografija.png", True)], pd

    # ── BA-05: tačno dva kandidata iz presude, nepotvrđena; nijedan običan datum; preformulacije ne dupliraju ──────
    for _ in range(2):
        _osvezi(pid)
    rok = {h["datum_iso"]: h for h in _rokovi(b, pid)}
    assert sorted(rok) == sorted([_iso(ROK_A), _iso(ROK_B)]), _rokovi(b, pid)
    assert all(h["dokument_naziv"] == "01 Presuda digitalna.pdf" for h in rok.values())
    for d in (DONETA, OBICAN, URUCENA_TUZ, URUCENO, PUNOMOCJE):
        assert _iso(d) not in rok
    ra, rb = rok[_iso(ROK_A)], rok[_iso(ROK_B)]
    assert _stanja(k, pid) == {ra["id"]: "UNCONFIRMED", rb["id"]: "UNCONFIRMED"}
    assert _posalji(b, smtp)["poslato"] == 0                                                   # nepotvrđeno ne šalje

    # ── BA-06: potvrda A, odbijanje B; ostaju posle osvežavanja i ponovne obrade ─────────────────────────────────
    assert k.post(f"/api/rokovi/{ra['id']}/potvrdi", json={}, headers=A).status_code == 200
    assert k.post(f"/api/rokovi/{rb['id']}/odbij", json={}, headers=A).status_code == 200
    _osvezi(pid)
    r2 = k.post("/api/smart-intake/documents", files=[("files", ("01 Presuda digitalna.pdf", _bajt("01 Presuda digitalna.pdf"),
                                                                 "application/pdf"))], headers=A).json()["rezultati"][0]
    assert r2["already_submitted"] is True
    assert _stanja(k, pid) == {ra["id"]: "CONFIRMED", rb["id"]: "REJECTED"}
    assert potvrdjeni_ids([ra["id"], rb["id"]]) == {ra["id"]}

    # ── BA-07: jedan podsetnik, samo A, tačno jednom ─────────────────────────────────────────────────────────────
    rez = _posalji(b, smtp)
    assert rez["poslato"] == 1 and rez["neisporuceno"] == 0, rez
    [(primalac, telo)] = _poruke(smtp)
    assert "advokat-a@example.invalid" in primalac and _iso(ROK_A) in telo and _iso(ROK_B) not in telo
    assert _posalji(b, smtp)["poslato"] == 0 and len(smtp.primljeno) == 1

    # ── BA-08: dopuna u ISTI predmet; dve obaveze istog dana ostaju dve; ništa staro se ne menja ────────────────
    genome.dopuna = True
    r = k.post("/api/smart-intake/documents", files=[("files", ("05 Obavestenje suda.pdf", _pdf(DOPUNA), "application/pdf"))], headers=A)
    _do_kraja()
    _finalizuj(k, {"05": r.json()["rezultati"][0]["job_id"]}, pid)
    _do_kraja_dogadjaja(b)
    _osvezi(pid)
    assert [p["id"] for p in t["predmeti"] if p["user_id"] == "uid-A"] == [pid]
    assert len([d for d in t["predmet_dokumenti"] if d["predmet_id"] == pid]) == 5
    nove = [h for h in _rokovi(b, pid) if h["datum_iso"] == _iso(ROK_C)]
    assert len(nove) == 2 and len({h["dogadjaj"] for h in nove}) == 2 and {h["akter"] for h in nove} == {"Smart Intake"}, nove
    assert len(_rokovi(b, pid)) == 4
    st = _stanja(k, pid)
    assert st[ra["id"]] == "CONFIRMED" and st[rb["id"]] == "REJECTED" and all(st[h["id"]] == "UNCONFIRMED" for h in nove)
    assert _posalji(b, smtp)["poslato"] == 0 and len(smtp.primljeno) == 1                     # nepotvrđena dopuna ne šalje
    assert not re.search(r"Dokument prihvaćen", json.dumps([x["vrednost"] for x in k.get(f"/api/predmeti/{pid}", headers=A).json()["procesni_dogadjaji"]["stavke"]], ensure_ascii=False))

    # izolacija: drugi korisnik ne vidi, ne menja i ne prima
    assert k.get(f"/api/predmeti/{pid}", headers=B).status_code == 404
    assert k.get(f"/api/smart-intake/jobs/{poslovi['01 Presuda digitalna.pdf']}", headers=B).status_code == 404
    assert k.get(f"/api/rokovi/kandidati?predmet_id={pid}", headers=B).json()["rokovi"] == []
    assert k.post(f"/api/rokovi/{rb['id']}/potvrdi", json={}, headers=B).status_code == 404
    assert _stanja(k, pid)[rb["id"]] == "REJECTED"
